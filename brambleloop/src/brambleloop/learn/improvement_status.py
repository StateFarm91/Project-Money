"""Learn / continuous self-improvement status for the Owner Command Center and the orchestrator.

Two read-only functions (v1.1 cross-lane contract, lane B):

* `summary(db)` -- the department's provider: every measured loop, its active policy, the
  decisions and outcomes it has observed, proposals and experiments by state, promotions and
  rollbacks with their measured evidence, and the persisted lessons. Never raises; an empty
  database is `UNKNOWN` with the reason, never a row of zeros.
* `next_work(db)` -- work items the Executive Orchestrator (lane A) can enqueue for the Learn
  department, most urgent first. Contract in `next_work`'s docstring.

Neither function writes anything. UNKNOWN is never rendered as 0: a count is a count of rows
that exist; a metric that has not been measured is `None` with `reading: "UNMEASURED"`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

SOURCES = ["learn_decisions", "learn_proposals", "learn_policy_lessons", "improvements",
           "config_versions", "learn_gaps", "core.models.ListingOutcome",
           "core.models.SupportCase", "core.models.ListingAsset", "core.models.CostEntry",
           "core.models.Incident", "src/brambleloop/improve/policy_loops.py",
           "src/brambleloop/improve/invariants.py"]


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value):
    value = _aware(value)
    return value.isoformat() if value else None


def _loop_item(db, lp, s) -> dict:
    from sqlalchemy import select

    from ..improve import policy_loops as pl
    from ..learn.models import LearnDecision, LearnProposal

    decisions = list(s.scalars(select(LearnDecision).where(LearnDecision.loop == lp.key)))
    observed = [d for d in decisions if d.outcome is not None]
    proposals = list(s.scalars(select(LearnProposal).where(LearnProposal.loop == lp.key)
                               .order_by(LearnProposal.id)))
    by_state: dict[str, int] = {}
    for p in proposals:
        by_state[p.state] = by_state.get(p.state, 0) + 1
    evaluated = [p for p in proposals if (p.evidence or {}).get("incumbent")]
    last = evaluated[-1] if evaluated else None
    lp_reading = (last.evidence or {}).get("incumbent") if last is not None else None
    measured = (len(observed) >= pl.MIN_DECISIONS and lp_reading is not None
                and pl._sufficient(lp, lp_reading) is None)
    active = pl.active(db, lp.key)
    return {
        "loop": lp.key, "title": lp.title, "cell": lp.cell, "family": lp.family,
        "param": lp.param, "active": active,
        "reading": "measured" if measured else "UNMEASURED",
        "why_unmeasured": (None if measured else
                           f"{len(observed)} decision(s) with an observed outcome (needs "
                           f"{pl.MIN_DECISIONS}); source: {lp.outcome_source}"
                           if len(observed) < pl.MIN_DECISIONS else
                           ("not evaluated yet" if lp_reading is None else
                            pl._sufficient(lp, lp_reading))),
        "decisions_logged": len(decisions), "decisions_with_outcome": len(observed),
        "metric": lp.metric, "guardrail": lp.guardrail,
        "last_evaluation": None if last is None else {
            "proposal": last.id, "at": _iso(last.at), "state": last.state,
            "params_from": last.params_from, "params_to": last.params_to,
            "baseline": last.baseline, "result": last.result,
            "basis": "measured (replay estimator on logged decisions)"
                     if lp.family == "replay" else
                     "measured (exact counterfactual F1 on observed subjects)"},
        "proposals_by_state": by_state,
        "promotions": [{"proposal": p.id, "improvement": p.improvement_id,
                        "params_from": p.params_from, "params_to": p.params_to,
                        "baseline": p.baseline, "result": p.result,
                        "decided_at": _iso(p.decided_at)}
                       for p in proposals if p.state in (pl.PROMOTED, pl.ROLLED_BACK)],
        "rollbacks": [{"proposal": p.id, "improvement": p.improvement_id,
                       "params_to": p.params_to,
                       "monitoring": (p.evidence or {}).get("rollback"),
                       "decided_at": _iso(p.decided_at)}
                      for p in proposals if p.state == pl.ROLLED_BACK],
        "refusals": by_state.get(pl.REFUSED, 0),
        "consumer": lp.consumer, "consumer_status": lp.consumer_status,
        "proposer": lp.proposer, "challenger": lp.challenger,
    }


def summary(db) -> dict:
    """The Learn / self-improvement provider (lane B contract). Never raises."""
    try:
        return _summary(db)
    except Exception as exc:  # noqa: BLE001 - a provider reports, it does not crash the page
        return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
                "sources": SOURCES,
                "reason": f"learn status unreadable: {type(exc).__name__}: {str(exc)[:200]}"}


def _summary(db) -> dict:
    from sqlalchemy import func, select

    from ..core.models import Improvement
    from ..improve import invariants
    from ..improve import policy_loops as pl
    from ..learn.models import LearnDecision, LearnPolicyLesson, LearnProposal

    with db.session() as s:
        items = [_loop_item(db, lp, s) for lp in pl.LOOPS]
        pipeline: dict[str, dict[str, int]] = {}
        rollback_pending = []
        for r in s.scalars(select(Improvement)):
            ev = r.evidence or {}
            trial = ev.get("sandbox_trial") or "untrialled"
            pipeline.setdefault(trial, {})
            pipeline[trial][r.state] = pipeline[trial].get(r.state, 0) + 1
            if r.state == "promoted" and ev.get("rollback_pending"):
                rollback_pending.append(r.id)
        stamps = [s.scalar(select(func.max(LearnDecision.outcome_at))),
                  s.scalar(select(func.max(LearnProposal.at))),
                  s.scalar(select(func.max(LearnPolicyLesson.at)))]
    stamps = [_aware(x) for x in stamps if x is not None]
    recent = pl.lessons(db, limit=10)

    measured = [i for i in items if i["reading"] == "measured"]
    any_rows = any(i["decisions_logged"] or i["proposals_by_state"] for i in items) or \
        bool(pipeline)
    if not any_rows:
        status, reason = "UNKNOWN", ("no policy-loop decision, outcome or proposal has been "
                                     "recorded yet; the loops are built and waiting for data")
    elif rollback_pending:
        status, reason = "DEGRADED", f"rollback pending verification on {rollback_pending}"
    elif len(measured) < len(items):
        status = "DEGRADED"
        reason = (f"{len(items) - len(measured)} of {len(items)} loops are UNMEASURED "
                  f"(not enough observed outcomes)")
    else:
        status, reason = "OK", "every loop has a measured evaluation"

    return {
        "status": status, "reason": reason,
        "as_of": max(stamps).isoformat() if stamps else None,
        "basis": "measured" if measured else "unknown",
        "items": items,
        "pipeline": {"improvements_by_trial_and_state": pipeline,
                     "rollback_pending": rollback_pending,
                     "closed_loops": ["league_replay (job priority -> swarm.orchestrate."
                                      "priority_for)",
                                      "self_audit (standard floor -> release gate)",
                                      "policy_loop (five launch loops -> consumers above)"]},
        "lessons": recent,
        "guardrail": {"protected_invariants": [i.key for i in invariants.PROTECTED_INVARIANTS],
                      "refusals_total": sum(i["refusals"] for i in items)},
        "sources": SOURCES,
    }


# ---- next_work -------------------------------------------------------------------------------


def _item(kind: str, key: str, priority: int, reason: str, evidence: dict,
          job_type: str | None = None) -> dict:
    return {"kind": kind, "key": key, "priority": int(priority), "reason": reason,
            "evidence": evidence, "department": "learn", "job_type": job_type}


def next_work(db) -> list[dict]:
    """Work the Learn department should do next, most urgent first. Read-only; never raises.

    Contract (for lane A's Executive Orchestrator):
      each item = {"kind": str, "key": str, "priority": int 1..100 (higher is more urgent),
                   "reason": str, "evidence": dict (row ids / values it was derived from),
                   "department": "learn", "job_type": str | None}
      * `key` is a stable idempotency key: the same situation yields the same key every call.
      * `job_type` names an existing registered handler that does the work when one exists
        ("improve.sandbox", "improve.monitor", "learn.scan"); None means the item is a
        review/decision for a department, not a job.
      * kinds: learn.complete_rollback (90), learn.monitor_promotion (75),
        learn.sandbox_proposal (70), finance.cost_review (65), quality.extra_review (60),
        visual.precheck (55), learn.evaluate_loop (50), learn.lesson_gap (40, +20 when the
        topic is on the defect watchlist), learn.instrument_loop (20), learn.provider_error
        (10).
      * Every item is derived from rows; an empty database returns the instrument items only.
    """
    out: list[dict] = []
    for section in (_rollbacks_and_pipeline, _loops_work, _watch_work, _gap_work):
        try:
            out.extend(section(db))
        except Exception as exc:  # noqa: BLE001 - one section never silences the others
            out.append(_item("learn.provider_error", f"learn.provider_error:{section.__name__}",
                             10, f"{section.__name__} unreadable: {type(exc).__name__}",
                             {"error": str(exc)[:200]}))
    seen = set()
    unique = []
    for item in sorted(out, key=lambda i: (-i["priority"], i["key"])):
        if item["key"] not in seen:
            seen.add(item["key"])
            unique.append(item)
    return unique


def _rollbacks_and_pipeline(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import Improvement
    from ..improve import policy_loops as pl

    items = []
    with db.session() as s:
        rows = list(s.scalars(select(Improvement).where(
            Improvement.state.in_(("proposed", "testing", "promoted")))))
        for r in rows:
            ev = r.evidence or {}
            trial = ev.get("sandbox_trial")
            if r.state == "promoted" and ev.get("rollback_pending"):
                items.append(_item("learn.complete_rollback", f"rollback:{r.id}", 90,
                                   "a rollback was decided and is not yet verified complete",
                                   {"improvement": r.id, "pending": ev["rollback_pending"]},
                                   "improve.monitor"))
            elif r.state in ("proposed", "testing") and trial == pl.TRIAL:
                items.append(_item("learn.sandbox_proposal", f"sandbox:{r.id}", 70,
                                   "a policy-loop proposal is waiting for its sandbox trial, "
                                   "tests and independent judge",
                                   {"improvement": r.id, "state": r.state,
                                    "baseline": r.baseline_value}, "improve.sandbox"))
            elif r.state == "promoted" and trial == pl.TRIAL:
                change = ev.get("change") or {}
                promoted_at = _aware(r.promoted_at)
                fresh = [d for d in pl._decisions(db, change.get("loop", ""), after=promoted_at)
                         if d["outcome"] is not None] if promoted_at else []
                if len(fresh) >= pl.MIN_FRESH:
                    items.append(_item("learn.monitor_promotion",
                                       f"monitor:{r.id}:{pl.fingerprint(fresh)[:12]}", 75,
                                       f"{len(fresh)} post-promotion outcomes are observed; "
                                       f"retain or roll back",
                                       {"improvement": r.id, "loop": change.get("loop"),
                                        "fresh_decisions": len(fresh)}, "improve.monitor"))
    return items


def _loops_work(db) -> list[dict]:
    from sqlalchemy import select

    from ..improve import policy_loops as pl
    from ..learn.models import LearnProposal

    items = []
    now = datetime.now(timezone.utc)
    for lp in pl.LOOPS:
        rows = [r for r in pl._decisions(db, lp.key) if r["outcome"] is not None]
        if len(rows) < pl.MIN_DECISIONS:
            items.append(_item("learn.instrument_loop", f"instrument:{lp.key}", 20,
                               f"{lp.title}: {len(rows)} observed outcome(s), needs "
                               f"{pl.MIN_DECISIONS}. {lp.consumer_status}",
                               {"loop": lp.key, "observed": len(rows),
                                "outcome_source": lp.outcome_source}))
            continue
        fp = pl.fingerprint(rows)
        with db.session() as s:
            last = s.scalar(select(LearnProposal).where(LearnProposal.loop == lp.key)
                            .order_by(LearnProposal.id.desc()))
            judged = last is not None and (last.evidence or {}).get("fingerprint") == fp
            recent = last is not None and now - _aware(last.at) < timedelta(hours=24)
        if not judged and not recent:
            items.append(_item("learn.evaluate_loop", f"evaluate:{lp.key}:{fp[:12]}", 50,
                               f"{lp.title}: {len(rows)} observed outcomes not yet evaluated "
                               f"against the incumbent",
                               {"loop": lp.key, "observed": len(rows), "fingerprint": fp},
                               "improve.sandbox"))
    return items


def _watch_work(db) -> list[dict]:
    from sqlalchemy import select

    from ..improve import policy_loops as pl
    from ..learn.models import LearnDecision

    items = []
    watch = pl.defect_watchlist(db)
    if watch["topics"]:
        with db.session() as s:
            open_versions = [d for d in s.scalars(select(LearnDecision).where(
                LearnDecision.loop == "pattern_defect_watch",
                LearnDecision.outcome.is_(None)))]
            for d in open_versions:
                hit = sorted(set(d.features.get("topics") or []) & set(watch["topics"]))
                if hit:
                    items.append(_item("quality.extra_review", f"extra_review:{d.subject}", 60,
                                       f"{d.subject} touches watched defect topic(s) {hit} "
                                       f"(observed rate >= {watch['threshold']['value']}); "
                                       f"extra review, on top of every gate",
                                       {"subject": d.subject, "topics": hit,
                                        "rates": {t: watch["topics"][t] for t in hit},
                                        "threshold": watch["threshold"]}))
    pre = pl.visual_precheck(db)
    for group, rate in pre["groups"].items():
        items.append(_item("visual.precheck", f"visual_precheck:{group}", 55,
                           f"asset group {group} is blocked by the visual gate at {rate}; "
                           f"pre-check before the next render", {"group": group, "rate": rate,
                                                                 "threshold": pre["threshold"]}))
    cost = pl.cost_watch(db)
    for slug, early in cost["releases"].items():
        items.append(_item("finance.cost_review", f"cost_review:{slug}", 65,
                           f"release {slug} spent CA${early:.2f} in its first cost entries "
                           f"(actual); review before it continues. A flag only: no ceiling "
                           f"moves", {"product_slug": slug, "early_cost_cad": early,
                                      "threshold": cost["threshold"]}))
    return items


def _gap_work(db) -> list[dict]:
    from sqlalchemy import select

    from ..improve import policy_loops as pl
    from ..learn.models import LearnGap

    watched = set(pl.defect_watchlist(db)["topics"])
    items = []
    with db.session() as s:
        for g in s.scalars(select(LearnGap).where(LearnGap.state == "QUEUED")):
            bonus = 20 if g.topic in watched else 0
            items.append(_item("learn.lesson_gap", f"lesson_gap:{g.topic}", 40 + bonus,
                               f"no approved lesson covers {g.topic}"
                               + ("; it is on the defect watchlist" if bonus else ""),
                               {"topic": g.topic, "sources": len(g.evidence or []),
                                "defect_watch": bool(bonus)}, None))
    return items
