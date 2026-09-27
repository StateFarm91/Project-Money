"""Certification H: runtime wiring, proven from actual execution rather than from reading code.

A fresh temp-file database is seeded (`Registry.seed_defaults`), `Scheduler.tick` enqueues
every cadence, and `Worker.run_once` drains the queue to empty. Nothing may spend: the
network is refused at the socket, model and Etsy credentials are removed from the process
environment, and the artifact store points into a temp directory.

For every job type claimed as wiring, the test asserts the job was enqueued *by a cadence*,
authorised for the agent that ran it, and executed to DONE (or to a deliberate refusal) --
never DEAD from a missing permission, handler or module. For every library function claimed
as wired, a spy is installed on the function and the real caller is run; the spy must be hit.

Run: cd brambleloop && $PY tests/test_cert_wiring.py
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="cert_wiring_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP}/wiring.db"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI",
                      "GOOGLE_API", "STABILITY", "BRAMBLELOOP_IMAGE_KEY")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the certification harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]
socket.getaddrinfo = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import PermissionDenied, Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, Listing, Phase, utcnow  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401  (registers handlers)
from brambleloop.runtime import worker as worker_mod  # noqa: E402
from brambleloop.runtime.worker import CADENCES, Scheduler, Worker, handlers  # noqa: E402
from brambleloop.swarm import orchestrate  # noqa: E402

# The 17 rows closed as wiring, and the job types their closure notes name.
WIRING_ROWS = (41, 42, 81, 85, 91, 100, 144, 174, 175, 176, 186, 187, 192, 241, 265, 270, 313)

# The new handlers the closeout added, each of which must be on a cadence.
TARGET_JOB_TYPES = (
    "creative.blind_review", "creative.grid_tournament", "intel.acceptance",
    "ops.provenance_backfill", "finance.escalation_check",
    "improve.measure", "improve.mine", "improve.monitor",
    "swarm.review", "swarm.allocate", "swarm.orphans", "swarm.backlog",
    "growth.experiments",
    # The cadences the wiring rows ride on.
    "improve.weekly", "improve.retrospective", "culture.sweep", "mjs.scan",
    "chain.rebuild",
)


# ---- spies ---------------------------------------------------------------

class Spy:
    def __init__(self, module, name: str):
        self.module, self.name = module, name
        self.original = getattr(module, name)
        self.calls: list[tuple] = []

        def wrapper(*a, **k):
            self.calls.append((a, k))
            return self.original(*a, **k)

        wrapper.__wrapped__ = self.original  # type: ignore[attr-defined]
        setattr(module, name, wrapper)

    def restore(self) -> None:
        setattr(self.module, self.name, self.original)


def _spies() -> dict[str, Spy]:
    from brambleloop.commerce import buyer_trust
    from brambleloop.creative import audit as creative_audit
    from brambleloop.culture import radar
    from brambleloop.growth import experiments
    from brambleloop.improve import cells, director
    from brambleloop.intel import observe
    from brambleloop.visual import gallery

    return {
        "disclosure_check": Spy(buyer_trust, "disclosure_check"),
        "priority_for@tick": Spy(worker_mod, "priority_for"),
        "launch_pack": Spy(experiments, "launch_pack"),
        "radar.memory": Spy(radar, "memory"),
        "adaptive_interval": Spy(observe, "adaptive_interval"),
        "escalation_plan": Spy(gallery, "escalation_plan"),
        "agent_quality": Spy(orchestrate, "agent_quality"),
        "allocate": Spy(orchestrate, "allocate"),
        "resolve_orphans": Spy(orchestrate, "resolve_orphans"),
        "feed_idle": Spy(orchestrate, "feed_idle"),
        "retirement_review": Spy(orchestrate, "retirement_review"),
        "persist_catalogue_audit": Spy(creative_audit, "persist_catalogue_audit"),
        "director.conflicts": Spy(director, "conflicts"),
        "cells.retrospective": Spy(cells, "retrospective"),
    }


# ---- the drain -----------------------------------------------------------

_STATE: dict = {}


def _drain(db: Database, w: Worker, limit: int = 3000, max_seconds: float = 1200.0) -> int:
    n, t0 = 0, time.monotonic()
    while w.run_once():
        n += 1
        if n >= limit or time.monotonic() - t0 > max_seconds:
            raise AssertionError(f"queue did not drain: {n} jobs in {time.monotonic() - t0:.0f}s")
    return n


def drained() -> dict:
    """One tick plus a full drain, shared by the read-only tests below."""
    if _STATE:
        return _STATE
    cwd = os.getcwd()
    os.chdir(_TMP)  # any relative write lands in the temp dir, never in the repository
    try:
        db = Database(os.environ["BRAMBLELOOP_DATABASE_URL"])
        db.create_all()
        Registry(db).seed_defaults()
        spies = _spies()
        now = utcnow()
        enqueued = Scheduler(db).tick(now)
        w = Worker(db, "cert-wiring", phase=Phase.SHADOW, lease_seconds=900)
        ran = _drain(db, w)
        # Frozen at the end of the drain: later tests call some of these functions through
        # other paths (the API test), and a count read later would credit the drain with it.
        at_drain = {k: len(v.calls) for k, v in spies.items()}
        _STATE.update(db=db, spies=spies, enqueued=enqueued, worker=w, ran=ran, now=now,
                      at_drain=at_drain)
    finally:
        os.chdir(cwd)
    return _STATE


def _jobs(db: Database, job_type: str | None = None) -> list[Job]:
    with db.session() as s:
        q = select(Job).order_by(Job.id)
        if job_type:
            q = q.where(Job.job_type == job_type)
        rows = list(s.scalars(q))
        for r in rows:
            s.expunge(r)
        return rows


def _cadence_for(job_type: str) -> tuple[str, str]:
    for name, agent, jt, _p in CADENCES:
        if jt == job_type:
            return name, agent
    raise AssertionError(f"{job_type} is on no cadence")


WIRING_FAILURE_MARKERS = ("permission denied", "no handler registered", "ModuleNotFoundError",
                          "ImportError", "AttributeError", "NameError")


# ---- tests ---------------------------------------------------------------

def test_every_target_is_scheduled_handled_and_permitted_statically():
    reg = Registry(drained()["db"])
    for jt in TARGET_JOB_TYPES:
        _name, agent = _cadence_for(jt)
        assert handlers.get(jt) is not None, f"no handler for {jt}"
        try:
            reg.authorize(agent, jt)
        except PermissionDenied as e:
            raise AssertionError(f"cadence agent {agent} may not run {jt}: {e}")


def test_each_target_was_enqueued_by_its_cadence_and_executed_to_done():
    st = drained()
    db = st["db"]
    problems = []
    for jt in TARGET_JOB_TYPES:
        name, agent = _cadence_for(jt)
        rows = [j for j in _jobs(db, jt) if (j.idempotency_key or "").startswith(f"cadence:{name}:")]
        if not rows:
            problems.append(f"{jt}: no job enqueued by cadence {name}")
            continue
        j = rows[0]
        if j.agent != agent:
            problems.append(f"{jt}: ran as {j.agent}, cadence says {agent}")
        if j.status is not JobStatus.DONE:
            problems.append(f"{jt}: status {j.status.value}: {(j.last_error or '')[:200]}")
        if j.status is JobStatus.DONE and not isinstance(j.outputs, dict):
            problems.append(f"{jt}: DONE with no outputs")
    assert not problems, problems


def test_no_job_in_the_drain_died_except_by_deliberate_refusal():
    db = drained()["db"]
    bad = []
    for j in _jobs(db):
        err = j.last_error or ""
        if j.status in (JobStatus.DEAD, JobStatus.FAILED) or j.status is JobStatus.PENDING:
            if not err.startswith("capability not enabled"):
                bad.append((j.id, j.job_type, j.status.value, err[:160]))
        if any(m in err for m in WIRING_FAILURE_MARKERS):
            bad.append((j.id, j.job_type, j.status.value, err[:160]))
    assert not bad, bad
    dead = [j for j in _jobs(db) if j.status is JobStatus.DEAD]
    assert all(j.job_type == "store.publish" for j in dead), [(j.job_type, j.last_error[:80]) for j in dead]


def test_scheduler_tick_calls_priority_for_and_bands_every_cadence_job():
    """#187: the scheduler enqueues at priority_for(job_type), observed through a spy."""
    st = drained()
    spy = st["spies"]["priority_for@tick"]
    called = {a[0] for a, _k in spy.calls}
    cadence_types = {jt for _n, _a, jt, _p in CADENCES}
    assert cadence_types <= called, sorted(cadence_types - called)
    for j in _jobs(st["db"]):
        if (j.idempotency_key or "").startswith("cadence:"):
            assert j.priority == orchestrate.priority_for(j.job_type), (j.job_type, j.priority)


def test_follow_on_work_is_enqueued_at_its_band_too():
    """#187 says customer incidents and truth defects go first. A band applied only at the
    scheduler leaves every handler-enqueued job (gate.certify, finance.challenge, the whole
    release chain) at the queue default, below housekeeping."""
    db = drained()["db"]
    wrong = sorted({(j.job_type, j.priority, orchestrate.priority_for(j.job_type))
                    for j in _jobs(db)
                    if j.priority != orchestrate.priority_for(j.job_type)})
    assert not wrong, f"job type, enqueued priority, its band: {wrong}"


def test_swarm_handlers_reach_their_runtime_functions():
    """#174 #175 #176 #186 via swarm.review/allocate/orphans/backlog."""
    from brambleloop.core.models import SwarmAllocation

    st = drained()
    sp = st["spies"]
    for key in ("agent_quality", "allocate", "resolve_orphans", "feed_idle"):
        assert st["at_drain"][key], f"{key} was never called by its handler"
    with st["db"].session() as s:
        assert s.scalar(select(SwarmAllocation).limit(1)) is not None, "no SwarmAllocation row"
        actions = {a.action for a in s.scalars(select(AuditLog))}
    for action in ("swarm.agent_review", "swarm.allocation", "swarm.orphans", "swarm.backlog"):
        assert action in actions, action


def test_weekly_cycle_calls_retirement_review_autopsy_memory_and_director():
    """#192 (retirement_review), #85 (persist_catalogue_audit), #91 (director.conflicts)."""
    at = drained()["at_drain"]
    for key in ("retirement_review", "persist_catalogue_audit", "director.conflicts"):
        assert at[key], f"{key} not reached from improve.weekly"


def test_retrospective_reaches_cells_and_reports_the_new_sections():
    """#100: the retrospective handler calls cells.retrospective and the record carries the
    stop-doing list and next upgrades the closure note claims."""
    st = drained()
    assert st["at_drain"]["cells.retrospective"]
    with st["db"].session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "improvement.retrospective")
                       .order_by(AuditLog.id.desc()))
        detail = dict(row.detail or {}) if row else {}
    for key in ("stop_doing", "top_next_upgrades"):
        assert key in detail, (key, sorted(detail))


def test_listing_draft_actually_runs_the_disclosure_check():
    """#41's closure: 'disclosure_check runs on every listing'. Measured on the real chain
    order. Against 63f2493 the check ran in listing.draft, before listing.seo writes the copy,
    so it read no Listing row and returned UNMEASURED without ever calling disclosure_check
    (C-47). The repair measures where the copy exists: every listing.seo must run
    disclosure_check on the persisted copy and record the reading; a draft-time UNMEASURED is
    no longer the whole story."""
    st = drained()
    seos = [j for j in _jobs(st["db"], "listing.seo") if j.status is JobStatus.DONE]
    assert seos, "no listing.seo ran"
    unchecked = [j.inputs.get("slug") for j in seos
                 if not (j.outputs or {}).get("disclosures", {}).get("checked")]
    assert st["at_drain"]["disclosure_check"], (
        f"buyer_trust.disclosure_check was never called across {len(seos)} listings; "
        f"unchecked: {unchecked}")
    assert not unchecked, unchecked
    with st["db"].session() as s:
        recorded = {r.artifact for r in s.scalars(select(AuditLog).where(
            AuditLog.action.in_(("listing.disclosure_checked", "listing.disclosure_finding"))))}
    # Per product, not per job: an evergreen repositioning (launch.plan's pivot) re-runs
    # listing.seo for the same release, so counting jobs against distinct releases fails for a
    # correct chain (C-73). Every product whose SEO ran must have its reading recorded.
    recorded_slugs = {str(a).split("@")[0] for a in recorded}
    missing = {j.inputs.get("slug") for j in seos} - recorded_slugs
    assert not missing, (missing, recorded)


def test_growth_experiments_calls_launch_pack_for_every_drafted_listing():
    """#241/#265: the next day's growth.experiments cadence registers a pack per listing."""
    from brambleloop.core.models import RegisteredExperiment

    st = drained()
    db = st["db"]
    spy = st["spies"]["launch_pack"]
    before = len(spy.calls)
    tomorrow = st["now"] + timedelta(days=1, minutes=5)
    assert "growth_experiments" in Scheduler(db).tick(tomorrow)
    w = Worker(db, "cert-wiring-2", phase=Phase.SHADOW, job_types=["growth.experiments"])
    assert w.run_once()
    job = [j for j in _jobs(db, "growth.experiments")][-1]
    assert job.status is JobStatus.DONE, job.last_error
    with db.session() as s:
        listed = {r.product_slug for r in s.scalars(select(Listing))}
        registered = {r.product_slug for r in s.scalars(select(RegisteredExperiment))}
    called = {k.get("product") for _a, k in spy.calls[before:]}
    assert listed and listed <= called, sorted(listed - called)
    assert listed <= registered, sorted(listed - registered)


def test_mjs_scan_consults_the_adaptive_interval_before_any_request():
    """#313 via scan_or_explain. A dummy credential makes the reader configured; the scan
    itself is replaced so nothing is sent. With a scan recorded minutes ago the job defers
    without scanning; with none the scan is attempted."""
    from brambleloop.core.models import BenchmarkObservation
    from brambleloop.intel import benchmarks, observe

    st = drained()
    db = st["db"]
    spy = st["spies"]["adaptive_interval"]
    attempted = []

    def fake_scan(*a, **k):
        attempted.append(1)
        raise RuntimeError("cert harness: scan stubbed, no request sent")

    real_scan = observe.scan
    observe.scan = fake_scan
    os.environ["ETSY_API_KEY"] = "cert-dummy-keystring"
    os.environ["ETSY_SHARED_SECRET"] = "cert-dummy-secret"
    try:
        from brambleloop.intel import etsy_public
        os.environ[etsy_public.KEYSTRING_VAR] = "cert-dummy-keystring"
        os.environ[etsy_public.SECRET_VAR] = "cert-dummy-secret"
        with db.session() as s:
            s.add(BenchmarkObservation(benchmark_key=benchmarks.MJS_KEY, kind="official_api_read",
                                       at=utcnow() - timedelta(minutes=10), detail={}))
            s.commit()
        base = len(spy.calls)
        finished_before = {j.id for j in _jobs(db, "mjs.scan")
                           if j.status is not JobStatus.PENDING}
        t1 = st["now"] + timedelta(hours=2, minutes=1)
        Scheduler(db).tick(t1)
        w = Worker(db, "cert-wiring-3", phase=Phase.SHADOW, job_types=["mjs.scan"])
        while w.run_once():
            pass
        ran = [j for j in _jobs(db, "mjs.scan") if j.id not in finished_before]
        assert ran, "no fresh mjs.scan job ran"
        for job in ran:
            assert job.status is JobStatus.DONE, (job.status.value, job.last_error)
            assert "adaptive interval" in (job.outputs or {}).get("reason", ""), job.outputs
        assert len(spy.calls) > base, "adaptive_interval not consulted"
        assert not attempted, "a scan that was not due was attempted"
        # Now make it due: the only recorded scan is a day old, past the 6 h fallback.
        with db.session() as s:
            for row in s.scalars(select(BenchmarkObservation)):
                row.at = utcnow() - timedelta(hours=30)
            s.commit()
        before = len(spy.calls)
        Scheduler(db).tick(t1 + timedelta(hours=2, minutes=1))
        while w.run_once():
            pass
        assert len(spy.calls) > before and attempted, (
            "a due scan was not attempted after consulting the interval")
    finally:
        observe.scan = real_scan
        for k in ("ETSY_API_KEY", "ETSY_SHARED_SECRET"):
            os.environ.pop(k, None)
        from brambleloop.intel import etsy_public
        os.environ.pop(etsy_public.KEYSTRING_VAR, None)
        os.environ.pop(etsy_public.SECRET_VAR, None)


def test_store_publish_walks_the_escalation_ladder_on_a_failed_parity_dimension():
    """#81: gallery.escalation_plan reached via parity.assess inside store.publish, in
    shadow, from a recorded blind review that found the listing materially inferior."""
    st = drained()
    db = st["db"]
    spy = st["spies"]["escalation_plan"]
    with db.session() as s:
        slug = s.scalar(select(Listing.product_slug).where(Listing.version != "collection")
                        .order_by(Listing.id))
    assert slug
    Registry(db).audit("creative_director", "creative.blind_review", artifact=slug,
                       detail={"slug": slug, "materially_inferior": True,
                               "why": "cert harness: judged inferior"})
    from brambleloop.queue.durable import JobQueue

    JobQueue(db).enqueue("store_operator", "store.publish", {"slug": slug, "version": "1.0.0"},
                         idempotency_key=f"cert-publish:{slug}")
    base = len(spy.calls)
    w = Worker(db, "cert-wiring-4", phase=Phase.SHADOW, job_types=["store.publish"])
    assert w.run_once()
    job = [j for j in _jobs(db, "store.publish") if j.idempotency_key == f"cert-publish:{slug}"][0]
    assert job.status is JobStatus.DEAD and job.last_error.startswith("capability not enabled"), (
        job.status, job.last_error)
    assert len(spy.calls) > base, "escalation_plan not reached from store.publish"
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "listing.parity",
                                              AuditLog.job_id == job.id))
        detail = dict(row.detail or {})
    assert detail.get("escalation"), detail.get("why")


def test_record_order_writes_the_bought_version():
    """#42 library half: cohorts.record_order -> buyer_trust.record_sale_version. (No
    production caller of record_order exists: ledger C-2; the row is not claimed covered.)"""
    from brambleloop.build2 import requirements as reqs
    from brambleloop.commerce import buyer_trust, cohorts

    db = drained()["db"]
    spy = Spy(buyer_trust, "record_sale_version")
    try:
        cohorts.record_customer(db, "cert-buyer")
        out = cohorts.record_order(db, "cert-buyer", "cert-order-1",
                                   product_slug="nordic-forest-mosaic-throw", version="1.0.0",
                                   price_cad=12.5, contribution_cad=10.0)
    finally:
        spy.restore()
    assert spy.calls and "version_recorded" in out, out
    assert reqs.get(42).status != reqs.COVERED, "#42 claims covered with no order ingest"


def test_api_paths_reach_radar_memory_and_the_stress_test():
    """#144 memory() and #270 stress_test are served at /api/culture and /api/growth."""
    from fastapi.testclient import TestClient

    from brambleloop.growth import mix

    drained()
    spy_mem = Spy(__import__("brambleloop.culture.radar", fromlist=["x"]), "memory")
    spy_st = Spy(mix, "stress_test")
    try:
        from brambleloop.app import main

        c = TestClient(main.app)
        assert c.get("/api/culture").status_code == 200
        assert c.get("/api/growth").status_code == 200
    finally:
        spy_mem.restore()
        spy_st.restore()
    assert spy_mem.calls, "radar.memory not reached from /api/culture"
    assert spy_st.calls, "stress_test not reached from /api/growth"


def test_radar_memory_is_read_by_some_agent_at_runtime():
    """#144: 'future agents should know which cultural territories recur annually'. In the
    drain culture.sweep ran; if no job reads memory(), only a human at /api/culture does."""
    st = drained()
    sweeps = _jobs(st["db"], "culture.sweep")
    assert sweeps and sweeps[0].status is JobStatus.DONE
    assert st["at_drain"]["radar.memory"], (
        "culture.radar.memory() was not called by any job in a full drain (culture.sweep "
        "calls route_findings, not memory/sweep); its only caller is GET /api/culture")


def test_no_row_whose_wiring_failed_here_is_still_claimed_covered():
    """The registry must not claim COVERED for a row this harness just showed unwired."""
    from brambleloop.build2 import requirements as reqs

    st = drained()
    db = st["db"]
    observed = {
        41: bool(st["at_drain"]["disclosure_check"]),
        144: bool(st["at_drain"]["radar.memory"]),
        187: all(j.priority == orchestrate.priority_for(j.job_type) for j in _jobs(db)),
    }
    status = {rid: reqs.get(rid).status for rid in WIRING_ROWS}
    print("      registry status of the 17 wiring rows:", status)
    wrong = {rid: status[rid] for rid, ok in observed.items()
             if not ok and status[rid] == reqs.COVERED}
    assert not wrong, f"claimed covered but not wired at runtime: {wrong}"


if __name__ == "__main__":
    t0 = time.monotonic()
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:900]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    sys.exit(1 if fails else 0)
