"""Turning a cultural signal into something this company can own.

Requirements 134, 137, 138, 142, 143, 146. The translation step is where a culture radar
either becomes a durable asset or becomes a copyright problem, and the difference is one
property: whether the protected thing survives the translation.

#134 names ten primitives — emotion, setting, era, humour type, colour language, object
category, ritual, character archetype, visual motif class and gifting context — and the reason
there are ten rather than one is that the useful part of a cultural moment is almost never the
property. "A chaotic family Christmas where everything goes wrong and the decorations are
enormous" is the demand. The film is how we found it.

Three things this module does that a prompt could not.

**It checks the decomposition instead of trusting it.** Every primitive is scanned for the
tokens the signal declared as protected, so an "emotion" reading *the emotion of being Baby
Yoda* is refused. Without the check, decomposition is a paraphrase with a better name — and a
paraphrase is what a model produces when the protected element is the most salient thing in
its input, which it always is.

**Eras are territories, not franchises (#137).** An era is reusable, recurs annually, and
belongs to nobody: retro ski lodge is available every winter forever, and no rights holder can
take it away in January. That is a strictly better asset than any licensed one, and it is the
reason the original lane is not a consolation prize.

**A theme becomes a collection only when it has earned the shape (#143).** A territory with
one product is a product. The collection architecture is six roles, and the module reports
which roles are missing rather than declaring a collection because six products exist.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .rights import ProtectedToken, check_free_of

# The ten primitives #134 enumerates. Closed, because an open list becomes "theme: Christmas"
# repeated ten times, and the whole point is that the ten are different questions.
PRIMITIVES: tuple[tuple[str, str], ...] = (
    ("emotion", "what the person feels, stated as a feeling rather than a topic"),
    ("setting", "where it happens, concretely enough to draw"),
    ("era", "which reusable aesthetic territory it belongs to"),
    ("humour_type", "the shape of the joke, if there is one"),
    ("colour_language", "the palette the moment carries, as a language not a swatch"),
    ("object_category", "what physical object the feeling attaches to"),
    ("ritual", "the repeated act the moment is built around"),
    ("character_archetype", "the role, never the character"),
    ("visual_motif_class", "the class of motif, never the distinctive one"),
    ("gifting_context", "who gives this to whom, and why that person"),
)

PRIMITIVE_KEYS: tuple[str, ...] = tuple(k for k, _ in PRIMITIVES)

# Reusable demand territories (#137). Independent of any franchise, recurring annually, and
# owned by nobody -- which makes them a better asset than a licence, not a worse one.
ERAS: dict[str, str] = {
    "retro_suburban_christmas": "aluminium tree, orange and avocado, a very tidy living room",
    "eighties_holiday_maximalism": "more of everything, jewel tones, unapologetic tinsel",
    "nineties_family_christmas": "plaid, forest green, a camcorder and a burnt casserole",
    "vintage_ski_lodge": "fair isle, oxblood, woodsmoke, a thermos",
    "mid_century_holiday": "clean lines, brass, a low table with a martini on it",
    "classic_storybook_winter": "ink-drawn hares, cream and soot, a lamp in the snow",
    "retro_halloween": "die-cut cats, harvest orange, crepe paper",
    "cottage_summer": "sun-bleached stripes, gingham, a jug of something on a step",
    "romantic_comedy_autumn": "camel coats, bookshops, leaves somebody is walking through",
}

# Durable original territories (#142). Emotions rather than properties: nobody owns the
# feeling of an over-decorated house, and everybody recognises it.
THEMES: dict[str, str] = {
    "chaotic_family_holiday": "everything goes wrong and it is still the best day",
    "over_the_top_decorating": "the house is visible from space and that is the point",
    "awkward_relatives": "affection expressed entirely through mild hostility",
    "winter_road_trip": "a thermos, a long dark road, and somebody asleep in the back",
    "office_holiday_party": "a paper crown worn with total sincerity",
    "cozy_movie_night": "the specific safety of a blanket and a screen",
    "magical_childhood_christmas": "the version remembered rather than the one that happened",
    "retro_toy_shop_winter": "a window display at night, seen from outside",
    "spooky_cute_halloween": "frightening in the way a very small ghost is frightening",
    "romantic_comedy_valentine": "sincerity that knows it is being sincere",
}

# The collection roles #143 names. A territory with one product is a product.
COLLECTION_ROLES: tuple[str, ...] = (
    "flagship", "quick_make", "giftable_mini", "decor", "wearable_accessory", "bundle")

# The product families #138 wants a strong signal translated across, so the tournament is
# broad rather than three blankets.
TRANSLATION_FAMILIES: tuple[str, ...] = (
    "blanket", "stocking", "ornament", "coaster", "wreath", "garland", "tableware",
    "amigurumi", "wearable", "bag", "pillow", "nursery", "pet", "kitchen", "interactive")

# A tournament that produced four ideas across two families is a shortlist, not a tournament.
MIN_FAMILIES = 6
MIN_TRANSLATIONS = 10


class TranslationRefused(Exception):
    """A decomposition that kept the property, or a collection that is one product."""


@dataclass
class Decomposition:
    signal_key: str
    primitives: dict = field(default_factory=dict)
    absent: list = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.absent

    def to_dict(self) -> dict:
        return {"signal": self.signal_key, "primitives": self.primitives,
                "absent": list(self.absent),
                "complete": self.complete,
                "note": ("The ten primitives are ten different questions. A decomposition "
                         "that answers three of them has found a topic, not a demand.")}


def decompose(signal_key: str, answers: dict, tokens: list[ProtectedToken]) -> Decomposition:
    """Break a cultural signal into primitives nobody owns, and prove it.

    The proof is the point. A decomposition derived from a protected source is a paraphrase
    unless somebody checks, and the protected element is always the most salient thing in the
    input — so it is exactly what survives when nobody does.
    """
    unknown = [k for k in answers if k not in PRIMITIVE_KEYS]
    if unknown:
        raise TranslationRefused(
            f"{sorted(unknown)} are not translation primitives: {list(PRIMITIVE_KEYS)}")

    primitives: dict = {}
    for key in PRIMITIVE_KEYS:
        value = str(answers.get(key) or "").strip()
        if not value:
            continue
        check_free_of(value, tokens, what=f"the {key!r} primitive")
        primitives[key] = value

    if "era" in primitives and primitives["era"] not in ERAS:
        raise TranslationRefused(
            f"{primitives['era']!r} is not a recorded era: {sorted(ERAS)}. An era invented "
            f"per signal is a franchise with a different name, and the value of an era is "
            f"that it comes back next year without anybody's permission (#137)")

    absent = [k for k in PRIMITIVE_KEYS if k not in primitives]
    return Decomposition(signal_key=signal_key, primitives=primitives, absent=absent)


@dataclass(frozen=True)
class Translation:
    """One original product idea derived from a signal."""

    slug: str
    family: str
    premise: str
    theme: str = ""
    era: str = ""

    def to_dict(self) -> dict:
        return {"slug": self.slug, "family": self.family, "premise": self.premise,
                "theme": self.theme, "era": self.era}


def white_space(signal_key: str, translations: list[Translation],
                tokens: list[ProtectedToken]) -> dict:
    """The breadth check #138 asks for, and the two ways breadth is faked.

    Fifteen ideas in two families is one idea in fifteen colours, and ten ideas whose premises
    restate each other is one idea typed ten times. Both are caught here rather than by the
    jury, because both are properties of the *set* and the jury sees concepts one at a time.
    """
    for t in translations:
        check_free_of(f"{t.slug} {t.premise}", tokens, what=f"the {t.slug!r} translation")
        if t.family not in TRANSLATION_FAMILIES:
            raise TranslationRefused(
                f"{t.family!r} is not a product family: {sorted(TRANSLATION_FAMILIES)}")

    families = sorted({t.family for t in translations})
    premises = [t.premise.lower().strip() for t in translations]
    distinct_premises = len(set(premises))

    return {
        "signal": signal_key,
        "translations": len(translations),
        "families": families,
        "family_count": len(families),
        "distinct_premises": distinct_premises,
        "broad_enough": (len(translations) >= MIN_TRANSLATIONS
                         and len(families) >= MIN_FAMILIES
                         and distinct_premises == len(translations)),
        "missing_families": [f for f in TRANSLATION_FAMILIES if f not in families],
        "note": ("Breadth is families and distinct premises, not count. Fifteen ideas in two "
                 "families is one idea in fifteen colours, and the jury cannot see that "
                 "because it reads concepts one at a time (#138)."),
    }


def collection(theme: str, roles_present: dict) -> dict:
    """Whether a cultural territory has earned a collection (#143).

    Reported as shape rather than declared from a count: six products that are all decor is a
    decor range with a theme, and the customer who wanted the giftable mini leaves.
    """
    if theme not in THEMES:
        raise TranslationRefused(
            f"{theme!r} is not a recorded franchise-free theme: {sorted(THEMES)}. Themes are "
            f"durable territories this company owns (#142), and one invented per signal is a "
            f"dependence on somebody else's property with the name filed off")
    have = {r: roles_present.get(r) for r in COLLECTION_ROLES if roles_present.get(r)}
    missing = [r for r in COLLECTION_ROLES if r not in have]
    return {
        "theme": theme,
        "meaning": THEMES[theme],
        "roles_present": have,
        "roles_missing": missing,
        "is_a_collection": not missing,
        "note": ("A territory with one product is a product. The six roles vary form and "
                 "price point while the visual language stays constant (#143)."
                 if missing else
                 "every collection role is filled by an original product in this territory"),
    }


def owned_territories() -> dict:
    """What this company owns outright, as distinct from what it is borrowing (#146).

    Worth being able to state as a number: the long-term goal is not permanent dependence on
    external pop culture, and a dependence nobody measures is one nobody notices growing.
    """
    return {
        "eras": ERAS,
        "themes": THEMES,
        "count": len(ERAS) + len(THEMES),
        "note": ("Eras and themes belong to nobody, recur annually, and cannot be withdrawn "
                 "in January. Every product built on one is an asset this company keeps; "
                 "every product built on a franchise is rented (#146)."),
    }
