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

from fastapi import FastAPI, Header
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from sqlalchemy import func, select

from ..agents.registry import Registry
from ..core.build import identity as build_identity
from ..core import opsauth
from ..core.db import Database
from ..core.models import (
    Agent, AuditLog, Collection, ContentPiece, CostEntry, Incident, Job, JobStatus,
    LedgerEntry, Listing, ListingAsset, OwnerAction, PatternVersion, Product, SpendLimit,
    SupportCase, utcnow,
)
from ..gateway.model_gateway import available_providers
from ..queue.durable import DuplicateJob, JobQueue
from ..runtime import pipeline  # noqa: F401  -- registers job handlers
from ..runtime.worker import Scheduler
from . import runner

APP_VERSION = "0.1.0"

db = Database()
app = FastAPI(title="Brambleloop Studio OS", version=APP_VERSION)


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
         "build": build_identity(), "runner": runner.STATE.to_dict()},
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
    from ..culture import radar, rapid, rights, score, translate

    return {
        "rights": rights.describe(),
        "radar": radar.sweep(db),
        "owned_territories": translate.owned_territories(),
        "primitives": dict(translate.PRIMITIVES),
        "opportunity_components": score.MEANING,
        "gates": list(score.GATES),
        "rapid_response_cell": rapid.describe(),
        "note": ("Cultural observation is demand evidence, never source material. A signal "
                 "whose rights are unclear becomes an original concept rather than a dead "
                 "opportunity, which is where the territories this company owns come from."),
    }


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
def api_seasonal_remerchandising(event: str = "Christmas") -> dict:
    """Existing certified products that could be sold into a season, and what each move needs.

    Re-merchandising never increments the catalogue, and "proven" is a claim about sales this
    company cannot make yet -- so candidates are eligible rather than proven, on every row.
    """
    from ..seasonal import remerchandising

    return remerchandising.plan(db, event=event)


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

    ceiling = monthly_ceiling_cad()
    model_spend = spent_this_month_cad(db)
    check("model_spend_within_its_ceiling",
          ceiling <= 25.0 and model_spend <= ceiling,
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

    unexpected = [j for j in dead if j.job_type != "store.publish"]
    recent = [j for j in unexpected if _aware(j.finished_at or j.created_at) >= cutoff]
    check("no_unexpected_dead_letters_in_24h", not recent,
          {"recent": sorted({j.job_type for j in recent}),
           "historical_total": len(unexpected),
           "historical_types": sorted({j.job_type for j in unexpected}),
           "expected_publish_refusals":
               sum(1 for j in dead if j.job_type == "store.publish")})

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
