"""A4b: a refused draft goes back to Research and returns as a new draft (owner directive
2026-11-02; queue Q26).

On a real SQLite file through the real Worker and the registered handlers: a radar concept the
fallback refuses (`cir.draft_refused`, gate construction) becomes one precise request; a
re-refusal never opens a second; an answer that still does not route stays open; an answer that
routes is drafted under `draft:<slug>:enrich:<round>` and reaches compile; MAX_ROUNDS answers
exhaust it for good; a fresh process reads the same state.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_enrichment_requests.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import dataclasses
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, PatternVersion, Product  # noqa: E402
from brambleloop.creative import enrichment_requests as E  # noqa: E402
from brambleloop.queue.durable import DuplicateJob, JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402

SEED = "woodland-fox-amigurumi"           # a radar seed the fallback refuses (an amigurumi)


def _store():
    path = f"{tempfile.mkdtemp(prefix='a4b_')}/a4b.sqlite"
    db = Database(f"sqlite:///{path}")
    db.create_all()
    Registry(db).seed_defaults()
    return db, path


def _audit(db):
    def write(action, artifact=None, detail=None, session=None, **_kw):
        if session is not None:
            session.add(AuditLog(actor="test", action=action, artifact=artifact,
                                 detail=detail or {}, at=datetime.now(timezone.utc)))
            return
        with db.session() as s:
            s.add(AuditLog(actor="test", action=action, artifact=artifact,
                           detail=detail or {}, at=datetime.now(timezone.utc)))
    return write


def _sweep(db, *, audit=None):
    writer = audit or _audit(db)
    return E.sweep(db, audit=writer, audit_transaction=writer)


def _enqueue(db):
    q = JobQueue(db)

    def enqueue(role, kind, data, **kw):
        try:
            return q.enqueue(role, kind, data, **kw)
        except DuplicateJob:
            return None
    return enqueue


def _payload(seed, **over):
    out = {k: v for k, v in dataclasses.asdict(seed).items() if not isinstance(v, tuple)}
    out.update(pipeline.concept_geometry(seed))
    out.update(over)
    return out


def _established(db, seed):
    with db.session() as s:
        p = Product(slug=seed.slug, title=seed.title)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="0.9.0", cir_json={}, certified=True))


def _run(db, job_type):
    while Worker(db, f"a4b-{job_type}", job_types=[job_type]).run_once():
        pass


def _jobs(db, job_type):
    with db.session() as s:
        return [(j.idempotency_key, j.status, dict(j.outputs or {}), dict(j.inputs or {}))
                for j in s.scalars(select(Job).where(Job.job_type == job_type).order_by(Job.id))]


def test_a_refused_draft_rejects_identity_substitution():
    db, path = _store()
    seed = pipeline._seed_for(SEED)
    _established(db, seed)
    JobQueue(db).enqueue("crochet_engineer", "cir.draft", _payload(seed), priority=0)
    _run(db, "cir.draft")
    assert _jobs(db, "cir.draft")[0][2].get("gate") == "construction"
    JobQueue(db).enqueue("crochet_engineer", "research.enrichment_sweep", {}, priority=0)
    _run(db, "research.enrichment_sweep")
    reqs = E.open_requests(db)
    assert [r["slug"] for r in reqs] == [seed.slug], reqs
    fake = _payload(seed, category="basket", title="Woodland Storage Basket")
    out = E.answer(db, seed.slug, fake, audit=_audit(db), enqueue=_enqueue(db))
    assert out["accepted"] is False and "differs" in out["why"], out
    for modified in (_payload(seed, rationale="invented evidence"),
                     _payload(seed, width_stitches=4),
                     _payload(seed, concept={"title": "unverified"})):
        blocked = E.answer(db, seed.slug, modified, audit=_audit(db), enqueue=_enqueue(db))
        assert blocked["accepted"] is False, blocked
    fresh = Database(f"sqlite:///{path}")
    assert E.open_requests(fresh)[0]["slug"] == seed.slug
    assert len(_jobs(fresh, "cir.draft")) == 1


def test_authoritative_seed_can_redraft_and_reaches_compile():
    db, path = _store()
    seed = pipeline._seed_for("nordic-forest-basket")
    _established(db, seed)
    _audit(db)("cir.draft_refused", artifact=seed.slug, detail={
        "reason": "fixture construction hold", "gate": "construction", "category": seed.category})
    _sweep(db, audit=_audit(db))
    out = E.answer(db, seed.slug, _payload(seed), audit=_audit(db), enqueue=_enqueue(db),
                   audit_transaction=_audit(db), enqueue_transaction=_enqueue(db))
    assert out["accepted"] and out["state"] == E.RESOLVED, out
    fresh = Database(f"sqlite:///{path}")
    _run(fresh, "cir.draft")
    jobs = _jobs(fresh, "cir.draft")
    assert len(jobs) == 1 and jobs[0][2].get("drafted") is True, jobs
    _run(fresh, "cir.compile")
    assert _jobs(fresh, "cir.compile")[-1][2].get("compiled") is True


def test_answers_are_bounded_and_an_exhausted_request_never_reopens():
    db, _path = _store()
    seed = pipeline._seed_for(SEED)
    _audit(db)("cir.draft_refused", artifact=seed.slug, detail={
        "reason": "an amigurumi needs shaped pieces", "gate": "construction",
        "category": seed.category, "needs": "shaped pieces"})
    _sweep(db, audit=_audit(db))
    bad = _payload(seed)
    first = E.answer(db, seed.slug, bad, audit=_audit(db), enqueue=_enqueue(db),
                     audit_transaction=_audit(db))
    second = E.answer(db, seed.slug, bad,
                      audit=_audit(db), enqueue=_enqueue(db), audit_transaction=_audit(db))
    assert first["state"] == E.OPEN and second["state"] == E.EXHAUSTED == "exhausted"
    assert E.MAX_ROUNDS == 2 and _jobs(db, "cir.draft") == []
    _audit(db)("cir.draft_refused", artifact=seed.slug, detail={
        "reason": "refused again for another reason", "gate": "construction",
        "category": seed.category, "needs": "something else"})
    swept = _sweep(db, audit=_audit(db))
    assert swept["opened"] == [] and swept["updated"] == [] and E.open_requests(db) == []
    # a refusal that is not about construction (the funnel) is not Research's to answer
    _audit(db)("cir.draft_refused", artifact="other-slug", detail={
        "reason": "no tournament carried it", "gate": "funnel.may_engineer"})
    assert _sweep(db, audit=_audit(db))["opened"] == []


def test_real_answer_handler_records_atomic_bounded_rounds():
    db, path = _store()
    seed = pipeline._seed_for(SEED)
    _audit(db)("cir.draft_refused", artifact=seed.slug, detail={
        "reason": "shaped pieces needed", "gate": "construction", "category": seed.category})
    _sweep(db, audit=_audit(db))
    for i in range(2):
        JobQueue(db).enqueue("crochet_engineer", "research.enrichment_answer",
                             {"slug": seed.slug, "payload": _payload(seed)},
                             idempotency_key=f"test-answer:{i}")
        _run(db, "research.enrichment_answer")
        db = Database(f"sqlite:///{path}")
    answers = _jobs(db, "research.enrichment_answer")
    assert [row[2]["state"] for row in answers] == [E.OPEN, E.EXHAUSTED]
    assert E.state(db)[seed.slug]["rounds"] == 2
    assert _jobs(db, "cir.draft") == []


def test_unsuccessful_answer_rolls_back_audit_pair_on_failure():
    db, _ = _store()
    seed = pipeline._seed_for(SEED)
    _audit(db)("cir.draft_refused", artifact=seed.slug, detail={
        "reason": "shaped pieces needed", "gate": "construction", "category": seed.category})
    _sweep(db, audit=_audit(db))

    def fails_second(action, *, artifact, detail, session):
        if action == E.REQUESTED:
            raise RuntimeError("simulated audit failure")
        _audit(db)(action, artifact=artifact, detail=detail, session=session)

    import pytest
    with pytest.raises(RuntimeError, match="simulated audit failure"):
        E.answer(db, seed.slug, _payload(seed), audit=_audit(db), enqueue=_enqueue(db),
                 audit_transaction=fails_second)
    assert E.state(db)[seed.slug].get("rounds", 0) == 0
    assert E._rows(db, E.ANSWERED) == []


def test_unsuccessful_answer_without_transactional_auditor_is_held():
    db, _ = _store()
    seed = pipeline._seed_for(SEED)
    _audit(db)("cir.draft_refused", artifact=seed.slug, detail={
        "reason": "shaped pieces needed", "gate": "construction", "category": seed.category})
    _sweep(db, audit=_audit(db))
    result = E.answer(db, seed.slug, _payload(seed), audit=_audit(db), enqueue=_enqueue(db))
    assert not result["accepted"] and "auditor or queue unavailable" in result["why"]
    assert E.state(db)[seed.slug].get("rounds", 0) == 0


def test_concurrent_real_answer_workers_do_not_spend_same_round(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    db, path = _store()
    seed = pipeline._seed_for(SEED)
    _audit(db)("cir.draft_refused", artifact=seed.slug, detail={
        "reason": "shaped pieces needed", "gate": "construction", "category": seed.category})
    _sweep(db, audit=_audit(db))
    for i in range(2):
        JobQueue(db).enqueue("crochet_engineer", "research.enrichment_answer",
                             {"slug": seed.slug, "payload": _payload(seed)},
                             idempotency_key=f"concurrent-answer:{i}")
    barrier = Barrier(2)
    original = E._recheck

    def synchronize(*args, **kwargs):
        result = original(*args, **kwargs)
        barrier.wait(timeout=15)
        return result

    monkeypatch.setattr(E, "_recheck", synchronize)

    def run(i):
        fresh = Database(path if path.startswith("postgresql") else f"sqlite:///{path}")
        return Worker(fresh, f"answer-{i}", job_types=["research.enrichment_answer"]).run_once()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(pool.map(run, range(2)))
    answers = _jobs(db, "research.enrichment_answer")
    assert sorted(row[2]["state"] for row in answers) == ["changed", "open"]
    assert len(E._rows(db, E.ANSWERED)) == 1
    assert E.state(db)[seed.slug]["rounds"] == 1


def test_real_answer_handler_queues_approved_draft_and_audits_in_transaction():
    db, _ = _store()
    seed = pipeline._seed_for("nordic-forest-basket")
    _established(db, seed)
    _audit(db)("cir.draft_refused", artifact=seed.slug, detail={
        "reason": "fixture", "gate": "construction", "category": seed.category})
    _sweep(db, audit=_audit(db))
    JobQueue(db).enqueue("crochet_engineer", "research.enrichment_answer",
                         {"slug": seed.slug, "payload": _payload(seed)},
                         idempotency_key="test:answer:approved")
    _run(db, "research.enrichment_answer")
    answers = _jobs(db, "research.enrichment_answer")
    assert answers[0][2]["accepted"] is True
    assert E.state(db)[seed.slug]["state"] == E.RESOLVED
    assert len(_jobs(db, "cir.draft")) == 1
    from brambleloop.runtime.lineage import JobLink
    with db.session() as session:
        assert session.scalar(select(JobLink).where(JobLink.child_id == answers[0][2]["job"]))


def test_stale_answer_worker_cannot_record_a_round():
    import pytest
    from brambleloop.queue.effects import LeaseLost
    from brambleloop.runtime.worker import JobContext, handlers
    from brambleloop.core.models import Phase
    from sqlalchemy import update

    db, _ = _store()
    seed = pipeline._seed_for(SEED)
    _audit(db)("cir.draft_refused", artifact=seed.slug, detail={
        "reason": "fixture", "gate": "construction", "category": seed.category})
    _sweep(db, audit=_audit(db))
    q = JobQueue(db)
    q.enqueue("crochet_engineer", "research.enrichment_answer",
              {"slug": seed.slug, "payload": _payload(seed)}, idempotency_key="answer:stale")
    claimed = q.claim("old-answer", ["research.enrichment_answer"])
    ctx = JobContext(job=claimed, db=db, queue=q, registry=Registry(db), phase=Phase.SHADOW)
    with db.session() as session:
        session.execute(update(Job).where(Job.id == claimed.id).values(lease_token="new-attempt"))
    with pytest.raises(LeaseLost):
        handlers.get("research.enrichment_answer")(ctx)
    assert E.state(db)[seed.slug].get("rounds", 0) == 0
    assert E._rows(db, E.ANSWERED) == []


def test_answer_worker_refuses_changed_persisted_producer():
    import pytest
    from brambleloop.queue.effects import LeaseLost
    from brambleloop.runtime.worker import JobContext, handlers
    from brambleloop.core.models import Phase
    from sqlalchemy import update

    for change in ({"inputs": {"slug": "other", "payload": {}}},
                   {"agent": "validator"}, {"job_type": "cir.draft"},
                   {"leased_by": "other-worker"}):
        db, _ = _store()
        seed = pipeline._seed_for(SEED)
        _audit(db)("cir.draft_refused", artifact=seed.slug, detail={
            "reason": "fixture", "gate": "construction", "category": seed.category})
        _sweep(db, audit=_audit(db))
        q = JobQueue(db)
        q.enqueue("crochet_engineer", "research.enrichment_answer",
                  {"slug": seed.slug, "payload": _payload(seed)}, idempotency_key="answer:changed")
        claimed = q.claim("answer-worker", ["research.enrichment_answer"])
        ctx = JobContext(job=claimed, db=db, queue=q, registry=Registry(db), phase=Phase.SHADOW)
        with db.session() as session:
            session.execute(update(Job).where(Job.id == claimed.id).values(**change))
        with pytest.raises(LeaseLost):
            handlers.get("research.enrichment_answer")(ctx)
        assert E.state(db)[seed.slug].get("rounds", 0) == 0
        assert E._rows(db, E.ANSWERED) == []


def test_competing_success_and_failed_answers_cannot_commit_the_same_round(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock

    db, path = _store()
    seed = pipeline._seed_for("nordic-forest-basket")
    _audit(db)("cir.draft_refused", artifact=seed.slug, detail={
        "reason": "fixture", "gate": "construction", "category": seed.category})
    _sweep(db, audit=_audit(db))
    for i in range(2):
        JobQueue(db).enqueue("crochet_engineer", "research.enrichment_answer",
                             {"slug": seed.slug, "payload": _payload(seed)},
                             idempotency_key=f"answer:mixed:{i}")
    barrier, lock, calls = Barrier(2), Lock(), []

    def conflicting_recheck(*_args, **_kwargs):
        # Model two code/policy snapshots disagreeing about the same answer.
        with lock:
            calls.append(len(calls))
            n = calls[-1]
        barrier.wait(timeout=15)
        return [] if n == 0 else [{"field": "construction", "why": "still missing"}]

    monkeypatch.setattr(E, "_recheck", conflicting_recheck)

    def run(i):
        fresh = Database(path if path.startswith("postgresql") else f"sqlite:///{path}")
        return Worker(fresh, f"mixed-answer-{i}",
                      job_types=["research.enrichment_answer"]).run_once()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(pool.map(run, range(2)))
    outputs = [row[2] for row in _jobs(db, "research.enrichment_answer")]
    assert sum(out.get("state") == "changed" for out in outputs) == 1
    answers = E._rows(db, E.ANSWERED)
    assert len(answers) == 1 and answers[0][2]["round"] == 1
    if answers[0][2]["state"] == E.RESOLVED:
        assert len(_jobs(db, "cir.draft")) == 1
    else:
        assert _jobs(db, "cir.draft") == []


def test_sweep_and_answer_serialize_request_state(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    db, path = _store()
    seed = pipeline._seed_for(SEED)
    audit = _audit(db)
    audit("cir.draft_refused", artifact=seed.slug, detail={"gate": "construction",
          "reason": "first", "category": seed.category})
    _sweep(db, audit=audit)
    audit("cir.draft_refused", artifact=seed.slug, detail={"gate": "construction",
          "reason": "changed", "category": seed.category})
    q = JobQueue(db)
    q.enqueue("crochet_engineer", "research.enrichment_sweep", {}, idempotency_key="race:sweep")
    q.enqueue("crochet_engineer", "research.enrichment_answer",
              {"slug": seed.slug, "payload": _payload(seed)}, idempotency_key="race:answer")
    sweep_job = q.claim("race-sweep", ["research.enrichment_sweep"])
    answer_job = q.claim("race-answer", ["research.enrichment_answer"])
    from brambleloop.runtime import lineage
    lineage.ensure_table(db)
    entered, release, answer_ready = Event(), Event(), Event()
    original = E._holds
    original_recheck = E._recheck

    def pause_sweep(*args, **kwargs):
        result = original(*args, **kwargs)
        entered.set()
        assert release.wait(timeout=15)
        return result

    monkeypatch.setattr(E, "_holds", pause_sweep)
    def observed_answer(*args, **kwargs):
        result = original_recheck(*args, **kwargs)
        answer_ready.set()
        return result
    monkeypatch.setattr(E, "_recheck", observed_answer)

    def run(kind):
        from brambleloop.core.models import Phase
        from brambleloop.runtime.worker import JobContext, handlers
        fresh = Database(path if path.startswith("postgresql") else f"sqlite:///{path}")
        job = sweep_job if kind == "research.enrichment_sweep" else answer_job
        ctx = JobContext(job=job, db=fresh, queue=JobQueue(fresh),
                         registry=Registry(fresh), phase=Phase.SHADOW)
        return handlers.get(kind)(ctx)

    with ThreadPoolExecutor(max_workers=2) as pool:
        sweep = pool.submit(run, "research.enrichment_sweep")
        assert entered.wait(timeout=15)
        answer = pool.submit(run, "research.enrichment_answer")
        assert answer_ready.wait(timeout=15)
        release.set()
        assert sweep.result(timeout=20)["work_done"] == 1
        assert answer.result(timeout=20)["state"] == "changed"
    assert E._rows(db, E.ANSWERED) == []


def test_different_old_refusals_do_not_cause_endless_audit_churn():
    db, path = _store()
    audit = _audit(db)
    for reason in ("first missing piece", "second missing piece"):
        audit("cir.draft_refused", artifact=SEED, detail={"reason": reason,
              "gate": "construction", "category": "amigurumi", "needs": reason})
    assert _sweep(db, audit=audit)["work_done"] == 1
    assert E.open_requests(db)[0]["asks"][0]["why"] == "second missing piece"
    for _ in range(3):
        assert _sweep(db, audit=audit)["work_done"] == 0
    fresh = Database(f"sqlite:///{path}")
    assert _sweep(fresh, audit=_audit(fresh))["work_done"] == 0
    with fresh.session() as session:
        rows = list(session.scalars(select(AuditLog).where(AuditLog.action == E.REQUESTED)))
    assert len(rows) == 1, rows


def test_last_refused_redraft_is_exhausted_and_duplicate_enqueue_is_not_success():
    db, path = _store()
    seed_slug = "nordic-forest-basket"
    audit = _audit(db)
    audit("cir.draft_refused", artifact=seed_slug, detail={"gate": "construction",
          "reason": "first", "category": "basket"})
    _sweep(db, audit=audit)
    good = _payload(pipeline._seed_for(seed_slug))
    key = f"draft:{seed_slug}:enrich:1"
    JobQueue(db).enqueue("crochet_engineer", "cir.draft", good, idempotency_key=key)
    duplicate = E.answer(db, seed_slug, good, audit=audit, enqueue=_enqueue(db),
                         audit_transaction=audit, enqueue_transaction=_enqueue(db))
    assert duplicate["accepted"] is False and E.state(db)[seed_slug]["state"] == E.OPEN
    audit(E.ANSWERED, artifact=seed_slug, detail={"round": E.MAX_ROUNDS, "state": E.RESOLVED})
    audit("cir.draft_refused", artifact=seed_slug, detail={"gate": "construction",
          "reason": "last attempt refused", "category": "basket"})
    outcome = _sweep(db, audit=audit)
    assert outcome["updated"] == [seed_slug], outcome
    fresh = Database(f"sqlite:///{path}")
    assert E.state(fresh)[seed_slug]["state"] == E.EXHAUSTED
    assert _sweep(fresh, audit=_audit(fresh))["work_done"] == 0


def test_restart_recovers_exact_queued_draft_when_answer_audit_was_interrupted():
    db, path = _store()
    seed_slug = "nordic-forest-basket"
    audit = _audit(db)
    audit("cir.draft_refused", artifact=seed_slug, detail={"gate": "construction",
          "reason": "shaped pieces needed", "category": "basket"})
    _sweep(db, audit=audit)
    good = _payload(pipeline._seed_for(seed_slug))
    def interrupted(action, **kwargs):
        if action == E.ANSWERED:
            raise RuntimeError("simulated interruption after durable queue insert")
        return audit(action, **kwargs)
    try:
        E.answer(db, seed_slug, good, audit=interrupted, enqueue=_enqueue(db),
                 audit_transaction=interrupted, enqueue_transaction=_enqueue(db))
        assert False, "interruption did not occur"
    except RuntimeError:
        pass
    fresh = Database(f"sqlite:///{path}")
    assert E.state(fresh)[seed_slug]["state"] == E.OPEN
    assert _jobs(fresh, "cir.draft") == []  # queue insert and audit rolled back together
    recovered = E.answer(fresh, seed_slug, good, audit=_audit(fresh), enqueue=_enqueue(fresh),
                         audit_transaction=_audit(fresh), enqueue_transaction=_enqueue(fresh))
    assert recovered["accepted"] is True and recovered["state"] == E.RESOLVED, recovered
    assert len(_jobs(fresh, "cir.draft")) == 1
    assert E.state(fresh)[seed_slug]["state"] == E.RESOLVED


def test_concurrent_answers_cannot_queue_two_drafts_for_one_round(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    db, path = _store()
    seed_slug = "nordic-forest-basket"
    audit = _audit(db)
    audit("cir.draft_refused", artifact=seed_slug, detail={"gate": "construction",
          "reason": "shaped pieces needed", "category": "basket"})
    _sweep(db, audit=audit)
    barrier = Barrier(2)
    original = E._recheck
    def synchronized_recheck(*args, **kwargs):
        result = original(*args, **kwargs)
        barrier.wait(timeout=10)
        return result
    monkeypatch.setattr(E, "_recheck", synchronized_recheck)
    def answer(title):
        fresh = Database(f"sqlite:///{path}")
        real_enqueue = _enqueue(fresh)
        return E.answer(fresh, seed_slug, _payload(pipeline._seed_for(seed_slug)), audit=_audit(fresh),
                        enqueue=real_enqueue, audit_transaction=_audit(fresh),
                        enqueue_transaction=real_enqueue)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(answer, ("Everyday Basket", "Storage Basket")))
    assert any(r.get("accepted") is True for r in results), results
    jobs = _jobs(db, "cir.draft")
    assert len(jobs) == 1 and jobs[0][0] == f"draft:{seed_slug}:enrich:1", jobs


def test_construction_precheck_matches_real_tapestry_palette_refusal():
    db, _ = _store()
    payload = {"slug": "fixture-unpaired-tapestry", "title": "Tapestry Basket",
               "category": "basket", "risk_class": "A", "rationale": "fixture",
               "stitch_repeat": [["sc", 4]], "width_stitches": 48, "rows": 14,
               "colors": {"a": "#fefefe"}}
    missing = E._recheck({"kind": "radar", "category": "basket"}, payload, None)
    assert missing and "two distinct colours" in str(missing), missing
    JobQueue(db).enqueue("crochet_engineer", "cir.draft", payload)
    _run(db, "cir.draft")
    jobs = _jobs(db, "cir.draft")
    assert len(jobs) == 1 and jobs[0][2].get("gate") == "construction", jobs
    assert "two distinct colours" in str(jobs[0][2]), jobs


def test_real_draft_refusal_before_answer_audit_reopens_by_job_identity():
    db, path = _store()
    slug = "nordic-forest-basket"
    seed = pipeline._seed_for(slug)
    _established(db, seed)
    audit = _audit(db)
    audit("cir.draft_refused", artifact=slug, detail={"gate": "construction",
          "reason": "original", "category": seed.category})
    _sweep(db, audit=audit)
    # Historical queue entries could be visible before ANSWERED. Preserve
    # recovery of those rows even though new enqueue+audit is atomic.
    payload = _payload(seed)
    data = {**payload, "enrichment_round": 1, "enrichment_fingerprint": E.fingerprint(payload),
            "enrichment_approval_sha256": E._approved_binding(db, slug)}
    job = _enqueue(db)("crochet_engineer", "cir.draft", data,
                       idempotency_key=f"draft:{slug}:enrich:1")
    from brambleloop.creative import fallback_constructions as FC
    old = FC.NEEDS.get("basket")
    FC.NEEDS["basket"] = "fixture: new construction evidence required"
    try:
        _run(db, "cir.draft")
    finally:
        if old is None:
            del FC.NEEDS["basket"]
        else:
            FC.NEEDS["basket"] = old
    audit(E.ANSWERED, artifact=slug, detail={"round": 1, "state": E.RESOLVED,
                                             "fingerprint": E.fingerprint(payload), "job": job.id})
    jobs = _jobs(db, "cir.draft")
    assert len(jobs) == 1 and jobs[0][2].get("gate") == "construction", jobs
    fresh = Database(f"sqlite:///{path}")
    before = E.state(fresh)[slug]
    assert before["state"] == E.RESOLVED
    outcome = _sweep(fresh, audit=_audit(fresh))
    assert outcome["updated"] == [slug], outcome
    assert E.state(fresh)[slug]["state"] == E.OPEN
    assert E.state(fresh)[slug]["rounds"] == 1
    assert _sweep(fresh, audit=_audit(fresh))["work_done"] == 0


def test_queued_enrichment_refuses_changed_or_withdrawn_approval_at_real_handler():
    from brambleloop.radar import intake
    for change in ("unchanged", "title", "withdrawn"):
        db, path = _store()
        intake._ensure(db)
        original = dataclasses.asdict(pipeline._seed_for("nordic-forest-basket"))
        slug = f"fixture-approved-basket-{change}"
        original.update(slug=slug, title="Original Storage Basket")
        with db.session() as session:
            session.add(intake.RadarConcept(slug=slug, state=intake.APPROVED,
                source=intake.SOURCE_FAMILY, source_ref=f"fixture:{change}",
                fingerprint=("a" if change == "title" else "b") * 64,
                seed=original, concept={}, brief={}, evidence=[], quality=1.0))
        seed = pipeline._seed_for(slug, db)
        assert seed is not None
        _established(db, seed)
        audit = _audit(db)
        audit("cir.draft_refused", artifact=slug, detail={"gate": "construction",
              "reason": "fixture", "category": "basket"})
        _sweep(db, audit=audit)
        out = E.answer(db, slug, _payload(seed), audit=audit, enqueue=_enqueue(db))
        assert out["accepted"] is False and "atomic" in out["why"], out
        # A previously queued dynamic job must also be held, even if it was
        # accepted by an older version before the fail-closed policy existed.
        data = _payload(seed)
        data["enrichment_round"] = 1
        data["enrichment_fingerprint"] = E.fingerprint(_payload(seed))
        data["enrichment_approval_sha256"] = E._approved_binding(db, slug)
        JobQueue(db).enqueue("crochet_engineer", "cir.draft", data,
                             idempotency_key=f"draft:{slug}:enrich:1")
        with db.session() as session:
            row = session.scalar(select(intake.RadarConcept).where(intake.RadarConcept.slug == slug))
            if change == "title":
                row.seed = {**row.seed, "title": "Revised Storage Basket"}
            elif change == "withdrawn":
                row.state = intake.WITHDRAWN
        fresh = Database(f"sqlite:///{path}")
        _run(fresh, "cir.draft")
        jobs = _jobs(fresh, "cir.draft")
        assert len(jobs) == 1 and jobs[0][2].get("gate") == "enrichment.authority", jobs
        assert jobs[0][2].get("drafted") is False
        assert not _jobs(fresh, "cir.compile")


def test_the_sweep_is_registered_scheduled_and_banded():
    from brambleloop.runtime.worker import CADENCES
    from brambleloop.swarm import orchestrate

    assert ("enrichment_sweep", "crochet_engineer", "research.enrichment_sweep",
            60 * 60) in CADENCES
    assert "research.enrichment_sweep" in orchestrate.JOB_BANDS


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:700])
                import traceback
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
