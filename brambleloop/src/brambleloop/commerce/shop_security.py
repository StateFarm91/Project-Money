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
