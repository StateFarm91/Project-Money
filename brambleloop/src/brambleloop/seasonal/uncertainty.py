"""Make-time as a distribution, because nobody has ever timed a Brambleloop maker.

The lead-time engine computes a launch date by chaining make-time, buffers and ramp. Every
term in that chain is an assumption, and the chain produced a single date — which was then
reported as a fact, and then reported as an *impossibility*: "LONG and FLAGSHIP Christmas work
is arithmetically impossible". That sentence is wrong in a specific and embarrassing way. The
arithmetic is exact; its inputs are guesses. A point estimate cannot establish impossibility,
and this build refuses exactly that move everywhere else — unmeasured is not zero, absent is
not inferred, a benchmark is not a measurement — and then made it in the one place where the
output is a decision about a whole season.

So make-time is an interval, and three properties matter.

**The spread is wide while there is no evidence, and it narrows as samples arrive.** With zero
physical tests the company does not know whether its maker crochets four hours a week or
fifteen, or whether "intermediate" means what the pattern thinks. The interval reflects that,
and every recorded sample pulls it in. Nothing else narrows it: more planning does not.

**It is asymmetric, because craft overruns.** A project that is going well finishes a little
early; a project that is going badly finishes very late — frogged rows, a yarn substitution
that changes gauge, a fortnight nobody touched it. A symmetric band would be a *third* wrong
claim dressed as rigour.

**Impossible requires the optimistic bound to have passed.** If the fastest plausible maker
could still finish, the honest verdict is high risk with insufficient runway, not impossible.
The distinction decides whether a season gets abandoned or attempted carefully, and abandoning
a season on an assumption is the more expensive mistake — it cannot be discovered later, since
nothing is built to find out with.
"""
from __future__ import annotations

from dataclasses import dataclass

# How wide the interval is with no calibration at all, as multipliers on the point estimate.
# Asymmetric: the low end is the maker who has the time and the skill the pattern assumes; the
# high end is frogged rows, a gauge surprise and a fortnight nobody touched it.
UNCALIBRATED_LOW = 0.55
UNCALIBRATED_HIGH = 2.20

# The narrowest the interval may ever get, however many samples exist. Two different people
# making the same object differ by more than this, so a band tighter than it would be claiming
# to know the maker rather than the pattern.
FLOOR_LOW = 0.80
FLOOR_HIGH = 1.35

# Samples at which the interval reaches its floor. Deliberately not small: three testers tell
# you about three people.
SAMPLES_FOR_FULL_WEIGHT = 12

COMFORTABLE = "comfortable"
TIGHT = "tight"
HIGH_RISK = "high_risk"
INFEASIBLE = "infeasible"

VERDICTS: tuple[str, ...] = (COMFORTABLE, TIGHT, HIGH_RISK, INFEASIBLE)

VERDICT_MEANING: dict[str, str] = {
    COMFORTABLE: "even a slow maker finishes with room to spare",
    TIGHT: "the typical maker finishes; a slow one does not",
    HIGH_RISK: ("only a fast maker finishes, and the runway is insufficient under current "
                "evidence"),
    INFEASIBLE: "even the fastest plausible maker cannot finish in time",
}


@dataclass(frozen=True)
class MakeTime:
    """An estimate with its uncertainty, and where the uncertainty came from."""

    point_hours: float
    low_hours: float
    high_hours: float
    samples: int
    calibrated: bool

    @property
    def spread(self) -> float:
        return self.high_hours - self.low_hours

    def to_dict(self) -> dict:
        return {
            "point_hours": round(self.point_hours, 1),
            "low_hours": round(self.low_hours, 1),
            "high_hours": round(self.high_hours, 1),
            "samples": self.samples,
            "calibrated": self.calibrated,
            "basis": ("narrowed by recorded physical samples" if self.calibrated else
                      "uncalibrated: no maker has been timed, so the interval is wide on "
                      "purpose and only samples narrow it"),
        }


def interval(point_hours: float, *, samples: int = 0) -> MakeTime:
    """Widen a point estimate into the interval the evidence actually supports.

    Interpolates from the uncalibrated band toward the floor as samples accumulate. The floor
    is not zero width: two people making the same object differ, and a band tighter than that
    would be claiming to know the maker rather than the pattern.
    """
    if point_hours < 0:
        raise ValueError("make hours cannot be negative")
    weight = min(1.0, max(0, samples) / SAMPLES_FOR_FULL_WEIGHT)
    low = UNCALIBRATED_LOW + (FLOOR_LOW - UNCALIBRATED_LOW) * weight
    high = UNCALIBRATED_HIGH + (FLOOR_HIGH - UNCALIBRATED_HIGH) * weight
    return MakeTime(point_hours=point_hours,
                    low_hours=point_hours * low,
                    high_hours=point_hours * high,
                    samples=max(0, samples),
                    calibrated=samples > 0)


def sample_count(db) -> int:
    """How many physical tests have actually been completed. Rows, not intentions."""
    from sqlalchemy import func, select

    from ..core.models import PhysicalTest

    with db.session() as s:
        return int(s.scalar(select(func.count()).select_from(PhysicalTest).where(
            PhysicalTest.passed == True)) or 0)  # noqa: E712


def feasibility(*, days_available: int, days_needed_point: int,
                days_needed_low: int, days_needed_high: int) -> dict:
    """Grade a window against the interval rather than against the point estimate.

    `infeasible` is reserved for the case where the *optimistic* bound has passed. If the
    fastest plausible maker could still finish, the honest verdict is high risk with
    insufficient runway — and the difference decides whether a season is abandoned or
    attempted carefully. Abandoning one on an assumption is the more expensive mistake,
    because nothing then gets built to find out with.
    """
    if days_available >= days_needed_high:
        verdict = COMFORTABLE
    elif days_available >= days_needed_point:
        verdict = TIGHT
    elif days_available >= days_needed_low:
        verdict = HIGH_RISK
    else:
        verdict = INFEASIBLE

    return {
        "verdict": verdict,
        "meaning": VERDICT_MEANING[verdict],
        "days_available": days_available,
        "days_needed": {"optimistic": days_needed_low, "typical": days_needed_point,
                        "pessimistic": days_needed_high},
        "shortfall_against_optimistic": max(0, days_needed_low - days_available),
        "blocks": verdict == INFEASIBLE,
        "note": ("Impossible requires the optimistic bound to have passed. A point estimate "
                 "cannot establish impossibility -- the arithmetic is exact and its inputs "
                 "are guesses -- and abandoning a season on an assumption cannot be "
                 "discovered later, because nothing gets built to find out with."),
    }
