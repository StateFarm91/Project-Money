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


GARMENT_KEYS = ("top_or_dress", "lower", "shoes", "outerwear", "accessories")


def signature(garments: dict | None) -> str:
    """The identity of a complete outfit: its normalised garments. Two outfit ids with the
    same signature are the same outfit (D-W4-LAURA-FLUX3 §4)."""
    g = garments or {}
    norm = "|".join(" ".join(str(g.get(k) or "").lower().replace("none", "").split())
                    for k in GARMENT_KEYS)
    import hashlib

    return hashlib.sha256(norm.encode()).hexdigest()


def _view(r) -> dict:
    return {"outfit_id": r.outfit_id, "description": r.description,
            "garments": dict(r.garments or {}), "signature": r.signature,
            "colours": list(r.colours or []),
            "reference_hashes": list(r.reference_hashes or []),
            "approved_reference": r.approved_reference or None,
            "setting": r.setting or None, "concept": dict(r.concept or {}),
            "approval_state": r.approval_state, "approved_by": r.approved_by,
            "listing": r.listing or None, "uses": list(r.uses or []),
            "replaced_by": r.replaced_by or None}


def register(db, *, outfit_id: str, garments: dict, description: str = "",
             colours: list[str] | tuple = (), reference_hashes: list[str] | tuple = (),
             concept: dict | None = None,
             identity_changes: dict | list | None = None) -> dict:
    """Propose a complete outfit. Idempotent on the id. Refuses an identity change, an
    incomplete outfit, and a complete outfit already registered under another id."""
    from sqlalchemy import select

    from .image_records import LauraOutfit, ensure_tables

    oid = str(outfit_id or "").strip().lower()
    if not _ID.match(oid):
        raise OutfitRefused("an outfit id is 3-80 characters of a-z, 0-9 and '-'")
    if identity_changes:
        raise OutfitRefused(
            "an outfit is styling, never identity: it may not change "
            f"{sorted(identity_changes) if isinstance(identity_changes, dict) else identity_changes}"
            " (locked: face, hair, eyes, apparent age, facial structure, body proportions)")
    g = {k: str((garments or {}).get(k) or "").strip()[:200] for k in GARMENT_KEYS}
    unknown = sorted(set(garments or {}) - set(GARMENT_KEYS))
    if unknown:
        raise OutfitRefused(f"unknown garment fields {unknown}; an outfit is {GARMENT_KEYS}")
    if not g["top_or_dress"] or not g["shoes"]:
        raise OutfitRefused("a complete outfit names its top or dress and its shoes "
                            "(D-W4-LAURA-FLUX3 §4)")
    if not g["lower"] and "dress" not in g["top_or_dress"].lower() and \
            "pinafore" not in g["top_or_dress"].lower():
        raise OutfitRefused("a complete outfit names its lower garment unless it is a dress")
    text = f"{description or ''} {' '.join(colours or ())} {' '.join(g.values())}"
    hit = _IDENTITY_WORDS.search(text)
    if hit:
        raise OutfitRefused(
            f"the outfit names {hit.group(0)!r}, which is part of Laura's locked identity, not "
            f"her clothes. An outfit never alters identity (D-W4-LAURA-OUTFIT)")
    refs = [str(h).strip().lower() for h in reference_hashes or ()]
    bad = [h for h in refs if not _SHA.match(h)]
    if bad:
        raise OutfitRefused(f"reference hashes must be sha256 hex: {bad[:3]}")
    from . import canonical

    identity_refs = set(canonical.CURRENT_REFERENCE_HASHES.values())
    if identity_refs & set(refs):
        raise OutfitRefused("Laura's canonical identity references are not outfit references")
    sig = signature(g)
    ensure_tables(db)
    with db.session() as s:
        row = _row(s, oid)
        if row is not None:
            return _view(row)
        twin = s.scalar(select(LauraOutfit).where(LauraOutfit.signature == sig))
        if twin is not None:
            raise OutfitRefused(f"this complete outfit is already registered as "
                                f"{twin.outfit_id} (listing {twin.listing or 'none yet'}); a "
                                f"complete outfit is never reused across listings")
        row = LauraOutfit(outfit_id=oid, garments=g, signature=sig,
                          description=str(description or "; ".join(
                              v for v in g.values() if v and v != "none"))[:2000],
                          colours=[str(c)[:40] for c in colours or ()],
                          reference_hashes=refs, approval_state="proposed",
                          concept=dict(concept or {}),
                          setting=str((concept or {}).get("setting") or "")[:200])
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
            from sqlalchemy import select

            from .image_records import LauraOutfit

            held = s.scalar(select(LauraOutfit).where(
                LauraOutfit.listing == listing, LauraOutfit.approval_state == "approved",
                LauraOutfit.outfit_id != row.outfit_id))
            if held is not None:
                return _result(FAIL, f"listing {listing!r} already uses outfit "
                                     f"{held.outfit_id}; every Laura image in a listing uses "
                                     f"the same outfit (D-W4-LAURA-FLUX3 §4). Replace it "
                                     f"instead", outfit_id=row.outfit_id,
                               listing_outfit=held.outfit_id)
            twin = s.scalar(select(LauraOutfit).where(
                LauraOutfit.signature == row.signature, LauraOutfit.listing != "",
                LauraOutfit.listing != listing))
            if row.signature and twin is not None:
                return _result(FAIL, f"the same complete outfit is reserved by "
                                     f"{twin.listing!r} as {twin.outfit_id}",
                               outfit_id=row.outfit_id, codes=["WARDROBE_REPETITION"])
            near = _too_similar(s, row, listing)
            if near is not None:
                return _result(FAIL, f"outfit {row.outfit_id} is not distinct from "
                                     f"{near['against']} (similarity {near['score']} >= "
                                     f"{_max_sim()}); slots {near['slots']}",
                               outfit_id=row.outfit_id, codes=["WARDROBE_REPETITION"],
                               similarity=near)
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
    with db.session() as s:
        old = _row(s, old_id)
        if old is None or old.listing != listing:
            return {"replaced": False, "status": FAIL, "why": f"{old_id} is not {listing}'s"}
        prior = old.approval_state
        # A retired outfit stays bound to its listing: it may be on published images.
        old.approval_state, old.replaced_by = "retired", new_id
    got = reserve(db, new_id, listing)
    if got["status"] != PASS:
        with db.session() as s:
            old = _row(s, old_id)
            old.approval_state, old.replaced_by = prior, ""
        return {"replaced": False, **got}
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


def reserved_for(db, listing: str) -> dict | None:
    """The approved outfit this listing holds, or None (styling then chooses one)."""
    from sqlalchemy import select

    from .image_records import LauraOutfit, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        r = s.scalar(select(LauraOutfit).where(LauraOutfit.listing == listing,
                                               LauraOutfit.approval_state == "approved"))
        return _view(r) if r is not None else None


def _max_sim() -> float:
    from .wardrobe import MAX_SIMILARITY

    return MAX_SIMILARITY


def _too_similar(s, row, listing: str) -> dict | None:
    """The first outfit held by another listing, or the reference clothing, that this
    complete outfit is not distinct from (owner wardrobe fix)."""
    from sqlalchemy import select

    from .image_records import LauraOutfit
    from .wardrobe import REFERENCE_OUTFIT, too_similar

    others = [("the canonical reference clothing", REFERENCE_OUTFIT)]
    for o in s.scalars(select(LauraOutfit).where(LauraOutfit.listing != "",
                                                  LauraOutfit.listing != listing,
                                                  LauraOutfit.outfit_id != row.outfit_id)):
        others.append((f"{o.outfit_id} ({o.listing})", dict(o.garments or {})))
    return too_similar(dict(row.garments or {}), others)


def distinctness(db, outfit_id: str | None, listing: str) -> dict:
    """Outfit distinctness across listings, as a gate reading: PASS, FAIL or UNKNOWN."""
    from .image_records import ensure_tables

    if not outfit_id:
        return _result(UNKNOWN, "no outfit id; distinctness cannot be measured")
    ensure_tables(db)
    with db.session() as s:
        row = _row(s, str(outfit_id).strip().lower())
        if row is None or not row.garments:
            return _result(UNKNOWN, f"outfit {outfit_id!r} has no registered garments")
        near = _too_similar(s, row, listing)
    if near is not None:
        return _result(FAIL, f"not distinct from {near['against']} (similarity "
                             f"{near['score']} >= {_max_sim()})", codes=["WARDROBE_REPETITION"],
                       similarity=near)
    return _result(PASS, "distinct from every other listing's outfit and from the reference "
                         "clothing")


# ---- outfit reference and the wardrobe editor (W-VISNEXT; OWNERIMG E6/E7) ----------------

def set_approved_reference(db, outfit_id: str, image_sha256: str, *, by: str) -> dict:
    """Make one generated Laura image this outfit's approved reference (OWNERIMG E6).

    Only an image of this outfit that the vision judge read as wearing it qualifies: a stored
    candidate with the same outfit id whose `outfit_consistency` PASSed and whose identity and
    body proportions did not FAIL. The reference fixes the clothes for later frames; it is
    never an identity reference (the canonical three stay the only ones)."""
    from .image_records import ImageCandidate, ensure_tables
    from sqlalchemy import select

    sha = str(image_sha256 or "").strip().lower()
    if not _SHA.match(sha):
        raise OutfitRefused("an outfit reference is a sha256 of a stored candidate image")
    if not str(by or "").strip():
        raise OutfitRefused("an outfit reference names who set it")
    from . import canonical

    if sha in set(canonical.CURRENT_REFERENCE_HASHES.values()):
        raise OutfitRefused("Laura's canonical identity references are not outfit references")
    ensure_tables(db)
    with db.session() as s:
        row = _row(s, str(outfit_id or "").strip().lower())
        if row is None:
            raise OutfitRefused(f"no outfit {outfit_id!r}")
        if row.approval_state != "approved":
            raise OutfitRefused(f"{row.outfit_id} is {row.approval_state}, not approved")
        cands = list(s.scalars(select(ImageCandidate).where(ImageCandidate.sha256 == sha)))
        ok = [c for c in cands if c.outfit_id == row.outfit_id and c.laura_present
              and ((c.checks or {}).get("outfit_consistency") or {}).get("status") == PASS
              and ((c.checks or {}).get("identity") or {}).get("status") != FAIL
              and ((c.checks or {}).get("body_proportions") or {}).get("status") != FAIL]
        if not ok:
            raise OutfitRefused(
                "no stored image of this outfit was read by the vision judge as wearing it "
                "(outfit_consistency PASS, identity and body proportions not FAIL)")
        row.approved_reference = sha
        row.reference_hashes = sorted(set(list(row.reference_hashes or []) + [sha]))
        return {**_view(row), "set_by": str(by)[:120]}


def wardrobe_editor(db) -> dict:
    """What the Command Center wardrobe editor shows: every outfit with its listing, state,
    distinctness and reference; the catalogue the selector draws from; the reference clothing
    no listing may wear; and the similarity rule."""
    from . import wardrobe as W

    rows = registry(db)
    out = []
    for o in rows:
        d = distinctness(db, o["outfit_id"], o.get("listing") or "") if o.get("garments") \
            else {"status": UNKNOWN}
        out.append({**o, "distinctness": {"status": d.get("status"), "why": d.get("why")}})
    return {"outfits": out, "slots": list(W.SLOTS),
            "catalogue": {s: [g for g, _, _ in W.CATALOGUE[s]] for s in W.SLOTS},
            "reference_clothing": dict(W.REFERENCE_OUTFIT),
            "max_similarity": W.MAX_SIMILARITY, "weights": dict(W.WEIGHTS),
            "rules": ["one complete outfit per listing; never reused across listings",
                      "the canonical references' clothing is never an outfit",
                      f"two outfits are distinct when their weighted similarity is below "
                      f"{W.MAX_SIMILARITY}",
                      "an outfit is styling, never identity"]}
