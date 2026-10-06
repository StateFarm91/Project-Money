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

from dataclasses import dataclass, replace

from ..cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row
from ..gates.originality import catalogue_provenance
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


def _drawn_size_cm(design: Design, motif: Motif) -> tuple[float, float]:
    """The finished size a design's typed counts make at its typed gauge, as the twin
    measures it (a row is as tall as its tallest stitch). This is the design's intent."""
    from ..cir import stitches

    width = design.width_stitches * 10.0 / design.stitches_per_10cm
    return width, design.motif_repeats * _repeat_height_cm(motif, design.rows_per_10cm,
                                                           stitches)


def _repeat_height_cm(motif: Motif, rows_per_10cm: float, stitches) -> float:
    """One repeat's height by the tallest-stitch rule the typed counts were DRAWN with: this
    is the design-intent size only (`_drawn_size_cm`), never what a finished piece measures."""
    tall = stitches.get("dc").row_height / (stitches.get("sc").row_height or 1.0)
    return sum((tall if "1" in line else 1.0) for line in motif.grid) * 10.0 / rows_per_10cm


def _measured_repeat_height_cm(motif: Motif, rows_per_10cm: float, stitches) -> float:
    """One repeat's height as the twin measures it: the stitch-weighted row height
    (`cir.geometry.HEIGHT_RULE`, PT-08). Counts are chosen with this rule so the size the
    pattern states is the size its own rows make, at the design's drawn intent."""
    from ..cir.geometry import mix_height_units

    base = stitches.get("sc").row_height or 1.0
    return sum(mix_height_units((("dc", line.count("1")), ("sc", line.count("0"))), base)
               for line in motif.grid) * 10.0 / rows_per_10cm


def _derive_from_yarn(design: Design) -> Design:
    """The same design at the gauge its declared yarn actually holds, counts recomputed to
    the nearest whole motif of the size it was drawn at. A motif is never cut, so a piece
    smaller than one motif at the new gauge is one motif, and the size it states is the
    size its counts make."""
    from ..cir import stitches
    from ..creative.prototype import gauge_for

    motif = get(design.motif)
    gauge = gauge_for(design.yarn_weight)
    width_cm, height_cm = _drawn_size_cm(design, motif)
    across = max(1, int(width_cm * gauge.stitches_per_10cm / (10.0 * motif.width) + 0.5))
    repeats = max(1, int(height_cm / _measured_repeat_height_cm(motif, gauge.rows_per_10cm,
                                                                stitches) + 0.5))
    return replace(design, width_stitches=across * motif.width, motif_repeats=repeats,
                   stitches_per_10cm=gauge.stitches_per_10cm,
                   rows_per_10cm=gauge.rows_per_10cm, hook_mm=gauge.hook_mm)


def build(design: Design, version: str = "1.0.0") -> CIR:
    """Generate the CIR. Refuses a width the motif cannot tile.

    Refusing rather than fudging matters: a motif silently truncated at the edge produces a
    blanket with half a fir tree down one side, which compiles perfectly and is a defect
    nobody's arithmetic will ever catch.
    """
    border_rows = 0
    catalogued = design == CATALOGUE.get(design.slug)
    cloudline = design.slug == "cloudline-baby-blanket" and catalogued
    if cloudline:
        # D-FB-6 authorized design revision: complete diamonds, with explicit equal
        # SC end borders. Published yarn gauge is the input; counts follow it.
        #
        # 1.2.0 (PT-08, PT-09, 2026-10-06): the length is computed with the stitch-weighted
        # row height every other measurement now uses (a sc row carrying one dc in nine is
        # 1.11 sc tall, not 2.0), and the colour changes every TWO rows. Two-row stripes put
        # every change at the same side edge, where the colour not in use is resting, so
        # "carry the resting colour up the side" is an instruction the fabric can obey; the
        # one-row stripes it replaced needed the yarn cut and rejoined at every change. The
        # end borders are an even number of rows for the same reason.
        from ..cir import stitches as _st
        from ..creative.prototype import gauge_for
        gauge = gauge_for(design.yarn_weight)
        motif = get(design.motif)
        across = round(78.8 * gauge.stitches_per_10cm / (10 * motif.width))
        target_units = 97.2 * gauge.rows_per_10cm / 10
        sc_h = _st.get("sc").row_height or 1.0
        dc_h = _st.get("dc").row_height
        repeat_units = sum(1.0 + line.count("1") / len(line) * (dc_h / sc_h - 1.0)
                           for line in motif.grid)
        candidates = [(abs(repeats * repeat_units + 2 * ends - target_units), ends, repeats)
                      for repeats in range(1, int(target_units / repeat_units) + 2)
                      # a border, not a second field: at most six plain rows at each end
                      for ends in range(2, 7, 2)]
        _, border_rows, repeats = min(candidates)
        design = replace(design, width_stitches=across * motif.width, motif_repeats=repeats,
                         stitches_per_10cm=gauge.stitches_per_10cm,
                         rows_per_10cm=gauge.rows_per_10cm, hook_mm=gauge.hook_mm)
    elif design.slug in YARN_DERIVED and catalogued:
        design = _derive_from_yarn(design)
    if version == "1.0.0" and catalogued:
        version = RELEASE_VERSIONS.get(design.slug, version)
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
    stripe = 2 if cloudline else 1

    rows: list[Row] = []
    index = 0
    for _ in range(design.motif_repeats):
        for line in motif.grid:
            index += 1
            if cloudline:
                # Two-row stripes, the first in the contrast colour so the cream border
                # reads as a border.
                colour = colour_names[1 - ((index - 1) // stripe) % len(colour_names)]
            else:
                colour = colour_names[(index - 1) % len(colour_names)]
            if index == 1:
                ops: list = [Op("sc", design.width_stitches)]
            else:
                ops = [Repeat(_runs(line), times=across)]
            rows.append(Row(index=index, ops=ops, declared_count=design.width_stitches,
                            turning_chain=1, color=colour))

    if border_rows:
        # Restore the full first diamond row: the plain foundation is now in the border.
        rows[0].ops = [Repeat(_runs(motif.grid[0]), times=across)]
        def edge():
            return Row(index=0, ops=[Op("sc", design.width_stitches)],
                       declared_count=design.width_stitches, turning_chain=1,
                       color=colour_names[0])
        rows = ([edge() for _ in range(border_rows)] + rows
                + [edge() for _ in range(border_rows)])
        for index, row in enumerate(rows, 1):
            row.index = index
    if cloudline:
        # A row that starts with a double crochet turns with two chains (not counted as a
        # stitch), so the edge dc is not dragged down to a single-crochet turning height.
        for row in rows:
            first = row.ops[0]
            while isinstance(first, Repeat):
                first = first.ops[0]
            if first.stitch == "dc":
                row.turning_chain = 2

    # What the colour changes ask of the maker, read off the rows rather than asserted
    # (`cir.colour_changes`, PT-09).
    from ..cir.colour_changes import plan_component

    probe = plan_component(Component(name="panel", construction="flat_rows", rows=rows,
                                     foundation=design.width_stitches,
                                     foundation_kind="chain"))
    if probe.changes and probe.carry_is_possible:
        colour_note = (f"Colour changes every {'two rows' if stripe == 2 else 'row'}, so every "
                       f"change falls at the same side edge: carry the resting colour loosely "
                       f"up that edge. ")
    elif probe.changes:
        colour_note = ("Colour changes every row. The rows turn, so the colour not in use is "
                       "always resting at the far edge when it is next needed: cut it and "
                       "rejoin at each change, and weave in the ends (see Finishing). ")
    else:
        colour_note = ""

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
            + (f"{design.motif_repeats} up ({design.motif_repeats * len(motif.grid)} motif rows). "
               if border_rows else f"{design.motif_repeats} up ({len(rows)} rows). ")
            + f"{motif.note}. "
            + colour_note
            + (f"Work {border_rows} single-crochet rows in {colour_names[0]} at each end "
               f"around the full diamond region; {len(rows)} rows total. " if border_rows
               else "")
            + (f" {design.note}" if design.note else "")),
        # F-783: where this design came from. Built from the Brambleloop motif library and
        # palette table by this module's deterministic tiler; no benchmark was consulted.
        provenance=catalogue_provenance(
            design.slug, {"builder": "products.builder.build", "design": vars(design),
                          "motif_grid": list(motif.grid)},
            ("products.builder", f"products.motifs:{motif.slug}",
             f"products.builder.PALETTES:{design.palette}")),
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
    "cloudline-baby-blanket": Design(
        slug="cloudline-baby-blanket", title="Cloudline Textured Baby Blanket",
        motif="diamond-lattice", palette="cloudline", width_stitches=126, motif_repeats=11,
        # Was "A continuous lattice: no long floats for small fingers to catch." There are no
        # floats in this fabric to be long or short: it works one colour per row and carries
        # the resting colour up the side edge, so the note described stranded colourwork this
        # pattern does not make -- and did it as reassurance about a child's safety, attached
        # to a hazard the product does not have. `gates.asset_truth` now refuses the claim.
        # And it says what the fabric IS rather than what it is not. The first correction read
        # "a relief rather than colourwork", which `launch0.fabric_truth` refused: that gate
        # matches the word "colourwork" anywhere in the title or notes and cannot read a
        # negation, and it is right not to try -- a note that mentions stranded colourwork on a
        # one-colour-per-row fabric still puts the wrong picture in a buyer's head, exactly as
        # the float claim did.
        note="The lattice is a relief: double crochet standing above a single-crochet "
             "ground, one colour per row."),
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
}


# D-FB-6 re-engineering of the flat catalogue (Cloudline has its own authorized border
# redesign in `build`). Each design here has its gauge derived from its declared yarn's
# published band (`creative.prototype.gauge_for`) and its stitch and row counts recomputed,
# in whole motif repeats, to the size it was drawn at (`_derive_from_yarn`); its default
# version becomes 1.1.0 because its content changed. Every Design still records the typed
# 16 sc/10cm it was drawn at -- that is the record of the intent the counts are derived from.
#
# Held back, with the reason recorded rather than faked:
LEGACY_HELD: dict[str, str] = {
    "autumn-oak-mosaic-throw": (
        "kept as the legacy record of a typed out-of-band gauge (16 sc/10cm against worsted): "
        "the gauge gate refuses it and tests/test_launch0_gauge.py pins that refusal, the "
        "proof that no catalogue design gains a pass except by re-engineering. It is not "
        "routed to a certificate until it is re-engineered here"),
    "cloudline-baby-blanket": "re-engineered separately: the D-FB-6 border redesign in build()",
}
YARN_DERIVED: frozenset[str] = frozenset(CATALOGUE) - frozenset(LEGACY_HELD)

# The released version of each catalogue design, applied when a caller asks for the default.
# A design's content (its CIR, or a customer-visible figure the twin derives from it) cannot
# change under a released version: tests/data/release_fingerprints.tsv pins both.
#
# 1.1.0: D-FB-6 (a8ed44f) re-derived gauge and counts.
# 1.2.0 (2026-10-06): PT-07/PT-08/PT-09 -- yardage counted per stitch once (increases were
# double-counted), row height by the stitch-weighted rule (a sc row with a few dc in it is no
# longer measured as a dc row), and colour-change notes that the rows can actually obey.
RELEASE_VERSIONS: dict[str, str] = {slug: "1.2.0" for slug in CATALOGUE}
RELEASE_VERSIONS["autumn-oak-mosaic-throw"] = "1.1.0"   # LEGACY_HELD, never re-derived


def for_slug(slug: str, version: str = "1.0.0") -> CIR | None:
    design = CATALOGUE.get(slug)
    return build(design, version) if design else None
