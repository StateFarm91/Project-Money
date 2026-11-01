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

from .model import CIR, op_colours

CARRIED = "carried"
CUT = "cut"
# P0-CIR-COLOURWORK: a row whose stitches change colour is tapestry work. Every yarn in it is
# carried inside the stitches (worked over), so it travels with the row and rests at the row's
# end edge like the main colour; nothing is cut at a change inside the row.
IN_ROW = "in_row"
TAPESTRY_CUT = "tapestry_cut"   # OPUS2I I-4: a contrast cut between tapestry rows, kept apart
                                # from the row-change cuts that `carry_is_possible` judges


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
    tapestry_rows: list[int] = field(default_factory=list)
    tapestry_cuts: int = 0
    first_tapestry_cut_row: int | None = None

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
    previous_in_row: set[str] = set()
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
        # Tapestry: the stitch colours of this row are carried inside it, so each rests where
        # the row ends, and each is a yarn the piece uses (its own join and fasten-off).
        # OPUS2H H2-2: a contrast that is resting at the other edge from where this turned row
        # starts (a plain row moved the work away from it) cannot be picked up there: it is
        # cut and rejoined, which costs two ends, unless it was carried in the row just before.
        in_row = sorted(op_colours(r.ops) - {r.color})
        for colour in in_row:
            if colour not in colours_seen:
                colours_seen.add(colour)
            elif (plan.turned and colour in resting and resting[colour] != start
                  and colour not in previous_in_row):
                plan.tapestry_cuts += 1
                plan.events.append((r.index, colour, TAPESTRY_CUT))
                if plan.first_tapestry_cut_row is None:
                    plan.first_tapestry_cut_row = r.index
            resting[colour] = end
            plan.events.append((r.index, colour, IN_ROW))
            if r.index not in plan.tapestry_rows:
                plan.tapestry_rows.append(r.index)
        previous_in_row = set(in_row)
        edge = end
    # Two ends per colour (its first join and its last fasten-off) and two per cut-and-rejoin.
    plan.ends = 2 * len(colours_seen) + 2 * plan.cut + 2 * plan.tapestry_cuts
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
    # Integration W5-INTEG1 x P0-CIR-COLOURWORK (review OPUS2J J-7): a joined-round piece with
    # tapestry (stitch-level) colour must print the tapestry sentence and its ends too, even
    # when no round changes its main colour -- otherwise the PDF omits how to work the contrast.
    tapestry = _tapestry_sentence(plan)
    each = f" on each {piece}" if make > 1 else ""
    if plan.changes == 0:
        if not tapestry:
            return None
        return f"{tapestry} Ends to weave in: about {plan.ends}{each}."
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
    if tapestry:
        out.append(tapestry)
    out.append(f"Ends to weave in: about {plan.ends}{each}.")
    return " ".join(out)


def _tapestry_sentence(plan: ColourPlan) -> str | None:
    if not plan.tapestry_rows:
        return None
    rows = plan.tapestry_rows
    span = _row_list(rows)
    unit = "row" if plan.turned else "round"
    plural = "s" if len(rows) > 1 else ""
    sentence = (f"Colourwork {unit}{plural} {span}: work over the colour not in use so it is "
                f"carried inside the stitches, and change colour on the last yarn-over of the "
                f"stitch before the new colour.")
    cuts = [row for row, _c, kind in plan.events if kind == TAPESTRY_CUT]
    if cuts:
        sentence += (f" Where a contrast was left at the other edge ({unit}{'s' if len(cuts) > 1 else ''} "
                     f"{_row_list(sorted(set(cuts)))}), cut it at the end of its last {unit} and "
                     f"rejoin it at the start of the next colourwork {unit}, leaving a 10 cm tail.")
    else:
        sentence += " Do not cut at these changes."
    return sentence


def _row_list(rows: list[int]) -> str:
    """Exact rows: "3", "2 and 4", "2, 4 and 6", runs compressed ("3-10")."""
    parts: list[str] = []
    start = prev = None
    for r in rows:
        if start is None:
            start = prev = r
        elif r == prev + 1:
            prev = r
        else:
            parts.append(f"{start}" if start == prev else f"{start}-{prev}")
            start = prev = r
    if start is not None:
        parts.append(f"{start}" if start == prev else f"{start}-{prev}")
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def instruction(plan: ColourPlan) -> str | None:
    """The finishing sentence the written pattern prints about colour changes, or None."""
    tapestry = _tapestry_sentence(plan)
    if plan.changes == 0:
        return tapestry
    if tapestry:
        rest = _row_instruction(plan)
        return f"{rest} {tapestry}" if rest else tapestry
    return _row_instruction(plan)


def _row_instruction(plan: ColourPlan) -> str | None:
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
