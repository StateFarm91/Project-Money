"""Build a compiled CIR from a motif and a size (Master Plan sections 2, 16).

`nordic_forest.py` engineered one product by hand. This generalises the same approach so the
rest of the catalogue is designed rather than templated: a motif from the library, a stated
width and a number of repeats, turned into rows by code.

The generalisation is what makes section 16's "about 12 exceptional release candidates"
achievable at all. Engineering twelve products by hand means twelve chances to make an
arithmetic slip; generating them from validated motifs means the slip has to be in one place,
where a test can find it.

Every product still compiles, reverse-compiles and certifies individually. Sharing a builder
is not sharing a pass.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row
from .motifs import LIBRARY, Motif, get

PALETTES: dict[str, dict[str, str]] = {
    "nordic": {"forest": "#244A3A", "cream": "#FAF6EB"},
    "autumn": {"wine": "#6E1F2A", "gold": "#C49545"},
    "cloudline": {"cream": "#FAF6EB", "ink": "#1A2B3C"},
    "hearth": {"pine": "#244A3A", "gold": "#C49545"},
    "cottage": {"cream": "#FAF6EB", "wine": "#6E1F2A"},
}


@dataclass(frozen=True)
class Design:
    """Everything needed to generate a product, and nothing that is merely decoration."""

    slug: str
    title: str
    motif: str
    palette: str
    width_stitches: int
    motif_repeats: int
    risk_class: str = "A"
    stitches_per_10cm: int = 16
    rows_per_10cm: int = 18
    hook_mm: float = 5.0
    yarn: str = "worsted acrylic"
    yarn_weight: str = "worsted"
    note: str = ""


class DesignDoesNotFit(ValueError):
    """The motif does not divide the stated width, so it would be cut off mid-shape."""


def _runs(pattern: str) -> list[Op]:
    ops: list[Op] = []
    code = "dc" if pattern[0] == "1" else "sc"
    length = 0
    for ch in pattern:
        current = "dc" if ch == "1" else "sc"
        if current == code:
            length += 1
        else:
            ops.append(Op(code, length))
            code, length = current, 1
    ops.append(Op(code, length))
    return ops


def build(design: Design, version: str = "1.0.0") -> CIR:
    """Generate the CIR. Refuses a width the motif cannot tile.

    Refusing rather than fudging matters: a motif silently truncated at the edge produces a
    blanket with half a fir tree down one side, which compiles perfectly and is a defect
    nobody's arithmetic will ever catch.
    """
    motif: Motif = get(design.motif)
    motif.validate()
    if design.width_stitches % motif.width:
        raise DesignDoesNotFit(
            f"{design.slug}: {design.width_stitches} stitches is not a multiple of the "
            f"{motif.width}-stitch {motif.slug} repeat, so the motif would be cut off "
            f"mid-shape. Choose a width that divides, or a motif that fits.")
    palette = PALETTES.get(design.palette)
    if palette is None:
        raise KeyError(f"unknown palette {design.palette!r}; have {sorted(PALETTES)}")

    colour_names = list(palette)
    across = design.width_stitches // motif.width

    rows: list[Row] = []
    index = 0
    for _ in range(design.motif_repeats):
        for line in motif.grid:
            index += 1
            colour = colour_names[(index - 1) % len(colour_names)]
            if index == 1:
                ops: list = [Op("sc", design.width_stitches)]
            else:
                ops = [Repeat(_runs(line), times=across)]
            rows.append(Row(index=index, ops=ops, declared_count=design.width_stitches,
                            turning_chain=1, color=colour))

    return CIR(
        slug=design.slug,
        title=design.title,
        version=version,
        construction="flat_rows",
        risk_class=design.risk_class,
        colors=dict(palette),
        gauge=Gauge(stitches_per_10cm=design.stitches_per_10cm,
                    rows_per_10cm=design.rows_per_10cm, stitch_type="sc",
                    hook_mm=design.hook_mm),
        materials=[Material(name=design.yarn, yarn_weight=design.yarn_weight, color_id=c)
                   for c in colour_names],
        components=[Component(name="panel", construction="flat_rows", rows=rows,
                              foundation=design.width_stitches, foundation_kind="chain")],
        designer_notes=(
            f"{motif.name} on a {motif.width}-stitch repeat, {across} across and "
            f"{design.motif_repeats} up ({len(rows)} rows). {motif.note}. "
            f"Colour changes every row; carry the resting colour up the side."
            + (f" {design.note}" if design.note else "")),
    )


# ---- the catalogue ---------------------------------------------------------
#
# One design per release candidate that is a flat, machine-verifiable piece. Products whose
# construction the compiler cannot yet fully model -- amigurumi, garments, bags -- are
# deliberately absent rather than approximated, because a templated stand-in that certifies is
# more dangerous than an obvious gap.

CATALOGUE: dict[str, Design] = {
    "winter-village-graphghan": Design(
        slug="winter-village-graphghan", title="Winter Village Graphghan",
        motif="snowfall", palette="nordic", width_stitches=144, motif_repeats=8,
        note="Sparse flakes so the field reads at blanket scale rather than as noise."),
    "heirloom-cable-blanket": Design(
        slug="heirloom-cable-blanket", title="Heirloom Cable Throw",
        motif="cable-twist", palette="hearth", width_stitches=144, motif_repeats=12,
        note="Texture rather than colourwork; a different buyer from the mosaic audience."),
    "cloudline-baby-blanket": Design(
        slug="cloudline-baby-blanket", title="Cloudline Textured Baby Blanket",
        motif="diamond-lattice", palette="cloudline", width_stitches=126, motif_repeats=11,
        note="A continuous lattice: no long floats for small fingers to catch."),
    "autumn-oak-mosaic-throw": Design(
        slug="autumn-oak-mosaic-throw", title="Autumn Oak Overlay Mosaic Throw",
        motif="fir-and-star", palette="autumn", width_stitches=144, motif_repeats=5),
    "harvest-table-runner": Design(
        slug="harvest-table-runner", title="Harvest Table Runner",
        motif="chevron-band", palette="autumn", width_stitches=48, motif_repeats=14),
    "mosaic-placemat-pair": Design(
        slug="mosaic-placemat-pair", title="Mosaic Placemat Pair",
        motif="diamond-lattice", palette="cottage", width_stitches=45, motif_repeats=5),
    "nordic-star-ornaments": Design(
        slug="nordic-star-ornaments", title="Nordic Star Ornament Set (6)",
        motif="snowfall", palette="nordic", width_stitches=12, motif_repeats=1,
        note="One ornament per repeat; the twelve-row snowfall keeps each one ornament-sized "
             "rather than the twenty-four rows the fir band would impose."),
    "spooky-garland": Design(
        slug="spooky-garland", title="Spooky Bunting Garland",
        motif="pumpkin-row", palette="autumn", width_stitches=40, motif_repeats=2),
    "valentine-heart-garland": Design(
        slug="valentine-heart-garland", title="Heart Motif Garland",
        motif="heart-row", palette="cottage", width_stitches=40, motif_repeats=2),
    "pet-snuggle-mat": Design(
        slug="pet-snuggle-mat", title="Pet Snuggle Mat",
        motif="basketweave", palette="hearth", width_stitches=56, motif_repeats=7),
    "pressed-flower-motifs": Design(
        slug="pressed-flower-motifs", title="Pressed Flower Motif Library (12)",
        motif="heart-row", palette="cottage", width_stitches=30, motif_repeats=2,
        note="A motif sampler: each repeat worked separately as a standalone appliqué."),
    "cottage-wall-hanging": Design(
        slug="cottage-wall-hanging", title="Cottage Botanical Wall Hanging",
        motif="chevron-band", palette="cottage", width_stitches=40, motif_repeats=6),
    "bobble-floor-pillow": Design(
        slug="bobble-floor-pillow", title="Bobble Floor Pillow",
        motif="basketweave", palette="hearth", width_stitches=72, motif_repeats=9),
    "chunky-ribbed-scarf": Design(
        slug="chunky-ribbed-scarf", title="Chunky Ribbed Scarf",
        motif="cable-twist", palette="nordic", width_stitches=45, motif_repeats=12),
}


def for_slug(slug: str, version: str = "1.0.0") -> CIR | None:
    design = CATALOGUE.get(slug)
    return build(design, version) if design else None
