"""A club is a promise of work not yet done, and month two is where it is broken.

Requirement 253. Research whether a recurring pattern club, a seasonal collection pass or a
membership would create genuine customer value and predictable revenue -- and do not launch
by assumption. Validate demand, support burden, delivery cadence and platform feasibility
first.

The instruction not to launch by assumption is easy to agree with and hard to obey, because
a club is the most appealing thing a small shop can imagine: predictable revenue, a reason to
make things, and buyers who have already decided. What that appeal hides is the direction the
money flows. A club takes payment for work that does not exist yet, which makes the revenue a
*liability* before it is income -- and the only product in the catalogue where failing to
deliver costs more than the sale, because the people owed are the ones who liked this shop
enough to commit.

Month two is where that happens. Month one ships the thing that already existed; month two
needs a new pattern, certified, on a date somebody else chose. So the cadence question is not
"would people like this" but "can this company make one to the standard it certifies at,
every period, indefinitely" -- and that is answerable from the lead time a product actually
takes rather than from enthusiasm.

The four questions are therefore not equal. Demand is a market question and currently
unmeasurable. Support burden scales with members and is unmeasurable for the same reason.
Platform feasibility is a fact about a marketplace nobody has read the rules of. But cadence
is answerable today, from what this company knows about how long its own work takes, and it
is the one that ends clubs.
"""
from __future__ import annotations

from dataclasses import dataclass

# The four the requirement names, and what each would need before a launch.
QUESTIONS: dict[str, dict] = {
    "demand": {
        "needs": "buyers who bought more than once, asked for more, or said they would pay",
        "answerable_today": False,
        "why": "nobody has bought anything, so nobody has demonstrated wanting the next one",
    },
    "support_burden": {
        "needs": "support cases per member per period, measured",
        "answerable_today": False,
        "why": ("support scales with members and a club concentrates every question into the "
                "week after the drop"),
    },
    "delivery_cadence": {
        "needs": "the lead time one certified product actually takes, against the period",
        "answerable_today": True,
        "why": ("this is the one that ends clubs, and it is arithmetic rather than opinion: "
                "month one ships what already existed and month two needs a new pattern, "
                "certified, on a date somebody else chose"),
    },
    "platform_feasibility": {
        "needs": "the marketplace's own rules on recurring charges, read rather than assumed",
        "answerable_today": False,
        "why": "nobody has read the seller policy, which is a gate rather than a judgement",
    },
}

# What a club actually is, financially, before it is anything else.
NATURE = ("money taken for work that does not exist yet: a liability before it is income, "
          "and the only product where failing to deliver costs more than the sale")

# How much headroom the cadence needs. A club that exactly fits its period has no room for
# the week somebody is ill, and there is always that week.
CADENCE_HEADROOM = 1.3


class ClubRefused(ValueError):
    """A launch on an unanswered question, or a cadence the work does not fit."""


@dataclass(frozen=True)
class Cadence:
    """The period a club promises, against what one product actually takes."""

    period_days: int
    product_lead_days: float
    products_per_period: int = 1


def check_cadence(cadence: Cadence) -> dict:
    """Whether this company can make what the club promises, every period, indefinitely."""
    if cadence.period_days <= 0 or cadence.product_lead_days <= 0:
        raise ClubRefused("a cadence needs a period and a lead time above zero")

    needed = cadence.product_lead_days * cadence.products_per_period * CADENCE_HEADROOM
    fits = needed <= cadence.period_days
    return {
        "period_days": cadence.period_days,
        "needed_days": round(needed, 1),
        "headroom": CADENCE_HEADROOM,
        "fits": fits,
        "why": (f"{cadence.products_per_period} product(s) at "
                f"{cadence.product_lead_days:.0f} days each, with {CADENCE_HEADROOM:g}x "
                f"headroom, needs {needed:.0f} days against a {cadence.period_days}-day "
                f"period"
                + ("" if fits else
                   ". Month one ships what already existed; month two is where this breaks, "
                   "in public, to the people who paid up front")),
        "no_headroom_note": ("a club that exactly fits its period has no room for the week "
                             "somebody is ill, and there is always that week"),
    }


def may_launch(answers: dict[str, bool], *, cadence: Cadence | None = None) -> dict:
    """Whether the research is done. Unanswered is not the same as answered no."""
    unknown = sorted(set(answers) - set(QUESTIONS))
    if unknown:
        raise ClubRefused(f"{unknown} are not questions this lane asks: {sorted(QUESTIONS)}")

    unanswered = [q for q in QUESTIONS if q not in answers]
    answered_no = [q for q, ok in answers.items() if not ok]

    cadence_verdict = check_cadence(cadence) if cadence else None
    if cadence_verdict and not cadence_verdict["fits"] and "delivery_cadence" not in answered_no:
        answered_no.append("delivery_cadence")

    return {
        "may_launch": not unanswered and not answered_no,
        "unanswered": unanswered,
        "answered_no": sorted(set(answered_no)),
        "cadence": cadence_verdict,
        "nature": NATURE,
        "why": ("every question is answered and the cadence fits"
                if not unanswered and not answered_no else
                f"{len(unanswered)} unanswered and {len(set(answered_no))} answered no. "
                f"Unanswered is not answered no, and neither is a launch"),
    }


def research_plan() -> dict:
    """What each question needs, and which one can be answered without a customer."""
    return {
        "questions": {k: dict(v) for k, v in QUESTIONS.items()},
        "answerable_today": [k for k, v in QUESTIONS.items() if v["answerable_today"]],
        "needs_customers_or_a_credential": [k for k, v in QUESTIONS.items()
                                            if not v["answerable_today"]],
        "note": ("only the cadence can be answered today, and it is the one that ends clubs. "
                 "The other three need buyers or a policy read"),
    }


def state() -> dict:
    """What a club is, and what has to be true before one exists."""
    return {
        "nature": NATURE,
        "questions": {k: dict(v) for k, v in QUESTIONS.items()},
        "cadence_headroom": CADENCE_HEADROOM,
        "research_plan": research_plan(),
        "note": ("A club is the most appealing thing a small shop can imagine, and what the "
                 "appeal hides is the direction the money flows: payment for work that does "
                 "not exist yet. Month one ships what already existed; month two needs a new "
                 "pattern, certified, on a date somebody else chose (#253)."),
    }
