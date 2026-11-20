"""W4-SWARMMETRICS: starved READY work, untouched opportunities, parallelism, agents view.

Rows: F-655 (24/7 Valuable Work), F-730 (No Lost Opportunity), F-489 (Parallelism
Efficiency), F-487 (Department Health).
Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_swarmmetrics.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
sys.path.insert(0, str(ROOT.parent / "ops"))
_TMP = tempfile.mkdtemp(prefix="w4_swarmmetrics_")

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry, CoverageGap, Job, JobStatus  # noqa: E402
from brambleloop.swarm import metrics  # noqa: E402

NOW = datetime.now(timezone.utc)
_n = [0]


def _db() -> Database:
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _job(s, jt, *, status=JobStatus.PENDING, age_h=0.0, run_after_h=None, agent="orchestrator",
         **kw):
    created = NOW - timedelta(hours=age_h)
    s.add(Job(agent=agent, job_type=jt, status=status, inputs={}, created_at=created,
              run_after=(NOW + timedelta(hours=run_after_h)) if run_after_h else created, **kw))


# ---- F-655 ----------------------------------------------------------------------------------

def test_late_ready_work_with_idle_capacity_is_starved():
    from brambleloop.swarm.orchestrate import band_for

    db = _db()
    jt = "ops.heartbeat"
    kind = band_for(jt)["kind"]
    sla_h = metrics.BAND_READY_SLA_S[kind] / 3600
    with db.session() as s:
        _job(s, jt, age_h=sla_h + 1)              # late
        _job(s, jt, age_h=0.01)                   # fresh
        _job(s, jt, age_h=sla_h + 5, run_after_h=3)  # deferred: not ready
    r = metrics.starved_ready(db, worker_target=2, now=NOW)
    assert r["reading"] == "starved" and r["starved"] == 1 and r["late_ready"] == 1, r
    assert r["late_by_band"] == {kind: 1} and r["capacity_idle"] is True
    with db.session() as s:
        _job(s, jt, status=JobStatus.RUNNING, age_h=0.1)
        _job(s, jt, status=JobStatus.RUNNING, age_h=0.1)
    busy = metrics.starved_ready(db, worker_target=2, now=NOW)
    assert busy["reading"] == "queueing" and busy["starved"] == 0
    unknown = metrics.starved_ready(db, worker_target=None, now=NOW)
    assert unknown["reading"] == "UNKNOWN" and unknown["starved"] is None


def test_health_reports_starved_ready_as_a_signal():
    from brambleloop.ops import health

    assert "starved_ready" in health.SIGNALS
    db = _db()
    with db.session() as s:
        _job(s, "ops.heartbeat", age_h=200)
    with db.session() as s:
        readings = health.read(s, runner_state={"worker_target": 3}, env={}, now=NOW)
    r = next(x for x in readings if x.signal == "starved_ready")
    assert r.state == health.DEGRADED and r.evidence["starved"] == 1, r
    empty = _db()
    with empty.session() as s:
        readings = health.read(s, runner_state={"worker_target": 3}, env={}, now=NOW)
    assert next(x for x in readings if x.signal == "starved_ready").state == health.HEALTHY


# ---- F-730 ----------------------------------------------------------------------------------

def test_untouched_opportunities_are_counted_and_value_weighted():
    db = _db()
    assert metrics.untouched_opportunities(db)["reading"] == "UNKNOWN"
    old = NOW - timedelta(days=10)
    with db.session() as s:
        s.add(CoverageGap(benchmark_key="mjs", arena="a1", pod="blankets", state="uncovered",
                          score=0.8, created_at=old, updated_at=old))
        s.add(CoverageGap(benchmark_key="mjs", arena="a2", pod="toys", state="concepting",
                          score=0.9, created_at=old, updated_at=old))
        s.add(CoverageGap(benchmark_key="mjs", arena="a3", pod="toys", state="uncovered",
                          score=0.5))
    r = metrics.untouched_opportunities(db, now=NOW)
    assert r["untouched"] == 1 and r["value_weighted"] == 0.8 and r["of_gaps"] == 3, r
    assert r["top"][0]["arena"] == "a1"


# ---- F-489 ----------------------------------------------------------------------------------

def test_parallelism_reads_pool_counters_and_dedupe_hits():
    from brambleloop.queue import durable
    from brambleloop.queue.durable import DuplicateJob, JobQueue

    assert metrics.parallelism({})["utilisation"] is None
    p = metrics.parallelism({"busy_seconds": 30.0, "idle_seconds": 90.0, "worker_pool": 4,
                             "worker_target": 2})
    assert p["utilisation"] == 0.25 and p["worker_target"] == 2
    db = _db()
    before = durable.DEDUPE_HITS.get("ops.heartbeat", 0)
    q = JobQueue(db)
    q.enqueue("orchestrator", "ops.heartbeat", {}, idempotency_key="swm:1")
    try:
        q.enqueue("orchestrator", "ops.heartbeat", {}, idempotency_key="swm:1")
    except DuplicateJob:
        pass
    assert durable.DEDUPE_HITS["ops.heartbeat"] == before + 1
    assert metrics.parallelism({})["dedupe_hits_total"] >= 1


def test_runner_state_carries_busy_and_idle_seconds():
    from brambleloop.app.runner import RunnerState

    st = RunnerState()
    st.busy_seconds, st.idle_seconds = 12.0, 48.0
    d = st.to_dict()
    assert d["busy_seconds"] == 12.0 and d["idle_seconds"] == 48.0


def test_merge_delay_is_read_from_git():
    import registry as R

    repo = Path(tempfile.mkdtemp(prefix="swm_git_"))

    def g(*a, date=None):
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
        if date:
            env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, env=env)

    g("init", "-q", "-b", "main")
    (repo / "a").write_text("1")
    g("add", "a")
    g("commit", "-qm", "base", date="2026-10-01T00:00:00Z")
    g("checkout", "-qb", "lane")
    (repo / "b").write_text("2")
    g("add", "b")
    g("commit", "-qm", "lane work", date="2026-10-01T01:00:00Z")
    g("checkout", "-q", "main")
    g("merge", "--no-ff", "-qm", "merge lane", "lane", date="2026-10-01T03:30:00Z")
    git = R.git_at(repo)
    out = R.merge_delay({"branch": "lane", "integration_ref": "main"}, git)
    assert out["seconds"] == 2.5 * 3600, out
    g("checkout", "-qb", "lane2")
    (repo / "c").write_text("3")
    g("add", "c")
    g("commit", "-qm", "unmerged", date="2026-10-02T00:00:00Z")
    pending = R.merge_delay({"branch": "lane2", "integration_ref": "main"}, git)
    assert pending["seconds"] is None and "not integrated" in pending["why"]


# ---- F-487 ----------------------------------------------------------------------------------

def test_agents_view_composes_running_pending_parked_completion_and_spend():
    db = _db()
    with db.session() as s:
        _job(s, "listing.seo", agent="listing", status=JobStatus.RUNNING, age_h=0.1,
             started_at=NOW - timedelta(minutes=3))
        _job(s, "listing.seo", agent="listing", age_h=0.2)
        _job(s, "listing.seo", agent="listing", age_h=0.1, run_after_h=2)
        _job(s, "pricing.position", agent="pricing", status=JobStatus.DONE, age_h=1,
             finished_at=NOW - timedelta(minutes=30))
        s.add(CostEntry(agent="listing", amount_cad=0.12, kind="llm", purpose="x", detail={}))
    view = metrics.agents_view(db, now=NOW)
    rows = {r["agent"]: r for r in view["agents"]}
    li, pr = rows["listing"], rows["pricing"]
    assert li["running_job"]["job_type"] == "listing.seo" and li["idle"] is False
    assert li["pending_ready"] == 1 and li["pending_deferred"] == 1
    assert li["month_spend_cad"] == 0.12
    assert pr["last_completion"] and pr["idle"] is True and pr["month_spend_cad"] == 0.0
    assert "spend_basis" in view and "parked_basis" in view


def test_api_routes_expose_the_metrics():
    src = (ROOT / "src" / "brambleloop" / "app" / "main.py").read_text(encoding="utf-8")
    assert '@app.get("/api/departments")' in src
    body = src[src.index('@app.get("/api/swarm/runtime")'):src.index('@app.get("/api/departments")')]
    for key in ('"starved_ready"', '"untouched_opportunities"', '"parallelism"'):
        assert key in body, key


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
