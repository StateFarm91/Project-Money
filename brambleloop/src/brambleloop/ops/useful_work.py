"""F-719 / F-720: 24/7 useful-work readings, and the ready-work age alarm that says *why*.

**F-719 readings** (`readings`), each from rows, UNMEASURED rather than zero when the rows
needed do not exist:
  * ready-work age by value band (`swarm.orchestrate.band_for`): the oldest due pending job
    per band, so a stale proven-winner job is not hidden behind a fresh housekeeping one;
  * owner-blocked hours: open owner actions, summed age;
  * WATCHING time: department spans recorded by the orchestrator (F-656);
  * autonomous completion rate (24 h): jobs completed / (completed + dead-lettered);
  * untouched opportunities: open `benchmark_listings` gaps is not a table this runtime has,
    so it is reported UNMEASURED with that reason rather than invented.

**F-720 alarm** (`alarm`): when the oldest ready job is older than the health threshold
*and* the worker is otherwise idle (nothing running), each of the oldest ready jobs is
diagnosed -- unknown/disabled/unpermitted agent, no handler, suspended job type, department
blocked, lane inactive -- and one incident per cause is opened (`ready-work-age:<cause>`),
naming examples. Resolved when no ready work is over the threshold.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

SIGNATURE = "ready-work-age:"
DIAGNOSE_TOP = 20


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)


def _ready(s, now):
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    return list(s.execute(select(Job.id, Job.agent, Job.job_type, Job.run_after, Job.created_at)
                          .where(Job.status == JobStatus.PENDING, Job.run_after <= now)
                          .order_by(Job.run_after)).all())


def readings(db, *, now: datetime | None = None) -> dict:
    from sqlalchemy import func, select

    from ..core.models import Job, JobStatus, OwnerAction
    from ..swarm.orchestrate import band_for

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        ready = _ready(s, now)
        owner = [(_aware(a.at)) for a in s.scalars(select(OwnerAction).where(
            OwnerAction.done == False))]  # noqa: E712
        since = now - timedelta(hours=24)
        done = s.scalar(select(func.count()).select_from(Job).where(
            Job.status == JobStatus.DONE, Job.finished_at >= since)) or 0
        dead = s.scalar(select(func.count()).select_from(Job).where(
            Job.status == JobStatus.DEAD, Job.finished_at >= since)) or 0
    by_band: dict[str, dict] = {}
    for jid, _agent, jt, run_after, _c in ready:
        b = band_for(jt)
        key = f"{b['band']}:{b['kind']}"
        age = (now - _aware(run_after)).total_seconds()
        cur = by_band.get(key)
        if cur is None or age > cur["oldest_s"]:
            by_band[key] = {"oldest_s": round(age), "job_id": jid, "job_type": jt,
                            "count": (cur or {}).get("count", 0) + 1}
        else:
            cur["count"] += 1
    try:
        from ..autonomy import memory

        spans = [m for m in memory.recall(db, kind="department.watching")]
    except Exception:  # noqa: BLE001
        spans = []
    watching = {}
    for m in spans:
        b = m.get("body") or {}
        try:
            start = datetime.fromisoformat(b["since"])
            end = datetime.fromisoformat(b.get("ended") or b.get("last_seen") or b["since"])
        except (KeyError, ValueError):
            continue
        watching[m.get("department") or "?"] = {
            "state": m.get("state"), "hours": round((end - start).total_seconds() / 3600, 2)}
    finished = done + dead
    return {
        "as_of": now.isoformat(),
        "ready_age_by_band": dict(sorted(by_band.items())) if ready else {},
        "oldest_ready_s": (round((now - _aware(ready[0][3])).total_seconds())
                           if ready else None),
        "owner_blocked": {"open_actions": len(owner),
                          "hours": round(sum((now - a).total_seconds() for a in owner
                                             if a) / 3600, 1)},
        "watching": watching if spans else "UNMEASURED",
        "autonomous_completion_rate_24h": (round(done / finished, 4) if finished
                                           else "UNMEASURED"),
        "untouched_opportunities": {"state": "UNMEASURED",
                                    "why": "no coverage-gap table is recorded at runtime"},
    }


def diagnose(db, agent_name: str, job_type: str, *, now: datetime | None = None) -> str:
    """The first reason a ready job is not being claimed, or "unexplained"."""
    from ..agents.registry import Registry
    from ..runtime.worker import handlers
    from ..swarm import orchestrate as orc

    agents = {a.name: a for a in Registry(db).all()}
    if agents.get(agent_name) is None:
        return "unknown_agent"
    if handlers.get(job_type) is None:
        return "no_handler"
    problem = orc._owner_problem(agents.get(agent_name), job_type)
    if problem:
        return "agent_disabled" if "disabled" in problem else "agent_not_permitted"
    try:
        if job_type in orc.suspended_job_types(db, now=now):
            return "job_type_suspended"
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..autonomy import memory
        from ..ops.slo import department_of

        dept = department_of(job_type)
        if dept and memory.active_block(db, dept, now=now):
            return "department_blocked"
    except Exception:  # noqa: BLE001
        pass
    alloc = orc.latest_allocation(db, now=now) or {}
    lane = (alloc.get("lanes") or {}).get(agent_name)
    if lane is not None and not lane.get("active"):
        return "lane_inactive"
    return "unexplained"


def alarm(db, session, *, now: datetime | None = None) -> dict:
    from sqlalchemy import func, select

    from ..core.models import Job, JobStatus
    from . import incident_lifecycle as lifecycle
    from .health import QUEUE_STALLED_AFTER_S

    now = now or datetime.now(timezone.utc)
    ready = _ready(session, now)
    stale = [r for r in ready
             if (now - _aware(r[3])).total_seconds() > QUEUE_STALLED_AFTER_S]
    running = session.scalar(select(func.count()).select_from(Job).where(
        Job.status == JobStatus.RUNNING)) or 0
    causes: dict[str, list] = {}
    if stale and not running:
        for jid, agent, jt, run_after, _c in stale[:DIAGNOSE_TOP]:
            cause = diagnose(db, agent, jt, now=now)
            causes.setdefault(cause, []).append(
                {"job_id": jid, "agent": agent, "job_type": jt,
                 "age_s": round((now - _aware(run_after)).total_seconds())})
    for cause, jobs in causes.items():
        lifecycle.open_or_restate(
            session, signature=f"{SIGNATURE}{cause}", severity="P2",
            summary=(f"{len(jobs)} ready job(s) waited over {QUEUE_STALLED_AFTER_S}s with the "
                     f"worker idle: {cause}"),
            detail={"cause": cause, "examples": jobs[:5]}, now=now)
    life = lifecycle.reconcile(session, SIGNATURE,
                               lambda inc: inc.signature[len(SIGNATURE):] in causes,
                               resolution="no ready work is over the age threshold with the "
                                          "worker idle", now=now)
    return {"stale_ready": len(stale), "running": running,
            "causes": {k: len(v) for k, v in causes.items()}, "resolved": life["resolved"]}
