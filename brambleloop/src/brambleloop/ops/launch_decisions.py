"""Sealed owner launch decisions that launch readiness reads (W4-LAUNCHFIX D2).

`launch.readiness` hard-coded `listing_fees` and `brand_clearance` as `ready=False`, with no
evidence path at all, so `transition_verdict` could never be ready and
`core.phase.record_transition` refused every move up out of SHADOW whatever the owner did.
This module is the evidence path. It records nothing that is not the owner's own decision, and
it uses the same mechanism as every other owner authority here:

* written only through the Command Center approvals (`launch_decision.preview`, then
  `launch_decision.record` under owner session + CSRF + nonce + fresh step-up), with the
  server-held operator credential, like `acceptance.rule` and `activation.approve`;
* each row is HMAC-sealed under the operator credential and hash-chained in its own family
  (`core.sealed_chain.GrantLedger`): an edited, inserted, replayed or deleted row breaks the
  chain, every decision then reads as unrecorded and a P1 tamper incident opens;
* each decision is bound to the digest of exactly what the owner was shown (`snapshot`), and is
  revocable (`launch_decision.revoke`, which only tightens).

Readiness turns ready only on a valid row whose bound content still covers today:
listing fees -- an approval whose listing count is at least today's catalogue at today's
per-listing fee; brand clearance -- three facts kept apart:

  (a) the knock-out screening, company work, recorded with its evidence (`brand.clearance`);
  (b) the owner's acceptance of the residual risk that screening shows (BRAND_RISK, a sealed
      decision bound to the digest of exactly that screening) -- required;
  (c) formal registration (REGISTRATION: file / not now) -- recorded if the owner decides it,
      reported, and NOT required: Master Plan v1.2 s.29 asks for "marketplace/domain/social-
      handle screening and appropriate trademark clearance; escalate formal legal clearance to
      the owner/professional if needed", and Build 2 #54 for a "brand/name clearance
      checkpoint". Neither requires a filing, and DECISION_LOG records no decision that does.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import date, datetime, timezone

from sqlalchemy import select

from ..core import opsauth
from ..core.models import AuditLog

APPROVED = "owner.launch_decision.recorded"
REVOKED = "owner.launch_decision.revoked"
REBASED = "owner.launch_decision.rebased"
PRINCIPAL = "owner:ops-token"

LISTING_FEES = "listing_fees"
BRAND_RISK = "brand_risk_acceptance"
REGISTRATION = "trademark_registration"
DECISIONS = (LISTING_FEES, BRAND_RISK, REGISTRATION)

#: The one answer the risk decision takes (b). Declining is simply not recording it.
BRAND_RISK_CHOICES = {
    "accept": ("I have read the knock-out screening shown, including every hit, and accept "
               "the residual risk of trading under the name"),
}
#: The registration decision (c). Recorded and reported; never required for launch.
REGISTRATION_CHOICES = {
    "file": "file a Canadian trademark application for the shop name (CA$458.05, a spend)",
    "not_now": "do not file now; revisit as sales grow",
}
CHOICES = {LISTING_FEES: {"approve": "approve the fee for this catalogue"},
           BRAND_RISK: BRAND_RISK_CHOICES, REGISTRATION: REGISTRATION_CHOICES}


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      default=str)


def _seal(detail: dict) -> str:
    if not opsauth.configured():
        raise ValueError("owner credential unavailable")
    return hmac.new(os.environ[opsauth.TOKEN_VAR].strip().encode(), _json(detail).encode(),
                    hashlib.sha256).hexdigest()


def digest(value) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def catalogue_listings(db) -> int:
    """The count `launch.readiness.assess` costs the fee from: listings not withdrawn."""
    from sqlalchemy import func

    from ..core.models import Listing

    with db.session() as s:
        return int(s.scalar(select(func.count(Listing.id)).where(
            Listing.state != "withdrawn")) or 0)


def _fee_terms() -> dict:
    from ..commerce import fee_schedule as fs
    from ..launch.readiness import LISTING_FEE_CAD, LISTING_FEE_USD, LISTING_PERIOD_MONTHS

    return {"fee_per_listing_usd": LISTING_FEE_USD,
            "fee_per_listing_cad": round(LISTING_FEE_CAD, 4),
            "listing_period_months": LISTING_PERIOD_MONTHS,
            "transaction_rate": fs.TRANSACTION.rate, "fee_reading": fs.READ_ON}


def snapshot(db, decision: str, *, searches=None, today: date | None = None) -> dict:
    """Exactly what the owner is shown and what a record binds. Raises ValueError if the
    decision cannot be asked yet (no valid knock-out search for the trademark decision)."""
    if decision == LISTING_FEES:
        from ..launch.readiness import LISTING_FEE_CAD

        n = catalogue_listings(db)
        return {"decision": LISTING_FEES, "listings": n, **_fee_terms(),
                "estimate_cad": round(n * LISTING_FEE_CAD, 2)}
    if decision in (BRAND_RISK, REGISTRATION):
        from ..brand import clearance

        ko = clearance.latest(searches=searches, today=today)
        if ko["state"] != "VALID":
            raise ValueError("no valid knock-out search on record: "
                             + "; ".join(ko["problems"])[:400])
        e = ko["entry"]
        return {"decision": decision, "name": clearance.SHOP_NAME,
                "knockout_digest": ko["digest"], "searched_on": e["searched_on"],
                "screens": {k: {"source": v.get("source"), "hits": v.get("hits")}
                            for k, v in sorted((e.get("screens") or {}).items())},
                "conflicts": list(e["conflicts"]), "conclusion": e["conclusion"],
                "choices": dict(CHOICES[decision])}
    raise ValueError(f"decision must be one of {list(DECISIONS)}")


def record(db, *, authorization: str, decision: str, expected_digest: str, reason: str,
           choice: str | None = None, searches=None, today: date | None = None) -> dict:
    """Seal one owner decision bound to the previewed content. Raises ValueError on refusal."""
    opsauth.check(authorization)
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("owner decision reason required")
    content = snapshot(db, decision, searches=searches, today=today)
    if not hmac.compare_digest(digest(content), str(expected_digest or "")):
        raise ValueError("approval preview changed; review the current content")
    if decision == LISTING_FEES and choice in (None, ""):
        choice = "approve"
    if choice not in CHOICES[decision]:
        raise ValueError(f"choice must be one of {sorted(CHOICES[decision])}")
    detail = {"principal": PRINCIPAL, "decision": decision, "content": content,
              "digest": digest(content), "choice": choice,
              "reason": reason.strip()[:2000],
              "recorded_at": datetime.now(timezone.utc).isoformat()}
    ident = LEDGER.append(db, action=APPROVED, artifact=decision, detail=detail)
    return {"approval_id": ident, "decision": decision, "digest": detail["digest"],
            "choice": detail["choice"], "principal": PRINCIPAL}


def revoke(db, *, authorization: str, approval_id: int) -> dict:
    opsauth.check(authorization)
    LEDGER.revoke(db, int(approval_id))
    return {"revoked": int(approval_id)}


def _make_ledger():
    from ..core.sealed_chain import GrantLedger

    return GrantLedger(approved=APPROVED, revoked=REVOKED, rebased=REBASED,
                       principal=PRINCIPAL, seal=_seal,
                       signature="authority_chain_tamper:launch_decision",
                       label="owner launch decision")


LEDGER = _make_ledger()


def current(db, decision: str) -> dict:
    """The newest valid sealed decision of this kind, or why there is none. Never raises."""
    try:
        with db.session() as s:
            rows = [(r.id, r.actor, dict(r.detail or {})) for r in s.scalars(
                select(AuditLog).where(AuditLog.action == APPROVED,
                                       AuditLog.artifact == decision)
                .order_by(AuditLog.id.desc()))]
    except Exception as exc:  # noqa: BLE001 - unreadable is unrecorded
        return {"recorded": False, "why": f"decisions unreadable: {type(exc).__name__}"}
    if not rows:
        return {"recorded": False, "why": f"no sealed owner decision on {decision} recorded"}
    first_why = None
    for ident, actor, detail in rows:
        why = None
        if actor != PRINCIPAL:
            why = "row not written by the owner principal"
        else:
            try:
                why = LEDGER.refusal(db, ident)
                if why is None:
                    seal = detail.pop("seal", "")
                    if not hmac.compare_digest(str(seal), _seal(detail)):
                        why = "seal invalid (edited, hand-inserted or credential rotated)"
                    elif detail.get("decision") != decision or detail.get(
                            "digest") != digest(detail.get("content")):
                        why = "row does not bind this decision's content"
            except (ValueError, TypeError, KeyError) as exc:
                why = f"unverifiable: {str(exc)[:160]}"
        if why is None:
            return {"recorded": True, "approval_id": ident, "content": detail["content"],
                    "choice": detail.get("choice"), "recorded_at": detail.get("recorded_at")}
        first_why = first_why or f"decision {ident}: {why}"
    return {"recorded": False, "why": first_why}


def listing_fees_state(db, listings: int) -> dict:
    """Ready only when a valid sealed approval covers today's catalogue at today's fee."""
    got = current(db, LISTING_FEES)
    out = {"ready": False, "listings": int(listings), "approval_id": got.get("approval_id")}
    if not got["recorded"]:
        out["why"] = got["why"]
        return out
    content = got["content"]
    terms = _fee_terms()
    approved_n = int(content.get("listings") or 0)
    out["approved_listings"] = approved_n
    if content.get("fee_per_listing_usd") != terms["fee_per_listing_usd"]:
        out["why"] = (f"the approval was for US${content.get('fee_per_listing_usd')} per "
                      f"listing and Etsy's fee is now US${terms['fee_per_listing_usd']}; "
                      f"re-approve at the current fee")
        return out
    if approved_n < int(listings):
        out["why"] = (f"the approval covers {approved_n} listings and the catalogue now holds "
                      f"{listings}; re-approve the fee for the current catalogue")
        return out
    out.update(ready=True, why=(f"owner decision {got['approval_id']} approved the fee for "
                                f"{approved_n} listings ({got.get('recorded_at')})"))
    return out


def brand_clearance_state(db, *, searches=None, today: date | None = None) -> dict:
    """Ready only on (a) a valid knock-out screening AND (b) the owner's sealed acceptance of
    its residual risk, bound to that exact screening. (c) registration is reported, never
    required."""
    from ..brand import clearance

    ko = clearance.latest(searches=searches, today=today)
    reg = current(db, REGISTRATION)
    out = {"ready": False, "knockout": ko["state"], "knockout_problems": ko["problems"][:5],
           "knockout_digest": ko["digest"], "risk_accepted": False,
           "registration": {"required": False, "decision": reg.get("choice"),
                            "bound_to_current_screening": bool(
                                reg.get("recorded") and (reg.get("content") or {}).get(
                                    "knockout_digest") == ko["digest"]),
                            "basis": ("Master Plan v1.2 s.29 and Build 2 #54 require "
                                      "screening and a clearance checkpoint, not a filing")}}
    if ko["state"] != "VALID":
        out["why"] = "no valid knock-out screening on record (company work)"
        return out
    out["conflicts"] = list(ko["entry"]["conflicts"])
    got = current(db, BRAND_RISK)
    if not got["recorded"]:
        out["why"] = f"the owner has not accepted the residual risk: {got['why']}"
        return out
    if got["content"].get("knockout_digest") != ko["digest"]:
        out["why"] = ("the owner's risk acceptance was made on a different screening than the "
                      "one now on record; re-decide on the current screening")
        return out
    out.update(ready=True, risk_accepted=True, approval_id=got["approval_id"],
               why=(f"knock-out screening of {ko['entry']['searched_on']} recorded and its "
                    f"residual risk accepted by the owner (decision {got['approval_id']})"))
    return out
