"""ENG-GARMENT: one garment pattern for every size, smallest first, others in parentheses.

A size is the same steps as every other size (`products.garment_families.step_signature`),
so the document is written step by step across sizes: each instruction is one line, every
number that differs between sizes is printed `smallest (next, next, ...)`, and every line ends
with the stitch count(s) after its rows, for every size. Nothing here computes a count: the
numbers are the recorded steps of each size's own build, and `gates.garment_fit` reads this
text back -- with its own grammar, sharing nothing with this module -- expands it per size and
compares every row's count with what the compiler counted for that size.

US and UK editions differ only in stitch tokens (`publish.abbreviations.token`, which
delegates to `cir.stitches.UK_TERMS`): the same document, the same numbers.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from ..products import garment_families as GF
from . import abbreviations

PIECE_TITLES = {
    "yoke_and_body": "Yoke and body", "sleeve_left": "Left sleeve",
    "sleeve_right": "Right sleeve", "band_left": "Left front band",
    "band_right": "Right front band (buttonhole band)", "body": "Body",
    "cuff": "Cuffs (make 2)", "neckband": "Neckband", "sleeve": "Sleeves (make 2)",
    "back": "Back", "front": "Front",
}
PIECE_KEYS = {v: k for k, v in PIECE_TITLES.items()}
LOOP_WORDS = {"back": " through the back loop", "front": " through the front loop",
              "both": ""}


@dataclass(frozen=True)
class Line:
    piece: str
    kind: str
    text: str


def values(xs) -> str:
    """`a` when every size agrees, else `a (b, c, ...)`, smallest size first."""
    xs = [str(x) for x in xs]
    if len(set(xs)) == 1:
        return xs[0]
    return f"{xs[0]} ({', '.join(xs[1:])})"


def _rows(steps) -> str:
    firsts = [s.first for s in steps]
    lasts = [s.last for s in steps]
    if firsts == lasts:
        return f"Row {values(firsts)}"
    return f"Rows {values([f'{a}-{b}' if a != b else str(a) for a, b in zip(firsts, lasts)])}"


def _sts(xs) -> str:
    return f"({values(xs)} sts)"


class Terms:
    def __init__(self, terminology: str):
        self.t = terminology.upper()

    def __getattr__(self, code):
        return abbreviations.token(code, self.t)

    @property
    def skip(self) -> str:
        return abbreviations.token("sk", self.t)


def _loop(steps, k: int) -> str:
    """The loop the rows of step k are worked in, for the text (same for every size)."""
    loop = steps[0].loop
    if loop == "fabric":
        return ""
    return LOOP_WORDS.get(loop, "")


def piece_lines(sizes_steps: list[list], *, piece: str, cirs: list, t: Terms) -> list[Line]:
    """Every instruction line of one piece, across sizes (each list is one size's steps)."""
    out: list[Line] = []
    n_steps = len(sizes_steps[0])
    sc = t.sc
    fam_loops = [GF.facts_of(c) for c in cirs]
    for k in range(n_steps):
        steps = [ss[k] for ss in sizes_steps]
        s0 = steps[0]
        kind = s0.kind
        lp = _loop(steps, k)
        label = s0.label.split(":")[0]
        head = f"{_rows(steps)}" + (f" ({label})" if label and kind not in ("cast_on",) else "")
        if kind == "cast_on":
            text = f"{t.ch.capitalize()} {values([s.get('sts') + 1 for s in steps])}."
        elif kind == "pick_up":
            text = (f"Pick up {values([s.get('sts') for s in steps])} sts evenly along the edge "
                    f"(see Finishing for where and the pick-up rate).")
        elif kind == "resume":
            text = (f"Rejoin the yarn to the {values([s.get('sts') for s in steps])} held "
                    f"sts of the {PIECE_TITLES.get(s0.label, s0.label).lower()}.")
        elif kind == "even":
            first_into_chain = steps[0].first == 1 and sizes_steps[0][0].kind == "cast_on"
            if first_into_chain and all(s.first == s.last == 1 for s in steps):
                text = (f"{head}: {sc} in 2nd {t.ch} from hook and in each {t.ch} across. "
                        f"{_sts([s.count for s in steps])}")
            elif first_into_chain:
                text = (f"{head}: {sc} in 2nd {t.ch} from hook and in each {t.ch} across "
                        f"on the first row; on every other row, {t.ch} 1, turn, {sc}{lp} in "
                        f"each st across. {_sts([s.count for s in steps])}")
            else:
                text = (f"{head}: {t.ch} 1, turn, {sc}{lp} in each st across. "
                        f"{_sts([s.count for s in steps])}")
        elif kind == "even_edge_rib":
            text = (f"{head}: {t.ch} 1, turn, {sc} through the back loop in the "
                    f"{values([s.get('rib') for s in steps])} sts at the hem edge and in both "
                    f"loops in every other st (the hem edge is at the start of one row and the "
                    f"end of the next). {_sts([s.count for s in steps])}")
            if steps[0].first == 1:
                text = (f"{head}: {sc} in 2nd {t.ch} from hook and in each {t.ch} across on "
                        f"the first row; then {t.ch} 1, turn, {sc} through the back loop in "
                        f"the {values([s.get('rib') for s in steps])} sts at the hem edge and "
                        f"in both loops in every other st (the hem edge is at the start of one "
                        f"row and the end of the next). {_sts([s.count for s in steps])}")
        elif kind in ("inc", "dec"):
            code = t.inc if kind == "inc" else t.dec
            word = "increase" if kind == "inc" else "decrease"
            text = (f"{head}: {word} 1 st at each end ({code} in the first and last st) of the "
                    f"first row and of every {values([s.get('every') for s in steps])} row(s) "
                    f"after it, {values([s.get('times') for s in steps])} times in all; work "
                    f"the rows between as {t.ch} 1, turn, {sc}{lp} in each st across. "
                    f"{_sts([s.count for s in steps])}")
        elif kind == "chain_on":
            ext = [s.get("extra") for s in steps]
            text = (f"{head}: {t.ch} 1, turn, {sc} in each st across, then {t.ch} "
                    f"{values(ext)} loosely; on the second row work a {sc} into each "
                    f"{t.ch} as well before the {t.ch} {values(ext)}. "
                    f"({values([s.count - s.get('extra') for s in steps])} sts, then "
                    f"{values([s.count for s in steps])} sts)")
        elif kind == "leave":
            lv = [s.get("leave") for s in steps]
            text = (f"{head}: {t.ch} 1, turn, {sc} in each st to the last {values(lv)} sts and "
                    f"leave them unworked; work the second row the same. "
                    f"({values([s.count + s.get('leave') for s in steps])} sts, then "
                    f"{values([s.count for s in steps])} sts)")
        elif kind == "neck_bridge":
            side = [s.get("side") for s in steps]
            neck = [s.get("neck") for s in steps]
            text = (f"{head}: {t.ch} 1, turn, {sc} {values(side)}, {t.ch} {values(neck)} "
                    f"loosely, {t.skip} {values(neck)} sts, {sc} {values(side)}. "
                    f"{_sts([s.count for s in steps])}")
        elif kind == "raglan":
            doubles = [s.get("doubles") for s in steps]
            lead = (f"work {values(doubles)} double raglan increase row(s) (16 sts increased "
                    f"each), then " if any(doubles) else "work ")
            text = (f"{head}: {lead}a raglan increase row "
                    f"(8 sts increased) on the next row and on every "
                    f"{values([s.get('every') for s in steps])} row(s) after it, "
                    f"{values([s.get('singles') for s in steps])} times in all; work the rows "
                    f"between as {t.ch} 1, turn, {sc} in each st across, slipping the markers. "
                    f"{_sts([s.count for s in steps])}")
        elif kind == "divide":
            f = [s.get("front") for s in steps]
            sl = [s.get("sleeve") for s in steps]
            b = [s.get("back") for s in steps]
            text = (f"{head}: {t.ch} 1, turn, {sc} {values(f)} (front), {t.skip} {values(sl)} "
                    f"sleeve sts and leave them on hold, {sc} {values(b)} (back), {t.skip} "
                    f"{values(sl)} sleeve sts and leave them on hold, {sc} {values(f)} (front). "
                    f"{_sts([s.count for s in steps])}")
        elif kind == "buttonholes":
            text = (f"{head}: {t.ch} 1, turn, {sc} through the back loop in the first "
                    f"{values([s.get('first') for s in steps])} sts, [{t.ch} 2, {t.skip} 2 sts, "
                    f"{sc} through the back loop in the next "
                    f"{values([s.get('between') for s in steps])} sts] "
                    f"{values([s.get('holes') - 1 for s in steps])} times, {t.ch} 2, {t.skip} "
                    f"2 sts, {sc} through the back loop in the last "
                    f"{values([s.get('last') for s in steps])} sts. "
                    f"{_sts([s.count for s in steps])}")
        else:
            raise ValueError(f"no wording for step kind {kind!r}")
        out.append(Line(piece, kind, text))
    del fam_loops
    return out


def setup_row_text(steps_by_size: list, t: Terms) -> str | None:
    """A raglan's set-up row places four markers: front, sleeve, back, sleeve, front."""
    rag = [next((s for s in ss if s.kind == "raglan"), None) for ss in steps_by_size]
    if any(r is None for r in rag):
        return None
    f = [r.get("f0") for r in rag]
    s = [r.get("s0") for r in rag]
    b = [r.get("b0") for r in rag]
    sc = t.sc
    return (f"Set-up: on Row 1, place markers as you go: {sc} {values(f)} (front), pm, "
            f"{sc} {values(s)} (sleeve), pm, {sc} {values(b)} (back), pm, {sc} {values(s)} "
            f"(sleeve), pm, {sc} {values(f)} (front). The raglan increases are worked either "
            f"side of each marker.")


def write(design, cirs: dict, terminology: str = "US") -> dict[str, list[Line]]:
    """{piece title: lines} for every piece, in the order the pieces are worked."""
    t = Terms(terminology)
    order = list(cirs)
    facts = [GF.facts_of(cirs[s]) for s in order]
    sigs = {GF.step_signature(cirs[s]) for s in order}
    if len(sigs) != 1:
        raise ValueError("the sizes are not one design: their steps differ")
    out: dict[str, list[Line]] = {}
    for piece in facts[0].pieces:
        steps = [f.pieces[piece] for f in facts]
        lines = piece_lines(steps, piece=piece, cirs=[cirs[s] for s in order], t=t)
        setup = setup_row_text(steps, t) if piece == "yoke_and_body" else None
        if setup:
            lines.insert(1, Line(piece, "note", setup))
        title = PIECE_TITLES.get(piece, piece.replace("_", " ").title())
        if piece == "band_right" and not any(ss.kind == "buttonholes" for ss in steps[0]):
            title = "Right front band"
        out[title] = lines
    return out


def rate(stitches: int, rows: int) -> str:
    """A pick-up rate as the nearest small fraction: "about 3 sts for every 4 rows"."""
    if rows <= 0:
        return f"{stitches} sts"
    f = Fraction(stitches, rows).limit_denominator(6)
    return f"about {f.numerator} sts for every {f.denominator} rows"


def finishing_lines(design, cirs: dict, terminology: str = "US") -> list[str]:
    """Seams, bands, buttonholes and pick-ups, with every count from the build."""
    t = Terms(terminology)
    order = list(cirs)
    facts = [GF.facts_of(cirs[s]) for s in order]
    cir0 = cirs[order[0]]
    out: list[str] = []
    for i, seam in enumerate(cir0.assembly, start=1):
        pick = [next((p for p in f.pickups if p["piece"] == seam.piece_a), None)
                for f in facts]
        if seam.method == "pick_up" and all(pick):
            sts = [p["stitches"] for p in pick]
            along = [p["rows_along"] for p in pick]
            where = {"band_left": "the left front edge, from the hem to the neck",
                     "band_right": "the right front edge, from the neck to the hem",
                     "cuff": "the end of each sleeve, across the rows of the sleeve",
                     "neckband": "the neck opening, all the way round"}.get(seam.piece_a,
                                                                           "the edge")
            rates = ([rate(s, r) for s, r in zip(sts, along)] if all(along) else None)
            name = PIECE_TITLES.get(seam.piece_a, seam.piece_a)
            if seam.piece_a == "band_right" and not any(f.buttons for f in facts):
                name = "Right front band"
            out.append(f"{i}. {name}: with the right "
                       f"side facing, join the yarn and pick up {values(sts)} sts evenly "
                       f"along {where}"
                       + (f" ({values(rates)})" if rates else
                          f" ({values([round(p['edge_cm'], 1) for p in pick])} cm)")
                       + f", then work the rows given above for it.")
            continue
        note = (seam.note or "").rstrip(".")
        verb = {"mattress": "Mattress-stitch", "whipstitch": "Whipstitch",
                "slst": f"Slip-stitch ({t.slst})"}.get(seam.method, "Join")
        out.append(f"{i}. {verb}: {note}.")
    n_buttons = [f.buttons for f in facts]
    if any(n_buttons):
        out.append(f"{len(cir0.assembly) + 1}. Buttons: sew {values(n_buttons)} buttons "
                   f"({GF.BUTTON_MM} mm) to the left front band opposite the buttonholes, "
                   f"through both loops of the band with a doubled strand, and fasten off "
                   f"securely on the wrong side.")
    out.append(f"{len(out) + 1}. Weave in every end through at least 5 cm of stitches, and "
               f"block the garment flat to the finished measurements in the size chart.")
    return out
