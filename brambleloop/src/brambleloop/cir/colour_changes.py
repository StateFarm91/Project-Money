"""Where each colour change happens, and whether the resting yarn is there to pick up (PT-09).

A two-colour piece worked in turned flat rows starts each row at the edge the previous row
ended on. A colour that is put down at one edge can only be "carried up the side" if the next
row that needs it starts at that same edge. With one-row stripes it never does: the resting
colour is always at the far edge, so the maker has to cut it and rejoin -- two ends per
change. The Cloudline blanket's designer note told the maker to carry the resting colour up
the side on a fabric where that is impossible on every change (~64 changes, ~128 ends).

This module answers the question from the rows alone, deterministically, so the note, the
written finishing instructions and the certificate cannot disagree with the fabric:

  * `analyse(cir)` walks every component's rows in working order and classifies every colour
    change as CARRIED (the incoming colour is resting at the edge this row starts from) or
    CUT (it is resting at the other edge, so it must be cut and rejoined), and counts the
    ends to weave in;
  * rounds that are joined or spiralled never turn, so every change happens at the same
    place and the colour not in use can always be carried up the inside of the join.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import CIR

CARRIED = "carried"
CUT = "cut"


@dataclass
class ColourPlan:
    component: str
    changes: int = 0
    carried: int = 0
    cut: int = 0
    first_cut_row: int | None = None
    ends: int = 0
    turned: bool = True
    events: list[tuple[int, str, str]] = field(default_factory=list)   # (row, colour, kind)
    # Per colour, the rows it is worked in, in working order -- what the round-worked wording
    # below reads its "cut after", "rests" and "pick up again" rounds from.
    rows_by_colour: dict[str, list[int]] = field(default_factory=dict)
    last_row: int | None = None

    @property
    def carry_is_possible(self) -> bool:
        """True when every change can be made by carrying the resting colour."""
        return self.cut == 0


def plan_component(comp) -> ColourPlan:
    rows = [r for r in comp.rows if r.color]
    plan = ColourPlan(component=comp.name, turned=comp.construction == "flat_rows")
    if not rows:
        return plan
    resting: dict[str, int] = {}        # colour -> edge its yarn rests at (0 or 1)
    current = None
    edge = 0                            # the edge row 1 starts from
    colours_seen: set[str] = set()
    for r in rows:
        start = edge
        if r.color != current:
            if current is not None:
                plan.changes += 1
                if r.color in resting and (resting[r.color] == start or not plan.turned):
                    plan.carried += 1
                    plan.events.append((r.index, r.color, CARRIED))
                elif r.color in resting:
                    plan.cut += 1
                    plan.events.append((r.index, r.color, CUT))
                    if plan.first_cut_row is None:
                        plan.first_cut_row = r.index
            colours_seen.add(r.color)
            current = r.color
        plan.rows_by_colour.setdefault(r.color, []).append(r.index)
        plan.last_row = r.index
        end = (1 - start) if plan.turned else start
        resting[r.color] = end
        edge = end
    # Two ends per colour (its first join and its last fasten-off) and two per cut-and-rejoin.
    plan.ends = 2 * len(colours_seen) + 2 * plan.cut
    return plan


def analyse(cir: CIR) -> dict[str, ColourPlan]:
    return {c.name: plan_component(c) for c in cir.components}


_COUNT_WORDS = {2: "Both", 3: "All three", 4: "All four", 5: "All five", 6: "All six"}


def _rests(rows: list[int]) -> list[tuple[int, int]]:
    """The (first, last) rows a colour sits out between two of its own runs."""
    return [(a + 1, b - 1) for a, b in zip(rows, rows[1:]) if b - a > 1]


def _span(a: int, b: int, label: str) -> str:
    return f"{label} {a}" if a == b else f"{label}s {a}-{b}"


def rounds_instruction(plan: ColourPlan, *, piece: str = "piece", make: int = 1,
                       upright: bool = False) -> str | None:
    """The colour-change wording for work in joined or spiral rounds (F2, 2026-10-31).

    Derived round by round from the rows, like the turned-row wording, and it says three
    things the earlier sentence did not: a colour whose last round is not the last round of
    the piece is cut and fastened off after that round (it is never needed again, so nothing
    is carried); a colour that sits out some rounds and returns is left attached and picked up
    again at the join; and the ends are counted per piece. "Up the inside of the join" is
    said only of a piece that has an inside -- a flat disc is carried on its wrong side.
    """
    if plan.changes == 0:
        return None
    lead = ("The one colour change falls" if plan.changes == 1 else
            f"{_COUNT_WORDS.get(plan.changes, f'All {plan.changes}')} colour changes fall")
    out = [f"{lead} at the join: make the joining sl st at the end of the round before in "
           f"the new colour."]
    where = "up the inside of the join" if upright else "on the wrong side at the join"
    for colour in sorted(plan.rows_by_colour, key=lambda c: plan.rows_by_colour[c][0]):
        rows = plan.rows_by_colour[colour]
        rests = _rests(rows)
        if rests:
            spans = " and ".join(_span(a, b, "Rnd") for a, b in rests)
            if len(rests) > 1:
                spans = "Rnds " + " and ".join(
                    f"{a}" if a == b else f"{a}-{b}" for a, b in rests)
            backs = " and ".join(str(b + 1) for _a, b in rests)
            out.append(f"Leave {colour} attached while it rests ({spans}), carrying it "
                       f"loosely {where}, and pick it up again for "
                       f"Rnd{'s' if len(rests) > 1 else ''} {backs}.")
        if plan.last_row is not None and rows[-1] < plan.last_row:
            out.append(f"Cut {colour} after Rnd {rows[-1]} and fasten it off; it is not used "
                       f"again.")
    each = f" on each {piece}" if make > 1 else ""
    out.append(f"Ends to weave in: about {plan.ends}{each}.")
    return " ".join(out)


def instruction(plan: ColourPlan) -> str | None:
    """The finishing sentence the written pattern prints about colour changes, or None."""
    if plan.changes == 0:
        return None
    if plan.carry_is_possible:
        where = ("at the same side edge" if plan.turned else "at the join")
        return (f"Colour changes: all {plan.changes} changes fall {where}, where the colour "
                f"not in use is resting, so carry it loosely up "
                f"{'that edge' if plan.turned else 'the inside of the join'} rather than "
                f"cutting it. Ends to weave in: about {plan.ends}.")
    return (f"Colour changes: {plan.cut} of the {plan.changes} start at the edge opposite the "
            f"resting colour, so it cannot be carried: cut it at the end of its row and rejoin "
            f"it at the start of its next row, leaving a 10 cm tail. Ends to weave in: about "
            f"{plan.ends}.")


CARRY_WORDS = ("carry the resting colour", "carry the colour", "carry it up the side",
               "carried up the side", "carry the yarn up")


def claims_carry(text: str) -> bool:
    low = " ".join((text or "").lower().split())
    return any(w in low for w in CARRY_WORDS)
