"""Digital twin: structural execution, geometry and yardage."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from tests import fixtures  # noqa: E402


def test_twin_cell_count_matches_compiled_stitches():
    cir = fixtures.good_sphere()
    r = compile_cir(cir)
    twin = build_twin(cir, r)
    # Every produced stitch becomes exactly one cell.
    assert twin.stitch_total == sum(row.produced for row in r.rows)
    assert twin.row_widths[3] == 18
    assert twin.row_widths[7] == 24


def test_twin_chart_grid_shape_matches_row_counts():
    cir = fixtures.good_mosaic_panel()
    r = compile_cir(cir)
    twin = build_twin(cir, r)
    grid = twin.chart_grid()
    assert [len(row) for row in grid] == [40, 40, 40, 40]
    # The grid is in fabric order, not working order (B-690).
    #
    # Flat rows turn, so an even row is worked in the opposite direction and its stitches sit
    # mirrored in the fabric relative to the order they were made. Every chart this renders
    # carries the footer "odd rows read right to left, even rows read left to right" -- an
    # explicit promise about direction that only holds if the grid says where stitches ARE.
    # This assertion used to encode working order, so the chart told makers to read even rows
    # one way while drawing them the other.
    #
    # Row 2 is worked as (3 sc, dc) ten times; in the fabric that reads (dc, 3 sc) ten times.
    assert grid[1][:5] == ["dc", "sc", "sc", "sc", "dc"]
    # Row 1 is odd, so working order and fabric order agree.
    assert grid[0][:5] == ["sc"] * 5


def test_twin_reports_colours_actually_present():
    cir = fixtures.good_mosaic_panel()
    twin = build_twin(cir, compile_cir(cir))
    assert twin.colors_used == {"forest", "wine"}
    assert twin.stitch_types_used == {"sc", "dc"}


def test_twin_computes_dimensions_from_gauge():
    cir = fixtures.good_mosaic_panel()
    twin = build_twin(cir, compile_cir(cir))
    # 40 sts at 16 sts/10cm = 25cm wide.
    assert twin.width_cm == 25.0
    assert twin.height_cm and 0 < twin.height_cm < 20


def test_twin_estimates_yardage_per_colour():
    cir = fixtures.good_mosaic_panel()
    twin = build_twin(cir, compile_cir(cir))
    assert set(twin.yarn_metres_by_color) == {"forest", "wine"}
    assert all(v > 0 for v in twin.yarn_metres_by_color.values())
    assert twin.calibrated is False  # uncalibrated until a physical test says otherwise


def test_twin_refuses_to_model_a_broken_pattern():
    cir = fixtures.broken_stitch_count()
    r = compile_cir(cir)
    try:
        build_twin(cir, r)
        assert False, "twin should refuse a pattern that failed compilation"
    except ValueError as e:
        assert "failed compilation" in str(e)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
