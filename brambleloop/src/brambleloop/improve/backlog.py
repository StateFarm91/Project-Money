"""The bounded improvement backlog: every open proposal is evaluated, or it expires on record.

W4-LEARN (2026-10-11). Production's Improvement record held 15 proposals, all PROPOSED, the
oldest weeks old, and the sandbox reported every one of them "waiting for a trial that can
evaluate them" on every pass. Fourteen were the teardown lab's delight hypotheses (#169,
"Raising customization on <slug> from 3 to at least 4 would make the product feel better than
expected"), one per product, re-derived on every product QA. Nothing measured them again and
nothing closed them, so the backlog could only grow -- the opposite of a learning loop.

This pass is the consumer the backlog lacked. It adds no authority: every transition goes
through the `cells` door (`test_result`, `reject`) that already refuses the wrong thing.

**A delight hypothesis is re-measured with the instrument that raised it.** The proposal was
opened from `teardown.lab.delight_for(... measured_self_scores ...)`; the evaluator re-reads
the same driver for the same product. Metric: the driver's score on the 1-5 teardown scale.
Baseline: the score recorded on the proposal. Decision rule:

- the score moved above the baseline -> `cells.test_result` records it and the row moves to
  TESTING (the hypothesis is verified on its own metric; the change itself landed through the
  product's release gates, which is where a product change is judged);
- the score moved below the baseline -> `cells.test_result` rejects it as a regression;
- the score is unchanged after `DELIGHT_TTL_DAYS` -> rejected as *expired unexecuted*, with the
  measurement that shows nothing changed. The reason is worded identically for every product so
  the Director's STOP list (`director.stop_doing`) can see the producer is generating work
  nobody executes, which is itself the lesson;
- the driver cannot be read (no certified version, no artefact) -> UNKNOWN, waits, and expires
  as *expired unmeasured* after the same TTL. Never scored as 0.

**Every other proposal with no registered trial expires after `STALE_PROPOSAL_DAYS`**, and a
cell holding more than `OPEN_CAP_PER_CELL` open, untrialled proposals has its oldest deferred
on record until it is back at the cap. A proposal a trial can evaluate is never capped or
expired here: it is being evaluated.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import cells

ACTION = "improve.backlog"
EVALUATOR = "backlog_evaluator"

DELIGHT_PREFIX = "delight:"
DELIGHT_TARGET = 4.0
DELIGHT_TTL_DAYS = 14
STALE_PROPOSAL_DAYS = 30
OPEN_CAP_PER_CELL = 8

# Reasons start with a fixed phrase (no slug inside the first 80 characters), because
# `director.stop_doing` groups rejections by their first 80 characters.
EXPIRED_UNEXECUTED = ("expired unexecuted: the driver this hypothesis promised to raise was "
                      "re-measured unchanged after the TTL")
EXPIRED_UNMEASURED = ("expired unmeasured: the driver this hypothesis names could not be "
                      "re-measured within the TTL")
EXPIRED_NO_TRIAL = ("expired: no registered trial or measurer evaluated this proposal "
                    "within the backlog TTL")
DEFERRED_CAP = ("deferred: the cell's open untrialled backlog is over its bound, oldest "
                "proposal closed first")


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def delight_target(baseline_ref: str) -> tuple[str, str] | None:
    """(slug, driver) for a delight proposal's `delight:<slug>:<driver>` reference."""
    if not (baseline_ref or "").startswith(DELIGHT_PREFIX):
        return None
    rest = baseline_ref[len(DELIGHT_PREFIX):]
    slug, _, driver = rest.rpartition(":")
    return (slug, driver) if slug and driver else None


def remeasure_delight(db, slug: str, driver: str) -> dict:
    """The driver's score now, read exactly as the proposal's was (`teardown.lab`)."""
    from ..teardown import lab

    try:
        delight = lab.delight_for(db, f"{lab.SELF_PREFIX}{slug}",
                                  measured=lab.measured_self_scores(db, slug))
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN, never a score
        return {"measured": False, "value": None,
                "why": f"the delight reading failed: {type(exc).__name__}: {str(exc)[:160]}"}
    value = (delight.get("drivers") or {}).get(driver)
    if value is None:
        return {"measured": False, "value": None,
                "why": (f"{driver} on {slug} has nothing to read now (no certified version or "
                        f"artefact carries it); UNKNOWN, not 0")}
    return {"measured": True, "value": float(value),
            "run_ref": f"delight:{slug}:{driver}:{float(value)}",
            "why": f"{driver} on {slug} reads {float(value)} from the product's own artefacts"}


def _open_rows(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import Improvement

    with db.session() as s:
        return [{"id": r.id, "cell": r.cell, "at": _aware(r.at), "baseline": r.baseline_value,
                 "baseline_ref": r.baseline_ref or "", "evidence": dict(r.evidence or {})}
                for r in s.scalars(select(Improvement).where(
                    Improvement.state == cells.PROPOSED).order_by(Improvement.id))]


def evaluate(db, *, now: datetime | None = None, audit: bool = True) -> dict:
    """One pass over the open backlog: measure, decide, or expire. Returns what moved."""
    from ..core.models import AuditLog
    from . import runner

    now = now or datetime.now(timezone.utc)
    verified, regressed, expired, waiting, deferred = [], [], [], [], []
    rows = _open_rows(db)
    for r in rows:
        target = delight_target(r["baseline_ref"])
        if target is None:
            continue
        slug, driver = target
        age_days = (now - r["at"]).total_seconds() / 86400 if r["at"] else 0.0
        reading = remeasure_delight(db, slug, driver)
        base = r["baseline"]
        stamp = {"backlog": {"by": EVALUATOR, "at": now.isoformat(), "slug": slug,
                             "driver": driver, "baseline": base, "target": DELIGHT_TARGET,
                             "reading": reading.get("value"), "why": reading["why"],
                             "age_days": round(age_days, 2)}}
        if reading["measured"] and base is not None and reading["value"] != base:
            state = cells.test_result(db, r["id"], reading["value"], evidence={
                **stamp, "sandbox": {"trial": "delight_remeasure", "by": EVALUATOR,
                                     "run_ref": reading["run_ref"], "at": now.isoformat(),
                                     "why": reading["why"]}})
            entry = {"improvement": r["id"], "cell": r["cell"], "slug": slug,
                     "driver": driver, "baseline": base, "result": reading["value"],
                     "state": state}
            (verified if state == cells.TESTING else regressed).append(entry)
            continue
        if age_days >= DELIGHT_TTL_DAYS:
            why = EXPIRED_UNEXECUTED if reading["measured"] else EXPIRED_UNMEASURED
            cells.reject(db, r["id"], why=f"{why} ({DELIGHT_TTL_DAYS} days): {reading['why']}",
                         evidence=stamp)
            expired.append({"improvement": r["id"], "cell": r["cell"], "slug": slug,
                            "driver": driver, "reading": reading.get("value"),
                            "why": why.split(":", 1)[0]})
            continue
        waiting.append({"improvement": r["id"], "cell": r["cell"], "slug": slug,
                        "driver": driver, "reading": reading.get("value"),
                        "measured": reading["measured"],
                        "expires_in_days": round(DELIGHT_TTL_DAYS - age_days, 2)})

    # Generic bound: untrialled, non-delight proposals expire, and a cell over its cap is
    # trimmed oldest first. A proposal with a registered trial is being evaluated: untouched.
    untrialled: dict[str, list[dict]] = {}
    for r in _open_rows(db):
        ev = r["evidence"]
        if (delight_target(r["baseline_ref"]) is not None or runner.trial_for(ev)
                or ev.get("kind") in runner.MEASUREMENT_KINDS):
            continue
        age_days = (now - r["at"]).total_seconds() / 86400 if r["at"] else 0.0
        if age_days >= STALE_PROPOSAL_DAYS:
            cells.reject(db, r["id"], why=f"{EXPIRED_NO_TRIAL} ({STALE_PROPOSAL_DAYS} days)",
                         evidence={"backlog": {"by": EVALUATOR, "at": now.isoformat(),
                                               "age_days": round(age_days, 2)}})
            expired.append({"improvement": r["id"], "cell": r["cell"],
                            "why": EXPIRED_NO_TRIAL.split(":", 1)[0]})
            continue
        untrialled.setdefault(r["cell"], []).append(r)
    for cell, open_rows in untrialled.items():
        excess = len(open_rows) - OPEN_CAP_PER_CELL
        for r in open_rows[:max(excess, 0)]:              # oldest first (ordered by id)
            cells.reject(db, r["id"], why=f"{DEFERRED_CAP} (cap {OPEN_CAP_PER_CELL})",
                         evidence={"backlog": {"by": EVALUATOR, "at": now.isoformat()}})
            deferred.append({"improvement": r["id"], "cell": cell})

    out = {"at": now.isoformat(), "open_before": len(rows),
           "open_after": len(_open_rows(db)),
           "verified": verified, "regressed": regressed, "expired": expired,
           "deferred": deferred, "waiting": waiting,
           "bounds": {"delight_ttl_days": DELIGHT_TTL_DAYS,
                      "stale_proposal_days": STALE_PROPOSAL_DAYS,
                      "open_cap_per_cell": OPEN_CAP_PER_CELL},
           "note": (f"{len(verified)} verified, {len(regressed)} regressed, {len(expired)} "
                    f"expired, {len(deferred)} deferred, {len(waiting)} waiting inside their "
                    f"TTL")}
    if audit:
        with db.session() as s:
            s.add(AuditLog(actor=EVALUATOR, action=ACTION, detail={
                k: (v[:50] if isinstance(v, list) else v) for k, v in out.items()}))
    return out


def admit_delight(db, *, cell: str, ref: str, now: datetime | None = None) -> dict | None:
    """Admission control for the delight producer. None admits; a dict says why not.

    Refuses a reference rejected within the cooldown (the same hypothesis re-opened the day
    after it expired is the backlog refilling itself) and a cell already holding
    `OPEN_CAP_PER_CELL` open delight proposals.
    """
    from sqlalchemy import select

    from ..core.models import Improvement

    now = now or datetime.now(timezone.utc)
    cooldown = now - timedelta(days=DELIGHT_TTL_DAYS * 2)
    with db.session() as s:
        recent = [r for r in s.scalars(select(Improvement).where(
            Improvement.baseline_ref == ref, Improvement.state == cells.REJECTED))
            if (_aware(datetime.fromisoformat((r.evidence or {})["decided_at"]))
                if (r.evidence or {}).get("decided_at") else _aware(r.at)) >= cooldown]
        open_in_cell = sum(1 for r in s.scalars(select(Improvement).where(
            Improvement.cell == cell, Improvement.state == cells.PROPOSED))
            if (r.baseline_ref or "").startswith(DELIGHT_PREFIX))
    if recent:
        return {"improvement": None, "cooldown": ref,
                "why": (f"{ref} was closed {len(recent)} time(s) in the last "
                        f"{DELIGHT_TTL_DAYS * 2} days; not re-opened until the cooldown ends")}
    if open_in_cell >= OPEN_CAP_PER_CELL:
        return {"improvement": None, "deferred": ref,
                "why": (f"{cell} already holds {open_in_cell} open delight proposals (cap "
                        f"{OPEN_CAP_PER_CELL}); a new one waits for one to be decided")}
    return None


def state() -> dict:
    return {"action": ACTION, "evaluator": EVALUATOR,
            "bounds": {"delight_ttl_days": DELIGHT_TTL_DAYS,
                       "stale_proposal_days": STALE_PROPOSAL_DAYS,
                       "open_cap_per_cell": OPEN_CAP_PER_CELL},
            "delight_metric": "the named driver's score on the 1-5 teardown scale, re-read by "
                              "teardown.lab.delight_for over measured_self_scores",
            "decision_rule": "moved up -> TESTING (verified); moved down -> REJECTED; "
                             "unchanged or unreadable past the TTL -> REJECTED as expired"}
