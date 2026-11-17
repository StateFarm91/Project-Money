"""Opt-in real PostgreSQL concurrent enrichment answer check."""
import os

try:
    import pytest
except ImportError:  # the runner has no pytest (review 6957186985)
    import _minipytest as pytest
from sqlalchemy.engine import make_url

import test_opus2_enrichment_requests as a4b
from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database

CASE_DATABASES = ("a4b_answer_test", "a4b_answer_mixed", "a4b_answer_stale", "a4b_answer_sweep")


def _skip(why):
    # Under real pytest a missing database skips; the script runner below always supplies one
    # (a disposable local cluster), so reaching this without pytest is a failure, not a pass.
    if hasattr(pytest, "skip"):
        pytest.skip(why)
    raise AssertionError(why)


@pytest.mark.parametrize("database_name,case", [
    ("a4b_answer_test", a4b.test_concurrent_real_answer_workers_do_not_spend_same_round),
    ("a4b_answer_mixed", a4b.test_competing_success_and_failed_answers_cannot_commit_the_same_round),
    ("a4b_answer_stale", lambda _monkeypatch: a4b.test_stale_answer_worker_cannot_record_a_round()),
    ("a4b_answer_sweep", a4b.test_sweep_and_answer_serialize_request_state),
])
def test_concurrent_real_answer_workers_on_postgresql(monkeypatch, database_name, case):
    url = os.environ.get("CODEX_A4B_TEST_POSTGRES_URL")
    if not url:
        _skip("requires an explicitly supplied disposable PostgreSQL database")
    parsed = make_url(url)
    if (not parsed.drivername.startswith("postgresql") or parsed.host not in
            {"127.0.0.1", "localhost", "::1"} or parsed.database != "a4b_answer_test"):
        raise AssertionError("refusing: use the isolated local a4b_answer_test database")
    database_url = parsed.set(database=database_name).render_as_string(hide_password=False)
    db = Database(database_url)
    db.create_all()
    Registry(db).seed_defaults()
    monkeypatch.setattr(a4b, "_store", lambda: (db, database_url))
    case(monkeypatch)


def _create_case_databases(url):
    """The disposable cluster holds only a4b_answer_test; each case runs in its own database."""
    from sqlalchemy import create_engine, text

    engine = create_engine(make_url(url).set(drivername="postgresql+psycopg2", database="postgres"),
                           isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            have = set(conn.execute(text("SELECT datname FROM pg_database")).scalars())
            for name in CASE_DATABASES:
                if name not in have:
                    conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        engine.dispose()


if __name__ == "__main__":
    # Repo convention: no pytest. With no URL a throwaway local cluster is made for the run
    # (tests/_pg_disposable, the test_codex_v0_postgres pattern); only with no PostgreSQL
    # toolchain at all does the suite SKIP. A supplied URL is used as is.
    import sys

    import _minipytest
    from _pg_disposable import disposable_cluster

    _made = not os.environ.get("CODEX_A4B_TEST_POSTGRES_URL")
    with disposable_cluster("CODEX_A4B_TEST_POSTGRES_URL", "a4b_answer_test",
                            prefix="a4b-answer-pg-") as _url:
        if _url is None:
            print("SKIP test_concurrent_real_answer_workers_on_postgresql: no PostgreSQL toolchain")
            sys.exit(0)
        if _made:
            _create_case_databases(_url)
        _minipytest.run_module(globals())
