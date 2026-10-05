"""Elastic specialist capacity, and the rules that stop it becoming a crowd.

Requirements 34, 174, 175, 176, 186, 187, 192, 302. The spec is explicit that agent count is
not to be artificially small — dozens or hundreds of logical specialists are allowed when
parallel specialisation improves quality or latency. What it is equally explicit about is the
other direction: redundant or consistently weak agents are merged or retired, because a swarm
that only grows is a cost centre wearing an org chart.

Four rules hold the middle.

**Work decides headcount, not ambition (#175).** Fan-out is computed from queue depth,
deadline pressure and the value of what is waiting. A fixed pool is wrong in both directions —
idle during a catalogue baseline, and expensively awake during a quiet Tuesday.

**No work is unowned (#176).** Every material task has an accountable cell and an explicit
state. Orphan detection is not a report somebody runs; it is a query with a name, because work
that nobody owns is not noticed by anybody — that is what being unowned means.

**Idle is a backlog, not a slogan (#186).** An agent with nothing urgent does not spin to
satisfy a 24/7 claim, and it does not stop either. It takes the highest-value thing from a
standing backlog, and the backlog is ordered by what the business actually needs next.

**Three identical observations is a stop, not a fourth (#34).** A loop that keeps making the
same call and getting the same answer has stopped working and started spending. Detection is
mechanical: identical call plus identical result, three times, opens the circuit and forces a
re-plan.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Priority bands (#187). Lower number wins. The ordering is a commercial argument, not a
# preference: a truth defect in a live product costs trust that cannot be re-earned, and a
# seasonal window that closes cannot be reopened at any price.
BANDS: tuple[tuple[int, str, str], ...] = (
    (10, "customer_incident", "a customer is affected right now"),
    (15, "truth_defect", "a published claim is not true"),
    (25, "seasonal_deadline", "a window closes and cannot be reopened"),
    (40, "proven_winner", "known demand, known economics"),
    (55, "benchmark_change", "the named benchmark moved"),
    (70, "new_opportunity", "unproven, possibly valuable"),
    (85, "exploration", "learning with no committed value"),
    (95, "housekeeping", "keeps the system honest, urgent to nobody"),
)

BAND_BY_KIND: dict[str, int] = {kind: p for p, kind, _ in BANDS}

# How many specialists one unit of waiting work justifies. Fan-out is bounded by spend rather
# than by a headcount constant: the ceiling that matters is money, and a number in the code is
# the "artificial scarcity" #174 objects to.
WORK_PER_SPECIALIST = 8
MIN_SPECIALISTS = 1

# Three identical observations (#34).
THRASH_LIMIT = 3


class SwarmRefused(ValueError):
    """Work that cannot be scheduled, or a fan-out that cannot be afforded."""


@dataclass(frozen=True)
class WorkItem:
    key: str
    kind: str
    owner: str = ""
    state: str = "open"
    value_cad: float = 0.0
    deadline_days: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in BAND_BY_KIND:
            raise SwarmRefused(
                f"{self.key}: {self.kind!r} has no priority band. Unbanded work is scheduled "
                f"by whoever wrote the enqueue call, which is how housekeeping outranks a "
                f"customer incident")

    @property
    def band(self) -> int:
        return BAND_BY_KIND[self.kind]

    def priority(self) -> float:
        """Band first, then deadline pressure, then value. Band is never traded away.

        A high-value opportunity does not outrank a customer incident however large it is,
        because the ordering between bands is a commercial argument the scheduler does not
        get to re-open.
        """
        urgency = 0.0
        if self.deadline_days is not None:
            urgency = max(0.0, 1.0 - min(self.deadline_days, 90) / 90.0)
        # Value contributes within a band only, scaled to stay below one band step.
        value = min(1.0, self.value_cad / 5000.0)
        return self.band - (urgency * 4.0) - (value * 3.0)

    def to_dict(self) -> dict:
        return {"key": self.key, "kind": self.kind, "owner": self.owner,
                "state": self.state, "band": self.band,
                "priority": round(self.priority(), 3),
                "value_cad": self.value_cad, "deadline_days": self.deadline_days}


def schedule(items: list[WorkItem]) -> list[WorkItem]:
    """Order the backlog. Stable within equal priority, so it does not shuffle each tick."""
    return sorted(items, key=lambda w: (w.priority(), w.key))


def orphans(items: list[WorkItem]) -> list[dict]:
    """Work with no accountable cell (#176).

    A query with a name rather than a report somebody remembers to run, because unowned work
    is precisely the work nobody is watching — that is what unowned means.
    """
    return [w.to_dict() for w in items
            if not w.owner and w.state not in ("done", "abandoned")]


def fan_out(*, open_work: int, budget_remaining_cad: float,
            cost_per_specialist_cad: float = 0.05,
            deadline_pressure: bool = False) -> dict:
    """How many specialists the waiting work justifies, bounded by money rather than a number.

    #174 objects to artificial scarcity and #188 requires central budget control, and those
    are the same requirement seen twice: the ceiling should be the real constraint, not a
    constant somebody picked.
    """
    if cost_per_specialist_cad <= 0:
        raise SwarmRefused("a specialist with no cost makes the budget ceiling meaningless")

    wanted = max(MIN_SPECIALISTS, -(-open_work // WORK_PER_SPECIALIST))
    if deadline_pressure:
        wanted = int(wanted * 1.5) or 1
    affordable = int(budget_remaining_cad / cost_per_specialist_cad)
    granted = max(0, min(wanted, affordable))

    return {
        "open_work": open_work,
        "wanted": wanted,
        "affordable": affordable,
        "granted": granted,
        "bounded_by": ("budget" if affordable < wanted else "work"),
        "note": ("Fan-out is bounded by spend rather than by a headcount constant: the "
                 "ceiling that matters is money, and a number in the code is the artificial "
                 "scarcity #174 objects to."),
    }


# ---------------------------------------------------------------------------
# Work-conserving autonomy (#186)

# The standing backlog an agent falls back to. Ordered by what the business needs next rather
# than by what is pleasant, and every entry is genuinely useful work rather than a way to look
# busy.
STANDING_BACKLOG: tuple[tuple[str, str], ...] = (
    ("benchmark_change", "check the named benchmark for changes"),
    ("new_opportunity", "score an uncovered arena in the coverage gap queue"),
    ("exploration", "run a concept tournament for the thinnest seasonal department"),
    ("housekeeping", "re-verify the continuity restore proof"),
    ("housekeeping", "recompute seasonal launch dates against today"),
    ("exploration", "mine recent failures for an improvement hypothesis"),
    ("housekeeping", "refresh the Build-2 coverage map from the registry"),
)


def next_work(urgent: list[WorkItem]) -> dict:
    """What to do now. Never nothing, and never spinning.

    An idle agent that polls to satisfy a 24/7 claim spends money to produce a heartbeat. An
    idle agent that stops is a 24/7 claim that is false. The third option is a backlog.
    """
    if urgent:
        chosen = schedule(urgent)[0]
        return {"source": "queue", "work": chosen.to_dict(),
                "why": f"highest priority open work, band {chosen.band}"}
    kind, description = STANDING_BACKLOG[0]
    return {
        "source": "standing_backlog",
        "work": {"kind": kind, "description": description,
                 "band": BAND_BY_KIND[kind]},
        "why": ("no urgent work; taking the highest-value standing item rather than polling "
                "to look alive or idling to look thrifty (#186)"),
        "backlog": [{"kind": k, "description": d} for k, d in STANDING_BACKLOG],
    }


# ---------------------------------------------------------------------------
# Thrash detection (#34)


@dataclass
class ThrashDetector:
    """Three identical observations is a stop, not a fourth.

    An agent repeating a call and getting the same answer has stopped working and started
    spending. The check is on call *and* result: a poll whose answer keeps changing is
    progress, and a poll whose answer never does is a loop.
    """

    limit: int = THRASH_LIMIT
    seen: dict[str, int] = field(default_factory=dict)
    tripped: set = field(default_factory=set)

    @staticmethod
    def signature(call: str, result) -> str:
        blob = json.dumps({"call": call, "result": result}, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]

    def observe(self, call: str, result) -> dict:
        key = self.signature(call, result)
        self.seen[key] = self.seen.get(key, 0) + 1
        count = self.seen[key]
        if count >= self.limit:
            self.tripped.add(key)
            return {
                "continue": False, "observations": count, "signature": key,
                "action": "replan",
                "why": (f"{count} identical observations of {call!r} with an identical "
                        f"result. The loop has stopped working and started spending; "
                        f"re-plan rather than poll again (#34)"),
            }
        return {"continue": True, "observations": count, "signature": key}

    def reset(self, call: str, result) -> None:
        self.seen.pop(self.signature(call, result), None)


# How far back the runtime sweep reads, and the statuses it reads. A dead job repeating the
# same error, or a paid job returning the same output, is a loop; a free job answering the
# same way every hour is a heartbeat, and the sweep leaves it alone.
THRASH_WINDOW_HOURS = 72
THRASH_SIGNATURE_PREFIX = "thrash:"


def _thrash_call(job) -> str:
    return json.dumps({"job_type": job.job_type, "inputs": job.inputs or {}},
                      sort_keys=True, default=str)


def thrash_sweep(db, *, now: datetime | None = None,
                 window_hours: int = THRASH_WINDOW_HOURS) -> dict:
    """Run `ThrashDetector` over recent job history and break the loops it finds (#34).

    The observation is (job type + inputs, result), where the result is the final error of a
    dead job (retries exhausted) and the outputs of a job that spent money. A job still
    retrying is not yet an observation: waiting for something, like a bundle waiting for its
    members, is not a loop until the retries run out. Three identical
    observations trip the breaker: an incident is opened (or restated) under a stable
    signature, and any retry of that same call still waiting in the queue is cancelled, so
    the loop stops spending rather than being reported while it continues. A free job whose
    answer never changes is not observed at all -- that is a heartbeat, not a loop.
    """
    from sqlalchemy import and_, or_, select

    from ..core.models import Incident, Job, JobStatus

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=window_hours)
    detector = ThrashDetector()
    tripped: dict[str, dict] = {}
    observed = 0
    with db.session() as s:
        jobs = list(s.scalars(select(Job).where(or_(
            Job.status == JobStatus.DEAD,
            and_(Job.status == JobStatus.DONE, Job.cost_cad > 0))).order_by(Job.id)))
        for job in jobs:
            created = job.created_at if job.created_at.tzinfo else \
                job.created_at.replace(tzinfo=timezone.utc)
            if created < since:
                continue
            if job.status == JobStatus.DEAD:
                result = {"error": (job.last_error or "")[:500]}
            elif job.status == JobStatus.DONE and float(job.cost_cad or 0.0) > 0:
                result = {"outputs": job.outputs}
            else:
                continue
            observed += 1
            call = _thrash_call(job)
            verdict = detector.observe(call, result)
            if not verdict["continue"]:
                entry = tripped.setdefault(verdict["signature"], {
                    "signature": verdict["signature"], "job_type": job.job_type,
                    "inputs": job.inputs or {}, "result": result, "job_ids": [],
                    "why": verdict["why"]})
                entry["job_ids"].append(job.id)

        cancelled: list[int] = []
        incidents: list[str] = []
        for sig, entry in tripped.items():
            call = json.dumps({"job_type": entry["job_type"], "inputs": entry["inputs"]},
                              sort_keys=True, default=str)
            for job in s.scalars(select(Job).where(Job.job_type == entry["job_type"],
                                                   Job.status == JobStatus.FAILED)):
                if _thrash_call(job) == call:
                    job.status = JobStatus.CANCELLED
                    job.last_error = ((job.last_error or "")
                                      + " | cancelled by the thrash breaker (#34): three "
                                        "identical observations; re-plan before retrying")[:4000]
                    cancelled.append(job.id)
            signature = f"{THRASH_SIGNATURE_PREFIX}{entry['job_type']}:{sig}"[:200]
            row = s.scalar(select(Incident).where(Incident.signature == signature,
                                                  Incident.resolved == False))  # noqa: E712
            summary = (f"{entry['job_type']} repeated an identical call with an identical "
                       f"result {len(entry['job_ids']) + 2} times in {window_hours}h. The "
                       f"loop has stopped working and started spending; its queued retries "
                       f"were cancelled and it needs a changed hypothesis before it runs "
                       f"again (#34).")
            # C-68/#34: a tripped loop is *suspended*, not only reported. The scheduler will
            # not re-enqueue this job type while the suspension stands, and it stands until
            # the hypothesis changes -- which, for a deployed system, is a different build
            # (the root-cause fix) -- so the next cadence window cannot restart the loop.
            suspension = {"kind": SUSPENDED, "job_type": entry["job_type"],
                          "code_commit": _commit(), "since": now.isoformat(),
                          "handler_digest": handler_digest(entry["job_type"])}
            if row is None:
                s.add(Incident(severity="P2", signature=signature, summary=summary,
                               detail={"job_type": entry["job_type"],
                                       "inputs": entry["inputs"], "result": entry["result"],
                                       "job_ids": entry["job_ids"][-20:],
                                       "suspension": suspension}))
            else:
                row.report_count = (row.report_count or 1) + 1
                row.summary = summary
                row.detail = {**dict(row.detail or {}), "suspension": suspension}
            incidents.append(signature)

        progress = _progress(s, since=since)
        backoffs = _free_poll_backoff(s, progress, now=now,
                                      skip={e["job_type"] for e in tripped.values()})
    return {"observed": observed, "window_hours": window_hours,
            "tripped": len(tripped), "incidents": incidents, "cancelled": cancelled,
            "limit": THRASH_LIMIT,
            "progress": progress, "backoff": backoffs,
            "suspended": sorted(suspended_job_types(db, now=now)),
            "note": ("no loop: no failing or paid call repeated an identical result three "
                     "times" if not tripped else
                     f"{len(tripped)} loop(s) broken: incidents raised and queued retries "
                     f"cancelled")}


# ---------------------------------------------------------------------------
# #34 (C-68): progress per iteration and per dollar, backoff for unchanged polling, and
# suspension until the hypothesis changes.

SUSPENDED = "suspended"
BACKOFF = "backoff"
BACKOFF_SIGNATURE_PREFIX = "thrash:backoff:"
# Three identical states without progress is the requirement's own number.
IDENTICAL_STATES = THRASH_LIMIT
# Backoff doubles per unchanged sweep, capped: a poll slowed to a week is a poll abandoned.
MAX_BACKOFF_FACTOR = 32
# Watchdogs whose whole job is to keep looking: liveness, the queue, the allocator, the
# sweeps themselves. Backing these off would blind the system to the change they exist to
# notice, and they cost nothing.
LIVENESS_JOB_TYPES: frozenset[str] = frozenset({
    "ops.heartbeat", "ops.health", "ops.queue_check", "ops.thrash", "build.tick",
    "swarm.allocate", "swarm.orphans", "swarm.backlog", "swarm.review", "ops.sentinel",
    "finance.governor", "finance.escalation_check", "ops.retention", "support.triage",
})
_VOLATILE_KEYS = ("at", "as_of", "now", "ran_at", "generated_at", "checked_at", "timestamp",
                  "allocation_id", "reading_id", "job_id", "audit_id", "id")


def _commit() -> str:
    from ..core.build import commit

    return commit()


def handler_digest(job_type: str) -> str | None:
    """A digest of the source of the module that handles `job_type` (C-85, Codex P08).

    "A new build" lifted every suspension: any deploy -- a copy change in a listing template
    -- released a loop tripped in the radar. A changed hypothesis for a tripped loop is a
    change to the code that runs it, so the suspension records the handler module's source
    digest and lifts only when THAT changes (or a person resolves the incident). None when
    the handler cannot be located, in which case the build commit is the fallback."""
    import hashlib
    import inspect
    import sys

    try:
        from ..runtime.worker import handlers

        fn = handlers.get(job_type)
        if fn is None:
            return None
        mod = sys.modules.get(getattr(fn, "__module__", "") or "")
        path = inspect.getsourcefile(mod) if mod is not None else None
        if not path:
            return None
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()[:16]
    except Exception:  # noqa: BLE001 - an unreadable handler is no evidence of a change
        return None


def _hypothesis_changed(suspension: dict) -> bool:
    """Whether the code the suspended loop runs has changed since it was suspended."""
    recorded = suspension.get("handler_digest")
    if recorded:
        current = handler_digest(suspension.get("job_type") or "")
        return bool(current) and current != recorded
    # A suspension written before digests were recorded: the build commit is all there is.
    return bool(suspension.get("code_commit")) and suspension["code_commit"] != _commit()


def _state_of(outputs) -> str:
    """A job's result with its clocks and row ids removed: what state did it observe?"""
    def strip(v):
        if isinstance(v, dict):
            return {k: strip(x) for k, x in sorted(v.items())
                    if k not in _VOLATILE_KEYS and not k.endswith("_at")}
        if isinstance(v, list):
            return [strip(x) for x in v]
        return v
    blob = json.dumps(strip(outputs or {}), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _progress(session, *, since: datetime) -> dict:
    """Per job type over the window: iterations, dollars, distinct states and the ratios."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    by: dict[str, dict] = {}
    # Bounded in SQL (C-80 defect 17): this runs hourly and the DONE table grows by the day.
    for job in session.scalars(select(Job).where(Job.status == JobStatus.DONE,
                                                 Job.finished_at >= since)
                               .order_by(Job.id)):
        finished = job.finished_at
        if finished is None or _aware(finished) < since:
            continue
        row = by.setdefault(job.job_type, {"iterations": 0, "cost_cad": 0.0, "states": [],
                                           "cadence": bool((job.inputs or {}).get("cadence")),
                                           "last_job_id": None})
        row["iterations"] += 1
        row["cost_cad"] += float(job.cost_cad or 0.0)
        row["states"].append(_state_of(job.outputs))
        row["last_job_id"] = job.id
    out = {}
    for jt, row in by.items():
        states = row["states"]
        changes = sum(1 for a, b in zip(states, states[1:]) if a != b)
        tail = states[-IDENTICAL_STATES:]
        out[jt] = {
            "iterations": row["iterations"], "cost_cad": round(row["cost_cad"], 6),
            "state_changes": changes,
            "progress_per_iteration": round(changes / row["iterations"], 4),
            "progress_per_dollar": (round(changes / row["cost_cad"], 4)
                                    if row["cost_cad"] > 0 else None),
            "identical_tail": (len(tail) == IDENTICAL_STATES and len(set(tail)) == 1),
            "cadence": row["cadence"],
            # The newest observation counted: a backoff level rises only when a *new*
            # unchanged observation appears, never on a sweep that saw nothing new.
            "last_job_id": row["last_job_id"],
        }
    return out


def _free_poll_backoff(session, progress: dict, *, now: datetime,
                       skip: set[str] | frozenset = frozenset()) -> dict:
    """Unchanged polling backs off exponentially; progress lifts the backoff (#34)."""
    from sqlalchemy import select

    from ..core.models import Incident
    from ..runtime.worker import CADENCES

    period_of = {jt: period for _n, _a, jt, period in CADENCES}
    applied, lifted = [], []
    for jt, row in sorted(progress.items()):
        if jt in LIVENESS_JOB_TYPES or jt in skip or jt not in period_of \
                or not row["cadence"]:
            continue
        signature = f"{BACKOFF_SIGNATURE_PREFIX}{jt}"
        open_row = session.scalar(select(Incident).where(Incident.signature == signature,
                                                         Incident.resolved.is_(False)))
        if not row["identical_tail"]:
            if open_row is not None:
                open_row.resolved = True
                lifted.append(jt)
            continue
        previous = ((open_row.detail or {}).get("suspension") or {}) if open_row else {}
        last_counted = previous.get("last_counted_job_id")
        if open_row is not None and last_counted is not None \
                and row.get("last_job_id") == last_counted:
            # C-80 defect 5 (Codex P07): the same tail seen again is not a new observation.
            # The level and the absolute deadline stand exactly as they were; the sweep
            # only restates that the backoff is still in force.
            applied.append({"job_type": jt, "factor": previous.get("factor"),
                            "until": previous.get("suspend_until"), "unchanged": True,
                            "level": previous.get("level")})
            continue
        level = int(previous.get("level", 0)) + 1 if open_row is not None else 1
        factor = min(MAX_BACKOFF_FACTOR, 2 ** level)
        until = now + timedelta(seconds=period_of[jt] * factor)
        if previous.get("suspend_until"):
            # a new unchanged observation extends the deadline; it never pulls it earlier
            until = max(until, datetime.fromisoformat(previous["suspend_until"]))
        suspension = {"kind": BACKOFF, "job_type": jt, "level": level, "factor": factor,
                      "suspend_until": until.isoformat(), "code_commit": _commit(),
                      "last_counted_job_id": row.get("last_job_id")}
        summary = (f"{jt} observed {IDENTICAL_STATES} identical states in a row without "
                   f"progress; polling backs off to every {factor}x its period (#34)")
        if open_row is None:
            session.add(Incident(severity="P3", signature=signature, summary=summary,
                                 halts_publication=False,
                                 detail={"suspension": suspension, "progress": row}))
        else:
            open_row.detail = {**dict(open_row.detail or {}), "suspension": suspension,
                               "progress": row}
            open_row.summary = summary
            open_row.report_count = (open_row.report_count or 1) + 1
        applied.append({"job_type": jt, "factor": factor, "until": until.isoformat(),
                        "unchanged": False, "level": level})
    return {"applied": applied, "lifted": lifted}


def suspended_job_types(db, *, now: datetime | None = None) -> dict[str, dict]:
    """Job types the scheduler must not enqueue now, with the reason (#34).

    A paid loop tripped by the breaker stays suspended until the code that runs it changes
    (a changed hypothesis, C-85: any new build no longer counts) or somebody resolves the
    incident;
    an unchanged poll is suspended until its backoff expires."""
    from sqlalchemy import select

    from ..core.models import Incident

    now = now or datetime.now(timezone.utc)
    commit = _commit()
    out: dict[str, dict] = {}
    with db.session() as s:
        for inc in s.scalars(select(Incident).where(
                Incident.resolved.is_(False),
                Incident.signature.like(f"{THRASH_SIGNATURE_PREFIX}%"))):
            sus = (inc.detail or {}).get("suspension") or {}
            jt = sus.get("job_type")
            if not jt:
                continue
            if sus.get("kind") == SUSPENDED:
                if _hypothesis_changed(sus):
                    continue          # the handler's own code changed: a changed hypothesis
                out[jt] = {"kind": SUSPENDED, "incident": inc.signature,
                           "why": "a loop spending without progress; waits for a changed "
                                  "hypothesis (a change to the code that runs it) or a "
                                  "resolved incident"}
            elif sus.get("kind") == BACKOFF:
                until = datetime.fromisoformat(sus["suspend_until"])
                if until > now:
                    out[jt] = {"kind": BACKOFF, "until": sus["suspend_until"],
                               "factor": sus.get("factor"), "incident": inc.signature}
    return out


def retry_allowed(db, job) -> dict:
    """A retry of a call the breaker tripped needs a changed hypothesis (#34).

    Deployment retries included: re-driving the same call under the same build is the same
    hypothesis, and the answer will be the same. Allowed once the running build differs from
    the one the loop was caught under, or the incident has been resolved by somebody."""
    from sqlalchemy import select

    from ..core.models import Incident

    call = _thrash_call(job)
    with db.session() as s:
        for inc in s.scalars(select(Incident).where(
                Incident.resolved.is_(False),
                Incident.signature.like(f"{THRASH_SIGNATURE_PREFIX}{job.job_type}:%"))):
            detail = inc.detail or {}
            same = json.dumps({"job_type": detail.get("job_type"),
                               "inputs": detail.get("inputs") or {}},
                              sort_keys=True, default=str) == call
            sus = detail.get("suspension") or {}
            if same and not _hypothesis_changed(sus):
                return {"allowed": False, "incident": inc.signature,
                        "why": ("this exact call tripped the thrash breaker under this build; "
                                "a retry needs a changed hypothesis -- a change to the code "
                                "that runs it, or the incident resolved (#34)")}
    return {"allowed": True}


# ---------------------------------------------------------------------------
# Retirement and merge (#192)

# A cell producing nothing over this many days with no successes is a candidate.
IDLE_DAYS_BEFORE_REVIEW = 21


def retirement_review(cells: list[dict], *, now: datetime | None = None) -> dict:
    """Which specialists should be merged or retired, and what must be kept first.

    The knowledge is the point. Retiring a cell that learned something and discarding what it
    learned costs more than the cell did, so every recommendation carries what to preserve.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=IDLE_DAYS_BEFORE_REVIEW)

    retire, merge, keep = [], [], []
    by_scope: dict[str, list[dict]] = {}
    for cell in cells:
        by_scope.setdefault(cell.get("scope", ""), []).append(cell)

    for cell in cells:
        last = cell.get("last_success_at")
        last_dt = (datetime.fromisoformat(last) if isinstance(last, str) else last)
        if last_dt is not None and last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        idle = last_dt is None or last_dt < cutoff
        duplicates = [c for c in by_scope.get(cell.get("scope", ""), [])
                      if c["key"] != cell["key"]]

        if duplicates and cell.get("tasks", 0) < max(
                (d.get("tasks", 0) for d in duplicates), default=0):
            merge.append({"cell": cell["key"], "into": duplicates[0]["key"],
                          "reason": f"redundant scope {cell.get('scope')!r}, fewer completions",
                          "preserve": cell.get("lessons", [])})
        elif idle and cell.get("tasks", 0) == 0:
            retire.append({"cell": cell["key"],
                           "reason": f"no completed work in {IDLE_DAYS_BEFORE_REVIEW} days",
                           "preserve": cell.get("lessons", [])})
        else:
            keep.append(cell["key"])

    return {
        "keep": keep, "merge": merge, "retire": retire,
        "note": ("More agents are allowed; redundant and consistently idle ones are not. "
                 "Every recommendation carries what to preserve first — retiring a cell and "
                 "discarding what it learned costs more than the cell did (#192)."),
    }


# ===========================================================================
# The runtime half. Everything above is a library; everything below reads the database the
# worker runs on, so the numbers above decide something instead of being reported.
#
# A proof audit (2026-09-26) found #174, #175, #176, #186 and #187 claimed covered while
# nothing in the runtime called any of this: `fan_out()` produced a number nobody acted on,
# `orphans()` had no caller, `next_work()` was only ever called with `[]`, and every queued
# job's priority was 50 or 100 by cadence period. The functions below are what the
# `swarm.*` handlers call.
# ===========================================================================

# ---------------------------------------------------------------------------
# #187: job types to the eight bands

# Every job type this system can run, mapped to the band its *kind of work* belongs to. The
# mapping is explicit rather than inferred from a name, because an inferred band is decided by
# whoever named the job type. A job type missing from this table falls to housekeeping and
# `band_for` says so (`mapped: False`); a test asserts every registered handler is mapped.
JOB_BANDS: dict[str, str] = {
    # A customer is waiting on this, now.
    "support.reply": "customer_incident",
    # Something this system claims may no longer be true: a stale artefact under a live slug,
    # a listing built from a superseded release, a gate verdict, or the system's own claims
    # about itself (online, within budget, capability open). A health check answered late is
    # a false "online" left standing, which is why liveness is here and not in housekeeping.
    "ops.sentinel": "truth_defect",
    "chain.rebuild": "truth_defect",
    "support.triage": "truth_defect",
    "gate.quality": "truth_defect",
    "gate.policy": "truth_defect",
    "gate.asset_truth": "truth_defect",
    "gate.certify": "truth_defect",
    "gate.lanes": "truth_defect",
    "physical.record": "truth_defect",
    "ops.heartbeat": "truth_defect",
    "ops.health": "truth_defect",
    "ops.queue_check": "truth_defect",
    "finance.escalation_check": "truth_defect",
    # A spend spike keeps spending until the governor pauses it, so it runs in the same band
    # as the escalation check rather than behind the week's exploration.
    "finance.governor": "truth_defect",
    "finance.challenge": "truth_defect",
    "ops.capability_probes": "truth_defect",
    "model.probe": "truth_defect",
    "ops.policy_watch": "truth_defect",
    # A window closes and cannot be reopened.
    "seasonal.sentinel": "seasonal_deadline",
    "seasonal.engine": "seasonal_deadline",
    "ops.thrash": "truth_defect",
    # #311: an MJs-derived opportunity's window closes exactly like a certified product's.
    "mjs.seasonal_sentinel": "seasonal_deadline",
    "seasonal.remerchandising": "seasonal_deadline",
    "launch.plan": "seasonal_deadline",
    "launch.readiness": "seasonal_deadline",
    "marketing.schedule": "seasonal_deadline",
    # The release chain of a certified product: known demand, known economics.
    "cir.draft": "proven_winner",
    "cir.revise": "proven_winner",
    "cir.compile": "proven_winner",
    "cir.twin": "proven_winner",
    "cir.reverse": "proven_winner",
    "assets.build": "proven_winner",
    "assets.physical_upgrade": "proven_winner",
    "physical.photo": "truth_defect",
    "physical.upgrade_impact": "exploration",
    "visual.identity_drift": "truth_defect",
    "creative.benchmark_memory": "benchmark_change",
    "creative.reference_reading": "benchmark_change",
    "assets.render": "proven_winner",
    "assets.owned_photography": "proven_winner",
    "assets.model_photography": "proven_winner",
    "listing.draft": "proven_winner",
    "listing.seo": "proven_winner",
    "pricing.position": "proven_winner",
    "collection.assemble": "proven_winner",
    "store.publish": "proven_winner",
    "store.update": "proven_winner",
    "content.draft": "proven_winner",
    "finance.reconcile": "proven_winner",
    # The named benchmark moved, or might have.
    "mjs.scan": "benchmark_change",
    "intel.serp_capture": "exploration",
    "mjs.reviews": "benchmark_change",
    "intel.benchmark_health": "benchmark_change",
    "intel.panel_discovery": "benchmark_change",
    "intel.benchmark_refresh": "benchmark_change",
    "etsy.probe": "benchmark_change",
    "intel.gallery_analysis": "benchmark_change",
    "intel.acceptance": "benchmark_change",
    "radar.scan": "benchmark_change",
    "radar.competitor_snapshot": "benchmark_change",
    "culture.sweep": "benchmark_change",
    "creative.blind_review": "benchmark_change",
    # Unproven, possibly valuable.
    "radar.score": "new_opportunity",
    "creative.expedition": "new_opportunity",
    "creative.grid_tournament": "new_opportunity",
    "creative.tournament": "new_opportunity",
    "plan.cycle": "new_opportunity",
    "pricing.experiment": "new_opportunity",
    "growth.experiments": "new_opportunity",
    "growth.conclude": "new_opportunity",
    "ads.campaign": "new_opportunity",
    "ads.adjust": "new_opportunity",
    "growth.distribution": "new_opportunity",
    "growth.journey": "truth_defect",
    "growth.steer": "housekeeping",
    "growth.preproduction": "exploration",
    # Learning with no committed value.
    "creative.blinded": "exploration",
    "creative.image_benchmark": "exploration",
    "creative.model_tournament": "exploration",
    "creative.model_reference_pack": "exploration",
    "creative.model_freeze": "exploration",
    "creative.photoreal_calibration": "exploration",
    "visual.provider_trial": "exploration",
    "visual.portrait_repair": "exploration",
    "seasonal.cycle_proof": "exploration",
    "improve.nightly": "exploration",
    "improve.weekly": "exploration",
    "improve.retrospective": "exploration",
    "intel.pod_learning": "exploration",
    "improve.role_work": "exploration",
    "improve.measure": "exploration",
    "improve.mine": "exploration",
    "improve.monitor": "exploration",
    "improve.sandbox": "exploration",
    "improve.league": "exploration",
    "improve.replay": "exploration",
    "teardown.enforce": "benchmark_change",
    "creative.style_learning": "exploration",
    "creative.white_space": "exploration",
    "commerce.readings": "exploration",
    "commerce.orders_ingest": "exploration",
    # F-005: a read-only Etsy taxonomy snapshot, behind the etsy_api gate.
    "listing.taxonomy_refresh": "exploration",
    "commerce.order_readings": "exploration",
    "scale.trajectory": "exploration",
    "creative.north_star": "exploration",
    "creative.four_season": "exploration",
    "creative.outcome_learning": "exploration",
    "seasonal.harvest": "exploration",
    "plan.strategy": "exploration",
    "portfolio.review": "exploration",
    # Keeps the system honest, urgent to nobody.
    "build.tick": "housekeeping",
    "ops.continuity": "housekeeping",
    "ops.offsite_archive": "housekeeping",
    "ops.retention": "housekeeping",
    "ops.capacity": "housekeeping",
    "ops.dependencies": "housekeeping",
    "ops.provenance_backfill": "housekeeping",
    "swarm.review": "housekeeping",
    "swarm.allocate": "housekeeping",
    "swarm.orphans": "housekeeping",
    "swarm.backlog": "housekeeping",
}

UNMAPPED_KIND = "housekeeping"


def band_for(job_type: str) -> dict:
    """The band a job type is enqueued at, and whether that was a decision or a default."""
    kind = JOB_BANDS.get(job_type)
    mapped = kind is not None
    kind = kind or UNMAPPED_KIND
    return {"job_type": job_type, "kind": kind, "band": BAND_BY_KIND[kind],
            "mapped": mapped}


# ---------------------------------------------------------------------------
# Protected bands (Codex CB2-G02). A declared invariant, enforced in two places:
#
#   1. `JobQueue.claim` orders by claim tier first -- customer_incident job types, then
#      truth_defect job types, then everything else -- and only then by priority less aging.
#      Aging (C-15) still lifts a starved job past fresher work *within* its tier, but no
#      amount of waiting, steering or explicit priority lets ordinary work be claimed while
#      runnable protected work waits.
#   2. `growth.steer` (and anything else that re-prioritises queued work) may move a job by
#      at most `steer_floor`: a job outside the protected bands is never moved into them, and
#      a job already inside one is never moved across it.
#
# The tier is decided by the job type's declared band (JOB_BANDS), not by the stored number,
# because the stored number is precisely what steering, deadlines and explicit enqueues change.
PROTECTED_KINDS: tuple[str, ...] = ("customer_incident", "truth_defect")
PROTECTED_CEILING: int = max(BAND_BY_KIND[k] for k in PROTECTED_KINDS)
ORDINARY_TIER: int = len(PROTECTED_KINDS)


def protected_job_types() -> dict[str, frozenset[str]]:
    """{protected kind: the job types declared in it}, in claim order."""
    return {kind: frozenset(t for t, k in JOB_BANDS.items() if k == kind)
            for kind in PROTECTED_KINDS}


def claim_tier(job_type: str) -> int:
    """0 customer_incident, 1 truth_defect, ORDINARY_TIER for every other job type."""
    kind = JOB_BANDS.get(job_type)
    return PROTECTED_KINDS.index(kind) if kind in PROTECTED_KINDS else ORDINARY_TIER


def steer_floor(job_type: str, current: int) -> int:
    """The lowest priority number a re-prioritisation may move this job to.

    A job sitting outside the protected bands stops one point behind the truth_defect band.
    A protected-type job sitting inside its own band stops at that band's floor (band less the
    within-band allowance), never crossing into the band above it. A job whose stored number
    is already at or below its floor is not moved further up at all.
    """
    current = int(current)
    tier = claim_tier(job_type)
    if tier < ORDINARY_TIER and current <= PROTECTED_CEILING:
        floor = BAND_BY_KIND[PROTECTED_KINDS[tier]] - MAX_WITHIN_BAND
        above = BAND_BY_KIND[PROTECTED_KINDS[tier - 1]] + 1 if tier > 0 else floor
        floor = max(floor, above)
    else:
        floor = PROTECTED_CEILING + 1
    return min(floor, current)


def steered_priority(job_type: str, current: int, delta: int) -> int:
    """`current + delta`, bounded below by `steer_floor` (Codex CB2-G02)."""
    return max(int(current) + int(delta), steer_floor(job_type, current))


def priority_for(job_type: str, inputs: dict | None = None, *, db=None,
                 now: datetime | None = None) -> int:
    """The `Job.priority` to enqueue a job at: its band, then deadline and value (#187).

    This replaced `50 if period <= 3600 else 100`, which ordered work by how often it was
    scheduled -- a proxy for nothing. With no inputs it is the job type's band. With inputs it
    is `priority_decision`: a deadline the job carries and the business value it names move
    it up *within* its band (never across one), and listing work whose product has earned
    nothing is not `proven_winner` work.
    """
    if not inputs and db is None:
        return int(band_for(job_type)["band"])
    return int(priority_decision(job_type, inputs, db=db, now=now)["priority"])


# ---------------------------------------------------------------------------
# #187: expected business value and deadlines, within a band
#
# The band is the commercial argument and is never traded away. Inside it, a job carrying a
# deadline that is days away is claimed before one whose window is a quarter off, and a job
# naming a larger expected value before a smaller one. The weights are a versioned scoring
# policy (`improve.league`, kind `scoring`): `improve.replay` replays historical jobs under the
# incumbent and its challengers, and a challenger that meets more deadlines on the replay and
# its holdout is promoted through the improvement sandbox -- which is what the runtime then
# reads here.

PRIORITY_POLICY_KIND = "scoring"
PRIORITY_POLICY_KEY = "policy:job_priority"
DEFAULT_PRIORITY_POLICY: dict = {"deadline_weight": 2.0, "value_weight": 2.0,
                                 "horizon_days": 30.0, "value_scale_cad": 500.0}
# Strictly below the smallest step between two bands (5), so no deadline and no value can
# carry a job across a band.
MAX_WITHIN_BAND = 4
DEADLINE_KEYS: tuple[str, ...] = ("deadline", "latest_launch", "window_closes", "launch_by",
                                  "due", "preferred_launch", "event_date")
VALUE_KEYS: tuple[str, ...] = ("value_cad", "expected_value_cad", "expected_revenue_cad")
# C-66 / Codex M05: a department's *heuristic* reason to claim a job earlier -- a lesson that
# favours this work -- is carried under its own key, bounded to one step inside the band, and
# is never written into a currency field. A CAD value on a job is a sourced estimate of what
# the work is worth; a heuristic is a reason, and the two are not exchangeable.
HEURISTIC_KEY = "priority_heuristic"
MAX_HEURISTIC_STEPS = 1
LISTING_KINDS_NEEDING_PROOF: frozenset[str] = frozenset({"proven_winner"})
_POLICY_CACHE: dict = {}
_POLICY_TTL = timedelta(minutes=5)


def clear_policy_cache() -> None:
    _POLICY_CACHE.clear()


def priority_policy(db=None, *, now: datetime | None = None) -> dict:
    """The incumbent job-priority policy from the registry, or the default when none is."""
    if db is None:
        return {**DEFAULT_PRIORITY_POLICY, "config_id": None, "source": "default"}
    now = now or datetime.now(timezone.utc)
    key = id(db)
    hit = _POLICY_CACHE.get(key)
    if hit is not None and now - hit[0] < _POLICY_TTL:
        return hit[1]
    try:
        from ..improve.league import incumbent_payload

        row = incumbent_payload(db, kind=PRIORITY_POLICY_KIND, key=PRIORITY_POLICY_KEY)
    except Exception:  # noqa: BLE001 - an unreadable registry is the default policy
        row = None
    policy = {**DEFAULT_PRIORITY_POLICY, "config_id": None, "source": "default"}
    if row is not None and row.get("payload"):
        try:
            loaded = json.loads(row["payload"])
            policy = {**DEFAULT_PRIORITY_POLICY,
                      **{k: float(v) for k, v in loaded.items() if k in DEFAULT_PRIORITY_POLICY},
                      "config_id": row["config_id"], "source": f"registry v{row['version']}"}
        except (ValueError, TypeError):
            pass
    _POLICY_CACHE[key] = (now, policy)
    return policy


def _parse_when(value) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        text = str(value)
        when = (datetime.fromisoformat(text) if "T" in text or " " in text
                else datetime.fromisoformat(text + "T23:59:59"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def deadline_of(inputs: dict | None) -> datetime | None:
    """The earliest deadline a job's inputs name, or None."""
    found = [_parse_when((inputs or {}).get(k)) for k in DEADLINE_KEYS]
    found = [f for f in found if f is not None]
    return min(found) if found else None


def value_of(inputs: dict | None) -> float | None:
    for k in VALUE_KEYS:
        v = (inputs or {}).get(k)
        if v not in (None, ""):
            try:
                return max(0.0, float(v))
            except (TypeError, ValueError):
                continue
    return None


def heuristic_of(inputs: dict | None) -> dict:
    """The bounded heuristic nudge a job's inputs carry, and its stated reason (M05)."""
    raw = (inputs or {}).get(HEURISTIC_KEY)
    if not isinstance(raw, dict):
        return {"steps": 0}
    try:
        steps = int(raw.get("steps") or 0)
    except (TypeError, ValueError):
        steps = 0
    return {"steps": max(0, min(MAX_HEURISTIC_STEPS, steps)),
            "source": str(raw.get("source") or "")[:80],
            "reason": str(raw.get("reason") or "")[:200],
            "lessons": list(raw.get("lessons") or [])[:10]}


def within_band(policy: dict, *, deadline_days: float | None, value_cad: float | None,
                heuristic_steps: int = 0) -> int:
    """Points a job moves up inside its band, from its deadline and value, capped.

    `heuristic_steps` is a department's stated reason to go earlier (a favouring lesson),
    already bounded by `heuristic_of`; it adds to the movement and never crosses the cap.
    """
    urgency = 0.0
    if deadline_days is not None:
        horizon = max(1.0, float(policy["horizon_days"]))
        urgency = max(0.0, 1.0 - min(max(deadline_days, 0.0), horizon) / horizon)
    value = 0.0
    if value_cad is not None:
        value = min(1.0, value_cad / max(1.0, float(policy["value_scale_cad"])))
    raw = urgency * float(policy["deadline_weight"]) + value * float(policy["value_weight"])
    steps = max(0, min(MAX_HEURISTIC_STEPS, int(heuristic_steps or 0)))
    return int(max(0, min(MAX_WITHIN_BAND, round(raw) + steps)))


def product_proven(db, slug: str) -> bool:
    """Whether a product has earned anything: a revenue ledger row attributed to it."""
    from sqlalchemy import select

    from ..core.models import LedgerEntry

    with db.session() as s:
        for row in s.scalars(select(LedgerEntry).where(LedgerEntry.gross_cad > 0)):
            if slug and slug in ((row.evidence_ref or "") + " " + (row.description or "")):
                return True
    return False


def priority_decision(job_type: str, inputs: dict | None = None, *, db=None,
                      now: datetime | None = None, policy: dict | None = None) -> dict:
    """The band, the within-band movement and the reason, for one job about to be enqueued."""
    now = now or datetime.now(timezone.utc)
    banded = band_for(job_type)
    kind = banded["kind"]
    demoted = ""
    slug = str((inputs or {}).get("slug") or (inputs or {}).get("product_slug") or "")
    if kind in LISTING_KINDS_NEEDING_PROOF and slug and db is not None:
        try:
            proven = product_proven(db, slug)
        except Exception:  # noqa: BLE001
            proven = True
        if not proven:
            kind = "new_opportunity"
            demoted = (f"{slug} has no attributed revenue, so its work is an unproven "
                       f"opportunity rather than a proven winner")
    policy = policy or priority_policy(db, now=now)
    deadline = deadline_of(inputs)
    days = None if deadline is None else (deadline - now).total_seconds() / 86400.0
    value = value_of(inputs)
    heuristic = heuristic_of(inputs)
    moved = within_band(policy, deadline_days=days, value_cad=value,
                        heuristic_steps=heuristic["steps"])
    band = BAND_BY_KIND[kind]
    return {"job_type": job_type, "kind": kind, "band": band, "moved": moved,
            "priority": band - moved, "deadline_days": None if days is None else round(days, 2),
            "value_cad": value, "demoted": demoted or None,
            "heuristic": heuristic if heuristic["steps"] else None,
            "policy": {k: policy.get(k) for k in ("config_id", "source")}}


# ---------------------------------------------------------------------------
# Shared reads

_OPEN_STATUSES = ("pending", "running", "failed")
_TERMINAL_OK = "done"
_TERMINAL_BAD = "dead"


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _status(job) -> str:
    return getattr(job.status, "value", str(job.status))


def _scheduled_job_types() -> set[str]:
    try:
        from ..runtime.worker import CADENCES
    except Exception:  # noqa: BLE001 # pragma: no cover - import order in odd callers
        return set()
    return {job_type for _n, _a, job_type, _p in CADENCES}


def _owner_problem(agent, job_type: str) -> str:
    """Why this agent cannot own this job, or "" when it can."""
    from ..agents.registry import FORBIDDEN_COMBINATIONS

    if agent is None:
        return "no such agent in the registry"
    if not agent.enabled:
        return f"agent {agent.name!r} is disabled"
    if job_type in FORBIDDEN_COMBINATIONS.get(agent.name, set()):
        return f"agent {agent.name!r} is structurally forbidden from {job_type!r}"
    if job_type not in (agent.allowed_job_types or []):
        return f"agent {agent.name!r} has no permission for {job_type!r}"
    return ""


# ---------------------------------------------------------------------------
# #174: every agent has a quality metric and a retirement condition


FUNCTION_FLOOR = 0.5
FUNCTION_MIN_SAMPLE = 5

# Codex M08: what kind of evidence each function metric is. Most are a *rate over the rows the
# function produced* -- how many of its own outputs passed the next stage -- which screens for
# a function that produces junk and says nothing about whether what passed was good. They are
# labelled so, never as observed quality. Only realised uplift is an outcome; the SEO score is
# our own scorer reading our own listing.
FUNCTION_EVIDENCE: dict[str, str] = {
    "role_realised_uplift": "realised_outcome",
    "listing_seo_score": "internal_score",
}
PRODUCTION_RATE_PROXY = "production_rate_proxy"
FUNCTION_EVIDENCE_LIMITS: dict[str, str] = {
    PRODUCTION_RATE_PROXY: ("a rate over rows this function produced, judged by the next stage "
                            "it fed; it screens for weak output and does not measure the "
                            "quality of what passed, so it can lower a verdict to watch and "
                            "never raise one"),
    "internal_score": "our own scorer read on our own artefact; not an independent reading",
    "realised_outcome": "realised uplift attributed to kept proposals (improve.roi's window)",
}


def function_quality(db, name: str, *, now: datetime | None = None) -> dict:
    """The quality of what this agent's function produced, read from its rows (#174)."""
    from sqlalchemy import select

    from ..agents.registry import stewardship
    from ..core.models import (Experiment, Incident, Job, Listing, ListingAsset,
                               PatternVersion, SupportCase)

    rule = stewardship(name)
    metric = rule.get("function_metric", "useful_output_rate")
    if metric == "exempt":
        return {"metric": metric, "value": None, "sample": 0, "reading": "exempt",
                "reads": rule.get("function_reads", "")}

    def outs(job_types: tuple[str, ...] | None = None) -> list[dict]:
        with db.session() as s:
            q = select(Job).where(Job.agent == name, Job.status == _TERMINAL_OK_STATUS())
            return [dict(j.outputs or {}) for j in s.scalars(q)
                    if job_types is None or j.job_type in job_types]

    value, sample = None, 0
    if metric == "role_realised_uplift":
        from ..improve import roles

        activity, _detail = roles.activity_from_db(db, name, now=now)
        sample = activity.proposals_made
        value = activity.realised_uplift if activity.proposals_kept else None
    elif metric == "promotion_yield":
        rows = outs(("radar.score",))
        sample, value = len(rows), (sum(1 for o in rows if o.get("promoted")) / len(rows)
                                    if rows else None)
    elif metric == "compile_pass_rate":
        rows = [o for o in outs(("cir.compile",)) if "compiled" in o]
        sample, value = len(rows), (sum(1 for o in rows if o["compiled"]) / len(rows)
                                    if rows else None)
    elif metric == "certification_grant_rate":
        rows = [o for o in outs(("gate.certify",)) if "granted" in o]
        sample, value = len(rows), (sum(1 for o in rows if o["granted"]) / len(rows)
                                    if rows else None)
    elif metric == "drafts_certified":
        drafts = len(outs(("cir.draft",)))
        with db.session() as s:
            certified = sum(1 for _ in s.scalars(select(PatternVersion).where(
                PatternVersion.certified == True)))  # noqa: E712
        sample, value = drafts, (min(1.0, certified / drafts) if drafts else None)
    elif metric == "asset_approval_rate":
        with db.session() as s:
            assets = list(s.scalars(select(ListingAsset)))
        sample, value = len(assets), (sum(1 for a in assets if a.approved) / len(assets)
                                      if assets else None)
    elif metric == "content_without_problems":
        rows = outs(("marketing.schedule",))
        sample, value = len(rows), (sum(1 for o in rows if not o.get("problems")) / len(rows)
                                    if rows else None)
    elif metric == "listing_seo_score":
        with db.session() as s:
            scores = [float(li.seo_score or 0.0) for li in s.scalars(select(Listing))]
        sample, value = len(scores), (sum(scores) / len(scores) if scores else None)
    elif metric == "cases_drafted":
        with db.session() as s:
            cases = list(s.scalars(select(SupportCase)))
        sample, value = len(cases), (sum(1 for c in cases if c.answer) / len(cases)
                                     if cases else None)
    elif metric == "orphans_resolved":
        with db.session() as s:
            raised = [i for i in s.scalars(select(Incident))
                      if (i.signature or "").startswith("swarm.orphan:")]
        sample, value = len(raised), (sum(1 for i in raised if i.resolved) / len(raised)
                                      if raised else None)
    elif metric == "experiments_decided":
        with db.session() as s:
            exps = list(s.scalars(select(Experiment)))
        sample, value = len(exps), (sum(1 for e in exps if e.result) / len(exps)
                                    if exps else None)
    else:  # useful_output_rate
        from ..runtime.pipeline import did_no_work

        rows = outs()
        sample, value = len(rows), (sum(1 for o in rows if not did_no_work(o)) / len(rows)
                                    if rows else None)
    measured = value is not None and sample >= FUNCTION_MIN_SAMPLE
    evidence = FUNCTION_EVIDENCE.get(metric, PRODUCTION_RATE_PROXY)
    return {"metric": metric, "reads": rule.get("function_reads", ""),
            "value": None if value is None else round(float(value), 4),
            "sample": sample, "reading": "measured" if measured else "UNMEASURED",
            "floor": FUNCTION_FLOOR if metric not in ("role_realised_uplift",
                                                      "listing_seo_score") else None,
            # Codex M08: the kind of evidence this number is, and what it cannot say.
            "evidence": evidence, "limits": FUNCTION_EVIDENCE_LIMITS[evidence]}


def _TERMINAL_OK_STATUS():
    from ..core.models import JobStatus

    return JobStatus.DONE


def agent_quality(db, *, now: datetime | None = None) -> dict:
    """Each agent's quality metric, read from job outcomes, and its retirement verdict.

    The metric and the condition come from `agents.registry.stewardship(name)`, the side
    table beside `DEFAULT_AGENTS`; this reads the `jobs` table (terminal outcomes in the
    window) and applies them. Nothing here disables anything: the verdict is a
    recommendation, because an agent's `enabled` flag is runtime state and switching off an
    agent whose cadence still fires turns its schedule into dead letters.
    """
    from sqlalchemy import select

    from ..agents.registry import Registry, stewardship
    from ..core.models import Job

    now = now or datetime.now(timezone.utc)
    agents = Registry(db).all()
    scheduled = _scheduled_job_types()

    with db.session() as s:
        jobs = [(j.agent, j.job_type, _status(j), _aware(j.finished_at),
                 (j.last_error or "")[:40]) for j in s.scalars(select(Job))]

    report, cells = {}, []
    for agent in agents:
        rule = stewardship(agent.name)
        window_start = now - timedelta(days=rule["window_days"])
        mine = [j for j in jobs if j[0] == agent.name]
        terminal = [j for j in mine if j[2] in (_TERMINAL_OK, _TERMINAL_BAD)
                    and j[3] is not None and j[3] >= window_start]
        done = [j for j in terminal if j[2] == _TERMINAL_OK]
        dead = [j for j in terminal if j[2] == _TERMINAL_BAD]
        denied = [j for j in dead if j[4].startswith("permission denied")]
        pending = [j for j in mine if j[2] in _OPEN_STATUSES]
        last_done = max((j[3] for j in mine if j[2] == _TERMINAL_OK and j[3]), default=None)
        on_cadence = sorted(set(agent.allowed_job_types or []) & scheduled)

        sample = len(terminal)
        rate = round(len(done) / sample, 4) if sample else None
        measured = sample >= rule["min_sample"]
        idle_cutoff = now - timedelta(days=IDLE_DAYS_BEFORE_REVIEW)
        idle = (last_done is None or last_done < idle_cutoff)

        if rule["exempt"]:
            verdict, why = "keep", f"dormant by design: {rule['exempt']}"
        elif measured and rate is not None and rate < rule["retire_below"]:
            verdict = "retire_or_repair"
            why = (f"{rule['metric']} {rate:.0%} over {sample} terminal jobs is below the "
                   f"retirement line of {rule['retire_below']:.0%}")
        elif idle and not on_cadence and not pending:
            verdict = "retire"
            why = (f"no completed job in {IDLE_DAYS_BEFORE_REVIEW} days, none of its job "
                   f"types is scheduled and nothing is queued for it")
        elif measured and rate is not None and rate < rule["floor"]:
            verdict = "watch"
            why = f"{rule['metric']} {rate:.0%} is below its floor of {rule['floor']:.0%}"
        else:
            verdict = "keep"
            why = ("inside its floor" if measured else
                   f"UNMEASURED: {sample} terminal job(s) in {rule['window_days']} days "
                   f"against a minimum sample of {rule['min_sample']}")

        function = function_quality(db, agent.name, now=now)
        if (verdict == "keep" and not rule["exempt"] and function["reading"] == "measured"
                and function.get("floor") is not None
                and function["value"] < function["floor"]):
            verdict = "watch"
            why = (f"its function metric {function['metric']} reads {function['value']:.0%} "
                   f"over {function['sample']}, below {function['floor']:.0%}: its jobs "
                   f"finish and what they produce is weak")
        report[agent.name] = {
            "metric": rule["metric"], "reads": rule["reads"],
            "inputs": rule.get("inputs", []), "outputs": rule.get("outputs", []),
            "function_quality": function,
            "value": rate if measured else None,
            "reading": "measured" if measured else "UNMEASURED",
            "sample": sample, "done": len(done), "dead": len(dead),
            "permission_denied": len(denied), "open": len(pending),
            "floor": rule["floor"], "retire_below": rule["retire_below"],
            "retirement_condition": rule["retire_when"],
            "on_cadence": on_cadence, "verdict": verdict, "why": why,
        }
        cells.append({"key": agent.name,
                      "scope": "|".join(sorted(agent.allowed_job_types or [])),
                      "tasks": len(done),
                      "last_success_at": last_done.isoformat() if last_done else None,
                      "lessons": []})

    # Redundancy is a property of the set, so it is read from the set: two agents holding
    # exactly the same job types are the merge `retirement_review` exists for.
    overlap = retirement_review(cells, now=now)
    for merge in overlap["merge"]:
        entry = report.get(merge["cell"])
        if entry is not None and not stewardship(merge["cell"])["exempt"]:
            entry["verdict"] = "merge"
            entry["why"] = f"{merge['reason']}; merge into {merge['into']}"
    return {
        "as_of": now.isoformat(),
        "agents": report,
        "retire": sorted(k for k, v in report.items() if v["verdict"] in
                         ("retire", "retire_or_repair")),
        "merge": sorted(k for k, v in report.items() if v["verdict"] == "merge"),
        "watch": sorted(k for k, v in report.items() if v["verdict"] == "watch"),
        "unmeasured": sorted(k for k, v in report.items() if v["reading"] == "UNMEASURED"),
        "enacted": False,
        "note": ("A recommendation, not an action: retiring an agent is a change to "
                 "DEFAULT_AGENTS, reviewed like any other permission change (#174, #192)."),
    }


# ---------------------------------------------------------------------------
# #175: allocation drives which lanes run and how much each may take

# How many standing-backlog jobs one idle tick may queue. Small on purpose: the backlog exists
# so an idle worker does something useful, not so it manufactures a queue.
MAX_BACKLOG_PER_TICK = 2
# What one specialist-run is priced at for the lane budget. Deliberately the padded figure
# `fan_out` already uses, so the two cannot disagree.
LANE_UNIT_COST_CAD = 0.05
# The allocation's own period, used to pace each agent's daily ceiling across runs.
ALLOCATION_PERIOD_SECONDS = 60 * 60
# An allocation older than this is not read; the backlog recomputes one instead.
ALLOCATION_MAX_AGE = timedelta(hours=6)


def _open_jobs(db, *, exclude_prefix: str = "swarm.") -> list[tuple]:
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    with db.session() as s:
        rows = s.scalars(select(Job).where(
            Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING))))
        return [(j.id, j.agent, j.job_type, _status(j)) for j in rows
                if not j.job_type.startswith(exclude_prefix)]


def allocate(db, *, now: datetime | None = None,
             period_seconds: int = ALLOCATION_PERIOD_SECONDS) -> dict:
    """Decide which lanes are active and how large each lane's batch may be, and record it.

    A lane is an agent. Its budget is what `spend_policy.work_that_fits` says fits under its
    own daily ceiling and the month's ceiling *now*; `fan_out` turns that and the lane's queue
    depth into specialists; the batch is the work those specialists may take. Nothing here
    raises a ceiling or spends: an agent whose ceiling is spent gets an inactive lane, and
    the standing backlog will not feed it.
    """
    from ..agents.registry import Registry
    from ..core.models import Authority, SwarmAllocation
    from ..finance.spend_policy import work_that_fits
    from ..intel import capacity as mission_capacity

    now = now or datetime.now(timezone.utc)
    open_jobs = _open_jobs(db)
    depth: dict[str, int] = {}
    for _id, agent, _t, _st in open_jobs:
        depth[agent] = depth.get(agent, 0) + 1

    # C-68 (#175): the allocation reads category, season, opportunity value and bottleneck,
    # not only queue depth and budget. Category is the agent's #30 function; season is open
    # work in the seasonal-deadline (or more urgent) bands, which is deadline pressure for
    # `fan_out`; opportunity value is open work in the proven-winner band or better; the
    # bottleneck is the function the latest capacity reading tilted toward.
    from .capacity import function_of, latest_mix

    mix = latest_mix(db, now=now)
    bottleneck = None
    with db.session() as s:
        from sqlalchemy import desc, select as _select

        from ..core.models import AuditLog as _Audit

        cap = s.scalar(_select(_Audit).where(_Audit.action == "ops.capacity")
                       .order_by(desc(_Audit.id)).limit(1))
        if cap is not None:
            bottleneck = (cap.detail or {}).get("tilted_toward")
    from ..finance.governor import unproductive_lanes

    unproductive = set(unproductive_lanes(db, now=now))
    pressure: dict[str, bool] = {}
    valuable: dict[str, int] = {}
    for _id, agent_name, jt, _st in open_jobs:
        band = band_for(jt)["band"]
        if band <= BAND_BY_KIND["seasonal_deadline"]:
            pressure[agent_name] = True
        if band <= BAND_BY_KIND["proven_winner"]:
            valuable[agent_name] = valuable.get(agent_name, 0) + 1

    lanes: dict[str, dict] = {}
    for agent in Registry(db).all():
        if not agent.enabled:
            continue
        pending = depth.get(agent.name, 0)
        fits = work_that_fits(db, agent=agent.name, purpose="swarm.lane",
                              period_seconds=period_seconds,
                              unit_cost_cad=LANE_UNIT_COST_CAD, now=now)
        fo = fan_out(open_work=pending, budget_remaining_cad=fits["cad_available_now"],
                     cost_per_specialist_cad=LANE_UNIT_COST_CAD,
                     deadline_pressure=pressure.get(agent.name, False))
        function = function_of(agent.name)
        granted = fo["granted"]
        affordable = fo["affordable"]
        boosts = []
        if pending and bottleneck and function == bottleneck:
            granted, boosts = granted + 1, boosts + [f"bottleneck function {bottleneck}"]
        if pending and valuable.get(agent.name):
            granted, boosts = granted + 1, boosts + [
                f"{valuable[agent.name]} open job(s) at proven-winner value or above"]
        granted = min(granted, affordable) if pending else fo["granted"]
        if agent.name in unproductive and granted > 1:
            # #31: spend that produced no validated pattern caps the lane that spent it.
            granted, boosts = 1, boosts + ["capped: 30 days of spend, no validated pattern"]
        lanes[agent.name] = {
            "open_work": pending, "wanted": fo["wanted"], "granted": granted,
            "bounded_by": fo["bounded_by"], "binding_ceiling": fits["binding_ceiling"],
            "cad_available_now": fits["cad_available_now"],
            "batch": min(pending, granted * WORK_PER_SPECIALIST) if pending else 0,
            "active": granted > 0,
            "green": agent.authority == Authority.GREEN,
            "function": function, "target_share": mix["mix"].get(function),
            "deadline_pressure": pressure.get(agent.name, False),
            "value_open": valuable.get(agent.name, 0), "boosts": boosts,
        }
        # #302: the benchmark mission's lane holds a reserved floor generic research cannot
        # draw below. Sized for the reserve plus the generic draw and bounded only by what
        # the lane's own ceiling affords, so the reservation never raises a ceiling.
        if agent.name == mission_capacity.MISSION_AGENT:
            mission_open = sum(1 for _i, a, t, _s in open_jobs
                               if a == agent.name and mission_capacity.is_mission_work(t))
            reserve = mission_capacity.reserve_lane(
                mission_open=mission_open, generic_open=pending - mission_open,
                granted=fo["granted"],
                affordable=int(fits["cad_available_now"] / LANE_UNIT_COST_CAD),
                work_per_specialist=WORK_PER_SPECIALIST)
            lane = lanes[agent.name]
            lane["granted"] = reserve["total"]
            lane["active"] = reserve["total"] > 0
            lane["batch"] = reserve["mission_batch"] + reserve["generic_batch"]
            lane["mjs_reserve"] = reserve

    idle = not open_jobs
    backlog_lanes = sorted(name for name, lane in lanes.items()
                           if lane["active"] and lane["green"] and lane["open_work"] == 0)
    backlog_batch = min(MAX_BACKLOG_PER_TICK, len(backlog_lanes)) if idle else 0
    granted = sum(lane["granted"] for lane in lanes.values())

    record = {
        "as_of": now.isoformat(), "open_work": len(open_jobs), "idle": idle,
        "granted": granted, "lanes": lanes,
        "active_lanes": sorted(k for k, v in lanes.items() if v["active"]),
        "inactive_lanes": sorted(k for k, v in lanes.items() if not v["active"]),
        "backlog_batch": backlog_batch, "backlog_lanes": backlog_lanes,
        "mjs_reserve": (lanes.get(mission_capacity.MISSION_AGENT) or {}).get("mjs_reserve"),
        "spend_increase_cad": 0.0,
        "mix": mix, "bottleneck": bottleneck,
        "note": ("Allocation reads existing ceilings and never raises one. An inactive lane "
                 "is one whose ceiling has no room for another run; the standing backlog "
                 "does not feed it (#175)."),
    }
    with db.session() as s:
        row = SwarmAllocation(at=now, open_work=len(open_jobs), granted=granted,
                              lanes=lanes, backlog_batch=backlog_batch,
                              detail={k: v for k, v in record.items() if k != "lanes"})
        s.add(row)
        s.flush()
        record["allocation_id"] = row.id
    # #175: what the runner activates from this allocation, recorded beside it.
    from .capacity import worker_target

    record["workers"] = worker_target(db, now=now)
    with db.session() as s:
        row = s.get(SwarmAllocation, record["allocation_id"])
        row.detail = {**dict(row.detail or {}), "workers": record["workers"]}
    return record


def latest_allocation(db, *, now: datetime | None = None) -> dict | None:
    """The most recent allocation young enough to act on, or None."""
    from sqlalchemy import desc, select

    from ..core.models import SwarmAllocation

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        row = s.scalar(select(SwarmAllocation).order_by(desc(SwarmAllocation.id)).limit(1))
        if row is None or now - _aware(row.at) > ALLOCATION_MAX_AGE:
            return None
        return {"allocation_id": row.id, "at": _aware(row.at).isoformat(),
                "lanes": dict(row.lanes or {}), "backlog_batch": row.backlog_batch,
                **{k: v for k, v in (row.detail or {}).items()
                   if k in ("idle", "active_lanes", "backlog_lanes")}}


def lane_batch(db, agent: str, *, now: datetime | None = None) -> dict:
    """How much one lane may take this period, per the latest allocation.

    For handlers that batch (the gallery backlog, a scan): the lane's batch is already
    bounded by `work_that_fits`, so a handler that reads this cannot exceed its ceiling by
    reading a stale constant.
    """
    alloc = latest_allocation(db, now=now)
    if alloc is None:
        return {"known": False, "batch": None,
                "why": "no allocation in the last six hours; the lane is UNMEASURED"}
    lane = alloc["lanes"].get(agent)
    if lane is None:
        return {"known": False, "batch": None, "why": f"no lane for {agent!r}"}
    # The batch bounds a handler that takes many units in one run; the concurrency bounds how
    # many of the lane's jobs run at once, and is what `lane_hold` enforces at the claim.
    return {"known": True, "batch": lane["batch"], "active": lane["active"],
            "concurrency": max(MIN_SPECIALISTS, int(lane.get("granted") or 0)),
            "allocation_id": alloc["allocation_id"]}


# ---------------------------------------------------------------------------
# #175 at the claim: the allocation decides how many of a lane's jobs run at once
#
# `allocate` sized every lane and `lane_batch` read it back, and nothing between the queue and
# a handler ever asked either of them: a lane granted one specialist ran as many of its jobs at
# once as there were workers to claim them. The enforcement belongs at the claim, because that
# is the one point every job passes through. A lane's specialists *are* its concurrency, so a
# lane granted N may have N of its jobs running at once; a lane the governor has found to be
# duplicating rather than adding throughput is held to one. Nothing here raises a ceiling or
# spends: it only decides whether a claimed job runs now or goes back to the queue.

# The allocator's own work is never held by the allocation it produces. A lane sized at zero
# would otherwise stop `swarm.allocate` from ever running again to resize it.
LANE_EXEMPT_PREFIXES: tuple[str, ...] = ("swarm.",)
# How long a job held back by its lane waits before it is claimable again. Short: the lane
# frees as soon as one of its running jobs finishes, and the hold is not a penalty.
LANE_HOLD_SECONDS = 60
# The audit action the governor's cadence writes its parallelism advice under (#188).
GOVERNOR_ACTION = "finance.governor"
LANE_HELD_ACTION = "swarm.lane_held"


def parallelism_advice(db, *, now: datetime | None = None) -> dict | None:
    """The governor's latest parallelism verdict, when it is young enough to act on."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == GOVERNOR_ACTION)
                       .order_by(desc(AuditLog.id)).limit(1))
        if row is None or now - _aware(row.at) > ALLOCATION_MAX_AGE:
            return None
        advice = dict((row.detail or {}).get("parallelism") or {})
    if not advice:
        return None
    return {"advice": advice.get("advice"), "why": advice.get("why"),
            "compared": advice.get("compared")}


def lane_concurrency(db, agent: str, *, now: datetime | None = None) -> dict:
    """How many of this lane's jobs may run at once, per the latest allocation."""
    alloc = latest_allocation(db, now=now)
    if alloc is None:
        return {"known": False, "limit": None,
                "why": ("no allocation in the last six hours, so the lane is UNMEASURED and "
                        "the claim is not held on it. The ceilings at dispatch still refuse "
                        "any spend they do not cover")}
    lane = (alloc.get("lanes") or {}).get(agent)
    if lane is None:
        return {"known": False, "limit": None, "allocation_id": alloc["allocation_id"],
                "why": f"allocation {alloc['allocation_id']} has no lane for {agent!r}"}
    granted = int(lane.get("granted") or 0)
    limit = max(MIN_SPECIALISTS, granted)
    advice = parallelism_advice(db, now=now)
    why = (f"allocation {alloc['allocation_id']} granted {agent} {granted} specialist(s); "
           f"a lane's specialists are its concurrency, with a floor of {MIN_SPECIALISTS} so "
           f"work that spends nothing is never starved by a spending budget")
    if advice and advice.get("advice") == "scale_down":
        limit = MIN_SPECIALISTS
        why += (". The governor found added workers only duplicated work "
                f"({advice.get('why')}), so the lane runs one job at a time")
    elif advice and advice.get("advice") == "scale_up":
        # #188: parallelism is scaled *up* when it materially improved throughput, bounded
        # by the worker pool that exists -- a limit above the pool would be a number only.
        from .capacity import worker_threads

        limit = min(max(limit, MIN_SPECIALISTS) + 1, max(worker_threads(), limit))
        why += (". The governor found added workers raised throughput "
                f"({advice.get('why')}), so the lane may run one more at once")
    return {"known": True, "limit": limit, "granted": granted,
            "allocation_id": alloc["allocation_id"],
            "parallelism": (advice or {}).get("advice"), "why": why}


def _running_in_lane(db, agent: str, *, now: datetime,
                     exclude_job_id: int | None = None) -> int:
    """This lane's jobs running on a live lease right now, excluding the one being decided."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    with db.session() as s:
        rows = s.execute(select(Job.id, Job.job_type, Job.lease_expires_at).where(
            Job.agent == agent, Job.status == JobStatus.RUNNING)).all()
    return sum(1 for jid, jt, lease in rows
               if jid != exclude_job_id
               and not jt.startswith(LANE_EXEMPT_PREFIXES)
               and (lease is None or _aware(lease) > now))


def claim_decision(db, agent_name: str, *, job_type: str = "", job_id: int | None = None,
                   now: datetime | None = None) -> dict:
    """Whether this lane may run one more job now, and the reading behind the answer."""
    now = now or datetime.now(timezone.utc)
    if job_type and job_type.startswith(LANE_EXEMPT_PREFIXES):
        return {"may_claim": True, "agent": agent_name, "job_type": job_type,
                "why": "the allocator's own work is never held by the allocation it produces"}
    lane = lane_concurrency(db, agent_name, now=now)
    if not lane["known"]:
        return {"may_claim": True, "agent": agent_name, "job_type": job_type,
                "lane": lane, "why": lane["why"]}
    running = _running_in_lane(db, agent_name, now=now, exclude_job_id=job_id)
    ok = running < lane["limit"]
    return {"may_claim": ok, "agent": agent_name, "job_type": job_type,
            "running": running, "limit": lane["limit"], "lane": lane,
            "why": (f"{running} of {agent_name}'s jobs already running against a lane of "
                    f"{lane['limit']}: " + ("room for this one" if ok else
                                            "held until one of them finishes"))}


def may_claim(db, agent_name: str, *, job_type: str = "", job_id: int | None = None,
              now: datetime | None = None) -> bool:
    """True when the latest allocation leaves this lane room for one more running job (#175)."""
    return claim_decision(db, agent_name, job_type=job_type, job_id=job_id,
                          now=now)["may_claim"]


# Codex CB2-P09: lane admission is serialized. Every lane/share decision counts the *other*
# RUNNING jobs, and a just-claimed job is RUNNING before it is decided. Two workers that claimed
# same-lane jobs at once each read the other as running and both held -- every runnable job of
# the lane given back while nothing of it ran (mutual deferral), and with equal hold times the
# same collision could repeat. Taking one admission lock before the reads and releasing it only
# after a hold is written back means the second decider always sees the first one's outcome:
# an admitted job as running, a held one as pending. The limit is never exceeded (a decider
# reads every job claimed before its read) and a lane is never left fully held back.
LANE_ADMISSION_LOCK_KEY = 0x6C616E65   # "lane": the Postgres advisory-lock key
LANE_ADMISSION_RETRIES = 12


def _admission_session(db, job):
    """A session holding the lane-admission lock until it commits or rolls back.

    Postgres: a transaction-scoped advisory lock. SQLite: the database write lock, taken by a
    no-op write to the row this worker holds (WAL readers are not blocked by it).
    """
    import random
    import time

    from sqlalchemy import text, update
    from sqlalchemy.exc import OperationalError

    from ..core.db import is_postgres
    from ..core.models import Job

    delay = 0.02
    for attempt in range(LANE_ADMISSION_RETRIES):
        s = db.new_session()
        try:
            if is_postgres(db.engine):
                s.execute(text("SELECT pg_advisory_xact_lock(:k)"),
                          {"k": LANE_ADMISSION_LOCK_KEY})
            else:
                s.execute(update(Job).where(Job.id == job.id).values(leased_by=Job.leased_by)
                          .execution_options(synchronize_session=False))
            return s
        except OperationalError as exc:
            s.rollback()
            s.close()
            locked = "locked" in str(exc).lower()
            if not locked or attempt == LANE_ADMISSION_RETRIES - 1:
                raise
            time.sleep(delay * (1.0 + random.random()))
            delay = min(delay * 2, 1.0)
    raise AssertionError("unreachable")  # pragma: no cover


def lane_hold(db, job, *, worker: str, now: datetime | None = None) -> bool:
    """Give a just-claimed job back to the queue if its lane is full. True when it was held.

    The single call the worker makes after `claim` and before running anything. The job goes
    back exactly as it was -- pending, unleased, its attempt not counted -- and becomes
    claimable again after `LANE_HOLD_SECONDS`, so a held job never moves toward a dead letter.
    The write is conditional on this worker still holding the lease; a job it has already
    lost is left alone and reported as not held. The decision and the hold run under the
    lane-admission lock (CB2-P09), so concurrent deciders are serialized.
    """
    from sqlalchemy import update

    from ..core.models import AuditLog, Job, JobStatus

    lock = _admission_session(db, job)
    try:
        # Read the clock after the lock: a decider that waited must not judge leases by the
        # moment it started waiting.
        now = now or datetime.now(timezone.utc)
        decision = claim_decision(db, job.agent, job_type=job.job_type, job_id=job.id,
                                  now=now)
        if decision["may_claim"]:
            # C-68 (#5, #30): the function mix and the production-lane split, at the same claim.
            from .capacity import share_decision

            share = share_decision(db, job, now=now, exempt=LANE_EXEMPT_PREFIXES)
            if not share["hold"]:
                lock.commit()
                return False
            decision = {**decision, "may_claim": False, "why": share["why"],
                        "hold_kind": share.get("kind"), "share": share}
        values = {"status": JobStatus.PENDING, "leased_by": None, "lease_expires_at": None,
                  "attempts": Job.attempts - 1,
                  "run_after": now + timedelta(seconds=LANE_HOLD_SECONDS)}
        if int(job.attempts or 0) <= 1:
            values["started_at"] = None        # the claim was its first; it has not started
        res = lock.execute(update(Job).where(
            Job.id == job.id, Job.status == JobStatus.RUNNING, Job.leased_by == worker,
            Job.attempts == job.attempts).values(**values)
            .execution_options(synchronize_session=False))
        if res.rowcount != 1:
            lock.commit()
            return False
        lock.add(AuditLog(actor="swarm_steward", action=LANE_HELD_ACTION,
                          artifact=job.job_type, job_id=job.id,
                          detail={"agent": job.agent, "worker": worker,
                                  "hold_kind": decision.get("hold_kind") or "agent_lane",
                                  "share": decision.get("share"),
                                  "running": decision.get("running"),
                                  "limit": decision.get("limit"),
                                  "allocation_id": (decision.get("lane") or {}).get(
                                      "allocation_id"),
                                  "hold_seconds": LANE_HOLD_SECONDS,
                                  "why": decision["why"]}))
        lock.commit()
        return True
    except Exception:
        lock.rollback()
        raise
    finally:
        lock.close()


# ---------------------------------------------------------------------------
# #176: work items from the rows that hold work, and nothing unowned

# Who answers for an incident nobody assigned. Quality owns release certificates and can
# veto (DEFAULT_AGENTS), which is what an incident about a released pattern needs.
DEFAULT_INCIDENT_OWNER = "quality_director"
_OPEN_IMPROVEMENT_STATES = ("proposed", "testing")


def work_items(db) -> list[dict]:
    """Every open unit of work in the database, as a WorkItem with its owner checked.

    Three sources: queued jobs, unresolved incidents and open improvements. An owner is only
    an owner if it can act -- an agent that exists, is enabled and holds the permission --
    so a job enqueued against the wrong agent is unowned work, not owned work that fails.
    """
    from sqlalchemy import select

    from ..agents.registry import Registry
    from ..core.models import Improvement, Incident, Job, JobStatus

    try:
        from ..improve.cells import BY_KEY as CELLS
    except Exception:  # noqa: BLE001 # pragma: no cover
        CELLS = {}

    agents = {a.name: a for a in Registry(db).all()}
    out: list[dict] = []
    with db.session() as s:
        for job in s.scalars(select(Job).where(
                Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED)))):
            problem = _owner_problem(agents.get(job.agent), job.job_type)
            item = WorkItem(key=f"job:{job.id}", kind=band_for(job.job_type)["kind"],
                            owner="" if problem else job.agent, state="open")
            out.append({"item": item, "source": "job", "ref": job.id,
                        "job_type": job.job_type, "named_owner": job.agent,
                        "status": _status(job), "problem": problem})
        for inc in s.scalars(select(Incident).where(Incident.resolved.is_(False))):
            named = str((inc.detail or {}).get("owner") or "")
            agent = agents.get(named)
            problem = ("no owner recorded" if not named else
                       "" if agent is not None and agent.enabled else
                       f"owner {named!r} is not an enabled agent")
            kind = "customer_incident" if inc.severity in ("P0", "P1") else "truth_defect"
            out.append({"item": WorkItem(key=f"incident:{inc.id}", kind=kind,
                                         owner="" if problem else named, state="open"),
                        "source": "incident", "ref": inc.id, "signature": inc.signature,
                        "named_owner": named, "problem": problem})
        for imp in s.scalars(select(Improvement).where(
                Improvement.state.in_(_OPEN_IMPROVEMENT_STATES))):
            problem = "" if imp.cell in CELLS else f"cell {imp.cell!r} is not an improvement cell"
            out.append({"item": WorkItem(key=f"improvement:{imp.id}", kind="exploration",
                                         owner="" if problem else imp.cell, state=imp.state),
                        "source": "improvement", "ref": imp.id, "named_owner": imp.cell,
                        "problem": problem})
    out.extend(_business_work_items(db, agents, CELLS))
    return out


# #176's other nouns: opportunity, benchmark, listing, experiment, customer issue, owner
# action and teardown finding. Each source names the agent accountable for it and the job
# type that agent must hold for the ownership to be real; the owner action is the owner's.
WORK_SOURCES: dict[str, tuple[str, str, str]] = {
    # source: (accountable agent, job type it must hold, band kind)
    "opportunity": ("market_radar", "radar.score", "new_opportunity"),
    "benchmark": ("orchestrator", "teardown.enforce", "benchmark_change"),
    "listing": ("listing", "listing.seo", "proven_winner"),
    "experiment": ("experiment_steward", "growth.conclude", "exploration"),
    "support_case": ("support", "support.triage", "customer_incident"),
    "teardown_finding": ("orchestrator", "teardown.enforce", "benchmark_change"),
}
OWNER = "owner"
_CLOSED_GAPS = ("covered", "dismissed", "closed", "abandoned", "retired")
_CLOSED_EXPERIMENTS = ("concluded", "stopped", "killed", "decided")
_CLOSED_LISTINGS = ("published", "retired", "withdrawn", "superseded")


def _business_work_items(db, agents: dict, cells: dict) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import (BenchmarkProduct, CoverageGap, Experiment, Listing,
                               OwnerAction, SupportCase, TeardownFinding)

    def entry(source: str, ref, key: str, *, named: str = "", state: str = "open",
              problem_override: str | None = None, kind: str | None = None, **extra) -> dict:
        agent_name, job_type, default_kind = WORK_SOURCES[source]
        named = named or agent_name
        problem = (problem_override if problem_override is not None
                   else _owner_problem(agents.get(named), job_type))
        return {"item": WorkItem(key=key, kind=kind or default_kind,
                                 owner="" if problem else named, state=state),
                "source": source, "ref": ref, "named_owner": named, "problem": problem,
                **extra}

    out: list[dict] = []
    with db.session() as s:
        for g in s.scalars(select(CoverageGap)):
            if g.state in _CLOSED_GAPS:
                continue
            named = str((g.evidence or {}).get("owner") or "")
            out.append(entry("opportunity", g.id, f"opportunity:{g.id}", named=named,
                             state=g.state, arena=g.arena))
        for b in s.scalars(select(BenchmarkProduct)):
            if b.teardown_state == "audited":
                continue
            out.append(entry("benchmark", b.id, f"benchmark:{b.ref}", state=b.teardown_state))
        for li in s.scalars(select(Listing)):
            if li.state in _CLOSED_LISTINGS:
                continue
            out.append(entry("listing", li.id, f"listing:{li.id}", state=li.state,
                             kind="new_opportunity"))
        for e in s.scalars(select(Experiment)):
            if e.result or e.state in _CLOSED_EXPERIMENTS:
                continue
            out.append(entry("experiment", e.id, f"experiment:{e.id}", state=e.state))
        for c in s.scalars(select(SupportCase).where(SupportCase.resolved.is_(False))):
            out.append(entry("support_case", c.id, f"support_case:{c.id}"))
        for a in s.scalars(select(OwnerAction).where(OwnerAction.done == False)):  # noqa: E712
            out.append({"item": WorkItem(key=f"owner_action:{a.id}", kind="housekeeping",
                                         owner=OWNER, state="waiting_for_owner"),
                        "source": "owner_action", "ref": a.id, "named_owner": OWNER,
                        "problem": ""})
        for f in s.scalars(select(TeardownFinding)):
            detail = f.detail or {}
            if f.promoted:
                continue
            if detail.get("promotion_refused"):
                out.append(entry("teardown_finding", f.id, f"teardown_finding:{f.id}",
                                 state="refused_as_hypothesis", problem_override=""))
                continue
            if f.benchmark_ref.startswith("brambleloop:"):
                continue                     # our own audit: a measurement, not work
            out.append(entry("teardown_finding", f.id, f"teardown_finding:{f.id}",
                             problem_override=("recorded and never promoted into an "
                                               "improvement cell (#164)")))
    return out


def _reassign_target(agents: dict, job_type: str) -> str:
    from ..core.models import Authority

    for name in sorted(agents):
        agent = agents[name]
        if agent.authority == Authority.GREEN and not _owner_problem(agent, job_type):
            return name
    return ""


def resolve_orphans(db, *, now: datetime | None = None) -> dict:
    """Find unowned work (#176) and give it an owner, or make it somebody's problem.

    Reassignment is deliberately narrow: a *pending* job moves only to a GREEN agent that
    already holds the permission, so this can never launder a job into authority it did not
    have -- a store publish enqueued by support is not handed to the store operator, it is
    surfaced. An unowned incident gets the quality director. Anything else becomes an
    incident whose evidence says what was unowned and why.
    """
    from sqlalchemy import select

    from ..agents.registry import Registry
    from ..core.models import Incident, Job, JobStatus

    now = now or datetime.now(timezone.utc)
    agents = {a.name: a for a in Registry(db).all()}
    entries = work_items(db)
    unowned = orphans([e["item"] for e in entries])
    unowned_keys = {o["key"] for o in unowned}

    reassigned, surfaced, owned_incidents = [], [], []
    with db.session() as s:
        for entry in entries:
            if entry["item"].key not in unowned_keys:
                continue
            evidence = {k: v for k, v in entry.items() if k != "item"}
            if entry["source"] == "job":
                job = s.get(Job, entry["ref"])
                target = (_reassign_target(agents, job.job_type)
                          if job is not None and job.status == JobStatus.PENDING else "")
                if target:
                    job.agent = target
                    reassigned.append({**evidence, "to": target})
                    continue
            elif entry["source"] == "incident":
                inc = s.get(Incident, entry["ref"])
                owner = DEFAULT_INCIDENT_OWNER
                if inc is not None and owner in agents and agents[owner].enabled:
                    inc.detail = {**(inc.detail or {}), "owner": owner,
                                  "owner_assigned_at": now.isoformat(),
                                  "owner_assigned_by": "swarm.orphans"}
                    owned_incidents.append({**evidence, "to": owner})
                    continue
            signature = f"swarm.orphan:{entry['source']}:{entry['ref']}"
            open_already = s.scalar(select(Incident).where(
                Incident.signature == signature, Incident.resolved.is_(False)))
            if open_already is None:
                s.add(Incident(
                    severity="P2", signature=signature,
                    summary=(f"unowned {entry['source']} {entry['ref']}: "
                             f"{entry['problem']}"),
                    detail={"owner": "orchestrator", "evidence": evidence,
                            "requirement": 176, "raised_at": now.isoformat()}))
            surfaced.append(evidence)

    items = [e["item"] for e in entries]
    return {
        "as_of": now.isoformat(),
        "work_items": len(items),
        "by_source": {src: sum(1 for e in entries if e["source"] == src)
                      for src in ("job", "incident", "improvement", *WORK_SOURCES,
                                  "owner_action")},
        "orphans": unowned,
        "reassigned": reassigned,
        "incident_owners_assigned": owned_incidents,
        "surfaced_as_incident": surfaced,
        "schedule_head": [w.to_dict() for w in schedule(items)[:5]],
    }


# ---------------------------------------------------------------------------
# #186: an idle queue takes the highest-value standing item

# What each standing item *is* in this runtime: the agent and job type that does it, and
# whether it spends model money. Spending items are never fed from idleness -- an idle worker
# buying tournaments to look busy is the spend increase #175 forbids -- and they stay on the
# cadences that already budget for them.
BACKLOG_JOBS: dict[str, tuple[str, str, bool]] = {
    "check the named benchmark for changes": ("market_radar", "mjs.scan", False),
    "score an uncovered arena in the coverage gap queue": ("market_radar", "radar.score",
                                                           False),
    "run a concept tournament for the thinnest seasonal department": (
        "creative_director", "creative.tournament", True),
    "re-verify the continuity restore proof": ("orchestrator", "ops.continuity", False),
    "recompute seasonal launch dates against today": ("orchestrator", "seasonal.sentinel",
                                                      False),
    "mine recent failures for an improvement hypothesis": ("orchestrator",
                                                           "improve.retrospective", False),
    "refresh the Build-2 coverage map from the registry": ("orchestrator", "build.tick",
                                                           False),
}

# A standing item already done this recently is not redone from idleness.
BACKLOG_COOLDOWN = timedelta(hours=6)


def feed_idle(db, queue, *, now: datetime | None = None) -> dict:
    """If the queue is idle, enqueue the highest-value standing items the allocation allows.

    Idempotent (one key per item per cooldown window), bounded (the allocation's
    `backlog_batch`, at most MAX_BACKLOG_PER_TICK), and GREEN-only: the job's agent must be
    GREEN, enabled and permitted, and the item must not spend.
    """
    from sqlalchemy import select

    from ..agents.registry import Registry
    from ..core.models import Authority, Job
    from ..queue.durable import DuplicateJob

    now = now or datetime.now(timezone.utc)
    open_jobs = _open_jobs(db)
    if open_jobs:
        items = [WorkItem(key=f"job:{jid}", kind=band_for(jt)["kind"], owner=agent)
                 for jid, agent, jt, _st in open_jobs]
        return {"idle": False, "enqueued": [], "open_work": len(open_jobs),
                "next": next_work(items)}

    alloc = latest_allocation(db, now=now) or allocate(db, now=now)
    batch = min(MAX_BACKLOG_PER_TICK, int(alloc.get("backlog_batch") or 0))
    lanes = alloc.get("lanes") or {}
    agents = {a.name: a for a in Registry(db).all()}
    window = int(now.timestamp() // BACKLOG_COOLDOWN.total_seconds())

    with db.session() as s:
        recent = {j.job_type for j in s.scalars(select(Job).where(
            Job.finished_at >= now - BACKLOG_COOLDOWN)) if _status(j) == _TERMINAL_OK}

    enqueued, skipped = [], []
    for kind, description in STANDING_BACKLOG:
        if len(enqueued) >= batch:
            break
        agent_name, job_type, spends = BACKLOG_JOBS[description]
        agent = agents.get(agent_name)
        reason = ""
        if spends:
            reason = "spends model money; idleness never buys work"
        elif agent is None or agent.authority != Authority.GREEN:
            reason = f"{agent_name} is not a GREEN agent"
        elif _owner_problem(agent, job_type):
            reason = _owner_problem(agent, job_type)
        elif not (lanes.get(agent_name) or {}).get("active"):
            reason = f"lane {agent_name} is inactive in allocation {alloc.get('allocation_id')}"
        elif job_type in recent:
            reason = f"{job_type} completed within {BACKLOG_COOLDOWN}"
        if reason:
            skipped.append({"description": description, "why": reason})
            continue
        try:
            job = queue.enqueue(agent_name, job_type,
                                {"source": "standing_backlog", "description": description,
                                 "band_kind": kind},
                                idempotency_key=f"backlog:{job_type}:{window}",
                                priority=priority_for(job_type))
            enqueued.append({"description": description, "job_type": job_type,
                             "agent": agent_name, "job_id": job.id,
                             "priority": priority_for(job_type)})
        except DuplicateJob:
            skipped.append({"description": description,
                            "why": "already fed from the backlog this window"})

    return {"idle": True, "enqueued": enqueued, "skipped": skipped, "batch": batch,
            "allocation_id": alloc.get("allocation_id"), "next": next_work([])}
