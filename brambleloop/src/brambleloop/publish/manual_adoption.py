"""E-4 / W-ADOPT: link an Etsy listing the owner made by hand to its certified release.

The owner publishes the first listings manually in Etsy Shop Manager. Before this module a
hand-made listing had no path into Brambleloop's records: the census reported it as
`etsy.unexpected_listing:<id>`, its orders were "unmatched", the stats export could match it
only on an exact title, and once the gates cleared `store.publish` would have created a
**second** Etsy listing for the same release.

`adopt(...)` is the owner-authorised action `listing.adopt_manual` (Command Center, owner
session + CSRF + nonce + step-up, `app.command_center.approvals`). It:

1. resolves the certified release exactly as the publication authority does (a certified
   `PatternVersion` with that release hash, and the drafted `Listing` bound to it);
2. **reads** the listing from Etsy with the sanctioned read credential and read path
   (`runtime.etsy_ops.build_client`, `Authority.READ` only): existence, shop ownership,
   state, title, description, price, tags, taxonomy, images and files;
3. compares what Etsy holds with the certified listing and package -- title, description,
   price against the plan band, tags, taxonomy, disclosures, file names / sizes / count, and
   the file hash where readable (Etsy's ShopListingFile carries no hash, so byte identity is
   recorded as NOT READABLE, never as matched). Differences are recorded and open a review
   item; they do not block adoption (the listing is already live; refusing to record it
   would only keep the duplicate-listing risk alive);
4. writes the Etsy id where the automated path writes it (`Listing.etsy_listing_id`, as in
   `draft_intent.checkpoint` / `runtime.pipeline` after create), sets
   `Listing.state = "published_manually"`, and records a `DraftIntent` in state
   `ADOPTED_MANUAL` carrying the remote id -- the unique (slug, version) intent row that makes
   `store.publish` refuse another create even if the listing row were later cleared;
5. audits `listing.adopted_manual` with the full verification record.

If Etsy cannot be read (no credential, an auth failure, any error) the adoption is recorded
as **UNVERIFIED**, never VERIFIED, and a review item says so. A listing Etsy reports as not
found (404) or as belonging to another shop is refused: there is nothing of ours to adopt.

**Read-only against Etsy.** This module calls only the client's read methods; it never
creates, updates, uploads or deletes. The tests assert zero non-GET requests on the transport.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

#: Audit actions.
ADOPTED = "listing.adopted_manual"
REFUSED = "listing.adopt_manual_refused"
#: Lifecycle state values (declared in ops/CONTRACT_CHANGES.md).
LISTING_STATE = "published_manually"
INTENT_STATE = "ADOPTED_MANUAL"
#: The non-halting review item opened when the listing differs from the certified package
#: or could not be read.
REVIEW_PREFIX = "listing.adoption_review:"

VERIFIED = "VERIFIED"
UNVERIFIED = "UNVERIFIED"

#: The states Etsy's census reads; any of them is a listing that exists.
_KNOWN_STATES = ("active", "draft", "inactive", "sold_out", "expired")


class AdoptionRefused(ValueError):
    """The adoption cannot be recorded; the message is owner-facing and stable."""


from sqlalchemy import DateTime as _DateTime, String as _String  # noqa: E402
from sqlalchemy.orm import Mapped as _Mapped, mapped_column as _col  # noqa: E402

from ..core.db import Base as _Base  # noqa: E402
from ..core.models import utcnow as _utcnow  # noqa: E402


class ManualListingClaim(_Base):
    """SECREVIEW F-3: one Etsy listing id belongs to at most one release, enforced by the
    database. Written in the same transaction as the adoption, so two concurrent adoptions
    of one id for two releases cannot both commit (the primary key refuses the second)."""

    __tablename__ = "manual_listing_claims"
    etsy_listing_id: _Mapped[str] = _col(_String(32), primary_key=True)
    slug: _Mapped[str] = _col(_String(80))
    version: _Mapped[str] = _col(_String(20))
    at: _Mapped[datetime] = _col(_DateTime(timezone=True), default=_utcnow)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_id(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    if not text.isdigit() or len(text) > 20:
        raise AdoptionRefused("etsy_listing_id must be the numeric id from the listing URL")
    return text


# ---- the certified release ------------------------------------------------------------


def _certified(db, slug: str, version: str, release: str) -> dict:
    """The certified release and its drafted listing, or AdoptionRefused."""
    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion, Product

    if not slug or not version or not release:
        raise AdoptionRefused("slug, version and certified release hash are required")
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = (s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                    PatternVersion.version == version))
              if product is not None else None)
        if pv is None or not pv.certified or pv.release_hash != release:
            raise AdoptionRefused("no certified release with that hash for this version")
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
        if listing is None or listing.release_hash != release:
            raise AdoptionRefused("no drafted listing bound to that certified release")
        return {"listing_id": listing.id, "title": listing.title,
                "description": listing.description, "tags": list(listing.tags or []),
                "price_cad": float(listing.price_cad or 0.0), "state": listing.state,
                "etsy_listing_id": str(listing.etsy_listing_id or "")}


def _certified_files(db, slug: str, version: str, release: str) -> dict[str, dict]:
    """terminology -> {name, sha256, bytes} from the `assets.built` record for this release."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..runtime.pipeline import _certified_pdf_hashes

    try:
        from .pdf import TERMINOLOGIES, pattern_filename
    except Exception:  # noqa: BLE001 - the renderer is not needed to name the files
        TERMINOLOGIES = ("US", "UK")

        def pattern_filename(t: str) -> str:
            return f"pattern-{t.lower()}.pdf"
    hashes = _certified_pdf_hashes(db, slug, version, release) or {}
    sizes: dict[str, int] = {}
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(
            AuditLog.action == "assets.built", AuditLog.artifact == f"{slug}@{version}")
            .order_by(desc(AuditLog.id)))
        for t, stored in ((row.detail or {}).get("pdfs") or {}).items() if row else ():
            if (stored or {}).get("sha256") == hashes.get(t) and stored.get("bytes"):
                sizes[t] = int(stored["bytes"])
    return {t: {"name": f"{slug}-{pattern_filename(t)}", "sha256": hashes.get(t),
                "bytes": sizes.get(t)} for t in TERMINOLOGIES}


def _plan_band(slug: str) -> dict:
    try:
        from ..products import launch0

        plan = launch0.launch_price(slug)
    except Exception as e:  # noqa: BLE001 - an unreadable plan is UNKNOWN, not a pass
        return {"known": False, "why": f"price plan unreadable: {type(e).__name__}"}
    if not plan:
        return {"known": False, "why": "no Launch-0 price plan for this slug"}
    low, high = plan["band_cad"]
    return {"known": True, "low_cad": float(low), "high_cad": float(high),
            "planned_cad": float(plan["price_cad"]), "basis": plan.get("basis", "")}


def _certified_taxonomy(db, slug: str, version: str) -> dict:
    try:
        from ..commerce import category

        sel = category.publish_inputs(db, slug=slug, version=version)
    except Exception as e:  # noqa: BLE001
        return {"known": False, "why": f"category unreadable: {type(e).__name__}"}
    if sel.get("status") != category.CHOSEN or not sel.get("taxonomy_id"):
        return {"known": False, "why": f"certified category {sel.get('status') or 'UNKNOWN'}"}
    return {"known": True, "taxonomy_id": int(sel["taxonomy_id"]),
            "properties": sel.get("properties")}


# ---- reading Etsy ---------------------------------------------------------------------


def _transport():
    """The production transport. A seam so tests count requests; never overridden in src/."""
    from ..integrations.http import UrllibTransport

    return UrllibTransport()


def _client(db, transport):
    from ..core import phase as phase_mod
    from ..runtime.etsy_ops import build_client

    try:
        phase = phase_mod.effective(db, record_incident=False)
    except Exception:  # noqa: BLE001 - an unreadable phase is shadow; reads need no phase
        phase = phase_mod.DEFAULT
    # owner_authorised stays False: this client is used for reads only, and every write
    # method refuses without a grant regardless.
    return build_client(db, phase, owner_authorised=False, transport=transport)


def _price(remote: dict) -> dict:
    p = remote.get("price")
    if isinstance(p, dict) and p.get("amount") is not None and p.get("divisor"):
        return {"amount": round(float(p["amount"]) / float(p["divisor"]), 2),
                "currency": str(p.get("currency_code") or "")}
    if isinstance(p, (int, float)):
        return {"amount": float(p), "currency": ""}
    return {"amount": None, "currency": ""}


def read_listing(db, listing_id: str, *, transport=None) -> dict:
    """What Etsy holds for `listing_id`, read-only. Never raises for an Etsy failure.

    Returns {"read": bool, "exists", "own_shop", "remote", "files", "images", "error"}.
    """
    from ..integrations.etsy import EtsyRejected

    out: dict[str, Any] = {"read": False, "exists": None, "own_shop": None, "remote": {},
                           "files": None, "images": None, "error": "", "calls": []}
    try:
        client = _client(db, transport or _transport())
    except Exception as e:  # noqa: BLE001 - no client is an unread listing
        out["error"] = f"client unavailable: {type(e).__name__}: {str(e)[:160]}"
        return out
    if client is None or client.credentials is None:
        out["error"] = "no Etsy read credential in this environment; nothing was read"
        return out
    try:
        try:
            remote = client.get_listing(listing_id, includes=("Images",))
        except EtsyRejected as e:
            if "returned 404 " in str(e):
                out.update(read=True, exists=False, error="Etsy reports no such listing (404)")
                return out
            raise
        out["remote"] = remote if isinstance(remote, dict) else {}
        out["exists"] = True
        shop = str(client.credentials.shop_id or "")
        held = str(out["remote"].get("shop_id") or "")
        out["own_shop"] = bool(shop and held and held == shop) if held else None
        try:
            out["properties"] = client.get_listing_properties(listing_id)
        except Exception as e:  # noqa: BLE001 - unread properties are recorded, not fatal
            out["properties_error"] = f"{type(e).__name__}: {str(e)[:160]}"
        try:
            out["files"] = client.get_listing_files(listing_id)
        except Exception as e:  # noqa: BLE001 - files unread is recorded, not fatal
            out["files_error"] = f"{type(e).__name__}: {str(e)[:160]}"
        imgs = out["remote"].get("images")
        if isinstance(imgs, list):
            out["images"] = imgs
        else:
            try:
                out["images"] = client.get_listing_images(listing_id)
            except Exception as e:  # noqa: BLE001
                out["images_error"] = f"{type(e).__name__}: {str(e)[:160]}"
        out["read"] = True
    except Exception as e:  # noqa: BLE001 - any failure is UNVERIFIED, never verified
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        out["read"] = False
    finally:
        out["calls"] = [{"method": c.get("method"), "operation": c.get("operation"),
                         "status": c.get("status")} for c in getattr(client, "calls", [])]
    return out


# ---- comparison -----------------------------------------------------------------------


def compare(db, *, slug: str, version: str, release: str, certified: dict,
            read: dict) -> dict:
    """The observed listing against the certified listing and package. Pure reads."""
    remote = read.get("remote") or {}
    observed = {
        "state": str(remote.get("state") or ""),
        "title": remote.get("title"),
        "price": _price(remote),
        "tags": list(remote.get("tags") or []),
        "taxonomy_id": remote.get("taxonomy_id"),
        "image_count": (len(read["images"]) if isinstance(read.get("images"), list)
                        else None),
        "file_count": (len(read["files"]) if isinstance(read.get("files"), list) else None),
        "files": [{"name": f.get("filename"), "bytes": f.get("size_bytes")}
                  for f in (read.get("files") or [])],
        "url": remote.get("url"),
        "created_timestamp": remote.get("original_creation_timestamp")
        or remote.get("created_timestamp"),
    }
    diffs: list[dict] = []
    not_verifiable: list[str] = []

    def diff(field: str, certified_value, etsy_value, note: str = "") -> None:
        diffs.append({"field": field, "certified": certified_value, "etsy": etsy_value,
                      "note": note})

    if observed["title"] != certified["title"]:
        diff("title", certified["title"], observed["title"])
    if isinstance(remote.get("description"), str) and \
            remote["description"].strip() != (certified["description"] or "").strip():
        diff("description", f"stored Listing.description ({len(certified['description'] or '')}"
             f" chars)", f"{len(remote['description'])} chars",
             "the listing description differs from the stored, certified copy")
    if sorted(t.lower() for t in observed["tags"]) != \
            sorted(t.lower() for t in certified["tags"]):
        diff("tags", certified["tags"], observed["tags"])

    band = _plan_band(slug)
    price = observed["price"]
    if price["amount"] is None:
        not_verifiable.append("price: Etsy returned no readable price")
    elif price["currency"] and price["currency"] != "CAD":
        diff("price", f"CA${certified['price_cad']:.2f}",
             f"{price['amount']:.2f} {price['currency']}",
             "shop currency is not CAD; the plan band (CAD) cannot be compared")
    else:
        if band["known"] and not (band["low_cad"] <= price["amount"] <= band["high_cad"]):
            diff("price", f"plan band CA${band['low_cad']:.2f}-{band['high_cad']:.2f}",
                 price["amount"], "outside the plan band")
        elif not band["known"]:
            not_verifiable.append(f"price plan band: {band['why']}")
        if abs(price["amount"] - certified["price_cad"]) > 0.005:
            diff("price", certified["price_cad"], price["amount"],
                 "differs from the stored listing price")

    tax = _certified_taxonomy(db, slug, version)
    if tax["known"]:
        if observed["taxonomy_id"] is None or int(observed["taxonomy_id"]) != tax["taxonomy_id"]:
            diff("taxonomy_id", tax["taxonomy_id"], observed["taxonomy_id"])
        # SECREVIEW F-2: listing properties against the certified category's, as the
        # census compares them; unread is not compared, never matched.
        from ..runtime.etsy_ops import canonical_properties

        try:
            want_props = canonical_properties(tax.get("properties"))
            got_props = (canonical_properties(read["properties"])
                         if isinstance(read.get("properties"), list) else None)
        except ValueError as e:
            want_props, got_props = None, None
            not_verifiable.append(f"properties: {e}")
        if got_props is None and want_props is not None:
            not_verifiable.append("properties: getListingProperties was not read")
        elif want_props is not None and got_props != want_props:
            diff("properties", want_props, got_props)
    else:
        not_verifiable.append(f"taxonomy: {tax['why']}; Etsy holds "
                              f"{observed['taxonomy_id']!r}")

    try:
        from ..runtime.etsy_ops import disclosure_on_remote

        disclosure = disclosure_on_remote(remote)
    except Exception as e:  # noqa: BLE001
        disclosure = {"checked": False, "why": f"{type(e).__name__}"}
    if not disclosure.get("checked"):
        not_verifiable.append(f"disclosures: {disclosure.get('why')}")
    elif not disclosure.get("complete"):
        diff("disclosures", "every required disclosure present and placed",
             {"missing": disclosure.get("missing"), "misplaced": disclosure.get("misplaced")})

    expected_files = _certified_files(db, slug, version, release)
    if observed["file_count"] is None:
        not_verifiable.append("digital files: getAllListingFiles was not read")
    else:
        held = {f["name"]: f for f in observed["files"]}
        if observed["file_count"] != len(expected_files):
            diff("file_count", len(expected_files), observed["file_count"])
        for t, want in sorted(expected_files.items()):
            got = held.get(want["name"])
            if got is None:
                diff(f"file:{t}", want["name"], sorted(held), "certified file name not found")
            elif want["bytes"] and got.get("bytes") is not None \
                    and int(got["bytes"]) != int(want["bytes"]):
                diff(f"file:{t}:bytes", want["bytes"], got["bytes"],
                     "size differs from the certified file, so the bytes differ")
        not_verifiable.append(
            "digital file hash: NOT READABLE -- Etsy's ShopListingFile carries no hash, so "
            "byte identity with the certified PDFs cannot be observed through the API")
    return {"observed": observed, "differences": diffs, "not_verifiable": not_verifiable,
            "certified": {"title": certified["title"], "tags": certified["tags"],
                          "price_cad": certified["price_cad"], "plan_band": band,
                          "taxonomy": tax, "files": expected_files},
            "disclosure": disclosure}


# ---- the action -----------------------------------------------------------------------


def _audit(db, actor: str, action: str, artifact: str, detail: dict) -> int:
    from ..core.models import AuditLog

    with db.session() as s:
        row = AuditLog(actor=str(actor)[:64], action=action, artifact=artifact[:200],
                       detail=detail)
        s.add(row)
        s.flush()
        return row.id


def _refuse(db, actor: str, artifact: str, why: str, **detail) -> None:
    _audit(db, actor, REFUSED, artifact, {"reason": why, **detail})
    raise AdoptionRefused(why)


def adoption_for(db, slug: str, version: str) -> dict | None:
    """The recorded manual adoption for (slug, version), or None."""
    from .draft_intent import DraftIntent, key_for

    with db.session() as s:
        intent = s.get(DraftIntent, key_for(slug, version))
        if intent is None or intent.state != INTENT_STATE:
            return None
        return {"slug": slug, "version": version, "release": intent.release,
                "etsy_listing_id": intent.remote_id, **dict(intent.detail or {})}


def adopted_states(db) -> dict[str, str]:
    """Etsy listing id -> the remote state the census should expect, for adopted listings."""
    from sqlalchemy import select

    from .draft_intent import DraftIntent

    out: dict[str, str] = {}
    with db.session() as s:
        for i in s.scalars(select(DraftIntent).where(DraftIntent.state == INTENT_STATE)):
            if i.remote_id:
                out[str(i.remote_id)] = str((i.detail or {}).get("expected_remote_state")
                                            or "active")
    return out


def _review(db, *, slug: str, version: str, listing_id: str, verification: str,
            differences: list, not_verifiable: list, error: str) -> int | None:
    """Open (or restate) the non-halting review item; resolve it when nothing is left."""
    from ..ops import incident_lifecycle as lifecycle
    from ..core.models import Incident
    from sqlalchemy import select

    signature = f"{REVIEW_PREFIX}{slug}@{version}"
    with db.session() as s:
        if verification == VERIFIED and not differences:
            row = s.scalar(select(Incident).where(Incident.signature == signature,
                                                  Incident.resolved.is_(False)))
            if row is not None:
                row.resolved = True
            return None
        parts = []
        if verification != VERIFIED:
            parts.append(f"Etsy could not be read ({error or 'unknown'}); the adoption is "
                         f"UNVERIFIED")
        if differences:
            parts.append("differs from the certified package: " + "; ".join(
                f"{d['field']}" + (f" ({d['note']})" if d.get("note") else "")
                for d in differences[:6]))
        summary = (f"Manually published Etsy listing {listing_id} adopted for "
                   f"{slug}@{version}: " + ". ".join(parts) + ". Review it in Shop Manager "
                   f"and reconcile deliberately; nothing here writes to Etsy.")
        row, new = lifecycle.open_or_restate(
            s, signature=signature, severity="P2", product_slug=slug,
            halts_publication=False, summary=summary,
            detail={"listing_id": listing_id, "verification": verification,
                    "differences": differences[:20], "not_verifiable": not_verifiable[:10]})
        if not new:
            row.summary = summary[:2000]     # the latest verification, not the first one
        return row.id


def adopt(db, *, etsy_listing_id: Any, slug: str, version: str, release: str,
          actor: str, reason: str = "", transport=None) -> dict:
    """Record a hand-made Etsy listing as the listing of a certified release.

    Idempotent: the same (listing, slug, version, release) again returns the recorded
    adoption (re-reading Etsy only when the earlier one was UNVERIFIED). A different listing
    for an adopted or published release, or a listing already linked elsewhere, is refused.
    """
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from ..core.models import Listing
    from .draft_intent import DraftIntent, key_for

    slug = str(slug or "").strip()
    version = str(version or "").strip()
    release = str(release or "").strip()
    artifact = f"{slug}@{version}"
    try:
        lid = _clean_id(etsy_listing_id)
    except AdoptionRefused as e:
        _refuse(db, actor, artifact, str(e))
    try:
        certified = _certified(db, slug, version, release)
    except AdoptionRefused as e:
        _refuse(db, actor, artifact, str(e), etsy_listing_id=lid, release=release)

    # Duplicate / conflict checks before any read: an existing intent decides.
    key = key_for(slug, version)
    with db.session() as s:
        intent = s.get(DraftIntent, key)
        prior = None if intent is None else {"state": intent.state,
                                             "remote_id": str(intent.remote_id or ""),
                                             "release": intent.release,
                                             "detail": dict(intent.detail or {})}
        other = s.scalar(select(Listing).where(Listing.etsy_listing_id == lid,
                                               Listing.id != certified["listing_id"]))
        other_art = f"{other.product_slug}@{other.version}" if other is not None else ""
    if other_art:
        _refuse(db, actor, artifact, f"Etsy listing {lid} is already linked to {other_art}",
                etsy_listing_id=lid)
    repeat = False
    if prior is not None:
        if prior["state"] != INTENT_STATE:
            _refuse(db, actor, artifact,
                    f"{artifact} already has an automated creation intent "
                    f"({prior['state']}, remote {prior['remote_id'] or 'unknown'}); it must "
                    f"be reconciled, not adopted over", etsy_listing_id=lid)
        if prior["remote_id"] != lid or prior["release"] != release:
            _refuse(db, actor, artifact,
                    f"{artifact} is already adopted as Etsy listing {prior['remote_id']}; "
                    f"one release has one listing", etsy_listing_id=lid)
        repeat = True
        if prior["detail"].get("verification") == VERIFIED:
            audit_id = _audit(db, actor, ADOPTED, artifact, {
                "etsy_listing_id": lid, "slug": slug, "version": version,
                "release": release, "repeat": True, "changed": False,
                "verification": VERIFIED, "reason": reason[:300],
                "note": "already adopted and verified; nothing changed, Etsy not re-read"})
            return {"adopted": True, "repeat": True, "changed": False,
                    "etsy_listing_id": lid, "slug": slug, "version": version,
                    "verification": VERIFIED, "audit_id": audit_id,
                    "differences": prior["detail"].get("differences", []),
                    "review_incident_id": prior["detail"].get("review_incident_id")}
    elif certified["etsy_listing_id"]:
        _refuse(db, actor, artifact,
                f"{artifact} is already linked to Etsy listing "
                f"{certified['etsy_listing_id']} by the automated path", etsy_listing_id=lid)

    read = read_listing(db, lid, transport=transport)
    if read["read"] and read["exists"] is False:
        _refuse(db, actor, artifact, f"Etsy reports no listing {lid}", etsy_listing_id=lid,
                calls=read["calls"])
    if read["read"] and read["own_shop"] is False:
        _refuse(db, actor, artifact,
                f"Etsy listing {lid} belongs to another shop; it cannot be adopted",
                etsy_listing_id=lid, calls=read["calls"])
    verification = VERIFIED if read["read"] and read["own_shop"] is True else UNVERIFIED
    if read["read"] and read["own_shop"] is None:
        read["error"] = "Etsy returned no shop_id, so ownership could not be confirmed"
    result = (compare(db, slug=slug, version=version, release=release, certified=certified,
                      read=read)
              if read["read"] else
              {"observed": {}, "differences": [], "not_verifiable": [
                  "the listing was not read from Etsy; nothing was compared"],
               "certified": {}, "disclosure": {}})
    state = result["observed"].get("state") or ""
    expected_state = state if verification == VERIFIED and state in _KNOWN_STATES \
        else "active"
    record = {
        "verification": verification, "read_error": read["error"][:300],
        "etsy_calls": read["calls"], "observed": result["observed"],
        "differences": result["differences"], "not_verifiable": result["not_verifiable"],
        "certified": result["certified"], "disclosure": result["disclosure"],
        "expected_remote_state": expected_state,
        "verified_at": _now().isoformat(), "adopted_by": actor, "reason": reason[:300]}

    try:
        with db.session() as s:
            listing = s.get(Listing, certified["listing_id"])
            # F-3: re-checked inside the write transaction; the claim row below makes the
            # database refuse the race this check alone could still lose.
            taken = s.scalar(select(Listing).where(Listing.etsy_listing_id == lid,
                                                   Listing.id != listing.id))
            if taken is not None:
                raise AdoptionRefused(f"Etsy listing {lid} is already linked to "
                                      f"{taken.product_slug}@{taken.version}")
            claim = s.get(ManualListingClaim, lid)
            if claim is not None and (claim.slug, claim.version) != (slug, version):
                raise AdoptionRefused(f"Etsy listing {lid} is already linked to "
                                      f"{claim.slug}@{claim.version}")
            if repeat:
                if claim is None:   # N-5: backfill an adoption recorded before claims existed
                    s.add(ManualListingClaim(etsy_listing_id=lid, slug=slug, version=version))
                intent = s.get(DraftIntent, key)
                adopted_at = (intent.detail or {}).get("adopted_at") or record["verified_at"]
                intent.detail = {**record, "adopted_at": adopted_at,
                                 "previous_verification": (intent.detail or {})
                                 .get("verification")}
            else:
                digest = hashlib.sha256(json.dumps(
                    [slug, version, release, lid], separators=(",", ":")).encode()).hexdigest()
                s.add(DraftIntent(key=key, slug=slug, version=version, release=release,
                                  content_digest=digest, token=f"manual:{uuid.uuid4().hex}"[:64],
                                  state=INTENT_STATE, remote_id=lid,
                                  detail={**record, "adopted_at": record["verified_at"]}))
                if listing.etsy_listing_id and listing.etsy_listing_id != lid:
                    raise AdoptionRefused("the listing gained a different Etsy id meanwhile")
                if claim is None:
                    s.add(ManualListingClaim(etsy_listing_id=lid, slug=slug, version=version))
            # Exactly where the automated path writes it (draft_intent.checkpoint).
            listing.etsy_listing_id = lid
            listing.state = LISTING_STATE
    except IntegrityError:
        # A concurrent adoption won the unique (slug, version) intent or the unique Etsy id.
        _refuse(db, actor, artifact, f"{artifact} or Etsy listing {lid} was claimed by a "
                f"concurrent adoption or creation; retry to see which", etsy_listing_id=lid)
    except AdoptionRefused as e:
        _refuse(db, actor, artifact, str(e), etsy_listing_id=lid)

    # The review item only for an adoption that was actually recorded.
    review_id = _review(db, slug=slug, version=version, listing_id=lid,
                        verification=verification, differences=result["differences"],
                        not_verifiable=result["not_verifiable"], error=read["error"])
    record["review_incident_id"] = review_id
    with db.session() as s:
        intent = s.get(DraftIntent, key)
        intent.detail = {**(intent.detail or {}), "review_incident_id": review_id}

    audit_id = _audit(db, actor, ADOPTED, artifact, {
        "etsy_listing_id": lid, "slug": slug, "version": version, "release": release,
        "repeat": repeat, "changed": True, **record})
    return {"adopted": True, "repeat": repeat, "changed": True, "etsy_listing_id": lid,
            "slug": slug, "version": version, "verification": verification,
            "state_on_etsy": state or None, "differences": result["differences"],
            "not_verifiable": result["not_verifiable"], "review_incident_id": review_id,
            "audit_id": audit_id}


# ---- W-ADOPT-2: the owner-accepted baseline -------------------------------------------
#
# The owner hand-edits listings in Shop Manager. Until a baseline is accepted, the census
# compares an adopted listing with its certified payload, and any difference is the P1,
# publication-halting `etsy.listing_drift:<id>`. `accept_baseline` lets the owner -- explicitly,
# with step-up, against a digest of exactly what they previewed -- accept the live copy as the
# expected baseline for that listing. From then on the census compares the live listing with
# the accepted baseline, so only genuinely new drift raises `etsy.listing_drift`.
#
# Acceptance is refused (and the review incident kept open) when the live copy contradicts
# Product Truth (the multiplicity, assembly and motif promises the CIR must back) or drops a
# required disclosure (the buyer-trust set, and the AI-assistance sentence verbatim). Nothing
# is ever accepted automatically.

BASELINE_ACCEPTED = "listing.baseline_accepted"
BASELINE_REFUSED = "listing.baseline_refused"
#: The listing fields a baseline fixes. State is not copy: the census checks it separately.
BASELINE_FIELDS = ("title", "description", "tags", "price", "taxonomy_id")


def snapshot(remote: dict) -> dict:
    """The copy fields of a listing as Etsy holds it, normalised for comparison."""
    price = _price(remote)
    return {"title": remote.get("title"),
            "description": remote.get("description"),
            "tags": sorted(str(t).strip().lower() for t in (remote.get("tags") or [])),
            "price": {"amount": price["amount"], "currency": price["currency"]},
            "taxonomy_id": (int(remote["taxonomy_id"]) if str(remote.get("taxonomy_id") or "")
                            .isdigit() else remote.get("taxonomy_id"))}


def digest_of(snap: dict) -> str:
    return hashlib.sha256(json.dumps(snap, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def baseline_drift(baseline: dict, remote: dict) -> list[str]:
    """What changed on Etsy since the owner accepted the baseline (census, F-544)."""
    want = (baseline or {}).get("snapshot") or {}
    got = snapshot(remote or {})
    out = []
    for field in BASELINE_FIELDS:
        if field not in want:
            continue
        if field == "description" and not isinstance(got.get(field), str):
            out.append("description: not returned")
            continue
        if got.get(field) != want.get(field):
            shown = (lambda v: f"{len(v)} chars" if isinstance(v, str) and len(v) > 80
                     else repr(v))
            out.append(f"{field}: accepted baseline {shown(want.get(field))}, Etsy holds "
                       f"{shown(got.get(field))}")
    return out


def accepted_baselines(db) -> dict[str, dict]:
    """Etsy listing id -> the accepted baseline, for adopted listings that have one."""
    from sqlalchemy import select

    from .draft_intent import DraftIntent

    out: dict[str, dict] = {}
    with db.session() as s:
        for i in s.scalars(select(DraftIntent).where(DraftIntent.state == INTENT_STATE)):
            base = (i.detail or {}).get("accepted_baseline")
            if i.remote_id and base:
                out[str(i.remote_id)] = dict(base)
    return out


def truth_problems(db, *, slug: str, version: str, snap: dict) -> list[str]:
    """Why this live copy may NOT be accepted: Product Truth or a required disclosure."""
    import dataclasses

    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion, Product

    problems: list[str] = []
    title, description = snap.get("title"), snap.get("description")
    if not isinstance(title, str) or not isinstance(description, str):
        return ["Etsy returned no title/description, so the copy cannot be checked"]
    # Disclosures: the buyer-trust set, run on the copy Etsy holds.
    from ..runtime.etsy_ops import disclosure_on_remote

    found = disclosure_on_remote({"title": title, "description": description})
    if not found.get("checked") or not found.get("complete"):
        problems.append(f"required disclosures missing or misplaced in the live copy: "
                        f"missing {[m.get('disclosure') for m in found.get('missing') or []]}, "
                        f"misplaced {found.get('misplaced') or []}")
    # The AI disclosures, verbatim: ai_assisted_design always (every pattern here is
    # AI-assisted), and any other AI sentence the certified copy carried.
    from ..gates.platform_policy import DISCLOSURES
    from ..gates.policy import AI_DISCLOSURE_KEYS

    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
        certified_copy = listing.description if listing is not None else ""
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = (s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                    PatternVersion.version == version))
              if product is not None else None)
        cir_json = dict(pv.cir_json or {}) if pv is not None else {}
    for key in AI_DISCLOSURE_KEYS:
        sentence = DISCLOSURES[key]
        owed = key == "ai_assisted_design" or sentence in (certified_copy or "")
        if owed and sentence not in description:
            problems.append(f"the AI disclosure {key!r} is not in the live description "
                            f"verbatim: {sentence!r}")
    # Product Truth: every promise the live title, description and tags make is backed.
    try:
        from ..cir.model import CIR
        from ..products import launch0

        cir = CIR.from_dict(cir_json)
        titled = dataclasses.replace(cir, title=title)
        for name, verdict in (("title promise", launch0.title_promise(titled)),
                              ("assembly promise", launch0.assembly_promise(titled)),
                              ("motif promise", launch0.motif_promise(
                                  cir, {"etsy.title": title, "etsy.description": description},
                                  tags={"etsy.tags": list(snap.get("tags") or [])}))):
            if not verdict.get("backed"):
                problems.append(f"Product Truth ({name}): "
                                f"{verdict.get('why') or verdict.get('problems')}")
    except Exception as e:  # noqa: BLE001 - an unchecked promise is not an accepted one
        problems.append(f"Product Truth cannot be checked against the certified CIR: "
                        f"{type(e).__name__}: {str(e)[:160]}")
    return problems


def baseline_preview(db, *, slug: str, version: str, etsy_listing_id: Any,
                     transport=None) -> dict:
    """What accepting would fix as the baseline, with its digest and the checks. Read-only."""
    lid = _clean_id(etsy_listing_id)
    adopted = adoption_for(db, slug, version)
    if adopted is None or str(adopted.get("etsy_listing_id")) != lid:
        raise AdoptionRefused(f"Etsy listing {lid} is not the adopted listing for "
                              f"{slug}@{version}")
    read = read_listing(db, lid, transport=transport)
    if not read["read"] or not read["exists"] or read["own_shop"] is not True:
        raise AdoptionRefused("the live listing could not be read from Etsy (or is not this "
                              "shop's); a baseline is only ever the copy actually read")
    snap = snapshot(read["remote"])
    certified = _certified(db, slug, version, adopted.get("release") or "")
    fresh = compare(db, slug=slug, version=version, release=adopted.get("release") or "",
                    certified=certified, read=read)
    differences = fresh["differences"]
    # SECREVIEW N-2: what this fresh, complete comparison could NOT compare. Never dropped:
    # it is carried into what the baseline does not cover, and into the proof.
    unverified = [n for n in fresh["not_verifiable"]
                  if not str(n).startswith(_STRUCTURAL_NOTES)]
    problems = truth_problems(db, slug=slug, version=version, snap=snap)
    # SECREVIEW N-3: properties are compared against a listing read that includes them, as
    # the census and read_back do; unread properties are said to be unread.
    remote = dict(read["remote"])
    if isinstance(read.get("properties"), list):
        from ..runtime.etsy_ops import canonical_properties

        try:
            remote["properties"] = canonical_properties(read["properties"])
        except ValueError as e:
            unverified.append(f"properties: Etsy returned unreadable properties ({e})")
    else:
        unverified.append("properties: getListingProperties was not read")
    not_covered = not_covered_by_baseline(db, slug=slug, version=version,
                                          remote=remote, differences=differences)
    not_covered += [n for n in unverified if n not in not_covered]
    return {"slug": slug, "version": version, "etsy_listing_id": lid, "snapshot": snap,
            "digest": digest_of(snap), "covers_fields": list(BASELINE_FIELDS),
            "differences_from_certified": differences, "not_verifiable": unverified,
            # F-1: shown to the owner, never accepted: these stay open and visible.
            "not_covered_by_baseline": not_covered,
            "acceptable": not problems, "refusals": problems, "etsy_calls": read["calls"]}


def _field_of(line: str) -> str:
    return str(line).split(":", 1)[0].strip()


def not_covered_by_baseline(db, *, slug: str, version: str, remote: dict,
                            differences: list) -> list[str]:
    """SECREVIEW F-1: every difference a copy baseline does NOT cover, listed for the owner.

    The listing fields outside BASELINE_FIELDS exactly as the census will compare them, plus
    the adoption-time package differences (files, counts) that are not copy.
    """
    from ..runtime import etsy_ops

    known = {"slug": slug, "version": version}
    try:
        etsy_ops.certified_payload(db, slug, version)
        fields = etsy_ops._certified_field_drift(db, known, remote, skip=BASELINE_FIELDS)
    except Exception as e:  # noqa: BLE001
        fields = etsy_ops._policy_field_drift(db, known, remote) + [
            f"properties: no certified payload ({str(e)[:120]}), so listing properties are "
            f"UNVERIFIED"]
    package = [f"{d['field']}: certified {d.get('certified')!r}, Etsy holds {d.get('etsy')!r}"
               for d in differences
               if d.get("field") not in BASELINE_FIELDS and d.get("field") != "disclosures"]
    return fields + package


def accept_baseline(db, *, slug: str, version: str, etsy_listing_id: Any,
                    expected_digest: str, actor: str, reason: str, transport=None) -> dict:
    """The owner accepts the live copy as this adopted listing's baseline. Never automatic."""
    from sqlalchemy import select

    from ..core.models import Incident
    from ..ops import incident_lifecycle as lifecycle
    from .draft_intent import DraftIntent, key_for

    artifact = f"{slug}@{version}"
    if not str(reason or "").strip():
        raise AdoptionRefused("owner decision reason required")
    try:
        shown = baseline_preview(db, slug=slug, version=version,
                                 etsy_listing_id=etsy_listing_id, transport=transport)
    except AdoptionRefused as e:
        _audit(db, actor, BASELINE_REFUSED, artifact, {"reason": str(e)})
        raise
    lid = shown["etsy_listing_id"]
    if expected_digest != shown["digest"]:
        _audit(db, actor, BASELINE_REFUSED, artifact, {
            "reason": "preview changed", "etsy_listing_id": lid, "digest": shown["digest"]})
        raise AdoptionRefused("approval preview changed; review the current content")
    signature = f"{REVIEW_PREFIX}{artifact}"
    if shown["refusals"]:
        _audit(db, actor, BASELINE_REFUSED, artifact, {
            "reason": "the live copy contradicts Product Truth or a required disclosure",
            "etsy_listing_id": lid, "refusals": shown["refusals"], "digest": shown["digest"]})
        with db.session() as s:
            row, new = lifecycle.open_or_restate(
                s, signature=signature, severity="P2", product_slug=slug,
                halts_publication=False,
                summary=(f"Live copy of Etsy listing {lid} ({artifact}) was NOT accepted as "
                         f"its baseline: {'; '.join(shown['refusals'][:3])}. Fix the listing "
                         f"in Shop Manager, then preview and accept again."),
                detail={"listing_id": lid, "baseline_refusals": shown["refusals"][:10]})
            if not new:
                row.summary = (f"Live copy of Etsy listing {lid} ({artifact}) was NOT accepted "
                               f"as its baseline: {'; '.join(shown['refusals'][:3])}")[:2000]
        raise AdoptionRefused("refused: the live copy contradicts Product Truth or a required "
                              "disclosure: " + "; ".join(shown["refusals"][:3]))
    baseline = {"snapshot": shown["snapshot"], "digest": shown["digest"],
                "covers_fields": list(BASELINE_FIELDS),
                "accepted_at": _now().isoformat(), "accepted_by": actor,
                "reason": str(reason)[:300],
                "accepted_differences": [d for d in shown["differences_from_certified"]
                                         if d.get("field") in BASELINE_FIELDS
                                         or d.get("field") == "disclosures"][:20],
                "not_covered": shown["not_covered_by_baseline"][:20],
                # N-2: the fresh comparison's uncompared items, kept for the proof.
                "not_verifiable": shown["not_verifiable"][:20]}
    with db.session() as s:
        intent = s.get(DraftIntent, key_for(slug, version))
        detail = dict(intent.detail or {})
        history = list(detail.get("baseline_history") or [])
        if detail.get("accepted_baseline"):
            history.append({k: detail["accepted_baseline"].get(k)
                            for k in ("digest", "accepted_at", "accepted_by")})
        intent.detail = {**detail, "accepted_baseline": baseline,
                         "baseline_history": history[-20:]}
        resolved, kept = [], []
        resolution = (f"owner accepted the live copy as the baseline (digest "
                      f"{shown['digest'][:12]}, fields {', '.join(BASELINE_FIELDS)}) at "
                      f"{baseline['accepted_at']}")
        # F-1: the halting drift incident is resolved only when every drift it records is a
        # field the owner reviewed and accepted; the review item only when nothing is left
        # outside the baseline. Anything else stays open, restated, and visible.
        drift_row = s.scalar(select(Incident).where(
            Incident.signature == f"etsy.listing_drift:{lid}", Incident.resolved.is_(False)))
        if drift_row is not None:
            recorded = list((drift_row.detail or {}).get("drift") or [])
            if recorded and all(_field_of(d) in BASELINE_FIELDS for d in recorded):
                drift_row.resolved = True
                drift_row.detail = {**(drift_row.detail or {}), "resolution": resolution}
                resolved.append(drift_row.signature)
            else:
                kept.append(drift_row.signature)
        review_row = s.scalar(select(Incident).where(Incident.signature == signature,
                                                     Incident.resolved.is_(False)))
        if baseline["not_covered"]:
            row, _ = lifecycle.open_or_restate(
                s, signature=signature, severity="P2", product_slug=slug,
                halts_publication=False,
                summary="", detail={"listing_id": lid,
                                    "not_covered_by_baseline": baseline["not_covered"]})
            row.summary = (f"Baseline accepted for Etsy listing {lid} ({artifact}) covers "
                           f"{', '.join(BASELINE_FIELDS)} only. Still open, not accepted: "
                           f"{'; '.join(baseline['not_covered'][:4])}")[:2000]
            kept.append(signature)
        elif review_row is not None:
            review_row.resolved = True
            review_row.detail = {**(review_row.detail or {}), "resolution": resolution}
            resolved.append(signature)
    audit_id = _audit(db, actor, BASELINE_ACCEPTED, artifact, {
        "etsy_listing_id": lid, **baseline, "incidents_resolved": resolved,
        "incidents_kept_open": kept})
    return {"accepted": True, "etsy_listing_id": lid, "digest": shown["digest"],
            "covers_fields": list(BASELINE_FIELDS),
            "accepted_differences": baseline["accepted_differences"],
            "not_covered_by_baseline": baseline["not_covered"],
            "incidents_resolved": resolved, "incidents_kept_open": kept,
            "audit_id": audit_id}


# ---- SECREVIEW F-2: what proves a manual listing in a live phase ------------------------

#: Adoption notes that are facts about Etsy's API, not unverified listing content.
_STRUCTURAL_NOTES = ("digital file hash: NOT READABLE",)


def proof_problems(db, *, slug: str, version: str, etsy_listing_id: str) -> list[str]:
    """Why a `published_manually` listing is NOT proven to match its certificate.

    Empty only when the adoption is VERIFIED (read from Etsy, our shop) AND the live listing
    matched the certified release and package -- or every difference is a copy field covered
    by an owner-accepted baseline -- AND nothing was left uncompared, AND no review or drift
    incident is open for it. A recorded difference is never "read back verified".
    """
    from sqlalchemy import select

    from ..core.models import Incident

    adopted = adoption_for(db, slug, version) or {}
    lid = str(etsy_listing_id or "")
    if str(adopted.get("etsy_listing_id") or "") != lid:
        return ["published manually with no adoption record"]
    out = []
    if adopted.get("verification") != VERIFIED:
        out.append("manual adoption UNVERIFIED (not read back)")
    base = adopted.get("accepted_baseline") or {}
    if base:
        uncovered = list(base.get("not_covered") or [])
        # SECREVIEW N-2: a baseline never drops an uncompared item. Its own fresh, complete
        # comparison at acceptance supersedes the adoption's notes; a baseline that recorded
        # none (older shape) falls back to the adoption's notes rather than to nothing.
        notes = (base["not_verifiable"] if "not_verifiable" in base
                 else adopted.get("not_verifiable") or [])
    else:
        uncovered = [f"{d.get('field')}" for d in adopted.get("differences") or []]
        notes = adopted.get("not_verifiable") or []
    uncovered += [n for n in notes
                  if not str(n).startswith(_STRUCTURAL_NOTES) and n not in uncovered]
    if uncovered:
        out.append("the live listing does not match its certificate and no accepted "
                   "baseline covers: " + "; ".join(str(u)[:120] for u in uncovered[:5]))
    with db.session() as s:
        for sig in (f"{REVIEW_PREFIX}{slug}@{version}", f"etsy.listing_drift:{lid}"):
            if s.scalar(select(Incident).where(Incident.signature == sig,
                                               Incident.resolved.is_(False))) is not None:
                out.append(f"open incident {sig}")
    return out
