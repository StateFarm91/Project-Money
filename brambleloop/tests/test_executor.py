"""The build loop, and the ways a never-idle loop lies about being busy.

The master intent asks for an autonomous build executor: owner-blocked work parked, the
highest-value unblocked requirement continuing, and a lost session not being a lost build.

The honest problem is that "never idle" is trivially satisfiable. A loop that always has
something to do can invent work; a dependency graph is satisfiable by declaring nothing
depends on anything; and parking is satisfiable by parking whatever is hard. Each of those
produces a queue that looks healthy and a build that has stopped, so most of these tests are
about the queue being unable to overstate itself.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.build2 import executor as E  # noqa: E402
from brambleloop.build2 import requirements as reg  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/executor.sqlite")
    db.create_all()
    return db


def _synced(env: dict | None = None) -> Database:
    db = _db()
    E.sync(db, env=env if env is not None else {})
    return db


# ---- the queue cannot overstate itself ------------------------------------


def test_every_executable_requirement_is_either_ready_or_parked():
    """The invariant the two halves actually share, stated correctly.

    An earlier version asserted ready == executable, which held only while every gated
    requirement was also `owner_gated`. It stopped holding the moment a requirement was
    half-built with its remainder behind a credential -- the ordinary case, not the
    exception -- and the equality would then have forced a choice between two lies: calling
    a half-built requirement owner-gated, or calling gated work ready.
    """
    db = _synced()
    balance = E.reconciliation(db)
    assert balance["balances"], balance
    assert balance["unaccounted"] == []
    # Nothing the owner has to unblock may appear as work this build can pick up.
    assert balance["owner_gated_but_ready"] == []
    # And the gap between the two numbers is exactly the half-built-but-gated set.
    assert balance["ready"] + len(balance["executable_parked"]) == balance["executable"]
    assert balance["executable_parked"], "nothing is half-built and gated; this proves little"


def test_a_requirement_re_audited_as_gated_leaves_the_queue():
    """A queue row must not outlive the status that created it.

    The first version of sync() skipped straight past an existing task when its requirement
    stopped being schedulable, so requirements re-audited as data-gated kept reporting
    themselves ready: the queue advertising work nobody can start, which is the exact failure
    this module exists to prevent.
    """
    import dataclasses

    db = _synced()

    ready = {r["requirement_id"] for r in E.queue(db, limit=400)["ready"]}
    victim = min(ready)

    original = reg.load
    reaudited = [dataclasses.replace(r, status=reg.DATA_GATED) if r.id == victim else r
                 for r in original()]
    try:
        reg.load = lambda: reaudited
        result = E.sync(db, env={})
    finally:
        reg.load = original

    assert victim in result["retired"], result["retired"]
    assert victim not in {r["requirement_id"] for r in E.queue(db, limit=400)["ready"]}

    # And the reverse: a requirement audited back to executable returns to the queue, so the
    # retirement is a reconciliation rather than a deletion the build cannot undo.
    E.sync(db, env={})
    assert victim in {r["requirement_id"] for r in E.queue(db, limit=400)["ready"]}
    assert E.reconciliation(db)["balances"] is True


def test_an_owner_gated_requirement_with_no_gate_is_refused():
    """Otherwise it falls into the ready list as work nobody can do.

    That is the single failure this module exists to prevent, and it is silent: the queue
    reports more ready work than exists, which is the one number the whole thing is for.
    """
    original = dict(E._GATE_FOR_REQUIREMENT)
    victim = reg.by_status(reg.OWNER_GATED)[0].id
    try:
        E._GATE_FOR_REQUIREMENT.pop(victim)
        try:
            E._validate_gates()
        except E.ExecutorRefused as e:
            assert "no gate" in str(e)
            assert "the queue overstates itself" in str(e)
        else:
            raise AssertionError("an ungated owner-gated requirement was accepted")
    finally:
        E._GATE_FOR_REQUIREMENT.clear()
        E._GATE_FOR_REQUIREMENT.update(original)


def test_every_gate_has_a_condition_the_code_can_test():
    """Free text would make parking a place to put anything difficult.

    A queue that can absorb its own difficulties never reports being blocked and never
    finishes — so a gate is a callable, not a sentence.
    """
    db = _db()
    for gate in E.GATES:
        assert callable(gate.check), gate.key
        assert gate.how and len(gate.how.split()) >= 4, gate.key
        assert gate.open(db, {}) in (True, False)

    # Two of them check rows rather than environment variables, which is the point: the
    # mechanism is "is this true yet", not "is there a credential".
    assert E.GATE_BY_KEY["benchmark_purchases"].open(db, {}) is False
    assert E.GATE_BY_KEY["ad_authority"].open(db, {}) is False


def test_a_dependency_cycle_is_refused_because_it_looks_healthy():
    original = dict(E.DEPENDENCIES)
    try:
        E.DEPENDENCIES[161] = (168,)  # 168 already depends on 161
        try:
            E._validate_graph()
        except E.ExecutorRefused as e:
            assert "cycle" in str(e)
            assert "while looking healthy" in str(e)
        else:
            raise AssertionError("a dependency cycle was accepted")
    finally:
        E.DEPENDENCIES.clear()
        E.DEPENDENCIES.update(original)


# ---- parking and un-parking ------------------------------------------------


def test_owner_blocked_requirements_are_parked_and_everything_else_continues():
    """The defect this was built for, stated as a property rather than as an intention."""
    db = _synced()
    q = E.queue(db)

    assert q["parked_total"] > 0, "nothing is parked, so this proves nothing"

    # Stated as the property rather than as a threshold. "More than a hundred ready" was a
    # count of today's backlog: it passes for the wrong reason while the build is young and
    # fails for a good one -- work getting done -- which is a test that has to be edited
    # every time it is right. What must hold at every size of backlog is that parking costs
    # the queue exactly the requirements that are parked and not one more.
    reconciled = E.reconciliation(db)
    assert reconciled["balances"] is True, reconciled
    assert reconciled["ready"] == reconciled["executable"] - len(
        reconciled["executable_parked"]), reconciled
    assert reconciled["ready"] > 0, "the queue stopped because something was parked"
    # Parked, ready and blocked are reported together: a queue showing only ready work looks
    # identical whether fourteen requirements are parked on a browser or none are.
    assert "browser_vision" in q["parked_by_capability"]
    assert len(q["parked_by_capability"]["browser_vision"]) >= 10
    assert "reported together" in q["note"]

    # The next thing to do is named, and it is not one of the parked ones.
    nxt = q["next"]
    assert nxt is not None
    assert nxt["state"] == E.READY


def test_a_gate_opening_un_parks_its_requirements_with_nobody_remembering():
    """The whole reason parking is a checkable condition rather than a note."""
    db = _synced()
    before = E.queue(db)
    credential = {"BRAMBLELOOP_IMAGE_KEY": "k"}

    # The property is that exactly the requirements parked on the gates this credential opens
    # become ready, and nothing else moves. Stated over whichever gates it opens rather than
    # over a named one, so the test keeps measuring the property when the gates change --
    # which they have twice in a day.
    opened = [g.key for g in E.GATES if g.open(db, credential) and not g.open(db, {})]
    assert opened, "this credential opens nothing, so the test proves nothing"
    expected = sorted(
        r for key in opened for r in before["parked_by_capability"].get(key, []))
    assert expected

    result = E.sync(db, env=credential)
    assert sorted(result["unparked"]) == expected

    after = E.queue(db)
    assert after["ready_total"] == before["ready_total"] + len(expected)
    for key in opened:
        assert key not in after["parked_by_capability"]


def test_a_gate_may_be_satisfied_and_carry_no_requirements():
    """Twice in one day, good news moved a gate and moved no work.

    BrambleloopStudio opened, and the four requirements parked on the shop turned out to be
    waiting on automated access to it, so they moved to etsy_api. Then the developer
    credential was approved and verified by use -- and three of those four turned out to be
    waiting on something else again: Marketplace Insights is a Shop Manager surface with no
    endpoint among the nine this application is authorised for, so reading it means reading
    a rendered page. They are on browser_vision now. The fourth needs orders to measure
    anything and is data-gated.

    Both gates stay, satisfied and carrying nothing, because a gate that has opened is
    evidence. What must never happen is the opposite: a gate opening and releasing work into
    the ready queue that nothing can start.
    """
    db = _synced({"ETSY_SHOP_NAME": "BrambleloopStudio"})

    for key in ("etsy_shop", "etsy_api"):
        assert E.GATE_BY_KEY[key].requirement_ids == (), key
        assert key not in E.queue(db)["parked_by_capability"]

    for requirement_id in (1, 37, 236):
        assert E.gate_for(requirement_id) == "browser_vision", requirement_id
    assert reg.get(235).status == reg.DATA_GATED

    assert E.reconciliation(db)["balances"] is True


def test_a_gate_that_checks_rows_opens_when_the_rows_arrive():
    """Not every owner action is a credential: ten purchased patterns is a row count."""
    from brambleloop.core.models import BenchmarkProduct

    db = _synced()
    assert E.GATE_BY_KEY["benchmark_purchases"].open(db, {}) is False
    parked = E.queue(db)["parked_by_capability"]["benchmark_purchases"]

    with db.session() as s:
        s.add(BenchmarkProduct(ref="acme-granny", seller="acme", purchased_on="2026-09-19"))

    assert E.GATE_BY_KEY["benchmark_purchases"].open(db, {}) is True
    assert sorted(E.sync(db, env={})["unparked"]) == sorted(parked)


def test_a_parked_requirement_cannot_be_claimed():
    """Starting work that cannot finish is how a loop looks busy and produces nothing."""
    db = _synced()
    parked = E.queue(db)["parked_by_capability"]["browser_vision"][0]
    try:
        E.claim(db, parked, worker="session-1")
    except E.ExecutorRefused as e:
        assert "cannot finish" in str(e)
    else:
        raise AssertionError("a parked requirement was claimed")


# ---- session loss ----------------------------------------------------------


def test_a_dead_session_loses_a_worker_rather_than_the_build():
    """The state is in the database, so the next worker reads it and continues.

    This is the requirement behind all of it: a build loop that exists only while a
    conversation is open is not autonomy, it is a person with extra steps — and the failure
    is invisible until the moment it matters.
    """
    db = _synced()
    target = E.next_ready(db)["requirement_id"]
    E.claim(db, target, worker="session-1")

    # Session 1 dies here. A second worker cannot steal the claim while the lease holds.
    try:
        E.claim(db, target, worker="session-2")
    except E.ExecutorRefused as e:
        assert "lease has not expired" in str(e)
    else:
        raise AssertionError("a live claim was stolen")

    # Once the lease expires it is taken over, and no manual intervention was needed.
    from sqlalchemy import select

    from brambleloop.core.models import BuildTask

    with db.session() as s:
        task = s.scalar(select(BuildTask).where(BuildTask.requirement_id == target))
        task.claimed_at = datetime.now(timezone.utc) - timedelta(
            minutes=E.CLAIM_LEASE_MINUTES + 5)

    taken = E.claim(db, target, worker="session-2")
    assert taken["worker"] == "session-2"

    # And the whole queue is readable by a process that has never seen this conversation.
    fresh = E.queue(db)
    assert fresh["in_progress"] and fresh["in_progress"][0]["claimed_by"] == "session-2"


def test_a_completion_needs_evidence_because_it_is_the_loops_own_progress():
    db = _synced()
    target = E.next_ready(db)["requirement_id"]
    E.claim(db, target, worker="session-1")

    try:
        E.complete(db, target, worker="session-1", evidence={})
    except E.ExecutorRefused as e:
        assert "nobody has to evidence" in str(e)
    else:
        raise AssertionError("a requirement was completed with no evidence")

    done = E.complete(db, target, worker="session-1",
                      evidence={"suite": "tests/test_executor.py", "tests": 12,
                                "commit": "abc1234"})
    assert done["state"] == E.DONE
    assert E.next_ready(db)["requirement_id"] != target


def test_a_released_requirement_is_not_a_finished_one():
    db = _synced()
    target = E.next_ready(db)["requirement_id"]
    E.claim(db, target, worker="session-1")
    E.release(db, target, worker="session-1", why="turned out to need the browser gate")
    assert E.next_ready(db)["requirement_id"] == target


# ---- the watchdog ----------------------------------------------------------


def test_idle_with_ready_work_is_a_stall_and_idle_with_everything_parked_is_not():
    """They need opposite responses and look identical from outside."""
    db = _synced()
    stalled = E.watchdog(db)
    assert stalled["verdict"] == "stalled"
    assert stalled["alarm"] is True
    assert stalled["next"] is not None
    assert "look identical from outside" in stalled["note"]

    # Park everything, and the same silence becomes correct rather than alarming.
    from sqlalchemy import select

    from brambleloop.core.models import BuildTask

    with db.session() as s:
        for task in s.scalars(select(BuildTask).where(BuildTask.state == E.READY)):
            task.state = E.PARKED
            task.parked_on = "browser_vision"

    waiting = E.watchdog(db)
    assert waiting["verdict"] == "waiting_on_owner"
    assert waiting["alarm"] is False
    assert "working correctly rather than a stall" in waiting["note"]


def test_a_completion_makes_the_loop_moving_again():
    db = _synced()
    target = E.next_ready(db)["requirement_id"]
    E.claim(db, target, worker="session-1")
    E.complete(db, target, worker="session-1", evidence={"commit": "abc1234"})

    health = E.watchdog(db)
    assert health["moving"] is True
    assert health["verdict"] == "moving"
    assert health["completions_in_window"] == 1


def test_a_completion_the_watchdog_cannot_see_is_a_false_alarm():
    """Found in production: six requirements closed and the watchdog said stalled.

    Most completions arrive through the registry rather than through `complete()` -- a
    session finishes the work and moves the status. Recording those only as a sync event
    left the watchdog blind to the commonest kind of progress, and a false alarm in the
    channel that exists to catch a real one is worse than no channel.
    """
    db = _db()
    E.sync(db, env={})

    # Close a requirement the way a session actually closes one: by moving the registry.
    from sqlalchemy import select

    from brambleloop.core.models import BuildEvent, BuildTask

    target = E.next_ready(db)["requirement_id"]
    with db.session() as s:
        task = s.scalar(select(BuildTask).where(BuildTask.requirement_id == target))
        task.status = reg.COVERED

    # A second sync sees the registry move and must record it as a completion.
    original = reg.load
    try:
        reg.load = lambda: tuple(
            r if r.id != target else type(r)(**{**r.to_dict(), "status": reg.COVERED,
                                                "body": r.body})
            for r in original())
        result = E.sync(db, env={})
    finally:
        reg.load = original

    assert target in result["completed"]
    with db.session() as s:
        completions = [e for e in s.scalars(select(BuildEvent))
                       if e.kind == "complete" and e.requirement_id == target]
    assert completions, "a registry-driven completion was invisible to the watchdog"
    assert completions[0].actor == "registry_sync"
    assert E.watchdog(db)["moving"] is True


def test_never_idle_is_measured_in_completions_rather_than_ticks():
    """A loop that always has something to do can invent work; this counts finished things."""
    db = _synced()
    for _ in range(5):
        E.sync(db, env={})
    assert E.watchdog(db)["completions_in_window"] == 0
    assert E.watchdog(db)["verdict"] == "stalled"


# ---- the off-device proof (#195) -------------------------------------------


def test_the_proof_counts_the_same_dead_letters_it_tests():
    """Found in production: the report said 16 and the condition meant 2.

    Shadow-mode publish refusals are the gate working, so they are excluded from the test --
    and they were not excluded from the count beside it. A number that does not measure what
    the verdict beside it measures is the same class of defect as an unmeasured rate
    reported as zero.
    """
    from brambleloop.build2 import autonomy
    from brambleloop.core.models import Job, JobStatus

    db = _db()
    now = datetime.now(timezone.utc)
    with db.session() as s:
        for i in range(5):
            s.add(Job(agent="publishing", job_type="store.publish",
                      status=JobStatus.DEAD, finished_at=now - timedelta(hours=i)))
        s.add(Job(agent="orchestrator", job_type="build.tick",
                  status=JobStatus.DEAD, finished_at=now - timedelta(hours=1)))

    proof = autonomy.off_device_proof(db)
    condition = proof["conditions"]["no_unexpected_dead_letters"]
    assert condition["have"] == 1, "the count must exclude what the test excludes"
    assert condition["types"] == ["build.tick"]
    assert condition["met"] is False
    assert proof["evidence"]["expected_publish_refusals"] == 5
    assert "means what it says" in condition["why"]


def test_the_proof_requires_work_spread_across_the_window_not_a_burst():
    """A container that died after booting completes a burst and then nothing."""
    from brambleloop.build2 import autonomy
    from brambleloop.core.models import Job, JobStatus

    db = _db()
    now = datetime.now(timezone.utc)
    with db.session() as s:
        # Fifty jobs, plenty of types, all inside ten minutes.
        for i in range(50):
            s.add(Job(agent="orchestrator", job_type=f"kind.{i % 6}",
                      status=JobStatus.DONE,
                      finished_at=now - timedelta(minutes=i % 10)))

    proof = autonomy.off_device_proof(db)
    assert proof["conditions"]["jobs_completed"]["met"] is True
    assert proof["conditions"]["distinct_job_types"]["met"] is True
    assert proof["conditions"]["activity_spread"]["met"] is False
    assert proof["passed"] is False
    assert "activity_spread" in proof["unmet"]
    assert "HTTP returns 200" in proof["note"]


# ---- the cadence -----------------------------------------------------------


def test_the_build_loop_runs_in_the_deployed_worker_not_in_a_conversation():
    from sqlalchemy import select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import AuditLog, Incident, Job, JobStatus
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - registers the handlers
    from brambleloop.runtime.worker import CADENCES, Worker

    assert any(c[2] == "build.tick" for c in CADENCES), \
        "the build loop is not on a cadence, so it only runs when somebody asks"

    db = _db()
    Registry(db).seed_defaults()
    JobQueue(db).enqueue("orchestrator", "build.tick", {}, idempotency_key="build-1")
    worker = Worker(db, "build-worker")
    for _ in range(20):
        if not worker.run_once():
            break

    with db.session() as s:
        dead = list(s.scalars(select(Job).where(Job.status == JobStatus.DEAD)))
        ticked = list(s.scalars(select(AuditLog).where(AuditLog.action == "build.ticked")))
        stalls = [i for i in s.scalars(select(Incident))
                  if i.signature == "build.stalled"]

    assert not dead, [(j.job_type, (j.last_error or "")[:200]) for j in dead]
    assert ticked, "the build tick ran and recorded nothing"
    detail = ticked[-1].detail
    # Ready is executable minus the half-built requirements whose remainder is gated.
    assert detail["ready"] == E.reconciliation(db)["ready"]
    assert detail["ready"] < len(reg.executable())
    assert detail["parked"] > 0
    assert detail["next"] is not None
    # Nothing has been completed and work is ready, so the loop raises exactly one stall.
    assert len(stalls) == 1
    assert "look identical from outside" in stalls[0].summary


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
