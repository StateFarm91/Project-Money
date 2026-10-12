"""The dated, category-matched benchmark set, and the ways a set lies about itself (#76, #67).

A set of two listings is one seller's two decisions; a set that cannot say how old it is
cannot claim to be current; a ten-dimension set reported as eight is averaging one file over.
Each has a test.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing, BenchmarkObservation  # noqa: E402
from brambleloop.intel import benchmark_set as S  # noqa: E402

KEY = "mjs_off_the_hook_designs"
NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _pod(db, pod="garments", listings=3, images=2, *, day=20, video=True,
         brand="one coherent shop look"):
    with db.session() as s:
        for i in range(listings):
            ref = f"{pod}-{i}"
            s.add(BenchmarkListing(
                benchmark_key=KEY, listing_ref=ref, title=f"{pod} {i}", pod=pod,
                audit_state="audited", media_count=7,
                detail={"gallery_audited": True, "has_video": video,
                        "palette": [{"hex": "AABBCC"}]}))
            for rank in range(images):
                observation = {"shot_type": ("full_fit", "detail_macro")[rank % 2],
                               "thumbnail_readability": "reads at grid scale",
                               "composition": "tight crop", "setting": "linen backdrop",
                               "product_visibility": "product owns the frame"}
                if brand:
                    observation["brand_coherence"] = brand
                s.add(BenchmarkObservation(
                    benchmark_key=KEY, listing_ref=ref, kind="gallery_image_observation",
                    at=datetime(2026, 9, day + i, tzinfo=timezone.utc),
                    detail={"image": {"rank": rank + 1}, "observation": observation}))


def test_a_set_below_its_minimum_is_refused_not_thinned():
    db = _db()
    _pod(db, listings=2, images=2)          # four images, two listings
    try:
        S.build(db, "garments", now=NOW)
    except S.SetRefused as exc:
        assert "below the stated minimum" in str(exc)
    else:
        raise AssertionError("a two-listing set was built")

    # And the minimum can be raised by a caller but never lowered under the floor.
    _pod(db, pod="hats", listings=3, images=2)
    assert S.build(db, "hats", now=NOW)["listings"] == 3
    try:
        S.build(db, "hats", now=NOW, min_observations=1, min_listings=1)  # cannot lower
        S.build(db, "hats", now=NOW, min_observations=20)
    except S.SetRefused as exc:
        assert "20 images" in str(exc)
    else:
        raise AssertionError("a raised minimum was ignored")


def test_the_set_is_dated_category_matched_and_ten_dimensions_wide():
    db = _db()
    _pod(db)
    out = S.build(db, "garments", now=NOW)
    assert out["listings"] == 3 and out["observations"] == 6
    assert all(m["pod"] == "garments" for m in out["members"])
    assert out["oldest_evidence"].startswith("2026-09-20")
    assert out["newest_evidence"].startswith("2026-09-22")
    assert out["current"] is True and out["age_days"] == 4
    assert set(out["dimensions"]) == set(S.DIMENSIONS) and len(S.DIMENSIONS) == 10
    # Every member cites its observation rows and dates.
    for member in out["members"]:
        assert member["observation_ids"] and member["observed_dates"]
    # Video comes from the API fact, brand consistency from the recorded field.
    assert out["dimensions"]["video_support"]["video_share"] == 1.0
    assert out["dimensions"]["brand_consistency"]["basis"] == S.MEASURED
    assert "one coherent shop look" in out["dimensions"]["brand_consistency"]["reads"]


def test_dimensions_the_vocabulary_cannot_record_are_carried_as_unmeasured():
    """Realism and lighting have no recorded field. They stay in the set, named, so ten
    dimensions are never quietly reported as eight."""
    db = _db()
    _pod(db)
    out = S.build(db, "garments", now=NOW)
    assert out["dimensions"]["realism"]["basis"] == S.UNMEASURED
    assert out["dimensions"]["lighting"]["basis"] == S.UNMEASURED
    assert {"realism", "lighting"} <= set(out["unmeasured"])
    assert "brand_consistency" in out["measured"]


def test_a_field_nobody_recorded_is_unmeasured_rather_than_defaulted():
    db = _db()
    _pod(db, brand="")
    out = S.build(db, "garments", now=NOW)
    assert out["dimensions"]["brand_consistency"]["basis"] == S.UNMEASURED
    assert "brand_coherence" in out["dimensions"]["brand_consistency"]["reason"]


def test_a_set_reports_itself_stale_and_the_release_comparison_refuses_it():
    db = _db()
    _pod(db, day=1)
    old = S.build(db, "garments", now=datetime(2026, 12, 1, tzinfo=timezone.utc))
    assert old["current"] is False
    try:
        S.compare_listing_set([{"role": "hero", "readable_at_grid": True}], old)
    except S.SetRefused as exc:
        assert "current" in str(exc)
    else:
        raise AssertionError("a stale set was compared against")


def test_the_release_comparison_rejects_substandard_presentation_and_names_the_unjudged():
    db = _db()
    _pod(db)
    current = S.build(db, "garments", now=NOW)
    out = S.compare_listing_set([{"role": "hero", "readable_at_grid": True}], current)
    assert out["substandard"] is True
    assert {"gallery_storytelling", "video_support"} <= set(out["behind"])
    assert out["rows"]["thumbnail_clarity"]["state"] == "level"
    # Dimensions our frame records cannot state are unjudged and named, not averaged in.
    assert "styling" in out["unjudged"] and "realism" in out["unjudged"]
    assert out["verdict"].startswith("reject")


def test_all_pods_reports_a_refusal_per_pod_rather_than_an_empty_set():
    db = _db()
    _pod(db)
    out = S.all_pods(db, now=NOW)
    assert out["pods_with_a_set"] == ["garments"]
    assert "blankets" in out["pods_without"]
    assert "below the stated minimum" in out["refused"]["blankets"]
    assert "unclassified" not in out["refused"]


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
