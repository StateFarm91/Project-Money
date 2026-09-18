"""Asset Truth Engine (Master Plan section 7, acceptance Gate C).

A listing image is a promise. If the hero shows a cabled motif the pattern cannot produce, or
the copy claims a queen-size blanket the gauge cannot reach, the customer finds out after
buying yarn -- which is a refund, a one-star review and a support case that all cost more than
the sale.

So imagery and claims are checked against the digital twin, which knows what the pattern
actually makes. Provenance is mandatory: an asset nobody can account for does not ship.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from ..cir.compiler import ERROR, WARNING, Finding
from ..cir.model import CIR
from ..cir.twin import TwinModel


class AssetClass(str, Enum):
    PHYSICAL_PRODUCT_PHOTO = "PHYSICAL_PRODUCT_PHOTO"
    DIGITAL_TWIN_RENDER = "DIGITAL_TWIN_RENDER"
    AI_LIFESTYLE_CONCEPT = "AI_LIFESTYLE_CONCEPT"
    INFOGRAPHIC = "INFOGRAPHIC"
    PATTERN_PREVIEW = "PATTERN_PREVIEW"


# How far a stated finished size may differ from the twin's computed size before it is a
# misrepresentation rather than rounding. Gauge genuinely varies; 10% is generous but finite.
SIZE_TOLERANCE = 0.10


@dataclass
class Provenance:
    source: str                      # "camera" | "twin" | "generator" | "designer"
    created_by: str                  # agent or person
    tool: str | None = None          # model / software identifier
    prompt_hash: str | None = None
    notes: str | None = None

    def is_complete(self) -> bool:
        return bool(self.source and self.created_by)


@dataclass
class Claims:
    """Customer-visible assertions attached to an asset or listing."""

    finished_width_cm: float | None = None
    finished_height_cm: float | None = None
    materials: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    difficulty: str | None = None
    time_hours: float | None = None
    size_label: str | None = None    # e.g. "throw", "queen"


@dataclass
class Asset:
    asset_id: str
    asset_class: AssetClass
    provenance: Provenance
    depicts_stitches: list[str] = field(default_factory=list)
    depicts_colors: list[str] = field(default_factory=list)
    depicts_components: list[str] = field(default_factory=list)
    claims: Claims = field(default_factory=Claims)
    is_hero: bool = False
    disclosed_as_illustration: bool = False


# Rough bed-size expectations in cm, used only to sanity-check a size *label* against the
# twin's computed dimensions. Deliberately wide.
SIZE_LABELS_CM: dict[str, tuple[float, float]] = {
    "baby": (70, 100),
    "lovey": (30, 45),
    "throw": (120, 170),
    "twin": (170, 220),
    "queen": (220, 260),
    "king": (260, 300),
}


def check_asset(
    asset: Asset, cir: CIR, twin: TwinModel, *, findings: list[Finding] | None = None
) -> list[Finding]:
    """Validate one asset against what the pattern actually produces."""
    out: list[Finding] = findings if findings is not None else []
    where = f"asset:{asset.asset_id}"

    if not asset.provenance.is_complete():
        out.append(Finding(ERROR, "ASSET_PROVENANCE",
                           "asset has incomplete provenance; it cannot be published", where))

    # --- depicted content must exist in the pattern ---
    real_stitches = twin.stitch_types_used
    for st in asset.depicts_stitches:
        if st not in real_stitches:
            out.append(Finding(
                ERROR, "ASSET_MOTIF_ABSENT",
                f"asset depicts {st!r} but the pattern never works that stitch "
                f"(pattern uses: {sorted(real_stitches)})", where))

    real_colors = twin.colors_used or set(cir.colors)
    for c in asset.depicts_colors:
        if c not in real_colors:
            out.append(Finding(
                ERROR, "ASSET_COLOR_ABSENT",
                f"asset depicts colour {c!r} which the pattern does not use "
                f"(pattern uses: {sorted(real_colors)})", where))

    real_components = {c.name for c in cir.components}
    for comp in asset.depicts_components:
        if comp not in real_components:
            out.append(Finding(
                ERROR, "ASSET_COMPONENT_ABSENT",
                f"asset depicts component {comp!r} which the pattern does not contain",
                where))

    # --- claims must be supported by the twin ---
    cl = asset.claims
    for label, claimed, actual in (
        ("width", cl.finished_width_cm, twin.width_cm),
        ("height", cl.finished_height_cm, twin.height_cm),
    ):
        if claimed is None:
            continue
        if actual is None:
            # The twin has no number for this dimension, which for a piece worked in the
            # round is a deliberate refusal rather than a gap: a closed shaped form takes
            # its finished size from stuffing and tension. Letting the claim through
            # unchecked because there is nothing to check it against is how an unverifiable
            # measurement reaches a listing.
            out.append(Finding(
                ERROR, "CLAIM_SIZE_UNVERIFIABLE",
                f"claims finished {label} of {claimed}cm, but the pattern supports no "
                f"{label} at the stated gauge"
                + (f": {twin.size_refusal}" if twin.size_refusal else ""), where))
            continue
        if actual <= 0:
            continue
        drift = abs(claimed - actual) / actual
        if drift > SIZE_TOLERANCE:
            out.append(Finding(
                ERROR, "CLAIM_SIZE_UNSUPPORTED",
                f"claims finished {label} of {claimed}cm but the pattern at the stated gauge "
                f"produces {actual}cm ({drift:.0%} off)", where))

    if cl.size_label:
        span = SIZE_LABELS_CM.get(cl.size_label.lower())
        biggest = max(filter(None, [twin.width_cm, twin.height_cm]), default=None)
        if span and biggest is not None and not (span[0] <= biggest <= span[1]):
            out.append(Finding(
                ERROR, "CLAIM_SIZE_LABEL_UNSUPPORTED",
                f"claims size {cl.size_label!r} (expects roughly {span[0]}-{span[1]}cm) but the "
                f"pattern's largest finished dimension is {biggest}cm", where))

    declared_materials = {m.name.lower() for m in cir.materials}
    for m in cl.materials:
        if declared_materials and m.lower() not in declared_materials:
            out.append(Finding(
                ERROR, "CLAIM_MATERIAL_UNSUPPORTED",
                f"claims material {m!r} which is not in the pattern's material list "
                f"({sorted(declared_materials)})", where))

    # Difficulty has to follow from what the pattern contains, in both directions. Claiming
    # "beginner" for something complex sets a buyer up to fail forty hours in; claiming
    # "advanced" for a two-stitch rectangle scares off the buyer it was made for and is just
    # as unsupported. The rule was previously only the first case, which left the gate line
    # "unsupported difficulty claims are blocked" half true.
    if cl.difficulty:
        stated = cl.difficulty.lower()
        advanced_stitches = {"tr", "dc_inc", "dc_dec"} & set(twin.stitch_types_used)
        colors_used = len([c for c in twin.colors_used if c])
        if stated == "beginner" and cir.risk_class == "C":
            out.append(Finding(
                ERROR, "CLAIM_DIFFICULTY_UNSUPPORTED",
                "claims beginner difficulty for a Class C (fitted/complex) pattern", where))
        elif stated == "beginner" and (advanced_stitches or colors_used > 2):
            out.append(Finding(
                ERROR, "CLAIM_DIFFICULTY_UNSUPPORTED",
                f"claims beginner difficulty, but the pattern uses "
                f"{sorted(advanced_stitches) or f'{colors_used} colours'}", where))
        elif stated in ("advanced", "expert") and not advanced_stitches and colors_used <= 2:
            out.append(Finding(
                ERROR, "CLAIM_DIFFICULTY_UNSUPPORTED",
                f"claims {stated} difficulty, but the pattern is "
                f"{sorted(twin.stitch_types_used)} in {colors_used} colour(s); overstating "
                f"difficulty turns away the buyer it was designed for", where))

    # --- honesty about what the image is ---
    #
    # Master Plan section 6 wants a consistent brand model; sections 7 and 27 want every
    # asset to be what it says it is. Those meet at a generated lifestyle image of a crochet
    # item, and the question -- flagged in BUILD_STATE to be decided deliberately rather than
    # by default -- is what such an image is allowed to imply.
    #
    # It is decided here, before anything in this system can produce one, because a rule set
    # after the first image exists is a rule argued against a sunk cost. An undisclosed
    # generated lifestyle image asserts that somebody photographed a finished object. For
    # every product in this catalogue that assertion is false in the strongest possible way:
    # zero physical samples exist, so there is no finished object anywhere in the world for a
    # photograph to be of. That is the same failure as a size claim the twin cannot support,
    # and it is not lessened by the image sitting in frame four instead of frame one -- a
    # buyer scrolling the gallery does not grade images by position.
    #
    # So it is an error wherever it appears, and being the hero is a second, separate error,
    # because the hero is the image that wins the click.
    if asset.asset_class is AssetClass.AI_LIFESTYLE_CONCEPT:
        if not asset.disclosed_as_illustration:
            out.append(Finding(
                ERROR, "ASSET_UNDISCLOSED_CONCEPT",
                "a generated lifestyle image is not disclosed as an illustration, so it "
                "asserts that someone photographed a finished object. No physical sample of "
                "this pattern exists, so there is nothing for such a photograph to be of",
                where))
        if asset.is_hero:
            out.append(Finding(
                ERROR, "ASSET_CONCEPT_AS_HERO",
                "a generated lifestyle image may not be the hero. The hero is the image that "
                "wins the click, and it has to be the thing the pattern actually makes",
                where))

    if asset.asset_class is AssetClass.PHYSICAL_PRODUCT_PHOTO and asset.provenance.source != "camera":
        out.append(Finding(
            ERROR, "ASSET_CLASS_MISMATCH",
            f"asset is labelled a physical product photo but its provenance source is "
            f"{asset.provenance.source!r}, not a camera", where))

    return out


# A product name is a claim about the shape of the object, and the least deniable kind. A
# buyer reading "Market Basket" expects something that stands up and holds things; a buyer
# reading "Hexagon Coaster Set" expects six sides. Both are checkable against the twin,
# because the twin knows whether the fabric is worked in the round and whether its rows are
# all the same width.
#
# Deliberately narrow. Mosaic and graphghan work legitimately *depicts* stars, hearts and
# flowers on rectangular fabric, so a motif word on its own proves nothing: "Star Blanket" is
# a blanket with stars, and fine. What is checked here are phrases that describe the object
# itself -- a shape word attached to the object noun, or a noun that can only be a
# three-dimensional thing.
_THREE_D_NOUNS = (
    "basket", "bag", "tote", "pouch", "purse", "backpack", "hat", "beanie", "bonnet",
    "sock", "mitten", "glove", "slipper", "bootie", "bowl", "vase", "planter",
    "amigurumi", "plushie", "plush", "doll", "bauble", "sphere", "cozy", "cosy",
)
# Stitch-pattern and motif names that merely contain a three-dimensional noun.
_THREE_D_EXCEPTIONS = ("basket weave", "basketweave", "bobble", "popcorn")

_OUTLINE_PATTERNS = (
    r"\b(hexagon|hexie|hexagonal|octagon|octagonal|pentagon)\b",
    r"\b(circle|circular)\b",
    r"\bround\s+(coaster|placemat|mat|rug|doily|trivet|cushion|pillow|pouf)\b",
    r"\b(star|heart|flower|leaf|oval)[-\s]shaped\b",
)


def check_shape_claims(text: str, cir: CIR, twin: TwinModel,
                       where: str = "product.title") -> list[Finding]:
    """Does the object the name describes match the object the pattern makes?"""
    out: list[Finding] = []
    low = " ".join(text.lower().split())
    if not low:
        return out

    stripped = low
    for exc in _THREE_D_EXCEPTIONS:
        stripped = stripped.replace(exc, " ")

    all_flat = all(c.construction == "flat_rows" for c in cir.components)
    promised = [n for n in _THREE_D_NOUNS if re.search(rf"\b{n}s?\b", stripped)]
    if promised and all_flat and not cir.makes_a_closed_form:
        out.append(Finding(
            ERROR, "CLAIM_CONSTRUCTION_UNSUPPORTED",
            f"name promises a {promised[0]}, which is a three-dimensional object, but every "
            f"component is worked in flat rows and the pattern contains nothing that joins "
            f"them into one. A flat panel sold as a {promised[0]} is a different product "
            f"from the one the buyer paid for", where))

    if twin.outline == "rectangle":
        for pattern in _OUTLINE_PATTERNS:
            m = re.search(pattern, low)
            if m:
                out.append(Finding(
                    ERROR, "CLAIM_SHAPE_UNSUPPORTED",
                    f"name claims a {m.group(0)!r} outline, but every row of the piece has "
                    f"the same stitch count, so the finished fabric is a rectangle. A motif "
                    f"worked *on* a rectangle is not the same claim as a shaped piece",
                    where))
                break

    return out


# A technique in the name is a claim about what the fabric *does*, and it is the least
# deniable kind after shape. "Heirloom Cable Throw" was worked entirely in single and double
# crochet: no crossing anywhere in it. So were "Bobble Floor Pillow" and "Chunky Ribbed
# Scarf". All three were certified, and none of the existing checks could see it, because the
# shape check looks at silhouettes and the asset check looks at what an image depicts.
#
# Each entry is a phrase and the stitches that would have to appear for it to be true.
# Deliberately short: only techniques this taxonomy can actually express, because a check
# that fires on a word the system has no stitch for would be unfixable by construction.
_TECHNIQUE_CLAIMS: tuple[tuple[str, frozenset[str], str], ...] = (
    (r"\bcable[ds]?\b|\bcabled\b", frozenset({"cable2x2", "cable1x1"}),
     "a cable is a crossing: stitches worked out of order around each other"),
    (r"\bbobble[sd]?\b|\bpopcorn\b", frozenset({"bob"}),
     "a bobble is several incomplete stitches closed together in one stitch"),
    (r"\brib(?:bed|bing)\b|\bwaffle\b", frozenset({"fpdc", "bpdc"}),
     "ribbing and waffle texture come from post stitches worked around the stitch below"),
)

# Mosaic is a colour technique rather than a stitch one, so it is checked differently: one
# colour cannot make a mosaic whatever stitches are used.
_MOSAIC_RE = r"\bmosaic\b"


def check_technique_claims(text: str, cir: CIR, twin: TwinModel,
                           where: str = "product.title") -> list[Finding]:
    """Does the fabric do what the name says it does?"""
    out: list[Finding] = []
    low = " ".join(text.lower().split())
    if not low:
        return out

    worked = set(twin.stitch_types_used)
    for pattern, required, explanation in _TECHNIQUE_CLAIMS:
        if not re.search(pattern, low):
            continue
        if worked & required:
            continue
        out.append(Finding(
            ERROR, "CLAIM_TECHNIQUE_UNSUPPORTED",
            f"name claims a technique the pattern does not work: {explanation}, and this "
            f"pattern works only {sorted(worked)}. Either the design changes or the name "
            f"does", where))

    if re.search(_MOSAIC_RE, low):
        colours = len([c for c in twin.colors_used if c])
        if colours < 2:
            out.append(Finding(
                ERROR, "CLAIM_TECHNIQUE_UNSUPPORTED",
                f"name claims mosaic colourwork but the pattern uses {colours} colour(s)",
                where))

    return out


def check_assets(assets: list[Asset], cir: CIR, twin: TwinModel) -> list[Finding]:
    out: list[Finding] = []
    for a in assets:
        check_asset(a, cir, twin, findings=out)

    heroes = [a for a in assets if a.is_hero]
    if not heroes:
        out.append(Finding(ERROR, "ASSET_NO_HERO", "listing has no hero image"))
    elif len(heroes) > 1:
        out.append(Finding(ERROR, "ASSET_MULTIPLE_HEROES",
                           f"listing declares {len(heroes)} hero images"))
    return out
