"""Opt-in PostgreSQL atomicity test; use only an empty disposable database."""
import os

import pytest
from sqlalchemy import inspect

from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
import test_codex_a6_atomic_effects as suite


def test_actual_release_effects_on_postgresql(monkeypatch):
    url = os.getenv("BRAMBLELOOP_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("requires an empty disposable PostgreSQL database")
    db = Database(url, scratch=True)
    if db.engine.dialect.name != "postgresql":
        pytest.fail("BRAMBLELOOP_TEST_POSTGRES_URL must name PostgreSQL")
    assert not inspect(db.engine).get_table_names(), "database must be empty"
    db.create_all()
    Registry(db).seed_defaults()
    monkeypatch.setattr(suite, "_store", lambda: (db, None))
    suite.test_actual_job_context_release_audit_and_followon_commit_or_rollback_together()
