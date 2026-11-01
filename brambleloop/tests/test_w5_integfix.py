"""Batch 5 integration fixes (W5-INTEG1): interactions between independently reviewed branches.

Each test fails on the pre-fix tree and names the two branches whose combination it covers.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from brambleloop.gates import size_claims as SC  # noqa: E402


def test_a_round_or_row_number_is_a_place_in_the_pattern_not_a_count():
    """W4-PDF1 basket 1.3.0 x OPUS2 size-claim truth: the 1.3.0 checkpoint tip "Up to Rnd 10
    the basket should lie flat" was read as a promise of ten baskets and refused the release."""
    for text in ("If it ruffles or cups Up to Rnd 10 the basket should lie flat.",
                 "By Round 12 the bowl stands on its own.",
                 "After Row 4 the basket wall begins."):
        assert SC.claims_in(text) == [], (text, SC.claims_in(text))
    # Real counts still count, including next to a round reference.
    assert SC.claimed_count(SC.claims_in("Includes 3 baskets.")) == 3
    assert SC.claimed_count(SC.claims_in("Work Round 4, then make 2 bowls.")) == 2
    assert SC.claimed_count(SC.claims_in("A set of 3 nesting baskets in one pattern.")) == 3


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:500]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
