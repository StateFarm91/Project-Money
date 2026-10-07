"""Durable job checkpoints (F-659): a long job resumes from its last step after a reclaim.

A worker that dies part-way through a multi-step job (a render sequence, a seasonal cycle)
used to restart that job from the top on reclaim. The paid-call replay (F-307 / F-339,
`gateway.paid_calls`) already stops a restarted job paying twice for the *same* model call,
but it does not stop the job redoing every free and every non-model step, and it cannot help
a step whose request differs on the second run. A checkpoint is the job's own record of
"steps up to here are done, and this is what they produced", written as each step finishes.

Semantics:

* Keyed by (job id, key). Writing the same key again replaces it, so a step that re-runs
  after a reclaim records one row, not two.
* Fenced to the lease holder: a write is accepted only while the job is RUNNING and, when the
  caller presents a lease token, only for the current token. A stale worker whose lease was
  reclaimed cannot overwrite the checkpoint the current holder is resuming from.
* Survives `fail(retry=True)` and lease reclaim (that is its purpose). Removed when the job
  completes; kept on a dead letter as evidence of how far it got.
* A checkpoint is a resume hint, never a payment record. Replay of paid answers stays with
  `gateway.paid_calls`; a handler resuming from a checkpoint still goes through the gateway
  for any call it makes, so the ceiling and the replay semantics are unchanged.

Table registration: created on first use (`ensure_table`, checkfirst) and imported by
`autonomy.models`, which `core.db.Database.create_all` already registers.
"""
from __future__ import annotations

import threading
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import Job, JobStatus, utcnow

AUDIT_ACTION = "job.checkpoint"


class JobCheckpoint(Base):
    __tablename__ = "job_checkpoints"
    job_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CheckpointRefused(RuntimeError):
    """The writer no longer holds the job; its checkpoint is not recorded."""


_ensured: set[int] = set()
_lock = threading.Lock()


def ensure_table(db) -> None:
    key = id(db.engine)
    if key in _ensured:
        return
    with _lock:
        if key not in _ensured:
            JobCheckpoint.__table__.create(db.engine, checkfirst=True)
            _ensured.add(key)


def save(db, job_id: int, key: str, state: dict, *, lease_token: str | None = None) -> dict:
    """Record `state` under `key` for a running job. Raises `CheckpointRefused` when fenced."""
    if not key or len(key) > 120:
        raise ValueError("checkpoint key must be 1-120 characters")
    ensure_table(db)
    with db.session() as s:
        job = s.get(Job, job_id)
        if job is None or job.status != JobStatus.RUNNING:
            raise CheckpointRefused(f"job {job_id} is not running; checkpoint {key!r} "
                                    f"not recorded")
        if lease_token is not None and job.lease_token != lease_token:
            raise CheckpointRefused(f"job {job_id}: lease no longer held by this attempt; "
                                    f"checkpoint {key!r} not recorded")
        row = s.get(JobCheckpoint, (job_id, key))
        if row is None:
            row = JobCheckpoint(job_id=job_id, key=key)
            s.add(row)
        row.state = dict(state or {})
        row.attempt = int(job.attempts or 0)
        row.saved_at = utcnow()
        return {"job_id": job_id, "key": key, "attempt": row.attempt}


def load(db, job_id: int, key: str) -> dict | None:
    """The last state recorded under `key` for this job, or None (never an empty default)."""
    ensure_table(db)
    with db.session() as s:
        row = s.get(JobCheckpoint, (job_id, key))
        return None if row is None else {**dict(row.state or {}),
                                         "_checkpoint": {"attempt": row.attempt,
                                                         "saved_at": str(row.saved_at)}}


def all_for(db, job_id: int) -> dict[str, dict]:
    ensure_table(db)
    with db.session() as s:
        return {r.key: dict(r.state or {}) for r in s.scalars(
            select(JobCheckpoint).where(JobCheckpoint.job_id == job_id)
            .order_by(JobCheckpoint.key))}


def clear(db_or_session, job_id: int) -> int:
    """Remove a job's checkpoints (on completion). Accepts a Database or an open Session."""
    if hasattr(db_or_session, "engine"):
        ensure_table(db_or_session)
        with db_or_session.session() as s:
            return int(s.execute(delete(JobCheckpoint)
                                 .where(JobCheckpoint.job_id == job_id)).rowcount or 0)
    return int(db_or_session.execute(delete(JobCheckpoint)
                                     .where(JobCheckpoint.job_id == job_id)).rowcount or 0)
