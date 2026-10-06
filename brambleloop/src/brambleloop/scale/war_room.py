"""The CA$5K war room: one board the CEO, CFO, growth and product agents execute from (#276).

Requirement 276: current monthly run rate, 30-day forecast, gap to CA$5K, primary constraint,
top five actions by expected incremental contribution, experiments in flight, winner alerts,
risk concentration and owner approvals.

Composed, not recomputed: the constraint is `scale.runrate.constraint`, the risk is
`scale.dependency.report`, experiments are `registered_experiments`, approvals are the owner
queue. What this module adds is the rule the board is held to: **every field is measured or
explicitly absent with its reason and the n it needs.** A board that shows CA$0 run rate
before anything is live is telling the agents reading it that the company tried and sold
nothing, which is a different fact from the true one.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

MEASURED = "measured"
UNMEASURED = "UNMEASURED"

TARGET_CAD = 5000.0
WINDOW_DAYS = 30
# A 30-day forecast is a persistence forecast of the last window; it needs two windows of
# history to state a range and this many orders to be more than a few baskets
# (commerce.benchmarks.MIN_ORDERS_FOR_REFUND_RATE).
MIN_FORECAST_ORDERS = 20
MIN_FORECAST_HISTORY_DAYS = 2 * WINDOW_DAYS
# Winner alerts: products with orders before a median means anything, and the multiple of the
# median contribution that makes a product disproportionate (scale.trajectory.WINNER_LIFT).
MIN_PRODUCTS_FOR_WINNERS = 3
MIN_WINNER_ORDERS = 20
TOP_ACTIONS = 5


def _unmeasured(why: str, needs: str) -> dict:
    return {"status": UNMEASURED, "value": None, "why": why, "needs": needs}


def _measured(value, source: str, **extra) -> dict:
    return {"status": MEASURED, "value": value, "source": source, **extra}


def _aware(at: datetime) -> datetime:
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def _orders(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import Order

    from ..commerce import orders_ingest as _oi

    with db.session() as s:
        return [{"at": _aware(o.at), "slug": o.product_slug, "revenue": o.revenue_cad or 0.0,
                 "contribution": o.contribution_cad or 0.0, "repeat": o.is_repeat}
                for o in _oi.countable_orders(s)]  # rc1-ORD2


def _observed(db, orders: list[dict], now: datetime):
    """The last window as a runrate.Observed, with traffic only where it was recorded."""
    from sqlalchemy import select

    from ..core.models import Listing, ListingOutcome
    from .runrate import Observed

    since = (now - timedelta(days=WINDOW_DAYS)).date().isoformat()
    window = [o for o in orders if o["at"] >= now - timedelta(days=WINDOW_DAYS)]
    with db.session() as s:
        periods = list(s.scalars(select(ListingOutcome).where(
            ListingOutcome.period_end >= since)))
        listings = len(list(s.scalars(select(Listing))))
    return Observed(
        visits=sum(p.visits for p in periods) if periods else None,
        impressions=sum(p.impressions for p in periods) if periods else None,
        orders=len(window) if orders else None,
        revenue_cad=round(sum(o["revenue"] for o in window), 2) if orders else None,
        contribution_cad=round(sum(o["contribution"] for o in window), 2) if orders else None,
        repeat_orders=sum(1 for o in window if o["repeat"]) if orders else None,
        listings=listings)


def board(db, *, now: datetime | None = None, target_cad: float = TARGET_CAD) -> dict:
    """The whole board, every field measured or absent with its reason."""
    from sqlalchemy import select

    from ..core.models import OwnerAction, RegisteredExperiment
    from . import dependency, runrate

    now = now or datetime.now(timezone.utc)
    orders = _orders(db)
    no_sales = ("no order has been recorded: nothing has sold, so a run rate would be a "
                "claim about a shop nobody has bought from")
    out: dict[str, dict] = {}

    # 1. run rate: the last 30 days of contribution-bearing revenue.
    last = [o for o in orders if o["at"] >= now - timedelta(days=WINDOW_DAYS)]
    prev = [o for o in orders if now - timedelta(days=2 * WINDOW_DAYS) <= o["at"]
            < now - timedelta(days=WINDOW_DAYS)]
    if not orders:
        out["monthly_run_rate"] = _unmeasured(no_sales, ">= 1 recorded order")
    else:
        out["monthly_run_rate"] = _measured(
            round(sum(o["revenue"] for o in last), 2), "orders table, trailing 30 days",
            orders=len(last), contribution_cad=round(sum(o["contribution"] for o in last), 2))

    # 2. 30-day forecast: persistence, with the last two windows as its range.
    history_days = ((now - min(o["at"] for o in orders)).days if orders else 0)
    if not orders:
        out["forecast_30d"] = _unmeasured(no_sales, f">= {MIN_FORECAST_ORDERS} orders over "
                                          f">= {MIN_FORECAST_HISTORY_DAYS} days")
    elif len(orders) < MIN_FORECAST_ORDERS or history_days < MIN_FORECAST_HISTORY_DAYS:
        out["forecast_30d"] = _unmeasured(
            f"{len(orders)} order(s) over {history_days} day(s) against floors of "
            f"{MIN_FORECAST_ORDERS} orders and {MIN_FORECAST_HISTORY_DAYS} days",
            f">= {MIN_FORECAST_ORDERS} orders over >= {MIN_FORECAST_HISTORY_DAYS} days")
    else:
        a = round(sum(o["revenue"] for o in last), 2)
        b = round(sum(o["revenue"] for o in prev), 2)
        out["forecast_30d"] = _measured(
            a, "persistence of the trailing 30 days", low=min(a, b), high=max(a, b),
            method=("the next 30 days as the last 30, ranged by the previous 30. Not a "
                    "probability: two windows state a range, not a distribution"))

    # 3. gap to target.
    if out["monthly_run_rate"]["status"] != MEASURED:
        out["gap_to_target"] = _unmeasured("the run rate is unmeasured: " + no_sales,
                                           ">= 1 recorded order")
    else:
        rate = out["monthly_run_rate"]["value"]
        out["gap_to_target"] = _measured(round(max(0.0, target_cad - rate), 2),
                                         "target minus trailing run rate",
                                         target_cad=target_cad, reached=rate >= target_cad)

    # 4. primary constraint.
    observed = _observed(db, orders, now)
    binding = runrate.constraint(observed, target_cad=target_cad)
    if binding.get("identifiable"):
        out["primary_constraint"] = _measured(binding["constraint"], "scale.runrate.constraint",
                                              rule=binding["rule"], action=binding["action"])
    else:
        out["primary_constraint"] = _unmeasured(binding["reason"],
                                                "observed " + ", ".join(binding["unmeasured"]))

    # 5. top actions by expected incremental contribution; 6. experiments in flight.
    with db.session() as s:
        experiments = list(s.scalars(select(RegisteredExperiment)))
        approvals = [{"id": a.id, "action": a.action, "reason": a.reason,
                      "max_cost_cad": a.max_cost_cad, "minutes": a.minutes,
                      "consequence_of_delay": a.consequence_of_delay, "blocks": a.blocks}
                     for a in s.scalars(select(OwnerAction).where(
                         OwnerAction.done == False).order_by(OwnerAction.id))]  # noqa: E712
    live = [e for e in experiments if e.state in ("registered", "running")]
    # #264: `growth.steer` ranks the experiment queue toward the week's constraint; the board
    # shows it in that order, so the agent reading it takes the constraint's levers first.
    live.sort(key=lambda e: ((e.detail or {}).get("steer_rank", 2), e.key))
    valued = sorted((e for e in live if e.expected_value_cad is not None),
                    key=lambda e: (-e.expected_value_cad, e.key))
    if not valued:
        out["top_actions"] = _unmeasured(
            (f"{len(live)} live experiment(s), none carrying an expected incremental "
             f"contribution; ranking unvalued work would rank by whoever wrote it first"
             if live else "no registered experiment or action carries an expected value"),
            "registered_experiments with expected_value_cad")
    else:
        out["top_actions"] = _measured(
            [{"key": e.key, "product": e.product_slug, "hypothesis": e.hypothesis,
              "expected_incremental_contribution_cad": e.expected_value_cad,
              "owner": e.owner, "decision": e.decision} for e in valued[:TOP_ACTIONS]],
            "registered_experiments.expected_value_cad",
            basis=("expected values are pre-registered estimates, not realised results"),
            unvalued=len(live) - len(valued))
    if binding.get("identifiable"):
        out["top_actions"]["constraint_action"] = binding["action"]
    out["experiments_in_flight"] = _measured(
        [{"key": e.key, "state": e.state, "metric": e.metric, "owner": e.owner,
          "sample": e.sample, "minimum_sample": e.minimum_sample, "gated_on": e.gated_on}
         for e in live], "registered_experiments", count=len(live))

    # 7. winner alerts.
    by_slug: dict[str, list[dict]] = {}
    for o in last:
        by_slug.setdefault(o["slug"], []).append(o)
    if len(last) < MIN_WINNER_ORDERS or len(by_slug) < MIN_PRODUCTS_FOR_WINNERS:
        out["winner_alerts"] = _unmeasured(
            f"{len(last)} order(s) across {len(by_slug)} product(s) in the window against "
            f"floors of {MIN_WINNER_ORDERS} orders and {MIN_PRODUCTS_FOR_WINNERS} products",
            f">= {MIN_WINNER_ORDERS} orders across >= {MIN_PRODUCTS_FOR_WINNERS} products")
    else:
        from .trajectory import WINNER_LIFT

        contrib = {k: sum(o["contribution"] for o in v) for k, v in by_slug.items()}
        ranked = sorted(contrib.values())
        mid = len(ranked) // 2
        median = (ranked[mid] if len(ranked) % 2 else (ranked[mid - 1] + ranked[mid]) / 2)
        winners = sorted(({"product": k, "contribution_cad": round(v, 2),
                           "multiple_of_median": round(v / median, 2) if median else None}
                          for k, v in contrib.items()
                          if median > 0 and v >= WINNER_LIFT * median),
                         key=lambda w: -w["contribution_cad"])
        out["winner_alerts"] = _measured(winners, "orders table, trailing 30 days",
                                         median_contribution_cad=round(median, 2),
                                         threshold_multiple=WINNER_LIFT)

    # 8. risk concentration; 9. owner approvals.
    risk = dependency.report(db)
    out["risk_concentration"] = _measured(
        {"existential": risk["existential"], "not_load_bearing_yet":
         risk["not_load_bearing_yet"], "unmeasurable": risk["unmeasurable"],
         "focus": risk["focus"]}, "scale.dependency.report")
    out["owner_approvals"] = _measured(approvals, "owner_actions (open)",
                                       count=len(approvals))

    measured = [k for k, v in out.items() if v["status"] == MEASURED]
    return {"at": now.isoformat(), "target_cad_per_month": target_cad, "board": out,
            "measured": measured, "unmeasured": [k for k in out if k not in measured],
            "note": ("Every field is measured with its source or UNMEASURED with its reason "
                     "and the n it needs; nothing defaults to zero (#276).")}
