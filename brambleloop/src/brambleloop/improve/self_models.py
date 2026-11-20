"""Durable state of the self-improvement team (ENG-IMPROVE, owner directive 2026-11-20).

Four tables, registered by `core.db.Database.register_models` so every process creates them at
boot (tests/test_w4_integ3_boot_tables.py):

* `si_policy_values`   -- the champion value of each declared tunable key, with the version,
                          the previous value and the challenger that put it there.
* `si_challengers`     -- one champion/challenger trial of one tunable key: its share cap, its
                          spend cap, its state and the evidence each decision was taken on.
* `si_observations`    -- one unit of work judged under one arm. Unique per (trial, unit), so a
                          unit replayed or re-recorded is never counted twice.
* `engineering_change_requests` -- a lesson that needs a code change, filed by the team and
                          tracked FILED -> BUILDING -> REVIEWED -> DEPLOYED -> VERIFIED (or
                          REOPENED). Production never edits code: these rows are the request.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow


class PolicyValue(Base):
    __tablename__ = "si_policy_values"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)        # {"v": <value>}
    previous: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(80), default="default")


class Challenger(Base):
    __tablename__ = "si_challengers"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    department: Mapped[str] = mapped_column(String(40), index=True)
    key: Mapped[str] = mapped_column(String(80), index=True)
    champion_value: Mapped[dict] = mapped_column(JSON, default=dict)
    challenger_value: Mapped[dict] = mapped_column(JSON, default=dict)
    share: Mapped[float] = mapped_column(Float, default=0.1)
    spend_cap_cad: Mapped[float] = mapped_column(Float, default=0.0)
    state: Mapped[str] = mapped_column(String(20), default="RUNNING", index=True)
    proposed_by: Mapped[str] = mapped_column(String(64), default="")
    lesson_ref: Mapped[str] = mapped_column(String(200), default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                            nullable=True)
    history: Mapped[list] = mapped_column(JSON, default=list)


class Observation(Base):
    __tablename__ = "si_observations"
    __table_args__ = (UniqueConstraint("challenger_id", "phase", "unit",
                                       name="uq_si_observation_unit"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    challenger_id: Mapped[int] = mapped_column(Integer, index=True)
    # "trial" while the challenger runs; "watch" after promotion, against the holdback.
    phase: Mapped[str] = mapped_column(String(10), default="trial")
    arm: Mapped[str] = mapped_column(String(12))                 # champion | challenger
    unit: Mapped[str] = mapped_column(String(120))
    success: Mapped[bool] = mapped_column(Boolean)
    cost_cad: Mapped[float] = mapped_column(Float, default=0.0)
    ref: Mapped[str] = mapped_column(String(200), default="")


class EngineeringChangeRequest(Base):
    __tablename__ = "engineering_change_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    defect_class: Mapped[str] = mapped_column(String(60), index=True)
    department: Mapped[str] = mapped_column(String(40), index=True)
    module: Mapped[str] = mapped_column(String(160), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    problem: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)   # rows, counts, examples
    proposed_change: Mapped[str] = mapped_column(Text, default="")
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    priority: Mapped[str] = mapped_column(String(4), default="P2", index=True)
    expected_kpi_gain: Mapped[dict] = mapped_column(JSON, default=dict)
    related: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(12), default="FILED", index=True)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    filed_by: Mapped[str] = mapped_column(String(64), default="")
    kpi_baseline: Mapped[dict] = mapped_column(JSON, default=dict)
    deployed_commit: Mapped[str] = mapped_column(String(64), default="")
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    history: Mapped[list] = mapped_column(JSON, default=list)
