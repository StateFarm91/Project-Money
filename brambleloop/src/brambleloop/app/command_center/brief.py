"""F-666 Overnight Brief: "while you were away", composed from durable rows (W4-CLOSE6).

  F-666  "'While you were away' shows autonomous hours, tasks/experiments, products
          advanced/rejected, image candidates, Etsy findings, compute/ad spend, sales/profit,
          incidents and decisions."

The Overnight handoff on HOME (`tabs.morning_brief`, F-896) already carried what changed,
completed tasks, money spent by kind, incidents, discoveries, the queue and decisions. It did
not carry autonomous hours, experiments, products advanced or rejected, image candidates, Etsy
findings, or sales and profit. `morning_sections` adds those, as envelopes the handoff card
renders, over the same window. `brief` is the full composed reading of all nine items. Each section here:
- is read from its own durable rows and names them in `sources`;
- carries a `status`. MEASURED means rows were read. UNKNOWN means the reader failed or no
  source exists, and it is never shown as 0.
Sales are UNMEASURED until the order source is connected and read; they are never CA$0.00.

No model is called and nothing is written.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

MEASURED, UNKNOWN = "MEASURED", "UNKNOWN"

# Audit actions that move a product forward, and ones that stop or reverse it. Named, not
# pattern-matched: a new action is added here deliberately.
ADVANCED = ("cir.drafted", "gate.certified", "listing.drafted", "store.published")
REJECTED = ("creative.returned_to_development", "creative.blinded_refused",
            "store.publish_refused", "gate.refused", "product.retired")
IMAGE = ("creative.grid_tournament", "assets.gallery_frames", "creative.reference_reading")
ETSY = ("mjs.findings", "mjs.mission_events", "intel.gallery_analysis", "seo.cycle_changed")


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _section(fn, sources: list[str]) -> dict:
    try:
        out = fn()
        return {"status": MEASURED, "sources": sources, **out}
    except Exception as exc:  # noqa: BLE001 - one unreadable source must not blank the brief
        return {"status": UNKNOWN, "sources": sources,
                "reason": f"unreadable: {type(exc).__name__}"}


def _audits(db, since, actions) -> Counter:
    from ...core.models import AuditLog

    with db.session() as s:
        return Counter(a for (a,) in s.execute(
            select(AuditLog.action).where(AuditLog.at >= since,
                                          AuditLog.action.in_(actions))).all())


def brief(db, *, since: datetime | None = None, now: datetime | None = None) -> dict:
    from ...core.models import CostEntry, Experiment, Incident, Job, JobStatus, OwnerAction

    now = now or datetime.now(timezone.utc)
    basis = "since your last view"
    if since is None:
        since, basis = now - timedelta(hours=12), "no previous view recorded; the last 12 h"
    since = _aware(since)

    def hours():
        with db.session() as s:
            done = [_aware(f) for (f,) in s.execute(select(Job.finished_at).where(
                Job.status == JobStatus.DONE, Job.finished_at >= since)).all() if f]
        active = {d.replace(minute=0, second=0, microsecond=0) for d in done}
        window = max((now - since).total_seconds() / 3600, 0.0)
        return {"active_hours": len(active), "window_hours": round(window, 1),
                "why": "clock hours in the window in which at least one job completed"}

    def tasks():
        with db.session() as s:
            rows = s.execute(select(Job.agent, Job.status).where(
                Job.finished_at >= since)).all()
            exps = list(s.scalars(select(Experiment).where(Experiment.created_at >= since)))
        by = Counter(st.value if hasattr(st, "value") else str(st) for _a, st in rows)
        agents = Counter(a for a, st in rows if st == JobStatus.DONE)
        return {"completed": by.get("done", 0), "failed": by.get("failed", 0),
                "dead": by.get("dead", 0), "by_agent": dict(agents.most_common(6)),
                "experiments_started": [{"name": e.name, "state": e.state,
                                         "source": f"experiments:{e.id}"} for e in exps[:6]]}

    def products():
        c = _audits(db, since, ADVANCED + REJECTED)
        return {"advanced": {a: c[a] for a in ADVANCED if c[a]},
                "rejected": {a: c[a] for a in REJECTED if c[a]}}

    def images():
        c = _audits(db, since, IMAGE)
        return {"events": {a: c[a] for a in IMAGE if c[a]}}

    def etsy():
        c = _audits(db, since, ETSY)
        return {"events": {a: c[a] for a in ETSY if c[a]}}

    def spend():
        with db.session() as s:
            rows = s.execute(select(CostEntry.kind, CostEntry.amount_cad).where(
                CostEntry.at >= since)).all()
        by = Counter()
        for kind, amt in rows:
            by[kind or "unattributed"] += float(amt or 0.0)
        compute = round(sum(v for k, v in by.items() if k != "ads"), 6)
        return {"compute_cad": compute, "ads_cad": round(by.get("ads", 0.0), 6),
                "by_kind": {k: round(v, 6) for k, v in by.items()},
                "basis": "recorded exposure (cost_entries), not a reconciled bill"}

    def sales():
        from . import readers

        r = readers.revenue(db)
        return {"revenue": r, "profit": ("UNMEASURED: profit needs measured revenue and the "
                                         "accountant's cost attribution"
                                         if r.get("state") != "MEASURED" else
                                         "see the accountant view")}

    def incidents():
        with db.session() as s:
            new = list(s.scalars(select(Incident).where(Incident.at >= since)
                                 .order_by(Incident.id.desc())))
            still = sum(1 for i in new if not i.resolved)
        return {"opened": len(new), "still_open": still,
                "items": [{"severity": i.severity, "summary": i.summary[:160],
                           "resolved": bool(i.resolved), "source": f"incidents:{i.id}"}
                          for i in new[:6]]}

    def decisions():
        with db.session() as s:
            opened = list(s.scalars(select(OwnerAction).where(OwnerAction.at >= since)))
            closed = list(s.scalars(select(OwnerAction).where(
                OwnerAction.done == True, OwnerAction.state_at >= since)))  # noqa: E712
            waiting = s.scalars(select(OwnerAction).where(
                OwnerAction.done == False)).all()  # noqa: E712
        return {"new_for_you": [{"action": a.action[:160], "source": f"owner_actions:{a.id}"}
                                for a in opened[:6]],
                "settled": len(closed), "waiting_on_you": len(waiting)}

    sections = {
        "autonomous_hours": _section(hours, ["jobs.finished_at"]),
        "tasks_and_experiments": _section(tasks, ["jobs", "experiments"]),
        "products": _section(products, ["audit_log"]),
        "image_candidates": _section(images, ["audit_log"]),
        "etsy_findings": _section(etsy, ["audit_log"]),
        "spend": _section(spend, ["cost_entries"]),
        "sales_and_profit": _section(sales, ["ledger", "orders"]),
        "incidents": _section(incidents, ["incidents"]),
        "decisions": _section(decisions, ["owner_actions"]),
    }
    return {"since": since.isoformat(), "as_of": now.isoformat(), "basis": basis,
            "sections": sections,
            "unknown": sorted(k for k, v in sections.items() if v["status"] == UNKNOWN)}


def morning_sections(db, *, since: datetime, now: datetime | None = None) -> dict:
    """The F-666 items the F-896 handoff lacked, as Command Center envelopes."""
    from .providers import envelope, unknown

    full = brief(db, since=since, now=now)["sections"]

    def env(key, items, sources, **extra):
        sec = full[key]
        if sec["status"] != MEASURED:
            return unknown(sec.get("reason") or "unreadable", "command_center.brief",
                           sec["sources"])
        return envelope("OK", items, sources, provider="command_center.brief", **extra)

    h, t, p = full["autonomous_hours"], full["tasks_and_experiments"], full["products"]
    rev = (full["sales_and_profit"].get("revenue") or {})
    return {
        "autonomous_hours": env("autonomous_hours", [
            {"label": "hours with completed work", "value": h.get("active_hours"),
             "of_hours": h.get("window_hours"), "why": h.get("why")}], ["jobs"]),
        "experiments": env("tasks_and_experiments", t.get("experiments_started") or [],
                           ["experiments"]),
        "products_moved": env("products", [
            {"direction": d, "action": a, "count": n}
            for d in ("advanced", "rejected") for a, n in (p.get(d) or {}).items()],
            ["audit_log"]),
        "image_candidates": env("image_candidates", [
            {"action": a, "count": n}
            for a, n in (full["image_candidates"].get("events") or {}).items()], ["audit_log"]),
        "etsy_findings": env("etsy_findings", [
            {"action": a, "count": n}
            for a, n in (full["etsy_findings"].get("events") or {}).items()], ["audit_log"]),
        "sales_and_profit": env("sales_and_profit", [
            {"label": "revenue", "state": rev.get("state"), "display": rev.get("display"),
             "why": rev.get("why")},
            {"label": "profit", "state": "UNMEASURED" if rev.get("state") != "MEASURED"
             else "SEE_ACCOUNTANT", "why": full["sales_and_profit"].get("profit")}],
            ["ledger", "orders"]),
    }
