"""ENG-GARMENT-2: one wearable pattern for every size, smallest first, others in parentheses.

Flat pieces are written by `publish.garment_writer.piece_lines` (the same grammar the garment
gates read back); pieces worked in joined rounds are written here, in a round grammar that
`gates.wearable_fit.read_round_line` reads back -- its own regexes, sharing nothing with this
module -- and expands per size against the compiler. Nothing here computes a count: every
number is a recorded step of that size's own build.
"""
from __future__ import annotations

from . import garment_writer as GW
from .garment_writer import Line, Terms, values

PIECE_TITLES = {
    "brim": "Brim", "crown": "Body and crown",
}


def _rnds(steps) -> str:
    firsts = [s.first for s in steps]
    lasts = [s.last for s in steps]
    if firsts == lasts:
        return f"Rnd {values(firsts)}"
    return f"Rnds {values([f'{a}-{b}' if a != b else str(a) for a, b in zip(firsts, lasts)])}"


def _sts(xs) -> str:
    return f"({values(xs)} sts)"


def round_lines(sizes_steps: list[list], *, piece: str, t: Terms) -> list[Line]:
    out: list[Line] = []
    sc = t.sc
    for k in range(len(sizes_steps[0])):
        steps = [ss[k] for ss in sizes_steps]
        s0 = steps[0]
        kind, label = s0.kind, s0.label.split(":")[0]
        head = _rnds(steps) + (f" ({label})" if label else "")
        counts = _sts([s.count for s in steps])
        if kind == "pick_up":
            text = (f"Pick up {values([s.get('sts') for s in steps])} sts evenly along the edge "
                    f"(see Finishing for where and the pick-up rate), and join with a "
                    f"{t.slst} to the first st.")
        elif kind == "magic_ring":
            text = (f"{head}: make a magic ring and work "
                    f"{values([s.get('sts') for s in steps])} {sc} into it; join with a "
                    f"{t.slst} to the first st. {counts}")
        elif kind == "resume":
            text = (f"Rejoin the yarn to the {values([s.get('sts') for s in steps])} held "
                    f"sts.")
        elif kind == "even":
            lp = GW.LOOP_WORDS.get(s0.loop, "")
            text = (f"{head}: {t.ch} 1, {sc}{lp} in each st around; join with a {t.slst} to "
                    f"the first st. {counts}")
        elif kind == "opening":
            half = values([s.get("worked") for s in steps])
            bridge = values([s.get("bridge") for s in steps])
            text = (f"{head}: {t.ch} 1, {sc} in the first {half} sts, {t.ch} {bridge} "
                    f"loosely, {t.skip} the last {bridge} sts; join with a {t.slst} to the "
                    f"first st. {counts}")
        elif kind == "spread_dec":
            d = values([s.get("dec") for s in steps])
            text = (f"{head}: {t.ch} 1, {sc} around, decreasing {d} sts evenly spaced "
                    f"({t.dec} {d} times); join with a {t.slst} to the first st. {counts}")
        elif kind == "spread_inc":
            d = values([s.get("inc") for s in steps])
            text = (f"{head}: {t.ch} 1, {sc} around, increasing {d} sts evenly spaced "
                    f"({t.inc} {d} times); join with a {t.slst} to the first st. {counts}")
        elif kind in ("section_dec", "section_inc"):
            n = values([s.get("sections") for s in steps])
            if kind == "section_dec":
                text = (f"{head}: on every round, {t.ch} 1, *{sc} to the last 2 sts of the "
                        f"section, {t.dec}; repeat from * in {n} equal sections round, so "
                        f"each round has 1 st fewer in every section; join with a {t.slst} "
                        f"to the first st. {counts}")
            else:
                text = (f"{head}: on every round, {t.ch} 1, *{sc} to the last st of the "
                        f"section, {t.inc}; repeat from * in {n} equal sections round, so "
                        f"each round has 1 st more in every section; join with a {t.slst} "
                        f"to the first st. {counts}")
        else:
            raise ValueError(f"no round wording for step kind {kind!r}")
        out.append(Line(piece, kind, text))
    return out


FLAT_KINDS = ("split", "vraglan")


def flat_lines(sizes_steps: list[list], *, piece: str, cirs: list, t: Terms) -> list[Line]:
    """Flat pieces in the garment grammar, plus the wearable flat kinds (`FLAT_KINDS`)."""
    import dataclasses

    stand_in = [[dataclasses.replace(s, kind="even") if s.kind in FLAT_KINDS else s
                 for s in ss] for ss in sizes_steps]
    lines = GW.piece_lines(stand_in, piece=piece, cirs=cirs, t=t)
    out = []
    for k, ln in enumerate(lines):
        steps = [ss[k] for ss in sizes_steps]
        if steps[0].kind == "split":
            keep = values([s.get("keep") for s in steps])
            hold = values([s.get("hold") for s in steps])
            head = GW._rows(steps) + (f" ({steps[0].label})" if steps[0].label else "")
            ln = Line(piece, "split",
                      f"{head}: {t.ch} 1, turn, {t.sc} in the first {keep} sts only, "
                      f"leaving the rest of the row: the last {hold} sts are held for the "
                      f"second shoulder and the centre sts are the neck edge. "
                      f"{_sts([s.count for s in steps])}")
        elif steps[0].kind == "vraglan":
            head = GW._rows(steps) + (f" ({steps[0].label})" if steps[0].label else "")
            v = lambda key: values([s.get(key) for s in steps])  # noqa: E731
            ln = Line(piece, "vraglan",
                      f"{head}: work {v('doubles')} double raglan increase row(s) (16 sts "
                      f"increased each), then a raglan increase row (8 sts increased) on the "
                      f"next row and on every {v('every')} row(s) after it, {v('singles')} "
                      f"times in all; at the same time, increase 1 st at each neck edge "
                      f"({t.inc} in the first and last st) on the first row and on every "
                      f"{v('neck_every')} row(s) after it, {v('neck')} times in all; work "
                      f"every other row as {t.ch} 1, turn, {t.sc} in each st across, slipping "
                      f"the markers. {_sts([s.count for s in steps])}")
        out.append(ln)
    rag = [next((s for s in ss if s.kind == "vraglan"), None) for ss in sizes_steps]
    if all(rag):
        v = lambda key: values([r.get(key) for r in rag])  # noqa: E731
        sc = t.sc
        out.insert(2, Line(piece, "note",
                           f"Set-up: on Row 1, place markers as you go: {sc} {v('f0')} "
                           f"(front), pm, {sc} {v('s0')} (sleeve), pm, {sc} {v('b0')} (back), "
                           f"pm, {sc} {v('s0')} (sleeve), pm, {sc} {v('f0')} (front). The "
                           f"raglan increases are worked either side of each marker."))
    return out


def write(design, cirs: dict, terminology: str = "US", titles: dict | None = None
          ) -> dict[str, list[Line]]:
    """{piece title: lines} for every piece, in the order the pieces are worked."""
    from ..products import wearables as WB

    t = Terms(terminology)
    order = list(cirs)
    facts = [WB.facts_of(cirs[s]) for s in order]
    if len({WB.step_signature(cirs[s]) for s in order}) != 1:
        raise ValueError("the sizes are not one design: their steps differ")
    names = {**GW.PIECE_TITLES, **PIECE_TITLES, **(titles or {})}
    out: dict[str, list[Line]] = {}
    for piece in facts[0].pieces:
        steps = [f.pieces[piece] for f in facts]
        if piece in facts[0].rounds:
            lines = round_lines(steps, piece=piece, t=t)
        else:
            lines = flat_lines(steps, piece=piece, cirs=[cirs[s] for s in order], t=t)
        out[names.get(piece, piece.replace("_", " ").capitalize())] = lines
    return out


def finishing_lines(design, cirs: dict, terminology: str = "US", *,
                    where: dict | None = None, closing: str | None = None,
                    titles: dict | None = None) -> list[str]:
    """Seams and pick-ups in working order, every count from the build."""
    from ..products import wearables as WB

    t = Terms(terminology)
    order = list(cirs)
    facts = [WB.facts_of(cirs[s]) for s in order]
    cir0 = cirs[order[0]]
    names = {**GW.PIECE_TITLES, **PIECE_TITLES, **(titles or {})}
    out: list[str] = []
    for seam in cir0.assembly:
        pick = [next((p for p in f.pickups if p["piece"] == seam.piece_a), None)
                for f in facts]
        i = len(out) + 1
        if seam.method == "pick_up" and all(pick):
            sts = [p["stitches"] for p in pick]
            along = [p.get("rows_along") or 0 for p in pick]
            rates = [GW.rate(s, r) for s, r in zip(sts, along)] if all(along) else None
            at = (where or {}).get(seam.piece_a, "the edge")
            out.append(f"{i}. {names.get(seam.piece_a, seam.piece_a)}: with the right side "
                       f"facing, join the yarn and pick up {values(sts)} sts evenly along "
                       f"{at}" + (f" ({values(rates)})" if rates else "")
                       + ", then work the rounds or rows given above for it.")
            continue
        verb = {"mattress": "Mattress-stitch", "whipstitch": "Whipstitch",
                "slst": f"Slip-stitch ({t.slst})"}.get(seam.method, "Join")
        out.append(f"{i}. {verb}: {(seam.note or '').rstrip('.')}.")
    if closing:
        out.append(f"{len(out) + 1}. {closing}")
    out.append(f"{len(out) + 1}. Weave in every end through at least 5 cm of stitches, and "
               f"block to the finished measurements in the size chart.")
    return out
