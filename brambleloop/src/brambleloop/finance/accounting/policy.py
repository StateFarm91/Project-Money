"""Finance's spend challenge (F-912 spend governor integration, F-919 cross-agent challenge).

Contract for lane H (Growth) and any other spender::

    check_spend(db, proposal) -> {"allow": bool, "reasons": [str, ...],
                                  "challenge_id": str, "verdict": str,
                                  "escalate_to": "owner" | None, "checks": [...]}

`proposal` keys (unknown keys are kept, ignored by the rules):

* `amount_cad` (required, > 0)           -- the spend asked for
* `purpose` (required, >= 10 chars)      -- what it buys
* `proposer` / `department`              -- e.g. "growth"
* `kind`                                 -- "ads" (default), "benchmark", "software", ...
* `channel`, `product_slug`              -- optional attribution
* `expected_contribution_cad`            -- Growth's own estimate of contribution returned
* `authority` = {"type": "owner_action", "ref": <owner_actions.requirement_key>}

Verdicts: `cleared` (allow=True: no policy objection *and* verified authority), `escalated`
(no hard violation Finance can measure, but authority or evidence is missing -- the owner
decides) and `blocked` (a policy violation: margin, cash, caps, phase). **Budget
availability is never permission**: without verified owner/policy authority the best
possible verdict is `escalated`, and `allow` is False. Every call is recorded as an
`acct_challenges` row; its id is returned so the spender and the owner cite the same record.

Finance cannot spend: this function returns an opinion and writes a record. Nothing here
calls a provider, a bank or an ads API (F-917).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from .models import AcctChallenge, AcctException
from .schema import ensure

MIN_PRODUCT_CONTRIBUTION_MARGIN = 0.40
EXTERNAL_KINDS = ("ads", "benchmark", "software", "contractor", "physical_test", "other")


def _authority(s, proposal: dict) -> tuple[bool, str]:
    from ...core.models import OwnerAction

    auth = proposal.get("authority") or {}
    if not isinstance(auth, dict) or not auth.get("ref"):
        return False, "no owner or policy authority attached"
    if auth.get("type") != "owner_action":
        return False, f"authority type {auth.get('type')!r} is not one Finance can verify"
    row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == str(auth["ref"])))
    if row is None:
        return False, f"owner action {auth['ref']!r} does not exist"
    if not row.done:
        return False, f"owner action {auth['ref']!r} is not approved (not done)"
    if row.max_cost_cad and float(proposal.get("amount_cad") or 0) > row.max_cost_cad + 1e-9:
        return False, (f"owner approved at most CA${row.max_cost_cad:.2f}; proposal asks "
                       f"CA${float(proposal['amount_cad']):.2f}")
    return True, f"owner action {auth['ref']!r} approved (max CA${row.max_cost_cad:.2f})"


def check_spend(db, proposal: dict, *, now: datetime | None = None) -> dict:
    from ...commerce.paid_media import CONSERVATIVE_CAPS
    from ...core import phase as phase_mod
    from . import accounts as A
    from . import cash as cash_mod
    from . import health as H
    from . import profitability
    from .ledger import balances, period_of

    db = ensure(db)
    now = now or datetime.now(timezone.utc)
    proposal = dict(proposal or {})
    checks: list[dict] = []

    def add(rule: str, outcome: str, why: str):
        checks.append({"rule": rule, "outcome": outcome, "why": why})

    try:
        amount = float(proposal.get("amount_cad"))
    except (TypeError, ValueError):
        amount = -1.0
    kind = str(proposal.get("kind") or "ads").lower()
    if amount <= 0:
        add("amount", "block", "amount_cad must be a positive number")
    if len(str(proposal.get("purpose") or "").strip()) < 10:
        add("purpose", "block", "a spend names what it buys; 'growth' is not a purpose")
    try:
        ph = phase_mod.effective(db, record_incident=False)
    except Exception:  # noqa: BLE001 - fail closed
        ph = "shadow"
    if ph == "shadow" and kind in EXTERNAL_KINDS:
        add("phase", "block", "the company is in SHADOW phase: no external spend executes")
    health = H.reading(db, now=now)
    pos = cash_mod.position(db, now=now, health=health)
    if pos["cash_on_hand_cad"] is None:
        add("cash", "block", "cash is UNKNOWN (" + (pos["cash_why"] or "no bank source")
            + "); Finance will not approve spend against an unknown balance")
    elif pos["safe_discretionary_budget_cad"] is None or \
            pos["safe_discretionary_budget_cad"] < amount:
        add("cash", "block", f"safe discretionary budget "
            f"{pos['safe_discretionary_budget_cad']} CAD is below CA${amount:.2f}")
    else:
        add("cash", "pass", f"within safe discretionary budget "
            f"CA${pos['safe_discretionary_budget_cad']:.2f}")
    if kind == "ads":
        if not health["revenue_known"]:
            add("evidence", "block", "sales are UNMEASURED; advertising needs measured "
                "attributable orders (section 11)")
        exp = proposal.get("expected_contribution_cad")
        if exp is None:
            add("margin", "escalate", "no expected contribution was stated, so the margin "
                "policy cannot be checked")
        elif amount > 0 and float(exp) / amount < CONSERVATIVE_CAPS.target_contribution_ratio:
            add("margin", "block", f"expected contribution CA${float(exp):.2f} on CA${amount:.2f} "
                f"is {float(exp) / amount:.2f} per ad dollar, below the "
                f"{CONSERVATIVE_CAPS.target_contribution_ratio:.2f} target")
        else:
            add("margin", "pass", "expected contribution clears the target ratio")
        if amount > CONSERVATIVE_CAPS.campaign_cad:
            add("caps", "block", f"CA${amount:.2f} exceeds the campaign cap "
                f"CA${CONSERVATIVE_CAPS.campaign_cad:.2f}")
        with db.session() as s:
            month_ads = (balances(s, period=period_of(now)).get(A.ADS) or {}).get("balance", 0)
        if month_ads / 1e6 + amount > CONSERVATIVE_CAPS.monthly_cad:
            add("caps", "block", f"month-to-date ads CA${month_ads / 1e6:.2f} + this "
                f"exceeds the monthly cap CA${CONSERVATIVE_CAPS.monthly_cad:.2f}")
    slug = proposal.get("product_slug")
    if slug:
        rows = [r for r in profitability.by(db, "product")["rows"] if r["product"] == slug]
        m = rows[0]["contribution_margin"] if rows else None
        if m is not None and m < MIN_PRODUCT_CONTRIBUTION_MARGIN:
            add("margin", "block", f"{slug} contribution margin {m:.0%} is below the "
                f"{MIN_PRODUCT_CONTRIBUTION_MARGIN:.0%} floor")
    with db.session() as s:
        ok, why = _authority(s, proposal)
        add("authority", "pass" if ok else "escalate",
            why + ("" if ok else "; budget availability is not permission (F-912)"))
        open_high = s.scalar(select(AcctException.id).where(
            AcctException.resolved == False, AcctException.severity == "high"))  # noqa: E712
    if open_high is not None:
        add("books", "escalate", "high-severity accounting exceptions are open; the books "
            "are not reconciled")
    blocks = [c for c in checks if c["outcome"] == "block"]
    escal = [c for c in checks if c["outcome"] == "escalate"]
    verdict = "blocked" if blocks else "escalated" if escal else "cleared"
    reasons = [f"[{c['rule']}] {c['why']}" for c in blocks + escal] or \
        ["no Finance objection; owner authority verified"]
    cid = "fin-" + uuid.uuid4().hex[:16]
    with db.session() as s:
        s.add(AcctChallenge(challenge_id=cid, at=now,
                            proposer=str(proposal.get("proposer") or
                                         proposal.get("department") or "")[:40],
                            amount_cad=max(0.0, amount), verdict=verdict, reasons=reasons,
                            proposal={k: v for k, v in proposal.items()
                                      if isinstance(v, (str, int, float, bool, dict, list,
                                                        type(None)))},
                            evidence={"checks": checks,
                                      "cash_on_hand_cad": pos["cash_on_hand_cad"],
                                      "safe_discretionary_budget_cad":
                                          pos["safe_discretionary_budget_cad"],
                                      "phase": ph}))
    return {"allow": verdict == "cleared", "reasons": reasons, "challenge_id": cid,
            "verdict": verdict, "escalate_to": "owner" if verdict != "cleared" else None,
            "checks": checks}


def challenges(db, *, limit: int = 50) -> list[dict]:
    db = ensure(db)
    with db.session() as s:
        return [{"challenge_id": c.challenge_id, "at": c.at.isoformat() if c.at else None,
                 "proposer": c.proposer, "amount_cad": c.amount_cad, "verdict": c.verdict,
                 "reasons": c.reasons}
                for c in s.scalars(select(AcctChallenge).order_by(AcctChallenge.id.desc())
                                   .limit(limit))]
