"""D-OWNER-COMPETITIVE-BAR: the owner's ruling on the competitive standard (#220).

Owner, 2026-11-22 ~02:05Z, "Ship without video": "Drop the video requirement and require 7
photos instead of matching the top seller's 20. Size options become advisory. All other checks
stay the same."

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_competitive_bar.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_cert_improve_wave as W  # noqa: E402 - its db and benchmark/product fixture

SLUG = "fixture-bar"


def _setup(frames: int, *, extra_bars: dict | None = None):
    from brambleloop.core.models import CompetitiveStandard, ListingAsset

    db = W._db()
    W._benchmark_and_product(db, SLUG)
    bars = {"gallery_images": 20.0, "video_in_gallery": 1.0, "size_options": 9.0}
    bars.update(extra_bars or {})
    with db.session() as s:
        for k, v in bars.items():
            s.add(CompetitiveStandard(key=k, value=v, higher_is_better=True, history=[]))
        for pos in range(1, frames + 1):
            s.add(ListingAsset(product_slug=SLUG, version="1.0.0", position=pos,
                               asset_class="digital_twin_render", role="hero" if pos == 1
                               else "detail", approved=True))
    return db


def _gate(db):
    from brambleloop.publish import release_gates

    return release_gates.standards_gate(db, slug=SLUG, version="1.0.0")


def _competitive_reasons(g):
    return [r for r in g["reasons"] if r.startswith("competitive standard")]


def test_seven_frames_no_video_one_size_is_not_withheld():
    from brambleloop.publish import withholding

    db = _setup(7)
    g = _gate(db)
    assert _competitive_reasons(g) == [], g["reasons"]
    by = {c["standard"]: c for c in g["competitive"]}
    # the benchmark readings are still recorded and reported, unchanged
    assert by["gallery_images"]["bar"] == 20.0 and by["gallery_images"]["verdict"] == "below"
    assert by["video_in_gallery"]["verdict"] == "below"
    assert by["size_options"]["verdict"] == "below"
    # what binds is the ruling
    assert by["gallery_images"]["binding"] is True
    assert by["gallery_images"]["effective_bar"] == 7.0
    assert by["gallery_images"]["binding_verdict"] == "met"
    assert by["video_in_gallery"]["binding_verdict"] == "advisory"
    assert by["size_options"]["binding_verdict"] == "advisory"
    withholding.reconcile(db, SLUG, "1.0.0", standards=g)
    held = withholding.reasons(db, SLUG, "1.0.0")
    assert withholding.COMPETITIVE_STANDARD not in held["reasons"], held
    assert not any("competitive" in str(r) for r in held.get("publish_reasons") or []), held


def test_six_frames_is_still_withheld():
    from brambleloop.publish import withholding

    db = _setup(6)
    g = _gate(db)
    reasons = _competitive_reasons(g)
    assert len(reasons) == 1 and "gallery_images" in reasons[0] and "bar 7.0" in reasons[0], reasons
    withholding.reconcile(db, SLUG, "1.0.0", standards=g)
    held = withholding.reasons(db, SLUG, "1.0.0")
    assert withholding.COMPETITIVE_STANDARD in held["reasons"], held
    assert any("gallery_images" in str(r) for r in held["publish_reasons"]), held


def test_a_gallery_bar_below_seven_still_binds_as_set():
    db = _setup(4, extra_bars={"gallery_images": 5.0})
    g = _gate(db)
    by = {c["standard"]: c for c in g["competitive"]}
    assert by["gallery_images"]["effective_bar"] == 5.0
    assert by["gallery_images"]["binding_verdict"] == "below"
    assert _competitive_reasons(g), g["reasons"]


def test_any_other_standard_binds_exactly_as_the_benchmark_sets_it():
    db = _setup(7, extra_bars={"pdf_pages": 12.0})
    g = _gate(db)
    by = {c["standard"]: c for c in g["competitive"]}
    assert by["pdf_pages"]["binding"] is True and by["pdf_pages"]["effective_bar"] == 12.0
    assert by["pdf_pages"]["binding_verdict"] in ("below", "unmeasured")
    assert any("pdf_pages" in r for r in _competitive_reasons(g)), g["reasons"]


def test_other_withholding_kinds_are_unaffected():
    from brambleloop.intel import mission_runtime
    from brambleloop.publish import withholding

    db = _setup(7)
    mission_runtime.record_veto(db, subject_ref=f"product:{SLUG}",
                                scope="flagship_creative_quality", reason="generic",
                                note="reads as every other throw")
    g = _gate(db)
    assert any("owner veto" in r for r in g["reasons"]), g["reasons"]
    withholding.reconcile(db, SLUG, "1.0.0", standards=g)
    held = withholding.reasons(db, SLUG, "1.0.0")
    assert any("owner veto" in str(r) for r in held.get("publish_reasons") or []), held


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print("ok", name)
    print(f"OK {n} tests")
