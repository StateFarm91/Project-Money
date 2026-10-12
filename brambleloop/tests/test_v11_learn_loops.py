"""v1.1 lane B: the Learn loop closes on measured evidence, and cannot weaken what it protects.

Directive §4, F-891, F-918, F-919, F-920. Every test drives the registered handlers the
runtime schedules (`improve.sandbox`, `improve.monitor`) on a file database seeded with real
rows, and asserts the downstream effect -- the value a runtime consumer reads, the decision it
takes on its next call -- not a library's return value.

* end to end: outcome rows -> proposal -> shadow evaluation -> promotion -> the next
  `consume.matching` call (which `runtime.release` makes for every listing) decides differently
* rollback: post-promotion outcomes regress -> the registry is restored, verified by reading
  the consumer's value back, the lesson persisted -- and the next cycle does not re-propose it
* negative: proposals touching protected thresholds are refused, recorded and audited, and
  nothing reaches the registry or the consumer
* D-B1: the capability monitor no longer reverts a trial-metric promotion on paper
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp(prefix="v11_learn_")
    db = Database(f"sqlite:///{tmp}/l.sqlite")
    db.create_all()
    from brambleloop.agents.registry import Registry

    Registry(db).seed_defaults()
    from brambleloop.swarm.orchestrate import clear_policy_cache

    clear_policy_cache()
    return db


_N = [0]


def _run(db, job_type: str, agent: str = "orchestrator") -> dict:
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Phase
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline, release  # noqa: F401 -- registers handlers
    from brambleloop.runtime.worker import JobContext, handlers

    handler = handlers.get(job_type)
    assert handler is not None, job_type
    q = JobQueue(db)
    _N[0] += 1
    job = q.enqueue(agent, job_type, {}, idempotency_key=f"v11b:{job_type}:{_N[0]}")
    return handler(JobContext(job=job, db=db, queue=q, registry=Registry(db),
                              phase=Phase.SHADOW))


LESSON = ("buyers search for chunky blanket cozy throw when the first cold week of "
          "autumn arrives")
TEXT = {"A": "chunky blanket cozy throw pattern",      # shares 4 words
        "B": "chunky blanket pattern",                 # shares 2 words
        "C": "amigurumi bunny pattern"}                # shares none
CTR = {"A": 0.12, "B": 0.01, "C": 0.06}


def _lesson(db) -> int:
    from brambleloop.improve import bus

    return bus.publish(db, origin_cell="growth", subject="search_language",
                       statement=LESSON, evidence_ref="test:v11b:lesson")


def _listing_outcome(db, slug: str, ctr: float) -> None:
    from brambleloop.core.models import ListingOutcome

    today = date.today().isoformat()
    with db.session() as s:
        s.add(ListingOutcome(product_slug=slug, version="1.0.0", period_start=today,
                             period_end=today, impressions=1000, visits=int(round(ctr * 1000)),
                             favourites=None, first_frame_views=None,
                             first_frame_engagements=None, orders=None, hero_style="",
                             styles=[], test_key="", source="test:v11b", detail={}))


def _decide(db, slug: str, group: str) -> list:
    """What runtime.release listing.seo does for one listing: read the SEO lesson inbox."""
    from brambleloop.improve import consume

    return consume.matching(db, "seo_search", TEXT[group], subject=slug)


def _seed_seo_history(db, n_each: int = 8) -> None:
    for i in range(n_each):
        for group in "ABC":
            slug = f"listing-{group.lower()}-{i}"
            _decide(db, slug, group)
            _listing_outcome(db, slug, CTR[group])


def _promote_seo(db) -> dict:
    from brambleloop.core.models import Improvement
    from brambleloop.improve import policy_loops as pl

    _lesson(db)
    # Before: the code default (2 shared words) gives the B-type listing its lesson slot.
    assert len(_decide(db, "probe-before", "B")) == 1
    assert pl.active(db, "seo_lesson_match")["source"] == "code_default"
    _seed_seo_history(db)
    sandbox = _run(db, "improve.sandbox")
    assert sandbox["ran"]
    with db.session() as s:
        rows = list(s.scalars(select(Improvement).where(
            Improvement.state == "promoted")))
        assert rows, sandbox
        promoted = [r for r in rows if (r.evidence or {}).get("sandbox_trial") == pl.TRIAL]
        assert len(promoted) == 1, sandbox
        row = promoted[0]
        return {"iid": row.id, "change": dict(row.evidence["change"]),
                "baseline": row.baseline_value, "result": row.result_value,
                "evidence": dict(row.evidence)}


def test_seo_loop_closes_end_to_end_and_the_next_listing_decides_differently():
    from brambleloop.core.models import ConfigVersion
    from brambleloop.improve import policy_loops as pl
    from brambleloop.learn.models import LearnDecision, LearnPolicyLesson, LearnProposal

    db = _db()
    got = _promote_seo(db)
    change, ev = got["change"], got["evidence"]
    # Proposal: min_shared 2 -> 3, measured on the frozen observed decisions.
    assert change["loop"] == "seo_lesson_match"
    assert change["params_from"] == {"min_shared": 2} and change["params_to"] == {"min_shared": 3}
    assert got["result"] > got["baseline"] + pl.GAIN_MARGIN, got
    # Independent evaluation and the pipeline's own evidence.
    assert ev["proposed_by"] == "experiment_designer" and ev["approved_by"] == "evaluator"
    assert ev["tests"]["regression_test"]["passed"] and ev["tests"]["adversarial_test"]["passed"]
    assert ev["sandbox"]["trial"] == pl.TRIAL and ev["executed"]
    # F-919: the cross-agent challenger reviewed it before it entered the pipeline.
    assert change["challenge"]["by"] == "quality" and change["challenge"]["upheld"]
    with db.session() as s:
        assert s.get(ConfigVersion, change["config_id"]).incumbent is True
        assert s.get(ConfigVersion, change["replaces"]).incumbent is False
        prop = s.scalar(select(LearnProposal).where(
            LearnProposal.improvement_id == got["iid"]))
        assert prop.state == pl.PROMOTED and prop.baseline == got["baseline"]
        kinds = {r.kind for r in s.scalars(select(LearnPolicyLesson))}
        assert "promoted" in kinds
    print("OK  proposal -> sandbox -> independent judge -> promotion recorded")

    # The consumer runtime.release calls reads the promoted value...
    assert pl.active(db, "seo_lesson_match")["value"] == 3
    # ...and the next listing decision is different: the 2-word match no longer takes a slot,
    # the 4-word match still does.
    assert _decide(db, "probe-after", "B") == []
    assert len(_decide(db, "probe-after-a", "A")) == 1
    with db.session() as s:
        d = s.scalar(select(LearnDecision).where(LearnDecision.subject == "probe-after"))
        assert d.params == {"min_shared": 3} and d.config_id == change["config_id"]
        assert d.action["applied"] is False and d.features["max_shared"] == 2
    # Reachability: the live listing.seo handler calls this exact consumer.
    release_src = (ROOT / "src/brambleloop/runtime/release.py").read_text()
    assert 'consume.matching(ctx.db, "seo_search"' in release_src
    print("OK  later run behaves differently: the promoted threshold is what listing.seo reads")


def test_a_regressing_promotion_is_rolled_back_verified_and_remembered():
    from brambleloop.core.models import ConfigVersion, Improvement, Incident
    from brambleloop.improve import policy_loops as pl
    from brambleloop.learn.models import LearnPolicyLesson, LearnProposal

    db = _db()
    got = _promote_seo(db)
    iid, change = got["iid"], got["change"]
    # Post-change outcomes regress: decisions taken under the promoted policy do badly.
    fresh = 0
    for i in range(4):
        for group in "AC":
            slug = f"fresh-{group.lower()}-{i}"
            _decide(db, slug, group)
            _listing_outcome(db, slug, 0.005)
            fresh += 1
    assert fresh >= pl.MIN_FRESH
    mon = _run(db, "improve.monitor")
    assert iid in mon["reverted"], mon
    with db.session() as s:
        assert s.get(Improvement, iid).state == "reverted"
        assert s.get(ConfigVersion, change["replaces"]).incumbent is True
        assert s.get(ConfigVersion, change["config_id"]).incumbent is False
        assert s.scalar(select(Incident).where(
            Incident.signature == f"improve-rollback:{iid}")) is not None
        prop = s.scalar(select(LearnProposal).where(LearnProposal.improvement_id == iid))
        assert prop.state == pl.ROLLED_BACK
        lesson = s.scalar(select(LearnPolicyLesson).where(
            LearnPolicyLesson.kind == "rolled_back"))
        assert lesson is not None and lesson.params == {"min_shared": 3}
    # Verified restored: the consumer reads the old threshold and decides as before.
    assert pl.active(db, "seo_lesson_match")["config_id"] == change["replaces"]
    assert len(_decide(db, "probe-restored", "B")) == 1
    print("OK  regression -> rollback executed, verified at the consumer, incident opened")

    # Memory changes the next decision: the rolled-back value is not proposed again even
    # where the evaluation would still favour it.
    lp = pl.loop("seo_lesson_match")
    rows = [r for r in pl._decisions(db, lp.key) if r["outcome"] is not None]
    inc = pl.active(db, lp.key)
    out = pl._consider(db, lp, 3, proposed_by=lp.proposer, now=datetime.now(timezone.utc),
                       rows=rows, inc=inc)
    verdict = pl.compare(lp, pl.evaluate(db, lp.key, 2, rows=rows),
                         pl.evaluate(db, lp.key, 3, rows=rows))
    if verdict["promote"]:
        assert out["state"] == pl.MEMORY_SKIPPED, out
    else:
        assert out["state"] == pl.NO_GAIN, out
    cycle = pl.cycle(db)
    with db.session() as s:
        again = [p for p in s.scalars(select(LearnProposal).where(
            LearnProposal.state == pl.PROPOSED))]
        assert not [p for p in again if p.params_to == {"min_shared": 3}], again
    assert cycle["loops"]["seo_lesson_match"]["reading"] == "measured"
    print(f"OK  persisted lesson stops the rolled-back value being re-proposed "
          f"(state {out['state']})")


def test_proposals_touching_protected_thresholds_are_refused_and_audited():
    from brambleloop.core.models import AuditLog, ConfigVersion, Improvement
    from brambleloop.improve import invariants
    from brambleloop.improve import policy_loops as pl
    from brambleloop.learn.models import LearnPolicyLesson, LearnProposal

    db = _db()
    attempts = [
        ("seo_lesson_match", {"min_evidence_rows": 0}, "evidence_requirements"),
        ("release_cost_watch", {"daily_cost_ceiling_cad": 500.0}, "spend_controls"),
        ("visual_gate_precheck", {"asset_truth_pass_threshold": 0.1}, "product_truth"),
        ("pattern_defect_watch", {"REGRESSION_TOLERANCE": 0.5}, "evidence_requirements"),
        ("support_lesson_match", {"escalation_threshold": 0.9}, "customer_safety"),
        ("seo_lesson_match", {"owner_approval_required": 0}, "authorization"),
        ("release_cost_watch", {"ledger_reconciliation_tolerance_cad": 50}, "accounting_truth"),
        ("seo_lesson_match", {"csp_strictness": 0}, "security"),
        ("visual_gate_precheck", {"min_shared": 2}, "undeclared_surface"),
        ("no_such_loop", {"min_shared": 1}, "undeclared_surface"),
        ("seo_lesson_match", {"min_shared": 0}, "hard_bounds"),
        ("seo_lesson_match", {"min_shared": 2.5}, "malformed_value"),
    ]
    assert attempts
    for key, params, expected in attempts:
        out = pl.submit(db, key, params, proposed_by="growth_agent")
        assert out["state"] == pl.REFUSED, (key, params, out)
        assert out["refusals"][0]["invariant"] == expected, (params, out)
    with db.session() as s:
        refused = list(s.scalars(select(LearnProposal).where(
            LearnProposal.state == pl.REFUSED)))
        audited = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "learn.improve.invariant_refused"))
        assert len(refused) == len(attempts) and audited == len(attempts)
        assert s.scalar(select(func.count()).select_from(Improvement)) == 0
        assert s.scalar(select(func.count()).select_from(ConfigVersion)) == 0
        assert s.scalar(select(func.count()).select_from(LearnPolicyLesson).where(
            LearnPolicyLesson.kind == "refused")) == len(attempts)
    for lp in pl.LOOPS:
        assert pl.active(db, lp.key)["source"] == "code_default"
    print(f"OK  {len(attempts)} protected/undeclared/out-of-bounds proposals refused, "
          f"recorded and audited; nothing reached the registry")

    # Defence at execution: a change payload that names a protected threshold never runs.
    from brambleloop.improve import cells

    iid = cells.propose(db, cell="finance", hypothesis=(
        "setting release cost watch flag value should improve the cost per release watch "
        "metric on observed releases"), expected_effect="x", rollback_ref="config:0",
        touches=("score",), proposed_by="cost_optimiser", trial=pl.TRIAL,
        trial_metric="release_cost_watch", higher_is_better=True, baseline=0.1,
        change={"loop": "release_cost_watch", "config_id": 0, "replaces": 0,
                "params_to": {"daily_cost_ceiling_cad": 900}, "params_from": {}})
    try:
        pl.execute(db, iid)
        raise AssertionError("executor ran a protected change")
    except pl.LoopRefused as exc:
        assert "invariant" in str(exc)
    # Defence at read: a tampered registry value outside bounds is not used.
    from brambleloop.improve import league

    league.register(db, kind=pl.KIND, key="learn.seo_lesson_match",
                    payload=json.dumps({"min_shared": 99}),
                    why_changed="tampered value written outside the loop for this test",
                    affected_departments=("seo_search",), incumbent=True)
    reads = pl.active(db, "seo_lesson_match")
    assert reads["value"] == 2 and reads["source"] == "code_default"
    assert "hard bounds" in reads["refused_registry_value"]["why"]
    # And no loop may declare a protected parameter tunable.
    for lp in pl.LOOPS:
        assert invariants.protected_invariant(lp.param) is None, lp.param
    print("OK  executor and consumer read both re-check the invariant guard")


def test_capability_monitor_no_longer_reverts_a_trial_promotion_on_paper():
    """D-B1: `monitor.sweep` judged trial-metric promotions in capability units and wrote
    REVERTED without the rollback executor -- the promoted configuration kept running."""
    from brambleloop.core.models import Improvement
    from brambleloop.improve import cells, monitor

    db = _db()
    iid = cells.propose(db, cell="runtime", hypothesis=(
        "replacing job priority policy version one with challenger version two should meet "
        "more deadlines on the replay"), expected_effect="on-time share rises",
        rollback_ref="config:1", touches=("priority",), proposed_by="prompt_tool_challenger",
        trial="league_replay", trial_metric="replay_on_time:x", higher_is_better=True,
        baseline=0.5, change={"config_id": 2, "replaces": 1})
    with db.session() as s:
        row = s.get(Improvement, iid)
        row.state, row.result_value = "promoted", 0.6
        row.promoted_at = datetime.now(timezone.utc) - timedelta(hours=1)
    # The daily measurer writes the runtime cell's own metric: dead letters per day.
    cells.record_capability(db, "runtime", 0.0, detail={"from": "improve.measure"})
    out = monitor.sweep(db)
    with db.session() as s:
        assert s.get(Improvement, iid).state == "promoted"
    assert [e["improvement"] for e in out["trial_judged_elsewhere"]] == [iid]
    print("OK  a trial-metric promotion is left to runner.monitor_trials (D-B1)")


def test_predictor_loop_promotes_from_visual_gate_outcomes():
    from brambleloop.core.models import ListingAsset
    from brambleloop.improve import policy_loops as pl

    db = _db()
    start = datetime.now(timezone.utc) - timedelta(days=30)
    # Hero photos are blocked by the visual gate 40% of the time; detail charts never.
    hero = [1, 0, 1, 0, 0] * 4
    chart = [0] * 20
    seq = []
    for i in range(20):
        seq.append(("photo", "hero", hero[i]))
        seq.append(("chart", "detail", chart[i]))
    assert seq
    with db.session() as s:
        for n, (cls, role, blocked) in enumerate(seq):
            s.add(ListingAsset(product_slug=f"p{n}", version="1.0.0", position=1,
                               asset_class=cls, role=role, sha256=None, claims={},
                               approved=not blocked,
                               blocked_reasons=["visual gate: test"] if blocked else [],
                               created_at=start + timedelta(hours=n)))
    before = pl.visual_precheck(db)
    assert before["groups"] == {}, before        # 0.4 < the 0.5 default: nothing flagged
    sandbox = _run(db, "improve.sandbox")
    executed = [e for e in sandbox["executed"] if e.get("implements") == "visual_gate_precheck"]
    assert len(executed) == 1 and executed[0]["active_value"] == 0.4, sandbox
    assert [s_["baseline"] < s_["result"] for s_ in sandbox["sandboxed"]] == [True], sandbox
    assert pl.active(db, "visual_gate_precheck")["value"] == 0.4
    after = pl.visual_precheck(db)
    assert after["groups"] == {"photo/hero": 0.4}, after
    from brambleloop.learn import improvement_status

    work = improvement_status.next_work(db)
    assert any(w["kind"] == "visual.precheck" and w["key"] == "visual_precheck:photo/hero"
               for w in work), work
    print("OK  predictor loop: visual gate outcomes -> promoted precheck -> next_work item")


def test_provider_contract_on_empty_and_populated_databases():
    from brambleloop.learn import improvement_status as st

    db = _db()
    empty = st.summary(db)
    for key in ("status", "as_of", "basis", "items", "sources"):
        assert key in empty, key
    assert empty["status"] == "UNKNOWN" and empty["basis"] == "unknown" and empty["reason"]
    assert empty["as_of"] is None
    json.dumps(empty)
    loops_read = empty["items"]
    assert loops_read and len(loops_read) == 5
    for it in loops_read:
        assert it["reading"] == "UNMEASURED" and it["decisions_with_outcome"] == 0
        assert it["active"]["source"] == "code_default"
    work = st.next_work(db)
    assert work and all(w["kind"] == "learn.instrument_loop" for w in work)
    for w in work:
        assert set(w) >= {"kind", "key", "priority", "reason", "evidence"}
        assert 1 <= w["priority"] <= 100
    json.dumps(work)
    print("OK  empty database: UNKNOWN with a reason, never zeros; next_work instruments")

    db2 = _db()
    _promote_seo(db2)
    full = st.summary(db2)
    assert full["status"] in ("OK", "DEGRADED", "BLOCKED", "UNKNOWN")
    assert full["status"] == "DEGRADED" and full["basis"] == "measured" and full["as_of"]
    seo = next(i for i in full["items"] if i["loop"] == "seo_lesson_match")
    assert seo["reading"] == "measured" and seo["active"]["value"] == 3
    assert seo["promotions"] and seo["promotions"][0]["params_to"] == {"min_shared": 3}
    assert full["pipeline"]["improvements_by_trial_and_state"]["policy_loop"]["promoted"] == 1
    assert any(lesson["kind"] == "promoted" for lesson in full["lessons"])
    json.dumps(full)
    print("OK  populated: measured loop, promotion with baseline/result, lessons, DEGRADED "
          "because four loops have no outcomes yet")


def test_guardrail_kpi_and_cross_agent_challenge_refuse_a_gamed_win():
    """F-918 / F-919: a challenger that wins the metric by losing the guardrail is challenged out."""
    from brambleloop.improve import policy_loops as pl

    lp = pl.loop("seo_lesson_match")
    inc = {"shared": {"value": 0.05, "n": 20, "guard": 0.04},
           "holdout": {"value": 0.05, "n": 5, "guard": 0.04}}
    gamed = {"shared": {"value": 0.09, "n": 15, "guard": 0.01},
             "holdout": {"value": 0.06, "n": 4, "guard": 0.01}}
    verdict = pl.compare(lp, inc, gamed)
    assert not verdict["promote"] and any("guardrail" in b for b in verdict["blockers"])
    contest = pl.challenge(lp, {"params_to": {"min_shared": 3}, "incumbent": inc,
                                "challenger": gamed, "proposed_by": lp.proposer})
    assert contest["by"] == "quality" and not contest["upheld"]
    pred = pl.loop("release_cost_watch")
    flood = {"shared": {"value": 0.9, "n": 20, "positives": 5, "guard": 0.9},
             "holdout": {"value": 0.9, "n": 5, "positives": 2, "guard": 0.9}}
    base = {"shared": {"value": 0.5, "n": 20, "positives": 5, "guard": 0.2},
            "holdout": {"value": 0.5, "n": 5, "positives": 2, "guard": 0.2}}
    assert any("review load" in b for b in pl.compare(pred, base, flood)["blockers"])
    for lp_ in pl.LOOPS:
        assert lp_.challenger != lp_.proposer
    print("OK  anti-gaming guardrail and cross-agent challenge refuse a gamed win")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as exc:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                print("FAIL", name, exc)
                fails += 1
    sys.exit(1 if fails else 0)
