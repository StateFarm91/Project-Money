"""Distinctive-stitch benchmark set and its promotion gate (F-759) -- W4-C07.

"Maintain adversarial positive/negative examples for each supported distinctive stitch
family. The validator must reject visually plausible but wrong alternatives before that stitch
family is promoted to production support."

`FAMILIES` is the set. Each family names its validator and its examples, all deterministic
(drawn from the stitch's own definition, never a photograph of someone's product):

* **positives** -- the true fabric, at more than one phase, that the validator must PASS;
* **negatives** -- plausible wrong alternatives it must reject (not PASS): for star stitch the
  half-offset checker the first model drew, plain hdc rows, seed, knit, and the true fabric at
  twice the gauge (identity right, gauge wrong).

`promotion_gate(family)` runs every example and is PROMOTABLE only when every positive passes
and every negative is rejected, with at least `MIN_POSITIVES` and `MIN_NEGATIVES`. A family
with no validator (bobble, post stitches, cables today) is UNSUPPORTED -- it cannot be promoted,
however good its pictures look -- and a validator that cannot run (its optional SciPy
dependency absent) is UNKNOWN, never PROMOTABLE. Nothing here moves a validator's bars.
"""
from __future__ import annotations

MIN_POSITIVES = 2
MIN_NEGATIVES = 3
UNSUPPORTED_FAMILIES = ("bobble", "front_post", "back_post", "cable")


def _star():
    import numpy as np

    from ..visual import stitch_identity as S

    W, H, star, pair = 480, 400, 24.0, 43.0

    def g(img):
        return np.array(img.convert("L")).astype(float)

    positives = {"truth": lambda: g(S.draw_star_fabric(W, H, star, pair)),
                 "truth_phase": lambda: g(S.draw_star_fabric(W, H, star, pair, phase=0.37))}
    negatives = {
        "half_offset_checker": lambda: g(S.draw_star_fabric(W, H, star, pair,
                                                            column_offset=0.5)),
        "hdc_rows": lambda: g(S.draw_hdc_fabric(W, H, star / 2, pair / 2)),
        "seed": lambda: g(S.draw_seed_fabric(W, H, star / 2, pair / 2)),
        "knit": lambda: g(S.draw_knit_fabric(W, H, star / 2, pair / 2)),
        "double_gauge": lambda: g(S.draw_star_fabric(W, H, star * 2, pair * 2)),
    }

    def validate(gray):
        return S.measure(gray, star, pair)["status"]

    available = S.gaussian_filter is not None
    return {"validator": "visual.stitch_identity.measure (star, gauge 24/43 px)",
            "available": available, "validate": validate,
            "positives": positives, "negatives": negatives}


FAMILIES = {"star": _star}


def promotion_gate(family: str) -> dict:
    if family in UNSUPPORTED_FAMILIES or family not in FAMILIES:
        return {"family": family, "state": "UNSUPPORTED", "promotable": False,
                "why": "no validator exists for this family, so nothing can show it rejects a "
                       "plausible wrong alternative"}
    f = FAMILIES[family]()
    if not f["available"]:
        return {"family": family, "state": "UNKNOWN", "promotable": False,
                "why": "the validator's dependency is unavailable; UNKNOWN, not PASS"}
    pos = {k: f["validate"](make()) for k, make in f["positives"].items()}
    neg = {k: f["validate"](make()) for k, make in f["negatives"].items()}
    missed = sorted(k for k, v in pos.items() if v != "PASS")
    accepted = sorted(k for k, v in neg.items() if v == "PASS")
    enough = len(pos) >= MIN_POSITIVES and len(neg) >= MIN_NEGATIVES
    ok = enough and not missed and not accepted
    return {"family": family, "validator": f["validator"],
            "state": "PROMOTABLE" if ok else "BLOCKED", "promotable": ok,
            "positives": pos, "negatives": neg, "missed_positives": missed,
            "accepted_negatives": accepted,
            "why": ("every positive passes and every plausible wrong alternative is rejected"
                    if ok else
                    f"too few examples ({len(pos)}/{MIN_POSITIVES} positive, "
                    f"{len(neg)}/{MIN_NEGATIVES} negative)" if not enough else
                    f"missed {missed}; accepted wrong {accepted}")}
