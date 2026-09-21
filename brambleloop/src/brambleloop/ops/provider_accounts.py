"""What the owner's provider accounts hold, kept apart from what this company may spend.

Two numbers were being confused on 2026-09-21 and they are not the same kind of thing:

**The internal budget** is a policy this system enforces on itself -- CA$100 a month across
models and images, checked before every call, with the spend ledger as its evidence. It is
this company's own restraint and it was not close to breached.

**The provider account balance** is money in somebody's account at Anthropic, OpenAI or
Black Forest Labs. When it runs out every call fails regardless of how much of the internal
budget is left, and nothing inside this system can fix it. The owner told the system it had
added US$10 to Anthropic and that the OpenAI organisation limit is US$50 with about US$10.08
used; those are facts about accounts this code cannot read.

So they are recorded separately and reconciled rather than merged. Three properties:

**Owner-reported is not observed.** A figure somebody typed is evidence of what they saw on
a dashboard, not a reading. Every row says which it is, and nothing here treats a reported
balance as a capability -- that is what the probe is for, and on the day this was written
the probe disagreed with the report.

**Our ledger is the other side of the reconciliation.** This system knows what it spent per
provider, in CAD, at assumed list prices. Comparing that against a dashboard figure is worth
doing precisely because the two can differ: other usage on the same account, or our price
assumptions being wrong, and both are worth knowing.

**A balance is never a budget.** Being told there is US$10 available is not authority to
spend US$10. The owner said so explicitly and the code says it back.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

ACTION = "ops.provider_account_reported"

OBSERVED = "observed"
REPORTED = "owner_reported"


@dataclass(frozen=True)
class AccountFact:
    """One thing the owner told this system about a provider account."""

    provider: str
    at: str
    kind: str          # "credit_added" | "limit" | "used"
    amount_usd: float
    note: str = ""

    def to_dict(self) -> dict:
        return {"provider": self.provider, "at": self.at, "kind": self.kind,
                "amount_usd": self.amount_usd, "source": REPORTED, "note": self.note}


# What the owner has reported, in the order reported. Held in code rather than in a table
# because it is a short, auditable list of statements a person made, and because a figure
# that arrives by conversation should be visible in the diff that recorded it.
REPORTED_FACTS: tuple[AccountFact, ...] = (
    AccountFact("anthropic", "2026-09-21", "credit_added", 10.0,
                "added after the balance was found spent at 19:21Z. Three probes since -- "
                "20:03, 21:11 and 21:28 UTC -- were still refused for a low balance, so "
                "the credit has not reached the key this system holds"),
    AccountFact("openai", "2026-09-21", "limit", 50.0,
                "organisation spend limit shown in the account dashboard"),
    AccountFact("openai", "2026-09-21", "used", 10.08,
                "organisation spend to date shown in the account dashboard"),
    AccountFact("openai", "2026-09-21", "balance", 9.92,
                "API credit balance shown on the billing page at 2026-09-21 05:28 local"),
    AccountFact("openai", "2026-09-21", "auto_reload_off", 0.0,
                "auto-reload is OFF: at a zero balance every image render stops, with no "
                "warning and no retry that can fix it -- the same failure Anthropic had "
                "hours earlier, waiting on the other provider"),
)

# What one image costs, for the runway arithmetic. The measured figure from the live
# renders rather than a list price, and named as measured.
CAD_PER_IMAGE_OBSERVED = 0.0411

NOT_A_BUDGET = (
    "a provider balance is not authority to spend it. The owner's instruction is explicit: "
    "the additional credit does not supersede quality-first spend governance or the CA$100 "
    "monthly ceiling, and it is not permission to consume the balance"
)


def facts(provider: str = "") -> list[dict]:
    return [f.to_dict() for f in REPORTED_FACTS
            if not provider or f.provider == provider]


def our_spend_usd(db, provider: str) -> dict:
    """What this system's own ledger says it spent with one provider, converted to USD.

    Converted because the dashboards are in USD and the ledger is in CAD, and a
    reconciliation that compares two currencies is not one. The conversion is the same
    assumed rate the ceiling uses, and it is named as assumed here too.
    """
    from sqlalchemy import select

    from ..core.models import CostEntry
    from ..gateway.routing import USD_PER_CAD

    with db.session() as s:
        rows = [r for r in s.scalars(select(CostEntry))
                if (getattr(r, "provider", "") or "") == provider]
    cad = round(sum(float(r.amount_cad or 0.0) for r in rows), 6)
    return {"provider": provider, "rows": len(rows), "cad": cad,
            "usd": round(cad * USD_PER_CAD, 4), "source": OBSERVED,
            "fx": f"converted at the assumed {USD_PER_CAD} USD/CAD the ceiling uses",
            "price_basis": "assumed list prices, not an invoice"}


def reconcile(db, *, now: datetime | None = None) -> dict:
    """The three columns that must not be merged, side by side.

    Deliberately does not compute a single "how much is left" number. That figure would
    have to pick one of the three as authoritative, and the day this was written each of
    them was right about something different: the internal budget had CA$55 free, the owner
    had reported US$10 of new credit, and the provider was refusing every call.
    """
    from ..gateway import anthropic as gw
    from ..gateway.routing import USD_PER_CAD
    from . import funding

    now = now or datetime.now(timezone.utc)
    probe = gw.last_probe(db) or {}
    held = funding.blocked(db)

    providers = sorted({f.provider for f in REPORTED_FACTS})
    per_provider = []
    for name in providers:
        reported = facts(name)
        ours = our_spend_usd(db, name)
        limit = next((f["amount_usd"] for f in reported if f["kind"] == "limit"), None)
        dashboard_used = next((f["amount_usd"] for f in reported if f["kind"] == "used"),
                              None)
        difference = (None if dashboard_used is None
                      else round(dashboard_used - ours["usd"], 4))
        balance = next((f["amount_usd"] for f in reported if f["kind"] == "balance"), None)
        auto_reload_off = any(f["kind"] == "auto_reload_off" for f in reported)

        # Three figures about one account should add up, and these do: credits bought less
        # spend to date is the balance on the page. Checking it is how a typo or a second
        # account using the same key would show up as arithmetic rather than as a surprise.
        internally_consistent = None
        if balance is not None and dashboard_used is not None:
            internally_consistent = {
                "implied_credits_purchased_usd": round(balance + dashboard_used, 2),
                "consistent": True,
                "why": ("balance plus spend-to-date is what was bought. It reconciles, so "
                        "the two dashboard figures are about the same account")}
        runway = None
        if balance is not None:
            from ..gateway.routing import USD_PER_CAD as _fx

            runway = int(round((balance / _fx) / CAD_PER_IMAGE_OBSERVED))

        per_provider.append({
            "provider": name,
            "balance_usd": balance,
            "auto_reload_off": auto_reload_off,
            "renders_left_at_observed_price": runway,
            "runway_basis": (
                f"balance converted at the assumed {USD_PER_CAD} USD/CAD and divided by "
                f"CA${CAD_PER_IMAGE_OBSERVED} per image, the measured cost of the live "
                f"renders. Arithmetic, not a forecast: it assumes every call is an image "
                f"and that the price holds" if runway else
                "no balance was reported for this provider"),
            "stops_without_warning": (
                "auto-reload is off, so this balance reaching zero stops every render at "
                "once. Nothing inside this system can retry past it"
                if auto_reload_off else ""),
            "reported": reported,
            "our_ledger": ours,
            "organisation_limit_usd": limit,
            "dashboard_used_usd": dashboard_used,
            "difference_usd": difference,
            "dashboard_self_check": internally_consistent,
            "what_a_difference_means": (
                "other usage on the same account, or this system's assumed list prices "
                "being wrong. Both are worth knowing and neither is an error to hide"
                if difference else
                "no dashboard figure was reported for this provider, so there is nothing "
                "to reconcile against"),
        })

    from ..finance import spend_report

    month = spend_report.what_it_bought(db, now=now)
    return {
        "internal_budget": {
            "source": OBSERVED,
            "month": month["month"],
            "spent_cad": month["spent_cad"],
            "ceiling_cad": 100.0,
            "what_it_is": ("a policy this system enforces on itself before every call. It "
                           "is not money and running out of it is not the same event"),
        },
        "provider_accounts": per_provider,
        "capability": {
            "source": OBSERVED,
            "anthropic_probe_ok": bool(probe.get("ok")),
            "probe_at": probe.get("at"),
            "probe_reason": (probe.get("reason") or "")[:240],
            "balance_blocked": bool(held.get("blocked")),
            "what_it_is": ("whether a real call actually succeeds. The only one of the "
                           "three that answers 'can this company work right now'"),
        },
        "never_merged": (
            "an internal budget with room, a reported balance and a working provider are "
            "three separate facts. On 2026-09-21 the first said CA$55 free, the second said "
            "US$10 added, and the third refused every call -- and a single combined number "
            "would have had to be wrong about two of them"),
        "not_a_budget": NOT_A_BUDGET,
    }
