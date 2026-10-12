"""Creative performance learning by asset style (#82).

Every outcome row below is a synthetic test fixture: nothing is live, and the empty-database
test is the one that describes the company today.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.creative import style_learning as SL  # noqa: E402

TWIN_HERO = "twin_render/product_first/hero"
MODEL_HERO = "generated/model_bearing/fit"


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _frames(db, slug: str, *, model: bool = False) -> None:
    from brambleloop.core.models import ListingAsset

    with db.session() as s:
        if model:
            s.add(ListingAsset(product_slug=slug, version="1.0.0", position=1,
                               asset_class="AI_LIFESTYLE_CONCEPT", role="fit",
                               claims={"carries_model": True, "generated": True}))
        else:
            s.add(ListingAsset(product_slug=slug, version="1.0.0", position=1,
                               asset_class="DIGITAL_TWIN_RENDER", role="hero", claims={}))
        s.add(ListingAsset(product_slug=slug, version="1.0.0", position=2,
                           asset_class="INFOGRAPHIC", role="size", claims={}))


def _outcome(db, slug, impressions, visits, orders=0, **kw):
    return SL.record_outcome(db, product_slug=slug, version="1.0.0",
                             period_start="2027-01-01", period_end="2027-01-31",
                             impressions=impressions, visits=visits, orders=orders,
                             source="fixture: synthetic stats export", **kw)


def test_tagging_is_deterministic_from_the_frame_record():
    a = SL.tag("DIGITAL_TWIN_RENDER", "hero", {})
    assert a["style"] == TWIN_HERO and a["deterministic_render"] and not a["generated"]
    b = SL.tag("AI_LIFESTYLE_CONCEPT", "fit", {"carries_model": True})
    assert b["style"] == MODEL_HERO and b["generated"]
    c = SL.tag("DIGITAL_TWIN_RENDER", "hero", {"shot": "flatlay"})
    assert c["style"] == "twin_render/product_first/flatlay"
    assert SL.tag("SOMETHING_NEW", "x", {})["source"] == "unknown"
    assert SL.tag("DIGITAL_TWIN_RENDER", "hero", {}) == a


def test_an_empty_database_is_unmeasured_with_reasons_and_minimums():
    db = _db()
    out = SL.by_style(db)
    assert out["status"] == SL.UNMEASURED
    assert "nothing is live" in out["why"]
    assert str(SL.MIN_IMPRESSIONS) in out["needs"]
    learned = SL.learn(db)
    assert learned["promoted"] == [] and learned["status"] == SL.UNMEASURED


def test_the_minimum_n_boundary_n_minus_one_refuses_and_n_measures():
    db = _db()
    for slug in ("p1", "p2", "p3"):
        _frames(db, slug)
    # 199 impressions across three listings: one short.
    _outcome(db, "p1", 67, 3)
    _outcome(db, "p2", 66, 3)
    _outcome(db, "p3", 66, 3)
    ctr = SL.by_style(db)["by_style"][TWIN_HERO]["search_grid_ctr"]
    assert ctr["status"] == SL.UNMEASURED and "199" in ctr["why"], ctr
    _outcome(db, "p3", 67, 3)   # the same period rewritten: now exactly 200
    ctr = SL.by_style(db)["by_style"][TWIN_HERO]["search_grid_ctr"]
    assert ctr["status"] == SL.MEASURED and ctr["n"] == SL.MIN_IMPRESSIONS
    assert ctr["value"] == round(9 / 200, 5)


def test_a_style_on_too_few_listings_is_unmeasured_however_many_impressions():
    db = _db()
    for slug in ("p1", "p2"):
        _frames(db, slug)
        _outcome(db, slug, 5000, 100)
    ctr = SL.by_style(db)["by_style"][TWIN_HERO]["search_grid_ctr"]
    assert ctr["status"] == SL.UNMEASURED and "listing" in ctr["why"]


def test_impossible_outcomes_are_refused():
    db = _db()
    for bad in ({"impressions": 10, "visits": 11},
                {"impressions": 10, "visits": 5, "orders": 6},
                {"impressions": 10, "visits": 5, "first_frame_engagements": 3}):
        try:
            SL.record_outcome(db, product_slug="x", period_start="2027-01-01",
                              period_end="2027-01-02", source="s", **bad)
        except SL.StyleLearningRefused:
            continue
        raise AssertionError(f"accepted {bad}")
    try:
        SL.record_outcome(db, product_slug="x", period_start="2027-01-01",
                          period_end="2027-01-02", impressions=1, visits=0, source="")
        raise AssertionError("accepted a sourceless number")
    except SL.StyleLearningRefused:
        pass


def _seeded() -> Database:
    db = _db()
    for slug in ("t1", "t2", "t3"):
        _frames(db, slug)
        _outcome(db, slug, 1000, 80, orders=2, first_frame_views=300,
                 first_frame_engagements=30)
    for slug in ("m1", "m2", "m3"):
        _frames(db, slug, model=True)
        _outcome(db, slug, 1000, 20, orders=1)
    return db


def test_a_seeded_database_measures_every_metric_by_style():
    out = SL.by_style(_seeded())
    twin = out["by_style"][TWIN_HERO]
    assert twin["search_grid_ctr"]["value"] == 0.08
    assert twin["first_frame_engagement"]["value"] == 0.1
    assert twin["conversion"]["status"] == SL.MEASURED
    assert twin["experiment_outcomes"]["status"] == SL.UNMEASURED
    assert out["by_style"][MODEL_HERO]["search_grid_ctr"]["value"] == 0.02


def test_promotion_records_a_measured_winner_as_a_preference():
    db = _seeded()
    out = SL.promote(db, TWIN_HERO, rule={"prefer": TWIN_HERO, "for_role": "hero",
                                          "changes": ["lighting"]})
    assert out["promoted"] and out["evidence"]["lift"] >= SL.PROMOTION_MIN_LIFT
    assert SL.knowledge(db)[0]["key"] == f"hero:{TWIN_HERO}"


def test_the_loser_is_not_promoted_and_nothing_is_promoted_without_data():
    db = _seeded()
    try:
        SL.promote(db, MODEL_HERO, rule={"prefer": MODEL_HERO, "for_role": "hero",
                                         "changes": []})
        raise AssertionError("promoted a style that lost")
    except SL.PromotionRefused as e:
        assert "below" in str(e)
    try:
        SL.promote(_db(), TWIN_HERO, rule={"prefer": TWIN_HERO, "for_role": "hero",
                                           "changes": []})
        raise AssertionError("promoted with no data")
    except SL.PromotionRefused as e:
        assert "UNMEASURED" in str(e)


def test_a_promotion_that_changes_product_truth_policy_or_identity_is_refused():
    """Even for the measured winner: performance never overrides truth, policy or identity."""
    db = _seeded()
    for changes, domain in ((["width_cm"], "product_truth"), (["colors"], "product_truth"),
                            (["asset_class"], "policy"), (["ai_disclosure"], "policy"),
                            (["model_identity"], "identity"), (["brand_voice"], "identity")):
        try:
            SL.promote(db, TWIN_HERO, rule={"prefer": TWIN_HERO, "for_role": "hero",
                                            "changes": changes})
            raise AssertionError(f"promoted a rule changing {changes}")
        except SL.PromotionRefused as e:
            assert domain in str(e), (changes, str(e))
    assert SL.knowledge(db) == []


def test_a_generated_style_cannot_be_preferred_for_a_proof_frame():
    try:
        SL.check_rule(MODEL_HERO, {"prefer": MODEL_HERO, "for_role": "size", "changes": []})
        raise AssertionError("a generated image was preferred as evidence")
    except SL.PromotionRefused as e:
        assert "asset truth" in str(e)
    try:
        SL.check_rule(TWIN_HERO, {"prefer": TWIN_HERO, "for_role": "hero",
                                  "changes": ["mystery"]})
        raise AssertionError("an unknown change was assumed harmless")
    except SL.PromotionRefused:
        pass


def test_the_daily_pass_promotes_only_the_measured_winner():
    db = _seeded()
    out = SL.learn(db)
    assert out["promoted"] == [f"hero:{TWIN_HERO}"]
    assert [r["style"] for r in out["refused"]] == [MODEL_HERO]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
