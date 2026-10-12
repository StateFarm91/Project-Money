"""v1.1 lane H: Etsy Ads readiness per listing, economics with basis, eligibility evidence.

Every product, listing, outcome and order below is a TEST FIXTURE in a throwaway database.
Nothing here spends, publishes or contacts anybody.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_v11_ads_readiness.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Incident, Listing, ListingOutcome, ListingSetCertificateRecord, OwnerAction, Product,
)
from brambleloop.growth import ads_readiness as ads  # noqa: E402

NOW = datetime.now(timezone.utc)
TRUST_PASS = {"gate": "trust_ladder", "status": "PASS",
              "why": "TEST FIXTURE: trust ladder supplied as passed"}


def fresh_db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='v11ads_')}/a.sqlite")
    db.create_all()
    return db


def add_listing(db, slug, *, price=12.0, published=True, certified=True, organic=True):
    """A fixture listing; each readiness ingredient can be switched off."""
    with db.session() as s:
        s.add(Product(slug=slug, title=f"Fixture {slug}", status="certified"))
        s.add(Listing(product_slug=slug, version="1.0", title="t", description="d",
                      price_cad=price, state="published" if published else "draft",
                      etsy_listing_id="999001" if published else ""))
        if certified:
            s.add(ListingSetCertificateRecord(product_slug=slug, version="1.0", state="valid"))
        if organic:
            start = NOW.date() - timedelta(days=40)
            s.add(ListingOutcome(product_slug=slug, period_start=start.isoformat(),
                                 period_end=(start + timedelta(days=35)).isoformat(),
                                 visits=400, orders=6, impressions=5000,
                                 source="TEST FIXTURE stats export"))


def make_eligible(db):
    ads.record_evidence(db, status="ELIGIBLE", evidence_source="TEST FIXTURE Etsy UI ref",
                        verified_at=NOW - timedelta(minutes=5), now=NOW)


def gate(r, name):
    return next(g for g in r["gates"] if g["gate"] == name)


def test_fully_evidenced_listing_is_ready_with_modelled_basis():
    db = fresh_db()
    add_listing(db, "ready-one")
    make_eligible(db)
    r = ads.listing_readiness(db, "ready-one", now=NOW, trust_gate=TRUST_PASS)
    assert r["ready"], r["blocking"]
    e = r["economics"]
    assert e["basis"] == "modelled" and e["confidence"] == "low"
    assert e["refund_rate"] == "UNMEASURED"
    assert abs(e["break_even_roas"] - round(12 / e["contribution_per_order_cad"], 4)) < 1e-6
    assert e["break_even_roas_conservative"] > e["break_even_roas"]
    assert e["fee_reading"]["read_on"]


def test_unknown_economics_is_never_ready():
    db = fresh_db()
    add_listing(db, "no-price", price=0.0)
    make_eligible(db)
    r = ads.listing_readiness(db, "no-price", now=NOW, trust_gate=TRUST_PASS)
    g = gate(r, "unit_economics")
    assert g["status"] == "UNKNOWN"
    assert not r["ready"]
    assert r["economics"]["break_even_roas"] is None
    assert r["economics"]["contribution_per_order_cad"] is None  # not 0.0


def test_unknown_gates_never_count_as_pass():
    db = fresh_db()
    add_listing(db, "thin", organic=False)  # eligibility never recorded either
    r = ads.listing_readiness(db, "thin", now=NOW, trust_gate=TRUST_PASS)
    assert gate(r, "organic_signal")["status"] == "UNKNOWN"
    assert gate(r, "ads_eligibility")["status"] == "UNKNOWN"
    assert not r["ready"]
    assert "organic_signal: UNKNOWN" in r["blocking"]


def test_uncertified_or_unpublished_or_truth_incident_blocks():
    db = fresh_db()
    add_listing(db, "draft-one", published=False)
    add_listing(db, "uncert", certified=False)
    add_listing(db, "incident")
    with db.session() as s:
        s.add(Incident(severity="P1", product_slug="incident", signature="pattern-error",
                       summary="TEST FIXTURE", halts_publication=True))
    make_eligible(db)
    cases = {"draft-one": "listing_live", "uncert": "listing_certified",
             "incident": "product_truth_clear"}
    assert len(cases) == 3
    for slug, name in cases.items():
        r = ads.listing_readiness(db, slug, now=NOW, trust_gate=TRUST_PASS)
        assert gate(r, name)["status"] == "FAIL", (slug, r["blocking"])
        assert not r["ready"]


def test_trust_gate_unreadable_is_unknown_not_pass():
    db = fresh_db()
    add_listing(db, "t")
    g = ads._trust_gate(db)  # real ladder on an empty shop: never PASS
    assert g["status"] in ("FAIL", "UNKNOWN")


def test_offsite_exposure_is_modelled_and_labelled():
    x = ads.offsite_exposure(12.0, trailing_365_sales_usd=None)
    assert x["basis"] == "modelled" and x["controllable"] is False
    assert x["fee_per_attributed_order_cad_applied"] is None  # threshold position unknown
    assert x["fee_per_attributed_order_cad_conservative"] == round(12.0 * 0.15, 4)
    assert x["terms_source"]["reading"] == "advertising_rules"
    above = ads.offsite_exposure(12.0, trailing_365_sales_usd=20000.0)
    assert above["participation"] == "mandatory"
    assert above["fee_per_attributed_order_cad_applied"] == round(12.0 * 0.12, 4)


def test_countdown_never_grants_eligibility_and_dedupes_owner_action():
    db = fresh_db()
    before = datetime(2026, 9, 25, tzinfo=timezone.utc)
    first = ads.tick(db, now=before)
    assert first["days_remaining"] == 9 and first["date_is_estimate"]
    due = ads.tick(db, now=ads.REPORTED_RECHECK)
    ads.tick(db, now=ads.REPORTED_RECHECK + timedelta(hours=1))
    assert due["etsy_ads_status"] == "RECHECK_REQUIRED"
    assert due["activation_authorised"] is False
    with db.session() as s:
        acts = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == ads.REFRESH_KEY)))
    assert len(acts) == 1


def test_eligibility_evidence_expires_and_is_not_authority():
    db = fresh_db()
    now = ads.REPORTED_RECHECK
    ads.tick(db, now=now)
    v = ads.record_evidence(db, status="ELIGIBLE", evidence_source="TEST FIXTURE ref",
                            verified_at=now, now=now)
    assert v["etsy_ads_status"] == "ELIGIBLE" and not v["activation_authorised"]
    assert ads._eligibility_gate(db, now + timedelta(hours=1))["status"] == "PASS"
    assert ads._eligibility_gate(db, now + timedelta(hours=25))["status"] == "UNKNOWN"
    assert ads.tick(db, now=now + timedelta(days=1))["etsy_ads_status"] == "RECHECK_REQUIRED"


def test_future_or_blank_evidence_refused():
    db = fresh_db()
    for kwargs in ({"evidence_source": "x", "verified_at": NOW + timedelta(days=1)},
                   {"evidence_source": "  ", "verified_at": NOW}):
        try:
            ads.record_evidence(db, status="ELIGIBLE", now=NOW, **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"accepted {kwargs}")


def test_summary_contract_on_empty_and_populated_db():
    db = fresh_db()
    s = ads.summary(db)
    for k in ("status", "as_of", "basis", "items", "sources"):
        assert k in s, k
    assert s["status"] == "UNKNOWN" and s["basis"] == "unknown" and s["items"] == []
    assert s["execution_capability"] == "none" and s["spend_executed_cad"] == 0.0
    add_listing(db, "pop")
    s2 = ads.summary(db)
    assert s2["status"] in ("BLOCKED", "OK") and s2["basis"] == "modelled"
    rows = [i for i in s2["items"] if i["type"] == "listing_readiness"]
    assert len(rows) == 1 and rows[0]["economics_basis"] == "modelled"
    import json
    json.dumps(s2)  # JSON-serialisable


def test_next_work_contract():
    db = fresh_db()
    add_listing(db, "nw", organic=False)
    add_listing(db, "nw-price", price=0.0)
    work = ads.next_work(db, now=NOW)
    assert len(work) >= 3, work
    keys = {i["key"] for i in work}
    assert "ads.eligibility_tick" in keys
    assert "ads.organic_baseline:nw" in keys and "ads.economics:nw-price" in keys
    for i in work:
        assert set(i) >= {"key", "department", "kind", "action", "why", "spend_cad",
                          "blocked_by"}
        assert i["spend_cad"] == 0.0 and i["department"] == "growth"


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            fails += 1
            print("FAIL", name, repr(e))
    print(f"{len(tests) - fails} passing, {fails} failing")
    sys.exit(1 if fails else 0)
