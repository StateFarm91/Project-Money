"""eng/mc-perf: a production-shaped database for the Mission Control route-timing harness.

Builds on `_evidence_seed` (products with release histories, provenance, incidents, parked
runs) and adds the tables the owner's pages read at scale: thousands of jobs and audit rows,
paid-call records, cost entries, and stored binary blobs (durable artifacts and continuity
archives) so any route that reads a blob column by accident pays for it here, as in
production.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import _evidence_seed


def seed(db, *, now: datetime, jobs: int = 20_000, audits: int = 30_000,
         paid_calls: int = 5_000, costs: int = 8_000, blobs: int = 24,
         blob_kb: int = 1024, archives: int = 3, archive_mb: int = 8) -> dict:
    from sqlalchemy import insert

    from brambleloop.core.models import (AuditLog, ContinuityArchive, CostEntry,
                                         DurableArtifact, Job, JobStatus)
    from brambleloop.gateway.paid_calls import PaidCallRecord

    out = _evidence_seed.seed(db, now=now, jobs=jobs, audits=audits)
    with db.session() as s:
        rows = [{"key": f"pc-{n:06d}", "effect": "anthropic.messages", "job_id": n % 5000,
                 "job_type": "listing.seo", "fingerprint": f"{n:064x}"[-64:],
                 "outcome": ("SUCCEEDED", "FAILED", "PENDING")[n % 3] if n % 50 else "PENDING",
                 "estimate_cad": 0.01, "cost_kind": "model", "provider": "anthropic",
                 "model": "m", "agent": "a", "payload": {"n": n, "pad": "p" * 200},
                 "at": now - timedelta(minutes=n), "updated_at": now}
                for n in range(paid_calls)]
        for k in range(0, len(rows), 2000):
            s.execute(insert(PaidCallRecord), rows[k:k + 2000])
        crow = [{"agent": "a", "kind": "model", "amount_cad": 0.002, "detail": {"n": n},
                 "at": now - timedelta(minutes=7 * n)} for n in range(costs)]
        cols = {c.name for c in CostEntry.__table__.columns}
        crow = [{k: v for k, v in r.items() if k in cols} for r in crow]
        for k in range(0, len(crow), 2000):
            s.execute(insert(CostEntry), crow[k:k + 2000])
        for n in range(blobs):
            s.add(DurableArtifact(sha256=f"{n:064x}", content_type="image/png",
                                  bytes_len=blob_kb * 1024, payload=os.urandom(blob_kb * 1024),
                                  why_kept="perf seed"))
        for n in range(archives):
            import hashlib
            blob = os.urandom(archive_mb * 1024 * 1024)
            s.add(ContinuityArchive(at=now - timedelta(hours=n), digest=f"{n:064x}",
                                    payload_sha256=hashlib.sha256(blob).hexdigest(),
                                    payload=blob, raw_bytes=len(blob), stored_bytes=len(blob),
                                    total_rows=1, source="perf seed"))
        s.commit()
    out.update(paid_calls=paid_calls, costs=costs, blobs=blobs, archives=archives)
    return out
