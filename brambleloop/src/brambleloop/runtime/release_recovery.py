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


def retry_halted(ctx) -> dict:
    """R3: re-enqueue each halted certification once its halt has cleared, once per episode."""
    from ..core.models import Job
    from ..gates.incidents import IncidentTracker

    tracker = IncidentTracker(ctx.db)
    retried, still_halted, unreadable, already = [], [], [], []
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
        job = ctx.enqueue("quality_director", "gate.certify", inputs,
                          idempotency_key=retry_key(r["slug"], r["version"],
                                                    r["halt_audit_id"]))
        (retried if job is not None else already).append(r["artifact"])
    return {"retried": retried, "still_halted": still_halted,
            "already_retried": already, "no_cir_on_record": unreadable}


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


def seed_launch0(ctx, *, limit: int = SEED_PER_RUN) -> dict:
    """R5: draft the next Launch-0 release whose code version is not certified, once per design.

    In listing order; a release already seeded under this design is skipped (its key is taken),
    so the next run seeds the next one. `pending` names what is left."""
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product
    from ..gates.certificate import DOC_VERSION

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
        if len(seeded) >= limit:
            pending.append(rel)
            continue
        job = ctx.enqueue("crochet_engineer", "cir.draft", {"slug": cir.slug},
                          idempotency_key=seed_key(cir.slug, cir.version, cir.fingerprint,
                                                   DOC_VERSION))
        (seeded if job is not None else already).append(rel)
    return {"seeded": seeded, "certified": present, "already_seeded": already,
            "pending": pending}
