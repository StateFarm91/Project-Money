"""F-565 Marketplace Insights Opportunity Score (W4-INTELREC C05).

"For researched terms, combine buyer searches, competing listings, trend direction, Product
Truth feasibility, policy eligibility, expected margin and catalogue fit. Keep raw Etsy
evidence separate from the derived score."

Input: the owner-recorded Marketplace Insights snapshots (`intel.insights`, Etsy's own figures
read in Shop Manager -- pasted, never fetched). Output, per keyword:

* `raw` -- the newest snapshot exactly as recorded (searches, listings, trend, who, when),
  never altered or blended;
* `derived` -- each component with where it came from, and the score.

Components (every one UNKNOWN, never 0, when it has no source):
* demand ratio: searches / competing listings (both Etsy's Insights figures);
* trend factor: up 1.2, flat 1.0, down 0.8; `unknown` is left out, and said so;
* Product Truth feasibility: a radar seed whose words match the keyword, in a form this
  company has prototype geometry for (`creative.prototype.geometry_for`);
* policy eligibility: no protected (IP) term in the keyword (`gates.policy` IP list);
* expected margin: the matched seed's price through `commerce.pricing.net_contribution`,
  against `MIN_NET_CONTRIBUTION_CAD`;
* catalogue fit: the matched seed's category belongs to a storefront section.

A keyword that is ineligible, infeasible or below the margin floor gets no score, with the
reason; one with no search count is UNKNOWN. Reads rows; writes nothing; CA$0.
"""
from __future__ import annotations

import re

UNKNOWN = "UNKNOWN"
TREND_FACTOR = {"up": 1.2, "flat": 1.0, "down": 0.8}
_WORD = re.compile(r"[a-z]+")
_STOP = frozenset({"crochet", "pattern", "patterns", "pdf", "the", "a", "an", "and", "for",
                   "of", "with", "to", "in", "easy", "free"})


def _words(text: str) -> set[str]:
    return {w.rstrip("s") for w in _WORD.findall(str(text or "").lower()) if w not in _STOP}


def _latest_per_keyword(db) -> list[dict]:
    from . import insights

    seen, out = set(), []
    for row in insights.snapshots(db):                      # newest first
        if row["keyword"] in seen:
            continue
        seen.add(row["keyword"])
        out.append(row)
    return out


def _match_seed(keyword: str):
    from ..radar.opportunity import POOL

    want = _words(keyword)
    if not want:
        return None
    best, best_n = None, 0
    for seed in POOL:
        have = _words(f"{seed.title} {seed.category.replace('_', ' ')}")
        n = len(want & have)
        if n > best_n and n >= max(1, len(want) // 2 + len(want) % 2):
            best, best_n = seed, n
    return best


# A radar seed category -> the prototype form whose geometry decides whether it can be built
# and checked today. A category not named here is UNKNOWN, never assumed buildable.
FORM_OF_CATEGORY: dict[str, str] = {
    "blanket": "rectangle_throw", "mosaic_blanket": "rectangle_throw",
    "graphghan": "rectangle_throw", "baby": "rectangle_throw", "basket": "basket",
    "ornament": "ornament", "stocking": "stocking", "runner": "runner",
    "placemat": "flat_panel", "coaster": "coaster", "pillow": "pillow",
    "wall_decor": "wall_hanging", "hat": "hat", "bag": "bag", "scarf": "scarf",
    "shawl": "draped_garment", "amigurumi": "toy",
}


def _feasible(seed) -> dict:
    from ..creative.prototype import PrototypeRefused, geometry_for

    if seed is None:
        return {"value": None, "status": UNKNOWN,
                "why": "no radar seed matches this keyword, so feasibility is not judged"}
    form = FORM_OF_CATEGORY.get(seed.category)
    if form is None:
        return {"value": None, "status": UNKNOWN, "seed": seed.slug,
                "why": f"category {seed.category!r} has no prototype form"}
    try:
        geometry_for(form)
    except (PrototypeRefused, ValueError) as exc:
        return {"value": False, "status": "MEASURED", "seed": seed.slug, "form": form,
                "why": str(exc)[:200]}
    return {"value": True, "status": "MEASURED", "seed": seed.slug, "form": form,
            "why": f"{form} has prototype geometry"}


def _policy(keyword: str) -> dict:
    from ..gates.policy import _IP_TERMS

    low = f" {keyword.lower()} "
    hits = [t for t in _IP_TERMS if re.search(rf"\b{re.escape(str(t).lower())}\b", low)]
    return {"value": not hits, "status": "MEASURED", "protected_terms": hits,
            "why": "names a protected term" if hits else "no protected term"}


def _margin(seed) -> dict:
    from ..commerce import pricing

    if seed is None:
        return {"value": None, "status": UNKNOWN, "why": "no matched seed price"}
    net = pricing.net_contribution(float(seed.price_cad))
    amount = float(net["net_contribution"]["amount"])
    return {"value": round(amount, 2), "status": "MEASURED", "price_cad": seed.price_cad,
            "clears_floor": amount >= pricing.MIN_NET_CONTRIBUTION_CAD,
            "floor_cad": pricing.MIN_NET_CONTRIBUTION_CAD,
            "basis": net["foreign_share"]["basis"]}


def _fit(seed) -> dict:
    from ..brand.storefront import SECTIONS

    if seed is None:
        return {"value": None, "status": UNKNOWN, "why": "no matched seed"}
    section = next((s.slug for s in SECTIONS if seed.category in s.categories), None)
    return {"value": section is not None, "status": "MEASURED", "section": section,
            "why": (f"belongs to the {section} section" if section else
                    f"category {seed.category!r} belongs to no storefront section")}


def score_keyword(snapshot: dict) -> dict:
    """One keyword: the raw snapshot untouched, and the derived components and score."""
    raw = dict(snapshot)
    searches, listings = raw.get("search_count"), raw.get("listing_count")
    seed = _match_seed(raw["keyword"])
    trend = raw.get("trend_direction") or "unknown"
    d = {
        "demand_ratio": ({"value": round(searches / max(int(listings), 1), 4),
                          "status": "MEASURED", "basis": "Insights searches / listings"}
                         if searches is not None and listings is not None else
                         {"value": None, "status": UNKNOWN,
                          "why": "needs both the search and listing counts"}),
        "trend": ({"value": TREND_FACTOR[trend], "status": "MEASURED", "direction": trend}
                  if trend in TREND_FACTOR else
                  {"value": None, "status": UNKNOWN, "why": "trend not recorded; left out"}),
        "feasibility": _feasible(seed), "policy": _policy(raw["keyword"]),
        "margin": _margin(seed), "catalogue_fit": _fit(seed),
        "matched_seed": seed.slug if seed else None,
    }
    blockers = []
    if d["policy"]["value"] is False:
        blockers.append("policy: " + d["policy"]["why"])
    if d["feasibility"]["value"] is False:
        blockers.append("Product Truth: " + d["feasibility"]["why"])
    if d["margin"]["value"] is not None and not d["margin"]["clears_floor"]:
        blockers.append(f"margin CA${d['margin']['value']} below the "
                        f"CA${d['margin']['floor_cad']} floor")
    if blockers:
        d["score"] = {"value": None, "status": "INELIGIBLE", "why": "; ".join(blockers)}
    elif d["demand_ratio"]["value"] is None:
        d["score"] = {"value": None, "status": UNKNOWN, "why": d["demand_ratio"]["why"]}
    else:
        factor = d["trend"]["value"] if d["trend"]["value"] is not None else 1.0
        fit = 1.0 if d["catalogue_fit"]["value"] else 0.8 if d["catalogue_fit"]["value"] \
            is False else 1.0
        d["score"] = {"value": round(d["demand_ratio"]["value"] * factor * fit, 4),
                      "status": "DERIVED",
                      "formula": "demand_ratio x trend (1.0 when unknown) x fit (0.8 when "
                                 "the seed fits no section)",
                      "unknown_parts": sorted(k for k in ("trend", "feasibility", "margin",
                                                          "catalogue_fit")
                                              if d[k].get("value") is None)}
    return {"keyword": raw["keyword"], "raw": raw, "derived": d}


def scores(db) -> dict:
    rows = [score_keyword(s) for s in _latest_per_keyword(db)]
    ranked = sorted((r for r in rows if r["derived"]["score"]["value"] is not None),
                    key=lambda r: -r["derived"]["score"]["value"])
    return {"keywords": rows, "ranked": [r["keyword"] for r in ranked],
            "basis": "owner-recorded Marketplace Insights (raw kept apart from the score)"}
