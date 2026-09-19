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
}

# How much better a challenger must be on quality to justify promotion at equal cost. Small
# improvements on a shared task set are noise, and a league that promotes on noise churns.
QUALITY_MARGIN = 0.03

# A challenger may cost this much more per call only if quality improves by more than the
# margin again. Beyond it, the trade is a decision rather than an evaluation.
COST_TOLERANCE = 1.25


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
    """One configuration's showing on the shared task set."""

    config_id: int
    tasks: tuple[str, ...]
    quality: float
    cost_cad: float
    reliability: float

    def to_dict(self) -> dict:
        return {"config_id": self.config_id, "tasks": list(self.tasks),
                "quality": round(self.quality, 4), "cost_cad": round(self.cost_cad, 6),
                "reliability": round(self.reliability, 4)}


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

    reasons = []
    if quality_gain <= QUALITY_MARGIN:
        reasons.append(
            f"quality gain {quality_gain:+.3f} is within the {QUALITY_MARGIN} margin; "
            f"promoting on noise is how a league churns")
    if reliability_drop > 0:
        reasons.append(
            f"reliability fell {reliability_drop:.3f}: a configuration that wins when it "
            f"answers and fails more often has not won")
    if cost_ratio > COST_TOLERANCE:
        # The bar scales with the ratio rather than sitting at one threshold: a flat bar
        # treats 1.3x and 5x as the same trade, and they are not. Doubling the spend is
        # allowed to buy a real improvement; quintupling it has to buy a large one.
        required = QUALITY_MARGIN * 2 * (cost_ratio / COST_TOLERANCE)
        if quality_gain <= required:
            reasons.append(
                f"costs {cost_ratio:.2f}x the incumbent for a {quality_gain:+.3f} gain, "
                f"where {required:.3f} would be needed at that ratio. That is a different "
                f"trade rather than an improvement, and a league reporting only quality "
                f"takes it every time and finds the bill at the end of the month")

    return {
        "promote": not reasons,
        "reason": "beats the incumbent on all three axes" if not reasons else "held",
        "blockers": reasons,
        "quality_gain": round(quality_gain, 4),
        "cost_ratio": round(cost_ratio, 3) if cost_ratio != float("inf") else None,
        "reliability_delta": round(-reliability_drop, 4),
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
