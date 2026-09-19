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
    # Which requirement this action belongs to, and therefore the action's identity. The
    # queue de-duplicates on this rather than on the action's wording: an action that
    # derives a figure from the catalogue changes its text when the catalogue changes, and
    # comparing text gave the owner two entries for one decision.
    requirement_key: Mapped[str] = mapped_column(Text, default="")
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


# ---------------------------------------------------------------------------
# Benchmark intelligence (v1.4.3 sections 205-220 and 300-320).
#
# The owner named one shop and forbade generalising it into "watch proven sellers", so the
# registry is a table rather than a constant: a benchmark has scan health, freshness and an
# owner-supplied URL that has to survive Etsy changing its routing. What the tables below
# deliberately do *not* hold is any competitor's protected expression -- no pattern text, no
# chart, no downloaded image. They hold observations about merchandising, and the mechanism
# lessons drawn from them.


class Benchmark(Base):
    """One elite benchmark shop, with the evidence to say how fresh its coverage is (#205)."""

    __tablename__ = "benchmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    shop_name: Mapped[str] = mapped_column(String(120))
    platform: Mapped[str] = mapped_column(String(30), default="etsy")
    canonical_url: Mapped[str] = mapped_column(Text)
    # Kept alongside the short route because #301 requires the owner-supplied URL to remain
    # in the registry and in acceptance evidence, verbatim.
    owner_supplied_url: Mapped[str] = mapped_column(Text, default="")
    mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    reason_for_inclusion: Mapped[str] = mapped_column(Text, default="")
    categories: Mapped[list] = mapped_column(JSON, default=list)
    responsible_pods: Mapped[list] = mapped_column(JSON, default=list)
    scan_health: Mapped[dict] = mapped_column(JSON, default=dict)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                          nullable=True)
    last_baseline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                              nullable=True)
    last_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                            nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class BenchmarkListing(Base):
    """A listing observed in a benchmark catalogue: the living market map (#303)."""

    __tablename__ = "benchmark_listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    benchmark_key: Mapped[str] = mapped_column(String(60), index=True)
    listing_ref: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text, default="")
    pod: Mapped[str] = mapped_column(String(40), default="", index=True)
    product_type: Mapped[str] = mapped_column(String(60), default="")
    # The fingerprint is what makes change detection cheap (#212): unchanged content is not
    # paid for twice.
    fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)
    price_cad: Mapped[float] = mapped_column(Float, default=0.0)
    on_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    media_count: Mapped[int] = mapped_column(Integer, default=0)
    seasonal: Mapped[str] = mapped_column(String(40), default="")
    audit_state: Mapped[str] = mapped_column(String(30), default="discovered", index=True)
    evidence_grade: Mapped[str] = mapped_column(String(20), default="supporting")
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (UniqueConstraint("benchmark_key", "listing_ref",
                                       name="uq_benchmark_listing"),)


class BenchmarkObservation(Base):
    """One dated piece of benchmark evidence, with what it was allowed to do (#209, #319)."""

    __tablename__ = "benchmark_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    benchmark_key: Mapped[str] = mapped_column(String(60), index=True)
    listing_ref: Mapped[str] = mapped_column(String(80), default="", index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    grade: Mapped[str] = mapped_column(String(20), default="supporting", index=True)
    satisfies_mandate: Mapped[bool] = mapped_column(Boolean, default=False)
    pods_notified: Mapped[list] = mapped_column(JSON, default=list)
    mechanisms: Mapped[list] = mapped_column(JSON, default=list)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class CoverageGap(Base):
    """A benchmark arena with no competitive Brambleloop answer yet (#314)."""

    __tablename__ = "coverage_gaps"

    id: Mapped[int] = mapped_column(primary_key=True)
    benchmark_key: Mapped[str] = mapped_column(String(60), index=True)
    arena: Mapped[str] = mapped_column(String(80), index=True)
    pod: Mapped[str] = mapped_column(String(40), index=True)
    state: Mapped[str] = mapped_column(String(30), default="uncovered", index=True)
    # A queue that lets an item leave without saying why is a queue that shrinks by
    # forgetting. "not_pursuing" requires this field (#314).
    reason: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    components: Mapped[dict] = mapped_column(JSON, default=dict)
    product_slug: Mapped[str] = mapped_column(String(80), default="")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("benchmark_key", "arena", name="uq_benchmark_arena"),)


# ---------------------------------------------------------------------------
# Competitive product teardown laboratory (v1.4.3 sections 148-170).
#
# What these tables hold is the distinction the whole laboratory turns on: observations about
# a purchased competitor product, and never the product. No row here stores pattern text, a
# chart, an image or a transcription. The files themselves live outside the repository in a
# quarantined directory, and `teardown/library.py` is the only thing that may look at them.


class BenchmarkProduct(Base):
    """One purchased competitor product, as a manifest entry (#150)."""

    __tablename__ = "benchmark_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    seller: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(60), default="")
    pod: Mapped[str] = mapped_column(String(40), default="", index=True)
    listing_ref: Mapped[str] = mapped_column(String(80), default="")
    purchased_on: Mapped[str] = mapped_column(String(10), default="")
    paid_cad: Mapped[float] = mapped_column(Float, default=0.0)
    on_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    why_selected: Mapped[str] = mapped_column(Text, default="")
    listing_promises: Mapped[dict] = mapped_column(JSON, default=dict)
    # Filenames, sizes and hashes only. The contents stay in the quarantined library.
    files: Mapped[list] = mapped_column(JSON, default=list)
    dimensions: Mapped[list] = mapped_column(JSON, default=list)
    teardown_state: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TeardownFinding(Base):
    """One scored observation about a purchased benchmark (#153-#161)."""

    __tablename__ = "teardown_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    benchmark_ref: Mapped[str] = mapped_column(String(80), index=True)
    dimension: Mapped[str] = mapped_column(String(40), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    mechanism: Mapped[str] = mapped_column(Text, default="")
    # What Brambleloop should do about it. A teardown that produces no action is a review.
    improvement: Mapped[str] = mapped_column(Text, default="")
    promoted: Mapped[bool] = mapped_column(Boolean, default=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


# ---------------------------------------------------------------------------
# Continuous improvement (v1.4.3 sections 90-104).


class Improvement(Base):
    """One hypothesis, its evidence, and the way back (#92, #93)."""

    __tablename__ = "improvements"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    cell: Mapped[str] = mapped_column(String(40), index=True)
    metric: Mapped[str] = mapped_column(String(60), index=True)
    hypothesis: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="proposed", index=True)
    # Captured before anything changes. An improvement measured against a baseline recorded
    # afterwards is measured against itself.
    baseline_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_ref: Mapped[str] = mapped_column(String(80), default="")
    result_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_effect: Mapped[str] = mapped_column(Text, default="")
    rollback_ref: Mapped[str] = mapped_column(String(200), default="")
    cost_cad: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                         nullable=True)
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                         nullable=True)


class Lesson(Base):
    """Something learned once, routed to everyone it affects (#97, #101)."""

    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    origin_cell: Mapped[str] = mapped_column(String(40), index=True)
    subject: Mapped[str] = mapped_column(String(80), index=True)
    statement: Mapped[str] = mapped_column(Text)
    evidence_ref: Mapped[str] = mapped_column(String(200), default="")
    confidence: Mapped[str] = mapped_column(String(20), default="observed")
    routed_to: Mapped[list] = mapped_column(JSON, default=list)
    acted_on_by: Mapped[list] = mapped_column(JSON, default=list)
    superseded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CapabilityPoint(Base):
    """One measurement of one cell's capability, so improvement is checkable (#94, #95)."""

    __tablename__ = "capability_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    cell: Mapped[str] = mapped_column(String(40), index=True)
    metric: Mapped[str] = mapped_column(String(60), index=True)
    value: Mapped[float] = mapped_column(Float)
    sample: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class GrowthLoop(Base):
    """One acquisition mechanism and the traffic it has actually produced (#271)."""

    __tablename__ = "growth_loops"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    strength: Mapped[str] = mapped_column(String(20), default="untested", index=True)
    visits: Mapped[int] = mapped_column(Integer, default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    cost_cad: Mapped[float] = mapped_column(Float, default=0.0)
    latency_days: Mapped[int] = mapped_column(Integer, default=0)
    scalable: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------------------
# Culture and nostalgia (v1.4.3 sections 133-147).


class CultureSignal(Base):
    """One thing people are emotionally engaging with, and what it is allowed to become.

    The protected tokens are stored on the signal rather than worked out downstream, because
    a token declared at the point of observation is one every later step can be checked
    against -- and a token nobody declared is one nobody can be checked against (#135, #139).
    """

    __tablename__ = "culture_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    topic: Mapped[str] = mapped_column(Text, default="")
    domain: Mapped[str] = mapped_column(String(30), index=True)
    first_seen: Mapped[str] = mapped_column(String(10), default="")
    lane: Mapped[str] = mapped_column(String(30), default="original_concept", index=True)
    # Declared at observation time. Filenames-and-hashes discipline, applied to rights.
    protected_tokens: Mapped[list] = mapped_column(JSON, default=list)
    basis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    primitives: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(20), default="observed", index=True)
    exit_reason: Mapped[str] = mapped_column(Text, default="")
    outcome: Mapped[dict] = mapped_column(JSON, default=dict)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CultureObservation(Base):
    """One momentum reading for one signal, so decay is measured rather than felt (#140, #145)."""

    __tablename__ = "culture_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    signal_key: Mapped[str] = mapped_column(String(80), index=True)
    channel: Mapped[str] = mapped_column(String(30), index=True)
    observed_on: Mapped[str] = mapped_column(String(10), default="")
    interest: Mapped[float] = mapped_column(Float, default=0.0)
    competitor_listings: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class PolicySnapshot(Base):
    """One reading of one external platform policy, with its date (#39).

    A policy is not a constant. Storing the snapshot -- rather than encoding the rule in code
    and forgetting when it was true -- is what lets a release certificate say which version of
    Etsy's rules it was certified against, and what lets the freshness watch tell the
    difference between a policy that has not changed and one nobody has looked at.
    """

    __tablename__ = "policy_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    url: Mapped[str] = mapped_column(Text, default="")
    checked_on: Mapped[str] = mapped_column(String(10), default="")
    version: Mapped[str] = mapped_column(String(40), default="")
    digest: Mapped[str] = mapped_column(String(64), default="", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    material_change: Mapped[bool] = mapped_column(Boolean, default=False)
    affects: Mapped[list] = mapped_column(JSON, default=list)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class PriceObservation(Base):
    """One price point held for a period, with everything that could confound it (#46).

    The confounders are columns rather than notes because the whole value of an elasticity
    memory is being able to ask "was this a price effect or was it December", and a note
    cannot be filtered on.
    """

    __tablename__ = "price_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    product_slug: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(60), default="", index=True)
    price_cad: Mapped[float] = mapped_column(Float, default=0.0)
    on_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    regular_price_cad: Mapped[float] = mapped_column(Float, default=0.0)
    traffic_source: Mapped[str] = mapped_column(String(40), default="", index=True)
    season: Mapped[str] = mapped_column(String(40), default="", index=True)
    from_date: Mapped[str] = mapped_column(String(10), default="")
    to_date: Mapped[str] = mapped_column(String(10), default="")
    visits: Mapped[int] = mapped_column(Integer, default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    revenue_cad: Mapped[float] = mapped_column(Float, default=0.0)
    contribution_cad: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class Cohort(Base):
    """One launch cohort, organic or promoted, kept apart so the two can be compared (#48)."""

    __tablename__ = "cohorts"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    product_slug: Mapped[str] = mapped_column(String(80), index=True)
    arm: Mapped[str] = mapped_column(String(20), default="organic", index=True)
    from_date: Mapped[str] = mapped_column(String(10), default="")
    to_date: Mapped[str] = mapped_column(String(10), default="")
    visits: Mapped[int] = mapped_column(Integer, default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    revenue_cad: Mapped[float] = mapped_column(Float, default=0.0)
    spend_cad: Mapped[float] = mapped_column(Float, default=0.0)
    assisted: Mapped[int] = mapped_column(Integer, default=0)
    direct: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


# ---------------------------------------------------------------------------
# The autonomous build executor (v1.4.3 master intent: never-idle development).


class BuildTask(Base):
    """One Build-2 requirement as a schedulable unit of work, with its readiness derived.

    The registry in `build2/requirements.json` says what each requirement *is*. This says
    what can be worked on *now*, and it lives in Postgres rather than in a session's head --
    which is the whole point. A build loop that exists only while a conversation is open is
    not autonomy; it is a person with extra steps.
    """

    __tablename__ = "build_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    section: Mapped[str] = mapped_column(String(120), default="", index=True)
    # Mirrors the registry status at the time of the last sync, so drift is detectable.
    status: Mapped[str] = mapped_column(String(20), default="missing", index=True)
    # ready | parked | blocked | in_progress | done
    state: Mapped[str] = mapped_column(String(20), default="ready", index=True)
    priority: Mapped[float] = mapped_column(Float, default=100.0, index=True)
    # Requirement ids that must be done first. A cycle here is refused at sync time.
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    # The capability key this is parked on, if any. Checkable, never free text: an unpark
    # condition nothing can make true is a refusal dressed as a wait.
    parked_on: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    parked_reason: Mapped[str] = mapped_column(Text, default="")
    parked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                          nullable=True)
    # What proved it done: suite name, test count, commit. Evidence, not a checkbox.
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BuildEvent(Base):
    """Append-only record of the executor's own decisions.

    Separate from the audit log because the question it answers is different: the audit log
    says what the company did, and this says why the build loop chose it -- which is the only
    way to tell a loop that is working from one that is turning over.
    """

    __tablename__ = "build_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    requirement_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(80), default="executor")
    summary: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
