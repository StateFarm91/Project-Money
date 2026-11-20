"""Pods that get better, and the two ways of getting better that pull against each other.

Requirement 226. Every MJs and category pod participates in the continuous-learning
architecture of #177-194: category mistakes, new mechanisms, successful Brambleloop
responses, failed responses, current benchmarks and challenger strategies. *The pod should
become measurably more discerning and creative over time.*

Most of the machinery is already here. `intel.memory` (#316) gives every pod a versioned
lesson store where only an outcome moves a lesson's standing and a contradicted lesson is
superseded rather than deleted; `intel.pods` routes listings to specialists; `improve.league`
runs challengers; `improve.freshness` says how often evidence goes stale. What was missing is
the measurement the requirement's last sentence asks for, and that sentence contains a trap.

**Discerning and creative pull against each other, and one number hides which moved.** A pod
that rejects everything is maximally discerning and contributes nothing. A pod that accepts
everything is maximally generative and worthless. A single "pod quality" score can rise while
either one collapses, and the collapse that gets rewarded is whichever the score happens to
weight. So there are two measures and no function returns one without the other -- the same
structural move `improve.velocity` makes for release counts, and for the same reason.

**Discernment is precision against outcomes, never rejection rate.** The tempting measure is
how much a pod turns down, because it is available immediately and rises when the pod is
being careful. It measures caution. What discernment means is that the things a pod said
would work did, and the things it said would not did not -- which can only be scored after
the outcome arrives, and is therefore the measure nobody reaches for.

**A memory made only of failures teaches caution; one made only of mechanisms teaches
imitation.** The six record kinds the requirement names split cleanly into learning from what
went wrong and learning from what worked, and a pod whose memory has collapsed into one is
drifting somewhere nameable. The balance is reported, and it is reported as a direction
rather than as a target, because there is no correct ratio -- only a pod that has stopped
doing one of them.

Pods are not added to `improve.cells.CELLS`. A department is a function of this company and a
pod is a lens on somebody else's catalogue; putting them in one vocabulary would make
"department" mean two things and quietly double every count computed over it. They
participate through their own curve, on the adversarial freshness clock, which is what
participation in that architecture actually requires.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..improve import freshness
from .pods import POD_KEYS

# The six the requirement names, split by what they teach. Closed: a memory that grows a
# category whenever something does not fit cannot show that its balance changed.
CATEGORY_MISTAKE = "category_mistake"
FAILED_RESPONSE = "failed_response"
NEW_MECHANISM = "new_mechanism"
SUCCESSFUL_RESPONSE = "successful_response"
CURRENT_BENCHMARK = "current_benchmark"
CHALLENGER_STRATEGY = "challenger_strategy"

FROM_FAILURE: tuple[str, ...] = (CATEGORY_MISTAKE, FAILED_RESPONSE)
FROM_SUCCESS: tuple[str, ...] = (NEW_MECHANISM, SUCCESSFUL_RESPONSE, CURRENT_BENCHMARK,
                                 CHALLENGER_STRATEGY)

RECORD_KINDS: dict[str, str] = {
    CATEGORY_MISTAKE: "something this category gets wrong, ours or anybody's",
    FAILED_RESPONSE: "a Brambleloop answer that did not work, and what it cost to find out",
    NEW_MECHANISM: "a way of doing something, seen working, that this shop did not have",
    SUCCESSFUL_RESPONSE: "a Brambleloop answer that worked, with what made it work",
    CURRENT_BENCHMARK: "what the bar is in this category right now",
    CHALLENGER_STRATEGY: "an alternative reading of the same evidence, kept to be tested",
}

# A pod's world moves as fast as somebody else's catalogue, which is the fastest clock
# `improve.freshness` has. Taken from there rather than restated, so the two cannot drift.
POD_WORLD = freshness.ADVERSARIAL
POD_STALE_AFTER_HOURS = freshness.WORLD_SPEED[freshness.ADVERSARIAL][0]

# Judgements needed before precision means anything. Small samples of a rate produce
# confident nonsense, and a pod with four calls has not demonstrated discernment by getting
# three of them right.
MIN_JUDGEMENTS = 12

# Responses needed before an originality share is readable at all.
MIN_RESPONSES = 5

UNMEASURED = "unmeasured"
DRIFTING_CAUTIOUS = "drifting_cautious"
DRIFTING_IMITATIVE = "drifting_imitative"
BALANCED = "balanced"

# How lopsided a memory has to be before it is a direction rather than a week's noise.
DRIFT_SHARE = 0.85


class PodLearningRefused(ValueError):
    """A record kind nobody named, a discernment score from a rejection rate, or a
    capability reported one half at a time."""


@dataclass(frozen=True)
class Record:
    """One thing a pod learned, in one of the six kinds the requirement names."""

    pod: str
    kind: str
    subject: str
    evidence_ref: str
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.pod not in POD_KEYS:
            raise PodLearningRefused(f"{self.pod!r} is not a pod: {sorted(POD_KEYS)}")
        if self.kind not in RECORD_KINDS:
            raise PodLearningRefused(
                f"{self.kind!r} is not a record kind: {sorted(RECORD_KINDS)}. A memory that "
                f"grows a category whenever something does not fit cannot show that its "
                f"balance changed, and the balance is what says which way a pod is drifting")
        if not self.evidence_ref.strip():
            raise PodLearningRefused(
                f"{self.pod}/{self.kind}: name the evidence. A pod memory of things somebody "
                f"remembers is the thing intel.memory already refuses -- repetition without "
                f"an outcome is not learning")

    @property
    def teaches(self) -> str:
        return "failure" if self.kind in FROM_FAILURE else "success"


@dataclass(frozen=True)
class Judgement:
    """A call a pod made, and what later happened. Precision needs both."""

    pod: str
    subject: str
    predicted_worth_doing: bool
    outcome_worked: bool | None = None

    def __post_init__(self) -> None:
        if self.pod not in POD_KEYS:
            raise PodLearningRefused(f"{self.pod!r} is not a pod")

    @property
    def settled(self) -> bool:
        return self.outcome_worked is not None

    @property
    def correct(self) -> bool | None:
        if not self.settled:
            return None
        return self.predicted_worth_doing == self.outcome_worked


def discernment(judgements: list[Judgement]) -> dict:
    """How often a pod's calls were right, scored against outcomes rather than counted.

    The tempting measure is rejection rate: it is available immediately and rises whenever
    the pod is being careful. It measures caution. Discernment is whether the things it said
    would work did, which can only be scored once the outcome arrives -- and is therefore the
    measure nobody reaches for.
    """
    settled = [j for j in judgements if j.settled]
    if len(settled) < MIN_JUDGEMENTS:
        return {
            "reading": UNMEASURED, "settled": len(settled), "needed": MIN_JUDGEMENTS,
            "unsettled": len(judgements) - len(settled),
            "why": (f"{len(settled)} settled call(s) against {MIN_JUDGEMENTS}. A pod with "
                    f"four calls has not demonstrated discernment by getting three of them "
                    f"right, and a rate from a small sample is confident nonsense"),
        }
    correct = sum(1 for j in settled if j.correct)
    said_yes = [j for j in settled if j.predicted_worth_doing]
    said_no = [j for j in settled if not j.predicted_worth_doing]
    return {
        "reading": "measured", "settled": len(settled),
        "precision": round(correct / len(settled), 3),
        "said_worth_doing": len(said_yes),
        "of_those_worked": sum(1 for j in said_yes if j.outcome_worked),
        "said_not_worth_doing": len(said_no),
        "of_those_would_have_worked": sum(1 for j in said_no if j.outcome_worked),
        "why": (f"{correct} of {len(settled)} calls held up against what happened. Both "
                f"directions count: a pod that never says no is not discerning, and one "
                f"whose noes would all have worked is expensive"),
        "not_a_rejection_rate": (
            "rejection rate rises whenever a pod is cautious and is available immediately, "
            "which is why it gets used. It is not this"),
    }


def creativity(responses: list[dict]) -> dict:
    """The share of a pod's answers that were original rather than parity.

    Each response is {"subject": str, "axes": [...]}, where axes come from
    `intel.panel.SUPERIORITY_AXES`. A response whose only axis is parity is a match, and a pod
    that only matches is not becoming more creative however much it learns.
    """
    from .panel import PARITY, SUPERIORITY_AXES

    if len(responses) < MIN_RESPONSES:
        return {"reading": UNMEASURED, "responses": len(responses), "needed": MIN_RESPONSES,
                "why": (f"{len(responses)} response(s) against {MIN_RESPONSES}. An "
                        f"originality share from three answers is a fact about three "
                        f"answers")}
    original = []
    matched = []
    for r in responses:
        axes = {a for a in (r.get("axes") or []) if a in SUPERIORITY_AXES and a != PARITY}
        (original if axes else matched).append(r.get("subject", ""))
    share = len(original) / len(responses)
    return {
        "reading": "measured", "responses": len(responses),
        "original": len(original), "parity_only": len(matched),
        "original_share": round(share, 3),
        "why": (f"{len(original)} of {len(responses)} answers offered something beyond "
                f"matching. A pod that only matches is not becoming more creative however "
                f"much it learns, and #227 refuses parity as a reason to ship at all"),
    }


def balance(records: list[Record]) -> dict:
    """Which way a pod's memory is leaning, reported as a direction rather than a target."""
    if not records:
        return {"reading": UNMEASURED, "records": 0,
                "why": "no records. A pod with no memory is not drifting, it is empty"}
    failure = sum(1 for r in records if r.teaches == "failure")
    success = len(records) - failure
    share_failure = failure / len(records)

    if share_failure >= DRIFT_SHARE:
        state, why = DRIFTING_CAUTIOUS, (
            f"{failure} of {len(records)} records are mistakes and failed responses. A "
            f"memory made only of failures teaches caution, and a cautious specialist stops "
            f"finding things")
    elif share_failure <= 1 - DRIFT_SHARE:
        state, why = DRIFTING_IMITATIVE, (
            f"{success} of {len(records)} records are mechanisms, benchmarks and wins. A "
            f"memory made only of what worked elsewhere teaches imitation, which is #227's "
            f"failure arriving through the learning system rather than through a decision")
    else:
        state, why = BALANCED, (
            f"{failure} from failure and {success} from success. There is no correct ratio "
            f"here -- only a pod that has stopped doing one of them")

    return {
        "reading": state, "records": len(records),
        "from_failure": failure, "from_success": success,
        "failure_share": round(share_failure, 3),
        "by_kind": {k: sum(1 for r in records if r.kind == k)
                    for k in RECORD_KINDS if any(r.kind == k for r in records)},
        "why": why,
    }


def capability(pod: str, *, judgements: list[Judgement], responses: list[dict],
               records: list[Record]) -> dict:
    """A pod's capability, which is never one number.

    There is no function here that returns discernment without creativity. A single score can
    rise while either collapses, and the one that collapses is whichever the score happens to
    weight least -- which is exactly how a pod becomes very good at saying no.
    """
    if pod not in POD_KEYS:
        raise PodLearningRefused(f"{pod!r} is not a pod: {sorted(POD_KEYS)}")
    d = discernment([j for j in judgements if j.pod == pod])
    c = creativity(responses)
    b = balance([r for r in records if r.pod == pod])
    measured = d["reading"] == "measured" and c["reading"] == "measured"
    return {
        "pod": pod,
        "discernment": d, "creativity": c, "memory_balance": b,
        "measured": measured,
        "stale_after_hours": POD_STALE_AFTER_HOURS,
        "world": POD_WORLD,
        "why": ("both halves measured" if measured else
                "at least one half is unmeasured, and an unmeasured half is not a passing "
                "half"),
        "never_one_number": (
            "discerning and creative pull against each other: a pod that rejects everything "
            "is maximally discerning and contributes nothing, and one that accepts "
            "everything is generative and worthless. A single score can rise while either "
            "collapses"),
    }


def state() -> dict:
    """How pods participate in the continuous-learning architecture, and why not as cells."""
    return {
        "requirement": 226,
        "record_kinds": dict(RECORD_KINDS),
        "from_failure": list(FROM_FAILURE),
        "from_success": list(FROM_SUCCESS),
        "pods": sorted(POD_KEYS),
        "world": POD_WORLD,
        "stale_after_hours": POD_STALE_AFTER_HOURS,
        "min_judgements": MIN_JUDGEMENTS,
        "min_responses": MIN_RESPONSES,
        "builds_on": {
            "intel.memory": "the versioned lesson store where only an outcome moves standing",
            "intel.pods": "routing a listing to the specialist that answers for it",
            "improve.freshness": "the adversarial clock, taken from there rather than restated",
            "improve.league": "challenger strategies, evaluated rather than collected",
            "intel.panel": "what counts as an original response rather than a match",
        },
        "not_a_department": (
            "pods are deliberately not added to improve.cells.CELLS. A department is a "
            "function of this company and a pod is a lens on somebody else's catalogue; one "
            "vocabulary for both would make 'department' mean two things and quietly double "
            "every count computed over it"),
        "refuses": [
            "a record kind outside the six the requirement names",
            "a record with no evidence behind it",
            "a discernment reading from fewer than twelve settled calls",
            "an originality share from fewer than five responses",
            "a capability report with one half of the pair missing",
        ],
        "note": ("discernment is precision against outcomes, never rejection rate. Rejection "
                 "rate is available immediately and rises whenever a pod is being careful, "
                 "which is why it gets used, and what it measures is caution"),
    }
