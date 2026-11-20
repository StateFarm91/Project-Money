"""Photographic principles from the judged benchmark galleries (F-224, W4-AGENTS W7).

`intel.vision` judges sanctioned benchmark gallery images into a closed, non-copying
vocabulary. Until now those judgements fed the market map and nothing photographic: the
shot plans (`visual.shot_plans`) were built from the requirement words alone. This turns
the judgements into a per-pod **photographic-principles profile** and compares each Launch-0
shot plan with it.

What it reads, and what it never reads:
* only `shot_type` (closed: `intel.vision.SHOT_TYPES`) and the image's gallery rank. The
  free-text observation fields (composition, setting...) are short phrases about a
  competitor's photograph; they never enter a principle, so nothing here can carry a
  competitor's wording, composition or image;
* the result is shares and counts per pod -- "70% of judged home galleries include a
  detail macro" -- which is merchandising intelligence (CLAUDE.md), not a template.

What it does with them: a principle is a shot type that at least `WIDE_SHARE` of a pod's
judged galleries include, measured over at least `MIN_LISTINGS` judged listings; a pod below
that is INSUFFICIENT, never a principle. Each Launch-0 plan is compared with its pod's
principles: a principle whose gallery job our plan lacks is reported as an **advisory gap**.
Plans are not changed here. The shot plan's own gates (F-852, the disclosed-render rule,
one job per frame) decide what can fill a role; this only says what the market's galleries
show that ours does not plan to.
"""
from __future__ import annotations

import statistics

from ..publish import eligibility as el

READING = "creative.photo_principles"
MIN_LISTINGS = 5
WIDE_SHARE = 0.5
INSUFFICIENT = "INSUFFICIENT"

# The judged shot type -> the gallery job (publish.eligibility) that does the same work.
JOB_OF_SHOT: dict[str, str] = {
    "hero_product_only": el.DESIRE, "hero_styled": el.DESIRE,
    "full_fit": el.FIT, "three_quarter": el.FIT,
    "detail_macro": el.DETAIL, "flat_lay": el.ANGLE, "in_use": el.LIFESTYLE,
    "scale_reference": el.SCALE, "infographic": el.SIZING, "process": el.CONSTRUCTION,
    "packaging": el.CONTENTS,
}


def _judged(db) -> dict[tuple[str, str], list[tuple[int, str]]]:
    """(benchmark, listing) -> [(rank, shot_type)] for every judged gallery image."""
    from sqlalchemy import select

    from ..core.models import BenchmarkObservation

    out: dict[tuple[str, str], list[tuple[int, str]]] = {}
    with db.session() as s:
        for r in s.scalars(select(BenchmarkObservation).where(
                BenchmarkObservation.kind == "gallery_image_observation")):
            d = r.detail or {}
            shot = (d.get("observation") or {}).get("shot_type")
            if shot not in JOB_OF_SHOT:
                continue
            rank = (d.get("image") or {}).get("rank")
            out.setdefault((r.benchmark_key, r.listing_ref), []).append(
                (int(rank) if isinstance(rank, int) else 999, shot))
    return out


def _pods(db, keys) -> dict[tuple[str, str], str]:
    from sqlalchemy import select

    from ..core.models import BenchmarkListing

    want = set(keys)
    with db.session() as s:
        return {(r.benchmark_key, r.listing_ref): (r.pod or "unclassified")
                for r in s.scalars(select(BenchmarkListing))
                if (r.benchmark_key, r.listing_ref) in want}


def profile(db) -> dict:
    """Per pod: judged listings, first-image shot shares, coverage shares, principles."""
    judged = _judged(db)
    pods = _pods(db, judged)
    by_pod: dict[str, list[list[tuple[int, str]]]] = {}
    for key, images in judged.items():
        by_pod.setdefault(pods.get(key, "unclassified"), []).append(sorted(images))
    out: dict[str, dict] = {}
    for pod, galleries in sorted(by_pod.items()):
        n = len(galleries)
        first: dict[str, int] = {}
        cover: dict[str, int] = {}
        for g in galleries:
            first[g[0][1]] = first.get(g[0][1], 0) + 1
            for shot in {s for _r, s in g}:
                cover[shot] = cover.get(shot, 0) + 1
        entry = {"judged_listings": n,
                 "median_images_judged": statistics.median(len(g) for g in galleries),
                 "first_image": {k: round(v / n, 3) for k, v in sorted(first.items())},
                 "coverage": {k: round(v / n, 3) for k, v in sorted(cover.items())}}
        if n < MIN_LISTINGS:
            entry.update(state=INSUFFICIENT, principles=[],
                         why=f"{n} judged listing(s) against a floor of {MIN_LISTINGS}")
        else:
            entry.update(state="MEASURED", principles=[
                {"shot_type": shot, "job": JOB_OF_SHOT[shot], "share": share,
                 "principle": f"{share:.0%} of {n} judged {pod} galleries include "
                              f"{shot.replace('_', ' ')}"}
                for shot, share in sorted(entry["coverage"].items(), key=lambda x: -x[1])
                if share >= WIDE_SHARE])
        out[pod] = entry
    return {"pods": out, "judged_listings": len(judged),
            "basis": "intel.vision shot_type (closed vocabulary) and gallery rank only",
            "note": ("no benchmark gallery has been judged yet: there is no profile, and no "
                     "principle is assumed" if not judged else "")}


def pod_of_category(category: str) -> str:
    from ..seasonal.daily import DEPARTMENT_OF

    return DEPARTMENT_OF.get(category, "unclassified")


def compare(plan: dict, pod_profile: dict | None) -> dict:
    """One shot plan against its pod's principles: what the market shows that we lack."""
    jobs = {r["job"] for r in plan.get("roles") or []}
    if not pod_profile or pod_profile.get("state") != "MEASURED":
        return {"state": INSUFFICIENT if pod_profile else "UNKNOWN", "gaps": [], "covered": [],
                "why": (pod_profile or {}).get("why") or "no judged galleries in this pod"}
    gaps, covered = [], []
    for p in pod_profile["principles"]:
        (covered if p["job"] in jobs else gaps).append(p)
    return {"state": "COMPARED", "gaps": gaps, "covered": covered,
            "advisory": True,
            "note": "advisory: the plan's own gates decide what may fill a role"}


def run(db) -> dict:
    """The profile plus every Launch-0 plan compared with it."""
    from . import shot_plans

    prof = profile(db)
    plans = shot_plans.all_plans()["plans"]
    comparisons = {}
    for slug, plan in plans.items():
        pod = pod_of_category(plan.get("category") or "")
        comparisons[slug] = {"pod": pod, **compare(plan, prof["pods"].get(pod))}
    return {"profile": prof, "plans": comparisons,
            "gaps": sum(len(c["gaps"]) for c in comparisons.values())}
