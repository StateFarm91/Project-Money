"""W4-CCFINST: F-620 Command Center Finance -- the owner statement, MTD beside YTD.

Criterion (registry F-620, quoted): "Show MTD/YTD sales, refunds, Etsy fees, free ad credit,
cash ad spend, AI/infrastructure/software expenses, contribution profit, margin, tax reserve,
payout/cash position, unreconciled items and monthly-close status."

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_ccfinst.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_ccfinst_")

REQUIRED = ("gross_sales", "refunds", "etsy_fees", "free_ad_credit", "cash_ad_spend",
            "ai_spend", "infra_software_spend", "contribution", "margin", "tax_reserve",
            "cash", "expected_payout", "unreconciled", "monthly_close")


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/v{len(os.listdir(_TMP))}.sqlite")
    db.create_all()
    return db


def _rows(env):
    return {i["metric"]: i for i in env["items"]}


def test_every_criterion_line_is_present_mtd_beside_ytd():
    from brambleloop.app.command_center import finance_statement as F

    env = F.statement(_db())
    assert env["status"] in ("OK", "DEGRADED", "BLOCKED", "UNKNOWN"), env
    rows = _rows(env)
    missing = [k for k in REQUIRED if k not in rows]
    assert not missing, (missing, sorted(rows))
    for k, r in rows.items():
        if r["kind"] != "status":
            assert set(F.WINDOWS) <= set(r), r
    assert set(env["columns"]) == set(F.WINDOWS), env.get("columns")
    assert "month to date" in env["columns"]["mtd"] and "year to date" in env["columns"]["ytd"]


def test_unread_order_source_is_unknown_never_zero():
    from brambleloop.app.command_center import finance_statement as F

    rows = _rows(F.statement(_db()))
    for k in ("gross_sales", "refunds", "etsy_fees", "contribution", "tax_reserve"):
        for w in F.WINDOWS:
            cell = rows[k][w]
            assert cell["value_cad"] is None and cell["state"] in ("UNKNOWN", "STALE"), (k, w, cell)
            assert cell["why"], (k, w, cell)
    for w in F.WINDOWS:
        assert rows["margin"][w]["value"] is None and rows["margin"][w]["state"] == "UNKNOWN"
        credit = rows["free_ad_credit"][w]
        assert credit["value_cad"] is None and credit["state"] == "UNKNOWN", credit
        assert "not a zero credit" in credit["why"], credit
    close = rows["monthly_close"]
    assert close["state"] == "MEASURED" and close["previous_period_locked"] is False, close
    assert close["value"].endswith("not closed"), close


def test_recorded_spend_splits_by_account_and_ad_credit_makes_cash_ads_an_estimate():
    from brambleloop.app.command_center import finance_statement as F
    from brambleloop.core.models import CostEntry
    from brambleloop.finance import credits

    db = _db()
    now = datetime.now(timezone.utc)
    with db.session() as s:
        s.add(CostEntry(agent="a", kind="llm", amount_cad=3.0, provider="anthropic", at=now))
        s.add(CostEntry(agent="a", kind="image", amount_cad=1.0, provider="img", at=now))
        s.add(CostEntry(agent="a", kind="hosting", amount_cad=5.0, provider="railway", at=now))
        s.add(CostEntry(agent="a", kind="ads", amount_cad=2.0, provider="etsy_ads", at=now))
    rows = _rows(F.statement(db, now=now))
    for w in F.WINDOWS:
        assert rows["ai_spend"][w]["value_cad"] == 4.0, rows["ai_spend"]
        assert rows["infra_software_spend"][w]["value_cad"] == 5.0, rows["infra_software_spend"]
        assert rows["ai_spend"][w]["state"] in ("RECORDED", "ESTIMATED")
        assert rows["cash_ad_spend"][w] == {"value_cad": 2.0, "state": "RECORDED",
                                            "why": rows["cash_ad_spend"][w]["why"]}
        assert rows["free_ad_credit"][w]["state"] == "UNKNOWN"
    credits.grant(db, provider="etsy_ads", kind="ads_credit", amount=7.10, currency="CAD",
                  granted_on=(now.date().replace(day=1)).isoformat(),
                  evidence_ref="test:etsy_plus_statement")
    rows = _rows(F.statement(db, now=now))
    for w in F.WINDOWS:
        credit = rows["free_ad_credit"][w]
        assert credit["state"] == "ESTIMATED" and credit["value_cad"] == 5.10, credit
        cash_ads = rows["cash_ad_spend"][w]
        assert cash_ads["state"] == "ESTIMATED" and cash_ads["value_cad"] == 0.0, cash_ads
        assert "assumed" in cash_ads["why"], cash_ads


def test_money_tab_carries_the_statement_and_the_view_renders_it():
    from brambleloop.app.command_center import tabs

    out = tabs.money(_db())
    fin = out["sections"]["finance_statement"]
    assert fin["provider"] == "command_center.finance_statement", fin
    js = (ROOT / "src/brambleloop/app/command_center/static/js/views/money.js").read_text()
    assert "function financeStatementCard(env, result)" in js
    assert 'labelId: "money-finance-statement"' in js
    assert "formatMoney(c)" in js  # money cells use the shared Unknown-never-0 formatter


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            import traceback; traceback.print_exc()
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {str(exc)[:500]}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
