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
    def write(action, artifact=None, detail=None, **_kw):
        with db.session() as s:
            s.add(AuditLog(actor="test", action=action, artifact=artifact,
                           detail=detail or {}, at=datetime.now(timezone.utc)))
    return write


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
    E.sweep(db, audit=_audit(db))
    out = E.answer(db, seed.slug, _payload(seed), audit=_audit(db), enqueue=_enqueue(db))
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
    E.sweep(db, audit=_audit(db))
    bad = _payload(seed)
    first = E.answer(db, seed.slug, bad, audit=_audit(db), enqueue=_enqueue(db))
    second = E.answer(db, seed.slug, bad,
                      audit=_audit(db), enqueue=_enqueue(db))
    assert first["state"] == E.OPEN and second["state"] == E.EXHAUSTED == "exhausted"
    assert E.MAX_ROUNDS == 2 and _jobs(db, "cir.draft") == []
    _audit(db)("cir.draft_refused", artifact=seed.slug, detail={
        "reason": "refused again for another reason", "gate": "construction",
        "category": seed.category, "needs": "something else"})
    swept = E.sweep(db, audit=_audit(db))
    assert swept["opened"] == [] and swept["updated"] == [] and E.open_requests(db) == []
    # a refusal that is not about construction (the funnel) is not Research's to answer
    _audit(db)("cir.draft_refused", artifact="other-slug", detail={
        "reason": "no tournament carried it", "gate": "funnel.may_engineer"})
    assert E.sweep(db, audit=_audit(db))["opened"] == []


def test_different_old_refusals_do_not_cause_endless_audit_churn():
    db, path = _store()
    audit = _audit(db)
    for reason in ("first missing piece", "second missing piece"):
        audit("cir.draft_refused", artifact=SEED, detail={"reason": reason,
              "gate": "construction", "category": "amigurumi", "needs": reason})
    assert E.sweep(db, audit=audit)["work_done"] == 1
    assert E.open_requests(db)[0]["asks"][0]["why"] == "second missing piece"
    for _ in range(3):
        assert E.sweep(db, audit=audit)["work_done"] == 0
    fresh = Database(f"sqlite:///{path}")
    assert E.sweep(fresh, audit=_audit(fresh))["work_done"] == 0
    with fresh.session() as session:
        rows = list(session.scalars(select(AuditLog).where(AuditLog.action == E.REQUESTED)))
    assert len(rows) == 1, rows


def test_last_refused_redraft_is_exhausted_and_duplicate_enqueue_is_not_success():
    db, path = _store()
    seed_slug = "nordic-forest-basket"
    audit = _audit(db)
    audit("cir.draft_refused", artifact=seed_slug, detail={"gate": "construction",
          "reason": "first", "category": "basket"})
    E.sweep(db, audit=audit)
    good = _payload(pipeline._seed_for(seed_slug))
    key = f"draft:{seed_slug}:enrich:1"
    JobQueue(db).enqueue("crochet_engineer", "cir.draft", good, idempotency_key=key)
    duplicate = E.answer(db, seed_slug, good, audit=audit, enqueue=_enqueue(db))
    assert duplicate["accepted"] is False and E.state(db)[seed_slug]["state"] == E.OPEN
    audit(E.ANSWERED, artifact=seed_slug, detail={"round": E.MAX_ROUNDS, "state": E.RESOLVED})
    audit("cir.draft_refused", artifact=seed_slug, detail={"gate": "construction",
          "reason": "last attempt refused", "category": "basket"})
    outcome = E.sweep(db, audit=audit)
    assert outcome["updated"] == [seed_slug], outcome
    fresh = Database(f"sqlite:///{path}")
    assert E.state(fresh)[seed_slug]["state"] == E.EXHAUSTED
    assert E.sweep(fresh, audit=_audit(fresh))["work_done"] == 0


def test_restart_recovers_exact_queued_draft_when_answer_audit_was_interrupted():
    db, path = _store()
    seed_slug = "nordic-forest-basket"
    audit = _audit(db)
    audit("cir.draft_refused", artifact=seed_slug, detail={"gate": "construction",
          "reason": "shaped pieces needed", "category": "basket"})
    E.sweep(db, audit=audit)
    good = _payload(pipeline._seed_for(seed_slug))
    def interrupted(action, **kwargs):
        if action == E.ANSWERED:
            raise RuntimeError("simulated interruption after durable queue insert")
        return audit(action, **kwargs)
    try:
        E.answer(db, seed_slug, good, audit=interrupted, enqueue=_enqueue(db))
        assert False, "interruption did not occur"
    except RuntimeError:
        pass
    fresh = Database(f"sqlite:///{path}")
    assert E.state(fresh)[seed_slug]["state"] == E.OPEN
    recovered = E.answer(fresh, seed_slug, good, audit=_audit(fresh), enqueue=_enqueue(fresh))
    assert recovered["accepted"] is True and recovered["state"] == E.RESOLVED, recovered
    assert len(_jobs(fresh, "cir.draft")) == 1
    assert E.state(fresh)[seed_slug]["state"] == E.RESOLVED


def test_concurrent_answers_cannot_queue_two_drafts_for_one_round():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    db, path = _store()
    seed_slug = "nordic-forest-basket"
    audit = _audit(db)
    audit("cir.draft_refused", artifact=seed_slug, detail={"gate": "construction",
          "reason": "shaped pieces needed", "category": "basket"})
    E.sweep(db, audit=audit)
    barrier = Barrier(2)
    def answer(title):
        fresh = Database(f"sqlite:///{path}")
        real_enqueue = _enqueue(fresh)
        def synchronized_enqueue(*args, **kwargs):
            barrier.wait(timeout=10)
            return real_enqueue(*args, **kwargs)
        return E.answer(fresh, seed_slug, _payload(pipeline._seed_for(seed_slug)), audit=_audit(fresh),
                        enqueue=synchronized_enqueue)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(answer, ("Everyday Basket", "Storage Basket")))
    assert any(r.get("accepted") is True for r in results), results
    jobs = _jobs(db, "cir.draft")
    assert len(jobs) == 1 and jobs[0][0] == f"draft:{seed_slug}:enrich:1", jobs


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
