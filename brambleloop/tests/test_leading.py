"""The leading-indicator dashboard: ten indicators, none defaulted, success refused (#263).

Observed counts and orders below are test fixtures. With an empty database only release
velocity -- an internal fact -- is measured, and success is not claimable.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.scale import leading as L  # noqa: E402

REQUIREMENT_263_NAMES = ("qualified impressions", "CTR", "favourites/cart signals",
                         "conversion", "bundle attach", "email/content traffic",
                         "creator traffic", "search trend direction", "support defects",
                         "release velocity")


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _live_listing(db):
    from brambleloop.core.models import Listing

    with db.session() as s:
        s.add(Listing(product_slug="fixture", version="1.0.0", title="t", description="d",
                      etsy_listing_id="123"))


def test_there_are_ten_indicators_one_per_name_in_the_requirement():
    assert len(L.INDICATORS) == len(REQUIREMENT_263_NAMES) == 10


def test_an_empty_company_measures_only_release_velocity_and_claims_nothing():
    out = L.dashboard(_db())
    assert out["measured"] == ["release_velocity"]
    assert out["indicators"]["release_velocity"]["value"] == 0
    for key in out["unmeasured"]:
        row = out["indicators"][key]
        assert row["status"] == L.UNMEASURED and row["value"] is None
        assert row["why"] and row["needs"]
    assert out["success"]["claimable"] is False


def test_listing_surface_metrics_wait_for_a_live_listing_even_when_numbers_are_supplied():
    out = L.dashboard(_db(), observed={"impressions": 5000, "visits": 200})
    for key in ("qualified_impressions", "ctr", "favourites_and_cart"):
        assert out["indicators"][key]["status"] == L.UNMEASURED
        assert "no listing is live" in out["indicators"][key]["why"]


def test_supplied_numbers_on_a_live_listing_are_measured_and_success_still_refused():
    db = _db()
    _live_listing(db)
    out = L.dashboard(db, observed={"impressions": 5000, "visits": 200, "favourites": 12,
                                    "creator_visits": 3,
                                    "search_trend": {"direction": "rising",
                                                     "source": "fixture trend export",
                                                     "window": "90d"},
                                    "source": "fixture Stats export"})
    ind = out["indicators"]
    assert ind["qualified_impressions"]["value"] == 5000
    assert ind["ctr"]["value"] == 0.04
    assert ind["conversion"]["value"] == 0.0
    assert ind["creator_traffic"]["status"] == L.MEASURED
    assert ind["search_trend_direction"]["value"] == "rising"
    assert out["success"]["claimable"] is False, "success declared from leading indicators"


def test_a_trend_without_a_source_and_a_negative_count_are_refused():
    for observed in ({"search_trend": {"direction": "rising"}}, {"impressions": -1},
                     {"visits": 2.5}):
        try:
            L.dashboard(_db(), observed=observed)
        except L.LeadingRefused:
            continue
        raise AssertionError(f"accepted {observed}")


def test_orders_make_success_a_question_about_orders_and_rates_wait_for_the_floor():
    from brambleloop.commerce import cohorts

    db = _db()
    cohorts.record_customer(db, "fixture-buyer")
    cohorts.record_order(db, "fixture-buyer", "fixture-order", product_slug="p",
                         price_cad=8.0, contribution_cad=6.0)
    out = L.dashboard(db)
    assert out["success"]["claimable"] is True
    assert "contribution" in out["success"]["why"]
    assert out["indicators"]["bundle_attach"]["status"] == L.UNMEASURED
    assert out["indicators"]["support_defects"]["status"] == L.UNMEASURED


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{sum(1 for n in globals() if n.startswith('test_')) - fails} passing, {fails} failing")
    sys.exit(1 if fails else 0)
