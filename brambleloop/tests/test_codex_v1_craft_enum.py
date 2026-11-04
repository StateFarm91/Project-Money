"""Offline craft readings must not turn unsupported labels into observed defects."""
import pytest

from brambleloop.products.vessels import build_basket
from brambleloop.visual import fidelity


@pytest.mark.parametrize("craft", ["unreadable", "crocheted", "unknown", ""])
def test_unsupported_blind_craft_labels_are_unknown_not_fail(craft):
    exp = fidelity.expectation(build_basket("small"))
    reading = {"fabric_visible_clearly": "true", "craft": craft, "cable_style": "none",
               "ribbing_visible": "false", "border_or_edging_visible": "false"}
    result = fidelity.compare_craft(reading, exp)
    assert result["status"] == "UNKNOWN" and result["blocks_variant_input"] is True


def test_clear_known_craft_match_and_mismatch_keep_existing_verdicts():
    exp = fidelity.expectation(build_basket("small"))
    reading = {"fabric_visible_clearly": "true", "craft": "crochet", "cable_style": "none",
               "ribbing_visible": "false", "border_or_edging_visible": "false"}
    assert fidelity.compare_craft(reading, exp)["status"] == "PASS"
    reading["craft"] = "knitting"
    assert fidelity.compare_craft(reading, exp)["status"] == "FAIL"
