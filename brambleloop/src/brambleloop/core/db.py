"""Database layer.

Postgres in production, SQLite for hermetic tests (DECISION B-004). The queue's claim query
is the only place the two genuinely differ, and that difference is isolated in
`queue/durable.py`.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_URL = "sqlite:///brambleloop.db"


class Base(DeclarativeBase):
    pass


class EphemeralStorageRefused(RuntimeError):
    """A hosted deployment was about to run on storage that does not survive a restart."""


def resolve_url(url: str | None = None) -> str:
    """Pick the database URL, preferring an explicit one, then the platform's.

    Railway (and most platforms) inject `DATABASE_URL`, and inject it in the historical
    `postgres://` form that SQLAlchemy 2.x does not accept. Normalising it here rather than in
    a dashboard variable means the deployment cannot be broken by someone copying the value
    by hand.

    The refusal below matters more than it looks. Without it, a container whose database
    variable failed to bind falls back to a SQLite file on an ephemeral disk: every health
    check passes, the dashboard renders, and every job, audit record and release certificate
    is destroyed on the next restart. Failing to start is enormously preferable to running a
    company whose memory silently resets.
    """
    url = (url or os.environ.get("BRAMBLELOOP_DATABASE_URL")
           or os.environ.get("DATABASE_URL") or "").strip()
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    if not url:
        url = DEFAULT_URL
    if url.startswith("sqlite") and os.environ.get("BRAMBLELOOP_REQUIRE_POSTGRES") == "1":
        raise EphemeralStorageRefused(
            "BRAMBLELOOP_REQUIRE_POSTGRES=1 but no Postgres URL is bound. Refusing to start "
            "on ephemeral SQLite: the container would look healthy and lose every job, audit "
            "record and release certificate on its next restart."
        )
    return url


def make_engine(url: str | None = None, echo: bool = False) -> Engine:
    url = resolve_url(url)
    kwargs: dict = {"echo": echo, "future": True}
    if url.startswith("sqlite"):
        # check_same_thread=False so a worker thread can share the engine; WAL so a reader
        # does not block the queue writer.
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver glue
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return eng


def is_postgres(engine: Engine) -> bool:
    return engine.dialect.name == "postgresql"


class Database:
    def __init__(self, url: str | None = None, echo: bool = False):
        self.engine = make_engine(url, echo)
        self._sessions = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def create_all(self) -> list[str]:
        """Create missing tables, then add missing columns to the ones that exist.

        `create_all` alone does not touch a table that already exists, so a column added in
        code never reaches a deployed database. Returns what the additive migration changed,
        which the caller logs -- a schema change nobody can see is how a deploy breaks quietly.
        """
        from . import models  # noqa: F401  (import registers the mappings)
        from .migrate import apply as apply_migrations

        Base.metadata.create_all(self.engine)
        return apply_migrations(self.engine)

    def drop_all(self) -> None:
        Base.metadata.drop_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self._sessions()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def new_session(self) -> Session:
        return self._sessions()
