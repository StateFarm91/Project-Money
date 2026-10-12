"""R2 autonomy, audit ddf9c6e L-1: a write-ahead effect intent + lease check at the effect
boundary, generalising publish.draft_intent, applied to every external-effect handler.

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_autonomy_effect_intents.py
"""
from __future__ import annotations

import inspect
from datetime import timedelta

from r2_autonomy_harness import boot, run_tests

from sqlalchemy import select, update


def _ctx(db, job_type="store.activate"):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Phase
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import JobContext

    q = JobQueue(db, lease_seconds=60)
    q.enqueue("orchestrator", "ops.queue_check", {}, idempotency_key=f"l1:{job_type}")
    job = q.claim("w1")
    return JobContext(job=job, db=db, queue=q, registry=Registry(db), phase=Phase.SHADOW), q


def test_second_attempt_is_refused_and_applied_is_reported():
    from brambleloop.core.models import Incident
    from brambleloop.queue import effects

    db = boot()
    ctx, _q = _ctx(db)
    sent = []
    with effects.guard(ctx, "test.remote", "k1") as intent:
        sent.append(1)
        intent.applied("remote:9")
    try:
        with effects.guard(ctx, "test.remote", "k1"):
            sent.append(2)
        raise AssertionError("a repeat of an applied effect ran")
    except effects.EffectAlreadyApplied as e:
        assert e.result_ref == "remote:9"
    assert sent == [1], sent
    # an interrupted attempt leaves the outcome unknown: never repeated, incident opened
    try:
        with effects.guard(ctx, "test.remote", "k2"):
            raise TimeoutError("socket timed out after send")
    except TimeoutError:
        pass
    try:
        with effects.guard(ctx, "test.remote", "k2"):
            sent.append(3)
        raise AssertionError("an UNCERTAIN effect was repeated")
    except effects.EffectRefused as e:
        assert "EFFECT_RECONCILIATION" in str(e)
    assert sent == [1], sent
    rows = {r["idem"]: r for r in effects.rows(db)}
    assert rows["k1"]["state"] == "APPLIED" and rows["k1"]["duplicate_attempts"] == 1
    assert rows["k2"]["state"] == "UNCERTAIN" and rows["k2"]["duplicate_attempts"] == 1
    with db.session() as s:
        assert s.scalar(select(Incident.id).where(
            Incident.signature.like("effect.reconcile:%"))) is not None


def test_provably_unsent_releases_the_intent():
    from brambleloop.queue import effects

    db = boot()
    ctx, _q = _ctx(db)
    try:
        with effects.guard(ctx, "test.remote", "k3"):
            raise effects.EffectNotSent("validation refused before send")
    except effects.EffectNotSent:
        pass
    with effects.guard(ctx, "test.remote", "k3") as intent:
        intent.applied("remote:3")
    assert {r["idem"]: r["state"] for r in effects.rows(db)}["k3"] == "APPLIED"


def test_a_stale_worker_stops_before_the_effect():
    from brambleloop.core.models import Job
    from brambleloop.queue import effects

    db = boot()
    ctx, q = _ctx(db)
    # the lease lapses and another worker reclaims the job
    with db.session() as s:
        s.execute(update(Job).where(Job.id == ctx.job.id).values(
            lease_expires_at=ctx.job.lease_expires_at - timedelta(hours=1)))
    assert q.claim("w2") is not None
    sent = []
    try:
        with effects.guard(ctx, "test.remote", "k4"):
            sent.append(1)
        raise AssertionError("stale worker performed the effect")
    except effects.LeaseLost:
        pass
    assert sent == [] and not [r for r in effects.rows(db) if r["idem"] == "k4"]


def test_every_external_effect_handler_is_inventoried_and_guarded():
    import brambleloop.runtime.pipeline as pipeline
    from brambleloop.queue import effects

    assert effects.EFFECT_INVENTORY
    for jt, entry in effects.EFFECT_INVENTORY.items():
        assert entry["guard"] and entry["semantics"], jt
    act = inspect.getsource(pipeline.handle_store_activate)
    assert 'effect_guard(ctx, "etsy.activate"' in act
    assert act.index("effect_guard(") < act.index("client.activate(")
    pub = inspect.getsource(pipeline)
    assert "draft_intent.claim(" in pub
    # at-least-once paths are stated, not implied
    assert effects.AT_LEAST_ONCE_EFFECTS
    assert "AT-LEAST-ONCE" in effects.__doc__


if __name__ == "__main__":
    run_tests(globals())
