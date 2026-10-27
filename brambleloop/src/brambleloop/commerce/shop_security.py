"""Shop security posture, verified every day without exposing a credential (F-592).

`etsy.credential_health` already checks that the stored Etsy credential opens, carries the
required scopes and refreshes. F-592 asks for more, continuously: connected apps, shared
access, secret-rotation history, callback configuration and *suspicious authorization
changes*. This module reads only fingerprints, scope names, counts and timestamps -- never a
token, secret or key -- and judges:

- **scope change**: scopes added or removed since the previous daily reading. An added scope
  this company never asked for is a suspicious authorization change; a removed one breaks the
  next write or read.
- **credential replaced outside refresh**: the stored credential's token fingerprint changed
  while the rotation counter did not move -- a credential put there by something other than
  this system's own refresh or the owner's recorded authorization.
- **rotation history**: rotations and the age of the last update. A credential that has not
  refreshed in `ROTATION_STALE_DAYS` is reported (its refresh path is unexercised).
- **callback configuration**: `integrations.etsy_authorise.configuration()`'s own redirect
  checks (https, no fragment, the callback path), reported as problems only.
- **connected apps / shared access**: browser-only (no Etsy API); judged from the owner's
  dated readings (`commerce.shop_observations`), UNOBSERVED or STALE until one exists, and a
  non-empty page is a finding.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

ROTATION_STALE_DAYS = 30
#: Scopes this company's authorization asks for. Anything else appearing is suspicious.
EXPECTED_SCOPES = frozenset({"listings_r", "listings_w", "listings_d", "shops_r", "shops_w",
                             "transactions_r", "email_r"})


def _wanted_scopes() -> frozenset[str]:
    try:
        from ..integrations import etsy_oauth

        return frozenset(etsy_oauth.SCOPES_WANTED) | EXPECTED_SCOPES
    except Exception:  # noqa: BLE001
        return EXPECTED_SCOPES


def _age_days(iso: str | None, now: datetime) -> float | None:
    if not iso:
        return None
    try:
        at = datetime.fromisoformat(str(iso))
    except ValueError:
        return None
    at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    return round((now - at).total_seconds() / 86400.0, 2)


def posture(current: dict | None, previous: dict | None, *, observations: dict | None = None,
            callback: dict | None = None, now: datetime | None = None) -> dict:
    """The day's posture from two credential readings, owner observations and the callback."""
    now = now or datetime.now(timezone.utc)
    current, previous = current or {}, previous or {}
    observations = observations or {}
    findings: list[dict[str, Any]] = []
    checks: dict[str, Any] = {}

    checks["credential"] = current.get("status") or "UNKNOWN"
    if current.get("status") in ("UNHEALTHY",):
        findings.append({"check": "credential", "severity": "P1",
                         "detail": "; ".join(current.get("findings") or []) or "unhealthy"})

    now_scopes, was_scopes = set(current.get("scopes") or []), set(previous.get("scopes") or [])
    added = sorted(now_scopes - was_scopes) if previous else []
    removed = sorted(was_scopes - now_scopes) if previous else []
    unexpected = sorted(now_scopes - _wanted_scopes())
    checks["scopes"] = {"held": sorted(now_scopes), "added": added, "removed": removed,
                        "unexpected": unexpected}
    if unexpected:
        findings.append({"check": "scopes", "severity": "P1", "suspicious": True,
                         "detail": f"the credential holds scopes nobody here requested: "
                                   f"{unexpected}"})
    if removed:
        findings.append({"check": "scopes", "severity": "P1",
                         "detail": f"scopes removed since the last reading: {removed}"})

    fp_now, fp_was = current.get("token_fingerprint"), previous.get("token_fingerprint")
    rot_now, rot_was = current.get("rotations"), previous.get("rotations")
    replaced = bool(previous and fp_now and fp_was and fp_now != fp_was and rot_now == rot_was)
    checks["replaced_outside_refresh"] = replaced
    if replaced:
        findings.append({"check": "authorization", "severity": "P1", "suspicious": True,
                         "detail": "the stored credential changed while its rotation counter "
                                   "did not: it was replaced by something other than this "
                                   "system's refresh"})

    age = _age_days(current.get("updated_at"), now)
    checks["rotation"] = {"rotations": rot_now, "last_update_age_days": age,
                          "stale_after_days": ROTATION_STALE_DAYS}
    if current.get("stored") and age is not None and age > ROTATION_STALE_DAYS:
        findings.append({"check": "rotation", "severity": "P2",
                         "detail": f"no refresh in {age} days: the rotation path is "
                                   f"unexercised"})

    cb = callback or {}
    redirect_problems = [p for p in (cb.get("problems") or []) if "REDIRECT" in p.upper()]
    checks["callback"] = {"problems": redirect_problems,
                          "configured": bool(cb.get("redirect_uri"))}
    if redirect_problems:
        findings.append({"check": "callback", "severity": "P2",
                         "detail": "; ".join(redirect_problems)[:400]})

    for page, field in (("apps", "apps"), ("shared_access", "people")):
        obs = observations.get(page) or {"state": "UNOBSERVED"}
        listed = ((obs.get("observation") or {}).get("values") or {}).get(field) or []
        checks[page] = {"state": obs.get("state"), "listed": len(listed)}
        if obs.get("state") in ("FRESH", "STALE") and listed:
            findings.append({"check": page, "severity": "P1", "suspicious": True,
                             "detail": f"the owner's reading lists {len(listed)} "
                                       f"{'installed app(s)' if page == 'apps' else 'person(s) with shop access'}"})
    unverified = [p for p in ("apps", "shared_access")
                  if checks[p]["state"] not in ("FRESH",)]
    status = ("FINDINGS" if findings else "UNVERIFIED" if unverified or
              checks["credential"] in ("UNKNOWN", "ABSENT") else "OK")
    return {"status": status, "checks": checks, "findings": findings,
            "unverified": unverified, "observed_at": now.isoformat(),
            "exposes_credentials": False}


# ---- W4-C12: the three Etsy account registers (F-580, F-583, F-588) ------------------------
#
# Each register is a dated, owner-sourced record (Etsy has no API for installed apps, Shared
# Access or partner disclosures beyond a read of the partner list), stored as an
# `OperatingReading`, and judged in code. None of them can pass by being empty: an empty
# register is UNOBSERVED until the owner records a complete reading saying it is empty.

APPS_KIND = "etsy.register.apps"
SHARED_KIND = "etsy.register.shared_access"
PARTNERS_KIND = "etsy.register.partners"
REGISTER_MAX_AGE_DAYS = 30
PARTNERS_MAX_AGE_DAYS = 90
SHARED_IDLE_DAYS = 60
APP_FIELDS = ("name", "scopes", "purpose", "owner", "last_used_on", "data_access",
              "monthly_cost_cad", "revocation_path")
#: The first-party application, whose scopes and purpose this company knows from its own code.
FIRST_PARTY_APP = {
    "name": "Brambleloop Studio (this company's own Etsy app)",
    "purpose": "publish and maintain the shop's own listings and read its orders",
    "owner": "owner", "data_access": "listings, shop settings, receipts (no buyer messages)",
    "monthly_cost_cad": 0.0,
    "revocation_path": "Etsy > Settings > Account settings > Apps you've connected > Remove"}
#: Shared Access permissions Etsy offers, and the least each kind of helper needs.
SHARED_PERMISSIONS = frozenset({"listings", "orders", "messages", "finances", "marketing",
                                "settings", "stats"})


class RegisterRefused(ValueError):
    """A register entry that would be fabricated, undated or incomplete evidence."""


def _dt(v) -> datetime:
    if isinstance(v, datetime):
        at = v
    else:
        try:
            at = datetime.fromisoformat(str(v or "").replace("Z", "+00:00"))
        except ValueError as e:
            raise RegisterRefused("observed_at must be an ISO 8601 date-time") from e
    at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    if at > datetime.now(timezone.utc):
        raise RegisterRefused("a reading cannot be observed in the future")
    return at


def _store(db, kind: str, at: datetime, payload: dict) -> None:
    import uuid

    from ..core.models import OperatingReading

    with db.session() as s:
        # One row per reading: the (kind, period_key) pair is unique, so the key is the
        # reading's own timestamp and two readings on one day are both kept.
        s.add(OperatingReading(kind=kind, at=at, period_key=f"{at.strftime('%y%m%d')}-{uuid.uuid4().hex[:13]}",
                               payload=payload))


def _latest(db, kind: str) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == kind)
                       .order_by(desc(OperatingReading.at), desc(OperatingReading.id)).limit(1))
        return dict(row.payload or {}, _at=row.at.isoformat()) if row else None


def _base(reading: dict | None, max_age: int, now: datetime) -> dict:
    if reading is None:
        return {"state": "UNOBSERVED", "why": "no complete owner reading is on file"}
    at = datetime.fromisoformat(reading["observed_at"])
    age = (now - at).days
    return {"state": "STALE" if age > max_age else "FRESH", "observed_at": reading["observed_at"],
            "age_days": age}


def _check_complete(complete, statement: str) -> None:
    if complete is not True:
        raise RegisterRefused("a register reading is the whole page or it is not evidence")
    if len((statement or "").split()) < 4:
        raise RegisterRefused("a register reading carries the owner's statement of what the "
                              "page showed")


# F-580: connected apps -----------------------------------------------------------------------

def record_apps(db, *, observed_at, apps: list[dict], complete: bool, statement: str) -> dict:
    at = _dt(observed_at)
    _check_complete(complete, statement)
    clean = []
    for i, a in enumerate(apps):
        missing = [f for f in APP_FIELDS if a.get(f) in (None, "", [])
                   and f not in ("monthly_cost_cad",)]
        if a.get("monthly_cost_cad") is None:
            missing.append("monthly_cost_cad")
        if missing:
            raise RegisterRefused(f"app {i} ({a.get('name')!r}) lacks {missing}: an app nobody "
                                  f"can account for is recorded as debt, not as known")
        clean.append({f: a[f] for f in APP_FIELDS})
    payload = {"observed_at": at.isoformat(), "apps": clean, "statement": statement[:500]}
    _store(db, APPS_KIND, at, payload)
    return payload


def apps_register(db, *, held_scopes=(), credential_updated_at: str | None = None,
                  now: datetime | None = None) -> dict:
    """Every connected app with scopes, purpose, owner, last use, data, cost, revocation."""
    now = now or datetime.now(timezone.utc)
    reading = _latest(db, APPS_KIND)
    base = _base(reading, REGISTER_MAX_AGE_DAYS, now)
    first = {**FIRST_PARTY_APP, "scopes": sorted(held_scopes),
             "requested_scopes": sorted(_wanted_scopes()),
             "unrequested_scopes": sorted(set(held_scopes) - _wanted_scopes()),
             "last_used_on": credential_updated_at, "first_party": True}
    debt = []
    third = list((reading or {}).get("apps") or [])
    for a in third:
        last = _age_days(a.get("last_used_on"), now)
        if last is None or last > SHARED_IDLE_DAYS:
            debt.append({"app": a["name"], "why": (f"not used in {last} days" if last is not None
                                                   else "last use unknown")})
    if first["unrequested_scopes"]:
        debt.append({"app": first["name"],
                     "why": f"holds unrequested scopes {first['unrequested_scopes']}"})
    status = ("UNVERIFIED" if base["state"] != "FRESH" else "DEBT" if debt else "OK")
    return {"register": "apps", **base, "status": status, "apps": [first] + third,
            "security_debt": debt}


# F-583: Shared Access ------------------------------------------------------------------------

def record_shared_access(db, *, observed_at, members: list[dict], complete: bool,
                         statement: str) -> dict:
    at = _dt(observed_at)
    _check_complete(complete, statement)
    clean = []
    for i, m in enumerate(members):
        perms = set(m.get("permissions") or [])
        needs = set(m.get("needs") or [])
        if not str(m.get("label") or "").strip() or not m.get("granted_on"):
            raise RegisterRefused(f"member {i} needs a label and the date access was granted")
        bad = sorted((perms | needs) - SHARED_PERMISSIONS)
        if bad:
            raise RegisterRefused(f"member {i}: {bad} are not Shared Access permissions")
        if not needs:
            raise RegisterRefused(f"member {i}: state what the person needs access for, so "
                                  f"least privilege can be checked")
        clean.append({"label": m["label"], "permissions": sorted(perms),
                      "needs": sorted(needs), "granted_on": m["granted_on"],
                      "last_activity_on": m.get("last_activity_on")})
    payload = {"observed_at": at.isoformat(), "members": clean, "statement": statement[:500],
               "accountable": "owner"}
    _store(db, SHARED_KIND, at, payload)
    return payload


def shared_access_register(db, *, now: datetime | None = None) -> dict:
    """Team members, their access and activity, judged for least privilege (owner accountable)."""
    now = now or datetime.now(timezone.utc)
    reading = _latest(db, SHARED_KIND)
    base = _base(reading, REGISTER_MAX_AGE_DAYS, now)
    findings = []
    for m in (reading or {}).get("members") or []:
        extra = sorted(set(m["permissions"]) - set(m["needs"]))
        if extra:
            findings.append({"member": m["label"], "check": "least_privilege",
                             "detail": f"holds {extra} beyond what they need"})
        idle = _age_days(m.get("last_activity_on"), now)
        if idle is None or idle > SHARED_IDLE_DAYS:
            findings.append({"member": m["label"], "check": "idle",
                             "detail": ("no recorded activity" if idle is None
                                        else f"inactive {idle} days: revoke or justify")})
    status = "UNVERIFIED" if base["state"] != "FRESH" else "FINDINGS" if findings else "OK"
    return {"register": "shared_access", **base, "status": status,
            "members": (reading or {}).get("members") or [], "findings": findings,
            "accountable": "owner"}


# F-588: Partners You Work With ---------------------------------------------------------------

def record_partners(db, *, observed_at, partners: list[dict], complete: bool, statement: str,
                    source: str) -> dict:
    """The owner's reading of Etsy's production-partner page, or the shop's declared list."""
    at = _dt(observed_at)
    _check_complete(complete, statement)
    if source not in ("etsy_page", "getShopProductionPartners"):
        raise RegisterRefused("a partner disclosure is read from Etsy (the page or the API "
                              "read), never composed: fabricated partner data is refused")
    clean = []
    for i, p in enumerate(partners):
        if not str(p.get("name") or "").strip() or not str(p.get("role") or "").strip():
            raise RegisterRefused(f"partner {i} needs the name and role Etsy shows")
        clean.append({"name": p["name"], "role": p["role"],
                      "location": p.get("location"), "since": p.get("since")})
    payload = {"observed_at": at.isoformat(), "partners": clean, "source": source,
               "statement": statement[:500]}
    _store(db, PARTNERS_KIND, at, payload)
    return payload


def partners_register(db, *, now: datetime | None = None, reaudit: dict | None = None) -> dict:
    """The disclosure on file, STALE after 90 days, and REAUDIT when the providers changed."""
    now = now or datetime.now(timezone.utc)
    reading = _latest(db, PARTNERS_KIND)
    base = _base(reading, PARTNERS_MAX_AGE_DAYS, now)
    if reaudit is None:
        try:
            from ..intel import etsy_surfaces

            reaudit = etsy_surfaces.partners_reaudit()
        except Exception as exc:  # noqa: BLE001 - an unreadable provider set re-opens it
            reaudit = {"reopened": True, "why": f"provider set unreadable ({type(exc).__name__})"}
    if reading is not None and reaudit.get("reopened"):
        at = datetime.fromisoformat(reading["observed_at"])
        reviewed_after = reaudit.get("changed_at")
        if not reviewed_after or at <= datetime.fromisoformat(reviewed_after):
            base = {**base, "state": "REAUDIT", "why": reaudit.get("why")}
    status = "OK" if base["state"] == "FRESH" else "UNVERIFIED"
    return {"register": "partners", **base, "status": status,
            "partners": (reading or {}).get("partners") or [],
            "source": (reading or {}).get("source"), "reaudit": reaudit}
