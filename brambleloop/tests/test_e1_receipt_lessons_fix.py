"""eng/e1-receipt-lessons-fix: review of 76fe0dd3 (WS6 E1 receipt lessons).

M1  -- an order whose Offsite Ads attribution is UNKNOWN (Etsy's ledger not read for it;
       `offsite_ad_attributed` defaults False) was counted as organic demand and could publish a
       `commercial_demand` lesson. Only orders `paid_media.offsite_attribution(o) is False`
       count, and a category holding unread orders is UNMEASURED (its rate would be a guess).
LOW -- views include ad-bought views and say so; the job audit carries the official reading;
       the views count is stored under `views`, never `visits`; the order window is the
       snapshots' own timestamps, not whole days either side.

Every order, view and listing here is a TEST FIXTURE.
Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_e1_receipt_lessons_fix.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select, update  # noqa: E402

from brambleloop.core.models import AuditLog, Lesson, Order, OperatingReading  # noqa: E402
from brambleloop.commerce.listing_outcomes import SNAPSHOT_KIND  # noqa: E402
from brambleloop.improve import commercial_lessons as CL  # noqa: E402
from test_ws6_e1_receipt_lessons import PRODUCTS, _db, _order, _two_week_window  # noqa: E402


def _ledger_read(db, fee: float = 0.0, slug: str | None = None):
    """Etsy's payment-account ledger was read for these orders: no Offsite Ads fee."""
    with db.session() as s:
        q = update(Order).values(offsite_ads_fee_cad=fee)
        if slug:
            q = q.where(Order.product_slug == slug)
        s.execute(q)


def _three_categories(db, *, unread: str | None = None):
    _two_week_window(db)
    _order(db, "market-basket-small", 20, ledger_fee=None)
    _order(db, "hexagon-coaster-set", 4, ledger_fee=None)
    _order(db, "cloudline-baby-blanket", 2, ledger_fee=None)
    for slug in PRODUCTS:
        if slug != unread:
            _ledger_read(db, 0.0, slug)


def test_m1_orders_with_unknown_offsite_attribution_never_publish_demand():
    db = _db()
    _three_categories(db, unread="market-basket-small")
    basket = CL._category_and_family("market-basket-small")[0]
    v = CL.verdicts(db, CL.OFFICIAL)
    rec = v["categories"][basket]
    assert rec["verdict"] is None and rec["state"] == CL.UNMEASURED, rec
    assert rec["orders"] == 0 and rec["orders_attribution_unknown"] == 20, rec
    out = CL.record_lessons(db)
    assert not [p for p in out["published"]
                if p["basis"] == CL.OFFICIAL and p["category"] == basket], out["published"]
    with db.session() as s:
        assert not [r for r in s.scalars(select(Lesson).where(Lesson.subject == CL.DEMAND))
                    if r.evidence_ref.startswith(f"commercial:official:{basket}:")]


def test_m1_ledger_read_organic_orders_still_measure():
    db = _db()
    _three_categories(db)
    basket = CL._category_and_family("market-basket-small")[0]
    v = CL.verdicts(db, CL.OFFICIAL)
    assert v["categories"][basket]["verdict"] == CL.DEMAND, v["categories"]
    assert v["categories"][basket]["orders_attribution_unknown"] == 0


def test_m1_an_offsite_fee_excludes_the_order():
    db = _db()
    _three_categories(db)
    _ledger_read(db, 1.25, "market-basket-small")       # Etsy charged an Offsite Ads fee
    basket = CL._category_and_family("market-basket-small")[0]
    assert CL.official_groups(db)[basket].orders == 0


def test_low_views_are_stored_as_views_never_visits():
    db = _db()
    _three_categories(db)
    v = CL.verdicts(db, CL.OFFICIAL)
    for rec in v["categories"].values():
        assert "views" in rec and "visits" not in rec, rec
    assert "views" in v["shop"] and "visits" not in v["shop"], v["shop"]
    # The export basis keeps visits.
    assert CL.verdicts(db, CL.EXPORT)["denominator"] == "visits"


def test_low_views_say_they_include_ad_driven_views():
    db = _db()
    _three_categories(db)
    v = CL.verdicts(db, CL.OFFICIAL)
    assert "ad" in v["views_include"].lower() and "all" in v["views_include"].lower(), v
    CL.record_lessons(db)
    with db.session() as s:
        st = [r.statement for r in s.scalars(select(Lesson).where(
            Lesson.evidence_ref.like("commercial:official:%")))]
    assert st and all("including ad" in x for x in st), st


def test_low_the_job_audit_carries_the_official_reading():
    from brambleloop.runtime import pipeline  # noqa: F401 - registers handlers
    from brambleloop.core.models import Job, JobStatus, Phase
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    db = _db()
    _three_categories(db)
    job = JobQueue(db).enqueue("analyst", "improve.commercial_lessons", {}, priority=0,
                               idempotency_key="t:e1fix:audit")
    Worker(db, "e1fix", phase=Phase.SHADOW,
           job_types=["improve.commercial_lessons"]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, (row.status, row.last_error)
        outputs = dict(row.outputs or {})
        audit = s.scalars(select(AuditLog).where(
            AuditLog.action == "improve.commercial_lessons")).first()
    off = (audit.detail or {}).get("official")
    assert off and off["measurable"] is True and off["denominator"] == "views", audit.detail
    assert off["shop"] and "views" in off["shop"], off
    assert outputs.get("official", {}).get("measurable") is True, outputs


def _snap(db, at: datetime, views: dict[str, int]):
    with db.session() as s:
        s.add(OperatingReading(kind=SNAPSHOT_KIND, period_key=at.date().isoformat(), payload={
            "listings": {PRODUCTS[slug]: {"views": v, "favourites": 0}
                         for slug, v in views.items()}}, at=at))


def test_low_the_order_window_is_the_snapshot_times_not_whole_days():
    db = _db()
    utc = timezone.utc
    _snap(db, datetime(2026, 10, 1, 18, tzinfo=utc), {"market-basket-small": 100})
    _snap(db, datetime(2026, 10, 15, 6, tzinfo=utc), {"market-basket-small": 500})
    _order(db, "market-basket-small", 3, day="2026-10-01T08:00:00")   # before the 1st view
    _order(db, "market-basket-small", 4, day="2026-10-08T12:00:00")   # inside
    _order(db, "market-basket-small", 5, day="2026-10-15T20:00:00")   # after the last view
    _ledger_read(db)
    basket = CL._category_and_family("market-basket-small")[0]
    g = CL.official_groups(db)[basket]
    assert g.orders == 4, g


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
