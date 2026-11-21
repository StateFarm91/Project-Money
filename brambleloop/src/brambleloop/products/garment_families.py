"""ENG-GARMENT: Brambleloop's garment families, graded from published body tables.

Garments are the core bestseller category: cardigans, sweaters, vests and baby and child wear
in a run of sizes. `products.garments` proved grading (Harbour, Pebble); this module makes a
garment a whole release a maker can buy: ribbed hems and cuffs, picked-up bands with
buttonholes, stated ease, a gauge for every fabric and yardage per size in balls and yards.

**Every size is the same list of steps.** A piece is built by `Piece`, which appends rows
AND records the step that made them (`Step`): cast on, work even, shape every Nth row,
chain on, leave unworked, raglan increases, pick up. A size is the same step kinds in the
same order with that size's numbers. That is what lets one document print the smallest size
first with every other size in parentheses (`publish.garment_pdf`), and lets that text be
read back and expanded per size and compared with what the compiler counted
(`gates.garment_fit.multi_size_problems`). A design whose step list differs between sizes is
several designs sharing a name, and is refused (`step_signature`).

**Constructions** (each a function from one `cir.graded.GradedSize` to a whole CIR):

- `raglan_cardigan` -- top-down raglan, worked flat from the neck; sleeves resume their held
  stitches; ribbed hem and cuffs; front bands picked up along each front edge, buttonholes
  on the right band (or no buttons, for babies).
- `one_piece_sweater` -- a flat one-piece body with built-in sleeves: worked from the front
  hem, sleeves chained on at the underarm, over a slash neck at the shoulder line, sleeves
  left unworked on the way down, to the back hem. Side and underarm seams close it; cuffs and
  neckband are picked up.
- `side_to_side_vest` -- front and back panels worked side to side (the rows run vertically
  on the body, so the hem rib is the first stitches of every row), joined at the shoulders
  and sides, with a slash neck and armholes left open in the seams.
- `drop_shoulder_pullover` -- drop-shoulder panels with seaming: one body panel worked over
  the shoulders with a slash neck, sleeves worked flat and sewn on centred on the shoulder
  line, ribbed hems and cuffs, neckband picked up.

The proportions a body chart does not publish (neck width, cuff width, band depth, rib
depth, button spacing) are named design ratios here, never presented as measurements. No
benchmark is a source: this module imports nothing from `cir.benchmarks` or `research/`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..cir.graded import BABY, CHILD, WOMAN, FitIntent, GradedDesign, GradedSize
from ..cir.model import CIR, Component, Gauge, Hold, Material, Op, Row, Seam
from ..cir.shaping import SHAPING, ShapingRefused
from .garments import StitchFamily, _even

# ---- design ratios (stated, not measured) -------------------------------------------------

RIB_CM = 4.0                 # depth of a ribbed hem or cuff (adult); child/baby use RIB_CM_SMALL
RIB_CM_SMALL = 2.5
BAND_CM = 2.5                # depth of a picked-up front band or neckband (adult)
BAND_CM_SMALL = 2.0
CUFF_OF_UPPER_ARM = 0.8      # cuff width as a share of the finished upper arm
NECK_OF_CROSS_BACK = 0.75    # slash/raglan neck width as a share of the body's cross-back
BUTTON_SPACING_CM = 9.0      # target distance between buttons on an adult band
BUTTON_MM = 20               # the button a 2-stitch buttonhole fits in this fabric
BUTTONHOLE_STS = 2
MAX_PICKUP_DRIFT = 0.04      # a picked-up edge must be within 4% of the edge it is worked into

# Ball size the yardage is stated in (a design choice the supply list prints): the common
# put-up for each weight, in metres and grams. Balls are always rounded UP from the twin.
BALLS: dict[str, tuple[float, int]] = {
    # keyed by `publish.substitution` weight key (what `gauge_for` stores as yarn_weight);
    # each inside that weight's published metres-per-100 g band.
    "medium": (200.0, 100), "light": (230.0, 100), "fine": (150.0, 50),
    "bulky": (120.0, 100), "super_fine": (200.0, 50),
}
YARD_PER_M = 1.0936133


# ---- the step record --------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    """One instruction a piece is made of, with this size's numbers.

    `kind` is the instruction's shape and is identical across sizes; `n` holds this size's
    numbers (stitch counts, row counts, spacing). `first`/`last` are the rows it covers and
    `count` the stitch count after its last row."""

    piece: str
    kind: str
    first: int
    last: int
    count: int
    n: tuple[tuple[str, int], ...] = ()
    loop: str = "both"
    label: str = ""

    def get(self, key: str) -> int:
        return dict(self.n)[key]

    def to_dict(self) -> dict:
        return {"piece": self.piece, "kind": self.kind, "first": self.first,
                "last": self.last, "count": self.count, "n": dict(self.n), "loop": self.loop,
                "label": self.label}


class Piece:
    """Builds one component's rows and records the steps that made them."""

    def __init__(self, name: str, fam: StitchFamily, *, foundation: int, grain: str = "up",
                 make: int = 1, resumes: str | None = None, feature: str | None = None,
                 direction: str | None = None, note: str | None = None,
                 foundation_kind: str = "chain"):
        self.name, self.fam = name, fam
        self.rows: list[Row] = []
        self.steps: list[Step] = []
        self.holds: list[Hold] = []
        self.count = foundation
        self.kw = dict(foundation=foundation, grain=grain, make=make, resumes=resumes,
                       feature=feature, work_direction=direction, note=note,
                       foundation_kind="none" if resumes else foundation_kind)
        kind = "resume" if resumes else ("pick_up" if foundation_kind == "none" else "cast_on")
        self._record(kind, 0, 0, n=(("sts", foundation),), label=resumes or "")

    @property
    def next_index(self) -> int:
        return len(self.rows) + 1

    def _record(self, kind, first, last, *, n=(), loop="both", label=""):
        self.steps.append(Step(self.name, kind, first, last, self.count, tuple(n), loop,
                               label))

    def _row(self, ops, *, skips=0, note=None) -> Row:
        merged: list[Op] = []
        for op in ops:
            if op.count <= 0:
                continue
            merged.append(op)
        row = Row(index=self.next_index, ops=merged, declared_count=None,
                  turning_chain=self.fam.turning_chain, skips=skips, note=note)
        self.rows.append(row)
        return row

    def _finish(self, row: Row, count: int) -> None:
        row.declared_count = count
        self.count = count

    def loop_for(self, loop: str | None, index: int) -> str:
        return loop if loop is not None else self.fam.loop(index)

    def even(self, rows: int, *, loop: str | None = None, label: str = "",
             edge_rib: tuple[int, str] | None = None) -> None:
        """`rows` plain rows. `loop` overrides the fabric's texture ("back" for rib).
        `edge_rib=(n, "start"|"end")`: the first n stitches at that end of the FIRST row are
        worked in the back loop, alternating ends row by row (side-to-side hem rib)."""
        if rows < 1:
            raise ShapingRefused(f"{self.name}: a step of {rows} rows")
        first = self.next_index
        for _ in range(rows):
            i = self.next_index
            lp = self.loop_for(loop, i)
            if i == 1 and self.kw["foundation_kind"] == "chain":
                lp = "both"        # a foundation chain has no back loop to work into
            if edge_rib and i == 1 and self.kw["foundation_kind"] == "chain":
                self._finish(self._row([Op(self.fam.stitch, self.count, loop="both")]),
                             self.count)
                continue
            if edge_rib:
                k, end = edge_rib
                at_start = (end == "start") == ((i - first) % 2 == 0)
                body = Op(self.fam.stitch, self.count - k, loop=lp)
                rib = Op(self.fam.stitch, k, loop="back")
                ops = [rib, body] if at_start else [body, rib]
            else:
                ops = [Op(self.fam.stitch, self.count, loop=lp)]
            self._finish(self._row(ops), self.count)
        self._record("even", first, self.next_index - 1, n=(("rows", rows),),
                     loop=loop or "fabric", label=label + (":edge_rib" if edge_rib else ""))
        if edge_rib:
            self.steps[-1] = Step(self.name, "even_edge_rib", first, self.next_index - 1,
                                  self.count, (("rows", rows), ("rib", edge_rib[0])),
                                  "fabric", label)

    def shape(self, events: int, every: int, *, grow: bool, label: str = "",
              loop: str | None = None) -> None:
        """One increase (or decrease) at each end on the next row and every `every`th row
        after it, `events` times in all: (events - 1) * every + 1 rows."""
        if events < 1 or every < 1:
            raise ShapingRefused(f"{self.name}: shaping {events} times every {every} rows")
        inc, dec = SHAPING[self.fam.stitch]
        code = inc if grow else dec
        if code is None:
            raise ShapingRefused(f"{self.fam.stitch} cannot shape {'up' if grow else 'down'}")
        first = self.next_index
        total = (events - 1) * every + 1
        for k in range(total):
            i = self.next_index
            lp = self.loop_for(loop, i)
            if k % every == 0:
                middle = self.count - (2 if grow else 4)
                if middle < 1:
                    raise ShapingRefused(f"{self.name} row {i}: too narrow to shape")
                ops = [Op(code, 1, loop=lp), Op(self.fam.stitch, middle, loop=lp),
                       Op(code, 1, loop=lp)]
                self._finish(self._row(ops), self.count + (2 if grow else -2))
            else:
                self._finish(self._row([Op(self.fam.stitch, self.count, loop=lp)]),
                             self.count)
        self._record("inc" if grow else "dec", first, self.next_index - 1,
                     n=(("times", events), ("every", every)), loop=loop or "fabric",
                     label=label)

    def chain_on(self, extra: int, *, label: str = "") -> None:
        """Two rows: work across and chain `extra` at the end; then work into those chains,
        across, and chain `extra` again; the third row (the next step) works across all."""
        first = self.next_index
        for _ in range(2):
            i = self.next_index
            lp = self.loop_for(None, i)
            row = self._row([Op(self.fam.stitch, self.count, loop=lp), Op("ch", extra)],
                            note=f"chain {extra} loosely at the end of the row for the "
                                 f"sleeve")
            self._finish(row, self.count + extra)
        self._record("chain_on", first, self.next_index - 1, n=(("extra", extra),),
                     label=label)

    def leave(self, n: int, *, label: str = "") -> None:
        """Two rows, each leaving the last `n` stitches unworked (one sleeve each row)."""
        first = self.next_index
        for _ in range(2):
            i = self.next_index
            row = self._row([Op(self.fam.stitch, self.count - n, loop=self.loop_for(None, i))],
                            skips=n, note=f"leave the last {n} sts unworked")
            self._finish(row, self.count - n)
        self._record("leave", first, self.next_index - 1, n=(("leave", n),), label=label)

    def neck_bridge(self, neck: int, *, label: str = "slash neck") -> int:
        """The shoulder-line row: a chain bridges `neck` stitches at the centre."""
        if (self.count - neck) % 2 or neck < 2:
            raise ShapingRefused(f"{self.name}: a centred neck of {neck} on {self.count}")
        side = (self.count - neck) // 2
        i = self.next_index
        lp = self.loop_for(None, i)
        row = self._row([Op(self.fam.stitch, side, loop=lp), Op("ch", neck, spans=neck),
                         Op("sk", neck), Op(self.fam.stitch, side, loop=lp)],
                        note="shoulder line: the chain bridges the neck opening")
        self._finish(row, self.count)
        self._record("neck_bridge", i, i, n=(("side", side), ("neck", neck)), label=label)
        return i

    def buttonhole_row(self, gaps: list[int], *, label: str = "buttonholes") -> None:
        """A band row with a 2-stitch buttonhole after each of `gaps[:-1]`."""
        i = self.next_index
        lp = "back"
        ops: list[Op] = []
        for k, g in enumerate(gaps):
            ops.append(Op(self.fam.stitch, g, loop=lp))
            if k < len(gaps) - 1:
                ops += [Op("ch", BUTTONHOLE_STS, spans=BUTTONHOLE_STS), Op("sk", BUTTONHOLE_STS)]
        row = self._row(ops, note=f"{len(gaps) - 1} buttonholes")
        self._finish(row, self.count)
        self._record("buttonholes", i, i, n=(("holes", len(gaps) - 1), ("first", gaps[0]),
                                             ("between", gaps[1] if len(gaps) > 2 else 0),
                                             ("last", gaps[-1])), loop="back", label=label)

    def raglan(self, plan: list[int], f: int, s: int, b: int, *, label: str = "yoke") -> None:
        """Raglan increase rows: `plan[k]` units on row k (0 = plain)."""
        from .garments import _raglan_row

        first = self.next_index
        start = (("f0", f), ("s0", s), ("b0", b))
        for m in plan:
            i = self.next_index
            if m:
                row = _raglan_row(i, f, s, b, self.fam, m)
                self.rows.append(row)
                f, s, b = f + m, s + 2 * m, b + 2 * m
                self.count = row.declared_count
            else:
                self._finish(self._row([Op(self.fam.stitch, self.count,
                                           loop=self.fam.loop(i))]), self.count)
        doubles = sum(1 for m in plan if m == 2)
        singles = sum(1 for m in plan if m == 1)
        every = _spacing(plan)
        self._record("raglan", first, self.next_index - 1,
                     n=(("doubles", doubles), ("singles", singles), ("every", every),
                        ("rows", len(plan))) + start, label=label)

    def divide(self, sleeve: int, front: int, back: int) -> None:
        """The underarm row: sleeves on hold, fronts and back joined."""
        last = self.rows[-1].index
        self.holds += [Hold("sleeve_left", at_row=last, count=sleeve, from_stitch=front,
                            note="the body joins front to back under the arm"),
                       Hold("sleeve_right", at_row=last, count=sleeve,
                            from_stitch=front + sleeve + back)]
        width = 2 * front + back
        i = self.next_index
        row = self._row([Op(self.fam.stitch, width, loop=self.fam.loop(i))], skips=2 * sleeve,
                        note="fronts and back joined under each arm")
        self._finish(row, width)
        self._record("divide", i, i, n=(("sleeve", sleeve), ("front", front), ("back", back)),
                     label="underarm")

    def component(self, construction: str = "flat_rows") -> Component:
        return Component(self.name, construction, rows=self.rows, holds=self.holds,
                         **self.kw)


def _spacing(plan: list[int]) -> int:
    """Rows between single raglan increase rows (the doubles come first, every row)."""
    idx = [k for k, m in enumerate(plan) if m == 1]
    gaps = {b - a for a, b in zip(idx, idx[1:])}
    return min(gaps) if gaps else 1


def uniform(events: int, rows: int) -> tuple[int, int]:
    """(events, every) so `events` shaping rows fit in `rows` rows, evenly from the first.
    Events are capped at the rows available (one per row)."""
    if events <= 0:
        return 0, 1
    events = min(events, rows)
    every = 1 if events == 1 else max(1, (rows - 1) // (events - 1))
    return events, every


# ---- per-size facts a construction records --------------------------------------------------


@dataclass
class Facts:
    """What a built size states beyond its rows: the per-size numbers every gate re-checks."""

    construction: str
    pieces: dict[str, list[Step]] = field(default_factory=dict)
    seams: list[dict] = field(default_factory=list)    # garment seam ledger (gate input)
    pickups: list[dict] = field(default_factory=list)  # picked-up edges (gate input)
    buttons: int = 0
    rib_rows: int = 0
    band_rows: int = 0
    neck_cm: float = 0.0
    armhole_cm: float = 0.0
    sleeve_top_cm: float = 0.0
    band_cm: float = 0.0

    def to_dict(self) -> dict:
        return {"construction": self.construction,
                "pieces": {k: [s.to_dict() for s in v] for k, v in self.pieces.items()},
                "seams": self.seams, "pickups": self.pickups, "buttons": self.buttons,
                "rib_rows": self.rib_rows, "band_rows": self.band_rows,
                "neck_cm": self.neck_cm, "armhole_cm": self.armhole_cm,
                "sleeve_top_cm": self.sleeve_top_cm, "band_cm": self.band_cm}


FACTS_ATTR = "garment_facts"


def facts_of(cir: CIR) -> Facts | None:
    return getattr(cir, FACTS_ATTR, None)


def _cir(g: GradedSize, *, key, title, version, comps, seams, material, extra_materials,
         designer, size_note, risk, facts: Facts) -> CIR:
    cir = CIR(slug=f"{key}-{g.size.lower()}", title=f"{title} (size {g.size})",
              version=version, construction="flat_rows", components=comps, gauge=g.gauge,
              materials=[material] + list(extra_materials), colors={}, risk_class=risk,
              authored="brambleloop", assembly=seams, finished_size_note=size_note,
              designer_notes=designer)
    setattr(cir, FACTS_ATTR, facts)
    return cir


def _risk(g: GradedSize) -> str:
    from .garments import RELAXED_EASE_CM

    return "B" if g.fit.ease("bust") >= RELAXED_EASE_CM else "C"


def _small(g: GradedSize) -> bool:
    return g.body.cm("bust") is not None and g.body_cm("bust") < 70


def _rib_rows(g: GradedSize) -> int:
    return g.rows(RIB_CM_SMALL if _small(g) else RIB_CM, minimum=2)


def _band_rows(g: GradedSize) -> int:
    return g.rows(BAND_CM_SMALL if _small(g) else BAND_CM, minimum=2)


def pick_up_count(edge_cm: float, g: GradedSize) -> int:
    """The stitches a band picks up along an edge `edge_cm` long: the edge at stitch gauge."""
    return max(4, int(round(edge_cm / 10.0 * g.gauge.stitches_per_10cm)))


def button_gaps(stitches: int, buttons: int) -> list[int]:
    """Plain stitches before, between and after `buttons` 2-stitch buttonholes: equal gaps
    between the holes and half a gap at each end of the band (any odd stitch at the start).
    """
    if buttons < 1:
        return [stitches]
    worked = stitches - buttons * BUTTONHOLE_STS
    between = worked // buttons
    rest = worked - (buttons - 1) * between
    if between < 2 or rest < 2:
        raise ShapingRefused(f"{buttons} buttonholes do not fit on a {stitches}-st band")
    return [rest - rest // 2] + [between] * (buttons - 1) + [rest // 2]


# ---- 1. top-down raglan cardigan ------------------------------------------------------------


def raglan_cardigan(g: GradedSize, *, key: str, title: str, family: StitchFamily,
                    material: Material, version: str, buttons: bool = True,
                    neck_of_cross_back: float = 1.0) -> CIR:
    fam = family
    rib = _rib_rows(g)
    band_rows = _band_rows(g)
    band_cm = g.cm_of_rows(band_rows)
    band_sts = g.stitches(band_cm)
    # The bands meet at the centre front, so the body (fronts + back) is the finished chest
    # less one band's depth; the back takes the even half and the fronts share the rest.
    body_sts = g.stitches(g.finished_cm("bust") - band_cm)
    back = _even(body_sts // 2)
    front = (body_sts - back) // 2
    del band_sts
    sleeve_top = _even(g.stitches(g.finished_cm("upper_arm")))
    total = 2 * front + 2 * sleeve_top + back

    length_rows = g.rows(g.finished_cm("back_length"))
    yoke_rows = g.rows(g.finished_cm("armhole_depth"), minimum=4)
    neck_target = g.stitches(g.body_cm("cross_back") * neck_of_cross_back)
    units = max(1, round((total - neck_target) / 8))
    from .garments import MIN_SLEEVE_AT_NECK
    units = min(units, (sleeve_top - MIN_SLEEVE_AT_NECK) // 2, front - 1, (back - 2) // 2,
                2 * yoke_rows)
    f0, s0, b0 = front - units, sleeve_top - 2 * units, back - 2 * units
    doubles = max(0, units - yoke_rows)
    singles = units - 2 * doubles
    if singles + doubles > yoke_rows:
        raise ShapingRefused(f"size {g.size}: the yoke cannot hold {units} raglan units")
    s_events, s_every = uniform(singles, yoke_rows - doubles)
    plan = [2] * doubles
    tail = [0] * (yoke_rows - doubles)
    for k in range(s_events):
        tail[k * s_every] = 1
    plan += tail
    body_rows = length_rows - 1 - yoke_rows - 1
    if body_rows - rib < 2:
        raise ShapingRefused(f"size {g.size}: no body below the underarm")

    yoke = Piece("yoke_and_body", fam, foundation=2 * f0 + 2 * s0 + b0, feature="yoke",
                 direction="top_down", note="worked flat from the neck down; the fronts stay "
                                            "open")
    yoke.even(1, label="set-up row: place the four raglan markers")
    yoke.raglan(plan, f0, s0, b0)
    yoke.divide(sleeve_top, front, back)
    yoke.even(body_rows - rib, label="body")
    yoke.even(rib, loop="back", label="hem band")

    cuff = min(sleeve_top, _even(g.stitches(g.finished_cm("upper_arm") * CUFF_OF_UPPER_ARM)))
    sleeve_rows = g.rows(g.body_cm("arm_length") + g.fit.ease("arm_length"), minimum=6)
    shaping_rows = sleeve_rows - rib - 2
    events, every = uniform((sleeve_top - cuff) // 2, shaping_rows)
    cuff = sleeve_top - 2 * events
    sleeves = []
    for side in ("sleeve_left", "sleeve_right"):
        p = Piece(side, fam, foundation=sleeve_top, resumes=side, feature="sleeve",
                  direction="top_down")
        p.even(1, label="first sleeve row")
        if events:
            p.shape(events, every, grow=False, label="sleeve decreases")
        plain = sleeve_rows - 1 - ((events - 1) * every + 1 if events else 0) - rib
        if plain > 0:
            p.even(plain, label="sleeve")
        p.even(rib, loop="back", label="cuff band")
        sleeves.append(p)

    comp_yoke = yoke.component()
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    probe = CIR(slug="probe", title="probe", version="0", construction="flat_rows",
                components=[comp_yoke] + [p.component() for p in sleeves], gauge=g.gauge,
                materials=[material])
    pr = compile_cir(probe)
    if not pr.ok:
        raise ShapingRefused(f"size {g.size}: the yoke does not compile: "
                             f"{[str(e) for e in pr.errors][:1]}")
    front_edge_cm = build_twin(probe, pr, component=comp_yoke.name).height_cm
    pick = pick_up_count(front_edge_cm, g)
    n_buttons = 0
    if buttons:
        n_buttons = max(3, int(round(front_edge_cm / BUTTON_SPACING_CM)))
    bands = []
    for side, holes in (("band_left", 0), ("band_right", n_buttons)):
        # CLOTHING-E2E: with no buttons (the baby sizes) the bands are plain front bands;
        # labelled "button_band" they read as buttonholes with no buttons
        # (CLOSURE_WITHOUT_BUTTONS) and every baby size was refused at the PDF.
        p = Piece(side, fam, foundation=pick, grain="across",
                  feature="button_band" if n_buttons else "band",
                  direction="side_to_side", foundation_kind="none",
                  note=f"picked up along the {'left' if side == 'band_left' else 'right'} "
                       f"front edge")
        mid = band_rows // 2
        if holes:
            if mid > 0:
                p.even(mid, loop="back", label="band")
            p.buttonhole_row(button_gaps(pick, holes))
            rest = band_rows - mid - 1
            if rest > 0:
                p.even(rest, loop="back", label="band")
        else:
            p.even(band_rows, loop="back", label="band")
        bands.append(p)

    seams = [Seam("mattress", s, s, edge_a="left", edge_b="right",
                  note="close the sleeve seam from cuff to underarm through both loops; "
                       "bury the tails") for s in ("sleeve_left", "sleeve_right")]
    seams += [Seam("pick_up", b.name, "yoke_and_body", edge_a="left",
                   edge_b="left" if b.name == "band_left" else "right",
                   note=f"pick up {pick} sts evenly along the front edge, from hem to neck")
              for b in bands]
    facts = Facts("raglan", pieces={p.name: p.steps for p in [yoke] + sleeves + bands},
                  buttons=n_buttons, rib_rows=rib, band_rows=band_rows, band_cm=band_cm,
                  neck_cm=g.cm_of_stitches(2 * f0 + 2 * s0 + b0),
                  armhole_cm=g.cm_of_rows(yoke_rows + 1),
                  sleeve_top_cm=g.cm_of_stitches(sleeve_top))
    facts.pickups = [{"piece": b.name, "into": "yoke_and_body", "edge_cm": front_edge_cm,
                      "stitches": pick, "rows_along": len(comp_yoke.rows)} for b in bands]
    facts.seams = [{"seam": "front band", "a": b.name, "b": "yoke_and_body",
                    "a_cm": g.cm_of_stitches(pick), "b_cm": front_edge_cm} for b in bands]
    # Buttons are a notion, not a yarn: printed from `Facts.buttons` in the supply list,
    # never a `Material` (yardage and substitution read every material as a yarn).
    extra: list = []
    designer = ("A top-down raglan cardigan worked flat from the neck, with back-loop bands "
                "at the hem and cuffs and picked-up front bands"
                + (f" with {n_buttons} buttonholes." if n_buttons else
                   "; the fronts meet edge to edge, with nothing to fasten."))
    return _cir(g, key=key, title=title, version=version,
                comps=[comp_yoke] + [p.component() for p in sleeves + bands], seams=seams,
                material=material, extra_materials=extra, designer=designer,
                size_note=f"Finished chest {g.cm_of_stitches(2 * front + back) + band_cm:.0f} cm,"
                          f" to fit chest {g.body_cm('bust'):g} cm",
                risk=_risk(g), facts=facts)


# ---- 2. flat one-piece body with built-in sleeves ---------------------------------------------


def one_piece_sweater(g: GradedSize, *, key: str, title: str, family: StitchFamily,
                      material: Material, version: str,
                      neck_of_cross_back: float = NECK_OF_CROSS_BACK) -> CIR:
    fam = family
    rib = _rib_rows(g)
    band_rows = _band_rows(g)
    width = _even(g.stitches(g.finished_cm("bust") / 2.0))
    half_rows = g.rows(g.finished_cm("back_length"))          # hem to shoulder line
    arm_rows = g.rows(g.finished_cm("armhole_depth"), minimum=4)  # underarm to shoulder line
    below = half_rows - arm_rows
    if below - rib < 2:
        raise ShapingRefused(f"size {g.size}: no body below the underarm")
    body_cm = g.cm_of_stitches(width)
    drop_cm = max(0.0, (body_cm - g.body_cm("cross_back")) / 2.0)
    cuff_rib_cm = g.cm_of_rows(rib)
    ext_cm = g.body_cm("arm_length") + g.fit.ease("arm_length") - drop_cm - cuff_rib_cm
    extra = max(2, g.stitches(ext_cm))
    full = width + 2 * extra
    neck = g.stitches(g.body_cm("cross_back") * neck_of_cross_back)
    if (full - neck) % 2:
        neck += 1

    body = Piece("body", fam, foundation=width, feature="body", direction="bottom_up",
                 note="worked in one piece from the front hem, over the shoulders, to the "
                      "back hem; the sleeves are part of it")
    body.even(rib, loop="back", label="front hem band")
    body.even(below - rib, label="front")
    body.chain_on(extra, label="sleeves")
    body.even(arm_rows - 2, label="front and sleeves")
    neck_row = body.neck_bridge(neck)
    # The back mirrors the front row for row about the shoulder line: the front's two
    # chain-on rows (W+X, W+2X) meet the back's two leave rows (W+X, W) one row further from
    # the fold, so the back works one more full-width row and one fewer plain row.
    body.even(arm_rows - 1, label="back and sleeves")
    body.leave(extra, label="end of sleeves")
    body.even(below - rib - 1, label="back")
    body.even(rib, loop="back", label="back hem band")
    comp = body.component()

    # The sleeve's end (cuff edge) is the row ends of the extension: 2*arm_rows rows from the
    # first chained-on row, folded over the shoulder line. Cuffs and neckband are picked up.
    sleeve_rows = 2 * arm_rows + 1           # chain-on rows .. leave rows, inclusive
    first_sleeve = below + 1
    cuff_edge_cm = sleeve_rows * (10.0 / g.gauge.rows_per_10cm)
    cuff_pick = _even(pick_up_count(cuff_edge_cm, g))
    cuffs = Piece("cuff", fam, foundation=cuff_pick, make=2, grain="across", feature="cuff",
                  direction="side_to_side", foundation_kind="none",
                  note="picked up round the end of each sleeve")
    cuffs.even(rib, loop="back", label="cuff band")
    neck_cm = neck * 10.0 / g.gauge.stitches_per_10cm
    nb_pick = _even(pick_up_count(2 * neck_cm, g))
    neckband = Piece("neckband", fam, foundation=nb_pick, feature="band",
                     direction="bottom_up", foundation_kind="none",
                     note="picked up round the neck opening")
    neckband.even(band_rows, loop="back", label="neckband")

    seams = [
        Seam("mattress", "body", "body", edge_a="left", edge_b="left", at_round=1,
             spans_rounds=below + 2, mirrored=True,
             note="fold at the shoulder line; join each side from the hems to the underarm "
                  "and on along the underside of the sleeve to its end, through both loops; "
                  "bury the tails"),
        Seam("pick_up", "cuff", "body", edge_a="left", edge_b="left", at_round=first_sleeve,
             spans_rounds=sleeve_rows, mirrored=True,
             note=f"pick up {cuff_pick} sts evenly round the end of each sleeve"),
        Seam("mattress", "cuff", "cuff", edge_a="top", edge_b="bottom",
             note="close each cuff in line with the sleeve seam"),
        Seam("pick_up", "neckband", "body", edge_a="bottom", edge_b="opening",
             at_round=neck_row, spans_rounds=1,
             note=f"pick up {nb_pick} sts evenly round the neck opening at row {neck_row}"),
        Seam("mattress", "neckband", "neckband", edge_a="left", edge_b="right",
             note="close the neckband at the left shoulder"),
    ]
    facts = Facts("one_piece", pieces={"body": body.steps, "cuff": cuffs.steps,
                                       "neckband": neckband.steps},
                  rib_rows=rib, band_rows=band_rows, band_cm=g.cm_of_rows(band_rows),
                  neck_cm=neck_cm, armhole_cm=g.cm_of_rows(arm_rows),
                  sleeve_top_cm=2 * g.cm_of_rows(arm_rows))
    facts.pickups = [
        {"piece": "cuff", "into": "body", "edge_cm": cuff_edge_cm, "stitches": cuff_pick,
         "rows_along": sleeve_rows},
        {"piece": "neckband", "into": "body", "edge_cm": 2 * neck_cm, "stitches": nb_pick,
         "rows_along": 0}]
    # Front and back halves mirror at the fold: the same rows below the underarm and the
    # same sleeve rows on either side of the shoulder line, so the side seam meets row for row.
    front_rows = neck_row - 1
    back_rows = len(comp.rows) - neck_row
    facts.seams = [{"seam": "side and underarm", "a": "body(front half)", "b": "body(back half)",
                    "a_rows": front_rows, "b_rows": back_rows}]
    return _cir(g, key=key, title=title, version=version,
                comps=[comp, cuffs.component(), neckband.component()], seams=seams,
                material=material, extra_materials=[],
                designer="A one-piece sweater with built-in sleeves, worked flat from the "
                         "front hem over a slash neck to the back hem, with back-loop hem bands and "
                         "picked-up cuffs and neckband.",
                size_note=f"Finished chest {2 * body_cm:.0f} cm, to fit chest "
                          f"{g.body_cm('bust'):g} cm", risk=_risk(g), facts=facts)


# ---- 3. side-to-side vest ---------------------------------------------------------------------


def side_to_side_vest(g: GradedSize, *, key: str, title: str, family: StitchFamily,
                      material: Material, version: str,
                      neck_of_cross_back: float = NECK_OF_CROSS_BACK) -> CIR:
    """Front and back panels worked side to side: the foundation runs hem to shoulder, the
    rows stack across the body, and the first `rib` stitches of every row form the hem rib."""
    fam = family
    rib_cm = RIB_CM_SMALL if _small(g) else RIB_CM
    rib = g.stitches(rib_cm, minimum=2)
    length = g.stitches(g.finished_cm("back_length"))          # foundation: hem to shoulder
    across = g.rows(g.finished_cm("bust") / 2.0)                # rows: side to side
    if across % 2:
        across += 1
    neck_rows = g.rows(g.body_cm("cross_back") * neck_of_cross_back)
    if (across - neck_rows) % 2:
        neck_rows += 1
    shoulder = (across - neck_rows) // 2
    arm = g.stitches(g.finished_cm("armhole_depth"))
    if length - arm - rib < 2:
        raise ShapingRefused(f"size {g.size}: no side seam below the armhole")
    panels = []
    for name in ("back", "front"):
        p = Piece(name, fam, foundation=length, grain="across", feature="panel",
                  direction="side_to_side",
                  note="worked side to side; the foundation runs from hem to shoulder")
        p.even(across, edge_rib=(rib, "start"), label="panel")
        panels.append(p)
    seams = [
        Seam("mattress", "front", "back", edge_a="top", edge_b="top",
             note=f"join the shoulders: {shoulder} rows from each side edge, leaving the "
                  f"centre {neck_rows} rows open for the neck; through both loops"),
        Seam("mattress", "front", "back", edge_a="left", edge_b="left",
             note=f"join the side seams from the hem up {length - arm} sts, leaving the top "
                  f"{arm} sts open for the armhole; both sides"),
    ]
    facts = Facts("side_to_side", pieces={p.name: p.steps for p in panels},
                  rib_rows=rib, neck_cm=g.cm_of_rows(neck_rows),
                  armhole_cm=g.cm_of_stitches(arm))
    facts.seams = [
        {"seam": "shoulder", "a": "front", "b": "back", "a_rows": shoulder, "b_rows": shoulder,
         "a_edge_rows": across, "b_edge_rows": across},
        {"seam": "side", "a": "front", "b": "back", "a_sts": length - arm,
         "b_sts": length - arm, "a_edge_sts": length, "b_edge_sts": length}]
    return _cir(g, key=key, title=title, version=version,
                comps=[p.component() for p in panels], seams=seams, material=material,
                extra_materials=[],
                designer="A boxy vest in two panels worked side to side, with a back-loop "
                         "hem band worked into every row, a slash neck and open armholes.",
                size_note=f"Finished chest {2 * g.cm_of_rows(across):.0f} cm, to fit chest "
                          f"{g.body_cm('bust'):g} cm", risk=_risk(g), facts=facts)


# ---- 4. drop-shoulder panels with seaming -----------------------------------------------------


def drop_shoulder_pullover(g: GradedSize, *, key: str, title: str, family: StitchFamily,
                           material: Material, version: str,
                           neck_of_cross_back: float = NECK_OF_CROSS_BACK) -> CIR:
    fam = family
    rib = _rib_rows(g)
    band_rows = _band_rows(g)
    width = _even(g.stitches(g.finished_cm("bust") / 2.0))
    half_rows = g.rows(g.finished_cm("back_length"))
    neck = g.stitches(g.body_cm("cross_back") * neck_of_cross_back)
    if (width - neck) % 2:
        neck += 1
    body = Piece("body", fam, foundation=width, feature="body", direction="bottom_up",
                 note="worked in one piece from the front hem, over the shoulders, to the "
                      "back hem")
    body.even(rib, loop="back", label="front hem band")
    body.even(half_rows - rib, label="front")
    neck_row = body.neck_bridge(neck)
    body.even(half_rows - rib, label="back")
    body.even(rib, loop="back", label="back hem band")
    comp = body.component()

    top = _even(g.stitches(max(g.finished_cm("upper_arm"), 2 * g.finished_cm("armhole_depth"))))
    cuff = _even(g.stitches(g.finished_cm("upper_arm") * CUFF_OF_UPPER_ARM))
    body_cm = g.cm_of_stitches(width)
    drop_cm = max(0.0, (body_cm - g.body_cm("cross_back")) / 2.0)
    sleeve_rows = g.rows(g.body_cm("arm_length") + g.fit.ease("arm_length") - drop_cm,
                         minimum=rib + 6)
    events, every = uniform((top - cuff) // 2, sleeve_rows - rib - 1)
    cuff = top - 2 * events
    sl = Piece("sleeve", fam, foundation=cuff, make=2, feature="sleeve",
               direction="bottom_up")
    sl.even(rib, loop="back", label="cuff band")
    if events:
        sl.shape(events, every, grow=True, label="sleeve increases")
    plain = sleeve_rows - rib - ((events - 1) * every + 1 if events else 0)
    if plain > 0:
        sl.even(plain, label="sleeve")

    row_cm = 10.0 / g.gauge.rows_per_10cm
    half_cover = max(1, round(g.cm_of_stitches(top) / 2.0 / row_cm))
    first_cover = neck_row - half_cover
    below = first_cover - 1
    neck_cm = neck * 10.0 / g.gauge.stitches_per_10cm
    nb_pick = _even(pick_up_count(2 * neck_cm, g))
    nb = Piece("neckband", fam, foundation=nb_pick, feature="band", direction="bottom_up",
               foundation_kind="none", note="picked up round the neck opening")
    nb.even(band_rows, loop="back", label="neckband")
    seams = [
        Seam("whipstitch", "sleeve", "body", edge_a="top", edge_b="left",
             at_round=first_cover, spans_rounds=2 * half_cover + 1, mirrored=True,
             note="centre the sleeve on the shoulder line; sew through both loops of every "
                  "stitch and bury the tails"),
        Seam("mattress", "body", "body", edge_a="left", edge_b="left", at_round=1,
             spans_rounds=below, mirrored=True,
             note=f"join the front's side to the back's side from the hems to the sleeve, "
                  f"{below} rows each, through both loops; bury the tails"),
        Seam("mattress", "sleeve", "sleeve", edge_a="left", edge_b="right",
             note="close the underarm seam of each sleeve"),
        Seam("pick_up", "neckband", "body", edge_a="bottom", edge_b="opening",
             at_round=neck_row, spans_rounds=1,
             note=f"pick up {nb_pick} sts evenly round the neck opening at row {neck_row}"),
        Seam("mattress", "neckband", "neckband", edge_a="left", edge_b="right",
             note="close the neckband at the left shoulder"),
    ]
    facts = Facts("drop_shoulder", pieces={"body": body.steps, "sleeve": sl.steps,
                                           "neckband": nb.steps},
                  rib_rows=rib, band_rows=band_rows, band_cm=g.cm_of_rows(band_rows),
                  neck_cm=neck_cm, armhole_cm=(2 * half_cover + 1) * row_cm / 2.0,
                  sleeve_top_cm=g.cm_of_stitches(top))
    facts.pickups = [{"piece": "neckband", "into": "body", "edge_cm": 2 * neck_cm,
                      "stitches": nb_pick, "rows_along": 0}]
    facts.seams = [
        {"seam": "sleeve to armhole", "a": "sleeve", "b": "body",
         "a_cm": g.cm_of_stitches(top), "b_cm": (2 * half_cover + 1) * row_cm},
        {"seam": "side", "a": "body(front half)", "b": "body(back half)",
         "a_rows": neck_row - 1, "b_rows": len(comp.rows) - neck_row}]
    return _cir(g, key=key, title=title, version=version,
                comps=[comp, sl.component(), nb.component()], seams=seams,
                material=material, extra_materials=[],
                designer="A drop-shoulder pullover: one body panel worked over the shoulders "
                         "with a slash neck, sleeves sewn on, back-loop bands at the hems "
                         "and cuffs, and a picked-up neckband.",
                size_note=f"Finished chest {2 * body_cm:.0f} cm, to fit chest "
                          f"{g.body_cm('bust'):g} cm", risk=_risk(g), facts=facts)


# ---- what a built garment measures ---------------------------------------------------------


def built_measures(cir: CIR) -> dict[str, float]:
    """Finished chest, length and upper arm of a built garment, from its rows and twin."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin, row_width_cm

    r = compile_cir(cir)
    if not r.ok:
        raise ShapingRefused(f"{cir.slug} does not compile: {[str(e) for e in r.errors][:1]}")
    gauge = cir.gauge
    kind = construction_of(cir) or ""
    first = cir.components[0]
    if kind == "raglan":
        body_row = next(row for row in first.rows if row.skips)
        width = row_width_cm(next(x for x in r.rows if x.component == first.name
                                  and x.index == body_row.index), gauge)[0]
        twin = build_twin(cir, r, component=first.name)
        upper = max(row_width_cm(x, gauge)[0] for x in r.rows if x.component == "sleeve_left")
        # The two front bands meet at the centre front: one band's depth adds to the chest.
        band = build_twin(cir, r, component="band_right").height_cm
        return {"chest": round(width + band, 2), "length": twin.height_cm,
                "upper_arm": upper}
    if kind == "side_to_side":
        t = build_twin(cir, r, component="back")
        return {"chest": 2 * t.height_cm, "length": t.width_cm}
    t = build_twin(cir, r, component="body")
    below = [x for x in r.rows if x.component == "body"]
    chest = 2 * row_width_cm(below[0], gauge)[0]
    out = {"chest": chest, "length": t.height_cm / 2.0}
    if kind == "drop_shoulder":
        s = build_twin(cir, r, component="sleeve")
        out["upper_arm"] = s.width_cm
    else:
        # Built-in sleeve: its circumference is the rows worked at full (sleeve) width,
        # front and back of the fold together.
        full = max(x.stitch_count for x in below)
        n = sum(1 for x in below if x.stitch_count == full)
        out["upper_arm"] = round(n * t.height_cm / len(below), 2)
    return out


# ---- the designs -----------------------------------------------------------------------------

GARMENT_REQUIRES = ("bust", "back_length", "cross_back", "arm_length", "upper_arm",
                    "armhole_depth")
VEST_REQUIRES = ("bust", "back_length", "cross_back", "armhole_depth")


def _gauge(weight: str) -> Gauge:
    from ..creative.prototype import gauge_for

    return gauge_for(weight)


@dataclass(frozen=True)
class GarmentSpec:
    """A garment design: what it is, who it is for, how it is built, and its stated fit."""

    key: str
    title: str
    category: str                 # cardigan | sweater | vest | pullover
    audience: str                 # adult | child | baby
    construction: str             # raglan | one_piece | side_to_side | drop_shoulder
    weight: str
    fibre: str
    fit: str
    ease_cm: tuple[tuple[str, float], ...]
    version: str = "1.0.0"
    buttons: bool = False
    sizes: tuple[str, ...] | None = None
    texture: str = "plain"

    def table(self):
        return {"adult": WOMAN, "child": CHILD, "baby": BABY}[self.audience]


BUILDERS = {"raglan": raglan_cardigan, "one_piece": one_piece_sweater,
            "side_to_side": side_to_side_vest, "drop_shoulder": drop_shoulder_pullover}
MARKER = "products.garment_families"
PRIMITIVES = {
    "raglan": ("cir.graded", "cir.shaping.distribute", "Hold", "Seam", "pick_up"),
    "one_piece": ("cir.graded", "chain_on", "Seam", "pick_up"),
    "side_to_side": ("cir.graded", "side_to_side", "Seam"),
    "drop_shoulder": ("cir.graded", "cir.shaping.taper", "Seam", "pick_up"),
}
PRIMITIVES = {k: v + (f"{MARKER}:{k}",) for k, v in PRIMITIVES.items()}


def construction_of(cir: CIR) -> str | None:
    """Which family construction built this CIR, from its provenance (survives storage)."""
    prov = getattr(cir, "provenance", None)
    for p in (getattr(prov, "primitives_used", None) or ()):
        if str(p).startswith(MARKER + ":"):
            return str(p).split(":", 1)[1]
    return None


def design(spec: GarmentSpec) -> GradedDesign:
    """The graded design a garment spec describes. Every size runs the same builder."""
    fam = StitchFamily("sc", spec.texture)
    gauge = _gauge(spec.weight)
    if spec.construction == "one_piece":
        # The sleeves are chained on, and those chains are worked into as fabric. The design
        # states their gauge as the fabric's: the instructions say to chain loosely (or with
        # a hook one size up) so the chain is as wide as the stitches worked into it.
        import dataclasses
        gauge = dataclasses.replace(gauge, chains_per_10cm=gauge.stitches_per_10cm)
    material = Material(name=f"{spec.weight} {spec.fibre}", yarn_weight=gauge.yarn_weight)
    builder = BUILDERS[spec.construction]
    kw = {"buttons": spec.buttons} if spec.construction == "raglan" else {}

    def template(g):
        return builder(g, key=spec.key, title=spec.title, family=fam, material=material,
                       version=spec.version, **kw)

    d = GradedDesign(key=spec.key, title=spec.title, table=spec.table(), gauge=gauge,
                     fit=FitIntent(dict(spec.ease_cm), character=spec.fit),
                     requires=VEST_REQUIRES if spec.construction == "side_to_side"
                     else GARMENT_REQUIRES,
                     sizes=spec.sizes, primitives=PRIMITIVES[spec.construction],
                     template=template, measure=built_measures)
    d.spec = spec
    return d


def balls_and_yards(metres: float, weight: str) -> dict:
    """The yarn a size needs, from the twin's metres: balls (rounded up) and yards."""
    if weight not in BALLS:
        raise ValueError(f"no stated ball put-up for {weight!r} yarn")
    ball_m, ball_g = BALLS[weight]
    return {"metres": round(metres), "yards": int(math.ceil(metres * YARD_PER_M)),
            "balls": int(math.ceil(metres / ball_m)), "ball_m": ball_m, "ball_g": ball_g,
            "ball_yd": int(round(ball_m * YARD_PER_M))}


def step_signature(cir: CIR) -> tuple:
    """The step kinds of every piece, in order: identical for every size of one design."""
    f = facts_of(cir)
    if f is None:
        return ()
    return tuple((name, tuple((s.kind, s.loop, s.label) for s in steps))
                 for name, steps in f.pieces.items())
