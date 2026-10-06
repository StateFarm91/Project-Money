"""Durable record of the owner's business conversations with Laura (W3 lane F).

`laura_cc_turns` holds one row per question the owner asked Laura in the Command Center:
the question, the intent it was routed to, the answer exactly as shown, every fact with its
source, the follow-on proposals Laura offered, and how the answer was produced (deterministic
template, or a gateway rephrasing that passed the fact-preservation check). It is the
"meaningful interactions" part of Laura's durable history (D-FB-13) and survives restarts,
deploys and model swaps because the conversation lives here, not in a model's context.

`laura_cc_followons` holds every follow-on Laura created from a conversation: the stored
proposal it came from, what it became (a GREEN mission's job, or an owner action for
protected work) and who confirmed it.

Business register only. This module never stores, reads or exposes the owner-only private
register (spec/07, lane E's private tier); there is no column for it and no code path to it.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base
from ...core.models import utcnow

REGISTER = "business"


class LauraTurn(Base):
    __tablename__ = "laura_cc_turns"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    register: Mapped[str] = mapped_column(String(20), default=REGISTER)
    session_public_id: Mapped[str] = mapped_column(String(40), default="", index=True)
    question: Mapped[str] = mapped_column(Text, default="")
    intent: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    status: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    answer: Mapped[str] = mapped_column(Text, default="")
    facts: Mapped[list] = mapped_column(JSON, default=list)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    unknowns: Mapped[list] = mapped_column(JSON, default=list)
    proposals: Mapped[list] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(200), default="")
    identity_id: Mapped[str] = mapped_column(String(80), default="")


class LauraFollowOn(Base):
    __tablename__ = "laura_cc_followons"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    turn_id: Mapped[int] = mapped_column(Integer, index=True)
    proposal_key: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))           # mission | owner_action
    department: Mapped[str] = mapped_column(String(40), default="")
    job_type: Mapped[str] = mapped_column(String(80), default="")
    result_ref: Mapped[str] = mapped_column(String(200), default="")
    confirmed_by: Mapped[str] = mapped_column(String(80), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class LauraVoiceIdentity(Base):
    """The durable Laura Voice identity (D-FB-18 item 7): one row per owner-selected voice
    version, hash-chained. Provider-independent descriptors + the hash of the reference samples
    the owner heard; the provider/voice that rendered them is recorded as the current
    instrument, not as her identity. Written only by `voice_selection.select`."""

    __tablename__ = "laura_voice_identity"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    spec_id: Mapped[str] = mapped_column(String(40))
    spec_sha256: Mapped[str] = mapped_column(String(64))
    owner_decision_id: Mapped[str] = mapped_column(String(40))
    reference_samples_sha256: Mapped[str] = mapped_column(String(64))
    record: Mapped[dict] = mapped_column(JSON, default=dict)
    record_sha256: Mapped[str] = mapped_column(String(64))
    prev_sha256: Mapped[str] = mapped_column(String(64), default="")


TABLES = (LauraTurn.__table__, LauraFollowOn.__table__, LauraVoiceIdentity.__table__)
_ENSURED: set[int] = set()


def ensure_tables(db) -> None:
    """Create these tables on `db` if missing (idempotent, additive only)."""
    key = id(db.engine)
    if key in _ENSURED:
        return
    Base.metadata.create_all(db.engine, tables=list(TABLES))
    _ENSURED.add(key)
