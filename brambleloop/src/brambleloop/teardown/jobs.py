"""Durable, deduplicated jobs for manifested and licensed PDF purchases."""
from __future__ import annotations

from sqlalchemy import select

from ..core.models import BenchmarkLicence, BenchmarkProduct
from ..queue.durable import DuplicateJob, JobQueue
from . import licence


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
            result = queue.requeue_dead(job_types=["teardown.analyse"], ids=[exc.existing_id])
            requeued += len(result["requeued"])
    return {"queued": queued, "existing": existing, "requeued": requeued}
