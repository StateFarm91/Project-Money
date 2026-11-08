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
    assert len(workers) == 2, "both contradictory settlement reports must race"
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


@contextlib.contextmanager
def _disposable_cluster():
    """W6 certification: when no database is supplied but a local PostgreSQL toolchain is
    installed, make a brand-new throwaway cluster for this run only -- TCP on 127.0.0.1 only,
    a free port, one fresh empty `codex_v0_budget_test` database -- and destroy it afterwards.
    `initdb -A trust` trusts every local connection (loopback TCP and its own Unix socket
    directory), so while the test runs any local user of this container could connect: fine in
    a single-tenant test container, never on a shared host. The directory is under /tmp, not
    the runner's TMPDIR (the `postgres` user must traverse it), so a SIGKILLed run's leftover
    `codex-v0-pg-*` is not in the runner's TMP LEAKED census. A supplied
    CODEX_V0_TEST_DATABASE_URL is always used as is. With no toolchain nothing is created and
    the test SKIPs (which the runner counts as no passes)."""
    import glob
    import shutil
    import socket
    import subprocess
    import tempfile

    if os.environ.get("CODEX_V0_TEST_DATABASE_URL"):
        yield
        return
    bins = sorted(glob.glob("/usr/lib/postgresql/*/bin/initdb"))
    if not bins:
        yield
        return
    bindir = os.path.dirname(bins[-1])
    as_pg = []
    if os.geteuid() == 0:                       # initdb refuses root: run as `postgres`
        import pwd

        try:
            pwd.getpwnam("postgres")
        except KeyError:
            yield
            return
        as_pg = ["runuser", "-u", "postgres", "--"]
    base = tempfile.mkdtemp(prefix="codex-v0-pg-", dir="/tmp")  # postgres must reach it
    os.chmod(base, 0o755)
    if as_pg:
        shutil.chown(base, user="postgres")
    data = os.path.join(base, "data")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    started = False
    saved = {k: os.environ.get(k) for k in ("CODEX_V0_TEST_DATABASE_URL",
                                            "CODEX_V0_DISPOSABLE_DATABASE")}
    try:
        run = lambda *a: subprocess.run(as_pg + list(a), check=True, capture_output=True,  # noqa: E731
                                        timeout=120)
        run(f"{bindir}/initdb", "-D", data, "-A", "trust", "-U", "postgres")
        started = True   # before start: a start that times out may still leave a postmaster
        run(f"{bindir}/pg_ctl", "-D", data, "-w", "-l", os.path.join(base, "log"), "-o",
            f"-c listen_addresses=127.0.0.1 -c port={port} -c unix_socket_directories={base}",
            "start")
        run(f"{bindir}/createdb", "-h", "127.0.0.1", "-p", str(port), "-U", "postgres",
            "codex_v0_budget_test")
        os.environ["CODEX_V0_TEST_DATABASE_URL"] = (
            f"postgresql://postgres@127.0.0.1:{port}/codex_v0_budget_test")
        os.environ["CODEX_V0_DISPOSABLE_DATABASE"] = "yes"
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if started:
            subprocess.run(as_pg + [f"{bindir}/pg_ctl", "-D", data, "-m", "immediate", "-w",
                                    "stop"], capture_output=True, timeout=120)
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    # Repo convention (review U7 F2): no pytest. SKIP exits 0 when no disposable local
    # PostgreSQL database is supplied or can be made; anything else is a failure.
    try:
        with _disposable_cluster():
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
