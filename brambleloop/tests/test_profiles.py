"""What a cell knows about itself, and why its own review is deterministic.

v1.4.3 requirement 177. Each cell keeps a versioned capability profile -- objective, baseline,
mistakes, lessons, tactics that worked and did not, running versions, challengers -- and
reviews its own outcomes to propose evidence-backed improvements.

The tests hold two lines. The profile is assembled from the rows rather than stored beside
them, so there is no second copy of the truth to drift. And the review proposes only from
patterns in the cell's own record, because a review that writes fluent hypotheses every week
looks exactly like a cell that is learning -- and a review that could promote its own
proposals is the unsupervised rewriting #178 forbids, arriving from inside the department
that is supposed to be measuring.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.improve import cells, profiles, tiers  # noqa: E402

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/profiles.sqlite")
    db.create_all()
    return db


def _measure(db, cell: str, *values, days_ago: float = 1.0) -> None:
    from brambleloop.core.models import CapabilityPoint

    with db.session() as s:
        for i, value in enumerate(values):
            s.add(CapabilityPoint(cell=cell, metric="m", value=value,
                                  at=NOW - timedelta(days=days_ago + len(values) - i)))


def _kinds(review: dict) -> set[str]:
    return {p["kind"] for p in review["proposals"]}


# ---- the profile ----------------------------------------------------------


def test_a_cell_that_has_never_been_measured_has_no_capability_not_a_zero():
    state = profiles.profile(_db(), "quality", now=NOW)

    assert state["measurements"] == 0
    assert state["baseline"] is None and state["latest"] is None
    assert "different thing from a capability of zero" in state["note"]


def test_the_profile_carries_everything_the_requirement_names():
    state = profiles.profile(_db(), "quality", now=NOW)

    for key in ("objective", "metric", "baseline", "successful_tactics",
                "rejected_tactics", "lessons", "running_versions", "challengers",
                "measured_by", "agent"):
        assert key in state, key


def test_a_profile_is_assembled_from_the_rows_rather_than_stored_beside_them():
    """No second copy of the truth to drift from the first."""
    db = _db()
    _measure(db, "quality", 0.4, 0.3)

    assert profiles.profile(db, "quality", now=NOW)["measurements"] == 2
    _measure(db, "quality", 0.2)
    assert profiles.profile(db, "quality", now=NOW)["measurements"] == 3


def test_tactics_are_split_by_what_actually_happened_to_them():
    db = _db()
    cells.record_capability(db, "quality", 0.40)
    good = cells.propose(
        db, cell="quality",
        hypothesis="tightening the chart check before certification should catch defects",
        expected_effect="fewer defects after release", rollback_ref="git:aaa",
        touches=("weights",))
    cells.test_result(db, good, 0.20)
    cells.promote(db, good)

    bad = cells.propose(
        db, cell="quality",
        hypothesis="sampling fewer rows per certification should catch defects sooner",
        expected_effect="fewer defects after release", rollback_ref="git:bbb",
        touches=("weights",))
    cells.test_result(db, bad, 0.90)

    state = profiles.profile(db, "quality", now=NOW)

    assert [t["id"] for t in state["successful_tactics"]] == [good]
    assert [t["id"] for t in state["rejected_tactics"]] == [bad]


def test_an_unknown_cell_is_refused():
    try:
        profiles.profile(_db(), "vibes", now=NOW)
    except profiles.ProfileRefused as e:
        assert "is not a cell" in str(e)
    else:
        raise AssertionError("a profile was assembled for a cell that does not exist")


# ---- the review -----------------------------------------------------------


def test_a_run_in_the_wrong_direction_is_noticed_where_a_single_point_is_not():
    """A run is a direction and a single point is weather, and the cell that owns the metric
    is the last to see the run."""
    db = _db()
    # 'quality' counts defects after release: lower is better, so rising is worse.
    _measure(db, "quality", 0.10, 0.20, 0.30)

    review = profiles.self_review(db, "quality", now=NOW)

    assert "declining_capability" in _kinds(review)
    proposal = next(p for p in review["proposals"] if p["kind"] == "declining_capability")
    assert len(proposal["evidence"]["measurements"]) == profiles.DECLINE_RUN


def test_movement_in_the_right_direction_proposes_nothing():
    db = _db()
    _measure(db, "quality", 0.30, 0.20, 0.10)

    assert "declining_capability" not in _kinds(
        profiles.self_review(db, "quality", now=NOW))


def test_direction_follows_the_cell_rather_than_the_arithmetic():
    """Rising is worse for defects and better for acquisition loops."""
    db = _db()
    _measure(db, "growth", 1.0, 2.0, 3.0)

    assert "declining_capability" not in _kinds(
        profiles.self_review(db, "growth", now=NOW))


def test_the_commonest_real_state_is_the_one_a_review_names():
    """Nobody has measured it. No cell proposes anything about that, because there is
    nothing to look at."""
    review = profiles.self_review(_db(), "finance", now=NOW)

    assert "never_measured" in _kinds(review)
    proposal = next(p for p in review["proposals"] if p["kind"] == "never_measured")
    assert "a baseline, not a result" in proposal["why"]


def test_a_stale_baseline_is_a_comparison_with_a_company_that_no_longer_exists():
    db = _db()
    _measure(db, "pricing", 1.0, days_ago=profiles.STALE_AFTER_DAYS + 5)

    review = profiles.self_review(db, "pricing", now=NOW)

    assert "stale_measurement" in _kinds(review)
    assert "never_measured" not in _kinds(review)


def test_a_tactic_rejected_twice_for_the_same_reason_is_recorded_as_answered():
    """Repeating a rejected tactic is how a programme spends a quarter learning the same
    thing."""
    db = _db()
    cells.record_capability(db, "runtime", 2.0)
    for suffix in ("a", "b"):
        rejected = cells.propose(
            db, cell="runtime",
            hypothesis=f"claiming jobs in larger batches {suffix} should cut dead letters",
            expected_effect="fewer dead letters", rollback_ref=f"git:{suffix}",
            touches=("weights",))
        cells.test_result(db, rejected, 9.0)

    review = profiles.self_review(db, "runtime", now=NOW)

    assert "answered_tactic" in _kinds(review)
    proposal = next(p for p in review["proposals"] if p["kind"] == "answered_tactic")
    assert len(proposal["evidence"]["improvement_ids"]) >= profiles.REPEATED_REJECTION


def test_a_lesson_routed_here_and_never_acted_on_is_surfaced():
    db = _db()
    from brambleloop.core.models import Lesson

    with db.session() as s:
        s.add(Lesson(origin_cell="quality", subject="gauge_drift",
                     statement="swatches drift at this hook size",
                     routed_to=["pattern_engineering"], acted_on_by=[]))

    review = profiles.self_review(db, "pattern_engineering", now=NOW)

    assert "unused_lesson" in _kinds(review)


def test_a_clean_record_proposes_nothing_and_says_that_is_the_right_answer():
    db = _db()
    _measure(db, "quality", 0.30, 0.20, 0.10, days_ago=1)

    review = profiles.self_review(db, "quality", now=NOW)

    assert review["proposals"] == []
    assert "correct output of a review" in review["note"]


def test_a_review_proposes_and_never_promotes():
    """A review that could promote its own proposals is unsupervised rewriting arriving from
    inside the department that is supposed to be measuring."""
    db = _db()
    _measure(db, "quality", 0.10, 0.20, 0.30)

    review = profiles.self_review(db, "quality", now=NOW)

    assert review["proposals"]
    for proposal in review["proposals"]:
        assert set(proposal) == {"kind", "hypothesis", "evidence", "why"}
        assert "promote" not in proposal
    assert "enter the ordinary pipeline" in review["note"]

    # And nothing was written: the cell's own record is unchanged by being reviewed.
    from sqlalchemy import func, select

    from brambleloop.core.models import Improvement

    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(Improvement)) == 0


def test_every_cell_is_reviewed_and_the_ones_with_findings_come_first():
    db = _db()
    _measure(db, "quality", 0.30, 0.20, 0.10, days_ago=1)

    report = profiles.review_all(db, now=NOW)

    assert report["cells"] == len(cells.CELLS)
    assert report["with_proposals"] == report["cells"] - 1
    counts = [len(r["proposals"]) for r in report["reviews"]]
    assert counts == sorted(counts, reverse=True)


def test_a_proposal_from_a_review_still_has_to_pass_its_risk_tier():
    """The pipeline a proposal enters is the ordinary one, tiers included."""
    assert tiers.TIER_BY_KEY["gate"].needs_owner is True


def _run() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
