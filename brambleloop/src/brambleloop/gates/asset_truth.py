"""Asset Truth Engine (Master Plan section 7, acceptance Gate C).

A listing image is a promise. If the hero shows a cabled motif the pattern cannot produce, or
the copy claims a queen-size blanket the gauge cannot reach, the customer finds out after
buying yarn -- which is a refund, a one-star review and a support case that all cost more than
the sale.

So imagery and claims are checked against the digital twin, which knows what the pattern
actually makes. Provenance is mandatory: an asset nobody can account for does not ship.
"""
from __future__ import annotations

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
        if claimed is None or actual is None:
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
    if asset.asset_class is AssetClass.AI_LIFESTYLE_CONCEPT:
        if asset.is_hero and not asset.disclosed_as_illustration:
            out.append(Finding(
                ERROR, "ASSET_UNDISCLOSED_CONCEPT",
                "an AI lifestyle concept is being used as the hero image without being "
                "disclosed as an illustration; the hero reads as a photograph of a finished "
                "object that does not exist", where))
        elif not asset.disclosed_as_illustration:
            out.append(Finding(
                WARNING, "ASSET_CONCEPT_UNDISCLOSED",
                "AI lifestyle concept is not marked as an illustration", where))

    if asset.asset_class is AssetClass.PHYSICAL_PRODUCT_PHOTO and asset.provenance.source != "camera":
        out.append(Finding(
            ERROR, "ASSET_CLASS_MISMATCH",
            f"asset is labelled a physical product photo but its provenance source is "
            f"{asset.provenance.source!r}, not a camera", where))

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
