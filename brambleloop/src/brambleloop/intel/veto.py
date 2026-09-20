"""The owner's veto, and the feedback that usually evaporates.

Requirement 228. Until automated creative evaluation has demonstrated reliable alignment with
the owner's standards, the owner retains veto over canonical model identity and flagship
creative quality. Repeated veto reasons become structured training and evaluation evidence
for the Improvement Department rather than disappearing as chat feedback.

The second sentence is the requirement. A veto is easy: somebody says no and the thing does
not ship. What is hard is that the *reason* almost always evaporates -- it arrives as a
sentence in a conversation, it is acted on once, and six months later nobody can say whether
the same objection has been raised eleven times or once. An evaluator that could have been
trained on eleven instances of one objection was instead trained on nothing, and the owner
goes on making the same call by hand, which is precisely the state this requirement wants to
leave.

So three things.

**A veto carries a reason from a closed vocabulary, or it is not recorded.** Free text cannot
be counted, and counting is the whole point: the eleventh instance of one objection is a
finding and eleven unique sentences are a mood. The vocabulary is small and about *what was
wrong*, not about how it felt.

**The third repetition is a finding about the evaluator, not about the product.** One veto is
a product that missed. Three of the same reason is an automated evaluation that does not
know what the owner means by that word, and the fix is upstream of the product that happened
to arrive third.

**The veto cannot be retired by the system claiming alignment.** "Until automated evaluation
has demonstrated reliable alignment" is a demonstration, and the only demonstration that
counts is agreement over decisions the evaluator called *before* the owner did -- predicted,
then compared. An evaluator scored on decisions it saw the answer to first has demonstrated
nothing, and it is the natural way to build it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# What the owner keeps a veto over, per the requirement. Closed: a veto that can reach
# anything is not a veto over flagship creative, it is an approval step on everything.
IDENTITY = "canonical_model_identity"
FLAGSHIP_CREATIVE = "flagship_creative_quality"

VETO_SCOPE: dict[str, str] = {
    IDENTITY: "who the canonical model is -- frozen under #200 and not redesignable",
    FLAGSHIP_CREATIVE: "the creative on the products that say what this shop is worth",
}

# Why something was vetoed. Small and about what was wrong rather than how it felt, because
# free text cannot be counted and counting is the point.
REASONS: dict[str, str] = {
    "off_identity": "it is not her -- face, hair, age or styling has drifted",
    "generic": "it could be any shop's, which is the one thing a flagship may not be",
    "uncanny": "something in it reads as synthetic and a buyer will see it too",
    "wrong_register": "it is well made and it is not what this shop sounds like",
    "technically_wrong": "it depicts something the pattern does not produce",
    "weak_composition": "it does not hold together at the size it will be seen at",
    "over_processed": "the polish has eaten the thing that was good about it",
}

# How many times one reason must recur before it is a finding about the evaluator.
REPETITION_IS_A_FINDING = 3

# How many predictions an evaluator needs before its agreement rate means anything, and how
# well it has to agree. Both deliberately demanding: the veto is the owner's and handing it
# to a model early costs more than keeping it late.
MIN_PREDICTIONS = 30
REQUIRED_AGREEMENT = 0.90


class VetoRefused(ValueError):
    """A veto with no countable reason, or an evaluator graded on answers it had seen."""


@dataclass(frozen=True)
class Veto:
    """One owner refusal, recorded so that the reason outlives the conversation."""

    subject_ref: str
    scope: str
    reason: str
    note: str = ""
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.scope not in VETO_SCOPE:
            raise VetoRefused(
                f"{self.scope!r} is not within the owner's veto: {sorted(VETO_SCOPE)}. A "
                f"veto that can reach anything is an approval step on everything, which is "
                f"not what this requirement grants")
        if self.reason not in REASONS:
            raise VetoRefused(
                f"{self.reason!r} is not a recorded reason: {sorted(REASONS)}. Free text "
                f"cannot be counted, and counting is the whole point -- the eleventh "
                f"instance of one objection is a finding and eleven unique sentences are a "
                f"mood")

    def to_dict(self) -> dict:
        return {"subject_ref": self.subject_ref, "scope": self.scope,
                "reason": self.reason, "means": REASONS[self.reason],
                "note": self.note, "at": self.at.isoformat()}


def memory(vetoes: list[Veto]) -> dict:
    """What the vetoes add up to, which is the thing chat feedback never does."""
    counts: dict[str, int] = {}
    for v in vetoes:
        counts[v.reason] = counts.get(v.reason, 0) + 1

    findings = []
    for reason, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if count >= REPETITION_IS_A_FINDING:
            findings.append({
                "reason": reason, "count": count, "means": REASONS[reason],
                "finding": "about the evaluator, not about the products",
                "why": (f"{count} products were refused for {reason!r}. One veto is a "
                        f"product that missed; {REPETITION_IS_A_FINDING} of the same reason "
                        f"is an automated evaluation that does not know what the owner means "
                        f"by that word, and the fix is upstream of whichever product "
                        f"happened to arrive third"),
            })

    return {
        "vetoes": len(vetoes),
        "by_reason": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "findings": findings,
        "unrepeated": sorted(r for r, c in counts.items()
                             if c < REPETITION_IS_A_FINDING),
        "why": ("repeated reasons are training evidence for the Improvement Department "
                "rather than chat feedback that is acted on once and then evaporates"),
    }


# ---- retiring the veto -----------------------------------------------------

@dataclass(frozen=True)
class Prediction:
    """What the evaluator said *before* the owner ruled, and what the owner then said."""

    subject_ref: str
    predicted_veto: bool
    owner_vetoed: bool
    predicted_at: datetime
    owner_ruled_at: datetime

    def __post_init__(self) -> None:
        if self.predicted_at >= self.owner_ruled_at:
            raise VetoRefused(
                f"{self.subject_ref}: the prediction is dated at or after the owner's "
                f"ruling. An evaluator scored on decisions it saw the answer to first has "
                f"demonstrated nothing, and building it that way is the natural mistake -- "
                f"the owner's rulings are the easiest training data to hand")

    @property
    def agreed(self) -> bool:
        return self.predicted_veto == self.owner_vetoed


HELD = "held_by_owner"
RETIRED = "retired_to_evaluator"


def alignment(predictions: list[Prediction]) -> dict:
    """Whether automated evaluation has demonstrated the alignment #228 requires.

    There is no argument this function accepts that retires the veto. It counts predictions
    made ahead of the owner's ruling and compares.
    """
    if len(predictions) < MIN_PREDICTIONS:
        return {
            "state": HELD, "predictions": len(predictions), "needed": MIN_PREDICTIONS,
            "why": (f"{len(predictions)} prediction(s) against {MIN_PREDICTIONS}. Agreement "
                    f"on a handful is agreement about a handful, and the veto is the "
                    f"owner's until a demonstration exists rather than until one is claimed"),
        }
    agreed = sum(1 for p in predictions if p.agreed)
    rate = agreed / len(predictions)
    # False confidence is the asymmetric error: an evaluator that misses vetoes ships things
    # the owner would have refused, and one that over-vetoes only wastes work.
    missed = [p for p in predictions if p.owner_vetoed and not p.predicted_veto]
    if rate >= REQUIRED_AGREEMENT and not missed:
        return {"state": RETIRED, "predictions": len(predictions),
                "agreement": round(rate, 3), "missed_vetoes": 0,
                # Reported on both paths so a caller never has to branch to find out, and
                # so that zero is stated rather than inferred from a key being absent.
                "over_vetoes": sum(1 for p in predictions
                                   if p.predicted_veto and not p.owner_vetoed),
                "why": (f"{agreed} of {len(predictions)} agreed, at or above "
                        f"{REQUIRED_AGREEMENT:.0%}, with nothing the owner refused that the "
                        f"evaluator would have passed")}
    return {
        "state": HELD, "predictions": len(predictions), "agreement": round(rate, 3),
        "missed_vetoes": len(missed),
        "over_vetoes": sum(1 for p in predictions
                           if p.predicted_veto and not p.owner_vetoed),
        "why": (f"{agreed} of {len(predictions)} agreed"
                + (f", and {len(missed)} thing(s) the owner refused would have shipped. That "
                   f"error is the asymmetric one: over-vetoing wastes work and missing a "
                   f"veto ships what the owner would have refused"
                   if missed else
                   f", below the {REQUIRED_AGREEMENT:.0%} required")),
    }


def state() -> dict:
    """What the owner keeps, and what would be required to hand it over."""
    return {
        "requirement": 228,
        "scope": dict(VETO_SCOPE),
        "reasons": dict(REASONS),
        "repetition_is_a_finding": REPETITION_IS_A_FINDING,
        "retirement": {"min_predictions": MIN_PREDICTIONS,
                       "required_agreement": REQUIRED_AGREEMENT,
                       "and": "no veto the evaluator would have missed"},
        "refuses": [
            "a veto outside the two things the requirement grants it over",
            "a reason outside the countable vocabulary",
            "a prediction dated at or after the ruling it claims to have predicted",
            "retirement on agreement alone while a veto was missed",
        ],
        "note": ("a veto is easy and its reason is what evaporates -- it arrives in a "
                 "conversation, is acted on once, and six months later nobody can say "
                 "whether the same objection was raised eleven times or once. An evaluator "
                 "that could have been trained on eleven instances was trained on nothing"),
        "today": ("no veto has been recorded, because no flagship creative and no canonical "
                  "identity exist yet. The veto is held by the owner and there is nothing to "
                  "retire it with"),
    }
