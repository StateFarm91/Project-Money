"""D1 (catalogue unblock, 2026-11-22): the tag generator never emits a semantic duplicate.

hexie-coaster-set and mosaic-placemat-pair were refused TAG_SEMANTIC_DUPLICATE ('coaster
crochet' beside 'crochet coaster'). `choose_tags` already folds plurals, word order and
synonyms, but listing.seo's two post-passes re-added tags by string comparison: #240's
`_diversify_tags` topped the fresh choice up from the original set, and #237's
`_drop_vanity_tags` refilled freed slots from earning terms and queries. The gate
(`tag_diversity_problems`) is unchanged; the generator now asks the gate's own rule.

Listings below are TEST FIXTURES in a throwaway database; nothing is published.

Run: cd brambleloop && python3 tests/test_tag_semantic_dedupe.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import search as search_mod  # noqa: E402
from brambleloop.commerce.search import Query  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Listing, OperatingReading  # noqa: E402
from brambleloop.runtime import release  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="tag_dedupe_")


def _db(name: str) -> Database:
    db = Database(f"sqlite:///{_TMP}/{name}.sqlite")
    db.create_all()
    return db


def _coaster_queries() -> list[Query]:
    # The hexie-coaster-set shape: the same search phrased three ways, plus other intents.
    phrases = ["coaster crochet", "crochet coaster", "hexie coasters", "hexagon coaster",
               "crochet coaster set", "coaster pattern pdf", "table decor crochet",
               "housewarming gift", "cotton coasters", "granny hexagon", "drink mat crochet",
               "kitchen crochet", "beginner coaster", "home decor pattern", "boho coasters",
               "scrap yarn project", "quick crochet gift", "mug rug pattern"]
    return [Query(phrase=p, demand=0.9 - i * 0.03, competition=0.2)
            for i, p in enumerate(phrases)]


def test_helper_is_the_gates_rule():
    assert search_mod.is_semantic_repeat("coaster crochet", ["crochet coaster"])
    assert search_mod.is_semantic_repeat("hexie coasters", ["hexagon coaster"])
    assert search_mod.is_semantic_repeat("crochet placemats", ["placemat crochet"])
    assert not search_mod.is_semantic_repeat("crochet coaster set", ["crochet coaster"])
    tags = ["crochet coaster", "coaster crochet", "hexie coasters", "hexagon coaster"]
    out = search_mod.distinct_tags(tags)
    assert out == ["crochet coaster", "hexie coasters"]
    assert not search_mod.tag_diversity_problems(out)


def test_diversify_top_up_never_readds_a_semantic_duplicate():
    """A rival spends 'coaster crochet'; the fresh choice picks 'crochet coaster'; the
    top-up used to put 'coaster crochet' back beside it."""
    db = _db("diversify")
    queries = _coaster_queries()
    tags = search_mod.choose_tags(queries)
    assert not search_mod.tag_diversity_problems(tags), tags
    assert "coaster crochet" in tags
    with db.session() as s:
        s.add(Listing(product_slug="fixture-rival", version="1.0.0", title="Rival",
                      description="rival", tags=["coaster crochet"] + tags[3:6],
                      price_cad=5.0))
    new, reading = release._diversify_tags(db, "hexie-coaster-set", queries, tags)
    assert not search_mod.tag_diversity_problems(new), (new, reading)
    assert len(set(new)) == len(new)


def test_vanity_refill_never_adds_a_semantic_duplicate():
    """mosaic-placemat-pair: a vanity tag's slot was refilled with 'placemat crochet'
    beside 'crochet placemat' because the refill compared lowercase strings."""
    db = _db("vanity")
    with db.session() as s:
        s.add(OperatingReading(kind=release.ATTRIBUTION_KIND, period_key="fixture",
                               at=datetime(2026, 11, 20, tzinfo=timezone.utc),
                               payload={"period_key": "fixture", "joined": {
                                   "vanity_terms": ["mosaic xmas"],
                                   "terms": [{"term": "placemat crochet",
                                              "contribution_per_visit_cad": 0.4},
                                             {"term": "mosaic table mat",
                                              "contribution_per_visit_cad": 0.2}]}}))
    tags = ["crochet placemat", "mosaic xmas", "overlay mosaic"]
    queries = [Query(phrase=p, demand=0.5, competition=0.2)
               for p in ("crochet placemats", "dining decor")]
    new, got = release._drop_vanity_tags(db, queries, tags)
    assert got["vanity_dropped"] == ["mosaic xmas"]
    assert not search_mod.tag_diversity_problems(new), new
    assert new == ["crochet placemat", "overlay mosaic", "mosaic table mat"], new


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"\n  {sum(1 for n in globals() if n.startswith('test_')) - fails} passing, "
          f"{fails} failing")
    sys.exit(1 if fails else 0)
