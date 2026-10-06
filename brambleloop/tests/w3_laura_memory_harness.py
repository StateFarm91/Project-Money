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


def fresh_db(path: str | None = None) -> Database:
    if path is None:
        td = tempfile.TemporaryDirectory(prefix="w3e-mem-")
        TMPDIRS.append(td)
        path = f"{td.name}/t.sqlite"
    db = Database(f"sqlite:///{path}")
    db.create_all()
    return db


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
