"""v1.1 lane A: a simulated unattended night (F-880, F-881, F-894, F-895, F-896; §95).

What is simulated, and what is not. The orchestrator's clock is advanced in fifteen-minute
steps across eight hours (`inputs.now`); everything else is real: the jobs go through the real
durable queue, the real worker, the real permission layer and the real handlers, against a
file-backed SQLite database. No owner PC, no development session, no human enqueues anything
after the first tick. This is a SIMULATION of a night's cadence, not a soak: it proves the
loop generates, executes, measures and records useful work by itself; it does not prove eight
wall-clock hours of uptime (the directive forbids faking that).

One department (Store/Commerce) is blocked on an owner action for the whole night (§95): it
must receive nothing while the others keep working.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy import charters, memory, status  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry, Job, JobStatus  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402

TICKS = 32                      # eight hours at fifteen minutes


def night(db, start: datetime, *, block: str | None = "store_commerce") -> dict:
    if block:
        memory.block_department(db, block, reason="awaiting owner approval of Etsy "
                                "publication policy", owner_action="OA-NIGHT", now=start)
    q = JobQueue(db)
    w = Worker(db, "night-worker")
    per_tick = []
    for i in range(TICKS):
        t = start + timedelta(minutes=15 * i)
        q.enqueue("coo", "autonomy.orchestrate", {"now": t.isoformat()},
                  idempotency_key=f"night:orch:{i}")
        for _ in range(200):
            if not w.run_once():
                break
        with db.session() as s:
            orch = s.scalar(select(Job).where(Job.idempotency_key == f"night:orch:{i}"))
            per_tick.append({"t": t.isoformat(),
                             "status": getattr(orch.status, "value", ""),
                             "enqueued": (orch.outputs or {}).get("enqueued"),
                             "states": (orch.outputs or {}).get("states", {})})
    return {"ticks": per_tick, "worker": w.stats}


def test_an_unattended_night_produces_useful_work_across_departments():
    tmp = tempfile.mkdtemp(prefix="v11a-night-")
    db = Database(f"sqlite:///{tmp}/night.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    start = datetime.now(timezone.utc).replace(hour=3, minute=0, second=0, microsecond=0)
    run = night(db, start)
    ticks = run["ticks"]
    assert len(ticks) == TICKS
    assert all(t["status"] == "done" for t in ticks), [t["status"] for t in ticks]
    assert run["worker"].failed == 0 and run["worker"].denied == 0, run["worker"]

    missions = memory.recall(db, kind="mission", limit=1000)
    assert missions, "the night produced no missions"
    useful_by_dept: dict[str, int] = {}
    for m in missions:
        if m["state"] == "useful":
            useful_by_dept[m["department"]] = useful_by_dept.get(m["department"], 0) + 1
    # Every department with a real generator, except the blocked one, did useful work.
    assert "store_commerce" not in useful_by_dept, useful_by_dept
    assert len(useful_by_dept) >= 10, useful_by_dept
    assert sum(useful_by_dept.values()) >= 30, useful_by_dept

    # The blocked department stayed blocked and received nothing; nobody else waited on it.
    assert all(t["states"].get("store_commerce") == "BLOCKED" for t in ticks)
    with db.session() as s:
        gen = [j for j in s.scalars(select(Job)) if (j.inputs or {}).get("source") == "autonomy"]
        assert gen
        assert not [j for j in gen if (j.inputs or {}).get("department") == "store_commerce"]
        # No protected action, no spend.
        assert not [j for j in s.scalars(select(Job)) if j.job_type in
                    charters.PROTECTED_JOB_TYPES]
        assert (s.scalar(select(func.count()).select_from(CostEntry)) or 0) == 0
        dead = s.scalar(select(func.count()).select_from(Job).where(
            Job.status == JobStatus.DEAD)) or 0
    assert dead == 0, dead

    # Measured: every generated mission's outcome was recorded (bar the final tick's).
    open_missions = [m for m in missions if m["state"] == "queued"]
    assert len(open_missions) <= 11, len(open_missions)
    # Learned: department reviews persisted KPI snapshots.
    snaps = memory.recall(db, kind="kpi_snapshot", limit=500)
    assert len({s["department"] for s in snaps}) >= 5, sorted({s["department"] for s in snaps})
    # Morning handoff (F-896): a brief exists and reports the night honestly.
    briefs = memory.recall(db, kind="morning_brief", limit=10)
    assert briefs, "no morning brief"
    latest = briefs[0]["body"]
    assert latest["completed_total"] > 0
    assert latest["spend"]["basis"] == "unknown"        # no cost rows: never "CA$0.00"
    assert any(b["department"] == "store_commerce" for b in latest["blocked_departments"])
    # Timeline (F-927) recorded the night.
    tl = status.timeline(db, limit=200)
    kinds = {e["kind"] for e in tl["items"]}
    assert {"mission.created", "mission.useful", "kpi.measured"} <= kinds, kinds
    blocked = memory.events(db, department="store_commerce", limit=50)
    assert [e for e in blocked if e["kind"] == "department.blocked"], blocked
    # No tick left the company idle: every tick either generated work or every department
    # was busy, blocked or had already done all the work its evidence supports.
    for t in ticks:
        assert t["states"], t
        assert set(t["states"].values()) <= {"GENERATED", "BUSY", "BLOCKED", "SATURATED"}, t


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
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
