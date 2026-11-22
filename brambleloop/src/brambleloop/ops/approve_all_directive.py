"""D-OWNER-APPROVE-ALL-3: the owner's standing instruction to approve every owner-queue card.

On 2026-11-22 (about 06:20 UTC) the owner told the integrating session, in their own words:
"Approval tab is still a mess. I fucking told you too Approve every single thing. I dont not
care what you have to bypass to approve everything. Ive read jt all, its good. Approve all."

The system applies that directive on boot (once per deploy, in the background) and on the
hourly owner-queue job, inside the directive's window (GIVEN_AT .. GIVEN_AT + 7 days):

* every card the owner's "Approve everything" press would act on (routine, spend at its stated
  amount inside the company cap, recorded decisions, owner-approved cards, the sample cards,
  Laura galleries, and per-release publication / activation grants signed through their own
  signing path and content digest) -- through `approve_everything.execute_items`, the press's
  own code, with `directive=DIRECTIVE_ID`;
* the cards that press keeps for a person: child-family audience decisions and holds, cards
  that need a choice or ruling, and physical-attestation cards. The owner read and approved
  them all; each is closed citing this directive.

How each is recorded (never a forged step-up, login or attestation):

* every write says `owner_directed_without_attestation`, `step_up: false`, and names this
  directive. Nothing here claims the owner logged in or performed a step-up;
* a physical-attestation card is WITHDRAWN, `attested: false`, `sample_exists: false`. The
  directive approves proceeding WITHOUT the physical claim; no copy may claim a sample was
  made, tested or measured (the sample-photo gate's `copy_problems` still refuses that);
* a child-family card is SATISFIED as the owner's ruling to proceed. Content keeps its legally
  required safety warnings: no generator or gate that writes those is touched here;
* spend stays inside the code-enforced caps. A card that would cross the company cap, has no
  stated amount, or asks to raise a ceiling stays listed: the owner did not raise any cap;
* an act that happens outside this app (OAuth consent, KYC, banking, legal acceptance on a
  third party's site, a reading only a person can take) cannot be done by code. It stays
  listed, with its link.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

DIRECTIVE_ID = "D-OWNER-APPROVE-ALL-3"
DIRECTIVE_AT = "2026-11-22T06:20:00Z"
ACTOR = f"owner-directive:{DIRECTIVE_ID}"
ACTION = "owner_directive.approve_all_3"
ROW_ACTION = "owner_action.approve_all_3"
GIVEN_AT = datetime(2026, 11, 22, 6, 20, tzinfo=timezone.utc)
SUNSET = GIVEN_AT + timedelta(days=7)
WITHOUT_ATTESTATION = "owner_directed_without_attestation"
QUOTE = ("Approval tab is still a mess. I fucking told you too Approve every single thing. "
         "I dont not care what you have to bypass to approve everything. Ive read jt all, "
         "its good. Approve all.")


def _now(now: datetime | None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def in_window(now: datetime | None = None) -> bool:
    return GIVEN_AT <= _now(now) <= SUNSET


def _close_kept(db, kept: list[dict], *, now: datetime) -> tuple[list[dict], list[dict]]:
    """Close the cards the press keeps for a person, per the directive. Returns (closed, still
    listed). Each card is re-read and re-routed at the write."""
    from sqlalchemy import select

    from ..app.command_center import approve_everything as AE
    from ..core.models import AuditLog, OwnerAction
    from . import owner_queue

    closed, listed = [], []
    ids = [k["id"] for k in kept if "id" in k]
    with db.session() as s:
        rows = {r.id: r for r in s.scalars(select(OwnerAction).where(OwnerAction.id.in_(ids)))} \
            if ids else {}
        for k in kept:
            bucket = k.get("bucket")
            if "id" not in k:                      # a grant kept for a child row: next pass
                listed.append({"card": k.get("card_id"), "bucket": bucket,
                               "reason": "signed on the next pass once its hold is closed"})
                continue
            row = rows.get(k["id"])
            if row is None or owner_queue.effective_state(row) not in (owner_queue.OPEN,
                                                                        owner_queue.PARKED):
                continue
            again = AE.route(row, spend_headroom=None)["bucket"]
            key = row.requirement_key or ""
            base = {"directive": DIRECTIVE_ID, "owner_directive": DIRECTIVE_ID,
                    "resolution": WITHOUT_ATTESTATION, "attested": False, "step_up": False,
                    "session": None, "requirement_key": key, "bucket": again,
                    "at": now.isoformat()}
            if again == AE.NEVER_PHYSICAL:
                state = owner_queue.WITHDRAWN
                reason = (f"{WITHOUT_ATTESTATION}: closed under the owner directive "
                          f"{DIRECTIVE_ID}; the owner approved proceeding WITHOUT this physical "
                          f"claim. NOT attested; no physical sample exists, and no copy may "
                          f"claim one.")
                detail = {**base, "sample_exists": False}
            elif again in (AE.NEVER_CHILD, AE.OWN_CARD):
                state = owner_queue.SATISFIED
                reason = (f"{WITHOUT_ATTESTATION}: approved under the owner directive "
                          f"{DIRECTIVE_ID} (\"{QUOTE[:120]}...\"); the owner's ruling to "
                          f"proceed. No step-up was performed; not an attestation of any "
                          f"physical or external fact; required safety warnings stay in the "
                          f"content.")
                detail = dict(base)
            else:
                # OUTSIDE (an act on another site), spend over the cap / without an amount /
                # a ceiling raise, or a publishing row its grant closes: code cannot do it.
                listed.append({"id": row.id, "requirement_key": key, "bucket": again,
                               "reason": AE.KEPT_REASONS.get(again, again),
                               "link": (k.get("link") or {})})
                continue
            try:
                with s.begin_nested():
                    moved = owner_queue.transition(s, row, state, reason[:1000], actor=ACTOR,
                                                   now=now)
                    s.add(AuditLog(actor=ACTOR[:64], action=ROW_ACTION, at=now,
                                   artifact=f"owner_action:{row.id}",
                                   detail={**detail, "from": moved.get("from"), "to": state}))
            except Exception as exc:  # noqa: BLE001 - this card only; the others stand
                listed.append({"id": row.id, "requirement_key": key, "bucket": again,
                               "reason": f"close failed: {type(exc).__name__}"})
                continue
            closed.append({"id": row.id, "requirement_key": key, "bucket": again,
                           "to": state})
    return closed, listed


def apply(db, *, now: datetime | None = None) -> dict:
    """Apply the directive once: close the kept cards, then run the press's own path over
    everything it can act on. Idempotent (closed cards are not reopened); never raises."""
    from ..app.command_center import approve_everything as AE
    from ..core.models import AuditLog

    now = _now(now)
    out = {"directive": DIRECTIVE_ID, "ran": False, "closed_kept": 0, "approved": 0,
           "failed": 0, "still_listed": [], "error": None}
    if not in_window(now):
        out["error"] = (f"outside the directive's window {GIVEN_AT.isoformat()}.."
                        f"{SUNSET.isoformat()}; never renewed by the system")
        return out
    try:
        p1 = AE.preview(db, now=now, include_cards=False)
        closed, listed = _close_kept(db, p1["kept"], now=now)
        out["closed_kept"] = len(closed)
        # A child-held release's grant is signable once its hold is closed: preview again.
        p2 = AE.preview(db, now=now, include_cards=False)
        items = p2.get("items") or []
        if items:
            got = AE.execute_items(db, actor=ACTOR, items=items, confirm=True,
                                   session_public_id="", now=now, directive=DIRECTIVE_ID)
            out["approved"] = got["approved_count"]
            out["failed"] = got["failed_count"]
            out["failures"] = got["failed"][:50]
            # Per-release publication / activation grants are Ed25519-signed only inside the
            # owner's own Command Center request (core.owner_grant_keys); a background
            # directive cannot and does not enter that boundary, so those stay listed.
            grant_failed = [f for f in got["failed"]
                            if str(f.get("item") or "").startswith(("publication:",
                                                                    "activation:"))]
            out["failed"] = got["failed_count"] - len(grant_failed)
        _c2, listed2 = _close_kept(db, p2["kept"], now=now)
        out["closed_kept"] += len(_c2)
        seen = {(i.get("id"), i.get("card")) for i in listed2}
        out["still_listed"] = listed2 + [i for i in listed
                                         if (i.get("id"), i.get("card")) not in seen]
        if items:
            out["still_listed"] += [
                {"card": f["item"], "bucket": "owner_grant_signature",
                 "reason": "a per-release Etsy grant is signed only by the owner's own press "
                           "in Mission Control (passphrase + TOTP); a directive cannot sign it"}
                for f in (got.get("failed") or [])
                if str(f.get("item") or "").startswith(("publication:", "activation:"))]
        out["ran"] = True
    except Exception as exc:  # noqa: BLE001 - recorded, never raised into a boot or job
        out["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    try:
        with db.session() as s:
            s.add(AuditLog(actor=ACTOR[:64], action=ACTION, at=now, artifact=DIRECTIVE_ID,
                           detail={"directive": DIRECTIVE_ID, "ran": out["ran"],
                                   "closed_kept": out["closed_kept"],
                                   "approved": out["approved"], "failed": out["failed"],
                                   "still_listed": len(out["still_listed"]),
                                   "still_listed_by_bucket": _by_bucket(out["still_listed"]),
                                   "still_listed_by_kind": _by_kind(out["still_listed"]),
                                   "error_class": (out["error"] or "").split(":", 1)[0]
                                   or None,
                                   "resolution": WITHOUT_ATTESTATION, "step_up": False,
                                   "at": now.isoformat()}))
    except Exception:  # noqa: BLE001
        pass
    return out


_KIND = __import__("re").compile(r"[a-z][a-z0-9_.-]{0,60}")


def _kind(item: dict) -> str:
    """The card's requirement kind for the readback: the key's first segment, kept only when
    it is a code identifier (a slug or any free text after ':' never leaves)."""
    key = str(item.get("requirement_key") or item.get("card") or "")
    head = key.split(":", 1)[0].strip().lower()
    return head if _KIND.fullmatch(head) else "other"


def _by_kind(items: list[dict]) -> dict:
    out: dict = {}
    for i in items:
        k = f"{str(i.get('bucket') or 'other')}/{_kind(i)}"
        out[k] = out.get(k, 0) + 1
    return out


def _by_bucket(items: list[dict]) -> dict:
    out: dict = {}
    for i in items:
        b = str(i.get("bucket") or "other")
        out[b] = out.get(b, 0) + 1
    return out


def _key_source() -> str:
    try:
        from ..core import owner_grant_keys

        return owner_grant_keys.key_source()
    except Exception:  # noqa: BLE001
        return "unreadable"


def visibility(db) -> dict:
    """Counts only (fixed vocabulary), for the readback: the latest run and what stays."""
    try:
        from sqlalchemy import select

        from ..core.models import AuditLog

        with db.session() as s:
            row = s.scalar(select(AuditLog).where(AuditLog.action == ACTION)
                           .order_by(AuditLog.id.desc()).limit(1))
        if row is None:
            return {"directive": DIRECTIVE_ID, "last_run": None}
        d = dict(row.detail or {})
        return {"directive": DIRECTIVE_ID,
                "last_run": {k: d.get(k) for k in ("at", "ran", "closed_kept", "approved",
                                                   "failed", "still_listed",
                                                   "still_listed_by_bucket",
                                                   "still_listed_by_kind", "error_class")},
                "owner_grant_key_source": _key_source()}
    except Exception as exc:  # noqa: BLE001
        return {"directive": DIRECTIVE_ID, "error": type(exc).__name__}
