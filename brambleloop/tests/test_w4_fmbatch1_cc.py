"""W4-FMBATCH1 batch C: the Command Center gaps CLOSE5 named (F-621, F-661, F-668, F-729).

- F-621 "...each department's ... objective, blockers, completed work, queue, spend and KPI
  trend." -- gap: no charter-KPI trend.
- F-661 "Today/Month/90-day objective, revenue/orders/profit/spend, conversion, live listings,
  customer risk, incidents, active departments, completed work and owner decisions." -- gap:
  objective, incidents, active departments, completed work, owner decisions.
- F-668 "org chart with director/worker status, objective, current work, heartbeat, queue,
  evidence, cost, completions, failures and learning." -- gap: org chart, heartbeat, learning.
- F-729 "...restarts recovered, experiments, improvements promoted/reverted and whether any
  department is unintentionally idle." -- gap: those four.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="fmb1_cc_")

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app.command_center import executive as X  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, Improvement, Incident, Job, JobStatus,  # noqa: E402
                                     Lesson, RegisteredExperiment)

NOW = datetime.now(timezone.utc)
_n = [0]


def _db():
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/c{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _job(s, jt, agent, status=JobStatus.DONE, *, hours_ago=1.0, attempts=1, outputs=None,
         err=None, run_after=None):
    t = NOW - timedelta(hours=hours_ago)
    s.add(Job(agent=agent, job_type=jt, inputs={}, status=status, attempts=attempts,
              outputs=outputs if outputs is not None else {"made": jt, "n": hours_ago},
              last_error=err, created_at=t, started_at=t,
              finished_at=None if status == JobStatus.PENDING else t,
              run_after=run_after or t))


def _items(env):
    return {i.get("metric") or i.get("agent"): i for i in env.get("items") or []}


def test_f661_the_executive_block_carries_objective_incidents_departments_work_decisions():
    db = _db()
    ex = _items(X.executive(db))
    assert ex["objective"]["state"] == "UNKNOWN" and ex["objective"]["value"] is None
    assert ex["active_departments"]["value"] == 0 and ex["completed_work_24h"]["value"] == 0
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action="plan.strategy_reviewed",
                       detail={"as_of": "2026-10-01", "trajectory": {"target_cad": 100000,
                                                                    "is_forecast": False}}))
        s.add(Incident(signature="health:x", severity="P2", summary="x", detail={}))
        _job(s, "finance.governor", "cfo")
        _job(s, "radar.scan", "market_radar")
    ex = _items(X.executive(db))
    assert ex["objective"]["state"] == "RECORDED" and ex["objective"]["value"] == 100000
    assert ex["open_incidents"]["value"] == 1
    assert ex["completed_work_24h"]["value"] == 2
    assert ex["active_departments"]["value"] == 2, ex["active_departments"]
    assert "owner_decisions" in ex


def test_f668_org_chart_heartbeat_and_learning():
    db = _db()
    with db.session() as s:
        _job(s, "finance.governor", "cfo", hours_ago=2)
        s.add(Lesson(origin_cell="finance", subject="fees", statement="fees are modelled",
                     evidence_ref="x"))
    env = X.agents_workspace(db)
    rows = _items(env)
    cfo = rows["cfo"]
    assert cfo["role"] == "director" and cfo["heartbeat"] is not None
    assert cfo["department_lessons_30d"] == 1
    org = env["org_chart"]
    assert org["finance"]["director"]["agent"] == "cfo"
    assert org["product_truth"]["director"]["agent"] == "quality_director"
    assert any(w["agent"] == "validator" for w in org["product_truth"]["workers"])
    assert rows["validator"]["heartbeat"] is None                 # never ran: not invented


def test_f729_restarts_experiments_improvements_and_idle_departments():
    db = _db()
    with db.session() as s:
        _job(s, "finance.governor", "cfo", attempts=2)              # recovered on retry
        _job(s, "radar.scan", "market_radar", status=JobStatus.PENDING,
             run_after=NOW - timedelta(minutes=5))                 # ready, never worked
        s.add(RegisteredExperiment(key="e1", hypothesis="h", state="running"))
        s.add(Improvement(cell="pricing", metric="m", hypothesis="h", state="promoted",
                          promoted_at=NOW - timedelta(days=1)))
        s.add(Improvement(cell="pricing", metric="m", hypothesis="h2", state="reverted",
                          promoted_at=NOW - timedelta(days=2), reverted_at=NOW - timedelta(days=1)))
    rows = _items(X.autonomy_health(db, auto={"items": []}, owner={"open_actions": 0}))
    assert rows["restarts_recovered_24h"]["value"] == 1
    assert rows["experiments"]["by_state"] == {"running": 1}
    assert rows["improvements_7d"] == {"metric": "improvements_7d", "promoted": 2,
                                       "reverted": 1}
    idle = rows["unintentionally_idle_departments"]
    assert idle["departments"] == ["intelligence"] and idle["value"] == 1, idle


def test_f621_the_kpi_trend_is_per_department_per_day_and_unknown_when_empty():
    db = _db()
    assert X.kpi_trend(db)["basis"] == "unknown"
    with db.session() as s:
        _job(s, "finance.governor", "cfo", hours_ago=1, outputs={"incidents": ["a"]})
        _job(s, "finance.governor", "cfo", hours_ago=1.5, outputs={"incidents": ["b"]})
        _job(s, "finance.reconcile", "cfo", status=JobStatus.DEAD, hours_ago=2,
             err="KeyError: 'slug'")
    t = X.kpi_trend(db, now=NOW)
    fin = t["by_department"]["finance"]
    assert t["basis"] == "measured" and len(t["days"]) == 7
    assert sum(fin["useful_completions"]) == 2 and sum(fin["defect_dead_letters"]) == 1
    from brambleloop.app.command_center import company

    d = {i["department"]: i for i in company.departments(db, auto={"status": "UNKNOWN"})["items"]}
    assert d["finance"]["kpi_trend_7d"]["basis"] == "measured"
    assert sum(d["finance"]["kpi_trend_7d"]["useful_completions"]) == 2


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
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
