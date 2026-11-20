"""A trajectory made of assumptions, labelled as one.

Requirement 26. Nightly scenario analysis over the eleven terms the requirement names --
listing count, qualified traffic, click-through, conversion, order value, repeat rate,
organic growth, paid CAC, product velocity, winner rate and retirement rate -- with the
assumptions and their sensitivity shown, the primary constraint identified, and one
instruction that governs the whole module: *do not present modeled probabilities as
objective truth*.

That instruction is not a disclaimer to append. A Monte Carlo over inputs nobody has
measured produces a distribution of *assumptions*, not of outcomes, and it produces it to
four decimal places with a histogram, which is what makes it persuasive. So:

**No function here returns a bare probability.** A number like 0.62 detaches from its
provenance the moment somebody writes it in a summary, and a probability without its
provenance is exactly the objective-truth claim the requirement forbids. Every figure comes
back inside its evidence -- how much of the model was observed, which terms were assumed,
and what the assumption was.

**Below the observed-share floor the run is named an assumption space and states no
probability at all.** This is the honest form of "once enough real data exists". Today the
figure is zero: no listing has an impression, no visitor has arrived and nothing has been
bought, so what a simulation would show is the shape of whatever was typed into it.

**The sensitivity ranking is the actual output while the inputs are assumed.** It does not
say what will happen; it says which assumption the answer is hostage to, which is the
question a company with no data can actually act on -- go and measure that one.

**The seed is the date.** A simulator that answers differently every night makes a trend
unreadable, and the first thing anybody does with a nightly number is compare it to last
night's.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from .runrate import Observed, constraint

# The eleven terms, with what each one is. Closed: a term nobody named cannot be assumed
# quietly into the model.
TERMS: dict[str, str] = {
    "listing_count": "how many listings exist",
    "qualified_traffic": "impressions reaching those listings each month",
    "ctr": "the share of impressions that become a visit",
    "conversion": "the share of visits that become an order",
    "aov_cad": "average order value",
    "repeat_rate": "additional orders per first order, from the same buyer",
    "organic_growth": "month-on-month growth in impressions, before new listings",
    "paid_cac_cad": "cost to buy one order, when paid traffic is authorised",
    "product_velocity": "new listings released per month",
    "winner_rate": "the share of new listings that become disproportionate earners",
    "retirement_rate": "the share of listings withdrawn per month",
}

# How much of the model must be observed before a probability may be stated at all.
MIN_OBSERVED_SHARE = 0.60
# What a winner is worth, as a multiple of an ordinary listing's traffic share. Itself an
# assumption, named as one rather than buried in the arithmetic.
WINNER_LIFT = 3.0
TRIALS = 2000

OBSERVED = "observed"


class TrajectoryRefused(ValueError):
    """A term nobody named, or a range that is not a range."""


@dataclass(frozen=True)
class Value:
    """One term's value, its range, and where it came from."""

    point: float
    low: float
    high: float
    source: str = ""          # "observed", or the basis for the assumption

    def __post_init__(self) -> None:
        if not (self.low <= self.point <= self.high):
            raise TrajectoryRefused(
                f"{self.low} <= {self.point} <= {self.high} is not a range. A point outside "
                f"its own interval is a typo that produces a confident answer")
        if not self.source.strip():
            raise TrajectoryRefused(
                "a value with no source cannot be told apart from a measurement, which is "
                "the whole distinction this module exists to keep")

    @property
    def observed(self) -> bool:
        return self.source == OBSERVED


def _check(inputs: dict[str, Value]) -> None:
    unknown = sorted(set(inputs) - set(TERMS))
    if unknown:
        raise TrajectoryRefused(f"{unknown} are not terms: {sorted(TERMS)}")
    missing = sorted(set(TERMS) - set(inputs))
    if missing:
        raise TrajectoryRefused(
            f"{missing} have no value at all. A term left out of the model is a term the "
            f"model assumed silently, which is worse than assuming it out loud")


def observed_share(inputs: dict[str, Value]) -> float:
    return sum(1 for v in inputs.values() if v.observed) / len(TERMS)


def _project(draw: dict[str, float], months: int) -> float:
    """Monthly revenue after `months`, from one draw of the terms."""
    listings = max(1.0, draw["listing_count"])
    traffic = draw["qualified_traffic"]
    winners = 0.0
    revenue = 0.0
    for _ in range(months):
        released = draw["product_velocity"]
        retired = listings * draw["retirement_rate"]
        before = listings
        listings = max(1.0, listings + released - retired)
        winners += released * draw["winner_rate"]
        # Traffic grows organically, with the catalogue, and with whatever winners exist.
        # A winner is worth a multiple of an ordinary listing rather than a separate channel,
        # because it earns its traffic in the same search results as everything else.
        traffic = traffic * (1 + draw["organic_growth"]) * (listings / before)
        lift = 1 + (winners * (WINNER_LIFT - 1) / listings)
        visits = traffic * lift * draw["ctr"]
        orders = visits * draw["conversion"] * (1 + draw["repeat_rate"])
        revenue = orders * draw["aov_cad"]
    return revenue


def run(inputs: dict[str, Value], *, months: int = 12, target_cad: float = 3000.0,
        on: date | None = None, trials: int = TRIALS) -> dict:
    """The scenario analysis, inside its own provenance.

    The seed is the date, so two reads of the same night agree; a nightly number is compared
    to last night's before it is compared to anything else, and a simulator that moves on
    its own makes that comparison meaningless.
    """
    _check(inputs)
    on = on or date.today()
    share = observed_share(inputs)
    rng = random.Random(f"{on.isoformat()}|{months}|{target_cad}")

    results = []
    for _ in range(trials):
        draw = {k: rng.triangular(v.low, v.high, v.point) for k, v in inputs.items()}
        results.append(_project(draw, months))
    results.sort()

    def pct(p: float) -> float:
        return round(results[min(len(results) - 1, int(p * len(results)))], 2)

    reached = sum(1 for r in results if r >= target_cad) / len(results)
    assumed = sorted(k for k, v in inputs.items() if not v.observed)

    out = {
        "on": on.isoformat(), "months": months, "target_cad": target_cad,
        "trials": trials,
        "observed_share": round(share, 3),
        "assumed_terms": assumed,
        "assumptions": {k: {"point": v.point, "low": v.low, "high": v.high,
                            "source": v.source}
                        for k, v in sorted(inputs.items()) if not v.observed},
        "monthly_revenue_cad": {"p10": pct(0.10), "p50": pct(0.50), "p90": pct(0.90)},
        "sensitivity": sensitivity(inputs, months=months),
        "seed": "the date, so two reads of the same night agree",
    }

    if share < MIN_OBSERVED_SHARE:
        out["kind"] = "assumption_space"
        out["probability"] = None
        out["what_this_is"] = (
            f"{share:.0%} of the model was observed, against a floor of "
            f"{MIN_OBSERVED_SHARE:.0%}. This is the shape of what was typed into it, not a "
            f"forecast, and it states no probability: a Monte Carlo over unmeasured inputs "
            f"produces a distribution of assumptions to four decimal places, which is what "
            f"makes it persuasive. The output to act on is the sensitivity ranking -- it "
            f"says which assumption the answer is hostage to, and that one is worth going "
            f"and measuring")
    else:
        out["kind"] = "forecast"
        out["probability"] = {
            "of_reaching_target": round(reached, 3),
            "over_trials": trials,
            "observed_share": round(share, 3),
            "assumed_terms": assumed,
            "not_objective": (
                "a modelled probability is a property of this model and these assumptions, "
                "never of the world. It is reported inside its provenance because a bare "
                "number detaches from it the moment somebody writes it in a summary"),
        }
        out["what_this_is"] = (
            f"a forecast conditional on {len(assumed)} assumed term(s), each listed above "
            f"with its basis")
    return out


def sensitivity(inputs: dict[str, Value], *, months: int = 12) -> list[dict]:
    """Which assumption the answer is hostage to, ranked.

    Each term is swung to its own low and high with everything else at its point value, and
    the spread that produces is what the answer is riding on. While the inputs are assumed
    this is the module's real output: it does not say what will happen, it says what to go
    and measure first.
    """
    _check(inputs)
    base = {k: v.point for k, v in inputs.items()}
    rows = []
    for term, value in inputs.items():
        low = dict(base, **{term: value.low})
        high = dict(base, **{term: value.high})
        at_low, at_high = _project(low, months), _project(high, months)
        rows.append({
            "term": term, "what": TERMS[term],
            "observed": value.observed,
            "at_low_cad": round(at_low, 2), "at_high_cad": round(at_high, 2),
            "spread_cad": round(abs(at_high - at_low), 2),
        })
    rows.sort(key=lambda r: -r["spread_cad"])
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


# What each term is assumed to be when it has not been observed, and on what basis. Wide on
# purpose: an assumption stated narrowly is a forecast pretending not to be one.
ASSUMED: dict[str, tuple[float, float, float, str]] = {
    "qualified_traffic": (1500.0, 200.0, 8000.0,
                          "assumed: impressions per month for a new shop's catalogue"),
    "ctr": (0.020, 0.005, 0.040, "assumed: growth.portfolio.BENCH_CTR, category-typical"),
    "conversion": (0.025, 0.005, 0.050,
                   "assumed: growth.portfolio.BENCH_CONVERSION, category-typical"),
    "aov_cad": (9.0, 5.0, 20.0, "assumed: the catalogue's own price band"),
    "repeat_rate": (0.10, 0.0, 0.35, "assumed: growth.loops repeat ceiling 0.35"),
    "organic_growth": (0.05, 0.0, 0.20, "assumed: month-on-month impression growth"),
    "paid_cac_cad": (8.0, 3.0, 20.0,
                     "assumed: paid traffic is not authorised, so no CAC has been paid"),
    "winner_rate": (0.05, 0.0, 0.20, "assumed: share of listings that become winners"),
}


def observed_terms(db, *, on: date | None = None) -> dict:
    """Every term this database can actually answer, as `Value`s sourced `observed` (C-64).

    Read from `scale.runrate.observe` (listing outcomes, orders, the ledger, published
    listings) and from the release and listing tables for velocity and retirement. A term
    with no source is absent here -- it is never zero-for-unknown.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion
    from .runrate import observe

    on = on or date.today()
    got = observe(db, today=on)
    o = got["observed"]
    out: dict[str, Value] = {}

    def put(term: str, value) -> None:
        if value is not None:
            v = float(value)
            out[term] = Value(v, v, v, OBSERVED)

    put("listing_count", o.listings)
    put("qualified_traffic", o.impressions)
    put("ctr", o.ctr)
    put("conversion", o.conversion)
    put("aov_cad", o.aov_cad)
    if o.orders and o.repeat_orders is not None:
        put("repeat_rate", o.repeat_orders / o.orders)
    since = datetime(on.year, on.month, on.day, tzinfo=timezone.utc) - timedelta(days=30)
    with db.session() as s:
        released = [v for v in s.scalars(select(PatternVersion).where(
            PatternVersion.certified.is_(True)))
                    if (v.created_at if v.created_at.tzinfo else
                        v.created_at.replace(tzinfo=timezone.utc)) >= since]
        listings = list(s.scalars(select(Listing)))
    put("product_velocity", len(released))
    if listings:
        put("retirement_rate", sum(1 for r in listings if r.state == "withdrawn")
            / len(listings))
    return {"terms": out, "observe": got}


def nightly(db, *, on: date | None = None, target_cad: float = 3000.0) -> dict:
    """The nightly run against what this company has actually observed (#26, C-64).

    With a database, every term the rows can answer is `observed` and every other is an
    assumption with its basis, and the scenario analysis runs: below the observed-share floor
    it is an assumption space with no probability and a sensitivity ranking that names which
    assumption the answer is hostage to; above it, a forecast inside its provenance. The
    primary constraint is `runrate.constraint` over the observed funnel, never an empty one.
    Without a database there is nothing observed and the run refuses, naming the constraint.
    """
    on = on or date.today()
    if db is None:
        binding = constraint(Observed(), target_cad=target_cad)
        return {
            "on": on.isoformat(),
            "ran": False,
            "why": ("no database was read, so no term of the model has been observed. A "
                    "nightly probability computed from that is a nightly restatement of "
                    "whatever was typed in"),
            "observed_share": 0.0,
            "floor": MIN_OBSERVED_SHARE,
            "primary_constraint": binding,
            "terms_needed": sorted(TERMS),
        }
    got = observed_terms(db, on=on)
    inputs = dict(got["terms"])
    for term, (point, low, high, basis) in ASSUMED.items():
        inputs.setdefault(term, Value(point, low, high, basis))
    inputs.setdefault("listing_count", Value(0.0, 0.0, 0.0, OBSERVED))
    inputs.setdefault("product_velocity", Value(0.0, 0.0, 0.0, OBSERVED))
    inputs.setdefault("retirement_rate", Value(0.0, 0.0, 0.25,
                                                "assumed: no listing exists to retire"))
    observed = got["observe"]
    binding = constraint(observed["observed"], target_cad=target_cad,
                         refund_rate=observed["refund_rate"],
                         support_rate=observed["support_rate"])
    result = run(inputs, target_cad=target_cad, on=on)
    top = result["sensitivity"][0] if result["sensitivity"] else None
    return {
        **result,
        "ran": True,
        "observed_terms": sorted(k for k, v in inputs.items() if v.observed),
        "unmeasured_funnel": observed["unmeasured"],
        "floor": MIN_OBSERVED_SHARE,
        "primary_constraint": binding,
        "hostage_to": (top["term"] if top else None),
        "measure_next": next((r["term"] for r in result["sensitivity"]
                              if not r["observed"]), None),
    }


def state() -> dict:
    """The terms, the floor, and what this module refuses to say."""
    return {
        "terms": dict(TERMS),
        "observed_share_floor": MIN_OBSERVED_SHARE,
        "winner_lift": WINNER_LIFT,
        "trials": TRIALS,
        "never": ("a bare probability. Every figure is returned inside its provenance -- how "
                  "much of the model was observed, which terms were assumed and on what "
                  "basis -- because a number detaches from its caveat the moment somebody "
                  "writes it in a summary, and a modelled probability without its "
                  "provenance is the objective-truth claim this requirement forbids (#26)"),
    }
