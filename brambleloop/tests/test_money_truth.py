"""Money and order truth (Final Build cluster D): F-283, F-289, F-273, F-541, F-558, F-608,
F-609, F-321, F-324, F-325, F-329.

Every test drives the real ingest (`commerce.orders_ingest.ingest`, the function the
six-hourly `commerce.orders_ingest` handler calls) or the real books/readiness readers on a
temp database, with FAKE Etsy readers only. Sockets are refused.

Run: cd brambleloop && $PY tests/test_money_truth.py
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="money_truth_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the money-truth harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select, text  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.commerce import orders_ingest  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, CostEntry, Customer, Incident,  # noqa: E402
                                     LedgerEntry, Listing, OAuthCredential, Order,
                                     OwnerAction)
from brambleloop.finance import reconcile, sources, sustainability  # noqa: E402
from brambleloop.finance.books import Books  # noqa: E402
from brambleloop.integrations.etsy_oauth import EtsyAuthNeedsOwner  # noqa: E402

NOW = datetime.now(timezone.utc)
_n = [0]


def _db():
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/money{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _open_gate(db):
    with db.session() as s:
        s.add(AuditLog(actor="market_radar", action="etsy.probe", detail={"ok": True}))
        s.add(OAuthCredential(provider="etsy", refresh_token_sealed="sealed",
                              token_fingerprint="abcd1234",
                              scopes="listings_r listings_w shops_r transactions_r"))


def _receipt(rid, buyer, listing_id, cents, *, days_ago=1, lines=1, status="paid"):
    return {"receipt_id": rid, "buyer_user_id": buyer, "status": status,
            "create_timestamp": int((NOW - timedelta(days=days_ago)).timestamp()),
            "refunds": [],
            "transactions": [{"transaction_id": rid * 10 + i, "listing_id": listing_id,
                              "quantity": 1,
                              "price": {"amount": cents, "divisor": 100,
                                        "currency_code": "CAD"}}
                             for i in range(lines)]}


def _entry(eid, ledger_type, ref_type, ref_id, cents, currency="CAD"):
    """A fake payment-account ledger entry in Etsy's documented shape. Never Etsy."""
    return {"entry_id": eid, "ledger_type": ledger_type, "reference_type": ref_type,
            "reference_id": str(ref_id), "amount": cents, "currency": currency,
            "created_timestamp": int(NOW.timestamp())}


class Feed:
    """Receipts only: a reader that cannot read the payment-account ledger."""

    def __init__(self, receipts):
        self.receipts_list = receipts
        self.calls = 0

    def receipts(self, *, since):
        self.calls += 1
        return list(self.receipts_list)


class LedgerFeed(Feed):
    """Receipts and the payment-account ledger."""

    def __init__(self, receipts, entries):
        super().__init__(receipts)
        self.entries = entries
        self.windows = []

    def ledger_entries(self, *, min_created, max_created):
        self.calls += 1
        self.windows.append((min_created, max_created))
        return list(self.entries)


class Revoked:
    """A reader whose credential only the owner can fix."""

    def __init__(self, message):
        self.message = message
        self.calls = 0

    def receipts(self, *, since):
        self.calls += 1
        raise EtsyAuthNeedsOwner(self.message)


def _listing(db, slug="cloudline-baby-blanket", etsy_id="222", price=9.0, state="published",
             created=None):
    with db.session() as s:
        s.add(Listing(product_slug=slug, version="1.0.0", title="B", description="",
                      price_cad=price, state=state, etsy_listing_id=etsy_id,
                      created_at=created or NOW - timedelta(weeks=8)))


# ---------------------------------------------------------------------------
# F-283 / F-289 / F-609: what ingest writes


def test_ingest_writes_unknown_source_and_a_modelled_fee_never_presented_as_charged():
    db = _db()
    _listing(db)
    _open_gate(db)
    got = orders_ingest.ingest(db, reader=Feed([_receipt(1, 501, "222", 900)]))
    assert got["ran"] and got["orders_created"] == 1
    assert got["fees"]["read"] is False and got["fees"]["basis"] == "modelled"
    with db.session() as s:
        order = s.scalar(select(Order))
        customer = s.scalar(select(Customer))
        row = s.scalar(select(LedgerEntry))
    assert order.acquisition_source == "unknown" and customer.acquisition_source == "unknown"
    assert order.fees_basis == "modelled" and order.offsite_ads_fee_cad is None
    assert order.fees_cad > 0
    # F-609: the ledger row is auditable -- source, external id, currency, original amount,
    # classification, basis per figure and reconciliation state.
    assert row.source == "etsy_receipts" and row.external_id == "etsy:1:10"
    assert row.currency == "CAD" and row.amount_original == 9.0
    assert row.classification == "sale" and row.basis == "measured"
    assert row.fees_basis == "modelled" and row.reconciliation_state == "unreconciled"


def test_the_first_sale_is_recorded_once_with_source_evidence_and_the_scale_caveat():
    db = _db()
    _listing(db)
    _open_gate(db)
    got = orders_ingest.ingest(db, reader=Feed([_receipt(1, 501, "222", 900, days_ago=3)]))
    assert got["first_sale"]["created"] is True
    orders_ingest.ingest(db, reader=Feed([_receipt(1, 501, "222", 900, days_ago=3),
                                          _receipt(2, 502, "222", 900, days_ago=1)]))
    record = sources.first_sale(db)
    assert record["external_ref"] == "etsy:1:10", "a later order never replaces the first"
    assert record["acquisition_source"] == "unknown" and record["channel"] == "unattributed"
    assert "receipt does not say how the buyer arrived" in record["evidence"]
    assert "possibility, not scale" in record["note"]


def test_the_traffic_table_shows_every_channel_and_an_explicit_unattributed_bucket():
    db = _db()
    _listing(db)
    _open_gate(db)
    orders_ingest.ingest(db, reader=Feed([_receipt(i, 500 + i, "222", 900) for i in (1, 2, 3)]))
    sources.attribute(db, "etsy:1:10", "etsy_ads", evidence="owner: Etsy Ads report, order 1")
    t = sources.table(db)
    assert set(t["channels"]) == {"etsy_organic", "etsy_ads", "offsite_ads", "owned_direct",
                                  "unattributed"}
    assert t["channels"]["etsy_ads"]["orders"] == 1
    assert t["channels"]["unattributed"]["orders"] == 2
    assert t["channels"]["etsy_organic"]["orders"] == 0, "no order credited to organic by default"
    assert t["total_orders"] == sum(r["orders"] for r in t["channels"].values())


def test_an_acquisition_source_without_evidence_is_refused():
    db = _db()
    _listing(db)
    _open_gate(db)
    orders_ingest.ingest(db, reader=Feed([_receipt(1, 501, "222", 900)]))
    for source, evidence in (("etsy_organic", ""), ("etsy", "a guess")):
        try:
            sources.attribute(db, "etsy:1:10", source, evidence=evidence)
        except sources.AttributionRefused:
            continue
        raise AssertionError(f"{source!r}/{evidence!r} was accepted")


# ---------------------------------------------------------------------------
# F-558 / F-273: measured fees from the payment-account ledger


def _ledger_entries():
    return [
        _entry(9001, "transaction", "transaction", 10, -59),        # 6.5% of 9.00
        _entry(9002, "processing_fee", "receipt", 1, -60),
        _entry(9003, "offsite_ads_fee", "receipt", 1, -135),        # 15% of 9.00
        _entry(9004, "listing", "listing", 222, -27),               # a listing fee: no order
        _entry(9005, "mystery_kind", "receipt", 1, -5),             # never counted as a fee
    ]


def test_charged_fees_replace_the_model_and_an_offsite_fee_is_deducted_and_attributed():
    db = _db()
    _listing(db)
    _open_gate(db)
    feed = LedgerFeed([_receipt(1, 501, "222", 900)], _ledger_entries())
    got = orders_ingest.ingest(db, reader=feed)
    assert got["fees"]["read"] is True and got["fees"]["orders_measured"] == 1
    assert "mystery_kind" in got["fees"]["unclassified"]
    assert [u["entry_id"] for u in got["fees"]["unmatched_fee_entries"]] == ["9004"]
    with db.session() as s:
        order = s.scalar(select(Order))
        row = s.scalar(select(LedgerEntry))
    assert order.fees_basis == "measured" and abs(order.fees_cad - 2.54) < 1e-9
    assert order.offsite_ad_attributed is True and order.offsite_ads_fee_cad == 1.35
    assert abs(order.contribution_cad - (9.0 - 2.54)) < 1e-9, "offsite fee is deducted"
    assert order.acquisition_source == "offsite_ads"
    assert "Offsite Ads fee entry 9003" in order.detail["attribution"]["evidence"]
    assert row.fees_basis == "measured" and row.fees_cad == order.fees_cad
    assert row.reconciliation_state == reconcile.RECONCILED
    # The first-sale record follows the evidence that arrived.
    assert sources.first_sale(db)["acquisition_source"] == "offsite_ads"
    assert sources.table(db)["channels"]["offsite_ads"]["orders"] == 1


def test_an_etsy_fee_for_an_order_we_do_not_have_opens_one_reconciliation_incident():
    """F-608: disagreement between Etsy and the internal orders is an incident."""
    db = _db()
    _listing(db)
    _open_gate(db)
    receipts = [_receipt(1, 501, "222", 900)]
    orphan = _entry(7001, "transaction", "transaction", 999990, -59)
    got = orders_ingest.ingest(db, reader=LedgerFeed(receipts, _ledger_entries() + [orphan]))
    assert got["fees"]["orphan_fee_entries"] == 1
    assert got["fees"]["reconciliation_incident"] == "opened"
    again = orders_ingest.ingest(db, reader=LedgerFeed(receipts, _ledger_entries() + [orphan]))
    assert again["fees"]["reconciliation_incident"] == "unchanged"
    with db.session() as s:
        incidents = list(s.scalars(select(Incident).where(
            Incident.signature == reconcile.RECONCILIATION_SIGNATURE)))
    assert len(incidents) == 1 and "transaction:999990" in incidents[0].detail["references"]


def test_fee_reconciliation_is_idempotent_and_adds_a_late_fee_incrementally():
    db = _db()
    _listing(db)
    _open_gate(db)
    receipts = [_receipt(1, 501, "222", 900)]
    entries = _ledger_entries()[:1]                  # only the transaction fee has posted
    orders_ingest.ingest(db, reader=LedgerFeed(receipts, entries))
    with db.session() as s:
        order = s.scalar(select(Order))
    assert order.fees_cad == 0.59 and order.offsite_ad_attributed is False
    assert order.detail["fees_reconciliation"] == reconcile.PARTIAL
    orders_ingest.ingest(db, reader=LedgerFeed(receipts, entries))          # same window
    with db.session() as s:
        assert s.scalar(select(Order)).fees_cad == 0.59, "a re-read added nothing"
    orders_ingest.ingest(db, reader=LedgerFeed(receipts, _ledger_entries()))  # later posts
    with db.session() as s:
        order = s.scalar(select(Order))
    assert abs(order.fees_cad - 2.54) < 1e-9 and order.offsite_ads_fee_cad == 1.35
    assert order.detail["fees_reconciliation"] == reconcile.RECONCILED


def test_a_receipt_level_fee_is_shared_across_its_lines_by_price():
    db = _db()
    _listing(db)
    _open_gate(db)
    feed = LedgerFeed([_receipt(1, 501, "222", 900, lines=2)],
                      [_entry(1, "processing_fee", "receipt", 1, -100)])
    orders_ingest.ingest(db, reader=feed)
    with db.session() as s:
        fees = sorted(o.fees_cad for o in s.scalars(select(Order)))
    assert fees == [0.5, 0.5]


def test_a_cancelled_receipt_keeps_no_revenue():
    db = _db()
    _listing(db)
    _open_gate(db)
    orders_ingest.ingest(db, reader=Feed([_receipt(1, 501, "222", 900, status="canceled")]))
    with db.session() as s:
        order = s.scalar(select(Order))
    assert order.refunded is True and order.revenue_cad == 0.0
    assert order.detail["receipt_status"] == "canceled"


def test_the_production_reader_reads_the_ledger_through_the_client_transport():
    """The thin reader goes through the client's own scope check and call path."""

    class Creds:
        shop_id = "42"

    class Client:
        def __init__(self):
            self.sent = []

        def _require(self, _authority):
            return Creds()

        def _call(self, method, path, *, operation, authority, query):
            self.sent.append((method, path, operation, query))

            class R:
                body = {"results": [{"entry_id": 1}]}
            return R()

    client = Client()
    reader = orders_ingest.EtsyReceiptReader(client)
    got = reader.ledger_entries(min_created=NOW - timedelta(days=2), max_created=NOW)
    assert got == [{"entry_id": 1}] and reader.calls == 1
    method, path, operation, query = client.sent[0]
    assert (method, path) == ("GET", "/shops/42/payment-account/ledger-entries")
    assert operation == "getShopPaymentAccountLedgerEntries"
    assert query["min_created"] < query["max_created"]


# ---------------------------------------------------------------------------
# F-541: credential failures become one owner action and one incident


def test_each_auth_failure_class_raises_one_idempotent_owner_action_and_incident():
    cases = {
        "refresh_refused": "Etsy refused the refresh grant with 400: invalid_grant. ...",
        "access_revoked": "Etsy refused the refresh grant with 401: revoked. ...",
        "scope_drift": "this token cannot perform getShopReceipts: it is missing "
                       "['transactions_r']. ...",
        "no_credential": "no refresh token. ETSY_REFRESH_TOKEN is read from the environment",
    }
    assert len(cases) == 4
    for expected, message in cases.items():
        db = _db()
        _open_gate(db)
        got = orders_ingest.ingest(db, reader=Revoked(message))
        assert got["ran"] is False and got["reading"] == "UNMEASURED", expected
        assert got["auth_failure"]["failure_class"] == expected, got["auth_failure"]
        again = orders_ingest.ingest(db, reader=Revoked(message))
        assert again["auth_failure"]["owner_action"] == "restated"
        assert again["auth_failure"]["incident"] == "counted"
        with db.session() as s:
            actions = list(s.scalars(select(OwnerAction).where(
                OwnerAction.requirement_key == orders_ingest.AUTH_ACTION_KEY)))
            incidents = list(s.scalars(select(Incident).where(
                Incident.signature == orders_ingest.AUTH_INCIDENT_SIGNATURE)))
            orders = list(s.scalars(select(Order)))
        assert len(actions) == 1 and actions[0].minutes and "Re-authorise" in actions[0].action
        assert len(incidents) == 1 and incidents[0].report_count == 2
        assert not orders


def test_an_auth_failure_never_reopens_an_action_the_owner_closed():
    db = _db()
    _open_gate(db)
    orders_ingest.ingest(db, reader=Revoked("invalid_grant"))
    with db.session() as s:
        s.scalar(select(OwnerAction)).done = True
    got = orders_ingest.ingest(db, reader=Revoked("invalid_grant"))
    assert got["auth_failure"]["owner_action"] == "already_decided"


# ---------------------------------------------------------------------------
# F-608: the books read the order source


def test_the_books_measure_sales_only_after_a_connected_source_was_read():
    db = _db()
    _listing(db)
    assert Books(db).profit_and_loss().to_dict()["sales_reading"] == "UNMEASURED"
    _open_gate(db)
    orders_ingest.ingest(db, reader=LedgerFeed([_receipt(1, 501, "222", 900)],
                                               _ledger_entries()))
    with db.session() as s:   # what the runtime handler audits after a completed read
        s.add(AuditLog(actor="cfo", action="commerce.orders_ingested",
                       detail={"ran": True}))
    d = Books(db).profit_and_loss().to_dict()
    assert d["sales_reading"] == "measured" and d["gross_sales_cad"] == 9.0
    assert d["platform_fees_basis"] == "measured" and d["all_figures_observed"] is True
    assert d["customers"] == 1
    assert d["sales_by_source"]["channels"]["offsite_ads"]["orders"] == 1


# ---------------------------------------------------------------------------
# F-609 migration: additive columns reach an existing database


def test_the_ledger_columns_are_added_to_an_existing_table_without_touching_its_rows():
    path = f"{_TMP}/legacy.sqlite"
    db = Database(f"sqlite:///{path}")
    with db.engine.begin() as conn:
        conn.execute(text("CREATE TABLE ledger (id INTEGER PRIMARY KEY, at DATETIME, "
                          "category VARCHAR(40), description TEXT, gross_cad FLOAT, "
                          "fees_cad FLOAT, refunds_cad FLOAT, expense_cad FLOAT, "
                          "evidence_ref VARCHAR(200))"))
        conn.execute(text("INSERT INTO ledger (at, category, description, gross_cad, "
                          "fees_cad, refunds_cad, expense_cad, evidence_ref) VALUES "
                          "('2026-09-01 00:00:00', 'sale', 'old', 12.0, 1.4, 0, 0, 'x')"))
    db.create_all()
    with db.session() as s:
        row = s.scalar(select(LedgerEntry))
    assert row.gross_cad == 12.0 and row.fees_cad == 1.4
    assert row.fees_basis == "unknown" and row.basis == "unknown", "never backfilled measured"
    assert row.reconciliation_state == "unreconciled" and row.amount_original is None


# ---------------------------------------------------------------------------
# F-321 / F-324 / F-325 / F-329


def _costs(db, rows):
    with db.session() as s:
        for at, amount, slug, purpose in rows:
            s.add(CostEntry(agent="gateway", kind="llm", amount_cad=amount, at=at,
                            product_slug=slug, purpose=purpose))


def test_the_forecast_refuses_on_thin_data_and_shows_only_a_floor():
    db = _db()
    _costs(db, [(NOW - timedelta(days=2), 0.5, "", "radar")])
    f = sustainability.forecast(db, now=NOW)
    assert f["status"] == "INSUFFICIENT_DATA" and f["scenarios"] is None
    assert any("cost history" in m for m in f["missing"])
    assert any("opening prices" in m for m in f["missing"])
    v = sustainability.verdict(db, now=NOW)
    assert v["sustainable"] is False and "waits on a forecast" in v["why"]


def _operating_history(db, *, platform_per_day):
    rows = []
    for d in range(1, 31):
        rows.append((NOW - timedelta(days=d), platform_per_day, "", "observation"))
    rows.append((NOW - timedelta(days=40), 3.0, "cloudline-baby-blanket", "creation"))
    rows.append((NOW - timedelta(days=5), 0.3, "cloudline-baby-blanket", "revalidation"))
    _costs(db, rows)
    _listing(db, created=NOW - timedelta(days=20))


def test_break_even_and_maintenance_split_creation_from_recurring_cost():
    db = _db()
    _operating_history(db, platform_per_day=0.01)
    be = sustainability.break_even(db)["products"]["cloudline-baby-blanket"]
    assert be["creation_cost_cad"] == 3.0, "spend after the listing went live is not creation"
    assert be["maintenance_cost_so_far_cad"] == 0.3
    assert be["contribution_basis"].startswith("modelled")
    assert be["break_even_sales"] == -(-3.0 // be["contribution_per_sale_cad"])
    m = sustainability.listing_maintenance_cost(db, now=NOW)
    assert m["reading"] == "unknown" and m["per_listing_month_cad"] > 0
    assert m["cost_basis"]["actual_cad"] is None  # legacy fixture has no charged-rate evidence
    assert sustainability.listing_maintenance_cost(_db())["reading"] == "UNMEASURED"


def test_the_forecast_names_low_base_high_and_the_gate_blocks_unsustainable_cost():
    db = _db()
    _operating_history(db, platform_per_day=0.01)
    f = sustainability.forecast(db, now=NOW)
    assert f["status"] == "computed" and set(f["scenarios"]) == {"low", "base", "high"}
    for s in f["scenarios"].values():
        assert s["assumptions"]["sales_per_month"] and s["why"]
    assert (f["scenarios"]["low"]["ai_cost_monthly_cad"]
            < f["scenarios"]["high"]["ai_cost_monthly_cad"])
    assert sustainability.verdict(db, now=NOW)["sustainable"] is True
    expensive = _db()
    _operating_history(expensive, platform_per_day=20.0)     # CA$600/month of inference
    v = sustainability.verdict(expensive, now=NOW)
    assert v["sustainable"] is False and "blocked until corrected" in v["why"]


def test_launch_readiness_carries_the_sustainable_economics_requirement():
    from brambleloop.launch.readiness import assess

    db = _db()
    by = {r.key: r for r in assess(db, phase="shadow").requirements}
    req = by["sustainable_economics"]
    assert req.ready is False and req.blocked_by == "build"
    assert req.evidence["status"] == "INSUFFICIENT_DATA" and req.evidence["missing"]


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
