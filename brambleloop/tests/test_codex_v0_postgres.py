"""Opt-in budget concurrency test against a disposable local PostgreSQL DB.

Set CODEX_V0_TEST_DATABASE_URL only to a newly created loopback-only database
named codex_v0_budget_test and CODEX_V0_DISPOSABLE_DATABASE=yes. This test
never contacts a paid provider.
"""
import os
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from brambleloop.agents.registry import Registry
from brambleloop.app.command_center.models import OwnerSession
from brambleloop.core.db import Database
from brambleloop.gateway import anthropic as gw
from brambleloop.gateway import paid_provider_gate as gate


def test_postgres_one_reservation_cannot_authorize_two_calls():
    raw = os.environ.get("CODEX_V0_TEST_DATABASE_URL", "")
    if not raw:
        pytest.skip("no disposable local PostgreSQL test database supplied")
    if os.environ.get("CODEX_V0_DISPOSABLE_DATABASE") != "yes":
        pytest.fail("explicit disposable database confirmation is required")
    url = make_url(raw)
    if (url.get_backend_name() != "postgresql" or url.host != "127.0.0.1"
            or url.database != "codex_v0_budget_test"):
        pytest.fail("test requires the named disposable loopback-only PostgreSQL database")
    db = Database(raw, scratch=True)
    if inspect(db.engine).get_table_names():
        pytest.fail("test database must be freshly created and empty")
    db.create_all()
    Registry(db).seed_defaults()
    now = datetime.now(timezone.utc)
    with db.session() as session:
        session.add(OwnerSession(public_id="codex-v0-fixture", token_hash="fixture-only",
            created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=1),
            stepup_until=now + timedelta(minutes=5)))
    provider = "flux-3-image"
    gate.activate(db, provider=provider, scope=gate.GENERATION, by="owner:test",
                  session_public_id="codex-v0-fixture", now=now,
                  daily_ceiling_cad=2, monthly_ceiling_cad=5, per_gallery_cad=2)
    reservation = gw.check_budget_cad(db, estimate_cad=0.4, agent="gateway",
        purpose="test.render", provider=provider, model=provider, now=now)
    ready = threading.Barrier(2)
    results = []

    def attempt(fingerprint):
        ready.wait(timeout=10)
        try:
            gate.authorize(db, provider=provider, scope=gate.GENERATION,
                estimate_cad=0.4, fingerprint=fingerprint,
                reservation_id=reservation["reservation_id"], now=now)
            results.append("allowed")
        except gate.PaidCallRefused as exc:
            results.append(exc.code)

    threads = [threading.Thread(target=attempt, args=(f"test-{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(results) == ["allowed", "reservation_already_used"]
