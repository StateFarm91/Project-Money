"""Tests for build_designs.py (no network). Run: .venv/bin/python products/pod/test_build_designs.py
Personalized text length is unpredictable (buyer's town/surname/name) -- the main risk is text
running off the canvas, which silently produces a bad print file rather than an error. These
tests render with deliberately long/short sample text and check every pixel row that should be
background-only actually is (i.e. no ink touches the left/right safety margin)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from build_designs import mug_welcome, print_cottage, tote_hockey, DESIGNS, MUG_SIZE, PRINT_SIZE, TOTE_SIZE


def assert_no_ink_in_margins(im, margin_frac, bg):
    """bg-coloured pixels only within `margin_frac` of each edge (allow a few px of AA)."""
    w, h = im.size
    m = int(w * margin_frac)
    px = im.load()
    for y in (0, h // 4, h // 2, 3 * h // 4, h - 1):
        for x in list(range(0, m, max(1, m // 8))) + list(range(w - m, w, max(1, m // 8))):
            p = px[x, y]
            assert p == bg, f"ink found in margin at ({x},{y}): {p} (expected background {bg})"


def test_mug_short_town_fits():
    im = mug_welcome(town="Muskoka", province="Ontario")
    assert im.size == MUG_SIZE
    assert_no_ink_in_margins(im, 0.05, (26, 43, 60))


def test_mug_long_town_and_province_still_fits():
    im = mug_welcome(town="Sault Ste. Marie", province="Newfoundland and Labrador", established=1912)
    assert_no_ink_in_margins(im, 0.03, (26, 43, 60))


def test_print_short_family_fits():
    im = print_cottage(family="McKenna", established="2024")
    assert im.size == PRINT_SIZE
    assert_no_ink_in_margins(im, 0.03, (250, 246, 235))


def test_print_long_hyphenated_family_fits():
    im = print_cottage(family="Papineau-Beauchamp", established="1998")
    assert_no_ink_in_margins(im, 0.03, (250, 246, 235))


def test_tote_short_name_fits():
    im = tote_hockey(name="James", number="17", role="mom")
    assert im.size == TOTE_SIZE
    assert_no_ink_in_margins(im, 0.03, (255, 255, 255))


def test_tote_long_name_and_role_fits():
    im = tote_hockey(name="Alexander", number="100", role="grandmother")
    assert_no_ink_in_margins(im, 0.03, (255, 255, 255))


def test_all_named_designs_render_without_error():
    for name, fn in DESIGNS.items():
        img = fn()
        assert img.size[0] > 0 and img.size[1] > 0, name


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn(); print("OK ", name)
            except Exception as e:
                fails += 1; print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
