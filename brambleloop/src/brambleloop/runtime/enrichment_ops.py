"""The job that runs `creative.enrichment_requests.sweep` (crochet_engineer).

Hourly. A brief the construction registry held for research enrichment becomes one precise,
deduplicated request for Research (W-CONCEPT answers it through `enrichment_requests.answer`).
CA$0, deterministic, never drafts or publishes by itself.
"""
from __future__ import annotations

from .worker import JobContext, handlers


def _transaction_audit(ctx, action, *, artifact, detail, session):
    from ..core.models import AuditLog
    session.add(AuditLog(actor=ctx.job.agent, action=action, artifact=artifact,
                         job_id=ctx.job.id, phase=ctx.phase, detail=detail))


def _transaction_lease(ctx, session, job_type, inputs):
    from sqlalchemy import select
    from ..core.models import Job, JobStatus, utcnow
    from ..queue.effects import LeaseLost

    token = getattr(ctx.job, "lease_token", None)
    job = session.scalar(select(Job).where(Job.id == ctx.job.id).with_for_update())
    expires = job.lease_expires_at if job is not None else None
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=utcnow().tzinfo)
    if (not token or job is None or job.status != JobStatus.RUNNING
            or job.lease_token != token or not job.leased_by
            or job.leased_by != ctx.job.leased_by
            or job.agent != "crochet_engineer" or ctx.job.agent != job.agent
            or job.job_type != job_type or job.inputs != inputs
            or expires is None or expires <= utcnow()):
        raise LeaseLost("enrichment worker lease is no longer current")


@handlers.register("research.enrichment_sweep")
def handle_enrichment_sweep(ctx: JobContext) -> dict:
    from ..creative import enrichment_producer as producer
    from ..creative import enrichment_requests as er

    out = er.sweep(ctx.db, audit=ctx.audit,
                   audit_transaction=lambda *a, **kw: _transaction_audit(ctx, *a, **kw),
                   validate_transaction=lambda s: _transaction_lease(
                       ctx, s, "research.enrichment_sweep", ctx.job.inputs or {}))
    # A4B-2: the production answer side. It queues an answer only when the authoritative
    # seed now passes the construction that refused it; the answer job does the rest.
    produced = producer.produce(ctx.db, enqueue=ctx.enqueue)
    out["answers"] = produced
    out["work_done"] = int(out.get("work_done", 0)) + len(produced["answers_queued"])
    return out


@handlers.register("research.enrichment_answer")
def handle_enrichment_answer(ctx: JobContext) -> dict:
    """Process an already-authorized research answer with durable audit state."""
    from ..creative import enrichment_requests as er
    from . import lineage

    inputs = ctx.job.inputs or {}
    slug, payload = inputs.get("slug"), inputs.get("payload")
    brief = inputs.get("brief")
    if not isinstance(slug, str) or not slug or not isinstance(payload, dict):
        return {"accepted": False, "why": "answer requires a slug and structured payload"}
    if brief is not None and not isinstance(brief, dict):
        return {"accepted": False, "why": "brief must be structured"}
    lineage.ensure_table(ctx.db)

    def transaction_queue(agent, job_type, data, *, session, **kw):
        child = ctx.enqueue(agent, job_type, data, session=session, **kw)
        if child is not None:
            session.add(lineage.JobLink(parent_id=ctx.job.id, child_id=child.id,
                                        parent_type=ctx.job.job_type, child_type=job_type))
        return child

    return er.answer(ctx.db, slug, payload, brief, audit=ctx.audit, enqueue=ctx.enqueue,
                     audit_transaction=lambda *a, **kw: _transaction_audit(ctx, *a, **kw),
                     enqueue_transaction=transaction_queue,
                     validate_transaction=lambda s: _transaction_lease(
                         ctx, s, "research.enrichment_answer", inputs))
