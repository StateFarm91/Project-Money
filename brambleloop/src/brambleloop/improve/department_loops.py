"""Every department's improvement loop: KPI -> observations -> lessons -> consumer.

The owner's directive (2026-11-20): every department gets better with experience, and learning
is worthless unless it changes behaviour. This module states each department's loop as data
and then CHECKS it against the running system rather than trusting the declaration:

* **KPI** -- a rate measured from real rows. For every department it is the *useful yield* of
  the department's own jobs: finished runs that produced something (`orchestrate.made_progress`:
  work done, not a no-op or a deferral) over finished runs (DONE or DEAD). A credential-gated
  wait is excluded from both, because it measures the owner queue, not the department. An
  empty window is UNKNOWN, never zero.
* **Observation stream** -- the `jobs` rows of those job types (and, where the department has
  one, the policy-loop decisions in `learn_decisions`).
* **Lessons with evidence thresholds** -- `lessons` rows routed to (or originating in) the
  department's cells. A lesson counts as VERIFIED only at confidence >= `measured` with an
  evidence reference; APPLIED only when a consumer recorded acting on it (`bus.acted_on`).
* **Consumer** -- the code that changes behaviour because of a lesson. Each declared consumer
  is checked statically (its module's source must contain the call) and live (it must have
  acted on a lesson, or written a decision, in the window). A department with no consumer is
  a MISSING finding; a consumer that never fired is DORMANT. Neither is ever a pass, and each
  files an engineering change request (`improve.ecr`).
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import stats

WINDOW_DAYS = 30
TREND_RECENT_DAYS = 7
VERIFIED_CONFIDENCE = ("measured", "confirmed")


@dataclass(frozen=True)
class Consumer:
    kind: str          # "lesson" (consume.matching/act on a cell) | "policy_loop"
    module: str        # dotted module whose source must contain `token`
    token: str
    cell_or_loop: str
    how: str


@dataclass(frozen=True)
class Department:
    key: str
    name: str
    prefixes: tuple[str, ...]
    cells: tuple[str, ...]
    consumers: tuple[Consumer, ...]
    kpi: str = "useful yield of the department's finished jobs"


def _lc(module, token, cell, how):
    return Consumer("lesson", module, token, cell, how)


def _pl(module, token, loop, how):
    return Consumer("policy_loop", module, token, loop, how)


DEPARTMENTS: tuple[Department, ...] = (
    Department("research", "Research", ("radar.", "mjs.", "intel.", "research.", "culture."),
               ("market_radar",),
               (_lc("brambleloop.runtime.pipeline", 'consume.matching(db, "market_radar"',
                    "market_radar", "radar.score nudges a concept's score by matched lessons"),
                _lc("brambleloop.intel.watchlist", 'consume.matching(db, "market_radar"',
                    "market_radar", "watchlist opportunities checked against lessons"))),
    Department("concept_creative", "Concept & creative", ("creative.", "seasonal."),
               ("product_creativity", "portfolio"),
               (_lc("brambleloop.seasonal.daily", "consume.matching(db, SEASONAL_CELL",
                    "portfolio", "seasonal remerchandising shaped by matched lessons"),)),
    Department("engineering", "Pattern engineering", ("cir.",), ("pattern_engineering",),
               (_lc("brambleloop.runtime.pipeline", 'consume.matching(ctx.db, "pattern_engineering"',
                    "pattern_engineering", "engineering lessons attached to a CIR draft"),)),
    Department("qa", "QA / Product Truth", ("gate.", "physical."), ("quality",),
               (_pl("brambleloop.learn.improvement_status", "defect_watchlist(db)",
                    "pattern_defect_watch", "defect watch queues extra review of releases"),)),
    Department("visual", "Visual", ("assets.", "visual."), ("creative_assets",),
               (_pl("brambleloop.learn.improvement_status", "pl.visual_precheck(db)",
                    "visual_gate_precheck", "visual pre-check flags assets before the gate"),)),
    Department("seo_listing", "SEO & listing", ("listing.", "seo.", "store."), ("seo_search",),
               (_lc("brambleloop.runtime.release", 'consume.matching(ctx.db, "seo_search"',
                    "seo_search", "lesson-matched queries get a tag slot"),)),
    Department("pricing", "Pricing", ("pricing.",), ("pricing",), ()),
    Department("marketing", "Marketing", ("growth.", "marketing.", "ads."), ("growth",),
               (_lc("brambleloop.growth.content", "consume.matching(db, CONTENT_CELL",
                    "growth", "content pieces shaped by matched lessons"),)),
    Department("finance", "Finance", ("finance.", "commerce."), ("finance",),
               (_pl("brambleloop.learn.improvement_status", "pl.cost_watch(db)",
                    "release_cost_watch", "early cost-review flags (never moves a ceiling)"),)),
    Department("ops", "Ops / reliability", ("ops.", "swarm.", "autonomy."), ("runtime",), ()),
    Department("support", "Customer support", ("support.",), ("customer_experience",),
               (_lc("brambleloop.runtime.release", 'consume.matching(ctx.db, "customer_experience"',
                    "customer_experience", "lessons attached to open support cases"),)),
)
BY_KEY: dict[str, Department] = {d.key: d for d in DEPARTMENTS}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v):
    return None if v is None else (v if v.tzinfo else v.replace(tzinfo=timezone.utc))


def department_of(job_type: str) -> str | None:
    best = None
    for d in DEPARTMENTS:
        for p in d.prefixes:
            if job_type.startswith(p) and (best is None or len(p) > best[1]):
                best = (d.key, len(p))
    return best[0] if best else None


# ---- KPI --------------------------------------------------------------------------------

def kpi_counts(db, department: str, since: datetime, until: datetime) -> tuple[int, int]:
    """(useful, finished) for the department's jobs that finished in [since, until)."""
    from sqlalchemy import or_, select

    from ..core.models import Job, JobStatus
    from ..swarm.orchestrate import gated_noop, made_progress

    d = BY_KEY[department]
    useful = finished = 0
    with db.session() as s:
        q = (select(Job.status, Job.outputs, Job.finished_at)
             .where(Job.status.in_((JobStatus.DONE, JobStatus.DEAD)),
                    Job.finished_at >= since, Job.finished_at < until,
                    or_(*[Job.job_type.like(f"{p}%") for p in d.prefixes])))
        for status, outputs, fin in s.execute(q):
            at = _aware(fin)
            if at is None or not (since <= at < until):
                continue
            if status == JobStatus.DONE and gated_noop(outputs):
                continue
            finished += 1
            if status == JobStatus.DONE and made_progress(outputs):
                useful += 1
    return useful, finished


def kpi(db, department: str, *, now: datetime | None = None) -> dict:
    now = now or _now()
    recent_from = now - timedelta(days=TREND_RECENT_DAYS)
    prior_from = now - timedelta(days=WINDOW_DAYS)
    recent = kpi_counts(db, department, recent_from, now)
    prior = kpi_counts(db, department, prior_from, recent_from)
    x, n = recent[0] + prior[0], recent[1] + prior[1]
    return {"key": "useful_yield", "what": BY_KEY[department].kpi,
            "window_days": WINDOW_DAYS, "successes": x, "trials": n,
            "value": round(x / n, 4) if n else None,
            "state": "MEASURED" if n >= stats.TREND_MIN_N else "UNKNOWN",
            "trend": stats.trend(recent, prior),
            "source": "jobs (DONE/DEAD; made_progress; gated no-ops excluded)"}


# ---- lessons ----------------------------------------------------------------------------

def lessons(db, department: str, *, now: datetime | None = None) -> dict:
    from sqlalchemy import select

    from ..core.models import Lesson

    d = BY_KEY[department]
    cells = set(d.cells)
    since = (now or _now()) - timedelta(days=WINDOW_DAYS)
    learned = verified = applied = applied_window = 0
    examples = []
    with db.session() as s:
        for r in s.scalars(select(Lesson).where(Lesson.withdrawn_at.is_(None))
                           .order_by(Lesson.id.desc()).limit(5000)):
            if not (cells & set(r.routed_to or []) or r.origin_cell in cells):
                continue
            learned += 1
            ok = r.confidence in VERIFIED_CONFIDENCE and bool(r.evidence_ref)
            verified += ok
            acts = [e for e in (r.acted_on_by or []) if e.get("cell") in cells]
            if acts:
                applied += 1
                if any((_parse(e.get("at")) or since) >= since for e in acts):
                    applied_window += 1
            if len(examples) < 3:
                examples.append({"lesson": r.id, "subject": r.subject,
                                 "confidence": r.confidence, "applied": bool(acts)})
    return {"learned": learned, "verified": verified, "applied": applied,
            "applied_in_window": applied_window,
            "threshold": f"confidence in {list(VERIFIED_CONFIDENCE)} with an evidence_ref",
            "examples": examples}


def _parse(v):
    try:
        return _aware(datetime.fromisoformat(v)) if v else None
    except (TypeError, ValueError):
        return None


# ---- consumers --------------------------------------------------------------------------

def _source(module: str) -> str | None:
    try:
        spec = importlib.util.find_spec(module)
        if spec is None or not spec.origin:
            return None
        with open(spec.origin, encoding="utf-8") as fh:
            return fh.read()
    except (ImportError, OSError, ValueError):
        return None


def consumer_state(db, c: Consumer, *, now: datetime | None = None) -> dict:
    src = _source(c.module)
    static = bool(src and c.token in src)
    out = {"kind": c.kind, "module": c.module, "target": c.cell_or_loop, "how": c.how,
           "static_check": "PRESENT" if static else "ABSENT"}
    if not static:
        return {**out, "state": "MISSING", "fired": 0,
                "why": f"{c.module} no longer contains {c.token!r}"}
    since = (now or _now()) - timedelta(days=WINDOW_DAYS)
    fired = _fired(db, c, since)
    return {**out, "fired": fired, "state": "ACTIVE" if fired else "DORMANT",
            "why": None if fired else f"declared, but did not act in {WINDOW_DAYS} days"}


def _fired(db, c: Consumer, since: datetime) -> int:
    from sqlalchemy import func, select

    if c.kind == "policy_loop":
        from ..learn.models import LearnDecision

        with db.session() as s:
            return int(s.scalar(select(func.count()).select_from(LearnDecision)
                                .where(LearnDecision.loop == c.cell_or_loop,
                                       LearnDecision.at >= since)) or 0)
    from ..core.models import Lesson

    n = 0
    with db.session() as s:
        for acts in s.scalars(select(Lesson.acted_on_by).order_by(Lesson.id.desc())
                              .limit(5000)):
            for e in acts or []:
                if e.get("cell") == c.cell_or_loop and (_parse(e.get("at")) or since) >= since:
                    n += 1
    return n


def table(db, *, now: datetime | None = None) -> dict:
    """The department x KPI x lesson-consumer table, with its findings."""
    from . import tuning

    now = now or _now()
    rows, findings = [], []
    for d in DEPARTMENTS:
        cons = [consumer_state(db, c, now=now) for c in d.consumers]
        active = [c for c in cons if c["state"] == "ACTIVE"]
        tunables = [t for t in tuning.TUNABLES if t.department == d.key]
        if not cons:
            verdict, why = "FINDING", "no consumer: nothing changes behaviour from a lesson"
            findings.append({"department": d.key, "defect_class": "missing_consumer",
                             "why": why})
        elif not active:
            verdict = "FINDING"
            why = "consumer(s) declared but none acted on a lesson in the window"
            findings.append({"department": d.key, "defect_class": "dormant_consumer",
                             "why": why, "consumers": [c["module"] for c in cons]})
        else:
            verdict, why = "LOOP_CLOSED", None
        rows.append({"department": d.key, "name": d.name, "kpi": kpi(db, d.key, now=now),
                     "observations": {"jobs": list(d.prefixes)},
                     "lessons": lessons(db, d.key, now=now), "consumers": cons,
                     "tunables": [{"key": t.key, "reader_wired": bool(t.reader)}
                                  for t in tunables],
                     "verdict": verdict, "why": why})
    return {"as_of": now.isoformat(), "departments": rows, "findings": findings,
            "closed": sum(1 for r in rows if r["verdict"] == "LOOP_CLOSED"),
            "total": len(rows)}


def file_findings(db, tbl: dict) -> list[dict]:
    """One deduplicated change request per finding. Returns the filing results."""
    from . import ecr

    out = []
    for f in tbl["findings"]:
        d = BY_KEY[f["department"]]
        row = next(r for r in tbl["departments"] if r["department"] == d.key)
        k = row["kpi"]
        module = (",".join(sorted({c.module for c in d.consumers}))
                  or f"(none: no consumer reads {', '.join(d.cells)} lessons)")
        problem = (f"{d.name}: {f['why']}. Lessons routed to {list(d.cells)}: "
                   f"{row['lessons']['learned']} learned, {row['lessons']['verified']} "
                   f"verified, {row['lessons']['applied']} applied.")
        out.append(ecr.file(
            db, defect_class=f["defect_class"], department=d.key, module=module,
            title=f"{d.name}: {f['defect_class'].replace('_', ' ')}", problem=problem,
            evidence={"lessons": row["lessons"], "consumers": row["consumers"],
                      "kpi": {"successes": k["successes"], "trials": k["trials"],
                              "value": k["value"], "state": k["state"]},
                      "examples": row["lessons"]["examples"]},
            proposed_change=(
                f"Add a consumer that changes {d.name} behaviour from verified lessons on "
                f"{list(d.cells)} -- via consume.matching/consume.act or a declared tunable "
                f"read through improve.tuning.value -- and records acting on them."
                if f["defect_class"] == "missing_consumer" else
                f"Find why {module} did not act on routed lessons in {WINDOW_DAYS} days "
                f"(no matching lessons, a silent exception, or the call site unreachable) "
                f"and fix it."),
            acceptance_criteria=[
                f"department_loops.table reports {d.key} LOOP_CLOSED (a consumer ACTIVE)",
                "a test drives a verified lesson through the consumer and asserts the "
                "behaviour change and the bus.acted_on record",
                f"{d.key} useful-yield KPI does not regress after deploy (stats.compare)"],
            priority="P2", expected_kpi_gain={"kpi": f"{d.key}.useful_yield",
                                              "direction": "up", "min_gain": stats.MIN_EFFECT},
            kpi_baseline={"successes": k["successes"], "trials": k["trials"]}))
    return out
