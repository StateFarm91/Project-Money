"""The post-season learning harvest (#298).

Orders below are synthetic fixtures for a Halloween that, in this test, has passed. The
empty-database tests are the company today: nothing harvested, the calendar unchanged.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.seasonal import harvest as H  # noqa: E402
from brambleloop.seasonal import leadtime  # noqa: E402

HALLOWEEN = date(2026, 10, 31)
AFTER = date(2026, 11, 30)
# Orders per week, keyed by days before the event: rises, peaks 14 days out, decays.
CURVE = {42: 1, 35: 2, 28: 3, 21: 4, 14: 5, 7: 3, 0: 1}   # 19 orders


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _orders(db, curve: dict[int, int], *, extra: int = 0):
    from brambleloop.core.models import Customer, Order

    with db.session() as s:
        cust = Customer(customer_ref="fixture-buyer")
        s.add(cust)
        s.flush()
        n = 0
        weeks = [(d, c) for d, c in curve.items()] + [(0, extra)]
        for days, count in weeks:
            for _ in range(count):
                n += 1
                at = datetime.combine(HALLOWEEN - timedelta(days=days + 1), datetime.min.time(),
                                      tzinfo=timezone.utc)
                s.add(Order(customer_id=cust.id, external_ref=f"h-{n}", at=at,
                            product_slug="spooky-garland", category="ornaments",
                            price_cad=8.0, revenue_cad=8.0, contribution_cad=5.0,
                            acquisition_source="etsy_search" if n % 2 else "pinterest",
                            search_term="halloween garland crochet"))


def test_an_event_that_has_not_passed_is_refused():
    out = H.harvest(_db(), "Christmas", today=date(2026, 9, 27),
                    occurrence=date(2026, 12, 25))
    assert out["status"] == H.NOT_PASSED and "has not passed" in out["why"]


def test_an_unknown_event_is_refused():
    try:
        H.harvest(_db(), "Arbor Day")
        raise AssertionError("harvested an event nobody named")
    except H.HarvestRefused:
        pass


def test_a_passed_event_with_no_orders_is_refused_and_recorded_with_its_reason():
    db = _db()
    out = H.harvest(db, "Christmas", today=date(2026, 9, 27))
    assert out["occurrence"] == "2025-12-25"
    assert out["status"] == H.REFUSED and "0 order(s)" in out["why"]
    adj = H.timing_adjustments(db, "Christmas")
    assert adj["status"] == H.UNMEASURED and "0 order(s)" in adj["why"]
    assert H.adjusted_assumptions(db, "Christmas") is leadtime.DEFAULT


def test_the_order_minimum_boundary():
    db = _db()
    _orders(db, CURVE)          # 19
    out = H.harvest(db, "Halloween", today=AFTER, occurrence=HALLOWEEN)
    assert out["status"] == H.REFUSED and "19 order(s)" in out["why"]
    db = _db()
    _orders(db, CURVE, extra=1)  # 20
    out = H.harvest(db, "Halloween", today=AFTER, occurrence=HALLOWEEN)
    assert out["status"] == H.MEASURED and out["orders"] == H.MIN_EVENT_ORDERS


def test_a_measured_harvest_joins_every_dimension_and_reads_the_curve():
    db = _db()
    _orders(db, CURVE, extra=1)
    out = H.harvest(db, "Halloween", today=AFTER, occurrence=HALLOWEEN)
    worked = out["worked"]
    assert set(worked) == {"concepts", "palettes", "categories", "thumbnails",
                           "search_terms", "prices", "bundles", "channels"}
    assert worked["categories"]["ornaments"]["status"] == H.MEASURED
    assert worked["prices"]["6_to_10"]["orders"] == 20
    t = out["timing"]["orders"]
    assert t["status"] == H.MEASURED
    assert t["peak_days_before"] == 14 and t["demand_began_days_before"] == 35
    # The extra order lands in the last week, so decay is first seen the week after.
    assert t["decay_observed"] and t["decayed_days_before"] == -7
    assert out["timing"]["price_observations"]["status"] == H.UNMEASURED


def test_the_learned_timing_is_what_next_years_calendar_reads():
    db = _db()
    _orders(db, CURVE, extra=1)
    H.harvest(db, "Halloween", today=AFTER, occurrence=HALLOWEEN)
    adj = H.timing_adjustments(db, "Halloween")
    assert adj["status"] == H.MEASURED and adj["demand_began_days_before"] == 35
    raised = H.adjusted_assumptions(db, "Halloween")
    base = leadtime.DEFAULT.planning_buffer_days
    assert all(raised.planning_buffer_days[k] >= v for k, v in base.items())
    assert raised.planning_buffer_days[leadtime.QUICK] > base[leadtime.QUICK]
    assert raised.source_of("planning_buffer_days") == "measured"


def test_the_daily_pass_acts_only_on_passed_events_and_does_not_redo_a_measured_one():
    db = _db()
    _orders(db, CURVE, extra=1)
    first = H.harvest_due(db, today=AFTER)
    assert "Halloween" in first["measured"]
    assert all(date.fromisoformat(r["occurrence"]) < AFTER for r in first["ran"])
    second = H.harvest_due(db, today=AFTER)
    assert any(s["event"] == "Halloween" for s in second["skipped"])


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
