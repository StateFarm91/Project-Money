"""W4-SWARMQUEUES: RUN/GROW/IMPROVE pull order with WATCHING spans (F-656) and the pre-launch
scope rule (F-630).

Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_swarmqueues.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="w4_swarmqueues_")

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry, Job  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402

NOW = datetime.now(timezone.utc)
_n = [0]


def _db() -> Database:
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def test_every_banded_job_type_has_a_class_and_department_lookup():
    assert orc.PULL_ORDER == ("RUN", "GROW", "IMPROVE")
    assert set(orc.CLASS_BY_BAND_KIND) == {k for _p, k, _w in orc.BANDS}
    for jt in orc.JOB_BANDS:
        c = orc.work_class_for(jt)
        assert c["class"] in orc.PULL_ORDER and "department" in c, c
    assert orc.work_class_for("support.reply")["class"] == "RUN"
    assert orc.work_class_for("mjs.scan")["class"] == "GROW"
    assert orc.work_class_for("improve.retrospective")["class"] == "IMPROVE"


def test_pull_order_is_run_then_grow_then_improve_stably():
    real = (orc.STANDING_BACKLOG, dict(orc.BACKLOG_JOBS))
    orc.STANDING_BACKLOG = real[0] + (("customer_incident", "answer the oldest support case"),)
    orc.BACKLOG_JOBS["answer the oldest support case"] = ("support", "support.reply", False)
    try:
        ordered, plan = orc.backlog_order(_db())
    finally:
        orc.STANDING_BACKLOG = real[0]
        orc.BACKLOG_JOBS.clear()
        orc.BACKLOG_JOBS.update(real[1])
    classes = [p["class"] for p in plan["order"]]
    assert classes == sorted(classes, key=orc.PULL_ORDER.index), classes
    assert ordered[0][1] == "answer the oldest support case"
    grow = [p["description"] for p in plan["order"] if p["class"] == "GROW"]
    assert grow == ["check the named benchmark for changes",
                    "score an uncovered arena in the coverage gap queue"]


def test_pre_launch_work_serving_an_open_readiness_item_goes_first():
    db = _db()
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action="launch.assessed",
                       detail={"ours_to_do": ["final_master_closure"], "blocked_on_owner": [],
                               "blocked_on_integration": []}))
    ordered, plan = orc.backlog_order(db)
    assert plan["phase"] == "shadow" and plan["readiness"]["known"] is True
    improve = [p for p in plan["order"] if p["class"] == "IMPROVE"]
    assert improve[0]["description"] == "refresh the Build-2 coverage map from the registry"
    assert improve[0]["serves_open_readiness"] == ["final_master_closure"]
    later = {p["description"]: p["deprioritised_pre_launch"] for p in improve[1:]}
    assert later["mine recent failures for an improvement hypothesis"] is True
    assert len(ordered) == len(orc.STANDING_BACKLOG), "deprioritised, never dropped"


def test_unknown_readiness_reorders_nothing():
    plan = orc.backlog_order(_db())[1]
    assert plan["readiness"]["known"] is False
    assert not any(p["deprioritised_pre_launch"] for p in plan["order"])


def test_watching_is_recorded_as_a_zero_token_span():
    db = _db()
    real = orc.MAX_BACKLOG_PER_TICK
    orc.MAX_BACKLOG_PER_TICK = 0  # nothing may be fed: the company watches
    try:
        out = orc.feed_idle(db, JobQueue(db), now=NOW)
    finally:
        orc.MAX_BACKLOG_PER_TICK = real
    assert out["enqueued"] == [] and out["watching"]["state"] == "WATCHING", out
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(Job)) == 0
        assert s.scalar(select(func.count()).select_from(CostEntry)) == 0
    again = orc._watching(db, idle_and_unfed=True, why="still idle", now=NOW + timedelta(minutes=5))
    assert again["state"] == "WATCHING"  # one open span, not a second start
    JobQueue(db).enqueue("orchestrator", "ops.heartbeat", {}, idempotency_key="sq:1")
    busy = orc.feed_idle(db, JobQueue(db), now=NOW + timedelta(minutes=10))
    assert busy["idle"] is False and busy["watching"]["state"] == "ended"
    assert busy["watching"]["seconds"] == 600
    spans = orc.watching_spans(db)
    assert spans[0]["seconds"] == 600 and spans[0]["until"]
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == orc.WATCHING_STARTED)) == 1


def test_fed_items_carry_class_and_department():
    db = _db()
    out = orc.feed_idle(db, JobQueue(db), now=NOW)
    assert out["enqueued"], out
    assert all(e["class"] in orc.PULL_ORDER and "department" in e for e in out["enqueued"])
    assert "pull_plan" in out


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
