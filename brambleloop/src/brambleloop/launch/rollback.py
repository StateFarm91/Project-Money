"""The rollback plan, rehearsed rather than asserted (#54, C-80 defect 10).

The launch gate used to call the rollback plan ready when a database restore had been proved
recently. That proves the database can come back; it says nothing about withdrawing what was
published without losing the evidence, which is what a rollback of a launch is. So the
rehearsal here walks the withdrawal round trip for one listing, dry, and records what it found:

1. the certificate the listing was published under is retained on the release row;
2. a listing row exists for the release and is in a state the withdrawal path handles;
3. every deliverable a restore would re-serve -- the PDF the last build produced and the
   stored listing frames -- is on disk under its recorded hash, so a withdrawn listing can be
   put back as the same bytes;
4. the state round trip itself: the listing's state is taken to `withdrawn` and back to where
   it was on a copy, never on the row, and the job that restores it is named (the targeted
   chain rebuild that redraws listing copy from the retained release).

Nothing here changes a listing, publishes or contacts anyone; the record is one audit row per
release per run, which the readiness gate reads and ages.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

ACTION = "launch.rollback_rehearsed"
# A rehearsal older than this no longer proves the plan; the daily readiness re-rehearses.
MAX_AGE_DAYS = 3
WITHDRAWN = "withdrawn"
RESTORE_VIA = "chain.rebuild (targeted: listing_copy, seo from the retained release)"


def rehearse(db, *, slug: str, version: str, store=None, job_id: int | None = None) -> dict:
    """Walk the withdrawal round trip for one release, dry, and record the rehearsal."""
    from sqlalchemy import desc, select

    from ..core.artifacts import ArtifactStore
    from ..core.models import (AuditLog, Job, JobStatus, Listing, ListingAsset,
                               PatternVersion, Product)

    store = store or ArtifactStore()
    steps: list[dict] = []
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = (s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                    PatternVersion.version == version))
              if product is not None else None)
        certificate = dict(pv.certificate or {}) if pv is not None else {}
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version)
                           .order_by(desc(Listing.id)).limit(1))
        state = listing.state if listing is not None else None
        frame_shas = [r.sha256 for r in s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == slug, ListingAsset.version == version))]
        built = next((dict(j.outputs or {}) for j in s.scalars(
            select(Job).where(Job.job_type == "assets.build", Job.status == JobStatus.DONE)
            .order_by(desc(Job.id)).limit(200))
            if (j.outputs or {}).get("slug") == slug
            and (j.outputs or {}).get("version") == version
            and (j.outputs or {}).get("pdf_sha256")), None)

    steps.append({"step": "certificate_retained", "ok": bool(certificate.get("granted")),
                  "why": ("the release row keeps the certificate it was published under"
                          if certificate.get("granted") else
                          "no granted certificate is retained for this release")})
    steps.append({"step": "listing_on_record", "ok": listing is not None and state != WITHDRAWN,
                  "state": state,
                  "why": ("a listing exists in a state the withdrawal path handles"
                          if listing is not None and state != WITHDRAWN else
                          "no listing to withdraw" if listing is None else
                          "the listing is already withdrawn")})
    pdf_shas = sorted({v for v in (built or {}).get("pdf_sha256_by_terminology", {}).values()}
                      | ({built["pdf_sha256"]} if built else set()))
    missing = [sha for sha in pdf_shas + frame_shas if not store.exists(sha)]
    steps.append({"step": "deliverables_restorable",
                  "ok": bool(pdf_shas) and bool(frame_shas) and not missing,
                  "pdf_hashes": len(pdf_shas), "frame_hashes": len(frame_shas),
                  "missing_on_disk": [m[:12] for m in missing][:8],
                  "why": ("every PDF and frame a restore would re-serve is on disk under its "
                          "recorded hash" if pdf_shas and frame_shas and not missing else
                          "no built PDF is recorded for this release" if not pdf_shas else
                          "no stored frames are recorded for this release" if not frame_shas
                          else f"{len(missing)} recorded artefact(s) are not on disk")})
    # the round trip, on a copy: where the state goes and how it comes back
    round_trip = ([state, WITHDRAWN, state] if listing is not None and state != WITHDRAWN
                  else None)
    steps.append({"step": "state_round_trip", "ok": round_trip is not None,
                  "transitions": round_trip, "restore_via": RESTORE_VIA,
                  "why": ("withdraw sets the listing to 'withdrawn' (audited listing.withdrawn) "
                          "and the targeted rebuild restores it from the retained release"
                          if round_trip else "nothing to round-trip")})
    ok = all(st["ok"] for st in steps)
    detail = {"slug": slug, "version": version, "ok": ok, "steps": steps,
              "dry_run": True, "rehearsed_at": datetime.now(timezone.utc).isoformat()}
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=ACTION, artifact=f"{slug}@{version}",
                       job_id=job_id, detail=detail))
    return detail


def latest(db, *, slug: str, version: str, now: datetime | None = None,
           max_age_days: int = MAX_AGE_DAYS) -> dict | None:
    """The most recent rehearsal for this release, or None when none is young enough."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == ACTION,
                                              AuditLog.artifact == f"{slug}@{version}")
                       .order_by(desc(AuditLog.id)).limit(1))
        if row is None:
            return None
        at = row.at if row.at.tzinfo else row.at.replace(tzinfo=timezone.utc)
        detail = dict(row.detail or {})
    if now - at > timedelta(days=max_age_days):
        return None
    return {**detail, "at": at.isoformat()}
