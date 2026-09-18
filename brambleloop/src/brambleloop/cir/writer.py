"""CIR -> customer-facing written pattern.

Downstream of the CIR, never the source of truth (Master Plan section 2). US terminology is
canonical; UK is a rendering choice, not a fork (section 31).

The emitted grammar is deliberately strict and regular so the reverse compiler can parse it
back independently. Writer and reverse compiler share no parsing code on purpose: if they
shared it, a round-trip would prove nothing.
"""
from __future__ import annotations

from .. cir import stitches
from .compiler import CompileResult
from .rowcycle import describe, detect_cycle
from .model import CIR, Component, Op, OpNode, Repeat, Row


def _term(code: str, terminology: str) -> str:
    s = stitches.get(code)
    if terminology.upper() == "UK":
        return {
            "sc": "dc", "hdc": "htr", "dc": "tr", "tr": "dtr",
            "inc": "dc inc", "dec": "dc dec", "dc_inc": "tr inc", "dc_dec": "tr dec",
            "ch": "ch", "slst": "ss", "sk": "miss",
        }.get(code, code)
    return code


def write_op(op: Op, terminology: str = "US") -> str:
    code = _term(op.stitch, terminology)
    st = stitches.get(op.stitch)
    n = op.count

    if op.stitch == "ch":
        return f"ch {n}" if n > 1 else "ch 1"
    if op.stitch == "sk":
        return f"sk next {n} sts" if n > 1 else "sk next st"
    if st.consumes == 2:  # decreases
        base = f"{code} over next 2 sts"
        return f"{base} x {n}" if n > 1 else base
    return f"{code} in next {n} sts" if n > 1 else f"{code} in next st"


def write_node(node: OpNode, terminology: str = "US") -> str:
    if isinstance(node, Op):
        return write_op(node, terminology)
    inner = ", ".join(write_node(o, terminology) for o in node.ops)
    if node.times is None:
        return f"*{inner}; rep from * to end"
    return f"[{inner}] x {node.times}"


def write_row(
    row: Row, component: Component, count: int | None, terminology: str = "US",
    state_color: bool = False,
) -> str:
    """One row or round of customer-facing instruction.

    `state_color` names the yarn in the line. It is on whenever the pattern has more than one
    colour, because a two-colour pattern whose written instructions never say which yarn to
    pick up is not a written pattern -- it is a chart with sentences next to it. Overlay
    mosaic in particular is one colour per row, and the colour *is* the design.
    """
    label = "Row" if component.construction == "flat_rows" else "Rnd"
    parts: list[str] = []
    if row.turning_chain:
        turn = ", turn" if component.construction == "flat_rows" else ""
        parts.append(f"Ch {row.turning_chain}{turn}.")

    is_first = component.rows and row is component.rows[0]
    if is_first and component.foundation_kind == "magic_ring":
        # A magic-ring round has no previous fabric to work into, so "in next N sts" would
        # be nonsense to a maker. Structure is still a plain run of stitches.
        if len(row.ops) == 1 and isinstance(row.ops[0], Op):
            op = row.ops[0]
            body = f"{op.count} {_term(op.stitch, terminology)} in magic ring"
        else:
            body = ", ".join(write_node(n, terminology) for n in row.ops) + " in magic ring"
        parts.append(body + ".")
    else:
        body = ", ".join(write_node(n, terminology) for n in row.ops)
        parts.append(body + ".")
    heading = f"{label} {row.index}"
    if state_color and row.color:
        heading += f" ({row.color})"
    line = f"{heading}: " + " ".join(parts)
    if count is not None:
        line += f" ({count} sts)"
    if row.note:
        line += f"  -- {row.note}"
    return line


SPIRAL_LINE = ("Work in a continuous spiral. Do not join the rounds; mark the first stitch "
               "of each round and move the marker up as you go.")
JOINED_LINE = ("Join each round with a sl st to the first stitch, then ch 1 to begin the "
               "next round.")


def construction_lines(comp: Component) -> list[str]:
    """How the rounds are worked, stated once rather than repeated on every line.

    A maker who does not know whether to join has a different fabric from the one the
    pattern was validated as: joining leaves a seam up the side, spiralling does not. Saying
    it once at the top of the component keeps one source of truth, and the reverse compiler
    reads this line back and checks it against the CIR, so a document that says "spiral"
    over a joined pattern is caught rather than shipped.
    """
    if comp.construction == "spiral_rounds":
        return [SPIRAL_LINE]
    if comp.construction == "joined_rounds":
        return [JOINED_LINE]
    return []


ASSEMBLY_HEADING = "## Assembly"

_SEAM_WORDS = {
    "whipstitch": "Whipstitch",
    "slst": "Slip stitch",
    "mattress": "Mattress stitch",
    "sew": "Sew",
}


def write_seam(seam, position: int) -> str:
    """One finishing step, in the same regular grammar as a row so it can be read back.

    The placement clause is what turns a set of correct pieces into an object. A maker who
    is told only that the ear attaches to the head has to work out where from a photograph,
    which is the "beauty image, guess the instructions" failure arriving through the back
    door of an unspecified assembly step.
    """
    verb = _SEAM_WORDS.get(seam.method, "Join")
    if seam.is_self_seam:
        where = f"the two edges of the {seam.piece_a} together"
    else:
        where = f"the {seam.piece_a} to the {seam.piece_b}"
    if seam.is_placed:
        last = seam.at_round + seam.spans_rounds - 1
        span = (f"round {seam.at_round}" if seam.spans_rounds == 1
                else f"rounds {seam.at_round}-{last}")
        where += f" across {span}"
        if seam.stitches_from_centre is not None:
            where += f", {seam.stitches_from_centre} sts either side of centre"
        if seam.mirrored:
            where += ", and the second one mirrored on the far side"
    line = f"Step {position}: {verb} {where}."
    if seam.stuff_before_closing:
        line += " Stuff firmly before closing."
    if seam.note:
        note = seam.note.rstrip(".")
        line += f" {note[0].upper()}{note[1:]}."
    return line


def assembly_lines(cir: CIR) -> list[str]:
    if not cir.assembly:
        return []
    out = [ASSEMBLY_HEADING]
    out.extend(write_seam(seam, i) for i, seam in enumerate(cir.assembly, start=1))
    return out


def collapses_rows(cir: CIR) -> bool:
    """True when the written pattern will collapse a repeated block into an instruction.

    Listing copy has to say what the PDF actually contains. "A stitch count on every single
    row" stops being true the moment the writer collapses rows 49-120 into one sentence, and
    a claim that was true last week is the kind that ships. Derived from the same
    `detect_cycle` the writer uses, so the copy and the document cannot drift apart.
    """
    return any(detect_cycle(c.rows) is not None for c in cir.components)


def write_pattern(cir: CIR, result: CompileResult, terminology: str = "US") -> str:
    """Render the full customer-facing pattern body."""
    out: list[str] = [f"{cir.title}", f"Version {cir.version}", ""]
    if cir.gauge:
        g = cir.gauge
        hook = f", {g.hook_mm}mm hook" if g.hook_mm else ""
        out.append(
            f"Gauge: {g.stitches_per_10cm} sts x {g.rows_per_10cm} rows = 10cm in "
            f"{_term(g.stitch_type, terminology)}{hook}"
        )
    if cir.materials:
        out.append("Materials: " + "; ".join(
            f"{m.name} ({m.colorway})" if m.colorway else m.name for m in cir.materials))
    out.append(f"Terminology: {terminology.upper()} terms")
    out.append("")

    for comp in cir.components:
        if len(cir.components) > 1 or comp.name != "body":
            make = f" (make {comp.make})" if comp.make > 1 else ""
            out.append(f"## {comp.name}{make}")
        if comp.foundation and comp.foundation_kind == "chain":
            out.append(f"Foundation: ch {comp.foundation}.")
        out.extend(construction_lines(comp))
        # Collapse a repeated row-block into an instruction, the way a real pattern does.
        # Printing all 120 rows of a five-repeat blanket is complete and unusable: a maker
        # loses their place in four pages of near-identical lines. The cycle is derived from
        # the rows, so it cannot disagree with them.
        cycle = detect_cycle(comp.rows)
        state_color = len(cir.colors) > 1
        for row in comp.rows:
            if cycle is not None and cycle.covers(row.index):
                continue
            try:
                count = result.row(comp.name, row.index).stitch_count
            except KeyError:
                count = None
            out.append(write_row(row, comp, count, terminology, state_color))
            if cycle is not None and row.index == cycle.end:
                out.append(describe(cycle, comp.rows[-1].index))
        out.append("")

    out.extend(assembly_lines(cir))

    return "\n".join(out).rstrip() + "\n"
