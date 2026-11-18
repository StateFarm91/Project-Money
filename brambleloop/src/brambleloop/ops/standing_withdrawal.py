"""WS4 Stage A, part 2: taking standing-policy listings back down, bounded.

Design: research/final_build/w6/WS4_standing_policy_design.md §5.3 (rollback, v2: "adds
`EtsyClient.deactivate(listing_id, grant)`. It is the only door that sends `state=inactive`.
It reads back first and refuses unless the listing is `active` and in SP lineage") and §5.4
(the withdrawal authority), under §9 M1/M6 item 11.

Withdrawing does not widen what the system can do, but a compromised worker could use it to
destroy work, so `OwnerGrant.WITHDRAW` (resolved here by `withdraw_refusal`) is valid only
when ALL of these hold, re-read from the database at the client, immediately before the
request:

1. **SP lineage.** The listing was made live by a standing activation grant that a job
   consumed (`standing_activation`). A listing the owner published personally, or one made
   live through today's per-product owner approval, is never in lineage, so it is never
   reachable from here.
2. **The policy has stopped.** The owner's standing policy reads SUSPENDED, revoked (NONE),
   DEAD or BROKEN. While it is in effect nothing is withdrawn automatically. (§5.4's other
   case, "the owner asked", is the owner's own Etsy dashboard today; an owner-signed withdrawal
   request is not built here.)
3. **Rate.** At most `MAX_PER_HOUR` withdrawals in any hour.
4. **Before-state read-back.** The listing as Etsy holds it right now is this listing and is
   `active`.

Phase is deliberately not one of them. A withdrawal is deny-direction, and the moment it is
most wanted is right after the owner rolls the phase back to SHADOW. Every withdrawal is
audited (`listing.withdrawn`) with the before and after state Etsy reported, and the local
Listing becomes `withdrawn`.

Rollback (`plan`) PLANS ONLY. On a stopped policy it lists the SP-lineage listings that are
live and the SP-lineage drafts, and records the plan (`policy.rollback_planned`) for the
owner's card. Executing a plan is `withdraw`, one listing at a time, under the bounds above.
There is no automatic execution in this increment: the policy has no signed "withdraw on
stop" field, and adding one is an owner-signed content change, not a default.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import standing_boundary as SB
from . import standing_policy as SP

WITHDRAW = "store.withdraw"
MAX_PER_HOUR = 10
WITHDRAWN = "listing.withdrawn"
PLANNED = "policy.rollback_planned"
ACTOR = "standing_rollback"
STOPPED_STATES = frozenset({SP.SUSPENDED_STATE, SP.NONE, SP.DEAD, SP.BROKEN})


def _now(now=None) -> datetime:
    from . import standing_issuer as SI

    return SI._now(now)


def lineage_of_live(db, listing_id: str) -> dict | None:
    """The consumed standing activation grant that made `listing_id` live, or None."""
    from sqlalchemy import select

    from . import standing_activation as SA
    from . import standing_grants as SG

    SG.ensure_tables(db)
    with db.session() as s:
        for g in s.scalars(select(SG.StandingGrant).where(
                SG.StandingGrant.consumed_at.is_not(None)).order_by(SG.StandingGrant.id.desc())):
            body = g.detail_json or {}
            if body.get("action") == SA.ACTION and str(body.get("listing_id")) == str(listing_id):
                return {"grant_id": g.id, "policy_row_id": g.policy_row_id, "scope": g.scope,
                        "release": g.release, "job_id": g.consumed_job_id}
    return None


def stopped(db, *, now=None) -> str | None:
    """Why the owner's standing policy counts as stopped, or None while it is not."""
    eff = SP.effective(db, now=_now(now))
    state = eff.get("state")
    if state in STOPPED_STATES:
        return f"{state}: {eff.get('why')}"
    return None


def _recent(db, now) -> int:
    from sqlalchemy import func, select

    from ..core.models import AuditLog

    with db.session() as s:
        return int(s.scalar(select(func.count(AuditLog.id)).where(
            AuditLog.action == WITHDRAWN, AuditLog.at >= now - timedelta(hours=1))) or 0)


def withdraw_refusal(db, listing_id: str, *, remote: dict | None,
                     now: datetime | None = None) -> str | None:
    """Why `OwnerGrant.WITHDRAW` does not cover taking `listing_id` down now, or None."""
    try:
        now = _now(now)
        if lineage_of_live(db, listing_id) is None:
            return (f"listing {listing_id} is not in SP lineage: only a listing a standing "
                    "activation grant made live can be withdrawn here")
        why = stopped(db, now=now)
        if why is None:
            return ("the standing policy is still in effect: nothing it made live is "
                    "withdrawn automatically while it is")
        if _recent(db, now) >= MAX_PER_HOUR:
            return f"at most {MAX_PER_HOUR} withdrawals per hour"
        if not isinstance(remote, dict) or str(remote.get("listing_id")) != str(listing_id):
            return "the read-back is not this listing"
        if str(remote.get("state") or "").lower() != "active":
            return f"listing {listing_id} is {remote.get('state')!r} on Etsy, not active"
        return None
    except Exception as exc:  # noqa: BLE001 - an unverifiable withdrawal is refused
        return f"withdrawal could not be verified: {type(exc).__name__}"


def withdraw(db, client, *, slug: str, version: str, listing_id: str,
             now: datetime | None = None) -> dict:
    """Take one SP-lineage listing down through `EtsyClient.deactivate`, and record it."""
    from sqlalchemy import update

    from ..core.models import AuditLog, Listing
    from ..integrations.etsy import OwnerGrant

    now = _now(now)
    grant = OwnerGrant(db, action=OwnerGrant.WITHDRAW, approval_id="policy-stopped",
                       slug=slug, version=version, listing_id=str(listing_id))
    out = client.deactivate(str(listing_id), grant=grant)
    lineage = lineage_of_live(db, listing_id) or {}
    with db.session() as s:
        s.execute(update(Listing).where(Listing.product_slug == slug, Listing.version == version,
                                        Listing.etsy_listing_id == str(listing_id))
                  .values(state="withdrawn"))
        s.add(AuditLog(actor=ACTOR, action=WITHDRAWN, artifact=f"{slug}@{version}",
                       detail={"etsy_listing_id": str(listing_id), "before": out["before"],
                               "after": out["after"], "grant_id": lineage.get("grant_id"),
                               "why": stopped(db, now=now), "at": now.isoformat()}))
    return out


def plan(db, *, now: datetime | None = None) -> dict:
    """The rollback plan for a stopped policy. Records it; executes nothing."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog, Listing
    from . import standing_activation as SA
    from . import standing_grants as SG

    now = _now(now)
    why = stopped(db, now=now)
    if why is None:
        return {"planned": False, "why": "the standing policy is not stopped"}
    SG.ensure_tables(db)
    live, drafts = [], []
    with db.session() as s:
        grants = list(s.scalars(select(SG.StandingGrant).where(
            SG.StandingGrant.consumed_at.is_not(None))))
        for g in grants:
            body = g.detail_json or {}
            slug, _, version = g.scope.partition("@")
            row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
            if row is None or not row.etsy_listing_id:
                continue
            item = {"slug": slug, "version": version, "listing_id": str(row.etsy_listing_id),
                    "grant_id": g.id}
            if body.get("action") == SA.ACTION and row.state == "active" and \
                    str(body.get("listing_id")) == str(row.etsy_listing_id):
                live.append(item)
            elif body.get("action") == SA.PUBLISH and row.state != "active":
                if SA.lineage(db, slug, version, g.release, g.policy_row_id)["state"] == SB.PASS:
                    drafts.append(item)
        last = s.scalar(select(AuditLog).where(AuditLog.action == PLANNED)
                        .order_by(desc(AuditLog.id)))
    detail = {"why": why, "live": live, "drafts": drafts, "executes": "nothing: plan only",
              "at": now.isoformat()}
    same = last is not None and {k: (last.detail or {}).get(k) for k in ("live", "drafts")} \
        == {"live": live, "drafts": drafts}
    if not same:
        with db.session() as s:
            s.add(AuditLog(actor=ACTOR, action=PLANNED, artifact="standing_policy",
                           detail=detail))
    return {"planned": True, "recorded": not same, **detail}
