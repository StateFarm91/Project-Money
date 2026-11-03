"""Behavioral retry checks using persistent database transactions."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from brambleloop.core.evidence_transaction import run_db_transaction


class Deadlock(Exception):
    pgcode = "40P01"


def test_abort_rolls_back_before_fresh_transaction(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retry.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE events (id INTEGER PRIMARY KEY, value TEXT)"))
    sessions = []

    def action(session):
        sessions.append(session)
        session.execute(text("INSERT INTO events VALUES (1, 'committed')"))
        if len(sessions) == 1:
            raise DBAPIError("query", {}, Deadlock(), False)
        return "done"

    assert run_db_transaction(sessionmaker(engine), action, sleep=lambda _: None) == "done"
    assert len(sessions) == 2 and sessions[0] is not sessions[1]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT id, value FROM events")).all() == [(1, "committed")]


def test_exhaustion_rolls_back_every_attempt(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'failure.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE events (id INTEGER PRIMARY KEY)"))
    attempts = []

    def action(session):
        attempts.append(1)
        session.execute(text("INSERT INTO events VALUES (1)"))
        raise DBAPIError("query", {}, Deadlock(), False)

    with pytest.raises(DBAPIError):
        run_db_transaction(sessionmaker(engine), action, max_attempts=2, sleep=lambda _: None)
    assert len(attempts) == 2
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM events")).scalar_one() == 0


def test_invalidated_connection_never_retried(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'unknown.db'}")
    attempts = []

    def action(session):
        attempts.append(1)
        raise DBAPIError("query", {}, Deadlock(), connection_invalidated=True)

    with pytest.raises(DBAPIError):
        run_db_transaction(sessionmaker(engine), action, sleep=lambda _: None)
    assert len(attempts) == 1


@pytest.mark.parametrize("raw_connection", [False, True])
def test_callback_cannot_commit_partial_work(tmp_path, raw_connection):
    engine = create_engine(f"sqlite:///{tmp_path / 'commit.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE events (id INTEGER PRIMARY KEY)"))

    def action(session):
        session.execute(text("INSERT INTO events VALUES (1)"))
        if raw_connection:
            session.connection().commit()
        else:
            session.commit()

    with pytest.raises(RuntimeError, match="must not commit"):
        run_db_transaction(sessionmaker(engine), action)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM events")).scalar_one() == 0


def test_non_concurrency_failure_is_not_retried(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'other.db'}")
    attempts = []

    def action(session):
        attempts.append(1)
        raise DBAPIError("query", {}, ValueError("unknown"))

    with pytest.raises(DBAPIError):
        run_db_transaction(sessionmaker(engine), action, sleep=lambda _: None)
    assert len(attempts) == 1
