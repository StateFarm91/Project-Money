"""Certification repairs for the improvement cluster (defects C-62, C-63).

Rows 53, 90, 92, 93, 95, 96, 97, 99, 100, 129, 147, 153-161, 164, 174, 176, 179, 180, 187,
190, 193, 194, 220, 228, 231. Every test drives a registered handler with a real JobContext on
a file database, seeded with real rows, and asserts the downstream effect -- a row moved, a
configuration promoted and rolled back, a gate that refuses, an enqueue that changed -- rather
than a library's return value.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp(prefix="cert_wave_improve_")
    db = Database(f"sqlite:///{tmp}/w.sqlite")
    db.create_all()
    from brambleloop.agents.registry import Registry

    Registry(db).seed_defaults()
    from brambleloop.swarm.orchestrate import clear_policy_cache

    clear_policy_cache()
    return db


_N = [0]


def _ctx(db, job_type: str, agent: str = "orchestrator", inputs: dict | None = None):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Phase
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline, release  # noqa: F401 -- registers handlers
    from brambleloop.runtime.worker import JobContext

    q = JobQueue(db)
    _N[0] += 1
    job = q.enqueue(agent, job_type, inputs or {}, idempotency_key=f"wi:{job_type}:{_N[0]}")
    return JobContext(job=job, db=db, queue=q, registry=Registry(db), phase=Phase.SHADOW)


def _run(db, job_type: str, agent: str = "orchestrator", inputs: dict | None = None) -> dict:
    from brambleloop.runtime import pipeline, release  # noqa: F401
    from brambleloop.runtime.worker import handlers

    handler = handlers.get(job_type)
    assert handler is not None, f"no handler registered for {job_type!r}"
    return handler(_ctx(db, job_type, agent, inputs))


def _scheduled(job_type: str, agent: str) -> None:
    """The job type is on a cadence, granted to its agent and banded."""
    from brambleloop.agents.registry import DEFAULT_AGENTS
    from brambleloop.runtime.worker import CADENCES
    from brambleloop.swarm.orchestrate import JOB_BANDS

    assert any(jt == job_type and a == agent for _n, a, jt, _p in CADENCES), job_type
    spec = next(a for a in DEFAULT_AGENTS if a["name"] == agent)
    assert job_type in spec["allowed_job_types"], (agent, job_type)
    assert job_type in JOB_BANDS, job_type


def _seed_contention(db, *, days: int = 5, start_days_ago: int = 6) -> None:
    """Each day a burst of ten equal-band jobs: five valuable and unhurried enqueued first,
    five worth nothing with a three-hour deadline behind them. One hour of work each."""
    from brambleloop.core.models import Job, JobStatus

    now = datetime.now(timezone.utc)
    with db.session() as s:
        for d in range(days):
            t0 = (now - timedelta(days=start_days_ago - d)).replace(hour=1, minute=0,
                                                                    second=0, microsecond=0)
            for i in range(10):
                urgent = i >= 5
                inputs = ({"deadline": (t0 + timedelta(hours=3)).isoformat()} if urgent else
                          {"deadline": (t0 + timedelta(days=25)).isoformat(),
                           "value_cad": 500})
                s.add(Job(agent="orchestrator", job_type="improve.nightly", inputs=inputs,
                          priority=85, status=JobStatus.DONE, created_at=t0,
                          run_after=t0, started_at=t0, finished_at=t0 + timedelta(hours=1)))


def _improvement(db, iid):
    from brambleloop.core.models import Improvement

    with db.session() as s:
        r = s.get(Improvement, iid)
        return r.state, dict(r.evidence or {}), r.baseline_value, r.result_value


# ---------------------------------------------------------------------------
# #95 #180 #193 #187 #92 #90 #93 #100 #190: replay -> league runs -> sandbox -> promote ->
# execute (the runtime reads it) -> monitor -> rollback


def test_replay_produces_league_runs_and_waits_honestly_without_history():
    _scheduled("improve.replay", "orchestrator")
    db = _db()
    out = _run(db, "improve.replay")
    assert out["ran"] is False and out["reading"] == "UNMEASURED"
    from brambleloop.core.models import AuditLog

    with db.session() as s:
        assert s.scalar(select(AuditLog).where(AuditLog.action == "improve.league.run")) is None


def test_a_replayed_challenger_is_sandboxed_promoted_executed_and_rolled_back():
    from brambleloop.core.models import AuditLog, ConfigVersion, Incident, Job
    from brambleloop.improve import league
    from brambleloop.queue.durable import JobQueue
    from brambleloop.swarm import orchestrate

    db = _db()
    _seed_contention(db)

    # 1. The cadence replays history: incumbent and six neighbours, runs recorded.
    out = _run(db, "improve.replay")
    assert out["ran"] and out["jobs"] == 50 and out["days"] == 5
    assert len(out["challengers_registered"]) == 6
    with db.session() as s:
        runs = list(s.scalars(select(AuditLog).where(AuditLog.action == "improve.league.run")))
    assert len(runs) == 7
    assert all(r.detail["holdout"] for r in runs), "the newest day is held out"
    assert len(out["proposed"]) == 1, out["compared"]
    iid = out["proposed"][0]["improvement"]
    state, ev, baseline, _ = _improvement(db, iid)
    assert state == "proposed" and baseline == 0.5
    assert ev["proposed_by"] == "prompt_tool_challenger"
    assert ev["sandbox_trial"] == "league_replay"
    losers = {r["config_id"] for r in out["retired"]}
    with db.session() as s:
        assert all(s.get(ConfigVersion, c).retired_at is not None for c in losers)

    # 2. The league judges the same runs and leaves the promotion to the sandbox that owns it.
    league_out = _run(db, "improve.league")
    assert any(h.get("route") == "sandbox" for h in league_out["held"]), league_out

    # 3. The sandbox: trial, regression + adversarial, the evaluator approves, the scoring tier
    #    auto-promotes, and the promotion executes: the challenger is the registry incumbent.
    sandbox = _run(db, "improve.sandbox")
    assert [x["improvement"] for x in sandbox["promoted"]] == [iid], sandbox
    state, ev, baseline, result = _improvement(db, iid)
    assert state == "promoted" and result > baseline
    assert ev["approved_by"] == "evaluator" and ev["executed"]
    challenger = ev["change"]["config_id"]
    with db.session() as s:
        assert s.get(ConfigVersion, challenger).incumbent is True
        assert s.get(ConfigVersion, ev["change"]["replaces"]).incumbent is False

    # 4. Acted on: the next enqueue is prioritised by the promoted policy.
    orchestrate.clear_policy_cache()
    policy = orchestrate.priority_policy(db)
    assert policy["config_id"] == challenger
    q = JobQueue(db)
    soon = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    urgent = q.enqueue("orchestrator", "improve.nightly", {"deadline": soon})
    rich = q.enqueue("orchestrator", "improve.nightly",
                     {"deadline": (datetime.now(timezone.utc) + timedelta(days=26)).isoformat(),
                      "value_cad": 500})
    assert urgent.priority < rich.priority, (urgent.priority, rich.priority)

    # 5. Monitor: a fresh window replayed since the promotion reads worse -> reverted, the
    #    previous version restored, a rollback incident opened.
    replaced = ev["change"]["replaces"]
    league.record_run(db, replaced, tasks={"day:x1": 0.9, "day:x2": 0.9}, cost_cad=0.0,
                      reliability=1.0, run_ref="replay:aaaaaaaaaaaa:fresh..fresh:20",
                      recorded_by="prompt_tool_challenger")
    league.record_run(db, challenger, tasks={"day:x1": 0.4, "day:x2": 0.4}, cost_cad=0.0,
                      reliability=1.0, run_ref="replay:bbbbbbbbbbbb:fresh..fresh:20",
                      recorded_by="prompt_tool_challenger")
    mon = _run(db, "improve.monitor")
    assert iid in mon["reverted"], mon
    assert _improvement(db, iid)[0] == "reverted"
    with db.session() as s:
        assert s.get(ConfigVersion, replaced).incumbent is True
        assert s.get(ConfigVersion, challenger).incumbent is False
        assert s.scalar(select(Incident).where(
            Incident.signature == f"improve-rollback:{iid}")) is not None
    orchestrate.clear_policy_cache()
    assert orchestrate.priority_policy(db)["config_id"] == replaced


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            t0 = time.monotonic()
            try:
                fn()
                print(f"OK   {name} ({time.monotonic() - t0:.1f}s)")
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback

                traceback.print_exc()
                print(f"FAIL {name}: {type(e).__name__}: {str(e)[:600]}")
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
