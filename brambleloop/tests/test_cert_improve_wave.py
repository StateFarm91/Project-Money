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
    league.record_run(db, change["replaces"], tasks={"day:y": 0.5}, cost_cad=0.0,
                      reliability=1.0, run_ref="replay:cccccccccccc:y..y:30",
                      recorded_by="prompt_tool_challenger")
    league.record_run(db, change["config_id"], tasks={"day:y": 0.9}, cost_cad=0.0,
                      reliability=1.0, run_ref="replay:dddddddddddd:y..y:30",
                      recorded_by="prompt_tool_challenger")
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
    assert tool.why_changed and tool.tests_run and tool.affected_departments
    assert json.loads(tool.detail["payload"])["source_sha256"]


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
