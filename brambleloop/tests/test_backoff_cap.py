"""BACKOFF-CAP (19i19): the free-poll backoff is capped at min(4x cadence period, 6 h).

Production (29b8d03a2, 2026-11-23 03:58Z): 19 job types parked by the thrash breaker's
free-poll backoff, radar.concept_pool and the assets.* photographers at 32x a daily or
6-hourly period (until December), creative.blinded at 32x a fortnight (until 2028). The
breaker exists to stop *hot* idle loops; these tests hold that it still does, that no park
outlives the cap, and that rows parked under the old cap are clamped on boot and by the sweep.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, Job, JobStatus, utcnow  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import worker as W  # noqa: E402
from brambleloop.runtime.worker import CADENCES, Scheduler  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402

HOUR = 3600
POOL = "radar.concept_pool"


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/cap.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _period(jt):
    return orc.cadence_period(jt)


def _legacy_park(db, jt, *, since, factor=32, level=5):
    """A backoff row exactly as the old 32x cap wrote it."""
    period = _period(jt)
    until = since + timedelta(seconds=period * factor)
    with db.session() as s:
        s.add(Incident(severity="P3", signature=f"{orc.BACKOFF_SIGNATURE_PREFIX}{jt}",
                       summary="legacy 32x", at=since, halts_publication=False,
                       detail={"suspension": {"kind": orc.BACKOFF, "job_type": jt,
                                              "level": level, "factor": factor,
                                              "suspend_until": until.isoformat(),
                                              "since": since.isoformat(),
                                              "last_counted_job_id": 1}}))
    return until


def _idle_runs(db, jt, n=3, *, end=None, outputs=None):
    end = end or utcnow()
    with db.session() as s:
        for i in range(n):
            at = end - timedelta(minutes=10 * (n - i))
            s.add(Job(agent="orchestrator", job_type=jt, inputs={"cadence": "c"},
                      status=JobStatus.DONE, cost_cad=0.0,
                      outputs=outputs or {"ran": True, "work_done": 0, "same": 1},
                      created_at=at, started_at=at, finished_at=at + timedelta(minutes=1)))


def test_cap_is_min_of_four_periods_and_six_hours_for_every_cadence():
    seen = set()
    for _n, _a, jt, period in CADENCES:
        if jt in seen:
            continue
        seen.add(jt)
        cap = orc.backoff_cap_seconds(jt)
        assert cap <= 6 * HOUR, (jt, cap)
        assert cap <= 4 * _period(jt), (jt, cap, _period(jt))
        assert cap == min(4 * _period(jt), 6 * HOUR), (jt, cap)
    # the production offenders, by name
    for jt in (POOL, "assets.model_photography", "assets.owned_photography",
               "assets.photo_review", "creative.model_reference_pack", "creative.blinded",
               "listing.package", "visual.identity_drift", "chain.successors"):
        assert orc.backoff_cap_seconds(jt) <= 6 * HOUR, jt


def test_a_32x_park_clamps_to_the_cap_on_read_and_in_the_rows():
    db = _db()
    now = utcnow()
    since = now - timedelta(hours=1)
    legacy_until = _legacy_park(db, POOL, since=since)
    assert legacy_until > now + timedelta(days=7)      # production: parked until December
    cap = orc.backoff_cap_seconds(POOL)
    # read clamped, before anything rewrites the row
    hold = orc.suspended_job_types(db, now=now)[POOL]
    assert orc._parse_when(hold["until"]) == since + timedelta(seconds=cap), hold
    assert hold["factor"] <= orc.MAX_BACKOFF_FACTOR
    # and the clamp rewrites the row, only ever earlier
    out = orc.clamp_parked_backoffs(db, now=now)
    assert [c["job_type"] for c in out] == [POOL], out
    with db.session() as s:
        sus = s.scalar(select(Incident).where(
            Incident.signature == f"{orc.BACKOFF_SIGNATURE_PREFIX}{POOL}")).detail["suspension"]
    assert orc._parse_when(sus["suspend_until"]) == since + timedelta(seconds=cap)
    assert sus["clamped_from"] == legacy_until.isoformat()
    assert sus["factor"] <= orc.MAX_BACKOFF_FACTOR
    assert orc.clamp_parked_backoffs(db, now=now) == [], "the clamp is idempotent"
    # past the cap the job is due again
    assert POOL not in orc.suspended_job_types(db, now=since + timedelta(seconds=cap + 1))


def test_clamping_happens_on_boot_and_the_job_is_enqueued():
    db = _db()
    now = utcnow()
    # parked 7 h ago under the old cap: the cap (6 h) has already passed
    _legacy_park(db, POOL, since=now - timedelta(hours=7))
    W._BACKOFF_CLAMPED_AT_BOOT.discard(id(db))
    sched = Scheduler(db)
    sched.tick(now=now)
    assert [c["job_type"] for c in sched.backoff_clamped] == [POOL], sched.backoff_clamped
    assert sched.backoff_clamped[0]["expired"] is True
    assert POOL not in sched.suspended, sched.suspended
    with db.session() as s:
        jobs = list(s.scalars(select(Job).where(Job.job_type == POOL)))
    assert jobs, "the clamped job was not enqueued on the boot tick"


def test_paid_loop_suspensions_are_not_touched_by_the_clamp():
    db = _db()
    now = utcnow()
    with db.session() as s:
        s.add(Incident(severity="P2", signature=f"{orc.THRASH_SIGNATURE_PREFIX}mjs.scan:x",
                       summary="paid loop", at=now - timedelta(days=3),
                       detail={"suspension": {"kind": orc.SUSPENDED, "job_type": "mjs.scan",
                                              "since": (now - timedelta(days=3)).isoformat(),
                                              "handler_digest": orc.handler_digest("mjs.scan"),
                                              "code_commit": orc._commit()}}))
    assert orc.clamp_parked_backoffs(db, now=now) == []
    assert "mjs.scan" in orc.suspended_job_types(db, now=now)


def test_a_genuine_hot_idle_loop_is_still_slowed():
    """A 15-minute poller with identical output backs off -- to at most 4x (1 h), and the
    level climbs on each new identical observation -- but never further."""
    hot = next(jt for _n, _a, jt, p in CADENCES
               if p <= 15 * 60 and jt not in orc.LIVENESS_JOB_TYPES
               and jt not in orc.UPSTREAM_INPUTS and jt not in orc.INPUT_PROBES)
    period = _period(hot)
    db = _db()
    now = utcnow()
    _idle_runs(db, hot, end=now)
    out = orc.thrash_sweep(db, now=now)
    applied = {a["job_type"]: a for a in out["backoff"]["applied"]}
    assert hot in applied, (hot, out["backoff"])
    first = orc._parse_when(applied[hot]["until"])
    assert first == now + timedelta(seconds=2 * period), applied[hot]
    assert hot in orc.suspended_job_types(db, now=now + timedelta(seconds=period)), \
        "the hot idle loop was not slowed"
    # more identical observations: the park grows, and stops at the cap
    t = now
    for _ in range(6):
        t = t + timedelta(hours=2)
        _idle_runs(db, hot, n=1, end=t)
        out = orc.thrash_sweep(db, now=t)
        a = {x["job_type"]: x for x in out["backoff"]["applied"]}[hot]
        until = orc._parse_when(a["until"])
        assert until - t <= timedelta(seconds=orc.backoff_cap_seconds(hot)), a
        assert a["factor"] <= orc.MAX_BACKOFF_FACTOR
    assert until - t == timedelta(seconds=min(4 * period, 6 * HOUR)), (until, t)
    assert hot in orc.suspended_job_types(db, now=t + timedelta(seconds=period))


def test_daily_job_park_never_crosses_its_next_window():
    """32x of a daily period was a month. A daily job is now parked at most 6 h."""
    jt = "assets.owned_photography"
    assert _period(jt) == 24 * HOUR
    db = _db()
    now = utcnow()
    _idle_runs(db, jt, end=now, outputs={"ran": False, "reason": "same"})
    out = orc.thrash_sweep(db, now=now)
    hits = [a for a in out["backoff"]["applied"] if a["job_type"] == jt]
    assert hits, ("the idle daily job was not backed off at all", out["backoff"])
    for a in hits:
        assert orc._parse_when(a["until"]) <= now + timedelta(hours=6), a


def test_image_jobs_wake_when_image_generation_becomes_usable():
    db = _db()
    now = utcnow()
    since = now - timedelta(minutes=30)
    from brambleloop.gateway import images

    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=images.PROBE_ACTION, at=since -
                       timedelta(hours=1), detail={"ok": False}))
    for jt in ("assets.owned_photography", "assets.model_photography",
               "creative.model_reference_pack"):
        _legacy_park(db, jt, since=since, factor=2, level=1)
        assert jt in orc.suspended_job_types(db, now=now), jt
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=images.PROBE_ACTION,
                       at=now - timedelta(minutes=5), detail={"ok": True}))
    held = orc.suspended_job_types(db, now=now)
    for jt in ("assets.owned_photography", "assets.model_photography",
               "creative.model_reference_pack"):
        assert jt not in held, (jt, held.get(jt))


def test_a_routine_ok_probe_is_not_new_image_input():
    db = _db()
    now = utcnow()
    since = now - timedelta(minutes=30)
    from brambleloop.gateway import images

    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=images.PROBE_ACTION,
                       at=since - timedelta(hours=1), detail={"ok": True}))
        s.add(AuditLog(actor="orchestrator", action=images.PROBE_ACTION,
                       at=now - timedelta(minutes=5), detail={"ok": True}))
    _legacy_park(db, "assets.owned_photography", since=since, factor=2, level=1)
    assert "assets.owned_photography" in orc.suspended_job_types(db, now=now)


def test_photo_review_wakes_on_new_frames_from_the_photographers():
    db = _db()
    now = utcnow()
    since = now - timedelta(minutes=30)
    _legacy_park(db, "assets.photo_review", since=since, factor=2, level=1)
    assert "assets.photo_review" in orc.suspended_job_types(db, now=now)
    with db.session() as s:
        s.add(Job(agent="publishing", job_type="assets.owned_photography", inputs={},
                  status=JobStatus.DONE, outputs={"ran": True, "made": 1, "work_done": 1},
                  created_at=now - timedelta(minutes=9), started_at=now - timedelta(minutes=9),
                  finished_at=now - timedelta(minutes=8)))
    assert "assets.photo_review" not in orc.suspended_job_types(db, now=now)


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
