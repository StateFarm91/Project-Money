"""The adversarial jury, and the gate a concept must clear before anyone engineers it.

Requirements 83, 85, 87, 88. #85 asks for a Creativity Director plus independent critics whose
job is to attack sameness, genericness, weak emotional appeal, derivative thinking, poor
thumbnail potential and unnecessary complexity — and the sentence that makes it real is the one
about the pass rate being expected to be low.

A jury that passes everything is a formality, and a formality is how the current catalogue
happened: nothing in the pipeline could refuse a design for being the fourth mosaic throw,
because nothing was asked to.

**Critics can only reject.** Each returns a finding or nothing. There is no critic that awards
points, because a scoring jury averages a fatal objection away — the same failure the CA$5K
ladder avoids by taking a minimum. One critic's rejection ends the concept.

**Nothing passes on structure alone.** The structural critics below are real and mechanical,
and they cannot tell whether a thing is *desirable*. That needs eyes. So the gate's best
possible verdict without a vision model is `needs_taste`: structurally clean, unjudged, and
explicitly not approved. A concept that reaches engineering on structural cleanliness alone
would be exactly what #83 forbids — engineered because it filled a category slot.

**Every death is recorded.** Creative-failure autopsies are not a report written afterwards;
they are the rejection itself, kept.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .concept import Concept, Field, distance, nearest

# How close is too close. Tuned against the pair this company already has: two mosaic throws
# differing only in palette score 0.0, and a genuinely adjacent idea — same form, different
# construction and occasion — scores around 0.45.
CLONE_THRESHOLD = 0.25
FIELD_SPREAD_MINIMUM = 0.45
MIN_FIELD = 12          # #84: a diverse field, not a shortlist
MAX_FIELD = 25

# Techniques a lane can carry before the product is fighting its own buyer.
LANE_TECHNIQUE_BUDGET: dict[str, int] = {
    "QUICK": 2, "SHORT": 3, "MEDIUM": 4, "LONG": 5, "FLAGSHIP": 7,
}


@dataclass(frozen=True)
class Finding:
    critic: str
    concept: str
    problem: str
    evidence: dict

    def to_dict(self) -> dict:
        return {"critic": self.critic, "concept": self.concept, "problem": self.problem,
                "evidence": self.evidence}


@dataclass
class Context:
    """What the critics need to judge a concept against."""

    field: Field | None = None
    catalogue: list[Concept] | None = None      # what we already sell
    benchmark: list[Concept] | None = None      # what the observed competitor sells
    techniques: int = 1                          # distinct techniques the concept needs


Critic = Callable[[Concept, Context], "Finding | None"]


# ---------------------------------------------------------------------------
# The critics


def sameness(concept: Concept, ctx: Context) -> Finding | None:
    """Is this the same idea as something already in our own catalogue?

    The failure this company actually has. Four throws differing in motif and palette are one
    product with four names, and a catalogue of them looks like range to nobody but us.
    """
    near, d = nearest(concept, ctx.catalogue or [])
    if near is not None and d < CLONE_THRESHOLD:
        return Finding("sameness", concept.key,
                       f"this is the same idea as {near.key!r} at distance {d}: same "
                       f"silhouette, construction and job, differing mainly in decoration",
                       {"nearest": near.key, "distance": d,
                        "shared": [f for f in Concept.IDENTITY_FIELDS
                                   if getattr(concept, f) == getattr(near, f)]})
    return None


def genericness(concept: Concept, ctx: Context) -> Finding | None:
    """Does the premise say anything a different product could not also say? (#88)"""
    specific = concept.premise_tokens()
    if len(specific) < 3:
        return Finding("genericness", concept.key,
                       "the premise is built from words that could describe any crochet "
                       "product; if the seller name, price and reviews vanished, nothing "
                       "here would create curiosity",
                       {"specific_tokens": sorted(specific), "premise": concept.premise})
    return None


def weak_emotional_appeal(concept: Concept, ctx: Context) -> Finding | None:
    """Does it know who it is for and what it is for?"""
    if concept.recipient == "self" and concept.occasion == "everyday" \
            and concept.feeling in ("cosy", "serene"):
        return Finding("emotional_appeal", concept.key,
                       "an everyday thing for oneself that feels cosy is the default answer "
                       "to every crochet brief; it names no moment a buyer would act on",
                       {"recipient": concept.recipient, "occasion": concept.occasion,
                        "feeling": concept.feeling})
    if not concept.function.strip() or len(concept.function.split()) < 3:
        return Finding("emotional_appeal", concept.key,
                       "the concept does not say what it does for the person who owns it",
                       {"function": concept.function})
    return None


def derivative(concept: Concept, ctx: Context) -> Finding | None:
    """Is its appeal borrowed from a specific competitor product? (#87)

    Note what this does *not* forbid: entering the same broad arena is explicitly allowed
    (#215, #306). Cardigans are not owned by anybody. What is refused is a concept whose
    distinctiveness collapses to one seller's particular execution.
    """
    near, d = nearest(concept, ctx.benchmark or [])
    if near is not None and d < CLONE_THRESHOLD:
        return Finding("derivative", concept.key,
                       f"this sits inside a benchmark product's radius ({near.key!r}, "
                       f"distance {d}). The arena is fair game; this particular execution is "
                       f"theirs",
                       {"benchmark": near.key, "distance": d})
    return None


def thumbnail(concept: Concept, ctx: Context) -> Finding | None:
    """Would the idea survive being 170 pixels wide? (#88)

    Where a vision model exists this is its judgement. Where one does not, the structural
    proxy still catches the reliable failure: an idea whose whole appeal is fine detail.
    """
    if concept.thumbnail_reads_small is False:
        return Finding("thumbnail", concept.key,
                       "judged not to read at mobile-grid size, where the buying decision "
                       "actually starts", {"judged": True})
    fine = {"tiny", "miniature", "micro", "delicate", "intricate", "filigree", "lace",
            "fine", "detailed", "subtle"}
    hits = sorted(fine & concept.premise_tokens())
    if hits and concept.form in ("ornament", "coaster", "garland", "pouch"):
        return Finding("thumbnail", concept.key,
                       f"a small object whose premise rests on {hits} has nothing left at "
                       f"thumbnail size", {"tokens": hits, "form": concept.form})
    return None


def unnecessary_complexity(concept: Concept, ctx: Context) -> Finding | None:
    """Is it asking more of the maker than the idea repays?"""
    budget = LANE_TECHNIQUE_BUDGET[concept.make_lane]
    if ctx.techniques > budget:
        return Finding("complexity", concept.key,
                       f"{ctx.techniques} distinct techniques in a {concept.make_lane} "
                       f"product, where {budget} is the budget; the difficulty is not the "
                       f"thing being sold",
                       {"techniques": ctx.techniques, "budget": budget})
    return None


CRITICS: tuple[tuple[str, Critic], ...] = (
    ("sameness", sameness),
    ("genericness", genericness),
    ("emotional_appeal", weak_emotional_appeal),
    ("derivative", derivative),
    ("thumbnail", thumbnail),
    ("complexity", unnecessary_complexity),
)


# ---------------------------------------------------------------------------
# The gate (#83)

REJECTED = "rejected"
NEEDS_TASTE = "needs_taste"
APPROVED = "approved"


@dataclass
class Verdict:
    concept: str
    decision: str
    findings: list[Finding]
    unjudged: list[str]

    @property
    def survives(self) -> bool:
        return self.decision != REJECTED

    def to_dict(self) -> dict:
        return {"concept": self.concept, "decision": self.decision,
                "findings": [f.to_dict() for f in self.findings],
                "unjudged": list(self.unjudged)}


def judge(concept: Concept, ctx: Context | None = None) -> Verdict:
    """Run every critic. One rejection is enough.

    Deliberately not a score. Averaging critics lets five approvals bury the one that noticed
    the product is a recolour, which is the same arithmetic mistake as averaging a confidence
    ladder — and it is how a jury becomes a formality.
    """
    ctx = ctx or Context()
    findings = [f for _, critic in CRITICS if (f := critic(concept, ctx)) is not None]
    if findings:
        return Verdict(concept.key, REJECTED, findings, [])

    # Structurally clean is not desirable. These are the questions only eyes answer, and
    # while nothing can see, the honest verdict is that nobody has looked.
    unjudged = []
    if concept.thumbnail_reads_small is None:
        unjudged.append("thumbnail_legibility")
    if concept.craft_impression is None:
        unjudged.append("craft_impression")
    if unjudged:
        return Verdict(concept.key, NEEDS_TASTE, [], unjudged)
    if (concept.craft_impression or 0) < 3.5:
        return Verdict(concept.key, REJECTED, [Finding(
            "craft_impression", concept.key,
            f"judged at {concept.craft_impression} for apparent craftsmanship, below the "
            f"bar a premium listing has to clear", {"score": concept.craft_impression})], [])
    return Verdict(concept.key, APPROVED, [], [])
