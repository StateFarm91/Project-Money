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
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, BenchmarkListing, CoverageGap, Job, JobStatus,
)
from brambleloop.intel import coverage, research  # noqa: E402
from brambleloop.intel.benchmarks import MJS_KEY  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.radar import ideation, intake  # noqa: E402
from brambleloop.radar.opportunity import POOL  # noqa: E402
from brambleloop.runtime import intel_ops  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Scheduler, Worker  # noqa: E402

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
            s.add(BenchmarkListing(benchmark_key=shop, listing_ref=f"fx-{pod}-{n + i}",
                                   title=title, pod=pod, price_cad=price,
                                   audit_state="audited", first_seen=seen, last_seen=seen,
                                   detail={}))


# One shop is the owner's benchmark (MJS): the pre-engineering anti-clone check measures a
# concept against that benchmark's observed listings in the pod, and waits without them.
KITCHEN = [(MJS_KEY, "Farmhouse Dishcloth Crochet Pattern", 5.5),
           (MJS_KEY, "Rustic Cotton Washcloth Pattern", 6.0),
           ("fx-shop-b", "Cotton Washcloth Crochet Pattern", 6.5),
           ("fx-shop-b", "Granny Potholder Pattern", 7.0),
           ("fx-shop-c", "Scrubby Dishcloth Set Pattern", 7.5)]


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
