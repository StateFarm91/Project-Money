"""W4-INTELREC: the owner's permanent watchlist and the chain it feeds.

OFFLINE INTEGRATION TEST -- NOT PRODUCTION EVIDENCE. Every Etsy read is a recorded fixture
reader; nothing touches a network, spends, or writes to Etsy. What it proves is the wiring on
the real job system (JobQueue + Worker + the registered handlers), not that production does it.

The chain driven end to end: seeded official-API observations of the three non-anchor shops
(plus Mrs J's stored rows) -> intel.watchlist_scan -> intel.watchlist_compare (validation by
cross-shop corroboration) -> Laura's executive tick (the new `intelligence` provider) ->
intel.opportunity_review (a durable decision) -> a departmental job (creative.tournament) ->
the attempt settles without an engineered product, twice -> a recorded lesson -> a later
decision on the same arena changes because of it.

Also: duplicate suppression, safe retries, source outage, persistence across restart, spend
limits, no endless repetition of a failed strategy, and no competitor content in the record.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _k in ("ETSY_API_KEY", "ETSY_SHARED_SECRET", "ETSY_KEYSTRING", "ANTHROPIC_API_KEY"):
    os.environ.pop(_k, None)

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Benchmark, BenchmarkListing, CoverageGap, Job, JobStatus, Lesson, Phase, Product)
from brambleloop.intel import benchmarks, coverage, watchlist  # noqa: E402
from brambleloop.intel.etsy_public import ReadFailed  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

DESCRIPTION = ("Crochet PATTERN, PDF instant download, 9 pages. Written instructions, US "
               "terms. Worsted weight yarn, 5 mm hook.")


def _listing(lid, title, fav=10, price=900, sale=False):
    return {"listing_id": lid, "title": title,
            "price": {"amount": price, "divisor": 100, "currency_code": "CAD"},
            "tags": ["crochet pattern"], "materials": ["yarn"], "state": "active",
            "last_modified_timestamp": 1000, "num_favorers": fav, "taxonomy_id": 66,
            "is_digital": True, "is_sale": sale, "description": DESCRIPTION,
            "url": f"https://fixture.invalid/listing/{lid}"}


# Two shops sell hats (the corroborated arena); one sells bags only.
CATALOGUES = {
    "MadelineMaeCo": [_listing(5000 + i, f"Ribbed Beanie Hat Crochet Pattern {i}") for i in range(4)],
    "ZKBDESIGNER": [_listing(6000 + i, f"Slouchy Bucket Hat Crochet Pattern {i}", sale=i == 0)
                    for i in range(3)],
    "TheEasyDesign": [_listing(7000 + i, f"Market Tote Bag Crochet Pattern {i}") for i in range(3)],
}
SHOPS = {"MadelineMaeCo": 1, "ZKBDESIGNER": 2, "TheEasyDesign": 3}


class Reader:
    """Recorded official-API answers. `down` names shops whose reads fail (an outage)."""

    def __init__(self, down=(), calls=None):
        self.down = set(down)
        self.calls = calls if calls is not None else []

    def resolve_shop(self, name):
        self.calls.append(("resolve", name))
        if name in self.down:
            raise ReadFailed(f"find_shops returned HTTP 503 for {name}", status=503)
        return {"shop_id": SHOPS[name], "shop_name": name, "transaction_sold_count": 1200,
                "review_count": 310, "review_average": 4.9, "num_favorers": 5000,
                "listing_active_count": len(CATALOGUES[name])}

    def catalogue(self, shop_id, **kw):
        name = next(n for n, i in SHOPS.items() if i == shop_id)
        return list(CATALOGUES[name])

    def images(self, ref):
        return [{"rank": i + 1, "url_fullxfull": f"https://fixture.invalid/{ref}/{i}.jpg"}
                for i in range(5)]

    def videos(self, ref):
        return []

    def reviews(self, shop_id, *, limit=100):
        return [{"rating": 2, "review": "the instructions were confusing"}] * 3


def _db(path=None):
    db = Database(f"sqlite:///{path or tempfile.mkdtemp(prefix='intelrec-') + '/i.db'}")
    db.create_all()
    Registry(db).seed_defaults()
    benchmarks.seed(db)
    return db


def _run(db, job_type, inputs=None, *, agent="market_radar", key=None):
    job = JobQueue(db).enqueue(agent, job_type, dict(inputs or {}), priority=0,
                               idempotency_key=key or f"t:{job_type}:{os.urandom(4).hex()}")
    Worker(db, "intelrec", phase=Phase.SHADOW, job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, (job_type, row.status, row.last_error)
        return dict(row.outputs or {})


def _with_reader(reader):
    watchlist.reader_factory = lambda: reader


def test_the_watchlist_is_exact_and_permanent():
    keys = [m.key for m in watchlist.WATCHLIST]
    assert keys == [benchmarks.MJS_KEY, "madeline_mae_co", "zkbdesigner", "the_easy_design"]
    roles = {m.shop_name: (m.role, m.special) for m in watchlist.WATCHLIST}
    assert roles["MJsOffTheHookDesigns"] == ("anchor", True)
    assert roles["MadelineMaeCo"] == ("special", True)
    assert roles["ZKBDESIGNER"] == ("permanent", False)
    assert roles["TheEasyDesign"] == ("permanent", False)
    urls = {m.shop_name: m.owner_url for m in watchlist.WATCHLIST}
    assert urls["ZKBDESIGNER"] == "https://www.etsy.com/ca/shop/ZKBDESIGNER"
    assert urls["TheEasyDesign"] == "https://www.etsy.com/ca/shop/TheEasyDesign"
    assert urls["MadelineMaeCo"] == "https://www.etsy.com/shop/MadelineMaeCo"
    # Mrs J's original registry entry is untouched (#301 owner-supplied URL verbatim).
    assert benchmarks.MJS.owner_supplied_url == benchmarks.MJS_OWNER_SUPPLIED_URL
    db = _db()
    with db.session() as s:
        rows = {b.key: b for b in s.scalars(select(Benchmark))}
    assert set(keys) <= set(rows) and all(rows[k].mandatory for k in keys)
    assert all(watchlist.SCOPE[k] for k in ("public_sales_milestones", "price_and_promotions",
                                            "review_counts_and_sentiment", "bundles"))


def test_offline_observation_to_lesson_through_the_real_job_system():
    """OFFLINE, NOT PRODUCTION: observation -> validation -> Laura -> department -> lesson."""
    db = _db()
    _with_reader(Reader())
    try:
        scan = _run(db, "intel.watchlist_scan", {"force": True})
        assert scan["ran"] and scan["observed"] == 3, scan
        with db.session() as s:
            seen = {k: n for k, n in s.execute(
                select(BenchmarkListing.benchmark_key, BenchmarkListing.id))}
        assert {"madeline_mae_co", "zkbdesigner", "the_easy_design"} <= set(seen)

        cmp_ = _run(db, "intel.watchlist_compare")
        assert cmp_["validated_arenas"] >= 1, cmp_
        with db.session() as s:
            gap = s.scalar(select(CoverageGap).where(
                CoverageGap.benchmark_key == watchlist.WATCHLIST_KEY))
            gap_id, pod = gap.id, gap.pod
            assert len(gap.evidence["corroborated_by"]) >= 2

        # Laura observes the intelligence provider and delegates the review.
        assert watchlist.summary(db)["status"] == "DEGRADED"
        from brambleloop.laura.executive import loop

        state = loop.observe(db)
        assert state["providers"]["intelligence"]["status"] == "DEGRADED", state["providers"]
        pri = [p for p in loop.prioritise(state, now=datetime.now(timezone.utc))
               if p.rule == "provider" and p.subject == "intelligence"]
        assert pri and pri[0].job_type == "intel.opportunity_review"
        _run(db, "laura.executive_tick", {}, agent="laura")
        with db.session() as s:
            delegated = s.scalar(select(Job).where(Job.job_type == "intel.opportunity_review"))
        assert delegated is not None, "Laura did not delegate the opportunity review"
        Worker(db, "intelrec-review", phase=Phase.SHADOW,
               job_types=["intel.opportunity_review"]).run_once()
        with db.session() as s:
            ev = dict(s.get(CoverageGap, gap_id).evidence)
            design = s.get(Job, ev["design_job_id"])
            assert design.job_type in ("creative.tournament", "radar.score"), design.job_type
            design_id = design.id

        # The departmental attempt settles without an engineered product -- twice.
        for attempt in (1, 2):
            with db.session() as s:
                j = s.get(Job, design_id)
                j.status = JobStatus.DONE
                j.finished_at = datetime.now(timezone.utc) - timedelta(days=2)
            watchlist.review(db, enqueue=_enqueuer(db))
            with db.session() as s:
                g = s.get(CoverageGap, gap_id)
                ev = dict(g.evidence)
                state_now = g.state
            if attempt == 1:
                assert ev.get("design_job_id") and ev["design_job_id"] != design_id
                design_id = ev["design_job_id"]
        assert state_now == coverage.NOT_PURSUING
        with db.session() as s:
            lesson = s.scalar(select(Lesson).where(
                Lesson.evidence_ref == f"watchlist_gap:{gap_id}"))
        assert lesson is not None and "stop re-asking" in lesson.statement

        # The lesson changes a later decision: a new gap in the same arena is deferred.
        new = coverage.upsert(db, benchmark_key=watchlist.WATCHLIST_KEY,
                              arena=f"watchlist:{pod}:again", pod=pod)
        later = watchlist.review(db, enqueue=_enqueuer(db))
        mine = [d for d in later["decisions"] if d["gap"] == new]
        assert mine and mine[0]["last"] == "deferred_by_lesson", later
    finally:
        watchlist.reader_factory = None


def _enqueuer(db):
    q = JobQueue(db)
    from brambleloop.queue.durable import DuplicateJob

    def enqueue(agent, job_type, inputs, *, idempotency_key=None, **kw):
        try:
            return q.enqueue(agent, job_type, inputs, idempotency_key=idempotency_key, **kw)
        except DuplicateJob:
            return None
    return enqueue


def test_duplicates_retries_outage_and_restart():
    path = tempfile.mkdtemp(prefix="intelrec-r-") + "/i.db"
    db = _db(path)
    calls: list = []
    _with_reader(Reader(down={"ZKBDESIGNER"}, calls=calls))
    try:
        first = watchlist.scan_all(db, force=True)
        assert first["observed"] == 2 and first["outages"] == ["zkbdesigner"]
        with db.session() as s:
            n1 = s.query(BenchmarkListing).count()
        # Duplicate suppression: the same unchanged catalogue adds no rows and no events.
        watchlist.scan_all(db, force=True)
        with db.session() as s:
            assert s.query(BenchmarkListing).count() == n1
        # Not due: the adaptive interval defers a healthy shop, no read is made.
        before = len(calls)
        watchlist.scan_all(db)
        assert [c for c in calls[before:] if c[1] == "MadelineMaeCo"] == []
        # The outage is visible to Laura after the second failure, never a dead letter.
        assert watchlist._state(db, "zkbdesigner")["consecutive_failures"] == 3  # 3 attempts
        assert "source outage" in watchlist.summary(db)["reason"]
        # Persistence across restart: a fresh process reads the same state from the database.
        db2 = Database(f"sqlite:///{path}")
        assert watchlist._state(db2, "madeline_mae_co")["state"] == "ok"
        assert watchlist._state(db2, "zkbdesigner")["state"] == "source_outage"
        # Recovery: the shop comes back and the failure count resets.
        _with_reader(Reader())
        watchlist.scan_all(db2, force=True)
        assert watchlist._state(db2, "zkbdesigner")["consecutive_failures"] == 0
        # Safe retry: the review is idempotent per attempt -- running it twice queues one job.
        db2_q = _enqueuer(db2)
        watchlist.record_comparison(db2)
        a = watchlist.review(db2, enqueue=db2_q)
        b = watchlist.review(db2, enqueue=db2_q)
        assert len(a["decisions"]) >= 1 and b["decisions"] == []
    finally:
        watchlist.reader_factory = None


def test_no_competitor_content_and_ai_use_is_never_assumed():
    db = _db()
    _with_reader(Reader())
    try:
        watchlist.scan_all(db, force=True)
        rep = watchlist.record_comparison(db)["report"]
    finally:
        watchlist.reader_factory = None
    text = json.dumps(rep)
    for name in SHOPS:
        assert name.lower() not in text.lower()
    assert "Beanie" not in text and "Tote" not in text           # no titles
    assert all(s["ai_use"]["assessment"] == "UNKNOWN" and s["ai_use"]["hypothesis_only"]
               for s in rep["shops"])
    graded = rep["shops"][1]["figures"]
    assert graded["public_sales"]["grade"] == "MEASURED"
    assert graded["public_sales"]["source"] == "findShops" and graded["public_sales"]["as_of"]
    mrs_j = rep["shops"][0]["figures"]
    assert mrs_j["public_sales"]["grade"] == "UNKNOWN"            # never read here: UNKNOWN


def test_a_validated_arena_becomes_a_research_agent_question_once():
    """G6: the Research Agent is asked whether the corroborated demand is durable."""
    from brambleloop.intel.research import ResearchTask

    db = _db()
    _with_reader(Reader())
    try:
        watchlist.scan_all(db, force=True)
        first = watchlist.record_comparison(db)
        again = watchlist.record_comparison(db)
    finally:
        watchlist.reader_factory = None
    assert first["gaps"] and first["gaps"] == again["gaps"]
    with db.session() as s:
        tasks = list(s.scalars(select(ResearchTask)))
        gap = s.get(CoverageGap, first["gaps"][0])
        assert len(tasks) == len(first["gaps"])               # deduped on the trigger
        assert gap.evidence["research_task_id"] == tasks[0].id
        assert tasks[0].decision_ref.startswith("intel.opportunity_review:gap:")
    out = watchlist.review(db, enqueue=_enqueuer(db))
    assert out["decisions"][0]["history"][-1]["research_task_id"] == tasks[0].id


def test_spend_limits_and_bounded_work():
    """The watchlist jobs spend nothing (no cost rows) and the review starts at most
    REVIEW_LIMIT departmental jobs per run; paid work it starts passes the existing ceilings."""
    from brambleloop.core.models import CostEntry

    db = _db()
    _with_reader(Reader())
    try:
        _run(db, "intel.watchlist_scan", {"force": True})
        _run(db, "intel.watchlist_compare")
        for i in range(6):
            coverage.upsert(db, benchmark_key=watchlist.WATCHLIST_KEY,
                            arena=f"watchlist:extra{i}", pod="hats")
        out = watchlist.review(db, enqueue=_enqueuer(db))
    finally:
        watchlist.reader_factory = None
    assert len(out["decisions"]) <= watchlist.REVIEW_LIMIT
    with db.session() as s:
        assert s.query(CostEntry).count() == 0
    from brambleloop.agents.registry import Registry as R

    R(db).authorize("market_radar", "intel.watchlist_scan")
    R(db).authorize("market_radar", "intel.opportunity_review")


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
