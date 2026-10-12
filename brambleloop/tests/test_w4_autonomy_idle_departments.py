"""W4-AUTONOMY (2026-10-11): "eligible work exists but the department idles" (owner Rule #1).

Production 0417f35, read from the public GETs at 14:39Z:

* the only open jobs were model jobs parked because the Anthropic balance is spent
  (`ai.parked`, run_after +30 min, re-parked for up to 24 h): creative.tournament x4,
  creative.grid_tournament, intel.gallery_analysis, seasonal.cycle_proof. The orchestrator's
  Snapshot counted them as open, so Product & Design, Intelligence and Visual read BUSY and
  were given none of the deterministic work their own generators held. The same count kept
  `idle_wake` and Laura's "company queue is empty" path from ever firing in the outage.
* `ops.sentinel` dead-lettered 7 times in 8 minutes on
  `StringDataRightTruncation: value too long for type character varying(200)`: the rebuild
  key carries every moved fingerprint, Postgres enforces VARCHAR(200), SQLite does not. The
  sentinel found 14 products to rebuild and none of that work ever reached the queue.
* the control lane's own `autonomy.orchestrate` was held by the pool's function mix, and
  share holds favoured "starved" model jobs that would only be parked again.

Each test below reproduces one of those against a database seeded the way production was.
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

os.environ.setdefault("BRAMBLELOOP_WORKER_THREADS", "3")

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy import generators, orchestrator, rule1  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, Job, JobStatus, OwnerAction,  # noqa: E402
                                     utcnow)
from brambleloop.ops import artefacts as A, funding, rebuild_graph as G  # noqa: E402
from brambleloop.queue.durable import (IDEMPOTENCY_KEY_MAX, DuplicateJob,  # noqa: E402
                                       JobQueue, fit_idempotency_key)
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.scale import allocation as mixmod  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402

PARKED = ("creative.tournament", "creative.tournament", "creative.grid_tournament",
          "intel.gallery_analysis", "seasonal.cycle_proof")
AGENT = {"creative.tournament": "creative_director",
         "creative.grid_tournament": "creative_director",
         "intel.gallery_analysis": "market_radar", "seasonal.cycle_proof": "publishing"}


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='w4auto-')}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _spent_balance(db) -> None:
    """The open owner action production carries: the Anthropic balance is spent."""
    with db.session() as s:
        s.add(OwnerAction(requirement_key=funding.REQUIREMENT_KEY,
                          action="Add credit to the Anthropic account.",
                          reason="Anthropic refused a call: credit balance too low"))


def _park_like_production(db, now) -> list[int]:
    """Model jobs exactly as `park_if_model_down` leaves them: pending, run_after +30 min."""
    ids = []
    with db.session() as s:
        for i, jt in enumerate(PARKED):
            j = Job(agent=AGENT[jt], job_type=jt, inputs={"n": i}, priority=40,
                    status=JobStatus.PENDING, run_after=now + timedelta(minutes=30),
                    idempotency_key=f"parked-{i}")
            s.add(j)
            s.flush()
            ids.append(j.id)
    return ids


# ---- 1. parked work does not make a department BUSY ------------------------------------

def test_departments_holding_only_parked_model_jobs_are_given_their_eligible_work():
    db = _db()
    now = datetime.now(timezone.utc)
    _spent_balance(db)
    _park_like_production(db, now)

    snap = generators.Snapshot.read(db, now)
    for dept in ("product_design", "intelligence", "visual"):
        assert snap.open_by_department.get(dept, 0) == 0, (dept, snap.open_by_department)
        assert snap.waiting_by_department.get(dept, 0) >= 1, snap.waiting_by_department
    # Every waiting type is still known open, so it is never generated a second time.
    assert snap.open_by_type["creative.tournament"] == 2

    # Rule #1 measurement now sees the defect the BUSY reading hid ...
    before = rule1.measure(db, now=now)["departments"]
    for dept in ("product_design", "intelligence", "visual"):
        assert before[dept]["idle_at_end"] is True, (dept, before[dept])
        assert before[dept]["rule1_defect"] is True, (dept, before[dept])

    report = orchestrator.tick(db, now=now)
    for dept in ("product_design", "intelligence", "visual"):
        entry = report["departments"][dept]
        assert entry["state"] == "GENERATED", (dept, entry)
        assert entry["waiting_jobs"] >= 1, entry
    generated = {m["department"]: m["job_type"] for m in report["missions"]}
    # Deterministic, charter-generatable work; never another parked model job.
    for dept in ("product_design", "intelligence", "visual"):
        assert generated[dept] not in PARKED, generated
    with db.session() as s:
        n_tournaments = len(list(s.scalars(select(Job.id).where(
            Job.job_type == "creative.tournament"))))
    assert n_tournaments == 2, "a waiting job type is never enqueued again"

    # ... and once each department holds actionable work, the defect is gone.
    after = rule1.measure(db, now=datetime.now(timezone.utc))["departments"]
    for dept in ("product_design", "intelligence", "visual"):
        assert after[dept]["rule1_defect"] is False, (dept, after[dept])


def test_a_department_with_due_work_is_still_busy():
    db = _db()
    now = datetime.now(timezone.utc)
    JobQueue(db).enqueue("creative_director", "creative.tournament", {"n": 1},
                         idempotency_key="due")
    report = orchestrator.tick(db, now=now + timedelta(seconds=1))
    assert report["departments"]["product_design"]["state"] == "BUSY"


def test_a_waiting_handoff_consumer_is_not_duplicated():
    """With waiting jobs no longer making a department BUSY, a handoff whose consumer job is
    already open (only waiting) must not enqueue a second consumer."""
    from brambleloop.core.models import SupportCase

    db = _db()
    now = datetime.now(timezone.utc)
    with db.session() as s:
        s.add(SupportCase(customer_ref="c-1", question="Is row 12 right?"))
        s.add(Job(agent="support", job_type="support.triage", inputs={}, priority=10,
                  status=JobStatus.FAILED, run_after=now + timedelta(minutes=5),
                  idempotency_key="triage-backoff", attempts=1))
    report = orchestrator.tick(db, now=now)
    entry = report["departments"]["support"]
    assert entry["waiting_jobs"] == 1, entry
    with db.session() as s:
        triage = list(s.scalars(select(Job.id).where(Job.job_type == "support.triage")))
    assert len(triage) == 1, "the waiting consumer will read the case; no duplicate"


def test_idle_wake_fires_when_only_parked_work_is_queued():
    db = _db()
    now = datetime.now(timezone.utc)
    _park_like_production(db, now)
    assert orchestrator.idle_wake(db, JobQueue(db), now=now) is True


def test_laura_counts_parked_jobs_as_waiting_not_as_company_work():
    from brambleloop.laura.executive import loop

    db = _db()
    now = datetime.now(timezone.utc)
    _park_like_production(db, now)
    state = loop.observe(db, now=now)
    assert state["queue"]["company_work_open"] == 0, state["queue"]
    assert state["queue"]["company_work_waiting"] == len(PARKED), state["queue"]
    # Still visible as open types, so Laura never delegates a second copy of one.
    assert state["queue"]["open_by_type"]["creative.tournament"] == 2


# ---- 2. the sentinel's rebuild key fits the Postgres column ----------------------------

def test_a_long_idempotency_key_is_fitted_deterministically():
    long_a = "rebuild:product:hex:" + "-".join(f"cir:p{i}=abcdef12" for i in range(40))
    long_b = long_a[:-1] + "3"
    fa, fb = fit_idempotency_key(long_a), fit_idempotency_key(long_b)
    assert len(fa) <= IDEMPOTENCY_KEY_MAX and len(fb) <= IDEMPOTENCY_KEY_MAX
    assert fa == fit_idempotency_key(long_a), "same key, same stored key"
    assert fa != fb, "a shared prefix never merges two different keys"
    assert fit_idempotency_key("short") == "short" and fit_idempotency_key(None) is None

    db = _db()
    q = JobQueue(db)
    job = q.enqueue("listing", "chain.rebuild", {}, idempotency_key=long_a)
    assert len(job.idempotency_key) <= IDEMPOTENCY_KEY_MAX
    try:
        q.enqueue("listing", "chain.rebuild", {}, idempotency_key=long_a)
        raise AssertionError("the same long key must enqueue once")
    except DuplicateJob:
        pass
    q.enqueue("listing", "chain.rebuild", {}, idempotency_key=long_b)


def test_a_wide_rebuild_fits_the_varchar_200_key_column():
    """Production: the release chain moved under 14 products, the per-product rebuild key
    carried every moved fingerprint, and Postgres refused the insert. SQLite stores any
    length, so this asserts the bound Postgres enforces."""
    db = Database("sqlite://")
    db.create_all()
    slugs = ["autumn-oak-mosaic-throw", "cloudline-baby-blanket", "harvest-table-runner",
             "hexie-coaster-set", "market-basket-trio", "mosaic-placemat-pair",
             "nordic-forest-mosaic-throw", "nordic-star-ornaments", "pet-snuggle-mat",
             "pressed-flower-motifs", "pumpkin-cluster-set", "spooky-garland",
             "valentine-heart-garland", "winter-village-graphghan"]
    old = A.fingerprint("chain-v1")
    with db.session() as s:
        for slug in slugs:
            A.record(s, artefact_class="pdf", artefact_key=f"{slug}.pdf", product_slug=slug,
                     inputs={"chain:release": old, f"cir:{slug}": A.fingerprint(slug)})
    changed = {"chain:release": A.fingerprint("chain-v2")}
    changed.update({f"cir:{slug}": A.fingerprint(slug + "-v2") for slug in slugs})
    queue = JobQueue(db)
    with db.session() as s:
        first = G.enqueue(s, queue, changed=changed, per="product", reason="chain moved")
        again = G.enqueue(s, queue, changed=changed, per="product", reason="chain moved")
    assert len(first["enqueued"]) == len(slugs), first["enqueued"]
    assert again["enqueued"] == [] and len(again["already_queued"]) == len(slugs)
    with db.session() as s:
        keys = list(s.scalars(select(Job.idempotency_key).where(
            Job.job_type == "chain.rebuild")))
    assert len(keys) == len(slugs)
    assert max(len(k) for k in keys) <= IDEMPOTENCY_KEY_MAX, max(len(k) for k in keys)
    assert all(k.startswith("rebuild:product:") for k in keys)


# ---- 3. share holds conserve work ----------------------------------------------------

def _capacity_reading(db):
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action="ops.capacity",
                       detail={"mix": dict(mixmod.BUILD_MIX), "phase": "build",
                               "tilted_toward": None}))


def _running(db, agent, job_type):
    with db.session() as s:
        s.add(Job(agent=agent, job_type=job_type, inputs={}, status=JobStatus.RUNNING,
                  leased_by="other", lease_expires_at=utcnow() + timedelta(minutes=10),
                  started_at=utcnow(), attempts=1))


def _held(db):
    with db.session() as s:
        return [r.job_id for r in s.scalars(select(AuditLog).where(
            AuditLog.action == orc.LANE_HELD_ACTION))]


def test_runnable_work_is_not_held_for_a_model_job_that_would_only_be_parked():
    db = _db()
    _capacity_reading(db)
    _spent_balance(db)
    _running(db, "orchestrator", "ops.health")
    q = JobQueue(db)
    infra = q.enqueue("orchestrator", "ops.queue_check", {}, priority=0,
                      idempotency_key="infra").id
    q.enqueue("creative_director", "creative.tournament", {}, priority=50,
              idempotency_key="model")
    assert Worker(db, "pool-1").run_once()
    assert infra not in _held(db), "held for work no worker can run"
    with db.session() as s:
        assert s.get(Job, infra).status == JobStatus.DONE


def test_with_the_provider_up_the_starved_model_job_still_wins_the_hold():
    db = _db()
    _capacity_reading(db)
    _running(db, "orchestrator", "ops.health")
    q = JobQueue(db)
    infra = q.enqueue("orchestrator", "ops.queue_check", {}, priority=0,
                      idempotency_key="infra").id
    q.enqueue("creative_director", "creative.tournament", {}, priority=50,
              idempotency_key="model")
    assert Worker(db, "pool-1").run_once()
    assert infra in _held(db), "the #30 mix is unchanged when the starved work can run"


def test_the_control_lane_is_not_held_by_the_pools_function_mix():
    db = _db()
    _capacity_reading(db)
    _running(db, "orchestrator", "ops.health")
    q = JobQueue(db)
    orch = q.enqueue("coo", "autonomy.orchestrate", {}, priority=0,
                     idempotency_key="orch").id
    q.enqueue("support", "support.triage", {}, priority=50, idempotency_key="dist")
    from brambleloop.runtime.lanes import CONTROL

    control = Worker(db, "web-2-control", job_types=sorted(CONTROL))
    assert control.run_once()
    assert orch not in _held(db)
    with db.session() as s:
        assert s.get(Job, orch).status == JobStatus.DONE
    # The pool itself still enforces the mix on the same job type.
    db2 = _db()
    _capacity_reading(db2)
    _running(db2, "orchestrator", "ops.health")
    q2 = JobQueue(db2)
    orch2 = q2.enqueue("coo", "autonomy.orchestrate", {}, priority=0,
                       idempotency_key="orch").id
    q2.enqueue("support", "support.triage", {}, priority=50, idempotency_key="dist")
    assert Worker(db2, "pool-1").run_once()
    assert orch2 in _held(db2)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"{len(fns)} passed")
