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
from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.db import Database, is_postgres
from ..core.models import Job, JobStatus, utcnow

DEFAULT_LEASE_SECONDS = 300
BACKOFF_BASE_SECONDS = 2
BACKOFF_CAP_SECONDS = 3600


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


class JobQueue:
    def __init__(self, db: Database, lease_seconds: int = DEFAULT_LEASE_SECONDS):
        self.db = db
        self.lease_seconds = lease_seconds

    # ---- producing -----------------------------------------------------
    def enqueue(
        self,
        agent: str,
        job_type: str,
        inputs: dict | None = None,
        *,
        priority: int = 100,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
        run_after: datetime | None = None,
        session: Session | None = None,
    ) -> Job:
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
    def claim(self, worker: str, job_types: Sequence[str] | None = None) -> Job | None:
        """Atomically lease one runnable job, or return None.

        Runnable means: pending (or failed and due for retry), scheduled time has arrived, and
        not currently held by a live lease. Postgres uses SKIP LOCKED; SQLite relies on its
        write lock plus a conditional update, which is correct because SQLite serialises
        writers anyway.
        """
        now = utcnow()
        with self.db.session() as s:
            q = (
                select(Job)
                .where(
                    Job.status.in_([JobStatus.PENDING, JobStatus.FAILED]),
                    Job.run_after <= now,
                )
                .order_by(Job.priority.asc(), Job.run_after.asc(), Job.id.asc())
                .limit(1)
            )
            if job_types:
                q = q.where(Job.job_type.in_(list(job_types)))
            if is_postgres(self.db.engine):
                q = q.with_for_update(skip_locked=True)

            job = s.scalar(q)
            if job is None:
                job = self._reclaim_expired(s, now, job_types)
                if job is None:
                    return None

            job.status = JobStatus.RUNNING
            job.leased_by = worker
            job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            job.attempts += 1
            job.started_at = job.started_at or now
            s.flush()
            s.expunge(job)
            return job

    def _reclaim_expired(
        self, s: Session, now: datetime, job_types: Sequence[str] | None
    ) -> Job | None:
        """Take back a job whose worker died holding the lease."""
        q = (
            select(Job)
            .where(Job.status == JobStatus.RUNNING)
            .order_by(Job.priority.asc(), Job.id.asc())
        )
        if job_types:
            q = q.where(Job.job_type.in_(list(job_types)))
        for job in s.scalars(q):
            exp = _aware(job.lease_expires_at)
            if exp is not None and exp <= now:
                if job.attempts >= job.max_attempts:
                    job.status = JobStatus.DEAD
                    job.last_error = (job.last_error or "") + " | lease expired, retries exhausted"
                    job.finished_at = now
                    continue
                return job
        return None

    # ---- completing ----------------------------------------------------
    def complete(self, job_id: int, outputs: dict | None = None, cost_cad: float = 0.0) -> None:
        with self.db.session() as s:
            job = s.get(Job, job_id)
            if job is None:
                raise KeyError(f"no job {job_id}")
            job.status = JobStatus.DONE
            job.outputs = outputs or {}
            job.finished_at = utcnow()
            job.leased_by = None
            job.lease_expires_at = None
            job.cost_cad = (job.cost_cad or 0.0) + cost_cad

    def fail(self, job_id: int, error: str, *, retry: bool = True) -> Job:
        """Record a failure and either schedule a backed-off retry or dead-letter the job."""
        with self.db.session() as s:
            job = s.get(Job, job_id)
            if job is None:
                raise KeyError(f"no job {job_id}")
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

    def heartbeat(self, job_id: int) -> None:
        """Extend a lease for a job that is legitimately still running."""
        with self.db.session() as s:
            job = s.get(Job, job_id)
            if job and job.status == JobStatus.RUNNING:
                job.lease_expires_at = utcnow() + timedelta(seconds=self.lease_seconds)

    # ---- inspection ----------------------------------------------------
    def counts(self) -> dict[str, int]:
        with self.db.session() as s:
            out: dict[str, int] = {}
            for st in JobStatus:
                out[st.value] = len(list(s.scalars(select(Job).where(Job.status == st))))
            return out

    def dead_letters(self) -> list[Job]:
        with self.db.session() as s:
            jobs = list(s.scalars(select(Job).where(Job.status == JobStatus.DEAD)))
            for j in jobs:
                s.expunge(j)
            return jobs

    def get(self, job_id: int) -> Job | None:
        with self.db.session() as s:
            job = s.get(Job, job_id)
            if job:
                s.expunge(job)
            return job
