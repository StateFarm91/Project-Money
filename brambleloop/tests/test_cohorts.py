"""Customer cohorts: a reference not a person, one axis per row, and no metric under the floor.

#11 and #12. Every customer and order here is a test fixture in a throwaway database; the
production tables are empty and `state()` says so. The floor tests are the point: below
`MIN_COHORT_N` a cohort metric is UNMEASURED with its reason, never a number with a caveat.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.commerce import cohorts as C  # noqa: E402

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _populate(db, n: int, *, repeaters: int, gap_days: int = 20) -> None:
    """n fixture buyers of one product; the first `repeaters` buy again after gap_days."""
    for i in range(n):
        ref = f"fixture-buyer-{i}"
        C.record_customer(db, ref, at=T0, acquisition_source="etsy_search",
                          first_product_slug="mosaic-throw", first_category="blankets",
                          first_season="none")
        C.record_order(db, ref, f"fixture-order-{i}-a", product_slug="mosaic-throw",
                       at=T0, category="blankets", price_cad=12.0, contribution_cad=9.0)
        if i < repeaters:
            C.record_order(db, ref, f"fixture-order-{i}-b", product_slug="cable-hat",
                           at=T0 + timedelta(days=gap_days), category="hats",
                           price_cad=8.0, contribution_cad=6.0)


def test_an_empty_company_reports_unmeasured_and_the_owner_gated_source():
    state = C.state(_db())
    assert state["customers"] == 0 and state["orders"] == 0
    assert state["readable_cohorts"] == 0
    assert state["source"]["status"] == "OWNER-GATED"
    assert state["source"]["scope"] == "transactions_r"
    assert "UNMEASURED" in state["note"]


def test_a_customer_reference_is_never_personal_data_and_an_order_needs_a_buyer():
    db = _db()
    for bad in ("", "  ", "someone@example.com"):
        try:
            C.record_customer(db, bad)
        except C.CohortRefused:
            continue
        raise AssertionError(f"accepted customer_ref {bad!r}")
    try:
        C.record_order(db, "nobody", "o-1", product_slug="x")
    except C.CohortRefused:
        pass
    else:
        raise AssertionError("an order for nobody was recorded")
    C.record_customer(db, "fixture-1")
    try:
        C.record_order(db, "fixture-1", "o-2", product_slug="x", price_cad=5.0,
                       contribution_cad=9.0)
    except C.CohortRefused:
        pass
    else:
        raise AssertionError("contribution above revenue was accepted")


def test_every_customer_joins_every_axis_and_the_first_hundred_are_the_validation_cohort():
    db = _db()
    out = C.record_customer(db, "fixture-a", first_product_slug="p", first_category="hats")
    assert set(out["memberships"]) == set(C.AXES)
    assert out["memberships"]["validation"] == "first_hundred"
    assert C.record_customer(db, "fixture-a")["created"] is False
    try:
        C.members(db, "favourite_colour", "red")
    except C.CohortRefused:
        pass
    else:
        raise AssertionError("an axis nobody named was read")


def test_below_the_floor_every_metric_is_unmeasured_not_a_number():
    db = _db()
    _populate(db, C.MIN_COHORT_N - 1, repeaters=10)
    m = C.metrics(db, "first_product", "mosaic-throw", as_of=T0 + timedelta(days=400))
    assert m["readable"] is False
    for h in ("30d", "60d", "90d", "180d"):
        assert m["repeat_rate"][h]["status"] == "UNMEASURED"
        assert m["repeat_rate"][h]["value"] is None
    assert m["time_to_repeat_days"]["status"] == "UNMEASURED"
    assert m["aov_cad"]["status"] == "UNMEASURED"
    assert m["lifetime_contribution"]["status"] == "UNMEASURED"
    assert m["category_affinity"]["status"] == "UNMEASURED"


def test_at_the_floor_the_metrics_are_measured_and_right_censored():
    db = _db()
    n = C.MIN_COHORT_N
    _populate(db, n, repeaters=n, gap_days=20)
    m = C.metrics(db, "first_product", "mosaic-throw", as_of=T0 + timedelta(days=400))
    assert m["readable"] is True
    assert m["repeat_rate"]["30d"]["value"] == 1.0
    assert m["time_to_repeat_days"]["value"] == 20
    assert m["aov_cad"]["value"] == 10.0
    assert m["lifetime_contribution"]["value"] == 15.0
    # Twenty days in, nobody has had thirty days to repeat: censored, not disloyal.
    young = C.metrics(db, "first_product", "mosaic-throw", as_of=T0 + timedelta(days=20))
    assert young["repeat_rate"]["30d"]["status"] == "UNMEASURED"


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
