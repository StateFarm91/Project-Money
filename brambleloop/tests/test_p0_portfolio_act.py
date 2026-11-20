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
sys.path.insert(0, str(ROOT / "tests"))
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


def _review(db, as_of=None) -> Job:
    job = JobQueue(db).enqueue("orchestrator", "portfolio.review",
                               {"as_of": as_of.isoformat()} if as_of else {},
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


def test_quality_reverifies_and_seo_queues_one_bounded_fix_only_rebuild():
    db = _seeded()
    week = PA.week_of(TODAY)
    out = _review(db).outputs["acted"]
    assert {a["slug"]: a["kind"] for a in out["acted"]} == {"coaster-seo": "seo",
                                                             "basket-p1": "quality"}, out
    q = _jobs(db, "quality-fix:%")
    assert sorted(j.job_type for j in q) == sorted(jt for _a, jt in PA.QUALITY_CHECKS)
    assert all(j.idempotency_key.endswith(f":basket-p1:{week}") for j in q)
    seo = _jobs(db, "seo-fix:%")
    assert [(j.job_type, j.idempotency_key) for j in seo] == [
        ("listing.seo", f"seo-fix:coaster-seo:{week}")], seo
    i = seo[0].inputs
    # Review ee5dbeee token: chain_key keeps 12 characters of a token, so the token is
    # `pf2026W45`, not `portfolio:2026-W45` (which truncated to `portfolio:20` every week).
    assert i["fix_only"] is True and i["rebuild"] == PA.rebuild_token(week), i
    assert i["rebuild"] == "pf" + week.replace("-", "") and len(i["rebuild"]) <= 12, i
    from brambleloop.runtime.release import chain_key

    nxt = PA.week_of(TODAY + timedelta(days=7))
    assert (chain_key("launch", "x", "1", "r", PA.rebuild_token(week))
            != chain_key("launch", "x", "1", "r", PA.rebuild_token(nxt)))
    assert i["version"] == "1.0.0" and i["release"], i
    # No portfolio card for SEO any more: the fix_only handler owns the live-listing card.
    assert _cards(db) == []


_E2E: dict = {}


def _e2e() -> dict:
    """One real certified chain (Main's fix_only fixture), shared by the two e2e tests: a
    live, repriced listing with SEO_PROBLEM exposure, portfolio.review, the queue drained."""
    if _E2E:
        return _E2E
    import test_w6_fix_only_rebuild as FO

    st = FO.chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    FO._set_listing(db, slug, version, state="published", etsy_listing_id="7654321",
                    price_cad=12.34)
    with db.session() as s:
        s.add(ListingOutcome(product_slug=slug, version=version,
                             period_start=(TODAY - timedelta(days=28)).isoformat(),
                             period_end=(TODAY - timedelta(days=1)).isoformat(),
                             impressions=4000, visits=4, favourites=0, source="fixture"))
    before = FO._listing(db, slug, version)
    out = _review(db).outputs["acted"]
    FO._drain(db, name="pact-e2e")
    _E2E.update(FO=FO, db=db, slug=slug, version=version, before=before, out=out)
    return _E2E


def test_the_fix_only_seo_rebuild_never_touches_a_live_listing_or_reaches_publish():
    e = _e2e()
    FO, db, slug, version, before, out = (e[k] for k in ("FO", "db", "slug", "version",
                                                         "before", "out"))
    assert any(a["slug"] == slug and a["kind"] == "seo" for a in out["acted"]), out
    token = PA.rebuild_token(PA.week_of(TODAY))
    ran = FO._jobs(db, token)
    assert ("listing.seo", JobStatus.DONE) in ran, ran
    assert not [t for t, _s in ran if t in FO.DOWNSTREAM], ran
    assert FO._listing(db, slug, version) == before            # state, price, copy, Etsy id
    with db.session() as s:
        card = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == f"listing.live_update:{slug}@{version}"))
    assert card is not None and not card.done, "the owner was not asked to apply the copy"


def test_a_declined_live_update_card_is_not_rebuilt_and_re_asked_the_next_week():
    """Review ee5dbeee N1 on the real chain: the owner declines the `listing.live_update`
    card, and the next ISO week's review queues no new seo-fix and raises no new card."""
    from brambleloop.ops import owner_queue

    e = _e2e()
    FO, db, slug, version = e["FO"], e["db"], e["slug"], e["version"]
    key = PA.live_update_key(slug, version)
    with db.session() as s:
        card = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key,
                                                  OwnerAction.done == False))  # noqa: E712
        assert card is not None, "the first review raised no live_update card"
        owner_queue.close(card, owner_queue.WITHDRAWN, "keep the current copy")
    nxt = TODAY + timedelta(days=7)
    week2 = PA.week_of(nxt)
    out = _review(db, as_of=nxt).outputs["acted"]
    assert out["week"] == week2 and not [a for a in out["acted"] if a["slug"] == slug], out
    why = [k["why"] for k in out["skipped"] if k["slug"] == slug and k["kind"] == "seo"]
    assert len(why) == 1 and "listing.live_update" in why[0] and "decided" in why[0], out
    assert _jobs(db, f"seo-fix:{slug}:{week2}") == []
    FO._drain(db, name="pact-e2e-w2")
    assert FO._jobs(db, PA.rebuild_token(week2)) == []
    with db.session() as s:
        cards = [r.done for r in s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == key))]
    assert cards == [True], cards                                # no new card


def test_an_open_live_update_card_is_not_rebuilt_over():
    from brambleloop.growth.portfolio import SEO_PROBLEM

    db = _db()
    _release(db, "coaster-seo")
    with db.session() as s:
        s.add(OwnerAction(requirement_key=PA.live_update_key("coaster-seo", "1.0.0"),
                          action="compare and apply", max_cost_cad=0.0, minutes=10))
    nxt = TODAY + timedelta(days=7)
    out = PA.act(_ctx(db), [Classification("coaster-seo", SEO_PROBLEM, "shown")],
                 today=nxt, review_id=None)
    assert out["acted"] == [] and "is open" in out["skipped"][0]["why"], out
    assert _jobs(db, "seo-fix:%") == []
    # Past the quiet period a decided card no longer holds the SKU back.
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == PA.live_update_key("coaster-seo", "1.0.0")))
        row.state, row.done = "withdrawn", True
        row.state_at = NOW - timedelta(days=PA.DECIDED_QUIET_DAYS + 1)
    later = PA.act(_ctx(db), [Classification("coaster-seo", SEO_PROBLEM, "shown")],
                   today=TODAY, review_id=None)
    assert [a["slug"] for a in later["acted"]] == ["coaster-seo"], later


def test_seo_without_an_earlier_listing_seo_is_skipped_and_never_invented():
    from brambleloop.growth.portfolio import SEO_PROBLEM

    db = _db()
    _release(db, "no-history", seo_history=False)
    out = PA.act(_ctx(db), [Classification("no-history", SEO_PROBLEM, "shown")],
                 today=TODAY, review_id=None)
    assert out["acted"] == [], out
    assert [(k["slug"], k["kind"]) for k in out["skipped"]] == [("no-history", "seo")], out
    assert "no earlier listing.seo for no-history@1.0.0" in out["skipped"][0]["why"], out
    assert _jobs(db, "seo-fix:%") == []


def test_seo_without_a_certified_release_is_skipped_by_name():
    from brambleloop.growth.portfolio import SEO_PROBLEM

    db = _db()
    out = PA.act(_ctx(db), [Classification("ghost", SEO_PROBLEM, "shown")],
                 today=TODAY, review_id=None)
    assert out["acted"] == [] and out["skipped"] == [
        {"slug": "ghost", "kind": "seo", "why": "no certified current release to rebuild"}], out
    assert _jobs(db, "seo-fix:%") == []


def test_a_rerun_in_the_same_week_rebuilds_and_re_verifies_nothing_twice():
    db = _seeded()
    _review(db)
    before = len(_jobs(db, "quality-fix:%")), len(_jobs(db, "seo-fix:%"))
    again = _review(db).outputs["acted"]
    assert again["acted"] == [], again
    assert (len(_jobs(db, "quality-fix:%")), len(_jobs(db, "seo-fix:%"))) == before == (4, 1)


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
    with db.session() as s:          # review ee5dbeee N3: every card states its terms
        cards = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like("portfolio.%"))))
        assert len(cards) == 2, cards
        for r in cards:
            assert r.max_cost_cad == 0.0 and r.minutes == 10, (r.max_cost_cad, r.minutes)
            assert "stays as it is" in (r.consequence_of_delay or ""), r.consequence_of_delay
            assert "Close this card as withdrawn" in r.action and "@1.0.0" in r.action, r.action
            assert (r.blocks or "").endswith(r.requirement_key.split(":", 1)[1]), r.blocks
    # The stored 0.0 could be the column default, so the card itself must state its ceiling.
    for kind, c in ((PA.RETIRE_CARD, labels[0]), (PA.REWORK_CARD, labels[1])):
        f = PA._card(kind, c, {"version": "1.0.0"}, TODAY)
        assert set(f) == {"action", "reason", "max_cost_cad", "minutes",
                          "consequence_of_delay", "blocks"}, f
        assert f["max_cost_cad"] == 0.0 and f["minutes"] == 10, f
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
    db = _db()
    slugs = [f"sku-{i:02d}" for i in range(PA.WEEKLY_CAP + 2)]
    for slug in slugs:
        _release(db, slug)
    labels = [Classification(s, RETIRE, "no sales in a year") for s in slugs]
    w1 = PA.act(_ctx(db), labels, today=TODAY, review_id=None)
    assert len(w1["acted"]) == PA.WEEKLY_CAP and len(w1["capped"]) == 2, w1
    assert len(_cards(db)) == PA.WEEKLY_CAP
    w2 = PA.act(_ctx(db), labels, today=TODAY + timedelta(days=7), review_id=None)
    assert sorted(a["slug"] for a in w2["acted"]) == slugs[5:], w2
    assert len(w2["restated"]) == PA.WEEKLY_CAP and len(_cards(db)) == len(slugs)


def test_the_cap_bounds_fix_only_seo_rebuilds_and_the_capped_go_first_next_week():
    from brambleloop.growth.portfolio import SEO_PROBLEM

    db = _db()
    slugs = [f"seo-{i:02d}" for i in range(PA.WEEKLY_CAP + 2)]
    for slug in slugs:
        _release(db, slug)
    labels = [Classification(s, SEO_PROBLEM, "shown, not chosen") for s in slugs]
    w1 = PA.act(_ctx(db), labels, today=TODAY, review_id=None)
    assert len(w1["acted"]) == PA.WEEKLY_CAP and len(w1["capped"]) == 2, w1
    assert len(_jobs(db, "seo-fix:%")) == PA.WEEKLY_CAP
    w2 = PA.act(_ctx(db), labels, today=TODAY + timedelta(days=7), review_id=None)
    assert [a["slug"] for a in w2["acted"]][:2] == sorted(c["slug"] for c in w1["capped"]), w2


def test_the_cap_counts_earlier_runs_in_the_same_week():
    """Review ee5dbeee N4: a second review in the same ISO week with other SKUs never takes
    the week past WEEKLY_CAP, for jobs and for cards."""
    from brambleloop.growth.portfolio import SEO_PROBLEM

    db = _db()
    seo = [f"seo-{i:02d}" for i in range(PA.WEEKLY_CAP + 2)]
    ret = [f"ret-{i:02d}" for i in range(PA.WEEKLY_CAP + 2)]
    for slug in seo + ret:
        _release(db, slug)
    first = [Classification(s, SEO_PROBLEM, "shown") for s in seo[:3]] + [
        Classification(s, RETIRE, "no sales") for s in ret[:3]]
    second = [Classification(s, SEO_PROBLEM, "shown") for s in seo[3:]] + [
        Classification(s, RETIRE, "no sales") for s in ret[3:]]
    w1 = PA.act(_ctx(db), first, today=TODAY, review_id=None)
    assert len(w1["acted"]) == 6, w1
    w2 = PA.act(_ctx(db), second, today=TODAY, review_id=None)
    assert sorted((a["kind"], a["slug"]) for a in w2["acted"]) == [
        ("retire", "ret-03"), ("retire", "ret-04"), ("seo", "seo-03"), ("seo", "seo-04")], w2
    assert len(w2["capped"]) == 4, w2
    assert len(_jobs(db, f"seo-fix:%:{PA.week_of(TODAY)}")) == PA.WEEKLY_CAP
    assert len(_cards(db)) == PA.WEEKLY_CAP


def test_a_failure_while_acting_never_fails_the_committed_review():
    """Review ee5dbeee N5: the PortfolioReview row is committed before act(); an exception in
    act() is audited and reported, and the review job still succeeds."""
    from brambleloop.core.models import PortfolioReview

    db = _seeded()
    real = PA.act

    def boom(*_a, **_k):
        raise RuntimeError("fixture failure")

    PA.act = boom
    try:
        out = _review(db).outputs
    finally:
        PA.act = real
    assert "RuntimeError: fixture failure" in out["acted"]["error"], out["acted"]
    with db.session() as s:
        assert len(list(s.scalars(select(PortfolioReview)))) == 1
        failed = [a.detail for a in s.scalars(select(AuditLog).where(
            AuditLog.action == PA.ACT_FAILED))]
        assert len(failed) == 1 and "fixture failure" in failed[0]["error"], failed
        assert s.scalar(select(AuditLog).where(AuditLog.action == "portfolio.reviewed"))


def test_the_review_date_is_the_utc_date():
    """Review ee5dbeee N6: week keys come from the UTC calendar, not the host's. The host
    zone is moved to one whose date differs from UTC's right now (UTC+14 from 10:00 UTC,
    UTC-11 before 11:00 UTC), so a host-local date fails on any host."""
    import os

    db = _db()
    zone = "Pacific/Kiritimati" if datetime.now(timezone.utc).hour >= 10 else "Pacific/Pago_Pago"
    old = os.environ.get("TZ")
    os.environ["TZ"] = zone
    time.tzset()
    try:
        out = _review(db).outputs
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()
    assert out["as_of"] == datetime.now(timezone.utc).date().isoformat(), out["as_of"]


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
