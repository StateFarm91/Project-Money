"""Per-operation cost attribution columns the ledger row itself does not carry (F-304).

`CostEntry` holds provider, model, job, agent, product, purpose, tokens, estimate and time.
Four dimensions the Final Master asks for were missing: the **listing** a call was spent on,
the **image count** it billed or looked at, the **provider-observed actual** cost, and an
**evidence reference** tying the row to the record that proves it. They live here, one row
per cost entry, written by the single ledger writer (`spend_report.record`) in the same
transaction, so they cannot be optional by accident any more than the five columns were.

A sidecar rather than new `cost_entries` columns because `core/models.py` belongs to the
integrator; `create_all` picks the table up when this module is imported, and
`ensure_table` creates it on a database made before it existed.

Honesty rules, each enforced below rather than promised:

* **UNKNOWN is never 0.** `listing_id`, `image_count` and `observed_cad` are NULL when not
  known. A text call with no image hint has `image_count` NULL, not 0, because nothing
  proved it carried none.
* **Estimated is not actual.** `CostEntry.amount_cad` is what this system *recorded* at its
  own (assumed list) prices. `observed_cad` is only ever a figure a provider reported, and is
  written only by an explicit caller or by provider settlement (`ops.provider_accounts`).
* **A listing is resolved, not guessed.** The product's latest `Listing` row is the listing;
  a product with none has no listing yet and says so.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow

IMAGE_UNIT = "image"
CALL_UNIT = "call"

# How each figure was obtained, so a reader can tell a reading from an inference.
LISTING_RESOLVED = "resolved_from_product_listing"
LISTING_EXPLICIT = "explicit"
LISTING_NONE_YET = "product_has_no_listing_yet"
LISTING_SHARED = "shared_spend_has_no_listing"

IMAGES_RENDERED = "images_rendered_by_this_row"
IMAGES_SENT = "images_sent_with_this_call"
IMAGES_UNKNOWN = "unknown"


class CostAttribution(Base):
    """The F-304 dimensions of one `CostEntry`."""

    __tablename__ = "cost_attributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    cost_entry_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    listing_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    etsy_listing_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    listing_basis: Mapped[str] = mapped_column(String(40), default="")
    image_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_basis: Mapped[str] = mapped_column(String(40), default=IMAGES_UNKNOWN)
    units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="")
    observed_cad: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_basis: Mapped[str] = mapped_column(String(60), default="")
    evidence_ref: Mapped[str] = mapped_column(String(200), default="", index=True)


_LOCK = threading.Lock()
_FLAG = "_brambleloop_cost_attributions_ready"


def ensure_table(db) -> None:
    """Create the sidecar if missing. `db` is a `Database` or an open SQLAlchemy session."""
    engine = db.engine if hasattr(db, "engine") else db.get_bind()
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if getattr(engine, _FLAG, False):
            return
        Base.metadata.create_all(engine, tables=[CostAttribution.__table__], checkfirst=True)
        setattr(engine, _FLAG, True)


def _count(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, (list, tuple)):
        return len(value)
    if isinstance(value, str) and value:
        return 1
    return None


def image_count_of(kind: str, detail: dict) -> tuple[int | None, str]:
    """How many images this row billed (a render) or carried (a vision call), or UNKNOWN."""
    for key in ("image_count", "images"):
        n = _count(detail.get(key))
        if n is not None:
            return n, (IMAGES_RENDERED if kind == IMAGE_UNIT else IMAGES_SENT)
    if kind == IMAGE_UNIT:
        # `gateway.images.record_render` writes exactly one row per billed render.
        return 1, IMAGES_RENDERED
    if detail.get("image"):
        return 1, IMAGES_SENT
    return None, IMAGES_UNKNOWN


def resolve_listing(session, product_slug: str, detail: dict,
                    listing_id: int | None) -> tuple[int | None, str, str]:
    """(listing id, etsy listing id, basis). Never invents a listing."""
    from sqlalchemy import select

    from ..core.models import Listing

    if listing_id is not None:
        row = session.get(Listing, int(listing_id))
        return int(listing_id), (row.etsy_listing_id or "") if row else "", LISTING_EXPLICIT
    explicit = detail.get("listing_id")
    if isinstance(explicit, int) and not isinstance(explicit, bool):
        row = session.get(Listing, explicit)
        return explicit, (row.etsy_listing_id or "") if row else "", LISTING_EXPLICIT
    if not product_slug:
        return None, "", LISTING_SHARED
    row = session.scalars(select(Listing).where(Listing.product_slug == product_slug)
                          .order_by(Listing.id.desc()).limit(1)).first()
    if row is None:
        return None, "", LISTING_NONE_YET
    return row.id, row.etsy_listing_id or "", LISTING_RESOLVED


def evidence_of(detail: dict, job_id: int | None, evidence_ref: str) -> str:
    if evidence_ref:
        return str(evidence_ref)[:200]
    for key, label in (("paid_call_key", "paid_call"), ("reservation_id", "reservation")):
        if detail.get(key):
            return f"{label}:{detail[key]}"[:200]
    return f"job:{job_id}" if job_id else ""


def write(session, *, cost_entry_id: int, kind: str, product_slug: str, detail: dict,
          job_id: int | None, listing_id: int | None = None, image_count: int | None = None,
          observed_cad: float | None = None, observed_basis: str = "",
          evidence_ref: str = "") -> CostAttribution:
    """Called by `spend_report.record` inside its own transaction."""
    lid, etsy, lbasis = resolve_listing(session, product_slug, detail, listing_id)
    if image_count is not None:
        images, ibasis = int(image_count), (IMAGES_RENDERED if kind == IMAGE_UNIT
                                           else IMAGES_SENT)
    else:
        images, ibasis = image_count_of(kind, detail)
    if observed_cad is not None and not observed_basis:
        raise ValueError("an observed (provider-reported) cost must name where it was read")
    row = CostAttribution(
        cost_entry_id=cost_entry_id, listing_id=lid, etsy_listing_id=etsy,
        listing_basis=lbasis, image_count=images, image_basis=ibasis,
        units=(images if kind == IMAGE_UNIT else 1),
        unit=(IMAGE_UNIT if kind == IMAGE_UNIT else CALL_UNIT),
        observed_cad=(None if observed_cad is None else round(float(observed_cad), 8)),
        observed_basis=observed_basis[:60],
        evidence_ref=evidence_of(detail, job_id, evidence_ref))
    session.add(row)
    return row


def report(db, *, days: int = 30, now: datetime | None = None) -> dict:
    """Spend by listing, images billed, and recorded vs provider-observed, over a window.

    Reconciles: per-listing + no-listing-yet + shared + rows without a sidecar (written
    before F-304) equals the window's recorded total.
    """
    from sqlalchemy import select

    from ..core.models import CostEntry

    from contextlib import nullcontext

    ensure_table(db)
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    reader = db.session() if callable(getattr(db, "session", None)) else nullcontext(db)
    with reader as s:
        pairs = s.execute(select(CostEntry, CostAttribution).outerjoin(
            CostAttribution, CostAttribution.cost_entry_id == CostEntry.id)
            .where(CostEntry.at >= since)).all()
        by_listing: dict[str, dict] = {}
        buckets = {LISTING_NONE_YET: 0.0, LISTING_SHARED: 0.0, "no_sidecar": 0.0}
        images_rendered = 0
        image_cad = 0.0
        images_unknown_rows = 0
        observed_rows, observed_cad, recorded_for_observed = 0, 0.0, 0.0
        total = 0.0
        for entry, attr in pairs:
            amt = float(entry.amount_cad or 0.0)
            total += amt
            if attr is None:
                buckets["no_sidecar"] += amt
                continue
            if attr.listing_id is not None:
                key = str(attr.listing_id)
                b = by_listing.setdefault(key, {
                    "listing_id": attr.listing_id, "etsy_listing_id": attr.etsy_listing_id,
                    "product_slug": entry.product_slug, "cad": 0.0, "calls": 0,
                    "images_rendered": 0})
                b["cad"] += amt
                b["calls"] += 1
                if attr.image_basis == IMAGES_RENDERED:
                    b["images_rendered"] += int(attr.image_count or 0)
            else:
                buckets[attr.listing_basis if attr.listing_basis in buckets
                        else LISTING_SHARED] += amt
            if attr.image_basis == IMAGES_RENDERED:
                images_rendered += int(attr.image_count or 0)
                image_cad += amt
            elif attr.image_basis == IMAGES_UNKNOWN:
                images_unknown_rows += 1
            if attr.observed_cad is not None:
                observed_rows += 1
                observed_cad += float(attr.observed_cad)
                recorded_for_observed += amt
    listings = sorted(({**v, "cad": round(v["cad"], 6)} for v in by_listing.values()),
                      key=lambda r: -r["cad"])
    accounted = sum(r["cad"] for r in listings) + sum(buckets.values())
    return {
        "days": days,
        "recorded_cad": round(total, 6),
        "basis": "recorded at this system's assumed list prices (not an invoice)",
        "by_listing": listings,
        "no_listing_yet_cad": round(buckets[LISTING_NONE_YET], 6),
        "shared_cad": round(buckets[LISTING_SHARED], 6),
        "written_before_f304_cad": round(buckets["no_sidecar"], 6),
        "reconciles": abs(accounted - total) < 1e-6,
        "images_rendered": images_rendered,
        "cad_per_rendered_image": (round(image_cad / images_rendered, 6)
                                   if images_rendered else None),
        "rows_with_image_count_unknown": images_unknown_rows,
        "provider_observed": {
            "rows": observed_rows,
            "observed_cad": round(observed_cad, 6) if observed_rows else None,
            "recorded_cad_for_those_rows": (round(recorded_for_observed, 6)
                                            if observed_rows else None),
            "why_none": ("" if observed_rows else
                         "no provider-reported per-call cost has been read: the recorded "
                         "figures are estimates at list price, not observed billing "
                         "(provider usage access is an owner action, F-106)")},
    }
