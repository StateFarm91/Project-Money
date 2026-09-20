"""The agents whose only job is other agents, and the three ways such a swarm flatters itself.

Requirement 179. Dedicated meta-agents — evaluator, failure-miner, experiment designer,
prompt/tool challenger, cost optimiser, reliability engineer, creative critic and
cross-department lesson router — whose work is measured by *verified uplift, not number of
changes*.

The machinery these roles operate already exists: `improve.cells` measures each department's
capability, `improve.bus` routes lessons, `improve.roi` computes realised benefit,
`improve.league` runs challengers, `improve.governance` bounds what any self-improvement may
touch, `improve.tiers` says what evidence a change needs. What did not exist is the roster:
who is accountable for which of those, what each may and may not do, and how each is scored.
A swarm with no roster is a swarm where every agent is vaguely responsible for improvement,
which is the same as none of them being responsible for any of it.

**Scored on uplift, and structurally unable to be scored on activity.** The requirement's last
clause is the whole of the danger. An improvement swarm graded on changes made will make
changes: it will find forty findings, file thirty proposals, promote twelve, and the
department will not be measurably better at anything. So `scorecard()` computes from realised
benefit alone, `proposals_made` is recorded and cannot enter the score, and a scorecard that
tries to include it is refused. A role that proposed forty changes and kept none scores zero,
not forty.

And the other half of that, which matters as much: **a rejected proposal scores zero, never
negative.** Penalising rejection teaches the swarm to propose only what will obviously pass,
and a challenger that only proposes safe changes has stopped being a challenger. Removing a
hypothesis is worth something; it is just not worth uplift.

**Nobody grades their own homework.** The evaluator may not evaluate a proposal it authored
and the challenger may not judge its own challenge — not because these agents would cheat,
but because the author of a change has necessarily been thinking about the cases it handles
well, which is the same failure `improve.league` refuses at the task-set level. Here it is
refused at the person level.

**Opposed objectives name what they may not trade.** The cost optimiser wants spend down and
the reliability engineer wants failures down, and those pull against each other. Given one
scalar score, whichever runs last pays for the other out of a budget nobody agreed to spend.
So each role carries what it may never trade away, and a proposal that trades it is refused
by name rather than weighed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import governance

# ---- what a role may do ---------------------------------------------------

PROPOSE = "propose"          # may put a change forward
JUDGE = "judge"              # may decide whether a change is an improvement
ROUTE = "route"              # may move a lesson between departments
ANNOTATE = "annotate"        # may add an opinion that is never sole evidence

POWERS: tuple[str, ...] = (PROPOSE, JUDGE, ROUTE, ANNOTATE)


class RoleRefused(ValueError):
    """A meta-agent asked to grade itself, trade what it may not, or count its own activity."""


@dataclass(frozen=True)
class Role:
    """One meta-agent: its job, its powers, its measure and its hard limit."""

    key: str
    title: str
    job: str
    powers: tuple[str, ...]
    reads: str                    # the module whose rows it works from
    measured_by: str              # always an uplift, never a count
    must_not_trade: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        unknown = sorted(set(self.powers) - set(POWERS))
        if unknown:
            raise RoleRefused(f"{self.key}: {unknown} are not powers: {list(POWERS)}")
        if PROPOSE in self.powers and JUDGE in self.powers:
            raise RoleRefused(
                f"{self.key} may both propose and judge. The author of a change has "
                f"necessarily been thinking about the cases it handles well, which is the "
                f"failure improve.league refuses at the task-set level; this is the same "
                f"failure at the person level, and it is not fixed by good intentions")

    def to_dict(self) -> dict:
        return {"key": self.key, "title": self.title, "job": self.job,
                "powers": list(self.powers), "reads": self.reads,
                "measured_by": self.measured_by,
                "must_not_trade": list(self.must_not_trade), "note": self.note}


# The eight the requirement names. Closed: an improvement swarm that grows a role whenever
# something is hard is the crowd `swarm.orchestrate` exists to prevent, one level up.
ROLES: tuple[Role, ...] = (
    Role("evaluator", "Evaluator",
         "decide whether a proposed change actually improved the thing it touched",
         (JUDGE,), "improve.roi and improve.cells",
         "the share of its verdicts later confirmed by the measured capability curve",
         ("deterministic_validation",),
         note=("judges, and therefore never proposes. Its own measure is whether its calls "
               "held up, not how many it made")),
    Role("failure_miner", "Failure Miner",
         "read incidents, dead letters, refusals and complaints for the pattern behind them",
         (PROPOSE,), "gates.incidents, queue dead letters, support cases",
         "uplift of the changes its findings led to, after they were kept",
         note=("a finding nobody acted on is worth nothing here, which is the correct "
               "incentive: mining is easy and fixing is the work")),
    Role("experiment_designer", "Experiment Designer",
         "turn a hypothesis into a test that can come back negative",
         (PROPOSE,), "commerce.listing_tests and requirement 265's portfolio",
         "uplift of the decisions its experiments changed",
         note=("an experiment that cannot change a decision is killed by #265 before it "
               "runs; designing one is not output")),
    Role("prompt_tool_challenger", "Prompt / Tool Challenger",
         "run challenger configurations against incumbents on the shared task set",
         (PROPOSE,), "improve.league",
         "uplift of promoted challengers, measured after promotion",
         note="proposes challengers; the league and the evaluator decide them"),
    Role("cost_optimiser", "Cost Optimiser",
         "reduce spend per unit of work without buying the reduction from somewhere else",
         (PROPOSE,), "the cost ledger and finance.governor",
         "cost removed that stayed removed, net of any uplift it cost",
         ("reliability", "quality", "deterministic_validation"),
         note=("the cheapest configuration is always the one that does less. What it may "
               "not trade is named because a single score would let it")),
    Role("reliability_engineer", "Reliability Engineer",
         "reduce the share of work that fails, retries or dead-letters",
         (PROPOSE,), "runtime queue and ops.health",
         "failures removed that stayed removed",
         ("contribution", "deterministic_validation"),
         note=("the most reliable system is one that attempts nothing interesting; the "
               "trade it may not make is buying reliability with the business")),
    Role("creative_critic", "Creative Critic",
         "say where creative work is weak, before a buyer has to",
         (ANNOTATE,), "creative tournament and publish.layout_qa",
         "uplift of the creative changes its notes led to",
         note=("annotates only. A model's opinion about a design is never the sole evidence "
               "for a release decision -- deterministic validation wins even if every LLM "
               "disagrees, and that rule does not soften because the subject is aesthetic")),
    Role("lesson_router", "Cross-Department Lesson Router",
         "carry a lesson from the department that learned it to the ones it applies to",
         (ROUTE,), "improve.bus",
         "uplift in the receiving departments, not lessons published",
         note=("publishing is the cheap half. improve.bus already records who acted on "
               "what, which is the number that means anything")),
)

BY_KEY: dict[str, Role] = {r.key: r for r in ROLES}

# The single job type every role runs. One type rather than eight because the work differs by
# role and not by kind: each of these reads its own rows and reports what it found, and eight
# job types would be eight handlers doing the same shape of thing with different queries.
# The *agent* is the role, so `ctx.job.agent` is what dispatches.
ROLE_JOB_TYPE = "improve.role_work"

# What each role reads when its cadence fires, named here so the handler cannot quietly
# change what a role is accountable for.
ROLE_READS: dict[str, str] = {
    "evaluator": "promotions recorded since the last pass, against the capability curve after",
    "failure_miner": "open incidents and dead letters, grouped by signature",
    "experiment_designer": "experiments that have run long enough to have concluded",
    "prompt_tool_challenger": "configurations with no challenger registered against them",
    "cost_optimiser": "ledger entries by category against what they returned",
    "reliability_engineer": "dead letters and failing health signals",
    "creative_critic": "listing assets refused by the truth gate or the layout check",
    "lesson_router": "lessons routed and not acted on",
}

# Things a role's proposal may claim to trade. Closed so that "efficiency" cannot be used to
# mean whatever the proposal needs it to mean.
TRADEABLE: tuple[str, ...] = ("cost", "latency", "reliability", "quality", "contribution",
                              "coverage", "deterministic_validation")

# What no role may trade, whatever its objective. Repeated here rather than inferred, because
# a rule that only exists inside another module's check is a rule nobody reads.
NEVER_TRADEABLE: tuple[str, ...] = ("deterministic_validation",)


def role(key: str) -> Role:
    if key not in BY_KEY:
        raise RoleRefused(f"{key!r} is not a meta-agent role: {sorted(BY_KEY)}")
    return BY_KEY[key]


# ---- nobody grades their own homework -------------------------------------

def may_judge(*, judge: str, author: str) -> dict:
    """Whether this role may rule on a proposal that role made."""
    j, a = role(judge), role(author)
    if JUDGE not in j.powers:
        return {"may_judge": False, "why": f"{j.key} has no judging power: {list(j.powers)}"}
    if judge == author:
        return {"may_judge": False,
                "why": (f"{j.key} authored this proposal. An author has necessarily been "
                        f"thinking about the cases the change handles well, which is the "
                        f"same failure improve.league refuses when a challenger brings its "
                        f"own tasks")}
    if a.key not in BY_KEY:  # pragma: no cover - role() already raised
        return {"may_judge": False, "why": "unknown author"}
    return {"may_judge": True, "judge": j.key, "author": a.key,
            "why": "the judge did not write it"}


# ---- what a proposal may trade --------------------------------------------

def check_proposal(*, author: str, trades: tuple[str, ...] = (),
                   hypothesis: str = "", touches: tuple[str, ...] = ()) -> dict:
    """A proposal's trades, against what its author may never trade away."""
    r = role(author)
    if PROPOSE not in r.powers and ANNOTATE not in r.powers:
        raise RoleRefused(f"{r.key} may not propose changes: {list(r.powers)}")

    unknown = sorted(set(trades) - set(TRADEABLE))
    if unknown:
        raise RoleRefused(
            f"{unknown} are not things a proposal may name as traded: {list(TRADEABLE)}. An "
            f"open vocabulary lets 'efficiency' mean whatever the proposal needs it to mean")

    forbidden = sorted(set(trades) & set(NEVER_TRADEABLE))
    if forbidden:
        return {"ok": False, "author": r.key, "trades": list(trades),
                "why": (f"{forbidden} may not be traded by any role. Deterministic "
                        f"validation wins even if every LLM disagrees, and an improvement "
                        f"that buys its improvement from the compiler's correctness is not "
                        f"an improvement")}

    crossed = sorted(set(trades) & set(r.must_not_trade))
    if crossed:
        return {"ok": False, "author": r.key, "trades": list(trades),
                "why": (f"{r.key} may not trade {crossed}: {r.note}. Given one scalar score "
                        f"it would, and whoever ran last would have spent a budget nobody "
                        f"agreed to")}

    if hypothesis:
        boundary = governance.check(hypothesis, touches=touches)
        if not boundary.ok:
            return {"ok": False, "author": r.key, "trades": list(trades),
                    "why": f"refused by the improvement boundary: {boundary.reason}"}

    return {"ok": True, "author": r.key, "trades": list(trades),
            "why": f"{r.key} may make this trade, and the boundary allows it"}


# ---- scored on uplift, and nothing else -----------------------------------

@dataclass(frozen=True)
class Activity:
    """What a role did in a period. Two of these three fields cannot reach the score."""

    role_key: str
    proposals_made: int = 0
    proposals_kept: int = 0
    realised_uplift: float = 0.0
    kept_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        role(self.role_key)
        if self.proposals_kept > self.proposals_made:
            raise RoleRefused(
                f"{self.role_key}: {self.proposals_kept} kept of {self.proposals_made} "
                f"proposed")
        if any(v < 0 for v in (self.proposals_made, self.proposals_kept)):
            raise RoleRefused("negative counts are not activity")


UNMEASURED = "unmeasured"

# A role with kept proposals whose benefit has not been realised yet is `unmeasured`, not
# zero. `improve.roi` holds the realisation window; the distinction is the same one this
# build keeps making, and getting it wrong here retires an agent for being recent.
REALISATION_PENDING = "realisation_pending"


def scorecard(activity: Activity) -> dict:
    """One role's period, scored on uplift alone.

    `proposals_made` is reported because somebody will want it, and it is arithmetically
    unable to reach the score: an improvement swarm graded on changes made will make changes,
    and the department will not be measurably better at anything.
    """
    r = role(activity.role_key)
    if activity.proposals_made == 0:
        return {"role": r.key, "score": 0.0, "reading": UNMEASURED,
                "proposals_made": 0, "proposals_kept": 0,
                "why": ("nothing was proposed, so there is no uplift to attribute. That is "
                        "not the same as having tried and failed, and it is not scored as "
                        "if it were")}
    if activity.proposals_kept > 0 and activity.realised_uplift == 0.0:
        return {"role": r.key, "score": 0.0, "reading": REALISATION_PENDING,
                "proposals_made": activity.proposals_made,
                "proposals_kept": activity.proposals_kept,
                "why": ("changes were kept and their benefit has not been realised yet. "
                        "improve.roi holds the window; scoring this as zero uplift would "
                        "retire an agent for being recent")}
    return {
        "role": r.key,
        "score": round(activity.realised_uplift, 4),
        "reading": "measured",
        "measured_by": r.measured_by,
        "proposals_made": activity.proposals_made,
        "proposals_kept": activity.proposals_kept,
        "kept_refs": list(activity.kept_refs),
        "why": (f"{activity.realised_uplift:+.4f} of realised uplift from "
                f"{activity.proposals_kept} kept changes. The {activity.proposals_made} "
                f"proposals are reported and cannot enter this number"),
        "rejections_cost_nothing": (
            "a proposal that was tested and rejected scores zero, never negative. Penalising "
            "rejection teaches the swarm to propose only what will obviously pass, and a "
            "challenger that only proposes safe changes has stopped being a challenger"),
    }


def swarm_report(activities: list[Activity]) -> dict:
    """Every role's period together, with the roles nobody staffed named rather than absent."""
    by_key = {a.role_key: a for a in activities}
    cards = []
    for r in ROLES:
        a = by_key.get(r.key)
        cards.append(scorecard(a) if a is not None else
                     {"role": r.key, "score": 0.0, "reading": UNMEASURED,
                      "why": "no activity recorded for this role in the period"})
    measured = [c for c in cards if c["reading"] == "measured"]
    return {
        "roles": cards,
        "total_uplift": round(sum(c["score"] for c in measured), 4),
        "measured_roles": len(measured), "of": len(ROLES),
        "unstaffed": [c["role"] for c in cards if c["reading"] == UNMEASURED],
        "note": ("the total is uplift, not throughput. A swarm that proposed two hundred "
                 "changes and moved no capability curve reports zero here, which is the "
                 "number the requirement asks for"),
    }


def state() -> dict:
    """The roster, and the rules that keep it from grading itself."""
    return {
        "requirement": 179,
        "roles": [r.to_dict() for r in ROLES],
        "operates": {
            "improve.cells": "the capability curve each role is trying to move",
            "improve.roi": "realised benefit, which is the only thing scored",
            "improve.league": "where the challenger's proposals are decided",
            "improve.bus": "where the router's lessons are recorded as acted on",
            "improve.governance": "the boundary every proposal passes",
        },
        "refuses": [
            "a role that both proposes and judges",
            "a judge ruling on a proposal it authored",
            "a proposal trading what its author may never trade",
            "any proposal trading deterministic validation",
            "a scorecard computed from proposals made",
        ],
        "never_tradeable": list(NEVER_TRADEABLE),
        "job_type": ROLE_JOB_TYPE,
        "reads": dict(ROLE_READS),
        "note": ("measured by verified uplift, not number of changes -- implemented as an "
                 "arithmetic impossibility rather than as a policy"),
    }
