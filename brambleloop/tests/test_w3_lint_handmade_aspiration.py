"""Wave 3 lane C: the "handmade" truth rule, refined on the semantic claim (owner decision
2026-10-06).

Brambleloop sells digital crochet patterns and makes nothing by hand. "Handmade" stays refused
as a description of anything the shop sells, made or photographed; the one reading allowed is
the customer's own making ("Patterns for a More Handmade Life", "for your handmade home").
Both directions are pinned here. No network, no model.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_lint_handmade_aspiration.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.store_foundation import lint  # noqa: E402

FAILS = 0


def check(name: str, fn) -> None:
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as exc:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


# The customer's life or home, made by the customer with a pattern.
ASPIRATIONAL = (
    "Patterns for a More Handmade Life",
    "Crochet patterns for a more handmade life",
    "for your handmade home",
    "Patterns for your handmade home.",
    "A more handmade life, one stitch at a time",
    "Calm crochet for a handmade home and table",
    "PATTERNS FOR A MORE HANDMADE LIFE",
    "Patterns for a more hand-made life",
)

# Claims that the shop, its products, items or listings are handmade -- still refused.
PRODUCT_CLAIMS = (
    "Handmade with love",
    "hand made in Canada",
    "100% handmade",
    "handmade",
    "Handmade crochet baskets",
    "Shop our handmade patterns",
    "Our handmade life",
    "My handmade home",
    "Brambleloop's handmade life",
    "Brambleloop handmade home decor",
    "for your handmade home decor",
    "a handmade home collection",
    "a handmade blanket for your home",
    "a more handmade life, made by hand by us",
    "a handmade life, handmade by us",
    "Hand-crocheted for your handmade home",
    "Every item is handmade, for a more handmade life",
    "a more handmade life collection",
    "your handmade home-decor",
    # disguised spellings are the claim they spell, and the exemption does not cover them
    "Ｈａｎｄｍａｄｅ baskets",
    "h a n d m a d e baskets",
)


def test_aspirational_uses_pass():
    for text in ASPIRATIONAL:
        found = [f for f in lint.lint(text, voice=False) if f["code"] == "TRUTH_PHYSICAL_MAKING"]
        assert not found, (text, found)


def test_product_claims_still_fail():
    for text in PRODUCT_CLAIMS:
        codes = {f["code"] for f in lint.lint(text, voice=False)}
        assert codes & {"TRUTH_PHYSICAL_MAKING", "TRUTH_OBFUSCATED_TEXT"}, (text, codes)


def test_a_product_claim_beside_the_aspiration_is_still_caught():
    found = lint.lint("Patterns for a more handmade life. Every basket is handmade.",
                      voice=False)
    assert [f for f in found if f["code"] == "TRUTH_PHYSICAL_MAKING"], found


def test_the_exemption_covers_only_the_word_handmade():
    # The exemption never swallows a longer match such as "handmade by".
    found = lint.lint("for your handmade home, handmade by Brambleloop", voice=False)
    assert any(f["match"].lower().startswith("handmade by") for f in found), found


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)

if FAILS:
    sys.exit(1)
