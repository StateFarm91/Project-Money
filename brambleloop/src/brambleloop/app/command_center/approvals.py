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

import logging
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
    # W4-B2GATES: two owner gates read a record that no door in the running system could
    # write, so they could never open. These are those doors; each records only.
    "acceptance.rule": (True, "record the owner's ruling on the API+vision acceptance wording"),
    "ads.set_limit": (True, "set the owner's ads SpendLimit (capped at the conservative caps)"),
    # W4-PRODFIX: `platform_policy.unreviewed_changes` blocks publishing (and the marketing
    # rebuild) until a material Etsy policy change is reviewed and re-tested, and nothing in
    # the running system could record that review (`review_change` had no caller). The
    # preview shows the change; the review records exactly what the owner confirmed.
    "policy.review_preview": (False, "read a material platform-policy change before review"),
    "policy.review": (True, "record the owner's review and re-test of a policy change"),
}

#: The words the owner confirms, verbatim. Anything else is refused.
POLICY_REVIEW_CONFIRMATION = "reviewed and tested"

#: The two answers the `acceptance_ruling` gate asks for (#189/#221/#222/#320). Either opens
#: the gate: what changes is which remaining work the rows hold.
ACCEPTANCE_RULINGS = {
    "api_vision_satisfies": ("an API+vision traversal satisfies the browser/vision wording"),
    "browser_required": ("a rendered-browser traversal is required; API+vision does not "
                         "satisfy the wording"),
}


class ActionRefused(ValueError):
    """The underlying authority (or input validation) refused; message says why.

    The message is owner-facing and stable; `detail` (raw exception text, if any) goes only to
    the server log and the security-event audit row, never to the response (audit L3)."""

    def __init__(self, message: str, *, detail: dict | None = None):
        super().__init__(message)
        self.detail = detail


class ActionNotFound(ActionRefused):
    """The thing the action names does not exist (HTTP 404)."""


log = logging.getLogger("brambleloop.cc.approvals")

# Refusal texts the authorities raise deliberately; these reach the owner verbatim. Any other
# exception text (e.g. "invalid literal for int()") is replaced by a stable message.
_AUTHORITY_MESSAGES = (
    "owner decision reason required",
    "approval preview changed; review the current content",
    "slug, version and certified release hash are required",
    "no certified release with that hash for this version",
    "no drafted listing bound to that certified release",
    "already on Etsy; publication grants cover draft creation only",
    "no inactive recorded listing/release",
    "certified frames and verified publication files required",
    "owner credential unavailable",
)
_AUTHORITY_PREFIXES = ("the owner publication grant chain does not verify",
                       "the owner activation approval chain does not verify")


def _owner_message(exc: Exception) -> str:
    text = str(exc).strip()
    if type(exc).__name__ in ("ImprovementRefused", "LeagueRefused"):
        return text[:500] or "refused by the improvement authority"
    if text in _AUTHORITY_MESSAGES or text.startswith(_AUTHORITY_PREFIXES):
        return text[:500]
    return "refused: the request was malformed or named something that is not valid"


def _int(body: dict, key: str) -> int:
    value = body.get(key)
    if isinstance(value, bool):
        raise ActionRefused(f"{key} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        raise ActionRefused(f"{key} must be an integer") from None


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
    if key in ("acceptance_ruling", "ad_authority"):
        reason = ("recorded here by the owner (step-up); the gate re-checks the record: "
                  + str(c.get("how_it_is_checked") or "")[:300])
    if key == "acceptance_ruling":
        for ruling, text in ACCEPTANCE_RULINGS.items():
            actions.append({"action": "acceptance.rule", "requires_step_up": True,
                            "label": "Rule: " + text.split(";")[0], "params": {"ruling": ruling}})
    elif key == "ad_authority":
        from ...commerce.paid_media import CONSERVATIVE_CAPS as _caps

        actions.append({"action": "ads.set_limit", "requires_step_up": True,
                        "label": (f"Set ads limit CA${_caps.daily_cad:.2f}/day, "
                                  f"CA${_caps.campaign_cad:.2f} lifetime"),
                        "params": {"daily_cap_cad": _caps.daily_cad,
                                   "lifetime_cap_cad": _caps.campaign_cad}})
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
        # F-870 / F-623 / F-197 / F-180 (K7): the packet, the rank and the tester route.
        "why_software_cannot": c.get("why_software_cannot"),
        "requirement_kind": c.get("requirement_kind"),
        "packet_missing": c.get("packet_missing") or [],
        "rank": c.get("rank"), "urgency": c.get("urgency"),
        "steps": c.get("steps"), "state": c.get("state"),
        **({"tester_route": c["tester_route"]} if c.get("tester_route") else {}),
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
    # W4-PRODFIX: each unreviewed material policy change is a card (it blocks publishing).
    try:
        from ...gates import platform_policy

        cards = cards + [{
            "card_id": f"policy:{c['source']}", "kind": "policy_review",
            "title": f"Etsy policy changed: {c['source']}",
            "what": (f"{c['source']} changed materially (reading {c['checked_on']}); "
                     f"{', '.join(c['affects'])} are blocked until it is reviewed and "
                     f"re-tested"),
            "executable": True,
            "actions": [{"action": "policy.review_preview", "requires_step_up": False,
                         "params": {"source": c["source"]}},
                        {"action": "policy.review", "requires_step_up": True,
                         "params": {"source": c["source"],
                                    "confirm": POLICY_REVIEW_CONFIRMATION,
                                    "tested": "<what you re-tested>",
                                    "expected_digest": "<from policy.review_preview>"}}],
            "sources": [f"policy_snapshots:{c['snapshot_id']}"]}
            for c in platform_policy.unreviewed_changes(db)]
    except Exception as exc:  # noqa: BLE001
        reason = (reason + "; " if reason else "") + (
            f"policy changes unreadable: {type(exc).__name__}")
        status = "DEGRADED" if status == "OK" else status
    # W4-CCREL: the release approval card. The deploy decision (gate production_window)
    # carries the candidate SHA, suite result, security review and rollback target; with no
    # deploy decision open, a pending candidate gets its own read-only card.
    from . import release_card as release_mod

    try:
        rc = release_mod.candidate()
    except Exception as exc:  # noqa: BLE001 - unreadable release evidence is UNKNOWN
        rc = {"pending": False, "why": f"release evidence unreadable: {type(exc).__name__}"}
    deploy = next((c for c in cards if c.get("card_id") == f"gate:{release_mod.DEPLOY_GATE}"),
                  None)
    if rc.get("pending") and deploy is not None:
        deploy.update(release_mod.card_fields(rc))
        deploy["evidence"] = list(deploy.get("evidence") or []) + release_mod.evidence(rc)
        deploy["sources"] = list(deploy.get("sources") or []) + [rc["record"]]
    elif rc.get("pending"):
        cards = cards + [release_mod.standalone_card(rc)]
    from . import company as company_mod
    from .providers import guard

    batches = guard("decision_batches", lambda: company_mod.owner_decision_batches(raw))
    return {"status": status, "reason": reason, "cards": cards, "open": len(cards),
            "release": release_mod.envelope_for(rc),
            # W4-OWNER: the consolidated decision packet, batch first.
            "decision_batches": batches,
            # F-204 (K7): an empty queue is proven only by a fresh assessment + live gates.
            "empty_state": raw.get("empty_state"),
            "parked_owner_actions": raw.get("parked_owner_actions") or [],
            "waiting_on_data": raw.get("waiting_on_data") or [],
            "external_capability_unavailable": raw.get("external_capability_unavailable")
            or [],
            # W4-GATESB: decisions the owner cannot usefully answer yet, each with what makes
            # it askable. `customers` is data, never an owner card.
            "not_yet_askable": _not_yet_askable(raw),
            "note": raw.get("note"),
            "sources": ["build2.executor.approval_inbox", "owner_actions",
                        "ops.publication_authority.evidence"]}


NEVER_OWNER_CARD = frozenset({"customers"})


def _not_yet_askable(raw: dict) -> dict:
    items = raw.get("not_yet_askable") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return {"status": "UNKNOWN", "items": [], "basis": "unknown",
                "reason": "this build's approval inbox does not report not-yet-askable "
                          "decisions", "sources": ["build2.executor.approval_inbox"]}
    out = []
    for it in items:
        if not isinstance(it, dict) or it.get("gate") in NEVER_OWNER_CARD:
            continue
        pre = it.get("precondition")
        out.append({"gate": it.get("gate"), "what": it.get("what"),
                    "askable_when": (pre if isinstance(pre, str) else
                                     (pre or {}).get("what") or (pre or {}).get("why")
                                     if isinstance(pre, dict) else None) or "UNKNOWN",
                    "precondition": pre, "unblocks_count": len(it.get("unblocks") or []),
                    "owner_action_ids": it.get("owner_action_ids") or []})
    return {"status": "OK", "items": out, "basis": "measured",
            "sources": ["build2.executor.approval_inbox", "build2.gate_clearance.prerequisite"]}


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


def _require_publication_evidence(db, body: dict) -> None:
    """Server-side evidence gate for publication.approve (audit ddf9c6e L1).

    The inbox card is only `executable` when every gated section of the approval packet
    passes; the server enforces the same rule rather than trusting the UI. FAIL and UNKNOWN
    both refuse (UNKNOWN is never PASS); an unreadable packet refuses."""
    from ...ops import publication_authority as pub

    try:
        ev = pub.evidence(db, body.get("slug"), body.get("version"), body.get("release", ""))
        summary = ev["summary"]
        ready = summary.get("all_gated_sections_pass") is True
        not_passing = [str(x) for x in summary.get("not_passing") or []]
    except Exception as exc:  # noqa: BLE001 - fail closed
        log.info("publication evidence unreadable: %s: %s", type(exc).__name__, exc)
        raise ActionRefused("evidence not ready: the approval packet could not be read",
                            detail={"exception": type(exc).__name__}) from None
    if not ready:
        raise ActionRefused("evidence not ready: " + (", ".join(not_passing) or "unknown")
                            + " not passing; a publication grant needs every gated section "
                            "to pass (Product Truth first)",
                            detail={"not_passing": not_passing})


def _record_acceptance_ruling(db, ruling: str, reason: str, *, actor: str) -> dict:
    """The door the `acceptance_ruling` gate reads: a done OwnerAction under its key."""
    from ...build2 import executor
    from ...ops import owner_queue

    if ruling not in ACCEPTANCE_RULINGS:
        raise ActionRefused(f"ruling must be one of {sorted(ACCEPTANCE_RULINGS)}")
    if not reason:
        raise ActionRefused("owner decision reason required")
    with db.session() as s:
        row = OwnerAction(requirement_key=executor.ACCEPTANCE_RULING_KEY,
                          action=f"Acceptance ruling ({ruling}): {ACCEPTANCE_RULINGS[ruling]}",
                          reason=reason[:2000], max_cost_cad=0.0, minutes=2,
                          blocks="#189 #221 #222 #320")
        s.add(row)
        s.flush()
        owner_queue.transition(s, row, owner_queue.SATISFIED,
                               f"owner ruled {ruling}: {reason}"[:1000], actor=actor)
        oid = row.id
    return {"ruling": ruling, "owner_action_id": oid, "gate": "acceptance_ruling",
            "note": "the gate re-checks this record; the four rows un-park on its next read"}


def _set_ads_limit(db, body: dict, reason: str) -> dict:
    """The door the `ad_authority` gate reads: SpendLimit('ads'), never above the caps the
    code already enforces (commerce.paid_media.CONSERVATIVE_CAPS). Sets authority only:
    nothing is spent here, and SpendGuard still refuses any spend over the cap."""
    from ...agents.registry import SpendGuard
    from ...commerce.paid_media import CONSERVATIVE_CAPS as caps

    if not reason:
        raise ActionRefused("owner decision reason required")
    try:
        daily = float(body.get("daily_cap_cad"))
        lifetime = float(body.get("lifetime_cap_cad"))
    except (TypeError, ValueError):
        raise ActionRefused("daily_cap_cad and lifetime_cap_cad must be numbers") from None
    if not (0 < daily <= caps.daily_cad):
        raise ActionRefused(f"daily_cap_cad must be > 0 and <= CA${caps.daily_cad:.2f} "
                            "(the conservative cap enforced in code)")
    if not (daily <= lifetime <= caps.campaign_cad):
        raise ActionRefused(f"lifetime_cap_cad must be between the daily cap and "
                            f"CA${caps.campaign_cad:.2f}")
    SpendGuard(db).set_limit("ads", daily, lifetime)
    return {"scope": "ads", "daily_cap_cad": daily, "lifetime_cap_cad": lifetime,
            "spent": 0.0, "note": "authority only; nothing was spent"}


def _policy_change(db, source: str) -> dict:
    """The newest unreviewed material change of `source`, the reading before it, and the
    digest binding what the owner is shown (so a review cannot confirm text it never saw)."""
    import hashlib
    import json as _json

    from ...core.models import PolicySnapshot
    from ...gates import platform_policy

    pending = {c["source"]: c for c in platform_policy.unreviewed_changes(db)}
    if source not in pending:
        raise ActionNotFound(f"no unreviewed material change for policy source {source!r}")
    with db.session() as s:
        row = s.get(PolicySnapshot, pending[source]["snapshot_id"])
        before = s.scalars(select(PolicySnapshot).where(
            PolicySnapshot.source == source, PolicySnapshot.id < row.id)
            .order_by(PolicySnapshot.id.desc())).first()
        shown = {
            "source": source, "snapshot_id": row.id,
            "changed": {"version": row.version, "checked_on": row.checked_on,
                        "digest": row.digest, "summary": row.summary or "",
                        "url": row.url or "", "affects": list(pending[source]["affects"])},
            "before": ({"snapshot_id": before.id, "version": before.version,
                        "checked_on": before.checked_on, "digest": before.digest,
                        "summary": before.summary or ""} if before is not None else None),
        }
    shown["review_digest"] = hashlib.sha256(
        _json.dumps(shown, sort_keys=True, default=str).encode()).hexdigest()
    shown["confirm_with"] = POLICY_REVIEW_CONFIRMATION
    return shown


def _review_policy_change(db, body: dict, *, actor: str) -> dict:
    from ...gates import platform_policy

    source = str(body.get("source") or "").strip()
    shown = _policy_change(db, source)
    confirmed = str(body.get("confirm") or "").strip()
    tested = str(body.get("tested") or "").strip()
    if confirmed != POLICY_REVIEW_CONFIRMATION:          # verbatim (review F9)
        raise ActionRefused(f"confirm must be exactly {POLICY_REVIEW_CONFIRMATION!r}")
    if not tested:
        raise ActionRefused("tested must say what was re-tested against the changed policy")
    if body.get("expected_digest") != shown["review_digest"]:
        raise ActionRefused("approval preview changed; review the current content")
    try:
        out = platform_policy.review_change(db, source, reviewed_by="owner:command-center",
                                            tested=tested, snapshot_id=shown["snapshot_id"])
    except platform_policy.PolicyRefused as exc:
        if "newer change arrived" in str(exc):
            raise ActionRefused("approval preview changed; review the current content") \
                from None
        raise ActionRefused(str(exc)[:500]) from None
    record = {"source": source, "snapshot_id": shown["snapshot_id"],
              "confirmed": confirmed, "tested": tested[:2000],
              "review_digest": shown["review_digest"], "shown": shown, "session": actor,
              "reviewed_by": "owner:command-center"}
    audit_id = _audit(db, actor, "policy.change_reviewed", f"policy:{source}", record)
    return {**out, "review_audit_id": audit_id, "confirmed": confirmed}


def execute(db, action: str, body: dict, *, actor: str) -> dict:
    """Run one owner action through its existing mechanism. Raises ActionRefused."""
    from ...laura.private.firewall import reject_private

    # PRIV Step 4 (spec/07 Ruling 2): owner-private input never reaches this protected path.
    reject_private((action, body, actor), context="security")
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
            if mod is pub:
                _require_publication_evidence(db, body)
            kwargs = dict(authorization=_ops_token(), slug=body.get("slug"),
                          version=body.get("version"), release=body.get("release", ""),
                          expected_digest=body.get("expected_digest"), reason=tagged)
            result = mod.approve(db, **kwargs)
        elif action in ("publication.revoke", "activation.revoke"):
            mod = pub if action.startswith("publication") else act
            ident = _int(body, "approval_id")
            with db.session() as s:
                row = s.get(AuditLog, ident)
                is_grant = (row is not None and row.action == mod.APPROVED
                            and row.actor == mod.PRINCIPAL)
            if not is_grant:
                # Never seal a revocation for an id that is not a grant of this ledger: it
                # would report success for nothing and pre-revoke a future id (audit L2).
                raise ActionNotFound(f"no {action.split('.')[0]} grant {ident}")
            result = mod.revoke(db, authorization=_ops_token(), approval_id=ident)
        elif action == "improvement.approve":
            from ...improve import cells

            result = cells.record_owner_approval(db, _int(body, "id"), approved_by="owner",
                                                 why=str(body.get("why") or reason))
        elif action == "challenger.approve":
            from ...improve import league

            result = league.record_owner_decision(db, _int(body, "id"),
                                                  approved_by="owner",
                                                  why=str(body.get("why") or reason))
        elif action == "incident.acknowledge":
            iid = _int(body, "incident_id")
            with db.session() as s:
                if s.get(Incident, iid) is None:
                    raise ActionRefused(f"no incident {iid}")
            result = {"acknowledged": iid, "resolved": False,
                      "note": str(body.get("note") or "")[:500]}
        elif action == "owner_action.defer":
            oid = _int(body, "owner_action_id")
            with db.session() as s:
                row = s.get(OwnerAction, oid)
                if row is None:
                    raise ActionRefused(f"no owner action {oid}")
                # F-180 (K7): a deferral is the owner parking the action -- it leaves the
                # active queue with a timestamp and reason; the row and its history stay.
                from ...ops import owner_queue

                note = str(body.get("note") or "")[:500]
                if owner_queue.effective_state(row) == owner_queue.OPEN:
                    owner_queue.transition(s, row, owner_queue.PARKED,
                                           note or "deferred by the owner", actor=actor)
            result = {"deferred": oid, "note": note, "state": owner_queue.PARKED}
        elif action == "acceptance.rule":
            result = _record_acceptance_ruling(db, str(body.get("ruling") or ""), tagged,
                                               actor=actor)
        elif action == "ads.set_limit":
            result = _set_ads_limit(db, body, tagged)
        elif action == "policy.review_preview":
            return {"result": _policy_change(db, str(body.get("source") or "").strip()),
                    "audit_id": None}  # a read: nothing to audit
        elif action == "policy.review":
            result = _review_policy_change(db, body, actor=actor)
        else:  # pragma: no cover - ACTIONS is exhaustive
            raise ActionRefused(action)
    except ActionRefused:
        raise
    except opsauth.OpsAuthUnavailable as exc:
        raise ActionRefused("operator credential not configured",
                            detail={"exception": type(exc).__name__}) from exc
    except Exception as exc:  # noqa: BLE001 - the authority's refusal, mapped to stable text
        name = type(exc).__name__
        if name in ("ValueError", "KeyError", "TypeError", "ImprovementRefused",
                    "LeagueRefused", "PermissionError", "OpsAuthRefused"):
            raw = str(exc)[:500]
            log.info("command-center action %s refused: %s: %s", action, name, raw)
            raise ActionRefused(_owner_message(exc),
                                detail={"exception": name, "message": raw}) from exc
        raise
    audit_id = _audit(db, actor, f"cc.owner_action.{action}",
                      str(body.get("slug") or body.get("source") or body.get("id")
                          or body.get("approval_id")
                          or body.get("incident_id") or body.get("owner_action_id") or ""),
                      {"action": action, "via": "command_center", "session": actor,
                       "reason": reason[:300],
                       "result": {k: v for k, v in (result or {}).items()
                                  if k in ("approval_id", "revoked", "digest", "expires_at",
                                           "improvement", "owner_approved", "acknowledged",
                                           "deferred", "source", "snapshot_id",
                                           "reviewed", "review_audit_id", "confirmed")}})
    return {"result": result, "audit_id": audit_id}
