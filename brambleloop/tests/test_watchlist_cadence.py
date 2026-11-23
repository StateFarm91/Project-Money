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


def _uncapped(fn):
    """BACKOFF-CAP (19i19): run a test under the old 32x backoff (no min(4x period, 6 h)
    cap), so the multi-day legacy park it builds still stands and the lift it is about is
    proved on its own, independent of the cap that now also ends such a park."""
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **k):
        saved = (orc.BACKOFF_CAP_PERIODS, orc.BACKOFF_CAP_SECONDS, orc.MAX_BACKOFF_FACTOR)
        orc.BACKOFF_CAP_PERIODS, orc.BACKOFF_CAP_SECONDS, orc.MAX_BACKOFF_FACTOR = \
            10 ** 6, 10 ** 12, 32
        try:
            return fn(*a, **k)
        finally:
            orc.BACKOFF_CAP_PERIODS, orc.BACKOFF_CAP_SECONDS, orc.MAX_BACKOFF_FACTOR = saved
    return wrapper


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


@_uncapped
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


NON_ANCHOR = [m for m in watchlist.WATCHLIST if m.role != watchlist.ANCHOR]


def _production_silence(db, now):
    """Production at 15:10Z on 11-18 as it stood: the old build's standing backoff on the
    scan (recorded while the key was refused), the seven shops last attempted ~19 h ago."""
    t_ref = now - timedelta(days=40)
    _probe(db, t_ref, ok=False)
    last = now - timedelta(hours=19)
    with db.session() as s:
        s.add(Incident(severity="P3", signature=f"{orc.BACKOFF_SIGNATURE_PREFIX}{SCAN}",
                       summary="legacy", at=t_ref + timedelta(hours=1),
                       detail={"suspension": {"kind": orc.BACKOFF, "job_type": SCAN,
                                              "level": 5, "factor": 32,
                                              "suspend_until": (last + timedelta(days=8))
                                              .isoformat()}}))
        s.add(Job(agent="market_radar", job_type=SCAN, inputs={"cadence": "watchlist_scan"},
                  idempotency_key="cadence:watchlist_scan:legacy", status=JobStatus.DONE,
                  outputs=dict(LEGACY_REFUSED_OUTPUTS), created_at=last, started_at=last,
                  finished_at=last))
    for m in NON_ANCHOR:
        watchlist._save_state(db, m.key, {"state": "credential_refused",
                                          "last_attempt_at": last.isoformat()}, now=last)


@_uncapped
def test_the_readback_names_the_scheduler_hold_and_each_shop_says_why():
    from brambleloop.ops import production_evidence as PE

    db = _db()
    now = utcnow()
    _production_silence(db, now)
    ev = PE.evidence(db, now=now)
    sched = ev["scheduler"]
    assert sched.get("readable") is True, sched
    held = {r["job_type"]: r for r in sched["suspended_job_types"]}
    assert held[SCAN]["kind"] == orc.BACKOFF and held[SCAN]["until"] \
        and held[SCAN]["incident"].startswith("thrash:backoff:"), held
    row = next(c for c in sched["cadences"] if c["job_type"] == SCAN)
    assert row["skipped_because"] == "suspended", row
    assert row["last_enqueued_at"] and row["next_window_at"], row
    assert sched["blocked_departments"] == [], sched["blocked_departments"]
    silent = {r["alias"] for r in sched["unattempted_mandatory_shops"]}
    assert len(silent) == len(NON_ANCHOR), sched["unattempted_mandatory_shops"]
    shops = [r for r in ev["competitor_scans"]["shops"] if r["role"] != "anchor"]
    assert shops, ev["competitor_scans"]
    for r in shops:
        why = r.get("not_attempted_because") or {}
        assert why.get("code") == "scheduler_backoff", r
        assert why.get("until") and why.get("incident"), why
    # no shop name leaves on the read-only route
    blob = repr(ev)
    for m in watchlist.WATCHLIST:
        assert m.shop_name not in blob, m.shop_name


@_uncapped
def test_a_mandatory_shop_silent_for_twice_its_cadence_raises_a_p1_naming_the_cause():
    from brambleloop.ops import scheduler_readback as SR

    db = _db()
    now = utcnow()
    _production_silence(db, now)
    SR._LAST_ESCALATION.clear()
    Scheduler(db).tick(now=now)
    with db.session() as s:
        rows = list(s.scalars(select(Incident).where(
            Incident.signature.like(f"{SR.INCIDENT_PREFIX}%"), Incident.resolved.is_(False))))
        assert len(rows) == len(NON_ANCHOR), [r.signature for r in rows]
        for r in rows:
            assert r.severity == "P1"
            assert r.detail["cause"]["code"] == "scheduler_backoff", r.detail
            assert "scheduler_backoff" in r.summary and SCAN in r.summary, r.summary
    # the owner's fix: the probe succeeds; the hold lifts, the scan is enqueued and runs,
    # every shop is attempted, and the escalation resolves itself with the reason.
    _probe(db, now + timedelta(minutes=1), ok=True)
    watchlist.reader_factory = intelrec.Reader
    try:
        later = now + timedelta(minutes=20)
        Scheduler(db).tick(now=later)
        assert _scan_jobs(db, JobStatus.PENDING), "the lifted scan was not enqueued"
        _run_pending_scan(db, later)
        got = SR.escalate_unattempted(db, now=later + timedelta(minutes=5))
    finally:
        watchlist.reader_factory = None
    assert not got["raised"] and len(got["resolved"]) == len(NON_ANCHOR), got
    # an adaptive-interval deferral is the scanner working: never escalated
    assert "adaptive_not_due" in SR.LEGITIMATE_CAUSES


def _run_cadence(db, job_type, *, days, end, step_hours=1):
    """Tick hourly and execute `job_type` whenever its cadence enqueues it (no new input)."""
    t = end - timedelta(days=days)
    while t < end:
        Scheduler(db).tick(now=t)
        with db.session() as s:
            pend = [j.id for j in s.scalars(select(Job).where(
                Job.job_type == job_type, Job.status == JobStatus.PENDING))]
        for _ in pend:
            Worker(db, "wlcad", phase=Phase.SHADOW, job_types=[job_type]).run_once()
        with db.session() as s:
            for i in pend:
                r = s.get(Job, i)
                assert r.status == JobStatus.DONE, (job_type, r.status, r.last_error)
                r.created_at = r.started_at = t
                r.finished_at = t + timedelta(minutes=1)
        orc.thrash_sweep(db, now=t + timedelta(minutes=5))
        t += timedelta(hours=step_hours)


def _upstream_done(db, job_type, outputs, at):
    with db.session() as s:
        s.add(Job(agent="market_radar", job_type=job_type, inputs={}, status=JobStatus.DONE,
                  outputs=outputs, created_at=at, started_at=at, finished_at=at))


def test_concept_intake_and_compare_backoffs_lift_when_their_input_changes():
    """Task 4. Same department and cadence family: CA$0, no credential, but each reads only
    other jobs' output. With no new input their runs are identical and back off (reproduced:
    concept_intake at 4x within days); the backoff must lift once the input changes -- an
    answered research task for intake, a real watchlist scan for the comparison -- not
    outlast it by up to 32 periods."""
    db = _db()
    end = utcnow() - timedelta(hours=3)
    _run_cadence(db, "radar.concept_intake", days=5, end=end)
    held = orc.suspended_job_types(db, now=end)
    assert held.get("radar.concept_intake", {}).get("kind") == orc.BACKOFF, (
        "precondition: unchanged intake runs back off", held)
    # a fresh comparison is NOT new input for intake (it reports work_done=1 every run)
    _upstream_done(db, "intel.watchlist_compare", {"shops": 8, "work_done": 1},
                   end + timedelta(minutes=10))
    assert "radar.concept_intake" in orc.suspended_job_types(
        db, now=end + timedelta(minutes=11))
    # an answered research task is
    _upstream_done(db, "research.investigate", {"ran": True, "work_done": 1},
                   end + timedelta(minutes=20))
    assert "radar.concept_intake" not in orc.suspended_job_types(
        db, now=end + timedelta(minutes=21))
    Scheduler(db).tick(now=end + timedelta(minutes=22))
    with db.session() as s:
        assert s.scalar(select(Job).where(Job.job_type == "radar.concept_intake",
                                          Job.status == JobStatus.PENDING)), \
            "intake was not enqueued after its input changed"
    # the hourly sweep does not re-arm it from the pre-input observations
    out = orc.thrash_sweep(db, now=end + timedelta(minutes=25))
    assert "radar.concept_intake" not in out["suspended"], out["backoff"]

    # the comparison: a backoff (as written by the sweep) lifts on a real scan of the shops,
    # not on a refused no-op or a run that observed nothing
    t = end
    with db.session() as s:
        s.add(Incident(severity="P3",
                       signature=f"{orc.BACKOFF_SIGNATURE_PREFIX}intel.watchlist_compare",
                       summary="x", at=t, detail={"suspension": {
                           "kind": orc.BACKOFF, "job_type": "intel.watchlist_compare",
                           "level": 3, "factor": 8, "since": t.isoformat(),
                           "suspend_until": (t + timedelta(days=8)).isoformat()}}))
    _upstream_done(db, SCAN, {"ran": False, "credential_refused": True, "work_done": 0},
                   t + timedelta(hours=1))
    _upstream_done(db, SCAN, {"ran": True, "observed": 0, "work_done": 0},
                   t + timedelta(hours=2))
    assert "intel.watchlist_compare" in orc.suspended_job_types(db, now=t + timedelta(hours=3))
    _upstream_done(db, SCAN, {"ran": True, "observed": 7, "work_done": 7},
                   t + timedelta(hours=4))
    assert "intel.watchlist_compare" not in orc.suspended_job_types(
        db, now=t + timedelta(hours=5))
    for jt in ("intel.watchlist_compare", "radar.concept_intake"):
        assert orc.gate_of(jt) is None      # no credential gate: never a gated no-op


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


# --- Review round 2 (of 77795758) -------------------------------------------------------

REFUSED_ERROR = "EtsyAuthError: ping returned HTTP 403: API key refused"


def _dead_mjs(db, at, n=3):
    """`n` DEAD mjs.scan jobs whose final error is the refused key, one per 2 h before `at`."""
    with db.session() as s:
        for i in range(n):
            t = at - timedelta(hours=2 * (n - i))
            s.add(Job(agent="market_radar", job_type="mjs.scan",
                      inputs={"cadence": "mjs_scan"}, status=JobStatus.DEAD,
                      last_error=REFUSED_ERROR, cost_cad=0.0,
                      created_at=t, started_at=t, finished_at=t + timedelta(minutes=1)))


def test_a_breaker_suspension_lifted_by_the_probe_is_not_rewritten_by_the_next_sweep():
    """Review A. The breaker trips on DEAD runs that failed on the refused key; the owner's fix
    (an OK probe) lifts it. The next hourly sweep still sees the same DEAD runs in its 72 h
    window: it must not re-suspend the job type on them (on 77795758 it rewrote the
    suspension with since=now and gate_refused=False, refusing the lift for good)."""
    db = _db()
    t0 = utcnow() - timedelta(hours=10)
    _probe(db, t0 - timedelta(hours=12), ok=False)
    _dead_mjs(db, t0)
    out = orc.thrash_sweep(db, now=t0)
    assert out["tripped"] == 1 and "mjs.scan" in out["suspended"], out
    fixed = t0 + timedelta(minutes=30)
    _probe(db, fixed, ok=True)
    assert "mjs.scan" not in orc.suspended_job_types(db, now=fixed + timedelta(minutes=1))
    for h in (1, 2, 5):
        out = orc.thrash_sweep(db, now=t0 + timedelta(hours=h))
        assert "mjs.scan" not in out["suspended"], (h, out)
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature.like(f"{orc.THRASH_SIGNATURE_PREFIX}mjs.scan:%"),
            Incident.resolved.is_(False)))
        sus = inc.detail["suspension"]
        assert sus["gate_refused"] is True and sus["since"] == t0.isoformat(), sus
    # 80 h later the trips have left the window; the lift still holds
    later = t0 + timedelta(hours=80)
    assert "mjs.scan" not in orc.thrash_sweep(db, now=later)["suspended"]
    assert "mjs.scan" not in orc.suspended_job_types(db, now=later)


def test_the_same_loop_after_the_fix_still_trips_the_breaker():
    """Control for review A: three new DEAD runs *after* the OK probe are a loop with a working
    key. They trip the breaker and that suspension does not lift on later OK probes."""
    db = _db()
    t0 = utcnow() - timedelta(hours=20)
    _probe(db, t0 - timedelta(hours=12), ok=False)
    _dead_mjs(db, t0)
    orc.thrash_sweep(db, now=t0)
    _probe(db, t0 + timedelta(minutes=30), ok=True)
    _dead_mjs(db, t0 + timedelta(hours=8))          # 3 more, all after the fix
    out = orc.thrash_sweep(db, now=t0 + timedelta(hours=8))
    assert "mjs.scan" in out["suspended"], out
    _probe(db, t0 + timedelta(hours=9), ok=True)    # a routine OK probe is no changed gate
    assert "mjs.scan" in orc.suspended_job_types(db, now=t0 + timedelta(hours=10))


def _legacy_backoff(db, at, *, job_type=SCAN):
    """A backoff as the old build wrote it: no gate recorded, judged by the probe in force."""
    with db.session() as s:
        s.add(Incident(severity="P3", signature=f"{orc.BACKOFF_SIGNATURE_PREFIX}{job_type}",
                       summary="legacy", at=at,
                       detail={"suspension": {"kind": orc.BACKOFF, "job_type": job_type,
                                              "level": 5, "factor": 32,
                                              "suspend_until": (at + timedelta(days=8))
                                              .isoformat()}}))


@_uncapped
def test_only_a_genuine_gate_change_lifts_a_backoff():
    """Review B (kills M2: dropping 'the probe in force then was refused'). The lift is the
    credential changing, not the 6-hourly probe clock: OK->OK and refused->refused must not
    lift; refused->OK must."""
    now = utcnow()
    t0 = now - timedelta(days=2)
    cases = {  # probes before the backoff, probes after it -> lifted?
        "ok->ok": ([True], [True, True], False),
        "refused->refused": ([False], [False], False),
        "refused->ok": ([False], [True], True),
        "ok->refused->ok": ([True], [False, True], False),
        "no probe then->ok": ([], [True], False),
    }
    for name, (before, after, lifts) in cases.items():
        db = _db()
        for i, ok in enumerate(before):
            _probe(db, t0 - timedelta(hours=6 * (len(before) - i)), ok=ok)
        _legacy_backoff(db, t0)
        for i, ok in enumerate(after):
            _probe(db, t0 + timedelta(hours=6 * (i + 1)), ok=ok)
        held = SCAN in orc.suspended_job_types(db, now=now)
        assert held is (not lifts), (name, "lifted" if not held else "held")
        with db.session() as s:
            got = orc.gate_changed_since(s, orc.ETSY_GATE, t0)
        assert bool(got) is lifts, (name, got)
    # (kills M3) the newest-written probe is an OK row stamped *before* the backoff (a
    # backfilled or clock-skewed write) while a refusal was in force at the backoff: an OK
    # from before the backoff is no change after it.
    db = _db()
    _probe(db, t0 - timedelta(hours=1), ok=False)
    _legacy_backoff(db, t0)
    _probe(db, t0 - timedelta(hours=3), ok=True)
    assert SCAN in orc.suspended_job_types(db, now=now)
    with db.session() as s:
        assert orc.gate_changed_since(s, orc.ETSY_GATE, t0) is None


def test_the_sweep_still_backs_off_an_unchanged_poll_across_routine_ok_probes():
    """Review B, the sweep's side of M2: identical (non-gated) runs of a gated job type while
    the key works are a poll without progress. A routine OK probe after them is no changed
    input, so the sweep must still back them off."""
    db = _db()
    now = utcnow()
    t0 = now - timedelta(hours=30)
    _probe(db, t0 - timedelta(hours=1), ok=True)
    with db.session() as s:
        for i in range(3):
            at = t0 + timedelta(hours=6 * i)
            s.add(Job(agent="market_radar", job_type=SCAN, inputs={"cadence": "watchlist_scan"},
                      status=JobStatus.DONE, cost_cad=0.0,
                      outputs={"ran": True, "observed": 0, "outages": 0, "work_done": 0},
                      created_at=at, started_at=at, finished_at=at + timedelta(minutes=1)))
    _probe(db, now - timedelta(hours=1), ok=True)
    out = orc.thrash_sweep(db, now=now)
    assert SCAN in [a["job_type"] for a in out["backoff"]["applied"]], out["backoff"]
    assert SCAN in out["suspended"], out


def test_production_magnitude_32x_backoff_driven_by_the_sweep_lifts_and_cadence_resumes():
    """Review LOW: the reproduction reached factor 2. Here the hourly sweep itself carries the
    old build's standing backoff to production's level 5 (32x, eight 6 h periods), the
    owner fixes the key, and the scan is enqueued in the very next window, reads every shop,
    and keeps its 6-hourly cadence for a day with the hourly sweep running."""
    db = _db()
    now = utcnow() - timedelta(days=2)
    t0 = now - timedelta(hours=30)
    _probe(db, t0 - timedelta(hours=1), ok=False)
    last_id = _legacy_runs(db, t0)                 # the old build's unmarked refused runs
    with db.session() as s:
        s.add(Incident(severity="P3", signature=f"{orc.BACKOFF_SIGNATURE_PREFIX}{SCAN}",
                       summary="legacy", at=t0,
                       detail={"suspension": {"kind": orc.BACKOFF, "job_type": SCAN,
                                              "level": 4, "factor": 16,
                                              "suspend_until": (t0 + timedelta(days=4))
                                              .isoformat(),
                                              "last_counted_job_id": last_id - 1}}))
    out = orc.thrash_sweep(db, now=now)            # key still refused: level 4 -> 5
    hold = orc.suspended_job_types(db, now=now)[SCAN]
    # BACKOFF-CAP (19i19): the level still climbs, but the park is capped at
    # min(4x period, 6 h) -- it used to reach 32x (eight days for this 6-hourly scan).
    assert hold["factor"] == orc.MAX_BACKOFF_FACTOR == 4, (hold, out["backoff"])
    assert hold["until"] <= (now + timedelta(seconds=orc.backoff_cap_seconds(SCAN))
                             ).isoformat(), hold
    try:
        window = _fix_and_tick(db, now + timedelta(minutes=30))
        assert SCAN not in orc.suspended_job_types(db, now=window)
        assert _scan_jobs(db, JobStatus.PENDING), "the scan was not enqueued after the fix"
        _run_pending_scan(db, window)
        last = _scan_jobs(db)[-1]
        assert last.outputs.get("ran") is True and \
            last.outputs.get("observed") == len(intelrec.SHOPS), last.outputs
        # a day of hourly ticks and sweeps: every 6 h window enqueues and runs the scan
        runs = 0
        t = window + timedelta(hours=1)
        while t < window + timedelta(hours=24):
            Scheduler(db).tick(now=t)
            runs += _run_pending_scan(db, t)
            assert SCAN not in orc.thrash_sweep(db, now=t + timedelta(minutes=5))["suspended"]
            t += timedelta(hours=1)
        assert runs >= 24 * 3600 // PERIOD - 1, runs
    finally:
        watchlist.reader_factory = None
        os.environ.pop("ETSY_API_KEY", None)


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
