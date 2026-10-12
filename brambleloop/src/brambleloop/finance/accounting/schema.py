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
    """A `Database`-shaped wrapper over one caller-owned Session (flush, never commit).

    W4-FINHEALTH (production `PendingRollbackError`): this wrapper used to yield the shared
    session with no failure handling at all. When a block inside it failed at flush -- on
    Postgres that includes a `varchar(n)` overflow SQLite never enforces -- the session was
    left in SQLAlchemy's "rollback required" state, and the caller that caught the failure
    and carried on (`dashboard.summary` records "posting refresh failed" and then reads the
    books) died on its very next query with `PendingRollbackError`. The owner then saw the
    whole Finance summary as "unavailable: PendingRollbackError" instead of the figures with
    the refresh failure named beside them.

    Now: if the block raises and the transaction can no longer be used -- SQLAlchemy has
    marked it inactive, or the database is Postgres and a DBAPI error has aborted the
    transaction server-side -- the session is rolled back before the exception continues.
    That loses nothing that was not already lost (both states discard the whole transaction;
    the only remaining move is `rollback()`), and it makes the session usable again for the
    caller that chose to continue. The exception is always re-raised: a failure is never
    swallowed here, and nothing is committed.
    """

    def __init__(self, session):
        self._s = session
        self.engine = session.get_bind()

    @contextmanager
    def session(self):
        try:
            yield self._s
            self._s.flush()
        except BaseException as exc:
            if _transaction_is_lost(self._s, exc):
                self._s.rollback()
            raise


def _transaction_is_lost(session, exc: BaseException) -> bool:
    """True when the session's transaction cannot be used again without a rollback."""
    from sqlalchemy.exc import DBAPIError

    if not session.is_active:  # flush failed: SQLAlchemy's PendingRollbackError state
        return True
    if isinstance(exc, DBAPIError):
        bind = session.get_bind()
        # Postgres aborts the whole transaction on any statement error ("current
        # transaction is aborted, commands ignored until end of transaction block").
        return getattr(getattr(bind, "dialect", None), "name", "") == "postgresql"
    return False


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
