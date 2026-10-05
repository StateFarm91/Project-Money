"""Texture designs: the ones whose names were claims the fabric did not honour.

Three products in the catalogue were named for techniques their patterns could not contain.
"Heirloom Cable Throw", "Bobble Floor Pillow" and "Chunky Ribbed Scarf" were all worked
entirely in single and double crochet colourwork -- no crossing, no bobble, no rib anywhere in
any of them. One of the three was the fourth-ranked product in the selected portfolio, with a
certificate and a drafted listing in production.

That is the flat-panel-called-a-basket defect in a different dimension, and the fix is the
same: make the claim true rather than soften the wording. So these are built out of stitches
that actually do the thing -- post stitches for ribbing, closed clusters for bobbles, and
crossings for cables -- and `gates.asset_truth.check_technique_claims` now blocks any product
whose name says otherwise.

Every design here is generated the same way the motif catalogue is: a repeat that divides the
width exactly, a row count that divides the cycle exactly so the written pattern collapses,
and arithmetic the compiler checks rather than a designer's confidence.
"""
from __future__ import annotations

from ..cir import stitches as _stitches
from ..cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row
from ..creative.prototype import gauge_for
from ..gates.originality import catalogue_provenance

# The worsted gauge is derived from the declared yarn's published single-crochet band
# (D-FB-6, F-116). It used to be a typed 16 sc/18 rows per 10cm against worsted -- a fabric
# worsted cannot make (band 11-14) -- so the cable throw and the bobble pillow stated sizes and
# yardage from a gauge their own yarn could not hold. Their stitch and row counts are now
# recomputed from this gauge to keep the finished sizes the designs were drawn at
# (`CABLE_TARGET_CM`, `PILLOW_TARGET_CM`).
WORSTED = gauge_for("worsted")
# 11 sc/10cm sits inside the published bulky band (8-11), so the scarf's gauge is evidenced by
# its declared yarn as typed; it is not re-derived, and its counts are unchanged.
CHUNKY = Gauge(stitches_per_10cm=11, rows_per_10cm=13, stitch_type="sc", hook_mm=6.5)

# The cushion pad this cover is designed around. Named once, because it appears in the
# sizing arithmetic and in the sentence the buyer reads, and those two must not drift.
PAD_CM = 45.0

# Intended finished (width, height) in cm of the two worsted designs: the sizes their counts
# made when they were drawn (70 sts x 13 bobble blocks; 144 sts x 30 cable blocks, as the twin
# measured them). Counts follow the derived gauge in whole repeats and whole blocks, so the
# stated size is what the counts make, within one repeat of this intent.
PILLOW_TARGET_CM = (43.8, 43.9)
CABLE_TARGET_CM = (90.0, 128.9)

PINE = {"pine": "#244A3A"}
HEARTH = {"gold": "#C49545"}
CREAM = {"cream": "#FAF6EB"}


class DoesNotDivide(ValueError):
    """The repeat does not tile the width, so the last one would be cut off mid-shape."""


def _check(width: int, repeat: int, label: str) -> int:
    if width % repeat:
        raise DoesNotDivide(
            f"{label}: {width} stitches is not a multiple of the {repeat}-stitch repeat, so "
            f"the last one would be cut off")
    return width // repeat


def across_cm(stitches: int, gauge: Gauge) -> float:
    """How wide `stitches` actually measures at this gauge.

    Every size sentence in this file is built from this rather than typed beside the stitch
    count, because a number typed beside a count is a second copy of it, and the two only
    agree until somebody changes one of them.
    """
    return stitches / gauge.stitches_per_10cm * 10.0


def _nearest(target: float, unit: float) -> int:
    """Whole units closest to `target`, never fewer than one."""
    return max(1, int(target / unit + 0.5))


def _row_height_cm(codes: tuple[str, ...], gauge: Gauge) -> float:
    """One row's height, as the twin measures it: as tall as its tallest stitch."""
    base = _stitches.get(gauge.stitch_type).row_height or 1.0
    tallest = max(_stitches.get(c).row_height for c in codes)
    return 10.0 / gauge.rows_per_10cm * (tallest / base)


def build_ribbed_scarf(version: str = "1.0.0") -> CIR:
    """Post-stitch ribbing: fpdc and bpdc in the same columns on every row.

    Ribbing is not a colour effect and cannot be imitated by one. Working the post stitches
    into the same columns each row is what makes the ribs stand up and the fabric stretch,
    and it is why the previous "Chunky Ribbed Scarf" -- plain single and double crochet in
    two colours -- was a scarf with a name it had not earned.
    """
    width = 24            # a scarf, not a wrap
    across = _check(width, 4, "ribbed scarf")
    relaxed_cm = across_cm(width, CHUNKY)

    rows = [Row(index=1, ops=[Op("sc", width)], declared_count=width, color="pine",
                turning_chain=1)]
    # 100 ribbing rows: about 147 cm long, and a multiple of four so the writer collapses
    # them into one instruction instead of printing the same line a hundred times.
    for index in range(2, 102):
        rows.append(Row(index=index,
                        ops=[Repeat([Op("fpdc", 2), Op("bpdc", 2)], times=across)],
                        declared_count=width, color="pine", turning_chain=2))

    return CIR(
        slug="chunky-ribbed-scarf",
        title="Chunky Ribbed Scarf",
        version=version,
        construction="flat_rows",
        risk_class="A",
        colors=dict(PINE),
        gauge=CHUNKY,
        materials=[Material(name="chunky acrylic", yarn_weight="chunky", colorway="pine",
                            color_id="pine")],
        components=[Component(name="scarf", construction="flat_rows", rows=rows,
                              foundation=width)],
        finished_size_note=(
            f"Ribbing stretches, so the width is given relaxed. Worked at the stated gauge "
            f"it measures about {relaxed_cm:.0f} cm across unstretched."),
        designer_notes=("Every row works front and back post stitches into the same columns, "
                        "which is what makes the rib stand up rather than merely look "
                        "striped."),
        # F-783: generic post-stitch ribbing sized by this module; no benchmark consulted.
        provenance=catalogue_provenance(
            "chunky-ribbed-scarf",
            {"builder": "products.texture.build_ribbed_scarf", "width": width, "rows": 101,
             "rib": "fpdc2/bpdc2", "gauge": vars(CHUNKY)},
            ("products.texture", "post_stitch_ribbing")),
    )


def build_bobble_pillow(version: str = "1.0.0") -> CIR:
    """A staggered bobble grid on a single crochet ground.

    The bobbles alternate position every second bobble row, which is what makes a grid rather
    than columns. A bobble costs about five double crochets of yarn in one stitch's width, so
    the estimate for this piece is dominated by them -- which is why the yarn table carries a
    real figure for `bob` instead of falling back to a default that would have understated a
    cushion by a third.
    """
    # A little under the pad on purpose, so the pad fills the cover out rather than swimming
    # in it. The figure that goes on the listing is computed below rather than written here:
    # a centimetre count typed beside a stitch count is the second copy that went wrong last
    # time, when the note claimed this panel was wider than the pad it is narrower than.
    across = _nearest(PILLOW_TARGET_CM[0], 5 * 10.0 / WORSTED.stitches_per_10cm)
    width = across * 5
    _check(width, 5, "bobble pillow")
    block_cm = (2 * _row_height_cm(("sc",), WORSTED)
                + 2 * _row_height_cm(("sc", "bob"), WORSTED))
    blocks = _nearest(PILLOW_TARGET_CM[1] - _row_height_cm(("sc",), WORSTED), block_cm)
    panel_cm = across_cm(width, WORSTED)
    # Stated in the sentence below rather than assumed by it: which way round the panel and
    # the pad sit is worked out from the arithmetic, not typed.
    difference = PAD_CM - panel_cm
    fit = (f"{difference:.1f} cm narrower than the pad" if difference > 0
           else f"{-difference:.1f} cm wider than the pad" if difference < 0
           else "exactly the pad's width")

    rows: list[Row] = [Row(index=1, ops=[Op("sc", width)], declared_count=width,
                           color="gold", turning_chain=1)]
    index = 1
    # Four-row blocks: plain, bobbles, plain, bobbles offset. The offset is the difference
    # between a grid and a set of columns.
    for _ in range(blocks):
        index += 1
        rows.append(Row(index=index, ops=[Op("sc", width)], declared_count=width,
                        color="gold", turning_chain=1))
        index += 1
        rows.append(Row(index=index,
                        ops=[Repeat([Op("sc", 4), Op("bob")], times=across)],
                        declared_count=width, color="gold", turning_chain=1))
        index += 1
        rows.append(Row(index=index, ops=[Op("sc", width)], declared_count=width,
                        color="gold", turning_chain=1))
        index += 1
        rows.append(Row(index=index,
                        ops=[Repeat([Op("sc", 2), Op("bob"), Op("sc", 2)], times=across)],
                        declared_count=width, color="gold", turning_chain=1))

    return CIR(
        slug="bobble-floor-pillow",
        title="Bobble Floor Pillow Cover",
        version=version,
        construction="flat_rows",
        risk_class="B",
        colors=dict(HEARTH),
        gauge=WORSTED,
        materials=[Material(name="worsted acrylic", yarn_weight="worsted", colorway="gold",
                            color_id="gold")],
        components=[Component(name="front", construction="flat_rows", rows=rows,
                              foundation=width,
                              note="The front panel. The back is a plain panel of the same "
                                   "stitch and row count.")],
        designer_notes=("Class B: the arithmetic and the fabric are verifiable, but a cushion "
                        "cover's fit around a pad depends on how firmly it is worked, so "
                        "nothing is claimed about that until a physical sample says so."),
        finished_size_note=(
            f"Sized for a {PAD_CM:.0f} cm floor cushion pad. The panel measures about "
            f"{panel_cm:.1f} cm across at the stated gauge -- {fit} -- so the pad fills the "
            f"cover out instead of swimming in it. Bobble fabric draws in as well, so work "
            f"the gauge swatch in pattern rather than in plain single crochet."),
        # F-783: a staggered bobble grid sized to the pad by this module.
        provenance=catalogue_provenance(
            "bobble-floor-pillow",
            {"builder": "products.texture.build_bobble_pillow", "width": width,
             "blocks": blocks, "pad_cm": PAD_CM, "gauge": vars(WORSTED)},
            ("products.texture", "staggered_bobble_grid")),
    )


def build_cable_throw(version: str = "1.0.0") -> CIR:
    """Cable columns separated by post-stitch ribbing, crossing every fourth row.

    A cable is a crossing: stitches worked out of order, around each other. The CIR consumes
    stitches strictly in order, so a crossing is one composite stitch that consumes four and
    produces four rather than a sequence pretending to reorder them -- the arithmetic the
    compiler guarantees stays exact, and which pair crosses in front is a property of the
    stitch instead of prose nobody checked.
    """
    across = _nearest(CABLE_TARGET_CM[0], 8 * 10.0 / WORSTED.stitches_per_10cm)
    width = across * 8
    _check(width, 8, "cable throw")
    wide_cm = across_cm(width, WORSTED)

    rows: list[Row] = [Row(index=1, ops=[Op("sc", width)], declared_count=width,
                           color="cream", turning_chain=1)]
    plain = [Op("bpdc", 2), Op("fpdc", 4), Op("bpdc", 2)]
    crossing = [Op("bpdc", 2), Op("cable2x2"), Op("bpdc", 2)]

    block_cm = (3 * _row_height_cm(("bpdc", "fpdc"), WORSTED)
                + _row_height_cm(("bpdc", "cable2x2"), WORSTED))
    blocks = _nearest(CABLE_TARGET_CM[1] - _row_height_cm(("sc",), WORSTED), block_cm)
    index = 1
    # Four-row blocks: three rows of ribbed columns, then the crossing row.
    for _ in range(blocks):
        for body in (plain, plain, plain, crossing):
            index += 1
            rows.append(Row(index=index, ops=[Repeat(list(body), times=across)],
                            declared_count=width, color="cream", turning_chain=2))

    return CIR(
        slug="heirloom-cable-blanket",
        title="Heirloom Cable Throw",
        version=version,
        construction="flat_rows",
        risk_class="A",
        colors=dict(CREAM),
        gauge=WORSTED,
        materials=[Material(name="worsted acrylic", yarn_weight="worsted", colorway="cream",
                            color_id="cream")],
        components=[Component(name="throw", construction="flat_rows", rows=rows,
                              foundation=width)],
        designer_notes=(
            f"{across} cable columns, each crossing every fourth row, separated by back post "
            f"ribbing. The crossing is worked over four stitches: two held to the front, two "
            f"worked behind them, then the held pair."),
        finished_size_note=(
            f"About {wide_cm:.0f} cm wide at the stated gauge. Cable fabric draws in across "
            f"its width, which the gauge swatch has to be worked in pattern to show."),
        # F-783: cable columns built on the compiler's composite crossing stitch.
        provenance=catalogue_provenance(
            "heirloom-cable-blanket",
            {"builder": "products.texture.build_cable_throw", "width": width, "blocks": blocks,
             "column": 8, "gauge": vars(WORSTED)},
            ("products.texture", "cir.stitches:cable2x2", "post_stitch_ribbing")),
    )
