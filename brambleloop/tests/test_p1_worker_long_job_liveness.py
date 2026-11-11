"""P1 6783107211: a long job does not mark the worker dead; a genuinely hung one still does.

Production /health read `runner.worker_alive` false every night from ~00:15 to ~00:20Z, on two
builds booted at different times. The scheduler keys each cadence window as
`floor(epoch / period)`, so every 24-hour cadence (~50 of them) opens at 00:00:00Z at once;
the embedded worker drains them in band order and one handler ~13 minutes in runs ~7
minutes. The runner wrote its tick only between jobs and called a tick older than 120 s
dead -- so that handler read as a dead worker for its whole run, and /api/verify failed
`worker_is_alive`.

Reproduced here through the REAL runner loop (`app.runner._worker_loop`) on a file-backed
database, with the thresholds scaled down (tick stale after 1 s, handler budget 3 s):

* the nightly shape: a daily cadence (`plan.cycle`, enqueued by `Scheduler.tick` exactly as
  at midnight) whose handler runs past the tick threshold. Before the fix this read dead
  for the whole run; now it reads alive on `handler_running`, with the job named;
* a handler past its budget (the lease system's hung-handler cap) reads dead;
* a worker wedged OUTSIDE a handler (here: in the claim) reads dead after the tick
  threshold -- being inside `run_once` is not "busy".

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_p1_worker_long_job_liveness.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = tempfile.mkdtemp(prefix="p1_liveness_art_")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import runner  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job, JobStatus, Phase  # noqa: E402
from brambleloop.runtime import worker as W  # noqa: E402

JOB_TYPE = "plan.cycle"          # the daily_review cadence: one of the midnight burst


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='p1_liveness_')}/c.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


class _Harness:
    """The real `_worker_loop` in a thread, with scaled thresholds and one slow handler."""

    def __init__(self, handler_seconds: float, *, stale_s=1.0, budget_s=3.0, long_s=None,
                 raises: bool = False):
        self.handler_seconds = handler_seconds
        self.raises = raises
        self.release = threading.Event()
        self.entered = threading.Event()
        self.saved = (runner.WORKER_TICK_STALE_S, runner.handler_budget_seconds,
                      runner._START_DELAY, runner._IDLE_SLEEP, runner.STATE,
                      W.handlers.get(JOB_TYPE), W.CADENCES, runner.HANDLER_LONG_S)
        runner.WORKER_TICK_STALE_S = stale_s
        runner.HANDLER_LONG_S = budget_s * 0.6 if long_s is None else long_s
        runner.handler_budget_seconds = lambda: budget_s
        runner._START_DELAY, runner._IDLE_SLEEP = 0.0, 0.05
        runner.STATE = runner.RunnerState(enabled=True)

        def slow(ctx):
            self.entered.set()
            self.release.wait(self.handler_seconds)
            if self.raises:
                raise RuntimeError("handler failed (review 6785727146 M9)")
            return {"artifact": "slow plan.cycle"}
        W.handlers.register(JOB_TYPE)(slow)
        W.CADENCES = [c for c in W.CADENCES if c[2] == JOB_TYPE]
        # only the job under test: no orchestrator idle wake, no refill after a job ends
        from brambleloop.autonomy import orchestrator as _orch
        self.saved_wake = (_orch, _orch.idle_wake, W.Worker._refill_after)
        _orch.idle_wake = lambda *a, **k: False
        W.Worker._refill_after = lambda self_, job: None
        self.stop = threading.Event()
        self.db = _db()

    def start(self):
        self.thread = threading.Thread(
            target=runner._worker_loop,
            args=(self.db, "worker-p1", Phase.SHADOW, self.stop), daemon=True)
        self.thread.start()
        return self

    def midnight(self):
        """Scheduler.tick at a 00:00Z window opening, as production's first tick does."""
        midnight = datetime(2026, 11, 11, 0, 0, 30, tzinfo=timezone.utc)
        return W.Scheduler(self.db).tick(now=midnight)

    def close(self):
        self.release.set()
        self.stop.set()
        self.thread.join(timeout=10)
        (runner.WORKER_TICK_STALE_S, runner.handler_budget_seconds, runner._START_DELAY,
         runner._IDLE_SLEEP, runner.STATE, handler, W.CADENCES,
         runner.HANDLER_LONG_S) = self.saved
        if handler is not None:
            W.handlers.register(JOB_TYPE)(handler)
        orch, wake, refill = self.saved_wake
        orch.idle_wake, W.Worker._refill_after = wake, refill


def _wait(pred, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def test_midnight_windows_all_open_together_whatever_the_boot_time():
    """The anchor: a 24 h window is floor(epoch / 86400), so every daily cadence's window
    opens at 00:00:00Z -- independent of when the process booted."""
    daily = [c for c in W.CADENCES if c[3] == 24 * 60 * 60]
    assert len(daily) >= 30, len(daily)
    before = datetime(2026, 11, 10, 23, 59, 59, tzinfo=timezone.utc)
    after = before + timedelta(seconds=2)
    for name, _a, _jt, period in daily:
        assert int(after.timestamp() // period) == int(before.timestamp() // period) + 1, name


def test_a_long_nightly_handler_reads_busy_not_dead():
    h = _Harness(handler_seconds=2.5, long_s=2.2).start()
    try:
        assert "daily_review" in h.midnight()
        assert h.entered.wait(10), "the cadence's handler never started"
        time.sleep(1.6)                                   # past the 1 s tick threshold
        st = runner.STATE.to_dict()
        tick_age = (datetime.now(timezone.utc)
                    - runner.STATE.worker_last_tick).total_seconds()
        assert tick_age > runner.WORKER_TICK_STALE_S, tick_age    # pre-fix: dead here
        assert st["worker_alive"] is True and st["worker_alive_basis"] == "handler_running", st
        assert st["worker_busy"]["job_type"] == JOB_TYPE, st["worker_busy"]
        job_id = st["worker_busy"]["job_id"]
        h.release.set()

        def done():
            with h.db.session() as s:
                return s.get(Job, job_id).status == JobStatus.DONE
        assert _wait(done), "the long job never completed"
        # the next job (if any) is another one: this job is no longer what keeps it alive
        assert (runner.STATE.busy() or {}).get("job_id") != job_id, runner.STATE.busy()
        assert _wait(lambda: runner.STATE.liveness()[0]), runner.STATE.to_dict()
    finally:
        h.close()


def test_a_handler_past_its_budget_reads_dead():
    h = _Harness(handler_seconds=30.0, stale_s=0.5, budget_s=1.5, long_s=0.8).start()
    try:
        h.midnight()
        assert h.entered.wait(10)
        assert _wait(lambda: runner.STATE.liveness()[1] == "handler_over_budget", 6), \
            runner.STATE.to_dict()
        assert runner.STATE.to_dict()["worker_alive"] is False
    finally:
        h.close()


def test_a_worker_wedged_outside_a_handler_still_reads_dead():
    """Inside run_once but not in a handler (a hung claim) is not busy: dead after the tick
    threshold, exactly as before."""
    h = _Harness(handler_seconds=0.0, stale_s=0.5, budget_s=60.0)
    wedged = threading.Event()
    real_claim = W.JobQueue.claim

    def hung_claim(self, *a, **k):
        if wedged.is_set():
            time.sleep(30)
        return real_claim(self, *a, **k)
    W.JobQueue.claim = hung_claim
    try:
        h.start()
        assert _wait(lambda: runner.STATE.worker_last_tick is not None), "never ticked"
        # a real job first, so a "busy" left behind by it would show (it must be cleared)
        h.midnight()
        assert h.entered.wait(10), "the job never ran"

        def done():
            with h.db.session() as s:
                return all(j.status == JobStatus.DONE for j in
                           s.query(Job).filter(Job.job_type == JOB_TYPE))
        assert _wait(done), "the job never completed"
        wedged.set()
        assert _wait(lambda: runner.STATE.liveness() == (False, "tick_stale"), 6), \
            runner.STATE.to_dict()
        assert runner.STATE.busy() is None
    finally:
        W.JobQueue.claim = real_claim
        h.close()


def test_the_pure_liveness_rules():
    now = datetime.now(timezone.utc)

    class _W:
        current = None
    w = _W()
    st = runner.RunnerState(enabled=True, worker_last_tick=now - timedelta(seconds=600),
                            worker_ref=w)
    assert st.liveness(now) == (False, "tick_stale")
    w.current = {"job_id": 7, "job_type": JOB_TYPE, "started_at": now - timedelta(seconds=420)}
    assert st.liveness(now) == (True, "handler_running")       # the nightly 7-minute job
    w.current["started_at"] = now - timedelta(seconds=runner.HANDLER_LONG_S + 1)
    assert st.liveness(now) == (True, "handler_long")           # alive, degraded
    assert runner.HANDLER_LONG_S == 15 * 60 < runner.handler_budget_seconds()
    w.current["started_at"] = now - timedelta(seconds=runner.handler_budget_seconds() + 1)
    assert st.liveness(now) == (False, "handler_over_budget")
    w.current = None
    st.worker_last_tick = now
    assert st.liveness(now) == (True, "tick")
    assert runner.RunnerState(enabled=True).liveness(now) == (False, "no_tick")


def test_a_handler_past_the_long_threshold_is_handler_long_then_dead_at_the_budget():
    """Review 6785727146 F1: under the threshold handler_running; past it handler_long
    (alive, degraded); past the budget dead."""
    h = _Harness(handler_seconds=30.0, stale_s=0.3, budget_s=2.4, long_s=1.0).start()
    try:
        h.midnight()
        assert h.entered.wait(10)
        seen = []
        assert _wait(lambda: (seen.append(runner.STATE.liveness()[1]) or
                              seen[-1] == "handler_over_budget"), 8), seen
        order = [b for i, b in enumerate(seen) if i == 0 or seen[i - 1] != b]
        assert order[-3:] == ["handler_running", "handler_long", "handler_over_budget"], order
    finally:
        h.close()


def test_the_long_handler_incident_is_raised_once_and_resolved_when_it_finishes():
    """F1: one open, non-halting P2 incident while the handler is long (restated, never
    duplicated), resolved -- with the reason -- once the handler is no longer running."""
    from brambleloop.core.models import Incident

    db = _db()

    class _Wk:
        current = None
    wk = _Wk()
    now = datetime.now(timezone.utc)
    st = runner.RunnerState(enabled=True, worker_last_tick=now - timedelta(seconds=3000),
                            worker_ref=wk)

    def rows():
        with db.session() as s:
            return [(r.severity, r.resolved, r.halts_publication, (r.detail or {}).get("job_id"),
                     r.report_count) for r in s.query(Incident).filter(
                Incident.signature == runner.LONG_HANDLER_SIGNATURE).order_by(Incident.id)]
    wk.current = {"job_id": 1, "job_type": JOB_TYPE, "started_at": now - timedelta(seconds=60)}
    assert runner.watch_long_handler(db, st, now) == "none" and rows() == []
    wk.current["started_at"] = now - timedelta(seconds=runner.HANDLER_LONG_S + 30)
    assert runner.watch_long_handler(db, st, now) == "raised"
    assert runner.watch_long_handler(db, st, now) == "kept"
    assert rows() == [("P2", False, False, 1, 2)], rows()
    wk.current["started_at"] = now - timedelta(seconds=runner.handler_budget_seconds() + 5)
    assert runner.watch_long_handler(db, st, now) == "kept"      # over budget: still open
    wk.current = {"job_id": 2, "job_type": JOB_TYPE,             # a different long job
                  "started_at": now - timedelta(seconds=runner.HANDLER_LONG_S + 30)}
    assert runner.watch_long_handler(db, st, now) == "raised"
    assert [r[1] for r in rows()] == [True, False] and rows()[1][3] == 2, rows()
    wk.current = None                                            # finished
    assert runner.watch_long_handler(db, st, now) == "resolved"
    assert all(r[1] for r in rows()), rows()
    with db.session() as s:
        last = s.query(Incident).order_by(Incident.id.desc()).first()
        assert "no longer running" in last.detail["resolution"], last.detail
    # the scheduler loop is what calls it (it ticks while the worker is held)
    src = (ROOT / "src" / "brambleloop" / "app" / "runner.py").read_text()
    loop = src[src.index("def _scheduler_loop"):src.index("# v1.1 lane I W-3")]
    assert "watch_long_handler(db)" in loop


def test_a_handler_that_raises_clears_current():
    """Review 6785727146 F3 (M9): the finally clears `current` on a raise too."""
    h = _Harness(handler_seconds=0.3, raises=True).start()
    try:
        h.midnight()
        assert h.entered.wait(10)

        def failed():
            with h.db.session() as s:
                j = s.query(Job).filter(Job.job_type == JOB_TYPE).one()
                return j.status in (JobStatus.FAILED, JobStatus.DEAD, JobStatus.PENDING) \
                    and j.attempts >= 1
        assert _wait(failed), "the raising job never failed"
        assert _wait(lambda: runner.STATE.busy() is None), runner.STATE.busy()
        assert getattr(runner.STATE.worker_ref, "current", "missing") is None
    finally:
        h.close()


def test_in_a_pool_worker_ref_is_worker_zero():
    """F3 (M4): with more than one pool worker, liveness reads worker 0, never another."""
    h = _Harness(handler_seconds=0.0)

    class _T:
        def get(self):
            return 2
    stops = [threading.Event(), threading.Event()]
    try:
        t1 = threading.Thread(target=runner._worker_loop,
                              args=(h.db, "worker-p1-1", Phase.SHADOW, stops[1], 1, _T()),
                              daemon=True)
        t1.start()
        time.sleep(0.4)
        assert runner.STATE.worker_ref is None, runner.STATE.worker_ref
        t0 = threading.Thread(target=runner._worker_loop,
                              args=(h.db, "worker-p1-0", Phase.SHADOW, stops[0], 0, _T()),
                              daemon=True)
        t0.start()
        assert _wait(lambda: runner.STATE.worker_ref is not None)
        assert runner.STATE.worker_ref.name == "worker-p1-0", runner.STATE.worker_ref.name
        time.sleep(0.3)
        assert runner.STATE.worker_ref.name == "worker-p1-0"
    finally:
        for e in stops:
            e.set()
        h.stop.set()
        h.thread = t0
        h.close()
        t1.join(timeout=10)


def test_the_tick_threshold_can_only_be_tightened_by_the_environment():
    """Review 6785727146 F2: BRAMBLELOOP_WORKER_TICK_STALE_S cannot loosen 120 s."""
    import importlib
    import subprocess

    code = ("import os;os.environ['BRAMBLELOOP_WORKER_TICK_STALE_S']='{v}';"
            "from brambleloop.app import runner;print(runner.WORKER_TICK_STALE_S)")
    for value, expect in (("9999", 120.0), ("30", 30.0)):
        out = subprocess.run([sys.executable, "-c", code.format(v=value)], capture_output=True,
                             text=True, env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                             timeout=120)
        assert float(out.stdout.strip().splitlines()[-1]) == expect, (value, out.stdout,
                                                                      out.stderr[-400:])
    importlib.invalidate_caches()


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
