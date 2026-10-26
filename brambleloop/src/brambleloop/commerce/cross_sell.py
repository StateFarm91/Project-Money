"""F-775 Cross-Sell Graph (W4-AGENTS cluster C3).

"Every product records legitimate related products, bundles, collections, tutorials, materials
and next-project recommendations. Agents optimize attach rate without misleading customers."

`graph(db)` builds one node per certified product from our own records only:
* related: certified siblings in the same declared family (`creative.family_engine`);
* bundles: the radar pool's bundle seeds for that family;
* collection: the storefront section its category maps to (`brand.storefront.section_for`);
* tutorials: APPROVED learn lessons for the pattern's own techniques
  (`learn.service.listing_help_links` -- the same gate as the PDF);
* materials: the CIR's own materials (yarn weight, colour ids), never a brand claim;
* next projects: uncertified family seeds and certified products in the same collection.
Edges never point at a product that is not certified (nothing a buyer cannot buy is
recommended), and attach rate is UNMEASURED until orders exist. Read-only, CA$0.
"""
from __future__ import annotations

UNMEASURED = "UNMEASURED"


def graph(db) -> dict:
    from ..brand.storefront import section_for
    from ..creative.family_engine import _certified, family_of
    from ..radar.opportunity import POOL

    certified = _certified(db)
    slugs = {r["slug"] for r in certified}
    seeds = {p.slug: p for p in POOL}
    fam_of = {r["slug"]: family_of(r["slug"])[0] for r in certified}
    section = {}
    for r in certified:
        seed = seeds.get(r["slug"])
        section[r["slug"]] = section_for(seed.category if seed else "",
                                         bool(seed and seed.is_bundle))
    nodes = []
    for r in certified:
        slug, fam = r["slug"], fam_of[r["slug"]]
        try:
            from ..cir.model import CIR
            from ..learn import service as learn

            tutorials = [l["slug"] for l in learn.listing_help_links(db, CIR.from_dict(r["cir"]))]
        except Exception:  # noqa: BLE001 - no lesson reachable is not "none exist"
            tutorials = UNMEASURED
        materials = sorted({f"{m.get('yarn_weight') or '?'}:{m.get('color_id') or '?'}"
                            for m in (r["cir"].get("materials") or [])}) or UNMEASURED
        related = sorted(s for s in slugs if s != slug and fam and fam_of.get(s) == fam)
        bundles = sorted(p.slug for p in POOL if fam and p.family == fam and p.is_bundle)
        same_collection = sorted(s for s in slugs if s != slug and section[s] == section[slug])
        nxt = sorted({p.slug for p in POOL if fam and p.family == fam and not p.is_bundle
                      and p.slug not in slugs})
        nodes.append({"product": slug, "version": r["version"], "family": fam,
                      "related": related, "bundles": bundles, "collection": section[slug],
                      "tutorials": tutorials, "materials": materials,
                      "next_projects": {"in_catalogue": same_collection[:5],
                                        "planned_family_members": nxt[:5]},
                      "attach_rate": UNMEASURED})
    return {"nodes": nodes, "products": len(nodes),
            "rule": "edges point only at certified products; attach rate UNMEASURED until orders"}
