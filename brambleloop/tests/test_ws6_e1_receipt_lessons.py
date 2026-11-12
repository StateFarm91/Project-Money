"""WS6 E1: buyer evidence from OFFICIAL Etsy data reaches rankings without any owner export.

The numerator is receipt orders (`transactions_r`, `Order.source == orders_ingest.SOURCE`);
the denominator is official listing VIEWS (differenced daily `getListingsByShop` snapshots).
Impressions, visits, carts, conversion and traffic sources stay UNKNOWN. Every order, view and
listing here is a TEST FIXTURE; nothing is real.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws6_e1_receipt_lessons.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.commerce import cohorts  # noqa: E402
from brambleloop.commerce.listing_outcomes import SNAPSHOT_KIND  # noqa: E402
from brambleloop.commerce.orders_ingest import SOURCE  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Lesson, Listing, OperatingReading  # noqa: E402
from brambleloop.improve import commercial_lessons as CL  # noqa: E402

PRODUCTS = {"market-basket-small": "11", "hexagon-coaster-set": "22",
            "cloudline-baby-blanket": "33"}


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='ws6e1_')}/e.sqlite", scratch=True)
    db.create_all()
    Registry(db).seed_defaults()
    with db.session() as s:
        for slug, lid in PRODUCTS.items():
            s.add(Listing(product_slug=slug, version="1.0.0", etsy_listing_id=lid, title=slug, description="fixture",
                          state="active", release_hash="r" * 64))
    return db


def _snapshot(db, day: str, views: dict[str, int]):
    with db.session() as s:
        s.add(OperatingReading(kind=SNAPSHOT_KIND, period_key=day, payload={
            "listings": {PRODUCTS[slug]: {"views": v, "favourites": 0}
                         for slug, v in views.items()}},
            at=datetime.fromisoformat(day).replace(tzinfo=timezone.utc)))


def _order(db, slug, n, *, day="2026-10-10", source=SOURCE, ref_prefix="etsy",
           offsite=False):
    for i in range(n):
        ref = f"{ref_prefix}:{slug}-{day}-{source}-{int(offsite)}-{i}:{i}"
        cohorts.record_customer(db, f"cust-{ref}", at=datetime.fromisoformat(day).replace(
            tzinfo=timezone.utc), acquisition_source="unknown", first_product_slug=slug)
        cohorts.record_order(db, f"cust-{ref}", ref, product_slug=slug,
                             at=datetime.fromisoformat(day).replace(tzinfo=timezone.utc),
                             price_cad=8.0, revenue_cad=8.0, source=source,
                             offsite_ad_attributed=offsite, detail={"state": "paid"})


def _two_week_window(db):
    _snapshot(db, "2026-10-01", {"market-basket-small": 100, "hexagon-coaster-set": 100,
                                 "cloudline-baby-blanket": 100})
    _snapshot(db, "2026-10-15", {"market-basket-small": 500, "hexagon-coaster-set": 500,
                                 "cloudline-baby-blanket": 700})


def test_receipt_orders_over_official_views_publish_lessons_without_any_export():
    db = _db()
    _two_week_window(db)
    _order(db, "market-basket-small", 20)        # 20 / 400 views = 5%
    _order(db, "hexagon-coaster-set", 4)         # 4 / 400 = 1%
    _order(db, "cloudline-baby-blanket", 2)      # 2 / 600 = 0.33%
    v = CL.verdicts(db, CL.OFFICIAL)
    assert v["measurable"] is True and v["denominator"] == "views", v
    assert {"impressions", "visits", "carts", "conversion_rate",
            "traffic_sources"} <= set(v["unknown"])
    verdict = {k: c["verdict"] for k, c in v["categories"].items()}
    basket = CL._category_and_family("market-basket-small")[0]
    assert verdict[basket] == CL.DEMAND, verdict
    out = CL.record_lessons(db)
    assert out["official"]["measurable"] is True
    assert any(p["basis"] == CL.OFFICIAL and p["subject"] == CL.DEMAND
               for p in out["published"]), out["published"]
    with db.session() as s:
        lessons = list(s.scalars(select(Lesson).where(Lesson.subject == CL.DEMAND)))
    assert lessons and lessons[0].evidence_ref.startswith("commercial:official:")
    assert "Etsy listing views" in lessons[0].statement and "visits UNKNOWN" in (
        lessons[0].statement)
    # The export basis is untouched: nothing measured there.
    assert CL.verdicts(db, CL.EXPORT)["measurable"] is False


def test_only_countable_receipt_orders_inside_the_views_window_count():
    db = _db()
    _two_week_window(db)
    _order(db, "market-basket-small", 3)
    _order(db, "market-basket-small", 5, source="fixture")            # not a receipt
    _order(db, "market-basket-small", 5, ref_prefix="manual")        # not an Etsy ref
    _order(db, "market-basket-small", 5, offsite=True)               # paid traffic
    _order(db, "market-basket-small", 5, day="2026-09-20")            # before the window
    _order(db, "market-basket-small", 5, day="2026-10-20")            # after the window
    groups = CL.official_groups(db)
    basket = CL._category_and_family("market-basket-small")[0]
    assert groups[basket].orders == 3 and groups[basket].visits == 400, groups[basket]


def test_views_are_unknown_not_zero_when_a_count_falls_or_has_one_snapshot():
    db = _db()
    _snapshot(db, "2026-10-01", {"market-basket-small": 100, "hexagon-coaster-set": 300})
    _snapshot(db, "2026-10-15", {"market-basket-small": 90, "hexagon-coaster-set": 600,
                                 "cloudline-baby-blanket": 50})
    w = CL._view_windows(db)
    assert "market-basket-small" not in w          # the cumulative count fell
    assert "cloudline-baby-blanket" not in w       # one snapshot only
    assert w["hexagon-coaster-set"]["views"] == 300


def test_bases_never_supersede_each_other():
    """An official lesson and an export lesson for the same category are separate evidence:
    a later export reading withdraws only the export lesson."""
    from brambleloop.commerce.listing_outcomes import EXPORT_SOURCE
    from brambleloop.core.models import ListingOutcome

    db = _db()
    _two_week_window(db)
    _order(db, "market-basket-small", 20)
    _order(db, "hexagon-coaster-set", 4)
    _order(db, "cloudline-baby-blanket", 2)
    with db.session() as s:
        for slug, visits, orders in (("market-basket-small", 400, 20),
                                     ("hexagon-coaster-set", 400, 4),
                                     ("cloudline-baby-blanket", 600, 2)):
            s.add(ListingOutcome(product_slug=slug, version="1.0.0",
                                 period_start="2026-09-01", period_end="2026-09-30",
                                 impressions=visits * 10, visits=visits, favourites=1,
                                 orders=orders, source=EXPORT_SOURCE + "fixture-1"))
    first = CL.record_lessons(db)
    bases = {p["basis"] for p in first["published"]}
    assert bases == {CL.EXPORT, CL.OFFICIAL}, first["published"]
    with db.session() as s:
        for r in s.scalars(select(ListingOutcome)):
            s.delete(r)
    second = CL.record_lessons(db)
    with db.session() as s:
        live = [r.evidence_ref for r in s.scalars(select(Lesson).where(
            Lesson.withdrawn_at.is_(None), Lesson.subject.in_(CL.SUBJECTS)))]
    assert live and all(ref.startswith("commercial:official:") for ref in live), live
    assert second["withdrawn"], second
    # The export lesson was withdrawn as unsupported on ITS basis -- never "superseded" by
    # the official lesson for the same category.
    with db.session() as s:
        gone = [r for r in s.scalars(select(Lesson).where(Lesson.withdrawn_at.is_not(None)))]
    assert gone and all(not str(r.evidence_ref).startswith("commercial:official:")
                        for r in gone), [r.evidence_ref for r in gone]
    from brambleloop.core.models import AuditLog

    with db.session() as s:
        reasons = [dict(a.detail or {}) for a in s.scalars(select(AuditLog).where(
            AuditLog.action.like("%withdraw%")))]
    assert reasons and not any("lesson:" in str(d) and "superseded" in str(d)
                               for d in reasons), reasons


def test_a_category_below_the_views_floor_is_unmeasured():
    db = _db()
    _snapshot(db, "2026-10-01", {"market-basket-small": 0, "hexagon-coaster-set": 0,
                                 "cloudline-baby-blanket": 0})
    _snapshot(db, "2026-10-15", {"market-basket-small": CL.MIN_VIEWS - 1,
                                 "hexagon-coaster-set": CL.MIN_VIEWS - 1,
                                 "cloudline-baby-blanket": CL.MIN_VIEWS - 1})
    _order(db, "market-basket-small", 20)
    _order(db, "hexagon-coaster-set", 1)
    v = CL.verdicts(db, CL.OFFICIAL)
    assert v["measurable"] is False, v
    assert all(c["state"] == CL.UNMEASURED for c in v["categories"].values()), v


def test_nothing_official_recorded_measures_nothing():
    db = _db()
    v = CL.verdicts(db, CL.OFFICIAL)
    assert v["measurable"] is False and "UNMEASURED" in v["why"], v
    assert CL.record_lessons(db)["published"] == []


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e))
    print(f"PASS: {fails} failing" if not fails else f"FAILED: {fails} failing")
    sys.exit(1 if fails else 0)
