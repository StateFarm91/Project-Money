"""OPUS2-P0: P0-CHAIN-DEADENDS -- every stage that can stop gets a deterministic successor.

The four dead ends W-INVENTORY found (research/final_build/w4/INVENTORY.md): a refused price,
blocked listing images, an unversioned parity row and a held seasonal launch. Stage outcomes
are injected by swapping the stage body the registered wrapper calls; the unknown-product
refusal and the sweep run for real.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_chain_deadends.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")
for _v in ("RAILWAY_GIT_COMMIT_SHA", "BRAMBLELOOP_COMMIT"):
    os.environ.pop(_v, None)

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident, Job, JobStatus, OwnerAction  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import chain_successors as CS  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402
from brambleloop.runtime.worker import CADENCES, JobContext, handlers  # noqa: E402
from brambleloop.seasonal import leadtime as lt  # noqa: E402

REL = {"slug": "deadend-fixture-cowl", "version": "1.0.0", "release": "r" * 64,
       "rebuild": "tok"}


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='opus2_dead_')}/d.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run(db, agent, job_type, inputs):
    q = JobQueue(db)
    job = q.enqueue(agent, job_type, dict(inputs), idempotency_key=f"t:{os.urandom(4).hex()}")
    return handlers.get(job_type)(JobContext(job=job, db=db, queue=q, registry=Registry(db),
                                             phase=None))


class _Stage:
    """Swap one stage body for the duration of a test."""

    def __init__(self, name, out):
        self.name, self.out, self.saved = name, out, getattr(release, name)

    def __enter__(self):
        setattr(release, self.name, lambda ctx: dict(self.out))

    def __exit__(self, *a):
        setattr(release, self.name, self.saved)


def _incidents(db):
    with db.session() as s:
        return {r.signature: (r.severity, r.halts_publication, r.resolved, dict(r.detail or {}))
                for r in s.scalars(select(Incident).where(Incident.signature.like(f"{CS.PREFIX}%")))}


def _owner_actions(db):
    with db.session() as s:
        return [(r.requirement_key, r.max_cost_cad, r.why_software_cannot)
                for r in s.scalars(select(OwnerAction).order_by(OwnerAction.id))]


def _jobs(db, job_type):
    with db.session() as s:
        return [(j.inputs, j.run_after, j.idempotency_key, j.agent) for j in s.scalars(
            select(Job).where(Job.job_type == job_type).order_by(Job.id))]


def test_the_sweep_is_wired_hourly_and_the_wrappers_are_the_registered_handlers():
    assert ("chain_successors", "listing", "chain.successors", 3600) in CADENCES
    Registry(_db()).authorize("listing", "chain.successors")
    assert handlers.get("assets.build") is release.handle_assets_build_with_successor
    assert handlers.get("pricing.position") is release.handle_pricing_position_with_successor
    assert handlers.get("launch.plan") is release.handle_launch_plan_with_successor


def test_a_net_floor_price_refusal_becomes_one_owner_action_and_an_incident():
    db = _db()
    refused = {"slug": REL["slug"], "stopped": True, "refused": "no price inside the band "
               "CA$4.00-CA$12.00 clears the CA$1.50 net floor",
               "reasons": ["net contribution below floor"]}
    with _Stage("handle_pricing_position", refused):
        out = _run(db, "pricing", "pricing.position", REL)
        _run(db, "pricing", "pricing.position", REL)          # the same refusal again
    assert out["stopped"] and out["successor"]["owner_action"].endswith(
        f"{REL['slug']}@{REL['version']}")
    acts = _owner_actions(db)
    assert len(acts) == 1 and acts[0][1] == 0.0 and "commercial decision" in acts[0][2]
    inc = _incidents(db)[CS.signature(CS.PRICING, REL["slug"], REL["version"])]
    assert inc[0] == "P2" and inc[1] is False and inc[3]["inputs"]["release"] == REL["release"]
    assert "rebuild" not in inc[3]["inputs"]


def test_an_unknown_product_is_a_company_defect_not_an_owner_decision():
    db = _db()
    out = _run(db, "pricing", "pricing.position",
               {"slug": "no-such-product-anywhere", "version": "1.0.0"})
    assert out["code"] == release.UNKNOWN_PRODUCT and out["stopped"]
    assert out["successor"]["owner_action"] is None and _owner_actions(db) == []
    assert CS.signature(CS.PRICING, "no-such-product-anywhere", "1.0.0") in _incidents(db)


def test_blocked_listing_images_record_a_visual_incident_and_enqueue_nothing_now():
    db = _db()
    blocked = {"slug": REL["slug"], "version": REL["version"], "ok": False,
               "blocking_image_problems": ["hero shows 5 coasters; the set is 4"]}
    with _Stage("handle_assets_build", blocked):
        out = _run(db, "publishing", "assets.build", REL)
    assert out["ok"] is False and out["successor"]["opened"] is True
    inc = _incidents(db)[CS.signature(CS.ASSETS, REL["slug"], REL["version"])]
    assert inc[3]["department"] == "visual" and inc[3]["problems"]
    assert inc[3]["refused_under_commit"] == "unknown"
    assert len(_jobs(db, "assets.build")) == 1                # only the job that ran


def test_a_successful_stage_records_no_dead_end():
    db = _db()
    with _Stage("handle_assets_build", {"ok": True, "pdf_sha256": "a" * 64}):
        out = _run(db, "publishing", "assets.build", REL)
    assert "successor" not in out and _incidents(db) == {}


def test_a_held_launch_is_replanned_the_day_after_the_missed_occasion_once():
    db = _db()
    held = {"held": True, "window_decision": {"action": lt.HOLD, "occasion": "Christmas",
                                              "event_date": "2026-12-25",
                                              "may_launch_seasonally": False}}
    inputs = {**REL, "as_of": "2026-12-20", "window_decision": {"x": 1}}
    with _Stage("handle_launch_plan", held):
        out = _run(db, "growth", "launch.plan", inputs)
        _run(db, "growth", "launch.plan", inputs)
    assert out["successor"] == {"replan_on": "2026-12-26", "queued": True}
    plans = [j for j in _jobs(db, "launch.plan") if j[1] and j[1].date() == date(2026, 12, 26)]
    assert len(plans) == 1 and plans[0][3] == "growth"
    assert "window_decision" not in plans[0][0] and "as_of" not in plans[0][0]


def test_a_pivot_needs_no_successor_and_an_unknown_occasion_waits_thirty_days():
    db = _db()
    pivot = {"held": True, "window_decision": {"action": lt.PIVOT_EVERGREEN}}
    with _Stage("handle_launch_plan", pivot):
        out = _run(db, "growth", "launch.plan", {**REL, "as_of": "2026-11-01"})
    assert "successor" not in out
    unknown = {"held": True, "window_decision": {"action": lt.HOLD, "event_date": None}}
    with _Stage("handle_launch_plan", unknown):
        out = _run(db, "growth", "launch.plan", {**REL, "as_of": "2026-11-01"})
    assert out["successor"]["replan_on"] == "2026-12-01"


def test_the_sweep_redrives_once_per_new_commit_and_never_under_an_unknown_one():
    db = _db()
    blocked = {"ok": False, "blocking_image_problems": ["invented edging"]}
    os.environ["RAILWAY_GIT_COMMIT_SHA"] = "a" * 40
    try:
        with _Stage("handle_assets_build", blocked):
            _run(db, "publishing", "assets.build", REL)
        q = JobQueue(db)
        same = CS.sweep(db, q)
        assert same["redriven"] == [] and "under this commit" in same["waiting"][0]["why"]
        os.environ["RAILWAY_GIT_COMMIT_SHA"] = "b" * 40
        first = CS.sweep(db, q)
        again = CS.sweep(db, q)
        assert len(first["redriven"]) == 1 and again["redriven"] == []
        redrives = [j for j in _jobs(db, "assets.build") if j[2].startswith("deadend:")]
        assert len(redrives) == 1 and redrives[0][0]["rebuild"] == "deadend:" + "b" * 12
        assert redrives[0][3] == "publishing"
        os.environ.pop("RAILWAY_GIT_COMMIT_SHA")
        unknown = CS.sweep(db, q)
        assert unknown["redriven"] == [] and "unknown" in unknown["waiting"][0]["why"]
    finally:
        os.environ.pop("RAILWAY_GIT_COMMIT_SHA", None)


def test_the_sweep_closes_a_dead_end_once_its_stage_succeeds_for_that_release():
    db = _db()
    with _Stage("handle_assets_build", {"ok": False, "blocking_image_problems": ["x"]}):
        _run(db, "publishing", "assets.build", REL)
    with db.session() as s:
        s.add(Job(agent="publishing", job_type="assets.build", status=JobStatus.DONE,
                  inputs=dict(REL), outputs={"pdf_sha256": "a" * 64},
                  finished_at=datetime.now(timezone.utc)))
    out = _run(db, "listing", "chain.successors", {})
    assert out["resolved"] == [CS.signature(CS.ASSETS, REL["slug"], REL["version"])]
    assert not pipeline.did_no_work(out, "chain.successors")
    assert all(v[2] for v in _incidents(db).values())


def test_review_opus2b2_f11_the_pricing_owner_action_closes_with_its_dead_end():
    db = _db()
    refused = {"slug": REL["slug"], "stopped": True, "refused": "no price clears the floor",
               "reasons": ["net contribution below floor"]}
    with _Stage("handle_pricing_position", refused):
        _run(db, "pricing", "pricing.position", REL)
    with db.session() as s:
        s.add(Job(agent="pricing", job_type="pricing.position", status=JobStatus.DONE,
                  inputs=dict(REL), outputs={"price_cad": 6.5},
                  finished_at=datetime.now(timezone.utc)))
    out = _run(db, "listing", "chain.successors", {})
    assert out["resolved"] == [CS.signature(CS.PRICING, REL["slug"], REL["version"])], out
    with db.session() as s:
        acts = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like(f"{CS.OWNER_KEY}%"))))
        assert acts and all(a.done for a in acts)
        assert all(a.state == "satisfied" and "cleared" in (a.state_reason or "")
                   for a in acts)


def test_the_parity_row_carries_the_version_and_release_it_judged():
    import inspect

    src = inspect.getsource(pipeline)
    i = src.index('ctx.audit("listing.parity"')
    window = src[i:i + 300]
    assert '"version": ctx.job.inputs.get("version", "1.0.0")' in window
    assert '"release": ctx.job.inputs.get("release", "")' in window


def _deadend_inputs(db, kind=CS.ASSETS):
    with db.session() as s:
        row = s.scalar(select(Incident).where(
            Incident.signature == CS.signature(kind, REL["slug"], REL["version"]),
            Incident.resolved.is_(False)))
        return None if row is None else dict((row.detail or {}).get("inputs") or {})


def test_a_fix_only_refusal_never_replaces_the_releases_own_dead_end():
    """Review STOREFRONT a1331372 H1 (repro B): the dead end keeps its ordinary inputs."""
    db = _db()
    blocked = {"ok": False, "blocking_image_problems": ["invented edging"]}
    with _Stage("handle_assets_build", blocked):
        _run(db, "publishing", "assets.build", REL)                     # the release's own
        assert "fix_only" not in _deadend_inputs(db)
        _run(db, "publishing", "assets.build", {**REL, "rebuild": "fo-1", "fix_only": True})
    assert "fix_only" not in _deadend_inputs(db), _deadend_inputs(db)


def test_a_fix_only_refusal_alone_opens_no_dead_end():
    db = _db()
    with _Stage("handle_assets_build", {"ok": False, "blocking_image_problems": ["x"]}):
        _run(db, "publishing", "assets.build", {**REL, "fix_only": True})
    assert _deadend_inputs(db) is None
    from brambleloop.core.models import AuditLog

    with db.session() as s:                           # review cdf4cb5e A-L2 / M9
        assert s.scalar(select(AuditLog).where(
            AuditLog.action == "chain.deadend_not_recorded")) is not None


def test_a_fix_only_success_never_closes_the_releases_dead_end():
    """Review STOREFRONT a1331372 H1 (repro A): a fix-only build stops before launch.plan."""
    db = _db()
    with _Stage("handle_assets_build", {"ok": False, "blocking_image_problems": ["x"]}):
        _run(db, "publishing", "assets.build", REL)
    with db.session() as s:
        s.add(Job(agent="publishing", job_type="assets.build", status=JobStatus.DONE,
                  inputs={**REL, "fix_only": True}, outputs={"pdf_sha256": "a" * 64},
                  finished_at=datetime.now(timezone.utc)))
    out = _run(db, "listing", "chain.successors", {})
    assert out["resolved"] == [], out
    assert _deadend_inputs(db) is not None


def test_the_sweep_never_redrives_with_the_bound_and_commits_never_share_a_key():
    db = _db()
    os.environ["RAILWAY_GIT_COMMIT_SHA"] = "a" * 40
    try:
        with _Stage("handle_assets_build", {"ok": False, "blocking_image_problems": ["x"]}):
            _run(db, "publishing", "assets.build", REL)
        with db.session() as s:                    # a legacy row carrying the bound
            row = s.scalar(select(Incident).where(Incident.signature == CS.signature(
                CS.ASSETS, REL["slug"], REL["version"])))
            row.detail = {**dict(row.detail), "inputs": {**dict(row.detail)["inputs"],
                                                         "fix_only": True}}
        os.environ["RAILWAY_GIT_COMMIT_SHA"] = "b" * 40
        out = CS.sweep(db, JobQueue(db))
        # Review 4b4e3694: an ORDINARY dead end whose inputs a pre-fix fix-only refusal
        # restated still stands for the release's own refusal. It stays open with the bound
        # stripped, and it is never re-driven automatically.
        assert out["redriven"] == [] and out["resolved"] == [], out
        assert "legacy" in out["waiting"][0]["why"], out
        assert not [j for j in _jobs(db, "assets.build") if j[2].startswith("deadend:")]
        assert _deadend_inputs(db) is not None and "fix_only" not in _deadend_inputs(db)
        again = CS.sweep(db, JobQueue(db))                     # stays waiting on later sweeps
        assert again["redriven"] == [] and again["resolved"] == [], again
        # ...and an ordinary success still closes it.
        with db.session() as s:
            s.add(Job(agent="publishing", job_type="assets.build", status=JobStatus.DONE,
                      inputs=dict(REL), outputs={"pdf_sha256": "a" * 64},
                      finished_at=datetime.now(timezone.utc)))
        closed = CS.sweep(db, JobQueue(db))
        assert closed["resolved"] and _deadend_inputs(db) is None, closed
    finally:
        os.environ.pop("RAILWAY_GIT_COMMIT_SHA", None)
    # Commits that share their first 4 hex collided when the token was cut to 12 characters
    # (review cdf4cb5e A-M1); so did any two parity-escalation states.
    for x, y in (("deadend:aaaa11112222", "deadend:aaaa33334444"),
                 ("parity-escalation:" + "1" * 16, "parity-escalation:" + "2" * 16)):
        a = release.chain_key("listing.seo", "s", "1", "r" * 64, x)
        b = release.chain_key("listing.seo", "s", "1", "r" * 64, y)
        assert a != b, (a, b)
    assert release.chain_key("x", "s", "1", "", "0123456789ab").endswith(":0123456789ab:c"
                                                                          + str(release.CHAIN_VERSION))


def test_a_legacy_dead_end_that_began_as_a_fix_only_refusal_is_resolved_not_redriven():
    """Review 4b4e3694: one report, and the refusing job was itself bound."""
    db = _db()
    os.environ["RAILWAY_GIT_COMMIT_SHA"] = "a" * 40
    try:
        q = JobQueue(db)
        job = q.enqueue("publishing", "assets.build", {**REL, "fix_only": True},
                        idempotency_key="legacy-fo")
        with db.session() as s:                      # the row a pre-fix record() wrote
            s.add(Incident(severity="P2", signature=CS.signature(CS.ASSETS, REL["slug"],
                                                                 REL["version"]),
                           summary="legacy", product_slug=REL["slug"],
                           detail={"kind": CS.ASSETS, "stage": "assets.build",
                                   "inputs": {k: v for k, v in {**REL, "fix_only": True}.items()
                                              if k != "rebuild"},
                                   "refused_under_commit": "a" * 40, "refused_job": job.id}))
        os.environ["RAILWAY_GIT_COMMIT_SHA"] = "b" * 40
        out = CS.sweep(db, q)
        assert out["resolved"] and out["redriven"] == [], out
        assert _deadend_inputs(db) is None
    finally:
        os.environ.pop("RAILWAY_GIT_COMMIT_SHA", None)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
