"""F-055 Style/Aesthetic Intent: the fallback facet map carries an evidence-backed aesthetic.

Board row: "Aesthetic facet exists in map_product but the live listing_language fallback facets
omit aesthetic unless the intake brief mapped it" -> "Include an evidence-backed aesthetic facet
in the fallback path". The evidence is the product's own record (listing qualifiers, title),
read against the classifier's aesthetic vocabulary; a product naming none maps none, and our
own vocabulary is never let in (it would refuse the whole facet map).

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_aesthetic_intent.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import intent  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402

FAILS = 0


def check(name, fn):
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as e:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {e!r}")


def _db():
    db = Database("sqlite://", scratch=True)
    db.create_all()
    return db


def test_the_aesthetic_comes_from_the_products_own_words():
    orn = l0.candidate("nordic-star-ornaments")
    assert intent.aesthetic_of(list(orn.listing.qualifiers), orn.title) == "nordic"
    blanket = l0.candidate("cloudline-baby-blanket")
    assert intent.aesthetic_of(list(blanket.listing.qualifiers), blanket.title) == ""
    assert intent.aesthetic_of([], "") == ""
    assert intent.aesthetic_of(["rustic"], "Farmhouse Basket") == "rustic"   # order given


def test_our_own_vocabulary_is_never_an_aesthetic():
    ours = sorted(w for w in intent.OUR_VOCABULARY
                  if intent._FACET_WORDS.get(w) == "aesthetic")
    for w in ours:  # vacuity-ok: no overlap between the vocabularies is the good case
        assert intent.aesthetic_of([w], "") == "", w
    empty = sorted(w for w in intent.EMPTY_FOR_SEARCH
                   if intent._FACET_WORDS.get(w) == "aesthetic")
    for w in empty:  # vacuity-ok: no overlap between the vocabularies is the good case
        assert intent.aesthetic_of([w], "") == "", w


def test_the_fallback_facet_map_carries_it_and_still_maps():
    orn = l0.candidate("nordic-star-ornaments")
    got = intent.listing_language(_db(), slug=orn.slug, category="ornament", season="Christmas",
                                  difficulty="beginner", techniques=["texture"],
                                  motifs=list(orn.listing.qualifiers), title=orn.title)
    assert got["mapped"] is True, got
    assert got["facets"].get("aesthetic") == "nordic", got["facets"]
    plain = intent.listing_language(_db(), slug="cloudline-baby-blanket", category="baby",
                                    season=None, difficulty="beginner",
                                    techniques=["texture"], motifs=[], title="")
    assert plain["mapped"] is True and "aesthetic" not in plain["facets"], plain["facets"]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        check(name, fn)
    sys.exit(1 if FAILS else 0)
