"""Finance: the books, the CFO challenge and the trajectory (Master Plan sections 1, 15, 34).

Section 15 lists what must be tracked: gross sales, discounts, refunds, platform and payment
fees, ads, AI/API, hosting, software, testers and contractors, tax reserve, contribution
margin, net profit and cash. Section 34 adds cost-to-create and throughput. Section 1 sets the
CA$100,000 target and, to its credit, calls it "a target, not a guarantee".

Everything below reports zero revenue, because revenue is zero. That is the point of building
it now: the accounting exists and is honest before there is anything to flatter. A P&L that
first appears alongside the first sale is a P&L nobody has checked.

Two rules shaped this file.

**Every figure is either observed or explicitly marked as an estimate.** `Books` reads the
ledger and the cost entries and reports what is there. `trajectory` projects, and says
loudly that it is projecting, because the CA$100K figure is the one most likely to be quoted
back as though it were a forecast.

**Tax is reserved, not spent.** GST/HST on Canadian sales is money held for a government, and
counting it as revenue is how a small business discovers a liability it already spent.

**Missing is not zero (F-608).** The paragraph above was written when "revenue is zero" was
the whole truth. It stopped being the whole truth the moment a shop could sell: Etsy
delivers a digital file without this system, so a sale completes whether or not the order
source (`transactions_r`) is connected. While it is not connected -- today -- this file
used to report CA$0.00 gross sales and 0 orders with `all_figures_observed: true`, which is
a measured zero nobody measured. Now the sales side has a reading:

* `measured` -- the source is connected and has been read (`orders_ingest.source_state`);
* `INCOMPLETE` -- sales are recorded but the source is not currently read, so the figures
  are a lower bound and are labelled one;
* `UNMEASURED` -- nothing recorded and the source is not read: every sales-derived figure
  is `None` with the reason, never 0.00.

Operating cost is measured either way (it is read from the cost ledger this system writes),
so it is always reported.

**A modelled fee is not a charged fee (F-609).** Sale fees are `pricing.fees()` output until
Etsy's payment-account ledger replaces them (`finance.reconcile`). The P&L reports platform
fees split by basis -- measured, modelled, unknown -- and `all_figures_observed` is true
only when every figure on it was observed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from ..core.models import CostEntry, LedgerEntry, SpendLimit

# Reserved against net sales. Brambleloop is Canadian; this is a conservative single rate
# standing in for per-province GST/HST until a real tax configuration exists. It is a
# *reserve*, so being approximately right and never spending it is the correct behaviour.
TAX_RESERVE_RATE = 0.13

# Section 1's target, restated so nothing has to remember it.
ANNUAL_TARGET_CAD = 100_000.0
MONTHLY_TARGET_CAD = ANNUAL_TARGET_CAD / 12

COST_KINDS = ("llm", "api", "hosting", "software", "ads", "testing", "other")


@dataclass
class ProfitAndLoss:
    period_start: str
    period_end: str

    gross_sales_cad: float = 0.0
    discounts_cad: float = 0.0
    refunds_cad: float = 0.0
    platform_fees_cad: float = 0.0
    other_expense_cad: float = 0.0

    cost_by_kind: dict = field(default_factory=dict)

    orders: int = 0
    customers: int = 0

    # F-608: the sales side's reading -- "measured", "INCOMPLETE" (a lower bound) or
    # "UNMEASURED" -- with the reason and the order source state it was read from. Defaults
    # to measured so a ProfitAndLoss built by hand from known figures reads as it did.
    sales_reading: str = "measured"
    sales_why: str = ""
    order_source: dict = field(default_factory=dict)
    # F-609: platform fees by how they were obtained.
    fees_by_basis: dict = field(default_factory=dict)
    # F-289: orders and revenue per channel, unattributed explicit. None when unmeasured.
    sales_by_source: dict | None = None

    @property
    def sales_measured(self) -> bool:
        return self.sales_reading == "measured"

    @property
    def sales_unmeasured(self) -> bool:
        return self.sales_reading == "UNMEASURED"

    @property
    def fees_basis(self) -> str:
        """measured | modelled | unknown | mixed | none -- what `platform_fees_cad` is."""
        present = [k for k, v in (self.fees_by_basis or {}).items() if v]
        if not present:
            return "none"
        return present[0] if len(present) == 1 else "mixed"

    @property
    def net_sales_cad(self) -> float:
        return round(self.gross_sales_cad - self.discounts_cad - self.refunds_cad, 2)

    @property
    def tax_reserve_cad(self) -> float:
        """Held for a government, never counted as ours."""
        return round(max(0.0, self.net_sales_cad) * TAX_RESERVE_RATE, 2)

    @property
    def operating_costs_cad(self) -> float:
        return round(sum(self.cost_by_kind.values()) + self.other_expense_cad, 4)

    @property
    def contribution_margin_cad(self) -> float:
        """Net sales less the costs that vary with selling: fees and ads."""
        variable = self.platform_fees_cad + self.cost_by_kind.get("ads", 0.0)
        return round(self.net_sales_cad - variable, 2)

    @property
    def net_profit_cad(self) -> float:
        return round(self.net_sales_cad - self.platform_fees_cad
                     - self.operating_costs_cad - self.tax_reserve_cad, 4)

    @property
    def cash_cad(self) -> float:
        """What is actually ours. Net profit with the tax reserve already removed above."""
        return self.net_profit_cad

    def to_dict(self) -> dict:
        fees_by_basis = {k: round(v, 2) for k, v in (self.fees_by_basis or {}).items()}
        observed = (self.sales_measured
                    and not fees_by_basis.get("modelled") and not fees_by_basis.get("unknown"))
        common = {
            "sales_reading": self.sales_reading,
            "sales_why": self.sales_why,
            "order_source": self.order_source,
            "platform_fees_basis": self.fees_basis,
            "platform_fees_by_basis": fees_by_basis,
            "sales_by_source": self.sales_by_source,
            "all_figures_observed": observed,
        }
        if self.sales_unmeasured:
            # Every figure that depends on sales is unknown, and says so. Operating cost is
            # this system's own spend and is measured regardless.
            return {
                "period": {"start": self.period_start, "end": self.period_end},
                **{k: None for k in ("gross_sales_cad", "discounts_cad", "refunds_cad",
                                     "net_sales_cad", "platform_fees_cad",
                                     "tax_reserve_cad", "contribution_margin_cad",
                                     "net_profit_cad", "cash_cad", "orders", "customers")},
                "operating_costs_cad": self.operating_costs_cad,
                "cost_by_kind": {k: round(v, 4)
                                 for k, v in sorted(self.cost_by_kind.items())},
                **common,
                "note": ("Sales are UNMEASURED, not CA$0.00: " + self.sales_why
                         + ". Operating costs are measured."),
            }
        return {
            **common,
            "sales_is_lower_bound": self.sales_reading == "INCOMPLETE",
            "period": {"start": self.period_start, "end": self.period_end},
            "gross_sales_cad": round(self.gross_sales_cad, 2),
            "discounts_cad": round(self.discounts_cad, 2),
            "refunds_cad": round(self.refunds_cad, 2),
            "net_sales_cad": self.net_sales_cad,
            "platform_fees_cad": round(self.platform_fees_cad, 2),
            "operating_costs_cad": self.operating_costs_cad,
            "cost_by_kind": {k: round(v, 4) for k, v in sorted(self.cost_by_kind.items())},
            "tax_reserve_cad": self.tax_reserve_cad,
            "contribution_margin_cad": self.contribution_margin_cad,
            "net_profit_cad": self.net_profit_cad,
            "cash_cad": self.cash_cad,
            "orders": self.orders,
            "customers": self.customers,
        }


class Books:
    def __init__(self, db):
        self.db = db

    def profit_and_loss(self, *, since: datetime | None = None,
                        until: datetime | None = None) -> ProfitAndLoss:
        until = until or datetime.now(timezone.utc)
        since = since or (until - timedelta(days=30))
        pl = ProfitAndLoss(period_start=since.date().isoformat(),
                           period_end=until.date().isoformat())

        from sqlalchemy import func

        from ..commerce import orders_ingest
        from ..core.models import Order
        from . import reconcile, sources

        with self.db.session() as s:
            entries = list(s.scalars(select(LedgerEntry).where(LedgerEntry.at >= since,
                                                               LedgerEntry.at <= until)))
            for e in entries:
                pl.gross_sales_cad += e.gross_cad
                pl.refunds_cad += e.refunds_cad
                pl.platform_fees_cad += e.fees_cad
                pl.other_expense_cad += e.expense_cad
                if e.category == "sale":
                    pl.orders += 1
                elif e.category == "discount":
                    pl.discounts_cad += e.expense_cad
            pl.fees_by_basis = reconcile.fee_basis_summary(e for e in entries if e.fees_cad)
            pl.customers = s.scalar(select(func.count(func.distinct(Order.customer_id)))
                                    .where(Order.at >= since, Order.at <= until)) or 0

            for c in s.scalars(select(CostEntry).where(CostEntry.at >= since,
                                                       CostEntry.at <= until)):
                kind = c.kind if c.kind in COST_KINDS else "other"
                pl.cost_by_kind[kind] = pl.cost_by_kind.get(kind, 0.0) + c.amount_cad

        # F-608: what the sales side is, read from the order source rather than assumed.
        state = orders_ingest.source_state(self.db)
        pl.order_source = {k: state[k] for k in ("open", "last_read_at", "missing",
                                                 "owner_action")}
        recorded_sales = any(e.category == "sale" for e in entries)
        if state["measured"]:
            pl.sales_reading = "measured"
        elif recorded_sales:
            pl.sales_reading = "INCOMPLETE"
            pl.sales_why = ("sales are recorded but " + state["why"][0].lower()
                            + state["why"][1:] + "; the recorded figures are a lower bound")
        else:
            pl.sales_reading = "UNMEASURED"
            pl.sales_why = state["why"]
        if not pl.sales_unmeasured:
            pl.sales_by_source = sources.table(self.db, since=since, until=until)
        return pl

    def unit_economics(self, *, products_validated: int, listings_drafted: int,
                       since: datetime | None = None) -> dict:
        """Section 34: cost per validated pattern, per listing, per acquired customer.

        A six-figure store can still be a bad business if autonomous production burns more in
        API and ad spend than it earns. These are the ratios that catch that early, and they
        are computable now precisely because they do not need revenue.
        """
        pl = self.profit_and_loss(since=since)
        opex = pl.operating_costs_cad
        customers = None if pl.sales_unmeasured else pl.customers
        return {
            "operating_cost_cad": round(opex, 4),
            "validated_patterns": products_validated,
            "listings_drafted": listings_drafted,
            "cost_per_validated_pattern_cad": (round(opex / products_validated, 4)
                                               if products_validated else None),
            "cost_per_listing_cad": (round(opex / listings_drafted, 4)
                                     if listings_drafted else None),
            "customers": customers,
            "cost_per_acquired_customer_cad": (round(opex / customers, 4)
                                               if customers else None),
            "note": (("cost per acquired customer is undefined because customers are "
                      "UNMEASURED: " + pl.sales_why) if customers is None else
                     "cost per acquired customer is undefined because there are no customers. "
                     "That is the honest answer, not a divide-by-zero to paper over."
                     if not customers else ""),
        }


# ---- CFO challenge ---------------------------------------------------------


@dataclass
class Challenge:
    severity: str        # note | concern | block
    subject: str
    finding: str
    ask: str = ""

    def to_dict(self) -> dict:
        return {"severity": self.severity, "subject": self.subject,
                "finding": self.finding, "ask": self.ask}


def cfo_challenge(pl: ProfitAndLoss, *, limits: list[SpendLimit] | None = None,
                  infra_monthly_cad: float = 0.0,
                  infra_ceiling_cad: float = 20.0) -> list[Challenge]:
    """Section 14's CFO/Skeptic, as a function rather than a personality.

    Its job is to be the part of the system that is unimpressed. It reports concerns even when
    everything is nominally fine, because a reviewer who only speaks up during a crisis is a
    reviewer nobody has calibrated.
    """
    out: list[Challenge] = []

    if pl.sales_unmeasured:
        out.append(Challenge(
            "note", "revenue",
            "Revenue is UNMEASURED, not CA$0.00: " + pl.sales_why + ". Every ratio below has "
            "an unknown denominator, and no pricing, ad or portfolio decision can be justified "
            "by performance data this system cannot see.",
            "connect the order source (owner action reauthorise_transactions_r)"))
    elif pl.gross_sales_cad == 0:
        out.append(Challenge(
            "note", "revenue",
            "Revenue is CA$0.00 and there are no customers. Nothing is published, so this is "
            "expected rather than alarming — but every ratio below has an undefined "
            "denominator, and no pricing, ad or portfolio decision can be justified by "
            "performance data that does not exist yet."))

    if pl.operating_costs_cad > 0 and pl.sales_unmeasured:
        out.append(Challenge(
            "concern", "burn",
            f"CA${pl.operating_costs_cad:.2f} of operating cost against UNMEASURED revenue. "
            f"The cost is known; whether anything was earned against it is not.",
            "keep cost-per-validated-pattern in every finance report"))
    elif pl.operating_costs_cad > 0 and pl.gross_sales_cad == 0:
        out.append(Challenge(
            "concern", "burn",
            f"CA${pl.operating_costs_cad:.2f} of operating cost against CA$0.00 of revenue. "
            f"At this scale that is affordable, and the thing to watch is whether it stays "
            f"proportional to output rather than to time.",
            "keep cost-per-validated-pattern in every finance report"))

    if infra_monthly_cad > infra_ceiling_cad:
        out.append(Challenge(
            "block", "infrastructure",
            f"Recurring infrastructure is CA${infra_monthly_cad:.2f}/month against an owner "
            f"ceiling of CA${infra_ceiling_cad:.2f}.",
            "stop the excess spend and bring the owner the exact requirement, cost and "
            "consequence"))

    ads = pl.cost_by_kind.get("ads", 0.0)
    if ads > 0 and (pl.orders == 0 or pl.sales_unmeasured):
        out.append(Challenge(
            "block", "paid media",
            (f"CA${ads:.2f} of advertising with no measured attributable orders (sales are "
             f"UNMEASURED)." if pl.sales_unmeasured else
             f"CA${ads:.2f} of advertising with zero attributable orders."),
            "pause the campaign; section 11 requires scaling only on profitable evidence"))

    for limit in (limits or []):
        if limit.paused:
            out.append(Challenge("block", f"budget:{limit.scope}",
                                 f"{limit.scope} is paused after breaching its cap.",
                                 "a paused scope stays paused until the owner reviews it"))
        elif limit.lifetime_cap_cad and limit.spent_lifetime_cad > limit.lifetime_cap_cad * 0.8:
            out.append(Challenge(
                "concern", f"budget:{limit.scope}",
                f"{limit.scope} has used {limit.spent_lifetime_cad:.2f} of "
                f"{limit.lifetime_cap_cad:.2f} lifetime."))

    if pl.tax_reserve_cad > 0:
        out.append(Challenge(
            "note", "tax",
            f"CA${pl.tax_reserve_cad:.2f} is reserved against net sales and is not ours to "
            f"spend. Counting it as revenue is how a small business discovers a liability it "
            f"has already spent."))
    return out


# ---- trajectory ------------------------------------------------------------


def trajectory(pl: ProfitAndLoss, *, today: date | None = None) -> dict:
    """Where CA$100K stands. Refuses to forecast from nothing.

    Section 1 is careful to call the target "a target, not a guarantee", and this is the
    number most likely to be repeated back as though it were a forecast. So with no sales
    there is no run rate, no projection and no percentage — only the arithmetic of what the
    target would require, clearly labelled as arithmetic.
    """
    today = today or date.today()
    aov = (pl.net_sales_cad / pl.orders) if pl.orders else None

    if pl.sales_unmeasured:
        return {
            "as_of": today.isoformat(),
            "target_annual_cad": ANNUAL_TARGET_CAD,
            "sales_reading": "UNMEASURED",
            "observed_orders": None,
            "observed_revenue_cad": None,
            "run_rate_cad": None,
            "projection": None,
            "is_forecast": False,
            "what_the_target_requires": {
                "at_aov_cad_17": round(ANNUAL_TARGET_CAD / 17, 0),
                "orders_per_month_at_aov_17": round(ANNUAL_TARGET_CAD / 17 / 12, 0),
                "orders_per_day_at_aov_17": round(ANNUAL_TARGET_CAD / 17 / 365, 1),
            },
            "note": ("Orders are UNMEASURED (" + pl.sales_why + "), so there is no run rate "
                     "and no projection. The figures above are arithmetic on the target, "
                     "not a forecast, and must never be presented as one."),
        }

    if not pl.orders:
        return {
            "as_of": today.isoformat(),
            "target_annual_cad": ANNUAL_TARGET_CAD,
            "observed_orders": 0,
            "observed_revenue_cad": 0.0,
            "run_rate_cad": None,
            "projection": None,
            "is_forecast": False,
            "what_the_target_requires": {
                "at_aov_cad_17": round(ANNUAL_TARGET_CAD / 17, 0),
                "orders_per_month_at_aov_17": round(ANNUAL_TARGET_CAD / 17 / 12, 0),
                "orders_per_day_at_aov_17": round(ANNUAL_TARGET_CAD / 17 / 365, 1),
            },
            "note": ("No orders exist, so there is no run rate and no projection. The figures "
                     "above are arithmetic on the target, not a forecast, and must never be "
                     "presented as one."),
        }

    days = max(1, (date.fromisoformat(pl.period_end)
                   - date.fromisoformat(pl.period_start)).days)
    daily = pl.net_sales_cad / days
    return {
        "as_of": today.isoformat(),
        "target_annual_cad": ANNUAL_TARGET_CAD,
        "observed_orders": pl.orders,
        "observed_revenue_cad": pl.net_sales_cad,
        "aov_cad": round(aov, 2) if aov else None,
        "run_rate_cad": round(daily * 365, 2),
        "projection": round(daily * 365, 2),
        "is_forecast": True,
        "share_of_target": round(daily * 365 / ANNUAL_TARGET_CAD, 4),
        "sales_reading": pl.sales_reading,
        "note": (f"A run rate extrapolated from {days} days and {pl.orders} orders. Treat it "
                 f"as a direction, not a number."
                 + (" The orders are a lower bound (sales INCOMPLETE: the order source is "
                    "not currently read)." if pl.sales_reading == "INCOMPLETE" else "")),
    }
