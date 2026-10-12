"""W4-SWARMCONTROL: ownership boundaries, resource-aware concurrency, cooperative preemption.

Rows: F-457 (Ownership Boundaries), F-470 (Resource-Aware Concurrency), F-473 (Priority
Preemption).
Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_swarmcontrol.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
sys.path.insert(0, str(ROOT.parent / "ops"))
_TMP = tempfile.mkdtemp(prefix="w4_swarmcontrol_")

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus  # noqa: E402
from brambleloop.swarm import preempt, resources  # noqa: E402

NOW = datetime.now(timezone.utc)
_n = [0]


def _db() -> Database:
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


# ---- F-470 -------------------------------------------------------------------------------

def _fake_host(*, rss_kb=None, mem_max=None, psi=None, meminfo_kb=None) -> tuple[Path, Path]:
    root = Path(tempfile.mkdtemp(prefix="swc_host_"))
    proc, cg = root / "proc", root / "cg"
    (proc / "self").mkdir(parents=True)
    cg.mkdir()
    if rss_kb is not None:
        (proc / "self" / "status").write_text(f"Name:\tpython\nVmRSS:\t{rss_kb} kB\n")
    if meminfo_kb is not None:
        (proc / "meminfo").write_text(f"MemTotal:       {meminfo_kb} kB\n")
    if mem_max is not None:
        (cg / "memory.max").write_text(str(mem_max))
    if psi is not None:
        (cg / "cpu.pressure").write_text(f"some avg10=1.00 avg60={psi} avg300=1.00 total=1\n")
    return proc, cg


def test_memory_or_cpu_pressure_saturates_and_host_load_never_does():
    proc, cg = _fake_host(rss_kb=900 * 1024, mem_max=1024 * 1024 * 1024)
    r = resources.read(None, proc=proc, cgroup=cg, load=lambda: (99.0, 0, 0))
    assert r["saturated"] is True and "memory" in r["why"], r
    assert r["load_per_cpu"] and "informational" in r["load_note"]
    proc, cg = _fake_host(rss_kb=100 * 1024, mem_max=1024 * 1024 * 1024, psi=91.5)
    r = resources.read(None, proc=proc, cgroup=cg, load=lambda: (0.1, 0, 0))
    assert r["saturated"] is True and "CPU pressure" in r["why"]
    proc, cg = _fake_host(rss_kb=100 * 1024, mem_max=1024 * 1024 * 1024, psi=5.0)
    r = resources.read(None, proc=proc, cgroup=cg, load=lambda: (99.0, 0, 0))
    assert r["saturated"] is False, "host-wide load must not scale the pool down"


def test_unreadable_resources_are_unknown_not_healthy():
    proc, cg = _fake_host()
    r = resources.read(None, proc=proc, cgroup=cg, load=lambda: (0.1, 0, 0))
    assert r["saturated"] is None and r["why"].startswith("UNKNOWN")
    proc, cg = _fake_host(rss_kb=1024, meminfo_kb=8 * 1024 * 1024)
    r = resources.read(None, proc=proc, cgroup=cg, load=lambda: (0.1, 0, 0))
    assert r["memory_limit_source"].startswith("MemTotal") and r["saturated"] is False
    assert resources.db_connections(_db())["in_use"] is None  # SQLite: not applicable


def test_worker_target_returns_to_one_worker_while_saturated():
    from brambleloop.swarm import capacity, orchestrate

    db = _db()
    real = (orchestrate.latest_allocation, orchestrate.parallelism_advice, capacity._resources)
    orchestrate.latest_allocation = lambda db, now=None: {
        "allocation_id": "a1", "lanes": {"listing": {"granted": 3, "open_work": 5}}}
    orchestrate.parallelism_advice = lambda db, now=None: None
    try:
        capacity._resources = lambda db: {"saturated": False, "why": "within thresholds"}
        assert capacity.worker_target(db, pool=4)["target"] == 3
        capacity._resources = lambda db: {"saturated": True, "why": "memory 92%"}
        out = capacity.worker_target(db, pool=4)
        assert out["target"] == 1 and "resources saturated" in out["why"], out
        capacity._resources = lambda db: {"saturated": None, "why": "UNKNOWN"}
        assert capacity.worker_target(db, pool=4)["target"] == 3  # unknown is not saturation
    finally:
        (orchestrate.latest_allocation, orchestrate.parallelism_advice,
         capacity._resources) = real


def test_health_carries_the_resources_signal():
    from brambleloop.ops import health

    assert "resources" in health.SIGNALS
    db = _db()
    with db.session() as s:
        readings = health.read(s, runner_state={}, env={}, now=NOW)
    r = next(x for x in readings if x.signal == "resources")
    assert r.state in (health.HEALTHY, health.DEGRADED, health.UNKNOWN)
    assert "memory_share" in r.evidence and "cpu_pressure_avg60" in r.evidence


# ---- F-473 -------------------------------------------------------------------------------

def _seed_preempt(db, *, waited_s=600):
    with db.session() as s:
        running = Job(agent="learn", job_type="learn.scan", status=JobStatus.RUNNING,
                      inputs={}, started_at=NOW - timedelta(minutes=10))
        s.add(running)
        created = NOW - timedelta(seconds=waited_s)
        s.add(Job(agent="support", job_type="support.reply", status=JobStatus.PENDING,
                  inputs={}, created_at=created, run_after=created))
        s.flush()
        return running.id


def test_preemption_wanted_only_behind_a_full_pool_for_better_waiting_work():
    db = _db()
    jid = _seed_preempt(db)
    with db.session() as s:
        job = s.get(Job, jid)
    want = preempt.preemption_wanted(db, job, worker_target=1, now=NOW)
    assert want and want["job_type"] == "support.reply" and want["tier"] == 0, want
    assert preempt.preemption_wanted(db, job, worker_target=2, now=NOW) is None  # room
    assert preempt.preemption_wanted(db, job, worker_target=None, now=NOW) is None or \
        preempt._worker_target() is not None
    fresh = _db()
    fid = _seed_preempt(fresh, waited_s=10)
    with fresh.session() as s:
        fjob = s.get(Job, fid)
    assert preempt.preemption_wanted(fresh, fjob, worker_target=1, now=NOW) is None


def test_a_yielding_handler_is_requeued_uncounted_with_its_checkpoint():
    from brambleloop.app.runner import STATE
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker, handlers

    db = _db()
    created = NOW - timedelta(minutes=10)
    with db.session() as s:
        s.add(Job(agent="support", job_type="support.reply", status=JobStatus.PENDING,
                  inputs={}, created_at=created, run_after=NOW + timedelta(hours=1)))
    job = JobQueue(db).enqueue("learn", "learn.scan", {}, idempotency_key="swc:yield")
    seen = {}

    def handler(ctx):
        # Make the higher-band job runnable now, then ask.
        with db.session() as s:
            other = s.scalar(__import__("sqlalchemy").select(Job).where(
                Job.job_type == "support.reply"))
            other.run_after = created
        seen["want"] = ctx.should_yield(now=datetime.now(timezone.utc))
        if seen["want"]:
            ctx.yield_now(seen["want"]["why"], key="progress", state={"step": 3})
        return {"work_done": 1}

    old_handler, old_target = handlers.get("learn.scan"), STATE.worker_target
    handlers._handlers["learn.scan"] = handler
    STATE.worker_target = 1
    try:
        w = Worker(db, "w-test", job_types=["learn.scan"])
        assert w.run_once()
    finally:
        STATE.worker_target = old_target
        if old_handler is not None:
            handlers._handlers["learn.scan"] = old_handler
    assert seen["want"] and seen["want"]["job_type"] == "support.reply", seen
    assert w.stats.preempted == 1 and w.stats.failed == 0
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.PENDING and row.attempts == 0, (row.status, row.attempts)
        assert row.leased_by is None
        audit = s.scalar(__import__("sqlalchemy").select(AuditLog).where(
            AuditLog.action == preempt.PREEMPTED_ACTION))
        assert audit is not None and audit.job_id == job.id
    saved = JobQueue(db).restore(job.id, "progress")
    assert saved and saved["step"] == 3 and saved["_checkpoint"]["attempt"] == 1, saved


def test_gallery_analysis_yields_between_images():
    src = (ROOT / "src" / "brambleloop" / "runtime" / "release.py").read_text(encoding="utf-8")
    assert "should_stop=ctx.should_yield" in src and 'key="gallery_progress"' in src
    vsrc = (ROOT / "src" / "brambleloop" / "intel" / "vision.py").read_text(encoding="utf-8")
    assert 'stopped_by = "preempted"' in vsrc


# ---- F-457 -------------------------------------------------------------------------------

def test_overlapping_live_lane_manifests_are_refused_at_enrolment():
    import board as B
    import registry as R

    reg = R.Registry(Path(tempfile.mkdtemp(prefix="swc_reg_")) / "jobs.json",
                     git=lambda *a: (1, ""))
    log = Path(tempfile.mkdtemp()) / "x.log"
    reg.enrol(B.Job(name="lane-a", log=log), lane="A",
              owns=["brambleloop/src/brambleloop/swarm/", "ops/registry.py"])
    try:
        reg.enrol(B.Job(name="lane-b", log=log), lane="B",
                  owns=["brambleloop/src/brambleloop/swarm/metrics.py"])
    except R.OwnershipConflict as exc:
        assert "lane-a" in str(exc)
    else:
        raise AssertionError("an overlapping manifest was dispatched")
    reg.enrol(B.Job(name="lane-c", log=log), lane="C",
              owns=["brambleloop/src/brambleloop/swarmx/", "ops/registry_test.py"])
    reg.integrate("lane-a", "deadbeef")  # integrated: no longer live
    reg.enrol(B.Job(name="lane-b", log=log), lane="B",
              owns=["brambleloop/src/brambleloop/swarm/metrics.py"])
    assert R.paths_overlap("src/a*", "src/abc/x.py") and not R.paths_overlap("src/a", "src/ab")
    assert R.paths_overlap("*", "anything")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
