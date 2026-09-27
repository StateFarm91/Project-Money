"""The physical-proof upgrade path: a real photograph arrives, the listing upgrades (#64).

For a product first marketed with permitted non-physical representations -- digital-twin
renders, disclosed illustrations -- the moment a tester or customer photographs a finished
object is the moment the listing can carry proof. #64 asks for three things and this module
is all three, run by handlers rather than described:

1. **Intake.** `intake` records the photograph by hash with who took it and the rights basis
   it may be used under. No basis, no use: "where rights permit" is the requirement's own
   condition, so an unlicensed photograph is received and held, never queued.
2. **The upgrade task.** `plan_upgrade` supplements the listing with the photograph as a
   `PHYSICAL_PRODUCT_PHOTO` frame in the PROOF job -- the only purpose a photograph alone
   can serve (`publish.eligibility`) -- names the conceptual frames it can replace, and
   leaves the new frame unapproved: it still has to pass asset truth, and the changed frame
   set invalidates the listing-set certificate by fingerprint (#70), so the listing is
   re-certified rather than silently edited.
3. **Impact.** `measure_impact` compares first-frame click-through and conversion before and
   after the upgrade from `ListingOutcome` rows. With no live listing those rows cannot
   exist, and the reading is UNMEASURED with that reason -- never a zero.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

RIGHTS_BASES: dict[str, str] = {
    "brambleloop_made": "the object was made and photographed by Brambleloop",
    "tester_agreement": "the tester's written agreement covers marketing use of their photos",
    "customer_permission": "the customer gave recorded permission for this photograph",
    "licensed": "a licence for commercial use is on file",
}
SOURCES = ("tester", "customer", "owner")
PROOF_ROLES = ("hero", "detail", "scale", "proof", "fit")
UPGRADE_KIND = "physical.upgrade_impact"
_SHA = re.compile(r"^[0-9a-f]{64}$")


class UpgradeRefused(ValueError):
    pass


def intake(db, *, slug: str, version: str = "", source: str, sha256: str,
           rights_basis: str = "", taken_by: str = "", physical_test_id: int | None = None,
           note: str = "") -> dict:
    """Record one physical photograph. Idempotent on its hash."""
    from sqlalchemy import select

    from ..core.models import PhysicalPhoto

    sha = (sha256 or "").strip().lower()
    if not _SHA.match(sha):
        raise UpgradeRefused("a photograph is recorded by its SHA-256; this is not one")
    if source not in SOURCES:
        raise UpgradeRefused(f"{source!r} is not a photo source: {SOURCES}")
    if rights_basis and rights_basis not in RIGHTS_BASES:
        raise UpgradeRefused(f"{rights_basis!r} is not a rights basis: {sorted(RIGHTS_BASES)}")
    with db.session() as s:
        row = s.scalar(select(PhysicalPhoto).where(PhysicalPhoto.sha256 == sha))
        if row is None:
            row = PhysicalPhoto(product_slug=slug, version=version, source=source, sha256=sha,
                                rights_basis=rights_basis, taken_by=taken_by[:120],
                                physical_test_id=physical_test_id,
                                state="received" if rights_basis else "held_no_rights",
                                detail={"note": note[:500]})
            s.add(row)
            s.flush()
            new = True
        else:
            new = False
        return {"photo_id": row.id, "new": new, "state": row.state,
                "may_use": bool(row.rights_basis)}


def _ratio(num, den) -> float | None:
    return round(num / den, 4) if num is not None and den else None


def _outcome_metrics(rows) -> dict:
    views = sum(int(r.first_frame_views or 0) for r in rows)
    engaged = sum(int(r.first_frame_engagements or 0) for r in rows)
    visits = sum(int(r.visits or 0) for r in rows)
    orders = sum(int(r.orders or 0) for r in rows)
    return {"periods": len(rows), "ctr": _ratio(engaged, views),
            "conversion": _ratio(orders, visits), "visits": visits}


def plan_upgrade(db, photo_id: int, *, today: date | None = None) -> dict:
    """Add the photograph as a proof frame, name what it can replace, record the baseline."""
    from sqlalchemy import func, select
    from sqlalchemy.orm.attributes import flag_modified

    from ..core.models import ListingAsset, ListingOutcome, PhysicalPhoto

    today = today or datetime.now(timezone.utc).date()
    with db.session() as s:
        photo = s.get(PhysicalPhoto, photo_id)
        if photo is None:
            raise UpgradeRefused(f"no physical photo {photo_id}")
        if not photo.rights_basis:
            return {"photo_id": photo_id, "upgraded": False,
                    "why": "no rights basis is recorded, so the photograph is held unused"}
        if photo.state == "upgrade_queued":
            return {"photo_id": photo_id, "upgraded": False, "why": "already upgraded"}
        slug = photo.product_slug
        version = photo.version or s.scalar(
            select(ListingAsset.version).where(ListingAsset.product_slug == slug)
            .order_by(ListingAsset.id.desc()).limit(1)) or "1.0.0"
        frames = list(s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == slug, ListingAsset.version == version)))
        replaceable = [{"position": f.position, "role": f.role, "asset_class": f.asset_class}
                       for f in frames if f.asset_class != "PHYSICAL_PRODUCT_PHOTO"
                       and f.role in PROOF_ROLES]
        position = (max((f.position for f in frames), default=0) or 0) + 1
        s.add(ListingAsset(
            product_slug=slug, version=version, position=position,
            asset_class="PHYSICAL_PRODUCT_PHOTO", role="proof", sha256=photo.sha256,
            claims={"physical_photo_id": photo.id, "source": photo.source,
                    "rights_basis": photo.rights_basis, "taken_by": photo.taken_by,
                    "supplements": [r["position"] for r in replaceable],
                    "provenance": "camera"},
            approved=False,
            blocked_reasons=["awaiting asset-truth review and listing-set re-certification"]))
        before = list(s.scalars(select(ListingOutcome).where(
            ListingOutcome.product_slug == slug,
            ListingOutcome.period_end <= today.isoformat())))
        baseline = _outcome_metrics(before)
        photo.state = "upgrade_queued"
        photo.detail = {**(photo.detail or {}), "upgraded_on": today.isoformat(),
                        "frame_position": position, "replaceable": replaceable,
                        "baseline": baseline}
        flag_modified(photo, "detail")
    return {"photo_id": photo_id, "upgraded": True, "slug": slug, "version": version,
            "frame_position": position, "replaceable": replaceable, "baseline": baseline}


def measure_impact(db, *, today: date | None = None) -> dict:
    """CTR and conversion after each upgrade against its baseline; UNMEASURED without data."""
    from sqlalchemy import select

    from ..core.models import ListingOutcome, OperatingReading, PhysicalPhoto

    today = today or datetime.now(timezone.utc).date()
    readings = []
    with db.session() as s:
        photos = list(s.scalars(select(PhysicalPhoto).where(
            PhysicalPhoto.state == "upgrade_queued")))
        for p in photos:
            since = (p.detail or {}).get("upgraded_on", "")
            after = list(s.scalars(select(ListingOutcome).where(
                ListingOutcome.product_slug == p.product_slug,
                ListingOutcome.period_start >= since)))
            base = (p.detail or {}).get("baseline") or {}
            now = _outcome_metrics(after)
            if not after or base.get("ctr") is None or now["ctr"] is None:
                readings.append({"photo_id": p.id, "slug": p.product_slug,
                                 "impact": "UNMEASURED",
                                 "why": ("no listing outcome before and after the upgrade: "
                                         "click-through and conversion need a live listing's "
                                         "traffic, which shadow mode cannot produce")})
                continue
            readings.append({"photo_id": p.id, "slug": p.product_slug, "impact": "measured",
                             "ctr_before": base["ctr"], "ctr_after": now["ctr"],
                             "ctr_delta": round(now["ctr"] - base["ctr"], 4),
                             "conversion_before": base.get("conversion"),
                             "conversion_after": now["conversion"]})
        payload = {"as_of": today.isoformat(), "upgrades": len(photos), "readings": readings}
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == UPGRADE_KIND,
            OperatingReading.period_key == today.isoformat()))
        if row is None:
            s.add(OperatingReading(kind=UPGRADE_KIND, period_key=today.isoformat(),
                                   payload=payload))
        else:
            row.payload = payload
    return payload
