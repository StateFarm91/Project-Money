"""The nightly sweep, and the word it is not allowed to say.

Requirement 193. The whole risk in a scheduled sweep is `completed`. A job that finishes
without raising and writes "ok" reads identically whether it did the work or skipped every
stage of it, and the comfortable reading is the one that gets believed -- which is how a
company reports a year of nightly improvement cycles during which nothing was read.

This build has met that shape three times already: a funnel stage that killed nothing, an
artefact with no provenance row, and a buyer journey nobody walked. Here the verdict is
computed from what each stage returned rather than from the absence of an exception.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.improve import nightly as N  # noqa: E402

AT = datetime(2026, 9, 20, 3, 0, tzinfo=timezone.utc)


def _all_ran(found: int = 1, read: int = 10):
    return [N.stage_ran(s, read=read, found=found) for s in N.STAGES]


# ---- three outcomes, never two --------------------------------------------


def test_found_nothing_and_did_not_run_are_different_outcomes():
    """A boolean here collapses the one distinction the sweep exists to keep."""
    quiet = N.stage_ran(N.MINE, read=40, found=0)
    skipped = N.stage_skipped(N.MINE, "the incident table was unreachable")
    assert quiet.outcome == N.NOTHING and quiet.ran is True
    assert skipped.outcome == N.SKIPPED and skipped.ran is False


def test_a_stage_that_read_nothing_did_not_run_however_it_reports_itself():
    """Finding nothing in nothing has not established that there was nothing to find."""
    out = N.stage_ran(N.INGEST, read=0)
    assert out.outcome == N.SKIPPED
    assert "cannot report that there was nothing" in out.why


def test_reporting_found_with_nothing_found_is_refused():
    try:
        N.StageResult(stage=N.MINE, outcome=N.FOUND, read=10, found=0)
    except N.NightlyRefused as e:
        assert "the whole point of having both" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a stage found nothing and called it a find")


def test_reporting_nothing_after_reading_nothing_is_refused():
    try:
        N.StageResult(stage=N.MINE, outcome=N.NOTHING, read=0)
    except N.NightlyRefused as e:
        assert "found nothing in nothing" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an empty read passed as a clean result")


def test_a_skipped_stage_must_say_why():
    try:
        N.StageResult(stage=N.QUEUE, outcome=N.SKIPPED)
    except N.NightlyRefused as e:
        assert "nobody implemented" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a silent skip was accepted")


def test_an_invented_outcome_is_refused():
    try:
        N.StageResult(stage=N.MINE, outcome="ok", read=1)
    except N.NightlyRefused as e:
        assert "is not an outcome" in str(e)
    else:  # pragma: no cover
        raise AssertionError("'ok' was accepted as an outcome")


def test_an_invented_stage_is_refused():
    try:
        N.stage_ran("vibe_check", read=1, found=1)
    except N.NightlyRefused as e:
        assert "not a sweep stage" in str(e)
    else:  # pragma: no cover
        raise AssertionError("the sweep grew a stage")


# ---- the verdict is computed, not asserted --------------------------------


def test_every_stage_the_requirement_names_is_present():
    for stage in ("ingest_evidence", "mine_failures", "update_lessons", "run_challengers",
                  "identify_bottlenecks", "queue_safe_improvements", "produce_delta"):
        assert stage in N.STAGES
    assert len(N.STAGES) == 7


def test_a_sweep_where_every_stage_ran_is_complete():
    out = N.delta(_all_ran(), at=AT)
    assert out["verdict"] == N.COMPLETE
    assert out["did_not_run"] == []
    assert len(out["found_something"]) == 7


def test_one_skipped_stage_makes_the_whole_sweep_incomplete():
    results = _all_ran()[:-1] + [N.stage_skipped(N.DELTA, "the writer was unavailable")]
    out = N.delta(results, at=AT)
    assert out["verdict"] == N.INCOMPLETE
    assert out["did_not_run"] == [N.DELTA]
    assert "finished without raising" in out["why"]


def test_a_stage_nobody_reported_at_all_is_did_not_run_rather_than_absent():
    out = N.delta(_all_ran()[:3], at=AT)
    assert out["verdict"] == N.INCOMPLETE
    assert len(out["did_not_run"]) == 4
    assert out["stages"][N.QUEUE]["outcome"] == N.SKIPPED
    assert "no result was reported" in out["stages"][N.QUEUE]["why"]


def test_a_sweep_that_found_nothing_anywhere_is_still_complete():
    """Finding nothing is a real result. Not running is not."""
    results = [N.stage_ran(s, read=12, found=0) for s in N.STAGES]
    out = N.delta(results, at=AT)
    assert out["verdict"] == N.COMPLETE
    assert len(out["found_nothing"]) == 7
    assert out["total_found"] == 0


def test_an_empty_sweep_cannot_report_success():
    out = N.delta([], at=AT)
    assert out["verdict"] == N.INCOMPLETE
    assert len(out["did_not_run"]) == len(N.STAGES)


def test_two_results_for_one_stage_make_the_night_incomparable():
    results = _all_ran() + [N.stage_ran(N.MINE, read=1, found=1)]
    try:
        N.delta(results, at=AT)
    except N.NightlyRefused as e:
        assert "cannot be compared" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a stage reported twice and the delta accepted it")


def test_the_totals_are_sums_of_what_was_actually_read():
    out = N.delta(_all_ran(found=2, read=5), at=AT)
    assert out["total_read"] == 35
    assert out["total_found"] == 14


# ---- comparable across nights ---------------------------------------------


def test_the_delta_says_what_changed_since_last_night():
    first = N.delta(_all_ran(found=1, read=10), at=AT)
    quieter = [N.stage_ran(s, read=10, found=0) for s in N.STAGES]
    second = N.delta(quieter, at=AT, previous=first)
    assert second["since_previous"]["found_delta"] == -7
    assert set(second["since_previous"]["newly_quiet"]) == set(N.STAGES)
    assert second["since_previous"]["newly_active"] == []


def test_a_stage_blocked_two_nights_running_is_named_as_such():
    blocked = _all_ran()[:-1] + [N.stage_skipped(N.DELTA, "writer unavailable")]
    first = N.delta(blocked, at=AT)
    second = N.delta(blocked, at=AT, previous=first)
    assert second["since_previous"]["still_blocked"] == [N.DELTA]
    assert "a defect rather than a bad night" in second["since_previous"]["why"]


def test_a_stage_waking_up_is_reported_as_newly_active():
    quiet = N.delta([N.stage_ran(s, read=10, found=0) for s in N.STAGES], at=AT)
    active = N.delta(_all_ran(), at=AT, previous=quiet)
    assert set(active["since_previous"]["newly_active"]) == set(N.STAGES)


def test_a_long_quiet_run_is_reported_without_a_diagnosis():
    """Genuinely clean and quietly broken are the same reading, so it does not pick one."""
    quiet = N.delta([N.stage_ran(s, read=10, found=0) for s in N.STAGES], at=AT)
    out = N.quiet_run([quiet] * 20, N.MINE)
    assert out["quiet_nights"] == 20
    assert "cannot tell which" in out["why"]


def test_a_quiet_run_is_broken_by_a_night_that_found_something():
    quiet = N.delta([N.stage_ran(s, read=10, found=0) for s in N.STAGES], at=AT)
    active = N.delta(_all_ran(), at=AT)
    out = N.quiet_run([quiet, quiet, active], N.MINE)
    assert out["quiet_nights"] == 0


# ---- a minimum, not a monopoly --------------------------------------------


def test_the_sweep_queues_improvements_rather_than_promoting_them():
    out = N.state()
    assert "queues improvements rather than promoting them" in out["is_a_minimum_not_a_monopoly"]
    assert N.QUEUE in N.STAGES
    assert not any("promote" in s for s in N.STAGES)


def test_state_names_the_verdict_rule():
    out = N.state()
    assert out["requirement"] == 193
    assert "absence of an exception" in out["note"]
    assert any("complete verdict while any stage did not run" in r for r in out["refuses"])


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
