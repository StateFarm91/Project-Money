"""F-113 Commercial Salvage Test (W4-AGENTS cluster C3).

"Before rescue, re-run current creative, MJs-market, seasonal, novelty and portfolio gates;
weak legacy products retire."

A legacy product is a certified release outside the current Launch scope
(`products.launch0.launch_scope_slugs`). `review(db)` re-runs, for each, the gates as they
stand today:
* creative: the current MJs blind review (`creative.blind_review.current_review`); materially
  inferior is FAIL, a stale or absent review is UNKNOWN;
* MJs-market: whether today's radar portfolio would still select its concept
  (`radar.opportunity.select_portfolio`);
* seasonal: the #297 window decision (`publish.release_gates.window_decision`);
* novelty: the certificate's originality-provenance stage (`gates.originality`);
* portfolio: whether its listing competes with another in the catalogue
  (`commerce.portfolio.diversification`).
**It only ever RECOMMENDS** (`retire_recommended` / `rescue_candidate` / `review`). It never
deletes, unlists, deactivates or changes a product or a listing; there is no write here.
"""
from __future__ import annotations

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"


def _guard(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - an unreadable gate is UNKNOWN
        return UNKNOWN, f"unreadable ({type(exc).__name__})"


def _gates(db, r: dict, selected: set | None, competing: set | None) -> dict:
    from ..cir.model import CIR
    from ..creative.blind_review import current_review
    from ..gates.originality import provenance_findings
    from ..products import launch0
    from ..publish.release_gates import window_decision

    slug, version = r["slug"], r["version"]
    concept = launch0.radar_concept_for(slug) or slug

    def creative():
        rv = current_review(db, slug=slug)
        if not rv or rv.get("materially_inferior") is None:
            return UNKNOWN, (rv or {}).get("why") or "no current blind review"
        return (FAIL, "materially inferior to the benchmark") if rv["materially_inferior"] \
            else (PASS, "not inferior in the current blind review")

    def market():
        if selected is None:
            return UNKNOWN, "today's radar portfolio could not be read"
        return ((PASS, "today's radar portfolio still selects it") if concept in selected
                else (FAIL, "today's radar portfolio would not select it"))

    def seasonal():
        w = window_decision(db, slug=slug, version=version)
        return ((PASS, w.get("why", "")) if w.get("may_launch_seasonally")
                else (FAIL, f"{w.get('action')}: {w.get('why', '')}"))

    def novelty():
        errs = [f for f in provenance_findings(CIR.from_dict(r["cir"])) if f.is_error]
        return (FAIL, errs[0].code) if errs else (PASS, "originality provenance holds")

    def portfolio():
        if competing is None:
            return UNKNOWN, "catalogue diversification could not be read"
        return ((FAIL, "its listing competes with another for the same query")
                if slug in competing else (PASS, "no cannibalising pair"))

    return {k: dict(zip(("verdict", "why"), _guard(fn))) for k, fn in (
        ("creative", creative), ("mjs_market", market), ("seasonal", seasonal),
        ("novelty", novelty), ("portfolio", portfolio))}


def review(db) -> dict:
    from ..commerce.portfolio import diversification
    from ..creative.family_engine import _certified
    from ..products import launch0
    from ..radar.opportunity import select_portfolio

    scope = set(launch0.launch_scope_slugs())
    legacy = [r for r in _certified(db) if r["slug"] not in scope]
    try:
        selected = {c.seed.slug for c in select_portfolio().selected}
    except Exception:  # noqa: BLE001 - review b199cdb L-2: unreadable is UNKNOWN, never FAIL
        selected = None
    try:
        div = diversification(db)
        competing = {s for pair in (div.get("competing_pairs") or [])
                     for s in (pair.get("between") or [])}
    except Exception:  # noqa: BLE001 - review b199cdb L-2: unreadable is UNKNOWN, never PASS
        competing = None
    rows = []
    for r in legacy:
        g = _gates(db, r, selected, competing)
        fails = [k for k, v in g.items() if v["verdict"] == FAIL]
        unknown = [k for k, v in g.items() if v["verdict"] == UNKNOWN]
        if g["creative"]["verdict"] == FAIL or len(fails) >= 2:
            rec = "retire_recommended"
        elif not fails and len(unknown) <= 1 and g["creative"]["verdict"] != UNKNOWN:
            # review b199cdb L-2: rescue needs a known creative verdict
            rec = "rescue_candidate"
        else:
            rec = "review"
        rows.append({"slug": r["slug"], "version": r["version"], "gates": g,
                     "failed": fails, "unknown": unknown, "recommendation": rec})
    return {"legacy": rows, "count": len(rows),
            "retire_recommended": [x["slug"] for x in rows
                                   if x["recommendation"] == "retire_recommended"],
            "acts": "recommends only: never deletes, unlists, deactivates or edits anything",
            "writes": 0}
