"""rc1-ORD2: the follow-ups left open by the orders-truth repair, made permanent.

1. The Etsy ledger mapping verification is owner authority: sealed under the owner credential,
   hash-chained (core.sealed_chain), recorded only through an owner route. A forged, inserted,
   replayed or edited row is refused; a broken chain reverts every fee it made `measured` to
   `unverified` and opens a P1 tamper incident. Changing the type list or the divisor voids it.
2. Ledger listing fees follow the same rule (`unverified_mapping` until verified).
3. One shared predicate decides what a countable order is: a voided, unreconciled or held order
   moves none of cohorts, the channel table, order readings or the dashboard counts.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_rc1_ord2.py
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

_TMP = tempfile.mkdtemp(prefix="rc1_ord2_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.update(BRAMBLELOOP_PHASE="shadow", BRAMBLELOOP_REQUIRE_POSTGRES="0")
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC", "OPENAI", "ETSY", "GEMINI", "GOOGLE_API", "DATABASE_URL",
                      "BRAMBLELOOP_DATABASE")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the rc1-ORD2 harness")


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



from brambleloop.core import sealed_chain  # noqa: E402
from brambleloop.ops import retention  # noqa: E402

TOKEN = "local-owner-ord2-test-token-32characters"
os.environ["BRAMBLELOOP_OPS_TOKEN"] = TOKEN
COMPLETE = [entry(1, "transaction", "transaction", 10, -78),
            entry(2, "processing_fee", "receipt", 1, -66)]


def pl(db):
    return Books(db).profit_and_loss(since=NOW - timedelta(days=30),
                                     until=NOW + timedelta(days=1))


def the_order(db, ref="etsy:1:10"):
    with db.session() as s:
        o = s.scalar(select(Order).where(Order.external_ref == ref))
        led = s.scalar(select(LedgerEntry).where(LedgerEntry.evidence_ref == ref))
        return o.fees_basis, (led.fees_basis if led else None), dict(o.detail or {})


def tamper_incident(db):
    with db.session() as s:
        return s.scalar(select(Incident).where(
            Incident.signature == reconcile.MAPPING_TAMPER_SIGNATURE,
            Incident.resolved == False))  # noqa: E712


def verify(db):
    return reconcile.record_mapping_verification(db, authorization=TOKEN, by="owner",
                                                 evidence="synthetic live-read fixture")


def measured_order(db):
    ingest(db, [receipt()], COMPLETE)
    assert the_order(db)[:2] == (reconcile.UNVERIFIED, reconcile.UNVERIFIED)
    verify(db)
    fb, lb, d = the_order(db)
    assert (fb, lb) == ("measured", "measured"), (fb, lb)
    return d


# ---------------------------------------------------------------------------
# 1. sealed, chained, owner-credential mapping verification


def test_1_recording_needs_the_owner_credential():
    db = _db()
    from brambleloop.core import opsauth

    for bad in ("", "Bearer wrong-token-wrong-token-wrong-token"):
        try:
            reconcile.record_mapping_verification(db, authorization=bad, by="owner",
                                                  evidence="x")
        except opsauth.OpsAuthRefused:
            pass
        else:
            raise AssertionError("verification recorded without the owner credential")
    assert reconcile.mapping_verified(db) is False


def test_1_a_forged_unsealed_owner_row_is_refused():
    """The rc1-ORD row shape (actor "owner", plain detail) no longer verifies anything."""
    db = _db()
    ingest(db, [receipt()], COMPLETE)
    with db.session() as s:
        s.add(AuditLog(actor="owner", action=reconcile.MAPPING_VERIFIED_ACTION,
                       detail={"fingerprint": reconcile.mapping_fingerprint(), "by": "owner",
                               "evidence": "forged"}))
        s.add(AuditLog(actor=reconcile.MAPPING_PRINCIPAL,
                       action=reconcile.MAPPING_VERIFIED_ACTION,
                       detail={"fingerprint": reconcile.mapping_fingerprint(), "seq": 1,
                               "prev_id": None, "prev_seal": "", "seal": "0" * 64}))
    st = reconcile.mapping_state(db)
    assert st["verified"] is False and st["chain_valid"] is False, st
    assert pl(db).to_dict()["platform_fees_basis"] == "unverified"
    assert the_order(db)[0] == reconcile.UNVERIFIED
    inc = tamper_incident(db)
    assert inc is not None and inc.severity == "P1"


def test_1_a_valid_sealed_verification_flips_fees_to_measured():
    db = _db()
    d = measured_order(db)
    assert d["fees_mapping"] == "owner_verified"
    assert d["money"]["fees"]["basis"] == "measured"
    assert "MEASURED" in d["money"]["contribution_basis"]
    st = reconcile.mapping_state(db)
    assert st["verified"] and st["chain_valid"], st
    p = pl(db).to_dict()
    assert p["platform_fees_basis"] == "measured", p["platform_fees_by_basis"]
    assert tamper_incident(db) is None


def test_1_an_inserted_replayed_row_breaks_the_chain_and_reverts_the_fees():
    db = _db()
    measured_order(db)
    with db.session() as s:
        good = s.scalar(select(AuditLog).where(
            AuditLog.action == reconcile.MAPPING_VERIFIED_ACTION))
        # A database writer copies the validly sealed row to the end of the table.
        s.add(AuditLog(actor=good.actor, action=good.action, artifact=good.artifact,
                       detail=dict(good.detail)))
    assert reconcile.mapping_verified(db) is False
    p = pl(db).to_dict()
    assert p["platform_fees_basis"] == "unverified" and p["all_figures_observed"] is False
    fb, lb, d = the_order(db)
    assert (fb, lb) == (reconcile.UNVERIFIED, reconcile.UNVERIFIED)
    assert d["fees_mapping"] == reconcile.UNVERIFIED_MAPPING
    assert d["money"]["fees"]["basis"] == reconcile.UNVERIFIED_MAPPING
    assert tamper_incident(db).severity == "P1"
    # A new verification is refused over a broken chain; the owner rebases first.
    try:
        verify(db)
    except ValueError:
        pass
    else:
        raise AssertionError("a verification was appended over a broken chain")
    reconcile.rebase_mapping_chain(db, authorization=TOKEN, reason="replayed row found")
    assert reconcile.mapping_verified(db) is False, "a rebase voids earlier verifications"
    verify(db)
    assert reconcile.mapping_verified(db) is True
    assert the_order(db)[:2] == ("measured", "measured")
    assert tamper_incident(db) is None


def test_1_an_edited_row_is_refused():
    db = _db()
    measured_order(db)
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(
            AuditLog.action == reconcile.MAPPING_VERIFIED_ACTION))
        row.detail = {**row.detail, "evidence": "edited after sealing"}
    assert reconcile.mapping_verified(db) is False
    pl(db)
    assert the_order(db)[:2] == (reconcile.UNVERIFIED, reconcile.UNVERIFIED)
    assert tamper_incident(db) is not None


def test_1_a_deleted_revocation_does_not_revive_the_verification():
    db = _db()
    measured_order(db)
    vid = reconcile.mapping_state(db)["verification_id"]
    reconcile.revoke_mapping_verification(db, authorization=TOKEN, verification_id=vid)
    assert reconcile.mapping_verified(db) is False
    assert the_order(db)[0] == reconcile.UNVERIFIED
    # Deleting the newest row is tail truncation, a residual sealed_chain states; here the
    # revocation is deleted from the middle of the chain (a later row follows it).
    db = _db()
    measured_order(db)
    vid = reconcile.mapping_state(db)["verification_id"]
    reconcile.revoke_mapping_verification(db, authorization=TOKEN, verification_id=vid)
    reconcile.rebase_mapping_chain(db, authorization=TOKEN, reason="re-anchor")
    with db.session() as s:
        s.delete(s.scalar(select(AuditLog).where(
            AuditLog.action == reconcile.MAPPING_REVOKED_ACTION)))
    assert reconcile.mapping_state(db)["chain_valid"] is False
    assert reconcile.mapping_verified(db) is False


def test_1_changing_the_type_list_or_divisor_voids_the_verification():
    db = _db()
    measured_order(db)
    with patch.object(reconcile, "LEDGER_AMOUNT_DIVISOR", 1):
        assert reconcile.mapping_verified(db) is False
        pl(db)
        assert the_order(db)[:2] == (reconcile.UNVERIFIED, reconcile.UNVERIFIED)
    assert reconcile.mapping_verified(db) is True
    pl(db)
    assert the_order(db)[:2] == ("measured", "measured")
    with patch.dict(reconcile._FEE_EXACT, {"vat_on_fees": "regulatory_fee"}):
        assert reconcile.mapping_verified(db) is False
        assert pl(db).to_dict()["platform_fees_basis"] == "unverified"
    # A changed mapping is not tampering: no incident.
    assert tamper_incident(db) is None


def test_1_the_route_is_owner_only_and_records_a_sealed_row():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from brambleloop.app import security
    from brambleloop.app.ledger_mapping_api import make_router

    db = _db()
    app = FastAPI()
    app.include_router(make_router(db))
    c = TestClient(app)
    body = {"by": "owner", "evidence": "live read 2026-10-06"}
    assert c.post("/api/owner/ledger-mapping/verify", json=body).status_code == 403
    assert c.post("/api/owner/ledger-mapping/verify", json=body,
                  headers={"Authorization": "Bearer nope"}).status_code == 403
    assert c.get("/api/owner/ledger-mapping").status_code == 403
    r = c.post("/api/owner/ledger-mapping/verify", json=body,
               headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200, r.text
    assert reconcile.mapping_verified(db) is True
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(
            AuditLog.action == reconcile.MAPPING_VERIFIED_ACTION))
        assert row.actor == reconcile.MAPPING_PRINCIPAL and row.detail["seal"]
    st = c.get("/api/owner/ledger-mapping", headers={"Authorization": f"Bearer {TOKEN}"})
    assert st.json()["verified"] is True
    # Default deny on the real app: the gate covers every mutating route under the prefix.
    assert security.requires_operator("POST", "/api/owner/ledger-mapping/verify")
    assert security.requires_operator("GET", "/api/owner/ledger-mapping")
    assert security.refusal_status("/api/owner/ledger-mapping/rebase") == 403


def test_1_the_chain_rows_are_protected_from_retention():
    for action in reconcile.MAPPING_ACTIONS:
        assert action in retention.PROTECTED_ACTIONS, action


# ---------------------------------------------------------------------------
# 2. ledger listing fees


def _listing_fee(eid="lf-1"):
    return {"kind": "listing_fee", "reference_type": "listing", "reference_id": "555",
            "entry_id": eid, "at": NOW.isoformat(), "charge": 0.27, "currency": "CAD",
            "ledger_type": "listing"}


def _listing_bases(db):
    from brambleloop.core.models import CostEntry

    with db.session() as s:
        led = [r.basis for r in s.scalars(select(LedgerEntry).where(
            LedgerEntry.source == reconcile.LISTING_LEDGER_SOURCE))]
        mirror = [(c.detail or {}).get("basis") for c in s.scalars(select(CostEntry).where(
            CostEntry.kind == "etsy_listing_fee_actual"))]
    return led, mirror


def test_2_a_listing_fee_is_unverified_until_the_mapping_is_verified():
    from brambleloop.finance import listing_costs

    db = _db()
    listing_costs.ingest_actual(db, [_listing_fee()])
    assert _listing_bases(db) == ([reconcile.UNVERIFIED], [reconcile.UNVERIFIED_MAPPING])
    p = pl(db)
    assert "measured" not in {k for k, v in p.operating_costs_by_basis.items() if v}
    assert p.unobserved_operating_rows >= 1
    verify(db)
    assert _listing_bases(db) == (["measured"], ["measured"])
    listing_costs.ingest_actual(db, [_listing_fee("lf-2")])
    assert _listing_bases(db) == (["measured", "measured"], ["measured", "measured"])
    vid = reconcile.mapping_state(db)["verification_id"]
    reconcile.revoke_mapping_verification(db, authorization=TOKEN, verification_id=vid)
    assert _listing_bases(db) == ([reconcile.UNVERIFIED] * 2, [reconcile.UNVERIFIED_MAPPING] * 2)


def test_2_reconcile_apply_passes_listing_fees_through_the_same_rule():
    db = _db()
    ingest(db, [receipt()], COMPLETE + [entry(5, "listing", "listing", 555, -27)])
    assert _listing_bases(db) == ([reconcile.UNVERIFIED], [reconcile.UNVERIFIED_MAPPING])


# ---------------------------------------------------------------------------
# 3. one countable-order predicate


def _readings(db):
    from brambleloop.app import dashboard_truth
    from brambleloop.commerce import cohorts, order_readings

    st = cohorts.state(db)
    members = cohorts.members(db, "validation", "first_hundred")
    table = sources.table(db)
    rows = order_readings.orders(db)
    ev = dashboard_truth.commercial_evidence(db)
    rev = dashboard_truth.revenue_reading(db)
    p = pl(db)
    return {
        "cohort_orders": st["orders"],
        "member_orders": sum(m["orders"] for m in members),
        "member_revenue": round(sum(m["revenue_cad"] for m in members), 2),
        "table_orders": table["total_orders"],
        "table_revenue": round(sum(c["revenue_cad"] for c in table["channels"].values()), 2),
        "reading_rows_unrefunded": sum(1 for r in rows if not r["refunded"]),
        "reading_revenue": round(sum(r["revenue_cad"] for r in rows), 2),
        "dashboard_orders": ev["orders"],
        "dashboard_evidenced": ev["evidenced_sales"],
        "dashboard_revenue": rev.get("value_cad"),
        "books_orders": p.orders, "books_customers": p.customers,
    }


def test_3_unreconciled_and_voided_orders_move_no_reader():
    db = _db()
    ingest(db, [receipt(1, buyer=101), receipt(2, buyer=102)])
    both = _readings(db)
    assert both["cohort_orders"] == both["table_orders"] == both["books_orders"] == 2, both
    assert both["dashboard_orders"] == both["reading_rows_unrefunded"] == 2, both
    assert both["member_orders"] == 2 and both["member_revenue"] == 24.0, both
    assert both["table_revenue"] == both["reading_revenue"] == 24.0, both

    # Only receipt 2 now: what a world with order 1 never recorded reads like.
    ref = _db()
    ingest(ref, [receipt(2, buyer=102)])
    one = _readings(ref)

    # Order 1 becomes UNRECONCILED (refund amount unknown): it must read as absent.
    ingest(db, [receipt(1, buyer=101, status="partially refunded", updated=60)],
           at=NOW + timedelta(minutes=1))
    with db.session() as s:
        o = s.scalar(select(Order).where(Order.external_ref == "etsy:1:10"))
        assert o.detail["state"] == oi.UNRECONCILED and o.revenue_cad == 12.0, \
            "the row keeps its last revenue; every reader must ignore it"
        assert oi.standing(o, oi.held_refs(s)) == oi.STANDING_HELD
    got = _readings(db)
    for k in ("cohort_orders", "member_orders", "member_revenue", "table_orders",
              "table_revenue", "reading_rows_unrefunded", "reading_revenue",
              "dashboard_orders", "books_orders", "books_customers"):
        assert got[k] == one[k], (k, got[k], one[k])

    # Order 2 is then voided (cancelled): it is no order anywhere either.
    ingest(db, [receipt(2, buyer=102, status="canceled", updated=120)],
           at=NOW + timedelta(minutes=2))
    got = _readings(db)
    for k in ("cohort_orders", "member_orders", "table_orders", "reading_rows_unrefunded",
              "dashboard_orders", "dashboard_evidenced", "books_orders", "books_customers"):
        assert got[k] == 0, (k, got)
    for k in ("member_revenue", "table_revenue", "reading_revenue"):
        assert got[k] == 0.0, (k, got)


def test_3_the_predicate_is_defined_once():
    from types import SimpleNamespace as N

    held = frozenset({"etsy:9:90"})
    mk = lambda ref="etsy:1:10", refunded=False, **d: N(external_ref=ref,  # noqa: E731
                                                          refunded=refunded, detail=d)
    assert oi.countable(mk(state="paid"))
    assert oi.countable(mk(state="partially_refunded"))
    assert oi.countable(mk())  # a row written before states existed
    assert oi.standing(mk(state="fully_refunded")) == oi.STANDING_VOIDED
    assert oi.standing(mk(state="cancelled")) == oi.STANDING_VOIDED
    assert oi.standing(mk(refunded=True)) == oi.STANDING_VOIDED
    assert oi.standing(mk(state="unreconciled")) == oi.STANDING_UNRECONCILED
    assert oi.standing(mk(state="paid", revenue_unknown=True)) == oi.STANDING_UNRECONCILED
    assert oi.standing(mk("etsy:9:90", state="paid"), held) == oi.STANDING_HELD
    assert oi.in_books(mk(state="cancelled")) and not oi.in_books(mk(state="unreconciled"))
    # Every order reader in scope routes through it.
    root = Path(__file__).resolve().parents[1] / "src" / "brambleloop"
    for rel in ("finance/books.py", "finance/sources.py", "finance/sustainability.py",
                "commerce/cohorts.py", "commerce/order_readings.py", "commerce/bundles.py",
                "growth/mix.py", "growth/weekly.py", "growth/experiments.py",
                "app/dashboard_truth.py"):
        text = (root / rel).read_text()
        assert ("countable" in text or "booked_orders" in text or "standing" in text), rel
        assert "Order.refunded.is_(False)" not in text, rel


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
