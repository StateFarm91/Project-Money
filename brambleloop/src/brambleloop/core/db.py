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


def make_engine(url: str | None = None, echo: bool = False) -> Engine:
    url = url or os.environ.get("BRAMBLELOOP_DATABASE_URL", DEFAULT_URL)
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

    def create_all(self) -> None:
        from . import models  # noqa: F401  (import registers the mappings)

        Base.metadata.create_all(self.engine)

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
