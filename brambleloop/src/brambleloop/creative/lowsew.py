"""ENG-LOWSEW-CHENILLE: low-sew chunky chenille animals, drafted as join-as-you-go CIRs.

The technique class (D-OWNER-CORE-FAMILIES, teardown L2/L3): limbs, ears, tails and trunks are
worked as tubes, flattened and closed with a stated number of sc through both layers, and
then crocheted INTO a named round of the body or head at explicit stitch positions; a head is
joined to the body by working its last round through the body's open last round. No piece is
sewn on. The yarn is a first-class chenille class (`cir.yarn_classes`), so the gauge, hook
range, sizes and yardage are this yarn's.

Everything here is Brambleloop's own: the animals, their names, their proportions, the round
sequences and the wording. Nothing is taken from a benchmark -- the benchmarks taught the
technique class and the defects to avoid (no gauge, no hook range, no eye options).

`LAYOUT` places each joined piece by a mirror line (a fraction of the round, the animal's
front-to-back line) so every pair is mirrored about one line and a single piece -- a tail, a
trunk -- is centred on it. `cir.joins` then proves the counts, positions and symmetry from
the compiled rounds; the builder is never trusted for them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..cir.model import CIR, Component, Material, Op, Repeat, Row
from ..cir import yarn_classes

LOWSEW = "lowsew_chenille"
PRIMITIVES = ("creative.lowsew.draft", "cir.joins.check", "cir.yarn_classes.CHENILLE_6",
              "products.moment_candidates._disc", "products.moment_candidates._decrease_to",
              "cir.closed_forms.check")


@dataclass(frozen=True)
class Piece:
    """A tube from a magic ring, increased to `around`, worked `plain` rounds and either
    fold-closed (an appendage), gathered shut, or left open (a body the head joins)."""

    name: str
    colour: str
    around: int
    plain: int
    make: int = 1
    wedges: int = 6
    end: str = "fold"                # fold | close | open | join_head
    decrease_to: int | None = None   # for a body or head: the neck / closing count
    stuffed: bool = False
    colour_from: tuple[tuple[int, str], ...] = ()   # (from round, colour) changes
    note: str = ""


@dataclass(frozen=True)
class Joined:
    """`piece` crocheted into round `round` of `host`, as a pair or a single centred piece."""

    host: str
    round: int
    piece: str
    width: int
    gap: int | None = None           # stitches between a pair; None = one centred piece
    back: bool = False               # centred on the far end of the mirror line


@dataclass(frozen=True)
class Animal:
    slug: str
    title: str
    kind: str
    colours: dict
    pieces: tuple[Piece, ...]
    joins: tuple[Joined, ...]
    line: dict                       # host -> 0-based stitch the mirror line passes through
    drift: dict                      # host -> drift allowance in sts
    eyes: tuple[str, int, int]       # piece, round, sts apart
    eye_yarn: str
    story: str
    extra_notes: dict = field(default_factory=dict)


def _tube(p: Piece) -> list[Row]:
    from ..products.moment_candidates import _decrease_to, _disc, _Rows

    rows = _Rows()

    def colour_at(index: int) -> str:
        c = p.colour
        for start, col in p.colour_from:
            if index >= start:
                c = col
        return c

    _disc(rows, p.around, p.colour, wedges=p.wedges)
    for _ in range(p.plain):
        rows.add([Op("sc", p.around)], p.around, p.colour)
    if p.decrease_to is not None:
        _decrease_to(rows, p.around, p.decrease_to, p.colour, wedges=p.wedges)
    for r in rows.rows:
        r.color = colour_at(r.index)
    if p.end == "fold":
        width = rows.rows[-1].declared_count // 2
        rows.rows.append(Row(index=rows.next, ops=[Op("sc", width)], declared_count=width,
                             color=colour_at(rows.next), fold=True,
                             note="leave a short tail and weave it into the closed edge"))
    return rows.rows


def _place(count: int, line: float, joins: list) -> list[tuple[int, str, int]]:
    """(0-based start, piece, width) for every run, mirrored about stitch `line` (or about
    its far end, half a round away, for a piece at the back)."""
    out = []
    for j in joins:
        centre = line + count / 2.0 if j.back else line
        if j.gap is None:
            start = centre - (j.width - 1) / 2.0
            out.append((int(round(start)) % count, j.piece, j.width))
        else:
            first = int(round(centre - (2 * j.width + j.gap - 1) / 2.0)) % count
            out.append((first, j.piece, j.width))
            out.append((first + j.width + j.gap, j.piece, j.width))
    return sorted(out)


def _joined_round(count: int, runs: list[tuple[int, str, int]], colour: str,
                  index: int) -> Row:
    ops: list = []
    pos = 0
    for start, piece, width in runs:
        if start < pos or start + width > count:
            raise ValueError(f"round {index}: the {piece} at st {start + 1} overlaps or wraps "
                             f"the start of the round")
        if start > pos:
            ops.append(Op("sc", start - pos))
        ops.append(Op("sc", width, through=piece))
        pos = start + width
    if pos < count:
        ops.append(Op("sc", count - pos))
    return Row(index=index, ops=ops, declared_count=count, color=colour)


def draft(animal: Animal, *, version: str = "1.0.0", provenance=None,
          yarn: yarn_classes.YarnClass = yarn_classes.CHENILLE_6) -> CIR:
    gauge = yarn.gauge()
    by_name = {p.name: p for p in animal.pieces}
    rows_by_piece = {p.name: _tube(p) for p in animal.pieces}
    # Joined rounds: replace the host's plain round with one worked through each piece.
    hosts: dict[tuple[str, int], list] = {}
    for j in animal.joins:
        hosts.setdefault((j.host, j.round), []).append(j)
    for (host, index), js in hosts.items():
        rows = rows_by_piece[host]
        row = next(r for r in rows if r.index == index)
        if not (len(row.ops) == 1 and isinstance(row.ops[0], Op) and row.ops[0].stitch == "sc"):
            raise ValueError(f"{host} round {index} is not a plain round to join into")
        count = row.declared_count
        runs = _place(count, animal.line[host], js)
        new = _joined_round(count, runs, row.color, index)
        rows[rows.index(row)] = new
    # The head's last round is worked through the body's open last round.
    for p in animal.pieces:
        if p.end == "join_head":
            rows = rows_by_piece[p.name]
            body = next(q for q in animal.pieces if q.end == "open")
            width = rows_by_piece[body.name][-1].declared_count
            if rows[-1].declared_count != width:
                raise ValueError(f"the {p.name} ends on {rows[-1].declared_count} sts and the "
                                 f"{body.name} on {width}: they cannot be joined stitch for "
                                 f"stitch")
            rows.append(Row(index=rows[-1].index + 1,
                            ops=[Op("sc", width, through=body.name)],
                            declared_count=width, color=rows[-1].color,
                            note=(f"hold the {p.name} on the {body.name}, face to the front, "
                                  f"and work each stitch through both pieces")))
    components = []
    eye_piece, eye_round, eye_gap = animal.eyes
    # The principal piece (the body) is printed first: the document, the twin's headline
    # size and the PDF read the first piece as the object. Pieces crocheted into it are
    # printed after it under a "Make first" line (`cir.joins.make_first`).
    principal = [p for p in animal.pieces if p.end in ("open", "close")]
    heads = [p for p in animal.pieces if p.end == "join_head"]
    rest = [p for p in animal.pieces if p not in principal and p not in heads]
    for p in principal + heads + rest:
        rows = rows_by_piece[p.name]
        stuff_at = None
        if p.stuffed:
            last_open = rows[-2].index if p.end == "join_head" else rows[-1].index
            stuff_at = rows[-2].index if p.end == "close" else last_open
        drift = animal.drift.get(p.name)
        how = {"fold": "Unstuffed: the chenille holds its shape. Fold-closed, then crocheted in",
               "close": "Worked from the base up, stuffed and gathered shut",
               "open": "Worked from the base up and stuffed; left open for the head",
               "join_head": "Worked from the top down, stuffed, then joined to the body"}[p.end]
        note = f"{how}. {p.note}".strip()
        if p.name == eye_piece:
            note += (" Embroider the eyes with yarn only, after stuffing, at the round and "
                     "spacing given.")
        components.append(Component(
            name=p.name, construction="spiral_rounds", rows=rows, foundation=0,
            foundation_kind="magic_ring", make=p.make, note=note,
            stuff_at_round=stuff_at, closes=(p.end == "close"),
            join_drift_sts=drift,
            eye_round=eye_round if p.name == eye_piece else None,
            eye_gap_sts=eye_gap if p.name == eye_piece else None))
    used = sorted({r.color for c in components for r in c.rows if r.color})
    colours = {k: v for k, v in animal.colours.items() if k in used}
    materials = [Material(name=f"{yarn.name} polyester yarn", yarn_weight=yarn.weight_key,
                          colorway=c, color_id=c, fibre_content=(("polyester", 100),))
                 for c in used]
    materials += [Material(name="new polyester fibrefill (toy stuffing)"),
                  Material(name=f"{animal.eye_yarn} worsted acrylic scrap for the embroidered "
                                f"eyes", yarn_weight="medium")]
    # Sizes from the yarn class: the widest round of the body and the head.
    widest = max(r.declared_count for c in components if c.stuff_at_round is not None
                 for r in c.rows)
    around = widest / gauge.stitches_per_10cm * 10.0
    cir = CIR(
        slug=animal.slug, title=animal.title, version=version,
        construction="spiral_rounds", risk_class="C", colors=colours, gauge=gauge,
        materials=materials, components=components, assembly=[],
        designer_notes=(f"{animal.story} Low-sew construction: every limb and ear is "
                        f"fold-closed and crocheted into a stated round at stated stitches; "
                        f"nothing is sewn on. Worked in {yarn.name} (CYC {yarn.cyc}) on a "
                        f"{gauge.hook_mm:g} mm hook, range {yarn.hook_range_words}."),
        finished_size_note=(
            f"The widest round is about {around:.0f} cm around at the stated gauge. Computed "
            f"from the stitch counts and this yarn class's design gauge, not yet measured on a "
            f"worked sample; height depends on the stuffing."),
        provenance=provenance if provenance is not None else default_provenance(animal),
    )
    return cir


def default_provenance(animal: Animal):
    """Brambleloop's own design record. No benchmark is consulted: the teardowns contributed a
    technique class (fold-and-close limbs crocheted into a body round) and defect classes,
    never a pattern text, count, chart, image, character or name."""
    import hashlib

    from ..cir.model import Provenance

    brief = f"{animal.slug}|{animal.kind}|{animal.story}"
    return Provenance(concept_key=f"lowsew:{animal.slug}",
                      brief_digest=hashlib.sha256(brief.encode()).hexdigest()[:16],
                      primitives_used=PRIMITIVES, benchmarks_consulted=(),
                      generated_by="brambleloop", at="2026-11-20T00:00:00Z")


# ---- three original animals ------------------------------------------------------------------
#
# Chosen to be unlike the benchmarks (a capybara and a highland cow): a penguin (one closed
# body, wings and feet crocheted in), a fox (a head joined to the body, ears, legs and a tail
# on the mirror line) and an elephant (a head joined to the body, wide ears, a trunk on the
# mirror line and four legs on one round).

PENGUIN = Animal(
    slug="tumble-penguin-chenille", title="Tumble the Penguin Chenille Amigurumi",
    kind="penguin",
    colours={"charcoal": "#34373D", "marigold": "#E2A23A"},
    pieces=(
        Piece("foot", "marigold", around=12, plain=2, make=2),
        Piece("wing", "charcoal", around=12, plain=4, make=2),
        Piece("body", "charcoal", around=36, plain=8, decrease_to=6, end="close",
              stuffed=True),
    ),
    joins=(Joined("body", 7, "foot", 6, gap=2), Joined("body", 12, "wing", 6, gap=12)),
    line={"body": 12.5}, drift={"body": 1}, eyes=("body", 15, 5), eye_yarn="cream",
    story="Tumble is a round, waddling penguin with marigold feet.")

FOX = Animal(
    slug="juniper-fox-chenille", title="Juniper the Fox Chenille Amigurumi",
    kind="fox",
    colours={"rust": "#B5522B", "cream": "#F0E6D4", "bark": "#4A3528"},
    pieces=(
        Piece("leg", "bark", around=12, plain=3, make=2),
        Piece("tail", "cream", around=18, plain=5, colour_from=((5, "rust"),)),
        Piece("ear", "rust", around=12, plain=2, make=2),
        Piece("body", "rust", around=30, plain=5, decrease_to=18, end="open", stuffed=True),
        Piece("head", "rust", around=30, plain=4, decrease_to=18, end="join_head",
              stuffed=True),
    ),
    joins=(Joined("body", 6, "leg", 6, gap=3), Joined("body", 8, "tail", 9, back=True),
           Joined("head", 6, "ear", 6, gap=8)),
    line={"body": 7.0, "head": 9.5}, drift={"body": 1, "head": 2},
    eyes=("head", 8, 4), eye_yarn="dark brown",
    story="Juniper is a sitting fox with a cream-tipped tail.")

ELEPHANT = Animal(
    slug="marlow-elephant-chenille", title="Marlow the Elephant Chenille Amigurumi",
    kind="elephant",
    colours={"mist": "#9AA3AD"},
    pieces=(
        Piece("front_leg", "mist", around=12, plain=3, make=2),
        Piece("back_leg", "mist", around=12, plain=3, make=2),
        Piece("ear", "mist", around=18, plain=2, make=2),
        Piece("trunk", "mist", around=12, plain=4),
        Piece("body", "mist", around=36, plain=6, decrease_to=18, end="open", stuffed=True),
        Piece("head", "mist", around=30, plain=5, decrease_to=18, end="join_head",
              stuffed=True),
    ),
    joins=(Joined("body", 7, "front_leg", 6, gap=3), Joined("body", 7, "back_leg", 6, gap=3, back=True),
           Joined("head", 7, "ear", 9, gap=6), Joined("head", 9, "trunk", 6)),
    line={"body": 7.0, "head": 11.5}, drift={"body": 1, "head": 2},
    eyes=("head", 10, 6), eye_yarn="charcoal",
    story="Marlow is a sturdy little elephant with wide ears and a short trunk.")

ANIMALS = (PENGUIN, FOX, ELEPHANT)
