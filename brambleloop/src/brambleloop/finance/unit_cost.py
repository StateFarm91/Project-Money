"""What each thing cost to make, and whether the company can afford to keep making them.

Requirement 31, and its last sentence is the whole module: *a six-figure store that burns more
than it earns is failure.* That is not a warning about extravagance. It is a warning about a
specific and very comfortable failure — every number rising, the catalogue growing, the agents
busy, and the operating cost per validated product rising faster than the contribution per
product, which nobody notices because nobody is dividing.

So two ratios, and they are the ones #31 names: **validated products per operating dollar**
and **contribution profit per operating dollar**. Both are divisions the company can compute
today for the numerator and, today, has a zero for one side of. That zero is reported as a
zero rather than hidden, because "we spent CA$40 and earned nothing" is the true state and it
is the state a growing catalogue makes easy to stop looking at.

The per-artefact costs are read from the cost ledger by the audit trail rather than estimated,
so a cost that was never recorded shows as *unattributed* instead of as cheap. An artefact
produced by work nobody costed looks free, and free is the most dangerous price.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from dataclasses import dataclass


@dataclass(frozen=True)
class Artefact:
    """One thing #31 wants a unit cost on, and how to count it from the audit trail.

    `actions` is a tuple because one artefact can be produced by more than one kind of work:
    a concept arrives from scoring, from a discovery expedition and from a tournament, and
    picking one action would quietly cost only the concepts that came the way somebody
    happened to list first.

    `count_in_detail` is the other half. Most audit rows are one row per artefact; a
    discovery run is a single row that produced eighty concepts, and counting it as one
    concept would report a field of eighty at eighty times its real unit cost -- an error
    that makes discovery look catastrophically expensive and would be read as a reason to
    stop doing it.
    """

    key: str
    actions: tuple[str, ...]
    meaning: str
    count_in_detail: str | None = None


ARTEFACTS: tuple[Artefact, ...] = (
    Artefact("concept", ("concept.scored",), "a concept that reached a score"),
    Artefact("discovered_concept", ("creative.expedition", "creative.tournament"),
             "a concept invented against a proven market arena",
             count_in_detail="proposed"),
    Artefact("validated_pattern", ("gate.certified",),
             "a pattern that passed the full gate chain"),
    Artefact("pdf", ("publish.document",), "a rendered pattern document"),
    Artefact("listing", ("listing.drafted",), "a listing draft ready for review"),
    Artefact("visual_asset", ("asset.rendered",), "a rendered listing image"),
    Artefact("support_case", ("support.answered",), "a customer question answered"),
    Artefact("acquired_customer", ("ledger.sale",), "a customer who paid"),
)

ARTEFACT_BY_KEY: dict[str, Artefact] = {a.key: a for a in ARTEFACTS}


def unit_costs(db, *, days: int = 30, now: datetime | None = None) -> dict:
    """Cost per artefact over a window, from the cost ledger and the audit trail.

    Work whose cost was never recorded is reported as unattributed rather than averaged away.
    An artefact produced by uncosted work looks free, and free is the most dangerous price.
    """
    from sqlalchemy import func, select

    from ..core.models import AuditLog, CostEntry, LedgerEntry

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    def _aware(value):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    with db.session() as s:
        costs = [(c.agent, c.amount_cad, _aware(c.at), c.job_id)
                 for c in s.scalars(select(CostEntry))]
        actions = [(a.action, _aware(a.at), a.job_id, a.detail or {})
                   for a in s.scalars(select(AuditLog))]
        contribution = s.scalar(select(func.coalesce(
            func.sum(LedgerEntry.gross_cad - LedgerEntry.fees_cad
                     - LedgerEntry.refunds_cad - LedgerEntry.expense_cad), 0.0))) or 0.0

    window_costs = [c for c in costs if c[2] >= since]
    total_cost = sum(c[1] for c in window_costs)
    costed_jobs = {c[3]: c[1] for c in window_costs if c[3] is not None}

    rows = {}
    attributed = 0.0
    seen_jobs: set[int] = set()
    for artefact in ARTEFACTS:
        produced = [a for a in actions if a[0] in artefact.actions and a[1] >= since]
        # A job's cost is attributed once. Two artefacts sharing a job -- a run that both
        # proposed concepts and drafted a listing -- would otherwise each claim the whole
        # cost, and the total attributed would exceed what was spent.
        direct = sum(costed_jobs.get(a[2], 0.0) for a in produced
                     if a[2] is not None and a[2] not in seen_jobs)
        seen_jobs.update(a[2] for a in produced if a[2] is not None)
        attributed += direct
        if artefact.count_in_detail:
            count = sum(int(a[3].get(artefact.count_in_detail) or 0) for a in produced)
        else:
            count = len(produced)
        uncosted = sum(1 for a in produced if a[2] is None or a[2] not in costed_jobs)
        rows[artefact.key] = {
            "meaning": artefact.meaning,
            "produced": count,
            "runs": len(produced) if artefact.count_in_detail else None,
            "direct_cost_cad": round(direct, 4),
            "cost_each_cad": (round(direct / count, 4) if count else None),
            "produced_by_uncosted_work": uncosted,
            "note": (f"{uncosted} of {len(produced)} runs were produced by work with no "
                     f"recorded cost, so the figure above is a floor"
                     if uncosted else ""),
        }

    validated = rows["validated_pattern"]["produced"]
    return {
        "window_days": days,
        "operating_cost_cad": round(total_cost, 4),
        "attributed_cost_cad": round(attributed, 4),
        "unattributed_cost_cad": round(total_cost - attributed, 4),
        "artefacts": rows,
        # #31's two ratios. Both reported even when one side is zero, because a growing
        # catalogue makes it easy to stop looking at the side that is not moving.
        "validated_products_per_operating_dollar": (
            round(validated / total_cost, 3) if total_cost else None),
        "contribution_per_operating_dollar": (
            round(float(contribution) / total_cost, 3) if total_cost else None),
        "contribution_cad": round(float(contribution), 2),
        "burning": bool(total_cost > 0 and float(contribution) <= 0),
        "note": (f"CA${total_cost:.2f} spent and CA${float(contribution):.2f} earned in "
                 f"{days} days. A six-figure store that burns more than it earns is failure "
                 f"(#31), and the comfortable version of that failure is every number rising "
                 f"while nobody divides."
                 if total_cost else
                 "no operating cost recorded in this window, so neither ratio is defined"),
    }


def throughput_target(db, *, target_products: int, budget_cad: float) -> dict:
    """Whether a production plan is affordable at the cost this company actually incurs.

    Uses the observed cost per validated pattern rather than an estimate. With none observed
    it says so: a plan priced from an assumed unit cost is a plan about a different company.
    """
    observed = unit_costs(db)
    each = observed["artefacts"]["validated_pattern"]["cost_each_cad"]
    if not each:
        return {"affordable": None,
                "reason": ("no validated pattern has a recorded cost, so a plan cannot be "
                           "priced. An assumed unit cost would produce a confident plan "
                           "about a different company"),
                "observed": observed}
    needed = each * target_products
    return {
        "affordable": needed <= budget_cad,
        "cost_each_cad": each,
        "target_products": target_products,
        "needed_cad": round(needed, 2),
        "budget_cad": budget_cad,
        "shortfall_cad": round(max(0.0, needed - budget_cad), 2),
        "observed_window_days": observed["window_days"],
    }
