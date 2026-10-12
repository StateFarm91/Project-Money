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
        end = (1 - start) if plan.turned else start
        resting[r.color] = end
        edge = end
    # Two ends per colour (its first join and its last fasten-off) and two per cut-and-rejoin.
    plan.ends = 2 * len(colours_seen) + 2 * plan.cut
    return plan


def analyse(cir: CIR) -> dict[str, ColourPlan]:
    return {c.name: plan_component(c) for c in cir.components}


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
