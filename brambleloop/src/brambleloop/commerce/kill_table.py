"""The scale/kill routing table, with every threshold marked for what it is (#23).

Requirement 23 is four sentences of routing and one of humility. Weak CTR goes to the
thumbnail and the title. Strong CTR with weak conversion goes to the offer, trust and price.
Strong conversion with low traffic goes to distribution. High sales with high support goes
to QA before anything scales. And then: *learn thresholds from real data*.

The routing is deterministic and is written here as a table, so that the action follows from
the diagnosis and not from whoever is looking at the dashboard. The thresholds are the part
nobody has. Every one below is marked `UNLEARNED`, carries the source it was borrowed from --
`scale.runrate`'s category-typical starting points, `growth.loops`'s measured-sample floor,
`commerce.benchmarks`'s refund-rate floor -- and is a default to be replaced by a learned
baseline, not a fact about this shop. A table whose thresholds are presented as findings
would route the first real listing on numbers invented before it existed.

Two things this module refuses. It refuses to route a listing that has not been shown to
enough people: below the sample floor every rule reports that its inputs are unmeasured, and
the recommended action is to wait, because pausing a listing on its fortieth visit is as wrong
as never pausing it. And it refuses to name a constraint `scale.runrate.constraint` would
name differently: `compose()` runs both and reports whether they agree, so a disagreement is
a finding and not a silent choice.

Today every input is UNMEASURED. There is no listing, no impression and no visit, and the
table says so on each row rather than defaulting a rate to zero and routing to "kill".
"""
from __future__ import annotations

from dataclasses import dataclass

from ..growth.loops import MEASURED_SAMPLE
from ..scale import runrate
from .benchmarks import MIN_ORDERS_FOR_REFUND_RATE

UNLEARNED = "UNLEARNED"
UNMEASURED = "UNMEASURED"

# The defect ceilings `scale.runrate.constraint` applies before any commercial term. Mirrored
# here as named constants and held to runrate by a test, because the two modules must flip at
# the same point or a listing can be "scale" in one report and "QA first" in the other.
DEFECT_SUPPORT_RATE = 0.10
DEFECT_REFUND_RATE = 0.05


@dataclass(frozen=True)
class Threshold:
    key: str
    value: float
    status: str
    source: str
    meaning: str

    def to_dict(self) -> dict:
        return {"key": self.key, "value": self.value, "status": self.status,
                "source": self.source, "meaning": self.meaning}


# Every threshold the table reads. All UNLEARNED: the spec says to learn them from real data
# and there is none, so each is a borrowed default with its source named.
THRESHOLDS: dict[str, Threshold] = {
    "ctr_weak_below": Threshold(
        "ctr_weak_below", runrate.BENCH_CTR * 0.5, UNLEARNED,
        "half of scale.runrate.BENCH_CTR, a category-typical starting point",
        "below this share of impressions becoming visits, the thumbnail is losing"),
    "ctr_strong_at": Threshold(
        "ctr_strong_at", runrate.BENCH_CTR, UNLEARNED,
        "scale.runrate.BENCH_CTR",
        "at or above this the hero has won the click"),
    "conversion_weak_below": Threshold(
        "conversion_weak_below", runrate.BENCH_CONVERSION * 0.5, UNLEARNED,
        "half of scale.runrate.BENCH_CONVERSION, a category-typical starting point",
        "below this share of visits becoming orders, the page is losing the buyer"),
    "conversion_strong_at": Threshold(
        "conversion_strong_at", runrate.BENCH_CONVERSION, UNLEARNED,
        "scale.runrate.BENCH_CONVERSION",
        "at or above this the listing closes"),
    "support_high_above": Threshold(
        "support_high_above", DEFECT_SUPPORT_RATE, UNLEARNED,
        "scale.runrate.constraint's defect rule",
        "support cases per order above this is a defect, and scaling a defect multiplies it"),
    "refund_high_above": Threshold(
        "refund_high_above", DEFECT_REFUND_RATE, UNLEARNED,
        "scale.runrate.constraint's defect rule",
        "refunds per order above this is a defect"),
    "min_visits_to_judge": Threshold(
        "min_visits_to_judge", float(MEASURED_SAMPLE), UNLEARNED,
        "growth.loops.MEASURED_SAMPLE",
        "below this many visits no rate means anything"),
    "min_orders_for_defect_rate": Threshold(
        "min_orders_for_defect_rate", float(MIN_ORDERS_FOR_REFUND_RATE), UNLEARNED,
        "commerce.benchmarks.MIN_ORDERS_FOR_REFUND_RATE",
        "one refund against three orders reads as 33% and is a rumour"),
}


@dataclass(frozen=True)
class Route:
    key: str
    condition: str
    action: str
    owner: str                       # the department the action belongs to
    needs: tuple[str, ...]           # the signals the rule reads
    runrate_rule: str | None         # the scale.runrate rule this corresponds to

    def to_dict(self) -> dict:
        return {"key": self.key, "condition": self.condition, "action": self.action,
                "owner": self.owner, "needs": list(self.needs),
                "runrate_rule": self.runrate_rule}


# In priority order. Defects first, because scaling a defect multiplies it; then the funnel
# in the order a visitor moves through it, for the same reason runrate walks it that way.
TABLE: tuple[Route, ...] = (
    Route("high_sales_high_support",
          "orders are arriving and support or refunds per order are above the defect ceiling",
          "QA before scaling: re-run the release chain on the listed version, read the cases "
          "as defects, and scale nothing until the rate is back under the ceiling",
          "quality", ("orders", "support_cases", "refunds"), "rising_defects"),
    Route("weak_ctr",
          "impressions are being shown and too few become visits",
          "thumbnail and title intervention: the hero and the first line, not the product",
          "creative", ("impressions", "visits"), "high_traffic_weak_ctr"),
    Route("strong_ctr_weak_conversion",
          "visits arrive and too few become orders",
          "offer, trust and price: the hero won the click and the page lost the buyer",
          "commerce", ("impressions", "visits", "orders"), "strong_ctr_weak_conversion"),
    Route("strong_conversion_low_traffic",
          "the page closes and nobody is arriving",
          "distribution investment: the listing works and is not being seen",
          "growth", ("visits", "orders"), "strong_conversion_low_traffic"),
    Route("weak_ctr_and_weak_conversion",
          "after a fair sample, both the thumbnail and the page are losing",
          "retire or re-engineer: two failed halves after a fair test is a product finding, "
          "not a merchandising one",
          "portfolio", ("impressions", "visits", "orders"), None),
    Route("healthy",
          "every measured rate is at or above its threshold and defects are under the ceiling",
          "scale gradually, re-measuring as contribution moves",
          "commerce", ("impressions", "visits", "orders"), "cac_below_allowable"),
)

BY_KEY: dict[str, Route] = {r.key: r for r in TABLE}


class KillTableRefused(ValueError):
    """A route asked for on a listing nobody has seen, or a threshold that is not a number."""


def _defect_rate(numerator: int | None, orders: int | None) -> float | None:
    if numerator is None or orders is None:
        return None
    if orders < MIN_ORDERS_FOR_REFUND_RATE:
        return None
    return numerator / orders


def route(observed: runrate.Observed, *, support_cases: int | None = None,
          refunds: int | None = None, needed_visits: int | None = None) -> dict:
    """Which row fires for one listing's signals, and which rows cannot be read.

    Every rule reports one of three things: it fired, it did not fire, or its inputs are
    UNMEASURED. A rule with an unmeasured input never fires and never counts as passed.
    """
    t = {k: v.value for k, v in THRESHOLDS.items()}
    ctr = observed.ctr
    conversion = observed.conversion
    visits = observed.visits
    support_rate = _defect_rate(support_cases, observed.orders)
    refund_rate = _defect_rate(refunds, observed.orders)

    signals = {
        "impressions": observed.impressions, "visits": visits, "orders": observed.orders,
        "support_cases": support_cases, "refunds": refunds,
        "ctr": None if ctr is None else round(ctr, 5),
        "conversion": None if conversion is None else round(conversion, 5),
        "support_rate": None if support_rate is None else round(support_rate, 4),
        "refund_rate": None if refund_rate is None else round(refund_rate, 4),
    }
    unmeasured = [k for k in ("impressions", "visits", "orders") if signals[k] is None]

    enough = visits is not None and visits >= t["min_visits_to_judge"]

    rows = []
    fired: str | None = None
    for r in TABLE:
        missing = [n for n in r.needs if signals.get(n) is None]
        if r.key == "high_sales_high_support":
            # Defects are read per order, so the floor is orders rather than visits.
            if support_rate is None and refund_rate is None:
                rows.append({**r.to_dict(), "status": UNMEASURED,
                             "why": (f"needs {MIN_ORDERS_FOR_REFUND_RATE} orders and the "
                                     f"support and refund counts; "
                                     f"{'none of these are measured' if missing else 'orders are below the floor'}")})
                continue
            hit = ((support_rate or 0.0) > t["support_high_above"]
                   or (refund_rate or 0.0) > t["refund_high_above"])
        elif missing or not enough:
            rows.append({**r.to_dict(), "status": UNMEASURED,
                         "why": (f"{missing} unmeasured" if missing else
                                 f"{visits} visits against a floor of "
                                 f"{int(t['min_visits_to_judge'])}: pausing a listing on its "
                                 f"fortieth visit is as wrong as never pausing it")})
            continue
        elif r.key == "weak_ctr":
            hit = ctr is not None and ctr < t["ctr_weak_below"] and not (
                conversion is not None and conversion < t["conversion_weak_below"])
        elif r.key == "weak_ctr_and_weak_conversion":
            hit = (ctr is not None and ctr < t["ctr_weak_below"]
                   and conversion is not None and conversion < t["conversion_weak_below"])
        elif r.key == "strong_ctr_weak_conversion":
            hit = (ctr is not None and ctr >= t["ctr_weak_below"]
                   and conversion is not None and conversion < t["conversion_weak_below"])
        elif r.key == "strong_conversion_low_traffic":
            hit = (conversion is not None and conversion >= t["conversion_strong_at"]
                   and needed_visits is not None and visits < needed_visits)
        else:  # healthy
            hit = (ctr is not None and ctr >= t["ctr_weak_below"]
                   and conversion is not None and conversion >= t["conversion_weak_below"]
                   and (needed_visits is None or visits >= needed_visits))
        rows.append({**r.to_dict(), "status": "fired" if hit else "not_fired"})
        if hit and fired is None:
            fired = r.key

    if fired is None:
        verdict = "wait" if (unmeasured or not enough) else "no_rule_fired"
        action = ("collect more signal before routing anything; every rate here is either "
                  "unmeasured or below the sample floor" if verdict == "wait" else
                  "no row fired: the rates sit between thresholds, which is a listing to "
                  "watch rather than one to act on")
    else:
        verdict = fired
        action = BY_KEY[fired].action

    return {
        "verdict": verdict, "action": action,
        "owner": BY_KEY[fired].owner if fired else None,
        "signals": signals, "unmeasured": unmeasured, "enough_sample": enough,
        "rows": rows,
        "thresholds": {k: v.to_dict() for k, v in THRESHOLDS.items()},
        "note": ("every threshold is UNLEARNED: a borrowed default with its source named, "
                 "to be replaced by a baseline learned from this shop's own data (#23)"),
    }


def compose(observed: runrate.Observed, *, support_cases: int | None = None,
            refunds: int | None = None, target_cad: float = 3000.0) -> dict:
    """The table and `scale.runrate.constraint` side by side, with whether they agree.

    Two modules that can each name a constraint must name the same one, or a listing is
    "scale" in one report and "QA first" in the other and somebody picks the one they like.
    """
    orders = observed.orders
    support_rate = _defect_rate(support_cases, orders)
    refund_rate = _defect_rate(refunds, orders)
    constraint = runrate.constraint(observed, target_cad=target_cad,
                                    refund_rate=refund_rate, support_rate=support_rate)
    needed = constraint.get("needed_visits_per_month")
    routed = route(observed, support_cases=support_cases, refunds=refunds,
                   needed_visits=int(needed) if needed else None)

    fired = routed["verdict"] if routed["verdict"] in BY_KEY else None
    runrate_rule = constraint.get("rule")
    if not constraint.get("identifiable"):
        agreement = {"comparable": False,
                     "why": "runrate cannot name a constraint yet: " + constraint["reason"]}
    elif fired is None:
        agreement = {"comparable": False,
                     "why": f"the table reached {routed['verdict']!r} and named no row"}
    else:
        expected = BY_KEY[fired].runrate_rule
        agreement = {"comparable": True, "agree": expected == runrate_rule,
                     "table_row": fired, "runrate_rule": runrate_rule,
                     "why": ("both name the same term" if expected == runrate_rule else
                             f"the table routed to {fired!r} and runrate named "
                             f"{runrate_rule!r}: a disagreement is a finding, not a choice")}

    return {"route": routed, "constraint": constraint, "agreement": agreement,
            "target_cad_per_month": target_cad}


def state() -> dict:
    """The table, its thresholds and what each needs, for a reader with no data."""
    return {
        "rows": [r.to_dict() for r in TABLE],
        "thresholds": {k: v.to_dict() for k, v in THRESHOLDS.items()},
        "all_thresholds_unlearned": all(v.status == UNLEARNED for v in THRESHOLDS.values()),
        "inputs_today": {k: UNMEASURED for k in ("impressions", "visits", "orders",
                                                 "support_cases", "refunds")},
        "composes_with": "scale.runrate.constraint",
        "note": ("Deterministic routing: weak CTR to the thumbnail and title, strong CTR with "
                 "weak conversion to offer, trust and price, strong conversion with low "
                 "traffic to distribution, high sales with high support to QA before scaling. "
                 "Every threshold is UNLEARNED and every input is UNMEASURED today, and the "
                 "table says so on each row rather than routing a listing nobody has seen "
                 "(#23)."),
    }
