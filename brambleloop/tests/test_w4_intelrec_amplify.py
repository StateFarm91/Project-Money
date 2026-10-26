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


def test_two_attempts_without_a_new_member_hold_the_family():
    db = _db()
    _certify(db, "nordic-forest-mosaic-throw")
    _orders(db, "nordic-forest-mosaic-throw", fe.AMPLIFY_MIN_ORDERS)
    for _ in range(fe.AMPLIFY_MAX_ATTEMPTS):
        fe.amplify(db, fe.family_report(db), enqueue=_enq(db))
        with db.session() as s:
            for j in s.scalars(select(Job).where(Job.status == JobStatus.PENDING)):
                j.status = JobStatus.DONE
    out = fe.amplify(db, fe.family_report(db), enqueue=_enq(db))
    st = fe._amp_state(db, "nordic-forest")
    assert out["decisions"] == [] and st["held"] and st["failed_attempts"] == 2


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
