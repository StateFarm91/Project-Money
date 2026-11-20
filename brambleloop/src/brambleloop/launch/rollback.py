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
#: ENG-ETSY-PUBLISH slice 1: the executed rollback of a draft this system created.
DRAFT_WITHDRAWN = "listing.draft_withdrawn"
DRAFT_WITHDRAW_REFUSED = "listing.draft_withdraw_refused"
#: Local states a draft withdrawal handles: a verified draft, or one that read back short.
from ..core.listing_state import PUBLISHED as _VERIFIED_DRAFT  # noqa: E402

WITHDRAWABLE_LOCAL = (_VERIFIED_DRAFT, "incomplete_on_etsy")
#: The state the local listing returns to: what it was before `store.publish` created the draft.
RESTORED_STATE = "draft"
#: Remote states that count as gone after a delete (Etsy's soft-delete record).
TERMINAL_REMOTE = ("removed",)
EXECUTABLE_PATH = ("launch.rollback.withdraw_draft: read the draft back, delete it on Etsy only "
                   "while Etsy reports it as a draft, verify by a second read that Etsy no "
                   "longer holds it, then restore the local listing to its pre-draft state "
                   "(state 'draft', no Etsy id) and retire the creation intent, so the "
                   "retained release can be drafted again as the same bytes")


def rehearse(db, *, slug: str, version: str, store=None, job_id: int | None = None) -> dict:
    """Walk the withdrawal round trip for one release, dry, and record the rehearsal."""
    from sqlalchemy import desc, select

    from ..core.artifacts import ArtifactStore
    from ..core.models import (AuditLog, Listing, ListingAsset, ListingSetCertificateRecord,
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
        release = (pv.release_hash or "") if pv is not None else ""
        # ENG-ETSY-PUBLISH (slice 1): the frames a restore re-serves are the valid listing-set
        # certificate's, the ones an upload sends (`etsy_ops.certified_images`). Stored
        # ListingAsset rows are read only when no valid certificate exists: they include
        # frames no certificate names, so a stale one used to fail a drill whose certified
        # set was fully restorable.
        cert = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == slug,
            ListingSetCertificateRecord.version == version,
            ListingSetCertificateRecord.state == "valid")
            .order_by(desc(ListingSetCertificateRecord.id)).limit(1))
        cert_frames = sorted({str(f.get("sha256") or "") for f in
                              ((cert.certificate or {}).get("frames") or [])
                              if isinstance(f, dict) and f.get("sha256")}) if cert else []
        frame_shas = cert_frames or sorted({r.sha256 for r in s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == slug, ListingAsset.version == version)) if r.sha256})
        frame_source = ("listing_set_certificate" if cert_frames else
                        "listing_assets" if frame_shas else None)
    # ENG-ETSY-PUBLISH (slice 1): the PDFs are the ones certified for THIS release, from every
    # `assets.built` row (`deliverables.certified`, the source `secure_release` keeps). The
    # drill used to look only at the newest 200 assets.build jobs across the whole catalogue,
    # so on a busy factory an older release read "no built PDF is recorded" and failed.
    from ..commerce import deliverables

    certified_pdfs = deliverables.certified(db, slug, version, release)["pdfs"]
    if not certified_pdfs:
        certified_pdfs = _built_job_pdfs(db, slug, version, release)
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
    pdf_shas = sorted({v for v in certified_pdfs.values() if v})
    # W4-FIRSTSALE (B5): on disk, or held in Postgres under its hash (durable_artifacts,
    # re-hashed on read) -- either way a restore re-serves the same bytes.

    missing = [sha for sha in pdf_shas + frame_shas
               if not deliverables.restorable(db, sha, store)]
    steps.append({"step": "deliverables_restorable",
                  "ok": bool(pdf_shas) and bool(frame_shas) and not missing,
                  "pdf_hashes": len(pdf_shas), "frame_hashes": len(frame_shas),
                  "pdf_terminologies": sorted(certified_pdfs), "frame_source": frame_source,
                  "missing_on_disk": [m[:12] for m in missing][:8],
                  "why": ("every PDF and frame a restore would re-serve is on disk or held in "
                          "Postgres under its recorded hash" if pdf_shas and frame_shas and not missing else
                          "no built PDF is recorded for this release" if not pdf_shas else
                          "no stored frames are recorded for this release" if not frame_shas
                          else f"{len(missing)} recorded artefact(s) are neither on disk "
                          "nor held in Postgres")})
    # the round trip, on a copy: where the state goes and how it comes back
    round_trip = ([state, WITHDRAWN, state] if listing is not None and state != WITHDRAWN
                  else None)
    steps.append({"step": "state_round_trip", "ok": round_trip is not None,
                  "transitions": round_trip, "restore_via": RESTORE_VIA,
                  "executable_path": EXECUTABLE_PATH,
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


def _built_job_pdfs(db, slug: str, version: str, release: str) -> dict:
    """Fallback when no `assets.built` row names the PDFs: the newest DONE assets.build job
    for THIS slug@version (every such job, not a catalogue-wide window), release-bound when
    the job records one."""
    from sqlalchemy import desc, select

    from ..core.models import Job, JobStatus

    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type == "assets.build",
                                             Job.status == JobStatus.DONE)
                           .order_by(desc(Job.id))):
            out, inp = dict(j.outputs or {}), dict(j.inputs or {})
            if out.get("slug") != slug or out.get("version") != version:
                continue
            recorded = inp.get("release") or out.get("release") or ""
            if release and recorded and recorded != release:
                continue
            hashes = {t: h for t, h in (out.get("pdf_sha256_by_terminology") or {}).items() if h}
            if not hashes and out.get("pdf_sha256"):
                hashes = {"US": out["pdf_sha256"]}
            if hashes:
                return hashes
    return {}


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


class RollbackRefused(RuntimeError):
    """The draft withdrawal was not executed; nothing on Etsy or locally was changed."""


def _refuse(db, *, slug, version, why, job_id, listing_id=None):
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=DRAFT_WITHDRAW_REFUSED,
                       artifact=f"{slug}@{version}", job_id=job_id,
                       detail={"reason": str(why)[:500], "etsy_listing_id": listing_id}))
    raise RollbackRefused(why)


def withdraw_draft(db, client, *, slug: str, version: str, reason: str, grant=None,
                   job_id: int | None = None) -> dict:
    """Roll back the Etsy draft this system created for slug@version, and restore the prior
    local state (ENG-ETSY-PUBLISH slice 1).

    A draft is never visible to buyers, so withdrawing one strands nobody. In order:

    1. The local listing must record an Etsy id and be `published` (a verified draft) or
       `incomplete_on_etsy`. Anything else refuses with nothing sent.
    2. Etsy is read. A listing Etsy no longer holds (404) skips the delete. A listing Etsy
       reports in any state but `draft` is refused: a live listing is deactivated, never
       deleted, and that is the owner's (or the standing-withdrawal) door, not this one.
    3. `EtsyClient.delete_listing(expect_states=("draft",))`. It re-reads the state itself,
       and its write boundary needs the publication grant that created this draft
       (`OwnerGrant.PUBLISH_COMPLETE`: only that grant's own draft) or the draft-only shadow
       lane in a non-publishing phase.
    4. A second read must find the listing gone (`listing_exists` False). A 204 alone is
       Etsy accepting the request, not proof that the draft is gone.
    5. Only then, in one transaction, the local listing returns to `draft` with no Etsy id.
       Its copy, price and release binding are untouched. The creation intent is retired,
       its record copied into the audit row, so the same release may be drafted once more.
       Open `store.publish_incomplete` incidents for this release resolve with the evidence.

    Every outcome is audited (`listing.draft_withdrawn` or `listing.draft_withdraw_refused`).
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog, Listing
    from ..ops import incident_lifecycle
    from ..publish import draft_intent
    from ..runtime.etsy_ops import PUBLISH_INCOMPLETE

    if not str(reason or "").strip():
        _refuse(db, slug=slug, version=version, why="a draft withdrawal needs a reason",
                job_id=job_id)
    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version)
                           .order_by(desc(Listing.id)).limit(1))
        before = (None if listing is None else
                  {"state": listing.state, "etsy_listing_id": listing.etsy_listing_id,
                   "release_hash": listing.release_hash})
    if before is None:
        _refuse(db, slug=slug, version=version, why="no local listing for this release",
                job_id=job_id)
    listing_id = str(before["etsy_listing_id"] or "")
    if not listing_id:
        _refuse(db, slug=slug, version=version, why="the local listing records no Etsy draft",
                job_id=job_id)
    if before["state"] not in WITHDRAWABLE_LOCAL:
        _refuse(db, slug=slug, version=version, listing_id=listing_id,
                why=(f"local listing state {before['state']!r} is not a draft this path "
                     f"withdraws {list(WITHDRAWABLE_LOCAL)}; a live listing is deactivated"),
                job_id=job_id)
    exists, remote_state = client.listing_exists(listing_id)
    remote_state = str(remote_state or "").lower()
    deleted = False
    after_state = "absent"
    if exists:
        if remote_state != "draft":
            _refuse(db, slug=slug, version=version, listing_id=listing_id,
                    why=(f"Etsy reports listing {listing_id} as {remote_state!r}, not 'draft': "
                         "a listing buyers can see is deactivated, never deleted"),
                    job_id=job_id)
        try:
            deleted = bool(client.delete_listing(listing_id, expect_states=("draft",),
                                                 grant=grant))
        except Exception as exc:  # noqa: BLE001 - a refused or failed delete changes nothing
            _refuse(db, slug=slug, version=version, listing_id=listing_id,
                    why=f"delete refused or failed: {type(exc).__name__}: {str(exc)[:300]}",
                    job_id=job_id)
        still, after_state = client.listing_exists(listing_id)
        after_state = str(after_state or "").lower()
        # A soft delete leaves a terminal `removed` record, which no buyer can see and no
        # request can revive; that is gone. Every other state Etsy still reports is not.
        if still and after_state not in TERMINAL_REMOTE:
            _refuse(db, slug=slug, version=version, listing_id=listing_id,
                    why=(f"Etsy still holds listing {listing_id} ({after_state!r}) after the "
                         "delete; the local listing is left as it was"),
                    job_id=job_id)
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version)
                       .order_by(desc(Listing.id)).limit(1).with_for_update())
        if row is None or str(row.etsy_listing_id or "") != listing_id:
            raise RollbackRefused("the local listing changed during the withdrawal")
        row.etsy_listing_id = ""          # the column default: no Etsy listing
        row.state = RESTORED_STATE
        intent = s.get(draft_intent.DraftIntent, draft_intent.key_for(slug, version))
        retired = None
        if intent is not None and str(intent.remote_id or "") in ("", listing_id):
            retired = {"state": intent.state, "remote_id": intent.remote_id,
                       "release": intent.release, "content_digest": intent.content_digest,
                       "at": intent.at.isoformat() if intent.at else None}
            s.delete(intent)
        resolved = incident_lifecycle.resolve_signatures(
            s, [f"{PUBLISH_INCOMPLETE}{slug}@{version}",
                f"draft-create:{draft_intent.key_for(slug, version)}"],
            resolution=f"Etsy draft {listing_id} withdrawn and verified gone")
        detail = {"etsy_listing_id": listing_id, "reason": str(reason)[:300],
                  "before": before, "after": {"state": RESTORED_STATE, "etsy_listing_id": ""},
                  "remote_state_before": remote_state if exists else "absent",
                  "deleted_by_this_call": deleted, "verified_absent": True,
                  "remote_state_after": after_state if after_state else "absent",
                  "retired_intent": retired, "resolved_incidents": resolved}
        s.add(AuditLog(actor="orchestrator", action=DRAFT_WITHDRAWN,
                       artifact=f"{slug}@{version}", job_id=job_id, detail=detail))
    return detail
