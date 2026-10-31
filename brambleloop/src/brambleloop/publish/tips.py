"""Tips and troubleshooting, decided by what this pattern contains.

A tips page is where a pattern document most easily starts saying things nobody checked:
generic advice pasted onto every product, numbers that belonged to another design, a promise
about how firm a basket wall will be from a company that has never made one. So every tip here
is switched on by a feature the compiled pattern actually has, and every number in it is read
from the twin or the compiler -- never typed. A tip with no trigger in this pattern is not
printed, and a tip about how the finished object behaves physically (stiffness, wear, wash) is
not written at all until a physical sample exists to say so.

The advice itself is standard crochet technique -- how to read a ruffle, where a colour change
goes, what a twisted corner means -- in the same sense as `abbreviations.METHOD`: a property of
the technique rather than of any one design. Stitch names are resolved through the registry
for the document's terminology, so a UK document never receives a US word by way of a tip.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tip:
    title: str
    text: str
    trigger: str          # what in the pattern switched this tip on (kept for the audit)


def _times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def _rows(twin) -> dict[int, list]:
    rows: dict[int, list] = {}
    for c in twin.cells:
        rows.setdefault(c.row, []).append(c)
    return dict(sorted(rows.items()))


def tips(cir, result, twin, text: str, terminology: str = "US") -> list[Tip]:
    from ..cir.geometry import corners
    from ..cir.writer import JOINED_LINE
    from . import abbreviations as ab

    out: list[Tip] = []
    rows = _rows(twin)
    if not rows:
        return out
    comp = cir.components[0]
    piece = comp.name.replace("_", " ")
    round_word = "round" if "round" in comp.construction else "row"
    label = "Rnd" if round_word == "round" else "Row"
    first, last = min(rows), max(rows)
    stitch = ab.token(cir.gauge.stitch_type, terminology) if cir.gauge else "stitch"

    # 1. counts -- every pattern the writer gives a count per line for.
    if "sts)" in text:
        out.append(Tip(
            "Count every " + round_word,
            f"Each {round_word} ends with its stitch total in brackets, from "
            f"{len(rows[first])} sts at {label} {first} to {len(rows[last])} sts at "
            f"{label} {last}. Put a stitch marker in the first stitch of every {round_word} and "
            f"count before you join: a {round_word} that is one stitch out is a minute to fix "
            f"now and a frustration later.",
            "the written pattern states a stitch count on every line"))

    rings = list(getattr(getattr(twin, "geometry", None), "rings", []) or [])
    base = [r for r in rings if r.rise_cm <= 0]
    wall = [r for r in rings if r.rise_cm > 0]
    sides = None
    if len(cir.components) == 1 and rings:
        sides = corners([r for r in result.rows if r.component == comp.name])

    # 2. a flat disc or base: ruffle vs cup.
    if base:
        upto = base[-1].index
        out.append(Tip(
            "If it ruffles or cups",
            f"Up to {label} {upto} the {piece} should lie flat. If it ruffles like a frill, it "
            f"has more stitches than it needs or your stitches are loose; if it curls up into "
            f"a bowl, a {round_word} is short of increases or your stitches are tight. Count "
            f"the last {round_word} against its total first, then compare its size with "
            f"'Checking your progress'.",
            f"{len(base)} {round_word}s grow outward without rising (twin.geometry)"))

    # 3. stacked increases make corners.
    if sides:
        out.append(Tip(
            "Keeping the corners straight",
            f"The {sides} corners come from each {round_word}'s increases sitting directly on "
            f"top of the increases below. If the corners start to twist into a swirl, the "
            f"start of the {round_word} has drifted: begin every {round_word} in its first "
            f"stitch, where your marker is, and work the repeat exactly as written.",
            f"cir.geometry.corners reports {sides} stacked corners"))

    # 4. a wall rising from a base.
    first_wall_loops = ({getattr(c, "loop", "both") for c in twin.cells
                         if c.row == wall[0].index} if base and wall else set())
    if base and wall and first_wall_loops == {"back"}:
        # 1.3.0: a back-loop first wall round makes a defined edge, not a gradual turn.
        out.append(Tip(
            "Turning the base into the wall",
            f"{label} {wall[0].index} is worked in the back loop only. The front loops you "
            f"leave unworked make a ridge around the outside of the base, and the base folds "
            f"up along that ridge into the wall, so the edge is defined rather than rounded. "
            f"Every wall {round_word} keeps the base's stitch count, so the count does not "
            f"make the wall flare; if it leans outward, check your tension against the gauge.",
            f"{label} {wall[0].index} is worked in the back loop (twin.cells loop)"))
    elif base and wall:
        out.append(Tip(
            "Turning the base into the wall",
            f"{label} {wall[0].index} is the first {round_word} with no increases, so the edge "
            f"of the base starts to turn upward there. Let it turn rather than pulling it flat; "
            f"by {label} {wall[min(len(wall) - 1, 3)].index} the wall will be clearly rising "
            f"from the base.",
            f"{label} {wall[0].index} is the first ring with rise (twin.geometry)"))

    # 5. colour changes at the join.
    changes = sum(1 for a, b in zip(list(rows)[:-1], list(rows)[1:])
                  if rows[a][0].color != rows[b][0].color)
    if changes and JOINED_LINE in text:
        out.append(Tip(
            "Neat colour changes",
            f"This {piece} changes colour {_times(changes)}, always "
            f"at the join. Work the joining sl st with the new "
            f"colour, and carry the colour you are resting loosely "
            f"{'up the inside of the join' if wall else 'on the wrong side at the join'}: a "
            f"tight carry puckers the fabric at the join, a loose one disappears.",
            f"{changes} colour changes between consecutive {round_word}s"))

    # 6. joined rounds leave a line of joins.
    if JOINED_LINE in text:
        out.append(Tip(
            "The line of joins",
            f"Joined {round_word}s leave a faint line where each {round_word} starts and "
            f"ends. That is expected. Keep the joining sl st snug but not tight, and "
            + (f"turn the {piece} so the line sits at the back." if wall else
               "it shows least on the wrong side, so let that side face down."),
            "the pattern joins every round (cir.writer.JOINED_LINE)"))

    # 7. gauge, read against this pattern's own figures.
    if cir.gauge:
        out.append(Tip(
            "If your piece comes out the wrong size",
            f"Size comes from gauge: {cir.gauge.stitches_per_10cm:g} sts to 10 cm in {stitch} "
            f"with the {cir.gauge.hook_mm:g} mm hook. Bigger than 'Checking your progress' "
            f"says means your stitches are looser than gauge — try a hook one size smaller. "
            f"Smaller means tighter — try one size larger. The stitch counts never change.",
            "cir.gauge"))

    # 8. a set of several identical pieces.
    if comp.make > 1:
        out.append(Tip(
            "Making a matching set",
            f"This pattern makes {comp.make} {piece}s. Work them all from the same balls, with "
            f"the same hook, and if you can in one or two sittings, so your tension — and so "
            f"the size — matches across the set. The yarn amounts under Materials are for "
            f"all {comp.make}.",
            f"Component.make = {comp.make}"))
    return out
