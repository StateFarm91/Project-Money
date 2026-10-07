"""Lane G wave 3: the Launch-0 search strategy is truthful, complete and not stuffed.

Baskets are ONE listing with three sizes; every listing uses 13 tags of <= 20 characters,
every word traces to a verified fact, demand is modelled (never measured without evidence),
category/attributes stay GATED, and the four funnel problems are kept separate.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.seo._testkit import fresh_db, run  # noqa: E402

_PLAN = {}


def plan():
    if not _PLAN:
        from brambleloop.seo import strategy

        _PLAN.update(strategy.plan())
    return _PLAN


def products():
    ps = plan()["products"]
    assert len(ps) == 5, [p["slug"] for p in ps]   # W4-PIPE: 5 Launch-0 products
    return ps


def test_five_products_and_baskets_are_one_listing_with_sizes():
    by = {p["slug"]: p for p in products()}
    assert set(by) == {"nursery-nesting-baskets", "hexagon-coaster-set",
                       "cloudline-baby-blanket", "nordic-star-ornaments",
                       "winter-village-graphghan"}
    b = by["nursery-nesting-baskets"]
    assert b["listing_unit"] == "product" and len(b["variants"]) == 3
    assert "3 Sizes" in b["title"]
    for size in ("small", "medium", "large"):
        assert size in b["description"]["text"]


def test_every_product_passes_every_check():
    ps = products()
    assert len(ps) == 5
    for p in ps:
        assert p["ok"], (p["slug"], p["blocking"])
        assert p["writes_to_etsy"] is False


def test_thirteen_tags_within_limits_and_charset():
    ps = products()
    assert len(ps) == 5
    for p in ps:
        assert len(p["tags"]) == 13, p["slug"]
        assert len({t.lower() for t in p["tags"]}) == 13
        for t in p["tags"]:
            assert len(t) <= 20 and t == t.lower() and t[0] not in "-'", t


def test_titles_buyer_first_no_repeats_under_limit():
    from brambleloop.seo import strategy

    ps = products()
    assert len(ps) == 5
    for p in ps:
        assert len(p["title"]) <= 140
        assert "crochet pattern" in p["title"].lower()[:45], p["title"]
        assert strategy.title_repeats(p["title"]) == []


def test_no_stem_stuffing():
    from brambleloop.seo import strategy

    ps = products()
    assert len(ps) == 5
    for p in ps:
        counts = strategy.stem_slot_counts(p["tags"])
        assert counts and max(counts.values()) <= strategy.MAX_STEM_SLOTS, counts


def test_demand_is_modelled_not_measured_without_evidence():
    ps = products()
    assert len(ps) == 5
    for p in ps:
        assert p["tag_basis_counts"] == {"modelled": 13}
        assert p["families"]
        for fam in p["families"]:
            assert fam["demand_basis"] == "modelled"
            assert "not demand" in fam["priority_basis"]
            for row in fam["phrases"]:
                assert row["demand_basis"] == "modelled" and row["measured"] == {}
        assert "no phrase here has measured demand" == p["demand_statement"]
    blob = json.dumps(plan()).lower()
    for word in ("search volume", "searches per month", "monthly searches"):
        assert word not in blob


def test_untrue_words_are_blocked():
    from brambleloop.products import launch0 as L
    from brambleloop.seo import facts, strategy

    cand = L.candidate("hexagon-coaster-set")
    f = facts.for_product(cand)
    saved = list(strategy.TAGS[cand.slug])
    try:
        strategy.TAGS[cand.slug] = saved[:-1] + ["easy coasters"]
        out = strategy.build(cand, f)
        assert not out["ok"]
        assert any("easy" in b for b in out["blocking"]), out["blocking"]
        strategy.TAGS[cand.slug] = saved[:-1] + ["mug rug"]
        assert not strategy.build(cand, f)["ok"]
    finally:
        strategy.TAGS[cand.slug] = saved


def test_product_licences_trace_to_source_text():
    from brambleloop.products import launch0 as L
    from brambleloop.seo import facts

    f = facts.for_product(L.candidate("cloudline-baby-blanket"))
    for w in ("diamond", "lattice", "striped", "afghan"):
        assert f.source_of(w), w
    assert f.source_of("modern") is None and f.source_of("heirloom") is None
    b = facts.for_product(L.candidate("nursery-nesting-baskets"))
    assert b.source_of("nesting") and b.source_of("3")
    assert b.source_of("bread") is None     # true of one size only, not of the product
    assert b.width_cm is None


def test_category_and_attributes_gated():
    db = fresh_db()
    from brambleloop.seo import strategy

    p = strategy.plan(db)
    assert p["products"]
    for prod in p["products"]:
        assert prod["category"]["status"] == "GATED(etsy_api)"
        assert prod["category"]["seller_taxonomy_id"] is None
        assert prod["category"]["buyer_path_status"] == "UNVERIFIED"
        assert prod["attributes"]["status"] == "GATED(etsy_api)"


def test_description_natural_and_honest():
    ps = products()
    assert len(ps) == 5
    for p in ps:
        d = p["description"]
        assert d["final"] is False and d["findings"] == []
        text = d["text"]
        assert "calculated from the stated gauge" in text
        assert "no finished item is shipped" in text
        for bad in ("compiler", "AI", "machine", "guaranteed", "tested", "photograph"):
            assert bad not in text, bad
        assert any(b["block"] == "disclosure" for b in d["required_blocks"])


def test_funnel_stages_are_separate():
    from brambleloop.seo import strategy

    assert set(strategy.FUNNEL) == {"matching", "ranking", "ctr", "conversion"}
    for stage in ("ranking", "ctr", "conversion"):
        assert strategy.FUNNEL[stage]["status_now"].startswith("UNKNOWN")


def test_existing_validator_agrees():
    from brambleloop.products import launch0 as L
    from brambleloop.seo import facts, truth

    ps = products()
    assert len(ps) == 5
    for p in ps:
        f = facts.for_product(L.candidate(p["slug"]))
        v = truth.validate_listing(p["title"], p["tags"], f, competitors=[])
        assert v["ok"], v["blocking"]


if __name__ == "__main__":
    run(globals())
