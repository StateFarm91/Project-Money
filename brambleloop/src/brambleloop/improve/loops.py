"""The learning loops, each with its producer, store, metric, baseline, decision rule and consumer.

W4-LEARN (2026-10-11). The owner's scoreboard read "improvement cells measured 0/12, lessons
acted on 0". Behind those two numbers are eight different loops, and production's rows show
they fail in different ways: some are measured and simply have nothing to accept yet, some
accumulated proposals nobody evaluated, one ran a real experiment whose verdict never reached
the scoreboard, and some cannot move before a sale. One number per loop hides which.

`scoreboard(db)` reads each loop from rows and reports, per loop:

- `producer` / `store` / `consumer` -- where proposals come from, where they accumulate, and
  what accepts or rejects them;
- `metric`, `baseline`, `decision_rule` -- what makes the outcome a measurement;
- `status` -- MEASURED (the loop has a measured outcome on record), WAITING (it runs and has
  nothing decidable yet), UNKNOWN (no real data exists to measure it; never shown as 0) and
  `outcomes` -- accepted / rejected / open counts from rows.

Read-only. Nothing here moves a row.
"""
from __future__ import annotations

from datetime import datetime, timezone

MEASURED = "MEASURED"
WAITING = "WAITING"
UNKNOWN = "UNKNOWN"

# Which cells have a runtime decision that reads its lesson inbox and records `acted_on`
# (`consume.act` call sites). A routed cell outside this map has no consumer: a lesson sent
# only there can never be acted on, before or after launch.
LESSON_CONSUMERS: dict[str, str] = {
    "market_radar": "radar.score (lesson score adjustment)",
    "pattern_engineering": "radar.score -> cir.draft heuristic (favouring lessons only)",
    "seo_search": "listing.seo (tag slot)",
    "customer_experience": "support triage (lesson attached to a case)",
    "growth": "growth content plan",
    "portfolio": "seasonal daily plan",
    "learn": "learn.scan (gap moved up the editor's plan)",
}


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _cells_loop(db) -> dict:
    from sqlalchemy import select

    from ..core.models import CapabilityPoint
    from .cells import CELLS

    with db.session() as s:
        cells_seen = {}
        for p in s.scalars(select(CapabilityPoint).order_by(CapabilityPoint.id)):
            cells_seen.setdefault(p.cell, []).append(p.value)
    measured = sorted(k for k in cells_seen)
    unmeasured = sorted(c.key for c in CELLS if c.key not in cells_seen)
    return {
        "loop": "capability_cells", "producer": "improve.measure (daily)",
        "store": "CapabilityPoint", "metric": "each cell's own metric (cells.CELLS)",
        "baseline": "the cell's first reading", "decision_rule":
            "retrospective direction per cell, outside the metric's noise floor",
        "consumer": "improve.retrospective -> bottleneck / department health",
        "status": MEASURED if measured else UNKNOWN,
        "outcomes": {"measured": len(measured), "of": len(CELLS),
                     "with_two_or_more_readings": sum(1 for v in cells_seen.values()
                                                      if len(v) >= 2)},
        "unknown": unmeasured,
        "why": ("cells with no reading are UNKNOWN: their source rows (sales, orders, traffic, "
                "forecasts) do not exist before launch" if unmeasured else ""),
    }


def _lessons_loop(db) -> dict:
    from sqlalchemy import select

    from ..core.models import Lesson

    with db.session() as s:
        rows = list(s.scalars(select(Lesson)))
    live = [r for r in rows if r.superseded_by is None]
    routed = [r for r in live if r.routed_to]
    acted = [r for r in routed if r.acted_on_by]
    no_consumer = [r for r in routed
                   if not any(c in LESSON_CONSUMERS for c in (r.routed_to or []))]
    by_subject: dict[str, dict] = {}
    for r in routed:
        d = by_subject.setdefault(r.subject, {"live": 0, "acted_on": 0,
                                              "consumers": sorted(
                                                  c for c in (r.routed_to or [])
                                                  if c in LESSON_CONSUMERS)})
        d["live"] += 1
        d["acted_on"] += 1 if r.acted_on_by else 0
    return {
        "loop": "lesson_bus", "producer": "improve.mine (failures), intel findings, learn radar",
        "store": "Lesson (live = not superseded)",
        "metric": "routed live lessons acted on / routed live lessons",
        "baseline": "0 acted on (no consumer existed for most subjects)",
        "decision_rule": ("a consumer acts only when the lesson changes its decision "
                          "(consume.matching threshold); acted_on is recorded by that consumer"),
        "consumer": LESSON_CONSUMERS,
        "status": (MEASURED if acted else WAITING if routed else UNKNOWN),
        "outcomes": {"live": len(live), "superseded": len(rows) - len(live),
                     "routed": len(routed), "acted_on": len(acted),
                     "routed_only_to_cells_without_a_consumer": len(no_consumer)},
        "by_subject": by_subject,
        "why": ("" if acted else
                "no consumer decision has matched a lesson yet; lessons routed only to cells "
                "without a consumer cannot be acted on by construction"),
    }


def _replay_loop(db) -> dict:
    from sqlalchemy import select

    from ..core.models import ConfigVersion
    from . import replay

    kind, key = replay._policy_key()
    with db.session() as s:
        rows = list(s.scalars(select(ConfigVersion).where(
            ConfigVersion.kind == kind, ConfigVersion.key == key).order_by(ConfigVersion.id)))
    verdicts, rejected, accepted, open_ = [], 0, 0, 0
    incumbent = next((r for r in rows if r.incumbent), None)
    for r in rows:
        outcome = dict(r.measured_outcome or {})
        full = outcome.get("league_verdict_full") or {}
        if outcome.get("retired_by") == replay.ACTION:
            rejected += 1
            verdicts.append({"config_id": r.id, "version": r.version, "verdict": "rejected",
                             "quality_gain": full.get("quality_gain"),
                             "why": (full.get("blockers") or [""])[0][:160],
                             "runs_judged": len(outcome.get("evidence_refs") or [])})
        elif not r.incumbent and r.retired_at is None:
            open_ += 1
        if r.incumbent and r.version > 1:
            accepted += 1
    return {
        "loop": "job_priority_replay", "producer": "improve.replay (daily; challengers by "
                                                  "prompt_tool_challenger)",
        "store": "ConfigVersion (policy/job_priority) + league runs",
        "metric": f"band-weighted on-time share on the {replay.SIMULATOR['version']} replay of "
                  f"the last {replay.WINDOW_DAYS} days of terminal jobs",
        "baseline": "the incumbent's replay of the same jobs, same run",
        "decision_rule": "league.compare: quality gain above the margin on shared days AND "
                         "held on the newest-fifth holdout; otherwise retired with the verdict "
                         f"and re-trialled after {replay.RETRIAL_DAYS} days",
        "consumer": "improve.sandbox (evaluator approves, scoring tier promotes) -> "
                    "swarm.orchestrate.priority_policy on the next enqueue",
        "status": (MEASURED if verdicts or accepted else
                   WAITING if rows else UNKNOWN),
        "outcomes": {"rejected": rejected, "accepted": accepted, "open": open_,
                     "incumbent": incumbent.id if incumbent else None},
        "verdicts": verdicts[-10:],
        "why": "" if rows else ("no replay has run: it needs at least "
                                f"{replay.MIN_JOBS} terminal jobs over {replay.MIN_DAYS} days"),
    }


def _improvements_loop(db) -> dict:
    from sqlalchemy import select

    from ..core.models import Improvement
    from . import backlog, cells

    with db.session() as s:
        rows = list(s.scalars(select(Improvement)))
    by_state: dict[str, int] = {}
    delight: dict[str, int] = {}
    for r in rows:
        by_state[r.state] = by_state.get(r.state, 0) + 1
        if backlog.delight_target(r.baseline_ref or ""):
            delight[r.state] = delight.get(r.state, 0) + 1
    decided = sum(by_state.get(k, 0) for k in (cells.TESTING, cells.PROMOTED,
                                               cells.REJECTED, cells.REVERTED))
    return {
        "loop": "improvement_backlog",
        "producer": "teardown lab delight QA (#169), policy loops, replay, teardown pipeline",
        "store": "Improvement",
        "metric": "per row: its own metric (delight driver score / trial metric / cell metric)",
        "baseline": "captured at proposal time (cells.propose)",
        "decision_rule": backlog.state()["decision_rule"] + "; untrialled proposals expire "
                         f"after {backlog.STALE_PROPOSAL_DAYS} days; at most "
                         f"{backlog.OPEN_CAP_PER_CELL} open untrialled per cell",
        "consumer": "improve.sandbox -> improve.backlog.evaluate + registered trials",
        "status": MEASURED if decided else (WAITING if rows else UNKNOWN),
        "outcomes": {"by_state": by_state, "delight_by_state": delight,
                     "open": by_state.get(cells.PROPOSED, 0), "decided": decided},
        "why": "" if rows else "no proposal has been recorded",
    }


def _realised_loop(db) -> dict:
    from . import roi

    out = roi.realised_benefit(db)
    return {
        "loop": "realised_benefit", "producer": "promotions (cells.promote)",
        "store": "Improvement (promoted) + CapabilityPoint",
        "metric": "movement of the promoted change's metric after realisation_days",
        "baseline": "the proposal-time baseline", "decision_rule": "roi neutral band",
        "consumer": "improve.runner.discipline (stagnation throttle), role scorecards",
        "status": MEASURED if out.get("assessed") else UNKNOWN,
        "outcomes": {k: out.get(k) for k in ("promotions", "assessed", "hit_rate")},
        "why": "" if out.get("assessed") else
               "no promoted change has been assessed; nothing to measure, not a zero return",
    }


def _growth_loop(db) -> dict:
    from sqlalchemy import select

    from ..core.models import Experiment

    with db.session() as s:
        rows = list(s.scalars(select(Experiment)))
    by_state: dict[str, int] = {}
    for r in rows:
        by_state[r.state] = by_state.get(r.state, 0) + 1
    decided = [r for r in rows if r.result]
    return {
        "loop": "growth_experiments", "producer": "growth experiment registry",
        "store": "Experiment", "metric": "each experiment's declared metric",
        "baseline": "holdout / pre-period, per design", "decision_rule":
            "growth.conclude: stop rule and minimum sample per design",
        "consumer": "growth.conclude",
        "status": MEASURED if decided else UNKNOWN,
        "outcomes": {"by_state": by_state, "decided": len(decided)},
        "why": "" if decided else ("no listing is live, so no visit, order or attach rate "
                                   "exists to conclude any experiment on: UNKNOWN, not 0"),
    }


def _learn_loop(db) -> dict:
    try:
        from ..learn import metrics

        m = metrics.department_metrics(db)
    except Exception as exc:  # noqa: BLE001 - reported, not hidden
        return {"loop": "learn_gap_coverage", "status": UNKNOWN,
                "why": f"{type(exc).__name__}: {str(exc)[:160]}"}
    total = m.get("gaps_total") or 0
    return {
        "loop": "learn_gap_coverage", "producer": "learn.scan (hourly)",
        "store": "LearnGap / Lesson (learn)", "metric": "gaps covered / gaps total",
        "baseline": "coverage at first scan", "decision_rule":
            "a gap is covered only by an approved lesson; routed bus lessons re-rank gaps",
        "consumer": "learn.scan -> editor's plan; consume.act records the lesson",
        "status": MEASURED if total else UNKNOWN,
        "outcomes": {k: m.get(k) for k in ("gaps_total", "gaps_covered", "coverage",
                                           "lessons_approved")},
        "why": "" if total else "no source-backed learner gap recorded",
    }


LOOPS = (_cells_loop, _lessons_loop, _replay_loop, _improvements_loop, _realised_loop,
         _growth_loop, _learn_loop)


def scoreboard(db) -> dict:
    """Every learning loop's status from rows, and the totals the owner's scoreboard reads."""
    out = []
    for fn in LOOPS:
        try:
            out.append(fn(db))
        except Exception as exc:  # noqa: BLE001 - one unreadable loop never hides the others
            out.append({"loop": fn.__name__.strip("_"), "status": UNKNOWN,
                        "why": f"unreadable: {type(exc).__name__}: {str(exc)[:160]}"})
    count = {s: sum(1 for x in out if x.get("status") == s)
             for s in (MEASURED, WAITING, UNKNOWN)}
    replay_ = next((x for x in out if x["loop"] == "job_priority_replay"), {})
    impr = next((x for x in out if x["loop"] == "improvement_backlog"), {})
    lessons = next((x for x in out if x["loop"] == "lesson_bus"), {})
    by_state = (impr.get("outcomes") or {}).get("by_state") or {}
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "loops": out, "count": count,
        "experiments": {
            # A replay winner is accepted through its Improvement row, so it is counted
            # there once; a replay loser has no row and is counted from its verdict.
            "accepted": by_state.get("testing", 0) + by_state.get("promoted", 0),
            "rejected": ((replay_.get("outcomes") or {}).get("rejected") or 0)
            + by_state.get("rejected", 0) + by_state.get("reverted", 0),
            "open": by_state.get("proposed", 0)
            + ((replay_.get("outcomes") or {}).get("open") or 0),
        },
        "lessons": lessons.get("outcomes") or {},
        "note": (f"{count[MEASURED]} loop(s) measured, {count[WAITING]} waiting with nothing "
                 f"decidable, {count[UNKNOWN]} UNKNOWN for want of real data"),
    }
