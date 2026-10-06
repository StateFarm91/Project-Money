"""Tab aggregators: each tab reads the department providers (tolerating absence) and the
production database directly. No canned data; UNKNOWN is never coerced to zero (F-898)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from . import approvals, emergency, notifications, providers, readers
from .models import SecurityEvent, ensure_tables, kv_get, kv_set
from .providers import envelope, guard, now_iso, unknown

HOME_SEEN_KEY = "home_last_seen"


def _tab(name: str, sections: dict, **extra) -> dict:
    return {"tab": name, "generated_at": now_iso(), "sections": sections, **extra}


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


# ---- money --------------------------------------------------------------------------


def money_section(db) -> dict:
    """The Accountant provider is primary; fallback readers only state what they measure."""
    acct = providers.call("accounting", db)
    rev = readers.revenue(db)
    spent = readers.recorded_spend(db)
    try:
        from .. import dashboard_truth

        src = dashboard_truth._order_source(db)
        source_health = {"order_source_measured": bool(src.get("measured")),
                         "last_read_at": src.get("last_read_at"),
                         "why": src.get("why") or "",
                         "warning": (None if src.get("measured") else
                                     "order/payment source is not connected-and-read: revenue,"
                                     " fees and profit are UNKNOWN, not CA$0.00")}
    except Exception as exc:  # noqa: BLE001
        source_health = {"order_source_measured": False,
                         "warning": f"source health unreadable: {type(exc).__name__}"}
    status = acct["status"]
    if status == "UNKNOWN" and rev["state"] == "MEASURED":
        status = "DEGRADED"
    return {"status": status, "accounting": acct, "revenue": rev,
            "profit": (acct.get("profit") if isinstance(acct.get("profit"), dict) else
                       {"value_cad": None, "state": "UNKNOWN", "basis": "unknown",
                        "display": "UNKNOWN",
                        "why": acct.get("reason") or "the accountant provider owns profit"}),
            "recorded_spend": spent, "source_health": source_health,
            "reason": acct.get("reason") if acct["status"] == "UNKNOWN" else None}


def money(db) -> dict:
    m = money_section(db)
    return _tab("MONEY", {"accounting": m["accounting"], "spend_limits": readers.spend_limits(db)},
                status=m["status"], revenue=m["revenue"], profit=m["profit"],
                recorded_spend=m["recorded_spend"], source_health=m["source_health"],
                reason=m["reason"])


def money_drill(db, metric: str) -> dict:
    metric = str(metric or "")[:80]
    if not metric:
        return unknown("metric required", "money.drill")
    if providers.available("accounting_drill"):
        out, why = providers.call_raw("accounting_drill", db, metric)
        if out is not None:
            return out if isinstance(out, dict) else {"metric": metric, "rows": out}
        return unknown(why or "drill failed", "finance.accounting.dashboard.drill")
    if metric == "revenue":
        rev = readers.revenue(db)
        if rev["state"] != "MEASURED":
            return unknown(f"revenue is {rev['state']}: {rev.get('why')}", "readers.revenue",
                           rev["sources"])
    if metric == "recorded_spend":
        from ...core.models import CostEntry

        def read():
            with db.session() as s:
                rows = list(s.scalars(select(CostEntry).order_by(CostEntry.id.desc())
                                      .limit(200)))
                items = [{**readers.row_dict(r), "source": f"cost_entries:{r.id}"}
                         for r in rows]
            return envelope("OK" if items else "UNKNOWN", items, ["cost_entries"],
                            provider="cost_entries", metric=metric,
                            reason=None if items else "no cost entry recorded")

        return guard("cost_entries", read, sources=["cost_entries"])
    return unknown("the accountant drill-through (lane E) is not built; no source rows to show",
                   "finance.accounting.dashboard.drill")


# ---- home / brief ---------------------------------------------------------------------


def _changes_since(db, since: datetime | None) -> dict:
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        basis = "no previous view recorded; showing the last 24 h"
    else:
        basis = "since your last view"
    events = readers.audit_events(db, since=since, limit=25)
    return envelope("OK", events, [e["source"] for e in events] or ["audit_log"],
                    provider="audit_log", since=since.isoformat(), basis_note=basis)


def home(db) -> dict:
    ensure_tables(db)
    with db.session() as s:
        seen = kv_get(s, HOME_SEEN_KEY, {}) or {}
    since = None
    if seen.get("at"):
        try:
            since = datetime.fromisoformat(seen["at"])
        except ValueError:
            since = None
    m = money_section(db)
    autonomy = providers.call("autonomy", db)
    store_f = providers.call("store_foundation", db)
    prods = readers.products(db)
    inc = readers.incidents(db, limit=10)
    box = approvals.inbox(db)
    jw = readers.jobs_window(db, 24)
    improve = providers.call("improvement", db)
    try:
        from ...core import phase as phase_mod

        ph = phase_mod.resolve(db)
        launch = envelope("OK" if ph["phase"] != "shadow" else "BLOCKED",
                          [{"phase": ph["phase"], "why": ph["why"]}],
                          ["audit_log (owner.phase.transition)", "env BRAMBLELOOP_PHASE"],
                          provider="core.phase.resolve",
                          reason=("SHADOW: nothing is published live" if ph["phase"] == "shadow"
                                  else None))
    except Exception as exc:  # noqa: BLE001
        launch = unknown(f"phase unreadable: {type(exc).__name__}", "core.phase.resolve")
    headline = {
        "revenue": m["revenue"], "profit": m["profit"],
        "store": {"products": len(prods["items"]) if prods["status"] == "OK" else None,
                  "certified": prods.get("certified"), "on_etsy": prods.get("on_etsy"),
                  "status": prods["status"], "reason": prods.get("reason")},
        "launch": {"phase": (launch["items"][0]["phase"] if launch["items"] else "UNKNOWN"),
                   "status": launch["status"]},
        "autonomy": {"status": autonomy["status"], "reason": autonomy.get("reason"),
                     "jobs_completed_24h": jw.get("completed") if jw["status"] == "OK" else None},
        "incidents_open": inc.get("open_total") if inc["status"] != "UNKNOWN" else None,
        "owner_decisions": box["open"],
    }
    opportunities = guard("opportunities", lambda: envelope(
        improve["status"] if improve["status"] != "UNKNOWN" else "OK",
        [i for i in improve.get("items", [])][:5] + readers.improvements(db).get("items", [])[:5],
        (improve.get("sources") or []) + ["improvements"], provider="learn+improvements"))
    return _tab("HOME", {
        "changes_since_last_view": _changes_since(db, since),
        "autonomy": autonomy, "store": store_f, "products": prods,
        "money": m["accounting"], "incidents": inc,
        "owner_actions": readers.owner_actions_summary(db),
        "work_24h": jw, "launch": launch, "opportunities": opportunities},
        headline=headline, last_seen_at=seen.get("at"))


def mark_seen(db) -> dict:
    ensure_tables(db)
    at = datetime.now(timezone.utc).isoformat()  # full precision: "since" must be exact
    with db.session() as s:
        kv_set(s, HOME_SEEN_KEY, {"at": at})
    return {"seen_at": at}


def morning_brief(db, hours: float = 12) -> dict:
    """F-896: what changed, completed, money spent, incidents, discoveries, queue, decisions."""
    from ...core.models import CostEntry, Incident, Job, JobStatus, Lesson

    hours = max(1.0, min(float(hours or 12), 72.0))
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    def spent():
        with db.session() as s:
            rows = list(s.execute(select(CostEntry.kind, func.sum(CostEntry.amount_cad),
                                         func.count()).where(CostEntry.at >= since)
                                  .group_by(CostEntry.kind)))
        items = [{"kind": k or "other", "amount_cad": round(float(v or 0), 4),
                  "entries": int(n)} for k, v, n in rows]
        total = round(sum(i["amount_cad"] for i in items), 2)
        return envelope("OK", items, ["cost_entries"], provider="cost_entries",
                        total={"value_cad": total, "state": "RECORDED", "basis": "measured",
                               "display": f"CA${total:,.2f} (recorded)"})

    def incidents_opened():
        with db.session() as s:
            rows = list(s.scalars(select(Incident).where(Incident.at >= since)
                                  .order_by(Incident.at.desc()).limit(25)))
            items = [{"id": r.id, "severity": r.severity, "summary": r.summary[:300],
                      "resolved": bool(r.resolved), "source": f"incidents:{r.id}"}
                     for r in rows]
        return envelope("OK", items, [i["source"] for i in items] or ["incidents"],
                        provider="incidents")

    def discoveries():
        with db.session() as s:
            rows = list(s.scalars(select(Lesson).where(Lesson.at >= since)
                                  .order_by(Lesson.id.desc()).limit(10)))
            items = [{"subject": r.subject, "statement": r.statement[:300],
                      "confidence": r.confidence, "source": f"lessons:{r.id}"} for r in rows]
        return envelope("OK", items, [i["source"] for i in items] or ["lessons"],
                        provider="lessons")

    def queued():
        with db.session() as s:
            n = s.scalar(select(func.count()).select_from(Job).where(
                Job.status == JobStatus.PENDING)) or 0
            types = list(s.execute(select(Job.job_type, func.count()).where(
                Job.status == JobStatus.PENDING).group_by(Job.job_type)
                .order_by(func.count().desc()).limit(10)))
        return envelope("OK", [{"job_type": t, "pending": int(c)} for t, c in types],
                        ["jobs"], provider="jobs", pending_total=int(n))

    box = approvals.inbox(db)
    autonomy = providers.call("autonomy", db)
    return _tab("MORNING_BRIEF", {
        "what_changed": envelope("OK", readers.audit_events(db, since=since, limit=30),
                                 ["audit_log"], provider="audit_log"),
        "completed": readers.jobs_window(db, hours),
        "money_spent": guard("money_spent", spent, sources=["cost_entries"]),
        "incidents": guard("incidents", incidents_opened, sources=["incidents"]),
        "discoveries": guard("discoveries", discoveries, sources=["lessons"]),
        "overnight_autonomy": autonomy,
        "queued_actions": guard("queued", queued, sources=["jobs"]),
        "decisions_needed": envelope("OK" if not box["cards"] else "BLOCKED",
                                     [{"card_id": c["card_id"], "title": c["title"]}
                                      for c in box["cards"]],
                                     box["sources"], provider="approvals.inbox",
                                     reason=(f"{len(box['cards'])} owner decisions open"
                                             if box["cards"] else None))},
        window_hours=hours, since=since.isoformat())


# ---- store / operations / autonomy / insights -----------------------------------------


def store(db) -> dict:
    return _tab("STORE", {"store_foundation": providers.call("store_foundation", db),
                          "seo": providers.call("seo", db),
                          "products": readers.products(db),
                          "publication_candidates": guard(
                              "publication_candidates", lambda: envelope(
                                  "OK", approvals._publication_cards(db),
                                  ["pattern_versions", "listings",
                                   "ops.publication_authority.evidence"],
                                  provider="approvals.publication_candidates"))})


def operations(db) -> dict:
    return _tab("OPERATIONS", {"slo": providers.call("slo", db),
                               "autonomy": providers.call("autonomy", db),
                               "queue": readers.queue(db),
                               "incidents": readers.incidents(db),
                               "agents": readers.agents(db)},
                emergency=guard("emergency", lambda: emergency.status(db)))


def operations_drill(db, kind: str, ident: str) -> dict:
    from ...core.models import Agent, AuditLog, Incident, Job

    models = {"job": Job, "incident": Incident, "audit": AuditLog, "agent": Agent}
    model = models.get(kind)
    if model is None:
        return unknown(f"kind must be one of {sorted(models)}", "operations.drill")
    with db.session() as s:
        if kind == "agent" and not str(ident).isdigit():
            row = s.scalar(select(Agent).where(Agent.name == str(ident)))
        else:
            try:
                row = s.get(model, int(ident))
            except (TypeError, ValueError):
                row = None
        if row is None:
            return unknown(f"no {kind} {ident!r}", "operations.drill")
        data = readers.row_dict(row)
        data.pop("seal", None)
        if isinstance(data.get("detail"), dict):
            data["detail"] = {k: v for k, v in data["detail"].items() if k != "seal"}
        table = model.__tablename__
        q = select(AuditLog).order_by(AuditLog.id.desc()).limit(20)
        if kind == "job":
            q = q.where(AuditLog.job_id == row.id)
            agent = row.agent
        elif kind == "incident":
            q = q.where(AuditLog.artifact.ilike(f"%{(row.product_slug or row.signature)[:60]}%"))
            agent = (row.detail or {}).get("agent") if isinstance(row.detail, dict) else None
        elif kind == "agent":
            q = q.where(AuditLog.actor == row.name)
            agent = row.name
        else:
            q = q.where(AuditLog.artifact == row.artifact) if row.artifact else q.where(
                AuditLog.id == row.id)
            agent = row.actor
        related = [{"id": a.id, "at": readers._iso(a.at), "actor": a.actor,
                    "action": a.action, "artifact": a.artifact,
                    "source": f"audit_log:{a.id}"} for a in s.scalars(q)]
    return envelope("OK", [data], [f"{table}:{data.get('id', ident)}"],
                    provider="operations.drill", kind=kind, responsible_agent=agent,
                    audit_history=related, confidence="recorded row (measured)")


def autonomy(db) -> dict:
    from ...core.models import AuditLog

    jw = readers.jobs_window(db, 24)

    def owner_gap():
        with db.session() as s:
            last = s.scalar(select(func.max(AuditLog.at)).where(
                AuditLog.actor.like("owner%")))
        if last is None:
            return unknown("no owner action is recorded", "audit_log (actor owner*)")
        hours = (datetime.now(timezone.utc) - _aware(last)).total_seconds() / 3600
        return envelope("OK", [{"hours": round(hours, 1), "last_owner_action_at":
                                _aware(last).isoformat()}], ["audit_log"],
                        provider="audit_log (actor owner*)",
                        note=("hours since the last recorded owner action; development-chat "
                              "prompts are not recorded in production state"))

    return _tab("AUTONOMY", {"autonomy": providers.call("autonomy", db),
                             "improvement": providers.call("improvement", db),
                             "jobs_24h": jw,
                             "hours_since_owner_action": guard("owner_gap", owner_gap),
                             "improvements": readers.improvements(db),
                             "lessons": readers.lessons(db),
                             "experiments": readers.experiments(db)},
                last_useful_action=jw.get("last_useful_action"))


def insights(db) -> dict:
    return _tab("INSIGHTS", {"seo": providers.call("seo", db),
                             "ads": providers.call("ads", db),
                             "experiments": readers.experiments(db),
                             "lessons": readers.lessons(db),
                             "improvements": readers.improvements(db)})


def timeline(db, limit: int = 50) -> dict:
    limit = max(1, min(int(limit or 50), 200))
    events = []
    sources = ["audit_log"]
    a_events, why = providers.call_raw("timeline", db, limit=limit)
    a_status = "UNKNOWN"
    if isinstance(a_events, dict):
        a_status = a_events.get("status", "UNKNOWN")
        a_events = a_events.get("items")
    if isinstance(a_events, list):
        a_status = "OK" if a_status == "UNKNOWN" else a_status
        for e in a_events:
            if isinstance(e, dict):
                events.append({**e, "origin": "autonomy.status.timeline"})
        sources.append("brambleloop.autonomy.status.timeline")
    for e in readers.audit_events(db, limit=limit):
        events.append({**e, "origin": "audit_log"})
    events.sort(key=lambda e: str(e.get("at") or ""), reverse=True)
    return _tab("TIMELINE", {}, events=events[:limit], sources=sources,
                autonomy_timeline={"status": a_status,
                                   "reason": why if a_events is None else None})


def notifications_tab(db) -> dict:
    return _tab("NOTIFICATIONS", {}, **notifications.listing(db))


def account(db, current_session: str) -> dict:
    from ...core.models import OAuthCredential
    from ...gateway.model_gateway import available_providers
    from . import auth

    ensure_tables(db)

    def services():
        with db.session() as s:
            rows = list(s.scalars(select(OAuthCredential)))
            items = [{"provider": r.provider, "scopes": (r.scopes or "").split(),
                      "token_fingerprint": r.token_fingerprint,
                      "obtained_at": readers._iso(r.obtained_at),
                      "updated_at": readers._iso(r.updated_at),
                      "source": f"oauth_credentials:{r.provider}"} for r in rows]
        if not items:
            return unknown("no connected OAuth service is recorded", "oauth_credentials")
        return envelope("OK", items, [i["source"] for i in items], provider="oauth_credentials")

    with db.session() as s:
        events = [{"id": e.id, "at": readers._iso(e.at), "kind": e.kind,
                   "outcome": e.outcome, "method": e.method, "route": e.route,
                   "reason": e.reason, "session_id": e.session_public_id or None}
                  for e in s.scalars(select(SecurityEvent).order_by(SecurityEvent.id.desc())
                                     .limit(50))]
        refused_24h = s.scalar(select(func.count()).select_from(SecurityEvent).where(
            SecurityEvent.outcome == "refused",
            SecurityEvent.at >= datetime.now(timezone.utc) - timedelta(hours=24))) or 0
    emerg = guard("emergency", lambda: emergency.status(db))
    return _tab("ACCOUNT", {
        "connected_services": guard("services", services, sources=["oauth_credentials"]),
        "budgets": readers.spend_limits(db)},
        owner={"principal": "owner (passphrase{})".format(
            " + TOTP" if auth.totp_required() else ""),
            "login_configured": auth.login_configured(),
            "totp_required": auth.totp_required(),
            "stepup_window_seconds": int(auth.STEPUP_WINDOW.total_seconds())},
        sessions=auth.list_sessions(db, current_session),
        security_events=events, refused_attempts_24h=int(refused_24h),
        model_providers={"configured": available_providers(),
                         "note": "a provider is listed only when its credential is configured"},
        authorities={"phase": emerg.get("phase") if isinstance(emerg, dict) else None,
                     "live_grants": ((emerg.get("publishing") or {}).get("live_grants")
                                     if isinstance(emerg, dict) else None)},
        notification_policy=notifications.get_policy(db),
        emergency=emerg)
