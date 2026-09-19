"""What each cell knows about itself, and the review it runs on its own record.

Requirement 177. Every agent or cell keeps a versioned capability profile: its objective, its
baseline, the mistakes it has made, the lessons routed to it, the tactics that worked, the
tactics that did not, the prompt and tool versions it is currently running, and the
challengers competing with them. Then it reviews its own outcomes and proposes improvements
backed by that evidence.

Almost all of that already exists in this company, scattered: capability history, improvement
rows, the lesson bus, the configuration league. What did not exist is the view from one cell's
position, which is the only position from which the question "am I getting better, and at
what" can be asked. A profile is therefore assembled rather than stored -- there is no second
copy of the truth to drift from the first.

The review is deliberately deterministic. A model can write a plausible improvement hypothesis
about anything, which is precisely the problem: a cell that proposes fluently every week looks
like a cell that is learning. These proposals each come from a specific pattern in the cell's
own recorded rows -- a capability falling over consecutive measurements, a tactic family
rejected twice for the same reason, a metric nobody has measured in a month -- and each
carries the rows it came from. A cell with a clean record proposes nothing, and that is the
correct output rather than a gap to fill.

Nothing here promotes. Proposals enter the ordinary pipeline: the governance check, the
sandbox result, the risk tier and its cooldown. A self-review that could promote itself is
the unsupervised rewriting #178 forbids, arriving from inside the department that is supposed
to be measuring.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .cells import BY_KEY, CELLS, PROMOTED, PROPOSED, REJECTED, REVERTED, TESTING

# Consecutive measurements moving the wrong way before the cell is asked to look at itself.
# Two is noise on almost any metric; three is a direction.
DECLINE_RUN = 3

# A metric nobody has measured in this long is the commonest real state of an improvement
# programme, and the one nobody proposes anything about.
STALE_AFTER_DAYS = 30

# A tactic family rejected this many times has been answered.
REPEATED_REJECTION = 2

# Which agent answers for each cell, where the mapping is unambiguous. Cells without one are
# owned by the orchestrator, and saying so is better than inventing an agent per cell.
CELL_AGENT: dict[str, str] = {
    "product_creativity": "market_radar",
    "pattern_engineering": "crochet_engineer",
    "quality": "quality_director",
    "market_radar": "market_radar",
    "pricing": "pricing",
    "creative_assets": "asset_truth",
    "seo_search": "listing",
    "growth": "growth",
    "customer_experience": "support",
    "portfolio": "orchestrator",
    "finance": "cfo",
    "runtime": "orchestrator",
}


class ProfileRefused(ValueError):
    """A profile asked for a cell that does not exist."""


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def profile(db, cell_key: str, *, now: datetime | None = None) -> dict:
    """One cell's capability profile, assembled from the rows rather than kept beside them."""
    from sqlalchemy import select

    from ..core.models import CapabilityPoint, ConfigVersion, Improvement, Lesson

    cell = BY_KEY.get(cell_key)
    if cell is None:
        raise ProfileRefused(f"{cell_key!r} is not a cell: {sorted(BY_KEY)}")

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        history = sorted(
            ((_aware(h.at), h.value, dict(h.detail or {}))
             for h in s.scalars(select(CapabilityPoint).where(
                 CapabilityPoint.cell == cell_key))),
            key=lambda row: row[0])
        improvements = [
            {"id": i.id, "state": i.state, "hypothesis": i.hypothesis,
             "baseline": i.baseline_value, "result": i.result_value,
             "at": _aware(i.at).isoformat(),
             "evidence": dict(i.evidence or {})}
            for i in s.scalars(select(Improvement).where(Improvement.cell == cell_key))]
        lessons = [
            {"id": l.id, "subject": l.subject, "statement": l.statement,
             "acted_on": bool(l.acted_on_by),
             "from_here": l.origin_cell == cell_key}
            for l in s.scalars(select(Lesson))
            if l.origin_cell == cell_key or cell_key in (l.routed_to or [])]
        versions = [
            {"kind": v.kind, "key": v.key, "version": v.version,
             "incumbent": v.incumbent, "why_changed": v.why_changed,
             "measured_outcome": v.measured_outcome}
            for v in s.scalars(select(ConfigVersion))
            if cell_key in (v.affected_departments or [])]

    latest = history[-1] if history else None
    first = history[0] if history else None
    return {
        "cell": cell_key,
        "agent": CELL_AGENT.get(cell_key, "orchestrator"),
        "department": cell.department,
        "objective": cell.what_it_means,
        "metric": cell.metric,
        "higher_is_better": cell.higher_is_better,
        "measured_by": cell.measure,
        "baseline": (first[1] if first else None),
        "latest": (latest[1] if latest else None),
        "measurements": len(history),
        "last_measured_at": (latest[0].isoformat() if latest else None),
        "days_since_measured": (round((now - latest[0]).total_seconds() / 86400, 1)
                                if latest else None),
        "successful_tactics": [i for i in improvements if i["state"] == PROMOTED],
        "rejected_tactics": [i for i in improvements if i["state"] == REJECTED],
        "reverted_tactics": [i for i in improvements if i["state"] == REVERTED],
        "in_flight": [i for i in improvements if i["state"] in (PROPOSED, TESTING)],
        "lessons": lessons,
        "running_versions": [v for v in versions if v["incumbent"]],
        "challengers": [v for v in versions if not v["incumbent"]],
        "note": ("this cell has never been measured, so it has no baseline and no capability "
                 "-- which is a different thing from a capability of zero and is the state "
                 "most cells are actually in"
                 if not history else
                 f"{len(history)} measurement(s), {len([i for i in improvements if i['state'] == PROMOTED])} "
                 f"promoted tactic(s), {len(lessons)} lesson(s) in reach"),
    }


def self_review(db, cell_key: str, *, now: datetime | None = None) -> dict:
    """What this cell's own record says it should try next, with the rows behind each.

    Proposals only. A self-review that could promote itself is unsupervised rewriting
    arriving from inside the department that is supposed to be measuring.
    """
    state = profile(db, cell_key, now=now)
    cell = BY_KEY[cell_key]
    now = now or datetime.now(timezone.utc)
    proposals: list[dict] = []

    from sqlalchemy import select

    from ..core.models import CapabilityPoint

    with db.session() as s:
        history = sorted(
            ((_aware(h.at), h.value) for h in s.scalars(select(CapabilityPoint).where(
                CapabilityPoint.cell == cell_key))),
            key=lambda row: row[0])

    # 1. A capability moving the wrong way for three consecutive measurements is a direction
    #    rather than noise, and it is the one pattern a cell never notices about itself.
    if len(history) >= DECLINE_RUN:
        window = history[-DECLINE_RUN:]
        worse = all(
            (b < a if cell.higher_is_better else b > a)
            for (_, a), (_, b) in zip(window, window[1:]))
        if worse:
            proposals.append({
                "kind": "declining_capability",
                "hypothesis": (
                    f"{cell.metric} has moved the wrong way across {DECLINE_RUN} consecutive "
                    f"measurements in {cell.department}; the last promoted change in this "
                    f"cell should be re-examined before anything else is tried"),
                "evidence": {"measurements": [[at.isoformat(), v] for at, v in window]},
                "why": ("a run is a direction and a single point is weather, and the cell "
                        "that owns the metric is the last to see the run"),
            })

    # 2. Nobody has measured it. The commonest real state, and the one no cell proposes
    #    anything about because there is nothing to look at.
    days = state["days_since_measured"]
    if state["measurements"] == 0:
        proposals.append({
            "kind": "never_measured",
            "hypothesis": (
                f"{cell.metric} has never been measured in {cell.department}, so no change "
                f"here can be shown to be an improvement; the first act is a measurement "
                f"rather than a change"),
            "evidence": {"measurements": 0, "measured_by": cell.measure},
            "why": "a first measurement is a baseline, not a result",
        })
    elif days is not None and days > STALE_AFTER_DAYS:
        proposals.append({
            "kind": "stale_measurement",
            "hypothesis": (
                f"{cell.metric} was last measured {days:.0f} days ago in {cell.department}; "
                f"re-measure before proposing anything, because a change measured against a "
                f"month-old baseline is measured against a different company"),
            "evidence": {"days_since_measured": days,
                         "last_measured_at": state["last_measured_at"]},
            "why": "an old baseline is a comparison with something that no longer exists",
        })

    # 3. A tactic family the evidence has already answered twice.
    by_reason: dict[str, list[int]] = {}
    for rejected in state["rejected_tactics"]:
        reason = (rejected["evidence"] or {}).get("why", "")
        if reason:
            by_reason.setdefault(reason[:80], []).append(rejected["id"])
    for reason, ids in by_reason.items():
        if len(ids) >= REPEATED_REJECTION:
            proposals.append({
                "kind": "answered_tactic",
                "hypothesis": (
                    f"{len(ids)} changes in {cell.department} have now been rejected for the "
                    f"same reason; the family should be recorded as answered rather than "
                    f"retried with different wording"),
                "evidence": {"improvement_ids": ids, "reason": reason},
                "why": ("repeating a rejected tactic is how an improvement programme spends "
                        "a quarter learning the same thing"),
            })

    # 4. A lesson routed here that nobody acted on.
    untouched = [l for l in state["lessons"] if not l["acted_on"] and not l["from_here"]]
    if untouched:
        proposals.append({
            "kind": "unused_lesson",
            "hypothesis": (
                f"{len(untouched)} lesson(s) routed to {cell.department} have not been acted "
                f"on; each is either applicable and unused or misrouted, and both are worth "
                f"resolving before new hypotheses are written"),
            "evidence": {"lesson_ids": [l["id"] for l in untouched][:10]},
            "why": ("compounding is measured by what acted on a lesson, not by how many "
                    "exist"),
        })

    return {
        "cell": cell_key,
        "agent": state["agent"],
        "proposals": proposals,
        "profile": state,
        "note": ("this cell's record shows nothing to act on, which is the correct output of "
                 "a review rather than a gap to fill: a cell that proposes fluently every "
                 "week looks exactly like a cell that is learning"
                 if not proposals else
                 f"{len(proposals)} proposal(s), each from a pattern in this cell's own "
                 f"rows. None of them is promoted here: they enter the ordinary pipeline "
                 f"with its governance check, sandbox result and risk tier"),
    }


def review_all(db, *, now: datetime | None = None) -> dict:
    """Every cell's self-review, with the ones that found something first."""
    reviews = [self_review(db, cell.key, now=now) for cell in CELLS]
    reviews.sort(key=lambda r: -len(r["proposals"]))
    return {
        "cells": len(reviews),
        "with_proposals": len([r for r in reviews if r["proposals"]]),
        "reviews": [{"cell": r["cell"], "agent": r["agent"],
                     "proposals": r["proposals"],
                     "measurements": r["profile"]["measurements"]} for r in reviews],
        "note": ("Each proposal comes from a pattern in one cell's own recorded rows, and "
                 "none of them promotes anything. A review that could promote itself is "
                 "unsupervised rewriting arriving from inside the department that is "
                 "supposed to be measuring (#177, #178)."),
    }
