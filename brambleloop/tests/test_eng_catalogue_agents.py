"""ENG-CATALOGUE slice 2: the agents panel (`/api/cc/operating-evidence`).

Every figure comes from persisted rows; useful work is judged by `did_no_work` (WORK_KEYS),
self-observation is never useful work, an unreadable part is UNKNOWN (never 0 or OK), and the
route is owner-only and read-only.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_eng_catalogue_agents.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="eng_catalogue_agents_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'agents.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the agents-panel harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, event  # noqa: E402

from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.app.command_center import operating_evidence as O  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus  # noqa: E402
from brambleloop.ops import slo  # noqa: E402
from brambleloop.swarm import orchestrate  # noqa: E402

PASS = "owner passphrase for the agents-panel harness"
os.environ[opsauth.TOKEN_VAR] = "a" * 40
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
main.db.create_all()
DB = main.db
NOW = datetime.now(timezone.utc)
H = timedelta(hours=1)


def _job(job_type, status, *, agent="worker", outputs=None, created=None, finished=None,
         run_after=None, error=""):
    with DB.session() as s:
        j = Job(agent=agent, job_type=job_type, status=status, inputs={}, outputs=outputs or {},
                created_at=created or NOW - H, finished_at=finished,
                run_after=run_after or created or NOW - H, last_error=error)
        s.add(j)
        s.commit()
        return j.id


def _wipe():
    with DB.session() as s:
        for m in (Job, AuditLog, slo.RuntimeSample):
            s.execute(delete(m))
        s.commit()


def _dept(view, key):
    return next(d for d in view["departments"] if d["department"] == key)


def test_last_useful_job_is_judged_by_work_keys_not_by_ran():
    _wipe()
    useful = _job("cir.compile", JobStatus.DONE, outputs={"work_done": 2},
                  finished=NOW - 3 * H)
    _job("cir.compile", JobStatus.DONE, outputs={"work_done": 0}, finished=NOW - H)  # ran, no-op
    _job("cir.compile", JobStatus.DONE, outputs={}, finished=NOW - 2 * H)          # ran, empty
    v = O.view(DB, now=NOW)
    d = _dept(v, "product_truth")
    assert d["last_useful_job"]["state"] == "FOUND"
    assert d["last_useful_job"]["job_id"] == useful
    assert d["completed_24h"] == {"useful": 1, "no_op": 2}
    assert v["last_24h"]["stage_transitions"] == {"validation": 1}
    assert v["state"] == "OK"


def test_a_green_health_check_is_never_useful_work_and_never_ok():
    _wipe()
    _job("ops.health", JobStatus.DONE, outputs={"state": "healthy", "work_done": 9},
         finished=NOW - H)
    _job("ops.heartbeat", JobStatus.DONE, outputs={"work_done": 1}, finished=NOW - H)
    v = O.view(DB, now=NOW)
    for d in v["departments"]:
        assert d["last_useful_job"]["state"] != "FOUND", d
    assert v["last_24h"]["useful"] == 0 and v["state"] == "IDLE"


def test_an_exhausted_scan_is_unknown_never_none():
    _wipe()
    for i in range(6):
        _job("cir.compile", JobStatus.DONE, outputs={"work_done": 0}, finished=NOW - i * H)
    _job("cir.compile", JobStatus.DONE, outputs={"work_done": 1}, finished=NOW - 30 * H)
    with patch.object(O, "SCAN_LIMIT", 4), patch.object(O, "SCAN_BATCH", 2):
        v = O.view(DB, now=NOW)
    lu = _dept(v, "product_truth")["last_useful_job"]
    assert lu["state"] == O.UNKNOWN and lu["scanned"] == 4
    assert _dept(v, "product_truth")["state"] == O.UNKNOWN and v["state"] == O.UNKNOWN
    # With the full bound the older useful job is found.
    assert _dept(O.view(DB, now=NOW), "product_truth")["last_useful_job"]["state"] == "FOUND"
    _wipe()
    _job("cir.compile", JobStatus.DONE, outputs={"work_done": 0}, finished=NOW - H)
    assert _dept(O.view(DB, now=NOW), "product_truth")["last_useful_job"]["state"] == "NONE"


def test_queue_depth_oldest_age_in_progress_and_next_scheduled():
    _wipe()
    _job("cir.compile", JobStatus.PENDING, created=NOW - 5 * H, run_after=NOW + H)
    _job("gate.certify", JobStatus.FAILED, created=NOW - 2 * H)          # awaiting retry
    _job("cir.draft", JobStatus.PENDING, created=NOW - 7 * H)
    _job("cir.compile", JobStatus.RUNNING, created=NOW - H)
    v = O.view(DB, now=NOW)
    q = v["queue_by_stage"]
    assert q["validation"]["waiting"] == 1 and q["independent_review"]["waiting"] == 1
    assert q["development"]["waiting"] == 1
    assert abs(q["development"]["oldest_age_s"] - 7 * 3600) < 120
    pt = _dept(v, "product_truth")
    assert pt["queue"]["waiting"] == 2 and pt["in_progress"] == 1
    assert abs(pt["queue"]["oldest_age_s"] - 5 * 3600) < 120
    assert pt["next_scheduled"]["pending_run_after"].startswith((NOW + H).isoformat()[:16])


def test_dead_letters_block_until_a_later_success_and_reasons_are_named():
    _wipe()
    dead = _job("cir.compile", JobStatus.DEAD, finished=NOW - 2 * H,
                error="KeyError: rows")
    v = O.view(DB, now=NOW)
    pt = _dept(v, "product_truth")
    assert pt["state"] == "BLOCKED" and pt["dead_letters"] == {"last_24h": 1, "open": 1}
    assert f"job {dead}" in pt["blocked"][0]["why"]
    assert v["dead_letters"]["open_defect"] == 1 and v["blocked_agents"]
    _job("cir.compile", JobStatus.DONE, outputs={"work_done": 1}, finished=NOW - H)
    v = O.view(DB, now=NOW)
    pt = _dept(v, "product_truth")
    assert pt["blocked"] == [] and pt["dead_letters"]["open"] == 0
    assert v["dead_letters"]["total"] == 1 and v["dead_letters"]["open"] == 0


def test_suspensions_block_with_reason_and_unreadable_suspensions_are_unknown():
    _wipe()
    _job("cir.compile", JobStatus.DONE, outputs={"work_done": 1}, finished=NOW - H)
    with patch.object(orchestrate, "suspended_job_types",
                      lambda db, now=None: {"cir.compile": {"kind": "suspended",
                                                            "why": "loop without progress",
                                                            "incident": "thrash:cir.compile"}}):
        v = O.view(DB, now=NOW)
    pt = _dept(v, "product_truth")
    assert pt["state"] == "BLOCKED" and "loop without progress" in pt["blocked"][0]["why"]

    def boom(db, now=None):
        raise RuntimeError("incidents unreadable")

    with patch.object(orchestrate, "suspended_job_types", boom):
        v = O.view(DB, now=NOW)
    pt = _dept(v, "product_truth")
    assert pt["blocked"] == O.UNKNOWN and pt["state"] == O.UNKNOWN
    assert v["suspensions_readable"] is False and v["state"] == O.UNKNOWN


def test_workers_healthy_and_unhealthy_from_heartbeats_and_unmeasured_is_unknown():
    _wipe()
    v = O.view(DB, now=NOW)
    assert v["workers"]["state"] == O.UNKNOWN and v["workers"]["healthy"] is None
    with DB.session() as s:
        s.add_all([
            slo.RuntimeSample(at=NOW - timedelta(minutes=2), kind="heartbeat",
                              component="worker", instance="a", ok=True),
            slo.RuntimeSample(at=NOW - 3 * H, kind="heartbeat", component="worker",
                              instance="b", ok=True),
            slo.RuntimeSample(at=NOW - timedelta(minutes=1), kind="heartbeat",
                              component="scheduler", instance="c", ok=False),
        ])
        s.commit()
    w = O.view(DB, now=NOW)["workers"]
    assert w["healthy"] == 1 and w["unhealthy"] == 2 and w["state"] == "DEGRADED"
    why = {i["instance"]: i["why"] for i in w["items"]}
    assert why["a"] is None and "no heartbeat" in why["b"] and "not ok" in why["c"]


def test_recoveries_and_products_completed_in_24h():
    _wipe()
    with DB.session() as s:
        s.add_all([
            AuditLog(actor="owner", action="recovery.restart_stuck_job", artifact="r",
                     at=NOW - H, detail={"result": "restarted"}),
            AuditLog(actor="queue", action="queue.lease_reclaimed", at=NOW - 2 * H),
            AuditLog(actor="owner", action="recovery.refused", artifact="q", at=NOW - H,
                     detail={"result": {"refused": "not stuck"}}),
            AuditLog(actor="queue", action="queue.lease_reclaimed", at=NOW - 3 * 24 * H),
            AuditLog(actor="x", action="listing.seo_drafted", artifact="a@1", at=NOW - H),
            AuditLog(actor="x", action="listing.seo_drafted", artifact="a@1", at=NOW - H),
            AuditLog(actor="x", action="listing.seo_drafted", artifact="b@1", at=NOW - H),
            AuditLog(actor="x", action="listing.seo_drafted", artifact="c@1",
                     at=NOW - 30 * H),
        ])
        s.commit()
    _job("gate.certify", JobStatus.DONE, outputs={"granted": True, "work_done": 1},
         finished=NOW - H)
    _job("gate.certify", JobStatus.DONE, outputs={"granted": False, "work_done": 1},
         finished=NOW - H)
    v = O.view(DB, now=NOW)
    r = v["recoveries"]
    assert r["last_24h"] == 2 and r["last_7d"] == 3 and r["refused_24h"] == 1
    assert "recovery.refused" not in {x["action"] for x in r["recent"]}
    assert v["last_24h"]["listing_packages_completed"] == 2
    assert v["last_24h"]["versions_certified"] == 1


def test_unreadable_jobs_are_unknown_never_zero():
    def boom(s, now):
        raise OSError("jobs unreadable")

    with patch.object(O, "_by_type", boom):
        v = O.view(DB, now=NOW)
    assert v["state"] == O.UNKNOWN and "jobs unreadable" in v["why"]
    assert v["departments"] is None and v["last_24h"] is None and v["dead_letters"] is None


def test_the_route_is_owner_only_and_read_only():
    _wipe()
    _job("cir.compile", JobStatus.DONE, outputs={"work_done": 1}, finished=NOW - H)
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert anon.get("/api/cc/operating-evidence").status_code in (401, 403)
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert c.post("/api/cc/auth/login", json={"passphrase": PASS}).status_code == 200
    writes = []

    def probe(conn, cursor, statement, params, context, executemany):
        head = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if head in ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "REPLACE") \
                and "cc_owner_sessions" not in statement:
            writes.append(statement[:120])

    event.listen(DB.engine, "before_cursor_execute", probe)
    try:
        r = c.get("/api/cc/operating-evidence")
    finally:
        event.remove(DB.engine, "before_cursor_execute", probe)
    assert r.status_code == 200, r.text
    data = r.json().get("data", r.json())
    assert data["tab"] == "OPERATING_EVIDENCE" and data["read_only"] is True
    assert not writes, f"the panel wrote: {writes}"
    assert c.post("/api/cc/operating-evidence").status_code in (404, 405)


if __name__ == "__main__":
    failed = passed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:600])
                import traceback

                traceback.print_exc()
    print(f"{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
