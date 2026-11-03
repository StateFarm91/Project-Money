"""P0-PHOTO-ASSET-REVIEW: the deterministic asset-truth review of a physical sample photo frame.

`physical_upgrade.plan_upgrade` and `lead_with_if_qualifying` put an attested sample photograph
in the gallery (first, when it qualifies) and leave its frame unapproved, "awaiting asset-truth
review and listing-set re-certification". Nothing in production ever performed that review, so
a photo-led listing set could never certify: it failed closed forever (integrator queue
2026-11-02T03:40Z, P0-PHOTO-ASSET-REVIEW).

This module is that review. It is code, not a model: no LLM verdict decides an approval. For
one PHYSICAL_PRODUCT_PHOTO frame it checks, from stored records only:

  attestation_binds_release   the photo is filed under this frame's slug and version, and
                              `sample_photo.qualifying_photos(slug, version)` -- the
                              publication gate's own predicate (owner attestation of the file,
                              intake attestation, rights basis, a passed full make of THIS
                              release, not a file the system made) -- accepts it;
  hash_matches_attested_sample  frame hash == photo hash == the hash the owner attested ==
                              the qualifying entry's hash, and the bytes are in the store;
  frame_order_valid           positions are 1..n with no gap or duplicate, the photo is at
                              position 1 and marked as leading, and no other frame leads;
  no_disclosure_free_claim    the frame claims only what a photograph can (who, rights,
                              provenance "camera", leads/supplements) -- no size, colour,
                              difficulty or other figure that needs a disclosure -- and it is
                              not a generated frame or a digest the system recorded as made.

Every check must be exactly True. Anything else -- False, a missing record, an exception -- is
a refusal (fail closed on UNKNOWN), and a render is never approved as a photo. On approval the
frame's awaiting reason is cleared (any other recorded reason stays and keeps it blocked), an
audit row records every check, and the listing-set certificate is re-issued through the
existing path (`release_gates.listing_set(..., issue=True)`). A refusal is audited too.
"""
from __future__ import annotations

ACTION = "gate.photo_asset_reviewed"
PHOTO_CLASS = "PHYSICAL_PRODUCT_PHOTO"
AWAITING = "awaiting asset-truth review and listing-set re-certification"
# What a photograph's frame may claim. Everything else (width_cm, height_cm, colors,
# difficulty, ...) is a figure the photo itself does not establish and needs a disclosure.
ALLOWED_CLAIMS = frozenset({"physical_photo_id", "source", "rights_basis", "taken_by",
                            "provenance", "leads_gallery", "supplements"})
CHECKS = ("attestation_binds_release", "hash_matches_attested_sample", "frame_order_valid",
          "no_disclosure_free_claim")


def _checks(db, frame_id: int) -> tuple[dict, dict]:
    """(checks, context). Each check is True, False, or a string saying why it is UNKNOWN."""
    from sqlalchemy import select

    from ..core.models import ListingAsset, PhysicalPhoto
    from . import release_gates, sample_photo
    from .physical_upgrade import bytes_on_file

    with db.session() as s:
        frame = s.get(ListingAsset, int(frame_id))
        if frame is None:
            return {c: "no such frame" for c in CHECKS}, {}
        slug, version = frame.product_slug, frame.version
        claims = dict(frame.claims or {})
        ctx = {"frame_id": frame.id, "slug": slug, "version": version,
               "position": frame.position, "sha256": frame.sha256,
               "asset_class": frame.asset_class, "claims": claims,
               "blocked_reasons": list(frame.blocked_reasons or [])}
        if frame.asset_class != PHOTO_CLASS:
            return ({c: f"not a {PHOTO_CLASS} frame ({frame.asset_class})" for c in CHECKS},
                    ctx)
        generated = bool(release_gates.is_generated_frame(frame))
        siblings = sorted(((f.position, f.id, f.asset_class, dict(f.claims or {}))
                           for f in s.scalars(select(ListingAsset).where(
                               ListingAsset.product_slug == slug,
                               ListingAsset.version == version))))
        pid = claims.get("physical_photo_id")
        photo = s.get(PhysicalPhoto, int(pid)) if isinstance(pid, int) else None
        if photo is None:
            return {c: "the frame names no stored physical photo" for c in CHECKS}, ctx
        p = {"id": photo.id, "slug": photo.product_slug, "version": photo.version,
             "sha256": photo.sha256,
             "attested": ((photo.detail or {}).get("owner_attestation") or {}).get("sha256")}
        frame_sha = frame.sha256
    ctx["photo_id"] = p["id"]

    q = sample_photo.qualifying_photos(db, slug, version)
    entry = next((e for e in q.get("qualifying") or [] if e.get("photo_id") == p["id"]), None)
    rejected = next((e for e in q.get("rejected") or [] if e.get("photo_id") == p["id"]), None)
    checks: dict = {}
    checks["attestation_binds_release"] = (
        p["slug"] == slug and p["version"] == version and entry is not None)
    if rejected is not None:
        ctx["not_qualifying_because"] = rejected.get("why")
    checks["hash_matches_attested_sample"] = bool(
        frame_sha and frame_sha == p["sha256"] == p["attested"]
        and entry is not None and entry.get("sha256") == frame_sha
        and bytes_on_file(db, frame_sha))
    positions = [pos for pos, *_ in siblings]
    leaders = [(pos, fid) for pos, fid, _cls, c in siblings if c.get("leads_gallery") is True]
    contiguous = positions == list(range(1, len(positions) + 1))
    if claims.get("leads_gallery") is True:
        # the leading photo: at position 1 and the only frame that leads
        checks["frame_order_valid"] = (contiguous and ctx["position"] == 1
                                       and leaders == [(1, ctx["frame_id"])])
    else:
        # OPUS2S-3: a second qualifying photo of the release, behind the one that leads: a
        # supplement, valid when exactly one other frame leads, at position 1.
        # OPUS2W-4: and the frame that leads is itself a photograph.
        lead_cls = {fid: cls for _pos, fid, cls, _c in siblings}
        checks["frame_order_valid"] = (contiguous and ctx["position"] > 1
                                       and len(leaders) == 1 and leaders[0][0] == 1
                                       and lead_cls.get(leaders[0][1]) == PHOTO_CLASS)
    synthetic = sample_photo._synthetic_shas(db, [frame_sha]) if frame_sha else {}
    checks["no_disclosure_free_claim"] = (
        set(claims) <= ALLOWED_CLAIMS and claims.get("provenance") == "camera"
        and not generated and frame_sha not in synthetic)
    if not checks["no_disclosure_free_claim"]:
        ctx["claims_not_allowed"] = sorted(set(claims) - ALLOWED_CLAIMS)
        if generated or frame_sha in synthetic:
            ctx["made_not_taken"] = synthetic.get(frame_sha, "a generated frame")
    return checks, ctx


NOT_QUALIFYING = "photo not qualifying: "          # I-A3-NONQUALIFYING-PHOTO (terminal state)
# The checks a photo that does not (yet) qualify fails: the attestation of this release and the
# attested sample's bytes. Any other failure (order, claims, UNKNOWN) stays awaiting review.
_QUALIFYING_CHECKS = ("attestation_binds_release", "hash_matches_attested_sample")
_LOCK_KEY = 0x0B2A3F07                              # Postgres advisory lock for photo review


def _lock(s, db) -> None:
    """OPUS2W-1: hold the write lock for the whole review -- the checks and the write -- so no
    writer can commit between them (Postgres: an advisory xact lock; SQLite: BEGIN IMMEDIATE,
    the codebase's pattern in release._serialise_owner_queue). Readers are not blocked."""
    from sqlalchemy import text

    from ..core.db import is_postgres

    if is_postgres(db.engine):
        s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    else:
        s.execute(text("BEGIN IMMEDIATE"))


def _invalidate_photo_certificates(session, slug: str, version: str, reason: str) -> None:
    """Invalidate listing-set certificates in the same transaction as a photo change."""
    from sqlalchemy import select
    from ..core.models import AuditLog, ListingSetCertificateRecord, utcnow

    records = session.scalars(select(ListingSetCertificateRecord).where(
        ListingSetCertificateRecord.product_slug == slug,
        ListingSetCertificateRecord.version == version,
        ListingSetCertificateRecord.state == "valid").with_for_update())
    for record in records:
        record.state = "invalidated"
        record.invalidated_by = [reason]
        record.invalidated_at = utcnow()
        session.add(AuditLog(actor="asset_truth", action="gate.photo_certificate_invalidated",
                             artifact=f"{slug}@{version}", detail={
                                 "certificate_id": record.id, "reason": reason}))


def _lock_photo_sources(session, frames) -> bool:
    """Fence existing photo and full-make rows for this transaction.

    PostgreSQL row locks also block ordinary UPDATE/DELETE writers that do not use
    the photo advisory lock. This is only a partial fence: provenance inserts,
    other binding dependencies, artifact bytes, and operations after commit still
    require their own coordination.
    """
    from sqlalchemy import select
    from ..core.models import PhysicalPhoto, PhysicalTest

    ids = []
    for frame in frames:
        pid = (frame.claims or {}).get("physical_photo_id")
        if type(pid) is not int:
            return False
        ids.append(pid)
    photos = list(session.scalars(select(PhysicalPhoto).where(
        PhysicalPhoto.id.in_(sorted(set(ids)))).order_by(PhysicalPhoto.id).with_for_update()))
    if len(photos) != len(set(ids)):
        return False
    test_ids = sorted({p.physical_test_id for p in photos if p.physical_test_id is not None})
    if test_ids:
        list(session.scalars(select(PhysicalTest).where(
            PhysicalTest.id.in_(test_ids)).order_by(PhysicalTest.id).with_for_update()))
    return True


def photo_snapshot_current(session, db, slug: str, version: str, frames) -> bool:
    """Under the photo lock, compare proposed photos to current evidence and frames."""
    from sqlalchemy import select
    from ..core.models import ListingAsset

    current = list(session.scalars(select(ListingAsset).where(
        ListingAsset.product_slug == slug, ListingAsset.version == version,
        ListingAsset.asset_class == PHOTO_CLASS).with_for_update()))
    current = [f for f in current if not any(str(r).startswith(NOT_QUALIFYING)
                                             for r in (f.blocked_reasons or []))]
    proposed = [f for f in frames if f.asset_class == PHOTO_CLASS]
    def identity(frame):
        return (frame.id, frame.position, frame.sha256, frame.approved,
                dict(frame.claims or {}), list(frame.blocked_reasons or []))
    if sorted((identity(f) for f in current), key=lambda x: x[0]) != sorted(
            (identity(f) for f in proposed), key=lambda x: x[0]):
        return False
    if not _lock_photo_sources(session, current):
        return False
    for frame in current:
        if not frame.approved or frame.blocked_reasons:
            return False
        try:
            checks, _ = _checks(db, frame.id)
        except Exception:  # noqa: BLE001 - unreadable evidence cannot certify
            return False
        if any(checks.get(c) is not True for c in CHECKS):
            return False
    return True


def photo_certificate_current(session, db, slug: str, version: str, certified_frames) -> bool:
    """Under the photo lock, bind a proposed certificate to current qualifying photos."""
    from sqlalchemy import select
    from ..core.models import ListingAsset

    current = list(session.scalars(select(ListingAsset).where(
        ListingAsset.product_slug == slug, ListingAsset.version == version,
        ListingAsset.asset_class == PHOTO_CLASS).with_for_update()))
    current = [f for f in current if not any(str(r).startswith(NOT_QUALIFYING)
                                             for r in (f.blocked_reasons or []))]
    expected = [(f.position, f.sha256) for f in certified_frames if f.medium == PHOTO_CLASS]
    # A photo-led disclosed certificate deliberately includes its leader only;
    # other valid supplements may exist without being included in that certificate.
    by_key = {(f.position, f.sha256): f for f in current}
    if len(set(expected)) != len(expected) or any(key not in by_key for key in expected):
        return False
    if not _lock_photo_sources(session, [by_key[key] for key in expected]):
        return False
    for frame in (by_key[key] for key in expected):
        if not frame.approved or frame.blocked_reasons:
            return False
        try:
            checks, _ = _checks(db, frame.id)
        except Exception:  # noqa: BLE001 - unreadable evidence cannot certify
            return False
        if any(checks.get(c) is not True for c in CHECKS):
            return False
    return True


def _reviewable(reasons) -> bool:
    return AWAITING in reasons or any(str(r).startswith(NOT_QUALIFYING) for r in reasons)


def review_frame(db, frame_id: int, *, reissue: bool = True) -> dict:
    """Review one photo frame under the write lock; approve it only when every check is
    exactly True. A frame that does not qualify gets a terminal named reason instead of
    staying awaiting (I-A3-NONQUALIFYING-PHOTO); the listing-set certificate excludes it.

    A3D-5: a lock that cannot be taken (another writer past the busy timeout) is a refusal for
    this frame, not an exception that stops the sweep; nothing is written and the next sweep
    reviews it again."""
    from sqlalchemy.exc import OperationalError

    try:
        return _review_frame(db, frame_id, reissue=reissue)
    except OperationalError as exc:
        return {"frame_id": frame_id, "approved": False,
                "failed": [f"UNKNOWN: write lock not taken ({type(exc).__name__})"]}


def _review_frame(db, frame_id: int, *, reissue: bool) -> dict:
    from sqlalchemy import select

    from ..core.models import AuditLog, ListingAsset

    with db.session() as s:
        _lock(s, db)
        frame = s.scalars(select(ListingAsset).where(ListingAsset.id == int(frame_id))
                          .with_for_update()).first()
        try:
            if frame is not None and frame.asset_class == PHOTO_CLASS:
                if not _lock_photo_sources(s, [frame]):
                    raise ValueError("photo source missing")
            checks, ctx = _checks(db, frame_id)
        except Exception as exc:  # noqa: BLE001 - an unreadable record approves nothing
            checks, ctx = {c: f"UNKNOWN: {type(exc).__name__}" for c in CHECKS}, {
                "frame_id": frame_id}
        approved = all(checks.get(c) is True for c in CHECKS)
        failed = [c for c in CHECKS if checks.get(c) is not True]
        out = {k: v for k, v in {**ctx, "checks": checks, "approved": approved,
                                 "failed": failed}.items()
               if k not in ("claims", "blocked_reasons", "asset_class")}
        if frame is None:
            # OPUS2W-5: a frame that is gone is never reported approved.
            out.update(approved=False, failed=["frame_gone"])
            approved = False
        elif not _reviewable(list(frame.blocked_reasons or [])):
            # OPUS2S-1: only a frame awaiting this review (or held as not qualifying) is
            # reviewed; a withdrawn frame (approved=False with no reason) is not this review's.
            approved = False
            out.update(approved=False,
                       failed=failed or ["not awaiting asset-truth review"])
        else:
            others = [r for r in (frame.blocked_reasons or [])
                      if r != AWAITING and not str(r).startswith(NOT_QUALIFYING)]
            if approved:
                frame.blocked_reasons = others
                frame.approved = not others
                out["frame_approved"] = frame.approved
                out["other_reasons"] = others
            elif set(failed) & set(_QUALIFYING_CHECKS) and not any(
                    isinstance(checks.get(c), str) for c in failed):
                # (a photo that does not qualify cannot lead, so its order check fails with it)
                # I-A3-NONQUALIFYING-PHOTO: terminal and named, never holding the set hostage;
                # the sweep re-opens it once a later attestation or full make qualifies it.
                frame.blocked_reasons = [f"{NOT_QUALIFYING}{', '.join(failed)}"] + others
                frame.approved = False
                out["not_qualifying"] = failed
            elif any(str(r).startswith(NOT_QUALIFYING) for r in frame.blocked_reasons or []):
                # A3D-1: the photo qualifies now, but another check fails (its order, a claim,
                # an UNKNOWN). The "not qualifying" reason is no longer true: it goes back to
                # awaiting review, rejoins the set and blocks it by name -- never a stale
                # reason that keeps a qualifying photo out of the set for good.
                frame.blocked_reasons = [AWAITING] + others
                frame.approved = False
                out["reopened_awaiting"] = failed
        if frame is not None and out.get("frame_approved") is not True:
            _invalidate_photo_certificates(s, frame.product_slug, frame.version,
                                           "photo_review_not_approved")
        s.add(AuditLog(actor="asset_truth", action=ACTION,
                       artifact=f"{ctx.get('slug')}@{ctx.get('version')}",
                       detail={k: v for k, v in out.items() if k != "certificate"}))
    if (approved and reissue and out.get("frame_approved")) or (
            reissue and out.get("not_qualifying")):
        from . import release_gates

        try:
            cert = release_gates.listing_set(db, slug=ctx["slug"], version=ctx["version"],
                                             issue=True)
            out["certificate"] = {"blocks_release": cert.get("blocks_release"),
                                  "reasons": list(cert.get("reasons") or [])[:5],
                                  "issued": bool(cert.get("certificate"))}
        except Exception as exc:  # noqa: BLE001 - re-certification is re-run by its own job
            out["certificate"] = {"issued": False, "error": type(exc).__name__}
    return out


def awaiting_frames(db) -> list[int]:
    """Every photo frame awaiting review, and every one held as not qualifying whose photo
    qualifies now (a later attestation or passed full make re-opens it)."""
    from sqlalchemy import select

    from ..core.models import ListingAsset
    from . import sample_photo

    out: list[int] = []
    with db.session() as s:
        rows = [(f.id, f.product_slug, f.version, list(f.blocked_reasons or []),
                 dict(f.claims or {}).get("physical_photo_id"), f.sha256)
                for f in s.scalars(select(ListingAsset).where(
                    ListingAsset.asset_class == PHOTO_CLASS).order_by(ListingAsset.id))]
    for fid, slug, version, reasons, pid, sha in rows:
        if AWAITING in reasons:
            out.append(fid)
        elif any(str(r).startswith(NOT_QUALIFYING) for r in reasons):
            try:
                q = sample_photo.qualifying_photos(db, slug, version)
            except Exception:  # noqa: BLE001 - unreadable: stays held, re-read next sweep
                continue
            # A3D-3: only a frame whose own bytes are the qualifying photo's is re-opened; a
            # frame holding other bytes would fail the hash check again on every sweep.
            if any(e.get("photo_id") == pid and sha and e.get("sha256") == sha
                   for e in q.get("qualifying") or []):
                out.append(fid)
    return out


def _promote_if_leaderless(db, frame_id: int) -> bool:
    """A3D-1: a held photo that qualifies now, in a set no photograph leads, is moved to lead
    through the same `lead_with_if_qualifying` an attestation uses -- whatever made it qualify
    (a later full make, a rights record, restored bytes). A set already led by a photograph is
    left as it is; this one is reviewed as a supplement."""
    from sqlalchemy import select

    from ..core.models import ListingAsset
    from .physical_upgrade import lead_with_if_qualifying

    with db.session() as s:
        frame = s.get(ListingAsset, int(frame_id))
        if frame is None:
            return False
        pid = dict(frame.claims or {}).get("physical_photo_id")
        reasons = list(frame.blocked_reasons or [])
        photo_leads = any(
            f.asset_class == PHOTO_CLASS and (f.claims or {}).get("leads_gallery") is True
            and not any(str(r).startswith(NOT_QUALIFYING) for r in (f.blocked_reasons or []))
            for f in s.scalars(select(ListingAsset).where(
                ListingAsset.product_slug == frame.product_slug,
                ListingAsset.version == frame.version)))
    if photo_leads or not isinstance(pid, int) or not _reviewable(reasons):
        return False
    return bool(lead_with_if_qualifying(db, pid))


def _reopen_stale_approved_photos(db) -> None:
    """Re-review every approved physical photo whose evidence has lapsed."""
    from sqlalchemy import select
    from ..core.models import ListingAsset

    with db.session() as s:
        ids = list(s.scalars(select(ListingAsset.id).where(
            ListingAsset.asset_class == PHOTO_CLASS,
            ListingAsset.approved == True)))  # noqa: E712
    for fid in ids:
        try:
            with db.session() as s:
                _lock(s, db)
                frame = s.scalar(select(ListingAsset).where(
                    ListingAsset.id == fid).with_for_update())
                if (frame is None or not frame.approved
                        or frame.asset_class != PHOTO_CLASS):
                    continue
                try:
                    checks, _ = _checks(db, fid)
                except Exception:  # noqa: BLE001 - unreadable evidence is not approval
                    checks = {}
                if any(checks.get(c) is not True for c in CHECKS):
                    # Awaiting is durable if the process stops before the review.
                    # Never clear other holds; review_frame rechecks the evidence.
                    frame.approved = False
                    _invalidate_photo_certificates(s, frame.product_slug, frame.version,
                                                   "photo_evidence_changed")
                    frame.blocked_reasons = [AWAITING] + [r for r in
                        (frame.blocked_reasons or []) if r != AWAITING]
        except Exception:  # noqa: BLE001 - unknown evidence cannot cause approval
            continue


def _excluded_leader_recoveries(db) -> list[int]:
    """Previously approved supplements can replace an excluded photo leader."""
    from sqlalchemy import select
    from ..core.models import ListingAsset
    from . import sample_photo

    with db.session() as s:
        rows = list(s.scalars(select(ListingAsset).order_by(ListingAsset.id)))
        releases = {(f.product_slug, f.version) for f in rows
                    if f.asset_class == PHOTO_CLASS and f.position == 1
                    and any(str(r).startswith(NOT_QUALIFYING)
                            for r in (f.blocked_reasons or []))}
        candidates = [(f.id, f.product_slug, f.version, f.sha256,
                       (f.claims or {}).get("physical_photo_id")) for f in rows
                      if (f.product_slug, f.version) in releases and f.asset_class == PHOTO_CLASS
                      and f.approved is True and not (f.blocked_reasons or [])]
    selected = []
    for slug, version in sorted(releases):
        try:
            qualifying = sample_photo.qualifying_photos(db, slug, version).get("qualifying") or []
        except Exception:  # noqa: BLE001 - unknown evidence cannot promote
            continue
        for fid, cslug, cversion, sha, pid in candidates:
            if (cslug, cversion) == (slug, version) and any(
                    e.get("photo_id") == pid and sha and e.get("sha256") == sha
                    for e in qualifying):
                selected.append(fid)
                break
    return selected


def sweep(db) -> dict:
    """Review every awaiting (or newly qualifying) photo frame. CA$0, never publishes."""
    results = []
    _reopen_stale_approved_photos(db)
    for fid in awaiting_frames(db):
        try:
            _promote_if_leaderless(db, fid)
        except Exception:  # noqa: BLE001 - not promoted: the review below still names why
            pass
        results.append(review_frame(db, fid))
    for fid in _excluded_leader_recoveries(db):
        try:
            from .physical_upgrade import lead_with_if_qualifying
            from ..core.models import ListingAsset
            with db.session() as s:
                row = s.get(ListingAsset, fid)
                pid = (row.claims or {}).get("physical_photo_id") if row else None
            if isinstance(pid, int) and lead_with_if_qualifying(db, pid):
                results.append(review_frame(db, fid))
        except Exception:  # noqa: BLE001 - retain the hold and retry on next sweep
            continue
    return {"reviewed": len(results),
            "approved": sum(1 for r in results if r.get("frame_approved") is True),
            "not_qualifying": [r.get("frame_id") for r in results if r.get("not_qualifying")],
            "refused": [{"frame_id": r.get("frame_id"),
                         "failed": r.get("failed") or r.get("other_reasons") or ["not approved"]}
                        for r in results if r.get("frame_approved") is not True],
            "work_done": sum(1 for r in results if r.get("frame_approved") is True)}
