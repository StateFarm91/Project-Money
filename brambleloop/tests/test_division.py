"""The armhole division: the one primitive that blocked a third of the benchmark catalogue.

Garments are 140 of the 438 observed MJs listings and the deepest proven-and-unserved arena,
and this engine could not build one. Not because rounds were missing, or shaping, or
assembly, or grading -- all four existed, and `cir/grading.py` says in its own docstring that
it was written for the garments pod. What was missing was working into part of a previous
row: a yoke worked in rounds splits, the sleeve stitches go on hold, and the body continues
over the rest. Without it the compiler saw a body round consuming 32 of 48 and called it an
underrun, so a cardigan could only ship as a flat panel nobody can wear.

"Place 24 sts on hold for the sleeve" is a promise, and the rules below exist because a
promise nobody checks is how a pattern ships with live stitches nobody comes back for.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR, Component, Gauge, Hold, Op, Row  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402


def sc(n: int) -> list[Op]:
    return [Op(stitch="sc", count=n)]


def yoke(*, holds=None, skips=16, sleeves=(("left_sleeve", "sleeve_left", 8),
                                           ("right_sleeve", "sleeve_right", 8))) -> CIR:
    """A top-down yoke: 48 sts, split at round 2, body over 32, two sleeves of 8."""
    body = Component(
        name="yoke_and_body", construction="joined_rounds", foundation=48,
        rows=[Row(index=1, ops=sc(48), declared_count=48),
              Row(index=2, ops=sc(48), declared_count=48),
              Row(index=3, ops=sc(48 - skips), declared_count=48 - skips, skips=skips),
              Row(index=4, ops=sc(48 - skips), declared_count=48 - skips)],
        holds=list(holds) if holds is not None else [
            Hold(name="sleeve_left", at_row=2, count=8),
            Hold(name="sleeve_right", at_row=2, count=8, from_stitch=20)])
    pieces = [Component(name=name, construction="joined_rounds", foundation=0,
                        foundation_kind="none", resumes=hold,
                        rows=[Row(index=1, ops=sc(n), declared_count=n)])
              for name, hold, n in sleeves]
    return CIR(slug="yoke", title="Top-down yoke", version="1",
               construction="joined_rounds", components=[body] + pieces,
               gauge=Gauge(stitches_per_10cm=18, rows_per_10cm=20))


def errors(cir: CIR) -> list[str]:
    return [f.code for f in compile_cir(cir).findings if f.severity == "ERROR"]


# ---- the product that could not be expressed --------------------------------


def test_a_top_down_yoke_compiles_clean():
    """The whole point. Before this, no arrangement of the CIR could say it."""
    assert errors(yoke()) == []


def test_without_the_hold_the_same_rounds_are_an_underrun():
    """Which is exactly what the compiler said before, and it was right to."""
    cir = yoke(skips=16)
    cir.components[0].rows[2].skips = 0
    assert "UNDERRUN" in errors(cir)


def test_a_divided_pattern_tells_the_maker_what_became_of_the_held_stitches():
    """"Rnd 3: sc 32" over a round of 48, with no explanation, is unfollowable.

    The arithmetic would be correct and the twin would agree, which is what makes this the
    dangerous kind of wrong: a document that passes every check and cannot be worked.
    """
    cir = yoke()
    text = write_pattern(cir, compile_cir(cir))
    assert "on a stitch holder or waste yarn" in text
    assert "8 sts (sts 1-8) for sleeve left" in text
    assert "8 sts (sts 21-28) for sleeve right" in text
    assert "Rejoin yarn to the sts held for sleeve left" in text


def test_the_twin_builds_from_a_divided_pattern():
    cir = yoke()
    result = compile_cir(cir)
    assert result.ok
    assert build_twin(cir, result, component="yoke_and_body") is not None


# ---- the four ways a division goes wrong ------------------------------------


def test_a_hold_nobody_resumes_is_an_error():
    """Live stitches and no instruction: the maker reaches the end and stops."""
    assert "HOLD_ABANDONED" in errors(
        yoke(sleeves=(("left_sleeve", "sleeve_left", 8),)))


def test_two_components_cannot_resume_the_same_hold():
    """The same stitches worked twice."""
    assert "HOLD_CONTESTED" in errors(yoke(sleeves=(
        ("left_sleeve", "sleeve_left", 8), ("other_left", "sleeve_left", 8),
        ("right_sleeve", "sleeve_right", 8))))


def test_a_sleeve_that_picks_up_the_wrong_count_is_an_error():
    """Two stitches short is a hole in the armpit, and it compiles without this."""
    assert "HOLD_MISMATCH" in errors(yoke(sleeves=(
        ("left_sleeve", "sleeve_left", 6), ("right_sleeve", "sleeve_right", 8))))


def test_overlapping_holds_are_refused():
    assert "HOLD_OVERLAP" in errors(yoke(holds=[
        Hold(name="sleeve_left", at_row=2, count=8, from_stitch=0),
        Hold(name="sleeve_right", at_row=2, count=8, from_stitch=4)]))


def test_a_hold_past_the_end_of_its_row_is_refused():
    assert "HOLD_OVERRUN" in errors(yoke(holds=[
        Hold(name="sleeve_left", at_row=2, count=60),
        Hold(name="sleeve_right", at_row=2, count=8, from_stitch=20)]))


def test_a_hold_on_a_row_that_does_not_exist_is_refused():
    assert "HOLD_BAD_ROW" in errors(yoke(holds=[
        Hold(name="sleeve_left", at_row=99, count=8),
        Hold(name="sleeve_right", at_row=2, count=8, from_stitch=20)]))


def test_resuming_a_hold_nobody_declared_is_refused():
    assert "HOLD_UNKNOWN" in errors(yoke(sleeves=(
        ("left_sleeve", "sleeve_left", 8), ("right_sleeve", "sleeve_right", 8),
        ("ghost", "sleeve_middle", 8))))


def test_a_row_cannot_hold_everything_it_has():
    cir = yoke()
    cir.components[0].rows[2].skips = 48
    assert "SKIPS_EVERYTHING" in errors(cir)


def test_a_component_cannot_declare_the_same_hold_twice():
    try:
        Component(name="x", construction="joined_rounds", foundation=8,
                  rows=[Row(index=1, ops=sc(8))],
                  holds=[Hold(name="a", at_row=1, count=2),
                         Hold(name="a", at_row=1, count=2, from_stitch=4)])
    except ValueError as e:
        assert "duplicate hold" in str(e)
    else:
        raise AssertionError("two holds shared a name")


# ---- nothing that worked before changed -------------------------------------


def test_a_pattern_with_no_division_is_untouched():
    """`skips` defaults to zero and `holds` to empty, so every existing CIR is unaffected."""
    plain = CIR(slug="p", title="Plain", version="1", construction="flat_rows",
                components=[Component(name="body", construction="flat_rows", foundation=20,
                                      rows=[Row(index=1, ops=sc(20), declared_count=20),
                                            Row(index=2, ops=sc(20), declared_count=20)])])
    assert errors(plain) == []
    text = write_pattern(plain, compile_cir(plain))
    assert "stitch holder" not in text and "Rejoin" not in text


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
