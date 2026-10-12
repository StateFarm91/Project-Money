"""Swarm measurements: starved READY work, untouched opportunities, parallelism, agents.

Final Master F-655 (24/7 Valuable Work), F-730 (No Downtime Means No Lost Opportunity),
F-489 (Parallelism Efficiency) and F-487 (Department Health). Each is a reading over durable
rows (plus the runner's own process counters where the row says so), with UNKNOWN where the
input does not exist -- never a zero standing in for "not measured".

* ``starved_ready`` -- runnable PENDING jobs older than their band's READY SLA **while the
  pool has idle capacity** (running < the allocation's worker target). Work waiting because
  every worker is busy is queueing; work waiting while a worker is idle is the defect.
* ``untouched_opportunities`` -- coverage gaps still UNCOVERED after ``UNTOUCHED_AFTER``,
  value-weighted by their score. Opportunity discovery is cadence-based; this measures
  whether discovered opportunity is acted on.
* ``parallelism`` -- busy vs idle seconds of the pool (runner STATE), duplicate work avoided
  (queue idempotency refusals, `queue.durable.DEDUPE_HITS`) and claim concurrency.
* ``agents_view`` -- one row per agent: running job, pending and deferred counts, parked job
  types (suspended by the thrash breaker), last completion, month spend, idle flag.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# How long a runnable job of each band may wait before it is starved, in seconds. Ordered like
# the bands: a customer incident waits minutes, housekeeping waits days. Named so the reading
# says which promise was broken rather than "the queue is old".
BAND_READY_SLA_S: dict[str, int] = {
    "customer_incident": 15 * 60,
    "truth_defect": 30 * 60,
    "seasonal_deadline": 2 * 3600,
    "proven_winner": 6 * 3600,
    "benchmark_change": 12 * 3600,
    "new_opportunity": 24 * 3600,
    "exploration": 48 * 3600,
    "housekeeping": 72 * 3600,
}
UNTOUCHED_AFTER = timedelta(days=7)


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def starved_ready(db, *, worker_target: int | None, now: datetime | None = None) -> dict:
    """F-655: READY work past its band SLA while capacity sat idle."""
    from sqlalchemy import func, select

    from ..core.models import Job, JobStatus
    from .orchestrate import band_for

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        running = int(s.scalar(select(func.count()).select_from(Job).where(
            Job.status == JobStatus.RUNNING)) or 0)
        pending = list(s.execute(select(Job.id, Job.job_type, Job.created_at, Job.run_after)
                                 .where(Job.status == JobStatus.PENDING)).all())
    late, by_band = [], {}
    for jid, jt, created, run_after in pending:
        ready_at = max(_aware(created), _aware(run_after) or _aware(created))
        if ready_at > now:
            continue  # deferred, not ready
        kind = band_for(jt)["kind"]
        sla = BAND_READY_SLA_S.get(kind)
        waited = (now - ready_at).total_seconds()
        if sla is not None and waited > sla:
            late.append({"job": f"jobs:{jid}", "job_type": jt, "band": kind,
                         "waited_s": round(waited), "sla_s": sla})
            by_band[kind] = by_band.get(kind, 0) + 1
    if worker_target is None:
        idle = None
    else:
        idle = running < int(worker_target)
    starved = len(late) if idle else 0
    return {
        "reading": ("UNKNOWN" if idle is None and late else
                    "starved" if idle and late else
                    "queueing" if late else "ok"),
        "starved": starved if idle is not None else None,
        "late_ready": len(late),
        "late_by_band": by_band,
        "capacity_idle": idle, "running": running, "worker_target": worker_target,
        "oldest": sorted(late, key=lambda r: -r["waited_s"])[:5],
        "sla_s": BAND_READY_SLA_S,
        "why": ("worker target unknown, so whether late work waited behind idle capacity "
                "cannot be said" if idle is None and late else
                "late READY work while the pool had idle capacity: valuable work untouched "
                "for no reason" if idle and late else
                "late work is queueing behind a full pool" if late else
                "no READY work is past its band SLA"),
    }


def untouched_opportunities(db, *, now: datetime | None = None) -> dict:
    """F-730 / F-719: discovered opportunity still uncovered after UNTOUCHED_AFTER."""
    from sqlalchemy import select

    from ..core.models import CoverageGap
    from ..intel import coverage

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        rows = list(s.scalars(select(CoverageGap)))
    if not rows:
        return {"reading": "UNKNOWN", "untouched": None, "value_weighted": None,
                "why": "no coverage gap has been discovered, so nothing can be untouched yet"}
    stale = [r for r in rows if r.state == coverage.UNCOVERED
             and now - _aware(r.updated_at or r.created_at) > UNTOUCHED_AFTER]
    top = sorted(stale, key=lambda r: -(r.score or 0.0))[:5]
    return {"reading": "untouched" if stale else "ok", "untouched": len(stale),
            "of_gaps": len(rows),
            "value_weighted": round(sum(float(r.score or 0.0) for r in stale), 4),
            "after_days": UNTOUCHED_AFTER.days,
            "top": [{"arena": r.arena, "pod": r.pod, "score": r.score,
                     "uncovered_since": _aware(r.created_at).isoformat()} for r in top],
            "why": (f"{len(stale)} discovered gap(s) left uncovered over "
                    f"{UNTOUCHED_AFTER.days} days" if stale else
                    "every discovered gap was acted on within the window")}


def parallelism(runner_state: dict | None) -> dict:
    """F-489: utilisation of the pool and duplicate work avoided (process-local counters)."""
    from ..queue import durable

    rs = runner_state or {}
    busy, idle = rs.get("busy_seconds"), rs.get("idle_seconds")
    measured = isinstance(busy, (int, float)) and isinstance(idle, (int, float)) \
        and (busy + idle) > 0
    lanes = {k: {"busy_seconds": v.get("busy_seconds"), "idle_seconds": v.get("idle_seconds")}
             for k, v in (rs.get("lanes") or {}).items()}
    return {
        "busy_seconds": busy if measured else None,
        "idle_seconds": idle if measured else None,
        "utilisation": round(busy / (busy + idle), 4) if measured else None,
        "lanes": lanes,
        "worker_pool": rs.get("worker_pool"), "worker_target": rs.get("worker_target"),
        "dedupe_hits": dict(durable.DEDUPE_HITS),
        "dedupe_hits_total": sum(durable.DEDUPE_HITS.values()),
        "dedupe_since": durable.DEDUPE_SINCE.isoformat(),
        "basis": ("process-local counters since this process started (runner STATE, queue "
                  "idempotency refusals); a restart resets them" if measured else
                  "UNKNOWN: this process has no pool counters (not the worker process, or "
                  "nothing has run yet)"),
        "merge_delay": "dev-lane merge delay is measured by ops/registry.py "
                       "(`merge_delay`), outside the deployed tree",
    }


def agents_view(db, *, now: datetime | None = None) -> dict:
    """F-487: per agent -- running job, pending, parked job types, last completion, spend."""
    from sqlalchemy import func, select

    from ..core.models import Agent, Job, JobStatus
    from ..finance import spend_report
    from .orchestrate import suspended_job_types

    now = now or datetime.now(timezone.utc)
    try:
        parked = suspended_job_types(db, now=now)
    except Exception as exc:  # noqa: BLE001
        parked, parked_err = {}, f"unreadable: {type(exc).__name__}"
    else:
        parked_err = None
    try:
        spend = spend_report.what_it_bought(db, now=now).get("by_agent") or {}
        spend_err = None
    except Exception as exc:  # noqa: BLE001
        spend, spend_err = None, f"unreadable: {type(exc).__name__}"
    with db.session() as s:
        agents = [(a.name, a.enabled, list(a.allowed_job_types or []))
                  for a in s.scalars(select(Agent).order_by(Agent.name))]
        running = {}
        for jid, agent, jt, started in s.execute(
                select(Job.id, Job.agent, Job.job_type, Job.started_at)
                .where(Job.status == JobStatus.RUNNING)).all():
            running.setdefault(agent, {"job": f"jobs:{jid}", "job_type": jt,
                                       "started_at": _aware(started).isoformat()
                                       if started else None})
        pend = {}
        for agent, run_after in s.execute(select(Job.agent, Job.run_after).where(
                Job.status == JobStatus.PENDING)).all():
            p = pend.setdefault(agent, {"ready": 0, "deferred": 0})
            p["deferred" if run_after and _aware(run_after) > now else "ready"] += 1
        last = dict(s.execute(select(Job.agent, func.max(Job.finished_at)).where(
            Job.status == JobStatus.DONE).group_by(Job.agent)).all())
    rows = []
    for name, enabled, types in agents:
        p = pend.get(name, {"ready": 0, "deferred": 0})
        lf = _aware(last.get(name))
        rows.append({
            "agent": name, "enabled": bool(enabled),
            "running_job": running.get(name),
            "pending_ready": p["ready"], "pending_deferred": p["deferred"],
            "parked_job_types": {t: parked[t]["why"] for t in types if t in parked},
            "last_completion": lf.isoformat() if lf else None,
            "month_spend_cad": (None if spend is None else
                                round(float((spend.get(name) or {}).get("cad") or 0.0), 6)),
            "idle": bool(enabled) and name not in running and p["ready"] == 0,
        })
    return {"as_of": now.isoformat(), "agents": rows,
            "spend_basis": spend_err or "finance.spend_report.what_it_bought (this month, "
                                        "recorded rows; an agent with no row spent nothing "
                                        "recorded)",
            "parked_basis": parked_err or "swarm.orchestrate.suspended_job_types"}
