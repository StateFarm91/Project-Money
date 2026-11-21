"""MISSION-CONTROL-2: the owner's "Approve all eligible" button (D-MC2-APPROVE-ALL).

The owner asked for one button that clears the routine part of the owner queue. This module is
that button. It is not a new authority: it reads the classifier the hourly sweep already uses
(`authority.standing_internal.classify`) and moves rows with the lifecycle the sweep already
uses (`ops.owner_queue.transition`). The difference from the sweep is who acts: the OWNER, inside
an owner session that has passed the existing passphrase + TOTP login and a fresh step-up
(`auth.require_stepup`, enforced by the route in `api.py`, never here).

Eligible = an open or parked OwnerAction row whose kind the classifier marks ROUTINE_INTERNAL or
AUTO_CLOSE, and which the exclusion guard below does not catch.

Never approved, listed separately with the reason (`EXCLUDED`):
* child-safety holds (certification / construction / safety authority);
* physical-sample attestations (physical evidence only a person can supply);
* spend above approved ceilings (and paid ads / subscriptions);
* public-publishing authority (publication, activation, phase, standing policy, live listings);
* every other genuine owner exception (grant signatures, OAuth consent, KYC / legal / banking,
  external policy attestation, kinds nobody classified) -- those are acts the owner does at
  their own door, not by a bulk approval;
* every Command Center card that is not an OwnerAction row (executor gates, publication,
  activation and standing-policy grants, policy reviews, the release card).

Defence in depth: the exclusion guard also matches the requirement key itself, so a row the
classifier wrongly marked routine but whose key names a child-safety, physical, spend or
publication subject is still excluded (`guarded: true`).

Safety of the batch:
* `preview` returns the exact rows and a digest of them; `execute` refuses unless the caller's
  `expected_digest` matches the set computed now (no approving a set the owner did not see);
* each row is re-read and re-classified inside the writing session, so a row that closed or
  changed kind since the preview is skipped, never approved;
* every approval writes its `owner_action.lifecycle` row (via `transition`) and one
  `owner_action.approve_all` audit row; the batch writes one `owner_queue.approve_all` row with
  the counts, the ids and the excluded tallies. Nothing is deleted, signed, sealed, published,
  spent or messaged.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from ...authority import standing_internal as SI

STEP_UP_ACTION = "owner_queue.approve_all"
ROW_AUDIT_ACTION = "owner_action.approve_all"
BATCH_AUDIT_ACTION = "owner_queue.approve_all"

CHILD_SAFETY = "child_safety"
PHYSICAL_SAMPLE = "physical_sample"
SPEND_ABOVE_CEILING = "spend_above_ceiling"
PUBLIC_PUBLISHING = "public_publishing"
OWNER_ONLY = "owner_only"
NOT_AN_OWNER_ACTION = "not_an_owner_action_row"

EXCLUDED: dict[str, str] = {
    CHILD_SAFETY: ("a child-safety hold is released only by a certification and safety ruling "
                   "on that product, with its evidence; never in bulk"),
    PHYSICAL_SAMPLE: ("a physical-sample attestation says a person made, measured or "
                      "photographed something; a button cannot attest that"),
    SPEND_ABOVE_CEILING: ("spend above an approved ceiling, paid ads and subscriptions are "
                          "consequential spend, decided one at a time; ceilings stay enforced "
                          "in code"),
    PUBLIC_PUBLISHING: ("public-publishing authority is a signed grant bound to one release's "
                        "content (publication, activation, phase, standing policy); never a "
                        "bulk approval"),
    OWNER_ONLY: ("an act only the owner can do at its own door (a signed grant, OAuth consent, "
                 "KYC / legal / banking, an external policy attestation) or a kind nobody has "
                 "classified yet (fail closed)"),
    NOT_AN_OWNER_ACTION: ("an executor gate, grant or review card: it closes when reality "
                          "changes or through its own step-up door, not by this button"),
}
CATEGORY_ORDER = (CHILD_SAFETY, PHYSICAL_SAMPLE, SPEND_ABOVE_CEILING, PUBLIC_PUBLISHING,
                  OWNER_ONLY, NOT_AN_OWNER_ACTION)

_CLASS_CATEGORY = {
    SI.PHYSICAL_EVIDENCE: PHYSICAL_SAMPLE,
    SI.SPEND_BEYOND_BUDGET: SPEND_ABOVE_CEILING,
    SI.PAID_ADS_SUBSCRIPTIONS: SPEND_ABOVE_CEILING,
    SI.PUBLICATION: PUBLIC_PUBLISHING,
}

# The key guard (checked first, whatever the classifier says). Order = precedence.
_KEY_GUARDS: tuple[tuple[str, re.Pattern], ...] = (
    (CHILD_SAFETY, re.compile(r"child|safety|small_part|choking|(^|[^a-z])toys?($|[^a-z])", re.I)),
    (PHYSICAL_SAMPLE, re.compile(r"physical|sample|swatch|attest|tester", re.I)),
    (SPEND_ABOVE_CEILING, re.compile(r"spend|ceiling|budget|(^|[.:])ads[.:]|subscription|"
                                     r"reinvest|credit|payout", re.I)),
    (PUBLIC_PUBLISHING, re.compile(r"publish|publication|activat|(^|[.:])phase($|[.:])|"
                                   r"standing_policy|first_public|live_update|live_listing|"
                                   r"portfolio\.retire", re.I)),
)


def _now(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def guard(requirement_key: str | None) -> str | None:
    """The excluded category a requirement key names on its face, or None."""
    key = requirement_key or ""
    for category, rx in _KEY_GUARDS:
        if rx.search(key):
            return category
    return None


def judge(requirement_key: str | None) -> dict:
    """{eligible, category, guarded, verdict} for one OwnerAction kind. Fails closed."""
    verdict = SI.classify(requirement_key)
    guarded = guard(requirement_key)
    if verdict["disposition"] == SI.GENUINE_EXCEPTION:
        klass = verdict["class"]
        if klass == SI.CERT_SAFETY_AUTHORITY:
            category = CHILD_SAFETY if guarded == CHILD_SAFETY or "child" in (
                requirement_key or "").lower() else OWNER_ONLY
        else:
            category = _CLASS_CATEGORY.get(klass) or (
                guarded if klass == SI.UNCLASSIFIED and guarded else OWNER_ONLY)
        return {"eligible": False, "category": category, "guarded": False, "verdict": verdict}
    if verdict["disposition"] not in (SI.ROUTINE_INTERNAL, SI.AUTO_CLOSE):
        return {"eligible": False, "category": OWNER_ONLY, "guarded": False, "verdict": verdict}
    if guarded is not None:
        return {"eligible": False, "category": guarded, "guarded": True, "verdict": verdict}
    return {"eligible": True, "category": None, "guarded": False, "verdict": verdict}


def _target(row, verdict: dict, *, now: datetime) -> tuple[str, str]:
    """The lifecycle state the owner's approval moves a row to, and the reason."""
    from ...ops import owner_queue
    from ...ops import owner_queue_consolidate as OQC

    decided = OQC.decide(row, verdict, now=now)
    base = "approved by the owner with 'Approve all eligible' (step-up session)"
    if decided is None:   # e.g. a stale-class row not yet past STALE_AFTER: the owner answers
        return owner_queue.SUPERSEDED, f"{base}: {verdict['why']}"[:1000]
    state, why = decided
    return state, f"{base}; {why}"[:1000]


def _open_rows(s):
    from sqlalchemy import select

    from ...core.models import OwnerAction
    from ...ops import owner_queue

    rows = s.scalars(select(OwnerAction).where(OwnerAction.done == False)  # noqa: E712
                     .order_by(OwnerAction.id))
    return [r for r in rows
            if owner_queue.effective_state(r) in (owner_queue.OPEN, owner_queue.PARKED)]


def _digest(items: list[dict]) -> str:
    body = json.dumps([[i["id"], i["requirement_key"], i["to"]] for i in items],
                      separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def _other_cards(db) -> tuple[list[dict], str | None]:
    """Command Center cards that are not OwnerAction rows: always excluded, listed."""
    try:
        from . import approvals

        cards = approvals.inbox(db).get("cards") or []
    except Exception as exc:  # noqa: BLE001 - unreadable is said, never read as empty
        return [], f"approval inbox unreadable: {type(exc).__name__}"
    out = []
    for c in cards:
        cid = str(c.get("card_id") or "")
        if cid.startswith("owner_action:"):
            continue
        out.append({"card_id": cid, "kind": c.get("kind"), "title": c.get("title"),
                    "requirement_key": c.get("requirement_key"),
                    "category": NOT_AN_OWNER_ACTION, "reason": EXCLUDED[NOT_AN_OWNER_ACTION]})
    return out, None


def preview(db, *, now: datetime | None = None, include_cards: bool = True) -> dict:
    """What the button would approve now, what it never approves (and why), and the digest."""
    now = _now(now)
    eligible, excluded = [], []
    with db.session() as s:
        for row in _open_rows(s):
            j = judge(row.requirement_key)
            base = {"id": row.id, "requirement_key": row.requirement_key,
                    "title": (row.action or "")[:200], "class": j["verdict"]["class"],
                    "disposition": j["verdict"]["disposition"]}
            if j["eligible"]:
                state, reason = _target(row, j["verdict"], now=now)
                eligible.append({**base, "to": state, "why": j["verdict"]["why"]})
            else:
                excluded.append({**base, "category": j["category"], "guarded": j["guarded"],
                                 "reason": EXCLUDED[j["category"]],
                                 "classifier_why": j["verdict"]["why"]})
    cards, cards_error = (_other_cards(db) if include_cards else ([], None))
    excluded_all = excluded + cards
    by_cat = {k: 0 for k in CATEGORY_ORDER}
    for e in excluded_all:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1
    return {"read_only": True, "as_of": now.isoformat(), "step_up_required": True,
            "step_up_action": STEP_UP_ACTION,
            "eligible_count": len(eligible), "eligible": eligible,
            "digest": _digest(eligible),
            "excluded_count": len(excluded_all), "excluded_by_category": by_cat,
            "excluded": excluded_all, "excluded_reasons": dict(EXCLUDED),
            "cards_error": cards_error,
            "rule": ("approves every open or parked owner-queue row the classifier "
                     f"({SI.DIRECTIVE_ID} table) marks routine or auto-close; never child-"
                     "safety holds, physical-sample attestations, spend above ceilings or "
                     "public-publishing authority")}


class Refused(ValueError):
    pass


def execute(db, *, actor: str, expected_digest: str, session_public_id: str = "",
            now: datetime | None = None) -> dict:
    """Approve every eligible row, in one transaction, auditing each. The CALLER enforces the
    owner session and step-up; this refuses a stale preview."""
    from sqlalchemy import select

    from ...core.models import AuditLog, OwnerAction
    from ...ops import owner_queue

    now = _now(now)
    if not actor.startswith("owner:"):
        raise Refused("only an owner session may approve the owner queue")
    current = preview(db, now=now, include_cards=False)
    if not expected_digest or expected_digest != current["digest"]:
        raise Refused("the eligible set changed since your preview; review it again "
                      f"({current['eligible_count']} eligible now)")
    batch = current["digest"][:16]
    approved, skipped = [], []
    ids = [i["id"] for i in current["eligible"]]
    with db.session() as s:
        rows = {r.id: r for r in s.scalars(select(OwnerAction).where(OwnerAction.id.in_(ids)))}
        for item in current["eligible"]:
            row = rows.get(item["id"])
            if row is None or owner_queue.effective_state(row) not in (owner_queue.OPEN,
                                                                        owner_queue.PARKED):
                skipped.append({"id": item["id"], "why": "no longer open"})
                continue
            j = judge(row.requirement_key)          # re-judged at the write: never stale
            if not j["eligible"]:
                skipped.append({"id": row.id, "why": f"now excluded ({j['category']})"})
                continue
            state, reason = _target(row, j["verdict"], now=now)
            moved = owner_queue.transition(s, row, state, reason, actor=actor, now=now)
            if not moved.get("changed"):
                skipped.append({"id": row.id, "why": "already in that state"})
                continue
            s.add(AuditLog(actor=actor[:64], action=ROW_AUDIT_ACTION, at=now,
                           artifact=f"owner_action:{row.id}",
                           detail={"batch": batch, "requirement_key": row.requirement_key,
                                   "disposition": j["verdict"]["disposition"],
                                   "class": j["verdict"]["class"],
                                   "rule": j["verdict"]["rule"], "from": moved.get("from"),
                                   "to": state, "reason": reason[:500],
                                   "step_up": True, "session": session_public_id[:64],
                                   "at": now.isoformat()}))
            approved.append({"id": row.id, "requirement_key": row.requirement_key,
                             "to": state})
        s.add(AuditLog(actor=actor[:64], action=BATCH_AUDIT_ACTION, at=now,
                       artifact=f"approve_all:{batch}",
                       detail={"approved": len(approved), "skipped": len(skipped),
                               "approved_ids": [a["id"] for a in approved][:500],
                               "excluded_by_category": current["excluded_by_category"],
                               "digest": current["digest"], "step_up": True,
                               "session": session_public_id[:64], "at": now.isoformat()}))
    return {"batch": batch, "approved_count": len(approved), "approved": approved,
            "skipped": skipped, "excluded_by_category": current["excluded_by_category"],
            "at": now.isoformat()}
