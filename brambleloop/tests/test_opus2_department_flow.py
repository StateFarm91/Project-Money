"""OPUS2: Research -> Product Development as one durable department flow, in one store
(owner directive 2026-11-02, item 6).

Real research runs (listings, the tournament, winner intake, the gate, the sentinel re-gate)
feed Product Development's real handlers through the durable job queue, in one database:

* a draft the funnel refuses does not block the winner in the same queue;
* a durable cir.draft survives a crash: the worker that enqueued it is gone, a fresh process
  on the same store drafts, compiles and sends it to certification;
* the department moves on to its next product (release recovery's next-release seeding),
  once per design, without redoing the winner.

What this does not show, and why: a research run whose winner is a tapestry basket or a toy
does not reach Product Development today, because the research gate refuses basket and pouch
winners without silhouette qualifiers (#108) and there is no toy arena. Those constructions
are shown from research-shaped briefs through the same handler in
test_opus2_research_to_development (part 2). Both are W-CONCEPT dependencies.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_department_flow.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

import test_cert_design_pipeline as T  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing, Job, JobStatus  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402


def _listings(db, pod, title, prefix):
    with db.session() as s:
        for i in range(12):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"{prefix}{i}",
                                   title=title, pod=pod, price_cad=8.0,
                                   audit_state="audited", detail={"num_favorers": 90}))


def _jobs(db, job_type):
    with db.session() as s:
        return [(j.id, j.status, dict(j.inputs or {}), dict(j.outputs or {}))
                for j in s.scalars(select(Job).where(Job.job_type == job_type)
                                   .order_by(Job.id))]


def test_research_to_development_is_durable_survives_a_restart_and_moves_on():
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import release_recovery

    db = T._db()
    url = str(db.engine.url)
    # 1. A real stockings research run: its winner waits on a judgement, is judged and
    #    re-gated by the sentinel, and a durable cir.draft job is queued.
    _listings(db, "stockings", "Festive Christmas Stocking Crochet Pattern", "S")
    result, first = T._tournament(db, generator=T.stocking_field())
    assert result["ran"] is True and first["decision"] == "waiting", first
    first_slug = first["concept"]["key"]
    T._judge(db, first_slug)
    out, _ = T._handler(db, "mjs.seasonal_sentinel", {}, agent="market_radar")
    assert {"slug": first_slug, "decision": "engineering"} in out["regated"]["presented"], out
    # A second draft in the same queue that its funnel refuses (no tournament carried it):
    # it must end refused, and must not block the winner behind or ahead of it.
    JobQueue(db).enqueue("crochet_engineer", "cir.draft",
                         {"slug": "uncarried-concept", "concept": {**first["concept"],
                                                                   "key": "uncarried-concept"}},
                         idempotency_key="draft:uncarried-concept")
    queued = _jobs(db, "cir.draft")
    assert len(queued) == 2 and all(j[1] == JobStatus.PENDING for j in queued), queued
    # 2. The process stops here: no worker ran either draft. A fresh process on the same store
    #    drains the durable queue: the uncarried concept is refused, the winner is drafted,
    #    compiled and sent to certification.
    del db
    restarted = Database(url)
    drafts = {d["inputs"].get("slug"): d for d in T._drain(restarted, "cir.draft")}
    assert drafts[first_slug]["status"] == JobStatus.DONE, drafts[first_slug]
    assert drafts[first_slug]["outputs"].get("drafted") is True, drafts[first_slug]
    assert drafts["uncarried-concept"]["outputs"].get("drafted") is False, drafts
    # refused at the first gate that sees it (the pre-engineering brief gate, then the funnel)
    assert drafts["uncarried-concept"]["outputs"].get("gate") in ("refused", "funnel"), drafts
    assert drafts["uncarried-concept"]["status"] == JobStatus.DONE
    compiled = T._drain(restarted, "cir.compile")
    assert compiled and all(c["outputs"]["compiled"] is True for c in compiled), compiled
    assert _jobs(restarted, "gate.certify"), "the compiled winner was not sent to certification"
    # 3. The department moves on to its next product: the next-product step (release
    #    recovery's Launch-0 seeding, run by every chain rebuild) drafts the next release that
    #    is not certified, once per design; asked again, it does not duplicate it.
    from brambleloop.queue.durable import DuplicateJob

    q = JobQueue(restarted)

    def enqueue(role, kind, data, **kw):          # as JobContext.enqueue: a duplicate is None
        try:
            return q.enqueue(role, kind, data, **kw)
        except DuplicateJob:
            return None

    ctx = SimpleNamespace(db=restarted, enqueue=enqueue)
    first_seed = release_recovery.seed_launch0(ctx, limit=1)
    assert len(first_seed["seeded"]) == 1, first_seed
    again = release_recovery.seed_launch0(ctx, limit=1)
    assert first_seed["seeded"][0] not in again["seeded"], (first_seed, again)
    nxt = first_seed["seeded"][0].split("@")[0]
    drafted = {d["inputs"].get("slug"): d for d in T._drain(restarted, "cir.draft")}
    assert drafted[nxt]["status"] == JobStatus.DONE, drafted[nxt]
    assert drafted[nxt]["outputs"].get("drafted") is True, drafted[nxt]
    assert drafted[first_slug]["status"] == JobStatus.DONE      # the winner is not redone

if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:800])
                import traceback
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
