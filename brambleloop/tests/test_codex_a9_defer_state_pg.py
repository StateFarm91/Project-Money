"""Opt-in owner-action interleaving on an empty disposable PostgreSQL database."""
import os

import pytest
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
from brambleloop.core.models import Listing, PatternVersion, Product
import test_codex_a9_defer_state as suite


def test_source_change_then_defer_rechecks_on_postgresql(monkeypatch):
    url = os.getenv("BRAMBLELOOP_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("requires an empty disposable PostgreSQL database")
    parsed = make_url(url)
    if (parsed.host not in {"localhost", "127.0.0.1", "::1"}
            or os.getenv("BRAMBLELOOP_CONFIRM_DISPOSABLE_POSTGRES") != "1"):
        pytest.fail("test requires loopback PostgreSQL and explicit disposable confirmation")
    db = Database(url, scratch=True)
    if db.engine.dialect.name != "postgresql":
        pytest.fail("BRAMBLELOOP_TEST_POSTGRES_URL must name PostgreSQL")
    assert not inspect(db.engine).get_table_names(), "database must be empty"
    db.create_all()
    Registry(db).seed_defaults()
    with db.session() as session:
        product = Product(slug="test-bound-release", title="Fixture")
        session.add(product)
        session.flush()
        session.add(PatternVersion(product_id=product.id, version="1.0.0", cir_json={},
                                   certified=True, release_hash="a" * 64,
                                   certificate={"granted": True}))
        session.add(Listing(product_slug=product.slug, version="1.0.0", title="Adult Basket",
                            description="Fixture copy", tags=["basket"], release_hash="a" * 64))
    monkeypatch.setattr(suite, "fixture", lambda: db)
    suite.test_defer_rechecks_after_source_writer_releases_owner_queue_lock()
