"""Opt-in PostgreSQL concurrency tests against a disposable test database."""
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from brambleloop.core.evidence_transaction import run_db_transaction


@pytest.fixture
def db():
    url = os.environ.get("BRAMBLELOOP_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("BRAMBLELOOP_TEST_POSTGRES_URL is not configured")
    if not url.startswith(("postgresql://", "postgresql+psycopg2://")):
        pytest.fail("a PostgreSQL test database URL is required")
    engine = create_engine(url, pool_size=5)
    schema = "codex_evidence_test_" + uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        conn.execute(text(f'CREATE TABLE "{schema}".events (id integer PRIMARY KEY, value integer NOT NULL)'))
        conn.execute(text(f'INSERT INTO "{schema}".events VALUES (1,0),(2,0)'))
    try:
        yield engine, sessionmaker(bind=engine), f'"{schema}".events'
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def test_real_deadlock_retries_whole_transaction(db):
    engine, factory, table = db
    barrier = threading.Barrier(2)
    attempts = [0, 0]

    def worker(index):
        def action(session):
            attempts[index] += 1
            first, second = ((1, 2) if index == 0 else (2, 1))
            session.execute(text(f"UPDATE {table} SET value=value+1 WHERE id=:id"), {"id": first})
            if attempts[index] == 1:
                barrier.wait(timeout=5)
            session.execute(text(f"UPDATE {table} SET value=value+1 WHERE id=:id"), {"id": second})
        run_db_transaction(factory, action, delay_seconds=0)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(worker, range(2)))
    with engine.connect() as conn:
        values = conn.execute(text(f"SELECT value FROM {table} ORDER BY id")).scalars().all()
    assert values == [2, 2] and sorted(attempts) == [1, 2]


def test_real_serialization_error_uses_fresh_snapshot(db):
    engine, factory, table = db
    snapshot, updated = threading.Event(), threading.Event()
    attempts = []

    def writer():
        assert snapshot.wait(5)
        with engine.begin() as conn:
            conn.execute(text(f"UPDATE {table} SET value=10 WHERE id=1"))
        updated.set()

    def action(session):
        attempts.append(1)
        session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        value = session.execute(text(f"SELECT value FROM {table} WHERE id=1")).scalar_one()
        if len(attempts) == 1:
            snapshot.set()
            assert updated.wait(5)
        session.execute(text(f"UPDATE {table} SET value=:v WHERE id=1"), {"v": value + 1})
        return value

    with ThreadPoolExecutor(max_workers=1) as pool:
        writing = pool.submit(writer)
        result = run_db_transaction(factory, action, delay_seconds=0)
        writing.result(timeout=5)
    with engine.connect() as conn:
        value = conn.execute(text(f"SELECT value FROM {table} WHERE id=1")).scalar_one()
    assert (result, value, len(attempts)) == (10, 11, 2)
