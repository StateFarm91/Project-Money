"""ENG-FIRSTLIST: the owner's door from a recorded grant to the job that uses it.

Before this module a valid owner grant could not cause anything in production:

* `store.publish` is enqueued once per release by `launch.plan` (`runtime/release.py`). In
  SHADOW that job is refused and dead-lettered, and `store.publish` is a
  DELIBERATE_REFUSAL_TYPE, so `requeue_dead` never re-drives it. No route enqueued another, so
  the owner's `publication.approve` grant (24 h) expired unused.
* `store.activate` is enqueued after a verified draft with no `owner_activation_approval_id`,
  and nothing anywhere put one on a job, so `activation_authority.validate` always refused and
  no draft could ever be activated.

`queue_publication` and `queue_activation` enqueue that one job, carrying the grant id, and only
when the grant is valid *now* and the phase allows the job to act. Neither weakens a gate:
they check nothing the handler does not check again, and the handler still resolves the phase,
the kill-switch, the grant, the credential, every release gate, the PDF hashes and the images
at its own execution boundary. What they add is a refusal *before* the job exists. That is
needed because a store.publish refused in SHADOW is never re-driven and its idempotency key
stays taken. A door that enqueued under SHADOW would spend the owner's grant on a dead letter.

One job per grant (the idempotency key carries the grant id). A second press returns the job
already queued rather than queueing another, so a double tap cannot create two drafts or
charge two listing fees. Nothing here contacts Etsy, signs, spends or changes the phase.
"""
from __future__ import annotations

import os

from sqlalchemy import select

from ..core import listing_state

PUBLISH_AGENT = "store_operator"
PUBLISH_JOB = "store.publish"
ACTIVATE_JOB = "store.activate"
QUEUED_PUBLISH = "owner.publication.queued"
QUEUED_ACTIVATE = "owner.activation.queued"
KILL_SWITCH_VAR = "BRAMBLELOOP_PUBLISH_AUTHORISED"


class ExecutionRefused(ValueError):
    """The job was not queued, with the reason."""


def _phase_refusal(db) -> str | None:
    from ..core.phase import resolve
    from ..integrations.etsy import PHASES_THAT_MAY_PUBLISH

    try:
        r = resolve(db)
    except Exception as exc:  # noqa: BLE001 - an unreadable phase is no authority
        return f"the runtime phase could not be resolved ({type(exc).__name__})"
    phase = r.get("phase")
    if phase not in PHASES_THAT_MAY_PUBLISH:
        return (f"the effective runtime phase is {phase!r} (recorded {r.get('recorded_phase')!r}, "
                f"environment {r.get('env_phase')!r}); a store job queued now would be refused "
                f"and, for store.publish, never re-driven. Record the phase transition and set "
                f"BRAMBLELOOP_PHASE first")
    return None


def _kill_switch_refusal() -> str | None:
    if os.environ.get(KILL_SWITCH_VAR, "") != "1":
        return (f"{KILL_SWITCH_VAR} is not '1' in this deployment; the global publication "
                f"switch denies every store job")
    return None


def _open_job(db, job_type: str, slug: str, version: str):
    from ..core.models import Job, JobStatus

    with db.session() as s:
        for job in s.scalars(select(Job).where(
                Job.job_type == job_type,
                Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING)))):
            i = job.inputs or {}
            if i.get("slug") == slug and str(i.get("version")) == str(version):
                return job.id
    return None


def _enqueue(db, job_type: str, inputs: dict, key: str) -> tuple[int, bool]:
    from ..queue.durable import DuplicateJob, JobQueue

    try:
        job = JobQueue(db).enqueue(PUBLISH_AGENT, job_type, inputs, idempotency_key=key)
        return job.id, True
    except DuplicateJob as dup:
        return int(dup.existing_id), False


def _status(db, job_id: int) -> str:
    from ..core.models import Job

    with db.session() as s:
        job = s.get(Job, job_id)
        if job is None:
            return "missing"
        return job.status.value if hasattr(job.status, "value") else str(job.status)


def _audit(db, action: str, artifact: str, detail: dict) -> None:
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="owner:command-center", action=action, artifact=artifact[:200],
                       detail=detail))


def queue_publication(db, *, slug: str, version: str, release: str, approval_id: int,
                      actor: str = "owner") -> dict:
    """Queue the one store.publish that creates the Etsy draft for this grant.

    Refused unless the grant resolves valid now for exactly this release and content, the
    phase allows publication and the kill-switch is on. The draft is inactive and costs
    nothing on Etsy; the listing fee is charged at activation."""
    from . import publication_authority as pa

    if not slug or not version or not release:
        raise ExecutionRefused("slug, version and the certified release hash are required")
    ident = int(approval_id)
    refusal, grant = pa.resolve(db, slug=slug, version=version, release=release,
                                approval_id=ident)
    if refusal is not None:
        raise ExecutionRefused(f"owner publication grant {ident} is not usable now: {refusal}")
    for why in (_kill_switch_refusal(), _phase_refusal(db)):
        if why:
            raise ExecutionRefused(why)
    key = f"owner-publish:{slug}:{version}:{release[:24]}:{grant}"
    existing = _open_job(db, PUBLISH_JOB, slug, version)
    if existing is not None:
        return {"job_id": existing, "queued": False, "approval_id": grant,
                "why": "a store.publish job for this release is already pending or running"}
    job_id, created = _enqueue(db, PUBLISH_JOB,
                               {"slug": slug, "version": version, "release": release,
                                "owner_publication_approval_id": grant}, key)
    if created:
        _audit(db, QUEUED_PUBLISH, f"{slug}@{version}",
               {"job_id": job_id, "approval_id": grant, "release": release, "actor": actor})
    return {"job_id": job_id, "queued": created, "approval_id": grant,
            "job_status": _status(db, job_id),
            "why": ("queued: the handler re-checks the phase, the grant, the credential and "
                    "every release gate before it creates the draft" if created else
                    "this grant has already queued its store.publish job (it is not queued "
                    "twice); a further attempt needs a new grant")}


def queue_activation(db, *, slug: str, version: str, release: str, approval_id: int,
                     actor: str = "owner") -> dict:
    """Queue the one store.activate that makes the verified draft public for this grant.

    Refused unless a verified Etsy draft is recorded, the activation grant validates now for
    that listing and content, the phase allows publication and the kill-switch is on. Etsy
    charges its listing fee (US$0.20) when the listing is activated."""
    from ..core.models import Listing
    from . import activation_authority as aa

    if not slug or not version:
        raise ExecutionRefused("slug and version are required")
    ident = int(approval_id)
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version))
        listing_id = str(row.etsy_listing_id or "") if row is not None else ""
        state = row.state if row is not None else ""
    if not listing_id:
        raise ExecutionRefused("no Etsy draft is recorded for this release")
    if state == "active":
        raise ExecutionRefused(f"listing {listing_id} is already active")
    if state != listing_state.PUBLISHED:  # a verified draft only, never "live" (SECREVIEW F-4)
        raise ExecutionRefused(f"listing {listing_id} is {state!r}, not a draft whose "
                               f"read-back verified ('published'); resolve the incomplete "
                               f"draft first")
    refusal = aa.validate(db, ident, slug=slug, version=version, listing_id=listing_id,
                          release=release or "")
    if refusal is not None:
        raise ExecutionRefused(f"owner activation grant {ident} is not usable now: {refusal}")
    for why in (_kill_switch_refusal(), _phase_refusal(db)):
        if why:
            raise ExecutionRefused(why)
    existing = _open_job(db, ACTIVATE_JOB, slug, version)
    if existing is not None:
        return {"job_id": existing, "queued": False, "approval_id": ident,
                "etsy_listing_id": listing_id,
                "why": "a store.activate job for this release is already pending or running"}
    job_id, created = _enqueue(db, ACTIVATE_JOB,
                               {"slug": slug, "version": version, "release": release or "",
                                "owner_activation_approval_id": ident},
                               f"owner-activate:{listing_id}:{ident}")
    if created:
        _audit(db, QUEUED_ACTIVATE, f"{slug}@{version}",
               {"job_id": job_id, "approval_id": ident, "etsy_listing_id": listing_id,
                "actor": actor})
    return {"job_id": job_id, "queued": created, "approval_id": ident,
            "etsy_listing_id": listing_id,
            "job_status": _status(db, job_id),
            "why": ("queued: the handler reads the draft back, re-checks every gate, the "
                    "grant and the daily ceiling, then activates" if created else
                    "this grant has already queued its store.activate job (it is not queued "
                    "twice); a further attempt needs a new grant")}
