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


def _open_image_generation(db) -> None:
    """Open the image gate by generating an image, with the provider call injected.

    It used to open on `BRAMBLELOOP_IMAGE_KEY` being set. A key that is set, a key for a
    provider with no price on file, an account with no credit, and a provider that refuses
    this company's brief on content grounds are four states and one string, and the last is
    a live possibility for a brief about an attractive adult model.
    """
    from brambleloop.gateway import images

    images.probe(
        db,
        env={"BRAMBLELOOP_IMAGE_PROVIDER": "flux-2-pro", "BRAMBLELOOP_IMAGE_KEY": "k"},
        generator=lambda prompt, **kw: {"provider": "flux-2-pro", "cad": 0.0274,
                                        "url": "https://example.invalid/i.png",
                                        "latency_ms": 900.0})


def _open_tester_roster(db) -> None:
    """A second gate, so a test that completes one requirement still has one to look at."""
    from brambleloop.core.models import CreatorProfile

    with db.session() as s:
        # A tester who agreed: since C-38 a bare prospect on file does not open the gate.
        s.add(CreatorProfile(ref="a-tester", delivered=1))


def _open_physical_proof(db) -> None:
    """Open one gate by making its condition true, which is the only way a gate opens."""
    from datetime import datetime as _dt

    from brambleloop.core.models import PhysicalTest

    with db.session() as s:
        s.add(PhysicalTest(product_slug="a-sample", version="1", tester_ref="t",
                           completed_at=_dt.now(timezone.utc), passed=True))


def _synced_with_ready_work() -> Database:
    """A database with ready work in it, whatever today's backlog happens to be.

    Several tests below are about claiming, leases, completion and the watchdog -- mechanics
    with nothing to do with how much work is outstanding. They read `next_ready` off the
    live registry, which worked only while the backlog was non-empty, and on 2026-09-20 it
    emptied: nothing is `missing` and every executable requirement is parked on a gate that
    opens from demonstrated capability. Nine tests failed in one run, not one of them because
    the thing it tests had broken.

    That is the same mistake as the threshold in the parking test above, in a different
    costume: a test that borrows its fixture from today's backlog is measuring the backlog.
    So ready work is produced here the way it will actually be produced from now on -- by a
    gate's condition becoming true.

    A gate whose requirements are all `partial` on purpose: opening it produces ready work
    and leaves the reconciliation balanced, where opening a credential gate un-parks
    requirements still audited `owner_gated` -- correct behaviour, and a state where
    `balances` is deliberately false.

    It was `culture_feed` for an afternoon, until that gate's three requirements were built
    and closed, at which point opening it produced no ready work and six tests failed at
    once. The assertion below said exactly that, which is why it is an assertion and not a
    comment -- but the lesson is the one directly above, one level up: a fixture borrowed
    from today's registry is a fixture that expires when the work gets done.
    """
    db = _db()
    E.sync(db, env={})
    _open_physical_proof(db)
    _open_tester_roster(db)
    E.sync(db, env={})
    assert E.next_ready(db) is not None, (
        "this gate no longer produces ready work; the scenario tests below need one "
        "requirement they can claim, and borrowing it from the live backlog is what broke")
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
    # Blocked (waiting on an unfinished dependency) is the third honest place; it was always
    # empty until the Build 2 certification reopened rows other rows depend on (#26 on #25).
    assert (balance["ready"] + len(balance["executable_parked"]) + balance["blocked"]
            == balance["executable"])
    assert balance["executable_parked"], "nothing is half-built and gated; this proves little"


def test_a_requirement_re_audited_as_gated_leaves_the_queue():
    """A queue row must not outlive the status that created it.

    The first version of sync() skipped straight past an existing task when its requirement
    stopped being schedulable, so requirements re-audited as data-gated kept reporting
    themselves ready: the queue advertising work nobody can start, which is the exact failure
    this module exists to prevent.
    """
    import dataclasses

    db = _synced_with_ready_work()

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
    # Blocked on an unfinished dependency is the third accounted place (see the invariant
    # test above); it was empty until the certification reopened rows others depend on.
    assert reconciled["ready"] == reconciled["executable"] - len(
        reconciled["executable_parked"]) - reconciled["blocked"], reconciled
    # Zero ready is a legitimate state and a stalled queue is not, and the difference is
    # whether the zero is accounted for. "ready > 0" stood here until the day it stopped
    # being true, which is the failure mode the comment above already names and this file
    # then walked into anyway: a backlog that empties is the build working. What holds at
    # every size is that every executable requirement is either ready or parked on a named
    # gate, so a queue at zero can say which of the two it is.
    if reconciled["ready"] == 0:
        assert (len(reconciled["executable_parked"]) + reconciled["blocked"]
                == reconciled["executable"]), \
            "the queue is empty and the parked set does not account for it"
    # Parked, ready and blocked are reported together: a queue showing only ready work looks
    # identical whether fourteen requirements are parked on a browser or none are.
    assert "rendered_pages" in q["parked_by_capability"]
    # C-38 (2026-09-27) split what rendered_pages used to hold across the gates each
    # requirement actually waits on; the same work must still all be reported as parked.
    # C-40 then completed #2 and #15 through the API search index, so they left the browser
    # gate as finished work rather than moving to another park. Asserted by membership, not a
    # count, so a row silently moving between gates is caught too.
    pbc = q["parked_by_capability"]
    # #39's policy pages are the hand-written table's one rendered_pages requirement; the
    # registry may park others there (C-60 reopened #35 onto it). Both halves must be
    # reported, and nothing else may be: a row here that neither half parked is a row the
    # executor invented a reason for.
    registry_rendered = {rid for rid, key in E._registry_gates().items()
                         if key == "rendered_pages"}
    assert set(pbc["rendered_pages"]) == {39} | registry_rendered, pbc["rendered_pages"]
    assert {1, 37, 236} <= set(pbc.get("insights_access", [])), pbc
    assert {189, 221, 222, 320} <= set(pbc.get("acceptance_ruling", [])), pbc
    parked_anywhere = {r for rows in pbc.values() for r in rows}
    assert 2 not in parked_anywhere, "#2 is done, not parked"
    # #15 scores five of its six dimensions from the API index on cadence (C-40, C-71); the
    # sixth, thumbnail COMPOSITION, is a judgement of an image and waits on image_vision by
    # name -- that park, and no other, is allowed for it.
    assert {k for k, rows in pbc.items() if 15 in rows} <= {"image_vision"}, pbc
    assert "reported together" in q["note"]

    # The next thing to do is named when there is one, and it is never a parked one. There
    # is no third answer: a queue with ready work that names nothing to do is the defect
    # this whole module exists to prevent.
    nxt = q["next"]
    if q["ready_total"] > 0:
        assert nxt is not None, "work is ready and the queue names nothing to do"
        assert nxt["state"] == E.READY
    else:
        assert nxt is None, "nothing is ready and the queue named something anyway"


def _parked_on_image_generation():
    """A context in which one otherwise-ready requirement is parked on `image_generation`.

    C-60 re-classified every live row that sat on this gate (#203 onto the external
    `model_bearing_render`, #300 onto the chain link that actually stops it), so no registry
    requirement waits on image generation today. The un-park mechanism is still what these
    tests prove, so the parking is supplied through the same `_registry_gates` hook the
    registry uses -- a real requirement id, a real gate, a real opening -- rather than by
    depending on whatever the live registry happens to park there this week.
    """
    import contextlib

    @contextlib.contextmanager
    def ctx():
        probe = _synced()
        ready = [r["requirement_id"] for r in E.queue(probe, limit=400)["ready"]]
        assert ready, "no ready requirement to park, so this proves nothing"
        rid = ready[0]
        real = E._registry_gates
        E._registry_gates = lambda: {**real(), rid: "image_generation"}
        try:
            yield rid
        finally:
            E._registry_gates = real
    return ctx()


def test_a_gate_opening_un_parks_its_requirements_with_nobody_remembering():
    """The whole reason parking is a checkable condition rather than a note."""
    with _parked_on_image_generation():
        _gate_opening_un_parks()


def _gate_opening_un_parks():
    db = _synced()
    before = E.queue(db)

    # The property is that exactly the requirements parked on the gates this evidence opens
    # become ready, and nothing else moves. Stated over whichever gates it opens rather than
    # over a named one, so the test keeps measuring the property when the gates change --
    # which they have three times in two days.
    #
    # Evidence rather than a credential, since 2026-09-20: no gate in this table opens on a
    # typed string any more, so what opens one is a recorded successful use. An image
    # generated is what the image gate reads.
    _open_image_generation(db)
    opened = [g.key for g in E.GATES if g.open(db, {})
              and before["parked_by_capability"].get(g.key)]
    assert opened, "this evidence opens nothing, so the test proves nothing"
    expected = sorted(
        r for key in opened for r in before["parked_by_capability"].get(key, []))
    assert expected

    result = E.sync(db, env={})
    assert sorted(result["unparked"]) == expected

    after = E.queue(db)
    assert after["ready_total"] == before["ready_total"] + len(expected)
    for key in opened:
        assert key not in after["parked_by_capability"]


def test_a_renamed_gate_re_labels_the_rows_already_parked_on_the_old_one():
    """Found in production, 2026-09-20, an hour after splitting a gate.

    Parking wrote `parked_on` only when the state changed, so a task already parked kept the
    key it was parked under. When `browser_vision` became `image_vision` and
    `rendered_pages`, twenty-two live rows went on naming a gate nothing checks. They would
    still have un-parked correctly -- the un-park test reads `gate_for`, not the stored label
    -- so this was a console reporting a capability that no longer exists rather than a stuck
    queue. A label written once is a label that goes stale without saying so.
    """
    from sqlalchemy import select

    from brambleloop.core.models import BuildTask

    db = _synced()
    target = E.queue(db, limit=400)["parked_by_capability"]["rendered_pages"][0]
    with db.session() as s:
        task = s.scalar(select(BuildTask).where(BuildTask.requirement_id == target))
        task.parked_on = "a_gate_that_no_longer_exists"

    E.sync(db, env={})

    with db.session() as s:
        task = s.scalar(select(BuildTask).where(BuildTask.requirement_id == target))
        assert task.parked_on == "rendered_pages"
        assert "moved from a_gate_that_no_longer_exists" in task.parked_reason
    assert "a_gate_that_no_longer_exists" not in E.queue(db, limit=400)[
        "parked_by_capability"]


def test_every_parked_row_names_a_gate_that_exists():
    """The invariant the re-labelling protects, stated over the whole queue."""
    db = _synced()
    keys = set(E.queue(db, limit=400)["parked_by_capability"])
    unknown = sorted(keys - set(E.GATE_BY_KEY))
    assert unknown == [], f"{unknown} name no gate, so nothing will ever open them"


def test_a_gate_may_be_satisfied_and_carry_no_requirements():
    """Twice in one day, good news moved a gate and moved no work.

    BrambleloopStudio opened, and the four requirements parked on the shop turned out to be
    waiting on automated access to it, so they moved to etsy_api. Then the developer
    credential was approved and verified by use -- and three of those four turned out to be
    waiting on something else again: Marketplace Insights is a Shop Manager surface with no
    endpoint among the nine this application is authorised for, so reading it means reading
    a rendered page. They are on rendered_pages now. The fourth needs orders to measure
    anything and is data-gated.

    Both gates stay, satisfied and carrying nothing, because a gate that has opened is
    evidence. What must never happen is the opposite: a gate opening and releasing work into
    the ready queue that nothing can start.
    """
    db = _synced({"ETSY_SHOP_NAME": "BrambleloopStudio"})

    for key in ("etsy_shop", "etsy_api"):
        assert E.GATE_BY_KEY[key].requirement_ids == (), key
        assert key not in E.queue(db)["parked_by_capability"]

    # Since 2026-09-27 (C-38) Marketplace Insights waits on owner-recorded readings rather
    # than on a browser: `insights_access`, which counts InsightsSnapshot rows.
    for requirement_id in (1, 37, 236):
        assert E.gate_for(requirement_id) == "insights_access", requirement_id
    # The fourth, #235, may only ever wait on orders. C-60 (2026-09-27) reopened it as
    # executable work -- `promotion.incrementality` had no caller -- so today it is parked
    # nowhere; the day it is parked again, the park must be the data gate `customers` and the
    # status must say so. Either way it never waits on a credential or a browser.
    gate_235 = E.gate_for(235)
    if gate_235 is None:
        assert reg.get(235).status == reg.PARTIAL, reg.get(235).status
    else:
        assert gate_235 == "customers", gate_235
        # A park is written as `partial` + explicit `parked_on` (C-74: the registry forbids
        # parked_on on a data_gated row, and only an explicit park parks a partial one).
        assert reg.get(235).status == reg.PARTIAL and reg.get(235).parked_on == "customers", \
            (reg.get(235).status, reg.get(235).parked_on)

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
    parked = E.queue(db)["parked_by_capability"]["rendered_pages"][0]
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
    db = _synced_with_ready_work()
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
    db = _synced_with_ready_work()
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
    # The property, not the shape. A completed requirement is never what the queue offers
    # next -- and "there is nothing next" satisfies that as fully as "something else is",
    # which matters now that the backlog is small enough to empty.
    nxt = E.next_ready(db)
    assert nxt is None or nxt["requirement_id"] != target


def test_a_released_requirement_is_not_a_finished_one():
    db = _synced_with_ready_work()
    target = E.next_ready(db)["requirement_id"]
    E.claim(db, target, worker="session-1")
    E.release(db, target, worker="session-1", why="turned out to need the browser gate")
    assert E.next_ready(db)["requirement_id"] == target


# ---- the watchdog ----------------------------------------------------------


def test_idle_with_ready_work_is_a_stall_and_idle_with_everything_parked_is_not():
    """They need opposite responses and look identical from outside.

    Refined 2026-09-26: ready work that nobody has *claimed* is not a stall. The deployed
    worker never writes code, so "nothing completed in six hours" with no claim measures how
    often a session was opened. That is `awaiting_build_session`, names the top ready
    requirement, and does not alarm. A claim with no completion is the stall.
    """
    db = _synced_with_ready_work()
    awaiting = E.watchdog(db)
    assert awaiting["verdict"] == E.AWAITING_BUILD_SESSION
    assert awaiting["alarm"] is False
    assert awaiting["next"] is not None
    assert f"#{awaiting['next']['requirement_id']}" in awaiting["note"]

    target = E.next_ready(db)["requirement_id"]
    E.claim(db, target, worker="session-1")
    stalled = E.watchdog(db)
    assert stalled["verdict"] == E.STALLED
    assert stalled["alarm"] is True
    assert stalled["claims_in_window"] == 1
    assert {"requirement_id": target, "claimed_by": "session-1"} in stalled["in_progress"]
    assert "took the task and stopped" in stalled["note"]

    # A claim older than the window is still a stall while the task is held.
    later = datetime.now(timezone.utc) + timedelta(hours=E.IDLE_ALARM_HOURS + 1)
    assert E.watchdog(db, now=later)["verdict"] == E.STALLED
    E.release(db, target, worker="session-1", why="test")
    assert E.watchdog(db, now=later)["verdict"] == E.AWAITING_BUILD_SESSION

    db = _synced_with_ready_work()

    # Park everything, and the same silence becomes correct rather than alarming.
    from sqlalchemy import select

    from brambleloop.core.models import BuildTask

    with db.session() as s:
        for task in s.scalars(select(BuildTask).where(BuildTask.state == E.READY)):
            task.state = E.PARKED
            task.parked_on = "rendered_pages"

    waiting = E.watchdog(db)
    assert waiting["verdict"] == "waiting_on_owner"
    assert waiting["alarm"] is False
    assert "working correctly rather than a stall" in waiting["note"]


def test_a_completion_makes_the_loop_moving_again():
    db = _synced_with_ready_work()
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
    db = _synced_with_ready_work()

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
    db = _synced_with_ready_work()
    for _ in range(5):
        E.sync(db, env={})
    assert E.watchdog(db)["completions_in_window"] == 0
    # Five syncs are not progress: the loop is not "moving". Nobody claimed anything, so it
    # is waiting for a build session rather than stalled.
    assert E.watchdog(db)["moving"] is False
    assert E.watchdog(db)["verdict"] == E.AWAITING_BUILD_SESSION


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


def test_a_job_standing_aside_for_another_build_is_a_refusal_not_a_death():
    """The second kind of deliberate dead letter, and it made a health check lie.

    A rolling deploy runs two commits at once. A job stamped for the build that should run
    it, claimed by the one that should not, fails on purpose so the right replica takes it
    -- and the work then happens. `/api/verify` counted that as an unexplained death and
    went red, which is how a health signal stops being read.
    """
    from datetime import datetime, timedelta, timezone

    from brambleloop.build2 import autonomy
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.queue.durable import deliberate_refusal

    assert deliberate_refusal("store.publish") is True
    assert deliberate_refusal(
        "creative.model_reference_pack",
        "RuntimeError: this job asked for pack 'v6' and this build produces 'v5'. Failing "
        "so another replica takes it") is True
    # And an ordinary failure is still an ordinary failure.
    assert deliberate_refusal("build.tick", "AttributeError: NoneType") is False

    db = _db()
    now = datetime.now(timezone.utc)
    with db.session() as s:
        s.add(Job(agent="creative_director", job_type="creative.model_reference_pack",
                  status=JobStatus.DEAD, finished_at=now - timedelta(hours=1),
                  last_error="Failing so another replica takes it"))
        s.add(Job(agent="orchestrator", job_type="build.tick",
                  status=JobStatus.DEAD, finished_at=now - timedelta(hours=1),
                  last_error="AttributeError: NoneType"))

    condition = autonomy.off_device_proof(db)["conditions"]["no_unexpected_dead_letters"]
    assert condition["types"] == ["build.tick"], condition["types"]


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
    """Both idle states, through the worker rather than through the module.

    The tick reads the world rather than an injected fixture, which is the point -- a gate
    opening in production opens it for the deployed worker with nobody editing anything. So
    this drives it twice: once with the backlog as it actually is, where every executable
    requirement is parked and the loop's silence is correct, and once after a gate's
    condition has become true, where the same silence is a stalled loop. The two look
    identical from outside and the incident is the whole difference.
    """
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
    worker = Worker(db, "build-worker")

    def tick(key: str) -> None:
        JobQueue(db).enqueue("orchestrator", "build.tick", {}, idempotency_key=key)
        for _ in range(20):
            if not worker.run_once():
                break

    def state():
        with db.session() as s:
            return (
                list(s.scalars(select(Job).where(Job.status == JobStatus.DEAD))),
                list(s.scalars(select(AuditLog).where(AuditLog.action == "build.ticked"))),
                [i for i in s.scalars(select(Incident)) if i.signature == "build.stalled"],
            )

    tick("build-1")
    dead, ticked, stalls = state()
    assert not dead, [(j.job_type, (j.last_error or "")[:200]) for j in dead]
    assert ticked, "the build tick ran and recorded nothing"
    detail = ticked[-1].detail
    # Ready is executable minus the half-built requirements whose remainder is gated.
    assert detail["ready"] == E.reconciliation(db)["ready"]
    assert detail["ready"] < len(reg.executable())
    assert detail["parked"] > 0
    # Idle with everything parked. The loop has completed nothing and must not say so in the
    # channel that exists for real stalls, because a channel that cries wolf gets muted.
    if detail["ready"] == 0:
        assert detail["next"] is None
        assert detail["verdict"] == "waiting_on_owner"
        assert not stalls, "everything is parked and the loop raised a stall anyway"

    # Now a gate's condition becomes true in the database the deployed worker actually
    # reads, and the same silence becomes a stall with exactly one incident behind it.
    _open_physical_proof(db)
    tick("build-2")
    tick("build-3")

    dead, ticked, stalls = state()
    assert not dead, [(j.job_type, (j.last_error or "")[:200]) for j in dead]
    opened = ticked[-1].detail
    assert opened["ready"] > 0, "the gate released no work, so this proves nothing"
    assert opened["next"] is not None
    # Ready and unclaimed: waiting for a build session, which is an operator note naming the
    # top ready requirement, not a P2 about how often somebody opens a session.
    assert opened["verdict"] == E.AWAITING_BUILD_SESSION
    assert f"#{opened['next']}" in (opened["operator_note"] or "")
    assert not stalls, [i.summary[:80] for i in stalls]

    # A claim that makes no progress is the stall, and two ticks are still one row.
    E.claim(db, opened["next"], worker="session-9")
    tick("build-4")
    tick("build-5")
    dead, ticked, stalls = state()
    assert ticked[-1].detail["verdict"] == E.STALLED
    # Two ticks, one incident: a loop that raises a fresh row every hour is a loop nobody
    # reads.
    #
    # Asserted as a total rather than as an increment. `before + 1` quietly depended on
    # the first phase being silent, which stopped being true on 2026-09-22 when the
    # canonical-model gate opened and six requirements un-parked into genuinely ready
    # work: the first tick then correctly raised the stall, and the test failed on a
    # change that was the system working. The property was never about the increment -- it
    # is that however many ticks pass, one stall is one row.
    assert len(stalls) == 1, [i.summary[:80] for i in stalls]
    assert "took the task and stopped" in stalls[-1].summary
    assert stalls[-1].resolved is False
    assert stalls[-1].report_count >= 2 and stalls[-1].detail.get("last_seen")

    # Released: nothing is claimed, so the stall closes itself and says why.
    E.release(db, opened["next"], worker="session-9", why="test")
    with db.session() as s:
        from brambleloop.core.models import BuildEvent
        for e in s.scalars(select(BuildEvent).where(BuildEvent.kind == "claim")):
            e.at = e.at - timedelta(hours=E.IDLE_ALARM_HOURS + 1)
    tick("build-6")
    dead, ticked, stalls = state()
    assert len(stalls) == 1 and stalls[0].resolved is True
    assert "waiting for a build session" in stalls[0].detail["resolution"]
    assert stalls[0].detail["resolved_at"]
    assert ticked[-1].detail["stall_resolved"] == ["build.stalled"]


# ---- the registry may park its own remainder ------------------------------


def test_a_partial_requirement_whose_remainder_is_gated_is_parked_by_its_own_audit():
    """The note and the parking are one edit, because they used to be two.

    #292 is the case that found this. Its note said every move the build could reach was
    built and the rest waited on image generation, and the executor -- which cannot read
    prose -- went on offering it as the single highest-value ready requirement. A queue whose
    top item cannot be started is the failure this module exists to prevent, and it had it.
    """
    gated = E._registry_gates()
    assert gated, "no requirement declares its own gate; this test proves nothing"
    for rid, key in gated.items():
        assert key in E.GATE_BY_KEY, (rid, key)
        assert reg.get(rid).status in reg.EXECUTABLE, (rid, reg.get(rid).status)

    db = _synced(env={})
    rows = {r["requirement_id"]: r for r in E.queue(db, limit=400)["ready"]}
    for rid in gated:
        assert rid not in rows, f"{rid} declares a gate and is still ready"


def test_a_registry_gate_nothing_checks_is_refused_rather_than_silently_parking():
    """The dangerous direction: parked on a key no gate owns can never un-park.

    That is worse than not parking at all. The requirement leaves the queue and never comes
    back, and the loop reports itself finished by having lost a requirement rather than by
    having done it.
    """
    real = E._registry_gates
    E._registry_gates = lambda: {292: "a_capability_nobody_defined"}
    try:
        raised = None
        try:
            E._validate_gates()
        except E.ExecutorRefused as e:
            raised = e
        assert raised is not None, "a gate nothing checks was accepted"
        assert "never opens" in str(raised)
    finally:
        E._registry_gates = real


def test_the_registry_gate_un_parks_on_the_same_condition_as_the_hand_written_one():
    """Parked here is still parked *on a condition*, not filed away.

    A gate that opens has to return its requirement to the queue with nobody remembering to
    do it -- the whole reason gates are checked rather than recorded. The registry half must
    behave identically to the table half or it is a quiet way of dropping work.
    """
    with _parked_on_image_generation():
        _registry_gate_un_parks()


def _registry_gate_un_parks():
    gated = [rid for rid, key in E._registry_gates().items()
             if key == "image_generation"]
    assert gated, "no registry requirement waits on image generation"
    shut = _synced(env={})
    assert E.queue(shut, limit=400)["parked_by_capability"]["image_generation"]

    # Opened the only way it can be: a real generation recorded.
    _open_image_generation(shut)
    E.sync(shut, env={})
    ready = {r["requirement_id"] for r in E.queue(shut, limit=400)["ready"]}
    for rid in gated:
        assert rid in ready, f"{rid} did not come back when its gate opened"


def test_a_remainder_that_needs_orders_has_somewhere_to_wait():
    """The gap in the parking mechanism, found by reading the next ready requirement.

    `parked_on` covered capabilities somebody can grant. #18's remainder -- whether fast
    support reduces refunds and improves reviews -- needs *orders*, and nothing in the gate
    table could ever open for that, so it sat at the top of the ready queue advertising a
    measurement that cannot be taken until refunds exist.

    The `customers` gate is the one entry in that table the owner cannot grant. It counts
    ledger rows rather than reading a phase flag, for the reason every other gate counts
    something: a flag saying "we are selling now" is a claim and a ledger entry is an event.
    """
    from brambleloop.core.models import LedgerEntry

    gate = E.GATE_BY_KEY["customers"]
    shut = _db()
    assert gate.open(shut, {}) is False
    # And no environment variable can open it, which is the whole point.
    assert gate.open(shut, {"BRAMBLELOOP_PHASE": "production",
                            "BRAMBLELOOP_CUSTOMERS": "many"}) is False

    E.sync(shut, env={})
    parked = E.queue(shut, limit=400)["parked_by_capability"]
    assert parked.get("customers"), parked

    with shut.session() as s:
        s.add(LedgerEntry(category="sale", description="first order", gross_cad=9.0,
                          evidence_ref="test"))
    assert gate.open(shut, {}) is True

    E.sync(shut, env={})
    q = E.queue(shut, limit=400)
    ready = {r["requirement_id"] for r in q["ready"]}
    blocked = {r["requirement_id"] for r in q["blocked"]}
    after = q["parked_by_capability"].get("customers", [])
    for rid in parked["customers"]:
        # The sale releases the customers park. A row that also depends on unfinished work
        # (#26 on #25 since the certification reopened #25) moves to blocked, which is where
        # it belongs -- it must never stay parked on customers once customers exist.
        assert rid not in after, f"{rid} is still parked on customers after the first sale"
        assert rid in ready or rid in blocked, f"{rid} did not come back when the first sale landed"


def test_a_remainder_that_needs_a_published_listing_has_somewhere_to_wait():
    """The second gate nobody can grant with a key, and it is not waiting on a stranger.

    Impressions, click-through and favourites are facts about a listing somebody can see.
    No credential produces them for a listing that was never published, and shadow mode
    forbids publishing by design -- so the requirement was sitting in the ready queue
    advertising a measurement that cannot be taken.

    It counts an Etsy listing id rather than reading the phase flag, because a phase is a
    statement of intent and a listing id is a listing.
    """
    from brambleloop.core.models import Listing

    gate = E.GATE_BY_KEY["live_listings"]
    shut = _db()
    assert gate.open(shut, {}) is False
    assert gate.open(shut, {"BRAMBLELOOP_PHASE": "production"}) is False

    with shut.session() as s:
        s.add(Listing(product_slug="p", version="1.0.0", title="t", description="d",
                      price_cad=9.0))
    assert gate.open(shut, {}) is False, "a drafted listing is not a published one"

    with shut.session() as s:
        s.add(Listing(product_slug="q", version="1.0.0", title="t", description="d",
                      price_cad=9.0, etsy_listing_id="1234567890"))
    assert gate.open(shut, {}) is True


def test_a_finished_requirement_cannot_carry_a_gate_for_work_it_no_longer_owes():
    """parked_on describes the *remainder*. With no remainder it is a leftover key.

    Built from the real registry with one requirement swapped, so the spine and status
    checks pass and this is the only thing left to fail on -- a hand-rolled one-row registry
    would trip the spine check first and the test would pass without ever reaching the rule
    it names.
    """
    import dataclasses

    covered = next(r for r in reg.load() if r.status == reg.COVERED)
    spoiled = tuple(dataclasses.replace(r, parked_on="image_generation")
                    if r.id == covered.id else r for r in reg.load())
    raised = None
    try:
        reg._validate(spoiled)
    except ValueError as e:
        raised = e
    assert raised is not None, "a gate on finished work was accepted"
    assert "not executable work" in str(raised), str(raised)
    assert str(covered.id) in str(raised), str(raised)


# ---- a note is not a park -------------------------------------------------

# Phrases that say, in prose, that a requirement is waiting for something that does not
# exist. Deliberately narrow: each one states a blocker rather than describing remaining
# work, because "still to build" is ordinary and "needs a credential nobody has" is a park.
_BLOCKED_PHRASES = (
    "unrunnable until",
    "needs a connected",
    "which this company has never had",
    "needs the vision capability",
    # Added after the list missed #200, whose note said "needs the image capability" while
    # the list held only "vision". One word apart, and the requirement sat in the ready
    # queue -- a phrase list catches the phrasings somebody thought of, which is why the
    # sweep that found it ran over the whole registry rather than over one requirement.
    "needs the image capability",
    "needs a credential",
    "does not exist yet in shadow mode",
    "no feed is connected",
)


def test_a_requirement_whose_note_says_it_is_blocked_is_parked():
    """Three times in one session, prose in a note was doing a gate's job.

    #133, #140 and #147 said no cultural feed is connected. #61 and #64 said they needed a
    vision capability and a photograph of an object nobody has made. #168 said unrunnable
    until benchmarks are purchased, and #79 said it needed vision. Every one of those notes
    was accurate, and every one of those requirements sat in the ready queue reporting itself
    as work somebody could start -- because a note is read by people and the queue reads
    gates.

    This is the check that would have caught all seven. It is phrase-matching and therefore
    crude, and crude is the right trade here: a false positive costs a reworded note or a
    park that should have existed anyway, and a false negative costs the ready count its
    meaning.
    """
    stranded = []
    for requirement in reg.load():
        if requirement.status in (reg.COVERED, reg.OWNER_GATED, reg.DATA_GATED):
            continue
        if getattr(requirement, "parked_on", None):
            continue
        note = (getattr(requirement, "note", "") or "").lower()
        hit = next((phrase for phrase in _BLOCKED_PHRASES if phrase in note), None)
        if hit:
            stranded.append(f"#{requirement.id} says {hit!r} and is not parked")
    assert not stranded, (
        "these requirements describe a blocker in prose and advertise themselves as ready "
        "work: " + "; ".join(stranded))


def test_every_parked_requirement_names_a_gate_that_exists():
    """The other direction: a park onto a gate nothing defines never opens."""
    unknown = []
    for requirement in reg.load():
        key = getattr(requirement, "parked_on", None)
        if key and key not in E.GATE_BY_KEY:
            unknown.append(f"#{requirement.id} parked on {key!r}")
    assert not unknown, unknown


def test_owner_approval_is_a_gate_rather_than_a_sentence_in_a_note():
    """The defect this gate was written for, caught in production a day after it started.

    Nine requirements' notes read "needs an image generation capability *and owner identity
    selection*". Only the first half was written as a gate, so the moment image generation
    started working all nine un-parked into the ready queue -- work nobody can start,
    advertised as ready, which is the one number this module exists to get right. A prose
    condition is not a gate no matter how clearly it is written.
    """
    assert "canonical_model" in E.GATE_BY_KEY
    # The condition, not the requirement list. The list is data and it legitimately
    # emptied on 2026-09-22 when the owner approved the identity -- a gate that has opened
    # is kept as evidence and carries nothing, the way `etsy_shop` does. Asserting the
    # membership would have made this test fail on the approval it was written to wait for.
    gate = E.GATE_BY_KEY["canonical_model"]
    assert gate.check is E._canonical_model_approved
    assert "approval" in gate.what or "approve" in gate.what

    # The invariant that outlives the list: nothing owner-gated is ever ready.
    db = _synced({"BRAMBLELOOP_IMAGE_KEY_OPENAI": "set"})
    assert E.reconciliation(db)["owner_gated_but_ready"] == []
    assert E.reconciliation(db)["balances"] is True


def test_a_rendered_pack_does_not_open_the_owner_approval_gate():
    """The gate has to be unsatisfiable by more work. `canonical_pack` reads the one slot
    `select` refuses to write without an approval timestamp, so a better picture cannot
    make it true -- which is the whole point of a decision gate as against a capability."""
    from brambleloop.visual import identity, model_registry

    db = _db()
    assert E._canonical_model_approved(db, {}) is False

    model_registry.record_candidate(
        db, "brambleloop-canonical",
        fields={f: "described" for f in identity.IDENTITY_FIELDS},
        image_refs=["rendered.png"])
    assert E._canonical_model_approved(db, {}) is False, \
        "a rendered candidate is not an approval"

    try:
        model_registry.select_canonical(db, "brambleloop-canonical", owner_approved=False)
    except (model_registry.RegistryRefused, identity.IdentityRefused):
        pass
    else:                                                    # pragma: no cover
        raise AssertionError("select_canonical promoted without the owner")
    assert E._canonical_model_approved(db, {}) is False

    model_registry.select_canonical(db, "brambleloop-canonical", owner_approved=True)
    assert E._canonical_model_approved(db, {}) is True, \
        "the gate must actually open once the owner approves, or it is a wall"


def test_the_reconciliation_is_actually_called_by_the_report():
    """It was written, tested, and read by nothing -- this build's most familiar failure,
    committed by the module whose docstring names it. While nobody called it, nine
    owner-gated requirements sat in the production ready list for a day."""
    db = _synced({})
    report = E.report(db, env={})
    assert "reconciliation" in report
    assert report["reconciliation"]["balances"] is True


def test_the_model_bearing_render_gate_opens_only_on_a_frame_that_cleared_every_floor():
    """#72, #130 and #202 wait on a model-bearing frame that passes all six floors.

    The gate reads `assets.model_photography` records. A frame that failed photographic
    realism, one with an `unverifiable` floor, one written with fewer floors than the current
    six, and a product-first `assets.owned_photography` frame must all leave it closed.
    """
    from brambleloop.build2 import closure
    from brambleloop.core.models import AuditLog
    from brambleloop.publish import model_photography, owned_photography

    gate = E.GATE_BY_KEY["model_bearing_render"]
    assert closure.kind_of("model_bearing_render"), "the gate is not classified by closure"
    assert "model_bearing_render" in closure.EXTERNAL_GATES

    db = _db()
    assert gate.open(db) is False

    passing = {name: "pass" for name in model_photography.FLOORS}
    near_misses = [
        {**passing, "photographic_realism": "fail"},
        {**passing, "product_truth": "unverifiable"},
        {k: v for k, v in passing.items() if k != "styling"},
    ]
    with db.session() as s:
        for floors in near_misses:
            s.add(AuditLog(actor="publishing", action=model_photography.ACTION, detail={
                "made": True, "carries_model": True, "floors": floors,
                "usable_as_listing_asset": all(v == "pass" for v in floors.values())}))
        # A product-first frame that passed its own floors proves nothing about her.
        s.add(AuditLog(actor="publishing", action=owned_photography.ACTION, detail={
            "made": True, "carries_model": False, "floors": passing,
            "usable_as_listing_asset": True}))
        # And a record that says usable without carrying the model is not one.
        s.add(AuditLog(actor="publishing", action=model_photography.ACTION, detail={
            "made": True, "carries_model": False, "floors": passing,
            "usable_as_listing_asset": True}))
    assert gate.open(db) is False

    with db.session() as s:
        s.add(AuditLog(actor="publishing", action=model_photography.ACTION, detail={
            "made": True, "carries_model": True, "floors": passing,
            "usable_as_listing_asset": True}))
    assert gate.open(db) is True


def test_the_scheduler_condition_counts_cadences_rather_than_any_audit_row():
    """`scheduler_alive` read every audit row in the window, so a burst of hand-driven work
    -- or the health sweep writing about itself -- could stand in for a scheduler that had
    stopped. It counts hours in which a cadence was enqueued."""
    from brambleloop.build2 import autonomy
    from brambleloop.core.models import AuditLog, Job, JobStatus

    db = _db()
    now = datetime.now(timezone.utc)
    with db.session() as s:
        for h in range(20):
            s.add(AuditLog(actor="orchestrator", action="ops.health",
                           at=now - timedelta(hours=h)))
    proof = autonomy.off_device_proof(db, now=now)
    assert proof["conditions"]["scheduler_alive"]["have"] == 0
    assert proof["conditions"]["scheduler_alive"]["met"] is False

    with db.session() as s:
        for h in range(14):
            s.add(Job(agent="orchestrator", job_type="ops.heartbeat", status=JobStatus.DONE,
                      idempotency_key=f"cadence:infra_heartbeat:{h}",
                      created_at=now - timedelta(hours=h, minutes=5),
                      finished_at=now - timedelta(hours=h)))
        # Hand-enqueued work in the same hours does not count as the scheduler.
        for h in range(20, 23):
            s.add(Job(agent="orchestrator", job_type="build.tick", status=JobStatus.DONE,
                      idempotency_key=f"manual:{h}", created_at=now - timedelta(hours=h),
                      finished_at=now - timedelta(hours=h)))
    alive = autonomy.off_device_proof(db, now=now)["conditions"]["scheduler_alive"]
    assert alive["have"] == 14, alive
    assert alive["met"] is True



# ---- certification repairs C-16 and C-38 (2026-09-27) -----------------------------------


def _held_state(db, rid):
    from sqlalchemy import select

    from brambleloop.core.models import BuildTask

    with db.session() as s:
        t = s.scalar(select(BuildTask).where(BuildTask.requirement_id == rid))
        return t.state, t.claimed_by


def _refusals(db):
    from sqlalchemy import select

    from brambleloop.core.models import BuildEvent

    with db.session() as s:
        return [e.summary for e in s.scalars(select(BuildEvent).where(
            BuildEvent.kind == "refused"))]


def test_only_the_claimant_of_an_in_progress_task_completes_or_releases_it():
    """C-16: completing a parked/unclaimed task, or another worker's, is refused and
    audited."""
    db = _synced_with_ready_work()
    snap = E.queue(db, limit=400)
    parked = [rid for ids in snap["parked_by_capability"].values() for rid in ids]
    assert parked, "nothing parked; this proves nothing"
    for call in (lambda: E.complete(db, parked[0], worker="w", evidence={"x": "y"}),
                 lambda: E.release(db, parked[0], worker="w", why="w")):
        try:
            call()
        except E.ExecutorRefused as e:
            assert "claim it first" in str(e)
        else:
            raise AssertionError("a parked requirement was finished without a claim")
    assert _held_state(db, parked[0])[0] == E.PARKED

    target = E.next_ready(db)["requirement_id"]
    try:
        E.complete(db, target, worker="A", evidence={"x": "y"})
    except E.ExecutorRefused:
        pass
    else:
        raise AssertionError("a READY, unclaimed requirement was completed")
    E.claim(db, target, worker="A")
    for call in (lambda: E.complete(db, target, worker="B", evidence={"x": "y"}),
                 lambda: E.release(db, target, worker="B", why="not mine")):
        try:
            call()
        except E.ExecutorRefused as e:
            assert "claimed by 'A'" in str(e)
        else:
            raise AssertionError("B finished a requirement A holds")
    assert _held_state(db, target) == (E.IN_PROGRESS, "A")
    assert len(_refusals(db)) == 5
    assert E.complete(db, target, worker="A", evidence={"suite": "ok"})["state"] == E.DONE


def test_an_honest_release_does_not_leave_the_watchdog_alarming():
    """C-16: the watchdog counted claim *events*, so claim -> release read as a stall."""
    db = _synced_with_ready_work()
    target = E.next_ready(db)["requirement_id"]
    E.claim(db, target, worker="A")
    assert E.watchdog(db)["verdict"] == E.STALLED
    E.release(db, target, worker="A", why="out of time; nothing half-done")
    h = E.watchdog(db)
    assert h["alarm"] is False and h["verdict"] == E.AWAITING_BUILD_SESSION, h


def test_owned_surfaces_opens_on_a_recorded_probe_not_on_a_variable():
    from brambleloop.core.models import AuditLog

    db = _db()
    gate = E.GATE_BY_KEY["owned_surfaces"]
    env = {"BRAMBLELOOP_SITE_URL": "https://example.test", "PINTEREST_ACCESS_TOKEN": "t"}
    assert gate.open(db, env) is False, "a variable alone opened owned_surfaces"
    with db.session() as s:
        s.add(AuditLog(actor="t", action="owned_surface.probe", detail={"ok": False}))
    assert gate.open(db, env) is False
    with db.session() as s:
        s.add(AuditLog(actor="t", action="owned_surface.probe", detail={"ok": True}))
    assert gate.open(db, {}) is True


def test_customers_counts_evidenced_revenue_not_expenses():
    from brambleloop.core.models import LedgerEntry

    db = _db()
    gate = E.GATE_BY_KEY["customers"]
    with db.session() as s:
        s.add(LedgerEntry(category="hosting", expense_cad=5.0, evidence_ref="inv-1"))
        s.add(LedgerEntry(category="sale", gross_cad=12.0, evidence_ref=""))
    assert gate.open(db) is False, "an expense or an unevidenced sale opened customers"
    with db.session() as s:
        s.add(LedgerEntry(category="sale", gross_cad=12.0, evidence_ref="etsy-receipt-1"))
    assert gate.open(db) is True


def test_tester_roster_counts_agreement_not_prospects():
    from brambleloop.core.models import CreatorProfile

    db = _db()
    gate = E.GATE_BY_KEY["tester_roster"]
    with db.session() as s:
        s.add(CreatorProfile(ref="prospect", invited=1))
    assert gate.open(db) is False, "a prospect opened tester_roster"
    with db.session() as s:
        s.add(CreatorProfile(ref="agreed", permissions=["test_pattern"]))
    assert gate.open(db) is True
    db = _db()
    with db.session() as s:
        s.add(CreatorProfile(ref="delivered", delivered=1))
    assert gate.open(db) is True


def test_insights_access_opens_only_on_a_recorded_reading():
    from datetime import datetime as _dt

    db = _db()
    gate = E.GATE_BY_KEY["insights_access"]
    assert gate.requirement_ids == (1, 37, 236)
    assert gate.open(db) is False
    from brambleloop.core.models import InsightsSnapshot

    with db.session() as s:
        s.add(InsightsSnapshot(keyword="crochet cardigan", search_count=1200,
                               observed_on=_dt.now(timezone.utc)))
    assert gate.open(db) is True


def test_acceptance_ruling_opens_only_on_the_owners_done_decision():
    from brambleloop.core.models import OwnerAction

    db = _db()
    gate = E.GATE_BY_KEY["acceptance_ruling"]
    assert gate.requirement_ids == (189, 221, 222, 320)
    with db.session() as s:
        s.add(OwnerAction(requirement_key="decision.api_vision_equivalence",
                          action="rule on API+vision equivalence", done=False))
        s.add(OwnerAction(requirement_key="something.else", action="x", done=True))
    assert gate.open(db) is False
    with db.session() as s:
        s.add(OwnerAction(requirement_key="decision.api_vision_equivalence",
                          action="ruled", done=True))
    assert gate.open(db) is True


def test_rendered_pages_carries_only_what_waits_on_a_browser():
    held = set(E.GATE_BY_KEY["rendered_pages"].requirement_ids)
    assert 39 in held
    moved = {1, 37, 236, 189, 221, 222, 320, 277, 281, 67, 71, 76, 86, 126, 218, 315}
    assert not held & moved, held & moved
    assert {277, 281} <= set(E.GATE_BY_KEY["model_provider"].requirement_ids)
    E._validate_gates()

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
