"""W4-LISTREADY (R3, R5): releases the chain stopped driving, re-driven through the normal gates.

Production (read 2026-10-20, b931d17) showed two ways a release falls out of the chain for
good, and neither is a gate refusing it:

* **R3, a halted certification is never retried.** `gate.certify` halts while a P0/P1 incident
  is open against the product (Gate E, unchanged here). The halted job keeps its idempotency
  key, and so do the `cir.draft` and `cir.compile` jobs before it, so once the incident is
  resolved nothing can enqueue that certification again. nordic-star-ornaments@1.5.0 and
  mosaic-placemat-pair@1.4.0 were halted on 2026-10-20T10:02Z this way.
* **R5, six Launch-0 releases were never drafted at all.** `chain.rebuild` redrafts only slugs
  that already have a certified release, so the three basket sizes, the hexagon coaster set,
  the Nordic Forest baby blanket and the key basket never entered the chain in production.

Both are answered here, deterministically and idempotently:

* `retry_halted` re-enqueues the halted `gate.certify` with the same CIR, keyed on the halt
  that stopped it (`certify-after-halt:<slug>:<version>:<halt audit id>`). One retry per halt
  episode; never while the product is still halted (the same `publication_halted` predicate
  `gate.certify` applies); never once a later certify outcome is on record.
* `seed_launch0` enqueues `cir.draft` for every Launch-0 release whose code version has no
  certified release, keyed on the design's fingerprint and the document version, so it runs
  once per design. Drafting, compiling and certifying are the normal jobs with their normal
  gates; nothing here certifies, lists or publishes anything.
"""
from __future__ import annotations

HALTED = "gate.halted"
# A certify attempt that reached a decision: a later one of these ends a halt episode.
OUTCOMES = ("gate.certified", "gate.blocked", "gate.version_conflict")
RETRY_PREFIX = "certify-after-halt"
SEED_PREFIX = "launch0-seed"


def halted_releases(db) -> list[dict]:
    """Every release whose latest certify attempt was halted and not decided since.

    Returns [{artifact, slug, version, halt_audit_id, job_id}], oldest halt first."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    latest_halt: dict[str, tuple[int, int | None]] = {}
    latest_outcome: dict[str, int] = {}
    with db.session() as s:
        for row_id, action, artifact, job_id in s.execute(
                select(AuditLog.id, AuditLog.action, AuditLog.artifact, AuditLog.job_id)
                .where(AuditLog.action.in_((HALTED,) + OUTCOMES))):
            if not artifact or "@" not in artifact:
                continue
            if action == HALTED:
                if row_id > latest_halt.get(artifact, (-1, None))[0]:
                    latest_halt[artifact] = (row_id, job_id)
            elif row_id > latest_outcome.get(artifact, -1):
                latest_outcome[artifact] = row_id
    out = []
    for artifact, (halt_id, job_id) in latest_halt.items():
        if latest_outcome.get(artifact, -1) > halt_id:
            continue
        slug, _, version = artifact.partition("@")
        out.append({"artifact": artifact, "slug": slug, "version": version,
                    "halt_audit_id": halt_id, "job_id": job_id})
    return sorted(out, key=lambda r: r["halt_audit_id"])


def retry_key(slug: str, version: str, halt_audit_id: int) -> str:
    return f"{RETRY_PREFIX}:{slug}:{version}:{halt_audit_id}"


def _certified_versions(db, slug: str) -> list[str]:
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    with db.session() as s:
        return [v for (v,) in s.execute(
            select(PatternVersion.version).join(Product,
                                                PatternVersion.product_id == Product.id)
            .where(Product.slug == slug, PatternVersion.certified == True))]  # noqa: E712


def newer_certified(db, slug: str, version: str) -> list[str]:
    """Certified versions of `slug` above `version` (review F2); unorderable ones count as
    newer, so an older release is never re-certified past a release nobody can place."""
    from ..ops.artefacts import version_key

    mine = version_key(version)
    out = []
    for v in _certified_versions(db, slug):
        k = version_key(v)
        if v != version and (mine is None or k is None or k > mine):
            out.append(v)
    return sorted(out)


def design_check(slug: str, version: str, recorded: dict) -> str:
    """"" when the recorded CIR is still exactly the design the code defines for this
    slug@version (review F3), else why not."""
    import json

    from ..cir.model import CIR
    from .pipeline import _engineered_cir

    try:
        code = _engineered_cir(slug)
    except Exception as exc:  # noqa: BLE001 - a design that no longer builds is not retried
        return f"the code's design for {slug} does not build ({type(exc).__name__})"
    if code is None:
        return f"the code defines no design for {slug}"
    if code.version != version:
        return (f"the code's design for {slug} is now {code.version}, not {version}; the "
                f"halted release is not re-certified")
    try:
        rec = CIR.from_dict(recorded)
    except Exception as exc:  # noqa: BLE001 - an unreadable record is not certified
        return f"the recorded CIR is unreadable ({type(exc).__name__})"
    normal = json.loads(json.dumps(code.to_dict(), default=str))
    if rec.fingerprint != code.fingerprint or normal != json.loads(json.dumps(recorded,
                                                                              default=str)):
        return (f"the design moved during the halt: the recorded CIR for {slug}@{version} is "
                f"not the code's current design; it is not re-certified")
    return ""


def certify_in_flight(db, slug: str, version: str, *, except_key: str | None = None) -> list[int]:
    """Unfinished `gate.certify` jobs for exactly this slug@version (review F5)."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    out = []
    with db.session() as s:
        for j in s.scalars(select(Job).where(
                Job.job_type == "gate.certify",
                Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED)))):
            cir = (j.inputs or {}).get("cir") or {}
            if except_key and j.idempotency_key == except_key:
                continue
            if cir.get("slug") == slug and cir.get("version") == version:
                out.append(j.id)
    return out


def retry_halted(ctx) -> dict:
    """R3: re-enqueue each halted certification once its halt has cleared, once per episode.

    Not retried, with the reason recorded (`skipped`), when (review F2, F3, F5):
    a newer release of the slug is certified; the recorded CIR is no longer the design the
    code defines for that slug@version; or a `gate.certify` for it is already queued or
    running."""
    from ..core.models import Job
    from ..gates.incidents import IncidentTracker

    tracker = IncidentTracker(ctx.db)
    me = getattr(getattr(ctx, "job", None), "id", None)
    retried, still_halted, unreadable, already = [], [], [], []
    skipped: dict[str, str] = {}
    for r in halted_releases(ctx.db):
        if tracker.publication_halted(r["slug"]):
            still_halted.append(r["artifact"])
            continue
        inputs = None
        if r["job_id"] is not None:
            with ctx.db.session() as s:
                job = s.get(Job, r["job_id"])
                inputs = dict(job.inputs or {}) if job is not None else None
        if not inputs or not isinstance(inputs.get("cir"), dict):
            unreadable.append(r["artifact"])       # no CIR on record: nothing is guessed
            continue
        newer = newer_certified(ctx.db, r["slug"], r["version"])
        if newer:
            skipped[r["artifact"]] = f"superseded_by_newer: {newer} certified"
            continue
        moved = design_check(r["slug"], r["version"], inputs["cir"])
        if moved:
            skipped[r["artifact"]] = f"design_moved: {moved}"
            continue
        key = retry_key(r["slug"], r["version"], r["halt_audit_id"])
        flying = [j for j in certify_in_flight(ctx.db, r["slug"], r["version"], except_key=key)
                  if j != me]
        if flying:
            skipped[r["artifact"]] = f"certify_in_flight: job(s) {flying}"
            continue
        job = ctx.enqueue("quality_director", "gate.certify", inputs, idempotency_key=key)
        (retried if job is not None else already).append(r["artifact"])
    if skipped:
        ctx.audit("certify.retry_skipped", detail={"skipped": skipped})
    return {"retried": retried, "still_halted": still_halted,
            "already_retried": already, "no_cir_on_record": unreadable, "skipped": skipped}


def launch0_releases() -> list:
    """(cir) for every Launch-0 release the code defines, in listing order."""
    from ..products import launch0 as l0

    out = []
    for slug in l0.LAUNCH0_SLUGS:
        for v in l0.candidate(slug).variants:
            out.append(l0.cir_for(v.build))
    return out


def seed_key(slug: str, version: str, fingerprint: str, doc_version) -> str:
    return f"{SEED_PREFIX}:{slug}:{version}:{fingerprint}:d{doc_version}"


# One release per whole-catalogue `chain.rebuild` (hourly in production): each seeded draft runs
# the full chain (compile, certify, assets, listing), so the ten are trickled in over about ten
# hours rather than queued as one burst on the shared worker.
SEED_PER_RUN = 1

# P0-NEXT-PRODUCT (owner goal L4): Launch-0 seeding starts a new product only while fewer than
# WIP_LIMIT product chains are in flight (a fixed work-in-progress count, review L4 L4). A
# product's chain is "in flight" while one of its chain-stage jobs is RUNNING, or is PENDING /
# FAILED (retry) and due within IN_FLIGHT_HORIZON. A job parked further ahead -- a seasonal
# re-plan `chain_successors.launch_held` schedules for the day after a missed occasion, up to a
# year away (review L4 H1) -- is waiting on the calendar, not occupying the worker, so it holds
# no slot. Finished, dead-lettered and cancelled jobs hold nothing: a held or dead-ended
# product never blocks the next one.
#
# Scope (review L4 M1): the limit governs this autonomous Launch-0 seeding only. Drafts other
# producers enqueue (radar.score's `draft:<slug>`, redrafts) are not gated here; they are
# COUNTED as in flight, so seeding never adds to a worker they already fill.
CHAIN_STAGE_JOBS = ("cir.draft", "cir.compile", "cir.revise", "cir.reengineer",
                    "gate.certify", "listing.draft", "assets.build", "assets.physical_upgrade",
                    "visual.image_production", "pricing.position", "listing.seo",
                    "launch.plan")
WIP_LIMIT = 2
IN_FLIGHT_HORIZON_HOURS = 6


def _job_slug(inputs: dict) -> str | None:
    inputs = inputs or {}
    return inputs.get("slug") or (inputs.get("cir") or {}).get("slug")


def _aware(value):
    from datetime import timezone

    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def idle_capacity(db, *, limit: int = WIP_LIMIT, now=None) -> dict:
    """How many product chains are in flight now, and how many WIP slots are free.

    Deterministic: a pure read of the durable queue. `in_flight` names each product with a
    chain-stage job RUNNING, or PENDING / FAILED (retry) due within IN_FLIGHT_HORIZON_HOURS;
    `parked` names jobs scheduled further ahead, which hold no slot. `slots` is what is left
    of `limit`. A chain job with no readable slug counts as one unnamed product, never zero."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    now = _aware(now) or datetime.now(timezone.utc)
    horizon = now + timedelta(hours=IN_FLIGHT_HORIZON_HOURS)
    live = (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED)
    busy: dict[str, list] = {}
    parked: list[str] = []
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type.in_(CHAIN_STAGE_JOBS),
                                             Job.status.in_(live)).order_by(Job.id)):
            key = _job_slug(j.inputs) or f"(unnamed job {j.id})"
            due = _aware(j.run_after)
            if j.status != JobStatus.RUNNING and due is not None and due > horizon:
                parked.append(f"{key}:{j.job_type}#{j.id}@{due.date().isoformat()}")
                continue
            busy.setdefault(key, []).append(f"{j.job_type}#{j.id}:{j.status.value}")
    slots = max(0, limit - len(busy))
    return {"limit": limit, "in_flight": sorted(busy), "jobs": busy, "slots": slots,
            "idle": slots > 0, "parked": parked}


EXHAUSTED_SIGNATURE = "catalogue-exhausted:launch0"


def _signal_exhausted(ctx, *, already: list, certified: list) -> None:
    """Review L4 L4: an owner-VISIBLE signal (an open, non-halting incident on the Command
    Center) that the release registry has nothing left to feed the chain. Not an owner card:
    adopting a new product into the registry is an integrator code change, not an owner
    action. One open row, restated, never duplicated."""
    from sqlalchemy import select

    from ..core.models import Incident

    summary = (f"Launch-0 seeding is exhausted: {len(certified)} release(s) certified and "
               f"{len(already)} seeded; the chain has no further eligible product until a new "
               f"one is adopted into the release registry (builder.CATALOGUE / "
               f"RELEASE_VERSIONS), an integrator code change")
    with ctx.db.session() as s:
        row = s.scalar(select(Incident).where(Incident.signature == EXHAUSTED_SIGNATURE,
                                              Incident.resolved.is_(False)))
        if row is None:
            s.add(Incident(severity="P3", product_slug=None, signature=EXHAUSTED_SIGNATURE,
                           summary=summary, halts_publication=False,
                           detail={"certified": certified[:20], "seeded": already[:20]}))
        else:
            row.summary = summary
            row.report_count = (row.report_count or 1) + 1


def seed_launch0(ctx, *, limit: int = SEED_PER_RUN, wip_limit: int = WIP_LIMIT) -> dict:
    """R5: draft the next Launch-0 release whose code version is not certified, once per design.

    In listing order; a release already seeded under this design is skipped (its key is taken),
    so the next run seeds the next one. `pending` names what is left.

    P0-NEXT-PRODUCT: only into idle capacity (`idle_capacity`). With no free slot nothing is
    seeded and `held_for_capacity` names the products in flight; the next run after a chain
    finishes (or dead-letters) seeds the next eligible release. `exhausted` is True when no
    Launch-0 release is left to seed or waiting: the chain cannot feed itself further from the
    release registry, and adopting a new product into it is a code change (integrator)."""
    from sqlalchemy import select

    from ..core.models import Job, PatternVersion, Product
    from ..gates.certificate import DOC_VERSION

    from ..queue.durable import fit_idempotency_key

    capacity = idle_capacity(ctx.db, limit=wip_limit)
    limit = min(limit, capacity["slots"])
    in_flight_here: list[str] = []
    stopped = False
    with ctx.db.session() as s:
        certified = {(slug, version) for slug, version in s.execute(
            select(Product.slug, PatternVersion.version)
            .join(PatternVersion, PatternVersion.product_id == Product.id)
            .where(PatternVersion.certified == True))}  # noqa: E712
    seeded, present, already, pending = [], [], [], []
    for cir in launch0_releases():
        rel = f"{cir.slug}@{cir.version}"
        if (cir.slug, cir.version) in certified:
            present.append(rel)
            continue
        if newer_certified(ctx.db, cir.slug, cir.version):
            present.append(f"{rel} (a newer release is certified; not seeded)")
            continue
        key = seed_key(cir.slug, cir.version, cir.fingerprint, DOC_VERSION)
        with ctx.db.session() as s:          # review L4 L3: the key as the queue stores it
            taken = s.scalar(select(Job.id).where(
                Job.idempotency_key == fit_idempotency_key(key))) is not None
        if taken:                         # seeded before, whatever the capacity is now
            already.append(rel)
            continue
        if cir.slug in capacity["in_flight"]:
            # review L4 M2: this product's chain is already running (a radar draft, a
            # redraft): a second cir.draft would take a second slot for the same product.
            in_flight_here.append(rel)
            continue
        if len(seeded) >= limit or stopped:
            pending.append(rel)
            continue
        job = ctx.enqueue("crochet_engineer", "cir.draft", {"slug": cir.slug},
                          idempotency_key=key)
        if job is None:
            # review L4 L2: a concurrent duplicate took the key between the read and the
            # enqueue. Stop seeding this run rather than spend the slot on the next release.
            already.append(rel)
            stopped = True
            continue
        seeded.append(rel)
    exhausted = not seeded and not pending and not in_flight_here
    if exhausted:
        _signal_exhausted(ctx, already=already, certified=present)
    held = None if capacity["idle"] or not pending else {
        "in_flight": capacity["in_flight"], "limit": capacity["limit"],
        "why": (f"{len(capacity['in_flight'])} product chain(s) in flight, at the work-in-"
                f"progress limit {capacity['limit']}: the next release is seeded once one "
                f"finishes")}
    return {"seeded": seeded, "certified": present, "already_seeded": already,
            "pending": pending, "in_flight_already": in_flight_here,
            "capacity": {k: capacity[k] for k in
                         ("limit", "in_flight", "slots", "idle", "parked")},
            "held_for_capacity": held,
            "exhausted": exhausted,
            "exhausted_why": None if not exhausted else (
                "every Launch-0 release is certified, superseded or already seeded; a further "
                "product enters the chain only once it is adopted into the release registry "
                "(builder.CATALOGUE / RELEASE_VERSIONS), an integrator code change")}


def duplicate_certification(db, job, cir) -> str:
    """Review F5: why this `gate.certify` job would only repeat a certification that landed
    after it was queued, or "". Identical content (the stored release's CIR and document
    version equal this job's) certified by another job since this one was created: running it
    again would only re-certify the same release. Anything else -- different content, an older
    certification, unreadable state -- is not a duplicate, and the job runs as before."""
    import json

    from sqlalchemy import select

    from ..core.models import AuditLog, PatternVersion, Product
    from ..gates.certificate import DOC_VERSION

    created = getattr(job, "created_at", None)
    if created is None:
        return ""
    try:
        with db.session() as s:
            pv = s.scalar(select(PatternVersion).join(
                Product, PatternVersion.product_id == Product.id).where(
                Product.slug == cir.slug, PatternVersion.version == cir.version,
                PatternVersion.certified == True))  # noqa: E712
            if pv is None:
                return ""
            if (pv.certificate or {}).get("doc_version") != DOC_VERSION:
                return ""
            if pv.cir_json != json.loads(json.dumps(cir.to_dict(), default=str)):
                return ""
            later = s.scalar(select(AuditLog).where(
                AuditLog.action == "gate.certified",
                AuditLog.artifact == f"{cir.slug}@{cir.version}",
                AuditLog.at > created,
                AuditLog.job_id != getattr(job, "id", None)).order_by(AuditLog.id.desc()))
            if later is None:
                return ""
            return (f"{cir.slug}@{cir.version} was certified with identical content by job "
                    f"{later.job_id} after this job was queued")
    except Exception:  # noqa: BLE001 - unreadable is not a duplicate: certify as before
        return ""


# ---- delta review N3: a live listing of a superseded release ---------------------------------

SUPERSEDED_LIVE = "listing.superseded_live:"


def superseded_live_listings(db) -> dict:
    """Raise (and restate) one owner-visible P2 per live listing whose release is not the
    product's newest certified release; resolve it when that stops holding.

    Since R1 an older release's artefacts read `superseded` and raise no halt, which is right
    for drafts -- publication refuses a superseded release -- but a listing already *live* on
    Etsy keeps selling the old release and auto-renews. Nothing here changes the listing: the
    owner decides (update it to the newest release, or deactivate it). Never halting: the
    newest release's own publication is unaffected (product independence)."""
    from sqlalchemy import select

    from ..core.models import Listing, Product
    from ..ops import incident_lifecycle as lifecycle
    from ..ops.artefacts import newest_release

    opened, held, resolved = [], [], []
    # Final review R4: "live" is what Etsy shows, not only our row. The latest listing census
    # (getListingsByShop per state) marks a listing of ours active even when the local row
    # says otherwise; both sources are read and merged per slug@version.
    candidates: dict[tuple[str, str], dict] = {}
    try:
        from .etsy_ops import CENSUS_READING, latest_reading

        census = latest_reading(db, CENSUS_READING) or {}
        for r in census.get("estate") or []:
            if r.get("ours") and r.get("state") == "active" and r.get("slug") \
                    and r.get("version"):
                candidates.setdefault((r["slug"], r["version"]), {
                    "etsy_listing_id": r.get("listing_id"), "listing_id": None,
                    "source": "etsy listing census (state active)",
                    "should_auto_renew": r.get("should_auto_renew")})
    except Exception:  # noqa: BLE001 - an unreadable census adds nothing; the rows still do
        pass
    with db.session() as s:
        for row in s.scalars(select(Listing).where(Listing.state == "active")):
            candidates.setdefault((row.product_slug, row.version), {
                "etsy_listing_id": row.etsy_listing_id, "listing_id": row.id,
                "source": "local listing row (state active)"})
        holding = set()
        for (slug, version), info in sorted(candidates.items()):
            product = s.scalar(select(Product).where(Product.slug == slug))
            newest = newest_release(s, product.id) if product is not None else None
            if newest is None or newest.version == version:
                continue
            row = type("Live", (), {"product_slug": slug, "version": version,
                                    "id": info["listing_id"],
                                    "etsy_listing_id": info["etsy_listing_id"]})
            sig = f"{SUPERSEDED_LIVE}{row.product_slug}@{row.version}"
            holding.add(sig)
            _, new = lifecycle.open_or_restate(
                s, signature=sig, severity="P2", product_slug=None, halts_publication=False,
                summary=(f"{row.product_slug}@{row.version} is live on Etsy, but the newest "
                         f"certified release is {newest.version}: buyers get the older "
                         f"pattern and Etsy may auto-renew it. Owner decision: update the "
                         f"listing to {newest.version}, or deactivate it"),
                detail={"listing_id": row.id, "etsy_listing_id": row.etsy_listing_id,
                        "live_version": row.version, "newest": newest.version,
                        "source": info["source"],
                        "should_auto_renew": info.get("should_auto_renew")})
            (opened if new else held).append(sig)
        from ..core.models import Incident

        stale = [i.signature for i in s.scalars(select(Incident).where(
            Incident.signature.like(f"{SUPERSEDED_LIVE}%"), Incident.resolved.is_(False)))
            if i.signature not in holding]
        if stale:
            resolved = lifecycle.resolve_signatures(
                s, stale, resolution="no live listing of a superseded release remains")
    return {"opened": opened, "held": held, "resolved": resolved}
