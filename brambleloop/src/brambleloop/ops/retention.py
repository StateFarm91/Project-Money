"""What this system may forget, and the evidence it may never forget.

Nothing pruned anything. Measured 2026-09-24: the audit log grows about 4,700 rows a day, the
job table about 900, the dead-letter queue about 21. At those rates the audit log passes 1.7
million rows within a year, on the Postgres instance that dominates the CA$20/month
infrastructure ceiling, and `/api/status` was already measurably slower than `/health` because
of a query over that table. `JobQueue.purge_dead` existed and was called from nowhere in
`src/`, which is the honest state of retention here: a function with no policy behind it.

**The hard part is not deleting; it is knowing what a gate reads.** Several checks in this
system are *lifetime* counts over `audit_log`, and a lifetime count over a pruned table is a
different claim from the one it says it is making:

* `/api/verify`'s `publication_was_actually_attempted_and_refused` requires
  `store.publish_refused > 0` over all time. Prune those rows and the check that stops
  `nothing_published` passing by absence goes red -- and the fix somebody reaches for is to
  weaken it.
* `gateway.image_bench.spent_to_date` **sums every `image.benchmark` row ever written** to
  enforce the owner's cumulative CA$50 authorisation. That figure is cumulative precisely
  because it was once applied per run and four runs each stayed inside a budget approved once.
  Pruning those rows would rebuild the defect the owner's decision was made to close: a
  ceiling that forgets what it has spent.
* `scale.confidence` counts `continuity.verified` and `store.publish_refused` over all time,
  and `jobs_done >= 100` is one of its gate conditions.
* Two dozen readers ask for the *latest* row of one action. An action whose every row is older
  than the horizon would answer "never happened" instead of "happened, a while ago".

So retention is expressed as three rules rather than one horizon:

1. **Protected actions are never deleted at any age.** Each entry names the reader that makes
   it evidence, because a protected list with no reasons is a list somebody prunes.
2. **The most recent rows of every action survive**, protected or not, so no "latest row"
   reader can be made to answer differently by retention.
3. **Everything else goes after the horizon.**

`KNOWN_READ_ACTIONS` is the other half of that. Every action name the codebase reads by name
is listed with how it is read, and a test scans `src/` and fails when a reader names an action
this module has not heard of. That is the check that matters in a year: the danger is not this
policy, it is the next lifetime aggregate somebody writes over a table that is now pruned.

**Cost rows are never touched.** `cost_entries` is what every ceiling in the company is
computed from and what the ledger reconciles against; it grows at about 1,200 rows a month,
which is not a problem this decade. A retention policy that pruned the money would be a
retention policy that lowered a ceiling.

**A job row that other evidence points at is not deletable.** `audit_log.job_id`,
`cost_entries.job_id` and `spend_reservations.job_id` are real foreign keys, so deleting such a
job either raises or -- worse, on a database with the constraint off -- orphans the evidence.
Those jobs are kept and counted, and in practice that is most of them, which is a finding
rather than a disappointment: the job table cannot be pruned much without deleting audit
evidence, and the audit evidence is the part with a policy.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# How long an ordinary audit row is kept. Ninety days covers every window any signal in this
# system reads (the longest is `improve.weekly`'s seven days and the maturity reader's
# thirty), with a wide margin, and it is long enough that a quarter's retrospective can still
# be argued from rows rather than from summaries.
AUDIT_RETENTION_DAYS = 90

# Kept per action whatever their age, so a reader that asks for the most recent row of an
# action cannot be given a different answer by retention. Two rather than one: some readers
# compare the latest against the one before it.
KEEP_PER_ACTION = 2

# Finished jobs. This has to exceed the longest cadence period, and that is arithmetic rather
# than taste: the scheduler's idempotency key is `cadence:<name>:<window>` where the window is
# `now // period`, so deleting the job that holds a key whose window is still open lets the
# cadence run twice in one window. The longest period is `strategy_review` at thirty days, so
# forty-five leaves fifteen days of margin, and a test computes the longest period from
# `worker.CADENCES` and refuses a horizon that does not clear it.
JOB_RETENTION_DAYS = 45

# Kept per job type regardless of age, so `build2.maturity`'s `jobs_seen` -- the set of job
# types this company has ever run -- cannot be narrowed by retention.
KEEP_PER_JOB_TYPE = 3

# `scale.confidence` gates on `jobs_done >= 100` over all time. Retention must not be able to
# make a true claim false, so it stops well above the threshold rather than at it.
JOBS_DONE_FLOOR = 1000

# Dead letters. Only deliberate refusals are ever removed -- see `prune_dead_letters`.
DEAD_LETTER_RETENTION_DAYS = 90


# Every audit action this codebase reads by name, and how it is read. The value is what decides
# whether it can be pruned:
#
#   lifetime_total  a count or sum over *all* rows. Pruning changes the answer. Protected.
#   latest          the most recent row. Rule 2 keeps it whatever the horizon.
#   windowed        read inside a bounded recent window. The horizon is far outside it.
#
# `unknown_read_actions` below reads the action literals out of `src/` -- from equality tests
# and membership tests against the action column -- and a test fails on one that is not here.
# The point is not this list's current contents; it is that the next lifetime aggregate
# somebody writes has to come here and make a decision.
KNOWN_READ_ACTIONS: dict[str, tuple[str, str]] = {
    "store.published": ("lifetime_total",
                        "app.main /api/verify `nothing_published` counts all of them"),
    "store.publish_refused": ("lifetime_total",
                              "app.main /api/verify "
                              "`publication_was_actually_attempted_and_refused`, and "
                              "scale.confidence, both count all of them"),
    "continuity.verified": ("lifetime_total",
                            "scale.confidence counts every restore ever proved"),
    "continuity.failed": ("latest", "app.main /api/continuity reads the last proof"),
    "image.benchmark": ("lifetime_total",
                        "gateway.image_bench.spent_to_date sums these to enforce the "
                        "owner's cumulative CA$50 authorisation"),
    "image.reference_probe": ("lifetime_total",
                              "gateway.image_bench.spent_to_date sums these too "
                              "(images.REFERENCE_PROBE_ACTION)"),
    "image.benchmark_blocked": ("latest", "gateway.image_bench.last_run"),
    "image.benchmark_capped": ("latest", "gateway.image_bench.last_run"),
    "model.frozen": ("lifetime_total",
                     "visual.freeze and visual.bible read the canonical identity freeze, "
                     "which is permanent provenance and not re-derivable"),
    "design.provenance": ("lifetime_total",
                          "ops.artefacts proves what each derived artefact was made from; "
                          "a missing row reads as unproven, which blocks publication"),
    "model.probe": ("latest", "gateway.anthropic.provider_usable reads a successful call"),
    "model.analysis": ("windowed", "gateway.routing reads recent analyses"),
    "ops.health": ("latest", "runtime.release reads the last sweep"),
    "ops.requeued_for_commit": ("latest", "runtime.pipeline reads the last re-drive"),
    "improve.nightly": ("latest", "runtime.release reads the last nightly"),
    "improve.promoted": ("windowed", "improve.tiers and improve.roi read recent promotions"),
    "creative.blinded": ("latest", "runtime.release reads the last blinded run"),
    "creative.blind_review": ("latest", "runtime.release reads the last review"),
    "concept.autopsy": ("windowed", "runtime.pipeline reads recent autopsies"),
    "seasonal.cycle_proof": ("latest", "runtime.release reads the last cycle proof"),
    "etsy.probe": ("latest", "intel.etsy_public reads the last probe"),
    "runtime.started": ("windowed",
                        "ops.health.container_starts reads a 24-hour window to tell a "
                        "restart from a deploy"),
}

PROTECTED_ACTIONS: frozenset[str] = frozenset(
    action for action, (how, _why) in KNOWN_READ_ACTIONS.items() if how == "lifetime_total")


class RetentionRefused(ValueError):
    """A retention run that would have deleted evidence something reads."""


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def unknown_read_actions(source_root=None) -> list[str]:
    """Audit actions the code reads by name that this module has no decision about.

    Read out of the source rather than maintained by hand, because a list somebody has to
    remember to update is wrong exactly when new work lands. The risk this guards is specific:
    somebody adds a lifetime count over `audit_log` in six months and retention, which is
    correct today, silently starts lowering it.
    """
    import re
    from pathlib import Path

    root = Path(source_root) if source_root else Path(__file__).resolve().parents[1]
    named: set[str] = set()
    equality = re.compile(r'AuditLog\.action\s*==\s*["\']([a-zA-Z0-9_.]+)["\']')
    inside = re.compile(r'AuditLog\.action\.in_\(\s*\(([^)]*)\)', re.S)
    literal = re.compile(r'["\']([a-zA-Z0-9_.]+)["\']')
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        named.update(equality.findall(text))
        for group in inside.findall(text):
            named.update(literal.findall(group))
    return sorted(a for a in named if a not in KNOWN_READ_ACTIONS)


def audit_plan(db, *, now: datetime | None = None,
               days: int = AUDIT_RETENTION_DAYS,
               keep_per_action: int = KEEP_PER_ACTION) -> dict:
    """Which audit rows are deletable, and what is being kept and why.

    A plan rather than a delete, so the decision can be read before it is taken and so
    `/api/status` can report what retention would do without doing it.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(1, int(days)))
    deletable: list[int] = []
    kept_protected = 0
    kept_recent_per_action = 0
    seen_per_action: dict[str, int] = {}
    with db.session() as s:
        # Newest first, because rule 2 is "the most recent rows of every action survive" and
        # that is only cheap to decide in this order.
        rows = list(s.execute(select(AuditLog.id, AuditLog.action, AuditLog.at)
                             .order_by(desc(AuditLog.id))).all())
    for row_id, action, at in rows:
        # Rule 2 first: the newest rows of every action survive whatever the horizon says,
        # because a "latest row" reader must not be able to get a different answer from
        # retention than from the truth.
        seen = seen_per_action.get(action, 0)
        if seen < max(1, int(keep_per_action)):
            seen_per_action[action] = seen + 1
            kept_recent_per_action += 1
            continue
        if action in PROTECTED_ACTIONS:
            kept_protected += 1
            continue
        if (_aware(at) or now) >= cutoff:
            continue
        deletable.append(row_id)
    return {
        "table": "audit_log",
        "total_rows": len(rows),
        "deletable": len(deletable),
        "deletable_ids": deletable,
        "kept_because_protected": kept_protected,
        "kept_because_recent_for_their_action": kept_recent_per_action,
        "horizon_days": int(days),
        "cutoff": cutoff.isoformat(),
        "protected_actions": sorted(PROTECTED_ACTIONS),
        "why_protected": {a: KNOWN_READ_ACTIONS[a][1] for a in sorted(PROTECTED_ACTIONS)},
        "unknown_read_actions": unknown_read_actions(),
        "why": ("a lifetime count over a pruned table is a different claim from the one it "
                "says it is making. These actions are counted or summed over all time by a "
                "gate, so they are kept at any age"),
    }


def job_plan(db, *, now: datetime | None = None, days: int = JOB_RETENTION_DAYS,
             keep_per_type: int = KEEP_PER_JOB_TYPE,
             done_floor: int = JOBS_DONE_FLOOR) -> dict:
    """Which finished jobs are deletable, and every reason the rest are not.

    Four reasons a finished job stays, and they are different faults if any of them is got
    wrong:

    * It is inside the horizon, which must clear the longest cadence period or a cadence's
      idempotency key is freed while its window is still open.
    * Something points at it. `audit_log.job_id`, `cost_entries.job_id` and
      `spend_reservations.job_id` are foreign keys, so deleting the job breaks the evidence or
      orphans it.
    * It is one of the most recent of its job type, so the set of job types this company has
      ever run (`build2.maturity`) cannot be narrowed by retention.
    * Removing it would take the lifetime count of completed jobs below the floor that
      `scale.confidence`'s gate reads. Retention must not be able to make a true claim false.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog, CostEntry, Job, JobStatus, SpendReservation

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(1, int(days)))
    with db.session() as s:
        referenced: set[int] = set()
        for table in (AuditLog, CostEntry, SpendReservation):
            referenced.update(
                job_id for (job_id,) in s.execute(
                    select(table.job_id).where(table.job_id.is_not(None))).all())
        rows = list(s.execute(
            select(Job.id, Job.job_type, Job.status, Job.finished_at, Job.created_at)
            .order_by(desc(Job.id))).all())

    done_total = sum(1 for _i, _t, status, _f, _c in rows if status == JobStatus.DONE)
    deletable: list[int] = []
    kept: dict[str, int] = {"referenced": 0, "recent_for_their_type": 0,
                            "inside_horizon": 0, "not_finished": 0,
                            "protecting_the_done_floor": 0}
    seen_per_type: dict[str, int] = {}
    surviving_done = done_total
    for job_id, job_type, status, finished_at, created_at in rows:
        seen = seen_per_type.get(job_type, 0)
        if seen < max(1, int(keep_per_type)):
            seen_per_type[job_type] = seen + 1
            kept["recent_for_their_type"] += 1
            continue
        if status not in (JobStatus.DONE, JobStatus.CANCELLED):
            # A dead letter is not retention's business -- `prune_dead_letters` has its own
            # much stricter rule -- and a pending or running job is live work.
            kept["not_finished"] += 1
            continue
        when = _aware(finished_at) or _aware(created_at) or now
        if when >= cutoff:
            kept["inside_horizon"] += 1
            continue
        if job_id in referenced:
            kept["referenced"] += 1
            continue
        if status == JobStatus.DONE and surviving_done - 1 < int(done_floor):
            kept["protecting_the_done_floor"] += 1
            continue
        if status == JobStatus.DONE:
            surviving_done -= 1
        deletable.append(job_id)

    return {
        "table": "jobs",
        "total_rows": len(rows),
        "done_rows": done_total,
        "deletable": len(deletable),
        "deletable_ids": deletable,
        "kept": kept,
        "surviving_done_rows": surviving_done,
        "done_floor": int(done_floor),
        "horizon_days": int(days),
        "cutoff": cutoff.isoformat(),
        "why_referenced_are_kept": (
            "audit_log.job_id, cost_entries.job_id and spend_reservations.job_id are foreign "
            "keys. Deleting the job breaks the evidence that points at it, and the evidence "
            "is the part with a policy"),
        "why_the_floor_exists": (
            "scale.confidence gates on 100 completed jobs over all time. Retention must not "
            "be able to make a true claim false, so it stops far above the threshold"),
    }


def dead_letter_plan(db, *, now: datetime | None = None,
                     days: int = DEAD_LETTER_RETENTION_DAYS) -> dict:
    """Which dead letters may be removed: the deliberate refusals, and only those.

    "The one thing a dead-letter queue must never do is lose a failure nobody looked at" is
    `purge_dead`'s own rule and this does not soften it. A shadow-mode publication refusal and
    a replica standing aside for the build that can run it are the system working -- there are
    149 of them in production and every one is a refusal -- and after three months they are a
    fact nobody is going to act on. A defect is never pruned at any age.
    """
    from sqlalchemy import select

    from ..core.models import AuditLog, CostEntry, Job, JobStatus, SpendReservation
    from ..queue.durable import deliberate_refusal

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(1, int(days)))
    with db.session() as s:
        referenced: set[int] = set()
        for table in (AuditLog, CostEntry, SpendReservation):
            referenced.update(
                job_id for (job_id,) in s.execute(
                    select(table.job_id).where(table.job_id.is_not(None))).all())
        rows = list(s.execute(
            select(Job.id, Job.job_type, Job.last_error, Job.finished_at, Job.created_at)
            .where(Job.status == JobStatus.DEAD)).all())

    deletable: list[int] = []
    kept = {"is_a_defect": 0, "inside_horizon": 0, "referenced": 0}
    for job_id, job_type, last_error, finished_at, created_at in rows:
        if not deliberate_refusal(job_type, last_error or ""):
            kept["is_a_defect"] += 1
            continue
        when = _aware(finished_at) or _aware(created_at) or now
        if when >= cutoff:
            kept["inside_horizon"] += 1
            continue
        if job_id in referenced:
            kept["referenced"] += 1
            continue
        deletable.append(job_id)
    return {
        "table": "jobs (dead)",
        "total_rows": len(rows),
        "deletable": len(deletable),
        "deletable_ids": deletable,
        "kept": kept,
        "horizon_days": int(days),
        "cutoff": cutoff.isoformat(),
        "classified_by": "queue.durable.deliberate_refusal",
        "why": ("only refusals working correctly are ever removed. A dead letter that is a "
                "defect is work the company still owes and is kept at any age"),
    }


def plan(db, *, now: datetime | None = None) -> dict:
    """Everything retention would do, without doing any of it."""
    now = now or datetime.now(timezone.utc)
    audit = audit_plan(db, now=now)
    jobs = job_plan(db, now=now)
    dead = dead_letter_plan(db, now=now)
    from ..finance import reservations

    return {
        "at": now.isoformat(),
        "audit_log": {k: v for k, v in audit.items() if k != "deletable_ids"},
        "jobs": {k: v for k, v in jobs.items() if k != "deletable_ids"},
        "dead_letters": {k: v for k, v in dead.items() if k != "deletable_ids"},
        "reservations_kept_hours": reservations.KEEP_RELEASED_HOURS,
        "never_touched": {
            "cost_entries": ("every ceiling in the company is computed from these and the "
                             "ledger reconciles against them. About 1,200 rows a month"),
            "ledger": "actual money events, each with an evidence reference",
            "release certificates and pattern versions": "the product's provenance",
        },
        "why_a_plan_exists": (
            "a deletion nobody can read before it happens is a deletion nobody can argue "
            "with afterwards"),
    }


def apply(db, *, now: datetime | None = None, dry_run: bool = False) -> dict:
    """Run the policy. Returns what it removed and everything it declined to remove.

    Refuses outright if the source names an audit action this module has no decision about:
    that means somebody added a reader and retention does not know whether pruning its rows
    changes its answer, which is exactly the state in which a retention run does damage.
    """
    from ..core.models import AuditLog, Job
    from ..finance import reservations

    now = now or datetime.now(timezone.utc)
    unknown = unknown_read_actions()
    if unknown:
        raise RetentionRefused(
            f"these audit actions are read by name in `src/` and this module has no "
            f"retention decision about them: {unknown}. Add each to "
            f"`KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned "
            f"table is a different claim from the one it says it is making, and that is the "
            f"mistake this refusal exists to prevent")

    audit = audit_plan(db, now=now)
    jobs = job_plan(db, now=now)
    dead = dead_letter_plan(db, now=now)
    swept = reservations.sweep(db, now=now)

    removed = {"audit_log": 0, "jobs": 0, "dead_letters": 0}
    if not dry_run:
        with db.session() as s:
            for row_id in audit["deletable_ids"]:
                row = s.get(AuditLog, row_id)
                if row is not None:
                    s.delete(row)
                    removed["audit_log"] += 1
            for row_id in list(jobs["deletable_ids"]) + list(dead["deletable_ids"]):
                row = s.get(Job, row_id)
                if row is not None:
                    s.delete(row)
                    removed["jobs" if row_id in set(jobs["deletable_ids"])
                            else "dead_letters"] += 1

    return {
        "at": now.isoformat(),
        "dry_run": bool(dry_run),
        "removed": removed,
        "reservations": swept,
        "audit_log": {k: v for k, v in audit.items() if k != "deletable_ids"},
        "jobs": {k: v for k, v in jobs.items() if k != "deletable_ids"},
        "dead_letters": {k: v for k, v in dead.items() if k != "deletable_ids"},
    }


def state() -> dict:
    """The policy as a readable object, for the console and for a future session."""
    return {
        "audit_retention_days": AUDIT_RETENTION_DAYS,
        "keep_per_action": KEEP_PER_ACTION,
        "job_retention_days": JOB_RETENTION_DAYS,
        "keep_per_job_type": KEEP_PER_JOB_TYPE,
        "jobs_done_floor": JOBS_DONE_FLOOR,
        "dead_letter_retention_days": DEAD_LETTER_RETENTION_DAYS,
        "protected_actions": sorted(PROTECTED_ACTIONS),
        "known_read_actions": {a: {"read_as": how, "reader": why}
                               for a, (how, why) in sorted(KNOWN_READ_ACTIONS.items())},
        "never_pruned": ["cost_entries", "ledger", "pattern_versions",
                         "dead letters that are defects"],
        "measured_growth_2026_09_24": {"audit_log_per_day": 4700, "jobs_per_day": 900,
                                       "dead_letters_per_day": 21},
        "why": ("at 4,700 audit rows a day nothing pruned anything, and the database is the "
                "main cost driver under the CA$20/month infrastructure ceiling. The horizon "
                "is the easy half; knowing which rows a gate counts over all time is the "
                "half that decides whether retention is safe"),
    }
