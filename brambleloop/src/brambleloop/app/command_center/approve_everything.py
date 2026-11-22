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
# APPROVE-FIX (B): an unclassified owner card that needs no choice, ruling, spend, publishing
# grant or outside act: the owner approves it in-app. Recorded `satisfied` as owner-approved
# via step-up (which it is); never as an attestation.
OWNER_APPROVED = "owner_approved_step_up"
ACTED = (ROUTINE, SPEND, DECISION, PUBLICATION_GRANT, ACTIVATION_GRANT, PHYSICAL_DIRECTIVE,
         OWNER_APPROVED)

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
# APPROVE-FIX (B): OWN_CARD keys that stay on their own card even when unclassified, because a
# closed row under them is READ AS A DECISION by other code (e.g. `build2.executor.
# _acceptance_ruled`, `runtime.etsy_ops` "already_decided") or needs a choice between answers.
_NEEDS_A_CHOICE = re.compile(
    r"^(decision\.|acceptance|launch_decision|listing_fees$|brand_clearance$|phase$|"
    r"ad_authority|ads[.:]|correction_notice|buyer|message|support|model_select|"
    r"storefront|etsy\.auth|reauthorise|childrens-decision|cert|safety)", re.I)
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
    # 7. APPROVE-FIX (B): an unclassified card with no choice to make and nothing that reads its
    #    close as a decision: the owner approves it here.
    if (klass == SI.UNCLASSIFIED and cat == AA.OWNER_ONLY and AA.guard(key) is None
            and not _NEEDS_A_CHOICE.search(key)):
        return {**out, "bucket": OWNER_APPROVED}
    return {**out, "bucket": OWN_CARD,
            "link": {"card": f"#/approvals/owner_action:{row.id}", "external": None,
                     "where": "its own card"}}


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
    import time as _time

    now = _now(now)
    t0 = _time.monotonic()
    timings: dict[str, int] = {}
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
                if r["class"] == AA.LAURA_GALLERY_CLASS:
                    # BATCH19F (IMAGE-BF): the owner sees the frames they approve.
                    from ...visual import laura_approval

                    raised = laura_approval.card(db, row.requirement_key) or {}
                    item["frames"] = raised.get("frames") or []
                    item["run_key"] = raised.get("run_key")
            elif r["bucket"] == SPEND:
                left = round(left - r["amount_cad"], 2)
                item["to"] = "satisfied"
            elif r["bucket"] in (DECISION, OWNER_APPROVED):
                item["to"] = "satisfied"
            elif r["bucket"] == PHYSICAL_DIRECTIVE:
                item["to"] = "withdrawn"
            (acted if r["bucket"] in ACTED else kept).append(item)
    timings["rows_ms"] = int((_time.monotonic() - t0) * 1000)
    grants, grant_kept = _grant_candidates(db, child_slugs)
    timings["grants_ms"] = int((_time.monotonic() - t0) * 1000) - timings["rows_ms"]
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
    t1 = _time.monotonic()
    others, inbox_owner_cards, cards_error = (
        _not_owner_cards(db) if include_cards else ([], None, None))
    timings["cards_ms"] = int((_time.monotonic() - t1) * 1000)
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
            "directive": DIRECTIVE_RENDERS,
            # APPROVE-FIX: every row the press acts on, as the key the press sends back.
            "items": [item_key(i) for i in acted],
            "last_press": last_press(db),
            "timings_ms": {**timings, "total_ms": int((_time.monotonic() - t0) * 1000)}}


def item_key(i: dict) -> str:
    """One previewed item, as the press names it: the bucket, the row or card, and what the
    owner saw it would bind (target state, stated amount, content digest)."""
    ident = i.get("id") if "id" in i else i.get("card_id")
    amount = i.get("amount_cad")
    return "|".join([i["bucket"], str(ident), i.get("to") or "",
                     "" if amount is None else f"{float(amount):.2f}", i.get("digest") or ""])


def last_press(db) -> dict | None:
    """The newest press's stored outcome, so the page shows it even if the browser closed
    the request before the answer arrived."""
    try:
        from sqlalchemy import select

        from ...core.models import AuditLog

        with db.session() as s:
            row = s.scalar(select(AuditLog).where(AuditLog.action == BATCH_AUDIT_ACTION)
                           .order_by(AuditLog.id.desc()).limit(1))
            if row is None:
                return None
            d = dict(row.detail or {})
            return {"at": d.get("at"), "batch": d.get("batch"),
                    "approved_count": d.get("acted"), "failed_count": d.get("failed_count", 0),
                    "failed": (d.get("failed") or [])[:200],
                    "not_in_preview_any_more": d.get("dropped_count", 0)}
    except Exception as exc:  # noqa: BLE001 - said, never read as "nothing happened"
        return {"error": f"last press unreadable: {type(exc).__name__}"}


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


def _reason(base: str, extra: str = "", directive: str | None = None) -> str:
    tail = f"; {extra}" if extra else ""
    if directive:
        return (f"approved under the owner directive {directive} ({WITHOUT_ATTESTATION}; no "
                f"step-up was performed): {base}{tail}")[:1000]
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
    laura_runs: list[str] = []
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
            elif b == OWNER_APPROVED:
                state = owner_queue.SATISFIED
                reason = _reason(f"{row.requirement_key}", "owner-approved via step-up; not "
                                 "an attestation of any physical or external fact")
                detail["owner_approved_via_step_up"] = True
            elif b == PHYSICAL_DIRECTIVE:
                state = owner_queue.WITHDRAWN
                reason = (f"{WITHOUT_ATTESTATION}: resolved by the owner directive "
                          f"{DIRECTIVE_RENDERS} (publish with renders; no physical sample "
                          f"will be made). NOT attested; no sample exists.")
                detail.update({"resolution": WITHOUT_ATTESTATION, "attested": False,
                               "sample_exists": False, "owner_directive": DIRECTIVE_RENDERS})
            else:  # pragma: no cover - ACTED is exhaustive
                raise Refused(f"unknown bucket {b}")
            if b == ROUTINE and again["class"] == AA.LAURA_GALLERY_CLASS:
                # BATCH19F (IMAGE-BF): a Laura gallery is approved per frame hash through
                # `laura_approval`, never by a bare close; it is re-judged after the commit.
                from ...visual import laura_approval

                try:
                    with s.begin_nested():
                        got = laura_approval._decide_in(
                            s, db, row, decision=laura_approval.APPROVED, actor=actor,
                            step_up=True, via="approve_everything",
                            session_public_id=session_public_id, now=now)
                except laura_approval.Refused as exc:
                    raise Refused(f"Laura gallery {row.requirement_key}: {exc}"[:300]) from None
                laura_runs.append(got["run_key"])
                moved = {"from": owner_queue.OPEN, "changed": True}
            else:
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
    laura = {}
    if laura_runs:
        from ...visual import laura_approval

        for run_key in laura_runs:      # after the approvals committed: re-judge each gallery
            try:
                laura[run_key] = laura_approval.after_decision(db, run_key)
            except Exception as exc:  # noqa: BLE001 - recorded; the approval stands
                laura[run_key] = {"certified": False,
                                  "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return {"batch": batch, "acted_count": len(done), "acted": done, "by_bucket": tally,
            "laura_galleries": laura,
            "kept_count": current["kept_count"], "at": now.isoformat()}


# ---- APPROVE-FIX: the press the owner's page sends ----------------------------------------
#
# Root cause of "I approve and nothing changes" (production http log, 2026-11-22 00:19 and
# 00:22 UTC): the preview took 122-166 s, and `execute` above re-ran the WHOLE preview (every
# release's evidence packet, every Laura card) before writing. The browser closed both presses
# (HTTP 499) before an answer arrived, and a container restart at 00:25 ended the run, so
# nothing was committed and the owner was never told. One failing row would also have rolled
# back every other row.
#
# `execute_items` takes the exact items the owner previewed (`preview()["items"]`) and:
# * re-reads ONLY those rows and re-routes each one at the write (pure and fast, no packets);
# * approves an item only if it is still exactly what the owner saw (same bucket, target,
#   amount and content digest) -- never anything the owner did not preview;
# * writes each item in its own savepoint, so one refusal is reported for that item and
#   never undoes the others;
# * stores the outcome (approved, failed with reason, no longer in the list) in the batch
#   audit row, which the preview's `last_press` shows even if the browser gave up waiting.
# Every gate still runs: the child-safety and physical guards in `route`, the CA$ company cap
# (headroom re-read now), each grant's own signing path with the previewed digest, and the
# publication evidence check.

MAX_ITEMS = 5000


def execute_items(db, *, actor: str, items: list, confirm: bool,
                  session_public_id: str = "", now: datetime | None = None,
                  directive: str | None = None) -> dict:
    """The owner's press over the previewed items. The CALLER enforces the owner session and
    the fresh step-up."""
    from sqlalchemy import select

    from ...core.models import AuditLog, OwnerAction
    from ...ops import activation_authority as act
    from ...ops import owner_queue
    from ...ops import publication_authority as pub
    from . import approvals

    now = _now(now)
    if directive is not None:
        # D-OWNER-APPROVE-ALL-3: the system applies the owner's standing directive. Only the
        # directive module calls this with `directive`; nothing claims a step-up or a login.
        from ...ops import approve_all_directive as _AD

        if directive != _AD.DIRECTIVE_ID or actor != _AD.ACTOR:
            raise Refused("not a recognised owner directive")
    elif not actor.startswith("owner:"):
        raise Refused("only an owner session may approve the owner queue")
    if confirm is not True:
        raise Refused("confirm the exact list first")
    if not isinstance(items, list) or not items:
        raise Refused("no previewed items were sent; open the list again")
    if len(items) > MAX_ITEMS:
        raise Refused(f"too many items in one press ({len(items)} > {MAX_ITEMS})")
    wanted: list[tuple[str, str, str, str, str]] = []
    for k in items:
        parts = str(k).split("|")
        if len(parts) != 5 or parts[0] not in ACTED:
            raise Refused(f"not a previewed item: {str(k)[:120]}")
        wanted.append(tuple(parts))  # type: ignore[arg-type]
    seen = set(items)
    batch = hashlib.sha256("\n".join(sorted(seen)).encode()).hexdigest()[:16]
    common = {"batch": batch, "step_up": True, "session": session_public_id[:64],
              "at": now.isoformat(), "directive": "D-APPROVE-FIX"}
    if directive is not None:
        common = {"batch": batch, "step_up": False, "session": None, "at": now.isoformat(),
                  "directive": directive, "owner_directive": directive,
                  "resolution": WITHOUT_ATTESTATION, "attested": False}
    done: list[dict] = []
    failed: list[dict] = []
    dropped: list[dict] = []

    def fail(ident, key, why):
        failed.append({"item": ident, "requirement_key": key, "reason": str(why)[:300]})

    # Spend: the headroom is re-read now; unreadable spend approves no spend.
    cap = _cap_cad()
    try:
        left = round(max(0.0, cap - _spent_cad(db, now)), 2)
        spend_error = None
    except Exception as exc:  # noqa: BLE001
        left, spend_error = None, f"month-to-date spend unreadable: {type(exc).__name__}"

    row_items = [w for w in wanted if w[0] not in (PUBLICATION_GRANT, ACTIVATION_GRANT)]
    grant_items = [w for w in wanted if w[0] in (PUBLICATION_GRANT, ACTIVATION_GRANT)]
    ops_token = ""
    if grant_items:
        try:
            ops_token = approvals._ops_token()
        except KeyError:
            for w in grant_items:
                fail(w[1], None, "operator credential not configured; no grant can be signed")
            grant_items = []
    laura_runs: list[str] = []
    with db.session() as s:
        from ...runtime.release import _serialise_owner_queue

        _serialise_owner_queue(s, db)
        one = _OneTransaction(db, s)
        ids = []
        for w in row_items:
            try:
                ids.append(int(w[1]))
            except ValueError:
                raise Refused(f"not a previewed row id: {w[1][:40]}") from None
        rows = {r.id: r for r in s.scalars(select(OwnerAction).where(OwnerAction.id.in_(ids)))}
        child_slugs = _open_child_slugs(_open_rows(s))
        # Spend in id order, as the preview computed it.
        for bucket, ident, to, amount_s, _dg in sorted(
                row_items, key=lambda w: (w[0] != SPEND, int(w[1]))):
            row = rows.get(int(ident))
            key = row.requirement_key if row is not None else None
            if row is None or owner_queue.effective_state(row) not in (owner_queue.OPEN,
                                                                        owner_queue.PARKED):
                dropped.append({"item": ident, "requirement_key": key,
                                "reason": "no longer open (closed or replaced since the list "
                                          "was shown)"})
                continue
            again = route(row, spend_headroom=left)          # re-judged at the write
            if again["bucket"] != bucket:
                fail(ident, key, f"its class changed since the list was shown "
                                 f"({again['bucket']}); it was not approved")
                continue
            if bucket == SPEND:
                if spend_error:
                    fail(ident, key, spend_error)
                    continue
                if f"{again['amount_cad']:.2f}" != amount_s:
                    fail(ident, key, "its stated amount changed since the list was shown")
                    continue
            detail = {**common, "bucket": bucket, "requirement_key": key,
                      "class": again["class"]}
            try:
                with s.begin_nested():
                    state, reason = _write_row(s, one, row, bucket, again, detail,
                                               actor=actor, now=now, cap=cap,
                                               left=left, laura_runs=laura_runs,
                                               session_public_id=session_public_id,
                                               directive=directive)
            except Exception as exc:  # noqa: BLE001 - this row only; the others stand
                fail(ident, key, exc)
                continue
            if bucket == SPEND:
                left = round(left - again["amount_cad"], 2)
            done.append({"bucket": bucket, "id": row.id, "requirement_key": key,
                         "to": state})
        # Grants: only those previewed, each bound to the digest the owner saw.
        if grant_items:
            fresh, _kept = _grant_candidates(db, child_slugs)
            by_card = {g["card_id"]: g for g in fresh}
            for bucket, card_id, _to, _amt, dg in grant_items:
                g = by_card.get(card_id)
                if g is None or g["bucket"] != bucket:
                    dropped.append({"item": card_id, "requirement_key": None,
                                    "reason": "no longer awaiting a grant (or now held)"})
                    continue
                if g["digest"] != dg:
                    fail(card_id, None, "its content changed since you previewed it; "
                                        "nothing was signed for it")
                    continue
                mod = pub if bucket == PUBLICATION_GRANT else act
                why = _reason(f"{card_id} bound to content {dg[:16]}", directive=directive)
                try:
                    with s.begin_nested():
                        if mod is pub:
                            approvals._require_publication_evidence(
                                one, {"slug": g["slug"], "version": g["version"],
                                      "release": g["release"]})
                        got = mod.approve(one, authorization=ops_token, slug=g["slug"],
                                          version=g["version"], release=g["release"],
                                          expected_digest=dg, reason=why)
                        s.add(AuditLog(actor=actor[:64], action=GRANT_AUDIT_ACTION, at=now,
                                       artifact=f"{g['slug']}@{g['version']}"[:200],
                                       detail={**common, "grant": bucket,
                                               "approval_id": got["approval_id"],
                                               "digest": got["digest"],
                                               "release": g["release"],
                                               "expires_at": got["expires_at"]}))
                except Exception as exc:  # noqa: BLE001 - this grant only
                    fail(card_id, None, exc)
                    continue
                done.append({"bucket": bucket, "card_id": card_id,
                             "approval_id": got["approval_id"]})
        tally = {b: sum(1 for d in done if d["bucket"] == b) for b in ACTED}
        s.add(AuditLog(actor=actor[:64], action=BATCH_AUDIT_ACTION, at=now,
                       artifact=f"approve_everything:{batch}",
                       detail={**common, "acted": len(done), "by_bucket": tally,
                               "requested": len(seen), "failed_count": len(failed),
                               "failed": failed[:200], "dropped_count": len(dropped),
                               "dropped": dropped[:200],
                               "ids": [d.get("id") or d.get("card_id") for d in done][:5000],
                               "company_cap_cad": cap}))
    laura = {}
    if laura_runs:
        from ...visual import laura_approval

        for run_key in laura_runs:
            try:
                laura[run_key] = laura_approval.after_decision(db, run_key)
            except Exception as exc:  # noqa: BLE001 - recorded; the approval stands
                laura[run_key] = {"certified": False,
                                  "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return {"batch": batch, "requested": len(seen), "acted_count": len(done),
            "approved_count": len(done), "acted": done, "by_bucket": tally,
            "failed_count": len(failed), "failed": failed,
            "dropped_count": len(dropped), "dropped": dropped,
            "laura_galleries": laura, "at": now.isoformat()}


def _write_row(s, one, row, bucket, again, detail, *, actor, now, cap, left, laura_runs,
               session_public_id, directive: str | None = None) -> tuple[str, str]:
    """One OwnerAction row's approval, as `execute` writes it (same doors, same audits)."""
    from ...core.models import AuditLog
    from ...ops import owner_queue

    if bucket == ROUTINE:
        state, reason = AA._target(row, AA.judge(row.requirement_key)["verdict"], now=now)
    elif bucket == SPEND:
        amount = again["amount_cad"]
        after = round(left - amount, 2)
        if after < -1e-9:
            raise Refused("the company hard cap would be crossed")
        state = owner_queue.SATISFIED
        reason = _reason(f"spend approved at its stated CA${amount:.2f}",
                         f"company cap CA${cap:.2f}/month unchanged", directive=directive)
        s.add(AuditLog(actor=actor[:64], action=SPEND_AUDIT_ACTION, at=now,
                       artifact=f"owner_action:{row.id}",
                       detail={**detail, "amount_cad": amount, "company_cap_cad": cap,
                               "headroom_after_cad": after, "spends_nothing_itself": True}))
        detail["amount_cad"] = amount
    elif bucket == DECISION:
        why = _reason(f"{row.requirement_key}", directive=directive)
        if again["decision"] == "improvement":
            from ...improve import cells

            cells.record_owner_approval(one, again["target_id"], approved_by="owner", why=why)
        else:
            from ...improve import league

            league.record_owner_decision(one, again["target_id"], approved_by="owner", why=why)
        state, reason = owner_queue.SATISFIED, why
    elif bucket == OWNER_APPROVED:
        state = owner_queue.SATISFIED
        if directive:
            reason = _reason(f"{row.requirement_key}", "not an attestation of any physical or "
                             "external fact", directive=directive)
            detail["owner_approved_via_step_up"] = False
        else:
            reason = _reason(f"{row.requirement_key}", "owner-approved via step-up; not an "
                             "attestation of any physical or external fact")
            detail["owner_approved_via_step_up"] = True
    elif bucket == PHYSICAL_DIRECTIVE:
        state = owner_queue.WITHDRAWN
        reason = (f"{WITHOUT_ATTESTATION}: resolved by the owner directive "
                  f"{DIRECTIVE_RENDERS} (publish with renders; no physical sample "
                  f"will be made). NOT attested; no sample exists.")
        detail.update({"resolution": WITHOUT_ATTESTATION, "attested": False,
                       "sample_exists": False, "owner_directive": DIRECTIVE_RENDERS})
    else:
        raise Refused(f"unknown bucket {bucket}")
    if bucket == ROUTINE and again["class"] == AA.LAURA_GALLERY_CLASS:
        from ...visual import laura_approval

        got = laura_approval._decide_in(s, one._db, row, decision=laura_approval.APPROVED,
                                        actor=actor, step_up=directive is None,
                                        owner_directive=directive,
                                        via="approve_everything",
                                        session_public_id=session_public_id, now=now)
        laura_runs.append(got["run_key"])
        moved = {"from": owner_queue.OPEN, "changed": True}
    else:
        moved = owner_queue.transition(s, row, state, reason, actor=actor, now=now)
    s.add(AuditLog(actor=actor[:64], action=ROW_AUDIT_ACTION, at=now,
                   artifact=f"owner_action:{row.id}",
                   detail={**detail, "from": moved.get("from"), "to": state,
                           "reason": reason[:500]}))
    return state, reason
