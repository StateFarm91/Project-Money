"""F-859 Visual Economics: yield, rejection reasons, latency, compute, spend and cost per
certified listing set (W4-C08).

Reads only what the image-production workflow already records (`visual.image_records`):
* `image_production_runs` -- one row per listing gallery (slug@version@release): its status,
  generation calls and spend;
* `image_candidates` -- one row per candidate image: outcome, failure categories, cost and
  latency.

A **certified listing set** is a gallery that passed every automated gate: run status
`ready_for_owner_review` (waiting for the owner's look) or `approved_for_publication`.
**Cost per certified listing set** is ALL spend -- the blocked and abandoned galleries
included, because that is what producing the certified ones actually cost -- divided by the
number of certified sets. It is None (never 0) when nothing is certified yet or any
candidate's cost is unknown. Deterministic, read-only, CA$0.
"""
from __future__ import annotations

CERTIFIED_STATES = ("ready_for_owner_review", "approved_for_publication")
KIND = "visual.economics"


def _secs(a, b) -> float | None:
    try:
        return max((b - a).total_seconds(), 0.0)
    except Exception:  # noqa: BLE001 - a missing timestamp is unknown, not zero
        return None


def summary(db, *, slug: str | None = None) -> dict:
    from sqlalchemy import select

    from .image_records import ImageCandidate, ImageProductionRun, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        rq, cq = select(ImageProductionRun), select(ImageCandidate)
        if slug:
            rq, cq = rq.where(ImageProductionRun.slug == slug), cq.where(
                ImageCandidate.slug == slug)
        runs = [{"run_key": r.run_key, "listing": r.listing, "status": r.status,
                 "calls": r.generation_calls or 0, "spent_cad": float(r.spent_cad or 0.0),
                 "wall_s": _secs(r.created_at, r.updated_at)} for r in s.scalars(rq)]
        cands = [{"run_key": c.run_key, "outcome": c.outcome, "cost": c.cost_cad,
                  "latency": c.latency_s, "cats": list(c.failure_categories or []),
                  "role": c.role} for c in s.scalars(cq)]
    reasons: dict[str, int] = {}
    for c in cands:
        if c["outcome"] != "accepted":
            for cat in c["cats"] or ["uncategorised"]:
                reasons[cat] = reasons.get(cat, 0) + 1
    accepted = sum(1 for c in cands if c["outcome"] == "accepted")
    unknown_cost = sum(1 for c in cands if c["cost"] is None)
    cand_spend = sum(c["cost"] for c in cands if c["cost"] is not None)
    run_spend = sum(r["spent_cad"] for r in runs)
    # The run's own spend counter covers calls that left no candidate (a provider error);
    # the larger of the two is the honest total.
    spent = round(max(run_spend, cand_spend), 4)
    certified = [r for r in runs if r["status"] in CERTIFIED_STATES]
    lat = [c["latency"] for c in cands if c["latency"] is not None]
    per_set = []
    for r in runs:
        mine = [c for c in cands if c["run_key"] == r["run_key"]]
        per_set.append({"run_key": r["run_key"], "listing": r["listing"],
                        "status": r["status"], "certified": r["status"] in CERTIFIED_STATES,
                        "candidates": len(mine),
                        "accepted": sum(1 for c in mine if c["outcome"] == "accepted"),
                        "generation_calls": r["calls"], "spent_cad": round(r["spent_cad"], 4),
                        "wall_clock_s": r["wall_s"]})
    return {
        "listing_sets": len(runs), "certified_listing_sets": len(certified),
        "candidates": len(cands), "accepted": accepted,
        "yield": round(accepted / len(cands), 4) if cands else None,
        "rejection_reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        "latency_s": ({"total": round(sum(lat), 2), "mean": round(sum(lat) / len(lat), 2),
                       "max": max(lat), "measured": len(lat)} if lat else None),
        "compute": {"generation_calls": sum(r["calls"] for r in runs),
                    "candidates_judged": len(cands)},
        "spent_cad": spent, "candidates_with_unknown_cost": unknown_cost,
        "cost_per_certified_listing_set_cad": (
            round(spent / len(certified), 4) if certified and not unknown_cost else None),
        "cost_per_accepted_image_cad": (round(spent / accepted, 4)
                                        if accepted and not unknown_cost else None),
        "per_set": per_set,
        "certified_means": list(CERTIFIED_STATES),
        "rule": ("all spend, blocked galleries included, over certified sets; None when "
                 "nothing is certified or a cost is unknown -- never 0"),
    }


def record(db) -> dict:
    """One persisted reading per day, so the economics have a history."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from ..core.models import OperatingReading

    out = summary(db)
    slim = {k: v for k, v in out.items() if k != "per_set"}
    key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == KIND,
                                                      OperatingReading.period_key == key))
        if row is None:
            s.add(OperatingReading(kind=KIND, period_key=key, payload=slim))
        else:
            row.payload = slim
    return slim
