"""The owner-private context in the Command Center (PRIV contract, spec/07 Ruling 2).

This is the ONLY non-private module allowed to import `laura.private.{access,store}` or call
`.reveal()` (`laura.private.access.ALLOWED_IMPORTERS`; a static test enforces it). Everything
private enters and leaves through here, and only here:

* Opening needs a live owner session with a FRESH step-up (`access.open_context`). The grant id
  never goes to the client: it is looked up server-side, per request, from the session's own
  unrevoked grant and re-verified by `access.require` on every store call.
* Values are revealed only while building the private view's response body (served with
  `Cache-Control: no-store`). Nothing private is written to notifications, the timeline, audit
  detail, Ask Company, Talk to Laura (business), any provider summary or Python logging.
* Refusals are recorded as security events with kind `private_context` and the exception
  CLASS NAME only -- never the body, text, key or a record id.
* What exists: owner-supplied facts, owner turns, forget, close, and -- only when the owner
  has enabled it -- Laura's reply in the private register (D-W4-PL-1, PRIVATE_LAURA_TRACE §5
  Step 3). `owner_turn` records the owner's words; then, if the private key is configured, the
  owner's register switch is on and a spend authorisation exists, it reveals the owner's notes
  and recent turns HERE, passes them as plain strings inside delimited data blocks to
  `gateway.laura_register.reply` (the isolated model call: no paid-call journal, no cache, no
  content in any record), and records the answer through
  `store.record_turn(role="laura", reply_to=<owner turn>, model_ref=...)` -- the only
  provenance-valid way a reply enters history. The reply is returned only in this no-store
  POST body. Any unavailability is `reply_status: UNAVAILABLE` with a generic reason; there is
  never a canned or templated private reply. The register is the owner's adult register
  (`laura.private_reply@3`, D-W4-PL-VENICE-ADULT): explicit adult dialogue and consensual
  roleplay for the one adult owner, with hard limits that are never relaxed (no minors, no
  non-consent presented as endorsed, no real people, nothing unlawful) and Venice's Terms as the
  outer limit, never worked around.

Business paths never import this module (`test_w3_laura_cc_private` proves it statically and
with an SQL watch), and `laura.private.firewall.reject_private` refuses its values on every
protected path.
"""
from __future__ import annotations

from datetime import datetime, timezone

REPLY_GATED = ("Laura's private replies are off until the owner enables them: the private key "
               "(BRAMBLELOOP_PRIVATE_MEMORY_KEY), the register switch "
               "(BRAMBLELOOP_LAURA_PRIVATE_REGISTER=1), the private provider "
               "(BRAMBLELOOP_PRIVATE_PROVIDER=venice with VENICE_API_KEY) and a spend "
               "authorisation "
               "(BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD, default CA$0, at most the laura_private "
               "CA$0.50/day), on a deployed release. Until then your words are stored "
               "encrypted and no reply is generated (D-W4-PL-1, pending owner "
               "acknowledgement).")
REPLY_ENABLED = ("Laura replies in her private adult register (owner ruling 2026-10-20): "
                 "affectionate, romantic and flirtatious, including explicit adult dialogue "
                 "and consensual roleplay; hard limits always hold (never minors, real "
                 "people or anything unlawful) and Venice's Terms are the outer limit. "
                 "Replies are stored encrypted with your words.")
#: How much private context feeds one reply (latest facts, most recent turns).
CONTEXT_FACTS = 20
CONTEXT_TURNS = 12


class PrivateUnavailable(Exception):
    """Mapped by the route to an HTTP status with a generic message. `status` 403/503/400."""

    def __init__(self, status: int, code: str, exc_name: str):
        super().__init__(code)
        self.status = status
        self.code = code
        self.exc_name = exc_name


def _map(exc: Exception) -> PrivateUnavailable:
    from ...laura.private.errors import (KeyUnavailable, PrivateAccessRefused,
                                         PrivateRefused)

    name = type(exc).__name__
    if isinstance(exc, KeyUnavailable):
        return PrivateUnavailable(503, "PRIVATE_UNAVAILABLE", name)
    if isinstance(exc, PrivateAccessRefused):
        return PrivateUnavailable(403, "PRIVATE_REFUSED", name)
    if isinstance(exc, PrivateRefused):
        return PrivateUnavailable(400, "PRIVATE_INPUT_REFUSED", name)
    return PrivateUnavailable(500, "PRIVATE_ERROR", name)


def _grant_id(db, session_public_id: str) -> str | None:
    """The session's newest live grant (server-side; never sent to the client)."""
    from sqlalchemy import inspect, select

    from ...laura.private.models import PrivateGrant

    if not inspect(db.engine).has_table(PrivateGrant.__tablename__):
        return None
    now = datetime.now(timezone.utc)
    with db.session() as s:
        rows = list(s.scalars(select(PrivateGrant).where(
            PrivateGrant.session_public_id == session_public_id,
            PrivateGrant.revoked_at.is_(None)).order_by(PrivateGrant.id.desc()).limit(5)))
        for g in rows:
            exp = g.expires_at if g.expires_at.tzinfo else g.expires_at.replace(
                tzinfo=timezone.utc)
            if exp > now:
                return g.grant_id
    return None


def _principal(db, session_public_id: str):
    from ...laura.private import access
    from ...laura.private.errors import PrivateAccessRefused

    gid = _grant_id(db, session_public_id)
    if gid is None:
        raise PrivateAccessRefused("no open private context on this session")
    return access.resume(db, session_public_id, gid)


def _call(fn):
    try:
        return fn()
    except PrivateUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - every failure becomes a generic refusal
        raise _map(exc) from None


def _agent_present(db) -> bool:
    """Is the `laura_private` billing agent registered here with a positive ceiling?"""
    import math

    from ...agents.registry import Registry
    from ...gateway import laura_register

    try:
        row = Registry(db).get(laura_register.AGENT)
    except Exception:  # noqa: BLE001 - absent (PermissionDenied) or unreadable is "unmet"
        return False
    c = float(row.daily_cost_ceiling_cad or 0.0)
    return bool(math.isfinite(c) and c > 0)


def _release_deployed(boot: dict | None = None, env=None) -> dict:
    """Is the running process a proven, deployed release? One rule, in
    `gateway.laura_register.release_proven`, shared with the reply path that enforces it."""
    from ...gateway import laura_register

    return laura_register.release_proven(env, boot)


def prerequisites(db, *, env=None, boot: dict | None = None) -> list[dict]:
    """Each activation prerequisite, met or unmet, by NAME (never a value of any secret).

    W4-PLACT (owner decision 2026-10-13, D-W4-PL-3). Human consent is NOT a prerequisite:
    Private Laura is Brambleloop's established AI persona, not an impersonation of a real
    person (OA-PL-3 removed). Truthful AI representation still binds in the prompt.
    """
    from ...gateway import laura_register
    from ...laura.private import store

    e = laura_register.enablement(env)
    try:
        key = bool(store.configured())          # validates the key; never reads it out
    except Exception:  # noqa: BLE001
        key = False
    rel = _release_deployed(boot, env)
    n = e["names"]
    return [
        {"id": "key_configured", "met": key,
         "label": f"private memory key configured ({n['private_key']})"},
        {"id": "register_switch", "met": bool(e["register_switch"]),
         "label": f"register switch {n['switch']}=1"},
        {"id": "daily_cad_set", "met": e["spend_authorised_cad_per_day"] > 0,
         "label": (f"daily spend set ({n['spend']}; CA$"
                   f"{e['spend_authorised_cad_per_day']:.2f}/day, capped at the "
                   f"{laura_register.AGENT} ceiling CA${laura_register.agent_ceiling_cad():.2f})")},
        {"id": "laura_private_agent", "met": _agent_present(db),
         "label": f"billing agent {laura_register.AGENT} registered with its own daily ceiling"},
        # W4-VENICE (owner ruling D-W4-PL-VENICE): Venice is the Private Laura provider. Met
        # only with Venice selected AND its key present (names only; never the value).
        {"id": "private_provider_venice",
         "met": bool(e.get("provider") == "venice" and e["provider_configured"]),
         "label": (f"private provider Venice selected ({n['provider_switch']}=venice) and "
                   f"its key configured (VENICE_API_KEY); model {_venice_model()}")},
        {"id": "current_release_deployed", "met": rel["met"],
         "label": f"current release deployed ({rel['detail']})"},
    ]


def _venice_model() -> str:
    from ...gateway import venice

    return venice.model() or f"{venice.MODEL} (not eligible: refused)"


def _enablement(db=None) -> dict:
    """Non-content: whether a private reply may be attempted, and which gate is closed."""
    from ...gateway import laura_register
    from ...laura.private import store

    e = laura_register.enablement()
    key = store.configured()
    agent = _agent_present(db) if db is not None else True
    # Security review of 5f18d11 (L3): the release prerequisite gates enablement too.
    release = bool(laura_register.release_proven()["met"])
    return {"key_configured": key, "register_switch": e["register_switch"],
            "spend_authorised_cad_per_day": e["spend_authorised_cad_per_day"],
            "provider_configured": e["provider_configured"],
            "provider": e.get("provider"),
            "laura_private_agent": agent,
            "current_release_deployed": release,
            "enabled": bool(key and e["register_switch"]
                            and e["spend_authorised_cad_per_day"] > 0
                            and e["provider_configured"] and agent and release)}


def _register_label(en: dict) -> str:
    return "ENABLED" if en["enabled"] else "GATED"


def status(db, session_public_id: str) -> dict:
    """Non-content status for the badge: configured? open? is the reply register enabled?"""
    from ...laura.private import store

    try:
        is_open = bool(session_public_id) and _grant_id(db, session_public_id) is not None
    except Exception:  # noqa: BLE001
        is_open = False
    en = _enablement(db)
    prereq = prerequisites(db)
    return {"configured": store.configured(), "open": is_open,
            "requires": "a fresh owner step-up to open; closes on logout/revoke or after 30 min",
            "reply_register": _register_label(en),
            "reply_why": REPLY_ENABLED if en["enabled"] else REPLY_GATED,
            "enablement": en,
            # W4-PLACT: each activation prerequisite as met/unmet (names only, no secrets).
            "prerequisites": prereq,
            "prerequisites_met": all(p["met"] for p in prereq),
            "isolation": "encrypted owner-only store; never read by business, public, customer "
                         "or protected paths"}


def open_(db, session_public_id: str) -> dict:
    from ...laura.private import access

    def run():
        p = access.open_context(db, session_public_id, flag=access.PRIVATE_FLAG)
        access.require(db, p, "open")      # verify the fresh grant end to end
        return {"open": True, "ttl_minutes": int(access.GRANT_TTL.total_seconds() // 60)}
    return _call(run)


def close(db, session_public_id: str) -> dict:
    from ...laura.private import access

    return _call(lambda: {"closed": access.close_context(db, _principal(db,
                                                                         session_public_id))})


def on_session_revoked(db, session_public_id: str, reason: str = "session_revoked") -> int:
    """Belt and braces for logout / revoke (access.require already refuses a dead session)."""
    from ...laura.private import access

    try:
        return access.revoke_session_contexts(db, session_public_id, reason)
    except Exception:  # noqa: BLE001 - the session itself is already revoked
        return 0


def _row(r) -> dict:
    return {"id": r.record_id, "kind": r.kind, "provenance": r.provenance,
            "at": (r.created_at.isoformat() if hasattr(r.created_at, "isoformat")
                   else (str(r.created_at) if r.created_at else None)),
            "role": r.role, "key": r.key.reveal() if r.key is not None else None,
            "text": r.value.reveal() if r.value is not None else None}


def view(db, session_public_id: str, *, limit: int = 50) -> dict:
    """Facts + conversation, revealed for the private response body only."""
    from ...laura.private import store

    def run():
        p = _principal(db, session_public_id)
        return {"facts": [_row(r) for r in store.facts(db, p)],
                "conversation": [_row(r) for r in store.conversation(db, p, limit=limit)],
                "reply_register": _register_label(_enablement(db))}
    return _call(run)


def remember(db, session_public_id: str, key: str, text: str) -> dict:
    from ...laura.private import store

    return _call(lambda: {"id": store.remember(db, _principal(db, session_public_id),
                                               str(key or ""), str(text or ""),
                                               provenance="owner_supplied")})


def _laura_reply(db, principal, owner_turn_id: str, text: str) -> dict:
    """Laura's reply to one owner turn, or a generic UNAVAILABLE. Reveals only here."""
    from ...gateway import laura_register
    from ...laura.private import store

    if not laura_register.enablement()["register_switch"]:
        return {"reply": None, "reply_status": "UNAVAILABLE", "reason": "REGISTER_OFF",
                "why": REPLY_GATED}
    # With the switch on, every other gate (spend authorisation, provider, budget, health)
    # is decided -- and each money refusal audited without content -- by the isolated call.
    facts = [(r.key.reveal() if r.key is not None else "", r.value.reveal())
             for r in store.facts(db, principal)[:CONTEXT_FACTS]]
    turns = [(r.role, r.value.reveal())
             for r in store.conversation(db, principal, limit=CONTEXT_TURNS + 1)
             if r.record_id != owner_turn_id][-CONTEXT_TURNS:]
    user = laura_register.render_user(facts=facts, turns=turns, message=text)
    try:
        out = laura_register.reply(db, system=laura_register.PROMPT.system, user=user)
    except laura_register.ReplyUnavailable as exc:
        return {"reply": None, "reply_status": "UNAVAILABLE", "reason": exc.code,
                "why": exc.reason}
    rid = store.record_turn(db, principal, "laura", out["text"], reply_to=owner_turn_id,
                            model_ref=out["model_ref"])
    return {"reply": {"id": rid, "role": "laura", "text": out["text"],
                      "model_ref": out["model_ref"]},
            "reply_status": "REPLIED", "why": REPLY_ENABLED}


def owner_turn(db, session_public_id: str, text: str) -> dict:
    """Record what the owner typed; Laura replies only when the owner has enabled it.

    W4-LAURAONE: with the unified thread switched on, this split route is closed (409
    UNIFIED_THREAD) so no second, disconnected conversation can grow beside the one thread."""
    from ...gateway import laura_unified
    from ...laura.private import store

    if laura_unified.enabled():
        raise PrivateUnavailable(409, "UNIFIED_THREAD", "UnifiedThreadActive")

    def run():
        p = _principal(db, session_public_id)
        text_ = str(text or "")
        tid = store.record_turn(db, p, "owner", text_)
        return {"id": tid, **_laura_reply(db, p, tid, text_)}
    return _call(run)


def forget(db, session_public_id: str, record_id: str) -> dict:
    from ...laura.private import store

    return _call(lambda: {"deleted": store.forget(db, _principal(db, session_public_id),
                                                  str(record_id or ""))})


# ---------------------------------------------------------------------------
# W4-LAURAONE: one Laura, one thread (owner requirement 2026-10-20, D-W4-LAURA-UNIFIED,
# spec/13 ADD-LCONT-01..10; research/final_build/w4/LAURAONE.md).
#
# Every turn, whatever its subject, is recorded in THIS encrypted store with a sealed topic
# label. Private and everyday turns are answered through the ONE existing private reply path
# (`_unified_venice` -> `laura_register.reply`: Venice, `laura_private` budget, the pinned
# prompt unchanged). Business turns become a brief that holds only the business question; a
# deterministic leak guard (`gateway.laura_unified.leak_check`) compares the brief, and then the
# exact outbound request, against every private turn and note, and refuses on any hit. Business
# Laura (`laura.agency.ceo_chat.converse`: Claude, `laura` budget) answers the brief; the
# business side records only the brief and its result. A mixed turn, or a brief the guard stops,
# becomes an in-thread question showing the exact text that would cross; only the owner's
# approval (with a fresh step-up, enforced by the route) releases exactly that text, recorded in
# `laura_boundary_crossings` with nothing else. Off by default: `BRAMBLELOOP_LAURA_UNIFIED`.

UNIFIED_CONTEXT_SCAN = 120          # turns read to build Venice's context (then filtered)
UNIFIED_VIEW_TURNS = 200
UNIFIED_MAX_IDS = 200
UNIFIED_APPROVAL_TEXT = ("(Owner action: approved sharing the quoted text with the business "
                         "side.)")
UNIFIED_CONTROLS = ("mark_private", "exclude", "include", "forget")
#: The business side's conversation key for the one thread: business history (briefs and
#: results only) follows the THREAD, not the owner's login session, so it survives restarts
#: and new sessions like the thread itself does.
UNIFIED_BUSINESS_SESSION = "laura-unified-thread"


def _unified_required() -> None:
    from ...gateway import laura_unified

    if not laura_unified.enabled():
        raise PrivateUnavailable(404, "UNIFIED_OFF", "UnifiedThreadOff")


def unified_status(db, session_public_id: str) -> dict:
    """Non-content status of the one thread: switches, prerequisites, budgets (names only)."""
    from ...gateway import laura_register, laura_unified

    base = status(db, session_public_id)
    on = laura_unified.enabled()
    b2v = laura_unified.business_to_venice()
    prereq = [{"id": "unified_switch", "met": on,
               "label": f"unified thread switch {laura_unified.UNIFIED_ENV}=venice"},
              *base["prerequisites"]]
    return {"unified": laura_unified.mode() or "off",
            "business_to_venice": b2v,
            "business_to_venice_label": (
                f"{laura_unified.BUSINESS_TO_VENICE_ENV}=1: business briefs and validated "
                "answers enter Venice's context" if b2v else
                f"{laura_unified.BUSINESS_TO_VENICE_ENV} off: Venice sees a content-free "
                "placeholder for business exchanges"),
            "configured": base["configured"], "open": base["open"],
            "requires": base["requires"],
            "venice_replies": base["reply_register"],
            "budgets": {"conversation": f"{laura_register.AGENT} (Venice replies)",
                        "business": "laura (Business Laura via Claude)"},
            "prerequisites": prereq,
            "prerequisites_met": all(p["met"] for p in prereq),
            "isolation": base["isolation"]}


def _thread_row(r) -> dict:
    return {"id": r.record_id, "role": r.role, "label": r.label or "private",
            "excluded": bool(r.excluded), "sensitive": bool(r.sensitive),
            "reply_to": r.reply_to, "model_ref": r.model_ref,
            "at": (r.created_at.isoformat() if hasattr(r.created_at, "isoformat")
                   else (str(r.created_at) if r.created_at else None)),
            "text": r.value.reveal() if r.value is not None else None}


def unified_view(db, session_public_id: str, *, limit: int = UNIFIED_VIEW_TURNS) -> dict:
    """The one thread, revealed for the no-store response body only."""
    from ...gateway import laura_unified
    from ...laura.private import store

    _unified_required()

    def run():
        p = _principal(db, session_public_id)
        return {"unified": laura_unified.mode(),
                "business_to_venice": laura_unified.business_to_venice(),
                "turns": [_thread_row(r) for r in store.conversation(db, p, limit=limit)],
                "crossings": [{"id": x.record_id, "status": x.status,
                               "source": (x.sources or (None,))[0],
                               "sensitive": bool(x.sensitive),
                               "origin": x.origin, "requires_stepup": bool(x.stepup),
                               "text": x.value.reveal(),
                               "question": laura_unified.crossing_question(x.value.reveal())}
                              for x in store.crossings(db, p)],
                "notes": len(store.facts(db, p))}
    return _call(run)


def _private_texts(db, principal) -> list[str]:
    """Plain strings the leak guard compares against: EVERY retained non-business turn (owner
    and Laura; the whole store, not a window), every private note (key and text) and every
    crossing request not approved. Built here, used for one check, never stored or logged."""
    from ...laura.private import store

    out: list[str] = []
    for r in store.conversation(db, principal, limit=None):
        if (r.label or "private") != "business":
            out.append(r.value.reveal())
    for f in store.facts(db, principal, history=True):
        out.append(f.value.reveal())
        if f.key is not None:
            out.append(f.key.reveal())
    for x in store.crossings(db, principal):
        if x.status != "approved":
            out.append(x.value.reveal())
    return out


FEED_NOTE_KEY = "Company context (allowlisted business feed; not the owner's notes)"


def _venice_context(db, principal, owner_turn_id: str, *, with_feed: bool = False):
    """(notes, turns, pack) Venice may see for continuity: non-excluded turns, every business
    exchange as a content-free placeholder, and -- only with the owner's switch
    BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE=1 -- the restricted, allowlisted company-context
    pack (`laura.agency.venice_context`). Nothing else about the company reaches Venice."""
    from ...gateway import laura_unified
    from ...laura.agency import venice_context
    from ...laura.private import store

    facts = [(r.key.reveal() if r.key is not None else "", r.value.reveal())
             for r in store.facts(db, principal)[:CONTEXT_FACTS]]
    turns: list[tuple[str, str]] = []
    for r in store.conversation(db, principal, limit=UNIFIED_CONTEXT_SCAN):
        if r.record_id == owner_turn_id or r.excluded:
            continue
        if (r.label or "private") == "business":
            if r.role == "owner":
                turns.append(("laura", laura_unified.BUSINESS_PLACEHOLDER))
            continue
        turns.append((r.role, r.value.reveal()))
    pack = None
    if with_feed and venice_context.enabled():
        pack = venice_context.build(db)
        facts = [(FEED_NOTE_KEY, pack["text"]), *facts]
    return facts, turns[-CONTEXT_TURNS:], pack


def _venice_selected() -> bool:
    from ...gateway import laura_register, venice

    return laura_register.enablement().get("provider") == venice.PROVIDER_VALUE


def _laura_intent(db, principal, owner_turn_id: str, text: str, cls: dict) -> tuple[dict, str]:
    """Laura (Venice) decides whether a business tool is needed. When her router cannot be
    reached, code decides (business-classified turns only) -- and says so."""
    from ...gateway import laura_register, laura_unified

    if not (laura_register.enablement()["register_switch"] and _venice_selected()):
        return laura_unified.code_intent(cls), "code"
    _, turns, _ = _venice_context(db, principal, owner_turn_id)
    user = laura_unified.render_intent_user(turns=turns, message=text)
    try:
        out = laura_register.reply(db, system=laura_unified.INTENT.system, user=user,
                                   prompt=laura_unified.INTENT)
    except laura_register.ReplyUnavailable as exc:
        return laura_unified.code_intent(cls), f"code (Laura's router: {exc.code})"
    return out["text"], "laura"


def _unified_venice(db, principal, owner_turn_id: str, text: str, label: str) -> dict:
    """Laura's reply through the ONE private reply path (Venice; `laura_private` budget).
    Venice only: the thread is never forwarded to any other provider."""
    from ...gateway import laura_register
    from ...laura.agency import venice_context
    from ...laura.private import store

    if not laura_register.enablement()["register_switch"]:
        return {"reply": None, "reply_status": "UNAVAILABLE", "reason": "REGISTER_OFF",
                "why": laura_register.REASONS["REGISTER_OFF"]}
    if not _venice_selected():
        return {"reply": None, "reply_status": "UNAVAILABLE", "reason": "UNIFIED_NEEDS_VENICE",
                "why": laura_register.REASONS["UNIFIED_NEEDS_VENICE"]}
    facts, turns, pack = _venice_context(db, principal, owner_turn_id, with_feed=True)
    user = laura_register.render_user(facts=facts, turns=turns, message=text)
    if pack is not None:
        venice_context.record_sent(db, pack)      # hash, names, counts -- never a value
    try:
        out = laura_register.reply(db, system=laura_register.PROMPT.system, user=user)
    except laura_register.ReplyUnavailable as exc:
        return {"reply": None, "reply_status": "UNAVAILABLE", "reason": exc.code,
                "why": exc.reason}
    rid = store.record_turn(db, principal, "laura", out["text"], reply_to=owner_turn_id,
                            model_ref=out["model_ref"], label=label)
    return {"reply": {"id": rid, "role": "laura", "text": out["text"],
                      "model_ref": out["model_ref"], "side": "conversation",
                      "feed": ({"sha256": pack["sha256"], "fields": pack["fields"]}
                               if pack else None)},
            "reply_status": "REPLIED"}


def _request_crossing(db, principal, source_turn_id: str, offer: dict,
                      sensitive: bool) -> dict:
    from ...gateway import laura_unified
    from ...laura.private import store

    from ...laura.agency import boundary

    # Defence in depth: a one-tap offer whose text overlaps the private conversation (the leak
    # guard) is upgraded to need a fresh step-up, and the owner is told why.
    overlaps = bool(laura_unified.leak_check(offer["text"], _private_texts(db, principal),
                                             allowed=boundary.approved_texts(db)))
    stepup = bool(offer["stepup"]) or overlaps
    xid = store.request_crossing(db, principal, source_turn_id, offer["text"],
                                 sensitive=sensitive, origin=offer["origin"], stepup=stepup)
    return {"id": xid, "status": "pending", "sensitive": bool(sensitive),
            "text": offer["text"], "origin": offer["origin"],
            "requires_stepup": stepup, "overlaps_private": overlaps,
            "question": laura_unified.crossing_question(offer["text"])}


def _unified_business(db, principal, owner_turn_id: str, brief: str,
                      *, provider_factory=None) -> dict:
    """Business Laura answers `brief` -- a code-rendered structured request, or text the owner
    explicitly approved -- or nothing is sent. Defence in depth: the leak guard checks the
    brief and then the exact outbound request against the whole private store."""
    from ...gateway import laura_unified
    from ...laura.agency import boundary, ceo_chat
    from ...laura.private import store

    private_texts = _private_texts(db, principal)
    allowed = boundary.approved_texts(db)
    if laura_unified.leak_check(brief, private_texts, allowed=allowed):
        return {"reply": None, "reply_status": "REFUSED", "reason": "LEAK_GUARD",
                "why": laura_unified.GUARD_REFUSED}

    def outbound(task, system, user):
        hits = laura_unified.leak_check(user, private_texts, allowed=allowed)
        return laura_unified.GUARD_REFUSED if hits else ""

    res = ceo_chat.converse(db, brief, session_public_id=UNIFIED_BUSINESS_SESSION,
                            provider_factory=provider_factory, outbound_check=outbound,
                            allow_memory=False)
    if res["status"] == ceo_chat.REFUSED:
        return {"reply": None, "reply_status": "REFUSED", "reason": "LEAK_GUARD",
                "why": res["answer"]}
    model = (res.get("model") or {}).get("model") or "none"
    rid = store.record_turn(db, principal, "laura", res["answer"], reply_to=owner_turn_id,
                            model_ref=f"business/{model}"[:120], label="business",
                            business_ref=res.get("turn_id"))
    return {"reply": {"id": rid, "role": "laura", "text": res["answer"], "side": "business",
                      "status": res["status"], "business_turn_id": res.get("turn_id"),
                      "brief": brief,
                      "facts": res.get("facts") or [], "sources": res.get("sources") or [],
                      "unknowns": res.get("unknowns") or [],
                      "proposals": res.get("proposals") or [],
                      "model_ref": f"business/{model}"[:120]},
            "reply_status": ("REPLIED" if res["status"] in ("ANSWERED", "PARTIAL")
                             else res["status"])}


def unified_turn(db, session_public_id: str, text: str, *, force_private: bool = False,
                 provider_factory=None) -> dict:
    """One owner turn in the one thread. Laura's intent (Venice) decides whether a business
    tool is used. Code sends only a STRUCTURED request (tool + allowlisted parameters, rendered
    by code); any free text -- the owner's own words included -- is only offered, and crosses
    on the owner's explicit approval. `provider_factory` is the business model transport
    (tests inject one; production passes None)."""
    from ...gateway import laura_unified
    from ...laura.agency import boundary
    from ...laura.private import store

    _unified_required()

    def run():
        p = _principal(db, session_public_id)
        text_ = str(text or "")
        cls = laura_unified.classify(text_, force_private=bool(force_private))
        label = cls["label"]
        tid = store.record_turn(db, p, "owner", text_, label=label,
                                sensitive=cls["sensitive"])
        if force_private:
            intent, routed = {"tool": "none", "brief": ""}, "owner (kept private)"
        else:
            intent, routed = _laura_intent(db, p, tid, text_, cls)
        plan = laura_unified.plan_brief(intent, cls, text_,
                                        product_slugs=boundary.product_slugs(db))
        out: dict = {"id": tid, "label": label, "sensitive": cls["sensitive"],
                     "intent": {"tool": intent.get("tool", "none"), "routed_by": routed,
                                "params": plan["params"]}}
        if plan["send"]:
            out.update(_unified_business(db, p, tid, plan["send"],
                                         provider_factory=provider_factory))
            out["brief_origin"] = "structured"
        else:
            out.update(_unified_venice(db, p, tid, text_, label))
        if plan["offer"]:
            out["crossing"] = _request_crossing(db, p, tid, plan["offer"], cls["sensitive"])
        return out
    return _call(run)


def unified_crossing(db, session_public_id: str, crossing_id: str, *, approve: bool,
                     stepped_up: bool = False, provider_factory=None) -> dict:
    """The owner's answer to "Can I share this with the business side?". Approving needs a
    fresh step-up unless the text is the owner's own business-classified words (one explicit
    tap). Approval records exactly that text (`laura_boundary_crossings`), then Business Laura
    answers it -- still through the leak guard, with it allowed."""
    from ...laura.agency import boundary
    from ...laura.private import store

    _unified_required()

    def run():
        p = _principal(db, session_public_id)
        xid = str(crossing_id or "")
        cur = next((x for x in store.crossings(db, p) if x.record_id == xid), None)
        if cur is None:
            raise PrivateUnavailable(404, "CROSSING_NOT_FOUND", "CrossingNotFound")
        if approve and cur.stepup and not stepped_up:
            raise PrivateUnavailable(403, "STEP_UP_REQUIRED", "StepUpRequired")
        rec = store.resolve_crossing(db, p, xid, approve=bool(approve))
        if not approve:
            return {"id": rec.record_id, "status": "declined", "crossed": False}
        text_ = rec.value.reveal()
        crossed = boundary.record(db, text_, session_public_id=session_public_id)
        atid = store.record_turn(db, p, "owner", UNIFIED_APPROVAL_TEXT, label="business")
        out = {"id": rec.record_id, "status": "approved", "crossed": True,
               "crossing_record": crossed["id"], "approval_turn": atid}
        out.update(_unified_business(db, p, atid, text_, provider_factory=provider_factory))
        refs = {"crossed_ref": crossed["id"], "approval_turn": atid}
        if (out.get("reply") or {}).get("business_turn_id"):
            refs["business_ref"] = out["reply"]["business_turn_id"]
        store.annotate_crossing(db, p, xid, **refs)
        return out
    return _call(run)


def _derived_business_records(db, principal, ids: list[str]) -> tuple[set, set]:
    """Business rows derived from these owner turns: the business turn behind each reply, and
    every approved crossing (and its business turn) that quoted them."""
    from ...laura.private import store

    turns = store.conversation(db, principal, limit=None)
    by_reply = {r.reply_to: r for r in turns if r.reply_to}
    biz, xs = set(), set()
    for i in ids:
        r = by_reply.get(i)
        if r is not None and (r.refs or {}).get("business_ref"):
            biz.add(r.refs["business_ref"])
    for x in store.crossings(db, principal):
        if (x.sources or (None,))[0] in ids and x.status == "approved":
            refs = x.refs or {}
            if refs.get("crossed_ref"):
                xs.add(refs["crossed_ref"])
            if refs.get("business_ref"):
                biz.add(refs["business_ref"])
    return biz, xs


def unified_control(db, session_public_id: str, action: str, ids) -> dict:
    """The owner's privacy controls over a turn or a range of turns: mark private (which also
    REDACTS the business records already derived from them), exclude from model context,
    include again, or forget (real deletion). An owner turn's reply follows it."""
    from ...laura.agency import boundary
    from ...laura.private import store

    _unified_required()
    if action not in UNIFIED_CONTROLS:
        raise PrivateUnavailable(400, "PRIVATE_INPUT_REFUSED", "UnknownControl")
    if not isinstance(ids, list) or not ids or len(ids) > UNIFIED_MAX_IDS \
            or not all(isinstance(i, str) for i in ids):
        raise PrivateUnavailable(400, "PRIVATE_INPUT_REFUSED", "BadIds")

    def run():
        p = _principal(db, session_public_id)
        if action == "forget":
            return {"action": action,
                    "affected": sum(store.forget(db, p, i) for i in ids)}
        replies = {r.reply_to: r.record_id
                   for r in store.conversation(db, p, limit=None) if r.reply_to}
        targets = list(dict.fromkeys([*ids, *[replies[i] for i in ids if i in replies]]))
        kw = ({"label": "private"} if action == "mark_private"
              else {"excluded": action == "exclude"})
        out = {"action": action,
               "affected": sum(1 for i in targets if store.set_turn_flags(db, p, i, **kw))}
        if action == "mark_private":
            biz, xs = _derived_business_records(db, p, ids)
            out["redacted"] = boundary.redact(db, turn_ids=biz, crossing_ids=xs)
        return out
    return _call(run)
