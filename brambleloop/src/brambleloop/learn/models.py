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
