"""The Etsy surface inventory, served and re-verified against what is actually held (F-514).

`intel.etsy_surfaces` is the machine-readable inventory of every Shop Manager surface, with
verdicts, operations, scopes and evidence. The audit's gap: it was static code nobody could
read from the running system, and nothing re-checked its claims against reality. This
module:

- **serves** it (`served()`), one row per surface with the channel F-514 names --
  `api`, `browser_only`, `owner_only`, `unsupported`, `not_applicable` or `unknown` -- and
  the coverage of the surfaces the requirement lists by name;
- **re-verifies** it daily (`reverify()`), against three things the static file cannot know:
  the scopes the *stored* credential actually holds (not the scopes the file says were
  granted on one date), the freshness of every collector's last reading, and the owner's
  dated readings of browser-only pages. A surface whose declared API access is not backed by
  a held scope, or whose evidence is missing or stale, is reported by name. Fourth (W4-FM2),
  each verdict's classification against Etsy's *current* published API document, read weekly
  by `runtime.etsy_ops.reverify_openapi`: never re-verified, unreadable, stale or drifted is
  a named problem, and a drifted surface is marked on its item.

`summary(db)` follows the cross-lane provider contract (status, as_of, basis, items,
sources) and never raises on an empty database.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

#: The surfaces F-514 names, mapped to inventory keys.
REQUIRED = {
    "Listings": "listings", "Search Visibility": "search_visibility", "Stats": "stats",
    "Marketplace Insights": "marketplace_insights", "Marketing/Ads": "etsy_ads",
    "Sales & Discounts": "sales_and_discounts", "Messages": "messages", "Orders": "orders",
    "Customer Service Stats": "customer_service_stats",
    "Policy Violations": "policy_violations", "Finances": "payment_account",
    "Apps": "apps", "shop customization": "info_and_appearance",
    "policies": "policy_settings", "subscription": "subscription",
    "API/OAuth": "developer_portal",
}

READINGS = {"shop_snapshot": "etsy.shop_snapshot", "listing_census": "etsy.listing_census"}
OWNER_PAGES = {"policy_violations", "shared_access", "apps", "options"}


def channel(surface) -> str:
    from ..intel import etsy_surfaces as es

    if surface.verdict == es.NOT_APPLICABLE:
        return "not_applicable"
    if surface.verdict == es.UNSUPPORTED:
        return "unsupported"
    if surface.verdict == es.OWNER_ONLY:
        return "owner_only"
    if surface.verdict in (es.OBSERVE, es.ANALYZE, es.ACT):
        return "api" if surface.operations else "browser_only"
    return "unknown"


def served() -> dict:
    """The inventory as data, with the channel per surface and F-514's named coverage."""
    from ..intel import etsy_surfaces as es

    rows = [{**s.to_dict(), "channel": channel(s)} for s in es.surfaces()]
    keys = {r["key"] for r in rows}
    coverage = {name: (key if key in keys else None) for name, key in REQUIRED.items()}
    return {"surfaces": rows, "count": len(rows), "named_coverage": coverage,
            "missing_named": sorted(n for n, k in coverage.items() if k is None),
            "registry_problems": es.check_registry(), "source": "intel.etsy_surfaces"}


def reverify(db, *, now: float | None = None) -> dict:
    """Each surface's declared access and evidence, checked against what is held today."""
    from ..intel import etsy_surfaces as es
    from ..runtime.etsy_ops import CREDENTIAL_READING, latest_reading
    from . import shop_observations

    now = now or time.time()
    cred = latest_reading(db, CREDENTIAL_READING) or {}
    held = set(cred.get("scopes") or [])
    readings = {name: latest_reading(db, kind) for name, kind in READINGS.items()}
    items, problems = [], []
    for s in es.surfaces():
        ch = channel(s)
        entry = {"key": s.key, "name": s.name, "verdict": s.verdict, "channel": ch}
        if s.scopes and ch == "api":
            missing = [x for x in s.scopes if x not in held] if cred else list(s.scopes)
            entry["scopes_missing"] = missing
            if missing:
                entry["scope_state"] = "UNKNOWN" if not cred else "NOT_HELD"
                if cred:
                    problems.append(f"{s.key}: declared API access needs {missing}, which "
                                    f"the stored credential does not hold")
            else:
                entry["scope_state"] = "HELD"
        if s.collector:
            state = es.evidence_state(s, readings.get(s.collector), now=now)
            entry["evidence_state"] = state
            if state != es.FRESH:
                problems.append(f"{s.key}: collector {s.collector} evidence is {state}")
        elif s.key in OWNER_PAGES:
            entry["evidence_state"] = shop_observations.latest(db, s.key)["state"]
        else:
            entry["evidence_state"] = es.NO_COLLECTOR
        items.append(entry)
    classification = _classification(db, now, items, problems)
    return {"items": items, "problems": problems, "credential_read": bool(cred),
            "classification": classification,
            "checked_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat()}


def _classification(db, now: float, items: list[dict], problems: list[str]) -> dict:
    """Whether each surface's verdict still rests on Etsy's published API document (F-514).

    Reads the latest `etsy.openapi_reverify` reading. Never re-verified, unreadable, stale or
    drifted are each a named problem; a surface the drift touches is marked on its item.
    """
    from ..intel import etsy_surfaces as es
    from ..runtime.etsy_ops import OPENAPI_READING, OPENAPI_REVERIFY_DAYS, latest_reading

    reading = latest_reading(db, OPENAPI_READING)
    if not reading:
        problems.append("classification: never re-verified against Etsy's current API "
                        "document (job etsy.openapi_reverify has not run)")
        state = {"status": "UNVERIFIED", "checked_at": None}
    else:
        state = {"status": reading.get("status") or "UNVERIFIED",
                 "checked_at": reading.get("checked_at"),
                 "version": reading.get("version")}
        try:
            age_days = (now - datetime.fromisoformat(reading["checked_at"]).timestamp()) / 86400
        except (KeyError, TypeError, ValueError):
            age_days = None
        if age_days is None or age_days > 2 * OPENAPI_REVERIFY_DAYS:
            state["status"] = "STALE" if age_days is not None else "UNVERIFIED"
            problems.append(f"classification: re-verification is {state['status']} "
                            f"(last {reading.get('checked_at')})")
        elif reading.get("status") == es.OPENAPI_UNREADABLE:
            problems.append(f"classification: UNREADABLE: {reading.get('why')}")
        elif reading.get("status") == es.OPENAPI_DRIFTED:
            touched = {a["surface"]: a["reasons"] for a in reading.get("affected") or []}
            for item in items:
                if item["key"] in touched:
                    item["classification_state"] = es.OPENAPI_DRIFTED
                    problems.append(f"{item['key']}: classification drifted: "
                                    f"{'; '.join(touched[item['key']])[:240]}")
            if not touched:
                problems.append("classification: Etsy's document changed (operations "
                                "added/removed) without a surface named; re-audit")
    for item in items:
        item.setdefault("classification_state", state["status"])
    return state


def summary(db) -> dict:
    """Provider-shaped: status, as_of, basis, items, sources. Never raises."""
    try:
        inv = served()
        check = reverify(db)
    except Exception as e:  # noqa: BLE001 - an unreadable inventory is UNKNOWN
        return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
                "sources": [], "reason": f"{type(e).__name__}: {str(e)[:200]}"}
    status = ("UNKNOWN" if not check["credential_read"] else
              "DEGRADED" if check["problems"] or inv["missing_named"] else "OK")
    return {"status": status, "as_of": check["checked_at"], "basis": "measured",
            "items": check["items"], "problems": check["problems"][:50],
            "missing_named": inv["missing_named"], "surfaces": inv["count"],
            "classification": check["classification"],
            "sources": ["intel.etsy_surfaces", "operating_readings:etsy.credential_health",
                        "operating_readings:etsy.openapi_reverification",
                        "operating_readings:etsy.shop_snapshot",
                        "operating_readings:etsy.listing_census",
                        "audit_log:etsy.shop_observation"]}
