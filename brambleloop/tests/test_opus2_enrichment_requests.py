"""A4b: a refused draft goes back to Research and returns as a new draft (owner directive
2026-11-02; queue Q26).

On a real SQLite file through the real Worker and the registered handlers: a radar concept the
fallback refuses (`cir.draft_refused`, gate construction) becomes one precise request; a
re-refusal never opens a second; an answer that still does not route stays open; an answer that
routes is drafted under `draft:<slug>:<fingerprint>` and reaches compile; MAX_ROUNDS answers
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


def test_a_refused_draft_is_one_request_then_a_new_draft_that_reaches_compile():
    db, path = _store()
    seed = pipeline._seed_for(SEED)
    _established(db, seed)
    JobQueue(db).enqueue("crochet_engineer", "cir.draft", _payload(seed), priority=0)
    _run(db, "cir.draft")
    assert _jobs(db, "cir.draft")[0][2].get("gate") == "construction"
    # the sweep runs as the registered job
    JobQueue(db).enqueue("crochet_engineer", "research.enrichment_sweep", {}, priority=0)
    _run(db, "research.enrichment_sweep")
    reqs = E.open_requests(db)
    assert [r["slug"] for r in reqs] == [seed.slug], reqs
    ask = reqs[0]["asks"][0]
    assert ask["field"] == "construction" and ask["why"] and ask["needs"], ask
    # the same refusal recorded again opens nothing new
    _audit(db)("cir.draft_refused", artifact=seed.slug, detail={
        "reason": ask["why"], "gate": "construction", "category": seed.category,
        "needs": ask["needs"]})
    swept = E.sweep(db, audit=_audit(db))
    assert swept["opened"] == [] and swept["updated"] == [], swept
    # an answer that still does not route stays open, with what is missing
    still = E.answer(db, seed.slug, _payload(seed, title="Woodland Fox Amigurumi"),
                     audit=_audit(db), enqueue=_enqueue(db))
    assert still["state"] == E.OPEN and still["still_missing"], still
    # Research re-concepts it as something the fallback makes: drafted under a fresh key
    good = _payload(seed, category="basket", title="Woodland Storage Basket")
    out = E.answer(db, seed.slug, good, audit=_audit(db), enqueue=_enqueue(db))
    assert out["accepted"] and out["state"] == E.RESOLVED and out["round"] == 2, out
    keys = [k for k, *_ in _jobs(db, "cir.draft")]
    assert f"draft:{seed.slug}:{out['fingerprint']}" in keys, keys
    # a restart reads the same state, and the queued draft reaches compile
    fresh = Database(f"sqlite:///{path}")
    assert E.open_requests(fresh) == []
    _run(fresh, "cir.draft")
    redraft = [j for j in _jobs(fresh, "cir.draft") if (j[0] or "").endswith(out["fingerprint"])][0]
    assert redraft[1] == JobStatus.DONE and redraft[2].get("drafted") is True, redraft
    _run(fresh, "cir.compile")
    compiled = _jobs(fresh, "cir.compile")
    assert compiled and compiled[-1][2].get("compiled") is True, compiled
    # the same answer again drafts nothing (the request is resolved, the key is spent)
    again = E.answer(fresh, seed.slug, good, audit=_audit(fresh), enqueue=_enqueue(fresh))
    assert again["accepted"] is False
    assert len([k for k, *_ in _jobs(fresh, "cir.draft") if out["fingerprint"] in (k or "")]) == 1


def test_answers_are_bounded_and_an_exhausted_request_never_reopens():
    db, _path = _store()
    seed = pipeline._seed_for(SEED)
    _audit(db)("cir.draft_refused", artifact=seed.slug, detail={
        "reason": "an amigurumi needs shaped pieces", "gate": "construction",
        "category": seed.category, "needs": "shaped pieces"})
    E.sweep(db, audit=_audit(db))
    bad = _payload(seed, title="Woodland Fox Amigurumi")
    first = E.answer(db, seed.slug, bad, audit=_audit(db), enqueue=_enqueue(db))
    second = E.answer(db, seed.slug, {**bad, "title": "Sleepy Fox Amigurumi"},
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
