"""W4-INTELREC G5: Winner Amplification is delegated, bounded and its follow-ons measured.

OFFLINE (fixtures; not production evidence). A family with orders at or above the floor gets
one original follow-on through the ordinary funnel (radar.score -> pre-engineering gate);
below the floor nothing happens (UNMEASURED); follow-on orders are counted only for members
certified after the decision; two settled attempts that add no member hold the family.
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (Customer, Job, JobStatus, Order, PatternVersion,  # noqa: E402
                                     Phase, Product)
from brambleloop.creative import family_engine as fe  # noqa: E402
from brambleloop.queue.durable import DuplicateJob, JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='amp-')}/a.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _certify(db, slug, rows=1):
    with db.session() as s:
        p = Product(slug=slug, title=slug)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1", certified=True,
                             cir_json={"construction": "flat", "components": [
                                 {"name": "a", "rows": [{"n": i} for i in range(rows)]}]}))


def _orders(db, slug, n, start=0):
    with db.session() as s:
        c = s.scalar(select(Customer)) or Customer(customer_ref="fixture-buyer")
        s.add(c)
        s.flush()
        for i in range(n):
            s.add(Order(customer_id=c.id, external_ref=f"{slug}-{start + i}", product_slug=slug,
                        price_cad=9.0))


def _enq(db):
    q = JobQueue(db)

    def enqueue(agent, job_type, inputs, *, idempotency_key=None, **kw):
        try:
            return q.enqueue(agent, job_type, inputs, idempotency_key=idempotency_key, **kw)
        except DuplicateJob:
            return None
    return enqueue


def test_below_the_floor_nothing_is_amplified():
    db = _db()
    _certify(db, "nordic-forest-mosaic-throw")
    _orders(db, "nordic-forest-mosaic-throw", fe.AMPLIFY_MIN_ORDERS - 1)
    out = fe.amplify(db, fe.family_report(db), enqueue=_enq(db))
    assert out["decisions"] == []


def test_a_proven_family_gets_one_original_follow_on_and_is_measured():
    db = _db()
    _certify(db, "nordic-forest-mosaic-throw")
    _orders(db, "nordic-forest-mosaic-throw", fe.AMPLIFY_MIN_ORDERS)
    # through the real job system: the family engine handler delegates the follow-on
    job = JobQueue(db).enqueue("creative_director", "creative.family_engine", {},
                               idempotency_key="fe-1")
    Worker(db, "amp", phase=Phase.SHADOW, job_types=["creative.family_engine"]).run_once()
    with db.session() as s:
        assert s.get(Job, job.id).status == JobStatus.DONE, s.get(Job, job.id).last_error
        follow = s.scalar(select(Job).where(Job.job_type == "radar.score"))
        assert follow is not None and follow.inputs["amplify_family"] == "nordic-forest"
        follow_id = follow.id
    # #22: the best seller was investigated by commerce.replication.study -- 5 orders is
    # below its winner floor, so it says so in its own words and names no cause.
    inv = fe._amp_state(db, "nordic-forest")["investigation"]
    assert inv["credible"] is False and "not a credible winner" in inv["reasons"][0]
    # idempotent: the open attempt is not duplicated
    assert fe.amplify(db, fe.family_report(db), enqueue=_enq(db))["decisions"] == []
    # the follow-on member is certified and sells: measured as a follow-on, not inferred
    with db.session() as s:
        j = s.get(Job, follow_id)
        j.status = JobStatus.DONE
    _certify(db, "nordic-forest-stocking", rows=3)
    _orders(db, "nordic-forest-stocking", 2, start=100)
    fe.amplify(db, fe.family_report(db), enqueue=_enq(db))
    st = fe._amp_state(db, "nordic-forest")
    assert st["follow_on"]["members"] == ["nordic-forest-stocking"]
    assert st["follow_on"]["orders"] == 2
    assert st.get("failed_attempts", 0) == 0


def test_a_credible_winner_gets_a_bounded_study_and_the_follow_on_holds_its_causes():
    from datetime import datetime, timedelta, timezone

    from brambleloop.commerce import replication

    db = _db()
    _certify(db, "nordic-forest-mosaic-throw")
    for slug in ("cloudline-baby-blanket", "autumn-oak-mosaic-throw", "nordic-forest-stocking"):
        _certify(db, slug, rows=2)
        _orders(db, slug, 3, start=500 + len(slug))
    _orders(db, "nordic-forest-mosaic-throw", replication.MIN_ORDERS)
    # Review N-8: weeks live count from first certification, not from the first order.
    with db.session() as s:
        for pv in s.scalars(select(PatternVersion).join(
                Product, PatternVersion.product_id == Product.id).where(
                Product.slug == "nordic-forest-mosaic-throw")):
            pv.created_at = datetime.now(timezone.utc) - timedelta(
                weeks=replication.MIN_WEEKS + 1)
    fe.amplify(db, fe.family_report(db), enqueue=_enq(db))
    inv = fe._amp_state(db, "nordic-forest")["investigation"]
    assert inv["credible"] is True and inv["winner"] == "nordic-forest-mosaic-throw"
    assert inv["ends"]                                     # the study is bounded
    with db.session() as s:
        job = s.scalar(select(Job).where(Job.job_type.in_(("radar.score",
                                                            "creative.tournament"))))
        assert job.inputs["amplify_holds"] == [e["dimension"] for e in inv["explanations"]][:3]


def test_two_attempts_without_a_new_member_hold_the_family():
    db = _db()
    _certify(db, "nordic-forest-mosaic-throw")
    _orders(db, "nordic-forest-mosaic-throw", fe.AMPLIFY_MIN_ORDERS)
    for n in range(fe.AMPLIFY_MAX_ATTEMPTS):
        fe.amplify(db, fe.family_report(db), enqueue=_enq(db))
        with db.session() as s:
            for j in s.scalars(select(Job).where(Job.status == JobStatus.PENDING)):
                # MEASURED and not promoted: a real failed attempt (review H-1/L-5)
                j.status = JobStatus.DONE
                # two independent measurements (different scores, N-3)
                j.outputs = {"slug": j.inputs.get("slug"), "score": 0.31 - 0.02 * n,
                             "promoted": False}
    out = fe.amplify(db, fe.family_report(db), enqueue=_enq(db))
    st = fe._amp_state(db, "nordic-forest")
    assert out["decisions"] == [] and st["held"] and st["failed_attempts"] == 2


def test_a_refused_or_dead_follow_on_is_not_a_failed_attempt():
    """Review L-5: a refusal, park or dead letter measured nothing, so it is not counted."""
    db = _db()
    _certify(db, "nordic-forest-mosaic-throw")
    _orders(db, "nordic-forest-mosaic-throw", fe.AMPLIFY_MIN_ORDERS)
    for status, out in ((JobStatus.DEAD, None),
                        (JobStatus.DONE, {"slug": "x", "promoted": False,
                                          "reason": "not in the pool"}),
                        (JobStatus.CANCELLED, None)):
        fe.amplify(db, fe.family_report(db), enqueue=_enq(db))
        with db.session() as s:
            for j in s.scalars(select(Job).where(Job.status == JobStatus.PENDING)):
                j.status, j.outputs = status, out
    fe.amplify(db, fe.family_report(db), enqueue=_enq(db))
    st = fe._amp_state(db, "nordic-forest")
    assert st.get("failed_attempts", 0) == 0 and not st.get("held"), st
    assert st["last_outcome"] == "not_attempted"


def test_a_promoted_follow_on_is_progress_not_failure():
    db = _db()
    _certify(db, "nordic-forest-mosaic-throw")
    _orders(db, "nordic-forest-mosaic-throw", fe.AMPLIFY_MIN_ORDERS)
    fe.amplify(db, fe.family_report(db), enqueue=_enq(db))
    with db.session() as s:
        j = s.scalar(select(Job).where(Job.job_type == "radar.score"))
        j.status = JobStatus.DONE
        j.outputs = {"slug": j.inputs["slug"], "score": 0.9, "promoted": True}
    fe.amplify(db, fe.family_report(db), enqueue=_enq(db))
    st = fe._amp_state(db, "nordic-forest")
    assert st["last_outcome"] == "progressed" and st.get("failed_attempts", 0) == 0


def test_no_declared_member_records_needs_original_design_and_queues_no_paid_job():
    """Review M-2: this handler is CA$0 delegable work; an original follow-on design is paid
    creative work, so it is recorded and surfaced, never queued from here."""
    db = _db()
    queued = []

    def enqueue(agent, job_type, inputs, **kw):
        queued.append(job_type)
        return None
    rep = {"families": [{"family": "fixture-family", "amplification": {"orders": 9},
                         "members": [{"slug": "fixture-a", "orders": 9}],
                         "next_members": [], "orders": 9}]}
    out = fe.amplify(db, rep, enqueue=enqueue)
    assert queued == [], queued
    assert out["decisions"] == [{"family": "fixture-family", "job_id": None,
                                 "decision": "needs_original_design"}]
    assert fe._amp_state(db, "fixture-family")["needs_original_design"]



def test_a_promoted_member_is_not_rescored_until_its_outcome_is_known():
    """Review 720b291 N-2: three runs after a promotion queue nothing more; a promotion that
    has not certified within AMPLIFY_PROMOTION_DAYS counts as a failed attempt."""
    from datetime import date, timedelta

    db = _db()
    _certify(db, "nordic-forest-mosaic-throw")
    _orders(db, "nordic-forest-mosaic-throw", fe.AMPLIFY_MIN_ORDERS)
    d0 = date(2026, 10, 27)
    fe.amplify(db, fe.family_report(db), enqueue=_enq(db), today=d0)
    with db.session() as s:
        j = s.scalar(select(Job).where(Job.job_type == "radar.score"))
        j.status = JobStatus.DONE
        j.outputs = {"slug": j.inputs["slug"], "score": 0.9, "promoted": True}
    for k in range(1, 4):
        fe.amplify(db, fe.family_report(db), enqueue=_enq(db), today=d0 + timedelta(days=k))
    with db.session() as s:
        assert s.query(Job).filter(Job.job_type == "radar.score").count() == 1
    st = fe._amp_state(db, "nordic-forest")
    assert st["promoted"]["seed"] and st.get("failed_attempts", 0) == 0
    fe.amplify(db, fe.family_report(db), enqueue=_enq(db),
               today=d0 + timedelta(days=1 + fe.AMPLIFY_PROMOTION_DAYS))  # promoted on d0+1
    st = fe._amp_state(db, "nordic-forest")
    assert st["failed_attempts"] == 1 and not st.get("promoted"), st
    # and the study window was kept from the first attempt (N-8)
    assert st["study_starts"] == d0.isoformat()


def test_an_identical_rescore_is_a_repeat_not_a_second_failure():
    """Review 720b291 N-3 in amplification."""
    from datetime import date, timedelta

    db = _db()
    _certify(db, "nordic-forest-mosaic-throw")
    _orders(db, "nordic-forest-mosaic-throw", fe.AMPLIFY_MIN_ORDERS)
    d = date(2026, 10, 27)
    for _ in range(2):
        fe.amplify(db, fe.family_report(db), enqueue=_enq(db), today=d)
        with db.session() as s:
            for j in s.scalars(select(Job).where(Job.status == JobStatus.PENDING)):
                j.status = JobStatus.DONE
                j.outputs = {"slug": j.inputs.get("slug"), "score": 0.31, "promoted": False,
                             "evidence": {"discount": 1.0}}
    fe.amplify(db, fe.family_report(db), enqueue=_enq(db), today=d)
    st = fe._amp_state(db, "nordic-forest")
    assert st["failed_attempts"] == 1 and st["last_outcome"] == "repeat_measurement", st
    assert not st.get("held")


def test_n8_weeks_live_count_from_certification_not_the_first_order():
    from datetime import date, datetime, timedelta, timezone

    db = _db()
    _certify(db, "nordic-forest-mosaic-throw")
    _orders(db, "nordic-forest-mosaic-throw", 3)
    with db.session() as s:
        for o in s.scalars(select(Order)):
            o.at = datetime.now(timezone.utc) - timedelta(weeks=40)   # an old first order
        pv = s.scalar(select(PatternVersion))
        today = date.today()
        pv.created_at = datetime(today.year, today.month, today.day,
                                 tzinfo=timezone.utc) - timedelta(weeks=3)
    sku = next(k for k in fe._skus(db, today) if k.slug == "nordic-forest-mosaic-throw")
    assert sku.weeks_live == 3, sku.weeks_live


def test_n8_a_follow_on_that_is_not_adjacent_is_parked_not_queued():
    from brambleloop.radar.opportunity import POOL

    seed = next(p.slug for p in POOL if p.family)
    clone = fe.adjacency({"winner": seed, "credible": False}, seed)
    assert clone["adjacent"] is False and any("changes nothing" in r for r in clone["reasons"])
    unknown = fe.adjacency({"winner": "no-such-seed"}, "also-no-such-seed")
    assert unknown["adjacent"] is None                     # UNKNOWN, never passed

    db = _db()
    _certify(db, "nordic-forest-mosaic-throw")
    _orders(db, "nordic-forest-mosaic-throw", fe.AMPLIFY_MIN_ORDERS)
    real = fe.adjacency
    fe.adjacency = lambda inv, nxt: {"adjacent": False, "reasons": ["palette only"]}
    try:
        out = fe.amplify(db, fe.family_report(db), enqueue=_enq(db))
    finally:
        fe.adjacency = real
    assert [d["decision"] for d in out["decisions"]] == ["not_adjacent"]
    with db.session() as s:
        assert s.scalar(select(Job).where(Job.job_type == "radar.score")) is None
    assert "not an adjacent experiment" in fe._amp_state(db, "nordic-forest")["how"]


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
