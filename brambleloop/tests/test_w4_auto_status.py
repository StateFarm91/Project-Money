"""W4-AUTO: per-agent status provider, Rule #1 measurement and the wave-4 wiring requests.

`autonomy.status.agents(db)` is the per-agent visibility envelope lane CC renders (doing now,
current job, last useful result, produced/rejected, blockers, next work/wake, useful and no-op
rates, cost, state, as_of). `autonomy.rule1.measure(db)` is the Rule #1 judge used by the proof
and the output audit. The wiring requests (W4-MJS, W4-STORE, W4-VISUAL) are asserted here so a
later edit cannot silently un-wire them.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.agents.registry import DEFAULT_AGENTS, Registry  # noqa: E402
from brambleloop.autonomy import orchestrator, rule1, status, visual_rnd_job  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402
from brambleloop.runtime.worker import CADENCES, Worker  # noqa: E402

CONTRACT = {"status", "as_of", "basis", "items", "sources"}
AGENT_FIELDS = {"agent", "department", "state", "doing_now", "started_at", "current_job",
                "last_useful_result", "blockers", "next_work", "next_wake", "completed",
                "useful", "noop", "useful_rate", "noop_rate", "dead"}


def boot() -> Database:
    tmp = tempfile.mkdtemp(prefix="w4auto-")
    db = Database(f"sqlite:///{tmp}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def test_agents_provider_is_unknown_on_an_empty_database():
    db = boot()
    env = status.agents(db)
    assert CONTRACT <= set(env), env
    assert env["status"] == "UNKNOWN" and env["items"] == [], env
    assert env["reason"], env


def test_agents_provider_reports_every_agent_after_real_work():
    db = boot()
    orchestrator.tick(db)
    w = Worker(db, "w")
    ran = 0
    for _ in range(40):
        if not w.run_once():
            break
        ran += 1
    assert ran > 0, "the orchestrator generated no runnable work"
    env = status.agents(db)
    assert CONTRACT <= set(env), env
    assert env["status"] != "UNKNOWN", env
    assert env["as_of"], env
    agent_rows = env["items"]
    assert agent_rows, env
    names = {i["agent"] for i in agent_rows}
    assert names == {a["name"] for a in DEFAULT_AGENTS}, names ^ {a["name"] for a in DEFAULT_AGENTS}
    for i in agent_rows:
        assert AGENT_FIELDS <= set(i), (i["agent"], AGENT_FIELDS - set(i))
        assert i["state"] in ("active", "sleeping", "blocked", "unhealthy"), i
        if i["completed"] == 0:
            # UNKNOWN is never 0: no completions means no rate, not a 0% rate.
            assert i["useful_rate"] is None and i["noop_rate"] is None, i
    assert any(i["completed"] for i in agent_rows), "no agent recorded a completion"


def test_rule1_measure_covers_every_department():
    db = boot()
    orchestrator.tick(db)
    w = Worker(db, "w")
    for _ in range(40):
        if not w.run_once():
            break
    m = rule1.measure(db)
    deps = m["departments"]
    assert len(deps) == 11, sorted(deps)
    for key, e in deps.items():
        assert {"done", "useful", "useful_distinct", "noop", "rule1_defect"} <= set(e) or \
            "eligible_error" in e, (key, e)
        assert e["useful_distinct"] <= e["useful"] <= e["done"], (key, e)
    assert m["totals"]["done"] == sum(e["done"] for e in deps.values())


def test_wiring_mjs_findings_counts_only_changed_findings():
    keys = pipeline.WORK_KEYS["mjs.scan"]
    assert "findings.changed" in keys, keys
    base = {"new": 0, "reclassified": 0, "inspected": 0, "learning_domains": 0}
    assert pipeline.did_no_work({**base, "findings": {"findings": 4, "changed": []}},
                                "mjs.scan")
    assert pipeline.did_no_work({**base, "findings": {"error": "boom"}}, "mjs.scan")
    assert not pipeline.did_no_work({**base, "findings": {"findings": 4, "changed": ["k"]}},
                                    "mjs.scan")


def test_wiring_store_live_drift_is_a_daily_orchestrator_cadence():
    rows = [c for c in CADENCES if c[2] == "store.live_drift"]
    assert rows == [("store_live_drift", "orchestrator", "store.live_drift", 86400)], rows
    names = [c[0] for c in CADENCES]
    assert names.index("store_live_drift") == names.index("etsy_shop_snapshot") + 1, names
    orch = next(a for a in DEFAULT_AGENTS if a["name"] == "orchestrator")
    assert "store.live_drift" in orch["allowed_job_types"]
    assert "store.live_drift" in pipeline.WORK_KEYS
    assert pipeline.did_no_work({"counts": {}, "unknown": 2, "proposals": 0, "findings": 0,
                                 "incidents_opened": [], "writes_performed": 0},
                                "store.live_drift")
    assert not pipeline.did_no_work({"proposals": 0, "findings": 2, "incidents_opened": []},
                                    "store.live_drift")


def test_wiring_visual_rnd_counts_refreshed_launch_imagery():
    report = {"classes": {}, "launch_imagery": {
        "a": {"refreshed": True, "covered": [], "missing": []},
        "b": {"refreshed": False, "covered": [], "missing": []},
        "c": {"refreshed": False, "error": "ValueError: x"}}}
    out = visual_rnd_job.summarise(report)
    assert out["imagery_refreshed"] == 1 and out["imagery_errors"] == 1, out
    assert out["work_done"] == 1, out
    assert not pipeline.did_no_work(out, "visual.rnd.cycle")
    idle = visual_rnd_job.summarise({"classes": {}, "launch_imagery": {
        "b": {"refreshed": False}}})
    assert idle["work_done"] == 0 and pipeline.did_no_work(idle, "visual.rnd.cycle"), idle
    assert visual_rnd_job.summarise({"classes": {}})["work_done"] == 0


def test_judge_counts_drafted_cirs_certificates_and_launch_plans():
    """The W4 before-proof judged Product & Design 0% useful: cir.draft declared `drafted`
    but its success paths never set it. Refusals with reasons are QA output; launch plans
    were undeclared. Each is asserted against the real handler output shape."""
    assert not pipeline.did_no_work({"artifact": "x@1.2.0", "drafted": True, "rows": 56,
                                     "engineered": True}, "cir.draft")
    assert pipeline.did_no_work({"artifact": "x", "drafted": False, "is_bundle": True},
                                "cir.draft")
    assert not pipeline.did_no_work({"artifact": "x@1", "granted": False, "release_hash": None,
                                     "reasons": ["ERROR GAUGE"]}, "gate.certify")
    assert pipeline.did_no_work({"artifact": "x@1", "granted": False, "reasons": []},
                                "gate.certify")
    assert not pipeline.did_no_work({"slug": "x", "launch_on": "2026-10-14"}, "launch.plan")
    assert pipeline.did_no_work({"slug": "x"}, "launch.plan")


def test_cir_draft_handler_reports_drafted_on_the_engineered_path():
    import inspect

    src = inspect.getsource(pipeline.handle_cir_draft)
    assert '"drafted": True' in src, "engineered success path must declare drafted"


def test_gate_blockers_name_who_they_wait_on_from_the_closure_classifier():
    """W4-GATESB: a data/external/unclassified gate is never shown as waiting on the owner."""
    from brambleloop.build2 import closure

    samples = {"owner": sorted(closure.OWNER_GATES), "data": sorted(closure.DATA_GATES),
               "external": sorted(closure.EXTERNAL_GATES)}
    assert all(samples.values()), samples
    for waiting_on, keys in samples.items():
        for g in keys:
            b = status.gate_blocker(g)
            assert b["waiting_on"] == waiting_on and b["kind"] == f"{waiting_on}_gate", b
            assert b["closure_kind"] == closure.kind_of(g), b
    b = status.gate_blocker("nobody.classified.this")
    assert b["waiting_on"] == "company" and b["closure_kind"] == "UNCLASSIFIED", b
    db = boot()
    from brambleloop.queue.durable import JobQueue

    q = JobQueue(db)  # the summary needs one recorded job, else it is honestly UNKNOWN
    q.enqueue("orchestrator", "ops.capacity", {"probe": 1})
    job = q.claim("w", job_types=["ops.capacity"])
    assert job is not None
    q.complete(job.id, {"probe": 1})
    gate_blks = [blk for row in status.summary(db)["items"] for blk in row.get("blockers", [])
                 if blk.get("gate")]
    assert gate_blks, "a fresh shadow company has closed gates; none reached the summary"
    for blk in gate_blks:
        assert blk["kind"] == f"{blk['waiting_on']}_gate", blk


def test_fm2_openapi_reverify_is_scheduled_authorised_banded_and_judged():
    """W4-FM2 F-514: the weekly OpenAPI re-verification runs by itself."""
    from brambleloop.runtime.worker import handlers
    from brambleloop.swarm import orchestrate

    jt = "etsy.openapi_reverify"
    sched = [c for c in CADENCES if c[2] == jt]
    assert len(sched) == 1 and sched[0][1] == "orchestrator", sched
    assert sched[0][3] == 7 * 24 * 60 * 60, sched
    orch = next(a for a in DEFAULT_AGENTS if a["name"] == "orchestrator")
    assert jt in orch["allowed_job_types"]
    assert handlers.get(jt) is not None, "no handler registered for the cadence"
    assert orchestrate.band_for(jt)["mapped"]
    assert pipeline.WORK_KEYS[jt] == ("affected",)
    assert pipeline.did_no_work({"status": "current", "affected": 0, "writes_performed": 0}, jt)
    assert not pipeline.did_no_work({"status": "drift", "affected": 2, "writes_performed": 0},
                                    jt)


def test_long_read_only_analysis_does_not_starve_the_release_chain_at_boot():
    """W4-CHAIN residual: maturity analysis is deferred at boot and banded behind the chain."""
    from datetime import timedelta

    from brambleloop.core.models import Job
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import worker as wm
    from brambleloop.swarm import orchestrate

    jt = "ops.maturity_disagreements"
    assert jt in wm.BOOT_DEFERRED_SECONDS
    chain = ("chain.rebuild", "cir.draft", "gate.certify", "assets.build")
    assert chain
    for c in chain:
        assert orchestrate.priority_for(jt) > orchestrate.priority_for(c), c
    started = wm.utcnow()
    assert wm.boot_deferred_run_after(jt, started + timedelta(seconds=5),
                                      started_at=started) is not None
    assert wm.boot_deferred_run_after(
        jt, started + timedelta(seconds=wm.BOOT_DEFERRED_SECONDS[jt] + 1),
        started_at=started) is None
    assert wm.boot_deferred_run_after("chain.rebuild", started, started_at=started) is None
    # The real scheduler, right after process start: the analysis is enqueued but not yet due,
    # and a release-chain job enqueued at the same time is what the worker claims.
    db = boot()
    wm.Scheduler(db).tick(now=wm.PROCESS_STARTED_AT + timedelta(seconds=1))
    with db.session() as s:
        rows = [r for r in s.query(Job).filter(Job.job_type == jt)]
    assert rows, "the maturity cadence was not enqueued"
    ra = rows[0].run_after if rows[0].run_after.tzinfo else \
        rows[0].run_after.replace(tzinfo=wm.PROCESS_STARTED_AT.tzinfo)
    assert ra >= wm.PROCESS_STARTED_AT + timedelta(
        seconds=wm.BOOT_DEFERRED_SECONDS[jt] - 1), ra
    q = JobQueue(db)
    q.enqueue("orchestrator", "chain.rebuild", {"probe": 1},
              priority=orchestrate.priority_for("chain.rebuild"))
    claimed = q.claim("w", job_types=[jt, "chain.rebuild"])
    assert claimed is not None and claimed.job_type == "chain.rebuild", claimed


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK", name)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            fails += 1
            print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
