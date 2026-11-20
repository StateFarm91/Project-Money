"""Tables owned by the authority package.

* `authority_policies` -- the owner's recorded grants (F-703). Append-mostly: a grant is
  revoked by setting `revoked_at`, never deleted, so the ladder's history is auditable.
* `company_work_items` -- the durable company work DAG (F-658, F-702, F-721).

Registration: `core.db.Database.create_all` imports the modules whose tables it creates. Until
the integrator wires this module there (WIRING REQUEST in handoff_K11.md), `ensure_tables`
creates both tables on first use, idempotently (`checkfirst`), the `autonomy.models` pattern.
"""
from __future__ import annotations

import threading
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow


class AuthorityPolicy(Base):
    __tablename__ = "authority_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    agent: Mapped[str] = mapped_column(String(64), index=True)
    action_class: Mapped[str] = mapped_column(String(32), index=True)
    # Empty = every job type of the class for this agent.
    job_type: Mapped[str] = mapped_column(String(80), default="")
    level: Mapped[str] = mapped_column(String(20), default="owner_each")
    max_per_day: Mapped[int] = mapped_column(Integer, default=0)
    max_cost_cad: Mapped[float] = mapped_column(Float, default=0.0)
    granted_by: Mapped[str] = mapped_column(String(64))
    owner_decision_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, default="")
    # The measured safe history the grant was made on (F-703), frozen at grant time.
    safe_history: Mapped[dict] = mapped_column(JSON, default=dict)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                        nullable=True)
    revoked_by: Mapped[str] = mapped_column(String(64), default="")


class WorkItem(Base):
    __tablename__ = "company_work_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(200))
    department: Mapped[str] = mapped_column(String(40), default="", index=True)
    job_type: Mapped[str] = mapped_column(String(80))
    action_class: Mapped[str] = mapped_column(String(32), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    # Ownership: the department that owns the outcome and the agent that executes it.
    owner_agent: Mapped[str] = mapped_column(String(64), default="")
    submitted_by: Mapped[str] = mapped_column(String(64), default="")
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str] = mapped_column(String(64), default="")
    approval_ref: Mapped[str] = mapped_column(String(120), default="")
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Completion evidence: the job row, its terminal status and what it reported.
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("key", name="uq_company_work_items_key"),)


_LOCK = threading.Lock()
_FLAG = "_brambleloop_authority_tables"


def ensure_tables(db) -> None:
    engine = db.engine
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if getattr(engine, _FLAG, False):
            return
        Base.metadata.create_all(engine, tables=[AuthorityPolicy.__table__,
                                                 WorkItem.__table__], checkfirst=True)
        setattr(engine, _FLAG, True)
