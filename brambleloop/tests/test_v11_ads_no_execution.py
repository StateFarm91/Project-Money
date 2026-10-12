"""v1.1 lane H: the ads module has no execution capability, and its KPIs resist gaming.

Directive §12 / F-930: Growth may research, propose, prepare and measure; it may not launch a
paid campaign. There is no Etsy Ads write API in this repository and this module must not add
one. F-918: ROAS is computed on evidence-attributed revenue only, with confidence, and a good
ROAS never authorises spend.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_v11_ads_no_execution.py
"""
from __future__ import annotations

import ast
import inspect
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.core.models import CostEntry, Customer, Order  # noqa: E402
from brambleloop.growth import ads_readiness as ads  # noqa: E402
from test_v11_ads_readiness import NOW, TRUST_PASS, add_listing, fresh_db, make_eligible  # noqa: E402

NETWORK_MODULES = {"socket", "requests", "httpx", "urllib", "urllib3", "http", "aiohttp",
                   "ssl", "smtplib"}
FORBIDDEN_IMPORTS = NETWORK_MODULES | {"brambleloop.integrations", "integrations",
                                       "brambleloop.publish", "publish"}
FORBIDDEN_CALLS = {"authorise_spend", "enqueue", "reserve", "reserve_in", "urlopen",
                   "request", "post", "put"}
FORBIDDEN_NAME_WORDS = ("activate", "launch", "execute", "spend_now", "start_campaign",
                        "create_campaign")


def _tree():
    return ast.parse(inspect.getsource(ads))


def test_no_network_or_integration_imports():
    found = []
    nodes = list(ast.walk(_tree()))
    assert nodes
    for node in nodes:
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    assert found, "parsed no imports at all"
    bad = [m for m in found
           if m.lstrip(".").split(".")[0] in FORBIDDEN_IMPORTS
           or any(m.lstrip(".").startswith(f) for f in FORBIDDEN_IMPORTS)]
    assert not bad, bad


def test_no_spend_enqueue_or_http_calls():
    calls = []
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call):
            f = node.func
            calls.append(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
    assert calls
    assert not (set(calls) & FORBIDDEN_CALLS), set(calls) & FORBIDDEN_CALLS


def test_no_function_named_like_an_executor():
    names = [n.name for n in ast.walk(_tree())
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert "propose" in names and "summary" in names
    bad = [n for n in names if any(w in n.lower() for w in FORBIDDEN_NAME_WORDS)]
    assert not bad, bad


def test_full_flow_runs_with_network_disabled_and_spends_nothing():
    real = socket.socket

    def refuse(*a, **k):
        raise AssertionError("ads module attempted a network connection")

    socket.socket = refuse
    try:
        db = fresh_db()
        add_listing(db, "n")
        make_eligible(db)
        got = ads.propose(db, "n", daily_budget_cad=1.0, days=3, funding="etsy_plus_credit",
                          hypothesis="TEST FIXTURE h", stop_condition="TEST FIXTURE stop",
                          now=NOW, trust_gate=TRUST_PASS)
        ads.tick(db, now=NOW)
        s = ads.summary(db)
        ads.next_work(db, now=NOW)
    finally:
        socket.socket = real
    assert got["executed"] is False
    assert s["spend_executed_cad"] == 0.0 and s["activation_authorised"] is False
    with db.session() as sess:
        assert sess.query(CostEntry).count() == 0  # no spend row written


def test_roas_uses_only_evidence_attributed_ads_revenue():
    orders = [
        {"channel": "etsy_ads", "revenue_cad": 12, "contribution_cad": 10, "evidence": "stats"},
        {"channel": "etsy_ads", "revenue_cad": 12, "contribution_cad": 10, "evidence": ""},
        {"channel": "etsy_organic", "revenue_cad": 500, "contribution_cad": 450,
         "evidence": "stats"},
        {"channel": "unattributed", "revenue_cad": 300, "contribution_cad": 250,
         "evidence": ""},
        {"channel": "offsite_ads", "revenue_cad": 40, "contribution_cad": 30, "evidence": "fee"},
    ]
    r = ads.attributed_roas(orders, spend_cad=6.0, spend_basis="measured")
    assert r["attributed_orders"] == 1 and r["excluded_orders"] == 4
    assert r["roas"] == 2.0 and r["contribution_roas"] == round(10 / 6, 4)
    assert r["confidence"] == "low"  # one order is not evidence of scale


def test_roas_without_measured_spend_is_unknown_not_zero_or_infinite():
    orders = [{"channel": "etsy_ads", "revenue_cad": 12, "contribution_cad": 10,
               "evidence": "stats"}]
    for spend, basis in ((None, "unknown"), (5.0, "estimated"), (0.0, "measured")):
        r = ads.attributed_roas(orders, spend_cad=spend, spend_basis=basis)
        assert r["status"] == "UNKNOWN" and r["roas"] is None, (spend, basis)


def test_confidence_reaches_adequate_only_at_floor():
    one = {"channel": "etsy_ads", "revenue_cad": 10, "contribution_cad": 8, "evidence": "x"}
    n = ads.MIN_ATTRIBUTED_ORDERS_FOR_CONFIDENCE
    assert ads.attributed_roas([one] * (n - 1), spend_cad=10.0,
                               spend_basis="measured")["confidence"] == "low"
    assert ads.attributed_roas([one] * n, spend_cad=10.0,
                               spend_basis="measured")["confidence"] == "adequate"


def test_db_kpis_blend_nothing_and_never_authorise():
    db = fresh_db()
    with db.session() as s:
        c = Customer(customer_ref="TEST-FIXTURE-C1")
        s.add(c)
        s.flush()
        s.add(Order(customer_id=c.id, external_ref="TEST-FIXTURE-O1", product_slug="k",
                    revenue_cad=900.0, contribution_cad=800.0,
                    acquisition_source="etsy_organic",
                    detail={"state": "paid", "attribution": {"evidence": "TEST stats"}}))
        s.add(Order(customer_id=c.id, external_ref="TEST-FIXTURE-O2", product_slug="k",
                    revenue_cad=12.0, contribution_cad=10.0, acquisition_source="etsy_ads",
                    detail={"state": "paid", "attribution": {"evidence": "TEST stats"}}))
        s.add(CostEntry(agent="ads", kind="ads", amount_cad=5.0))
    k = ads.kpis(db)
    assert k["roas"]["attributed_orders"] == 1 and k["roas"]["attributed_revenue_cad"] == 12.0
    assert k["roas"]["excluded_orders"] == 1  # the CA$900 organic order is not ad revenue
    assert k["roas"]["roas"] == 2.4 and k["roas"]["confidence"] == "low"
    assert k["may_scale_on_kpis"] is False
    assert k["guardrails"]["organic_and_paid_separate"] is True


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            fails += 1
            print("FAIL", name, repr(e))
    print(f"{len(tests) - fails} passing, {fails} failing")
    sys.exit(1 if fails else 0)
