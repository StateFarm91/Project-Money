"""Make-time distribution calibration (F-083) -- W4-C07.

"Replace single assumed maker speed with observed distributions by product class/skill level as
tester/customer evidence accumulates; seasonal runway uses uncertainty bounds."

The make-time estimate (`seasonal.leadtime.estimate_for`, from the twin's stitch count) is one
number, and the planner scales it by an *assumed* factor per skill (`Assumptions.skill_factor`:
beginner 1.6 ... experienced 0.8). This replaces that assumption with evidence where evidence
exists:

* `distributions(records)` -- tester/customer completions `{product_class, skill, hours,
  estimated_hours, source}`, grouped by (product class, skill). Each group's distribution is
  the observed/estimated ratio's p10, p50 and p90 (nearest-rank), once it has `MIN_SAMPLES`
  completions; below that it is UNMEASURED, and the planner keeps the assumed factor and says
  so. A record without both hours is not counted (UNKNOWN is never 0).
* `runway(...)` -- the seasonal launch dates from `seasonal.leadtime.compile_launch` at the
  observed p10 (optimistic), p50 (typical) and p90 (pessimistic) make-hours. Observed hours
  already belong to that skill, so the assumed skill factor is set to 1.0 for them rather than
  applied twice. With no distribution the assumed path runs unchanged, labelled ASSUMED, with
  its own (wide, sample-free) interval.

Only the optimistic bound may close a window (the planner's own rule); the pessimistic date is
when to start if the slow tail matters.
"""
from __future__ import annotations

from dataclasses import replace
from math import ceil

MIN_SAMPLES = 5
UNMEASURED = "UNMEASURED"


def _q(sorted_vals: list[float], p: float) -> float:
    k = max(1, ceil(p * len(sorted_vals)))
    return sorted_vals[k - 1]


def distributions(records) -> dict:
    groups: dict[tuple[str, str], list[float]] = {}
    skipped = 0
    for r in records or ():
        h, e = r.get("hours"), r.get("estimated_hours")
        if h is None or not e:
            skipped += 1
            continue
        groups.setdefault((r["product_class"], r["skill"]), []).append(float(h) / float(e))
    out = {}
    for (cls, skill), vals in sorted(groups.items()):
        vals.sort()
        key = f"{cls}/{skill}"
        if len(vals) < MIN_SAMPLES:
            out[key] = {"state": UNMEASURED, "n": len(vals),
                        "why": f"{len(vals)} of {MIN_SAMPLES} completions"}
            continue
        out[key] = {"state": "MEASURED", "n": len(vals),
                    "ratio": {"p10": round(_q(vals, 0.10), 3), "p50": round(_q(vals, 0.50), 3),
                              "p90": round(_q(vals, 0.90), 3)},
                    "basis": "observed hours / twin estimate, nearest-rank quantiles"}
    return {"groups": out, "skipped_incomplete": skipped}


def runway(*, event: str, event_date, today, estimated_hours: float, product_class: str,
           skill: str, records=(), assumptions=None) -> dict:
    from ..seasonal import leadtime as lt

    a = assumptions or lt.DEFAULT
    d = distributions(records)["groups"].get(f"{product_class}/{skill}")
    if not d or d["state"] != "MEASURED":
        plan = lt.compile_launch(event, event_date, make_hours=estimated_hours, skill=skill,
                                 assumptions=a)
        return {"basis": "ASSUMED", "distribution": d or {"state": UNMEASURED, "n": 0},
                "skill_factor": a.skill_factor.get(skill),
                "latest_launch": {"optimistic": plan.latest_optimistic_launch.isoformat(),
                                  "typical": plan.latest_effective_launch.isoformat(),
                                  "pessimistic": plan.latest_pessimistic_launch.isoformat()},
                "status": plan.status(today)}
    neutral = replace(a, skill_factor={**a.skill_factor, skill: 1.0})
    dates, hours = {}, {}
    for name, p in (("optimistic", "p10"), ("typical", "p50"), ("pessimistic", "p90")):
        h = round(estimated_hours * d["ratio"][p], 2)
        hours[name] = h
        dates[name] = lt.compile_launch(event, event_date, make_hours=h, skill=skill,
                                        assumptions=neutral).latest_effective_launch
    typical = lt.compile_launch(event, event_date, make_hours=hours["typical"], skill=skill,
                                assumptions=neutral)
    return {"basis": "MEASURED", "distribution": d, "make_hours": hours,
            "latest_launch": {k: v.isoformat() for k, v in dates.items()},
            "status": typical.status(today),
            "rule": "only the optimistic bound may close a window"}
