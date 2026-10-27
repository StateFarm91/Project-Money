"""Gauge learning system (F-809) -- W4-C11.

"Gauge receives a dedicated educational system: stitch vs row gauge, swatching, hook
adjustment, yarn substitution, tension consistency, blocking and garment-fit consequences.
Visual examples and calculators must agree with Product Truth."

The calculators. Each is arithmetic a learner can repeat, and the one that matters most --
what a different gauge does to the finished piece -- is not a formula of its own: `fit`
rebuilds the pattern's digital twin (`cir.twin.build_twin`, the same model the PDF's finished
size and the support concierge answer from) at the learner's measured gauge. So the lesson's
calculator and the product's stated size cannot disagree; they are one computation.

* `measure_swatch` -- stitch gauge and row gauge, separately, per 10 cm;
* `hook_advice` -- the direction to change hook (more stitches than the pattern: the fabric is
  tight, go up a size) to the next standard size; within `TOLERANCE` it says keep the hook. It
  never promises the new hook will hit gauge: swatch again;
* `consistency` -- the spread of repeated swatch readings; above `MAX_CV` the tension is not
  yet consistent and no single reading should be trusted;
* `blocking` -- the change from unblocked to blocked; above `TOLERANCE` gauge must be measured
  blocked, because that is what the finished piece will be;
* `substitute` -- skeins of a substitute yarn for the pattern's metres (the twin's yardage and
  its stated tolerance), refused across yarn-weight classes;
* `fit` -- finished width and height at the learner's gauge against the pattern's, and the
  difference in cm and percent.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import replace

TOLERANCE = 0.02       # 2 % either way is "on gauge"
MAX_CV = 0.03
HOOKS_MM = (2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0,
            8.0, 9.0, 10.0)


class GaugeRefused(ValueError):
    pass


def measure_swatch(*, stitches: int, rows: int, width_cm: float, height_cm: float) -> dict:
    if min(stitches, rows) <= 0 or min(width_cm, height_cm) <= 0:
        raise GaugeRefused("a swatch needs a positive stitch count, row count and size")
    return {"stitches_per_10cm": round(stitches * 10 / width_cm, 2),
            "rows_per_10cm": round(rows * 10 / height_cm, 2),
            "note": "stitch gauge sets width and row gauge sets length; they are matched "
                    "separately and can be off in different directions"}


def _ratio(measured: float, target: float) -> float:
    return (measured - target) / target


def hook_advice(*, target_sts: float, measured_sts: float, hook_mm: float) -> dict:
    r = _ratio(measured_sts, target_sts)
    if abs(r) <= TOLERANCE:
        return {"action": "keep", "hook_mm": hook_mm, "off_by": round(r, 4),
                "why": "within 2 % of the pattern's stitch gauge"}
    bigger = r > 0       # too many stitches per 10 cm: the fabric is tight
    sizes = [h for h in HOOKS_MM if (h > hook_mm if bigger else h < hook_mm)]
    nxt = (min(sizes) if bigger else max(sizes)) if sizes else None
    return {"action": "go_up" if bigger else "go_down", "hook_mm": nxt, "off_by": round(r, 4),
            "why": (f"{abs(r):.0%} {'more' if bigger else 'fewer'} stitches per 10 cm than the "
                    f"pattern; try the next size and swatch again"
                    + ("" if nxt else "; no standard size remains in that direction"))}


def consistency(readings) -> dict:
    vals = [float(v) for v in readings or ()]
    if len(vals) < 2:
        return {"state": "UNMEASURED", "why": "consistency needs two or more readings"}
    cv = statistics.pstdev(vals) / statistics.mean(vals)
    return {"state": "CONSISTENT" if cv <= MAX_CV else "INCONSISTENT", "cv": round(cv, 4),
            "why": (f"readings vary by {cv:.1%}" +
                    ("" if cv <= MAX_CV else "; practise until they settle before matching "
                                             "gauge"))}


def blocking(*, unblocked_sts: float, blocked_sts: float) -> dict:
    r = _ratio(blocked_sts, unblocked_sts)
    return {"change": round(r, 4), "measure_blocked": abs(r) > TOLERANCE,
            "why": (f"blocking changed the stitch gauge by {r:+.1%}; " +
                    ("measure gauge after blocking" if abs(r) > TOLERANCE else
                     "either measurement will do"))}


def _twin(cir):
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    return build_twin(cir, compile_cir(cir))


def substitute(cir, *, metres_per_skein: float, yarn_weight: str) -> dict:
    twin = _twin(cir)
    weights = {m.yarn_weight for m in cir.materials if m.yarn_weight}
    if weights and yarn_weight not in weights:
        raise GaugeRefused(f"{yarn_weight!r} is not the pattern's {sorted(weights)}: a "
                           f"different weight class changes gauge, so yardage alone is not "
                           f"a substitution")
    metres = sum(twin.yarn_metres_by_color.values())
    with_tol = metres * (1 + twin.yardage_tolerance)
    return {"pattern_metres": round(metres, 1), "with_tolerance_metres": round(with_tol, 1),
            "skeins": math.ceil(with_tol / float(metres_per_skein)),
            "basis": "cir.twin yardage and its stated tolerance (Product Truth)"}


def fit(cir, *, stitches_per_10cm: float, rows_per_10cm: float) -> dict:
    if cir.gauge is None:
        raise GaugeRefused("the pattern states no gauge, so there is nothing to compare")
    design = _twin(cir)
    yours = _twin(replace(cir, gauge=replace(cir.gauge, stitches_per_10cm=stitches_per_10cm,
                                             rows_per_10cm=rows_per_10cm)))

    def diff(a, b):
        if a is None or b is None:
            return {"pattern_cm": a, "yours_cm": b, "difference_cm": None,
                    "difference_pct": None}
        return {"pattern_cm": round(a, 1), "yours_cm": round(b, 1),
                "difference_cm": round(b - a, 1), "difference_pct": round((b - a) / a, 4)}

    return {"width": diff(design.width_cm, yours.width_cm),
            "height": diff(design.height_cm, yours.height_cm),
            "basis": "cir.twin rebuilt at your gauge: the same model as the stated size"}
