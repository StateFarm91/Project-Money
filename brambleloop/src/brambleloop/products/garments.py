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


@dataclass(frozen=True)
class StitchFamily:
    """The fabric: its stitch, and whether alternate rows are worked in the back loop."""

    stitch: str = "sc"
    texture: str = "plain"   # "plain" | "ridged"

    def __post_init__(self) -> None:
        if self.stitch not in SHAPING or SHAPING[self.stitch][1] is None:
            raise ShapingRefused(f"{self.stitch} cannot both increase and decrease here")
        if self.texture not in ("plain", "ridged"):
            raise ShapingRefused(f"unknown texture {self.texture!r}")

    @property
    def turning_chain(self) -> int:
        return {"sc": 1, "hdc": 2, "dc": 3}[self.stitch]

    @property
    def inc(self) -> str:
        return SHAPING[self.stitch][0]

    def loop(self, row_index: int) -> LoopTarget:
        return "back" if self.texture == "ridged" and row_index % 2 == 0 else "both"

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
                       material: Material) -> CIR:
    gauge = g.gauge
    fam = family
    tc = fam.turning_chain

    width = _even(g.stitches(g.finished_cm("bust") / 2.0))          # front = back
    neck = g.stitches(g.body_cm("cross_back") * NECK_OF_CROSS_BACK)
    if (width - neck) % 2:
        neck += 1
    side = (width - neck) // 2
    if side < 2:
        raise ShapingRefused(f"size {g.size}: the neck would leave no shoulder")
    half_rows = g.rows(g.finished_cm("back_length"))                 # hem to shoulder line

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
    sleeve = Component("sleeve", "flat_rows", foundation=cuff, make=2,
                       rows=list(sleeve_taper.rows), grain="up")

    # Neckband: a strip as long as the neck opening's perimeter, closed into a ring.
    band_len = _even(2 * neck)
    band_rows = g.rows(NECKBAND_CM, minimum=2)
    band = Component("neckband", "flat_rows", foundation=band_len, grain="up",
                     rows=[_plain(i, band_len, fam) for i in range(1, band_rows + 1)])

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
        Seam("whipstitch", "neckband", "body", edge_a="bottom", edge_b="opening",
             note="ease the ring round the neck opening, band seam at the back"),
    ]
    return CIR(
        slug=f"{key}-{g.size.lower()}", title=f"{title} (size {g.size})", version="1.0.0",
        construction="flat_rows", components=[body, sleeve, band],
        gauge=gauge, materials=[material], risk_class=_risk(g), authored="brambleloop",
        assembly=seams,
        finished_size_note=(f"Finished chest {2 * body_cm:.0f} cm, length "
                            f"{g.cm_of_rows(half_rows):.0f} cm, to fit chest "
                            f"{g.body_cm('bust'):g} cm"),
        designer_notes="A drop-shoulder pullover in one body piece with a slash neck.")


# ---- raglan, top down ----------------------------------------------------------------------

BACK_NECK_OF_CROSS_BACK = 0.45
MIN_SLEEVE_TOP = 2


def _raglan_row(index: int, f: int, s: int, b: int, fam: StitchFamily) -> Row:
    """One increase row: one increase either side of each of the four raglan lines."""
    lp = fam.loop(index)
    st, inc = fam.stitch, fam.inc
    plan = [(st, f - 1), (inc, 2), (st, s - 2), (inc, 2), (st, b - 2), (inc, 2),
            (st, s - 2), (inc, 2), (st, f - 1)]
    ops: list[Op] = []
    for code, n in plan:
        if n <= 0:
            continue
        if ops and ops[-1].stitch == code:     # adjacent increases read as one run
            ops[-1] = Op(code, ops[-1].count + n, loop=lp)
        else:
            ops.append(Op(code, n, loop=lp))
    total = 2 * f + 2 * s + b + 8
    return Row(index=index, ops=ops, declared_count=total, turning_chain=fam.turning_chain)


def raglan_top_down(g: GradedSize, *, key: str, title: str, family: StitchFamily,
                    material: Material) -> CIR:
    fam = family
    back = _even(g.stitches(g.finished_cm("bust") / 2.0))
    front = back // 2
    sleeve_top = _even(g.stitches(g.finished_cm("upper_arm")))
    yoke_rows = g.rows(g.finished_cm("armhole_depth"), minimum=4)

    back_neck = g.stitches(g.body_cm("cross_back") * BACK_NECK_OF_CROSS_BACK)
    k = max(1, (back - back_neck) // 2)                  # raglan increase rows
    k = min(k, (sleeve_top - MIN_SLEEVE_TOP) // 2, front - 1, yoke_rows)
    if k < 1:
        raise ShapingRefused(f"size {g.size}: no room for raglan shaping")
    f0, s0, b0 = front - k, sleeve_top - 2 * k, back - 2 * k
    if s0 < 2 or b0 < 2 or f0 < 1:
        raise ShapingRefused(f"size {g.size}: the neck would start with an empty section")

    rows: list[Row] = []
    f, s, b = f0, s0, b0
    for offset, events in enumerate(distribute(k, yoke_rows)):
        index = 1 + offset
        if events:
            rows.append(_raglan_row(index, f, s, b, fam))
            f, s, b = f + 1, s + 2, b + 2
        else:
            rows.append(_plain(index, 2 * f + 2 * s + b, fam))
    assert (f, s, b) == (front, sleeve_top, back)
    yoke_last = rows[-1].index

    holds = [Hold("sleeve_left", at_row=yoke_last, count=sleeve_top, from_stitch=front,
                  note="the body joins front to back under the arm"),
             Hold("sleeve_right", at_row=yoke_last, count=sleeve_top,
                  from_stitch=front + sleeve_top + back)]
    body_width = 2 * front + back
    body_rows_n = g.rows(g.finished_cm("back_length") - g.finished_cm("armhole_depth"),
                         minimum=4)
    first_body = yoke_last + 1
    rows.append(Row(index=first_body,
                    ops=[Op(fam.stitch, body_width, loop=fam.loop(first_body))],
                    declared_count=body_width, turning_chain=fam.turning_chain,
                    skips=2 * sleeve_top, note="fronts and back joined under each arm"))
    rows += [_plain(i, body_width, fam)
             for i in range(first_body + 1, first_body + body_rows_n)]
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
        sleeves.append(Component(name, "flat_rows", foundation=0, foundation_kind="none",
                                 resumes=name, rows=list(t.rows), grain="up"))
    seams = [Seam("mattress", name, name, edge_a="left", edge_b="right",
                  note="close the sleeve seam from cuff to underarm")
             for name in ("sleeve_left", "sleeve_right")]
    return CIR(
        slug=f"{key}-{g.size.lower()}", title=f"{title} (size {g.size})", version="1.0.0",
        construction="flat_rows", components=[yoke] + sleeves, gauge=g.gauge,
        materials=[material], risk_class=_risk(g), authored="brambleloop", assembly=seams,
        finished_size_note=(f"Finished chest {g.cm_of_stitches(2 * back):.0f} cm, to fit "
                            f"chest {g.body_cm('bust'):g} cm"),
        designer_notes="An open-front raglan cardigan worked flat from the neck down.")


# ---- the two demonstration designs ----------------------------------------------------------

DROP_SHOULDER_REQUIRES = ("bust", "back_length", "cross_back", "arm_length", "upper_arm",
                          "armhole_depth")
RAGLAN_REQUIRES = ("bust", "back_length", "cross_back", "arm_length", "upper_arm",
                   "armhole_depth")


def harbour_pullover() -> GradedDesign:
    """An adult relaxed drop-shoulder pullover in ridged single crochet, CYC woman XS-5X."""
    family = StitchFamily("sc", "ridged")
    gauge = Gauge(stitches_per_10cm=16, rows_per_10cm=18, stitch_type="sc", hook_mm=5.5,
                  yarn_weight="worsted")
    material = Material(name="worsted wool", yarn_weight="worsted")
    key, title = "harbour-drop-shoulder-pullover", "Harbour Drop-Shoulder Pullover"
    return GradedDesign(
        key=key, title=title, table=WOMAN, gauge=gauge,
        fit=FitIntent({"bust": 20, "back_length": 15, "armhole_depth": 4, "upper_arm": 8}),
        requires=DROP_SHOULDER_REQUIRES,
        primitives=("cir.graded", "cir.shaping.taper", "cir.assembly", "Seam"),
        template=lambda g: drop_shoulder_flat(g, key=key, title=title, family=family,
                                              material=material))


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
