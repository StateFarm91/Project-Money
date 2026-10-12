"""Find the Etsy shop id from the owner's own OAuth grant, and bind only the expected shop.

Why this exists (W4-ETSYSHOPID, 2026-10-12). The owner completed the authorization-code grant
and the refresh token is sealed in `oauth_credentials`, but `Credentials.from_env` returned
None because `ETSY_SHOP_ID` was not in the environment -- so every authenticated read said
"no Etsy credentials". The shop's public page is behind anti-bot protection and is not
scraped. The grant itself says whose shop it is:

1. **The user id.** Etsy's OAuth documentation shows access tokens of the form
   `12345678.O1zLuwv...`; the numeric part before the first `.` is the id of the user who
   granted access. When a token has no numeric prefix the documented `getMe`
   (`GET /v3/application/users/me`, scope `shops_r`) answers `user_id` instead.
2. **The shop.** `getShopByOwnerUserId` (`GET /v3/application/users/{user_id}/shops`, scope
   `shops_r`) returns that user's shop: `shop_id`, `shop_name`, `user_id`.
3. **The check.** The shop is bound only when its `shop_name` equals the expected shop
   (`store_foundation.content.ETSY_HANDLE`, "BrambleloopStudio"). Anything else is refused,
   an incident is opened, and nothing is stored: a grant from a different Etsy account must
   never point this company's writes at somebody else's shop.

Two GETs, no writes. The token refresh they may cause is the same persisting, compare-and-set
refresh every other authenticated call uses. No token value reaches the audit row, the
incident or the return value.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

INCIDENT_SIGNATURE = "etsy.shop_binding:mismatch"


def expected_shop_name() -> str:
    from ..store_foundation.content import ETSY_HANDLE

    return ETSY_HANDLE


def bound_shop_id(db) -> str:
    """The stored shop id, only if it was bound to the expected shop name; else "".

    The one answer every "is the shop id known?" check should read besides `ETSY_SHOP_ID`
    (launch.readiness, ops.dependencies, build2.executor, store_readiness). No network.
    """
    if db is None:
        return ""
    from ..core import oauth_store

    binding = oauth_store.load_shop_binding(db) or {}
    if str(binding.get("shop_name") or "") != expected_shop_name():
        return ""
    return str(binding.get("shop_id") or "").strip()


def shop_id_present(db, env: dict[str, str] | None = None) -> bool:
    """`ETSY_SHOP_ID` is set, or a name-verified binding is stored."""
    import os

    e = env if env is not None else os.environ
    return bool((e.get("ETSY_SHOP_ID") or "").strip() or bound_shop_id(db))


def credentials_present(db, env: dict[str, str] | None = None) -> bool:
    """Whether an authenticated Etsy client could be built here, without making a call.

    Keystring, a shop id (env or binding), and a token: a static access token, an
    environment refresh token or a stored refresh token that opens. Presence, not proof.
    """
    import os

    e = env if env is not None else os.environ
    key = (e.get("ETSY_KEYSTRING") or e.get("ETSY_API_KEY") or "").strip()
    if not key or not shop_id_present(db, e):
        return False
    if (e.get("ETSY_ACCESS_TOKEN") or "").strip() or (e.get("ETSY_REFRESH_TOKEN") or "").strip():
        return True
    if db is None:
        return False
    from ..core import oauth_store

    try:
        return bool(oauth_store.load_refresh_token(db, env=e))
    except Exception:  # noqa: BLE001 - an unreadable store is an absent credential
        return False


def _user_id_from_token(token: str) -> str:
    prefix = (token or "").split(".", 1)[0]
    return prefix if prefix.isdigit() else ""


def _audit(db, action: str, detail: dict) -> None:
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="etsy_shop_binding", action=action, detail=detail))


def _refuse(db, detail: dict) -> dict:
    from ..ops import incident_lifecycle as lifecycle

    with db.session() as s:
        lifecycle.open_or_restate(
            s, signature=INCIDENT_SIGNATURE, severity="P1",
            summary=(f"The Etsy grant belongs to shop {detail.get('shop_name')!r}, not the "
                     f"expected {detail.get('expected')!r}; the shop id was NOT bound and "
                     f"authenticated Etsy work stays off until the owner re-authorises from "
                     f"the {detail.get('expected')} account."),
            detail=detail)
    _audit(db, "etsy.shop_resolution_refused", detail)
    return {"status": "refused", **detail}


def resolve(db, credentials: Any, *, transport: Any, phase: str = "shadow") -> dict:
    """Resolve, check and store the shop id. Returns a report that never carries a token.

    `credentials` is the shop-less `Credentials.from_env(..., require_shop=False)`; it must
    hold a `token_provider` (a stored or environment refresh token). Statuses: `resolved`,
    `refused` (wrong shop, incident opened), `no_token`, `unreadable` (Etsy answered nothing
    usable). Etsy errors propagate to the caller unchanged.
    """
    from ..core import oauth_store
    from .etsy import Authority, EtsyClient

    if credentials is None or credentials.token_provider is None:
        return {"status": "no_token"}
    client = EtsyClient(transport, credentials=credentials, phase=phase)
    # Refreshes (and persists the rotation) when the stored token has no live access token.
    token = credentials.token_provider.token(operation="getShopByOwnerUserId")
    user_id, how = _user_id_from_token(token), "access_token_prefix"
    if not user_id:
        me = client.get_me() or {}
        user_id, how = str(me.get("user_id") or "").strip(), "getMe"
    if not user_id:
        return {"status": "unreadable", "reason": "no user id in the token or getMe"}

    body = client._call("GET", f"/users/{user_id}/shops", operation="getShopByOwnerUserId",
                        authority=Authority.READ).body or {}
    if isinstance(body.get("results"), list):
        shops = body["results"]
        body = shops[0] if len(shops) == 1 and isinstance(shops[0], dict) else {}
    shop_id = str(body.get("shop_id") or "").strip()
    shop_name = str(body.get("shop_name") or "").strip()
    owner = str(body.get("user_id") or "").strip()
    expected = expected_shop_name()
    detail = {"shop_id": shop_id, "shop_name": shop_name, "user_id": user_id,
              "how": f"{how} + getShopByOwnerUserId", "expected": expected}
    if not shop_id or not shop_id.isdigit():
        return {"status": "unreadable", **detail,
                "reason": "getShopByOwnerUserId returned no numeric shop_id"}
    if shop_name != expected or (owner and owner != user_id):
        return _refuse(db, {**detail, "owner_user_id": owner})

    oauth_store.save_shop_binding(db, shop_id=shop_id, shop_name=shop_name,
                                  user_id=user_id, how=detail["how"])
    _audit(db, "etsy.shop_resolved", detail)
    from ..ops import incident_lifecycle as lifecycle

    with db.session() as s:
        lifecycle.resolve_signatures(
            s, [INCIDENT_SIGNATURE],
            resolution=f"grant resolved to {shop_name} ({shop_id})")
    log.info("etsy shop bound from the owner's grant: %s (%s)", shop_name, shop_id)
    return {"status": "resolved", **detail}


def ensure_credentials(db, *, transport: Any, phase: str = "shadow",
                       env: dict[str, str] | None = None):
    """Credentials for an authenticated client, binding the shop first if it has to.

    Unchanged when `ETSY_SHOP_ID` is set, when a binding is already stored, or when there is
    no token: those all go straight through `Credentials.from_env`. Only a token with no shop
    triggers `resolve`, and a failure there is logged and leaves the answer None -- exactly
    what this returned before the resolver existed.
    """
    from .etsy import Credentials

    creds = Credentials.from_env(env, transport=transport, db=db)
    if creds is not None or db is None:
        return creds
    unbound = Credentials.from_env(env, transport=transport, db=db, require_shop=False)
    if unbound is None or unbound.token_provider is None or unbound.shop_id:
        return None
    try:
        report = resolve(db, unbound, transport=transport, phase=phase)
    except Exception as e:  # noqa: BLE001 - resolution failing must not crash a client build
        log.warning("etsy shop could not be resolved from the grant: %s: %s",
                    type(e).__name__, str(e)[:200])
        return None
    if report.get("status") != "resolved":
        return None
    from dataclasses import replace

    # Same provider: no second refresh, and its compare-and-set state stays current.
    return replace(unbound, shop_id=report["shop_id"])
