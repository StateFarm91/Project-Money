"""Brambleloop's own garment constructions, as templates over any graded size.

Two constructions, each a function from one resolved size to a whole CIR:

- `drop_shoulder_flat` -- a drop-shoulder pullover. The body is ONE flat panel worked from the
  front hem up to the shoulder line, where a bridged chain opens a slash neck, and down the
  back to the back hem; it folds over the shoulders. Sleeves are worked flat from cuff to
  upper arm with an evenly spaced taper and sewn to the body's side edges, centred on the
  shoulder line. A neckband is sewn round the neck opening.
- `raglan_top_down` -- an open-front raglan cardigan worked flat from the neck down. Raglan
  increases at four lines are spaced evenly through the yoke; at the underarm the sleeve
  stitches go on hold and the body continues over fronts and back; each sleeve resumes its
  held stitches and tapers evenly to the cuff.

Everything a size needs is computed from that size's body (`cir.graded`, sourced from the
Craft Yarn Council standard), the design's stated ease, and the gauge. The shaping is
`cir.shaping`'s; the division is `Hold`/`resumes`; the finishing is `Seam`s that name their
edges, checked by `cir.assembly`. The proportions a body chart does not publish -- how wide
the neck opening is, how much narrower the cuff is than the upper arm -- are stated here as
named design ratios, never presented as measurements.

**No benchmark is a source.** This module does not import `cir.benchmarks` or anything under
`research/`, and `tests/test_garments.py` fails if it ever does; `cir.specification` refuses
any design whose stitch tables contain a benchmark's. The constructions above are generic
crochet techniques written from first principles for this file.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..cir.graded import CHILD, WOMAN, FitIntent, GradedDesign, GradedSize
from ..cir.model import CIR, Component, Gauge, Hold, LoopTarget, Material, Op, Row, Seam
from ..cir.shaping import SHAPING, ShapingRefused, distribute, taper

# Ease at or above this on the chest is a relaxed garment rather than a fitted one; below it
# the design is risk class C and cannot ship without a physical sample (Master Plan s.3).
RELAXED_EASE_CM = 10.0


# The fabrics a template can work, as the loop each row goes into: (even rows, odd rows).
# Only loop targets, because the stitch registry, the writer ("in back loop of next 12 sts")
# and the reverse compiler already round-trip them; no new stitch is invented for texture.
#   plain     both loops every row: a flat, even fabric
#   ridged    back loop on alternate rows: a horizontal ridge every second row
#   ribbed    back loop every row: the deep crochet rib, ridges on both faces
#   furrowed  front loop on alternate rows: a softer ridge that sits on the other face
TEXTURES: dict[str, tuple[LoopTarget, LoopTarget]] = {
    "plain": ("both", "both"),
    "ridged": ("back", "both"),
    "ribbed": ("back", "back"),
    "furrowed": ("front", "both"),
}


@dataclass(frozen=True)
class ColourPlan:
    """Which colour each row is worked in, as a rule rather than a list.

    `solid` is one colour. `stripes` cycles the colours in order, one band of `band_cm` each,
    counted from where each piece starts (a raglan's sleeves continue the yoke's count, so
    stripes meet at the underarm). `blocks` splits each piece into as many equal-height blocks
    as there are colours, in order from where the piece starts.
    """

    colours: tuple[tuple[str, str], ...]          # (name, hex), in order
    kind: str = "solid"                           # "solid" | "stripes" | "blocks"
    band_cm: float = 0.0

    def __post_init__(self) -> None:
        if not self.colours:
            raise ShapingRefused("a colour plan needs at least one colour")
        if self.kind not in ("solid", "stripes", "blocks"):
            raise ShapingRefused(f"unknown colour plan {self.kind!r}")
        if self.kind == "stripes" and self.band_cm <= 0:
            raise ShapingRefused("stripes need a band height")
        if self.kind != "solid" and len(self.colours) < 2:
            raise ShapingRefused(f"{self.kind} need at least two colours")

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(n for n, _ in self.colours)

    def at(self, g: "GradedSize", position: int, length: int) -> str | None:
        """The colour of the row `position` (1-based) rows into a piece `length` rows long."""
        if self.kind == "solid":
            return None
        n = len(self.colours)
        if self.kind == "stripes":
            band = g.rows(self.band_cm, minimum=1)
            return self.names[((position - 1) // band) % n]
        block = min(n - 1, (position - 1) * n // max(1, length))
        return self.names[block]


def _paint(rows, plan: "ColourPlan | None", g, positions, length: int) -> None:
    if plan is None or plan.kind == "solid":
        return
    for row, pos in zip(rows, positions):
        row.color = plan.at(g, pos, length)


def _materials(material: Material, plan: "ColourPlan | None") -> tuple[list, dict]:
    if plan is None:
        return [material], {}
    return ([Material(name=material.name, yarn_weight=material.yarn_weight, color_id=name)
             for name in plan.names], dict(plan.colours))


@dataclass(frozen=True)
class StitchFamily:
    """The fabric: its stitch, and whether alternate rows are worked in the back loop."""

    stitch: str = "sc"
    texture: str = "plain"   # one of TEXTURES

    def __post_init__(self) -> None:
        if self.stitch not in SHAPING or SHAPING[self.stitch][1] is None:
            raise ShapingRefused(f"{self.stitch} cannot both increase and decrease here")
        if self.texture not in TEXTURES:
            raise ShapingRefused(f"unknown texture {self.texture!r}")

    @property
    def turning_chain(self) -> int:
        return {"sc": 1, "hdc": 2, "dc": 3}[self.stitch]

    @property
    def inc(self) -> str:
        return SHAPING[self.stitch][0]

    def loop(self, row_index: int) -> LoopTarget:
        return TEXTURES[self.texture][row_index % 2]

    def loops(self, first: int, count: int) -> dict[int, LoopTarget]:
        return {i: self.loop(i) for i in range(first, first + count)}


def _risk(g: GradedSize) -> str:
    return "B" if g.fit.ease("bust") >= RELAXED_EASE_CM else "C"


def _plain(index: int, n: int, family: StitchFamily, **kw) -> Row:
    return Row(index=index, ops=[Op(family.stitch, n, loop=family.loop(index))],
               declared_count=n, turning_chain=family.turning_chain, **kw)


def _even(n: int) -> int:
    return n if n % 2 == 0 else n + 1


# ---- drop shoulder -------------------------------------------------------------------------

# Design ratios, not body measurements. The slash neck spans this fraction of the shoulder
# width (so the opening's perimeter clears a head), and the cuff is this fraction of the
# finished upper arm.
NECK_OF_CROSS_BACK = 0.8
CUFF_OF_UPPER_ARM = 0.75
NECKBAND_CM = 3.0


def drop_shoulder_flat(g: GradedSize, *, key: str, title: str, family: StitchFamily,
                       material: Material, length_ratio: float = 1.0,
                       neck_of_cross_back: float = NECK_OF_CROSS_BACK,
                       colours: ColourPlan | None = None, version: str = "1.0.0") -> CIR:
    gauge = g.gauge
    fam = family
    tc = fam.turning_chain

    width = _even(g.stitches(g.finished_cm("bust") / 2.0))          # front = back
    neck = g.stitches(g.body_cm("cross_back") * neck_of_cross_back)
    if (width - neck) % 2:
        neck += 1
    side = (width - neck) // 2
    if side < 2:
        raise ShapingRefused(f"size {g.size}: the neck would leave no shoulder")
    half_rows = g.rows(g.finished_cm("back_length") * length_ratio)  # hem to shoulder line

    # Body: front hem -> shoulder line (neck row bridged) -> back hem.
    body_rows = [_plain(i, width, fam) for i in range(1, half_rows + 1)]
    neck_row = half_rows + 1
    body_rows.append(Row(
        index=neck_row,
        ops=[Op(fam.stitch, side, loop=fam.loop(neck_row)), Op("ch", neck, spans=neck),
             Op("sk", neck), Op(fam.stitch, side, loop=fam.loop(neck_row))],
        declared_count=width, turning_chain=tc,
        note="shoulder line: the chain bridges the neck opening"))
    body_rows += [_plain(i, width, fam) for i in range(neck_row + 1, neck_row + half_rows + 1)]
    # Colour counts from each hem, so the front and back match at the side seams.
    _paint(body_rows, colours, g,
           [i if i <= neck_row else 2 * neck_row - i for i in range(1, len(body_rows) + 1)],
           neck_row)
    body = Component("body", "flat_rows", foundation=width, rows=body_rows, grain="up",
                     note="worked in one piece from the front hem, over the shoulders, to "
                          "the back hem")

    # Sleeve: cuff -> upper arm, tapered evenly. Its top edge is sewn to the body's side,
    # centred on the shoulder line, so its width sets how many body rows it covers.
    top_cm = max(g.finished_cm("upper_arm"), 2 * g.finished_cm("armhole_depth"))
    top = _even(g.stitches(top_cm))
    cuff = _even(g.stitches(g.finished_cm("upper_arm") * CUFF_OF_UPPER_ARM))
    body_cm = g.cm_of_stitches(width)
    drop_cm = max(0.0, (body_cm - g.body_cm("cross_back")) / 2.0)
    sleeve_rows = g.rows(g.body_cm("arm_length") + g.fit.ease("arm_length") - drop_cm,
                         minimum=4)
    sleeve_taper = taper(cuff, top, sleeve_rows, edge="both", stitch=fam.stitch,
                         turning_chain=tc, loops_by_row=fam.loops(1, sleeve_rows))
    sleeve_rows_list = list(sleeve_taper.rows)
    _paint(sleeve_rows_list, colours, g, range(1, sleeve_rows + 1), sleeve_rows)
    sleeve = Component("sleeve", "flat_rows", foundation=cuff, make=2,
                       rows=sleeve_rows_list, grain="up")

    # Neckband: a strip as long as the neck opening's perimeter, closed into a ring. Worked
    # in the first colour: a band is a frame, not part of the stripe sequence.
    band_len = _even(2 * neck)
    band_rows = g.rows(NECKBAND_CM, minimum=2)
    band_colour = colours.names[0] if colours and colours.kind != "solid" else None
    band = Component("neckband", "flat_rows", foundation=band_len, grain="up",
                     rows=[_plain(i, band_len, fam, color=band_colour)
                           for i in range(1, band_rows + 1)])

    # Rows of the body the sleeve top covers: half the sleeve top either side of the
    # shoulder line, in whole rows.
    half_cover = max(1, round(g.cm_of_stitches(top) / 2.0 / (10.0 / gauge.rows_per_10cm)))
    first_cover = neck_row - half_cover + 1
    below = first_cover - 1   # body rows under the sleeve on the front half

    seams = [
        Seam("whipstitch", "sleeve", "body", edge_a="top", edge_b="left",
             at_round=first_cover, spans_rounds=2 * half_cover, mirrored=True,
             note="centre the sleeve on the shoulder line"),
        Seam("mattress", "body", "body", edge_a="left", edge_b="left", at_round=1,
             spans_rounds=below, mirrored=True,
             note=f"join the front's side to the back's side from the hems to the sleeve, "
                  f"{below} rows each"),
        Seam("mattress", "sleeve", "sleeve", edge_a="left", edge_b="right",
             note="close the underarm seam of each sleeve"),
        Seam("mattress", "neckband", "neckband", edge_a="left", edge_b="right",
             note="close the band into a ring"),
        # Placed at the shoulder-line row, which is where the neck opening is: the join is
        # located, not left to the picture (certification audit C-9).
        Seam("whipstitch", "neckband", "body", edge_a="bottom", edge_b="opening",
             at_round=neck_row, spans_rounds=1,
             note=f"ease the ring round the neck opening at row {neck_row}, band seam at "
                  f"the back"),
    ]
    materials, palette = _materials(material, colours)
    return CIR(
        slug=f"{key}-{g.size.lower()}", title=f"{title} (size {g.size})", version=version,
        construction="flat_rows", components=[body, sleeve, band],
        gauge=gauge, materials=materials, colors=palette, risk_class=_risk(g),
        authored="brambleloop", assembly=seams,
        finished_size_note=(f"Finished chest {2 * body_cm:.0f} cm, length "
                            f"{g.cm_of_rows(half_rows):.0f} cm, to fit chest "
                            f"{g.body_cm('bust'):g} cm"),
        designer_notes="A drop-shoulder pullover in one body piece with a slash neck.")


# ---- raglan, top down ----------------------------------------------------------------------
#
# The neck is a design ratio of the shoulders. CYC publishes no neck circumference (it is
# UNSOURCED in both tables), so the whole neck edge of this open-front cardigan -- both
# fronts, both sleeve tops and the back neck -- is aimed at `NECK_EDGE_OF_CROSS_BACK` times
# the body's cross-back, never at a guessed neck measurement.
#
# The raglan then has to grow from that neck to the chest and both upper arms by the
# underarm. Every increase unit is the standard raglan increase: one stitch either side of
# each of the four raglan lines, 8 per unit (each front +1, each sleeve +2, the back +2).
# The units needed are (underarm total - neck) / 8, and they are spread over the yoke rows
# by `distribute`: fewer units than rows gives every-other-row (or sparser) increases, more
# units than rows gives every-row increases with some rows working two (or more) either side
# of each line -- so the count lands exactly on the underarm total whatever the row gauge.
# (The first version allowed at most one unit per row and capped the units at the yoke
# rows; with tall dc rows the yoke could not grow, and it started with a neck of 0.6-0.88
# of the chest -- certification audit C-7.)
#
# Where the upper arm is large relative to the chest, the sleeve top cannot shrink below
# `MIN_SLEEVE_AT_NECK` stitches at the neck; the units are capped there and the neck ends up
# wider than the target. `cir.specification.refuse_an_implausible_garment` then decides
# whether that neck still fits a body, and refuses it if not.
NECK_EDGE_OF_CROSS_BACK = 1.0
MIN_SLEEVE_AT_NECK = 2
# The sleeve top's "saddle" at the neck, as a ratio of the cross-back: how much of the neck
# edge the sleeves carry. With the standard symmetric increases the neck edge is
# 2 x (back - sleeve top) + 4 x saddle at the underarm's widths, so this is also what sets
# the neck's width wherever the target above cannot be reached; it is how a neckline choice
# (close / crew / wide) reaches every size.
SLEEVE_AT_NECK_OF_CROSS_BACK = 0.06
MIN_SLEEVE_TOP = MIN_SLEEVE_AT_NECK            # the name the first version used


def _raglan_row(index: int, f: int, s: int, b: int, fam: StitchFamily, m: int = 1) -> Row:
    """One increase row: `m` increases either side of each of the four raglan lines."""
    lp = fam.loop(index)
    st, inc = fam.stitch, fam.inc
    plan = [(st, f - m), (inc, 2 * m), (st, s - 2 * m), (inc, 2 * m), (st, b - 2 * m),
            (inc, 2 * m), (st, s - 2 * m), (inc, 2 * m), (st, f - m)]
    ops: list[Op] = []
    for code, n in plan:
        if n <= 0:
            continue
        if ops and ops[-1].stitch == code:     # adjacent increases read as one run
            ops[-1] = Op(code, ops[-1].count + n, loop=lp)
        else:
            ops.append(Op(code, n, loop=lp))
    total = 2 * f + 2 * s + b + 8 * m
    note = None if m == 1 else f"{m} increases either side of each raglan line"
    return Row(index=index, ops=ops, declared_count=total, turning_chain=fam.turning_chain,
               note=note)


def _yoke_plan(units: int, rows: int, f0: int, s0: int, b0: int) -> list[int] | None:
    """Units per yoke row, spread evenly, that every row has the stitches to work."""
    def fits(plan):
        f, s, b = f0, s0, b0
        for m in plan:
            if m and (f < m or s < 2 * m or b < 2 * m):
                return False
            f, s, b = f + m, s + 2 * m, b + 2 * m
        return True
    even = distribute(units, rows)
    if fits(even):
        return even
    later = sorted(even)          # the heavier rows moved down, where the sections are wider
    return later if fits(later) else None


def raglan_top_down(g: GradedSize, *, key: str, title: str, family: StitchFamily,
                    material: Material, length_ratio: float = 1.0,
                    neck_of_cross_back: float = NECK_EDGE_OF_CROSS_BACK,
                    sleeve_at_neck_of_cross_back: float = SLEEVE_AT_NECK_OF_CROSS_BACK,
                    colours: ColourPlan | None = None, version: str = "1.0.0") -> CIR:
    fam = family
    back = _even(g.stitches(g.finished_cm("bust") / 2.0))
    front = back // 2
    sleeve_top = _even(g.stitches(g.finished_cm("upper_arm")))
    total = 2 * front + 2 * sleeve_top + back

    # Rows: the whole length is rounded once and the yoke and body are derived from it, so
    # the built length never falls between sizes (audit C-10: rounding the yoke and the body
    # separately lost a row from 4X to 5X).
    length_rows = g.rows(g.finished_cm("back_length") * length_ratio)
    yoke_rows = g.rows(g.finished_cm("armhole_depth"), minimum=4)
    body_rows_n = length_rows - yoke_rows
    if body_rows_n < 4:
        raise ShapingRefused(f"size {g.size}: the body below the underarm would be "
                             f"{body_rows_n} rows")

    neck_target = g.stitches(g.body_cm("cross_back") * neck_of_cross_back)
    units = max(0, round((total - neck_target) / 8))
    saddle = max(MIN_SLEEVE_AT_NECK,
                 g.stitches(g.body_cm("cross_back") * sleeve_at_neck_of_cross_back))
    units = min(units, (sleeve_top - saddle) // 2, front - 1, (back - 2) // 2)
    if units < 1:
        raise ShapingRefused(f"size {g.size}: no room for raglan shaping")
    f0, s0, b0 = front - units, sleeve_top - 2 * units, back - 2 * units
    plan = _yoke_plan(units, yoke_rows, f0, s0, b0)
    if plan is None:
        raise ShapingRefused(f"size {g.size}: {units} raglan increase units do not fit in "
                             f"{yoke_rows} yoke rows")

    rows: list[Row] = []
    f, s, b = f0, s0, b0
    for offset, m in enumerate(plan):
        index = 1 + offset
        if m:
            rows.append(_raglan_row(index, f, s, b, fam, m))
            f, s, b = f + m, s + 2 * m, b + 2 * m
        else:
            rows.append(_plain(index, 2 * f + 2 * s + b, fam))
    assert (f, s, b) == (front, sleeve_top, back)
    yoke_last = rows[-1].index

    holds = [Hold("sleeve_left", at_row=yoke_last, count=sleeve_top, from_stitch=front,
                  note="the body joins front to back under the arm"),
             Hold("sleeve_right", at_row=yoke_last, count=sleeve_top,
                  from_stitch=front + sleeve_top + back)]
    body_width = 2 * front + back
    first_body = yoke_last + 1
    rows.append(Row(index=first_body,
                    ops=[Op(fam.stitch, body_width, loop=fam.loop(first_body))],
                    declared_count=body_width, turning_chain=fam.turning_chain,
                    skips=2 * sleeve_top, note="fronts and back joined under each arm"))
    rows += [_plain(i, body_width, fam)
             for i in range(first_body + 1, first_body + body_rows_n)]
    _paint(rows, colours, g, range(1, len(rows) + 1), len(rows))
    yoke = Component("yoke_and_body", "flat_rows", foundation=2 * f0 + 2 * s0 + b0,
                     rows=rows, holds=holds, grain="up",
                     note="worked flat from the neck down; the fronts stay open")

    cuff = _even(g.stitches(g.finished_cm("upper_arm") * CUFF_OF_UPPER_ARM))
    cuff = min(cuff, sleeve_top)
    sleeve_rows = g.rows(g.body_cm("arm_length") + g.fit.ease("arm_length"), minimum=4)
    sleeves = []
    for name in ("sleeve_left", "sleeve_right"):
        t = taper(sleeve_top, cuff, sleeve_rows, edge="both", stitch=fam.stitch,
                  turning_chain=fam.turning_chain, loops_by_row=fam.loops(1, sleeve_rows))
        srows = list(t.rows)
        # Stripes continue the yoke's count from the underarm; blocks divide the sleeve.
        if colours is not None and colours.kind == "stripes":
            _paint(srows, colours, g, range(yoke_last + 1, yoke_last + 1 + sleeve_rows),
                   sleeve_rows)
        else:
            _paint(srows, colours, g, range(1, sleeve_rows + 1), sleeve_rows)
        sleeves.append(Component(name, "flat_rows", foundation=0, foundation_kind="none",
                                 resumes=name, rows=srows, grain="up"))
    seams = [Seam("mattress", name, name, edge_a="left", edge_b="right",
                  note="close the sleeve seam from cuff to underarm")
             for name in ("sleeve_left", "sleeve_right")]
    materials, palette = _materials(material, colours)
    return CIR(
        slug=f"{key}-{g.size.lower()}", title=f"{title} (size {g.size})", version=version,
        construction="flat_rows", components=[yoke] + sleeves, gauge=g.gauge,
        materials=materials, colors=palette, risk_class=_risk(g), authored="brambleloop",
        assembly=seams,
        finished_size_note=(f"Finished chest {g.cm_of_stitches(2 * back):.0f} cm, to fit "
                            f"chest {g.body_cm('bust'):g} cm"),
        designer_notes="An open-front raglan cardigan worked flat from the neck down.")


# ---- what the built garment measures -------------------------------------------------------

def built_measures(cir: CIR) -> dict[str, float]:
    """The finished chest, length, armhole depth and upper arm of a built garment, in cm,
    measured from its compiled rows and digital twin rather than from its size table."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin, row_width_cm

    r = compile_cir(cir)
    if not r.ok:
        raise ShapingRefused(f"{cir.slug} does not compile: {[str(e) for e in r.errors][:1]}")
    gauge = cir.gauge
    first = cir.components[0]
    if first.holds:                                   # top-down yoke
        first_body = next(row for row in first.rows if row.skips)
        body = [x for x in r.rows if x.component == first.name
                and x.index >= first_body.index]
        twin = build_twin(cir, r, component=first.name)
        armhole = (twin.row_top_cm[first_body.index - 1] if twin.row_top_cm else
                   (first_body.index - 1) / gauge.rows_per_10cm * 10)
        sleeve = cir.components[1].name
        upper = max(row_width_cm(x, gauge)[0] for x in r.rows if x.component == sleeve)
        return {"chest": row_width_cm(body[0], gauge)[0], "length": twin.height_cm,
                "armhole": armhole, "upper_arm": upper}
    body = build_twin(cir, r, component="body")
    sleeve = build_twin(cir, r, component="sleeve")
    return {"chest": 2 * body.width_cm, "length": body.height_cm / 2.0,
            "armhole": sleeve.width_cm / 2.0, "upper_arm": sleeve.width_cm}


# ---- the two demonstration designs ----------------------------------------------------------

DROP_SHOULDER_REQUIRES = ("bust", "back_length", "cross_back", "arm_length", "upper_arm",
                          "armhole_depth")
RAGLAN_REQUIRES = ("bust", "back_length", "cross_back", "arm_length", "upper_arm",
                   "armhole_depth")


HARBOUR_VERSION = "1.1.0"


def harbour_pullover() -> GradedDesign:
    """An adult relaxed drop-shoulder pullover in ridged single crochet, CYC woman XS-5X."""
    family = StitchFamily("sc", "ridged")
    # Derived from the declared worsted's published band (D-FB-6): a typed 16 sc/10cm is a
    # fabric worsted cannot make. Grading recomputes every count from it.
    from ..creative.prototype import gauge_for
    gauge = gauge_for("worsted")
    material = Material(name="worsted wool", yarn_weight="worsted")
    key, title = "harbour-drop-shoulder-pullover", "Harbour Drop-Shoulder Pullover"
    # Patterns are software releases: the derived gauge changed every size's counts, so the
    # released version moved 1.0.0 -> 1.1.0 (pinned in tests/data/release_fingerprints.tsv).
    version = HARBOUR_VERSION
    return GradedDesign(
        key=key, title=title, table=WOMAN, gauge=gauge,
        fit=FitIntent({"bust": 20, "back_length": 15, "armhole_depth": 4, "upper_arm": 8}),
        requires=DROP_SHOULDER_REQUIRES,
        primitives=("cir.graded", "cir.shaping.taper", "cir.assembly", "Seam"),
        measure=built_measures,
        template=lambda g: drop_shoulder_flat(g, key=key, title=title, family=family,
                                              material=material, version=version))


def pebble_cardigan() -> GradedDesign:
    """A child's open-front raglan cardigan in double crochet, CYC child/youth 2-16."""
    family = StitchFamily("dc", "plain")
    gauge = Gauge(stitches_per_10cm=14, rows_per_10cm=8, stitch_type="dc", hook_mm=4.5,
                  yarn_weight="dk")
    material = Material(name="dk cotton", yarn_weight="dk")
    key, title = "pebble-raglan-cardigan", "Pebble Raglan Cardigan"
    return GradedDesign(
        key=key, title=title, table=CHILD, gauge=gauge,
        fit=FitIntent({"bust": 10, "back_length": 6, "armhole_depth": 2, "upper_arm": 5}),
        requires=RAGLAN_REQUIRES,
        primitives=("cir.graded", "cir.shaping.taper", "cir.shaping.distribute", "Hold",
                    "Seam"),
        measure=built_measures,
        template=lambda g: raglan_top_down(g, key=key, title=title, family=family,
                                           material=material))


DESIGNS = {"harbour-drop-shoulder-pullover": harbour_pullover,
           "pebble-raglan-cardigan": pebble_cardigan}


def every_graded_cir() -> dict[str, CIR]:
    """Every sourced size of every garment design, keyed by slug."""
    out: dict[str, CIR] = {}
    for make in DESIGNS.values():
        for cir in make().build_all().values():
            out[cir.slug] = cir
    return out
