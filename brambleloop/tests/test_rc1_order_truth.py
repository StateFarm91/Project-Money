"""RC1 independent-audit findings on order, payment and refund truth, made permanent.

Each test is the audit's reproduction (scratchpad audit1/orders1-5.py) against the production
`commerce.orders_ingest.ingest` / `finance.reconcile.apply` / `finance.books.Books` services,
on a fresh SQLite database, with a fake receipt feed and no network:

* E1 a `partially refunded` receipt with no refund amount is held UNRECONCILED, never booked
  as a paid sale;
* E2 a cancelled or fully refunded sale is not an order, a customer or the first sale;
* E3 a paid sale in a currency with no rate is held with its own amount and CAD UNKNOWN,
  raises an incident, and keeps the books' sales reading off `measured`;
* E4 a partial ledger fee is `partial` (posted + modelled), never `measured`;
* E5 ledger types are an allow-list, unknown types and implausible magnitudes are incidents,
  and fees read through the unverified mapping are not `measured` until the owner verifies;
* E6 a refund in another currency is not read as the receipt's; duplicate transaction ids
  are refused and raised;
* G1 the publication evidence calls the price `set`, and voided orders are not sales volume.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_rc1_order_truth.py
"""
from __future__ import annotations

import copy
import os
import shutil
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="rc1_order_truth_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.update(BRAMBLELOOP_PHASE="shadow", BRAMBLELOOP_REQUIRE_POSTGRES="0")
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC", "OPENAI", "ETSY", "GEMINI", "GOOGLE_API", "DATABASE_URL",
                      "BRAMBLELOOP_DATABASE")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the rc1 order-truth harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.socket.connect_ex = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.commerce import orders_ingest as oi  # noqa: E402
from brambleloop.commerce.pricing import fees as model_fees  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, Customer, Incident, LedgerEntry,  # noqa: E402
                                     Listing, OAuthCredential, Order)
from brambleloop.finance import reconcile, sources  # noqa: E402
from brambleloop.finance.books import Books, trajectory  # noqa: E402

NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
_n = [0]


def receipt(rid=1, *, status="paid", refunds=(), amount=1200, currency="CAD", buyer=101,
            updated=0, lines=1):
    """One receipt in Etsy v3's ShopReceipt shape; `refunds` is (cents, currency) pairs."""
    return {"receipt_id": rid, "buyer_user_id": buyer,
            "create_timestamp": int((NOW - timedelta(days=1)).timestamp()),
            "update_timestamp": int(NOW.timestamp()) + updated, "status": status,
            "is_paid": True,
            "refunds": [{"amount": {"amount": c, "divisor": 100, "currency_code": cur}}
                        for c, cur in refunds],
            "transactions": [{"transaction_id": rid * 10 + i, "listing_id": 111, "quantity": 1,
                              "price": {"amount": amount, "divisor": 100,
                                        "currency_code": currency}}
                             for i in range(lines)]}


class Feed:
    def __init__(self, rows, entries=None):
        self.rows, self.entries, self.calls = rows, entries, 0

    def receipts(self, *, since):
        self.calls += 1
        return [copy.deepcopy(r) for r in self.rows]


class LedgerFeed(Feed):
    def ledger_entries(self, *, min_created, max_created):
        return list(self.entries or [])


def entry(eid, ledger_type, ref_type, ref_id, cents):
    return {"entry_id": eid, "ledger_type": ledger_type, "reference_type": ref_type,
            "reference_id": str(ref_id), "amount": cents, "currency": "CAD",
            "created_timestamp": int(NOW.timestamp())}


def _db():
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/case{_n[0]}.db", scratch=True)
    db.create_all()
    with db.session() as s:
        s.add(AuditLog(actor="test", action="etsy.probe", detail={"ok": True}))
        s.add(OAuthCredential(provider="etsy", refresh_token_sealed="synthetic-not-a-token",
                              token_fingerprint="synthetic", scopes="transactions_r"))
        s.add(Listing(product_slug="synthetic-product", version="2.0.0",
                      title="Synthetic fixture", description="", price_cad=12,
                      state="published", etsy_listing_id="111",
                      created_at=NOW - timedelta(days=2)))
    return db


def ingest(db, rows, entries=None, at=NOW):
    reader = LedgerFeed(rows, entries) if entries is not None else Feed(rows)
    got = oi.ingest(db, reader=reader, now=at)
    with db.session() as s:   # what the runtime handler audits after a completed read
        s.add(AuditLog(actor="cfo", action=oi.INGEST_AUDIT, detail={"ran": got["ran"]}))
    return got


def pl(db):
    return Books(db).profit_and_loss(since=NOW - timedelta(days=30),
                                     until=NOW + timedelta(days=1))


def orders(db):
    with db.session() as s:
        return list(s.scalars(select(Order).order_by(Order.id)))


def incident(db, signature):
    with db.session() as s:
        return s.scalar(select(Incident).where(Incident.signature == signature)
                        .order_by(Incident.id.desc()).limit(1))


def verify(db):
    # rc1-ORD2: recorded only under the owner credential, sealed and chained.
    os.environ["BRAMBLELOOP_OPS_TOKEN"] = "local-owner-ledger-mapping-token-32chars"
    reconcile.record_mapping_verification(db, authorization="local-owner-ledger-mapping-token-32chars", by="owner",
                                          evidence="synthetic fixture")


# ---------------------------------------------------------------------------
# E1


def test_E1_partially_refunded_with_no_refund_amount_is_held_not_booked():
    db = _db()
    got = ingest(db, [receipt(status="partially refunded")])
    assert orders(db) == [], "a sale whose refund is unknown is not booked at full price"
    with db.session() as s:
        assert list(s.scalars(select(LedgerEntry))) == []
    held = oi.held(db)
    assert [h["reason"] for h in held] == [oi.HELD_UNRECONCILED]
    assert held[0]["cad"] is None and held[0]["revenue_cad"] is None, "UNKNOWN, not zero"
    assert held[0]["amount_original"] == 12.0 and held[0]["currency"] == "CAD"
    assert got["held_incidents"][oi.UNRECONCILED_INCIDENT] == "opened"
    assert incident(db, oi.UNRECONCILED_INCIDENT).resolved is False
    d = pl(db).to_dict()
    assert d["sales_reading"] == "INCOMPLETE" and d["held_orders"][0]["ref"] == "etsy:1:10"
    assert d["gross_sales_cad"] == 0.0 and d["orders"] == 0


def test_E1_a_recorded_sale_whose_receipt_turns_unreconciled_is_excluded_then_rebooked():
    db = _db()
    ingest(db, [receipt()])
    assert pl(db).to_dict()["sales_reading"] == "measured"
    ingest(db, [receipt(status="partially refunded", updated=60)], at=NOW + timedelta(minutes=1))
    (o,) = orders(db)
    assert o.detail["state"] == oi.UNRECONCILED and o.detail["revenue_unknown"] is True
    d = pl(db).to_dict()
    assert d["sales_reading"] == "INCOMPLETE" and d["gross_sales_cad"] == 0.0
    assert d["orders"] == 0 and d["customers"] == 0
    # An older revision replayed does not release the hold.
    ingest(db, [receipt()], at=NOW + timedelta(minutes=2))
    assert [h["ref"] for h in oi.held(db)] == ["etsy:1:10"]
    # Etsy states the refund: the order is booked at the receipt's truth and the hold ends.
    got = ingest(db, [receipt(status="partially refunded", refunds=[(400, "CAD")],
                              updated=120)], at=NOW + timedelta(minutes=3))
    (o,) = orders(db)
    assert o.revenue_cad == 8.0 and o.detail["state"] == oi.PARTIALLY_REFUNDED
    assert "revenue_unknown" not in o.detail
    assert oi.held(db) == []
    assert got["held_incidents"][oi.UNRECONCILED_INCIDENT] == "resolved"
    d = pl(db).to_dict()
    assert d["sales_reading"] == "measured" and d["net_sales_cad"] == 8.0 and d["orders"] == 1


# ---------------------------------------------------------------------------
# E2


def test_E2_a_cancelled_first_sale_is_not_an_order_customer_or_first_sale():
    db = _db()
    ingest(db, [receipt()])
    assert sources.first_sale(db)["external_ref"] == "etsy:1:10"
    ingest(db, [receipt(status="canceled", updated=60)], at=NOW + timedelta(minutes=1))
    p = pl(db)
    d = p.to_dict()
    assert (d["gross_sales_cad"], d["refunds_cad"], d["net_sales_cad"]) == (12.0, 12.0, 0.0)
    assert d["orders"] == 0 and d["customers"] == 0 and d["voided_orders"] == 1
    t = trajectory(p)
    assert t["observed_orders"] == 0 and t.get("aov_cad") is None
    assert Books(db).unit_economics(products_validated=1, listings_drafted=1,
                                    since=NOW - timedelta(days=30))["customers"] in (0, None)
    assert sources.first_sale(db) is None, "a voided sale is not the first sale"
    # History is kept: the order row and the record (marked voided) both remain.
    assert len(orders(db)) == 1 and orders(db)[0].refunded is True
    from brambleloop.core.models import OperatingReading
    with db.session() as s:
        rec = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == sources.FIRST_SALE_KIND))
        assert rec.payload["voided"] is True and rec.payload["external_ref"] == "etsy:1:10"


def test_E2_a_voided_first_sale_hands_the_record_to_the_next_live_sale():
    db = _db()
    ingest(db, [receipt(1), receipt(2, buyer=102)])
    assert sources.first_sale(db)["external_ref"] == "etsy:1:10"
    ingest(db, [receipt(1, status="fully refunded", updated=60), receipt(2, buyer=102)],
           at=NOW + timedelta(minutes=1))
    rec = sources.first_sale(db)
    assert rec["external_ref"] == "etsy:2:20"
    assert any(h.get("external_ref") == "etsy:1:10" for h in rec["history"])
    d = pl(db).to_dict()
    assert d["orders"] == 1 and d["customers"] == 1 and d["voided_orders"] == 1


# ---------------------------------------------------------------------------
# E3


def test_E3_a_sale_in_a_currency_with_no_rate_is_held_and_sales_are_not_measured():
    for cur in ("EUR", "GBP", "AUD"):
        db = _db()
        got = ingest(db, [receipt(currency=cur)])
        assert got["ran"] is True
        assert [h["ref"] for h in got["held_unresolved"]] == ["etsy:1:10"], "never dropped"
        held = oi.held(db)
        assert held[0]["reason"] == oi.HELD_UNCONVERTED and held[0]["currency"] == cur
        assert held[0]["amount_original"] == 12.0 and held[0]["cad"] is None
        assert incident(db, oi.UNCONVERTED_INCIDENT).resolved is False
        d = pl(db).to_dict()
        assert d["sales_reading"] != "measured" and d["sales_is_lower_bound"] is True
        assert cur in d["sales_why"] and d["all_figures_observed"] is False
        # Idempotent on re-read: one record, the same incident restated.
        ingest(db, [receipt(currency=cur)], at=NOW + timedelta(minutes=1))
        assert len(oi.held(db)) == 1
        with db.session() as s:
            assert len(list(s.scalars(select(Incident).where(
                Incident.signature == oi.UNCONVERTED_INCIDENT)))) == 1
    # A later CAD sale is booked, but the first-sale record names the earlier held one.
    ingest(db, [receipt(currency="AUD"), dict(receipt(2, buyer=102), create_timestamp=int(
        NOW.timestamp()))], at=NOW + timedelta(minutes=2))
    rec = sources.first_sale(db)
    assert rec["external_ref"] == "etsy:2:20" and rec["first_sale_uncertain"] is True
    assert rec["earlier_held_sales"] == ["etsy:1:10"]


# ---------------------------------------------------------------------------
# E4


def test_E4_a_partial_ledger_fee_is_partial_with_the_missing_component_modelled():
    db = _db()
    verify(db)   # even with the mapping verified, a missing component is not measured
    ingest(db, [receipt()], [entry(1, "transaction", "transaction", 10, -78)])
    (o,) = orders(db)
    expected = round(0.78 + model_fees(12.0).payment_fee, 2)
    assert o.fees_basis == "partial" and o.fees_cad == expected
    assert o.contribution_cad == round(12.0 - expected, 2)
    assert o.detail["fees_reconciliation"] == reconcile.PARTIAL
    assert "processing_fee" in o.detail["fees_modelled_missing"]
    text = o.detail["money"]["contribution_basis"]
    assert "PARTIAL fees" in text and "ESTIMATED" not in text and "MEASURED" not in text
    with db.session() as s:
        assert s.scalar(select(LedgerEntry)).fees_basis == "partial"
    d = pl(db).to_dict()
    assert d["platform_fees_basis"] == "partial" and d["all_figures_observed"] is False


# ---------------------------------------------------------------------------
# E5


def test_E5_a_fee_credit_named_refund_is_unclassified_not_a_customer_refund():
    db = _db()
    got = ingest(db, [receipt()], [entry(3, "transaction_fee_refund", "receipt", 1, 65)])
    (o,) = orders(db)
    assert o.revenue_cad == 12.0 and o.refunded is False
    assert "ledger_refund_cad" not in o.detail
    assert "transaction_fee_refund" in got["fees"]["unclassified"]
    assert got["fees"]["ledger_incidents"][reconcile.UNCLASSIFIED_SIGNATURE] == "opened"
    assert reconcile.classify({"ledger_type": "offsite_ads_fee_refund"}) == "unclassified"


def test_E5_a_hundredfold_fee_is_held_as_anomalous_and_raised():
    db = _db()
    verify(db)
    got = ingest(db, [receipt()], [entry(2, "transaction", "transaction", 10, -7800)])
    (o,) = orders(db)
    assert o.fees_basis == "modelled" and o.fees_cad == round(model_fees(12.0).total_fees, 2)
    assert o.contribution_cad > 0, "a unit error is not booked as a loss"
    assert o.detail["fee_entries_held"] == ["2"]
    assert got["fees"]["ledger_incidents"][reconcile.ANOMALY_SIGNATURE] == "opened"
    # A plausible fee arriving later is applied, but the order cannot read complete while
    # an entry against it is held.
    ingest(db, [receipt()], [entry(2, "transaction", "transaction", 10, -7800),
                             entry(4, "transaction", "transaction", 10, -78),
                             entry(5, "processing_fee", "receipt", 1, -66)],
           at=NOW + timedelta(minutes=1))
    (o,) = orders(db)
    assert o.fees_basis == "partial" and o.fees_cad == 1.44


def test_E5_complete_fees_are_unverified_until_the_owner_verifies_the_mapping():
    db = _db()
    entries = [entry(1, "transaction", "transaction", 10, -78),
               entry(2, "processing_fee", "receipt", 1, -66)]
    got = ingest(db, [receipt()], entries)
    (o,) = orders(db)
    assert got["fees"]["mapping"] == reconcile.UNVERIFIED_MAPPING
    assert o.fees_basis == reconcile.UNVERIFIED and o.fees_cad == 1.44
    assert o.detail["fees_mapping"] == reconcile.UNVERIFIED_MAPPING
    assert o.detail["money"]["fees"]["basis"] == reconcile.UNVERIFIED_MAPPING
    assert "UNVERIFIED" in o.detail["money"]["contribution_basis"]
    d = pl(db).to_dict()
    assert d["platform_fees_basis"] == "unverified" and d["all_figures_observed"] is False
    # The owner verifies; a newly posted entry re-derives the order as measured.
    verify(db)
    assert reconcile.mapping_verified(db) is True
    ingest(db, [receipt()], entries + [entry(9, "offsite_ads_fee", "receipt", 1, -150)],
           at=NOW + timedelta(minutes=1))
    (o,) = orders(db)
    assert o.fees_basis == "measured" and o.fees_cad == 2.94
    # A verification is of one mapping: changing the unit voids it.
    with patch.object(reconcile, "LEDGER_AMOUNT_DIVISOR", 1):
        assert reconcile.mapping_verified(db) is False


def test_E5_a_ledger_refund_carries_the_unverified_mapping_basis():
    db = _db()
    ingest(db, [receipt()], [entry(7, "REFUND", "receipt", 1, -500)])
    (o,) = orders(db)
    assert o.revenue_cad == 7.0
    assert o.detail["ledger_refund_basis"] == reconcile.UNVERIFIED_MAPPING


# ---------------------------------------------------------------------------
# E6


def test_E6_a_refund_in_another_currency_is_not_read_as_the_receipts():
    db = _db()
    got = ingest(db, [receipt(status="partially refunded", refunds=[(500, "USD")])])
    assert orders(db) == []
    (h,) = oi.held(db)
    assert h["reason"] == oi.HELD_UNRECONCILED and "USD" in h["why"]
    assert got["held_incidents"][oi.UNRECONCILED_INCIDENT] == "opened"


def test_E6_duplicate_transaction_ids_refuse_the_receipt_and_raise():
    db = _db()
    r = receipt()
    r["transactions"].append(copy.deepcopy(r["transactions"][0]))
    got = ingest(db, [r])
    assert orders(db) == []
    assert any("duplicate transaction_id" in x["why"] for x in got["not_recorded"])
    inc = incident(db, oi.ANOMALY_INCIDENT)
    assert inc is not None and inc.resolved is False
    assert any(x.get("receipt_id") == 1 for x in inc.detail["refused"])


# ---------------------------------------------------------------------------
# G1


def test_G1_publication_economics_price_is_set_and_voided_orders_are_not_volume():
    from brambleloop.ops import publication_authority as pa

    db = _db()
    eco = pa._economics(db, "synthetic-product", "2.0.0")
    assert eco["price_basis"] == "set" and eco["sales_volume_basis"] == "unknown"
    ingest(db, [receipt()])
    ingest(db, [receipt(status="canceled", updated=60)], at=NOW + timedelta(minutes=1))
    with db.session() as s:
        assert s.scalar(select(Order)).product_slug == "synthetic-product"
    eco = pa._economics(db, "synthetic-product", "2.0.0")
    assert eco["sales_volume_basis"] == "unknown", "a cancelled order is not sales volume"
    ingest(db, [receipt(2, buyer=102)], at=NOW + timedelta(minutes=2))
    assert pa._economics(db, "synthetic-product", "2.0.0")["sales_volume_basis"] == "measured"


if __name__ == "__main__":
    fails = 0
    try:
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
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
