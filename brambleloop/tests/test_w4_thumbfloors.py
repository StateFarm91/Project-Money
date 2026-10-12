"""W4-THUMBFLOORS: F-252 resolution and exposure floors in `thumbnail.evaluate_thumbnail`.

The first photo now has to clear two floors before its grid composition is even weighed:
* a short edge of at least `MIN_SHORT_EDGE_PX`, without which the listing cannot be zoomed;
* exposure read on the subject (a crushed or blown subject shows no stitch) and on the whole
  frame (too dark).
A white or dark *background* is never penalised. Click appeal compared against other listings
stays with the image_vision grid tournament (F-278).

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_thumbfloors.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

from brambleloop.commerce import thumbnail as T  # noqa: E402

CREAM, GREEN = (250, 246, 235), (36, 74, 58)


def _square(size, fill, subject, box_frac=(0.1, 0.1, 0.9, 0.9)):
    img = Image.new("RGB", (size, size), fill)
    x0, y0, x1, y1 = (round(v * size) for v in box_frac)
    img.paste(Image.new("RGB", (x1 - x0, y1 - y0), subject), (x0, y0))
    return img


def test_a_well_exposed_hero_at_zoom_resolution_passes_and_reports_its_floors():
    v = T.evaluate_thumbnail(_square(2000, CREAM, GREEN))
    assert v.ok, v.problems
    m = v.measurements
    assert m["short_edge_px"] == 2000
    assert m["subject_crushed_share"] == 0.0 and m["subject_blown_share"] == 0.0
    assert m["mean_luminance"] > T.MIN_FRAME_MEAN_LUMINANCE


def test_a_hero_too_small_to_zoom_is_flagged():
    v = T.evaluate_thumbnail(_square(T.MIN_SHORT_EDGE_PX - 100, CREAM, GREEN))
    assert any(p.startswith("THUMB_RESOLUTION_LOW") for p in v.problems), v.problems
    wide = Image.new("RGB", (2400, 800), CREAM)
    assert any(p.startswith("THUMB_RESOLUTION_LOW")
               for p in T.quality_floors(wide)["problems"]), "the short edge decides"
    assert T.quality_floors(_square(T.MIN_SHORT_EDGE_PX, CREAM, GREEN))["ok"]


def test_a_crushed_subject_is_underexposed():
    v = T.evaluate_thumbnail(_square(1200, CREAM, (4, 4, 4)))
    assert any(p.startswith("THUMB_UNDEREXPOSED") for p in v.problems), v.problems


def test_a_blown_subject_is_overexposed():
    v = T.evaluate_thumbnail(_square(1200, (176, 186, 172), (255, 255, 255)))
    assert any(p.startswith("THUMB_OVEREXPOSED") for p in v.problems), v.problems


def test_a_dark_frame_is_too_dark_even_when_the_subject_is_not_clipped():
    v = T.evaluate_thumbnail(_square(1200, (12, 12, 14), (60, 40, 30)))
    assert any(p.startswith("THUMB_FRAME_TOO_DARK") for p in v.problems), v.problems


def test_a_white_or_black_seamless_background_is_not_an_exposure_failure():
    white = T.quality_floors(_square(1200, (255, 255, 255), GREEN))
    assert white["ok"], white["problems"]
    black = T.quality_floors(_square(1200, (0, 0, 0), (200, 180, 160),
                                     box_frac=(0.05, 0.05, 0.95, 0.95)))
    assert black["ok"], black["problems"]


def test_the_contract_palettes_clear_the_exposure_floors():
    """Every Launch-0 render colour on the contract background: none is clipped."""
    from brambleloop.products import launch0 as L
    from brambleloop.visual import render_contract as K

    builds = ("cloudline_blanket", "snowfall_throw", "basket_medium", "hexagon_coasters",
              "snowflake_ornaments")
    assert builds
    for b in builds:
        for name, hexv in L.cir_for(b).colors.items():
            img = _square(2000, K.BACKGROUND, K.hex_rgb(hexv))
            out = T.quality_floors(img)
            assert out["ok"], (b, name, out["problems"])


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    sys.exit(bool(failures))
