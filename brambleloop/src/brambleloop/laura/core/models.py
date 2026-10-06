"""Laura's durable state (wave 3 lane D): identity versions, priorities, decisions, challenges.

Four additive tables. None holds anything that exists only inside a model's context window;
together with `laura.core.identity.GENESIS` they ARE Laura, whichever model provides the
cognition on a given day.

* `laura_identity_versions` -- the canonical identity record, append-only and hash-chained.
  Version 1 is the genesis record from code; any later version needs a recorded owner decision
  (`identity.amend`). ORM updates and deletes are refused outright.
* `laura_priorities` -- her current and past priorities, each with a reason and the durable
  rows it was derived from. Keyed (upsert), so a re-run tick changes nothing.
* `laura_decisions` -- her history: real actions only (a priority set or closed, a
  delegation, a review of a department's result, a challenge, a constitutional block, an
  escalation). Append-only, keyed for idempotency; ORM updates and deletes are refused.
* `laura_challenges` -- a Finance / Product Truth / Security objection against her work. Only
  the raising department or the owner may resolve one; Laura cannot.

Registration: `core.db.Database.create_all` imports this module; `ensure_tables` also creates
the tables lazily (checkfirst), so a process that never called create_all still works.
"""
from __future__ import annotations

import threading
from datetime import datetime

from sqlalchemy import (JSON, Boolean, DateTime, Float, Integer, String, Text,
                        UniqueConstraint, event)
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base
from ...core.models import utcnow


class LauraIdentityVersion(Base):
    __tablename__ = "laura_identity_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    record: Mapped[dict] = mapped_column(JSON, default=dict)
    sha256: Mapped[str] = mapped_column(String(64))
    prev_sha256: Mapped[str] = mapped_column(String(64), default="")
    owner_decision_id: Mapped[str] = mapped_column(String(40), default="")
    actor: Mapped[str] = mapped_column(String(40), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("version", name="uq_laura_identity_version"),)


class LauraPriority(Base):
    __tablename__ = "laura_priorities"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(200))
    rule: Mapped[str] = mapped_column(String(40), index=True)
    department: Mapped[str] = mapped_column(String(40), default="", index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    evidence_fp: Mapped[str] = mapped_column(String(32), default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    # open | delegated | blocked | awaiting_owner | closed
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    job_type: Mapped[str] = mapped_column(String(80), default="")
    mission_key: Mapped[str] = mapped_column(String(200), default="")
    constitution: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_reason: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (UniqueConstraint("key", name="uq_laura_priority_key"),)


class LauraDecision(Base):
    __tablename__ = "laura_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(200))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    # priority.set | priority.closed | delegation | review | challenge | rework |
    # blocked | owner_action | escalation
    kind: Mapped[str] = mapped_column(String(30), index=True)
    department: Mapped[str] = mapped_column(String(40), default="", index=True)
    subject: Mapped[str] = mapped_column(String(300), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    refs: Mapped[list] = mapped_column(JSON, default=list)
    # Which cognition produced the decision ("deterministic" today). Recorded so a model swap
    # is visible in her history -- and so it is visible that a swap changed nothing else.
    cognition: Mapped[dict] = mapped_column(JSON, default=dict)
    identity_sha256: Mapped[str] = mapped_column(String(64), default="")

    __table_args__ = (UniqueConstraint("key", name="uq_laura_decision_key"),)


class LauraChallenge(Base):
    __tablename__ = "laura_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    raised_by: Mapped[str] = mapped_column(String(20), index=True)   # finance|product_truth|security
    # Scope of the objection: {"department": x} | {"job_type": y} | {} (all of her work).
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_by: Mapped[str] = mapped_column(String(20), default="")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str] = mapped_column(Text, default="")


TABLES = (LauraIdentityVersion, LauraPriority, LauraDecision, LauraChallenge)


class ImmutableRecordError(RuntimeError):
    """An attempt to edit or delete Laura's identity history or decision history."""


def _refuse(kind: str):
    def _listener(_mapper, _conn, target):
        raise ImmutableRecordError(
            f"{type(target).__name__} {getattr(target, 'id', '?')}: Laura's identity and "
            f"decision history are append-only ({kind} refused). An identity change is a new "
            f"version authorised by a recorded owner decision.")
    return _listener


for _cls in (LauraIdentityVersion, LauraDecision):
    event.listen(_cls, "before_update", _refuse("update"))
    event.listen(_cls, "before_delete", _refuse("delete"))


_LOCK = threading.Lock()
_FLAG = "_brambleloop_laura_core_tables"


def ensure_tables(db) -> None:
    """Create Laura's tables if absent; idempotent, flag held on the engine object."""
    engine = db.engine
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if getattr(engine, _FLAG, False):
            return
        Base.metadata.create_all(engine, tables=[t.__table__ for t in TABLES], checkfirst=True)
        setattr(engine, _FLAG, True)
