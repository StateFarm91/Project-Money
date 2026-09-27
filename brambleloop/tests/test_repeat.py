"""The repeat engine: recommendation runs today, repeat rate waits for customers (#252).

Order rows below are test fixtures, not customers.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.commerce import cohorts  # noqa: E402
from brambleloop.commerce import repeat as R  # noqa: E402
from brambleloop.radar.opportunity import POOL  # noqa: E402

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _a_product():
    return next(s for s in POOL if not s.is_bundle)


def test_a_recommendation_never_points_at_what_the_buyer_owns():
    for seed in [s for s in POOL if not s.is_bundle][:12]:
        out = R.recommend(seed.slug, today=date(2026, 3, 1))
        shown = {r["slug"] for k in ("next_project", "matching_collection", "future_season")
                 for r in out[k]}
        assert seed.slug not in shown
        assert not shown & set(out["never_recommended"])
        for kind in ("next_project", "matching_collection", "future_season"):
            assert len(out[kind]) <= R.PER_KIND


def test_future_season_is_a_season_still_ahead_and_not_the_one_bought_for():
    seed = _a_product()
    out = R.recommend(seed.slug, today=date(2026, 3, 1))
    assert out["future_season"], "an empty list would pass the loop below vacuously"
    for row in out["future_season"]:
        assert row["season"] != seed.season
        assert "opens in" in row["why"]


def test_an_unknown_product_is_refused():
    try:
        R.recommend("no-such-pattern-anywhere")
    except R.RepeatRefused:
        return
    raise AssertionError("recommended after a product nobody sells")


def test_no_orders_is_a_refusal_not_a_zero():
    out = R.windows([], axis="first_product", value="x")
    assert out["measurable"] is False and out["status"] == "UNMEASURED"
    assert out["horizons_days"] == [30, 60, 90, 180]
    try:
        R.windows([], axis="favourite_colour", value="x")
    except R.RepeatRefused:
        pass
    else:
        raise AssertionError("an axis nobody named was measured")


def test_windows_are_measured_at_the_floor_and_unmeasured_below_it():
    def orders(n):
        rows = []
        for i in range(n):
            rows.append({"customer_ref": f"fixture-{i}", "at": T0, "product_slug": "p",
                         "category": "hats", "season": "none", "contribution_cad": 5.0,
                         "revenue_cad": 8.0})
            if i % 2 == 0:
                rows.append({"customer_ref": f"fixture-{i}", "at": T0 + timedelta(days=45),
                             "product_slug": "q", "category": "hats", "season": "none",
                             "contribution_cad": 5.0, "revenue_cad": 8.0})
        return rows

    as_of = T0 + timedelta(days=365)
    thin = R.windows(orders(cohorts.MIN_COHORT_N - 1), axis="first_product", value="p",
                     as_of=as_of)
    assert thin["measurable"] is False
    full = R.windows(orders(cohorts.MIN_COHORT_N), axis="first_product", value="p",
                     as_of=as_of)
    assert full["measurable"] is True
    assert full["windows"]["30d"]["value"] == 0.0     # the repeat came on day 45
    assert full["windows"]["60d"]["value"] == 0.5


def test_state_separates_what_runs_today_from_what_waits():
    state = R.state()
    assert state["recommendation"]["executable"] is True
    assert state["measurement"]["executable"] is False
    assert state["measurement"]["status"] == "UNMEASURED"


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
