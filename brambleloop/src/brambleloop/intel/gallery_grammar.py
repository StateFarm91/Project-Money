"""F-231 Benchmark-Derived Photo Grammar (W4-INTELREC C05).

"After the MJs teardown is legally purchased and ingested, quantify high-level gallery grammar
such as image count/types, hero composition, close-up frequency, background/environment
patterns, model-versus-product-only mix, lighting, framing and within-listing consistency."

The input is the judged benchmark galleries (`intel.vision`, sanctioned API images judged into
a closed vocabulary), read through the same accessor as `visual.photo_principles`. Only the
closed `shot_type` and the image's gallery rank are used, so nothing quantified here can carry a
competitor's wording, composition or picture. Per pod, over at least `MIN_LISTINGS` judged
listings (below that the pod is INSUFFICIENT):

* image count -- median judged images per gallery;
* hero composition -- the share of galleries whose first image is each shot type;
* close-up frequency -- the mean share of a gallery's images that are `detail_macro`;
* model-versus-product mix -- the share of galleries with a worn/model shot (`full_fit`,
  `three_quarter`) and the share whose hero is product-only;
* sequence -- the median gallery position of the first close-up;
* within-listing consistency -- the mean share of a gallery's images that are distinct shot
  types (1.0: every frame does a different job).

Lighting, background/environment and framing are free-text judgements in `intel.vision`; they
are reported UNMEASURED here rather than turned into a vocabulary nobody defined. The teardown
purchase (when the owner makes it) adds galleries; the quantifier does not change.
"""
from __future__ import annotations

import statistics

READING = "intel.gallery_grammar"
INSUFFICIENT = "INSUFFICIENT"
MODEL_SHOTS = frozenset({"full_fit", "three_quarter"})
UNMEASURED_DIMENSIONS = {
    "lighting": "free-text in intel.vision; no closed vocabulary is defined",
    "background_environment": "free-text in intel.vision (setting); no closed vocabulary",
    "framing": "free-text in intel.vision (composition); no closed vocabulary",
}


def grammar(db) -> dict:
    from ..visual.photo_principles import MIN_LISTINGS, _judged, _pods

    judged = _judged(db)
    pods = _pods(db, judged)
    by_pod: dict[str, list[list[str]]] = {}
    for key, images in judged.items():
        by_pod.setdefault(pods.get(key, "unclassified"), []).append(
            [shot for _rank, shot in sorted(images)])
    out = {}
    for pod, galleries in sorted(by_pod.items()):
        n = len(galleries)
        if n < MIN_LISTINGS:
            out[pod] = {"state": INSUFFICIENT, "judged_listings": n,
                        "why": f"{n} judged listing(s) against a floor of {MIN_LISTINGS}"}
            continue
        heroes: dict[str, int] = {}
        for g in galleries:
            heroes[g[0]] = heroes.get(g[0], 0) + 1
        first_close = [g.index("detail_macro") + 1 for g in galleries if "detail_macro" in g]
        out[pod] = {
            "state": "MEASURED", "judged_listings": n,
            "image_count_median": statistics.median(len(g) for g in galleries),
            "hero_composition": {k: round(v / n, 3) for k, v in sorted(heroes.items())},
            "close_up_frequency": round(statistics.mean(
                g.count("detail_macro") / len(g) for g in galleries), 3),
            "model_shot_share": round(sum(1 for g in galleries if MODEL_SHOTS & set(g)) / n, 3),
            "product_only_hero_share": round(sum(1 for g in galleries
                                                 if g[0] == "hero_product_only") / n, 3),
            "first_close_up_position_median": (statistics.median(first_close)
                                               if first_close else None),
            "within_listing_consistency": round(statistics.mean(
                len(set(g)) / len(g) for g in galleries), 3),
        }
    return {"pods": out, "judged_listings": len(judged),
            "unmeasured": UNMEASURED_DIMENSIONS,
            "basis": "intel.vision shot_type (closed vocabulary) and gallery rank only"}
