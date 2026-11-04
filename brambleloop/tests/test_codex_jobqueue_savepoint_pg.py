"""Opt-in real PostgreSQL interleaving; use an empty disposable database only."""
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event, inspect, select

from brambleloop.core.db import Database
from brambleloop.core.models import AuditLog, Job
from brambleloop.queue.durable import DuplicateJob, JobQueue


def test_real_concurrent_duplicate_keeps_caller_transaction():
    url = os.getenv("BRAMBLELOOP_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("requires an empty disposable PostgreSQL database")
    db = Database(url, scratch=True)
    if db.engine.dialect.name != "postgresql":
        pytest.fail("BRAMBLELOOP_TEST_POSTGRES_URL must name PostgreSQL")
    assert not inspect(db.engine).get_table_names(), "database must be empty"
    db.create_all()
    queue = JobQueue(db)
    winner_ids = []
    with db._sessions() as session:
        with session.begin():
            session.add(AuditLog(actor="race", action="before"))
            connection = session.connection()

            def insert_winner(conn, cursor, statement, parameters, context, executemany):
                if statement.lstrip().upper().startswith("INSERT INTO JOBS") and not winner_ids:
                    winner_ids.append(None)
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(queue.enqueue, "quality_director", "gate.quality", {},
                                             priority=0, idempotency_key="pg-race-key")
                        winner_ids[0] = future.result(timeout=10).id

            event.listen(connection, "before_cursor_execute", insert_winner)
            try:
                with pytest.raises(DuplicateJob) as duplicate:
                    queue.enqueue("quality_director", "gate.quality", {}, priority=0,
                                  idempotency_key="pg-race-key", session=session)
                assert duplicate.value.existing_id == winner_ids[0]
                assert session.in_transaction() and session.is_active
                session.add(AuditLog(actor="race", action="after"))
            finally:
                event.remove(connection, "before_cursor_execute", insert_winner)
    with db.session() as observer:
        assert set(observer.scalars(select(AuditLog.action).where(AuditLog.actor == "race"))) == {
            "before", "after"}
        assert len(list(observer.scalars(select(Job).where(Job.idempotency_key == "pg-race-key")))) == 1
