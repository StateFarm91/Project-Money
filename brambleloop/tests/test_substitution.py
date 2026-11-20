"""#7's buildable half: what can I use instead, and how much of it.

The interesting tests here are the three refusals and one piece of arithmetic that looks
right and is not.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.cir.model import Gauge, Material  # noqa: E402
from brambleloop.publish import substitution as S  # noqa: E402


def test_gauge_decides_which_weights_substitute_not_the_name_on_the_band():
    """Weight names are a marketing category and their gauge bands overlap heavily.

    A "worsted" from one mill works to a different fabric than a "worsted" from another, so
    what qualifies a substitute is whether the *pattern's* gauge sits inside that weight's
    published band.
    """
    at_13 = S.substitutes(13.0, declared="worsted")
    keys = {w["weight"] for w in at_13["weights"]}
    assert keys == {"light", "medium"}, keys
    assert at_13["declared"] == "medium"
    assert at_13["declared_holds_gauge"] is True

    # A pattern whose own stated weight cannot hold its own gauge is worth knowing about.
    mismatched = S.substitutes(30.0, declared="chunky")
    assert mismatched["declared_holds_gauge"] is False, mismatched
    assert "bulky" not in {w["weight"] for w in mismatched["weights"]}


def test_a_pattern_with_no_gauge_gets_no_substitution_guidance():
    """A guide without a gauge is a guess with a table around it."""
    class _Cir:
        gauge = None
        materials: list = []

    raised = None
    try:
        S.guidance(_Cir())
    except S.SubstitutionRefused as e:
        raised = e
    assert raised is not None
    assert "guess with a table around it" in str(raised)


def test_across_fibres_it_gives_a_direction_and_refuses_a_number():
    """`calibration_key` learned this the expensive way.

    Keying a measured yardage factor on weight alone would have let a firm cotton basket
    rewrite the yardage on an acrylic throw, because cotton and acrylic at the same weight do
    not use the same length of yarn per stitch. How much they differ is measured on a sample,
    and this module has not seen one.
    """
    out = S.how_much(900, from_weight="worsted", to_weight="dk",
                     from_fibre="worsted acrylic", to_fibre="dk cotton")
    assert out["measurable"] is False, out
    assert out["fibre_change"] == "synthetic to plant"
    assert "measured on a sample" in out["why"]
    assert "buy_metres" not in out, "a number was given across a fibre change"


def test_the_obvious_yardage_arithmetic_is_the_wrong_one():
    """Scaling the estimate by the ratio of lengths per 100g looks right and is wrong.

    That ratio is about *mass*, not about length used. At the same gauge and finished size
    the stitch count is identical and each stitch's yarn path is the same size, so the metres
    barely move. What moves is how many balls those metres arrive in. The first version of
    this module scaled by the ratio and produced a band from 485m to 900m for a 900m pattern,
    which would have sent a buyer home with half the yarn.
    """
    lighter = S.how_much(900, from_weight="worsted", to_weight="dk",
                         from_fibre="acrylic", to_fibre="acrylic")
    heavier = S.how_much(900, from_weight="worsted", to_weight="chunky",
                         from_fibre="acrylic", to_fibre="acrylic")

    # The metres are the pattern's own estimate plus the margin, both directions.
    assert lighter["buy_metres"] == heavier["buy_metres"] == round(900 * 1.15, 1)
    assert lighter["buy_metres"] > 900, "the buy figure has no margin in it"

    # What the substitution actually changes is the ball count and the fabric.
    assert lighter["balls_100g"] < heavier["balls_100g"], (lighter, heavier)
    assert "lighter and more open" in lighter["fabric_changes"]
    assert "heavier and denser" in heavier["fabric_changes"]


def test_contrast_is_checked_on_lightness_because_a_thumbnail_is_nearly_greyscale():
    """Two colours of equal lightness merge in the grid however different they look in hand.

    That is the difference between a motif and a smudge in the thumbnail a buyer actually
    decides from, and hue distance does not catch it.
    """
    reads = S.colourway([{"role": "ground", "hex": "1F3A2E"},
                         {"role": "motif", "hex": "C9A227"}])
    assert reads["reads"] is True, reads

    # Very different hues, almost identical lightness.
    merges = S.colourway([{"role": "ground", "hex": "1F3A2E"},
                          {"role": "motif", "hex": "2E3A1F"}])
    assert merges["reads"] is False, merges
    assert merges["weakest_pair"]["value_gap"] < S.MIN_VALUE_SEPARATION
    assert "merge in the grid" in merges["why"]


def test_a_colourway_nobody_stated_in_hex_is_unmeasurable_rather_than_fine():
    """A colour name is somebody's word for it. "Sage" is not a measurement."""
    none_given = S.colourway([])
    assert none_given["measurable"] is False
    assert "somebody's word for it" in none_given["why"]

    one_colour = S.colourway([{"role": "ground", "hex": "1F3A2E"}])
    assert one_colour["measurable"] is False
    assert "no contrast to check" in one_colour["why"]


def test_the_guidance_block_is_computed_from_the_pattern_and_not_written_about_it():
    class _Twin:
        yarn_metres_by_color = {"main": 700.0, "accent": 200.0}

    class _Cir:
        gauge = Gauge(stitches_per_10cm=13.0, rows_per_10cm=14.0, stitch_type="sc",
                      hook_mm=5.0, yarn_weight="worsted")
        materials = [Material(name="worsted acrylic", yarn_weight="worsted")]

    out = S.guidance(_Cir(), _Twin(),
                     colours=[{"role": "main", "hex": "1F3A2E"},
                              {"role": "accent", "hex": "C9A227"}])
    assert out["declared_weight"] == "medium"
    assert out["declared_fibre_class"] == "synthetic"
    assert out["estimate_metres"] == 900.0
    # The declared weight is not offered as a substitute for itself.
    assert all(row["to"] != "medium" for row in out["how_much"] if "to" in row), out["how_much"]
    assert out["how_much"], "no substitute was offered for a gauge two weights can hold"
    assert out["colourway"]["reads"] is True


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
