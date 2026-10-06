"""Direct readers over the production database (F-898: the same durable state production uses).

Every function returns a provider-contract envelope (`providers.envelope`) whose `sources`
name the rows it read (`table:id`). Nothing here writes, renders, enqueues or calls a model,
and nothing here has a canned path: an empty table is an empty list, an unreadable one is
UNKNOWN.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from .providers import envelope, guard, now_iso, unknown

SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def _iso(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return str(v)


def row_dict(row, *, max_text: int = 600) -> dict:
    """A generic, JSON-safe view of an ORM row (for drill-down)."""
    out = {}
    for col in row.__table__.columns:
        v = getattr(row, col.key, None)
        if isinstance(v, datetime):
            v = _iso(v)
        elif hasattr(v, "value") and not isinstance(v, (int, float, str)):
            v = v.value
        elif isinstance(v, str) and len(v) > max_text:
            v = v[:max_text] + "..."
        out[col.key] = v
    return out


def _since(hours: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


# ---- incidents ----------------------------------------------------------------


def incidents(db, *, limit: int = 25) -> dict:
    from ...core.models import Incident

    def read():
        with db.session() as s:
            rows = list(s.scalars(select(Incident).where(Incident.resolved == False)  # noqa: E712
                                  .order_by(Incident.at.desc()).limit(200)))
            items = [{"id": r.id, "severity": r.severity, "summary": r.summary[:400],
                      "signature": r.signature, "product_slug": r.product_slug,
                      "halts_publication": bool(r.halts_publication),
                      "report_count": r.report_count, "at": _iso(r.at),
                      "source": f"incidents:{r.id}"} for r in rows]
        items.sort(key=lambda i: (SEVERITY_RANK.get(i["severity"], 9), i["at"] or ""))
        items = items[:limit]
        crit = [i for i in items if i["severity"] in ("P0", "P1")]
        status = "BLOCKED" if any(i["halts_publication"] for i in items) else (
            "DEGRADED" if crit else "OK")
        return envelope(status, items, [i["source"] for i in items] or ["incidents"],
                        provider="incidents (open)", open_total=len(rows),
                        reason=(f"{len(crit)} P0/P1 incidents open" if crit else None))

    return guard("incidents", read, sources=["incidents"])


# ---- queue / jobs ---------------------------------------------------------------


def queue(db) -> dict:
    from ...core.models import Job, JobStatus

    def read():
        with db.session() as s:
            counts = {(k.value if hasattr(k, "value") else str(k)): int(v)
                      for k, v in s.execute(select(Job.status, func.count())
                                            .group_by(Job.status))}
            last_done = s.scalar(select(func.max(Job.finished_at)).where(
                Job.status == JobStatus.DONE))
            dead = list(s.scalars(select(Job).where(Job.status == JobStatus.DEAD)
                                  .order_by(Job.id.desc()).limit(10)))
            dead_items = [{"id": j.id, "agent": j.agent, "job_type": j.job_type,
                           "attempts": j.attempts, "last_error": (j.last_error or "")[:300],
                           "finished_at": _iso(j.finished_at), "source": f"jobs:{j.id}"}
                          for j in dead]
        items = [{"status": k, "count": v} for k, v in sorted(counts.items())]
        status = "DEGRADED" if counts.get("dead") else "OK"
        if not counts:
            return envelope("UNKNOWN", [], ["jobs"], basis="unknown",
                            reason="no job has ever been recorded", provider="jobs")
        return envelope(status, items, ["jobs"], provider="jobs",
                        last_job_done_at=_iso(last_done), dead_letters=dead_items,
                        reason=(f"{counts.get('dead')} dead-lettered jobs"
                                if counts.get("dead") else None))

    return guard("jobs", read, sources=["jobs"])


def jobs_window(db, hours: float = 24) -> dict:
    from ...core.models import Job, JobStatus

    def read():
        since = _since(hours)
        with db.session() as s:
            done = list(s.execute(select(Job.agent, func.count()).where(
                Job.status == JobStatus.DONE, Job.finished_at >= since).group_by(Job.agent)))
            failed = s.scalar(select(func.count()).select_from(Job).where(
                Job.status.in_([JobStatus.FAILED, JobStatus.DEAD]),
                Job.finished_at >= since)) or 0
            created = s.scalar(select(func.count()).select_from(Job).where(
                Job.created_at >= since)) or 0
            last = s.scalar(select(Job).where(Job.status == JobStatus.DONE)
                            .order_by(Job.finished_at.desc()).limit(1))
            last_item = None if last is None else {
                "id": last.id, "agent": last.agent, "job_type": last.job_type,
                "finished_at": _iso(last.finished_at), "source": f"jobs:{last.id}"}
        items = [{"agent": a, "completed": int(n)} for a, n in sorted(done)]
        return envelope("OK", items, ["jobs"], provider=f"jobs (last {hours:g}h)",
                        completed=sum(i["completed"] for i in items), failed=int(failed),
                        created=int(created), window_hours=hours,
                        last_useful_action=last_item)

    return guard("jobs_window", read, sources=["jobs"])


# ---- audit / timeline --------------------------------------------------------------


# Audit actions that are machine chatter rather than company events (timeline/brief filter).
_CHATTER = ("job.claimed", "job.lease", "swarm.lane_held", "heartbeat", "worker.tick")


def audit_events(db, *, since: datetime | None = None, limit: int = 50,
                 include_chatter: bool = False) -> list[dict]:
    from ...core.models import AuditLog

    with db.session() as s:
        q = select(AuditLog).order_by(AuditLog.id.desc())
        if since is not None:
            q = q.where(AuditLog.at >= since)
        rows = list(s.scalars(q.limit(limit * 4 if not include_chatter else limit)))
    out = []
    for r in rows:
        if not include_chatter and r.action.startswith(_CHATTER):
            continue
        detail = dict(r.detail or {})
        detail.pop("seal", None)
        out.append({"id": r.id, "at": _iso(r.at), "actor": r.actor, "action": r.action,
                    "artifact": r.artifact, "phase": getattr(r.phase, "value", r.phase),
                    "summary": str(detail.get("reason") or detail.get("summary")
                                   or detail.get("why") or "")[:300],
                    "source": f"audit_log:{r.id}"})
        if len(out) >= limit:
            break
    return out


# ---- owner actions / approvals -----------------------------------------------------


def owner_inbox(db) -> dict:
    """The existing single owner queue (build2.executor.approval_inbox, F-663)."""
    from ...build2 import executor

    return executor.approval_inbox(db)


def owner_actions_summary(db) -> dict:
    def read():
        inbox = owner_inbox(db)
        cards = inbox.get("cards") or []
        items = [{"card_id": (f"gate:{c['gate']}" if c.get("gate") else
                              f"owner_action:{c.get('owner_action_id')}"),
                  "what": c.get("what") or c.get("action"),
                  "max_spend_cad": c.get("max_spend_cad"),
                  "minutes": c.get("minutes"),
                  "consequence_of_waiting": c.get("consequence_of_waiting")}
                 for c in cards]
        return envelope("BLOCKED" if items else "OK", items,
                        ["owner_actions", "build2.executor.approval_inbox"],
                        provider="build2.executor.approval_inbox",
                        reason=(f"{len(items)} owner decisions open" if items else None),
                        open_actions=len(items))

    return guard("owner_actions", read, sources=["owner_actions"])


# ---- products / store --------------------------------------------------------------


def products(db, *, limit: int = 100) -> dict:
    from ...core.models import Listing, PatternVersion, Product

    def read():
        with db.session() as s:
            prods = list(s.scalars(select(Product).order_by(Product.id).limit(limit)))
            items = []
            for p in prods:
                pv = s.scalar(select(PatternVersion).where(PatternVersion.product_id == p.id)
                              .order_by(PatternVersion.id.desc()).limit(1))
                listing = s.scalar(select(Listing).where(Listing.product_slug == p.slug)
                                   .order_by(Listing.id.desc()).limit(1))
                srcs = [f"products:{p.id}"]
                if pv is not None:
                    srcs.append(f"pattern_versions:{pv.id}")
                if listing is not None:
                    srcs.append(f"listings:{listing.id}")
                items.append({
                    "slug": p.slug, "title": p.title, "status": p.status,
                    "version": pv.version if pv else None,
                    "certified": bool(pv.certified) if pv else False,
                    "release_hash": (pv.release_hash if pv else None),
                    "listing_state": listing.state if listing else None,
                    "on_etsy": bool(listing and listing.etsy_listing_id),
                    "price_cad": (listing.price_cad if listing else None),
                    "sources": srcs})
        if not items:
            return envelope("UNKNOWN", [], ["products"], basis="unknown",
                            reason="no product recorded", provider="products")
        return envelope("OK", items, ["products", "pattern_versions", "listings"],
                        provider="products+pattern_versions+listings",
                        certified=sum(1 for i in items if i["certified"]),
                        on_etsy=sum(1 for i in items if i["on_etsy"]))

    return guard("products", read, sources=["products"])


# ---- money (fallback readers; the Accountant provider is primary) -----------------


VALUE_STATES = ("MEASURED", "ESTIMATED", "MODELLED", "RECORDED")


def _money(value, *, state: str, basis: str, sources: list, why: str = "") -> dict:
    """A money value. Only a measured/estimated/modelled/recorded state carries a number;
    every other state carries `value_cad: None` and displays the state word, never 0."""
    if state not in VALUE_STATES or value is None:
        st = state if state not in VALUE_STATES else "UNKNOWN"
        return {"value_cad": None, "state": st, "basis": "unknown", "display": st,
                "sources": sources, "why": why}
    suffix = "" if state == "MEASURED" else f" ({state.lower()})"
    return {"value_cad": round(float(value), 2), "state": state, "basis": basis,
            "display": f"CA${float(value):,.2f}{suffix}", "sources": sources, "why": why}


def revenue(db) -> dict:
    from .. import dashboard_truth

    try:
        r = dashboard_truth.revenue_reading(db)
    except Exception as exc:  # noqa: BLE001
        return _money(None, state="UNKNOWN", basis="unknown", sources=["ledger", "orders"],
                      why=f"revenue unreadable: {type(exc).__name__}")
    if r.get("state") != "MEASURED":
        return _money(None, state="UNMEASURED", basis="unknown",
                      sources=["ledger", "orders", "commerce.orders_ingest.source_state"],
                      why=r.get("why") or "order source not connected and read")
    return _money(r.get("value_cad"), state="MEASURED", basis="measured",
                  sources=["ledger (measured, reconciled)"],
                  why="sum of reconciled measured sales net of refunds")


def recorded_spend(db) -> dict:
    from .. import dashboard_truth

    try:
        r = dashboard_truth.spend_reading(db)
    except Exception as exc:  # noqa: BLE001
        return _money(None, state="UNKNOWN", basis="unknown", sources=["cost_entries"],
                      why=f"spend unreadable: {type(exc).__name__}")
    # Recorded spend is a sum of rows this system wrote; it is a real (recorded) amount but
    # not a reconciled all-in operating cost, and is labelled so.
    out = _money(r.get("total_recorded_cad"), state="RECORDED", basis="measured",
                 sources=["cost_entries", "ledger.fees_cad", "ledger.expense_cad"],
                 why="recorded spend only (not reconciled, not an all-in opex)")
    out["label"] = r.get("label")
    out["by_kind"] = r.get("cost_entries_by_kind")
    return out


def spend_limits(db) -> dict:
    from ...core.models import SpendLimit

    def read():
        with db.session() as s:
            rows = list(s.scalars(select(SpendLimit).order_by(SpendLimit.scope)))
            items = [{"scope": r.scope, "daily_cap_cad": r.daily_cap_cad,
                      "lifetime_cap_cad": r.lifetime_cap_cad,
                      "spent_today_cad": r.spent_today_cad,
                      "spent_lifetime_cad": r.spent_lifetime_cad, "paused": bool(r.paused),
                      "source": f"spend_limits:{r.id}"} for r in rows]
        if not items:
            return envelope("UNKNOWN", [], ["spend_limits"], basis="unknown",
                            reason="no spend limit configured (all spend is refused)",
                            provider="spend_limits")
        return envelope("OK", items, [i["source"] for i in items], provider="spend_limits",
                        any_paused=any(i["paused"] for i in items))

    return guard("spend_limits", read, sources=["spend_limits"])


# ---- agents -------------------------------------------------------------------------


def agents(db) -> dict:
    from ...core.models import Agent

    def read():
        with db.session() as s:
            rows = list(s.scalars(select(Agent).order_by(Agent.name)))
            items = [{"name": a.name, "enabled": bool(a.enabled),
                      "authority": getattr(a.authority, "value", a.authority),
                      "daily_cost_ceiling_cad": a.daily_cost_ceiling_cad,
                      "source": f"agents:{a.id}"} for a in rows]
        if not items:
            return envelope("UNKNOWN", [], ["agents"], basis="unknown",
                            reason="no agent registered", provider="agents")
        paused = [i["name"] for i in items if not i["enabled"]]
        return envelope("DEGRADED" if paused else "OK", items, ["agents"],
                        provider="agents", paused=paused,
                        reason=(f"paused: {paused}" if paused else None))

    return guard("agents", read, sources=["agents"])


# ---- learn / insights ------------------------------------------------------------


def _table_recent(db, model, name: str, *, order_col, limit: int = 10, fields=()) -> dict:
    def read():
        with db.session() as s:
            total = s.scalar(select(func.count()).select_from(model)) or 0
            rows = list(s.scalars(select(model).order_by(order_col.desc()).limit(limit)))
            items = [{**{f: (_iso(getattr(r, f)) if isinstance(getattr(r, f), datetime)
                             else getattr(r, f)) for f in fields},
                      "source": f"{name}:{r.id}"} for r in rows]
        if not total:
            return envelope("UNKNOWN", [], [name], basis="unknown",
                            reason=f"no {name} recorded", provider=name)
        return envelope("OK", items, [name], provider=name, total=int(total))

    return guard(name, read, sources=[name])


def improvements(db) -> dict:
    from ...core.models import Improvement

    return _table_recent(db, Improvement, "improvements", order_col=Improvement.id,
                         fields=("id", "at", "cell", "metric", "state", "hypothesis",
                                 "baseline_value", "result_value", "promoted_at",
                                 "reverted_at"))


def lessons(db) -> dict:
    from ...core.models import Lesson

    return _table_recent(db, Lesson, "lessons", order_col=Lesson.id,
                         fields=("id", "at", "origin_cell", "subject", "statement",
                                 "confidence", "evidence_ref"))


def experiments(db) -> dict:
    from ...core.models import Experiment

    return _table_recent(db, Experiment, "experiments", order_col=Experiment.id,
                         fields=("id", "name", "kind", "product_slug", "state",
                                 "hypothesis", "max_loss_cad"))


def now() -> str:
    return now_iso()


__all__ = ["incidents", "queue", "jobs_window", "audit_events", "owner_inbox",
           "owner_actions_summary", "products", "revenue", "recorded_spend", "spend_limits",
           "agents", "improvements", "lessons", "experiments", "row_dict", "unknown"]
