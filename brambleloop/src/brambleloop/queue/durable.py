"""Durable job queue (Master Plan section 13, acceptance Gate A).

Design constraints that matter because nobody is watching at 3am:

  - A worker that dies mid-job must not strand that job. Jobs are *leased*, not assigned; an
    expired lease is reclaimable.
  - A job that would publish, message or spend must never run twice. That is what
    `idempotency_key` buys: the uniqueness is enforced by the database, not by a code path
    that can be forgotten.
  - A job that keeps failing must stop, loudly, in a dead-letter state rather than retrying
    forever and burning money.
"""
from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import (DateTime, Integer, case, cast, func, literal, or_, select,
                        text, update)
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from ..core.db import Database, is_postgres
from ..core.models import Job, JobStatus, utcnow

DEFAULT_LEASE_SECONDS = 300
BACKOFF_BASE_SECONDS = 2
BACKOFF_CAP_SECONDS = 3600

# Bounded aging (C-15). A due job's effective priority improves by one point for every
# AGING_STEP_SECONDS it has waited past `run_after`, by at most AGING_CAP points. So bands
# order fresh work exactly as before (under ten minutes of waiting nothing moves), and a job
# of band P overtakes fresh band-B work after at most (P - B + 1) * AGING_STEP_SECONDS of
# waiting: a band-200 job beats a steady band-10 stream within 191 * 600 s ~= 31.8 hours.
# The cap (200) keeps the credit bounded, so it cannot turn an ancient job into an arbitrarily
# negative priority that out-ranks everything forever.
AGING_STEP_SECONDS = 600
AGING_CAP = 200

# A claim retries the conditional lease write at most this many times. After the first lost
# write on SQLite this connection holds the write lock, so the second attempt reads
# authoritative state; the bound only matters under Postgres SKIP LOCKED.
CLAIM_ATTEMPTS = 8

# SQLite's busy handler is not fair: under many concurrent writers on a loaded host a waiter
# can lose the lock race for longer than the driver's 5 s timeout and see "database is
# locked". A queue write that fails that way rolled back completely, so it is retried as a
# whole transaction. Without this a lost `complete` became a handler exception, the worker
# failed the job, and the backed-off retry ran it a second time -- a duplicate execution
# arriving through the lock instead of through the claim (C-11).
LOCK_RETRIES = 12


# Dead letters that are the system working rather than the system failing.
#
# ONE classifier, `classify_dead_letter`, answers every question anybody asks about a dead
# letter; `deliberate_refusal` and `JobQueue.requeue_dead` are both read from it. They used to
# be two lists -- `DELIBERATE_REFUSAL_*` here and `JobQueue.REFUSAL_MARKERS` below -- and a
# value that lives in two places disagrees with itself: the Worker's own
# `capability not enabled: shadow mode` dead letter on any type other than store.publish was
# "refused on purpose, never re-drive" to `requeue_dead` and a DEFECT to `ops.health`,
# `/api/verify` and `ops.retention` (certification finding C-14, 2026-09-27).
#
# Three kinds, because there are two questions and they differ on one real row:
#
#   REFUSED     a closed gate said no (shadow mode, a capability nobody granted). Not a
#               defect, and never re-driven -- re-driving it is asking a closed gate to open.
#   STOOD_ASIDE a job stamped for a build other than the one that claimed it, failing so the
#               right replica takes it (2026-09-21). Not a defect, and IS re-drivable: the
#               right build should get the work.
#   DEFECT      everything else. Work the company still owes; re-driven once fixed.
REFUSED = "refused"
STOOD_ASIDE = "stood_aside"
DEFECT = "defect"

# Job types whose every dead letter is a refusal (shadow mode refusing to publish).
DELIBERATE_REFUSAL_TYPES: frozenset[str] = frozenset({"store.publish"})

# A closed gate's words. Written by the Worker as `capability not enabled: ...` and by the
# capability layer's shadow-mode refusals. Matched case-insensitively.
#
# A permission denial is deliberately NOT here. It reads like a refusal and is usually a
# misconfiguration: the operational heartbeat was scheduled against an agent that had no
# permission for it and dead-lettered every fifteen minutes from the first boot. Once the
# registry is corrected that work is owed, and re-driving it is safe regardless, because the
# worker re-authorises on every dispatch.
CAPABILITY_REFUSAL_MARKERS: tuple[str, ...] = ("capability not enabled", "shadow mode")

# Two markers for the pack stand-aside, because the row it produced in production carries
# the *front* of the message and not always the back: `last_error` is the exception text and
# the "another replica" clause is its last sentence, so a truncated or reformatted copy kept
# "asked for pack" and lost the marker that classified it. Either phrase is the same refusal.
STAND_ASIDE_MARKERS: tuple[str, ...] = ("another replica", "asked for pack")

# Every marker that makes a dead letter "not a defect". Kept for callers that read it.
DELIBERATE_REFUSAL_MARKERS: tuple[str, ...] = CAPABILITY_REFUSAL_MARKERS + STAND_ASIDE_MARKERS


def classify_dead_letter(job_type: str, last_error: str = "") -> str:
    """REFUSED, STOOD_ASIDE or DEFECT. The single source every dead-letter reader uses."""
    if job_type in DELIBERATE_REFUSAL_TYPES:
        return REFUSED
    error = (last_error or "").lower()
    if any(marker in error for marker in CAPABILITY_REFUSAL_MARKERS):
        return REFUSED
    if any(marker in error for marker in STAND_ASIDE_MARKERS):
        return STOOD_ASIDE
    return DEFECT


def deliberate_refusal(job_type: str, last_error: str = "") -> bool:
    """Whether this dead letter is a refusal working rather than a defect."""
    return classify_dead_letter(job_type, last_error) != DEFECT


def redrivable(job_type: str, last_error: str = "") -> bool:
    """Whether re-driving this dead letter is recovery rather than asking a closed gate again."""
    return classify_dead_letter(job_type, last_error) != REFUSED


class DuplicateJob(Exception):
    """Raised when an idempotency key already exists. Not an error -- a guarantee working."""

    def __init__(self, key: str, existing_id: int):
        super().__init__(f"job with idempotency key {key!r} already exists (id={existing_id})")
        self.key = key
        self.existing_id = existing_id


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; normalise so comparisons never explode."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _is_lock_error(exc: BaseException) -> bool:
    text_ = str(exc).lower()
    return "database is locked" in text_ or "database table is locked" in text_


class JobQueue:
    def __init__(self, db: Database, lease_seconds: int = DEFAULT_LEASE_SECONDS):
        self.db = db
        self.lease_seconds = lease_seconds

    def _txn(self, fn):
        """Run `fn(session)` in one transaction, retrying the whole of it on a SQLite lock."""
        if is_postgres(self.db.engine):
            with self.db.session() as s:
                return fn(s)
        delay = 0.02
        for attempt in range(LOCK_RETRIES):
            try:
                with self.db.session() as s:
                    return fn(s)
            except OperationalError as exc:
                if not _is_lock_error(exc) or attempt == LOCK_RETRIES - 1:
                    raise
                time.sleep(delay * (1.0 + random.random()))
                delay = min(delay * 2, 1.0)
        raise AssertionError("unreachable")  # pragma: no cover

    # ---- producing -----------------------------------------------------
    def enqueue(
        self,
        agent: str,
        job_type: str,
        inputs: dict | None = None,
        *,
        priority: int | None = None,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
        run_after: datetime | None = None,
        session: Session | None = None,
    ) -> Job:
        # An omitted priority is the job type's band (C-46). The old default of 100 sat below
        # every band (the highest is 95), so every follow-on job enqueued through
        # `JobContext.enqueue` -- gate.certify, listing.draft, store.publish, support.* -- ran
        # after housekeeping. An explicit priority still wins.
        if priority is None:
            from ..swarm.orchestrate import priority_for

            priority = priority_for(job_type)

        def _do(s: Session) -> Job:
            if idempotency_key:
                existing = s.scalar(
                    select(Job).where(Job.idempotency_key == idempotency_key)
                )
                if existing:
                    raise DuplicateJob(idempotency_key, existing.id)
            job = Job(
                agent=agent,
                job_type=job_type,
                inputs=inputs or {},
                priority=priority,
                idempotency_key=idempotency_key,
                max_attempts=max_attempts,
                run_after=run_after or utcnow(),
            )
            s.add(job)
            try:
                s.flush()
            except IntegrityError:
                s.rollback()
                existing = s.scalar(
                    select(Job).where(Job.idempotency_key == idempotency_key)
                )
                raise DuplicateJob(idempotency_key or "", existing.id if existing else -1)
            return job

        if session is not None:
            return _do(session)
        with self.db.session() as s:
            return _do(s)

    # ---- consuming -----------------------------------------------------
    def _effective_priority(self, now: datetime):
        """`priority` less a bounded aging credit for time spent waiting (C-15).

        Claim order was strictly (priority, run_after, id), so a steady stream of band-10
        work starved a band-200 job for ever. Now a due job's effective priority improves by
        one point per AGING_STEP_SECONDS it has waited since `run_after`, capped at
        AGING_CAP points. Fresh work (waited < one step) still orders strictly by band.
        """
        if is_postgres(self.db.engine):
            waited = func.extract("epoch", literal(now, DateTime(timezone=True)) - Job.run_after)
            steps = func.floor(waited / AGING_STEP_SECONDS)
        else:
            waited = (func.julianday(literal(now, DateTime(timezone=True)))
                      - func.julianday(Job.run_after)) * 86400.0
            steps = cast(waited / AGING_STEP_SECONDS, Integer)
        credit = case((steps > AGING_CAP, AGING_CAP), (steps < 0, 0), else_=steps)
        return Job.priority - credit

    def claim(self, worker: str, job_types: Sequence[str] | None = None) -> Job | None:
        """Atomically lease one runnable job, or return None.

        Runnable means: pending (or failed and due for retry), scheduled time has arrived, and
        not currently held by a live lease -- or RUNNING on a lease that has expired.

        The lease is taken by a *conditional* UPDATE that re-states the condition the row was
        chosen on (same status, same `attempts`, still due / still expired) and succeeds only
        when exactly one row changed. The old path read a row and then updated it by id
        unconditionally; on SQLite two workers read the same row between each other's writes
        and both ran it -- 56 of 120 jobs twice under six threads on a WAL file (C-11). A
        losing UPDATE leaves this connection holding SQLite's write lock, so the re-read that
        follows it is authoritative and the next attempt cannot lose the same way. Postgres
        additionally takes the candidate row FOR UPDATE SKIP LOCKED.
        """
        pg = is_postgres(self.db.engine)

        def _do(s: Session) -> Job | None:
            now = utcnow()
            for _ in range(CLAIM_ATTEMPTS):
                # Expired leases first, not only when nothing else is runnable. A job whose
                # worker died holding the lease was otherwise recoverable only while the
                # queue was idle -- under a backlog, when a worker is most likely to be
                # killed, the orphan stayed RUNNING behind newer work indefinitely. It cannot
                # spin: `claim` increments `attempts`, so a job that keeps dying reaches
                # `max_attempts` and dead-letters like any other.
                taken = self._reclaim_expired(s, now, job_types, worker)
                if taken is None:
                    q = (
                        select(Job.id, Job.attempts)
                        .where(
                            Job.status.in_([JobStatus.PENDING, JobStatus.FAILED]),
                            Job.run_after <= now,
                        )
                        .order_by(self._effective_priority(now).asc(),
                                  Job.run_after.asc(), Job.id.asc())
                        .limit(1)
                    )
                    if job_types:
                        q = q.where(Job.job_type.in_(list(job_types)))
                    if pg:
                        q = q.with_for_update(skip_locked=True, of=Job)
                    row = s.execute(q).first()
                    if row is None:
                        return None
                    taken = self._take(s, row.id, row.attempts, worker, now, reclaim=False)
                if taken is not None:
                    job = s.get(Job, taken, populate_existing=True)
                    s.flush()
                    s.expunge(job)
                    return job
            return None

        return self._txn(_do)

    def _take(self, s: Session, job_id: int, attempts: int, worker: str, now: datetime,
              *, reclaim: bool) -> int | None:
        """The conditional lease write. Returns the id when this call won the row."""
        cond = [Job.id == job_id, Job.attempts == attempts]
        if reclaim:
            cond += [Job.status == JobStatus.RUNNING, Job.lease_expires_at <= now]
        else:
            cond += [Job.status.in_([JobStatus.PENDING, JobStatus.FAILED]),
                     Job.run_after <= now]
        res = s.execute(
            update(Job).where(*cond).values(
                status=JobStatus.RUNNING,
                leased_by=worker,
                lease_expires_at=now + timedelta(seconds=self.lease_seconds),
                attempts=Job.attempts + 1,
                started_at=func.coalesce(Job.started_at, now),
            ).execution_options(synchronize_session=False))
        return job_id if res.rowcount == 1 else None

    def _reclaim_expired(
        self, s: Session, now: datetime, job_types: Sequence[str] | None, worker: str
    ) -> int | None:
        """Take back a job whose worker died holding the lease. Returns the id taken."""
        q = (
            select(Job.id, Job.attempts, Job.max_attempts)
            .where(Job.status == JobStatus.RUNNING, Job.lease_expires_at <= now)
            .order_by(Job.priority.asc(), Job.id.asc())
        )
        if job_types:
            q = q.where(Job.job_type.in_(list(job_types)))
        # The same lock the pending claim takes. Without it two workers reclaiming at the
        # same moment both read the same expired row, both set it RUNNING and both run the
        # job -- which is precisely the double-execution `idempotency_key` exists to make
        # impossible, arriving through the recovery path instead of the enqueue path.
        if is_postgres(self.db.engine):
            q = q.with_for_update(skip_locked=True, of=Job)
        for row in s.execute(q).all():
            if row.attempts >= row.max_attempts:
                s.execute(
                    update(Job).where(Job.id == row.id, Job.attempts == row.attempts,
                                      Job.status == JobStatus.RUNNING,
                                      Job.lease_expires_at <= now)
                    .values(status=JobStatus.DEAD,
                            last_error=func.coalesce(Job.last_error, "")
                            + " | lease expired, retries exhausted",
                            finished_at=now)
                    .execution_options(synchronize_session=False))
                continue
            taken = self._take(s, row.id, row.attempts, worker, now, reclaim=True)
            if taken is not None:
                return taken
        return None

    # ---- completing ----------------------------------------------------
    # ---- fencing ---------------------------------------------------------
    #
    # A lease that expired was reclaimed, and the job now belongs to whoever reclaimed it.
    # The original worker does not know that: it was slow, not dead, and when its handler
    # returns it will try to mark the job done -- over the top of the second run, which may
    # still be executing, and with outputs from a run the queue had already given up on.
    # That is two writers believing they own one row, which is the exact thing a lease is
    # for preventing. So a completion or failure names the worker it comes from, and one
    # from a worker that no longer holds the lease is refused and recorded rather than
    # applied.
    #
    # `worker=None` is for a job nobody is running. It used to be unconditional, so an
    # unnamed caller overwrote a job another worker held on a live lease (C-12). It is now
    # refused whenever the job is RUNNING on a live lease somebody holds; an operator who
    # really means to override a running job passes `administrative=True`, and that override
    # is itself audited.
    def _fenced(self, s: Session, job: Job, worker: str | None, what: str,
                administrative: bool = False) -> bool:
        """True when `worker` may write this job's outcome; audits and refuses otherwise."""
        from ..core.models import AuditLog

        now = utcnow()
        exp = _aware(job.lease_expires_at)
        live_holder = (job.status == JobStatus.RUNNING and bool(job.leased_by)
                       and exp is not None and exp > now)
        status = getattr(job.status, "value", str(job.status))
        if worker is None:
            if not live_holder:
                return True
            if administrative:
                s.add(AuditLog(actor="queue", action="queue.administrative_override",
                               artifact=job.job_type, job_id=job.id,
                               detail={"attempted": what, "lease_held_by": job.leased_by,
                                       "lease_expires_at": exp.isoformat(),
                                       "status": status,
                                       "why": ("an unnamed administrative caller wrote the "
                                               "outcome of a job another worker holds on a "
                                               "live lease")}))
                return True
            s.add(AuditLog(actor="queue", action="queue.unfenced_write_refused",
                           artifact=job.job_type, job_id=job.id,
                           detail={"attempted": what, "lease_held_by": job.leased_by,
                                   "lease_expires_at": exp.isoformat(), "status": status,
                                   "why": ("an unnamed caller tried to write the outcome "
                                           "of a job another worker holds on a live lease; "
                                           "pass worker= or administrative=True")}))
            return False
        # Held by this worker, or held by nobody while still running (a row written before
        # leases carried a name). A job that is no longer RUNNING was finished or re-queued
        # by somebody else, and a late report from this worker would overwrite that.
        if job.status == JobStatus.RUNNING and (not job.leased_by or job.leased_by == worker):
            return True
        s.add(AuditLog(actor="queue", action="queue.stale_lease_refused",
                       artifact=job.job_type, job_id=job.id,
                       detail={"attempted_by": worker, "lease_held_by": job.leased_by,
                               "attempted": what, "status": status,
                               "why": ("this worker's lease expired and the job was "
                                       "reclaimed; its outcome belongs to the current "
                                       "holder, not to a run the queue already gave up on")}))
        return False

    def complete(self, job_id: int, outputs: dict | None = None, cost_cad: float = 0.0,
                 *, worker: str | None = None, administrative: bool = False) -> bool:
        """Mark a job done. Returns False, changing nothing, when the write is fenced off."""
        def _do(s: Session) -> bool:
            job = s.get(Job, job_id)
            if job is None:
                raise KeyError(f"no job {job_id}")
            if not self._fenced(s, job, worker, "complete", administrative):
                return False
            job.status = JobStatus.DONE
            job.outputs = outputs or {}
            job.finished_at = utcnow()
            job.leased_by = None
            job.lease_expires_at = None
            job.cost_cad = (job.cost_cad or 0.0) + cost_cad
            return True

        return self._txn(_do)

    def fail(self, job_id: int, error: str, *, retry: bool = True,
             worker: str | None = None, administrative: bool = False) -> Job | None:
        """Record a failure and either schedule a backed-off retry or dead-letter the job.

        Returns None, changing nothing, when the write is fenced off: a failure reported by a
        run the queue already reclaimed must not dead-letter or back off the run that
        replaced it.
        """
        def _do(s: Session) -> Job | None:
            job = s.get(Job, job_id)
            if job is None:
                raise KeyError(f"no job {job_id}")
            if not self._fenced(s, job, worker, "fail", administrative):
                return None
            job.last_error = error[:4000]
            job.leased_by = None
            job.lease_expires_at = None

            if not retry or job.attempts >= job.max_attempts:
                job.status = JobStatus.DEAD
                job.finished_at = utcnow()
            else:
                job.status = JobStatus.FAILED
                delay = min(
                    BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS ** job.attempts
                )
                # Jitter so a provider outage does not produce a synchronised retry stampede.
                delay = delay * (0.8 + 0.4 * random.random())
                job.run_after = utcnow() + timedelta(seconds=delay)
            s.flush()
            s.expunge(job)
            return job

        return self._txn(_do)

    def heartbeat(self, job_id: int, *, worker: str | None = None) -> bool:
        """Extend a lease for a job that is legitimately still running. True when extended.

        Fenced like `complete` (C-13): a named worker extends only a lease it holds (or an
        unnamed legacy lease). A stale worker's renewal thread used to keep extending the
        lease on a job another worker had reclaimed, so if that worker then died its orphan
        stayed unreclaimable for as long as the stale thread kept ticking. `worker=None` is
        the unnamed legacy path and extends any RUNNING job.
        """
        cond = [Job.id == job_id, Job.status == JobStatus.RUNNING]
        if worker is not None:
            cond.append(or_(Job.leased_by.is_(None), Job.leased_by == worker))
        def _do(s: Session) -> bool:
            res = s.execute(
                update(Job).where(*cond)
                .values(lease_expires_at=utcnow() + timedelta(seconds=self.lease_seconds))
                .execution_options(synchronize_session=False))
            return res.rowcount == 1

        return self._txn(_do)

    # ---- inspection ----------------------------------------------------
    def counts(self) -> dict[str, int]:
        """How many jobs are in each state, counted by the database.

        This built every count by loading every matching row into Python -- six full table
        scans, six times the whole `jobs` table materialised as objects, on an endpoint the
        console polls. It was invisible at a few hundred rows and is not a fixed cost:
        production completed 226 jobs in six hours on 2026-09-24, about 900 a day, so the
        work this function does grows for as long as the company runs and never comes back
        down. `/api/status` already took 0.8s. One grouped count is the same answer in one
        round trip that does not move the rows at all.
        """
        with self.db.session() as s:
            out: dict[str, int] = {st.value: 0 for st in JobStatus}
            rows = s.execute(
                select(Job.status, func.count()).group_by(Job.status)).all()
            for status, n in rows:
                out[getattr(status, "value", status)] = int(n)
            return out

    def dead_letters(self) -> list[Job]:
        with self.db.session() as s:
            jobs = list(s.scalars(select(Job).where(Job.status == JobStatus.DEAD)))
            for j in jobs:
                s.expunge(j)
            return jobs

    # Kept for callers that read it; the decision is `classify_dead_letter`'s (C-14).
    REFUSAL_MARKERS = CAPABILITY_REFUSAL_MARKERS

    def requeue_dead(self, *, job_types: list[str] | None = None,
                     ids: list[int] | None = None, reset_attempts: bool = True) -> dict:
        """Re-drive dead-lettered jobs after the bug that killed them has been fixed.

        A dead letter caused by a defect is work the company still owes. Once the defect is
        fixed the job should run, not sit in a graveyard making the queue-health signal red
        forever. This is the operational counterpart to fixing the code.

        Deliberate refusals are never re-driven. Returns what it moved and what it declined,
        because an operation that silently skips half its input is worse than one that fails.
        """
        moved: list[int] = []
        skipped: list[dict] = []
        with self.db.session() as s:
            q = select(Job).where(Job.status == JobStatus.DEAD)
            if job_types:
                q = q.where(Job.job_type.in_(job_types))
            if ids:
                q = q.where(Job.id.in_(ids))
            for job in s.scalars(q):
                if not redrivable(job.job_type, job.last_error or ""):
                    skipped.append({"id": job.id, "job_type": job.job_type,
                                    "reason": "refused on purpose, not a failure"})
                    continue
                job.status = JobStatus.PENDING
                job.leased_by = None
                job.lease_expires_at = None
                job.run_after = utcnow()
                job.last_error = None
                job.finished_at = None
                if reset_attempts:
                    job.attempts = 0
                moved.append(job.id)
        return {"requeued": moved, "skipped": skipped}

    def purge_dead(self, *, job_types: list[str], before: datetime | None = None) -> int:
        """Delete dead letters of a given type. Used only for jobs that must never re-run.

        Requires explicit job types: there is no "purge everything", because the one thing a
        dead-letter queue must never do is lose a failure nobody looked at.

        A job something else points at is skipped. `audit_log.job_id`, `cost_entries.job_id`
        and `spend_reservations.job_id` are real foreign keys, so deleting such a row either
        raises an integrity error or -- on a database with the constraint off -- orphans the
        evidence, and the money rows are the ones every ceiling in the company is computed
        from. This was never hit because nothing called this function; `ops.retention` now
        does, and it reports the same count separately.
        """
        from ..core.models import AuditLog, CostEntry, SpendReservation

        removed = 0
        with self.db.session() as s:
            referenced: set[int] = set()
            for table in (AuditLog, CostEntry, SpendReservation):
                referenced.update(
                    job_id for (job_id,) in s.execute(
                        select(table.job_id).where(table.job_id.is_not(None))).all())
            q = select(Job).where(Job.status == JobStatus.DEAD,
                                  Job.job_type.in_(job_types))
            for job in s.scalars(q):
                if before is not None and (job.finished_at or job.created_at) >= before:
                    continue
                if job.id in referenced:
                    continue
                s.delete(job)
                removed += 1
        return removed

    def get(self, job_id: int) -> Job | None:
        with self.db.session() as s:
            job = s.get(Job, job_id)
            if job:
                s.expunge(job)
            return job
