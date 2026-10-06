"""v1.1 lane E: the owner Money view and the truth of its numbers.

F-902 / section 95 ("disconnect an accounting source: Money changes to UNKNOWN/stale with a
source-health warning rather than CA$0.00"), F-905 accrual vs cash, F-908 cash & runway,
F-913 forecast honesty, F-914 provider contract.
Run: cd brambleloop && PYTHONPATH=src python3 tests/test_v11_accounting_money.py
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="v11_acct_money_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")


def _no_network(*_a, **_k):
    raise OSError("network refused by the accounting harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry  # noqa: E402
from brambleloop.finance.accounting import (cash, dashboard, forecast,  # noqa: E402
                                            posting_rules, reconciliation, shadow_dataset,
                                            views)

NOW = datetime.now(timezone.utc)
_n = [0]
CONTRACT = {"status", "as_of", "basis", "items", "sources"}


def _db(seed=True):
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/m{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    if seed:
        shadow_dataset.seed(db, now=NOW)
    return db


def _items(s):
    assert s["items"], s
    return {i["metric"]: i for i in s["items"]}


def test_empty_database_is_unknown_never_zero_and_never_raises():
    db = _db(seed=False)
    s = dashboard.summary(db)
    assert CONTRACT <= set(s) and s["status"] == "UNKNOWN", s["status"]
    json.dumps(s)
    it = _items(s)
    for k in ("gross_sales", "net_sales", "fees", "contribution", "profit", "tax_reserve",
              "cash", "safe_discretionary_budget"):
        assert it[k]["value_cad"] is None, (k, it[k])
        assert it[k]["reading"] == "UNKNOWN", (k, it[k])
    assert "transactions_r" in s["reason"]


def test_provider_accepts_a_bare_sqlalchemy_session():
    db = _db()
    with db.session() as sess:
        s = dashboard.summary(sess)
    assert CONTRACT <= set(s) and s["status"] in ("OK", "DEGRADED"), s.get("reason")
    assert _items(s)["gross_sales"]["value_cad"] > 0


def test_disconnecting_the_order_source_turns_money_unknown_not_zero():
    """Section 95."""
    # Connected and read, no sales: a measured zero is allowed and is labelled measured.
    db = _db(seed=False)
    shadow_dataset.connect_order_source(db)
    with db.session() as s:
        s.add(AuditLog(actor="cfo", action="commerce.orders_ingested", detail={"ran": True}))
    it = _items(dashboard.summary(db))
    assert it["gross_sales"]["value_cad"] == 0.0 and it["gross_sales"]["reading"] == "measured"
    # Disconnect the source: the same zero is now UNKNOWN with a source-health warning.
    shadow_dataset.disconnect_order_source(db)
    s = dashboard.summary(db)
    it = _items(s)
    assert it["gross_sales"]["value_cad"] is None and it["gross_sales"]["reading"] == "UNKNOWN"
    assert s["status"] == "UNKNOWN"
    assert s["source_health"]["orders"]["state"] == "disconnected"
    assert "orders: DISCONNECTED" in s["reason"]
    # With recorded sales and the source disconnected: a labelled lower bound, never measured.
    db2 = _db()
    shadow_dataset.disconnect_order_source(db2)
    s2 = dashboard.summary(db2)
    it2 = _items(s2)
    assert it2["gross_sales"]["reading"] == "lower_bound" and s2["status"] == "DEGRADED"
    assert "lower_bound" in s2["reason"]


def test_a_stale_source_is_labelled_stale():
    db = _db(seed=False)
    shadow_dataset.connect_order_source(db)
    with db.session() as s:
        s.add(AuditLog(actor="cfo", action="commerce.orders_ingested", detail={"ran": True},
                       at=NOW - timedelta(days=3)))
    s = dashboard.summary(db, now=NOW)
    assert s["source_health"]["orders"]["state"] == "stale"
    assert _items(s)["gross_sales"]["reading"] == "stale"
    assert s["status"] == "DEGRADED"


def test_accrual_and_cash_are_separate_bases_and_cash_is_unknown_without_a_bank():
    db = _db()
    posting_rules.post_all(db)
    acc, csh = views.accrual(db), views.cash(db)
    assert acc["basis_of_accounting"] == "accrual" and csh["basis_of_accounting"] == "cash"
    money_a = {k for k in acc if k.endswith("_cad")}
    money_c = {k for k in csh if k.endswith("_cad")}
    assert money_a and money_c and not (money_a & money_c)
    assert all(k.startswith("accrual_") for k in money_a if k.startswith(("accrual", "cash")))
    assert csh["cash_reading"] == "UNKNOWN" and csh["cash_bank_balance_cad"] is None
    assert acc["accrual_gross_sales_cad"] > 0, "accrual revenue exists while cash is unknown"
    reconciliation.import_statement(db, "bank", [
        {"external_id": "c1", "at": NOW, "kind": "owner_contribution", "amount": 200.0,
         "reference": "owner"}], now=NOW)
    reconciliation.match(db, now=NOW)
    posting_rules.post_all(db)
    csh = views.cash(db)
    assert csh["cash_reading"] == "measured" and csh["cash_bank_balance_cad"] == 200.0
    assert views.accrual(db)["accrual_gross_sales_cad"] == acc["accrual_gross_sales_cad"], \
        "an owner contribution is cash, not revenue"


def test_cash_position_reserves_safe_budget_and_runway():
    db = _db()
    posting_rules.post_all(db)
    p = cash.position(db, now=NOW)
    assert p["cash_on_hand_cad"] is None and p["safe_discretionary_budget_cad"] is None
    assert p["runway"] is None and "UNKNOWN" in p["runway_why"]
    assert p["expected_payout_cad"] > 0 and "not cash" in p["expected_payout_reading"]
    assert p["committed_spend_cad"] == 0.75, p["committed_spend_cad"]
    assert p["obligations"]["accrued_listing_fee_exposure_cad"] == 0.28
    assert p["tax_reserve"]["sales_tax_reserve_ytd_cad"] > 0
    assert any(b["basis"] == "declared_not_observed" for b in p["upcoming_bills"])
    reconciliation.import_statement(db, "bank", [
        {"external_id": "c1", "at": NOW, "kind": "owner_contribution", "amount": 1000.0,
         "reference": "owner"}], now=NOW)
    reconciliation.match(db, now=NOW)
    posting_rules.post_all(db)
    p2 = cash.position(db, now=NOW)
    assert p2["cash_on_hand_cad"] == 1000.0
    assert 0 < p2["safe_discretionary_budget_cad"] < 1000.0 - 270.0  # 6 x CA$45 reserve
    assert p2["runway"]["low_months"] > 0


def test_forecast_is_a_range_with_assumptions_never_a_booked_point():
    db = _db()
    posting_rules.post_all(db)
    f = forecast.forecast(db, now=NOW)
    assert f["is_booked"] is False and f["is_measured"] is False and f["basis"] == "modelled"
    assert f["revenue"] is None and "measured orders" in f["revenue_why"]
    oc = f["operating_cost"]
    assert oc and oc["low_cad"] <= oc["high_cad"] and oc["assumptions"]
    assert "value" not in oc and "value_cad" not in oc
    # Enough measured orders: a revenue range appears, still a range.
    with db.session() as s:
        from brambleloop.core.models import LedgerEntry
        for i in range(12):
            s.add(LedgerEntry(category="sale", gross_cad=10.0, evidence_ref=f"f-{i}",
                              basis="measured", at=NOW - timedelta(days=i)))
    posting_rules.post_all(db)
    f2 = forecast.forecast(db, now=NOW)
    r = f2["revenue"]
    assert r and r["low_cad"] < r["high_cad"] and r["assumptions"] and r["confidence"]
    assert "value_cad" not in r


def test_summary_items_label_actual_vs_estimated():
    db = _db()
    s = dashboard.summary(db, now=NOW)
    assert s["status"] == "DEGRADED" and s["basis"] == "estimated"
    it = _items(s)
    fees = it["fees"]
    assert fees["reading"] == "estimated"
    assert round(fees["actual_cad"] + fees["estimated_cad"], 4) == fees["value_cad"]
    assert it["cash"]["value_cad"] is None and it["cash"]["reading"] == "UNKNOWN"
    assert s["tax_reserve"]["basis"].startswith("estimated")
    assert s["payout_status"]["expected_payout_cad"] > 0
    for window in ("mtd", "ytd", "all", NOW.strftime("%Y-%m")):
        assert dashboard.summary(db, window=window, now=NOW)["status"] in ("OK", "DEGRADED")
    json.dumps(s)


def test_held_orders_make_sales_a_lower_bound():
    db = _db()
    from brambleloop.commerce import orders_ingest
    from brambleloop.core.models import OperatingReading
    with db.session() as s:
        s.add(OperatingReading(kind=orders_ingest.HELD_KIND, period_key=orders_ingest.HELD_KEY,
                               payload={"records": {"etsy:9:90": {
                                   "ref": "etsy:9:90", "reason": "unconverted_currency",
                                   "at": NOW.isoformat(), "currency": "JPY",
                                   "amount_original": 2000, "revision": 1}}}))
    acc = views.accrual(db, since=NOW - timedelta(days=30), until=NOW + timedelta(days=1))
    assert acc["sales_reading"] == "lower_bound" and acc["held_orders"] == ["etsy:9:90"]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    assert tests
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
