"""W4-CREATIVE's moment-first candidates, engineered as pattern software (W4-PIPE2).

`creative.emotional_brief.NEW_CANDIDATES` holds eight concepts written person-and-moment
first. A concept is not a product: until a CIR exists there is nothing for the compiler, the
digital twin, the assembly check or certification to measure, and nothing a buyer could make.
This module is the engineering step for seven of them (the pencil roll is engineered in
`products.pipeline_board.pencil_roll_cir`), in `emotional_brief.gate_candidates()
['engineering_queue']` order.

Rules every builder here keeps, because they are the company's rules:

* **The CIR is the product.** Counts come from arithmetic on the declared yarn's published
  gauge band (`creative.prototype.gauge_for`), never from a picture; the compiler, reverse
  compiler, twin and certificate decide whether it is true.
* **The fabric is what this CIR can express.** One colour per row/round, with double crochet
  standing in relief on a single-crochet ground (the catalogue's own motif fabric). Per-stitch
  colourwork is not expressible (`launch0.per_stitch_colour_expressible()` is False), so no
  name or note here claims stranded or tapestry work. Where a brief named a technique the CIR
  cannot carry, the engineered design says what it does instead (see ENGINEERING_NOTES).
* **Motifs are Brambleloop's own** (`products.motifs`), built from geometry. No competitor
  pattern, chart or photograph informed any count here; `benchmarks_consulted` is empty.
* **Pre-release.** Every version is 0.x: a candidate is not a catalogue product until it
  clears Product Truth, its taste gate and an owner-governed adoption.
"""
from __future__ import annotations

import math

from ..cir.model import CIR, Component, Gauge, Hold, Material, Op, Repeat, Row, Seam
from ..gates.originality import catalogue_provenance
from .builder import _runs
from .motifs import Motif, get

VERSION = "0.1.0"
ENGINEERED_BY = "W4-PIPE2 products.moment_candidates"

FOREST, CREAM, WINE, GOLD = "#244A3A", "#FAF6EB", "#6E1F2A", "#C49545"


def _gauge(weight: str) -> Gauge:
    from ..creative.prototype import gauge_for

    return gauge_for(weight)


def _row_cm(g: Gauge) -> float:
    return 10.0 / g.rows_per_10cm


def _sts_for(cm: float, g: Gauge, multiple: int) -> int:
    """The stitch count nearest `cm` at this gauge that is a whole number of `multiple`."""
    return max(multiple, int(round(cm * g.stitches_per_10cm / 10.0 / multiple)) * multiple)


def _rounds_for(cm: float, g: Gauge, minimum: int = 1) -> int:
    return max(minimum, int(round(cm / _row_cm(g))))


class _Rows:
    """Appends rows with consecutive indices, so no builder can number two rows alike."""

    def __init__(self, start: int = 1):
        self.rows: list[Row] = []
        self.next = start

    def add(self, ops: list, count: int, colour: str, note: str | None = None,
            turning_chain: int = 0) -> Row:
        row = Row(index=self.next, ops=ops, declared_count=count, color=colour, note=note,
                  turning_chain=turning_chain)
        self.rows.append(row)
        self.next += 1
        return row

    @property
    def last(self) -> int:
        return self.next - 1


def _disc(rows: _Rows, target: int, colour: str, wedges: int = 6, *,
          stagger: bool = True) -> None:
    """Increase rounds from a magic ring to `target` stitches.

    `stagger=True` moves each round's increase to the middle of its wedge on alternate rounds,
    so the increases never stack into corners and the piece is a circle (`geometry.corners`
    reads 0 sides); stacked increases make a polygon, which a round object must not be.
    """
    if target % wedges:
        raise ValueError(f"{target} is not a whole number of {wedges} wedges")
    rows.add([Op("sc", wedges)], wedges, colour)
    count = wedges
    k = 1
    while count < target:
        k += 1
        per = count // wedges          # stitches in each wedge of the round below
        if per == 1:
            body: list = [Op("inc")]
        elif stagger and k % 2 == 0:
            before = (per - 1) // 2
            after = per - 1 - before
            body = ([Op("sc", before)] if before else []) + [Op("inc")] + (
                [Op("sc", after)] if after else [])
        else:
            body = [Op("sc", per - 1), Op("inc")]
        count += wedges
        rows.add([Repeat(body, times=wedges)], count, colour)


def _decrease_to(rows: _Rows, start: int, target: int, colour: str, wedges: int = 6) -> None:
    """Decrease rounds, one decrease per wedge per round, from `start` down to `target`."""
    count = start
    k = 0
    while count > target:
        k += 1
        per = count // wedges
        if per == 2:
            body: list = [Op("dec")]
        elif k % 2 == 0:
            before = (per - 2) // 2
            after = per - 2 - before
            body = ([Op("sc", before)] if before else []) + [Op("dec")] + (
                [Op("sc", after)] if after else [])
        else:
            body = [Op("sc", per - 2), Op("dec")]
        count -= wedges
        rows.add([Repeat(body, times=wedges)], count, colour)


def _plain(rows: _Rows, n: int, count: int, colour: str, stitch: str = "sc") -> None:
    for _ in range(n):
        rows.add([Op(stitch, count)], count, colour)


def _relief_band(rows: _Rows, motif: Motif, count: int, colours: tuple[str, str], *,
                 upside_down: bool = False, turning: int = 0) -> None:
    """One full motif repeat as relief rows/rounds: dc where the chart is 1, sc where 0.

    Colours alternate every row/round, the catalogue's own relief fabric. `upside_down`
    works the chart from its last line, so a motif with an up (a fir) stands upright on a
    piece worked from the other end.
    """
    if count % motif.width:
        raise ValueError(f"{count} stitches does not tile the {motif.width}-stitch "
                         f"{motif.slug} repeat")
    across = count // motif.width
    lines = list(reversed(motif.grid)) if upside_down else list(motif.grid)
    for i, line in enumerate(lines):
        ops = ([Op("sc", count)] if set(line) == {"0"} else
               [Repeat(_runs(line), times=across)])
        rows.add(ops, count, colours[i % 2], turning_chain=turning)


def _provenance(slug: str, brief: dict, primitives: tuple[str, ...]):
    return catalogue_provenance(slug, {"builder": f"{ENGINEERED_BY}.{slug}", **brief},
                                ("products.moment_candidates",) + primitives)


def _sized(cir: CIR, main: str, around: str | None = None, along: str | None = None,
           *, across: str | None = None) -> CIR:
    """State the finished size the twin computes for the main piece, never a typed figure.

    A round piece states its circumference (stitches over gauge) and, where the twin can
    measure one, its length; a flat piece states width and length. A closed, stuffed shape
    has no twin length (`twin.size_refusal`), so only its circumference is stated.
    """
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    result = compile_cir(cir)
    if not result.ok:
        return cir          # certification reports the compile errors; nothing to state
    twin = build_twin(cir, result, component=main)
    comp = next(c for c in cir.components if c.name == main)
    parts = []
    if comp.construction == "flat_rows":
        if twin.width_cm and twin.height_cm:
            parts.append(f"about {twin.width_cm:.0f} cm {across or 'wide'} and "
                         f"{twin.height_cm:.0f} cm {along or 'long'}")
    else:
        widest = max(r.stitch_count for r in result.rows if r.component == main)
        parts.append(f"about {widest / cir.gauge.stitches_per_10cm * 10.0:.0f} cm "
                     f"{around or 'around'}")
        if twin.height_cm and along and not twin.size_refusal:
            parts.append(f"about {twin.height_cm:.0f} cm {along}")
    cir.finished_size_note = (
        "The finished piece is " + " and ".join(parts) + " at the stated gauge. Computed "
        "from the stitch counts by the digital twin, not yet measured on a worked sample.")
    return cir


# ---------------------------------------------------------------------------------------
# 1. first-christmas-stocking

def first_christmas_stocking(version: str = VERSION) -> CIR:
    """Toe-up stocking in joined rounds with an afterthought heel and a fir-and-star leg.

    * Toe: increase rounds from a magic ring to the leg count, staggered so they never stack.
    * Foot, then a heel-opening round: half the stitches are bridged by a chain and skipped,
      which leaves a slot; the heel is worked into that slot afterwards, in the round, and
      decreased closed (an afterthought heel), so no seam is needed and none is claimed.
    * Leg: one 24-round repeat of the fir-and-star chart, worked from its last line so the
      firs stand upright when the stocking hangs cuff-up; then a plain cream cuff band and a
      slip-stitch edge round.
    * Hanging tab: four stitches of the edge round are held and worked up as a tab, which is
      folded and sewn to itself to make the loop.

    The brief named "stranded colourwork" and a "turned heel"; the CIR cannot express
    per-stitch colour, so the firs and stars are a relief (see ENGINEERING_NOTES).
    """
    g = _gauge("worsted")
    motif = get("fir-and-star")
    leg = _sts_for(38.0, g, 12)                       # ~38 cm round: 48 sts at 12.5/10cm
    foot_rounds = _rounds_for(9.0, g)
    rows = _Rows()
    _disc(rows, leg, "cream")                         # toe
    toe_end = rows.last
    _plain(rows, foot_rounds, leg, "forest")
    half = leg // 2
    rows.add([Op("sc", half), Op("ch", half, spans=half), Op("sk", half)], leg, "forest",
             note=f"heel opening: the {half} chains bridge {half} skipped stitches")
    heel_round = rows.last
    _plain(rows, 2, leg, "forest")
    _relief_band(rows, motif, leg, ("forest", "cream"), upside_down=True)
    band_end = rows.last
    cuff_rounds = _rounds_for(6.0, g, 6)
    _plain(rows, cuff_rounds, leg, "cream")
    rows.add([Op("slst", leg)], leg, "cream", note="a slip-stitch edge round for the cuff")
    tab_sts = 4
    stocking = Component(
        name="stocking", construction="joined_rounds", rows=rows.rows, foundation=0,
        foundation_kind="magic_ring",
        holds=[Hold("hanging_tab", at_row=rows.last, count=tab_sts, from_stitch=0,
                    note="the first four stitches of the last cuff round, at the back join")],
        note="Worked toe-up in one piece.")

    heel_rows = _Rows()
    heel_rows.add([Op("sc", leg)], leg, "cream",
                  note=(f"join cream at one corner of the heel opening and work {half} sc "
                        f"along the chain side and {half} sc along the skipped stitches"))
    _plain(heel_rows, 2, leg, "cream")
    _decrease_to(heel_rows, leg, 12, "cream")
    heel = Component(name="heel", construction="joined_rounds", rows=heel_rows.rows,
                     foundation=leg, foundation_kind="none",
                     note="An afterthought heel, worked in the round into the heel opening.")

    tab_rows = _Rows()
    tab_len = _rounds_for(10.0, g)
    for _ in range(tab_len):
        tab_rows.add([Op("sc", tab_sts)], tab_sts, "cream", turning_chain=1)
    tab = Component(name="hanging_tab", construction="flat_rows", rows=tab_rows.rows,
                    foundation=tab_sts, foundation_kind="none", resumes="hanging_tab",
                    note="A narrow tab worked up from the held cuff stitches.")

    assembly = [
        Seam("whipstitch", "hanging_tab", "hanging_tab", edge_a="top", edge_b="bottom",
             note="Fold the tab in half to the inside of the cuff and sew its last row to its "
                  "first, making the hanging loop."),
    ]
    return _sized(CIR(
        slug="first-christmas-stocking", title="First Christmas Fir and Star Stocking",
        version=version, construction="joined_rounds", risk_class="B",
        colors={"forest": FOREST, "cream": CREAM}, gauge=g,
        materials=[Material(name="worsted acrylic", yarn_weight="worsted", colorway="forest",
                            color_id="forest"),
                   Material(name="worsted acrylic", yarn_weight="worsted", colorway="cream",
                            color_id="cream")],
        components=[stocking, heel, tab], assembly=assembly,
        designer_notes=(
            f"Fir and Star relief on a {motif.width}-stitch repeat, {leg // motif.width} "
            f"around the leg, one full chart (rounds {band_end - len(motif.grid) + 1}-"
            f"{band_end}) worked from its last line so the firs stand upright when the "
            f"stocking hangs. The relief is double crochet standing above a single-crochet "
            f"ground, one colour per round. Every round starts at the join, so the colour "
            f"not in use waits at the join on the inside: carry it up loosely there. The toe "
            f"is rounds 1-{toe_end}. Round {heel_round} leaves the heel opening; the heel "
            f"is worked into it afterwards and decreased closed, then the last 12 stitches "
            f"are drawn together. The cuff is left plain cream, wide enough to embroider an "
            f"initial on if you choose."),
        finished_size_note=None,
        provenance=_provenance(
            "first-christmas-stocking",
            {"leg_sts": leg, "gauge": vars(g), "motif": motif.slug, "motif_grid": list(motif.grid),
             "construction": "toe-up joined rounds, afterthought heel, held-stitch tab"},
            ("products.motifs:fir-and-star", "joined_rounds", "chain_span_opening",
             "hold_resume")),
    ), "stocking", "around the leg", "from toe to cuff")


def _two(name_a: str, name_b: str, weight: str, fibre: str) -> list[Material]:
    return [Material(name=f"{weight} {fibre}", yarn_weight=weight, colorway=n, color_id=n)
            for n in (name_a, name_b)]


# ---------------------------------------------------------------------------------------
# 2. reading-nook-cable-wrap

def reading_nook_cable_wrap(version: str = VERSION) -> CIR:
    """A long rectangular wrap, worked in flat rows, with 2-over-2 cables running its length.

    Rows run across the wrap's width, so cable columns stack up its length. A four-row cycle:
    a right-side cable row (three dc between each crossing), a wrong-side sc row, a plain dc
    row, a wrong-side sc row. Cream end bands of single crochet frame the forest body.

    The 2-over-2 crossing is an uncalibrated primitive in this company (`cir.stitches`):
    its row height is a convention until a tester works it, which certification reports
    as a physical calibration gate, not a design defect.
    """
    g = _gauge("worsted")
    unit = 7                                          # dc 3 + one 4-stitch crossing
    repeats = max(2, int(round((48.0 * g.stitches_per_10cm / 10.0 - 3) / unit)))
    width = repeats * unit + 3
    band = 4
    rows = _Rows()
    for _ in range(band):
        rows.add([Op("sc", width)], width, "cream", turning_chain=1)
    cycle_cm = 4.4                                    # cross(dc) + sc + dc + sc, approx.
    cycles = max(4, int(round((170.0 - 6.0) / cycle_cm)))
    for _ in range(cycles):
        rows.add([Repeat([Op("dc", 3), Op("cable2x2")], times=repeats), Op("dc", 3)],
                 width, "forest", turning_chain=2, note="cable row (right side)")
        rows.add([Op("sc", width)], width, "forest", turning_chain=1)
        rows.add([Op("dc", width)], width, "forest", turning_chain=2)
        rows.add([Op("sc", width)], width, "forest", turning_chain=1)
    for _ in range(band):
        rows.add([Op("sc", width)], width, "cream", turning_chain=1)
    wrap = Component(name="wrap", construction="flat_rows", rows=rows.rows, foundation=width,
                     foundation_kind="chain", grain="up",
                     note="Worked in rows from one end of the wrap to the other.")
    return _sized(CIR(
        slug="reading-nook-cable-wrap", title="Reading Nook Cable Wrap", version=version,
        construction="flat_rows", risk_class="B",
        colors={"forest": FOREST, "cream": CREAM}, gauge=g,
        materials=_two("forest", "cream", "worsted", "wool"),
        components=[wrap],
        designer_notes=(
            f"{repeats} cable columns, each a 2-over-2 crossing worked on every fourth row, "
            f"separated by three double crochet, so the cables run the full length of the "
            f"wrap. Rows alternate double and single crochet; the cable rows face you. The "
            f"forest body is framed by {band} rows of cream single crochet at each end; the "
            f"colour changes only at the two bands, so cut and rejoin there."),
        provenance=_provenance(
            "reading-nook-cable-wrap",
            {"width_sts": width, "cycles": cycles, "gauge": vars(g),
             "construction": "flat rows, 4-row cable cycle"},
            ("cir.stitches:cable2x2", "flat_rows")),
    ), "wrap", along="long", across="wide")


# ---------------------------------------------------------------------------------------
# 3. mothers-day-heart-tea-cosy

def mothers_day_heart_tea_cosy(version: str = VERSION) -> CIR:
    """A tea cosy worked top-down: a flat crown, a heart-row band, then two skirt panels.

    The crown is increase rounds from a magic ring; the body is straight rounds carrying one
    repeat of the heart-row chart (worked from its first line, so the hearts point down);
    then the round divides: half the stitches are held for the back, and the front and back
    are each worked down in rows. The two gaps between the panels are the spout and handle
    openings, so the openings are made by the construction rather than cut or claimed.
    """
    g = _gauge("dk")
    motif = get("heart-row")
    n = _sts_for(62.0, g, 30)                         # whole hearts and whole wedges
    rows = _Rows()
    _disc(rows, n, "cream")
    crown_end = rows.last
    _plain(rows, 2, n, "cream")
    _relief_band(rows, motif, n, ("wine", "cream"))
    _plain(rows, 2, n, "cream")
    half = n // 2
    body = Component(
        name="cosy", construction="joined_rounds", rows=rows.rows, foundation=0,
        foundation_kind="magic_ring",
        holds=[Hold("front", at_row=rows.last, count=half, from_stitch=0,
                    note="the front half of the last round"),
               Hold("back", at_row=rows.last, count=half, from_stitch=half,
                    note="the back half of the last round")],
        note="Worked top-down from the centre of the crown.")
    skirt_rows = _rounds_for(8.0, g)

    def skirt(name: str) -> Component:
        r = _Rows()
        for _ in range(skirt_rows):
            r.add([Op("sc", half)], half, "cream", turning_chain=1)
        return Component(name=name, construction="flat_rows", rows=r.rows, foundation=half,
                         foundation_kind="none", resumes=name,
                         note=f"The {name} skirt, worked down in rows from the held stitches.")

    return _sized(CIR(
        slug="mothers-day-heart-tea-cosy", title="Heart Row Tea Cosy", version=version,
        construction="joined_rounds", risk_class="B",
        colors={"cream": CREAM, "wine": WINE}, gauge=g,
        materials=_two("cream", "wine", "dk", "wool"),
        components=[body, skirt("front"), skirt("back")],
        designer_notes=(
            f"Heart Row relief on a {motif.width}-stitch repeat, {n // motif.width} hearts "
            f"around, double crochet standing above a single-crochet ground, one colour per "
            f"round. Rounds 1-{crown_end} are the crown. The two gaps left between the front "
            f"and back skirts are the spout and handle openings; each skirt is "
            f"{skirt_rows} rows deep."),
        provenance=_provenance(
            "mothers-day-heart-tea-cosy",
            {"sts": n, "gauge": vars(g), "motif": motif.slug, "motif_grid": list(motif.grid),
             "construction": "top-down crown, band, held halves worked as skirts"},
            ("products.motifs:heart-row", "joined_rounds", "hold_resume")),
    ), "cosy", "around the body", "from the crown to the start of the skirts")


# ---------------------------------------------------------------------------------------
# 4. snowfall-advent-garland

def snowfall_advent_garland(version: str = VERSION) -> CIR:
    """Twenty-four mitten pockets, each with an afterthought thumb and a hanging tab, and a
    chain cord threaded through the tabs.

    A mitten is worked from the fingertip in joined rounds: increase rounds, one repeat of
    the snowfall chart (two across), a thumb-opening round (three chains bridging three
    skipped stitches), then a cream cuff and a slip-stitch edge. The thumb is worked into the
    opening afterwards. Four edge stitches are held and worked up as a tab, folded into a
    loop. The cord is a single row of slip stitch along a chain, threaded through the loops.
    """
    g = _gauge("worsted")
    motif = get("snowfall")
    n = 24                                            # two snowfall repeats around
    rows = _Rows()
    _disc(rows, n, "cream")
    _plain(rows, 1, n, "forest")
    _relief_band(rows, motif, n, ("forest", "cream"))
    rows.add([Op("sc", n - 4), Op("ch", 3, spans=3), Op("sk", 3), Op("sc", 1)], n, "forest",
             note="thumb opening: three chains bridge three skipped stitches")
    thumb_round = rows.last
    _plain(rows, 2, n, "forest")
    _plain(rows, 3, n, "cream")
    rows.add([Op("slst", n)], n, "cream", note="a slip-stitch edge round for the cuff")
    pockets = 24
    mitten = Component(
        name="mitten", construction="joined_rounds", rows=rows.rows, foundation=0,
        foundation_kind="magic_ring", make=pockets,
        holds=[Hold("loop_tab", at_row=rows.last, count=4, from_stitch=0,
                    note="four stitches of the edge round, at the join")],
        note="Worked from the fingertip in one piece.")
    t = _Rows()
    t.add([Op("sc", 6)], 6, "forest",
          note="join forest at one corner of the thumb opening and work 3 sc along the "
               "chain and 3 sc along the skipped stitches")
    _plain(t, 3, 6, "forest")
    t.add([Repeat([Op("dec")], times=3)], 3, "forest", note="draw the last 3 stitches closed")
    thumb = Component(name="thumb", construction="joined_rounds", rows=t.rows, foundation=6,
                      foundation_kind="none", make=pockets,
                      note="An afterthought thumb, worked into the thumb opening.")
    tab = _Rows()
    for _ in range(_rounds_for(5.0, g)):
        tab.add([Op("sc", 4)], 4, "cream", turning_chain=1)
    loop_tab = Component(name="loop_tab", construction="flat_rows", rows=tab.rows,
                         foundation=4, foundation_kind="none", resumes="loop_tab",
                         make=pockets, note="A short tab worked up from the held stitches.")
    cord_len = _sts_for(24 * 11.0 + 2 * 30.0, g, 1)
    cord = Component(name="cord", construction="flat_rows",
                     rows=[Row(index=1, ops=[Op("slst", cord_len)], declared_count=cord_len,
                               color="forest", turning_chain=1)],
                     foundation=cord_len, foundation_kind="chain",
                     note="Thread the cord through the 24 loops, spacing the mittens evenly "
                          "and leaving about 30 cm free at each end for tying.")
    return _sized(CIR(
        slug="snowfall-advent-garland", title="Snowfall Mitten Advent Garland",
        version=version, construction="joined_rounds", risk_class="B",
        colors={"forest": FOREST, "cream": CREAM}, gauge=g,
        materials=_two("forest", "cream", "worsted", "acrylic"),
        components=[mitten, thumb, loop_tab, cord],
        assembly=[Seam("whipstitch", "loop_tab", "loop_tab", edge_a="top", edge_b="bottom",
                       note="Fold each tab in half to the inside of its cuff and sew its last "
                            "row to its first, making a loop. Repeat for all 24.")],
        designer_notes=(
            f"Make {pockets} mittens, {pockets} thumbs and {pockets} tabs, and one cord. "
            f"Snowfall relief on a {motif.width}-stitch repeat, two across each mitten, "
            f"double crochet standing above a single-crochet ground, one colour per round; "
            f"every round starts at the join, so carry the colour not in use up the inside "
            f"there. Round {thumb_round} leaves the thumb opening. Each cuff is an open "
            f"pocket for a folded note."),
        provenance=_provenance(
            "snowfall-advent-garland",
            {"sts": n, "pockets": pockets, "gauge": vars(g), "motif": motif.slug,
             "motif_grid": list(motif.grid),
             "construction": "fingertip-up mittens, afterthought thumb, tab loops, cord"},
            ("products.motifs:snowfall", "joined_rounds", "chain_span_opening",
             "hold_resume")),
    ), "mitten", "around each mitten", "from fingertip to cuff")


# ---------------------------------------------------------------------------------------
# 5. housewarming-key-basket

def housewarming_key_basket(version: str = VERSION) -> CIR:
    """A round catch-all basket: a staggered-increase base and basketweave relief walls."""
    g = _gauge("worsted")
    motif = get("basketweave")
    n = _sts_for(20.0 * math.pi, g, 24)               # whole wedges and whole blocks
    rows = _Rows()
    _disc(rows, n, "cream")
    base_end = rows.last
    _plain(rows, 1, n, "pine")
    _relief_band(rows, motif, n, ("pine", "cream"))
    _plain(rows, 2, n, "pine")
    rows.add([Op("slst", n)], n, "pine", note="a slip-stitch edge round for the rim")
    basket = Component(name="basket", construction="joined_rounds", rows=rows.rows,
                       foundation=0, foundation_kind="magic_ring",
                       note="Worked in one piece from the centre of the base.")
    return _sized(CIR(
        slug="housewarming-key-basket", title="Housewarming Key Basket", version=version,
        construction="joined_rounds", risk_class="B",
        colors={"pine": FOREST, "cream": CREAM}, gauge=g,
        materials=_two("pine", "cream", "worsted", "cotton"),
        components=[basket],
        designer_notes=(
            f"Rounds 1-{base_end} are the base; the increases move to the middle of each "
            f"wedge on alternate rounds so they never stack and the base stays round. The "
            f"walls carry one repeat of the {motif.name} chart, {n // motif.width} blocks "
            f"around: double crochet standing above a single-crochet ground, one colour per "
            f"round. How firmly the walls stand depends on yarn and tension, so nothing is "
            f"claimed about stiffness until a sample is made."),
        provenance=_provenance(
            "housewarming-key-basket",
            {"sts": n, "gauge": vars(g), "motif": motif.slug, "motif_grid": list(motif.grid),
             "construction": "staggered disc base, relief walls"},
            ("products.motifs:basketweave", "joined_rounds")),
    ), "basket", "around the wall", "tall")


# ---------------------------------------------------------------------------------------
# 6. heart-row-ring-pillow

def heart_row_ring_pillow(version: str = VERSION) -> CIR:
    """A small round drum pillow: a top worked down into a heart-row side band, a matching
    bottom disc sewn on over the stuffing, and a slip-stitch cord at the centre for the rings.

    Stuffed and closed, so the risk matrix sets class C (F-073): its finished shape is only
    known from a full physical make, and certification says so rather than guessing.
    """
    g = _gauge("fine")
    motif = get("heart-row")
    n = _sts_for(15.0 * math.pi, g, 30)
    rows = _Rows()
    _disc(rows, n, "cream")
    top_end = rows.last
    _relief_band(rows, motif, n, ("wine", "cream"))
    rows.add([Op("sc", n)], n, "cream")
    band_end = rows.last
    pillow = Component(name="pillow", construction="joined_rounds", rows=rows.rows,
                       foundation=0, foundation_kind="magic_ring",
                       note="The top and side band, worked in one piece from the centre.")
    b = _Rows()
    _disc(b, n, "cream")
    bottom = Component(name="bottom", construction="joined_rounds", rows=b.rows,
                       foundation=0, foundation_kind="magic_ring",
                       note="A flat disc the same size as the top.")
    loop = Component(name="ring_loop", construction="flat_rows",
                     rows=[Row(index=1, ops=[Op("slst", 40)], declared_count=40,
                               color="wine", turning_chain=1)],
                     foundation=40, foundation_kind="chain",
                     note="A slip-stitch cord; its middle is sewn to the centre of the top "
                          "and its ends tie the rings on.")
    return _sized(CIR(
        slug="heart-row-ring-pillow", title="Heart Row Ring Pillow", version=version,
        construction="joined_rounds", risk_class="C",
        colors={"cream": CREAM, "wine": WINE}, gauge=g,
        materials=_two("cream", "wine", "fine", "cotton") + [
            Material(name="polyester fibrefill")],
        components=[pillow, bottom, loop],
        assembly=[
            Seam("whipstitch", "bottom", "pillow", edge_a="top", edge_b="bottom",
                 at_round=band_end, stuff_before_closing=True,
                 note=f"Whipstitch the bottom disc's last round to round {band_end} of the "
                      f"pillow, stuffing firmly with fibrefill before closing the last few "
                      f"centimetres."),
            Seam("sew", "ring_loop", "ring_loop", edge_a="left", edge_b="right",
                 note="Fold the cord in half and sew its middle to the magic-ring centre of "
                      "the top; tie the rings on with the two ends."),
        ],
        designer_notes=(
            f"Rounds 1-{top_end} are the top; the side band (rounds {top_end + 1}-"
            f"{band_end}) carries one repeat of the Heart Row chart, {n // motif.width} "
            f"hearts around, double crochet standing above a single-crochet ground, one "
            f"colour per round."),
        provenance=_provenance(
            "heart-row-ring-pillow",
            {"sts": n, "gauge": vars(g), "motif": motif.slug, "motif_grid": list(motif.grid),
             "construction": "disc top and relief band, sewn bottom disc, cord loop"},
            ("products.motifs:heart-row", "joined_rounds")),
    ), "pillow", "around the side band", "deep")


# ---------------------------------------------------------------------------------------
# 7. spring-garden-kneeler

def spring_garden_kneeler(version: str = VERSION) -> CIR:
    """A kneeling pad: a tulip-trellis relief front panel and a plain back panel of the same
    size, sewn together around the edge over a firm stuffing.

    The tulip rows of each repeat (chart lines 4-7) are worked in gold and the trellis rows
    in pine, so the tulip heads are gold; one colour per row, as everywhere in this
    catalogue. The back panel's row count is chosen so its measured height matches the
    front's (the assembly check holds both edges to the same length).
    """
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    g = _gauge("worsted")
    motif = get("tulip-trellis")
    width = _sts_for(38.0, g, motif.width)
    across = width // motif.width
    rows = _Rows()
    for _ in range(2):
        rows.add([Op("sc", width)], width, "pine", turning_chain=1)
    for _ in range(2):
        for i, line in enumerate(motif.grid):
            colour = "gold" if 4 <= i <= 7 else "pine"
            ops = [Repeat(_runs(line), times=across)]
            first = _runs(line)[0].stitch
            rows.add(ops, width, colour, turning_chain=2 if first == "dc" else 1)
    for _ in range(2):
        rows.add([Op("sc", width)], width, "pine", turning_chain=1)
    front = Component(name="front", construction="flat_rows", rows=rows.rows,
                      foundation=width, foundation_kind="chain")
    probe = CIR(slug="probe", title="probe", version=version, construction="flat_rows",
                components=[front], gauge=g, colors={"pine": FOREST, "gold": GOLD})
    front_h = build_twin(probe, compile_cir(probe), component="front").height_cm
    back_rows = max(2, int(round(front_h / _row_cm(g))))
    back = Component(
        name="back", construction="flat_rows",
        rows=[Row(index=i, ops=[Op("sc", width)], declared_count=width, color="pine",
                  turning_chain=1) for i in range(1, back_rows + 1)],
        foundation=width, foundation_kind="chain")
    return _sized(CIR(
        slug="spring-garden-kneeler", title="Spring Garden Kneeler", version=version,
        construction="flat_rows", risk_class="C",
        colors={"pine": FOREST, "gold": GOLD}, gauge=g,
        materials=_two("pine", "gold", "worsted", "acrylic") + [
            Material(name="polyester fibrefill")],
        components=[front, back],
        assembly=[Seam("whipstitch", "front", "back", edge_a="perimeter",
                       edge_b="perimeter", stuff_before_closing=True, at_round=1,
                       spans_rounds=back_rows,
                       note="Place the panels wrong sides together and whipstitch around "
                            "three sides; stuff firmly with polyester fibrefill, then close "
                            "the fourth side.")],
        designer_notes=(
            f"Tulip Trellis relief on a {motif.width}-stitch repeat, {across} across and two "
            f"up, between two single-crochet rows top and bottom: double crochet standing "
            f"above a single-crochet ground. The four tulip rows of each repeat are worked "
            f"in gold and every other row in pine, so cut and rejoin at each colour change. "
            f"The back is {back_rows} rows of single crochet."),
        provenance=_provenance(
            "spring-garden-kneeler",
            {"width_sts": width, "back_rows": back_rows, "gauge": vars(g),
             "motif": motif.slug, "motif_grid": list(motif.grid),
             "construction": "relief front panel + plain back panel, stuffed"},
            ("products.motifs:tulip-trellis", "flat_rows")),
    ), "front", along="deep", across="wide")


# Engineering queue order (emotional_brief.gate_candidates()['engineering_queue'] on
# 2026-10-07), minus the pencil roll, which products.pipeline_board engineers.
ENGINEERED = {
    "first-christmas-stocking": first_christmas_stocking,
    "reading-nook-cable-wrap": reading_nook_cable_wrap,
    "mothers-day-heart-tea-cosy": mothers_day_heart_tea_cosy,
    "snowfall-advent-garland": snowfall_advent_garland,
    "heart-row-ring-pillow": heart_row_ring_pillow,
    "housewarming-key-basket": housewarming_key_basket,
    "spring-garden-kneeler": spring_garden_kneeler,
}

# Listing qualifiers for the search stage (category word, motif words, season), the same
# shape as `pipeline_board.CREATIVE_SEARCH`. Motif words are only what each fabric depicts.
SEARCH: dict[str, tuple[str, tuple[str, ...], str | None]] = {
    "first-christmas-stocking": ("christmas stocking", ("fir", "star"), "christmas"),
    "reading-nook-cable-wrap": ("wrap", ("cable",), None),
    "mothers-day-heart-tea-cosy": ("tea cosy", ("heart",), None),
    "snowfall-advent-garland": ("advent garland", ("snowfall", "mitten"), "christmas"),
    "housewarming-key-basket": ("basket", ("basketweave",), None),
    "heart-row-ring-pillow": ("ring pillow", ("heart",), None),
    "spring-garden-kneeler": ("garden kneeler", ("tulip", "trellis"), None),
}

# Where the engineered design departs from the creative brief, and why. The CIR is the
# product; a brief that asked for something the CIR cannot honestly express is answered
# with what it does instead, and the creative lane is told (handoff_PIPE2.md).
ENGINEERING_NOTES: dict[str, str] = {
    "first-christmas-stocking": (
        "Brief techniques named stranded colourwork and a turned heel. Per-stitch colour is "
        "not expressible in the CIR, so the firs and stars are a dc relief, one colour per "
        "round; the heel is an afterthought heel worked into a chain-bridged opening."),
    "reading-nook-cable-wrap": (
        "Real 2-over-2 cable crossings (cable2x2), so the name's cable claim is backed; the "
        "crossing is an uncalibrated primitive, which is a physical-tester gate. The cream "
        "'border edging' is cream end bands (a perimeter round is not expressible on one "
        "flat component)."),
    "mothers-day-heart-tea-cosy": (
        "Seamless top-down: crown, heart band, then held halves worked as front and back "
        "skirts; the gaps between them are the spout and handle openings."),
    "snowfall-advent-garland": (
        "24 fingertip-up mittens with afterthought thumbs and folded tab loops, threaded on "
        "a slip-stitch cord. Numbers on the pockets are not engineered (no chart support for "
        "numerals) and are not claimed in the title."),
    "housewarming-key-basket": (
        "Staggered increases so the base is round, as the brief says; the disclosed "
        "renderer draws only fully stacked (polygon) bases today (cir.geometry.corners "
        "cannot return 0 for a disc whose second round is all increases)."),
    "heart-row-ring-pillow": (
        "A drum pillow: disc top worked down into a heart-row side band, a sewn-on bottom "
        "over fibrefill. Stuffed and closed, so class C: a physical make is required."),
    "spring-garden-kneeler": (
        "Brief named modular panels and tulip bobbles. Engineered as a relief front panel "
        "and a matching back (a grid of squares cannot be length-checked by cir.assembly), "
        "with the tulip heads as gold dc relief rows rather than bobbles (bob is an "
        "uncalibrated primitive). New motif products.motifs:tulip-trellis. Stuffed: class C."),
}


# ---------------------------------------------------------------------------------------
# The concept board the creative taste gate judges (CREATIVE_DIAGNOSIS r2, B-137).
#
# Rendered deterministically from the engineered CIR's digital twin -- the company's own
# arithmetic, drawn stitch by stitch exactly as `creative.board.make_board` draws a
# prototype -- never presented as a photograph. Filed as one audit row whose image digest a
# vision judgement can be bound to (`creative.intake.board_for` / `board_digest_for`).

BOARD_ACTION = "creative.concept_board"
BOARD_PX = 570


# Pieces worked from the top down (crown or top first): their first row is the top of the
# object as it is used. Every other main piece is drawn with its last row at the top.
WORKED_DOWN = frozenset({"mothers-day-heart-tea-cosy", "heart-row-ring-pillow"})
RAISED = frozenset({"cable2x2", "cable1x1", "fpdc", "bpdc", "bob"})


def board_png(cir: CIR, *, px: int = 26, window: int = 40) -> bytes:
    """The main piece's motif region, drawn stitch by stitch in the CIR's own colours.

    Each cell is one twin stitch in the colour its row is worked in; a raised stitch (dc,
    cable, post) is drawn taller and lit, as relief stands off the ground. The window is the
    rows that carry the motif (padded, at most `window` rows and stitches), oriented as the
    object is used. Deterministic: same CIR, same bytes.
    """
    import io
    import random

    from PIL import Image, ImageDraw

    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..visual.render import _shade, _stitch

    result = compile_cir(cir)
    if not result.ok:
        raise ValueError(f"{cir.slug} does not compile; there is no fabric to draw")
    twin = build_twin(cir, result, component=cir.components[0].name)
    rows = sorted({c.row for c in twin.cells})
    kinds: dict[int, set[str]] = {}
    for c in twin.cells:
        kinds.setdefault(c.row, set()).add(c.stitch)

    def raised(c) -> bool:
        # A crossing or post stitch always stands out; a dc only where it sits among sc in
        # its own row (relief), not in an all-dc row.
        return c.stitch in RAISED or (c.stitch == "dc" and "sc" in kinds[c.row])

    motif_rows = [r for r in rows if any(raised(c) for c in twin.cells if c.row == r)]
    lo_r, hi_r = (motif_rows[0], motif_rows[-1]) if motif_rows else (rows[0], rows[-1])
    span = [r for r in rows if lo_r - 2 <= r <= hi_r + 2][:window]
    if cir.slug not in WORKED_DOWN:
        span = list(reversed(span))                 # last row at the top
    by_row = {r: sorted((c for c in twin.cells if c.row == r),
                        key=lambda c: getattr(c, "fabric_position", c.position))[:window]
              for r in span}
    ncols = max(len(v) for v in by_row.values())
    aspect = (10.0 / cir.gauge.stitches_per_10cm) / (10.0 / cir.gauge.rows_per_10cm)
    cw, ch = px, max(8, int(round(px / aspect)))
    pitch = int(round(ch * 0.62))
    img = Image.new("RGB", (ncols * cw, len(span) * pitch + ch), (40, 36, 34))
    d = ImageDraw.Draw(img)
    rng = random.Random(0)

    def rgb(name: str | None) -> tuple[int, int, int]:
        h = (cir.colors.get(name or "") or "#888888").lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]

    for ri, r in enumerate(span):
        for col, c in enumerate(by_row[r]):
            base = rgb(c.color)
            up = raised(c)
            tone = rng.uniform(0.95, 1.05) * (1.08 if up else 0.92)
            body = _shade(base, tone)
            hgt = ch * (1.3 if up else 1.0)
            _stitch(d, col * cw, ri * pitch - (hgt - ch), cw, hgt, rng.uniform(-1, 1), body,
                    _shade(base, 1.3 if up else 1.12), _shade(base, 0.6),
                    loop=getattr(c, "loop", "both"), rng=rng)
    side = min(img.size)
    img = img.crop((0, 0, side, side)).resize((BOARD_PX, BOARD_PX))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def file_board(db, cir: CIR, store=None) -> dict:
    """Render, store and file the concept board for one engineered candidate."""
    from ..core.artifacts import ArtifactStore
    from ..core.models import AuditLog

    store = store or ArtifactStore()
    stored = store.put(f"board/{cir.slug}/{cir.version}.png", board_png(cir), "image/png",
                       db=db, keep="concept board for the creative taste gate")
    record = {"slug": cir.slug, "version": cir.version, "fingerprint": cir.fingerprint,
              "kind": "digital_twin_render", "image": {"sha256": stored.sha256},
              "image_ref": f"sha256:{stored.sha256}",
              "disclosure": ("a deterministic render of the engineered pattern's fabric from "
                             "its compiled digital twin, not a photograph"),
              "source": ENGINEERED_BY}
    with db.session() as s:
        s.add(AuditLog(actor="creative", action=BOARD_ACTION, artifact=cir.slug,
                       detail=record))
    return record


def board_record(db, slug: str) -> dict | None:
    """The newest concept board filed for `slug`, or None."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalars(select(AuditLog).where(AuditLog.action == BOARD_ACTION,
                                               AuditLog.artifact == slug)
                        .order_by(desc(AuditLog.id)).limit(1)).first()
        return dict(row.detail or {}) if row is not None else None


def register_for_taste_gate(db, slug: str, *, today=None) -> dict:
    """Put an engineered candidate where `creative.intake.regate_held` looks for it.

    Writes one `creative.winner_intake` row carrying the pre-engineering gate's own verdict
    for this candidate (`emotional_brief.gate_candidates`). It records `waiting` only when the
    gate says waiting: a refused candidate is filed as refused, and nothing here sets
    `thumbnail_reads_small` or `craft_impression` -- only a vision judge bound to the board's
    bytes may (`intake.judge_held`).
    """
    from ..core.models import AuditLog
    from ..creative import emotional_brief as eb
    from ..creative import intake

    gate = eb.gate_candidates(db, today=today)
    row = gate["candidates"].get(slug)
    if row is None:
        return {"registered": False, "why": f"{slug} is not a gated creative candidate: "
                                            f"{gate['refused_at_brief'].get(slug)}"}
    concepts, _ = eb.candidate_concepts()
    concept = next(c for c in concepts if c.key == slug)
    brief = eb.GATE_BRIEFS[slug].to_brief()
    decision = {"waiting": intake.WAITING, "refused": intake.REFUSED}.get(
        row["decision"], intake.ENGINEERING if row["engineer"] else intake.WAITING)
    cir = ENGINEERED[slug]()
    detail = {"decision": decision, "source": ENGINEERED_BY, "original_key": slug,
              "concept": concept.to_dict(), "brief": brief,
              "gate": {k: row[k] for k in ("decision", "failed", "unmeasured", "waiting_on",
                                           "reasons")},
              "judgement": None, "mjs_event_id": None,
              "payload": {"slug": slug, "title": cir.title, "version": cir.version,
                          "concept": concept.to_dict(), "brief": brief,
                          "engineered": f"products.moment_candidates.ENGINEERED[{slug!r}]",
                          "source": ENGINEERED_BY, "pod": concept.pod}}
    with db.session() as s:
        s.add(AuditLog(actor="creative", action=intake.INTAKE_ACTION, artifact=slug,
                       detail=detail))
    return {"registered": True, "decision": decision, "waiting_on": row["waiting_on"]}
