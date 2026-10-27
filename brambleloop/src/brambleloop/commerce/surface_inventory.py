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


# ---- W4-C13 F-546: Etsy feature discovery, classified before adoption -----------------------
#
# F-546: "Continuously audit new/changed Shop Manager capabilities, API fields, Seller Handbook
# guidance and Etsy Plus features. Classify each as useful, irrelevant, owner-only, unsupported
# or research-needed before adoption." The weekly OpenAPI re-verification already notices a
# changed document; what was missing is the register a discovery lands in and the rule that
# nothing is adopted before it is classified. `discover()` files new or changed features from
# any of the four sources as `unclassified`; `classify()` records one of the five verdicts with
# its reason; `may_adopt()` is true only for `useful`.

FEATURE_ACTION = "etsy.feature_discovered"
CLASSIFY_ACTION = "etsy.feature_classified"
FEATURE_SOURCES = ("openapi", "shop_manager", "seller_handbook", "etsy_plus")
FEATURE_CLASSES = ("useful", "irrelevant", "owner_only", "unsupported", "research_needed")


class FeatureRefused(ValueError):
    """A discovery or classification that would not be evidence."""


def _feature_key(source: str, name: str) -> str:
    return f"{source}:{name.strip().lower()}"[:200]


def features(db) -> dict[str, dict]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    out: dict[str, dict] = {}
    with db.session() as s:
        for a in s.scalars(select(AuditLog).where(AuditLog.action.in_(
                (FEATURE_ACTION, CLASSIFY_ACTION))).order_by(AuditLog.id)):
            d = dict(a.detail or {})
            k = d["key"]
            if a.action == FEATURE_ACTION:
                prev = out.get(k)
                out[k] = {**(prev or {}), **d, "class": "unclassified"
                          if prev is None or d.get("changed") else prev.get("class"),
                          "discovered_at": (prev or {}).get("discovered_at")
                          or a.at.isoformat()}
            elif k in out:
                out[k].update({"class": d["class"], "reason": d["reason"],
                               "classified_by": d["by"], "classified_at": a.at.isoformat()})
    return out


def discover(db, *, items: list[dict], observed_at: str) -> dict:
    """File newly seen or changed features; an unchanged one is not re-filed."""
    from ..core.models import AuditLog

    if not observed_at:
        raise FeatureRefused("a discovery is dated")
    known = features(db)
    filed = []
    with db.session() as s:
        for it in items:
            src, name = it.get("source"), str(it.get("name") or "").strip()
            if src not in FEATURE_SOURCES or not name:
                raise FeatureRefused(f"a feature names its source {FEATURE_SOURCES} and itself")
            k = _feature_key(src, name)
            desc = str(it.get("description") or "")[:300]
            prev = known.get(k)
            if prev is not None and prev.get("description") == desc:
                continue
            s.add(AuditLog(actor="etsy_department", action=FEATURE_ACTION, artifact=k,
                           detail={"key": k, "source": src, "name": name, "description": desc,
                                   "observed_at": observed_at, "changed": prev is not None}))
            filed.append(k)
    return {"filed": filed, "unclassified": [k for k, v in features(db).items()
                                             if v["class"] == "unclassified"]}


def classify(db, key: str, *, cls: str, reason: str, by: str) -> dict:
    from ..core.models import AuditLog

    if cls not in FEATURE_CLASSES:
        raise FeatureRefused(f"{cls!r} is not one of {FEATURE_CLASSES}")
    if len((reason or "").split()) < 4:
        raise FeatureRefused("a classification says why")
    if key not in features(db):
        raise FeatureRefused(f"{key!r} was never discovered")
    with db.session() as s:
        s.add(AuditLog(actor=by[:60] or "etsy_department", action=CLASSIFY_ACTION,
                       artifact=key, detail={"key": key, "class": cls, "reason": reason[:400],
                                             "by": by[:60]}))
    return {"key": key, "class": cls}


def may_adopt(db, key: str) -> dict:
    f = features(db).get(key)
    if f is None:
        return {"may_adopt": False, "why": "never discovered or classified"}
    ok = f["class"] == "useful"
    return {"may_adopt": ok, "class": f["class"],
            "why": "classified useful" if ok else f"classified {f['class']}: not adopted"}


# ---- W4-C13 F-599: Shop Manager UI drift --------------------------------------------------
#
# F-599: "Quarterly and after material Etsy announcements, compare the observed Shop Manager
# navigation/surfaces with the maintained surface inventory. New, renamed or removed tabs create
# review tasks." The API half (the OpenAPI review card) exists. This is the navigation half: the
# owner's (or a later collector's) dated reading of the Shop Manager navigation is compared with
# the inventory's `where` paths. Differences become ONE batched, non-interrupting review card
# (`store:etsy.ui_drift_review`, the same batching as `store:etsy.openapi_review`), restated by
# a later reading. A reading is due every `UI_DRIFT_DAYS` or after an announcement.

UI_READING = "etsy.shop_manager_nav"
UI_REVIEW_KEY = "store:etsy.ui_drift_review"
UI_DRIFT_DAYS = 91
UI_TRIGGERS = ("quarterly", "announcement")


def _nav_paths() -> dict[str, str]:
    from ..intel import etsy_surfaces as es

    out = {}
    for s in es.surfaces():
        where = (s.where or "").strip()
        if where.lower().startswith("shop manager"):
            out[where.lower()] = s.key
    return out


def ui_drift(db, *, observed: list[str], observed_at, trigger: str) -> dict:
    """Compare the observed navigation with the inventory; card the differences."""
    from sqlalchemy import select

    from ..core.models import OperatingReading, OwnerAction

    if trigger not in UI_TRIGGERS:
        raise FeatureRefused(f"a UI drift reading is {UI_TRIGGERS}")
    at = observed_at if isinstance(observed_at, datetime) else datetime.fromisoformat(
        str(observed_at))
    at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    seen = {p.strip().lower() for p in observed if p.strip()}
    if not seen:
        raise FeatureRefused("an empty navigation reading is not a reading")
    inv = _nav_paths()
    new = sorted(seen - set(inv))
    removed = sorted(inv[p] for p in set(inv) - seen)
    # renamed: the same last segment under a different parent, or the same parent with one
    # new and one missing leaf -- reported as a pair for a person to confirm.
    renamed = []
    for p in list(new):
        parent = p.rsplit(">", 1)[0].strip()
        gone = [q for q in set(inv) - seen if q.rsplit(">", 1)[0].strip() == parent]
        if len(gone) == 1:
            renamed.append({"was": gone[0], "now": p, "surface": inv[gone[0]]})
    payload = {"observed_at": at.isoformat(), "trigger": trigger, "observed": sorted(seen),
               "new": new, "removed": removed, "renamed": renamed}
    with db.session() as s:
        key = at.strftime("%Y-%m-%dT%H%M%S")
        prior = s.scalar(select(OperatingReading).where(OperatingReading.kind == UI_READING,
                                                        OperatingReading.period_key == key))
        if prior is None:
            s.add(OperatingReading(kind=UI_READING, period_key=key, payload=payload, at=at))
        else:
            prior.payload = payload          # the same reading entered again replaces itself
        drift = bool(new or removed)
        row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == UI_REVIEW_KEY,
                                                 OwnerAction.done.is_(False)))
        if drift:
            reason = (f"Shop Manager navigation read {at.date()} ({trigger}) differs from the "
                      f"surface inventory: new {new[:8]}, removed {removed[:8]}, possibly "
                      f"renamed {[r['now'] for r in renamed][:5]}")
            if row is None:
                s.add(OwnerAction(
                    requirement_key=UI_REVIEW_KEY, max_cost_cad=0.0, minutes=15,
                    action=("Review the Shop Manager navigation changes against the surface "
                            "inventory (intel.etsy_surfaces) and confirm each new, renamed or "
                            "removed tab"),
                    reason=reason,
                    consequence_of_delay=("the inventory may describe tabs that moved; a new "
                                          "capability goes unclassified"),
                    blocks="Etsy surface registry review (not a first-sale blocker)"))
            else:
                row.reason = reason
    return {**payload, "review_card": UI_REVIEW_KEY if drift else None}


def ui_drift_due(db, *, now: datetime | None = None, announcement: bool = False) -> dict:
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == UI_READING)
                       .order_by(desc(OperatingReading.at)).limit(1))
        last = row.at if row else None
    last = (last if last is None or last.tzinfo else last.replace(tzinfo=timezone.utc))
    if announcement:
        return {"due": True, "why": "a material Etsy announcement"}
    if last is None:
        return {"due": True, "why": "the navigation has never been read"}
    age = (now - last).days
    return {"due": age >= UI_DRIFT_DAYS, "last": last.isoformat(), "age_days": age,
            "why": f"last read {age} days ago (every {UI_DRIFT_DAYS})"}


# ---- W4-C13 F-600: the Etsy autopilot contract, per surface ---------------------------------
#
# F-600: the Etsy department is never "done": it observes, diagnoses, prioritises, researches,
# tests, proves, deploys, verifies remotely, monitors and learns across every supported shop
# surface. `contract()` reads, per surface, which stage is backed by running code and which is
# not, so the gap is a list rather than a claim. A surface the company does not act on
# (not_applicable, unsupported) is out of scope by its verdict, stated.

AUTOPILOT_STAGES = ("observe", "diagnose", "prioritise", "research", "test", "prove",
                    "deploy", "verify_remotely", "monitor", "learn")


def contract(db) -> dict:
    from ..intel import etsy_surfaces as es

    inv = reverify(db)
    rows, gaps = [], 0
    for it in inv["items"]:
        ch = it["channel"]
        if ch in ("not_applicable", "unsupported"):
            rows.append({"surface": it["key"], "in_scope": False,
                         "why": f"verdict {it['verdict']}: not a surface the shop acts on"})
            continue
        observed = it.get("evidence_state") not in (None, es.NO_COLLECTOR)
        acts = ch == "api" and it["verdict"] == es.ACT
        stages = {
            "observe": "collector or owner reading" if observed else None,
            "diagnose": "surface_inventory.reverify" if observed else None,
            "prioritise": "Laura executive tick (provider: storefront)" if observed else None,
            "research": "intel.research (research tasks)",
            "test": "improve sandbox / storefront change budget" if acts else None,
            "prove": "release gates and read-back" if acts else None,
            "deploy": "publish pipeline behind the storefront grant" if acts else None,
            "verify_remotely": "census / shop snapshot read-back" if observed else None,
            "monitor": "daily collectors and incidents" if observed else None,
            "learn": "improve.mine lessons" if observed else None,
        }
        missing = [s for s in AUTOPILOT_STAGES if not stages[s]]
        gaps += len(missing)
        rows.append({"surface": it["key"], "in_scope": True, "channel": ch,
                     "stages": stages, "missing": missing})
    in_scope = [r for r in rows if r["in_scope"]]
    return {"stages": list(AUTOPILOT_STAGES), "surfaces": rows,
            "in_scope": len(in_scope), "fully_covered": sum(1 for r in in_scope
                                                            if not r["missing"]),
            "gaps": gaps, "done": False,
            "rule": "the Etsy department is never done; gaps are listed, never assumed closed"}
