"""Reading what buyers complain about, without keeping what they said.

#2's third weakness signal and #98's `customer_pain` domain, both of which this system had
correctly recorded as unmeasurable. The reason it gave was right at the time and is worth
keeping: *inferring complaints from a competitor's catalogue is inventing them.* Reading
their reviews is not inferring. It is observing, and the distinction is the whole of the
difference between the two.

What must never happen is the thing that would make it easy: storing, summarising or quoting
a review. A complaint theme is a fact about a category. A review is somebody's words.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.intel import learning, observe  # noqa: E402

REVIEWS = [
    {"review": "The pattern was confusing and I couldn't follow row 12", "rating": 2},
    {"review": "Confusing instructions, vague in places", "rating": 3},
    {"review": "Unclear and poorly written throughout", "rating": 2},
    {"review": "Beautiful design, though I ran out of yarn", "rating": 4},
    {"review": "Lovely, thank you so much", "rating": 5},
    {"review": "Gorgeous pattern", "rating": 5},
]


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/complaints.sqlite")
    db.create_all()
    return db


def test_a_recurring_theme_is_counted_and_a_one_off_is_not():
    """#2 asks for *recurring* complaints, and the word is doing work."""
    themes = observe.complaint_themes(REVIEWS)
    assert themes["themes"]["instructions_unclear"] == 3
    assert themes["recurring"] == {"instructions_unclear": 3}
    assert "yarn_estimate_wrong" in themes["themes"]
    assert "yarn_estimate_wrong" not in themes["recurring"]


def test_no_review_text_reviewer_or_quotation_is_ever_stored():
    """The boundary is a test, not an intention."""
    themes = observe.complaint_themes(REVIEWS)
    blob = repr(themes)
    for review in REVIEWS:
        assert review["review"] not in blob
        assert review["review"][:20] not in blob


def test_the_rating_distribution_is_kept_because_it_is_a_number():
    themes = observe.complaint_themes(REVIEWS)
    assert themes["reviews_rated"] == 6
    assert themes["low_rated"] == 3
    assert themes["low_rated_share"] == 0.5


def test_no_reviews_at_all_is_unmeasurable_and_not_a_category_without_complaints():
    themes = observe.complaint_themes([])
    assert not themes["measurable"]
    assert themes["recurring"] == {}


def test_only_recurring_themes_reach_the_learning_radar():
    """A theme below the floor would age for 180 days as though it were a property of the
    category."""
    db = _db()
    one_off = observe.complaint_themes(REVIEWS[3:])
    assert learning.ingest_complaints(db, themes=one_off)["recorded"] == []
    real = observe.complaint_themes(REVIEWS)
    assert learning.ingest_complaints(db, themes=real)["recorded"] == ["customer_pain"]


def test_a_reading_with_no_recurring_theme_is_not_a_silence():
    db = _db()
    result = learning.ingest_complaints(db, themes=observe.complaint_themes(REVIEWS[3:]))
    assert "not a silence" in result["reason"]


def test_recording_the_same_reading_twice_adds_nothing():
    db = _db()
    themes = observe.complaint_themes(REVIEWS)
    assert learning.ingest_complaints(db, themes=themes, today=date(2026, 9, 20))["recorded"]
    assert learning.ingest_complaints(
        db, themes=themes, today=date(2026, 9, 20))["recorded"] == []


def test_the_customer_pain_domain_is_no_longer_claimed_unfeedable_by_inference():
    """The old note said no review had been read. It was true, and it is not any more."""
    reason = learning.NOT_FEEDABLE["customer_pain"]
    assert "reading their reviews is observing them" in reason
    assert "mjs.reviews" in reason


def test_the_scan_records_a_dated_observation_rather_than_a_variable():
    class Reader:
        def resolve_shop(self, name):
            return {"shop_id": 1, "shop_name": name}

        def reviews(self, shop_id, *, limit=100):
            return REVIEWS

    from sqlalchemy import select

    from brambleloop.core.models import BenchmarkObservation

    db = _db()
    themes = observe.scan_reviews(db, reader=Reader())
    assert themes["recurring"] == {"instructions_unclear": 3}
    with db.session() as s:
        row = s.scalar(select(BenchmarkObservation))
        assert row is not None and row.detail["reviews"]["recurring"]


def test_the_weakness_hunt_reports_complaints_once_they_are_read():
    from brambleloop.core.models import BenchmarkListing
    from brambleloop.intel import benchmarks
    from brambleloop.radar import arbitrage

    class Reader:
        def resolve_shop(self, name):
            return {"shop_id": 1, "shop_name": name}

        def reviews(self, shop_id, *, limit=100):
            return REVIEWS

    db = _db()
    with db.session() as s:
        for i in range(6):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=str(i),
                                   title="t", pod="hats", media_count=2))
    before = arbitrage.weakness_hunt(db)
    assert before["complaints"]["measurable"] is False
    observe.scan_reviews(db, reader=Reader())
    after = arbitrage.weakness_hunt(db)
    assert after["complaints"]["recurring"] == {"instructions_unclear": 3}


def test_video_is_unknown_where_no_gallery_was_audited():
    """Counting unknown as "no video" turns an unfinished backfill into a competitor's
    weakness."""
    from brambleloop.core.models import BenchmarkListing
    from brambleloop.intel import benchmarks
    from brambleloop.radar import arbitrage

    db = _db()
    with db.session() as s:
        for i in range(5):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=str(i),
                                   title="t", pod="hats", media_count=2, detail={}))
    report = arbitrage.weakness_hunt(db)
    assert report["video"]["measurable"] is False
    assert "not the same as no video" in report["video"]["reason"]


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
