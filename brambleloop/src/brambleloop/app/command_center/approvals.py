"""Evidence-backed approval inbox (F-885) and one-tap owner actions (F-886).

The inbox is not a second queue. It is the existing single owner queue
(`build2.executor.approval_inbox`, which already merges executor gates with `OwnerAction`
rows) re-shaped into the F-885 card, plus the protected-authority candidates the launch packet
already evaluates (`ops.publication_authority.evidence`).

Executing an action never bypasses an authority mechanism: each action calls the *same*
function the operator-token route calls (`publication_authority.approve`,
`activation_authority.approve`, `cells.record_owner_approval`, `league.record_owner_decision`),
with the server-held operator credential, on behalf of an owner session that has passed
session + CSRF + nonce + step-up checks. The grant that results is the existing sealed,
chained, expiring, revocable grant and is re-validated at the execution boundary, so a
revocation recorded before execution makes the protected action refuse (§95).
"""
from __future__ import annotations

import os

from sqlalchemy import select

from ...core import opsauth
from ...core.models import AuditLog, Incident, OwnerAction

# action -> (requires step-up, description)
ACTIONS: dict[str, tuple[bool, str]] = {
    "publication.preview": (False, "read the exact content and evidence a grant would bind"),
    "publication.approve": (True, "record a sealed 24 h owner publication grant"),
    "publication.revoke": (False, "revoke a publication grant (tightens)"),
    "activation.preview": (False, "read the exact content an activation grant would bind"),
    "activation.approve": (True, "record a sealed 24 h owner activation grant"),
    "activation.revoke": (False, "revoke an activation grant (tightens)"),
    "improvement.approve": (True, "record the owner's approval of a gate-tier improvement"),
    "challenger.approve": (True, "record the owner's decision to promote a challenger"),
    "incident.acknowledge": (False, "acknowledge an incident (does not resolve it)"),
    "owner_action.defer": (False, "note that a decision is deferred (the gate stays computed)"),
}


class ActionRefused(ValueError):
    """The underlying authority (or input validation) refused; message says why."""


def _ops_token() -> str:
    if not opsauth.configured():
        raise ActionRefused("operator credential not configured")
    return os.environ[opsauth.TOKEN_VAR].strip()


def _ev(label, state, why, source) -> dict:
    return {"label": label, "state": state, "why": str(why or "")[:400], "source": source}


def _gate_card(c: dict) -> dict:
    key = c.get("gate")
    oa = c.get("owner_action_id")
    card_id = f"gate:{key}" if key else f"owner_action:{oa}"
    rk = str(c.get("requirement_key") or "")
    actions = []
    reason = None
    kind = "GATE" if key else "OWNER-DECISION"
    if rk.startswith("improve.upgrade:") and rk.split(":", 1)[1].isdigit():
        kind = "IMPROVEMENT"
        actions.append({"action": "improvement.approve", "requires_step_up": True,
                        "params": {"id": int(rk.split(":", 1)[1])}})
    elif rk.startswith("improve.league:") and rk.split(":", 1)[1].isdigit():
        kind = "CHALLENGER"
        actions.append({"action": "challenger.approve", "requires_step_up": True,
                        "params": {"id": int(rk.split(":", 1)[1])}})
    else:
        reason = ("completed outside this app (an account, purchase or credential at the "
                  "provider); the gate re-checks reality and closes this card itself: "
                  + str(c.get("how_it_is_checked") or "")[:300])
    if oa:
        actions.append({"action": "owner_action.defer", "requires_step_up": False,
                        "params": {"owner_action_id": oa}})
    sources = ["build2.executor.approval_inbox"]
    sources += [f"owner_actions:{i}" for i in (c.get("merged_owner_action_ids") or [])]
    unblocks = c.get("unblocks_count") or 0
    max_spend = c.get("max_spend_cad")
    return {
        "card_id": card_id, "kind": kind, "title": c.get("what") or c.get("action"),
        "proposed_action": c.get("action"),
        "recommendation": (f"Recommended when convenient: it un-parks {unblocks} parked "
                           f"requirement(s); nothing else waits on it" if unblocks else
                           "No requirement is parked on this; low priority"),
        "evidence": [_ev("gate check", "FAIL" if key else "OPEN",
                         c.get("evidence") or c.get("how_it_is_checked"),
                         f"executor gate {key}" if key else f"owner_actions:{oa}")],
        "uncertainty": c.get("risk") or "not described",
        "expected_benefit": c.get("capability_unlocked") or "",
        "downside": c.get("risk") or "not described",
        "max_spend_cad": (float(max_spend) if isinstance(max_spend, (int, float)) else None),
        "monthly_ceiling_cad": c.get("monthly_ceiling_cad"),
        "minutes": c.get("minutes"),
        "reversibility": c.get("rollback") or "not described",
        "deadline": None,
        "consequence_of_no_action": c.get("consequence_of_waiting") or "not stated",
        "continues_regardless": c.get("continues_regardless"),
        "unblocks": c.get("unblocks") or [],
        "executable": any(a["action"] != "owner_action.defer" for a in actions),
        "actions": actions, "not_executable_reason": reason,
        "sources": sources,
    }


def _publication_cards(db, limit: int = 20) -> list[dict]:
    """Certified releases with a stored listing and no live grant: publication candidates."""
    from ...core.models import Listing, PatternVersion, Product
    from ...ops import publication_authority as pa

    out = []
    with db.session() as s:
        rows = list(s.execute(
            select(Product.slug, PatternVersion.version, PatternVersion.release_hash,
                   PatternVersion.id, Listing.id, Listing.state)
            .join(PatternVersion, PatternVersion.product_id == Product.id)
            .join(Listing, (Listing.product_slug == Product.slug)
                  & (Listing.version == PatternVersion.version))
            .where(PatternVersion.certified == True)  # noqa: E712
            .order_by(PatternVersion.id.desc()).limit(limit)))
    seen = set()
    for slug, version, release, pv_id, listing_id, listing_state in rows:
        if (slug, version) in seen or listing_state == "active":
            continue
        seen.add((slug, version))
        try:
            ev = pa.evidence(db, slug, version, release or "")
        except Exception as exc:  # noqa: BLE001
            ev = {"summary": {"all_gated_sections_pass": False,
                              "not_passing": list(pa.GATED_SECTIONS)},
                  **{k: {"state": "UNKNOWN", "why": f"unreadable: {type(exc).__name__}"}
                     for k in pa.GATED_SECTIONS + ("economics",)}}
        display = pa.display(ev)
        ready = bool(ev["summary"]["all_gated_sections_pass"])
        econ = ev.get("economics") or {}
        out.append({
            "card_id": f"publication:{slug}@{version}", "kind": "PUBLICATION",
            "title": f"Create the Etsy draft for {slug} v{version}",
            "proposed_action": ("record a sealed 24 h publication grant bound to this exact "
                                "certified release and listing content"),
            "recommendation": ("Ready: every gated section passes" if ready else
                               "Not ready: " + ", ".join(ev["summary"]["not_passing"])
                               + " not passing"),
            "evidence": [_ev(r["section"], r["state"], r["why"],
                             f"ops.publication_authority.evidence[{r['section']}]")
                         for r in display],
            "uncertainty": ("UNKNOWN sections: " + ", ".join(ev["summary"].get("unknown") or [])
                            if ev["summary"].get("unknown") else "none reported"),
            "expected_benefit": "the product can be drafted on Etsy (still inactive)",
            "downside": "a draft listing exists on Etsy; activation is a separate grant",
            "max_spend_cad": None,
            "economics": {"state": econ.get("state", "UNKNOWN"), "why": econ.get("why", "")},
            "reversibility": "the grant is revocable until used; the draft can be deleted",
            "deadline": None,
            "consequence_of_no_action": "the release stays unpublished; nothing else waits",
            "executable": ready,
            "actions": ([{"action": "publication.preview", "requires_step_up": False,
                          "params": {"slug": slug, "version": version,
                                     "release": release or ""}},
                         {"action": "publication.approve", "requires_step_up": True,
                          "params": {"slug": slug, "version": version,
                                     "release": release or "",
                                     "expected_digest": "<from publication.preview>"}}]
                        if ready else []),
            "not_executable_reason": (None if ready else
                                      "gated sections do not all pass (Product Truth first)"),
            "sources": [f"pattern_versions:{pv_id}", f"listings:{listing_id}",
                        "ops.publication_authority.evidence"]})
    return out


def inbox(db) -> dict:
    from . import readers

    try:
        raw = readers.owner_inbox(db)
        cards = [_gate_card(c) for c in raw.get("cards") or []]
        status, reason = "OK", None
    except Exception as exc:  # noqa: BLE001
        raw, cards = {}, []
        status, reason = "UNKNOWN", f"owner queue unreadable: {type(exc).__name__}"
    try:
        pub = _publication_cards(db)
    except Exception as exc:  # noqa: BLE001
        pub = []
        reason = (reason + "; " if reason else "") + (
            f"publication candidates unreadable: {type(exc).__name__}")
        status = "DEGRADED" if status == "OK" else status
    cards = cards + pub
    return {"status": status, "reason": reason, "cards": cards, "open": len(cards),
            "waiting_on_data": raw.get("waiting_on_data") or [],
            "external_capability_unavailable": raw.get("external_capability_unavailable")
            or [],
            "note": raw.get("note"),
            "sources": ["build2.executor.approval_inbox", "owner_actions",
                        "ops.publication_authority.evidence"]}


def card(db, card_id: str) -> dict | None:
    for c in inbox(db)["cards"]:
        if c["card_id"] == card_id:
            return c
    return None


def _audit(db, actor: str, action: str, artifact: str, detail: dict) -> int:
    with db.session() as s:
        row = AuditLog(actor=actor[:64], action=action[:80], artifact=artifact[:200],
                       detail=detail)
        s.add(row)
        s.flush()
        return row.id


def execute(db, action: str, body: dict, *, actor: str) -> dict:
    """Run one owner action through its existing mechanism. Raises ActionRefused."""
    from ...ops import activation_authority as act
    from ...ops import publication_authority as pub

    if action not in ACTIONS:
        raise ActionRefused(f"unknown action {action!r}")
    body = body if isinstance(body, dict) else {}
    reason = str(body.get("reason") or "").strip()
    tagged = f"{reason} [owner via command center {actor}]" if reason else ""
    try:
        if action in ("publication.preview", "activation.preview"):
            mod = pub if action.startswith("publication") else act
            content = mod.snapshot(db, body.get("slug"), body.get("version"),
                                   body.get("release", ""))
            out = {"content": content, "digest": mod.digest(content)}
            if mod is pub:
                ev = pub.evidence(db, body.get("slug"), body.get("version"),
                                  body.get("release", ""))
                out["display"] = pub.display(ev)
            return {"result": out, "audit_id": None}  # a read: nothing to audit
        if action in ("publication.approve", "activation.approve"):
            mod = pub if action.startswith("publication") else act
            if not reason:
                raise ActionRefused("owner decision reason required")
            kwargs = dict(authorization=_ops_token(), slug=body.get("slug"),
                          version=body.get("version"), release=body.get("release", ""),
                          expected_digest=body.get("expected_digest"), reason=tagged)
            result = mod.approve(db, **kwargs)
        elif action in ("publication.revoke", "activation.revoke"):
            mod = pub if action.startswith("publication") else act
            result = mod.revoke(db, authorization=_ops_token(),
                                approval_id=int(body.get("approval_id")))
        elif action == "improvement.approve":
            from ...improve import cells

            result = cells.record_owner_approval(db, int(body.get("id")), approved_by="owner",
                                                 why=str(body.get("why") or reason))
        elif action == "challenger.approve":
            from ...improve import league

            result = league.record_owner_decision(db, int(body.get("id")),
                                                  approved_by="owner",
                                                  why=str(body.get("why") or reason))
        elif action == "incident.acknowledge":
            iid = int(body.get("incident_id"))
            with db.session() as s:
                if s.get(Incident, iid) is None:
                    raise ActionRefused(f"no incident {iid}")
            result = {"acknowledged": iid, "resolved": False,
                      "note": str(body.get("note") or "")[:500]}
        elif action == "owner_action.defer":
            oid = int(body.get("owner_action_id"))
            with db.session() as s:
                if s.get(OwnerAction, oid) is None:
                    raise ActionRefused(f"no owner action {oid}")
            result = {"deferred": oid, "note": str(body.get("note") or "")[:500]}
        else:  # pragma: no cover - ACTIONS is exhaustive
            raise ActionRefused(action)
    except ActionRefused:
        raise
    except opsauth.OpsAuthUnavailable as exc:
        raise ActionRefused(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - the authority's refusal, verbatim
        name = type(exc).__name__
        if name in ("ValueError", "KeyError", "TypeError", "ImprovementRefused",
                    "LeagueRefused", "PermissionError"):
            raise ActionRefused(str(exc)[:500] or name) from exc
        raise
    audit_id = _audit(db, actor, f"cc.owner_action.{action}",
                      str(body.get("slug") or body.get("id") or body.get("approval_id")
                          or body.get("incident_id") or body.get("owner_action_id") or ""),
                      {"action": action, "via": "command_center", "session": actor,
                       "reason": reason[:300],
                       "result": {k: v for k, v in (result or {}).items()
                                  if k in ("approval_id", "revoked", "digest", "expires_at",
                                           "improvement", "owner_approved", "acknowledged",
                                           "deferred")}})
    return {"result": result, "audit_id": audit_id}
