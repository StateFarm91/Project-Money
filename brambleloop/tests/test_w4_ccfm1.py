"""W4-CCFM1: Command Center completion, Final Master post-launch rows F-619, F-621, F-651, F-652.

* F-619 / F-651: every owner area the Final Master names maps to a Command Center route and the
  API it reads (`tabs.WORKSPACES`); the one area with no view, Customers, now has one
  (`tabs.customers`, shown on Insights): aggregates only, UNKNOWN (never 0) while the order
  source is not read, no buyer content.
* F-621: each department carries its objective (charter mission), recorded spend (governor
  spend_by department; UNKNOWN when unattributed) and a measured 7-day completed-work trend.
* F-652 / F-670: a recorded-spend trend (30 days) and a dependency-free SVG bar chart that draws
  unknown values as gaps, never as zero bars.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_ccfm1.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_ccfm1_")
STATIC = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static"
NOW = datetime.now(timezone.utc)


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/v{len(os.listdir(_TMP))}.sqlite")
    db.create_all()
    return db


def _job(s, *, dept: str, finished: datetime, status="DONE"):
    from brambleloop.core.models import Job, JobStatus

    s.add(Job(agent="coo", job_type="autonomy.department_review", inputs={"department": dept},
              status=getattr(JobStatus, status), attempts=1, started_at=finished,
              finished_at=finished, outputs={"ok": True}))


def _cost(s, *, at: datetime, cad: float, department: str = ""):
    from brambleloop.core.models import CostEntry

    s.add(CostEntry(at=at, agent="researcher", kind="llm", amount_cad=cad, department=department))


def test_completed_trend_is_measured_per_department_and_day():
    from brambleloop.app.command_center import company

    db = _db()
    with db.session() as s:
        _job(s, dept="intelligence", finished=NOW - timedelta(hours=1))
        _job(s, dept="intelligence", finished=NOW - timedelta(hours=2))
        _job(s, dept="intelligence", finished=NOW - timedelta(days=2))
        _job(s, dept="growth", finished=NOW - timedelta(days=10))          # outside the window
        _job(s, dept="growth", finished=NOW - timedelta(hours=3), status="DEAD")  # not completed
    t = company.completed_trend(db, company._job_dept_fn(), now=NOW)
    assert t["basis"] == "measured" and len(t["days"]) == company.TREND_DAYS
    assert t["days"][-1] == NOW.date().isoformat()
    research = t["by_department"]["intelligence"]
    assert research[-1] == 2 and research[-3] == 1 and sum(research) == 3
    assert "growth" not in t["by_department"]
    unk = company.completed_trend(db, None, now=NOW)
    assert unk["basis"] == "unknown" and unk["by_department"] == {} and unk["why"]


def test_department_spend_is_recorded_zero_only_when_nothing_was_spent():
    from brambleloop.app.command_center import company

    empty = company.department_spend(_db())
    z = company._dept_spend(empty, "intelligence")
    assert z["state"] == "RECORDED" and z["value_cad"] == 0.0
    db = _db()
    with db.session() as s:
        _cost(s, at=NOW - timedelta(days=1), cad=1.25, department="intelligence")
        _cost(s, at=NOW - timedelta(days=2), cad=0.75)                   # unattributed
    spend = company.department_spend(db)
    assert spend["ok"]
    r = company._dept_spend(spend, "intelligence")
    assert r["state"] == "RECORDED" and abs(r["value_cad"] - 1.25) < 1e-9
    g = company._dept_spend(spend, "growth")
    assert g["state"] == "UNKNOWN" and g["value_cad"] is None and "unattributed" in g["why"]
    bad = company._dept_spend({"ok": False, "why": "boom"}, "intelligence")
    assert bad["value_cad"] is None and bad["state"] == "UNKNOWN"


def test_departments_carry_objective_spend_and_trend():
    from brambleloop.app.command_center import company
    from brambleloop.autonomy import charters

    db = _db()
    with db.session() as s:
        _job(s, dept="intelligence", finished=NOW - timedelta(hours=1))
    keys = [c.key for c in charters.CHARTERS]
    assert keys
    auto = {"status": "OK", "as_of": NOW.isoformat(),
            "items": [{"department": k, "status": "OK"} for k in keys]}
    env = company.departments(db, auto=auto)
    items = env["items"]
    assert len(items) == len(keys)
    missions = {c.key: c.mission for c in charters.CHARTERS}
    for it in items:
        assert it["objective"] == missions[it["department"]] and it["objective"]
        assert it["spend_30d"]["state"] in ("RECORDED", "UNKNOWN")
        assert it["completed_trend_7d"]["basis"] == "measured"
        assert len(it["completed_trend_7d"]["counts"]) == company.TREND_DAYS
    research = next(i for i in items if i["department"] == "intelligence")
    assert research["completed_trend_7d"]["counts"][-1] == 1


def test_customers_are_aggregates_unknown_until_orders_are_read():
    from brambleloop.app.command_center import tabs
    from brambleloop.core.models import SupportCase

    db = _db()
    with db.session() as s:
        s.add(SupportCase(customer_ref="SENTINEL-BUYER-REF", question="SENTINEL question text",
                          answer="SENTINEL answer", escalated=True, sent=False))
        s.add(SupportCase(customer_ref="b2", question="q", answer="a", sent=True, resolved=True))
    out = tabs.customers(db)
    blob = json.dumps(out)
    assert "SENTINEL" not in blob, "customer content leaked into the aggregate view"
    orders = out["sections"]["orders"]
    assert orders["status"] == "UNKNOWN" and orders["items"]
    for it in orders["items"]:
        assert it["value"] is None and it["state"] == "UNKNOWN" and it["why"]
    sup = {i["metric"]: i["value"] for i in out["sections"]["support"]["items"]}
    assert sup == {"cases": 2, "awaiting_reply": 1, "escalated": 1, "resolved": 1}
    assert out["sections"]["reviews"]["status"] == "UNKNOWN"
    ins = tabs.insights(db)["sections"]
    assert {"customer_orders", "customer_support", "customer_reviews"} <= set(ins)


def test_spend_trend_sums_recorded_spend_per_day():
    from brambleloop.app.command_center import tabs

    db = _db()
    with db.session() as s:
        _cost(s, at=NOW - timedelta(minutes=5), cad=0.5)
        _cost(s, at=NOW - timedelta(minutes=6), cad=0.25)
        _cost(s, at=NOW - timedelta(days=3), cad=1.0)
        _cost(s, at=NOW - timedelta(days=40), cad=9.0)                   # outside 30 days
    env = tabs.spend_trend(db, now=NOW)
    vals = [i["value_cad"] for i in env["items"]]
    assert len(vals) == 30 and abs(vals[-1] - 0.75) < 1e-9 and abs(vals[-4] - 1.0) < 1e-9
    assert abs(env["total_cad"] - 1.75) < 1e-9
    assert "spend_trend" in tabs.money(db)["sections"]


def test_every_named_owner_area_has_a_route_and_an_api():
    from brambleloop.app import main
    from brambleloop.app.command_center import tabs

    ws = tabs.WORKSPACES
    assert ws
    areas = " | ".join(w["area"].lower() for w in ws)
    # F-619's and F-651's named areas, each served somewhere.
    for need in ("today", "month", "finance", "products", "listings", "marketing", "customers",
                 "experiments", "departments", "agent", "owner actions", "system health",
                 "visual", "etsy", "qa", "research", "reliability", "owner inbox",
                 "command center"):
        assert need in areas, need
    routes_js = (STATIC / "js" / "routes.js").read_text(encoding="utf-8")
    app_js = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
    paths = {getattr(r, "path", "") for r in main.app.routes}
    from brambleloop.app import security

    api_paths = {p for p, _m, _d in security.iter_api_routes(main.app)} | paths
    for w in ws:
        rid = w["route"]
        assert f'id: "{rid}"' in routes_js or f"{rid}:" in app_js, rid
        assert (STATIC / "js" / "views" / f"{rid}.js").is_file(), rid
        assert w["api"].split("?")[0] in api_paths, w["api"]
        assert w["rows"], w


def test_bar_chart_draws_unknown_as_a_gap_and_uses_no_html_sink():
    comp = (STATIC / "js" / "components.js").read_text(encoding="utf-8")
    body = comp[comp.index("export function barChart"):]
    assert "createElementNS" in body and "innerHTML" not in body
    assert "never as 0" in body or "never a 0" in body
    assert re.search(r'typeof v !== "number" \|\| !Number\.isFinite\(v\)\) return', body)
    css = (STATIC / "css" / "app.css").read_text(encoding="utf-8")
    assert ".chart-bar { fill: var(--accent); }" in css   # theme token: light and dark
    money = (STATIC / "js" / "views" / "money.js").read_text(encoding="utf-8")
    company_js = (STATIC / "js" / "views" / "company.js").read_text(encoding="utf-8")
    assert "barChart(" in money and "barChart(" in company_js


def test_f670_light_dark_tokens_chart_and_drill_down():
    """F-670: one shared stylesheet with light/dark tokens (system preference and an explicit
    choice), the chart component, and drill-down routes from cards to source rows."""
    css = (STATIC / "css" / "app.css").read_text(encoding="utf-8")
    assert "@media (prefers-color-scheme: dark)" in css
    assert ':root:not([data-theme="light"])' in css and ':root[data-theme="dark"]' in css
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'href="css/app.css"' in html and "<style" not in html     # shared, not inline
    app = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
    assert 'drill: { id: "drill"' in app and (STATIC / "js" / "views" / "drill.js").is_file()
    comps = (STATIC / "js" / "components.js").read_text(encoding="utf-8")
    assert "#/drill/${encodeURIComponent(ref)}" in comps            # every source list drills
    assert "export function barChart" in comps


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
