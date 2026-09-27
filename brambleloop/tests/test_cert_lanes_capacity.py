"""C-68: lane controls that decide something at the claim (#5, #30, #175, #188).

The audit of 9434c53 found every capacity decision recorded and none acted on: one worker
thread meant a lane limit could never hold, the #30 function mix was a weekly row nobody read,
the Fast/Flagship label drove no capacity, and the governor's parallelism advice could only
lower a limit. Every test here runs jobs through `Worker.run_once` (or a registered handler with
a real database) and asserts what the worker then did.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

os.environ["BRAMBLELOOP_WORKER_THREADS"] = "3"

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, CostEntry, Job, JobStatus, SwarmAllocation, utcnow,
)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import JobContext, Worker, handlers  # noqa: E402
from brambleloop.scale import allocation as mixmod  # noqa: E402
from brambleloop.swarm import capacity as cap  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/lanes.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _running(db, agent, job_type, inputs=None, worker="other-worker"):
    with db.session() as s:
        j = Job(agent=agent, job_type=job_type, inputs=inputs or {}, status=JobStatus.RUNNING,
                leased_by=worker, lease_expires_at=utcnow() + timedelta(minutes=10),
                started_at=utcnow(), attempts=1)
        s.add(j)
        s.flush()
        return j.id


def _enqueue(db, agent, job_type, inputs, priority, key):
    return JobQueue(db).enqueue(agent, job_type, inputs, idempotency_key=key,
                                priority=priority).id


def _held(db) -> list[AuditLog]:
    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == orc.LANE_HELD_ACTION)))
        for r in rows:
            s.expunge(r)
        return rows


def _status(db, job_id):
    with db.session() as s:
        return s.get(Job, job_id).status


def _capacity_reading(db, mix):
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action="ops.capacity",
                       detail={"mix": mix, "phase": "build", "tilted_toward": None}))


# ---- #30: the function mix is enforced on work -------------------------------------------


def test_a_function_over_its_share_is_held_while_distribution_waits():
    db = _db()
    _capacity_reading(db, dict(mixmod.BUILD_MIX))
    # Infrastructure already holds its one worker of three.
    _running(db, "orchestrator", "ops.health")
    infra = _enqueue(db, "orchestrator", "ops.queue_check", {}, 0, "infra")
    dist = _enqueue(db, "support", "support.triage", {}, 50, "dist")

    w = Worker(db, "pool-1")
    assert w.run_once()
    held = _held(db)
    assert len(held) == 1 and held[0].job_id == infra, [h.detail for h in held]
    assert held[0].detail["hold_kind"] == "function_share"
    assert "distribution" in held[0].detail["why"]
    assert _status(db, infra) == JobStatus.PENDING, "a held job goes back unchanged"
    # The next claim is the starved function's job, which runs.
    assert w.run_once()
    assert _status(db, dist) == JobStatus.DONE


def test_the_mix_is_work_conserving_when_nothing_else_waits():
    db = _db()
    _capacity_reading(db, dict(mixmod.BUILD_MIX))
    _running(db, "orchestrator", "ops.health")
    infra = _enqueue(db, "orchestrator", "ops.queue_check", {}, 0, "infra-alone")
    assert Worker(db, "pool-1").run_once()
    assert not _held(db)
    assert _status(db, infra) == JobStatus.DONE


def test_a_function_over_its_measured_share_yields_while_the_pool_is_in_use():
    """C-80 defect 4: at pool 3 every slot budget is one, so the mix must bind on measured
    job-seconds. Infrastructure has run the whole window; with the pool in use, its next job
    yields to distribution's waiting work even though it holds no slot yet."""
    db = _db()
    _capacity_reading(db, dict(mixmod.BUILD_MIX))
    now = utcnow()
    with db.session() as s:
        for i in range(3):
            s.add(Job(agent="orchestrator", job_type="ops.dependencies", inputs={},
                      status=JobStatus.DONE, started_at=now - timedelta(hours=i + 2),
                      finished_at=now - timedelta(hours=i + 1)))
    _running(db, "market_radar", "radar.scan")          # the pool is in use
    infra = _enqueue(db, "orchestrator", "ops.queue_check", {}, 0, "infra-window")
    dist = _enqueue(db, "support", "support.triage", {}, 50, "dist-window")

    w = Worker(db, "pool-1")
    assert w.run_once()
    held = _held(db)
    assert [h.job_id for h in held] == [infra], [h.detail for h in held]
    assert held[0].detail["hold_kind"] == "function_share"
    share = held[0].detail["share"]
    assert share["running_by_function"]["infrastructure"] == 0, "no slot was held: the window bound"
    assert share["window"]["status"] == "MEASURED"
    assert share["window"]["shares"]["infrastructure"] == 1.0
    assert "job-seconds" in held[0].detail["why"] and "distribution" in held[0].detail["why"]
    assert _status(db, infra) == JobStatus.PENDING
    assert w.run_once()
    assert _status(db, dist) == JobStatus.DONE


def test_the_measured_share_does_not_reorder_an_idle_pool():
    """With nothing else running, the one worker runs the job priority gave it: the window
    shares capacity, it does not replace the queue order (and a serial drain never stalls)."""
    db = _db()
    _capacity_reading(db, dict(mixmod.BUILD_MIX))
    now = utcnow()
    with db.session() as s:
        s.add(Job(agent="orchestrator", job_type="ops.dependencies", inputs={},
                  status=JobStatus.DONE, started_at=now - timedelta(hours=2),
                  finished_at=now - timedelta(hours=1)))
    infra = _enqueue(db, "orchestrator", "ops.queue_check", {}, 0, "infra-idle")
    _enqueue(db, "support", "support.triage", {}, 50, "dist-idle")
    assert Worker(db, "pool-1").run_once()
    assert not _held(db)
    assert _status(db, infra) == JobStatus.DONE


def test_function_budgets_share_the_pool_by_largest_remainder():
    """Slot budgets: at least one each, the rest of the pool to the most under-served share."""
    assert cap.function_budgets(mixmod.BUILD_MIX, 3) == {
        "product_qa": 1, "market_intelligence": 1, "distribution": 1, "infrastructure": 1}
    # 3.15/1.4/1.4/1.05 -> floors 3/1/1/1 and the seventh slot to the largest remainder;
    # market intelligence and distribution tie, and distribution wins the tie (#30's point)
    assert cap.function_budgets(mixmod.BUILD_MIX, 7) == {
        "product_qa": 3, "market_intelligence": 1, "distribution": 2, "infrastructure": 1}
    assert cap.function_budgets(mixmod.MATURE_MIX, 10) == {
        "product_qa": 3, "market_intelligence": 3, "distribution": 3, "infrastructure": 1}


# ---- #5: the production lanes split making capacity --------------------------------------


def _route(db, slug, lane):
    with db.session() as s:
        s.add(AuditLog(actor="quality_director", action=cap.LANE_ROUTED_ACTION,
                       artifact=f"{slug}@1.0.0", detail={"lane": lane}))


def test_a_lane_over_its_engineering_share_is_held_while_the_other_lane_waits():
    db = _db()
    _route(db, "fast-a", "fast")
    _route(db, "fast-b", "fast")
    _route(db, "flag-c", "flagship")
    _running(db, "publishing", "assets.build", {"slug": "fast-a"})
    fast_next = _enqueue(db, "publishing", "assets.build", {"slug": "fast-b"}, 0, "fb")
    flag_next = _enqueue(db, "publishing", "assets.build", {"slug": "flag-c"}, 50, "fc")

    assert Worker(db, "pool-2").run_once()
    held = _held(db)
    assert [h.job_id for h in held] == [fast_next], [h.detail for h in held]
    assert held[0].detail["hold_kind"] == "lane_share"
    share = held[0].detail["share"]
    assert share["lane"] == "fast" and share["lane_limits"] == {"fast": 1, "flagship": 1}
    assert _status(db, fast_next) == JobStatus.PENDING
    # the flagship job is what the worker claims next (it may fail on a fixture slug; what
    # matters is that it was the one claimed, not held)
    Worker(db, "pool-2").run_once()
    with db.session() as s:
        assert s.get(Job, flag_next).attempts >= 1
    assert len(_held(db)) == 1


def test_certification_jobs_carrying_the_cir_are_counted_against_their_lane():
    """C-80 defect 3: cir.compile and gate.certify carry {"cir": {...}}, not a bare slug, and
    were never lane-counted. A running gate.certify on a fast product fills the fast lane, and
    the next fast cir.compile is held while flagship engineering waits."""
    db = _db()
    _route(db, "fast-a", "fast")
    _route(db, "fast-b", "fast")
    _route(db, "flag-c", "flagship")
    running = _running(db, "quality_director", "gate.certify", {"cir": {"slug": "fast-a"}})
    with db.session() as s:
        assert cap.slug_of(s.get(Job, running)) == "fast-a"
    fast_next = _enqueue(db, "crochet_engineer", "cir.compile", {"cir": {"slug": "fast-b"}},
                         0, "fb-cir")
    flag_next = _enqueue(db, "publishing", "assets.build", {"slug": "flag-c"}, 50, "fc-cir")

    assert Worker(db, "pool-2").run_once()
    held = _held(db)
    assert [h.job_id for h in held] == [fast_next], [h.detail for h in held]
    assert held[0].detail["hold_kind"] == "lane_share"
    assert held[0].detail["share"]["lane"] == "fast"
    assert held[0].detail["share"]["lane_running"] == 1, "the running gate.certify was counted"
    assert _status(db, fast_next) == JobStatus.PENDING
    Worker(db, "pool-2").run_once()
    with db.session() as s:
        assert s.get(Job, flag_next).attempts >= 1
    # the measured split reads the same inputs
    with db.session() as s:
        s.add(Job(agent="quality_director", job_type="gate.certify",
                  inputs={"cir": {"slug": "flag-c"}}, status=JobStatus.DONE,
                  started_at=utcnow() - timedelta(minutes=10), finished_at=utcnow()))
    assert cap.measured_lane_split(db)["seconds"].get("flagship", 0) > 0


def test_gate_lanes_counts_a_collection_from_its_certified_family_and_records_the_split():
    from tests.test_cert_preengineering import _certify, _ctx

    db = _db()
    # the two nordic-forest members this repository can engineer, and one lone throw
    for slug in ("nordic-forest-mosaic-throw", "nordic-star-ornaments",
                 "autumn-oak-mosaic-throw"):
        _certify(db, slug)
    out = handlers.get("gate.lanes")(_ctx(db, "quality_director", "gate.lanes",
                                          {"as_of": "2026-09-17"}))
    with db.session() as s:
        routed = {r.artifact.split("@")[0]: r.detail for r in s.scalars(
            select(AuditLog).where(AuditLog.action == cap.LANE_ROUTED_ACTION))}
        capacity = s.scalar(select(AuditLog).where(
            AuditLog.action == cap.LANE_CAPACITY_ACTION)).detail
    for slug in ("nordic-forest-mosaic-throw", "nordic-star-ornaments"):
        assert routed[slug]["profile"]["pattern_count"] == 2, routed[slug]["profile"]
        assert routed[slug]["profile"]["sizes"] == 1
    assert routed["autumn-oak-mosaic-throw"]["profile"]["pattern_count"] == 1
    # lanes.allocate's split, recorded for the claim. The three gate.certify runs above carry
    # the CIR (inputs.cir.slug) and are now counted (C-80 defect 3), so the split run so far
    # is measured -- strengthened from the earlier UNMEASURED, which was the uncounted bug.
    assert capacity["shares"] == {"fast": 0.6, "flagship": 0.4}
    assert capacity["measured_status"] == "measured", capacity["measured"]
    assert capacity["measured"]["total"] > 0 and set(capacity["measured"]["seconds"]) <= {
        "fast", "flagship"}
    assert capacity["boosted_jobs"] == [], "nothing was queued, so nothing is moved"
    assert out["lane_capacity"]["units"]


def test_size_depth_is_read_from_the_certified_size_run_not_a_constant():
    """C-80 defects 1 and 2: a graded garment's size depth is the number of certified sizes of
    its design (shared provenance concept_key, cir.graded), read by gate.lanes from the
    catalogue; a lone release is a run of one, and the basis is recorded with the profile."""
    from tests.test_cert_preengineering import _certify, _ctx

    from brambleloop.cir.graded import size_run
    from brambleloop.cir.model import CIR
    from brambleloop.core.models import PatternVersion, Product
    from brambleloop.products import garments

    db = _db()
    _certify(db, "nordic-forest-mosaic-throw")
    design = garments.pebble_cardigan()
    sizes = design.sourced_sizes()
    first = CIR.from_dict({**design.build(sizes[0]).to_dict(), "slug": "cropped-cardigan"})
    assert first.provenance is not None and "cir.graded" in first.provenance.primitives_used

    def certified(cir):
        with db.session() as s:
            product = Product(slug=cir.slug, title=cir.title, status="certified",
                              risk_class=cir.risk_class)
            s.add(product)
            s.flush()
            s.add(PatternVersion(product_id=product.id, version=cir.version,
                                 cir_json=cir.to_dict(), release_hash="h" * 12, certified=True,
                                 certificate={"granted": True,
                                              "stages_run": ["compile", "reverse"]}))

    certified(first)
    out = handlers.get("gate.lanes")(_ctx(db, "quality_director", "gate.lanes",
                                          {"as_of": "2026-09-17"}))
    routed = {c["slug"]: c for c in out["routing"]["products"]} if "routing" in out else None
    with db.session() as s:
        routed = {r.artifact.split("@")[0]: r.detail for r in s.scalars(
            select(AuditLog).where(AuditLog.action == cap.LANE_ROUTED_ACTION))}
    assert routed["cropped-cardigan"]["profile"]["sizes"] == 1
    assert routed["cropped-cardigan"]["profile"]["sizes_basis"].startswith("graded run")
    assert routed["nordic-forest-mosaic-throw"]["profile"]["sizes"] == 1
    assert routed["nordic-forest-mosaic-throw"]["profile"]["sizes_basis"].startswith(
        "a single release")

    # a second certified size of the same design: the run is two, read from the catalogue
    certified(design.build(sizes[1]))
    handlers.get("gate.lanes")(_ctx(db, "quality_director", "gate.lanes",
                                    {"as_of": "2026-09-17"}))
    with db.session() as s:
        latest = {}
        for r in s.scalars(select(AuditLog).where(AuditLog.action == cap.LANE_ROUTED_ACTION)
                           .order_by(AuditLog.id)):
            latest[r.artifact.split("@")[0]] = r.detail
        catalogue = [pv.cir_json for pv in s.scalars(select(PatternVersion))]
    assert latest["cropped-cardigan"]["profile"]["sizes"] == 2, latest["cropped-cardigan"]
    run = size_run(first.to_dict(), catalogue)
    assert run["status"] == "MEASURED" and sorted(run["run"]) == sorted(
        ["cropped-cardigan", design.build(sizes[1]).slug])
    assert size_run({"title": "x"}, catalogue)["status"] == "UNMEASURED"


def test_a_starved_lane_has_its_queued_engineering_moved_up():
    db = _db()
    _route(db, "fast-a", "fast")
    _route(db, "flag-c", "flagship")
    now = utcnow()
    with db.session() as s:
        # a week of fast-only engineering: flagship's measured share is 0, below its floor
        for i in range(3):
            s.add(Job(agent="publishing", job_type="assets.build", inputs={"slug": "fast-a"},
                      status=JobStatus.DONE, started_at=now - timedelta(hours=i + 2),
                      finished_at=now - timedelta(hours=i + 1)))
    waiting = _enqueue(db, "publishing", "assets.build", {"slug": "flag-c"},
                       orc.priority_for("assets.build"), "starved")
    from brambleloop.commerce import lanes

    q = JobQueue(db)
    ctx = JobContext(job=q.enqueue("quality_director", "gate.lanes", {}), db=db, queue=q,
                     registry=Registry(db), phase=None)
    detail = release._lane_capacity(ctx, lanes)
    assert detail["starved"] == ["flagship"] and detail["mix_check"]["ok"] is False
    assert detail["boosted_jobs"] == [waiting]
    with db.session() as s:
        assert s.get(Job, waiting).priority == orc.priority_for("assets.build") - 5


# ---- #175 / #188: the allocation activates workers and scales both ways -------------------


def test_allocation_reads_category_season_value_and_bottleneck_and_sets_the_worker_target():
    db = _db()
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action="ops.capacity",
                       detail={"mix": mixmod.MATURE_MIX, "tilted_toward": "distribution"}))
    q = JobQueue(db)
    q.enqueue("orchestrator", "seasonal.sentinel", {}, idempotency_key="s1",
              priority=orc.priority_for("seasonal.sentinel"))
    q.enqueue("support", "support.reply", {"question": "x"}, idempotency_key="s2",
              priority=orc.priority_for("support.reply"))
    q.enqueue("market_radar", "radar.scan", {}, idempotency_key="s3",
              priority=orc.priority_for("radar.scan"))
    out = orc.allocate(db)
    lanes = out["lanes"]
    assert lanes["support"]["function"] == "distribution"
    assert lanes["support"]["deadline_pressure"] is True       # a customer reply
    assert lanes["orchestrator"]["deadline_pressure"] is True  # a seasonal deadline
    assert any("bottleneck" in b for b in lanes["support"]["boosts"])
    # value and deadline move the grant above what queue depth alone wanted, inside the money
    assert lanes["orchestrator"]["granted"] > lanes["orchestrator"]["wanted"]
    assert lanes["support"]["granted"] <= int(lanes["support"]["cad_available_now"] / 0.05) \
        or lanes["support"]["granted"] == 0
    assert out["workers"]["target"] == 3, out["workers"]      # three lanes with work, pool 3


def test_parallelism_advice_scales_the_worker_target_and_lane_limit_up_and_down():
    db = _db()
    q = JobQueue(db)
    q.enqueue("support", "support.triage", {}, idempotency_key="a", priority=70)
    orc.allocate(db)
    base = cap.worker_target(db)["target"]
    lane = orc.lane_concurrency(db, "support")["limit"]
    assert base == 1 and lane == 1

    def advise(advice):
        with db.session() as s:
            s.add(AuditLog(actor="cfo", action=orc.GOVERNOR_ACTION,
                           detail={"parallelism": {"advice": advice, "why": "test"}}))

    advise("scale_up")
    assert cap.worker_target(db)["target"] == min(3, base + 1)
    assert orc.lane_concurrency(db, "support")["limit"] == lane + 1
    advise("scale_down")
    assert cap.worker_target(db)["target"] == 1
    assert orc.lane_concurrency(db, "support")["limit"] == 1


def test_the_runner_starts_a_pool_and_activates_only_the_target():
    os.environ["BRAMBLELOOP_RUNNER_START_DELAY"] = "0"
    import importlib

    from brambleloop.app import runner

    runner = importlib.reload(runner)
    db = _db()
    try:
        runner.start(db)
        worker_threads = [t for t in runner._threads if "worker_loop" in t.name]
        assert len(worker_threads) == 3
        assert runner.STATE.worker_pool == 3
        assert runner.wait_for_tick(10)
    finally:
        runner.stop()
    target = runner._Target(db, 3)
    assert target.get() == 1, "no allocation: one worker, never none"


def test_experiment_spend_is_attributed_from_the_spending_job():
    from brambleloop.finance import governor

    db = _db()
    with db.session() as s:
        tagged = Job(agent="growth", job_type="growth.experiments",
                     inputs={"experiment": "exp-7"}, status=JobStatus.DONE)
        explore = Job(agent="creative_director", job_type="creative.blinded", inputs={},
                      status=JobStatus.DONE)
        committed = Job(agent="listing", job_type="listing.seo", inputs={},
                        status=JobStatus.DONE)
        s.add_all([tagged, explore, committed])
        s.flush()
        for j, amt in ((tagged, 0.5), (explore, 0.25), (committed, 0.1)):
            s.add(CostEntry(agent=j.agent, amount_cad=amt, job_id=j.id))
    with db.session() as s:
        out = governor.spend_by(s, "experiment")
    rows = {r["key"]: r["cad"] for r in out["rows"]}
    # C-80 defect 13 (Codex P13): only a tagged experiment is an experiment row, and it says
    # so; the exploration-band spend is a proxy bucket of its own, never an experiment key.
    assert rows == {"exp-7": 0.5}, rows
    assert {r["key"]: r["basis"] for r in out["rows"]} == {"exp-7": governor.BASIS_TAGGED}
    assert out["proxy"]["basis"] == governor.BASIS_BAND_PROXY
    assert {r["key"]: r["cad"] for r in out["proxy"]["rows"]} == {
        "exploration:creative.blinded": 0.25}
    assert abs(out["unattributed_cad"] - 0.1) < 1e-9 and out["has_writer"] is True
    assert abs(out["total_cad"] - 0.85) < 1e-9, "rows + proxy + unattributed reconcile"


def test_the_new_rule_sees_the_capacity_path_live():
    from brambleloop.build2 import reachability as R

    R.clear_cache()
    for rel, fn in (("swarm/capacity.py", "share_decision"),
                    ("swarm/capacity.py", "worker_target"),
                    ("commerce/lanes.py", "allocate"), ("commerce/lanes.py", "check_mix")):
        v = R.function_reached(rel, fn)
        assert v["reached"], v


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
