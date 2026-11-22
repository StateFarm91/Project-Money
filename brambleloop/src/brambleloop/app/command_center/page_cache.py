"""eng/mc-perf: precomputed Mission Control page snapshots, with their age shown.

Why. The owner reported Mission Control "takes minutes and minutes to load when I click
stuff". Measured on a production-shaped database (MC-PERF.md): `/api/cc/autonomy` and
`/api/cc/learn` re-run every department's work planner (ledger scans, ads readiness, image
checks; ~17k SQL statements) on every click, and `/api/cc/company` re-runs autonomy, the
approval inbox, the finance summary and the storefront gate on every click. These readings
change on the scale of minutes, not per click.

What this does, and what it never does:

* A page body is computed once and kept for `ttl` seconds. Every body served from here says
  so: `snapshot = {computed_at, age_s, ttl_s, served_from_snapshot}`. Nothing cached is
  presented as fresh -- the age is in the body the page renders.
* Single-flight: concurrent clicks on a cold page wait for ONE computation, never N.
* Explicit invalidation: any successful non-GET request under `/api/cc/` (an owner action,
  an approval, a decision) clears every snapshot, so the next read after the owner acts is
  recomputed live. `invalidate()` is also callable directly.
* A failed computation is never cached.
* A snapshot is tied to the provider modules that computed it (`deps`): a provider lane
  installed, replaced or removed in this process since then forces a recomputation, so a
  source that has just started failing is never hidden behind its previous answer.
* Home's job counts -- work completed (24 h) and work in progress per department, the counts
  F-884 says must move with the database -- are re-read live on every snapshot hit
  (`tabs.home_live`, one jobs read) and listed in `snapshot.live`; the rest of the body is
  the snapshot, with its age.
* Only read-only page bodies go here. Approvals, the approve-all / approve-everything
  previews and every POST are never cached: a press re-checks each item live at the time
  of the press, and step-up auth is untouched.
* `BRAMBLELOOP_CC_SNAPSHOT_TTL_S=0` switches the cache off (every read live).

Also here: an in-flight request counter (`RequestsInFlight`) and `yield_to_requests()`,
which CPU-bound background work in the web process calls in its inner loops so the GIL is
handed to request threads while a request is being served (F-11 mitigation, measured in
MC-PERF.md). It never changes what the background work computes, only when it runs.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone

DEFAULT_TTL_S = 60.0


def _ttl(default: float) -> float:
    raw = os.environ.get("BRAMBLELOOP_CC_SNAPSHOT_TTL_S")
    if raw is None or raw == "":
        return default
    try:
        v = float(raw)
    except ValueError:
        return default
    return max(0.0, min(v, default))      # the environment may only shorten, never lengthen


class _Entry:
    __slots__ = ("value", "at", "mono", "generation", "deps")

    def __init__(self, value, at, mono, generation, deps=None):
        self.value, self.at, self.mono, self.generation = value, at, mono, generation
        self.deps = deps


_lock = threading.Lock()
_entries: dict[str, _Entry] = {}
_flights: dict[str, threading.Lock] = {}
_generation = 0
STATS = {"hits": 0, "misses": 0, "invalidations": 0}


def invalidate(reason: str = "") -> None:
    """Drop every snapshot (an owner write happened). In-flight computations that started
    before this call are not stored."""
    global _generation
    with _lock:
        _generation += 1
        _entries.clear()
        STATS["invalidations"] += 1


def reset() -> None:
    invalidate("reset")
    with _lock:
        STATS.update(hits=0, misses=0, invalidations=0)


def _stamp(body, entry: _Entry, ttl: float, cached: bool):
    if not isinstance(body, dict):
        return body
    out = dict(body)
    out["snapshot"] = {"computed_at": entry.at.isoformat(), "live": [],
                       "age_s": round(max(0.0, time.monotonic() - entry.mono), 1),
                       "ttl_s": ttl, "served_from_snapshot": cached,
                       "basis": ("precomputed page snapshot; recomputed after ttl_s or on "
                                 "any owner action" if cached else "computed for this request")}
    return out


def _ok(body) -> bool:
    return isinstance(body, dict)


def get(key: str, compute, *, ttl: float = DEFAULT_TTL_S, deps=None):
    """The page body for `key`: a snapshot younger than `ttl`, else computed now (once).

    `deps`, when given, is a cheap callable naming what the body was computed from (for the
    Command Center pages: which provider module each contract path resolves to). A snapshot
    is served only while `deps()` still returns what it returned when the body was computed;
    otherwise the body describes inputs that are gone, and it is recomputed."""
    ttl = _ttl(ttl)
    if ttl <= 0:
        return compute()
    now_deps = deps() if deps is not None else None

    def _fresh(e):
        return (e is not None and time.monotonic() - e.mono < ttl
                and e.deps == now_deps)

    with _lock:
        e = _entries.get(key)
        if _fresh(e):
            STATS["hits"] += 1
            return _stamp(e.value, e, ttl, True)
        flight = _flights.setdefault(key, threading.Lock())
    with flight:
        with _lock:                     # another reader may have filled it while we waited
            e = _entries.get(key)
            if _fresh(e):
                STATS["hits"] += 1
                return _stamp(e.value, e, ttl, True)
            gen = _generation
            STATS["misses"] += 1
        body = compute()
        e = _Entry(body, datetime.now(timezone.utc), time.monotonic(), gen, now_deps)
        if _ok(body):
            with _lock:
                if gen == _generation:  # not invalidated while computing
                    _entries[key] = e
        return _stamp(body, e, ttl, False)


# ---- request-aware yielding for background CPU work (F-11) ---------------------------


class RequestsInFlight:
    """ASGI wrapper: counts HTTP requests being served, and invalidates the page snapshots
    after any successful non-GET `/api/cc/` request."""

    count = 0
    _lock = threading.Lock()

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        cls = RequestsInFlight
        with cls._lock:
            cls.count += 1
        path = scope.get("path") or ""
        write = (scope.get("method") or "GET").upper() not in ("GET", "HEAD", "OPTIONS") \
            and path.startswith("/api/cc/")
        status = {"code": 0}

        async def _send(message):
            if message.get("type") == "http.response.start":
                status["code"] = int(message.get("status") or 0)
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            with cls._lock:
                cls.count -= 1
            if write and 200 <= status["code"] < 400:
                invalidate(f"{scope.get('method')} {path}")


#: Seconds a background loop sleeps (releasing the GIL) per yield while a request is in
#: flight. 0 disables yielding.
YIELD_S = float(os.environ.get("BRAMBLELOOP_BG_YIELD_S", "0.002") or 0)
_tick = threading.local()


def yield_to_requests(every: int = 200) -> None:
    """Called from inner loops of CPU-bound background work in the web process. Every
    `every` calls, if a request is in flight and this is not a request thread, sleep briefly
    so the request thread gets the GIL. Changes timing only, never results."""
    n = getattr(_tick, "n", 0) + 1
    _tick.n = n
    if n % every or YIELD_S <= 0 or RequestsInFlight.count <= 0:
        return
    if threading.current_thread().name.startswith(("AnyIO worker", "MainThread")):
        return
    time.sleep(YIELD_S)
