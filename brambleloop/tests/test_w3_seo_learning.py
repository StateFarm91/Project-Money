"""Lane G wave 3: learning hooks are UNKNOWN until data exists, then diagnose one stage.

No count is ever rendered as 0 when it was not measured; carts stay UNKNOWN (no source);
the four funnel problems stay separate; shop-level recommendations are checkable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.seo._testkit import fresh_db, run  # noqa: E402
from brambleloop.seo import learning  # noqa: E402


def test_empty_db_everything_unknown_never_zero():
    f = learning.funnel(fresh_db())
    per = f["per_product"]
    assert len(per) == 5      # W4-PIPE: five Launch-0 products
    for slug, row in per.items():
        for sig in ("impressions", "clicks", "favourites", "orders", "carts"):
            assert row[sig]["status"] == "UNKNOWN" and row[sig]["value"] is None, (slug, sig)
    assert f["search_visibility"]["status"] == "UNKNOWN"
    assert learning.proposals(fresh_db()) == []
    json.dumps(f, default=str)


def _outcome(db, slug, imp, vis, fav, orders):
    from brambleloop.core.models import ListingOutcome

    with db.session() as s:
        s.add(ListingOutcome(product_slug=slug, period_start="2026-11-01",
                             period_end="2026-11-07", impressions=imp, visits=vis,
                             favourites=fav, orders=orders, source="test"))


def test_low_exposure_is_matching_not_ctr():
    db = fresh_db()
    _outcome(db, "hexagon-coaster-set", 40, 3, None, None)
    row = learning.funnel(db)["per_product"]["hexagon-coaster-set"]
    assert row["diagnosis"]["stage"] == "matching_or_ranking"
    assert row["rates"]["ctr"] is None and "insufficient" in row["rates"]["ctr_basis"]
    assert row["favourites"]["status"] == "UNKNOWN"     # None is not 0
    assert row["carts"]["status"] == "UNKNOWN"
    props = learning.proposals(db)
    assert props and props[0]["stage"] == "matching_or_ranking"
    assert props[0]["writes_to_etsy"] is False


def test_shown_but_not_clicked_is_ctr():
    db = fresh_db()
    _outcome(db, "cloudline-baby-blanket", 1200, 10, 1, 0)
    d = learning.funnel(db)["per_product"]["cloudline-baby-blanket"]["diagnosis"]
    assert d["stage"] == "ctr"


def test_clicked_is_conversion_with_measured_rates():
    db = fresh_db()
    _outcome(db, "nursery-nesting-baskets", 2000, 80, 6, 2)
    row = learning.funnel(db)["per_product"]["nursery-nesting-baskets"]
    assert row["diagnosis"]["stage"] == "conversion"
    assert row["rates"]["ctr"] == 0.04 and row["rates"]["conversion"] == 0.025
    assert row["orders"]["basis"] == "measured"


def test_thresholds_are_labelled_modelled():
    f = learning.funnel(fresh_db())
    assert "modelled" in f["thresholds"]["basis"]
    sig = {s["signal"]: s for s in learning.SIGNALS}
    assert sig["carts"]["source"] is None


def test_shop_recommendation_checks_clean_and_catches_bad_copy():
    from brambleloop.seo import shop

    r = shop.review()
    assert not [x for x in r["recommendation_findings"] if x["severity"] == "fail"]
    assert not r["recommendation_findings"], r["recommendation_findings"]
    bad = shop.check_shop_copy({
        "shop_title": "AI compiled crochet crochet patterns, the best verified patterns ever",
        "announcement": "Welcome. Verified by our compiler.",
        "sections": ["A section name that is far too long for Etsy"]})
    codes = {x["code"] for x in bad}
    assert {"SHOP_TITLE_TOO_LONG", "TECH_FOREGROUNDED", "ANNOUNCEMENT_CATEGORY_LATE",
            "SECTION_NAME_TOO_LONG", "UNSUPPORTABLE_CLAIM", "SHOP_TITLE_REPEATS"} <= codes
    # an unverified limit is a warning, never a silent pass and never a hard fail
    too_long = [x for x in bad if x["code"] == "SHOP_TITLE_TOO_LONG"]
    assert too_long and too_long[0]["severity"] == "warn"


def test_status_summary_carries_learning_unknown():
    from brambleloop.seo import status

    s = status.summary(fresh_db())
    per = s["w3"]["learning"]["per_product"]
    assert per
    for row in per.values():
        assert set(row.values()) == {"UNKNOWN"}


if __name__ == "__main__":
    run(globals())
