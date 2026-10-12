"""W4-SHOPSYNC: reconcile the owner-configured live shop into three honest states.

The owner configured the real Etsy shop by hand. Production still reported many settings
UNKNOWN, because nothing read the settings the API does expose, and the ones it does not
expose had no short way for the owner to say "done". This module does both.

Every storefront setting ends in exactly one of three states:

* **CONFIRMED-LIVE**: read from Etsy's Open API v3 by a sanctioned, read-only, api_key GET,
  with the operation and timestamp recorded, and the reading no older than
  `API_MAX_AGE_DAYS`.
* **OWNER-CONFIRMED**: the API cannot read it (`READS` names no operation for it). The owner
  confirmed it with one tap from the Store tab. The confirmation carries the evidence that was
  already on file (owner observations, OwnerAction cards, related API facts) and a timestamp,
  and is valid for `OWNER_MAX_AGE_DAYS`.
* **UNVERIFIED**: anything else. A blank API read of an owner-configured image or text is
  still CONFIRMED-LIVE, with `value_present: false`. A setting nobody read is never "fine".

**Operations.** Each one was checked against Etsy's published document
(`publish.listing_schema.ETSY_OPENAPI_URL`, sha256 b993d52f… pinned in
research/final_build/w4/evidence_MARKETINTEL/etsy_openapi_facts_2026-10-11.json). All are GET.
All carry Etsy's root-level `api_key` security, so the app keystring alone is enough: no
OAuth scope, no token, and no route to a write. That is the least privilege that reads the
shop. `findShops` resolves the shop id only when ETSY_SHOP_ID is not set, and only on an exact
name match.

**Owner-configured fields are never written.** This module has no write path. Live values
feed `live_state` as the authoritative side of the drift report.
"""
from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

CONFIRMED_LIVE = "CONFIRMED-LIVE"
OWNER_CONFIRMED = "OWNER-CONFIRMED"
UNVERIFIED = "UNVERIFIED"

SYNC_READING = "store.shop_sync"
CONFIRM_ACTION = "store.owner_confirmed"
SYNC_ACTION = "store.shop_sync"
API_MAX_AGE_DAYS = 7
OWNER_MAX_AGE_DAYS = 90
SHOP_NAME_DEFAULT = "BrambleloopStudio"
BASE = "https://openapi.etsy.com/v3/application"

#: The Open API v3 operations this module calls. Every one is GET with root-level `api_key`
#: security in Etsy's document. The path templates are copied from that document.
OPERATIONS: dict[str, str] = {
    "findShops": "/shops",
    "getShop": "/shops/{shop_id}",
    "getShopSections": "/shops/{shop_id}/sections",
    "getShopReturnPolicies": "/shops/{shop_id}/policies/return",
    "getFeaturedListingsByShop": "/shops/{shop_id}/listings/featured",
}

#: Read by nothing here because they need an OAuth scope. Recorded so the doc and the Store tab
#: say why, rather than implying the settings are unreadable:
#: getHolidayPreferences (shops_r), getMe (shops_r: the account's user and shop id),
#: getUser (email_r).
OAUTH_ONLY = ("getHolidayPreferences", "getMe", "getUser")


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    api: tuple[tuple[str, str], ...]     # (operation, field) pairs that evidence it
    owner_confirmable: bool               # True when the API cannot fully read it
    related_actions: tuple[str, ...] = ()  # OwnerAction.requirement_key values
    observation_fields: tuple[str, ...] = ()  # live_state observation keys
    where: str = ""


SETTINGS: tuple[Setting, ...] = (
    Setting("shop_name", "Shop name", (("getShop", "shop_name"),), False,
            where="Settings > Your shop"),
    Setting("shop_icon", "Shop icon (logo)", (("getShop", "icon_url_fullxfull"),), False,
            where="Settings > Your shop > Logo"),
    Setting("banner", "Banner", (("getShop", "image_url_760x100"),), True,
            ("store:OA-BANNER",), where="Shop home editor > Banner. The Shop schema exposes "
            "only image_url_760x100; a big banner may not appear there, so the owner can "
            "confirm when the API shows none"),
    Setting("tagline", "Shop title (tagline)", (("getShop", "title"),), False,
            where="Shop home editor > Shop title"),
    Setting("announcement", "Announcement", (("getShop", "announcement"),), False,
            ("store:OA-C",), where="Shop home editor > Announcement"),
    Setting("about", "About headline and story", (), True, ("store:OA-OBS",),
            ("about_headline", "about_story"), "Shop home editor > About (no API field)"),
    Setting("member_identity", "Shop members (Laura's profile and role)", (), True,
            ("store:OA-OBS", "store:OA-B"), ("laura_member_profile", "laura_member_role"),
            "Settings > Your shop > Shop members (no API operation; getMe and getUser "
            "return only the account holder, under OAuth)"),
    Setting("listing_order", "Listing order (Custom)", (), True,
            ("store:OA-C",), where="Shop home editor > listing order. The sort setting is not "
            "in the API; getFeaturedListingsByShop's featured_rank is shown as evidence"),
    Setting("sold_visibility", "Sold items hidden", (), True, ("store:OA-C",),
            where="Settings > Options > sold items (no API field)"),
    Setting("sections", "Sections", (("getShopSections", "title"),), False,
            ("store:OA-D1",), where="Shop home editor > Sections"),
    Setting("buyer_messages", "Messages to buyers", (("getShop", "sale_message"),
                                                     ("getShop", "digital_sale_message")),
            False, ("store:OA-E",), where="Settings > Info & Appearance"),
    Setting("vacation", "Vacation mode off", (("getShop", "is_vacation"),
                                              ("getShop", "vacation_message")), False,
            where="Settings > Options > Vacation mode"),
    Setting("faq", "FAQ (with licence)", (), True, ("store:OA-F",),
            where="Shop home editor > FAQ (no API field)"),
    Setting("privacy_policy", "Privacy policy", (("getShop", "policy_privacy"),), False,
            ("store:OA-F",), where="Settings > Policy settings > Privacy"),
    Setting("cancellation_policy", "Returns and cancellations",
            (("getShopReturnPolicies", "accepts_returns"),
             ("getShop", "policy_refunds")), False, ("store:OA-F",),
            where="Settings > Policy settings > Returns & exchanges"),
    Setting("payment_readiness", "Etsy Payments onboarded",
            (("getShop", "is_etsy_payments_onboarded"),
             ("getShop", "is_direct_checkout_onboarded")), False,
            where="Finances > Payment settings. Payout bank and tax details are a separate, "
            "owner-confirmed setting"),
    Setting("currency_location", "Currency CAD and location Canada",
            (("getShop", "currency_code"), ("getShop", "shop_location_country_iso")), False,
            where="Settings > Info & Appearance"),
    Setting("payout_details", "Payout bank account and tax details", (), True,
            ("store:OA-B",), where="Finances > Payment settings (not in the API)"),
    Setting("two_factor", "Two-factor authentication on", (), True, ("store:OA-B",),
            where="Account settings > Security (no API field)"),
)
SETTING_BY_KEY = {s.key: s for s in SETTINGS}


class ConfirmRefused(ValueError):
    """A confirmation that cannot be evidence (unknown setting, or the API reads it)."""


# ---- reading -------------------------------------------------------------------------


class SyncRefused(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, etsy_error: str = ""):
        super().__init__(message)
        self.status = status
        self.etsy_error = etsy_error


class ShopReader:
    """Read-only Open API v3 client restricted to `OPERATIONS` (GET, api_key only)."""

    def __init__(self, transport, *, keystring: str, shared_secret: str = ""):
        self.transport = transport
        self._header = f"{keystring}:{shared_secret}" if shared_secret else keystring
        self._secrets = (keystring, shared_secret)
        self.calls: list[dict] = []

    def get(self, operation: str, *, path: dict | None = None,
            query: dict | None = None) -> dict:
        template = OPERATIONS.get(operation)
        if template is None:
            raise PermissionError(f"{operation!r} is not one of the shop-sync reads "
                                  f"{sorted(OPERATIONS)}")
        url = BASE + template.format(**(path or {}))
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items()
                                                 if v is not None})
        response = self.transport.request("GET", url, headers={"x-api-key": self._header,
                                                               "Accept": "application/json"})
        status = getattr(response, "status", None) or 200
        body = getattr(response, "body", None) or {}
        self.calls.append({"operation": operation, "path": template, "status": status})
        if status >= 400:
            raise SyncRefused(f"{operation} returned HTTP {status}", status=status,
                              etsy_error=_etsy_error(body, self._secrets))
        return body if isinstance(body, dict) else {}


def _etsy_error(body: Any, secrets: tuple[str, ...]) -> str:
    """Etsy's own refusal text, with any echoed credential replaced by a fingerprint."""
    from ..integrations.http import Redactor

    text = body.get("error") if isinstance(body, dict) else ""
    text = " ".join(str(text or "").split())
    return Redactor(secrets).string(text)[:200] if text else ""


#: Injection point for tests; None in production (`integrations.http.UrllibTransport`).
transport_factory: Callable[[], Any] | None = None


def _env(env: dict | None) -> dict:
    return env if env is not None else dict(os.environ)


def _keystring(e: dict) -> tuple[str, str]:
    return ((e.get("ETSY_KEYSTRING") or e.get("ETSY_API_KEY") or "").strip(),
            (e.get("ETSY_SHARED_SECRET") or "").strip())


def _resolve_shop_id(reader: ShopReader, e: dict) -> tuple[int | None, str]:
    configured = (e.get("ETSY_SHOP_ID") or "").strip()
    if configured.isdigit():
        return int(configured), "ETSY_SHOP_ID"
    name = (e.get("ETSY_SHOP_NAME") or SHOP_NAME_DEFAULT).strip()
    found = reader.get("findShops", query={"shop_name": name, "limit": 25})
    for shop in found.get("results") or []:
        if str(shop.get("shop_name", "")).casefold() == name.casefold():
            return int(shop["shop_id"]), f"findShops exact match on {name!r}"
    return None, f"findShops returned no shop named exactly {name!r}"


def sync(db, *, env: dict | None = None, now: datetime | None = None) -> dict:
    """Read the shop's API-exposed settings and store one dated reading. Never writes.

    Returns `ran`, `reading` (`measured` / `UNMEASURED`), the operations called and why. Every
    outcome is recorded as a `store.shop_sync` audit row (operations and status, never the
    credential), so "not read, and why" is as visible as a reading.
    """
    out = _sync(db, env=env, now=now)
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=SYNC_ACTION, artifact="etsy_shop",
                       detail={k: out.get(k) for k in (
                           "ran", "reading", "why", "operations", "shop_id_source",
                           "credential_refused", "etsy_error") if k in out}))
    return out


def _sync(db, *, env: dict | None = None, now: datetime | None = None) -> dict:
    from ..intel import etsy_public
    from ..runtime.etsy_ops import store_reading

    now = now or datetime.now(timezone.utc)
    e = _env(env)
    key, secret = _keystring(e)
    if not key:
        return {"ran": False, "reading": "UNMEASURED", "operations": [],
                "why": "no ETSY_KEYSTRING/ETSY_API_KEY in this environment; nothing read"}
    probe = etsy_public.last_probe(db)
    if etsy_public.auth_refused(probe):
        return {"ran": False, "reading": "UNMEASURED", "operations": [],
                "credential_refused": True,
                "why": "Etsy refused the app key at the last etsy.probe; the shop is read "
                       "after a probe succeeds"}
    if transport_factory is not None:
        transport = transport_factory()
    else:
        from ..integrations.http import UrllibTransport

        transport = UrllibTransport()
    reader = ShopReader(transport, keystring=key, shared_secret=secret)
    try:
        shop_id, shop_id_source = _resolve_shop_id(reader, e)
        if shop_id is None:
            return {"ran": False, "reading": "UNMEASURED", "operations": reader.calls,
                    "why": shop_id_source}
        shop = reader.get("getShop", path={"shop_id": shop_id})
        sections = reader.get("getShopSections", path={"shop_id": shop_id})
        returns = reader.get("getShopReturnPolicies", path={"shop_id": shop_id})
        featured = reader.get("getFeaturedListingsByShop", path={"shop_id": shop_id},
                              query={"limit": 100})
    except SyncRefused as exc:
        return {"ran": False, "reading": "UNMEASURED", "operations": reader.calls,
                "credential_refused": exc.status in etsy_public.AUTH_REFUSED,
                "etsy_error": exc.etsy_error, "why": str(exc)[:300]}
    payload = {
        "observed_at": now.timestamp(), "observed_at_iso": now.isoformat(),
        "shop_id": shop_id, "shop_id_source": shop_id_source,
        "operations": reader.calls, "shop": shop,
        "sections": _results(sections), "return_policies": _results(returns),
        "featured": [{"listing_id": r.get("listing_id"), "featured_rank": r.get("featured_rank"),
                      "title": str(r.get("title") or "")[:140]}
                     for r in _results(featured)],
        "writes_performed": 0,
    }
    store_reading(db, SYNC_READING, payload, now=now)
    return {"ran": True, "reading": "measured", "operations": reader.calls,
            "shop_id_source": shop_id_source,
            "why": "read the shop's API-exposed settings (api_key, GET only)"}


def _results(body: dict) -> list[dict]:
    got = body.get("results") if isinstance(body, dict) else None
    return [r for r in got if isinstance(r, dict)] if isinstance(got, list) else []


def latest_sync(db) -> dict | None:
    from ..runtime.etsy_ops import latest_reading

    return latest_reading(db, SYNC_READING)


# ---- owner confirmation ---------------------------------------------------------------


def evidence(db, key: str, *, reading: dict | None = None) -> dict:
    """What is already on file for `key`. Pre-filled so the owner only confirms it."""
    from sqlalchemy import select

    from ..core.models import OwnerAction
    from . import live_state

    s_ = SETTING_BY_KEY[key]
    out: dict[str, Any] = {"api": {}, "observations": {}, "owner_actions": []}
    reading = reading if reading is not None else (latest_sync(db) or {})
    for op, fld in s_.api:
        value = _api_value(reading, op, fld)
        if value is not _MISSING:
            out["api"][f"{op}.{fld}"] = _short(value)
    if key == "listing_order" and reading.get("featured") is not None:
        out["api"]["getFeaturedListingsByShop.featured_rank"] = [
            {"listing_id": r.get("listing_id"), "featured_rank": r.get("featured_rank")}
            for r in reading["featured"][:20]]
    if key == "payout_details":
        value = _api_value(reading, "getShop", "is_etsy_payments_onboarded")
        if value is not _MISSING:
            out["api"]["getShop.is_etsy_payments_onboarded"] = value
    if s_.observation_fields:
        snap = live_state.snapshot(db)
        for f in s_.observation_fields:
            row = snap.get(f) or {}
            if row.get("state") != live_state.UNKNOWN:
                out["observations"][f] = {"value": _short(row.get("value")),
                                          "observed_at": row.get("observed_at"),
                                          "source": row.get("source")}
    if s_.related_actions:
        with db.session() as s:
            for row in s.scalars(select(OwnerAction).where(
                    OwnerAction.requirement_key.in_(s_.related_actions))):
                out["owner_actions"].append({"key": row.requirement_key, "done": bool(row.done),
                                             "action": str(row.action or "")[:240]})
    return out


def confirm(db, key: str, *, actor: str, statement: str = "",
            now: datetime | None = None) -> dict:
    """Record the owner's one-tap confirmation of a setting the API cannot read."""
    from ..core.models import AuditLog

    s_ = SETTING_BY_KEY.get(key)
    if s_ is None:
        raise ConfirmRefused(f"unknown setting {key!r}; one of {sorted(SETTING_BY_KEY)}")
    if not s_.owner_confirmable:
        raise ConfirmRefused(f"{s_.label} is read from Etsy's API ({_ops(s_)}); it is "
                             f"confirmed by the reading, not by a statement")
    now = now or datetime.now(timezone.utc)
    ev = evidence(db, key)
    text = re.sub(r"\s+", " ", str(statement or "")).strip()[:500] or default_statement(s_)
    detail = {"setting": key, "label": s_.label, "confirmed_at": now.isoformat(),
              "statement": text, "evidence": ev, "where": s_.where}
    with db.session() as s:
        row = AuditLog(actor=actor[:64], action=CONFIRM_ACTION,
                       artifact=f"etsy_shop:setting:{key}", detail=detail)
        s.add(row)
        s.flush()
        return {"id": row.id, "setting": key, "state": OWNER_CONFIRMED,
                "confirmed_at": detail["confirmed_at"]}


def default_statement(s_: Setting) -> str:
    return (f"I checked the live shop ({s_.where.split('.')[0]}) and {s_.label} is set as "
            f"intended.")


def _confirmations(db) -> dict[str, dict]:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    out: dict[str, dict] = {}
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == CONFIRM_ACTION)
                             .order_by(desc(AuditLog.id)).limit(500)):
            d = dict(row.detail or {})
            out.setdefault(d.get("setting"), dict(d, by=row.actor, id=row.id))
    return out


# ---- status ----------------------------------------------------------------------------

_MISSING = object()


def _api_value(reading: dict, op: str, fld: str):
    if not reading:
        return _MISSING
    if op == "getShop":
        shop = reading.get("shop") or {}
        return shop[fld] if fld in shop else _MISSING
    rows = {"getShopSections": reading.get("sections"),
            "getShopReturnPolicies": reading.get("return_policies"),
            "getFeaturedListingsByShop": reading.get("featured")}.get(op)
    if rows is None:
        return _MISSING
    return [r.get(fld) for r in rows]


def _present(value) -> bool:
    if value is _MISSING or value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (list, tuple)):
        return any(_present(v) for v in value)
    return bool(str(value).strip())


def _short(value):
    if isinstance(value, str):
        return value[:300]
    if isinstance(value, list):
        return [_short(v) for v in value[:20]]
    return value


def _ops(s_: Setting) -> str:
    return ", ".join(f"{op}.{fld}" for op, fld in s_.api)


def _age_days(at: datetime | None, now: datetime) -> float | None:
    return None if at is None else (now - at).total_seconds() / 86400.0


def status(db, *, now: datetime | None = None) -> dict:
    """Every setting with its state, source, timestamp and the evidence a confirm would carry."""
    now = now or datetime.now(timezone.utc)
    reading = latest_sync(db) or {}
    read_at = (datetime.fromtimestamp(float(reading["observed_at"]), tz=timezone.utc)
               if reading.get("observed_at") else None)
    read_age = _age_days(read_at, now)
    fresh_read = read_age is not None and 0 <= read_age <= API_MAX_AGE_DAYS
    confirmations = _confirmations(db)
    rows = []
    for s_ in SETTINGS:
        row: dict[str, Any] = {"key": s_.key, "label": s_.label, "where": s_.where,
                               "api_operations": [f"{op}.{fld}" for op, fld in s_.api],
                               "owner_confirmable": s_.owner_confirmable}
        values = {f"{op}.{fld}": _api_value(reading, op, fld) for op, fld in s_.api}
        read = [v for v in values.values() if v is not _MISSING]
        conf = confirmations.get(s_.key)
        conf_at = datetime.fromisoformat(conf["confirmed_at"]) if conf else None
        conf_age = _age_days(conf_at, now)
        conf_fresh = conf_age is not None and 0 <= conf_age <= OWNER_MAX_AGE_DAYS
        api_complete = bool(s_.api) and read and fresh_read and (
            not s_.owner_confirmable or any(_present(v) for v in read))
        if api_complete:
            row.update(state=CONFIRMED_LIVE, source=", ".join(
                k for k, v in values.items() if v is not _MISSING),
                observed_at=read_at.isoformat(), value_present=any(_present(v) for v in read),
                values={k: _short(v) for k, v in values.items() if v is not _MISSING})
        elif s_.owner_confirmable and conf_fresh:
            row.update(state=OWNER_CONFIRMED, source="owner (Command Center)",
                       observed_at=conf["confirmed_at"], statement=conf.get("statement"),
                       confirmed_by=conf.get("by"))
        else:
            why = []
            if s_.api and not reading:
                why.append("Etsy has not been read yet (store.shop_sync)")
            elif s_.api and not fresh_read:
                why.append(f"the last Etsy reading is older than {API_MAX_AGE_DAYS} days")
            elif s_.api and read and not any(_present(v) for v in read):
                why.append("the API shows nothing for it")
            if not s_.api:
                why.append("no Open API v3 operation exposes it")
            if s_.owner_confirmable:
                why.append("confirm it from the Store tab" if not conf else
                           f"the owner confirmation is older than {OWNER_MAX_AGE_DAYS} days")
            row.update(state=UNVERIFIED, source=None, observed_at=None, why="; ".join(why))
        if row["state"] != CONFIRMED_LIVE and s_.owner_confirmable:
            row["evidence"] = evidence(db, s_.key, reading=reading)
            row["prefilled_statement"] = default_statement(s_)
        rows.append(row)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    return {"generated_at": now.isoformat(), "settings": rows, "counts": counts,
            "last_read": {"at": read_at.isoformat() if read_at else None,
                          "operations": reading.get("operations") or [],
                          "shop_id_source": reading.get("shop_id_source")},
            "states": [CONFIRMED_LIVE, OWNER_CONFIRMED, UNVERIFIED],
            "writes_performed": 0}
