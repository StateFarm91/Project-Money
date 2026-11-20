"""What each department actually produced, as evidence, reviewed before it reaches Laura.

The owner's direction (2026-10-26): departments do real work through the job queue, return
evidence, pass quality review and report to Laura. The reporting path already exists:
`autonomy.department_review` measures a department (`autonomy.kpis.compute`), writes the
snapshot to company memory as `kpi_snapshot`, and Laura's executive loop reads those
snapshots. What the snapshot carried was activity only (useful completions, dead letters,
cadence freshness) -- the same three generic KPIs for every charter. None of it said what a
department had *produced*.

This module adds, per department, readers over the rows and readings the department's own
jobs write: the storefront review, the growth journey and distribution plans, content drafted,
certified releases, verified gallery assets, observed benchmark listings and research, the
books and spend, support cases. Each item is

    {"value": ..., "status": OK | STALE | UNKNOWN, "sources": [...], "why": ...}

and `review()` is the quality gate every item passes before it is reported: an OK or STALE item
must cite at least one source row and carry a value; an UNKNOWN item must carry no value (never
a 0 standing in for "not measured"); a count must be a non-negative integer. An item that fails
is REJECTED -- reported as rejected, never passed through.

Reads only; writes nothing; no network, no model, CA$0.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

OK, STALE, UNKNOWN, REJECTED = "OK", "STALE", "UNKNOWN", "REJECTED"
STALE_AFTER_HOURS = 48

# Charter key -> the departments the owner named that it serves.
NAMED = {
    "store_commerce": ("Storefront",),
    "growth": ("Growth", "Marketing"),
    "product_design": ("Product Development",),
    "visual": ("Visual Production",),
    "intelligence": ("Market Intelligence",),
    "finance": ("Finance",),
    "support": ("Customer Experience",),
}


def _aware(v):
    return v if v is None or v.tzinfo else v.replace(tzinfo=timezone.utc)


def _item(value, sources, *, at=None, now=None, why=""):
    if value is None:
        return {"value": None, "status": UNKNOWN, "sources": list(sources or []),
                "why": why or "no row records this yet"}
    status = OK
    if at is not None and now is not None and (now - _aware(at)) > timedelta(
            hours=STALE_AFTER_HOURS):
        status = STALE
        why = why or f"newest source is older than {STALE_AFTER_HOURS} h"
    return {"value": value, "status": status, "sources": list(sources or []), "why": why}


def _reading(db, kind: str):
    """(payload, source ref, at) of the newest operating reading of `kind`, or Nones."""
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == kind)
                       .order_by(desc(OperatingReading.at), desc(OperatingReading.id)).limit(1))
        if row is None:
            return None, None, None
        return dict(row.payload or {}), f"operating_readings:{row.id}", row.at


def _audit(db, action: str):
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == action)
                       .order_by(AuditLog.id.desc()).limit(1))
        return (dict(row.detail or {}), f"audit_log:{row.id}", row.at) if row else (
            None, None, None)


def _count(db, model, *where):
    from sqlalchemy import func, select

    with db.session() as s:
        return int(s.scalar(select(func.count()).select_from(model).where(*where)) or 0)


# ---- per department ------------------------------------------------------------------------

def storefront(db, now) -> dict:
    from ..core.models import Listing

    rev, ref, at = _reading(db, "storefront.review")
    out = {}
    if rev is None:
        for k in ("surfaces_ok", "agent_gaps", "owner_gaps", "surfaces_unknown"):
            out[k] = _item(None, [], why="no storefront.review reading yet")
    else:
        rows = rev.get("surfaces") or []
        out["surfaces_ok"] = _item(sum(1 for r in rows if r.get("status") == "OK"), [ref],
                                   at=at, now=now)
        out["agent_gaps"] = _item(len(rev.get("agent_gaps") or []), [ref], at=at, now=now)
        out["owner_gaps"] = _item(len(rev.get("owner_gaps") or []), [ref], at=at, now=now)
        out["surfaces_unknown"] = _item(len(rev.get("unknown") or []), [ref], at=at, now=now)
    n = _count(db, Listing)
    out["listings_drafted"] = _item(n, ["listings"])
    return out


def growth(db, now) -> dict:
    from ..core.models import ContentPiece, RegisteredExperiment

    out = {}
    jr, jref, jat = _reading(db, "growth.journey")
    if jr is None:
        out["listings_journey_audited"] = _item(None, [], why="no growth.journey reading yet")
        out["friction_incidents_open"] = _item(None, [], why="no growth.journey reading yet")
    else:
        fr = jr.get("friction") or {}
        out["listings_journey_audited"] = _item(fr.get("listings"), [jref], at=jat, now=now)
        out["friction_incidents_open"] = _item(len(fr.get("incidents_open") or []), [jref],
                                               at=jat, now=now)
    dr, dref, dat = _reading(db, "growth.distribution")
    if dr is None:
        out["pins_ready"] = _item(None, [], why="no growth.distribution reading yet")
    else:
        out["pins_ready"] = _item((dr.get("pins") or {}).get("ready"), [dref], at=dat, now=now)
    out["experiments_registered"] = _item(_count(db, RegisteredExperiment),
                                          ["registered_experiments"])
    out["experiments_concluded"] = _item(
        _count(db, RegisteredExperiment, RegisteredExperiment.state == "concluded"),
        ["registered_experiments"])
    # Marketing: the content ecosystem drafted and held (marketing.schedule).
    out["content_pieces_drafted"] = _item(_count(db, ContentPiece), ["content_pieces"])
    out["content_pieces_published"] = _item(
        _count(db, ContentPiece, ContentPiece.state == "published"), ["content_pieces"])
    return out


def product_design(db, now) -> dict:
    from ..core.models import Job, JobStatus, PatternVersion

    since = now - timedelta(days=7)
    return {
        "certified_releases": _item(
            _count(db, PatternVersion, PatternVersion.certified == True),  # noqa: E712
            ["pattern_versions"]),
        "uncertified_versions": _item(
            _count(db, PatternVersion, PatternVersion.certified == False),  # noqa: E712
            ["pattern_versions"]),
        "concepts_drafted_7d": _item(
            _count(db, Job, Job.job_type == "cir.draft", Job.status == JobStatus.DONE,
                   Job.finished_at >= since), ["jobs:cir.draft"]),
        "revisions_7d": _item(
            _count(db, Job, Job.job_type == "cir.revise", Job.status == JobStatus.DONE,
                   Job.finished_at >= since), ["jobs:cir.revise"]),
    }


def visual(db, now) -> dict:
    from ..core.models import ListingAsset

    total = _count(db, ListingAsset)
    out = {"gallery_assets": _item(total, ["listing_assets"]),
           "gallery_assets_approved": _item(
               _count(db, ListingAsset, ListingAsset.approved == True),  # noqa: E712
               ["listing_assets"])}
    pp, ref, at = _reading(db, "creative.photo_principles")
    out["shot_plan_gaps"] = (_item(pp.get("gaps"), [ref], at=at, now=now) if pp else
                             _item(None, [], why="no creative.photo_principles reading yet"))
    return out


def intelligence(db, now) -> dict:
    from ..core.models import BenchmarkListing

    out = {"benchmark_listings_observed": _item(_count(db, BenchmarkListing),
                                                ["benchmark_listings"])}
    snap, ref, at = _reading(db, "radar.competitor_snapshot")
    out["competitor_groups"] = (_item(len(snap.get("groups") or []), [ref], at=at, now=now)
                                if snap else _item(None, [], why="no competitor snapshot yet"))
    try:
        from ..intel import research as R

        R._ensure(db)
        out["research_open"] = _item(_count(db, R.ResearchTask, R.ResearchTask.state == R.OPEN),
                                     ["research_tasks"])
        out["research_answered"] = _item(
            _count(db, R.ResearchTask, R.ResearchTask.state == R.ANSWERED), ["research_tasks"])
    except Exception as exc:  # noqa: BLE001 - an unreadable store is UNKNOWN
        out["research_open"] = _item(None, [], why=f"unreadable: {type(exc).__name__}")
        out["research_answered"] = _item(None, [], why=f"unreadable: {type(exc).__name__}")
    return out


def finance(db, now) -> dict:
    from sqlalchemy import func, select

    from ..core.models import CostEntry

    out = {}
    rec, ref, at = _audit(db, "finance.reconciled")
    if rec is None:
        out["net_sales_cad"] = _item(None, [], why="the books have not been reconciled yet")
    else:
        out["net_sales_cad"] = _item((rec.get("pl") or {}).get("net_sales_cad"), [ref],
                                     at=at, now=now)
    since = now - timedelta(days=30)
    with db.session() as s:
        n, total = s.execute(select(func.count(), func.coalesce(func.sum(CostEntry.amount_cad),
                                                                0.0))
                             .where(CostEntry.at >= since)).one()
    # No cost row is not CA$0.00 (the morning brief's rule too): UNKNOWN until a row exists.
    out["recorded_spend_30d_cad"] = (
        _item(round(float(total or 0.0), 2), ["cost_entries"],
              why=f"{int(n)} cost entries in 30 days") if n else
        _item(None, [], why="no cost_entries rows in 30 days; not rendered as CA$0.00"))
    ch, cref, cat = _audit(db, "finance.challenged")
    out["cfo_challenges"] = (_item(len(ch.get("challenges") or []), [cref], at=cat, now=now)
                             if ch is not None else _item(None, [],
                                                          why="no CFO challenge yet"))
    out["cfo_blocking"] = (_item(ch.get("blocking"), [cref], at=cat, now=now)
                           if ch is not None else _item(None, [], why="no CFO challenge yet"))
    return out


def support(db, now) -> dict:
    from ..core.models import SupportCase

    cases = _count(db, SupportCase)
    if not cases:
        return {"cases": _item(None, [], why="no customer case exists yet"),
                "cases_open": _item(None, [], why="no customer case exists yet"),
                "replies_drafted": _item(None, [], why="no customer case exists yet")}
    return {"cases": _item(cases, ["support_cases"]),
            "cases_open": _item(_count(db, SupportCase, SupportCase.resolved == False),  # noqa
                                ["support_cases"]),
            "replies_drafted": _item(_count(db, SupportCase, SupportCase.answer != ""),
                                     ["support_cases"])}


READERS = {"store_commerce": storefront, "growth": growth, "product_design": product_design,
           "visual": visual, "intelligence": intelligence, "finance": finance,
           "support": support}


# ---- the quality review --------------------------------------------------------------------

def review(evidence: dict) -> dict:
    """Every item checked before it is reported; a failing item is REJECTED, never passed."""
    accepted, rejected = {}, []
    for key, it in (evidence or {}).items():
        why = None
        st, val = it.get("status"), it.get("value")
        if st not in (OK, STALE, UNKNOWN):
            why = f"status {st!r} is not a reporting status"
        elif st == UNKNOWN and val is not None:
            why = "an UNKNOWN item carries a value"
        elif st in (OK, STALE) and val is None:
            why = "an OK item has no value"
        elif st in (OK, STALE) and not it.get("sources"):
            why = "no source row is cited"
        elif isinstance(val, bool) or (isinstance(val, (int, float)) and val < 0 and
                                       not key.endswith("_cad")):
            why = "a count must be a non-negative number"
        if why:
            rejected.append({"key": key, "why": why})
            accepted[key] = {**it, "status": REJECTED, "why": why}
        else:
            accepted[key] = it
    return {"items": accepted, "passed": len(evidence or {}) - len(rejected),
            "rejected": rejected}


def summary(db) -> list[dict]:
    """Per department, from its newest reviewed snapshot: what the morning brief reports."""
    from . import memory

    out, seen = [], set()
    for snap in memory.recall(db, kind="kpi_snapshot", limit=200):
        key = snap["department"]
        ev = (snap.get("body") or {}).get("evidence")
        if key in seen or not ev:
            continue
        seen.add(key)
        items = ev.get("items") or {}
        out.append({"department": key, "named": ev.get("departments") or [],
                    "snapshot": snap["key"], "passed": ev.get("passed"),
                    "rejected": [r["key"] for r in ev.get("rejected") or []],
                    "unknown": sorted(k for k, v in items.items() if v.get("status") == UNKNOWN),
                    "stale": sorted(k for k, v in items.items() if v.get("status") == STALE),
                    "values": {k: v.get("value") for k, v in items.items()
                               if v.get("status") in (OK, STALE)}})
    return sorted(out, key=lambda x: x["department"])


def collect(db, key: str, *, now: datetime | None = None) -> dict | None:
    """The reviewed evidence of one department, or None for a charter with no reader."""
    reader = READERS.get(key)
    if reader is None:
        return None
    now = now or datetime.now(timezone.utc)
    try:
        raw = reader(db, now)
    except Exception as exc:  # noqa: BLE001 - an unreadable department is reported, not hidden
        return {"departments": list(NAMED.get(key, ())), "items": {}, "passed": 0,
                "rejected": [{"key": "*", "why": f"evidence unreadable: "
                                                 f"{type(exc).__name__}: {str(exc)[:160]}"}]}
    return {"departments": list(NAMED.get(key, ())), **review(raw)}
