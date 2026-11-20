"""F-473 Priority Preemption: long, lower-value work yields to waiting higher-band work.

Bands order claiming and lane holds return over-share jobs to PENDING, but a running job was
never asked to stop: a two-hour drain of exploration work held its worker while a truth
defect waited behind a full pool. Preemption here is **cooperative**: a long handler asks
`JobContext.should_yield()` between steps; when the answer is yes it checkpoints its progress
and calls `JobContext.yield_now()`, and the worker puts the job back to PENDING -- unleased,
its attempt not counted, claimable again shortly -- exactly as a lane hold does. Nothing is
killed mid-step and nothing is lost: the checkpoint (`queue.checkpoints`, F-659) lets the next
attempt resume.

Preemption is wanted only when all of these hold:

* the pool is full -- running jobs >= the worker target (unknown target: never preempt);
* a runnable PENDING job sits in a strictly better band than the running one (a lower band
  number), or in a protected claim tier (customer incident, truth defect) the running job is
  not in;
* that job has waited at least ``MIN_WAIT_S`` (so a brief race is not a preemption).

Checks are cheap but not free, so a context asks the database at most every
``CHECK_EVERY_S``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

MIN_WAIT_S = 120
CHECK_EVERY_S = 30
REQUEUE_AFTER_S = 5
PREEMPTED_ACTION = "job.preempted"


class Preempted(Exception):
    """Raised by `JobContext.yield_now`; the worker requeues the job un-counted."""

    def __init__(self, job_id: int, why: str, checkpoint_key: str | None = None):
        super().__init__(why)
        self.job_id = job_id
        self.why = why
        self.checkpoint_key = checkpoint_key


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _worker_target() -> int | None:
    try:
        from ..app.runner import STATE

        t = STATE.worker_target
        return int(t) if isinstance(t, int) and t > 0 else None
    except Exception:  # noqa: BLE001
        return None


def preemption_wanted(db, job, *, worker_target: int | None = None,
                      now: datetime | None = None) -> dict | None:
    """The waiting job this running one should yield to, or None."""
    from sqlalchemy import func, select

    from ..core.models import Job, JobStatus
    from .orchestrate import band_for, claim_tier

    now = now or datetime.now(timezone.utc)
    target = worker_target if worker_target is not None else _worker_target()
    if not target:
        return None
    mine_band = band_for(job.job_type)["band"]
    mine_tier = claim_tier(job.job_type)
    with db.session() as s:
        running = int(s.scalar(select(func.count()).select_from(Job).where(
            Job.status == JobStatus.RUNNING)) or 0)
        if running < target:
            return None
        waiting = list(s.execute(select(Job.id, Job.job_type, Job.created_at, Job.run_after)
                                 .where(Job.status == JobStatus.PENDING)).all())
    best = None
    for jid, jt, created, run_after in waiting:
        ready_at = max(_aware(created), _aware(run_after) or _aware(created))
        if ready_at > now or (now - ready_at).total_seconds() < MIN_WAIT_S:
            continue
        band, tier = band_for(jt)["band"], claim_tier(jt)
        if tier < mine_tier or band < mine_band:
            if best is None or (tier, band) < (best["tier"], best["band"]):
                best = {"job": f"jobs:{jid}", "job_type": jt, "band": band, "tier": tier,
                        "waited_s": round((now - ready_at).total_seconds())}
    if best is None:
        return None
    return {**best, "running": running, "worker_target": target,
            "why": (f"{best['job_type']} (band {best['band']}) has waited "
                    f"{best['waited_s']}s behind a full pool ({running}/{target}) while "
                    f"{job.job_type} (band {mine_band}) runs")}


def requeue_preempted(db, job, *, worker: str, why: str,
                      now: datetime | None = None) -> bool:
    """Put a preempted job back to PENDING, unleased, its attempt un-counted. Lease-fenced."""
    from sqlalchemy import update

    from ..core.models import AuditLog, Job, JobStatus

    now = now or datetime.now(timezone.utc)
    values = {"status": JobStatus.PENDING, "leased_by": None, "lease_expires_at": None,
              "attempts": Job.attempts - 1,
              "run_after": now + timedelta(seconds=REQUEUE_AFTER_S)}
    with db.session() as s:
        res = s.execute(update(Job).where(
            Job.id == job.id, Job.status == JobStatus.RUNNING, Job.leased_by == worker,
            Job.attempts == job.attempts).values(**values)
            .execution_options(synchronize_session=False))
        if res.rowcount != 1:
            return False
        s.add(AuditLog(actor="swarm_steward", action=PREEMPTED_ACTION, artifact=job.job_type,
                       job_id=job.id, detail={"worker": worker, "why": why[:400]}))
    return True
