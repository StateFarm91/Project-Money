"""Pre-registered experiments, and the discipline that makes a result mean something.

Requirements 241, 265, 266, 272. Two rules carry this module, and both exist because the
alternative is a company that learns confidently wrong things.

**A threshold declared after the result is not a threshold (#241).** Every launch ships with a
pre-registered plan: the hypothesis, the metric, the sample it needs, the success and failure
lines, and the date it stops. Deciding afterwards what would have counted as success is how
every experiment succeeds and nothing is ever learned — and it does not feel like cheating,
which is what makes it common.

**Revenue that would have happened anyway is not a result (#266).** Without a holdout or a
staggered rollout, an experiment measures the season, the day of the week and the listing that
was already selling. The design says so in the record rather than in a caveat nobody reads: an
experiment with no control is labelled `not_incremental` and may not be claimed as causal,
however good its numbers look.

**Scaling is gated on more than a good number (#272).** A product that converts well and
generates support tickets is not ready to scale; it is ready to be fixed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

# Designs, ordered by what they can actually support as a claim.
HOLDOUT = "holdout"                 # a control group, untouched
STAGGERED = "staggered_rollout"     # some get it first
PRE_POST = "pre_post"               # same population, before and after
NO_CONTROL = "no_control"           # nothing to compare against

DESIGNS: tuple[str, ...] = (HOLDOUT, STAGGERED, PRE_POST, NO_CONTROL)

# Which designs support a causal claim. Pre/post does not: it cannot separate the change from
# the week it happened in, and seasonality is the largest effect in this business.
CAUSAL_DESIGNS: frozenset[str] = frozenset({HOLDOUT, STAGGERED})

REGISTERED = "registered"
RUNNING = "running"
CONCLUDED = "concluded"
ABANDONED = "abandoned"


class ExperimentRefused(ValueError):
    """A plan that cannot produce a trustworthy answer, or a claim its design cannot carry."""


@dataclass
class Experiment:
    """One pre-registered test. Everything that decides the verdict is fixed before it runs."""

    key: str
    hypothesis: str
    metric: str
    design: str
    success_threshold: float
    failure_threshold: float
    minimum_sample: int
    stop_on: date
    higher_is_better: bool = True
    cost_cad: float = 0.0
    state: str = REGISTERED
    observed: float | None = None
    sample: int = 0
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.design not in DESIGNS:
            raise ExperimentRefused(f"{self.design!r} is not a design: {sorted(DESIGNS)}")
        if len(self.hypothesis.split()) < 6:
            raise ExperimentRefused(
                "a hypothesis states what is expected to change and why; this is a title")
        if self.minimum_sample <= 0:
            raise ExperimentRefused(
                "an experiment with no minimum sample concludes on its first data point, "
                "which is how noise becomes a finding")
        better, worse = self.success_threshold, self.failure_threshold
        if self.higher_is_better and better <= worse:
            raise ExperimentRefused(
                "the success line must sit above the failure line, or every result is both")
        if not self.higher_is_better and better >= worse:
            raise ExperimentRefused(
                "for a metric where lower is better, success must sit below failure")

    @property
    def supports_causal_claim(self) -> bool:
        return self.design in CAUSAL_DESIGNS

    def verdict(self) -> dict:
        """What the numbers say, and what the design permits saying about them."""
        if self.observed is None:
            return {"verdict": "no result yet", "claimable": False}
        if self.sample < self.minimum_sample:
            return {
                "verdict": "undersampled",
                "claimable": False,
                "reason": (f"{self.sample} observations against a pre-registered minimum of "
                           f"{self.minimum_sample}. Stopping early at a good number is the "
                           f"most common way to find an effect that is not there"),
            }

        if self.higher_is_better:
            won = self.observed >= self.success_threshold
            lost = self.observed <= self.failure_threshold
        else:
            won = self.observed <= self.success_threshold
            lost = self.observed >= self.failure_threshold

        outcome = "success" if won else ("failure" if lost else "inconclusive")
        return {
            "verdict": outcome,
            "observed": self.observed,
            "sample": self.sample,
            "claimable": outcome in ("success", "failure"),
            "causal": self.supports_causal_claim,
            "claim": (
                f"{self.metric} moved to {self.observed}, and with a {self.design} design "
                f"this supports a causal claim"
                if self.supports_causal_claim else
                f"{self.metric} was {self.observed}, but a {self.design} design cannot "
                f"separate the change from the season, the weekday or a listing that was "
                f"already moving. Recorded as association, never as cause (#266)"),
        }


def register(experiments: dict[str, Experiment], experiment: Experiment) -> Experiment:
    if experiment.key in experiments:
        raise ExperimentRefused(f"{experiment.key!r} is already registered")
    experiments[experiment.key] = experiment
    return experiment


def record(experiment: Experiment, observed: float, sample: int) -> dict:
    """Attach a result to a plan that already said what would count."""
    if experiment.state == CONCLUDED:
        raise ExperimentRefused(
            f"{experiment.key!r} has concluded. Adding data to a finished experiment until "
            f"it says the right thing is the oldest way to be wrong")
    experiment.observed = observed
    experiment.sample = sample
    verdict = experiment.verdict()
    if verdict["claimable"]:
        experiment.state = CONCLUDED
    else:
        experiment.state = RUNNING
    return verdict


def launch_pack(*, product: str, hypothesis: str, price_cad: float,
                today: date | None = None) -> list[Experiment]:
    """The experiment plan every important launch ships with (#241).

    Four pre-registered tests, because the four things that decide whether a listing works are
    decided by different mechanisms and a single blended metric cannot separate them.
    """
    today = today or date.today()
    stop = today + timedelta(days=28)
    return [
        Experiment(
            key=f"{product}:thumbnail",
            hypothesis=f"the hero frame for {product} earns a click at mobile-grid size",
            metric="listing_click_through_rate", design=STAGGERED,
            success_threshold=0.02, failure_threshold=0.008,
            minimum_sample=1000, stop_on=stop),
        Experiment(
            key=f"{product}:price",
            hypothesis=f"{product} converts at CA${price_cad:.2f} without discounting",
            metric="conversion_rate", design=HOLDOUT,
            success_threshold=0.02, failure_threshold=0.005,
            minimum_sample=500, stop_on=stop),
        Experiment(
            key=f"{product}:search",
            hypothesis=f"the tag set for {product} reaches buyers already searching for it",
            metric="impressions_from_target_queries", design=PRE_POST,
            success_threshold=500, failure_threshold=50,
            minimum_sample=14, stop_on=stop),
        Experiment(
            key=f"{product}:bundle",
            hypothesis=f"{product} attaches to a companion product often enough to pay for "
                       f"the bundle work",
            metric="bundle_attach_rate", design=HOLDOUT,
            success_threshold=0.12, failure_threshold=0.03,
            minimum_sample=200, stop_on=stop),
    ]


# ---------------------------------------------------------------------------
# The scale readiness gate (#272)

SCALE_CONDITIONS: tuple[str, ...] = (
    "product_quality_stable",
    "support_load_acceptable",
    "refunds_acceptable",
    "creative_certified_truthful",
    "contribution_positive_or_bounded",
    "attribution_working",
)


def scale_readiness(conditions: dict[str, bool]) -> dict:
    """Refuse to scale a product whose numbers are good and whose foundations are not.

    A product that converts well and generates support tickets is not ready to scale; it is
    ready to be fixed, and scaling it multiplies the tickets along with the revenue.
    """
    unknown = [k for k in conditions if k not in SCALE_CONDITIONS]
    if unknown:
        raise ExperimentRefused(f"unknown scale conditions: {sorted(unknown)}")

    unmet = [c for c in SCALE_CONDITIONS if not conditions.get(c, False)]
    return {
        "ready": not unmet,
        "required": list(SCALE_CONDITIONS),
        "unmet": unmet,
        "note": ("Every condition holds; scaling is a spend decision rather than a risk one."
                 if not unmet else
                 f"Not ready: {', '.join(unmet)}. Scaling multiplies whatever is already "
                 f"true, including the parts nobody has fixed."),
    }
