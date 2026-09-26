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


# Stitches that stand off the surface with every loop worked (the same family charts.relief
# shades and launch0.TEXTURE_STITCHES names). Kept here as a literal so this module reads the
# cells alone and does not import the publishing layer.
RELIEF_STITCHES: frozenset[str] = frozenset({
    "fpdc", "bpdc", "bob", "cable2x2", "cable1x1", "beg_star_st", "star_st", "end_star_st"})
# Of those, the ones that stand PROUD of the fabric (a back post stitch recedes). The
# along-row period is the period of the proud mask: in "bpdc 2, fpdc 4, bpdc 2" every cell is
# a relief stitch, and the eight-stitch repeat is visible only as raised against recessed.
RAISED_STITCHES: frozenset[str] = RELIEF_STITCHES - {"bpdc"}


def _relief_signature(rows, by_row, total: int) -> dict | None:
    """Texture from relief stitches: which cells stand off the surface, and whether they line
    up in columns (ribs, cables) or break up (a bobble grid, a star fabric)."""
    def code(c): return getattr(c, "stitch", None)
    relief_rows = {r: [code(c) in RELIEF_STITCHES for c in by_row[r]] for r in rows}
    n_relief = sum(sum(v) for v in relief_rows.values())
    if not n_relief:
        return None
    # Column persistence: of the relief cells in a row, how many have a relief cell directly
    # above them in the next row. Ribs and cable columns persist; a staggered bobble grid or a
    # star fabric's eye rows do not.
    persist = pairs = 0
    ordered = list(rows)
    for a, b in zip(ordered, ordered[1:]):
        ra, rb = relief_rows[a], relief_rows[b]
        for i, on in enumerate(ra):
            if on and i < len(rb):
                pairs += 1; persist += rb[i]
    column = persist / pairs if pairs else 0.0
    # Along-row period of the relief mask (the smallest shift that reproduces a row), from
    # the row with the most relief cells; 0 when a row is all relief (plain ribbing).
    raised_rows = {r: [code(c) in RAISED_STITCHES for c in by_row[r]] for r in rows}
    best = max(raised_rows.values(), key=sum)
    period = 0
    if 0 < sum(best) < len(best):
        for k in range(1, len(best)):
            if all(best[i] == best[(i + k) % len(best)] for i in range(len(best))):
                period = k; break
    kinds = sorted({code(c) for r in rows for c in by_row[r] if code(c) in RELIEF_STITCHES})
    if column >= 0.5:
        surface, why = "ridges_up_the_rows", ("relief stitches sit in the same positions row after row, so they stack "
                                              "into columns running up the rows: ribbing, or cable columns")
    else:
        surface, why = "checkered", ("relief stitches move between rows, so the surface breaks up into a grid rather "
                                     "than running in ridges")
    return {"textured": True, "cells": total, "loop_targeted_cells": 0, "relief_cells": n_relief, "relief_stitches": kinds,
            "column_persistence": round(column, 3), "period_along_row_sts": period, "surface": surface, "why": why,
            "orientation_is_in_fabric_axes": ("along/up the rows, not up/across the worn garment. Which of those is vertical "
                                              "depends on the panel's grain direction, which the CIR does not carry, so this "
                                              "deliberately does not say")}


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
        # Loop targets are not the only relief. Post stitches stand forward of or behind the
        # fabric, bobbles and crossings sit proud of it, and a star closes into a puff -- all
        # of it light and shadow with every loop worked. The first version of this rule saw
        # only unworked loops, so it called the Heirloom Cable Throw (18 cable columns on
        # back-post ribbing, class A) a flat fabric; found by the V1 graduation benchmark's
        # Product Truth cross-check, 2026-09-26. Measured from the cells, as the loop rule is.
        relief = _relief_signature(rows, by_row, total)
        if relief is not None:
            return relief
        return {"textured": False, "why": "every stitch works both loops and no stitch stands "
                                          "off the surface, so the fabric is flat: there are "
                                          "no unworked loops and no relief stitches to catch light",
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
        # Constant single-loop targeting is not the absence of texture -- it is ribbing, the
        # most common textured fabric in crochet. Every row leaves its unworked loop in the
        # same relative place, so each row contributes a bar and the bars stack into ridges
        # running along the rows. The first version of this classifier called it "uniform"
        # because it only looked for *variation*, and so reported the neckband of a ribbed
        # cardigan as barely textured. Absence of variation is not absence of texture.
        surface, why = "ridges_along_the_rows", (
            "the loop target is the same everywhere, so every row leaves its unworked loop "
            "in the same place and the rows stack into ridges: this is ribbing")
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
