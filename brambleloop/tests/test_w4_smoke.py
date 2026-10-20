"""W4-SMOKE: F-171 production smoke matrix (ops/smoke.py, GET /api/verify/smoke) and F-144
per-feature production readback (ops/readback.py, run by ops/deploy.sh after the deploy)."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT.parent / "ops"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(OPS))

import readback  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus  # noqa: E402
from brambleloop.ops import smoke  # noqa: E402
from brambleloop.runtime.worker import CADENCES  # noqa: E402

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
SHA = "a" * 40


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _healthy(db, *, probe_age_h=1.0, etsy_ok=False, continuity_failed_after=False):
    """A database a healthy production would have written: cadences scheduled for days, every
    cadence completed recently, probes and a continuity proof recent, work completing."""
    with db.session() as s:
        s.add(Job(agent="orchestrator", job_type="ops.heartbeat", status=JobStatus.DONE,
                  idempotency_key="cadence:infra_heartbeat:old", created_at=NOW - timedelta(days=5),
                  finished_at=NOW - timedelta(days=5)))
        for i, (_n, agent, jt, _p) in enumerate(CADENCES):
            s.add(Job(agent=agent, job_type=jt, status=JobStatus.DONE,
                      idempotency_key=f"done:{i}", created_at=NOW - timedelta(minutes=20),
                      finished_at=NOW - timedelta(minutes=10)))
        for action in smoke.PROBES:
            s.add(AuditLog(actor="orchestrator", action=action,
                           at=NOW - timedelta(hours=probe_age_h),
                           detail={"ok": etsy_ok if action == "etsy.probe" else True,
                                   "reason": "ping returned HTTP 403" if action == "etsy.probe"
                                   and not etsy_ok else ""}))
        s.add(AuditLog(actor="orchestrator", action="continuity.verified",
                       at=NOW - timedelta(hours=3), detail={}))
        if continuity_failed_after:
            s.add(AuditLog(actor="orchestrator", action="continuity.failed",
                           at=NOW - timedelta(hours=1), detail={}))
    return db


def _by_name(m):
    return {c["check"]: c for c in m["checks"]}


def test_a_fresh_database_is_unknown_never_pass():
    m = smoke.smoke_matrix(_db(), now=NOW)
    assert m["verdict"] == "UNKNOWN" and m["unknown"], m
    assert not m["failing"]


def test_a_healthy_production_passes_every_check_and_a_refused_probe_still_ran():
    m = smoke.smoke_matrix(_healthy(_db()), now=NOW)
    assert m["verdict"] == "PASS", [c for c in m["checks"] if c["verdict"] != "PASS"]
    c = _by_name(m)
    assert {"probe_ran:model.probe", "probe_ran:vision.probe", "probe_ran:etsy.probe",
            "continuity_restore_proven", "cadence_coverage", "queue_round_trip",
            "search_intelligence_captured"} <= set(c)
    etsy = c["probe_ran:etsy.probe"]
    assert etsy["verdict"] == "PASS" and etsy["evidence"]["provider_answered_ok"] is False
    assert "403" in etsy["evidence"]["provider_reason"]


def test_a_probe_that_stopped_running_fails():
    m = smoke.smoke_matrix(_healthy(_db(), probe_age_h=40), now=NOW)
    assert m["verdict"] == "FAIL"
    assert "probe_ran:model.probe" in m["failing"]


def test_a_failed_restore_after_the_last_proof_fails():
    m = smoke.smoke_matrix(_healthy(_db(), continuity_failed_after=True), now=NOW)
    assert "continuity_restore_proven" in m["failing"]


def test_stale_cadences_and_a_stopped_queue_fail():
    db = _db()
    with db.session() as s:
        s.add(Job(agent="orchestrator", job_type="ops.heartbeat", status=JobStatus.DONE,
                  idempotency_key="cadence:infra_heartbeat:old",
                  created_at=NOW - timedelta(days=5), finished_at=NOW - timedelta(days=5)))
        s.add(Job(agent="orchestrator", job_type="ops.heartbeat", status=JobStatus.PENDING,
                  idempotency_key="cadence:infra_heartbeat:stuck",
                  created_at=NOW - timedelta(hours=3), run_after=NOW - timedelta(hours=3)))
    m = smoke.smoke_matrix(db, now=NOW)
    assert {"cadence_coverage", "queue_round_trip", "search_intelligence_captured"} <= \
        set(m["failing"]), m["failing"]
    assert _by_name(m)["queue_round_trip"]["evidence"]["oldest_due_pending_wait_s"] >= 3 * 3600


# ---- F-144 readback ----------------------------------------------------------------------

def _prod_bodies(sha=SHA, **over):
    verify = {"ok": True, "checks": [{"check": n, "ok": True} for n in (
        "phase_is_shadow", "nothing_published", "publication_was_actually_attempted_and_refused",
        "no_unexpected_dead_letters_in_24h", "every_agent_has_a_cost_ceiling")]}
    bodies = {
        "/health": (200, {"build": {"commit": sha, "known": True},
                          "runner": {"worker_alive": True}}),
        "/api/status": (200, {"boot_guard": {"enforced": True, "ok": True}}),
        "/api/verify": (200, verify),
        "/api/verify/smoke": (200, {"verdict": "PASS"}),
        "/api/build": (200, {"final_master": {"launch_ready": False, "status": "DEGRADED"}}),
        "/api/catalogue": (200, {"published": False}),
        "/api/launch/packet": (401, {"error": "operator credential required"}),
        # W4-CLOSE6 manifest additions (F-144)
        "/api/departments": (200, {"agents": []}),
        "/api/swarm/runtime": (200, {"agent_quality": {}}),
        "/api/funding/packets": (200, {"packets": [{"packet": "model_credit"}]}),
        "/api/offsite": (200, {"configured": True}),
        "/api/continuity": (200, {"last_proof_ok": True}),
        "/api/etsy": (200, {"usable": True}),
    }
    bodies.update(over)
    return bodies


def _fetcher(bodies):
    def fetch(url):
        path = "/" + url.split("/", 3)[3] if url.count("/") >= 3 else "/"
        if path not in bodies:
            raise OSError("unreachable")
        return bodies[path]
    return fetch


def test_every_feature_reads_back_on_a_healthy_deploy():
    out = readback.run(SHA, url="https://prod.invalid", fetch=_fetcher(_prod_bodies()))
    assert out["verdict"] == "PASS" and not out["not_done"], out
    rows = {r for f in out["features"] for r in f["rows"]}
    assert {"F-144", "F-171", "F-172", "F-169"} <= rows


def test_a_feature_that_does_not_read_back_is_not_done():
    bad = _prod_bodies(**{"/api/verify/smoke": (503, {"verdict": "FAIL"})})
    out = readback.run(SHA, url="https://prod.invalid", fetch=_fetcher(bad))
    assert out["verdict"] == "FAIL" and any("smoke" in f for f in out["not_done"])
    other = readback.run("b" * 40, url="https://prod.invalid", fetch=_fetcher(_prod_bodies()))
    assert "release identity" in other["not_done"]


def test_unknown_is_never_a_pass_and_unreachable_is_reported():
    missing = _prod_bodies(**{"/api/status": (200, {})})
    out = readback.run(SHA, url="https://prod.invalid", fetch=_fetcher(missing))
    assert out["verdict"] == "UNKNOWN" and out["reachable"]
    dark = readback.run(SHA, url="https://prod.invalid", fetch=_fetcher({}))
    assert dark["verdict"] == "UNKNOWN" and dark["reachable"] is False


def _serve(bodies):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            code, body = bodies.get(self.path, (404, {"error": "not found"}))
            raw = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c",
                           "user.email=t@example.invalid", *args],
                          capture_output=True, text=True, check=True)


def _deploy_with_readback(make_bodies):
    base = Path(tempfile.mkdtemp(prefix="smoke-deploy-"))
    origin, repo = base / "origin.git", base / "repo"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "ops").mkdir()
    for name in ("deploy.sh", "verify_deploy.py", "readback.py"):
        (repo / "ops" / name).write_bytes((OPS / name).read_bytes())
    (repo / "ops" / "deploy_guard.py").write_text("import sys; sys.exit(0)\n")
    (repo / "ops" / "deployed_sha.py").write_text("print('0' * 40)\n")
    (repo / "README").write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "remote", "add", "origin", str(origin))
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    srv = _serve(make_bodies(head))
    try:
        env = dict(os.environ, BRAMBLELOOP_PRODUCTION_URL=f"http://127.0.0.1:{srv.server_port}",
                   DEPLOY_VERIFY_TIMEOUT="2", DEPLOY_VERIFY_INTERVAL="0.2")
        return head, subprocess.run(["sh", "ops/deploy.sh"], cwd=repo, env=env,
                                    capture_output=True, text=True, timeout=120)
    finally:
        srv.shutdown()


def test_deploy_sh_exits_5_when_a_feature_does_not_read_back_and_0_when_all_do():
    head, ok = _deploy_with_readback(lambda h: _prod_bodies(sha=h))
    assert ok.returncode == 0 and f"DEPLOYED {head} (readback PASS)" in ok.stdout, \
        (ok.stdout, ok.stderr)
    head, bad = _deploy_with_readback(
        lambda h: _prod_bodies(sha=h, **{"/api/verify/smoke": (503, {"verdict": "FAIL"})}))
    assert bad.returncode == 5, (bad.stdout, bad.stderr)
    assert "readback did not pass" in bad.stderr and "smoke" in bad.stderr


def test_the_smoke_route_is_public_read_only_and_never_200_unless_pass():
    from brambleloop.app import security

    assert "/api/verify/smoke" in security.PUBLIC_GET_NOTES
    assert "/api/verify/smoke" not in security.OPERATOR_GET_ROUTES
    main = (ROOT / "src/brambleloop/app/main.py").read_text()
    assert '@app.get("/api/verify/smoke")' in main
    assert 'status_code=200 if m["verdict"] == "PASS" else 503' in main
    assert '"smoke_matrix": smoke' in main


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
