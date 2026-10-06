"""Closed economic classes and creation stages for every ledger row (F-303, F-320).

`CostEntry.purpose` is a free-form task key, so "what did development cost versus what does
running the shop cost" was a reading of strings. This is the closed vocabulary the ledger is
read through: every row maps to exactly one ECONOMIC CLASS -- and one-time creation is kept
apart from recurring operation -- and creation rows to one STAGE of making a product. A
purpose the table does not know is `unclassified` and counted, never dropped or guessed, so a
new purpose shows up as a gap rather than as somebody else's cost.
"""
from __future__ import annotations

import re
from datetime import datetime

DEVELOPMENT, BENCHMARK, CREATION, LISTING, RECURRING, SUPPORT, ADS, PLATFORM, UNCLASSIFIED = (
    "development", "benchmark", "one_time_creation", "listing", "recurring_observation",
    "support", "ads", "platform", "unclassified")
CLASSES = (DEVELOPMENT, BENCHMARK, CREATION, LISTING, RECURRING, SUPPORT, ADS, PLATFORM,
           UNCLASSIFIED)
ONE_TIME = frozenset({DEVELOPMENT, BENCHMARK, CREATION, LISTING})
STAGES = ("concept", "engineering", "certification", "imagery", "listing", "judging")

# purpose (without its @version) -> (class, stage or None)
PURPOSES: dict[str, tuple[str, str | None]] = {
    "concept_generation": (CREATION, "concept"),
    "concept_ideation": (CREATION, "concept"),
    "concept.naming": (CREATION, "concept"),
    "creative.concept_field": (CREATION, "concept"),
    "creative_evaluation": (CREATION, "judging"),
    "creative.blinded_appeal": (CREATION, "judging"),
    "construction_reading": (CREATION, "engineering"),
    "pattern_validation": (CREATION, "certification"),
    "asset_inspection": (CREATION, "judging"),
    "image.generate": (CREATION, "imagery"),
    "model_tournament": (CREATION, "imagery"),
    "listing_copy": (LISTING, "listing"),
    "listing.polish": (LISTING, "listing"),
    "listing_classify": (LISTING, "listing"),
    "listing_mechanisms": (LISTING, "listing"),
    "gallery_observation": (RECURRING, None),
    "seasonal_signal": (RECURRING, None),
    "topic_filing": (RECURRING, None),
    "review.mining": (RECURRING, None),
    "search_grid_tournament": (RECURRING, None),
    "benchmark_challenge": (BENCHMARK, None),
    "image_benchmark_judging": (BENCHMARK, None),
    "model.probe": (PLATFORM, None),
    "vision.probe": (PLATFORM, None),
    "image.probe": (PLATFORM, None),
    "image.reference_probe": (PLATFORM, None),
    "culture.probe": (PLATFORM, None),
    "swarm.lane": (DEVELOPMENT, None),
}
_KIND_CLASS = {"ads": ADS, "paid_media": ADS, "support": SUPPORT}


def classify(purpose: str | None, kind: str | None = None) -> dict:
    """{economic_class, stage, one_time} for one ledger row."""
    if (kind or "") in _KIND_CLASS:
        cls, stage = _KIND_CLASS[kind], None
    else:
        key = re.sub(r"@\d+$", "", str(purpose or "").strip())
        cls, stage = PURPOSES.get(key, (UNCLASSIFIED, None))
        if cls == UNCLASSIFIED and (kind or "") == "image":
            cls, stage = CREATION, "imagery"
    return {"economic_class": cls, "stage": stage, "one_time": cls in ONE_TIME}


def by_class(rows) -> dict:
    out = {c: {"cad": 0.0, "calls": 0} for c in CLASSES}
    for r in rows:
        c = classify(getattr(r, "purpose", ""), getattr(r, "kind", ""))["economic_class"]
        out[c]["cad"] = round(out[c]["cad"] + float(r.amount_cad or 0.0), 6)
        out[c]["calls"] += 1
    one_time = round(sum(v["cad"] for k, v in out.items() if k in ONE_TIME), 6)
    recurring = round(sum(v["cad"] for k, v in out.items()
                          if k not in ONE_TIME and k != UNCLASSIFIED), 6)
    return {"classes": out, "one_time_cad": one_time, "recurring_cad": recurring,
            "unclassified_cad": out[UNCLASSIFIED]["cad"],
            "unclassified_purposes": sorted({str(getattr(r, "purpose", "") or "")
                                             for r in rows
                                             if classify(getattr(r, "purpose", ""),
                                                         getattr(r, "kind", ""))
                                             ["economic_class"] == UNCLASSIFIED})}


def product_creation_cost(db, product_slug: str, *, since: datetime | None = None) -> dict:
    """F-320: what making one product cost, by stage and by provider, from its ledger rows.

    Recorded exposure, labelled: rows priced from list prices are `assumed`, and spend that
    belongs to the product but no known stage is `unstaged` rather than spread over stages."""
    from sqlalchemy import select

    from ..core.models import CostEntry

    with db.session() as s:
        q = select(CostEntry).where(CostEntry.product_slug == product_slug)
        if since is not None:
            q = q.where(CostEntry.at >= since)
        rows = list(s.scalars(q))
    stages = {st: 0.0 for st in STAGES}
    stages["unstaged"] = 0.0
    providers: dict[str, float] = {}
    for r in rows:
        c = classify(r.purpose, r.kind)
        key = c["stage"] or "unstaged"
        stages[key] = round(stages[key] + float(r.amount_cad or 0.0), 6)
        p = r.provider or "unknown"
        providers[p] = round(providers.get(p, 0.0) + float(r.amount_cad or 0.0), 6)
    return {"product_slug": product_slug, "calls": len(rows),
            "total_cad": round(sum(float(r.amount_cad or 0.0) for r in rows), 6),
            "by_stage": stages, "by_provider": providers,
            "basis": "recorded" if rows else "unknown",
            "note": ("list-price exposure from the ledger, not provider invoices"
                     if rows else "no ledger rows attributed to this product")}
