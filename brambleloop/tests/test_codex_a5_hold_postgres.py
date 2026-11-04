"""Opt-in, disposable PostgreSQL check for the A5 hold transaction."""
import os

import pytest
from sqlalchemy.engine import make_url

import test_w5_a5_correction_loop as a5
from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database


@pytest.mark.parametrize("database_name,case", [
    ("a5_hold_test", a5.test_concurrent_identical_holds_are_recorded_once),
    ("a5_hold_stale_test", a5.test_stale_worker_cannot_replace_current_hold_evidence),
])
def test_hold_recording_on_postgresql(monkeypatch, database_name, case):
    url = os.environ.get("CODEX_A5_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("requires an explicitly supplied disposable PostgreSQL database")
    parsed = make_url(url)
    if (not parsed.drivername.startswith("postgresql") or parsed.host not in
            {"127.0.0.1", "localhost", "::1"} or parsed.database != "a5_hold_test"):
        pytest.fail("refusing: use the isolated local a5_hold_test database")
    db = Database(parsed.set(database=database_name).render_as_string(hide_password=False))
    db.create_all()
    Registry(db).seed_defaults()
    monkeypatch.setattr(a5, "_db", lambda: db)
    case()
