"""W4-FMLEDGER: F-659 adoption -- the longest release handlers resume from a checkpoint.

`JobContext.checkpoint/restore` (W4-AUTO, queue/checkpoints.py) is the primitive; this proves
the two long handlers named in the AUTO wiring request use it through the real worker:

* `seasonal.cycle_proof` -- a worker that dies after the cycle ran but before the report was
  filed resumes from the checkpointed report: the cycle (concepts, engineering, render) is
  not run again, and the resumed attempt needs no model credential to file it.
* `assets.model_photography` -- a worker that dies after the render but before the frame
  record was filed resumes from the checkpointed record: the render is not repeated.
* A direct handler call (no queued job) has nothing to resume from and still runs the step.

Every crash is injected after the checkpoint; completion clears the checkpoints.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus  # noqa: E402
from brambleloop.queue import checkpoints  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import release  # noqa: E402
from brambleloop.runtime import worker as worker_mod  # noqa: E402
from brambleloop.runtime.worker import CADENCES, Worker  # noqa: E402

AGENT_OF = {jt: agent for _n, agent, jt, _p in CADENCES}


def boot() -> Database:
    tmp = tempfile.mkdtemp(prefix="w4fml-ckpt-")
    db = Database(f"sqlite:///{tmp}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


class _Patch:
    """Set attributes for the duration of a test and put every one back."""

    def __init__(self):
        self.saved = []

    def set(self, obj, name, value):
        self.saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, value in reversed(self.saved):
            setattr(obj, name, value)


def _crash_on_audit(p: _Patch, action: str) -> dict:
    """The first `ctx.audit(action)` raises: the worker dies after the long step."""
    state = {"armed": True}
    real = worker_mod.JobContext.audit

    def audit(self, act, **kw):
        if act == action and state["armed"]:
            state["armed"] = False
            raise RuntimeError("worker died before filing the result")
        return real(self, act, **kw)

    p.set(worker_mod.JobContext, "audit", audit)
    return state


def _rerun(db, job_id):
    with db.session() as s:
        s.get(Job, job_id).run_after = datetime.now(timezone.utc) - timedelta(seconds=1)


def _audits(db, action):
    with db.session() as s:
        return list(s.scalars(select(AuditLog).where(AuditLog.action == action)))


REPORT = {"steps": [{"step": "assets", "state": "PASS", "evidence": {"slug": "cycle-x"}}],
          "complete": True, "weakest_link": None, "customer_can_finish_in_time": True}


def test_cycle_proof_resumes_from_the_checkpointed_report():
    from brambleloop.gateway import anthropic, failover
    from brambleloop.seasonal import cycle

    db = boot()
    p = _Patch()
    runs: list[int] = []
    creds = {"key": "present"}
    try:
        p.set(anthropic.AnthropicProvider, "key", classmethod(lambda cls: creds["key"]))
        p.set(failover, "job_gateway", lambda *a, **k: object())

        def run(db_, *, gateway, asset_maker):
            assert gateway is not None
            runs.append(1)
            return dict(REPORT)

        p.set(cycle, "run", run)
        crash = _crash_on_audit(p, "seasonal.cycle_proof")
        jt = "seasonal.cycle_proof"
        job = JobQueue(db).enqueue(AGENT_OF[jt], jt, {})
        w = Worker(db, "w")
        w.run_once()  # attempt 1: the cycle runs, the worker dies before filing it
        assert runs == [1], runs
        assert not crash["armed"], "the injected crash did not fire"
        saved = checkpoints.all_for(db, job.id)
        assert "cycle_report" in saved and saved["cycle_report"]["report"]["complete"] is True
        assert _audits(db, "seasonal.cycle_proof") == []
        creds["key"] = None  # the resumed attempt must not need the provider at all
        _rerun(db, job.id)
        w.run_once()  # attempt 2: resumes from the checkpoint
        assert runs == [1], ("the cycle ran twice", runs)
        with db.session() as s:
            row = s.get(Job, job.id)
            assert row.status == JobStatus.DONE, (row.status, row.last_error)
            assert row.outputs["resumed_from_checkpoint"] is True, row.outputs
            assert row.outputs["assets_slug"] == "cycle-x"
        assert len(_audits(db, "seasonal.cycle_proof")) == 1
        assert checkpoints.all_for(db, job.id) == {}, "completion must clear checkpoints"
    finally:
        p.undo()
    print("OK test_cycle_proof_resumes_from_the_checkpointed_report")


def _patch_model_photography(p: _Patch, renders: list):
    from brambleloop.cir import compiler, twin
    from brambleloop.gateway import images
    from brambleloop.products import builder
    from brambleloop.publish import listing_asset, model_photography

    cir = SimpleNamespace(version="1.0.0", slug="model-x")
    p.set(images, "usable", lambda db: True)
    p.set(builder, "for_slug", lambda slug: cir if slug == "model-x" else None)
    p.set(model_photography, "planned_shots", lambda c: {"shots": ["on_body"]})
    p.set(model_photography, "what_to_do_next",
          lambda db, *, slug, version: {"render": True, "reason": "no_usable_frame",
                                        "attempts": 0, "why": ""})
    p.set(compiler, "compile_cir", lambda c: SimpleNamespace(ok=True))
    p.set(twin, "build_twin", lambda c, r: object())
    p.set(listing_asset, "needs_the_model", lambda c: True)

    def make(db, cir_, twin_, *, work_dir, record, **kw):
        renders.append(kw.get("shot_plan"))
        return {"made": False, "waiting_on": "identity_review", "floors": {"verdict": "HOLD"},
                "usable_as_listing_asset": False, "why": "held for review"}

    p.set(listing_asset, "make", make)


def test_model_photography_resumes_without_rendering_again():
    from brambleloop.publish import model_photography

    db = boot()
    p = _Patch()
    renders: list = []
    try:
        _patch_model_photography(p, renders)
        crash = _crash_on_audit(p, model_photography.ACTION)
        jt = "assets.model_photography"
        job = JobQueue(db).enqueue(AGENT_OF[jt], jt, {"slug": "model-x"})
        w = Worker(db, "w")
        w.run_once()  # attempt 1: renders, dies before filing the frame record
        assert len(renders) == 1, renders
        assert not crash["armed"], "the injected crash did not fire"
        saved = checkpoints.all_for(db, job.id)
        assert "render:model-x@1.0.0" in saved, saved
        _rerun(db, job.id)
        w.run_once()  # attempt 2: resumes
        assert len(renders) == 1, ("the render was repeated", renders)
        with db.session() as s:
            row = s.get(Job, job.id)
            assert row.status == JobStatus.DONE, (row.status, row.last_error)
            assert row.outputs["resumed_from_checkpoint"] is True, row.outputs
            assert row.outputs["waiting_on"] == "identity_review"
        assert len(_audits(db, model_photography.ACTION)) == 1
        assert checkpoints.all_for(db, job.id) == {}
    finally:
        p.undo()
    print("OK test_model_photography_resumes_without_rendering_again")


def test_a_direct_call_without_a_queued_job_still_runs_the_step():
    db = boot()
    p = _Patch()
    renders: list = []
    try:
        _patch_model_photography(p, renders)
        audits: list[str] = []
        ctx = SimpleNamespace(db=db, job=SimpleNamespace(id=None, inputs={"slug": "model-x"}),
                              audit=lambda action, **kw: audits.append(action))
        out = release.handle_model_photography(ctx)
        assert out["ran"] is True and out["resumed_from_checkpoint"] is False, out
        assert len(renders) == 1, renders
        assert release._checkpoint_step(ctx, "k", {"v": 1}) is False
        assert release._restore_step(ctx, "k") is None
    finally:
        p.undo()
    print("OK test_a_direct_call_without_a_queued_job_still_runs_the_step")


TESTS = [
    test_cycle_proof_resumes_from_the_checkpointed_report,
    test_model_photography_resumes_without_rendering_again,
    test_a_direct_call_without_a_queued_job_still_runs_the_step,
]

if __name__ == "__main__":
    assert TESTS
    failed = 0
    for t in TESTS:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL {t.__name__}: {e}")
    print(f"{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
