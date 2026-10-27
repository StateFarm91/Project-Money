"""W4-C12: Search Visibility as first-party findings, closure proof, three areas and aging.

Rows (Final Master, quoted):
- F-516@v0.16 "Capture Etsy Search Visibility findings as first-party evidence with timestamp,
  affected listing/shop area, recommended action, severity, owner and status. Do not substitute
  an internal SEO score for Etsy's own warning."
- F-517@v0.16 "After a corrective change, re-check Etsy Search Visibility and require the finding
  to clear or materially change before marking it resolved. Record time-to-clear and
  confirmation evidence."
- F-560 "Model Etsy Search Visibility exactly across Listings, Shop and Customer Service. Keep
  each area independently green/amber/red with first-party findings and timestamps."
- F-561 "Track how long each Etsy Search Visibility issue remains open; re-check after fixes and
  alert when Etsy has not cleared an expected issue within its normal refresh window."
Owner readings are fixtures; no Etsy call, nothing published.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.commerce import search_visibility as sv  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident, Listing  # noqa: E402

NOW = datetime.now(timezone.utc)
T0 = NOW - timedelta(days=20)
ITEM = {"scope": "listing", "listing_id": "1234567", "category": "Missing attributes",
        "remediation": "add the colour attribute", "severity": "Needs attention"}
SHOP = {"scope": "shop", "category": "Shop announcement missing",
        "remediation": "write a shop announcement"}


def _db() -> Database:
    db = Database("sqlite://", scratch=True)
    db.create_all()
    with db.session() as s:
        s.add(Listing(product_slug="p", version="1", title="t", description="d", tags=[],
                      price_cad=8.0, etsy_listing_id="1234567"))
    return db


def test_f516_a_finding_carries_area_action_severity_owner_status_and_refuses_a_score():
    db = _db()
    sv.record_reading(db, observed_at=T0, items=[ITEM, SHOP], complete=True)
    rows = {r["scope"]: r for r in sv.items(db)}
    lst = rows["listing"]
    assert lst["area"] == "listings" and lst["severity"] == "Needs attention"
    assert lst["owner"] == "store_commerce" and lst["state"] == sv.OPEN
    assert lst["remediation"] and lst["first_seen_at"] and lst["last_checked_at"]
    assert rows["shop"]["area"] == "shop" and rows["shop"]["severity"] is None   # not invented
    try:
        sv.record_reading(db, observed_at=T0 + timedelta(hours=1),
                          items=[{**ITEM, "seo_score": 42}], complete=False)
        raise AssertionError("an internal score was accepted as Etsy's finding")
    except sv.SearchVisibilityRefused as e:
        assert "F-516" in str(e)


def test_f517_only_a_later_recheck_resolves_and_records_time_to_clear_and_proof():
    db = _db()
    sv.record_reading(db, observed_at=T0, items=[ITEM], complete=True)
    iid = sv.items(db)[0]["id"]
    fixed = T0 + timedelta(days=1)
    sv.mark_remediated(db, iid, ref="listing 1234567 attributes v2", at=fixed)
    assert sv.items(db)[0]["state"] == sv.REMEDIATED_PENDING
    assert sv.items(db)[0]["cleared_at"] is None and sv.items(db)[0]["confirmation"] is None
    # A severity change on re-check is recorded as a change, not a resolution.
    sv.record_reading(db, observed_at=T0 + timedelta(days=2),
                      items=[{**ITEM, "severity": "Low"}], complete=True)
    r = sv.items(db)[0]
    assert r["state"] == sv.REMEDIATED_PENDING and r["severity"] == "Low"
    assert any(h.get("changed") == "severity" for h in r["history"])
    sv.record_reading(db, observed_at=T0 + timedelta(days=4), items=[], complete=True)
    r = sv.items(db)[0]
    assert r["state"] == sv.CLEARED and r["cleared_at"]
    c = r["confirmation"]
    assert c["hours_from_first_seen"] == 96.0 and c["hours_from_remediation"] == 72.0, c
    assert c["remediated_ref"] == "listing 1234567 attributes v2" and c["complete"] is True


def test_f560_three_areas_are_independent_and_never_green_by_default():
    db = _db()
    empty = sv.areas(db, now=NOW)["areas"]
    assert set(empty) == {"listings", "shop", "customer_service"}
    assert {a["status"] for a in empty.values()} == {"UNMEASURED"}
    sv.record_reading(db, observed_at=NOW - timedelta(days=1), items=[ITEM, SHOP],
                      complete=True)
    shop_id = next(r["id"] for r in sv.items(db) if r["scope"] == "shop")
    sv.mark_remediated(db, shop_id, ref="announcement written", at=NOW - timedelta(hours=12))
    a = sv.areas(db, now=NOW)["areas"]
    assert a["listings"]["status"] == "red" and a["listings"]["findings"][0]["first_seen_at"]
    assert a["shop"]["status"] == "amber"
    assert a["customer_service"]["status"] == "green" and a["customer_service"]["as_of"]
    stale = sv.areas(db, now=NOW + timedelta(days=30))["areas"]
    assert stale["customer_service"]["status"] == "amber"


def test_f561_aging_asks_for_a_recheck_then_alerts_past_the_refresh_window():
    db = _db()
    sv.record_reading(db, observed_at=T0, items=[ITEM], complete=True)
    iid = sv.items(db)[0]["id"]
    sv.mark_remediated(db, iid, ref="attributes v2", at=T0 + timedelta(days=1))
    out = sv.aging(db, now=NOW)
    e = out["items"][0]
    assert e["open_days"] >= 19 and e["rechecked_since_fix"] is False and "re-read" in e["needs"]
    assert out["overdue"] == []
    # Re-checked after the fix, still listed, and past the window: an alert, once.
    sv.record_reading(db, observed_at=T0 + timedelta(days=12), items=[ITEM], complete=True)
    out = sv.aging(db, now=NOW)
    assert [x["id"] for x in out["overdue"]] == [iid] and len(out["incidents_opened"]) == 1
    assert sv.aging(db, now=NOW)["incidents_opened"] == []
    # Etsy clears it: the alert resolves.
    sv.record_reading(db, observed_at=T0 + timedelta(days=13), items=[], complete=True)
    sv.aging(db, now=NOW)
    with db.session() as s:
        incs = list(s.scalars(select(Incident).where(
            Incident.signature.like(f"{sv.AGING_SIGNATURE}:%"))))
        assert incs and all(i.resolved for i in incs)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
