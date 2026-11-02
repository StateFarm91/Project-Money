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
        checks["frame_order_valid"] = (contiguous and ctx["position"] > 1
                                       and len(leaders) == 1 and leaders[0][0] == 1)
    synthetic = sample_photo._synthetic_shas(db, [frame_sha]) if frame_sha else {}
    checks["no_disclosure_free_claim"] = (
        set(claims) <= ALLOWED_CLAIMS and claims.get("provenance") == "camera"
        and not generated and frame_sha not in synthetic)
    if not checks["no_disclosure_free_claim"]:
        ctx["claims_not_allowed"] = sorted(set(claims) - ALLOWED_CLAIMS)
        if generated or frame_sha in synthetic:
            ctx["made_not_taken"] = synthetic.get(frame_sha, "a generated frame")
    return checks, ctx


def review_frame(db, frame_id: int, *, reissue: bool = True) -> dict:
    """Review one photo frame; approve it only when every check is exactly True."""
    from ..core.models import AuditLog, ListingAsset

    try:
        checks, ctx = _checks(db, frame_id)
    except Exception as exc:  # noqa: BLE001 - an unreadable record approves nothing
        checks, ctx = {c: f"UNKNOWN: {type(exc).__name__}" for c in CHECKS}, {
            "frame_id": frame_id}
    approved = all(checks.get(c) is True for c in CHECKS)
    failed = [c for c in CHECKS if checks.get(c) is not True]
    out = {k: v for k, v in {**ctx, "checks": checks, "approved": approved,
                             "failed": failed}.items()
           if k not in ("claims", "blocked_reasons", "asset_class")}
    with db.session() as s:
        from sqlalchemy import select

        # OPUS2S-2: the frame is locked and re-read in the write; if anything the checks read
        # changed since (a concurrent upgrade moved it, re-marked it, or replaced its bytes),
        # nothing is approved and the next sweep reviews it afresh.
        frame = s.scalars(select(ListingAsset).where(ListingAsset.id == int(frame_id))
                          .with_for_update()).first()
        if frame is not None and approved:
            now = {"position": frame.position, "sha256": frame.sha256,
                   "asset_class": frame.asset_class, "claims": dict(frame.claims or {}),
                   "blocked_reasons": list(frame.blocked_reasons or [])}
            changed = sorted(k for k, v in now.items() if ctx.get(k) != v)
            # OPUS2S-1: only a frame still awaiting this review is approved. A withdrawn
            # frame (approved=False with no reason) is not this review's to approve.
            if AWAITING not in now["blocked_reasons"]:
                changed.append("not awaiting asset-truth review")
            if changed:
                approved = False
                out.update(approved=False, failed=["unchanged_since_checked"],
                           changed=changed)
        if frame is not None and approved:
            remaining = [r for r in (frame.blocked_reasons or []) if r != AWAITING]
            frame.blocked_reasons = remaining
            frame.approved = not remaining
            out["frame_approved"] = frame.approved
            out["other_reasons"] = remaining
        s.add(AuditLog(actor="asset_truth", action=ACTION,
                       artifact=f"{ctx.get('slug')}@{ctx.get('version')}",
                       detail={k: v for k, v in out.items() if k != "certificate"}))
    if approved and reissue and out.get("frame_approved"):
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
    """Every photo frame still carrying the awaiting-review reason."""
    from sqlalchemy import select

    from ..core.models import ListingAsset

    with db.session() as s:
        return [f.id for f in s.scalars(select(ListingAsset).where(
            ListingAsset.asset_class == PHOTO_CLASS).order_by(ListingAsset.id))
            if AWAITING in (f.blocked_reasons or [])]


def sweep(db) -> dict:
    """Review every awaiting photo frame. CA$0, deterministic, never publishes."""
    results = [review_frame(db, fid) for fid in awaiting_frames(db)]
    return {"reviewed": len(results), "approved": sum(1 for r in results if r["approved"]),
            "refused": [{"frame_id": r.get("frame_id"), "failed": r["failed"]}
                        for r in results if not r["approved"]],
            "work_done": sum(1 for r in results if r["approved"])}
