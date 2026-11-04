"""Caller-owned work survives a duplicate job insert race."""
import tempfile
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from brambleloop.core.db import Database
from brambleloop.core.models import AuditLog, Job
from brambleloop.queue.durable import DuplicateJob, JobQueue


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='queue-savepoint-')}/test.sqlite", scratch=True)
    db.create_all()
    return db


def test_duplicate_insert_race_keeps_outer_transaction_usable_and_committable():
    db = _db()
    queue = JobQueue(db)
    original = queue.enqueue("quality_director", "gate.quality", {},
                             priority=0, idempotency_key="race-key")
    with db._sessions() as session:
        with session.begin():
            session.add(AuditLog(actor="test", action="before"))
            real_scalar = session.scalar
            calls = 0

            def miss_precheck(*args, **kwargs):
                nonlocal calls
                calls += 1
                return None if calls == 1 else real_scalar(*args, **kwargs)

            # Force the stale pre-check, but let the real unique constraint
            # reject the insert. The following lookup uses the real database.
            with patch.object(session, "scalar", side_effect=miss_precheck):
                with pytest.raises(DuplicateJob) as duplicate:
                    queue.enqueue("quality_director", "gate.quality", {}, priority=0,
                                  idempotency_key="race-key", session=session)
            assert duplicate.value.existing_id == original.id
            assert session.in_transaction() and session.is_active
            session.add(AuditLog(actor="test", action="after"))
    with db.session() as observer:
        assert set(observer.scalars(select(AuditLog.action))) >= {"before", "after"}
        assert len(list(observer.scalars(select(Job).where(Job.idempotency_key == "race-key")))) == 1


def test_other_integrity_failure_is_not_misreported_as_duplicate():
    db = _db()
    queue = JobQueue(db)
    with db._sessions() as session:
        with session.begin():
            session.add(AuditLog(actor="test", action="before-invalid-job"))
            with pytest.raises(IntegrityError):
                queue.enqueue(None, "gate.quality", {}, priority=0,
                              idempotency_key="unused-key", session=session)
            assert session.in_transaction() and session.is_active
            session.add(AuditLog(actor="test", action="after-invalid-job"))
    with db.session() as observer:
        assert set(observer.scalars(select(AuditLog.action))) >= {
            "before-invalid-job", "after-invalid-job"}


def test_fresh_outer_transaction_rollback_does_not_commit_the_enqueued_job():
    db = _db()
    queue = JobQueue(db)
    with db._sessions() as session:
        session.begin()
        queue.enqueue("quality_director", "gate.quality", {}, priority=0,
                      idempotency_key="rollback-key", session=session)
        session.rollback()
    with db.session() as observer:
        assert observer.scalar(select(Job).where(Job.idempotency_key == "rollback-key")) is None
