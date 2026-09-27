"""Shaping primitives: tapers and bind-offs, generated rather than hand-counted.

A sleeve that goes from 36 stitches at the cuff to 58 at the upper arm over 70 rows is eleven
increase rows spread across seventy, and the spreading is where hand-written patterns go
wrong: "increase every 6th row 11 times" is 66 rows, not 70, and the last four rows are
nobody's decision. This module makes that arithmetic a function so it is done once, exactly,
for every size of every design.

Two rules.

**Evenly distributed, exactly.** Shaping events are placed with Bresenham's line algorithm:
row `i` of `n` carries `floor(i*k/n) - floor((i-1)*k/n)` of the `k` events. That is the
closest integer approximation of a straight line from the start count to the end count --
the edge of the finished piece is as straight as whole stitches allow -- and the last row
lands exactly on the target count by construction, so the final number is never a rounding
accident.

**A bind-off is a promise about the stitches left behind.** Crochet does not cast off: the
stitches a shaped edge leaves are simply not worked again. `bind_off` expresses that with the
two primitives the compiler already checks -- `Row.skips` for the stitches this piece stops
working, and a `Hold` when some of them are picked up later by another piece (the second
shoulder of a divided neck) -- so an unworked stitch is either declared finished or declared
waiting, and never merely forgotten.

Nothing here is garment vocabulary. A basket's tapered wall, a bag's gusset and a toy's leg
use the same two functions.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import stitches
from .model import Hold, LoopTarget, Op, Row

# What each stitch family increases and decreases with. A family with no decrease cannot
# taper down, and saying so is better than silently substituting a single-crochet decrease
# into a half-double fabric (which changes the row height at that edge).
SHAPING: dict[str, tuple[str, str | None]] = {
    "sc": ("inc", "dec"),
    "dc": ("dc_inc", "dc_dec"),
    "hdc": ("hdc_inc", None),
}

Edge = str  # "both" | "start" | "end"


class ShapingRefused(ValueError):
    """A taper or bind-off whose arithmetic does not close."""


def distribute(events: int, rows: int) -> list[int]:
    """How many of `events` fall on each of `rows` rows, as evenly as whole numbers allow.

    Bresenham: the cumulative total after row i is floor(i * events / rows), so the sum is
    exactly `events` and no two rows differ by more than one.
    """
    if rows < 1:
        raise ShapingRefused("a taper needs at least one row to happen over")
    if events < 0:
        raise ShapingRefused("a negative number of shaping events is not a taper")
    return [(i * events) // rows - ((i - 1) * events) // rows for i in range(1, rows + 1)]


@dataclass(frozen=True)
class Taper:
    """The rows of a taper, and the counts they declare."""

    rows: tuple[Row, ...]
    counts: tuple[int, ...]

    @property
    def final_count(self) -> int:
        return self.counts[-1]


def taper(from_count: int, to_count: int, over_rows: int, *, edge: Edge = "both",
          stitch: str = "sc", first_index: int = 1, turning_chain: int = 1,
          loop: LoopTarget = "both", color: str | None = None,
          loops_by_row: dict[int, LoopTarget] | None = None) -> Taper:
    """Rows taking a piece from `from_count` to `to_count` stitches over `over_rows` rows.

    `edge="both"` shapes symmetrically, one event at each edge, so the difference must be
    even; "start" or "end" shape one edge only. Increases are one-into-two, decreases
    two-into-one, in the stitch family's own shaping stitch, placed at the very edge.
    `loops_by_row` overrides `loop` for particular row indices (a textured fabric alternates).
    """
    if from_count < 1 or to_count < 1:
        raise ShapingRefused("a taper must start and end on at least one stitch")
    if stitch not in SHAPING:
        raise ShapingRefused(f"no shaping stitches are defined for {stitch!r}: "
                             f"{sorted(SHAPING)}")
    if edge not in ("both", "start", "end"):
        raise ShapingRefused(f"edge must be both, start or end, not {edge!r}")
    stitches.get(stitch)
    inc_code, dec_code = SHAPING[stitch]
    diff = to_count - from_count
    growing = diff > 0
    shaper = inc_code if growing else dec_code
    if diff and shaper is None:
        raise ShapingRefused(f"{stitch} has no decrease stitch in this schema; a taper down "
                             f"in {stitch} cannot be written honestly")
    sides = 2 if edge == "both" else 1
    if abs(diff) % sides:
        raise ShapingRefused(
            f"a symmetric taper changes both edges together, so {from_count} to {to_count} "
            f"(a difference of {abs(diff)}) cannot be shaped evenly at both edges")
    per_row = distribute(abs(diff) // sides, over_rows)

    rows: list[Row] = []
    counts: list[int] = []
    current = from_count
    for offset, events in enumerate(per_row):
        index = first_index + offset
        row_loop = (loops_by_row or {}).get(index, loop)
        if not events:
            ops = [Op(stitch, current, loop=row_loop)]
            produced = current
        else:
            # Each increase consumes one and makes two; each decrease consumes two and makes
            # one. The plain run in the middle is whatever the edges leave.
            consumed_at_edges = events * sides * (1 if growing else 2)
            middle = current - consumed_at_edges
            if middle < 0:
                raise ShapingRefused(
                    f"row {index} would decrease {events * sides} times over {current} "
                    f"stitches; the taper is too steep for the width")
            edge_op = Op(shaper, events, loop=row_loop)
            ops = []
            if edge in ("both", "start"):
                ops.append(edge_op)
            if middle:
                ops.append(Op(stitch, middle, loop=row_loop))
            if edge in ("both", "end"):
                ops.append(Op(shaper, events, loop=row_loop))
            produced = current + (events * sides if growing else -events * sides)
        rows.append(Row(index=index, ops=ops, declared_count=produced,
                        turning_chain=turning_chain, color=color))
        counts.append(produced)
        current = produced
    if current != to_count:  # pragma: no cover - Bresenham closes by construction
        raise ShapingRefused(f"taper ended on {current}, not {to_count}")
    return Taper(rows=tuple(rows), counts=tuple(counts))


@dataclass(frozen=True)
class BindOff:
    """A row that stops working some stitches, and the hold for any that wait."""

    row: Row
    hold: Hold | None
    finished: int      # stitches left unworked for good (the bound-off edge)

    @property
    def worked(self) -> int:
        return self.row.declared_count or 0


def bind_off(available: int, keep: int, *, index: int, after_row: int,
             hold_name: str | None = None, hold_count: int = 0, stitch: str = "sc",
             turning_chain: int = 1, loop: LoopTarget = "both",
             color: str | None = None) -> BindOff:
    """Work `keep` of `available` stitches; the rest are finished, or held for later.

    The kept stitches are the first `keep` of the row below. When `hold_count` is given, the
    LAST `hold_count` stitches of the row `after_row` are held as `hold_name` for another
    component to resume, and whatever lies between the kept and the held stitches is the
    bound-off edge -- the centre of a divided neckline, for instance. `after_row` is the
    row whose stitches are held; the returned row is the one worked next, at `index`.
    """
    if not 1 <= keep < available:
        raise ShapingRefused(f"a bind-off keeps between 1 and {available - 1} stitches, "
                             f"not {keep}")
    if hold_count < 0 or keep + hold_count > available:
        raise ShapingRefused(f"keeping {keep} and holding {hold_count} of {available} "
                             f"stitches claims stitches that are not there")
    if hold_count and not hold_name:
        raise ShapingRefused("held stitches need a name for the piece that resumes them")
    hold = None
    if hold_count:
        hold = Hold(name=hold_name, at_row=after_row, count=hold_count,
                    from_stitch=available - hold_count,
                    note=f"{available - keep - hold_count} sts between are left unworked")
    row = Row(index=index, ops=[Op(stitch, keep, loop=loop)], declared_count=keep,
              turning_chain=turning_chain, color=color, skips=available - keep)
    return BindOff(row=row, hold=hold, finished=available - keep - hold_count)
