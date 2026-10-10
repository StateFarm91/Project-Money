"""W4-AUTO: the provenance backstop under concurrent worker lanes.

After-proof finding (2026-10-07): `listing.seo` for market-basket-small ran 52 s on one lane
while `creative.candidates_file` and `swarm.allocate` ran on others; the time-windowed backstop
blamed both slug-less jobs for the listing's copy and dead-lettered them. An artefact is now
set aside only when another job named for that same product overlapped the window; everything
else is still enforced.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Agent, Job, JobStatus  # noqa: E402
from brambleloop.ops import artefacts as provenance  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime.worker import HandlerRegistry, Worker, concurrent_attribution  # noqa: E402

MISSING = ("listing_copy", "basket@1.2.0", "basket")


def boot() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='w4auto-prov-')}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    with db.session() as s:
        a = s.scalar(select(Agent).where(Agent.name == "orchestrator"))
        a.allowed_job_types = list(a.allowed_job_types) + ["probe.slugless", "listing.seo"]
    return db


def _run(db, *, concurrent_slug: str | None) -> Job:
    """A slug-less job whose window shows one unproven artefact of `basket`."""
    q = JobQueue(db)
    if concurrent_slug:
        q.enqueue("orchestrator", "listing.seo", {"slug": concurrent_slug})
        other = q.claim("lane-b", ["listing.seo"])  # RUNNING on another lane
        assert other is not None and other.status == JobStatus.RUNNING
    reg = HandlerRegistry()

    @reg.register("probe.slugless")
    def _h(ctx):
        return {"allocated": 1}

    real_ai, real_me = provenance.assert_instrumented, provenance.may_enforce_unproven
    provenance.assert_instrumented = lambda s, *, since, job_id=None: {
        "job_id": job_id, "since": None, "checked": 1, "missing": [MISSING],
        "incomplete": [{"artefact_class": MISSING[0], "artefact_key": MISSING[1],
                        "gaps": ["job_id"]}]}
    provenance.may_enforce_unproven = lambda s, *, ignoring=(): {"may_enforce_unproven": True}
    try:
        job = q.enqueue("orchestrator", "probe.slugless", {}, max_attempts=1)
        Worker(db, "lane-a", registry=reg).run_once()
    finally:
        provenance.assert_instrumented, provenance.may_enforce_unproven = real_ai, real_me
    return q.get(job.id)


def test_artefact_of_a_concurrent_same_product_job_is_not_this_jobs_defect():
    row = _run(boot(), concurrent_slug="basket")
    assert row.status == JobStatus.DONE, (row.status, row.last_error)


def test_unattributable_artefact_is_still_enforced():
    row = _run(boot(), concurrent_slug=None)
    assert row.status == JobStatus.DEAD and "provenance refused" in (row.last_error or ""), row
    row = _run(boot(), concurrent_slug="some-other-product")
    assert row.status == JobStatus.DEAD, (row.status, row.last_error)


def test_attribution_moves_only_matching_slugs_and_keeps_the_rest():
    db = boot()
    q = JobQueue(db)
    q.enqueue("orchestrator", "listing.seo", {"slug": "basket"})
    other = q.claim("lane-b", ["listing.seo"])
    assert other is not None
    keep = ("listing_copy", "mat@1.0.0", "mat")
    gap = {"missing": [MISSING, keep], "incomplete": [
        {"artefact_class": MISSING[0], "artefact_key": MISSING[1], "gaps": []},
        {"artefact_class": keep[0], "artefact_key": keep[1], "gaps": []}]}
    with db.session() as s:
        out = concurrent_attribution(s, gap, since=other.started_at, job_id=other.id + 1)
    assert out["missing"] == [keep], out
    assert [c["artefact"] for c in out["concurrent"]] == [list(MISSING)], out
    assert [i["artefact_key"] for i in out["incomplete"]] == [keep[1]], out
    assert other.id in out["concurrent"][0]["concurrent_jobs"], out
    # The job's own rows never excuse it.
    with db.session() as s:
        own = concurrent_attribution(s, {"missing": [MISSING]}, since=other.started_at,
                                     job_id=other.id)
    assert own["missing"] == [MISSING], own


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK", name)
        except Exception as e:  # noqa: BLE001
            fails += 1
            print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
