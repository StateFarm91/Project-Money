"""The governing model and creative spend policy, in the one place everything else reads.

Recorded 2026-09-20 on the owner's decision, which reversed the standing instruction rather
than relaxing it. The old policy was a hard CA$25 a month and "start economically"; the
build did that faithfully and the faithfulness became the problem. Routing decisions, cadence
intervals and analysis depths had accumulated whose stated justification was the ceiling
rather than the work -- each defensible, and together a company optimising for cheapness.

**QUALITY FIRST. COST SECOND. WASTE NEVER.**

The three clauses are ordered and the order is the policy. Quality decides. Cost is the
tie-breaker, not the argument. And waste -- paying twice for an unchanged listing, asking a
model something deterministic code answers, rendering a field nobody will look at -- is
refused at any budget, because waste is not a saving that was declined, it is spending with
nothing on the other side of it.

**A ceiling is not a target, and this file cannot make it one.** CA$100 a month is the
authority; the expectation is that most months cost far less. What changed is not how much
this company intends to spend but which argument is allowed to win: "the cheaper model is
adequate" is no longer a reason, and "the better model costs several times more" is no
longer an objection when the improvement is commercially meaningful.

**The ceiling lives here and nowhere else.** It used to be restated in two modules, which is
the defect this build has named repeatedly about prices: a number written twice is a number
that will drift, and the one that bills is the one that is true. `routing` and the provider
gateway both read this constant, and a test refuses a second literal.

**Approaching the ceiling is a report, never a quiet downgrade.** If genuinely useful work
consumes the budget, the answer is an owner action with the evidence attached -- what was
spent, what it bought, what is being constrained, what a higher ceiling would buy. Silently
routing to a weaker model to stay inside is the failure this policy exists to prevent, and it
is the one that would never appear in any log.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

# The one ceiling. Combined model, vision and image-generation spend, per calendar month.
# Raised from CA$25 on 2026-09-20. Infrastructure is a separate ceiling (CA$20) and is not
# governed here.
CEILING_CAD = 100.0
PREVIOUS_CEILING_CAD = 25.0
CEILING_SET_ON = "2026-09-20"

# Report to the owner at this share of the ceiling, with evidence, rather than waiting for a
# refusal. Four-fifths leaves room to finish the month's committed work while the decision is
# being made -- an escalation that arrives at the moment of the first refusal arrives too
# late to be a decision and only in time to be a complaint.
ESCALATE_AT_SHARE = 0.80

# A separate, one-off authorisation: what the owner approved for the controlled
# image-provider benchmark. Here rather than in the benchmark module for the same reason the
# monthly ceiling is here -- owner-authorised money is written once, in the file that says
# what the authority is, so a second literal cannot drift from it.
# Cumulative lifetime authorization for the image-provider benchmark, raised from CA$25 by
# the owner on 2026-09-21 and explicitly *inclusive of everything already spent* across every
# prior run: rendering, blind judging, retries, re-drives and the experiments that were
# invalidated when the method was corrected. It is not CA$50 of new spend. The distinction is
# the whole reason the figure is enforced cumulatively rather than per run -- four runs each
# stayed inside a CA$25 approved once, which is how CA$25 became CA$31.
BENCHMARK_BUDGET_CAD = 50.0

# Spend that buys nothing, refused at any budget. Not a cost-saving list: each of these is
# money with nothing on the other side of it, which is a different thing from money the
# policy would rather not spend.
WASTE: dict[str, str] = {
    "recompute_unchanged": (
        "an observation whose content fingerprint has not moved is the same observation. "
        "Paying for it twice buys the answer already held (#212, #225)"),
    "ask_what_code_answers": (
        "stitch counts, yardage, gauge and every other pattern fact are decided by the "
        "compiler. A model asked them produces noise with a price (§27)"),
    "duplicate_questions": (
        "a second question about the same picture is a second bill for an answer already "
        "bought. Derive from what was gathered rather than re-asking"),
    "unbatched_fields": (
        "a field of concepts asked one at a time costs more and produces less variety, "
        "because a model asked for five different things at once cannot answer with the "
        "same thing five times"),
    "render_what_nobody_reads": (
        "an asset generated for a frame the gallery will not carry is finished waste rather "
        "than cheap work"),
}

# What the owner named as worth paying for, in the owner's order. Each carries what may not
# be traded away to save money, because "we economised here" is the sentence this list
# exists to make impossible to write without noticing.
@dataclass(frozen=True)
class Priority:
    rank: int
    key: str
    what: str
    never: str


PRIORITIES: tuple[Priority, ...] = (
    Priority(1, "product_creativity",
             "the product itself must be exceptional",
             "a technically correct mediocre product is a failure, so concept tournaments "
             "and jury quality are not reduced to preserve unused budget"),
    Priority(2, "mjs_intelligence",
             "deep analysis of the accessible benchmark catalogue and gallery evidence",
             "visual-analysis depth is not reduced where deeper analysis materially "
             "improves product decisions"),
    Priority(3, "product_visualization",
             "crochet texture, construction, proportions and materials convincing enough "
             "for serious creative evaluation",
             "an inferior image model is not selected because it saves a few dollars"),
    Priority(4, "model_identity",
             "permanent identity consistency once the canonical model is chosen",
             "identity drift is a failed asset; reference-conditioning architecture is "
             "chosen on what performs, not on what is cheapest"),
    Priority(5, "listing_and_storefront_creative",
             "heroes, galleries, banner, icon and seasonal storefront at the premium "
             "standard",
             "materially inferior customer-facing creative is not chosen because the better "
             "option costs modestly more"),
    Priority(6, "high_value_judgement",
             "final concept selection, benchmark challenges and flagship decisions",
             "important creative judgement is not downgraded to a weaker model to save "
             "pennies"),
)

PRIORITY_BY_KEY: dict[str, Priority] = {p.key: p for p in PRIORITIES}

# The levers that reduce cost without reducing quality. Kept as a list because the policy's
# third clause is an instruction to keep using them, not permission to stop.
LEVERS: tuple[str, ...] = (
    "content-keyed caching, which cannot go stale: a changed input has a different key and "
    "simply misses",
    "fingerprints, so an unchanged competitor listing is never re-read",
    "deduplication across pods, so one observation is not paid for by each reader",
    "batching, which is cheaper per item and produces more internal variety",
    "tier routing by what the task needs, so reading a title into a category does not cost "
    "what judging a photograph costs",
)

# The sentence this policy was written to make unwriteable, kept verbatim so a test can look
# for it. A justification that reduces to "the cheaper option was adequate" is refused.
REFUSED_JUSTIFICATION = "the cheaper option was adequate"


# What share of the month one purpose may consume before it has to stop and say so.
#
# Not a budget-splitting exercise: only the purposes that can run away have an entry, and
# the number is a *stop*, not an allowance to reach. Gallery analysis is the live case --
# measured at CA$0.029 an image, the raised cadence is CA$8.70 a day while the backlog
# drains, which is CA$260 a month if the queue never empties. The queue does empty, and a
# capability whose safety depends on an assumption about a queue is a capability with no
# guard at all.
#
# The purpose of the cap is priority order rather than thrift. Product creativity is the
# owner's first priority and MJs intelligence the second, so a four-day image backlog must
# not be able to consume the month and leave concept generation refused at the ceiling. When
# it stops it stops loudly and the work is named as constrained -- which is the escalation
# path, not a quiet downgrade.
ALLOCATION: dict[str, float] = {
    "gallery_observation": 0.40,
}


def may_spend(db, purpose: str, *, now: datetime | None = None) -> dict:
    """Whether this purpose has room left in its share of the month.

    Returns rather than raises: the caller is a drain loop, and a loop that crashes on a
    budget boundary loses the work it had already done. It stops, records why, and the
    reason reaches the owner as constrained work instead of as a smaller number nobody
    queried.
    """
    from . import spend_report

    share = ALLOCATION.get(purpose)
    if share is None:
        return {"may_spend": True, "purpose": purpose, "capped": False,
                "why": "no allocation: this purpose cannot run away on its own"}

    report = spend_report.what_it_bought(db, now=now)
    spent = float((report["by_purpose"].get(purpose) or {}).get("cad") or 0.0)
    allowed = round(CEILING_CAD * share, 4)
    return {
        "may_spend": spent < allowed,
        "purpose": purpose,
        "capped": True,
        "spent_cad": round(spent, 4),
        "allowed_cad": allowed,
        "share_of_ceiling": share,
        "why": (f"{purpose} has spent CA${spent:.2f} of the CA${allowed:.2f} this month's "
                f"policy allows it. Stopping here keeps the ceiling available for the "
                f"priorities above it rather than letting one backlog consume the month"
                if spent >= allowed else
                f"CA${round(allowed - spent, 2):.2f} of this purpose's share remains"),
    }


class PolicyRefused(ValueError):
    """A trade the policy does not allow, or an escalation with nothing behind it."""


def ceiling_cad() -> float:
    """The authorised monthly ceiling. Every other module reads this rather than a literal."""
    return CEILING_CAD


def headroom(spent_cad: float) -> dict:
    """Where the month stands, and whether it is time to tell the owner."""
    share = round(spent_cad / CEILING_CAD, 4) if CEILING_CAD else 1.0
    return {
        "spent_cad": round(spent_cad, 4),
        "ceiling_cad": CEILING_CAD,
        "share": share,
        "remaining_cad": round(CEILING_CAD - spent_cad, 4),
        "escalate": share >= ESCALATE_AT_SHARE,
        "escalate_at_share": ESCALATE_AT_SHARE,
        "why_early": ("an escalation that arrives at the first refusal arrives too late to "
                      "be a decision and only in time to be a complaint"),
    }


def may_downgrade_for_cost(*, priority_key: str, reason: str) -> None:
    """Refuse a quality downgrade whose argument is money.

    Called where the temptation lives: a routing choice, a cadence interval, an analysis
    depth. It does not stop anybody hard-coding a cheaper model -- nothing could -- but it
    refuses the *declared* trade, so a downgrade has to be made without saying why, and a
    change with no stated reason is what code review is for.
    """
    priority = PRIORITY_BY_KEY.get(priority_key)
    if priority is None:
        raise PolicyRefused(
            f"{priority_key!r} is not one of the owner's spending priorities: "
            f"{sorted(PRIORITY_BY_KEY)}")
    raise PolicyRefused(
        f"priority {priority.rank} ({priority.key}) may not be traded for cost: "
        f"{priority.never}. The stated reason was {reason!r}. Quality decides; cost is the "
        f"tie-breaker, not the argument")


def escalation(db, *, now: datetime | None = None,
               constrained: list[str] | None = None,
               proposed_ceiling_cad: float | None = None,
               expected_value: str = "") -> dict:
    """The OWNER ACTION REQUIRED report, in the shape the owner asked for.

    Six fields, and the two that are easy to leave out are the two that matter: what the
    money produced, and what work is being constrained. A ceiling request with the first
    four is a bill; with all six it is a decision somebody can make.
    """
    from . import spend_report

    now = now or datetime.now(timezone.utc)
    produced = spend_report.what_it_bought(db, now=now)
    state = headroom(produced["spent_cad"])

    if not state["escalate"] and proposed_ceiling_cad is None:
        return {"required": False, **state,
                "why": (f"the month is {state['share'] * 100:.0f}% spent, under the "
                        f"{ESCALATE_AT_SHARE * 100:.0f}% at which this reports. Nothing is "
                        f"being constrained and nothing is asked for")}

    return {
        "required": True,
        "action": "raise the authorised monthly model and creative spend ceiling",
        "current_spend_cad": state["spent_cad"],
        "ceiling_cad": CEILING_CAD,
        "share_of_ceiling": state["share"],
        "burn_rate_cad_per_day": produced["burn_rate_cad_per_day"],
        "projected_month_end_cad": produced["projected_month_end_cad"],
        "what_the_money_produced": produced["by_purpose"],
        "what_is_constrained": constrained or [],
        "proposed_ceiling_cad": proposed_ceiling_cad or round(CEILING_CAD * 2, 2),
        "expected_improvement": expected_value or (
            "state what the additional ceiling buys before asking for it. A request with no "
            "expected improvement is a bill"),
        "not_doing_meanwhile": (
            "quality is not silently degraded to stay inside. Work that cannot be done at "
            "the standard the policy sets waits and is named here"),
        "minutes": 2,
        "consequence_of_waiting": (
            "the named work stops at the ceiling rather than being done worse"),
    }


def state(db=None) -> dict:
    """The policy as a readable object, for the console and for the owner."""
    body = {
        "policy": "QUALITY FIRST. COST SECOND. WASTE NEVER.",
        "ceiling_cad": CEILING_CAD,
        "previous_ceiling_cad": PREVIOUS_CEILING_CAD,
        "ceiling_set_on": CEILING_SET_ON,
        "ceiling_is_not_a_target": (
            "the authority is CA$100; the expectation is that most months cost far less. "
            "What changed is which argument may win, not how much this company intends to "
            "spend"),
        "priorities": [{"rank": p.rank, "key": p.key, "what": p.what, "never": p.never}
                       for p in PRIORITIES],
        "waste_refused_at_any_budget": dict(WASTE),
        "levers": list(LEVERS),
        "escalate_at_share": ESCALATE_AT_SHARE,
        "per_purpose_allocation": dict(ALLOCATION),
        "allocation_is_a_stop_not_an_allowance": (
            "only purposes that can run away have an entry. The cap exists for priority "
            "order rather than thrift: a four-day image backlog must not consume the month "
            "and leave concept generation refused at the ceiling"),
        "infrastructure_is_separate": (
            "recurring infrastructure has its own CA$20 ceiling and is not governed here"),
    }
    if db is not None:
        from . import spend_report

        produced = spend_report.what_it_bought(db)
        body["this_month"] = headroom(produced["spent_cad"])
        body["burn_rate_cad_per_day"] = produced["burn_rate_cad_per_day"]
    return body


def month_start(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    return date(now.year, now.month, 1)
