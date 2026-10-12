"""v1.1 integrator wiring: the command-center routes lanes C, F, I and A asked for.

* GET /cc/store-preview (lane F, F-926): owner session required, no-store + noindex.
* /api/cc/operations/recovery/* (lane I W-5): owner session + step-up, refusals are 409s.
* /api/cc/departments/{d}/block|unblock (lane A F-889): block needs only the session (it is
  restrictive); unblock needs step-up. The orchestrator honours the block.

Run: cd brambleloop && PYTHONPATH=src python tests/test_v11_wiring_cc.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="v11_wire_cc_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the wiring harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main, security  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.app.command_center.models import OwnerSession  # noqa: E402
from brambleloop.autonomy import charters, memory, orchestrator  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402

OPS = "w" * 40
PASS = "owner passphrase for the wiring harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db


def anon():
    return TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)


def session():
    c = anon()
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def post(c, csrf, path, body):
    return c.post(path, json=body, headers={
        "X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
        "X-CC-Timestamp": str(int(time.time()))})


def expire_stepup(c):
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    with DB.session() as s:
        s.scalar(select(OwnerSession).where(OwnerSession.public_id == sid)).stepup_until = (
            auth._now() - timedelta(seconds=1))


def test_store_preview_is_owner_only_and_never_cached_or_indexed():
    assert security.owner_session_route("/cc/store-preview")
    r = anon().get("/cc/store-preview")
    assert r.status_code == 401, (r.status_code, r.text[:200])
    # The public PWA shell stays public; only the preview page is gated.
    assert not security.owner_session_route("/cc/index.html")
    c, _ = session()
    r = c.get("/cc/store-preview?viewport=desktop")
    assert r.status_code == 200, r.text[:300]
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["cache-control"] == "no-store"
    assert "noindex" in r.headers["x-robots-tag"]
    assert "content-security-policy" in r.headers
    assert "<script" not in r.text.lower()


def test_recovery_routes_need_stepup_and_refuse_unsafe_cases():
    c, csrf = session()
    r = c.get("/api/cc/operations/recovery")
    assert r.status_code == 200 and "recent" in r.json(), r.text
    assert anon().get("/api/cc/operations/recovery").status_code == 401
    expire_stepup(c)
    r = post(c, csrf, "/api/cc/operations/recovery/rerun-cycle",
             {"cadence": "slo_check", "request_id": "rq-1"})
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    assert post(c, csrf, "/api/cc/auth/step-up", {"passphrase": PASS}).status_code == 200
    r = post(c, csrf, "/api/cc/operations/recovery/rerun-cycle",
             {"cadence": "no_such_cadence", "request_id": "rq-2"})
    assert r.status_code == 409 and r.json()["code"] == "REFUSED_BY_AUTHORITY", r.text
    r = post(c, csrf, "/api/cc/operations/recovery/restart-job",
             {"job_id": "x", "request_id": "rq-3"})
    assert r.status_code == 409, r.text
    r = post(c, csrf, "/api/cc/operations/recovery/rerun-cycle",
             {"cadence": "slo_check", "request_id": "rq-4"})
    assert r.status_code == 200, r.text
    with DB.session() as s:
        jobs = list(s.scalars(select(Job).where(Job.job_type == "ops.slo")))
    assert jobs, "rerun enqueued nothing"
    # Same request id again: one action, not two.
    r = post(c, csrf, "/api/cc/operations/recovery/rerun-cycle",
             {"cadence": "slo_check", "request_id": "rq-4"})
    assert r.status_code == 200, r.text
    with DB.session() as s:
        again = list(s.scalars(select(Job).where(Job.job_type == "ops.slo")))
    assert len(again) == len(jobs), (len(again), len(jobs))


def test_soak_report_route_is_read_only_and_validates_input():
    c, _ = session()
    assert c.get("/api/cc/operations/soak?start=nonsense").status_code == 400
    r = c.get("/api/cc/operations/soak",
              params={"start": "2026-10-06T00:00:00+00:00"})
    assert r.status_code == 200, r.text


def test_department_block_without_stepup_unblock_with_and_the_orchestrator_obeys():
    c, csrf = session()
    expire_stepup(c)
    r = post(c, csrf, "/api/cc/departments/no_such/block", {"reason": "x"})
    assert r.status_code == 404, r.text
    r = post(c, csrf, "/api/cc/departments/growth/block", {"reason": "owner pause"})
    assert r.status_code == 200, r.text
    assert memory.active_block(DB, "growth") is not None
    report = orchestrator.tick(DB, JobQueue(DB), departments=[charters.BY_KEY["growth"]])
    assert report["departments"]["growth"]["state"] == "BLOCKED", report
    r = post(c, csrf, "/api/cc/departments/growth/unblock", {})
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    assert memory.active_block(DB, "growth") is not None
    assert post(c, csrf, "/api/cc/auth/step-up", {"passphrase": PASS}).status_code == 200
    r = post(c, csrf, "/api/cc/departments/growth/unblock", {})
    assert r.status_code == 200, r.text
    assert memory.active_block(DB, "growth") is None
    with DB.session() as s:
        acts = [a.action for a in s.scalars(select(AuditLog).where(
            AuditLog.artifact == "department:growth"))]
    assert acts == ["cc.department.block", "cc.department.unblock"], acts


def test_new_mutating_routes_refuse_without_a_session():
    c = anon()
    paths = ("/api/cc/operations/recovery/restart-job",
             "/api/cc/operations/recovery/release-lease",
             "/api/cc/operations/recovery/rerun-cycle",
             "/api/cc/departments/growth/block", "/api/cc/departments/growth/unblock")
    assert paths
    for p in paths:
        r = c.post(p, json={})
        assert r.status_code in (401, 403), (p, r.status_code)
    with DB.session() as s:
        assert not list(s.scalars(select(Job).where(Job.status == JobStatus.RUNNING)))


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
