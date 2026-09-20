"""Rewarding an action, never an opinion -- and never rewarding what cannot be counted.

Requirement 256. Test legitimate referral and share mechanics that encourage customers to
show finished projects or share useful products, without manipulating reviews. Track
attributable new customers and contribution. Never condition support or discounts on positive
reviews.

The prohibition is the same line this build has drawn twice already, arriving from a third
direction: a collaboration may buy work and never an opinion (#9), a support reply may not
ask for a rating (#257), and here a reward may be for an *action* -- showing a finished
object, passing on a link -- and never for an *outcome statement*. The distinction survives
contact with a marketing plan only if it is checkable, so the reward names what triggers it,
and a trigger phrased as a sentiment is refused. `commerce.reviews` already holds the phrases
that do that, and they are imported rather than listed again.

The second rule is about counting, and it is the one that makes a referral programme
measurable or decorative. "Tell a friend" produces no evidence of anything: new customers
arrive, and whoever likes the programme attributes them to it. A mechanic with no attribution
cannot be judged -- and it will be judged anyway, favourably, by the person who proposed it.
So a mechanic without an attributable trigger is refused before it runs rather than argued
about afterwards.

The third is arithmetic. A referral reward is a cost per acquired customer, and it is worth
paying only against contribution rather than revenue: a CA$5 credit against a CA$6 pattern is
a customer acquired at a loss that looks like growth in every report that stops at the top
line.
"""
from __future__ import annotations

from dataclasses import dataclass

from .reviews import GATING_PHRASES

# What a customer may be rewarded for doing. Every entry is an action somebody takes, not an
# opinion somebody holds.
REWARDABLE: dict[str, str] = {
    "shows_finished_project": "they photograph what they made and show it, however it went",
    "shares_a_link": "they pass the product on to somebody who might want it",
    "brings_a_first_purchase": "somebody they referred buys for the first time",
}

# What a reward may never be for. Named so the refusal can say the word.
NEVER_REWARDABLE: tuple[str, ...] = (
    "a positive review", "a rating", "a five-star", "a testimonial", "a public endorsement",
    "removing a negative review")

# A mechanic has to leave evidence, or it cannot be judged and will be judged anyway.
ATTRIBUTABLE: tuple[str, ...] = ("referral_code", "unique_link", "recorded_mention")

# The reward is a cost per acquired customer, paid out of contribution rather than revenue.
MAX_SHARE_OF_CONTRIBUTION = 0.30


class ReferralRefused(ValueError):
    """A reward for an opinion, a mechanic nothing can attribute, or one that loses money."""


@dataclass(frozen=True)
class Mechanic:
    """One referral or share mechanic: what it rewards, how it is counted, what it costs."""

    key: str
    rewards: str
    attribution: str = ""
    reward_cad: float = 0.0
    copy: str = ""

    def __post_init__(self) -> None:
        if self.rewards not in REWARDABLE:
            raise ReferralRefused(
                f"{self.rewards!r} is not something a customer does: {sorted(REWARDABLE)}. "
                f"A reward is for an action, never for an opinion")


def check(mechanic: Mechanic, *, contribution_per_customer_cad: float | None = None) -> dict:
    """Whether this mechanic may run, and which of the three rules it breaks if not."""
    reasons: list[str] = []

    lowered = mechanic.copy.lower()
    sentiment = sorted({p for p in GATING_PHRASES if p in lowered})
    if sentiment:
        reasons.append(
            f"the copy contains {sentiment}, which rewards what somebody says rather than "
            f"what they did. The phrases are commerce.reviews' own, because this is the same "
            f"line arriving from a third direction")

    if mechanic.attribution not in ATTRIBUTABLE:
        reasons.append(
            f"{mechanic.attribution or 'nothing'} attributes this. 'Tell a friend' produces "
            f"no evidence: new customers arrive and whoever likes the programme attributes "
            f"them to it. A mechanic that cannot be judged will be judged anyway, favourably, "
            f"by the person who proposed it")

    if contribution_per_customer_cad is None:
        reasons.append(
            "no contribution per customer, so the reward cannot be checked against anything. "
            "A reward is a cost per acquired customer")
    elif mechanic.reward_cad > contribution_per_customer_cad * MAX_SHARE_OF_CONTRIBUTION:
        reasons.append(
            f"CA${mechanic.reward_cad:.2f} against CA${contribution_per_customer_cad:.2f} of "
            f"contribution, above {MAX_SHARE_OF_CONTRIBUTION:.0%}. A credit larger than the "
            f"margin is a customer acquired at a loss that looks like growth in every report "
            f"stopping at the top line")

    return {
        "mechanic": mechanic.key, "ok": not reasons, "reasons": reasons,
        "rewards": mechanic.rewards,
        "rewards_what": REWARDABLE[mechanic.rewards],
        "never_rewards": list(NEVER_REWARDABLE),
        "attribution": mechanic.attribution,
    }


def outcome(*, attributed_customers: int | None, contribution_cad: float | None,
            reward_spend_cad: float) -> dict:
    """What the programme produced, or why that cannot be said."""
    if attributed_customers is None or contribution_cad is None:
        missing = [n for n, v in (("attributed_customers", attributed_customers),
                                  ("contribution_cad", contribution_cad)) if v is None]
        return {"measurable": False, "missing": missing,
                "why": ("an unmeasured referral programme is the one everybody remembers "
                        "fondly. Both numbers or neither")}
    net = contribution_cad - reward_spend_cad
    return {
        "measurable": True,
        "attributed_customers": attributed_customers,
        "contribution_cad": round(contribution_cad, 2),
        "reward_spend_cad": round(reward_spend_cad, 2),
        "net_cad": round(net, 2),
        "worth_it": net > 0,
        "why": ("contribution after the rewards it cost"),
    }


def state() -> dict:
    """What may be rewarded, what may never be, and what has to be countable."""
    return {
        "rewardable": dict(REWARDABLE),
        "never_rewardable": list(NEVER_REWARDABLE),
        "attribution": list(ATTRIBUTABLE),
        "max_share_of_contribution": MAX_SHARE_OF_CONTRIBUTION,
        "shares_its_refusals_with": "commerce.reviews",
        "note": ("A reward is for an action -- showing what you made, however it went, or "
                 "passing something on -- and never for an outcome statement. And a mechanic "
                 "nothing can attribute will be judged anyway, favourably, by the person who "
                 "proposed it (#256)."),
    }
