"""Shared fixtures for tests/test_w3_laura_memory_*.py (not a suite itself)."""
from __future__ import annotations

import secrets
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402

FAILS = 0
TMPDIRS: list[tempfile.TemporaryDirectory] = []


def check(name: str, fn) -> None:
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as exc:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


def _pg_name(path: str | None) -> str:
    import hashlib

    return "w3e_" + (hashlib.sha1(path.encode()).hexdigest()[:16] if path
                     else secrets.token_hex(8))


def _pg_url(name: str) -> str:
    import os

    from sqlalchemy.engine import make_url

    return make_url(os.environ["BRAMBLELOOP_TEST_PG_ADMIN_URL"]).set(
        database=name).render_as_string(hide_password=False)


def _pg_db(path: str | None) -> Database:
    """Opt-in (W4-PRIVLAURA, G-11): with BRAMBLELOOP_TEST_PG_ADMIN_URL set to a THROWAWAY local
    Postgres admin URL, each fresh_db() is a new database there (the same `path` maps to the
    same database, so a "restart" reopens it). Unset -- the default -- nothing changes."""
    import os

    from sqlalchemy import create_engine, text

    admin = os.environ["BRAMBLELOOP_TEST_PG_ADMIN_URL"]
    name = _pg_name(path)
    eng = create_engine(admin, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        if not c.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"),
                         {"n": name}).scalar():
            c.execute(text(f'CREATE DATABASE "{name}"'))
    eng.dispose()
    db = Database(_pg_url(name))
    db.create_all()
    with db.engine.connect() as c:          # WAL written for this store starts here
        db._w3_wal_start = str(c.execute(text("SELECT pg_current_wal_lsn()")).scalar())
    return db


def fresh_db(path: str | None = None) -> Database:
    import os

    if os.environ.get("BRAMBLELOOP_TEST_PG_ADMIN_URL"):
        return _pg_db(path)
    if path is None:
        td = tempfile.TemporaryDirectory(prefix="w3e-mem-")
        TMPDIRS.append(td)
        path = f"{td.name}/t.sqlite"
    db = Database(f"sqlite:///{path}")
    db.create_all()
    return db


def store_url(path: str) -> str:
    """The database URL of the store `fresh_db(path)` creates (for a child process)."""
    import os

    if os.environ.get("BRAMBLELOOP_TEST_PG_ADMIN_URL"):
        return _pg_url(_pg_name(path))
    return f"sqlite:///{path}"


def reopen(path: str) -> Database:
    """A NEW engine on an existing store (a "process restart"): no create_all, same data.
    SQLite: the same file. Postgres (opt-in): the database `fresh_db(path)` created."""
    import os

    if os.environ.get("BRAMBLELOOP_TEST_PG_ADMIN_URL"):
        return Database(_pg_url(_pg_name(path)))
    return Database(f"sqlite:///{path}")


def raw_storage_bytes(db) -> bytes:
    """Every byte the database has written to disk for this store, after a flush to the main
    files -- the "at rest" bytes, per dialect. SQLite: the database file plus -wal/-shm after a
    WAL checkpoint. Postgres: CHECKPOINT, then every relation file of this database under
    `base/<oid>/` plus the cluster WAL (`pg_wal/`). Needs a local throwaway cluster readable by
    the test process (the opt-in harness)."""
    from sqlalchemy import text

    if db.engine.dialect.name == "sqlite":
        path = Path(db.engine.url.database)
        with db.engine.connect() as c:          # flush WAL into the main file
            c.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        blob = path.read_bytes()
        for extra in (path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
            if extra.exists():
                blob += extra.read_bytes()
        return blob
    if db.engine.dialect.name == "postgresql":
        # The WAL is cluster-wide, so only the WAL written since this store was created is
        # read (other databases in the throwaway cluster are other tests' data, not this one's).
        start = getattr(db, "_w3_wal_start", None)
        assert start, "a Postgres store must come from fresh_db() to know its WAL start"
        with db.engine.connect() as c:
            c.execute(text("CHECKPOINT"))
            data_dir = Path(c.execute(text("SHOW data_directory")).scalar())
            oid = c.execute(text("SELECT oid FROM pg_database WHERE datname = "
                                 "current_database()")).scalar()
            end = str(c.execute(text("SELECT pg_current_wal_lsn()")).scalar())
            f0, o0 = c.execute(text("SELECT file_name, file_offset FROM "
                                    "pg_walfile_name_offset(CAST(:l AS pg_lsn))"),
                               {"l": start}).one()
            f1, o1 = c.execute(text("SELECT file_name, file_offset FROM "
                                    "pg_walfile_name_offset(CAST(:l AS pg_lsn))"),
                               {"l": end}).one()
        rel = [f for f in sorted((data_dir / "base" / str(oid)).rglob("*")) if f.is_file()]
        assert rel, "no relation files found"
        wal_dir = data_dir / "pg_wal"
        segs = sorted(p.name for p in wal_dir.iterdir()
                      if p.is_file() and len(p.name) == 24 and f0 <= p.name <= f1)
        assert segs and segs[0] == f0, (segs[:2], f0)
        wal = b""
        for name in segs:
            data = (wal_dir / name).read_bytes()
            lo = o0 if name == f0 else 0
            hi = o1 if name == f1 else len(data)
            wal += data[lo:hi]
        return b"".join(f.read_bytes() for f in rel) + wal
    raise AssertionError(f"no at-rest reader for dialect {db.engine.dialect.name!r}")


def owner_session(db, *, expired: bool = False, revoked: bool = False) -> str:
    from brambleloop.app.command_center.models import OwnerSession

    now = datetime.now(timezone.utc)
    pid = "s_" + secrets.token_hex(8)
    with db.session() as s:
        s.add(OwnerSession(public_id=pid, token_hash=secrets.token_hex(32),
                           device_label="test", created_at=now, last_seen_at=now,
                           expires_at=now + (timedelta(hours=-1) if expired
                                             else timedelta(hours=8)),
                           revoked_at=now if revoked else None,
                           revoked_reason="test" if revoked else ""))
    return pid


def raises(exc_type, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except exc_type as e:
        return e
    raise AssertionError(f"expected {exc_type.__name__}")


def finish() -> None:
    for td in TMPDIRS:
        td.cleanup()
    if FAILS:
        print(f"{FAILS} FAILED")
        sys.exit(1)
