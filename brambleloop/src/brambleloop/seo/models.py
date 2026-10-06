"""Durable SEO state: keyword evidence, proposals and the cycles that produced them.

Additive tables on the shared `Base`. They are created by `ensure_tables(db)` (the pattern
`commerce.search_visibility` uses) so this package works before `core.db.create_all` is wired
to import it; the WIRING REQUEST in `handoff_G.md` adds that import.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow

# Evidence basis labels. `measured`: a count Etsy produced (Stats export, Marketplace
# Insights as read by the owner, the API index's result count). `observed`: a phrase seen in
# a real listing or search result -- presence, not volume. `modelled`: a hand-set constant or a
# template (commerce.search._TEMPLATES). `unknown`: provenance not recorded.
MEASURED = "measured"
OBSERVED = "observed"
MODELLED = "modelled"
UNKNOWN = "unknown"
BASES = (MEASURED, OBSERVED, MODELLED, UNKNOWN)


class SeoKeywordEvidence(Base):
    """One piece of evidence about one search phrase, with where it came from."""

    __tablename__ = "seo_keyword_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    phrase: Mapped[str] = mapped_column(String(200), index=True)
    metric: Mapped[str] = mapped_column(String(60))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    basis: Mapped[str] = mapped_column(String(20), index=True)
    # What the value can be used as. A result count is measured supply; using it as
    # "competition" is a proxy and says so here.
    use: Mapped[str] = mapped_column(String(60), default="")
    source: Mapped[str] = mapped_column(String(80), index=True)
    source_ref: Mapped[str] = mapped_column(String(200), default="")
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    fingerprint: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (UniqueConstraint("fingerprint", name="uq_seo_evidence_fp"),)


class SeoProposal(Base):
    """A title/tag/attribute proposal for one draft. Never written to Etsy."""

    __tablename__ = "seo_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_slug: Mapped[str] = mapped_column(String(80), index=True)
    candidate: Mapped[str] = mapped_column(String(80), default="")
    input_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(20), default="PROPOSED", index=True)
    ok: Mapped[int] = mapped_column(Integer, default=0)
    proposal: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 index=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                           nullable=True)

    __table_args__ = (UniqueConstraint("product_slug", "input_fingerprint",
                                       name="uq_seo_proposal_input"),)


class SeoCycle(Base):
    """One `run_cycle` that changed something. A no-op cycle writes nothing."""

    __tablename__ = "seo_cycles"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    evidence_added: Mapped[int] = mapped_column(Integer, default=0)
    proposals_written: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (UniqueConstraint("fingerprint", name="uq_seo_cycle_fp"),)


TABLES = (SeoKeywordEvidence, SeoProposal, SeoCycle)


def ensure_tables(db) -> None:
    from ._db import engine

    eng = engine(db)
    for model in TABLES:
        model.__table__.create(eng, checkfirst=True)


def tables_exist(db) -> bool:
    from sqlalchemy import inspect

    from ._db import engine

    try:
        names = set(inspect(engine(db)).get_table_names())
    except Exception:  # noqa: BLE001 - an unreadable schema is not a populated one
        return False
    return all(m.__tablename__ in names for m in TABLES)
