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
  never a canned or templated private reply. Sexually explicit content is out of scope under
  the provider's usage policy and is not bypassed.

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
    """Record what the owner typed; Laura replies only when the owner has enabled it."""
    from ...laura.private import store

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
