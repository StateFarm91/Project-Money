"""Product Family Engine over the CERTIFIED catalogue (W4-AGENTS product-engine batch).

`creative.family.family_test` (#111) answers, before engineering, whether one concept *can*
seed a family. Nothing answered the catalogue-level questions the requirements ask once
products exist:

* Master Plan s33: "at least one bundle-ready family" in the launch portfolio;
* F-359 / #111: families "where genuine customer value exists, while preventing low-value
  catalogue duplication" -- a member that differs from a sibling only by colour is a recolour
  with a collection name on it (F-791: "merely changing colour ... is not sufficient");
* Master Plan s5 Winner Amplification: "turns proven demand into matching products, bundles,
  sizes, colourways" -- from PROVEN demand, so it waits on real orders and says UNMEASURED.

`family_report(db)` is deterministic and reads only our own rows (certified pattern versions,
the radar pool's declared families, orders). It writes nothing; the job stores one reading.
It never creates a product: a next member is a radar-pool seed that still has to pass the
ordinary funnel (radar.score -> preengineering -> cir.draft -> compile -> certify).
"""
from __future__ import annotations

import hashlib
import json

UNMEASURED = "UNMEASURED"
# Winner Amplification needs proven demand. Five orders for a family is this module's own
# floor (no requirement states a number); below it amplification is UNMEASURED, never "no".
AMPLIFY_MIN_ORDERS = 5


def structure_fingerprint(cir_json: dict) -> str:
    """The design's structure with colour removed: two members with the same fingerprint are
    the same pattern in different colours (a recolour, not a sibling)."""
    comps = []
    for c in cir_json.get("components") or []:
        rows = [{k: v for k, v in (r or {}).items() if k not in ("color", "colour")}
                for r in c.get("rows") or []]
        comps.append({k: v for k, v in c.items() if k not in ("rows", "name")} | {"rows": rows})
    body = {"construction": cir_json.get("construction"), "components": comps}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()
                          ).hexdigest()[:16]


def family_of(slug: str) -> tuple[str | None, str]:
    """(family key, source) for a certified CIR slug, from the radar pool's declared family."""
    from ..products import launch0
    from ..radar.opportunity import POOL

    by = {p.slug: p for p in POOL}
    concept = launch0.radar_concept_for(slug) or slug
    seed = by.get(concept) or by.get(slug)
    if seed is not None and seed.family:
        return seed.family, f"radar.opportunity.POOL[{seed.slug}].family"
    return None, "no declared family"


def _certified(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    latest: dict[str, dict] = {}
    with db.session() as s:
        for slug, version, cir_json in s.execute(
                select(Product.slug, PatternVersion.version, PatternVersion.cir_json)
                .join(PatternVersion, PatternVersion.product_id == Product.id)
                .where(PatternVersion.certified == True)  # noqa: E712
                .order_by(PatternVersion.id)).all():
            latest[slug] = {"slug": slug, "version": version, "cir": cir_json or {}}
    return list(latest.values())


def _orders_by_slug(db) -> dict[str, int]:
    from sqlalchemy import func, select

    from ..core.models import Order

    with db.session() as s:
        return {slug: int(n) for slug, n in s.execute(
            select(Order.product_slug, func.count()).group_by(Order.product_slug)).all()}


def family_report(db) -> dict:
    from ..radar.opportunity import POOL

    certified = _certified(db)
    orders = _orders_by_slug(db)
    fams: dict[str, dict] = {}
    singles: list[str] = []
    for r in certified:
        fam, source = family_of(r["slug"])
        if fam is None:
            singles.append(r["slug"])
            continue
        f = fams.setdefault(fam, {"family": fam, "source": source, "members": [],
                                  "structures": {}})
        fp = structure_fingerprint(r["cir"])
        f["members"].append({"slug": r["slug"], "version": r["version"], "structure": fp,
                             "orders": orders.get(r["slug"], 0)})
        f["structures"].setdefault(fp, []).append(r["slug"])
    certified_slugs = {r["slug"] for r in certified}
    out = []
    for key, f in sorted(fams.items()):
        recolours = [sorted(v) for v in f["structures"].values() if len(v) > 1]
        distinct = len(f["structures"])
        n_orders = sum(m["orders"] for m in f["members"])
        next_members = sorted(
            ({"seed": p.slug, "category": p.category, "whitespace": p.whitespace,
              "route": "radar.score -> preengineering -> cir.draft (the ordinary funnel)"}
             for p in POOL if p.family == key and not p.is_bundle
             and p.slug not in certified_slugs),
            key=lambda x: -x["whitespace"])
        out.append({
            "family": key, "source": f["source"], "members": f["members"],
            "distinct_designs": distinct,
            # A bundle is derived, never asserted: two distinct certified designs (#111).
            "bundle_ready": distinct >= 2,
            "recolour_duplicates": recolours,
            "next_members": next_members[:5],
            "orders": n_orders,
            "amplification": (UNMEASURED if n_orders < AMPLIFY_MIN_ORDERS else {
                "proposal": "amplify the family through the funnel (matching member, bundle, "
                            "size or colourway), proven by its orders",
                "orders": n_orders}),
        })
    return {"families": out, "single_products": sorted(singles),
            "certified": len(certified),
            "portfolio_has_bundle_ready_family": any(f["bundle_ready"] for f in out),
            "recolour_duplicates": [d for f in out for d in f["recolour_duplicates"]],
            "amplify_min_orders": AMPLIFY_MIN_ORDERS, "writes": 0}
