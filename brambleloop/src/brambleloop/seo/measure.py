"""The measurement hook: did a keyword decision earn anything? Honest confidence, or UNKNOWN.

Inputs (existing commerce readers' tables, read-only):

- `listing_outcomes` -- per listing per period: impressions, visits, favourites, orders,
  written only once a listing is live and a Stats export or the API says what happened.
- the owner's Etsy Stats export (`operating_readings` kind `attribution.stats`, via the
  evidence store) -- per *search term*, shop-wide. Etsy's export does not split a term by
  listing, so a term's outcome is shop-level evidence.

Attribution rules:

- A term with no Stats row is `UNKNOWN`. Never 0.
- A term with a Stats row, carried by exactly one *live* listing (one with an
  `etsy_listing_id`), is attributed to that listing with basis `estimated` (sole live carrier);
  carried by several, it is `unattributable` -- the shop-level figure is reported, not split.
- Confidence comes from the visit volume behind the figure and is capped at `moderate`:
  under 30 visits `insufficient`, under 100 `low`, otherwise `moderate`. A single shop-level
  export never supports `high`.
- Listing-level outcomes are `measured` (they are Etsy's counts) but are never divided among
  the listing's tags: that split would be invented.
"""
from __future__ import annotations

MIN_VISITS_LOW = 30
MIN_VISITS_MODERATE = 100


def _confidence(visits) -> str:
    if visits is None:
        return "unknown"
    if visits < MIN_VISITS_LOW:
        return "insufficient"
    if visits < MIN_VISITS_MODERATE:
        return "low"
    return "moderate"


def listing_outcomes(db) -> dict[str, dict]:
    from sqlalchemy import select

    from ..core.models import ListingOutcome
    from ._db import session

    out: dict[str, dict] = {}
    try:
        with session(db) as s:
            for r in s.scalars(select(ListingOutcome)):
                o = out.setdefault(r.product_slug, {"impressions": 0, "visits": 0,
                                                    "favourites": None, "orders": None,
                                                    "periods": [], "sources": []})
                o["impressions"] += r.impressions or 0
                o["visits"] += r.visits or 0
                if r.favourites is not None:
                    o["favourites"] = (o["favourites"] or 0) + r.favourites
                if r.orders is not None:
                    o["orders"] = (o["orders"] or 0) + r.orders
                o["periods"].append(f"{r.period_start}..{r.period_end}")
                o["sources"].append(f"listing_outcomes:{r.id}")
    except Exception:  # noqa: BLE001 - no table: nothing measured
        return {}
    return out


def _live_tags(db) -> dict[str, list[str]]:
    """slug -> tags, for listings that exist on Etsy (an etsy_listing_id is recorded)."""
    from sqlalchemy import select

    from ..core.models import Listing
    from ._db import session

    try:
        with session(db) as s:
            return {r.product_slug: [t.lower() for t in (r.tags or [])]
                    for r in s.scalars(select(Listing)) if r.etsy_listing_id}
    except Exception:  # noqa: BLE001
        return {}


def attribution(db, tags_by_slug: dict[str, list[str]], *,
                evidence_rows: list[dict] | None = None) -> dict:
    """Per slug, per keyword: outcome and how confidently it can be credited."""
    from . import evidence as ev_mod

    rows = ev_mod.all_rows(db) if evidence_rows is None else evidence_rows
    ev = ev_mod.by_phrase(rows)
    outcomes = listing_outcomes(db)
    live = _live_tags(db)
    carriers: dict[str, list[str]] = {}
    for slug, tags in live.items():
        for t in tags:
            carriers.setdefault(t, []).append(slug)

    per_slug: dict[str, dict] = {}
    measured_terms = 0
    for slug, tags in sorted(tags_by_slug.items()):
        kw = []
        for t in tags:
            m = (ev.get(t.lower()) or {}).get("measured") or {}
            if "stats_impressions" not in m and "stats_visits" not in m:
                kw.append({"term": t, "status": "UNKNOWN", "basis": "unknown",
                           "why": "no Etsy Stats export row for this term"})
                continue
            measured_terms += 1
            who = carriers.get(t.lower(), [])
            visits = m.get("stats_visits")
            if who == [slug]:
                status, basis = "ATTRIBUTED", "estimated"
                why = "sole live listing carrying this tag; the export is shop-level"
            elif not who:
                status, basis = "SHOP_LEVEL_ONLY", "measured"
                why = "the term is in the export but no live listing carries it as a tag"
            else:
                status, basis = "UNATTRIBUTABLE", "measured"
                why = f"shop-level term carried by {len(who)} live listings; not split"
            kw.append({"term": t, "status": status, "basis": basis,
                       "impressions": m.get("stats_impressions"), "visits": visits,
                       "orders": m.get("stats_orders"),
                       "confidence": _confidence(visits), "why": why,
                       "sources": (ev.get(t.lower()) or {}).get("sources", [])[:5]})
        o = outcomes.get(slug)
        per_slug[slug] = {
            "listing_outcome": ({**o, "basis": "measured"} if o else
                                {"status": "UNKNOWN", "why": "no listing_outcomes row: the "
                                 "listing is not live or no Stats/API reading was recorded"}),
            "keywords": kw}
    status = "UNKNOWN" if not (outcomes or measured_terms) else "MEASURED_PARTIAL"
    return {"status": status, "per_slug": per_slug, "measured_terms": measured_terms,
            "listings_with_outcomes": len(outcomes),
            "rules": {"min_visits_low": MIN_VISITS_LOW,
                      "min_visits_moderate": MIN_VISITS_MODERATE,
                      "max_confidence": "moderate"}}
