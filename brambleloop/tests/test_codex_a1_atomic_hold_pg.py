"""Opt-in checks against separate disposable local PostgreSQL databases."""
import os

import pytest
from sqlalchemy.engine import make_url

import test_a1r_child_safety_core as harness
import test_codex_a1_atomic_hold as atomic
from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database


@pytest.mark.parametrize("name,case", [
    ("a1_hold_test", atomic.test_concurrent_safety_holds_share_one_owner_action),
    ("a1_hold_stale", atomic.test_stale_producer_cannot_write_safety_hold),
    ("a1_hold_retry", atomic.test_real_worker_retries_after_owner_action_write_failure_atomically),
    ("a1_hold_locks", atomic.test_postgresql_owner_and_job_contention_fails_fast_and_retries),
])
def test_atomic_holds_on_postgresql(monkeypatch, name, case):
    url = os.environ.get("CODEX_A1_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("requires explicitly supplied disposable PostgreSQL databases")
    parsed = make_url(url)
    if (not parsed.drivername.startswith("postgresql") or parsed.host not in
            {"127.0.0.1", "localhost", "::1"} or parsed.database != "a1_hold_test"):
        pytest.fail("refusing: use isolated local a1_hold_test databases")
    db = Database(parsed.set(database=name).render_as_string(hide_password=False))
    db.create_all()
    Registry(db).seed_defaults()
    monkeypatch.setattr(harness, "_store", lambda: (db, None))
    case()
