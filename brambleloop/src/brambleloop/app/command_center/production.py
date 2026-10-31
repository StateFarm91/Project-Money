"""W5-INVENTORY: the Command Center "Production" view (GET /api/cc/production).

Owner session only (the `/api/cc/*` default-deny gate), read-only: the inventory is derived in
`recorded` gate mode (verdicts store.publish already recorded), so a page load writes no row,
renders nothing and enqueues nothing. Cached for `TTL` seconds so repeated phone reloads do not
re-derive the whole inventory.

Sections (provider envelopes, so the generic CC renderer can draw any of them):
  inventory      -- one item per state: count and the products in it; the physical sample
                    is shown as an attribute beside the state (owner clarification 2026-10-27)
  tiers          -- internal / private Etsy draft / public publication readiness counts
  products       -- one row per product/version: state, physical sample, holds, flags
  agents_working -- jobs running now
  recent_outputs -- PDFs built, listing packages drafted, versions certified (7 d)
  stalls_loops   -- STALLED and LOOPING rows with their reasons
  costs_failures -- per-department 24 h / 7 d cost, failures and dead letters, useful vs no-op
  next_work      -- due/pending jobs and the next cadence windows
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

from . import providers

TTL = 60.0
_LOCK = threading.Lock()
_CACHE: dict = {"at": 0.0, "data": None}
SOURCES = ["jobs", "pattern_versions", "listings", "audit_log", "physical_tests",
           "draft_creation_intents", "cost_entries", "owner_actions"]


def reset() -> None:
    with _LOCK:
        _CACHE.update(at=0.0, data=None)


def _env(name, fn, sources=None):
    return providers.guard(name, fn, sources=sources or SOURCES)


def _inventory_section(inv: dict) -> dict:
    by_state: dict[str, list] = {}
    for it in inv["items"]:
        by_state.setdefault(it["state"], []).append(
            f"{it['slug']}@{it['version']}" if it["version"] else it["slug"])
    from ...products import production_inventory as pi

    items = []
    for s in inv["states"]:
        key = s["key"]
        if s["kind"] == "attribute":
            want = "pending" if key == pi.PHYSICAL_PENDING else "passed"
            members = [f"{it['slug']}@{it['version']}" for it in inv["items"]
                       if (it.get("physical_sample") or {}).get("status") == want]
            items.append({"title": s["label"], "key": key, "count": len(members),
                          "kind": "attribute (shown beside the state; gates public "
                                  "publication only)", "products": members[:30]})
        else:
            members = by_state.get(key, [])
            items.append({"title": s["label"], "key": key, "count": len(members),
                          "products": members[:30]})
    return providers.envelope("OK", items, SOURCES, provider="production.inventory",
                              as_of=inv["as_of"], total=inv["total"], counts=inv["counts"],
                              physical_counts=inv["physical_counts"])


def _tiers_section(inv: dict) -> dict:
    internal = sum(1 for it in inv["items"] if it["tiers"]["internal"].get("complete"))
    items = [
        {"title": "Internal package complete", "count": internal,
         "detail": "development, validation, review, PDF, visuals, listing package -- "
                   "never blocked by a sample photo"},
        {"title": "Private Etsy draft ready", "count": inv["private_draft_ready"],
         "detail": "product gates, phase and the owner's draft grant"},
        {"title": "Public publication ready", "count": inv["public_ready"],
         "detail": "everything above plus the physical sample where required"},
        {"title": "Awaiting physical sample", "count": inv["physical_counts"]["pending"],
         "detail": "never counted as Ready for publication"},
    ]
    return providers.envelope("OK", items, SOURCES, provider="production.tiers",
                              as_of=inv["as_of"])


def _products_section(inv: dict, flow: dict) -> dict:
    by_key = {(r["slug"], r["version"]): r for r in flow["rows"]}
    items = []
    for it in inv["items"]:
        fr = by_key.get((it["slug"], it["version"])) or {}
        status = ("BLOCKED" if fr.get("stalled") or it["state"] == "revision_required"
                  else "DEGRADED" if fr.get("looping") or it["holds"] else "OK")
        items.append({
            "title": f"{it['slug']}@{it['version']}" if it["version"] else it["slug"],
            "status": status, "inventory_state": it["label"], "detail": it["why"],
            "physical_sample": (it.get("physical_sample") or {}).get("status"),
            "held": ", ".join(sorted({h["kind"] for h in it["holds"]})) or None,
            "latest_stage": fr.get("latest_stage"),
            "last_progress_at": fr.get("last_progress_at"),
            "cost_to_date_cad": it["evidence"].get("cost_to_date_cad"),
            "stalled": bool(fr.get("stalled")), "looping": bool(fr.get("looping"))})
    order = {k: i for i, k in enumerate(("BLOCKED", "DEGRADED", "OK"))}
    items.sort(key=lambda x: (order[x["status"]], x["title"]))
    worst = items[0]["status"] if items else "OK"
    return providers.envelope(worst, items, SOURCES, provider="production.products",
                              as_of=inv["as_of"],
                              reason=None if worst == "OK" else
                              "some products are stalled, looping, held or need revision")


def _agents_working(db) -> dict:
    from sqlalchemy import select

    from ...core.models import Job, JobStatus
    from ...products.production_inventory import _Job

    with db.session() as s:
        rows = [_Job(j) for j in s.scalars(select(Job).where(Job.status == JobStatus.RUNNING)
                                           .order_by(Job.started_at))]
    items = [{"title": j.agent, "job_type": j.job_type, "job_id": j.id,
              "product": j.slug, "started_at": j.started_at.isoformat() if j.started_at
              else None} for j in rows]
    return providers.envelope("OK", items, ["jobs"], provider="production.agents_working",
                              count=len(items))


def _recent_outputs(db, now) -> dict:
    from sqlalchemy import select

    from ...core.models import AuditLog, Job, JobStatus

    since = now - timedelta(days=7)
    items = []
    with db.session() as s:
        for a in s.scalars(select(AuditLog).where(
                AuditLog.action.in_(("assets.built", "listing.seo_drafted")),
                AuditLog.at >= since).order_by(AuditLog.id.desc()).limit(30)):
            d = a.detail or {}
            items.append({"title": a.artifact, "kind": ("premium PDF" if a.action ==
                                                         "assets.built" else "listing package"),
                          "at": a.at.isoformat() if a.at else None,
                          "digest": ((d.get("pdf") or {}).get("sha256") or "")[:16] or None})
        for j in s.scalars(select(Job).where(Job.job_type == "gate.certify",
                                             Job.status == JobStatus.DONE,
                                             Job.finished_at >= since)
                           .order_by(Job.id.desc()).limit(30)):
            o = j.outputs or {}
            if o.get("granted") is True:
                items.append({"title": o.get("artifact"), "kind": "certified version",
                              "at": j.finished_at.isoformat() if j.finished_at else None,
                              "digest": (o.get("release_hash") or "")[:16] or None})
    items.sort(key=lambda x: x["at"] or "", reverse=True)
    return providers.envelope("OK", items[:40], ["audit_log", "jobs"],
                              provider="production.recent_outputs")


def _stalls_loops(flow: dict) -> dict:
    items = []
    for r in flow["rows"]:
        name = f"{r['slug']}@{r['version']}" if r["version"] else r["slug"]
        for st in r["stalls"]:
            items.append({"title": name, "status": "BLOCKED", "kind": f"STALLED: {st['kind']}",
                          "job_id": st.get("job_id"), "job_type": st.get("job_type"),
                          "detail": st.get("why") or f"{st.get('age_hours')} h"})
        for lp in r["loops"]:
            items.append({"title": name, "status": "DEGRADED",
                          "kind": f"LOOPING: {lp.get('kind', 'same_input_digest')}",
                          "job_type": lp["job_type"], "runs": lp["runs"],
                          "input_digest": lp["input_digest"],
                          "detail": lp.get("why") or ("outputs unchanged"
                                                       if lp["outputs_unchanged"]
                                                       else "outputs varied")})
    status = "BLOCKED" if flow["stalled_count"] else "DEGRADED" if flow["looping_count"] else "OK"
    return providers.envelope(status, items, ["jobs"], provider="production.flow_health",
                              reason=None if status == "OK" else
                              f"{flow['stalled_count']} stalled, {flow['looping_count']} looping",
                              thresholds=flow["thresholds"])


def _costs_failures(act: dict) -> dict:
    items = []
    d24 = {d["department"]: d for d in act["windows"]["24h"]["departments"]}
    for d in act["windows"]["7d"]["departments"]:
        a = d24.get(d["department"]) or {}
        status = "BLOCKED" if d["dead_defect"] else "DEGRADED" if d["failed"] else "OK"
        items.append({"title": d["department"], "status": status,
                      "cost_24h_cad": a.get("cost_cad", 0.0), "cost_7d_cad": d["cost_cad"],
                      "completed_7d": d["completed"], "useful_7d": d["useful"],
                      "no_op_7d": d["no_op"], "failed_7d": d["failed"],
                      "dead_defect_7d": d["dead_defect"], "dead_refused_7d": d["dead_refused"],
                      "idle_s_24h": a.get("idle_s")})
    worst = ("BLOCKED" if any(i["status"] == "BLOCKED" for i in items) else
             "DEGRADED" if any(i["status"] == "DEGRADED" for i in items) else "OK")
    return providers.envelope(worst, items, ["jobs", "cost_entries"],
                              provider="production.departments", as_of=act["as_of"],
                              reason=None if worst == "OK" else "failures or dead letters in 7 d",
                              agents_24h=act["windows"]["24h"]["agents"])


def _next_work(nw: dict) -> dict:
    items = [{"title": p["job_type"], "agent": p["agent"], "run_after": p["run_after"],
              "product": p["product"], "due": p["due"]} for p in nw["pending"]]
    items += [{"title": c["cadence"], "agent": c["agent"], "job_type": c["job_type"],
               "next_at": c["next_at"]} for c in nw["cadences"]]
    return providers.envelope("OK", items, ["jobs", "runtime.worker.CADENCES"],
                              provider="production.next_work")


def build(db) -> dict:
    from ...ops import flow_health
    from ...products import production_inventory as pi

    now = datetime.now(timezone.utc)
    rec = pi.load_records(db)
    inv = pi.derive(db, records=rec)
    fl = flow_health.flow(db, inventory=inv, records=rec, now=now)
    act = providers.guard("production.activity", lambda: flow_health.activity(db, now=now))
    sections = {
        "inventory": _env("production.inventory", lambda: _inventory_section(inv)),
        "tiers": _env("production.tiers", lambda: _tiers_section(inv)),
        "products": _env("production.products", lambda: _products_section(inv, fl)),
        "agents_working": _env("production.agents_working", lambda: _agents_working(db)),
        "recent_outputs": _env("production.recent_outputs", lambda: _recent_outputs(db, now)),
        "stalls_loops": _env("production.flow_health", lambda: _stalls_loops(fl)),
        "costs_failures": (_env("production.departments", lambda: _costs_failures(act))
                           if "windows" in act else act),
        "next_work": _env("production.next_work",
                          lambda: _next_work(flow_health.next_work(db, now=now))),
    }
    return {"tab": "PRODUCTION", "generated_at": providers.now_iso(), "read_only": True,
            "gate_mode": inv["gate_mode"], "sections": sections}


def view(db) -> dict:
    with _LOCK:
        if _CACHE["data"] is not None and time.monotonic() - _CACHE["at"] < TTL:
            return _CACHE["data"]
    try:
        data = build(db)
    except Exception as exc:  # noqa: BLE001 - an unreadable inventory is UNKNOWN, never empty
        return {"tab": "PRODUCTION", "generated_at": providers.now_iso(), "status": "UNKNOWN",
                "reason": f"production view could not be built: {type(exc).__name__}",
                "sections": {}}
    with _LOCK:
        _CACHE.update(at=time.monotonic(), data=data)
    return data
