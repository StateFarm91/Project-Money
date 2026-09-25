"""Enforcement, reservation, retention and temporary files: the second reliability wave.

The 2026-09-24 audit fixed what the system could *see* and left four things it could not
*stop*. Each test here is against one of those, and each says which production reading or
which owner ruling it comes from.

The governing ruling, 2026-09-25, is the owner's, and two of these tests exist only because of
its second half:

    "Keep the CA$4.00/day market_radar ceiling. Do NOT raise it to fit the existing cadence.
     Adapt/slow/prioritize the gallery cadence so it fits inside the existing authorized
     budget. Global/monthly spend remains authoritative; per-agent ceilings are permissions,
     not additive budgets."

So a per-agent ceiling refuses as a permission and names itself as one, the monthly ceiling is
checked first because it is the budget, and twenty-four agents declaring about CA$57 a day
against a CA$100 month is not an over-commitment and nothing here treats it as one.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core import workspace  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, CostEntry, Job, JobStatus, SpendReservation)
from brambleloop.finance import reservations, spend_policy, spend_report  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.intel import vision  # noqa: E402
from brambleloop.ops import health as H  # noqa: E402
from brambleloop.ops import retention  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime.worker import CADENCES, cadence_seconds  # noqa: E402

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
CHEAP_MODEL = "claude-haiku-4-5"


def _db():
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _spend(db, agent, cad, *, purpose="test", at=None, kind="llm"):
    """A cost row at a chosen instant. `spend_report.record` stamps its own `at`, and a test
    that needs a specific day has to write the timestamp rather than hope the calendar
    cooperates -- which is the failure mode the previous suite documented and fixed."""
    with db.session() as s:
        s.add(CostEntry(agent=agent, amount_cad=cad, kind=kind, purpose=purpose,
                        at=at or NOW))


# ---------------------------------------------------------------------------
# 1. The cadence is derived from the ceiling rather than declared beside it


def test_the_gallery_batch_is_computed_from_the_ceiling_and_fits_inside_it():
    """`spend_policy.ALLOCATION` stated the gallery cadence costs CA$8.70 a day while
    `agents.registry` gave `market_radar` CA$4.00. Two owner-derived numbers, two files, no
    reconciliation. The owner ruled: keep the CA$4.00. So the batch is now derived, and a
    day of derived batches has to fit inside the ceiling it was derived from."""
    db = _db()
    unit = vision.per_image_estimate_cad()
    period = cadence_seconds("gallery_analysis")
    fit = spend_policy.work_that_fits(
        db, agent=vision.AGENT, purpose=vision.TASK,
        period_seconds=period, unit_cost_cad=unit, now=NOW)

    assert fit["units"] >= 1, fit
    runs = spend_policy.runs_per_day(period)
    ceiling = gw.agent_daily_ceiling(db, vision.AGENT)["daily_ceiling_cad"]
    assert ceiling == 4.0, "the owner's ruling is to keep this at CA$4.00"
    day_cost = fit["units"] * unit * runs
    assert day_cost <= ceiling, (
        f"a day of derived batches costs CA${day_cost:.2f} against a CA${ceiling:.2f} "
        f"ceiling. The batch is supposed to be sized to fit, not to be checked afterwards")
    # And it is a real slowdown rather than a relabelling of the old number.
    assert fit["units"] * runs < 300, (
        "the old cadence was 25 images every two hours -- 300 a day. A derived batch that "
        "still came to 300 would mean the ceiling had been fitted to the cadence")


def test_there_is_no_images_per_run_constant_left_to_drift():
    """The defect was not the value 25; it was that a value existed in a second place at all.
    A corrected literal drifts again the next time either side of it moves."""
    source = (ROOT / "src" / "brambleloop" / "runtime" / "release.py").read_text()
    # An assignment at module level, not the word in the comment that records why it is gone.
    assert not re.search(r"^GALLERY_BATCH\s*=", source, re.M), (
        "an images-per-run constant is back. The batch has to be computed from the ceiling, "
        "or the two numbers can disagree again")
    assert "spend_policy.work_that_fits" in source


def test_the_batch_shrinks_when_the_agents_other_cadences_have_spent_the_day():
    """`market_radar` also runs the culture sweep, the radar scans and the Etsy probe. A
    gallery batch that ignored them would take the whole permission and leave the rest of the
    agent's day refused."""
    db = _db()
    unit = vision.per_image_estimate_cad()
    before = spend_policy.work_that_fits(
        db, agent=vision.AGENT, purpose=vision.TASK, period_seconds=7200,
        unit_cost_cad=unit, now=NOW)["units"]
    _spend(db, vision.AGENT, 3.90, purpose="culture.sweep")
    after = spend_policy.work_that_fits(
        db, agent=vision.AGENT, purpose=vision.TASK, period_seconds=7200,
        unit_cost_cad=unit, now=NOW)["units"]
    assert before > 0 and after == 0, (before, after)


def test_a_run_that_fits_nothing_names_the_ceiling_that_stopped_it():
    """Three different stops have three different answers -- wait for tomorrow, wait for the
    month, ask the owner -- so "capped" without a name is unactionable."""
    db = _db()
    _spend(db, vision.AGENT, 4.0, purpose="culture.sweep")
    fit = spend_policy.work_that_fits(
        db, agent=vision.AGENT, purpose=vision.TASK, period_seconds=7200,
        unit_cost_cad=vision.per_image_estimate_cad(), now=NOW)
    assert fit["units"] == 0
    assert fit["binding_ceiling"] == "agent_daily_ceiling", fit
    assert "still queued" in fit["why"], fit["why"]
    assert "agent_daily_ceiling" in fit["bounds"]
    assert "monthly_model_ceiling" in fit["bounds"]


def test_the_batch_never_exceeds_the_months_remaining_headroom():
    """The month is the authoritative budget, so a batch is never *planned* larger than the
    room left in it even when the agent's daily permission has plenty."""
    db = _db()
    _spend(db, "creative_director", 99.9, purpose="image_benchmark_judging")
    fit = spend_policy.work_that_fits(
        db, agent=vision.AGENT, purpose=vision.TASK, period_seconds=7200,
        unit_cost_cad=vision.per_image_estimate_cad(), now=NOW)
    assert fit["binding_ceiling"] == "monthly_model_ceiling", fit
    assert fit["units"] == 1, fit  # CA$0.10 left, one image at CA$0.062


def test_the_batch_and_the_guard_are_sized_on_the_same_arithmetic():
    """A batch sized on the measured mean against a guard enforced on the padded estimate is
    two numbers disagreeing about the same money -- which is the whole defect, one layer
    down."""
    _, tier = __import__("brambleloop.gateway.routing", fromlist=["route"]).route(vision.TASK)
    direct = gw.estimate_cad(
        tier.model,
        input_tokens=len(vision.analysis_prompt()) // 4 + gw.IMAGE_TOKENS_ESTIMATE,
        output_tokens=vision.ANALYSIS_MAX_TOKENS)
    assert vision.per_image_estimate_cad() == direct


def test_the_period_is_read_from_the_schedule_that_fires_it():
    db = _db()
    assert cadence_seconds("gallery_analysis") == 2 * 60 * 60
    try:
        cadence_seconds("not_a_cadence")
        raise AssertionError("a cadence nothing schedules has no rate to report")
    except KeyError as exc:
        assert "not scheduled" in str(exc)


# ---------------------------------------------------------------------------
# 2. Per-agent enforcement, before the call, as a permission


def test_an_agent_over_its_daily_ceiling_is_refused_before_the_call():
    """Production, 2026-09-24: `market_radar` averaged CA$3.94 a day against a CA$4.00
    ceiling that was consulted by exactly one writer and bypassed by nine. This is the
    behaviour change -- it stops work that used to run, on purpose."""
    db = _db()
    _spend(db, "market_radar", 3.999, purpose="gallery_observation")
    try:
        gw.check_budget(db, model=CHEAP_MODEL, input_tokens=100_000, max_tokens=1000,
                        now=NOW, agent="market_radar")
        raise AssertionError("the daily ceiling did not bind")
    except gw.AgentCeilingExceeded as exc:
        assert "market_radar" in str(exc)
        assert "daily permission, not the budget" in str(exc), str(exc)
        assert "next UTC day" in str(exc)


def test_the_agent_refusal_says_the_month_still_has_room_because_it_does():
    """The owner's ruling: per-agent ceilings are permissions, not additive budgets. A
    refusal that read like the company was out of money would be a false statement and would
    send somebody to raise the wrong ceiling."""
    db = _db()
    _spend(db, "validator", 1.5, purpose="cir.compile")  # ceiling CA$1.00
    try:
        gw.check_budget(db, model=CHEAP_MODEL, input_tokens=1000, max_tokens=100,
                        now=NOW, agent="validator")
        raise AssertionError("the daily ceiling did not bind")
    except gw.AgentCeilingExceeded as exc:
        text = str(exc)
        assert "CA$98" in text, text   # CA$100 ceiling, CA$1.50 spent
        assert "cheaper model" not in text


def test_the_monthly_ceiling_is_checked_first_because_it_is_the_budget():
    """Both ceilings crossed at once has to report the month, not the agent: the month is the
    authoritative figure and the one whose answer is an owner decision."""
    db = _db()
    _spend(db, "validator", 99.99, purpose="cir.compile")
    try:
        gw.check_budget(db, model=CHEAP_MODEL, input_tokens=100_000, max_tokens=1000,
                        now=NOW, agent="validator")
        raise AssertionError("neither ceiling bound")
    except gw.AgentCeilingExceeded as exc:  # noqa: F841
        raise AssertionError(
            "the agent permission was reported while the month was over its ceiling. The "
            f"month is authoritative and must be named first: {exc}")
    except gw.BudgetExceeded as exc:
        assert "ceiling of CA$100.00" in str(exc), str(exc)


def test_an_agent_permission_is_a_subclass_so_every_existing_refusal_still_refuses():
    """Six call sites and the worker already catch `BudgetExceeded`. A new exception outside
    that hierarchy would be a guard that raises past every handler written to stop it."""
    assert issubclass(gw.AgentCeilingExceeded, gw.BudgetExceeded)


def test_a_spender_the_registry_has_never_heard_of_gets_no_invented_ceiling():
    """Production attributes spend to `gateway`, `publishing` and `intel`, none of which is a
    registered agent. Enforcing a number nobody authorised would be worse than the gap:
    `spend_report.per_agent_today` reports them, and this refuses to make one up."""
    db = _db()
    _spend(db, "gateway", 50.0, purpose="model.probe")
    assert gw.agent_daily_ceiling(db, "gateway") is None
    out = gw.check_budget(db, model=CHEAP_MODEL, input_tokens=1000, max_tokens=100,
                          now=NOW, agent="gateway")
    assert out["agent_permission"] is None
    assert any(r["agent"] == "gateway"
               for r in spend_report.per_agent_today(db)["spenders_with_no_agent_row"])


def test_the_permission_and_the_month_are_asked_about_the_same_day():
    """`registry.spend_today` read the wall clock while `check_budget` took a timestamp, so a
    caller that said which instant it meant got a daily ceiling computed from a different day.
    That agrees with itself while the frozen date happens to be today and stops agreeing after
    the next UTC midnight -- a defect this repository has already had twice. Asked here about a
    day that is deliberately neither today nor the day of the rows."""
    db = _db()
    _spend(db, "validator", 5.0, purpose="cir.compile", at=NOW)
    yesterday = NOW - timedelta(days=1)
    assert Registry(db).spend_today("validator", now=yesterday) == 0.0
    # The same CA$5.00 is over the CA$1.00 ceiling today and invisible the day before it.
    assert gw.agent_daily_ceiling(db, "validator", now=NOW)["spent_today_cad"] == 5.0
    assert gw.agent_daily_ceiling(db, "validator",
                                  now=yesterday)["spent_today_cad"] == 0.0
    out = gw.check_budget(db, model=CHEAP_MODEL, input_tokens=1000, max_tokens=100,
                          now=yesterday, agent="validator")
    assert out["agent_permission"]["spent_today_cad"] == 0.0


def test_an_agent_whose_run_is_holding_unbilled_spend_is_refused_on_the_total():
    """`intel.vision` bills once per run, so the daily ceiling has to count what the run is
    holding as well as what the ledger has -- the same in-batch hole the monthly ceiling
    had."""
    db = _db()
    _spend(db, "market_radar", 3.0, purpose="gallery_observation")
    try:
        gw.check_budget(db, model=CHEAP_MODEL, input_tokens=100_000, max_tokens=1000,
                        now=NOW, agent="market_radar", uncommitted_cad=0.95)
        raise AssertionError("the unbilled half of the run was not counted")
    except gw.AgentCeilingExceeded as exc:
        assert "unbilled in this run" in str(exc), str(exc)


# ---------------------------------------------------------------------------
# 3. The durable aggregate reservation


def test_a_check_writes_a_reservation_before_the_call_and_another_process_sees_it():
    """The audit's §5, left open: "no reservation is written before a call, the estimate is
    recorded after the fact, so overshoot is bounded only by (concurrent callers x largest
    estimate)". Two holders, one month, and the second must see the first's claim."""
    db = _db()
    first = gw.check_budget(db, model=CHEAP_MODEL, input_tokens=1000, max_tokens=100,
                            now=NOW, agent="market_radar", holder="host:1:1")
    assert first["reservation_id"] is not None
    assert first["reserved_by_others_cad"] == 0.0

    second = gw.check_budget(db, model=CHEAP_MODEL, input_tokens=1000, max_tokens=100,
                             now=NOW, agent="market_radar", holder="host:2:1")
    assert second["reserved_by_others_cad"] == first["estimate_cad"], second
    assert second["reserved_by_others_count"] == 1


def test_the_reservation_is_what_refuses_the_second_of_two_concurrent_callers():
    """The overshoot this closes. Both callers read the same month; without a row written in
    between, both find room and both spend."""
    db = _db()
    _spend(db, "market_radar", 99.0, purpose="gallery_observation")
    # A big enough estimate that two of them cross the ceiling and one does not.
    a = gw.check_budget(db, model=CHEAP_MODEL, input_tokens=350_000, max_tokens=1000,
                        now=NOW, holder="host:1:1")
    assert 0.5 < a["estimate_cad"] < 1.0, (
        "the point of the sizing is that one call fits in the CA$1.00 left and two do not")
    try:
        gw.check_budget(db, model=CHEAP_MODEL, input_tokens=350_000, max_tokens=1000,
                        now=NOW, holder="host:2:1")
        raise AssertionError(
            "the second caller was authorised against a month that did not include the "
            "first caller's live reservation. That is the unbounded overshoot")
    except gw.BudgetExceeded as exc:
        assert "reserved right now by 1 other caller" in str(exc), str(exc)


def test_a_caller_does_not_reserve_against_itself():
    """A batching loop passes its own in-flight spend as `uncommitted_cad`. Counting its own
    reservations too would charge it twice and refuse work the ceiling has room for -- and a
    guard that refuses correct work is a guard somebody turns off."""
    db = _db()
    for _ in range(5):
        gw.check_budget(db, model=CHEAP_MODEL, input_tokens=1000, max_tokens=100,
                        now=NOW, holder="host:1:1")
    out = gw.check_budget(db, model=CHEAP_MODEL, input_tokens=1000, max_tokens=100,
                          now=NOW, holder="host:1:1")
    assert out["reserved_by_others_cad"] == 0.0, out
    held = reservations.outstanding(db, exclude_holder="host:1:1", now=NOW)
    assert held["own_holder_count"] == 6 and held["count"] == 0


def test_a_reservation_whose_holder_died_expires_rather_than_charging_for_ever():
    """The phantom charge. Railway replaces this container several times an hour, so a holder
    dying between claiming and spending is the normal case. A reservation that outlived its
    holder must stop counting, or one killed container closes the ceiling for the month."""
    db = _db()
    reservations.reserve(db, amount_cad=90.0, holder="dead:1:1", ttl_seconds=60, now=NOW)
    during = reservations.outstanding(db, now=NOW + timedelta(seconds=30))
    assert during["cad"] == 90.0

    after = reservations.outstanding(db, now=NOW + timedelta(seconds=120))
    assert after["cad"] == 0.0, "an expired reservation is not money anybody is about to spend"
    assert after["expired_unreleased_cad"] == 90.0, (
        "it must still be reported: a reservation nobody released is the evidence that a "
        "call site does not release what it takes")

    # And the ceiling agrees with the reader.
    out = gw.check_budget(db, model=CHEAP_MODEL, input_tokens=1000, max_tokens=100,
                          now=NOW + timedelta(seconds=120), holder="host:9:9")
    assert out["reserved_by_others_cad"] == 0.0
    assert out["expired_unreleased_cad"] == 90.0


def test_release_returns_the_money_and_records_what_the_call_actually_cost():
    db = _db()
    out = gw.check_budget(db, model=CHEAP_MODEL, input_tokens=1000, max_tokens=100,
                          now=NOW, holder="host:1:1")
    # Released at the instant it was reserved at. Without `now` this line asserted that a
    # reservation stamped at the frozen NOW was still live against the real wall clock, which
    # was true only while NOW happened to be within the 300-second TTL of the real date. It
    # passed on the day it was written and expired afterwards -- the same defect as the test
    # fixed on 2026-09-25 that expired at midnight, and the reason `release_reservation` now
    # takes the instant.
    assert gw.release_reservation(db, out["reservation_id"], actual_cad=0.0004,
                                  now=NOW) is True
    assert reservations.outstanding(db, now=NOW)["cad"] == 0.0
    # Released, not deleted: the reservation beside its bill is the reconciliation the
    # owner's spend-accounting instruction asked for and never had.
    with db.session() as s:
        row = s.get(SpendReservation, out["reservation_id"])
        assert row.released_at is not None and row.actual_cad == 0.0004
    # Releasing twice, or releasing nothing, is not an error: callers release in a `finally`.
    assert gw.release_reservation(db, out["reservation_id"]) is False
    assert gw.release_reservation(db, None) is False


def test_the_sweep_closes_abandoned_reservations_and_says_they_were_abandoned():
    db = _db()
    reservations.reserve(db, amount_cad=5.0, holder="dead:1:1", ttl_seconds=60, now=NOW)
    swept = reservations.sweep(db, now=NOW + timedelta(seconds=120))
    assert swept["abandoned_closed"] == 1 and swept["abandoned_cad"] == 5.0
    with db.session() as s:
        row = s.scalars(__import__("sqlalchemy").select(SpendReservation)).one()
        assert row.detail["abandoned"] is True
        assert "died between claiming" in row.detail["why"]


def test_the_spend_signal_can_see_money_that_is_reserved_and_not_yet_billed():
    """The ceiling now counts reservations, so a reader that could not see them would report
    a smaller number than the guard enforces against -- which is how a health signal starts
    disagreeing with the thing it is reporting on."""
    db = _db()
    reservations.reserve(db, amount_cad=7.5, holder="other:1:1", ttl_seconds=300, now=NOW)
    with db.session() as s:
        reading = {r.signal: r for r in H.read(
            s, runner_state={"worker_last_tick": NOW.isoformat(),
                             "scheduler_last_tick": NOW.isoformat()},
            env={}, now=NOW)}["spend"]
    assert reading.evidence["reserved_but_not_yet_billed_cad"] == 7.5
    assert reading.evidence["reservations_live"] == 1


# ---------------------------------------------------------------------------
# 4. Temporary-file lifecycle


def test_no_production_module_creates_a_directory_nothing_removes():
    """The call that left 29 GB and 37,284 directories in the suite's `/tmp` on 2026-09-20 was
    in ten production handlers on cadences that repeat forever. Only frequent container
    replacement was saving us, which is a leak mitigated by an accident of hosting.

    One `mkdtemp` is allowed to remain, and it is named here rather than exempted silently:
    `/api/continuity/export` hands the file to the server to stream *after* this function
    returns, so a block that cleaned up on the way out would delete the export before a byte
    of it was sent. It cleans up in a background task instead, which the assertion below
    checks."""
    src = ROOT / "src" / "brambleloop"
    offenders = []
    for path in sorted(src.rglob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            # The call, not the prose. Several modules now explain in a comment what they used
            # to do, and a check that could not tell a `mkdtemp(` from the words "mkdtemp" is a
            # check that punishes writing the reason down.
            if "mkdtemp(" not in line or line.lstrip().startswith("#"):
                continue
            offenders.append(f"{path.relative_to(src)}:{number}: {line.strip()}")
    assert len(offenders) == 1, offenders
    assert offenders[0].startswith("app/main.py"), offenders

    main = (src / "app" / "main.py").read_text()
    assert "BackgroundTask(shutil.rmtree, work" in main, (
        "the one remaining mkdtemp must be cleaned up after the response is sent")


def test_a_supplied_working_directory_is_never_deleted():
    """Every converted handler takes an optional `work_dir` from its job inputs, used by the
    tests and by a caller that wants the artefacts kept. Cleaning that up would delete
    somebody else's files as a side effect of a defect fix."""
    import tempfile

    with tempfile.TemporaryDirectory() as outer:
        marker = Path(outer) / "keep-me"
        marker.write_text("x")
        with workspace.work_dir(outer, prefix="unused-") as got:
            assert got == outer
        assert marker.exists()


def test_a_directory_this_system_created_goes_even_when_the_body_raises():
    """The path that leaked worst: a handler that failed half way through a render left the
    render behind and was then retried."""
    created = {}
    try:
        with workspace.work_dir(None, prefix="motif-chart-") as path:
            created["path"] = path
            assert Path(path).is_dir()
            raise RuntimeError("the render failed")
    except RuntimeError:
        pass
    assert not Path(created["path"]).exists()


def test_every_prefix_a_call_site_uses_is_one_the_disk_signal_counts():
    """A working directory whose prefix the signal does not know is a leftover the one signal
    that exists to see it cannot see. Four `TemporaryDirectory` prefixes were already in
    production and uncounted when this check was written."""
    src = ROOT / "src" / "brambleloop"
    used = set()
    pattern = re.compile(r'prefix="([a-z0-9-]+-)"')
    for path in sorted(src.rglob("*.py")):
        used.update(pattern.findall(path.read_text()))
    unknown = sorted(p for p in used if p not in H.TEMP_PREFIXES)
    assert not unknown, (
        f"these working-directory prefixes are used in `src/` and are not in "
        f"`health.TEMP_PREFIXES`, so anything they leave behind is invisible to the disk "
        f"signal: {unknown}")


def test_a_render_with_nowhere_to_put_it_is_refused_rather_than_leaked():
    """`images.generate` returns a path that has to outlive the call, so it cannot own the
    directory -- which is why it used to make one nobody owned. The two callers that passed
    none are where production's `generated-` directories came from."""
    from brambleloop.gateway import images

    try:
        images.generate("a mug", env={}, provider_key="flux-2-pro")
        raise AssertionError("a render whose bytes nobody owns was accepted")
    except images.ImagesRefused as exc:
        assert "work_dir" in str(exc) and "outlive" in str(exc)


def test_a_render_path_with_no_directory_loses_the_chart_loudly_or_not_at_all():
    """The trap this fix nearly walked into. `motif_fidelity.chart_image` cannot own its
    directory -- the path it returns is handed to `images.generate` as a conditioning
    reference -- so when it stopped inventing one, a caller with no `work_dir` would have got
    an empty chart path and gone on rendering: the picture made, the record written, the fabric
    judged against nothing. A silent downgrade is worse than the leak it replaced. Both render
    paths therefore create the directory themselves when nobody gives them one."""
    from brambleloop.publish import model_photography, motif_fidelity, owned_photography

    cir = twin = object()
    assert motif_fidelity.chart_image(cir, twin, work_dir="") == "", (
        "with no directory there is no chart, and it must not be invented in a directory "
        "nothing removes")
    for module in (model_photography, owned_photography):
        source = Path(module.__file__).read_text()
        assert 'workspace.work_dir(None, prefix=' in source, (
            f"{module.__name__} can be called without a work_dir, and without one it would "
            f"render with no chart conditioning it and say nothing about it")


def test_the_benchmark_owns_the_directory_its_renders_land_in():
    """The benchmark rendered thirty images a candidate into directories nobody owned, four
    times a day. The lifetime belongs to whoever consumes the bytes, and here that is the run
    itself: the renders exist to be judged and the judging finishes before it returns. So the
    run holds the directory, rather than the caller having to remember to."""
    source = (ROOT / "src" / "brambleloop" / "gateway" / "image_bench.py").read_text()
    assert 'workspace.work_dir(work_dir, prefix="generated-")' in source
    for call in re.findall(r"images\.(?:generate|reference_probe)\((?:[^()]|\([^()]*\))*\)",
                           source):
        assert "work_dir" in call, (
            f"this render passes no work_dir, so `images.generate` refuses it: {call}")


# ---------------------------------------------------------------------------
# 5. Retention


def test_retention_keeps_every_audit_action_a_gate_counts_over_all_time():
    """`/api/verify`'s `publication_was_actually_attempted_and_refused` needs
    `store.publish_refused > 0` for all time, and `image_bench.spent_to_date` **sums** every
    `image.benchmark` row to enforce the owner's cumulative CA$50. Pruning either would make
    a gate go red or a spent budget look unspent -- and the second rebuilds the exact defect
    the cumulative rule was written to close."""
    db = _db()
    old = NOW - timedelta(days=400)
    with db.session() as s:
        for _ in range(4):
            s.add(AuditLog(actor="listing", action="store.publish_refused", at=old))
            s.add(AuditLog(actor="creative_director", action="image.benchmark", at=old,
                           detail={"spent_cad": 3.0}))
            s.add(AuditLog(actor="orchestrator", action="ops.heartbeat", at=old))

    plan = retention.audit_plan(db, now=NOW)
    with db.session() as s:
        select = __import__("sqlalchemy").select
        kept = {row.action for row in s.scalars(select(AuditLog))
                if row.id not in set(plan["deletable_ids"])}
    assert "store.publish_refused" in kept and "image.benchmark" in kept
    assert plan["deletable"] > 0, "nothing was prunable, so this proves nothing"
    assert "store.publish_refused" in plan["protected_actions"]
    assert plan["why_protected"]["image.benchmark"]


def test_retention_keeps_the_newest_rows_of_every_action_whatever_the_horizon():
    """Two dozen readers ask for the *latest* row of one action. An action whose every row is
    older than the horizon would start answering "never happened" instead of "happened, a
    while ago" -- a verdict computed from the absence of evidence, arriving by deletion."""
    db = _db()
    old = NOW - timedelta(days=400)
    with db.session() as s:
        for _ in range(6):
            s.add(AuditLog(actor="orchestrator", action="ops.health", at=old))

    result = retention.apply(db, now=NOW)
    assert result["removed"]["audit_log"] == 6 - retention.KEEP_PER_ACTION
    with db.session() as s:
        select = __import__("sqlalchemy").select
        left = list(s.scalars(select(AuditLog).where(AuditLog.action == "ops.health")))
    assert len(left) == retention.KEEP_PER_ACTION, (
        "a reader asking for the last `ops.health` must still get an answer")


def test_retention_refuses_to_run_when_the_code_reads_an_action_it_has_no_decision_about():
    """The check that matters in a year. The danger is not this policy; it is the next
    lifetime aggregate somebody writes over a table that is now pruned."""
    db = _db()
    assert retention.unknown_read_actions() == [], (
        "an audit action is read by name in `src/` with no retention decision recorded. Add "
        "it to `retention.KNOWN_READ_ACTIONS` with how it is read")

    import tempfile

    with tempfile.TemporaryDirectory() as fake_src:
        (Path(fake_src) / "reader.py").write_text(
            'x = select(AuditLog).where(AuditLog.action == "brand.new.thing")\n')
        assert retention.unknown_read_actions(fake_src) == ["brand.new.thing"]


def test_the_job_horizon_clears_the_longest_cadence_period():
    """The scheduler's idempotency key is `cadence:<name>:<now // period>`. Delete the job
    holding a key whose window is still open and the cadence runs twice in one window --
    which for a spending cadence is a duplicate bill. So this is arithmetic, not taste."""
    longest = max(period for _n, _a, _t, period in CADENCES)
    assert retention.JOB_RETENTION_DAYS * 86400 > longest, (
        f"the job horizon is {retention.JOB_RETENTION_DAYS} days and the longest cadence "
        f"period is {longest / 86400:.0f} days. A job deleted while its window is still "
        f"open frees an idempotency key that is still in force")


def test_retention_will_not_delete_a_job_that_evidence_points_at():
    """`audit_log.job_id`, `cost_entries.job_id` and `spend_reservations.job_id` are real
    foreign keys. Deleting such a job either raises or orphans the evidence, and the money
    rows are what every ceiling in the company is computed from."""
    db = _db()
    old = NOW - timedelta(days=200)
    with db.session() as s:
        for index in range(retention.KEEP_PER_JOB_TYPE + 2):
            s.add(Job(agent="orchestrator", job_type="ops.heartbeat",
                      status=JobStatus.DONE, created_at=old, finished_at=old,
                      idempotency_key=f"k{index}"))
        s.flush()
        # The *oldest* one, so it is outside the keep-newest-per-type rule and the only thing
        # standing between it and deletion is the cost row pointing at it.
        billed = s.scalars(__import__("sqlalchemy").select(Job)).all()[0]
        s.add(CostEntry(agent="gateway", amount_cad=0.01, job_id=billed.id, at=old))
        billed_id = billed.id

    plan = retention.job_plan(db, now=NOW, done_floor=0)
    assert billed_id not in plan["deletable_ids"], (
        "a job with a cost row was marked deletable. That row is what a ceiling is computed "
        "from")
    assert plan["kept"]["referenced"] >= 1


def test_retention_keeps_the_newest_jobs_of_every_type_so_the_history_of_types_survives():
    """`build2.maturity` reads `jobs_seen` -- the set of job types this company has ever run.
    Pruning oldest-first across the whole table would narrow that set and make a capability
    that has run look like one that never has."""
    db = _db()
    old = NOW - timedelta(days=300)
    with db.session() as s:
        for index in range(retention.KEEP_PER_JOB_TYPE):
            s.add(Job(agent="orchestrator", job_type="plan.strategy", status=JobStatus.DONE,
                      created_at=old, finished_at=old, idempotency_key=f"s{index}"))
    plan = retention.job_plan(db, now=NOW, done_floor=0)
    assert plan["deletable"] == 0, plan
    assert plan["kept"]["recent_for_their_type"] == retention.KEEP_PER_JOB_TYPE


def test_retention_cannot_take_the_completed_job_count_below_the_gate_that_reads_it():
    """`scale.confidence` gates on 100 completed jobs over all time. Retention must not be
    able to make a true claim false."""
    db = _db()
    old = NOW - timedelta(days=300)
    with db.session() as s:
        for index in range(retention.KEEP_PER_JOB_TYPE + 5):
            s.add(Job(agent="orchestrator", job_type="ops.queue_check", status=JobStatus.DONE,
                      created_at=old, finished_at=old, idempotency_key=f"q{index}"))
    plan = retention.job_plan(db, now=NOW)
    assert plan["deletable"] == 0, plan
    assert plan["kept"]["protecting_the_done_floor"] == 5
    assert plan["done_floor"] >= 100


def test_only_dead_letters_that_are_refusals_working_are_ever_removed():
    """"The one thing a dead-letter queue must never do is lose a failure nobody looked at"
    is `purge_dead`'s own rule and retention does not soften it. Production holds 149 dead
    letters and every one is a refusal working correctly."""
    db = _db()
    old = NOW - timedelta(days=200)
    with db.session() as s:
        s.add(Job(agent="listing", job_type="store.publish", status=JobStatus.DEAD,
                  last_error="shadow mode", created_at=old, finished_at=old,
                  idempotency_key="refusal"))
        s.add(Job(agent="orchestrator", job_type="ops.heartbeat", status=JobStatus.DEAD,
                  last_error="AttributeError: NoneType", created_at=old, finished_at=old,
                  idempotency_key="defect"))

    plan = retention.dead_letter_plan(db, now=NOW)
    assert plan["deletable"] == 1 and plan["kept"]["is_a_defect"] == 1
    result = retention.apply(db, now=NOW)
    assert result["removed"]["dead_letters"] == 1
    left = JobQueue(db).dead_letters()
    assert [j.job_type for j in left] == ["ops.heartbeat"]


def test_purge_dead_skips_a_dead_letter_that_evidence_points_at():
    """`purge_dead` was called from nowhere, so this never bit. It has a caller now, and a
    dead letter with a cost row against it is a foreign key away from an integrity error."""
    db = _db()
    with db.session() as s:
        job = Job(agent="listing", job_type="store.publish", status=JobStatus.DEAD,
                  last_error="shadow mode", created_at=NOW, finished_at=NOW,
                  idempotency_key="billed-refusal")
        s.add(job)
        s.flush()
        s.add(CostEntry(agent="listing", amount_cad=0.02, job_id=job.id, at=NOW))
    assert JobQueue(db).purge_dead(job_types=["store.publish"]) == 0
    assert len(JobQueue(db).dead_letters()) == 1


def test_retention_never_touches_the_rows_every_ceiling_is_computed_from():
    """A retention policy that pruned the money would be a retention policy that lowered a
    ceiling."""
    db = _db()
    old = NOW - timedelta(days=900)
    _spend(db, "market_radar", 12.0, purpose="gallery_observation", at=old)
    retention.apply(db, now=NOW)
    with db.session() as s:
        rows = list(s.scalars(__import__("sqlalchemy").select(CostEntry)))
    assert len(rows) == 1 and rows[0].amount_cad == 12.0
    assert "cost_entries" in retention.plan(db, now=NOW)["never_touched"]


def test_the_retention_cadence_and_its_permission_exist_together():
    """A cadence scheduled against an agent with no permission for it dead-letters every
    time it fires -- which is how the operational heartbeat dead-lettered every fifteen
    minutes from the first boot."""
    scheduled = {job_type: agent for _n, agent, job_type, _p in CADENCES}
    assert scheduled.get("ops.retention") == "orchestrator"
    db = _db()
    Registry(db).authorize("orchestrator", "ops.retention")


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
