"""OPUS2-P0: a basket render is told its top rim is the plain final round (owner report).

Owner-generated basket images showed a braided rim; every certified basket CIR ends in plain
single-crochet rounds. The render negative names the rim so "edge" cannot be read as
excluding a vessel's top.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_rim_negative.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.products import launch0  # noqa: E402


def test_a_basket_render_is_told_its_top_rim_is_the_plain_final_round():
    """Owner report: generated basket images showed a braided rim the CIR does not have."""
    from brambleloop.creative import pattern_refs as P

    for build in ("basket_small", "basket_medium", "basket_large"):
        cir = launch0.cir_for(build)
        last = cir.components[0].rows[-1]
        assert {op.stitch for op in last.ops} == {"sc"}, build      # a plain sc final round
        neg = " | ".join(P.negatives(P.fabric_facts(cir)))
        assert "no braided, rolled, twisted, scalloped, picot or crab-stitch" in neg, build


def test_a_flat_piece_keeps_its_row_end_wording():
    from brambleloop.creative import pattern_refs as P

    cir = launch0.cir_for("cloudline_blanket")
    neg = " | ".join(P.negatives(P.fabric_facts(cir)))
    assert "the edges are the plain ends of the rows" in neg and "top rim" not in neg


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
