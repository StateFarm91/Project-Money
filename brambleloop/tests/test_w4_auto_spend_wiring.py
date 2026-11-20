"""W4-AUTO: wiring requests from W4-SPEND (F-098, F-310, F-659).

* F-098 -- a model-needing job is parked (pending, attempt not counted, audited `ai.parked`)
  while the model provider is measurably down, instead of failing and burning its retries.
  An unprobed provider is unknown, not down, and parks nothing.
* F-310 -- the thrash sweep's progress measure counts new durable evidence rows, so a job
  whose outputs read the same but which recorded a new observation is not backed off.
* F-659 -- `JobContext.checkpoint/restore`: a reclaimed or retried job resumes from its last
  checkpoint without repeating its steps; a stale worker cannot overwrite it; completion
  clears it. Paid-call replay (F-307/F-339) is untouched.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus  # noqa: E402
from brambleloop.gateway import failover  # noqa: E402
from brambleloop.queue import checkpoints  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import worker as worker_mod  # noqa: E402
from brambleloop.runtime.worker import (CADENCES, MODEL_JOB_TYPES, PARKED_ACTION,  # noqa: E402
                                        HandlerRegistry, Worker)
from brambleloop.swarm import orchestrate  # noqa: E402


def boot() -> Database:
    tmp = tempfile.mkdtemp(prefix="w4auto-spend-")
    db = Database(f"sqlite:///{tmp}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


AGENT_OF = {jt: agent for _n, agent, jt, _p in CADENCES}


def _model_type() -> tuple[str, str]:
    jt = "seasonal.cycle_proof"
    assert jt in MODEL_JOB_TYPES and jt in AGENT_OF
    return AGENT_OF[jt], jt


def _counting_registry(calls: list, job_type: str) -> HandlerRegistry:
    hr = HandlerRegistry()

    @hr.register(job_type)
    def _h(ctx):
        calls.append(ctx.job.id)
        raise RuntimeError("Your credit balance is too low to access the Anthropic API")

    return hr


def _down(db) -> None:
    for _ in range(failover.DOWN_AFTER_CONSECUTIVE):
        failover.record_attempt(db, provider="anthropic", model="m", ok=False,
                                error=RuntimeError("503 overloaded"))


def test_model_job_parks_while_the_provider_is_down():
    db = boot()
    agent, jt = _model_type()
    _down(db)
    job = JobQueue(db).enqueue(agent, jt, {"x": 1})
    calls: list = []
    w = Worker(db, "w", registry=_counting_registry(calls, jt))
    assert w.run_once() is True
    assert calls == [], "the handler ran (and would have burned a retry) during an outage"
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.PENDING, row.status
        assert int(row.attempts or 0) == 0, row.attempts
        assert row.leased_by is None
        ra = row.run_after if row.run_after.tzinfo else row.run_after.replace(
            tzinfo=timezone.utc)
        assert ra > datetime.now(timezone.utc), "a parked job must wait for the breaker"
        audits = list(s.scalars(select(AuditLog).where(AuditLog.action == PARKED_ACTION)))
    assert len(audits) == 1 and audits[0].job_id == job.id, audits
    assert audits[0].detail["source"] == "failover", audits[0].detail
    assert w.stats.parked == 1 and w.stats.failed == 0
    print("OK test_model_job_parks_while_the_provider_is_down")


def test_unprobed_provider_is_unknown_not_down_and_parks_nothing():
    db = boot()
    assert worker_mod.model_provider_down(db) == {"down": False}
    agent, jt = _model_type()
    JobQueue(db).enqueue(agent, jt, {"x": 2})
    calls: list = []
    w = Worker(db, "w", registry=_counting_registry(calls, jt))
    w.run_once()
    assert len(calls) == 1, "with no evidence of an outage the job must run as before"
    assert w.stats.parked == 0
    print("OK test_unprobed_provider_is_unknown_not_down_and_parks_nothing")


def test_non_model_job_is_never_parked():
    db = boot()
    _down(db)
    jt = "ops.heartbeat"
    assert jt not in MODEL_JOB_TYPES and "model.probe" not in MODEL_JOB_TYPES
    JobQueue(db).enqueue(AGENT_OF[jt], jt, {})
    hr = HandlerRegistry()
    ran: list = []

    @hr.register(jt)
    def _h(ctx):
        ran.append(1)
        return {"ok": True}

    w = Worker(db, "w", registry=hr)
    w.run_once()
    assert ran == [1] and w.stats.completed == 1 and w.stats.parked == 0
    print("OK test_non_model_job_is_never_parked")


def test_failed_probe_and_spent_balance_are_outage_evidence():
    db = boot()
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action="model.probe",
                       detail={"ok": False, "error": "credit balance is too low"}))
    d = worker_mod.model_provider_down(db)
    assert d["down"] and d["source"] in {"probe", "funding"}, d
    print("OK test_failed_probe_and_spent_balance_are_outage_evidence")


def test_long_parked_job_runs_and_reports_its_own_refusal():
    db = boot()
    agent, jt = _model_type()
    _down(db)
    job = JobQueue(db).enqueue(agent, jt, {"x": 3})
    with db.session() as s:
        s.get(Job, job.id).created_at = (datetime.now(timezone.utc)
                                         - timedelta(seconds=worker_mod.MAX_PARK_SECONDS + 60))
    calls: list = []
    w = Worker(db, "w", registry=_counting_registry(calls, jt))
    w.run_once()
    assert calls == [job.id], "an outage nobody fixes for a day must surface, not park forever"
    print("OK test_long_parked_job_runs_and_reports_its_own_refusal")


def _done_job(db, jt: str, outputs: dict, evidence: list[dict], when: datetime) -> int:
    with db.session() as s:
        j = Job(agent="orchestrator", job_type=jt, inputs={"cadence": "c"}, outputs=outputs,
                status=JobStatus.DONE, created_at=when, finished_at=when)
        s.add(j)
        s.flush()
        for ev in evidence:
            s.add(AuditLog(actor="orchestrator", action=ev["action"], artifact=ev.get("a"),
                           job_id=j.id, detail=ev.get("d") or {}))
        s.add(AuditLog(actor="orchestrator", action=f"job.completed:{jt}", job_id=j.id))
        return j.id


def test_progress_counts_new_evidence_rows_and_ignores_restatements():
    db = boot()
    now = datetime.now(timezone.utc)
    n = orchestrate.IDENTICAL_STATES
    assert n >= 2
    # same outputs every run, but each run records a NEW observation
    for i in range(n):
        _done_job(db, "radar.scan", {"scored": 0}, [{"action": "radar.observation",
                                                     "a": f"sig-{i}", "d": {"v": i}}],
                  now - timedelta(minutes=n - i))
    # same outputs and the SAME evidence row restated every run (the first run's row is
    # genuinely new; the n restatements after it are not)
    for i in range(n + 1):
        _done_job(db, "culture.sweep", {"read": 0}, [{"action": "culture.reading",
                                                      "a": "same", "d": {"v": 1}}],
                  now - timedelta(minutes=n + 1 - i))
    with db.session() as s:
        prog = orchestrate._progress(s, since=now - timedelta(hours=1))
    assert prog, "no progress rows"
    radar, culture = prog["radar.scan"], prog["culture.sweep"]
    assert radar["new_evidence_rows"] == n and not radar["identical_tail"], radar
    assert radar["state_changes"] == n - 1, radar
    assert culture["new_evidence_rows"] == 1, culture
    assert culture["identical_tail"], "a restated row is not new evidence"
    print("OK test_progress_counts_new_evidence_rows_and_ignores_restatements")


def test_bookkeeping_audits_are_not_evidence():
    assert "job." in orchestrate.EVIDENCE_EXCLUDED_PREFIXES
    assert PARKED_ACTION.startswith(orchestrate.EVIDENCE_EXCLUDED_PREFIXES)
    assert "paid_call.replayed".startswith(orchestrate.EVIDENCE_EXCLUDED_PREFIXES)
    print("OK test_bookkeeping_audits_are_not_evidence")


def test_checkpoint_resumes_after_reclaim_without_repeating_steps():
    db = boot()
    q = JobQueue(db, lease_seconds=1)
    jt = "ops.heartbeat"
    job = q.enqueue(AGENT_OF[jt], jt, {})
    steps_run: list[str] = []
    hr = HandlerRegistry()
    crash = {"on": True}

    @hr.register(jt)
    def _h(ctx):
        for step in ("render", "judge", "file"):
            if ctx.restore(step) is not None:
                continue
            steps_run.append(step)
            ctx.checkpoint(step, {"done": step})
            if step == "judge" and crash["on"]:
                crash["on"] = False
                raise RuntimeError("worker died mid-job")
        return {"ok": True, "resumed": ctx.restore("render") is not None}

    w = Worker(db, "w", registry=hr)
    w.run_once()  # attempt 1 dies after judge
    assert steps_run == ["render", "judge"], steps_run
    assert set(checkpoints.all_for(db, job.id)) == {"render", "judge"}
    with db.session() as s:
        s.get(Job, job.id).run_after = datetime.now(timezone.utc) - timedelta(seconds=1)
    w.run_once()  # attempt 2 resumes
    assert steps_run == ["render", "judge", "file"], ("a step was repeated", steps_run)
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, (row.status, row.last_error)
        assert row.outputs["resumed"] is True
    assert checkpoints.all_for(db, job.id) == {}, "completion must clear checkpoints"
    print("OK test_checkpoint_resumes_after_reclaim_without_repeating_steps")


def test_stale_worker_cannot_overwrite_a_checkpoint():
    db = boot()
    q = JobQueue(db)
    job = q.enqueue("orchestrator", "ops.heartbeat", {})
    claimed = q.claim("w1")
    assert claimed is not None and claimed.id == job.id
    q.checkpoint(job.id, "step", {"v": 1}, lease_token=claimed.lease_token)
    try:
        q.checkpoint(job.id, "step", {"v": 2}, lease_token="not-the-current-token")
    except checkpoints.CheckpointRefused:
        pass
    else:
        raise AssertionError("a stale lease token overwrote the checkpoint")
    got = q.restore(job.id, "step")
    assert got is not None and got["v"] == 1, got
    assert q.restore(job.id, "never") is None
    print("OK test_stale_worker_cannot_overwrite_a_checkpoint")


TESTS = [
    test_model_job_parks_while_the_provider_is_down,
    test_unprobed_provider_is_unknown_not_down_and_parks_nothing,
    test_non_model_job_is_never_parked,
    test_failed_probe_and_spent_balance_are_outage_evidence,
    test_long_parked_job_runs_and_reports_its_own_refusal,
    test_progress_counts_new_evidence_rows_and_ignores_restatements,
    test_bookkeeping_audits_are_not_evidence,
    test_checkpoint_resumes_after_reclaim_without_repeating_steps,
    test_stale_worker_cannot_overwrite_a_checkpoint,
]

if __name__ == "__main__":
    assert TESTS
    failed = 0
    for t in TESTS:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL {t.__name__}: {e}")
    print(f"{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
