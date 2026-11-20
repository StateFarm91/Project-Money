"""W4-CCALL: F-622 combined Marketing & Customers owner view.

Orders by channel and refunds are UNKNOWN (never 0) until the order source is read; ROAS comes
from growth.ads_readiness and is UNKNOWN without measured ad spend; CPC/CTR and review themes
have no source and say so; no customer content is shown.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_ccall.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_ccall_")


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/v{len(os.listdir(_TMP))}.sqlite")
    db.create_all()
    return db


def _rows(env):
    return {i["metric"]: i for i in env["items"]}


def test_marketing_customers_is_unknown_not_zero_until_orders_are_read():
    from brambleloop.app.command_center import tabs
    from brambleloop.core.models import SupportCase

    db = _db()
    with db.session() as s:
        s.add(SupportCase(customer_ref="SENTINEL-REF", question="SENTINEL text", escalated=True))
    env = tabs.marketing_customers(db)
    assert "SENTINEL" not in json.dumps(env)
    r = _rows(env)
    for k in ("orders_organic", "orders_paid", "orders_owned", "orders_unattributed", "refunds"):
        assert r[k]["value"] is None and r[k]["state"] == "UNKNOWN" and r[k]["why"], r[k]
    assert r["roas"]["value"] is None and r["roas"]["state"] == "UNKNOWN"
    assert r["cpc_ctr"]["state"] == "UNKNOWN" and r["review_themes"]["state"] == "UNKNOWN"
    assert r["support_cases"]["value"] == 1 and r["support_cases"]["escalated"] == 1
    assert env["status"] == "DEGRADED" and "orders UNKNOWN" in env["reason"]
    assert "marketing_customers" in tabs.insights(db)["sections"]


def test_measured_orders_are_split_by_channel():
    from brambleloop.app import dashboard_truth
    from brambleloop.app.command_center import tabs
    from brambleloop.core.models import Customer, Order

    db = _db()
    with db.session() as s:
        c = Customer(customer_ref="c1")
        s.add(c)
        s.flush()
        for i, src in enumerate(("etsy_search", "etsy_ads", "pinterest", "unknown", "etsy_organic")):
            s.add(Order(customer_id=c.id, external_ref=f"o{i}", product_slug="p",
                        acquisition_source=src, refunded=(i == 0)))
    real = dashboard_truth._order_source
    dashboard_truth._order_source = lambda _db: {"measured": True, "why": ""}
    try:
        r = _rows(tabs.marketing_customers(db))
    finally:
        dashboard_truth._order_source = real
    # o0 (etsy_search) is refunded, so voided: not a countable order, but a refund.
    assert (r["orders_organic"]["value"], r["orders_paid"]["value"],
            r["orders_owned"]["value"]) == (1, 1, 1), r
    assert r["orders_unattributed"]["value"] == 1
    assert r["orders_organic"]["state"] == "MEASURED"
    assert r["refunds"]["value"] == 1 and r["refunds"]["state"] == "MEASURED"


def test_insights_view_puts_the_combined_view_first():
    js = (ROOT / "src" / "brambleloop" / "app" / "command_center" / "static" / "js" / "views"
          / "insights.js").read_text(encoding="utf-8")
    assert 'const ORDER = [["marketing_customers", "Marketing & customers"]' in js


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
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {str(exc)[:500]}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
