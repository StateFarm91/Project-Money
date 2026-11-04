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
