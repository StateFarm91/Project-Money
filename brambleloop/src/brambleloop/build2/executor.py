"""The build loop, in the database rather than in a conversation.

The master intent asks for an autonomous build executor that never idles: owner-blocked work
is parked, the highest-value unblocked requirement continues, and losing a session is not
losing the build. This module is the machinery for that, and it exists because the previous
arrangement worked for the wrong reason.

Build 2 did route around the missing Etsy credential — eight milestones landed while it was
unavailable, and no requirement waited on it. But the thing that routed around it was a
session. The dependency graph was prose in BUILD_STATE, the priority queue was judgement, and
the parking decision was made once and remembered by whoever was in the conversation. All of
that evaporates when the session does. Autonomy that depends on a particular process staying
alive is not autonomy; it is a person with extra steps, and the failure is invisible right up
until the moment it matters.

So four things move into Postgres, where the deployed worker can read them:

**The graph.** Every requirement is a row with its dependencies and a derived state. `ready`
means nothing is stopping it. `blocked` means a requirement it needs is unfinished. `parked`
means the owner has to do something first — and parking is the interesting one.

**Parking is checkable or it is refused.** A task may only be parked on a *capability* whose
availability the code can test, and the capability is the one the access registry already
defines. "Waiting on the owner" as free text would make parking a place to put anything hard,
and a queue that can absorb its own difficulties never reports being blocked and never
finishes. Unparking is automatic: the capability becomes available, the task becomes ready,
and nothing has to remember.

**Never-idle is measured in requirements, not in ticks.** A loop that always has something to
do is trivially satisfiable by inventing work, which is the failure `swarm.next_work` already
names for agents and which applies with more force here. The watchdog therefore asks a harder
question than "is the loop running": it asks whether anything has been *completed* recently,
and it distinguishes idle-because-blocked from idle-because-nobody-looked. Those need
opposite responses and they look identical from outside.

**An owner action never stops the queue.** It becomes a row with a capability attached, the
requirements that wait on it are parked, and the loop moves to the next ready thing. The
owner's queue and the build queue are separate objects with one link between them, so the
build cannot be held up by a decision nobody has made yet.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import requirements as reg

READY = "ready"
BLOCKED = "blocked"
PARKED = "parked"
IN_PROGRESS = "in_progress"
DONE = "done"

STATES: tuple[str, ...] = (READY, BLOCKED, PARKED, IN_PROGRESS, DONE)

# Which registry statuses produce a schedulable task at all. `data_gated` requirements are
# not parked on a capability -- no credential makes a customer exist -- so they are held
# separately and never counted as executable.
SCHEDULABLE = (reg.PARTIAL, reg.MISSING)

# Sections ordered by how much of the business depends on them. A priority that is only the
# requirement number builds the document in order, which is the order it was written rather
# than the order it is needed.
SECTION_WEIGHT: dict[str, float] = {
    "MJsOffTheHookDesigns priority mission": 5.0,
    "Adversarial commercial + policy audit": 12.0,
    "Creativity engine + continuous improvement": 15.0,
    "Deep seasonal creativity audit": 18.0,
    "Proven-trend seasonal capture & lead-time engine": 20.0,
    "Core commercial upgrades": 25.0,
    "CA$5K/month scale architecture": 30.0,
    "24/7 cloud autonomy, agent swarms, continuous learning": 32.0,
    "Culture & nostalgia opportunity engine": 40.0,
    "Competitive product teardown laboratory": 45.0,
    "Visual asset production audit": 50.0,
    "Voice session reconciliation (model + MJs)": 60.0,
}
DEFAULT_SECTION_WEIGHT = 55.0

# A partial requirement is cheaper to finish than a missing one and is worth doing first: it
# already has a shape, and the gap is usually named in its note.
STATUS_BONUS: dict[str, float] = {reg.PARTIAL: -6.0, reg.MISSING: 0.0}

# How long a claim survives without progress before another worker may take it. A session
# that dies mid-requirement must not hold the task forever, which is the same lease logic the
# job queue already uses and for the same reason.
CLAIM_LEASE_MINUTES = 90

# No completion in this long, with ready work available, is the watchdog's alarm.
IDLE_ALARM_HOURS = 6


class ExecutorRefused(ValueError):
    """A park with no checkable condition, a cycle, or a completion with no evidence."""


# ---------------------------------------------------------------------------
# Dependencies
#
# Deliberately sparse. A dense graph invented up front would block most of the build on
# guesses about what needs what; these are the edges where building the second thing first
# genuinely produces something that has to be redone.

DEPENDENCIES: dict[int, tuple[int, ...]] = {
    # The pre-launch benchmark challenge cannot run before the teardown scorecard exists.
    168: (161, 162),
    # Improvement pipeline needs the findings it consumes.
    164: (161,),
    # The confidence gate reads the ladder.
    27: (274,),
    # Cannibalisation needs the contribution figures pricing produces.
    45: (24,),
    # The trajectory simulator reads the run-rate decomposition.
    26: (25,),
    # Culture radar's improvement wiring needs the improvement bus.
    147: (97,),
    # Seasonal collection calendar needs the lead-time engine's arithmetic.
    123: (283,),
    # Storefront takeovers need the collection architecture they would present.
    131: (143,),
}


# ---------------------------------------------------------------------------
# Owner gates
#
# Every owner-gated requirement is parked on one of these, and every gate has a condition the
# code can *test*. That is the load-bearing constraint: free text would make parking a place
# to put anything difficult, and a queue that can absorb its own difficulties never reports
# being blocked and never finishes. `sync()` refuses an owner-gated requirement with no gate
# rather than letting it drift into the ready list, where it would be work nobody can do.
#
# Two of these check database rows rather than environment variables, which is the point:
# the mechanism is "is this true yet", not "is there a credential".

def _env_gate(*names: str):
    def check(db, env) -> bool:
        import os

        e = env if env is not None else os.environ
        return all((e.get(n) or "").strip() for n in names)
    return check


def _benchmarks_purchased(db, env) -> bool:
    """The owner's ten benchmark patterns, counted rather than asked about."""
    from sqlalchemy import func, select

    from ..core.models import BenchmarkProduct

    with db.session() as s:
        return bool(s.scalar(select(func.count()).select_from(BenchmarkProduct)))


def _model_usable(db, env) -> bool:
    """A key is not a capability.

    The owner supplied an Anthropic key on 2026-09-19 and the first call it made returned
    "Your credit balance is too low to access the Anthropic API." The key authenticates; the
    account cannot serve a request. An environment-variable check would have opened this gate
    and un-parked four requirements onto work that cannot run, which is the queue advertising
    work nobody can start -- the exact failure this module exists to prevent. So the
    condition is a recorded successful call, and it opens by itself when one happens.
    """
    from ..gateway.anthropic import usable

    return usable(db)


def _ads_authorised(db, env) -> bool:
    """Advertising authority is a spend limit the owner set, not a sentence in a chat."""
    from sqlalchemy import select

    from ..core.models import SpendLimit

    with db.session() as s:
        limit = s.scalar(select(SpendLimit).where(SpendLimit.scope == "ads"))
        return bool(limit and limit.daily_cap_cad > 0 and not limit.paused)


class Gate:
    """One owner-granted thing, its checkable condition, and what waits on it."""

    def __init__(self, key: str, what: str, check, requirement_ids: tuple[int, ...],
                 how: str):
        self.key = key
        self.what = what
        self.check = check
        self.requirement_ids = requirement_ids
        self.how = how

    def open(self, db, env=None) -> bool:
        return bool(self.check(db, env))

    def to_dict(self, db=None, env=None) -> dict:
        out = {"key": self.key, "what": self.what, "how_it_is_checked": self.how,
               "requirement_ids": list(self.requirement_ids)}
        if db is not None:
            out["open"] = self.open(db, env)
        return out


GATES: tuple[Gate, ...] = (
    Gate("benchmark_observation",
         "read-only Etsy API credentials for the MJs benchmark mission",
         lambda db, env: _env_gate("ETSY_API_KEY", "ETSY_SHARED_SECRET")(db, env),
         (206, 299, 301, 303, 319),
         "both Railway variables are set and non-empty"),
    Gate("model_provider", "a model provider that can actually serve a request",
         _model_usable,
         (94, 104, 177, 178),
         "a recorded model.probe succeeded -- a real call, not a variable being set"),
    Gate("etsy_shop", "a live Etsy shop, which only the account holder can open",
         _env_gate("ETSY_SHOP_ID"),
         (1, 37, 235, 236),
         "ETSY_SHOP_ID is set, which only exists once the shop does"),
    Gate("browser_vision",
         "a cloud browser/vision worker pool for rendered-page and image evidence",
         _env_gate("BRAMBLELOOP_BROWSER_URL"),
         (15, 39, 67, 71, 76, 86, 116, 126, 189, 218, 221, 222, 277, 278, 281, 304, 315, 320),
         "a browser worker endpoint is configured"),
    Gate("image_generation", "an image-generation capability for the canonical model pack",
         _env_gate("BRAMBLELOOP_IMAGE_KEY"),
         (72, 73, 74, 75, 130, 198, 199, 202),
         "an image-generation key is set"),
    Gate("benchmark_purchases", "roughly ten purchased competitor patterns",
         _benchmarks_purchased,
         (165, 166, 317),
         "at least one BenchmarkProduct row exists -- counted, not asked about"),
    Gate("offsite_storage",
         "an object-storage bucket and credential outside this provider, so a copy of the "
         "continuity archive survives losing the provider itself",
         _env_gate("BRAMBLELOOP_ARCHIVE_URL"),
         (51,),
         "BRAMBLELOOP_ARCHIVE_URL is set, which only exists once a bucket does"),
    Gate("ad_authority", "an approved advertising budget",
         _ads_authorised,
         (242, 243, 244, 245, 294, 295),
         "a SpendLimit row for 'ads' exists with a positive, unpaused daily cap"),
)

GATE_BY_KEY: dict[str, Gate] = {g.key: g for g in GATES}
_GATE_FOR_REQUIREMENT: dict[int, str] = {
    rid: g.key for g in GATES for rid in g.requirement_ids}


def gate_for(requirement_id: int) -> str | None:
    """Which owner gate this requirement waits on, if any."""
    return _GATE_FOR_REQUIREMENT.get(requirement_id)


def gate_states(db, env=None) -> dict:
    """Every gate and whether it is open, checked rather than remembered."""
    return {g.key: g.to_dict(db, env) for g in GATES}


def _validate_graph() -> None:
    known = {r.id for r in reg.load()}
    for node, edges in DEPENDENCIES.items():
        if node not in known:
            raise ExecutorRefused(f"dependency declared for unknown requirement {node}")
        for edge in edges:
            if edge not in known:
                raise ExecutorRefused(f"requirement {node} depends on unknown {edge}")
    # Depth-first cycle check. A cycle makes every task in it permanently blocked, and the
    # queue would report "nothing ready" while looking entirely healthy.
    colour: dict[int, int] = {}

    def visit(node: int, path: tuple[int, ...]) -> None:
        state = colour.get(node, 0)
        if state == 1:
            raise ExecutorRefused(
                f"dependency cycle: {' -> '.join(str(p) for p in path + (node,))}. Every "
                f"task in a cycle is permanently blocked, and the queue would report "
                f"nothing ready while looking healthy")
        if state == 2:
            return
        colour[node] = 1
        for edge in DEPENDENCIES.get(node, ()):
            visit(edge, path + (node,))
        colour[node] = 2

    for node in DEPENDENCIES:
        visit(node, ())


def _validate_gates() -> None:
    """Every owner-gated requirement must be parked on a gate somebody can test.

    Without this the registry's `owner_gated` status and the executor's parking drift apart
    silently, and the drift always goes the same way: an owner-gated requirement with no gate
    falls through into the ready list, where it is work nobody can actually do. The queue
    then reports more ready work than exists, which is the one number this whole module is
    for.
    """
    ungated = [r.id for r in reg.by_status(reg.OWNER_GATED)
               if gate_for(r.id) is None]
    if ungated:
        raise ExecutorRefused(
            f"owner-gated requirements with no gate: {ungated}. Each needs a gate with a "
            f"condition the code can test, or it falls into the ready list as work nobody "
            f"can do and the queue overstates itself")
    known = {r.id for r in reg.load()}
    stray = [rid for rid in _GATE_FOR_REQUIREMENT if rid not in known]
    if stray:
        raise ExecutorRefused(f"gates declared for unknown requirements: {stray}")


def priority_of(requirement) -> float:
    """Lower is sooner. Section first, then how nearly finished it already is."""
    weight = SECTION_WEIGHT.get(requirement.section, DEFAULT_SECTION_WEIGHT)
    return weight + STATUS_BONUS.get(requirement.status, 0.0) + requirement.id / 1000.0


# ---------------------------------------------------------------------------
# Sync


def sync(db, *, env: dict[str, str] | None = None) -> dict:
    """Reconcile the task table with the registry and the current capabilities.

    Idempotent and safe to run on every tick. Registry status is the source of truth for
    *what* a requirement is; this table owns *where it stands*, and a requirement whose
    registry status moved to covered is completed here rather than silently diverging.
    """
    from sqlalchemy import select

    from ..core.models import BuildTask

    _validate_graph()
    _validate_gates()
    now = datetime.now(timezone.utc)

    open_gates: dict[str, bool] = {g.key: g.open(db, env) for g in GATES}

    created, updated, unparked, completed, retired = 0, 0, [], [], []
    with db.session() as s:
        existing = {t.requirement_id: t for t in s.scalars(select(BuildTask))}
        done_ids = {r.id for r in reg.load() if r.status == reg.COVERED}

        for requirement in reg.load():
            if requirement.status not in SCHEDULABLE and requirement.status != reg.OWNER_GATED:
                # Covered and data-gated requirements are not schedulable work. Covered ones
                # still get a row so completion is visible; data-gated ones do not, because
                # no credential makes a customer exist and a task that can never be ready is
                # a permanent blocker wearing a queue entry.
                if requirement.status != reg.COVERED:
                    stale = existing.get(requirement.id)
                    if stale is not None:
                        # A requirement re-audited as data-gated must leave the queue, not
                        # sit in it forever because the row already existed. The first
                        # version of this skipped straight past an existing task, so five
                        # requirements reclassified as gated kept reporting themselves ready
                        # -- the queue advertising work nobody can start, which is the exact
                        # failure this module was written to prevent.
                        s.delete(stale)
                        retired.append(requirement.id)
                    continue

            task = existing.get(requirement.id)
            first_sight = task is None
            if first_sight:
                task = BuildTask(requirement_id=requirement.id)
                s.add(task)
                created += 1
            else:
                updated += 1

            task.title = requirement.title
            task.section = requirement.section
            task.status = requirement.status
            task.note = requirement.note
            task.depends_on = list(DEPENDENCIES.get(requirement.id, ()))
            task.priority = priority_of(requirement)
            task.updated_at = now

            if requirement.status == reg.COVERED:
                if task.state != DONE:
                    task.state = DONE
                    task.completed_at = task.completed_at or now
                    # A completion is a transition this system *observed*, not a status it
                    # found on first sight. Counting the already-covered backlog as
                    # completions would make the first sync look like 140 requirements
                    # finishing at once, and the watchdog would report a moving loop from a
                    # table that had just been created.
                    if not first_sight:
                        completed.append(requirement.id)
                continue

            gate_key = gate_for(requirement.id)
            if gate_key and not open_gates.get(gate_key, False):
                if task.state != PARKED:
                    gate = GATE_BY_KEY[gate_key]
                    task.state = PARKED
                    task.parked_on = gate_key
                    task.parked_at = now
                    task.parked_reason = (
                        f"waiting on {gate.what}. Checked by: {gate.how}. Parked rather "
                        f"than blocking -- every other requirement continues, and this "
                        f"un-parks automatically when the condition becomes true, with "
                        f"nobody having to remember")
                continue

            if task.state == PARKED:
                # The gate opened. Nothing had to remember.
                task.state = READY
                task.parked_on = None
                task.parked_reason = ""
                task.parked_at = None
                unparked.append(requirement.id)

            unmet = [d for d in task.depends_on if d not in done_ids]
            if unmet:
                task.state = BLOCKED
                continue

            if task.state in (BLOCKED,) or task.state not in (IN_PROGRESS, DONE):
                task.state = READY

    result = {"created": created, "updated": updated, "unparked": unparked,
              "completed": completed, "retired": retired, "gates_open": open_gates}

    # A completion the watchdog cannot see is a completion that did not happen, as far as the
    # only thing watching is concerned. Most completions arrive this way -- a session finishes
    # the work and moves the registry status -- and recording them only as a "sync" event made
    # the watchdog report a stalled loop while six requirements had just closed. A false alarm
    # in the channel that exists to catch a real one is worse than no channel.
    for requirement_id in completed:
        record(db, kind="complete", requirement_id=requirement_id, actor="registry_sync",
               summary=f"completed {requirement_id} by registry status",
               detail={"source": "registry_sync"})
    if unparked:
        record(db, kind="unpark", summary=(
            f"{len(unparked)} requirements un-parked because their gate opened"),
            detail={"requirement_ids": unparked, "gates_open": open_gates})
    return result


def record(db, *, kind: str, summary: str, requirement_id: int | None = None,
           actor: str = "executor", detail: dict | None = None) -> int:
    from ..core.models import BuildEvent

    with db.session() as s:
        row = BuildEvent(kind=kind, requirement_id=requirement_id, actor=actor,
                         summary=summary, detail=detail or {})
        s.add(row)
        s.flush()
        return row.id


# ---------------------------------------------------------------------------
# The queue


def reconciliation(db) -> dict:
    """The invariant tying the registry to the queue, stated as what is actually true.

    `executable` (partial or missing) means this build still owes the requirement.
    `ready` means nothing is stopping it right now. Those were the same number while every
    gated requirement was also `owner_gated` -- and they stopped being the same the moment a
    requirement was half-built with its remainder behind a credential, which is the ordinary
    case rather than the exception. Asserting equality would have forced a choice between
    two lies: calling a half-built requirement owner-gated, or calling gated work ready.

    So: every executable requirement is either ready or parked, nothing owner-gated is ever
    ready, and the parked ones name their gate.
    """
    from sqlalchemy import select

    from ..core.models import BuildTask

    with db.session() as s:
        tasks = [(t.requirement_id, t.status, t.state, t.parked_on)
                 for t in s.scalars(select(BuildTask))]

    executable = {r.id for r in reg.executable()}
    ready = {rid for rid, _, state, _ in tasks if state == READY}
    parked = {rid: gate for rid, _, state, gate in tasks if state == PARKED}
    blocked = {rid for rid, _, state, _ in tasks if state == BLOCKED}

    owner_gated_ready = sorted(
        rid for rid in ready
        if reg.get(rid).status == reg.OWNER_GATED)
    unaccounted = sorted(executable - ready - set(parked) - blocked)

    return {
        "executable": len(executable),
        "ready": len(ready),
        "executable_parked": sorted(executable & set(parked)),
        "blocked": len(blocked),
        "balances": not unaccounted and not owner_gated_ready,
        "unaccounted": unaccounted,
        "owner_gated_but_ready": owner_gated_ready,
        "note": ("Executable means this build owes it; ready means nothing is stopping it "
                 "now. A half-built requirement whose remainder waits on a credential is "
                 "both owed and parked, which is why these are two numbers rather than one."),
    }


def queue(db, *, limit: int = 25) -> dict:
    """What is ready, what is parked, what is blocked — and why, for each.

    The three are reported together on purpose. A queue that showed only ready work would
    look identical whether twelve requirements were parked on a credential or none were.
    """
    from sqlalchemy import select

    from ..core.models import BuildTask

    with db.session() as s:
        tasks = list(s.scalars(select(BuildTask)))
        rows = [{"requirement_id": t.requirement_id, "title": t.title,
                 "section": t.section, "status": t.status, "state": t.state,
                 "priority": t.priority, "depends_on": list(t.depends_on or []),
                 "parked_on": t.parked_on, "parked_reason": t.parked_reason,
                 "claimed_by": t.claimed_by}
                for t in tasks]

    ready = sorted([r for r in rows if r["state"] == READY], key=lambda r: r["priority"])
    parked = [r for r in rows if r["state"] == PARKED]
    blocked = [r for r in rows if r["state"] == BLOCKED]
    in_progress = [r for r in rows if r["state"] == IN_PROGRESS]

    by_capability: dict[str, list[int]] = {}
    for r in parked:
        by_capability.setdefault(r["parked_on"] or "unknown", []).append(r["requirement_id"])

    return {
        "ready": ready[:limit],
        "ready_total": len(ready),
        "parked_total": len(parked),
        "parked_by_capability": by_capability,
        "blocked_total": len(blocked),
        "blocked": blocked[:limit],
        "in_progress": in_progress,
        "done_total": sum(1 for r in rows if r["state"] == DONE),
        "next": ready[0] if ready else None,
        "note": ("Ready, parked and blocked are reported together: a queue showing only "
                 "ready work looks identical whether twelve requirements are parked on a "
                 "credential or none are."),
    }


def next_ready(db) -> dict | None:
    """The highest-value requirement nothing is stopping."""
    return queue(db, limit=1)["next"]


def claim(db, requirement_id: int, *, worker: str) -> dict:
    """Take a requirement, with a lease so a dead session does not hold it forever."""
    from sqlalchemy import select

    from ..core.models import BuildTask

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=CLAIM_LEASE_MINUTES)
    with db.session() as s:
        task = s.scalar(select(BuildTask).where(
            BuildTask.requirement_id == requirement_id))
        if task is None:
            raise ExecutorRefused(f"no build task for requirement {requirement_id}")
        if task.state == DONE:
            raise ExecutorRefused(f"requirement {requirement_id} is already done")
        if task.state == PARKED:
            raise ExecutorRefused(
                f"requirement {requirement_id} is parked on {task.parked_on!r}; claiming it "
                f"would be starting work that cannot finish")
        if task.state == BLOCKED:
            raise ExecutorRefused(
                f"requirement {requirement_id} depends on {task.depends_on}, which are not "
                f"done. Building it first produces something that has to be redone")
        if task.state == IN_PROGRESS and task.claimed_by != worker:
            claimed_at = task.claimed_at
            if claimed_at is not None and claimed_at.tzinfo is None:
                claimed_at = claimed_at.replace(tzinfo=timezone.utc)
            if claimed_at is not None and claimed_at > cutoff:
                raise ExecutorRefused(
                    f"requirement {requirement_id} is claimed by {task.claimed_by!r} and the "
                    f"lease has not expired")
        task.state = IN_PROGRESS
        task.claimed_by = worker
        task.claimed_at = now
        task.updated_at = now
        out = {"requirement_id": requirement_id, "title": task.title,
               "section": task.section, "worker": worker,
               "lease_expires_in_minutes": CLAIM_LEASE_MINUTES}

    record(db, kind="claim", requirement_id=requirement_id, actor=worker,
           summary=f"claimed {requirement_id}: {out['title']}")
    return out


def complete(db, requirement_id: int, *, worker: str, evidence: dict) -> dict:
    """Finish a requirement, with evidence. A completion with no evidence is a checkbox."""
    from sqlalchemy import select

    from ..core.models import BuildTask

    if not evidence or not any(str(v).strip() for v in evidence.values()):
        raise ExecutorRefused(
            "a completion records what proved it -- a suite, a test count, a commit. Without "
            "that the build loop's own progress is the one number in this company nobody "
            "has to evidence")

    now = datetime.now(timezone.utc)
    with db.session() as s:
        task = s.scalar(select(BuildTask).where(
            BuildTask.requirement_id == requirement_id))
        if task is None:
            raise ExecutorRefused(f"no build task for requirement {requirement_id}")
        task.state = DONE
        task.completed_at = now
        task.updated_at = now
        task.evidence = dict(evidence)
        task.claimed_by = None
        title = task.title

    record(db, kind="complete", requirement_id=requirement_id, actor=worker,
           summary=f"completed {requirement_id}: {title}", detail=dict(evidence))
    return {"requirement_id": requirement_id, "state": DONE, "evidence": dict(evidence)}


def release(db, requirement_id: int, *, worker: str, why: str) -> dict:
    """Put a claimed requirement back, without pretending it was finished."""
    from sqlalchemy import select

    from ..core.models import BuildTask

    with db.session() as s:
        task = s.scalar(select(BuildTask).where(
            BuildTask.requirement_id == requirement_id))
        if task is None:
            raise ExecutorRefused(f"no build task for requirement {requirement_id}")
        task.state = READY
        task.claimed_by = None
        task.claimed_at = None
        task.updated_at = datetime.now(timezone.utc)

    record(db, kind="release", requirement_id=requirement_id, actor=worker,
           summary=f"released {requirement_id}: {why}")
    return {"requirement_id": requirement_id, "state": READY, "why": why}


# ---------------------------------------------------------------------------
# The watchdog


def watchdog(db, *, now: datetime | None = None,
             idle_alarm_hours: int = IDLE_ALARM_HOURS) -> dict:
    """Is the build actually moving, and if not, is that legitimate?

    The two idle states need opposite responses and look identical from outside. Idle with
    ready work is a stalled loop and is an incident. Idle with everything parked is the
    system working correctly and waiting on a person, and raising an incident for it would
    train everybody to ignore the channel — so it reports, names the capability, and does
    not alarm.
    """
    from sqlalchemy import select

    from ..core.models import BuildEvent

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=idle_alarm_hours)

    def _aware(value):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    with db.session() as s:
        completions = [_aware(e.at) for e in s.scalars(select(BuildEvent).where(
            BuildEvent.kind == "complete"))]

    recent = [c for c in completions if c >= cutoff]
    snapshot = queue(db)
    last = max(completions) if completions else None

    if recent:
        return {"moving": True, "completions_in_window": len(recent),
                "window_hours": idle_alarm_hours,
                "last_completion": last.isoformat() if last else None,
                "ready_total": snapshot["ready_total"],
                "verdict": "moving"}

    if snapshot["ready_total"] == 0:
        return {
            "moving": False,
            "completions_in_window": 0,
            "window_hours": idle_alarm_hours,
            "last_completion": last.isoformat() if last else None,
            "ready_total": 0,
            "parked_total": snapshot["parked_total"],
            "parked_by_capability": snapshot["parked_by_capability"],
            "verdict": "waiting_on_owner" if snapshot["parked_total"] else "finished",
            "alarm": False,
            "note": ("Nothing is ready and nothing has completed, which is the system "
                     "working correctly rather than a stall. Raising an incident here would "
                     "train everybody to ignore the channel."),
        }

    return {
        "moving": False,
        "completions_in_window": 0,
        "window_hours": idle_alarm_hours,
        "last_completion": last.isoformat() if last else None,
        "ready_total": snapshot["ready_total"],
        "next": snapshot["next"],
        "verdict": "stalled",
        "alarm": True,
        "note": (f"{snapshot['ready_total']} requirements are ready and nothing has been "
                 f"completed in {idle_alarm_hours} hours. Idle with ready work is a stalled "
                 f"loop; idle with everything parked is correct. They look identical from "
                 f"outside, which is why this distinguishes them."),
    }


def report(db, *, env: dict[str, str] | None = None) -> dict:
    """Everything an absent owner needs to see about the build loop itself."""
    from ..launch import access

    snapshot = queue(db)
    return {
        "queue": snapshot,
        "watchdog": watchdog(db),
        "gates": gate_states(db, env),
        "capabilities": access.statuses(env),
        "dependencies": {str(k): list(v) for k, v in DEPENDENCIES.items()},
        "claim_lease_minutes": CLAIM_LEASE_MINUTES,
        "note": ("The graph, the queue and the parking state live in Postgres, so losing a "
                 "session loses a worker rather than the build. An owner action parks the "
                 "requirements that need it and never holds the queue."),
    }


# ---------------------------------------------------------------------------
# The owner approval inbox (#196)
#
# The requirement is that an owner action collapses into a card, non-urgent ones batch, and
# *everything else continues*. The last clause is the one that matters and it is the one a
# card UI would quietly drop: an inbox is only asynchronous if the queue behind it does not
# wait, and that property lives in `sync()` rather than here. What lives here is making the
# ask small enough to answer from a phone.

# How the cards sort. Free and quick first, because an owner reading on a phone answers the
# top one, and the top one should be the one that unblocks most for least.
def _urgency(card: dict) -> tuple:
    return (card["max_cost_cad"], card["minutes"], -card["unblocks_count"])


def approval_inbox(db, *, env: dict[str, str] | None = None) -> dict:
    """Every open owner action as a card, with what continues regardless (#196).

    Each card carries the seven things #196 asks for -- what, why, capability, maximum spend,
    risk, rollback, consequence of waiting -- plus the count of requirements it would
    un-park, which is the number that actually decides the order somebody answers them in.
    """
    from ..launch import access

    requests = {r.key: r for r in access.pending_requests(env)}
    cards = []
    for gate in GATES:
        if gate.open(db, env):
            continue
        parked = [r for r in gate.requirement_ids]
        request = requests.get(gate.key)
        cards.append({
            "gate": gate.key,
            "what": gate.what,
            "action": (request.action if request else
                       f"grant {gate.what}"),
            "why": (request.purpose if request else
                    f"{len(parked)} requirements are parked on it"),
            "capability_unlocked": (request.unlocks if request else gate.what),
            "max_spend_cad": request.max_cost_cad if request else 0.0,
            "monthly_ceiling_cad": request.monthly_ceiling_cad if request else 0.0,
            "minutes": request.minutes if request else 10,
            "risk": (request.security_scope if request else
                     "scope not yet described in the access registry"),
            "rollback": ("revocable at the source at any time; the gate closes again and "
                         "its requirements re-park automatically"),
            "consequence_of_waiting": (request.consequence_of_declining if request else
                                       f"requirements {parked} stay parked"),
            "continues_regardless": (request.continues_without if request else
                                     "every requirement not parked on this gate"),
            "unblocks": parked,
            "unblocks_count": len(parked),
            "how_it_is_checked": gate.how,
            "max_cost_cad": request.max_cost_cad if request else 0.0,
        })

    cards.sort(key=_urgency)
    snapshot = queue(db)
    free_and_quick = [c for c in cards if c["max_cost_cad"] == 0.0]
    return {
        "cards": cards,
        "open_actions": len(cards),
        "batched_free_and_quick": [c["gate"] for c in free_and_quick],
        "total_parked": snapshot["parked_total"],
        "ready_regardless": snapshot["ready_total"],
        "blocking_the_build": False,
        "note": ("An inbox is only asynchronous if the queue behind it does not wait. "
                 f"{snapshot['ready_total']} requirements are ready right now and none of "
                 f"them needs any of these answers; answering them un-parks "
                 f"{snapshot['parked_total']} more (#196)."),
    }
