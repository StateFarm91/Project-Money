"""v1.1 lane E: the double-entry ledger and its posting rules (F-902, F-903).

Temp SQLite databases, synthetic rows, sockets refused.
Run: cd brambleloop && PYTHONPATH=src python3 tests/test_v11_accounting_ledger.py
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
_TMP = tempfile.mkdtemp(prefix="v11_acct_ledger_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")


def _no_network(*_a, **_k):
    raise OSError("network refused by the accounting harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select, text  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry, LedgerEntry, Order  # noqa: E402
from brambleloop.finance.accounting import (close, ledger, posting_rules,  # noqa: E402
                                            reconciliation, shadow_dataset, views)
from brambleloop.finance.accounting import exceptions as X  # noqa: E402
from brambleloop.finance.accounting.models import (AcctJournalEntry,  # noqa: E402
                                                   AcctPosting, ImmutableLedgerError)

NOW = datetime.now(timezone.utc)
_n = [0]


def _db():
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/l{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _pair(dr, cr, cad, basis="measured"):
    m = ledger.to_micros(cad)
    return [{"account": dr, "debit_micros": m, "credit_micros": 0, "basis": basis},
            {"account": cr, "debit_micros": 0, "credit_micros": m, "basis": basis}]


def _entry(key, at=None):
    return {"entry_key": key, "at": at or NOW, "rule": "test", "source_key": key,
            "source_table": "test", "source_id": "1"}


def test_unbalanced_and_off_chart_entries_are_refused():
    db = _db()
    bad = _pair("1100", "4000", 10.0)
    bad[1]["credit_micros"] -= 1
    refusals = 0
    for lines in (bad, _pair("1100", "9999", 1.0), _pair("1100", "4000", 1.0)[:1],
                  [{"account": "1100", "debit_micros": 5, "credit_micros": 5,
                    "basis": "measured"}, {"account": "4000", "debit_micros": 0,
                                           "credit_micros": 0, "basis": "measured"}],
                  _pair("1100", "4000", 1.0, basis="guess")):
        try:
            ledger.post(db, _entry(f"bad{refusals}"), lines)
        except ledger.LedgerRefused:
            refusals += 1
    assert refusals == 5
    with db.session() as s:
        assert s.scalar(select(AcctJournalEntry.id)) is None, "nothing written on refusal"


def test_entries_are_idempotent_by_key_and_balanced_to_the_micro():
    db = _db()
    a = ledger.post(db, _entry("k1"), _pair("5200", "2000", 0.000123))
    b = ledger.post(db, _entry("k1"), _pair("5200", "2000", 0.000123))
    assert a == b
    tb = views.trial_balance(db)
    assert tb["balanced"] and tb["chain_ok"] and tb["entries_in_journal"] == 1


def test_posted_records_are_immutable_through_the_orm():
    db = _db()
    eid = ledger.post(db, _entry("k1"), _pair("1100", "4000", 12.0))
    for mutate in ("entry_update", "posting_update", "entry_delete"):
        try:
            with db.session() as s:
                e = s.get(AcctJournalEntry, eid)
                if mutate == "entry_update":
                    e.memo = "edited"
                elif mutate == "posting_update":
                    s.scalar(select(AcctPosting).where(AcctPosting.entry_id == eid)
                             ).debit_micros = 1
                else:
                    s.delete(e)
        except ImmutableLedgerError:
            continue
        raise AssertionError(f"{mutate} was not refused")
    assert ledger.verify_chain(db)["ok"]


def test_raw_sql_tampering_is_detected_by_the_seal():
    db = _db()
    ledger.post(db, _entry("k1"), _pair("1100", "4000", 12.0))
    ledger.post(db, _entry("k2"), _pair("5100", "1100", 1.0))
    assert ledger.verify_chain(db)["ok"]
    with db.session() as s:
        s.execute(text("UPDATE acct_postings SET credit_micros = 13000000, "
                       "debit_micros = 0 WHERE line = 1 AND entry_id = 1"))
    v = ledger.verify_chain(db)
    assert not v["ok"] and v["problems"], v
    problems = " ".join(p["problem"] for p in v["problems"])
    assert "seal mismatch" in problems and "unbalanced" in problems


def test_a_correction_is_a_reversal_plus_a_new_version_never_an_edit():
    db = _db()
    with db.session() as s:
        s.add(LedgerEntry(category="sale", gross_cad=10.0, fees_cad=1.0, evidence_ref="t-1",
                          at=NOW))
    r1 = posting_rules.post_all(db)
    assert r1["posted"] == 1
    assert posting_rules.post_all(db)["posted"] == 0, "idempotent"
    with db.session() as s:
        s.scalar(select(LedgerEntry)).refunds_cad = 4.0  # a refund arrived on the source row
    r3 = posting_rules.post_all(db)
    assert r3["reversed"] == 1 and r3["posted"] == 1, r3
    with db.session() as s:
        rows = list(s.scalars(select(AcctJournalEntry).order_by(AcctJournalEntry.id)))
    assert [r.kind for r in rows] == ["original", "reversal", "original"]
    assert rows[1].reverses_id == rows[0].id and rows[2].entry_key.endswith(":v2")
    acc = views.accrual(db)
    assert acc["_micros"]["gross"] == 10_000_000 and acc["_micros"]["refunds"] == 4_000_000
    assert ledger.verify_chain(db)["ok"]


def test_duplicate_source_rows_are_refused_not_summed():
    db = _db()
    with db.session() as s:
        s.add(LedgerEntry(category="sale", gross_cad=10.0, evidence_ref="etsy:1:10", at=NOW))
        s.add(LedgerEntry(category="sale", gross_cad=10.0, evidence_ref="etsy:1:10", at=NOW))
        s.add(CostEntry(agent="a", kind="llm", amount_cad=2.0, provider="anthropic",
                        detail={"charge_id": "inv-1", "price_basis": "measured"}))
        s.add(CostEntry(agent="a", kind="llm", amount_cad=2.0, provider="anthropic",
                        detail={"charge_id": "inv-1", "price_basis": "measured"}))
    r = posting_rules.post_all(db)
    assert r["duplicates"] == 2 and r["posted"] == 2, r
    m = views.accrual(db)["_micros"]
    assert m["gross"] == 10_000_000 and m["operating"] == 2_000_000
    kinds = {x["kind"] for x in X.listing(db)}
    assert kinds == {"duplicate_source_row"}
    cmp = reconciliation.compare_with_books(db)
    assert not cmp["agree"], "books sum the duplicates; the ledger does not"
    assert cmp["metrics"]["gross_sales_cad"]["books_minus_ledger"] == 10.0
    assert {c["cause"] for c in cmp["explained_by"]} >= {"duplicate_source_row",
                                                         "duplicate_cost_charge"}
    assert "LEDGER is the source of truth" in cmp["verdict"]


def test_locked_period_never_moves_late_changes_book_in_the_next_open_period():
    db = _db()
    last_month = (NOW.replace(day=1) - timedelta(days=5))
    shadow_dataset.connect_order_source(db)
    with db.session() as s:
        from brambleloop.core.models import AuditLog
        s.add(AuditLog(actor="cfo", action="commerce.orders_ingested", detail={"ran": True}))
        s.add(LedgerEntry(category="sale", gross_cad=20.0, fees_cad=2.0, evidence_ref="t-9",
                          at=last_month, basis="measured", fees_basis="measured"))
    posting_rules.post_all(db)
    p = ledger.period_of(last_month)
    locked = close.lock_period(db, p, by="accountant")
    assert locked["locked"]
    before = views.trial_balance(db, period=p)
    with db.session() as s:
        s.scalar(select(LedgerEntry)).refunds_cad = 5.0
    r = posting_rules.post_all(db)
    assert r["reversed"] == 1 and r["posted"] == 1
    after = views.trial_balance(db, period=p)
    assert before["rows"] == after["rows"], "a locked period's figures never move"
    assert close.verify_lock(db, p)["intact"]
    with db.session() as s:
        late = list(s.scalars(select(AcctJournalEntry).where(
            AcctJournalEntry.source_period == p, AcctJournalEntry.period != p)))
    assert len(late) == 2 and all("LATE ADJUSTMENT" in e.memo for e in late)
    assert {e.period for e in late} == {ledger.next_period(p)}
    try:
        close.lock_period(db, p, by="accountant")
    except close.CloseRefused:
        pass
    else:
        raise AssertionError("a locked period cannot be locked again")


def test_held_and_unreconciled_orders_are_not_posted_but_raised():
    db = _db()
    shadow_dataset.seed(db, now=NOW)
    posting_rules.post_all(db)
    with db.session() as s:
        o = s.scalar(select(Order).order_by(Order.id))
        o.detail = {**(o.detail or {}), "state": "unreconciled"}
        ref = o.external_ref
    r = posting_rules.post_all(db)
    assert r["reversed"] == 1 and r["excluded"] >= 1, r
    assert any(x["key"] == f"unreconciled:{ref}" for x in X.listing(db))


def test_assumed_fx_is_posted_as_modelled_not_measured():
    db = _db()
    shadow_dataset.seed(db, now=NOW)
    posting_rules.post_all(db)
    with db.session() as s:
        usd = list(s.scalars(select(AcctPosting).where(AcctPosting.currency == "USD")))
    assert usd and all(p.basis == "modelled" for p in usd), [p.basis for p in usd]


def test_ledger_agrees_with_the_books_on_a_realistic_shadow_dataset():
    db = _db()
    shadow_dataset.seed(db, now=NOW)
    posting_rules.post_all(db)
    cmp = reconciliation.compare_with_books(db, until=NOW)
    assert cmp["agree"], cmp
    assert cmp["metrics"]["gross_sales_cad"]["ledger"] > 0
    assert cmp["books_sales_reading"] == cmp["ledger_sales_reading"] == "measured"
    tb = views.trial_balance(db)
    assert tb["balanced"] and tb["chain_ok"]


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
