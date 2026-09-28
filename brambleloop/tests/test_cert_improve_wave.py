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


def _seed_contention(db, *, days: int = 5, start_days_ago: int = 6,
                     workers: tuple[str, ...] = ("",)) -> None:
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
                          run_after=t0, started_at=t0, finished_at=t0 + timedelta(hours=1),
                          leased_by=workers[i % len(workers)] or None))


def _post_promotion_dataset(tag: str, *, days_ahead: int = 1) -> tuple[dict, dict]:
    """A dataset observed wholly after now, with two whole days of dated tasks."""
    now = datetime.now(timezone.utc)
    d1 = (now + timedelta(days=days_ahead)).date().isoformat()
    d2 = (now + timedelta(days=days_ahead + 1)).date().isoformat()
    dataset = {"fingerprint": f"fresh-{tag}", "jobs": 20,
               "bounds": [(now + timedelta(days=days_ahead)).isoformat(),
                          (now + timedelta(days=days_ahead + 1, hours=6)).isoformat()]}
    return dataset, {f"day:{d1}": None, f"day:{d2}": None}


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
    _fresh_worse_runs(db, replaced, challenger)
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


def _promote_replay_challenger(db) -> tuple[int, int, int]:
    """Replay, sandbox and promote one job-priority challenger; (improvement, new, old)."""
    _seed_contention(db)
    out = _run(db, "improve.replay")
    iid = out["proposed"][0]["improvement"]
    sandbox = _run(db, "improve.sandbox")
    assert [x["improvement"] for x in sandbox["promoted"]] == [iid], sandbox
    _state, ev, _b, _r = _improvement(db, iid)
    return iid, int(ev["change"]["config_id"]), int(ev["change"]["replaces"])


def _fresh_worse_runs(db, replaced: int, challenger: int, *, tag: str = "fresh",
                      old_q: float = 0.9, new_q: float = 0.4) -> None:
    """Runs on a dataset observed after the promotion where the promoted policy reads worse."""
    from brambleloop.improve import league, replay

    dataset, days = _post_promotion_dataset(tag)
    league.record_run(db, replaced, tasks={d: old_q for d in days}, cost_cad=0.0,
                      reliability=1.0, run_ref=f"replay:aaaaaaaaaaaa:{tag}..{tag}:20",
                      recorded_by="prompt_tool_challenger", dataset=dataset,
                      simulator=replay.SIMULATOR)
    league.record_run(db, challenger, tasks={d: new_q for d in days}, cost_cad=0.0,
                      reliability=1.0, run_ref=f"replay:bbbbbbbbbbbb:{tag}..{tag}:20",
                      recorded_by="prompt_tool_challenger", dataset=dataset,
                      simulator=replay.SIMULATOR)


def test_a_rollback_killed_between_deciding_and_executing_is_resumed_not_lost():
    """C-81 (Codex M01): REVERTED is written only after the rollback effect is verified.

    The process is killed twice -- once before the executor runs, once after it ran but
    before verification -- and each restart resumes the pending rollback. Until the active
    policy is shown restored the row stays PROMOTED with `rollback_pending`, the incident
    stays open, and nothing re-judges or re-executes the promotion.
    """
    from brambleloop.core.models import ConfigVersion, Incident
    from brambleloop.improve import runner
    from brambleloop.swarm import orchestrate

    db = _db()
    iid, challenger, replaced = _promote_replay_challenger(db)
    _fresh_worse_runs(db, replaced, challenger)
    signature = f"improve-rollback:{iid}"

    def _rollback_state():
        state, ev, _b, _r = _improvement(db, iid)
        with db.session() as s:
            inc = s.scalar(select(Incident).where(Incident.signature == signature))
            active = s.get(ConfigVersion, challenger).incumbent
        return state, ev.get("rollback_pending"), ev.get("rollback"), inc, active

    real = runner.ROLLBACKS["league_replay"]

    def killed_before_executing(db_, iid_, *, why):
        raise RuntimeError("killed before the rollback executor ran")

    def killed_after_executing(db_, iid_, *, why):
        real(db_, iid_, why=why)
        raise RuntimeError("killed after the executor and before verification")

    # Kill 1: decided, incident opened, executor never ran.
    runner.ROLLBACKS["league_replay"] = killed_before_executing
    try:
        try:
            _run(db, "improve.monitor")
        except RuntimeError:
            pass
        state, pending, done, inc, active = _rollback_state()
        assert state == "promoted" and done is None, "REVERTED was written before the effect"
        assert pending and pending["attempts"] == 1 and pending["because"]
        assert active is True, "the challenger is still the incumbent; nothing rolled back"
        assert inc is not None and inc.resolved is False
        assert inc.detail["rollback_state"] == "pending"

        # Restart 1, same fault: resumed (attempt 2), not re-judged, still pending.
        windows_before = _improvement(db, iid)[1].get("monitored_windows")
        try:
            _run(db, "improve.monitor")
        except RuntimeError:
            pass
        state, pending, done, inc, active = _rollback_state()
        assert state == "promoted" and pending["attempts"] == 2 and active is True
        assert _improvement(db, iid)[1].get("monitored_windows") == windows_before

        # Kill 2: the executor restored the previous version, then the process died before
        # verification. The effect is there, the row still honestly says pending.
        runner.ROLLBACKS["league_replay"] = killed_after_executing
        try:
            _run(db, "improve.monitor")
        except RuntimeError:
            pass
        state, pending, done, inc, active = _rollback_state()
        assert state == "promoted" and pending["attempts"] == 3 and inc.resolved is False
        assert active is False, "the executor did run before the kill"
    finally:
        runner.ROLLBACKS["league_replay"] = real

    # Restart 2, healthy: the idempotent executor finds the version already restored, the
    # verifier reads the registry and the live policy, and only now is REVERTED written.
    mon = _run(db, "improve.monitor")
    assert iid in mon["reverted"] and iid not in mon["rollback_pending"], mon
    state, pending, done, inc, active = _rollback_state()
    assert state == "reverted" and pending is None
    assert done["attempts"] == 4 and done["verified"]["verified"] is True
    assert done["verified"]["active_config_id"] == replaced
    assert inc.resolved is True and inc.detail["rollback_state"] == "verified"
    assert active is False
    orchestrate.clear_policy_cache()
    assert orchestrate.priority_policy(db)["config_id"] == replaced

    # Idempotent: another pass has nothing to resume and reverts nothing.
    again = _run(db, "improve.monitor")
    assert again["reverted"] == [] and again["rollback_pending"] == []
    assert _improvement(db, iid)[0] == "reverted"


def test_a_replay_of_unchanged_history_is_never_fresh_post_promotion_evidence():
    """C-63 (Codex M03): a run timestamped after the promotion is not evidence about it
    unless its dataset is new, its observations pass the promotion, and a whole day has been
    observed since. Each non-fresh kind is recorded on the row and reverts nothing."""
    from brambleloop.core.models import ConfigVersion
    from brambleloop.improve import league, replay

    db = _db()
    iid, challenger, replaced = _promote_replay_challenger(db)
    _state, ev, _b, _r = _improvement(db, iid)
    judged_fp = ev["change"]["judged_on"]["fingerprint"]
    assert judged_fp and ev["change"]["simulator"] == replay.SIMULATOR["version"]
    now = datetime.now(timezone.utc)

    def _record(tag, *, dataset, tasks_old, tasks_new):
        for cid, tasks, d in ((replaced, tasks_old, "a"), (challenger, tasks_new, "b")):
            league.record_run(db, cid, tasks=tasks, cost_cad=0.0, reliability=1.0,
                              run_ref=f"replay:{d * 12}:{tag}:20",
                              recorded_by="prompt_tool_challenger", dataset=dataset,
                              simulator=replay.SIMULATOR)

    def _not_reverted(kind):
        mon = _run(db, "improve.monitor")
        state, ev, _b, _r = _improvement(db, iid)
        assert mon["reverted"] == [] and state == "promoted", (kind, mon)
        assert ev["not_fresh"]["kind"] == kind, ev["not_fresh"]
        with db.session() as s:
            assert s.get(ConfigVersion, challenger).incumbent is True

    worse = {"day:x": 0.4}
    better = {"day:x": 0.9}
    # 1. The same historical tasks replayed again after the promotion: the same evaluation.
    _record("again", dataset={"fingerprint": judged_fp,
                              "bounds": [(now + timedelta(days=1)).isoformat()] * 2},
            tasks_old=better, tasks_new=worse)
    _not_reverted("repeated_evaluation")
    # 2. A new dataset whose every observation predates the promotion.
    _record("old", dataset={"fingerprint": "older-history",
                            "bounds": [(now - timedelta(days=9)).isoformat(),
                                       (now - timedelta(days=8)).isoformat()]},
            tasks_old=better, tasks_new=worse)
    _not_reverted("predates_promotion")
    # 3. A run that says nothing about what it was scored on.
    for cid, tasks, d in ((replaced, better, "c"), (challenger, worse, "d")):
        league.record_run(db, cid, tasks=tasks, cost_cad=0.0, reliability=1.0,
                          run_ref=f"replay:{d * 12}:blank..blank:20",
                          recorded_by="prompt_tool_challenger")
    _not_reverted("unbounded")
    # 4. Fresh bounds, but the only dated task is the promotion day itself: not a whole day.
    today = f"day:{now.date().isoformat()}"
    _record("partial", dataset={"fingerprint": "reaches-past",
                                "bounds": [(now - timedelta(days=1)).isoformat(),
                                           (now + timedelta(hours=2)).isoformat()]},
            tasks_old={today: 0.9}, tasks_new={today: 0.4})
    mon = _run(db, "improve.monitor")
    assert mon["reverted"] == [] and _improvement(db, iid)[0] == "promoted"
    # 5. Two whole days observed after the promotion: judged, and worse -> reverted.
    _fresh_worse_runs(db, replaced, challenger)
    mon = _run(db, "improve.monitor")
    assert iid in mon["reverted"], mon
    state, ev, _b, _r = _improvement(db, iid)
    assert state == "reverted" and ev["monitoring"]["dataset"] == "fresh-fresh"
    assert len(ev["monitoring"]["tasks"]) == 2 and ev["monitoring"]["observed"] == 0.4


def test_the_replay_scopes_its_claim_to_the_simulator_it_ran():
    """C-63 / C-68 (Codex M02): the simulator's assumptions are versioned on every run, a
    history produced by a worker pool the simulator does not model proposes nothing, and a
    DEAD job keeps its failure meaning."""
    from brambleloop.core.models import AuditLog, Job, JobStatus
    from brambleloop.improve import replay

    db = _db()
    _seed_contention(db, workers=("worker-1", "worker-2"))
    out = _run(db, "improve.replay")
    assert out["ran"] and out["simulator"] == replay.SIMULATOR["version"]
    assert out["dataset"]["workers_observed"] == 2 and out["dataset"]["fingerprint"]
    assert out["fidelity"]["comparable"] is False and out["fidelity"]["reasons"]
    assert out["compared"] and any(c["promote"] for c in out["compared"])
    assert out["proposed"] and "does not model" in out["proposed"][0]["refused"]
    with db.session() as s:
        runs = list(s.scalars(select(AuditLog).where(AuditLog.action == "improve.league.run")))
    assert len(runs) == 7
    assert all(r.detail["simulator"]["version"] == replay.SIMULATOR["version"]
               and r.detail["dataset"]["fingerprint"] == out["dataset"]["fingerprint"]
               for r in runs)
    sandbox = _run(db, "improve.sandbox")
    assert sandbox["promoted"] == [] and sandbox["sandboxed"] == []

    # A dead job occupies the worker and is never on time, so the day it died reads worse
    # than the same day with it finished -- the failure is kept in the metric.
    db2 = _db()
    _seed_contention(db2)
    now = datetime.now(timezone.utc)
    t0 = (now - timedelta(days=6)).replace(hour=0, minute=30, second=0, microsecond=0)
    with db2.session() as s:
        s.add(Job(agent="orchestrator", job_type="improve.nightly",
                  inputs={"deadline": (t0 + timedelta(days=25)).isoformat()}, priority=85,
                  status=JobStatus.DEAD, created_at=t0, run_after=t0, started_at=t0,
                  finished_at=t0 + timedelta(hours=1), last_error="boom"))
    out2 = _run(db2, "improve.replay")
    assert out2["dataset"]["dead_jobs"] == 1 and out2["fidelity"]["dead_jobs"] == 1
    with db2.session() as s:
        inc_run = next(r for r in s.scalars(select(AuditLog).where(
            AuditLog.action == "improve.league.run")) if r.detail["config_id"] == out2["incumbent"])
    day_with_dead = f"day:{t0.date().isoformat()}"
    other_days = [v for k, v in inc_run.detail["tasks"].items() if k != day_with_dead]
    assert inc_run.detail["tasks"][day_with_dead] < min(other_days), inc_run.detail["tasks"]


def test_the_nightly_sweep_runs_challenger_evaluations_rather_than_counting_them():
    _scheduled("improve.nightly", "orchestrator")
    from brambleloop.core.models import AuditLog

    db = _db()
    _seed_contention(db)
    out = _run(db, "improve.nightly")
    from brambleloop.improve import nightly

    stage = out["delta"]["stages"][nightly.CHALLENGERS]
    with db.session() as s:
        runs = list(s.scalars(select(AuditLog).where(AuditLog.action == "improve.league.run")))
    assert len(runs) == 7, len(runs)
    assert stage["detail"]["evaluated"]["compared"] == 6, stage


# ---------------------------------------------------------------------------
# #153-#161 #164 #155 (Pattern Help): findings -> enforced requirements -> the self-audit trial


def _benchmark_and_product(db, slug: str = "fixture-good") -> None:
    from brambleloop.core.models import BenchmarkProduct, PatternVersion, Product

    with db.session() as s:
        s.add(BenchmarkProduct(ref="bench-1", seller="SyntheticShop", category="blanket",
                               files=[{"name": "p.pdf", "role": "pattern_pdf", "bytes": 3,
                                       "sha256": "0" * 64}]))
        p = Product(slug=slug, title="Fixture", status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={}, certified=True,
                             release_hash="a" * 64, certificate={
                                 "granted": True, "findings": [],
                                 "stages_run": ["compile", "specification", "reverse"]}))


def _beginner(error_recovery: int, *, mechanism: str = "") -> dict:
    from brambleloop.teardown.audits import BY_KEY

    answers = {e: 3 for e in BY_KEY["beginner_experience"].element_keys}
    answers["error_recovery"] = {"score": error_recovery, "mechanism": mechanism or (
        "the document gives no route back when a count goes wrong late in the work")}
    return answers


def _publish_gate_reasons(db, slug: str) -> list[str]:
    from brambleloop.core.models import AuditLog
    from brambleloop.runtime.pipeline import ShadowModeRefusal

    try:
        _run(db, "store.publish", agent="store_operator",
             inputs={"slug": slug, "version": "1.0.0"})
    except ShadowModeRefusal:
        pass
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "store.release_gates")
                       .order_by(AuditLog.id.desc()))
        return list((row.detail or {}).get("reasons") or [])


def test_a_teardown_trap_is_enforced_routed_to_pattern_help_and_promoted_on_our_self_audit():
    _scheduled("teardown.enforce", "orchestrator")
    from brambleloop.core.models import Incident, SupportCase, TeardownFinding
    from brambleloop.teardown import lab

    db = _db()
    _benchmark_and_product(db)

    # #161: confidence and raw notes are captured on the row.
    rec = lab.record_audit(db, "bench-1", "beginner_experience", _beginner(1),
                           confidence=0.8, raw_notes="late-row errors have no recovery path")
    [fid] = rec["findings_recorded"]
    with db.session() as s:
        f = s.get(TeardownFinding, fid)
        assert f.confidence == 0.8 and "recovery" in f.raw_notes
    iid = rec["promotions"][0]["improvement"]
    state, ev, baseline, _ = _improvement(db, iid)
    assert state == "proposed" and baseline is None and ev["sandbox_trial"] == "self_audit"

    # The enforcement cadence: a binding `prevent` requirement, our product unmeasured on it.
    out = _run(db, "teardown.enforce")
    assert out["binding"] >= 1 and "fixture-good" in out["blocked"]
    assert out["pattern_help"] and out["lessons"]
    # ...and the publish gate refuses on it (#155 PDF consumer).
    reasons = _publish_gate_reasons(db, "fixture-good")
    assert any("beginner_experience:error_recovery" in r for r in reasons), reasons

    # Pattern Help (#155): an open case about the trap is routed to the pattern_help specialist.
    with db.session() as s:
        s.add(SupportCase(customer_ref="c1", question="I made a mistake and need to undo rows"))
    triage = _run(db, "support.triage", agent="support")
    assert triage["pattern_help"]["routed"], triage["pattern_help"]
    with db.session() as s:
        case = s.scalar(select(SupportCase))
        assert case.specialist == "pattern_help" and case.detail["pattern_help"]

    # #164 the sandbox: no self-audit yet -> waits; the first self-audit becomes the baseline.
    first = _run(db, "improve.sandbox")
    assert any(w["improvement"] == iid for w in first["waiting_detail"])
    lab.record_audit(db, "brambleloop:fixture-good", "beginner_experience", _beginner(2))
    anchored = _run(db, "improve.sandbox")
    assert [a["improvement"] for a in anchored["anchored"]] == [iid]
    assert _improvement(db, iid)[2] == 2.0
    # A later self-audit that beat it: tested, approved, promoted (prompt tier), executed.
    lab.record_audit(db, "brambleloop:fixture-good", "beginner_experience", _beginner(
        4, mechanism="every late-row error now has a numbered recovery step and a checkpoint"))
    done = _run(db, "improve.sandbox")
    assert [p["improvement"] for p in done["promoted"]] == [iid], done
    assert done["executed"] and done["executed"][0]["floor"] == 4.0
    with db.session() as s:
        assert s.get(TeardownFinding, fid).detail["adopted"]["floor"] == 4.0
    assert not any("error_recovery" in r for r in _publish_gate_reasons(db, "fixture-good"))

    # #93: a self-audit after promotion that reads below the baseline reverts it and drops
    # the floor, with a rollback incident.
    lab.record_audit(db, "brambleloop:fixture-good", "beginner_experience", _beginner(1))
    mon = _run(db, "improve.monitor")
    assert iid in mon["reverted"], mon
    with db.session() as s:
        assert "adopted" not in s.get(TeardownFinding, fid).detail
        assert s.scalar(select(Incident).where(
            Incident.signature == f"improve-rollback:{iid}")) is not None


def test_self_audits_bind_to_the_release_they_read_and_keywords_are_only_structural():
    """C-66 / C-67 (Codex M07): a self-audit certifies the release it audited and nothing
    later; a keyword in the shop package is a structural check, never semantic clarity."""
    from brambleloop.core.models import PatternVersion, TeardownFinding
    from brambleloop.teardown import enforce, lab
    from brambleloop.teardown.audits import BY_KEY

    db = _db()
    _benchmark_and_product(db)
    lab.record_audit(db, "bench-1", "beginner_experience", _beginner(1), confidence=0.9)
    # Our self-audit of release a...: the gate stops refusing on the trap.
    rec = lab.record_audit(db, "brambleloop:fixture-good", "beginner_experience", _beginner(4))
    with db.session() as s:
        bound = s.get(TeardownFinding, rec["findings_recorded"][0]).detail["bound_to"]
    assert bound["release_hash"] == "a" * 64 and bound["version"] == "1.0.0"
    assert not any("error_recovery" in r for r in _publish_gate_reasons(db, "fixture-good"))
    row = next(r for r in enforce.check(db, "fixture-good")["rows"]
               if r["key"] == "beginner_experience:error_recovery")
    assert row["verdict"] == "met" and row["evidence"] == "self_audit"

    # The dependency changes: a new release of the same slug. The audit of release a... is
    # stale evidence, the requirement reads unmeasured with the reason, and publish refuses.
    with db.session() as s:
        s.scalar(select(PatternVersion)).release_hash = "b" * 64
    reasons = _publish_gate_reasons(db, "fixture-good")
    assert any("error_recovery" in r and "unmeasured" in r and "another release" in r
               for r in reasons), reasons
    row = next(r for r in enforce.check(db, "fixture-good")["rows"]
               if r["key"] == "beginner_experience:error_recovery")
    assert row["stale_self_audits"] == rec["findings_recorded"] and row["ours"] is None
    # ...and the sandbox/monitor reader stops reading it too, so no floor rests on it.
    assert enforce.catalogue_scores(db, "beginner_experience:error_recovery") == []
    # A self-audit of the new release binds to it and applies again.
    lab.record_audit(db, "brambleloop:fixture-good", "beginner_experience", _beginner(4))
    assert not any("error_recovery" in r for r in _publish_gate_reasons(db, "fixture-good"))
    assert len(enforce.catalogue_scores(db, "beginner_experience:error_recovery")) == 1

    # Support and rights: benchmarks disagree about the FAQ (5 against 1) so ours must be
    # unambiguous. The shop package has a FAQ -- a keyword hit -- which is structural evidence
    # and cannot settle a clarity requirement: unmeasured, blocking, until a self-audit of
    # this release reads it strong.
    from brambleloop.core.models import BenchmarkProduct

    with db.session() as s:
        s.add(BenchmarkProduct(ref="bench-2", seller="OtherShop", category="blanket",
                               files=[{"name": "p.pdf", "role": "pattern_pdf", "bytes": 3,
                                       "sha256": "1" * 64}]))
    support = {e: 3 for e in BY_KEY["support_rights"].element_keys}
    lab.record_audit(db, "bench-1", "support_rights", {**support, "faq": {
        "score": 5, "mechanism": "every likely question is answered before purchase"}},
        confidence=0.9)
    lab.record_audit(db, "bench-2", "support_rights", {**support, "faq": {
        "score": 1, "mechanism": "no questions are answered anywhere in the package"}},
        confidence=0.9)
    assert enforce.support_text_evidence()["faq"] is True, "the keyword check does fire"
    row = next(r for r in enforce.check(db, "fixture-good", consumers=("support",))["rows"]
               if r["key"] == "support_rights:faq" and r["kind"] == "clarify")
    assert row["verdict"] == "unmeasured" and row["evidence"] == "structural_keyword", row
    assert any("support_rights:faq (clarify" in r and "structural keyword" in r
               for r in _publish_gate_reasons(db, "fixture-good"))
    lab.record_audit(db, "brambleloop:fixture-good", "support_rights", {**support, "faq": {
        "score": 4, "mechanism": "our FAQ answers each disputed question in one sentence"}})
    row = next(r for r in enforce.check(db, "fixture-good", consumers=("support",))["rows"]
               if r["key"] == "support_rights:faq" and r["kind"] == "clarify")
    assert row["verdict"] == "met" and row["evidence"] == "self_audit", row
    assert not any("support_rights:faq (clarify" in r
                   for r in _publish_gate_reasons(db, "fixture-good"))


def test_release_eligibility_is_one_record_and_clearing_one_reason_never_clears_another():
    """C-67 / C-69 (Codex M10): the teardown QA withhold, the owner's veto, the competitive
    standard and the binding teardown requirements live on one durable record that the
    certification, draft, rebuild and publish paths all read; each kind clears alone."""
    from types import SimpleNamespace

    from brambleloop.core.models import AuditLog, CompetitiveStandard, PatternVersion
    from brambleloop.intel import mission_runtime
    from brambleloop.publish import withholding
    from brambleloop.runtime import pipeline

    db = _db()
    _benchmark_and_product(db, "fixture-hold")
    cir = SimpleNamespace(slug="fixture-hold", version="1.0.0")
    ctx = _ctx(db, "gate.certify", agent="quality_director")

    def _cert():
        with db.session() as s:
            return dict(s.scalar(select(PatternVersion)).certificate or {})

    def _draft():
        return _run(db, "listing.draft", agent="listing",
                    inputs={"slug": "fixture-hold", "version": "1.0.0", "release": "a" * 64})

    # The certification path's mark (the teardown QA, #163) and the owner's veto (#228).
    pipeline._mark_withheld(ctx, cir, "teardown QA (#163): parity with every benchmark")
    mission_runtime.record_veto(db, subject_ref="product:fixture-hold",
                                scope="flagship_creative_quality", reason="generic")
    reasons = _publish_gate_reasons(db, "fixture-hold")
    assert any("release withheld (#163)" in r for r in reasons), reasons
    assert any("owner veto (#228)" in r for r in reasons), reasons
    cert = _cert()
    assert set(cert["withholding"]) == {"teardown_qa", "owner_veto"}, cert["withholding"]
    assert "teardown QA" in cert["withheld"] and "owner veto" in cert["withheld"]
    drafted = _draft()
    assert drafted["drafted"] is False
    assert "owner veto" in drafted["withheld"] and "teardown QA" in drafted["withheld"]

    # Lifting the veto clears its kind and nothing else: publish and draft still refuse on
    # the QA withhold, and the record says exactly what remains.
    mission_runtime.record_veto(db, subject_ref="product:fixture-hold",
                                scope="flagship_creative_quality", owner_vetoed=False)
    drafted = _draft()
    assert drafted["drafted"] is False and "owner veto" not in drafted["withheld"]
    assert "teardown QA" in drafted["withheld"]
    reasons = _publish_gate_reasons(db, "fixture-hold")
    assert not any("owner veto" in r for r in reasons)
    assert any("release withheld (#163)" in r for r in reasons), reasons
    cert = _cert()
    assert set(cert["withholding"]) == {"teardown_qa"} and "owner_veto" in cert["withholding_cleared"]

    # A competitive standard the listing is below (#220) is recorded under its own kind by
    # the publish gates; it withholds publication and does not stop the content being built.
    with db.session() as s:
        s.add(CompetitiveStandard(key="gallery_images", value=5.0, higher_is_better=True,
                                  history=[]))
    reasons = _publish_gate_reasons(db, "fixture-hold")
    assert any("competitive standard gallery_images" in r for r in reasons)
    cert = _cert()
    assert set(cert["withholding"]) == {"teardown_qa", "competitive_standard"}
    assert "gallery_images" in cert["withholding"]["competitive_standard"]["reason"]
    assert "competitive" not in cert["withheld"]

    # Clearing the QA withhold (a later certification that passes it) clears only that kind:
    # the draft path opens, the publish path still refuses on the competitive standard.
    pipeline._mark_withheld(ctx, cir, None)
    cert = _cert()
    assert "withheld" not in cert and set(cert["withholding"]) == {"competitive_standard"}
    drafted = _draft()
    assert drafted["drafted"] is True, drafted
    reasons = _publish_gate_reasons(db, "fixture-hold")
    assert not any("#163" in r for r in reasons)
    assert any("competitive standard gallery_images" in r for r in reasons)
    with db.session() as s:
        refused = list(s.scalars(select(AuditLog).where(
            AuditLog.action == "listing.refused_withheld")))
    assert len(refused) == 2 and all("teardown QA" in r.detail["why"] for r in refused)
    # The record reports itself for any reader.
    view = withholding.reasons(db, "fixture-hold", "1.0.0")
    assert view["blocks_publish"] and not view["blocks_build"] and view["summary"] is None


def test_owner_veto_and_competitive_standard_block_at_the_gates():
    from brambleloop.core.models import (AuditLog, CompetitiveStandard, ListingAsset)
    from brambleloop.intel import mission_runtime

    db = _db()
    _benchmark_and_product(db, "fixture-veto")
    # #220: a benchmark raised the gallery standard to 5 images; the listing has 2.
    with db.session() as s:
        s.add(CompetitiveStandard(key="gallery_images", value=5.0, higher_is_better=True,
                                  history=[]))
        for pos in (1, 2):
            s.add(ListingAsset(product_slug="fixture-veto", version="1.0.0", position=pos,
                               asset_class="digital_twin_render", role="hero", approved=True))
    reasons = _publish_gate_reasons(db, "fixture-veto")
    assert any("competitive standard gallery_images" in r for r in reasons), reasons

    # #228: the owner's veto blocks publish; a later ruling letting it through lifts it.
    mission_runtime.record_veto(db, subject_ref="product:fixture-veto",
                                scope="flagship_creative_quality", reason="generic",
                                note="reads as every other throw")
    assert any("owner veto" in r for r in _publish_gate_reasons(db, "fixture-veto"))
    mission_runtime.record_veto(db, subject_ref="product:fixture-veto",
                                scope="flagship_creative_quality", owner_vetoed=False)
    assert not any("owner veto" in r for r in _publish_gate_reasons(db, "fixture-veto"))


# ---------------------------------------------------------------------------
# #179 role work from rows; #99 prioritise + stagnation; #96 code versions


def test_role_work_reports_real_proposals_kept_and_realised_uplift():
    from brambleloop.improve import league

    db = _db()
    _seed_contention(db)
    _run(db, "improve.replay")
    _run(db, "improve.sandbox")
    card = _run(db, "improve.role_work", agent="prompt_tool_challenger")
    assert card["proposed"] == 6 and card["kept"] == 1, card
    assert card["scorecard"]["reading"] == "realisation_pending"
    # A fresh window replayed after promotion where the promoted policy holds: the monitor
    # records the observation and the role's uplift is realised from it.
    from brambleloop.core.models import Improvement

    with db.session() as s:
        imp = s.scalar(select(Improvement).where(Improvement.state == "promoted"))
        change = dict(imp.evidence["change"])
    _fresh_worse_runs(db, change["replaces"], change["config_id"], tag="held",
                      old_q=0.5, new_q=0.9)
    _run(db, "improve.monitor")
    again = _run(db, "improve.role_work", agent="prompt_tool_challenger")
    assert again["realised_uplift"] > 0 and again["scorecard"]["reading"] == "measured", again
    evaluator = _run(db, "improve.role_work", agent="evaluator")
    assert evaluator["activity"]["verdicts"]["approved"] == 1


def test_sandbox_orders_by_expected_impact_and_throttles_a_stagnating_department():
    from brambleloop.core.models import Improvement, Incident
    from brambleloop.improve import cells

    db = _db()
    for v in (10.0, 11.0):
        cells.record_capability(db, "seo_search", v)
    low = cells.propose(db, cell="seo_search", hypothesis=(
        "grouping the candidate phrases by cluster should raise the distinct clusters the "
        "catalogue answers this week"), expected_effect="more clusters",
        rollback_ref="capability:seo_search:2", touches=("weights",), proposed_by="listing")
    high = cells.propose(db, cell="seo_search", hypothesis=(
        "ranking by cluster before length should raise the distinct clusters the catalogue "
        "answers within a week"), expected_effect="more clusters",
        rollback_ref="capability:seo_search:2", touches=("weights",), proposed_by="listing")
    with db.session() as s:
        s.get(Improvement, low).evidence = {**s.get(Improvement, low).evidence,
                                            "expected_gain": 0.5}
        s.get(Improvement, high).evidence = {**s.get(Improvement, high).evidence,
                                             "expected_gain": 3.0}
    out = _run(db, "improve.sandbox")
    assert out["prioritised"][:2] == [high, low], out["prioritised"]

    # Three old promotions that returned nothing: the department is stagnating.
    now = datetime.now(timezone.utc)
    with db.session() as s:
        for i in range(3):
            s.add(Improvement(cell="seo_search", metric="distinct_query_clusters",
                              hypothesis="h" * 40, state="promoted", baseline_value=10.0,
                              result_value=11.0, promoted_at=now - timedelta(days=30),
                              at=now - timedelta(days=31), evidence={}))
    cells.record_capability(db, "seo_search", 10.0)
    again = _run(db, "improve.sandbox")
    assert again["discipline"]["stagnating"] is True
    with db.session() as s:
        assert s.scalar(select(Incident).where(
            Incident.signature == "improve-stagnation")) is not None


def test_prompts_tools_and_policies_are_versioned_from_the_running_code():
    from brambleloop.core.models import ConfigVersion

    db = _db()
    _run(db, "improve.monitor")          # the cadence that ensures the registry
    with db.session() as s:
        rows = list(s.scalars(select(ConfigVersion).where(ConfigVersion.incumbent == True)))  # noqa: E712
    kinds = {r.kind for r in rows}
    assert {"prompt", "tool", "policy", "model"} <= kinds, kinds
    keys = {r.key for r in rows}
    assert "tool:cir_compiler" in keys and "policy:spend_ceilings" in keys
    tool = next(r for r in rows if r.key == "tool:cir_compiler")
    # C-82: registration names the coverage that exercises the tool (`tests_declared`) and
    # never synthesises an executed run -- `tests_run` is empty until one is observed.
    assert tool.why_changed and tool.tests_declared and tool.affected_departments
    assert tool.tests_run == [], tool.tests_run
    assert json.loads(tool.detail["payload"])["source_sha256"]


def test_tests_run_holds_only_observed_runs_bound_to_the_versions_digest():
    """C-82 (Codex M04): declared coverage is not execution provenance."""
    from brambleloop.core.models import ConfigVersion
    from brambleloop.improve import league

    db = _db()
    iid, challenger, replaced = _promote_replay_challenger(db)
    with db.session() as s:
        ch = s.get(ConfigVersion, challenger)
        inc = s.get(ConfigVersion, replaced)
        runs, declared, digest = list(ch.tests_run), list(ch.tests_declared), ch.digest
        inc_runs, inc_declared = list(inc.tests_run), list(inc.tests_declared)
    # Registration declared coverage for both; the incumbent was never put through a run.
    assert declared == ["improve.replay"] and "tests/test_swarm.py" in inc_declared
    assert inc_runs == [], inc_runs
    # The sandbox's regression and adversarial runs happened against the challenger and were
    # observed: each carries the run id and the digest of the version it ran against.
    assert {r["test"] for r in runs} == {"gates.regression.run", "improve.sandbox.adversarial"}
    assert all(r["run_id"] and r["source_sha256"] == digest and r["by"] == "sandbox_runner"
               and "at" in r and isinstance(r["passed"], bool) for r in runs), runs
    _state, ev, _b, _r = _improvement(db, iid)
    assert {r["run_id"] for r in runs} == {t["ref"] for t in ev["tests"].values()}
    # Nothing can register a run, and a run of some other source is refused.
    try:
        league.register(db, kind="scoring", key="policy:job_priority", payload="{}",
                        why_changed="a payload registered with a synthesised run record",
                        affected_departments=("runtime",), tests_run=("tests/test_swarm.py",))
    except league.LeagueRefused as e:
        assert "tests_declared" in str(e)
    else:
        raise AssertionError("register accepted tests_run")
    try:
        league.record_test_run(db, challenger, test="x", run_id="r1", source_sha256="0" * 64,
                               passed=True, recorded_by="sandbox_runner")
    except league.LeagueRefused as e:
        assert "not evidence about this version" in str(e)
    else:
        raise AssertionError("a run of another source was attached")
    # Idempotent on (test, run_id); the standings report both facts separately.
    again = league.record_test_run(db, challenger, test=runs[0]["test"],
                                   run_id=runs[0]["run_id"], source_sha256=digest,
                                   passed=True, recorded_by="sandbox_runner")
    assert again["recorded"] is False
    standing = next(r for r in league.standings(db)["all"] if r["id"] == challenger)
    assert standing["tests_declared"] == declared and len(standing["tests_run"]) == 2


# ---------------------------------------------------------------------------
# #194 #53 #100: the weekly cycle reads its domains from rows, can add, and stops things


def test_weekly_cycle_reads_domains_from_rows_adds_a_specialist_and_stops_things():
    _scheduled("improve.weekly", "orchestrator")
    from brambleloop.core.models import (CostEntry, Experiment, ListingOutcome, OwnerAction,
                                         SupportCase, TeardownFinding)

    db = _db()
    now = datetime.now(timezone.utc)
    with db.session() as s:
        s.add(ListingOutcome(product_slug="p1", period_start="2026-09-01", source="etsy_stats",
                             period_end="2026-09-07", impressions=900, visits=120, orders=0))
        s.add(SupportCase(customer_ref="c", question="where is my file",
                          at=now - timedelta(days=5)))
        s.add(CostEntry(agent="market_radar", kind="llm", amount_cad=1.0,
                        department="market_radar", at=now - timedelta(days=10)))
        s.add(CostEntry(agent="market_radar", kind="llm", amount_cad=3.0,
                        department="market_radar", at=now - timedelta(days=1)))
        s.add(Experiment(name="stale-exp", kind="listing_test", state="running",
                         created_at=now - timedelta(days=60)))
        for i in range(3):
            s.add(TeardownFinding(benchmark_ref=f"b{i}", dimension="chart_quality",
                                  score=4.0, mechanism="m" * 20, improvement="i" * 20))
    out = _run(db, "improve.weekly")
    dm = out["domains_measured"]
    assert dm["conversion"]["findings"] == 1 and dm["support"]["findings"] >= 1
    assert dm["cost"]["findings"] >= 1 and dm["ads"]["reading"] == "UNMEASURED"
    assert "teardown_finding_steward" in out["added"], out["added"]
    assert out["add_card"] == "queued"
    assert out["stop_list"]["executed"] == [{"experiment": 1, "state": "stopped"}]
    with db.session() as s:
        assert s.scalar(select(Experiment)).state == "stopped"
        assert s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "improve.architecture:add")) is not None


# ---------------------------------------------------------------------------
# #176 #174 #187: ownership over every noun, per-function quality, value and deadline


def test_work_items_cover_every_noun_and_an_unpromoted_finding_is_surfaced():
    from brambleloop.core.models import (BenchmarkProduct, CoverageGap, Experiment, Incident,
                                         Listing, OwnerAction, SupportCase, TeardownFinding)

    db = _db()
    with db.session() as s:
        s.add(CoverageGap(benchmark_key="mjs", arena="stockings", pod="seasonal"))
        s.add(BenchmarkProduct(ref="bench-9", seller="S"))
        s.add(Listing(product_slug="p1", version="1.0.0", title="t", description="d"))
        s.add(Experiment(name="e1", kind="listing_test"))
        s.add(SupportCase(customer_ref="c", question="q"))
        s.add(OwnerAction(action="sign the thing"))
        s.add(TeardownFinding(benchmark_ref="bench-9", dimension="chart_quality", score=4.0,
                              mechanism="m" * 20, improvement="i" * 20))
    out = _run(db, "swarm.orphans", agent="swarm_steward")
    by = out["by_source"]
    for src in ("opportunity", "benchmark", "listing", "experiment", "support_case",
                "owner_action", "teardown_finding"):
        assert by[src] == 1, (src, by)
    assert [o["key"] for o in out["orphans"]] == ["teardown_finding:1"], out["orphans"]
    with db.session() as s:
        assert s.scalar(select(Incident).where(
            Incident.signature == "swarm.orphan:teardown_finding:1")) is not None


def test_agent_quality_reads_each_agents_function_with_declared_inputs_and_outputs():
    from brambleloop.core.models import Job, JobStatus

    db = _db()
    now = datetime.now(timezone.utc)
    with db.session() as s:
        for i in range(10):
            s.add(Job(agent="validator", job_type="cir.compile", status=JobStatus.DONE,
                      outputs={"compiled": i < 3}, created_at=now, finished_at=now,
                      started_at=now, idempotency_key=f"v{i}"))
    out = _run(db, "swarm.review", agent="swarm_steward")
    agents = out["agents"] if "agents" in out else out["quality"]["agents"]
    v = agents["validator"]
    assert v["inputs"] and v["outputs"]
    assert v["function_quality"]["metric"] == "compile_pass_rate"
    assert v["function_quality"]["value"] == 0.3 and v["verdict"] == "watch", v


def test_priority_uses_deadline_value_and_proven_revenue_inside_the_band():
    from brambleloop.core.models import LedgerEntry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.swarm.orchestrate import BAND_BY_KIND

    db = _db()
    q = JobQueue(db)
    unproven = q.enqueue("listing", "listing.seo", {"slug": "nordic-forest-basket"})
    assert unproven.priority == BAND_BY_KIND["new_opportunity"]
    with db.session() as s:
        s.add(LedgerEntry(category="sale", gross_cad=12.0,
                          evidence_ref="order:1:nordic-forest-basket"))
    proven = q.enqueue("listing", "listing.seo", {"slug": "nordic-forest-basket", "n": 2})
    assert proven.priority == BAND_BY_KIND["proven_winner"]
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    far = (datetime.now(timezone.utc) + timedelta(days=80)).isoformat()
    a = q.enqueue("orchestrator", "seasonal.sentinel", {"latest_launch": soon})
    b = q.enqueue("orchestrator", "seasonal.sentinel", {"latest_launch": far})
    band = BAND_BY_KIND["seasonal_deadline"] if a.priority < 30 else a.priority
    assert a.priority < b.priority, (a.priority, b.priority)
    assert b.priority - a.priority <= 4 and a.priority > band - 5


# ---------------------------------------------------------------------------
# #97 #147 lessons acted on; #231 concentration; #129 taste


def test_market_radar_and_listings_act_on_their_lessons():
    from brambleloop.core.models import Lesson
    from brambleloop.improve import bus

    db = _db()
    lid = bus.publish(db, origin_cell="product_creativity", subject="construction_preference",
                      statement=("buyers strongly prefer a mosaic storage basket worked in one "
                                 "piece, with no seaming at the end"),
                      evidence_ref="test:low-sew")
    out = _run(db, "radar.score", agent="market_radar",
               inputs={"slug": "nordic-forest-basket"})
    assert out["lesson_adjustment"] == 0.02, out
    with db.session() as s:
        acted = [e["cell"] for e in s.get(Lesson, lid).acted_on_by]
    assert "market_radar" in acted


def test_engineering_lessons_nudge_priority_as_a_bounded_heuristic_never_as_cad():
    """C-66 (Codex M05): a lesson match is a reason to claim the draft one step earlier inside
    its band, carried under its own key; it never invents currency value, and the record of
    acting on it says the benefit is unmeasured."""
    from brambleloop.core.models import Job, Lesson
    from brambleloop.improve import bus
    from brambleloop.swarm.orchestrate import HEURISTIC_KEY, priority_decision

    def _draft_job(db):
        with db.session() as s:
            return next(dict(inputs=dict(j.inputs or {}), priority=j.priority)
                        for j in s.scalars(select(Job).where(Job.job_type == "cir.draft")))

    inputs = {"slug": "nordic-forest-mosaic-throw", "as_of": "2026-09-17"}
    plain = _db()
    assert _run(plain, "radar.score", agent="market_radar", inputs=inputs)["promoted"]
    without = _draft_job(plain)

    db = _db()
    lids = [bus.publish(db, origin_cell="product_creativity", subject="construction_preference",
                        statement=("buyers strongly prefer an overlay mosaic throw whose rows "
                                   "are a countable sequence worked in one piece"),
                        evidence_ref=f"test:lesson-{i}") for i in range(3)]
    out = _run(db, "radar.score", agent="market_radar", inputs=inputs)
    assert out["promoted"]
    with_lessons = _draft_job(db)

    # No CAD field moved: three matching lessons used to add 450 CAD of invented value.
    for key in ("value_cad", "expected_value_cad", "expected_revenue_cad"):
        assert with_lessons["inputs"].get(key) == without["inputs"].get(key), key
    heuristic = with_lessons["inputs"][HEURISTIC_KEY]
    assert set(heuristic["lessons"]) == set(lids) and heuristic["steps"] == 1
    assert "unmeasured" in heuristic["benefit"] and heuristic["reason"]
    # Acted on: exactly one step earlier inside the band, never across it.
    decision = priority_decision("cir.draft", with_lessons["inputs"], db=db)
    assert with_lessons["priority"] == without["priority"] - 1 == decision["priority"]
    assert decision["heuristic"]["steps"] == 1 and decision["moved"] <= 4
    assert decision["band"] - 4 <= with_lessons["priority"] <= decision["band"]
    with db.session() as s:
        acted = {e["cell"]: e["how"] for e in s.get(Lesson, lids[0]).acted_on_by}
    assert "pattern_engineering" in acted, acted
    assert "benefit unmeasured" in acted["pattern_engineering"]


def test_culture_findings_publish_lessons_to_radar_seo_and_portfolio():
    from brambleloop.core.models import Lesson
    from brambleloop.culture import radar

    db = _db()
    original = radar.findings
    radar.findings = lambda db, limit=20: {
        "findings": [{"signal": "cottagecore", "sensitive": False,
                      "momentum": {"direction": "rising"},
                      "lead_lag": {"measurable": True, "lead_days": 21}}],
        "weights_measurable": False, "why_weights_are_unmeasured": "no sales"}
    try:
        radar.route_findings(db)
    finally:
        radar.findings = original
    with db.session() as s:
        lessons = list(s.scalars(select(Lesson)))
    subjects = {l.subject for l in lessons}
    assert {"cultural_territory", "cultural_timing"} <= subjects
    routed = {c for l in lessons for c in l.routed_to}
    assert {"market_radar", "seo_search", "growth", "portfolio"} <= routed


def test_high_concentration_moves_ideations_next_role_away_from_the_winner():
    from brambleloop.core.models import LedgerEntry, Product
    from brambleloop.creative import ideation

    db = _db()
    with db.session() as s:
        for slug in ("alpha-throw", "beta-hat", "gamma-bag"):
            s.add(Product(slug=slug, title=slug, status="certified"))
        s.add(LedgerEntry(category="sale", gross_cad=100.0, evidence_ref="order:alpha-throw"))
        s.add(LedgerEntry(category="sale", gross_cad=5.0, evidence_ref="order:beta-hat"))
    out = ideation.role(db)
    assert out["diversifying"] is True and out["avoid_family"] == "alpha"
    assert out["concentration"]["top_sku"] == "alpha-throw"
    assert out["role"] != out["deprioritised_role"]


def test_the_taste_judge_rejects_the_obvious_winner_whatever_its_novelty():
    from types import SimpleNamespace

    from brambleloop.creative import ideation

    def cand(key, form, motif, dist, feeling="cosy"):
        concept = SimpleNamespace(key=key, title=key, form=form, motif=motif,
                                  make_lane="SHORT", feeling=feeling, function="warmth",
                                  pod="p", occasion="christmas", premise="",
                                  construction="flat", palette_story="winter",
                                  recipient="self", provenance="internal")
        return SimpleNamespace(concept=concept, nearest_distance=dist)

    field = [cand("a", "stocking", "reindeer", 0.9), cand("b", "stocking", "reindeer", 0.8),
             cand("c", "stocking", "reindeer", 0.7), cand("d", "garland", "lichen", 0.6)]
    plan = {"floor": {"floor": 0.45}, "role": {"lanes": ["SHORT"], "role": "CORE"},
            "history": []}
    out = ideation.select(plan, candidates=field, survivors=field)
    assert {r["key"] for r in out["taste_rejected"]} == {"a", "b", "c"}
    assert out["winner"]["key"] == "d"


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
