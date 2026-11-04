"""A4(a) P0-RESEARCH-TO-CONCEPT: a coverage gap with no POOL concept becomes a NEW concept.

Runs the real runtime on a real SQLite FILE: the cadence scheduler (`Scheduler.tick`), the
durable queue and a `Worker` claiming the registered handlers through `run_once` --
`radar.scan` -> `radar.score` (coverage handoff) -> `research.investigate` (ideation step) ->
`radar.concept_intake` -> `radar.score` -> `cir.draft`. No handler under test is mocked.

The only stand-in is the vision judge's recorded verdict (`creative.intake.judgement_for`),
which is model I/O: `image_vision` is CLOSED here, and without a judgement the
pre-engineering gate holds every new concept WAITING (also tested below). Every competitor
listing, shop and price here is a TEST FIXTURE -- not an observation anybody made.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
from concurrent.futures import ThreadPoolExecutor
import sys
import hashlib
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select, text  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, BenchmarkListing, CoverageGap, Job, JobStatus, Phase,
)
from brambleloop.intel import coverage, research  # noqa: E402
from brambleloop.intel.benchmarks import MJS_KEY  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.radar import ideation, intake  # noqa: E402
from brambleloop.radar.opportunity import POOL  # noqa: E402
from brambleloop.runtime import intel_ops  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import JobContext, Scheduler, Worker  # noqa: E402

TODAY = date.today()
POOL_SLUGS = {s.slug for s in POOL}
# The research-to-concept chain. Everything else the cadences enqueue stays PENDING here.
CHAIN = ["radar.scan", "radar.score", "research.investigate", "radar.concept_intake",
         "cir.draft"]


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/a4a.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _gap(db, pod: str, key: str = "fixture-watch") -> int:
    return coverage.upsert(db, benchmark_key=key, arena=f"watchlist:{pod}", pod=pod)


def _listings(db, pod: str, rows, *, days_ago: int = 4) -> None:
    """Fixture competitor listings: (shop, title, price)."""
    seen = datetime.now(timezone.utc) - timedelta(days=days_ago)
    with db.session() as s:
        n = s.scalar(select(BenchmarkListing.id).order_by(BenchmarkListing.id.desc())
                     .limit(1)) or 0
        for i, (shop, title, price) in enumerate(rows):
            s.add(BenchmarkListing(benchmark_key=shop, listing_ref=str(10000000 + n + i),
                                   title=title, pod=pod, price_cad=price,
                                   audit_state="audited", first_seen=seen, last_seen=seen,
                                   detail={"source_shop_id": (str(int(hashlib.sha256(
                                       shop.encode()).hexdigest()[:12], 16) + 1) if shop else "")}))


# One shop is the owner's benchmark (MJS): the pre-engineering anti-clone check measures a
# concept against that benchmark's observed listings in the pod, and waits without them.
KITCHEN = [(MJS_KEY, "Farmhouse Dishcloth Crochet Pattern", 5.5),
           (MJS_KEY, "Rustic Cotton Washcloth Pattern", 6.0),
           ("fx-shop-b", "Cotton Washcloth Crochet Pattern", 6.5),
           ("fx-shop-b", "Granny Potholder Pattern", 7.0),
           ("fx-shop-c", "Scrubby Dishcloth Set Pattern", 7.5)]


def test_census_does_not_interpret_text_or_boolean_as_a_recorded_price():
    for value in (True, False, "1", "invalid", None, float("inf"), float("nan"), -1, 0):
        assert ideation._observed_price(value) is None


def test_census_skips_malformed_price_without_fabricating_a_price():
    db = _db()
    _listings(db, "kitchen_bath", KITCHEN)
    # SQLite can hold a legacy malformed value despite the model's float type.
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE benchmark_listings SET price_cad='invalid' "
                                "WHERE id=(SELECT min(id) FROM benchmark_listings)"))
    observed = ideation.observe(db, "kitchen_bath", today=TODAY)
    assert observed["ok"] is True
    assert observed["listings"] == 5
    # The invalid listing contributes neither zero nor an invented price.
    assert observed["price_median_cad"] == 6.5


def test_research_worker_holds_when_all_observed_prices_are_malformed():
    db = _db()
    gid = _gap(db, "kitchen_bath")
    _listings(db, "kitchen_bath", KITCHEN)
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE benchmark_listings SET price_cad='invalid'"))
    _drive(db, datetime.now(timezone.utc))
    assert _ideation(db, gid)["outcome"] == ideation.OUT_INSUFFICIENT
    assert not _concepts(db)
    assert any("no observed listing carries a price" in str(row.detail)
               for row in _audits(db, ideation.INSUFFICIENT))


def _judge_intake_concepts():
    """Stand in for the vision judge's recorded verdict on research concepts only (model
    I/O). POOL concepts get no judgement, exactly as in SHADOW."""
    from brambleloop.creative import intake as creative_intake

    real = creative_intake.judgement_for

    def fixture(db, key):
        if key not in POOL_SLUGS and str(key).endswith(("-dishcloth", "-hot-pad")):
            return {"thumbnail_reads_small": True, "craft_impression": 4.2,
                    "sources": ["fixture vision verdict"]}
        return real(db, key)

    creative_intake.judgement_for = fixture
    return lambda: setattr(creative_intake, "judgement_for", real)


def _drive(db, now: datetime, *, types=CHAIN, limit: int = 400) -> int:
    """One cadence tick, then the worker runs until the chain is idle."""
    Scheduler(db).tick(now)
    w = Worker(db, "a4a-test", job_types=list(types))
    ran = 0
    while ran < limit and w.run_once():
        ran += 1
    assert ran < limit, "the chain did not go idle"
    return ran


def _jobs(db, job_type: str) -> list[Job]:
    with db.session() as s:
        return list(s.scalars(select(Job).where(Job.job_type == job_type).order_by(Job.id)))


def _tasks(db) -> list[research.ResearchTask]:
    research._ensure(db)
    with db.session() as s:
        rows = list(s.scalars(select(research.ResearchTask)
                              .where(research.ResearchTask.trigger.like("ideation_gap:%"))
                              .order_by(research.ResearchTask.id)))
        s.expunge_all()
        return rows


def _concepts(db) -> list[intake.RadarConcept]:
    intake._ensure(db)
    with db.session() as s:
        rows = list(s.scalars(select(intake.RadarConcept).order_by(intake.RadarConcept.id)))
        s.expunge_all()
        return rows


def _audits(db, action: str) -> list[AuditLog]:
    with db.session() as s:
        return list(s.scalars(select(AuditLog).where(AuditLog.action == action)
                              .order_by(AuditLog.id)))


def _ideation(db, gap_id: int) -> dict:
    with db.session() as s:
        return dict((s.get(CoverageGap, gap_id).evidence or {}).get("ideation") or {})


def _counts(db) -> dict:
    return {"tasks": len(_tasks(db)), "concepts": len(_concepts(db)),
            "proposals": sum(len((t.detail or {}).get("concept_proposals") or [])
                             for t in _tasks(db)),
            "drafts": len([j for j in _jobs(db, "cir.draft")
                           if j.idempotency_key.startswith("draft:")
                           and j.idempotency_key[6:] not in POOL_SLUGS]),
            "investigations": len(_jobs(db, "research.investigate")),
            "intakes": len([j for j in _jobs(db, "radar.concept_intake")
                            if j.idempotency_key.startswith("intake:ideation:")])}


# ---- the chain -------------------------------------------------------------------------------


def test_a_gap_with_no_pool_concept_becomes_a_new_concept_and_a_cir_draft():
    db = _db()
    gid = _gap(db, "kitchen_bath")
    assert not [s for s in POOL if __import__("brambleloop.intel.pods", fromlist=["x"])
                .BY_KEY["kitchen_bath"].matches(s.slug.replace("-", " "))], \
        "precondition: no POOL concept answers kitchen_bath"
    _listings(db, "kitchen_bath", KITCHEN)
    restore = _judge_intake_concepts()
    try:
        _drive(db, datetime.now(timezone.utc))
    finally:
        restore()

    # 1. the coverage handoff opened ONE research task carrying the ideation brief.
    tasks = _tasks(db)
    assert len(tasks) == 1, [t.trigger for t in tasks]
    task = tasks[0]
    assert task.trigger == f"ideation_gap:{gid}"
    assert task.detail["ideation_brief"] == {"gap": gid, "pod": "kitchen_bath",
                                             "arena": "watchlist:kitchen_bath"}
    # 2. answered from the recorded observations: a dated, fact-grade source and finding,
    #    with a recorded confidence.
    assert task.state == research.ANSWERED and task.confidence == "medium"
    assert task.sources[0]["retrieval"] == "internal" and task.sources[0]["read_on"]
    assert task.findings[0]["claim_class"] == "fact"
    assert "5 listings" in task.findings[0]["statement"]
    assert "3 resolved marketplace shops" in task.findings[0]["statement"]
    assert task.detail["ideation_census"]["census_sha256"] in task.sources[0]["citation"]
    prop = task.detail["concept_proposals"][0]
    assert prop["concept"]["construction"] == "flat_rows"
    slug = prop["slug"]
    assert slug not in POOL_SLUGS, slug
    # The title is the pod noun plus a house descriptor, never a competitor's words.
    assert prop["title"].endswith(" Dishcloth")
    assert not ideation.originality_reasons(prop["title"], prop["title"][:-10],
                                            ideation.observed_titles(db))

    # 3. intake approved it as a NEW concept outside POOL ...
    rows = _concepts(db)
    assert [(r.slug, r.state) for r in rows] == [(slug, intake.APPROVED)], \
        [(r.slug, r.state, r.reasons) for r in rows]
    assert rows[0].source_ref == f"research_task:{task.id}"
    assert {i["ref"] for i in rows[0].evidence} == set(prop["evidence"])
    # ... radar.score promoted it, and cir.draft was enqueued AND run automatically.
    drafts = [j for j in _jobs(db, "cir.draft") if j.idempotency_key == f"draft:{slug}"]
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.inputs["provenance"] == f"radar.intake:research_task:{task.id}"
    assert draft.status == JobStatus.DONE, (draft.status, draft.last_error)
    out = dict(draft.outputs or {})
    if out.get("drafted"):
        compiles = [j for j in _jobs(db, "cir.compile") if j.inputs["cir"]["slug"] == slug]
        assert compiles, "a drafted CIR goes to deterministic validation"
        print(f"     NEW concept {slug!r} drafted: {out.get('artifact')} "
              f"({out.get('construction')}); cir.compile queued")
    else:
        # A deterministic refusal is acceptable -- and must be recorded with a named reason.
        refused = [a for a in _audits(db, "cir.draft_refused") if a.artifact == slug]
        assert out.get("reasons") and (refused or out.get("gate")), out
        print(f"     NEW concept {slug!r} refused at cir.draft: {out.get('reasons')}")

    # 4. the gap's ideation record carries the durable outcome.
    rec = _ideation(db, gid)
    assert rec["task"] == task.id and rec["outcome"] == "proposed" and rec["slug"] == slug


def test_the_new_concept_continues_through_compile_to_certification():
    """Handoff item (Main, #28): past cir.draft, the research concept goes through
    deterministic validation and certification on the same worker -- compiled, then a
    gate.certify job that ends DONE with a recorded verdict (granted, or refused with named
    codes). Nothing is assumed granted; a refusal must be named."""
    db = _db()
    _gap(db, "kitchen_bath")
    _listings(db, "kitchen_bath", KITCHEN)
    restore = _judge_intake_concepts()
    try:
        _drive(db, datetime.now(timezone.utc))
        slug = _tasks(db)[0].detail["concept_proposals"][0]["slug"]
        draft = [j for j in _jobs(db, "cir.draft") if j.idempotency_key == f"draft:{slug}"][0]
        assert (draft.outputs or {}).get("drafted") is True, draft.outputs
        w = Worker(db, "a4a-certify", job_types=["cir.compile", "gate.certify"])
        while w.run_once():
            pass
    finally:
        restore()
    compiles = [j for j in _jobs(db, "cir.compile") if j.inputs["cir"]["slug"] == slug]
    assert compiles and compiles[-1].status == JobStatus.DONE, compiles
    assert (compiles[-1].outputs or {}).get("compiled") is True, compiles[-1].outputs
    # The actual compiled CIR must make the square object its title promises.
    from brambleloop.cir.model import CIR
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    cir = CIR.from_dict(compiles[-1].inputs["cir"])
    twin = build_twin(cir, compile_cir(cir))
    assert 20 <= twin.width_cm <= 25, twin.width_cm
    assert 20 <= twin.height_cm <= 25, twin.height_cm
    assert abs(twin.width_cm - twin.height_cm) <= 2, (twin.width_cm, twin.height_cm)
    # The old 48x14 placemat geometry must fail at the actual release gate.
    from brambleloop.runtime.pipeline import Concept, concept_to_cir
    from brambleloop.gates.certificate import certify
    old = concept_to_cir(Concept(slug="dishcloth-old", title="Old Dishcloth",
        category="placemat", stitch_repeat=[("sc", 3), ("dc", 1)],
        width_stitches=48, rows=14, colors={"a": "#ffffff"}))
    refusal = certify(old)
    assert not refusal.granted
    assert any(f.code == "DISHCLOTH_DIMENSIONS" for f in refusal.findings), refusal.findings
    from brambleloop.publish.eligibility import name_truth
    for title in ("Old Dish\u200bcloth", "Old Dish-cloth", "Old Ｄｉｓｈｃｌｏｔｈ"):
        old.title = title
        verdict = certify(old)
        assert not verdict.granted, title
        assert any(f.code == "DISHCLOTH_DIMENSIONS" for f in verdict.findings), title
        assert any("object:" in problem for problem in name_truth(old)), title
    old.title = "Old Placemat"
    assert any("object:" in p for p in name_truth(old, {"title": "Dishcloth"}))
    proposal = _tasks(db)[0].detail["concept_proposals"][0]
    assert proposal["concept"]["palette_story"] == "forest green and cream"
    assert proposal["concept"]["motif"] == "alternating stripes"
    assert cir.colors == {"forest": "#244A3A", "cream": "#FAF6EB"}, cir.colors
    certs = [j for j in _jobs(db, "gate.certify")
             if (j.inputs.get("cir") or {}).get("slug") == slug]
    assert certs, "a compiled research concept was not sent to certification"
    cert = certs[-1]
    assert cert.status == JobStatus.DONE, (cert.status, cert.last_error)
    out = dict(cert.outputs or {})
    granted = out.get("granted", out.get("certified"))
    assert granted is not None, out
    if not granted:
        named = out.get("errors") or out.get("codes") or out.get("reasons")
        assert named, f"certification refused {slug} without naming why: {out}"
    print(f"     certify {slug}: granted={granted} {str(out)[:200]}")


def test_future_dated_market_listings_do_not_make_evidence():
    db = _db()
    _listings(db, "kitchen_bath", KITCHEN, days_ago=-400)
    observed = ideation.observe(db, "kitchen_bath", today=TODAY)
    assert observed["listings"] == 0, observed
    assert observed["ok"] is False, observed


def test_hot_pad_claim_is_not_generated_without_heat_evidence():
    db = _db()
    _listings(db, "kitchen_bath", [("a", "Hot Pad", 5),
                                    ("b", "Potholder", 6),
                                    ("b", "Hot Pad", 7)])
    observed = ideation.observe(db, "kitchen_bath", today=TODAY)
    assert observed["ok"] is False, observed
    assert observed["object"] is None, observed


def test_recovery_refuses_to_attach_a_proposal_to_changed_evidence():
    db = _db()
    gid = _gap(db, "kitchen_bath")
    _listings(db, "kitchen_bath", KITCHEN)
    restore = _judge_intake_concepts()
    try:
        _drive(db, datetime.now(timezone.utc))
        task_id = _tasks(db)[0].id
        # Simulate interruption after the answer but before proposal attachment.
        with db.session() as session:
            task = session.get(research.ResearchTask, task_id)
            detail = dict(task.detail)
            detail["concept_proposals"] = []
            task.detail = detail
            # Keep the evidence floor satisfied, but change the source census.
            listing = session.scalar(select(BenchmarkListing).order_by(BenchmarkListing.id))
            listing.price_cad += 1
        JobQueue(db).enqueue("research_agent", "research.investigate", {"task_id": task_id},
                             idempotency_key=f"codex:recovery:{task_id}")
        worker = Worker(db, "a4a-recovery", job_types=["research.investigate"])
        assert worker.run_once()
        with db.session() as session:
            task = session.get(research.ResearchTask, task_id)
            assert not task.detail.get("concept_proposals"), task.detail
        outcome = _ideation(db, gid)
        assert outcome["outcome"] == "insufficient_evidence", outcome
        assert "census differs" in str(outcome["why"]), outcome
    finally:
        restore()


def test_object_specific_market_floor_does_not_use_unrelated_listings():
    db = _db()
    _listings(db, "kitchen_bath", [("a", "Dishcloth", 5),
                                    ("b", "Hot Pad", 6),
                                    ("b", "Trivet", 7)])
    observed = ideation.observe(db, "kitchen_bath", today=TODAY)
    assert not observed["ok"], observed
    assert "object-specific" in str(observed["reasons"]), observed


def test_restart_after_proposal_attachment_restores_gap_progress():
    db = _db()
    gid = _gap(db, "kitchen_bath")
    _listings(db, "kitchen_bath", KITCHEN)
    restore = _judge_intake_concepts()
    try:
        _drive(db, datetime.now(timezone.utc))
        task_id = _tasks(db)[0].id
        expected_slug = _tasks(db)[0].detail["concept_proposals"][0]["slug"]
        with db.session() as session:
            gap = session.get(CoverageGap, gid)
            evidence = dict(gap.evidence)
            record = dict(evidence["ideation"])
            record.update(outcome=None, slug=None)
            evidence["ideation"] = record
            gap.evidence = evidence
        JobQueue(db).enqueue("research_agent", "research.investigate", {"task_id": task_id},
                             idempotency_key=f"codex:reattach:{task_id}")
        assert Worker(db, "a4a-reattach", job_types=["research.investigate"]).run_once()
        record = _ideation(db, gid)
        assert record["outcome"] == "proposed", record
        assert record["slug"] == expected_slug, record
        assert len(_tasks(db)[0].detail["concept_proposals"]) == 1
    finally:
        restore()


def test_restart_recovers_one_proposal_audit_from_persisted_evidence():
    db = _db()
    gid = _gap(db, "kitchen_bath")
    _listings(db, "kitchen_bath", KITCHEN)
    _drive(db, datetime.now(timezone.utc))
    task = _tasks(db)[0]
    slug = task.detail["concept_proposals"][0]["slug"]
    # Simulate the old crash window: the proposal exists but the gap and audit
    # did not commit. This deletion is confined to the disposable test DB.
    with db.session() as s:
        for event in s.scalars(select(AuditLog).where(AuditLog.action == ideation.PROPOSED)):
            s.delete(event)
        gap = s.get(CoverageGap, gid)
        evidence = dict(gap.evidence)
        record = dict(evidence["ideation"])
        record.update(outcome=None, slug=None)
        evidence["ideation"] = record
        gap.evidence = evidence
    q = JobQueue(db)
    for n in range(2):
        q.enqueue("research_agent", "research.investigate", {"task_id": task.id},
                  idempotency_key=f"codex:audit-recovery:{n}")
        assert Worker(db, f"audit-recovery-{n}", job_types=["research.investigate"]).run_once()
    audits = _audits(db, ideation.PROPOSED)
    assert len(audits) == 1
    assert audits[0].artifact == slug
    assert audits[0].detail["task"] == task.id
    assert audits[0].detail["recovered_from_persisted_proposal"] is True
    assert _ideation(db, gid)["slug"] == slug
    assert len(_tasks(db)[0].detail["concept_proposals"]) == 1


def test_recovery_does_not_record_proposal_for_reassigned_gap():
    db = _db()
    gid = _gap(db, "kitchen_bath")
    _listings(db, "kitchen_bath", KITCHEN)
    _drive(db, datetime.now(timezone.utc))
    task = _tasks(db)[0]
    with db.session() as s:
        for event in s.scalars(select(AuditLog).where(AuditLog.action == ideation.PROPOSED)):
            s.delete(event)
        gap = s.get(CoverageGap, gid)
        evidence = dict(gap.evidence)
        record = dict(evidence["ideation"])
        record["task"] = task.id + 1000
        evidence["ideation"] = record
        gap.evidence = evidence
    JobQueue(db).enqueue("research_agent", "research.investigate", {"task_id": task.id},
                         idempotency_key="codex:wrong-owner-recovery")
    assert Worker(db, "wrong-owner", job_types=["research.investigate"]).run_once()
    assert not _audits(db, ideation.PROPOSED)
    assert _ideation(db, gid)["task"] == task.id + 1000


def test_two_recovery_workers_record_one_proposal_audit(monkeypatch):
    db = _db()
    gid = _gap(db, "kitchen_bath")
    _listings(db, "kitchen_bath", KITCHEN)
    _drive(db, datetime.now(timezone.utc))
    task = _tasks(db)[0]
    with db.session() as s:
        for event in s.scalars(select(AuditLog).where(AuditLog.action == ideation.PROPOSED)):
            s.delete(event)
        gap = s.get(CoverageGap, gid)
        evidence = dict(gap.evidence)
        record = dict(evidence["ideation"])
        record.update(outcome=None, slug=None)
        evidence["ideation"] = record
        gap.evidence = evidence
    q = JobQueue(db)
    jobs = [q.enqueue("research_agent", "research.investigate", {"task_id": task.id},
                      idempotency_key=f"concurrent-audit-recovery:{n}", priority=-1000)
            for n in range(2)]
    claimed = [q.claim(f"recovery-{n}", job_types=["research.investigate"])
               for n in range(2)]
    assert {job.id for job in claimed} == {job.id for job in jobs}
    barrier = threading.Barrier(2, timeout=20)
    original = ideation._reconcile_proposal

    def synchronized(*args, **kwargs):
        barrier.wait()
        return original(*args, **kwargs)

    monkeypatch.setattr(ideation, "_reconcile_proposal", synchronized)
    # Call the real registered handler on separately claimed durable jobs. The
    # worker's admission policy can serialize one agent and mask this race.
    contexts = [JobContext(job, db, q, Registry(db), Phase.SHADOW) for job in claimed]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(intel_ops.handle_research_investigate, contexts))
    assert all(outcome["why"] == "persisted proposal reconciled" for outcome in outcomes)
    assert len(_audits(db, ideation.PROPOSED)) == 1


def test_recovery_holds_when_existing_audit_conflicts_with_proposal():
    db = _db()
    gid = _gap(db, "kitchen_bath")
    _listings(db, "kitchen_bath", KITCHEN)
    _drive(db, datetime.now(timezone.utc))
    task = _tasks(db)[0]
    with db.session() as s:
        event = s.scalar(select(AuditLog).where(AuditLog.action == ideation.PROPOSED))
        event.artifact = "conflicting-test-slug"
        gap = s.get(CoverageGap, gid)
        evidence = dict(gap.evidence)
        record = dict(evidence["ideation"])
        record.update(outcome=None, slug=None)
        evidence["ideation"] = record
        gap.evidence = evidence
    q = JobQueue(db)
    queued = q.enqueue("research_agent", "research.investigate", {"task_id": task.id},
                       idempotency_key="codex:conflicting-audit-recovery")
    assert Worker(db, "conflicting-audit", job_types=["research.investigate"]).run_once()
    with db.session() as s:
        result = s.get(Job, queued.id).outputs
    assert "conflicting proposal audit" in result["why"]
    assert _ideation(db, gid)["outcome"] is None
    assert len(_audits(db, ideation.PROPOSED)) == 1


def test_recovery_refuses_inconsistent_persisted_census_reference():
    db = _db()
    _gap(db, "kitchen_bath")
    _listings(db, "kitchen_bath", KITCHEN)
    _drive(db, datetime.now(timezone.utc))
    task = _tasks(db)[0]
    with db.session() as s:
        for event in s.scalars(select(AuditLog).where(AuditLog.action == ideation.PROPOSED)):
            s.delete(event)
        stored = s.get(research.ResearchTask, task.id)
        sources = [dict(source) for source in stored.sources]
        sources[0]["citation"] = "db:unrelated-observation"
        stored.sources = sources
    queued = JobQueue(db).enqueue("research_agent", "research.investigate",
                                  {"task_id": task.id}, idempotency_key="bad-census-ref")
    assert Worker(db, "bad-census", job_types=["research.investigate"]).run_once()
    with db.session() as s:
        result = s.get(Job, queued.id).outputs
    assert "census references are inconsistent" in result["why"]
    assert not _audits(db, ideation.PROPOSED)


def test_recovery_refuses_worker_whose_lease_was_reclaimed():
    db = _db()
    _gap(db, "kitchen_bath")
    _listings(db, "kitchen_bath", KITCHEN)
    _drive(db, datetime.now(timezone.utc))
    task = _tasks(db)[0]
    with db.session() as s:
        for event in s.scalars(select(AuditLog).where(AuditLog.action == ideation.PROPOSED)):
            s.delete(event)
    q = JobQueue(db)
    target = q.enqueue("research_agent", "research.investigate", {"task_id": task.id},
                       idempotency_key="reclaimed-recovery", priority=-1000)
    claimed = q.claim("first-worker", job_types=["research.investigate"])
    assert claimed.id == target.id and claimed.lease_token
    stale = JobContext(claimed, db, q, Registry(db), Phase.SHADOW)
    with db.session() as s:
        row = s.get(Job, target.id)
        row.lease_token = "replacement-lease"
        row.leased_by = "new-worker"
    result = intel_ops.handle_research_investigate(stale)
    assert "lease is no longer current" in result["why"]
    assert not _audits(db, ideation.PROPOSED)


def test_reassigned_gap_holds_research_candidate_and_real_score_handler():
    db = _db()
    gid = _gap(db, "kitchen_bath")
    _listings(db, "kitchen_bath", KITCHEN)
    _drive(db, datetime.now(timezone.utc))
    task = _tasks(db)[0]
    slug = task.detail["concept_proposals"][0]["slug"]
    assert intake.approved_concept(db, slug) is not None
    with db.session() as s:
        gap = s.get(CoverageGap, gid)
        evidence = dict(gap.evidence)
        rec = dict(evidence["ideation"])
        rec["task"] = task.id + 1000
        evidence["ideation"] = rec
        gap.evidence = evidence
    assert not [c for c in intake.research_candidates(db, today=TODAY)
                if c["source_ref"] == f"research_task:{task.id}"]
    assert intake.approved_concept(db, slug) is None
    assert slug not in {seed.slug for seed in intake.pool_with_intake(db)}
    before = len(_jobs(db, "cir.draft"))
    queued = JobQueue(db).enqueue("market_radar", "radar.score", {"slug": slug},
                                  idempotency_key="codex:reassigned-score", priority=-1000)
    assert Worker(db, "reassigned-score", job_types=["radar.score"]).run_once()
    with db.session() as s:
        result = s.get(Job, queued.id).outputs
    assert result["promoted"] is False and result["reason"] == "not in the pool"
    assert len(_jobs(db, "cir.draft")) == before
    # A corrected owner record makes the still-valid approval visible again;
    # a transient mismatch does not fabricate a new approval or destroy it.
    with db.session() as s:
        gap = s.get(CoverageGap, gid)
        evidence = dict(gap.evidence)
        rec = dict(evidence["ideation"])
        rec["task"] = task.id
        evidence["ideation"] = rec
        gap.evidence = evidence
    assert intake.approved_concept(db, slug) is not None


def test_changed_attached_proposal_holds_old_approved_concept():
    db = _db()
    _gap(db, "kitchen_bath")
    _listings(db, "kitchen_bath", KITCHEN)
    _drive(db, datetime.now(timezone.utc))
    task = _tasks(db)[0]
    slug = task.detail["concept_proposals"][0]["slug"]
    assert intake.approved_concept(db, slug) is not None
    with db.session() as s:
        row = s.get(research.ResearchTask, task.id)
        detail = dict(row.detail)
        proposal = dict(detail["concept_proposals"][0])
        proposal["title"] += " changed"
        detail["concept_proposals"] = [proposal]
        row.detail = detail
    assert intake.approved_concept(db, slug) is None
    assert any(c["proposal"]["slug"] == slug for c in intake.research_candidates(db, today=TODAY))


def test_removing_ideation_markers_does_not_reclassify_existing_intake():
    db = _db()
    _gap(db, "kitchen_bath")
    _listings(db, "kitchen_bath", KITCHEN)
    _drive(db, datetime.now(timezone.utc))
    task = _tasks(db)[0]
    slug = task.detail["concept_proposals"][0]["slug"]
    assert intake.approved_concept(db, slug) is not None
    with db.session() as s:
        row = s.get(research.ResearchTask, task.id)
        detail = dict(row.detail)
        detail.pop("ideation_brief", None)
        detail.pop("ideation_refs", None)
        detail.pop("ideation_census", None)
        row.detail = detail
        row.trigger = "other-research"
    assert intake.approved_concept(db, slug) is None
    assert not [c for c in intake.research_candidates(db, today=TODAY)
                if c["source_ref"] == f"research_task:{task.id}"]


def test_unknown_shop_is_not_counted_as_an_independent_source():
    db = _db()
    _listings(db, "kitchen_bath", [("", "Dishcloth one", 5),
                                    ("", "Dishcloth two", 6),
                                    ("a", "Dishcloth three", 7)])
    observed = ideation.observe(db, "kitchen_bath", today=TODAY)
    assert observed["object_shops"] == 1, observed
    assert not observed["ok"], observed


def test_originality_rejects_normalized_competitor_variants():
    title, descriptor = "Tideline Stripe Dishcloth", "Tideline Stripe"
    for other in ("Ｔｉｄｅｌｉｎｅ Ｓｔｒｉｐｅ Ｄｉｓｈｃｌｏｔｈ",
                  "Tide-Line Stripe Dishcloth", "Tideline Stripes Dishcloths"):
        assert ideation.originality_reasons(title, descriptor, [("fixture", other)]), other


def test_same_marketplace_listing_under_multiple_keys_is_not_independent_evidence():
    db = _db()
    _listings(db, "kitchen_bath", [("a", "Dishcloth", 5),
                                    ("b", "Dishcloth", 6),
                                    ("c", "Dishcloth", 7)])
    with db.session() as session:
        for listing in session.scalars(select(BenchmarkListing)):
            listing.listing_ref = "999"
    observed = ideation.observe(db, "kitchen_bath", today=TODAY)
    assert observed["listings"] == 0 and not observed["ok"], observed
    with db.session() as session:
        for row, spelling in zip(session.scalars(select(BenchmarkListing)), ("1", "01", "001")):
            row.listing_ref = spelling
    observed = ideation.observe(db, "kitchen_bath", today=TODAY)
    assert observed["listings"] == 0 and not observed["ok"], observed


def test_unverified_heat_protection_is_refused_at_certificate_and_live_listing():
    from brambleloop.runtime.pipeline import Concept, concept_to_cir
    from brambleloop.gates.certificate import certify
    from brambleloop.publish.eligibility import name_truth
    cir = concept_to_cir(Concept(slug="hot-pad-old", title="Everyday Hot Pad",
        category="placemat", stitch_repeat=[("sc", 3), ("dc", 1)],
        width_stitches=48, rows=14, colors={"a": "#ffffff"}))
    verdict = certify(cir)
    assert not verdict.granted
    assert any(f.code == "HEAT_PROTECTION_UNVERIFIED" for f in verdict.findings)
    assert any("Heat-protection" in item for item in name_truth(cir))
    cir.title = "Everyday Placemat"
    assert any("Heat-protection" in item for item in name_truth(cir, {"title": "Ｐｏｔ-hоlder"}))


def test_distinct_benchmark_keys_for_one_resolved_shop_do_not_count_twice():
    db = _db()
    _listings(db, "kitchen_bath", [("a", "Dishcloth one", 5),
                                    ("b", "Dishcloth two", 6),
                                    ("b", "Dishcloth three", 7)])
    with db.session() as session:
        for listing in session.scalars(select(BenchmarkListing)):
            listing.detail = {**listing.detail, "source_shop_id": "1234"}
    observed = ideation.observe(db, "kitchen_bath", today=TODAY)
    assert observed["object_shops"] == 1 and not observed["ok"], observed
    with db.session() as session:
        rows = list(session.scalars(select(BenchmarkListing)))
        rows[0].detail = {**rows[0].detail, "source_shop_id": "0001234"}
        rows[1].detail = {**rows[1].detail, "source_shop_id": "²"}
        rows[2].detail = {**rows[2].detail, "source_shop_id": "1234"}
    observed = ideation.observe(db, "kitchen_bath", today=TODAY)
    assert observed["object_shops"] == 1 and not observed["ok"], observed


def test_scan_binds_resolved_shop_id_on_new_and_unchanged_listings():
    import test_intel
    from brambleloop.intel import observe

    db = test_intel._db()
    reader = test_intel._Reader([test_intel._listing(1, "Cotton Dishcloth")])
    observe.scan(db, reader, env={})
    with db.session() as session:
        row = session.scalar(select(BenchmarkListing).where(BenchmarkListing.listing_ref == "1"))
        assert row.detail["source_shop_id"] == "4242", row.detail
        row.detail = {k: v for k, v in row.detail.items() if k != "source_shop_id"}
    observe.scan(db, reader, env={})
    with db.session() as session:
        row = session.scalar(select(BenchmarkListing).where(BenchmarkListing.listing_ref == "1"))
        assert row.detail["source_shop_id"] == "4242", row.detail


def test_malformed_or_misattributed_catalogue_does_not_create_evidence_or_withdraw():
    import test_intel
    from brambleloop.intel import observe

    db = test_intel._db()
    reader = test_intel._Reader([test_intel._listing(1, "Cotton Dishcloth")])
    observe.scan(db, reader, env={})
    reader.listings = [test_intel._listing(None, "Invalid Dishcloth"),
                       test_intel._listing(2, "Other Dishcloth", shop_id=9999)]
    observe.scan(db, reader, env={})
    with db.session() as session:
        rows = list(session.scalars(select(BenchmarkListing)))
        old = next(row for row in rows if row.listing_ref == "1")
        assert old.audit_state != "withdrawn"
        assert not any(row.listing_ref == "None" for row in rows)
        mismatched = next(row for row in rows if row.listing_ref == "2")
        assert mismatched.detail["source_shop_id"] == "", mismatched.detail
    class UnresolvedReader(test_intel._Reader):
        def resolve_shop(self, name):
            return {"shop_id": None}
    observe.scan(db, UnresolvedReader([]), env={})
    with db.session() as session:
        old = session.scalar(select(BenchmarkListing).where(BenchmarkListing.listing_ref == "1"))
        assert old.audit_state != "withdrawn"


def test_legacy_padded_id_and_withdrawn_reappearance_do_not_duplicate_or_misstate():
    import test_intel
    from brambleloop.intel import observe
    db = test_intel._db()
    reader = test_intel._Reader([test_intel._listing(1, "Cotton Dishcloth")])
    observe.scan(db, reader, env={})
    with db.session() as session:
        row = session.scalar(select(BenchmarkListing))
        row.listing_ref = "0001"
        row.audit_state = "withdrawn"
    outcome = observe.scan(db, reader, env={})
    with db.session() as session:
        rows = list(session.scalars(select(BenchmarkListing)))
        assert len(rows) == 1 and rows[0].listing_ref == "0001", rows
        assert rows[0].audit_state == "audited", rows[0].audit_state
        assert rows[0].detail.get("gallery_audited") is True, rows[0].detail
    assert "1" in outcome.deep_audited, outcome
    assert outcome.new_listings == [] and outcome.withdrawn == [], outcome


def test_legacy_padded_listing_is_backfilled_using_canonical_id():
    import test_intel
    from brambleloop.intel import observe
    db = test_intel._db()
    reader = test_intel._Reader([test_intel._listing(1, "Cotton Dishcloth")])
    observe.scan(db, reader, env={})
    with db.session() as session:
        row = session.scalar(select(BenchmarkListing))
        row.listing_ref = "0001"
        row.detail = {k: v for k, v in row.detail.items() if k != "gallery_audited"}
    outcome = observe.scan(db, reader, env={})
    assert "1" in outcome.backfilled and "1" in outcome.deep_audited, outcome
    with db.session() as session:
        row = session.scalar(select(BenchmarkListing))
        assert row.detail.get("gallery_audited") is True


def test_ambiguous_legacy_listing_ids_are_held_without_duplicate_or_withdrawal():
    import test_intel
    from brambleloop.intel import observe
    db = test_intel._db()
    reader = test_intel._Reader([test_intel._listing(1, "Cotton Dishcloth")])
    observe.scan(db, reader, env={})
    with db.session() as session:
        row = session.scalar(select(BenchmarkListing))
        session.add(BenchmarkListing(benchmark_key=row.benchmark_key, listing_ref="0001",
                                     title=row.title, pod=row.pod, price_cad=row.price_cad,
                                     audit_state="audited", detail=dict(row.detail)))
    outcome = observe.scan(db, reader, env={})
    assert not outcome.new_listings and not outcome.withdrawn, outcome
    assert any("ambiguous" in p for p in outcome.problems), outcome.problems
    with db.session() as session:
        rows = list(session.scalars(select(BenchmarkListing)))
        assert len(rows) == 2 and all(r.audit_state != "withdrawn" for r in rows)


def test_withdrawn_observations_do_not_count_as_current_demand():
    db = _db()
    _listings(db, "kitchen_bath", KITCHEN)
    with db.session() as session:
        for listing in session.scalars(select(BenchmarkListing)):
            listing.audit_state = "withdrawn"
    observed = ideation.observe(db, "kitchen_bath", today=TODAY)
    assert observed["listings"] == 0 and not observed["ok"], observed


def test_truncated_catalogue_never_proves_existing_listing_disappeared():
    import test_intel
    from brambleloop.intel import observe
    from brambleloop.intel.etsy_public import CatalogueResult, PublicReader
    db = test_intel._db()
    reader = test_intel._Reader([test_intel._listing(1, "Cotton Dishcloth")])
    observe.scan(db, reader, env={})
    # An API page count says more exist than this capped read returned.
    public = object.__new__(PublicReader)
    public.get = lambda *args, **kwargs: {"count": 2, "results": [test_intel._listing(2, "Other")]}
    partial = public.catalogue(4242, limit=1, max_pages=1)
    assert isinstance(partial, CatalogueResult) and not partial.complete
    reader.catalogue = lambda _shop: partial
    observe.scan(db, reader, env={})
    with db.session() as session:
        original = session.scalar(select(BenchmarkListing).where(BenchmarkListing.listing_ref == "1"))
        assert original.audit_state != "withdrawn", original.audit_state


def test_contradictory_empty_page_and_duplicate_ids_do_not_prove_absence():
    import test_intel
    from brambleloop.intel import observe
    from brambleloop.intel.etsy_public import PublicReader
    db = test_intel._db()
    reader = test_intel._Reader([test_intel._listing(1, "Cotton Dishcloth")])
    observe.scan(db, reader, env={})
    public = object.__new__(PublicReader)
    public.get = lambda *args, **kwargs: {"count": 20, "results": []}
    partial = public.catalogue(4242, max_pages=1)
    assert not partial.complete
    for malformed in (-1, 1.5, True, "²", None):
        public.get = lambda *args, value=malformed, **kwargs: {"count": value, "results": []}
        assert not public.catalogue(4242, max_pages=1).complete, malformed
    reader.catalogue = lambda _shop: partial
    observe.scan(db, reader, env={})
    with db.session() as session:
        row = session.scalar(select(BenchmarkListing).where(BenchmarkListing.listing_ref == "1"))
        assert row.audit_state != "withdrawn"
    pages = iter([{"count": 2, "results": [test_intel._listing(2, "One")]},
                  {"count": 1, "results": [test_intel._listing(3, "Two")]}])
    public.get = lambda *args, **kwargs: next(pages)
    assert not public.catalogue(4242, limit=1, max_pages=2).complete
    duplicate = test_intel._listing(2, "Cotton Dishcloth")
    fresh = test_intel._db()
    outcome = observe.scan(fresh, test_intel._Reader([duplicate, dict(duplicate)]), env={})
    assert any("repeats" in p for p in outcome.problems), outcome.problems
    with fresh.session() as session:
        assert not list(session.scalars(select(BenchmarkListing)))


def test_nonfinite_market_prices_are_not_demand_evidence():
    db = _db()
    _listings(db, "kitchen_bath", [("a", "Dishcloth one", float("inf")),
                                    ("b", "Dishcloth two", float("inf")),
                                    ("b", "Dishcloth three", float("inf"))])
    observed = ideation.observe(db, "kitchen_bath", today=TODAY)
    assert not observed["ok"] and observed["price_median_cad"] is None, observed


def test_heat_claim_variants_are_held_without_verified_evidence():
    from brambleloop.gates.object_truth import heat_protection_findings
    from brambleloop.runtime.pipeline import Concept, concept_to_cir
    cir = concept_to_cir(Concept(slug="plain-mat", title="Plain Mat", category="placemat",
        stitch_repeat=[("sc", 3), ("dc", 1)], width_stitches=48, rows=14,
        colors={"a": "#ffffff"}))
    for text in ("Heat resistant table mat", "protects tables from hot cookware",
                 "Oven Mitt", "hot plate mat", "pot rest", "heatproof trivet",
                 "insulates your table from high temperatures", "safely handles hot pans"):
        assert heat_protection_findings(cir, texts=[text]), text
    assert not heat_protection_findings(cir)


def test_rerunning_and_redelivering_creates_no_duplicates():
    db = _db()
    gid = _gap(db, "kitchen_bath")
    _listings(db, "kitchen_bath", KITCHEN)
    restore = _judge_intake_concepts()
    try:
        now = datetime.now(timezone.utc)
        _drive(db, now)
        first = _counts(db)
        assert first["tasks"] == 1 and first["concepts"] == 1 and first["drafts"] == 1, first
        # Re-run the cadences in later windows (radar.scan and concept_intake fire again).
        _drive(db, now + timedelta(hours=7))
        _drive(db, now + timedelta(hours=13))
        # Re-deliver every event by hand under fresh keys.
        q = JobQueue(db)
        tid = _tasks(db)[0].id
        q.enqueue("research_agent", "research.investigate", {"task_id": tid},
                  idempotency_key="redeliver:investigate")
        q.enqueue("market_radar", "radar.score", {"handoff": {"source": "redelivery"}},
                  idempotency_key="redeliver:handoff")
        q.enqueue("market_radar", "radar.concept_intake", {}, idempotency_key="redeliver:intake")
        w = Worker(db, "a4a-redeliver", job_types=CHAIN)
        while w.run_once():
            pass
    finally:
        restore()
    again = _counts(db)
    assert {k: again[k] for k in ("tasks", "concepts", "proposals", "drafts", "intakes")} \
        == {k: first[k] for k in ("tasks", "concepts", "proposals", "drafts", "intakes")}, \
        (first, again)
    assert again["investigations"] == first["investigations"] + 1   # only the redelivery
    assert len(_audits(db, ideation.BRIEF_OPENED)) == 1
    assert len(_audits(db, ideation.PROPOSED)) == 1
    assert len(_audits(db, intake.APPROVED_ACTION)) == 1


def test_no_recorded_evidence_is_a_named_outcome_and_no_proposal():
    db = _db()
    gid = _gap(db, "kitchen_bath")
    _listings(db, "kitchen_bath", KITCHEN[:1])          # one listing, one shop: too thin
    _drive(db, datetime.now(timezone.utc))
    tasks = _tasks(db)
    assert len(tasks) == 1 and tasks[0].state == research.OPEN, \
        "the question stays open for re-investigation when observations arrive"
    assert not (tasks[0].detail or {}).get("concept_proposals")
    assert not tasks[0].findings, "no finding is invented"
    assert not _concepts(db)
    rec = _ideation(db, gid)
    assert rec["outcome"] == "insufficient_evidence", rec
    assert any("below 3" in r for r in rec["why"]) and any("shop" in r for r in rec["why"])
    named = _audits(db, ideation.INSUFFICIENT)
    assert len(named) == 1 and named[0].artifact == f"research_task:{tasks[0].id}"
    assert not [j for j in _jobs(db, "cir.draft") if j.idempotency_key[6:] not in POOL_SLUGS]


def test_a_title_that_overlaps_a_competitor_listing_is_refused():
    db = _db()
    gid = _gap(db, "kitchen_bath")
    # Competitor listings that already wear every house descriptor's dishcloth title.
    _listings(db, "kitchen_bath", KITCHEN + [
        (f"fx-shop-{i % 3}", f"{d[0]} Dishcloth Crochet Pattern", 6.0)
        for i, d in enumerate(ideation.HOUSE_DESCRIPTORS)])
    _drive(db, datetime.now(timezone.utc))
    rec = _ideation(db, gid)
    assert rec["outcome"] == "title_overlaps_competitor", rec
    assert any("observed listing" in r for r in rec["why"])
    assert not (_tasks(db)[0].detail or {}).get("concept_proposals")
    assert not _concepts(db) and len(_audits(db, ideation.TITLE_REFUSED)) == 1

    # The rule itself: equal, overlapping, or carrying our descriptor phrase.
    titles = [("L1", "Harbour Band Dishcloth"), ("L2", "Rustic Kiln Brick Washcloth Pattern"),
              ("L3", "Oat Furrow Dishcloth Pattern Easy")]
    assert "equals" in ideation.originality_reasons("Harbour Band Dishcloth",
                                                    "Harbour Band", titles)[0]
    assert "overlaps" in ideation.originality_reasons("Oat Furrow Dishcloth", "Oat Furrow",
                                                      titles)[0]
    assert "appears" in " ".join(ideation.originality_reasons("Kiln Brick Hot Pad",
                                                              "Kiln Brick", titles))
    assert ideation.originality_reasons("Linen Ridge Dishcloth", "Linen Ridge", titles) == []


def test_one_colliding_descriptor_is_skipped_not_copied():
    db = _db()
    gid = _gap(db, "kitchen_bath")
    n = len(ideation.HOUSE_DESCRIPTORS)
    first = ideation.HOUSE_DESCRIPTORS[gid % n][0]
    _listings(db, "kitchen_bath", KITCHEN + [("fx-shop-c", f"{first} Dishcloth", 6.0)])
    _drive(db, datetime.now(timezone.utc))
    prop = _tasks(db)[0].detail["concept_proposals"][0]
    assert not prop["title"].startswith(first), prop["title"]
    assert prop["title"] == f"{ideation.HOUSE_DESCRIPTORS[(gid + 1) % n][0]} Dishcloth"


def test_without_a_vision_judgement_the_concept_is_held_and_the_next_gap_proceeds():
    """No bypass: the research concept meets the same pre-engineering gate as any concept.
    Held WAITING on the vision judge, it is an outcome, so the next gap is opened."""
    db = _db()
    g1 = _gap(db, "kitchen_bath")
    g2 = _gap(db, "education", key="fixture-watch-2")
    _listings(db, "kitchen_bath", KITCHEN)
    now = datetime.now(timezone.utc)
    _drive(db, now)
    rows = _concepts(db)
    assert len(rows) == 1 and rows[0].state == intake.APPROVED
    held = [a for a in _audits(db, "radar.scored") if a.artifact == rows[0].slug]
    assert held and held[-1].detail["promoted"] is False and held[-1].detail["gate"] == "waiting"
    assert not [j for j in _jobs(db, "cir.draft") if j.idempotency_key == f"draft:{rows[0].slug}"]
    assert ideation.status(db, _ideation(db, g1)) == ("done", "held_at_pre_engineering_gate")
    _drive(db, now + timedelta(hours=7))
    assert _ideation(db, g2).get("task"), "the next gap was picked up on the next cadence tick"


# ---- continuation ----------------------------------------------------------------------------


def test_after_the_first_concept_completes_the_next_gap_is_picked_up_on_the_next_tick():
    db = _db()
    g1 = _gap(db, "kitchen_bath")
    g2 = _gap(db, "education", key="fixture-watch-2")
    g3 = _gap(db, "kitchen_bath", key="fixture-watch-3")
    _listings(db, "kitchen_bath", KITCHEN)
    _listings(db, "education", [("fx-shop-a", "Crochet Masterclass Guidebook", 12.0),
                                ("fx-shop-b", "Beginner Crochet Course", 15.0),
                                ("fx-shop-c", "Stitch Guide Book", 9.0)])
    restore = _judge_intake_concepts()
    try:
        now = datetime.now(timezone.utc)
        _drive(db, now)
        # Tick 1: exactly one gap is ideated; the others wait behind it (bounded).
        assert [bool(_ideation(db, g).get("task")) for g in (g1, g2, g3)] == \
            [True, False, False]
        assert _audits(db, ideation.WAITING)
        slug = _ideation(db, g1)["slug"]
        draft = [j for j in _jobs(db, "cir.draft") if j.idempotency_key == f"draft:{slug}"]
        assert draft and draft[0].status == JobStatus.DONE
        st = ideation.status(db, _ideation(db, g1))
        assert st[0] == "done" and st[1] in ("drafted", "draft_refused"), st

        # Tick 2 (the next radar.scan window): with no manual action the next eligible gap
        # is picked up. g3 is in the same pod as the new concept, which now answers it, so
        # it is re-scored, not re-ideated (no near-duplicate SKU); g2 is opened.
        _drive(db, now + timedelta(hours=7))
    finally:
        restore()
    rec2 = _ideation(db, g2)
    assert rec2.get("task"), "the second gap was picked up"
    assert rec2["outcome"] == "no_supported_object", rec2
    assert not _ideation(db, g3).get("task")
    assert len(_concepts(db)) == 1
    done = [a.detail for a in _audits(db, ideation.COMPLETED)]
    assert any(d["gap"] == g1 and d["outcome"] in ("drafted", "draft_refused") for d in done)
    handoffs = [j for j in _jobs(db, "radar.score")
                if j.idempotency_key.startswith("coverage-handoff:scan:")]
    assert len(handoffs) >= 2 and all(j.status == JobStatus.DONE for j in handoffs)


def test_the_new_module_is_reached_from_the_runtime():
    from brambleloop.build2 import reachability

    reachability.reachable.cache_clear()
    reachability._references.cache_clear()
    v = reachability.reached("radar/ideation.py")
    assert v["reached"], v


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
