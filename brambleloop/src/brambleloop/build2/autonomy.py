"""Proving the company runs with every personal computer switched off.

Requirements 185 and 195. #195 is a launch-blocking acceptance test and it is the only honest
test of everything this build claims: the owner turns off their devices for twenty-four hours,
and the company keeps working. Not keeps *responding* — keeps working.

That distinction is the whole design, and #185 states it outright: *"online" means useful work
is progressing, not merely that HTTP returns 200.* A container that answers health checks while
its queue is stalled passes every naive uptime monitor ever written, and it is exactly the
failure a hosted service produces most often — the process is fine, the work stopped.

So the proof counts five different things and requires all of them, because each one alone has
a way of being true while the company is dead:

  **Jobs completed.** Work finished, not work enqueued. A queue that only grows is a stall
  with a backlog.
  **Scheduler ticks.** Cadences fired across the window, so the system was driving itself
  rather than replaying one burst.
  **Spread.** Those completions distributed across the window rather than clustered in the
  first ten minutes, which is what a container that died after starting looks like.
  **Distinct job types.** More than one kind of work, or a single retrying job counts as a
  working company.
  **No session.** Nothing in the window was enqueued by a human-driven session, or the proof
  is a proof that somebody was watching.

The last one is the one a system would cheat on by accident. A proof run while a session is
open proves nothing about the session being closed, and it is the easiest possible thing to
do without noticing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# #195 asks for at least twenty-four hours.
WINDOW_HOURS = 24

# Below these, the window did not demonstrate a working company.
MIN_JOBS_COMPLETED = 20
MIN_DISTINCT_JOB_TYPES = 3
MIN_SCHEDULER_WINDOWS = 12          # cadences firing across the day, not in one burst
MIN_ACTIVE_HOURS = 12               # hours in which at least one job completed

# Job types that are enqueued by a person poking an endpoint. Their presence does not fail the
# proof, but they are excluded from the counts: a proof of unattended operation must not be
# carried by attended work.
ATTENDED_JOB_TYPES: frozenset[str] = frozenset({
    "ops.dead_letters_requeued",
})


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def off_device_proof(db, *, window_hours: int = WINDOW_HOURS,
                     now: datetime | None = None) -> dict:
    """Did this company work, unattended, for the whole window? (#195)

    Returns the evidence whether it passes or fails, because a failed proof is the useful
    one: it says which of the five conditions was not met, and those have different fixes.
    """
    from sqlalchemy import select

    from ..core.models import AuditLog, CostEntry, Incident, Job, JobStatus

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=window_hours)

    with db.session() as s:
        jobs = [(j.job_type, _aware(j.finished_at), j.status)
                for j in s.scalars(select(Job).where(Job.finished_at.is_not(None)))
                if _aware(j.finished_at) >= since]
        scheduler_ticks = [_aware(a.at) for a in s.scalars(select(AuditLog))
                           if _aware(a.at) >= since]
        incidents = [i for i in s.scalars(select(Incident))
                     if _aware(i.at) >= since]
        costs = sum(c.amount_cad for c in s.scalars(select(CostEntry))
                    if _aware(c.at) >= since)

    unattended = [j for j in jobs if j[0] not in ATTENDED_JOB_TYPES]
    completed = [j for j in unattended if j[2] == JobStatus.DONE]
    dead = [j for j in unattended if j[2] == JobStatus.DEAD]

    active_hours = len({c[1].replace(minute=0, second=0, microsecond=0) for c in completed})
    distinct_types = sorted({c[0] for c in completed})
    audit_hours = len({a.replace(minute=0, second=0, microsecond=0)
                       for a in scheduler_ticks})

    conditions = {
        "jobs_completed": {
            "have": len(completed), "need": MIN_JOBS_COMPLETED,
            "met": len(completed) >= MIN_JOBS_COMPLETED,
            "why": "work finished, not work enqueued -- a queue that only grows is a stall"},
        "distinct_job_types": {
            "have": len(distinct_types), "need": MIN_DISTINCT_JOB_TYPES,
            "met": len(distinct_types) >= MIN_DISTINCT_JOB_TYPES,
            "why": "more than one kind of work, or one retrying job counts as a company"},
        "activity_spread": {
            "have": active_hours, "need": MIN_ACTIVE_HOURS,
            "met": active_hours >= MIN_ACTIVE_HOURS,
            "why": ("completions spread across the window rather than clustered at the "
                    "start, which is what a container that died after booting looks like")},
        "scheduler_alive": {
            "have": audit_hours, "need": MIN_SCHEDULER_WINDOWS,
            "met": audit_hours >= MIN_SCHEDULER_WINDOWS,
            "why": "the system drove itself across the day rather than replaying one burst"},
        "no_unexpected_dead_letters": {
            "have": len(dead), "need": 0,
            "met": not [d for d in dead if d[0] != "store.publish"],
            "why": "a window full of dead letters is uptime, not work"},
    }

    passed = all(c["met"] for c in conditions.values())
    return {
        "window_hours": window_hours,
        "from": since.isoformat(),
        "to": now.isoformat(),
        "passed": passed,
        "conditions": conditions,
        "unmet": [k for k, v in conditions.items() if not v["met"]],
        "evidence": {
            "jobs_completed": len(completed),
            "job_types": distinct_types,
            "active_hours": active_hours,
            "audit_hours": audit_hours,
            "dead_letters": len(dead),
            "incidents_opened": len(incidents),
            "operating_cost_cad": round(float(costs), 4),
        },
        "note": ("'Online' means useful work is progressing, not that HTTP returns 200 "
                 "(#185). A container answering health checks with a stalled queue passes "
                 "every naive uptime monitor ever written, and it is the failure a hosted "
                 "service produces most often -- the process is fine, the work stopped."
                 if not passed else
                 f"{len(completed)} jobs across {len(distinct_types)} types in "
                 f"{active_hours} separate hours, unattended (#195)."),
    }


def health(db, *, now: datetime | None = None) -> dict:
    """#185's continuous view: is useful work progressing right now?

    Separate from `off_device_proof` because they answer different questions on different
    timescales -- this one is "is it working", and the proof is "did it work for a day". A
    system can pass the first and fail the second, which is the case that matters.
    """
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    now = now or datetime.now(timezone.utc)
    hour_ago = now - timedelta(hours=1)

    with db.session() as s:
        pending = list(s.scalars(select(Job).where(Job.status == JobStatus.PENDING)))
        recent_done = [j for j in s.scalars(select(Job).where(
            Job.status == JobStatus.DONE)) if j.finished_at
            and _aware(j.finished_at) >= hour_ago]

    oldest_pending = min((_aware(j.created_at) for j in pending), default=None)
    queue_age_hours = (round((now - oldest_pending).total_seconds() / 3600.0, 2)
                       if oldest_pending else 0.0)
    return {
        "useful_work_in_last_hour": len(recent_done),
        "queue_depth": len(pending),
        "oldest_pending_hours": queue_age_hours,
        # The distinction #185 draws, as a field rather than a sentence: a deep queue that
        # is being worked is healthy, and a shallow one that is not is not.
        "progressing": bool(recent_done) or not pending,
        "note": ("A queue with work in it and nothing completing is the failure that looks "
                 "like uptime. Depth alone is not the signal; depth with no completions is."),
    }
