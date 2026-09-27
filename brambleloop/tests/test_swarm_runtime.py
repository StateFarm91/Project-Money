"""The swarm rules, run by the worker rather than called from a test.

A proof audit (2026-09-26) found #174, #175, #176, #186 and #187 claimed covered while nothing
in the runtime called the library: `fan_out()` returned a number nobody used, `orphans()` had
no caller, `next_work()` was only ever called with `[]`, and queued priority was 50 or 100 by
cadence period. Every test here enqueues a real `swarm.*` job and lets `Worker.run_once` run
it through the permission layer, so what is proven is the runtime path.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import DEFAULT_AGENTS, Registry, stewardship  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Agent, CostEntry, Improvement, Incident, Job, JobStatus, SwarmAllocation, utcnow,
)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker, handlers  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/swarm.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run(db, job_type: str, inputs: dict | None = None, *, key: str | None = None) -> dict:
    """Enqueue one steward job ahead of everything and let the worker run it."""
    job = JobQueue(db).enqueue("swarm_steward", job_type, inputs or {},
                               idempotency_key=key or f"test:{job_type}:{utcnow().timestamp()}",
                               priority=0)
    worker = Worker(db, "swarm-test")
    assert worker.run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, (row.status, row.last_error)
        return dict(row.outputs or {})


def _finished_job(db, agent, job_type, status, *, days_ago=1, error=""):
    with db.session() as s:
        s.add(Job(agent=agent, job_type=job_type, status=status, last_error=error or None,
                  finished_at=utcnow() - timedelta(days=days_ago)))


# ---- #187 ------------------------------------------------------------------


def test_every_runnable_job_type_has_a_band_decided_rather_than_defaulted():
    types = set(handlers.known()) | {t for a in DEFAULT_AGENTS for t in a["allowed_job_types"]}
    unmapped = sorted(t for t in types if not orc.band_for(t)["mapped"])
    assert not unmapped, f"{unmapped} would be enqueued at a band nobody decided"
    assert orc.priority_for("support.reply") < orc.priority_for("seasonal.sentinel") \
        < orc.priority_for("listing.seo") < orc.priority_for("mjs.scan") \
        < orc.priority_for("creative.expedition") < orc.priority_for("creative.blinded") \
        < orc.priority_for("ops.retention")
    assert orc.band_for("nobody.named.this") == {
        "job_type": "nobody.named.this", "kind": "housekeeping", "band": 95, "mapped": False}


def test_the_queue_claims_by_band_when_the_band_is_the_priority():
    """What the enqueue-site change buys: an hourly benchmark no longer outruns a reply."""
    db = _db()
    q = JobQueue(db)
    q.enqueue("creative_director", "creative.image_benchmark", {}, idempotency_key="a",
              priority=orc.priority_for("creative.image_benchmark"))
    q.enqueue("support", "support.reply", {"question": "x"}, idempotency_key="b",
              priority=orc.priority_for("support.reply"))
    assert q.claim("w").job_type == "support.reply"


# ---- #174 ------------------------------------------------------------------


def test_every_agent_has_a_quality_metric_and_a_retirement_condition():
    for spec in DEFAULT_AGENTS:
        rule = stewardship(spec["name"])
        assert rule["metric"] and rule["retire_when"] and rule["reads"], spec["name"]
        assert 0 < rule["retire_below"] < rule["floor"] <= 1


def test_the_review_handler_reads_job_outcomes_and_applies_the_condition():
    db = _db()
    for _ in range(3):
        _finished_job(db, "validator", "cir.compile", JobStatus.DONE)
    for _ in range(9):
        _finished_job(db, "validator", "cir.compile", JobStatus.DEAD, error="boom")
    # Outside the window: not part of the reading.
    for _ in range(20):
        _finished_job(db, "validator", "cir.compile", JobStatus.DONE, days_ago=60)

    out = _run(db, "swarm.review")
    validator = out["agents"]["validator"]
    assert validator["reading"] == "measured" and validator["sample"] == 12
    assert validator["value"] == 0.25
    assert validator["verdict"] == "retire_or_repair" and "validator" in out["retire"]

    # No jobs, no cadence, nothing queued: the idle half of the condition.
    assert out["agents"]["pricing"]["verdict"] == "retire"
    # Owner-gated capability: idle is the gate working, not the agent failing.
    assert out["agents"]["ads"]["verdict"] == "keep"
    assert "dormant by design" in out["agents"]["ads"]["why"]
    # A scheduled agent with no history is UNMEASURED, not scored.
    orch = out["agents"]["orchestrator"]
    assert orch["reading"] == "UNMEASURED" and orch["value"] is None
    assert out["enacted"] is False
    with db.session() as s:
        assert all(a.enabled for a in s.scalars(select(Agent))), "a review disabled an agent"


# ---- #175 ------------------------------------------------------------------


def test_the_allocation_is_recorded_per_lane_and_bounded_by_the_ceiling():
    db = _db()
    q = JobQueue(db)
    for n in range(3):
        q.enqueue("market_radar", "radar.score", {}, idempotency_key=f"s{n}",
                  priority=200, run_after=utcnow() + timedelta(hours=1))
    out = _run(db, "swarm.allocate")
    assert out["spend_increase_cad"] == 0.0
    with db.session() as s:
        row = s.scalar(select(SwarmAllocation))
        lane = row.lanes["market_radar"]
        assert lane["open_work"] == 3 and lane["active"] and 0 < lane["batch"] <= 3
        assert s.scalar(select(CostEntry)) is None, "allocation spent money"


def test_a_lane_whose_ceiling_is_spent_is_inactive_and_the_backlog_skips_it():
    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="market_radar", amount_cad=4.0, kind="llm"))
    out = _run(db, "swarm.backlog")
    assert out["idle"] is True
    fed = [e["job_type"] for e in out["enqueued"]]
    assert "mjs.scan" not in fed and "radar.score" not in fed
    assert any("inactive" in s["why"] for s in out["skipped"])
    # The spending item is never fed from idleness.
    assert any(s["description"].startswith("run a concept tournament")
               and "spends" in s["why"] for s in out["skipped"])
    assert fed == ["ops.continuity", "seasonal.sentinel"], fed


# ---- #186 ------------------------------------------------------------------


def test_an_idle_queue_takes_the_highest_value_standing_items_once():
    db = _db()
    out = _run(db, "swarm.backlog", key="b1")
    assert out["idle"] is True and out["batch"] == orc.MAX_BACKLOG_PER_TICK
    assert [e["job_type"] for e in out["enqueued"]] == ["mjs.scan", "radar.score"]
    with db.session() as s:
        queued = {j.job_type: j for j in s.scalars(select(Job).where(
            Job.status == JobStatus.PENDING))}
    assert queued["mjs.scan"].agent == "market_radar"
    assert queued["mjs.scan"].priority == orc.priority_for("mjs.scan")

    # The queue is no longer idle, so a second tick feeds nothing -- and says what is next.
    again = _run(db, "swarm.backlog", key="b2")
    assert again["idle"] is False and again["enqueued"] == []
    assert again["next"]["source"] == "queue"


def test_the_backlog_is_idempotent_within_a_window():
    db = _db()
    now = datetime(2026, 9, 27, 1, 0, tzinfo=timezone.utc)
    first = orc.feed_idle(db, JobQueue(db), now=now)
    with db.session() as s:  # drain what was fed without running it
        for j in s.scalars(select(Job)):
            j.status = JobStatus.CANCELLED
    second = orc.feed_idle(db, JobQueue(db), now=now + timedelta(minutes=5))
    fed_first = {e["job_type"] for e in first["enqueued"]}
    fed_second = {e["job_type"] for e in second["enqueued"]}
    assert fed_first == {"mjs.scan", "radar.score"}
    assert not fed_first & fed_second, "a standing item was fed twice in one window"
    assert {s["why"] for s in second["skipped"] if s["description"].startswith("check the")} \
        == {"already fed from the backlog this window"}


# ---- #176 ------------------------------------------------------------------


def test_orphaned_work_is_reassigned_or_surfaced_with_evidence():
    db = _db()
    q = JobQueue(db)
    later = utcnow() + timedelta(hours=2)
    # A GREEN job queued against an agent without the permission: reassigned.
    misrouted = q.enqueue("listing", "radar.scan", {}, idempotency_key="m", run_after=later)
    # A publish queued by support: never laundered to the store operator.
    forbidden = q.enqueue("support", "store.publish", {}, idempotency_key="f", run_after=later)
    with db.session() as s:
        s.add(Incident(severity="P1", signature="defect:x", summary="row 4 wrong"))
        s.add(Improvement(cell="no_such_cell", metric="m",
                          hypothesis="a hypothesis with no cell to own it", state="proposed"))
        s.add(Improvement(cell="quality", metric="defects_found_after_release",
                          hypothesis="an owned hypothesis", state="proposed"))

    out = _run(db, "swarm.orphans")
    # Three jobs: the two planted and the steward's own running job, which is owned.
    # #176 now also reads opportunities, benchmarks, listings, experiments, support cases,
    # owner actions and teardown findings; none exist here, and each is counted as zero.
    assert out["by_source"] == {"job": 3, "incident": 1, "improvement": 2, "opportunity": 0,
                                "benchmark": 0, "listing": 0, "experiment": 0,
                                "support_case": 0, "teardown_finding": 0, "owner_action": 0}
    assert {o["key"] for o in out["orphans"]} == {
        f"job:{misrouted.id}", f"job:{forbidden.id}", "incident:1", "improvement:1"}
    assert [r["to"] for r in out["reassigned"]] == ["market_radar"]
    assert out["incident_owners_assigned"][0]["to"] == "quality_director"

    with db.session() as s:
        assert s.get(Job, misrouted.id).agent == "market_radar"
        assert s.get(Job, forbidden.id).agent == "support"
        raised = {i.signature: i for i in s.scalars(select(Incident).where(
            Incident.signature.like("swarm.orphan:%")))}
        assert set(raised) == {f"swarm.orphan:job:{forbidden.id}",
                               "swarm.orphan:improvement:1"}
        evidence = raised[f"swarm.orphan:job:{forbidden.id}"].detail["evidence"]
        assert "forbidden" in evidence["problem"]
        assert s.get(Incident, 1).detail["owner"] == "quality_director"

    # Idempotent: a second pass raises nothing new and reassigns nothing.
    again = _run(db, "swarm.orphans", key="o2")
    assert again["reassigned"] == []
    with db.session() as s:
        assert len(list(s.scalars(select(Incident).where(
            Incident.signature.like("swarm.orphan:%"))))) == 2



def test_the_runtime_routes_report_what_the_handlers_decided():
    """GET only: the page reports the handlers' decisions and never makes one."""
    import os

    os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/app.sqlite"
    os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")
    from fastapi.testclient import TestClient

    from brambleloop.app import main

    with TestClient(main.app) as c:
        swarm = c.get("/api/swarm/runtime").json()
        experiments = c.get("/api/experiments").json()
    assert "orchestrator" in swarm["agent_quality"]["agents"]
    assert swarm["agent_quality"]["enacted"] is False
    assert "allocation" in swarm and isinstance(swarm["orphans"], list)
    assert experiments["count"] == len(experiments["experiments"])

if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
