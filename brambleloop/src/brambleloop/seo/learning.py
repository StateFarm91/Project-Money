"""Continuous search learning hooks: what each marketplace signal will teach, once it exists.

Directive section 13: "Once real data exists, continuously learn from Search Visibility,
impressions, clicks, favorites, carts, orders and conversion." Today no listing is live, so
every signal is UNKNOWN and this module says so -- it never renders a missing count as 0 and
never proposes a change from an empty table.

Signals and where they come from (read-only; existing tables):

| signal            | source                                              | funnel stage        |
|-------------------|-----------------------------------------------------|---------------------|
| impressions       | listing_outcomes.impressions (Stats / API)          | matching + ranking  |
| clicks (visits)   | listing_outcomes.visits                             | CTR                 |
| favourites        | listing_outcomes.favourites                         | conversion (intent) |
| carts             | NO SOURCE in this repo (no column, no reader)       | conversion          |
| orders            | listing_outcomes.orders                             | conversion          |
| search terms      | seo_keyword_evidence (Etsy Stats export, owner)     | matching per query  |
| Search Visibility | commerce.search_visibility items (owner readings)   | ranking (shop/listing/service) |

Diagnosis keeps the four problems separate (`strategy.FUNNEL`): a listing with few impressions
has a matching/ranking problem that no title rewrite for CTR will fix; a listing with
impressions and no visits has a CTR problem (thumbnail/title front); visits without orders is
conversion. Each diagnosis carries the sample it rests on and refuses below `MIN_*`.

The thresholds are policy constants of this department (modelled), not Etsy benchmarks: there
is no measured shop baseline yet. A stage is compared against the shop's own other listings
once at least two have enough data; until then it is reported, not judged.
"""
from __future__ import annotations

MIN_IMPRESSIONS = 200     # below: matching/ranking cannot be judged (modelled policy)
MIN_VISITS = 30           # below: conversion cannot be judged (same as seo.measure)
THRESHOLD_BASIS = "modelled policy constant (no measured shop baseline exists)"

SIGNALS = (
    {"signal": "impressions", "source": "listing_outcomes.impressions",
     "stage": "matching+ranking", "feeds": "tag/title/category re-proposal; Search "
                                           "Visibility remediation"},
    {"signal": "clicks", "source": "listing_outcomes.visits", "stage": "ctr",
     "feeds": "title-front and thumbnail challengers (Visual lane H owns thumbnails)"},
    {"signal": "favourites", "source": "listing_outcomes.favourites", "stage": "conversion",
     "feeds": "description/price/image review"},
    {"signal": "carts", "source": None, "stage": "conversion",
     "feeds": "WIRING: no carts column or reader exists; stays UNKNOWN until one does"},
    {"signal": "orders", "source": "listing_outcomes.orders", "stage": "conversion",
     "feeds": "earning terms get tag priority (seo.proposals must-include)"},
    {"signal": "search_terms", "source": "seo_keyword_evidence[etsy_stats_export]",
     "stage": "matching (per query)", "feeds": "earning terms kept; vanity terms withheld "
                                               "(seo.proposals)"},
    {"signal": "search_visibility", "source": "commerce.search_visibility",
     "stage": "ranking", "feeds": "open recommendations become SEO work items; only a later "
                                  "complete reading clears them"},
)


def _unknown(why: str) -> dict:
    return {"value": None, "status": "UNKNOWN", "basis": "unknown", "why": why}


def _measured(v, src) -> dict:
    return {"value": v, "status": "MEASURED", "basis": "measured", "sources": src}


def _search_visibility(db) -> dict:
    try:
        from ..commerce import search_visibility as sv

        if not sv.live_gate_open(db):
            return _unknown("live_listings gate closed: no shop to read Search Visibility for")
        items = sv.items(db, state=sv.OPEN)
        at = sv.latest_reading_at(db)
        if at is None:
            return _unknown("no Search Visibility reading recorded by the owner yet")
        return {"value": len(items), "status": "MEASURED", "basis": "measured",
                "open_items": items[:20], "latest_reading_at": at.isoformat(),
                "sources": ["search_visibility_items"]}
    except Exception as exc:  # noqa: BLE001
        return _unknown(f"Search Visibility unreadable ({type(exc).__name__})")


def funnel(db, slugs: list[str] | None = None) -> dict:
    """Per product: each signal measured or UNKNOWN, the rates the sample supports, and the
    stage diagnosis. Read-only."""
    from . import measure

    if slugs is None:
        from ..products import launch0 as L

        slugs = list(L.LAUNCH0_SLUGS)
    outcomes = measure.listing_outcomes(db) if db is not None else {}
    per = {}
    for slug in slugs:
        o = outcomes.get(slug)
        if not o:
            per[slug] = {s["signal"]: _unknown("no listing_outcomes row: not live or no "
                                               "Stats/API reading recorded")
                         for s in SIGNALS if s["signal"] in ("impressions", "clicks",
                                                             "favourites", "orders")}
            per[slug]["carts"] = _unknown("no carts source exists in this repository")
            per[slug]["diagnosis"] = {"stage": None, "status": "UNKNOWN",
                                      "why": "no outcome data"}
            continue
        src = o.get("sources", [])
        row = {"impressions": _measured(o["impressions"], src),
               "clicks": _measured(o["visits"], src),
               "favourites": (_measured(o["favourites"], src) if o["favourites"] is not None
                              else _unknown("favourites not recorded in the reading")),
               "orders": (_measured(o["orders"], src) if o["orders"] is not None
                          else _unknown("orders not recorded in the reading")),
               "carts": _unknown("no carts source exists in this repository")}
        row["rates"] = _rates(o)
        row["diagnosis"] = diagnose(o)
        per[slug] = row
    return {"per_product": per, "search_visibility": _search_visibility(db),
            "thresholds": {"min_impressions": MIN_IMPRESSIONS, "min_visits": MIN_VISITS,
                           "basis": THRESHOLD_BASIS},
            "signals": list(SIGNALS)}


def _rates(o: dict) -> dict:
    imp, vis = o.get("impressions") or 0, o.get("visits") or 0
    out = {}
    out["ctr"] = (round(vis / imp, 4) if imp >= MIN_IMPRESSIONS else None)
    out["ctr_basis"] = "measured" if out["ctr"] is not None else (
        f"insufficient: {imp} impressions < {MIN_IMPRESSIONS}")
    if o.get("orders") is not None and vis >= MIN_VISITS:
        out["conversion"] = round(o["orders"] / vis, 4)
        out["conversion_basis"] = "measured"
    else:
        out["conversion"] = None
        out["conversion_basis"] = (f"insufficient: {vis} visits < {MIN_VISITS}"
                                   if o.get("orders") is not None else "orders unknown")
    return out


def diagnose(o: dict) -> dict:
    """Which of the four problems the evidence points at -- one stage, with its sample."""
    imp = o.get("impressions") or 0
    vis = o.get("visits") or 0
    orders = o.get("orders")
    if imp < MIN_IMPRESSIONS:
        return {"stage": "matching_or_ranking", "status": "INSUFFICIENT_DATA"
                if imp else "LOW_EXPOSURE",
                "why": f"{imp} impressions (< {MIN_IMPRESSIONS}); a CTR or conversion "
                       "change cannot help a listing that is not being shown",
                "next": "re-check matching (title/tags/category/attributes truth + coverage); "
                        "read Search Visibility; do not touch thumbnails for this reason"}
    if vis < MIN_VISITS:
        return {"stage": "ctr", "status": "CANDIDATE",
                "why": f"{imp} impressions but {vis} visits (< {MIN_VISITS})",
                "next": "challenger thumbnail (lane H) and title-front test; matching is "
                        "not the problem"}
    if orders is None:
        return {"stage": "conversion", "status": "UNKNOWN", "why": "orders not recorded"}
    return {"stage": "conversion", "status": "OBSERVED",
            "why": f"{vis} visits, {orders} orders",
            "next": "compare against the shop's other listings once two have >= "
                    f"{MIN_VISITS} visits; description/price/image review"}


def proposals(db) -> list[dict]:
    """Learning proposals. Empty with a reason until any measured signal exists."""
    f = funnel(db)
    out = []
    for slug, row in f["per_product"].items():
        d = row.get("diagnosis") or {}
        if d.get("status") in (None, "UNKNOWN"):
            continue
        out.append({"slug": slug, "stage": d["stage"], "why": d["why"],
                    "action": d.get("next", ""), "writes_to_etsy": False,
                    "kind": "proposal"})
    sv = f["search_visibility"]
    if sv.get("status") == "MEASURED" and sv.get("value"):
        out.append({"slug": None, "stage": "ranking",
                    "why": f"{sv['value']} open Search Visibility item(s)",
                    "action": "remediate, then wait for a later complete owner reading",
                    "writes_to_etsy": False, "kind": "proposal"})
    return out
