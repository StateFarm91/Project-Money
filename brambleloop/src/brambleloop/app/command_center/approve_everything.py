"""APPROVE-ALL-V2: the owner's "Approve everything I can decide (N)" (D-APPROVE-ALL-V2).

The v1 button (`approve_all`) approves only classifier-routine rows. In production every one of
those had already been closed by the hourly sweep, so it read "Approve all eligible (0)" over 98
open cards. The owner said: "I approve every single one ... Approve them all, whatever it takes."

This is the owner's own act, inside the existing owner session (passphrase + TOTP login), behind
a FRESH step-up (`auth.require_stepup`, enforced by the route, consumed after use) and one
confirm on the exact list (`preview` -> `digest` -> `execute(expected_digest=...)`). It never
bypasses the session, the step-up, CSRF or the nonce.

What one press does, in ONE database transaction (every write below or none of them):

* **routine**: the v1 set, unchanged (`approve_all.judge` / `approve_all._target`);
* **spend above ceiling**: each row approved at its stated `max_cost_cad`, in id order, while
  month-to-date ceiling-governed spend + the amounts approved so far stay within the company
  hard cap `finance.spend_policy.ceiling_cad()` (CA$100/month). A row that would cross it, a row
  with no stated amount and any `spend.ceiling.*` raise stay open with the reason. The cap is
  read, never written; nothing here spends -- each spend path's own guard still runs;
* **owner only**: only decision-type cards whose decision this app records
  (`improve.upgrade:<id>`, `improve.league:<id>`, through the same functions as their single
  doors). Acts that happen outside this app (OAuth consent, KYC, legal, banking, external policy
  attestation, credentials, readings) stay open and are listed as "do it at <link>";
* **public publishing**: per-release grants signed through the existing signing path
  (`publication_authority.approve` / `activation_authority.approve` with the operator
  credential, exactly as `approvals.execute` does for one card), each bound to the content
  digest the owner previewed; a publication grant also needs `_require_publication_evidence`.
  A release with an open child-safety row is never signed;
* **physical-sample cards**: closed as resolved by the owner directive
  D-OWNER-PUBLISH-WITH-RENDERS -- state `withdrawn`, resolution
  `owner_directed_without_attestation`, `attested: false`, `sample_exists: false`. Never
  `satisfied`, so `standing_internal.owner_closed` never reads one as an owner attestation.

Never in any bulk: child-safety rows (by classifier, by key guard, or by the row's own text) and
any attestation that a person physically made, measured or photographed something (the key
guard's physical subjects that are not one of the sample cards, `physical_size_conflict:`).

Cards that are not OwnerAction rows (executor gates, grant cards, policy reviews, the release
card) are not owner-queue rows: they are counted apart (`not_owner_action_rows`) and removed
from the owner's Approvals counts; publication and activation cards are what the
public-publishing class signs.
"""
from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone

from ...authority import standing_internal as SI
from . import approve_all as AA

STEP_UP_ACTION = "owner_queue.approve_everything"
ROW_AUDIT_ACTION = "owner_action.approve_everything"
BATCH_AUDIT_ACTION = "owner_queue.approve_everything"
SPEND_AUDIT_ACTION = "owner.spend.approved"
GRANT_AUDIT_ACTION = "owner.grant.approve_everything"
DIRECTIVE_RENDERS = "D-OWNER-PUBLISH-WITH-RENDERS"
WITHOUT_ATTESTATION = "owner_directed_without_attestation"

# ---- what a press does with each row (acted) ----------------------------------------------
ROUTINE = "routine"
SPEND = "spend_approved"
DECISION = "owner_decision"
PUBLICATION_GRANT = "publication_grant"
ACTIVATION_GRANT = "activation_grant"
PHYSICAL_DIRECTIVE = "physical_sample_closed_by_directive"
ACTED = (ROUTINE, SPEND, DECISION, PUBLICATION_GRANT, ACTIVATION_GRANT, PHYSICAL_DIRECTIVE)

# ---- what stays open (listed, with the reason) ----------------------------------------------
NEVER_CHILD = "never_bulk_child_safety"
NEVER_PHYSICAL = "never_bulk_physical_attestation"
OUTSIDE = "do_it_outside_this_app"
SPEND_OVER_CAP = "spend_over_company_cap"
SPEND_NO_AMOUNT = "spend_amount_not_stated"
SPEND_CEILING_RAISE = "spend_ceiling_raise"
PUBLISHING_COVERED = "publishing_row_covered_by_grant"
OWN_CARD = "needs_its_own_card"
KEPT = (NEVER_CHILD, NEVER_PHYSICAL, OUTSIDE, SPEND_OVER_CAP, SPEND_NO_AMOUNT,
        SPEND_CEILING_RAISE, PUBLISHING_COVERED, OWN_CARD)

KEPT_REASONS = {
    NEVER_CHILD: "a child-safety hold is its own card, released only by a ruling on that "
                 "product with its evidence; never in any bulk",
    NEVER_PHYSICAL: "says a person physically made, measured or photographed something; no "
                    "button can attest that",
    OUTSIDE: "the act happens outside this app (OAuth consent, KYC, legal, banking, external "
             "policy attestation, a credential or a reading); do it at the link and the "
             "producer closes the card",
    SPEND_OVER_CAP: "approving it would take this month past the CA$100/month company hard cap",
    SPEND_NO_AMOUNT: "no stated amount: it cannot be approved 'at its stated amount'",
    SPEND_CEILING_RAISE: "asks to raise a ceiling; the company hard cap is fixed in code",
    PUBLISHING_COVERED: "its release's grant is signed in this press; the card closes itself "
                        "when the grant is used",
    OWN_CARD: "needs a choice, a ruling, a buyer message or a gate this press cannot decide",
}

# Sample cards the directive closes (a make, a swatch, a calibration sample). Anything else the
# physical guard catches is an attestation and stays.
SAMPLE_PREFIXES = ("physical_evidence:", "physical_review:")
SAMPLE_EXACT = ("physical_calibration",)
# Decisions this app records, through the same function as the card's own door.
DECISION_PREFIXES = {"improve.upgrade:": "improvement", "improve.league:": "challenger"}
# Publication-class keys whose act is in Etsy Shop Manager, not here.
_OUTSIDE_PUB = ("etsy_surface:", "store:OA-", "storefront.asset:", "etsy.exercise.stranded_draft.")
# Owner-only classes whose act is outside this app.
_OUTSIDE_CLASSES = (SI.KYC_LEGAL_BANKING, SI.POLICY_ATTESTATION, SI.GRANT_SIGNATURE,
                    SI.PHYSICAL_EVIDENCE)
# Text guard on the row's own words: a child-safety subject anywhere keeps the row out.
_CHILD_TEXT = re.compile(r"child|small[ _-]?parts?|choking|(^|[^a-z])(toys?|baby|infant)"
                         r"($|[^a-z])", re.I)

SHOP_MANAGER = "https://www.etsy.com/your/shops/me/dashboard"
ETSY_DEVELOPERS = "https://www.etsy.com/developers/your-apps"


def _now(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _cap_cad() -> float:
    from ...finance.spend_policy import ceiling_cad

    return float(ceiling_cad())


def _spent_cad(db, now: datetime) -> float:
    from ...gateway import routing

    return float(routing.spent_this_month(db, now))


def _link(row_id: int, key: str, klass: str) -> dict:
    k = key or ""
    if k in ("etsy.auth:reauthorise", "reauthorise_transactions_r"):
        ext, where = None, "Store tab: reconnect Etsy (OAuth consent by the account holder)"
    elif k in ("benchmark_observation",) or "developer_portal" in k:
        ext, where = ETSY_DEVELOPERS, "Etsy developer portal"
    elif k.startswith(("etsy", "store:", "payout", "storefront", "policy_violation")):
        ext, where = SHOP_MANAGER, "Etsy Shop Manager"
    elif klass == SI.KYC_LEGAL_BANKING:
        ext, where = None, "the provider's account, legal or billing page named on the card"
    else:
        ext, where = None, "the provider or host named on the card"
    return {"card": f"#/approvals/owner_action:{row_id}", "external": ext, "where": where}


def route(row, *, spend_headroom: float | None = None) -> dict:
    """Where one open OwnerAction row goes. Pure (no database): child safety and physical
    attestation are decided first, before any class can act on a row."""
    key = row.requirement_key or ""
    j = AA.judge(key)
    verdict, cat = j["verdict"], j["category"]
    klass = verdict["class"]
    text = f"{key} {row.action or ''}"
    out = {"category_v1": cat if not j["eligible"] else "eligible", "class": klass}
    # 1. never in any bulk: child safety (classifier, key guard, or the row's own words).
    if cat == AA.CHILD_SAFETY or AA.guard(key) == AA.CHILD_SAFETY or _CHILD_TEXT.search(text):
        return {**out, "bucket": NEVER_CHILD}
    # 2. the sample cards the owner's directive closes; every other physical subject is an
    #    attestation and stays.
    if key.startswith(SAMPLE_PREFIXES) or key in SAMPLE_EXACT:
        return {**out, "bucket": PHYSICAL_DIRECTIVE}
    if key.startswith("physical_size_conflict:") or AA.guard(key) == AA.PHYSICAL_SAMPLE:
        return {**out, "bucket": NEVER_PHYSICAL}
    if klass == SI.PHYSICAL_EVIDENCE:      # a reading or screenshot only a person can take
        return {**out, "bucket": OUTSIDE, "link": _link(row.id, key, klass)}
    # 3. the v1 routine set.
    if j["eligible"]:
        return {**out, "bucket": ROUTINE}
    # 4. spend above ceiling: at its stated amount, inside the company hard cap.
    if cat == AA.SPEND_ABOVE_CEILING:
        if key.startswith("spend.ceiling."):
            return {**out, "bucket": SPEND_CEILING_RAISE}
        basis = (getattr(row, "max_cost_basis", None) or "stated")
        amount = row.max_cost_cad
        if basis != "stated" or amount is None or float(amount) < 0:
            return {**out, "bucket": SPEND_NO_AMOUNT}
        amount = round(float(amount), 2)
        if spend_headroom is None or amount > spend_headroom + 1e-9:
            return {**out, "bucket": SPEND_OVER_CAP, "amount_cad": amount}
        return {**out, "bucket": SPEND, "amount_cad": amount}
    # 5. public publishing: rows are covered by the release grants signed in this press.
    if cat == AA.PUBLIC_PUBLISHING:
        if key.startswith(_OUTSIDE_PUB):
            return {**out, "bucket": OUTSIDE, "link": _link(row.id, key, klass)}
        if key.startswith("first_public_listing:"):
            return {**out, "bucket": PUBLISHING_COVERED, "covered_by": ACTIVATION_GRANT}
        if key.startswith("standing_policy.hold:"):
            scope = key.split(":", 2)[1] if key.count(":") >= 1 else ""
            return {**out, "bucket": PUBLISHING_COVERED, "covered_by": PUBLICATION_GRANT,
                    "scope": scope}
        return {**out, "bucket": OWN_CARD}
    # 6. owner only: decision-type cards this app records; outside acts get their link.
    for prefix, kind in DECISION_PREFIXES.items():
        tail = key[len(prefix):]
        if key.startswith(prefix) and tail.isdigit():
            return {**out, "bucket": DECISION, "decision": kind, "target_id": int(tail)}
    if klass in _OUTSIDE_CLASSES:
        return {**out, "bucket": OUTSIDE, "link": _link(row.id, key, klass)}
    return {**out, "bucket": OWN_CARD}


def _open_rows(s):
    return AA._open_rows(s)


def _open_child_slugs(rows) -> set[str]:
    """Slugs named by an open child-safety row: their releases are never signed in bulk."""
    out = set()
    for r in rows:
        key = r.requirement_key or ""
        if key.startswith("childrens-decision:") or AA.guard(key) == AA.CHILD_SAFETY:
            tail = key.split(":", 1)[1] if ":" in key else ""
            out.add(tail.split("@", 1)[0])
    return {s for s in out if s}


def _grant_candidates(db, child_slugs: set[str]) -> tuple[list[dict], list[dict]]:
    """(to sign, kept) per-release grants, each with the content digest it will bind."""
    from ...ops import activation_authority as act
    from ...ops import publication_authority as pub
    from . import approvals

    sign, kept = [], []
    for kind, cards, mod in ((PUBLICATION_GRANT, approvals._publication_cards(db), pub),
                             (ACTIVATION_GRANT, approvals._activation_cards(db), act)):
        for c in cards:
            approve = next((a for a in c.get("actions") or []
                            if a["action"] in ("publication.approve", "activation.approve")),
                           None)
            if approve is None or not c.get("executable"):
                continue                     # not ready: stays on its own card (not counted)
            p = approve["params"]
            slug, version, release = p["slug"], p["version"], p.get("release", "")
            base = {"bucket": kind, "card_id": c["card_id"], "slug": slug,
                    "version": version, "release": release, "title": c.get("title")}
            if slug in child_slugs:
                kept.append({**base, "bucket": NEVER_CHILD,
                             "reason": KEPT_REASONS[NEVER_CHILD]})
                continue
            # Already a live grant for this release: nothing to sign.
            if any(a["action"].endswith(".execute") for a in c.get("actions") or []):
                continue
            try:
                content = mod.snapshot(db, slug, version, release)
            except Exception as exc:  # noqa: BLE001 - unreadable content is never signed
                kept.append({**base, "bucket": OWN_CARD,
                             "reason": f"content unreadable: {type(exc).__name__}"})
                continue
            sign.append({**base, "digest": mod.digest(content)})
    return sign, kept


def _not_owner_cards(db) -> tuple[list[dict], int, str | None]:
    """Inbox cards that are not OwnerAction rows (never owner-queue rows), and the number of
    owner_action cards the inbox shows."""
    try:
        from . import approvals

        cards = approvals.inbox(db).get("cards") or []
    except Exception as exc:  # noqa: BLE001 - unreadable is said, never read as empty
        return [], 0, f"approval inbox unreadable: {type(exc).__name__}"
    other = [{"card_id": c.get("card_id"), "kind": c.get("kind"), "title": c.get("title")}
             for c in cards if not str(c.get("card_id") or "").startswith("owner_action:")]
    return other, len(cards) - len(other), None


def _digest(items: list[dict]) -> str:
    body = json.dumps(sorted([[i["bucket"], str(i.get("id") or i.get("card_id")),
                               i.get("requirement_key") or "", i.get("to") or "",
                               i.get("amount_cad"), i.get("digest") or ""] for i in items],
                             key=lambda x: (x[0], x[1])), separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def preview(db, *, now: datetime | None = None, include_cards: bool = True) -> dict:
    """The exact list one press acts on, what stays and why, the counts, and the digest."""
    now = _now(now)
    cap = _cap_cad()
    try:
        spent = _spent_cad(db, now)
        headroom = round(max(0.0, cap - spent), 2)
        spend_error = None
    except Exception as exc:  # noqa: BLE001 - unreadable spend approves no spend
        spent, headroom = None, None
        spend_error = f"month-to-date spend unreadable: {type(exc).__name__}"
    acted, kept = [], []
    with db.session() as s:
        rows = _open_rows(s)
        child_slugs = _open_child_slugs(rows)
        left = headroom
        for row in rows:
            r = route(row, spend_headroom=left)
            item = {"id": row.id, "requirement_key": row.requirement_key,
                    "title": (row.action or "")[:200], **r}
            if r["bucket"] == ROUTINE:
                item["to"], item["why"] = AA._target(row, AA.judge(row.requirement_key)
                                                     ["verdict"], now=now)
            elif r["bucket"] == SPEND:
                left = round(left - r["amount_cad"], 2)
                item["to"] = "satisfied"
            elif r["bucket"] == DECISION:
                item["to"] = "satisfied"
            elif r["bucket"] == PHYSICAL_DIRECTIVE:
                item["to"] = "withdrawn"
            (acted if r["bucket"] in ACTED else kept).append(item)
    grants, grant_kept = _grant_candidates(db, child_slugs)
    acted += grants
    kept += grant_kept
    signed_pub = {f"{g['slug']}@{g['version']}" for g in grants
                  if g["bucket"] == PUBLICATION_GRANT}
    signed_act = any(g["bucket"] == ACTIVATION_GRANT for g in grants)
    for k in kept:                           # a publishing row with no grant to cover it
        if k["bucket"] == PUBLISHING_COVERED and not (
                (k.get("covered_by") == ACTIVATION_GRANT and signed_act)
                or (k.get("covered_by") == PUBLICATION_GRANT
                    and k.get("scope") in signed_pub)):
            k["bucket"] = OWN_CARD
    for k in kept:
        k.setdefault("reason", KEPT_REASONS[k["bucket"]])
    others, inbox_owner_cards, cards_error = (
        _not_owner_cards(db) if include_cards else ([], None, None))
    by_bucket = {b: 0 for b in ACTED + KEPT}
    for i in acted + kept:
        by_bucket[i["bucket"]] += 1
    owner_rows = sum(1 for i in acted + kept if "id" in i)
    spend_total = round(sum(i.get("amount_cad") or 0 for i in acted if i["bucket"] == SPEND), 2)
    return {"read_only": True, "as_of": now.isoformat(), "step_up_required": True,
            "step_up_action": STEP_UP_ACTION, "confirm_required": True,
            "count": len(acted), "acted": acted, "kept": kept,
            "kept_count": len(kept), "by_bucket": by_bucket,
            "kept_reasons": dict(KEPT_REASONS), "digest": _digest(acted),
            "spend": {"company_cap_cad": cap, "month_to_date_cad": spent,
                      "headroom_cad": headroom, "approved_in_press_cad": spend_total,
                      "error": spend_error,
                      "rule": "approved at each row's stated amount while month-to-date + "
                              "approved stays within the cap; the cap is never raised"},
            # What the owner's Approvals view counts: OwnerAction rows only.
            "counts": {"owner_rows_open": owner_rows,
                       "can_decide_now": len(acted),
                       "stays_with_reason": sum(1 for k in kept if "id" in k),
                       "not_owner_action_rows": (len(others) if include_cards else None),
                       "inbox_owner_action_cards": inbox_owner_cards},
            "not_owner_action_rows": others, "cards_error": cards_error,
            "directive": DIRECTIVE_RENDERS}


class Refused(ValueError):
    pass


class _OneTransaction:
    """`db` whose every `session()` is the one open session: the existing single-card doors
    (publication/activation `approve`, `cells.record_owner_approval`, `league`) write into
    the press's transaction, so a failure anywhere rolls every write back."""

    def __init__(self, db, s):
        self._db, self._s = db, s

    @contextmanager
    def session(self):
        yield self._s
        self._s.flush()

    def __getattr__(self, name):
        return getattr(self._db, name)


def _reason(base: str, extra: str = "") -> str:
    tail = f"; {extra}" if extra else ""
    return (f"approved by the owner with 'Approve everything I can decide' (fresh step-up): "
            f"{base}{tail}")[:1000]


def execute(db, *, actor: str, expected_digest: str, confirm: bool,
            session_public_id: str = "", now: datetime | None = None) -> dict:
    """One press. The CALLER enforces the owner session and the fresh step-up."""
    from sqlalchemy import select

    from ...core.models import AuditLog, OwnerAction
    from ...ops import activation_authority as act
    from ...ops import owner_queue
    from ...ops import publication_authority as pub
    from . import approvals

    now = _now(now)
    if not actor.startswith("owner:"):
        raise Refused("only an owner session may approve the owner queue")
    if confirm is not True:
        raise Refused("confirm the exact list first")
    current = preview(db, now=now, include_cards=False)
    if not expected_digest or expected_digest != current["digest"]:
        raise Refused("the list changed since your preview; review it again "
                      f"({current['count']} now)")
    if any(i["bucket"] == SPEND for i in current["acted"]) and current["spend"]["error"]:
        raise Refused(current["spend"]["error"])
    batch = current["digest"][:16]
    done: list[dict] = []
    common = {"batch": batch, "step_up": True, "session": session_public_id[:64],
              "at": now.isoformat(), "directive": "D-APPROVE-ALL-V2"}
    try:
        ops_token = approvals._ops_token() if any(
            i["bucket"] in (PUBLICATION_GRANT, ACTIVATION_GRANT) for i in current["acted"]) \
            else ""
    except KeyError:
        raise Refused("operator credential not configured; no grant can be signed") from None
    with db.session() as s:
        from ...runtime.release import _serialise_owner_queue

        _serialise_owner_queue(s, db)
        one = _OneTransaction(db, s)
        ids = [i["id"] for i in current["acted"] if "id" in i]
        rows = {r.id: r for r in s.scalars(select(OwnerAction).where(OwnerAction.id.in_(ids)))}
        cap, left = current["spend"]["company_cap_cad"], current["spend"]["headroom_cad"]
        for item in current["acted"]:
            b = item["bucket"]
            if b in (PUBLICATION_GRANT, ACTIVATION_GRANT):
                mod = pub if b == PUBLICATION_GRANT else act
                body = {"slug": item["slug"], "version": item["version"],
                        "release": item["release"]}
                why = _reason(f"{item['card_id']} bound to content {item['digest'][:16]}")
                try:
                    if mod is pub:
                        approvals._require_publication_evidence(one, body)
                    g = mod.approve(one, authorization=ops_token, slug=item["slug"],
                                    version=item["version"], release=item["release"],
                                    expected_digest=item["digest"], reason=why)
                except Exception as exc:  # noqa: BLE001 - one refusal refuses the press
                    raise Refused(f"{item['card_id']}: {str(exc)[:300]}") from None
                s.add(AuditLog(actor=actor[:64], action=GRANT_AUDIT_ACTION, at=now,
                               artifact=f"{item['slug']}@{item['version']}"[:200],
                               detail={**common, "grant": b, "approval_id": g["approval_id"],
                                       "digest": g["digest"], "release": item["release"],
                                       "expires_at": g["expires_at"]}))
                done.append({"bucket": b, "card_id": item["card_id"],
                             "approval_id": g["approval_id"]})
                continue
            row = rows.get(item["id"])
            if row is None or owner_queue.effective_state(row) not in (owner_queue.OPEN,
                                                                        owner_queue.PARKED):
                raise Refused(f"owner action {item['id']} is no longer open; review again")
            again = route(row, spend_headroom=left)      # re-judged at the write
            if again["bucket"] != b:
                raise Refused(f"owner action {row.id} changed class ({again['bucket']})")
            detail = {**common, "bucket": b, "requirement_key": row.requirement_key,
                      "class": again["class"]}
            if b == ROUTINE:
                state, reason = AA._target(row, AA.judge(row.requirement_key)["verdict"],
                                           now=now)
            elif b == SPEND:
                amount = again["amount_cad"]
                left = round(left - amount, 2)
                if left < -1e-9:                          # belt and braces: never past the cap
                    raise Refused("the company hard cap would be crossed; nothing approved")
                state = owner_queue.SATISFIED
                reason = _reason(f"spend approved at its stated CA${amount:.2f}",
                                 f"company cap CA${cap:.2f}/month unchanged")
                s.add(AuditLog(actor=actor[:64], action=SPEND_AUDIT_ACTION, at=now,
                               artifact=f"owner_action:{row.id}",
                               detail={**detail, "amount_cad": amount,
                                       "company_cap_cad": cap, "headroom_after_cad": left,
                                       "spends_nothing_itself": True}))
                detail["amount_cad"] = amount
            elif b == DECISION:
                why = _reason(f"{row.requirement_key}")
                try:
                    if again["decision"] == "improvement":
                        from ...improve import cells

                        cells.record_owner_approval(one, again["target_id"],
                                                    approved_by="owner", why=why)
                    else:
                        from ...improve import league

                        league.record_owner_decision(one, again["target_id"],
                                                     approved_by="owner", why=why)
                except Exception as exc:  # noqa: BLE001
                    raise Refused(f"{row.requirement_key}: {str(exc)[:300]}") from None
                state, reason = owner_queue.SATISFIED, why
            elif b == PHYSICAL_DIRECTIVE:
                state = owner_queue.WITHDRAWN
                reason = (f"{WITHOUT_ATTESTATION}: resolved by the owner directive "
                          f"{DIRECTIVE_RENDERS} (publish with renders; no physical sample "
                          f"will be made). NOT attested; no sample exists.")
                detail.update({"resolution": WITHOUT_ATTESTATION, "attested": False,
                               "sample_exists": False, "owner_directive": DIRECTIVE_RENDERS})
            else:  # pragma: no cover - ACTED is exhaustive
                raise Refused(f"unknown bucket {b}")
            moved = owner_queue.transition(s, row, state, reason, actor=actor, now=now)
            s.add(AuditLog(actor=actor[:64], action=ROW_AUDIT_ACTION, at=now,
                           artifact=f"owner_action:{row.id}",
                           detail={**detail, "from": moved.get("from"), "to": state,
                                   "reason": reason[:500]}))
            done.append({"bucket": b, "id": row.id, "requirement_key": row.requirement_key,
                         "to": state})
        tally = {b: sum(1 for d in done if d["bucket"] == b) for b in ACTED}
        s.add(AuditLog(actor=actor[:64], action=BATCH_AUDIT_ACTION, at=now,
                       artifact=f"approve_everything:{batch}",
                       detail={**common, "digest": current["digest"], "acted": len(done),
                               "by_bucket": tally, "kept_by_bucket": {
                                   b: current["by_bucket"][b] for b in KEPT},
                               "ids": [d.get("id") or d.get("card_id") for d in done][:500],
                               "spend_approved_cad": current["spend"]["approved_in_press_cad"],
                               "company_cap_cad": cap}))
    return {"batch": batch, "acted_count": len(done), "acted": done, "by_bucket": tally,
            "kept_count": current["kept_count"], "at": now.isoformat()}
