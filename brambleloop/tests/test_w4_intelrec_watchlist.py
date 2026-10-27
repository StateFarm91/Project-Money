"""W4-INTELREC: the owner's permanent watchlist and the chain it feeds.

OFFLINE INTEGRATION TEST -- NOT PRODUCTION EVIDENCE. Every Etsy read is a recorded fixture
reader; nothing touches a network, spends, or writes to Etsy. What it proves is the wiring on
the real job system (JobQueue + Worker + the registered handlers), not that production does it.

The chain driven end to end: seeded official-API observations of the three non-anchor shops
(plus Mrs J's stored rows) -> intel.watchlist_scan -> intel.watchlist_compare (validation by
cross-shop corroboration) -> Laura's executive tick (the new `intelligence` provider) ->
intel.opportunity_review (a durable decision) -> non-spending radar.score jobs for the pool
concepts that answer the arena -> the attempt is MEASURED (scored) and not promoted, twice ->
a recorded lesson -> a later decision on the same arena changes because of it.

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
            design_ids = list(ev["design_job_ids"])
            assert {s.get(Job, i).job_type for i in design_ids} == {"radar.score"}

        # The scored attempt is measured and nothing is promoted -- twice.
        for attempt in (1, 2):
            _measured(db, design_ids, promoted=False)
            watchlist.review(db, enqueue=_enqueuer(db))
            with db.session() as s:
                g = s.get(CoverageGap, gap_id)
                ev = dict(g.evidence)
                state_now = g.state
            if attempt == 1:
                assert ev.get("design_job_ids") and set(ev["design_job_ids"]).isdisjoint(
                    design_ids)
                design_ids = list(ev["design_job_ids"])
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


def _measured(db, ids, *, promoted, status=JobStatus.DONE, scored=True):
    with db.session() as s:
        for i in ids:
            j = s.get(Job, i)
            j.status = status
            j.finished_at = datetime.now(timezone.utc) - timedelta(days=2)
            j.outputs = ({"slug": j.inputs.get("slug"), "score": 0.4 + 0.5 * promoted,
                          "promoted": promoted} if scored else
                         {"slug": j.inputs.get("slug"), "promoted": False,
                          "reason": "not in the pool"})


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
        third = watchlist.scan_all(db)
        assert [c for c in calls[before:] if c[1] == "MadelineMaeCo"] == []
        # Review L-6: the failing shop is not re-read inside its backoff window either.
        assert [c for c in calls[before:] if c[1] == "ZKBDESIGNER"] == []
        zk = next(x for x in third["shops"] if x["key"] == "zkbdesigner")
        assert zk["deferred"] and "backoff" in zk["why"], zk
        # The outage is visible to Laura after the second failure, never a dead letter.
        assert watchlist._state(db, "zkbdesigner")["consecutive_failures"] == 2  # 2 reads
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



def _gap(db, pod="hats", arena=None):
    return coverage.upsert(db, benchmark_key=watchlist.WATCHLIST_KEY,
                           arena=arena or f"watchlist:{pod}", pod=pod)


def test_summary_is_unknown_when_unconfigured_or_refused():
    """Review M-1: an unobserved watchlist never reads OK to Laura."""
    db = _db()
    assert watchlist.summary(db)["status"] == "UNKNOWN"          # never read
    out = watchlist.scan_all(db, env={})                          # no credential
    assert out["ran"] is False
    sm = watchlist.summary(db)
    assert sm["status"] == "UNKNOWN" and "not_configured" in sm["reason"], sm
    # A key-wide credential refusal at the last etsy.probe, then the scan waits.
    from brambleloop.core.models import AuditLog

    db = _db()
    with db.session() as s:
        s.add(AuditLog(actor="etsy", action="etsy.probe",
                       detail={"ok": False, "status": 403, "reason": "HTTP 403"}))
    real = watchlist._reader
    watchlist._reader = lambda env=None: Reader()
    try:
        out = watchlist.scan_all(db)
    finally:
        watchlist._reader = real
    assert out["ran"] is False
    sm = watchlist.summary(db)
    assert sm["status"] == "UNKNOWN" and "credential_refused" in sm["reason"], sm
    assert all(watchlist._state(db, k)["state"] == "credential_refused"
               for k in ("madeline_mae_co", "zkbdesigner", "the_easy_design"))
    # Observed and quiet: OK.
    db = _db()
    _with_reader(Reader())
    try:
        watchlist.scan_all(db, force=True)
    finally:
        watchlist.reader_factory = None
    assert watchlist.summary(db)["status"] == "OK"


def test_design_outcomes_are_classified_from_what_the_job_produced():
    """Review H-1: a refused, parked or dead route is not an attempt and teaches nothing; a
    promotion is progress; only a MEASURED non-promotion counts toward the lesson."""
    from datetime import date

    db = _db()
    gid = _gap(db)
    q = _enqueuer(db)
    day = date(2026, 10, 27)
    seen: set = set()
    for status in (JobStatus.DEAD, JobStatus.DONE, JobStatus.CANCELLED):
        watchlist.review(db, enqueue=q, today=day)
        ids = watchlist._open_gaps(db)[0]["evidence"]["design_job_ids"]
        assert ids and seen.isdisjoint(ids)             # each route on a fresh key
        seen |= set(ids)
        _measured(db, ids, promoted=False, status=status, scored=False)
        out = watchlist.review(db, enqueue=q, today=day)
        assert [d["last"] for d in out["decisions"]] == ["route_refused"], out
        # parked: not re-routed the next day (L-4), only after REDECIDE_AFTER
        assert watchlist.review(db, enqueue=q, today=day + timedelta(days=1))["decisions"] == []
        day = day + watchlist.REDECIDE_AFTER
    with db.session() as s:
        g = s.get(CoverageGap, gid)
        assert g.state == coverage.UNCOVERED and not g.evidence.get("failed_attempts")
        assert s.scalar(select(Lesson).where(
            Lesson.evidence_ref == f"watchlist_gap:{gid}")) is None
    # A successful radar.score (promoted) is progress, not a failure.
    watchlist.review(db, enqueue=q, today=day)
    ids = watchlist._open_gaps(db)[0]["evidence"]["design_job_ids"]
    _measured(db, ids[:1], promoted=True)
    _measured(db, ids[1:], promoted=False)
    out = watchlist.review(db, enqueue=q, today=day)
    assert [d["last"] for d in out["decisions"]] == ["progressed"], out
    with db.session() as s:
        g = s.get(CoverageGap, gid)
        assert g.state == coverage.CONCEPTING and not g.evidence.get("failed_attempts")


def test_no_paid_job_types_are_queued_by_the_scan_or_the_review():
    """Review M-2/M-3/M-4/I-2: Laura-delegable and scan work never originates paid jobs."""
    from brambleloop.autonomy import charters
    from brambleloop.intel import mission_runtime

    db = _db()
    queued = []

    def enqueue(agent, job_type, inputs, **kw):
        queued.append(job_type)
        return None
    real = mission_runtime.process

    def mission(db_, *, enqueue, **kw):     # a mission step that asks for paid work
        enqueue("creative_director", "creative.tournament", {}, idempotency_key="x")
        enqueue("market_radar", "radar.score", {}, idempotency_key="y")
        return {"pending": 0, "processed": 1}
    mission_runtime.process = mission
    _with_reader(Reader())
    try:
        out = watchlist.scan_all(db, enqueue=enqueue, force=True)
    finally:
        mission_runtime.process = real
        watchlist.reader_factory = None
    withheld = [s["mission"]["paid_work_withheld"] for s in out["shops"]]
    assert all(w == ["creative.tournament"] for w in withheld), withheld
    watchlist.record_comparison(db)
    _gap(db, "hats", "watchlist:hats:x")
    nope = _gap(db, "education")                          # no pool concept answers it
    rev = watchlist.review(db, enqueue=enqueue)
    assert set(queued) <= {"radar.score"}, queued
    assert not set(queued) & watchlist.PAID_JOB_TYPES
    assert any(d["gap"] == nope and d["last"] == "needs_original_design"
               for d in rev["decisions"]), rev
    # The constitution is told CA$0 for Laura's delegation; the reasons say why that holds.
    assert "radar.score" in charters.SAFE_GENERATED["intel.opportunity_review"]
    assert "intel.opportunity_review" in charters.SAFE_GENERATED


def test_parked_gaps_are_not_redecided_daily():
    """Review L-4: needs_original_design/deferred gaps leave the waiting list until the
    corroborating shops change or REDECIDE_AFTER passes."""
    from datetime import date

    db = _db()
    _with_reader(Reader())
    try:
        watchlist.scan_all(db, force=True)
    finally:
        watchlist.reader_factory = None
    gid = _gap(db, "education")
    d0 = date(2026, 10, 27)
    first = watchlist.review(db, enqueue=_enqueuer(db), today=d0)
    assert [d["last"] for d in first["decisions"] if d["gap"] == gid] == ["needs_original_design"]
    assert gid not in watchlist.summary(db)["waiting"]
    nxt = watchlist.review(db, enqueue=_enqueuer(db), today=d0 + timedelta(days=1))
    assert [d for d in nxt["decisions"] if d["gap"] == gid] == []
    week = watchlist.review(db, enqueue=_enqueuer(db), today=d0 + watchlist.REDECIDE_AFTER)
    assert [d["gap"] for d in week["decisions"]].count(gid) == 1
    # new corroboration re-opens it at once
    watchlist._merge_gap_evidence(db, gid, {"corroborated_by": ["shop-x", "shop-y"]})
    again = watchlist.review(db, enqueue=_enqueuer(db),
                             today=d0 + watchlist.REDECIDE_AFTER + timedelta(days=1))
    assert [d["gap"] for d in again["decisions"]].count(gid) == 1


def test_stale_and_unmeasured_figures_are_not_measured():
    """Review L-1/L-2/L-3."""
    db = _db()

    class NoReviews(Reader):
        def reviews(self, shop_id, *, limit=100):
            return []
    _with_reader(NoReviews())
    try:
        watchlist.scan_all(db, force=True)
        watchlist.reader_factory = lambda: NoReviews(down={"ZKBDESIGNER"})
        watchlist.scan_all(db, force=True)
        rep = watchlist.compare(db)
    finally:
        watchlist.reader_factory = None
    by = {s["alias"]: s for s in rep["shops"]}
    zkb = by[watchlist.benchmark_alias_safe("zkbdesigner")]
    assert zkb["observation"]["state"] == "source_outage"
    assert zkb["figures"]["public_sales"]["grade"] == "STALE"
    mad = by[watchlist.benchmark_alias_safe("madeline_mae_co")]
    assert mad["figures"]["public_sales"]["grade"] == "MEASURED"
    assert mad["figures"]["recurring_complaint_themes"]["grade"] == "UNKNOWN"
    assert rep["shops"][0]["observation"]["state"] in ("rows_present", "never")


def test_refused_shops_back_off_and_a_scan_resolves_each_shop_once():
    """Review L-6."""
    db = _db()
    calls: list = []
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _with_reader(Reader(down={"ZKBDESIGNER"}, calls=calls))
    try:
        watchlist.scan_all(db, now=now)
        resolves = [c for c in calls if c == ("resolve", "MadelineMaeCo")]
        assert len(resolves) == 1, calls
        for h in (1, 7, 13):                      # 1 failure: wait 6 h; 2 failures: 12 h
            watchlist.scan_all(db, now=now + timedelta(hours=h))
        zkb = [c for c in calls if c == ("resolve", "ZKBDESIGNER")]
        assert len(zkb) == 2, zkb                  # at 0 h and 7 h; 1 h and 13 h back off
        assert watchlist._state(db, "zkbdesigner")["consecutive_failures"] == 2
    finally:
        watchlist.reader_factory = None


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
