"""Product-runtime job observation: duration envelopes, non-destructive diagnosis, and the
five activity states (wave-3 K7).

F-337  Rolling normal duration per job_type from completed jobs. A running job past
       `INVESTIGATE_MULTIPLE` x its rolling median (only where at least `MIN_HISTORY` samples
       exist) is flagged for investigation -- and investigation means reading the job's
       authoritative state first (`diagnose`), never restarting it.
F-338  `diagnose` tells alive / advancing / completed-but-unobserved / blocked on a dependency
       / duplicated apart, from records only. It mutates nothing, so valid output and evidence
       already produced are preserved; the restart path stays the owner-audited
       `ops.recovery.restart_stuck_job`.
F-343  `activity` distinguishes work executing, work completed, observer waiting, blocked and
       unknown. A live worker or a live waiter never makes the system busy or progressing:
       "executing" needs a running job whose lease is current, "completed" needs a finished
       job in the window.

Read-only. Consumed by `ops.health.read` (signal `job_durations`) on the 15-minute
`ops.health` cadence, and by the owner truth provider (`ops.truth.summary`).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from statistics import median

INVESTIGATE_MULTIPLE = 3.0
MIN_HISTORY = 5
HISTORY_PER_TYPE = 50
COMPLETED_WINDOW_S = 6 * 60 * 60
ADVANCING_WINDOW_S = 15 * 60

EXECUTING = "work_executing"
COMPLETED = "work_completed"
OBSERVER_WAITING = "observer_waiting"
BLOCKED = "blocked"
UNKNOWN = "unknown"
ACTIVITY_STATES = (EXECUTING, COMPLETED, OBSERVER_WAITING, BLOCKED, UNKNOWN)

# Inputs that differ between two otherwise identical enqueues and so do not make work distinct.
_VOLATILE_INPUT_KEYS = frozenset({"cadence", "request_id", "enqueued_at", "at", "tick"})


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def envelopes(session, *, now: datetime | None = None) -> dict[str, dict]:
    """Rolling median duration (seconds) per job_type from its latest completed jobs."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    samples: dict[str, list[float]] = {}
    q = (select(Job.job_type, Job.started_at, Job.finished_at)
         .where(Job.status == JobStatus.DONE, Job.started_at.is_not(None),
                Job.finished_at.is_not(None))
         .order_by(Job.id.desc()).limit(5000))
    for job_type, started, finished in session.execute(q):
        bucket = samples.setdefault(job_type, [])
        if len(bucket) >= HISTORY_PER_TYPE:
            continue
        secs = (_aware(finished) - _aware(started)).total_seconds()
        if secs >= 0:
            bucket.append(secs)
    return {jt: {"samples": len(v), "median_s": round(median(v), 3) if v else None,
                 "enough_history": len(v) >= MIN_HISTORY,
                 "investigate_after_s": (round(median(v) * INVESTIGATE_MULTIPLE, 3)
                                         if len(v) >= MIN_HISTORY else None)}
            for jt, v in samples.items()}


def _canonical_inputs(inputs) -> str:
    data = {k: v for k, v in (inputs or {}).items() if k not in _VOLATILE_INPUT_KEYS}
    return json.dumps(data, sort_keys=True, default=str)


def diagnose(session, job, *, now: datetime | None = None) -> dict:
    """What a long-running job is actually doing, from records. Never mutates anything."""
    from sqlalchemy import func, select

    from ..core.models import AuditLog, Job, JobStatus

    now = _aware(now or datetime.now(timezone.utc))
    lease = _aware(job.lease_expires_at)
    alive = lease is not None and lease > now
    recent_audit = session.scalar(
        select(func.max(AuditLog.at)).where(AuditLog.job_id == job.id))
    advancing = (recent_audit is not None and
                 now - _aware(recent_audit) <= timedelta(seconds=ADVANCING_WINDOW_S))
    completed_unobserved = job.status == JobStatus.RUNNING and (
        job.outputs is not None or job.finished_at is not None)
    blocked_on = []
    for k, v in (job.inputs or {}).items():
        if not (k.endswith("job_id") and isinstance(v, int)):
            continue
        dep = session.get(Job, v)
        if dep is not None and dep.status in (JobStatus.PENDING, JobStatus.RUNNING,
                                              JobStatus.FAILED):
            blocked_on.append({"input": k, "job_id": v, "status": dep.status.value})
    key = _canonical_inputs(job.inputs)
    duplicates = [j.id for j in session.scalars(
        select(Job).where(Job.job_type == job.job_type, Job.id != job.id,
                          Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING))))
        if _canonical_inputs(j.inputs) == key]
    if completed_unobserved:
        verdict = "completed_but_unobserved"
    elif blocked_on:
        verdict = "blocked_on_dependency"
    elif duplicates:
        verdict = "duplicated"
    elif alive and advancing:
        verdict = "alive_and_advancing"
    elif alive:
        verdict = "alive_not_advancing"
    else:
        verdict = "lease_lapsed"
    return {"job_id": job.id, "job_type": job.job_type, "status": job.status.value,
            "alive": alive, "advancing": advancing,
            "last_audit_at": _aware(recent_audit).isoformat() if recent_audit else None,
            "completed_but_unobserved": completed_unobserved, "blocked_on": blocked_on,
            "duplicates": duplicates, "verdict": verdict,
            "destructive_action_taken": False,
            "preserve": ("outputs already written stay on the row; a restart, if anyone "
                         "chooses one, goes through ops.recovery.restart_stuck_job (audited)")}


def watch(session, *, now: datetime | None = None) -> dict:
    """Every running job against its envelope; over-envelope ones diagnosed, not restarted."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    now = _aware(now or datetime.now(timezone.utc))
    env = envelopes(session, now=now)
    running = list(session.scalars(select(Job).where(Job.status == JobStatus.RUNNING)))
    over, unassessable = [], []
    for job in running:
        e = env.get(job.job_type) or {"enough_history": False, "samples": 0}
        started = _aware(job.started_at)
        runtime = (now - started).total_seconds() if started else None
        if runtime is None or not e["enough_history"]:
            unassessable.append({"job_id": job.id, "job_type": job.job_type,
                                 "samples": e.get("samples", 0),
                                 "why": "no start time" if runtime is None else
                                 f"fewer than {MIN_HISTORY} completed samples"})
            continue
        if runtime > e["investigate_after_s"]:
            over.append({"job_id": job.id, "job_type": job.job_type,
                         "runtime_s": round(runtime, 1), "median_s": e["median_s"],
                         "multiple": round(runtime / e["median_s"], 2) if e["median_s"]
                         else None,
                         "diagnosis": diagnose(session, job, now=now)})
    return {"running": len(running), "over_envelope": over, "unassessable": unassessable,
            "envelopes": env, "threshold_multiple": INVESTIGATE_MULTIPLE,
            "min_history": MIN_HISTORY, "as_of": now.isoformat()}


def activity(session, *, now: datetime | None = None, observers_alive: int = 0) -> dict:
    """One of the five activity states, from job rows -- never from a process being alive."""
    from sqlalchemy import func, select

    from ..core.models import Job, JobStatus

    from .health import SELF_OBSERVING_JOB_TYPES

    now = _aware(now or datetime.now(timezone.utc))
    try:
        running = list(session.scalars(select(Job).where(Job.status == JobStatus.RUNNING)))
        done = session.scalar(select(func.count()).select_from(Job).where(
            Job.status == JobStatus.DONE, Job.finished_at.is_not(None),
            Job.job_type.not_in(tuple(SELF_OBSERVING_JOB_TYPES)),
            Job.finished_at >= now - timedelta(seconds=COMPLETED_WINDOW_S))) or 0
        pending = session.scalar(select(func.count()).select_from(Job).where(
            Job.status == JobStatus.PENDING)) or 0
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN, never idle
        return {"state": UNKNOWN, "why": f"jobs unreadable: {type(exc).__name__}"}
    # The sweep observing the system is not the system working (F-343).
    running = [j for j in running if j.job_type not in SELF_OBSERVING_JOB_TYPES]
    executing = [j for j in running if _aware(j.lease_expires_at) is not None
                 and _aware(j.lease_expires_at) > now]
    blocked = []
    for j in running:
        d = diagnose(session, j, now=now)
        if d["verdict"] in ("blocked_on_dependency", "duplicated"):
            blocked.append(j.id)
    if executing and len(blocked) < len(executing):
        state, why = EXECUTING, f"{len(executing)} job(s) running under a current lease"
    elif blocked:
        state, why = BLOCKED, f"running job(s) {blocked} are blocked or duplicated"
    elif done:
        state, why = COMPLETED, f"{done} job(s) completed in the last {COMPLETED_WINDOW_S // 3600}h"
    elif observers_alive or pending:
        state, why = OBSERVER_WAITING, (
            "something is waiting (a live observer or pending jobs) and no work is executing "
            "or completed; a waiter being alive is not progress")
    else:
        state, why = UNKNOWN, "no running, completed or pending work is on record"
    return {"state": state, "why": why, "executing": len(executing),
            "completed_in_window": int(done), "pending": int(pending),
            "blocked_job_ids": blocked, "observers_alive": observers_alive,
            "states": list(ACTIVITY_STATES)}
