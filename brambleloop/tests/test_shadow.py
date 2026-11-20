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

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Job, JobStatus, PatternVersion, Phase, Product,
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


def drain(db: Database, phase: Phase = Phase.SHADOW, limit: int = 400) -> Worker:
    w = Worker(db, "shadow-worker", phase=phase)
    for _ in range(limit):
        if not w.run_once():
            break
    return w


# One eleven-product cycle, shared by the tests below that only *read* its outcome.
#
# Measured 2026-09-18: this file was 245 seconds for nine tests, and four of them were 60
# seconds each because each ran its own full cycle. Three of those four assert different
# things about the same run -- that a product came out certified, that publication was
# refused, that the audit trail covers every stage -- so running the cycle three times was
# not three pieces of evidence. It was one piece of evidence, paid for three times.
#
# The fourth, `test_open_incident_halts_certification`, injects defects *before* the cycle
# and so genuinely needs its own, and keeps it.
#
# A shared fixture is how a test suite rots, so this one does not rely on a comment asking
# consumers to behave. It fingerprints the warehouse after building and checks the
# fingerprint before every later use, so a test that mutates the cycle fails the next
# consumer loudly and by name instead of quietly changing what it was reading.
_CYCLE: tuple[Database, Worker] | None = None
_CYCLE_FINGERPRINT: tuple[int, ...] | None = None


def _fingerprint(db: Database) -> tuple[int, ...]:
    with db.session() as s:
        return tuple(
            s.scalar(select(func.count()).select_from(model)) or 0
            for model in (Product, PatternVersion, AuditLog, Job)
        )


def one_shadow_cycle() -> tuple[Database, Worker]:
    """The cycle, built once. Read it; do not write to it."""
    global _CYCLE, _CYCLE_FINGERPRINT
    if _CYCLE is None:
        db = boot()
        JobQueue(db).enqueue("orchestrator", "plan.cycle", {})
        worker = drain(db)
        _CYCLE = (db, worker)
        _CYCLE_FINGERPRINT = _fingerprint(db)
        return _CYCLE

    db, _ = _CYCLE
    current = _fingerprint(db)
    assert current == _CYCLE_FINGERPRINT, (
        "the shared cycle has been modified, so this test is no longer reading the outcome "
        f"the pipeline produced: {_CYCLE_FINGERPRINT} -> {current}. Give the test that "
        "writes its own cycle with boot()")
    return _CYCLE



def test_a_modified_shared_cycle_is_refused_rather_than_silently_read():
    """The guard on the shared cycle, proved rather than asserted in a comment.

    Three tests read one cycle instead of paying for three, which is only safe while none of
    them writes to it. `one_shadow_cycle` fingerprints the warehouse and re-checks it before
    every later use -- and a guard nobody has seen fire is the same mistake as a thumbnail
    check that passes a blank image, so this fires it.

    Runs against a throwaway cycle of its own and restores the module state, so it cannot
    disturb the real one.
    """
    global _CYCLE, _CYCLE_FINGERPRINT

    saved = (_CYCLE, _CYCLE_FINGERPRINT)
    try:
        db = boot()
        _CYCLE = (db, Worker(db, "guard-worker", phase=Phase.SHADOW))
        _CYCLE_FINGERPRINT = _fingerprint(db)

        # Untouched, so it is handed over.
        assert one_shadow_cycle()[0] is db

        with db.session() as session:
            session.add(Product(slug="guard-probe", title="Guard Probe", status="draft"))

        try:
            one_shadow_cycle()
        except AssertionError as e:
            assert "has been modified" in str(e), e
        else:
            raise AssertionError(
                "the guard did not fire: a test could modify the shared cycle and every "
                "test after it would quietly read something the pipeline never produced")
    finally:
        _CYCLE, _CYCLE_FINGERPRINT = saved


def test_full_product_runs_end_to_end_without_intervention():
    db, w = one_shadow_cycle()

    assert w.stats.completed >= 5, w.stats
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == "nordic-forest-mosaic-throw"))
        assert product is not None, "pipeline did not produce a product"
        assert product.status == "certified"
        pv = s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id))
        assert pv is not None and pv.certified is True
        assert pv.release_hash and len(pv.release_hash) == 64
        assert pv.certificate["granted"] is True
        assert "reverse" in pv.certificate["stages_run"]


def test_shadow_mode_refuses_to_publish():
    """Section 26: a new autonomous system is not connected to live listings on day one."""
    db, _ = one_shadow_cycle()

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
    db, _ = one_shadow_cycle()
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
        tracker.report(DefectReport("nordic-forest-mosaic-throw", "1.0.0", "panel", 4,
                                    f"cust-{i}", "row 4 count is wrong"))
    assert tracker.publication_halted("nordic-forest-mosaic-throw")

    JobQueue(db).enqueue("orchestrator", "plan.cycle", {})
    drain(db)

    with db.session() as s:
        assert s.scalar(select(Product).where(
            Product.slug == "nordic-forest-mosaic-throw")) is None
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



def test_a_product_that_stops_certifying_has_its_listing_withdrawn():
    """Refusing a certificate and leaving the storefront alone leaves a draft for a product
    the release chain has just rejected. Shadow mode is what stands between that draft and a
    customer, and shadow mode is a phase, not a guarantee."""
    from brambleloop.core.models import Listing
    from brambleloop.products.vessels import build_hexagon_coaster

    db = boot()
    cir = build_hexagon_coaster()
    with db.session() as s:
        s.add(Listing(product_slug=cir.slug, version=cir.version, title="Hexagon Coaster Set",
                      description="drafted earlier, when this product still certified",
                      price_cad=4.5, state="draft"))

    # Break the pattern the way a bad edit would: round 5 now claims a count it cannot reach.
    cir.components[0].rows[4].declared_count = 999
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()})
    drain(db)

    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == cir.slug))
        assert listing.state == "withdrawn", listing.state
        withdrawn = s.scalars(
            select(AuditLog).where(AuditLog.action == "listing.withdrawn")).all()
        assert withdrawn, "the withdrawal was not recorded"

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
