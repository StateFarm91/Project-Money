"""Deterministic CIR compiler.

Master Plan section 3: "Critical arithmetic is deterministic code, not LLM opinion."

The compiler resolves every row against the fabric available to it and fails loudly on any
disagreement. No model, prompt or reviewer can override it -- if the arithmetic does not
close, the pattern does not ship.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from . import stitches
from .model import CIR, Component, Op, OpNode, Repeat, Row

# Severity ordering matters: any ERROR blocks release (Master Plan section 2).
ERROR = "ERROR"
WARNING = "WARNING"


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    component: str | None = None
    row: int | None = None

    def __str__(self) -> str:
        where = ""
        if self.component:
            where = f" [{self.component}"
            where += f" row {self.row}]" if self.row is not None else "]"
        return f"{self.severity} {self.code}:{where} {self.message}"


@dataclass
class ResolvedOp:
    """An op with its to-end repeat resolved to a concrete number of repetitions."""

    stitch: str
    count: int
    consumes: int
    produces: int
    repeat_group: int | None = None  # index of the repeat this op belongs to, if any


@dataclass
class ResolvedRow:
    component: str
    index: int
    into_count: int
    consumed: int
    produced: int
    remainder: int
    color: str | None
    ops: list[ResolvedOp]
    turning_chain: int
    turning_chain_counts: bool

    @property
    def stitch_count(self) -> int:
        return self.produced + (self.turning_chain_counts and self.turning_chain > 0)


@dataclass
class CompileResult:
    cir: CIR
    rows: list[ResolvedRow] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == ERROR for f in self.findings)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == WARNING]

    def row(self, component: str, index: int) -> ResolvedRow:
        for r in self.rows:
            if r.component == component and r.index == index:
                return r
        raise KeyError(f"no resolved row {component}/{index}")

    def counts(self, component: str) -> list[int]:
        return [r.stitch_count for r in self.rows if r.component == component]


def _flatten(nodes: Iterable[OpNode], available: int, group: list[int]) -> tuple[list[ResolvedOp], list[str]]:
    """Expand ops, resolving to-end repeats against `available`.

    Returns (resolved ops, problems). `group` is a one-element mutable counter so nested
    repeats can be labelled without a class.
    """
    out: list[ResolvedOp] = []
    problems: list[str] = []

    # First pass: everything except the to-end repeat, so we know what it has to absorb.
    fixed_consume = 0
    to_end: list[int] = []
    for i, n in enumerate(nodes):
        if isinstance(n, Repeat) and n.times is None:
            to_end.append(i)
        else:
            try:
                fixed_consume += n.consumes
            except Exception:  # pragma: no cover - guarded by model validation
                problems.append(f"could not resolve consumption of {n!r}")

    if len(to_end) > 1:
        problems.append("a row may contain at most one to-end repeat")
        return out, problems

    nodes = list(nodes)
    for i, n in enumerate(nodes):
        if isinstance(n, Op):
            out.append(ResolvedOp(n.stitch, n.count, n.consumes, n.produces))
            continue

        assert isinstance(n, Repeat)
        gid = group[0]
        group[0] += 1

        if n.times is None:
            unit = n.unit_consumes
            if unit <= 0:
                problems.append("to-end repeat consumes no stitches; it would never terminate")
                continue
            budget = available - fixed_consume
            if budget < 0:
                problems.append(
                    f"fixed stitches consume {fixed_consume} but only {available} are available"
                )
                continue
            times = budget // unit
            leftover = budget - times * unit
            if times < 1:
                problems.append(
                    f"to-end repeat needs {unit} stitches per repeat but only {budget} remain"
                )
                continue
            if leftover:
                problems.append(
                    f"to-end repeat of {unit} st does not divide the {budget} available "
                    f"stitches evenly ({leftover} left over)"
                )
        else:
            times = n.times

        for _ in range(times):
            sub, sub_problems = _flatten(n.ops, available, group)
            problems.extend(sub_problems)
            for r in sub:
                out.append(
                    ResolvedOp(r.stitch, r.count, r.consumes, r.produces, repeat_group=gid)
                )

    return out, problems


def compile_component(comp: Component, cir: CIR, findings: list[Finding]) -> list[ResolvedRow]:
    resolved: list[ResolvedRow] = []
    counts_by_index: dict[int, int] = {}

    available = comp.foundation
    if comp.construction == "flat_rows" and comp.foundation == 0 and comp.rows:
        findings.append(
            Finding(
                WARNING,
                "NO_FOUNDATION",
                "flat component declares no foundation chain; row 1 will be validated "
                "against its own production only",
                comp.name,
            )
        )

    for row in comp.rows:
        if row.into is not None:
            if row.into not in counts_by_index:
                findings.append(
                    Finding(
                        ERROR,
                        "BAD_INTO",
                        f"row works into row {row.into}, which has not been worked yet",
                        comp.name,
                        row.index,
                    )
                )
                continue
            into_count = counts_by_index[row.into]
        else:
            into_count = available

        # Row 1 of a flat piece with no foundation has nothing to consume; treat its own
        # production as authoritative rather than inventing a constraint.
        first_freeform = (
            row is comp.rows[0] and comp.foundation == 0 and row.into is None
        )

        ops, problems = _flatten(row.ops, into_count, [0])
        for p in problems:
            findings.append(Finding(ERROR, "REPEAT", p, comp.name, row.index))

        consumed = sum(o.consumes for o in ops)
        produced = sum(o.produces for o in ops)
        remainder = into_count - consumed

        if not first_freeform:
            if consumed > into_count:
                findings.append(
                    Finding(
                        ERROR,
                        "OVERRUN",
                        f"row consumes {consumed} stitches but only {into_count} are available",
                        comp.name,
                        row.index,
                    )
                )
            elif remainder > 0 and not row.allow_remainder:
                findings.append(
                    Finding(
                        ERROR,
                        "UNDERRUN",
                        f"row consumes {consumed} of {into_count} available stitches, "
                        f"leaving {remainder} unworked and undeclared",
                        comp.name,
                        row.index,
                    )
                )

        total = produced + (1 if row.turning_chain_counts and row.turning_chain > 0 else 0)

        if row.declared_count is not None and row.declared_count != total:
            findings.append(
                Finding(
                    ERROR,
                    "COUNT_MISMATCH",
                    f"pattern declares {row.declared_count} stitches but the row produces {total}",
                    comp.name,
                    row.index,
                )
            )

        if total <= 0:
            findings.append(
                Finding(
                    ERROR,
                    "EMPTY_ROW",
                    "row produces no stitches, so the fabric cannot continue",
                    comp.name,
                    row.index,
                )
            )

        if row.turning_chain == 0 and comp.construction == "flat_rows":
            tallest = max((stitches.get(o.stitch).height for o in ops), default=0)
            if tallest >= 2.0:
                findings.append(
                    Finding(
                        WARNING,
                        "NO_TURNING_CHAIN",
                        "row uses stitches taller than sc but declares no turning chain; "
                        "edges will pull in",
                        comp.name,
                        row.index,
                    )
                )

        if row.color and cir.colors and row.color not in cir.colors:
            findings.append(
                Finding(
                    ERROR,
                    "UNKNOWN_COLOR",
                    f"row references colour {row.color!r} which is not in the colour table",
                    comp.name,
                    row.index,
                )
            )

        resolved.append(
            ResolvedRow(
                component=comp.name,
                index=row.index,
                into_count=into_count,
                consumed=consumed,
                produced=produced,
                remainder=max(0, remainder),
                color=row.color,
                ops=ops,
                turning_chain=row.turning_chain,
                turning_chain_counts=row.turning_chain_counts,
            )
        )
        counts_by_index[row.index] = total
        available = total

    indices = [r.index for r in comp.rows]
    if indices != sorted(indices):
        findings.append(
            Finding(ERROR, "ROW_ORDER", f"row indices are not ascending: {indices}", comp.name)
        )
    if len(indices) != len(set(indices)):
        findings.append(
            Finding(ERROR, "DUPLICATE_ROW", f"duplicate row indices: {indices}", comp.name)
        )

    return resolved


def check_assembly(cir: CIR, findings: list[Finding]) -> None:
    """Validate the finishing: a seam that names a piece the pattern does not contain is a
    maker standing there with two rectangles and an instruction about a third."""
    by_name = {c.name: c for c in cir.components}
    names = set(by_name)
    stuffing = any("stuff" in m.name.lower() or "fibre" in m.name.lower()
                   or "fiber" in m.name.lower() for m in cir.materials)
    for position, seam in enumerate(cir.assembly, start=1):
        for piece in (seam.piece_a, seam.piece_b):
            if piece not in names:
                findings.append(Finding(
                    ERROR, "ASSEMBLY_UNKNOWN_PIECE",
                    f"assembly step {position} joins {piece!r}, which is not a component of "
                    f"this pattern (have: {sorted(names)})"))
        if seam.stuff_before_closing and not stuffing:
            findings.append(Finding(
                WARNING, "ASSEMBLY_NO_STUFFING_DECLARED",
                f"assembly step {position} says to stuff before closing, but no stuffing is "
                f"in the materials list, so the buyer will not have bought any"))

        # Placement has to point at fabric that exists. "Attach at round 40" on a
        # twenty-round head is an instruction a maker stops at, and it is the kind of
        # mistake that survives every other check in this system because the pieces
        # themselves are all correct.
        host = by_name.get(seam.piece_b)
        if seam.is_placed and host is not None:
            rounds = [r.index for r in host.rows]
            last = max(rounds, default=0)
            first = min(rounds, default=0)
            end = seam.at_round + seam.spans_rounds - 1
            if seam.at_round < first or end > last:
                findings.append(Finding(
                    ERROR, "ASSEMBLY_PLACEMENT_OFF_PIECE",
                    f"assembly step {position} attaches across rounds {seam.at_round}-{end} "
                    f"of {seam.piece_b!r}, which has rounds {first}-{last}"))
            elif seam.stitches_from_centre is not None:
                width = next((r.declared_count for r in host.rows
                              if r.index == seam.at_round), None)
                if width is not None and seam.stitches_from_centre * 2 > width:
                    findings.append(Finding(
                        ERROR, "ASSEMBLY_PLACEMENT_TOO_WIDE",
                        f"assembly step {position} places the join "
                        f"{seam.stitches_from_centre} stitches either side of centre on a "
                        f"round of {width} stitches; the two would overlap"))
        if seam.spans_rounds < 1:
            findings.append(Finding(
                ERROR, "ASSEMBLY_PLACEMENT_EMPTY",
                f"assembly step {position} spans {seam.spans_rounds} rounds"))

    # A multi-piece pattern whose joins do not say where they go is the bag-of-pieces
    # failure with extra steps: every piece correct, and no way to arrive at the object.
    unplaced = [i for i, seam in enumerate(cir.assembly, start=1)
                if not seam.is_self_seam and not seam.is_placed]
    if unplaced and len(names) > 1:
        findings.append(Finding(
            WARNING, "ASSEMBLY_UNPLACED",
            f"assembly steps {unplaced} join two different pieces without saying where on "
            f"the second piece the join happens. A maker can follow every round and still "
            f"not know where the ears go"))


def compile_cir(cir: CIR) -> CompileResult:
    """Compile and validate a CIR. Never raises on pattern problems -- it reports them."""
    result = CompileResult(cir=cir)
    for comp in cir.components:
        result.rows.extend(compile_component(comp, cir, result.findings))
    check_assembly(cir, result.findings)
    return result
