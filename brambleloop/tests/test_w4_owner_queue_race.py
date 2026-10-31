"""INTEG8: two launch-readiness passes at once must not queue the same owner request twice.

`handle_launch_readiness` reads the open owner actions, then inserts a row for every request
with no open row. Two passes running together (the hourly cadence and an operator-enqueued
pass on two worker threads) each read "absent" before either inserted. Each then inserted,
so the owner saw one decision twice: `test_deploy` showed 40 -> 41 under SQLite lock
contention. The check and the insert are now one serialised transaction
(`release._serialise_owner_queue`: an advisory transaction lock on Postgres, BEGIN IMMEDIATE on
SQLite).

The test forces the interleaving the race needs. Each pass waits at a barrier right after its
read, so with no serialisation both passes read before either writes. With serialisation the
second pass cannot read until the first has committed, so the barrier times out and the second
pass reads the first pass's rows.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_owner_queue_race.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
import threading
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import OwnerAction, Phase  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers the handlers
from brambleloop.runtime import release  # noqa: E402
from brambleloop.runtime.worker import JobContext, handlers  # noqa: E402


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/race.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _two_concurrent_passes(db: Database) -> list[BaseException]:
    barrier = threading.Barrier(2, timeout=3)
    real = release._open_owner_actions
    reads = []

    def read_then_wait(s):
        out = real(s)
        reads.append(len(out))
        try:
            barrier.wait()      # both passes hold their read here when nothing serialises them
        except threading.BrokenBarrierError:
            pass                # serialised: the other pass is waiting on the lock, not here
        return out

    q = JobQueue(db)
    jobs = [q.enqueue("orchestrator", "launch.readiness", {}, idempotency_key=f"race-{i}")
            for i in range(2)]
    errors: list[BaseException] = []

    def run(job):
        try:
            ctx = JobContext(job=job, db=db, queue=q, registry=Registry(db), phase=Phase.SHADOW)
            handlers.get("launch.readiness")(ctx)
        except BaseException as exc:  # noqa: BLE001 - reported by the test
            errors.append(exc)

    release._open_owner_actions = read_then_wait
    try:
        threads = [threading.Thread(target=run, args=(j,)) for j in jobs]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)
    finally:
        release._open_owner_actions = real
    assert len(reads) == 2, (reads, errors)
    return errors


def test_two_concurrent_readiness_passes_queue_each_request_once():
    db = _db()
    errors = _two_concurrent_passes(db)
    assert not errors, errors
    with db.session() as s:
        keys = [a.requirement_key for a in s.scalars(
            select(OwnerAction).where(OwnerAction.done == False))  # noqa: E712
            if a.requirement_key]
    assert keys, "the readiness pass queued nothing: the test proves nothing"
    dup = {k: n for k, n in Counter(keys).items() if n > 1}
    assert not dup, f"owner requests queued twice by concurrent passes: {dup}"


def test_the_check_and_the_insert_share_one_serialised_transaction():
    import inspect

    src = inspect.getsource(release.handle_launch_readiness)
    lock_at = src.index("_serialise_owner_queue(s, ctx.db)")
    assert lock_at < src.index("_open_owner_actions(s)") < src.index("s.add(OwnerAction(")
    body = inspect.getsource(release._serialise_owner_queue)
    assert "pg_advisory_xact_lock" in body and "BEGIN IMMEDIATE" in body


def test_two_concurrent_surface_seedings_queue_each_etsy_surface_request_once():
    """Batch 4: `etsy_ops.seed_owner_queue` read the existing `etsy_surface:*` rows and inserted
    the missing ones in its own unlocked session, after `launch.readiness` released the
    owner-queue lock. Two passes could each read "absent" and both insert. The interleaving is
    forced: each seeding waits at a barrier after its read, before it inserts."""
    from brambleloop.intel import etsy_surfaces
    from brambleloop.runtime import etsy_ops

    db = _db()
    barrier = threading.Barrier(2, timeout=3)
    real = etsy_surfaces.owner_queue
    calls = []

    def queue_then_wait():
        calls.append(1)
        try:
            barrier.wait()      # both seedings hold their read here when nothing serialises them
        except threading.BrokenBarrierError:
            pass                # serialised: the other seeding is waiting on the lock
        return real()

    errors: list[BaseException] = []

    def run():
        try:
            etsy_ops.seed_owner_queue(db)
        except BaseException as exc:  # noqa: BLE001 - reported by the test
            errors.append(exc)

    etsy_surfaces.owner_queue = queue_then_wait
    try:
        threads = [threading.Thread(target=run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)
    finally:
        etsy_surfaces.owner_queue = real
    assert not errors, errors
    assert len(calls) >= 2, calls
    with db.session() as s:
        keys = [a.requirement_key for a in s.scalars(select(OwnerAction))
                if a.requirement_key.startswith(etsy_ops.SURFACE_PREFIX)]
    assert keys, "the seeding queued nothing: the test proves nothing"
    dup = {k: n for k, n in Counter(keys).items() if n > 1}
    assert not dup, f"etsy_surface requests queued twice by concurrent seedings: {dup}"


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:1500]}", flush=True)
    sys.exit(1 if fails else 0)
