"""The improvement handlers, run the way the worker runs them, on a temporary database.

Requirements 85, 90, 93, 97, 100, 101, 178, 192, 193, 194. The modules are tested next door;
this proves the scheduled entry points actually call them -- a handler that returns without
raising is not evidence it did anything -- and that a full nightly and weekly run on a seeded
company changes no gate threshold and no Product Truth.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import pkgutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402


def _db():
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/improve.sqlite")
    db.create_all()
    from brambleloop.agents.registry import Registry

    Registry(db).seed_defaults()
    return db


_N = [0]


def _run(db, job_type: str, agent: str = "orchestrator") -> dict:
    from brambleloop.agents.registry import Registry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401  -- registers handlers
    from brambleloop.runtime.worker import JobContext, handlers

    _N[0] += 1
    queue = JobQueue(db)
    job = queue.enqueue(agent, job_type, {}, idempotency_key=f"t:{job_type}:{_N[0]}")
    ctx = JobContext(job=job, db=db, queue=queue, registry=Registry(db), phase=None)
    return handlers.get(job_type)(ctx)


def _seed(db):
    from datetime import datetime, timedelta, timezone

    from brambleloop.core.models import (AuditLog, BenchmarkObservation, Incident, Job,
                                         JobStatus, Keyword, ListingAsset, PatternVersion,
                                         Product)

    now = datetime.now(timezone.utc)
    with db.session() as s:
        p = Product(slug="cable-throw", title="Cable Throw")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={}, certified=True))
        s.add(PatternVersion(product_id=p.id, version="1.0.1", cir_json={}, certified=False))
        s.add(ListingAsset(product_slug="cable-throw", version="1.0.0", position=1,
                           asset_class="photo", role="hero", approved=False))
        s.add(Keyword(phrase="crochet cable blanket pattern"))
        s.add(BenchmarkObservation(at=now - timedelta(hours=5), benchmark_key="mjs",
                                   listing_ref="L1", kind="gallery"))
        s.add(Incident(severity="P1", signature="row-94-count", product_slug="cable-throw",
                       summary="round 94 count does not match", detail={}))
        s.add(AuditLog(actor="quality", action="gate.blocked", artifact="cable-throw@1.0.1",
                       detail={"reasons": ["E_COUNT: round 94 declares 23"]}))
        s.add(Job(agent="a", job_type="assets.render", status=JobStatus.DEAD, inputs={},
                  last_error="TimeoutError: render took too long",
                  created_at=now - timedelta(days=2)))
        s.add(AuditLog(actor="creative_director", action="creative.tournament",
                       artifact="christmas/home",
                       detail={"field": {"generated": 40}, "survivors": [{}],
                               "causes": {"sameness": 30, "genericness": 6}}))


def _count(db, model, **where):
    from sqlalchemy import func, select

    stmt = select(func.count()).select_from(model)
    for key, value in where.items():
        stmt = stmt.where(getattr(model, key) == value)
    with db.session() as s:
        return s.scalar(stmt) or 0


# ---- each handler --------------------------------------------------------------------------


def test_improve_measure_records_capability_points_through_the_handler():
    from brambleloop.core.models import AuditLog, CapabilityPoint

    db = _db()
    empty = _run(db, "improve.measure")
    # The only row an empty company has is this job itself, which the runtime cell counts.
    assert empty["cells"] == ["runtime"] and len(empty["skipped"]) == 12  # thirteen cells (learn, F-799) less runtime
    _seed(db)
    out = _run(db, "improve.measure")
    assert out["measured"] >= 6 and "pattern_engineering" in out["cells"]
    assert _count(db, CapabilityPoint) == out["measured"] + 1
    assert _count(db, AuditLog, action="improve.measure") == 2
    again = _run(db, "improve.measure")      # same rows, same reading -- bar the new job
    assert set(again["cells"]) <= {"runtime"} and "pattern_engineering" in again["repeated"]


def test_improve_mine_publishes_routed_lessons_once():
    from brambleloop.core.models import Lesson

    db = _db()
    _seed(db)
    out = _run(db, "improve.mine")
    assert out["published"] == 4 and "quality" in out["routed_to"]
    lessons = _count(db, Lesson)
    again = _run(db, "improve.mine")
    assert again["published"] == 0 and _count(db, Lesson) == lessons


def test_the_nightly_sweep_ingests_mines_and_queues_for_real():
    from brambleloop.core.models import Improvement

    db = _db()
    empty = _run(db, "improve.nightly")
    # An empty company: nothing failed, so mining read nothing and says it did not run, and
    # the verdict is incomplete rather than a clean night.
    assert empty["delta"]["stages"]["mine_failures"]["outcome"] == "did_not_run"
    assert empty["verdict"] == "incomplete"
    # The only measurable row is the sweep's own job, which the runtime cell counts.
    assert empty["delta"]["stages"]["ingest_evidence"]["detail"]["cells_measured"] == ["runtime"]
    _seed(db)
    out = _run(db, "improve.nightly")
    stages = out["delta"]["stages"]
    assert stages["ingest_evidence"]["outcome"] == "ran_and_found"
    assert stages["mine_failures"]["outcome"] == "ran_and_found"
    assert stages["update_lessons"]["outcome"] == "ran_and_found"
    assert stages["run_challengers"]["outcome"] in ("ran_and_found", "ran_and_found_nothing")
    assert stages["queue_safe_improvements"]["read"] == 13  # thirteen cells incl. learn (F-799)
    # The never-measured proposals for cells measured tonight close as done, not failed.
    assert stages["queue_safe_improvements"]["detail"]["resolved_by_measurement"] >= 6
    assert _count(db, Improvement, state="promoted") == 0     # the sweep never promotes


def test_the_weekly_cycle_reviews_retirement_and_executes_only_the_safe():
    from brambleloop.improve import cells

    db = _db()
    _seed(db)
    _run(db, "improve.measure")
    cells.record_capability(db, "seo_search", 1.0, sample=3)
    iid = cells.propose(db, cell="seo_search",
                        hypothesis=("ranking search phrases by cluster before length should "
                                    "raise the number of distinct clusters answered"),
                        expected_effect="more clusters", rollback_ref="weights:seo:v1",
                        touches=("weights",), proposed_by="listing")
    cells.test_result(db, iid, 2.0)
    cells.approve(db, iid, approved_by="evaluator", why="beat the baseline on the holdout")
    gated = cells.propose(db, cell="quality",
                          hypothesis=("reordering release checks so the cheapest refusal runs "
                                      "first should cut time to a verdict per product"),
                          expected_effect="faster verdicts", rollback_ref="release:v1",
                          touches=("release",), proposed_by="quality_director")
    cells.record_capability(db, "quality", 1.0, sample=1)
    out = _run(db, "improve.weekly")
    assert [e["improvement"] for e in out["executed"]] == [iid]
    assert all(q["improvement"] != gated for q in out["executed"])
    review = out["retirement_review"]
    assert {w["cell"] for w in review["waiting_for_data"]} >= {"pricing", "finance"}
    assert "pattern_engineering" in review["keep"]
    assert out["architecture"]["subtracted"] == len(review["retire"]) + len(review["merge"])
    # #85: the catalogue autopsy is kept as a lesson, once.
    assert out["catalogue_autopsy_lesson"]
    assert _run(db, "improve.weekly")["catalogue_autopsy_lesson"] == out[
        "catalogue_autopsy_lesson"]


def test_the_retrospective_handler_carries_the_hundreds_clauses():
    from brambleloop.core.models import AuditLog

    db = _db()
    _seed(db)
    _run(db, "improve.nightly")
    out = _run(db, "improve.retrospective")
    assert "hit_rate" in out and out["unmeasured"] < 12
    from sqlalchemy import desc, select
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "improvement.retrospective")
                       .order_by(desc(AuditLog.id)))
    for key in ("stop_doing", "top_next_upgrades", "experiments_completed",
                "experiments_killed", "realised_benefit", "learned"):
        assert key in row.detail, key
    assert row.detail["learned"], "the mined lessons are what was learned this week"


def test_the_monitor_handler_reverts_a_regression_with_a_rollback_proposal():
    from brambleloop.core.models import Incident
    from brambleloop.improve import cells

    db = _db()
    cells.record_capability(db, "seo_search", 3.0, sample=3)
    iid = cells.propose(db, cell="seo_search",
                        hypothesis=("ranking search phrases by cluster before length should "
                                    "raise the number of distinct clusters answered"),
                        expected_effect="more clusters", rollback_ref="weights:seo:v1",
                        touches=("weights",), proposed_by="listing")
    cells.test_result(db, iid, 4.0)
    cells.approve(db, iid, approved_by="evaluator", why="beat the baseline cleanly")
    cells.promote(db, iid, promoted_by="evaluator")
    cells.record_capability(db, "seo_search", 2.0, sample=3, detail={"from": "improve.measure"})
    out = _run(db, "improve.monitor")
    assert out["reverted"] == [iid]
    assert out["rollback_proposals"] == [f"improve-rollback:{iid}"]
    assert _count(db, Incident, signature=f"improve-rollback:{iid}") == 1


def test_the_brief_reads_the_jury_memory_back_and_records_provenance():
    from brambleloop.core.models import AuditLog, BenchmarkListing, BenchmarkObservation
    from brambleloop.creative import reference

    db = _db()
    _seed(db)
    _run(db, "improve.mine")
    with db.session() as s:
        for ref in ("1", "2"):
            s.add(BenchmarkListing(benchmark_key="mjs_off_the_hook_designs",
                                   listing_ref=ref, title="t", pod="garments"))
            s.add(BenchmarkObservation(benchmark_key="mjs_off_the_hook_designs",
                                       listing_ref=ref, kind="gallery_image_observation",
                                       detail={"observation": {"setting": "studio"}}))
    out = reference.brief(db, "garments", benchmark_key="mjs_off_the_hook_designs")
    assert out["usable"] is True
    assert any(l["subject"] == "creative_rejection" for l in out["lessons"])
    assert out["design_provenance"]["recorded"] is True
    reference.brief(db, "garments", benchmark_key="mjs_off_the_hook_designs")
    assert _count(db, AuditLog, action="design.provenance") == 1   # one design, not two


# ---- the whole loop leaves the gates alone -------------------------------------------------


def _threshold_snapshot() -> str:
    """Every upper-case constant in the gate modules and the improvement boundary."""
    import brambleloop.gates as gates

    names = [f"brambleloop.gates.{m.name}" for m in pkgutil.iter_modules(gates.__path__)]
    names += ["brambleloop.improve.governance", "brambleloop.improve.tiers",
              "brambleloop.improve.cells", "brambleloop.creative.jury",
              "brambleloop.creative.tournament", "brambleloop.creative.standard"]
    snap = {}
    for name in sorted(names):
        module = importlib.import_module(name)
        for key, value in sorted(vars(module).items()):
            if key.isupper() and isinstance(value, (int, float, str, tuple, dict, frozenset,
                                                    list)):
                snap[f"{name}.{key}"] = repr(value)
    return hashlib.sha256(json.dumps(snap, sort_keys=True).encode()).hexdigest()


def _product_truth_digest() -> str:
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.products.texture import build_cable_throw

    cir = build_cable_throw()
    result = compile_cir(cir)
    return hashlib.sha256(json.dumps(
        {"cir": cir.to_dict(), "ok": result.ok,
         "rows": [getattr(r, "count", None) for r in result.rows],
         "findings": sorted(f.code for f in result.findings)},
        sort_keys=True, default=str).encode()).hexdigest()


def test_a_full_nightly_and_weekly_run_changes_no_threshold_and_no_product_truth():
    from brambleloop.improve import cells

    thresholds, truth = _threshold_snapshot(), _product_truth_digest()
    db = _db()
    _seed(db)
    # Something for the loop to act on: an approved scoring change and a queued gate one.
    cells.record_capability(db, "seo_search", 1.0, sample=3)
    iid = cells.propose(db, cell="seo_search",
                        hypothesis=("ranking search phrases by cluster before length should "
                                    "raise the number of distinct clusters answered"),
                        expected_effect="more clusters", rollback_ref="weights:seo:v1",
                        touches=("weights",), proposed_by="listing")
    cells.test_result(db, iid, 2.0)
    cells.approve(db, iid, approved_by="evaluator", why="beat the baseline on the holdout")
    for job_type in ("improve.measure", "improve.mine", "improve.nightly", "improve.weekly",
                     "improve.retrospective", "improve.monitor", "improve.nightly",
                     "improve.weekly"):
        _run(db, job_type)
    assert _threshold_snapshot() == thresholds
    assert _product_truth_digest() == truth


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
