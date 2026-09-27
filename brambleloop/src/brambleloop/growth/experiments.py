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
    # #265: every experiment has somebody accountable for it, a value it is expected to be
    # worth, and the decision its result would change. `expected_value_cad` is None when
    # nothing has been measured to estimate it from -- UNMEASURED, never a guessed number.
    owner: str = ""
    expected_value_cad: float | None = None
    decision: str = ""
    on_success: str = ""
    on_failure: str = ""
    # A capability the experiment cannot run without (a `build2.executor` gate key). An
    # experiment whose surface does not exist is defined and parked, not run.
    gated_on: str = ""

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

    def kill_reason(self) -> str:
        """Why this experiment should not run at all, or "" (#265).

        An experiment whose success and failure lead to the same action cannot change a
        decision, so running it buys a number and nothing else. Nor does one whose cost
        exceeds what it is expected to be worth -- when that value has been measured.
        """
        if not self.decision.strip():
            return "names no decision its result could change"
        if not self.on_success.strip() or not self.on_failure.strip():
            return "does not say what happens on success and on failure"
        if self.on_success.strip().lower() == self.on_failure.strip().lower():
            return (f"success and failure both lead to {self.on_success!r}, so the result "
                    f"cannot change a decision")
        if self.expected_value_cad is not None and self.cost_cad > self.expected_value_cad:
            return (f"costs CA${self.cost_cad:.2f} against an expected value of "
                    f"CA${self.expected_value_cad:.2f}")
        return ""

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
            minimum_sample=1000, stop_on=stop, owner="publishing",
            decision="keep or replace the hero frame",
            on_success="keep the hero frame", on_failure="replace the hero frame"),
        Experiment(
            key=f"{product}:price",
            hypothesis=f"{product} converts at CA${price_cad:.2f} without discounting",
            metric="conversion_rate", design=HOLDOUT,
            success_threshold=0.02, failure_threshold=0.005,
            minimum_sample=500, stop_on=stop, owner="pricing",
            decision=f"hold CA${price_cad:.2f} or reposition the price",
            on_success="hold the price", on_failure="reposition the price"),
        Experiment(
            key=f"{product}:search",
            hypothesis=f"the tag set for {product} reaches buyers already searching for it",
            metric="impressions_from_target_queries", design=PRE_POST,
            success_threshold=500, failure_threshold=50,
            minimum_sample=14, stop_on=stop, owner="listing",
            decision="keep or rewrite the tag set",
            on_success="keep the tag set", on_failure="rewrite the tag set"),
        Experiment(
            key=f"{product}:bundle",
            hypothesis=f"{product} attaches to a companion product often enough to pay for "
                       f"the bundle work",
            metric="bundle_attach_rate", design=HOLDOUT,
            success_threshold=0.12, failure_threshold=0.03,
            minimum_sample=200, stop_on=stop, owner="growth",
            decision="build the companion bundle or drop it",
            on_success="build the bundle", on_failure="drop the bundle"),
    ]


# The content surface this company does not have yet. Defined now, so the day a site or a
# Pinterest account exists the test is already pre-registered rather than designed after the
# first good week.
OWNED_SURFACES_GATE = "owned_surfaces"


def content_experiment(*, product: str, today: date | None = None) -> Experiment:
    """The content/Pinterest experiment for one product, gated on an owned surface (#241)."""
    today = today or date.today()
    return Experiment(
        key=f"{product}:pinterest_content",
        hypothesis=(f"pinned project content for {product} sends visits that convert at "
                    f"least as well as marketplace search"),
        metric="visits_from_owned_content", design=STAGGERED,
        success_threshold=100, failure_threshold=10,
        minimum_sample=28, stop_on=today + timedelta(days=56), owner="growth",
        decision="invest in pinned content for this product or stop producing it",
        on_success="keep producing pinned content", on_failure="stop producing pinned content",
        gated_on=OWNED_SURFACES_GATE)


# ---------------------------------------------------------------------------
# Persistence (#241, #265). The dict above is a registry for one process; these rows are the
# one the company keeps.

GATED = "gated"
KILLED = "killed"


def _to_row_fields(e: Experiment, product_slug: str) -> dict:
    return dict(product_slug=product_slug, hypothesis=e.hypothesis, metric=e.metric,
                design=e.design, success_threshold=float(e.success_threshold),
                failure_threshold=float(e.failure_threshold),
                minimum_sample=int(e.minimum_sample), higher_is_better=e.higher_is_better,
                stop_on=e.stop_on.isoformat(), cost_cad=float(e.cost_cad), owner=e.owner,
                expected_value_cad=e.expected_value_cad, decision=e.decision,
                gated_on=e.gated_on,
                detail={"on_success": e.on_success, "on_failure": e.on_failure,
                        "notes": list(e.notes)})


def persist(db, experiment: Experiment, *, product_slug: str = "",
            gate_open: bool | None = None) -> dict:
    """Write a pre-registered experiment, or leave the existing registration alone.

    Registration is write-once: the thresholds are what make the result mean anything, so a
    second call cannot move them. An experiment with no owner is refused; one that cannot
    change a decision is stored as `killed` with its reason rather than run; one whose gate
    is closed is stored as `gated`.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from ..core.models import RegisteredExperiment

    if not experiment.owner.strip():
        raise ExperimentRefused(
            f"{experiment.key}: an experiment with no owner is one nobody reads the result of")
    kill = experiment.kill_reason()
    state = (KILLED if kill else
             GATED if experiment.gated_on and gate_open is not True else REGISTERED)
    with db.session() as s:
        row = s.scalar(select(RegisteredExperiment).where(
            RegisteredExperiment.key == experiment.key))
        if row is not None:
            # A gate opening is the one state change a re-registration may carry.
            if row.state == GATED and state == REGISTERED:
                row.state = REGISTERED
                row.updated_at = datetime.now(timezone.utc)
            return {"key": row.key, "created": False, "state": row.state,
                    "killed_reason": row.killed_reason}
        row = RegisteredExperiment(key=experiment.key, state=state, killed_reason=kill,
                                   **_to_row_fields(experiment, product_slug))
        s.add(row)
    return {"key": experiment.key, "created": True, "state": state, "killed_reason": kill}


def load(db, key: str) -> Experiment:
    from sqlalchemy import select

    from ..core.models import RegisteredExperiment

    with db.session() as s:
        row = s.scalar(select(RegisteredExperiment).where(RegisteredExperiment.key == key))
        if row is None:
            raise ExperimentRefused(f"no registered experiment {key!r}")
        detail = row.detail or {}
        return Experiment(
            key=row.key, hypothesis=row.hypothesis, metric=row.metric, design=row.design,
            success_threshold=row.success_threshold,
            failure_threshold=row.failure_threshold, minimum_sample=row.minimum_sample,
            stop_on=date.fromisoformat(row.stop_on), higher_is_better=row.higher_is_better,
            cost_cad=row.cost_cad, state=row.state, observed=row.observed, sample=row.sample,
            notes=list(detail.get("notes") or []), owner=row.owner,
            expected_value_cad=row.expected_value_cad, decision=row.decision,
            on_success=detail.get("on_success", ""), on_failure=detail.get("on_failure", ""),
            gated_on=row.gated_on)


def record_persisted(db, key: str, observed: float, sample: int) -> dict:
    """`record` against the stored registration, written back. Killed or gated refuse."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from ..core.models import RegisteredExperiment

    experiment = load(db, key)
    if experiment.state in (KILLED, GATED):
        raise ExperimentRefused(
            f"{key!r} is {experiment.state}; a result for an experiment that was not "
            f"allowed to run is a result nobody pre-registered")
    verdict = record(experiment, observed, sample)
    with db.session() as s:
        row = s.scalar(select(RegisteredExperiment).where(RegisteredExperiment.key == key))
        row.observed, row.sample, row.state = observed, sample, experiment.state
        row.updated_at = datetime.now(timezone.utc)
    return verdict


def register_launch(db, *, product: str, price_cad: float, today: date | None = None,
                    env: dict | None = None) -> dict:
    """The launch path's experiment registration: the pack plus the gated content test."""
    try:
        from ..build2.executor import GATES

        gate = next((g for g in GATES if g.key == OWNED_SURFACES_GATE), None)
        surfaces_open = bool(gate.open(db, env)) if gate is not None else False
    except Exception:  # noqa: BLE001 - a gate that cannot be read is a closed gate
        surfaces_open = False
    pack = launch_pack(product=product, hypothesis="", price_cad=price_cad, today=today)
    pack.append(content_experiment(product=product, today=today))
    results = [persist(db, e, product_slug=product, gate_open=surfaces_open) for e in pack]
    return {"product": product, "experiments": results,
            "owned_surfaces_open": surfaces_open,
            "created": sum(1 for r in results if r["created"]),
            "killed": [r["key"] for r in results if r["state"] == KILLED],
            "gated": [r["key"] for r in results if r["state"] == GATED]}


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
