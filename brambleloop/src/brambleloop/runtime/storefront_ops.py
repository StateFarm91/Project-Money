"""Storefront Director handlers (W4-AGENTS): storefront.review, content.draft, store.update.

* `storefront.review` (storefront_director, OBSERVE): evaluate the shop from stored readings;
  one `storefront.review` reading a day; when the agent can propose a fix, enqueue
  `content.draft`. No network, CA$0.
* `content.draft` (storefront_director or growth, DRAFT): record the deterministic, validated
  storefront proposals; for each valid proposal with an Etsy write API, enqueue ONE
  `store.update` keyed on (proposal, phase, grant), so a held proposal is retried exactly
  when the phase or the owner's grant changes and never otherwise.
* `store.update` (store_operator, PUBLISH, protected): apply one proposal. In SHADOW, or
  without the owner's sealed storefront grant for that exact change, nothing is sent: the
  proposal is recorded as held, with the reason. Only the live-state gate, the grant and a
  publishing phase together reach `EtsyClient.update_shop` / `create_shop_section`.
"""
from __future__ import annotations

import os

from ..core.models import Phase
from .worker import JobContext, handlers, protected_phase


def _review_and_record(ctx: JobContext) -> dict:
    from ..store_foundation import director
    from .etsy_ops import store_reading

    rev = director.review(ctx.db)
    store_reading(ctx.db, director.REVIEW_READING, rev)
    return rev


@handlers.register("storefront.review")
def handle_storefront_review(ctx: JobContext) -> dict:
    from ..store_foundation import director

    rev = _review_and_record(ctx)
    # F-527 (W4-AGENTS C3): brand asset health, findings routed to the agent that fixes them.
    from ..store_foundation import asset_health
    from .etsy_ops import store_reading

    health = asset_health.check(ctx.db)
    store_reading(ctx.db, "storefront.asset_health", health)
    queued = None
    if rev["agent_gaps"]:
        job = ctx.enqueue("storefront_director", "content.draft",
                          {"kind": "storefront", "gaps": rev["agent_gaps"]},
                          idempotency_key=f"content.draft:storefront:"
                                          f"{director.digest(rev['agent_gaps'])[:16]}:"
                                          f"{rev['at'][:10]}")
        queued = getattr(job, "id", None)
    ctx.audit("storefront.review", detail={"counts": rev["counts"],
                                           "agent_gaps": rev["agent_gaps"],
                                           "owner_gaps": rev["owner_gaps"],
                                           "draft_job": queued})
    return {"surfaces": len(rev["surfaces"]), "agent_gaps": rev["agent_gaps"],
            "owner_gaps": rev["owner_gaps"], "unknown": rev["unknown"],
            "asset_health": {"fixes": health["fix_count"], "routes": health["routes"]},
            "draft_job": queued, "writes_performed": 0, "etsy_calls": 0,
            "work_done": len(rev["surfaces"]) - len(rev["unknown"])}


@handlers.register("content.draft")
def handle_content_draft(ctx: JobContext) -> dict:
    """Storefront content drafted as recorded proposals. Publishes nothing."""
    from ..ops import storefront_authority
    from ..store_foundation import director

    kind = str((ctx.job.inputs or {}).get("kind") or "storefront")
    if kind != "storefront":
        return {"ran": False, "why": f"content.draft kind {kind!r} is not built; the "
                                     f"product content ecosystem is marketing.schedule"}
    rev = _review_and_record(ctx)
    props = director.build_proposals(ctx.db, rev)
    recorded, applies = 0, []
    phase = protected_phase(ctx).value
    for p in props:
        recorded += director.record_proposal(ctx.db, p)
        if not (p.get("api_writable") and p.get("valid")):
            continue
        _why, grant_id = storefront_authority.resolve(ctx.db, p["digest"][:20], p["change"])
        job = ctx.enqueue("store_operator", "store.update",
                          {"kind": "storefront", "proposal": p["digest"][:20]},
                          idempotency_key=f"store.update:storefront:{p['digest'][:16]}:"
                                          f"{phase}:{grant_id or 'nogrant'}")
        if job is not None:
            applies.append(job.id)
    ctx.audit("storefront.drafted", detail={"proposals": len(props), "recorded": recorded,
                                            "apply_jobs": applies})
    return {"proposals": len(props), "recorded": recorded,
            "valid": sum(1 for p in props if p.get("valid", not p.get("problems"))),
            "owner_steps": [p["surface"] for p in props if not p.get("api_writable")],
            "apply_jobs": applies, "published": False, "writes_performed": 0,
            "work_done": recorded + len(applies)}


def _raise_write_authority_card(ctx: JobContext, held: dict) -> None:
    from sqlalchemy import select

    from ..core.models import OwnerAction

    rk = "storefront:write_authority"
    with ctx.db.session() as s:
        if s.scalar(select(OwnerAction.id).where(OwnerAction.requirement_key == rk,
                                                 OwnerAction.done == False)):  # noqa: E712
            return
        s.add(OwnerAction(
            requirement_key=rk,
            action=("Review the Storefront Director's recorded proposals and, for each you "
                    "accept, approve it in the Command Center (storefront.approve: your "
                    "session and a fresh step-up; preview first for its digest)"),
            reason=(f"store.update holds proposal {held['proposal']} ({held['surface']}): "
                    f"{held['reason']}"[:600]),
            max_cost_cad=0.0, minutes=5, blocks="storefront",
            consequence_of_delay="announcement / buyer messages / sections stay as they are",
            why_software_cannot="a storefront change is visible to every buyer; it needs the "
                                "owner's sealed grant for that exact change"))


def _replaced_since_approval(ctx: JobContext, grant_id, change: dict) -> str | None:
    from ..core.models import AuditLog
    from ..ops import storefront_authority

    with ctx.db.session() as s:
        row = s.get(AuditLog, int(grant_id))
        granted = ((row.detail or {}).get("content") or {}).get("replaces") if row else None
    if not isinstance(granted, dict):
        return "the grant records no live text it replaces; re-approve from a fresh preview"
    now = storefront_authority.live_replaced(ctx.db, change)
    for k, v in now.items():
        if (granted.get(k) or {}).get("live_value") != v.get("live_value"):
            return (f"the live {k} changed since the owner approved; the approval no longer "
                    f"describes what would be overwritten -- preview and approve again")
    return None


@handlers.register("store.update")
def handle_store_update(ctx: JobContext) -> dict:
    """Apply one recorded storefront proposal, or record it as held. Never raises in SHADOW."""
    from ..integrations.etsy import (Credentials, EtsyClient, EtsyNotConfigured,
                                     EtsyNotPermitted, OwnerGrant)
    from ..ops import storefront_authority
    from ..store_foundation import director

    i = dict(ctx.job.inputs or {})
    if i.get("kind") != "storefront":
        return {"ran": False, "written": False,
                "why": "store.update applies Storefront Director proposals only; live "
                       "listing edits have no proposal source and are not wired"}
    ident = str(i.get("proposal") or "")
    p = director.proposal(ctx.db, ident)
    if p is None or not p.get("api_writable"):
        return {"ran": False, "written": False, "why": f"no API-writable proposal {ident!r}"}
    change = p["change"]
    held = {"proposal": ident, "surface": p.get("surface"), "change": change}

    def hold(reason: str, *, card: bool = False) -> dict:
        director.set_proposal_state(ctx.db, ident, "held", reason=reason[:400])
        ctx.audit("store.update_held", artifact=f"storefront:{ident}",
                  detail={**held, "reason": reason[:400], "etsy_calls": 0})
        if card:
            _raise_write_authority_card(ctx, {**held, "reason": reason})
        return {"written": False, "held": True, "proposal": ident, "reason": reason,
                "etsy_calls": 0, "writes_performed": 0, "work_done": 1}

    problems = director.validate_change(ctx.db, change, surface=p.get("surface", ""))
    if problems:
        return hold("proposal no longer validates: " + "; ".join(problems)[:300])
    phase_now = protected_phase(ctx)
    if phase_now is Phase.SHADOW:
        return hold("SHADOW mode: storefront changes are recorded as proposals, never sent")
    why, grant_id = storefront_authority.resolve(ctx.db, ident, change)
    if why:
        return hold(why, card=True)
    # Review L-2: the grant binds the live text it replaces; if the live shop changed since the
    # owner approved (e.g. the owner edited it by hand), the approval no longer describes what
    # would be overwritten, so nothing is sent.
    stale = _replaced_since_approval(ctx, grant_id, change)
    if stale:
        return hold(stale, card=True)
    grant = OwnerGrant(ctx.db, action=OwnerGrant.STOREFRONT, approval_id=grant_id,
                       change=change)
    from ..integrations.http import UrllibTransport

    transport = UrllibTransport()
    client = EtsyClient(transport, credentials=Credentials.from_env(transport=transport,
                                                                    db=ctx.db),
                        phase=phase_now.value,
                        owner_authorised=os.environ.get(storefront_authority.KILL_SWITCH_VAR,
                                                        "") == "1")
    from ..queue.effects import EffectNotSent

    refused: list[str] = []
    try:
        with ctx.effect("etsy.storefront", ident) as intent:
            try:
                if change["operation"] == "updateShop":
                    body = client.update_shop(change["fields"], grant=grant)
                else:
                    body = client.create_shop_section(change["title"], grant=grant)
            except (EtsyNotPermitted, EtsyNotConfigured) as exc:
                refused.append(str(exc))       # refused before any request: nothing sent
                raise EffectNotSent(str(exc)) from exc
            intent.applied(f"storefront:{ident}")
    except EffectNotSent:
        return hold(f"refused at the client: {refused[0] if refused else 'not sent'}")
    director.set_proposal_state(ctx.db, ident, "applied", grant=grant_id)
    ctx.audit("store.update_applied", artifact=f"storefront:{ident}",
              detail={**held, "grant": grant_id, "calls": client.calls})
    return {"written": True, "proposal": ident, "grant": grant_id,
            "etsy_calls": len(client.calls), "response_keys": sorted(body)[:20],
            "work_done": 1}
