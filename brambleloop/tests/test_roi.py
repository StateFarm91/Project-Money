"""What an improvement returned, and whether a design used what the company knows.

v1.4.3 requirements 99 and 101. Both are second halves. The first half of #99 -- refusing a
change nobody can afford -- was built with the improvement cells; the half that gets skipped
is going back for the benefit, because cost is known on the day and benefit is known later.
The first half of #101 counts lessons acted on; the half #101 is actually named after is
whether a *new design* stood on what the company already knows.

The failures worth holding a test on: reading the sandbox number that won the promotion as
though it were the realised return, collapsing "promoted yesterday" into "returned nothing",
and prioritising a candidate that never said what would count as it working.
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
from brambleloop.improve import cells, roi  # noqa: E402

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/roi.sqlite")
    db.create_all()
    return db


def _promoted(db, *, cell="quality", baseline=0.20, result=0.10, cost=1.50) -> int:
    """A change that beat its baseline and was promoted. 'quality' is lower-is-better."""
    cells.record_capability(db, cell, baseline)
    improvement_id = cells.propose(
        db, cell=cell, hypothesis=("tightening the chart check before certification should catch "
                    "stitch-count defects earlier"),
        expected_effect="fewer defects reach a release", rollback_ref="git:abc123", touches=("weights",),
        spend_cad=cost, spend_authorised_cad=5.0)
    cells.test_result(db, improvement_id, result)
    cells.promote(db, improvement_id)
    return improvement_id


def _age(db, improvement_id: int, days: float) -> None:
    """Backdate a promotion, and everything measured up to it, so a return can be read.

    The baseline measurement and the sandbox result both happened before the promotion, so
    they move back with it; anything a test records afterwards is the production reading.
    """
    from brambleloop.core.models import CapabilityPoint, Improvement

    promoted_at = NOW - timedelta(days=days)
    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        row.promoted_at = promoted_at
        for point in s.query(CapabilityPoint).filter(CapabilityPoint.cell == row.cell):
            point.at = promoted_at - timedelta(minutes=1)


# ---- #99: what did it return? ---------------------------------------------


def test_nothing_promoted_says_so_rather_than_reporting_a_hit_rate():
    report = roi.realised_benefit(_db(), now=NOW)
    assert report["promotions"] == 0
    assert report["hit_rate"] is None
    assert "nobody goes back for" in report["note"]


def test_the_sandbox_number_that_won_the_promotion_is_not_read_as_the_return():
    """The promotion records its own result as a capability point. Counting that as the
    realised benefit would make every promotion succeed by construction."""
    db = _db()
    improvement_id = _promoted(db, baseline=0.20, result=0.10)
    _age(db, improvement_id, 30)

    report = roi.realised_benefit(db, now=NOW)

    assert report["returned"] == [], "the sandbox result was read as a realised return"
    assert len(report["unmeasured"]) == 1
    assert report["unmeasured"][0]["observed"] is None
    assert "never measured again" in report["note"]


def test_a_change_promoted_this_morning_is_too_early_not_a_failure():
    db = _db()
    improvement_id = _promoted(db)
    _age(db, improvement_id, 1)

    report = roi.realised_benefit(db, now=NOW)

    assert len(report["too_early"]) == 1
    assert report["unmeasured"] == []
    assert report["assessed"] == 0
    assert report["hit_rate"] is None, "a hit rate over promotions made this morning"


def test_production_measuring_better_than_the_baseline_is_a_return():
    db = _db()
    improvement_id = _promoted(db, baseline=0.20, result=0.10, cost=1.50)
    _age(db, improvement_id, 30)
    cells.record_capability(db, "quality", 0.11, detail={"from": "production"})

    report = roi.realised_benefit(db, now=NOW)

    assert len(report["returned"]) == 1
    row = report["returned"][0]
    assert row["baseline"] == 0.20 and row["observed"] == 0.11
    assert row["movement"] > roi.NEUTRAL_BAND
    assert report["spent_cad"] == 1.50
    assert report["hit_rate"] == 1.0


def test_a_promotion_whose_metric_did_not_move_is_a_cost_with_no_return():
    db = _db()
    improvement_id = _promoted(db, baseline=0.20, result=0.10, cost=2.25)
    _age(db, improvement_id, 30)
    cells.record_capability(db, "quality", 0.201, detail={"from": "production"})

    report = roi.realised_benefit(db, now=NOW)

    assert len(report["no_return"]) == 1, report
    assert report["no_return"][0]["cost_cad"] == 2.25
    assert report["hit_rate"] == 0.0
    assert "cost without return" in report["note"]


def test_production_measuring_worse_than_the_baseline_is_a_regression():
    db = _db()
    improvement_id = _promoted(db, baseline=0.20, result=0.10)
    _age(db, improvement_id, 30)
    cells.record_capability(db, "quality", 0.40, detail={"from": "production"})

    report = roi.realised_benefit(db, now=NOW)

    assert len(report["regressed"]) == 1
    assert report["regressed"][0]["movement"] < -roi.NEUTRAL_BAND


def test_direction_follows_the_cell_not_the_arithmetic():
    """'growth' is higher-is-better; a rise there is a return, where a rise in 'quality'
    (defects after release) is a regression."""
    db = _db()
    cells.record_capability(db, "growth", 2.0)
    improvement_id = cells.propose(
        db, cell="growth", hypothesis=("adding a second acquisition loop with attribution should raise "
                    "the count of loops carrying measured traffic"),
        expected_effect="more loops carry measured traffic", rollback_ref="git:def456",
        touches=("weights",))
    cells.test_result(db, improvement_id, 3.0)
    cells.promote(db, improvement_id)
    _age(db, improvement_id, 30)
    cells.record_capability(db, "growth", 4.0, detail={"from": "production"})

    report = roi.realised_benefit(db, now=NOW)

    assert len(report["returned"]) == 1, report


# ---- #99: prioritising what to spend the next dollar on -------------------


def test_a_candidate_that_cannot_say_what_would_count_as_working_is_refused():
    try:
        roi.prioritise([{"key": "rewrite_the_listing_prompt", "cost_cad": 3.0}])
    except roi.RoiRefused as e:
        assert "what would count as working" in str(e)
    else:
        raise AssertionError("a candidate with no expected effect was prioritised")


def test_a_free_change_with_real_expected_impact_outranks_a_paid_one():
    ranked = roi.prioritise([
        {"key": "paid", "expected_impact": 0.30, "cost_cad": 2.0},
        {"key": "free", "expected_impact": 0.05, "cost_cad": 0.0},
    ])["ranked"]
    assert [r["key"] for r in ranked] == ["free", "paid"]
    assert ranked[1]["impact_per_cad"] == 0.15


# ---- #101: did this design use what the company knows? --------------------


def _lesson(db, subject: str) -> int:
    from brambleloop.core.models import Lesson

    with db.session() as s:
        row = Lesson(origin_cell="quality", subject=subject,
                     statement=f"what {subject} taught us", confidence="observed")
        s.add(row)
        s.flush()
        return row.id


def test_a_design_cannot_cite_knowledge_the_company_does_not_have():
    db = _db()
    try:
        roi.design_provenance(db, product_slug="new-throw", lesson_ids=(404,))
    except roi.RoiRefused as e:
        assert "does not have" in str(e)
    else:
        raise AssertionError("a design cited a lesson that does not exist")


def test_a_design_that_drew_on_nothing_is_recorded_not_forbidden():
    db = _db()
    record = roi.design_provenance(db, product_slug="first-in-new-territory",
                                   lesson_ids=(), brief="mosaic blanket")
    assert record["count"] == 0
    assert "first product in a new territory" in record["note"]


def test_compounding_is_unmeasurable_until_designs_record_what_they_drew_on():
    report = roi.compounding_report(_db())
    assert report["measurable"] is False
    assert "cannot be told apart" in report["reason"]


def test_a_catalogue_of_designs_drawing_on_nothing_is_visible_as_restarting():
    db = _db()
    for slug in ("one", "two", "three"):
        roi.design_provenance(db, product_slug=slug, lesson_ids=())

    report = roi.compounding_report(db)

    assert report["measurable"] is True
    assert report["share"] == 0.0
    assert "restarting from generic intelligence" in report["note"]


def test_designs_standing_on_accumulated_lessons_are_counted_as_such():
    db = _db()
    first = _lesson(db, "gauge_drift")
    second = _lesson(db, "thumbnail_crop")
    roi.design_provenance(db, product_slug="second-throw", lesson_ids=(first, second))
    roi.design_provenance(db, product_slug="third-throw", lesson_ids=(first,))
    roi.design_provenance(db, product_slug="fourth-throw", lesson_ids=())

    report = roi.compounding_report(db)

    assert report["designs"] == 3
    assert report["designs_using_accumulated_knowledge"] == 2
    assert report["mean_lessons_per_design"] == 1.0
    assert "2 of 3 designs" in report["note"]


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
