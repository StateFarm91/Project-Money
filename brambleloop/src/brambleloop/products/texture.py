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

from ..cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row

WORSTED = Gauge(stitches_per_10cm=16, rows_per_10cm=18, stitch_type="sc", hook_mm=5.0)
CHUNKY = Gauge(stitches_per_10cm=11, rows_per_10cm=13, stitch_type="sc", hook_mm=6.5)

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


def build_ribbed_scarf(version: str = "1.0.0") -> CIR:
    """Post-stitch ribbing: fpdc and bpdc in the same columns on every row.

    Ribbing is not a colour effect and cannot be imitated by one. Working the post stitches
    into the same columns each row is what makes the ribs stand up and the fabric stretch,
    and it is why the previous "Chunky Ribbed Scarf" -- plain single and double crochet in
    two colours -- was a scarf with a name it had not earned.
    """
    width = 24            # 21.8 cm unstretched at this gauge: a scarf, not a wrap
    across = _check(width, 4, "ribbed scarf")

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
        finished_size_note=("Ribbing stretches, so the width is given relaxed. Worked at the "
                            "stated gauge it measures about 22 cm across unstretched."),
        designer_notes=("Every row works front and back post stitches into the same columns, "
                        "which is what makes the rib stand up rather than merely look "
                        "striped."),
    )


def build_bobble_pillow(version: str = "1.0.0") -> CIR:
    """A staggered bobble grid on a single crochet ground.

    The bobbles alternate position every second bobble row, which is what makes a grid rather
    than columns. A bobble costs about five double crochets of yarn in one stitch's width, so
    the estimate for this piece is dominated by them -- which is why the yarn table carries a
    real figure for `bob` instead of falling back to a default that would have understated a
    cushion by a third.
    """
    width = 70            # 43.8 cm: sized for a 45 cm pad, which bobble fabric draws in to
    across = _check(width, 5, "bobble pillow")

    rows: list[Row] = [Row(index=1, ops=[Op("sc", width)], declared_count=width,
                           color="gold", turning_chain=1)]
    index = 1
    # Thirteen four-row blocks: plain, bobbles, plain, bobbles offset. The offset is the
    # difference between a grid and a set of columns.
    for _ in range(13):
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
        finished_size_note=("Sized for a 45 cm floor cushion pad. Bobble fabric draws in, so "
                            "the panel is worked slightly wider than the pad."),
    )


def build_cable_throw(version: str = "1.0.0") -> CIR:
    """Cable columns separated by post-stitch ribbing, crossing every fourth row.

    A cable is a crossing: stitches worked out of order, around each other. The CIR consumes
    stitches strictly in order, so a crossing is one composite stitch that consumes four and
    produces four rather than a sequence pretending to reorder them -- the arithmetic the
    compiler guarantees stays exact, and which pair crosses in front is a property of the
    stitch instead of prose nobody checked.
    """
    width = 144
    across = _check(width, 8, "cable throw")

    rows: list[Row] = [Row(index=1, ops=[Op("sc", width)], declared_count=width,
                           color="cream", turning_chain=1)]
    plain = [Op("bpdc", 2), Op("fpdc", 4), Op("bpdc", 2)]
    crossing = [Op("bpdc", 2), Op("cable2x2"), Op("bpdc", 2)]

    index = 1
    # Thirty four-row blocks: three rows of ribbed columns, then the crossing row.
    for _ in range(30):
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
        designer_notes=("Eighteen cable columns, each crossing every fourth row, separated by "
                        "back post ribbing. The crossing is worked over four stitches: two "
                        "held to the front, two worked behind them, then the held pair."),
        finished_size_note=("About 90 cm wide at the stated gauge. Cable fabric draws in "
                            "across its width, which the gauge swatch has to be worked in "
                            "pattern to show."),
    )
