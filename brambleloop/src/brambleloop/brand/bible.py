"""The brand system (Master Plan section 6).

Section 6's requirement is that the Etsy grid reads as one premium design house rather than a
stack of unrelated listings. That is a consistency problem, and consistency maintained by
taste alone does not survive an autonomous system producing assets unattended for months.

So the brand is data: a locked palette, locked type, locked crop and lighting rules, a
collection naming grammar, and a character bible for the brand model. Anything that renders
an asset reads from here, and `check_grid_coherence` can say whether the grid still holds
together without anyone looking at it.

On the brand model specifically. The owner's bible asks for a consistent fictional adult
woman for wearable imagery. Three constraints are built in rather than left to judgement:
she is never used where product-first imagery is stronger (blankets, decor, amigurumi), her
description may not drift toward a real person, and any image of her is an
AI_LIFESTYLE_CONCEPT that Asset Truth treats as a concept rather than a photograph of a
finished object. A rendered model wearing a garment nobody has made is not evidence that the
garment exists.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---- visual identity -------------------------------------------------------

PALETTE: dict[str, str] = {
    "pine": "#244A3A",
    "cream": "#FAF6EB",
    "ink": "#1A2B3C",
    "gold": "#C49545",
    "wine": "#6E1F2A",
    "line": "#D6CEBC",
    "muted": "#6B7280",
}

ACCENT_ORDER = ("pine", "gold", "wine")

TYPOGRAPHY = {
    "display": "Helvetica-Bold",
    "body": "Helvetica",
    "tracking_display": 0.02,
    "min_body_pt": 9,
}

# WCAG 2.1 AA for text below 18pt, as the measurement it is: a ratio of relative luminance
# between the ink and the paper it sits on.
#
# Here rather than in a renderer because more than one thing renders text on this palette, and
# the brand's own `muted` grey measures 4.48:1 on the brand's cream -- a fraction under the
# floor. The customer's PDF was corrected on 2026-09-24 by darkening its own ink; the chart
# and legend images inside that same PDF were not, so the running heads and row labels a maker
# reads while working stayed below the floor. Two renderers, one rule: this one.
MIN_TEXT_CONTRAST = 4.5


def _srgb_channel(value: float) -> float:
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    """Relative luminance of an sRGB colour given as three 0.0-1.0 channels."""
    r, g, b = (_srgb_channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    """Contrast ratio between two colours, 1.0 (invisible) to 21.0 (black on white)."""
    a, b = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def legible(fg: tuple[float, float, float], bg: tuple[float, float, float], *,
            minimum: float = MIN_TEXT_CONTRAST) -> tuple[float, float, float]:
    """The brand colour, moved away from its background only as far as it has to be.

    Returns the original untouched when it already passes, so a future palette that is legible
    on its own renders exactly as specified. The palette itself is never edited here: the
    storefront, the chart renderer and the PDF all read `PALETTE`, and moving it to fix one
    surface's contrast would change the others silently.
    """
    out = tuple(float(c) for c in fg)
    if contrast_ratio(out, bg) >= minimum:
        return out  # type: ignore[return-value]
    darker = relative_luminance(out) < relative_luminance(bg)
    factor = 0.97 if darker else 1.03
    for _ in range(64):
        if contrast_ratio(out, bg) >= minimum:
            return out  # type: ignore[return-value]
        out = tuple(min(1.0, max(0.0, c * factor)) for c in out)
    return out  # type: ignore[return-value] # pragma: no cover - 64 steps reach black or white


def rgb255(name: str) -> tuple[int, int, int]:
    """One palette colour as 0-255 integers, for renderers that work in bytes."""
    value = PALETTE[name].lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]

CROP_RULES = {
    "hero_aspect": (1, 1),          # Etsy's grid crops to square; compose for it
    "detail_aspect": (4, 5),
    "safe_margin_pct": 0.06,        # nothing meaningful inside the outer 6%
    "text_max_coverage_pct": 0.25,  # a hero is a photograph, not a poster
}

LIGHTING = {
    "direction": "soft directional from upper left",
    "temperature": "warm, 4800-5400K feel",
    "shadows": "soft, present -- never flat studio white",
    "background": "cream linen, pale oak or muted botanical",
}

FORBIDDEN_VISUAL = (
    "neon", "high-saturation gradient", "stock-photo glossiness",
    "cluttered collage hero", "rainbow palette", "hard flash shadow",
)

# ---- naming grammar --------------------------------------------------------

# Collection names are two words: a place-or-nature word, then a texture-or-object word.
# Constrained on purpose. An autonomous namer left free produces "Cozy Autumn Vibes Blanket
# Pattern Set", which reads as exactly the generic AI store the bible says to avoid.
NAME_FIRST = ("Nordic", "Autumn", "Cloudline", "Harvest", "Bramble", "Hollow", "Cottage",
              "Winter", "Meadow", "Thistle", "Alpine", "Orchard")
NAME_SECOND = ("Forest", "Oak", "Grove", "Fern", "Hearth", "Pine", "Loom", "Frost",
               "Bloom", "Stone", "Field", "Light")

_BANNED_IN_NAMES = re.compile(
    r"\b(cozy|vibes|amazing|ultimate|best|perfect|super|cute|adorable|trendy|must[- ]have|"
    r"stunning|gorgeous)\b", re.I)


def check_collection_name(name: str) -> list[str]:
    """A collection name is part of the brand, so it is checked like any other asset."""
    problems: list[str] = []
    words = name.strip().split()
    if len(words) != 2:
        problems.append(f"BRAND_NAME_SHAPE: {name!r} must be exactly two words")
    if _BANNED_IN_NAMES.search(name):
        problems.append(f"BRAND_NAME_GENERIC: {name!r} uses marketplace filler language")
    if words and words[0] not in NAME_FIRST:
        problems.append(f"BRAND_NAME_LEXICON: {words[0]!r} is not in the first-word lexicon")
    if len(words) > 1 and words[1] not in NAME_SECOND:
        problems.append(f"BRAND_NAME_LEXICON: {words[1]!r} is not in the second-word lexicon")
    return problems


# ---- the brand model -------------------------------------------------------

# Verbatim from the owner's character bible, held as data so drift is detectable rather than
# a matter of opinion.
MODEL_TRAITS: dict[str, str] = {
    "identity": "one recurring fictional adult woman, not a real person",
    "hair": "long, rich dark brown",
    "eyes": "striking light eyes",
    "brows": "strong, defined",
    "features": "refined and balanced, editorial",
    "expression": "warm and approachable",
    "makeup": "natural to polished, never heavy",
    "age_band": "adult, approximately 25-35",
    "styling": "premium but relatable; clothing suits the garment, season and setting",
}

MODEL_CONTINUITY = (
    "face proportions", "eye colour", "hair colour", "hair length",
    "body proportions", "approximate age",
)

# Products where the model is the wrong answer. Section 6 is explicit that product-first
# imagery is stronger for these, and a model draped in a blanket hides the pattern that the
# customer is actually buying.
MODEL_FORBIDDEN_CATEGORIES = frozenset({
    "mosaic_blanket", "blanket", "graphghan", "baby", "amigurumi", "ornament",
    "seasonal_decor", "basket", "coaster", "placemat", "runner", "pillow",
    "wall_decor", "flower", "pet", "tree_skirt", "stocking", "nursery",
})

MODEL_ALLOWED_CATEGORIES = frozenset({"garment", "hat", "scarf", "shawl", "bag"})


class RealPersonLikeness(ValueError):
    """A model description drifted toward a real, identifiable person."""


# Names the owner's brief explicitly warns against duplicating, plus the general rule. This
# list is not the safeguard -- the rule below is -- but a named celebrity is the one failure
# mode worth catching by name because it is the one somebody would type in on purpose.
_NAMED_PEOPLE = re.compile(
    r"\b(megan fox|angelina jolie|kendall jenner|gal gadot|ana de armas|zendaya|"
    r"look[- ]?alike of|lookalike of|based on the actress|resembling the celebrity)\b", re.I)


def check_model_prompt(text: str, category: str) -> list[str]:
    """Validate an image brief for the brand model before anything renders it."""
    problems: list[str] = []
    if _NAMED_PEOPLE.search(text):
        raise RealPersonLikeness(
            f"the brief names or references a real person: {_NAMED_PEOPLE.search(text).group(0)!r}. "
            f"The brand model is a fictional character and may not be built as a likeness of "
            f"anyone real, however the request is phrased.")
    if category in MODEL_FORBIDDEN_CATEGORIES:
        problems.append(
            f"BRAND_MODEL_WRONG_PRODUCT: {category!r} is product-first. A model holding a "
            f"blanket hides the pattern the customer is buying.")
    elif category not in MODEL_ALLOWED_CATEGORIES:
        problems.append(f"BRAND_MODEL_UNKNOWN_CATEGORY: {category!r} has no model policy")
    missing = [k for k in MODEL_CONTINUITY
               if k.split()[0].lower() not in text.lower()]
    if len(missing) > 2:
        problems.append(
            f"BRAND_MODEL_UNDERSPECIFIED: the brief fixes too few continuity traits "
            f"({sorted(set(MODEL_CONTINUITY) - set(missing))}); character drift is the "
            f"default outcome of a vague brief")
    return problems


def model_brief(category: str, garment: str, season: str | None = None) -> str:
    """Build a continuity-preserving brief. Every generation starts from the same sentence."""
    if category in MODEL_FORBIDDEN_CATEGORIES:
        raise ValueError(
            f"{category!r} is product-first; section 6 says not to use the model here")
    traits = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in MODEL_TRAITS.items())
    setting = f" Seasonal setting: {season}." if season else ""
    return (
        f"Recurring Brambleloop brand model, a fictional adult woman. {traits}. "
        f"Wearing a handmade crochet {garment}. Keep face proportions, eye colour, hair "
        f"colour, hair length, body proportions and approximate age identical to previous "
        f"approved references.{setting} Lighting: {LIGHTING['direction']}, "
        f"{LIGHTING['temperature']}. Background: {LIGHTING['background']}. "
        f"Not a likeness of any real person."
    )


# ---- grid coherence --------------------------------------------------------


@dataclass
class GridItem:
    slug: str
    title: str
    palette: dict[str, str]
    hero_class: str
    collection: str | None = None


@dataclass
class CoherenceReport:
    ok: bool
    problems: list[str] = field(default_factory=list)
    palette_share: float = 0.0
    hero_class_share: float = 0.0

    def to_dict(self) -> dict:
        return {"ok": self.ok, "problems": list(self.problems),
                "palette_share": round(self.palette_share, 3),
                "hero_class_share": round(self.hero_class_share, 3)}


def check_grid_coherence(items: list[GridItem], min_palette_share: float = 0.7,
                         min_hero_share: float = 0.7) -> CoherenceReport:
    """Does the storefront grid read as one shop?

    Two measurable proxies for a judgement nobody is around to make: how much of the grid
    draws from the brand palette, and how consistent the hero treatment is. A grid where
    every listing picked its own colours and its own hero style is the generic AI store the
    bible names as the thing to avoid.
    """
    problems: list[str] = []
    if not items:
        return CoherenceReport(ok=False, problems=["BRAND_GRID_EMPTY: nothing to assess"])

    brand_hexes = {v.lower() for v in PALETTE.values()}
    on_brand = 0
    for item in items:
        used = {v.lower() for v in item.palette.values()}
        if used and used <= brand_hexes:
            on_brand += 1
        elif used - brand_hexes:
            problems.append(
                f"BRAND_PALETTE_DRIFT: {item.slug} uses {sorted(used - brand_hexes)}")
    palette_share = on_brand / len(items)

    classes = [i.hero_class for i in items]
    dominant = max(set(classes), key=classes.count)
    hero_share = classes.count(dominant) / len(items)
    if hero_share < min_hero_share:
        problems.append(
            f"BRAND_HERO_INCONSISTENT: only {hero_share:.0%} of heroes are {dominant!r}; "
            f"a grid with mixed hero treatments reads as several shops")

    if palette_share < min_palette_share:
        problems.append(
            f"BRAND_PALETTE_SHARE_LOW: {palette_share:.0%} of listings are on-palette")

    for item in items:
        if item.collection:
            for p in check_collection_name(item.collection):
                problems.append(f"{item.slug}: {p}")

    return CoherenceReport(ok=not problems, problems=problems,
                           palette_share=palette_share, hero_class_share=hero_share)
