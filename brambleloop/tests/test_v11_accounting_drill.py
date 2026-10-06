"""v1.1 lane E: drill-through (F-915), profitability (F-906) and cost attribution (F-907).

Section 95: "Trace a displayed profit number from the phone UI to source orders, fees, spend
and corrections."
Run: cd brambleloop && PYTHONPATH=src python3 tests/test_v11_accounting_drill.py
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="v11_acct_drill_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")


def _no_network(*_a, **_k):
    raise OSError("network refused by the accounting harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import LedgerEntry  # noqa: E402
from brambleloop.finance.accounting import (attribution, dashboard,  # noqa: E402
                                            posting_rules, profitability, shadow_dataset)

NOW = datetime.now(timezone.utc)
_n = [0]


def _db():
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    shadow_dataset.seed(db, now=NOW)
    posting_rules.post_all(db, now=NOW)
    return db


def test_displayed_profit_traces_to_orders_fees_spend_and_corrections():
    """Section 95."""
    db = _db()
    # A correction: a later refund on the first sale's ledger row.
    with db.session() as s:
        first = s.scalar(select(LedgerEntry).where(LedgerEntry.category == "sale")
                         .order_by(LedgerEntry.at.desc()))
        first.refunds_cad = round(first.refunds_cad + 1.0, 2)
        corrected_ref = first.evidence_ref
    posting_rules.post_all(db, now=NOW)
    shown = {i["metric"]: i for i in dashboard.summary(db, now=NOW)["items"]}["profit"]
    assert shown["value_cad"] is not None and shown["drill"] == "profit"
    d = dashboard.drill(db, shown["drill"], now=NOW)
    assert d["status"] == "OK" and d["value_cad"] == shown["value_cad"], (d["value_cad"], shown)
    assert d["check"]["matches"]
    assert abs(sum(r["contribution_cad"] for r in d["rows"]) - d["value_cad"]) < 0.005
    assert abs(sum(r["contribution_cad"] for r in d["rows"])
               - d["check"]["sum_of_rows_cad"]) < 1e-6
    assert d["rows"]
    tables = {r["source_table"] for r in d["rows"]}
    assert {"ledger", "cost_entries"} <= tables, tables
    orders = [r["source_row"]["order"] for r in d["rows"]
              if r["source_table"] == "ledger" and r["source_row"].get("order")]
    assert orders and all(o["external_ref"].startswith("etsy:") for o in orders)
    fee_rows = [r for r in d["rows"] if r["account"] == "5100"]
    assert fee_rows and all(r["source_row"]["fees_basis"] for r in fee_rows)
    spend = [r for r in d["rows"] if r["source_table"] == "cost_entries"]
    assert spend and all(r["source_row"]["provider"] or r["source_row"]["kind"]
                         for r in spend)
    assert any(r["kind"] == "reversal" for r in d["rows"])
    chain = [c for c in d["corrections"] if any(h["kind"] == "reversal" for h in c["history"])]
    assert chain and [h["kind"] for h in chain[0]["history"]] == ["original", "reversal",
                                                                  "original"]
    assert any(r["source_ref"] == corrected_ref for r in d["rows"])


def test_every_dashboard_metric_drills_and_sums():
    db = _db()
    s = dashboard.summary(db, window="all", now=NOW)
    drillable = [i for i in s["items"] if i["drill"]]
    assert drillable
    for i in drillable:
        d = dashboard.drill(db, i["drill"], window="all", now=NOW)
        if i["value_cad"] is None:
            assert d["value_cad"] is None, i["metric"]
            continue
        assert d["check"]["matches"], i["metric"]
        assert abs(d["value_cad"] - i["value_cad"]) < 0.006, (i["metric"], d["value_cad"],
                                                              i["value_cad"])
    bad = dashboard.drill(db, "vibes")
    assert bad["status"] == "UNKNOWN" and "profit" in bad["valid_metrics"]


def test_profitability_by_every_dimension_sums_to_the_company_total():
    db = _db()
    totals = set()
    for dim in profitability.DIMENSIONS:
        r = profitability.by(db, dim)
        assert r["rows"], dim
        assert abs(sum(x["profit_cad"] for x in r["rows"]) - r["total_profit_cad"]) < 1e-3
        totals.add(round(r["total_profit_cad"], 3))
    assert len(totals) == 1, totals
    prod = {x["product"]: x for x in profitability.by(db, "product")["rows"]}
    assert "unattributed" in prod, "unattributed costs are shown, not spread"
    assert all(x["basis"] in ("actual", "estimated") for x in prod.values())
    assert any(x["basis"] == "estimated" for x in prod.values()), "modelled fees are estimates"
    ch = {x["channel"] for x in profitability.by(db, "channel")["rows"]}
    assert "unattributed" in ch


def test_cost_attribution_by_product_release_department_provider():
    db = _db()
    a = attribution.report(db)
    assert a["total_cad"] > 0
    assert a["by"]["category"]["image_render"] > 0 and a["by"]["category"]["model_api"] > 0
    assert a["by"]["category"]["marketplace_fees"] > 0
    assert a["by"]["category"]["benchmark_purchases"] == 6.5
    assert a["by"]["product"]["granny-square-tote"] >= 0.96
    assert a["by"]["provider"]["anthropic"] > 0 and a["by"]["department"]["design"] > 0
    assert a["unattributed_share"] is not None and 0 < a["unattributed_share"] < 1
    assert abs(sum(a["by"]["category"].values()) - a["total_cad"]) < 1e-3


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
