"""Durable records for listing-image production (W-OWNERIMG).

Three additive tables. They are shared by the autonomous image-production workflow
(`visual.image_production`) and the owner-upload fallback (`publish.owner_images`):

* `laura_outfits`: the D-W4-LAURA-OUTFIT registry. Each outfit has an id, a description,
  colours, reference image hashes and an approval state. It may be reserved by (bound to) at
  most one listing, and it keeps a usage list of (listing, slug@version, image sha).
* `image_production_runs`: one row per slug@version@release. It records the workflow's
  stage, its status (the Command Center states), its attempt counters and its per-stage
  evidence.
* `image_candidates`: one row per candidate image, whatever made it. A row holds:
  - the bytes' sha256;
  - its binding;
  - the shared gate verdict;
  - provider, model, cost and latency;
  - learning categories;
  - for an owner submission, the owner's visual approval. That approval is a field of its
    own and is never part of the technical verdict.

Registration: `core.db.Database.create_all` imports this module. `ensure_tables` also creates
the tables on first use (checkfirst), the same pattern `queue.checkpoints` uses.
"""
from __future__ import annotations

import threading
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow


class LauraOutfit(Base):
    __tablename__ = "laura_outfits"

    id: Mapped[int] = mapped_column(primary_key=True)
    outfit_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    # D-W4-LAURA-FLUX3 §4: the complete outfit. Keys: top_or_dress, lower, shoes,
    # outerwear, accessories ("" / "none" where not worn).
    garments: Mapped[dict] = mapped_column(JSON, default=dict)
    signature: Mapped[str] = mapped_column(String(64), default="", index=True)
    colours: Mapped[list] = mapped_column(JSON, default=list)
    # The approved outfit reference image (sha256), once one exists.
    approved_reference: Mapped[str] = mapped_column(String(64), default="")
    # The photoshoot concept chosen with it (visual.styling), so settings are not repeated.
    setting: Mapped[str] = mapped_column(String(200), default="")
    concept: Mapped[dict] = mapped_column(JSON, default=dict)
    reference_hashes: Mapped[list] = mapped_column(JSON, default=list)
    # proposed | approved | retired
    approval_state: Mapped[str] = mapped_column(String(20), default="proposed", index=True)
    approved_by: Mapped[str] = mapped_column(String(80), default="")
    # The one listing (product listing slug) this outfit is reserved for; "" = free.
    listing: Mapped[str] = mapped_column(String(120), default="", index=True)
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # [{"listing", "product", "image_sha256", "at"}]
    uses: Mapped[list] = mapped_column(JSON, default=list)
    replaced_by: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImageProductionRun(Base):
    __tablename__ = "image_production_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[str] = mapped_column(String(20), default="")
    release: Mapped[str] = mapped_column(String(80), default="")
    listing: Mapped[str] = mapped_column(String(120), default="", index=True)
    stage: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(40), default="awaiting_certified_pattern",
                                        index=True)
    blocked_reason: Mapped[str] = mapped_column(Text, default="")
    attempts_exhausted: Mapped[bool] = mapped_column(Boolean, default=False)
    generation_calls: Mapped[int] = mapped_column(Integer, default=0)
    spent_cad: Mapped[float] = mapped_column(Float, default=0.0)
    outfit_id: Mapped[str] = mapped_column(String(80), default="")
    # {stage: {"inputs", "outputs", "evidence", "cost_cad", "at"}}
    stages: Mapped[dict] = mapped_column(JSON, default=dict)
    card: Mapped[dict] = mapped_column(JSON, default=dict)
    owner_decision: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImageCandidate(Base):
    __tablename__ = "image_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    run_key: Mapped[str] = mapped_column(String(200), default="", index=True)
    # autonomous | owner_submitted. Recorded for provenance and learning; no gate reads it.
    method: Mapped[str] = mapped_column(String(20), index=True)
    provenance_kind: Mapped[str] = mapped_column(String(60))
    slug: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[str] = mapped_column(String(20), default="")
    release: Mapped[str] = mapped_column(String(80), default="")
    listing: Mapped[str] = mapped_column(String(120), default="", index=True)
    role: Mapped[str] = mapped_column(String(40), default="", index=True)
    stage: Mapped[str] = mapped_column(String(40), default="")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    provider: Mapped[str] = mapped_column(String(80), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    prompt_sha256: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(80), default="")
    references: Mapped[list] = mapped_column(JSON, default=list)
    laura_present: Mapped[bool] = mapped_column(Boolean, default=False)
    outfit_id: Mapped[str] = mapped_column(String(80), default="")
    cost_cad: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_basis: Mapped[str] = mapped_column(String(200), default="")
    latency_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    binding: Mapped[dict] = mapped_column(JSON, default=dict)
    checks: Mapped[dict] = mapped_column(JSON, default=dict)
    technical_status: Mapped[str] = mapped_column(String(20), default="UNKNOWN", index=True)
    publishable: Mapped[bool] = mapped_column(Boolean, default=False)
    # accepted | rejected | unverified | provider_error
    outcome: Mapped[str] = mapped_column(String(20), default="unverified", index=True)
    failure_categories: Mapped[list] = mapped_column(JSON, default=list)
    # Owner-submitted only: the owner's visual approval. A separate field that never feeds
    # `technical_status` or `publishable`.
    owner_visual_approval: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    submitted_by: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


_TABLES = (LauraOutfit.__table__, ImageProductionRun.__table__, ImageCandidate.__table__)
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
