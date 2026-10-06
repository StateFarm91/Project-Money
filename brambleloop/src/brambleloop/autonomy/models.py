"""Durable company memory and company timeline (F-920, F-927).

Two additive tables, owned by the autonomy package:

* `company_memory` -- keyed, source-linked operational memory: missions the orchestrator
  created and what they produced, department KPI snapshots, lessons, morning briefs,
  department blocks. Keyed so a write is an upsert: a worker that dies after writing and is
  re-run on reclaim writes the same row again instead of a second one.
* `company_timeline` -- an append-only chronological record of significant autonomous
  actions. Keyed too: the same event recorded twice (a re-run after a reclaimed lease) is one
  row.

Neither table holds anything that exists only inside a model's context window; every row
names the rows it was derived from (`sources` / `refs`).

Registration: `core.db.Database.create_all` imports the modules whose tables it creates.
Until the integrator wires this module there (WIRING REQUEST in handoff_A.md), `ensure_tables`
creates these two tables on first use, idempotently (`checkfirst`).
"""
from __future__ import annotations

import threading
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow


class CompanyMemory(Base):
    __tablename__ = "company_memory"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40), index=True)
    department: Mapped[str] = mapped_column(String(40), default="", index=True)
    subject: Mapped[str] = mapped_column(String(200), default="")
    state: Mapped[str] = mapped_column(String(30), default="", index=True)
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    # Provenance strings: "jobs:123", "pattern_versions:7", "company_memory:kpi:...".
    sources: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("key", name="uq_company_memory_key"),)


class TimelineEvent(Base):
    __tablename__ = "company_timeline"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(200))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    department: Mapped[str] = mapped_column(String(40), default="", index=True)
    actor: Mapped[str] = mapped_column(String(64), default="")
    severity: Mapped[str] = mapped_column(String(10), default="info")
    summary: Mapped[str] = mapped_column(Text, default="")
    refs: Mapped[list] = mapped_column(JSON, default=list)
    seq: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("key", name="uq_company_timeline_key"),)


_LOCK = threading.Lock()
_FLAG = "_brambleloop_autonomy_tables"


def ensure_tables(db) -> None:
    """Create the two autonomy tables if absent. Idempotent and cheap after the first call.

    The flag lives on the engine object itself (not an id() cache, which a garbage-collected
    engine's successor could reuse)."""
    engine = db.engine
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if getattr(engine, _FLAG, False):
            return
        Base.metadata.create_all(engine, tables=[CompanyMemory.__table__,
                                                 TimelineEvent.__table__], checkfirst=True)
        setattr(engine, _FLAG, True)
