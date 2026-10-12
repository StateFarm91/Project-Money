"""W4-CCFM2: Command Center executive (F-661), agents workspace (F-668), autonomy health (F-729).

Every figure is read from durable tables and equals what SQL says (like test_cert_dashboard);
UNKNOWN is never shown as 0.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_ccfm2.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_ccfm2_")
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/v{len(os.listdir(_TMP))}.sqlite")
    db.create_all()
    return db


def _job(s, *, agent="researcher", status="DONE", finished=None, created=None, run_after=None,
         job_type="intel.scan"):
    from brambleloop.core.models import Job, JobStatus

    j = Job(agent=agent, job_type=job_type, inputs={}, status=getattr(JobStatus, status),
            attempts=1, finished_at=finished, started_at=finished,
            created_at=created or NOW, run_after=run_after or NOW - timedelta(minutes=1))
    s.add(j)
    return j


def _by(items, key="metric"):
    return {i[key]: i for i in items}


def test_executive_is_unmeasured_until_the_order_source_is_read():
    from brambleloop.app.command_center import executive
    from brambleloop.core.models import Incident, Listing, SupportCase

    db = _db()
    with db.session() as s:
        s.add(Listing(product_slug="a", version="1.0.0", title="t", description="d", state="active", etsy_listing_id="123"))
        s.add(Listing(product_slug="b", version="1.0.0", title="t2", description="d"))
        s.add(Incident(severity="P1", signature="x", summary="customer-facing"))
        s.add(Incident(severity="P2", signature="y", summary="internal"))
        s.add(Incident(severity="P1", signature="z", summary="done", resolved=True))
        s.add(SupportCase(customer_ref="c", question="q", escalated=True, sent=False))
    env = executive.executive(db, now=NOW)
    rows = _by(env["items"])
    for k in ("today", "month", "90d"):
        rev = rows[f"revenue_{k}"]["revenue"]
        assert rev["value_cad"] is None and rev["state"] == "UNMEASURED", rev
    assert rows["conversion"]["value"] is None and rows["conversion"]["state"] == "UNKNOWN"
    assert rows["live_listings"]["value"] == 1 and rows["live_listings"]["drafted"] == 2
    risk = rows["customer_risk"]
    assert risk["value"] == 2 and risk["open_p0_p1_incidents"] == 1
    assert risk["escalated_support_awaiting_reply"] == 1
    assert env["status"] == "DEGRADED" and "UNMEASURED" in env["reason"]
    assert rows["profit_all_time"]["profit"]["value_cad"] is None


def test_revenue_windows_sum_only_reconciled_measured_sales_when_measured():
    from brambleloop.app import dashboard_truth
    from brambleloop.app.command_center import executive
    from brambleloop.core.models import LedgerEntry
    from brambleloop.finance.reconcile import RECONCILED

    db = _db()
    with db.session() as s:
        def sale(at, gross, refunds=0.0, recon=RECONCILED, basis="measured", ref="r"):
            s.add(LedgerEntry(at=at, category="sale", gross_cad=gross, refunds_cad=refunds,
                              evidence_ref=f"{ref}{gross}{at.isoformat()}", basis=basis,
                              reconciliation_state=recon))
        sale(NOW - timedelta(minutes=10), 10.0, refunds=1.0)
        sale(NOW - timedelta(days=40), 5.0)
        sale(NOW - timedelta(days=100), 7.0)
        sale(NOW - timedelta(minutes=5), 99.0, recon="unreconciled")       # never counted
        sale(NOW - timedelta(minutes=5), 50.0, basis="estimated")          # never counted
    real = dashboard_truth._order_source
    dashboard_truth._order_source = lambda _db: {"measured": True, "why": ""}
    try:
        w = executive.revenue_windows(db, now=NOW)
    finally:
        dashboard_truth._order_source = real
    assert w["today"]["value_cad"] == 9.0 and w["today"]["state"] == "MEASURED"
    month_start = NOW.replace(day=1, hour=0, minute=0, second=0)
    assert w["month"]["value_cad"] == (9.0 + (5.0 if NOW - timedelta(days=40) >= month_start
                                              else 0.0))
    assert w["90d"]["value_cad"] == 14.0


def test_agents_workspace_columns_equal_sql():
    from brambleloop.app.command_center import executive
    from brambleloop.core.models import Agent, CostEntry

    db = _db()
    with db.session() as s:
        s.add(Agent(name="researcher", daily_cost_ceiling_cad=1.0))
        s.add(Agent(name="growth", daily_cost_ceiling_cad=0.0))
        s.add(Agent(name="never_ran", daily_cost_ceiling_cad=2.0))
        _job(s, agent="researcher", finished=NOW - timedelta(hours=1))
        _job(s, agent="researcher", finished=NOW - timedelta(hours=2))
        _job(s, agent="researcher", status="DEAD", finished=NOW - timedelta(hours=3))
        _job(s, agent="researcher", finished=NOW - timedelta(days=3))     # outside 24 h
        _job(s, agent="growth", status="RUNNING", finished=None)
        s.add(CostEntry(at=NOW - timedelta(minutes=1), agent="researcher", amount_cad=0.4))
        s.add(CostEntry(at=NOW - timedelta(minutes=1), agent="growth", amount_cad=0.1))
    env = executive.agents_workspace(db, now=NOW)
    rows = _by(env["items"], "agent")
    assert set(rows) == {"researcher", "growth", "never_ran"}
    r = rows["researcher"]
    assert (r["completed_24h"], r["failed_24h"], r["state"]) == (2, 1, "idle")
    assert abs(r["spent_today_cad"] - 0.4) < 1e-9 and r["daily_ceiling_cad"] == 1.0
    assert r["over_ceiling"] is False
    g = rows["growth"]
    assert g["state"] == "active" and g["current_job"]["job_type"] == "intel.scan"
    assert g["over_ceiling"] is True                          # a CA$0 ceiling is a permission of 0
    assert rows["never_ran"]["state"] == "UNKNOWN" and rows["never_ran"]["why"]
    assert env["status"] == "DEGRADED"
    assert executive.agents_workspace(_db(), now=NOW)["status"] == "UNKNOWN"


def test_autonomy_health_reads_hours_oldest_ready_owner_blocked_and_states():
    from brambleloop.app.command_center import executive

    db = _db()
    with db.session() as s:
        _job(s, finished=NOW - timedelta(minutes=10))
        _job(s, finished=NOW - timedelta(minutes=20))                     # same hour bucket?
        _job(s, finished=NOW - timedelta(hours=5))
        _job(s, status="PENDING", created=NOW - timedelta(minutes=30))
        _job(s, status="PENDING", created=NOW - timedelta(hours=2),
             run_after=NOW + timedelta(hours=1))                          # not ready yet
    auto = {"items": [{"state": "active"}, {"state": "sleeping", "next_wake": "x"},
                      {"state": "sleeping"}, {"state": "blocked"}]}
    env = executive.autonomy_health(db, auto=auto, owner={"open_actions": 3}, now=NOW)
    rows = _by(env["items"])
    hrs = {(NOW - timedelta(minutes=m)).replace(minute=0, second=0) for m in (10, 20)}
    assert rows["hours_with_completed_work_24h"]["value"] == len(hrs) + 1
    old = rows["oldest_ready_work_seconds"]
    assert abs(old["value"] - 1800) <= 2 and old["ready_pending"] == 1
    assert rows["owner_blocked_decisions"]["value"] == 3
    st = rows["agent_states"]
    assert (st["active"], st["watching"], st["blocked"], st["unknown"]) == (1, 1, 1, 1)
    empty = executive.autonomy_health(_db(), auto={"items": []}, owner={}, now=NOW)
    erows = _by(empty["items"])
    assert empty["status"] == "UNKNOWN"
    assert erows["hours_with_completed_work_24h"]["value"] is None       # never 0
    assert erows["oldest_ready_work_seconds"]["value"] is None
    assert erows["owner_blocked_decisions"]["value"] is None
    assert erows["agent_states"]["active"] is None


def test_tabs_carry_the_new_blocks():
    from brambleloop.app.command_center import tabs

    db = _db()
    assert "executive" in tabs.home(db)["sections"]
    assert "agents_workspace" in tabs.autonomy(db)["sections"]
    assert "autonomy_health" in tabs.operations(db)["sections"]
    static = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static" / "js" / "views"
    assert '["executive", ' in (static / "home.js").read_text()
    assert '["agents_workspace", ' in (static / "learn.js").read_text()
    assert '["autonomy_health", ' in (static / "operations.js").read_text()


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
