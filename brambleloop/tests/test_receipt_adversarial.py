"""Codex's adversarial receipt cases, made permanent (FB-2 O; Codex C-78, CB2-O01..O08,
CB2-P15).

The first eleven tests are the cases of Codex's offline script
`test_receipt_adversarial.py` (11 cases; at 0f3f5d1 it gave 8 FAIL / 3 PASS, against the
unmerged orders2 commit 3081402 10 / 1), carried over with the same fixtures and the same
assertions: synthetic receipts in Etsy's public v3 shape, a fresh SQLite database, the
production `commerce.orders_ingest.ingest` service, and no network. The rest pin the money
fixes that sit beside them: losses are not clamped in `finance.reconcile`, ledger refund
entries are applied, loop counters follow a refund down, a band that cannot clear the net
floor is refused, and unit-cost contribution is windowed with the cost it is divided by.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_receipt_adversarial.py
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="receipt_adversarial_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.update(BRAMBLELOOP_PHASE="shadow", BRAMBLELOOP_REQUIRE_POSTGRES="0")
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC", "OPENAI", "ETSY", "GEMINI", "GOOGLE_API", "DATABASE_URL",
                      "BRAMBLELOOP_DATABASE")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the receipt-adversarial harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.socket.connect_ex = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.commerce import buyer_trust  # noqa: E402
from brambleloop.commerce import orders_ingest as oi  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, CostEntry, Customer, GrowthLoop,  # noqa: E402
                                     LedgerEntry, Listing, OAuthCredential, Order,
                                     OrderVersion)

NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
_n = [0]


def receipt(rid=1, *, days=1, paid=True, status="paid", refund=0, amount=1200, buyer=101):
    """Codex's fixture, unchanged: one CAD line on listing 111, updated at NOW."""
    return {"receipt_id": rid, "buyer_user_id": buyer,
            "create_timestamp": int((NOW - timedelta(days=days)).timestamp()),
            "update_timestamp": int(NOW.timestamp()), "status": status, "is_paid": paid,
            "refunds": ([{"amount": {"amount": refund, "divisor": 100,
                                     "currency_code": "CAD"}}] if refund else []),
            "transactions": [{"transaction_id": rid * 10, "listing_id": 111, "quantity": 1,
                              "price": {"amount": amount, "divisor": 100,
                                        "currency_code": "CAD"}}]}


class Feed:
    """A fake reader. `filter_created` makes `since` a CREATION filter, as a reader that
    does not declare a last-modified watermark may treat it."""

    def __init__(self, rows, filter_created=False):
        self.rows = rows
        self.calls = 0
        self.filter_created = filter_created
        self.since = None

    def receipts(self, *, since):
        self.calls += 1
        self.since = since
        return [r for r in self.rows if not self.filter_created or since is None
                or r["create_timestamp"] >= since.timestamp()]


def snapshot(db):
    with db.session() as s:
        return {
            "orders": [{k: getattr(o, k) for k in ("external_ref", "version", "revenue_cad",
                                                   "contribution_cad", "refunded",
                                                   "is_repeat", "acquisition_source")}
                       for o in s.scalars(select(Order).order_by(Order.id))],
            "ledger": [{k: getattr(o, k) for k in ("evidence_ref", "gross_cad", "refunds_cad",
                                                   "net_cad")}
                       for o in s.scalars(select(LedgerEntry).order_by(LedgerEntry.id))],
            "versions": [{"ref": o.order_ref, "version": o.version}
                         for o in s.scalars(select(OrderVersion))],
            "customers": [{"ref": o.customer_ref,
                           "first_seen_at": o.first_seen_at.isoformat()}
                          for o in s.scalars(select(Customer))]}


def _url():
    _n[0] += 1
    return f"sqlite:///{_TMP}/case{_n[0]}.db"


def _db(url=None):
    url = url or _url()
    db = Database(url, scratch=True)
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


def ingest(db, rows, **kwargs):
    return oi.ingest(db, reader=Feed(rows, **kwargs), now=NOW)


# ---------------------------------------------------------------------------
# Codex's eleven cases


def test_control_paid_receipt_is_idempotent():
    db = _db()
    ingest(db, [receipt()])
    ingest(db, [receipt()])
    v = snapshot(db)
    assert (len(v["orders"]), len(v["ledger"]), len(v["versions"])) == (1, 1, 1)


def test_control_closed_gate_never_reads_feed():
    db = _db()
    with db.session() as s:
        s.get(OAuthCredential, "etsy").scopes = ""
    feed = Feed([receipt()])
    out = oi.ingest(db, reader=feed, now=NOW)
    assert not out["ran"] and feed.calls == 0 and snapshot(db)["orders"] == []


def test_O01_late_full_refund_reconciles_existing_order():
    db = _db()
    ingest(db, [receipt()])
    ingest(db, [receipt(refund=1200)])
    v = snapshot(db)
    assert (v["orders"][0]["revenue_cad"], v["ledger"][0]["refunds_cad"]) == (0, 12)


def test_O01_partial_refund_preserves_unreturned_revenue():
    db = _db()
    ingest(db, [receipt(refund=200)])
    v = snapshot(db)
    assert (v["orders"][0]["revenue_cad"], v["ledger"][0]["refunds_cad"]) == (10, 2)


def test_O01_old_modified_receipt_is_not_lost_to_creation_watermark():
    db = _db()
    ingest(db, [receipt(1, days=60), receipt(2, days=1, buyer=202)])
    feed = Feed([receipt(1, days=60, refund=1200), receipt(2, days=1, buyer=202)],
                filter_created=True)
    out = oi.ingest(db, reader=feed, now=NOW)
    assert snapshot(db)["orders"][0]["revenue_cad"] == 0
    # The reader was asked from the change window, and the run says why.
    assert feed.since is not None and feed.since <= NOW - oi.CHANGE_WINDOW
    assert "change window" in out["read_mode"]


def test_O02_unpaid_open_receipt_creates_no_sales_revenue():
    db = _db()
    ingest(db, [receipt(paid=False, status="open")])
    assert sum(r["revenue_cad"] for r in snapshot(db)["orders"]) == 0


def test_O02_cancelled_receipt_creates_no_sales_revenue():
    db = _db()
    ingest(db, [receipt(status="canceled")])
    assert sum(r["revenue_cad"] for r in snapshot(db)["orders"]) == 0


def test_O03_imported_old_sale_does_not_inherit_future_listing_version():
    db = _db()
    ingest(db, [receipt(days=60)])
    assert "2.0.0" not in [r["version"] for r in snapshot(db)["versions"]], (
        "only the current listing version is known and it postdates this sale")


def test_O04_first_purchase_is_earliest_not_first_encountered():
    db = _db()
    ingest(db, [receipt(2, days=1), receipt(1, days=60)])
    first = snapshot(db)["customers"][0]["first_seen_at"]
    assert first.startswith((NOW - timedelta(days=60)).date().isoformat()), first


def test_O05_retry_after_order_commit_repairs_version_evidence():
    url = _url()
    db = _db(url)
    with patch.object(buyer_trust, "record_sale_version",
                      side_effect=RuntimeError("injected post-order-commit interruption")):
        try:
            ingest(db, [receipt()])
        except RuntimeError as exc:
            assert "injected" in str(exc)
        else:
            raise AssertionError("the injected interruption did not surface")
    db.engine.dispose()
    db = Database(url, scratch=True)
    ingest(db, [receipt()])
    v = snapshot(db)
    assert (len(v["orders"]), len(v["versions"]), len(v["ledger"])) == (1, 1, 1)


def test_O07_negative_contribution_matches_negative_ledger():
    db = _db()
    ingest(db, [receipt(amount=1)])
    v = snapshot(db)
    assert v["ledger"][0]["net_cad"] < 0
    assert abs(v["orders"][0]["contribution_cad"] - v["ledger"][0]["net_cad"]) < 0.005


# ---------------------------------------------------------------------------
# The money beside them


class LedgerFeed(Feed):
    """Receipts plus Etsy payment-account ledger entries."""

    SINCE_IS_LAST_MODIFIED = True

    def __init__(self, rows, entries):
        super().__init__(rows)
        self.entries = entries

    def ledger_entries(self, *, min_created, max_created):
        self.calls += 1
        return list(self.entries)


def _entry(eid, ledger_type, ref_type, ref_id, cents):
    return {"entry_id": eid, "ledger_type": ledger_type, "reference_type": ref_type,
            "reference_id": str(ref_id), "amount": cents, "currency": "CAD",
            "created_timestamp": int(NOW.timestamp())}


def _verify_mapping(db):
    """The owner's recorded verification of the ledger mapping: without it a ledger fee is
    `unverified`, never `measured` (RC1 audit E5)."""
    from brambleloop.finance import reconcile

    # rc1-ORD2: recorded only under the owner credential, sealed and chained.
    os.environ["BRAMBLELOOP_OPS_TOKEN"] = "local-owner-ledger-mapping-token-32chars"
    reconcile.record_mapping_verification(db, authorization="local-owner-ledger-mapping-token-32chars", by="owner",
                                          evidence="synthetic fixture")


def test_O07_reconcile_keeps_a_refunded_sales_measured_fee_as_a_loss():
    """finance.reconcile no longer clamps contribution at zero: a fully refunded sale whose
    measured fees stayed with Etsy is a loss on the order, equal to the ledger's net."""
    db = _db()
    _verify_mapping(db)
    rows = [receipt(refund=1200)]
    oi.ingest(db, reader=LedgerFeed(rows, [_entry(1, "transaction", "transaction", 10, -78),
                                           _entry(2, "processing_fee", "receipt", 1, -66)]),
              now=NOW)
    with db.session() as s:
        o = s.scalar(select(Order))
        row = s.scalar(select(LedgerEntry))
    assert o.fees_basis == "measured" and abs(o.fees_cad - 1.44) < 1e-9
    assert o.revenue_cad == 0 and abs(o.contribution_cad - (-1.44)) < 1e-9
    assert abs(o.contribution_cad - row.net_cad) < 0.005


def test_O07_a_later_refund_keeps_the_measured_fee():
    """A receipt reconciled after Etsy's fee was measured moves revenue, not the fee."""
    db = _db()
    _verify_mapping(db)
    entries = [_entry(1, "transaction", "transaction", 10, -78),
               _entry(2, "processing_fee", "receipt", 1, -66)]
    oi.ingest(db, reader=LedgerFeed([receipt()], entries), now=NOW)
    later = dict(receipt(refund=200), update_timestamp=int(NOW.timestamp()) + 60)
    oi.ingest(db, reader=LedgerFeed([later], entries), now=NOW + timedelta(minutes=5))
    with db.session() as s:
        o = s.scalar(select(Order))
        row = s.scalar(select(LedgerEntry))
    assert o.fees_basis == "measured" and abs(o.fees_cad - 1.44) < 1e-9
    assert o.revenue_cad == 10.0 and abs(o.contribution_cad - (10.0 - 1.44)) < 1e-9
    assert row.fees_basis == "measured" and abs(row.fees_cad - 1.44) < 1e-9
    assert row.refunds_cad == 2.0 and abs(o.contribution_cad - row.net_cad) < 0.005


def test_O01_a_ledger_refund_the_receipt_has_not_shown_is_applied_once():
    """Etsy's ledger shows money paid back that the receipt does not carry yet: the order's
    revenue follows the ledger (money that left is not revenue), idempotently, and a later
    receipt that still lacks it does not undo it."""
    db = _db()
    entries = [_entry(7, "REFUND", "receipt", 1, -500)]
    oi.ingest(db, reader=LedgerFeed([receipt()], entries), now=NOW)
    oi.ingest(db, reader=LedgerFeed([receipt()], entries), now=NOW + timedelta(minutes=5))
    with db.session() as s:
        o = s.scalar(select(Order))
        row = s.scalar(select(LedgerEntry))
    assert o.revenue_cad == 7.0 and row.refunds_cad == 5.0
    assert o.detail["refund_reconciliation"] == "raised_to_etsy_ledger"
    assert o.detail["refund_entries"] == ["7"] and o.detail["ledger_refund_cad"] == 5.0
    assert abs(o.contribution_cad - (7.0 - o.fees_cad)) < 1e-9
    later = dict(receipt(), update_timestamp=int(NOW.timestamp()) + 600)
    oi.ingest(db, reader=LedgerFeed([later], entries), now=NOW + timedelta(minutes=15))
    with db.session() as s:
        assert s.scalar(select(Order)).revenue_cad == 7.0


def test_O01_a_refund_for_an_order_we_do_not_have_joins_the_reconciliation_incident():
    from brambleloop.core.models import Incident
    from brambleloop.finance import reconcile

    db = _db()
    out = oi.ingest(db, reader=LedgerFeed([receipt()], [_entry(8, "REFUND", "receipt", 99,
                                                               -300)]), now=NOW)
    assert out["fees"]["reconciliation_incident"] == "opened"
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == reconcile.RECONCILIATION_SIGNATURE))
    assert inc is not None and "8" in inc.detail["entry_ids"]


def test_O06_a_refund_moves_the_loop_counter_down():
    from brambleloop.commerce import order_readings as orr

    db = _db()
    row = dict(refunded=False, acquisition_source="offsite_ads", contribution_cad=5.0)
    orr.loop_block(db, [row])
    with db.session() as s:
        assert s.scalar(select(GrowthLoop).where(GrowthLoop.key == "paid_ads")).orders == 1
    got = orr.loop_block(db, [dict(row, refunded=True, contribution_cad=-0.9)])
    with db.session() as s:
        loop = s.scalar(select(GrowthLoop).where(GrowthLoop.key == "paid_ads"))
        assert (loop.orders, loop.contribution_cad) == (0, -0.9)
    assert got["by_loop"]["paid_ads"] == {"orders": 1, "refunded": 1, "net_orders": 0,
                                          "contribution": -0.9}


def test_O08_a_band_that_cannot_clear_the_net_floor_is_refused():
    from brambleloop.commerce.pricing import decide_price

    d = decide_price("x", category_band_cad=(1.0, 1.2), proposed_cad=1.1)
    assert d.refused and "floor is binding" in d.refused
    assert d.to_dict()["refused"] == d.refused


def test_P15_unit_cost_contribution_is_windowed_with_the_cost():
    from brambleloop.finance import unit_cost

    db = _db()
    now = datetime.now(timezone.utc)
    with db.session() as s:
        s.add(LedgerEntry(at=now - timedelta(days=400), category="sale", description="old",
                          gross_cad=100.0, fees_cad=0.0, refunds_cad=0.0, evidence_ref="old-1"))
        s.add(CostEntry(agent="x", amount_cad=10.0, at=now - timedelta(days=1), purpose="t"))
    r = unit_cost.unit_costs(db, days=30, now=now)
    assert r["contribution_cad"] == 0.0 and r["lifetime_contribution_cad"] == 100.0
    assert r["contribution_per_operating_dollar"] == 0.0 and r["burning"] is True
    with db.session() as s:
        s.add(LedgerEntry(at=now - timedelta(days=3), category="sale", description="new",
                          gross_cad=20.0, fees_cad=2.0, refunds_cad=0.0, evidence_ref="new-1"))
    r = unit_cost.unit_costs(db, days=30, now=now)
    assert r["contribution_cad"] == 18.0 and r["burning"] is False
    assert r["contribution_per_operating_dollar"] == 1.8


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
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
