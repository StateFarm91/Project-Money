"""Gate B -- writer / reverse compiler.

The decisive test: mutate the customer-facing text the way a bad PDF edit would, and prove
the reverse compiler catches it. The writer and reverse compiler share no parsing code, so a
clean round trip is evidence rather than a tautology.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.reverse import compare, parse_pattern  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from tests import fixtures  # noqa: E402


def _text(cir, terminology="US"):
    return write_pattern(cir, compile_cir(cir), terminology)


def codes(findings):
    return {f.code for f in findings}


def test_sphere_round_trips_clean():
    cir = fixtures.good_sphere()
    assert compare(cir, _text(cir)) == []


def test_mosaic_round_trips_clean():
    cir = fixtures.good_mosaic_panel()
    assert compare(cir, _text(cir)) == []


def test_written_output_is_human_readable():
    cir = fixtures.good_sphere()
    text = _text(cir)
    assert "Rnd 3: [sc in next st, inc in next st] x 6. (18 sts)" in text
    assert "Gauge: 20 sts x 22 rows = 10cm in sc, 3.5mm hook" in text


def test_to_end_repeat_is_written_and_parsed():
    cir = fixtures.good_mosaic_panel()
    text = _text(cir)
    assert "rep from * to end" in text
    rows = parse_pattern(text)
    assert len(rows) == 4
    assert rows[1].declared_count == 40


def test_repeat_count_mutation_is_caught():
    """A PDF edit changing 'x 6' to 'x 7' must not reach a customer."""
    cir = fixtures.good_sphere()
    mutated = _text(cir).replace("[sc in next st, inc in next st] x 6", "[sc in next st, inc in next st] x 7")
    findings = compare(cir, mutated)
    assert "REVERSE_MISMATCH" in codes(findings)


def test_stitch_substitution_is_caught():
    """Swapping sc for dc changes the fabric entirely."""
    cir = fixtures.good_sphere()
    mutated = _text(cir).replace("Rnd 6: sc in next 30 sts.", "Rnd 6: dc in next 30 sts.")
    findings = compare(cir, mutated)
    assert "REVERSE_MISMATCH" in codes(findings)


def test_stitch_run_length_mutation_is_caught():
    cir = fixtures.good_sphere()
    mutated = _text(cir).replace("sc in next 3 sts, inc", "sc in next 2 sts, inc")
    findings = compare(cir, mutated)
    assert "REVERSE_MISMATCH" in codes(findings)


def test_declared_count_mutation_is_caught():
    cir = fixtures.good_sphere()
    mutated = _text(cir).replace("(18 sts)", "(19 sts)")
    findings = compare(cir, mutated)
    assert "REVERSE_COUNT" in codes(findings)


def test_turning_chain_removal_is_caught():
    cir = fixtures.good_mosaic_panel()
    mutated = _text(cir).replace("Row 2: Ch 1, turn. ", "Row 2: ")
    findings = compare(cir, mutated)
    assert "REVERSE_TURNING_CHAIN" in codes(findings)


def test_dropped_row_is_caught():
    cir = fixtures.good_sphere()
    lines = [l for l in _text(cir).splitlines() if not l.startswith("Rnd 5:")]
    findings = compare(cir, "\n".join(lines))
    assert "REVERSE_ROW_COUNT" in codes(findings)


def test_unparseable_instruction_is_reported_not_ignored():
    cir = fixtures.good_sphere()
    mutated = _text(cir).replace("sc in next 30 sts", "work around loosely")
    findings = compare(cir, mutated)
    assert "REVERSE_PARSE" in codes(findings)


def test_uk_terminology_round_trips():
    cir = fixtures.good_sphere()
    uk = _text(cir, "UK")
    assert "dc in next st" in uk  # UK 'dc' is US 'sc'
    assert compare(cir, uk, terminology="UK") == []


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
