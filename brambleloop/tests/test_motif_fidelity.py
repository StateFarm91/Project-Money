"""Does the fabric in the picture work the pattern the buyer will make?

The gap was found by the check that missed it: a clean, believable crocheted blanket in the
right two colours, on the right surface, in the right light, worked in a checkerboard while
the certified pattern makes a diamond lattice. Every existing check passed it.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.products.builder import for_slug  # noqa: E402
from brambleloop.publish import motif_fidelity as mf  # noqa: E402


def _subject(slug: str = "cloudline-baby-blanket"):
    cir = for_slug(slug)
    return cir, build_twin(cir, compile_cir(cir))


def _answer(**overrides) -> dict:
    out = {"repeating_unit_shape": "diamond outline lattice", "repeats_across": 14,
           "colour_arrangement": "two colours alternating", "same_pattern_as_chart": True,
           "fabric_readable": True}
    out.update(overrides)
    return out


def test_the_checkerboard_is_a_mismatch_however_convincing_the_rest_is():
    cir, twin = _subject()
    want = mf.expected(cir, twin)
    out = mf.judge(_answer(repeating_unit_shape="solid square", repeats_across=8), want)
    assert out["verdict"] == mf.MISMATCH
    assert "polite yes" in out["why"]


def test_the_charts_own_pattern_is_a_match():
    cir, twin = _subject()
    out = mf.judge(_answer(), mf.expected(cir, twin))
    assert out["verdict"] == mf.MATCH
    assert "diamond" in out["overlap"] or "lattice" in out["overlap"]


def test_a_polite_yes_does_not_survive_a_contradicting_description():
    """`same_pattern_as_chart` is the question a model most wants to answer politely, so it
    is asked and not trusted alone."""
    cir, twin = _subject()
    want = mf.expected(cir, twin)
    assert mf.judge(_answer(same_pattern_as_chart=True,
                            repeating_unit_shape="chevron band"), want)["verdict"] \
        == mf.MISMATCH
    # And a plain no is taken at its word.
    assert mf.judge(_answer(same_pattern_as_chart=False), want)["verdict"] == mf.MISMATCH


def test_fabric_that_cannot_be_seen_is_unmeasurable_and_still_blocks():
    cir, twin = _subject()
    want = mf.expected(cir, twin)
    hidden = mf.judge(_answer(fabric_readable=False), want)
    assert hidden["verdict"] == mf.UNMEASURABLE
    assert "closer or flatter frame" in hidden["why"]

    cannot_tell = mf.judge(_answer(same_pattern_as_chart=None), want)
    assert cannot_tell["verdict"] == mf.UNMEASURABLE


def test_the_comparison_is_against_the_chart_rather_than_a_sentence():
    """A generator that produced squares will happily be told they are diamonds."""
    import tempfile

    cir, twin = _subject()
    seen: dict = {}

    def judger(image_ref, chart_ref):
        seen["image"] = image_ref
        seen["chart"] = chart_ref
        return _answer()

    with tempfile.TemporaryDirectory() as tmp:
        image = Path(tmp) / "asset.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n")
        out = mf.check(None, str(image), cir, twin, judger=judger)

    assert seen["image"].endswith("asset.png")
    assert Path(seen["chart"]).is_file(), "the chart was not rendered to compare against"
    assert out["verdict"] == mf.MATCH
    assert out["blocks_customer_facing_asset"] is False
    assert out["expected"]["chart_rows"] == 88


def test_the_vocabulary_is_closed():
    """An open one accepts 'a lovely texture', and a check whose evidence is that cannot
    disagree with any image ever rendered."""
    try:
        mf.parse('{"repeating_unit_shape": "diamond", "vibe": "lovely"}')
    except mf.MotifRefused as e:
        assert "vibe" in str(e)
    else:
        raise AssertionError("an open vocabulary was accepted")

    try:
        mf.parse('{"repeating_unit_shape": "diamond"}')
    except mf.MotifRefused as e:
        assert "not answered" in str(e)
    else:
        raise AssertionError("a description with holes in it was accepted")


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
