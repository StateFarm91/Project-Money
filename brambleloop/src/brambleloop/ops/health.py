"""Online means work is progressing, not that HTTP returned 200.

Requirement 185. The requirement writes its own definition into the middle of the sentence
and it is the whole module: *'online' means useful work is progressing, not merely that HTTP
returns 200*. Everything here follows from taking that literally.

A container can serve 200s, keep a worker ticking, keep a scheduler enqueuing, hold an empty
queue and complete nothing for a week. Every signal an ordinary health check reads is green,
because every one of them measures *liveness* -- the process exists and responds -- and none
of them measures *progress*. That is this build's recurring defect wearing its most
respectable costume: the verdict is computed from the absence of failures, and a system that
is doing nothing has no failures at all.

So `progress` is a signal in its own right, with the same standing as the worker's
heartbeat: jobs actually completed in the window. An idle system reports `idle` rather than
`healthy`, and the two are different words on purpose.

The queue's age is the companion signal. A live worker and a job that has been pending for
three hours is not a worker that is alive; it is a worker that is alive and not working,
which reads as healthy on every dashboard that counts processes.

**Self-healing is reported honestly, which turned out to mean reporting that the repairs
already exist elsewhere.** The obvious design gives this sweep a list of fixes to apply, and
writing it produced two findings worth more than the code would have been.

An expired lease is already reclaimed inside the queue's own claim path, on every claim, so
a lease repair here would be a second implementation of something that has never not
happened. And a dead letter is already re-driven once per deploy, which is the right trigger:
a dead letter is fixed by a *code change*, so re-driving it on a fifteen-minute timer re-runs
a failure that nothing has fixed, ninety-six times a day, spending whatever it spends. The
timer is not a safer version of the deploy; it is a retry storm with a health check's name on
it.

So this module does not repair. It detects, it insists on persistence before it escalates,
and it names where each automatic repair actually lives so that "self-healing" is a claim
somebody can check. What it cannot fix at all -- a container restart, a missing credential,
money already spent -- it escalates by name rather than attempting, because a repair that is
announced and does not happen is worse than none: nobody looks.

**Escalation is for persistence, not for a bad minute.** A signal that fails once is a blip;
the same signal failing across consecutive sweeps is a condition, and only the second raises
anything. The escalation carries the observations that produced it rather than a summary,
because the first question anybody asks about an alert is what it actually saw.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

HEALTHY = "healthy"
IDLE = "idle"
DEGRADED = "degraded"
DOWN = "down"
UNKNOWN = "unknown"

# The signals the requirement names. `progress` is first because it is the one that decides
# whether any of the others mean anything.
SIGNALS: dict[str, str] = {
    "progress": "jobs actually completed in the window -- the only signal that is about work",
    "evidence_freshness": ("completed work that produced something this system did not "
                           "already know -- the signal `progress` cannot give"),
    "worker_heartbeat": "the worker ticked recently",
    "scheduler_freshness": "the scheduler has enqueued within its own interval",
    "queue_age": "how long the oldest pending job has waited",
    "database": "the store answers and holds the company's memory",
    "integrations": "the external services this system is allowed to reach",
    "rendered_pages": "a browser worker for pages with no sanctioned endpoint",
    "model_gateway": "a model provider that can serve a request",
    "certificate_freshness": "how long since anything was certified",
    "spend": "the ceilings are on and unbreached",
}

# A worker that has not ticked in this long is not alive.
WORKER_SILENT_AFTER_S = 120
# A scheduler whose last tick is older than this has stopped scheduling.
SCHEDULER_SILENT_AFTER_S = 15 * 60
# A pending job older than this means the queue is not draining, whatever the worker says.
QUEUE_STALLED_AFTER_S = 60 * 60
# How far back to look for a job whose result differed from that cadence's previous run.
#
# Longer than the progress window because several cadences are daily: six hours of
# identical daily results is normal and twelve is not. Chosen so a system producing
# nothing new across two full cycles of its fastest meaningful work is visible as stalled.
EVIDENCE_WINDOW_S = 12 * 60 * 60

# Completed jobs below this in the window means nothing is being achieved.
PROGRESS_WINDOW_S = 6 * 60 * 60
MIN_COMPLETIONS = 1
# Nothing certified in this long is a chain that has stopped producing.
CERTIFICATE_STALE_AFTER_DAYS = 30
# How many consecutive sweeps a signal must fail before it is a condition rather than a blip.
ESCALATE_AFTER_SWEEPS = 3

# Repairs that genuinely happen automatically, and where. Named with their location because
# "self-healing" is otherwise a claim nobody can check, and because both of these were nearly
# reimplemented here before anybody looked.
ALREADY_AUTOMATIC: dict[str, str] = {
    "clear_expired_lease": ("queue.durable.JobQueue.claim reclaims an expired lease on every "
                            "claim, so a holder that died never blocks its job"),
    "requeue_dead_letter": ("the deploy re-drives non-refusal dead letters once (B-327), "
                            "which is the right trigger: a dead letter is fixed by a code "
                            "change, so a fifteen-minute timer would re-run a failure "
                            "nothing has fixed, ninety-six times a day"),
}
CANNOT_REPAIR: dict[str, str] = {
    "restart_container": ("nothing here has process control over its own host, so a restart "
                          "is an escalation rather than an action"),
    "restore_an_integration": "a credential is the owner's to supply",
    "reverse_a_spend": "money that has left cannot be un-spent by a health check",
}


class HealthRefused(ValueError):
    """A signal nobody named, or a repair this system cannot actually perform."""


@dataclass
class Reading:
    """One signal, what it saw, and what it means."""

    signal: str
    state: str
    evidence: dict = field(default_factory=dict)
    why: str = ""

    def __post_init__(self) -> None:
        if self.signal not in SIGNALS:
            raise HealthRefused(f"{self.signal!r} is not a signal: {sorted(SIGNALS)}")

    @property
    def bad(self) -> bool:
        return self.state in (DEGRADED, DOWN)

    def to_dict(self) -> dict:
        return {"signal": self.signal, "state": self.state, "evidence": self.evidence,
                "why": self.why}


def _age_s(when: datetime | None, now: datetime) -> float | None:
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (now - when).total_seconds()


def read(db, *, runner_state: dict | None = None, env: dict[str, str] | None = None,
         now: datetime | None = None, executing_worker: bool = False,
         from_cadence: bool = False) -> list[Reading]:
    """Every signal, read from records rather than from the fact that this code is running.

    `executing_worker` and `from_cadence` are the exception, and they are the strongest
    evidence available rather than a shortcut. If this sweep is itself running inside a
    worker's job, a worker is alive -- that is a fact about the present moment, where a
    heartbeat field is a fact about the last time somebody wrote one. And if the job arrived
    from a cadence, the scheduler enqueued it.

    They exist because the alternative is a false alarm with a long life. `runner.STATE` is
    process-local, so in a split deployment the process reading it is not the process
    writing it, and the heartbeat would read `None` forever -- an hourly "the worker is
    down" incident raised by a worker that is demonstrably running, which is exactly the
    noise this module refuses to produce elsewhere.
    """
    from sqlalchemy import func, select

    from ..core.models import Job, JobStatus, PatternVersion, SpendLimit

    now = now or datetime.now(timezone.utc)
    runner_state = runner_state or {}
    env = env or {}
    readings: list[Reading] = []

    since = now - timedelta(seconds=PROGRESS_WINDOW_S)
    completed = db.scalar(
        select(func.count()).select_from(Job)
        .where(Job.status == JobStatus.DONE)
        .where(Job.finished_at.is_not(None))
        .where(Job.finished_at >= since)) or 0
    readings.append(Reading(
        "progress", HEALTHY if completed >= MIN_COMPLETIONS else IDLE,
        {"completed_in_window": int(completed),
         "window_hours": PROGRESS_WINDOW_S // 3600},
        ("work is being completed" if completed >= MIN_COMPLETIONS else
         "nothing has been completed in the window. Every other signal can be green while "
         "this one is not, because the others measure that the process exists and this one "
         "measures that it is achieving something")))

    # Whether any of that completed work actually produced something new.
    #
    # `progress` counts completed jobs, and on 2026-09-22 that was the whole problem: the
    # system ran 44 cadences and 2,893 jobs across a full day with every liveness signal
    # green, while the gallery cadence re-judged the same twenty-five images every two
    # hours and five other cadences returned `ran: false`. Jobs completing is not evidence
    # being produced, and a health sweep that cannot tell them apart reports a loop
    # spinning in place as healthy indefinitely -- which it did, for about eight hours,
    # at roughly CA$8.50 a day.
    #
    # Measured by comparing each cadence's latest result against its previous one, because
    # that is what "new" means here and it needs no judgement: a cadence returning exactly
    # what it returned last time has told this system nothing it did not know.
    fresh, repeated = _evidence(db, now)
    readings.append(Reading(
        "evidence_freshness",
        HEALTHY if fresh else IDLE,
        {"cadences_with_new_results": sorted(fresh),
         "cadences_repeating_themselves": sorted(repeated),
         "window_hours": EVIDENCE_WINDOW_S // 3600},
        ("work completed and some of it produced results this system had not seen before"
         if fresh else
         "every job that completed in the window returned what its cadence returned last "
         "time. The queue is draining, the worker is alive and nothing is being learned -- "
         "which is what a stalled loop looks like from the inside, and why `progress` "
         "being green is not enough to call this healthy")))

    tick_age = _age_s(_parse(runner_state.get("worker_last_tick")), now)
    if tick_age is None and executing_worker:
        readings.append(Reading(
            "worker_heartbeat", HEALTHY, {"executing_this_sweep": True},
            "this sweep is being executed by a worker, which is stronger evidence than a "
            "heartbeat field: one is the present moment, the other is the last time "
            "somebody wrote to a variable this process may not even share"))
    elif runner_state.get("worker_starting"):
        readings.append(Reading("worker_heartbeat", HEALTHY,
                                {"starting": True},
                                "started and not yet late, which is distinct from dead"))
    elif tick_age is None:
        readings.append(Reading("worker_heartbeat", DOWN, {"last_tick": None},
                                "the worker has never ticked"))
    else:
        readings.append(Reading(
            "worker_heartbeat", HEALTHY if tick_age < WORKER_SILENT_AFTER_S else DOWN,
            {"seconds_since_tick": round(tick_age)},
            "" if tick_age < WORKER_SILENT_AFTER_S else
            f"silent for {round(tick_age)}s against {WORKER_SILENT_AFTER_S}s"))

    sched_age = _age_s(_parse(runner_state.get("scheduler_last_tick")), now)
    if sched_age is None and from_cadence:
        readings.append(Reading(
            "scheduler_freshness", HEALTHY, {"arrived_from_a_cadence": True},
            "this job was enqueued by the scheduler, so it has ticked"))
    elif runner_state.get("worker_starting"):
        readings.append(Reading("scheduler_freshness", HEALTHY, {"starting": True}, ""))
    elif sched_age is None:
        readings.append(Reading("scheduler_freshness", DOWN, {"last_tick": None},
                                "the scheduler has never ticked, so no cadence has fired"))
    else:
        readings.append(Reading(
            "scheduler_freshness",
            HEALTHY if sched_age < SCHEDULER_SILENT_AFTER_S else DEGRADED,
            {"seconds_since_tick": round(sched_age)},
            "" if sched_age < SCHEDULER_SILENT_AFTER_S else
            f"no cadence has been enqueued for {round(sched_age)}s"))

    oldest = db.scalar(
        select(func.min(Job.created_at)).where(Job.status == JobStatus.PENDING))
    queue_age = _age_s(oldest, now)
    readings.append(Reading(
        "queue_age",
        HEALTHY if queue_age is None or queue_age < QUEUE_STALLED_AFTER_S else DEGRADED,
        {"oldest_pending_seconds": None if queue_age is None else round(queue_age)},
        ("nothing is waiting" if queue_age is None else
         "" if queue_age < QUEUE_STALLED_AFTER_S else
         f"the oldest pending job has waited {round(queue_age)}s. A live worker and a job "
         f"nobody has taken is a worker that is alive and not working, which reads as "
         f"healthy on any dashboard that counts processes")))

    try:
        db.scalar(select(func.count()).select_from(SpendLimit))
        readings.append(Reading("database", HEALTHY, {"answers": True}, ""))
    except Exception as exc:  # pragma: no cover - the store failing is the case it is for
        readings.append(Reading("database", DOWN, {"error": str(exc)[:200]},
                                "the company's memory did not answer"))

    for signal, keys in (("integrations", ("ETSY_API_KEY", "ETSY_SHOP_NAME")),
                         ("rendered_pages", ("BRAMBLELOOP_BROWSER_URL",)),
                         ("model_gateway", ("ANTHROPIC_API_KEY",))):
        present = sorted(k for k in keys if str(env.get(k, "")).strip())
        readings.append(Reading(
            signal, HEALTHY if present else UNKNOWN,
            {"configured": present},
            "" if present else
            "not configured, which is a gate rather than a fault: an absent capability is "
            "not a broken one, and reporting it as down would make the dashboard red for a "
            "decision nobody has made yet"))

    newest = db.scalar(select(func.max(PatternVersion.created_at))
                       .where(PatternVersion.certified.is_(True)))
    cert_age = _age_s(newest, now)
    if cert_age is None:
        readings.append(Reading("certificate_freshness", UNKNOWN, {"certified": 0},
                                "nothing has ever been certified, which is a state and not "
                                "a fault"))
    else:
        days = cert_age / 86400
        readings.append(Reading(
            "certificate_freshness",
            HEALTHY if days < CERTIFICATE_STALE_AFTER_DAYS else DEGRADED,
            {"days_since_last_certificate": round(days, 1)},
            "" if days < CERTIFICATE_STALE_AFTER_DAYS else
            f"nothing certified for {round(days)} days: the chain has stopped producing"))

    limits = list(db.scalars(select(SpendLimit)))
    paused = [limit.scope for limit in limits if limit.paused]
    readings.append(Reading(
        "spend", DEGRADED if paused else HEALTHY,
        {"limits": len(limits), "paused": paused},
        f"{paused} paused by a breach" if paused else ""))

    return readings


def _parse(value) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:  # pragma: no cover - a malformed timestamp is not a health state
        return None


def verdict(readings: list[Reading]) -> dict:
    """One word for the whole system, and it is never 'healthy' while nothing is happening."""
    by_signal = {r.signal: r for r in readings}
    down = [r.signal for r in readings if r.state == DOWN]
    degraded = [r.signal for r in readings if r.state == DEGRADED]
    progressing = by_signal.get("progress")
    idle = progressing is not None and progressing.state == IDLE

    if down:
        state, why = DOWN, f"{down} are down"
    elif degraded:
        state, why = DEGRADED, f"{degraded} are degraded"
    elif idle:
        state, why = IDLE, ("every process is alive and nothing is being completed. This is "
                            "not healthy and it is not down, and calling it either is how a "
                            "week of achieving nothing passes a health check")
    else:
        state, why = HEALTHY, "work is being completed and no signal is bad"

    return {"state": state, "why": why, "down": down, "degraded": degraded,
            "readings": [r.to_dict() for r in readings]}


def remediation(db, readings: list[Reading]) -> dict:
    """Where each repair happens, and what has to be escalated instead.

    Deliberately not a list of fixes this sweep applies. Both of the obvious ones already
    happen, one on every queue claim and one on every deploy, and re-driving a dead letter
    on a timer re-runs a failure nothing has fixed.
    """
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    bad = {r.signal for r in readings if r.bad}
    handled: list[dict] = []

    # Deliberate refusals and defects are counted apart. Production holds 134 dead letters
    # and every one of them is a publication refused by shadow mode -- the system working.
    # Reporting those as a repair backlog would put a permanent false number on the console,
    # and a number that is always there is a number nobody reads.
    from ..queue.durable import JobQueue

    dead = list(db.scalars(select(Job).where(Job.status == JobStatus.DEAD)))
    refusals, defects = [], []
    for job in dead:
        error = (job.last_error or "").lower()
        (refusals if any(m in error for m in JobQueue.REFUSAL_MARKERS)
         else defects).append(job)
    if refusals:
        handled.append({"condition": "deliberate_refusals", "count": len(refusals),
                        "repaired_by": "nothing",
                        "how": ("these are jobs the system refused on purpose -- shadow "
                                "mode, or a capability nobody has granted. They are the "
                                "guard working, not a backlog, and re-driving one would be "
                                "asking the same question and getting the same answer")})
    if defects:
        handled.append({"condition": "dead_letters", "count": len(defects),
                        "jobs": [j.id for j in defects][:25],
                        "repaired_by": "deploy", "how": ALREADY_AUTOMATIC["requeue_dead_letter"]})

    if "queue_age" in bad:
        handled.append({"condition": "stalled_queue",
                        "repaired_by": "queue.claim",
                        "how": ALREADY_AUTOMATIC["clear_expired_lease"],
                        "note": ("if the queue is still stalled with leases being reclaimed, "
                                 "the worker is not claiming at all, which is the heartbeat "
                                 "signal's problem rather than the queue's")})

    escalations = []
    if "worker_heartbeat" in bad:
        escalations.append({"signal": "worker_heartbeat",
                            "needs": "restart_container",
                            "why": CANNOT_REPAIR["restart_container"]})
    for signal in ("integrations", "model_gateway", "rendered_pages"):
        if signal in bad:
            escalations.append({"signal": signal, "needs": "restore_an_integration",
                                "why": CANNOT_REPAIR["restore_an_integration"]})
    if "spend" in bad:
        escalations.append({"signal": "spend", "needs": "owner_decision",
                            "why": CANNOT_REPAIR["reverse_a_spend"]})

    return {
        "repaired_elsewhere": handled,
        "repaired_here": [],
        "must_escalate": escalations,
        "note": ("this sweep repairs nothing itself, and that is the finding rather than a "
                 "gap: both obvious repairs already happen -- a lease on every claim, a "
                 "dead letter on every deploy -- and re-driving a dead letter on a timer "
                 "re-runs a failure nothing has fixed. What cannot be fixed at all is "
                 "escalated by name rather than attempted, because a repair that is "
                 "announced and does not happen is worse than none"),
    }


def persistence(history: list[list[Reading]]) -> dict:
    """Which signals have been bad across consecutive sweeps, oldest sweep first.

    A signal that fails once is a blip and a deploy produces several. The same signal failing
    across consecutive sweeps is a condition, and only that is worth waking somebody for.
    """
    runs: dict[str, int] = {}
    for sweep in history:
        bad = {r.signal for r in sweep if r.bad}
        for signal in SIGNALS:
            runs[signal] = runs.get(signal, 0) + 1 if signal in bad else 0
    persistent = sorted(s for s, n in runs.items() if n >= ESCALATE_AFTER_SWEEPS)
    return {
        "consecutive": {s: n for s, n in sorted(runs.items()) if n},
        "persistent": persistent,
        "threshold": ESCALATE_AFTER_SWEEPS,
        "why": ("a signal that fails once is a blip, and a deploy produces several. The same "
                "signal failing across consecutive sweeps is a condition"),
    }


def state() -> dict:
    """What is watched, what may be repaired, and what online is allowed to mean."""
    return {
        "signals": dict(SIGNALS),
        "states": [HEALTHY, IDLE, DEGRADED, DOWN, UNKNOWN],
        "already_automatic": dict(ALREADY_AUTOMATIC),
        "cannot_repair": dict(CANNOT_REPAIR),
        "thresholds": {"worker_silent_after_s": WORKER_SILENT_AFTER_S,
                       "scheduler_silent_after_s": SCHEDULER_SILENT_AFTER_S,
                       "queue_stalled_after_s": QUEUE_STALLED_AFTER_S,
                       "progress_window_s": PROGRESS_WINDOW_S,
                       "certificate_stale_after_days": CERTIFICATE_STALE_AFTER_DAYS,
                       "escalate_after_sweeps": ESCALATE_AFTER_SWEEPS},
        "note": ("Online means useful work is progressing, not that HTTP returned 200. A "
                 "container can serve 200s, tick a worker, run a scheduler, hold an empty "
                 "queue and complete nothing for a week -- every liveness signal green, "
                 "because none of them is about work. An idle system reports idle (#185)."),
    }


def _evidence(db, now) -> tuple[set[str], set[str]]:
    """Which cadences produced a new result in the window, and which repeated themselves.

    Compares each job type's most recent completed result against the one before it. A
    cadence whose two latest runs are identical has produced nothing new, whatever its
    status says; one whose result moved has told this system something.

    Deliberately not a judgement about *value*: "different from last time" is checkable
    without opinion, and the failure this exists to catch -- the same twenty-five images
    judged and charged for every two hours, reporting `judged: 25` each time -- is exactly
    a result that never moves.
    """
    import datetime
    import json

    from sqlalchemy import desc, select

    from ..core.models import Job, JobStatus

    since = now - datetime.timedelta(seconds=EVIDENCE_WINDOW_S)
    rows = list(db.scalars(
        select(Job).where(Job.status == JobStatus.DONE)
        .where(Job.finished_at.is_not(None))
        .where(Job.finished_at >= since)
        .order_by(desc(Job.finished_at)).limit(400)))

    latest: dict[str, list[str]] = {}
    for job in rows:
        seen = latest.setdefault(job.job_type, [])
        if len(seen) < 2:
            seen.append(json.dumps(job.outputs or {}, sort_keys=True, default=str))

    fresh, repeated = set(), set()
    for job_type, results in latest.items():
        # One run in the window is new by construction: there is nothing it repeats.
        if len(results) < 2 or results[0] != results[1]:
            fresh.add(job_type)
        else:
            repeated.add(job_type)
    return fresh, repeated
