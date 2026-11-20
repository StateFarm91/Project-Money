"""Marketing channels compared per listing and per product family, one credit per order
(F-574 Marketing Channel Attribution).

`finance.sources.table` answers "how much came from each of the four channels the first-sale
record names". F-574 asks a finer question at a finer grain: organic Etsy search, Etsy Ads,
Offsite Ads, social and Share & Save, compared *per listing and per product family*, with the
rule that one order is never credited to two channels internally.

Single credit is structural: an order is credited to the one channel its `acquisition_source`
maps to (`finance.sources.attribute` is the one evidence-backed writer of that column). The
only place a second channel could sneak in is the Offsite Ads flag, which Etsy's ledger sets
independently of the source; an order whose flag and source disagree is credited once (to its
source) and listed under `conflicts` for review -- never counted in both rows.

A product family is the catalogue category the order was recorded under (`Order.category`,
from the product seed at ingest); an order with none is `uncategorised`, never dropped.
Only countable orders are compared (`orders_ingest.countable`), the same rule the books use.
"""
from __future__ import annotations

COMPARISON_CHANNELS: tuple[str, ...] = ("organic_search", "etsy_ads", "offsite_ads", "social",
                                        "share_and_save", "owned_direct", "unattributed")

_TO_COMPARISON = {
    "etsy_organic": "organic_search", "etsy_search": "organic_search",
    "etsy_ads": "etsy_ads",
    "offsite_ads": "offsite_ads",
    "social": "social", "pinterest": "social", "instagram": "social", "tiktok": "social",
    "facebook": "social",
    "share_and_save": "share_and_save",
    "owned_direct": "owned_direct", "direct": "owned_direct", "email": "owned_direct",
    "google": "owned_direct", "seo": "owned_direct",
}


def channel_of(acquisition_source: str | None) -> str:
    return _TO_COMPARISON.get((acquisition_source or "").strip().lower(), "unattributed")


def _empty() -> dict:
    return {c: {"orders": 0, "revenue_cad": 0.0, "contribution_cad": 0.0}
            for c in COMPARISON_CHANNELS}


def _round(rows: dict) -> dict:
    for r in rows.values():
        r["revenue_cad"] = round(r["revenue_cad"], 2)
        r["contribution_cad"] = round(r["contribution_cad"], 2)
    return rows


def compare(db) -> dict:
    """Per-family and per-listing channel tables; every order credited exactly once."""
    from sqlalchemy import select

    from ..commerce import orders_ingest
    from ..core.models import Order

    families: dict[str, dict] = {}
    listings: dict[str, dict] = {}
    conflicts, credited, seen = [], 0, set()
    with db.session() as s:
        orders = orders_ingest.countable_orders(s, select(Order))
        for o in orders:
            if o.external_ref in seen:      # defensive: a ref is credited once
                continue
            seen.add(o.external_ref)
            ch = channel_of(o.acquisition_source)
            if bool(o.offsite_ad_attributed) and ch != "offsite_ads":
                conflicts.append({"order": o.external_ref, "credited_to": ch,
                                  "also_flagged": "offsite_ads",
                                  "why": "Etsy's ledger flags an Offsite Ads fee but the "
                                         "recorded source differs; credited once, to the "
                                         "source, pending review"})
            fam = (o.category or "").strip() or "uncategorised"
            for table, key in ((families, fam), (listings, o.product_slug or "unknown")):
                row = table.setdefault(key, _empty())[ch]
                row["orders"] += 1
                row["revenue_cad"] += float(o.revenue_cad or 0.0)
                row["contribution_cad"] += float(o.contribution_cad or 0.0)
            credited += 1
        total = len(orders)
    for t in (families, listings):
        for k in t:
            _round(t[k])
    credits = sum(r["orders"] for fam in families.values() for r in fam.values())
    return {
        "channels": list(COMPARISON_CHANNELS),
        "by_family": families, "by_listing": listings,
        "orders": total, "credits": credits,
        "single_credit": credits == credited == len(seen),
        "conflicts": conflicts,
        "reading": "measured" if total else "UNMEASURED",
        "why": None if total else "no countable order exists to compare",
        "note": ("one order, one channel: credited by its evidence-backed acquisition source; "
                 "unattributed is shown, never folded into organic"),
    }
