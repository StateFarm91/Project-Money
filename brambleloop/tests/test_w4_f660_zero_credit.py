"""F-660 Elastic Capacity: normal multi-agent operation continues when cloud credit is zero.

Acceptance (master_v1.1 F-660): "cloud sessions are optional burst capacity, never a structural
dependency; normal multi-agent operation continues when promotional/paid cloud credit is zero."
Ledger next action: "Record a zero-cloud-credit test run (runtime unaffected) as evidence".

This is that run, deterministic and local:
* the credits wallet (`finance.credits`) holds no promotional or cloud credit at all;
* every cloud-session / provider credential variable is removed from the environment;
* three workers (the runner's default pool) claim and complete jobs for three different agents
  *concurrently* -- a barrier only opens when all three handlers are running at once;
* the runtime's dispatch path (runner, worker, durable queue) does not read the credits wallet,
  so a zero (or absent) credit balance cannot gate it.

Session independence itself is proven by tests/test_cert_claude_independence.py (import
closure, image, start command, kill/resume without this session).

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_f660_zero_credit.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_f660_")
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC", "CLAUDE", "OPENAI", "GEMINI", "REPLICATE", "FAL_", "BFL",
                      "GOOGLE_CLOUD", "AWS_", "AZURE_")):
        os.environ.pop(_k)

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Agent, Job, JobStatus  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime.worker import HandlerRegistry, Worker  # noqa: E402

AGENTS = ("validator", "market_radar", "listing")


def _boot() -> Database:
    db = Database(f"sqlite:///{_TMP}/v{len(os.listdir(_TMP))}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def test_three_agents_work_concurrently_with_zero_cloud_credit():
    from brambleloop.finance import credits

    db = _boot()
    w = credits.wallet(db)
    assert w["providers"] == {} and w["credit_granted_cad"] == 0, w   # no credit of any kind
    with db.session() as s:
        names = {a.name for a in s.query(Agent).all()}
        assert set(AGENTS) <= names, sorted(names)
        for a in s.query(Agent).filter(Agent.name.in_(AGENTS)).all():
            a.allowed_job_types = list(a.allowed_job_types or []) + ["test.f660"]
    barrier = threading.Barrier(3, timeout=20)
    registry = HandlerRegistry()

    @registry.register("test.f660")
    def work(ctx):
        barrier.wait()                       # opens only when three run at the same time
        return {"agent": ctx.job.agent, "useful": True}

    q = JobQueue(db)
    for a in AGENTS:
        q.enqueue(a, "test.f660", {"who": a})
    workers = [Worker(db, f"pool-{i}", registry=registry) for i in range(3)]
    threads = [threading.Thread(target=w_.run_once) for w_ in workers]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not barrier.broken, "the three jobs did not run concurrently"
    with db.session() as s:
        rows = [(j.agent, j.status) for j in s.query(Job).filter(Job.job_type == "test.f660")]
    assert sorted(rows) == sorted((a, JobStatus.DONE) for a in AGENTS), rows
    assert sum(w_.stats.completed for w_ in workers) == 3


def test_the_dispatch_path_does_not_read_the_credit_wallet():
    src = ROOT / "src" / "brambleloop"
    paths = [src / "app" / "runner.py", src / "runtime" / "worker.py",
             src / "queue" / "durable.py"]
    assert all(p.is_file() for p in paths)
    for p in paths:
        text = p.read_text(encoding="utf-8")
        assert "finance.credits" not in text and "from ..finance import credits" not in text, p
        assert "credits.wallet" not in text, p


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {str(exc)[:500]}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
