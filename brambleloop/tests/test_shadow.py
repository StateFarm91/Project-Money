"""Gate F -- shadow-mode graduation.

'At least one full simulated product completes Market Radar -> Opportunity -> CIR -> QA ->
PDF/assets -> pricing -> listing draft -> launch plan -> simulated support without routine
human intervention.'

Also proves the refusals hold: shadow mode does not publish, a broken pattern never certifies,
and an open P0/P1 incident halts the chain.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, JobStatus, PatternVersion, Phase, Product,
)
from brambleloop.gates.incidents import DefectReport, IncidentTracker  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402  (registers handlers)
from brambleloop.runtime.worker import Scheduler, Worker  # noqa: E402


def boot() -> Database:
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def drain(db: Database, phase: Phase = Phase.SHADOW, limit: int = 100) -> Worker:
    w = Worker(db, "shadow-worker", phase=phase)
    for _ in range(limit):
        if not w.run_once():
            break
    return w


def test_full_product_runs_end_to_end_without_intervention():
    db = boot()
    JobQueue(db).enqueue("orchestrator", "plan.cycle", {})
    w = drain(db)

    assert w.stats.completed >= 5, w.stats
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == "mosaic_blanket-concept"))
        assert product is not None, "pipeline did not produce a product"
        assert product.status == "certified"
        pv = s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id))
        assert pv is not None and pv.certified is True
        assert pv.release_hash and len(pv.release_hash) == 64
        assert pv.certificate["granted"] is True
        assert "reverse" in pv.certificate["stages_run"]


def test_shadow_mode_refuses_to_publish():
    """Section 26: a new autonomous system is not connected to live listings on day one."""
    db = boot()
    JobQueue(db).enqueue("orchestrator", "plan.cycle", {})
    drain(db)

    q = JobQueue(db)
    publishes = [j for j in q.dead_letters() if j.job_type == "store.publish"]
    assert publishes, "expected a publish attempt to be refused and dead-lettered"
    assert "SHADOW" in publishes[0].last_error or "shadow" in publishes[0].last_error

    with db.session() as s:
        refusals = list(s.scalars(
            select(AuditLog).where(AuditLog.action == "store.publish_refused")
        ))
    assert refusals, "the refusal must be auditable"


def test_audit_trail_covers_the_whole_chain():
    db = boot()
    JobQueue(db).enqueue("orchestrator", "plan.cycle", {})
    drain(db)
    with db.session() as s:
        actions = {a.action for a in s.scalars(select(AuditLog))}
    for expected in ("radar.scanned", "radar.scored", "cir.drafted", "cir.compiled",
                     "gate.certified", "listing.drafted"):
        assert expected in actions, f"missing audit step {expected}: {sorted(actions)}"


def test_open_incident_halts_certification():
    """Gate E crossed with the pipeline: a P1 defect stops the release chain."""
    db = boot()
    tracker = IncidentTracker(db)
    for i in range(3):
        tracker.report(DefectReport("mosaic_blanket-concept", "1.0.0", "panel", 4,
                                    f"cust-{i}", "row 4 count is wrong"))
    assert tracker.publication_halted("mosaic_blanket-concept")

    JobQueue(db).enqueue("orchestrator", "plan.cycle", {})
    drain(db)

    with db.session() as s:
        assert s.scalar(select(Product).where(
            Product.slug == "mosaic_blanket-concept")) is None
        halted = list(s.scalars(select(AuditLog).where(AuditLog.action == "gate.halted")))
    assert halted, "certification should have been halted by the open incident"


def test_a_concept_whose_maths_fails_dies_at_compile():
    db = boot()
    # 40 stitches cannot be covered by a repeat consuming 6 -- the compiler must refuse.
    JobQueue(db).enqueue("crochet_engineer", "cir.draft", {
        "slug": "bad-concept", "title": "Bad Concept", "category": "mosaic_blanket",
        "stitch_repeat": [["sc", 5], ["dc", 1]], "width_stitches": 40, "rows": 4,
        "colors": {"forest": "#244A3A"},
    })
    drain(db)

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == "bad-concept"))
        compiled = s.scalar(select(AuditLog).where(AuditLog.action == "cir.compiled"))
    assert product is None, "a pattern that fails compilation must never become a product"
    assert compiled is not None and compiled.detail["ok"] is False


def test_scheduler_is_idempotent_within_a_window():
    db = boot()
    sched = Scheduler(db)
    first = sched.tick()
    second = sched.tick()
    assert first, "first tick should enqueue the due cadences"
    assert second == [], "the same window must not enqueue twice"


def test_worker_denies_a_job_an_agent_may_not_run():
    db = boot()
    JobQueue(db).enqueue("listing", "ads.campaign", {"budget": 100})
    w = drain(db)
    assert w.stats.denied == 1
    with db.session() as s:
        denials = list(s.scalars(select(AuditLog).where(AuditLog.action == "job.denied")))
    assert denials


def test_worker_survives_a_handler_that_explodes():
    db = boot()
    from brambleloop.runtime.worker import handlers

    @handlers.register("ops.explode")
    def _boom(ctx):
        raise RuntimeError("handler exploded")

    reg = Registry(db)
    with db.session() as s:
        from brambleloop.core.models import Agent
        a = s.scalar(select(Agent).where(Agent.name == "orchestrator"))
        a.allowed_job_types = list(a.allowed_job_types) + ["ops.explode"]

    JobQueue(db).enqueue("orchestrator", "ops.explode", {})
    w = drain(db)
    assert w.stats.failed == 1
    assert w.stats.completed == 0


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
