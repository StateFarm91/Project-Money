"""Opt-in budget concurrency test against a disposable local PostgreSQL DB.

Set CODEX_V0_TEST_DATABASE_URL only to a newly created loopback-only database
named codex_v0_budget_test and CODEX_V0_DISPOSABLE_DATABASE=yes. This test
never contacts a paid provider.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import contextlib
import os
import multiprocessing
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from brambleloop.agents.registry import Registry
from brambleloop.app.command_center.models import OwnerSession
from brambleloop.core.db import Database
from brambleloop.gateway import anthropic as gw
from brambleloop.gateway import paid_provider_gate as gate


class _Skip(Exception):
    pass


@contextlib.contextmanager
def _raises(exc, match: str | None = None):
    try:
        yield
    except exc as e:  # noqa: PERF203
        if match is not None and not re.search(match, str(e)):
            raise AssertionError(f"{exc.__name__} raised, but {str(e)!r} !~ {match!r}") from e
        return
    raise AssertionError(f"{exc.__name__} was not raised")


def _settle_in_process(url, ticket, status, start):
    db = Database(url, scratch=True)
    if not start.wait(timeout=10):
        raise RuntimeError("settlement start signal timed out")
    gate.settle(db, ticket, status, actual_cad=0.7)


def test_postgres_one_reservation_cannot_authorize_two_calls():
    raw = os.environ.get("CODEX_V0_TEST_DATABASE_URL", "")
    if not raw:
        raise _Skip("no disposable local PostgreSQL test database supplied")
    if os.environ.get("CODEX_V0_DISPOSABLE_DATABASE") != "yes":
        raise AssertionError("explicit disposable database confirmation is required")
    url = make_url(raw)
    if (url.get_backend_name() != "postgresql" or url.host != "127.0.0.1"
            or url.database != "codex_v0_budget_test"):
        raise AssertionError("test requires the named disposable loopback-only PostgreSQL database")
    db = Database(raw, scratch=True)
    if inspect(db.engine).get_table_names():
        raise AssertionError("test database must be freshly created and empty")
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
            ticket = gate.authorize(db, provider=provider, scope=gate.GENERATION,
                estimate_cad=0.4, fingerprint=fingerprint,
                reservation_id=reservation["reservation_id"], now=now)
            results.append(("allowed", ticket))
        except gate.PaidCallRefused as exc:
            results.append((exc.code, None))

    threads = [threading.Thread(target=attempt, args=(f"test-{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(value[0] for value in results) == ["allowed", "reservation_already_used"]
    ticket = next(value[1] for value in results if value[0] == "allowed")
    with gw.budget_lock(db):
        with _raises(gw.BudgetExceeded, match="nested"):
            gate.settle(db, ticket, gate.BILLED, actual_cad=0.7)
    with db.session() as session:
        assert session.get(gate.PaidProviderCall, ticket["call_id"]).status == gate.RESERVED
    # Separate processes do not share the Python process lock; the database
    # lock must serialize these contradictory settlement reports.
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    workers = [context.Process(target=_settle_in_process, args=(raw, ticket, status, start))
               for status in (gate.RELEASED, gate.BILLED)]
    for worker in workers:
        worker.start()
    start.set()
    for worker in workers:
        worker.join(timeout=20)
        assert worker.exitcode == 0
    with db.session() as session:
        row = session.get(gate.PaidProviderCall, ticket["call_id"])
        assert row.status == gate.UNCERTAIN
        assert row.estimate_cad == 0.7


if __name__ == "__main__":
    # Repo convention (review U7 F2): no pytest. SKIP exits 0 when no disposable local
    # PostgreSQL database is supplied; anything else is a failure.
    try:
        test_postgres_one_reservation_cannot_authorize_two_calls()
        print("OK   test_postgres_one_reservation_cannot_authorize_two_calls")
        print("0 failure(s)")
        sys.exit(0)
    except _Skip as e:
        print(f"SKIP test_postgres_one_reservation_cannot_authorize_two_calls: {e}")
        sys.exit(0)
    except Exception as e:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        print("FAIL test_postgres_one_reservation_cannot_authorize_two_calls", repr(e))
        print("1 failure(s)")
        sys.exit(1)
