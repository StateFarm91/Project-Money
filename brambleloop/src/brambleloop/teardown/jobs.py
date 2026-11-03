"""Durable, deduplicated jobs for manifested and licensed PDF purchases."""
from __future__ import annotations

from sqlalchemy import select

from ..core.models import (BenchmarkAnalysis, BenchmarkLicence, BenchmarkProduct,
                           BenchmarkTechniqueObservation)
from ..queue.durable import DuplicateJob, JobQueue
from . import licence

MAX_AUTOMATIC_REDRIVES = 2


def enqueue_technique_supplement(db, analysis_id: int) -> dict:
    """Queue one additive extraction for historical evidence, without editing it."""
    from .analysis_store import (TECHNIQUE_EXTRACTOR_VERSION, manifested_pdf,
                                 needs_technique_supplement, technique_extractor_digest)
    from .review import evidence_digest

    with db.session() as s:
        source = s.get(BenchmarkAnalysis, analysis_id)
        extractor_sha256 = technique_extractor_digest()
        if source is None or not needs_technique_supplement(source, extractor_sha256=extractor_sha256):
            return {"queued": 0, "existing": 0, "reason": "not_needed"}
        product = s.get(BenchmarkProduct, source.benchmark_id)
        if not manifested_pdf(product, source.file_sha256):
            return {"queued": 0, "existing": 0, "reason": "source_unavailable"}
        terms = s.scalar(select(BenchmarkLicence).where(BenchmarkLicence.source_ref == product.ref))
        if terms is None or "private_analysis" not in (terms.allowed_uses or []) \
                or "private_analysis" in (terms.prohibited_uses or []):
            return {"queued": 0, "existing": 0, "reason": "licence_refused"}
        digest = evidence_digest(source)
        existing = s.scalar(select(BenchmarkTechniqueObservation.id).where(
            BenchmarkTechniqueObservation.analysis_id == analysis_id,
            BenchmarkTechniqueObservation.extractor_version == TECHNIQUE_EXTRACTOR_VERSION,
            BenchmarkTechniqueObservation.extractor_sha256 == extractor_sha256,
            BenchmarkTechniqueObservation.source_digest == digest))
        if existing is not None:
            return {"queued": 0, "existing": 1, "reason": "observation_exists"}
    queue = JobQueue(db)
    try:
        queue.enqueue("orchestrator", "teardown.analyse", {
            "mode": "technique_supplement", "analysis_id": analysis_id, "source_digest": digest,
            "extractor_sha256": extractor_sha256}, idempotency_key=(
                f"teardown:technique:{TECHNIQUE_EXTRACTOR_VERSION}:{analysis_id}:{digest}:{extractor_sha256}"))
        return {"queued": 1, "existing": 0, "requeued": 0}
    except DuplicateJob as exc:
        result = queue.requeue_dead(job_types=["teardown.analyse"], ids=[exc.existing_id],
                                    max_automatic_redrives=MAX_AUTOMATIC_REDRIVES)
        return {"queued": 0, "existing": 1, "requeued": len(result["requeued"])}


def enqueue_purchase(db, benchmark_id: int) -> dict:
    with db.session() as s:
        product = s.get(BenchmarkProduct, benchmark_id)
        if product is None:
            return {"queued": 0, "existing": 0}
        recorded = s.scalar(select(BenchmarkLicence.id).where(
            BenchmarkLicence.source_ref == product.ref))
        files = list(product.files or [])
        ref = product.ref
    # Conservative default terms permit private analysis, but automatic work
    # starts only after the purchase's licence has actually been recorded.
    if recorded is None:
        return {"queued": 0, "existing": 0, "reason": "licence_not_recorded"}
    try:
        licence.refuse_unless_permitted(db, ref, "private_analysis")
    except licence.LicenceRefused:
        return {"queued": 0, "existing": 0, "reason": "licence_refused"}
    queue = JobQueue(db)
    queued = existing = requeued = 0
    for item in files:
        sha = item.get("sha256") or ""
        if not str(item.get("name") or "").lower().endswith(".pdf"):
            continue
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            continue
        try:
            queue.enqueue("orchestrator", "teardown.analyse",
                          {"benchmark_id": benchmark_id, "file_sha256": sha},
                          idempotency_key=f"teardown:{benchmark_id}:{sha}")
            queued += 1
        except DuplicateJob as exc:
            existing += 1
            result = queue.requeue_dead(job_types=["teardown.analyse"], ids=[exc.existing_id],
                                        max_automatic_redrives=MAX_AUTOMATIC_REDRIVES)
            requeued += len(result["requeued"])
    return {"queued": queued, "existing": existing, "requeued": requeued}
