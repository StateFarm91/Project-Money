"""Gate B -- writer / reverse compiler.

The decisive test: mutate the customer-facing text the way a bad PDF edit would, and prove
the reverse compiler catches it. The writer and reverse compiler share no parsing code, so a
clean round trip is evidence rather than a tautology.
"""
from __future__ import annotations

import re
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
    # Take the line out of the rendered text rather than matching a literal: the heading
    # gained a colour when written patterns started naming the yarn, and a tamper that no
    # longer applies is a test that proves nothing.
    text = _text(cir)
    victim = next(l for l in text.splitlines() if re.match(r"^Row 2\b", l))
    mutated = text.replace(victim, victim.replace("Ch 1, turn. ", ""), 1)
    assert mutated != text, "the tamper did not apply"
    findings = compare(cir, mutated)
    assert "REVERSE_TURNING_CHAIN" in codes(findings)


def test_dropped_row_is_caught():
    cir = fixtures.good_sphere()
    lines = [l for l in _text(cir).splitlines() if not re.match(r"^Rnd 5\b", l)]
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



# ---- texture: which loop the hook enters -------------------------------------------------


def _textured():
    from brambleloop.cir.model import CIR, Component, Gauge, Op, Repeat, Row
    return CIR(
        slug="ridge", title="Ridge swatch", version="1", construction="flat_rows",
        gauge=Gauge(16, 12, stitch_type="hdc"),
        components=[Component("body", "flat_rows", foundation=12, rows=[
            Row(1, [Op("hdc", 12)], declared_count=12, turning_chain=1),
            Row(2, [Op("hdc", 12, loop="back")], declared_count=12, turning_chain=1),
            Row(3, [Repeat([Op("hdc", loop="front"), Op("hdc", loop="back")], times=6)],
                declared_count=12, turning_chain=1),
            Row(4, [Op("dec", 1, loop="back"), Op("hdc", 10, loop="front")],
                declared_count=11, turning_chain=1),
        ])])


def test_the_loop_is_written_and_read_back_in_both_terminologies():
    cir = _textured()
    us, uk = _text(cir), _text(cir, "UK")
    assert "hdc in back loop of next 12 sts" in us
    assert "htr in back loop of next 12 sts" in uk
    assert "dec in back loop over next 2 sts" in us
    for text, term in ((us, "US"), (uk, "UK")):
        assert compare(cir, text, terminology=term) == [], term
        loops = [op.loop for r in parse_pattern(text, term) for op in r.ops
                 if hasattr(op, "loop")]
        assert "back" in loops, term


def test_a_flipped_loop_is_a_mismatch_not_a_nuance():
    """Count-neutral, so the only thing that can catch it is the reverse compiler."""
    cir = _textured()
    text = _text(cir)
    flipped = text.replace("hdc in back loop of next 12 sts", "hdc in front loop of next 12 sts")
    assert flipped != text
    assert "REVERSE_MISMATCH" in codes(compare(cir, flipped))
    plain = text.replace("hdc in back loop of next 12 sts", "hdc in next 12 sts")
    assert "REVERSE_MISMATCH" in codes(compare(cir, plain))


def test_the_benchmark_back_loop_rib_round_trips():
    from brambleloop.cir import benchmarks as B  # read-only fixture use
    cir = B.cardigan("M")
    text = _text(cir)
    assert "in back loop of next" in text
    assert compare(cir, text) == []


# ---- multi-piece documents: row scope resets per piece ------------------------------------


def _two_pieces():
    from brambleloop.cir.model import CIR, Component, Gauge, Op, Row

    def piece(name, n, rows, make=1):
        body = [Row(1, [Op("sc", n)], declared_count=n, turning_chain=1)]
        body += [Row(i, [Op("sc", n, loop="back" if i % 2 else "both")], declared_count=n,
                     turning_chain=1) for i in range(2, rows + 1)]
        return Component(name, "flat_rows", foundation=n, rows=body, make=make)
    return CIR(slug="pair", title="Pair", version="1", construction="flat_rows",
               gauge=Gauge(16, 18),
               components=[piece("front", 20, 13), piece("sleeve", 12, 9, make=2)])


def test_a_row_cycle_is_read_inside_its_own_piece():
    """"Repeat rows 2-5" under the sleeve used to find the front's rows 2-5 too."""
    cir = _two_pieces()
    text = _text(cir)
    assert text.count("Repeat rows") == 2, text
    assert compare(cir, text) == []
    parsed = parse_pattern(text)
    assert [p.component for p in parsed].count("sleeve") == 9


def test_a_dropped_piece_or_a_wrong_make_count_is_caught():
    cir = _two_pieces()
    text = _text(cir)
    assert "REVERSE_MAKE" in codes(compare(cir, text.replace("(make 2)", "(make 3)")))
    head, _, _ = text.partition("## sleeve")
    tail = text[text.index("## Finishing"):]
    missing = compare(cir, head + tail)
    assert {"REVERSE_COMPONENTS", "REVERSE_ROW_COUNT"} <= codes(missing)


def test_a_hold_and_its_resume_are_read_back():
    from tests.test_division import yoke
    cir = yoke()
    text = _text(cir)
    assert compare(cir, text) == []
    moved = text.replace("(sts 21-28)", "(sts 22-29)")
    assert moved != text
    assert "REVERSE_HOLD" in codes(compare(cir, moved))

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
