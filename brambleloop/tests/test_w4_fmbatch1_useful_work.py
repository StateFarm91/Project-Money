"""F-719 / F-720 / F-729: useful-work readings, the diagnosed ready-work alarm, the CC block,
and the company-departments route (F-601)."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import _opread  # INTEG7 (R-1): owner-only reads present the operator credential
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1uw_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/m.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")
os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy import memory  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident, Job, JobStatus, OwnerAction  # noqa: E402
from brambleloop.ops import useful_work as U  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401  (registers handlers)

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def boot():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='fmb1uw-')}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _job(db, agent, jt, age_h, status=JobStatus.PENDING, finished=None):
    with db.session() as s:
        s.add(Job(agent=agent, job_type=jt, status=status, inputs={},
                  run_after=NOW - timedelta(hours=age_h), created_at=NOW - timedelta(hours=age_h),
                  finished_at=finished))


def test_empty_readings_are_unmeasured_not_zero():
    r = U.readings(boot(), now=NOW)
    assert r["oldest_ready_s"] is None and r["ready_age_by_band"] == {}
    assert r["autonomous_completion_rate_24h"] == "UNMEASURED"
    assert r["watching"] == "UNMEASURED"
    assert r["untouched_opportunities"]["state"] == "UNMEASURED"


def test_readings_from_rows():
    db = boot()
    _job(db, "market_radar", "radar.score", 3)
    _job(db, "orchestrator", "ops.slo", 1)
    _job(db, "orchestrator", "ops.slo", 2, status=JobStatus.DONE, finished=NOW - timedelta(hours=1))
    _job(db, "orchestrator", "ops.slo", 2, status=JobStatus.DEAD, finished=NOW - timedelta(hours=1))
    with db.session() as s:
        s.add(OwnerAction(requirement_key="x", action="do", reason="r",
                          at=NOW - timedelta(hours=10)))
    memory.remember(db, "department.watching:support", kind="department.watching",
                    department="support", state="watching",
                    body={"since": (NOW - timedelta(hours=4)).isoformat(),
                          "last_seen": NOW.isoformat()}, now=NOW)
    r = U.readings(db, now=NOW)
    assert r["oldest_ready_s"] == 3 * 3600 and len(r["ready_age_by_band"]) >= 1
    assert r["autonomous_completion_rate_24h"] == 0.5
    assert r["owner_blocked"]["open_actions"] == 1 and r["owner_blocked"]["hours"] == 10.0
    assert r["watching"]["support"]["hours"] == 4.0


def test_alarm_names_the_cause_and_resolves():
    db = boot()
    _job(db, "market_radar", "creative.tournament", 3)     # radar may not run it
    _job(db, "nobody_agent", "ops.slo", 3)
    _job(db, "orchestrator", "zz.no_such_handler", 3)
    with db.session() as s:
        out = U.alarm(db, s, now=NOW)
    assert out["causes"] == {"agent_not_permitted": 1, "unknown_agent": 1, "no_handler": 1}
    with db.session() as s:
        sigs = sorted(i.signature for i in s.query(Incident).filter(Incident.resolved == False))  # noqa: E712
    assert sigs == ["ready-work-age:agent_not_permitted", "ready-work-age:no_handler",
                    "ready-work-age:unknown_agent"]
    with db.session() as s:
        for j in s.query(Job).all():
            j.status = JobStatus.CANCELLED
    with db.session() as s:
        again = U.alarm(db, s, now=NOW)
    assert again["stale_ready"] == 0 and len(again["resolved"]) == 3


def test_alarm_is_quiet_while_the_worker_is_busy():
    db = boot()
    _job(db, "nobody_agent", "ops.slo", 3)
    _job(db, "orchestrator", "ops.slo", 0, status=JobStatus.RUNNING)
    with db.session() as s:
        assert U.alarm(db, s, now=NOW)["causes"] == {}


def test_routes_and_cc_block():
    from fastapi.testclient import TestClient

    from brambleloop.app import main
    from brambleloop.app.command_center import executive

    main.db.create_all()
    Registry(main.db).seed_defaults()
    c = TestClient(main.app)
    assert c.get("/api/useful-work").status_code in (401, 503)      # anonymous: refused
    assert c.get("/api/company/departments").status_code in (401, 503)
    assert set(_opread.get(c, "/api/useful-work").json()) >= {"ready_age_by_band",
                                                              "owner_blocked"}
    deps = _opread.get(c, "/api/company/departments").json()
    assert deps["total"] == 12
    assert _opread.get(c, "/api/departments").status_code == 200   # F-487 route untouched
    metrics = {m["metric"] for m in executive._autonomy_extra(main.db, NOW)}
    assert {"oldest_ready_work_s", "owner_blocked_hours", "watching_departments",
            "autonomous_completion_rate_24h"} <= metrics


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
