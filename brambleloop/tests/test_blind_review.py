"""The competitive blind review writes the row parity reads, and never flatters (#75, #71).

`visual.parity`'s eighth dimension read an audit row nothing wrote, so the creative parity
gate could never pass and the note beside it called the gap "draining". These tests pin the
writer to the reader, and pin the two ways the verdict could be flattered: a pod nobody has
observed, and a product nobody has rendered. Both are UNKNOWN, and UNKNOWN blocks.
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
from brambleloop.creative import blind_review as R  # noqa: E402
from brambleloop.visual import parity  # noqa: E402

KEY = "mjs_off_the_hook_designs"


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _observed_pod(db, pod: str = "blankets", listings: int = 4, images: int = 3, *,
                  legible: bool = True, video: bool = True, media: int = 8) -> None:
    """A pod with enough judged images to be a standard."""
    with db.session() as s:
        for i in range(listings):
            ref = f"{pod}-{i}"
            s.add(BenchmarkListing(
                benchmark_key=KEY, listing_ref=ref, title=f"{pod} {i}", pod=pod,
                audit_state="audited", media_count=media,
                detail={"gallery_audited": True, "has_video": video,
                        "image_urls": ["https://i.etsystatic.com/x.jpg"] * media}))
            shots = ("hero_styled", "detail_macro", "flat_lay", "in_use")
            for rank in range(images):
                s.add(BenchmarkObservation(
                    benchmark_key=KEY, listing_ref=ref, kind="gallery_image_observation",
                    at=datetime(2026, 9, 20 + i, tzinfo=timezone.utc),
                    detail={"image": {"rank": rank + 1},
                            "observation": {
                                "shot_type": shots[rank % len(shots)],
                                "thumbnail_readability": ("reads clearly at grid scale"
                                                          if legible else
                                                          "unreadable at thumbnail size"),
                                "detail_coverage": "close stitch detail shown"}}))


def _frame(role: str = "hero", readable: bool | None = True) -> dict:
    return {"made": True, "role": role, "readable_at_grid": readable, "slug": "x",
            "version": "1.0.0", "image_ref": f"ref-{role}"}


def _parity_reads(db, slug: str) -> dict | None:
    """Exactly the read `runtime.pipeline._listing_parity` performs."""
    from brambleloop.runtime import pipeline

    return pipeline._benchmark_quality(db, slug)


# ---- the writer meets the reader --------------------------------------------


def test_the_row_written_is_the_row_parity_reads():
    """The whole point: after `record`, the pipeline's reader finds a verdict for the slug
    and parity's COMPETITIVE dimension is no longer unjudged."""
    db = _db()
    _observed_pod(db)
    frames = [_frame("hero"), _frame("detail"), _frame("chart"), _frame("flat"),
              _frame("scale"), _frame("in_use"), _frame("fit"), _frame("process")]
    result = R.review(db, slug="autumn-oak-mosaic-throw", pod="blankets", frames=frames)
    R.record(db, result)

    read = _parity_reads(db, "autumn-oak-mosaic-throw")
    assert read is not None and read["slug"] == "autumn-oak-mosaic-throw"
    assert "materially_inferior" in read

    out = parity.assess([{**f, "carries_model": False, "motif": {"verdict": "match"},
                          "photographic_realism": {"verdict": "clear"},
                          "inspection": {"described": True,
                                         "semantic": {"finished_or_in_progress_agrees": True}}}
                         for f in frames], benchmark_quality=read)
    assert out["dimensions"][parity.COMPETITIVE]["verdict"] != parity.UNJUDGED
    assert out["dimensions"][parity.COMPETITIVE]["why"] == read["why"]


def test_a_pod_nobody_has_observed_is_unknown_and_unknown_blocks():
    """Absent observations are UNKNOWN, never PASS. Parity reads the row and still blocks."""
    db = _db()
    result = R.review(db, slug="cloudline-baby-blanket", pod="blankets",
                      frames=[_frame("hero"), _frame("detail")])
    assert result["verdict"] == R.UNKNOWN
    assert result["materially_inferior"] is None
    assert "below the floor" in result["why"]
    R.record(db, result)

    read = _parity_reads(db, "cloudline-baby-blanket")
    assert read is not None
    out = parity.assess([_frame("hero") | {"carries_model": False,
                                           "motif": {"verdict": "match"},
                                           "photographic_realism": {"verdict": "clear"},
                                           "inspection": {"described": True, "semantic": {
                                               "finished_or_in_progress_agrees": True}}}],
                        benchmark_quality=read)
    assert out["dimensions"][parity.COMPETITIVE]["verdict"] == parity.UNJUDGED
    assert out["blocks_release"] is True


def test_a_thin_standard_is_unknown_rather_than_easy_to_clear():
    """Five judged images across two listings is one photographer's decisions, not a
    category standard -- and a thin standard is the easiest kind to clear."""
    db = _db()
    _observed_pod(db, listings=2, images=2)
    result = R.review(db, slug="s", pod="blankets", frames=[_frame("hero")])
    assert result["verdict"] == R.UNKNOWN
    assert result["standard"]["sufficient"] is False
    assert result["standard"]["observations"] == 4


def test_a_product_with_no_render_is_unknown_not_a_pass():
    db = _db()
    _observed_pod(db)
    result = R.review(db, slug="nothing-rendered", pod="blankets", frames=[])
    assert result["verdict"] == R.UNKNOWN
    assert result["materially_inferior"] is None
    assert "nothing to compare" in result["why"].lower()


# ---- the verdict itself -------------------------------------------------------


def test_a_single_hero_against_deep_observed_galleries_is_materially_inferior():
    """Today's honest reading of this catalogue: one frame, no detail, no video, against
    galleries observed to carry eight images, close stitch work and a video. That is the
    finding, and it is written as `materially_inferior: True`."""
    db = _db()
    _observed_pod(db, media=8, video=True)
    result = R.review(db, slug="harvest-table-runner", pod="blankets",
                      frames=[_frame("hero", readable=True)])
    assert result["verdict"] == R.INFERIOR
    assert result["materially_inferior"] is True
    behind = set(result["comparison"]["behind"])
    assert {"gallery_depth", "shot_variety", "video"} <= behind
    # The verdict cites the rows it was drawn from, dated.
    assert len(result["evidence"]["observation_ids"]) == 12
    assert result["evidence"]["observation_dates"]["oldest"].startswith("2026-09-20")
    assert result["evidence"]["listing_refs"] == [f"blankets-{i}" for i in range(4)]

    out = parity.assess(
        [_frame("hero") | {"carries_model": False, "motif": {"verdict": "match"},
                           "photographic_realism": {"verdict": "clear"},
                           "inspection": {"described": True, "semantic": {
                               "finished_or_in_progress_agrees": True}}}],
        benchmark_quality=result)
    assert out["dimensions"][parity.COMPETITIVE]["verdict"] == parity.FAIL


def test_a_frame_that_does_not_read_at_grid_scale_is_decisive_on_its_own():
    """Thumbnail readability is where the buying decision starts, so behind on it alone is
    material even when every other dimension is level."""
    db = _db()
    _observed_pod(db, media=2, images=2, video=False)
    frames = [_frame("hero", readable=False), _frame("detail")]
    result = R.review(db, slug="s", pod="blankets", frames=frames)
    assert result["comparison"]["behind"] == [R.DECISIVE]
    assert result["materially_inferior"] is True


def test_level_on_every_judged_dimension_is_not_inferior_and_cites_its_evidence():
    db = _db()
    _observed_pod(db, media=2, images=2, video=False)
    frames = [_frame("hero"), _frame("detail")]
    result = R.review(db, slug="s", pod="blankets", frames=frames)
    assert result["verdict"] == R.NOT_INFERIOR
    assert result["materially_inferior"] is False
    assert result["comparison"]["behind"] == []
    assert result["evidence"]["observation_ids"]


def test_an_unchecked_frame_leaves_the_decisive_dimension_unjudged():
    """`readable_at_grid: None` is "nobody checked", which is not "reads"."""
    db = _db()
    _observed_pod(db, media=2, images=2, video=False)
    result = R.review(db, slug="s", pod="blankets",
                      frames=[_frame("hero", readable=None), _frame("detail")])
    assert result["comparison"]["dimensions"][R.DECISIVE]["state"] == "unjudged"
    assert R.DECISIVE not in result["comparison"]["behind"]


def test_a_row_without_the_fields_the_reader_needs_is_refused():
    db = _db()
    try:
        R.record(db, {"slug": "x"})
    except R.ReviewRefused:
        pass
    else:
        raise AssertionError("a row parity cannot read was written")


def test_the_run_writes_one_row_per_product_and_reports_counts():
    """Over the real catalogue, with no observation: every product UNKNOWN, one row each,
    and `last_review` finds each row by slug."""
    db = _db()
    out = R.run(db)
    assert out["reviewed"] == len(R.catalogue_slugs()) > 0
    assert out["counts"][R.UNKNOWN] == out["reviewed"]
    for slug, _title in R.catalogue_slugs():
        row = R.last_review(db, slug=slug)
        assert row is not None and row["slug"] == slug
        assert row["materially_inferior"] is None


def test_our_products_are_routed_by_the_same_router_as_the_benchmark():
    from brambleloop.intel import pods

    assert R.pod_for("autumn-oak-mosaic-throw", "Autumn Oak Mosaic Throw") == \
        pods.route("Autumn Oak Mosaic Throw") == "blankets"
    # A title that routes nowhere falls back to the catalogue's recorded pod.
    assert R.pod_for("winter-village-graphghan", "Winter Village Graphghan") == "home_decor"


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
