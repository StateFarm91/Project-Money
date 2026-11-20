"""Engineering change requests: lessons that need code, filed as structured rows.

Production never edits or deploys code. When the self-improvement team finds a lesson only
code can act on -- a department with no consumer, a loop parked by the thrash breaker, a
recurring defect class, a missing capability -- it files an `EngineeringChangeRequest` row.
The integrator's routine reads open rows through the readback token endpoint
(`GET /api/readback/ecrs`, read-only) and launches builder sessions; review, certification
and deploy stay where they are.

**Dedupe.** A request is identified by `fingerprint(defect_class, department, module)`. Filing
the same problem again while a request is open adds evidence (occurrences, newest examples)
to that row instead of opening a second one. Requests that were closed before, or that touch
the same department and module, are listed in `related`.

**Lifecycle.** FILED -> BUILDING -> REVIEWED -> DEPLOYED -> VERIFIED, with REVIEWED ->
BUILDING (review sent it back) and DEPLOYED -> REOPENED -> BUILDING. A request is closed only
by `verify`, when the KPI it promised has measurably improved after the deploy
(`stats.compare` against the baseline captured when it was filed). A deploy whose KPI did
not improve once enough post-deploy runs exist is REOPENED with the new evidence. Every
transition is appended to `history` and audited.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from . import stats

ACTION = "improve.ecr"

FILED, BUILDING, REVIEWED, DEPLOYED = "FILED", "BUILDING", "REVIEWED", "DEPLOYED"
VERIFIED, REOPENED = "VERIFIED", "REOPENED"
OPEN_STATES = (FILED, BUILDING, REVIEWED, DEPLOYED, REOPENED)
TRANSITIONS: dict[str, tuple[str, ...]] = {
    FILED: (BUILDING,),
    REOPENED: (BUILDING,),
    BUILDING: (REVIEWED,),
    REVIEWED: (DEPLOYED, BUILDING),
    DEPLOYED: (),            # only `verify` moves a deployed request (VERIFIED or REOPENED)
    VERIFIED: (),
}
DEFECT_CLASSES = ("missing_consumer", "dormant_consumer", "failing_loop",
                  "recurring_defect", "missing_capability", "unwired_tunable")
PRIORITIES = ("P0", "P1", "P2", "P3")
MAX_EXAMPLES = 10
# A deploy is judged once this many post-deploy runs exist (the stats floor), and reopened
# if after VERIFY_MAX_DAYS the KPI still has not measurably improved.
VERIFY_MAX_DAYS = 21


class ECRRefused(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v):
    return None if v is None else (v if v.tzinfo else v.replace(tzinfo=timezone.utc))


def fingerprint(defect_class: str, department: str, module: str) -> str:
    raw = f"{defect_class.strip().lower()}|{department.strip().lower()}|{module.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _audit(db, ecr_id: int, entry: dict) -> None:
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="improve.ecr", action=ACTION, artifact=f"ecr:{ecr_id}",
                       detail={"ecr": ecr_id, **entry}))


def _log(row, event: str, **evidence) -> dict:
    entry = {"at": _now().isoformat(), "event": event, **evidence}
    row.history = list(row.history or []) + [entry]
    row.updated_at = _now()
    return entry


def file(db, *, defect_class: str, department: str, module: str, title: str, problem: str,
         evidence: dict, proposed_change: str, acceptance_criteria: list[str],
         priority: str = "P2", expected_kpi_gain: dict | None = None,
         kpi_baseline: dict | None = None, filed_by: str = "improve.self_tune") -> dict:
    """File (or merge into) a request. Returns {"id", "created", "related"}."""
    from sqlalchemy import or_, select

    from .self_models import EngineeringChangeRequest as E

    if defect_class not in DEFECT_CLASSES:
        raise ECRRefused(f"unknown defect class {defect_class!r}")
    if priority not in PRIORITIES:
        raise ECRRefused(f"unknown priority {priority!r}")
    if not isinstance(evidence, dict) or not evidence:
        raise ECRRefused("a change request without evidence is an opinion, not a request")
    if not acceptance_criteria:
        raise ECRRefused("a change request names how its fix will be accepted")
    fp = fingerprint(defect_class, department, module)
    examples = list(evidence.get("examples") or [])
    with db.session() as s:
        open_row = s.scalar(select(E).where(E.fingerprint == fp, E.state.in_(OPEN_STATES))
                            .order_by(E.id.desc()).limit(1))
        if open_row is not None:
            ev = dict(open_row.evidence or {})
            merged = (list(ev.get("examples") or []) + [x for x in examples
                                                        if x not in (ev.get("examples") or [])])
            ev.update({k: v for k, v in evidence.items() if k != "examples"})
            ev["examples"] = merged[-MAX_EXAMPLES:]
            open_row.evidence = ev
            open_row.occurrences = (open_row.occurrences or 1) + 1
            if PRIORITIES.index(priority) < PRIORITIES.index(open_row.priority):
                open_row.priority = priority
            entry = _log(open_row, "evidence_added", occurrences=open_row.occurrences)
            rid, related = open_row.id, list(open_row.related or [])
            created = False
        else:
            related = sorted(set(s.scalars(select(E.id).where(or_(
                E.fingerprint == fp, (E.department == department) & (E.module == module))))))
            row = E(fingerprint=fp, defect_class=defect_class, department=department,
                    module=module, title=title[:200], problem=problem,
                    evidence={**evidence, "examples": examples[-MAX_EXAMPLES:]},
                    proposed_change=proposed_change,
                    acceptance_criteria=list(acceptance_criteria), priority=priority,
                    expected_kpi_gain=dict(expected_kpi_gain or {}), related=related,
                    state=FILED, occurrences=1, filed_by=filed_by,
                    kpi_baseline=dict(kpi_baseline or {}), history=[])
            s.add(row)
            s.flush()
            entry = _log(row, "filed", priority=priority, related=related)
            rid, created = row.id, True
    _audit(db, rid, entry)
    return {"id": rid, "created": created, "related": related}


def advance(db, ecr_id: int, to_state: str, *, by: str, note: str = "",
            commit: str = "") -> dict:
    """Move a request along its lifecycle. DEPLOYED needs the deployed commit."""
    from .self_models import EngineeringChangeRequest as E

    with db.session() as s:
        row = s.get(E, ecr_id)
        if row is None:
            raise ECRRefused(f"no change request {ecr_id}")
        if to_state not in TRANSITIONS.get(row.state, ()):
            raise ECRRefused(f"{row.state} -> {to_state} is not a lifecycle step"
                             + (" (only verify moves a deployed request)"
                                if row.state == DEPLOYED else ""))
        if to_state == DEPLOYED:
            if not commit:
                raise ECRRefused("a deploy names the commit that shipped the fix")
            row.deployed_commit, row.deployed_at = commit[:64], _now()
        frm = row.state
        row.state = to_state
        entry = _log(row, f"{frm}->{to_state}", by=by, note=note, commit=commit or None)
    _audit(db, ecr_id, entry)
    return {"id": ecr_id, "state": to_state}


def verify(db, ecr_id: int, *, measure, now: datetime | None = None) -> dict:
    """Judge a DEPLOYED request on its KPI. `measure(since, until)` -> (successes, trials).

    VERIFIED (closed) when post-deploy runs beat the filed baseline (stats.compare BETTER);
    REOPENED with the new evidence when they are worse, or when VERIFY_MAX_DAYS passed with
    enough runs and no measurable gain; otherwise it stays DEPLOYED (UNKNOWN: too few runs).
    """
    from .self_models import EngineeringChangeRequest as E

    now = now or _now()
    with db.session() as s:
        row = s.get(E, ecr_id)
        if row is None or row.state != DEPLOYED:
            return {"id": ecr_id, "verdict": "not_deployed",
                    "state": None if row is None else row.state}
        base = row.kpi_baseline or {}
        deployed_at = _aware(row.deployed_at)
    if not base.get("trials"):
        old = measure(deployed_at - timedelta(days=30), deployed_at)
    else:
        old = (int(base["successes"]), int(base["trials"]))
    new = measure(deployed_at, now)
    cmp = stats.compare(new, old, min_n=stats.TREND_MIN_N)
    aged = (now - deployed_at) >= timedelta(days=VERIFY_MAX_DAYS)
    if cmp["verdict"] == "BETTER":
        to, event = VERIFIED, "kpi_verified"
    elif cmp["verdict"] == "WORSE" or (aged and cmp["verdict"] != "UNKNOWN"):
        to, event = REOPENED, "kpi_not_verified"
    else:
        return {"id": ecr_id, "verdict": "UNKNOWN" if cmp["verdict"] == "UNKNOWN" else "wait",
                "comparison": cmp}
    with db.session() as s:
        row = s.get(E, ecr_id)
        row.state = to
        ev = dict(row.evidence or {})
        ev.setdefault("verifications", []).append({"at": now.isoformat(), "comparison": cmp,
                                                   "commit": row.deployed_commit})
        row.evidence = ev
        entry = _log(row, event, comparison=cmp, commit=row.deployed_commit)
    _audit(db, ecr_id, entry)
    return {"id": ecr_id, "verdict": to, "comparison": cmp}


def _row(r) -> dict:
    return {"id": r.id, "filed_at": _aware(r.at).isoformat(), "state": r.state,
            "defect_class": r.defect_class, "department": r.department, "module": r.module,
            "title": r.title, "problem": r.problem, "evidence": r.evidence,
            "proposed_change": r.proposed_change,
            "acceptance_criteria": r.acceptance_criteria, "priority": r.priority,
            "expected_kpi_gain": r.expected_kpi_gain, "related": r.related,
            "occurrences": r.occurrences, "kpi_baseline": r.kpi_baseline,
            "deployed_commit": r.deployed_commit or None,
            "updated_at": _aware(r.updated_at).isoformat() if r.updated_at else None,
            "history": (r.history or [])[-10:]}


def listing(db, *, open_only: bool = True, department: str | None = None,
            limit: int = 200) -> list[dict]:
    from sqlalchemy import select

    from .self_models import EngineeringChangeRequest as E

    with db.session() as s:
        q = select(E).order_by(E.priority, E.id).limit(limit)
        if open_only:
            q = q.where(E.state.in_(OPEN_STATES))
        if department:
            q = q.where(E.department == department)
        return [_row(r) for r in s.scalars(q)]


def summary(db) -> dict:
    """Counts per department and state: open, shipped (deployed), verified."""
    from sqlalchemy import func, select

    from .self_models import EngineeringChangeRequest as E

    out: dict[str, dict] = {}
    with db.session() as s:
        for dept, state, n in s.execute(select(E.department, E.state, func.count(E.id))
                                        .group_by(E.department, E.state)):
            d = out.setdefault(dept, {"open": 0, "shipped": 0, "verified": 0, "reopened": 0})
            if state == VERIFIED:
                d["verified"] += n
            elif state == DEPLOYED:
                d["shipped"] += n
                d["open"] += n
            else:
                d["open"] += n
                if state == REOPENED:
                    d["reopened"] += n
    return out


def _counts_only(value, depth: int = 0):
    """Numbers, booleans, short identifiers and nested counts; never free text."""
    if isinstance(value, bool) or isinstance(value, (int, float)) or value is None:
        return value
    if isinstance(value, dict) and depth < 3:
        return {k: _counts_only(v, depth + 1) for k, v in value.items()
                if k not in ("subject", "statement", "why", "how", "detail", "note")}
    if isinstance(value, list) and depth < 3:
        return [_counts_only(v, depth + 1) for v in value[:MAX_EXAMPLES]]
    if isinstance(value, str) and len(value) <= 80 and "\n" not in value:
        return value
    return "<omitted>"


def readback(db) -> dict:
    """The projection `GET /api/readback/ecrs` serves: open requests, newest evidence counts."""
    rows = []
    for r in listing(db, open_only=True):
        rows.append({k: r[k] for k in ("id", "filed_at", "state", "defect_class",
                                       "department", "module", "title", "problem",
                                       "proposed_change", "acceptance_criteria",
                                       "priority", "expected_kpi_gain", "related",
                                       "occurrences", "kpi_baseline", "deployed_commit",
                                       "updated_at")}
                    | {"evidence": _counts_only(r["evidence"]),
                       "history": [{"at": h.get("at"), "event": h.get("event")}
                                   for h in r["history"]]})
    return {"schema": "brambleloop.ecr.readback.v1", "generated_at": _now().isoformat(),
            "open": len(rows), "lifecycle": list(TRANSITIONS), "requests": rows,
            "note": "read-only; production never edits or deploys code. Close = KPI "
                    "verified after deploy (improve.ecr.verify)."}
