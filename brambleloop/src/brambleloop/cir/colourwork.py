"""Charted colourwork, validated row by row (ENG-COLOURWORK).

A charted component declares its chart (`model.Chart`) beside its rows. The chart is the
design, the rows are the instructions, and this module proves the two say the same thing,
deterministically, before anything downstream (twin, writer, PDF, certificate) reads either.
No model is asked; if every LLM disagrees with these checks, these checks win.

Four gates, each with its own finding code (each pinned by a mutation test in
`tests/test_eng_colourwork.py`):

* **Chart/instruction agreement** (`CHART_INSTRUCTION_DISAGREE`, `CHART_STITCH_COUNT`). Every
  stitch the rows work is expanded, laid out in fabric order (a turned flat row runs the other
  way, exactly as `twin.build_twin` mirrors it), and compared with the chart cell for cell. A
  row of the wrong width, a stitch in the wrong colour, or a colour worked outside the chart
  is an error. The compiler has already checked the stitch counts; this checks the colours.
* **Colour count** (`COLOURWORK_COLOUR_COUNT`). At most `MAX_COLOURS_IN_ROW[technique]`
  yarns in any one row (tapestry carries every yarn of a row inside the stitches, and more
  than two carried strands make a stiff, thick fabric), at most `MAX_COLOURS` in the piece,
  and every chart colour is a declared CIR colour with a yarn in the materials list.
* **Float length** (`COLOURWORK_FLOAT_TOO_LONG`). In a carried technique a yarn travels
  unworked between the stitches it is worked in. The longest such carry, counted from the
  edge the row starts at to the edge it ends at (and around the join, for a round), is at most
  `MAX_FLOAT[technique]` stitches, so the strand is anchored regularly and the fabric stays
  even and practical. A row that carries a yarn it never works is the extreme case.
* **Colour-change placement** (`COLOUR_CHANGE_UNREACHABLE`). Every yarn a charted row works
  must be at hand where the row needs it: carried through the previous row (so it rests at
  the edge this row starts from), or joined here for the first time. A yarn that sat out a
  row is resting at the far edge of a turned piece -- the instructions would ask for a colour
  that is not there -- so the chart must keep it carried or not use it again. (Rounds never
  turn: a yarn that sits out a round rests at the join, where the next round starts.)

The thresholds are a stated house design rule, not a sourced standard; they are constants
here so a test, a report and a reviewer all read the same number.
"""
from __future__ import annotations

from .model import CIR, Component, Op, Repeat

MAX_COLOURS = 3
MAX_COLOURS_IN_ROW: dict[str, int] = {"tapestry": 2}
MAX_FLOAT: dict[str, int] = {"tapestry": 12}

CODES = ("CHART_INSTRUCTION_DISAGREE", "CHART_STITCH_COUNT", "COLOURWORK_COLOUR_COUNT",
         "COLOURWORK_FLOAT_TOO_LONG", "COLOUR_CHANGE_UNREACHABLE")


def _expand(nodes, row_colour: str | None) -> list[str | None]:
    out: list[str | None] = []
    for node in nodes:
        if isinstance(node, Op):
            from . import stitches

            produced = stitches.get(node.stitch).produces
            out.extend([node.color or row_colour] * (node.count * produced))
        elif isinstance(node, Repeat):
            out.extend(_expand(node.ops, row_colour) * int(node.times or 1))
    return out


def worked_colours(comp: Component, result=None) -> dict[int, list[str | None]]:
    """Per row, the colour of every stitch in FABRIC order (the twin's `fabric_position`).

    Read from the compiled rows when `result` is given (to-end repeats resolved), else from
    the CIR's own ops. A turned flat row is reversed on even rows, the same rule the twin uses.
    """
    turned = comp.construction == "flat_rows"
    out: dict[int, list[str | None]] = {}
    if result is not None:
        from . import stitches

        for r in result.rows:
            if r.component != comp.name:
                continue
            cells: list[str | None] = []
            for op in r.ops:
                cells.extend([op.color or r.color]
                             * (op.count * stitches.get(op.stitch).produces))
            out[r.index] = cells[::-1] if turned and r.index % 2 == 0 else cells
        return out
    for row in comp.rows:
        cells = _expand(row.ops, row.color)
        out[row.index] = cells[::-1] if turned and row.index % 2 == 0 else cells
    return out


def _longest_carry(cells: list, yarn: str, cyclic: bool) -> int:
    """The longest run of stitches in which `yarn` is carried but not worked."""
    n = len(cells)
    if yarn not in cells:
        return n
    if cyclic:
        first = cells.index(yarn)
        ring = cells[first:] + cells[:first]
        best = cur = 0
        for c in ring:
            cur = cur + 1 if c != yarn else 0
            best = max(best, cur)
        return best
    best = cur = 0
    for c in cells:
        cur = cur + 1 if c != yarn else 0
        best = max(best, cur)
    return best


def problems(cir: CIR, result=None) -> list[tuple[str, str, str, int | None]]:
    """Every violation as (code, message, component, row); [] when every chart holds."""
    out: list[tuple[str, str, str, int | None]] = []
    materials = {m.color_id for m in cir.materials or [] if getattr(m, "color_id", None)}
    for comp in cir.components:
        chart = comp.chart
        if chart is None:
            continue
        technique = chart.technique
        cap_row = MAX_COLOURS_IN_ROW[technique]
        cap_float = MAX_FLOAT[technique]
        cyclic = comp.construction != "flat_rows"
        grid = worked_colours(comp, result)
        palette = set(chart.key.values())
        unknown = sorted(c for c in palette if c not in (cir.colors or {}))
        if unknown:
            out.append(("COLOURWORK_COLOUR_COUNT",
                        f"the chart keys {unknown}, which the CIR does not declare as colours",
                        comp.name, None))
        unyarned = sorted(c for c in palette if c not in materials)
        if unyarned:
            out.append(("COLOURWORK_COLOUR_COUNT",
                        f"the chart works {unyarned} with no yarn for it in the materials",
                        comp.name, None))
        worked_all = {c for cells in grid.values() for c in cells if c}
        if len(worked_all) > MAX_COLOURS:
            out.append(("COLOURWORK_COLOUR_COUNT",
                        f"the piece works {len(worked_all)} colours {sorted(worked_all)}; a "
                        f"charted piece works at most {MAX_COLOURS}", comp.name, None))
        previous: set[str] = set()
        joined: set[str] = set()
        prev_charted = False
        for index in sorted(grid):
            cells = grid[index]
            want = chart.colours_at(index)
            row_yarns = {c for c in cells if c}
            if want is None:
                if len(row_yarns) > 1:
                    out.append(("CHART_INSTRUCTION_DISAGREE",
                                f"row {index} works {sorted(row_yarns)} but lies outside the "
                                f"chart (rows {chart.first_row}-{chart.last_row}), where a row "
                                f"works one colour", comp.name, index))
                previous = set(row_yarns)
                joined |= row_yarns
                prev_charted = False
                continue
            if len(want) != len(cells):
                out.append(("CHART_STITCH_COUNT",
                            f"row {index} works {len(cells)} sts but the chart row has "
                            f"{len(want)}", comp.name, index))
                previous = set(row_yarns)
                joined |= row_yarns
                prev_charted = True
                continue
            wrong = [i for i, (a, b) in enumerate(zip(cells, want)) if a != b]
            if wrong:
                i = wrong[0]
                out.append(("CHART_INSTRUCTION_DISAGREE",
                            f"row {index}: {len(wrong)} st(s) disagree with the chart; first "
                            f"at fabric st {i + 1}, the instructions work {cells[i]!r} where "
                            f"the chart shows {want[i]!r}", comp.name, index))
            if len(row_yarns) > cap_row:
                out.append(("COLOURWORK_COLOUR_COUNT",
                            f"row {index} works {len(row_yarns)} colours {sorted(row_yarns)}; "
                            f"{technique} carries at most {cap_row} in a row", comp.name, index))
            if len(row_yarns) > 1:
                for yarn in sorted(row_yarns):
                    run = _longest_carry(cells, yarn, cyclic)
                    if run > cap_float:
                        out.append(("COLOURWORK_FLOAT_TOO_LONG",
                                    f"row {index}: {yarn} is carried {run} sts without being "
                                    f"worked; {technique} allows at most {cap_float}",
                                    comp.name, index))
                # Placement: a yarn this charted row works must be at hand -- carried in the
                # row before, or joined here for the first time.
            stranded = sorted(y for y in row_yarns
                              if not cyclic and prev_charted and y in joined
                              and y not in previous)
            for y in stranded:
                out.append(("COLOUR_CHANGE_UNREACHABLE",
                            f"row {index} works {y}, which was not carried through row "
                            f"{index - 1}; it rests at the far edge and is not where this "
                            f"row needs it", comp.name, index))
            previous = set(row_yarns)
            joined |= row_yarns
            prev_charted = True
    return out


def chart_findings(cir: CIR, result=None) -> list:
    """The problems as compiler `Finding`s (all ERROR)."""
    from .compiler import ERROR, Finding

    return [Finding(ERROR, code, msg, component=comp, row=row)
            for code, msg, comp, row in problems(cir, result)]


def twin_findings(cir: CIR, twins: dict) -> list:
    """The twin renders the true chart: its colour grid equals the declared chart, cell for
    cell, for every charted row (`CHART_TWIN_DISAGREE`)."""
    from .compiler import ERROR, Finding

    out = []
    for comp in cir.components:
        if comp.chart is None or comp.name not in twins:
            continue
        twin = twins[comp.name]
        rows = sorted({c.row for c in twin.cells})
        grid = dict(zip(rows, twin.color_grid()))
        for index in range(comp.chart.first_row, comp.chart.last_row + 1):
            if grid.get(index) != comp.chart.colours_at(index):
                out.append(Finding(ERROR, "CHART_TWIN_DISAGREE",
                                   f"row {index}: the digital twin's fabric does not match "
                                   f"the declared chart", component=comp.name, row=index))
                break
    return out


def charted(cir: CIR) -> bool:
    return any(c.chart is not None for c in cir.components)


def yarn_by_colour(twin) -> dict[str, float]:
    """Metres of yarn per colour for the piece, from the twin (carried strands included)."""
    return dict(twin.yarn_metres_by_color)
