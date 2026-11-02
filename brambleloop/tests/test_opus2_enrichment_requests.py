"""OPUS2: the research-enrichment consumer (OPUS2R-7; owner directive 2026-11-02, item 5).

A brief the construction registry held for research enrichment becomes one precise,
deduplicated request for Research; Research's answer is re-checked before any draft; a
resolved answer is drafted under a fresh key through the real handler; an answer that still
lacks something stays open until MAX_ROUNDS, then the request is exhausted. Every state is
an audit row, so a fresh process (a restart) reads exactly the same state.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_enrichment_requests.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from test_opus2_research_to_development import _brief  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job  # noqa: E402
from brambleloop.creative import construction_registry as R  # noqa: E402
from brambleloop.creative import enrichment_requests as E  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402


def _db():
    path = f"{tempfile.mkdtemp(prefix='opus2_enrich_')}/d.sqlite"
    db = Database(f"sqlite:///{path}")
    db.create_all()
    from brambleloop.agents.registry import Registry

    Registry(db).seed_defaults()
    return db, path


def _audit(db):
    def write(action, artifact=None, detail=None, **_kw):
        with db.session() as s:
            s.add(AuditLog(actor="test", action=action, artifact=artifact,
                           detail=detail or {}, at=datetime.now(timezone.utc)))
    return write


def _ctx(db, concept, brief=None):
    emitted = []
    job = SimpleNamespace(inputs={"slug": concept["key"], "concept": concept,
                                  "brief": brief or {}})
    ctx = SimpleNamespace(db=db, job=job, audit=_audit(db),
                          enqueue=lambda role, kind, data, **kw: emitted.append(
                              (kind, data, kw)))
    return ctx, emitted


def _hold(db, concept, brief=None):
    ctx, emitted = _ctx(db, concept, brief)
    out = pipeline._draft_creative(ctx, concept["key"])
    assert out.get("held") is True and emitted == [], out
    return out


def test_a_held_brief_becomes_one_precise_request_and_an_engine_hold_none():
    db, _path = _db()
    fox = _brief("brief-fox-toy", "toy", "amigurumi_shaping", "fox", palette="caramel",
                 title="Fox Amigurumi")
    heart = _brief("brief-heart", "basket", "tapestry", "unicorn", title="Unicorn Tapestry Basket")
    mosaic = _brief("brief-mosaic", "basket", "mosaic_overlay", "diamond")
    for c in (fox, heart, mosaic):
        _hold(db, c)
    _hold(db, fox)                                    # the same brief held again
    out = E.sweep(db, audit=_audit(db))
    assert sorted(out["opened"]) == ["brief-fox-toy", "brief-heart"], out
    assert E.sweep(db, audit=_audit(db))["opened"] == []          # no duplicate request
    reqs = {r["slug"]: r for r in E.open_requests(db)}
    assert set(reqs) == {"brief-fox-toy", "brief-heart"}, reqs     # mosaic: an engine hold
    fox_motif = next(a for a in reqs["brief-fox-toy"]["asks"] if a["field"] == "motif")
    assert set(fox_motif["accepts"]) >= {"bear", "bunny"}, fox_motif
    heart_motif = next(a for a in reqs["brief-heart"]["asks"] if a["field"] == "motif")
    assert "heart" in heart_motif["accepts"] and "diamond" in heart_motif["accepts"]
    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == E.REQUESTED)))
    assert len(rows) == 2, [r.artifact for r in rows]
    # a hold that also waits on an engine decision is not Research's to answer
    _audit(db)(R.HELD_ACTION, artifact="brief-mixed", detail={
        "request": {"form": "basket", "family": "tapestry"},
        "unresolved": [{"field": "motif", "why": "x", "resolved_by": R.ENRICH},
                       {"field": "dimensions_cm", "why": "y", "resolved_by": R.ENGINE}]})
    assert E.sweep(db, audit=_audit(db))["opened"] == []


def test_an_answer_that_resolves_is_drafted_under_a_fresh_key_through_the_handler():
    db, _path = _db()
    fox = _brief("brief-fox-toy", "toy", "amigurumi_shaping", "fox", palette="caramel",
                 title="Fox Amigurumi")
    _hold(db, fox)
    E.sweep(db, audit=_audit(db))
    enriched = {**fox, "motif": "bear", "title": "Bear Amigurumi"}
    queued = []
    out = E.answer(db, "brief-fox-toy", enriched, {}, audit=_audit(db),
                   enqueue=lambda role, kind, data, **kw: queued.append((role, kind, data, kw)))
    assert out["accepted"] is True and out["state"] == E.RESOLVED, out
    role, kind, data, kw = queued[0]
    assert (role, kind) == ("crochet_engineer", "cir.draft")
    assert kw["idempotency_key"] == "draft:brief-fox-toy:enrich:1", kw
    assert E.open_requests(db) == []
    # the enqueued payload drafts through the real creative handler
    ctx, emitted = _ctx(db, data["concept"], data["brief"])
    drafted = pipeline._draft_creative(ctx, "brief-fox-toy")
    assert drafted["drafted"] is True and drafted["construction"] == "amigurumi", drafted
    assert emitted and emitted[0][0] == "cir.compile"
    # a second answer to a resolved request is refused (no duplicate draft)
    again = E.answer(db, "brief-fox-toy", enriched, {}, audit=_audit(db),
                     enqueue=lambda *a, **k: queued.append(a))
    assert again["accepted"] is False and len(queued) == 1, again


def test_an_answer_that_still_lacks_something_stays_open_then_is_exhausted():
    db, _path = _db()
    fox = _brief("brief-fox-toy", "toy", "amigurumi_shaping", "fox", palette="caramel",
                 title="Fox Amigurumi")
    _hold(db, fox)
    E.sweep(db, audit=_audit(db))
    queued = []
    enqueue = lambda *a, **k: queued.append(a)      # noqa: E731
    first = E.answer(db, "brief-fox-toy", {**fox, "motif": "owl"}, {}, audit=_audit(db),
                     enqueue=enqueue)
    assert first["state"] == E.OPEN and first["round"] == 1, first
    assert {u["field"] for u in first["still_missing"]} == {"motif"}, first
    assert [r["slug"] for r in E.open_requests(db)] == ["brief-fox-toy"]
    second = E.answer(db, "brief-fox-toy", {**fox, "motif": "cat"}, {}, audit=_audit(db),
                      enqueue=enqueue)
    assert second["state"] == E.EXHAUSTED and second["round"] == E.MAX_ROUNDS == 2, second
    assert E.open_requests(db) == [] and queued == []
    third = E.answer(db, "brief-fox-toy", {**fox, "motif": "bear", "title": "Bear Amigurumi"},
                     {}, audit=_audit(db), enqueue=enqueue)
    assert third["accepted"] is False and queued == [], third
    # held again later, even for a different reason: an exhausted request is not re-opened
    _hold(db, {**fox, "motif": "owl"})
    swept = E.sweep(db, audit=_audit(db))
    assert swept["opened"] == [] and swept["updated"] == [] and E.open_requests(db) == [], swept


def test_a_resolved_brief_held_again_reopens_once_with_its_rounds_counted():
    db, _path = _db()
    fox = _brief("brief-fox-toy", "toy", "amigurumi_shaping", "fox", palette="caramel",
                 title="Fox Amigurumi")
    _hold(db, fox)
    E.sweep(db, audit=_audit(db))
    E.answer(db, "brief-fox-toy", {**fox, "motif": "bear", "title": "Bear Amigurumi"}, {},
             audit=_audit(db), enqueue=lambda *a, **k: None)
    _hold(db, {**fox, "motif": "bear", "title": "Juniper Friend"})   # the re-draft is held
    out = E.sweep(db, audit=_audit(db))
    assert out["updated"] == ["brief-fox-toy"] and len(E.open_requests(db)) == 1, out
    last = E.answer(db, "brief-fox-toy", {**fox, "motif": "bear", "title": "Bear Amigurumi"},
                    {}, audit=_audit(db), enqueue=lambda *a, **k: None)
    assert last["state"] == E.RESOLVED and last["round"] == 2, last
    _hold(db, {**fox, "motif": "bear", "title": "Woodland Keepsake"})
    assert E.sweep(db, audit=_audit(db))["updated"] == []          # no round left


def test_state_survives_a_restart_and_the_job_runs_through_the_worker():
    db, path = _db()
    fox = _brief("brief-fox-toy", "toy", "amigurumi_shaping", "fox", palette="caramel",
                 title="Fox Amigurumi")
    _hold(db, fox)
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    JobQueue(db).enqueue("crochet_engineer", "research.enrichment_sweep", {}, priority=0)
    Worker(db, "w-enrich", job_types=["research.enrichment_sweep"]).run_once()
    with db.session() as s:
        job = s.scalar(select(Job).where(Job.job_type == "research.enrichment_sweep"))
        assert job.last_error is None, job.last_error
    restarted = Database(f"sqlite:///{path}")            # a fresh process on the same store
    assert [r["slug"] for r in E.open_requests(restarted)] == ["brief-fox-toy"]
    assert E.sweep(restarted, audit=_audit(restarted))["opened"] == []
    from brambleloop.runtime.worker import CADENCES

    assert ("enrichment_sweep", "crochet_engineer", "research.enrichment_sweep",
            60 * 60) in CADENCES
    assert R.ENRICH == "research_enrichment"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:600])
                import traceback
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
