"""v1.1 lane A, §95: "Kill a worker during unattended execution: the job is safely
reclaimed/recovered without duplicate external effects."

Two proofs:

1. A real OS process runs `autonomy.orchestrate`, performs all of its effects (missions, memory,
   timeline, an owner approval item), and is SIGKILLed before it can complete the job. A fresh
   worker reclaims the expired lease and runs the same job again. Every effect is keyed, so the
   database afterwards holds exactly what one clean run leaves -- compared against a reference
   database that ran once without interruption.
2. The lease token (ported from Codex 8877f05): two workers that share a NAME -- as two
   containers with the same PID did under the old `web-<pid>` default -- cannot complete each
   other's attempt. Name fencing alone accepted the stale completion.
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

from sqlalchemy import func, select, update  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy.models import CompanyMemory, TimelineEvent  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, Job, JobStatus, Listing,  # noqa: E402
                                     OwnerAction, PatternVersion, Product, utcnow)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import Worker, handlers  # noqa: E402

NOW = "2026-10-06T03:00:00+00:00"

KILLED_WORKER = """
import os, sys, time
sys.path.insert(0, {src!r})
from brambleloop.core.db import Database
from brambleloop.core.models import Phase
from brambleloop.runtime import pipeline  # registers the real handlers
from brambleloop.runtime.worker import Worker, handlers
from brambleloop.autonomy.handlers import handle_orchestrate

real = handle_orchestrate

def effects_then_hang(ctx):
    real(ctx)                                  # every effect written...
    open({flag!r}, "w").write(str(os.getpid()))
    time.sleep(600)                            # ...and killed before completing
    return {{"never": True}}

handlers.register("autonomy.orchestrate")(effects_then_hang)
db = Database({url!r})
Worker(db, "web-7", phase=Phase.SHADOW).run(max_seconds=600)
"""


def seed(db):
    db.create_all()
    Registry(db).seed_defaults()
    with db.session() as s:
        p = Product(slug="cosy", title="Cosy")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={}, certified=True,
                             certificate={"ok": True}))
        s.add(Listing(product_slug="cosy", version="1.0.0", title="t", description="d"))


def effects(db) -> dict:
    with db.session() as s:
        gen = [j for j in s.scalars(select(Job)) if (j.inputs or {}).get("source") == "autonomy"]
        return {
            "generated_jobs": sorted(j.idempotency_key for j in gen),
            "memory": sorted(k for (k,) in s.execute(select(CompanyMemory.key))
                             if k != "orchestrator:last_tick"),
            "timeline": sorted(k for (k,) in s.execute(select(TimelineEvent.key))
                               if not k.startswith("department.degraded")),
            "owner_actions": s.scalar(select(func.count()).select_from(OwnerAction)),
            "protected_jobs": s.scalar(select(func.count()).select_from(Job).where(
                Job.job_type.in_(["store.publish", "store.activate", "ads.campaign",
                                  "support.reply"]))),
        }


def test_sigkilled_orchestrator_is_reclaimed_without_duplicate_effects():
    with tempfile.TemporaryDirectory() as tmp:
        # Reference: one clean, uninterrupted run.
        ref = Database(f"sqlite:///{tmp}/ref.sqlite")
        seed(ref)
        JobQueue(ref).enqueue("coo", "autonomy.orchestrate", {"now": NOW},
                              idempotency_key="orch-1")
        w = Worker(ref, "ref")
        assert w.run_once() and w.stats.completed == 1, w.stats
        expected = effects(ref)
        assert len(expected["generated_jobs"]) == 11, expected
        assert expected["owner_actions"] == 1 and expected["protected_jobs"] == 0

        # The run that gets killed.
        url = f"sqlite:///{tmp}/live.sqlite"
        db = Database(url)
        seed(db)
        job = JobQueue(db).enqueue("coo", "autonomy.orchestrate", {"now": NOW},
                                   idempotency_key="orch-1")
        flag = Path(tmp) / "has_effects"
        script = Path(tmp) / "killed.py"
        script.write_text(KILLED_WORKER.format(src=str(SRC), url=url, flag=str(flag)))
        proc = subprocess.Popen([sys.executable, str(script)])
        try:
            deadline = time.time() + 120
            while not flag.exists() and time.time() < deadline:
                time.sleep(0.1)
            assert flag.exists(), "the doomed worker never wrote its effects"
            os.kill(proc.pid, signal.SIGKILL)
            proc.wait(timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()
        held = JobQueue(db).get(job.id)
        assert held.status == JobStatus.RUNNING and held.leased_by == "web-7", held
        first_token = held.lease_token
        assert first_token, "claim did not stamp a lease token"
        half = effects(db)
        assert half == expected, "the killed attempt's effects differ from one clean run"

        # The platform restarts the container; the lease expires; a new worker reclaims.
        with db.session() as s:
            s.execute(update(Job).where(Job.id == job.id).values(
                lease_expires_at=utcnow() - timedelta(seconds=1)))
        w2 = Worker(db, "web-7")              # same name, as a restarted container would be
        assert w2.run_once() is True
        assert w2.stats.completed == 1, w2.stats
        done = JobQueue(db).get(job.id)
        assert done.status == JobStatus.DONE and done.attempts == 2, done
        after = effects(db)
        assert after == expected, {k: (len(after[k]) if isinstance(after[k], list) else after[k],
                                       len(expected[k]) if isinstance(expected[k], list)
                                       else expected[k]) for k in after}
        # The stale attempt's completion would now be refused by its token.
        assert JobQueue(db).complete(job.id, {"late": True}, worker="web-7",
                                     lease_token=first_token) is False


def test_same_named_workers_cannot_complete_each_others_attempt():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(f"sqlite:///{tmp}/t.sqlite")
        db.create_all()
        Registry(db).seed_defaults()
        q = JobQueue(db, lease_seconds=60)
        job = q.enqueue("coo", "autonomy.department_review", {"department": "finance"})
        a = q.claim("web-7")
        assert a.id == job.id and a.lease_token
        with db.session() as s:
            s.execute(update(Job).where(Job.id == job.id).values(
                lease_expires_at=utcnow() - timedelta(seconds=1)))
        b = q.claim("web-7")                     # another container, same PID, same name
        assert b.id == job.id and b.lease_token and b.lease_token != a.lease_token
        # Name fencing alone would accept this: same name, job RUNNING.
        assert q.complete(job.id, {"stale": True}, worker="web-7",
                          lease_token=a.lease_token) is False
        assert q.fail(job.id, "stale failure", worker="web-7",
                      lease_token=a.lease_token) is None
        assert q.heartbeat(job.id, worker="web-7", lease_token=a.lease_token) is False
        assert q.complete(job.id, {"fresh": True}, worker="web-7",
                          lease_token=b.lease_token) is True
        final = q.get(job.id)
        assert final.status == JobStatus.DONE and final.outputs == {"fresh": True}
        assert final.lease_token is None
        with db.session() as s:
            refused = s.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.job_id == job.id,
                AuditLog.action.like("queue.stale_lease%")))
        assert refused >= 2, refused


def test_the_worker_presents_its_token_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(f"sqlite:///{tmp}/t.sqlite")
        db.create_all()
        Registry(db).seed_defaults()
        seen = {}

        @handlers.register("test.v11a.token")
        def _h(ctx):
            seen["token"] = ctx.job.lease_token
            # Simulate the lease being reclaimed by a same-named worker mid-handler.
            with ctx.db.session() as s:
                s.execute(update(Job).where(Job.id == ctx.job.id).values(lease_token="other"))
            return {"done": True}

        Registry(db)
        with db.session() as s:
            from brambleloop.core.models import Agent
            agent = s.scalar(select(Agent).where(Agent.name == "coo"))
            agent.allowed_job_types = list(agent.allowed_job_types) + ["test.v11a.token"]
        JobQueue(db).enqueue("coo", "test.v11a.token", {})
        w = Worker(db, "web-7")
        assert w.run_once() is True
        assert seen["token"], seen
        assert w.stats.completed == 0 and w.stats.skipped == 1, w.stats
        with db.session() as s:
            j = s.scalar(select(Job).where(Job.job_type == "test.v11a.token"))
            assert j.status == JobStatus.RUNNING, j.status


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
