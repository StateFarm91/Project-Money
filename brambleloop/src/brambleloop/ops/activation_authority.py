"""Owner/operator-authenticated, content-bound activation authority (F-703/F-835).

Uses existing ops credential and append-only audit evidence; this identifies the operator
credential holder, not a separately verified natural person. Rotation invalidates grants.
No endpoint queues or performs an Etsy action. Execution still requires every release gate.

rc1-AUTH D2: approvals, revocations and owner rebases form one sealed hash chain
(`core.sealed_chain.GrantLedger`). A revocation is sealed and bound to the grant's seal; any
revocation row naming a grant revokes it (an unsealed one too, reported as tampering); a
deleted, inserted or replayed row breaks the chain, refusing every activation grant with a P1
tamper incident until the owner rebases.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from ..core import opsauth
from ..core.models import AuditLog, Listing, PatternVersion, Product

APPROVED = "owner.activation.approved"
REVOKED = "owner.activation.revoked"
REBASED = "owner.activation.rebased"
PRINCIPAL = "owner:ops-token"


def _now():
    return datetime.now(timezone.utc)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _seal(detail):
    if not opsauth.configured():
        raise ValueError("owner credential unavailable")
    return hmac.new(os.environ[opsauth.TOKEN_VAR].strip().encode(),
                    _json(detail).encode(), hashlib.sha256).hexdigest()


def snapshot(db, slug, version, release=""):
    from ..runtime import etsy_ops
    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                Listing.version == version))
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                   PatternVersion.version == version)) if product else None
        if listing is None or not listing.etsy_listing_id or listing.state == "active" or pv is None:
            raise ValueError("no inactive recorded listing/release")
        listing_id = str(listing.etsy_listing_id)
        cir = pv.cir_json
    frames = etsy_ops.certified_frames(db, slug, version, release=release)
    files = etsy_ops.published_files(db, slug, version, listing_id)
    if frames["problems"] or not files:
        raise ValueError("certified frames and verified publication files required")
    return {"action": "store.activate", "slug": slug, "version": version,
            "release": release, "listing_id": listing_id, "cir": cir,
            "payload": etsy_ops.sent_fields(etsy_ops.certified_payload(db, slug, version)),
            "frames": frames, "files": files}


def digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def approve(db, *, authorization, slug, version, expected_digest, reason, release=""):
    opsauth.check(authorization)
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("owner decision reason required")
    content = snapshot(db, slug, version, release)
    if not hmac.compare_digest(digest(content), str(expected_digest)):
        raise ValueError("approval preview changed; review the current content")
    now = _now()
    detail = {"principal": PRINCIPAL, "action": "store.activate", "content": content,
              "digest": digest(content), "reason": reason.strip(),
              "approved_at": now.isoformat(), "expires_at": (now + timedelta(hours=24)).isoformat()}
    ident = LEDGER.append(db, action=APPROVED, artifact=f"{slug}@{version}", detail=detail)
    return {"approval_id": ident, "digest": detail["digest"],
            "expires_at": detail["expires_at"], "principal": PRINCIPAL}


def revoke(db, *, authorization, approval_id):
    opsauth.check(authorization)
    LEDGER.revoke(db, int(approval_id))
    return {"revoked": int(approval_id)}


def rebase(db, *, authorization, reason):
    """Owner re-anchors a broken grant chain. Voids every earlier activation grant."""
    opsauth.check(authorization)
    return {"rebase_id": LEDGER.rebase(db, reason), "voids_grants_before": True}


def _make_ledger():
    from ..core.sealed_chain import GrantLedger

    return GrantLedger(approved=APPROVED, revoked=REVOKED, rebased=REBASED, principal=PRINCIPAL,
                       seal=_seal, signature="authority_chain_tamper:store.activate",
                       label="owner activation approval")


LEDGER = _make_ledger()


def validate(db, approval_id, *, slug, version, listing_id, release=""):
    """Fail closed; resolve the durable grant anew at the execution boundary."""
    try:
        ident = int(approval_id)
        with db.session() as s:
            row = s.get(AuditLog, ident)
            if row is None or row.action != APPROVED or row.actor != PRINCIPAL:
                return "recorded Launch-0 owner activation approval required"
            detail = dict(row.detail or {})
        chained = LEDGER.refusal(db, ident)
        if chained is not None:
            return f"owner activation approval refused: {chained}"
        seal = detail.pop("seal", "")
        if not hmac.compare_digest(str(seal), _seal(detail)):
            return "owner activation approval invalid or credential rotated"
        now = _now()
        if not datetime.fromisoformat(detail["approved_at"]) <= now < datetime.fromisoformat(detail["expires_at"]):
            return "owner activation approval expired or future-dated"
        current = snapshot(db, slug, version, release)
        if current["listing_id"] != str(listing_id) or digest(current) != detail["digest"]:
            return "owner activation approval does not match current action/content"
        return None
    except (ValueError, TypeError, KeyError, OverflowError):
        return "recorded valid Launch-0 owner activation approval required"
