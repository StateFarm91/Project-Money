"""Offline craft readings must not turn unsupported labels into observed defects."""
import pytest

from brambleloop.products.vessels import build_basket
from brambleloop.visual import fidelity


@pytest.mark.parametrize("reading", [None, [], ""])
def test_absent_or_malformed_craft_reading_is_not_an_edit_base(reading):
    result = fidelity.compare_craft(reading, fidelity.expectation(build_basket("small")))
    assert result["status"] == "UNKNOWN" and result["blocks_variant_input"] is True


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


@pytest.mark.parametrize("field,value", [("craft", "unknown"),
                                        ("ribbing_declared", "false"),
                                        ("cables_declared", "false"),
                                        ("edging_declared", "false")])
def test_malformed_pattern_craft_fact_never_passes_or_proves_a_defect(field, value):
    from dataclasses import replace

    exp = replace(fidelity.expectation(build_basket("small")), **{field: value})
    reading = {"fabric_visible_clearly": "true", "craft": "crochet", "cable_style": "none",
               "ribbing_visible": "false", "border_or_edging_visible": "false"}
    result = fidelity.compare_craft(reading, exp)
    assert result["status"] == "UNKNOWN" and result["blocks_variant_input"] is True


def test_invalid_ribbing_fact_does_not_hide_observed_craft_mismatch():
    from dataclasses import replace

    exp = replace(fidelity.expectation(build_basket("small")), ribbing_declared="false")
    reading = {"fabric_visible_clearly": "true", "craft": "knitting", "cable_style": "none",
               "ribbing_visible": "false", "border_or_edging_visible": "false"}
    assert fidelity.compare_craft(reading, exp)["status"] == "FAIL"
