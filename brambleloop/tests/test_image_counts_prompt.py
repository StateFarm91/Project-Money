"""IMAGE-BLOCKED: the FLUX prompt states the two numbers the fidelity gate refuses on.

The gate (`visual.fidelity`) measures the flat piece's long/short ratio against the twin and
counts the declared horizontal repeats. The prompt gave centimetres and pointed at the chart but
never stated the ratio or the count. The new COUNTS section states both, derived from the
certified rules, and it must agree with the gate's own expectation for the same CIR. The gate is
unchanged; no extra paid call is made (this only changes the text of the one existing call).

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_image_counts_prompt.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.creative import flux_prompt as FP  # noqa: E402
from brambleloop.creative import pattern_refs as PR  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.visual import fidelity as FD  # noqa: E402

FLAT = "cloudline_blanket"


def _rules(cir):
    return PR.technical_rules(cir, release_hash="f" * 64)


def test_counts_agree_with_the_gates_own_expectation():
    cir = launch0.cir_for(FLAT)
    text = FP.counts_and_proportion(_rules(cir))
    assert text, "a single-piece flat product must state its proportion"
    piece = FD.expectation(cir).pieces[0]
    ratio = float(re.search(r"long side is ([0-9.]+) times", text).group(1))
    assert abs(ratio - piece.ratio) <= 0.01, (ratio, piece.ratio)
    if piece.repeat:
        n = int(re.search(r"exactly (\d+)", text).group(1))
        assert n == piece.repeat["n"], (n, piece.repeat)
        assert piece.repeat["what"].split()[0] in text, (text, piece.repeat)
    else:
        assert "exactly" not in text, text


def test_multi_component_and_round_pieces_say_nothing():
    rules = {"fabric": {"multi_component": True},
             "components": [{"name": "a", "worked": "in flat rows", "width_cm": 10,
                             "height_cm": 10}, {"name": "b", "worked": "in flat rows",
                                                "width_cm": 5, "height_cm": 5}]}
    assert FP.counts_and_proportion(rules) == ""
    rules = {"fabric": {}, "components": [{"name": "a", "worked": "in rounds",
                                           "width_cm": 10, "height_cm": 10}]}
    assert FP.counts_and_proportion(rules) == ""


def test_motif_repeats_only_when_they_divide_the_width():
    base = {"fabric": {}, "components": [{"name": "body", "worked": "in flat rows",
                                          "width_cm": 60.0, "height_cm": 90.0,
                                          "stitches_across": 120}]}
    got = FP.counts_and_proportion({**base, "repeat": {"component": "body", "stitches": 12}})
    assert "exactly 10 identical motif repeats" in got and "1.50 times" in got, got
    got = FP.counts_and_proportion({**base, "repeat": {"component": "body", "stitches": 7}})
    assert "exactly" not in got, got
    got = FP.counts_and_proportion({**base, "fabric": {"cables": {"columns": 4}},
                                    "repeat": {"component": "body", "stitches": 12}})
    assert "exactly 4 cable columns" in got, got


def test_the_section_is_in_the_built_prompt():
    cir = launch0.cir_for(FLAT)
    rules = _rules(cir)
    roles = ("product_layout", "product_texture", "product_detail", "product_rules")
    built = FP.build(rules=rules, roles=roles, role="product_anchor")
    assert "COUNT AND PROPORTION (these are checked):" in built.text
    assert any(s["ref"] == "image.flux3.counts@1" for s in built.sections), built.sections
    assert built.receipt()["builder_version"] == FP.BUILDER_VERSION


def test_fidelity_rejections_are_counted_in_a_fixed_vocabulary():
    from brambleloop.ops import production_evidence as PE

    acc = {"frames": 0, "by_code": {}, "by_check": {}}
    fail = {"product_truth": {"fidelity": {
        "status": "FAIL", "codes": ["WRONG_REPEAT_COUNT", "secret text <b>"],
        "checks": [{"check": "body:repeat_count", "status": "FAIL"},
                   {"check": "body:aspect", "status": "PASS"},
                   {"check": "Free Text Here!", "status": "FAIL"}]}}}
    PE._count_fidelity_rejection(acc, fail)
    PE._count_fidelity_rejection(acc, {"product_truth": {"fidelity": {"status": "PASS",
                                                                       "codes": ["X"]}}})
    PE._count_fidelity_rejection(acc, None)
    assert acc == {"frames": 1, "by_code": {"WRONG_REPEAT_COUNT": 1, "other": 1},
                   "by_check": {"body:repeat_count": 1, "other": 1}}, acc


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
