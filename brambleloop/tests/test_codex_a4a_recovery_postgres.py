"""Opt-in PostgreSQL coverage using locally created, disposable databases only.

The test user must be allowed to create/drop a database. Never point this at an
application database: the explicit opt-in is intended for an isolated test server.
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import test_w5_a4a_research_to_concept as suite
from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database


@pytest.fixture
def pg_suite(monkeypatch):
    raw_url = os.getenv("CODEX_A4A_TEST_POSTGRES_URL", "")
    if not raw_url or os.getenv("CODEX_A4A_TEST_IS_DISPOSABLE") != "1":
        pytest.skip("requires explicitly opted-in disposable PostgreSQL server")
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql" or url.host not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("A4a tests require a loopback PostgreSQL server")
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg2")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    created = []
    opened = []

    def build():
        name = "a4arecovery_" + uuid.uuid4().hex
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        created.append(name)
        db = Database(url.set(database=name).render_as_string(hide_password=False))
        opened.append(db)
        db.create_all()
        Registry(db).seed_defaults()
        return db

    monkeypatch.setattr(suite, "_db", build)
    try:
        yield suite
    finally:
        for db in opened:
            db.engine.dispose()
        with admin.connect() as conn:
            for name in created:
                conn.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()


def test_restart(pg_suite):
    pg_suite.test_restart_recovers_one_proposal_audit_from_persisted_evidence()


def test_reassignment(pg_suite):
    pg_suite.test_recovery_does_not_record_proposal_for_reassigned_gap()


def test_conflicting_audit(pg_suite):
    pg_suite.test_recovery_holds_when_existing_audit_conflicts_with_proposal()


def test_bad_reference(pg_suite):
    pg_suite.test_recovery_refuses_inconsistent_persisted_census_reference()


def test_concurrent_handlers(pg_suite, monkeypatch):
    pg_suite.test_two_recovery_workers_record_one_proposal_audit(monkeypatch)


def test_reclaimed_lease(pg_suite):
    pg_suite.test_recovery_refuses_worker_whose_lease_was_reclaimed()


def test_reassigned_gap_holds_score(pg_suite):
    pg_suite.test_reassigned_gap_holds_research_candidate_and_real_score_handler()


def test_changed_proposal_holds_old_approval(pg_suite):
    pg_suite.test_changed_attached_proposal_holds_old_approved_concept()


def test_removed_markers_do_not_reclassify_recorded_ideation(pg_suite):
    pg_suite.test_removing_ideation_markers_does_not_reclassify_existing_intake()


def test_future_source_date(pg_suite):
    pg_suite.test_future_dated_market_source_is_not_current_evidence()


def test_malformed_source_date(pg_suite):
    pg_suite.test_malformed_source_date_holds_instead_of_crashing_intake_worker()


def test_missing_finding_support(pg_suite):
    pg_suite.test_finding_with_missing_support_is_not_backed_by_other_valid_source()


def test_future_answer_timestamp(pg_suite):
    pg_suite.test_future_answer_timestamp_is_not_accepted_as_current()


def test_malformed_finding_support(pg_suite):
    pg_suite.test_malformed_support_reference_holds_instead_of_crashing_worker()
