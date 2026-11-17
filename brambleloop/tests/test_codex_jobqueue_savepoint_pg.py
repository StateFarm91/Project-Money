"""Opt-in real PostgreSQL interleaving; use an empty disposable database only."""
import os
from concurrent.futures import ThreadPoolExecutor

try:
    import pytest
except ImportError:  # the runner has no pytest (review 6957186985)
    import _minipytest as pytest
from sqlalchemy import event, inspect, select

from brambleloop.core.db import Database
from brambleloop.core.models import AuditLog, Job
from brambleloop.queue.durable import DuplicateJob, JobQueue


def _skip(why):
    # Under real pytest a missing database skips; the script runner below always supplies one
    # (a disposable local cluster), so reaching this without pytest is a failure, not a pass.
    if hasattr(pytest, "skip"):
        pytest.skip(why)
    raise AssertionError(why)


def test_real_concurrent_duplicate_keeps_caller_transaction():
    url = os.getenv("BRAMBLELOOP_TEST_POSTGRES_URL")
    if not url:
        _skip("requires an empty disposable PostgreSQL database")
    db = Database(url, scratch=True)
    assert db.engine.dialect.name == "postgresql", (
        "BRAMBLELOOP_TEST_POSTGRES_URL must name PostgreSQL")
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


if __name__ == "__main__":
    # Repo convention: no pytest. With no URL a throwaway local cluster is made for the run
    # (tests/_pg_disposable, the test_codex_v0_postgres pattern); only with no PostgreSQL
    # toolchain at all does the suite SKIP.
    import sys

    import _minipytest
    from _pg_disposable import disposable_cluster

    with disposable_cluster("BRAMBLELOOP_TEST_POSTGRES_URL", "jobqueue_savepoint_test",
                            prefix="savepoint-pg-") as _url:
        if _url is None:
            print("SKIP test_real_concurrent_duplicate_keeps_caller_transaction: "
                  "no PostgreSQL toolchain")
            sys.exit(0)
        _minipytest.run_module(globals())
