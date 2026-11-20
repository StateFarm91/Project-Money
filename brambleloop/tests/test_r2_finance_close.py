"""R2-FIN regressions: month-end close, integrity on read, late adjustments, forecast.

Audit of final-candidate-ddf9c6e (research/final_build/audit_ddf9c6e/REPORT_finance.md):
H1, M4 (close), M12, L6, L7. Each test fails on ddf9c6e and passes after the fix.
Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_finance_close.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
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


def test_H1_close_refuses_with_unmatched_statement_lines_never_matched():
    """p19: statement lines for the closing month that match nothing, match() never run."""
    db = _db()
    controller.run_cycle(db, now=NOW)
    py, pm, prev = _prev()
    R.import_statement(db, "etsy_ledger", [
        {"external_id": "z1", "at": datetime(py, pm, 15, tzinfo=timezone.utc), "kind": "fee",
         "amount": -40.0, "reference": "9999999"},
        {"external_id": "z2", "at": datetime(py, pm, 16, tzinfo=timezone.utc),
         "kind": "refund", "amount": -55.0, "reference": "8888888"}], now=NOW)
    cl = close.checklist(db, prev, now=NOW)
    assert cl["closable"] is False, cl["owner_summary"]
    # Even without the refresh the raw statement-line state blocks.
    cl2 = close.checklist(db, prev, now=NOW, refresh=False)
    assert any(s["step"] == "statement_lines" and s["outcome"] == "block"
               for s in cl2["steps"]), cl2["steps"]
    try:
        close.lock_period(db, prev, by="r2", now=NOW)
        raise AssertionError("locked a month with unmatched statement lines")
    except close.CloseRefused:
        pass
    assert close.verify_lock(db, prev) == {"period": prev, "locked": False}
    kinds = {x["kind"] for x in X.listing(db, period=prev)}
    assert "unmatched_statement_line" in kinds, kinds


def test_H1_close_runs_anomaly_detection_itself():
    """A refund larger than its sale is an anomaly only detect() opens; lock must see it."""
    from brambleloop.core.models import LedgerEntry

    db = _db()
    controller.run_cycle(db, now=NOW)
    py, pm, prev = _prev()
    with db.session() as s:
        e = s.scalars(select(LedgerEntry).where(
            LedgerEntry.category == "sale",
            LedgerEntry.at < datetime(NOW.year, NOW.month, 1, tzinfo=timezone.utc))
            .order_by(LedgerEntry.id)).first()
        assert e is not None
        s.add(LedgerEntry(at=e.at, category="sale", description="hand entry",
                          gross_cad=1.0, refunds_cad=50.0, evidence_ref="r2-hand-1",
                          source="manual", external_id="r2-adj-1", basis="measured",
                          fees_basis="measured"))
    from brambleloop.finance.accounting import posting_rules
    posting_rules.post_all(db, now=NOW)
    try:
        close.lock_period(db, prev, by="r2", now=NOW)
        locked = True
    except close.CloseRefused:
        locked = False
    opened = [x for x in X.listing(db) if x["kind"].startswith("anomaly:")]
    assert not locked or not opened, "locked while an anomaly was undetected"
    assert not locked, "a month whose anomalies were never scanned was locked"


def test_H1_lock_is_written_only_after_a_fresh_scan_and_stays_irreversible():
    db = _db()
    controller.run_cycle(db, now=NOW)
    _, _, prev = _prev()
    r = close.lock_period(db, prev, by="r2", now=NOW)
    assert r["locked"] is True
    with db.session() as s:
        from brambleloop.finance.accounting.models import AcctPeriodLock
        row = s.scalar(select(AcctPeriodLock).where(AcctPeriodLock.period == prev))
        steps = {x["step"]: x["outcome"] for x in row.checklist["steps"]}
    assert steps.get("refresh") == "pass" and steps.get("statement_lines") == "pass", steps
    try:
        close.lock_period(db, prev, by="r2", now=NOW)
        raise AssertionError("second lock accepted")
    except close.CloseRefused:
        pass
    assert not hasattr(close, "unlock_period")


def test_M4_close_blocks_on_stale_orders():
    """p03: orders read 3 days before the close -> source_completeness must block."""
    db = _db()
    controller.run_cycle(db, now=NOW)
    _, _, prev = _prev()
    later = NOW + timedelta(days=3)
    cl = close.checklist(db, prev, now=later)
    sc = next(s for s in cl["steps"] if s["step"] == "source_completeness")
    assert sc["outcome"] == "block", sc
    try:
        close.lock_period(db, prev, by="r2", now=later)
        raise AssertionError("locked on stale orders")
    except close.CloseRefused:
        pass


def test_M12_summary_blocks_immediately_on_locked_month_tamper():
    """p03: balanced raw-SQL edit in a locked month -> summary BLOCKED on the next read."""
    db = _db()
    controller.run_cycle(db, now=NOW)
    _, _, prev = _prev()
    close.lock_period(db, prev, by="r2", now=NOW)
    with db.session() as s:
        pid = s.execute(text(
            "select p.id from acct_postings p join acct_journal_entries e on e.id=p.entry_id "
            "where e.period=:p and p.account='4000' limit 1"), {"p": prev}).scalar()
        assert pid is not None
        s.execute(text("update acct_postings set credit_micros = credit_micros + 5000000 "
                       "where id=:i"), {"i": pid})
        s.execute(text(
            "update acct_postings set debit_micros = debit_micros + 5000000 where id=(select "
            "id from acct_postings where entry_id=(select entry_id from acct_postings where "
            "id=:i) and debit_micros>0 limit 1)"), {"i": pid})
    assert ledger.verify_chain(db)["ok"] is False
    sm = dashboard.summary(db, now=NOW)
    assert sm["status"] == "BLOCKED", (sm["status"], sm["reason"][:300])
    assert "INTEGRITY" in sm["reason"], sm["reason"][:300]
    assert sm["integrity"]["ok"] is False


def test_L6_late_adjustment_to_locked_month_is_never_silent():
    """p20: a locked month's source row edited in place -> a late_adjustment exception."""
    from brambleloop.core.models import LedgerEntry

    db = _db()
    controller.run_cycle(db, now=NOW)
    _, _, prev = _prev()
    close.lock_period(db, prev, by="r2", now=NOW)
    with db.session() as s:
        e = s.scalars(select(LedgerEntry).where(
            LedgerEntry.category == "sale",
            LedgerEntry.at < datetime(NOW.year, NOW.month, 1, tzinfo=timezone.utc))
            .order_by(LedgerEntry.id)).first()
        e.gross_cad += 100
    controller.run_cycle(db, now=NOW)
    assert close.verify_lock(db, prev)["intact"] is True
    late = X.listing(db, kind="late_adjustment")
    assert late and late[0]["period"] == NOW.strftime("%Y-%m"), late
    assert dashboard.summary(db, now=NOW)["exceptions"]["open"] >= 1


def test_L7_forecast_cost_low_end_uses_actual_history():
    """A 10-day-old cost history must not be averaged over 60 days."""
    from brambleloop.core.models import CostEntry
    from brambleloop.finance.accounting import forecast, posting_rules

    db = _db(seed=False)
    with db.session() as s:
        for i in range(10):
            s.add(CostEntry(at=NOW - timedelta(days=i), kind="llm", agent="a",
                            provider="anthropic", model="m", purpose="p", amount_cad=6.0,
                            detail={"basis": "measured"}))
    posting_rules.post_all(db, now=NOW)
    f = forecast.forecast(db, now=NOW, horizon_days=30)
    # 6 CAD/day over the 10 days that exist -> ~180 for 30 days, not 60/60*30 = 30.
    assert f["operating_cost"]["low_cad"] >= 150.0, f["operating_cost"]


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
