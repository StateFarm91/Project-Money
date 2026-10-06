"""Codex CB2-G02: the customer_incident and truth_defect bands are protected, declared once.

`growth.steer` moved a pending chain.rebuild from 25 by a fast-lane credit of -20 to 5, ahead of
a waiting support reply at 10, and `JobQueue.claim` then claimed the rebuild first. The
invariant now lives in `swarm.orchestrate` (PROTECTED_KINDS, claim_tier, steer_floor) and is
enforced at both ends: steering never carries a job into or across a protected band, and the
claim orders protected job types first, so neither steering, an explicit priority nor aging
lets ordinary work be claimed while runnable protected work waits.

Every job and reading here is a TEST FIXTURE in a throwaway database.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_protected_bands.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
import threading
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job, OperatingReading, utcnow  # noqa: E402
from brambleloop.queue import durable  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402
from brambleloop.swarm.orchestrate import BAND_BY_KIND  # noqa: E402

CUSTOMER = BAND_BY_KIND["customer_incident"]
TRUTH = BAND_BY_KIND["truth_defect"]


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='bands_')}/b.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def test_the_protected_bands_are_declared_and_mapped():
    assert orc.PROTECTED_KINDS == ("customer_incident", "truth_defect")
    assert orc.PROTECTED_CEILING == TRUTH
    types = orc.protected_job_types()
    assert "support.reply" in types["customer_incident"]
    assert "chain.rebuild" in types["truth_defect"]
    assert orc.claim_tier("support.reply") == 0
    assert orc.claim_tier("chain.rebuild") == 1
    assert orc.claim_tier("listing.draft") == orc.ORDINARY_TIER
    assert orc.claim_tier("never.mapped") == orc.ORDINARY_TIER


def test_steering_never_moves_a_job_into_or_across_a_protected_band():
    sp = orc.steered_priority
    # The Codex case: a job at 25 with the fast-lane credit of -20 stops behind truth_defect.
    assert sp("chain.rebuild", 25, -20) == TRUTH + 1
    assert sp("listing.draft", 25, -20) == TRUTH + 1
    assert sp("listing.draft", 70, -10) == 60          # ordinary moves are unchanged
    assert sp("listing.draft", 40, +10) == 50          # and so are moves down
    # A protected job inside its band stays inside it, never above the band before it.
    assert sp("chain.rebuild", TRUTH, -20) == CUSTOMER + 1
    assert sp("support.reply", CUSTOMER, -20) == CUSTOMER - orc.MAX_WITHIN_BAND
    # An ordinary job already placed in a protected number (explicit enqueue) is not pushed
    # further up by steering.
    assert sp("listing.draft", 5, -20) == 5
    for jt in ("chain.rebuild", "support.reply", "listing.draft", "x.unmapped"):
        for start in (0, 5, 10, 11, 15, 16, 21, 25, 40, 95):
            for delta in (-20, -10, 10):
                after = sp(jt, start, delta)
                if start > TRUTH:
                    assert after > TRUTH, (jt, start, delta, after)
                if CUSTOMER < start <= TRUTH and jt != "support.reply":
                    # only a customer-incident job may be steered into the customer band
                    assert after > CUSTOMER, (jt, start, delta, after)
                assert after <= max(start, start + delta)


def test_a_fast_lane_steer_does_not_put_a_rebuild_ahead_of_a_waiting_customer():
    """The Codex reproduction, through `growth_ops.steer` and `JobQueue.claim`."""
    from brambleloop.runtime import growth_ops
    from brambleloop.seasonal import daily

    db = _db()
    slug, today = "nordic-forest-mosaic-throw", date.today()
    with db.session() as s:
        s.add(OperatingReading(kind=daily.KIND, period_key=today.isoformat(),
                               payload={"fast_lane": {"admitted": [slug]}}))
    q = JobQueue(db)
    job = q.enqueue("listing", "chain.rebuild", {"slug": slug}, idempotency_key="band-rebuild",
                    priority=BAND_BY_KIND["seasonal_deadline"])
    customer = q.enqueue("customer_support", "support.reply", {"case_id": 999},
                         idempotency_key="band-customer", priority=CUSTOMER)
    out = growth_ops.steer(db, today=today)
    with db.session() as s:
        after = s.get(Job, job.id).priority
    assert after > TRUTH, (after, out["jobs_moved"])
    moved = next(m for m in out["jobs_moved"] if m["job_id"] == job.id)
    assert moved["requested_delta"] == -20 and moved["delta"] == after - 25
    assert moved["clamped_at"] == TRUTH + 1
    claimed = q.claim("verifier")
    assert claimed.id == customer.id, (claimed.job_type, claimed.priority)
    # A second steer does not move it further (already steered, and at the floor anyway).
    growth_ops.steer(db, today=today)
    with db.session() as s:
        assert s.get(Job, job.id).priority == after


def test_claim_orders_protected_types_first_whatever_the_stored_priority():
    db = _db()
    q = JobQueue(db)
    ordinary = q.enqueue("listing", "listing.draft", {}, priority=-50)     # explicit, very low
    truth = q.enqueue("listing", "chain.rebuild", {}, priority=40)
    customer = q.enqueue("support", "support.reply", {}, priority=60)
    order = [q.claim("w").id for _ in range(3)]
    assert order == [customer.id, truth.id, ordinary.id], order


def test_aging_does_not_let_ordinary_work_overtake_a_protected_band():
    db = _db()
    q = JobQueue(db)
    ancient = q.enqueue("listing", "listing.draft", {}, priority=40,
                        run_after=utcnow() - timedelta(days=365))
    old_truth = q.enqueue("listing", "chain.rebuild", {}, priority=TRUTH,
                          run_after=utcnow() - timedelta(days=365))
    fresh_customer = q.enqueue("support", "support.reply", {}, priority=CUSTOMER)
    fresh_truth = q.enqueue("listing", "ops.health", {}, priority=TRUTH)
    order = [q.claim("w").id for _ in range(4)]
    # Customer first however long the others waited; inside the truth tier aging still
    # works (the year-old rebuild before the fresh check); ordinary work last.
    assert order == [fresh_customer.id, old_truth.id, fresh_truth.id, ancient.id], order
    # Aging still works between ordinary jobs (C-15 is intact inside a tier).
    db = _db()
    q = JobQueue(db)
    low = q.enqueue("a", "t", priority=200,
                    run_after=utcnow() - timedelta(seconds=192 * durable.AGING_STEP_SECONDS))
    q.enqueue("a", "t", priority=10)
    assert q.claim("w").id == low.id


def test_concurrent_workers_claim_every_protected_job_before_any_ordinary_one():
    db = _db()
    q = JobQueue(db)
    ordinary = {q.enqueue("listing", "listing.draft", {"i": i}, priority=0).id
                for i in range(12)}
    protected = {q.enqueue("support", "support.reply", {"i": i}, priority=60).id
                 for i in range(6)}
    protected |= {q.enqueue("listing", "chain.rebuild", {"i": i}, priority=90).id
                  for i in range(6)}
    claims: list[tuple[float, int]] = []
    lock = threading.Lock()
    barrier = threading.Barrier(4)

    def run(k):
        mine = JobQueue(db)
        barrier.wait()
        while True:
            job = mine.claim(f"w{k}")
            if job is None:
                return
            with lock:
                claims.append(job.id)

    threads = [threading.Thread(target=run, args=(k,)) for k in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert sorted(claims) == sorted(ordinary | protected), "a job was lost or claimed twice"
    first = claims[:len(protected)]
    assert set(first) == protected, (
        "an ordinary job was claimed while protected work was still waiting")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
