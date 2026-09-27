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
            gate_open: bool | None = None, launch: dict | None = None) -> dict:
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
            confounding = None
            if launch is not None:
                # Thresholds never move; what the launch variables did since registration is
                # appended as the confounder log (#241).
                confounding = log_confounders(row, launch)
            return {"key": row.key, "created": False, "state": row.state,
                    "killed_reason": row.killed_reason, "confounding": confounding}
        fields = _to_row_fields(experiment, product_slug)
        if launch is not None:
            fields["detail"] = {**fields["detail"], **launch_detail(experiment, launch)}
        row = RegisteredExperiment(key=experiment.key, state=state, killed_reason=kill,
                                   **fields)
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
    record_ = launch_record(db, product, price_cad=price_cad, today=today)
    results = [persist(db, e, product_slug=product, gate_open=surfaces_open, launch=record_)
               for e in pack]
    confounded = [r["key"] for r in results
                  if (r.get("confounding") or {}).get("confounded")]
    return {"product": product, "experiments": results,
            "launch_record": record_, "confounded": confounded,
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


# ---------------------------------------------------------------------------
# The runtime conclusion step (#265, #266). Registration was reachable; nothing ever fed a
# result back, estimated a value, or concluded. `conclude_all` is what the daily
# `growth.conclude` job runs. With no data it concludes nothing and says so per experiment.

QUICK_MAX_DAYS = 28
EV_WINDOW_DAYS = 90
UNMEASURED = "UNMEASURED"


def _aware(value):
    from datetime import timezone

    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def observe_metric(db, row) -> dict:
    """The pre-registered metric, read from the rows that measure it, or UNMEASURED.

    Only rows dated after the registration count: data from before a test started is not a
    result of the test.
    """
    from sqlalchemy import select

    from ..core.models import ListingOutcome, Order
    from ..scale.runrate import orders_source_live

    since = _aware(row.created_at).date().isoformat() if row.created_at else ""
    slug = row.product_slug
    with db.session() as s:
        outcomes = [o for o in s.scalars(select(ListingOutcome).where(
            ListingOutcome.product_slug == slug)) if (o.period_start or "") >= since]
        orders = [o for o in s.scalars(select(Order).where(Order.product_slug == slug))
                  if _aware(o.at) is not None
                  and _aware(o.at).date().isoformat() >= since]
        attached = [o for o in s.scalars(select(Order).where(Order.cross_sell_of == slug))
                    if _aware(o.at) is not None
                    and _aware(o.at).date().isoformat() >= since]

    metric = row.metric
    if metric == "listing_click_through_rate":
        impressions = sum(int(o.impressions or 0) for o in outcomes)
        if not outcomes or not impressions:
            return {"observed": None, "sample": 0, "why": "no recorded impressions"}
        visits = sum(int(o.visits or 0) for o in outcomes)
        return {"observed": round(visits / impressions, 5), "sample": impressions,
                "source": "listing_outcomes"}
    if metric == "conversion_rate":
        counted = [o for o in outcomes if o.orders is not None]
        visits = sum(int(o.visits or 0) for o in counted)
        if not counted or not visits:
            return {"observed": None, "sample": 0,
                    "why": "no recorded visits with a measured order count"}
        return {"observed": round(sum(int(o.orders) for o in counted) / visits, 5),
                "sample": visits, "source": "listing_outcomes"}
    if metric == "bundle_attach_rate":
        if not orders_source_live(db)["live"] or not orders:
            return {"observed": None, "sample": 0, "why": "no recorded orders for the product"}
        return {"observed": round(len(attached) / len(orders), 5), "sample": len(orders),
                "source": "orders.cross_sell_of"}
    return {"observed": None, "sample": 0,
            "why": f"no source records {metric!r} yet; it is UNMEASURED, not zero"}


def control_present(db, row) -> dict:
    """Whether the design's control actually exists in the data (#266).

    A holdout design with no organic cohort is a pre/post in disguise, and it may not make
    a causal claim however it was registered.
    """
    from sqlalchemy import select

    from ..commerce.elasticity import holdout_from_db
    from ..core.models import ListingOutcome

    if row.design == HOLDOUT:
        got = holdout_from_db(db, row.product_slug)
        return {"present": bool(got["separable"]), "via": "cohorts",
                "why": got.get("reason", "organic and promoted arms both recorded")}
    if row.design == STAGGERED:
        with db.session() as s:
            arms = {o.hero_style or o.version for o in s.scalars(select(ListingOutcome).where(
                ListingOutcome.test_key == row.key))}
        return {"present": len(arms) >= 2, "via": "listing_outcomes.test_key",
                "why": f"{len(arms)} rollout arm(s) recorded under this test key"}
    return {"present": False, "via": row.design,
            "why": f"a {row.design} design has no control by construction"}


def estimate_expected_value(db, row, *, today: date | None = None) -> float | None:
    """What the decision is worth, from measured contribution, or None (#265).

    The stake is the product's contribution over the trailing ninety days, scaled by how far
    apart the pre-registered success and failure lines sit: a test whose two outcomes are
    close together decides little. With no recorded orders there is no contribution to put
    at stake, and the value stays None -- UNMEASURED, never a guessed number.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from ..core.models import Order
    from ..scale.runrate import orders_source_live

    if not orders_source_live(db)["live"]:
        return None
    now = datetime.now(timezone.utc) if today is None else datetime(
        today.year, today.month, today.day, tzinfo=timezone.utc)
    since = now - timedelta(days=EV_WINDOW_DAYS)
    with db.session() as s:
        got = [o for o in s.scalars(select(Order).where(Order.product_slug == row.product_slug))
               if _aware(o.at) is not None and _aware(o.at) >= since and not o.refunded]
    if not got:
        return None
    stake = sum(float(o.contribution_cad or 0.0) for o in got)
    top = max(abs(row.success_threshold), abs(row.failure_threshold))
    gap = abs(row.success_threshold - row.failure_threshold) / top if top else 0.0
    return round(max(0.0, stake) * gap, 2)


def balance(db) -> dict:
    """Quick low-cost tests against strategic longer ones, among live experiments (#265)."""
    from sqlalchemy import select

    from ..core.models import RegisteredExperiment

    quick, long_ = [], []
    with db.session() as s:
        for r in s.scalars(select(RegisteredExperiment)):
            if r.state in (KILLED, CONCLUDED, ABANDONED):
                continue
            created = _aware(r.created_at).date() if r.created_at else date.today()
            days = (date.fromisoformat(r.stop_on) - created).days if r.stop_on else 0
            (quick if days <= QUICK_MAX_DAYS else long_).append(
                {"key": r.key, "days": days, "cost_cad": r.cost_cad, "state": r.state})
    runnable_long = [x for x in long_ if x["state"] != GATED]
    return {
        "quick": len(quick), "long": len(long_),
        "long_runnable": len(runnable_long),
        "balanced": bool(quick) and bool(runnable_long),
        "quick_max_days": QUICK_MAX_DAYS,
        "note": ("both quick and strategic experiments are running" if quick and runnable_long
                 else "no strategic (longer) experiment can run: every one is gated on a "
                      "surface this company does not have yet" if quick and long_
                 else "no strategic experiment is registered" if quick
                 else "no quick experiment is registered"),
        "long_detail": long_[:20],
    }


def conclude_all(db, *, today: date | None = None) -> dict:
    """Estimate values, feed results in, and conclude what the pre-registration allows.

    Per registered or running experiment: re-estimate the expected value from measured
    contribution (killing it if its cost now exceeds that value), read the metric, and when
    there is a reading pass it through `record_persisted`, which concludes only at the
    pre-registered sample. The claim is written with the incrementality discipline: a
    success without a control present in the data is an association, never a cause. With no
    data nothing is concluded.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from ..core.models import RegisteredExperiment

    with db.session() as s:
        keys = [r.key for r in s.scalars(select(RegisteredExperiment).where(
            RegisteredExperiment.state.in_([REGISTERED, RUNNING])))]

    results = []
    for key in keys:
        with db.session() as s:
            row = s.scalar(select(RegisteredExperiment).where(RegisteredExperiment.key == key))
        # Everything is read before anything is written, so no read runs inside a write.
        ev = estimate_expected_value(db, row, today=today)
        reading = observe_metric(db, row)
        control = control_present(db, row)
        kill = (f"costs CA${row.cost_cad:.2f} against an expected value of CA${ev:.2f}"
                if ev is not None and row.cost_cad > ev else "")
        with db.session() as s:
            fresh = s.scalar(select(RegisteredExperiment).where(RegisteredExperiment.key == key))
            if ev != fresh.expected_value_cad:
                fresh.expected_value_cad = ev
                fresh.updated_at = datetime.now(timezone.utc)
            if kill:
                fresh.state = KILLED
                fresh.killed_reason = kill
        if kill:
            results.append({"key": key, "state": KILLED, "expected_value_cad": ev,
                            "concluded": False, "why": kill})
            continue
        if reading["observed"] is None:
            results.append({"key": key, "state": row.state, "concluded": False,
                            "expected_value_cad": ev if ev is not None else UNMEASURED,
                            "observed": UNMEASURED, "why": reading["why"]})
            continue
        verdict = record_persisted(db, key, reading["observed"], reading["sample"])
        causal = (bool(verdict.get("causal")) and control["present"]
                  and not (row.detail or {}).get("confounded"))
        claim = (verdict.get("claim", "") if causal or not verdict.get("claimable") else
                 f"{row.metric} was {reading['observed']}; "
                 + ((row.detail or {}).get("confounded_why", "") + " (#241)"
                    if (row.detail or {}).get("confounded") else
                    f"the {row.design} design's control is not present in the data "
                    f"({control['why']})")
                 + ", so this is recorded as an association and never as a cause (#266)")
        with db.session() as s:
            fresh = s.scalar(select(RegisteredExperiment).where(RegisteredExperiment.key == key))
            detail = dict(fresh.detail or {})
            detail["last_verdict"] = {**verdict, "causal": causal,
                                      "control": control, "claim": claim,
                                      "source": reading.get("source"),
                                      "at": datetime.now(timezone.utc).isoformat()}
            fresh.detail = detail
            state = fresh.state
        results.append({"key": key, "state": state, "concluded": state == CONCLUDED,
                        "verdict": verdict.get("verdict"), "causal": causal,
                        "expected_value_cad": ev if ev is not None else UNMEASURED,
                        "observed": reading["observed"], "sample": reading["sample"]})

    return {"examined": len(results),
            "concluded": [r["key"] for r in results if r.get("concluded")],
            "killed": [r["key"] for r in results if r["state"] == KILLED],
            "no_data": sum(1 for r in results if r.get("observed") == UNMEASURED),
            "results": results, "balance": balance(db),
            "note": ("nothing was concluded: no experiment has a reading, and with no data "
                     "the discipline concludes nothing" if not any(r.get("concluded")
                                                                  for r in results)
                     else "concluded only at the pre-registered sample; claims without a "
                          "control present in the data are recorded as association")}



# ---------------------------------------------------------------------------
# #241: the launch record -- hero variants, the title/tag strategy and the confounders --
# written with the pack at launch rather than a day after drafting.

# The launch variables. Each is recorded with its value when the pack is registered; any of
# them changing afterwards is a confounder, and more than one changing at once confounds every
# experiment whose metric they move.
LAUNCH_VARIABLES: tuple[str, ...] = ("price_cad", "hero", "title", "tags", "bundle",
                                     "release_hash")

# Which variables each experiment's metric is sensitive to.
SENSITIVE_TO: dict[str, tuple[str, ...]] = {
    "thumbnail": ("hero", "title", "price_cad"),
    "price": ("price_cad", "hero", "title", "tags", "bundle"),
    "search": ("title", "tags"),
    "bundle": ("bundle", "price_cad"),
    "pinterest_content": ("hero", "title"),
}

HERO_CHALLENGER_ROLES: tuple[str, ...] = ("collection", "pattern_preview")
ROTATION_DAYS = 14


def _suffix(key: str) -> str:
    return key.rsplit(":", 1)[-1]


def launch_record(db, product: str, *, price_cad: float | None = None,
                  today: date | None = None) -> dict:
    """What is being launched, read from the stored listing and frames. Nothing invented.

    Hero variants are the product's stored frames that could lead the listing: the `hero`
    frame, then approved frames in a challenger role. Two or more give a staggered rotation
    with dated windows; one gives no rotation, and the thumbnail test says it has no
    challenger; none is UNMEASURED.
    """
    from sqlalchemy import select

    from ..core.models import Listing, ListingAsset
    from ..radar.opportunity import POOL

    today = today or date.today()
    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == product,
                                                 Listing.version != "collection")
                           .order_by(Listing.id.desc()))
        frames = list(s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == product).order_by(ListingAsset.position)))
    usable = [f for f in frames if not (f.blocked_reasons or [])]
    heroes = [f for f in usable if f.role == "hero"] + \
        [f for f in usable if f.role in HERO_CHALLENGER_ROLES and f.approved]
    variants = [{"name": f"{'ABCDEFGH'[i]}:{f.role}:{f.asset_class}@{f.position}",
                 "position": f.position, "role": f.role, "asset_class": f.asset_class,
                 "sha256": f.sha256} for i, f in enumerate(heroes[:4])]
    if len(variants) >= 2:
        plan = {"design": STAGGERED, "rotation_days": ROTATION_DAYS,
                "schedule": [{"variant": v["name"],
                              "from": (today + timedelta(days=i * ROTATION_DAYS)).isoformat(),
                              "to": (today + timedelta(days=(i + 1) * ROTATION_DAYS - 1))
                              .isoformat()} for i, v in enumerate(variants)]}
    elif variants:
        plan = {"design": "single_hero", "schedule": [],
                "why": "one stored hero frame and no approved challenger: there is nothing "
                       "to rotate, so the thumbnail test measures this frame against its "
                       "thresholds and supports no comparison"}
    else:
        plan = {"design": "UNMEASURED", "schedule": [],
                "why": "no stored frame exists for this product yet"}

    seed = next((m for m in POOL if m.slug == product), None)
    bundle = next((m.slug for m in POOL if seed and seed.family and m.is_bundle
                   and m.family == seed.family), None)
    tags = list(listing.tags or []) if listing else []
    values = {
        "price_cad": (float(listing.price_cad) if listing and listing.price_cad
                      else price_cad),
        "hero": variants[0]["sha256"] if variants else None,
        "title": listing.title if listing else None,
        "tags": sorted(tags) if listing else None,
        "bundle": bundle,
        "release_hash": listing.release_hash if listing else None,
    }
    return {
        "recorded_on": today.isoformat(),
        "hero_variants": variants,
        "hero_plan": plan,
        "title_tag_strategy": {
            "title": values["title"], "tags": tags,
            "on_failure": ("rewrite the tags that drew no impressions from target queries and "
                           "retest the title's leading phrase; the rest of the listing is held "
                           "fixed while that runs" if listing else
                           "UNMEASURED: no listing is drafted, so no title or tag set exists"),
        },
        "variables": values,
        "unrecorded": sorted(k for k, v in values.items() if v is None),
    }


def launch_detail(experiment: Experiment, launch: dict) -> dict:
    """The part of the launch record an experiment carries in its registration."""
    out = {"launch": {"recorded_on": launch["recorded_on"],
                      "variables": launch["variables"],
                      "unrecorded": launch["unrecorded"]},
           "confounder_log": [], "confounded": False}
    part = _suffix(experiment.key)
    if part == "thumbnail":
        out["hero_variants"] = launch["hero_variants"]
        out["hero_plan"] = launch["hero_plan"]
    if part == "search":
        out["title_tag_strategy"] = launch["title_tag_strategy"]
    return out


def log_confounders(row, launch: dict) -> dict:
    """Compare today's launch variables with those registered, and log what moved.

    One change is recorded as a confounder of the experiments it touches. More than one at
    once, on variables this experiment is sensitive to, marks it `confounded`: its result may
    still be read, and may never be claimed as caused by any single one of them.
    """
    detail = dict(row.detail or {})
    registered = (detail.get("launch") or {}).get("variables")
    if registered is None:
        # Registered before launch records existed: record the baseline now, flagged late.
        detail["launch"] = {"recorded_on": launch["recorded_on"],
                            "variables": launch["variables"],
                            "unrecorded": launch["unrecorded"], "late": True}
        detail.setdefault("confounder_log", [])
        row.detail = detail
        return {"changed": [], "confounded": bool(detail.get("confounded"))}
    changed = [k for k in LAUNCH_VARIABLES
               if k in launch["variables"] and registered.get(k) != launch["variables"][k]
               and registered.get(k) is not None]
    if not changed:
        return {"changed": [], "confounded": bool(detail.get("confounded"))}
    relevant = [k for k in changed if k in SENSITIVE_TO.get(_suffix(row.key), ())]
    log = list(detail.get("confounder_log") or [])
    log.append({"on": launch["recorded_on"], "changed": changed, "relevant": relevant,
                "from": {k: registered.get(k) for k in changed},
                "to": {k: launch["variables"].get(k) for k in changed}})
    detail["confounder_log"] = log
    if len(relevant) > 1:
        detail["confounded"] = True
        detail["confounded_why"] = (f"{', '.join(relevant)} changed at once; the result cannot "
                                    f"be attributed to any one of them")
    detail["launch"] = {**detail["launch"], "variables": {**registered,
                                                          **launch["variables"]}}
    row.detail = detail
    return {"changed": changed, "relevant": relevant,
            "confounded": bool(detail.get("confounded"))}


def register_at_launch(db, *, product: str, price_cad: float | None = None,
                       today: date | None = None) -> dict:
    """The launch path's call: register the pack with its launch record, at launch (#241).

    The price is the drafted listing's when none is given. With no listing the pack still
    registers, and its launch record says which variables are UNMEASURED.
    """
    from sqlalchemy import select

    from ..core.models import Listing

    if price_cad is None:
        with db.session() as s:
            listing = s.scalar(select(Listing).where(Listing.product_slug == product,
                                                     Listing.version != "collection"))
            price_cad = float(listing.price_cad) if listing else 0.0
    return register_launch(db, product=product, price_cad=price_cad, today=today)
