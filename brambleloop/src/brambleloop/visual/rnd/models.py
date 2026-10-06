"""Durable Visual R&D state: pipeline versions, experiments, judgements, market evidence, lessons.

Additive tables on the shared `Base`, created lazily by `ensure_tables(db)` (the pattern
`seo.models` and `commerce.search_visibility` use) so the department works before
`core.db.create_all` imports this module; the WIRING REQUEST in `handoff_H.md` adds that import.

Nothing critical lives in a context window: a pipeline version, the experiment that produced
it, every image judgement it was measured on, every marketplace reading that later confirmed
or overturned it, and the lesson the loop persisted are all rows.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from ...core.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class VisualPipelineVersion(Base):
    """One version of one product class's whole image pipeline (its parameters + lineage).

    `state`: incumbent (the version generation reads) | candidate (a challenger under test) |
    retired (was incumbent, replaced by a promotion) | rejected (a challenger that lost or failed
    a gate) | rolled_back (was incumbent, removed because it regressed or was overturned).
    """

    __tablename__ = "visual_rnd_pipelines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    product_class: Mapped[str] = mapped_column(String(48), index=True)
    generation: Mapped[int] = mapped_column(Integer, default=1)
    label: Mapped[str] = mapped_column(String(120), default="")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    digest: Mapped[str] = mapped_column(String(64), index=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str] = mapped_column(String(24), index=True)
    why: Mapped[str] = mapped_column(Text, default="")
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The measured reading the version was promoted on (its controlled-test score), which is
    # what monitoring compares production against.
    promoted_on: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class VisualExperiment(Base):
    """One challenger against one incumbent: hypothesis, execution route, result, decision."""

    __tablename__ = "visual_rnd_experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now,
                                                 index=True)
    product_class: Mapped[str] = mapped_column(String(48), index=True)
    incumbent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    challenger_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage: Mapped[str] = mapped_column(String(48), default="")
    varied: Mapped[dict] = mapped_column(JSON, default=dict)
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    diagnosis: Mapped[dict] = mapped_column(JSON, default=dict)
    execution: Mapped[str] = mapped_column(String(32), default="deterministic_local")
    state: Mapped[str] = mapped_column(String(32), index=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    estimated_cost_cad: Mapped[float | None] = mapped_column(Float, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VisualJudgement(Base):
    """One image (or gallery) through the fast-loop gates, with its measured cost and latency."""

    __tablename__ = "visual_rnd_judgements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    pipeline_id: Mapped[int] = mapped_column(Integer, index=True)
    experiment_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    arm: Mapped[str] = mapped_column(String(24), default="production")
    product_class: Mapped[str] = mapped_column(String(48), index=True)
    subject: Mapped[str] = mapped_column(String(160), index=True)
    image_sha256: Mapped[str] = mapped_column(String(64), default="")
    gates: Mapped[dict] = mapped_column(JSON, default=dict)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    failures: Mapped[list] = mapped_column(JSON, default=list)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_cad: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_basis: Mapped[str] = mapped_column(String(64), default="unknown")
    source: Mapped[str] = mapped_column(String(64), default="")


class VisualMarketEvidence(Base):
    """A marketplace reading for listings imaged by one pipeline version (the slow loop).

    Counts only: a reading nobody measured is absent, never zero.
    """

    __tablename__ = "visual_rnd_market"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    pipeline_id: Mapped[int] = mapped_column(Integer, index=True)
    product_class: Mapped[str] = mapped_column(String(48), index=True)
    subject: Mapped[str] = mapped_column(String(160), default="")
    impressions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clicks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    favourites: Mapped[int | None] = mapped_column(Integer, nullable=True)
    carts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    purchases: Mapped[int | None] = mapped_column(Integer, nullable=True)
    refunds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    support_flags: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_ref: Mapped[str] = mapped_column(String(240), default="")


class VisualLesson(Base):
    """What the loop learned, read before it proposes again (refusals are lessons too)."""

    __tablename__ = "visual_rnd_lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    product_class: Mapped[str] = mapped_column(String(48), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    statement: Mapped[str] = mapped_column(Text, default="")
    ref: Mapped[str] = mapped_column(String(160), default="")


class VisualHeroVariant(Base):
    """One hero (listing frame 1) treatment for one product class: the commercial R&D unit.

    `style_key` is the value `ListingOutcome.hero_style` carries for listings that showed this
    hero, which is how the slow loop credits marketplace outcomes to it. `state`: incumbent |
    candidate | rejected | retired | overturned | gated_spend (a paid challenger waiting for
    owner spend authority) | unavailable (needs an asset that does not exist yet).
    `basis` says what the latest decision rested on: "proxy" (internal judges only) or
    "market" (ListingOutcome evidence). A proxy promotion is provisional by construction.
    """

    __tablename__ = "visual_rnd_hero_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now,
                                                 index=True)
    product_class: Mapped[str] = mapped_column(String(48), index=True)
    treatment: Mapped[str] = mapped_column(String(64), index=True)
    style_key: Mapped[str] = mapped_column(String(120), index=True)
    execution: Mapped[str] = mapped_column(String(32), default="deterministic_local")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str] = mapped_column(String(24), index=True)
    basis: Mapped[str] = mapped_column(String(16), default="proxy")
    gates: Mapped[dict] = mapped_column(JSON, default=dict)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    objective: Mapped[dict] = mapped_column(JSON, default=dict)
    estimated_cost_cad: Mapped[float | None] = mapped_column(Float, nullable=True)
    why: Mapped[str] = mapped_column(Text, default="")
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


TABLES = (VisualPipelineVersion, VisualExperiment, VisualJudgement, VisualMarketEvidence,
          VisualLesson, VisualHeroVariant)
# The tables whose presence means "the department has run" (the hero table is additive and
# created by the same `ensure_tables`, so an older database is not reported as never-run).
CORE_TABLES = TABLES[:5]


def is_session(db) -> bool:
    return isinstance(db, Session)


def engine(db):
    return db.get_bind() if is_session(db) else db.engine


@contextmanager
def session(db) -> Iterator[Session]:
    """Either the repo's `Database` wrapper or a bare Session (the caller then owns commit)."""
    if is_session(db):
        yield db
        db.flush()
        return
    with db.session() as s:
        yield s


def ensure_tables(db) -> None:
    eng = engine(db)
    for model in TABLES:
        model.__table__.create(eng, checkfirst=True)


def tables_exist(db) -> bool:
    from sqlalchemy import inspect

    try:
        names = set(inspect(engine(db)).get_table_names())
    except Exception:  # noqa: BLE001 - an unreadable schema is not a populated one
        return False
    return all(m.__tablename__ in names for m in CORE_TABLES)


def table_exists(db, model) -> bool:
    from sqlalchemy import inspect

    try:
        return model.__tablename__ in set(inspect(engine(db)).get_table_names())
    except Exception:  # noqa: BLE001
        return False
