"""Gate B (pattern safety) -- deterministic compiler.

Run: python -m pytest brambleloop/tests -q   (or python brambleloop/tests/test_compiler.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR  # noqa: E402
from tests import fixtures  # noqa: E402


def codes(result) -> set[str]:
    return {f.code for f in result.errors}


def test_good_sphere_compiles():
    r = compile_cir(fixtures.good_sphere())
    assert r.ok, [str(f) for f in r.errors]
    assert r.counts("body") == [6, 12, 18, 24, 30, 30, 24]


def test_good_mosaic_compiles_and_resolves_to_end_repeats():
    r = compile_cir(fixtures.good_mosaic_panel())
    assert r.ok, [str(f) for f in r.errors]
    assert r.counts("panel") == [40, 40, 40, 40]
    # 40 available / 4 per repeat = 10 repeats of [sc 3, dc], i.e. 20 ops all tagged as
    # belonging to the same bracket (the group id identifies the bracket, not the repetition).
    row2 = r.row("panel", 2)
    assert row2.consumed == 40 and row2.produced == 40
    assert len(row2.ops) == 20
    assert {o.repeat_group for o in row2.ops} == {0}


def test_broken_stitch_count_is_rejected():
    r = compile_cir(fixtures.broken_stitch_count())
    assert not r.ok
    assert "COUNT_MISMATCH" in codes(r)
    bad = [f for f in r.errors if f.code == "COUNT_MISMATCH"][0]
    assert bad.row == 4 and "23" in bad.message and "24" in bad.message


def test_broken_repeat_is_rejected():
    r = compile_cir(fixtures.broken_repeat())
    assert not r.ok
    assert "REPEAT" in codes(r)
    assert "does not divide" in " ".join(f.message for f in r.errors)


def test_overrun_is_rejected():
    r = compile_cir(fixtures.broken_overrun())
    assert not r.ok
    assert "OVERRUN" in codes(r)


def test_underrun_is_rejected():
    r = compile_cir(fixtures.broken_underrun())
    assert not r.ok
    assert "UNDERRUN" in codes(r)


def test_unknown_colour_is_rejected():
    r = compile_cir(fixtures.broken_unknown_color())
    assert not r.ok
    assert "UNKNOWN_COLOR" in codes(r)


def test_cir_round_trips_through_json():
    original = fixtures.good_sphere()
    clone = CIR.from_json(original.to_json())
    assert clone.to_json() == original.to_json()
    assert compile_cir(clone).counts("body") == compile_cir(original).counts("body")


def test_turning_chain_warning_for_tall_stitches():
    cir = fixtures.good_mosaic_panel()
    cir.components[0].rows[1].turning_chain = 0
    r = compile_cir(cir)
    assert any(f.code == "NO_TURNING_CHAIN" for f in r.warnings)


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
