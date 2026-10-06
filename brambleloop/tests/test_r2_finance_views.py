"""R2-FIN regressions: MONEY tab / brief / books freshness and basis, spend challenge.

Audit of final-candidate-ddf9c6e (research/final_build/audit_ddf9c6e/REPORT_finance.md):
M4 (tab, books), M6, M11, L4. Each fails on ddf9c6e and passes after the fix.
Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_finance_views.py
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


def test_M4_stale_orders_are_not_measured_on_money_tab_or_books():
    """p13: last receipt read 10 days ago."""
    from brambleloop.app.command_center import tabs
    from brambleloop.finance.books import Books

    db = _db(at=NOW - timedelta(days=10))
    controller.run_cycle(db, now=NOW - timedelta(days=10))
    m = tabs.money(db)
    assert m["revenue"]["state"] != "MEASURED", m["revenue"]
    assert m["revenue"]["value_cad"] is None or m["revenue"]["state"] == "STALE"
    assert m["source_health"]["order_source_measured"] is False, m["source_health"]
    assert m["source_health"]["warning"], m["source_health"]
    pl = Books(db).profit_and_loss(since=NOW - timedelta(days=60), until=NOW)
    assert pl.sales_reading == "STALE", pl.sales_reading
    assert pl.to_dict()["profit_basis"] != "measured"


def test_M6_brief_and_recorded_spend_basis_come_from_rows():
    """p12: a modelled listing fee and an unknown-basis model call are not `measured`."""
    from brambleloop.app.command_center import tabs
    from brambleloop.core.models import CostEntry

    db = _db(seed=False)
    with db.session() as s:
        s.add(CostEntry(at=NOW, kind="etsy_listing_fee", agent="x", provider="etsy", model="",
                        purpose="reserve", amount_cad=0.28, detail={"basis": "modelled"}))
        s.add(CostEntry(at=NOW, kind="llm", agent="x", provider="anthropic", model="m",
                        purpose="p", amount_cad=1.0, estimated_cad=1.0, detail={}))
    b = tabs.morning_brief(db)["sections"]["money_spent"]
    assert b["total"]["basis"] != "measured", b["total"]
    assert b["total"]["by_basis_cad"].get("modelled") == 0.28, b["total"]
    assert "not measured" in b["total"]["display"], b["total"]
    m = tabs.money(db)
    assert m["recorded_spend"]["basis"] != "measured", m["recorded_spend"]
    item = tabs._money_item({"metric": "owner_payable", "value_cad": 1.0,
                             "reading": "derived"})
    assert item["state"] == "RECORDED" and item["basis"] == "derived", item


def test_M11_check_spend_kind_is_validated_and_amount_must_be_finite():
    """p06: synonyms of ads get the ads caps; unknown kinds and NaN/inf are refused."""
    from brambleloop.core import phase as phase_mod
    from brambleloop.core.models import OwnerAction
    from brambleloop.finance.accounting import policy

    db = _db()
    R.import_statement(db, "bank", [{"external_id": "c1", "at": NOW - timedelta(days=1),
                                     "kind": "owner_contribution", "amount": 20000.0,
                                     "reference": "seed"}], now=NOW)
    controller.run_cycle(db, now=NOW)
    for x in X.listing(db):
        X.resolve(db, x["key"], resolution="reviewed in the R2-FIN fixture", by="owner")
    with db.session() as s:
        s.add(OwnerAction(requirement_key="auth:big", action="approve", reason="x",
                          max_cost_cad=5000.0, done=True))
    real = phase_mod.effective
    phase_mod.effective = lambda *a, **k: "limited_production"  # isolate the kind rules
    try:
        def chk(**p):
            base = {"amount_cad": 900.0, "purpose": "promoted listings test",
                    "proposer": "growth", "expected_contribution_cad": 2000.0,
                    "authority": {"type": "owner_action", "ref": "auth:big"}}
            base.update(p)
            r = policy.check_spend(db, base, now=NOW)
            return r, {c["rule"] for c in r["checks"] if c["outcome"] == "block"}

        cases = ("advertising", "ads ", "etsy_ads", "Etsy-Ads")
        assert cases
        for k in cases:
            r, blocks = chk(kind=k)
            assert r["allow"] is False and "caps" in blocks, (k, r["verdict"], blocks)
        r, blocks = chk(kind="crypto_mining", amount_cad=10.0)
        assert r["allow"] is False and "kind" in blocks, (r["verdict"], blocks)
        bad = (float("nan"), "nan", float("inf"), -5.0, None)
        assert bad
        for amt in bad:
            r, blocks = chk(kind="advertising", amount_cad=amt)
            assert r["allow"] is False and "amount" in blocks, (amt, blocks)
        r, blocks = chk(kind="ads", amount_cad=10.0, expected_contribution_cad=float("nan"))
        assert r["allow"] is False and "margin" in blocks, blocks
    finally:
        phase_mod.effective = real


def test_L4_money_drill_revenue_returns_the_headline_rows_when_measured():
    from brambleloop.app.command_center import tabs

    db = _db()
    controller.run_cycle(db, now=NOW)
    rev = tabs.money(db)["revenue"]
    d = tabs.money_drill(db, "revenue")
    if rev["state"] == "MEASURED":
        assert d["status"] == "OK" and d["items"], d
        assert d["check"]["matches"] is True, d["check"]
    else:
        assert d["status"] == "UNKNOWN"
    assert "not built" not in str(d.get("reason") or ""), d


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
