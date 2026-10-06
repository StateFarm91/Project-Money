"""Pattern and image truth findings PT-07..PT-10 (independent audit 2, 2026-10-06).

PT-07  yardage counted each increase twice (coaster 41.0 m stated, 28.8 m by its own model).
PT-08  a row was as tall as its tallest stitch, so a sc row with one dc in nine was a dc row.
PT-09  Cloudline alternated colour every turned row while telling the maker to carry the
       resting colour up the side, which turned rows make impossible.
PT-10  stacked-increase pieces are hexagons; sizes are quoted across the points and the flats.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir import stitches  # noqa: E402
from brambleloop.cir.colour_changes import analyse, instruction  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.geometry import row_height_cm  # noqa: E402
from brambleloop.cir.model import CIR, Component, Gauge, Op, Row  # noqa: E402
from brambleloop.cir.twin import _YARN_FACTOR, build_twin, size_statement  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.products import builder, launch0, vessels  # noqa: E402


def _twin(build):
    cir = launch0.cir_for(build)
    return cir, build_twin(cir, compile_cir(cir))


# ---- PT-07 ---------------------------------------------------------------------------------

def _independent_yardage(cir: CIR) -> float:
    """Count every stitch exactly once: an `inc` is two sc, nothing more."""
    result = compile_cir(cir)
    w = 10.0 / cir.gauge.stitches_per_10cm
    total = 0.0
    for comp in cir.components:
        for r in [x for x in result.rows if x.component == comp.name]:
            for op in r.ops:
                if op.stitch == "inc":
                    total += 2 * _YARN_FACTOR["sc"] * w * op.count
                else:
                    total += _YARN_FACTOR.get(op.stitch, 3.0) * w * op.count
            total += _YARN_FACTOR["ch"] * w * (r.turning_chain or 0)
        total *= comp.make
    return total / 100.0


def test_yardage_counts_each_increase_once():
    for build in ("hexagon_coasters", "basket_small", "basket_medium", "basket_large"):
        cir, t = _twin(build)
        stated = sum(t.yarn_metres_by_color.values())
        assert abs(stated - _independent_yardage(cir)) < 0.3, (build, stated)
    _cir, coaster = _twin("hexagon_coasters")
    total = sum(coaster.yarn_metres_by_color.values())
    assert 28.0 <= total <= 29.5, total          # was 41.0 (43 % over)
    _cir, small = _twin("basket_small")
    assert 51.5 <= sum(small.yarn_metres_by_color.values()) <= 52.5   # was 57.4


def test_composite_stitch_factors_are_per_instance():
    """inc = 2 sc, dc_inc = 2 dc, hdc3 = 3 hdc, cable2x2 = 4 dc-ish: per op, not per stitch."""
    assert _YARN_FACTOR["inc"] == 2 * _YARN_FACTOR["sc"]
    assert _YARN_FACTOR["dc_inc"] == 2 * _YARN_FACTOR["dc"]
    assert abs(_YARN_FACTOR["hdc3"] - 3 * _YARN_FACTOR["hdc"]) < 1e-9
    assert _YARN_FACTOR["cable2x2"] == 4 * 11.5


# ---- PT-08 ---------------------------------------------------------------------------------

def test_row_height_is_the_stitch_weighted_mean():
    g = Gauge(stitches_per_10cm=10, rows_per_10cm=10, stitch_type="sc")
    rows = [Row(index=1, ops=[Op("sc", 8), Op("dc", 1)], declared_count=9),
            Row(index=2, ops=[Op("dc", 9)], declared_count=9),
            Row(index=3, ops=[Op("sc", 9)], declared_count=9)]
    cir = CIR(slug="t", title="t", version="1.0.0", construction="flat_rows", gauge=g,
              components=[Component(name="p", construction="flat_rows", rows=rows,
                                    foundation=9, foundation_kind="chain")])
    result = compile_cir(cir)
    assert result.ok, result.errors
    h = [row_height_cm(r, cir) for r in result.rows]
    dc = stitches.get("dc").row_height
    assert abs(h[0] - (8 + dc) / 9) < 1e-9          # 1.11 cm, not the 2.0 cm of a dc row
    assert abs(h[1] - dc) < 1e-9 and abs(h[2] - 1.0) < 1e-9
    t = build_twin(cir, result)
    assert abs(t.height_cm - round(sum(h), 1)) < 1e-9 and "weighted" in t.height_rule
    assert t.calibrated is False


def test_cloudline_size_is_the_weighted_model_and_its_label_follows():
    cir, t = _twin("cloudline_blanket")
    assert cir.version == "1.2.0"
    assert (t.width_cm, t.height_cm) == (79.2, 96.4)
    cand = launch0.candidate("cloudline-baby-blanket")
    assert cand.variants[0].label == "79.2 x 96.4 cm"
    assert launch0.size_label_backed(cand.variants[0].label, None, None, twin=t)["backed"]


# ---- PT-09 ---------------------------------------------------------------------------------

def test_cloudline_colour_changes_can_all_be_carried():
    cir, _t = _twin("cloudline_blanket")
    plan = analyse(cir)["panel"]
    assert plan.changes > 30 and plan.cut == 0 and plan.carry_is_possible
    assert plan.ends == 4
    rows = cir.components[0].rows
    assert len(rows) > 1, "the cloudline panel compiled no rows to check"
    # Every colour block is an even number of rows, so every change is at one edge.
    blocks, run = [], 1
    for a, b in zip(rows, rows[1:]):
        if a.color == b.color:
            run += 1
        else:
            blocks.append(run)
            run = 1
    blocks.append(run)
    assert all(n % 2 == 0 for n in blocks), blocks
    # A row that begins with a dc turns with two chains.
    from brambleloop.cir.model import Repeat

    for r in rows:
        first = r.ops[0]
        while isinstance(first, Repeat):
            first = first.ops[0]
        assert r.turning_chain == (2 if first.stitch == "dc" else 1), r.index
    text = write_pattern(cir, compile_cir(cir))
    assert "carry it loosely up that edge" in text and "Ends to weave in: about 4" in text
    assert certify(cir).granted


def test_one_row_stripes_cannot_claim_carry():
    """The pre-PT-09 Cloudline shape: colour every row on turned rows plus a carry note."""
    g = Gauge(stitches_per_10cm=12.5, rows_per_10cm=13.8, stitch_type="sc", hook_mm=5.0)
    rows = [Row(index=i, ops=[Op("sc", 10)], declared_count=10, turning_chain=1,
                color="cream" if i % 2 else "ink") for i in range(1, 9)]
    cir = CIR(slug="stripe-test", title="Stripe Test", version="1.0.0",
              construction="flat_rows", gauge=g, colors={"cream": "#FAF6EB", "ink": "#1A2B3C"},
              components=[Component(name="panel", construction="flat_rows", rows=rows,
                                    foundation=10, foundation_kind="chain")],
              designer_notes="Colour changes every row; carry the resting colour up the side.")
    plan = analyse(cir)["panel"]
    assert plan.cut == plan.changes - 1 and not plan.carry_is_possible
    assert "cut it" in instruction(plan)
    cert = certify(cir)
    assert not cert.granted
    assert any(f.code == "COLOUR_CARRY_IMPOSSIBLE" for f in cert.findings)


def test_one_row_stripe_catalogue_notes_say_cut_not_carry():
    cir = builder.for_slug("harvest-table-runner")
    assert "carry" not in (cir.designer_notes or "").lower()
    assert "cut it and rejoin" in cir.designer_notes


# ---- PT-10 ---------------------------------------------------------------------------------

def test_hexagon_spans_and_titles():
    _c, coaster = _twin("hexagon_coasters")
    assert coaster.sides == 6
    assert (coaster.across_points_cm, coaster.across_flats_cm) == (9.7, 8.4)
    assert size_statement(coaster) == ("hexagon, 9.7 cm across the points, 8.4 cm across "
                                       "the flats")
    for build, spans in (("basket_small", (16.0, 13.9)), ("basket_medium", (20.8, 18.0)),
                         ("basket_large", (25.6, 22.2))):
        cir, t = _twin(build)
        assert (t.across_points_cm, t.across_flats_cm) == spans, build
        assert "Hexagonal" in cir.title and "across the flats" in cir.finished_size_note
        assert "stack" in cir.components[0].note
        assert certify(cir).granted, build
    # 60 sc at 12.5 sts/10 cm: perimeter 48 cm, side 8 cm, points 16, flats 8*sqrt(3).
    _c, small = _twin("basket_small")
    assert abs(small.across_flats_cm - round(8 * math.sqrt(3), 1)) < 1e-9


def test_a_round_name_on_a_hexagon_is_refused():
    from dataclasses import replace

    cir = vessels.build_hexagon_coaster()
    cert = certify(replace(cir, title="Round Coaster Set"))
    assert any(f.code == "CLAIM_SHAPE_UNSUPPORTED" for f in cert.findings)
    assert certify(cir).granted


def test_pdf_and_writer_state_the_convention():
    cir, t = _twin("hexagon_coasters")
    text = write_pattern(cir, compile_cir(cir), width_cm=t.width_cm, height_cm=t.height_cm)
    assert "9.7 cm across the points and 8.4 cm across the flats" in text



def test_size_derived_designs_are_counted_with_the_twins_own_row_height():
    """PT-08 follow-through: the builders that choose row counts from a target size must use
    the same stitch-weighted rule the twin measures with, or every derived design comes out
    short of its own intent (the flagship throw measured 90.3 cm against a 122.2 cm intent)."""
    from brambleloop.products import nordic_forest, texture

    for size, (_w, target_h) in nordic_forest.TARGET_CM.items():
        cir = nordic_forest.build(size)
        t = build_twin(cir, compile_cir(cir))
        repeat = nordic_forest._repeat_height_cm(nordic_forest.GAUGE)
        assert abs(t.height_cm - target_h) <= repeat / 2 + 0.2, (size, t.height_cm, target_h)
    for build_fn, target in ((texture.build_cable_throw, texture.CABLE_TARGET_CM),
                             (texture.build_bobble_pillow, texture.PILLOW_TARGET_CM)):
        cir = build_fn()
        t = build_twin(cir, compile_cir(cir))
        assert abs(t.height_cm - target[1]) <= 0.1 * target[1], (cir.slug, t.height_cm, target)
    runner = builder.for_slug("harvest-table-runner")
    t = build_twin(runner, compile_cir(runner))
    assert 110 <= t.height_cm <= 135, t.height_cm

if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e)[:400])
    sys.exit(1 if fails else 0)
