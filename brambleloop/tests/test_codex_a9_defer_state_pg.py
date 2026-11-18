"""Opt-in owner-action interleaving on an empty disposable PostgreSQL database."""
import sys  # noqa: E402  (review U6 H2: standalone/run_tests.sh import path)
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(_Path(__file__).resolve().parent))
import contextlib
import os
import sys

import _minipytest as pytest  # Review U6 H2: pytest is not a dependency; same runner everywhere
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
from brambleloop.core.models import Listing, PatternVersion, Product
import test_codex_a9_defer_state as suite


@contextlib.contextmanager
def _disposable_cluster():
    """Review of 56f92eb9 (same fix as A3 N1, the W6 `_disposable_cluster` pattern of
    test_codex_v0_postgres.py): with no BRAMBLELOOP_TEST_POSTGRES_URL supplied but a local
    PostgreSQL toolchain installed, make a brand-new throwaway cluster for this run only --
    TCP on 127.0.0.1, a free port, one fresh empty database -- and destroy it afterwards
    (`initdb -A trust`: fine in a single-tenant test container, never on a shared host). A
    supplied URL is always used as is; with no toolchain nothing is created and the test
    SKIPs, which the runner counts as no passes (never a silent pass)."""
    import glob
    import shutil
    import socket
    import subprocess
    import tempfile

    if os.environ.get("BRAMBLELOOP_TEST_POSTGRES_URL"):
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
    base = tempfile.mkdtemp(prefix="a9-defer-pg-", dir="/tmp")  # postgres must reach it
    os.chmod(base, 0o755)
    if as_pg:
        shutil.chown(base, user="postgres")
    data = os.path.join(base, "data")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    started = False
    keys = ("BRAMBLELOOP_TEST_POSTGRES_URL", "BRAMBLELOOP_CONFIRM_DISPOSABLE_POSTGRES")
    saved = {k: os.environ.get(k) for k in keys}
    try:
        run = lambda *a: subprocess.run(as_pg + list(a), check=True, capture_output=True,  # noqa: E731
                                        timeout=120)
        run(f"{bindir}/initdb", "-D", data, "-A", "trust", "-U", "postgres")
        started = True   # before start: a start that times out may still leave a postmaster
        run(f"{bindir}/pg_ctl", "-D", data, "-w", "-l", os.path.join(base, "log"), "-o",
            f"-c listen_addresses=127.0.0.1 -c port={port} -c unix_socket_directories={base}",
            "start")
        run(f"{bindir}/createdb", "-h", "127.0.0.1", "-p", str(port), "-U", "postgres",
            "codex_a9_defer_test")
        os.environ["BRAMBLELOOP_TEST_POSTGRES_URL"] = (
            f"postgresql://postgres@127.0.0.1:{port}/codex_a9_defer_test")
        os.environ["BRAMBLELOOP_CONFIRM_DISPOSABLE_POSTGRES"] = "1"
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
    # Review U6 H2. With no supplied database it makes its own disposable cluster when a
    # local PostgreSQL toolchain exists; only without one does it print SKIP and exit 0 (the
    # harness then reports a suite with no passes: UNKNOWN, not PASS).
    import traceback

    import _minipytest

    mp = _minipytest.MonkeyPatch()
    name = "test_source_change_then_defer_rechecks_on_postgresql"
    try:
        with _disposable_cluster():
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
