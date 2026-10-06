"""v1.1 lane E: bank / Etsy / processor reconciliation (F-904) and anomalies (F-911).

Section 95: "Inject a duplicate fee/payment/refund: reconciliation detects the exception and
prevents silent double counting."
Run: cd brambleloop && PYTHONPATH=src python3 tests/test_v11_accounting_reconciliation.py
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="v11_acct_rec_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")


def _no_network(*_a, **_k):
    raise OSError("network refused by the accounting harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry, LedgerEntry, Order  # noqa: E402
from brambleloop.finance.accounting import (anomalies, ledger, posting_rules,  # noqa: E402
                                            reconciliation, shadow_dataset, views)
from brambleloop.finance.accounting import exceptions as X  # noqa: E402

NOW = datetime.now(timezone.utc)
_n = [0]


def _db(seed=True):
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/r{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    if seed:
        shadow_dataset.seed(db, now=NOW)
        posting_rules.post_all(db, now=NOW)
    return db


def _first_receipt(db):
    with db.session() as s:
        o = s.scalar(select(Order).order_by(Order.id))
        return str((o.detail or {}).get("receipt_id")), o.external_ref


def _totals(db):
    m = views.accrual(db)["_micros"]
    return (m["gross"], m["refunds"], m["fees"], m["operating"])


def test_a_replayed_statement_is_imported_once():
    db = _db()
    lines = [{"external_id": "bk-1", "at": NOW, "kind": "deposit", "amount": 20.0,
              "reference": "ETSY PAYOUT 1"}]
    a = reconciliation.import_statement(db, "bank", lines, now=NOW)
    b = reconciliation.import_statement(db, "bank", lines, now=NOW)
    assert a["imported"] == 1 and b["imported"] == 0 and b["replayed"] == 1


def test_injected_duplicate_fee_payment_and_refund_are_detected_and_not_double_counted():
    """Section 95."""
    db = _db()
    rid, ref = _first_receipt(db)
    t = NOW - timedelta(days=1)
    reconciliation.import_statement(db, "bank", [
        {"external_id": "bk-1", "at": t, "kind": "deposit", "amount": 30.0,
         "reference": "ETSY CANADA PAYOUT"}], now=NOW)
    reconciliation.import_statement(db, "etsy_ledger", [
        {"external_id": "et-1", "at": t, "kind": "payout", "amount": -30.0, "reference": "p1"},
        {"external_id": "et-2", "at": t, "kind": "fee", "amount": -0.78, "reference": rid},
        {"external_id": "et-3", "at": t, "kind": "refund", "amount": -1.00, "reference": rid},
    ], now=NOW)
    reconciliation.match(db, now=NOW)
    posting_rules.post_all(db, now=NOW)
    before = _totals(db)
    cash_before = views.trial_balance(db)["rows"]
    bank_before = [r for r in cash_before if r["account"] == "1000"][0]["debit_cad"]
    assert bank_before == 30.0
    # Inject: the same payment (bank deposit), fee and refund again, under new ids.
    reconciliation.import_statement(db, "bank", [
        {"external_id": "bk-1-dup", "at": t + timedelta(hours=5), "kind": "deposit",
         "amount": 30.0, "reference": "ETSY CANADA PAYOUT"}], now=NOW)
    out = reconciliation.import_statement(db, "etsy_ledger", [
        {"external_id": "et-2-dup", "at": t, "kind": "fee", "amount": -0.78, "reference": rid},
        {"external_id": "et-3-dup", "at": t, "kind": "refund", "amount": -1.00,
         "reference": rid},
    ], now=NOW)
    assert len(out["duplicates"]) == 2
    reconciliation.match(db, now=NOW)
    posting_rules.post_all(db, now=NOW)
    dups = [l for l in reconciliation.statement_lines(db) if l["state"] == "duplicate"]
    assert {l["external_id"] for l in dups} == {"bk-1-dup", "et-2-dup", "et-3-dup"}
    assert all(l["duplicate_of"] for l in dups)
    exc = [x for x in X.listing(db) if x["kind"] == "duplicate_statement_line"]
    assert len(exc) == 3 and all(x["severity"] == "high" for x in exc)
    assert _totals(db) == before, "no silent double counting in the accrual figures"
    bank_after = [r for r in views.trial_balance(db)["rows"] if r["account"] == "1000"][0]
    assert bank_after["debit_cad"] == 30.0, "the duplicate deposit is not cash twice"


def test_payout_matches_bank_deposit_and_unmatched_lines_become_exceptions():
    db = _db()
    t = NOW - timedelta(days=1)
    reconciliation.import_statement(db, "etsy_ledger", [
        {"external_id": "et-p1", "at": t, "kind": "payout", "amount": -25.5,
         "reference": "payout-1"}], now=NOW)
    reconciliation.import_statement(db, "bank", [
        {"external_id": "bk-1", "at": t + timedelta(days=2), "kind": "deposit",
         "amount": 25.5, "reference": "ETSY"},
        {"external_id": "bk-2", "at": t, "kind": "deposit", "amount": 99.0,
         "reference": "UNKNOWN WIRE"}], now=NOW)
    rep = reconciliation.match(db, now=NOW)
    states = {l["external_id"]: l["state"] for l in reconciliation.statement_lines(db)}
    assert states == {"et-p1": "matched", "bk-1": "matched", "bk-2": "unmatched"}, states
    assert rep["unmatched"] == 1
    assert any(x["kind"] == "unmatched_statement_line" for x in X.listing(db))
    posting_rules.post_all(db, now=NOW)
    bank = [r for r in views.trial_balance(db)["rows"] if r["account"] == "1000"][0]
    assert bank["debit_cad"] == 25.5, "an unmatched deposit is an exception, not a posting"


def test_charged_fee_that_disagrees_with_the_books_is_a_mismatch():
    db = _db()
    rid, ref = _first_receipt(db)
    with db.session() as s:
        o = s.scalar(select(Order).where(Order.external_ref == ref))
        o.fees_basis = "unverified"  # the books now hold an Etsy-read fee
        fees = o.fees_cad
    reconciliation.import_statement(db, "etsy_ledger", [
        {"external_id": "et-f", "at": NOW, "kind": "fee", "amount": -(fees + 3.0),
         "reference": rid}], now=NOW)
    rep = reconciliation.match(db, now=NOW)
    assert rep["mismatches"] == 1
    assert any(x["kind"] == "fee_mismatch" for x in X.listing(db))


def test_etsy_ledger_entries_import_through_the_shared_type_mapping():
    db = _db(seed=False)
    out = reconciliation.import_etsy_ledger(db, [
        {"entry_id": 1, "ledger_type": "transaction", "reference_type": "transaction",
         "reference_id": "10010", "amount": -78, "currency": "CAD",
         "created_timestamp": int(NOW.timestamp())},
        {"entry_id": 2, "ledger_type": "mystery_type", "reference_type": "receipt",
         "reference_id": "1", "amount": -10, "currency": "CAD",
         "created_timestamp": int(NOW.timestamp())}], now=NOW)
    assert out["imported"] == 1 and out["unclassified_skipped"] == 1
    line = reconciliation.statement_lines(db)[0]
    assert line["kind"] == "fee" and line["amount_cad"] == -0.78


def test_anomalies_fee_rate_refunds_deposits_duplicates_and_chain():
    db = _db()
    rid, ref = _first_receipt(db)
    with db.session() as s:
        o = s.scalar(select(Order).where(Order.external_ref == ref))
        o.fees_basis, o.fees_cad = "measured", round(o.price_cad * 0.9, 2)
        s.add(LedgerEntry(category="sale", gross_cad=5.0, refunds_cad=9.0,
                          evidence_ref="odd-refund", at=NOW))
        s.add(CostEntry(agent="a", kind="image", provider="openai", model="m", purpose="p",
                        amount_cad=0.9, at=NOW))
        s.add(CostEntry(agent="a", kind="image", provider="openai", model="m", purpose="p",
                        amount_cad=0.9, at=NOW + timedelta(seconds=20)))
    reconciliation.import_statement(db, "bank", [
        {"external_id": "bal", "at": NOW, "kind": "balance", "amount": 0.0,
         "reference": "x"}], now=NOW)
    reconciliation.import_statement(db, "etsy_ledger", [
        {"external_id": "old-payout", "at": NOW - timedelta(days=20), "kind": "payout",
         "amount": -12.0, "reference": "p-old"}], now=NOW)
    reconciliation.match(db, now=NOW)
    posting_rules.post_all(db, now=NOW)
    found = anomalies.detect(db, now=NOW)
    types = {f["type"] for f in found["findings"]}
    assert {"unexpected_fee_rate", "refund_anomaly", "duplicate_charge",
            "missing_deposit"} <= types, types
    assert all(f["evidence"] for f in found["findings"])
    assert found["opened"] >= 4
    # Tamper with the journal: drift is reported.
    from sqlalchemy import text
    with db.session() as s:
        s.execute(text("UPDATE acct_journal_entries SET memo='x' WHERE id=1"))
    types2 = {f["type"] for f in anomalies.detect(db, now=NOW)["findings"]}
    assert "reconciliation_drift" in types2


def test_resolving_an_exception_needs_an_explanation():
    db = _db(seed=False)
    X.open_exception(db, key="k", kind="test", summary="s")
    try:
        X.resolve(db, "k", resolution="ok", by="owner")
    except ValueError:
        pass
    else:
        raise AssertionError("a one-word resolution was accepted")
    assert X.resolve(db, "k", resolution="matched to bank line 7 manually", by="owner")["changed"]
    assert not X.listing(db)


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
