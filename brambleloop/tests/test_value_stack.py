"""#7: what a flagship gives beyond the instructions, and the rule about how it is priced.

The requirement ends on "price the customer outcome rather than page count", which is a rule
about what may enter the arithmetic. These tests are mostly about holding that rule in a way
a future edit cannot quietly undo.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.creative.concept import Concept  # noqa: E402
from brambleloop.creative.prototype import author  # noqa: E402
from brambleloop.publish import value_stack as V  # noqa: E402


def _built(form="rectangle_throw", construction="flat_rows"):
    concept = Concept(
        key="k", title="Lantern Throw",
        premise="a folded ridge that stands proud of the field so it reads across a room",
        pod="blankets", form=form, construction=construction, motif="lantern",
        palette_story="ember and soot", recipient="self", occasion="everyday",
        feeling="cosy", function="warmth", make_lane="LONG", provenance="test")
    cir = author(concept)
    result = compile_cir(cir)
    assert result.ok, [str(f) for f in result.errors][:3]
    return cir, build_twin(cir, result)


def test_price_cannot_be_derived_from_page_count():
    """The requirement's closing sentence, held by making the forbidden thing unreachable.

    A docstring saying "we do not price on page count" is a promise. A function that never
    receives one cannot be made to, which is the difference between a rule and an intention.
    """
    import inspect

    signature = inspect.signature(V.outcome_price)
    for forbidden in V.NEVER_PRICED_ON:
        assert forbidden not in signature.parameters, forbidden
    source = inspect.getsource(V.outcome_price)
    for forbidden in ("pages", "page_count", "word_count", "file_size"):
        assert forbidden not in source.replace("page count", ""), forbidden

    cir, twin = _built()
    priced = V.outcome_price(twin, make_hours=45.0, make_lane="LONG", colours=2,
                             market_median_cad=9.5)
    assert set(priced["factors"]) == {f.key for f in V.PRICE_FACTORS}
    assert priced["never_priced_on"] == list(V.NEVER_PRICED_ON)


def test_the_price_is_anchored_on_what_the_market_charges():
    """A price with no relation to the department's own prices is a number this company made
    up about a market it has already measured."""
    cir, twin = _built()
    cheap = V.outcome_price(twin, make_hours=45.0, make_lane="LONG", colours=2,
                            market_median_cad=6.0)
    dear = V.outcome_price(twin, make_hours=45.0, make_lane="LONG", colours=2,
                           market_median_cad=18.0)
    assert dear["price_cad"] > cheap["price_cad"]
    assert cheap["anchor_cad"] == 6.0

    raised = None
    try:
        V.outcome_price(twin, make_hours=45.0, make_lane="LONG", colours=2,
                        market_median_cad=0.0)
    except V.ValueStackRefused as e:
        raised = e
    assert raised is not None
    assert "no anchor" in str(raised)


def test_a_bigger_object_and_a_longer_make_both_move_the_price():
    """The two things the buyer actually receives and spends, moving the number they pay."""
    _cir, throw = _built()
    _cir2, small = _built(form="coaster")
    anchor = 9.5
    big = V.outcome_price(throw, make_hours=45.0, make_lane="LONG", colours=2,
                          market_median_cad=anchor)
    little = V.outcome_price(small, make_hours=1.0, make_lane="QUICK", colours=2,
                             market_median_cad=anchor)
    assert big["price_cad"] > little["price_cad"], (big, little)
    assert big["factors"]["finished_object"] > little["factors"]["finished_object"]
    assert big["factors"]["commitment"] > little["factors"]["commitment"]


def test_progress_milestones_state_a_number_a_maker_can_count():
    """A maker halfway up a blanket is asking whether what is on their hook is right.

    A picture they can only agree with does not answer that; a stitch count and a measurement
    do.
    """
    cir, twin = _built()
    progress = V.milestones(cir, twin)
    assert progress["rows_total"] > 0
    marks = progress["milestones"]
    assert 3 <= len(marks) <= 5, marks
    assert [m["row"] for m in marks] == sorted(m["row"] for m in marks)
    assert marks[0]["row"] == 1 and marks[-1]["row"] == progress["rows_total"]
    for mark in marks:
        assert mark["stitches_in_this_row"] > 0
        assert mark["height_so_far_cm"] >= 0
        assert "stitches across" in mark["what_should_be_true"]
    # The last milestone is the finished object, so its height is the twin's.
    assert abs(marks[-1]["height_so_far_cm"] - twin.height_cm) < 1.0


def test_print_safety_is_measured_on_lightness_because_home_printers_are_greyscale():
    """A chart whose colours differ in hue but not in value prints as one flat block --
    unusable on exactly the copy a maker props open beside them."""
    cir, twin = _built()
    safe = V.print_safety(cir)
    assert safe["measurable"] is True
    assert safe["prints"] is True, safe
    assert safe["weakest_pair"]["value_gap"] >= V.MIN_VALUE_SEPARATION

    # Two colours of near-identical lightness merge, and the report says so rather than
    # calling the pattern unusable: the chart's letter cue still carries it.
    cir.colors = {"main": "#1F3A2E", "accent": "#2E3A1F"}
    merged = V.print_safety(cir)
    assert merged["prints"] is False, merged
    assert merged["colour_independent_cue"] is True
    assert "harder to read rather than impossible" in merged["why"]


def test_a_single_colour_pattern_has_nothing_to_merge():
    cir, twin = _built()
    cir.colors = {"main": "#1F3A2E"}
    only = V.print_safety(cir)
    assert only["measurable"] is False
    assert only["prints"] is None
    assert only["colour_independent_cue"] is True


def test_video_is_named_as_gated_rather_than_promised():
    """A listing that offers a video it cannot make is the plainest kind of
    misrepresentation."""
    cir, twin = _built()
    stack = V.value_stack(cir, twin, make_hours=45.0, make_lane="LONG",
                          market_median_cad=9.5)
    assert "video" in stack["gated"]
    assert "does not have" in stack["gated"]["video"]
    assert set(stack) == {"progress", "print", "price", "gated"}


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
