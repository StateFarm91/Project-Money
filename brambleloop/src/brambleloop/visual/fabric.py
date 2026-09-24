"""Deterministic fabric rendering: the product's structure comes from the instructions.

Written 2026-09-24, after twelve renders across three image providers returned product
truth 0 of 12. The diagnosis that produced this module is in B-689: asking a diffusion model
to draw a specific combinatorial stitch structure and then judging whether it matches the
chart is a model guessing the instructions, which the Execution Directive forbids for pattern
text and which nothing made permissible for pattern imagery.

So the crochet region is not generated. It is drawn from the compiled twin, cell by cell,
from the same certified CIR the pattern text is written from. Every visual property this
module emits is a consequence of a stitch count, a gauge number or a loop target that the
compiler has already checked. There is no model in this path and no prompt, which is what
makes the output's structure true by construction rather than true if a judge notices.

**This is deliberately not a beauty renderer.** It answers one question -- can Brambleloop
produce a visual whose structure is authoritative -- and it answers it in flat SVG with no
lighting, no yarn hairiness and no drape. Presentation is a later layer and a different
problem; a presentation layer may composite, light or restyle around this, but it may never
redraw the fabric, because then the structure stops being authoritative and we are back to
guessing.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

# Physical stitch proportions, in millimetres per gauge unit. Derived from the gauge rather
# than assumed: a stitch is (10cm / stitches_per_10cm) wide and (10cm / rows_per_10cm) tall,
# which is the same arithmetic `twin._flat_dimensions` uses for the finished measurements.
# Using one source for both means the swatch and the size claim cannot disagree.


def cell_size_mm(gauge) -> tuple[float, float]:
    """One stitch's footprint in millimetres, from the gauge and nothing else."""
    return (100.0 / gauge.stitches_per_10cm, 100.0 / gauge.rows_per_10cm)


def _ridge(loop: str) -> str | None:
    """Which edge of the cell carries the surface bar this loop target leaves behind.

    Working into the back loop leaves the front loop unworked, lying on the near face as a
    horizontal bar at the bottom of the stitch; working into the front loop leaves the back
    loop showing at the top. Both-loop stitches leave no bar, which is why plain fabric
    reads flat and this is the whole mechanism behind textured stitch patterns.
    """
    return {"back": "lower", "front": "upper"}.get(loop)


def swatch_svg(twin, gauge, *, max_rows: int | None = None, max_cols: int | None = None,
               scale: float = 4.0, yarn: str = "#c98b9b", shade: str = "#a86f7e") -> str:
    """A flat, deterministic drawing of a compiled component's fabric.

    `twin` is a `TwinModel`; every cell drawn is a stitch the compiler counted. Nothing here
    invents a stitch, and a cell with no loop target draws no bar rather than a decorative
    one -- absence of texture is drawn as absence, never as a guess.
    """
    w_mm, h_mm = cell_size_mm(gauge)
    cw, ch = w_mm * scale, h_mm * scale

    rows = sorted({c.row for c in twin.cells})
    if max_rows:
        rows = rows[:max_rows]
    by_row = {r: sorted((c for c in twin.cells if c.row == r),
                        key=lambda c: getattr(c, "fabric_position", c.position))
              for r in rows}
    ncols = max((len(v) for v in by_row.values()), default=0)
    if max_cols:
        ncols = min(ncols, max_cols)

    parts = [f'<rect width="100%" height="100%" fill="{escape(yarn)}"/>']
    for ri, r in enumerate(rows):
        y = ri * ch
        for c in by_row[r][:ncols]:
            x = getattr(c, "fabric_position", c.position) * cw
            parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{cw:.2f}" height="{ch:.2f}" '
                f'fill="{escape(yarn)}" stroke="{escape(shade)}" stroke-width="0.4" '
                f'stroke-opacity="0.35"/>')
            edge = _ridge(getattr(c, "loop", "both"))
            if edge is None:
                continue
            # The unworked loop, drawn where it actually sits.
            by = y + (ch * 0.86 if edge == "lower" else ch * 0.06)
            parts.append(
                f'<rect x="{x:.2f}" y="{by:.2f}" width="{cw:.2f}" height="{ch * 0.16:.2f}" '
                f'fill="{escape(shade)}" fill-opacity="0.75"/>')

    width, height = ncols * cw, len(rows) * ch
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
            f'height="{height:.0f}" viewBox="0 0 {width:.2f} {height:.2f}">'
            + "".join(parts) + "</svg>")


def texture_signature(twin, *, max_rows: int | None = None) -> dict:
    """What the fabric's texture actually is, measured from the cells rather than described.

    This is the part that can be tested. A textured pattern makes a claim about its surface
    -- ridges running one way, a repeat of a certain period -- and those claims are
    properties of the loop targets in the grid, so they can be computed and asserted rather
    than looked at. `orientation` is reported in *fabric* axes (along a row, or up the rows);
    turning that into "vertical on the worn garment" needs the panel's grain direction,
    which the CIR does not yet carry and which this deliberately does not guess.
    """
    rows = sorted({c.row for c in twin.cells})
    if max_rows:
        rows = rows[:max_rows]
    by_row = {r: sorted((c for c in twin.cells if c.row == r),
                        key=lambda c: getattr(c, "fabric_position", c.position))
              for r in rows}

    targeted = [c for r in rows for c in by_row[r] if getattr(c, "loop", "both") != "both"]
    total = sum(len(by_row[r]) for r in rows)
    if not targeted:
        return {"textured": False, "why": "every stitch works both loops, so the surface is "
                                          "flat: there are no unworked loops to catch light",
                "cells": total}

    # Does the loop target alternate along a row, and does it offset between rows? Those two
    # together are what makes a waffle rather than stripes.
    alternates, offsets = 0, 0
    comparable_rows = 0
    prev = None
    for r in rows:
        seq = [getattr(c, "loop", "both") for c in by_row[r]]
        flips = sum(1 for a, b in zip(seq, seq[1:]) if a != b and "both" not in (a, b))
        pairs = sum(1 for a, b in zip(seq, seq[1:]) if "both" not in (a, b))
        if pairs:
            alternates += flips / pairs
            comparable_rows += 1
        if prev is not None:
            same = [(a, b) for a, b in zip(prev, seq) if "both" not in (a, b)]
            if same:
                offsets += sum(1 for a, b in zip(prev, seq)
                               if "both" not in (a, b) and a != b) / len(same)
        prev = seq

    alt = alternates / comparable_rows if comparable_rows else 0.0
    off = offsets / (len(rows) - 1) if len(rows) > 1 else 0.0
    # Classified from both numbers rather than thresholded on one.
    #
    # A single threshold cannot tell a checkerboard from a ridge: high alternation alone says
    # the loop target changes along the row, and only the between-row offset says whether the
    # next row continues that column or breaks it. Reporting "ridges run up the rows" from
    # alternation alone would assert a direction the measurement does not support, which is
    # the same defect as a verdict computed from evidence that was never gathered.
    hi_alt, hi_off = alt >= 0.5, off >= 0.5
    if hi_alt and hi_off:
        surface, why = "checkered", ("the loop target changes along the row and changes "
                                     "again on the next row, so no column persists: the "
                                     "surface breaks up rather than running in ridges")
    elif hi_alt:
        surface, why = "ridges_up_the_rows", ("the loop target changes along the row but "
                                              "repeats on the next, so each column keeps "
                                              "its target and ridges run across the rows")
    elif hi_off:
        surface, why = "ridges_along_the_rows", ("the loop target holds along a row and "
                                                 "flips on the next, so each row is a band")
    else:
        surface, why = "uniform", "the loop target barely changes in either direction"
    return {
        "textured": True,
        "cells": total,
        "loop_targeted_cells": len(targeted),
        "alternation_along_row": round(alt, 3),
        "offset_between_rows": round(off, 3),
        "surface": surface,
        "why": why,
        "orientation_is_in_fabric_axes": (
            "along/up the rows, not up/across the worn garment. Which of those is vertical "
            "depends on the panel's grain direction, which the CIR does not carry, so this "
            "deliberately does not say"),
    }
