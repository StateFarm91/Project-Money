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
from brambleloop.growth.portfolio import (  # noqa: E402
    QUALITY_PROBLEM, RETIRE, REWORK, Classification,
)
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


def _listing(db, slug):
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug))
        return row.state, row.price_cad, row.etsy_listing_id


def _cards(db, prefix="portfolio."):
    with db.session() as s:
        return [(r.requirement_key, r.done) for r in s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like(f"{prefix}%")).order_by(OwnerAction.id))]


def test_the_weekly_cap_is_five():
    assert PA.WEEKLY_CAP == 5 and PA.DECIDED_QUIET_DAYS == 90


def test_quality_reverifies_and_seo_asks_the_owner_without_touching_the_live_listing():
    db = _seeded()
    with db.session() as s:                      # a later repricing of the live listing
        s.scalar(select(Listing).where(Listing.product_slug == "coaster-seo")).price_cad = 12.34
    week = PA.week_of(TODAY)
    out = _review(db).outputs["acted"]
    assert {a["slug"]: a["kind"] for a in out["acted"]} == {"coaster-seo": "seo",
                                                             "basket-p1": "quality"}, out
    q = _jobs(db, "quality-fix:%")
    assert sorted(j.job_type for j in q) == sorted(jt for _a, jt in PA.QUALITY_CHECKS)
    assert all(j.idempotency_key.endswith(f":basket-p1:{week}") for j in q)
    # Review PORTFOLIO F1/F2/F3: no listing.seo, no launch.plan, no store.publish is queued.
    with db.session() as s:
        chain = [j.job_type for j in s.scalars(select(Job).where(Job.job_type.in_((
            "listing.seo", "launch.plan", "store.publish", "marketing.schedule"))))
            if not (j.idempotency_key or "").startswith("fixture-seo:")]
    assert chain == [], chain
    assert _listing(db, "coaster-seo") == ("published", 12.34, "e-coaster-seo")
    assert _cards(db) == [("portfolio.seo:coaster-seo", False)]
    with db.session() as s:
        card = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "portfolio.seo:coaster-seo"))
        assert "Shop Manager" in card.action and card.minutes == 10
        assert card.max_cost_cad == 0.0 and card.consequence_of_delay


def test_a_rerun_restates_the_card_and_re_verifies_nothing_twice():
    db = _seeded()
    _review(db)
    before = len(_jobs(db, "quality-fix:%"))
    again = _review(db).outputs["acted"]
    assert again["acted"] == [], again
    assert len(_jobs(db, "quality-fix:%")) == before == 4
    assert _cards(db) == [("portfolio.seo:coaster-seo", False)]      # one card, restated


def _ctx(db) -> JobContext:
    queue = JobQueue(db)
    job = queue.enqueue("orchestrator", "portfolio.review", {},
                        idempotency_key=f"ctx:{time.time_ns()}")
    return JobContext(job=job, db=db, queue=queue, registry=Registry(db), phase=Phase.SHADOW)


def test_cards_are_per_sku_not_per_week_and_a_decision_is_not_re_asked_for_90_days():
    from brambleloop.ops import owner_queue

    db = _db()
    _release(db, "old-throw")
    _release(db, "tired-hat")
    labels = [Classification("old-throw", RETIRE, "no sales in a year"),
              Classification("tired-hat", REWORK, "converts at a tenth")]
    for week in range(3):                       # three weekly reviews, nobody answers
        PA.act(_ctx(db), labels, today=TODAY + timedelta(days=7 * week), review_id=None)
    assert _cards(db) == [("portfolio.retire:old-throw", False),
                          ("portfolio.rework:tired-hat", False)]
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "portfolio.retire:old-throw"))
        owner_queue.close(row, owner_queue.WITHDRAWN, "keep selling it")
    out = PA.act(_ctx(db), labels[:1], today=TODAY + timedelta(days=30), review_id=None)
    assert out["acted"] == [] and "decided" in out["skipped"][0]["why"], out
    later = PA.act(_ctx(db), labels[:1], today=TODAY + timedelta(days=95), review_id=None)
    assert [a["slug"] for a in later["acted"]] == ["old-throw"], later
    assert _cards(db).count(("portfolio.retire:old-throw", False)) == 1
    with db.session() as s:
        jobs = [j.job_type for j in s.scalars(select(Job))
                if not (j.idempotency_key or "").startswith("fixture-seo:")]
    assert set(jobs) <= {"portfolio.review"}, jobs        # cards only, never a job


def test_the_cap_rotates_so_capped_skus_go_first_next_week():
    db = _db()
    slugs = [f"sku-{i:02d}" for i in range(PA.WEEKLY_CAP + 2)]
    for slug in slugs:
        _release(db, slug)
    labels = [Classification(s, QUALITY_PROBLEM, "open P1") for s in slugs]
    w1 = PA.act(_ctx(db), labels, today=TODAY, review_id=None)
    assert [a["slug"] for a in w1["acted"]] == slugs[:5]
    assert [c["slug"] for c in w1["capped"]] == slugs[5:]
    w2 = PA.act(_ctx(db), labels, today=TODAY + timedelta(days=7), review_id=None)
    assert [a["slug"] for a in w2["acted"]][:2] == slugs[5:], w2   # the capped ones first
    seen = {a["slug"] for a in w1["acted"] + w2["acted"]}
    assert seen == set(slugs)


def test_the_cap_bounds_new_cards_and_the_capped_are_asked_the_next_week():
    from brambleloop.growth.portfolio import SEO_PROBLEM

    db = _db()
    slugs = [f"sku-{i:02d}" for i in range(PA.WEEKLY_CAP + 2)]
    for slug in slugs:
        _release(db, slug)
    labels = [Classification(s, SEO_PROBLEM, "low ctr") for s in slugs]
    w1 = PA.act(_ctx(db), labels, today=TODAY, review_id=None)
    assert len(w1["acted"]) == PA.WEEKLY_CAP and len(w1["capped"]) == 2, w1
    assert len(_cards(db)) == PA.WEEKLY_CAP
    w2 = PA.act(_ctx(db), labels, today=TODAY + timedelta(days=7), review_id=None)
    assert sorted(a["slug"] for a in w2["acted"]) == slugs[5:], w2
    assert len(w2["restated"]) == PA.WEEKLY_CAP and len(_cards(db)) == len(slugs)


def test_a_discard_the_offer_guard_withheld_is_never_acted_on():
    db = _db()
    _release(db, "slow-cushion")                  # live 60 days in the fixture
    with db.session() as s:
        s.scalar(select(Listing).where(Listing.product_slug == "slow-cushion")).created_at = (
            NOW - timedelta(days=200))
    with db.session() as s:
        s.add(ListingOutcome(product_slug="slow-cushion", version="1.0.0",
                             period_start=(TODAY - timedelta(days=28)).isoformat(),
                             period_end=(TODAY - timedelta(days=1)).isoformat(),
                             impressions=4000, visits=200, favourites=40, source="fixture"))
    out = _review(db).outputs
    assert any(g["slug"] == "slow-cushion" and g["label"] == REWORK and not g["may_retire"]
               for g in out["offer_guard"]), out["offer_guard"]
    assert out["acted"]["acted"] == [] and _cards(db) == [], out["acted"]


def test_no_certified_release_is_skipped_by_name():
    db = _db()
    out = PA.act(_ctx(db), [Classification("ghost", QUALITY_PROBLEM, "p1")],
                 today=TODAY, review_id=None)
    assert out["acted"] == [] and "no certified current release" in out["skipped"][0]["why"]


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
