"""F-878 (W4-CCPACKET): the owner's Launch-0 launch packet in the Command Center.

`GET /api/cc/launch/packet` serves `launch.packet.build(db, sha=build.commit())` behind the
same gate as every `/api/cc/*` route (default-deny: the operator credential must be configured
and an owner session is required; `security.operator_gate` -> `auth.gate`). Read-only: the
packet reads state and never writes, enqueues, renders or contacts a provider.

The packet is regenerated at most once per `TTL`, in one background build shared by concurrent
requests (a full assessment takes tens of seconds), so page loads neither wait on it nor stack
repeated full assessments. The view states the
packet's own `generated_at`, so a cached packet never reads as fresher than it is.

The packet's own verdict is kept verbatim (READY / BLOCKED / UNKNOWN); the card status maps it
onto the Command Center vocabulary (READY -> OK). UNKNOWN is never shown as passing.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .providers import now_iso

TTL = timedelta(minutes=5)
_REPO = Path(__file__).resolve().parents[4]
_VERDICT_STATUS = {"READY": "OK", "BLOCKED": "BLOCKED", "UNKNOWN": "UNKNOWN"}
_SOURCES = ["launch.packet.build", "ops.publication_authority.evidence",
            "launch.readiness.launch_assessment", "core.phase.resolve", "core.build.commit"]

_lock = threading.Lock()
_cache: dict = {"at": None, "packet": None, "error": None, "thread": None, "started": None}

# Replaceable in tests; the production builder is `launch.packet.build`.
BUILD = None
# How long a request waits for a packet being generated before answering without it.
WAIT_S = 2.0


def reset() -> None:
    with _lock:
        _cache.update(at=None, packet=None, error=None, thread=None, started=None)


def _build(db) -> dict:
    from ...core import build as build_mod
    from ...launch import packet

    fn = BUILD or packet.build
    research = _REPO / "research" / "final_build"
    # The deploy image ships src/ only: without research/ the recorded-suite section says
    # UNKNOWN ("no repository root given") rather than pointing at files that are not there.
    return fn(db, sha=build_mod.commit(), repo_root=_REPO if research.is_dir() else None)


def _refresh(db) -> None:
    try:
        p, err = _build(db), None
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN with the reason
        p, err = None, f"{type(exc).__name__}: {str(exc)[:240]}"
    with _lock:
        _cache.update(at=datetime.now(timezone.utc), packet=p, error=err, thread=None)


def _packet(db, wait: float | None = None):
    """(packet, error, read_at, generating). A full assessment takes seconds to tens of
    seconds, so it runs OFF the request path, single-flight: a stale or absent packet starts
    one background build; the request waits at most `wait` and otherwise answers with the
    last packet (whose own generated_at it shows) or, before the first, UNKNOWN."""
    now = datetime.now(timezone.utc)
    with _lock:
        stale = _cache["at"] is None or now - _cache["at"] >= TTL
        if stale and _cache["thread"] is None:
            th = threading.Thread(target=_refresh, args=(db,), daemon=True,
                                  name="cc-launch-packet")
            _cache.update(thread=th, started=now)
            th.start()
        thread = _cache["thread"]
    if thread is not None:
        thread.join(WAIT_S if wait is None else wait)
    with _lock:
        return (_cache["packet"], _cache["error"], _cache["at"],
                _cache["thread"] is not None)


def _product_row(p: dict) -> dict:
    gates = p.get("open_gates") or []
    unknown = p.get("unknown") or []
    status = "OK" if p.get("publishable_now") else ("UNKNOWN" if unknown else "BLOCKED")
    listing = p.get("listing") or {}
    return {"title": f"{p.get('candidate') or p.get('slug')} · {p.get('slug')} v{p.get('version')}",
            "status": status,
            "certified": p.get("certified"),
            "publishable_now": p.get("publishable_now"),
            "physical_proof": p.get("physical_proof"),
            "listing_state": listing.get("state") if listing else None,
            "price_cad": listing.get("price_cad") if listing else None,
            "open_gates": [f"{g.get('section')}: {g.get('state')}" for g in gates],
            "detail": "; ".join(f"{g.get('section')} {g.get('state')}: {g.get('why') or ''}"[:160]
                                for g in gates[:4]) or "every gated section passes"}


def view(db, *, wait: float | None = None) -> dict:
    p, err, read_at, generating = _packet(db, wait)
    if p is None:
        why = (f"launch packet could not be generated: {err}" if err else
               "the launch packet is being generated from state; reload in a minute"
               if generating else "no launch packet has been generated")
        env = {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
               "sources": _SOURCES, "provider": "launch.packet.build", "reason": why,
               "generating": generating}
        return {"tab": "LAUNCH_PACKET", "generated_at": now_iso(), "status": "UNKNOWN",
                "reason": env["reason"], "sections": {"packet": env}}
    verdict = str(p.get("verdict") or "UNKNOWN")
    status = _VERDICT_STATUS.get(verdict, "UNKNOWN")
    products = p.get("products") or []
    reason = None
    if status != "OK":
        bits = []
        if p.get("products_error"):
            bits.append(f"products unreadable: {p['products_error']}")
        if p.get("products_blocked"):
            bits.append(f"{len(p['products_blocked'])} of {len(products)} product(s) not "
                        "publishable now")
        if p.get("products_with_unknowns"):
            bits.append(f"{len(p['products_with_unknowns'])} product(s) with sections never read")
        q = p.get("owner_queue") or {}
        if q.get("owner_actions"):
            bits.append(f"{len(q['owner_actions'])} open owner action(s)")
        if not (p.get("phase") or {}).get("agree", True):
            bits.append("recorded phase and environment disagree")
        reason = f"verdict {verdict}: " + ("; ".join(bits) or "see the packet")
    env = {"status": status, "as_of": p.get("generated_at"), "basis": "measured",
           "items": [_product_row(x) for x in products], "sources": _SOURCES,
           "provider": "launch.packet.build", "verdict": verdict,
           "verdict_rule": p.get("verdict_rule"), "candidate_sha": p.get("candidate_sha"),
           "phase": p.get("phase"), "owner_queue": p.get("owner_queue"),
           "owner_queue_error": p.get("owner_queue_error"),
           "spend_limits": p.get("spend_limits"),
           "spend_limits_error": p.get("spend_limits_error"),
           "recorded_suite": p.get("recorded_suite"),
           "rollback_path": p.get("rollback_path"),
           "activation_steps": p.get("activation_steps"),
           "cache": {"read_at": read_at.isoformat() if read_at else None,
                     "ttl_seconds": int(TTL.total_seconds()), "refreshing": generating}}
    if reason:
        env["reason"] = reason
    return {"tab": "LAUNCH_PACKET", "generated_at": now_iso(), "status": status,
            "reason": reason, "sections": {"packet": env}}
