"""Measuring the rendered frame, because the plan was never the thing that was wrong.

v1.4.3 requirement 59. Build 1 shipped listing images whose text was a few pixels tall, on a
hero whose fabric render had no internal contrast, and everything upstream reported success:
the plan was correct, the renderer ran, the file was written. The defect existed only in the
pixels and nothing was looking at the pixels.

So these tests build the failures as images and assert they are caught. The background is
inferred from the corners rather than assumed from the palette -- a check that hardcodes cream
passes a blank frame the day the brand changes, and the blank frame is what it was written to
catch.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw  # noqa: E402

from brambleloop.publish import layout_qa as Q  # noqa: E402

CREAM = (250, 246, 235)
PINE = (46, 74, 58)


def _frame(image, position: int = 1):
    class _F:
        pass

    f = _F()
    f.image = image
    f.position = position
    return f


def _blank(size=(600, 450), colour=CREAM) -> Image.Image:
    return Image.new("RGB", size, colour)


def _subject(size=(600, 450), box=(150, 110, 450, 340)) -> Image.Image:
    image = _blank(size)
    ImageDraw.Draw(image).rectangle(list(box), fill=PINE)
    return image


def _codes(problems) -> set[str]:
    return {p.split(":")[0] for p in problems}


# ---- the defect this module was written for -------------------------------


def test_a_blank_frame_is_caught_where_every_upstream_check_passed():
    report = Q.inspect(_blank(), position=1)

    assert _codes(report.problems) == {"FRAME_FLAT"}, report.problems
    assert any("reported success" in p for p in report.problems)


def test_the_background_is_inferred_rather_than_assumed_from_the_palette():
    """A check that hardcodes cream passes a blank frame the day the brand changes."""
    on_charcoal = Q.inspect(_blank(colour=(30, 30, 32)), position=1)

    assert "FRAME_FLAT" in _codes(on_charcoal.problems)


def test_a_frame_with_a_subject_passes():
    report = Q.inspect(_subject(), position=1)

    assert report.ok, report.problems
    assert report.ink_share > 0.2


# ---- the search grid ------------------------------------------------------


def test_an_image_that_dies_at_thumbnail_size_is_caught():
    """An image legible at two thousand pixels and uniform in the search grid is an image
    nobody will ever click."""
    image = _blank((2000, 1500))
    draw = ImageDraw.Draw(image)
    # A fine one-pixel grid: real ink at listing scale, and nothing a 170px thumbnail can
    # resolve. This is the shape of the defect rather than a contrived one -- hairline chart
    # rules and thin type behave exactly this way.
    for x in range(0, 2000, 4):
        draw.line([(x, 0), (x, 1499)], fill=PINE, width=1)

    report = Q.inspect(image, position=1)

    assert report.ink_share >= 0.01
    assert "FRAME_DIES_AT_THUMBNAIL" in _codes(report.problems), report.problems


def test_content_in_the_badge_band_is_content_at_risk():
    image = _blank()
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, 599, 30], fill=PINE)
    draw.rectangle([0, 420, 599, 449], fill=PINE)
    draw.rectangle([0, 0, 20, 449], fill=PINE)
    draw.rectangle([579, 0, 599, 449], fill=PINE)

    report = Q.inspect(image, position=2)

    assert "FRAME_EDGE_CLIPPING" in _codes(report.problems)
    assert any("badges" in p for p in report.problems)


def test_a_subject_the_mobile_crop_removes_is_caught():
    """The grid applies that crop, so the shopper sees the part that was left over."""
    wide = _blank((1200, 400))
    ImageDraw.Draw(wide).rectangle([20, 150, 260, 250], fill=PINE)

    report = Q.inspect(wide, position=1)

    assert "FRAME_CROP_LOSS" in _codes(report.problems)
    assert report.crop_survival < Q.MIN_CROP_SURVIVAL


# ---- composition ----------------------------------------------------------


def test_a_frame_with_a_subject_too_small_to_see_is_flat_too():
    """One rule rather than two. A frame that is 99.96% one colour and a frame that is 100%
    one colour are the same frame to a shopper, and a second code for the near-miss is a
    distinction only the code can see."""
    image = _blank()
    ImageDraw.Draw(image).rectangle([295, 220, 305, 230], fill=PINE)

    assert "FRAME_FLAT" in _codes(Q.inspect(image, position=3).problems)


def test_a_full_bleed_frame_is_flat_rather_than_empty():
    """The first version of this inferred the background from the corners, so a subject that
    reached them became the background by definition and a frame that was 97% one block of
    colour was reported as 96% empty. Both failures are the same failure: one colour is the
    whole frame."""
    image = _blank()
    ImageDraw.Draw(image).rectangle([5, 5, 594, 444], fill=PINE)

    report = Q.inspect(image, position=3)

    assert "FRAME_FLAT" in _codes(report.problems), report.problems
    assert any("one colour" in p for p in report.problems)


def test_type_a_few_pixels_tall_is_caught_where_the_renderer_raised_nothing():
    """The font-fallback defect, as an image rather than as a stack trace."""
    image = _blank()
    draw = ImageDraw.Draw(image)
    for y in range(220, 224):
        for x in range(120, 480, 3):
            draw.point((x, y), fill=PINE)

    report = Q.inspect(image, position=4, expect_text=True)

    assert "FRAME_TEXT_TOO_SMALL" in _codes(report.problems)
    assert any("rendered without error" in p for p in report.problems)


def test_text_of_a_reasonable_height_passes():
    image = _blank()
    draw = ImageDraw.Draw(image)
    for y in range(200, 240):
        for x in range(120, 300, 2):
            draw.point((x, y), fill=PINE)

    report = Q.inspect(image, position=4, expect_text=True)

    assert "FRAME_TEXT_TOO_SMALL" not in _codes(report.problems), report.problems


# ---- across a gallery ------------------------------------------------------


def test_an_unrendered_frame_is_named_rather_than_skipped():
    """An unrendered frame is the state in which every pixel rule passes by having nothing
    to measure."""
    class _Missing:
        image = None
        position = 2

    problems = Q.check_frames([_frame(_subject(), 1), _Missing()])

    assert "FRAME_NOT_RENDERED" in _codes(problems)


def test_a_gallery_that_mixes_aspect_ratios_is_caught():
    problems = Q.check_frames([
        _frame(_subject((600, 450)), 1),
        _frame(_subject((600, 600), (150, 150, 450, 450)), 2),
    ])

    assert "FRAME_RATIOS_DISAGREE" in _codes(problems)
    assert any("reads as a reseller's page" in p for p in problems)


def test_a_consistent_gallery_passes():
    frames = [_frame(_subject(), i) for i in (1, 2, 3)]

    report = Q.report(frames)

    assert report["ok"] is True, report["problems"]
    assert len(report["frames"]) == 3
    assert all(f["rendered"] for f in report["frames"])
    assert "rather than about the code that drew it" in report["note"]


# ---- #62: the hero is held to it in the real chain -------------------------


def test_the_hero_standard_runs_inside_the_listing_check():
    """Everything else in that function checks the hero is truthful. This checks it is
    legible, and the two fail independently: Build 1's hero was entirely truthful and
    entirely invisible."""
    from brambleloop.gates.asset_truth import AssetClass
    from brambleloop.publish.listing_assets import Frame, check_frame_plan

    blank_hero = Frame(position=1, role="hero", asset_class=AssetClass.DIGITAL_TWIN_RENDER,
                       caption="hero", image=_blank((800, 800)))

    problems = check_frame_plan([blank_hero])

    assert any(p.startswith("LISTING_HERO_FRAME_FLAT") for p in problems), problems


def test_a_chart_may_not_be_the_hero():
    """The hero answers 'what will I have made'. A diagram answers 'how' to somebody who has
    not decided to care yet."""
    from brambleloop.gates.asset_truth import AssetClass
    from brambleloop.publish.listing_assets import Frame, check_frame_plan

    chart_hero = Frame(position=1, role="hero", asset_class=AssetClass.INFOGRAPHIC,
                       caption="chart", image=_subject((800, 800), (200, 200, 600, 600)))

    problems = check_frame_plan([chart_hero])

    assert any("LISTING_HERO_IS_AN_INFOGRAPHIC" in p for p in problems), problems


def test_a_legible_hero_raises_no_layout_problem():
    from brambleloop.gates.asset_truth import AssetClass
    from brambleloop.publish.listing_assets import Frame, check_frame_plan

    good_hero = Frame(position=1, role="hero", asset_class=AssetClass.DIGITAL_TWIN_RENDER,
                      caption="hero", image=_subject((800, 800), (200, 180, 600, 620)))

    problems = check_frame_plan([good_hero])

    assert not [p for p in problems if p.startswith("LISTING_HERO_FRAME")], problems


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
