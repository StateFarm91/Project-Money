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
#: Slots per UTC clock hour (the database bound): half the rolling-hour ceiling.
SLOTS_PER_CLOCK_HOUR = MAX_PER_HOUR // 2
WITHDRAWN = "listing.withdrawn"
# Verdict 6998051067 M1: written BEFORE the Etsy request, so a crash after Etsy accepted is
# recoverable from the record (a retry reconciles from Etsy's read-back).
INTENT = "listing.withdraw_intent"
MISMATCH_INCIDENT = "standing_policy.withdrawal_unconfirmed:"
MISMATCH_CARD = "standing_policy.withdrawal_unconfirmed:"
#: The per-product owner path's success event (runtime.pipeline.handle_store_activate).
OWNER_ACTIVATED = "store.activated"
PLANNED = "policy.rollback_planned"
ACTOR = "standing_rollback"
STOPPED_STATES = frozenset({SP.SUSPENDED_STATE, SP.NONE, SP.DEAD, SP.BROKEN})


class WithdrawalRefused(Exception):
    """A withdrawal the database bound refused before anything was sent."""


def _now(now=None) -> datetime:
    from . import standing_issuer as SI

    return SI._now(now)


def lineage_of_live(db, listing_id: str) -> dict | None:
    """The standing activation that made `listing_id` live, or None. Fails closed.

    Verdict 6998051067 M2: a consumed activation grant is not enough. The grant's seal must
    verify under the issuer key, a read-back-verified Stage A activation event
    (`standing_activation.ACTIVATED`) must exist for that grant and listing, and no later
    activation of the listing by another path (the owner's per-product `store.activated`) may
    exist: a listing the owner made live is never withdrawn from here."""
    from sqlalchemy import select

    from ..core.models import AuditLog
    from . import standing_activation as SA
    from . import standing_grants as SG

    SG.ensure_tables(db)
    lid = str(listing_id)
    with db.session() as s:
        verified = [r for r in s.scalars(select(AuditLog).where(
            AuditLog.action == SA.ACTIVATED, AuditLog.actor == SA.ACTIVATED_ACTOR)
            .order_by(AuditLog.id.desc()))
            if str((r.detail or {}).get("etsy_listing_id")) == lid]
        if not verified:
            return None
        latest = verified[0]
        other = [r for r in s.scalars(select(AuditLog).where(
            AuditLog.action == OWNER_ACTIVATED, AuditLog.id > latest.id))
            if str((r.detail or {}).get("etsy_listing_id")) == lid]
        if other:
            return None
        # Verdict 6999967600 L-F: a recorded withdrawal ends that activation's lineage; only a
        # new verified Stage A activation starts it again.
        ended = [r for r in s.scalars(select(AuditLog).where(
            AuditLog.action == WITHDRAWN, AuditLog.id > latest.id))
            if str((r.detail or {}).get("etsy_listing_id")) == lid]
        if ended:
            return None
        g = s.get(SG.StandingGrant, int((latest.detail or {}).get("grant_id") or -1))
        if g is None or g.consumed_at is None:
            return None
        body, seal = dict(g.detail_json or {}), str(g.seal or "")
        out = {"grant_id": g.id, "policy_row_id": g.policy_row_id, "scope": g.scope,
               "release": g.release, "job_id": g.consumed_job_id,
               "activated_event_id": latest.id}
    if body.get("action") != SA.ACTION or str(body.get("listing_id")) != lid:
        return None
    if not SG.verify(SA.DOMAIN, body, seal):
        return None
    return out


def stopped(db, *, now=None) -> str | None:
    """Why the owner's standing policy counts as stopped, or None while it is not."""
    eff = SP.effective(db, now=_now(now))
    state = eff.get("state")
    if state == SP.NONE and eff.get("why") == SP.NOT_MODE_T_WHY:
        # The policy is in force; only this deployment cannot issue under it. A missing or
        # stale process heartbeat never takes a listing down (CERTFIX-3).
        return None
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


def _open_intent(db, listing_id: str):
    """The latest withdrawal intent for `listing_id` with no withdrawal recorded after it."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    lid = str(listing_id)
    with db.session() as s:
        intents = [r for r in s.scalars(select(AuditLog).where(AuditLog.action == INTENT)
                                        .order_by(AuditLog.id.desc()))
                   if str((r.detail or {}).get("etsy_listing_id")) == lid]
        if not intents:
            return None
        done = [r for r in s.scalars(select(AuditLog).where(AuditLog.action == WITHDRAWN,
                                                              AuditLog.id > intents[0].id))
                if str((r.detail or {}).get("etsy_listing_id")) == lid]
        return None if done else {"id": intents[0].id, **dict(intents[0].detail or {})}


def _record_withdrawn(db, *, slug, version, listing_id, before, after, now, reconciled=False):
    from sqlalchemy import update

    from ..core.models import AuditLog, Listing
    from ..ops import incident_lifecycle as lifecycle
    from ..ops import owner_queue

    lineage = lineage_of_live(db, listing_id) or {}
    with db.session() as s:
        s.execute(update(Listing).where(Listing.product_slug == slug, Listing.version == version,
                                        Listing.etsy_listing_id == str(listing_id))
                  .values(state="withdrawn"))
        s.add(AuditLog(actor=ACTOR, action=WITHDRAWN, artifact=f"{slug}@{version}",
                       detail={"etsy_listing_id": str(listing_id), "before": before,
                               "after": after, "grant_id": lineage.get("grant_id"),
                               "why": stopped(db, now=now), "reconciled": reconciled,
                               "at": now.isoformat()}))
        lifecycle.resolve_signatures(
            s, [f"{MISMATCH_INCIDENT}{listing_id}"],
            resolution=f"listing {listing_id} reads inactive on Etsy and is recorded withdrawn")
        from sqlalchemy import select

        from ..core.models import OwnerAction

        card = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == f"{MISMATCH_CARD}{listing_id}",
            OwnerAction.done.is_(False)))
        if card is not None:
            owner_queue.close(card, owner_queue.SATISFIED,
                              f"listing {listing_id} reads inactive on Etsy")


def _unconfirmed(db, *, slug, version, listing_id, why, now):
    """Verdict 6998051067 M1: Etsy accepted (or may have) but does not read inactive. One
    incident and one owner card name the listing; nothing is recorded as withdrawn."""
    from ..ops import incident_lifecycle as lifecycle
    from ..ops import owner_queue

    with db.session() as s:
        lifecycle.open_or_restate(
            s, signature=f"{MISMATCH_INCIDENT}{listing_id}", severity="P2",
            summary=(f"withdrawal of standing-policy listing {listing_id} is unconfirmed: "
                     f"{why}"),
            detail={"etsy_listing_id": str(listing_id), "slug": slug, "version": version,
                    "why": why}, product_slug=slug, now=now)
        owner_queue.ensure(
            s, f"{MISMATCH_CARD}{listing_id}",
            action=(f"Check listing {listing_id} on Etsy: a standing-policy withdrawal was sent "
                    f"but Etsy does not report it inactive ({why}). Deactivate it on Etsy if "
                    f"it is still live; the next withdrawal run reconciles the record."),
            reason="the rollback of a stopped standing policy could not confirm this listing",
            max_cost_cad=0.0, minutes=5,
            consequence_of_delay="a listing of a stopped policy may still be live",
            blocks="completing the standing-policy rollback")


def _claim_slot(db, listing_id: str, now: datetime) -> int:
    """Take one of the clock hour's MAX_PER_HOUR request slots, or refuse (nothing sent)."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from . import standing_activation as SA

    SA.ensure_tables(db)
    hour = now.strftime("%Y-%m-%dT%H")
    with db.session() as s:
        rows = list(s.execute(select(SA.StandingWithdrawalSlot.slot_no,
                                     SA.StandingWithdrawalSlot.listing_id).where(
            SA.StandingWithdrawalSlot.hour == hour)))
    mine = [n for n, lid in rows if str(lid) == str(listing_id)]
    if mine:
        return mine[0]              # L-D: a retry of this listing this hour reuses its slot
    used = {n for n, _lid in rows}
    free = [n for n in range(1, SLOTS_PER_CLOCK_HOUR + 1) if n not in used]
    if not free:
        raise WithdrawalRefused(f"at most {SLOTS_PER_CLOCK_HOUR} withdrawals per clock hour "
                                f"({MAX_PER_HOUR} per rolling hour, database)")
    try:
        with db.session() as s:
            s.add(SA.StandingWithdrawalSlot(hour=hour, slot_no=free[0],
                                            listing_id=str(listing_id), at=now))
    except IntegrityError:
        raise WithdrawalRefused("another withdrawal took this hour's slot first; "
                                "refused, never retried into an extra slot") from None
    return free[0]


def withdraw(db, client, *, slug: str, version: str, listing_id: str,
             now: datetime | None = None) -> dict:
    """Take one SP-lineage listing down through `EtsyClient.deactivate`, and record it.

    Verdict 6998051067 M1: durable at every step.
    * An intent (`listing.withdraw_intent`) is written before the request.
    * If an earlier intent has no recorded withdrawal and Etsy already reads the listing
      inactive, the earlier attempt reached Etsy and crashed before recording: this run
      completes the local record (`reconciled`) and sends nothing.
    * If Etsy does not read inactive after the request, one incident and one owner card name
      the listing, and nothing is recorded as withdrawn (a later run retries or reconciles).
    """
    from ..core.models import AuditLog
    from ..integrations.etsy import EtsyNotPermitted, OwnerGrant

    now = _now(now)
    pending = _open_intent(db, listing_id)
    if pending is not None:
        current = client.get_listing(str(listing_id), includes=())
        state = str(current.get("state") or "").lower()
        if state == "inactive" and lineage_of_live(db, listing_id) is not None:
            _record_withdrawn(db, slug=slug, version=version, listing_id=listing_id,
                              before=pending.get("before") or "active", after=state, now=now,
                              reconciled=True)
            return {"listing_id": str(listing_id), "before": pending.get("before") or "active",
                    "after": state, "reconciled": True}
    _claim_slot(db, listing_id, now)
    with db.session() as s:
        s.add(AuditLog(actor=ACTOR, action=INTENT, artifact=f"{slug}@{version}",
                       detail={"etsy_listing_id": str(listing_id), "before": "active",
                               "at": now.isoformat()}))
    grant = OwnerGrant(db, action=OwnerGrant.WITHDRAW, approval_id="policy-stopped",
                       slug=slug, version=version, listing_id=str(listing_id))
    try:
        out = client.deactivate(str(listing_id), grant=grant)
    except EtsyNotPermitted:
        raise                       # refused at the client before any request: nothing sent
    except Exception as exc:  # noqa: BLE001 - verdict 6999967600 L-E: a transport error after
        # the PATCH is as unconfirmed as a read-back mismatch: the request may have landed.
        _unconfirmed(db, slug=slug, version=version, listing_id=listing_id,
                     why=f"{type(exc).__name__}: {str(exc)[:280]}", now=now)
        raise
    _record_withdrawn(db, slug=slug, version=version, listing_id=listing_id,
                      before=out["before"], after=out["after"], now=now)
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
                    str(body.get("listing_id")) == str(row.etsy_listing_id) and \
                    (lin := lineage_of_live(db, row.etsy_listing_id)) is not None and \
                    lin["grant_id"] == g.id:
                # Verdict 6998051067 M2: the same lineage `withdraw` requires.
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
