"""ENG-SUPPLY: capacity-aware product admission (products.supply).

Every new product enters engineering through one admission controller. These tests run the
real controller, the real durable queue and the registered `supply.admit` handler on SQLite
files; nothing under test is mocked except the two readings a test is about (the worker
target, an unreadable spend reading). Every slug and title here is a TEST FIXTURE.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="eng_supply_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
# ENG-SUPPLY-LANE: this suite pins the historical one-worker admission (WIP 2, one admission
# per run) through the existing env override and the per-run constant; the capacity-based
# defaults are proven in tests/test_supply_lane.py.
os.environ["BRAMBLELOOP_SUPPLY_MAX_WIP"] = "2"

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, CostEntry, Job, JobStatus, OwnerAction, Phase, PhysicalTest,
)
from brambleloop.products import supply  # noqa: E402
supply.MAX_ADMIT_PER_RUN = 1  # ENG-SUPPLY-LANE: the historical trickle, pinned
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import CADENCES, JobContext, Worker  # noqa: E402

_N = [0]


def _path():
    _N[0] += 1
    return f"sqlite:///{_TMP}/sup{_N[0]}.db"


def _db(path=None):
    db = Database(path or _path())
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _ctx(db, key="holder"):
    job = JobQueue(db).enqueue("orchestrator", "supply.admit", {}, idempotency_key=key)
    return JobContext(job=job, db=db, queue=JobQueue(db), registry=Registry(db),
                      phase=Phase.SHADOW)


def _chain(db, slug, status=JobStatus.PENDING, job_type="gate.certify", key=None,
           run_after=None, agent="quality_director"):
    j = JobQueue(db).enqueue(agent, job_type, {"slug": slug},
                             idempotency_key=key or f"chain:{slug}:{job_type}",
                             **({"run_after": run_after} if run_after else {}))
    with db.session() as s:
        s.get(Job, j.id).status = status
    return j.id


def _offer(ctx, slug, *, family=None, demand=0.6, research=True):
    return supply.offer(ctx, slug=slug, key=f"draft:{slug}", source="radar.score",
                        payload={"slug": slug, "title": slug.replace("-", " ").title()},
                        family=family or slug, demand=demand, research=research)


def _drafts(db):
    with db.session() as s:
        return [j.inputs["slug"] for j in s.scalars(
            select(Job).where(Job.job_type == "cir.draft").order_by(Job.id))]


def _admissions(db):
    with db.session() as s:
        return [r.detail for r in s.scalars(select(AuditLog).where(
            AuditLog.action == supply.ADMISSION).order_by(AuditLog.id))]


def _finish(db, slug):
    with db.session() as s:
        for j in s.scalars(select(Job)):
            if (j.inputs or {}).get("slug") == slug:
                j.status = JobStatus.DONE


# ---- capacity ------------------------------------------------------------------------------

def test_admission_fills_free_capacity_and_refuses_past_it_with_the_reason():
    db = _db()
    ctx = _ctx(db)
    a = _offer(ctx, "linen-ridge-washcloth")
    b = _offer(ctx, "harbour-fog-cowl")
    c = _offer(ctx, "meadow-step-rug")
    assert a["admitted"] and b["admitted"], (a, b)
    assert c["offered"] and not c["admitted"] and c["job"] is None, c
    assert c["why"].startswith("capacity: 2 product chain(s) in flight"), c
    assert _drafts(db) == ["linen-ridge-washcloth", "harbour-fog-cowl"]
    last = _admissions(db)[-1]
    assert last["refused"]["draft:meadow-step-rug"] == c["why"], last
    assert last["capacity"]["in_flight"] == ["harbour-fog-cowl", "linen-ridge-washcloth"]
    # the refused offer waits in the supply queue, durably
    assert [o["slug"] for o in supply.offers(db)] == ["meadow-step-rug"]
    # one finishes: the next run admits the waiting offer, with no manual kick
    _finish(db, "linen-ridge-washcloth")
    out = supply.admit(ctx)
    assert [x["slug"] for x in out["admitted"]] == ["meadow-step-rug"], out
    assert supply.offers(db) == []


def test_a_larger_per_run_allowance_never_admits_past_the_free_slots():
    """The trickle is the lesser of the per-run allowance and the free slots: a caller asking
    for more per run still gets no more than the work-in-progress limit leaves free."""
    db = _db()
    ctx = _ctx(db)
    _chain(db, "kiln-dust-throw", key="k1")
    _chain(db, "salt-marsh-wrap", key="k2")
    for slug in ("birch-bark-pouch", "wren-song-mitts", "quarry-stone-mat"):
        assert not _offer(ctx, slug)["admitted"]
    _finish(db, "kiln-dust-throw")
    out = supply.admit(ctx, per_run=5)
    assert [x["slug"] for x in out["admitted"]] == ["birch-bark-pouch"], out
    assert out["capacity"]["slots"] == 1, out
    assert len(out["refused"]) == 2 and all(
        v.startswith("per-run trickle") for v in out["refused"].values()), out
    assert _drafts(db) == ["birch-bark-pouch"]


def test_the_wip_ceiling_follows_the_worker_target_and_stays_bounded():
    from brambleloop.swarm import capacity

    db = _db()
    real = capacity.worker_target
    try:
        # ENG-SUPPLY-LANE: capacity-based. Nothing is measured on this db, so each worker
        # carries the WIP_PER_WORKER floor (4); MAX_WIP 12 binds; the env override still
        # lowers it or raises it to HARD_MAX_WIP, never past.
        for target, env, want in ((1, {}, 4), (2, {}, 8), (3, {}, 12), (40, {}, 12),
                                  (40, {"BRAMBLELOOP_SUPPLY_MAX_WIP": "6"}, 6),
                                  (40, {"BRAMBLELOOP_SUPPLY_MAX_WIP": "999"}, supply.HARD_MAX_WIP),
                                  (1, {"BRAMBLELOOP_SUPPLY_MAX_WIP": "1"}, 1),
                                  (1, {"BRAMBLELOOP_SUPPLY_MAX_WIP": "junk"}, 4)):
            capacity.worker_target = lambda db, now=None, t=target: {"target": t}
            got = supply.wip_ceiling(db, env=env)["limit"]
            assert got == want, (target, env, got)

        def boom(db, now=None):
            raise RuntimeError("unreadable")
        capacity.worker_target = boom
        w = supply.wip_ceiling(db, env={})
        assert w["limit"] == supply.WIP_PER_WORKER and "unreadable" in w["source"], w
    finally:
        capacity.worker_target = real


def test_a_stage_backlog_refuses_new_products_and_names_the_stage():
    db = _db()
    ctx = _ctx(db)
    now = datetime.now(timezone.utc)
    # an old due job: the stage is not keeping up
    _chain(db, "slow-stage-item", key="old", run_after=now - timedelta(hours=7))
    out = _offer(ctx, "willow-bark-pouch")
    assert not out["admitted"] and "stage backlog: gate.certify" in out["why"], out
    db2 = _db()
    ctx2 = _ctx(db2)
    # expected work: many due jobs of one in-flight product, each a measured hour long
    for i in range(3):
        jid = _chain(db2, "measured-item", status=JobStatus.DONE, key=f"done{i}")
        with db2.session() as s:
            j = s.get(Job, jid)
            j.started_at, j.finished_at = now - timedelta(hours=2), now - timedelta(hours=1)
    for i in range(3):
        _chain(db2, "busy-item", key=f"due{i}")
    cap = supply.assess(db2, now=datetime.now(timezone.utc))
    assert cap["backlog"]["stages"]["gate.certify"]["basis"].startswith("MEASURED"), cap
    assert any(r.startswith("stage backlog:") for r in cap["refusals"]), cap
    assert cap["slots"] == 0
    assert not _offer(ctx2, "willow-bark-pouch")["admitted"]


# ---- cost ----------------------------------------------------------------------------------

def _spend(db, cad, slug="spent-item"):
    with db.session() as s:
        s.add(CostEntry(agent="crochet_engineer", kind="llm", amount_cad=cad,
                        product_slug=slug, purpose="fixture"))


def test_admission_respects_the_existing_spend_ceilings():
    from brambleloop.finance import spend_policy

    # at the escalation share: the remaining month is kept for in-flight work
    db = _db()
    _spend(db, spend_policy.CEILING_CAD * 0.85)
    out = _offer(_ctx(db), "cedar-loop-basket")
    assert not out["admitted"] and "escalation share" in out["why"], out
    assert _drafts(db) == []
    # below the share but the expected cost of one more product does not fit
    db = _db()
    _spend(db, spend_policy.CEILING_CAD * 0.6)            # one product measured at 60%
    out = _offer(_ctx(db), "cedar-loop-basket")
    assert not out["admitted"] and "expected for 0 in-flight product(s) plus one" in out["why"]
    # measured cheap products: admitted, and the basis is recorded as measured
    db = _db()
    _spend(db, 1.0)
    ctx = _ctx(db)
    assert _offer(ctx, "cedar-loop-basket")["admitted"]
    assert supply.assess(db)["cost"]["expected"]["basis"].startswith("MEASURED")


def test_an_unreadable_spend_reading_refuses_unknown_is_never_pass():
    from brambleloop.finance import spend_policy

    db = _db()
    real = spend_policy.binding_ceiling
    try:
        def boom(db, now=None):
            raise RuntimeError("ledger offline")
        spend_policy.binding_ceiling = boom
        out = _offer(_ctx(db), "salt-marsh-tote")
    finally:
        spend_policy.binding_ceiling = real
    assert not out["admitted"] and "UNKNOWN is never PASS" in out["why"], out
    assert _drafts(db) == []


# ---- parked and blocked products ---------------------------------------------------------

def test_a_product_parked_on_a_sample_or_the_owner_frees_its_slot():
    db = _db()
    ctx = _ctx(db)
    # In flight (due inside the horizon) but not due now: waiting holds no worker time.
    soon = datetime.now(timezone.utc) + timedelta(hours=1)
    _chain(db, "sample-wait-item", key="a", run_after=soon)
    _chain(db, "owner-wait-item", key="b", run_after=soon)
    assert not _offer(ctx, "fern-path-coaster")["admitted"]          # both slots taken
    with db.session() as s:
        s.add(PhysicalTest(product_slug="sample-wait-item", version="1.0.0",
                           tester_ref="fixture tester"))
    cap = supply.assess(db)
    assert "sample-wait-item" in cap["waiting"] and cap["slots"] == 1, cap
    out = supply.admit(ctx)
    assert [x["slug"] for x in out["admitted"]] == ["fern-path-coaster"], out
    # the owner-waiting product frees its slot the same way
    with db.session() as s:
        s.add(OwnerAction(action="approve the owner-wait-item listing", reason="fixture",
                          requirement_key="fixture:owner-wait-item"))
    cap = supply.assess(db)
    assert cap["waiting"]["owner-wait-item"].startswith("owner action #"), cap
    assert cap["in_flight"] == ["fern-path-coaster"] and cap["slots"] == 1, cap
    # but a waiting product whose job is RUNNING is using the worker: it holds its slot
    _chain(db, "owner-wait-item", status=JobStatus.RUNNING, job_type="assets.build",
           key="c")
    cap = supply.assess(db)
    assert "owner-wait-item" in cap["in_flight"] and cap["slots"] == 0, cap


def test_an_owner_action_naming_a_longer_slug_never_parks_a_different_product():
    """Supply review M2: substring matching parked "granny-square" because an owner action
    named "granny-square-blanket", freeing a slot while its chain work was due."""
    db = _db()
    soon = datetime.now(timezone.utc) + timedelta(hours=1)
    _chain(db, "granny-square", key="a", run_after=soon)
    _chain(db, "tote", key="b", job_type="cir.compile", run_after=soon)
    with db.session() as s:
        s.add(OwnerAction(action="approve the granny-square-blanket listing", reason="fixture",
                          requirement_key="fixture:granny-square-blanket"))
        s.add(OwnerAction(action="review market-tote-bag photos", reason="fixture",
                          requirement_key="fixture:market-tote-bag"))
    cap = supply.assess(db)
    assert cap["waiting"] == {}, cap
    assert sorted(cap["in_flight"]) == ["granny-square", "tote"] and cap["slots"] == 0, cap
    # the exact slug, delimited by punctuation, still parks it
    with db.session() as s:
        s.add(OwnerAction(action="decide: granny-square, needs the owner", reason="fixture",
                          requirement_key="fixture:granny-square"))
    cap = supply.assess(db)
    assert "granny-square" in cap["waiting"] and cap["slots"] == 1, cap


def test_a_waiting_product_with_chain_work_due_now_keeps_its_slot():
    """Supply review M2: a product whose chain job is due now uses the worker and the model
    budget now, so an owner action or a sample naming it does not free its slot."""
    db = _db()
    _chain(db, "due-now-item", key="a")                               # due now
    with db.session() as s:
        s.add(OwnerAction(action="approve the due-now-item listing", reason="fixture",
                          requirement_key="fixture:due-now-item"))
        s.add(PhysicalTest(product_slug="due-now-item", version="1.0.0",
                           tester_ref="fixture tester"))
    cap = supply.assess(db)
    assert "due-now-item" in cap["in_flight"] and "due-now-item" not in cap["waiting"], cap
    # a FAILED retry that is due now holds its slot the same way
    db2 = _db()
    _chain(db2, "retry-item", status=JobStatus.FAILED, key="r")
    with db2.session() as s:
        s.add(OwnerAction(action="approve retry-item", reason="fixture",
                          requirement_key="fixture:retry-item"))
    cap = supply.assess(db2)
    assert "retry-item" in cap["in_flight"] and "retry-item" not in cap["waiting"], cap


def test_a_blocked_product_does_not_halt_the_others():
    db = _db()
    ctx = _ctx(db)
    _chain(db, "nordic-thing", key="a")                     # family nordic in flight
    _chain(db, "dead-end-item", status=JobStatus.DEAD, key="b")  # dead-lettered: holds nothing
    with db.session() as s:
        s.add(AuditLog(actor="test", action=supply.OFFERED, artifact="nordic-thing",
                       detail={"slug": "nordic-thing", "key": "draft:nordic-thing",
                               "family": "nordic", "payload": {"slug": "nordic-thing"}}))
        s.add(AuditLog(actor="test", action=supply.ADMITTED, artifact="nordic-thing",
                       detail={"key": "draft:nordic-thing"}))
    # family diversity is work-conserving: a second nordic product waits while another family
    # wants the slot, even with higher demand ...
    with db.session() as s:
        for slug, fam, demand in (("nordic-twin", "nordic", 0.9), ("tidepool-mat", "tide", 0.2)):
            s.add(AuditLog(actor="test", action=supply.OFFERED, artifact=slug, detail={
                "slug": slug, "key": f"draft:{slug}", "family": fam, "demand": demand,
                "research": True, "payload": {"slug": slug}}))
    out = supply.admit(ctx)
    assert [x["slug"] for x in out["admitted"]] == ["tidepool-mat"], out
    assert out["refused"]["draft:nordic-twin"].startswith("family diversity"), out
    assert "another family goes first" in out["refused"]["draft:nordic-twin"]
    # ... and is admitted when nothing else wants the slot: diversity never idles capacity
    _finish(db, "tidepool-mat")
    out = supply.admit(ctx)
    assert [x["slug"] for x in out["admitted"]] == ["nordic-twin"], out
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == supply.ADMITTED,
                                              AuditLog.artifact == "nordic-twin"))
        assert row.detail["family_in_flight"] == 1, row.detail


def test_blocked_candidates_ranked_first_do_not_stop_one_admission_run():
    """M12: within one run, a refused candidate ahead in the queue (its product already in
    flight, or its family already in flight) is passed over and the next eligible one is
    admitted -- a blocked product never halts the others."""
    db = _db()
    ctx = _ctx(db)
    _chain(db, "fjord-blanket", key="a")                       # in flight, family fjord
    _chain(db, "filler-item", key="b")                         # fills the second slot
    _offer(ctx, "fjord-blanket", family="fjord", demand=0.99)     # its product is in flight
    _offer(ctx, "fjord-runner", family="fjord", demand=0.98)      # its family is in flight
    _offer(ctx, "quiet-ember-pouch", family="ember", demand=0.57)
    _finish(db, "filler-item")
    out = supply.admit(ctx, per_run=1)
    assert [x["slug"] for x in out["admitted"]] == ["quiet-ember-pouch"], out
    assert out["refused"]["draft:fjord-blanket"].startswith("product fjord-blanket already"), out
    assert out["refused"]["draft:fjord-runner"].startswith("family diversity"), out


def test_research_originals_go_before_pool_promotions_then_by_demand():
    db = _db()
    ctx = _ctx(db)
    _chain(db, "fill-one", key="a")
    _chain(db, "fill-two", key="b")
    _offer(ctx, "pool-high", demand=0.95, research=False)
    _offer(ctx, "research-low", demand=0.56)
    _offer(ctx, "research-unknown", demand=None)
    _offer(ctx, "research-high", demand=0.8)
    assert [o["slug"] for o in supply.offers(db)] == [
        "research-high", "research-low", "research-unknown", "pool-high"]
    _finish(db, "fill-one")
    _finish(db, "fill-two")
    assert [x["slug"] for x in supply.admit(ctx, per_run=2)["admitted"]] == [
        "research-high", "research-low"]


def test_launch0_keeps_priority_but_yields_a_slot_to_waiting_research():
    db = _db()
    ctx = _ctx(db)
    _chain(db, "busy-one", key="a")
    _chain(db, "busy-two", key="b")
    _offer(ctx, "loch-mist-throw")                              # waits: no slot
    # a re-offer of the same key adds no row; it only retries admission
    again = _offer(ctx, "loch-mist-throw", demand=0.99, research=False)
    assert again["already_waiting"] and not again["admitted"], again
    with db.session() as s:
        assert len(list(s.scalars(select(AuditLog).where(
            AuditLog.action == supply.OFFERED)))) == 1
    assert supply.offers(db)[0]["research"] is True
    _finish(db, "busy-one")
    _finish(db, "busy-two")
    first = supply.run(ctx)                                     # Launch-0 first
    assert len(first["launch0"]["seeded"]) == 1 and first["offers"]["admitted"] == [], first
    second = supply.run(ctx)                                    # then research, not Launch-0
    assert "next slot goes to research supply" in second["launch0"]["yielded"], second
    assert [x["slug"] for x in second["offers"]["admitted"]] == ["loch-mist-throw"], second
    assert any("launch0_yielded" in d for d in _admissions(db))
    assert supply.launch0_share(1) == 1 and supply.launch0_share(4) == 3


def test_a_chain_that_ends_refills_its_slot_at_once_through_the_worker():
    """Requirement 3: when a product's last live chain job ends, the worker enqueues one
    admission pass keyed on that job -- the next eligible offer is admitted without waiting
    for the 15-minute cadence and without a manual kick."""
    db = _db()
    ctx = _ctx(db)
    with db.session() as s:                    # the holder admit job is not a due pass here
        s.get(Job, ctx.job.id).status = JobStatus.DONE
    _chain(db, "busy-one", key="a")
    two = _chain(db, "busy-two", key="b")
    _chain(db, "busy-two", job_type="assets.build", key="b2")
    _offer(ctx, "ash-grove-cushion")
    assert _drafts(db) == []
    with db.session() as s:
        s.get(Job, two).status = JobStatus.DONE
    with db.session() as s:
        ended = s.get(Job, two)
        s.expunge(ended)
    # busy-two still has assets.build live: its chain continues, no refill
    assert supply.after_chain_job(db, JobQueue(db), ended) is None
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.idempotency_key == "b2")):
            j.status = JobStatus.DONE
    rid = supply.after_chain_job(db, JobQueue(db), ended)
    assert rid is not None
    assert supply.after_chain_job(db, JobQueue(db), ended) is None   # one pass per end
    with db.session() as s:
        assert s.get(Job, rid).idempotency_key == f"{supply.REFILL_PREFIX}:{two}"
    # a non-chain job never triggers one; a still-live (retrying) chain job does not either
    other = JobQueue(db).enqueue("orchestrator", "ops.heartbeat", {}, idempotency_key="hb")
    assert supply.after_chain_job(db, JobQueue(db), other) is None
    # the real worker: it runs the pass and the waiting offer is admitted
    w = Worker(db, "refill-worker", job_types=["supply.admit"])
    while w.run_once():
        pass
    # the freed slot is filled at once: Launch-0 (the owner's launch scope) has first claim
    # while none of its releases is in flight; the research offer is next in line
    assert _drafts(db) == ["market-basket-small"], _drafts(db)
    with db.session() as s:
        assert s.get(Job, rid).status == JobStatus.DONE
        assert s.get(Job, rid).outputs["admitted"] == 1
    # a chain job that failed and will retry is still live: its product's slot is not freed,
    # so it enqueues no refill (checked with no admission pass due, so nothing else masks it)
    retrying = _chain(db, "kettle-pond-shawl", status=JobStatus.FAILED, key="retry")
    with db.session() as s:
        assert s.scalar(select(Job.id).where(Job.job_type == "supply.admit",
                                             Job.status == JobStatus.PENDING)) is None
        live = s.get(Job, retrying)
        s.expunge(live)
    assert supply.after_chain_job(db, JobQueue(db), live) is None
    with db.session() as s:
        s.get(Job, retrying).status = JobStatus.DEAD
    assert supply.after_chain_job(db, JobQueue(db), live) is not None   # dead-lettered: ends
    # end to end: a worker finishing a chain job enqueues the pass by itself
    db2 = _db()
    ctx2 = _ctx(db2)
    with db2.session() as s:
        s.get(Job, ctx2.job.id).status = JobStatus.DONE
    _chain(db2, "full-one", key="a")
    with db2.session() as s:
        s.add(AuditLog(actor="test", action=supply.OFFERED, artifact="ash-grove-cushion",
                       detail={"slug": "ash-grove-cushion", "key": "draft:ash-grove-cushion",
                               "research": True, "payload": {"slug": "ash-grove-cushion"}}))
    seo = _chain(db2, "full-two", status=JobStatus.PENDING, job_type="listing.seo", key="seo",
                 agent="listing")
    with db2.session() as s:        # one attempt: whether it completes or dead-letters, it ends
        s.get(Job, seo).max_attempts = 1
    assert not supply.admit(_ctx(db2, "probe"))["admitted"]
    with db2.session() as s:
        s.get(Job, s.scalar(select(Job.id).where(Job.idempotency_key == "probe"))).status = \
            JobStatus.DONE
    Worker(db2, "chain-worker", job_types=["listing.seo"]).run_once()
    with db2.session() as s:
        refill = s.scalar(select(Job).where(Job.idempotency_key.like(
            f"{supply.REFILL_PREFIX}:%")))
    with db2.session() as s:
        assert s.get(Job, seo).status in (JobStatus.DONE, JobStatus.DEAD)
    assert refill is not None and refill.job_type == "supply.admit", refill
    assert refill.idempotency_key == f"{supply.REFILL_PREFIX}:{seo}"


# ---- the non-catalogue research concept, through the real job, across a restart ----------

def test_a_non_catalogue_research_concept_is_admitted_and_enqueued_after_a_restart():
    from brambleloop.products.builder import CATALOGUE
    from brambleloop.radar.opportunity import POOL

    path = _path()
    db = _db(path)
    slug = "kelp-weave-washcloth"
    assert slug not in CATALOGUE and slug not in {p.slug for p in POOL}
    ctx = _ctx(db)
    _chain(db, "busy-one", key="a")
    _chain(db, "busy-two", key="b")
    payload = {"slug": slug, "title": "Kelp Weave Washcloth", "category": "dishcloth",
               "provenance": "radar.intake:research_task:fixture"}
    out = supply.offer(ctx, slug=slug, payload=payload, key=f"draft:{slug}",
                       source="radar.score", family="kitchen_bath", demand=0.61,
                       research=True)
    assert out["offered"] and not out["admitted"], out
    # a re-offer under the same key is not recorded twice
    assert supply.offer(ctx, slug=slug, payload=payload, key=f"draft:{slug}",
                        source="radar.score")["offered"] is True     # still waiting
    assert len(supply.offers(db)) == 1
    _finish(db, "busy-one")
    _finish(db, "busy-two")
    del db, ctx                                             # the worker process restarts
    db = Database(path)
    w = Worker(db, "restarted", job_types=["supply.admit"])
    JobQueue(db).enqueue("orchestrator", "supply.admit", {}, idempotency_key="after-restart")
    while w.run_once():
        pass
    with db.session() as s:
        drafts = list(s.scalars(select(Job).where(Job.job_type == "cir.draft")))
        run = s.scalar(select(Job).where(Job.idempotency_key == "after-restart"))
        assert run.status == JobStatus.DONE, (run.status, run.last_error)
        assert not pipeline.did_no_work(run.outputs, "supply.admit"), run.outputs
    # two admission runs (the holder and this one): Launch-0, the owner's launch scope, takes
    # the first freed slot; the research concept the second (one admission per run)
    assert [j.idempotency_key.split(":")[0] for j in drafts] == ["launch0-seed", "draft"], \
        [j.idempotency_key for j in drafts]
    d = drafts[1]
    assert d.idempotency_key == f"draft:{slug}" and d.agent == "crochet_engineer"
    assert d.inputs == payload and d.status == JobStatus.PENDING
    # exactly once: another run, and a pruned job, never admit it again
    JobQueue(db).enqueue("orchestrator", "supply.admit", {}, idempotency_key="again")
    assert w.run_once()
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.idempotency_key == f"draft:{slug}")):
            s.delete(j)
    assert supply.offers(db) == []
    assert supply.admit(_ctx(db, "third"))["admitted"] == []
    assert slug not in _drafts(db)


def test_chain_rebuild_runs_the_admission_pass():
    db = _db()
    ctx = _ctx(db)
    _chain(db, "busy-one", key="a")
    _chain(db, "busy-two", key="b")
    _offer(ctx, "drift-glass-bowl")
    _finish(db, "busy-one")
    _finish(db, "busy-two")
    j = JobQueue(db).enqueue("listing", "chain.rebuild", {}, idempotency_key="rb")
    out = release.handle_chain_rebuild(JobContext(job=j, db=db, queue=JobQueue(db),
                                                  registry=Registry(db),
                                                  phase=Phase.SHADOW))
    rec = out["recovery"]
    assert rec["launch0_seed"]["seeded"], rec      # Launch-0 first (owner launch scope) ...
    assert rec["supply"]["offers"]["refused"]["draft:drift-glass-bowl"].startswith(
        "per-run trickle"), rec                     # ... then the trickle holds the offer
    assert rec["supply"]["waiting_offers"] == 1


# ---- registration --------------------------------------------------------------------------

def test_supply_admit_is_a_registered_cadenced_job():
    from brambleloop.authority.classes import JOB_CLASS
    from brambleloop.autonomy import charters
    from brambleloop.ops import retention
    from brambleloop.runtime.worker import handlers
    from brambleloop.swarm.orchestrate import JOB_BANDS

    assert ("supply_admit", "orchestrator", "supply.admit", 15 * 60) in CADENCES
    Registry(_db()).authorize("orchestrator", "supply.admit")
    assert pipeline.WORK_KEYS["supply.admit"] == ("admitted",)
    assert JOB_BANDS["supply.admit"] == "proven_winner"
    assert "supply.admit" in JOB_CLASS
    assert "supply.admit" in next(c for c in charters.CHARTERS if c.key == "executive").job_types
    assert handlers.get("supply.admit") is not None
    # an unchanged admission run while capacity is full is not a poll to back off
    from brambleloop.swarm.orchestrate import LIVENESS_JOB_TYPES
    assert "supply.admit" in LIVENESS_JOB_TYPES
    for action in (supply.OFFERED, supply.ADMITTED):
        assert retention.KNOWN_READ_ACTIONS[action][0] == "lifetime_total", action


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as exc:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(exc))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
