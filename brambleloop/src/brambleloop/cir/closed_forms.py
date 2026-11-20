"""ENG-PLUSH: closed stuffed pieces in rounds -- stuffing points, closures, part geometry.

An amigurumi body is a sphere-like piece: magic ring, increases, even rounds, decreases,
close. Two things about it are not stitch counts and were, until now, prose a maker had to
trust: *when* it is stuffed, and *that* it is closed. Both decide whether the object can be
made at all -- a piece stuffed after the opening has shrunk below a hand's width cannot be
stuffed firmly, and a "closed" piece whose last round is 18 stitches is an open bag of
fibrefill.

`Component.stuff_at_round` and `Component.closes` state them as structure, and this module
checks them against the compiled rounds and the surface geometry `cir.geometry.measure`
computes (the same geometry the digital twin carries), so the compiler, the twin and the
writer read one definition:

  STUFFING_POINT_UNKNOWN_ROUND  the stuffing round is not a round of the piece
  STUFFING_POINT_TOO_EARLY      stuffed before the widest round: the piece is still growing
  STUFFING_OPENING_TOO_SMALL    the opening at the stuffing round is under STUFF_OPENING_MIN_STS
  STUFFING_AFTER_CLOSE          stuffed on the last round of a piece that closes
  CLOSED_FORM_OPEN              `closes` but the last round is larger than CLOSEABLE_STITCHES
  CLOSED_FORM_UNSTUFFED         a closed piece with no stuffing point (an empty ball)
  CLOSED_FORM_NOT_ROUNDS        a closure or stuffing point on a piece worked in flat rows
  PART_GEOMETRY_GATHERED        a round grows faster than its height allows (it ruffles)
  PART_GEOMETRY_TOO_SHALLOW     the meridian is shorter than the widest diameter: the piece
                                cannot enclose stuffing, it is a folded disc
  PART_GEOMETRY_NO_GAUGE        no gauge: the geometry cannot be checked (UNKNOWN, ERROR)

Every finding is an ERROR: a closed form that cannot be stuffed or closed is not a pattern.
"""
from __future__ import annotations

from .model import CIR

STUFF_OPENING_MIN_STS = 12          # about 3 cm across at worsted: two fingers and fibrefill
SHALLOW_RATIO = 1.0                 # meridian arc / widest diameter below this cannot enclose


def _finding(code: str, message: str, where: str):
    from .compiler import ERROR, Finding

    return Finding(ERROR, code, message, where)


def check(cir: CIR, result, findings: list) -> None:
    """Append a finding for every stuffing point, closure or closed geometry that fails."""
    from . import geometry

    for comp in cir.components:
        if comp.stuff_at_round is None and not comp.closes:
            continue
        name = comp.name
        if comp.construction == "flat_rows":
            findings.append(_finding("CLOSED_FORM_NOT_ROUNDS",
                                     "a stuffing point or closure is stated on a piece worked "
                                     "in flat rows; only a piece in rounds closes", name))
            continue
        rows = [r for r in result.rows if r.component == name]
        if not rows:
            continue
        counts = {r.index: r.stitch_count for r in rows}
        last = rows[-1]
        widest_index = max(rows, key=lambda r: (r.stitch_count, -r.index)).index
        if comp.closes and last.stitch_count > geometry.CLOSEABLE_STITCHES:
            findings.append(_finding(
                "CLOSED_FORM_OPEN",
                f"the piece is stated to close, but its last round {last.index} has "
                f"{last.stitch_count} sts; a gathered closure needs "
                f"{geometry.CLOSEABLE_STITCHES} or fewer", name))
        if comp.closes and comp.stuff_at_round is None:
            findings.append(_finding(
                "CLOSED_FORM_UNSTUFFED",
                "the piece closes but states no stuffing point: it would be closed empty, or "
                "stuffed through a hole that is no longer there", name))
        at = comp.stuff_at_round
        if at is not None:
            if at not in counts:
                findings.append(_finding(
                    "STUFFING_POINT_UNKNOWN_ROUND",
                    f"stuffing is stated after round {at}, which the piece does not have "
                    f"(rounds {rows[0].index}-{last.index})", name))
            else:
                if at < widest_index:
                    findings.append(_finding(
                        "STUFFING_POINT_TOO_EARLY",
                        f"stuffed after round {at}, before the widest round {widest_index}: "
                        f"the piece is still growing and the stuffing would fall out", name))
                if counts[at] < STUFF_OPENING_MIN_STS:
                    findings.append(_finding(
                        "STUFFING_OPENING_TOO_SMALL",
                        f"the opening after round {at} is {counts[at]} sts, under the "
                        f"{STUFF_OPENING_MIN_STS} sts a piece can be stuffed firmly through",
                        name))
                if comp.closes and at == last.index:
                    findings.append(_finding(
                        "STUFFING_AFTER_CLOSE",
                        f"stuffed after round {at}, the closing round", name))
        if cir.gauge is None:
            findings.append(_finding("PART_GEOMETRY_NO_GAUGE",
                                     "no gauge, so the closed piece's geometry cannot be "
                                     "checked (UNKNOWN is not a pass)", name))
            continue
        rev = geometry.measure(comp, result, cir)
        if any(r.growth_ratio > geometry.SMOOTH_TOLERANCE for r in rev.rings[1:]):
            bad = [r.index for r in rev.rings[1:] if r.growth_ratio > geometry.SMOOTH_TOLERANCE]
            findings.append(_finding(
                "PART_GEOMETRY_GATHERED",
                f"rounds {bad} grow faster than their own height allows; the piece would "
                f"ruffle rather than curve", name))
        if comp.closes and rev.rings:
            arc = rev.rings[-1].arc_cm
            if arc < SHALLOW_RATIO * rev.max_diameter_cm:
                findings.append(_finding(
                    "PART_GEOMETRY_TOO_SHALLOW",
                    f"the piece is {arc:.1f} cm from ring to closure along its surface but "
                    f"{rev.max_diameter_cm:.1f} cm across: it cannot enclose stuffing", name))


def part_geometry(cir: CIR, result) -> list[dict]:
    """Per piece: rounds, widest count and circumference, and for a closed piece the meridian.

    Read by the PDF's part diagram and by the child-safety gate; computed from the same
    `geometry.measure` the twin carries, so no surface states a number the twin does not."""
    from . import geometry

    out = []
    for comp in cir.components:
        rows = [r for r in result.rows if r.component == comp.name]
        if not rows:
            continue
        entry = {"piece": comp.name, "make": comp.make, "construction": comp.construction,
                 "rounds": len(rows), "counts": [r.stitch_count for r in rows],
                 "widest_sts": max(r.stitch_count for r in rows),
                 "stuff_at_round": comp.stuff_at_round, "closes": comp.closes}
        if cir.gauge is not None and comp.construction != "flat_rows":
            rev = geometry.measure(comp, result, cir)
            entry.update(circumference_cm=round(rev.max_circumference_cm, 1),
                         diameter_cm=round(rev.max_diameter_cm, 1),
                         meridian_cm=round(rev.rings[-1].arc_cm, 1) if rev.rings else None,
                         shape=rev.shape)
        out.append(entry)
    return out
