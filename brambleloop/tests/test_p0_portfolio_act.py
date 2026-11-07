"""P0-PORTFOLIO-ACT: portfolio.review classifications become bounded, keyed jobs.

Real `portfolio.review` handler through the real Worker, file-backed SQLite. The fixtures are
the rows the classifier reads: certified releases, listing outcomes, an open P1 incident and
the earlier `listing.seo` job a rebuild repeats. Every product is a test fixture.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_p0_portfolio_act.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import hashlib
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Incident, Job, JobStatus, Listing, ListingOutcome, OwnerAction, PatternVersion,
    Product,
)
from brambleloop.growth import portfolio_act as PA  # noqa: E402
from brambleloop.growth.portfolio import RETIRE, REWORK, SEO_PROBLEM, Classification  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.core.phase import Phase  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import JobContext, Worker, handlers  # noqa: E402

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='pact_')}/pact.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _release(db, slug: str, *, seo_history: bool = True) -> None:
    with db.session() as s:
        p = Product(slug=slug, title=slug, status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0",
                             cir_json={"components": [{"name": "body"}]},
                             release_hash=hashlib.sha256(slug.encode()).hexdigest(),
                             certified=True, certificate={"stages_run": ["compile"]}))
        s.add(Listing(product_slug=slug, version="1.0.0", title=f"{slug} crochet pattern",
                      description="d", tags=["crochet pattern"], price_cad=9.0,
                      state="published", etsy_listing_id=f"e-{slug}",
                      created_at=NOW - timedelta(days=60)))
        if seo_history:
            s.add(Job(agent="listing", job_type="listing.seo",
                      inputs={"slug": slug, "version": "1.0.0", "category": "home_decor"},
                      status=JobStatus.DONE, finished_at=NOW - timedelta(days=50),
                      idempotency_key=f"fixture-seo:{slug}"))


def _outcome(db, slug, impressions, visits):
    with db.session() as s:
        s.add(ListingOutcome(product_slug=slug, version="1.0.0",
                             period_start=(TODAY - timedelta(days=28)).isoformat(),
                             period_end=(TODAY - timedelta(days=1)).isoformat(),
                             impressions=impressions, visits=visits, favourites=0,
                             source="fixture"))


def _review(db) -> Job:
    job = JobQueue(db).enqueue("orchestrator", "portfolio.review", {},
                               idempotency_key=f"t:review:{time.time_ns()}")
    assert Worker(db, "t", job_types=["portfolio.review"]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
    assert row.status == JobStatus.DONE, row.last_error
    return row


def _jobs(db, like: str) -> list[Job]:
    with db.session() as s:
        rows = list(s.scalars(select(Job).where(Job.idempotency_key.like(like))))
        for r in rows:
            s.expunge(r)
        return rows


def _seeded() -> Database:
    db = _db()
    _release(db, "coaster-seo")                         # shown, not chosen -> SEO_PROBLEM
    _outcome(db, "coaster-seo", impressions=4000, visits=4)
    _release(db, "basket-p1")                           # open P1 -> QUALITY_PROBLEM
    _outcome(db, "basket-p1", impressions=4000, visits=200)
    with db.session() as s:
        s.add(Incident(severity="P1", product_slug="basket-p1", signature="fixture-p1",
                       summary="fixture defect"))
    return db


def test_seo_and_quality_problems_become_one_keyed_job_each():
    db = _seeded()
    week = PA.week_of(TODAY)
    out = _review(db).outputs
    labels = {c["slug"]: c["label"] for c in out["classifications"]["classifications"]} \
        if isinstance(out["classifications"], dict) and "classifications" in out[
            "classifications"] else None
    acted = {a["slug"]: a for a in out["acted"]["acted"]}
    assert set(acted) == {"coaster-seo", "basket-p1"}, (out["acted"], labels)
    seo = _jobs(db, "seo-fix:%")
    assert [j.idempotency_key for j in seo] == [f"seo-fix:coaster-seo:{week}"], seo
    assert seo[0].job_type == "listing.seo" and seo[0].inputs["slug"] == "coaster-seo"
    assert seo[0].inputs["rebuild"] == f"portfolio:{week}"
    q = _jobs(db, "quality-fix:%")
    assert sorted(j.job_type for j in q) == sorted(jt for _a, jt in PA.QUALITY_CHECKS)
    assert all(j.inputs["slug"] == "basket-p1" and j.inputs["version"] == "1.0.0" for j in q)
    assert not _jobs(db, "seo-fix:basket-p1:%") and not _jobs(db, "quality-fix:%coaster%")
    with db.session() as s:
        assert s.scalar(select(AuditLog).where(AuditLog.action == PA.ACTION)) is not None


def test_a_rerun_in_the_same_week_adds_nothing():
    db = _seeded()
    _review(db)
    before = len(_jobs(db, "seo-fix:%")) + len(_jobs(db, "quality-fix:%"))
    again = _review(db).outputs["acted"]
    assert again["acted"] == [], again
    assert {s["slug"] for s in again["skipped"]} == {"coaster-seo", "basket-p1"}, again
    assert len(_jobs(db, "seo-fix:%")) + len(_jobs(db, "quality-fix:%")) == before == 5


def _ctx(db) -> JobContext:
    queue = JobQueue(db)
    job = queue.enqueue("orchestrator", "portfolio.review", {},
                        idempotency_key=f"ctx:{time.time_ns()}")
    return JobContext(job=job, db=db, queue=queue, registry=Registry(db), phase=Phase.SHADOW)


def test_retire_and_rework_raise_owner_cards_never_jobs():
    db = _db()
    _release(db, "old-throw")
    _release(db, "tired-hat")
    before = {j.id for j in _jobs(db, "%")}
    out = PA.act(_ctx(db), [Classification("old-throw", RETIRE, "no sales in a year"),
                            Classification("tired-hat", REWORK, "converts at a tenth")],
                 today=TODAY, review_id=None)
    assert {a["kind"] for a in out["acted"]} == {"retire", "rework"}, out
    week = PA.week_of(TODAY)
    with db.session() as s:
        keys = sorted(r.requirement_key for r in s.scalars(select(OwnerAction)))
    assert keys == [f"portfolio.retire:old-throw:{week}", f"portfolio.rework:tired-hat:{week}"]
    after = {j.id for j in _jobs(db, "%")} - before
    with db.session() as s:
        new = [s.get(Job, i).job_type for i in after]
    assert new == ["portfolio.review"], new        # only the context's own job; no retire job
    again = PA.act(_ctx(db), [Classification("old-throw", RETIRE, "no sales in a year")],
                   today=TODAY, review_id=None)
    assert again["acted"] == [] and again["skipped"][0]["slug"] == "old-throw", again


def test_the_weekly_cap_bounds_each_kind_and_reports_the_rest():
    db = _db()
    slugs = [f"sku-{i:02d}" for i in range(PA.WEEKLY_CAP + 2)]
    for slug in slugs:
        _release(db, slug)
    out = PA.act(_ctx(db), [Classification(s, SEO_PROBLEM, "low ctr") for s in slugs],
                 today=TODAY, review_id=None)
    assert len(out["acted"]) == PA.WEEKLY_CAP and len(out["capped"]) == 2, out
    assert len(_jobs(db, "seo-fix:%")) == PA.WEEKLY_CAP
    # The capped ones are not dropped: next week they are first in line.
    nxt = PA.act(_ctx(db), [Classification(s, SEO_PROBLEM, "low ctr") for s in slugs],
                 today=TODAY + timedelta(days=7), review_id=None)
    assert len(nxt["acted"]) == PA.WEEKLY_CAP, nxt


def test_no_certified_release_or_no_listing_history_is_skipped_by_name():
    db = _db()
    _release(db, "never-listed", seo_history=False)
    out = PA.act(_ctx(db), [Classification("never-listed", SEO_PROBLEM, "low ctr"),
                            Classification("ghost", SEO_PROBLEM, "low ctr")],
                 today=TODAY, review_id=None)
    why = {s["slug"]: s["why"] for s in out["skipped"]}
    assert "no earlier listing.seo" in why["never-listed"], why
    assert "no certified current release" in why["ghost"], why
    assert out["acted"] == [] and _jobs(db, "seo-fix:%") == []


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
