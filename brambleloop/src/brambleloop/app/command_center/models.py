"""Owner Command Center tables (v1.1 lane C).

Defined on the shared `Base` so `Base.metadata.create_all` creates them wherever this module has
been imported (the app imports it at mount time). `ensure_tables` creates just these tables on
an existing database, so the command center works before a shared-registration wiring change.

* `cc_owner_sessions` -- owner browser sessions. Only a SHA-256 of the cookie token is stored;
  a database read never yields a usable session.
* `cc_nonces` -- one row per accepted mutating request nonce (replay protection, F-887).
* `cc_security_events` -- append-only audit of authentication outcomes and every refused
  attempt (F-887 "audit of refused attempts"). Kept apart from `audit_log` on purpose: a
  refused request must not change the company's operational audit trail (the default-deny
  test fingerprints it), but it must leave a trace the owner can read.
* `cc_notifications` -- the owner's in-app notifications, deduplicated on `dedupe_key`.
* `cc_kv` -- small owner preferences (notification policy, last-viewed marker).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base
from ...core.models import utcnow


class OwnerSession(Base):
    __tablename__ = "cc_owner_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    device_label: Mapped[str] = mapped_column(String(80), default="")
    client_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stepup_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                          nullable=True)
    failed_stepups: Mapped[int] = mapped_column(Integer, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str] = mapped_column(String(200), default="")


class RequestNonce(Base):
    __tablename__ = "cc_nonces"

    id: Mapped[int] = mapped_column(primary_key=True)
    nonce: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    session_public_id: Mapped[str] = mapped_column(String(40), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SecurityEvent(Base):
    __tablename__ = "cc_security_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    outcome: Mapped[str] = mapped_column(String(16), index=True)  # "refused" | "ok"
    method: Mapped[str] = mapped_column(String(8), default="")
    route: Mapped[str] = mapped_column(String(200), default="")
    reason: Mapped[str] = mapped_column(String(300), default="")
    session_public_id: Mapped[str] = mapped_column(String(40), default="", index=True)
    client_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class Notification(Base):
    __tablename__ = "cc_notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(200), index=True)
    severity: Mapped[str] = mapped_column(String(12), index=True)
    category: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    consequence: Mapped[str] = mapped_column(Text, default="")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    deep_link: Mapped[str] = mapped_column(String(300), default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                   index=True)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                         nullable=True)

    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_cc_notification_key"),)


class KeyValue(Base):
    __tablename__ = "cc_kv"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


TABLES = (OwnerSession.__table__, RequestNonce.__table__, SecurityEvent.__table__,
          Notification.__table__, KeyValue.__table__)

_ENSURED: set[int] = set()


def ensure_tables(db) -> None:
    """Create the command center's tables on `db` if missing (idempotent, additive only)."""
    key = id(db.engine)
    if key in _ENSURED:
        return
    Base.metadata.create_all(db.engine, tables=list(TABLES))
    _ENSURED.add(key)


def kv_get(session, key: str, default=None):
    from sqlalchemy import select

    row = session.scalar(select(KeyValue).where(KeyValue.key == key))
    import copy

    return copy.deepcopy(dict(row.value)) if row is not None else default


def kv_set(session, key: str, value: dict) -> None:
    import copy

    from sqlalchemy import select

    row = session.scalar(select(KeyValue).where(KeyValue.key == key))
    if row is None:
        session.add(KeyValue(key=key, value=dict(value), updated_at=utcnow()))
    else:
        row.value = copy.deepcopy(dict(value))
        row.updated_at = utcnow()
