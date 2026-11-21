"""ENG-SUPPLY-LANE: new products reach certified unaided while the publishing halt is OPEN.

Production readback (17f17c20): certification_pipeline 16 products, 0 certified in 7 days;
the autonomy loop 11/12 with nothing in `original_product`; systemic publishing halt #380
open. Owner P0: "Publication holds MUST NOT stop permitted research, QA, PDFs or internal
listings."

This suite builds that state on a scratch SQLite file and runs the real handlers through the
real worker:

* 16 existing products, every one certified, each with its post-certification listing work
  retry-waiting behind the publication hold; 12 of them carry an open `stale-artefact` halt,
  and the real `incident_lifecycle.escalate_systemic` opens the company-wide
  `systemic-halt:publication` row from that evidence (staleness only, no integrity failure);
* Launch-0 exhausted (every release seeded before);
* the concept pool generated from synthetic watchlist scans: 100+ evidence-backed concepts,
  with an answered research task behind each arena that has READY concepts;
* paid vision open (owner activation + probe) with a FIXTURE vision judge.

Only the scheduler's cadence jobs are enqueued (`radar.concept_pool`, `radar.concept_intake`,
`mjs.seasonal_sentinel`, `supply.admit`); the worker drains whatever they cause.

Two defects stopped all new supply while the halt was open, both reproduced here and pinned
by a mutation test each:

1. `gate.certify` refused every release while ANY publication halt applied to the product --
   the company-wide staleness halt included -- so no new product could certify (QA gated on
   publishing).
2. Admission counted a product's held post-certification listing work as engineering
   work-in-progress, so 16 held products filled a WIP of 2 and nothing new was admitted.

Every gate stays: a product's own halt and a systemic halt with integrity evidence still stop
certification; child safety still withholds a toy for physical evidence under the hold; and
nothing is published while the hold is open.

Every listing, research source, judgement and product here is a TEST FIXTURE.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_supply_lane.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

import test_new_product_flow as NPF  # noqa: E402 - Launch-0 exhaustion, vision, fixture judge
import test_concepts100 as C100  # noqa: E402 - the synthetic watchlist scans and research

from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import (  # noqa: E402
    AuditLog, Incident, Job, JobStatus, PatternVersion, Product,
)
from brambleloop.gates.incidents import IncidentTracker  # noqa: E402
from brambleloop.ops import incident_lifecycle as IL  # noqa: E402
from brambleloop.ops import production_evidence as pe  # noqa: E402
from brambleloop.products import supply  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.radar import concept_pool as P  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402

EXISTING = 16
STALE = 12
CADENCE_JOBS = (("market_radar", "radar.concept_pool"),) + NPF.CADENCE_JOBS
CYCLES = 4
MAX_JOBS_PER_CYCLE = 400


def _existing_slugs():
    return [f"existing-{i:02d}" for i in range(EXISTING)]


def _open_staleness_halt(db, slugs, *, stale: int) -> dict:
    """Products with held listing work and `stale` of them stale; the real escalation."""
    now = datetime.now(timezone.utc)
    with db.session() as s:
        for i, slug in enumerate(slugs):
            p = s.scalar(select(Product).where(Product.slug == slug))
            if p is None:
                p = Product(slug=slug, title=slug.replace("-", " ").title(),
                            status="listing_ready")
                s.add(p)
                s.flush()
                s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={"slug": slug},
                                     certified=True, certificate={"granted": True},
                                     release_hash=f"{i + 1:064x}"))
            # post-certification listing work, retry-waiting behind the publication hold
            s.add(Job(agent="publishing", job_type="listing.draft", inputs={"slug": slug},
                      status=JobStatus.FAILED, attempts=1, max_attempts=5,
                      created_at=now - timedelta(hours=10), run_after=now + timedelta(hours=2),
                      idempotency_key=f"held-listing:{slug}",
                      last_error="held: publication hold (fixture)"))
            if i < stale:
                s.add(Incident(signature=f"stale-artefact:marketing_asset:{slug}@1.0.0",
                               severity="P1", product_slug=slug, halts_publication=True,
                               summary="fixture stale artefact"))
    with db.session() as s:
        return IL.escalate_systemic(s)


def _production_state(*, halt: bool = True):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    db = C100._db()
    NPF._exhaust_launch0(db)
    C100._scan(db)
    P.replenish(db, now=now, unit_cad=0.12, admit=False)
    for pod in sorted({r.pod for r in C100._pool(db) if r.state == P.READY}):
        C100._answered_task(db, pod)
    ev = _open_staleness_halt(db, _existing_slugs(), stale=STALE if halt else 0)
    NPF._open_vision(db)
    return db, ev


def _drain(db, *, cycles: int = CYCLES, sample=None) -> None:
    for c in range(cycles):
        q = JobQueue(db)
        for agent, job_type in CADENCE_JOBS:
            q.enqueue(agent, job_type, {"cadence": f"fixture-{c}"},
                      idempotency_key=f"fixture-cadence:{job_type}:{c}", priority=0)
        w = Worker(db, f"lane-{c}")
        for _ in range(MAX_JOBS_PER_CYCLE):
            if not w.run_once():
                break
            if sample is not None:
                sample(db)


def _new_certified(db) -> list[tuple[str, dict]]:
    existing = set(_existing_slugs())
    with db.session() as s:
        return [(p.slug, dict(pv.certificate or {})) for p, pv in s.execute(
            select(Product, PatternVersion).join(PatternVersion,
                                                 PatternVersion.product_id == Product.id)
            .where(PatternVersion.certified.is_(True))) if p.slug not in existing]


def _rows(db, action: str):
    with db.session() as s:
        return [(r.artifact, dict(r.detail or {})) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id))]


def _systemic_open(db) -> bool:
    with db.session() as s:
        return s.scalar(select(Incident.id).where(
            Incident.signature == IL.SYSTEMIC_SIGNATURE, Incident.resolved.is_(False),
            Incident.halts_publication.is_(True))) is not None


def _with_judge():
    judge = NPF._Judge('{"thumbnail_reads_small": true, "craft_impression": 4.3}')
    return judge, NPF._with_judge(judge)


# ---- the production state -------------------------------------------------------------------

def test_the_simulated_state_is_productions():
    db, ev = _production_state()
    assert ev["systemic"] and ev["opened"] and not ev["integrity_failures"], ev
    assert set(ev["widespread_families"]) == {"stale-artefact"}, ev
    assert _systemic_open(db)
    with db.session() as s:
        assert len(list(s.scalars(select(Product.id)))) == EXISTING
    backed = [r for r in C100._pool(db) if P.evidence_backed(r)]
    assert len(backed) >= P.TARGET_EVIDENCE_BACKED, len(backed)
    # every existing product is publication-halted; their listing work holds no engineering
    # slot, and admission is open
    tracker = IncidentTracker(db)
    assert all(tracker.publication_halted(s) for s in _existing_slugs())
    cap = supply.assess(db)
    assert sorted(cap["held_for_publication"]) == _existing_slugs(), cap["held_for_publication"]
    assert cap["in_flight"] == [] and cap["slots"] == cap["limit"] > 2, cap
    assert not cap["refusals"], cap["refusals"]


# ---- the fix, end to end --------------------------------------------------------------------

def test_with_the_publishing_halt_open_new_products_reach_certified_unaided():
    db, _ev = _production_state()
    peak = {"n": 0}

    def sample(db_):
        peak["n"] = max(peak["n"], len(supply.assess(db_)["in_flight"]))

    judge, restore = _with_judge()
    try:
        _drain(db, sample=sample)
    finally:
        restore()
    certified = _new_certified(db)
    assert len(certified) > 2, [s for s, _ in certified]
    admitted = {a for a, d in _rows(db, supply.ADMITTED)}
    for slug, cert in certified:
        assert cert.get("granted") is True and cert.get("release_hash"), (slug, cert)
        for stage in ("compile", "twin", "reverse"):
            assert stage in cert["stages_run"], (slug, stage, cert["stages_run"])
        assert not [f for f in cert.get("findings") or [] if f["severity"] == "ERROR"], slug
        # a graded wearable is admitted once and certified per size (`<slug>-<size>`)
        assert any(slug == a or slug.startswith(f"{a}-") for a in admitted), \
            f"{slug} did not enter by the one door (supply.admitted)"
    # certified under the hold, and said so
    under = {a.split("@", 1)[0] for a, _d in _rows(db, "gate.certify_under_publication_hold")}
    assert {s for s, _ in certified} <= under, (under, certified)
    # many in flight at once, not two
    assert peak["n"] > 2, peak
    # the halt is still OPEN, and nothing was published under it
    assert _systemic_open(db)
    tracker = IncidentTracker(db)
    assert all(tracker.publication_halted(s) for s, _ in certified)
    with db.session() as s:
        assert not list(s.scalars(select(Job).where(Job.job_type == "store.publish",
                                                    Job.status == JobStatus.DONE)))
        packages = [j.outputs or {} for j in s.scalars(
            select(Job).where(Job.job_type == "listing.package"))]
    assert all(o.get("publishes") is not True for o in packages), packages
    # the existing products' listing work is still held, untouched
    with db.session() as s:
        held = list(s.scalars(select(Job).where(Job.idempotency_key.like("held-listing:%"))))
    assert len(held) == EXISTING and all(j.status == JobStatus.FAILED for j in held)
    # the factory counter reads the same
    v = pe.factory_visibility(db, now=datetime.now(timezone.utc))["supply"]
    assert v["certified_24h"]["products"] >= len(certified) > 2, v
    assert v["pool_total"] >= P.TARGET_EVIDENCE_BACKED and v["pool_by_state"][P.ADMITTED] > 0
    assert v["engineering"]["held_for_publication"] >= EXISTING, v


# ---- mutations: each defect, restored, re-creates the stall ---------------------------------

def test_mutation_certification_gated_on_the_publication_hold_certifies_nothing():
    db, _ev = _production_state()
    real = IncidentTracker.certification_halts
    IncidentTracker.certification_halts = lambda self, slug: [
        i for i in self.open_incidents(slug) if i.halts_publication]
    judge, restore = _with_judge()
    try:
        _drain(db, cycles=3)
    finally:
        IncidentTracker.certification_halts = real
        restore()
    assert _new_certified(db) == []
    halted = [d for _a, d in _rows(db, "gate.halted")]
    assert halted, "the mutant halts every new certification"


def test_mutation_held_publishing_work_holding_engineering_slots_admits_nothing():
    db, _ev = _production_state()
    real = supply.held_for_publication
    supply.held_for_publication = lambda *a, **k: {}
    judge, restore = _with_judge()
    try:
        _drain(db, cycles=3)
        cap = supply.assess(db)
    finally:
        supply.held_for_publication = real
        restore()
    assert _new_certified(db) == []
    assert any(r.startswith(f"capacity: {EXISTING} product chain(s) in flight")
               for r in cap["refusals"]), cap["refusals"]
    assert not [a for a, d in _rows(db, supply.ADMITTED)]


# ---- every gate stays -------------------------------------------------------------------------

def test_a_products_own_halt_and_an_integrity_halt_still_stop_certification():
    db, _ev = _production_state()
    tracker = IncidentTracker(db)
    # a new product under the staleness-only systemic halt: QA proceeds, publication held
    assert tracker.certification_halts("brand-new-product") == []
    assert tracker.publication_halted("brand-new-product")
    # a product's own halt (here: its stale artefact) stops its certification as before
    own = tracker.certification_halts("existing-00")
    assert [i.signature for i in own] == ["stale-artefact:marketing_asset:existing-00@1.0.0"]
    # an integrity failure in the systemic evidence keeps the systemic row halting QA
    with db.session() as s:
        s.add(Incident(signature="authority_chain_tamper:fixture", severity="P0",
                       product_slug=None, halts_publication=True, summary="fixture tamper"))
    with db.session() as s:
        ev = IL.escalate_systemic(s)
    assert ev["integrity_failures"], ev
    sigs = [i.signature for i in tracker.certification_halts("brand-new-product")]
    assert IL.SYSTEMIC_SIGNATURE in sigs, sigs
    # unreadable evidence never waives the systemic row
    real = IL.systemic_evidence
    IL.systemic_evidence = lambda s: (_ for _ in ()).throw(RuntimeError("unreadable"))
    try:
        with db.session() as s:
            for r in s.scalars(select(Incident).where(
                    Incident.signature == "authority_chain_tamper:fixture")):
                r.resolved = True
        sigs = [i.signature for i in tracker.certification_halts("brand-new-product")]
    finally:
        IL.systemic_evidence = real
    assert IL.SYSTEMIC_SIGNATURE in sigs, sigs


def test_child_safety_still_withholds_a_toy_certified_under_the_publication_hold():
    import test_eng_animals as TA
    import test_eng_families as EF

    real = EF._db

    def held_db():
        db = real()
        ev = _open_staleness_halt(db, [f"held-{i}" for i in range(4)], stale=4)
        assert ev["systemic"] and not ev["integrity_failures"], ev
        return db
    EF._db = held_db
    try:
        out = EF._certify_research_concept(TA._frog_proposal())
    finally:
        EF._db = real
    assert _systemic_open(out["db"])
    cert = out["certified"]
    assert not cert.get("halted_by_incident"), cert           # QA ran under the hold ...
    assert cert["granted"] is False                            # ... and child safety held it
    codes = sorted({r.split(":")[0].split()[-1] for r in cert["reasons"]})
    assert codes == ["CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN", "PHYSICAL_TEST_REQUIRED"], \
        cert["reasons"]


def test_publishing_work_frees_an_engineering_slot_only_while_held_and_not_running():
    db = C100._db()
    q = JobQueue(db)
    soon = datetime.now(timezone.utc) + timedelta(hours=1)
    q.enqueue("publishing", "assets.build", {"slug": "plain-item"}, idempotency_key="a",
              run_after=soon)
    q.enqueue("publishing", "listing.draft", {"slug": "halted-item"}, idempotency_key="b",
              run_after=soon)
    q.enqueue("quality_director", "gate.certify", {"slug": "halted-engineering"},
              idempotency_key="c", run_after=soon)
    q.enqueue("publishing", "listing.draft", {"slug": "halted-engineering"},
              idempotency_key="d", run_after=soon)
    with db.session() as s:
        for slug in ("halted-item", "halted-engineering"):
            s.add(Incident(signature=f"customer:{slug}", severity="P1", product_slug=slug,
                           halts_publication=True, summary="fixture own halt"))
    cap = supply.assess(db)
    # no hold: publishing work keeps its slot (unchanged); held: it frees it; a held product
    # with engineering work live keeps its slot
    assert list(cap["held_for_publication"]) == ["halted-item"], cap["held_for_publication"]
    assert sorted(cap["in_flight"]) == ["halted-engineering", "plain-item"], cap["in_flight"]
    # running publishing work is using the worker: it keeps its slot even while held
    with db.session() as s:
        j = s.scalar(select(Job).where(Job.idempotency_key == "b"))
        j.status = JobStatus.RUNNING
    cap = supply.assess(db)
    assert cap["held_for_publication"] == {} and "halted-item" in cap["in_flight"], cap


def test_the_wip_ceiling_is_capacity_based():
    from brambleloop.swarm import capacity

    db = C100._db()
    real = capacity.worker_target
    capacity.worker_target = lambda db, now=None: {"target": 1}
    try:
        floor = supply.wip_ceiling(db, env={})
        assert floor["limit"] == supply.WIP_PER_WORKER > 2, floor
        assert not floor["per_product"]["measured"], floor
        # measured: draft + compile + certify at 60 s each -> 3600 // 180 = 20 per worker,
        # bounded by MAX_WIP
        now = datetime.now(timezone.utc)
        with db.session() as s:
            for jt in ("cir.draft", "cir.compile", "gate.certify"):
                s.add(Job(agent="x", job_type=jt, inputs={}, status=JobStatus.DONE,
                          started_at=now - timedelta(minutes=5),
                          finished_at=now - timedelta(minutes=4)))
        got = supply.wip_ceiling(db, env={})
        assert got["per_product"]["measured"] and got["per_worker"] == 20, got
        assert got["limit"] == supply.MAX_WIP, got
        assert supply.wip_ceiling(db, env={"BRAMBLELOOP_SUPPLY_MAX_WIP": "3"})["limit"] == 3
    finally:
        capacity.worker_target = real


def test_factory_visibility_supply_counts_use_fixed_vocabulary_only():
    db, _ev = _production_state()
    v = pe.factory_visibility(db, now=datetime.now(timezone.utc))["supply"]
    assert set(v) == {"pool_generated", "pool_by_state", "pool_total", "in_flight_by_stage", "products_in_flight",
                      "engineering", "offers_waiting", "certified_24h",
                      # ENG-SUPPLY-FEED (tests/test_supply_feed.py pins their vocabulary)
                      "allowance", "ready_by_pod", "ready_by_research", "last_admit"}, sorted(v)
    assert set(v["pool_by_state"]) <= set(P.STATES) | {"unrecognised"}, v["pool_by_state"]
    from brambleloop.runtime.release_recovery import CHAIN_STAGE_JOBS

    assert set(v["in_flight_by_stage"]) == set(CHAIN_STAGE_JOBS)
    assert v["in_flight_by_stage"]["listing.draft"] == EXISTING, v["in_flight_by_stage"]
    assert v["engineering"]["held_for_publication"] == EXISTING, v["engineering"]
    assert v["certified_24h"] == {"releases": 0, "products": 0}, v
    text = json.dumps(v)
    assert "existing-" not in text and "pool-" not in text, text
    # a pool that was never generated reads UNKNOWN, never 0
    empty = C100._db()
    e = pe.factory_visibility(empty, now=datetime.now(timezone.utc))["supply"]
    assert e["pool_by_state"] is None and e["pool_total"] is None, e
    assert e["pool_generated"] is False and v["pool_generated"] is True


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    failed = 0
    assert TESTS
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            import traceback

            failed += 1
            print(f"FAIL {t.__name__}: {type(exc).__name__}: {str(exc)[:1500]}")
            traceback.print_exc(limit=4)
    print(f"{len(TESTS) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
