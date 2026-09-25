"""Reliability and cost governance: the checks that were reporting on the wrong thing.

Every test here is against a defect that was live on 2026-09-24, and they are all one
defect wearing different clothes: a number that is read from somewhere nothing writes, a
verdict computed from the absence of evidence, a ceiling that erases the row proving it was
crossed, and the same question answered three different ways in three places.

The production readings each one was found from are quoted in the test that fixes it, so a
future session can tell a regression from a disagreement about what the check should mean.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.agents.registry import BudgetExceeded, Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Agent, CostEntry, Job, JobStatus, SpendLimit)
from brambleloop.finance import governor as G  # noqa: E402
from brambleloop.finance import spend_report  # noqa: E402
from brambleloop.ops import health as H  # noqa: E402
from brambleloop.queue.durable import JobQueue, deliberate_refusal  # noqa: E402

NOW = datetime(2026, 9, 24, 19, 0, tzinfo=timezone.utc)


def _real_now():
    """The wall clock, for the tests that write through `spend_report.record`.

    `record` stamps its row with `utcnow()` and takes no timestamp argument, so a test that
    writes through it and then reads with the frozen `NOW` above is asking two different
    clocks about the same day. That passes while the frozen date happens to be today and
    fails at the next UTC midnight -- which is exactly what happened: these three checks were
    green on 2026-09-24 and failed on 2026-09-25 with nothing in the code changed.

    A test whose correctness depends on an unstated condition -- here, that the calendar has
    not moved -- is the same defect family this file was written to catch, so it is fixed
    rather than re-pinned. `NOW` stays for the checks that supply their own timestamps (the
    `CostEntry(at=NOW)` rows, the budget and signal readings); those are internally
    consistent and must not be made to depend on the clock.
    """
    return datetime.now(timezone.utc)


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _alive(at=None):
    at = at or NOW
    return {"worker_last_tick": at.isoformat(), "scheduler_last_tick": at.isoformat()}


def _gov(db, dimension):
    """`governor.spend_by` takes a Session, as the health sweep does."""
    with db.session() as s:
        return G.spend_by(s, dimension, now=NOW)


def _signal(db, name, runner_state=None, now=None):
    """`now` is overridable because some signals are read against rows written by the real
    clock. Reading those with the frozen `NOW` asks two clocks about the same day, which is
    green until the next UTC midnight and red after it. The runner state is moved with it so
    the heartbeat signals stay consistent with the instant being asked about."""
    at = now or NOW
    with db.session() as s:
        readings = H.read(s, runner_state=runner_state or _alive(at), env={}, now=at)
    return {r.signal: r for r in readings}[name]


# --- the governor was reading three of its five dimensions out of the wrong place ---------

def test_department_is_read_from_the_column_the_single_writer_actually_writes():
    """Production, 2026-09-24: `/api/spend-report` attributed all CA$75.93 across three
    departments and `/api/governor` called the same CA$75.93 100% unattributed, from the
    same rows in the same minute. One dimension, two storage locations, and the reader had
    the one nothing writes."""
    db = _db()
    spend_report.record(db, agent="market_radar", amount_cad=4.0, purpose="gallery",
                        department="intel", product_slug="nordic-hat")

    out = _gov(db, "department")
    assert out["rows"] == [{"key": "intel", "cad": 4.0, "share": 1.0}], out["rows"]
    assert out["unattributed_cad"] == 0.0

    product = _gov(db, "product")
    assert product["rows"][0]["key"] == "nordic-hat"
    assert product["unattributed_cad"] == 0.0


def test_a_row_written_before_the_columns_existed_still_attributes_from_detail():
    """The fallback is not decoration: the old rows are the ones a history question asks
    about, and dropping them would trade one silent zero for another."""
    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="a", amount_cad=2.0, kind="llm", at=NOW,
                        detail={"department": "creative", "product": "old-slug"}))

    assert _gov(db, "department")["rows"][0]["key"] == "creative"
    assert _gov(db, "product")["rows"][0]["key"] == "old-slug"


def test_a_dimension_nothing_writes_says_so_instead_of_reading_as_sloppiness():
    """100% unattributed reads as call sites that forgot. Nothing in this system can tag a
    cost row with an experiment -- there is no column and no writer -- and that is a gap in
    a different place, fixed by different work."""
    db = _db()
    spend_report.record(db, agent="a", amount_cad=1.0, purpose="p", department="intel")

    out = _gov(db, "experiment")
    assert out["has_writer"] is False
    assert out["unattributed_cad"] == 1.0
    assert "cannot be tagged" in out["why_unattributed"]
    assert _gov(db, "department")["has_writer"] is True


def test_every_dimension_says_where_its_number_came_from():
    """The reconciliation guard cannot catch this class of fault -- a dimension that reads
    nothing puts the whole bill in `unattributed`, where it still sums to the invoice. So
    the source is reported instead."""
    db = _db()
    spend_report.record(db, agent="a", amount_cad=1.0, purpose="p")
    for dimension in G.DIMENSIONS:
        assert _gov(db, dimension)["read_from"]


# --- the daily ceiling used to delete the evidence that it had been crossed ---------------

def test_a_breached_daily_ceiling_still_records_what_was_spent():
    """The row was written after the check, so the one call that crossed the ceiling wrote
    nothing at all. The money had already left -- this is called after the provider answers
    -- and the monthly ceiling is computed from exactly these rows, so a daily breach
    lowered the number the monthly ceiling is checked against."""
    db = _db()
    reg = Registry(db)
    reg.seed_defaults()
    with db.session() as s:
        s.scalar(__import__("sqlalchemy").select(Agent).where(Agent.name == "validator"))

    reg.record_cost("validator", 0.4)
    try:
        reg.record_cost("validator", 5.0)   # validator's ceiling is CA$1.00 a day
    except BudgetExceeded:
        pass
    else:  # pragma: no cover - the refusal must still happen
        raise AssertionError("the ceiling did not refuse")

    assert reg.spend_today("validator") == 5.4, "the breaching spend is missing from the bill"


def test_the_refusal_itself_is_unchanged():
    """Recording the row does not permit the spend. The caller still raises, the job still
    dead-letters, and nothing new is allowed through."""
    db = _db()
    reg = Registry(db)
    reg.seed_defaults()
    raised = False
    try:
        reg.record_cost("validator", 99.0)
    except BudgetExceeded:
        raised = True
    assert raised


def test_the_daily_window_is_the_utc_day_not_the_hosts_local_one():
    """The rows are stamped with `utcnow`. Summing them against the host's local day makes
    the ceiling reset at an hour that depends on a container setting nobody records."""
    db = _db()
    reg = Registry(db)
    reg.seed_defaults()
    now = datetime.now(timezone.utc)
    with db.session() as s:
        s.add(CostEntry(agent="validator", amount_cad=0.25, kind="llm", at=now))
        s.add(CostEntry(agent="validator", amount_cad=9.0, kind="llm",
                        at=now - timedelta(days=2)))
    assert reg.spend_today("validator") == 0.25


# --- the monthly ceiling could not see a batch's own spend --------------------------------

def test_a_batch_checks_each_call_against_what_the_batch_has_already_spent():
    """`check_budget` reads the month from cost rows, and the callers that spend the most
    write one row per run rather than one per call: `intel.vision` judged about twenty-one
    images behind a single ledger row on 2026-09-24. So every call after the first was
    checked against the month as it stood before the loop began, and a guard whose whole
    purpose is to refuse before the call was refusing only the first call of each batch."""
    from brambleloop.gateway import anthropic as gw

    db = _db()
    spend_report.record(db, agent="market_radar", amount_cad=99.0, purpose="p")

    first = gw.check_budget(db, model="claude-haiku-4-5", input_tokens=200_000,
                            max_tokens=100, now=NOW)
    assert first["estimate_cad"] > 0.25, "the fixture needs a call big enough to matter"

    # The old behaviour: the same call again, with the run's own spend invisible.
    gw.check_budget(db, model="claude-haiku-4-5", input_tokens=200_000, max_tokens=100,
                    now=NOW)

    raised = False
    try:
        gw.check_budget(db, model="claude-haiku-4-5", input_tokens=200_000, max_tokens=100,
                        now=NOW, uncommitted_cad=first["estimate_cad"] * 3)
    except gw.BudgetExceeded as exc:
        raised = True
        assert "not yet billed" in str(exc), str(exc)
    assert raised, "a batch's own unbilled spend did not count against the ceiling"


def test_a_caller_that_bills_every_call_is_unaffected():
    """Passing nothing is the old behaviour, which is correct for a caller whose every call
    writes its own row."""
    from brambleloop.gateway import anthropic as gw

    db = _db()
    out = gw.check_budget(db, model="claude-haiku-4-5", input_tokens=1000, max_tokens=100,
                          now=NOW)
    assert out["committed_cad"] == out["spent_cad"] == 0.0


def test_the_headroom_it_reports_is_the_headroom_after_the_batch():
    """A run that reported headroom ignoring its own spend would hand the next decision a
    number that is already wrong."""
    from brambleloop.gateway import anthropic as gw

    db = _db()
    out = gw.check_budget(db, model="claude-haiku-4-5", input_tokens=1000, max_tokens=100,
                          now=NOW, uncommitted_cad=10.0)
    assert out["committed_cad"] == 10.0
    assert out["headroom_cad"] == round(100.0 - 10.0 - out["estimate_cad"], 6)


# --- nothing could see what an agent had actually spent today ----------------------------

def test_spend_today_is_reported_beside_the_ceiling_it_is_supposed_to_respect():
    """`Agent.daily_cost_ceiling_cad` is consulted by `registry.record_cost` and by nothing
    else. `spend_report.record` -- the single writer nearly every real call goes through --
    never looks at it, so an overrun had no surface anywhere in the system."""
    db = _db()
    Registry(db).seed_defaults()
    spend_report.record(db, agent="market_radar", amount_cad=8.70,
                        purpose="gallery_observation", department="intel")

    out = spend_report.per_agent_today(db, now=_real_now())
    over = {row["agent"]: row for row in out["over"]}
    assert "market_radar" in over, "an agent at twice its ceiling was not reported"
    assert over["market_radar"]["daily_ceiling_cad"] == 4.0
    assert over["market_radar"]["spent_today_cad"] == 8.70


def test_spend_by_a_name_that_is_not_an_agent_is_reported_rather_than_dropped():
    """A spender with no agent row has no ceiling at all, which is the one case worth
    surfacing hardest. Reporting only the registered agents would hide it perfectly."""
    db = _db()
    Registry(db).seed_defaults()
    spend_report.record(db, agent="ghost_department", amount_cad=3.0, purpose="p")
    out = spend_report.per_agent_today(db, now=_real_now())
    assert [r["agent"] for r in out["spenders_with_no_agent_row"]] == ["ghost_department"]


def test_an_agent_inside_its_ceiling_is_not_reported_as_over():
    db = _db()
    Registry(db).seed_defaults()
    spend_report.record(db, agent="market_radar", amount_cad=1.0, purpose="p")
    assert spend_report.per_agent_today(db, now=_real_now())["over"] == []


# --- the spend signal was green because there were no ceilings ----------------------------

def test_no_configured_scope_is_not_evidence_that_the_ceilings_are_on():
    """Production, 2026-09-24: `spend` read `{"limits": 0, "paused": []}` and reported
    healthy. Nothing in this system calls `SpendGuard.set_limit`, so the check was passing
    by having nothing to look at -- and the more scopes anybody forgets, the greener it
    got."""
    db = _db()
    reading = _signal(db, "spend")
    assert reading.evidence["limits"] == 0
    assert "no_scope_is_configured" in reading.evidence
    assert "not evidence that scoped spending is safe" in reading.evidence[
        "no_scope_is_configured"]


def test_the_spend_signal_reports_the_ceiling_that_is_actually_live():
    """The monthly model ceiling is the control that refuses before every call, and the
    signal that claimed to watch "the ceilings" had never read it."""
    db = _db()
    spend_report.record(db, agent="a", amount_cad=12.0, purpose="p")
    reading = _signal(db, "spend")
    assert reading.evidence["model_spend_this_month_cad"] == 12.0
    assert reading.evidence["model_ceiling_cad"] == 100.0
    assert reading.evidence["share_of_model_ceiling"] == 0.12
    assert reading.state == H.HEALTHY, "being inside the ceiling is not a fault"


def test_an_agent_over_its_daily_ceiling_degrades_the_spend_signal():
    db = _db()
    Registry(db).seed_defaults()
    spend_report.record(db, agent="validator", amount_cad=4.0, purpose="p")  # ceiling 1.00
    # Written through `record`, so it carries the real clock; read at the same instant.
    reading = _signal(db, "spend", now=_real_now())
    assert reading.state == H.DEGRADED
    assert reading.evidence["agents_over_their_daily_ceiling"][0]["agent"] == "validator"


def test_a_paused_scope_still_degrades_the_spend_signal():
    """The check that was there is kept. Nothing above replaces it."""
    db = _db()
    with db.session() as s:
        s.add(SpendLimit(scope="ads:meta", daily_cap_cad=5.0, lifetime_cap_cad=10.0,
                         paused=True))
    reading = _signal(db, "spend")
    assert reading.state == H.DEGRADED and reading.evidence["paused"] == ["ads:meta"]


def test_the_spend_signal_says_what_it_cannot_see():
    db = _db()
    assert "never written to a cost row" in _signal(db, "spend").evidence[
        "what_this_cannot_see"]


# --- nothing was watching the disk --------------------------------------------------------

def test_an_unreported_disk_is_unknown_rather_than_healthy():
    """The sweep reads the running container's own measurement, for the reason the worker
    heartbeat does: the process answering a request is not necessarily the one doing the
    work. Absent must never read as fine."""
    reading = _signal(_db(), "disk")
    assert reading.state == H.UNKNOWN and reading.evidence == {"reported": False}


def test_a_disk_with_no_room_for_the_next_write_is_degraded():
    db = _db()
    state = _alive()
    state["disk"] = {"filesystems": {"tmp": {"free_gb": 0.2, "total_gb": 8.0,
                                             "free_share": 0.025}},
                     "temp_dirs_left_behind": 400}
    reading = _signal(db, "disk", runner_state=state)
    assert reading.state == H.DEGRADED and "0.20 GB free" in reading.why


def test_a_large_disk_that_is_ninety_percent_used_is_not_a_fault():
    """The threshold is absolute on purpose. Ten percent of a 270 GB volume is 27 GB, which
    is not a risk to a workload whose largest write is a few-megabyte render -- and a signal
    that goes yellow on a normal day is a signal people turn off."""
    db = _db()
    state = _alive()
    state["disk"] = {"filesystems": {"tmp": {"free_gb": 27.0, "total_gb": 270.0,
                                             "free_share": 0.1}}}
    assert _signal(db, "disk", runner_state=state).state == H.HEALTHY


def test_the_container_counts_the_temporary_directories_its_own_handlers_left():
    """`tempfile.mkdtemp` never removes what it creates and the handlers that call it run on
    a cadence. The count is reported, never cleaned: deleting a directory another process is
    writing into loses that job's work."""
    tmp = tempfile.mkdtemp()
    old = os.environ.get("TMPDIR")
    os.environ["TMPDIR"] = tmp
    try:
        tempfile.tempdir = None
        for name in ("generated-abc", "reference-pack-xyz", "someone-elses-dir"):
            os.mkdir(os.path.join(tmp, name))
        facts = H.disk_facts()
    finally:
        tempfile.tempdir = None
        if old is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = old
        shutil.rmtree(tmp, ignore_errors=True)

    assert facts["temp_dirs_left_behind"] == 2, facts["temp_dir_prefixes"]
    assert set(facts["temp_dir_prefixes"]) == {"generated-", "reference-pack-"}


# --- one question, three answers ----------------------------------------------------------

def test_a_stand_aside_is_a_refusal_everywhere_or_nowhere():
    """Production, 2026-09-24: `/api/status` reported `dead_letter_defects: 1` while
    `/api/verify` reported zero unexpected dead letters, about the same row, in the same
    minute. `durable.py` says this value is "defined once because it is asked in two
    places"; it was in fact answered three ways."""
    db = _db()
    stand_aside = ("RuntimeError: this job asked for pack 'v4' and this build produces "
                   "'v16'. Failing rather than producing the wrong one, so another replica "
                   "running the right build can take it")
    with db.session() as s:
        s.add(Job(agent="creative_director", job_type="creative.model_reference_pack",
                  status=JobStatus.DEAD, inputs={}, last_error=stand_aside))
        s.add(Job(agent="store_operator", job_type="store.publish", status=JobStatus.DEAD,
                  inputs={}, last_error="capability not enabled: shadow mode"))

    assert deliberate_refusal("creative.model_reference_pack", stand_aside) is True

    with db.session() as s:
        out = H.remediation(s, H.read(s, runner_state=_alive(), now=NOW))
    conditions = {h["condition"]: h for h in out["repaired_elsewhere"]}
    assert conditions["deliberate_refusals"]["count"] == 2
    assert "dead_letters" not in conditions, "a refusal was filed as a defect to explain"


def test_a_genuine_defect_is_still_a_defect():
    """The unification must not swallow the case the console exists for."""
    db = _db()
    with db.session() as s:
        s.add(Job(agent="a", job_type="t", status=JobStatus.DEAD, inputs={},
                  last_error="TypeError: something genuinely broke"))
    with db.session() as s:
        out = H.remediation(s, H.read(s, runner_state=_alive(), now=NOW))
    conditions = {h["condition"]: h for h in out["repaired_elsewhere"]}
    assert conditions["dead_letters"]["count"] == 1


# --- a restart count that could not count restarts ------------------------------------------

def _boot(db, commit, at):
    from brambleloop.core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=H.BOOT_ACTION, at=at,
                       detail={"commit": commit, "at": at.isoformat()}))


def test_a_container_replaced_on_the_same_commit_is_a_restart():
    """`runner.STATE.worker_restarts` counts the worker thread's restart loop inside one
    process and resets to zero with that process. Production reported `restarts: 0` across
    three different `worker_started_at` values inside forty-seven minutes on 2026-09-24.
    Those three were deploys -- and nothing could have told them apart from a container
    dying every twenty minutes, which is the case a restart count exists for."""
    db = _db()
    _boot(db, "aaa", NOW - timedelta(hours=3))
    _boot(db, "aaa", NOW - timedelta(hours=2))
    _boot(db, "bbb", NOW - timedelta(hours=1))

    with db.session() as s:
        out = H.container_starts(s, now=NOW)
    assert out["starts"] == 3
    assert out["distinct_commits"] == 2
    assert out["restarts_on_a_commit_already_seen"] == 1


def test_a_deploy_is_not_counted_as_a_restart():
    db = _db()
    _boot(db, "aaa", NOW - timedelta(hours=2))
    _boot(db, "bbb", NOW - timedelta(hours=1))
    with db.session() as s:
        assert H.container_starts(s, now=NOW)["restarts_on_a_commit_already_seen"] == 0


def test_boots_outside_the_window_are_not_counted():
    db = _db()
    _boot(db, "aaa", NOW - timedelta(days=3))
    _boot(db, "aaa", NOW - timedelta(hours=1))
    with db.session() as s:
        out = H.container_starts(s, now=NOW)
    assert out["starts"] == 1 and out["restarts_on_a_commit_already_seen"] == 0


# --- work that could be silently lost ------------------------------------------------------

def test_an_expired_lease_is_reclaimed_while_there_is_still_pending_work():
    """The reclaim only ran when the pending query came back empty, so a job whose worker
    died holding the lease was recoverable exactly while the queue was idle -- and never
    under a backlog, which is when a worker is most likely to be killed. Nothing reports a
    job stuck in RUNNING, so it is not a delay anybody sees; it is work that stops
    existing."""
    q = JobQueue(_db())
    orphan = q.enqueue("orchestrator", "ops.heartbeat", {})
    claimed = q.claim("worker-that-died")
    assert claimed.id == orphan.id
    with q.db.session() as s:
        s.get(Job, orphan.id).lease_expires_at = datetime.now(timezone.utc) - timedelta(
            minutes=10)

    q.enqueue("orchestrator", "ops.queue_check", {})   # newer pending work in front

    again = q.claim("worker-2")
    assert again.id == orphan.id, "the orphan stayed RUNNING behind newer pending work"


def test_an_orphan_that_keeps_dying_still_dead_letters_rather_than_spinning():
    """Taking the reclaim first must not turn one broken job into a permanent retry loop.
    `claim` increments `attempts`, so it reaches `max_attempts` like any other job."""
    q = JobQueue(_db())
    job = q.enqueue("orchestrator", "ops.heartbeat", {}, max_attempts=2)
    for _ in range(3):
        claimed = q.claim("w")
        if claimed is None:
            break
        with q.db.session() as s:
            s.get(Job, claimed.id).lease_expires_at = datetime.now(
                timezone.utc) - timedelta(minutes=10)
    assert q.get(job.id).status == JobStatus.DEAD


def test_counts_are_counted_by_the_database_rather_than_loaded_into_python():
    """`/api/status` built every count by materialising every matching row, six times, on
    the endpoint the console polls -- work that grows for as long as the company runs.
    Production completed about 900 jobs a day on 2026-09-24."""
    q = JobQueue(_db())
    q.enqueue("orchestrator", "ops.heartbeat", {})
    q.enqueue("orchestrator", "ops.queue_check", {})
    q.claim("w")

    statements: list[str] = []
    from sqlalchemy import event

    def _seen(conn, cursor, statement, *a):  # noqa: ANN001
        statements.append(statement)

    event.listen(q.db.engine, "before_cursor_execute", _seen)
    try:
        counts = q.counts()
    finally:
        event.remove(q.db.engine, "before_cursor_execute", _seen)

    assert counts["pending"] == 1 and counts["running"] == 1
    assert counts["dead"] == 0 and counts["done"] == 0
    assert set(counts) == {s.value for s in JobStatus}

    selects = [x for x in statements if x.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 1, selects
    assert "count" in selects[0].lower(), selects[0]


# --- the lease lock several sessions share --------------------------------------------------

def _lock_dir():
    tmp = tempfile.mkdtemp(prefix="lockcheck-")
    shutil.copy(ROOT.parent / "ops" / "lock.py", os.path.join(tmp, "lock.py"))
    return tmp


def _lock(tmp, *args):
    return subprocess.run([sys.executable, os.path.join(tmp, "lock.py"), *args],
                          capture_output=True, text=True)


def test_two_sessions_cannot_both_hold_the_lease():
    """Read-then-write is two steps and not a lock: both sessions find no lease, both write
    one, the second overwrites the first, and both believe they hold it. Several
    departments now run at once, so this is a live shape."""
    tmp = _lock_dir()
    try:
        assert _lock(tmp, "acquire", "session-a").returncode == 0
        second = _lock(tmp, "acquire", "session-b")
        assert second.returncode == 3, second.stdout
        held = json.loads(_lock(tmp, "status").stdout)
        assert held["session"] == "session-a"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_a_long_session_keeps_its_lease_by_saying_it_is_alive():
    """Staleness was measured from the acquisition time, so any session running longer than
    the stale window was declared dead while it ran and its work could be taken over
    underneath it."""
    tmp = _lock_dir()
    try:
        _lock(tmp, "acquire", "session-a")
        path = os.path.join(tmp, "LOCK")
        lease = json.loads(open(path).read())
        old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        lease["acquired_utc"] = old
        lease["heartbeat_utc"] = old
        open(path, "w").write(json.dumps(lease))

        assert _lock(tmp, "refresh", "session-a").returncode == 0
        assert _lock(tmp, "acquire", "session-b").returncode == 3
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_a_lease_nobody_is_refreshing_is_still_taken_over():
    """The heartbeat must not turn the stale rule off: a session that actually died has to
    stop blocking every session after it."""
    tmp = _lock_dir()
    try:
        _lock(tmp, "acquire", "session-a")
        path = os.path.join(tmp, "LOCK")
        lease = json.loads(open(path).read())
        lease["heartbeat_utc"] = (datetime.now(timezone.utc) - timedelta(
            hours=4)).isoformat()
        open(path, "w").write(json.dumps(lease))

        taken = _lock(tmp, "acquire", "session-b")
        assert taken.returncode == 0 and "taken over" in taken.stdout
        assert json.loads(_lock(tmp, "status").stdout)["session"] == "session-b"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_an_unreadable_lease_does_not_wedge_every_session_after_it():
    """A malformed timestamp used to raise inside the acquire path. A lock file nobody can
    parse must not be able to lock everybody out, and must not crash the caller either --
    the exit code is the answer."""
    tmp = _lock_dir()
    try:
        open(os.path.join(tmp, "LOCK"), "w").write("{not json")
        out = _lock(tmp, "acquire", "session-a")
        assert out.returncode == 0, out.stderr
        assert json.loads(_lock(tmp, "status").stdout)["session"] == "session-a"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_the_holder_re_acquiring_is_not_refused_its_own_lease():
    tmp = _lock_dir()
    try:
        assert _lock(tmp, "acquire", "session-a").returncode == 0
        assert _lock(tmp, "acquire", "session-a").returncode == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
