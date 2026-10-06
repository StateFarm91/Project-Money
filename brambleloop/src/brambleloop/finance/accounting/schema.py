"""Database adapter and table registration for the accounting package.

The accounting tables live in `accounting.models` (lane-owned) and are created here, on
first use, with `Base.metadata.create_all(tables=...)` -- additive and idempotent. The
integrator should also import `accounting.models` from `core.db.Database.create_all` (a
WIRING REQUEST in handoff_E.md) so a deploy creates them up front; this keeps the package
working before and after that wiring.

The provider contract says `summary(db)` receives "db"; the rest of the codebase passes a
`core.db.Database` (with a `.session()` context manager). `as_db` accepts either a
`Database` or a bare SQLAlchemy `Session` and returns something with `.session()`.
"""
from __future__ import annotations

from contextlib import contextmanager

_FLAG = "_brambleloop_accounting_tables"


class _SessionDB:
    """A `Database`-shaped wrapper over one caller-owned Session (flush, never commit)."""

    def __init__(self, session):
        self._s = session
        self.engine = session.get_bind()

    @contextmanager
    def session(self):
        yield self._s
        self._s.flush()


def as_db(db):
    from sqlalchemy.orm import Session

    if isinstance(db, Session):
        return _SessionDB(db)
    return db


def ensure(db):
    """Create the accounting tables if missing. Returns the adapted db."""
    db = as_db(db)
    engine = getattr(db, "engine", None)
    if engine is None:
        return db
    if getattr(engine, _FLAG, False):
        return db
    from ...core.db import Base
    from . import models

    Base.metadata.create_all(engine, tables=[t.__table__ for t in models.TABLES])
    try:
        setattr(engine, _FLAG, True)
    except Exception:  # noqa: BLE001 - an engine that refuses attributes just re-checks
        pass
    return db
