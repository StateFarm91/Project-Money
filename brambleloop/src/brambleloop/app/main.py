"""Admin dashboard + API (Master Plan section 13).

Deliberately server-rendered and dependency-light: this has to stay up unattended, and a
build pipeline that can rot is a liability rather than a feature.

The dashboard's job is to answer, at a glance, the questions an absent owner actually has:
what is the system doing, what has it refused to do, what is stuck, what has it spent, and is
anything waiting on me.
"""
from __future__ import annotations

import os
from datetime import timedelta

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import func, select

from ..agents.registry import Registry
from ..core.db import Database
from ..core.models import (
    Agent, AuditLog, CostEntry, Incident, Job, JobStatus, LedgerEntry, OwnerAction,
    PatternVersion, Product, SpendLimit, utcnow,
)
from ..queue.durable import JobQueue
from ..runtime import pipeline  # noqa: F401  -- registers job handlers
from ..runtime.worker import Scheduler

APP_VERSION = "0.1.0"

db = Database()
app = FastAPI(title="Brambleloop Studio OS", version=APP_VERSION)


@app.on_event("startup")
def _startup() -> None:
    db.create_all()
    Registry(db).seed_defaults()


# ---- health ---------------------------------------------------------------


@app.get("/health")
def health() -> JSONResponse:
    """Liveness + a real readiness signal: can we actually reach the database?"""
    try:
        with db.session() as s:
            s.execute(select(func.count()).select_from(Job))
        healthy = True
        detail = "ok"
    except Exception as e:  # noqa: BLE001
        healthy = False
        detail = f"{type(e).__name__}: {e}"
    return JSONResponse(
        {"status": "ok" if healthy else "degraded", "version": APP_VERSION, "db": detail},
        status_code=200 if healthy else 503,
    )


# ---- api ------------------------------------------------------------------


@app.get("/api/status")
def api_status() -> dict:
    q = JobQueue(db)
    with db.session() as s:
        products = s.scalar(select(func.count()).select_from(Product)) or 0
        certified = s.scalar(
            select(func.count()).select_from(PatternVersion).where(PatternVersion.certified)
        ) or 0
        incidents = s.scalar(
            select(func.count()).select_from(Incident).where(Incident.resolved == False)  # noqa: E712
        ) or 0
        opex = s.scalar(select(func.sum(CostEntry.amount_cad))) or 0.0
        revenue = s.scalar(select(func.sum(LedgerEntry.gross_cad))) or 0.0
        owner_open = s.scalar(
            select(func.count()).select_from(OwnerAction).where(OwnerAction.done == False)  # noqa: E712
        ) or 0
    return {
        "version": APP_VERSION,
        "queue": q.counts(),
        "dead_letters": len(q.dead_letters()),
        "products": products,
        "certified_versions": certified,
        "open_incidents": incidents,
        "agent_opex_cad": round(float(opex), 4),
        "revenue_cad": round(float(revenue), 2),
        "owner_actions_open": owner_open,
    }


@app.post("/api/scheduler/tick")
def api_tick() -> dict:
    """Cron target. Idempotent per cadence window, so calling it often is harmless."""
    return {"enqueued": Scheduler(db).tick()}


@app.get("/api/jobs")
def api_jobs(limit: int = 50) -> dict:
    with db.session() as s:
        rows = list(s.scalars(select(Job).order_by(Job.id.desc()).limit(limit)))
        return {"jobs": [
            {"id": j.id, "agent": j.agent, "type": j.job_type, "status": j.status.value,
             "attempts": j.attempts, "error": (j.last_error or "")[:200]}
            for j in rows
        ]}


@app.get("/api/owner-actions")
def api_owner_actions() -> dict:
    with db.session() as s:
        rows = list(s.scalars(
            select(OwnerAction).where(OwnerAction.done == False)  # noqa: E712
        ))
        return {"actions": [
            {"id": a.id, "action": a.action, "reason": a.reason,
             "max_cost_cad": a.max_cost_cad, "minutes": a.minutes,
             "consequence_of_delay": a.consequence_of_delay, "blocks": a.blocks}
            for a in rows
        ]}


# ---- dashboard ------------------------------------------------------------

_CSS = """
:root{--ink:#1A2B3C;--pine:#244A3A;--cream:#FAF6EB;--gold:#C49545;--wine:#6E1F2A;
--muted:#6b7280;--line:#e5e0d3}
*{box-sizing:border-box}body{margin:0;background:var(--cream);color:var(--ink);
font:15px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}
header{background:var(--pine);color:var(--cream);padding:18px 24px}
h1{margin:0;font-size:20px;letter-spacing:.02em}
.sub{opacity:.8;font-size:13px;margin-top:2px}
main{max-width:1100px;margin:0 auto;padding:24px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;
margin-bottom:24px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px}
.card b{display:block;font-size:22px;color:var(--pine)}
.card span{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
h2{font-size:15px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);
margin:24px 0 8px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);
border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);font-size:13px}
th{background:#f7f4ea;font-weight:600;text-transform:uppercase;font-size:11px;
letter-spacing:.05em;color:var(--muted)}
tr:last-child td{border-bottom:none}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:600}
.done{background:#e6f2ec;color:var(--pine)}.dead{background:#fae8ea;color:var(--wine)}
.running{background:#fdf3e2;color:var(--gold)}.pending{background:#eef0f2;color:var(--muted)}
.failed{background:#fdf3e2;color:#9a6b1f}
.empty{color:var(--muted);font-style:italic;padding:12px}
.owner{border-left:4px solid var(--gold);background:#fffaf0}
"""


def _pill(status: str) -> str:
    cls = {"done": "done", "dead": "dead", "running": "running",
           "failed": "failed"}.get(status, "pending")
    return f'<span class="pill {cls}">{status}</span>'


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    st = api_status()
    q = JobQueue(db)

    with db.session() as s:
        jobs = list(s.scalars(select(Job).order_by(Job.id.desc()).limit(15)))
        audits = list(s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(15)))
        incidents = list(s.scalars(
            select(Incident).where(Incident.resolved == False)))  # noqa: E712
        owner = list(s.scalars(
            select(OwnerAction).where(OwnerAction.done == False)))  # noqa: E712
        products = list(s.scalars(select(Product).order_by(Product.id.desc()).limit(10)))
        limits = list(s.scalars(select(SpendLimit)))
        agents = list(s.scalars(select(Agent).order_by(Agent.name)))

    def rows(items, cols, empty):
        if not items:
            return f'<div class="empty">{empty}</div>'
        head = "".join(f"<th>{c}</th>" for c in cols[0])
        body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in items)
        return f"<table><tr>{head}</tr>{body}</table>"

    owner_html = ""
    if owner:
        items = [(a.action, f"CA${a.max_cost_cad:.2f}", f"{a.minutes} min",
                  a.consequence_of_delay) for a in owner]
        owner_html = "<h2>Owner action required</h2>" + rows(
            items, [["Action", "Max cost", "Time", "Consequence of delay"]], "")

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Brambleloop Studio OS</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>{_CSS}</style></head><body>
<header><h1>BRAMBLELOOP STUDIO</h1>
<div class="sub">Autonomous crochet commerce OS &middot; v{APP_VERSION} &middot; {utcnow():%Y-%m-%d %H:%M} UTC</div>
</header><main>
<div class="grid">
  <div class="card"><span>Queue pending</span><b>{st['queue'].get('pending',0)}</b></div>
  <div class="card"><span>Running</span><b>{st['queue'].get('running',0)}</b></div>
  <div class="card"><span>Dead letters</span><b>{st['dead_letters']}</b></div>
  <div class="card"><span>Certified releases</span><b>{st['certified_versions']}</b></div>
  <div class="card"><span>Open incidents</span><b>{st['open_incidents']}</b></div>
  <div class="card"><span>Agent opex</span><b>CA${st['agent_opex_cad']:.2f}</b></div>
  <div class="card"><span>Revenue</span><b>CA${st['revenue_cad']:.2f}</b></div>
</div>
{owner_html}
<h2>Recent jobs</h2>
{rows([(j.id, j.agent, j.job_type, _pill(j.status.value), j.attempts,
        (j.last_error or "")[:70]) for j in jobs],
      [["#", "Agent", "Job", "Status", "Tries", "Error"]], "No jobs yet.")}
<h2>Products</h2>
{rows([(p.slug, p.title, p.status, p.risk_class) for p in products],
      [["Slug", "Title", "Status", "Risk"]], "No products yet.")}
<h2>Open incidents</h2>
{rows([(i.severity, i.product_slug or "-", i.report_count, i.summary[:70],
        "HALTS" if i.halts_publication else "") for i in incidents],
      [["Sev", "Product", "Reports", "Summary", ""]], "No open incidents.")}
<h2>Spend limits</h2>
{rows([(l.scope, f"CA${l.spent_today_cad:.2f}/{l.daily_cap_cad:.2f}",
        f"CA${l.spent_lifetime_cad:.2f}/{l.lifetime_cap_cad:.2f}",
        "PAUSED" if l.paused else "ok") for l in limits],
      [["Scope", "Today", "Lifetime", "State"]], "No spend limits configured.")}
<h2>Agents</h2>
{rows([(a.name, a.authority.value, a.phase.value, f"CA${a.daily_cost_ceiling_cad:.2f}",
        "on" if a.enabled else "off") for a in agents],
      [["Agent", "Authority", "Phase", "Daily cap", ""]], "No agents.")}
<h2>Audit trail</h2>
{rows([(f"{a.at:%m-%d %H:%M}", a.actor, a.action, (a.artifact or "")[:40]) for a in audits],
      [["When", "Actor", "Action", "Artifact"]], "Nothing audited yet.")}
</main></body></html>"""
