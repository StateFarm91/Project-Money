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
    Agent, AuditLog, Collection, ContentPiece, CostEntry, Incident, Job, JobStatus,
    LedgerEntry, Listing, ListingAsset, OwnerAction, PatternVersion, Product, SpendLimit,
    SupportCase, utcnow,
)
from ..gateway.model_gateway import available_providers
from ..queue.durable import DuplicateJob, JobQueue
from ..runtime import pipeline  # noqa: F401  -- registers job handlers
from ..runtime.worker import Scheduler
from . import runner

APP_VERSION = "0.1.0"

db = Database()
app = FastAPI(title="Brambleloop Studio OS", version=APP_VERSION)


@app.on_event("startup")
def _startup() -> None:
    schema_changes = db.create_all()
    if schema_changes:
        # A schema change nobody can see is how a deploy breaks quietly.
        Registry(db).audit("orchestrator", "schema.migrated",
                           detail={"changes": schema_changes[:50]})
    changes = Registry(db).seed_defaults()
    if changes:
        # A deploy that silently changes an agent's authority is a deploy nobody can audit.
        Registry(db).audit("orchestrator", "agents.reconciled",
                           detail={"changes": changes[:50]})
    runner.start(db)


@app.on_event("shutdown")
def _shutdown() -> None:
    runner.stop()


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
        {"status": "ok" if healthy else "degraded", "version": APP_VERSION, "db": detail,
         "runner": runner.STATE.to_dict()},
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
        "runner": runner.STATE.to_dict(),
        # Reported rather than assumed. An empty list is the truthful answer until a key is
        # configured, and no part of the system may imply a model integration that does not
        # exist.
        "model_providers": available_providers(),
    }


@app.post("/api/scheduler/tick")
def api_tick() -> dict:
    """Cron target. Idempotent per cadence window, so calling it often is harmless."""
    return {"enqueued": Scheduler(db).tick()}


@app.get("/api/catalogue")
def api_catalogue() -> dict:
    """What the shop would be, if it were open. Drafted, never published."""
    with db.session() as s:
        listings = list(s.scalars(select(Listing)))
        assets = list(s.scalars(select(ListingAsset)))
        content = list(s.scalars(select(ContentPiece)))
        collections = list(s.scalars(select(Collection)))
        products = {p.id: p for p in s.scalars(select(Product))}
        certified = {pv.product_id: pv for pv in s.scalars(
            select(PatternVersion).where(PatternVersion.certified == True))}  # noqa: E712

    by_slug: dict[str, int] = {}
    for a in assets:
        by_slug[a.product_slug] = by_slug.get(a.product_slug, 0) + 1
    content_by_slug: dict[str, int] = {}
    for c in content:
        content_by_slug[c.product_slug] = content_by_slug.get(c.product_slug, 0) + 1

    return {
        "published": False,
        "why": ("BRAMBLELOOP_PHASE=shadow. There is no Etsy, Pinterest, email or messaging "
                "integration in this system, so nothing here can reach a customer."),
        "listings": [
            {"slug": l.product_slug, "version": l.version, "title": l.title,
             "price_cad": l.price_cad, "tags": len(l.tags), "state": l.state,
             "search_share": round(l.seo_score, 3),
             "chain_version": l.chain_version,
             "images": by_slug.get(l.product_slug, 0),
             "content_pieces": content_by_slug.get(l.product_slug, 0)}
            for l in sorted(listings, key=lambda x: -x.seo_score)
        ],
        "collections": [{"slug": c.slug, "title": c.title, "family": c.family}
                        for c in collections],
        "totals": {"listings": len(listings), "listing_images": len(assets),
                   "content_pieces": len(content), "collections": len(collections),
                   "certified_patterns": len(certified), "products": len(products)},
    }


@app.get("/api/finance")
def api_finance() -> dict:
    """The books, the CFO's view and where CA$100K stands. Every figure observed."""
    from ..finance.books import Books, cfo_challenge, trajectory

    books = Books(db)
    pl = books.profit_and_loss()
    with db.session() as s:
        limits = list(s.scalars(select(SpendLimit)))
        validated = s.scalar(select(func.count()).select_from(PatternVersion).where(
            PatternVersion.certified == True)) or 0  # noqa: E712
        listings = s.scalar(select(func.count()).select_from(Listing)) or 0

    return {
        "profit_and_loss": pl.to_dict(),
        "unit_economics": books.unit_economics(products_validated=validated,
                                               listings_drafted=listings),
        "cfo_challenges": [c.to_dict() for c in cfo_challenge(
            pl, limits=limits, infra_monthly_cad=7.0, infra_ceiling_cad=20.0)],
        "trajectory": trajectory(pl),
    }


@app.get("/api/support")
def api_support(limit: int = 50) -> dict:
    with db.session() as s:
        cases = list(s.scalars(select(SupportCase).order_by(SupportCase.id.desc())
                               .limit(min(limit, 500))))
        return {
            "cases": [{"id": c.id, "at": c.at.isoformat(), "desk": c.specialist,
                       "product": c.product_slug, "version": c.version,
                       "escalated": c.escalated, "sent": c.sent,
                       "question": c.question[:160], "answer": c.answer[:400]}
                      for c in cases],
            "nothing_sent": all(not c.sent for c in cases),
        }


@app.post("/api/plan-cycle")
def api_plan_cycle(as_of: str | None = None) -> dict:
    """Enqueue a planning cycle now instead of waiting for the daily cadence.

    GREEN: it enqueues work the system already does on a schedule, spends nothing, and cannot
    publish -- shadow mode refuses at the far end regardless of who started the run.

    `as_of` sets the date the radar scores against, and also scopes the downstream idempotency
    keys, so re-running a cycle for a date already processed collapses instead of duplicating.
    Running it for a new date re-scores the pool against that calendar, which is the point:
    the portfolio changes with the date, not with the catalogue.
    """
    payload = {"as_of": as_of} if as_of else {}
    key = f"plan.cycle:{as_of}" if as_of else None
    try:
        job = JobQueue(db).enqueue("orchestrator", "plan.cycle", payload,
                                   idempotency_key=key)
    except DuplicateJob:
        return {"enqueued": False, "reason": f"a cycle for {as_of} is already queued"}
    return {"enqueued": True, "job_id": job.id, "as_of": as_of}


@app.post("/api/chain-rebuild")
def api_chain_rebuild() -> dict:
    """Restart the post-certification chain for releases whose listing is missing or stale.

    The cadence runs hourly, which is right for an unattended system and slow when a deploy
    has just landed a fix that needs to reach shipped products. GREEN: it enqueues work the
    system already does on a schedule, spends nothing, and cannot publish.
    """
    # Keyed to the minute: a burst of clicks collapses into one rebuild, and an operator who
    # genuinely wants another can have it a minute later. A rebuild is idempotent anyway, but
    # queueing fifty of them turns a safe operation into a self-inflicted load test.
    key = f"chain.rebuild:{utcnow():%Y%m%dT%H%M}"
    try:
        job = JobQueue(db).enqueue("listing", "chain.rebuild", {}, idempotency_key=key)
    except DuplicateJob:
        return {"enqueued": False,
                "reason": "a rebuild was already queued this minute; it is idempotent, so "
                          "the queued one does the same work"}
    return {"enqueued": True, "job_id": job.id}


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


@app.get("/api/audit")
def api_audit(limit: int = 100, action: str | None = None) -> dict:
    """Read-only audit trail. The dashboard shows fifteen rows; verification needs more."""
    with db.session() as s:
        q = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 1000))
        if action:
            q = select(AuditLog).where(AuditLog.action == action).order_by(
                AuditLog.id.desc()).limit(min(limit, 1000))
        rows = list(s.scalars(q))
        return {"audit": [
            {"id": a.id, "at": a.at.isoformat(), "actor": a.actor, "action": a.action,
             "artifact": a.artifact, "phase": a.phase.value if a.phase else None,
             "detail": a.detail}
            for a in rows
        ]}


@app.get("/api/verify")
def api_verify() -> JSONResponse:
    """Standing safety assertions, evaluated against live state.

    "Railway says deployed" is not the same as "the company is alive and behaving". This
    answers the questions that actually matter to an absent owner: is it running, is its
    memory durable, has anything escaped shadow mode, and are the money guards still on. Each
    check reports the evidence it used, so a green result can be argued with.
    """
    checks: list[dict] = []

    def check(name: str, ok: bool, evidence) -> None:
        checks.append({"check": name, "ok": bool(ok), "evidence": evidence})

    phase = os.environ.get("BRAMBLELOOP_PHASE", "shadow")
    check("phase_is_shadow", phase == "shadow", {"BRAMBLELOOP_PHASE": phase})

    with db.session() as s:
        published = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "store.published")) or 0
        refused = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "store.publish_refused")) or 0
        certified = s.scalar(select(func.count()).select_from(PatternVersion).where(
            PatternVersion.certified)) or 0
        audits = s.scalar(select(func.count()).select_from(AuditLog)) or 0
        revenue = s.scalar(select(func.sum(LedgerEntry.gross_cad))) or 0.0
        customers = s.scalar(select(func.count()).select_from(LedgerEntry)) or 0
        limits = list(s.scalars(select(SpendLimit)))
        agents = list(s.scalars(select(Agent)))
        ad_spend = s.scalar(select(func.sum(CostEntry.amount_cad)).where(
            CostEntry.kind == "ads")) or 0.0

    check("nothing_published", published == 0,
          {"store.published": published, "store.publish_refused": refused})
    check("publication_was_actually_attempted_and_refused", refused > 0,
          {"refusals": refused})
    check("no_paid_advertising", ad_spend == 0, {"ad_spend_cad": float(ad_spend)})
    check("no_revenue_claimed", float(revenue) == 0.0 and customers == 0,
          {"revenue_cad": float(revenue), "ledger_entries": customers})
    check("no_model_provider_configured", available_providers() == [],
          {"providers": available_providers()})
    check("every_agent_has_a_cost_ceiling",
          bool(agents) and all(a.daily_cost_ceiling_cad > 0 for a in agents),
          {"agents": len(agents),
           "without_ceiling": [a.name for a in agents if a.daily_cost_ceiling_cad <= 0]})
    check("spend_limits_not_breached", all(not l.paused for l in limits),
          {"paused_scopes": [l.scope for l in limits if l.paused]})

    # Durability: a state this rich cannot have come from a container that started empty.
    durable = certified > 0 and audits > 0 and not _is_sqlite()
    check("state_is_in_a_durable_database", durable,
          {"engine": db.engine.dialect.name, "certified_versions": certified,
           "audit_records": audits})

    r = runner.STATE.to_dict()
    check("worker_is_alive", bool(r["worker_alive"]),
          {"last_tick": r["worker_last_tick"], "restarts": r["worker_restarts"]})
    check("scheduler_has_ticked", r["scheduler_last_tick"] is not None,
          {"last_tick": r["scheduler_last_tick"]})

    # Recent, not historical. A dead letter from a bug that was fixed last week is archaeology;
    # an endpoint that reports 503 forever because of it is an endpoint nobody reads. The
    # historical count stays in the evidence so the record is not quietly lost.
    q = JobQueue(db)
    dead = q.dead_letters()
    cutoff = utcnow() - timedelta(hours=24)
    unexpected = [j for j in dead if j.job_type != "store.publish"]
    recent = [j for j in unexpected if (j.finished_at or j.created_at) >= cutoff]
    check("no_unexpected_dead_letters_in_24h", not recent,
          {"recent": sorted({j.job_type for j in recent}),
           "historical_total": len(unexpected),
           "historical_types": sorted({j.job_type for j in unexpected}),
           "expected_publish_refusals":
               sum(1 for j in dead if j.job_type == "store.publish")})

    passed = all(c["ok"] for c in checks)
    return JSONResponse({"ok": passed, "checks": checks},
                        status_code=200 if passed else 503)


@app.post("/api/dead-letters/requeue")
def api_requeue(job_types: str | None = None) -> dict:
    """Re-drive dead letters after the defect that killed them is fixed.

    GREEN under the authority matrix: reversible, no spend, and structurally incapable of
    re-driving a deliberate refusal -- a publish blocked by shadow mode stays blocked no
    matter how often this is called.
    """
    types = [t.strip() for t in job_types.split(",")] if job_types else None
    result = JobQueue(db).requeue_dead(job_types=types)
    Registry(db).audit("orchestrator", "ops.dead_letters_requeued",
                       detail={"requeued": result["requeued"][:50],
                               "skipped": result["skipped"][:50],
                               "requested_types": types})
    return result


def _is_sqlite() -> bool:
    return db.engine.dialect.name == "sqlite"


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


def _counts() -> dict:
    """Catalogue totals for the dashboard. Cheap counts, not a full listing dump."""
    with db.session() as s:
        return {
            "listings": s.scalar(select(func.count()).select_from(Listing)) or 0,
            "listing_images": s.scalar(select(func.count()).select_from(ListingAsset)) or 0,
            "content_pieces": s.scalar(select(func.count()).select_from(ContentPiece)) or 0,
        }


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
  <div class="card"><span>Worker</span><b>{'live' if st['runner']['worker_alive'] else ('off' if not st['runner']['enabled'] else 'stalled')}</b></div>
  <div class="card"><span>Model providers</span><b>{len(st['model_providers']) or 'none'}</b></div>
  <div class="card"><span>Listings drafted</span><b>{_counts()['listings']}</b></div>
  <div class="card"><span>Listing images</span><b>{_counts()['listing_images']}</b></div>
  <div class="card"><span>Content pieces</span><b>{_counts()['content_pieces']}</b></div>
</div>
<div class="sub" style="color:var(--muted);font-size:12px;margin:-14px 0 18px">
Runner: {st['runner']['worker'] or 'not started'} &middot; last tick
{st['runner']['worker_last_tick'] or 'never'} &middot; restarts {st['runner']['worker_restarts']}
&middot; scheduler {st['runner']['scheduler_last_tick'] or 'never'}
{('&middot; last error: ' + st['runner']['last_error']) if st['runner']['last_error'] else ''}
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
