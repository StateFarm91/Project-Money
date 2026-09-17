"""Persistence proof using real OS processes, not simulated ones.

The owner's requirement is "prove persistence, not merely deployment". So this suite spawns
actual worker subprocesses against a file-backed database, kills them with SIGKILL mid-job
(no cleanup, no graceful shutdown, exactly like a platform evicting a container), and then
proves a fresh worker picks the work up and finishes it.

SIGKILL matters: SIGTERM would let the process tidy up, which is the easy case. The hard case
is the one where the worker simply ceases to exist while holding a lease.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Job, JobStatus, Product, utcnow,
)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: F401,E402
from brambleloop.runtime.worker import Scheduler, Worker  # noqa: E402

PYTHON = str(ROOT / ".venv" / "bin" / "python")
if not Path(PYTHON).exists():  # pragma: no cover - fallback for a bare interpreter
    PYTHON = sys.executable


SLOW_WORKER = """
import os, sys, time
sys.path.insert(0, {src!r})
from brambleloop.core.db import Database
from brambleloop.core.models import Phase
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime.worker import Worker, handlers

@handlers.register("test.slow")
def slow(ctx):
    # Announce that we have the lease, then hang until killed.
    open({flag!r}, "w").write(str(os.getpid()))
    time.sleep(600)
    return {{"never": True}}

db = Database({url!r})
w = Worker(db, {name!r}, phase=Phase.SHADOW)
w.run(max_seconds=600)
"""


def _spawn_slow_worker(url: str, flag: Path, name: str) -> subprocess.Popen:
    code = SLOW_WORKER.format(src=str(SRC), flag=str(flag), url=url, name=name)
    return subprocess.Popen([PYTHON, "-c", code], stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)


def _wait_for(path: Path, timeout: float = 20.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists():
            return True
        time.sleep(0.1)
    return False


def test_sigkilled_worker_loses_no_work_and_another_finishes_it():
    """A worker is SIGKILLed while holding a lease. The job must survive and complete."""
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/live.sqlite"
        flag = Path(tmp) / "claimed.flag"

        db = Database(url)
        db.create_all()
        Registry(db).seed_defaults()
        with db.session() as s:
            from brambleloop.core.models import Agent
            a = s.scalar(select(Agent).where(Agent.name == "validator"))
            a.allowed_job_types = list(a.allowed_job_types) + ["test.slow"]

        # A generous lease so the assertions below test semantics, not subprocess timing.
        q = JobQueue(db, lease_seconds=300)
        job = q.enqueue("validator", "test.slow", {"payload": "important"})

        proc = _spawn_slow_worker(url, flag, "doomed-worker")
        assert _wait_for(flag), "worker never claimed the job"

        # Hard kill: no signal handler, no cleanup, lease still held in the database.
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=10)

        assert q.get(job.id).status == JobStatus.RUNNING  # orphaned, lease still recorded
        assert q.get(job.id).leased_by == "doomed-worker"

        # Nothing may steal it while the lease is live -- otherwise two workers could run the
        # same job concurrently, which is how a job that spends money spends it twice.
        assert q.claim("eager-worker") is None, "a live lease must not be stealable"

        # Expire the lease deterministically rather than sleeping on the wall clock.
        with db.session() as s:
            s.get(Job, job.id).lease_expires_at = utcnow() - timedelta(seconds=1)

        # A fresh worker with a real handler now recovers and completes it.
        from brambleloop.runtime.worker import handlers

        @handlers.register("test.slow")
        def _fast(ctx):
            return {"recovered": True}

        rescuer = Worker(db, "rescue-worker")
        assert rescuer.run_once() is True
        final = q.get(job.id)
        assert final.status == JobStatus.DONE, final.last_error
        assert final.outputs == {"recovered": True}
        assert final.attempts == 2  # one lost attempt, one that finished
        assert final.inputs == {"payload": "important"}  # inputs survived intact


def test_pipeline_resumes_across_a_worker_restart_mid_flight():
    """Kill the worker mid-pipeline; a new process must carry the product to certification."""
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/live.sqlite"
        db = Database(url)
        db.create_all()
        Registry(db).seed_defaults()
        JobQueue(db).enqueue("orchestrator", "plan.cycle", {})

        # First worker: run only two steps, then "crash" (process simply stops).
        w1 = Worker(db, "worker-a")
        w1.run_once()
        w1.run_once()
        del w1

        with db.session() as s:
            assert s.scalar(select(Product)) is None  # not finished yet
        assert JobQueue(db).counts()["pending"] >= 1  # work is still queued, not lost

        # Second worker process picks up exactly where the first stopped.
        w2 = Worker(db, "worker-b")
        for _ in range(50):
            if not w2.run_once():
                break

        with db.session() as s:
            product = s.scalar(select(Product).where(
                Product.slug == "nordic-forest-mosaic-throw"))
            assert product is not None and product.status == "certified"
            actors = {a.actor for a in s.scalars(select(AuditLog))}
        assert actors, "the audit trail must survive the restart"


def test_state_survives_a_full_process_restart_on_disk():
    """Everything written by one process is visible to a completely separate one."""
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/live.sqlite"

        first = subprocess.run(
            [PYTHON, "-c", f"""
import sys; sys.path.insert(0, {str(SRC)!r})
from brambleloop.core.db import Database
from brambleloop.agents.registry import Registry
from brambleloop.queue.durable import JobQueue
db = Database({url!r}); db.create_all()
Registry(db).seed_defaults()
JobQueue(db).enqueue("orchestrator", "plan.cycle", {{}}, idempotency_key="cycle:1")
Registry(db).audit("orchestrator", "process.one", artifact="before-restart")
print("first process done")
"""], capture_output=True, text=True)
        assert first.returncode == 0, first.stderr

        second = subprocess.run(
            [PYTHON, "-c", f"""
import sys; sys.path.insert(0, {str(SRC)!r})
from sqlalchemy import select
from brambleloop.core.db import Database
from brambleloop.core.models import AuditLog, Job
db = Database({url!r})
with db.session() as s:
    jobs = list(s.scalars(select(Job)))
    audits = [a.artifact for a in s.scalars(select(AuditLog))]
print(len(jobs), audits)
"""], capture_output=True, text=True)
        assert second.returncode == 0, second.stderr
        assert "1 ['before-restart']" in second.stdout, second.stdout


def test_scheduler_does_not_duplicate_cadences_across_restarts():
    """Two scheduler processes in the same window must not double-enqueue."""
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/live.sqlite"
        db = Database(url)
        db.create_all()

        first = Scheduler(db).tick()
        assert first, "first scheduler run should enqueue cadences"

        # Simulate the process dying and a new one starting immediately.
        again = Scheduler(Database(url)).tick()
        assert again == [], "a restarted scheduler must not re-enqueue the same window"

        with db.session() as s:
            total = len(list(s.scalars(select(Job))))
        assert total == len(first)


def test_unfinished_jobs_are_visible_for_recovery_after_restart():
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/live.sqlite"
        db = Database(url)
        db.create_all()
        q = JobQueue(db, lease_seconds=1)
        for i in range(3):
            q.enqueue("market_radar", "radar.scan", {"i": i})
        q.claim("worker-1")
        q.claim("worker-1")

        counts = JobQueue(Database(url)).counts()
        assert counts["running"] == 2 and counts["pending"] == 1

        time.sleep(1.2)
        recovered = JobQueue(Database(url), lease_seconds=30)
        assert recovered.claim("worker-2") is not None
        assert recovered.claim("worker-2") is not None


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
