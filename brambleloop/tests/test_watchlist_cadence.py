"""ENG watchlist-cadence: a credential-gated reader resumes as soon as its credential works.

OFFLINE TEST -- NOT PRODUCTION EVIDENCE. No network, no spend, no Etsy write; every Etsy read
after the fix is a recorded fixture reader.

Production (build ea3aacc7, 2026-11-18): Etsy refused the app key from 2026-10-07 until the
owner fixed it at 2026-11-18T13:39Z. `mjs.scan` resumed on its next window; the seven other
watchlist shops (`intel.watchlist_scan`, 6-hourly) did not -- last attempted 2026-11-17T20:03Z.

Root cause reproduced here: every refused run of `intel.watchlist_scan` returned exactly the
same outputs ({"ran": False, "observed": 0, ...}; mjs.scan's refusal text carries the probe
time, so its state changed and it escaped). The hourly thrash sweep read that as an unchanged
free poll and backed the cadence off, doubling each new identical run to 32x its period
(8 days). Nothing about the owner's fix reached the backoff: it lifts only when a run shows
progress, and the scheduler would not enqueue a run. A second gate sat underneath: shops whose
own reads had been refused kept a per-shop backoff (up to 7 days) measured from the latest
refused run.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

for _k in ("ETSY_API_KEY", "ETSY_SHARED_SECRET", "ETSY_KEYSTRING", "ANTHROPIC_API_KEY"):
    os.environ.pop(_k, None)

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, Job, JobStatus, Phase, utcnow  # noqa: E402
from brambleloop.intel import benchmarks, watchlist  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import CADENCES, Scheduler, Worker  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402

import test_w4_intelrec_watchlist as intelrec  # noqa: E402 - the recorded fixture reader

SCAN = "intel.watchlist_scan"
PERIOD = next(p for _n, _a, jt, p in CADENCES if jt == SCAN)


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='wlcad-')}/w.db")
    db.create_all()
    Registry(db).seed_defaults()
    benchmarks.seed(db)
    return db


def _probe(db, at, *, ok: bool):
    detail = ({"ok": True, "status": 200, "at": at.isoformat()} if ok else
              {"ok": False, "status": 403, "at": at.isoformat(),
               "reason": "ping returned HTTP 403: API key refused"})
    with db.session() as s:
        s.add(AuditLog(actor="etsy_probe", action="etsy.probe", artifact="etsy", detail=detail,
                       at=at))


def _scan_jobs(db, status=None):
    with db.session() as s:
        q = select(Job).where(Job.job_type == SCAN)
        if status is not None:
            q = q.where(Job.status == status)
        rows = list(s.scalars(q.order_by(Job.id)))
        for r in rows:
            s.expunge(r)
        return rows


def _run_pending_scan(db, at):
    """Execute any enqueued watchlist scan as the worker would, then put it on the simulated
    clock (`at`), as if it had run then."""
    pending = _scan_jobs(db, JobStatus.PENDING)
    for _ in pending:
        Worker(db, "wlcad", phase=Phase.SHADOW, job_types=[SCAN]).run_once()
    with db.session() as s:
        for j in pending:
            row = s.get(Job, j.id)
            assert row.status == JobStatus.DONE, (row.status, row.last_error)
            row.created_at = at
            row.started_at = at
            row.finished_at = at + timedelta(minutes=1)
    return len(pending)


def _simulate_refusal(db, *, days: float, end):
    """Days of the production refusal: probes refuse 6-hourly, the scheduler ticks hourly,
    the thrash sweep runs hourly, and every scan the scheduler enqueues runs."""
    os.environ["ETSY_API_KEY"] = "fixture-key-not-real"
    watchlist.reader_factory = None
    t = end - timedelta(days=days)
    ran = 0
    hour = 0
    while t < end:
        if hour % 6 == 0:
            _probe(db, t, ok=False)
        Scheduler(db).tick(now=t)
        ran += _run_pending_scan(db, t)
        orc.thrash_sweep(db, now=t + timedelta(minutes=5))
        t += timedelta(hours=1)
        hour += 1
    return ran


def _fix_and_tick(db, fixed_at):
    """The owner fixes the key: the next probe succeeds. Then the scheduler ticks once in the
    next watchlist window."""
    _probe(db, fixed_at, ok=True)
    os.environ.pop("ETSY_API_KEY", None)
    watchlist.reader_factory = intelrec.Reader
    window = fixed_at + timedelta(seconds=PERIOD - (fixed_at.timestamp() % PERIOD) + 60)
    Scheduler(db).tick(now=window)
    return window


def test_days_of_refused_runs_do_not_silence_the_scan_after_the_key_is_fixed():
    db = _db()
    end = utcnow() - timedelta(hours=8)
    try:
        ran = _simulate_refusal(db, days=4, end=end)
        assert ran >= 3, ("the refusal phase never ran the scan", ran)
        window = _fix_and_tick(db, end + timedelta(minutes=30))
        assert SCAN not in orc.suspended_job_types(db, now=window), (
            "a successful etsy.probe after refusals must lift the scan's suspension",
            orc.suspended_job_types(db, now=window).get(SCAN))
        pending = _scan_jobs(db, JobStatus.PENDING)
        assert pending, "the next cadence window did not enqueue intel.watchlist_scan"
        _run_pending_scan(db, window)
        last = _scan_jobs(db)[-1]
        assert last.outputs.get("ran") is True, last.outputs
        assert last.outputs.get("observed") == len(intelrec.SHOPS), last.outputs
    finally:
        watchlist.reader_factory = None
        os.environ.pop("ETSY_API_KEY", None)


def test_a_refused_credential_no_op_is_never_backed_off_as_a_thrashing_poll():
    db = _db()
    end = utcnow() - timedelta(hours=8)
    try:
        _simulate_refusal(db, days=3, end=end)
        out = orc.thrash_sweep(db, now=end)
        backed = [a["job_type"] for a in out["backoff"]["applied"]]
        assert SCAN not in backed, ("a CA$0 refused-credential no-op that correctly waits for "
                                    "the probe was backed off as an unchanged poll", out)
        with db.session() as s:
            assert s.scalar(select(Incident).where(
                Incident.signature == f"{orc.BACKOFF_SIGNATURE_PREFIX}{SCAN}",
                Incident.resolved.is_(False))) is None
        # every refused run was a run: the job kept attempting and saying why
        assert all(j.outputs.get("credential_refused") for j in _scan_jobs(db, JobStatus.DONE))
    finally:
        watchlist.reader_factory = None
        os.environ.pop("ETSY_API_KEY", None)


def test_a_legacy_backoff_written_before_the_fix_lifts_on_a_successful_probe():
    """Production already holds the backoff the old code wrote (no gate recorded). It must
    lift on the owner's fix too, not only backoffs written by the new code."""
    db = _db()
    t0 = utcnow() - timedelta(days=3)
    _probe(db, t0, ok=False)
    until = (t0 + timedelta(days=8)).isoformat()
    with db.session() as s:
        s.add(Incident(severity="P3", signature=f"{orc.BACKOFF_SIGNATURE_PREFIX}{SCAN}",
                       summary="legacy", at=t0 + timedelta(hours=1),
                       detail={"suspension": {"kind": orc.BACKOFF, "job_type": SCAN,
                                              "level": 5, "factor": 32,
                                              "suspend_until": until}}))
    _probe(db, t0 + timedelta(days=1), ok=False)
    now = t0 + timedelta(days=2)
    assert SCAN in orc.suspended_job_types(db, now=now), "precondition: the backoff stands"
    _probe(db, now, ok=True)
    assert SCAN not in orc.suspended_job_types(db, now=now + timedelta(minutes=1))
    # a backoff for a job type no credential gates is untouched by the probe
    with db.session() as s:
        s.add(Incident(severity="P3",
                       signature=f"{orc.BACKOFF_SIGNATURE_PREFIX}intel.watchlist_compare",
                       summary="x", at=t0,
                       detail={"suspension": {"kind": orc.BACKOFF,
                                              "job_type": "intel.watchlist_compare",
                                              "level": 1, "factor": 2,
                                              "suspend_until": until}}))
    assert "intel.watchlist_compare" in orc.suspended_job_types(
        db, now=now + timedelta(minutes=2))


LEGACY_REFUSED_OUTPUTS = {"ran": False, "observed": 0, "outages": 0, "network_calls": None,
                          "work_done": 0}       # what build ea3aacc7 returned, unmarked


def _legacy_runs(db, at, n=3):
    with db.session() as s:
        rows = [Job(agent="market_radar", job_type=SCAN, inputs={"cadence": "watchlist_scan"},
                    status=JobStatus.DONE, outputs=dict(LEGACY_REFUSED_OUTPUTS), cost_cad=0.0,
                    created_at=at + timedelta(hours=6 * i), started_at=at + timedelta(hours=6 * i),
                    finished_at=at + timedelta(hours=6 * i, minutes=1)) for i in range(n)]
        s.add_all(rows)
        s.flush()
        return rows[-1].id


def test_the_hourly_sweep_does_not_rearm_a_lifted_legacy_backoff_before_the_scan_runs():
    """After the deploy, the 72 h window still holds the old build's unmarked refused runs.
    The hourly sweep must neither raise the standing backoff's level nor, with none open,
    write a fresh one from them once the probe has succeeded."""
    db = _db()
    now = utcnow()
    t0 = now - timedelta(hours=30)
    _probe(db, t0 - timedelta(hours=1), ok=False)
    last_id = _legacy_runs(db, t0)
    with db.session() as s:
        s.add(Incident(severity="P3", signature=f"{orc.BACKOFF_SIGNATURE_PREFIX}{SCAN}",
                       summary="legacy", at=t0,
                       detail={"suspension": {"kind": orc.BACKOFF, "job_type": SCAN,
                                              "level": 5, "factor": 32,
                                              "suspend_until": (now + timedelta(days=6))
                                              .isoformat(),
                                              "last_counted_job_id": last_id - 1}}))
    _probe(db, now - timedelta(hours=2), ok=True)
    out = orc.thrash_sweep(db, now=now)
    assert SCAN not in out["suspended"], out["backoff"]
    assert SCAN not in [a["job_type"] for a in out["backoff"]["applied"]], out["backoff"]
    # and with no backoff open at all, the same window writes none
    with db.session() as s:
        for inc in s.scalars(select(Incident).where(Incident.signature.like("thrash:%"))):
            inc.resolved = True
    out = orc.thrash_sweep(db, now=now + timedelta(minutes=5))
    assert SCAN not in out["suspended"], out["backoff"]
    # control: the same unchanged runs with the key STILL refused do back off (the old rule
    # stands for anything the gate does not explain)
    db2 = _db()
    _probe(db2, t0 - timedelta(hours=1), ok=False)
    _legacy_runs(db2, t0)
    out = orc.thrash_sweep(db2, now=now)
    assert SCAN in out["suspended"], out["backoff"]


def test_a_paid_loop_on_a_gated_job_type_still_trips_and_stays_suspended():
    """The breaker is kept for real spend loops: a probe success is no changed hypothesis for
    a loop that spent money returning the same answer."""
    db = _db()
    now = utcnow()
    with db.session() as s:
        for i in range(3):
            s.add(Job(agent="market_radar", job_type="mjs.scan",
                      inputs={"cadence": "mjs_scan"}, status=JobStatus.DONE,
                      outputs={"same": 1}, cost_cad=0.25,
                      started_at=now - timedelta(minutes=30 - i),
                      finished_at=now - timedelta(minutes=20 - i)))
    _probe(db, now - timedelta(hours=1), ok=True)
    out = orc.thrash_sweep(db, now=now)
    assert out["tripped"] == 1 and "mjs.scan" in out["suspended"], out
    _probe(db, now + timedelta(minutes=1), ok=True)
    assert "mjs.scan" in orc.suspended_job_types(db, now=now + timedelta(minutes=2))


def test_shop_backoff_from_refused_reads_lifts_once_a_probe_succeeds():
    """A shop whose own reads Etsy refused (consecutive_failures, state credential_refused)
    is read on the first run after a successful probe, not after its per-shop backoff."""
    db = _db()
    now = utcnow()
    key = "zkbdesigner"
    watchlist._save_state(db, key, {"state": "credential_refused", "consecutive_failures": 6,
                                    "last_attempt_at": (now - timedelta(hours=2)).isoformat()},
                          now=now - timedelta(hours=2))
    _probe(db, now - timedelta(hours=1), ok=True)
    calls: list = []
    m = watchlist.BY_KEY[key]
    got = watchlist.scan_member(db, m, intelrec.Reader(calls=calls), now=now)
    assert got.get("ran") is True, got
    # a source outage keeps its backoff: the probe says nothing about the source being up
    watchlist._save_state(db, "the_easy_design",
                          {"state": "source_outage", "consecutive_failures": 6,
                           "last_attempt_at": (now - timedelta(hours=2)).isoformat()},
                          now=now - timedelta(hours=2))
    got = watchlist.scan_member(db, watchlist.BY_KEY["the_easy_design"],
                                intelrec.Reader(), now=now)
    assert got.get("deferred") is True, got


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
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
