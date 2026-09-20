"""The trust sprint, and the four fifths of it that happen before the first customer.

Requirement 259. During the first hundred customers, prioritise flawless downloads, rapid
support, truthful expectations, defect prevention and post-purchase clarity -- without
sacrificing contribution irrationally -- because early trust compounds.

Reading it as written produces a plan that starts on the day of the first sale, and that is
the wrong day for four of the five. A flawless download is a property of the delivery path,
and the first buyer either gets the file or does not; there is no version of "we will make
downloads flawless during the first hundred" that helps customer one. Truthful expectations
are written into a listing before anybody reads it. Defect prevention is the release chain,
which runs before a product exists to sell. Post-purchase clarity is a page and a file that
are either written or not.

Only rapid support genuinely needs customers, because it is a response time and there is
nothing to respond to yet. So the sprint's honest shape is: four priorities that are *ready
or not ready today*, checkable now, and one that starts when the first buyer does.

That matters because the alternative is comfortable. A plan that begins at the first sale
lets every one of these sit unfinished while the shop feels prepared, and the first hundred
customers are the ones whose experience compounds hardest -- they are the review base, the
repeat base and the proof base, and each of them arrives exactly once.

**A sprint ends.** Saying so is not pedantry: a permanent sprint is just how the company
works, and calling it a sprint is how nobody asks when the extra cost stops. This one ends at
a hundred customers, and what it buys afterwards is the ordinary standard.

**What it may spend is time and prevention, never price.** "Do not sacrifice contribution
irrationally" has a specific reading here: a discount during the trust sprint teaches the
hundred buyers whose repeat behaviour matters most that the price is negotiable, and they are
precisely the cohort a value ladder depends on. The sprint may cost support hours, sample
costs and slower shipping of new products. It may not cost the price.
"""
from __future__ import annotations

from dataclasses import dataclass

from .buyer_trust import REQUIRED_DISCLOSURES

BEFORE = "before_the_first_customer"
DURING = "during_the_first_hundred"

# The five the requirement names, when each is actually done, and what makes it true.
PRIORITIES: dict[str, dict] = {
    "flawless_downloads": {
        "when": BEFORE,
        "what": "the file arrives, opens, and is the right version",
        "ready_when": ("the delivery path has been exercised end to end and the file a buyer "
                       "receives is the one the certificate covers"),
        "why_not_later": ("the first buyer either gets the file or does not, and there is no "
                          "version of improving this during the first hundred that helps "
                          "customer one"),
    },
    "truthful_expectations": {
        "when": BEFORE,
        "what": "every disclosure a purchase needs, where it is actually read",
        "ready_when": f"all of {sorted(REQUIRED_DISCLOSURES)} are present on their surfaces",
        "why_not_later": "a listing is written before anybody reads it",
    },
    "defect_prevention": {
        "when": BEFORE,
        "what": "the release chain, run in full, on everything that is sold",
        "ready_when": "every listed product carries a certificate from the current chain",
        "why_not_later": "prevention that begins after the first sale is not prevention",
    },
    "post_purchase_clarity": {
        "when": BEFORE,
        "what": "what to do next, how to ask, and from which version the answer comes",
        "ready_when": "the file and the listing both say how to get help",
        "why_not_later": "it is a page and a file, either written or not",
    },
    "rapid_support": {
        "when": DURING,
        "what": "a fast, human answer to the question a buyer actually asked",
        "ready_when": "a measured response time over real cases",
        "why_not_later": ("this one genuinely needs customers: it is a response time, and "
                          "there is nothing to respond to yet"),
    },
}

# The sprint ends. A permanent sprint is how the company works, and calling it a sprint is
# how nobody asks when the extra cost stops.
SPRINT_ENDS_AT_CUSTOMERS = 100

# What the sprint may spend, and the one thing it may not.
MAY_SPEND: tuple[str, ...] = ("support hours", "physical sample costs",
                              "slower release of new products")
MAY_NOT_SPEND: tuple[str, ...] = ("the price",)


class SprintRefused(ValueError):
    """A priority nobody named, or a discount dressed as a trust investment."""


@dataclass(frozen=True)
class Readiness:
    """What is actually true today about the four that do not need a customer."""

    flawless_downloads: bool = False
    truthful_expectations: bool = False
    defect_prevention: bool = False
    post_purchase_clarity: bool = False


def before_the_first_customer(readiness: Readiness) -> dict:
    """The four that are ready or not ready today, and are not waiting for anybody."""
    rows = []
    for key, spec in PRIORITIES.items():
        if spec["when"] != BEFORE:
            continue
        ready = bool(getattr(readiness, key))
        rows.append({"priority": key, "ready": ready, "what": spec["what"],
                     "ready_when": spec["ready_when"],
                     "why_not_later": spec["why_not_later"]})
    outstanding = [r["priority"] for r in rows if not r["ready"]]
    return {
        "priorities": rows,
        "ready": len(rows) - len(outstanding), "of": len(rows),
        "outstanding": outstanding,
        "note": ("all four are done, and they were done before anybody bought anything, "
                 "which is the only time they can be" if not outstanding else
                 f"{outstanding} are not ready. A plan that begins at the first sale lets "
                 f"these sit unfinished while the shop feels prepared, and the first hundred "
                 f"customers each arrive exactly once"),
    }


def status(*, customers: int, readiness: Readiness,
           measured_response_hours: float | None = None) -> dict:
    """Where the sprint stands, including the honest case where it has not started."""
    if customers < 0:
        raise SprintRefused("a negative customer count is not a count")

    before = before_the_first_customer(readiness)
    started = customers > 0
    finished = customers >= SPRINT_ENDS_AT_CUSTOMERS

    support = {
        "measurable": measured_response_hours is not None,
        "measured_response_hours": measured_response_hours,
        "why": ("a response time needs something to respond to"
                if measured_response_hours is None else "measured over real cases"),
    }

    return {
        "customers": customers,
        "started": started,
        "finished": finished,
        "ends_at": SPRINT_ENDS_AT_CUSTOMERS,
        "before_the_first_customer": before,
        "rapid_support": support,
        "may_spend": list(MAY_SPEND),
        "may_not_spend": list(MAY_NOT_SPEND),
        "note": (("the sprint has not started, and four of its five priorities do not need "
                  "it to. They are ready or not ready today")
                 if not started else
                 ("the sprint is over; what these buy afterwards is the ordinary standard"
                  if finished else
                  f"{SPRINT_ENDS_AT_CUSTOMERS - customers} customers left, and each arrives "
                  f"exactly once")),
    }


def check_investment(kind: str, *, is_discount: bool = False) -> dict:
    """Whether this is a trust investment or a discount wearing its clothes.

    "Do not sacrifice contribution irrationally" reads specifically here: a discount during
    the trust sprint teaches the hundred buyers whose repeat behaviour matters most that the
    price is negotiable, and they are precisely the cohort a value ladder depends on.
    """
    if is_discount or kind in MAY_NOT_SPEND:
        return {
            "kind": kind, "allowed": False,
            "why": ("a discount during the trust sprint teaches the hundred buyers whose "
                    "repeat behaviour matters most that the price is negotiable, and they "
                    "are exactly the cohort the value ladder depends on. The sprint spends "
                    "time and prevention, not price"),
        }
    if kind not in MAY_SPEND:
        return {"kind": kind, "allowed": False,
                "why": f"{kind!r} is not something this sprint spends: {list(MAY_SPEND)}"}
    return {"kind": kind, "allowed": True,
            "why": "time and prevention are what early trust is actually made of"}


def state() -> dict:
    """The five priorities, when each happens, and what the sprint may cost."""
    return {
        "priorities": {k: dict(v) for k, v in PRIORITIES.items()},
        "before_the_first_customer": [k for k, v in PRIORITIES.items()
                                      if v["when"] == BEFORE],
        "needs_customers": [k for k, v in PRIORITIES.items() if v["when"] == DURING],
        "ends_at_customers": SPRINT_ENDS_AT_CUSTOMERS,
        "may_spend": list(MAY_SPEND),
        "may_not_spend": list(MAY_NOT_SPEND),
        "note": ("Four of the five priorities happen before the first customer, not during "
                 "the first hundred. A plan that begins at the first sale lets them sit "
                 "unfinished while the shop feels prepared, and each of those hundred "
                 "customers arrives exactly once (#259)."),
    }
