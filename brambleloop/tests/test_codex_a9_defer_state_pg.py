"""Opt-in owner-action interleaving on an empty disposable PostgreSQL database."""
import os
import sys

import _minipytest as pytest  # Review U6 H2: pytest is not a dependency; same runner everywhere
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
from brambleloop.core.models import Listing, PatternVersion, Product
import test_codex_a9_defer_state as suite


class _Skip(Exception):
    pass


def _skip(why):
    raise _Skip(why)


def test_source_change_then_defer_rechecks_on_postgresql(monkeypatch):
    url = os.getenv("BRAMBLELOOP_TEST_POSTGRES_URL")
    if not url:
        _skip("requires an empty disposable PostgreSQL database")
    parsed = make_url(url)
    if (parsed.host not in {"localhost", "127.0.0.1", "::1"}
            or os.getenv("BRAMBLELOOP_CONFIRM_DISPOSABLE_POSTGRES") != "1"):
        raise AssertionError("test requires loopback PostgreSQL and explicit disposable confirmation")
    db = Database(url, scratch=True)
    if db.engine.dialect.name != "postgresql":
        raise AssertionError("BRAMBLELOOP_TEST_POSTGRES_URL must name PostgreSQL")
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


if __name__ == "__main__":
    # Review U6 H2. Without a disposable PostgreSQL this prints SKIP and exits 0, the same
    # convention as test_codex_v0_postgres: the harness then reports it as a suite with no
    # passes, which is the honest reading (UNKNOWN, not PASS).
    import traceback

    import _minipytest

    mp = _minipytest.MonkeyPatch()
    name = "test_source_change_then_defer_rechecks_on_postgresql"
    try:
        test_source_change_then_defer_rechecks_on_postgresql(mp)
        print(f"OK   {name}")
    except _Skip as e:
        print(f"SKIP {name}: {e}")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        print(f"FAIL {name}")
        sys.exit(1)
    finally:
        mp.undo()
