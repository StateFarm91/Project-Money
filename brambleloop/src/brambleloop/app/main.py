"""Admin dashboard + API (Master Plan section 13).

Deliberately server-rendered and dependency-light: this has to stay up unattended, and a
build pipeline that can rot is a liability rather than a feature.

The dashboard's job is to answer, at a glance, the questions an absent owner actually has:
what is the system doing, what has it refused to do, what is stuck, what has it spent, and is
anything waiting on me.
"""
from __future__ import annotations

import os
from datetime import timedelta, timezone

from fastapi import FastAPI, Header, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from sqlalchemy import func, select

from ..agents.registry import Registry
from ..core.build import identity as build_identity
from ..core import opsauth
from ..core.db import Database
from ..core.models import (
    Agent, AuditLog, Collection, ContentPiece, CostEntry, Experiment, Incident, Job,
    JobStatus, LedgerEntry, Listing, ListingAsset, OwnerAction, PatternVersion, Product,
    SpendLimit, SupportCase, utcnow,
)
from ..gateway.model_gateway import available_providers
from ..queue.durable import DuplicateJob, JobQueue
from ..runtime import pipeline  # noqa: F401  -- registers job handlers
from ..runtime.worker import Scheduler
from . import runner

APP_VERSION = "0.1.0"

db = Database()
app = FastAPI(title="Brambleloop Studio OS", version=APP_VERSION)


# What the last boot's enqueues did, readable from /health.
#
# All three boot blocks were written as `except (DuplicateJob, Exception): pass`, which is
# right about never blocking a boot and wrong about everything else: when the reference-pack
# build silently failed to enqueue across two deploys, there was no way to tell an exception
# from a duplicate key from a condition that was simply false. A swallowed exception with no
# trace is the boot-time version of a gate nobody can see refusing.
BOOT_ENQUEUES: list[dict] = []


# How long a boot job waits before it may run.
#
# A deploy rolls: for a minute or two the old container is still serving and still draining
# the queue, so a job created by the new container's startup is most likely to be taken by
# the old one -- which is exactly what happened to the corrected reference pack, three
# attempts in two minutes, all of them by the build the correction was replacing, and then
# a dead letter. The delay is not a fix for the mismatch (the version stamp is); it is what
# stops the mismatch consuming the job's attempts before the rollout has finished.
BOOT_JOB_DELAY_SECONDS = 90


def _boot_enqueue(name: str, *, when: bool, agent: str, job_type: str, key: str,
                  because: str = "", inputs: dict | None = None,
                  delay_seconds: int = BOOT_JOB_DELAY_SECONDS) -> dict:
    """Enqueue one boot job and record the outcome rather than swallowing it."""
    from datetime import timedelta

    record = {"name": name, "job_type": job_type, "key": key, "outcome": "", "detail": ""}
    payload = dict(inputs or {})
    if because:
        payload["because"] = because
    try:
        if not when:
            record["outcome"] = "not needed"
        else:
            job = JobQueue(db).enqueue(
                agent, job_type, payload, idempotency_key=key,
                run_after=utcnow() + timedelta(seconds=delay_seconds))
            record["outcome"] = "enqueued"
            record["detail"] = f"job {job.id}"
    except DuplicateJob as e:
        record["outcome"] = "duplicate"
        record["detail"] = str(e)[:200]
    except Exception as e:  # noqa: BLE001 - a boot job must never block a boot
        record["outcome"] = "error"
        record["detail"] = f"{type(e).__name__}: {e}"[:300]
    BOOT_ENQUEUES.append(record)
    return record


@app.on_event("startup")
def _startup() -> None:
    schema_changes = db.create_all()
    if schema_changes:
        # A schema change nobody can see is how a deploy breaks quietly.
        Registry(db).audit("orchestrator", "schema.migrated",
                           detail={"changes": schema_changes[:50]})
    changes = Registry(db).seed_defaults()
    if changes:
        # A deploy that silently changes an agent's authority is a deploy nobody can audit.
        Registry(db).audit("orchestrator", "agents.reconciled",
                           detail={"changes": changes[:50]})

    from ..growth.loops import seed as seed_loops
    from ..intel.benchmarks import seed as seed_benchmarks

    benchmark_changes = seed_benchmarks(db) + seed_loops(db)
    if benchmark_changes:
        Registry(db).audit("orchestrator", "benchmarks.reconciled",
                           detail={"changes": benchmark_changes[:50]})
    # Probe now rather than in six hours when a capability is credentialled and unproven.
    #
    # The gates read recorded evidence, which is right, and the evidence is written by a
    # six-hourly job -- so a credential that arrives just after a run leaves real, working
    # capability invisible for most of a day, with requirements parked on the absence of a
    # row. A deploy is exactly the moment that is most likely to be true, so a deploy asks.
    # Idempotent by the day, so a restart loop cannot turn this into a spend.
    try:
        from ..gateway import images as _images

        if _images.available() and not _images.usable(db):
            JobQueue(db).enqueue(
                "orchestrator", "ops.capability_probes", {},
                idempotency_key=f"boot-probe-{utcnow():%Y%m%d%H}")
    except (DuplicateJob, Exception):  # noqa: BLE001 - a probe must never block a boot
        pass

    # And finish an unsettled benchmark on the same principle. A credentialled candidate
    # with no scores on file is work the hourly cadence will do eventually; a deploy is a
    # cheaper moment to do it, and observations now persist per trial so an interrupted run
    # resumes rather than restarting. Bounded three ways: idempotent by the hour, refused by
    # the cumulative authorization inside the handler, and only enqueued when a candidate is
    # actually outstanding.
    try:
        from ..gateway import image_bench as _bench
        from ..gateway import images as _img

        if _bench.spent_to_date(db) < _bench.BENCHMARK_CEILING_CAD:
            outstanding = [c.key for c in _bench.CANDIDATES
                           if c.can_hold_an_identity
                           and c.key in set(_img.available())
                           and _bench.stored_result(db, c) is None]
            if outstanding:
                JobQueue(db).enqueue(
                    "creative_director", "creative.image_benchmark",
                    {"because": outstanding},
                    idempotency_key=f"boot-bench-{utcnow():%Y%m%d%H}")
    except (DuplicateJob, Exception):  # noqa: BLE001 - never block a boot
        pass

    # And the canonical-model tournament, on the same principle. It is keyed on the brief,
    # so this runs once per brief rather than once per deploy -- a changed direction renders
    # a new field, an unchanged one does nothing. Bounded by the same idempotency and by the
    # handler's own spend check.
    #
    # The idempotency key carries the brief fingerprint, not only the hour. An hour-only key
    # guards the clock while the work is keyed on the brief, and the two disagree exactly
    # when it matters: a corrected brief deployed in the same hour as the previous one found
    # the hour's key already spent, enqueued nothing, and reported "not yet run" until the
    # hour turned. The hour stays in the key so a failed attempt retries rather than being
    # locked out for the life of the brief.
    try:
        from ..runtime.release import _tournament_on_file, tournament_boot_key
        from ..gateway import images as _img2

        from ..visual import brief as _brief

        if (_img2.available() and not _brief.owner_candidate_supplied()
                and _tournament_on_file(db) is None):
            JobQueue(db).enqueue(
                "creative_director", "creative.model_tournament", {},
                idempotency_key=tournament_boot_key(utcnow()))
    except (DuplicateJob, Exception):  # noqa: BLE001 - never block a boot
        pass

    # And the reference pack for the owner's supplied candidate, on the same principle and
    # keyed the same way: on the candidate rather than on the clock, so a new concept builds
    # on the next deploy and an unchanged one does nothing.
    try:
        from ..runtime.release import _pack_on_file, pack_boot_key
        from ..gateway import images as _img3

        from ..visual import reference_pack as _pack

        needed = bool(_img3.available()) and _pack_on_file(db) is None
        _boot_enqueue("model_reference_pack", when=needed, agent="creative_director",
                      job_type="creative.model_reference_pack",
                      key=pack_boot_key(utcnow()),
                      inputs={"pack_version": _pack.PACK_VERSION})
    except Exception as e:  # noqa: BLE001 - never block a boot
        BOOT_ENQUEUES.append({"name": "model_reference_pack", "outcome": "error",
                              "detail": f"{type(e).__name__}: {e}"[:300]})

    # And freeze the pack the owner approved, once. Enqueued whenever an approval is
    # recorded and no canonical identity exists yet: the handler refuses a second
    # canonical outright, so this is safe to re-ask on every deploy and does nothing the
    # moment she is frozen. A job rather than an authenticated call, because the operator
    # token is a secret this repository must never hold and the owner's decision is not
    # one (#200).
    try:
        from ..visual import freeze as _freeze
        from ..visual import model_registry as _registry

        _wanted = bool(_freeze.approved()) and _registry.canonical_pack(db) is None
        _boot_enqueue("model_freeze", when=_wanted, agent="creative_director",
                      job_type="creative.model_freeze",
                      key=f"boot-freeze-{_freeze.approved().get('at', 'none')}",
                      inputs={"approved_at": _freeze.approved().get("at", "")})
    except Exception as e:  # noqa: BLE001 - never block a boot
        BOOT_ENQUEUES.append({"name": "model_freeze", "outcome": "error",
                              "detail": f"{type(e).__name__}: {e}"[:300]})

    # And re-ask #300's chain while its assets link is still open. The cadence is weekly,
    # which is right unattended and wrong immediately after the thing that was blocking it
    # changes -- the canonical identity was frozen minutes after this week's run had
    # already happened, so the next scheduled answer would have been seven days stale.
    # Self-limiting: `cycle_proof_incomplete` returns False once the link closes, so this
    # stops asking rather than spending on every deploy forever.
    try:
        from ..runtime.release import cycle_proof_incomplete

        _open = cycle_proof_incomplete(db)
        _boot_enqueue("seasonal_cycle_proof", when=_open, agent="publishing",
                      job_type="seasonal.cycle_proof",
                      key=f"boot-cycle-proof-"
                          f"{build_identity().get('commit_short', 'dev')}",
                      inputs={})
    except Exception as e:  # noqa: BLE001 - never block a boot
        BOOT_ENQUEUES.append({"name": "seasonal_cycle_proof", "outcome": "error",
                              "detail": f"{type(e).__name__}: {e}"[:300]})

    # And one owned product image per certified release. Idempotent by product and version
    # inside the handler, so a deploy re-attempts a render that failed and does nothing at
    # all once a release has its picture.
    try:
        from ..gateway import images as _img4

        _boot_enqueue("owned_photography", when=bool(_img4.usable(db)),
                      agent="publishing", job_type="assets.owned_photography",
                      key=f"boot-owned-asset-{build_identity().get('commit_short', 'dev')}")
    except Exception as e:  # noqa: BLE001 - never block a boot
        BOOT_ENQUEUES.append({"name": "owned_photography", "outcome": "error",
                              "detail": f"{type(e).__name__}: {e}"[:300]})

    # And the model-bearing frame, on the same principle: keyed on the rendering method
    # rather than on the clock. Its cadence is daily, which is right unattended and wrong
    # in exactly the case that matters -- a corrected prompt deployed an hour after the
    # day's frame failed would wait a day to be asked again, and the record in between
    # would be evidence about the method that was replaced.
    #
    # Self-limiting three ways. `what_to_do_next` renders nothing once the release has a
    # frame that cleared every floor, nothing once this method has spent its attempts on
    # this release, and nothing at all once a floor has failed every time this method was
    # asked -- so this asks on every deploy without spending on every deploy, and a deploy
    # does not buy another answer to a question already settled.
    try:
        from ..gateway import images as _img5
        from ..publish import model_photography as _mphoto
        from ..products.builder import for_slug
        from ..runtime.release import _model_bearing_slug

        _slug = _model_bearing_slug(db) if _img5.usable(db) else ""
        _cir = for_slug(_slug) if _slug else None
        _move = (_mphoto.what_to_do_next(db, slug=_slug, version=_cir.version)
                 if _cir else {"render": False, "why": "no certified product needs her"})
        _boot_enqueue("model_photography", when=bool(_move["render"]),
                      agent="publishing", job_type=_mphoto.ACTION,
                      key=f"boot-model-frame-{_slug}-{_mphoto.METHOD_VERSION}-"
                          f"{build_identity().get('commit_short', 'dev')}",
                      inputs={"slug": _slug})
        if not _move["render"]:
            BOOT_ENQUEUES[-1]["why"] = _move["why"][:300]
    except Exception as e:  # noqa: BLE001 - never block a boot
        BOOT_ENQUEUES.append({"name": "model_photography", "outcome": "error",
                              "detail": f"{type(e).__name__}: {e}"[:300]})

    # And ask once whether the photographic-realism standard can be met at all, keyed on
    # the checks rather than on the clock. One vision call about a public benchmark image;
    # nothing is rendered, copied or re-hosted.
    try:
        from ..runtime.release import photoreal_calibration
        from ..visual import photoreal as _photoreal

        _needed = photoreal_calibration(db) is None
        _boot_enqueue("photoreal_calibration", when=_needed, agent="creative_director",
                      job_type="creative.photoreal_calibration",
                      # The commit is in the key for the reason the cycle-proof key has
                      # it. The first attempt died on a missing agent permission and its
                      # dead letter kept the key, so the deploy carrying the fix enqueued
                      # nothing and reported `duplicate` -- an idempotency key outliving
                      # the defect it recorded, which is how a fix never gets to run.
                      # Self-limiting either way: this asks nothing once a calibration of
                      # these checks exists.
                      key=(f"boot-photoreal-calibration-{_photoreal.CHECKS_VERSION}-"
                           f"{build_identity().get('commit_short', 'dev')}"))
    except Exception as e:  # noqa: BLE001 - never block a boot
        BOOT_ENQUEUES.append({"name": "photoreal_calibration", "outcome": "error",
                              "detail": f"{type(e).__name__}: {e}"[:300]})

    runner.start(db)


@app.on_event("shutdown")
def _shutdown() -> None:
    runner.stop()


# ---- health ---------------------------------------------------------------


@app.get("/health")
def health() -> JSONResponse:
    """Liveness + a real readiness signal: can we actually reach the database?"""
    try:
        with db.session() as s:
            s.execute(select(func.count()).select_from(Job))
        healthy = True
        detail = "ok"
    except Exception as e:  # noqa: BLE001
        healthy = False
        detail = f"{type(e).__name__}: {e}"
    return JSONResponse(
        {"status": "ok" if healthy else "degraded", "version": APP_VERSION, "db": detail,
         "build": build_identity(), "runner": runner.STATE.to_dict(),
         # What this boot's enqueues actually did. A swallowed exception with no trace is
         # the boot-time version of a gate nobody can see refusing.
         "boot_enqueues": list(BOOT_ENQUEUES)},
        status_code=200 if healthy else 503,
    )


# ---- api ------------------------------------------------------------------


@app.get("/api/status")
def api_status() -> dict:
    q = JobQueue(db)
    with db.session() as s:
        products = s.scalar(select(func.count()).select_from(Product)) or 0
        certified = s.scalar(
            select(func.count()).select_from(PatternVersion).where(PatternVersion.certified)
        ) or 0
        incidents = s.scalar(
            select(func.count()).select_from(Incident).where(Incident.resolved == False)  # noqa: E712
        ) or 0
        opex = s.scalar(select(func.sum(CostEntry.amount_cad))) or 0.0
        revenue = s.scalar(select(func.sum(LedgerEntry.gross_cad))) or 0.0
        owner_open = s.scalar(
            select(func.count()).select_from(OwnerAction).where(OwnerAction.done == False)  # noqa: E712
        ) or 0
    return {
        "version": APP_VERSION,
        # Which commit this image was built from. The app version is hand-maintained and
        # therefore proves nothing about a deploy; this is the only field that says whether
        # a fix has actually reached production, and it says `unknown` when it cannot tell.
        "build": build_identity(),
        "queue": q.counts(),
        # Split, because the raw count is 99% Shadow Mode working correctly. A publication
        # job dying is a refusal, not a failure, and a number dominated by healthy refusals
        # is an alarm nobody can read. `/api/queue/dead` groups them.
        "dead_letters": len(q.dead_letters()),
        "dead_letter_refusals": sum(1 for j in q.dead_letters()
                                    if j.job_type == "store.publish"),
        "dead_letter_defects": sum(1 for j in q.dead_letters()
                                   if j.job_type != "store.publish"),
        "products": products,
        "certified_versions": certified,
        "open_incidents": incidents,
        "agent_opex_cad": round(float(opex), 4),
        "revenue_cad": round(float(revenue), 2),
        "owner_actions_open": owner_open,
        "runner": runner.STATE.to_dict(),
        # Reported rather than assumed. An empty list is the truthful answer until a key is
        # configured, and no part of the system may imply a model integration that does not
        # exist.
        "model_providers": available_providers(),
    }


@app.post("/api/scheduler/tick")
def api_tick() -> dict:
    """Cron target. Idempotent per cadence window, so calling it often is harmless."""
    return {"enqueued": Scheduler(db).tick()}


@app.get("/api/catalogue")
def api_catalogue() -> dict:
    """What the shop would be, if it were open. Drafted, never published."""
    with db.session() as s:
        listings = list(s.scalars(select(Listing)))
        assets = list(s.scalars(select(ListingAsset)))
        content = list(s.scalars(select(ContentPiece)))
        collections = list(s.scalars(select(Collection)))
        products = {p.id: p for p in s.scalars(select(Product))}
        certified = {pv.product_id: pv for pv in s.scalars(
            select(PatternVersion).where(PatternVersion.certified == True))}  # noqa: E712

    by_slug: dict[str, int] = {}
    for a in assets:
        by_slug[a.product_slug] = by_slug.get(a.product_slug, 0) + 1
    content_by_slug: dict[str, int] = {}
    for c in content:
        content_by_slug[c.product_slug] = content_by_slug.get(c.product_slug, 0) + 1

    return {
        "published": False,
        "why": ("BRAMBLELOOP_PHASE=shadow. There is no Etsy, Pinterest, email or messaging "
                "integration in this system, so nothing here can reach a customer."),
        "listings": [
            {"slug": l.product_slug, "version": l.version, "title": l.title,
             "price_cad": l.price_cad, "tags": len(l.tags), "state": l.state,
             "search_share": round(l.seo_score, 3),
             "chain_version": l.chain_version,
             "release": (l.release_hash or "")[:12],
             "images": by_slug.get(l.product_slug, 0),
             "content_pieces": content_by_slug.get(l.product_slug, 0)}
            for l in sorted(listings, key=lambda x: -x.seo_score)
        ],
        "collections": [{"slug": c.slug, "title": c.title, "family": c.family}
                        for c in collections],
        "totals": {"listings": len(listings), "listing_images": len(assets),
                   "content_pieces": len(content), "collections": len(collections),
                   "certified_patterns": len(certified), "products": len(products)},
    }


@app.get("/api/finance")
def api_finance() -> dict:
    """The books, the CFO's view and where CA$100K stands. Every figure observed."""
    from ..finance.books import Books, cfo_challenge, trajectory

    books = Books(db)
    pl = books.profit_and_loss()
    with db.session() as s:
        limits = list(s.scalars(select(SpendLimit)))
        validated = s.scalar(select(func.count()).select_from(PatternVersion).where(
            PatternVersion.certified == True)) or 0  # noqa: E712
        listings = s.scalar(select(func.count()).select_from(Listing)) or 0

    return {
        "profit_and_loss": pl.to_dict(),
        "unit_economics": books.unit_economics(products_validated=validated,
                                               listings_drafted=listings),
        "cfo_challenges": [c.to_dict() for c in cfo_challenge(
            pl, limits=limits, infra_monthly_cad=7.0, infra_ceiling_cad=20.0)],
        "trajectory": trajectory(pl),
    }


@app.get("/api/support")
def api_support(limit: int = 50) -> dict:
    with db.session() as s:
        cases = list(s.scalars(select(SupportCase).order_by(SupportCase.id.desc())
                               .limit(min(limit, 500))))
        return {
            "cases": [{"id": c.id, "at": c.at.isoformat(), "desk": c.specialist,
                       "product": c.product_slug, "version": c.version,
                       "escalated": c.escalated, "sent": c.sent,
                       "question": c.question[:160], "answer": c.answer[:400]}
                      for c in cases],
            "nothing_sent": all(not c.sent for c in cases),
        }


@app.post("/api/plan-cycle")
def api_plan_cycle(as_of: str | None = None) -> dict:
    """Enqueue a planning cycle now instead of waiting for the daily cadence.

    GREEN: it enqueues work the system already does on a schedule, spends nothing, and cannot
    publish -- shadow mode refuses at the far end regardless of who started the run.

    `as_of` sets the date the radar scores against, and also scopes the downstream idempotency
    keys, so re-running a cycle for a date already processed collapses instead of duplicating.
    Running it for a new date re-scores the pool against that calendar, which is the point:
    the portfolio changes with the date, not with the catalogue.
    """
    payload = {"as_of": as_of} if as_of else {}
    key = f"plan.cycle:{as_of}" if as_of else None
    try:
        job = JobQueue(db).enqueue("orchestrator", "plan.cycle", payload,
                                   idempotency_key=key)
    except DuplicateJob:
        return {"enqueued": False, "reason": f"a cycle for {as_of} is already queued"}
    return {"enqueued": True, "job_id": job.id, "as_of": as_of}


@app.post("/api/chain-rebuild")
def api_chain_rebuild() -> dict:
    """Restart the post-certification chain for releases whose listing is missing or stale.

    The cadence runs hourly, which is right for an unattended system and slow when a deploy
    has just landed a fix that needs to reach shipped products. GREEN: it enqueues work the
    system already does on a schedule, spends nothing, and cannot publish.
    """
    # Keyed to the minute: a burst of clicks collapses into one rebuild, and an operator who
    # genuinely wants another can have it a minute later. A rebuild is idempotent anyway, but
    # queueing fifty of them turns a safe operation into a self-inflicted load test.
    key = f"chain.rebuild:{utcnow():%Y%m%dT%H%M}"
    try:
        job = JobQueue(db).enqueue("listing", "chain.rebuild", {}, idempotency_key=key)
    except DuplicateJob:
        return {"enqueued": False,
                "reason": "a rebuild was already queued this minute; it is idempotent, so "
                          "the queued one does the same work"}
    return {"enqueued": True, "job_id": job.id}


@app.post("/api/launch-readiness")
def api_launch_readiness() -> dict:
    """Re-assess launch readiness now, rather than at the next daily cadence.

    The same argument as `/api/chain-rebuild`, for the same reason. A daily assessment is
    right for an unattended system and too slow the moment a deploy changes what the owner
    queue should say: the owner's queue then holds yesterday's wording until midnight, and
    the one time that mattered it was holding a fee figure costed for nine listings against
    a catalogue of sixteen.

    GREEN: it enqueues work the system already does on a schedule, spends nothing, publishes
    nothing, and only ever writes to the owner-action queue.
    """
    # Keyed to the minute, like the rebuild: a burst of clicks collapses into one
    # assessment, and the assessment is idempotent anyway.
    key = f"launch.readiness:{utcnow():%Y%m%dT%H%M}"
    try:
        job = JobQueue(db).enqueue("orchestrator", "launch.readiness", {},
                                   idempotency_key=key)
    except DuplicateJob:
        return {"enqueued": False,
                "reason": "an assessment was already queued this minute; it is idempotent, "
                          "so the queued one does the same work"}
    return {"enqueued": True, "job_id": job.id}



@app.get("/api/continuity")
def api_continuity() -> dict:
    """Continuity status. Deliberately says nothing a stranger could use.

    Reports whether backups are being proved and whether the archive can be retrieved at
    all, without exposing the database, its contents or its address.
    """
    from sqlalchemy import desc

    from ..core import continuity

    with db.session() as s:
        recent = list(s.scalars(
            select(AuditLog).where(AuditLog.action.in_(
                ("continuity.verified", "continuity.failed")))
            .order_by(desc(AuditLog.id)).limit(1)))
    last = recent[0] if recent else None
    return {
        "last_proof_at": last.at.isoformat() if last else None,
        "last_proof_ok": (last.action == "continuity.verified") if last else None,
        "last_proof": (last.detail or {}) if last else {},
        "archive_retrievable": opsauth.configured(),
        "credential": opsauth.token_health(),
        "retained": continuity.retained(db),
        "survives": {"container_replacement": True, "redeploy": True,
                     "provider_loss": False},
        "note": ("The archive is downloaded through GET /api/continuity/export with the "
                 "operator credential. Without that credential the endpoint is closed to "
                 "everyone, including the owner. Retained archives live in the database "
                 "they describe: that survives a container replacement, a redeploy and a "
                 "crash, and not the loss of the provider, which is an owner item."),
    }


@app.post("/api/continuity/verify")
def api_continuity_verify() -> dict:
    """Run the export-and-restore proof now rather than at the next scheduled window."""
    key = f"ops.continuity:{utcnow():%Y%m%dT%H%M}"
    try:
        job = JobQueue(db).enqueue("orchestrator", "ops.continuity", {},
                                   idempotency_key=key)
    except DuplicateJob:
        return {"enqueued": False,
                "reason": "a continuity proof was already queued this minute"}
    return {"enqueued": True, "job_id": job.id}


@app.get("/api/queue/cadences")
def api_queue_cadences() -> dict:
    """Every scheduled cadence, when it last ran, and what it returned.

    `/api/status` says the queue is moving and `/api/build` says the watchdog is happy, and
    neither can answer "did the weekly discovery run, and what did it say?". A cadence that
    completes reporting nothing to do looks identical to a cadence that never fired, and both
    look identical to a healthy queue -- so the outcome is the thing worth exposing, not the
    count.
    """
    from sqlalchemy import desc, select

    from ..core.models import Job, JobStatus
    from ..runtime.worker import CADENCES

    out = []
    with db.session() as s:
        for name, agent, job_type, period in CADENCES:
            rows = list(s.scalars(
                select(Job).where(Job.job_type == job_type)
                .order_by(desc(Job.id)).limit(1)))
            job = rows[0] if rows else None
            out.append({
                "cadence": name, "agent": agent, "job_type": job_type,
                "every_hours": round(period / 3600, 2),
                "last_job_id": job.id if job else None,
                "last_status": job.status.value if job and hasattr(job.status, "value")
                else (str(job.status) if job else "never_enqueued"),
                "last_finished_at": (job.finished_at.isoformat()
                                     if job and job.finished_at else None),
                "last_outputs": (job.outputs or {}) if job else {},
                "last_error": (job.last_error or "")[:200] if job else "",
            })
    never = [r["cadence"] for r in out if r["last_status"] == "never_enqueued"]
    no_op = [r["cadence"] for r in out
             if isinstance(r["last_outputs"], dict) and r["last_outputs"].get("ran") is False]
    return {
        "cadences": out,
        "never_enqueued": never,
        "last_run_was_a_no_op": no_op,
        "note": ("A cadence that completed reporting nothing to do is not the same as one "
                 "that never fired, and neither is visible in a queue depth of zero. A "
                 "no-op that contradicts the evidence is a defect wearing a success."),
    }


@app.get("/api/queue/dead")
def api_queue_dead() -> dict:
    """What is in the dead-letter queue, grouped by job type and failure.

    `/api/status` has reported a dead-letter *count* since the first deploy, and a count is
    not a diagnosis: it says something is wrong and gives nobody a way to find out what,
    which is how a number becomes wallpaper. Grouped rather than listed because a hundred
    dead letters are usually four defects.

    Public and read-only. The errors are this system's own tracebacks; nothing in them comes
    from a credential, because no client here puts one in an exception.
    """
    q = JobQueue(db)
    groups: dict[tuple[str, str], dict] = {}
    for job in q.dead_letters():
        head = (job.last_error or "").strip().split("\n")[0][:160]
        key = (job.job_type, head)
        row = groups.setdefault(key, {"job_type": job.job_type, "error": head, "count": 0,
                                      "first_seen": None, "last_seen": None,
                                      "example_job_id": job.id})
        row["count"] += 1
        at = job.finished_at or job.created_at
        stamp = at.isoformat() if at else None
        if stamp:
            row["first_seen"] = min(row["first_seen"] or stamp, stamp)
            row["last_seen"] = max(row["last_seen"] or stamp, stamp)
    rows = sorted(groups.values(), key=lambda r: -r["count"])
    return {
        "dead_letters": sum(r["count"] for r in rows),
        "distinct_failures": len(rows),
        "groups": rows,
        "note": ("A hundred dead letters are usually four defects. Re-driving them is "
                 "POST /api/queue/requeue and is authenticated; publication refusals are "
                 "never re-driven, because they are refusals working correctly."),
    }


@app.post("/api/queue/requeue")
def api_queue_requeue(authorization: str = Header(default="")) -> JSONResponse:
    """Re-drive dead letters whose defect has since been fixed. Authenticated.

    This exists because the same operational need has now arisen twice: a defect kills a job,
    the defect is fixed and deployed, and the dead letter sits there making the queue-health
    signal red until somebody with database access clears it. A signal that stays red after
    the fix is a signal people learn to ignore.

    Publication jobs are never re-driven from here, whatever is asked for. Their dead letters
    are refusals working correctly, and a re-drive endpoint that can touch them is a
    publication path wearing an operations label.
    """
    try:
        opsauth.check(authorization)
    except opsauth.OpsAuthUnavailable as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    except opsauth.OpsAuthRefused:
        return JSONResponse({"error": "operator credential required"}, status_code=401)

    q = JobQueue(db)
    types = sorted({j.job_type for j in q.dead_letters() if j.job_type != "store.publish"})
    if not types:
        return JSONResponse({"requeued": 0, "job_types": [],
                             "note": "no dead letter is eligible to be re-driven"})
    result = q.requeue_dead(job_types=types)
    Registry(db).audit("orchestrator", "queue.requeued", detail=result)
    return JSONResponse({**result, "job_types": types,
                         "note": ("publication refusals are never re-driven: they are "
                                  "refusals working correctly")})


@app.get("/api/continuity/export")
def api_continuity_export(authorization: str = Header(default="")) -> Response:
    """Download the portable export. Authenticated, and closed when unconfigured.

    This is the one endpoint that returns database contents, so it is the one that must not
    be reachable without the operator credential. `opsauth` refuses everybody when the token
    is unset, which is the safe direction: the opposite default would serve the company to
    the internet in the window between deploying this and remembering to set the variable.
    """
    import tempfile

    from ..core import continuity

    try:
        opsauth.check(authorization)
    except opsauth.OpsAuthUnavailable as e:
        # 503, not 401: nothing the caller can present would work.
        return JSONResponse({"error": str(e)}, status_code=503)
    except opsauth.OpsAuthRefused:
        return JSONResponse({"error": "operator credential required"}, status_code=401)

    work = tempfile.mkdtemp(prefix="continuity-download-")
    result = continuity.export(db, f"{work}/brambleloop-export.jsonl")
    Registry(db).audit("orchestrator", "continuity.exported",
                       detail={"digest": result.digest, "rows": result.total_rows,
                               "bytes": result.bytes_written, "source": result.source})
    return FileResponse(
        str(result.path), media_type="application/x-ndjson",
        filename=f"brambleloop-export-{result.created_at:%Y%m%dT%H%M%SZ}.jsonl",
        headers={"X-Brambleloop-Export-Digest": result.digest,
                 "X-Brambleloop-Export-Rows": str(result.total_rows)},
    )



@app.get("/api/access")
def api_access() -> dict:
    """What this system cannot do, what would unlock it, and what it costs (#223, #224).

    Deliberately reports the unmet capability first and the request second. A page that led
    with the request would read as a sales pitch; this one reads as a status.
    """
    from ..launch import access

    report = access.unmet_report()
    report["requests"] = [r.to_dict() for r in access.pending_requests()]
    return report


@app.get("/api/mjs")
def api_mjs() -> dict:
    """The MJs mission command centre (#318).

    Leads with whether the mission can observe anything at all, because a dashboard that led
    with coverage computed from an empty table would read as a healthy mission.
    """
    from ..intel.mission import mission_report

    return mission_report(db)


@app.get("/api/seasonal")
def api_seasonal() -> dict:
    """The seasonal war room: when every certified pattern must be live, and what is at risk.

    Leads with what is late rather than with what is fine, because a dashboard is read in the
    order it is written and the at-risk rows are the only ones anybody can still act on.
    """
    from ..seasonal.leadtime import catalogue_plans

    return catalogue_plans(db)


@app.post("/api/mjs/reclassify")
def api_mjs_reclassify(dry_run: bool = False,
                       authorization: str = Header(default="")) -> JSONResponse:
    """Re-route the stored benchmark catalogue through the current pod vocabulary (#303).

    Runs on every scan too. Exposed because a vocabulary widening should not have to wait six
    hours to become visible, and because the dry run is the honest way to see what a change to
    `pods.PODS` would actually do before it does it.

    Authenticated because it writes, even though it reads only stored titles and reaches no
    network: an endpoint that rewrites the benchmark's classification is not a public read.
    """
    try:
        opsauth.check(authorization)
    except opsauth.OpsAuthUnavailable as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    except opsauth.OpsAuthRefused:
        return JSONResponse({"error": "operator credential required"}, status_code=401)

    from ..intel import observe

    return JSONResponse(observe.reclassify(db, dry_run=dry_run))


@app.get("/api/search/arena-language")
def api_arena_language() -> dict:
    """The words a shopper in each proven arena actually sees (#293).

    Observed by construction: every term is read from a recorded benchmark listing, so
    nothing here can be labelled assumed. It is not a search-volume claim, which the payload
    says on itself rather than in a footnote.
    """
    from ..commerce import intent
    from ..creative import prospecting

    pods = []
    seen = set()
    for arena in prospecting.arenas(db):
        if arena.pod in seen:
            continue
        seen.add(arena.pod)
        pods.append(intent.arena_language(db, pod=arena.pod))
    return {"arenas": pods,
            "note": ("One entry per proven-and-unserved department. A department with too "
                     "few observed listings reports that it cannot be measured rather than "
                     "a frequency over four titles, which is one seller's habit.")}


@app.get("/api/creative/prospects")
def api_creative_prospects() -> dict:
    """Where discovery could go, what it has found, and what the engine cannot build (#104).

    Read-only and spends nothing. The expedition itself is a weekly cadence, for the same
    reason the blinded run is: a request that spends the model budget should not be one URL
    away.
    """
    from ..creative import prospecting, standard
    from ..creative.audit import catalogue_concepts
    from ..gateway import routing

    catalogue = catalogue_concepts() + prospecting.discovered(db)
    found = prospecting.arenas(db)
    plans = []
    for arena in found[:6]:
        plan = prospecting.slots(arena, catalogue=catalogue)
        plans.append({k: v for k, v in plan.items() if k != "slot_objects"})

    state = routing.budget(db)
    per_field = routing.estimate_cad(prospecting.GENERATION_TASK)
    return {
        "arenas": [a.to_dict() for a in found],
        "plans": plans,
        "engine_gaps": prospecting.engine_gaps(),
        "commercially_informed": standard.commercially_informed(
            catalogue, [{"event": a.event, "department": a.pod} for a in found]),
        "saturated_forms": prospecting.saturated_forms(catalogue),
        "history": prospecting.history(db),
        "estimated_cad_per_field": per_field,
        "affordable_fields": int(state.remaining_cad // per_field) if per_field else 0,
        "budget": state.to_dict(),
        "runs_on": "the weekly `arena_expedition` cadence, rotating through the proven gaps",
    }


@app.get("/api/creative/blinded")
def api_creative_blinded() -> dict:
    """What a blinded comparison against the human catalogue could currently measure (#94).

    A GET reports readiness and cost, and never spends: the run itself is a POST, because a
    read-only endpoint that quietly bills the month's model budget is a trap.
    """
    from ..creative import blinded
    from ..gateway import routing

    listings = blinded.benchmark_cards(db)
    state = routing.budget(db)
    per_pair = routing.estimate_cad(blinded.TASK)
    return {
        "benchmark_listings": len(listings),
        "readability": blinded.readability(listings) if listings else {},
        "min_pairs": blinded.MIN_PAIRS,
        "position_bias_ceiling": blinded.MAX_POSITION_SHARE,
        "estimated_cad_per_pair": per_pair,
        "affordable_pairs": int(state.remaining_cad // per_pair) if per_pair else 0,
        "budget": state.to_dict(),
        "last_run": blinded.last_run(db),
        "runs_on": ("the monthly `blinded_benchmark` cadence. There is no endpoint that "
                    "runs it, because a request that spends the model budget should not be "
                    "one URL away"),
        "compared_on": list(blinded.CARD_FIELDS),
        "not_compared_on": ["the photograph, which is most of why a listing sells and needs "
                            "the browser/vision capability"],
    }


@app.get("/api/mjs/coverage")
def api_mjs_coverage() -> dict:
    """What the living market map cannot see, named rather than counted (#207, #303).

    The map reports an unclassified count. This reports the listings behind it, because a
    keyword vocabulary may only grow from observed titles -- widening it from imagination
    produces pods that match nothing while looking broader.
    """
    from ..intel import market_map

    return market_map.gaps(db)


@app.get("/api/teardown")
def api_teardown() -> dict:
    """The teardown laboratory: what has been purchased, scored, and made into a standard.

    Reports the composite standard's own weakness first — whether it is still drawn from a
    single seller — because a standard that is one shop's product with extra steps is worse
    than no standard, and it is the failure that arrives quietly.
    """
    from ..intel import capacity as mjs_capacity
    from ..intel import market_map, memory as mjs_memory
    from ..intel import response as mjs_response
    from ..teardown import audits, pipeline, scorecard
    from ..teardown.library import ANALYST_ROLES, FORBIDDEN_ROLES

    composite = scorecard.composite_standard(db)
    return {
        "composite_standard": composite,
        "improvement_queue": scorecard.improvement_queue(db),
        # The nine per-dimension schedules (#152-#160): which have been run, what standard
        # they imply, and how far a finding actually travels before it becomes a change.
        "audit_coverage": audits.coverage(db),
        "publishing_standard": audits.publishing_requirements(db),
        "improvement_pipeline": pipeline.status(db),
        "critical_dimensions": list(pipeline.CRITICAL_DIMENSIONS),
        # #306-#309: what happens when the benchmark proves an arena. Reported here because
        # the teardown and the benchmark mission draw the same boundary in two places.
        "mjs_response": mjs_response.describe(),
        # #302, #303, #316: the mission's reserved capacity, its living catalogue map and
        # what the pods have actually learned as opposed to seen repeatedly.
        "mjs_capacity": mjs_capacity.describe(),
        "mjs_market_map": market_map.build(db),
        "mjs_memory": mjs_memory.report(db),
        "dimensions": list(scorecard.DIMENSIONS),
        "scale": scorecard.SCALE,
        "library": {
            "note": ("Purchased competitor files are held outside this repository and are "
                     "never served, quoted or reachable by pattern generation."),
            "readable_by": sorted(ANALYST_ROLES),
            "refused_for": FORBIDDEN_ROLES,
        },
    }


@app.get("/api/invention")
def api_invention() -> dict:
    """The brief machinery, and the bar it has to clear today.

    The creativity defect this addresses is measured rather than asserted: every product in
    the catalogue compiles to one component shape in two stitches. A validator cannot fix
    that, because given a season and a category the highest-probability output is the
    commodity. The brief has to carry the novelty.
    """
    from ..creative import audit, discovery, invention, standard, universe

    return {
        "invention_matrix": invention.matrix("christmas"),
        "dimensions": invention.DIMENSIONS,
        "transformations": invention.TRANSFORMATIONS,
        "wow_mechanisms": invention.WOW_MECHANISMS,
        "motif_grammar": {k: list(v) for k, v in invention.MOTIF_GRAMMAR.items()},
        "saturated_motifs": {k: sorted(v) for k, v in invention.SATURATED.items()},
        "generic_forms": sorted(invention.GENERIC_FORMS),
        "taste_rejections": standard.TASTE_REJECTIONS,
        "absolute_floor": standard.ABSOLUTE_FLOOR,
        "autopsies": standard.autopsy_patterns(db),
        "measured_defect": audit.generator_degrees_of_freedom(),
        # The cells a brief is generated against (#105, #113), and the seasons between the
        # holidays, which is where a shop that only sells in December is closed.
        "universe": {occasion: list(departments)
                     for occasion, departments in universe.UNIVERSE.items()},
        "contexts": universe.CONTEXTS,
        "skill_levels": universe.SKILL_LEVELS,
        "diversity_axes": list(universe.DIVERSITY_AXES),
        "between_holidays": {s: universe.between_holidays(s)["programs"]
                             for s in universe.FOUR_SEASON_PROGRAMS},
        "non_holiday_occasions": universe.NON_HOLIDAY_OCCASIONS,
        "unmet_angles": discovery.ANGLE_KINDS,
        "complaint_kinds": discovery.COMPLAINT_KINDS,
        "transferable_mechanisms": discovery.TRANSFERABLE,
        "north_star": standard.north_star({}),
    }


@app.get("/api/runrate")
def api_runrate() -> dict:
    """CA$3,000 a month as arithmetic, and which single term is binding.

    Contribution per visitor rather than conversion rate, because optimising conversion
    optimises a ratio whose denominator you are also buying.
    """
    from ..finance import unit_cost
    from ..scale import runrate

    observed = runrate.Observed()
    return {
        "decomposition": runrate.decompose(3000.0, observed=observed),
        "constraint": runrate.constraint(observed, target_cad=3000.0),
        "scale_rules": [{"key": k, "condition": c, "action": a}
                        for k, c, a in runrate.SCALE_RULES],
        "funnel_terms": dict(runrate.TERMS),
        "unit_cost": unit_cost.unit_costs(db),
    }


@app.get("/api/discipline")
def api_discipline() -> dict:
    """The reserves, the stop list and the staged ladder: what stops a system flattering itself.

    Grouped because they are one discipline seen three ways. A system that measures its own
    throughput optimises throughput; one with cash finds a use for it; one that reviews itself
    weekly only ever adds work.
    """
    from ..finance import reinvestment
    from ..improve import velocity
    from ..scale import confidence

    return {
        "confidence_bands": confidence.bands(db),
        "reinvestment_policy": reinvestment.describe(),
        "velocity": velocity.from_db(db),
        "stop_categories": velocity.STOP_CATEGORIES,
        "note": ("Releases per week is never reported alone (#52), a review that stops "
                 "nothing has to say why (#53), revenue fills four reserves before any of it "
                 "is an envelope (#49), and the architecture stage is earned without moving "
                 "either confidence band (#55)."),
    }


@app.get("/api/commercial")
def api_commercial() -> dict:
    """What this company has learned about price and promotion, which today is nothing.

    Reported as unmeasured rather than as zeroes, because an elasticity of zero is not the
    absence of a claim — it is the claim that price does not matter.
    """
    from ..commerce import elasticity

    return {
        "price_memory": elasticity.memory(db),
        "thresholds": {
            "min_orders_per_point": elasticity.MIN_ORDERS_PER_POINT,
            "min_visits_per_point": elasticity.MIN_VISITS_PER_POINT,
            "min_price_separation": elasticity.MIN_PRICE_SEPARATION,
        },
        "confounders_refused": ["season", "traffic_source", "category"],
        "note": ("A comparison across a confounder is refused rather than flagged. A warning "
                 "attached to a number is read by the person who wrote it and by nobody "
                 "afterwards, and the number travels on alone (#46, #48)."),
    }


@app.get("/api/policy")
def api_policy() -> dict:
    """How old this company's reading of Etsy's rules is, and what that blocks.

    The freshness answer comes first because "never checked" and "unchanged" produce the same
    dashboard on every other page, and they are opposite states.
    """
    from ..commerce import terms as customer_terms
    from ..gates.platform_policy import describe, freshness, policy_stamp

    return {
        "freshness": freshness(db),
        "certificate_stamp": policy_stamp(db),
        "rules": describe(),
        "customer_terms": customer_terms.BRAMBLELOOP_TERMS.to_dict(),
        "terms_surfaces": {
            surface: customer_terms.render(customer_terms.BRAMBLELOOP_TERMS, surface)
            for surface in customer_terms.SURFACES
        },
    }


@app.get("/api/culture")
def api_culture() -> dict:
    """The culture engine: what it remembers, what it owns, and what it may not use.

    The rights routing is reported first and unconditionally, because it is the part that
    stops a culture radar becoming a legal problem, and it is invisible in every other view.
    """
    from ..culture import feeds, radar, rapid, rights, score, translate

    return {
        "rights": rights.describe(),
        "feed": feeds.state(db),
        "findings": radar.findings(db),
        "radar": radar.sweep(db, feeds=[feeds.SOURCE_KEY] if feeds.usable(db) else None),
        "owned_territories": translate.owned_territories(),
        "primitives": dict(translate.PRIMITIVES),
        "opportunity_components": score.MEANING,
        "gates": list(score.GATES),
        "rapid_response_cell": rapid.describe(),
        "note": ("Cultural observation is demand evidence, never source material. A signal "
                 "whose rights are unclear becomes an original concept rather than a dead "
                 "opportunity, which is where the territories this company owns come from."),
    }


@app.get("/api/creative-reference")
def api_creative_reference(pod: str = "") -> dict:
    """What a strong competitor photograph teaches, and what it may never hand over.

    #116 and #278 read as one dangerous sentence and are two safe ones. Construction is
    learnable: a crew neckline is a fact like a gauge or a join, nobody owns it, and a
    company that could not observe one could not make a cardigan. Depiction is not: the
    field that describes a motif is the field that reproduces it, so `motif_density` is a
    quantity -- sparse, scattered, allover -- and there is no slot for what the motif is.

    A brief needs two listings. One listing's primitives are one seller's habits, and a
    brief written from them is an instruction to make that product again, which is #227's
    aggregation failure arriving through the design system rather than through a decision.
    """
    from ..creative import reference

    body = {"rules": reference.state()}
    if pod:
        body["brief"] = reference.brief(db, pod)
    return body


@app.get("/api/visual-inspection")
def api_visual_inspection() -> dict:
    """The checks this company makes on its own pictures, and what makes them (#61, #79).

    `visual/gallery.py` has always known what to ask and has always reported unmade checks
    as unjudged rather than as passes. What was missing was a model that could look, and it
    arrived on 2026-09-19 filed under a gate named after a cloud browser.

    The model is never shown the caption. "Does this image match this description" has an
    obvious polite answer, and a grader shown the expected result grades toward it -- so it
    is asked what it sees, and the comparison happens in deterministic code.
    """
    from ..visual import inspect

    return {
        "realism_checks": list(inspect.REALISM_CHECKS),
        "description_fields": list(inspect.DESCRIPTION_FIELDS),
        "verdicts": ["blocked", "unjudged", "clear"],
        "why_three": ("a gate with two outcomes has to call an unmade check something, and "
                      "whichever it calls it is wrong half the time"),
        "method": inspect.compare({}, {})["method"],
        "generator_does_not_grade_itself": (
            "the description is produced from the rendered file rather than from the plan "
            "that produced it, so a render that silently failed cannot describe what it "
            "intended"),
    }


@app.get("/api/gallery-intelligence")
def api_gallery_intelligence() -> dict:
    """What the judged gallery images have actually taught, per listing and per pod.

    The half of the benchmark mission that was parked behind a browser nobody had bought,
    and needed a model looking at URLs the sanctioned Etsy endpoint has been returning all
    along (#209, #304, #303, #210, #211).

    Two claims are kept apart here deliberately. "Vision is available" is about a capability
    and is true the moment one probe succeeds; "the catalogue has been looked at" is about
    438 listings and a backlog that drains ten images every four hours. A dashboard that
    reports the first is reporting the easy one.

    Nothing in the derived columns can carry a depicted subject: they are assembled from a
    closed observation vocabulary that has nowhere to put a motif, and nothing here reads a
    listing title.
    """
    from ..intel import vision

    return {
        "coverage": vision.coverage(db),
        "by_pod": vision.by_pod(db),
        "derived_columns": {"silhouette": list(vision.SILHOUETTE_FROM),
                            "merchandising_mechanism": list(vision.MECHANISM_FROM)},
        "minimum_images_for_a_column": vision.MIN_IMAGES_FOR_ATTRIBUTES,
        "why_a_minimum": ("a silhouette read from one frame is a fact about the hero shot "
                          "presented as a fact about the product"),
    }


@app.get("/api/capabilities/probes")
def api_capability_probes() -> dict:
    """What each capability has actually proven, apart from what is configured.

    Three of the build executor's gates used to read an environment variable, and the
    largest of them -- a browser worker URL -- stood in front of twenty-eight requirements.
    Set, misconfigured, unreachable and answered-with-a-403 are four states and one string.
    So each is a recorded successful use now, and this is where the evidence is readable.

    `rendered_pages` is for pages with no sanctioned endpoint: Marketplace Insights, search
    results, platform policy. Gallery images are deliberately not in that list -- their URLs
    arrive from the Etsy API and the model looks at them directly, which is why splitting
    that gate released ten requirements that had been waiting on infrastructure they did not
    need.
    """
    from ..culture import feeds
    from ..gateway import anthropic as gw
    from ..intel import browser

    return {
        "rendered_pages": browser.state(db),
        "image_vision": {"last_probe": gw.last_vision_probe(db),
                         "usable": gw.vision_usable(db),
                         "what_it_is": ("a model looking at the gallery URLs the sanctioned "
                                        "Etsy endpoint already returns. No browser, and no "
                                        "spend beyond the monthly model ceiling"),
                         "image_tokens_estimate": gw.IMAGE_TOKENS_ESTIMATE},
        "culture_feed": feeds.state(db),
        "why_probes": ("a credential is not a capability, and neither is a URL. Every gate "
                       "here reads a row written by something that worked"),
    }


@app.get("/api/benchmark-selection")
def api_benchmark_selection(target: int = 10, budget_cad: float = 0.0) -> dict:
    """Which benchmark patterns to buy, and the distinct unknown each one answers (#165/#166).

    Not the ten most popular. Popularity is a fact about a listing and this purchase is about
    the set: in one shop's catalogue the top ten share a department, a price band and a
    deliverable format, so nine of them answer a question the first already answered. The
    objective here is coverage of the facets a customer-experience teardown can differ along,
    picked greedily so a person can check the reasoning before spending real money.

    It stops short of the target when no remaining listing adds anything new, because ten was
    always an approximation of "enough" and a purchase made to round out a list is a purchase
    that teaches nothing.

    This buys nothing. It produces a list, its reasons and its expected cost.
    """
    from ..intel import benchmarks
    from ..intel.purchase_selection import SelectionRefused, select

    try:
        return select(db, benchmarks.MJS_KEY, target=max(1, min(target, 40)),
                      budget_cad=budget_cad if budget_cad > 0 else None)
    except SelectionRefused as exc:
        return {"selected": [], "refused": str(exc)}


@app.get("/api/image-generation")
def api_image_generation() -> dict:
    """The canonical model's generator: the decision, the candidates and the arithmetic.

    Image generation is not image understanding, and the substitution is refused in code
    rather than discouraged in a note -- the model that can look at a photograph cannot make
    one, and a system that swapped them would report the model pack as progressing while
    producing nothing.

    An identity lock (#200) is reference conditioning rather than a better prompt: a prompt
    describing a face produces a different face every time, within a family. So a provider
    that cannot take reference images cannot satisfy the requirement whatever its output
    quality, which is why one candidate here is ruled out on the requirement rather than on
    taste.
    """
    from ..gateway import images

    return images.state(db)


@app.get("/api/spend-policy")
def api_spend_policy() -> dict:
    """The governing model and creative spend policy, and where this month stands.

    QUALITY FIRST. COST SECOND. WASTE NEVER. The three clauses are ordered and the order is
    the policy: quality decides, cost is the tie-breaker rather than the argument, and waste
    is refused at any budget because waste is not a saving that was declined -- it is
    spending with nothing on the other side of it.

    The ceiling is an authority, not a target. What changed on 2026-09-20 is which argument
    may win, not how much this company intends to spend.
    """
    from ..finance import spend_policy

    return spend_policy.state(db)


@app.get("/api/spend-report")
def api_spend_report() -> dict:
    """What the money bought, by every dimension the owner asked to see it by.

    Provider, model, agent, department, product and purpose, with the pre-call reservation
    kept beside the bill. An estimate nobody compares against the invoice can drift by a
    factor of three, and did -- every ceiling check in that session was computed against the
    wrong number and none of them failed.

    Rows with no recorded dimension are counted under `unattributed` with their dollars
    intact, because dropping them would show a tidier number that does not match the bill,
    and the gap would be exactly the spending nobody could account for.
    """
    from ..finance import spend_policy, spend_report

    report = spend_report.what_it_bought(db)
    return {**report,
            "headroom": spend_policy.headroom(report["spent_cad"]),
            "escalation": spend_policy.escalation(db)}


@app.get("/api/teardown/readiness")
def api_teardown_readiness() -> dict:
    """Whether the Teardown Laboratory can receive CA$292 of purchased evidence.

    The owner's instruction was to verify this before asking them to buy. Checked from
    evidence -- an importable reader, a caller that exists, rows in a table -- rather than
    from a list somebody maintains, because a readiness report kept by hand says ready.
    """
    from ..teardown import readiness

    return readiness.check(db)


@app.get("/api/model-tournament/image/{sha256}")
def api_model_tournament_image(sha256: str) -> Response:
    """Serve one tournament render by its content digest.

    Unauthenticated on purpose, and narrowly: these are generated portraits of fictional
    people made for a brand decision, not customer data, not listing assets and not secrets.
    The route is digest-addressed, so it cannot be browsed -- you need the hash, and the
    hash comes from the tournament package.

    It exists because a finalist package that pointed at a container's `/tmp` was a package
    nobody could look at, and the owner's instruction was to present the finalists.
    """
    from ..core.artifacts import ArtifactMissing, ArtifactStore

    if not sha256.isalnum() or len(sha256) != 64:
        return JSONResponse({"error": "not a digest"}, status_code=400)
    try:
        # `db` so an image that was kept deliberately comes back after a restart. A
        # tournament field is evidence and re-rendering it is expected; the canonical
        # model's reference pack is not, and it was 404 within the hour of a redeploy
        # while the owner was being asked to approve it.
        payload = ArtifactStore().get(sha256, db=db)
    except ArtifactMissing as exc:
        # The hash is durable and the bytes are not, which the store says in its own words.
        return JSONResponse({"error": str(exc)}, status_code=404)
    return Response(content=payload, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/model-tournament")
def api_model_tournament() -> dict:
    """The canonical-model field, the finalists and their measured identity (#198, #199).

    Names no winner. Selection is a consequential brand decision and stays the owner's: a
    candidate that became canonical by topping a table is an identity nobody chose.
    """
    from ..runtime.release import _tournament_on_file
    from ..visual import brief, tournament

    package = _tournament_on_file(db)
    return {
        "brief": brief.state(),
        "plan": tournament.plan(db),
        "run": package,
        "state": ("awaiting owner selection" if package else
                  "not yet run for this brief"),
    }


@app.get("/api/funding")
def api_funding() -> dict:
    """Three facts that must never be merged: the internal budget, the provider accounts,
    and whether a call actually works.

    On the day this was written each was right about something different: CA$55 of the
    monthly ceiling free, US$10 of credit reported added, and every call refused.
    """
    from ..ops import provider_accounts

    return provider_accounts.reconcile(db)


@app.get("/api/model-pack")
def api_model_pack() -> dict:
    """The canonical reference pack built from the owner's candidate, and its measurements.

    Images are served by the existing digest route, so this is a package that can actually
    be looked at rather than a list of paths into a container's `/tmp`.
    """
    from ..runtime.release import _candidate_fingerprint, _pack_attempts, _pack_on_file
    from ..visual import brief, reference_pack

    package = _pack_on_file(db)
    attempts = _pack_attempts(db)
    return {
        "candidate": {
            "given_at": brief.CANDIDATE_GIVEN_AT,
            "is": brief.CANDIDATE_IS_OWNER_SUPPLIED,
            "rejected_finalists": brief.REJECTED_FINALISTS_NOTE,
        },
        "plan": reference_pack.plan(db),
        "pack": package,
        "candidate_fingerprint": _candidate_fingerprint(),
        "attempts": attempts,
        "state": ("awaiting owner approval" if package else
                  "attempted and unfinished" if attempts else
                  "not yet built for this candidate"),
        "frozen": False,
    }


@app.get("/api/model-asset")
def api_model_asset(slug: str = "") -> dict:
    """The most recent model-bearing listing frame, and what every floor said about it.

    Read-only and free. The record is what the job produced, not a fresh opinion about the
    same picture: five independent floors, the reference it was conditioned on, and the
    identity comparison made by a model that never saw the prompt.
    """
    from ..publish import model_photography
    from ..visual import model_registry, reliability

    record = model_photography.last_asset(db, slug=slug)
    pack = model_registry.canonical_pack(db)
    if record is None:
        return {"asset": None, "canonical_version": pack.version if pack else None,
                "why": ("no model-bearing frame has been made yet. "
                        "`assets.model_photography` runs daily and makes one per release "
                        "for the forms a buyer cannot judge without a body")}
    # The listing asset is a sequence, so the per-frame readings are what diagnose a
    # blocked floor: "product truth unverifiable" says nothing about which frame could not
    # be read, and a combined verdict with no frames behind it is a summary of evidence
    # nobody can see.
    frames = record.get("frames") or [record]
    return {
        "asset": {k: record.get(k) for k in (
            "slug", "version", "form", "method_version", "provider", "image",
            "conditioned_on", "shots", "floors", "floor_sources",
            "usable_as_listing_asset", "why", "why_two_frames",
            "disclosed_as_illustration", "disclosure", "spent_cad")},
        "frames": [{k: f.get(k) for k in (
            "shot", "role", "answers_for", "readable_at_grid", "floors", "image",
            "identity", "motif", "photographic_realism", "styling", "asset_truth",
            "inspection", "why")} for f in frames],
        "identity": frames[0].get("identity"),
        "motif": next((f.get("motif") for f in frames if f.get("motif")), None),
        "photographic_realism": frames[0].get("photographic_realism"),
        "canonical_version": pack.version if pack else None,
        "floors_never_average": record.get("floors_never_average"),
        # One passing sequence demonstrates possibility. This is the rate, the cost and
        # the diagnosis, judged against a standard written down before the sample existed.
        "reliability": reliability.measure(db),
    }


@app.get("/api/render-reliability")
def api_render_reliability() -> dict:
    """Whether the render pipeline is a capability or a run of luck, and what it costs.

    Read-only and free: it measures sequences already filed and renders nothing. The
    standard it judges against was written on `standard_set_at`, before any of these
    attempts were drawn, so the number cannot become the standard after the fact.
    """
    from ..visual import reliability

    return {
        "reliability": reliability.measure(db),
        "standard": {
            "correctness": ("no asset is ever marked usable with a floor that did not "
                            "say pass. Absolute -- one breach blocks launch however good "
                            "the rate, because that is the failure that reaches a buyer"),
            "economics": (f"every attempted gallery reaches a usable state inside "
                          f"{reliability.MAX_ATTEMPTS_PER_GALLERY} attempts at no more "
                          f"than CA${reliability.MAX_CAD_PER_USABLE_GALLERY} per usable "
                          f"gallery"),
            "set_at": reliability.STANDARD_SET_AT,
            "min_galleries_for_a_rate": reliability.MIN_GALLERIES_FOR_A_RATE,
            "min_asks_for_a_classification": reliability.MIN_ASKS_FOR_A_CLASSIFICATION,
        },
    }


@app.get("/api/reference-realism")
def api_reference_realism() -> dict:
    """Whether the frozen identity pack could ever produce a believable photograph.

    Three model frames failed `skin_looks_real` and `processing_is_restrained` against
    direction that names airbrushed skin explicitly. Either the generator will not do
    unretouched skin, or the reference it is copying is already airbrushed -- opposite
    fixes, and a render cannot tell them apart. This judges the reference by the same
    standard its renders are held to.

    Read-only: it judges images already on file and generates nothing. It does make vision
    calls, so it costs a fraction of a cent and is not run on a cadence.
    """
    from ..visual import photoreal

    return {"reference_realism": photoreal.reference_realism(db),
            "checks": dict(photoreal.CHECKS),
            "inherited_checks": list(photoreal.INHERITED)}


@app.get("/api/asset-coverage")
def api_asset_coverage() -> dict:
    """How much of the certified catalogue can actually be listed.

    The count nobody was keeping. The photography cadence reported success every day while
    photographing one representative product for ever, so "the job ran" and "the catalogue
    has pictures" had drifted a long way apart with nothing measuring the gap.
    """
    from ..runtime.release import owned_asset_coverage

    return {"owned": owned_asset_coverage(db)}


@app.get("/api/carried-portrait")
def api_carried_portrait() -> dict:
    """Whether the face every reference pack carries forward can pass what it passes on.

    `reference_pack.build` does not re-render the portrait -- it carries the approved file
    -- so this one answer decides whether any pack this code can build is freezable at all.
    Asked once per set of bytes and filed, so repeat calls are free and a replaced
    portrait is a new question asked automatically.
    """
    from ..visual import photoreal

    return {"carried_portrait": photoreal.carried_portrait(db),
            "inherited_checks": list(photoreal.INHERITED)}


@app.get("/api/photoreal-calibration")
def api_photoreal_calibration() -> dict:
    """Whether the photographic-realism judge can pass a photograph nobody generated.

    A standard nothing can clear is the same defect as a floor nothing can fail, and this
    is the question that tells the two apart: a render this judge blocks is only a render
    that needs changing if the judge would have passed a real camera's output.
    """
    from ..runtime.release import photoreal_calibration
    from ..visual import photoreal

    result = photoreal_calibration(db)
    return {
        "calibration": result,
        "checks_version": photoreal.CHECKS_VERSION,
        "checks": dict(photoreal.CHECKS),
        "why": ("asked once per version of these checks, against a real listing photograph "
                "from the observed benchmark. Used as a control and nothing else: not "
                "copied, not re-hosted, not imitated, and what it depicts is never "
                "described"),
        "state": ("not yet asked" if result is None else
                  "this judge failed a real photograph" if result.get("failed") else
                  "a real photograph failed nothing; some checks it could not show"
                  if result.get("unjudged") else
                  "a real photograph cleared every check"),
    }


@app.post("/api/model-identity/freeze")
def api_model_identity_freeze(authorization: str = Header(default="")) -> JSONResponse:
    """Freeze the approved reference pack as the canonical identity. Authenticated (#200).

    The owner approved the revised pack on 2026-09-22. This is the only path from measured
    to canonical, it refuses a pack with an unstated required dimension whatever the
    approval says, and it refuses a second canonical outright -- replacing her is a
    redesign and a separate decision.
    """
    try:
        opsauth.check(authorization)
    except opsauth.OpsAuthUnavailable as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    except opsauth.OpsAuthRefused:
        return JSONResponse({"error": "operator credential required"}, status_code=401)

    from ..visual import freeze as freeze_mod

    try:
        record = freeze_mod.freeze(db, owner_approved=True)
    except freeze_mod.FreezeRefused as exc:
        return JSONResponse({"frozen": False, "refused": str(exc)}, status_code=409)
    return JSONResponse(record, status_code=200)


@app.get("/api/model-identity/enforcement")
def api_model_identity_enforcement() -> dict:
    """The seven properties the owner asked to be proved after persistence (#200, #201).

    Read-only and free: every check is deterministic given the persisted pack, so this can
    be asked as often as anybody likes. It is run against the pack read back out of the
    database rather than one held in memory, because the question is whether the identity
    that survived persistence is the one being enforced.
    """
    from ..visual import freeze as freeze_mod

    return freeze_mod.enforcement_proof(db)


@app.get("/api/model-identity/freezable")
def api_model_identity_freezable() -> dict:
    """Which packs on file could be frozen, and why the others could not."""
    from ..visual import freeze as freeze_mod

    rows = freeze_mod.candidates_on_file(db)
    chosen = freeze_mod.newest_freezable(db)
    return {
        "packs": [{k: v for k, v in r.items() if k != "_package"} for r in rows],
        "would_freeze": chosen and {"pack_version": chosen["pack_version"],
                                    "at": chosen["at"],
                                    "skipped_newer": chosen["skipped_newer"]},
        "why_not_simply_the_newest": (
            "a newer build that could not state a required dimension is not a newer "
            "identity, it is an unusable one: freezing it would write a floor with a hole "
            "in it, and a dimension with no stated value can never drift again"),
    }


@app.get("/api/model-identity")
def api_model_identity() -> dict:
    """The canonical model: what is selected, what is only a candidate, and what blocks.

    Nothing is selected, and nothing will select itself. The design has always said so; what
    was missing until 2026-09-21 was anything that read it -- `visual/identity.py` had no
    callers anywhere in the codebase, so a correct gate sat unconsulted while the first
    model-bearing listing would have shipped past it.
    """
    from ..visual import model_registry

    return model_registry.state(db)


@app.get("/api/image-benchmark")
def api_image_benchmark() -> dict:
    """How the generator gets chosen, and why nothing is chosen yet.

    The owner's instruction is that quality decides and a modestly dearer model that
    materially outperforms is worth paying for, so this is a measurement rather than a
    comparison of price lists. Six trials that this catalogue genuinely needs rendered --
    stitch truth, hero comprehension, thumbnail strength, premium lifestyle, the canonical
    model brief and an anti-drift repeat against a reference -- five samples each, on every
    model that can hold an identity at all.

    The judge is the vision capability, blind to which model rendered which image, scoring a
    rubric whose every line carries the requirement it comes from. A judge told the brand
    grades the brand.

    With no results it names nobody. Falling back to the cheapest candidate is the decision
    the owner explicitly ruled out, and it is what a resultless benchmark becomes if the
    refusal is not written down.
    """
    from ..gateway import image_bench

    return image_bench.state(db)


@app.get("/api/models")
def api_models() -> dict:
    """Model routing, what it costs, and how much of the approved month is left.

    The ceiling is checked before every call rather than reported after, so this page is a
    status rather than a reconciliation.
    """
    from ..gateway import routing
    from ..intel import etsy_public

    return {
        "model_routing": routing.plan(db),
        "benchmark_read_credential": etsy_public.capability_report(),
    }


@app.get("/api/scale")
def api_scale() -> dict:
    """CA$5,000 a month: the paths to it, and how likely it currently is.

    The probability is computed from rows in this database and cannot be set, weighted or
    argued upward. A sophisticated architecture with no customers reports near zero, which is
    the answer #230 exists to insist on.
    """
    from ..scale import confidence, target

    return {
        "probability": confidence.probability(db),
        "scenarios": target.matrix(),
    }


@app.post("/api/seasonal/recompute")
def api_seasonal_recompute(as_of: str = "") -> dict:
    """Recompute the seasonal war room now, rather than at the next daily cadence.

    Same argument as `/api/launch-readiness` and `/api/chain-rebuild`: a daily cadence is
    right for an unattended system and too slow the moment a catalogue change alters what the
    launch dates should say. `as_of` asks what the room looked like, or will look like, on a
    given day — which is how a deadline is checked against a plan rather than against today.

    GREEN: it enqueues work already on a schedule, computes dates, spends nothing and
    publishes nothing.
    """
    key = f"seasonal.sentinel:{utcnow():%Y%m%dT%H%M}"
    inputs = {"as_of": as_of} if as_of else {}
    try:
        job = JobQueue(db).enqueue("orchestrator", "seasonal.sentinel", inputs,
                                   idempotency_key=key)
    except DuplicateJob:
        return {"enqueued": False,
                "reason": "a seasonal assessment was already queued this minute"}
    return {"enqueued": True, "job_id": job.id}


@app.post("/api/mjs/scan")
def api_mjs_scan() -> dict:
    """Scan the benchmark catalogue now rather than at the next six-hourly window.

    GREEN: reads public marketplace data, writes observations, queues internal work. It
    publishes nothing, spends nothing and contacts nobody. Without a credential it records
    why it could not run instead of recording an empty catalogue.
    """
    key = f"mjs.scan:{utcnow():%Y%m%dT%H%M}"
    try:
        job = JobQueue(db).enqueue("market_radar", "mjs.scan", {}, idempotency_key=key)
    except DuplicateJob:
        return {"enqueued": False, "reason": "a benchmark scan was already queued this minute"}
    return {"enqueued": True, "job_id": job.id,
            "note": "the result appears at GET /api/mjs once the worker runs it"}


@app.get("/api/creative")
def api_creative() -> dict:
    """The creative gate, pointed at our own catalogue.

    The owner judged the generated catalogue materially below standard. This reports the
    measurement rather than the agreement: which critic fires, on how many products, and what
    in the generator produces it.
    """
    from ..creative.audit import audit_catalogue

    return audit_catalogue()


@app.get("/api/mjs/vision")
def api_mjs_vision() -> dict:
    """The image-analysis backlog: what is waiting, what it would cost, whether it can run."""
    from ..intel.benchmarks import MJS_KEY
    from ..intel.cadence import next_interval
    from ..intel.vision import plan

    return {"backlog": plan(db, MJS_KEY),
            "scan_cadence": next_interval(db, MJS_KEY).to_dict()}


@app.get("/api/improve")
def api_improve() -> dict:
    """The Improvement Department: what moved, what regressed, and what it may never do."""
    from ..improve.bus import compounding
    from ..improve.cells import CELLS, capability_history, retrospective
    from ..improve.governance import describe

    return {
        "retrospective": retrospective(db),
        "compounding": compounding(db),
        "cells": [{"cell": c.key, "department": c.department, "metric": c.metric,
                   "higher_is_better": c.higher_is_better, "measure": c.measure,
                   "history": capability_history(db, c.key, limit=20)} for c in CELLS],
        "governance": describe(),
    }


@app.get("/api/calendar")
def api_calendar() -> dict:
    """The rolling 365-day calendar: every event, its phase, and how thin its coverage is."""
    from ..seasonal.calendar import coverage_matrix, rolling

    return {"calendar": rolling(), "coverage": coverage_matrix()}


@app.get("/api/growth")
def api_growth() -> dict:
    """The growth architecture: portfolio shape, loop evidence and this week's constraint."""
    from ..growth.loops import constraint, evidence_summary, from_db
    from ..growth.mix import report

    return {
        "portfolio": report(db),
        "loops": evidence_summary(from_db(db)),
        "constraint": constraint({}),
    }


@app.get("/api/swarm")
def api_swarm() -> dict:
    """Capacity, priority and orphaned work."""
    from ..gateway.routing import budget
    from ..swarm.orchestrate import BANDS, fan_out, next_work

    with db.session() as s:
        pending = s.scalar(select(func.count()).select_from(Job)
                           .where(Job.status == JobStatus.PENDING)) or 0
    state = budget(db)
    return {
        "capacity": fan_out(open_work=int(pending),
                            budget_remaining_cad=state.remaining_cad),
        "bands": [{"priority": p, "kind": k, "why": w} for p, k, w in BANDS],
        "next_when_idle": next_work([]),
    }


@app.get("/api/visual")
def api_visual() -> dict:
    """The canonical model system and the gallery standard."""
    from ..visual.gallery import ESCALATION, JOBS, REALISM_CHECKS
    from ..visual.identity import shot_plan, status

    return {
        "identity": status(),
        "shot_plans": {form: shot_plan(product_form=form)
                       for form in ("blanket", "fitted_garment", "stocking")},
        "frame_jobs": JOBS,
        "realism_checks": list(REALISM_CHECKS),
        "escalation_ladder": [{"action": a, "why": w} for a, w in ESCALATION],
    }

@app.get("/api/league")
def api_league() -> dict:
    """What is running, why, and what it was measured to beat.

    An incumbent with no measured outcome is named as such: it is running because it was
    first, which is the commonest reason anything runs.
    """
    from ..improve import league

    return {
        "standings": league.standings(db),
        "axes": {k: v[1] for k, v in league.AXES.items()},
        "quality_margin": league.QUALITY_MARGIN,
        "cost_tolerance": league.COST_TOLERANCE,
        "note": ("A challenger that brings its own tasks wins every time, so the task set is "
                 "shared and fixed. Cost and reliability are outcomes, not footnotes (#95)."),
    }


@app.get("/api/etsy")
def api_etsy() -> dict:
    """What this company can currently read from Etsy, and what that rests on.

    A credential is not a capability: Etsy v3 refuses the keystring alone, so this reports
    the last real read rather than whether two variables exist. It never reports the
    credential itself.
    """
    from ..intel import etsy_public

    return etsy_public.capability(db)


@app.post("/api/etsy/probe")
def api_etsy_probe() -> dict:
    """Ask Etsy now rather than waiting for the six-hourly cadence."""
    key = f"etsy.probe:{utcnow():%Y%m%dT%H%M}"
    try:
        job = JobQueue(db).enqueue("market_radar", "etsy.probe", {}, idempotency_key=key)
    except DuplicateJob:
        return {"enqueued": False, "reason": "a probe was already queued this minute"}
    return {"enqueued": True, "job_id": job.id,
            "note": "the result appears at GET /api/etsy once the worker runs it"}


@app.get("/api/model")
def api_model() -> dict:
    """Whether a model provider can actually serve a request, and what has been spent.

    A key is not a capability: this reports the last real call rather than whether a variable
    is set, and it never reports the key itself.
    """
    from ..gateway import anthropic

    return anthropic.state(db)


@app.get("/api/trust")
def api_trust() -> dict:
    """What has to be true before this shop buys traffic, and how fast it answers.

    Every rung reports passed, failed or unmeasured, and unmeasured is not passed: a rung
    nobody has looked at and a rung this shop has cleared are opposite situations.
    """
    from ..commerce import trust
    from ..support import service

    return {
        "accelerator": trust.may_scale_ads(db),
        "service_level": service.service_level(db),
        "refund_impact": service.refund_impact(db),
        "proof_floor": trust.PROOF_FLOOR,
        "targets": service.TARGETS,
    }


@app.get("/api/takeovers")
def api_takeovers() -> dict:
    """When each storefront surface turns over for each upcoming event, and what is late.

    Surfaces transition on different dates on purpose, and every takeover carries the date it
    reverts: the failure is not the Christmas banner going up late, it is the Christmas
    banner still being up in February.
    """
    from datetime import date as _date

    from ..brand import takeover
    from ..seasonal.calendar import rolling

    today = _date.today()
    # The rolling calendar already carries each event's true next date, so a takeover for
    # Christmas is never scheduled against a Christmas that has passed.
    upcoming = {e["event"]: _date.fromisoformat(e["event_date"])
                for e in rolling(today)["events"]}
    return takeover.calendar(upcoming, today=today)


@app.get("/api/funnel")
def api_funnel() -> dict:
    """The shape a selection tournament is meant to have, and the gates that make it one.

    Reported as the specification rather than as a run: no tournament has been run at this
    scale, because generating 75-100 cheap concepts needs a model this build does not have a
    key for. The machinery, its refusals and its arithmetic exist and are tested.
    """
    from ..creative import funnel

    return {
        "stages": [{"stage": s.key, "what": s.what, "floor_in": s.floor_in,
                    "target_out": list(s.target_out), "gate": s.gate}
                   for s in funnel.STAGES],
        "kill_causes": funnel.KILL_CAUSES,
        "runs": 0,
        "note": ("A stage that advances everything is a queue with a name, and a funnel fed "
                 "twelve concepts is the first ideas with a process wrapped around them. "
                 "Both are refused rather than warned about."),
    }


@app.get("/api/learning")
def api_learning() -> dict:
    """What the world outside this company said, and what nobody has looked at.

    Observations are signals, never causal evidence. A domain with no observations is named
    rather than counted as zero: zero signal and no look are the same number and opposite
    situations, and only the second is a defect in this system.
    """
    from ..intel import learning

    return {
        "radar": learning.radar(db),
        "domains": [{"domain": d.key, "what": d.what, "fresh_for_days": d.fresh_for_days,
                     "why": d.why} for d in learning.DOMAINS],
        "note": ("Nothing fetches these yet. The spine, the freshness model and the "
                 "signal/evidence boundary exist and are tested; retrieval is not "
                 "connected, and the radar says so by reporting every domain unobserved."),
    }


@app.get("/api/search/intent")
def api_search_intent(object: str = "stocking", season_event: str = "christmas",
                      recipient_or_use: str = "teacher gift",
                      technique: str = "", aesthetic: str = "",
                      skill_feature: str = "") -> dict:
    """The six-facet buyer-language map for one product, assumed and observed kept apart.

    A first listing built on assumed language is a reasonable thing to publish. It is not
    research, and blending the two loses the distinction by the time anybody acts on it.
    """
    from ..commerce import intent

    supplied = {"object": object, "season_event": season_event,
                "recipient_or_use": recipient_or_use, "technique": technique,
                "aesthetic": aesthetic, "skill_feature": skill_feature}
    try:
        facet_map = intent.map_product(**{k: v for k, v in supplied.items() if v})
    except intent.IntentRefused as exc:
        return {"error": str(exc), "facets": [f.key for f in intent.FACETS]}
    return intent.strategy(db, facet_map=facet_map)


@app.post("/api/model/probe")
def api_model_probe() -> dict:
    """Ask the provider now rather than waiting for the six-hourly cadence.

    Useful exactly once per change in the account's state -- credit arriving, a key rotating
    -- which is why it is idempotent per minute rather than per call. The ceiling is checked
    before the request like every other model call.
    """
    key = f"model.probe:{utcnow():%Y%m%dT%H%M}"
    try:
        job = JobQueue(db).enqueue("orchestrator", "model.probe", {},
                                   idempotency_key=key)
    except DuplicateJob:
        return {"enqueued": False,
                "reason": "a probe was already queued this minute"}
    return {"enqueued": True, "job_id": job.id,
            "note": "the result appears at GET /api/model once the worker runs it"}


@app.get("/api/arbitrage")
def api_arbitrage(pod: str = "") -> dict:
    """What this company can currently score about a micro-market, and what the rest needs.

    An unmeasured dimension leaves the arithmetic and is named. Filling it with a neutral
    value keeps the number's shape and loses its meaning, and nobody can tell by looking.
    """
    from ..radar import arbitrage

    return arbitrage.state(db, pod=pod)


@app.get("/api/seasonal/cycle")
def api_seasonal_cycle() -> dict:
    """One seasonal cycle end to end, with every link's evidence (#300, release-blocking).

    Runs without a model provider too, and says so: the generating step reports gated rather
    than inventing a placeholder concept, because a cycle that produced nothing and reported
    itself complete is the failure this endpoint exists to make impossible.
    """
    from ..gateway import routing
    from ..gateway.anthropic import AnthropicProvider
    from ..gateway.model_gateway import ModelGateway
    from ..seasonal import cycle

    gateway = None
    if AnthropicProvider.key():
        _task, tier = routing.route("concept_generation")
        gateway = ModelGateway([AnthropicProvider(model=tier.model)])
    return cycle.run(db, gateway=gateway)


@app.get("/api/preproduction")
def api_preproduction() -> dict:
    """What a concept post must say, and what it may never imply (#4).

    Nothing is published: no social credential has been granted. The refusals run anyway, so
    they are tested before the day they matter.
    """
    from ..commerce import preproduction

    return {
        "must_say_it_is_a_concept": list(preproduction.CONCEPT_MARKERS),
        "refused_because_they_imply_a_purchase": [
            {"pattern": pattern, "why": why}
            for pattern, why in preproduction.IMPLIES_AVAILABILITY],
        "never_fabricated": list(preproduction.NEVER_FABRICATED),
        "publishing": {"state": "gated", "gated_on": "social_credentials"},
        "note": ("A picture of a thing that does not exist, posted where people buy things, "
                 "is a pre-order somebody will try to place. No code path here can author an "
                 "engagement number."),
    }


@app.get("/api/markets")
def api_markets() -> dict:
    """The cross-border lens: language, holidays, currency, and what does not differ (#268).

    The requirement warns against assuming Canadian search behaviour is global. The error
    actually present points the other way: the benchmark is a United States shop, so every
    term frequency measured here describes that market rather than this company's.
    """
    from ..commerce import markets

    return markets.lens(db)


@app.get("/api/portfolio")
def api_portfolio() -> dict:
    """Whether the catalogue competes with itself, and whether it stuffs to avoid it (#240).

    The two failures are opposites. A catalogue all reaching for one head term ranks its own
    listings against each other; a catalogue fixing that by loading every term anybody might
    type gets demoted for it. Both are counted from the listings themselves.
    """
    from ..commerce import portfolio

    return portfolio.diversification(db)


@app.get("/api/rollforward")
def api_rollforward() -> dict:
    """Two capacities over one calendar, and the weeks one calendar throws away (#267).

    Engineering leaves an occasion when its last lane closes; marketing leaves weeks later,
    at the buyer's own last practical make date, because the catalogue already listed goes on
    selling until then. Those weeks are the ones that earn most, and a shop budgeting one
    capacity against one calendar has already moved on. Rolling forward is refused in both
    directions: nothing leaves an occasion that still holds it, and nothing arrives at one
    whose own preparation lead has passed. Where demand falls before the structural floor is
    reported as unobserved rather than guessed at.
    """
    from ..seasonal import rollforward

    return rollforward.state()


@app.get("/api/upgrade-pipeline")
def api_upgrade_pipeline() -> dict:
    """Bounded upgrade proposals, and the two things they may never prepare (#190).

    Evidence is a recorded run, never a field the proposal sets: a proposal that runs its own
    tests and reports them passed has reported an opinion in the shape of a fact. And evidence
    describes a version -- revising a proposal invalidates what was gathered against the old
    one rather than ageing it out, which is the failure that only happens to something working
    while nobody watches. Auto-promotion reads the tier and never the proposal's own view of
    its risk; there is no confidence field to set.
    """
    from ..improve import upgrades

    return upgrades.state()


@app.get("/api/nightly")
def api_nightly() -> dict:
    """The nightly sweep, and the word it is structurally unable to say (#193).

    A stage has three outcomes, never two: ran and found things, ran and found nothing, or
    did not run. A stage that read zero rows reports did_not_run however it describes itself,
    because finding nothing in nothing has not established there was nothing to find. The
    verdict is computed from what each stage returned rather than from this job finishing
    without raising.
    """
    from ..improve import nightly

    return nightly.state()


@app.get("/api/weekly-evolution")
def api_weekly_evolution() -> dict:
    """The weekly deep cycle, and the review that is only allowed to add (#194).

    Eight domains, audited rather than visited: nothing read is `not_audited`, not clean.
    Three of the four architecture moves subtract, because a review permitted to add
    specialists and never to merge or retire one grows the org chart every week, one
    individually defensible step at a time. A department may never propose the revision of
    its own success measure, and no revision may be argued from the old number having been
    unflattering.
    """
    from ..improve import weekly

    return weekly.state()


@app.get("/api/pod-learning")
def api_pod_learning() -> dict:
    """Pods that get better, in the two directions that pull against each other (#226).

    "More discerning and more creative" is a trap if it becomes one number. A pod that
    rejects everything is maximally discerning and contributes nothing; one that accepts
    everything is generative and worthless, and a single score can rise while either
    collapses. So there are two measures and nothing returns one alone.

    Discernment is precision against outcomes and explicitly not rejection rate -- rejection
    rate is available immediately and rises whenever a pod is being careful, which is why it
    gets used, and what it measures is caution.
    """
    from ..intel import pod_learning

    return pod_learning.state()


@app.get("/api/elite-panel")
def api_elite_panel() -> dict:
    """Learning from the best shops without becoming one (#215, #219, #220, #227, #228).

    The failure #227 guards is one of aggregation, not of any single decision. Every
    individual choice to match the benchmark is defensible -- they are good, this is what
    good looks like -- and a year of defensible choices is a shop that looks like a copy of a
    shop. Nobody ever decides to become derivative, which is why parity alone is a refusal
    rather than a caution.

    A panel of one is one shop's aesthetic with a formal name. A standard may be raised by a
    competitor and never lowered by one. And the owner's veto records *why* in a countable
    vocabulary, because the reason is the part that evaporates: acted on once, and six months
    later nobody can say whether the same objection was raised eleven times or once.
    """
    from ..intel import panel, veto

    return {"panel": panel.state(), "veto": veto.state()}


@app.get("/api/mechanisms")
def api_mechanisms() -> dict:
    """What a competitor listing teaches, and what it may never carry away (#214).

    A mechanism is a claim about *how* a listing works on a buyer -- the first photograph
    answering the sizing question before it is asked, the title leading with the occasion.
    It is never a claim about what the product depicts. That line is the whole safety
    property: "a wreath with cardinals" is a description of a protected design, and once it
    is written down as a lesson the pipeline will faithfully reproduce it.

    So decomposition refuses depiction words, reuses `culture.rights` for the containment
    check rather than reimplementing it, and requires a claimed effect of at least five
    words -- an observation with no effect cannot be wrong, and something that cannot be
    wrong is not evidence.

    A tournament is a search, not a response. It needs at least two mechanisms this shop
    does not already have AND demand evidence for the arena from our own data; parity is
    never a reason to ship (#227). Without that threshold, most competitor listings are
    notes, because a pipeline that answers every one of them spends the creative budget on
    whatever the competitor happened to publish.
    """
    from ..intel import mechanisms

    return mechanisms.state()


@app.get("/api/seasonal-engine")
def api_seasonal_engine() -> dict:
    """A year with many occasions in it, and the constant that says otherwise (#33).

    Priority comes from a score with no favourites: seven factors multiplied rather than
    averaged, because an occasion with no time remaining scores zero however strong its
    demand. Evergreen never drops to zero -- a shop entirely inside one festival has nothing
    to sell in February -- and the floor is subtracted before anything is granted rather than
    checked afterwards. Squads stand down by arithmetic. Construction primitives and
    commercial lessons cross seasons; designs do not. A breakout moves allocation and cannot
    reach a gate.

    The constant the merge instruction names is gone: all five call sites now read
    `compression.priority_shares()`, which returns scores when any occasion has them and the
    owner's named campaign, labelled, when none does. The seed survives because the evidence
    does not exist yet -- a straight cutover would reserve nothing for the campaign whose
    making window is open -- but it can no longer be read as a measurement.
    """
    from ..seasonal import engine

    return engine.state()


@app.get("/api/creative-flow")
def api_creative_flow() -> dict:
    """Truth to creative, and the listing as a shopper meets it (#63, #66).

    Creative may select from truth and may never extend it. Showing three of seven stitch
    types is a photograph of part of a thing; showing an eighth is a claim about a pattern
    that does not contain it, made by an image nobody thought of as a statement. The flow is
    ordered because a brief produced after the creative is a caption, and the asset-truth
    comparison is refused when its author made the work.

    And the listing is evaluated where it is chosen rather than where it was built: at 170
    pixels, in a grid, by somebody who does not yet know what this is. The first three frames
    are a context rather than a prefix -- most people do not scroll.
    """
    from ..publish import brief, mobile

    return {"flow": brief.state(), "mobile": mobile.state()}


@app.get("/api/listing-integrity")
def api_listing_integrity() -> dict:
    """Measurements traced, defects named, and the certificate that invalidates itself (#60, #68, #70).

    Every displayed number traces to the geometry object, and the check that matters is the
    contradiction: two numbers disagreeing about the same axis of the same component is
    invisible to any check that validates measurements one at a time, and one at a time is
    how they are usually checked.

    Visual defects get the treatment compiler defects already had -- a reproduction, a
    fixture, and a recurrence read as a bug in the fixture rather than a second bug in the
    renderer. And the listing certificate is invalidated by its inputs changing rather than
    by somebody revoking it, because a revocation step is a step somebody forgets and the
    forgetting is silent.
    """
    from ..publish import defects, dimensions, listing_set

    return {"dimensions": dimensions.state(), "defects": defects.state(),
            "listing_set": listing_set.state()}


@app.get("/api/asset-eligibility")
def api_asset_eligibility() -> dict:
    """What an asset is made of, what it is for, and the four gates between (#57, #58, #65, #69).

    `AssetClass` says what an asset is made of. Purpose says what it is allowed to do, and the
    requirement's own sentence is why both are needed: a technically correct chart cannot be
    promoted to hero merely because it rendered successfully. Rendering is a fact about the
    medium; being the hero is a question about the purpose.

    Each frame has exactly one job, and the set is checked for job collision rather than image
    similarity -- five genuinely different charts all doing DETAIL is the failure every
    pixel-level comparison passes. Each of the four gates reports passed, failed or not_run,
    and a gate that never ran has not passed. The honesty label is computed from the medium
    and is never permission: the truth verdict is consulted independently of it.
    """
    from ..publish import eligibility

    return eligibility.state()


@app.get("/api/owned-ip")
def api_owned_ip() -> dict:
    """The characters, motifs and worlds this company owns, and the direction (#146).

    Recurrence cannot be declared: an element becomes recurring by having recurred across
    enough releases and enough seasons, and there is no field that promotes it. Originality
    is checked over the name, the description and every derived primitive rather than over
    the name alone, because the failure being guarded is a character with an original name
    whose design is a recognisable external one -- which looks like an asset and carries the
    full risk of the thing it resembles.

    `dependence()` refuses to answer from a single reading, because "not permanent dependence
    on external pop culture" is a direction, and a dependence nobody trends is one nobody
    notices growing.
    """
    from ..culture import cast

    return cast.state()


@app.get("/api/freshness")
def api_freshness() -> dict:
    """How often each department's evidence goes stale, and by which clock (#191).

    A single interval across every department is far too slow for a competitor's catalogue
    and meaningless for the compiler. Each cell is mapped to how fast its world changes when
    nobody is looking, and compiler mathematics gets no interval at all -- it goes stale when
    the code changes, not when the clock runs, so a long interval would report it current for
    another month after somebody changed the compiler.

    Two clocks, because a freshness SLA measured in "when did we last look" rewards looking.
    A department re-running a scan hourly and learning nothing is perfectly fresh, and that
    is the commonest real state of an improvement programme.
    """
    from ..improve import freshness

    return freshness.state()


@app.get("/api/improvement-swarm")
def api_improvement_swarm() -> dict:
    """The meta-agents, and the league they argue in front of (#179, #180).

    An improvement swarm graded on changes made will make changes: forty findings, thirty
    proposals, twelve promotions, and no capability curve anywhere that moved. So a role's
    score is realised uplift and `proposals_made` is arithmetically unable to reach it. No
    role both proposes and judges, the cost optimiser may not buy its savings from
    reliability, and nothing may be traded for deterministic validation.

    The league adds what #180 asked for and #95 had not needed: latency as a fourth axis, a
    holdout that is never tuned against, a promotion bar that scales with how much was
    measured, and a rollback target recorded before anybody needs it.
    """
    from ..improve import league, roles

    return {
        **roles.state(),
        "league": {
            "axes": {k: v[1] for k, v in league.AXES.items()},
            "quality_margin": league.QUALITY_MARGIN,
            "significant_tasks": league.SIGNIFICANT_TASKS,
            "cost_tolerance": league.COST_TOLERANCE,
            "latency_tolerance": league.LATENCY_TOLERANCE,
            "holdout_slip": league.HOLDOUT_SLIP,
            "note": ("a fixed shared set is overfitted by the league itself, not by any one "
                     "author: a hundred challengers judged on the same forty tasks are "
                     "selected for those forty, and nobody ever brought a task of their own"),
        },
    }


@app.get("/api/calibration")
def api_calibration() -> dict:
    """Forecast against outcome, and what having been optimistic costs (#262).

    A forecast that was not written down before its period is a description, and
    recalibrating against descriptions builds a model that is always well calibrated and
    never right -- so `made_on` must precede the period and a later date is refused. The
    error is split in log space rather than by a waterfall, because a waterfall over a
    product gives each term a different share depending where it is walked and the order is
    chosen after the numbers are known. Optimism is penalised five times as hard as
    pessimism and recovers only after a run of accurate periods. Periods with no live
    listings are excluded rather than scored, which is every period today.
    """
    from ..scale import calibration

    return calibration.state()


@app.get("/api/friction")
def api_friction() -> dict:
    """The buyer journey, audited where confusion is made rather than where it lands (#261).

    A refund request that says "I thought I was buying the blanket" arrives at support and
    was caused in the listing, and an audit grouped by arrival produces a better support
    macro while the listing goes on saying the same thing. Friction is therefore filed at
    its cause. The second guard is the one this build keeps rebuilding: a stage with no
    complaints and no traversals reads `not_yet_walked`, never `clean`, because zero
    complaints from zero buyers is the evidence for both.
    """
    from ..commerce import friction

    return friction.state()


@app.get("/api/interviews")
def api_interviews() -> dict:
    """The first-hundred interview instrument, and what it structurally cannot say (#260).

    A voluntary sample answers a different question than the one asked, so nothing here is
    ever a finding: the output is hypotheses, labelled in the data, promotable only by an
    instrument that did not ask anybody a question. Selection rules that can see the outcome
    and incentives that can see the answer are refused by name, and the blind spot -- every
    person who did not buy -- is stated rather than implied.
    """
    from ..growth import interviews

    return interviews.state()


@app.get("/api/tools")
def api_tools() -> dict:
    """Free tools that answer before they ask, and the flows over a consented list (#255, #251).

    A tool that withholds its answer until somebody hands over an address is a lead capture
    form wearing a calculator's name. Five of the six tools the requirement names are
    arithmetic this system already runs on every release; what is missing is a surface. And
    there is no open rate here: an open is not a business outcome, and a flow judged on opens
    is optimised toward subject lines and away from the purchase.
    """
    from ..growth import tools

    return tools.state()


@app.get("/api/video")
def api_video() -> dict:
    """Video modules, where each fits, and why the canonical tutorial matters (#248).

    A clip that outlives its pattern is worse than no clip, because it is trusted and it is
    specific: the pattern is corrected, the instructions are reissued, and the
    troubleshooting video goes on telling people to do the thing that was wrong. So a module
    is recorded as a derived artefact and goes stale by the same mechanism a PDF does.
    """
    from ..growth import video

    return video.state()


@app.get("/api/pins")
def api_pins() -> dict:
    """What makes two pins different, and what cannot be produced yet (#246).

    Five pins that differ in crop, overlay and filter are one pin posted five times, and
    they are indistinguishable from five pins to any check that looks at the file. A pin
    here is an angle, a destination and a date rather than an image: image generation is a
    capability nobody has granted, and there is nowhere for a pin to land.
    """
    from ..growth import pins

    return pins.state()


@app.get("/api/clusters")
def api_clusters() -> dict:
    """Search clusters, seeded from questions makers demonstrably asked (#247).

    A keyword list produced by asking a model what crocheters search for is a list of things
    that sound like searches, and it is indistinguishable from a good one until a year of
    writing has been spent on it. These are seeded from the complaint themes counted from
    observed reviews: a complaint is an informational intent that arrived too late.
    """
    from ..growth import clusters

    return clusters.state()


@app.get("/api/ladder")
def api_ladder() -> dict:
    """The value ladder's rungs, its steps, and what a discount may do to them (#233, #234).

    A price that is on sale a third of the time is not a price -- it is a higher number that
    appears before the real one. The flagship is the one product whose job is to say what
    this shop is worth, so it is never routinely discounted. Tier movement, attach rate,
    contribution and lifetime value all need a customer and are reported as unmeasurable
    rather than zero.
    """
    from ..commerce import bundles, ladder

    out = ladder.state()
    out["bundles"] = bundles.state()
    return out


@app.get("/api/governor")
def api_governor(days: int = 30) -> dict:
    """Central budget control, and the three numbers it refuses to invent (#188).

    Attribution sums to the bill or it is refused: the spend nobody has a story for is
    exactly the spend worth looking at, so the remainder is named rather than dropped. The
    anomaly detector has no baseline, marginal value has a zero numerator, and parallelism
    cannot be judged from one worker count -- each says so rather than producing a number
    with the right shape and no meaning.
    """
    from ..finance import governor

    out = governor.state()
    with db.session() as session:
        out["report"] = governor.report(session, days=days)
    return out


@app.get("/api/console")
def api_console() -> dict:
    """One page's worth of operations, for an owner holding a phone (#183).

    A public marketing site is not required to keep agents alive; a console is. This
    assembles what the requirement names -- health, queues, products, agent activity, spend,
    incidents, approvals, experiments, deployment version and learning changes -- from the
    endpoints that already serve each one, so there is a single request to make when the
    question is "is anything waiting on me".

    Health is #185's verdict rather than a liveness ping, which means this page can say
    `idle`: every process alive and nothing completed is not healthy, and a console that
    cannot say so is a console that will report a green week of nothing.

    On exposure: this aggregates what the individual read endpoints already serve, at the
    same exposure. The two write paths -- the continuity export and the dead-letter requeue
    -- stay behind the operator credential, and nothing here is a new door.
    """
    import os

    from ..build2 import executor
    from ..intel import learning
    from ..ops import health

    env = dict(os.environ)
    with db.session() as s:
        readings = health.read(s, runner_state=runner.STATE.to_dict(), env=env)
        verdict = health.verdict(readings)
        approvals = executor.approval_inbox(db, env=env)
        jobs = list(s.scalars(select(Job).order_by(Job.id.desc()).limit(10)))
        pending = s.scalar(select(func.count()).select_from(Job)
                           .where(Job.status == JobStatus.PENDING)) or 0
        dead = s.scalar(select(func.count()).select_from(Job)
                        .where(Job.status == JobStatus.DEAD)) or 0
        incidents = list(s.scalars(select(Incident).where(Incident.resolved == False)))  # noqa: E712
        products = s.scalar(select(func.count()).select_from(Product)) or 0
        certified = s.scalar(select(func.count()).select_from(PatternVersion)
                             .where(PatternVersion.certified)) or 0
        limits = [{"scope": limit.scope, "daily_cap_cad": limit.daily_cap_cad,
                   "spent_today_cad": limit.spent_today_cad, "paused": limit.paused}
                  for limit in s.scalars(select(SpendLimit))]
        agents = [{"name": a.name, "authority": getattr(a.authority, "value", a.authority),
                   "daily_cost_ceiling_cad": a.daily_cost_ceiling_cad}
                  for a in s.scalars(select(Agent).order_by(Agent.name))]
        experiments = [{"name": e.name, "kind": e.kind, "state": e.state,
                        "product_slug": e.product_slug}
                       for e in s.scalars(select(Experiment).order_by(Experiment.id.desc())
                                          .limit(10))]
    # `learning.observations` takes the Database rather than a Session, because it opens its
    # own. Calling it inside the block above passed a Session to something that expects to
    # open one, which is the shape of mistake two different session conventions produce.
    changes = learning.observations(db)

    return {
        "health": {"state": verdict["state"], "why": verdict["why"],
                   "down": verdict["down"], "degraded": verdict["degraded"],
                   "readings": verdict["readings"]},
        "queues": {"pending": int(pending), "dead_letters": int(dead),
                   "recent": [{"id": j.id, "type": j.job_type, "agent": j.agent,
                               "status": getattr(j.status, "value", j.status)}
                              for j in jobs]},
        "products": {"count": int(products), "certified_versions": int(certified)},
        "agents": agents,
        "spend": {"limits": limits},
        "incidents": [{"signature": i.signature, "severity": i.severity,
                       "halts_publication": i.halts_publication,
                       "product_slug": i.product_slug, "summary": i.summary}
                      for i in incidents],
        "approvals": approvals,
        "experiments": experiments,
        "deployment": {"version": os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")[:12],
                       "phase": os.environ.get("BRAMBLELOOP_PHASE", "shadow"),
                       "started_at": runner.STATE.to_dict().get("worker_started_at")},
        "learning_changes": changes[:10],
        "note": ("the two questions an absent owner actually has are 'is it working' and "
                 "'is anything waiting on me', and they are the first and the "
                 "seventh key here"),
    }


@app.get("/api/health-signals")
def api_health_signals() -> dict:
    """Every health signal with its evidence, and what online is allowed to mean (#185)."""
    import os

    from ..ops import health

    out = health.state()
    with db.session() as s:
        readings = health.read(s, runner_state=runner.STATE.to_dict(), env=dict(os.environ))
        out["verdict"] = health.verdict(readings)
        out["remediation"] = health.remediation(s, readings)
    return out


@app.get("/api/provenance")
def api_provenance() -> dict:
    """What every derived artefact was made from, and what the sentinel found (#171, #173).

    A stable slug must never make stale output appear current, so freshness is proved rather
    than assumed: an artefact with no provenance row is unproven, not fresh. A mismatch is a
    proven defect and blocks the product's publication through the flag the publish path
    already consults; an absence is a backlog, counted and never called fresh.
    """
    from ..ops import artefacts as provenance

    out = provenance.state()
    with db.session() as session:
        current = provenance.current_from_db(session)
        expected = provenance.expected_from_db(session)
        verdicts = provenance.check(session, current=current, expected=expected)
        out["graduation"] = provenance.graduation(session, current=current,
                                                  expected=expected)
    out["estate"] = {
        "checked": len(verdicts),
        "fresh": sum(1 for v in verdicts if v.state == provenance.FRESH),
        "stale": sum(1 for v in verdicts if v.state == provenance.STALE),
        "unproven": sum(1 for v in verdicts if v.state == provenance.UNPROVEN),
    }
    return out


@app.get("/api/trajectory")
def api_trajectory() -> dict:
    """The scenario model's terms, and why it states no probability tonight (#26).

    A Monte Carlo over inputs nobody has measured produces a distribution of assumptions to
    four decimal places with a histogram, which is what makes it persuasive. No term of this
    model has been observed, so the run refuses and names the primary constraint instead --
    "nobody is arriving" does not need a simulation.
    """
    from ..scale import trajectory

    out = trajectory.state()
    out["tonight"] = trajectory.nightly(None)
    return out


@app.get("/api/allocation")
def api_allocation() -> dict:
    """Where the week goes, and why the default is not more engineering (#30).

    Engineering work is always available, always visible and never requires anybody outside
    this company; distribution requires an audience that does not exist yet. So the mature
    mix arrives as a number, distribution has a floor no bottleneck may cross, and an
    unmeasured bottleneck is not a bottleneck.
    """
    from ..commerce import lanes
    from ..scale import allocation

    with db.session() as session:
        qa = lanes.qa_stable(lanes.observe(session))
    out = allocation.state()
    out["today"] = allocation.allocate(qa=qa)
    return out


@app.get("/api/replication")
def api_replication() -> dict:
    """What counts as a winner, and why the reason for one is rarely a single thing (#22).

    Rank is not credibility: in a catalogue of three the best seller may have sold twice. A
    winner normally differs from the field on every dimension at once, each a complete
    explanation of which at most one is true, so candidate causes are ranked by how
    distinguishable they are and a confounded winner is reported as confounded.
    """
    from ..commerce import replication

    return replication.state()


@app.get("/api/free-to-paid")
def api_free_to_paid() -> dict:
    """What free work must carry, and the ladder it is supposed to move people up (#10).

    A free pattern for something this company sells does not lead to it, it replaces it --
    and that failure looks exactly like success from the inside, because the downloads go up.
    Nothing free exists yet, and an empty funnel is an empty funnel rather than a failing one.
    """
    from ..growth import free_to_paid

    out = free_to_paid.state()
    out["plan"] = free_to_paid.plan([])
    return out


@app.get("/api/offers")
def api_offers() -> dict:
    """The six offers a design can wear, and what each one tests (#13).

    The same design sold six ways is six propositions, and one of them failing says nothing
    about the other five. Two of the six cannot be delivered today and are named as
    unavailable rather than quietly priced: nothing here can make a video, and a stated
    answer time is a promise nobody has measured the capacity to keep.
    """
    from ..commerce import offers

    return offers.state()


@app.get("/api/benchmarks")
def api_benchmarks() -> dict:
    """The funnel axes, the five metrics and the floors under a baseline (#14).

    A baseline belongs to a cell -- category, traffic source, price band, shop maturity --
    and a comparison across cells is refused with the axes that differ. There are no cells
    yet: no listings, no impressions, no orders. That is different from a baseline of zero.
    """
    from ..commerce import benchmarks

    out = benchmarks.state()
    out["cells"] = benchmarks.cells([])
    return out


@app.get("/api/listing-tests")
def api_listing_tests() -> dict:
    """What a listing test must carry, and what this company has actually established (#16).

    A listing nobody saw did not fail -- it was not tested -- so an unreadable test writes
    nothing to the memory, because recording it as a disproof would block an idea nobody has
    tried. A disproof closes a question only in the context that produced it.
    """
    from ..commerce import listing_tests

    out = listing_tests.state()
    with db.session() as session:
        out["established"] = listing_tests.known(listing_tests.load(session))
    return out


@app.get("/api/creators")
def api_creators() -> dict:
    """The seeding roster: what a collaboration may ask for, and what it may never buy (#9).

    A collaboration buys work -- a tested sample, a finished photograph, a colourway nobody
    here chose, a crochet-along, a post. It can never buy an opinion: a review is not in the
    deliverable vocabulary and no caller can add one. The roster is empty, and an empty
    roster is not a network whose reliability is zero.
    """
    from ..growth import creators

    out = creators.state()
    with db.session() as session:
        out["roster"] = creators.roster(session)
    return out


@app.get("/api/lanes")
def api_lanes() -> dict:
    """The two production queues, their floors, and the gate list neither may shorten (#5).

    The fast lane buys learning rate and search coverage; the flagship lane buys authority,
    content depth and order value. Both floors exist because the first eats the second one
    defensible week at a time. Core QA stability is read from the records rather than set,
    because "after core QA stabilizes" is a condition about evidence.
    """
    from ..commerce import lanes

    with db.session() as session:
        evidence = lanes.observe(session)
    out = lanes.state()
    out["qa"] = lanes.qa_stable(evidence)
    out["qa"]["observed"] = {
        "regression_fixtures": evidence.regression_fixtures,
        "regression_passed": evidence.regression_passed,
        "certified_releases": evidence.certified_releases,
        "open_halting_incidents": evidence.open_halting_incidents,
    }
    return out


@app.get("/api/colour")
def api_colour(pod: str = "") -> dict:
    """Dated palette intelligence, from the colours Etsy publishes for every photograph (#280).

    One of the three sources the requirement names is available. The other two -- external
    fashion signals and this company's own colour performance -- say so, because a forecast
    resting on one source presented as resting on three is the most confident kind of wrong.
    """
    from ..seasonal import colour

    return colour.forecast(db, pod=pod)


@app.get("/api/owned")
def api_owned() -> dict:
    """Which flagships have an owned acquisition counterpart, and the CASL rules on sending.

    The email path is governed by Canada's Anti-Spam Legislation, and the rules are enforced
    in code rather than described in a policy: a comment in a detail dictionary does not stop
    a send (#20).
    """
    from ..growth import owned

    return {
        "counterparts": owned.counterparts(db),
        "owned_share": owned.owned_share(db),
        "casl": {
            "bases": owned.BASES,
            "implied_lifetime_days": owned.IMPLIED_LIFETIME_DAYS,
            "required_in_every_message": list(owned.REQUIRED_IN_EVERY_MESSAGE),
            "unsubscribe_must_work_for_days": owned.UNSUBSCRIBE_VALID_DAYS,
            "screen_not_clearance": ("these are the rules a careful sender follows, encoded "
                                     "so a send cannot skip them. Not legal advice"),
        },
    }


@app.get("/api/promotion")
def api_promotion() -> dict:
    """Whether the catalogue is being conditioned to require discounts (#19).

    The share on sale is countable today. Whether anything still sells at full price needs
    orders, and is reported unmeasurable rather than assumed: a catalogue with no sales has
    no full-price sales either, and that is a different finding from one that has stopped
    having them.
    """
    from ..commerce import promotion

    return {
        "dependence": promotion.dependence(db),
        "rules": {
            "max_promotion_days": promotion.MAX_PROMOTION_DAYS,
            "steep_discount_above": promotion.STEEP_DISCOUNT_ABOVE,
            "catalogue_dependence_above": promotion.CATALOGUE_DEPENDENCE_ABOVE,
        },
        "note": ("Measured on contribution rather than revenue lift. For a digital pattern "
                 "the two largely agree, and they come apart once the cost to create is "
                 "amortised over the units it sells (#31)."),
    }


@app.get("/api/dependency")
def api_dependency() -> dict:
    """Which single thing failing would end this company, and whether that is a risk yet.

    Concentration alone is not a finding. A dependency is existential when it is concentrated
    *and* load-bearing; before it carries anything it is a plan, and telling a pre-revenue
    company to open a second marketplace is how its one real advantage becomes five
    half-built ones (#29).
    """
    from ..scale import dependency

    return dependency.report(db)


@app.get("/api/arbitrage/departments")
def api_arbitrage_departments() -> dict:
    """Every observed department scored, and the four dimensions observation supports.

    The scorer run rather than available. Listing density, season timing, differentiation,
    support burden and expected contribution stay named and empty: one catalogue is not a
    market, an occasion has to be chosen, and the last two need orders.
    """
    from ..radar import arbitrage

    return arbitrage.score_observed(db)


@app.get("/api/breakthrough")
def api_breakthrough(arena: str = "stocking") -> dict:
    """The divergent lane: what is not being made, and what that claim currently rests on.

    With no observed competitor listing, a divergence is against our own catalogue -- useful,
    and not a market gap. Nothing here borrows the authority of a scan that has not happened.
    """
    from ..creative import breakthrough

    return {**breakthrough.diverge(db, arena=arena), "lanes": breakthrough.state(db)}


@app.get("/api/seasonal/transform")
def api_seasonal_transform() -> dict:
    """How a proven object becomes a seasonal one, and which of those are only photographs.

    Includes the master's own worked example run through the engine, so the answer is a
    function of the rules rather than of whoever is reading them.
    """
    from ..creative import seasonal_transform

    return {
        "layers": [{"layer": l.key, "what": l.what, "why": l.why,
                    "changes_the_object": l.changes_the_object}
                   for l in seasonal_transform.LAYERS],
        "worked_example": seasonal_transform.striped_cardigan_example(),
    }


@app.get("/api/seasonal/remerchandising")
def api_seasonal_remerchandising(event: str = "Christmas", pod: str = "") -> dict:
    """Existing certified products that could be sold into a season, and what each move needs.

    Re-merchandising never increments the catalogue, and "proven" is a claim about sales this
    company cannot make yet -- so candidates are eligible rather than proven, on every row.
    """
    from ..creative import prospecting
    from ..seasonal import remerchandising

    # Default to the same occasion the weekly cadence inspects -- the soonest proven arena
    # -- rather than to no occasion at all. The buyer-language map is per-occasion, so a
    # request that names none was reporting `search_positioning` as unavailable when the
    # truth was that nobody had looked. The cadence had always passed a pod; the endpoint
    # never did, so the two views of one capability disagreed and the human-readable one
    # was the wrong half (#292).
    if not pod:
        try:
            found = prospecting.arenas(db)
        except prospecting.NoArenasContradictsEvidence:
            found = []
        if found:
            soonest = min(found, key=lambda a: a.days_away)
            pod = soonest.pod
            event = event or soonest.event

    return remerchandising.plan(db, event=event, pod=pod)


@app.get("/api/seasonal/fastlane")
def api_seasonal_fastlane() -> dict:
    """What "fast" is allowed to mean here: bounded scope, and the same gates as everything.

    The lane shortens the queue and never the gate list, and the list is the release chain's
    own -- imported rather than retyped, because a second copy is how that guarantee would
    quietly stop being true.
    """
    from ..seasonal import fastlane

    return fastlane.state()


@app.get("/api/seasonal/teams")
def api_seasonal_teams() -> dict:
    """Which events hold dedicated capacity today, and what each holds.

    A team is a share of capacity or it is a name. One whose occasion has passed the buyer's
    last practical make date releases what it held without anybody remembering.
    """
    from ..seasonal import teams, uncertainty

    allocation = teams.allocate(db, samples=uncertainty.sample_count(db))
    try:
        teams.check(allocation)
    except teams.TeamRefused as exc:
        allocation["problem"] = str(exc)
    return allocation


@app.get("/api/seasonal/collections")
def api_seasonal_collections() -> dict:
    """The collection architecture's rules, and what a coherent collection has to satisfy.

    No collection has been assembled from live concepts: the concept pool a collection is
    built from needs the creative engine, so this reports the constraints rather than a
    result it does not have.
    """
    from ..seasonal import collections

    return {
        "minimum_members": collections.MIN_MEMBERS,
        "minimum_price_points": collections.MIN_PRICE_POINTS,
        "derivative_below": collections.DERIVATIVE_BELOW,
        "assembled": 0,
        "note": ("Members share a palette and a story and differ structurally. A recolour "
                 "scores zero on the concept engine's own distance, so it is refused by the "
                 "same arithmetic that refuses a duplicate in a tournament field (#289)."),
    }


@app.get("/api/seasonal/benchmark-matrix")
def api_seasonal_benchmark_matrix() -> dict:
    """Events against departments, with the benchmark's half filled from what was observed.

    A department the benchmark was seen selling and this catalogue does not answer is the row
    this exists for. A department neither of us sells is not that row, and an unobserved one
    is unknown rather than empty -- all three render identically in a matrix, and the empty
    cell is the one somebody points at.
    """
    from ..seasonal import benchmark_matrix

    return benchmark_matrix.matrix(db)


@app.get("/api/seasonal/compression")
def api_seasonal_compression(event: str = "Christmas") -> dict:
    """What to build for a priority occasion this week, given what a buyer can still finish.

    A retired product class is a statement about that class. The occasion continues, and the
    capacity the closed lane was holding moves into the fastest lane still open rather than
    out of the programme.
    """
    from ..seasonal import uncertainty
    from ..seasonal.compression import CompressionRefused, programme

    try:
        return programme(event, samples=uncertainty.sample_count(db))
    except CompressionRefused as exc:
        return {"event": event, "error": str(exc)}


@app.get("/api/seasonal/depth")
def api_seasonal_depth() -> dict:
    """Every ecosystem gap, thinnest event first, as briefs rather than as a count.

    A gap report that produces no work is a report. These are briefs, not products: nothing
    here counts as coverage, and depth moves when something is built.
    """
    from ..seasonal import depth, uncertainty

    return depth.depth_plan(samples=uncertainty.sample_count(db))


@app.get("/api/seasonal/capacity")
def api_seasonal_capacity(days: int = 60) -> dict:
    """Where late-window creative capacity should go, given what a buyer can still finish.

    The failure this prevents is not designing the wrong thing. It is continuing to design
    the right thing three weeks too late, which looks like productivity the whole time.
    """
    from ..creative import family
    from ..seasonal import uncertainty
    from ..seasonal.calendar import lane_feasibility

    samples = uncertainty.sample_count(db)
    return {
        "days_to_event": days,
        "lanes": lane_feasibility(days, samples=samples),
        "roles": [{"role": r.key, "what": r.what, "lane_ceiling": r.lane_ceiling,
                   "why_it_matters": r.why} for r in family.ROLES],
        "minimum_roles_for_a_family": family.MIN_VIABLE_ROLES,
        "window_multipliers": family.WINDOW_MULTIPLIER,
        "make_time_samples": samples,
        "note": ("Graded against the make-time interval rather than a point estimate: "
                 "impossible means the optimistic bound has passed, and everything short of "
                 "that is an instruction to hurry rather than to stop."),
    }


@app.get("/api/profiles")
def api_profiles() -> dict:
    """Each cell's capability profile and what its own record says it should try next.

    Proposals only. A review that could promote its own proposals is unsupervised rewriting
    arriving from inside the department that is supposed to be measuring.
    """
    from ..improve import profiles

    return profiles.review_all(db)


@app.get("/api/tiers")
def api_tiers() -> dict:
    """How fast this company is allowed to change itself, and how much of that it has spent.

    Learning may happen as fast as evidence arrives; promotion may not. A change is graded by
    what it touches, never by what it is called.
    """
    from ..improve import tiers

    return tiers.state(db)


@app.get("/api/roi")
def api_roi() -> dict:
    """What the improvement programme bought, and whether new designs stand on what we know.

    Cost is known on the day and benefit is known later, so benefit is the number nobody goes
    back for. The sandbox result that won a promotion is deliberately not read as its return:
    counting it would make every promotion succeed by construction.
    """
    from ..improve import roi

    return {
        "realised": roi.realised_benefit(db),
        "compounding": roi.compounding_report(db),
        "neutral_band": roi.NEUTRAL_BAND,
        "realisation_days": roi.REALISATION_DAYS,
    }


@app.get("/api/dependencies")
def api_dependencies() -> dict:
    """What this company stands on, and how each one comes back.

    Grouped by what stops rather than by vendor, because vendor prestige gets that backwards:
    Postgres holds the company's memory and GitHub holds a copy of code that is also on disk.
    """
    from ..ops import dependencies

    return dependencies.map_state(db)


@app.get("/api/seasonal/feasibility")
def api_seasonal_feasibility() -> dict:
    """What each make-lane's runway actually supports, as a gradient rather than a cliff.

    Graded against the optimistic bound of the make-time interval. A point estimate cannot
    establish impossibility, and this endpoint exists because an earlier version of this
    system reported a whole season closed on the strength of an assumed seven crochet hours
    a week.
    """
    from datetime import date as _date

    from ..radar.market import SEASONAL_EVENTS
    from ..seasonal.calendar import heaviest_launchable_lane, lane_feasibility
    from ..seasonal.uncertainty import interval, sample_count

    today = _date.today()
    samples = sample_count(db)
    events = []
    for event in SEASONAL_EVENTS:
        when = event.event_date
        if when < today:
            try:
                when = when.replace(year=when.year + 1)
            except ValueError:  # pragma: no cover - 29 February
                continue
        days = (when - today).days
        events.append({
            "event": event.name, "event_date": when.isoformat(), "days_away": days,
            "heaviest_lane": heaviest_launchable_lane(days, samples=samples, today=today),
            "lanes": lane_feasibility(days, samples=samples, today=today),
        })
    return {
        "today": today.isoformat(),
        "physical_samples": samples,
        "example_interval": interval(90.0, samples=samples).to_dict(),
        "events": sorted(events, key=lambda e: e["days_away"]),
        "note": ("Infeasible means the optimistic bound has passed, not that the point "
                 "estimate has. Until a maker has actually been timed the interval is wide, "
                 "and a wide interval is the honest input to a decision about a season."),
    }


@app.get("/api/build")
def api_build() -> dict:
    """The build loop itself: what is ready, what is parked on whom, and whether it is moving.

    This is the page that answers "is anything happening" without reading code logs. The
    queue, the gates and the watchdog verdict come from Postgres, so the answer is the same
    whether or not any session is open — which is the whole point of the loop existing here
    rather than in a conversation.
    """
    from ..build2 import autonomy, executor

    # Reconcile on read as well as on the cadence: a gate that opened a minute ago should
    # show as open on the page somebody is looking at, not in an hour.
    executor.sync(db)
    report = executor.report(db)
    report["approval_inbox"] = executor.approval_inbox(db)
    # #195/#185: the proof that this runs with the owner's devices off, and the continuous
    # version of the same question.
    report["off_device_proof"] = autonomy.off_device_proof(db)
    report["health"] = autonomy.health(db)
    return report


@app.get("/api/build2")
def api_build2() -> dict:
    """Build-2 requirement coverage against v1.4.3, as data rather than a claim."""
    from ..build2 import requirements as reqs

    return {
        "spec": "spec/08_Brambleloop_Queued_Upgrades_v1.4.3_MASTER.pdf",
        "coverage": reqs.coverage(),
        "sections": reqs.sections(),
        "executable_remaining": [r.to_dict() for r in reqs.executable()[:40]],
        "blocked_on_owner": [r.to_dict() for r in reqs.by_status(reqs.OWNER_GATED)],
    }


@app.get("/api/build2/maturity")
def api_build2_maturity(requirement: int | None = None) -> dict:
    """How far the covered requirements actually got, rung by rung.

    Separate from `/api/build2` because they answer different questions and the coverage
    percentage was quietly answering both. `covered` is a judgement that the module
    satisfies the spec line; this is whether that module was ever deployed, run, or seen
    working against production data.
    """
    from ..build2 import maturity, requirements as reqs

    if requirement is not None:
        return maturity.ladder(db, reqs.get(requirement))
    return maturity.report(db)


@app.get("/api/jobs")
def api_jobs(limit: int = 50) -> dict:
    with db.session() as s:
        rows = list(s.scalars(select(Job).order_by(Job.id.desc()).limit(limit)))
        return {"jobs": [
            {"id": j.id, "agent": j.agent, "type": j.job_type, "status": j.status.value,
             "attempts": j.attempts, "error": (j.last_error or "")[:200]}
            for j in rows
        ]}


@app.get("/api/owner-actions")
def api_owner_actions() -> dict:
    with db.session() as s:
        rows = list(s.scalars(
            select(OwnerAction).where(OwnerAction.done == False)  # noqa: E712
        ))
        return {"actions": [
            {"id": a.id, "action": a.action, "reason": a.reason,
             "max_cost_cad": a.max_cost_cad, "minutes": a.minutes,
             "consequence_of_delay": a.consequence_of_delay, "blocks": a.blocks}
            for a in rows
        ]}


@app.post("/api/physical-test")
def api_physical_test(payload: dict) -> dict:
    """Record a real crocheted sample. The one place measured data enters the system.

    Deliberately a queued job rather than an inline write: it changes published figures and
    can raise a defect that halts a product, so it belongs in the audited queue with
    everything else that can do that.
    """
    required = ("slug", "grams_by_color", "ball_band_grams", "ball_band_metres")
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return JSONResponse({"error": f"missing: {missing}",
                             "note": ("grams per colour and the ball band (g and m) are "
                                      "required; grams cannot become metres without the "
                                      "band, and a sample in grams alone is unusable")},
                            status_code=422)
    try:
        job = JobQueue(db).enqueue("quality_director", "physical.record", payload)
    except DuplicateJob:
        return {"enqueued": False, "reason": "an identical sample is already queued"}
    return {"enqueued": True, "job_id": job.id if job else None}


@app.get("/api/launch")
def api_launch() -> dict:
    """What stands between this shop and a live customer, computed on request.

    Separated from the owner queue: the queue is what a person has to do, this is the whole
    picture including the parts that are still ours.
    """
    from ..core.artifacts import ArtifactStore
    from ..gateway.model_gateway import available_providers
    from ..launch.readiness import assess, render

    try:
        providers = available_providers()
    except Exception:  # noqa: BLE001
        providers = []
    readiness = assess(db, phase=os.environ.get("BRAMBLELOOP_PHASE", "shadow"),
                       providers=providers, storage_durable=ArtifactStore().durable)
    payload = readiness.to_dict()
    payload["report_markdown"] = render(readiness)
    return payload


@app.get("/api/audit")
def api_audit(limit: int = 100, action: str | None = None) -> dict:
    """Read-only audit trail. The dashboard shows fifteen rows; verification needs more."""
    with db.session() as s:
        q = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 1000))
        if action:
            q = select(AuditLog).where(AuditLog.action == action).order_by(
                AuditLog.id.desc()).limit(min(limit, 1000))
        rows = list(s.scalars(q))
        return {"audit": [
            {"id": a.id, "at": a.at.isoformat(), "actor": a.actor, "action": a.action,
             "artifact": a.artifact, "phase": a.phase.value if a.phase else None,
             "detail": a.detail}
            for a in rows
        ]}


@app.get("/api/verify")
def api_verify() -> JSONResponse:
    """Standing safety assertions, evaluated against live state.

    "Railway says deployed" is not the same as "the company is alive and behaving". This
    answers the questions that actually matter to an absent owner: is it running, is its
    memory durable, has anything escaped shadow mode, and are the money guards still on. Each
    check reports the evidence it used, so a green result can be argued with.
    """
    checks: list[dict] = []

    def check(name: str, ok: bool, evidence) -> None:
        checks.append({"check": name, "ok": bool(ok), "evidence": evidence})

    phase = os.environ.get("BRAMBLELOOP_PHASE", "shadow")
    check("phase_is_shadow", phase == "shadow", {"BRAMBLELOOP_PHASE": phase})

    with db.session() as s:
        published = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "store.published")) or 0
        refused = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "store.publish_refused")) or 0
        certified = s.scalar(select(func.count()).select_from(PatternVersion).where(
            PatternVersion.certified)) or 0
        audits = s.scalar(select(func.count()).select_from(AuditLog)) or 0
        revenue = s.scalar(select(func.sum(LedgerEntry.gross_cad))) or 0.0
        customers = s.scalar(select(func.count()).select_from(LedgerEntry)) or 0
        limits = list(s.scalars(select(SpendLimit)))
        agents = list(s.scalars(select(Agent)))
        ad_spend = s.scalar(select(func.sum(CostEntry.amount_cad)).where(
            CostEntry.kind == "ads")) or 0.0

    check("nothing_published", published == 0,
          {"store.published": published, "store.publish_refused": refused})
    check("publication_was_actually_attempted_and_refused", refused > 0,
          {"refusals": refused})
    check("no_paid_advertising", ad_spend == 0, {"ad_spend_cad": float(ad_spend)})
    check("no_revenue_claimed", float(revenue) == 0.0 and customers == 0,
          {"revenue_cad": float(revenue), "ledger_entries": customers})
    # This assertion used to be "no model provider is configured", which was true for the
    # whole of Build 1 and stopped being true the moment the owner supplied a key. A standing
    # safety check that an owner decision has overtaken is not a safety check; it is a red
    # light nobody can clear, and the first thing a reader does with one is learn to ignore
    # it. What is still worth asserting is that the spend it makes possible is bounded.
    from ..gateway.anthropic import monthly_ceiling_cad, spent_this_month_cad

    # The bound is read from the policy rather than written here. It said `<= 25.0`, which
    # was the authorised figure until the owner raised it on 2026-09-20 -- and a hardcoded
    # bound in a production assertion is a red light that turns on when an owner decision is
    # carried out, which is the shape of check this file already warns about directly above.
    from ..finance.spend_policy import ceiling_cad as authorised_ceiling_cad

    ceiling = monthly_ceiling_cad()
    model_spend = spent_this_month_cad(db)
    check("model_spend_within_its_ceiling",
          ceiling <= authorised_ceiling_cad() and model_spend <= ceiling,
          {"providers": available_providers(), "spent_this_month_cad": model_spend,
           "monthly_ceiling_cad": ceiling})
    check("every_agent_has_a_cost_ceiling",
          bool(agents) and all(a.daily_cost_ceiling_cad > 0 for a in agents),
          {"agents": len(agents),
           "without_ceiling": [a.name for a in agents if a.daily_cost_ceiling_cad <= 0]})
    check("spend_limits_not_breached", all(not l.paused for l in limits),
          {"paused_scopes": [l.scope for l in limits if l.paused]})

    # Durability: a state this rich cannot have come from a container that started empty.
    durable = certified > 0 and audits > 0 and not _is_sqlite()
    check("state_is_in_a_durable_database", durable,
          {"engine": db.engine.dialect.name, "certified_versions": certified,
           "audit_records": audits})

    r = runner.STATE.to_dict()
    # A container that started ninety seconds ago has no tick to report yet, and saying it
    # is dead means every deploy opens a window where this endpoint reports failure. The
    # grace is bounded by the runner's own timings and expires; a worker that started long
    # ago and never ticked still fails, which is the case this check exists for.
    starting = bool(r.get("worker_starting"))
    check("worker_is_alive", bool(r["worker_alive"]) or starting,
          {"last_tick": r["worker_last_tick"], "restarts": r["worker_restarts"],
           "starting": starting, "started_at": r["worker_started_at"]})
    check("scheduler_has_ticked", r["scheduler_last_tick"] is not None or starting,
          {"last_tick": r["scheduler_last_tick"], "starting": starting})

    # Recent, not historical. A dead letter from a bug that was fixed last week is archaeology;
    # an endpoint that reports 503 forever because of it is an endpoint nobody reads. The
    # historical count stays in the evidence so the record is not quietly lost.
    q = JobQueue(db)
    dead = q.dead_letters()
    cutoff = utcnow() - timedelta(hours=24)

    def _aware(value):
        """SQLite hands back naive datetimes; Postgres hands back aware ones.

        Comparing them raises, and the comparison only happens when there is a dead letter
        to report -- so this endpoint returned 500 instead of a 503 with evidence at exactly
        the moment an absent owner needed to read it. Found when an unrelated defect put a
        real dead letter in the queue for the first time.
        """
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    # A refusal working correctly is not a defect, and there are two of them now. Shadow
    # mode refusing to publish was always one. The second arrived on 2026-09-21: a job
    # stamped with the pack version it was enqueued for, picked up by a replica still
    # running the previous build, standing aside so the right one takes it. The work then
    # happened -- and this check went red, because a deliberate refusal was being counted
    # as an unexplained death. A health signal that is red for a non-fault is a health
    # signal people stop reading, which is the failure this whole endpoint exists against.
    from ..queue.durable import deliberate_refusal

    def _deliberate(job) -> bool:
        return deliberate_refusal(job.job_type, job.last_error or "")

    unexpected = [j for j in dead if not _deliberate(j)]
    recent = [j for j in unexpected if _aware(j.finished_at or j.created_at) >= cutoff]
    check("no_unexpected_dead_letters_in_24h", not recent,
          {"recent": sorted({j.job_type for j in recent}),
           "historical_total": len(unexpected),
           "historical_types": sorted({j.job_type for j in unexpected}),
           "expected_publish_refusals":
               sum(1 for j in dead if j.job_type == "store.publish"),
           "expected_stand_asides":
               sum(1 for j in dead if j.job_type != "store.publish" and _deliberate(j)),
           "what_counts_as_expected": (
               "shadow mode refusing to publish, and a job standing aside for the build "
               "that can run it. Both are refusals working; neither is a death to explain")})

    passed = all(c["ok"] for c in checks)
    return JSONResponse({"ok": passed, "checks": checks},
                        status_code=200 if passed else 503)


@app.post("/api/dead-letters/requeue")
def api_requeue(job_types: str | None = None) -> dict:
    """Re-drive dead letters after the defect that killed them is fixed.

    GREEN under the authority matrix: reversible, no spend, and structurally incapable of
    re-driving a deliberate refusal -- a publish blocked by shadow mode stays blocked no
    matter how often this is called.
    """
    types = [t.strip() for t in job_types.split(",")] if job_types else None
    result = JobQueue(db).requeue_dead(job_types=types)
    Registry(db).audit("orchestrator", "ops.dead_letters_requeued",
                       detail={"requeued": result["requeued"][:50],
                               "skipped": result["skipped"][:50],
                               "requested_types": types})
    return result


def _is_sqlite() -> bool:
    return db.engine.dialect.name == "sqlite"


# ---- dashboard ------------------------------------------------------------

_CSS = """
:root{--ink:#1A2B3C;--pine:#244A3A;--cream:#FAF6EB;--gold:#C49545;--wine:#6E1F2A;
--muted:#6b7280;--line:#e5e0d3}
*{box-sizing:border-box}body{margin:0;background:var(--cream);color:var(--ink);
font:15px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}
header{background:var(--pine);color:var(--cream);padding:18px 24px}
h1{margin:0;font-size:20px;letter-spacing:.02em}
.sub{opacity:.8;font-size:13px;margin-top:2px}
main{max-width:1100px;margin:0 auto;padding:24px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;
margin-bottom:24px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px}
.card b{display:block;font-size:22px;color:var(--pine)}
.card span{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
h2{font-size:15px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);
margin:24px 0 8px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);
border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);font-size:13px}
th{background:#f7f4ea;font-weight:600;text-transform:uppercase;font-size:11px;
letter-spacing:.05em;color:var(--muted)}
tr:last-child td{border-bottom:none}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:600}
.done{background:#e6f2ec;color:var(--pine)}.dead{background:#fae8ea;color:var(--wine)}
.running{background:#fdf3e2;color:var(--gold)}.pending{background:#eef0f2;color:var(--muted)}
.failed{background:#fdf3e2;color:#9a6b1f}
.empty{color:var(--muted);font-style:italic;padding:12px}
.owner{border-left:4px solid var(--gold);background:#fffaf0}
"""


def _counts() -> dict:
    """Catalogue totals for the dashboard. Cheap counts, not a full listing dump."""
    with db.session() as s:
        return {
            "listings": s.scalar(select(func.count()).select_from(Listing)) or 0,
            "listing_images": s.scalar(select(func.count()).select_from(ListingAsset)) or 0,
            "content_pieces": s.scalar(select(func.count()).select_from(ContentPiece)) or 0,
        }


def _pill(status: str) -> str:
    cls = {"done": "done", "dead": "dead", "running": "running",
           "failed": "failed"}.get(status, "pending")
    return f'<span class="pill {cls}">{status}</span>'


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    st = api_status()
    q = JobQueue(db)

    with db.session() as s:
        jobs = list(s.scalars(select(Job).order_by(Job.id.desc()).limit(15)))
        audits = list(s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(15)))
        incidents = list(s.scalars(
            select(Incident).where(Incident.resolved == False)))  # noqa: E712
        owner = list(s.scalars(
            select(OwnerAction).where(OwnerAction.done == False)))  # noqa: E712
        products = list(s.scalars(select(Product).order_by(Product.id.desc()).limit(10)))
        limits = list(s.scalars(select(SpendLimit)))
        agents = list(s.scalars(select(Agent).order_by(Agent.name)))

    def rows(items, cols, empty):
        if not items:
            return f'<div class="empty">{empty}</div>'
        head = "".join(f"<th>{c}</th>" for c in cols[0])
        body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in items)
        return f"<table><tr>{head}</tr>{body}</table>"

    # Launch readiness, because "is anything waiting on me" is the question an absent owner
    # actually has, and a count of queued actions does not answer it.
    try:
        from ..core.artifacts import ArtifactStore
        from ..launch.readiness import assess

        readiness = assess(db, phase=os.environ.get("BRAMBLELOOP_PHASE", "shadow"),
                           providers=st["model_providers"],
                           storage_durable=ArtifactStore().durable)
        launch_html = "<h2>Launch readiness</h2>" + rows(
            [(r.description, "ready" if r.ready else "no", r.blocked_by or "-")
             for r in readiness.requirements],
            [["Requirement", "Ready", "Blocked on"]], "")
    except Exception as e:  # noqa: BLE001 - the dashboard must render even if this does not
        launch_html = ('<h2>Launch readiness</h2><div class="empty">could not be assessed: '
                       f'{type(e).__name__}</div>')

    # -- the Build-2 command centre (#318, and the owner's request) --------
    #
    # Built because the owner said they should not have to infer progress from code logs.
    # Every block is guarded: a dashboard that fails to render because one subsystem is
    # unhappy tells the owner nothing about the twelve that are fine.
    def _block(title: str, build) -> str:
        try:
            return f"<h2>{title}</h2>" + build()
        except Exception as e:  # noqa: BLE001
            return (f'<h2>{title}</h2><div class="empty">unavailable: '
                    f'{type(e).__name__}: {e}</div>')

    def _approvals() -> str:
        """What is waiting on the owner (#183). A count does not answer the question."""
        from ..build2 import executor

        inbox = executor.approval_inbox(db, env=dict(os.environ))
        cards = inbox.get("cards") or []
        return rows(
            [(c["gate"], c["action"], c.get("consequence_of_waiting", ""),
              c.get("requirements_unparked", c.get("parked", "")))
             for c in cards],
            [["Gate", "Action", "Consequence of waiting", "Unparks"]],
            "nothing is waiting on the owner")

    def _learning() -> str:
        """What this company has learned since yesterday, and where it came from (#183)."""
        from ..intel import learning

        seen = learning.observations(db)[:10]
        return rows(
            [(o.get("observed_on", ""), o.get("domain", ""), o.get("source", ""),
              (o.get("summary", "") or "")[:110]) for o in seen],
            [["Observed", "Domain", "Source", "What changed"]],
            "nothing observed yet -- which is a state, not a quiet week")

    def _health() -> str:
        """Online means work is progressing, not that this page rendered (#185)."""
        from ..ops import health

        with db.session() as s:
            readings = health.read(s, runner_state=runner.STATE.to_dict(),
                                   env=dict(os.environ))
        verdict = health.verdict(readings)
        return (f'<div class="grid"><div class="card"><span>state</span>'
                f'<b>{verdict["state"]}</b></div></div>'
                + f'<div class="empty">{verdict["why"]}</div>'
                + rows([(r["signal"], r["state"], r["why"][:90]) for r in
                        verdict["readings"]],
                       [["Signal", "State", "Why"]], ""))

    def _build2() -> str:
        from ..build2 import requirements as reqs

        cov = reqs.coverage()
        executable = cov.get("partial", 0) + cov.get("missing", 0)
        cards = "".join(
            f'<div class="card"><span>{k.replace("_", " ")}</span><b>{v}</b></div>'
            for k, v in sorted(cov.items()))
        return (f'<div class="grid">{cards}'
                f'<div class="card"><span>executable left</span><b>{executable}</b></div>'
                f"</div>")

    def _mission() -> str:
        from ..intel.benchmarks import MJS_KEY
        from ..intel.cadence import next_interval
        from ..intel.mission import mission_report
        from ..intel.vision import plan as vision_plan

        report = mission_report(db)
        backlog = vision_plan(db, MJS_KEY)
        cadence = next_interval(db, MJS_KEY)
        cov = report["catalogue_coverage"]
        return rows([
            ("observation", report["observation_state"]),
            ("shop", report["registry"]["shop_name"]),
            ("scan health", str(report["registry"]["scan_health"].get("state", "unknown"))),
            ("catalogue known / audited",
             f"{cov['listings_known']} / {cov['listings_audited']}"),
            ("last mandated evidence", str(report["last_mandated_evidence_at"] or "never")),
            ("images awaiting judgement",
             f"{backlog['pending_images']} (CA${backlog['estimated_cad_total']:.2f})"),
            ("scan cadence", f"every {cadence.interval_hours}h"),
            ("coverage gaps", str(report["gap_queue"]["total"])),
        ], [["Mission", "State"]], "")

    def _seasonal() -> str:
        from ..seasonal.leadtime import catalogue_plans

        room = catalogue_plans(db)
        at_risk = [r for r in room["at_risk_or_missed"] if r["status"] == "at_risk"]
        counts = room["counts"]
        head = rows([(k.replace("_", " "), str(v)) for k, v in counts.items()],
                    [["Window", "Products"]], "")
        if not at_risk:
            return head + '<div class="empty">Nothing is inside its last actionable window.</div>'
        return head + rows(
            [(r["slug"], r["event"], f"{r['days_to_latest']}d",
              r["latest_effective_launch"]) for r in at_risk[:10]],
            [["At risk", "Event", "Runway", "Last viable launch"]], "")

    def _scale() -> str:
        from ..scale.confidence import probability

        p = probability(db)
        gate = p["evidence_gate"]
        return rows([
            ("modelled probability of CA$5,000/month", f"{p['probability']:.2f}"),
            ("binding layer", p["weakest_critical_layer"]),
            ("capped by", p["capped_by"]),
            ("evidence gate", "met" if gate["satisfied"] else
             f"unmet: {', '.join(sorted(gate['unmet']))}"),
        ], [["CA$5K model", "Value"]], "")

    def _creative() -> str:
        from ..creative.audit import audit_catalogue

        report = audit_catalogue()
        freedom = report["generator_degrees_of_freedom"]
        return rows([
            ("products audited", str(report["products_audited"])),
            ("survived the creative gate", str(len(report["survivors"]))),
            ("dominant failure", str(report["autopsy"]["dominant_cause"])),
            ("constructions used", ", ".join(freedom["constructions_used"])),
            ("stitch vocabularies", ", ".join(freedom["stitch_vocabularies"])),
        ], [["Creative gate", "Value"]], "")

    def _improve() -> str:
        from ..improve.bus import compounding
        from ..improve.cells import CELLS, retrospective

        report = retrospective(db)
        comp = compounding(db)
        return rows([
            ("cells", str(len(CELLS))),
            ("measured", str(len(CELLS) - len(report["unmeasured_cells"]))),
            ("regressed", ", ".join(report["regressed_cells"]) or "none"),
            ("bottleneck", str(report["bottleneck"] or "none")),
            ("lessons acted on", f"{comp['acted_on']} / {comp['routed']}"),
        ], [["Improvement", "Value"]], "")

    def _models() -> str:
        from ..gateway.routing import budget
        from ..intel.etsy_public import health as etsy_health
        from ..launch.access import statuses

        state = budget(db)
        etsy = etsy_health()
        lines = [("model budget this month",
                  f"CA${state.spent_cad:.2f} / CA${state.ceiling_cad:.2f}"),
                 ("etsy read credential", "usable" if etsy["usable"] else etsy["reason"])]
        lines += [(c["name"], c["state"]) for c in statuses()]
        return rows(lines, [["Capability", "State"]], "")

    command_centre = (
        _block("Build 2 coverage", _build2)
        + _block("MJs mission", _mission)
        + _block("Seasonal deadlines", _seasonal)
        + _block("CA$5,000/month model", _scale)
        + _block("Creative standard", _creative)
        + _block("Improvement", _improve)
        + _block("Capabilities and spend", _models)
    )

    owner_html = ""
    if owner:
        items = [(a.action, f"CA${a.max_cost_cad:.2f}", f"{a.minutes} min",
                  a.consequence_of_delay) for a in owner]
        owner_html = "<h2>Owner action required</h2>" + rows(
            items, [["Action", "Max cost", "Time", "Consequence of delay"]], "")

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Brambleloop Studio OS</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>{_CSS}</style></head><body>
<header><h1>BRAMBLELOOP STUDIO</h1>
<div class="sub">Autonomous crochet commerce OS &middot; v{APP_VERSION} &middot; {utcnow():%Y-%m-%d %H:%M} UTC</div>
</header><main>
<div class="grid">
  <div class="card"><span>Queue pending</span><b>{st['queue'].get('pending',0)}</b></div>
  <div class="card"><span>Running</span><b>{st['queue'].get('running',0)}</b></div>
  <div class="card"><span>Dead letters</span><b>{st['dead_letters']}</b></div>
  <div class="card"><span>Certified releases</span><b>{st['certified_versions']}</b></div>
  <div class="card"><span>Open incidents</span><b>{st['open_incidents']}</b></div>
  <div class="card"><span>Agent opex</span><b>CA${st['agent_opex_cad']:.2f}</b></div>
  <div class="card"><span>Revenue</span><b>CA${st['revenue_cad']:.2f}</b></div>
  <div class="card"><span>Worker</span><b>{'live' if st['runner']['worker_alive'] else ('off' if not st['runner']['enabled'] else 'stalled')}</b></div>
  <div class="card"><span>Model providers</span><b>{len(st['model_providers']) or 'none'}</b></div>
  <div class="card"><span>Listings drafted</span><b>{_counts()['listings']}</b></div>
  <div class="card"><span>Listing images</span><b>{_counts()['listing_images']}</b></div>
  <div class="card"><span>Content pieces</span><b>{_counts()['content_pieces']}</b></div>
</div>
<div class="sub" style="color:var(--muted);font-size:12px;margin:-14px 0 18px">
Runner: {st['runner']['worker'] or 'not started'} &middot; last tick
{st['runner']['worker_last_tick'] or 'never'} &middot; restarts {st['runner']['worker_restarts']}
&middot; scheduler {st['runner']['scheduler_last_tick'] or 'never'}
{('&middot; last error: ' + st['runner']['last_error']) if st['runner']['last_error'] else ''}
</div>
{owner_html}
{command_centre}
{_block("Health", _health)}
{_block("Waiting on the owner", _approvals)}
{_block("Learning changes", _learning)}
{launch_html}
<h2>Recent jobs</h2>
{rows([(j.id, j.agent, j.job_type, _pill(j.status.value), j.attempts,
        (j.last_error or "")[:70]) for j in jobs],
      [["#", "Agent", "Job", "Status", "Tries", "Error"]], "No jobs yet.")}
<h2>Products</h2>
{rows([(p.slug, p.title, p.status, p.risk_class) for p in products],
      [["Slug", "Title", "Status", "Risk"]], "No products yet.")}
<h2>Open incidents</h2>
{rows([(i.severity, i.product_slug or "-", i.report_count, i.summary[:70],
        "HALTS" if i.halts_publication else "") for i in incidents],
      [["Sev", "Product", "Reports", "Summary", ""]], "No open incidents.")}
<h2>Spend limits</h2>
{rows([(l.scope, f"CA${l.spent_today_cad:.2f}/{l.daily_cap_cad:.2f}",
        f"CA${l.spent_lifetime_cad:.2f}/{l.lifetime_cap_cad:.2f}",
        "PAUSED" if l.paused else "ok") for l in limits],
      [["Scope", "Today", "Lifetime", "State"]], "No spend limits configured.")}
<h2>Agents</h2>
{rows([(a.name, a.authority.value, a.phase.value, f"CA${a.daily_cost_ceiling_cad:.2f}",
        "on" if a.enabled else "off") for a in agents],
      [["Agent", "Authority", "Phase", "Daily cap", ""]], "No agents.")}
<h2>Audit trail</h2>
{rows([(f"{a.at:%m-%d %H:%M}", a.actor, a.action, (a.artifact or "")[:40]) for a in audits],
      [["When", "Actor", "Action", "Artifact"]], "Nothing audited yet.")}
</main></body></html>"""


# ---------------------------------------------------------------------------
# Off-provider archive and the phone's route into the quarantined library


@app.get("/api/offsite")
def api_offsite() -> dict:
    """Whether a copy of this company exists somewhere losing this provider would not reach.

    Reports the last real round trip rather than whether the variables are set. A typed
    bucket address that is wrong survives provider loss exactly as well as no bucket at all,
    which is why the gate reads export-upload-read-back-decrypt-restore and not a string.
    """
    from ..core import offsite

    return offsite.state(db)


@app.post("/api/offsite/archive")
def api_offsite_archive(authorization: str = Header(default="")) -> JSONResponse:
    """Run the archive round trip now. Authenticated, because it writes.

    Exposed so the first archive after the credential is set does not have to wait for the
    daily cadence: the gate that opens on it is holding real work.
    """
    try:
        opsauth.check(authorization)
    except opsauth.OpsAuthUnavailable as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    except opsauth.OpsAuthRefused:
        return JSONResponse({"error": "operator credential required"}, status_code=401)

    from ..core import offsite

    record = offsite.archive(db)
    return JSONResponse(record, status_code=200 if record.get("ok") else 502)


@app.get("/api/teardown/intake")
def api_teardown_intake_plan(authorization: str = Header(default="")) -> JSONResponse:
    """The approved benchmark set with each pick's arrival state. Authenticated.

    Behind the operator credential not because the list is secret -- `/api/benchmark-selection`
    is open -- but because this one is the upload page's own state, and an upload page whose
    inventory anybody can read is one whose inventory anybody is looking at.
    """
    try:
        opsauth.check(authorization)
    except opsauth.OpsAuthUnavailable as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    except opsauth.OpsAuthRefused:
        return JSONResponse({"error": "operator credential required"}, status_code=401)

    from ..teardown import intake

    return JSONResponse(intake.plan(db))


@app.post("/api/teardown/intake")
async def api_teardown_intake(request: Request,
                              authorization: str = Header(default="")) -> JSONResponse:
    """Receive one purchase's files and generate everything derivable from them (#170).

    Multipart: `listing_ref` and one or more `files`. Nothing else is asked for, because
    everything else is already in the catalogue row that justified the purchase -- the
    seller, the department, the price, the promise and the recorded reason. A system that
    makes somebody retype what it stored is a system abandoned around purchase four.

    Zips are expanded here. Files are hashed, classified, manifested, audited against what
    the listing promised, and mirrored to the off-provider archive. The reply says whether
    that mirror happened, because on this host an upload that was not mirrored is a purchase
    that will have to be made again.

    The form is parsed manually rather than through `UploadFile` parameters so that a missing
    `python-multipart` is a 503 naming the dependency rather than an import-time crash of the
    whole application.
    """
    try:
        opsauth.check(authorization)
    except opsauth.OpsAuthUnavailable as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    except opsauth.OpsAuthRefused:
        return JSONResponse({"error": "operator credential required"}, status_code=401)

    from ..teardown.intake import IntakeRefused, receive

    try:
        form = await request.form()
    except Exception as exc:  # noqa: BLE001 - a missing parser and a bad body are both 400s
        return JSONResponse({"error": f"could not read the upload: {exc}"}, status_code=400)

    listing_ref = str(form.get("listing_ref") or "").strip()
    if not listing_ref:
        return JSONResponse({"error": "which pick this is (listing_ref) is the one thing "
                                      "intake cannot infer"}, status_code=400)

    uploads: list[tuple[str, bytes]] = []
    for item in form.getlist("files"):
        name = getattr(item, "filename", "") or ""
        if not name or not hasattr(item, "read"):
            continue
        uploads.append((name, await item.read()))
    if not uploads:
        return JSONResponse({"error": "no files were attached"}, status_code=400)

    paid = form.get("paid_cad")
    try:
        result = receive(db, listing_ref, uploads,
                         paid_cad=float(paid) if paid not in (None, "") else None)
    except IntakeRefused as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    Registry(db).audit("orchestrator", "teardown.intake_received",
                       detail={"ref": result["ref"], "files": result["file_count"],
                               "durable": result["durable"]})
    return JSONResponse(result)


@app.get("/ops/teardown", response_class=HTMLResponse)
def ops_teardown_page() -> HTMLResponse:
    """The phone page: paste the operator token once, tap a pick, choose files.

    Served without authentication because it contains no data -- every row on it is fetched
    with the token the browser holds. Deliberately one file, no build step and no framework:
    this is opened on a phone, months from now, by somebody who has just paid for thirteen
    patterns and wants them filed.
    """
    return HTMLResponse(_TEARDOWN_PAGE)


_TEARDOWN_PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brambleloop benchmark intake</title>
<style>
 :root{color-scheme:light dark}
 body{font:16px/1.5 system-ui,-apple-system,sans-serif;margin:0;padding:16px;
      max-width:720px;margin-inline:auto}
 h1{font-size:1.25rem;margin:0 0 4px}
 .sub{opacity:.7;font-size:.85rem;margin:0 0 16px}
 .warn{background:#fff4e5;color:#7a4b00;border-radius:8px;padding:10px 12px;font-size:.85rem;
       margin-bottom:12px}
 .pick{border:1px solid rgba(128,128,128,.35);border-radius:10px;padding:12px;margin-bottom:10px}
 .pick h2{font-size:.98rem;margin:0 0 4px}
 .meta{font-size:.8rem;opacity:.75;margin:0 0 8px}
 .done{opacity:.55}
 .badge{font-size:.72rem;border-radius:999px;padding:2px 8px;border:1px solid currentColor}
 input[type=password],input[type=file]{width:100%;box-sizing:border-box;padding:10px;
   border-radius:8px;border:1px solid rgba(128,128,128,.5);background:transparent;color:inherit}
 button{padding:10px 14px;border-radius:8px;border:0;background:#3c5a3f;color:#fff;
   font-size:.9rem;width:100%;margin-top:8px}
 .msg{font-size:.82rem;margin-top:8px;white-space:pre-wrap}
 a{color:inherit}
</style></head><body>
<h1>Benchmark intake</h1>
<p class="sub">Tap a pick, choose the files Etsy gave you. Zips are fine. Nothing needs
renaming, sorting or describing.</p>
<div id="auth"><p class="sub">Operator token (stored on this phone only):</p>
<input type="password" id="token" autocomplete="off" placeholder="BRAMBLELOOP_OPS_TOKEN">
<button onclick="save()">Remember and load</button></div>
<div id="status" class="msg"></div>
<div id="picks"></div>
<script>
const T=()=>localStorage.getItem('bl_ops')||'';
function save(){localStorage.setItem('bl_ops',document.getElementById('token').value.trim());load();}
function H(){return {'Authorization':'Bearer '+T()};}
async function load(){
  const s=document.getElementById('status'); s.textContent='Loading…';
  let r; try{ r=await fetch('/api/teardown/intake',{headers:H()}); }
  catch(e){ s.textContent='Could not reach the server: '+e; return; }
  if(r.status===401){ s.textContent='That token was rejected.'; return; }
  if(r.status===503){ s.textContent='No operator token is set on the server, so this page is closed.'; return; }
  const d=await r.json();
  document.getElementById('auth').style.display='none';
  s.textContent='';
  if(d.durable && !d.durable.configured){
    const w=document.createElement('div'); w.className='warn';
    w.textContent='Off-site archive not configured yet — '+d.durable.warning;
    document.getElementById('picks').before(w);
  }
  if(d.refused){ s.textContent=d.refused; return; }
  s.textContent=d.received+' of '+d.set_size+' received · expected CA$'+d.expected_cost_cad;
  const box=document.getElementById('picks'); box.innerHTML='';
  for(const p of d.picks) box.appendChild(card(p));
}
function card(p){
  const el=document.createElement('div'); el.className='pick'+(p.received?' done':'');
  const h=document.createElement('h2'); h.textContent=p.title||p.listing_ref; el.appendChild(h);
  const m=document.createElement('p'); m.className='meta';
  m.textContent='CA$'+p.price_cad+' · '+p.department+' · '+(p.received?p.files+' files received':p.answers||'');
  el.appendChild(m);
  if(p.url){const a=document.createElement('a');a.href=p.url;a.target='_blank';a.textContent='open the listing';a.className='meta';el.appendChild(a);}
  const f=document.createElement('input'); f.type='file'; f.multiple=true; el.appendChild(f);
  const b=document.createElement('button'); b.textContent=p.received?'Add more files':'Upload';
  const out=document.createElement('div'); out.className='msg';
  b.onclick=async()=>{
    if(!f.files.length){out.textContent='Choose the files first.';return;}
    b.disabled=true; out.textContent='Uploading '+f.files.length+' file(s)…';
    const fd=new FormData(); fd.append('listing_ref',p.listing_ref);
    for(const file of f.files) fd.append('files',file);
    try{
      const r=await fetch('/api/teardown/intake',{method:'POST',headers:H(),body:fd});
      const d=await r.json();
      out.textContent = r.ok
        ? d.file_count+' filed · '+d.promise_audit.verdict+(d.durable?' · archived off-site':' · NOT yet archived off-site')
        : ('Refused: '+(d.error||r.status));
      if(r.ok) setTimeout(load,1200);
    }catch(e){ out.textContent='Upload failed: '+e; }
    b.disabled=false;
  };
  el.appendChild(b); el.appendChild(out); return el;
}
if(T()) load();
</script></body></html>
"""
