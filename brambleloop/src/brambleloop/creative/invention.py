"""Inventing a premise, rather than validating one somebody already had.

Requirements 106, 107, 108, 109, 110, 115. The existing creative module can tell a weak
concept from a strong one; what it could not do was produce a strong one, and the measured
evidence of that gap is in `creative/audit.py` — all eleven products in the catalogue compile
to a single flat-rows panel in two stitches. That is not a taste failure. It is a generator
with one degree of freedom being asked for variety and answering with colour.

The owner named this a major Build-2 defect, and the defect is structural: given a season and a
category, the highest-probability output is the commodity, because the commodity is what the
category is made of. Nothing in a validator changes that. What changes it is making the
*brief* carry the novelty, so the generator is asked for a specific unusual thing rather than
for a good thing.

Five machines, and each one removes a different way of arriving at a recoloured commodity.

**The invention matrix (#106)** requires two dimensions that do not normally co-occur. Motif ×
function, holiday × storage, tableware × character. A brief naming only one dimension is
refused, because one dimension is a category and a category is what everybody else is already
making.

**The transformation engine (#107)** holds *abstract* transformation patterns — becomes a set,
nests, unfolds, stacks into a scene, inverts, reveals — learned from what the market proves
people want and never from any seller's expression. A transformation description that names a
specific product is refused by the same content boundary the teardown library uses.

**The silhouette gate (#108)** knows which forms are shapes and which are outlines. A disc, a
tube, a rectangle and a pouch are shapes; at mobile-grid scale they are indistinguishable from
every other disc. They survive only with an exceptional qualifier, and "a concept that needs
its title to explain why it is interesting is weak" is enforced literally: the premise is read
with the title removed.

**The emotional promise (#109)** must be executed in the object. "Cosy" achieved by writing
*cosy* in the listing is the failure this requirement exists to name, so the promise carries
the physical mechanism that delivers it — a structure, a texture, a motif or a colour
relationship — and copy language is refused as a mechanism.

**The wow requirement (#115)** is a declared mechanism from a closed list, because "clean and
correct is not enough" is unenforceable as a sentiment and trivial as a checklist item.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .concept import FEELINGS, FORMS, GENERIC_TOKENS

# ---------------------------------------------------------------------------
# #106: the cross-category invention matrix

# The dimensions a premise can be built from. Deliberately not the same list as the Concept's
# fields: these are *sources of novelty*, and a concept field is a slot to be filled.
DIMENSIONS: dict[str, str] = {
    "motif": "the visual idea: what it depicts or evokes",
    "function": "what it does for the person who owns it",
    "holiday": "the occasion it belongs to",
    "storage": "holding, containing or tidying something",
    "character": "a figure with a face and a personality",
    "household_utility": "a job somebody already does in this room",
    "wearable": "worn on the body",
    "personalization": "made specific to one person",
    "amigurumi": "sculptural three-dimensional shaping",
    "organization": "sorting or arranging several things",
    "decor": "seen rather than used",
    "interaction": "something the owner does with it",
    "nursery": "for a very small person",
    "keepsake": "kept long after its use ends",
    "tableware": "used where people eat",
    "modularity": "built from repeatable units",
    "gifting": "chosen for somebody else",
}

# #106's own pairings, plus the rule that generated them: two dimensions that do not normally
# appear together. Listed rather than computed so the ones the requirement names are
# guaranteed present, and `cross()` accepts any pair that is not in the same family.
NAMED_PAIRS: tuple[tuple[str, str], ...] = (
    ("motif", "function"),
    ("holiday", "storage"),
    ("character", "household_utility"),
    ("wearable", "personalization"),
    ("amigurumi", "organization"),
    ("decor", "interaction"),
    ("nursery", "keepsake"),
    ("tableware", "character"),
    ("modularity", "gifting"),
)

# Dimensions that are near-synonyms. Pairing within a family produces a brief that reads
# like a combination and is one idea stated twice.
_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"storage", "organization"}),
    frozenset({"decor", "motif"}),
    frozenset({"character", "amigurumi"}),
    frozenset({"keepsake", "gifting"}),
)


class InventionRefused(ValueError):
    """A brief that is a category, a transformation that is somebody's product, or a
    promise made in copy."""


@dataclass(frozen=True)
class Brief:
    """A premise slot: two dimensions that must both be executed in one object."""

    dimension_a: str
    dimension_b: str
    season: str
    premise: str

    def to_dict(self) -> dict:
        return {"dimension_a": self.dimension_a, "dimension_b": self.dimension_b,
                "meaning_a": DIMENSIONS[self.dimension_a],
                "meaning_b": DIMENSIONS[self.dimension_b],
                "season": self.season, "premise": self.premise}


def cross(dimension_a: str, dimension_b: str, *, season: str, premise: str) -> Brief:
    """Build a brief from two dimensions that do not normally co-occur (#106).

    One dimension is a category, and a category is what everybody else is already making.
    """
    for name in (dimension_a, dimension_b):
        if name not in DIMENSIONS:
            raise InventionRefused(
                f"{name!r} is not an invention dimension: {sorted(DIMENSIONS)}")
    if dimension_a == dimension_b:
        raise InventionRefused(
            f"{dimension_a!r} crossed with itself is one dimension, which is a category. "
            f"The point of the matrix is a premise the category does not already contain "
            f"(#106)")
    pair = frozenset({dimension_a, dimension_b})
    for family in _FAMILIES:
        if pair <= family:
            raise InventionRefused(
                f"{dimension_a!r} and {dimension_b!r} are near-synonyms: a brief built from "
                f"them reads like a combination and is one idea stated twice")
    if len(premise.split()) < 8:
        raise InventionRefused(
            "a brief states what the object is and what both dimensions are doing in it; "
            "this is a title")
    return Brief(dimension_a, dimension_b, season, premise.strip())


def matrix(season: str) -> list[dict]:
    """Every named pairing as an empty brief slot, so breadth is a queue not an intention."""
    return [{"dimension_a": a, "dimension_b": b, "season": season,
             "meaning_a": DIMENSIONS[a], "meaning_b": DIMENSIONS[b],
             "prompt": (f"an object where {DIMENSIONS[a]} and {DIMENSIONS[b]} are the same "
                        f"decision rather than two features")}
            for a, b in NAMED_PAIRS]


# ---------------------------------------------------------------------------
# #107: the form transformation engine

# Abstract patterns only. Each is a relationship between what the object is and what it does,
# learned from what the market proves people want -- never from a seller's expression.
TRANSFORMATIONS: dict[str, str] = {
    "becomes_a_set": "one object separates into several that are useful apart",
    "nests_inside": "smaller instances live inside the larger one",
    "unfolds": "a compact object opens into a larger arrangement",
    "stacks_into_a_scene": "separate objects assemble into one tableau",
    "inverts": "turning it inside out or upside down changes what it is",
    "modular_assembly": "repeatable units build an object of any size",
    "doubles_as": "the decorative object is also the useful one",
    "reveals": "something is hidden until the owner does one thing",
    "grows": "the object is added to season after season",
}

# Language that describes copying rather than abstracting. Same boundary as the teardown
# library's, at the door where a transformation would enter.
_NAMES_A_PRODUCT = (
    "just like", "same as", "copy of", "version of the", "based on the seller",
    "as sold by", "their design", "recreate", "replica",
)


@dataclass(frozen=True)
class Transformation:
    pattern: str
    from_form: str
    to_function: str
    description: str

    def to_dict(self) -> dict:
        return {"pattern": self.pattern, "meaning": TRANSFORMATIONS[self.pattern],
                "from_form": self.from_form, "to_function": self.to_function,
                "description": self.description}


def transform(pattern: str, *, from_form: str, to_function: str,
              description: str) -> Transformation:
    """Invent an original transformation from an abstract pattern (#107)."""
    if pattern not in TRANSFORMATIONS:
        raise InventionRefused(
            f"{pattern!r} is not a transformation pattern: {sorted(TRANSFORMATIONS)}. The "
            f"patterns are abstract on purpose -- what transfers from the market is the "
            f"relationship, never the object somebody sells")
    if from_form not in FORMS:
        raise InventionRefused(f"{from_form!r} is not a form: {sorted(FORMS)}")
    low = description.lower()
    for phrase in _NAMES_A_PRODUCT:
        if phrase in low:
            raise InventionRefused(
                f"{phrase!r} describes reproducing a specific product rather than applying "
                f"the abstract pattern. Learn the transformation, never the expression "
                f"(#107)")
    if len(to_function.split()) < 2:
        raise InventionRefused(
            "a transformation ends somewhere useful; name the function it becomes")
    return Transformation(pattern, from_form, to_function.strip(), description.strip())


# ---------------------------------------------------------------------------
# #108: the silhouette gate

# Forms that are shapes rather than outlines. At mobile-grid scale one disc is every disc.
GENERIC_FORMS: frozenset[str] = frozenset({
    "flat_panel", "rectangle_throw", "round_disc", "tube", "cone", "sphere", "pouch",
    "runner", "coaster", "scarf",
})

# What can rescue a generic form: something a buyer can see at thumbnail size.
QUALIFIERS: dict[str, str] = {
    "transformation": "it becomes or contains something else",
    "motif_composition": "the motif arrangement is the object's shape",
    "dimensional_texture": "the surface has relief a photograph shows",
    "unusual_function": "it does a job this category does not normally do",
    "character_system": "it is a figure, or part of a family of figures",
    "modular_reveal": "assembling it produces something the parts did not show",
}


def _meaningful_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", (text or "").lower())
            if w not in GENERIC_TOKENS]


def silhouette(*, form: str, premise: str, title: str = "",
               qualifiers: tuple[str, ...] = ()) -> dict:
    """Would this read as a distinct object in a grid of thumbnails? (#108)

    Two refusals. A generic form with no qualifier is a disc among discs. And a premise that
    is only interesting once the title explains it is weak — enforced literally by reading the
    premise with the title's words removed, because "the title carries it" is the exact
    failure the requirement names and it is invisible when both are read together.
    """
    unknown = [q for q in qualifiers if q not in QUALIFIERS]
    if unknown:
        raise InventionRefused(f"{sorted(unknown)} are not silhouette qualifiers: "
                               f"{sorted(QUALIFIERS)}")

    title_words = set(_meaningful_words(title))
    premise_words = _meaningful_words(premise)
    without_title = [w for w in premise_words if w not in title_words]

    problems: list[str] = []
    if form in GENERIC_FORMS and not qualifiers:
        problems.append(
            f"{form!r} is a shape rather than an outline: at mobile-grid scale one is every "
            f"one. It survives only with an exceptional qualifier -- a transformation, a "
            f"motif composition that is the shape, relief a photograph shows, an unusual "
            f"function, a character system or a modular reveal (#108)")
    if len(without_title) < 4:
        problems.append(
            f"with the title's words removed the premise has {len(without_title)} specific "
            f"words left. A concept that needs its title to explain why it is interesting is "
            f"weak, and reading them together hides it")

    return {
        "form": form,
        "generic_form": form in GENERIC_FORMS,
        "qualifiers": [{"key": q, "meaning": QUALIFIERS[q]} for q in qualifiers],
        "specific_words_without_title": without_title,
        "passes": not problems,
        "problems": problems,
    }


# ---------------------------------------------------------------------------
# #109: the emotional promise, executed in the object

# Ways a feeling can be delivered by the thing itself rather than by the words beside it.
EXECUTIONS: dict[str, str] = {
    "structure": "the way it is built",
    "texture": "relief, pile or stitch surface",
    "motif": "what it depicts",
    "colour_relationship": "how the colours behave against each other",
    "scale": "how large or small it is relative to expectation",
    "finish": "edging, backing, hardware or presentation",
}

# Language that describes a listing rather than an object.
_COPY_LANGUAGE = ("perfect for", "sure to", "will love", "adds a touch", "brings warmth",
                  "makes a great", "ideal gift", "cosy vibes", "must-have")


@dataclass(frozen=True)
class Promise:
    feeling: str
    execution: str
    how: str

    def to_dict(self) -> dict:
        return {"feeling": self.feeling, "execution": self.execution,
                "execution_meaning": EXECUTIONS[self.execution], "how": self.how}


def promise(feeling: str, execution: str, how: str) -> Promise:
    """Declare an emotional promise and the physical thing that delivers it (#109).

    "Cosy" achieved by writing *cosy* in the listing is the failure this requirement names,
    and it is the cheapest possible way to satisfy a check that only reads text.
    """
    if feeling not in FEELINGS:
        raise InventionRefused(f"{feeling!r} is not an emotional promise: {sorted(FEELINGS)}")
    if execution not in EXECUTIONS:
        raise InventionRefused(
            f"{execution!r} is not a way an object delivers a feeling: {sorted(EXECUTIONS)}")
    low = how.lower()
    for phrase in _COPY_LANGUAGE:
        if phrase in low:
            raise InventionRefused(
                f"{phrase!r} is listing copy, not an execution. The promise has to be "
                f"visible in the object -- a buyer looking at the photograph with the sound "
                f"off should feel it (#109)")
    if len(_meaningful_words(how)) < 3:
        raise InventionRefused(
            "say what about the object produces the feeling; this is an adjective with a "
            "sentence around it")
    return Promise(feeling, execution, how.strip())


# ---------------------------------------------------------------------------
# #110: seasonal motif grammar

MOTIF_GRAMMAR: dict[str, tuple[str, ...]] = {
    "christmas": ("tree", "stocking", "bow", "candy", "gingerbread", "snow", "woodland",
                  "star", "ornament", "santa", "reindeer", "wreath", "bell", "mitten",
                  "lantern", "sleigh", "nutcracker", "holly", "candle", "post_box"),
    "fall": ("leaf", "mushroom", "acorn", "pumpkin", "woodland", "harvest", "hedgehog",
             "conker", "apple", "wheat", "fox", "lantern"),
    "halloween": ("ghost", "bat", "monster", "witch", "haunted_architecture", "cat",
                  "spider", "cauldron", "skeleton", "moon", "candy", "eyeball"),
    "spring": ("floral", "chick", "rabbit", "egg", "garden_life", "nest", "lamb",
               "raincloud", "tulip", "bee", "seedling"),
    "summer": ("shell", "wave", "sun", "citrus", "picnic", "sailboat", "watermelon",
               "ice_cream", "wildflower", "dragonfly"),
}

# The motifs everybody uses. Not banned -- a Christmas with no tree is a different problem --
# but a concept built only from these is the commodity by construction.
SATURATED: dict[str, frozenset[str]] = {
    "christmas": frozenset({"tree", "santa", "snow", "stocking", "reindeer"}),
    "fall": frozenset({"pumpkin", "leaf"}),
    "halloween": frozenset({"ghost", "bat", "witch"}),
    "spring": frozenset({"egg", "rabbit", "chick"}),
    "summer": frozenset({"sun", "shell"}),
}


def motifs(season: str, chosen: tuple[str, ...]) -> dict:
    """Check a motif selection against the season's grammar and its clichés (#110).

    Recombination is the requirement: a motif nobody pairs with another is where a new
    premise comes from, and two saturated motifs together is the thumbnail everybody has.
    """
    if season not in MOTIF_GRAMMAR:
        raise InventionRefused(
            f"{season!r} has no motif grammar: {sorted(MOTIF_GRAMMAR)}")
    vocabulary = set(MOTIF_GRAMMAR[season])
    unknown = [m for m in chosen if m not in vocabulary]
    if unknown:
        raise InventionRefused(
            f"{sorted(unknown)} are not in the {season} grammar. Widening the grammar is a "
            f"deliberate decision; inventing a motif per concept is how a grammar stops "
            f"being one: {sorted(vocabulary)}")

    saturated = [m for m in chosen if m in SATURATED.get(season, frozenset())]
    fresh = [m for m in chosen if m not in SATURATED.get(season, frozenset())]
    return {
        "season": season,
        "chosen": list(chosen),
        "saturated": saturated,
        "fresh": fresh,
        "all_saturated": bool(chosen) and not fresh,
        "grammar_size": len(vocabulary),
        "unused": sorted(vocabulary - set(chosen)),
        "note": ("Every motif here is one everybody uses. Not forbidden -- a Christmas with "
                 "no tree is a different problem -- but a concept built only from these is "
                 "the commodity by construction, and recombination is where a new premise "
                 "comes from (#110)."
                 if chosen and not fresh else
                 "at least one motif is outside the saturated set"),
    }


# ---------------------------------------------------------------------------
# #115: the wow requirement

WOW_MECHANISMS: dict[str, str] = {
    "surprising_transformation": "it becomes something the photograph did not show",
    "exceptional_motif_composition": "the motif arrangement is itself the design",
    "dimensional_construction": "it is sculptural rather than flat",
    "unusual_but_useful_function": "it does a job this category does not normally do",
    "strong_character_system": "a figure, or a family of them, with a consistent logic",
    "modular_reveal": "the assembled whole is more than the parts suggested",
    "personalization_architecture": "it is designed to be made specific to one person",
    "striking_texture": "a surface a photograph can sell on its own",
    "premium_silhouette": "an outline nothing else in the grid has",
    "collection_storytelling": "it means more beside its siblings than alone",
}

FLAGSHIP = "FLAGSHIP"


@dataclass
class Wow:
    mechanism: str
    grounded_in: str
    problems: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict:
        return {"mechanism": self.mechanism,
                "meaning": WOW_MECHANISMS.get(self.mechanism, ""),
                "grounded_in": self.grounded_in, "ok": self.ok,
                "problems": list(self.problems)}


def wow(make_lane: str, mechanism: str | None, grounded_in: str = "") -> Wow:
    """Every flagship carries a declared WOW mechanism (#115).

    "Clean and correct is not enough" is unenforceable as a sentiment and trivial as a
    checkbox, so the mechanism is named from a closed list and grounded in something about
    this specific object. A mechanism with no grounding is a checkbox.
    """
    result = Wow(mechanism=mechanism or "", grounded_in=grounded_in.strip())
    if make_lane != FLAGSHIP:
        return result
    if not mechanism:
        result.problems.append(
            "a flagship with no declared WOW mechanism is a clean, correct, forgettable "
            "product -- which is the thing #115 exists to refuse")
        return result
    if mechanism not in WOW_MECHANISMS:
        raise InventionRefused(
            f"{mechanism!r} is not a WOW mechanism: {sorted(WOW_MECHANISMS)}")
    if len(_meaningful_words(grounded_in)) < 4:
        result.problems.append(
            f"{mechanism!r} is declared and not grounded in anything about this object. An "
            f"ungrounded mechanism is a checkbox, and a checkbox is what a generator learns "
            f"to tick")
    return result
