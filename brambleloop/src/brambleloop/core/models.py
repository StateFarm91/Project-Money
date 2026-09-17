"""Intelligence warehouse tables (Master Plan section 15).

Only the tables something actually writes to today are defined here. Modelling the full
warehouse up front would create dozens of tables no code touches, which rots. Tables are added
as their systems are built.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"      # will retry
    DEAD = "dead"          # exhausted retries -> dead-letter
    CANCELLED = "cancelled"


class Authority(str, enum.Enum):
    """Master Plan section 26 authority matrix."""

    GREEN = "green"    # autonomous, reversible, no spend
    YELLOW = "yellow"  # bounded customer/spend actions inside explicit limits
    RED = "red"        # owner-only: KYC, legal acceptance, banking, consequential spend


class Phase(str, enum.Enum):
    SHADOW = "shadow"
    STAGING = "staging"
    LIMITED_PRODUCTION = "limited_production"
    PRODUCTION = "production"


class Job(Base):
    """A unit of durable work.

    `idempotency_key` is the guard that makes duplicate execution safe: two jobs that would
    publish the same listing or spend the same budget cannot both exist (Gate A).
    """

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent: Mapped[str] = mapped_column(String(64), index=True)
    job_type: Mapped[str] = mapped_column(String(64), index=True)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    outputs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False), default=JobStatus.PENDING, index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    leased_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cost_cad: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_jobs_idempotency_key"),
        Index("ix_jobs_claimable", "status", "run_after", "priority"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Job {self.id} {self.agent}/{self.job_type} {self.status.value}>"


class Agent(Base):
    """Agent registry: explicit tools, budgets and financial authority (section 14)."""

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    allowed_job_types: Mapped[list] = mapped_column(JSON, default=list)
    authority: Mapped[Authority] = mapped_column(
        Enum(Authority, native_enum=False), default=Authority.GREEN
    )
    daily_cost_ceiling_cad: Mapped[float] = mapped_column(Float, default=5.0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    phase: Mapped[Phase] = mapped_column(
        Enum(Phase, native_enum=False), default=Phase.SHADOW
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def may_run(self, job_type: str) -> bool:
        return self.enabled and job_type in (self.allowed_job_types or [])


class AuditLog(Base):
    """Append-only. Every production action records actor, action, artifact and time.

    Nothing in the codebase updates or deletes rows here; the gates rely on it being a
    faithful record rather than a mutable convenience table.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    artifact: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    phase: Mapped[Phase | None] = mapped_column(
        Enum(Phase, native_enum=False), nullable=True
    )
    model_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    policy_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class CostEntry(Base):
    """Per-agent operating cost, so throughput can be measured in dollars (section 34)."""

    __tablename__ = "cost_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    agent: Mapped[str] = mapped_column(String(64), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), default="llm")  # llm | api | hosting | ads
    amount_cad: Mapped[float] = mapped_column(Float, default=0.0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class LedgerEntry(Base):
    """Financial ledger: actual money events only, each with an evidence reference."""

    __tablename__ = "ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    gross_cad: Mapped[float] = mapped_column(Float, default=0.0)
    fees_cad: Mapped[float] = mapped_column(Float, default=0.0)
    refunds_cad: Mapped[float] = mapped_column(Float, default=0.0)
    expense_cad: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_ref: Mapped[str] = mapped_column(String(200), default="")

    @property
    def net_cad(self) -> float:
        return self.gross_cad - self.fees_cad - self.refunds_cad - self.expense_cad


class SpendLimit(Base):
    """Hard budget ceilings enforced in code, not in a prompt (section 11)."""

    __tablename__ = "spend_limits"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    daily_cap_cad: Mapped[float] = mapped_column(Float, default=0.0)
    lifetime_cap_cad: Mapped[float] = mapped_column(Float, default=0.0)
    spent_today_cad: Mapped[float] = mapped_column(Float, default=0.0)
    spent_lifetime_cad: Mapped[float] = mapped_column(Float, default=0.0)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    day: Mapped[str] = mapped_column(String(10), default="")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(40), default="concept", index=True)
    risk_class: Mapped[str] = mapped_column(String(1), default="A")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    versions: Mapped[list["PatternVersion"]] = relationship(back_populates="product")


class PatternVersion(Base):
    """An immutable CIR release. `release_hash` makes a shipped pattern identifiable."""

    __tablename__ = "pattern_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    version: Mapped[str] = mapped_column(String(20))
    cir_json: Mapped[dict] = mapped_column(JSON)
    release_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    certified: Mapped[bool] = mapped_column(Boolean, default=False)
    certificate: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    product: Mapped[Product] = relationship(back_populates="versions")

    __table_args__ = (UniqueConstraint("product_id", "version", name="uq_product_version"),)


class Incident(Base):
    """A correlated quality problem (Gate E). P0/P1 can halt publication."""

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    severity: Mapped[str] = mapped_column(String(4), default="P2", index=True)
    product_slug: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    signature: Mapped[str] = mapped_column(String(200), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    report_count: Mapped[int] = mapped_column(Integer, default=1)
    halts_publication: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class OwnerAction(Base):
    """The single consolidated owner queue (section 14)."""

    __tablename__ = "owner_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    action: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")
    max_cost_cad: Mapped[float] = mapped_column(Float, default=0.0)
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    consequence_of_delay: Mapped[str] = mapped_column(Text, default="")
    blocks: Mapped[str] = mapped_column(Text, default="")
    done: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------------------
# Commercial warehouse (section 15).
#
# Added as their systems were built, not speculatively. Each table below has code that
# writes to it; the ones section 15 lists that are still absent -- SALES, REVIEWS,
# CAMPAIGNS -- stay absent until something real produces the rows, because a table full of
# nothing is indistinguishable from a table full of fiction.
# ---------------------------------------------------------------------------


class Collection(Base):
    """A named family of products sold as one visual idea (sections 6, 16)."""

    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    family: Mapped[str] = mapped_column(String(80), index=True)
    season: Mapped[str | None] = mapped_column(String(40), nullable=True)
    palette: Mapped[dict] = mapped_column(JSON, default=dict)
    story: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Motif(Base):
    """A reusable, original, validated design element (section 5).

    The library is inventory. A motif that compiled inside one product can be reused in
    another without re-earning its arithmetic, which is the only way a catalogue grows
    without the defect rate growing with it.
    """

    __tablename__ = "motifs"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    width_stitches: Mapped[int] = mapped_column(Integer)
    height_rows: Mapped[int] = mapped_column(Integer)
    grid: Mapped[list] = mapped_column(JSON)
    origin_product: Mapped[str | None] = mapped_column(String(80), nullable=True)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ListingAsset(Base):
    """One image in a listing's ordered frame plan (section 7)."""

    __tablename__ = "listing_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_slug: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[str] = mapped_column(String(20))
    position: Mapped[int] = mapped_column(Integer)
    asset_class: Mapped[str] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(40))
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claims: Mapped[dict] = mapped_column(JSON, default=dict)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_reasons: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("product_slug", "version", "position", name="uq_asset_slot"),
    )


class Listing(Base):
    """A drafted (never published, in shadow) storefront listing."""

    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_slug: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    price_cad: Mapped[float] = mapped_column(Float, default=0.0)
    state: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    seo_score: Mapped[float] = mapped_column(Float, default=0.0)
    # Which release chain produced this listing. A rebuild that only looked for *missing*
    # listings left every stale one in place, so staleness has to be visible.
    chain_version: Mapped[str] = mapped_column(String(8), default="1", index=True)
    # And which *certified release* produced it. The chain version catches a code change;
    # this catches a design change, which the chain version cannot see: a re-engineered
    # product keeps its slug and its version and gets a new release hash.
    release_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    # The Etsy listing this became, once it becomes one. Recorded so that publishing twice
    # updates a listing rather than creating a second one, and so a listing that exists on
    # Etsy with no file attached can be found again and completed.
    etsy_listing_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("product_slug", "version", name="uq_listing_version"),
    )


class Keyword(Base):
    """A query we are trying to cover, and how well we currently cover it (section 8)."""

    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    phrase: Mapped[str] = mapped_column(String(120), index=True)
    intent: Mapped[str] = mapped_column(String(30), default="product")
    est_competition: Mapped[float] = mapped_column(Float, default=0.5)
    est_demand: Mapped[float] = mapped_column(Float, default=0.5)
    covered_by: Mapped[list] = mapped_column(JSON, default=list)
    coverage: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("phrase", name="uq_keyword_phrase"),)


class CompetitorSnapshot(Base):
    """A dated observation of a competitor. Longitudinal by construction (section 4)."""

    __tablename__ = "competitor_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop: Mapped[str] = mapped_column(String(80), index=True)
    observed_on: Mapped[str] = mapped_column(String(10), index=True)
    price_low_cad: Mapped[float] = mapped_column(Float, default=0.0)
    price_high_cad: Mapped[float] = mapped_column(Float, default=0.0)
    signals: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (UniqueConstraint("shop", "observed_on", name="uq_shop_observation"),)


class SupportCase(Base):
    """A customer conversation, with the pattern version it was answered from (section 10)."""

    __tablename__ = "support_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    customer_ref: Mapped[str] = mapped_column(String(80), index=True)
    product_slug: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    specialist: Mapped[str] = mapped_column(String(40), default="concierge", index=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class Experiment(Base):
    """A price or creative test with its stopping rule fixed before it starts (section 9)."""

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    product_slug: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    arms: Mapped[list] = mapped_column(JSON, default=list)
    min_observations: Mapped[int] = mapped_column(Integer, default=200)
    max_loss_cad: Mapped[float] = mapped_column(Float, default=0.0)
    state: Mapped[str] = mapped_column(String(20), default="designed", index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PortfolioReview(Base):
    """A dated classification of every SKU (section 12)."""

    __tablename__ = "portfolio_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    as_of: Mapped[str] = mapped_column(String(10), index=True)
    classifications: Mapped[dict] = mapped_column(JSON, default=dict)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    evidence_available: Mapped[bool] = mapped_column(Boolean, default=False)


class ContentPiece(Base):
    """One item in a product's content ecosystem (section 11)."""

    __tablename__ = "content_pieces"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_slug: Mapped[str] = mapped_column(String(80), index=True)
    channel: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, default="")
    scheduled_for: Mapped[str | None] = mapped_column(String(10), nullable=True)
    state: Mapped[str] = mapped_column(String(20), default="drafted", index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PhysicalTest(Base):
    """A real person crocheting a real sample. Calibration data, not a formality."""

    __tablename__ = "physical_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_slug: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[str] = mapped_column(String(20))
    tester_ref: Mapped[str] = mapped_column(String(80))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    measured: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
