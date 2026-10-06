"""Additive durable Learn state, registered by core.db at integration."""
from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from ..core.db import Base


class LearnNode(Base):
    __tablename__ = "learn_nodes"
    key: Mapped[str] = mapped_column(String(240), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class LearnEdge(Base):
    __tablename__ = "learn_edges"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(240), index=True)
    target: Mapped[str] = mapped_column(String(240), index=True)
    relation: Mapped[str] = mapped_column(String(32))
    evidence: Mapped[dict] = mapped_column(JSON)


class LearnGap(Base):
    __tablename__ = "learn_gaps"
    topic: Mapped[str] = mapped_column(String(240), primary_key=True)
    state: Mapped[str] = mapped_column(String(32), default="QUEUED")
    owner: Mapped[str] = mapped_column(String(32), default="learn")
    # A source disappearing is not proof that its learner need was solved.
    evidence: Mapped[list] = mapped_column(JSON, default=list)


class Lesson(Base):
    __tablename__ = "learn_lessons"
    slug: Mapped[str] = mapped_column(String(100), primary_key=True)
    revision: Mapped[str] = mapped_column(String(64))
    spec: Mapped[dict] = mapped_column(JSON)
    reviews: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(32), default="DRAFT")


# ---- v1.1 lane B: measured self-improvement loops (directive §4, F-918..F-920) -------------
#
# Three durable records. A decision the runtime took under a policy, with the features it
# decided on and the outcome observed later; every proposal to change a policy, including
# the ones refused by the protected-invariant guard (refusals are memory too); and the
# lessons the loop persisted when it promoted, rolled back or refused something -- which the
# next cycle reads before proposing again. No critical memory lives only in a context window.
from datetime import datetime, timezone  # noqa: E402

from sqlalchemy import DateTime, Float, Integer  # noqa: E402


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LearnDecision(Base):
    __tablename__ = "learn_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    loop: Mapped[str] = mapped_column(String(64), index=True)
    subject: Mapped[str] = mapped_column(String(240), index=True)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    action: Mapped[dict] = mapped_column(JSON, default=dict)
    config_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    # None until observed. Never a guessed zero: an unobserved outcome is not a bad one.
    outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_ref: Mapped[str] = mapped_column(String(240), default="")


class LearnProposal(Base):
    __tablename__ = "learn_proposals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    loop: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(32), index=True)
    proposed_by: Mapped[str] = mapped_column(String(64), default="")
    params_from: Mapped[dict] = mapped_column(JSON, default=dict)
    params_to: Mapped[dict] = mapped_column(JSON, default=dict)
    metric: Mapped[str] = mapped_column(String(80), default="")
    baseline: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[float | None] = mapped_column(Float, nullable=True)
    improvement_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    replaces: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LearnPolicyLesson(Base):
    __tablename__ = "learn_policy_lessons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    loop: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    statement: Mapped[str] = mapped_column(Text)
    evidence_ref: Mapped[str] = mapped_column(String(240), default="")
    metric_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
