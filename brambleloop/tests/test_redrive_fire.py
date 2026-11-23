"""REDRIVE-FIRE: the two image redrives fire through the real scheduler path.

Production 19i18 (2026-11-23T01:50Z): three runs blocked on the provider's daily ceiling
yesterday, and two fidelity blocks were made under an older generation method. Neither redrive
fired, though both were deployed. Both live inside the hourly `chain.successors` sweep, and
that cadence sat in the thrash breaker's free-poll backoff at 32x (BUILD_STATE). A sweep that
waits for the UTC day to change returns identical outputs, so the breaker reads it as an idle
poll and parks it for 32 hours. Nothing woke it when the day changed.

Each test drives the real path:
  Scheduler.tick -> Worker.run_once -> handle_chain_successors -> chain_successors.sweep ->
  image_production.redrive_capability_blocked -> restart (enqueues visual.image_production)
with the backoff produced by the real `thrash_sweep`. The fixtures run with and without the
breaker's input probe (`orchestrate.INPUT_PROBES["chain.successors"]`), so each test shows
the defect and the fix. Nothing generates and nothing is paid: the restarted image job is
enqueued and never run.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_redrive_fire.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

for _k in ("RAILWAY_GIT_COMMIT_SHA", "BRAMBLELOOP_COMMIT", "GIT_COMMIT_SHA", "SOURCE_COMMIT"):
    os.environ.pop(_k, None)

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, Job  # noqa: E402
from brambleloop.ops import production_evidence as PE  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Scheduler, Worker  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402
from brambleloop.visual.image_records import (ImageCandidate, ImageProductionRun,  # noqa: E402
                                              ensure_tables)

JT = "chain.successors"
# D-OWNER-NO-PAUSE (19i20): production-pipeline job types, chain.successors included, are
# never parked by the idle backoff, so the 32x park these tests reproduce cannot happen in
# production any more (tests/test_no_pause.py). The redrive-lift mechanism they cover still
# serves every non-pipeline type, so here JT is treated as an ordinary poll.
_is_pipeline = orc.is_pipeline_job
orc.is_pipeline_job = lambda jt: jt != JT and _is_pipeline(jt)
DAILY = ("budget stop: paid provider gate refused before sending (provider_daily_ceiling): "
         "flux-3-image has CA$0.0700 reserved or billed today against the owner's CA$0.07 "
         "daily ceiling; this call is CA$0.0700")
FIDELITY = "product fidelity FAIL after 3 attempts: {'product_truth': 'wrong bands'}"

NOW = datetime.now(timezone.utc)
MIDNIGHT = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
YESTERDAY = MIDNIGHT - timedelta(hours=4)        # 20:00Z yesterday: the block
# One sweep per hourly cadence window (the scheduler keys a window by the hour). Four: the
# first sweep's audit row is new evidence to the breaker, then three identical states park it.
HOURLY = (10, 70, 130, 190)
PARKED = YESTERDAY + timedelta(minutes=210)      # 23:30Z yesterday: parked at 32x


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='rdf_')}/rdf.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    ensure_tables(db)
    return db


def _run(db, slug, *, stage, reason, when, calls=3, spent=0.07):
    key = IP.run_key(slug, "1.0.0", f"{slug}-release")
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug=slug, version="1.0.0",
                                 release=f"{slug}-release", listing=slug, stage=stage,
                                 status="blocked", blocked_reason=reason, stages={},
                                 generation_calls=calls, spent_cad=spent, updated_at=when,
                                 attempts_exhausted=True))
    return key


def _fail_candidates(db, key, slug, n=3):
    """Pre-method FAILed product frames: unstamped, as every frame made before 19i17."""
    with db.session() as s:
        for i in range(n):
            s.add(ImageCandidate(
                sha256=f"{i + 1:064x}", run_key=key, method="autonomous",
                provenance_kind="ai_generated_autonomous", slug=slug, version="1.0.0",
                release=f"{slug}-release", listing=slug, role=IP.ANCHOR_ROLE,
                stage="product_generation", attempt=i + 1,
                checks={"product_truth": {"status": "FAIL", "why": "bands"}},
                technical_status="FAIL", outcome="rejected"))


class _Clock:
    """The image module's clock (`IP._now`), pinned to a time yesterday."""

    def __init__(self, at):
        self.at = at

    def __enter__(self):
        self.real, IP._now = IP._now, (lambda: self.at)
        return self

    def __exit__(self, *a):
        IP._now = self.real


class _NoProbe:
    """The breaker as it was on 19i18: no input probe for the sweep."""

    def __enter__(self):
        self.saved = orc.INPUT_PROBES.pop(JT)

    def __exit__(self, *a):
        orc.INPUT_PROBES[JT] = self.saved


def _sweep_once(db, at):
    """One real cadence window: the scheduler enqueues the sweep, a worker runs it."""
    Scheduler(db).tick(now=at)
    w = Worker(db, job_types=[JT])
    assert w.run_once(), f"no {JT} job ran at {at}"
    with db.session() as s:
        job = s.scalar(select(Job).where(Job.job_type == JT).order_by(Job.id.desc()))
        return dict(job.outputs or {})


def _park_at_32x(db, *, since):
    """Identical hourly sweeps, judged by the real thrash sweep, then held at the 32x cap
    production showed (BUILD_STATE: chain.successors x32)."""
    out = orc.thrash_sweep(db, now=since)
    assert any(a["job_type"] == JT for a in out["backoff"]["applied"]), out["backoff"]
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == f"{orc.BACKOFF_SIGNATURE_PREFIX}{JT}",
            Incident.resolved.is_(False)))
        sus = dict(inc.detail["suspension"])
        sus.update(level=5, factor=32, since=since.isoformat(),
                   suspend_until=(since + timedelta(hours=32)).isoformat())
        inc.detail = {**dict(inc.detail), "suspension": sus}


def _image_jobs(db):
    with db.session() as s:
        return [dict(j.inputs or {}) for j in s.scalars(
            select(Job).where(Job.job_type == IP.JOB_TYPE).order_by(Job.id))]


def _history(db, key):
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        return (r.status, r.generation_calls, r.spent_cad,
                list(((r.stages or {}).get(IP.RESTART_KEY) or {}).get("history") or []))


def test_blocked_yesterday_on_the_daily_ceiling_restarts_today_through_the_scheduler():
    db = _db()
    key = _run(db, "market-basket", stage="product_generation", reason=DAILY, when=YESTERDAY)
    # Yesterday: hourly sweeps, each waiting for the UTC day to change.
    for m in HOURLY:
        at = YESTERDAY + timedelta(minutes=m)
        with _Clock(at):
            out = _sweep_once(db, at)
        assert [w["run_key"] for w in out["images"]["waiting"]] == [key], out["images"]
        assert out["work_done"] == 0, out
    _park_at_32x(db, since=PARKED)
    # Today. On 19i18 the sweep stays parked: the new UTC day reaches nothing.
    with _NoProbe():
        assert JT in orc.suspended_job_types(db, now=NOW), "the defect did not reproduce"
        Scheduler(db).tick(now=NOW)
        assert not Worker(db, job_types=[JT]).run_once()
    # With the sweep's input probe: the day changed, so the backoff lifts ...
    with db.session() as s:
        due = IP.redrive_due(s, PARKED)
    assert due and due["kind"] == "daily_ceiling_reset" and due["run_key"] == key, due
    assert JT not in orc.suspended_job_types(db, now=NOW)
    # ... and the next cadence window restarts the run, once.
    out = _sweep_once(db, NOW + timedelta(hours=1))
    assert [r["run_key"] for r in out["images"]["restarted"]] == [key], out["images"]
    assert out["work_done"] >= 1, out
    jobs = _image_jobs(db)
    assert len(jobs) == 1 and jobs[0]["epoch"] == 1, jobs
    status, calls, spent, history = _history(db, key)
    assert status != "blocked", status
    assert (calls, spent) == (3, 0.07), (calls, spent)     # spend and calls never reset
    assert history[-1]["by"] == IP.DAILY_REDRIVE_BY, history
    assert str(NOW.date()) in history[-1]["reason"], history
    # The audit the handler writes names the restart.
    with db.session() as s:
        detail = s.scalar(select(AuditLog.detail).where(
            AuditLog.action == "chain.successors_swept").order_by(AuditLog.id.desc()))
    assert detail["images"]["restarted"] == [key], detail
    assert set(detail["method_redrives"]) == set(IP.METHOD_REDRIVE_EVIDENCE), detail
    # It meets the ceiling again today: blocked again, and today's one restart is spent.
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        r.status, r.blocked_reason, r.stage, r.updated_at = ("blocked", DAILY,
                                                             "product_generation", NOW)
    with db.session() as s:
        assert IP.redrive_due(s, None) is None
    # Nothing is due, so the backoff stands as an ordinary idle poll would ...
    assert JT in orc.suspended_job_types(db, now=NOW + timedelta(hours=2))
    # ... and the sweep itself, run anyway, makes no second restart today.
    out = IP.redrive_capability_blocked(db, follow=lambda *a, **k: object())
    assert out["restarted"] == [] and [w["run_key"] for w in out["waiting"]] == [key], out
    assert len(_image_jobs(db)) == 1


def test_a_daily_ceiling_block_from_today_is_not_due():
    db = _db()
    _run(db, "coaster-set", stage="product_generation", reason=DAILY, when=NOW)
    with db.session() as s:
        assert IP.redrive_due(s, NOW - timedelta(hours=1)) is None
    # Nor is any other budget stop, on any day.
    db = _db()
    _run(db, "coaster-set", stage="product_generation", when=YESTERDAY,
         reason="budget stop: per-gallery cap CA$2.00 reached")
    with db.session() as s:
        assert IP.redrive_due(s, None) is None


def test_the_restart_cap_holds_the_probe_too():
    db = _db()
    key = _run(db, "trivet", stage="product_generation", reason=DAILY, when=YESTERDAY)
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        r.stages = {IP.RESTART_KEY: {"epoch": IP.MAX_RESTARTS, "history": []}}
    with db.session() as s:
        assert IP.redrive_due(s, None) is None


def test_an_old_method_fidelity_block_restarts_through_the_scheduler_once():
    db = _db()
    slug = "hexagon-coaster-set"
    # The run blocked at the fidelity gate after this release's one re-arm probe was spent
    # (a reverify restart re-judged its pre-method frames), so the probe cannot reach it.
    key = _run(db, slug, stage="product_generation", reason=DAILY, when=YESTERDAY)
    for m in HOURLY:
        at = YESTERDAY + timedelta(minutes=m)
        with _Clock(at):
            _sweep_once(db, at)
    _park_at_32x(db, since=PARKED)
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        r.stage, r.blocked_reason, r.attempts_exhausted = "fidelity_gate", FIDELITY, True
    _fail_candidates(db, key, slug)
    with _NoProbe():
        assert JT in orc.suspended_job_types(db, now=NOW), "the defect did not reproduce"
    with db.session() as s:
        due = IP.redrive_due(s, PARKED)
    assert due and due["kind"] == "method_redrive" and due["run_key"] == key, due
    assert JT not in orc.suspended_job_types(db, now=NOW)
    out = _sweep_once(db, NOW + timedelta(hours=1))
    assert out["method_redrives"] == {"eligible": 1, "done": 1, "no_headroom": 0}, out
    jobs = _image_jobs(db)
    assert len(jobs) == 1 and jobs[0]["stage"] == "product_generation", jobs
    status, calls, spent, history = _history(db, key)
    assert status != "blocked" and (calls, spent) == (3, 0.07), (status, calls, spent)
    assert history[-1]["method_version"] == IP.current_method_version(), history
    # The production readback now carries the field, in the fixed vocabulary.
    runs = PE._vp_runs(db)
    assert runs["method_redrives"] == {"eligible": 0, "done": 1, "no_headroom": 0}, runs
    assert runs["redrive_due"] is None, runs
    # It FAILs again under the current method: no second restart for this method.
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        r.status, r.stage, r.blocked_reason = "blocked", "fidelity_gate", FIDELITY
    with db.session() as s:
        assert IP.redrive_due(s, None) is None
    out = IP.redrive_capability_blocked(db, follow=lambda *a, **k: object())
    assert out["restarted"] == [] and out["method_redrives"]["done"] == [], out
    assert any(r.get("code") == IP.METHOD_REDRIVE_ALREADY for r in out["refused"]), out
    assert len(_image_jobs(db)) == 1


def test_a_method_redrive_without_headroom_is_judged_once_and_not_due_again():
    db = _db()
    slug = "housewarming-key-basket"
    key = _run(db, slug, stage="fidelity_gate", reason=FIDELITY, when=YESTERDAY, calls=99,
               spent=9.99)
    _fail_candidates(db, key, slug)
    with db.session() as s:
        assert (IP.redrive_due(s, None) or {}).get("kind") == "method_redrive"
    out = _sweep_once(db, NOW)
    assert out["method_redrives"] == {"eligible": 1, "done": 0, "no_headroom": 1}, out
    assert _image_jobs(db) == []
    with db.session() as s:
        assert IP.redrive_due(s, None) is None       # judged under this method: not due
    runs = PE._vp_runs(db)
    assert runs["method_redrives"]["no_headroom"] == 1, runs


def test_the_readback_field_is_present_with_nothing_to_report():
    runs = PE._vp_runs(_db())
    assert runs["method_redrives"] == {k: 0 for k in IP.METHOD_REDRIVE_EVIDENCE}, runs
    assert runs["redrive_due"] is None


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
