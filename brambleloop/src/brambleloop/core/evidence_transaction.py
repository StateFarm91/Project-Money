"""Bounded database transaction retry; this is not an evidence gate.

Callbacks must only perform database work, never commit or cause external
effects, and must revalidate evidence and authority on every attempt.
Separate invocations still require durable application idempotency.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy import event
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

T = TypeVar("T")
_RETRYABLE = frozenset({"40001", "40P01", "55P03"})


def run_db_transaction(
    session_factory: Callable[[], Session],
    operation: Callable[[Session], T],
    *,
    max_attempts: int = 3,
    delay_seconds: float = 0.025,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Retry definitive PostgreSQL concurrency failures in fresh transactions.

    Unknown outcomes and disconnected sessions are not retried. Callbacks must
    not commit, swallow DB failures, or perform I/O outside the database.
    """
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 5:
        raise ValueError("max_attempts must be an integer from 1 to 5")
    if not isinstance(delay_seconds, (int, float)) or isinstance(delay_seconds, bool) or not 0 <= delay_seconds <= 1:
        raise ValueError("delay_seconds must be between 0 and 1")
    for attempt in range(max_attempts):
        try:
            with session_factory() as session:
                state = {"commit_allowed": False}

                @event.listens_for(session, "before_commit")
                def guard_commit(_session):
                    if not state["commit_allowed"]:
                        raise RuntimeError("operation must not commit its transaction")

                with session.begin():
                    connection = session.connection()

                    @event.listens_for(connection, "commit")
                    def guard_connection_commit(_connection):
                        if not state["commit_allowed"]:
                            raise RuntimeError("operation must not commit its transaction")

                    result = operation(session)
                    if not session.in_transaction():
                        raise RuntimeError("operation ended its transaction")
                    state["commit_allowed"] = True
            return result
        except DBAPIError as error:
            code = getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)
            if error.connection_invalidated or code not in _RETRYABLE or attempt + 1 == max_attempts:
                raise
            sleep(delay_seconds * (attempt + 1))
    raise AssertionError("unreachable")
