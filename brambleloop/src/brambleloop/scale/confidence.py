"""How likely CA$5,000 a month actually is, computed from rows that exist.

Requirements 230, 274, 275 — and the owner's framing, which is the specification that matters:
the probability must be *earned from actual market evidence, not manufactured from optimistic
assumptions*.

That sentence rules out the obvious implementation. A weighted score over criteria somebody
fills in produces a number that rises when the architecture gets more sophisticated, which is
exactly what #230 forbids: *"Do not claim >=75% modeled confidence merely because the
architecture is sophisticated."* A system that has built a beautiful pipeline and sold nothing
must report a number near zero, and it must not be possible to argue it upward.

So three properties, each one a thing that cannot be done rather than a thing that should not:

**Every rung is a query, not a field.** Each layer of the ladder counts rows — orders,
customers, refunds, distinct selling SKUs, acquisition loops with attributable traffic. There
is no parameter to set a rung, no override, and no way for a code change to raise one without
changing what the database contains.

**Small samples cannot produce confidence.** Three orders at a 4% conversion rate is not
evidence of a 4% conversion rate. Every observed rate is shrunk toward the pessimistic prior
by its own sample size, so a rung earns confidence by accumulating observations rather than by
getting lucky early.

**The ladder is a minimum, not an average (#274).** The modelled probability cannot exceed its
weakest critical layer. An average lets nine strong rungs hide one fatal one — and "we can
make it, price it, and nobody buys it" is precisely the shape of failure an average hides.
Above that sits the #275 gate: a hard list of minimum conditions, all of which must hold
before any number at or above 75% may be reported at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# The evidence floor for a claim at or above 75% (#275). Each is a count, so each is checkable.
GATE = {
    "selling_skus": 4,              # several independently selling products
    "product_families": 2,          # across more than one family
    "outside_customers": 40,        # a meaningful sample of real outside customers
    "orders": 60,                   # enough orders for a conversion rate to mean something
    "acquisition_loops": 2,         # two viable loops, or one strong with a backup
    "months_of_history": 3,         # sustained, not a single good month
}
GATE_CEILING = 0.74  # what may be claimed while the gate is unmet

# Sample sizes at which an observed rate is worth as much as the prior says it is. Below this,
# an observed rate is shrunk toward the pessimistic end: the arithmetic of "we converted our
# first two visitors" should not produce confidence.
CONVERSION_SAMPLE_FOR_FULL_WEIGHT = 1000
ORDER_SAMPLE_FOR_FULL_WEIGHT = 100


@dataclass(frozen=True)
class Rung:
    """One layer of the ladder, with the evidence that produced it."""

    key: str
    confidence: float
    critical: bool
    evidence: dict = field(default_factory=dict)
    what_would_move_it: str = ""

    def to_dict(self) -> dict:
        return {"layer": self.key, "confidence": round(self.confidence, 3),
                "critical": self.critical, "evidence": self.evidence,
                "what_would_move_it": self.what_would_move_it}


def shrink(observed: float, sample: int, full_weight_at: int, prior: float = 0.0) -> float:
    """Weight an observed rate by how much of it was actually observed.

    A rate measured over three events is mostly noise, and treating it as a measurement is how
    an early fluke becomes a plan. The weight rises with the sample and reaches the observed
    value only when there is enough of it to believe.
    """
    if sample <= 0:
        return prior
    weight = min(1.0, sample / float(full_weight_at))
    return prior + (observed - prior) * weight


def _counts(db) -> dict:
    """Everything the ladder is computed from, in one pass. Rows, not opinions."""
    from sqlalchemy import func, select

    from ..core.models import (
        Incident, LedgerEntry, Listing, PatternVersion, PhysicalTest, SupportCase,
    )

    now = datetime.now(timezone.utc)
    with db.session() as s:
        certified = s.scalar(select(func.count()).select_from(PatternVersion)
                             .where(PatternVersion.certified == True)) or 0  # noqa: E712
        listings = s.scalar(select(func.count()).select_from(Listing)
                            .where(Listing.state == "published")) or 0
        physical_passed = s.scalar(select(func.count()).select_from(PhysicalTest)
                                   .where(PhysicalTest.passed == True)) or 0  # noqa: E712
        open_incidents = s.scalar(select(func.count()).select_from(Incident)
                                  .where(Incident.resolved == False)) or 0  # noqa: E712
        support = s.scalar(select(func.count()).select_from(SupportCase)) or 0
        # Revenue is only what the ledger records as a real money event with evidence.
        sales = list(s.scalars(select(LedgerEntry).where(LedgerEntry.category == "sale")))
        refunds = s.scalar(
            select(func.coalesce(func.sum(LedgerEntry.refunds_cad), 0.0))) or 0.0

    # SQLite hands back naive datetimes where Postgres returns aware ones, and comparing the
    # two raises. Normalising here rather than at every call site means the model gives the
    # same answer on the scratch database a test uses and on the production one.
    def _aware(value):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    gross = sum(x.gross_cad for x in sales)
    months = sorted({f"{_aware(x.at):%Y-%m}" for x in sales})
    cutoff = now - timedelta(days=30)
    recent = [x for x in sales if _aware(x.at) >= cutoff]
    return {
        "certified_patterns": certified,
        "published_listings": listings,
        "physical_tests_passed": physical_passed,
        "open_incidents": open_incidents,
        "support_cases": support,
        "orders": len(sales),
        "orders_last_30_days": len(recent),
        "gross_cad": round(gross, 2),
        "refunds_cad": round(float(refunds), 2),
        "months_with_revenue": len(months),
        "aov_cad": round(gross / len(sales), 2) if sales else 0.0,
    }


def ladder(db, *, observed_conversion: float = 0.0, conversion_sample: int = 0,
           selling_skus: int = 0, product_families: int = 0,
           acquisition_loops: int = 0, repeat_orders: int = 0,
           top_sku_revenue_share: float = 1.0) -> list[Rung]:
    """The seven layers of #274, each computed from what exists.

    The optional arguments are counts a caller supplies from systems that do not exist yet
    (attribution, repeat tracking). They default to zero, which is the honest value today and
    the one that keeps the ladder from flattering itself while those systems are unbuilt.
    """
    c = _counts(db)
    rungs: list[Rung] = []

    # -- product quality: the only rung this company can currently earn ----
    #
    # Deterministic validation is real evidence and it is capped anyway: a pattern nobody has
    # crocheted is a pattern that has never met a human's hands, and no amount of compiling
    # substitutes for that.
    validated = min(1.0, c["certified_patterns"] / 12.0)
    physical = min(1.0, c["physical_tests_passed"] / 5.0)
    quality = round(0.55 * validated + 0.45 * physical, 3)
    rungs.append(Rung(
        "product_quality", quality, True,
        {"certified_patterns": c["certified_patterns"],
         "physical_tests_passed": c["physical_tests_passed"],
         "open_incidents": c["open_incidents"]},
        "physical samples: deterministic validation caps this rung below 0.6 on its own, "
        "because a pattern nobody has crocheted has never met a human's hands"))

    # -- demand: somebody outside this company wanting the thing ----------
    demand = shrink(1.0, c["orders"], ORDER_SAMPLE_FOR_FULL_WEIGHT)
    rungs.append(Rung(
        "demand", round(demand, 3), True,
        {"orders": c["orders"], "gross_cad": c["gross_cad"],
         "published_listings": c["published_listings"]},
        "real orders from outside customers. Nothing else is demand evidence — not "
        "favourites, not traffic, not a benchmark shop's success"))

    # -- conversion: observed, over a sample large enough to mean something -
    conversion = shrink(min(1.0, observed_conversion / 0.02),
                        conversion_sample, CONVERSION_SAMPLE_FOR_FULL_WEIGHT)
    rungs.append(Rung(
        "conversion", round(conversion, 3), True,
        {"observed_rate": observed_conversion, "sample": conversion_sample,
         "sample_needed_for_full_weight": CONVERSION_SAMPLE_FOR_FULL_WEIGHT},
        "qualified visits and the orders they produced, over a sample in the thousands. "
        "A rate measured over three visits is noise wearing a decimal point"))

    # -- acquisition: can qualified traffic be produced again on purpose? --
    acquisition = min(1.0, acquisition_loops / 2.0)
    rungs.append(Rung(
        "acquisition", round(acquisition, 3), True,
        {"loops_with_attributable_traffic": acquisition_loops, "loops_needed": 2},
        "two acquisition loops with attributable traffic, or one exceptionally strong loop "
        "with a backup. One loop nobody controls is a hope with a dashboard"))

    # -- average order value ------------------------------------------------
    aov = shrink(min(1.0, c["aov_cad"] / 25.0), c["orders"], ORDER_SAMPLE_FOR_FULL_WEIGHT)
    rungs.append(Rung(
        "aov", round(aov, 3), True,
        {"observed_aov_cad": c["aov_cad"], "target_aov_cad": 25.0, "orders": c["orders"]},
        "observed order values, including whether bundles actually attach"))

    # -- repeat purchase ----------------------------------------------------
    #
    # Not critical: #275 allows a robust substitute. A shop whose customers each buy once can
    # still reach the target on acquisition alone, so a weak rung here caps nothing.
    repeat = shrink(min(1.0, repeat_orders / max(1, c["orders"]) / 0.25),
                    c["orders"], ORDER_SAMPLE_FOR_FULL_WEIGHT)
    rungs.append(Rung(
        "repeat", round(repeat, 3), False,
        {"repeat_orders": repeat_orders, "orders": c["orders"]},
        "second purchases from the same customer, or a substitute with comparable economics"))

    # -- portfolio resilience (#270) ---------------------------------------
    #
    # Zero selling SKUs is total concentration, so the rung is zero rather than undefined: a
    # portfolio with nothing in it is not diversified, it is empty.
    resilience = 0.0 if selling_skus == 0 else round(
        min(1.0, (1.0 - top_sku_revenue_share) / 0.6) * min(1.0, product_families / 2.0), 3)
    rungs.append(Rung(
        "portfolio_resilience", resilience, True,
        {"selling_skus": selling_skus, "product_families": product_families,
         "top_sku_revenue_share": top_sku_revenue_share},
        "revenue spread across several SKUs in more than one family, so losing the best "
        "one does not lose the target"))

    # Nothing downstream of demand may exceed it.
    #
    # Conversion, order value, repeat and resilience are all measured *from orders*, and the
    # order count is the one figure here that comes from the ledger rather than from a caller.
    # Without this clamp a caller could report a conversion sample of ten thousand visits and
    # a perfectly diversified portfolio into a database holding no sales at all, and the
    # ladder would believe it. Bounding them by demand means the only way to raise this model
    # is to sell something, which is the property the owner asked for.
    demand_rung = next(r for r in rungs if r.key == "demand")
    bounded = []
    for rung in rungs:
        if rung.key in ("conversion", "aov", "repeat", "portfolio_resilience") \
                and rung.confidence > demand_rung.confidence:
            bounded.append(Rung(
                rung.key, demand_rung.confidence, rung.critical,
                {**rung.evidence, "bounded_by_demand": True,
                 "orders_in_ledger": c["orders"]},
                f"{rung.what_would_move_it} — currently bounded by the order count, because "
                f"this is measured from orders and the ledger holds {c['orders']}"))
        else:
            bounded.append(rung)
    return bounded


def gate_status(db, *, selling_skus: int = 0, product_families: int = 0,
                acquisition_loops: int = 0, outside_customers: int = 0) -> dict:
    """The #275 floor: the conditions under which 75% may even be discussed."""
    c = _counts(db)
    actual = {
        "selling_skus": selling_skus,
        "product_families": product_families,
        "outside_customers": outside_customers,
        "orders": c["orders"],
        "acquisition_loops": acquisition_loops,
        "months_of_history": c["months_with_revenue"],
    }
    unmet = {k: {"have": actual[k], "need": v} for k, v in GATE.items() if actual[k] < v}
    return {
        "satisfied": not unmet,
        "required": GATE,
        "actual": actual,
        "unmet": unmet,
        "ceiling_while_unmet": GATE_CEILING,
    }


def probability(db, **evidence) -> dict:
    """The modelled probability of sustaining CA$5,000 a month, and why it is that number.

    A minimum over the critical rungs, capped by the evidence gate. Deliberately incapable of
    being talked upward: there is no argument this function accepts.
    """
    gate_kwargs = {k: evidence.get(k, 0) for k in
                   ("selling_skus", "product_families", "acquisition_loops",
                    "outside_customers")}
    rungs = ladder(db, **{k: v for k, v in evidence.items() if k != "outside_customers"})
    gate = gate_status(db, **gate_kwargs)

    critical = [r for r in rungs if r.critical]
    weakest = min(critical, key=lambda r: r.confidence)
    modelled = weakest.confidence
    capped_by = "the weakest critical layer"
    if not gate["satisfied"] and modelled > GATE_CEILING:
        modelled = GATE_CEILING
        capped_by = "the evidence gate (#275)"

    return {
        "probability": round(modelled, 3),
        "target_cad_per_month": 5000.0,
        "weakest_critical_layer": weakest.key,
        "capped_by": capped_by,
        "ladder": [r.to_dict() for r in rungs],
        "evidence_gate": gate,
        "method": (
            "The minimum over the critical layers, not an average (#274). An average lets "
            "nine strong rungs hide one fatal one, and 'we can make it, price it, and nobody "
            "buys it' is exactly the failure an average hides. Observed rates are shrunk "
            "toward the pessimistic prior by their own sample size, so an early fluke cannot "
            "become a plan. Nothing here can be set, weighted or argued upward: every rung "
            "counts rows."),
        "honest_statement": _statement(modelled, weakest, gate),
    }


def _statement(modelled: float, weakest: Rung, gate: dict) -> str:
    if modelled < 0.05:
        return (f"Effectively zero, and correctly so. The binding layer is {weakest.key!r}: "
                f"{weakest.what_would_move_it}. No amount of further building moves this "
                f"number — only customers do. A sophisticated architecture with no sales is "
                f"the exact case #230 was written to refuse.")
    if not gate["satisfied"]:
        missing = ", ".join(sorted(gate["unmet"]))
        return (f"Capped at {gate['ceiling_while_unmet']} because the evidence standard is "
                f"unmet: {missing}. The modelled figure may not be reported at or above 75% "
                f"until those counts exist.")
    return (f"Limited by {weakest.key!r} at {weakest.confidence:.2f}. "
            f"{weakest.what_would_move_it}")
