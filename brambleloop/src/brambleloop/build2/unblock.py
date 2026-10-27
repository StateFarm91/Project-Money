"""F-467: unblock fan-out -- a write that can open a gate recomputes the build graph now.

`build.tick` (hourly) is what un-parks requirements whose gate opened and names the ready
work a build session should start on. Waiting up to an hour after the owner answered a card,
recorded an Insights reading or authorised Etsy is the delay F-467 names. `request_recompute`
enqueues `build.tick` at once (idempotent per trigger per minute, so a burst of writes is one
recompute), and the HTTP middleware in `app.main` calls it after any successful write to a
gate-opening route. The tick's own operator note is the dispatch card for READY build work
(the deployed worker writes no code). Enqueue-only: it never runs the tick in the request.
"""
from __future__ import annotations

from datetime import datetime, timezone

# Routes whose successful write can open a build gate (owner decisions and grants, owner
# readings, Etsy authorisation). Prefix match; GET only for the OAuth callback.
GATE_WRITE_PREFIXES: tuple[str, ...] = (
    "/api/owner/decision", "/api/owner/phase", "/api/owner/publication",
    "/api/owner/activation", "/api/owner/ledger-mapping", "/api/insights/snapshot",
    "/api/insights/paste", "/api/etsy/oauth/callback",
)
GATE_READ_OPENERS: frozenset[str] = frozenset({"/api/etsy/oauth/callback"})


def opens_gates(method: str, path: str) -> bool:
    if not path.startswith(GATE_WRITE_PREFIXES):
        return False
    return method.upper() != "GET" or path in GATE_READ_OPENERS


def request_recompute(db, *, trigger: str, now: datetime | None = None) -> bool:
    from ..queue.durable import DuplicateJob, JobQueue

    now = now or datetime.now(timezone.utc)
    key = f"build.tick:event:{trigger.strip('/').replace('/', '.')}:{int(now.timestamp() // 60)}"
    try:
        JobQueue(db).enqueue("orchestrator", "build.tick",
                             {"trigger": trigger, "source": "gate_write"},
                             idempotency_key=key[:200], priority=10)
        return True
    except DuplicateJob:
        return False
