"""W4-FIRSTSALE: the owner's first-sale readiness view in the Command Center.

`GET /api/cc/first-sale` serves `launch.first_sale.build(db)` behind the same default-deny
`/api/cc/*` owner-session gate as every route here. Read-only: it reads state and never writes,
enqueues, renders customer files or contacts a provider. Like the launch packet it is built off
the request path, single-flight, at most once per `TTL`, and states its own `generated_at`.

Per product and shop-wide, every first-sale gate with PASS / FAIL / UNKNOWN, its evidence and
who acts (company or owner). UNKNOWN is never shown as passing.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from .providers import now_iso

TTL = timedelta(minutes=5)
WAIT_S = 2.0
BUILD = None            # replaceable in tests; production is `launch.first_sale.build`
_SOURCES = ["launch.first_sale.build", "launch.product_readiness.build",
            "commerce.category", "commerce.deliverables.durable_state",
            "integrations.etsy_image_readiness", "gates.first_customer",
            "ops.publication_authority.resolve"]
_STATUS = {"PASS": "OK", "FAIL": "BLOCKED", "UNKNOWN": "UNKNOWN"}
_lock = threading.Lock()
_cache: dict = {"at": None, "view": None, "error": None, "thread": None}


def reset() -> None:
    with _lock:
        _cache.update(at=None, view=None, error=None, thread=None)


def _refresh(db) -> None:
    from ...launch import first_sale

    try:
        v, err = (BUILD or first_sale.build)(db), None
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN with the reason
        v, err = None, f"{type(exc).__name__}: {str(exc)[:240]}"
    with _lock:
        _cache.update(at=datetime.now(timezone.utc), view=v, error=err, thread=None)


def _get(db, wait):
    now = datetime.now(timezone.utc)
    with _lock:
        if (_cache["at"] is None or now - _cache["at"] >= TTL) and _cache["thread"] is None:
            th = threading.Thread(target=_refresh, args=(db,), daemon=True,
                                  name="cc-first-sale")
            _cache["thread"] = th
            th.start()
        thread = _cache["thread"]
    if thread is not None:
        thread.join(WAIT_S if wait is None else wait)
    with _lock:
        return _cache["view"], _cache["error"], _cache["at"], _cache["thread"] is not None


def _gate_row(name: str, g: dict) -> dict:
    return {"gate": name, "state": g.get("state", "UNKNOWN"),
            "status": _STATUS.get(g.get("state"), "UNKNOWN"), "why": g.get("why", ""),
            "evidence": g.get("evidence", ""), "who_acts": g.get("who_acts"),
            "action": g.get("action", ""), "blocker": g.get("blocker")}


def view(db, *, wait: float | None = None) -> dict:
    v, err, read_at, generating = _get(db, wait)
    if v is None:
        why = (f"first-sale view could not be generated: {err}" if err else
               "the first-sale view is being generated from state; reload in a minute"
               if generating else "no first-sale view has been generated")
        env = {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
               "shop": [], "sources": _SOURCES, "reason": why, "generating": generating}
        return {"tab": "FIRST_SALE", "generated_at": now_iso(), "status": "UNKNOWN",
                "reason": why, "sections": {"first_sale": env}}
    items = []
    for p in v["products"]:
        states = list(p["gates"].values())
        status = ("OK" if p["first_sale_ready"] else
                  "BLOCKED" if "FAIL" in states else "UNKNOWN")
        items.append({"title": f"{p['title']} ({p['candidate']})", "status": status,
                      "who_acts": p["who_acts"],
                      "gates": [_gate_row(k, _first(p, k))
                                for k in v["gates"]]})
    shop = [_gate_row(k, g) for k, g in v["shop"].items()]
    status = "OK" if v["first_sale_possible"] else (
        "BLOCKED" if any(i["status"] == "BLOCKED" for i in items)
        or any(r["state"] == "FAIL" for r in shop) else "UNKNOWN")
    owner_acts = sorted({f"{r['gate']}: {r['action']}" for i in items for r in i["gates"]
                         if r["who_acts"] == "owner" and r["action"]})
    env = {"status": status, "as_of": v["generated_at"], "basis": "measured",
           "items": items, "shop": shop, "owner_actions": owner_acts,
           "rule": v["rule"], "sources": _SOURCES,
           "cache": {"read_at": read_at.isoformat() if read_at else None,
                     "ttl_seconds": int(TTL.total_seconds()), "refreshing": generating}}
    if status != "OK":
        env["reason"] = (f"no product is first-sale ready; "
                         f"{sum(1 for i in items if i['status'] == 'BLOCKED')} of {len(items)} "
                         f"blocked, {len(owner_acts)} owner action(s)")
    return {"tab": "FIRST_SALE", "generated_at": now_iso(), "status": status,
            "reason": env.get("reason"), "sections": {"first_sale": env}}


def _first(p: dict, gate: str) -> dict:
    """The product's gate, from its worst release (that release's evidence and action)."""
    order = {"FAIL": 0, "UNKNOWN": 1, "PASS": 2}
    rows = [r["gates"][gate] for r in p["releases"]]
    return sorted(rows, key=lambda g: order.get(g.get("state"), 1))[0] if rows else \
        {"state": "UNKNOWN", "why": "no release"}
