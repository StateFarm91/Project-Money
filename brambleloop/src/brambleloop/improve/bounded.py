"""The bounded experiment: a sandbox trial every department's cell can be judged by.

F-705 (Permanent Learning Loop): "Every department continuously runs OBSERVE -> detect
opportunity/failure -> HYPOTHESIS -> EXPERIMENT -> MEASURE -> ADVERSARIAL VALIDATION ->
PROMOTE/REJECT -> MONITOR." The loop existed (`improve.runner`), and a proposal on most cells
waited for ever, because the registered trials evaluate only a few kinds of change (a
rollback, a priority-policy replay, a self-audit floor, a policy-loop parameter, a measured
price). The other departments had a HYPOTHESIS step and no EXPERIMENT step.

F-412 (Research-to-Experiment Bridge): "Translate promising research into the smallest bounded
experiment that can falsify or support its applicability before a large build or spend."
`intel.research.bridge` turned an answered research task into a proposal carrying its day
bound -- and nothing ever called it, and nothing could evaluate what it produced.

This module is the missing EXPERIMENT step, for every cell:

* A proposal is **bounded** when it declares `scope.max_days` (the research bridge does). Its
  baseline is the cell's production reading taken before the change.
* The owning department applies the change with `start()`, which records who applied it, the
  reference of what was applied, and how to undo it -- the experiment window opens then and
  closes `max_days` later. A baseline that did not exist at proposal time is taken here, from
  the newest production reading *before* the change, never after.
* `trial()` is registered in `improve.runner.TRIALS`. It runs only when the window has closed,
  reads only `improve.measure` production readings inside the window (never the points a
  promotion or the monitor wrote for itself), and returns their mean in the cell's own units.
  Re-deriving it from the same rows gives the same number, which is what the runner's
  adversarial test checks.
* A window another change on the same cell landed in is **confounded**: the reading cannot be
  attributed to this change. The trial does not run; the runner marks the row superseded with
  the confounders named (F-126), so it is retained, closed and never read as a failure.

`research_intake()` is the runtime caller the bridge lacked (`improve.sandbox` runs it every
pass). `coverage()` is the loop per department, read off the registries rather than claimed.
No model is called and nothing is spent: a bounded proposal with a spend bound above zero is
still bounded by `improve.governance` at proposal time.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import cells, governance

TRIAL = "bounded_experiment"
EXPERIMENT = "experiment"
MIN_READINGS = 2           # one reading inside a window is an anecdote about one day
MAX_DAYS = 90
START_ACTION = "improve.experiment_started"
INTAKE_ACTION = "improve.research_intake"
RESEARCH_PROPOSER = "research"


class ExperimentRefused(ValueError):
    """A start the experiment's own rules forbid."""


def _aware(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def max_days(evidence: dict | None) -> int | None:
    try:
        d = int(((evidence or {}).get("scope") or {}).get("max_days") or 0)
    except (TypeError, ValueError):
        return None
    return d if 0 < d <= MAX_DAYS else None


def is_bounded(evidence: dict | None) -> bool:
    """A proposal that declared how long its experiment may run, and is not trial-metric."""
    ev = evidence or {}
    return max_days(ev) is not None and not (ev.get("trial_metric") or {}).get("metric")


def _production_points(db, cell: str, *, after: datetime | None = None,
                       until: datetime | None = None) -> list:
    from sqlalchemy import select

    from ..core.models import CapabilityPoint
    from . import measure

    with db.session() as s:
        rows = list(s.scalars(select(CapabilityPoint).where(CapabilityPoint.cell == cell)
                              .order_by(CapabilityPoint.id)))
        out = []
        for p in rows:
            if (p.detail or {}).get("from") != measure.SOURCE:
                continue          # a promotion's own point or the monitor's verdict is not one
            at = _aware(p.at)
            if after is not None and at <= after:
                continue
            if until is not None and at > until:
                continue
            out.append((p.id, at, float(p.value)))
        return out


def start(db, improvement_id: int, *, applied_by: str, applied_ref: str, undo: str,
          now: datetime | None = None) -> dict:
    """The owning department applied the change: open the experiment window."""
    from ..core.models import AuditLog, Improvement

    now = now or _now()
    who = governance.normalise_actor(applied_by)
    if not who or not (applied_ref or "").strip():
        raise ExperimentRefused("a started experiment names who applied it and what was "
                                "applied (a commit, a config version, a listing id)")
    if len((undo or "").split()) < 3:
        raise ExperimentRefused("an experiment states how it is undone before it starts")
    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            raise ExperimentRefused(f"no improvement {improvement_id}")
        ev = dict(row.evidence or {})
        days = max_days(ev)
        if row.state != cells.PROPOSED or not is_bounded(ev):
            raise ExperimentRefused(
                f"improvement {improvement_id} is {row.state} and "
                f"{'bounded' if days else 'declares no scope.max_days'}; only a PROPOSED "
                f"bounded experiment starts")
        if ev.get(EXPERIMENT):
            raise ExperimentRefused(f"improvement {improvement_id} already started at "
                                    f"{ev[EXPERIMENT]['started_at']}")
        cell = row.cell
        need_baseline = row.baseline_value is None
    anchored = None
    if need_baseline:
        before = [p for p in _production_points(db, cell) if p[1] <= now]
        if not before:
            raise ExperimentRefused(
                f"{cell} has no production reading before the change, so there would be "
                f"nothing to compare the experiment with. improve.measure must read it first")
        pid, _at, value = before[-1]
        anchored = {"value": value, "ref": f"capability_history:{pid}", "at": now.isoformat()}
    ends = now + timedelta(days=days)
    exp = {"started_at": now.isoformat(), "ends_at": ends.isoformat(), "max_days": days,
           "applied_by": who, "applied_ref": applied_ref.strip()[:200],
           "undo": undo.strip()[:300]}
    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        ev = dict(row.evidence or {})
        ev[EXPERIMENT] = exp
        if anchored is not None and row.baseline_value is None:
            row.baseline_value = anchored["value"]
            row.baseline_ref = anchored["ref"][:80]
            ev["baseline_anchored"] = anchored
        row.evidence = ev
        s.add(AuditLog(actor=who[:60], action=START_ACTION,
                       artifact=f"improvement:{improvement_id}",
                       detail={"improvement": improvement_id, "cell": cell, **exp}))
    return {"improvement": improvement_id, "cell": cell, **exp,
            **({"baseline_anchored": anchored} if anchored else {})}


def _window(ev: dict) -> tuple[datetime, datetime] | None:
    exp = ev.get(EXPERIMENT) or {}
    if not exp.get("started_at"):
        return None
    return (_aware(datetime.fromisoformat(exp["started_at"])),
            _aware(datetime.fromisoformat(exp["ends_at"])))


def confounders(db, improvement_id: int) -> list[dict]:
    """Other changes on the same cell that landed inside this experiment's window."""
    from sqlalchemy import select

    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        win = _window(dict(row.evidence or {})) if row else None
        if win is None:
            return []
        lo, hi = win
        found = []
        for r in s.scalars(select(Improvement).where(Improvement.cell == row.cell,
                                                     Improvement.id != row.id)):
            for what, at in (("promoted", r.promoted_at), ("reverted", r.reverted_at)):
                at = _aware(at)
                if at is not None and lo <= at <= hi:
                    found.append({"improvement": r.id, "event": what, "at": at.isoformat()})
            other = _window(dict(r.evidence or {}))
            if other is not None and other[0] <= hi and lo <= other[1]:
                found.append({"improvement": r.id, "event": "concurrent experiment",
                              "at": other[0].isoformat()})
        return found


def trial(db, improvement_id: int) -> dict:
    """The cell's production readings inside the closed experiment window (F-705)."""
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            return {"ran": False, "trial": TRIAL, "why": f"no improvement {improvement_id}"}
        ev, cell = dict(row.evidence or {}), row.cell
    win = _window(ev)
    if win is None:
        return {"ran": False, "trial": TRIAL,
                "why": (f"a bounded experiment of at most {max_days(ev)} day(s), not started: "
                        f"the {cell} department applies it with improve.bounded.start, "
                        f"which records what was applied and how it is undone")}
    lo, hi = win
    if _now() < hi:
        return {"ran": False, "trial": TRIAL,
                "why": f"the experiment window is open until {hi.isoformat()}"}
    conf = confounders(db, improvement_id)
    if conf:
        return {"ran": False, "trial": TRIAL, "confounded": conf,
                "why": (f"{len(conf)} other change(s) on {cell} landed inside the window, so "
                        f"the reading cannot be attributed to this one")}
    points = _production_points(db, cell, after=lo, until=hi)
    if len(points) < MIN_READINGS:
        return {"ran": False, "trial": TRIAL,
                "why": (f"{len(points)} production reading(s) of {cell} inside the window; "
                        f"{MIN_READINGS} are needed before it is a measurement")}
    value = round(sum(v for _i, _a, v in points) / len(points), 6)
    ids = [i for i, _a, _v in points]
    return {"ran": True, "trial": TRIAL, "value": value,
            "run_ref": f"capability_history:{cell}:{ids}"[:190],
            "reads": {"cell": cell, "points": ids, "window": [lo.isoformat(), hi.isoformat()]},
            "why": (f"{len(ids)} production reading(s) of {cell} between {lo.date()} and "
                    f"{hi.date()} average {value}")}


# ---- F-412: research findings into the loop ----------------------------------------------

# Which cell owns a research task's decision, by the decision_ref's first segment. A task
# whose decision no cell owns is reported, never filed under a guess.
DECISION_CELL: dict[str, str] = {
    "pricing": "pricing", "price": "pricing", "listing": "seo_search", "seo": "seo_search",
    "visual": "creative_assets", "asset": "creative_assets", "pattern": "pattern_engineering",
    "cir": "pattern_engineering", "creative": "product_creativity", "concept": "product_creativity",
    "support": "customer_experience", "cx": "customer_experience", "growth": "growth",
    "marketing": "growth", "ads": "growth", "portfolio": "portfolio", "finance": "finance",
    "radar": "market_radar", "intel": "market_radar", "quality": "quality", "qa": "quality",
    "gate": "quality", "runtime": "runtime", "ops": "runtime", "learn": "learn",
}


def cell_for(decision_ref: str, detail: dict | None = None) -> str | None:
    named = str((detail or {}).get("cell") or "")
    if named in cells.BY_KEY:
        return named
    head = (decision_ref or "").split(".", 1)[0].split(":", 1)[0].strip().lower()
    cell = DECISION_CELL.get(head)
    return cell if cell in cells.BY_KEY else None


def research_intake(db, *, now: datetime | None = None) -> dict:
    """Bridge every answered research task with a bounded next test into the loop (F-412)."""
    from sqlalchemy import select

    from ..intel import research as R

    now = now or _now()
    bridged, skipped = [], []
    try:
        with db.session() as s:
            tasks = [(t.id, t.decision_ref, dict(t.detail or {}))
                     for t in s.scalars(select(R.ResearchTask).where(
                         R.ResearchTask.state == R.ANSWERED).order_by(R.ResearchTask.id))]
    except Exception as exc:  # noqa: BLE001 - no research table yet
        return {"bridged": [], "skipped": [], "read": 0,
                "why": f"research tasks unreadable: {type(exc).__name__}"}
    for tid, decision_ref, d in tasks:
        if d.get("bridged_improvement"):
            continue
        c = d.get("conclusion") or {}
        if (c.get("effect") or {}).get("kind") != "hypothesis_produced" or not c.get("next_test"):
            continue                      # nothing testable: research that settled or stopped
        if c.get("adopt") is False:
            continue                      # the research itself prevented the experiment
        cell = cell_for(decision_ref, d)
        if cell is None:
            skipped.append({"task": tid, "why": f"no cell owns decision {decision_ref!r}"})
            continue
        try:
            out = R.bridge(db, tid, cell=cell, proposed_by=RESEARCH_PROPOSER, now=now,
                           rollback_ref=(f"research:{tid}: nothing is applied until "
                                         f"improve.bounded.start records the change and its "
                                         f"undo"))
        except (R.ResearchRefused, cells.ImprovementRefused,
                governance.GovernanceRefused) as exc:
            skipped.append({"task": tid, "cell": cell, "why": str(exc)[:300]})
            continue
        bridged.append({"task": tid, "cell": cell, "improvement": out["improvement"]})
    if bridged:
        from ..agents.registry import Registry

        Registry(db).audit("improvement_department", INTAKE_ACTION,
                           detail={"bridged": bridged, "skipped": skipped[:20]})
    return {"bridged": bridged, "skipped": skipped, "read": len(tasks)}


# ---- F-705: the loop, per department, read off the registries -----------------------------

STAGES: tuple[str, ...] = ("observe", "detect", "hypothesis", "experiment", "measure",
                           "adversarial_validation", "promote_reject", "monitor")


def coverage() -> dict:
    """Which code runs each stage for each department's cell. Read, not claimed."""
    from . import measure, mine, monitor, runner

    items = []
    for c in cells.CELLS:
        # The bounded experiment judges any cell's change on that cell's own metric; the
        # other registered trials judge particular kinds of change wherever they arise.
        trials = [TRIAL] if runner.TRIALS.get(TRIAL) is trial else []
        stages = {
            "observe": f"{measure.__name__}.record_all ({c.measure})",
            "detect": f"{mine.__name__}.mine",
            "hypothesis": "improve.cells.propose (failure memory, governance)",
            "experiment": trials,
            "measure": f"{measure.__name__}.record_all -> {TRIAL} window",
            "adversarial_validation": f"{runner.__name__}.adversarial_test",
            "promote_reject": f"{runner.__name__}._promote_or_route (tier-gated)",
            "monitor": f"{monitor.__name__}.sweep / {runner.__name__}.monitor_trials",
        }
        items.append({"cell": c.key, "department": c.department, "stages": stages,
                      "kind_specific_trials": sorted(n for n in runner.TRIALS if n != TRIAL),
                      "complete": all(stages[s] for s in STAGES)})
    return {"stages": list(STAGES), "items": items,
            "complete": all(i["complete"] for i in items),
            "adversarial_note": ("adversarial validation is deterministic re-derivation, a "
                                 "governance re-check and a hidden-surface check by a role "
                                 "that never proposes; no model adversary is configured")}


def summary(db) -> dict:
    """Laura's provider for the experiment step. Never raises."""
    try:
        return _summary(db)
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNKNOWN", "as_of": None, "items": [],
                "reason": f"experiments unreadable: {type(exc).__name__}: {str(exc)[:160]}"}


def _summary(db) -> dict:
    from sqlalchemy import select

    from ..core.models import Improvement

    now = _now()
    items, stalled = [], []
    with db.session() as s:
        rows = [(r.id, r.cell, r.state, dict(r.evidence or {})) for r in s.scalars(
            select(Improvement).where(Improvement.state == cells.PROPOSED))]
    for iid, cell, _state, ev in rows:
        if not is_bounded(ev):
            continue
        win = _window(ev)
        entry = {"improvement": iid, "cell": cell, "max_days": max_days(ev),
                 "state": "not_started" if win is None else
                 "running" if now < win[1] else "window_closed"}
        if win is not None and now >= win[1]:
            n = len(_production_points(db, cell, after=win[0], until=win[1]))
            entry["readings"] = n
            if n < MIN_READINGS:
                stalled.append(entry)
        items.append(entry)
    status = "DEGRADED" if stalled else "OK"
    reason = (f"{len(stalled)} closed experiment window(s) lack {MIN_READINGS} production "
              f"readings of their cell; improve.measure has to read them" if stalled else
              f"{len(items)} bounded experiment(s) open; none waiting on a measurement")
    return {"status": status, "as_of": now.isoformat(), "reason": reason, "items": items,
            "basis": "improvements (PROPOSED, scope.max_days)"}
