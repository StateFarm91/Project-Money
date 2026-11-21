"""The learning department's durable store (ENG-LEARN).

These are additive tables, created on first use (checkfirst), using the same pattern as
`visual.image_records`.

* `learning_image_observations`: one row per judged image candidate (generated or recovered).
  It holds the structured features, every gate verdict, the failure reasons, cost and attempt.
  The row is keyed by the `image_candidates` id, so a harvest is idempotent.
* `learning_pattern_observations`: one row per engineering outcome (draft refusal, compile,
  certify). It holds the construction family, category, design parameters and defect codes,
  keyed by the source job id.
* `learning_arms`: the versioned prompt templates per scope (`family:role`). Each arm is a
  champion, a challenger, retired or demoted, and records why it exists.
* `learning_decisions`: every seed, promotion, demotion and retirement, with its evidence.
* `learning_derived_lessons`: lessons derived from the observations above an evidence threshold.
  Each records the bus lesson it was published as. Benchmark teardown lessons
  (`learning.benchmark_lessons`) are stored here too, as `loop == "benchmark"`.
* `learning_lesson_effects`: LEARN-PROOF. Each time a decision hook changed an output because
  of a stored lesson (`kind == "applied"`, one row per lesson, department and subject), and how
  often each hook ran at all (`kind == "evaluated"`). Applied without evaluated is impossible;
  evaluated without applied is an honest zero.

Nothing here is a model judgement. A row is a fact copied from a gate verdict or a job
outcome, or a count over such rows.
"""
from __future__ import annotations

import threading
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow


class ImageObservation(Base):
    __tablename__ = "learning_image_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    slug: Mapped[str] = mapped_column(String(80), index=True)
    family: Mapped[str] = mapped_column(String(40), index=True)
    role: Mapped[str] = mapped_column(String(40), index=True)
    method: Mapped[str] = mapped_column(String(20), default="")
    run_key: Mapped[str] = mapped_column(String(200), default="", index=True)
    prompt_version: Mapped[str] = mapped_column(String(80), default="", index=True)
    arm_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    references: Mapped[list] = mapped_column(JSON, default=list)
    gates: Mapped[dict] = mapped_column(JSON, default=dict)
    failures: Mapped[list] = mapped_column(JSON, default=list)
    outcome: Mapped[str] = mapped_column(String(20), default="unverified", index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    first_pass: Mapped[bool] = mapped_column(Boolean, default=False)
    cost_cad: Mapped[float | None] = mapped_column(Float, nullable=True)


class PatternObservation(Base):
    __tablename__ = "learning_pattern_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    slug: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[str] = mapped_column(String(20), default="")
    fingerprint: Mapped[str] = mapped_column(String(80), default="")
    stage: Mapped[str] = mapped_column(String(30), index=True)     # draft | compile | certify
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    family: Mapped[str] = mapped_column(String(40), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    codes: Mapped[list] = mapped_column(JSON, default=list)        # [{code, source}]
    revision: Mapped[int] = mapped_column(Integer, default=0)


class Arm(Base):
    __tablename__ = "learning_arms"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(100), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    digest: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), index=True)   # champion|challenger|retired|demoted
    source: Mapped[str] = mapped_column(String(120), default="")
    why: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_champion_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Decision(Base):
    __tablename__ = "learning_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    scope: Mapped[str] = mapped_column(String(100), index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)     # seed|promote|demote|retire
    arm_id: Mapped[int] = mapped_column(Integer)
    from_arm_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class DerivedLesson(Base):
    __tablename__ = "learning_derived_lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    loop: Mapped[str] = mapped_column(String(20), index=True)     # image | pattern | commerce
    key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    scope: Mapped[str] = mapped_column(String(100), index=True)
    direction: Mapped[int] = mapped_column(Integer, default=0)     # +1 prefer, -1 avoid
    statement: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    bus_lesson_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    applied: Mapped[int] = mapped_column(Integer, default=0)


class LessonEffect(Base):
    __tablename__ = "learning_lesson_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)        # applied | evaluated
    lesson_key: Mapped[str] = mapped_column(String(80), index=True)  # "" for evaluated
    department: Mapped[str] = mapped_column(String(40), index=True)
    hook: Mapped[str] = mapped_column(String(60), index=True)
    subject: Mapped[str] = mapped_column(String(200), default="")
    count: Mapped[int] = mapped_column(Integer, default=1)
    first_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


_TABLES = (ImageObservation.__table__, PatternObservation.__table__, Arm.__table__,
           Decision.__table__, DerivedLesson.__table__, LessonEffect.__table__)
_ensured: set[int] = set()
_lock = threading.Lock()


def ensure_tables(db) -> None:
    key = id(db.engine)
    if key in _ensured:
        return
    with _lock:
        if key not in _ensured:
            for t in _TABLES:
                t.create(db.engine, checkfirst=True)
            _ensured.add(key)
