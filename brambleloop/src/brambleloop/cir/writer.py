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
    """Delegates to the single terminology table in `stitches`. See UK_TERMS there."""
    return stitches.term(code, terminology)


def write_op(op: Op, terminology: str = "US") -> str:
    code = _term(op.stitch, terminology)
    st = stitches.get(op.stitch)
    n = op.count

    if op.stitch == "ch":
        return f"ch {n}" if n > 1 else "ch 1"
    if op.stitch == "sk":
        # `code`, not the literal. This returned "sk" in both terminologies because it ran
        # before the mapping was consulted -- the UK entry existed and was dead.
        return f"{code} next {n} sts" if n > 1 else f"{code} next st"
    if st.consumes > 1:
        # Decreases consume two; a 2-over-2 cable crossing consumes four. Both are "over
        # next N sts", and hardcoding the two meant the first stitch that consumed more
        # would have been written as though it consumed one.
        base = f"{code} over next {st.consumes} sts"
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


def hold_line(comp: Component, row: Row) -> str:
    """The division, written where it happens.

    Without this a divided pattern reads "Rnd 24: sc 32 (32 sts)" over a round of 48 and the
    maker has no idea what became of the other sixteen. The arithmetic would be correct, the
    twin would agree, and the document would be unfollowable -- the bag-of-pieces failure
    arriving through shaping rather than through assembly.
    """
    taken = [h for h in comp.holds if h.at_row == row.index]
    if not taken:
        return ""
    parts = []
    for hold in sorted(taken, key=lambda h: h.from_stitch):
        start, end = hold.spans
        where = f"sts {start + 1}-{end}"
        parts.append(f"{hold.count} sts ({where}) for {hold.name.replace('_', ' ')}")
    return ("Place " + ", and ".join(parts) + " on a stitch holder or waste yarn; "
            "they are worked separately later.")


def resume_line(comp: Component) -> str:
    """How a held piece starts, said rather than implied."""
    if not comp.resumes:
        return ""
    return (f"Rejoin yarn to the sts held for {comp.resumes.replace('_', ' ')} and work in "
            f"the round from here.")


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


FINISHING_HEADING = "## Finishing"


def finishing_lines(cir: CIR, *, width_cm: float | None = None,
                    height_cm: float | None = None,
                    result: "CompileResult | None" = None) -> list[str]:
    """How the work stops being work in progress.

    Every Brambleloop pattern shipped without this, and nobody noticed until the teardown
    reader -- built to audit somebody else's document -- was pointed at ours and found no
    finishing section. The last thing the maker was told was the last row. Fastening off,
    securing the ends and blocking to the stated size are the difference between a finished
    object and a piece still on the hook, and every benchmark in the category says so.

    Derived, not written: the ends come from the colours the CIR actually uses and the
    blocking measurements from the twin. Nothing here claims anything about a fibre --
    the ball band is cited instead.

    That sentence used to end "a fibre this schema does not record", and the schema records
    one now (`Material.fibre_content`, added 2026-09-25). The ball band is still what is
    cited here, and for a better reason than the schema's silence: the buyer of a *pattern*
    chooses their own yarn, so the composition this pattern was written for is not the
    composition of the object in their hands. `write_pattern` prints the stated content on
    the Materials line, where it describes the yarn it belongs to; care instructions stay
    with the yarn the maker actually bought.
    """
    out = [FINISHING_HEADING,
           "Fasten off and weave in all ends on the wrong side. Thread each end through at "
           "least 5 cm of stitches, then back through a few in the opposite direction, so "
           "it cannot work loose in wear or washing."]

    colours = len(cir.colors or [])
    if colours > 1:
        out.append(f"This pattern uses {colours} colours, so there is an end to secure at "
                   f"every join and every change.")

    # "Pin it out and leave it to dry flat" is the one instruction in this document that can
    # destroy a finished object. It is correct for anything that IS flat -- a blanket, a
    # runner, a disc coaster -- and ruinous for a vessel: flattening a damp basket sets a
    # crease across the wall and it does not come back. The shape is not guessed at; it is
    # the same `cir.geometry` classification the twin records, so this branches on the
    # measured object rather than on the title or the slug.
    #
    # DISC stays with the flat wording deliberately: a coaster is flat, and a pattern that
    # hedged on every round piece would teach makers to ignore the finishing section.
    upright = ()
    if result is not None:
        from . import geometry as _geom

        # Inverted on purpose: NOT-flat rather than a list of the solid shapes. The
        # classifier already answers disc / tube / cone / dome / vessel / shaped / gathered,
        # and enumerating the six solid ones would mean a seventh added later silently
        # inherits "leave it to dry flat" -- a new shape would default to the one wording
        # that can destroy the object. A flat piece produces no revolution at all, so an
        # empty measurement keeps the flat wording and only a measured non-disc changes it.
        upright = tuple(sorted({
            rev.shape for rev in _geom.measure_all(cir, result).values()
            if rev.shape != _geom.DISC}))

    if upright:
        # No pinning measurement is offered: the stated size of a vessel is a diameter and a
        # height, and pinning to a width would be pinning it flat by another name.
        out.append("Do not block this piece flat. It is worked in the round and pressing it "
                   "out would crease the wall: damp-finish it standing up, easing it to the "
                   "stated measurements with your hands and letting it dry in its own shape, "
                   "stuffed lightly with a towel if it needs help standing.")
    elif width_cm and height_cm:
        out.append(f"Block the finished piece to {width_cm:.0f} x {height_cm:.0f} cm: pin "
                   f"it out damp to those measurements, easing rather than stretching, and "
                   f"leave it to dry flat. Those are the dimensions this pattern's gauge "
                   f"produces, so blocking to them is what makes the stated size the size "
                   f"you get.")
    else:
        out.append("Block the finished piece: pin it out damp, easing rather than "
                   "stretching, and leave it to dry flat.")

    out.append("Check the ball band before blocking with heat or water. Fibres behave "
               "differently and yours is the one in your hands.")
    return out


def fibre_content_phrase(material) -> str:
    """"55% cotton, 45% linen", or "" when the source does not state a composition.

    Empty is the honest output for a yarn nobody has a composition for, and it is the one
    the rest of the document is built to handle: `publish/pdf.py`'s children's gate reports
    `fibre_and_care` unrenderable and refuses the product rather than printing a guess. A
    phrase invented from the yarn *name* -- "worsted acrylic" becoming "100% acrylic" --
    would satisfy that gate with something no source said, which is the one failure the
    field was added to make impossible.

    The order is the material's own, which `Material.__post_init__` has already normalised
    to descending percentage. The writer does not re-sort: two places deciding an order is
    two places that can come to disagree about it.
    """
    return ", ".join(f"{percent}% {fibre}"
                     for fibre, percent in (material.fibre_content or ()))


def material_line(material) -> str:
    """One material as the buyer reads it on the Materials line.

    `name (colorway), 55% cotton, 45% linen` -- the composition appended to the yarn the
    pattern was written for, and only where the CIR states one.

    The buyer needs this here rather than in a footnote: fibre decides whether a garment is
    wearable against a child's skin, whether it can be machine washed, and whether an
    allergy rules the project out, and all three are decisions made before the yarn is
    bought. It is on the same line as the yarn it belongs to because a composition floating
    free of the yarn it describes is the kind of fact that gets attached to the wrong one.

    `cir.reverse.parse_fibre_content` reads this back with its own grammar, which is the
    round trip B-005 requires. It does not import this function and this function does not
    import it: a round trip through shared code proves nothing.
    """
    head = f"{material.name} ({material.colorway})" if material.colorway else material.name
    fibres = fibre_content_phrase(material)
    return f"{head}, {fibres}" if fibres else head


def collapses_rows(cir: CIR) -> bool:
    """True when the written pattern will collapse a repeated block into an instruction.

    Listing copy has to say what the PDF actually contains. "A stitch count on every single
    row" stops being true the moment the writer collapses rows 49-120 into one sentence, and
    a claim that was true last week is the kind that ships. Derived from the same
    `detect_cycle` the writer uses, so the copy and the document cannot drift apart.
    """
    return any(detect_cycle(c.rows) is not None for c in cir.components)


def write_pattern(cir: CIR, result: CompileResult, terminology: str = "US", *,
                  width_cm: float | None = None, height_cm: float | None = None) -> str:
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
        out.append("Materials: " + "; ".join(material_line(m) for m in cir.materials))
    out.append(f"Terminology: {terminology.upper()} terms")
    out.append("")

    for comp in cir.components:
        if len(cir.components) > 1 or comp.name != "body":
            make = f" (make {comp.make})" if comp.make > 1 else ""
            out.append(f"## {comp.name}{make}")
        if comp.foundation and comp.foundation_kind == "chain":
            out.append(f"Foundation: ch {comp.foundation}.")
        resumed = resume_line(comp)
        if resumed:
            out.append(resumed)
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
            held = hold_line(comp, row)
            if held:
                out.append(held)
            if cycle is not None and row.index == cycle.end:
                out.append(describe(cycle, comp.rows[-1].index))
        out.append("")

    out.extend(assembly_lines(cir))
    out.append("")
    out.extend(finishing_lines(cir, width_cm=width_cm, height_cm=height_cm, result=result))

    return "\n".join(out).rstrip() + "\n"
