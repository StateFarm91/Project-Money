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


def record_measured_outcome(db, config_id: int, *, outcome: dict, evidence_ref: str) -> dict:
    """Attach what a configuration was measured to do, without changing what is running.

    Promotion records a measured outcome as a side effect of switching; this records one for
    a configuration that is *not* switching -- an incumbent that was first and has now been
    put to a trial, or a challenger whose trial recommended against it. Idempotent on the
    evidence reference: the same trial re-read tomorrow adds nothing, so a standings row
    carries one line per run rather than one per night the run was noticed.
    """
    from ..core.models import ConfigVersion

    ref = evidence_ref.strip()
    if not ref:
        raise LeagueRefused("a measured outcome names the run that measured it")
    with db.session() as s:
        row = s.get(ConfigVersion, config_id)
        if row is None:
            raise LeagueRefused(f"no configuration version {config_id}")
        current = dict(row.measured_outcome or {})
        refs = list(current.get("evidence_refs") or [])
        if ref in refs:
            return {"config_id": config_id, "recorded": False, "evidence_ref": ref,
                    "why": "this run's outcome is already on the row"}
        refs.append(ref)
        row.measured_outcome = {**current, **dict(outcome), "evidence_ref": ref,
                                "evidence_refs": refs}
        return {"config_id": config_id, "recorded": True, "evidence_ref": ref,
                "kind": row.kind, "key": row.key, "version": row.version,
                "incumbent": row.incumbent}


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


# ---------------------------------------------------------------------------
# The league in the runtime (#95, #180)
#
# `compare`, `promote` and `rollback` had no caller: incumbents were registered nightly and no
# challenger was ever created, compared, promoted or rolled back. `cycle` is the cadence's
# pass. Three rules keep it honest.
#
# **A comparison reads recorded runs, never runs a model.** A run is one configuration's
# measured showing on named tasks, recorded with `record_run` under the reference of whatever
# produced it. Producing a run is a spending decision taken elsewhere, and while the model
# provider is closed the challengers registered here wait, saying so, rather than being judged
# on nothing. The incumbent's run defines the fixed shared task set, so a challenger that
# brings its own tasks is refused by `compare` exactly as the library already does.
#
# **Promotion goes through the same authority as every other self-change.** The configuration
# kind names the surface it touches, `improve.tiers` grades that surface, and #190's split
# decides: a pre-authorised tier promotes when `upgrades.may_auto_promote` allows it, anything
# else becomes an owner card and promotes only once the owner's decision is recorded on the
# challenger by `record_owner_decision`, which only the owner's identity satisfies. A
# configuration mirrored from running code (the routing table, the image provider) never
# promotes in the registry at all: flipping the row would make the registry describe a
# configuration the code is not running, so the card asks for the code change and
# `bootstrap` moves the registry when the code has moved.
#
# **Rollback is automatic and names its target.** A configuration the league promoted whose
# next recorded run falls below the incumbent it replaced -- on quality beyond the margin, or
# on reliability at all -- is rolled back to that incumbent with the reason recorded.

RUN_ACTION = "improve.league.run"
COMPARE_ACTION = "improve.league.compared"
LEAGUE = "improve.league"
CARD_PREFIX = "improve.league:"
CHALLENGER_AUTHOR = "prompt_tool_challenger"

# The risk surface each configuration kind touches, in `improve.tiers`' vocabulary.
KIND_SURFACE: dict[str, str] = {"prompt": "prompt", "model": "model_routing", "tool": "tool",
                                "policy": "policy"}


def record_run(db, config_id: int, *, tasks: dict, cost_cad: float, reliability: float,
               run_ref: str, recorded_by: str, latency_s: float | None = None,
               holdout: dict | None = None) -> dict:
    """Record one configuration's measured showing on named tasks. Idempotent on `run_ref`."""
    from sqlalchemy import select

    from ..core.models import AuditLog, ConfigVersion

    ref = (run_ref or "").strip()
    who = governance.normalise_actor(recorded_by)
    if not ref or not who:
        raise LeagueRefused("a run names what produced it and who recorded it")
    if not tasks:
        raise LeagueRefused("a run with no tasks measured nothing")
    scores = {str(k): float(v) for k, v in tasks.items()}
    held = {str(k): float(v) for k, v in (holdout or {}).items()}
    overlap = sorted(set(scores) & set(held))
    if overlap:
        raise LeagueRefused(f"holdout tasks {overlap} are also scored tasks; a holdout that "
                            f"leaks is the same evidence twice")
    if not 0.0 <= float(reliability) <= 1.0 or float(cost_cad) < 0 or (
            latency_s is not None and float(latency_s) < 0):
        raise LeagueRefused("reliability is a share, and cost and latency are not negative")
    with db.session() as s:
        row = s.get(ConfigVersion, config_id)
        if row is None:
            raise LeagueRefused(f"no configuration version {config_id}")
        for prior in s.scalars(select(AuditLog).where(AuditLog.action == RUN_ACTION)):
            if (prior.detail or {}).get("run_ref") == ref and \
                    (prior.detail or {}).get("config_id") == config_id:
                return {"run_id": prior.id, "recorded": False, "run_ref": ref}
        audit = AuditLog(actor=who, action=RUN_ACTION, artifact=f"{row.kind}/{row.key}",
                         detail={"config_id": config_id, "kind": row.kind, "key": row.key,
                                 "version": row.version, "tasks": scores, "holdout": held,
                                 "cost_cad": float(cost_cad),
                                 "reliability": float(reliability),
                                 "latency_s": None if latency_s is None else float(latency_s),
                                 "run_ref": ref})
        s.add(audit)
        s.flush()
        return {"run_id": audit.id, "recorded": True, "run_ref": ref}


def _runs(db) -> dict[int, list[dict]]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    out: dict[int, list[dict]] = {}
    with db.session() as s:
        for a in s.scalars(select(AuditLog).where(AuditLog.action == RUN_ACTION)
                           .order_by(AuditLog.id)):
            d = dict(a.detail or {})
            at = a.at if a.at.tzinfo else a.at.replace(tzinfo=timezone.utc)
            out.setdefault(int(d["config_id"]), []).append({**d, "run_id": a.id, "at": at})
    return out


def result_of(config_id: int, run: dict) -> Result:
    """A recorded run as the `Result` `compare` judges."""
    tasks = dict(run["tasks"])
    held = dict(run.get("holdout") or {})
    return Result(config_id=config_id, tasks=tuple(sorted(tasks)),
                  quality=sum(tasks.values()) / len(tasks),
                  cost_cad=float(run["cost_cad"]), reliability=float(run["reliability"]),
                  latency_s=run.get("latency_s"),
                  holdout_tasks=tuple(sorted(held)),
                  holdout_quality=(sum(held.values()) / len(held)) if held else None)


def record_owner_decision(db, config_id: int, *, approved_by: str, why: str) -> dict:
    """The owner's approval of a challenger's promotion, recorded on the challenger's row."""
    from ..core.models import ConfigVersion

    if governance.normalise_actor(approved_by) != "owner":
        raise LeagueRefused(f"{approved_by!r} is not the owner; this decision is the owner's")
    if len((why or "").split()) < 3:
        raise LeagueRefused("an owner decision says why; this is a label")
    with db.session() as s:
        row = s.get(ConfigVersion, config_id)
        if row is None:
            raise LeagueRefused(f"no configuration version {config_id}")
        row.measured_outcome = {**dict(row.measured_outcome or {}), "owner_approval": {
            "by": "owner", "because": why, "at": datetime.now(timezone.utc).isoformat()}}
    return {"config_id": config_id, "owner_approved": True}


def _code_mirrored(kind: str, key: str) -> bool:
    from . import bootstrap

    return ((kind == bootstrap.ROUTING_KIND and key.startswith(bootstrap.ROUTING_KEY_PREFIX))
            or (kind == bootstrap.IMAGE_KIND and key == bootstrap.IMAGE_KEY))


def _configs(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import ConfigVersion

    with db.session() as s:
        return [{"id": r.id, "kind": r.kind, "key": r.key, "version": r.version,
                 "digest": r.digest, "incumbent": r.incumbent, "why": r.why_changed,
                 "retired": r.retired_at is not None,
                 "outcome": dict(r.measured_outcome or {})}
                for r in s.scalars(select(ConfigVersion).order_by(ConfigVersion.id))]


def _authorise(db, inc: dict, ch: dict, verdict: dict, runs: dict, ref: str, *,
               now: datetime) -> dict:
    """Promote, card or hold a challenger that won, by the tier its kind's surface grades."""
    from . import tiers, upgrades

    surface = KIND_SURFACE.get(ch["kind"], "code")
    tier = tiers.classify((surface,))
    card_key = f"{CARD_PREFIX}{ch['id']}"
    proposal = upgrades.Proposal(
        key=f"config:{ch['id']}", author_role=CHALLENGER_AUTHOR,
        hypothesis=(f"replace {ch['kind']}/{ch['key']} version {inc['version']} with version "
                    f"{ch['version']}, which beat it on the shared task set: {ch['why']}"),
        scope=(surface,), content=ch["digest"], rollback_to=f"config:{inc['id']}")
    fp = proposal.fingerprint
    evidence = [upgrades.Evidence(tiers.BASELINE, runs["incumbent"]["run_ref"], fp),
                upgrades.Evidence(tiers.SANDBOX_RESULT, runs["challenger"]["run_ref"], fp),
                upgrades.Evidence(tiers.ROLLBACK, f"config:{inc['id']}", fp)]
    if verdict.get("holdout") == "held":
        # The holdout is the league's regression evidence: the untuned tasks did not get worse.
        evidence.append(upgrades.Evidence(tiers.REGRESSION_TEST,
                                          f"{runs['challenger']['run_ref']}:holdout", fp))
    owner = (ch["outcome"].get("owner_approval") or {})
    owner_decided = governance.normalise_actor(owner.get("by")) == "owner"
    if owner_decided:
        evidence.append(upgrades.Evidence(tiers.OWNER_APPROVAL, f"owner:{card_key}", fp))
    for item in evidence:
        upgrades.attach(proposal, item, touched=proposal.scope)

    mirrored = _code_mirrored(ch["kind"], ch["key"])
    if not mirrored and (tier.key in upgrades.PRE_AUTHORISED or owner_decided):
        if owner_decided:
            try:
                tiers.check_promotion(db, touches=proposal.scope,
                                      evidence=tuple(e.kind for e in proposal.current_evidence()),
                                      now=now)
                allowed = {"may_auto_promote": True}
            except tiers.TierRefused as exc:
                allowed = {"may_auto_promote": False, "why": str(exc)}
        else:
            allowed = upgrades.may_auto_promote(db, proposal, now=now)
        if not allowed["may_auto_promote"]:
            return {"route": "held", "config_id": ch["id"], "tier": tier.key,
                    "why": allowed.get("why", "")[:300]}
        promote(db, ch["id"], evidence_ref=ref, outcome={
            **ch["outcome"], "league_verdict": {k: verdict.get(k) for k in (
                "quality_gain", "required_margin", "holdout", "evidence", "cost_ratio",
                "reliability_delta")},
            "promoted_by": LEAGUE, "previous_incumbent": inc["id"],
            "promoted_at": now.isoformat(), "tier": tier.key,
            "replaced_quality": verdict["incumbent"]["quality"],
            "replaced_reliability": verdict["incumbent"]["reliability"]})
        tiers.record_promotion(db, tier=tier.key,
                               summary=f"configuration {ch['kind']}/{ch['key']} v{ch['version']}",
                               detail={"config_id": ch["id"], "replaced": inc["id"]})
        upgrades.close_owner_card(db, card_key)
        return {"route": "promoted", "config_id": ch["id"], "tier": tier.key,
                "replaced": inc["id"], "owner_approved": owner_decided}

    try:
        card = upgrades.owner_card(proposal)
    except upgrades.UpgradeRefused as exc:
        return {"route": "held", "config_id": ch["id"], "tier": tier.key,
                "why": str(exc)[:300]}
    if not card.get("queued"):
        return {"route": "held", "config_id": ch["id"], "tier": tier.key,
                "why": card.get("why", "")[:300]}
    action = (f"Decide whether {ch['kind']}/{ch['key']} version {ch['version']} replaces "
              f"version {inc['version']}: it beat it on the shared task set "
              f"(quality {verdict['quality_gain']:+.3f}, holdout {verdict['holdout']}). ")
    action += ("This configuration is defined in code, so approving means changing that code; "
               "the registry follows the code on the next nightly sweep"
               if mirrored else
               f"Approve with improve.league.record_owner_decision({ch['id']}, "
               f"approved_by='owner', why=...), or decline it")
    queued = upgrades.queue_owner_card(db, card_key, card, action=action, minutes=5,
                                       blocks=f"config:{ch['id']}")
    return {"route": "carded", "config_id": ch["id"], "tier": tier.key,
            "code_mirrored": mirrored, **queued}


def cycle(db, *, now: datetime | None = None) -> dict:
    """Register challengers, compare them on recorded runs, promote or card the winners, and
    roll back a promotion its next run shows was worse than what it replaced."""
    from sqlalchemy import select

    from ..core.models import AuditLog
    from . import bootstrap, upgrades

    now = now or datetime.now(timezone.utc)
    booted = bootstrap.ensure(db)
    challengers_registered = bootstrap.register_routing_challengers(db)
    runs = _runs(db)
    configs = _configs(db)

    compared, waiting, promoted, carded, held, refused = [], [], [], [], [], []
    groups: dict[tuple[str, str], list[dict]] = {}
    for c in configs:
        groups.setdefault((c["kind"], c["key"]), []).append(c)

    for (kind, key), rows in groups.items():
        inc = next((r for r in rows if r["incumbent"]), None)
        if inc is None:
            continue
        for ch in [r for r in rows if not r["incumbent"] and not r["retired"]]:
            ir = (runs.get(inc["id"]) or [None])[-1]
            cr = (runs.get(ch["id"]) or [None])[-1]
            if ir is None or cr is None:
                waiting.append({"config_id": ch["id"], "kind": kind, "key": key,
                                "why": ("no recorded run of the "
                                        + ("incumbent" if ir is None else "challenger")
                                        + " on the shared task set. A run is a measured "
                                        "showing somebody produced and recorded; producing "
                                        "one for a model configuration is a model call, "
                                        "and nothing here makes one")})
                continue
            ref = f"league:{ir['run_ref']}|{cr['run_ref']}"
            already = ref in (ch["outcome"].get("evidence_refs") or [])
            if already:
                verdict = dict(ch["outcome"].get("league_verdict_full") or {})
            else:
                try:
                    verdict = compare(result_of(inc["id"], ir), result_of(ch["id"], cr),
                                      shared_tasks=tuple(sorted(ir["tasks"])),
                                      touches=(KIND_SURFACE.get(kind, "code"),),
                                      hypothesis=ch["why"])
                except LeagueRefused as exc:
                    verdict = {"promote": False, "reason": "refused",
                               "blockers": [str(exc)[:400]]}
                record_measured_outcome(db, ch["id"], evidence_ref=ref, outcome={
                    "league_verdict_full": verdict, "against": inc["id"],
                    "role": "challenger"})
                with db.session() as s:
                    s.add(AuditLog(actor="orchestrator", action=COMPARE_ACTION,
                                   artifact=f"{kind}/{key}",
                                   detail={"incumbent": inc["id"], "challenger": ch["id"],
                                           "promote": verdict.get("promote"),
                                           "reason": verdict.get("reason"),
                                           "blockers": verdict.get("blockers", [])[:5],
                                           "holdout": verdict.get("holdout"),
                                           "evidence": verdict.get("evidence"),
                                           "ref": ref}))
                ch["outcome"] = _configs_one(db, ch["id"])
            entry = {"config_id": ch["id"], "kind": kind, "key": key,
                     "promote": bool(verdict.get("promote")),
                     "reason": verdict.get("reason"), "holdout": verdict.get("holdout"),
                     "blockers": verdict.get("blockers", [])[:3], "rejudged": not already}
            compared.append(entry)
            if verdict.get("reason") == "refused":
                refused.append(entry)
            if not verdict.get("promote"):
                continue
            out = _authorise(db, inc, ch, verdict, {"incumbent": ir, "challenger": cr}, ref,
                             now=now)
            {"promoted": promoted, "carded": carded}.get(out["route"], held).append(out)
            if out["route"] == "promoted":
                break                  # the group's incumbent changed; judge the rest next run

    rolled_back = _rollbacks(db, _runs(db), now=now)

    # Close cards whose challenger is no longer waiting on the owner.
    closed = []
    open_challengers = {c["id"] for c in _configs(db) if not c["incumbent"] and not c["retired"]}
    from ..core.models import OwnerAction

    with db.session() as s:
        keys = [a.requirement_key for a in s.scalars(select(OwnerAction).where(
            OwnerAction.done == False)) if (a.requirement_key or "").startswith(  # noqa: E712
                CARD_PREFIX)]
    for k in keys:
        try:
            cid = int(k.split(":", 1)[1])
        except (IndexError, ValueError):
            continue
        if cid not in open_challengers and upgrades.close_owner_card(db, k):
            closed.append(k)

    return {"at": now.isoformat(), "bootstrap": booted,
            "challengers_registered": challengers_registered,
            "compared": compared, "waiting": waiting, "refused": refused,
            "promoted": promoted, "owner_cards": carded, "held": held,
            "rolled_back": rolled_back, "cards_closed": closed,
            "note": (f"{len(compared)} comparison(s) on recorded runs, {len(waiting)} "
                     f"challenger(s) waiting for a run, {len(promoted)} promoted, "
                     f"{len(carded)} routed to the owner, {len(rolled_back)} rolled back")}


def _configs_one(db, config_id: int) -> dict:
    from ..core.models import ConfigVersion

    with db.session() as s:
        row = s.get(ConfigVersion, config_id)
        return dict(row.measured_outcome or {}) if row is not None else {}


def _rollbacks(db, runs: dict, *, now: datetime) -> list[dict]:
    """Roll back a league promotion whose next run is worse than what it replaced."""
    out = []
    for c in _configs(db):
        o = c["outcome"]
        if not c["incumbent"] or o.get("promoted_by") != LEAGUE or not o.get("previous_incumbent"):
            continue
        promoted_at = datetime.fromisoformat(o["promoted_at"])
        after = [r for r in runs.get(c["id"], []) if r["at"] > promoted_at]
        if not after:
            continue
        latest = after[-1]
        observed = result_of(c["id"], latest)
        margin = required_margin(len(observed.tasks))
        replaced_q = float(o.get("replaced_quality") or 0.0)
        replaced_r = float(o.get("replaced_reliability") or 0.0)
        reasons = []
        if observed.quality < replaced_q - margin:
            reasons.append(f"quality {observed.quality:.3f} fell below the {replaced_q:.3f} "
                           f"of the version it replaced by more than the {margin:.3f} margin")
        if observed.reliability < replaced_r:
            reasons.append(f"reliability {observed.reliability:.3f} fell below the "
                           f"{replaced_r:.3f} of the version it replaced")
        if not reasons:
            continue
        done = rollback(db, kind=c["kind"], key=c["key"],
                        to_config_id=int(o["previous_incumbent"]),
                        why=(f"run {latest['run_ref']} after promotion: " + "; ".join(reasons)))
        out.append({**done, "run_ref": latest["run_ref"], "reasons": reasons})
    return out
