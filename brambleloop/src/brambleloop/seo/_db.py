"""Accept either the repo's `Database` wrapper or a bare SQLAlchemy `Session`.

Every reader in this codebase takes `core.db.Database` and opens `db.session()`. The v1.1
provider contract says "db = SQLAlchemy Session". Both are accepted here so a caller holding
either gets the same answer; with a bare Session the caller owns the transaction, so this
module flushes but never commits it.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session


def is_session(db) -> bool:
    return isinstance(db, Session)


@contextmanager
def session(db) -> Iterator[Session]:
    if is_session(db):
        yield db
        db.flush()
        return
    with db.session() as s:
        yield s


def engine(db):
    return db.get_bind() if is_session(db) else db.engine


class _Wrapped:
    """A `Database`-shaped view of a bare Session, for repo readers that call `db.session()`."""

    def __init__(self, s: Session):
        self._s = s
        self.engine = s.get_bind()

    @contextmanager
    def session(self) -> Iterator[Session]:
        yield self._s
        self._s.flush()


def as_database(db):
    return _Wrapped(db) if is_session(db) else db
