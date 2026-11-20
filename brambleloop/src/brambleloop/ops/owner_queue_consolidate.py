"""Owner-queue consolidation under the standing authority (ENG-APPROVALS, D-OWNER-STANDING-INTERNAL).

`sweep` is the idempotent, scheduled pass (`ops.owner_queue_consolidate`, hourly) that applies
`authority.standing_internal.classify` to every open or parked OwnerAction:

* ROUTINE_INTERNAL -> `superseded` by the standing authority (the work proceeds inside every
  existing gate and ceiling; nothing waits on the owner for it);
* AUTO_CLOSE       -> `satisfied`, `superseded` or `expired` by the rule's own reason
  (already satisfied, redundant with another surface, or stale);
* GENUINE_EXCEPTION -> never touched. It stays open for the owner's one batch.

Every move goes through `ops.owner_queue.transition` (its `owner_action.lifecycle` row, the
row itself kept) and writes one `owner_action.standing_authority` audit row citing the
directive. Nothing is deleted, signed, sealed, published, spent or messaged.

Idempotent by construction: a second sweep over the same rows finds nothing open that is not a
genuine exception and writes nothing. A producer that raises a routine card again gets a new
row (the guard keeps one open per key), which the next sweep closes with a new audit row.

`counts` reads the P0 board numbers: owner exceptions open, cards closed automatically and
routine operations auto-approved in the last 24 h.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..authority import standing_internal as SI

JOB_TYPE = "ops.owner_queue_consolidate"

# The AUTO_CLOSE classes and the lifecycle state each closes to.
SATISFIED_RULE = "already_satisfied"
REDUNDANT_RULE = "redundant"
STALE_RULE = "stale"
REDUNDANT_WITHDRAWN_RULE = "redundant_withdrawn"
AUTO_CLOSE_STATES = {SATISFIED_RULE: "satisfied", REDUNDANT_RULE: "superseded",
                     REDUNDANT_WITHDRAWN_RULE: "withdrawn", STALE_RULE: "expired"}


def _now(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def decide(row, verdict: dict, *, now: datetime) -> tuple[str, str] | None:
    """(state, reason) for a non-genuine row, or None to leave it. Never for a genuine one."""
    from . import owner_queue

    if verdict["disposition"] == SI.GENUINE_EXCEPTION:
        return None
    if verdict["disposition"] == SI.ROUTINE_INTERNAL:
        return (owner_queue.SUPERSEDED,
                f"covered by the owner's standing authority {SI.DIRECTIVE_ID} "
                f"({SI.DIRECTIVE_AT}): {verdict['why']}")
    rule = verdict["class"]
    if rule == STALE_RULE:
        last = max((t for t in (_aware(row.at), _aware(row.state_at)) if t is not None),
                   default=None)
        if last is not None and now - last < SI.STALE_AFTER:
            return None                    # not stale yet: leave it for a later sweep
        return (owner_queue.EXPIRED,
                f"stale ({SI.DIRECTIVE_ID}): not restated for {SI.STALE_AFTER.days} days; "
                f"{verdict['why']}")
    state = AUTO_CLOSE_STATES.get(rule)
    if state is None:
        return None                        # an AUTO_CLOSE rule with no state: fail closed
    return state, f"{rule.replace('_', ' ')} ({SI.DIRECTIVE_ID}): {verdict['why']}"


def sweep(db, *, now: datetime | None = None) -> dict:
    """Apply the standing authority to the owner queue once. Idempotent."""
    from sqlalchemy import select

    from ..core.models import AuditLog, OwnerAction
    from . import owner_queue

    now = _now(now)
    out = {"routine_superseded": [], "auto_closed": [], "genuine_open": [],
           "unclassified_open": [], "left_open": [], "at": now.isoformat(),
           "directive": SI.DIRECTIVE_ID}
    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(OwnerAction.done == False)  # noqa: E712
                              .order_by(OwnerAction.id)))
        for row in rows:
            state_now = owner_queue.effective_state(row)
            if state_now not in (owner_queue.OPEN, owner_queue.PARKED):
                continue
            verdict = SI.classify(row.requirement_key)
            if verdict["disposition"] == SI.GENUINE_EXCEPTION:
                out["genuine_open"].append(row.id)
                if verdict["class"] == SI.UNCLASSIFIED:
                    out["unclassified_open"].append(row.requirement_key or f"#{row.id}")
                continue
            decision = decide(row, verdict, now=now)
            if decision is None:
                out["left_open"].append(row.id)
                continue
            state, reason = decision
            moved = owner_queue.transition(s, row, state, reason, actor=SI.ACTOR, now=now)
            if not moved.get("changed"):
                continue
            s.add(AuditLog(actor=SI.ACTOR, action=SI.AUDIT_ACTION, at=now,
                           artifact=f"owner_action:{row.id}",
                           detail={"directive": SI.DIRECTIVE_ID,
                                   "directive_at": SI.DIRECTIVE_AT,
                                   "disposition": verdict["disposition"],
                                   "class": verdict["class"], "rule": verdict["rule"],
                                   "requirement_key": row.requirement_key,
                                   "from": moved.get("from"), "to": state,
                                   "reason": reason[:500], "at": now.isoformat()}))
            bucket = ("routine_superseded" if verdict["disposition"] == SI.ROUTINE_INTERNAL
                      else "auto_closed")
            out[bucket].append({"id": row.id, "requirement_key": row.requirement_key,
                                "to": state})
    out["closed"] = len(out["routine_superseded"]) + len(out["auto_closed"])
    return out


def _approves_nothing(detail: dict) -> bool:
    key = str(detail.get("requirement_key") or "")
    return key.startswith(SI.NO_APPROVAL_PREFIXES)


def counts(db, *, now: datetime | None = None) -> dict:
    """P0 board: owner exceptions open; closed automatically and routine auto-approved (24 h)."""
    from sqlalchemy import select

    from ..core.models import AuditLog, OwnerAction
    from . import owner_queue

    now = _now(now)
    since = now - timedelta(hours=24)
    with db.session() as s:
        keys = [(r.id, r.requirement_key) for r in s.scalars(
            select(OwnerAction).where(OwnerAction.done == False))  # noqa: E712
            if owner_queue.effective_state(r) == owner_queue.OPEN]
        recent = [dict(d or {}) for (d,) in s.execute(
            select(AuditLog.detail).where(AuditLog.action == SI.AUDIT_ACTION,
                                          AuditLog.at >= since))]
    verdicts = [SI.classify(k) for _i, k in keys]
    genuine = [v for v in verdicts if v["disposition"] == SI.GENUINE_EXCEPTION]
    by_class: dict[str, int] = {}
    for v in genuine:
        by_class[v["class"]] = by_class.get(v["class"], 0) + 1
    return {
        "owner_exceptions_open": len(genuine),
        "owner_exceptions_by_class": dict(sorted(by_class.items())),
        "unclassified_open": by_class.get(SI.UNCLASSIFIED, 0),
        "awaiting_sweep": len(verdicts) - len(genuine),
        "closed_automatically_24h": sum(1 for d in recent
                                        if d.get("disposition") == SI.AUTO_CLOSE),
        "routine_auto_approved_24h": sum(
            1 for d in recent if d.get("disposition") == SI.ROUTINE_INTERNAL
            and not _approves_nothing(d)),
        # Supersedes that approve nothing (a stale challenger run, a drift note): counted apart.
        "routine_superseded_nothing_approved_24h": sum(
            1 for d in recent if d.get("disposition") == SI.ROUTINE_INTERNAL
            and _approves_nothing(d)),
        "since": since.isoformat(), "directive": SI.DIRECTIVE_ID,
        "source": f"owner_actions (open) + audit_log[{SI.AUDIT_ACTION}] (24 h)"}


# ---- the one owner batch (Command Center) -----------------------------------------------------

#: The exception class of each executor gate the owner can be asked to open. A gate this table
#: does not name is UNCLASSIFIED (fail closed: it stays in the batch, flagged).
GATE_EXCEPTION_CLASS: dict[str, str] = {
    "etsy_shop": SI.KYC_LEGAL_BANKING,            # identity verification + seller terms
    "etsy_api": SI.GRANT_SIGNATURE,               # the account holder's developer consent
    "transactions_r": SI.GRANT_SIGNATURE,         # OAuth consent by the signed-in owner
    "insights_access": SI.PHYSICAL_EVIDENCE,      # a Shop Manager reading a person records
    "benchmark_observation": SI.PHYSICAL_EVIDENCE,
    "second_market_benchmark": SI.PHYSICAL_EVIDENCE,
    "physical_proof": SI.PHYSICAL_EVIDENCE,
    "model_provider": SI.PAID_ADS_SUBSCRIPTIONS,  # a paid provider account and its credit
    "image_generation": SI.PAID_ADS_SUBSCRIPTIONS,
    "image_vision": SI.PAID_ADS_SUBSCRIPTIONS,
    "rendered_pages": SI.PAID_ADS_SUBSCRIPTIONS,  # a browser-worker service
    "offsite_storage": SI.PAID_ADS_SUBSCRIPTIONS,  # an outside bucket account
    "ad_authority": SI.PAID_ADS_SUBSCRIPTIONS,
    "benchmark_purchases": SI.SPEND_BEYOND_BUDGET,
    "acceptance_ruling": SI.CERT_SAFETY_AUTHORITY,
    "canonical_model": SI.GRANT_SIGNATURE,        # an owner approval record, never forged
    "production_window": SI.PUBLICATION,          # an unattended production window
    "live_listings": SI.PUBLICATION,              # leaving shadow mode
    "tester_roster": SI.PUBLICATION,              # outreach to real people (CASL)
    "owned_surfaces": SI.PUBLICATION,             # a public surface beyond the shop
}

#: Command Center card kinds that are not OwnerAction rows, and their class.
CARD_KIND_CLASS: dict[str, str] = {
    "PUBLICATION": SI.PUBLICATION, "ACTIVATION": SI.PUBLICATION,
    "STANDING_POLICY": SI.GRANT_SIGNATURE, "policy_review": SI.POLICY_ATTESTATION,
    "RELEASE": SI.PUBLICATION,
}


def card_verdict(card: dict) -> dict:
    """(disposition, class, why) for one Command Center approvals card."""
    kind = str(card.get("kind") or "")
    cid = str(card.get("card_id") or "")
    if kind == "PUBLICATION" and not card.get("executable"):
        # Not ready: nothing to approve yet. Manufacturing continues; it is not an ask.
        # Labelled by its true class (PUBLICATION): not-ready is the state, not the class.
        return {"disposition": SI.ROUTINE_INTERNAL, "class": SI.PUBLICATION,
                "not_ready": True,
                "why": ("its gated sections do not all pass yet; rebuild, recertify, PDF, "
                        "gallery, SEO and listing-package work continue automatically "
                        f"({SI.DIRECTIVE_ID}) and the card returns when it is ready")}
    if kind in CARD_KIND_CLASS:
        return {"disposition": SI.GENUINE_EXCEPTION, "class": CARD_KIND_CLASS[kind],
                "why": f"{kind} cards are owner exceptions under {SI.DIRECTIVE_ID}"}
    rk = str(card.get("requirement_key") or "")
    if cid.startswith("gate:"):
        gate = cid.split(":", 1)[1]
        rows_genuine = True
        if rk and rk != gate:
            rows_genuine = SI.is_genuine(rk)
        klass = GATE_EXCEPTION_CLASS.get(gate)
        if klass is not None or rows_genuine:
            return {"disposition": SI.GENUINE_EXCEPTION, "class": klass or SI.UNCLASSIFIED,
                    "why": f"executor gate {gate}"}
    if rk:
        v = SI.classify(rk)
        return {"disposition": v["disposition"], "class": v["class"], "why": v["why"]}
    return {"disposition": SI.GENUINE_EXCEPTION, "class": SI.UNCLASSIFIED,
            "why": "card names no requirement or gate this table knows (fail closed)"}


def exception_batch(cards: list[dict]) -> dict:
    """ONE concise owner batch: only the genuine exceptions, grouped by exception class.

    Everything else on the queue is listed by count with its reason (covered by the standing
    authority, or closed as redundant / stale / satisfied) -- never presented as an ask."""
    groups: dict[str, list[dict]] = {}
    covered: list[dict] = []
    for c in cards:
        v = card_verdict(c)
        if v["disposition"] != SI.GENUINE_EXCEPTION:
            covered.append({"card_id": c.get("card_id"), "class": v["class"],
                            "disposition": v["disposition"],
                            "not_ready": bool(v.get("not_ready"))})
            continue
        groups.setdefault(v["class"], []).append({
            "card_id": c.get("card_id"), "kind": c.get("kind"),
            "title": c.get("title"), "proposed_action": c.get("proposed_action"),
            "max_spend_cad": c.get("max_spend_cad", c.get("max_cost_cad")),
            "minutes": c.get("minutes"),
            "consequence_of_waiting": c.get("consequence_of_no_action")
            or c.get("consequence_of_waiting"),
            "executable": bool(c.get("executable")),
            "actions": [a.get("action") for a in c.get("actions") or []]})
    order = list(SI.EXCEPTION_CLASSES) + [SI.UNCLASSIFIED]
    sections = [{"class": k, "items": groups[k], "count": len(groups[k])}
                for k in order if k in groups]
    sections += [{"class": k, "items": v, "count": len(v)} for k, v in groups.items()
                 if k not in order]
    total = sum(s["count"] for s in sections)
    return {"title": "Owner exceptions (one batch)", "directive": SI.DIRECTIVE_ID,
            "exceptions": total, "sections": sections,
            "covered_by_standing_authority": len(covered),
            "covered_by_class": _tally(covered),
            "not_ready_publication": sum(1 for c in covered if c["not_ready"]),
            "rule": ("only the directive's exception classes reach the owner: grant signatures "
                     "and step-up acts, publication/activation, external policy attestation, "
                     "physical evidence, spend beyond approved budgets, paid ads or "
                     "subscriptions, KYC/legal/banking, certification/construction/safety "
                     "authority. A kind no rule names stays here (fail closed)."),
            "never": ("this view signs, seals, approves or publishes nothing; every action on "
                      "it is the existing owner door with its own step-up")}


def _tally(items: list[dict]) -> dict:
    out: dict[str, int] = {}
    for i in items:
        out[i["class"]] = out.get(i["class"], 0) + 1
    return dict(sorted(out.items()))
