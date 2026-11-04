"""Offline blind comparisons cannot pass without both images' observations."""
import copy
import json
from pathlib import Path

import pytest

from brambleloop.visual import fidelity, vision_judges
from test_w4_fidelity import CLOUD, _cir


class Judge:
    def __init__(self, reading):
        self.reading = reading

    def read(self, *_args, **_kwargs):
        return {"answered": True, "reading": self.reading}


def _reading():
    path = Path(__file__).parent / "fixtures" / "visnext" / "readings.json"
    return json.loads(path.read_text())["item_same"]["item_description"]


@pytest.mark.parametrize("side,field", [
    ("image_1", "craft"), ("image_1", "border_or_edging_visible"),
    ("image_1", "plain_end_bands_visible"), ("image_2", "plain_end_bands_visible"),
    ("image_1", "raised_cables_visible"), ("image_2", "raised_cables_visible"),
    ("image_1", "distinct_yarn_colours"), ("image_2", "distinct_yarn_colours"),
])
def test_incomplete_description_is_never_an_anchor_comparison_pass(side, field):
    reading = copy.deepcopy(_reading())
    reading[side][field] = "unclear"
    verdict = vision_judges.blind_consistency(Judge(reading), b"anchor", b"candidate",
                                               fidelity.expectation(_cir(CLOUD)))
    assert verdict["status"] == "UNKNOWN" and verdict["blocks_variant_input"] is True


def test_complete_match_still_passes_and_visible_wrong_craft_still_fails():
    exp = fidelity.expectation(_cir(CLOUD))
    reading = _reading()
    assert vision_judges.blind_consistency(Judge(reading), b"a", b"b", exp)["status"] == "PASS"
    reading["image_2"]["craft"] = "knitting"
    assert vision_judges.blind_consistency(Judge(reading), b"a", b"b", exp)["status"] == "FAIL"


@pytest.mark.parametrize("side", ["image_1", "image_2"])
def test_zero_yarn_colour_count_is_not_a_verifiable_comparison(side):
    reading = _reading()
    reading[side]["distinct_yarn_colours"] = 0
    verdict = vision_judges.blind_consistency(Judge(reading), b"a", b"b",
                                               fidelity.expectation(_cir(CLOUD)))
    assert verdict["status"] == "UNKNOWN"


@pytest.mark.parametrize("side", ["image_1", "image_2"])
def test_unrecognised_craft_label_is_unknown_not_a_definite_mismatch(side):
    reading = _reading()
    reading[side]["craft"] = "unreadable"
    verdict = vision_judges.blind_consistency(Judge(reading), b"a", b"b",
                                               fidelity.expectation(_cir(CLOUD)))
    assert verdict["status"] == "UNKNOWN" and verdict["blocks_variant_input"] is True


def test_unclear_anchor_edge_does_not_prove_invented_edging():
    reading = _reading()
    reading["image_1"]["border_or_edging_visible"] = "unclear"
    reading["image_2"]["border_or_edging_visible"] = "yes"
    verdict = vision_judges.blind_consistency(Judge(reading), b"a", b"b",
                                               fidelity.expectation(_cir(CLOUD)))
    assert verdict["status"] == "UNKNOWN"


def test_fewer_visible_colours_do_not_silently_pass_comparison():
    reading = _reading()
    reading["image_2"]["distinct_yarn_colours"] = 1
    verdict = vision_judges.blind_consistency(Judge(reading), b"a", b"b",
                                               fidelity.expectation(_cir(CLOUD)))
    assert verdict["status"] == "UNKNOWN"


def test_missing_or_hidden_comparison_is_not_a_variant_input():
    exp = fidelity.expectation(_cir(CLOUD))
    incomplete = _reading()
    del incomplete["image_1"]
    hidden = _reading()
    hidden["image_2"]["item_visible"] = "no"
    results = [vision_judges.compare_items(None, exp),
               vision_judges.blind_consistency(Judge(incomplete), b"a", b"b", exp),
               vision_judges.blind_consistency(Judge(hidden), b"a", b"b", exp),
               vision_judges.blind_consistency(None, b"a", b"b", exp)]
    assert all(v["status"] == "UNKNOWN" and v["blocks_variant_input"] is True for v in results)


def test_single_cable_in_compiled_cir_is_not_called_invented():
    from brambleloop.cir.model import Op
    from test_w5_v1_visual_correctness import _flat, _row

    rows = [_row(i, "pine") for i in range(1, 7)]
    rows[2].ops = [Op("sc", 4), Op("cable2x2"), Op("sc", 4)]
    cir = _flat("single-cable", rows, {"pine": "#244A3A"})
    exp = fidelity.expectation(cir)
    assert exp.cables_declared is True
    assert all(not p.repeat or "cable" not in str(p.repeat.get("what")) for p in exp.pieces)
    reading = _reading()
    for item in reading.values():
        item.update(border_or_edging_visible="no", plain_end_bands_visible="no",
                    distinct_yarn_colours=1)
    reading["image_1"]["raised_cables_visible"] = "no"
    reading["image_2"]["raised_cables_visible"] = "yes"
    result = vision_judges.blind_consistency(Judge(reading), b"a", b"b", exp)
    assert result["status"] == "UNKNOWN" and result["blocks_variant_input"] is True
    reading["image_2"]["raised_cables_visible"] = "no"
    assert vision_judges.blind_consistency(Judge(reading), b"a", b"b", exp)["status"] == "UNKNOWN"
    reading["image_2"]["raised_cables_visible"] = "yes"
    from brambleloop.products.vessels import build_basket

    basket = fidelity.expectation(build_basket("small"))
    assert not basket.cables_declared
    defect = vision_judges.blind_consistency(Judge(reading), b"a", b"b", basket)
    assert defect["status"] == "FAIL"


def test_declared_short_end_bands_are_not_called_invented():
    from test_w5_v1_visual_correctness import _flat, _row

    colors = ["cream", "cream", "pine", "pine", "cream", "pine", "pine", "cream", "cream"]
    cir = _flat("short-bands", [_row(i, color) for i, color in enumerate(colors, 1)],
                {"cream": "#DDD7CA", "pine": "#244A3A"})
    exp = fidelity.expectation(cir)
    assert exp.edge_ambiguity == "end_bands" and not any(p.bands for p in exp.pieces)
    reading = _reading()
    for item in reading.values():
        item.update(border_or_edging_visible="no", raised_cables_visible="no",
                    distinct_yarn_colours=2)
    reading["image_1"]["plain_end_bands_visible"] = "no"
    reading["image_2"]["plain_end_bands_visible"] = "yes"
    result = vision_judges.blind_consistency(Judge(reading), b"a", b"b", exp)
    assert result["status"] == "UNKNOWN" and result["blocks_variant_input"] is True
    reading["image_2"]["plain_end_bands_visible"] = "no"
    assert vision_judges.blind_consistency(Judge(reading), b"a", b"b", exp)["status"] == "UNKNOWN"
    reading["image_2"]["plain_end_bands_visible"] = "yes"

    from brambleloop.products.vessels import build_basket

    basket = fidelity.expectation(build_basket("small"))
    for item in reading.values():
        item["distinct_yarn_colours"] = 1
    assert vision_judges.blind_consistency(Judge(reading), b"a", b"b", basket)["status"] == "FAIL"


def test_multi_component_unknown_band_presence_cannot_pass_on_absence():
    from test_w5_v1_visual_correctness import _flat, _row

    cir = _flat("two-pieces", [_row(i, "pine") for i in range(1, 6)], {"pine": "#244A3A"})
    other = _flat("second", [_row(i, "pine") for i in range(1, 5)],
                  {"pine": "#244A3A"}).components[0]
    other.name = "other"
    cir.components.append(other)
    exp = fidelity.expectation(cir)
    assert exp.edge_ambiguity == "components"
    reading = _reading()
    for item in reading.values():
        item.update(border_or_edging_visible="no", plain_end_bands_visible="no",
                    raised_cables_visible="no", distinct_yarn_colours=1)
    result = vision_judges.blind_consistency(Judge(reading), b"a", b"b", exp)
    assert result["status"] == "UNKNOWN" and result["blocks_variant_input"] is True


def test_declared_edging_not_seen_in_either_image_is_not_a_pass():
    from test_w5_v1_visual_correctness import _flat, _row

    cir = _flat("with-border", [_row(i, "pine") for i in range(1, 6)],
                {"pine": "#244A3A"})
    cir.components[0].name = "border panel"
    exp = fidelity.expectation(cir)
    assert exp.edging_declared is True
    reading = _reading()
    for item in reading.values():
        item.update(border_or_edging_visible="no", plain_end_bands_visible="no",
                    raised_cables_visible="no", distinct_yarn_colours=1)
    result = vision_judges.blind_consistency(Judge(reading), b"a", b"b", exp)
    assert result["status"] == "UNKNOWN" and result["blocks_variant_input"] is True
    for item in reading.values():
        item["border_or_edging_visible"] = "yes"
    assert vision_judges.blind_consistency(Judge(reading), b"a", b"b", exp)["status"] == "PASS"


def test_both_images_missing_a_used_yarn_colour_do_not_pass():
    exp = fidelity.expectation(_cir(CLOUD))
    assert sum(float(share) > 0 for share in exp.expected_share) == 2
    reading = _reading()
    for item in reading.values():
        item["distinct_yarn_colours"] = 1
    result = vision_judges.blind_consistency(Judge(reading), b"a", b"b", exp)
    assert result["status"] == "UNKNOWN" and result["blocks_variant_input"] is True
    # The candidate may show the missing colour even when the anchor does not;
    # the incomplete anchor does not prove an invented extra colour.
    reading["image_2"]["distinct_yarn_colours"] = 2
    result = vision_judges.blind_consistency(Judge(reading), b"a", b"b", exp)
    assert result["status"] == "UNKNOWN" and result["blocks_variant_input"] is True


@pytest.mark.parametrize("shares", [[True, False], ["1", "0"], [0.3, 0.3], [float("nan"), 0]])
def test_malformed_expected_colour_usage_is_never_a_pass(shares):
    from dataclasses import replace

    exp = replace(fidelity.expectation(_cir(CLOUD)), expected_share=shares)
    result = vision_judges.blind_consistency(Judge(_reading()), b"a", b"b", exp)
    assert result["status"] == "UNKNOWN" and result["blocks_variant_input"] is True


def test_unused_palette_entry_is_not_required_visible():
    from test_w5_v1_visual_correctness import _flat, _row

    cir = _flat("unused-colour", [_row(i, "pine") for i in range(1, 6)],
                {"pine": "#244A3A", "cream": "#DDD7CA"})
    exp = fidelity.expectation(cir)
    assert len(exp.palette_hex) == 2 and sum(float(share) > 0 for share in exp.expected_share) == 1
    reading = _reading()
    for item in reading.values():
        item.update(border_or_edging_visible="no", plain_end_bands_visible="no",
                    raised_cables_visible="no", distinct_yarn_colours=1)
    assert vision_judges.blind_consistency(Judge(reading), b"a", b"b", exp)["status"] == "PASS"
