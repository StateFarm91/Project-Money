"""What a product idea is, before anybody engineers it.

Requirements 83, 84, 87, 88. The owner's judgement is that the current catalogue's creativity
is materially below standard, and treating that as a defect means finding the mechanism that
produced it rather than resolving to try harder.

The mechanism is visible in `products/builder.py`: a design is a motif, a palette, a width and
a repeat count. Everything the generator can vary is decoration, so everything it produces is
a variation. Nothing in the pipeline could notice, because nothing in the pipeline had a
representation of an *idea* — only of a fabric.

So a concept is structured rather than prose, and the structure is the part that has to differ.
Two concepts that share form, construction, motif, recipient, occasion and function are the
same concept in different colours, and `distance()` says so in a number. A tournament of
twenty such concepts is not a tournament (#84); a candidate that sits inside that radius of a
competitor's product is a clone (#87); and a premise assembled from words that could describe
anything is not a premise (#88).

The vocabularies below are closed on purpose. An open field accepts "beautiful cosy blanket",
which scores well against every check written to read English and means nothing to a buyer
scrolling a grid.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Closed vocabularies
#
# Each is a dimension a concept can actually differ along. Adding a value is a deliberate
# widening of what this company knows how to think about, which is the right size of decision
# to make on purpose.

FORMS: tuple[str, ...] = (
    "flat_panel", "rectangle_throw", "round_disc", "tube", "cone", "sphere", "basket",
    "fitted_garment", "draped_garment", "stocking", "ornament", "bag", "hat", "scarf",
    "pillow", "wall_hanging", "runner", "coaster", "toy", "wreath", "garland", "pouch",
)

CONSTRUCTIONS: tuple[str, ...] = (
    "flat_rows", "in_the_round", "motif_join", "top_down_yoke", "bottom_up", "side_to_side",
    "modular_panels", "amigurumi_shaping", "tapestry", "mosaic_overlay", "cable_panel",
    "granny_square", "corner_to_corner", "seamless_tube",
)

# What a buyer feels looking at the thumbnail. Emotional-design vocabulary, closed so that
# "nice" cannot be an answer.
FEELINGS: tuple[str, ...] = (
    "heirloom", "cosy", "playful", "nostalgic", "celebratory", "serene", "whimsical",
    "bold", "tender", "festive", "rugged", "romantic", "quietly_luxurious", "folkloric",
)

OCCASIONS: tuple[str, ...] = (
    "christmas", "halloween", "easter", "valentines", "thanksgiving", "new_baby",
    "housewarming", "wedding", "birthday", "mothers_day", "fathers_day", "graduation",
    "everyday", "winter_nesting", "spring_refresh", "summer_travel", "back_to_school",
)

RECIPIENTS: tuple[str, ...] = (
    "self", "partner", "new_parent", "child", "teen", "grandparent", "host", "pet_owner",
    "colleague", "teacher", "friend_who_has_everything", "newlyweds", "student",
)

MAKE_LANES: tuple[str, ...] = ("QUICK", "SHORT", "MEDIUM", "LONG", "FLAGSHIP")

# Words that describe nothing. A premise built only from these reads like a product and is
# not one -- which is precisely how a generated catalogue passes a prose check.
GENERIC_TOKENS: frozenset[str] = frozenset({
    "beautiful", "lovely", "nice", "pretty", "great", "perfect", "amazing", "stunning",
    "cosy", "cozy", "warm", "soft", "classic", "timeless", "elegant", "modern", "stylish",
    "unique", "special", "wonderful", "charming", "handmade", "crochet", "crocheted",
    "pattern", "easy", "simple", "quick", "set", "pack", "bundle", "gift", "home", "decor",
    "blanket", "throw", "scarf", "hat", "bag", "the", "a", "an", "and", "for", "with",
    "this", "that", "your", "our", "in", "of", "to", "is", "it", "made", "design",
})

_WORD = re.compile(r"[a-z]+")


class ConceptRefused(ValueError):
    """A concept whose structure is not a concept."""


@dataclass(frozen=True)
class Concept:
    """One product idea, described along the dimensions it could actually differ on."""

    key: str
    title: str
    premise: str            # the one-sentence visual premise #88 requires
    pod: str
    form: str
    construction: str
    motif: str              # the visual idea, not the stitch
    palette_story: str
    recipient: str
    occasion: str
    feeling: str
    function: str           # what it does for the person who owns it
    make_lane: str
    provenance: str = "internal"
    # Only a model that can look at an image may set these. `None` means nobody has judged,
    # which is a different thing from judged-and-fine, and the gate treats it differently.
    thumbnail_reads_small: bool | None = None
    craft_impression: float | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        for name, allowed in (("form", FORMS), ("construction", CONSTRUCTIONS),
                              ("feeling", FEELINGS), ("occasion", OCCASIONS),
                              ("recipient", RECIPIENTS), ("make_lane", MAKE_LANES)):
            value = getattr(self, name)
            if value not in allowed:
                raise ConceptRefused(
                    f"{self.key}: {name}={value!r} is not in the closed vocabulary. An open "
                    f"field here accepts 'nice', which scores well against every check "
                    f"written to read English and means nothing to a buyer")
        if len(self.premise.split()) < 6:
            raise ConceptRefused(
                f"{self.key}: a one-sentence visual premise is required before any "
                f"engineering (#88), and {self.premise!r} is not one")

    # -- the attributes that make two ideas the same idea ------------------
    #
    # Palette is deliberately excluded. A recolour is the canonical trivial variation, and
    # including palette here would let one hide as a difference.
    IDENTITY_FIELDS = ("pod", "form", "construction", "motif", "recipient", "occasion",
                       "function")

    def identity(self) -> tuple:
        return tuple(getattr(self, f) for f in self.IDENTITY_FIELDS)

    def premise_tokens(self) -> set[str]:
        return {w for w in _WORD.findall(self.premise.lower()) if w not in GENERIC_TOKENS}

    def to_dict(self) -> dict:
        return {
            "key": self.key, "title": self.title, "premise": self.premise, "pod": self.pod,
            "form": self.form, "construction": self.construction, "motif": self.motif,
            "palette_story": self.palette_story, "recipient": self.recipient,
            "occasion": self.occasion, "feeling": self.feeling, "function": self.function,
            "make_lane": self.make_lane, "provenance": self.provenance,
            "thumbnail_reads_small": self.thumbnail_reads_small,
            "craft_impression": self.craft_impression,
        }


# Weights over the identity fields. Form and construction dominate because they are what a
# buyer sees and what an engineer builds; a shared motif matters less than a shared silhouette.
_WEIGHTS: dict[str, float] = {
    "pod": 0.10, "form": 0.25, "construction": 0.20, "motif": 0.15,
    "recipient": 0.10, "occasion": 0.10, "function": 0.10,
}


def distance(a: Concept, b: Concept) -> float:
    """How different two ideas are, from 0 (the same idea) to 1 (nothing in common).

    Palette is not a term. Two concepts identical in every structural way and different in
    colour are the same concept, and this returns 0.0 for them — which is the whole point:
    the catalogue this company already has is full of that pair.
    """
    shared = sum(w for f, w in _WEIGHTS.items() if getattr(a, f) == getattr(b, f))
    structural = 1.0 - shared

    # A genuinely different premise is worth something, but it cannot rescue an identical
    # structure: capped so that rewriting the sentence never makes a recolour novel.
    tokens_a, tokens_b = a.premise_tokens(), b.premise_tokens()
    if tokens_a or tokens_b:
        overlap = len(tokens_a & tokens_b) / max(1, len(tokens_a | tokens_b))
        structural += 0.15 * (1.0 - overlap)
    return round(min(1.0, structural), 4)


def nearest(candidate: Concept, others: list[Concept]) -> tuple[Concept | None, float]:
    """The closest existing idea, and how close. The anti-clone gate's input (#87)."""
    if not others:
        return None, 1.0
    scored = [(other, distance(candidate, other)) for other in others
              if other.key != candidate.key]
    if not scored:
        return None, 1.0
    return min(scored, key=lambda pair: pair[1])


@dataclass
class Field:
    """A tournament field: the set of concepts competing for one opportunity."""

    opportunity: str
    concepts: list[Concept] = field(default_factory=list)

    def spread(self) -> float:
        """Mean pairwise distance. A field of recolours has a spread near zero."""
        pairs = [(a, b) for i, a in enumerate(self.concepts)
                 for b in self.concepts[i + 1:]]
        if not pairs:
            return 0.0
        return round(sum(distance(a, b) for a, b in pairs) / len(pairs), 4)

    def duplicate_pairs(self, threshold: float = 0.2) -> list[tuple[str, str, float]]:
        out = []
        for i, a in enumerate(self.concepts):
            for b in self.concepts[i + 1:]:
                d = distance(a, b)
                if d < threshold:
                    out.append((a.key, b.key, d))
        return sorted(out, key=lambda t: t[2])
