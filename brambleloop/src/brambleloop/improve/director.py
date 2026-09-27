"""The Improvement Director: per-cell backlogs, conflicting local optimisations, and the week.

Requirements 91 and 100. Twelve cells each improving their own number is the design, and it
has one failure the cells cannot see from inside: two of them optimising against each other.
Pricing raising margin while Growth buys acquisition with the same listing, Finance cutting
spend on the runtime that Reliability is paying to keep up, two cells moving the same
threshold in opposite directions. Each change is a local improvement, both can beat their
baselines in isolation, and the company oscillates. A director is the one position from which
the pair is visible, so the rule lives here:

**A conflict is flagged on both sides and neither is promoted until it is resolved.** Not
ranked, not averaged -- whichever promotes first would win by timing, which is not a reason.
Resolution is a recorded decision by somebody who proposed neither.

Three conflicts are detected, all from rows:

* two cells' open proposals touching the same declared surface (a shared gate, threshold,
  weight or prompt);
* two cells whose metrics trade against each other (`OPPOSED`) with open changes at once;
* a measurement-only proposal never conflicts -- measuring changes nothing.

The week's half (#100) is `execute_approved`: the weekly cycle *executes* improvements rather
than writing about them, but only the lowest-risk ones -- the `scoring` tier, already past
their sandbox test, approved by an independent judge, in no conflict -- and it goes through
`cells.promote`, so the tier's cooldown and weekly ceiling still apply. Everything else is
queued for the authority its tier names, with the reason.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .governance import normalise_actor, normalise_touches
from .cells import (BY_KEY, CELLS, PROMOTED, PROPOSED, REJECTED, REVERTED, TESTING,
                    ImprovementRefused)

ACTION = "improve.director"

# Cells whose metrics trade against each other, and what the trade is. A change in one that
# is paid for in the other is a local optimisation, however good it looks on its own curve.
OPPOSED: dict[frozenset, str] = {
    frozenset(("finance", "runtime")):
        "cost removed from the runtime is reliability bought back later (#179's cost "
        "optimiser and reliability engineer, one level up)",
    frozenset(("pricing", "growth")):
        "margin per sale against the number of sales: a price rise and an acquisition push "
        "on the same catalogue cannot both be attributed",
    frozenset(("product_creativity", "pattern_engineering")):
        "novel constructions against first-pass certification: each can win its own "
        "metric by spending the other's",
}

# The only tier the weekly cycle may promote on its own, and only with an independent
# approval. Every other tier needs evidence or a person the week does not have.
AUTO_TIERS: tuple[str, ...] = ("scoring",)

# Proposal kinds that change nothing and so can conflict with nothing.
MEASUREMENT_KINDS: tuple[str, ...] = ("never_measured", "stale_measurement")


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _open_rows(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import Improvement

    with db.session() as s:
        # Normalised exactly as `improve.tiers` normalises them (C-22): 'Weights ' and
        # 'weights' are one surface to the tier, so they are one surface here.
        return [{"id": r.id, "cell": r.cell, "state": r.state,
                 "touches": normalise_touches((r.evidence or {}).get("touches") or ()),
                 "kind": (r.evidence or {}).get("kind"),
                 "proposed_by": normalise_actor((r.evidence or {}).get("proposed_by")),
                 "conflict": (r.evidence or {}).get("conflict")}
                for r in s.scalars(select(Improvement).where(
                    Improvement.state.in_((PROPOSED, TESTING))).order_by(Improvement.id))]


def conflicts(db) -> list[dict]:
    """Every pair of open proposals from different cells that would optimise against each other."""
    rows = [r for r in _open_rows(db) if r["kind"] not in MEASUREMENT_KINDS]
    found = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if a["cell"] == b["cell"]:
                continue
            shared = sorted(set(a["touches"]) & set(b["touches"]))
            opposed = OPPOSED.get(frozenset((a["cell"], b["cell"])))
            if not shared and not opposed:
                continue
            why = (f"{a['cell']} and {b['cell']} both change {shared}: two local "
                   f"optimisations of one surface, and whichever promotes first wins by timing"
                   if shared else
                   f"{a['cell']} and {b['cell']} have metrics that trade against each other: "
                   f"{opposed}")
            found.append({"a": a["id"], "b": b["id"], "cells": [a["cell"], b["cell"]],
                          "shared_surfaces": shared, "opposed_metrics": bool(opposed),
                          "why": why})
    return found


def detect(db, *, now: datetime | None = None) -> dict:
    """Flag every current conflict on both of its proposals. Idempotent."""
    from ..core.models import Improvement

    now = now or datetime.now(timezone.utc)
    found = conflicts(db)
    flagged = []
    for pair in found:
        for me, other in ((pair["a"], pair["b"]), (pair["b"], pair["a"])):
            with db.session() as s:
                row = s.get(Improvement, me)
                evidence = dict(row.evidence or {})
                current = evidence.get("conflict") or {}
                resolved = {int(x) for x in evidence.get("conflict_resolved_with") or ()}
                if other in resolved:
                    continue
                if current.get("with") == other and not current.get("resolved"):
                    continue
                evidence["conflict"] = {"with": other, "why": pair["why"],
                                        "flagged_at": now.isoformat(), "resolved": False}
                row.evidence = evidence
                flagged.append(me)
    return {"conflicts": found, "newly_flagged": sorted(set(flagged))}


def blocking(db, improvement_id: int) -> dict | None:
    """The unresolved conflict holding this improvement, if any."""
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            return None
        conflict = (row.evidence or {}).get("conflict") or {}
        if not conflict or conflict.get("resolved"):
            return None
        other = s.get(Improvement, int(conflict["with"]))
        if other is None or other.state not in (PROPOSED, TESTING):
            return None          # the other side is no longer open; nothing to conflict with
        return dict(conflict)


def resolve(db, *, keep: int, drop: int | None, resolved_by: str, why: str) -> dict:
    """Decide a conflict. The resolver may be neither proposer.

    `drop=None` keeps both, with the reason on the record -- the owner can decide the trade
    is worth it. Otherwise the dropped proposal is rejected with the decision as its reason.
    """
    from ..core.models import Improvement

    if len((why or "").split()) < 5:
        raise ImprovementRefused("a conflict resolution says why; this is a label")
    with db.session() as s:
        kept = s.get(Improvement, keep)
        if kept is None:
            raise ImprovementRefused(f"no improvement {keep}")
        partner = drop if drop is not None else int(
            ((kept.evidence or {}).get("conflict") or {}).get("with") or 0)
        other = s.get(Improvement, partner) if partner else None
        if other is None:
            raise ImprovementRefused(f"improvement {keep} has no conflict partner to resolve")
        proposers = {normalise_actor((r.evidence or {}).get("proposed_by"))
                     for r in (kept, other)}
        if not normalise_actor(resolved_by):
            raise ImprovementRefused("a conflict resolution names who resolved it")
        if normalise_actor(resolved_by) in proposers - {""}:
            raise ImprovementRefused(
                f"{resolved_by!r} proposed one side of this conflict and may not decide it")
        at = datetime.now(timezone.utc).isoformat()
        for row, mate in ((kept, other), (other, kept)):
            evidence = dict(row.evidence or {})
            conflict = dict(evidence.get("conflict") or {"with": mate.id})
            conflict.update({"resolved": True, "resolved_by": resolved_by, "because": why,
                             "resolved_at": at})
            evidence["conflict"] = conflict
            evidence["conflict_resolved_with"] = sorted(
                set(evidence.get("conflict_resolved_with") or ()) | {mate.id})
            row.evidence = evidence
        if drop is not None:
            other.state = REJECTED
            other.evidence = {**(other.evidence or {}),
                              "why": f"conflict resolved against it by {resolved_by}: {why}"}
    return {"kept": keep, "dropped": drop, "resolved_by": resolved_by, "because": why}


# ---- per-cell backlog and experiment set (#91) ---------------------------------------------


def backlog(db, cell: str) -> dict:
    """One cell's defect/opportunity backlog, experiments and history, from the rows."""
    from sqlalchemy import select

    from ..core.models import Improvement
    from . import bus

    if cell not in BY_KEY:
        raise ImprovementRefused(f"unknown cell {cell!r}")
    with db.session() as s:
        rows = [{"id": r.id, "state": r.state, "hypothesis": r.hypothesis,
                 "baseline": r.baseline_value, "result": r.result_value,
                 "touches": list((r.evidence or {}).get("touches") or ()),
                 "conflict": (r.evidence or {}).get("conflict"),
                 "why": (r.evidence or {}).get("why")}
                for r in s.scalars(select(Improvement).where(Improvement.cell == cell)
                                   .order_by(Improvement.id))]
    defects = bus.inbox(db, cell)
    return {
        "cell": cell, "metric": BY_KEY[cell].metric,
        "backlog": [r for r in rows if r["state"] == PROPOSED],
        "defects_and_opportunities": defects,
        "experiments": [r for r in rows if r["state"] == TESTING],
        "history": [r for r in rows if r["state"] in (PROMOTED, REJECTED, REVERTED)],
        "in_conflict": [r["id"] for r in rows if r["conflict"]
                        and not (r["conflict"] or {}).get("resolved")
                        and r["state"] in (PROPOSED, TESTING)],
    }


def backlogs(db) -> dict:
    return {c.key: backlog(db, c.key) for c in CELLS}


# ---- the week: STOP list, next upgrades, experiments, execution (#100) ----------------------


def experiments(db, *, days: int = 7, now: datetime | None = None) -> dict:
    """Experiments that reached a verdict in the window: completed, and the killed subset."""
    from sqlalchemy import select

    from ..core.models import Improvement

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    completed, killed = [], []
    with db.session() as s:
        for r in s.scalars(select(Improvement).order_by(Improvement.id)):
            if r.state not in (PROMOTED, REJECTED, REVERTED):
                continue
            evidence = r.evidence or {}
            decided = (_aware(r.reverted_at) if r.state == REVERTED else
                       _aware(r.promoted_at) if r.state == PROMOTED else None)
            if decided is None and evidence.get("decided_at"):
                decided = datetime.fromisoformat(evidence["decided_at"])
            decided = _aware(decided) or _aware(r.at)
            if decided < cutoff:
                continue
            entry = {"improvement": r.id, "cell": r.cell, "state": r.state,
                     "baseline": r.baseline_value, "result": r.result_value,
                     "why": evidence.get("why") or evidence.get("reverted_because") or ""}
            completed.append(entry)
            if r.state in (REJECTED, REVERTED):
                killed.append(entry)
    return {"completed": completed, "killed": killed}


def stop_doing(db, *, stale_after_days: int = 30) -> list[dict]:
    """What the record says to stop: answered tactics, reverted changes, unread lessons."""
    from sqlalchemy import select

    from ..core.models import Improvement
    from . import bus, profiles

    stops: list[dict] = []
    with db.session() as s:
        rows = list(s.scalars(select(Improvement)))
        by_reason: dict[tuple[str, str], list[int]] = {}
        for r in rows:
            reason = ((r.evidence or {}).get("why") or "")[:80]
            if r.state == REJECTED and reason and not reason.startswith("resolved_by"):
                by_reason.setdefault((r.cell, reason), []).append(r.id)
            if r.state == REVERTED:
                stops.append({"stop": f"re-trying improvement {r.id} on {r.cell}",
                              "because": (r.evidence or {}).get("reverted_because")
                              or "it reverted in production",
                              "evidence": [r.id]})
    for (cell, reason), ids in by_reason.items():
        if len(ids) >= profiles.REPEATED_REJECTION:
            stops.append({"stop": f"proposing this tactic family in {cell}",
                          "because": f"rejected {len(ids)} times for: {reason}",
                          "evidence": ids})
    stale = bus.compounding(db, stale_after_days=stale_after_days)["stale_unacted"]
    by_subject: dict[str, list[int]] = {}
    for lesson in stale:
        by_subject.setdefault(lesson["subject"], []).append(lesson["id"])
    for subject, ids in by_subject.items():
        stops.append({"stop": f"publishing {subject!r} lessons nobody acts on",
                      "because": (f"{len(ids)} routed lesson(s) untouched past "
                                  f"{stale_after_days} days: route them to an owner of the "
                                  f"fix or stop producing them"),
                      "evidence": ids})
    return stops


def next_upgrades(db, *, limit: int = 5) -> list[dict]:
    """The open changes nearest to landing, cheapest risk first, with the step each needs."""
    from . import tiers

    ranked = []
    for r in _open_rows(db):
        if r["kind"] in MEASUREMENT_KINDS:
            continue
        try:
            tier = tiers.classify(r["touches"])
        except tiers.TierRefused:
            continue
        step = ("resolve the Director's conflict first" if r["conflict"]
                and not (r["conflict"] or {}).get("resolved") else
                "an independent judge's approval" if r["state"] == TESTING else
                "a sandbox result against the recorded baseline")
        ranked.append({"improvement": r["id"], "cell": r["cell"], "state": r["state"],
                       "tier": tier.key, "rank": tier.rank, "next_step": step})
    ranked.sort(key=lambda x: (x["state"] != TESTING, x["rank"], x["improvement"]))
    return ranked[:limit]


def execute_approved(db, *, executor: str = "evaluator") -> dict:
    """Promote the approved, tested, lowest-risk changes; queue everything else for authority.

    Goes through `cells.promote`, so separation of duties, the Director's conflict check and
    the tier's evidence, cooldown and weekly ceiling are all enforced there rather than
    re-implemented here -- a rule enforced at one call site is enforced at the ones somebody
    thought of.
    """
    from sqlalchemy import select

    from ..core.models import Improvement
    from . import cells, tiers

    detect(db)
    with db.session() as s:
        testing = [(r.id, r.cell, normalise_touches((r.evidence or {}).get("touches") or ()),
                    (r.evidence or {}).get("approved_by") or "",
                    (r.evidence or {}).get("proposed_by") or "")
                   for r in s.scalars(select(Improvement).where(Improvement.state == TESTING)
                                      .order_by(Improvement.id))]

    executed, queued = [], []
    for improvement_id, cell, touches, approver, proposer in testing:
        try:
            tier = tiers.classify(touches)
        except tiers.TierRefused as exc:
            queued.append({"improvement": improvement_id, "cell": cell, "authority": "owner",
                           "why": str(exc)[:200]})
            continue
        if tier.key not in AUTO_TIERS:
            queued.append({"improvement": improvement_id, "cell": cell, "tier": tier.key,
                           "authority": "owner" if tier.needs_owner else "evaluator",
                           "why": (f"{tier.key} tier needs {list(tier.requires)}; the weekly "
                                   f"cycle executes only {list(AUTO_TIERS)} changes")})
            continue
        if not approver:
            queued.append({"improvement": improvement_id, "cell": cell, "tier": tier.key,
                           "authority": "evaluator",
                           "why": "tested and low-risk, and not yet approved by a judge "
                                  "independent of its proposer"})
            continue
        try:
            cells.promote(db, improvement_id, promoted_by=executor)
        except (ImprovementRefused, tiers.TierRefused) as exc:
            queued.append({"improvement": improvement_id, "cell": cell, "tier": tier.key,
                           "authority": "evaluator", "why": str(exc)[:300]})
            continue
        executed.append({"improvement": improvement_id, "cell": cell, "tier": tier.key,
                         "approved_by": approver, "proposed_by": proposer,
                         "promoted_by": executor})
    return {"executed": executed, "queued_for_authority": queued,
            "auto_tiers": list(AUTO_TIERS),
            "note": (f"{len(executed)} approved low-risk change(s) executed, {len(queued)} "
                     f"queued for the authority their tier names")}


# ---- #192: which cells have earned their standing cost -------------------------------------


def retirement_candidates(db, *, now: datetime | None = None) -> dict:
    """The cells as `swarm.orchestrate.retirement_review` reads them, from rows.

    A cell's completed work is what it produced in the review window: capability readings
    and improvements decided. A data-gated cell is left out rather than reviewed -- a
    Pricing cell with no sale to measure is waiting for a customer, not weak, and retiring
    it would remove the department the first sale needs.
    """
    from sqlalchemy import select

    from ..core.models import CapabilityPoint, Improvement, Lesson
    from ..swarm.orchestrate import IDLE_DAYS_BEFORE_REVIEW
    from . import measure

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=IDLE_DAYS_BEFORE_REVIEW)
    with db.session() as s:
        points = [(p.cell, _aware(p.at)) for p in s.scalars(select(CapabilityPoint))]
        decided = [(r.cell, _aware(r.promoted_at or r.reverted_at or r.at))
                   for r in s.scalars(select(Improvement))
                   if r.state in (PROMOTED, REJECTED, REVERTED)]
        lessons = [(l.origin_cell, l.id) for l in s.scalars(select(Lesson))]

    reviewed, waiting = [], []
    for cell in CELLS:
        out = measure.measure_cell(db, cell.key, now=now)
        if isinstance(out, measure.NotMeasured) and out.reason.startswith("data-gated"):
            waiting.append({"cell": cell.key, "why": out.reason})
            continue
        mine = [at for c, at in points if c == cell.key]
        work = [at for at in mine if at >= cutoff] + [at for c, at in decided
                                                      if c == cell.key and at >= cutoff]
        reviewed.append({"key": cell.key, "scope": cell.metric, "tasks": len(work),
                         "last_success_at": max(mine) if mine else None,
                         "lessons": [i for c, i in lessons if c == cell.key]})
    return {"cells": reviewed, "waiting_for_data": waiting}


def state(db) -> dict:
    found = conflicts(db)
    return {
        "conflicts": found,
        "opposed_metrics": {" vs ".join(sorted(k)): v for k, v in OPPOSED.items()},
        "auto_tiers": list(AUTO_TIERS),
        "rules": [
            "a conflict is flagged on both sides and neither is promoted until resolved",
            "a conflict is resolved by somebody who proposed neither side",
            "the weekly cycle executes only approved, tested, scoring-tier changes, through "
            "cells.promote and its tier limits",
        ],
    }
