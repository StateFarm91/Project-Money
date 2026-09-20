"""What a competitor's listing is doing, taken apart into things nobody owns.

Requirement 214's two unbuilt halves: decompose the commercial mechanisms of a new listing,
and decide whether it justifies an original Brambleloop concept tournament. The rest of the
pipeline exists -- `intel.observe` archives the listing with dated evidence, `intel.pods`
classifies and routes it, `intel.coverage` turns an unanswered arena into queued work.

Decomposition is the dangerous step in that list, and it is dangerous in a specific way.

**A decomposition that keeps the expression is a copy with extra steps.** The purpose is to
learn *why* something works commercially: a size card that removes support questions, a
bundle that makes the anchor pattern look cheap, a first frame that reads at thumbnail scale.
None of those is anybody's property. What is somebody's property is the chart, the
photograph, the pattern text, the character on the ornament -- and a "mechanism" written
down as *a gnome with a striped hat* has not decomposed anything, it has described the
product in a way that sounds analytical. So a mechanism is refused if it names a depicted
subject, and `culture.rights.check_free_of` does the same word-boundary check here it does on
creative output, rather than a second implementation.

**A mechanism is a claim about commerce, so it names the effect it is supposed to have.**
"They use lifestyle photography" is an observation. "Lifestyle photography in frame two,
which is where a buyer decides whether they can picture owning it" is a mechanism: it says
what it does, which is the part that can later turn out to be wrong. An observation that
cannot be wrong teaches nothing, and a decomposition made of those accumulates forever
without changing a single decision.

**Most listings do not justify a tournament, and saying so is the useful part.** A pipeline
that turns every new competitor listing into a concept tournament burns the creative budget
on whatever the competitor happened to publish, which hands them the roadmap. The bar is
mechanisms this shop does not already have, in an arena it has evidence for -- and a new
listing in an arena already answered is a note, not a project.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..culture import rights

# What a mechanism can be about. Closed, and every entry is about how a thing is sold or
# built rather than what it depicts -- which is the whole distinction.
PRESENTATION = "presentation"
PACKAGING = "packaging"
PRICING = "pricing"
INFORMATION = "information"
RANGE = "range"
SERVICE = "service"
CONSTRUCTION = "construction"

CLASSES: dict[str, str] = {
    PRESENTATION: "how it is shown -- frame order, scale cues, what the thumbnail does",
    PACKAGING: "what arrives and how it is bundled",
    PRICING: "the number and what it is anchored against",
    INFORMATION: "what the buyer is told before they ask",
    RANGE: "how many variants, sizes or colourways, and why that many",
    SERVICE: "what happens around the purchase",
    CONSTRUCTION: "how the object is built, where that is visible and generic",
}

# Words that describe what a product depicts rather than how it works. A "mechanism" made of
# these is the product described in an analytical tone, which is the failure this refuses.
DEPICTION_WORDS: tuple[str, ...] = (
    "gnome", "snowman", "santa", "reindeer", "pumpkin", "cat", "dog", "bear", "bunny",
    "fox", "unicorn", "dinosaur", "elf", "angel", "witch", "ghost", "character",
    "motif", "design", "illustration", "artwork",
)

# Mechanisms this shop must already have before a new listing stops being interesting.
TOURNAMENT_MIN_NEW_MECHANISMS = 2


class MechanismRefused(ValueError):
    """A decomposition that kept the expression, or an observation dressed as a mechanism."""


@dataclass(frozen=True)
class Mechanism:
    """One commercial mechanism, and the effect it is claimed to have."""

    listing_ref: str
    klass: str
    what: str
    effect: str
    evidence_ref: str
    pod: str = ""

    def __post_init__(self) -> None:
        if self.klass not in CLASSES:
            raise MechanismRefused(
                f"{self.klass!r} is not a mechanism class: {sorted(CLASSES)}. Every class "
                f"here is about how a thing is sold or built rather than what it depicts, "
                f"which is the distinction that keeps this from being a copy with extra steps")
        if not self.evidence_ref.strip():
            raise MechanismRefused(
                f"{self.listing_ref}: a mechanism names the dated observation it came from, "
                f"or it is something somebody thought about a competitor")
        if len(self.effect.split()) < 5:
            raise MechanismRefused(
                f"{self.listing_ref}: say what this is supposed to do. 'They use lifestyle "
                f"photography' is an observation and cannot be wrong; a mechanism says what "
                f"it achieves, which is the part that can later turn out to be false -- and "
                f"an observation that cannot be wrong teaches nothing")
        surface = f"{self.what} {self.effect}".lower()
        hit = next((w for w in DEPICTION_WORDS
                    if rights._contains(surface, w)), None)
        if hit:
            raise MechanismRefused(
                f"{self.listing_ref}: {hit!r} describes what the product depicts, not how it "
                f"works. A mechanism written down as 'a gnome with a striped hat' has "
                f"decomposed nothing -- it is the product described in an analytical tone, "
                f"and the depicted subject is the part somebody owns")

    def to_dict(self) -> dict:
        return {"listing_ref": self.listing_ref, "class": self.klass,
                "class_means": CLASSES[self.klass], "what": self.what,
                "effect": self.effect, "evidence_ref": self.evidence_ref, "pod": self.pod}


def decompose(*, listing_ref: str, mechanisms: list[Mechanism],
              protected_tokens: list[rights.ProtectedToken] | None = None) -> dict:
    """Check a listing's decomposition against the tokens the observation declared.

    Reuses `rights.check_free_of` rather than implementing a second containment test: two
    answers to "did the protected thing survive" means the permissive one gets used, and this
    is the same check the creative brief runs on output.
    """
    tokens = list(protected_tokens or [])
    for m in mechanisms:
        try:
            rights.check_free_of(f"{m.what} {m.effect}", tokens,
                                 what=f"mechanism on {listing_ref!r}")
        except rights.RightsRefused as exc:
            raise MechanismRefused(
                f"{listing_ref}: {exc}. The mechanism is what this shop may learn; the "
                f"protected element is what it may not carry away") from exc

    by_class: dict[str, int] = {}
    for m in mechanisms:
        by_class[m.klass] = by_class.get(m.klass, 0) + 1
    return {
        "listing_ref": listing_ref,
        "mechanisms": [m.to_dict() for m in mechanisms],
        "by_class": dict(sorted(by_class.items())),
        "classes_covered": sorted(by_class),
        "classes_unexamined": sorted(set(CLASSES) - set(by_class)),
        "why": (f"{len(mechanisms)} mechanism(s) across {len(by_class)} class(es). Unexamined "
                f"classes are listed rather than assumed absent: a decomposition that looked "
                f"at presentation and stopped has not established that the pricing is "
                f"ordinary"),
    }


# ---- does this justify a tournament ---------------------------------------

TOURNAMENT = "run_a_tournament"
NOTE_ONLY = "note_it"
NO_ARENA_EVIDENCE = "no_arena_evidence"


def justifies_tournament(*, decomposition: dict, already_have: set[str],
                         arena_has_evidence: bool) -> dict:
    """Whether a new competitor listing is worth spending original creative work on.

    Most are not, and saying so is the useful part. A pipeline that turns every new
    competitor listing into a tournament spends the creative budget on whatever the
    competitor happened to publish, which is handing them the roadmap.
    """
    mechanisms = decomposition.get("mechanisms", [])
    new = [m for m in mechanisms if m["what"] not in already_have]

    if not arena_has_evidence:
        return {
            "decision": NO_ARENA_EVIDENCE, "new_mechanisms": len(new),
            "why": ("this arena has no demand evidence of its own. A competitor publishing "
                    "in it is evidence that they published, not that anybody bought -- and "
                    "spending a tournament on that is following rather than competing"),
        }
    if len(new) < TOURNAMENT_MIN_NEW_MECHANISMS:
        return {
            "decision": NOTE_ONLY, "new_mechanisms": len(new),
            "threshold": TOURNAMENT_MIN_NEW_MECHANISMS,
            "why": (f"{len(new)} mechanism(s) this shop does not already have, below "
                    f"{TOURNAMENT_MIN_NEW_MECHANISMS}. A new listing in an arena already "
                    f"answered is a note rather than a project, and the creative budget is "
                    f"the thing being protected"),
        }
    return {
        "decision": TOURNAMENT, "new_mechanisms": len(new),
        "mechanisms": [m["what"] for m in new],
        "why": (f"{len(new)} mechanisms this shop does not have, in an arena with its own "
                f"demand evidence. The tournament is for an original concept -- #227 refuses "
                f"parity as a reason to ship, so what this justifies is a search, not a "
                f"response"),
        "carries": ("the mechanisms, never the expression. #215 decides what entering the "
                    "arena requires and intel.panel refuses an entry offering only parity"),
    }


def state() -> dict:
    """What decomposition is for, and what it may never carry away."""
    return {
        "requirement": 214,
        "classes": dict(CLASSES),
        "tournament_threshold": TOURNAMENT_MIN_NEW_MECHANISMS,
        "builds_on": {
            "intel.observe": "the dated archive a mechanism must cite",
            "intel.pods": "which specialist answers for the listing",
            "intel.coverage": "an unanswered arena becoming queued work",
            "culture.rights": "the containment check, reused rather than reimplemented",
            "intel.panel": "what entering the arena then requires",
        },
        "refuses": [
            "a mechanism naming what the product depicts rather than how it works",
            "a mechanism carrying a token the observation declared protected",
            "an observation with no claimed effect, which cannot be wrong",
            "a mechanism with no dated evidence behind it",
            "a tournament for an arena with no demand evidence of its own",
        ],
        "note": ("a decomposition that keeps the expression is a copy with extra steps. What "
                 "is learnable is why something works commercially; what is not is the "
                 "chart, the photograph, the pattern text and the depicted subject"),
        "most_listings_are_notes": (
            "a pipeline that turns every new competitor listing into a concept tournament "
            "spends the creative budget on whatever the competitor happened to publish, "
            "which is handing them the roadmap"),
    }
