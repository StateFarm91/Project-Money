"""cir/shaping.py: tapers placed by Bresenham, bind-offs declared through skips and holds."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir import geometry  # noqa: E402
from brambleloop.cir import shaping as S  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR, Component, Gauge, Op, Row  # noqa: E402
from brambleloop.cir.reverse import compare  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402


def _flat(rows, foundation, construction="flat_rows"):
    return CIR(slug="t", title="Taper", version="1", construction=construction,
               gauge=Gauge(16, 18),
               components=[Component("piece", construction, foundation=foundation,
                                     rows=list(rows))])


def test_distribute_is_exact_and_even():
    for events, rows in ((11, 70), (0, 5), (5, 5), (13, 4), (1, 9)):
        spread = S.distribute(events, rows)
        assert sum(spread) == events and len(spread) == rows
        assert max(spread) - min(spread) <= 1


def test_a_taper_lands_exactly_on_its_target_and_compiles():
    for a, b, n, edge in ((36, 58, 70, "both"), (58, 36, 40, "both"), (20, 27, 9, "end"),
                          (30, 22, 8, "start"), (40, 40, 6, "both")):
        t = S.taper(a, b, n, edge=edge)
        assert len(t.rows) == n and t.final_count == b
        result = compile_cir(_flat(t.rows, a))
        assert result.ok, (a, b, [str(f) for f in result.errors])
        assert result.counts("piece") == list(t.counts)
        steps = [t.counts[0] - a] + [t.counts[i] - t.counts[i - 1] for i in range(1, n)]
        unit = 2 if edge == "both" else 1
        assert all(abs(s) % unit == 0 for s in steps)
        assert max(abs(s) for s in steps) - min(abs(s) for s in steps) <= unit


def test_a_taper_round_trips_through_the_written_pattern():
    t = S.taper(24, 36, 12, edge="both", loops_by_row={2: "back", 4: "back"})
    cir = _flat(t.rows, 24)
    text = write_pattern(cir, compile_cir(cir))
    assert "inc in back loop of next st" in text or "sc in back loop of next" in text
    assert compare(cir, text) == []
    assert compare(cir, write_pattern(cir, compile_cir(cir), "UK"), "UK") == []


def test_impossible_tapers_are_refused():
    for kwargs in ({"from_count": 20, "to_count": 25, "over_rows": 5},       # odd, both
                   {"from_count": 20, "to_count": 30, "over_rows": 0},
                   {"from_count": 6, "to_count": 2, "over_rows": 1},        # too steep
                   {"from_count": 20, "to_count": 10, "over_rows": 5, "stitch": "hdc"}):
        try:
            S.taper(**kwargs)
        except S.ShapingRefused:
            pass
        else:
            raise AssertionError(f"accepted {kwargs}")


def test_geometry_measure_reads_a_taper_worked_in_rounds():
    t = S.taper(24, 48, 12, edge="end", turning_chain=0)
    cir = _flat(t.rows, 24, construction="joined_rounds")
    result = compile_cir(cir)
    assert result.ok, [str(f) for f in result.errors]
    rev = geometry.measure(cir.components[0], result, cir)
    assert [r.count for r in rev.rings] == list(t.counts)
    circ = [r.circumference_cm for r in rev.rings]
    assert circ == sorted(circ) and circ[-1] == round(48 / 1.6, 2)
    assert rev.shape in (geometry.CONE, geometry.VESSEL, geometry.DISC)


def test_the_twin_sees_a_flat_taper_as_a_shaped_outline():
    t = S.taper(20, 32, 12)
    cir = _flat(t.rows, 20)
    twin = build_twin(cir, compile_cir(cir))
    assert twin.outline == "shaped_flat"
    assert twin.row_widths[t.rows[-1].index] == 32


def test_a_bind_off_with_a_held_shoulder_compiles_and_is_resumed():
    w, keep, held = 40, 12, 12
    body = [Row(i, [Op("sc", w)], declared_count=w, turning_chain=1) for i in range(1, 5)]
    b = S.bind_off(w, keep, index=5, after_row=4, hold_name="second_shoulder",
                   hold_count=held)
    assert b.finished == w - keep - held
    rows = body + [b.row] + [Row(6, [Op("sc", keep)], declared_count=keep, turning_chain=1)]
    first = Component("first", "flat_rows", foundation=w, rows=rows, holds=[b.hold])
    second = Component("second", "flat_rows", foundation=0, foundation_kind="none",
                       resumes="second_shoulder",
                       rows=[Row(1, [Op("sc", held)], declared_count=held, turning_chain=1),
                             Row(2, [Op("sc", held)], declared_count=held, turning_chain=1)])
    cir = CIR(slug="n", title="Neck", version="1", construction="flat_rows",
              gauge=Gauge(16, 18), components=[first, second])
    result = compile_cir(cir)
    assert result.ok, [str(f) for f in result.errors]
    text = write_pattern(cir, result)
    assert "for second shoulder" in text
    assert compare(cir, text) == []


def test_a_bind_off_that_claims_missing_stitches_is_refused():
    for kwargs in ({"available": 10, "keep": 10}, {"available": 10, "keep": 6, "hold_count": 5,
                                                   "hold_name": "x"},
                   {"available": 10, "keep": 4, "hold_count": 2}):
        try:
            S.bind_off(index=2, after_row=1, **kwargs)
        except S.ShapingRefused:
            pass
        else:
            raise AssertionError(f"accepted {kwargs}")


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
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
