"""W4-C12 wiring: the three C12 modules on the schedule (read-only or record-only).

* `listing.search_visibility_aging` (daily, `listing`) -- `commerce.search_visibility.aging`:
  how long each Search Visibility finding has been open; a fix Etsy has not cleared inside its
  window opens one de-duplicated P2 incident (resolved again when a reading clears it). Reads
  rows, writes a reading and incident state. No Etsy call: the page is owner-recorded.
* `listing.window_captures` (daily, `listing`) -- `commerce.listing_lifecycle.due_captures`
  over every listing with a verified activation in the lifecycle trail: which boost-window
  captures are due. Writes one reading; the captures themselves are filed by the owner
  (`record_capture`), never invented here.
* `etsy.dashboard_harvest` (daily, `orchestrator`) -- `integrations.etsy_dashboard.harvest`:
  every API-reachable actionable item (open orders, expiring renewals) from rows already on
  file becomes one de-duplicated owner task, and a task no longer observed is closed with its
  closure proof. No Etsy call: it reads stored orders and the stored listing census.

None spends, none publishes, none calls Etsy. The owner-entry HTTP routes for these modules
are the integrator's (with their security-list entries) and are not added here.
"""
from __future__ import annotations

from .worker import JobContext, handlers

AGING = "listing.search_visibility_aging"
CAPTURES = "listing.window_captures"
HARVEST = "etsy.dashboard_harvest"


def _store(db, kind, payload):
    from .etsy_ops import store_reading

    store_reading(db, kind, payload)


@handlers.register(AGING)
def handle_search_visibility_aging(ctx: JobContext) -> dict:
    from ..commerce import search_visibility as sv

    rep = sv.aging(ctx.db)
    _store(ctx.db, AGING, {k: rep[k] for k in ("items", "overdue", "incidents_opened",
                                               "refresh_window_days", "basis")})
    ctx.audit(AGING, detail={"open": len(rep["items"]), "overdue": len(rep["overdue"]),
                             "incidents_opened": len(rep["incidents_opened"])})
    return {"open": len(rep["items"]), "overdue": len(rep["overdue"]),
            "incidents_opened": rep["incidents_opened"],
            "work_done": len(rep["items"]) + len(rep["incidents_opened"])}


def activated_listing_ids(db) -> list[str]:
    from ..commerce import listing_lifecycle as lc

    return sorted({str(e["listing_id"]) for e in lc.trail(db)
                   if e.get("action") == "activate" and e.get("result") == "verified"
                   and e.get("listing_id")})


@handlers.register(CAPTURES)
def handle_window_captures(ctx: JobContext) -> dict:
    from ..commerce import listing_lifecycle as lc

    ids = activated_listing_ids(ctx.db)
    due = lc.due_captures(ctx.db, ids)
    _store(ctx.db, CAPTURES, {"listings": ids, "due": due, "basis": lc.WINDOW_BASIS})
    ctx.audit(CAPTURES, detail={"listings": len(ids), "due": len(due)})
    return {"listings": len(ids), "due": due, "work_done": len(due)}


@handlers.register(HARVEST)
def handle_dashboard_harvest(ctx: JobContext) -> dict:
    from ..integrations import etsy_dashboard as dash

    rep = dash.harvest(ctx.db)
    _store(ctx.db, HARVEST, {k: rep[k] for k in ("at", "opened", "still_open", "closed",
                                                 "unavailable")})
    ctx.audit(HARVEST, detail={"opened": len(rep["opened"]), "closed": len(rep["closed"]),
                               "still_open": len(rep["still_open"])})
    return {"opened": rep["opened"], "closed": rep["closed"],
            "still_open": len(rep["still_open"]), "unavailable": rep["unavailable"],
            "work_done": len(rep["opened"]) + len(rep["closed"])}
