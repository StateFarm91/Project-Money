"""Tables for the private context, on their OWN metadata (not `core.db.Base`).

Deliberately not registered on `core.db.Base`: the continuity export, `counts_by_table`, the
generic `create_all` and every reader that walks `Base.metadata` therefore never see these
tables, so private ciphertext is not copied into ordinary export bundles. `ensure_tables`
creates them on first use. An owner-held sealed backup exists separately
(`store.sealed_export`, ciphertext only).

Nothing in these tables is plaintext content:

* `laura_private_entries` -- one row per fact or interaction turn. Content (the text, the
  fact's key, the turn's role, the model reference, cited sources) is inside `ciphertext`.
  Plain columns are random ids, fixed vocabulary, HMAC blind indexes and timestamps, and all
  of them are bound into the AES-GCM associated data.
* `laura_private_grants` -- explicit private-context grants on owner sessions.
* `laura_private_access` -- the private context's own access log: operation, outcome, a
  fixed reason code, the principal's type name. Never content, never ids of content.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class PrivateBase(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PrivateGrant(PrivateBase):
    __tablename__ = "laura_private_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grant_id: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    session_public_id: Mapped[str] = mapped_column(String(40), index=True)
    key_id: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str] = mapped_column(String(40), default="")


class PrivateEntry(PrivateBase):
    __tablename__ = "laura_private_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(8), index=True)            # fact | turn
    provenance: Mapped[str] = mapped_column(String(16))                 # owner_supplied | interaction
    key_index: Mapped[str] = mapped_column(String(64), index=True)      # HMAC blind index
    grant_ref: Mapped[str] = mapped_column(String(64), index=True)      # HMAC of the grant id
    reply_to: Mapped[str | None] = mapped_column(String(48), unique=True, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))                 # ISO 8601 UTC
    key_id: Mapped[str] = mapped_column(String(16))
    scheme: Mapped[str] = mapped_column(String(16))
    nonce: Mapped[str] = mapped_column(String(24))
    ciphertext: Mapped[str] = mapped_column(Text)


class PrivateAccess(PrivateBase):
    __tablename__ = "laura_private_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    op: Mapped[str] = mapped_column(String(24))
    outcome: Mapped[str] = mapped_column(String(8))                     # ok | refused
    reason: Mapped[str] = mapped_column(String(40), default="")
    principal_type: Mapped[str] = mapped_column(String(40), default="")


TABLES = tuple(PrivateBase.metadata.tables)


def ensure_tables(db) -> None:
    PrivateBase.metadata.create_all(db.engine)
