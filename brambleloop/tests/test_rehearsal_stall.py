"""INT3: the shadow rehearsal's stall detector tells a busy worker from a stuck runtime.

Root cause of b9f9243 `store.publish[shadow]` = FAILED: the rehearsed product's
`store.publish` was queued FIFO (same band) behind `assets.build` jobs of the other Launch-0
products that the `chain.rebuild` cadence fans out. Under load each took 1-4 minutes on the
single pool worker, so this product's chain did not change for > 300 s while the worker was
continuously doing real work -- and the detector, which watched only this product's chain,
stopped the run. The job was never refused because it was never claimed yet, not because
anything blocked it.

These tests drive `_wait_for_chain` with a fake clock over a real queue:
  * busy: other products' jobs keep completing for longer than the stall window with no
    change in the rehearsed chain, then store.publish is claimed and refused -> "settled";
    the old chain-only detector would have stopped this run (asserted on the same scenario);
  * wedged: one job holds a lease that is never renewed, nothing completes -> "stalled"
    within the same 300 s window (the detector is not weakened);
  * the cap still bounds a run that progresses forever.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_rehearsal_stall.py
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402

SLUG = "cloudline-baby-blanket"
OTHERS = ["winter-village-graphghan", "spooky-garland", "market-basket-small",
          "market-basket-medium", "market-basket-large", "pressed-flower-motifs",
          "nordic-star-ornaments", "pet-snuggle-mat"]


def _rehearsal():
    spec = importlib.util.spec_from_file_location("shadow_rehearsal_int3",
                                                  ROOT / "scripts" / "shadow_rehearsal.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R = _rehearsal()


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='int3_stall_')}/q.sqlite")
    db.create_all()
    return db


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _chain_with_backlog(db):
    """The b9f9243 shape: this product's chain done up to store.publish, which waits at the
    same band behind other products' assets.build jobs queued earlier."""
    q = JobQueue(db)
    for jt in ("cir.compile", "gate.certify", "listing.draft", "assets.build",
               "pricing.position", "listing.seo", "launch.plan"):
        j = q.enqueue("t", jt, {"slug": SLUG}, priority=70)
        c = q.claim("w", [jt])
        assert c is not None and c.id == j.id
        assert q.complete(j.id, {"ok": True}, worker=c.leased_by, lease_token=c.lease_token)
    for s in OTHERS:
        q.enqueue("publishing", "assets.build", {"slug": s}, priority=70)
    pub = q.enqueue("store_operator", "store.publish", {"slug": SLUG, "version": "1.2.0"},
                    priority=70)
    return q, pub


def test_busy_worker_is_not_a_stall():
    db = _db()
    q, pub = _chain_with_backlog(db)
    clock = Clock()
    chain_marks: list[tuple[float, tuple]] = []
    state = {"ticks": 0, "running": None}

    def sleep(dt):
        # One worker: claim the next job in real claim order, run it for 180 s (3 polls of
        # 60 s), complete it. store.publish is claimed last and refused (dead), as in SHADOW.
        clock.t += 60
        state["ticks"] += 1
        chain_marks.append((clock.t, tuple((r["job_type"], r["status"])
                                           for r in R._jobs(db, R.CHAIN, SLUG))))
        if state["running"] is None:
            state["running"] = q.claim("web")
        if state["ticks"] % 3 == 0 and state["running"] is not None:
            j = state["running"]
            if j.job_type == "store.publish":
                assert q.fail(j.id, "capability not enabled: store.publish is a production "
                                    "capability; the system is in SHADOW mode", retry=False,
                              worker=j.leased_by, lease_token=j.lease_token) is not None
            else:
                assert q.complete(j.id, {"pdf_sha256": "x"}, worker=j.leased_by,
                                  lease_token=j.lease_token)
            state["running"] = None

    out = R._wait_for_chain(db, SLUG, clock=clock, sleep=sleep, poll=60)
    assert out["reason"] == "settled", out
    assert q.get(pub.id).status.value == "dead"
    print("OK   busy worker: store.publish settled after", out["waited_s"], "s")
    # The same scenario contains a window > 300 s with the rehearsed chain unchanged: the
    # pre-INT3 chain-only detector stopped exactly here (the b9f9243 FAILED).
    longest, since, prev = 0.0, 0.0, None
    assert chain_marks, "scenario produced no polls"
    for t, m in chain_marks:
        if m != prev:
            prev, since = m, t
        longest = max(longest, t - since)
    assert longest > R.STALL_SECONDS, longest
    print(f"OK   chain-only detector would have stalled ({longest:.0f}s unchanged)")


def test_wedged_runtime_is_still_a_stall():
    db = _db()
    q, _pub = _chain_with_backlog(db)
    q.claim("web")   # holds a lease, never completes, never heartbeats
    clock = Clock()

    def sleep(dt):
        clock.t += dt

    out = R._wait_for_chain(db, SLUG, clock=clock, sleep=sleep, poll=30)
    assert out["reason"] == "stalled", out
    assert out["waited_s"] <= R.STALL_SECONDS + 60, out
    assert out["queue"]["running"] and out["queue"]["pending_by_priority"], out
    print("OK   wedged runtime stalls after", out["waited_s"], "s with queue evidence")


def test_heartbeat_counts_as_progress_but_the_cap_still_binds():
    db = _db()
    q, _pub = _chain_with_backlog(db)
    j = q.claim("web")
    clock = Clock()

    def sleep(dt):
        clock.t += dt
        q.heartbeat(j.id, worker=j.leased_by, lease_token=j.lease_token)

    out = R._wait_for_chain(db, SLUG, clock=clock, sleep=sleep, poll=60, cap=900)
    assert out["reason"] == "cap", out
    print("OK   heartbeating job is progress; cap ends the run at", out["waited_s"], "s")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    assert tests
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL", t.__name__, type(e).__name__, e)
    raise SystemExit(1 if failed else 0)
