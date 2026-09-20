"""Configurations compete on a fixed task set, and cost counts as an outcome.

Requirements 95 and 96. Every material prompt, model, tool and decision policy is versioned
with why it changed and what it cost, and challengers run against incumbents on controlled
tasks. Promotion requires beating the incumbent *without violating a gate*.

Three failures this is shaped around, and the first is the one that makes leagues useless.

**A challenger that brings its own tasks wins every time.** The natural implementation lets
each configuration be evaluated on the cases its author thought were important, and the author
of a new prompt has necessarily been thinking about the cases it handles well. So the task set
is fixed and shared, a challenger may not be promoted on a task it introduced, and adding a
task is a separate act that applies to everybody retrospectively.

**Cost is an outcome, not a footnote.** A configuration that is three points better and five
times dearer is not better; it is a different trade, and the league that reports only quality
will take it every time and discover the bill at the end of the month. Reliability is the
third axis for the same reason — a configuration that wins when it answers and fails twice as
often has not won.

**A registry that records the change and not the reason answers the wrong question.** "What is
running" is easy and rarely asked. "Should this still be running" is the question somebody has
six months later, usually while something is wrong, and it needs the why, the tests, the cost
and the measured outcome that justified the switch.

Requirement 180 adds four things to that, each of which the original was quietly missing.

**A fixed shared set is overfitted by the league itself.** Refusing a challenger's own tasks
stops one author gaming one comparison, and it does nothing about the slower version: a
hundred challengers evaluated against the same forty tasks will, over a year, be selected for
those forty tasks, and nobody ever brought a task of their own. So a holdout is carried
alongside, its members are never used to tune anything, and a challenger that wins the shared
set while losing the holdout is refused with that named as the reason. A promotion decided
only on the shared set is now reported as `tuned_set_only`.

**Latency is the fourth axis.** The requirement names quality, cost, latency and reliability,
and the original had three. A configuration that is better and four times slower is a
different trade in exactly the way an expensive one is -- and worse, it is the trade that
looks free, because latency is nobody's line item until a cadence starts missing its window.

**A margin is not a significance test.** `QUALITY_MARGIN` on four tasks is a coin. The bar now
scales with the size of the set it was measured on, so a small set has to show a large
difference, which is the honest shape: a league that promotes on noise churns, and churn is
indistinguishable from progress in every report that counts promotions.

**Rollback is a recorded target, not a hope.** Promotion retires the incumbent; it did not
record what to go back to. `rollback()` restores the named previous version and says why,
because the moment rollback is needed is the moment nobody can reconstruct which version was
running last Tuesday.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from . import governance

KINDS: tuple[str, ...] = ("prompt", "model", "tool", "policy")

# The axes a configuration is judged on. All three, always: a league reporting one of them
# picks the trade nobody agreed to.
AXES: dict[str, tuple[bool, str]] = {
    "quality": (True, "task outcome on the shared set, higher is better"),
    "cost_cad": (False, "spend per call, lower is better"),
    "reliability": (True, "share of attempts that produced a usable answer"),
    "latency_s": (False, "seconds per call, lower is better (#180)"),
}

# How much better a challenger must be on quality to justify promotion at equal cost. Small
# improvements on a shared task set are noise, and a league that promotes on noise churns.
QUALITY_MARGIN = 0.03

# A challenger may cost this much more per call only if quality improves by more than the
# margin again. Beyond it, the trade is a decision rather than an evaluation.
COST_TOLERANCE = 1.25

# The same tolerance for time (#180). Latency is the axis that looks free, because it is
# nobody's line item until a cadence starts missing its window and the miss is blamed on
# load. A configuration that is better and four times slower is a trade, not a win.
LATENCY_TOLERANCE = 1.25

# How large a task set has to be before `QUALITY_MARGIN` is the whole bar. Below it the bar
# is scaled up, because a 0.04 gain on four tasks is a coin and a league that promotes on
# coins churns -- and churn is indistinguishable from progress in any report counting
# promotions rather than measuring capability.
SIGNIFICANT_TASKS = 20

# How far the challenger may fall behind on the holdout while still counting as a win there.
# Not zero: the holdout is small by construction and demanding it never dips would refuse
# every real improvement on noise.
HOLDOUT_SLIP = 0.02


class LeagueRefused(Exception):
    """A challenger judged on its own tasks, a promotion through a gate, or a bare change."""


def digest_of(payload: str) -> str:
    return hashlib.sha256((payload or "").encode("utf-8")).hexdigest()


def register(db, *, kind: str, key: str, payload: str, why_changed: str,
             tests_run: tuple[str, ...] = (), cost_per_call_cad: float = 0.0,
             affected_departments: tuple[str, ...] = (),
             incumbent: bool = False) -> dict:
    """Record a configuration version with the reason it exists (#96)."""
    from sqlalchemy import select

    from ..core.models import ConfigVersion

    if kind not in KINDS:
        raise LeagueRefused(f"{kind!r} is not a configuration kind: {list(KINDS)}")
    if len(why_changed.split()) < 6:
        raise LeagueRefused(
            f"{key}: a registry that records the change and not the reason answers 'what is "
            f"running' and never 'should it still be'. The second is the question somebody "
            f"has six months later, usually while something is wrong")
    if not affected_departments:
        raise LeagueRefused(
            f"{key}: name the departments this touches, or a regression here is discovered "
            f"by whichever one notices first")

    digest = digest_of(payload)
    with db.session() as s:
        prior = list(s.scalars(select(ConfigVersion).where(
            ConfigVersion.kind == kind, ConfigVersion.key == key).order_by(
                ConfigVersion.version)))
        if any(p.digest == digest for p in prior):
            existing = next(p for p in prior if p.digest == digest)
            return {"id": existing.id, "version": existing.version, "unchanged": True,
                    "note": "identical payload already registered; no new version created"}
        version = (prior[-1].version + 1) if prior else 1
        if incumbent:
            for p in prior:
                p.incumbent = False
        row = ConfigVersion(
            kind=kind, key=key, version=version, digest=digest,
            why_changed=why_changed.strip(), tests_run=list(tests_run),
            cost_per_call_cad=float(cost_per_call_cad),
            affected_departments=list(affected_departments), incumbent=incumbent)
        s.add(row)
        s.flush()
        return {"id": row.id, "version": version, "unchanged": False,
                "incumbent": incumbent}


# ---------------------------------------------------------------------------
# The league (#95)


@dataclass(frozen=True)
class Result:
    """One configuration's showing on the shared task set, and on the holdout if it ran one.

    `latency_s` and the holdout fields carry defaults so that a caller written before #180
    still works and is simply reported as having measured neither -- which is true, and is
    better than a zero that reads as instantaneous and a holdout that reads as passed.
    """

    config_id: int
    tasks: tuple[str, ...]
    quality: float
    cost_cad: float
    reliability: float
    latency_s: float | None = None
    holdout_tasks: tuple[str, ...] = ()
    holdout_quality: float | None = None

    @property
    def ran_holdout(self) -> bool:
        return bool(self.holdout_tasks) and self.holdout_quality is not None

    def to_dict(self) -> dict:
        return {"config_id": self.config_id, "tasks": list(self.tasks),
                "quality": round(self.quality, 4), "cost_cad": round(self.cost_cad, 6),
                "reliability": round(self.reliability, 4),
                "latency_s": (None if self.latency_s is None
                              else round(self.latency_s, 4)),
                "holdout_tasks": list(self.holdout_tasks),
                "holdout_quality": (None if self.holdout_quality is None
                                    else round(self.holdout_quality, 4))}


def required_margin(task_count: int) -> float:
    """The quality gain a challenger needs, scaled by how much was measured (#180).

    A fixed margin treats four tasks and four hundred as the same evidence. They are not: on
    four, `QUALITY_MARGIN` is within the noise of which four, and a league promoting on that
    churns while reporting progress. The scaling is deliberately crude -- this is not a t-test
    and does not pretend to be one; it is a bar that gets harder as the sample gets smaller,
    which is the direction the arithmetic has to go.
    """
    if task_count <= 0:
        return float("inf")
    if task_count >= SIGNIFICANT_TASKS:
        return QUALITY_MARGIN
    return QUALITY_MARGIN * (SIGNIFICANT_TASKS / task_count) ** 0.5


def compare(incumbent: Result, challenger: Result, *, shared_tasks: tuple[str, ...],
            touches: tuple[str, ...] = (), hypothesis: str = "") -> dict:
    """Should the challenger replace the incumbent? (#95)

    Refuses first on the task set, because that is the failure that makes every other check
    decorative: a challenger evaluated on cases its author was thinking about wins whatever
    the thresholds are.
    """
    introduced = set(challenger.tasks) - set(shared_tasks)
    if introduced:
        raise LeagueRefused(
            f"the challenger was judged on {sorted(introduced)}, which are not in the shared "
            f"set. The author of a new configuration has necessarily been thinking about the "
            f"cases it handles well, so a challenger that brings its own tasks wins every "
            f"time (#95)")
    missing = set(shared_tasks) - set(challenger.tasks)
    if missing:
        return {"promote": False, "reason": "incomplete",
                "why": (f"the challenger did not run {sorted(missing)}. A configuration that "
                        f"skipped the hard cases has not beaten anything")}

    # A promotion is a change to how the company works, so it passes the same boundary any
    # other self-improvement does.
    if hypothesis:
        boundary = governance.check(hypothesis, touches=touches)
        if not boundary.ok:
            raise LeagueRefused(
                f"promotion refused by the improvement boundary: {boundary.reason}")

    quality_gain = challenger.quality - incumbent.quality
    cost_ratio = (challenger.cost_cad / incumbent.cost_cad
                  if incumbent.cost_cad > 0 else
                  (float("inf") if challenger.cost_cad > 0 else 1.0))
    reliability_drop = incumbent.reliability - challenger.reliability
    margin = required_margin(len(shared_tasks))

    reasons = []
    if quality_gain <= margin:
        reasons.append(
            f"quality gain {quality_gain:+.3f} is within the {margin:.3f} margin for "
            f"{len(shared_tasks)} tasks; promoting on noise is how a league churns")
    if reliability_drop > 0:
        reasons.append(
            f"reliability fell {reliability_drop:.3f}: a configuration that wins when it "
            f"answers and fails more often has not won")
    if cost_ratio > COST_TOLERANCE:
        # The bar scales with the ratio rather than sitting at one threshold: a flat bar
        # treats 1.3x and 5x as the same trade, and they are not. Doubling the spend is
        # allowed to buy a real improvement; quintupling it has to buy a large one.
        required = margin * 2 * (cost_ratio / COST_TOLERANCE)
        if quality_gain <= required:
            reasons.append(
                f"costs {cost_ratio:.2f}x the incumbent for a {quality_gain:+.3f} gain, "
                f"where {required:.3f} would be needed at that ratio. That is a different "
                f"trade rather than an improvement, and a league reporting only quality "
                f"takes it every time and finds the bill at the end of the month")

    # Latency, the axis that looks free (#180). Same shape as cost, because it is the same
    # kind of mistake: a win that is four times slower has spent something nobody budgeted.
    latency_ratio = None
    if incumbent.latency_s is not None and challenger.latency_s is not None:
        latency_ratio = (challenger.latency_s / incumbent.latency_s
                         if incumbent.latency_s > 0 else
                         (float("inf") if challenger.latency_s > 0 else 1.0))
        if latency_ratio > LATENCY_TOLERANCE:
            required = margin * 2 * (latency_ratio / LATENCY_TOLERANCE)
            if quality_gain <= required:
                reasons.append(
                    f"takes {latency_ratio:.2f}x the incumbent's time for a "
                    f"{quality_gain:+.3f} gain, where {required:.3f} would be needed at that "
                    f"ratio. Latency is nobody's line item until a cadence misses its window")

    # The holdout (#180). A fixed shared set is overfitted by the league rather than by any
    # one author: a hundred challengers judged on the same forty tasks are selected for those
    # forty. Winning the tuned set and losing the untuned one is the signature of that, and
    # it is the one result a shared-set-only comparison cannot tell from a real improvement.
    holdout = "not_run"
    if challenger.ran_holdout and incumbent.ran_holdout:
        overlap = sorted(set(challenger.holdout_tasks) & set(shared_tasks))
        if overlap:
            raise LeagueRefused(
                f"holdout tasks {overlap} are also in the shared set, so they have been "
                f"tuned against and are not a holdout. A holdout that leaks is worse than "
                f"none: it is the same evidence twice, reported as two")
        holdout_gain = challenger.holdout_quality - incumbent.holdout_quality
        if holdout_gain < -HOLDOUT_SLIP:
            holdout = "lost"
            reasons.append(
                f"won the shared set by {quality_gain:+.3f} and lost the holdout by "
                f"{holdout_gain:+.3f}. That is what fitting the task set looks like from "
                f"outside, and it is the reading the shared set alone cannot produce")
        else:
            holdout = "held"

    return {
        "promote": not reasons,
        "reason": ("beats the incumbent on every measured axis" if not reasons else "held"),
        "blockers": reasons,
        "quality_gain": round(quality_gain, 4),
        "required_margin": round(margin, 4),
        "tasks_compared": len(shared_tasks),
        "cost_ratio": round(cost_ratio, 3) if cost_ratio != float("inf") else None,
        "latency_ratio": (None if latency_ratio is None else
                          (round(latency_ratio, 3) if latency_ratio != float("inf") else None)),
        "reliability_delta": round(-reliability_drop, 4),
        "holdout": holdout,
        "evidence": ("tuned_set_only" if holdout == "not_run" else "tuned_set_and_holdout"),
        "unmeasured_axes": sorted(
            ([] if challenger.latency_s is not None and incumbent.latency_s is not None
             else ["latency_s"])),
        "incumbent": incumbent.to_dict(),
        "challenger": challenger.to_dict(),
        "axes": {k: v[1] for k, v in AXES.items()},
    }


def promote(db, config_id: int, *, outcome: dict, evidence_ref: str) -> dict:
    """Make a challenger the incumbent, recording what it was measured to do."""
    from sqlalchemy import select

    from ..core.models import ConfigVersion

    if not evidence_ref.strip():
        raise LeagueRefused("a promotion names the run that justified it")
    with db.session() as s:
        row = s.get(ConfigVersion, config_id)
        if row is None:
            raise LeagueRefused(f"no configuration version {config_id}")
        for other in s.scalars(select(ConfigVersion).where(
                ConfigVersion.kind == row.kind, ConfigVersion.key == row.key,
                ConfigVersion.incumbent == True)):  # noqa: E712
            other.incumbent = False
            other.retired_at = datetime.now(timezone.utc)
        row.incumbent = True
        row.measured_outcome = {**dict(outcome), "evidence_ref": evidence_ref.strip()}
        return {"config_id": config_id, "kind": row.kind, "key": row.key,
                "version": row.version, "incumbent": True}


def rollback(db, *, kind: str, key: str, to_config_id: int, why: str) -> dict:
    """Put a previous version back, and record why (#180).

    Promotion already retires the incumbent, which is not the same as being able to undo it:
    the moment a rollback is needed is the moment nobody can reconstruct which version was
    running last Tuesday, and "retired_at is set on four of them" is not an answer. So the
    target is named, it has to be a real version of the same configuration, and the reason is
    required -- a rollback with no reason is indistinguishable from a second promotion, and
    six months later that is exactly how it reads.
    """
    from sqlalchemy import select

    from ..core.models import ConfigVersion

    if not why.strip():
        raise LeagueRefused(
            "a rollback names why it happened. Without it the registry shows a version "
            "change and nothing about whether the thing being rolled back was wrong, which "
            "is the only question anybody asks of this row afterwards")
    with db.session() as s:
        target = s.get(ConfigVersion, to_config_id)
        if target is None:
            raise LeagueRefused(f"no configuration version {to_config_id} to roll back to")
        if target.kind != kind or target.key != key:
            raise LeagueRefused(
                f"version {to_config_id} is {target.kind}/{target.key}, not {kind}/{key}. A "
                f"rollback that changes which configuration is running is not a rollback")
        if target.incumbent:
            return {"rolled_back": False, "config_id": to_config_id,
                    "why": "that version is already the incumbent"}

        rolled_from = None
        for other in s.scalars(select(ConfigVersion).where(
                ConfigVersion.kind == kind, ConfigVersion.key == key,
                ConfigVersion.incumbent == True)):  # noqa: E712
            rolled_from = other.id
            other.incumbent = False
            other.retired_at = datetime.now(timezone.utc)
        target.incumbent = True
        target.retired_at = None
        outcome = dict(target.measured_outcome or {})
        outcome["rollback"] = {"from_config_id": rolled_from, "why": why.strip(),
                               "at": datetime.now(timezone.utc).isoformat()}
        target.measured_outcome = outcome
        return {"rolled_back": True, "kind": kind, "key": key,
                "config_id": to_config_id, "version": target.version,
                "from_config_id": rolled_from, "why": why.strip()}


def rollback_target(db, *, kind: str, key: str) -> dict:
    """The version a rollback would restore, answered before it is needed rather than after."""
    from sqlalchemy import select

    from ..core.models import ConfigVersion

    with db.session() as s:
        rows = list(s.scalars(select(ConfigVersion).where(
            ConfigVersion.kind == kind, ConfigVersion.key == key).order_by(
                ConfigVersion.id.desc())))
        current = next((r for r in rows if r.incumbent), None)
        previous = next((r for r in rows
                         if not r.incumbent and r.retired_at is not None), None)
        return {
            "kind": kind, "key": key,
            "incumbent": None if current is None else
                         {"config_id": current.id, "version": current.version},
            "rollback_to": None if previous is None else
                           {"config_id": previous.id, "version": previous.version},
            "available": previous is not None,
            "why": ("the most recently retired version of this configuration"
                    if previous is not None else
                    "nothing has been retired, so there is nothing to go back to. A first "
                    "version has no rollback, and saying so is better than implying one"),
        }


def standings(db, *, kind: str = "", key: str = "") -> dict:
    """What is running, why, and what it was measured to do."""
    from sqlalchemy import select

    from ..core.models import ConfigVersion

    with db.session() as s:
        query = select(ConfigVersion)
        if kind:
            query = query.where(ConfigVersion.kind == kind)
        if key:
            query = query.where(ConfigVersion.key == key)
        rows = [{"id": r.id, "kind": r.kind, "key": r.key, "version": r.version,
                 "incumbent": r.incumbent, "why_changed": r.why_changed,
                 "tests_run": list(r.tests_run or []),
                 "cost_per_call_cad": r.cost_per_call_cad,
                 "affected_departments": list(r.affected_departments or []),
                 "measured_outcome": r.measured_outcome}
                for r in s.scalars(query)]

    unmeasured = [r for r in rows if r["incumbent"] and not r["measured_outcome"]]
    return {
        "configurations": len(rows),
        "incumbents": [r for r in rows if r["incumbent"]],
        "retired": [r for r in rows if not r["incumbent"]],
        "incumbents_with_no_measured_outcome": [r["key"] for r in unmeasured],
        "all": rows,
        "note": (f"{len(unmeasured)} incumbent configuration(s) have never been measured "
                 f"against anything. They are running because they were first, which is the "
                 f"commonest reason anything runs (#96)."
                 if unmeasured else "every incumbent carries a measured outcome"),
    }
