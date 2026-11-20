"""Checking the forecast against what happened, and paying for having been optimistic.

Requirement 262. Compare forecast against actual weekly and monthly revenue by channel and
category; decompose the error into traffic, CTR, conversion, AOV, repeat, launch timing and
winner rate; recalibrate the CA$5K trajectory continuously; and let optimistic model error
reduce confidence automatically.

Four things decide the implementation.

**A forecast that was not written down before the period is not a forecast.** Recalibration
from remembered expectations is the most reliable way to build a model that is always well
calibrated and never right: the expectation adjusts to the outcome on the way past, sincerely,
and nobody involved notices. So a `Forecast` carries `made_on`, it must precede the period it
predicts, and `compare()` refuses a forecast made during or after its own period. This is the
guard the rest of the module rests on, and it is the one that is inconvenient exactly when it
matters.

**A waterfall decomposition of a product is decided by whoever picks the order.** Revenue is
traffic times CTR times conversion times value, and substituting terms one at a time gives
each term a different share depending on where in the sequence it is walked -- so the person
doing the decomposition chooses, after seeing the numbers, how much of the miss belongs to
the term they would rather blame. Decomposing in log space is exact and order-independent:
the log of the total error is the sum of the logs of the term errors, with no interaction
left over and no sequence to choose. What that cannot do is invent a measurement, so terms
with no actual reading land in `unexplained` rather than being distributed across the ones
that were measured. Same rule as cost attribution: the table sums to the bill or it is
refused, and the remainder is named.

**Optimism costs more than pessimism, and it costs automatically.** Under-forecasting is a
pleasant surprise. Over-forecasting is a plan built on money that did not arrive, and by the
time it is visible the spending decisions it justified have already been made. So the penalty
is asymmetric, it applies without anybody agreeing to it, and it ratchets: confidence falls
immediately on an optimistic miss and recovers only after a run of accurate periods, slowly.
Symmetric recovery would let one good month erase a year of optimism, which is how a model
that has been wrong in one direction all year reports itself as calibrated.

**A period the shop was not selling in is not a forecast miss.** Today every actual is zero
because nothing is published, and a calibration run over those periods would report a
catastrophically optimistic model and take confidence to the floor. That would be arithmetic
rather than a finding -- the same defect as scoring marginal value from zero attributed
orders -- so a period with no exposure is excluded and counted, not scored.

This module never computes a probability of its own. `scale.confidence` owns that number, and
a second answer to it would mean the more flattering one gets quoted; what this produces is a
*ceiling*, which can lower that number and can never raise it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

# ---- the seven terms ------------------------------------------------------

# Named by the requirement, and each one a multiplicative factor on monthly revenue, because
# the decomposition below is only exact if they multiply to the thing being decomposed.
TERMS: dict[str, str] = {
    "qualified_traffic": "impressions reaching the listings in the period",
    "ctr": "share of impressions that became a visit",
    "conversion": "share of visits that became an order",
    "aov_cad": "average order value",
    "repeat_factor": "1 + additional orders per first order",
    "launch_timing": "the share of planned releases that landed inside their window",
    "winner_rate_factor": "the traffic multiple contributed by disproportionate earners",
}

# The decomposition reconstructs revenue from the terms. If the product misses the stated
# revenue by more than this, the terms are not a model of that revenue and decomposing it
# would attribute an error that is really a bookkeeping disagreement.
RECONSTRUCTION_TOLERANCE = 0.005


class CalibrationRefused(ValueError):
    """A comparison the evidence does not support, or a forecast written afterwards."""


@dataclass(frozen=True)
class Period:
    """A week or a month of one channel and category, which is the grain #262 asks for."""

    label: str
    starts_on: date
    ends_on: date
    channel: str = "all"
    category: str = "all"

    def __post_init__(self) -> None:
        if self.ends_on < self.starts_on:
            raise CalibrationRefused(f"{self.label}: ends before it starts")

    @property
    def slice(self) -> tuple[str, str]:
        return (self.channel, self.category)


@dataclass(frozen=True)
class Forecast:
    """What the model said, and -- the part that matters -- when it said it."""

    period: Period
    made_on: date
    revenue_cad: float
    terms: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.made_on >= self.period.starts_on:
            raise CalibrationRefused(
                f"{self.period.label}: forecast dated {self.made_on.isoformat()}, which is "
                f"not before the period it predicts. A forecast recorded once the period is "
                f"under way is a description, and calibrating against descriptions produces "
                f"a model that is always well calibrated and never right")
        if self.revenue_cad < 0:
            raise CalibrationRefused("a negative revenue forecast is not a forecast")
        unknown = sorted(set(self.terms) - set(TERMS))
        if unknown:
            raise CalibrationRefused(f"{unknown} are not decomposition terms: {sorted(TERMS)}")
        for name, value in self.terms.items():
            if value <= 0:
                raise CalibrationRefused(
                    f"{name}={value}: every term is a multiplicative factor, so none of them "
                    f"can be zero or negative without the decomposition losing its meaning")


@dataclass(frozen=True)
class Actual:
    """What happened, and whether the shop was selling at all while it happened."""

    period: Period
    revenue_cad: float
    terms: dict[str, float] = field(default_factory=dict)
    live_listings: int = 0

    def __post_init__(self) -> None:
        if self.revenue_cad < 0:
            raise CalibrationRefused("negative actual revenue is not a measurement")
        unknown = sorted(set(self.terms) - set(TERMS))
        if unknown:
            raise CalibrationRefused(f"{unknown} are not decomposition terms: {sorted(TERMS)}")
        for name, value in self.terms.items():
            if value <= 0:
                raise CalibrationRefused(f"{name}={value}: terms are positive factors")

    @property
    def exposed(self) -> bool:
        """Whether the model was applied to anything. Zero listings is not a bad forecast."""
        return self.live_listings > 0


# ---- one period -----------------------------------------------------------

OPTIMISTIC = "optimistic"
PESSIMISTIC = "pessimistic"
ACCURATE = "accurate"
NOT_EXPOSED = "not_exposed"

# Inside this band the model was right enough that calling it a miss would be noise.
ACCURATE_WITHIN = 0.15


def compare(forecast: Forecast, actual: Actual) -> dict:
    """One forecast against one outcome, with the direction of the miss named."""
    if forecast.period.label != actual.period.label:
        raise CalibrationRefused(
            f"comparing {forecast.period.label!r} against {actual.period.label!r}")
    if not actual.exposed:
        return {"period": forecast.period.label, "slice": list(forecast.period.slice),
                "verdict": NOT_EXPOSED, "scored": False,
                "why": ("no live listings in this period, so the model was never applied to "
                        "anything. Zero revenue against a positive forecast is arithmetic "
                        "about an unopened shop, not evidence the model is optimistic")}
    if forecast.revenue_cad <= 0:
        return {"period": forecast.period.label, "slice": list(forecast.period.slice),
                "verdict": NOT_EXPOSED, "scored": False,
                "why": "a zero forecast has no relative error to measure against"}

    signed = (actual.revenue_cad - forecast.revenue_cad) / forecast.revenue_cad
    if abs(signed) <= ACCURATE_WITHIN:
        verdict = ACCURATE
    elif signed < 0:
        verdict = OPTIMISTIC
    else:
        verdict = PESSIMISTIC
    return {
        "period": forecast.period.label, "slice": list(forecast.period.slice),
        "forecast_cad": round(forecast.revenue_cad, 2),
        "actual_cad": round(actual.revenue_cad, 2),
        "signed_error": round(signed, 4), "magnitude": round(abs(signed), 4),
        "verdict": verdict, "scored": True,
        "why": (f"forecast {forecast.revenue_cad:.2f}, actual {actual.revenue_cad:.2f}: "
                f"{abs(signed):.1%} {'below' if signed < 0 else 'above'} the forecast"),
    }


def _reconstructs(revenue: float, terms: dict[str, float]) -> bool:
    if not terms or set(terms) != set(TERMS):
        return False
    product = 1.0
    for value in terms.values():
        product *= value
    if revenue <= 0:
        return False
    return abs(product - revenue) / revenue <= RECONSTRUCTION_TOLERANCE


def decompose(forecast: Forecast, actual: Actual) -> dict:
    """Where the miss came from, in log space so the answer does not depend on the order.

    Each term contributes `log(actual_i / forecast_i)`, and those sum exactly to
    `log(actual / forecast)` when every term is measured. A term with no actual reading is
    not distributed across the measured ones: it lands in `unexplained`, which is the number
    worth looking at, because the unmodelled term is always the one nobody has a story for.
    """
    if forecast.revenue_cad <= 0 or actual.revenue_cad <= 0:
        raise CalibrationRefused(
            "a decomposition needs a positive forecast and a positive actual: the ratio of "
            "the two is what is being split up")
    if not _reconstructs(forecast.revenue_cad, forecast.terms):
        raise CalibrationRefused(
            "the forecast terms do not multiply to the forecast revenue within "
            f"{RECONSTRUCTION_TOLERANCE:.1%}. Terms that do not reconstruct the total are a "
            "model of something else, and splitting this error across them would attribute "
            "a bookkeeping disagreement to conversion")

    total = math.log(actual.revenue_cad / forecast.revenue_cad)
    contributions: dict[str, float] = {}
    explained = 0.0
    unmeasured: list[str] = []
    for name in TERMS:
        f = forecast.terms.get(name)
        a = actual.terms.get(name)
        if f is None or a is None:
            unmeasured.append(name)
            continue
        c = math.log(a / f)
        contributions[name] = c
        explained += c

    residual = total - explained
    share = {name: (c / total if total else 0.0) for name, c in contributions.items()}
    return {
        "period": forecast.period.label,
        "log_total": round(total, 6),
        "contributions": {k: round(v, 6) for k, v in sorted(contributions.items())},
        "share_of_error": {k: round(v, 4) for k, v in sorted(share.items())},
        "unexplained": round(residual, 6),
        "unexplained_share": round(residual / total, 4) if total else 0.0,
        "unmeasured_terms": sorted(unmeasured),
        "exact": not unmeasured,
        "method": ("log space, so the split is order-independent. A waterfall over a product "
                   "gives each term a different share depending where it is walked, and the "
                   "order is chosen after the numbers are known"),
    }


# ---- many periods ---------------------------------------------------------

MIN_SCORED_PERIODS = 4

# Optimism is penalised five times as hard as pessimism of the same size: a pleasant surprise
# costs nothing, and money that did not arrive was already spent against.
OPTIMISM_WEIGHT = 0.50
PESSIMISM_WEIGHT = 0.10
CEILING_FLOOR = 0.05

# Recovery is a ratchet. Confidence lost to optimism comes back only after a run of accurate
# periods, one step at a time, because symmetric recovery lets a single good month erase a
# year of being wrong in the same direction.
RECOVERY_RUN = 3
RECOVERY_STEP = 0.05


def calibrate(pairs: list[tuple[Forecast, Actual]]) -> dict:
    """The whole history: which way the model is wrong, by how much, and per term."""
    comparisons = [compare(f, a) for f, a in pairs]
    scored = [c for c in comparisons if c["scored"]]
    excluded = [c for c in comparisons if not c["scored"]]

    per_term: dict[str, list[float]] = {name: [] for name in TERMS}
    for f, a in pairs:
        if not a.exposed or f.revenue_cad <= 0 or a.revenue_cad <= 0:
            continue
        if not _reconstructs(f.revenue_cad, f.terms):
            continue
        for name in TERMS:
            fv, av = f.terms.get(name), a.terms.get(name)
            if fv and av:
                per_term[name].append(math.log(av / fv))

    bias = {}
    for name, values in per_term.items():
        if not values:
            bias[name] = {"periods": 0, "bias": None,
                          "reading": "unmeasured -- which is not the same as unbiased"}
            continue
        mean = sum(values) / len(values)
        bias[name] = {
            "periods": len(values), "bias": round(mean, 4),
            "reading": ("forecast too high" if mean < -0.05 else
                        "forecast too low" if mean > 0.05 else "no consistent direction"),
        }

    optimistic = [c for c in scored if c["verdict"] == OPTIMISTIC]
    pessimistic = [c for c in scored if c["verdict"] == PESSIMISTIC]
    accurate = [c for c in scored if c["verdict"] == ACCURATE]

    enough = len(scored) >= MIN_SCORED_PERIODS
    return {
        "periods_supplied": len(comparisons),
        "scored": len(scored),
        "excluded_unexposed": len(excluded),
        "optimistic": len(optimistic), "pessimistic": len(pessimistic),
        "accurate": len(accurate),
        "mean_signed_error": (round(sum(c["signed_error"] for c in scored) / len(scored), 4)
                              if scored else None),
        "term_bias": bias,
        "calibrated": enough,
        "why": (f"{len(scored)} scored periods" if enough else
                f"{len(scored)} scored periods is not a calibration; "
                f"{MIN_SCORED_PERIODS} are needed, and one comparison is an anecdote"),
        "comparisons": comparisons,
    }


def ceiling(pairs: list[tuple[Forecast, Actual]], *, prior: float = 1.0) -> dict:
    """The cap this history puts on any confidence claim. It lowers; it never raises.

    Returned as a ceiling rather than a probability because `scale.confidence` owns the
    probability, and two answers to one question means the more flattering one gets quoted.
    """
    result = calibrate(pairs)
    scored = [c for c in result["comparisons"] if c["scored"]]
    if not scored:
        return {"ceiling": round(prior, 3), "applied": False,
                "why": ("no scored period: every period supplied had no live listings, so "
                        "there is nothing here to hold a forecast to"),
                "scored": 0}

    cap = prior
    for c in scored:
        if c["verdict"] == OPTIMISTIC:
            cap *= max(0.0, 1 - OPTIMISM_WEIGHT * min(1.0, c["magnitude"]))
        elif c["verdict"] == PESSIMISTIC:
            cap *= max(0.0, 1 - PESSIMISM_WEIGHT * min(1.0, c["magnitude"]))

    # The ratchet: a run of accurate periods at the end of the history earns steps back.
    run = 0
    for c in reversed(scored):
        if c["verdict"] == ACCURATE:
            run += 1
        else:
            break
    recovered = 0
    if run >= RECOVERY_RUN:
        recovered = run - RECOVERY_RUN + 1
        cap = min(prior, cap + RECOVERY_STEP * recovered)

    cap = max(CEILING_FLOOR, min(prior, cap))
    return {
        "ceiling": round(cap, 3), "applied": cap < prior, "prior": prior,
        "scored": len(scored),
        "optimistic_periods": result["optimistic"],
        "accurate_run": run, "recovery_steps": recovered,
        "why": (f"{result['optimistic']} of {len(scored)} scored periods were optimistic. "
                f"Optimism is weighted {OPTIMISM_WEIGHT / PESSIMISM_WEIGHT:.0f}x pessimism "
                f"because a plan was built on money that did not arrive, and recovery needs "
                f"{RECOVERY_RUN} consecutive accurate periods before it begins"),
        "note": ("a ceiling, not a probability: scale.confidence computes the number and "
                 "this can only lower it"),
    }


def state() -> dict:
    """What the calibrator has, and what it is honest about not having."""
    return {
        "requirement": 262,
        "terms": list(TERMS),
        "grain": "week or month, by channel and category",
        "min_scored_periods": MIN_SCORED_PERIODS,
        "accurate_within": ACCURATE_WITHIN,
        "asymmetry": f"{OPTIMISM_WEIGHT / PESSIMISM_WEIGHT:.0f}x against optimism",
        "recovery": f"{RECOVERY_RUN} consecutive accurate periods, then {RECOVERY_STEP} a step",
        "refuses": [
            "a forecast dated on or after the period it predicts",
            "a decomposition whose terms do not reconstruct the revenue",
            "a period with no live listings, which is excluded rather than scored",
        ],
        "today": ("no scored periods exist: nothing is published, so every period would be "
                  "excluded as unexposed. The calibrator reports that rather than reporting "
                  "a model that is catastrophically optimistic about an unopened shop"),
        "owns": "a ceiling on confidence, never a probability",
    }
