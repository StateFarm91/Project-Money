"""Image-production learning: the failure taxonomy end to end, and the Learn path (W-VISNEXT).

**Taxonomy.** Every `image_candidates` row carries `failure_categories`: the gate categories
of `candidate_gates.FAILURE_CATEGORY` (identity_drift, body_proportion_drift, anatomy,
realism, outfit_consistency, wardrobe_repetition, product_fidelity, ...) plus the shared codes
of `creative.failure_codes` (Product Truth codes such as INVENTED_EDGING, and the wardrobe
codes WARDROBE_REPETITION and REFERENCE_CLOTHING_CARRYOVER). `taxonomy` reads them back,
groups each one under its owner, and lists anything it cannot classify, so a new code that
nobody registered is visible instead of silently counted.

**Learn path.** Learning never edits a brief or a prompt in place. A repeated, routable
failure becomes a *challenger* registered in `improve.league` (kind "prompt", key
`image_production.PROMPT_KEY`) with the repair negatives that counter it. It changes nothing
until the league measures it against the incumbent and promotes it; `prompt_version` only
ever reads the promoted incumbent. Per-attempt repair directives (`repair_routes`) are bounded
corrections inside one run and are not learning.
"""
from __future__ import annotations

import json

from ..creative import failure_codes as FC
from . import candidate_gates as CG

GATE_CATEGORIES = frozenset(CG.FAILURE_CATEGORY.values()) | {"provider_error"}
DEPARTMENTS = ("creative", "quality")


def owner_of(code: str) -> str | None:
    """Which taxonomy a recorded failure word belongs to, or None when nobody owns it."""
    if code in FC.CATEGORY_OF:
        return f"product_truth:{FC.CATEGORY_OF[code]}"
    if code in FC.WARDROBE_CATEGORY_OF:
        return f"wardrobe:{FC.WARDROBE_CATEGORY_OF[code]}"
    if code in GATE_CATEGORIES:
        return "gate"
    return None


def taxonomy(db, *, slug: str | None = None) -> dict:
    """Every recorded failure word, counted, grouped by owner; unclassified ones listed."""
    from sqlalchemy import select

    from .image_records import ImageCandidate, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        q = select(ImageCandidate)
        if slug:
            q = q.where(ImageCandidate.slug == slug)
        rows = list(s.scalars(q))
    counts: dict[str, int] = {}
    for r in rows:
        for c in r.failure_categories or []:
            counts[str(c)] = counts.get(str(c), 0) + 1
    groups: dict[str, dict[str, int]] = {}
    unclassified = []
    for code, n in sorted(counts.items()):
        owner = owner_of(code)
        if owner is None:
            unclassified.append(code)
            continue
        groups.setdefault(owner, {})[code] = n
    return {"candidates": len(rows), "counts": counts, "by_owner": groups,
            "unclassified": unclassified,
            "known_codes": sorted(FC.EVERY_CODE), "gate_categories": sorted(GATE_CATEGORIES)}


def propose_brief_challenger(db, *, min_count: int = 3, slug: str | None = None) -> dict:
    """Register (never promote) a brief challenger for repeated, routable failures.

    Only codes whose repair route is a prompt negative qualify; a code that needs a new
    reference, a re-picked outfit or a verification on the unfolded anchor is not a brief
    change. The challenger is the incumbent brief (or the code default) plus those negatives.
    It is inert until `improve.league` measures and promotes it."""
    from ..improve import league
    from . import image_production as IP
    from . import repair_routes as RR
    from . import shot_plans as SP

    tax = taxonomy(db, slug=slug)
    frequent = sorted(c for c, n in tax["counts"].items()
                      if n >= min_count and c in RR.ROUTES
                      and RR.ROUTES[c]["kind"] == RR.PROMPT_NEGATIVE)
    if not frequent:
        return {"registered": False, "why": f"no routable code reached {min_count} failures",
                "counts": tax["counts"]}
    inc = league.incumbent_payload(db, kind="prompt", key=IP.PROMPT_KEY)
    base = json.loads(inc["payload"]) if inc and inc.get("payload") else {
        "lifestyle_brief": {k: v[1] for k, v in SP.LIFESTYLE_BRIEF.items()}, "negatives": []}
    negatives = list(base.get("negatives") or [])
    for code in frequent:
        for n in RR.ROUTES[code].get("negatives") or []:
            if n not in negatives:
                negatives.append(n)
    payload = json.dumps({**base, "negatives": negatives,
                          "learned_from": {c: tax["counts"][c] for c in frequent}},
                         sort_keys=True)
    reg = league.register(
        db, kind="prompt", key=IP.PROMPT_KEY, payload=payload,
        why_changed=(f"image learning: {', '.join(frequent)} recurred at least {min_count} "
                     f"times; the challenger adds their routed prompt negatives to the brief"),
        tests_declared=("tests/test_w4_visnext.py",), affected_departments=DEPARTMENTS,
        incumbent=False)
    return {"registered": not reg.get("unchanged"), "config": reg, "codes": frequent,
            "promoted": False,
            "why": "registered as a challenger; only an improve.league promotion changes the "
                   "running brief"}
