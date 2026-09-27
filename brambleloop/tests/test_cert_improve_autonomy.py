"""Certification repairs for cluster W7: the improvement loop, autonomy and the support path.

Requirements 41 (support half, C-42), 92, 95, 175, 180, 188, 190, 192, 195. Each of these had
a library that existed and was tested while nothing in the running system called it. Every
test here drives the runtime entry point -- the registered handler, with a real JobContext on
a file database, or the function the worker's claim calls -- and asserts the effect is
persisted or enforced, not merely returned. Against the pre-repair tree each handler is
missing or each effect absent, so each test fails there.
"""
from __future__ import annotations

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

H = ("re-ranking candidate phrases by cluster before length should raise the number of "
     "distinct clusters the catalogue answers within a week")


def _db() -> Database:
    tmp = tempfile.mkdtemp(prefix="cert_w7_")
    db = Database(f"sqlite:///{tmp}/w7.sqlite")
    db.create_all()
    from brambleloop.agents.registry import Registry

    Registry(db).seed_defaults()
    return db


_N = [0]


def _ctx(db, job_type: str, agent: str = "orchestrator", inputs: dict | None = None,
         job=None):
    from brambleloop.agents.registry import Registry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline, release  # noqa: F401 -- registers handlers
    from brambleloop.runtime.worker import JobContext

    q = JobQueue(db)
    if job is None:
        _N[0] += 1
        job = q.enqueue(agent, job_type, inputs or {}, idempotency_key=f"w7:{job_type}:{_N[0]}")
    from brambleloop.core.models import Phase

    return JobContext(job=job, db=db, queue=q, registry=Registry(db), phase=Phase.SHADOW)


def _run(db, job_type: str, agent: str = "orchestrator", inputs: dict | None = None) -> dict:
    from brambleloop.runtime import pipeline, release  # noqa: F401 -- registers handlers
    from brambleloop.runtime.worker import handlers

    handler = handlers.get(job_type)
    assert handler is not None, f"no handler registered for {job_type!r}"
    return handler(_ctx(db, job_type, agent, inputs))


def _improvement(db, iid):
    from brambleloop.core.models import Improvement

    with db.session() as s:
        r = s.get(Improvement, iid)
        return r.state, dict(r.evidence or {}), r.result_value


def _backdate_promotions(db, *, hours: float) -> None:
    """Move every recorded promotion into the past, so a tier's cooldown is not the subject."""
    from brambleloop.core.models import AuditLog

    with db.session() as s:
        for a in s.scalars(select(AuditLog).where(AuditLog.action == "improve.promoted")):
            a.at = datetime.now(timezone.utc) - timedelta(hours=hours)


def _promoted_then_declining(db, *, touches=("weights",), cell="seo_search",
                             before=10.0, after=12.0, decline=(11.0, 10.5, 9.0)) -> tuple:
    """A promoted change on a cell, then three readings moving the wrong way, then the
    self-review's own declining_capability proposal -- exactly as the nightly QUEUE opens it."""
    from brambleloop.improve import cells, profiles, tiers

    cells.record_capability(db, cell, before, sample=5)
    a = cells.propose(db, cell=cell, hypothesis=H, expected_effect="more clusters",
                      rollback_ref=f"weights:{cell}:v1", touches=touches,
                      proposed_by=profiles.CELL_AGENT[cell])
    assert cells.test_result(db, a, after) == cells.TESTING
    need = tiers.classify(touches).requires
    for kind in (tiers.REGRESSION_TEST, tiers.ADVERSARIAL_TEST):
        if kind in need:
            cells.record_test(db, a, kind=kind, ref=f"fixture-run:{kind}", passed=True,
                              recorded_by="evaluator")
    cells.approve(db, a, approved_by="evaluator", why="beat baseline on the holdout set")
    assert cells.promote(db, a, promoted_by="evaluator") == cells.PROMOTED
    for v in decline:
        cells.record_capability(db, cell, v, detail={"from": "improve.measure"})
    queued = profiles.queue_proposals(db)
    b = next(q["improvement"] for q in queued["queued"]
             if q["cell"] == cell and q["kind"] == "declining_capability")
    return a, b


# ---- #92: the sandbox step -----------------------------------------------------------------


def test_sandbox_takes_a_declining_proposal_through_trial_tests_approval_and_promotion():
    from brambleloop.improve import cells, runner

    db = _db()
    a, b = _promoted_then_declining(db)
    assert _improvement(db, b)[0] == cells.PROPOSED
    _backdate_promotions(db, hours=7)            # the scoring cooldown is six hours

    out = _run(db, "improve.sandbox")
    state, ev, result = _improvement(db, b)
    assert [s["improvement"] for s in out["sandboxed"]] == [b], out
    assert result == 10.0, "the trial is the cell's recorded capability before promotion a"
    assert ev["sandbox"]["by"] == runner.RUNNER and ev["sandbox"]["trial"] == \
        "counterfactual_rollback" and ev["sandbox"]["run_ref"].startswith(f"improvement:{a}:")
    tests = ev["tests"]
    assert tests["regression_test"]["passed"] and tests["regression_test"]["by"] == runner.RUNNER
    assert tests["adversarial_test"]["passed"] and tests["adversarial_test"]["by"] == runner.RUNNER
    assert ev["approved_by"] == "evaluator" and ev["proposed_by"] == "listing"
    assert state == cells.PROMOTED and ev["promoted_by"] == "evaluator", (state, out["held"])
    from brambleloop.core.models import AuditLog

    with db.session() as s:
        assert s.scalar(select(AuditLog).where(AuditLog.action == runner.ACTION)) is not None


def test_sandbox_rejects_a_proposal_its_trial_shows_is_no_better():
    from brambleloop.improve import cells

    db = _db()
    # The cell read 8.0 before the promoted change and 9.0 now: rolling back would be worse.
    _a, b = _promoted_then_declining(db, before=8.0, after=12.0, decline=(11.0, 10.0, 9.0))
    _run(db, "improve.sandbox")
    state, ev, result = _improvement(db, b)
    assert state == cells.REJECTED and result == 8.0, (state, ev.get("why"))
    assert "approved_by" not in ev


def test_sandbox_never_lets_the_proposer_approve_and_invents_no_result():
    from brambleloop.core.models import Improvement
    from brambleloop.improve import cells

    db = _db()
    a, b = _promoted_then_declining(db)
    with db.session() as s:                     # the judge is also the author of this one
        row = s.get(Improvement, b)
        row.evidence = {**row.evidence, "proposed_by": "evaluator"}
    plain = cells.propose(db, cell="seo_search", hypothesis=H, expected_effect="x",
                          rollback_ref="w:v2", touches=("weights",), proposed_by="listing")
    _backdate_promotions(db, hours=7)
    out = _run(db, "improve.sandbox")
    state, ev, _ = _improvement(db, b)
    assert state == cells.TESTING and "approved_by" not in ev, (state, ev)
    assert any(h["improvement"] == b for h in out["held"]), out["held"]
    # A proposal no registered trial can evaluate waits; it is not given a number.
    pstate, pev, presult = _improvement(db, plain)
    assert pstate == cells.PROPOSED and presult is None and "sandbox" not in pev
    assert any(w["improvement"] == plain for w in out["waiting_detail"])


def test_adversarial_test_catches_a_tampered_sandbox_result():
    from brambleloop.core.models import Improvement
    from brambleloop.improve import runner

    db = _db()
    _a, b = _promoted_then_declining(db)
    _run(db, "improve.sandbox")          # records a genuine result; now forge it upwards
    with db.session() as s:
        s.get(Improvement, b).result_value = 99.0
    verdict = runner.adversarial_test(db, b)
    assert verdict["passed"] is False and "99.0" in verdict["why"], verdict


def test_an_empty_regression_suite_is_a_failed_run_not_a_pass():
    from brambleloop.improve import runner

    empty = Path(tempfile.mkdtemp(prefix="no_fixtures_"))
    out = runner.regression_test(directory=empty)
    assert out["passed"] is False and out["checked"] == 0
    assert runner.regression_test()["passed"] is True     # the repo's captured defects


def test_higher_tier_goes_to_one_owner_card_and_promotes_only_on_the_owners_record():
    from brambleloop.core.models import OwnerAction
    from brambleloop.improve import cells, upgrades

    db = _db()
    _a, b = _promoted_then_declining(db, touches=("cadence",))     # tooling tier
    _backdate_promotions(db, hours=24 * 4)                           # 72h tooling cooldown
    key = f"{upgrades.IMPROVEMENT_CARD_PREFIX}{b}"
    first = _run(db, "improve.sandbox")
    assert [c["improvement"] for c in first["owner_cards"]] == [b], first
    second = _run(db, "improve.sandbox")
    assert second["owner_cards"][0]["state"] == "already_open"
    with db.session() as s:
        cards = list(s.scalars(select(OwnerAction).where(OwnerAction.requirement_key == key)))
    assert len(cards) == 1 and not cards[0].done and "record" in cards[0].action
    state, ev, _ = _improvement(db, b)
    assert state == cells.TESTING and "owner_approval" not in ev, \
        "the runner recorded or forged an owner approval"

    # The launch-readiness sweep closes what its assessment no longer asks for; it must not
    # close a card it never raised.
    _run(db, "launch.readiness")
    with db.session() as s:
        assert s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key)
                        ).done is False

    # Nobody but the owner can record the decision.
    try:
        cells.record_owner_approval(db, b, approved_by="evaluator", why="looks good to me")
        raise AssertionError("a non-owner recorded an owner approval")
    except cells.ImprovementRefused:
        pass
    cells.record_owner_approval(db, b, approved_by="owner",
                                why="the rollback target is concrete and tested")
    third = _run(db, "improve.sandbox")
    assert [p["improvement"] for p in third["promoted"]] == [b], third
    assert _improvement(db, b)[0] == cells.PROMOTED
    with db.session() as s:
        assert s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key)).done


# ---- #95 / #180: the league ------------------------------------------------------------------


def _config(db, kind, key, payload, *, incumbent):
    from brambleloop.improve import league

    return league.register(db, kind=kind, key=key, payload=payload,
                           why_changed=("a listing copy prompt that leads with the finished "
                                        "size and the skill level"),
                           affected_departments=("seo_search",), incumbent=incumbent)["id"]


def _tasks(n, q, prefix="t"):
    return {f"{prefix}{i}": q for i in range(n)}


def test_league_registers_challengers_and_waits_honestly_without_runs():
    from brambleloop.core.models import ConfigVersion

    db = _db()
    out = _run(db, "improve.league")
    with db.session() as s:
        challengers = list(s.scalars(select(ConfigVersion).where(
            ConfigVersion.incumbent == False)))  # noqa: E712
    assert challengers and out["challengers_registered"]["registered"] == len(challengers)
    assert out["promoted"] == [] and out["compared"] == [] and out["waiting"] >= len(challengers)
    again = _run(db, "improve.league")
    assert again["challengers_registered"]["registered"] == 0


def test_league_promotes_a_preauthorised_winner_then_rolls_it_back_when_it_regresses():
    from brambleloop.core.models import ConfigVersion
    from brambleloop.improve import league

    db = _db()
    inc = _config(db, "prompt", "prompt:listing_copy", "v1 prompt text", incumbent=True)
    ch = _config(db, "prompt", "prompt:listing_copy", "v2 prompt text", incumbent=False)
    league.record_run(db, inc, tasks=_tasks(20, 0.60), holdout=_tasks(5, 0.60, "h"),
                      cost_cad=0.01, reliability=0.95, run_ref="replay:inc:1",
                      recorded_by="evaluator")
    league.record_run(db, ch, tasks=_tasks(20, 0.80), holdout=_tasks(5, 0.78, "h"),
                      cost_cad=0.01, reliability=0.96, run_ref="replay:ch:1",
                      recorded_by="evaluator")
    out = _run(db, "improve.league")
    assert [p["config_id"] for p in out["promoted"]] == [ch], out
    with db.session() as s:
        assert s.get(ConfigVersion, ch).incumbent and not s.get(ConfigVersion, inc).incumbent
    again = _run(db, "improve.league")
    assert again["promoted"] == [] and again["rolled_back"] == []

    league.record_run(db, ch, tasks=_tasks(20, 0.40), cost_cad=0.01, reliability=0.96,
                      run_ref="production:ch:week2", recorded_by="evaluator")
    back = _run(db, "improve.league")
    assert [r["config_id"] for r in back["rolled_back"]] == [inc], back
    with db.session() as s:
        assert s.get(ConfigVersion, inc).incumbent and not s.get(ConfigVersion, ch).incumbent
        assert "production:ch:week2" in s.get(ConfigVersion, inc).measured_outcome[
            "rollback"]["why"]


def test_league_refuses_a_challenger_judged_on_tasks_it_introduced():
    from brambleloop.core.models import ConfigVersion
    from brambleloop.improve import league

    db = _db()
    inc = _config(db, "prompt", "prompt:faq", "faq v1", incumbent=True)
    ch = _config(db, "prompt", "prompt:faq", "faq v2", incumbent=False)
    league.record_run(db, inc, tasks=_tasks(20, 0.6), cost_cad=0.01, reliability=0.9,
                      run_ref="r:inc", recorded_by="evaluator")
    league.record_run(db, ch, tasks={**_tasks(20, 0.9), "my_own_easy_case": 1.0},
                      cost_cad=0.01, reliability=0.9, run_ref="r:ch", recorded_by="evaluator")
    out = _run(db, "improve.league")
    assert [r["config_id"] for r in out["refused"]] == [ch] and out["promoted"] == []
    with db.session() as s:
        assert s.get(ConfigVersion, inc).incumbent


def test_league_code_mirrored_winner_goes_to_the_owner_not_the_registry():
    from brambleloop.core.models import ConfigVersion, OwnerAction
    from brambleloop.improve import league

    db = _db()
    _run(db, "improve.league")                      # registers routing challengers
    with db.session() as s:
        ch = s.scalar(select(ConfigVersion).where(ConfigVersion.incumbent == False)  # noqa
                      .order_by(ConfigVersion.id))
        inc = s.scalar(select(ConfigVersion).where(
            ConfigVersion.kind == ch.kind, ConfigVersion.key == ch.key,
            ConfigVersion.incumbent == True))  # noqa: E712
        ch_id, inc_id = ch.id, inc.id
    league.record_run(db, inc_id, tasks=_tasks(20, 0.7), holdout=_tasks(4, 0.7, "h"),
                      cost_cad=0.02, reliability=0.95, run_ref="r:inc", recorded_by="evaluator")
    league.record_run(db, ch_id, tasks=_tasks(20, 0.9), holdout=_tasks(4, 0.7, "h"),
                      cost_cad=0.005, reliability=0.96, run_ref="r:ch", recorded_by="evaluator")
    out = _run(db, "improve.league")
    assert [c["config_id"] for c in out["owner_cards"]] == [ch_id], out
    with db.session() as s:
        assert not s.get(ConfigVersion, ch_id).incumbent
        card = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == f"{league.CARD_PREFIX}{ch_id}"))
    assert card is not None and not card.done and "code" in card.action
    try:
        league.record_owner_decision(db, ch_id, approved_by="prompt_tool_challenger",
                                     why="it won the league clearly")
        raise AssertionError("a non-owner recorded the owner's decision")
    except league.LeagueRefused:
        pass


# ---- #175: the allocation decides the claim --------------------------------------------------


def _running(db, agent, job_type, *, worker, lease_minutes=5):
    from brambleloop.core.models import Job, JobStatus

    now = datetime.now(timezone.utc)
    with db.session() as s:
        j = Job(agent=agent, job_type=job_type, status=JobStatus.RUNNING, leased_by=worker,
                lease_expires_at=now + timedelta(minutes=lease_minutes), attempts=1,
                started_at=now, inputs={})
        s.add(j)
        s.flush()
        return j.id


def test_may_claim_reads_the_latest_allocation_and_lane_hold_puts_the_job_back():
    from brambleloop.core.models import AuditLog, Job, JobStatus
    from brambleloop.queue.durable import JobQueue
    from brambleloop.swarm import orchestrate as orc

    db = _db()
    assert orc.may_claim(db, "market_radar") is True          # no allocation: not held
    alloc = orc.allocate(db)
    granted = alloc["lanes"]["market_radar"]["granted"]
    assert granted >= 1
    for i in range(granted):
        _running(db, "market_radar", "culture.sweep", worker=f"w{i}")
    assert orc.may_claim(db, "market_radar", job_type="culture.sweep") is False
    assert orc.may_claim(db, "market_radar", job_type="swarm.allocate") is True
    assert orc.may_claim(db, "listing") is True               # another lane is unaffected

    q = JobQueue(db)
    q.enqueue("market_radar", "culture.sweep", {}, idempotency_key="w7:claim")
    job = q.claim("w-extra", ["culture.sweep"])
    assert job is not None and job.attempts == 1
    assert orc.lane_hold(db, job, worker="w-extra") is True
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.PENDING and row.attempts == 0 and row.leased_by is None
        assert row.run_after.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
        assert s.scalar(select(AuditLog).where(AuditLog.action == orc.LANE_HELD_ACTION))

    # A lease that lapsed is a dead worker, not a running job: it no longer fills the lane.
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.status == JobStatus.RUNNING)):
            j.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert orc.may_claim(db, "market_radar", job_type="culture.sweep") is True


def test_lane_hold_leaves_a_job_this_worker_no_longer_holds():
    from brambleloop.queue.durable import JobQueue
    from brambleloop.swarm import orchestrate as orc

    db = _db()
    orc.allocate(db)
    for i in range(5):
        _running(db, "market_radar", "culture.sweep", worker=f"w{i}")
    q = JobQueue(db)
    q.enqueue("market_radar", "culture.sweep", {}, idempotency_key="w7:lost")
    job = q.claim("w-a", ["culture.sweep"])
    assert orc.lane_hold(db, job, worker="somebody-else") is False


# ---- #188: the governor on a cadence ---------------------------------------------------------


def _spend(db, agent, amount, *, days_ago=0, hours_ago=0.0):
    from brambleloop.core.models import CostEntry

    at = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)
    with db.session() as s:
        s.add(CostEntry(agent=agent, amount_cad=amount, kind="llm", at=at, detail={}))


def test_governor_cadence_pauses_a_spiking_agent_through_the_reservation_table():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Incident, SpendReservation
    from brambleloop.finance import governor
    from brambleloop.gateway.anthropic import AgentCeilingExceeded, check_budget_cad

    db = _db()
    ceiling_before = Registry(db).get("market_radar").daily_cost_ceiling_cad
    for d in range(1, 21):
        _spend(db, "market_radar", 0.10, days_ago=d)
    _spend(db, "market_radar", 3.00, hours_ago=0.01)
    check_budget_cad(db, estimate_cad=0.01, agent="market_radar", reserve=False)  # allowed

    out = _run(db, "finance.governor", agent="cfo")
    assert out["agents_spiking"] == ["market_radar"] and out["paused"][0]["paused"], out
    try:
        check_budget_cad(db, estimate_cad=0.01, agent="market_radar", reserve=False)
        raise AssertionError("the spiking agent could still spend after the governor ran")
    except AgentCeilingExceeded:
        pass
    check_budget_cad(db, estimate_cad=0.01, agent="listing", reserve=False)  # others unaffected
    assert Registry(db).get("market_radar").daily_cost_ceiling_cad == ceiling_before
    today = datetime.now(timezone.utc).date().isoformat()
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == f"{governor.ANOMALY_SIGNATURE}:market_radar:{today}"))
        assert inc is not None and not inc.resolved
    _run(db, "finance.governor", agent="cfo")                       # idempotent
    with db.session() as s:
        holds = [r for r in s.scalars(select(SpendReservation))
                 if r.holder == f"{governor.HOLD_HOLDER_PREFIX}market_radar"]
        assert len(holds) == 1
        assert s.scalar(select(Incident).where(Incident.signature.like(
            f"{governor.ANOMALY_SIGNATURE}:%"))).report_count == 2


def test_governor_does_nothing_on_a_reading_it_cannot_take():
    from brambleloop.core.models import Incident, SpendReservation

    db = _db()
    _spend(db, "market_radar", 3.00, hours_ago=0.01)      # a first day is not a spike
    out = _run(db, "finance.governor", agent="cfo")
    assert out["paused"] == [] and out["incidents"] == []
    assert out["company_anomaly_measurable"] is False
    with db.session() as s:
        assert s.scalar(select(SpendReservation)) is None
        assert s.scalar(select(Incident)) is None


def test_governor_parallelism_advice_feeds_the_allocation_and_the_claim():
    from brambleloop.core.models import AuditLog, SwarmAllocation
    from brambleloop.finance import governor
    from brambleloop.swarm import orchestrate as orc

    db = _db()
    alloc = orc.allocate(db)
    granted = alloc["lanes"]["market_radar"]["granted"]
    assert granted >= 2, "the test needs a lane granted more than one specialist"
    now = datetime.now(timezone.utc)
    with db.session() as s:     # two earlier governor runs' observations: one and two workers
        for hours, workers in ((3, 1), (2, 2)):
            s.add(AuditLog(actor="cfo", action=governor.ACTION, at=now - timedelta(hours=hours),
                           detail={"observation": {"workers": workers, "minutes": 60,
                                                   "completed": 30}}))
    assert orc.lane_concurrency(db, "market_radar")["limit"] == granted
    out = _run(db, "finance.governor", agent="cfo")
    assert out["parallelism"]["advice"] == "scale_down", out["parallelism"]
    with db.session() as s:
        row = s.get(SwarmAllocation, alloc["allocation_id"])
        assert row.detail["parallelism"]["advice"] == "scale_down"
    assert orc.lane_concurrency(db, "market_radar")["limit"] == 1
    _running(db, "market_radar", "culture.sweep", worker="w0")
    assert orc.may_claim(db, "market_radar", job_type="culture.sweep") is False


# ---- #195: the off-device proof blocks launch ------------------------------------------------


def test_launch_readiness_carries_the_off_device_proof_as_a_blocking_item():
    from brambleloop.build2 import autonomy
    from brambleloop.core.models import AuditLog

    db = _db()
    out = _run(db, "launch.readiness")
    item = out["blocking_items"][0]
    assert item["key"] == autonomy.LAUNCH_ITEM_KEY and item["status"] == autonomy.NOT_PROVEN
    assert out["ready"] is False and autonomy.LAUNCH_ITEM_KEY in out["outstanding"]
    with db.session() as s:
        audit = s.scalar(select(AuditLog).where(AuditLog.action == "launch.assessed"))
    assert audit.detail["off_device_proof"]["status"] == autonomy.NOT_PROVEN


def test_an_uncomputable_proof_is_not_proven():
    from brambleloop.build2 import autonomy

    real = autonomy.off_device_proof
    autonomy.off_device_proof = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db gone"))
    try:
        item = autonomy.launch_item(_db())
    finally:
        autonomy.off_device_proof = real
    assert item["status"] == autonomy.NOT_PROVEN and item["passed"] is False


def test_a_window_worked_unattended_is_proven_with_recovery_evidence():
    from brambleloop.build2 import autonomy
    from brambleloop.core.models import Job, JobStatus

    db = _db()
    now = datetime.now(timezone.utc)
    with db.session() as s:
        for h in range(20):
            at = now - timedelta(hours=h + 0.5)
            for t in ("ops.health", "improve.measure", "swarm.allocate"):
                s.add(Job(agent="orchestrator", job_type=t, status=JobStatus.DONE, inputs={},
                          idempotency_key=f"cadence:{t}:{h}", created_at=at, finished_at=at,
                          attempts=2 if (h == 3 and t == "ops.health") else 1))
    item = autonomy.launch_item(db, now=now)
    assert item["status"] == autonomy.PROVEN, item["unmet"]
    assert item["evidence"]["restart_recovery"]["recovered_jobs"] == 1


# ---- #192: retirement recommendations reach the owner ----------------------------------------


def test_retirement_recommendations_become_one_owner_card_and_disable_nothing():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import OwnerAction
    from brambleloop.improve import director

    db = _db()
    enabled_before = sorted(a.name for a in Registry(db).all() if a.enabled)
    out = _run(db, "improve.weekly")
    routed = out["retirement_review"]["routed"]
    recommended = out["retirement_review"]["retire"] + out["retirement_review"]["merge"]
    with db.session() as s:
        card = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == director.RETIREMENT_CARD_KEY))
    if recommended:
        assert routed["state"] == "queued" and card is not None and not card.done
        assert all(r["cell"] in card.action for r in recommended)
    else:
        assert routed["state"] == "none" and card is None
    assert sorted(a.name for a in Registry(db).all() if a.enabled) == enabled_before

    review = {"retire": [{"cell": "growth", "reason": "no completed work in 21 days",
                          "preserve": [7, 9]}], "merge": [], "keep": []}
    first = director.route_retirements(db, review)
    assert first["state"] in ("queued", "restated")
    assert director.route_retirements(db, review)["state"] == "already_open"
    with db.session() as s:
        open_cards = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == director.RETIREMENT_CARD_KEY,
            OwnerAction.done == False)))  # noqa: E712
    assert len(open_cards) == 1 and "[7, 9]" in open_cards[0].action
    assert director.route_retirements(db, {"retire": [], "merge": []})["state"] == "closed"


# ---- #41 / C-42: the support path -------------------------------------------------------------


def test_support_triage_cadence_enqueues_draft_replies_and_counts_confusion():
    from brambleloop.core.models import Job, LedgerEntry, SupportCase
    from brambleloop.runtime.worker import handlers
    from brambleloop.support.department import CustomerExperience

    db = _db()
    dept = CustomerExperience(db)
    confused = dept.intake(customer_ref="c-1", message=(
        "I thought this was a finished blanket - when will my order ship?"))
    plain = dept.intake(customer_ref="c-2", message="How do I read the chart for round 3?")

    out = _run(db, "support.triage", agent="support")
    jobs = {j["case"]: j["job"] for j in out["triage"]["reply_jobs"]}
    assert set(jobs) == {confused, plain}, out["triage"]
    assert out["confusion"]["confusion_contacts"] == 1
    assert out["confusion"]["confusion_rate"] == "UNMEASURED"          # no orders
    with db.session() as s:
        details = {c.id: dict(c.detail) for c in s.scalars(select(SupportCase))}
    assert details[confused]["theme"] == "confusion" and details[plain]["theme"] == "other"
    if not out["case_window"].get("known"):
        assert details[confused]["resolve_before"] == "UNKNOWN"

    for case_id, job_id in jobs.items():
        with db.session() as s:
            job = s.get(Job, job_id)
            s.expunge(job)
        assert job.job_type == "support.reply" and job.inputs["case_id"] == case_id
        reply = handlers.get("support.reply")(_ctx(db, "support.reply", job=job))
        assert reply["sent"] is False and reply["case_id"] == case_id
    with db.session() as s:
        cases = list(s.scalars(select(SupportCase)))
    assert len(cases) == 2, "a drafted reply created a second case instead of answering one"
    assert all(c.answer and c.sent is False for c in cases)

    again = _run(db, "support.triage", agent="support")
    assert again["triage"]["reply_jobs"] == [] and again["triage"]["triaged"] == []

    with db.session() as s:          # a fixture sale: the rate becomes measurable
        s.add(LedgerEntry(category="sale", gross_cad=12.0, fees_cad=1.0, refunds_cad=0.0,
                          expense_cad=0.0))
    third = _run(db, "support.triage", agent="support")
    assert third["confusion"]["measurable"] is True
    assert third["confusion"]["confusion_rate"] == 1.0


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
