"""The buyer's journey, audited where the confusion is made rather than where it lands.

Requirement 261. Audit the journey from Etsy search through the listing, the download and
support; find confusion about "pattern vs finished item", file access, terminology, skill,
sizing and included deliverables; fix recurring friction in the listing and the packaging.

Two things about that sentence decide the whole module.

**The stage a confusion surfaces at is almost never the stage that caused it.** A refund
request that says "I thought I was buying the blanket" arrives at support, and a friction
audit that groups by where things arrive will file it under support and produce a better
support macro. The macro works: the buyer is refunded politely and quickly, the queue metric
improves, and the listing goes on saying the same thing to the next four hundred people. So
every friction here carries two stages -- where it *surfaced* and where it was *caused* --
and the fix is always applied at the cause. Grouping by surface is how a shop gets good at
absorbing a defect instead of removing it.

**A journey nobody walked audits clean.** Counting confusion reports and finding none is the
same evidence for a flawless funnel and for an empty one, and the second is this shop's
actual situation today. So a stage is `clean` only with positive evidence that somebody
traversed it; with no traversals it is `not_yet_walked`, which is a different word on purpose
and which `overall()` will not pass.

What follows from those two is the split this build keeps arriving at: most of this audit is
runnable today. Five of the six confusions the spec names are *created in the listing copy*,
which exists before any buyer does, and can be checked against the artefact deterministically.
`commerce.seo.build_description` already writes a description that satisfies them -- but the
audit reads the listing that is actually up rather than trusting the generator that made it,
because a description can be hand-edited, imported, or written before a rule existed, and an
auditor that asks the generator is asking the defendant.

The remaining half needs a published listing and a real buyer, and is parked there honestly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---- the journey ----------------------------------------------------------

SEARCH = "search"
LISTING = "listing"
DECISION = "decision"
CHECKOUT = "checkout"
DELIVERY = "delivery"
FIRST_USE = "first_use"
SUPPORT = "support"

STAGES: tuple[str, ...] = (SEARCH, LISTING, DECISION, CHECKOUT, DELIVERY, FIRST_USE, SUPPORT)

STAGE_MEANS: dict[str, str] = {
    SEARCH: "a maker sees the thumbnail and title among other results",
    LISTING: "they open the listing and read what this is",
    DECISION: "they decide to buy, or leave",
    CHECKOUT: "Etsy takes the payment -- a path this company does not own",
    DELIVERY: "the digital download reaches them",
    FIRST_USE: "they open the PDF and try to work the first rows",
    SUPPORT: "they ask a question or ask for their money back",
}

# Which stages this company can change. Checkout is Etsy's: friction found there is real and
# reportable, and naming it as ours would produce a fix nobody can ship.
OURS: frozenset[str] = frozenset({SEARCH, LISTING, DECISION, DELIVERY, FIRST_USE, SUPPORT})


# ---- what goes wrong ------------------------------------------------------

# A correctness friction is a thing that is broken; one instance is proof. A comprehension
# friction is a thing that was understood differently than it was meant; one instance is a
# person, and people differ. The two need opposite thresholds, and a single threshold applied
# to both either drowns the shop in single anecdotes or lets a dead download link wait for a
# second complaint.
CORRECTNESS = "correctness"
COMPREHENSION = "comprehension"

CONFUSIONS: dict[str, dict] = {
    "pattern_vs_finished_item": {
        "kind": COMPREHENSION, "caused_at": LISTING,
        "why": ("the most expensive one in this shop: it produces a refund and a one-star "
                "review together, and the buyer is not wrong -- they were sold something "
                "they did not believe they were buying"),
    },
    "file_access": {
        "kind": CORRECTNESS, "caused_at": DELIVERY,
        "why": "they paid and cannot open what they paid for",
    },
    "terminology": {
        "kind": COMPREHENSION, "caused_at": LISTING,
        "why": ("UK and US terms name different stitches with the same words. A maker who "
                "does not know which set a pattern uses will work the wrong stitch "
                "confidently for forty rows"),
    },
    "skill_level": {
        "kind": COMPREHENSION, "caused_at": LISTING,
        "why": "they bought something they cannot make yet, and blame the pattern",
    },
    "sizing": {
        "kind": COMPREHENSION, "caused_at": LISTING,
        "why": "the finished thing is not the size they pictured",
    },
    "included_deliverables": {
        "kind": COMPREHENSION, "caused_at": LISTING,
        "why": "they expected a chart, a video or a size range that was never offered",
    },
}


class FrictionRefused(ValueError):
    """An audit that would state more than its evidence supports."""


# ---- the deterministic half: the listing, today ---------------------------

# Each of the five listing-caused confusions is answered by something the copy either says or
# does not. These patterns look for the answer, not for the words a good listing tends to
# contain: "digital" alone appears in "digital download" and in "digital art", and a listing
# that says it is a digital download of a finished blanket is exactly the failure.
_ANSWERED_BY: dict[str, re.Pattern] = {
    "pattern_vs_finished_item": re.compile(
        r"(crochet\s+)?pattern,?\s+not\s+a\s+finished|not\s+a\s+finished\s+(item|product|"
        r"blanket|toy)|pattern\s+only\b", re.I),
    "terminology": re.compile(r"\b(US|UK|American|British)\s+(crochet\s+)?terms?\b", re.I),
    "skill_level": re.compile(r"\b(difficulty|skill\s+level)\b\s*[:\-]", re.I),
    "sizing": re.compile(r"\bfinished\s+size\b|\bmeasures\s+approximately\b", re.I),
    "included_deliverables": re.compile(r"\bwhat\s+you\s+get\b|\byou\s+(will\s+)?receive\b",
                                        re.I),
}

# Where the pattern-vs-item answer has to appear. Etsy truncates the description on a phone
# at roughly this point, and an answer below the fold is an answer the confused buyer never
# read. Measured against the shop's own generated copy, which puts it in the first sentence.
ABOVE_THE_FOLD_CHARS = 160


def listing_audit(*, title: str, description: str) -> dict:
    """The five listing-caused confusions, checked against the listing as it stands.

    No buyer is required and none is credited: this is a reading of an artefact, and it says
    so. It is the half of the audit that is available on day zero, which is the half worth
    having, because every buyer who is ever confused by this listing is confused by the
    version that was up when they arrived.
    """
    if not description.strip():
        raise FrictionRefused(
            "a listing with no description cannot be audited into being clear. An empty "
            "description answers none of the six questions and passing it would be the "
            "absence-of-failure verdict this build keeps removing")

    answered: dict[str, bool] = {}
    for confusion, pattern in _ANSWERED_BY.items():
        answered[confusion] = bool(pattern.search(description))

    head = description[:ABOVE_THE_FOLD_CHARS]
    in_title = bool(_ANSWERED_BY["pattern_vs_finished_item"].search(title)
                    or re.search(r"\bcrochet\s+pattern\b", title, re.I))
    above_fold = bool(_ANSWERED_BY["pattern_vs_finished_item"].search(head))

    defects: list[dict] = []
    for confusion, ok in sorted(answered.items()):
        if not ok:
            defects.append({
                "confusion": confusion, "stage": LISTING,
                "kind": CONFUSIONS[confusion]["kind"],
                "why": CONFUSIONS[confusion]["why"],
                "fix": "answer it in the description before anybody has to ask",
            })
    if answered["pattern_vs_finished_item"] and not (in_title and above_fold):
        defects.append({
            "confusion": "pattern_vs_finished_item", "stage": LISTING,
            "kind": COMPREHENSION,
            "why": (f"the description says so, but not in the title and not within the first "
                    f"{ABOVE_THE_FOLD_CHARS} characters. A buyer who is going to make this "
                    f"mistake makes it from the search result and the top of the page; the "
                    f"paragraph that would have corrected them is the one they did not open"),
            "fix": "say it in the title and in the first sentence",
        })

    return {
        "answered": answered, "defects": defects,
        "clear": not defects,
        "evidence": "the listing artefact",
        "note": ("read from the listing rather than from the generator that wrote it: copy "
                 "can be edited after it is built, and asking the generator whether its "
                 "output is correct is asking the defendant"),
    }


# ---- the evidenced half: what buyers actually did -------------------------

@dataclass(frozen=True)
class Friction:
    """One thing that went wrong for one buyer, with both of its stages."""

    confusion: str
    surfaced_at: str
    order_ref: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.confusion not in CONFUSIONS:
            raise FrictionRefused(
                f"{self.confusion!r} is not one of the confusions this audit tracks: "
                f"{sorted(CONFUSIONS)}. Free-text friction cannot be counted, and a category "
                f"that grows every week cannot show that anything is improving")
        if self.surfaced_at not in STAGES:
            raise FrictionRefused(f"{self.surfaced_at!r} is not a journey stage: {STAGES}")
        if not self.order_ref.strip():
            raise FrictionRefused(
                "friction with no order behind it is a worry, not an observation")

    @property
    def caused_at(self) -> str:
        return CONFUSIONS[self.confusion]["caused_at"]

    @property
    def kind(self) -> str:
        return CONFUSIONS[self.confusion]["kind"]


@dataclass(frozen=True)
class Traversal:
    """Evidence that somebody walked a stage. Without these, silence proves nothing."""

    stage: str
    count: int

    def __post_init__(self) -> None:
        if self.stage not in STAGES:
            raise FrictionRefused(f"{self.stage!r} is not a journey stage: {STAGES}")
        if self.count < 0:
            raise FrictionRefused("a negative traversal count is not a measurement")


# A comprehension friction becomes actionable on a rate, not a count: two in five buyers is
# an emergency and two in four hundred is two people. Below the minimum exposure the rate is
# not readable at all, which is `unmeasured` rather than `clean`.
MIN_EXPOSURE = 20
COMPREHENSION_RATE_FLOOR = 0.02
COMPREHENSION_MIN_OCCURRENCES = 2

CLEAN = "clean"
FRICTION_FOUND = "friction"
UNMEASURED = "unmeasured"
NOT_YET_WALKED = "not_yet_walked"


def audit(frictions: list[Friction], traversals: list[Traversal]) -> dict:
    """Per-stage verdicts, with friction attributed to the stage that caused it."""
    walked: dict[str, int] = {stage: 0 for stage in STAGES}
    for t in traversals:
        walked[t.stage] += t.count

    by_cause: dict[str, list[Friction]] = {stage: [] for stage in STAGES}
    for f in frictions:
        by_cause[f.caused_at].append(f)
        if f.caused_at != f.surfaced_at and walked[f.surfaced_at] == 0:
            # Somebody reached that stage in order to be confused at it. Not counting it is
            # how a stage stays "never walked" while it is visibly producing complaints.
            walked[f.surfaced_at] += 1

    stages: dict[str, dict] = {}
    actionable: list[dict] = []
    for stage in STAGES:
        exposure = walked[stage]
        here = by_cause[stage]
        counts: dict[str, int] = {}
        for f in here:
            counts[f.confusion] = counts.get(f.confusion, 0) + 1

        raised: list[dict] = []
        for confusion, n in sorted(counts.items()):
            spec = CONFUSIONS[confusion]
            if spec["kind"] == CORRECTNESS:
                raised.append({"confusion": confusion, "occurrences": n, "kind": CORRECTNESS,
                               "act": True,
                               "why": ("a correctness defect is proved by one instance: "
                                       "nobody's second complaint makes a dead file deader")})
                continue
            rate = (n / exposure) if exposure else None
            enough = (exposure >= MIN_EXPOSURE
                      and n >= COMPREHENSION_MIN_OCCURRENCES
                      and rate is not None and rate >= COMPREHENSION_RATE_FLOOR)
            raised.append({
                "confusion": confusion, "occurrences": n, "kind": COMPREHENSION,
                "rate": None if rate is None else round(rate, 4),
                "exposure": exposure, "act": enough,
                "why": ("recurring at a rate worth changing the listing for" if enough else
                        f"not yet separable from individual variation: {n} of {exposure}, "
                        f"and this threshold needs {COMPREHENSION_MIN_OCCURRENCES} "
                        f"occurrences at {COMPREHENSION_RATE_FLOOR:.0%} of at least "
                        f"{MIN_EXPOSURE} buyers"),
            })

        if any(r["act"] for r in raised):
            verdict = FRICTION_FOUND
        elif exposure == 0:
            verdict = NOT_YET_WALKED
        elif exposure < MIN_EXPOSURE:
            verdict = UNMEASURED
        else:
            verdict = CLEAN

        stages[stage] = {
            "stage": stage, "means": STAGE_MEANS[stage], "verdict": verdict,
            "exposure": exposure, "ours": stage in OURS, "raised": raised,
        }
        for r in raised:
            if r["act"]:
                actionable.append({**r, "fix_at": stage, "ours": stage in OURS,
                                   "surfaced_at": sorted({f.surfaced_at for f in here
                                                          if f.confusion == r["confusion"]})})

    return {
        "stages": stages, "actionable": actionable,
        "walked": sum(1 for s in STAGES if walked[s] > 0), "of": len(STAGES),
        "note": ("friction is filed at the stage that caused it, not the stage it arrived "
                 "at. Support is where most of it arrives and almost none of it is made"),
    }


def overall(report: dict) -> dict:
    """One verdict for the journey, which cannot be a pass over stages nobody walked."""
    stages = report["stages"]
    unwalked = sorted(s for s, v in stages.items() if v["verdict"] == NOT_YET_WALKED)
    unmeasured = sorted(s for s, v in stages.items() if v["verdict"] == UNMEASURED)
    with_friction = sorted(s for s, v in stages.items() if v["verdict"] == FRICTION_FOUND)

    if with_friction:
        verdict, why = FRICTION_FOUND, (
            f"friction to fix at: {', '.join(with_friction)}")
    elif unwalked:
        verdict, why = NOT_YET_WALKED, (
            f"no evidence anybody traversed {', '.join(unwalked)}. Zero complaints from zero "
            f"buyers is the same reading as a flawless funnel, and this shop is the first "
            f"case, so the audit says so rather than passing")
    elif unmeasured:
        verdict, why = UNMEASURED, (
            f"walked but below the readable threshold at: {', '.join(unmeasured)}")
    else:
        verdict, why = CLEAN, "every stage walked, measured and quiet"

    return {"verdict": verdict, "why": why, "passes": verdict == CLEAN,
            "not_yet_walked": unwalked, "unmeasured": unmeasured,
            "friction_at": with_friction}


def state() -> dict:
    """What this audit can see today, and what it is waiting for."""
    return {
        "requirement": 261,
        "available_now": {
            "listing_audit": ("the five listing-caused confusions, read from the listing "
                              "artefact. No buyer required"),
        },
        "needs_a_published_listing": [SEARCH, DECISION],
        "needs_a_real_buyer": [CHECKOUT, DELIVERY, FIRST_USE, SUPPORT],
        "blind_spot": ("everyone who left without buying. Their friction is the friction "
                       "that costs the most and this instrument cannot see any of it: every "
                       "stage below DECISION is measured from people who got past it"),
        "note": ("the pre-buyer half is not a smaller version of the audit -- it is the "
                 "half that is still true for every buyer who has not arrived yet"),
    }
