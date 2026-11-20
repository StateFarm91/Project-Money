"""W4-C12: dashboard tasks, KPI snapshot, traffic sources, and the three account registers.

Rows (Final Master, quoted):
- F-551 "Ingest Shop Manager dashboard top tasks, Shop Advisor warnings, recent activity, open
  orders, messages needing response, renewals/expiry and shop-specific reminders. Every
  actionable item becomes a durable task with owner, deadline, evidence and closure proof."
- F-552 "Persist dashboard views/visits/orders/revenue and relevant date range/channel context.
  Dashboard numbers are quick signals, not substitutes for detailed Stats."
- F-562 "Track Etsy Search, Etsy app/other Etsy pages, direct traffic, social, Etsy Ads,
  Offsite Ads and other available sources separately; preserve Etsy's attribution definitions."
- F-580 "Inventory every connected Etsy app, granted permissions/scopes, purpose, owner, last
  use, data access, cost and revocation path. Unknown or unused integrations are security debt."
- F-583 "If Shared Access is used, inventory team members, access dates and activity; enforce
  least privilege within Etsy's available model. Owner remains accountable for team actions."
- F-588 "Maintain accurate production-partner disclosures when applicable. Refuse fabricated or
  stale partner data and re-audit when fulfillment/manufacturing changes."
Fixtures only; no Etsy call, no write to Etsy.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.commerce import shop_security as SS  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Customer, OperatingReading, Order, OwnerAction  # noqa: E402
from brambleloop.integrations import etsy_dashboard as D  # noqa: E402

NOW = datetime.now(timezone.utc)


def _db() -> Database:
    db = Database("sqlite://", scratch=True)
    db.create_all()
    return db


def _order(db, ref, status, *, at=None, revenue=8.0, refunded=False):
    with db.session() as s:
        c = s.scalar(select(Customer).where(Customer.customer_ref == "buyer-1"))
        if c is None:
            c = Customer(customer_ref="buyer-1")
            s.add(c)
            s.flush()
        s.add(Order(customer_id=c.id, external_ref=ref, product_slug="moss", at=at or NOW,
                    revenue_cad=revenue, refunded=refunded,
                    detail={"receipt_status": status}))


def _census(db, estate):
    with db.session() as s:
        s.add(OperatingReading(kind="etsy.listing_census", period_key="d", at=NOW,
                               payload={"observed_at": NOW.isoformat(), "estate": estate}))


# ---- F-551 ----------------------------------------------------------------------------------

def test_f551_reachable_items_become_tasks_and_close_only_with_proof():
    db = _db()
    _order(db, "r-1", "paid")
    _order(db, "r-2", "completed")
    _census(db, [{"listing_id": "9", "slug": "moss", "ours": True,
                  "renewal": {"mode": "manual", "expiring_soon": True, "days_to_expiry": 3}},
                 {"listing_id": "8", "slug": "x", "ours": False,
                  "renewal": {"mode": "expired"}}])
    out = D.harvest(db, now=NOW)
    assert sorted(out["opened"]) == ["etsy.dashboard:order:r-1", "etsy.dashboard:renewal:9"]
    assert {"messages_needing_response", "shop_advisor", "top_tasks"} <= set(out["unavailable"])
    t = {x["kind"]: x for x in out["tasks"]}
    assert t["open_order"]["owner"] == "support" and t["open_order"]["deadline"]
    assert t["renewal"]["evidence"].startswith("etsy.listing_census@")
    assert "never on the date alone" in t["renewal"]["action"]
    assert D.harvest(db, now=NOW)["opened"] == []                  # durable, not duplicated
    with db.session() as s:                                       # the order completes
        o = s.scalar(select(Order).where(Order.external_ref == "r-1"))
        o.detail = {"receipt_status": "completed"}
    out = D.harvest(db, now=NOW)
    assert out["closed"] == ["etsy.dashboard:order:r-1"]
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "etsy.dashboard:order:r-1"))
        assert row.done and row.state == "satisfied" and "closure proof" in row.state_reason


# ---- F-552 ----------------------------------------------------------------------------------

def test_f552_snapshot_is_measured_orders_and_unknown_views_until_read():
    db = _db()
    _order(db, "a", "completed", at=datetime(2026, 9, 3, tzinfo=timezone.utc), revenue=8.0)
    _order(db, "b", "completed", at=datetime(2026, 9, 5, tzinfo=timezone.utc), revenue=12.5)
    _order(db, "c", "completed", at=datetime(2026, 10, 5, tzinfo=timezone.utc), revenue=99.0)
    snap = D.kpi_snapshot(db, start=date(2026, 9, 1), end=date(2026, 9, 30), now=NOW)
    assert snap["orders"]["value"] == 2 and snap["revenue_cad"]["value"] == 20.5
    assert snap["views"]["value"] == "UNKNOWN" and snap["visits"]["value"] == "UNKNOWN"
    assert snap["range"] == {"start": "2026-09-01", "end": "2026-09-30"}
    assert "not a substitute" in snap["note"]
    read = D.kpi_snapshot(db, start=date(2026, 9, 1), end=date(2026, 9, 30), now=NOW,
                          owner_reading={"views": 410, "visits": 120, "read_on": "2026-10-01"})
    assert read["visits"]["value"] == 120 and "owner-recorded" in read["visits"]["basis"]
    for bad in ({"views": -1, "read_on": "x"}, {"views": 3}):
        try:
            D.kpi_snapshot(db, start=date(2026, 9, 1), end=date(2026, 9, 30),
                           owner_reading=bad)
            raise AssertionError(bad)
        except D.DashboardRefused:
            pass
    with db.session() as s:
        assert len(list(s.scalars(select(OperatingReading).where(
            OperatingReading.kind == D.KPI_KIND)))) == 2


# ---- F-562 ----------------------------------------------------------------------------------

def test_f562_sources_are_kept_separately_with_etsys_labels_and_definitions():
    db = _db()
    csv_text = ("Traffic source,Visits\nEtsy search,120\nEtsy app & other Etsy pages,40\n"
                "Direct & other traffic,15\nSocial media,9\nEtsy Ads,4\nOffsite Ads,2\n"
                "Pinterest referral,3\n")
    out = D.record_traffic_sources(db, text=csv_text, start=date(2026, 9, 1),
                                   end=date(2026, 9, 30), exported_on=date(2026, 10, 1))
    labels = [r["etsy_label"] for r in out["sources"]]
    assert labels[:6] == ["Etsy search", "Etsy app & other Etsy pages", "Direct & other traffic",
                          "Social media", "Etsy Ads", "Offsite Ads"]
    assert out["unrecognised"] == ["Pinterest referral"]          # kept verbatim, not merged
    assert out["sources"][0]["etsy_definition"] == D.ETSY_TRAFFIC_SOURCES["Etsy search"]
    assert out["total_visits"] == 193 and out["basis"] == "owner-exported Etsy Stats"
    for bad in ("Source,Visits\nEtsy search,12a\n", "Visits\n3\n",
                "Source,Visits\nEtsy search,1\nEtsy search,2\n"):
        try:
            D.record_traffic_sources(db, text=bad, start=date(2026, 9, 1),
                                     end=date(2026, 9, 30), exported_on=date(2026, 10, 1))
            raise AssertionError(bad)
        except D.DashboardRefused:
            pass


# ---- F-580 ----------------------------------------------------------------------------------

APP = {"name": "Label printer", "scopes": ["transactions_r"], "purpose": "print labels",
       "owner": "owner", "last_used_on": (NOW - timedelta(days=90)).isoformat(),
       "data_access": "orders", "monthly_cost_cad": 0.0,
       "revocation_path": "Etsy > Apps you've connected > Remove"}


def test_f580_every_app_is_accounted_for_and_unused_ones_are_debt():
    db = _db()
    empty = SS.apps_register(db, held_scopes=["listings_r"], now=NOW)
    assert empty["status"] == "UNVERIFIED" and empty["state"] == "UNOBSERVED"
    first = empty["apps"][0]
    assert first["first_party"] and first["revocation_path"] and first["purpose"]
    try:
        SS.record_apps(db, observed_at=NOW, apps=[{"name": "Mystery"}], complete=True,
                       statement="the apps page lists one app")
        raise AssertionError("an unaccounted app was recorded as known")
    except SS.RegisterRefused as e:
        assert "purpose" in str(e)
    SS.record_apps(db, observed_at=NOW - timedelta(hours=1), apps=[APP], complete=True,
                   statement="the apps page lists one app")
    reg = SS.apps_register(db, held_scopes=["listings_r", "feedback_r"], now=NOW)
    assert reg["status"] == "DEBT"
    whys = {d["app"]: d["why"] for d in reg["security_debt"]}
    assert "not used in" in whys["Label printer"] and "feedback_r" in whys[first["name"]]


# ---- F-583 ----------------------------------------------------------------------------------

def test_f583_shared_access_is_checked_for_least_privilege_and_activity():
    db = _db()
    assert SS.shared_access_register(db, now=NOW)["status"] == "UNVERIFIED"
    SS.record_shared_access(db, observed_at=NOW - timedelta(hours=1), complete=True,
                            statement="Shared Access shows two people",
                            members=[{"label": "helper", "permissions": ["listings", "finances"],
                                      "needs": ["listings"], "granted_on": "2026-09-01",
                                      "last_activity_on": (NOW - timedelta(days=2)).isoformat()},
                                     {"label": "old", "permissions": ["stats"],
                                      "needs": ["stats"], "granted_on": "2026-01-01"}])
    reg = SS.shared_access_register(db, now=NOW)
    assert reg["status"] == "FINDINGS" and reg["accountable"] == "owner"
    checks = {(f["member"], f["check"]) for f in reg["findings"]}
    assert checks == {("helper", "least_privilege"), ("old", "idle")}, checks
    try:
        SS.record_shared_access(db, observed_at=NOW, complete=True,
                                statement="Shared Access shows one person",
                                members=[{"label": "x", "permissions": ["root"], "needs": ["x"],
                                          "granted_on": "2026-09-01"}])
        raise AssertionError("an invented permission was accepted")
    except SS.RegisterRefused:
        pass


# ---- F-588 ----------------------------------------------------------------------------------

def test_f588_partner_data_is_read_never_composed_and_goes_stale_or_reaudits():
    db = _db()
    try:
        SS.record_partners(db, observed_at=NOW, partners=[], complete=True,
                           statement="no partners, as far as I remember", source="memory")
        raise AssertionError("composed partner data was accepted")
    except SS.RegisterRefused as e:
        assert "fabricated" in str(e)
    unchanged = {"reopened": False, "why": "provider set unchanged"}
    assert SS.partners_register(db, now=NOW, reaudit=unchanged)["state"] == "UNOBSERVED"
    SS.record_partners(db, observed_at=NOW - timedelta(days=1), partners=[], complete=True,
                       statement="Production partners page lists none", source="etsy_page")
    ok = SS.partners_register(db, now=NOW, reaudit=unchanged)
    assert ok["status"] == "OK" and ok["state"] == "FRESH" and ok["source"] == "etsy_page"
    assert SS.partners_register(db, now=NOW + timedelta(days=120),
                                reaudit=unchanged)["state"] == "STALE"
    moved = SS.partners_register(db, now=NOW, reaudit={"reopened": True,
                                                       "why": "a fulfilment provider joined"})
    assert moved["state"] == "REAUDIT" and moved["status"] == "UNVERIFIED"


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
