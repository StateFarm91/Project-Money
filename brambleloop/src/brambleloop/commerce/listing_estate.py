"""The listing estate: every listing Etsy holds, with its assets, files and renewal state.

Wave-3 lane K8. The daily `etsy.listing_census` (runtime.etsy_ops) already read every state
and compared the certified *fields*. What it did not do, and what this module adds:

- **F-553 Listing Estate Manager.** One row per listing in any state, carrying the remote id,
  state, intended state, product family, taxonomy, properties, image count and alt texts,
  the digital files Etsy holds, the expiry date, days to expiry, the renewal mode and the
  per-renewal listing fee *as a modelled figure* (the fee schedule's claim, never a charge).
- **F-544 drift of images and files.** A listing that lost an image, gained a stranger's
  file or had one replaced is drift, exactly like an edited title: reported, never
  overwritten.
- **F-559 daily digital-delivery verification.** The files attached to every live listing of
  ours are re-read each day (getAllListingFiles) and compared by name and exact size with the
  certified bytes the verified publish sent, per terminology variant (US/UK). A failed read is
  UNVERIFIED, never clean. Etsy exposes no file hash and no post-purchase download API, so
  "a buyer can download it" is stated as *inferred from the attachment*, never as observed.
- **F-250 Recency non-gaming.** `publish.release_gates.renewal_decision` was the rule with no
  caller. It now runs on every census: an expired listing of ours becomes a renewal
  *proposal* (allowed by the rule, executed by nobody here), and a listing of ours whose
  expiry moved forward while it was still active and had no recorded material change is a
  renewal the rule would have refused -- reported as a finding, because a renewal for
  recency is a boost trick this company does not use.

Nothing here writes to Etsy. The reads are the ones `listings_r` already grants.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

#: A listing within this many days of expiring is flagged so a lapse is not a surprise.
EXPIRY_WARNING_DAYS = 14
#: How far the expiry has to jump forward, on a listing that was not expired, before the
#: census reads it as a renewal rather than clock noise.
RENEWAL_JUMP_DAYS = 7

DELIVERY_VERIFIED = "VERIFIED"
DELIVERY_FAILED = "FAILED"
DELIVERY_UNVERIFIED = "UNVERIFIED"
DELIVERY_NOT_APPLICABLE = "NOT_APPLICABLE"


def _days(seconds: float) -> float:
    return round(seconds / 86400.0, 2)


def _iso(ts: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def renewal_fee() -> dict:
    """The per-listing, per-renewal fee as the fee schedule states it. Modelled, not charged."""
    try:
        from . import fee_schedule

        claim = fee_schedule.LISTING
        return {"amount": claim.amount, "currency": claim.currency,
                "renewal_months": fee_schedule.LISTING_RENEWAL_MONTHS,
                "basis": "modelled", "source": "commerce.fee_schedule.CLAIMS['listing']"}
    except Exception as e:  # noqa: BLE001 - an unreadable schedule is unknown, not zero
        return {"amount": None, "currency": None, "basis": "unknown",
                "why": f"{type(e).__name__}: {str(e)[:120]}"}


def renewal_state(remote: dict, *, now: float) -> dict:
    """Expiry, days left and renewal mode for one census row."""
    ending = remote.get("ending_timestamp")
    state = str(remote.get("state") or "")
    out: dict[str, Any] = {"expires_at": _iso(ending), "auto_renew": remote.get(
        "should_auto_renew"), "days_to_expiry": None, "expiring_soon": False}
    if ending not in (None, ""):
        try:
            left = _days(float(ending) - now)
        except (TypeError, ValueError):
            left = None
        out["days_to_expiry"] = left
        out["expiring_soon"] = left is not None and 0 <= left <= EXPIRY_WARNING_DAYS
    if state == "expired":
        out["mode"] = "expired"
    elif remote.get("should_auto_renew") is True:
        out["mode"] = "auto_renew_on_expiry"
    elif remote.get("should_auto_renew") is False:
        out["mode"] = "manual"
    else:
        out["mode"] = "unknown"
    return out


# ---- F-559 / F-544: files and images, read back daily ----------------------------------


def delivery_check(client, listing_id: str, expected_files: list[dict] | None) -> dict:
    """The exact files Etsy attaches to this listing, against what the verified publish sent.

    `expected_files` is the `files_sent` list of the listing's `store.published` audit row
    (name, size, sha256, certified_sha256 per terminology file), or None when no verified
    publish names this listing -- in which case delivery cannot be verified at all.
    """
    from ..integrations import etsy_verify

    if expected_files is None:
        return {"status": DELIVERY_UNVERIFIED, "files": [], "problems": [
            "no verified publish names this listing, so there is no certified file set to "
            "verify delivery against"], "variants": []}
    try:
        remote = client.get_listing_files(listing_id)
    except Exception as e:  # noqa: BLE001 - an unread file list is unverified, never clean
        from ..integrations.etsy_oauth import EtsyAuthNeedsOwner

        if isinstance(e, EtsyAuthNeedsOwner):
            raise
        remote = None
    result = etsy_verify.verify_files(expected_files, remote, listing_id=listing_id)
    summary = result.summary()
    held = [{"filename": r.get("filename"), "filesize": r.get("filesize"),
             "rank": r.get("rank")} for r in (remote or [])]
    variants = sorted({str(f.get("name") or "") for f in expected_files})
    if remote is None:
        status = DELIVERY_UNVERIFIED
    else:
        status = DELIVERY_VERIFIED if result.verified else DELIVERY_FAILED
    return {"status": status, "files": held, "variants": variants,
            "problems": list(summary.get("problems") or result.problems),
            "post_purchase_availability": (
                "inferred from the attachment on the live listing; Etsy publishes no "
                "buyer-download API, so it is not observed")}


def image_check(client, listing_id: str, expected_count: int | None) -> dict:
    """How many images Etsy holds now against how many the verified publish uploaded."""
    try:
        rows = client.get_listing_images(listing_id)
    except Exception as e:  # noqa: BLE001
        from ..integrations.etsy_oauth import EtsyAuthNeedsOwner

        if isinstance(e, EtsyAuthNeedsOwner):
            raise
        return {"read": False, "count": None, "problems": [
            f"listing images read failed: {type(e).__name__}"]}
    rows = sorted(rows or [], key=lambda r: int(r.get("rank") or 0))
    problems = []
    if expected_count is not None and len(rows) != expected_count:
        problems.append(f"images: the verified publish uploaded {expected_count}, Etsy holds "
                        f"{len(rows)}")
    if not rows:
        problems.append("the listing holds no image")
    return {"read": True, "count": len(rows),
            "alt_texts": [str(r.get("alt_text") or "") for r in rows],
            "problems": problems}


def published_record(db, slug: str, version: str, listing_id: str) -> dict | None:
    """The verified publish's audit detail for this listing, or None."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(
                AuditLog.action == "store.published",
                AuditLog.artifact == f"{slug}@{version}").order_by(desc(AuditLog.id))):
            detail = row.detail or {}
            if str(detail.get("etsy_listing_id") or "") == str(listing_id):
                return dict(detail)
    return None


def asset_audit(db, client, listing_id: str, known: dict) -> dict:
    """F-544 / F-559 for one listing of ours: images and files, read back, judged."""
    record = (published_record(db, known["slug"], known["version"], listing_id)
              if known.get("slug") else None)
    expected_files = list(record.get("files_sent") or []) if record else None
    expected_images = int(record.get("images_uploaded")) if (
        record and isinstance(record.get("images_uploaded"), int)) else None
    delivery = delivery_check(client, listing_id, expected_files)
    images = image_check(client, listing_id, expected_images)
    drift = [f"files: {p}" for p in delivery["problems"]
             if delivery["status"] == DELIVERY_FAILED] + [f"images: {p}" for p in
                                                           images["problems"]]
    return {"delivery": delivery, "images": images, "drift": drift}


# ---- F-553: the estate row ----------------------------------------------------------------


def estate_row(remote: dict, known: dict | None, *, now: float,
               assets: dict | None = None, properties: list | None = None) -> dict:
    """Everything F-553 asks to track about one listing, from one census observation."""
    known = known or {}
    slug = known.get("slug")
    row = {
        "listing_id": str(remote.get("listing_id")), "state": remote.get("state"),
        "intended_state": known.get("state"), "local_state": known.get("local_state"),
        "ours": bool(known), "slug": slug, "version": known.get("version"),
        "product_family": _family(slug),
        "title": remote.get("title"), "taxonomy_id": remote.get("taxonomy_id"),
        "price": remote.get("price"), "quantity": remote.get("quantity"),
        "type": remote.get("type"),
        "ending_timestamp": remote.get("ending_timestamp"),
        "should_auto_renew": remote.get("should_auto_renew"),
        "renewal": renewal_state(remote, now=now),
        "renewal_fee": renewal_fee(),
        "properties": properties if properties is not None else remote.get("properties"),
    }
    if assets is not None:
        row["images"] = {k: assets["images"].get(k) for k in ("read", "count", "alt_texts")}
        row["files"] = assets["delivery"]["files"]
        row["delivery"] = assets["delivery"]["status"]
    else:
        row["images"] = None
        row["files"] = None
        row["delivery"] = DELIVERY_NOT_APPLICABLE if not known else DELIVERY_UNVERIFIED
    return row


def _family(slug: str | None) -> str | None:
    if not slug:
        return None
    try:
        from .orders_ingest import _seed

        seed = _seed(slug)
        if seed is not None:
            return str(getattr(seed, "category", "") or getattr(seed, "family", "")
                       or "") or None
    except Exception:  # noqa: BLE001 - an unknown family is None, not a guess
        return None
    return None


# ---- F-250: renewals judged by the rule that had no caller -------------------------------


def renewal_review(previous: list[dict] | None, estate: list[dict], *,
                   material_changes: dict[str, str] | None = None) -> dict:
    """Proposals for expired listings of ours; findings for renewals the rule refuses.

    `previous` is yesterday's estate. `material_changes` maps listing_id to a recorded
    material product change (a new certified version), the one other reason a renewal is
    allowed. Nothing is renewed here: a proposal is a row for the owner, not a request.
    """
    from ..publish.release_gates import renewal_decision

    material_changes = material_changes or {}
    before = {str(r.get("listing_id")): r for r in (previous or [])}
    proposals, findings, expiring = [], [], []
    for row in estate:
        if not row.get("ours"):
            continue
        lid = str(row["listing_id"])
        if row.get("state") == "expired":
            verdict = renewal_decision(reason="expired", listing_state="expired")
            proposals.append({"listing_id": lid, "slug": row.get("slug"),
                              "allowed": verdict["allowed"], "why": verdict["why"],
                              "fee": row.get("renewal_fee"), "executed": False})
            continue
        if (row.get("renewal") or {}).get("expiring_soon"):
            expiring.append({"listing_id": lid, "slug": row.get("slug"),
                             "days_to_expiry": row["renewal"]["days_to_expiry"],
                             "mode": row["renewal"]["mode"]})
        old = before.get(lid)
        if not old:
            continue
        try:
            jump = float(row.get("ending_timestamp")) - float(old.get("ending_timestamp"))
        except (TypeError, ValueError):
            continue
        if jump >= RENEWAL_JUMP_DAYS * 86400 and old.get("state") != "expired":
            change = material_changes.get(lid, "")
            verdict = renewal_decision(reason="material_change" if change else "recency",
                                       listing_state=str(old.get("state") or ""),
                                       material_change=change)
            if not verdict["allowed"]:
                findings.append({"listing_id": lid, "slug": row.get("slug"),
                                 "expiry_moved_days": _days(jump),
                                 "was_state": old.get("state"), "why": verdict["why"]})
    return {"proposals": proposals, "refused_renewals": findings, "expiring": expiring,
            "rule": "publish.release_gates.renewal_decision"}


def material_changes(db) -> dict[str, str]:
    """listing_id -> the newer certified version recorded for it (a material change)."""
    from sqlalchemy import select

    from ..core.models import Listing

    by_slug: dict[str, list] = {}
    with db.session() as s:
        for row in s.scalars(select(Listing)):
            by_slug.setdefault(row.product_slug, []).append(
                (str(row.etsy_listing_id or ""), str(row.version), row.created_at))
    out: dict[str, str] = {}
    for slug, rows in by_slug.items():
        listed = [r for r in rows if r[0]]
        for lid, version, created in listed:
            newer = [v for (_l, v, c) in rows if v != version and c and created and c > created]
            if newer:
                out[lid] = f"{slug}: certified version {newer[-1]} after {version}"
    return out
