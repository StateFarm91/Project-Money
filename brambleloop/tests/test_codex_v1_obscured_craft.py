"""An obscured image cannot establish a definite blind-vision craft defect."""
from brambleloop.products.vessels import build_basket
from brambleloop.visual import fidelity


def test_obscured_contradictory_craft_reading_is_held_not_a_definite_failure():
    cir = build_basket("small")
    exp = fidelity.expectation(cir)
    reading = {"fabric_visible_clearly": "false", "craft": "knitting",
               "cable_style": "knitted_rope", "ribbing_visible": "true",
               "border_or_edging_visible": "true"}
    blocked = fidelity.compare_craft(reading, exp)
    assert blocked["status"] == "UNKNOWN" and blocked["blocks_variant_input"] is True
    # The same contradictory facts on a clear image remain a definite failure.
    reading["fabric_visible_clearly"] = "true"
    assert fidelity.compare_craft(reading, exp)["status"] == "FAIL"
    # The vision uncertainty must not suppress a separate deterministic image failure.
    assert fidelity.verify_anchor(b"not an image", cir)["status"] == "FAIL"
