"""Command Center executive, agents and autonomy-health blocks (W4-CCFM2).

Final Master post-launch rows:
* F-661 Executive Command Center -- today / month / 90-day revenue, profit, conversion, live
  listings and customer risk, each with its basis. Revenue is summed only from measured,
  reconciled, countable sale rows (the A3-09 predicate `dashboard_truth._reconciled_measured`)
  and only while the order source is measured; otherwise every window is UNKNOWN, never 0.
* F-668 Agents Workspace -- one row per agent: department, state, current job, completed and
  failed work in 24 h, spend today against its daily ceiling (`spend_report.per_agent_today`).
* F-729 Autonomy Health -- hours with completed work in the last 24 h, the oldest ready
  (pending) job, owner-blocked work, and agent states (active / watching / blocked / unknown).

Read-only, durable tables only; no new source of truth. Every reader is guarded: a failure is
UNKNOWN with its reason.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from .providers import envelope, guard

WINDOWS = (("today", None), ("month", None), ("90d", 90))
CUSTOMER_RISK_SEVERITIES = ("P0", "P1")


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _window_start(key: str, now: datetime) -> datetime:
    if key == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if key == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return now - timedelta(days=90)


# ---- F-661 -----------------------------------------------------------------------------------

def _sales_with_dates(db) -> list[dict]:
    """The A3-09 sale rows (as `dashboard_truth._sale_rows`), with each row's date."""
    from ...commerce import orders_ingest
    from ...core.models import LedgerEntry, Order

    with db.session() as s:
        held = orders_ingest.held_refs(s)
        standing = {o.external_ref: orders_ingest.standing(o, held)
                    for o in s.scalars(select(Order))}
        rows = [{"at": _aware(at), "gross": float(g or 0), "refunds": float(r or 0),
                 "ref": (ref or "").strip(), "basis": b or "unknown",
                 "recon": rs or "unreconciled"}
                for at, g, r, ref, b, rs in s.execute(select(
                    LedgerEntry.at, LedgerEntry.gross_cad, LedgerEntry.refunds_cad,
                    LedgerEntry.evidence_ref, LedgerEntry.basis,
                    LedgerEntry.reconciliation_state).where(LedgerEntry.gross_cad > 0))]
    for row in rows:
        row["standing"] = (orders_ingest.STANDING_HELD if row["ref"] in held
                           else standing.get(row["ref"], orders_ingest.STANDING_COUNTABLE))
    return rows


def revenue_windows(db, now: datetime | None = None) -> dict:
    from .. import dashboard_truth

    now = now or datetime.now(timezone.utc)
    src = dashboard_truth._order_source(db)
    if not src.get("measured"):
        why = src.get("why") or "order source not connected and read"
        return {k: {"value_cad": None, "state": "UNMEASURED", "basis": "unknown", "why": why}
                for k, _ in WINDOWS}
    rows = [r for r in _sales_with_dates(db) if dashboard_truth._reconciled_measured(r)]
    out = {}
    for k, _ in WINDOWS:
        start = _window_start(k, now)
        v = round(sum(r["gross"] - r["refunds"] for r in rows
                      if r["at"] is not None and r["at"] >= start), 2)
        out[k] = {"value_cad": v, "state": "MEASURED", "basis": "measured",
                  "since": start.isoformat(),
                  "why": "reconciled measured sales net of refunds (A3-09)"}
    return out


def executive(db, now: datetime | None = None) -> dict:
    """F-661: the owner's executive block."""
    from ...core.models import Incident, Listing, SupportCase
    from . import tabs

    now = now or datetime.now(timezone.utc)

    def read():
        rev = revenue_windows(db, now)
        money = tabs.money_section(db)
        with db.session() as s:
            active = int(s.scalar(select(func.count()).select_from(Listing).where(
                Listing.etsy_listing_id != "", Listing.state == "active")) or 0)
            drafted = int(s.scalar(select(func.count()).select_from(Listing)) or 0)
            risk_incidents = int(s.scalar(select(func.count()).select_from(Incident).where(
                Incident.resolved == False,  # noqa: E712
                Incident.severity.in_(CUSTOMER_RISK_SEVERITIES))) or 0)
            escalated_waiting = int(s.scalar(select(func.count()).select_from(SupportCase).where(
                SupportCase.escalated == True, SupportCase.sent == False)) or 0)  # noqa: E712
        # Flat rows (the CC's generic row shows scalars and money values, not nested objects).
        items = [{"metric": f"revenue_{k}", "label": f"Revenue ({k})", "revenue": v,
                  "why": v.get("why")} for k, v in rev.items()]
        items += [
            {"metric": "profit_all_time", "label": "Profit (all time)", "profit": money["profit"]},
            {"metric": "conversion", "label": "Conversion (visits to orders)", "value": None,
             "state": "UNKNOWN",
             "why": "no visits reading: Etsy shop stats are not read by this system"},
            {"metric": "live_listings", "label": "Live listings (recorded active, with an Etsy id)",
             "value": active, "drafted": drafted, "state": "RECORDED",
             "why": "rows this system recorded; the live shop itself is not read here"},
            {"metric": "customer_risk", "label": "Customer risk", "value":
             risk_incidents + escalated_waiting, "open_p0_p1_incidents": risk_incidents,
             "escalated_support_awaiting_reply": escalated_waiting, "state": "MEASURED",
             "why": "open P0/P1 incidents plus escalated support cases awaiting a reply"},
        ]
        items += _executive_operations(db, now)
        measured = any(v.get("state") == "MEASURED" for v in rev.values())
        return envelope("OK" if measured else "DEGRADED", items,
                        ["ledger", "orders", "listings", "incidents", "support_cases",
                         "commerce.orders_ingest.source_state"],
                        provider="executive.executive", as_of=now.isoformat(),
                        reason=None if measured else
                        "revenue windows are UNMEASURED until the order source is read")

    return guard("executive", read, sources=["ledger", "listings", "incidents"])


def _executive_operations(db, now: datetime) -> list[dict]:
    """W4-FMBATCH1 (F-661): the objective, incidents, active departments, completed work and
    owner decisions -- the parts of the executive block CLOSE5 found missing. Each item is a
    reading or UNKNOWN with why; none is defaulted."""
    from ...core.models import AuditLog, Incident, Job, JobStatus
    from . import readers

    since = now - timedelta(hours=24)
    out: list[dict] = []
    with db.session() as s:
        plan = s.scalar(select(AuditLog).where(AuditLog.action == "plan.strategy_reviewed")
                        .order_by(AuditLog.id.desc()).limit(1))
        open_incidents = int(s.scalar(select(func.count()).select_from(Incident).where(
            Incident.resolved == False)) or 0)  # noqa: E712
        done = list(s.execute(select(Job.job_type, Job.inputs).where(
            Job.status == JobStatus.DONE, Job.finished_at >= since)).all())
    if plan is None:
        out.append({"metric": "objective", "label": "Objective (today / month / 90 days)",
                    "value": None, "state": "UNKNOWN",
                    "why": "no plan.strategy review has been recorded"})
    else:
        traj = (plan.detail or {}).get("trajectory") or {}
        out.append({"metric": "objective", "label": "Objective (today / month / 90 days)",
                    "value": traj.get("target_cad") or traj.get("target"),
                    "trajectory": traj, "state": "RECORDED",
                    "as_of": (plan.detail or {}).get("as_of"),
                    "why": ("the monthly strategy review's trajectory; a refusal to forecast "
                            "is shown as such" if not traj.get("is_forecast") else None)})
    out.append({"metric": "open_incidents", "label": "Open incidents", "value": open_incidents,
                "state": "MEASURED"})
    try:
        from ...autonomy import kpis

        depts = {kpis.job_department(jt, inp) for jt, inp in done} - {None}
        out.append({"metric": "active_departments", "label": "Departments with completed work (24 h)",
                    "value": len(depts), "departments": sorted(depts), "state": "MEASURED"})
    except Exception as exc:  # noqa: BLE001
        out.append({"metric": "active_departments", "value": None, "state": "UNKNOWN",
                    "why": f"department mapping unreadable: {type(exc).__name__}"})
    out.append({"metric": "completed_work_24h", "label": "Completed jobs (24 h)",
                "value": len(done), "state": "MEASURED"})
    try:
        own = readers.owner_actions_summary(db)
        n = own.get("open_actions") if isinstance(own, dict) else None
    except Exception:  # noqa: BLE001
        n = None
    out.append({"metric": "owner_decisions", "label": "Owner decisions waiting", "value": n,
                "state": "MEASURED" if n is not None else "UNKNOWN",
                "why": None if n is not None else "owner inbox unreadable"})
    return out


#: W4-FMBATCH1 (F-668): which improvement cells' lessons count as a department's learning.
#: A stated mapping (charter key -> improve.cells keys); a department with none reads UNKNOWN.
DEPARTMENT_CELLS: dict[str, tuple[str, ...]] = {
    "intelligence": ("market_radar",), "product_design": ("product_creativity",
                                                         "pattern_engineering"),
    "product_truth": ("quality",), "visual": ("creative_assets",),
    "store_commerce": ("seo_search", "pricing", "portfolio"),
    "support": ("customer_experience",), "finance": ("finance",), "growth": ("growth",),
    "learn": ("learn",), "platform": ("runtime",)}


# ---- F-668 -----------------------------------------------------------------------------------

def agents_workspace(db, now: datetime | None = None) -> dict:
    from ...core.models import Agent, Job, JobStatus
    from ...finance import spend_report

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    def read():
        try:
            from ...autonomy import charters

            dept_of_agent = {a: c.key for c in charters.CHARTERS for a in c.agents}
        except Exception:  # noqa: BLE001
            dept_of_agent = {}
        with db.session() as s:
            agents = list(s.scalars(select(Agent).order_by(Agent.name)))
            names = [a.name for a in agents]
            running = {}
            for jid, agent, jt, started in s.execute(select(
                    Job.id, Job.agent, Job.job_type, Job.started_at).where(
                    Job.status == JobStatus.RUNNING).order_by(Job.id.desc())):
                running.setdefault(agent, {"job_id": jid, "job_type": jt,
                                           "started_at": _aware(started).isoformat()
                                           if started else None})
            done = dict(s.execute(select(Job.agent, func.count()).where(
                Job.status == JobStatus.DONE, Job.finished_at >= since)
                .group_by(Job.agent)).all())
            failed = dict(s.execute(select(Job.agent, func.count()).where(
                Job.status.in_([JobStatus.FAILED, JobStatus.DEAD]), Job.finished_at >= since)
                .group_by(Job.agent)).all())
            ever = {a for a in s.scalars(select(Job.agent).distinct()) if a}
            # Heartbeat: the newest start or finish this agent recorded.
            beats = {}
            for agent, st, fin in s.execute(select(Job.agent, func.max(Job.started_at),
                                                   func.max(Job.finished_at))
                                            .group_by(Job.agent)).all():
                cand = [_aware(x) for x in (st, fin) if x is not None]
                beats[agent] = max(cand).isoformat() if cand else None
            from ...core.models import Lesson

            lessons_by_cell = dict(s.execute(select(Lesson.origin_cell, func.count()).where(
                Lesson.at >= now - timedelta(days=30)).group_by(Lesson.origin_cell)).all()) \
                if hasattr(Lesson, "at") else {}
        try:
            from ...autonomy import charters as _ch

            lead_of = {c.key: c.agents[0] for c in _ch.CHARTERS if c.agents}
        except Exception:  # noqa: BLE001
            lead_of = {}
        spend = spend_report.per_agent_today(db, now=now)
        spent = {r["agent"]: r for r in spend.get("agents") or []}
        items = []
        for a in agents:
            cur = running.get(a.name)
            state = ("active" if cur else
                     "disabled" if getattr(a, "enabled", True) is False else
                     "idle" if a.name in ever else "UNKNOWN")
            sp = spent.get(a.name) or {}
            items.append({
                "agent": a.name, "department": dept_of_agent.get(a.name),
                "state": state, "current_job": cur,
                "completed_24h": int(done.get(a.name, 0)),
                "failed_24h": int(failed.get(a.name, 0)),
                "spent_today_cad": sp.get("spent_today_cad"),
                "daily_ceiling_cad": sp.get("daily_ceiling_cad"),
                "over_ceiling": any(o.get("agent") == a.name for o in spend.get("over") or []),
                # W4-FMBATCH1 (F-668): role in the org chart, heartbeat and learning.
                "role": ("director" if dept_of_agent.get(a.name)
                         and lead_of.get(dept_of_agent[a.name]) == a.name else
                         "worker" if dept_of_agent.get(a.name) else "UNKNOWN"),
                "heartbeat": beats.get(a.name),
                "department_lessons_30d": (
                    sum(int(lessons_by_cell.get(c, 0)) for c in
                        DEPARTMENT_CELLS[dept_of_agent[a.name]])
                    if dept_of_agent.get(a.name) in DEPARTMENT_CELLS else None),
                "why": (None if state != "UNKNOWN" else
                        "no job has ever been recorded for this agent here"),
                "source": f"agents:{a.name}"})
        if not names:
            return envelope("UNKNOWN", [], ["agents"], basis="unknown",
                            reason="no agent is registered", provider="executive.agents")
        unregistered = spend.get("spenders_with_no_agent_row") or []
        org: dict[str, dict] = {}
        for it in items:
            d = it["department"] or "unassigned"
            node = org.setdefault(d, {"director": None, "workers": []})
            if it["role"] == "director":
                node["director"] = {"agent": it["agent"], "state": it["state"]}
            else:
                node["workers"].append({"agent": it["agent"], "state": it["state"]})
        return envelope("DEGRADED" if any(i["over_ceiling"] for i in items) else "OK", items,
                        ["agents", "jobs", "cost_entries (spend_report.per_agent_today)"],
                        provider="executive.agents_workspace", as_of=now.isoformat(),
                        spenders_with_no_agent_row=unregistered, day=spend.get("day"),
                        org_chart=org,
                        org_basis=("director = the first agent its charter lists "
                                   "(autonomy.charters); learning = lessons in 30 days from "
                                   "the department's improvement cells (DEPARTMENT_CELLS)"),
                        note="completed/failed are finished jobs in the last 24 h; spend is "
                             "recorded today (UTC) against the agent's daily ceiling")

    return guard("agents_workspace", read, sources=["agents", "jobs", "cost_entries"])


# ---- F-729 -----------------------------------------------------------------------------------

def autonomy_health(db, *, auto: dict | None = None, owner: dict | None = None,
                    now: datetime | None = None) -> dict:
    from ...core.models import Job, JobStatus
    from . import providers, readers

    now = now or datetime.now(timezone.utc)

    def read():
        since = now - timedelta(hours=24)
        with db.session() as s:
            finished = [_aware(f) for f in s.scalars(select(Job.finished_at).where(
                Job.status == JobStatus.DONE, Job.finished_at >= since))]
            ready = (Job.status == JobStatus.PENDING, Job.run_after <= now)
            oldest = s.scalar(select(func.min(Job.created_at)).where(*ready))
            pending = int(s.scalar(select(func.count()).select_from(Job).where(*ready)) or 0)
            any_job = s.scalar(select(func.count()).select_from(Job)) or 0
        hours = sorted({f.replace(minute=0, second=0, microsecond=0)
                        for f in finished if f is not None})
        oldest = _aware(oldest)
        ag = auto if auto is not None else providers.call("agents", db)
        states: dict[str, int] | None = None
        if isinstance(ag, dict) and isinstance(ag.get("items"), list) and ag["items"]:
            states = {"active": 0, "watching": 0, "blocked": 0, "UNKNOWN": 0}
            for it in ag["items"]:
                st = str((it or {}).get("state") or "UNKNOWN").lower()
                if st == "active":
                    states["active"] += 1
                elif st == "sleeping" and (it or {}).get("next_wake"):
                    states["watching"] += 1    # asleep with a scheduled wake: watching
                elif st == "blocked":
                    states["blocked"] += 1
                else:
                    states["UNKNOWN"] += 1
        own = owner if owner is not None else readers.owner_actions_summary(db)
        owner_open = own.get("open_actions") if isinstance(own, dict) else None
        items = [
            {"metric": "hours_with_completed_work_24h", "value": len(hours) if any_job else None,
             "of": 24, "why": None if any_job else "no job has ever been recorded"},
            {"metric": "oldest_ready_work_seconds",
             "value": (round((now - oldest).total_seconds()) if oldest else
                       (0 if pending == 0 and any_job else None)),
             "ready_pending": pending if any_job else None,
             "why": ("no ready job is waiting" if pending == 0 and any_job else None)},
            {"metric": "owner_blocked_decisions", "value": owner_open,
             "why": None if owner_open is not None else "owner inbox unreadable"},
            {"metric": "agent_states", "active": (states or {}).get("active"),
             "watching": (states or {}).get("watching"), "blocked": (states or {}).get("blocked"),
             "unknown": (states or {}).get("UNKNOWN"),
             "why": None if states is not None else
             "the autonomy agents provider reported no agents"},
        ]
        items += _autonomy_extra(db, now)
        return envelope("OK" if any_job else "UNKNOWN", items,
                        ["jobs", "build2.executor.approval_inbox", "autonomy agents"],
                        basis="measured" if any_job else "unknown",
                        provider="executive.autonomy_health", as_of=now.isoformat(),
                        reason=None if any_job else "no job has ever been recorded")

    return guard("autonomy_health", read, sources=["jobs"])


def _autonomy_extra(db, now: datetime) -> list[dict]:
    """W4-FMBATCH1 (F-729): restarts recovered, experiments, improvements promoted/reverted and
    unintentionally idle departments -- the parts CLOSE5 found missing."""
    from ...core.models import Improvement, Job, JobStatus, RegisteredExperiment

    since = now - timedelta(hours=24)
    week = now - timedelta(days=7)
    with db.session() as s:
        recovered = list(s.execute(select(Job.job_type).where(
            Job.status == JobStatus.DONE, Job.finished_at >= since, Job.attempts > 1)).all())
        exp_states = dict(s.execute(select(RegisteredExperiment.state, func.count())
                                    .group_by(RegisteredExperiment.state)).all())
        promoted = int(s.scalar(select(func.count()).select_from(Improvement).where(
            Improvement.promoted_at >= week)) or 0)
        reverted = int(s.scalar(select(func.count()).select_from(Improvement).where(
            Improvement.reverted_at >= week)) or 0)
        ready = list(s.execute(select(Job.job_type, Job.inputs).where(
            Job.status == JobStatus.PENDING, Job.run_after <= now)).all())
        done = list(s.execute(select(Job.job_type, Job.inputs).where(
            Job.status == JobStatus.DONE, Job.finished_at >= since)).all())
    out = [
        {"metric": "restarts_recovered_24h", "value": len(recovered),
         "job_types": sorted({r[0] for r in recovered})[:20],
         "why": "jobs that completed on a second or later attempt (retried or reclaimed)"},
        {"metric": "experiments", "by_state": {str(k): int(v) for k, v in exp_states.items()},
         "value": sum(int(v) for v in exp_states.values())},
        {"metric": "improvements_7d", "promoted": promoted, "reverted": reverted},
    ]
    try:
        from ...autonomy import kpis

        waiting = {kpis.job_department(jt, i) for jt, i in ready} - {None}
        working = {kpis.job_department(jt, i) for jt, i in done} - {None}
        idle = sorted(waiting - working)
        out.append({"metric": "unintentionally_idle_departments", "value": len(idle),
                    "departments": idle,
                    "why": ("ready work is waiting and the department completed nothing in "
                            "24 h" if idle else "every department with ready work completed "
                            "something in 24 h")})
    except Exception as exc:  # noqa: BLE001
        out.append({"metric": "unintentionally_idle_departments", "value": None,
                    "why": f"department mapping unreadable: {type(exc).__name__}"})
    return out


def kpi_trend(db, *, days: int = 7, now: datetime | None = None) -> dict:
    """W4-FMBATCH1 (F-621): each department's charter KPIs per UTC day -- useful completions
    (distinct non-noop results) and defect dead letters -- read in one pass over job rows with
    the same rules `autonomy.kpis.compute` applies to its 24 h window."""
    from ...core.models import Job, JobStatus
    from ...queue.durable import DEFECT, classify_dead_letter
    from ...autonomy import kpis

    now = now or datetime.now(timezone.utc)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    labels = [(start + timedelta(days=i)).date().isoformat() for i in range(days)]
    with db.session() as s:
        rows = list(s.execute(select(Job.job_type, Job.inputs, Job.outputs, Job.status,
                                     Job.last_error, Job.finished_at)
                              .where(Job.finished_at >= start)).all())
    if not rows:
        return {"days": labels, "by_department": {}, "basis": "unknown",
                "why": "no job finished in the window"}
    useful: dict[str, list[set]] = {}
    defects: dict[str, list[int]] = {}
    for jt, inp, outp, status, err, fin in rows:
        d = kpis.job_department(jt, inp)
        if d is None or jt in kpis.SELF_MEASUREMENT_TYPES:
            continue
        i = (_aware(fin).date() - start.date()).days
        if not 0 <= i < days:
            continue
        useful.setdefault(d, [set() for _ in labels])
        defects.setdefault(d, [0] * days)
        st = getattr(status, "value", status)
        if st == "done" and not kpis.did_no_work(outp, jt):
            useful[d][i].add((jt, kpis.fingerprint(outp)))
        elif st == "dead" and classify_dead_letter(jt, err or "") == DEFECT:
            defects[d][i] += 1
    return {"days": labels, "basis": "measured", "source": "jobs (autonomy.kpis rules)",
            "by_department": {d: {"useful_completions": [len(x) for x in useful[d]],
                                  "defect_dead_letters": defects[d]} for d in useful}}
