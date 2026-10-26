"""Baby & children's products as a first-class, measured product family (W4-AGENTS cluster C1).

The children's rows of the Final Master were satisfied only by a curated Launch-0 list and
hand-set radar priors. This module makes each one a deterministic reading over our own rows
(the radar pool, Launch-0 candidates, certified releases, and the competitor listings already
observed -- used as counts only, never copied):

* F-351 Priority Product Family: `PRIORITY_FAMILY` is consumed by `portfolio(db)`, which reports
  the children's family's research coverage, launch mix, storefront architecture and seasonal
  plan as one object (`intel.children_portfolio`, market_radar, daily).
* F-353 Core Category Coverage: `CORE_CATEGORIES` is the row's own list; `coverage(db)` says, per
  category, how much research evidence exists and names every gap as a research item.
* F-358 Gender-Neutral & Style Segments: `style_segments(db)` counts gender-neutral, gendered and
  style-specific demand in observed children's listings. It never infers a palette or aesthetic.
* F-365 Store Architecture: `architecture(db)` proposes a Baby & Kids collection only when
  catalogue depth justifies it (`BABY_KIDS_DEPTH` certified children's products), navigated by
  product family and age range where the product records support it.
* F-366 Launch Mix Evaluation: `launch_mix(db)` scores the opening catalogue across the five
  segments the row names and fails explicitly when children's products were not considered.
* F-359 (children's sibling sets) is read from `creative.family_engine` for children's members.

Nothing here writes, spends or contacts anyone; `portfolio` returns data for one reading.
"""
from __future__ import annotations

import re

PRIORITY_FAMILY = "baby_children"
UNMEASURED = "UNMEASURED"
BABY_KIDS_DEPTH = 4          # certified children's products before a dedicated collection

# F-353, verbatim from the row: "newborn/baby cardigans, toddler/children's cardigans,
# sweaters, jackets, dresses, tops/vests, hooded pieces, matching sets, bonnets/hats,
# decorative collars, blankets, seasonal/holiday garments, unisex designs ..."
CORE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "baby_cardigan": (r"\b(baby|newborn|infant)\b.*\bcardigan", r"\bcardigan\b.*\b(baby|newborn)"),
    "child_cardigan": (r"\b(toddler|child|children'?s|kids?)\b.*\bcardigan",),
    "sweater": (r"\b(baby|toddler|child|children'?s|kids?)\b.*\b(sweater|jumper|pullover)",),
    "jacket": (r"\b(baby|toddler|child|children'?s|kids?)\b.*\b(jacket|coat)",),
    "dress": (r"\b(baby|toddler|girls?|child|children'?s|kids?)\b.*\bdress",),
    "top_vest": (r"\b(baby|toddler|child|children'?s|kids?)\b.*\b(top|vest|tank)",),
    "hooded": (r"\b(baby|toddler|child|children'?s|kids?)\b.*\bhood",),
    "matching_set": (r"\b(baby|toddler|child|children'?s|kids?)\b.*\b(set|matching)",),
    "bonnet_hat": (r"\bbonnet\b", r"\b(baby|toddler|child|children'?s|kids?)\b.*\b(hat|beanie)"),
    "collar": (r"\bcollar\b",),
    "blanket": (r"\b(baby|nursery|toddler)\b.*\b(blanket|afghan|throw)",),
    "seasonal_garment": (r"\b(christmas|holiday|halloween|easter)\b.*\b(baby|toddler|kids?)",),
    "unisex": (r"\b(unisex|gender[- ]neutral)\b",),
}
_CHILD = re.compile(r"\b(baby|babies|newborn|infant|toddler|child|children'?s|kids?|nursery|"
                    r"bonnet|girls?|boys?)\b", re.I)
_NEUTRAL = re.compile(r"\b(unisex|gender[- ]neutral|neutral)\b", re.I)
_GENDERED = re.compile(r"\b(girls?|boys?|princess|little man|little lady)\b", re.I)
_STYLE = re.compile(r"\b(boho|vintage|heirloom|modern|minimalist|scandi|classic|preppy|"
                    r"rustic|cottagecore)\b", re.I)

# F-366's five segments, from our own category labels.
SEGMENTS = ("baby_children", "adult_garments", "home_decor", "seasonal", "accessories")
_SEGMENT_OF_CATEGORY = {
    "baby": "baby_children", "nursery": "baby_children",
    "garment": "adult_garments", "shawl": "adult_garments",
    "blanket": "home_decor", "mosaic_blanket": "home_decor", "graphghan": "home_decor",
    "basket": "home_decor", "coaster": "home_decor", "pillow": "home_decor",
    "placemat": "home_decor", "runner": "home_decor", "wall_decor": "home_decor",
    "flower": "home_decor", "pet": "home_decor",
    "ornament": "seasonal", "stocking": "seasonal", "seasonal_decor": "seasonal",
    "wedding": "seasonal",
    "hat": "accessories", "scarf": "accessories", "bag": "accessories",
    "amigurumi": "accessories",
    # Launch-0 candidates carry a pod, not a category (intel.pods.PODS keys).
    "blankets": "home_decor", "kitchen_bath": "home_decor", "collections": "home_decor",
    "ornaments": "seasonal", "stockings": "seasonal", "seasonal_gift": "seasonal",
    "garments": "adult_garments", "hats": "accessories", "bags": "accessories",
}


def is_children(*, category: str = "", audience: str = "", title: str = "") -> bool:
    if category in ("baby", "nursery"):
        return True
    if str(audience or "").startswith(("under_", "child", "baby", "toddler")):
        return True
    return bool(_CHILD.search(title or ""))


def segment(*, category: str = "", audience: str = "", title: str = "",
            season: str | None = None) -> str:
    if is_children(category=category, audience=audience, title=title):
        return "baby_children"
    if season and _SEGMENT_OF_CATEGORY.get(category) != "adult_garments":
        return "seasonal"
    return _SEGMENT_OF_CATEGORY.get(category, "home_decor")


def _observed_titles(db) -> list[tuple[str, str]]:
    from sqlalchemy import select

    from ..core.models import BenchmarkListing

    with db.session() as s:
        return [(t or "", p or "") for t, p in s.execute(
            select(BenchmarkListing.title, BenchmarkListing.product_type)).all()]


def coverage(db) -> dict:
    """F-353: research evidence per core children's category, and every gap as an item."""
    from ..radar.opportunity import POOL

    titles = [t for t, _ in _observed_titles(db)]
    rows, gaps = [], []
    for key, patterns in CORE_CATEGORIES.items():
        rx = [re.compile(p, re.I) for p in patterns]
        observed = sum(1 for t in titles if any(r.search(t) for r in rx))
        seeds = [p.slug for p in POOL if any(r.search(f"{p.title} {p.category}") for r in rx)]
        rows.append({"category": key, "observed_listings": observed, "pool_seeds": seeds,
                     "researched": observed > 0 or bool(seeds)})
        if observed == 0 and not seeds:
            gaps.append({"category": key, "item": "research",
                         "why": "no observed listing and no radar seed: demand unknown"})
    return {"categories": rows, "gaps": gaps,
            "observed_total": len(titles) if titles else UNMEASURED,
            "researched": sum(r["researched"] for r in rows), "of": len(rows)}


def style_segments(db) -> dict:
    """F-358: neutral / gendered / style-specific demand among observed children's listings.
    Counts only; no palette or aesthetic is inferred and no competitor text is kept."""
    kids = [t for t, _ in _observed_titles(db) if _CHILD.search(t)]
    if not kids:
        return {"children_listings": 0, "status": UNMEASURED,
                "why": "no observed children's listing yet"}
    neutral = sum(1 for t in kids if _NEUTRAL.search(t))
    gendered = sum(1 for t in kids if _GENDERED.search(t))
    styles: dict[str, int] = {}
    for t in kids:
        for m in {m.lower() for m in _STYLE.findall(t)}:
            styles[m] = styles.get(m, 0) + 1
    return {"children_listings": len(kids), "gender_neutral": neutral, "gendered": gendered,
            "unmarked": len(kids) - neutral - gendered if len(kids) >= neutral + gendered
            else 0, "style_terms": dict(sorted(styles.items())),
            "palette": "not inferred (F-358: use evidence and the creative system)",
            "status": "measured"}


def _catalogue(db) -> list[dict]:
    """Launch-0 candidates and the radar pool, each with its segment."""
    from ..products import launch0
    from ..radar.opportunity import POOL

    out = []
    for slug in launch0.LAUNCH0_SLUGS:
        c = launch0.candidate_for_cir(slug)
        cat = (c.pod or "") if c else ""
        out.append({"slug": slug, "source": "launch0", "audience": getattr(c, "audience", ""),
                    "segment": segment(category=cat, audience=getattr(c, "audience", "") or "",
                                       title=getattr(c, "title", slug) or slug)})
    for p in POOL:
        if p.is_bundle:
            continue
        out.append({"slug": p.slug, "source": "radar_pool", "audience": "",
                    "segment": segment(category=p.category, title=p.title, season=p.season)})
    return out


def launch_mix(db) -> dict:
    """F-366: the opening catalogue across the five segments, children's considered."""
    rows = [r for r in _catalogue(db) if r["source"] == "launch0"]
    counts = {s: sum(1 for r in rows if r["segment"] == s) for s in SEGMENTS}
    pool = {s: sum(1 for r in _catalogue(db) if r["source"] == "radar_pool"
                   and r["segment"] == s) for s in SEGMENTS}
    missing = [s for s in SEGMENTS if counts[s] == 0]
    return {"segments_considered": list(SEGMENTS), "launch0": counts, "candidate_pool": pool,
            "children_considered": PRIORITY_FAMILY in SEGMENTS,
            "children_in_launch": counts["baby_children"],
            "segments_absent_from_launch": missing,
            "ok": counts["baby_children"] > 0,
            "why": ("children's products are in the opening catalogue" if counts["baby_children"]
                    else "no children's product in the opening catalogue although the family "
                         "is the priority (F-351)")}


def architecture(db) -> dict:
    """F-365: a Baby & Kids collection only when depth justifies it."""
    from ..creative.family_engine import _certified, family_of
    from ..products import launch0

    kids = []
    for r in _certified(db):
        c = launch0.candidate_for_cir(r["slug"])
        audience = getattr(c, "audience", "") if c else ""
        if is_children(audience=audience or "", title=(r["cir"] or {}).get("title", "")):
            fam, _src = family_of(r["slug"])
            kids.append({"slug": r["slug"], "family": fam or "single",
                         "age_range": audience or UNMEASURED})
    if len(kids) < BABY_KIDS_DEPTH:
        return {"propose_collection": False, "children_certified": len(kids),
                "depth_needed": BABY_KIDS_DEPTH,
                "why": f"{len(kids)} certified children's product(s); a dedicated collection "
                       f"needs {BABY_KIDS_DEPTH} (an empty department is worse than none)"}
    by_family: dict[str, list[str]] = {}
    by_age: dict[str, list[str]] = {}
    for k in kids:
        by_family.setdefault(k["family"], []).append(k["slug"])
        by_age.setdefault(k["age_range"], []).append(k["slug"])
    return {"propose_collection": True, "section": "Baby & Kids",
            "children_certified": len(kids), "navigation": {
                "by_family": by_family,
                "by_age_range": ({a: v for a, v in by_age.items() if a != UNMEASURED}
                                 or UNMEASURED)},
            "applied_by": "storefront_director proposal (createShopSection), owner grant"}


COMPETITOR_FLOOR = 3       # observed children's listings in a category before it is "measured"


def competitive_study(db) -> dict:
    """F-367: a runtime competitive study of children's listings, per core category.

    From the listings already observed through sanctioned sources (`benchmark_listings`):
    per category, how many listings and how many distinct shops (shops by stable alias,
    never by name), the price band (min / median / max CA$, UNKNOWN when unobserved), the
    share on sale, the median gallery size and how many shops carry several listings in the
    category (a product family there). Counts and prices only: no competitor title, URL,
    image or wording is kept (CLAUDE.md: demand and merchandising intelligence only).
    """
    import statistics

    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..runtime.intel_ops import benchmark_alias

    with db.session() as s:
        rows = [(r.benchmark_key, r.title or "", float(r.price_cad or 0), bool(r.on_sale),
                 int(r.media_count or 0)) for r in s.scalars(select(BenchmarkListing))]
    kids = [r for r in rows if _CHILD.search(r[1])]
    out = []
    for key, patterns in CORE_CATEGORIES.items():
        rx = [re.compile(p, re.I) for p in patterns]
        hits = [r for r in kids if any(x.search(r[1]) for x in rx)]
        if not hits:
            out.append({"category": key, "listings": 0, "status": UNMEASURED})
            continue
        prices = [r[2] for r in hits if r[2] > 0]
        per_shop: dict[str, int] = {}
        for r in hits:
            a = benchmark_alias(r[0])
            per_shop[a] = per_shop.get(a, 0) + 1
        out.append({
            "category": key, "listings": len(hits), "shops": len(per_shop),
            "status": "MEASURED" if len(hits) >= COMPETITOR_FLOOR else "THIN",
            "price_min_cad": round(min(prices), 2) if prices else UNMEASURED,
            "price_median_cad": round(statistics.median(prices), 2) if prices else UNMEASURED,
            "price_max_cad": round(max(prices), 2) if prices else UNMEASURED,
            "on_sale_share": round(sum(1 for r in hits if r[3]) / len(hits), 3),
            "median_media": statistics.median([r[4] for r in hits]),
            "shops_with_a_family": sum(1 for n in per_shop.values() if n >= 2)})
    return {"categories": out, "children_listings_observed": len(kids) if rows else UNMEASURED,
            "measured": [c["category"] for c in out if c.get("status") == "MEASURED"],
            "copies_competitor_content": False}


def portfolio(db) -> dict:
    """F-351: the priority family's state across research, launch, storefront and families."""
    from ..creative.family_engine import family_report

    fam = family_report(db)
    kids_slugs = {r["slug"] for r in _catalogue(db) if r["segment"] == "baby_children"}
    kid_families = [f for f in fam["families"]
                    if any(m["slug"] in kids_slugs for m in f["members"])]
    return {"priority_family": PRIORITY_FAMILY, "coverage": coverage(db),
            "style_segments": style_segments(db), "launch_mix": launch_mix(db),
            "architecture": architecture(db),
            "competitive_study": competitive_study(db),
            "sibling_sets": [{"family": f["family"], "bundle_ready": f["bundle_ready"],
                              "recolour_duplicates": f["recolour_duplicates"]}
                             for f in kid_families],
            "writes": 0}
