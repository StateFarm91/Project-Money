"""Actionable search/ads recommendations (F-288).

Every search or ads recommendation names its evidence, the listings it affects, the mechanism
it expects to work through, its cost, its confidence and how to roll it back. "Improve SEO"
is not an action: `validate` refuses a recommendation whose action is one of the vague verbs
on its own, or that lacks any of the fields, and `from_stats` only ever emits validated ones.

`from_stats` reads the owner's latest Etsy Stats export (search terms with impressions,
visits and orders) and applies the routing the Final Master's acceptance tests require:

* inadequate exposure stays UNMEASURED and routes to exposure diagnosis, never to "weak";
* adequate impressions with weak clicks route to hero/title diagnosis before any budget
  escalation;
* healthy clicks with no sales route to product/value/trust/price diagnosis, not SEO.

Thresholds are `growth.portfolio`'s (MIN_IMPRESSIONS, MIN_CLICKS, BENCH_CTR,
BENCH_CONVERSION): category-typical starting points, stated as such, not invented here.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

CONFIDENCE = ("low", "medium", "high")
REQUIRED = ("action", "evidence", "affected_listings", "mechanism", "cost_cad", "confidence",
            "rollback")
# Actions that name a wish rather than a change. Matched on the whole normalised action
# after stripping filler, so "improve SEO" and "Optimise listings." are refused while
# "rewrite the title of X to lead with 'granny square blanket'" is not.
VAGUE = re.compile(
    r"^(please\s+)?(improve|optimi[sz]e|boost|increase|fix|enhance|work on|grow)\b"
    r"(\s+(the|our|shop|listing|listings|seo|search|ranking|rankings|visibility|traffic|"
    r"conversion|ads|sales|ctr|performance|keywords?))*\s*\.?$", re.I)
MIN_ACTION_WORDS = 5

EXPOSURE = "exposure_diagnosis"
CLICK = "click_diagnosis"
CONVERSION = "conversion_diagnosis"
HOLD = "hold"


class RecommendationRefused(ValueError):
    """A recommendation missing a required field, or one that is not an action."""


@dataclass
class Recommendation:
    action: str
    evidence: list[str]
    affected_listings: list[str]
    mechanism: str
    cost_cad: float
    confidence: str
    rollback: str
    route: str = ""
    subject: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def validate(rec: Recommendation | dict) -> Recommendation:
    d = rec.to_dict() if isinstance(rec, Recommendation) else dict(rec)
    missing = [k for k in REQUIRED if d.get(k) in (None, "", [], ())]
    if missing:
        raise RecommendationRefused(f"recommendation lacks {missing} (F-288)")
    action = " ".join(str(d["action"]).split())
    if VAGUE.match(action) or len(action.split()) < MIN_ACTION_WORDS:
        raise RecommendationRefused(
            f"{action!r} is not an action: name the change, the listing and the lever (F-288)")
    if d["confidence"] not in CONFIDENCE:
        raise RecommendationRefused(f"confidence must be one of {CONFIDENCE}")
    try:
        cost = float(d["cost_cad"])
    except (TypeError, ValueError) as exc:
        raise RecommendationRefused("cost_cad must be a number (0 when free)") from exc
    if cost < 0:
        raise RecommendationRefused("cost_cad cannot be negative")
    if not all(str(x).strip() for x in d["evidence"]) or not all(
            str(x).strip() for x in d["affected_listings"]):
        raise RecommendationRefused("evidence and affected listings must be non-empty strings")
    fields = {k: d.get(k) for k in Recommendation.__dataclass_fields__}
    fields["cost_cad"] = cost
    fields["evidence"] = [str(x) for x in d["evidence"]]
    fields["affected_listings"] = [str(x) for x in d["affected_listings"]]
    fields["notes"] = list(d.get("notes") or [])
    fields["route"] = str(d.get("route") or "")
    fields["subject"] = str(d.get("subject") or "")
    return Recommendation(**fields)


def route(impressions: int | None, visits: int | None, orders: int | None) -> tuple[str, str]:
    """(route, why) for one subject's funnel, by the acceptance-test routing."""
    from ..growth.portfolio import BENCH_CONVERSION, BENCH_CTR, MIN_CLICKS, MIN_IMPRESSIONS

    imp = impressions or 0
    if imp < MIN_IMPRESSIONS:
        return EXPOSURE, (f"{imp} impressions against a floor of {MIN_IMPRESSIONS}: UNMEASURED, "
                          f"not weak")
    ctr = (visits or 0) / imp
    if (visits or 0) < MIN_CLICKS and ctr < BENCH_CTR:
        return CLICK, (f"CTR {ctr:.3%} over {imp} impressions is under the category starting "
                       f"point {BENCH_CTR:.1%}")
    if (visits or 0) < MIN_CLICKS:
        return EXPOSURE, f"{visits or 0} visits against a floor of {MIN_CLICKS}: UNMEASURED"
    conv = (orders or 0) / visits if visits else 0.0
    if orders is None:
        return HOLD, "the export carries no order column; conversion is UNMEASURED"
    if conv < BENCH_CONVERSION:
        return CONVERSION, (f"{visits} visits and {orders} order(s): conversion {conv:.2%} is "
                            f"under the category starting point {BENCH_CONVERSION:.1%}")
    return HOLD, f"CTR {ctr:.2%} and conversion {conv:.2%} are at or above the starting points"


def _affected(term: str, listings: list[dict]) -> list[str]:
    t = term.lower().strip()
    return sorted({f"{l['slug']}@{l['version']}" for l in listings
                   if t and (t in [str(x).lower() for x in l.get("tags") or []]
                             or t in str(l.get("title") or "").lower())})


def _build(term: str, row: dict, affected: list[str], why: str, rt: str) -> Recommendation:
    ev = [f"Etsy Stats export: '{term}' impressions={row.get('impressions')}, "
          f"visits={row.get('visits')}, orders={row.get('orders')}", why]
    first = affected[0]
    if rt == EXPOSURE:
        return Recommendation(
            action=(f"Diagnose exposure for '{term}' on {first}: check indexing, category and "
                    f"attribute match before judging the listing"),
            evidence=ev, affected_listings=affected,
            mechanism=("more qualified impressions come from Etsy matching the listing to the "
                       "query (category, attributes, title/tag phrase); nothing is judged weak "
                       "until the exposure floor is met"),
            cost_cad=0.0, confidence="low",
            rollback="diagnosis only; nothing on the listing changes", route=rt, subject=term)
    if rt == CLICK:
        return Recommendation(
            action=(f"Challenge the hero frame and the first 40 title characters of {first} "
                    f"for '{term}' at thumbnail size before any ad budget"),
            evidence=ev, affected_listings=affected,
            mechanism=("searchers who see the thumbnail and title do not choose it; a clearer "
                       "truthful first frame or a title that leads with the query raises CTR"),
            cost_cad=0.0, confidence="medium",
            rollback=("restore the previous hero ordering and title from the listing's recorded "
                      "version; the search certificate is re-issued for the restored content"),
            route=rt, subject=term,
            notes=["budget escalation is refused while clicks are weak (acceptance test)"])
    return Recommendation(
        action=(f"Review product value, trust and price for {first} where '{term}' brings "
                f"clicks without sales; do not change SEO first"),
        evidence=ev, affected_listings=affected,
        mechanism=("buyers arrive and leave: the offer (price, what the pattern makes, photos "
                   "of the finished object, reviews, policies) is the lever, not the query"),
        cost_cad=0.0, confidence="medium",
        rollback="any price or copy change is recorded with its previous value and reverted "
                 "by the same pricing/listing path",
        route=rt, subject=term)


def from_stats(db) -> dict:
    """Validated recommendations from the latest Stats export, routed per acceptance tests."""
    from . import demand, visibility

    stats = visibility.latest_stats(db)
    if not stats:
        return {"status": "UNMEASURED", "recommendations": [], "refused": [],
                "why": "no Etsy Stats export has been ingested (/api/attribution/stats)"}
    listings = demand._opening_listings(db)
    recs, refused, unlinked = [], [], []
    for row in (stats.get("joined") or {}).get("terms") or []:
        term = str(row.get("term") or "")
        rt, why = route(row.get("impressions"), row.get("visits"), row.get("orders"))
        if rt == HOLD:
            continue
        affected = _affected(term, listings)
        if not affected:
            unlinked.append(term)
            continue
        try:
            recs.append(validate(_build(term, row, affected, why, rt)).to_dict())
        except RecommendationRefused as exc:
            refused.append({"term": term, "why": str(exc)})
    return {"status": "measured", "period": stats.get("period_key"),
            "recommendations": recs[:25], "refused": refused[:10],
            "terms_not_linked_to_a_listing": unlinked[:20],
            "rule": "every recommendation names evidence, affected listings, mechanism, cost, "
                    "confidence and rollback (F-288)"}
