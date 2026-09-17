"""Row-level repeats, derived rather than declared (Master Plan section 2).

A real crochet pattern does not print 120 rows when 24 of them repeat five times. It prints
the 24 and says "repeat rows 2-25 four more times". Ours printed all 120, which is technically
complete and practically unusable: a maker following it loses their place, and the PDF is four
pages of near-identical lines.

The design decision that matters here is **derived, not declared.** The obvious approach is a
new CIR field where a designer states the repeat. That field can disagree with the rows — and a
pattern whose stated repeat does not match its actual rows is a defect no arithmetic catches,
because both halves are internally consistent. So there is no field. The cycle is computed
from the compiled rows, which means it cannot be wrong, it needs no schema change, and every
existing product gets it for free.

The reverse compiler has to be able to undo this. It reads only the customer text, so when the
text says "repeat rows 2-25 four more times" it expands that back to 120 rows before
comparing. Collapsing the writer's output without teaching the reader to expand it would have
broken the one property the whole validation chain rests on.
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import Op, OpNode, Repeat, Row

# Below this, collapsing costs more than it saves: "repeat rows 2-3 once more" is longer than
# the two rows it replaces and reads as a puzzle.
MIN_CYCLE_ROWS = 4
# One further pass is enough when the block is large: collapsing a 24-row block once still
# removes 24 lines of near-identical prose, which is the whole point.
MIN_REPEATS = 1


@dataclass(frozen=True)
class RowCycle:
    """`repeats` further passes of rows `start`..`end`, inclusive, 1-indexed by row number."""

    start: int
    end: int
    repeats: int

    @property
    def period(self) -> int:
        return self.end - self.start + 1

    @property
    def rows_saved(self) -> int:
        return self.period * self.repeats

    def covers(self, row_index: int) -> bool:
        """True for a row that the repeat instruction replaces."""
        return self.end < row_index <= self.end + self.rows_saved


def _signature(row: Row) -> tuple:
    """Everything about a row a maker would notice. Two rows with the same signature are the
    same instruction, so one can stand for the other."""
    return (
        tuple(_shape(op) for op in row.ops),
        row.declared_count,
        row.turning_chain,
        row.turning_chain_counts,
        row.color,
        row.into,
        row.allow_remainder,
        (row.note or "").strip(),
    )


def _shape(node: OpNode) -> tuple:
    if isinstance(node, Op):
        return ("op", node.stitch, node.count)
    return ("rep", node.times, tuple(_shape(o) for o in node.ops))


def detect_cycle(rows: list[Row], *, min_period: int = MIN_CYCLE_ROWS,
                 min_repeats: int = MIN_REPEATS) -> RowCycle | None:
    """Find the longest run of whole repeated row-blocks in a component.

    Deliberately simple and deliberately conservative. It looks for one block, starting after
    any non-repeating preamble (a foundation row, a set-up row), that tiles the rest of the
    component exactly. A partial trailing repeat is not collapsed: "repeat rows 2-25 four more
    times, then work rows 2-9 once" is harder to follow than the rows themselves.
    """
    n = len(rows)
    if n < min_period * (min_repeats + 1):
        return None

    signatures = [_signature(r) for r in rows]

    best: RowCycle | None = None
    # `start` is the first row of the block; anything before it is preamble.
    for start in range(n):
        remaining = n - start
        for period in range(min_period, remaining // (min_repeats + 1) + 1):
            if remaining % period:
                continue
            copies = remaining // period
            if copies < min_repeats + 1:
                continue
            block = signatures[start:start + period]
            if all(signatures[start + i * period + j] == block[j]
                   for i in range(1, copies) for j in range(period)):
                candidate = RowCycle(start=rows[start].index,
                                     end=rows[start + period - 1].index,
                                     repeats=copies - 1)
                if candidate.rows_saved < min_period:
                    continue   # not worth the reader's attention
                if best is None or candidate.rows_saved > best.rows_saved:
                    best = candidate
    return best


def expand(rows: list[Row], cycle: RowCycle) -> list[Row]:
    """Undo a collapse: the rows a repeat instruction stands for, renumbered in sequence.

    Used by the reverse compiler. It reads collapsed customer text and needs the full row list
    to compare against, and the expansion has to be the reader's own work rather than
    something the writer hands it -- otherwise the two are no longer independent.
    """
    by_index = {r.index: r for r in rows}
    block = [by_index[i] for i in range(cycle.start, cycle.end + 1) if i in by_index]
    if len(block) != cycle.period:
        raise KeyError(f"rows {cycle.start}-{cycle.end} are not all present")

    out = list(rows)
    next_index = max(by_index) + 1
    for _ in range(cycle.repeats):
        for row in block:
            out.append(Row(index=next_index, ops=list(row.ops),
                           declared_count=row.declared_count,
                           turning_chain=row.turning_chain,
                           turning_chain_counts=row.turning_chain_counts,
                           color=row.color, into=row.into,
                           allow_remainder=row.allow_remainder, note=row.note))
            next_index += 1
    return out


def describe(cycle: RowCycle, final_row_index: int) -> str:
    """The customer-facing sentence. Says both what to repeat and where it ends.

    Stating the final row number is not redundant: it is the maker's checkpoint. Without it,
    someone who loses count has no way to tell whether they have worked four repeats or five,
    and the pattern gives them nothing to check against.
    """
    last = final_row_index
    times = "once more" if cycle.repeats == 1 else f"{cycle.repeats} more times"
    return (f"Repeat rows {cycle.start}-{cycle.end} {times}, "
            f"ending with row {last}. ({cycle.repeats + 1} repeats of the "
            f"{cycle.period}-row block in total.)")
