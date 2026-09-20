"""Free tools that answer before they ask, and the flow that cannot claim what it did.

Requirements 255 and 251.

**#255.** A free tool attracts makers with high intent because it is useful, and the failure
is specific and common: the tool that withholds its answer until somebody hands over an email
address. That is not a useful standalone utility with a path to a product; it is a lead
capture form wearing a calculator's name, and the maker who wanted the number leaves knowing
this shop asks for things before it gives them. So every tool here answers first. An address
may be asked for afterwards, to save the answer or to send the pattern it points at, and
never as the price of the answer.

The second finding is more useful than the module. Four of the six tools the requirement
names are arithmetic this system already does -- the twin computes yardage per colour, the
lead-time engine computes make time and what date a maker must start by, the compiler and the
twin between them compute finished size from gauge, and the seasonal calendar computes the
last practical make date for an occasion. None of them is missing. What is missing is a
surface to put them on, which is one owner action rather than four engineering ones, and this
module says which is which rather than proposing to build the calculators again.

**#251.** Lifecycle flows over a consented list, and the requirement's own instruction:
*track incremental contribution, not open rate vanity.* Both halves matter and the second is
the structural one. There is no open-rate field here and no function returns one, because an
open is not a business outcome and has not been a reliable signal of anything since mail
clients began fetching images on the reader's behalf -- a flow judged on opens is optimised
toward subject lines and away from the purchase.

Incremental contribution has a harder condition, and it is the one every lifecycle programme
skips. A flow sent to everybody measures the people who were going to buy anyway. Without a
holdout there is no incremental anything, and `growth.experiments` already says so and
already refuses, so the claim is checked there rather than restated here.

Every send goes through `growth.owned`'s CASL gate, and the frequency cap is enforced on the
recipient rather than on the flow: five flows that each send politely once a week send five
times a week to the person who is in all five.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..growth.experiments import CAUSAL_DESIGNS
from . import owned

# The six tools the requirement names, and -- the point of the table -- where the arithmetic
# for each already lives. "Build" here mostly means "expose".
TOOLS: dict[str, dict] = {
    "yardage_helper": {
        "answers": "how much yarn this project needs, per colour",
        "computed_by": "cir.twin._yardage, which the digital twin already runs per release",
        "exists": True,
    },
    "size_calculator": {
        "answers": "what finished size a given gauge produces, and what gauge a size needs",
        "computed_by": "cir.compiler and cir.twin, from the declared gauge",
        "exists": True,
    },
    "project_time_estimator": {
        "answers": "how long this will take at a maker's own pace",
        "computed_by": "seasonal.leadtime.effective_make_days",
        "exists": True,
    },
    "seasonal_make_time_planner": {
        "answers": "the last day to start if it has to be finished for an occasion",
        "computed_by": "seasonal.calendar's last_practical_make_date milestone",
        "exists": True,
    },
    "colour_planner": {
        "answers": "which colourways hold their contrast in this stitch",
        "computed_by": "publish.substitution.colourway, on perceived lightness",
        "exists": True,
    },
    "motif_preview": {
        "answers": "what a motif looks like worked in a chosen palette",
        "computed_by": "nothing yet: rendering a motif needs the visual pipeline",
        "exists": False,
    },
}

# The lifecycle flows the requirement names.
FLOWS: dict[str, str] = {
    "welcome": "what this shop is for, and one useful thing immediately",
    "category_interest": "more of the department they demonstrated interest in",
    "launch": "a new pattern, to the people whose interest it matches",
    "post_purchase_support": "how to get help, before they need to ask for it",
    "cross_sell": "the pattern that goes with the one they made",
    "seasonal_reactivation": "the occasion is coming and they made something for it before",
}

# What may never be reported as this programme's performance. Structural rather than
# discouraged: no function here returns any of them.
NEVER_REPORTED_AS_PERFORMANCE: tuple[str, ...] = (
    "open_rate", "opens", "click_rate_without_a_holdout", "list_size")

# Sends per recipient per week, counted on the person rather than on the flow.
MAX_SENDS_PER_WEEK = 2

# What a segment may be built from: something the subscriber did or said.
SEGMENT_EVIDENCE: tuple[str, ...] = ("purchase", "download", "stated_preference", "enquiry")


class ToolRefused(ValueError):
    """A tool that asks before it answers, or a flow that claims what it cannot."""


@dataclass(frozen=True)
class Tool:
    """One free utility, and what it asks of the person using it."""

    key: str
    asks_for_email_before_answering: bool = False
    leads_to: str = ""
    why_next: str = ""

    def __post_init__(self) -> None:
        if self.key not in TOOLS:
            raise ToolRefused(f"{self.key!r} is not a tool: {sorted(TOOLS)}")


def check_tool(tool: Tool) -> dict:
    """Whether this tool is useful standalone and points somewhere."""
    spec = TOOLS[tool.key]
    reasons: list[str] = []

    if tool.asks_for_email_before_answering:
        reasons.append(
            "it asks for an address before it answers. That is a lead capture form wearing a "
            "calculator's name, and the maker who wanted the number leaves knowing this shop "
            "asks for things before it gives them")
    if not tool.leads_to.strip():
        reasons.append("no product named. A tool with no path to anything is a gift, which "
                       "is a fine thing and is not this requirement")
    if len(tool.why_next.split()) < 5:
        reasons.append("no stated reason somebody who just got their answer would want that "
                       "product")

    return {
        "tool": tool.key, "ok": not reasons, "reasons": reasons,
        "answers": spec["answers"],
        "computed_by": spec["computed_by"],
        "already_exists": spec["exists"],
        "email_after_the_answer_is_fine": (
            "an address may be asked for after the answer, to save it or to send the pattern "
            "it points at -- never as the price of it"),
    }


def inventory() -> dict:
    """Which tools are arithmetic this system already does, and which need building."""
    exists = [k for k, v in TOOLS.items() if v["exists"]]
    missing = [k for k, v in TOOLS.items() if not v["exists"]]
    return {
        "already_computed": exists,
        "needs_building": missing,
        "note": (f"{len(exists)} of {len(TOOLS)} are arithmetic this system already runs on "
                 f"every release. What is missing is a surface to put them on, which is one "
                 f"owner action rather than {len(exists)} engineering ones"),
    }


@dataclass(frozen=True)
class Flow:
    """One lifecycle flow, its basis for sending, and how its effect will be read."""

    key: str
    segment_evidence: str
    design: str = ""              # the experiment design behind any contribution claim

    def __post_init__(self) -> None:
        if self.key not in FLOWS:
            raise ToolRefused(f"{self.key!r} is not a flow: {sorted(FLOWS)}")
        if self.segment_evidence not in SEGMENT_EVIDENCE:
            raise ToolRefused(
                f"{self.segment_evidence!r} is not evidence of interest: "
                f"{list(SEGMENT_EVIDENCE)}. A segment built on an open is a segment built on "
                f"whether somebody's mail client fetched an image")


def check_flow(flow: Flow) -> dict:
    """Whether this flow may claim a contribution, and what it may claim without a holdout."""
    reasons: list[str] = []
    causal = flow.design in CAUSAL_DESIGNS
    if not causal:
        reasons.append(
            f"design {flow.design or 'none'} is not one that supports a causal claim. A flow "
            f"sent to everybody measures the people who were going to buy anyway, so without "
            f"a holdout there is no incremental anything")

    return {
        "flow": flow.key, "what": FLOWS[flow.key],
        "segment_evidence": flow.segment_evidence,
        "may_claim_contribution": causal,
        "reasons": reasons,
        "never_reported": list(NEVER_REPORTED_AS_PERFORMANCE),
        "note": ("an association, which is worth recording and is not a contribution"
                 if not causal else "a holdout is in place, so the difference is the flow's"),
    }


def frequency(recipient_sends: dict[str, int]) -> dict:
    """Who is being written to too often, counted on the person rather than the flow.

    Five flows that each send politely once a week send five times a week to the person who
    is in all five, and every flow's own report looks reasonable.
    """
    over = {ref: n for ref, n in sorted(recipient_sends.items()) if n > MAX_SENDS_PER_WEEK}
    return {
        "cap_per_week": MAX_SENDS_PER_WEEK,
        "over_cap": over,
        "ok": not over,
        "why": ("the cap is on the person. Each flow's own report looks reasonable, and the "
                "person in all five gets five" if over else "nobody is over the cap"),
    }


def may_send(consent: owned.Consent, message: dict, *, today: date | None = None) -> dict:
    """Every send goes through the CASL gate, which is not restated here."""
    return owned.send_gate(consent, message, today)


def state() -> dict:
    """The tools, the flows, and the number this programme refuses to be judged on."""
    return {
        "tools": {k: dict(v) for k, v in TOOLS.items()},
        "inventory": inventory(),
        "flows": dict(FLOWS),
        "segment_evidence": list(SEGMENT_EVIDENCE),
        "never_reported_as_performance": list(NEVER_REPORTED_AS_PERFORMANCE),
        "max_sends_per_week": MAX_SENDS_PER_WEEK,
        "consent": ("growth.owned's CASL gate, which decides every send. Consent is not "
                    "restated here"),
        "note": ("A tool that withholds its answer until somebody hands over an address is a "
                 "lead capture form wearing a calculator's name. And there is no open rate "
                 "here: an open is not a business outcome, and a flow judged on opens is "
                 "optimised toward subject lines and away from the purchase (#255, #251)."),
    }
