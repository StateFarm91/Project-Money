"""The benchmark garment: a real commercial pattern, encoded and reconstructed.

This is the strongest test the CIR has, because unlike every other fixture the answer is
known independently: somebody wrote this pattern, somebody crocheted it, the finished
garment was photographed and its measurements were published. So the question is not "does
this compile" but "does our representation reproduce a real object".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.cir import benchmarks as B
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.twin import build_twin
from brambleloop.visual import fabric

# The pattern's own stated totals, which our row construction must land on exactly.
STATED_TOTAL_ROWS = (81, 91, 99, 107, 115, 125, 133, 143, 151)


def test_every_size_compiles_with_no_errors():
    for size in B.SIZES:
        r = compile_cir(B.cardigan(size))
        errors = [f for f in r.findings if getattr(f, "severity", "") == "ERROR"]
        assert not errors, f"{size}: {[str(e) for e in errors]}"


def test_the_row_count_lands_on_the_patterns_own_total_for_every_size():
    """front + armhole + back + armhole + front + final row, with nothing left over.

    The pattern publishes this total per size. Our construction derives it from the panel
    row counts, so agreeing on all nine is evidence that the construction is understood
    rather than that one size was fitted.
    """
    for i, size in enumerate(B.SIZES):
        rows = B.cardigan(size).components[0].rows
        assert len(rows) == STATED_TOTAL_ROWS[i], (
            f"{size}: built {len(rows)} rows, pattern states {STATED_TOTAL_ROWS[i]}")


def test_the_finished_length_recomputes_from_counts_and_gauge():
    """Geometric fidelity: stitch count / gauge must reproduce the published length."""
    for size in B.SIZES:
        rec = B.reconcile(size)
        drift = abs(rec["length_cm"] - rec["length_stated"]) / rec["length_stated"]
        assert drift < 0.02, f"{size}: {rec['length_cm']} vs stated {rec['length_stated']}"


def test_the_back_width_recomputes_from_row_count_and_gauge():
    for size in B.SIZES:
        rec = B.reconcile(size)
        drift = abs(rec["back_width_cm"] - rec["back_width_stated"]) / rec["back_width_stated"]
        assert drift < 0.03, f"{size}: {rec['back_width_cm']} vs {rec['back_width_stated']}"


def test_the_sleeve_can_actually_be_sewn_into_the_armhole():
    """The invariant that decides whether the pieces make a garment or a pile of rectangles.

    A sleeve is folded into a tube whose circumference is its row count at row gauge. That
    tube is sewn into an armhole whose perimeter is twice the armhole measurement. If those
    disagree the garment cannot be assembled, however correct each piece is alone.
    """
    for size in B.SIZES:
        assert B.reconcile(size)["seam_compatible"], (
            f"{size}: sleeve circumference and armhole perimeter disagree")


def test_the_body_and_sleeves_are_worked_sideways_and_say_so():
    """Grain is what lets anything downstream speak about direction on the worn garment."""
    c = B.cardigan("M")
    body = next(x for x in c.components if x.name == "body")
    sleeve = next(x for x in c.components if x.name == "sleeve")
    pocket = next(x for x in c.components if x.name == "pocket")
    assert body.grain == "across" and body.rows_run_vertically_on_the_body
    assert sleeve.grain == "across"
    assert pocket.grain == "up" and not pocket.rows_run_vertically_on_the_body


def test_the_body_fabric_measures_as_a_broken_surface_not_as_stripes():
    """The texture claim, computed from loop targets rather than asserted."""
    c = B.cardigan("XS")
    r = compile_cir(c)
    sig = fabric.texture_signature(build_twin(c, r, component="body"))
    assert sig["textured"] is True
    assert sig["alternation_along_row"] >= 0.5
    assert sig["offset_between_rows"] >= 0.5
    assert sig["surface"] == "checkered"


def test_the_neckband_measures_as_ribbing_rather_than_as_untextured():
    """Constant single-loop working is ribbing, not the absence of texture.

    Every row leaves its unworked loop in the same place, so the rows stack into ridges. A
    classifier that only looks for variation calls this flat, which is how the ribbed band
    of a ribbed cardigan gets reported as plain fabric.
    """
    c = B.cardigan("XS")
    r = compile_cir(c)
    sig = fabric.texture_signature(build_twin(c, r, component="neck_ribbing"))
    assert sig["textured"] is True
    assert sig["surface"] == "ridges_along_the_rows"


def test_the_cuff_is_slip_stitch_so_the_sleeve_reads_as_a_balloon():
    """The sleeve is a straight tube; the cuff is what shapes it.

    Nothing tapers. The balloon is produced by working the cuff edge in slip stitch, which
    is shorter than a half double and draws that edge in. Losing this would give a correct
    stitch count and a sleeve that hangs like a pipe.
    """
    c = B.cardigan("XS")
    sleeve = next(x for x in c.components if x.name == "sleeve")
    slst_rows = [r for r in sleeve.rows
                 if any(getattr(o, "stitch", None) == "slst" for o in r.ops)]
    assert slst_rows, "the cuff edge lost its slip stitches"
    assert len(slst_rows) >= len(sleeve.rows) // 3


def test_the_armhole_is_spanned_by_chains_and_declares_its_unworked_stitch():
    """Chains replace stitches the row did not work, and one is the turning chain."""
    c = B.cardigan("XS")
    body = next(x for x in c.components if x.name == "body")
    arm = [r for r in body.rows if any(getattr(o, "stitch", None) == "ch" for o in r.ops)]
    assert len(arm) == 2, f"a cardigan has two armholes, found {len(arm)}"
    for r in arm:
        assert r.skips == B.ARMHOLE_CH[0] - 1
    after = [body.rows[body.rows.index(r) + 1] for r in arm]
    assert all(r.allow_remainder for r in after), (
        "the row working back across the bridge skips the turning chain and must say so")


def test_the_whole_garment_is_four_pieces_and_a_complete_assembly():
    c = B.cardigan("L")
    assert {x.name for x in c.components} == {"body", "sleeve", "pocket", "neck_ribbing"}
    assert next(x for x in c.components if x.name == "sleeve").make == 2
    assert next(x for x in c.components if x.name == "pocket").make == 2
    assert c.makes_a_closed_form
    assert len(c.assembly) == 5


def test_grading_is_monotonic_in_every_dimension():
    """A size run that is not monotonic is a grading bug, whoever published it."""
    for seq in (B.BODY_STS, B.FRONT_ROWS, B.BACK_ROWS, B.ARMHOLE_CH,
                B.SLEEVE_STS, B.SLEEVE_ROWS, B.YARN_G):
        assert all(b >= a for a, b in zip(seq, seq[1:])), f"not monotonic: {seq}"


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("OK  ", name)
            except Exception as e:
                fails += 1; print("FAIL", name, repr(e)); traceback.print_exc()
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
