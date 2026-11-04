"""Opt-in real PostgreSQL concurrent enrichment answer check."""
import os

import pytest
from sqlalchemy.engine import make_url

import test_opus2_enrichment_requests as a4b
from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database


@pytest.mark.parametrize("database_name,case", [
    ("a4b_answer_test", a4b.test_concurrent_real_answer_workers_do_not_spend_same_round),
    ("a4b_answer_mixed", a4b.test_competing_success_and_failed_answers_cannot_commit_the_same_round),
    ("a4b_answer_stale", lambda _monkeypatch: a4b.test_stale_answer_worker_cannot_record_a_round()),
    ("a4b_answer_sweep", a4b.test_sweep_and_answer_serialize_request_state),
])
def test_concurrent_real_answer_workers_on_postgresql(monkeypatch, database_name, case):
    url = os.environ.get("CODEX_A4B_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("requires an explicitly supplied disposable PostgreSQL database")
    parsed = make_url(url)
    if (not parsed.drivername.startswith("postgresql") or parsed.host not in
            {"127.0.0.1", "localhost", "::1"} or parsed.database != "a4b_answer_test"):
        pytest.fail("refusing: use the isolated local a4b_answer_test database")
    database_url = parsed.set(database=database_name).render_as_string(hide_password=False)
    db = Database(database_url)
    db.create_all()
    Registry(db).seed_defaults()
    monkeypatch.setattr(a4b, "_store", lambda: (db, database_url))
    case(monkeypatch)
