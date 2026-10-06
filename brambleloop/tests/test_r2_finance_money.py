"""R2-FIN regressions: cash, drill, FX labels, tax pack, duplicates, seal, books cash.

Audit of final-candidate-ddf9c6e (research/final_build/audit_ddf9c6e/REPORT_finance.md):
M1, M2, M3, M5, M7, M8, M9, M10, L2, L3, L5. Each fails on ddf9c6e and passes after.
Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_finance_money.py
"""
from __future__ import annotations

import math
import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="r2fin_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")


def _no_network(*_a, **_k):
    raise OSError("network refused by the R2-FIN harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select, text  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.finance.accounting import (close, controller, dashboard,  # noqa: E402
                                            ledger, reconciliation as R, shadow_dataset)
from brambleloop.finance.accounting import exceptions as X  # noqa: E402

NOW = datetime.now(timezone.utc)
_n = [0]


def _db(seed=True, at=None):
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    if seed:
        shadow_dataset.seed(db, now=at or NOW)
    return db


def _prev():
    y, m = NOW.year, NOW.month
    py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
    return py, pm, f"{py}-{pm:02d}"


def _items(s):
    return {i["metric"]: i for i in s["items"]}


def test_M1_stale_bank_cash_is_stale_and_buys_no_budget():
    """p02 A2: bank imported 9 days ago -> cash `stale`, safe budget / runway UNKNOWN."""
    db = _db()
    R.import_statement(db, "bank", [{"external_id": "b1", "at": NOW - timedelta(days=30),
                                     "kind": "owner_contribution", "amount": 500.0,
                                     "reference": "seed"}], now=NOW - timedelta(days=6))
    R.match(db, now=NOW)
    s = dashboard.summary(db, now=NOW + timedelta(days=3))
    it = _items(s)
    assert s["source_health"]["bank"]["state"] == "stale"
    assert it["cash"]["reading"] == "stale", it["cash"]
    assert it["cash"]["reading"] != "measured"
    assert it["safe_discretionary_budget"]["value_cad"] is None, it["safe_discretionary_budget"]
    assert it["safe_discretionary_budget"]["reading"] == "UNKNOWN"
    assert s["runway"]["value"] is None
    from brambleloop.app.command_center import tabs
    m = tabs._money_item(it["cash"])
    assert m["state"] != "MEASURED" and "0.00" not in m["display"], m


def test_M2_unmatched_bank_deposit_makes_cash_unknown_not_zero():
    """p02 B: deposit 900 matching no payout + balance snapshot 1234 -> cash UNKNOWN."""
    db = _db()
    R.import_statement(db, "bank", [
        {"external_id": "d1", "at": NOW - timedelta(days=2), "kind": "deposit",
         "amount": 900.0, "reference": "NOPAYOUT"},
        {"external_id": "bal", "at": NOW - timedelta(days=1), "kind": "balance",
         "amount": 1234.0, "reference": "snap"}], now=NOW)
    R.match(db, now=NOW)
    it = _items(dashboard.summary(db, now=NOW))
    assert it["cash"]["value_cad"] is None and it["cash"]["reading"] == "UNKNOWN", it["cash"]
    assert "unreconciled" in it["cash"]["why"].lower(), it["cash"]["why"]
    assert it["safe_discretionary_budget"]["value_cad"] is None
    d = dashboard.drill(db, "cash", now=NOW)
    assert d["value_cad"] is None and d["status"] == "UNKNOWN", (d["value_cad"], d["status"])


def test_M3_drill_expected_payout_matches_summary_unknown():
    """p01: disconnected order source -> summary UNKNOWN, so the drill is UNKNOWN too."""
    db = _db(seed=False)
    s = _items(dashboard.summary(db, now=NOW))
    assert s["expected_payout"]["value_cad"] is None
    d = dashboard.drill(db, "expected_payout", now=NOW)
    assert d["status"] == "UNKNOWN" and d["value_cad"] is None, (d["status"], d["value_cad"])


def test_L3_drill_check_compares_independent_figures():
    db = _db()
    controller.run_cycle(db, now=NOW)
    s = _items(dashboard.summary(db, now=NOW))
    metrics = ("gross_sales", "fees", "profit", "operating_spend", "expected_payout")
    assert metrics
    for m in metrics:
        d = dashboard.drill(db, m, now=NOW)
        assert "independent_value_cad" in d["check"], d["check"]
        assert d["check"]["matches"] is True, (m, d["check"])
        assert d["value_cad"] == s[m]["value_cad"], (m, d["value_cad"], s[m]["value_cad"])


def test_M5_fx_assumed_revenue_is_estimated_not_measured():
    """p09: a USD sale at the assumed rate is modelled; gross/net say so."""
    db = _db()
    controller.run_cycle(db, now=NOW)
    s = dashboard.summary(db, now=NOW)
    it = _items(s)
    g = it["gross_sales"]
    assert g["reading"] == "estimated", g
    assert g["estimated_cad"] and g["estimated_cad"] > 0, g
    assert abs(g["actual_cad"] + g["estimated_cad"] - g["value_cad"]) < 1e-6
    assert it["net_sales"]["reading"] == "estimated" and it["net_sales"]["estimated_cad"] > 0
    assert it["profit"]["reading"] == "estimated"


def test_M7_tax_pack_unknown_fees_are_none_not_zero():
    from brambleloop.finance.accounting import tax_pack

    db = _db(seed=False)
    p = tax_pack.pack(db, NOW.strftime("%Y-%m"), now=NOW)
    sc = p["summary_cad"]
    assert p["sales_reading"] == "UNKNOWN"
    assert sc["marketplace_fees"] is None and sc["listing_fees"] is None, sc


def test_M8_duplicate_sale_for_same_receipt_with_new_external_id_is_refused():
    """p04: a second `sale` row for the same receipt, different external_id."""
    from brambleloop.core.models import LedgerEntry

    db = _db()
    base = _items(dashboard.summary(db, now=NOW))
    with db.session() as s:
        r = s.scalars(select(LedgerEntry).where(LedgerEntry.category == "sale")
                      .order_by(LedgerEntry.id)).first()
        s.add(LedgerEntry(at=r.at + timedelta(hours=1), category="sale",
                          description=r.description, gross_cad=r.gross_cad,
                          fees_cad=r.fees_cad, refunds_cad=r.refunds_cad,
                          evidence_ref=r.evidence_ref, source=r.source,
                          external_id=r.external_id + ":dup", currency=r.currency,
                          basis=r.basis, fees_basis=r.fees_basis))
    sm = dashboard.summary(db, now=NOW)
    it = _items(sm)
    assert it["gross_sales"]["value_cad"] == base["gross_sales"]["value_cad"]
    assert it["fees"]["value_cad"] == base["fees"]["value_cad"]
    assert "duplicate_source_row" in {x["kind"] for x in X.listing(db)}


def test_M9_seal_covers_every_economic_field_and_tail_deletion():
    """p11: raw-SQL edits of any meaningful field (and a deleted tail) break the chain."""
    edits = {
        "product_slug": "update acct_journal_entries set product_slug='other' where id=(select "
                        "min(id) from acct_journal_entries where product_slug!='')",
        "department": "update acct_journal_entries set department='x' where id=1",
        "channel": "update acct_journal_entries set channel='x' where id=1",
        "detail": "update acct_journal_entries set detail='{}' where id=1",
        "source_period": "update acct_journal_entries set source_period='1999-01' where id=1",
        "posted_at": "update acct_journal_entries set posted_at='2000-01-01' where id=1",
        "reverses_id": "update acct_journal_entries set reverses_id=1 where id=2",
        "posting.memo": "update acct_postings set memo='hacked' where id=1",
        "posting.currency": "update acct_postings set currency='USD' where id=1",
        "posting.amount_original": "update acct_postings set amount_original=999 where id=1",
    }
    assert edits
    for name, sql in edits.items():
        db = _db()
        controller.run_cycle(db, now=NOW)
        assert ledger.verify_chain(db)["ok"] is True
        with db.session() as s:
            s.execute(text(sql))
        assert ledger.verify_chain(db)["ok"] is False, name
    db = _db()
    controller.run_cycle(db, now=NOW)
    with db.session() as s:
        last = s.execute(text("select max(id) from acct_journal_entries")).scalar()
        s.execute(text("delete from acct_postings where entry_id=:i"), {"i": last})
        s.execute(text("delete from acct_journal_entries where id=:i"), {"i": last})
    assert ledger.verify_chain(db)["ok"] is False, "tail deletion undetected"


def test_M9_legacy_v1_rows_still_verify_under_their_own_seal():
    """Migration honesty: a pre-v2 row (no seal marker, v1 digest) verifies as v1 and is
    counted; stripping the marker from a v2 row does not downgrade it."""
    import json as _json

    db = _db()
    controller.run_cycle(db, now=NOW)
    assert ledger.verify_chain(db)["legacy_v1_entries"] == 0
    from brambleloop.finance.accounting.models import AcctJournalEntry
    # Strip the marker from entry 1 only: its stored digest is v2, so this is tamper.
    with db.session() as s:
        d = dict(s.get(AcctJournalEntry, 1).detail)
        d.pop("seal")
        s.execute(text("update acct_journal_entries set detail=:d where id=1"),
                  {"d": _json.dumps(d)})
    assert ledger.verify_chain(db, anchors=False)["ok"] is False
    # Rebuild a genuine legacy chain: re-seal every row under v1 (as ddf9c6e wrote them).
    db2 = _db()
    controller.run_cycle(db2, now=NOW)
    with db2.session() as s:
        prev = ledger.GENESIS
        for e in s.scalars(select(AcctJournalEntry).order_by(AcctJournalEntry.id)):
            d = dict(e.detail)
            d.pop("seal", None)
            lines = [{"account": p.account, "debit_micros": p.debit_micros,
                      "credit_micros": p.credit_micros, "basis": p.basis}
                     for p in ledger.lines_of(s, e.id)]
            rec = {"entry_key": e.entry_key, "at": ledger._iso(e.at), "period": e.period,
                   "rule": e.rule, "source_key": e.source_key, "source_table": e.source_table,
                   "source_id": e.source_id, "source_ref": e.source_ref,
                   "fingerprint": e.fingerprint, "kind": e.kind,
                   "reverses_key": d.get("reverses_key", ""), "memo": e.memo}
            h = ledger._canon(rec, lines, prev)
            s.execute(text("update acct_journal_entries set detail=:d, prev_hash=:p, hash=:h "
                           "where id=:i"), {"d": _json.dumps(d), "p": prev, "h": h, "i": e.id})
            prev = h
        s.execute(text("delete from operating_readings where kind=:k"),
                  {"k": ledger.ANCHOR_KIND})
    v = ledger.verify_chain(db2)
    assert v["ok"] is True and v["legacy_v1_entries"] == v["entries"] > 0, v


def test_M10_books_cash_is_never_net_profit():
    from brambleloop.finance.books import ProfitAndLoss

    pl = ProfitAndLoss(period_start="2026-09-01", period_end="2026-09-30",
                       gross_sales_cad=100.0, platform_fees_cad=10.0,
                       fees_by_basis={"measured": 10.0}, cost_by_kind={"llm": 5.0},
                       operating_costs_by_basis={"measured": 5.0})
    d = pl.to_dict()
    assert d["net_profit_cad"] is not None
    assert d["cash_cad"] is None and d["cash_reading"] == "UNKNOWN", (d["cash_cad"],
                                                                     d["cash_reading"])


def test_L2_negative_or_nonfinite_cost_rows_are_refused():
    from brambleloop.finance import spend_report
    from brambleloop.gateway import anthropic as gw

    db = _db(seed=False)
    spend_report.record(db, agent="a", amount_cad=90.0, purpose="real spend",
                        provider="anthropic", model="m")
    bad = (-80.0, float("nan"), float("inf"))
    assert bad
    for amt in bad:
        try:
            spend_report.record(db, agent="a", amount_cad=amt, purpose="bad row",
                                provider="anthropic", model="m")
            raise AssertionError(f"accepted {amt}")
        except ValueError:
            pass
    assert abs(gw.spent_this_month_cad(db, now=NOW) - 90.0) < 1e-9


def test_L5_sustainability_says_when_no_measured_order_backs_it():
    from brambleloop.finance import sustainability as S

    db = _db(seed=False)
    v = S.verdict(db, now=NOW)
    if v.get("status") == "computed":
        assert v["evidenced_by_measured_orders"] is (v["measured_orders"] > 0)
    else:
        assert v["sustainable"] is False
    import inspect
    assert "evidenced_by_measured_orders" in inspect.getsource(S.verdict)


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
            print("FAIL", t.__name__, repr(exc)[:300])
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
