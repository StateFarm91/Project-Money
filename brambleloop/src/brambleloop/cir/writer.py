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
    row: Row, component: Component, count: int | None, terminology: str = "US"
) -> str:
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
    line = f"{label} {row.index}: " + " ".join(parts)
    if count is not None:
        line += f" ({count} sts)"
    if row.note:
        line += f"  -- {row.note}"
    return line


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
        out.append("Materials: " + "; ".join(m.name for m in cir.materials))
    out.append(f"Terminology: {terminology.upper()} terms")
    out.append("")

    for comp in cir.components:
        if len(cir.components) > 1 or comp.name != "body":
            make = f" (make {comp.make})" if comp.make > 1 else ""
            out.append(f"## {comp.name}{make}")
        if comp.foundation and comp.foundation_kind == "chain":
            out.append(f"Foundation: ch {comp.foundation}.")
        for row in comp.rows:
            try:
                count = result.row(comp.name, row.index).stitch_count
            except KeyError:
                count = None
            out.append(write_row(row, comp, count, terminology))
        out.append("")

    return "\n".join(out).rstrip() + "\n"
