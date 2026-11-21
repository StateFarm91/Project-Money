"""HALT-380 H4: are chain.rebuild jobs starved before they reach their verify pass?

Production 7b250d61 read back 12 pending chain.rebuild jobs (oldest 0.13 h), 171 done in 7 d,
50 "already queued" on the last propagation, and no verified rebuild for ~15 h. H4 says the
jobs are starved, not wrong. Candidates named in the brief:

  (1) pending jobs are re-created / their run_after pushed forward before a worker claims them;
  (2) the hourly `chain_rebuild` cadence (whole-catalogue) or a re-run sentinel supersedes them;
  (3) deploy restarts kill their leases mid-run and the attempt cap ends them;
  (4) idempotency keys collide, so the verify pass never enqueues.

This drains the real worker (real queue, claim order, lane hold, handlers, sentinel,
propagation, cadence keys) over a production-shaped estate: 12 certified products whose
recorded artefacts were built under the chain fingerprint before a deploy moved it. Only the
three *stage* handlers a targeted rebuild enqueues (gate.certify / assets.build /
pricing.position) are replaced by a stub that rewrites the product's provenance rows under the
current fingerprint and binds them to the stage job -- exactly what the real stage does to
the row, without rendering twelve PDFs. Whether the stage remakes artefacts correctly is
`test_eng_stale_rebuild_loop.test_end_to_end_a_moved_chain_converges_in_one_attempt`'s job;
this suite is about whether the queue lets chain.rebuild get to verify at all.

Simulated time: `_elapse` moves every pending job's `run_after` (and every finished job's
`finished_at`) back by the step, which is the same as the clock moving forward for the claim
query and the RETRY_AFTER window. Each simulated hour also enqueues the two hourly cadences
that touch this path -- `ops.sentinel` and the whole-catalogue `chain.rebuild` -- under their
real cadence keys.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit  # noqa: E702
import hashlib
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

_TMP = tempfile.mkdtemp(prefix="halt380_h4_")
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from sqlalchemy import select, update  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (ArtefactProvenance, AuditLog, Job, JobStatus,  # noqa: E402
                                     PatternVersion, Phase, Product, utcnow)
from brambleloop.ops import artefacts as A  # noqa: E402
from brambleloop.products import builder  # noqa: E402
from brambleloop.queue.durable import DuplicateJob, JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402
from brambleloop.runtime import worker as W  # noqa: E402

from test_eng_stale_rebuild_loop import LIVE, _MovedChain, _no_policy  # noqa: E402

STAGES = ("gate.certify", "assets.build", "pricing.position")


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='h4-', dir=_TMP)}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _estate(db, slugs=LIVE):
    """12 certified releases, each with a pdf and a marketing asset recorded pre-deploy."""
    old = A.chain_fingerprint()
    with db.session() as s:
        for slug in slugs:
            p = Product(slug=slug, title=slug)
            s.add(p)
            s.flush()
            # two of the twelve are not in today's builder catalogue (production holds their
            # stored CIR); the stub stage never reads it, so a sibling's shape stands in
            built = builder.for_slug(slug) or builder.for_slug(LIVE[0])
            cir = {**built.to_dict(), "slug": slug}
            s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json=cir,
                                 certified=True,
                                 release_hash=hashlib.sha256(slug.encode()).hexdigest()))
        s.flush()
        for slug in slugs:
            for cls, key in (("pdf", f"{slug}@1.0.0#pdf-us"),
                             ("marketing_asset", f"{slug}:pinterest:{A.fingerprint(slug)[:16]}")):
                A.record(s, artefact_class=cls, artefact_key=key, product_slug=slug,
                         inputs={"chain:release": old})
    return old


class _StubStages:
    """The stage a targeted rebuild enqueues rewrites the product's rows, bound to itself."""

    def __init__(self):
        self.ran: list[tuple[str, str, int]] = []

    def _stage(self, ctx):
        i = dict(ctx.job.inputs)
        slug = i.get("slug") or (i.get("cir") or {}).get("slug") or i.get("product_slug") or ""
        with ctx.db.session() as s:
            rows = list(s.scalars(select(ArtefactProvenance).where(
                ArtefactProvenance.product_slug == slug)))
            for r in rows:
                A.record(s, artefact_class=r.artefact_class, artefact_key=r.artefact_key,
                         product_slug=slug, inputs={"chain:release": A.chain_fingerprint()})
            s.flush()
            s.execute(update(ArtefactProvenance).where(
                ArtefactProvenance.product_slug == slug).values(job_id=ctx.job.id))
        self.ran.append((ctx.job.job_type, slug, ctx.job.id))
        return {"stub_stage": True, "slug": slug}

    def __enter__(self):
        self.saved = {t: W.handlers.get(t) for t in STAGES}
        for t in STAGES:
            W.handlers._handlers[t] = self._stage
        return self

    def __exit__(self, *exc):
        for t, fn in self.saved.items():
            if fn is None:
                W.handlers._handlers.pop(t, None)
            else:
                W.handlers._handlers[t] = fn


def _elapse(db, minutes):
    d = timedelta(minutes=minutes)
    with db.session() as s:
        for j in s.scalars(select(Job)):
            if j.status in (JobStatus.PENDING, JobStatus.FAILED) and j.run_after is not None:
                j.run_after = j.run_after - d
            if j.finished_at is not None:
                j.finished_at = j.finished_at - d
            if j.created_at is not None:
                j.created_at = j.created_at - d


def _drain(db, name, limit=600):
    w = W.Worker(db, name, phase=Phase.SHADOW, lease_seconds=900,
                 job_types=["chain.rebuild", "ops.sentinel", *STAGES])
    n = 0
    for _ in range(limit):
        if not w.run_once():
            break
        n += 1
    return n


def _hourly(db, hour):
    """The two hourly cadences on this path, under their real keys (one window per hour)."""
    q = JobQueue(db)
    now = utcnow() + timedelta(hours=hour)
    for name, agent, jt in (("stale_artefact_sentinel", "orchestrator", "ops.sentinel"),
                            ("chain_rebuild", "listing", "chain.rebuild")):
        try:
            q.enqueue(agent, jt, {"cadence": name},
                      idempotency_key=W.cadence_key(name, 3600, now))
        except DuplicateJob:
            pass


def _readback(db, slugs=LIVE):
    with db.session() as s:
        jobs = [j for j in s.scalars(select(Job).where(Job.job_type == "chain.rebuild"))]
        audits = list(s.scalars(select(AuditLog).where(AuditLog.action.in_((
            "chain.rebuild_verified", "chain.rebuild_completed", "chain.rebuild_refused",
            "chain.rebuild_unbound", "swarm.lane_held")))))
    per = {}
    for slug in slugs:
        mine = [j for j in jobs if (j.inputs or {}).get("product_slug") == slug]
        per[slug] = {
            "first": [j.id for j in mine if not (j.inputs or {}).get("verify")],
            "verify_jobs": [(j.id, j.status.value, (j.inputs or {}).get("verify"))
                            for j in mine if (j.inputs or {}).get("verify")],
            "verified": [a.detail.get("check") for a in audits
                         if a.action == "chain.rebuild_verified"
                         and (a.artifact or "").startswith(f"{slug}@")],
            "completed": sorted({a.artifact for a in audits
                                 if a.action == "chain.rebuild_completed"
                                 and (a.detail or {}).get("product_slug") == slug
                                 and not (a.detail or {}).get("already_fresh")}),
            "refused": [(a.detail or {}).get("why") for a in audits
                        if a.action == "chain.rebuild_refused"
                        and (a.artifact or "").startswith(slug)],
        }
    held = sum(1 for a in audits if a.action == "swarm.lane_held"
               and a.artifact == "chain.rebuild")
    unfinished = [j for j in jobs if j.status in (JobStatus.PENDING, JobStatus.RUNNING,
                                                  JobStatus.FAILED)]
    return {"per": per, "lane_held_chain_rebuild": held,
            "unfinished": len(unfinished),
            "by_status": {st: sum(1 for j in jobs if j.status.value == st)
                          for st in {j.status.value for j in jobs}}}


def _run_estate(*, hours=3, step=10, restart_every=None):
    db = _db()
    _estate(db)
    restore = _no_policy()
    try:
        with _MovedChain(), _StubStages() as stub:
            for h in range(hours):
                _hourly(db, h)
                for m in range(0, 60, step):
                    _drain(db, f"h4-{h}-{m}")
                    if restart_every and (m // step) % restart_every == 0:
                        _kill_running_rebuild(db)
                    _elapse(db, step)
            _drain(db, "h4-final")
            return db, _readback(db), stub
    finally:
        restore()


def _kill_running_rebuild(db):
    """A deploy restart: one chain.rebuild is claimed, then its process dies holding the lease."""
    q = JobQueue(db, lease_seconds=900)
    job = q.claim("doomed-by-deploy", ["chain.rebuild"])
    if job is None:
        return None
    with db.session() as s:                     # the lease runs out while nobody holds it
        s.execute(update(Job).where(Job.id == job.id).values(
            lease_expires_at=utcnow() - timedelta(seconds=1)))
    return job.id


# --- H4 under the production shape -------------------------------------------------------------

def test_h4_twelve_stale_products_each_reach_verify_and_verify_completes():
    db, rb, stub = _run_estate()
    per = rb["per"]
    assert len(per) == 12
    no_first = [s for s, r in per.items() if not r["first"]]
    assert not no_first, f"sentinel never enqueued a rebuild for {no_first}: {rb}"
    refused = {s: r["refused"] for s, r in per.items() if r["refused"]}
    assert not refused, f"refused rather than rebuilt: {refused}"
    no_verify_job = [s for s, r in per.items() if not r["verify_jobs"]]
    assert not no_verify_job, f"(4) the verify pass was never enqueued for {no_verify_job}"
    never_verified = [s for s, r in per.items() if not r["verified"]]
    assert not never_verified, (f"(1)/(2) verify enqueued but never ran for {never_verified}: "
                                f"{ {s: per[s]['verify_jobs'] for s in never_verified} }")
    incomplete = [s for s, r in per.items() if len(r["completed"]) < 2]
    assert not incomplete, (f"verify ran but produced no completion for {incomplete}: "
                            f"{ {s: per[s] for s in incomplete} }")
    assert rb["unfinished"] == 0, rb
    print("   H4 readback:", {"by_status": rb["by_status"],
                              "lane_held_chain_rebuild": rb["lane_held_chain_rebuild"],
                              "stage_runs": len(stub.ran)})


def test_h4_hourly_cadence_and_sentinel_do_not_reset_a_pending_verify():
    """(1)/(2): a pending verify job keeps its run_after and id across the hourly cadences."""
    db = _db()
    _estate(db)
    restore = _no_policy()
    try:
        with _MovedChain(), _StubStages():
            _hourly(db, 0)
            _drain(db, "h4-a")               # sentinel -> first passes -> stages
            with db.session() as s:
                before = {j.id: j.run_after for j in s.scalars(select(Job).where(
                    Job.job_type == "chain.rebuild", Job.status == JobStatus.PENDING))}
            assert len(before) == 12, before
            _elapse(db, 5)
            _hourly(db, 1)                       # next hour's sentinel + whole-catalogue scan
            _drain(db, "h4-b")
            with db.session() as s:
                after = {j.id: j.run_after for j in s.scalars(select(Job).where(
                    Job.job_type == "chain.rebuild", Job.status == JobStatus.PENDING))}
            assert set(after) == set(before), (sorted(before), sorted(after))
            moved = {k for k in before if after[k] != before[k] - timedelta(minutes=5)}
            assert not moved, f"run_after pushed forward for {sorted(moved)}"
    finally:
        restore()


def test_h4_deploy_restarts_do_not_exhaust_verify():
    """(3): restarts that kill a rebuild's lease mid-run never end a rebuild before verify."""
    db, rb, _ = _run_estate(restart_every=2)
    per = rb["per"]
    dead = {s: [v for v in r["verify_jobs"] if v[1] == "dead"] for s, r in per.items()}
    dead = {s: v for s, v in dead.items() if v}
    never = [s for s, r in per.items() if not r["verified"]]
    assert not never, f"restarts kept {never} from verifying: {per}"
    assert not dead, f"restarts dead-lettered verify jobs: {dead}"


def test_h4_lane_share_does_not_hold_protected_rebuild_forever():
    """A pool with another function busy and waiting: chain.rebuild (truth_defect tier) must
    still be claimed and run, not handed back every minute while ordinary work waits."""
    from brambleloop.swarm import capacity

    db = _db()
    _estate(db, LIVE[:3])
    restore = _no_policy()
    saved = os.environ.get("BRAMBLELOOP_WORKER_THREADS")
    os.environ["BRAMBLELOOP_WORKER_THREADS"] = "2"
    try:
        with _MovedChain(), _StubStages():
            q = JobQueue(db, lease_seconds=900)
            # another 'listing'-function job is running on the other worker (live lease), and
            # another function has ordinary runnable work waiting below its share
            busy = q.enqueue("listing", "listing.package", {}, idempotency_key="busy-listing")
            q.claim("other-worker", ["listing.package"])
            for n in range(4):
                q.enqueue("market_radar", "radar.scan", {"n": n}, idempotency_key=f"radar-{n}")
            _hourly(db, 0)
            for step in range(8):
                _drain(db, f"h4-lane-{step}")
                _elapse(db, 10)
            rb = _readback(db, LIVE[:3])
            info = {s: rb["per"][s] for s in LIVE[:3]}
            never = [s for s, r in info.items() if not r["verified"]]
            assert busy is not None
            assert not never, (f"lane/function share held protected chain.rebuild for {never} "
                               f"({rb['lane_held_chain_rebuild']} holds): {info}; "
                               f"workers={capacity.worker_threads()}")
    finally:
        restore()
        if saved is None:
            os.environ.pop("BRAMBLELOOP_WORKER_THREADS", None)
        else:
            os.environ["BRAMBLELOOP_WORKER_THREADS"] = saved


def test_h4_the_share_still_binds_ordinary_work_and_the_lane_limit_binds_protected():
    """Protected work never yields to ordinary work, but the mix still binds ordinary work and
    protected work within its tier, and the agent-lane concurrency limit is untouched."""
    from brambleloop.swarm import capacity, orchestrate

    db = _db()
    saved = os.environ.get("BRAMBLELOOP_WORKER_THREADS")
    os.environ["BRAMBLELOOP_WORKER_THREADS"] = "2"
    try:
        q = JobQueue(db, lease_seconds=900)
        q.enqueue("listing", "listing.package", {}, idempotency_key="busy")
        q.claim("other-worker", ["listing.package"])
        q.enqueue("market_radar", "radar.scan", {}, idempotency_key="radar")
        ordinary = q.enqueue("listing", "listing.package", {"n": 2}, idempotency_key="ord")
        protected = q.enqueue("listing", "chain.rebuild", {"product_slug": "x",
                                                           "artefacts": ["pdf:x"]},
                              idempotency_key="prot")
        with db.session() as s:
            o, p = s.get(Job, ordinary.id), s.get(Job, protected.id)
            s.expunge(o)
            s.expunge(p)
        assert capacity.share_decision(db, o)["hold"] is True      # mix still enforced
        d = capacity.share_decision(db, p)
        assert d["hold"] is False, d          # protected never yields to ordinary work
        # ...but still shares with protected work of its own tier (the mix binds there)
        q.enqueue("orchestrator", "ops.queue_check", {}, idempotency_key="prot-waiting")
        d2 = capacity.share_decision(db, p)
        assert d2["hold"] is True and d2["kind"] == "function_share", d2
        # the hard per-agent lane limit is not part of the share and is unchanged
        import inspect

        src = inspect.getsource(orchestrate.lane_hold)
        assert src.index("claim_decision(") < src.index("share_decision("), \
            "the agent-lane limit must still be decided before (and independent of) the share"
    finally:
        if saved is None:
            os.environ.pop("BRAMBLELOOP_WORKER_THREADS", None)
        else:
            os.environ["BRAMBLELOOP_WORKER_THREADS"] = saved


if __name__ == "__main__":
    fails = 0
    for name in [n for n in list(globals()) if n.startswith("test_")]:
        try:
            globals()[name]()
            print(f"OK   {name}")
        except Exception as e:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            fails += 1
            print(f"FAIL {name}", repr(e)[:2000])
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
