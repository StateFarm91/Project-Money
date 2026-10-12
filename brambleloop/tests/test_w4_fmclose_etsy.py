"""W4-FMCLOSE: Final Master Etsy-commerce rows whose transactions_r gate cleared on 2026-10-12.

Each test names the requirement and asserts its acceptance criterion against the real code
paths on a temp database, with FAKE Etsy readers and signed FAKE webhook deliveries only.
Sockets are refused; nothing calls Etsy.

  F-512 Webhook Reliability         validation, idempotency, duplicate protection, retries,
                                    storage, observability (integrations.etsy_webhooks)
  F-501 Etsy Event Feedback         a verified event feeds the durable idempotent order layer
  F-570 Offsite Ads Economics       attribution tri-state; unread is never a measured 0 %
  F-574 Marketing Channel Attribution  per listing/family comparison, one credit per order
  F-590 Sales Channel Inventory     every sale's channel vs the readied inventory
  F-595 First-10-Sales Protocol     per-sale inspection record + live-listing edit hold

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_fmclose_etsy.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import base64
import json
import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="fmclose_etsy_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the FMCLOSE harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.commerce import first_ten, orders_ingest, paid_media, sales_channels  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, Incident, Job, Listing,  # noqa: E402
                                     OAuthCredential, OperatingReading, Order)
from brambleloop.finance import channel_comparison, reconcile, sources  # noqa: E402
from brambleloop.integrations import etsy_webhooks as wh  # noqa: E402

NOW = datetime.now(timezone.utc)
SECRET = "whsec_" + base64.b64encode(b"fmclose-test-signing-key-32bytes!").decode()
_n = [0]


def _db():
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/fmclose{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _open_gate(db):
    with db.session() as s:
        s.add(AuditLog(actor="market_radar", action="etsy.probe", detail={"ok": True}))
        s.add(OAuthCredential(provider="etsy", refresh_token_sealed="sealed",
                              token_fingerprint="abcd1234",
                              scopes="listings_r listings_w shops_r transactions_r"))


def _verify_mapping(db):
    os.environ["BRAMBLELOOP_OPS_TOKEN"] = "local-owner-ledger-mapping-token-32chars"
    reconcile.record_mapping_verification(
        db, authorization="local-owner-ledger-mapping-token-32chars", by="owner",
        evidence="synthetic test fixture")


def _receipt(rid, buyer, listing_id, cents, *, days_ago=1, receipt_type=0, refunds=()):
    r = {"receipt_id": rid, "buyer_user_id": buyer, "status": "paid",
         "create_timestamp": int((NOW - timedelta(days=days_ago)).timestamp()),
         "refunds": list(refunds),
         "transactions": [{"transaction_id": rid * 10, "listing_id": listing_id,
                           "quantity": 1,
                           "price": {"amount": cents, "divisor": 100, "currency_code": "CAD"}}]}
    if receipt_type is not None:
        r["receipt_type"] = receipt_type
    return r


def _entry(eid, ledger_type, ref_type, ref_id, cents):
    return {"entry_id": eid, "ledger_type": ledger_type, "reference_type": ref_type,
            "reference_id": str(ref_id), "amount": cents, "currency": "CAD",
            "created_timestamp": int(NOW.timestamp())}


class Feed:
    def __init__(self, receipts, entries=None):
        self.receipts_list, self.entries, self.calls = receipts, entries, 0

    def receipts(self, *, since):
        self.calls += 1
        return list(self.receipts_list)


class LedgerFeed(Feed):
    def ledger_entries(self, *, min_created, max_created):
        self.calls += 1
        return list(self.entries or [])


def _listing(db, slug="cloudline-baby-blanket", etsy_id="222", category=""):
    with db.session() as s:
        s.add(Listing(product_slug=slug, version="1.0.0", title="B", description="",
                      price_cad=9.0, state="published", etsy_listing_id=etsy_id,
                      created_at=NOW - timedelta(weeks=8)))


def _delivery(event="order.paid", *, wid="msg_1", shop="555", at=None, secret=SECRET,
              body=None):
    at = at or NOW
    body = body if body is not None else json.dumps(
        {"event_type": event, "shop_id": shop,
         "resource_url": "https://openapi.etsy.com/v3/application/shops/555/receipts/1"}
    ).encode()
    ts = str(int(at.timestamp()))
    return ({"webhook-id": wid, "webhook-timestamp": ts,
             "webhook-signature": wh.sign(secret, wid, ts, body)}, body)


# ---------------------------------------------------------------------------
# F-512 Webhook Reliability


def test_f512_validation_refuses_every_unprovable_delivery_before_writing():
    db = _db()
    h, body = _delivery()
    cases = [
        ("not_configured", dict(secret=""), h, body, 503),
        ("missing_headers", {}, {k: v for k, v in h.items() if k != "webhook-signature"},
         body, 400),
        ("bad_signature", {}, {**h, "webhook-signature": "v1," + base64.b64encode(
            b"x" * 32).decode()}, body, 401),
        ("bad_signature", {}, h, body + b" ", 401),          # body tampered after signing
        ("stale", {}, *_delivery(at=NOW - timedelta(seconds=301)), 401),
        ("unsupported_event", {}, *_delivery(event="listing.updated"), 422),
        ("foreign_shop", dict(shop_id="999"), h, body, 403),
    ]
    for reason, kw, headers, raw, status in cases:
        got_status, got = wh.receive(db, headers, raw, **{"secret": SECRET, "shop_id": None,
                                                          **kw})
        assert (got_status, got["reason"]) == (status, reason), (reason, got_status, got)
    wh.ensure_table(db)
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(wh.EtsyWebhookDelivery)) == 0
        assert s.scalar(select(func.count()).select_from(Job).where(
            Job.job_type == "commerce.orders_ingest")) == 0
    refused = wh.summary(db)["refused"]
    assert refused["bad_signature"] == 2 and refused["stale"] == 1, refused


def test_f512_multiple_signature_entries_accept_if_any_matches():
    db = _db()
    h, body = _delivery()
    h["webhook-signature"] = "v1,AAAA " + h["webhook-signature"]
    status, got = wh.receive(db, h, body, secret=SECRET, shop_id="555")
    assert status == 202 and got["accepted"] and not got["duplicate"], got


def test_f512_idempotent_storage_duplicate_protection_and_observability():
    db = _db()
    h, body = _delivery(wid="msg_42")
    s1, first = wh.receive(db, h, body, secret=SECRET, shop_id="555")
    s2, retry = wh.receive(db, h, body, secret=SECRET, shop_id="555")   # Etsy retry
    assert s1 == 202 and first["job_id"], first
    assert s2 == 200 and retry["duplicate"] is True and retry["job_id"] == first["job_id"]
    with db.session() as s:
        rows = list(s.scalars(select(wh.EtsyWebhookDelivery)))
        jobs = list(s.scalars(select(Job).where(Job.job_type == "commerce.orders_ingest")))
    assert len(rows) == 1 and rows[0].duplicates == 1 and rows[0].webhook_id == "msg_42"
    assert len(rows[0].body_sha256) == 64, "the digest is stored, never the body"
    assert len(jobs) == 1 and jobs[0].idempotency_key == "etsy.webhook:msg_42"
    assert jobs[0].max_attempts >= 2, "the woken ingest is retried like every job"
    summ = wh.summary(db)
    assert summ["received"] == 1 and summ["duplicates"] == 1
    assert summ["by_event"] == {"order.paid": 1} and summ["woken_jobs"], summ


def test_f512_a_storage_failure_answers_5xx_so_etsy_retries():
    db = _db()
    h, body = _delivery(wid="msg_fail")
    wh.ensure_table(db)

    class Boom:
        def enqueue(self, *a, **k):
            raise RuntimeError("database unavailable")

    status, got = wh.receive(db, h, body, secret=SECRET, shop_id="555", queue=Boom())
    assert status == 500 and got["reason"] == "enqueue_failed", got
    with db.session() as s:            # nothing stored, so Etsy's retry is not a duplicate
        assert s.scalar(select(func.count()).select_from(wh.EtsyWebhookDelivery)) == 0
    status, got = wh.receive(db, h, body, secret=SECRET, shop_id="555")
    assert status == 202 and got["duplicate"] is False, got


def test_f512_route_is_public_signed_and_reported_on_api_etsy():
    os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP}/route.sqlite"
    os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
    os.environ[wh.SECRET_ENV] = SECRET
    os.environ["ETSY_SHOP_ID"] = "555"
    try:
        from fastapi.testclient import TestClient

        from brambleloop.app import main, security

        assert ("POST", "/api/etsy/webhook") in security.PUBLIC_MUTATING_ROUTES
        main.db.create_all()
        Registry(main.db).seed_defaults()
        c = TestClient(main.app)
        h, body = _delivery(wid="msg_route")
        r = c.post("/api/etsy/webhook", content=body,
                   headers={**h, "content-type": "application/json"})
        assert r.status_code == 202, r.text
        bad = c.post("/api/etsy/webhook", content=body,
                     headers={**h, "webhook-signature": "v1,AAAA",
                              "content-type": "application/json"})
        assert bad.status_code == 401, bad.text
        e = c.get("/api/etsy").json()["webhooks"]
        assert e["configured"] is True and e["received"] >= 1, e
        assert SECRET not in json.dumps(e), "the secret is never reported"
    finally:
        os.environ.pop(wh.SECRET_ENV, None)
        os.environ.pop("ETSY_SHOP_ID", None)


# ---------------------------------------------------------------------------
# F-501 Etsy Event Feedback


def test_f501_verified_events_feed_the_idempotent_order_layer():
    db = _db()
    _listing(db)
    _open_gate(db)
    for wid in ("msg_a", "msg_b"):          # two events about the same receipt
        h, body = _delivery(wid=wid)
        assert wh.receive(db, h, body, secret=SECRET, shop_id="555")[0] == 202
    with db.session() as s:
        jobs = list(s.scalars(select(Job).where(Job.job_type == "commerce.orders_ingest")))
    assert len(jobs) == 2 and all(j.inputs["wake"] == "etsy.webhook" for j in jobs)
    feed = Feed([_receipt(1, 501, "222", 900)])
    for _job in jobs:                       # the worker runs each woken ingest
        orders_ingest.ingest(db, reader=feed)
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(Order)) == 1, \
            "two events, one receipt: one order (etsy:<receipt>:<transaction> is unique)"


# ---------------------------------------------------------------------------
# F-570 Offsite Ads Economics


def test_f570_unread_attribution_is_unmeasured_never_a_zero_share():
    db = _db()
    _listing(db)
    _open_gate(db)
    orders_ingest.ingest(db, reader=Feed([_receipt(1, 501, "222", 900),
                                          _receipt(2, 502, "222", 900)]))
    with db.session() as s:
        orders = list(s.scalars(select(Order)))
        assert all(o.offsite_ad_attributed is False for o in orders)  # the column's default
        share = paid_media.offsite_share(orders)
    assert share["status"] == "UNMEASURED" and share["share"] is None
    assert share["unknown"] == 2 and "not a non-attributed one" in share["why"]


def test_f570_ledger_read_measures_attribution_fee_and_recomputed_margin():
    db = _db()
    _listing(db)
    _open_gate(db)
    _verify_mapping(db)
    entries = [_entry(1, "transaction", "transaction", 10, -59),
               _entry(2, "processing_fee", "receipt", 1, -60),
               _entry(3, "offsite_ads_fee", "receipt", 1, -135),
               _entry(4, "transaction", "transaction", 20, -59),
               _entry(5, "processing_fee", "receipt", 2, -60)]
    orders_ingest.ingest(db, reader=LedgerFeed([_receipt(1, 501, "222", 900),
                                                _receipt(2, 502, "222", 900)], entries))
    with db.session() as s:
        orders = {o.external_ref: o for o in s.scalars(select(Order))}
        share = paid_media.offsite_share(list(orders.values()))
        a, b = orders["etsy:1:10"], orders["etsy:2:20"]
        assert paid_media.offsite_attribution(a) is True and a.offsite_ads_fee_cad == 1.35
        assert paid_media.offsite_attribution(b) is False and b.offsite_ads_fee_cad == 0.0
        assert abs(a.contribution_cad - (9.0 - 2.54)) < 1e-9, "margin recomputed with the fee"
    assert share == {**share, "status": "measured", "share": 0.5, "unknown": 0}
    f = paid_media.offsite_ads_forecast(orders=2, aov_usd=6.6, offsite_share=share["share"],
                                        trailing_365_sales_usd=13.2, contribution_rate=0.7)
    assert f["participation"] == "optional" and f["attribution_window_days"] == 30
    assert f["fee_rate_applied"] == 0.15


def test_f570_ads_plan_reports_unknown_attribution_and_the_threshold_status():
    from brambleloop.runtime import growth_ops

    db = _db()
    _listing(db)
    _open_gate(db)
    orders_ingest.ingest(db, reader=Feed([_receipt(1, 501, "222", 900)]))
    off = growth_ops.ads_plan(db)["offsite_ads"]
    assert off["status"] == "UNMEASURED", off
    assert off["attribution"] == {"orders": 1, "attributed": 0, "not_attributed": 0,
                                  "unknown": 1}
    assert off["participation"] == "optional" and "trailing_365_sales_usd" in off
    assert off["terms"]["attribution_window_days"] == 30


# ---------------------------------------------------------------------------
# F-574 Marketing Channel Attribution


def test_f574_channels_compared_per_listing_and_family_one_credit_per_order():
    db = _db()
    _listing(db)
    _listing(db, slug="harbour-cardigan", etsy_id="333")
    _open_gate(db)
    orders_ingest.ingest(db, reader=Feed([_receipt(i, 500 + i, "222" if i < 4 else "333", 900)
                                          for i in range(1, 7)]))
    ev = "owner: Etsy Stats export 2026-10-12"
    sources.attribute(db, "etsy:1:10", "etsy_search", evidence=ev)
    sources.attribute(db, "etsy:2:20", "etsy_ads", evidence=ev)
    sources.attribute(db, "etsy:3:30", "share_and_save", evidence=ev)
    sources.attribute(db, "etsy:4:40", "instagram", evidence=ev)
    sources.attribute(db, "etsy:5:50", "offsite_ads", evidence=ev)
    with db.session() as s:                 # Etsy's flag disagreeing with the source
        o = s.scalar(select(Order).where(Order.external_ref == "etsy:4:40"))
        o.offsite_ad_attributed = True
    got = channel_comparison.compare(db)
    assert got["channels"][:5] == ["organic_search", "etsy_ads", "offsite_ads", "social",
                                   "share_and_save"]
    blanket = got["by_listing"]["cloudline-baby-blanket"]
    cardigan = got["by_listing"]["harbour-cardigan"]
    assert [blanket[c]["orders"] for c in ("organic_search", "etsy_ads", "share_and_save")] \
        == [1, 1, 1]
    assert cardigan["social"]["orders"] == 1 and cardigan["offsite_ads"]["orders"] == 1
    assert cardigan["unattributed"]["orders"] == 1, "unknown stays unattributed"
    assert got["orders"] == 6 and got["credits"] == 6 and got["single_credit"] is True
    assert sum(r["orders"] for fam in got["by_family"].values() for r in fam.values()) == 6
    assert [c["order"] for c in got["conflicts"]] == ["etsy:4:40"]
    assert cardigan["offsite_ads"]["orders"] == 1, "the flagged order is not double-credited"
    # the four-channel table still sums to the same orders
    assert sources.table(db)["total_orders"] == 6


# ---------------------------------------------------------------------------
# F-590 Sales Channel Inventory


def test_f590_inventory_names_effects_and_an_unreadied_channel_is_an_incident():
    inv = sales_channels.inventory()
    for ch in inv["channels"].values():
        assert set(ch["effects"]) == {"listings", "inventory", "payments", "customer_data",
                                      "attribution"}
    assert inv["readied"] == ["etsy_com"]
    db = _db()
    _listing(db)
    _open_gate(db)
    got = orders_ingest.ingest(db, reader=Feed([_receipt(1, 501, "222", 900, receipt_type=0),
                                                _receipt(2, 502, "222", 900, receipt_type=1),
                                                _receipt(3, 503, "222", 900,
                                                         receipt_type=None)]))
    seen = got["sales_channels"]
    assert seen["by_channel"] == {"etsy_com": 1, "pattern": 1, "unknown": 1}, seen
    assert seen["unreadied_seen"] == ["pattern"]
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == f"{sales_channels.SIGNATURE}:pattern"))
        assert inc is not None and inc.severity == "P1" and not inc.resolved
    orders_ingest.ingest(db, reader=Feed([_receipt(2, 502, "222", 900, receipt_type=1)]))
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(Incident).where(
            Incident.signature.like(f"{sales_channels.SIGNATURE}%"))) == 1


# ---------------------------------------------------------------------------
# F-595 First-10-Sales Learning Protocol


def test_f595_each_of_the_first_ten_sales_gets_an_inspection_record():
    db = _db()
    _listing(db)
    _open_gate(db)
    got = orders_ingest.ingest(db, reader=Feed([_receipt(i, 500 + i, "222", 900,
                                                         days_ago=20 - i)
                                                for i in range(1, 4)]))
    assert got["first_ten"]["inspected"] == 3 and got["first_ten"]["open"] is True
    st = first_ten.state(db)
    rec = st["records"][0]
    for field in ("search_source", "conversion_path", "questions",
                  "download_support_friction", "review", "refund", "economics"):
        assert field in rec, field
    assert rec["sale_number"] == 1 and rec["external_ref"] == "etsy:1:10"
    assert rec["search_source"]["channel"] == "unattributed"
    assert rec["conversion_path"]["reading"] == "UNKNOWN", "unknown is never invented"
    assert rec["economics"]["fees_basis"] == "modelled"
    # a live listing's non-emergency edit is held; an emergency or a draft is not
    assert first_ten.edit_hold(db, "cloudline-baby-blanket", live=True)["held"] is True
    assert first_ten.edit_hold(db, "x", live=True, emergency=True)["held"] is False
    assert first_ten.edit_hold(db, "x", live=False)["held"] is False


def test_f595_a_later_refund_reaches_the_record_and_the_cohort_closes_at_ten():
    db = _db()
    _listing(db)
    _open_gate(db)
    receipts = [_receipt(i, 500 + i, "222", 900, days_ago=30 - i) for i in range(1, 12)]
    orders_ingest.ingest(db, reader=Feed(receipts))
    st = first_ten.state(db)
    assert st["inspected"] == 10 and st["open"] is False
    with db.session() as s:
        keys = sorted(r.period_key for r in s.scalars(select(OperatingReading).where(
            OperatingReading.kind == first_ten.KIND)))
    assert keys == [f"sale{n:02d}" for n in range(1, 11)]
    assert first_ten.edit_hold(db, "cloudline-baby-blanket", live=True)["held"] is False
    # sale 2 is partially refunded afterwards: its record is refreshed with history
    refunded = dict(receipts[1])
    refunded["refunds"] = [{"amount": {"amount": 300, "divisor": 100, "currency_code": "CAD"},
                            "transaction_id": 20, "reason": "file would not open"}]
    refunded["update_timestamp"] = int(NOW.timestamp())
    orders_ingest.ingest(db, reader=Feed([refunded]))
    rec = next(r for r in first_ten.state(db)["records"] if r["sale_number"] == 2)
    assert rec["refund"]["refund_cad"] == 3.0, rec["refund"]
    assert rec["history"] and "refund" in rec["history"][-1]["changed"]


# ---------------------------------------------------------------------------
# F-682 Accountant Activity


def test_f682_activity_shows_reconciliation_discrepancies_close_and_alerts_never_zeroed():
    from brambleloop.finance.accounting import activity, controller, dashboard, reconciliation

    db = _db()
    _listing(db)
    _open_gate(db)
    _verify_mapping(db)
    before = activity.activity(db)
    assert before["last_reconciliation"]["reading"] == "NEVER_RUN"
    booked = [_entry(1, "transaction", "transaction", 10, -59),
              _entry(2, "processing_fee", "receipt", 1, -60)]
    orders_ingest.ingest(db, reader=LedgerFeed([_receipt(1, 501, "222", 900)], booked))
    # The statement disagrees with what the books hold for this order's transaction fee.
    reconciliation.import_etsy_ledger(db, [_entry(1, "transaction", "transaction", 10, -159),
                                           _entry(2, "processing_fee", "receipt", 1, -60)])
    controller.run_cycle(db)
    first = activity.activity(db)
    assert first["last_reconciliation"]["at"] and first["last_reconciliation"]["matching"]
    mism = [x for x in first["discrepancies"]["accounting_exceptions"]
            if x["kind"] == "fee_mismatch"]
    assert len(mism) == 1, first["discrepancies"]
    ev = mism[0]["evidence"]
    assert ev["booked_cad"] != ev["statement_cad"] and ev["statement_cad"] > 0
    assert "locked_periods" in first["close"]
    names = {a["alert"]: a for a in first["tax_threshold_alerts"]}
    assert names["gst_hst_small_supplier"]["level"] == "clear"
    assert names["etsy_offsite_ads_365d"]["unit"] == "USD"
    controller.run_cycle(db)                       # a second cycle does not zero it
    again = activity.activity(db)
    still = [x for x in again["discrepancies"]["accounting_exceptions"]
             if x["kind"] == "fee_mismatch"]
    assert len(still) == 1 and still[0]["evidence"] == ev and not still[0]["resolved"]
    # served on the owner's Money view
    assert dashboard.summary(db)["activity"]["discrepancies"]["open"] >= 1


def test_f682_threshold_alert_approaches_and_crosses():
    from brambleloop.finance.accounting import activity

    a = activity._alert("x", 24500.0, 30000.0, "CAD", "w", "s")
    b = activity._alert("x", 30000.0, 30000.0, "CAD", "w", "s")
    c = activity._alert("x", None, 30000.0, "CAD", "w", "s")
    assert (a["level"], b["level"], c["level"]) == ("approaching", "crossed", "UNKNOWN")
    assert c["value"] is None, "unknown is never 0"


# ---------------------------------------------------------------------------
# F-657 Event Wakeups


def test_f657_each_business_event_wakes_its_team_once():
    from brambleloop.agents.registry import DEFAULT_AGENTS, FORBIDDEN_COMBINATIONS
    from brambleloop.autonomy import event_wakes
    from brambleloop.core.models import CultureSignal, OwnerAction, SupportCase
    from brambleloop.finance.accounting import exceptions as X

    held = {a["name"]: set(a["allowed_job_types"]) for a in DEFAULT_AGENTS}
    for kind, (agent, job_type) in event_wakes.ROUTES.items():
        assert job_type in held[agent], (kind, agent, job_type)
        assert job_type not in FORBIDDEN_COMBINATIONS.get(agent, set()), kind
    db = _db()
    _listing(db)
    _open_gate(db)
    assert {w["kind"] for w in event_wakes.scan(db)["woken"]} == set(), "nothing happened yet"
    orders_ingest.ingest(db, reader=Feed([_receipt(1, 501, "222", 900)]))
    with db.session() as s:
        s.add(SupportCase(customer_ref="etsy-user-501", question="the PDF will not open"))
        s.add(Incident(signature="policy_changed:etsy_fees", summary="fee policy changed"))
        s.add(Incident(signature="health:worker", summary="worker stale"))
        s.add(CultureSignal(key="sig-1", topic="cottagecore throws", domain="home"))
        s.add(OwnerAction(requirement_key="k1", action="approve", done=True, state="done"))
        o = s.scalar(select(Order))
        o.reviewed = True
        o.refunded = True
    X.open_exception(db, key="anomaly:spike:2026-10-12", kind="spend_spike",
                     summary="spike", severity="medium")
    h, body = _delivery(wid="msg_wake")
    wh.receive(db, h, body, secret=SECRET, shop_id="555")
    got = event_wakes.scan(db)
    woken = {w["kind"]: w for w in got["woken"]}
    assert set(woken) == {"order", "refund", "review", "message", "policy_change", "incident",
                          "spend_anomaly", "research_signal", "owner_decision"}, woken
    assert [k["kind"] for k in got["skipped"]] == ["etsy_event"], "receiver wakes directly"
    assert woken["order"]["job_type"] == "commerce.order_readings"
    assert woken["message"]["agent"] == "support"
    assert woken["policy_change"]["job_type"] == "ops.policy_watch"
    assert woken["spend_anomaly"]["job_type"] == "finance.governor"
    assert "Scheduler" in got["schedule"]
    with db.session() as s:
        jobs = {j.idempotency_key for j in s.scalars(select(Job))
                if (j.idempotency_key or "").startswith("wake:")}
    assert len(jobs) == len(woken)
    assert event_wakes.scan(db)["woken"] == [], "a re-scan with nothing new wakes nobody"
    orders_ingest.ingest(db, reader=Feed([_receipt(1, 501, "222", 900),
                                          _receipt(2, 502, "222", 900)]))
    assert [w["kind"] for w in event_wakes.scan(db)["woken"]] == ["order"]


def test_f657_the_orchestrate_tick_runs_the_event_scan():
    src = (ROOT / "src/brambleloop/autonomy/handlers.py").read_text()
    body = src.split("def handle_orchestrate", 1)[1].split("\ndef ", 1)[0]
    assert "event_wakes import scan" in body and "scan(ctx.db, ctx.queue" in body


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
