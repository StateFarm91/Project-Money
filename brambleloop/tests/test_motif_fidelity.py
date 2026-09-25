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
    """A generator that produced squares will happily be told they are diamonds.

    The chart's existence is asserted *at the moment the judge is handed it*, which is when
    this check's property is true or false. It used to be asserted after `check` returned, and
    that pinned a second property nobody meant: that the chart outlives the comparison. It did,
    because `check` wrote it with `tempfile.mkdtemp` and nothing removed it -- a rendered image
    per asset check, for ever, on the disk that ran out of space in this repository once
    already. `check` now owns and removes its chart (2026-09-25), so the assertion moved to
    where the question is actually being asked. Everything else here is unchanged, and the new
    position is the stronger test: it proves the judge was handed a file rather than a path.
    """
    import tempfile

    cir, twin = _subject()
    seen: dict = {}

    def judger(image_ref, chart_ref):
        seen["image"] = image_ref
        seen["chart"] = chart_ref
        seen["chart_existed_when_the_judge_saw_it"] = Path(chart_ref).is_file()
        return _answer()

    with tempfile.TemporaryDirectory() as tmp:
        image = Path(tmp) / "asset.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n")
        out = mf.check(None, str(image), cir, twin, judger=judger)

    assert seen["image"].endswith("asset.png")
    assert seen["chart_existed_when_the_judge_saw_it"], (
        "the chart was not rendered to compare against")
    assert out["chart_retained"] is False, (
        "the chart is deterministic output from a certified CIR and is redrawn for nothing, "
        "so it is not kept -- and the record has to say so rather than leave a path that "
        "stops resolving")
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



def _proto(cir):
    import dataclasses

    return dataclasses.replace(cir, designer_notes=(
        "prototype of hats-hat-0: an adult hat, worked in the round, "
        "52 x 22 cm at 12 sts/10cm"))


def test_a_note_about_the_object_does_not_become_the_chart_s_motif():
    """The defect that made product truth unpassable for every cycle-authored product.

    `creative.prototype.author` writes "prototype of {key}: {what}, {w} x {h} cm at
    {gauge}" -- the finished thing and its dimensions, with nothing in it about stitches.
    `expected` took the first sentence of that as the motif name, and two guaranteed
    failures followed: the render prompt asked for "fabric worked in this pattern's own
    motif: an adult hat, worked in the round", and the verdict compared an honest
    description of fabric against those words, found no overlap and returned `mismatch`
    every time. #300's weakest link failed for a reason that had nothing to do with the
    picture, twice, in production.
    """
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.products.builder import for_slug

    cir = for_slug("cloudline-baby-blanket")
    twin = build_twin(cir, compile_cir(cir))

    assert mf.motif_name(cir), "a real designer note still names the motif"
    assert mf.motif_name(_proto(cir)) == ""

    want = mf.expected(_proto(cir), twin)
    assert want["motif_is_named"] is False
    assert "finished object" in want["why_unnamed"]


def test_an_unnamed_motif_makes_the_name_test_unavailable_rather_than_satisfied():
    """The mirror defect, waiting behind the first one.

    With `motif_named` empty the overlap test was skipped and the verdict fell straight
    through to MATCH -- an expectation nothing can contradict, which passes every fabric
    ever rendered. Object prose made it always fail; no prose made it always pass. Both
    are a verdict resting on a value that is not about the thing being judged.
    """
    want = {"motif_named": "", "colour_count": 2, "why_unnamed": "prose names no motif"}
    observed = {"fabric_readable": True, "same_pattern_as_chart": True,
                "repeating_unit_shape": "shell rows",
                "colour_arrangement": "two colours alternating"}
    out = mf.judge(observed, want)
    assert out["verdict"] == mf.MATCH
    assert out["name_test"] == "unavailable", "an absent test must not report as a passed one"
    assert "prose names no motif" in out["why"]


def test_a_colour_the_pattern_does_not_contain_is_a_different_fabric():
    """The one fabric fact that is true of every certified pattern, prose or no prose.

    Both live renders of a two-colour certified hat came back as three-colour granny
    shells. The colour count is deterministic from the chart and is checked before the
    name, so it catches that for the products the cycle authors in memory as well as for
    the catalogue.
    """
    want = {"motif_named": "", "colour_count": 2}
    observed = {"fabric_readable": True, "same_pattern_as_chart": True,
                "repeating_unit_shape": "shell rows",
                "colour_arrangement": "three colours in repeating shell rows"}
    out = mf.judge(observed, want)
    assert out["verdict"] == mf.MISMATCH
    assert "3 colours" in out["why"] and "chart works 2" in out["why"]


def test_a_colour_arrangement_that_states_no_count_leaves_that_check_unmade():
    """Unmade is not passed, and it is not failed either."""
    assert mf._colours_in("") == 0
    assert mf._colours_in("subtle tonal variation across the piece") == 0
    want = {"motif_named": "", "colour_count": 2}
    observed = {"fabric_readable": True, "same_pattern_as_chart": True,
                "repeating_unit_shape": "shell rows",
                "colour_arrangement": "subtle tonal variation across the piece"}
    assert mf.judge(observed, want)["verdict"] == mf.MATCH


def test_the_prompt_points_at_the_chart_when_prose_names_no_motif():
    """"Plain single-colour fabric with no motif" was a claim made from a missing sentence."""
    from brambleloop.products.builder import for_slug
    from brambleloop.publish import owned_photography as op

    cir = for_slug("cloudline-baby-blanket")
    sentence = op.motif_sentence(_proto(cir))
    assert "exactly as the accompanying stitch chart shows" in sentence
    assert "no motif" not in sentence
    # And the colour count is stated either way, because that is what kept going wrong.
    assert "exactly two colours" in sentence
    assert "exactly two colours" in op.motif_sentence(cir)

def test_the_colour_count_counts_colours_and_not_stitch_codes():
    """It read `chart_grid()` -- a grid of stitch abbreviations -- and called it a colour count.

    A check whose whole job is to catch a render that invents a colour could not see colour. It
    was invisible because of a coincidence: 13 of the 16 catalogue patterns work two stitches and
    two colours, so the wrong instrument returned the right number. The three that disagree are
    the products rebuilt after the "Heirloom Cable Throw" defect -- one cream yarn each, all
    relief -- and the cable blanket's four stitch types were reported as four colours, which
    would have made `judge` call a correct one-colour render a mismatch and a three-colour render
    a match.
    """
    from brambleloop.products import texture

    single = texture.build_cable_throw()
    twin = build_twin(single, compile_cir(single))
    assert len(single.colors or {}) == 1
    assert len({c for row in twin.chart_grid() for c in row if c is not None}) == 4, \
        "the fixture has to be one whose stitch count and colour count differ, or this " \
        "test cannot fail"
    assert mf.chart_colours(twin) == 1

    # And the coincidence itself, so nobody re-derives the count from the stitch grid and finds
    # the suite still green: a two-colour design must not agree by accident here either.
    two = for_slug("cloudline-baby-blanket")
    assert mf.chart_colours(build_twin(two, compile_cir(two))) == 2


def test_the_verdict_refuses_a_render_that_adds_a_colour_to_a_single_colour_fabric():
    """The consequence of the wrong count, end to end through `judge`.

    The same render, the same judge answers: a mismatch against the corrected count of one, and
    a match against the four the old code produced from four stitch types. That is what the
    defect cost — not a check that failed, a check that agreed with the wrong fabric.
    """
    from brambleloop.products import texture

    cir = texture.build_cable_throw()
    twin = build_twin(cir, compile_cir(cir))
    want = mf.expected(cir, twin)
    assert want["colour_count"] == 1

    seen = {"fabric_readable": True, "same_pattern_as_chart": True,
            "repeating_unit_shape": "crossed cable columns",
            "colour_arrangement": "four colours in crossed cable columns"}

    verdict = mf.judge(seen, want)
    assert verdict["verdict"] == mf.MISMATCH, verdict
    assert "chart works 1" in verdict["why"], verdict["why"]
    assert verdict["colour_test"] == "failed"

    was = mf.judge(seen, {**want, "colour_count": 4})
    assert was["verdict"] == mf.MATCH, was
    assert was["colour_test"] == "passed"


def test_a_verdict_says_whether_the_colour_test_ran_rather_than_claiming_it_passed():
    """`_colours_in` returns 0 when the judge's phrase carries no count, and its own docstring
    says that leaves the colour check "unmade rather than passed" -- while both MATCH branches
    said "and the colour count agrees" either way.

    That is exactly the `name_test` defect this module already fixed, three lines above the check
    it was fixed in: a verdict naming a test it did not run. The state now travels with the
    verdict, so a reader can tell an established colour agreement from an unattempted one.
    """
    want = {"motif_named": "cable columns", "colour_count": 1}
    unstated = mf.judge({"fabric_readable": True, "same_pattern_as_chart": True,
                         "repeating_unit_shape": "cable columns",
                         "colour_arrangement": "cream, sage and rust stripes"}, want)
    assert unstated["verdict"] == mf.MATCH
    assert unstated["colour_test"].startswith("unavailable"), unstated
    assert "not compared" in unstated["why"], unstated["why"]

    stated = mf.judge({"fabric_readable": True, "same_pattern_as_chart": True,
                       "repeating_unit_shape": "cable columns",
                       "colour_arrangement": "one colour throughout"}, want)
    assert stated["colour_test"] == "passed", stated
    assert "colour count agrees" in stated["why"]

    # And every branch carries it, so no verdict is silent about the test.
    for observed in ({"fabric_readable": False},
                     {"fabric_readable": True, "same_pattern_as_chart": False},
                     {"fabric_readable": True, "same_pattern_as_chart": None},
                     {"fabric_readable": True, "same_pattern_as_chart": True,
                      "repeating_unit_shape": "granny shells"}):
        out = mf.judge(observed, want)
        if out["verdict"] == mf.UNMEASURABLE and not observed.get("fabric_readable"):
            continue  # nothing was seen at all, so there is no arrangement to read
        assert "colour_test" in out, out


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
