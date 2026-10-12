"""Remote recovery actions for the Command Center (F-900, F-886, F-925).

The owner must be able to un-stick the company from a phone, without Railway's console, a
terminal or the database. Three actions cover the failure shapes the queue actually has:

* ``restart_stuck_job`` -- a job RUNNING on a lease whose holder died (lease expired), or a
  FAILED job sitting out a long backoff, is made claimable *now*. A job on a **live** lease is
  refused: another worker holds it, and restarting it would be the duplicate execution the
  lease exists to prevent.
* ``release_stale_lease`` -- an `ops_leases` row (the single-active-scheduler lease) whose
  expiry has passed is cleared, so a replacement can take it immediately. A live lease is
  refused for the same reason.
* ``rerun_department_cycle`` -- one scheduled cadence is run again: its dead-lettered job is
  re-driven if the dead letter is a defect (never a deliberate refusal, never one the thrash
  breaker forbids), otherwise a fresh job of the cadence's type is enqueued. Refused while a
  job of that type is already PENDING/RUNNING, so it can never double up a cycle.

**Idempotent.** Every call carries a caller-chosen ``request_id``. The first call does the work
and writes one `audit_log` row whose artifact is ``recovery:<request_id>``; a repeat with the
same id does nothing and returns the recorded outcome with ``replayed: True``. A double-tap on
a phone is one action. The underlying writes are conditional UPDATEs and a unique idempotency
key, so even two concurrent first calls cannot both act.

**Audited.** Successes *and* refusals are audit rows naming the actor, the action, the target
and why. No action here bypasses a gate: none publishes, spends or messages anyone; each only
makes existing work claimable again, and the worker re-authorises every job it runs.

**Authorisation is the caller's.** These are pure functions over a database. Lane C exposes
them behind the operator/owner authentication in `app/security.py`; ``actor`` is whoever that
authentication proved. An empty actor is refused.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

ACTIONS = ("restart_stuck_job", "release_stale_lease", "rerun_department_cycle")


class RecoveryRefused(ValueError):
    """The action would be unsafe or meaningless; nothing was changed."""


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _aware(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _scope(db):
    from .slo import _Scope

    return _Scope(db)


def _artifact(request_id: str) -> str:
    return f"recovery:{request_id}"[:200]


def _validate(actor: str, request_id: str) -> None:
    if not (actor or "").strip():
        raise RecoveryRefused("a recovery action needs the authenticated actor who asked")
    rid = (request_id or "").strip()
    if not rid or len(rid) > 120:
        raise RecoveryRefused("a recovery action needs a request_id (1-120 chars) so a "
                              "repeated tap is one action, not two")


def _replay(s, request_id: str) -> dict | None:
    from sqlalchemy import select

    from ..core.models import AuditLog

    row = s.scalar(select(AuditLog).where(AuditLog.artifact == _artifact(request_id),
                                          AuditLog.action.like("recovery.%"))
                   .order_by(AuditLog.id.asc()).limit(1))
    if row is None:
        return None
    out = dict((row.detail or {}).get("result") or {})
    out["replayed"] = True
    return out


def _audit(s, *, actor: str, action: str, request_id: str, result: dict,
           job_id: int | None = None, now: datetime) -> None:
    from ..core.models import AuditLog

    s.add(AuditLog(at=now, actor=actor[:64], action=f"recovery.{action}"[:80],
                   artifact=_artifact(request_id), job_id=job_id,
                   detail={"request_id": request_id, "result": result}))


def _run(db, actor: str, request_id: str, action: str, fn, now: datetime) -> dict:
    """Validate, replay if already done, else act and audit -- one transaction."""
    _validate(actor, request_id)
    with _scope(db) as s:
        prior = _replay(s, request_id)
        if prior is not None:
            if prior.get("action") not in (None, action):
                raise RecoveryRefused(
                    f"request_id {request_id!r} was already used for "
                    f"{prior.get('action')!r}; a request id names one action")
            return prior
        try:
            result = fn(s)
        except RecoveryRefused as exc:
            refused = {"action": action, "done": False, "refused": str(exc),
                       "at": now.isoformat(), "actor": actor}
            _audit(s, actor=actor, action="refused", request_id=request_id, result=refused,
                   now=now)
            refused["replayed"] = False
            return refused
        result = {"action": action, "done": True, "at": now.isoformat(), "actor": actor,
                  **result}
        _audit(s, actor=actor, action=action, request_id=request_id, result=result,
               job_id=result.get("job_id"), now=now)
        result["replayed"] = False
        return result


# ---------------------------------------------------------------------------


def restart_stuck_job(db, job_id: int, *, actor: str, request_id: str, reason: str = "",
                      now: datetime | None = None) -> dict:
    from sqlalchemy import update

    from ..core.models import Job, JobStatus

    now = _now(now)

    def act(s) -> dict:
        job = s.get(Job, int(job_id))
        if job is None:
            raise RecoveryRefused(f"no job {job_id}")
        status = getattr(job.status, "value", str(job.status))
        lease = _aware(job.lease_expires_at)
        if job.status == JobStatus.RUNNING:
            if lease is not None and lease > now:
                raise RecoveryRefused(
                    f"job {job_id} is running on a live lease held by {job.leased_by!r} "
                    f"until {lease.isoformat()}; restarting it would run it twice")
            if (job.attempts or 0) >= (job.max_attempts or 0):
                raise RecoveryRefused(
                    f"job {job_id} has used {job.attempts}/{job.max_attempts} attempts; the "
                    f"queue will dead-letter it on the next claim. Re-run the cycle instead")
            cond = [Job.id == job.id, Job.status == JobStatus.RUNNING,
                    Job.attempts == job.attempts]
            cond.append(Job.lease_expires_at.is_(None) if lease is None
                        else Job.lease_expires_at <= now)
        elif job.status == JobStatus.FAILED:
            if _aware(job.run_after) is not None and _aware(job.run_after) <= now:
                raise RecoveryRefused(f"job {job_id} is already due; a worker will take it")
            cond = [Job.id == job.id, Job.status == JobStatus.FAILED]
        else:
            raise RecoveryRefused(
                f"job {job_id} is {status}; only a RUNNING job with an expired lease or a "
                f"FAILED job waiting out its backoff can be restarted")
        res = s.execute(update(Job).where(*cond).values(
            status=JobStatus.PENDING, leased_by=None, lease_expires_at=None, run_after=now)
            .execution_options(synchronize_session=False))
        if res.rowcount != 1:
            raise RecoveryRefused(f"job {job_id} changed while being restarted; nothing done")
        return {"job_id": job.id, "job_type": job.job_type, "was": status,
                "previous_holder": job.leased_by, "now": "pending", "reason": reason[:300]}

    return _run(db, actor, request_id, "restart_stuck_job", act, now)


def release_stale_lease(db, name: str, *, actor: str, request_id: str,
                        now: datetime | None = None) -> dict:
    from sqlalchemy import update

    from .slo import OpsLease

    now = _now(now)

    def act(s) -> dict:
        row = s.get(OpsLease, name)
        if row is None or not row.holder:
            raise RecoveryRefused(f"lease {name!r} is not held")
        exp = _aware(row.expires_at)
        if exp is not None and exp > now:
            raise RecoveryRefused(
                f"lease {name!r} is live (held by {row.holder!r} until {exp.isoformat()}); "
                f"releasing it would let a second holder run beside the first")
        holder = row.holder
        res = s.execute(update(OpsLease).where(
            OpsLease.name == name, OpsLease.holder == holder,
            (OpsLease.expires_at.is_(None)) | (OpsLease.expires_at <= now))
            .values(holder=None, expires_at=None)
            .execution_options(synchronize_session=False))
        if res.rowcount != 1:
            raise RecoveryRefused(f"lease {name!r} changed while being released")
        return {"lease": name, "previous_holder": holder,
                "expired_at": exp.isoformat() if exp else None}

    return _run(db, actor, request_id, "release_stale_lease", act, now)


def _cadence(name: str) -> tuple[str, str, str, int]:
    from ..runtime.worker import CADENCES

    for row in CADENCES:
        if row[0] == name:
            return row
    raise RecoveryRefused(f"{name!r} is not a scheduled cadence")


def rerun_department_cycle(db, cadence: str, *, actor: str, request_id: str,
                           now: datetime | None = None) -> dict:
    from sqlalchemy import select, update

    from ..core.models import Job, JobStatus
    from ..queue.durable import redrivable

    now = _now(now)

    def act(s) -> dict:
        name, agent, job_type, _period = _cadence(cadence)
        inflight = s.scalar(select(Job.id).where(
            Job.job_type == job_type,
            Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED]))
            .limit(1))
        if inflight is not None:
            raise RecoveryRefused(
                f"{name!r} already has job {inflight} in flight; a second run would double "
                f"the cycle")
        latest = s.scalar(select(Job).where(Job.job_type == job_type)
                          .order_by(Job.id.desc()).limit(1))
        if latest is not None and latest.status == JobStatus.DEAD:
            if not redrivable(latest.job_type, latest.last_error or ""):
                raise RecoveryRefused(
                    f"job {latest.id} was refused on purpose ({(latest.last_error or '')[:120]}"
                    f"); re-running it is asking a closed gate to open")
            try:
                from ..swarm.orchestrate import retry_allowed

                from .slo import _SessionDb

                gate = retry_allowed(_SessionDb(s), latest)
            except Exception:  # noqa: BLE001 - the breaker unreadable is not permission
                gate = {"allowed": False, "why": "the thrash breaker could not be read"}
            if not gate.get("allowed"):
                raise RecoveryRefused(f"job {latest.id}: {gate.get('why')}")
            res = s.execute(update(Job).where(Job.id == latest.id,
                                              Job.status == JobStatus.DEAD)
                            .values(status=JobStatus.PENDING, leased_by=None,
                                    lease_expires_at=None, run_after=now, last_error=None,
                                    finished_at=None, attempts=0)
                            .execution_options(synchronize_session=False))
            if res.rowcount != 1:
                raise RecoveryRefused(f"job {latest.id} changed while being re-driven")
            return {"cadence": name, "job_id": latest.id, "job_type": job_type,
                    "mode": "redrove_dead_letter"}
        return _enqueue(s, name, agent, job_type, request_id, now)

    return _run(db, actor, request_id, "rerun_department_cycle", act, now)


def _enqueue(s, name: str, agent: str, job_type: str, request_id: str,
             now: datetime) -> dict:
    from ..core.models import Job

    try:
        from ..swarm.orchestrate import priority_for

        priority = priority_for(job_type)
    except Exception:  # noqa: BLE001
        priority = 100
    job = Job(agent=agent, job_type=job_type,
              inputs={"cadence": name, "recovery_request": request_id},
              idempotency_key=f"recovery:{name}:{request_id}"[:200], priority=priority,
              run_after=now, created_at=now)
    s.add(job)
    s.flush()
    return {"cadence": name, "job_id": job.id, "job_type": job_type, "mode": "enqueued"}


def recent(db, *, limit: int = 50, since: timedelta = timedelta(days=7),
           now: datetime | None = None) -> list[dict]:
    """The recovery audit trail, newest first, for the Operations surface."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    now = _now(now)
    with _scope(db) as s:
        rows = list(s.scalars(select(AuditLog).where(
            AuditLog.action.like("recovery.%"), AuditLog.at >= now - since)
            .order_by(AuditLog.id.desc()).limit(limit)))
        return [{"id": r.id, "at": _aware(r.at).isoformat(), "actor": r.actor,
                 "action": r.action, "request": r.artifact,
                 "result": (r.detail or {}).get("result")} for r in rows]
