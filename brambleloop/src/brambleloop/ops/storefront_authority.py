"""Owner/operator-authenticated, content-bound *storefront* write authority (W4-AGENTS).

The storefront counterpart of `publication_authority` and `activation_authority`. The
Storefront Director (`store_foundation.director`) drafts storefront changes as recorded
proposals; a proposal reaches Etsy (`integrations.etsy.EtsyClient.update_shop` /
`create_shop_section`) only under a grant recorded here, and only in a publishing phase:

* **signed** -- Ed25519 over the whole grant with a web-only signing key, verified with the
  public key (M-2), so an edited row, a hand-inserted row or a key rotation invalidates it;
* **content-bound** -- bound to one recorded proposal and the exact change it sends (the Etsy
  operation and every field and value); a different change is refused;
* **expiring** -- 24 hours from approval, never future-dated;
* **revocable** and **chained** -- approvals, revocations and owner rebases form one sealed
  hash chain (`core.sealed_chain.GrantLedger`), exactly as the other two grant families;
* **kill-switched** -- `BRAMBLELOOP_STOREFRONT_WRITES_AUTHORISED` must be "1"; it can only
  deny, never grant.

W4-AGENTS M-1/M-2 (independent review of b5226f7): the approving principal is the owner's
Command Center session after a fresh step-up (never the operator bearer token), and rows are
signed with a web-only Ed25519 key that is not the approval credential; the worker verifies
with the public key only. Nothing here contacts Etsy or enqueues a job; approving a proposal makes the next `store.update`
for it able to run, and nothing else.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ..core import opsauth
from ..core.models import AuditLog

APPROVED = "owner.storefront.approved"
REVOKED = "owner.storefront.revoked"
REBASED = "owner.storefront.rebased"
# W4-AGENTS M-1: the approving principal is the owner's Command Center session after a fresh
# step-up (`app.command_center.approvals` "storefront.approve"), never the operator bearer.
PRINCIPAL = "owner:command-center"
ACTION = "store.update.storefront"
KILL_SWITCH_VAR = "BRAMBLELOOP_STOREFRONT_WRITES_AUTHORISED"
GRANT_HOURS = 24
# W4-AGENTS M-2: the sealing key is NOT the approval credential. Rows are signed with an
# Ed25519 private key that only the web process holds, and verified with the matching public
# key, which is all the worker holds. A process with the verify key (or the ops token) cannot
# mint a grant. Both are base64 of the raw 32-byte keys, set in the environment by the
# operator (`generate_keypair()` prints a pair); neither is ever stored in this repository.
SIGNING_KEY_VAR = "BRAMBLELOOP_STOREFRONT_SIGNING_KEY"
VERIFY_KEY_VAR = "BRAMBLELOOP_STOREFRONT_VERIFY_KEY"


def _now():
    return datetime.now(timezone.utc)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      default=str)


def _b64key(var: str) -> bytes:
    import base64

    raw = os.environ.get(var, "").strip()
    if not raw:
        raise ValueError(f"{var} is not set in this process")
    key = base64.b64decode(raw, validate=True)
    if len(key) != 32:
        raise ValueError(f"{var} must be a base64 32-byte Ed25519 key")
    return key


def _seal(detail):
    """Ed25519 signature over the canonical JSON. Only a process with the signing key can."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    try:
        key = Ed25519PrivateKey.from_private_bytes(_b64key(SIGNING_KEY_VAR))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"storefront signing key unavailable: {exc}") from None
    return key.sign(_json(detail).encode()).hex()


def _verify(detail, seal: str) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        pub = Ed25519PublicKey.from_public_bytes(_b64key(VERIFY_KEY_VAR))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"storefront verify key unavailable: {exc}") from None
    try:
        pub.verify(bytes.fromhex(str(seal)), _json(detail).encode())
        return True
    except (InvalidSignature, ValueError):
        return False


def generate_keypair() -> dict:
    """A fresh (signing, verify) pair as base64, for the operator to set. Never committed."""
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                           serialization.NoEncryption())
    pub = k.public_key().public_bytes(serialization.Encoding.Raw,
                                      serialization.PublicFormat.Raw)
    return {SIGNING_KEY_VAR: base64.b64encode(priv).decode(),
            VERIFY_KEY_VAR: base64.b64encode(pub).decode()}


def digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def kill_switch_refusal() -> str | None:
    """The global environment switch: it may only deny."""
    if os.environ.get(KILL_SWITCH_VAR, "") != "1":
        return (f"global storefront-write kill-switch is off ({KILL_SWITCH_VAR} is not '1'); "
                f"no grant can override it")
    return None


def snapshot(db, proposal: str) -> dict:
    """What a grant binds: the recorded proposal, re-validated now, and its exact change."""
    from ..store_foundation import director

    p = director.proposal(db, proposal)
    if p is None:
        raise ValueError(f"no recorded storefront proposal {proposal!r}")
    if not p.get("api_writable") or not isinstance(p.get("change"), dict):
        raise ValueError("this proposal has no Etsy write API; it is an owner step")
    problems = director.validate_change(db, p["change"], surface=p.get("surface", ""))
    if problems:
        raise ValueError("the proposal no longer validates: " + "; ".join(problems)[:300])
    return {"action": ACTION, "proposal": p["digest"], "surface": p.get("surface"),
            "change": p["change"]}


def approve(db, *, actor, proposal, expected_digest, reason, stepped_up: bool):
    """Record a signed owner grant for exactly the previewed storefront change.

    Reached only from the Command Center action "storefront.approve", which requires the
    owner's session, CSRF/nonce and a fresh step-up before calling this (M-1). There is no
    bearer-token path. Signing needs the web-only signing key (M-2)."""
    from ..laura.private.firewall import reject_private

    reject_private((actor, proposal, expected_digest, reason), context="storefront")
    if stepped_up is not True:
        raise ValueError("a storefront grant needs the owner's fresh step-up")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("owner decision reason required")
    content = snapshot(db, proposal)
    if not hmac.compare_digest(digest(content), str(expected_digest)):
        raise ValueError("approval preview changed; review the current content")
    now = _now()
    detail = {"principal": PRINCIPAL, "actor": str(actor)[:120], "stepped_up": True,
              "action": ACTION, "scope": f"storefront:{proposal}",
              "content": content, "digest": digest(content),
              "change_digest": digest(content["change"]), "reason": reason.strip(),
              "approved_at": now.isoformat(),
              "expires_at": (now + timedelta(hours=GRANT_HOURS)).isoformat()}
    ident = LEDGER.append(db, action=APPROVED, artifact=f"storefront:{proposal}", detail=detail)
    return {"approval_id": ident, "digest": detail["digest"],
            "expires_at": detail["expires_at"], "principal": PRINCIPAL}


def revoke(db, *, approval_id, authorization=None, actor=None):
    """Deny-only: the owner (Command Center) or the operator bearer may revoke."""
    if actor is None:
        opsauth.check(authorization)
    LEDGER.revoke(db, int(approval_id))
    return {"revoked": int(approval_id)}


def rebase(db, *, actor, reason, stepped_up: bool):
    """Owner re-anchors a broken chain (voids every earlier grant). Command Center + step-up."""
    if stepped_up is not True:
        raise ValueError("a chain rebase needs the owner's fresh step-up")
    return {"rebase_id": LEDGER.rebase(db, f"{reason} [owner {str(actor)[:80]}]"),
            "voids_grants_before": True}


def _make_ledger():
    from ..core.sealed_chain import GrantLedger

    return GrantLedger(approved=APPROVED, revoked=REVOKED, rebased=REBASED, principal=PRINCIPAL,
                       seal=_seal, verify=_verify,
                       signature=f"authority_chain_tamper:{ACTION}",
                       label="owner storefront grant")


LEDGER = _make_ledger()


def _check_one(db, ident: int, *, change: dict) -> str | None:
    with db.session() as s:
        row = s.get(AuditLog, ident)
        if row is None or row.action != APPROVED or row.actor != PRINCIPAL:
            return "recorded owner storefront grant required"
        detail = dict(row.detail or {})
    chained = LEDGER.refusal(db, ident)
    if chained is not None:
        return f"owner storefront grant refused: {chained}"
    seal = detail.pop("seal", "")
    try:
        if not _verify(detail, str(seal)):
            return "owner storefront grant signature invalid or key rotated"
    except ValueError as exc:
        return f"owner storefront grant cannot be verified here ({exc})"
    if detail.get("stepped_up") is not True:
        return "owner storefront grant was not made after a step-up"
    now = _now()
    if not (datetime.fromisoformat(detail["approved_at"]) <= now
            < datetime.fromisoformat(detail["expires_at"])):
        return "owner storefront grant expired or future-dated"
    if detail.get("action") != ACTION:
        return "owner grant is not a storefront grant"
    if not hmac.compare_digest(str(detail.get("change_digest") or ""), digest(change)):
        return "owner storefront grant does not cover this exact change"
    return None


def validate(db, approval_id=None, *, change: dict) -> str | None:
    """Fail closed; resolved anew at the execution boundary for the exact change sent."""
    try:
        deny = kill_switch_refusal()
        if deny:
            return deny
        if not isinstance(change, dict) or not change:
            return "a storefront grant is checked against the exact change sent"
        if approval_id is None:
            return "recorded owner storefront grant required"
        return _check_one(db, int(approval_id), change=change)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return f"recorded valid owner storefront grant required ({str(exc)[:200]})"


def resolve(db, proposal: str, change: dict | None = None) -> tuple[str | None, int | None]:
    """(refusal, grant id): the newest grant for this proposal valid now. Fails closed."""
    try:
        deny = kill_switch_refusal()
        if deny:
            return deny, None
        if change is None:
            from ..store_foundation import director

            p = director.proposal(db, proposal)
            change = (p or {}).get("change")
        if not isinstance(change, dict):
            return "no recorded storefront change to grant", None
        with db.session() as s:
            ids = list(s.scalars(select(AuditLog.id).where(
                AuditLog.action == APPROVED, AuditLog.artifact == f"storefront:{proposal}")
                .order_by(AuditLog.id.desc())))
        if not ids:
            return "recorded owner storefront grant required", None
        first = None
        for ident in ids:
            why = _check_one(db, ident, change=change)
            if why is None:
                return None, ident
            first = first or why
        return first, None
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return f"recorded valid owner storefront grant required ({str(exc)[:200]})", None
