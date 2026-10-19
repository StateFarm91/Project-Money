"""Laura outfit registry, enforced (owner rule D-W4-LAURA-OUTFIT, 2026-10-19).

The rule is short:

* Each distinct product listing uses a different Laura outfit.
* The photographs within one listing may share one outfit.
* Laura's canonical face and body proportions are preserved on every listing.

In code this means:

* **Reservation.** An outfit is reserved by at most one listing (`reserve`). The same
  listing may reserve it again and use it on any number of images. A different listing is
  refused (FAIL), whether the outfit is in use, retired or replaced: a retired outfit may
  still be on published images.
* **Release on failure.** `release` frees a reservation only while no image has used it.
  Once an image has, the outfit can only be replaced (`replace`). The old outfit stays bound
  to its listing for good.
* **Missing outfit.** An image with Laura and no outfit id reads UNKNOWN, and UNKNOWN blocks
  publication.
* **Unregistered or unapproved outfits** read UNKNOWN. Unknown is never PASS.
* **Styling, never identity.** An outfit may not declare any change to a locked identity
  feature (`visual.canonical.LOCKED`). Passing this check never implies the identity gate
  passed: the Laura gate order (`canonical.LAURA_LISTING_GATES`) runs identity first and
  independently.

The listing key is the product listing (`launch_imagery._primary_for`). For example, the
three nesting-basket sizes are one listing. A new version of a product is the same listing.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

PASS, FAIL, UNKNOWN, NOT_APPLICABLE = "PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"
APPROVAL_STATES = ("proposed", "approved", "retired")
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
# Words that describe the person rather than the clothes. An outfit that names one of these
# is trying to change who she is, which no outfit may do.
_IDENTITY_WORDS = re.compile(
    r"\b(hair(?:cut|style| colou?r)?|face|facial|eyes?|eye colou?r|skin tone|complexion|age|"
    r"younger|older|body|proportions?|slimmer|thinner|taller|weight|height|nose|"
    r"lips|jaw|cheekbones?)\b", re.I)


class OutfitRefused(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def listing_of(slug: str) -> str:
    """The product listing a release slug belongs to (its sizes and versions are one listing)."""
    try:
        from .launch_imagery import _primary_for

        found = _primary_for(slug)
        if found:
            return str(found[0])
    except Exception:  # noqa: BLE001 - an unreadable mapping falls back to the slug itself
        pass
    return slug


def _row(s, outfit_id: str):
    from sqlalchemy import select

    from .image_records import LauraOutfit

    return s.scalar(select(LauraOutfit).where(LauraOutfit.outfit_id == outfit_id))


def _view(r) -> dict:
    return {"outfit_id": r.outfit_id, "description": r.description, "colours": list(r.colours or []),
            "reference_hashes": list(r.reference_hashes or []),
            "approval_state": r.approval_state, "approved_by": r.approved_by,
            "listing": r.listing or None, "uses": list(r.uses or []),
            "replaced_by": r.replaced_by or None}


def register(db, *, outfit_id: str, description: str, colours: list[str] | tuple = (),
             reference_hashes: list[str] | tuple = (),
             identity_changes: dict | list | None = None) -> dict:
    """Propose an outfit. It is idempotent on the id and refuses any identity change."""
    from .image_records import LauraOutfit, ensure_tables

    oid = str(outfit_id or "").strip().lower()
    if not _ID.match(oid):
        raise OutfitRefused("an outfit id is 3-80 characters of a-z, 0-9 and '-'")
    if identity_changes:
        raise OutfitRefused(
            "an outfit is styling, never identity: it may not change "
            f"{sorted(identity_changes) if isinstance(identity_changes, dict) else identity_changes}"
            " (locked: face, hair, eyes, apparent age, facial structure, body proportions)")
    text = f"{description or ''} {' '.join(colours or ())}"
    hit = _IDENTITY_WORDS.search(text)
    if hit:
        raise OutfitRefused(
            f"the outfit description names {hit.group(0)!r}, which is part of Laura's locked "
            f"identity, not her clothes. An outfit never alters identity (D-W4-LAURA-OUTFIT)")
    refs = [str(h).strip().lower() for h in reference_hashes or ()]
    bad = [h for h in refs if not _SHA.match(h)]
    if bad:
        raise OutfitRefused(f"reference hashes must be sha256 hex: {bad[:3]}")
    from . import canonical

    identity_refs = set(canonical.CURRENT_REFERENCE_HASHES.values())
    if identity_refs & set(refs):
        raise OutfitRefused("Laura's canonical identity references are not outfit references")
    ensure_tables(db)
    with db.session() as s:
        row = _row(s, oid)
        if row is None:
            row = LauraOutfit(outfit_id=oid, description=str(description or "")[:2000],
                              colours=[str(c)[:40] for c in colours or ()],
                              reference_hashes=refs, approval_state="proposed")
            s.add(row)
            s.flush()
        return _view(row)


def approve(db, outfit_id: str, *, approved_by: str = "owner") -> dict:
    from .image_records import ensure_tables

    ensure_tables(db)
    with db.session() as s:
        row = _row(s, outfit_id)
        if row is None:
            raise OutfitRefused(f"no outfit {outfit_id!r}")
        if row.approval_state == "retired":
            raise OutfitRefused(f"{outfit_id} is retired and cannot be approved again")
        row.approval_state, row.approved_by = "approved", str(approved_by)[:80]
        return _view(row)


def get(db, outfit_id: str) -> dict | None:
    from .image_records import ensure_tables

    ensure_tables(db)
    with db.session() as s:
        row = _row(s, outfit_id)
        return _view(row) if row else None


def registry(db) -> list[dict]:
    from sqlalchemy import select

    from .image_records import LauraOutfit, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        return [_view(r) for r in s.scalars(select(LauraOutfit).order_by(LauraOutfit.id))]


def _result(status: str, why: str, **kw) -> dict:
    return {"status": status, "why": why, "rule": "D-W4-LAURA-OUTFIT", **kw}


def reserve(db, outfit_id: str | None, listing: str) -> dict:
    """Reserve this outfit for this listing. Same listing: PASS. Another listing: FAIL."""
    from .image_records import ensure_tables

    if not outfit_id:
        return _result(UNKNOWN, "Laura appears and no outfit id was given; an image with Laura "
                                "and no outfit cannot be checked for uniqueness")
    ensure_tables(db)
    with db.session() as s:
        row = _row(s, str(outfit_id).strip().lower())
        if row is None:
            return _result(UNKNOWN, f"outfit {outfit_id!r} is not in the registry")
        if row.listing and row.listing != listing:
            return _result(FAIL, f"outfit {row.outfit_id} is reserved by listing {row.listing!r}; "
                                 f"a different listing ({listing!r}) may not use it",
                           outfit_id=row.outfit_id, reserved_by=row.listing)
        if row.approval_state != "approved":
            return _result(UNKNOWN, f"outfit {row.outfit_id} is {row.approval_state}, not "
                                    f"approved", outfit_id=row.outfit_id)
        if not row.listing:
            row.listing, row.reserved_at = listing, _now()
        return _result(PASS, f"outfit {row.outfit_id} is reserved for {listing!r}",
                       outfit_id=row.outfit_id)


def check_use(db, outfit_id: str | None, *, listing: str, product: str, image_sha256: str,
              record: bool = True) -> dict:
    """The outfit-uniqueness check for one image of Laura, recording the use when it passes."""
    from sqlalchemy.orm.attributes import flag_modified

    got = reserve(db, outfit_id, listing)
    if got["status"] != PASS or not record:
        return got
    with db.session() as s:
        row = _row(s, got["outfit_id"])
        uses = list(row.uses or [])
        if not any(u.get("image_sha256") == image_sha256 for u in uses):
            uses.append({"listing": listing, "product": product, "image_sha256": image_sha256,
                         "at": _now().isoformat()})
            row.uses = uses
            flag_modified(row, "uses")
    return {**got, "why": got["why"] + "; use recorded"}


def release(db, outfit_id: str, listing: str, *, why: str) -> dict:
    """Free a reservation that never reached an image, for example after a failed run."""
    from .image_records import ensure_tables

    ensure_tables(db)
    with db.session() as s:
        row = _row(s, outfit_id)
        if row is None or row.listing != listing:
            return {"released": False, "why": "not reserved by this listing"}
        if row.uses:
            return {"released": False,
                    "why": (f"{len(row.uses)} image(s) already use {outfit_id}; the outfit "
                            f"stays bound to {listing!r}. Replace it instead")}
        row.listing, row.reserved_at = "", None
        return {"released": True, "why": str(why)[:300]}


def replace(db, old_id: str, new_id: str, listing: str) -> dict:
    """Retire the listing's outfit and reserve a new approved one for it."""
    from .image_records import ensure_tables

    ensure_tables(db)
    got = reserve(db, new_id, listing)
    if got["status"] != PASS:
        return {"replaced": False, **got}
    with db.session() as s:
        old = _row(s, old_id)
        if old is not None and old.listing == listing:
            old.approval_state, old.replaced_by = "retired", new_id
            # A retired outfit stays bound to its listing: it may be on published images.
    return {"replaced": True, "old": old_id, "new": new_id, "listing": listing}


def for_listing(db, listing: str) -> dict | None:
    """The outfit reserved for this listing, else the first approved free one (unreserved)."""
    from sqlalchemy import select

    from .image_records import LauraOutfit, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        mine = s.scalar(select(LauraOutfit).where(
            LauraOutfit.listing == listing, LauraOutfit.approval_state == "approved")
            .order_by(LauraOutfit.id))
        if mine is not None:
            return _view(mine)
        free = s.scalar(select(LauraOutfit).where(
            LauraOutfit.listing == "", LauraOutfit.approval_state == "approved")
            .order_by(LauraOutfit.id))
        return _view(free) if free is not None else None
