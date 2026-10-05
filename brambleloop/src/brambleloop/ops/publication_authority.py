"""Owner/operator-authenticated, content-bound *publication* authority (FB3-P).

The draft-creation counterpart of `activation_authority`. Before this module, the owner's
permission to create an Etsy draft was read only from the environment flag
`BRAMBLELOOP_PUBLISH_AUTHORISED=1`: no record of who granted it, for what, or until when.
A durable grant is now required at the pre-create boundary:

* **sealed** -- HMAC over the whole grant under the ops credential (`BRAMBLELOOP_OPS_TOKEN`),
  so an edited row, a hand-inserted row, or a credential rotation invalidates it;
* **scoped** -- bound to one `slug@version`, its certified release hash, the digest of the
  certified CIR and the exact listing fields that will be sent (taxonomy included);
* **expiring** -- 24 hours from approval, never future-dated;
* **revocable** -- an append-only revocation row, checked at every use;
* **audited** -- approval and revocation are `AuditLog` rows under the owner principal.

The environment flag remains only as a global kill-switch: it can additionally DENY (unset
or anything but "1" refuses every publication) but can no longer grant on its own.

As with activation, the principal is the holder of the ops credential, not a separately
verified natural person. Nothing here contacts Etsy or enqueues a job.
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

APPROVED = "owner.publication.approved"
REVOKED = "owner.publication.revoked"
PRINCIPAL = "owner:ops-token"
ACTION = "store.publish"
KILL_SWITCH_VAR = "BRAMBLELOOP_PUBLISH_AUTHORISED"
GRANT_HOURS = 24


def _now():
    return datetime.now(timezone.utc)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      default=str)


def _seal(detail):
    if not opsauth.configured():
        raise ValueError("owner credential unavailable")
    return hmac.new(os.environ[opsauth.TOKEN_VAR].strip().encode(),
                    _json(detail).encode(), hashlib.sha256).hexdigest()


def digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def kill_switch_refusal() -> str | None:
    """The global environment switch: it may only deny."""
    if os.environ.get(KILL_SWITCH_VAR, "") != "1":
        return (f"global publication kill-switch is off ({KILL_SWITCH_VAR} is not '1'); "
                f"no grant can override it")
    return None


def snapshot(db, slug, version, release):
    """What a grant is bound to: the certified release and the exact fields to be sent."""
    from ..runtime import etsy_ops

    if not slug or not version or not release:
        raise ValueError("slug, version and certified release hash are required")
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = (s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                    PatternVersion.version == version))
              if product is not None else None)
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
        if pv is None or not pv.certified or not pv.cir_json or pv.release_hash != release:
            raise ValueError("no certified release with that hash for this version")
        if listing is None or listing.release_hash != release:
            raise ValueError("no drafted listing bound to that certified release")
        if listing.etsy_listing_id:
            raise ValueError("already on Etsy; publication grants cover draft creation only")
        cir = pv.cir_json
    return {"action": ACTION, "slug": slug, "version": version, "release": release,
            "cir_digest": digest(cir),
            "payload": etsy_ops.sent_fields(etsy_ops.certified_payload(db, slug, version))}


def approve(db, *, authorization, slug, version, release, expected_digest, reason):
    """Record a sealed owner grant for exactly the previewed content."""
    opsauth.check(authorization)
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("owner decision reason required")
    content = snapshot(db, slug, version, release)
    if not hmac.compare_digest(digest(content), str(expected_digest)):
        raise ValueError("approval preview changed; review the current content")
    now = _now()
    detail = {"principal": PRINCIPAL, "action": ACTION, "scope": f"{slug}@{version}",
              "release": release, "content": content, "digest": digest(content),
              "reason": reason.strip(), "approved_at": now.isoformat(),
              "expires_at": (now + timedelta(hours=GRANT_HOURS)).isoformat()}
    detail["seal"] = _seal(detail)
    with db.session() as s:
        row = AuditLog(actor=PRINCIPAL, action=APPROVED, artifact=f"{slug}@{version}",
                       detail=detail)
        s.add(row)
        s.flush()
        return {"approval_id": row.id, "digest": detail["digest"],
                "expires_at": detail["expires_at"], "principal": PRINCIPAL}


def revoke(db, *, authorization, approval_id):
    opsauth.check(authorization)
    with db.session() as s:
        s.add(AuditLog(actor=PRINCIPAL, action=REVOKED, artifact=str(int(approval_id)),
                       detail={"approval_id": int(approval_id)}))
    return {"revoked": int(approval_id)}


def _check_one(db, ident, *, slug, version, release, current):
    with db.session() as s:
        row = s.get(AuditLog, ident)
        if row is None or row.action != APPROVED or row.actor != PRINCIPAL:
            return "recorded owner publication grant required"
        if row.artifact != f"{slug}@{version}":
            return "owner publication grant is for another product or version"
        revoked = s.scalar(select(AuditLog.id).where(AuditLog.action == REVOKED,
                                                    AuditLog.artifact == str(ident)))
        detail = dict(row.detail or {})
    if revoked:
        return "owner publication grant revoked"
    seal = detail.pop("seal", "")
    if not hmac.compare_digest(str(seal), _seal(detail)):
        return "owner publication grant invalid or credential rotated"
    now = _now()
    if not (datetime.fromisoformat(detail["approved_at"]) <= now
            < datetime.fromisoformat(detail["expires_at"])):
        return "owner publication grant expired or future-dated"
    if (detail.get("action") != ACTION or detail.get("scope") != f"{slug}@{version}"
            or detail.get("release") != release):
        return "owner publication grant does not cover this release"
    if digest(current) != detail.get("digest"):
        return "owner publication grant does not match current content"
    return None


def resolve(db, *, slug, version, release, approval_id=None) -> tuple[str | None, int | None]:
    """(refusal, grant id). Fails closed; resolved anew at every execution boundary.

    With `approval_id` only that grant is considered. Without it, the newest grant recorded
    for `slug@version` that is valid now is used, so a queued store.publish need not carry an
    id -- but the grant must still bind this release and the content about to be sent.
    """
    try:
        deny = kill_switch_refusal()
        if deny:
            return deny, None
        current = snapshot(db, slug, version, release)
        if approval_id is not None:
            ident = int(approval_id)
            return _check_one(db, ident, slug=slug, version=version, release=release,
                              current=current), (ident)
        with db.session() as s:
            ids = list(s.scalars(select(AuditLog.id).where(
                AuditLog.action == APPROVED, AuditLog.artifact == f"{slug}@{version}")
                .order_by(AuditLog.id.desc())))
        if not ids:
            return "recorded owner publication grant required", None
        first = None
        for ident in ids:
            why = _check_one(db, ident, slug=slug, version=version, release=release,
                             current=current)
            if why is None:
                return None, ident
            first = first or why
        return first, None
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return f"recorded valid owner publication grant required ({str(exc)[:200]})", None


def validate(db, approval_id=None, *, slug, version, release) -> str | None:
    return resolve(db, slug=slug, version=version, release=release,
                   approval_id=approval_id)[0]
