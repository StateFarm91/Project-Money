"""Adversarial certification: orchestration (queue, worker, leases, watchdog, incidents).

Each test tries to falsify one claim the orchestration layer makes about itself. A failing
test here is a finding, not a flaky test: assertions are the contract as documented in the
module docstrings, and they are not weakened to get green.

Every database is a temporary SQLite *file* (WAL), because several tests use threads or a
second process and an in-memory database is per-connection.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Agent, AuditLog, Job, JobStatus, utcnow  # noqa: E402
from brambleloop.queue.durable import (  # noqa: E402
    DuplicateJob, JobQueue, deliberate_refusal,
)
from brambleloop.runtime.worker import (  # noqa: E402
    CapabilityNotEnabled, HandlerRegistry, JobContext, Worker, _LeaseRenewal,
)

AGENT = "orchestrator"


def _db(name: str = "q.sqlite") -> tuple[Database, str]:
    tmp = tempfile.mkdtemp(prefix="cert_orch_")
    url = f"sqlite:///{tmp}/{name}"
    db = Database(url)
    db.create_all()
    Registry(db).seed_defaults()
    return db, url


def _allow(db: Database, *job_types: str, agent: str = AGENT) -> None:
    with db.session() as s:
        a = s.scalar(select(Agent).where(Agent.name == agent))
        a.allowed_job_types = list(a.allowed_job_types or []) + list(job_types)


def _expire(db: Database, job_id: int) -> None:
    with db.session() as s:
        s.get(Job, job_id).lease_expires_at = utcnow() - timedelta(seconds=5)


def _job(db: Database, job_id: int) -> Job:
    return JobQueue(db).get(job_id)


def _audits(db: Database, action: str) -> int:
    with db.session() as s:
        return s.scalar(select(func.count()).select_from(AuditLog)
                        .where(AuditLog.action == action)) or 0


# ---- leases ---------------------------------------------------------------------------------


def test_lease_is_exclusive_while_live():
    db, _ = _db()
    q = JobQueue(db)
    j = q.enqueue(AGENT, "cert.x")
    a = q.claim("A")
    assert a.id == j.id and a.leased_by == "A" and a.attempts == 1
    assert q.claim("B") is None, "a live lease was handed to a second worker"


def test_expired_lease_is_reclaimed_ahead_of_pending_backlog():
    db, _ = _db()
    q = JobQueue(db)
    orphan = q.enqueue(AGENT, "cert.x", priority=100)
    q.claim("A")
    for _ in range(5):
        q.enqueue(AGENT, "cert.x", priority=10)      # a higher-band backlog
    _expire(db, orphan.id)
    b = q.claim("B")
    assert b.id == orphan.id, "the orphan was not reclaimed first under a backlog"
    assert b.leased_by == "B" and b.attempts == 2


def test_stale_complete_and_fail_are_refused_and_new_holder_result_survives():
    db, _ = _db()
    q = JobQueue(db)
    j = q.enqueue(AGENT, "cert.x")
    q.claim("A")
    _expire(db, j.id)
    q.claim("B")
    assert q.complete(j.id, {"by": "A"}, worker="A") is False
    assert q.fail(j.id, "A blew up", worker="A") is None
    assert _job(db, j.id).status == JobStatus.RUNNING and _job(db, j.id).leased_by == "B"
    assert q.complete(j.id, {"by": "B"}, worker="B") is True
    # A late report after B finished is refused too, and B's result stays.
    assert q.complete(j.id, {"by": "A"}, worker="A") is False
    assert q.fail(j.id, "A late", retry=False, worker="A") is None
    row = _job(db, j.id)
    assert row.status == JobStatus.DONE and row.outputs == {"by": "B"}
    assert _audits(db, "queue.stale_lease_refused") == 4


def test_worker_none_cannot_overwrite_a_job_somebody_holds_a_live_lease_on():
    """`worker=None` is documented as the path for 'a job nobody is running'. A job held on a
    live lease IS being run, so the unfenced path must not apply to it."""
    db, _ = _db()
    q = JobQueue(db)
    j = q.enqueue(AGENT, "cert.x")
    q.claim("A")
    _expire(db, j.id)
    q.claim("B")                                    # B holds a live lease now
    applied = q.complete(j.id, {"by": "stale-A-without-name"})   # worker=None
    row = _job(db, j.id)
    assert applied is False and row.status == JobStatus.RUNNING and row.leased_by == "B", (
        f"worker=None overwrote a live lease held by B: applied={applied}, "
        f"status={row.status}, outputs={row.outputs}")


def test_stale_heartbeat_does_not_extend_the_new_holders_lease():
    """A stale worker (or its renewal thread) heartbeating must not keep somebody else's job
    alive: if B then dies, A's renewals make B's orphan unreclaimable for up to an hour."""
    db, _ = _db()
    q = JobQueue(db, lease_seconds=300)
    j = q.enqueue(AGENT, "cert.x")
    stale = q.claim("A")
    _expire(db, j.id)
    q.claim("B")
    _expire(db, j.id)                               # B has now died holding it
    ctx = JobContext(job=stale, db=db, queue=q, registry=Registry(db), phase=None)
    ctx.heartbeat()                                 # A's renewal thread, still ticking
    exp = _job(db, j.id).lease_expires_at
    exp = exp if exp.tzinfo else exp.replace(tzinfo=utcnow().tzinfo)
    assert exp <= utcnow(), (
        "JobQueue.heartbeat is unfenced: stale worker A extended the lease on a job B holds "
        f"(expires {exp.isoformat()}), so B's orphan cannot be reclaimed")


def test_renewal_keeps_a_long_handler_lease_and_nobody_steals_it():
    db, _ = _db()
    _allow(db, "cert.long")
    reg = HandlerRegistry()
    runs = Counter()

    @reg.register("cert.long")
    def _long(ctx):
        runs[ctx.job.id] += 1
        time.sleep(4.5)                             # 1.5x the lease
        return {"ok": True}

    q = JobQueue(db, lease_seconds=3)
    j = q.enqueue(AGENT, "cert.long")
    w = Worker(db, "long-1", registry=reg, lease_seconds=3)
    t = threading.Thread(target=w.run_once)
    t.start()
    stolen = []
    deadline = time.monotonic() + 5.5
    while t.is_alive() and time.monotonic() < deadline:
        got = JobQueue(db, lease_seconds=3).claim("thief", ["cert.long"])
        if got is not None:
            stolen.append(got.id)
        time.sleep(0.3)
    t.join()
    assert not stolen, f"a renewed lease was reclaimed mid-handler: {stolen}"
    assert runs[j.id] == 1 and _job(db, j.id).status == JobStatus.DONE
    assert w.stats.completed == 1


def test_renewal_cap_stops_renewing_so_a_hung_handler_becomes_reclaimable():
    db, _ = _db()
    q = JobQueue(db, lease_seconds=3)               # interval 1s
    j = q.enqueue(AGENT, "cert.x")
    q.claim("A")
    r = _LeaseRenewal(q, j.id, cap_seconds=2)
    r.start()
    time.sleep(6.5)                                 # cap + a full lease
    renewals = r.renewals
    r.stop()
    assert 1 <= renewals <= 2, f"renewal cap not honoured: {renewals} renewals"
    got = JobQueue(db, lease_seconds=3).claim("B")
    assert got is not None and got.id == j.id, "capped renewal left the job unreclaimable"


# ---- concurrency ------------------------------------------------------------------------------


def _hammer(n_jobs: int, n_workers: int) -> tuple[Counter, list, dict]:
    db, _ = _db()
    _allow(db, "cert.count")
    reg = HandlerRegistry()
    executions: Counter = Counter()
    lock = threading.Lock()

    @reg.register("cert.count")
    def _count(ctx):
        with lock:
            executions[ctx.job.id] += 1
        return {}

    q = JobQueue(db)
    for i in range(n_jobs):
        q.enqueue(AGENT, "cert.count", {"i": i})
    errors: list = []
    barrier = threading.Barrier(n_workers)

    def run(k):
        w = Worker(db, f"w{k}", registry=reg)
        barrier.wait()
        while True:
            try:
                if not w.run_once():
                    return
            except Exception as e:  # noqa: BLE001
                errors.append(f"{type(e).__name__}: {str(e)[:80]}")
                return

    threads = [threading.Thread(target=run, args=(k,)) for k in range(n_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return executions, errors, q.counts()


def test_concurrent_workers_never_execute_the_same_job_twice():
    executions, errors, counts = _hammer(120, 6)
    dup = {k: v for k, v in executions.items() if v > 1}
    assert not errors, f"workers crashed under contention: {errors[:3]}"
    assert not dup, (f"{len(dup)} of 120 jobs executed more than once by concurrent workers "
                     f"on SQLite (e.g. {dict(list(dup.items())[:5])}); counts={counts}")
    assert counts["done"] == 120


def test_concurrent_enqueue_with_one_idempotency_key_makes_one_row():
    db, _ = _db()
    q = JobQueue(db)
    made, dups, other = [], [], []
    barrier = threading.Barrier(8)

    def go():
        barrier.wait()
        try:
            made.append(q.enqueue(AGENT, "cert.x", idempotency_key="k:1").id)
        except DuplicateJob as e:
            dups.append(e.existing_id)
        except Exception as e:  # noqa: BLE001
            other.append(f"{type(e).__name__}: {e}")

    ts = [threading.Thread(target=go) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    with db.session() as s:
        rows = s.scalar(select(func.count()).select_from(Job)
                        .where(Job.idempotency_key == "k:1"))
    assert rows == 1 and len(made) == 1, (rows, made, dups, other)
    assert not other, other


# ---- retries, dead letters, refusals ---------------------------------------------------------


def test_retries_back_off_exponentially_then_dead_letter():
    db, _ = _db()
    _allow(db, "cert.flaky")
    reg = HandlerRegistry()

    @reg.register("cert.flaky")
    def _flaky(ctx):
        raise RuntimeError("provider 500")

    q = JobQueue(db)
    j = q.enqueue(AGENT, "cert.flaky", max_attempts=3)
    w = Worker(db, "w", registry=reg)
    delays = []
    for attempt in (1, 2, 3):
        before = utcnow()
        assert w.run_once()
        row = _job(db, j.id)
        if attempt < 3:
            ra = row.run_after if row.run_after.tzinfo else row.run_after.replace(
                tzinfo=before.tzinfo)
            delays.append((ra - before).total_seconds())
            assert row.status == JobStatus.FAILED
            assert w.run_once() is False, "a backed-off job was claimable before run_after"
            with db.session() as s:
                s.get(Job, j.id).run_after = utcnow() - timedelta(seconds=1)
    row = _job(db, j.id)
    assert row.status == JobStatus.DEAD and row.attempts == 3
    assert 1.5 <= delays[0] <= 2.5 and 3.1 <= delays[1] <= 4.9, delays


def test_deliberate_refusal_is_dead_lettered_once_and_never_redriven():
    db, _ = _db()
    _allow(db, "etsy.publish_listing", "cert.flaky")
    reg = HandlerRegistry()

    @reg.register("etsy.publish_listing")
    def _pub(ctx):
        raise CapabilityNotEnabled("shadow mode: publication is not promoted")

    @reg.register("cert.flaky")
    def _flaky(ctx):
        raise RuntimeError("bug")

    q = JobQueue(db)
    refused = q.enqueue(AGENT, "etsy.publish_listing", max_attempts=5)
    broken = q.enqueue(AGENT, "cert.flaky", max_attempts=1)
    w = Worker(db, "w", registry=reg)
    w.run_once()
    w.run_once()
    r = _job(db, refused.id)
    assert r.status == JobStatus.DEAD and r.attempts == 1, "a refusal was retried"
    out = q.requeue_dead()
    assert broken.id in out["requeued"] and refused.id not in out["requeued"]
    assert _job(db, refused.id).status == JobStatus.DEAD


def test_the_two_refusal_classifiers_agree_on_a_capability_refusal():
    """health.py and retention.py ask `deliberate_refusal`; requeue_dead asks
    REFUSAL_MARKERS. For the Worker's own CapabilityNotEnabled dead letter on any job type
    other than store.publish they must give the same answer."""
    err = "capability not enabled: shadow mode: publication is not promoted"
    redrivable = not any(m in err.lower() for m in JobQueue.REFUSAL_MARKERS)
    assert redrivable is False
    assert deliberate_refusal("etsy.publish_listing", err) is True, (
        "a CapabilityNotEnabled dead letter is refused-on-purpose for requeue_dead but "
        "classified as a DEFECT by deliberate_refusal (ops.health dead_letters backlog, "
        "retention never prunes it, verify reports it)")


def test_permission_denied_is_terminal_not_retried():
    db, _ = _db()
    reg = HandlerRegistry()
    reg.register("cert.forbidden")(lambda ctx: {})
    q = JobQueue(db)
    j = q.enqueue(AGENT, "cert.forbidden", max_attempts=5)
    Worker(db, "w", registry=reg).run_once()
    row = _job(db, j.id)
    assert row.status == JobStatus.DEAD and row.attempts == 1 and "permission denied" in (
        row.last_error or "")


# ---- crash / restart ---------------------------------------------------------------------------


_CHILD = r"""
import os, sys
sys.path.insert(0, {src!r})
from brambleloop.core.db import Database
from brambleloop.runtime.worker import HandlerRegistry, Worker
db = Database({url!r})
reg = HandlerRegistry()
@reg.register("cert.crash")
def h(ctx):
    with open({marker!r}, "a") as f:
        f.write("child\n"); f.flush(); os.fsync(f.fileno())
    os._exit(9)          # killed mid-handler: no complete, no fail, lease left behind
Worker(db, "child", registry=reg, lease_seconds=1).run_once()
"""


def test_crash_mid_handler_is_reclaimed_and_completed_exactly_once():
    db, url = _db()
    _allow(db, "cert.crash")
    marker = tempfile.mktemp(prefix="cert_crash_")
    j = JobQueue(db).enqueue(AGENT, "cert.crash", max_attempts=3)
    code = _CHILD.format(src=str(ROOT / "src"), url=url, marker=marker)
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          timeout=120)
    assert proc.returncode == 9, proc.stderr[-800:]
    row = _job(db, j.id)
    assert row.status == JobStatus.RUNNING and row.leased_by == "child"
    time.sleep(1.3)                                 # the child's lease lapses

    reg = HandlerRegistry()

    @reg.register("cert.crash")
    def _ok(ctx):
        with open(marker, "a") as f:
            f.write("parent\n")
        return {"recovered": True}

    w = Worker(db, "survivor", registry=reg)
    assert w.run_once()
    assert w.run_once() is False
    row = _job(db, j.id)
    assert row.status == JobStatus.DONE and row.attempts == 2
    assert row.outputs == {"recovered": True}
    assert open(marker).read().split() == ["child", "parent"]
    assert _audits(db, "job.completed:cert.crash") == 1


# ---- starvation --------------------------------------------------------------------------------


def test_a_flood_of_high_band_jobs_cannot_starve_a_low_band_job_forever():
    db, _ = _db()
    q = JobQueue(db)
    low = q.enqueue(AGENT, "cert.low", priority=200,
                    run_after=utcnow() - timedelta(days=3))     # waiting three days already
    for i in range(3):
        q.enqueue(AGENT, "cert.high", {"i": i}, priority=10)
    claimed_low_at = None
    for n in range(200):                            # steady flood: one new high per claim
        job = q.claim("w")
        q.complete(job.id, worker="w")
        if job.id == low.id:
            claimed_low_at = n
            break
        q.enqueue(AGENT, "cert.high", {"n": n}, priority=10)
    assert claimed_low_at is not None, (
        "claim order is strictly (priority, run_after, id) with no aging: a band-200 job "
        "waiting 3 days was passed over 200 times by a steady band-10 flood")


# ---- incident lifecycle -------------------------------------------------------------------------


def test_incident_lifecycle_restates_resolves_with_evidence_and_never_closes_a_true_one():
    from brambleloop.core.models import Incident
    from brambleloop.ops import incident_lifecycle as life

    db, _ = _db()
    with db.session() as s:
        _, new1 = life.open_or_restate(s, signature="seasonal.at_risk:a:xmas:2026",
                                       severity="P2", summary="a at risk")
        _, new2 = life.open_or_restate(s, signature="seasonal.at_risk:a:xmas:2026",
                                       severity="P2", summary="a at risk")
        life.open_or_restate(s, signature="seasonalXat_risk:b", severity="P2", summary="b")
    assert new1 is True and new2 is False
    with db.session() as s:
        out = life.reconcile(s, "seasonal.at_risk:", lambda r: True, resolution="gone")
    assert out["resolved"] == [] and len(out["still_open"]) == 1
    with db.session() as s:
        try:
            life.reconcile(s, "seasonal.at_risk:", lambda r: False, resolution="  ")
        except ValueError:
            pass
        else:
            raise AssertionError("resolved without evidence")
    with db.session() as s:
        out = life.reconcile(s, "seasonal.at_risk:", lambda r: False,
                             resolution="launched on time")
    # `_` in the prefix is a LIKE wildcard; the neighbour must not be touched.
    assert out["resolved"] == ["seasonal.at_risk:a:xmas:2026"], out
    with db.session() as s:
        rows = {r.signature: r for r in s.scalars(select(Incident))}
        a = rows["seasonal.at_risk:a:xmas:2026"]
        assert a.resolved and a.report_count == 3
        assert a.detail["resolution"] == "launched on time" and a.detail["resolved_at"]
        assert rows["seasonalXat_risk:b"].resolved is False


def _build_ctx(db, job_type="build.tick"):
    q = JobQueue(db)
    job = q.enqueue(AGENT, job_type, {}, idempotency_key=f"t:{job_type}:{time.time_ns()}")
    return JobContext(job=job, db=db, queue=q, registry=Registry(db), phase=None)


def _stall_open(db) -> list:
    from brambleloop.core.models import Incident

    with db.session() as s:
        return [(r.signature, r.resolved, r.report_count, (r.detail or {}).get("resolution"))
                for r in s.scalars(select(Incident).where(
                    Incident.signature == "build.stalled"))]


def _synthetic_ready(db, rid: int = 99001) -> int:
    """The shipped registry has nothing READY (everything is done or parked), so a synthetic
    requirement outside the registry is inserted; `sync` leaves rows it does not own alone."""
    from brambleloop.build2 import executor
    from brambleloop.core.models import BuildTask

    executor.sync(db)
    with db.session() as s:
        s.add(BuildTask(requirement_id=rid, title="synthetic cert task", section="cert",
                        status="missing", state=executor.READY, priority=-1.0))
    return rid


def test_watchdog_verdicts_and_build_tick_incident_lifecycle():
    from brambleloop.build2 import executor
    from brambleloop.core.models import BuildEvent, BuildTask
    from brambleloop.runtime import release  # noqa: F401 -- registers handlers
    from brambleloop.runtime.worker import handlers

    db, _ = _db()
    rid = _synthetic_ready(db)
    assert executor.queue(db)["next"]["requirement_id"] == rid
    assert executor.watchdog(db)["verdict"] == executor.AWAITING_BUILD_SESSION
    executor.claim(db, rid, worker="session-1")
    # Backdate the claim beyond the window: claimed, nothing completed -> stalled.
    old = utcnow() - timedelta(hours=executor.IDLE_ALARM_HOURS + 1)
    with db.session() as s:
        for ev in s.scalars(select(BuildEvent)):
            ev.at = old
        s.scalar(select(BuildTask).where(BuildTask.requirement_id == rid)).claimed_at = old
    health = executor.watchdog(db)
    assert health["verdict"] == executor.STALLED and health["alarm"] is True
    tick = handlers.get("build.tick")
    tick(_build_ctx(db))
    tick(_build_ctx(db))
    rows = _stall_open(db)
    assert len(rows) == 1 and rows[0][1] is False and rows[0][2] == 2, rows
    executor.complete(db, rid, worker="session-1", evidence={"suite": "42 passed"})
    tick(_build_ctx(db))
    rows = _stall_open(db)
    assert len(rows) == 1 and rows[0][1] is True and "moving" in (rows[0][3] or ""), rows


def test_executor_complete_is_fenced_to_the_claimant_and_to_claimable_states():
    from brambleloop.build2 import executor
    from brambleloop.core.models import BuildTask

    db, _ = _db()
    executor.sync(db)
    snap = executor.queue(db)
    problems = []
    parked = [rid for ids in snap["parked_by_capability"].values() for rid in ids]
    if parked:
        try:
            executor.complete(db, parked[0], worker="anyone", evidence={"x": "y"})
            problems.append(f"PARKED requirement {parked[0]} was completed without a claim")
        except executor.ExecutorRefused:
            pass
    if True:
        rid = _synthetic_ready(db)
        executor.claim(db, rid, worker="A")
        try:
            executor.complete(db, rid, worker="B", evidence={"x": "y"})
            with db.session() as s:
                st = s.scalar(select(BuildTask).where(BuildTask.requirement_id == rid)).state
            problems.append(f"B completed requirement {rid} claimed by A (state now {st})")
        except executor.ExecutorRefused:
            pass
    assert not problems, "; ".join(problems)


def test_watchdog_does_not_alarm_after_a_claim_was_honestly_released():
    from brambleloop.build2 import executor

    db, _ = _db()
    rid = _synthetic_ready(db)
    executor.claim(db, rid, worker="A")
    executor.release(db, rid, worker="A", why="out of time; nothing half-done")
    h = executor.watchdog(db)
    assert h["alarm"] is False, (
        f"nothing is held (in_progress={h.get('in_progress')}) yet the watchdog says "
        f"{h['verdict']} with alarm, because it counts claim *events* in the window")


def test_ops_health_and_seasonal_sentinel_run_clean_on_an_empty_company():
    from brambleloop.core.models import Incident
    from brambleloop.runtime import release  # noqa: F401
    from brambleloop.runtime.worker import handlers

    db, _ = _db()
    for jt in ("ops.health", "seasonal.sentinel", "ops.health"):
        out = handlers.get(jt)(_build_ctx(db, jt))
        assert isinstance(out, dict)
    with db.session() as s:
        opened = [r.signature for r in s.scalars(select(Incident))
                  if r.signature.startswith("seasonal.at_risk:")]
    assert opened == [], f"an empty catalogue raised seasonal incidents: {opened}"


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            t0 = time.monotonic()
            try:
                fn()
                print(f"OK   {name} ({time.monotonic() - t0:.1f}s)")
            except Exception as e:  # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(e).__name__}: {str(e)[:600]}")
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
