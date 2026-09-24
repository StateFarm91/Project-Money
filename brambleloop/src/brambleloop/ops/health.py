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
    # Named for what it measures rather than for what it was assumed to measure. It read
    # `paused` on a table with no rows and reported the ceilings healthy; the description
    # said "the ceilings are on" and the code could not see whether any was on at all.
    "spend": ("the scoped limits, the monthly model ceiling and each agent's daily "
              "ceiling, with what each one is actually at"),
    "disk": ("free space where this system writes, and the temporary directories its own "
             "handlers left behind"),
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
    "reclaim_disk": ("a temporary directory may belong to a job that is still writing into "
                     "it, so deleting it here would lose that job's work. The durable fix "
                     "is at the call sites, which must use `TemporaryDirectory` rather than "
                     "`mkdtemp`"),
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

    readings.append(_spend(db, now))

    readings.append(_disk(runner_state))

    return readings


def _spend(db, now: datetime) -> Reading:
    """The ceilings that are actually on, and what they are actually at.

    This signal is described as "the ceilings are on and unbreached" and it used to measure
    one thing: that no `SpendLimit` row carries `paused`. Nothing in this system ever calls
    `SpendGuard.set_limit`, so there are no rows -- production reported
    `{"limits": 0, "paused": []}` and `healthy` on 2026-09-24. The ceiling was green because
    there was no ceiling. That is this build's named defect exactly: a verdict computed from
    the absence of evidence, and the more ceilings anybody forgets to configure, the greener
    it gets.

    So the signal now reads the ceilings that exist and bind:

      * the `SpendLimit` scopes, if any, and whether a breach paused one. The count is in
        the evidence so "none configured" can never again look like "none breached".
      * the monthly model ceiling, which is the live control -- the one `check_budget`
        refuses against before every call.
      * each agent's declared daily ceiling against what that agent has actually spent
        today, which nothing else in this system looks at.

    Degraded means a ceiling was crossed, not that it is being approached: approaching is
    `spend_policy.escalation`'s job and it reports with evidence at four-fifths. A health
    signal that goes yellow on a normal working day is a health signal people turn off.
    """
    from sqlalchemy import select as _select

    from ..core.models import Agent, CostEntry, SpendLimit

    limits = list(db.scalars(_select(SpendLimit)))
    paused = [limit.scope for limit in limits if limit.paused]

    from ..finance.spend_policy import ceiling_cad
    from ..gateway.routing import COST_KIND

    month_spend = 0.0
    today_by_agent: dict[str, float] = {}
    today = now.date()
    for row in db.scalars(_select(CostEntry)):
        at = row.at if row.at.tzinfo else row.at.replace(tzinfo=timezone.utc)
        amount = float(row.amount_cad or 0.0)
        if row.kind == COST_KIND and (at.year, at.month) == (now.year, now.month):
            month_spend += amount
        if at.date() == today:
            today_by_agent[row.agent or ""] = today_by_agent.get(row.agent or "", 0.0) + amount

    ceiling = ceiling_cad()
    over_agents = []
    for agent in db.scalars(_select(Agent)):
        spent = round(today_by_agent.get(agent.name, 0.0), 4)
        if agent.daily_cost_ceiling_cad > 0 and spent > agent.daily_cost_ceiling_cad:
            over_agents.append({"agent": agent.name, "spent_today_cad": spent,
                                "daily_ceiling_cad": agent.daily_cost_ceiling_cad})

    month_spend = round(month_spend, 6)
    over_month = month_spend > ceiling
    evidence = {
        "limits": len(limits),
        "paused": paused,
        "model_spend_this_month_cad": month_spend,
        "model_ceiling_cad": ceiling,
        "share_of_model_ceiling": round(month_spend / ceiling, 4) if ceiling else None,
        "agents_over_their_daily_ceiling": over_agents,
        "what_this_cannot_see": (
            "spend that was never written to a cost row. Every ceiling here is computed "
            "from those rows, so a call that bills and records nothing is invisible to all "
            "of them"),
    }
    reasons = []
    if paused:
        reasons.append(f"{paused} paused by a breach")
    if over_month:
        reasons.append(f"model spend CA${month_spend:.2f} is over its CA${ceiling:.2f} "
                       f"monthly ceiling")
    if over_agents:
        reasons.append("; ".join(
            f"{o['agent']} has spent CA${o['spent_today_cad']:.2f} today against a daily "
            f"ceiling of CA${o['daily_ceiling_cad']:.2f}" for o in over_agents))
    if not limits:
        evidence["no_scope_is_configured"] = (
            "no SpendLimit row exists, so the paused check above has nothing to look at. "
            "It is not evidence that scoped spending is safe; it is evidence that no "
            "scoped ceiling has been set. The live controls are the two below it")
    return Reading("spend", DEGRADED if reasons else HEALTHY, evidence, "; ".join(reasons))


# How little free space counts as close to failing, in gigabytes.
#
# Absolute rather than a share, and that is the correction rather than a convenience. A share
# threshold was written first and it was the wrong instrument twice over: ten percent of a
# 270 GB volume is 27 GB, which is not a risk to a workload whose largest write is a
# few-megabyte render, and ten percent of a small container volume is a few hundred
# megabytes, which is. A share answers "how full is this disk" when the question is "is
# there room for the next write". The share is kept in the evidence because it is what a
# person reads, and the verdict is taken from the gigabytes because that is what fails.
DISK_LOW_FREE_GB = 1.0


def _disk(runner_state: dict) -> Reading:
    """Free space where the running container writes, and the temp directories it left.

    Added because none of the other ten signals is about storage, and the failure it catches
    has already happened once in this repository: the suite left 37,284 temporary
    directories and 29 GB behind, and eleven suites failed on "No space left on device" with
    no code change behind it. The production handlers use the same call that caused it --
    `tempfile.mkdtemp`, which never removes what it creates -- in the continuity, offsite,
    tournament, owned-asset, reference-pack and image-generation paths, and those run on a
    cadence forever. Nothing could see the result, which is the part worth fixing first: a
    filling disk is a slow failure that looks like nothing at all until every write fails at
    once.

    Read from `runner_state` rather than from this process's own filesystem, for the same
    reason the worker heartbeat is: the process answering an HTTP request is not necessarily
    the container doing the work, and a sweep that measures whichever machine happens to be
    running it is a check that cannot see the thing it exists to measure. Absent means
    `unknown`, never `healthy` -- an unreported disk is an unmeasured disk.

    It removes nothing. Deleting a temporary directory another process is writing into is
    how a running job loses the render it is holding.
    """
    facts = (runner_state or {}).get("disk")
    if not isinstance(facts, dict) or not facts:
        return Reading("disk", UNKNOWN, {"reported": False},
                       "the running process did not report its disk, so this is unmeasured "
                       "rather than fine")

    reasons: list[str] = []
    state = HEALTHY
    for name, reading in (facts.get("filesystems") or {}).items():
        free_gb = reading.get("free_gb")
        if free_gb is None:
            state = UNKNOWN if state == HEALTHY else state
            continue
        if free_gb < DISK_LOW_FREE_GB:
            state = DEGRADED
            reasons.append(f"{name} has {free_gb:.2f} GB free, under the "
                           f"{DISK_LOW_FREE_GB:.2f} GB this workload needs to keep writing")
    return Reading("disk", state, dict(facts), "; ".join(reasons))


# Prefixes this system's own handlers pass to `tempfile.mkdtemp`. Listed rather than counting
# everything in the temp directory, because the neighbours' litter is not this company's
# signal, and a number that includes it is a number nobody can act on.
TEMP_PREFIXES: tuple[str, ...] = (
    "continuity-", "continuity-download-", "offsite-", "tournament-", "owned-asset-",
    "reference-pack-", "generated-", "motif-chart-", "brambleloop-run-")


def disk_facts() -> dict:
    """Measure this container's disk. Called by the process that owns it, never by a reader.

    Every value is a measurement or is absent. A filesystem that cannot be read contributes
    an error rather than a reassuring number.
    """
    import os
    import shutil
    import tempfile

    tmp = tempfile.gettempdir()
    roots = {"tmp": tmp,
             "artifacts": os.environ.get("BRAMBLELOOP_ARTIFACT_DIR", "artifacts")}
    filesystems: dict[str, dict] = {}
    for name, path in roots.items():
        try:
            usage = shutil.disk_usage(path if os.path.isdir(path) else tmp)
        except OSError as exc:  # pragma: no cover - an unreadable mount is not a disk state
            filesystems[name] = {"error": str(exc)[:120]}
            continue
        filesystems[name] = {
            "free_gb": round(usage.free / 1e9, 3),
            "total_gb": round(usage.total / 1e9, 3),
            "free_share": round(usage.free / usage.total, 4) if usage.total else None}

    counts: dict[str, int] = {}
    try:
        names = os.listdir(tmp)
    except OSError:  # pragma: no cover - an unreadable temp directory is not a disk state
        names = []
    for entry in names:
        for prefix in TEMP_PREFIXES:
            if entry.startswith(prefix):
                counts[prefix] = counts.get(prefix, 0) + 1
                break
    return {
        "filesystems": filesystems,
        "temp_dirs_left_behind": sum(counts.values()),
        "temp_dir_prefixes": dict(sorted(counts.items())),
        "why_they_are_counted": (
            "`tempfile.mkdtemp` never removes what it creates, and the handlers that use it "
            "run on a cadence. Counted rather than cleaned: deleting a directory another "
            "process is writing into loses that job's work"),
    }


BOOT_ACTION = "runtime.started"


def container_starts(db, *, now: datetime | None = None, hours: int = 24) -> dict:
    """How often this container has been replaced, and how many of those were not deploys.

    The distinction is the whole value. A start on a commit an earlier start in the window
    already used is a *restart* -- the container died and came back on the same code -- and
    a start on a new commit is a deploy. `runner.STATE.worker_restarts` cannot tell them
    apart and cannot even see either, because it resets with the process it counts in.

    Reads rows, so it answers across container replacements, which is the only way a
    question about container replacements can be answered.
    """
    from sqlalchemy import select

    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    rows = [r for r in db.scalars(
        select(AuditLog).where(AuditLog.action == BOOT_ACTION).order_by(AuditLog.id))
        if (_age_s(r.at, now) or 0) <= hours * 3600]
    commits: list[str] = []
    repeats = 0
    for row in rows:
        commit = str((row.detail or {}).get("commit") or "")
        if commit and commit in commits:
            repeats += 1
        commits.append(commit)
    return {
        "window_hours": hours,
        "since": since.isoformat(),
        "starts": len(rows),
        "restarts_on_a_commit_already_seen": repeats,
        "distinct_commits": len({c for c in commits if c}),
        "why": ("a start on a commit an earlier start already used is the container being "
                "replaced without a deploy, which is the case a restart count exists for. "
                "A start on a new commit is a deploy"),
    }


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
    # `deliberate_refusal`, not `JobQueue.REFUSAL_MARKERS`. They answer different questions
    # and this is the first one: *is this dead letter a defect somebody has to explain?*
    # The markers answer the second -- *may this be re-driven?* -- and the two differ on a
    # real row. A job that stood aside for the build that can run it is not a defect (the
    # refusal worked) and IS re-drivable (the right build should take it). Reading the
    # re-drive rule as the defect rule put that row on this console as a repair backlog and
    # on `/api/verify` as nothing to explain, at the same moment, on 2026-09-24.
    from ..queue.durable import deliberate_refusal

    dead = list(db.scalars(select(Job).where(Job.status == JobStatus.DEAD)))
    refusals, defects = [], []
    for job in dead:
        (refusals if deliberate_refusal(job.job_type, job.last_error or "")
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
    if "disk" in bad:
        escalations.append({"signal": "disk", "needs": "reclaim_disk",
                            "why": CANNOT_REPAIR["reclaim_disk"]})

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
                       "escalate_after_sweeps": ESCALATE_AFTER_SWEEPS,
                       "disk_low_free_gb": DISK_LOW_FREE_GB},
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
