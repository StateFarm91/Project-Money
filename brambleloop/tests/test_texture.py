"""Texture: stitches that do what the name says, and the check that they have to.

Three products were named for techniques their patterns could not contain. "Heirloom Cable
Throw", "Bobble Floor Pillow" and "Chunky Ribbed Scarf" were plain single and double crochet
colourwork — no crossing, no bobble, no rib in any of them — and one was the fourth-ranked
product in the selected portfolio, certified, with a drafted listing in production.

It is the flat-panel-called-a-basket defect in a different dimension: a name claiming
something the fabric does not do. Neither the shape check (silhouettes) nor Asset Truth (what
an image depicts) could see it, because everything about those patterns was internally
perfect.

So this file pins both halves of the fix. The vocabulary exists and behaves — a crossing
consumes four stitches and says so, a bobble costs five double crochets of yarn rather than
a default that would understate a cushion by a third. And the claim is checked: a name that
says cable, bobble or ribbed must be backed by stitches that do it, while names that claim
nothing of the sort are left alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir import stitches  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.reverse import compare, parse_pattern  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.gates.asset_truth import check_technique_claims  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.products.texture import (  # noqa: E402
    build_bobble_pillow, build_cable_throw, build_ribbed_scarf,
)

DESIGNS = (build_ribbed_scarf, build_bobble_pillow, build_cable_throw)


def _twin(cir):
    result = compile_cir(cir)
    assert result.ok, [str(f) for f in result.errors]
    return result, build_twin(cir, result)


# ---- the vocabulary --------------------------------------------------------


def test_a_crossing_consumes_four_stitches_and_produces_four():
    """The arithmetic the compiler guarantees stays exact; the re-ordering is a property of
    the stitch rather than prose nobody validated."""
    cable = stitches.get("cable2x2")
    assert cable.consumes == 4 and cable.produces == 4
    small = stitches.get("cable1x1")
    assert small.consumes == 2 and small.produces == 2


def test_post_stitches_cost_the_compiler_nothing_and_buy_ribbing():
    for code in ("fpdc", "bpdc"):
        st = stitches.get(code)
        assert st.consumes == 1 and st.produces == 1
        assert st.row_height > 1.0, "a post stitch is a double crochet's height, near enough"


def test_a_bobble_is_priced_as_five_double_crochets_not_as_a_default():
    """The default would have understated a bobble cushion by more than a third."""
    from brambleloop.cir.twin import _YARN_FACTOR

    assert _YARN_FACTOR["bob"] > 4 * _YARN_FACTOR["dc"]
    assert "cable2x2" in _YARN_FACTOR and "fpdc" in _YARN_FACTOR


def test_the_writer_says_how_many_stitches_a_crossing_consumes():
    """Hardcoding "over next 2 sts" meant the first stitch to consume more would have been
    written as though it consumed one."""
    cir = build_cable_throw()
    result, _ = _twin(cir)
    text = write_pattern(cir, result)
    assert "cable2x2 over next 4 sts" in text
    assert "over next 2 sts" not in text


def test_the_reader_refuses_a_crossing_over_the_wrong_number_of_stitches():
    """A document claiming a crossing over three stitches describes a manoeuvre that does
    not exist, and the count would still add up."""
    cir = build_cable_throw()
    result, _ = _twin(cir)
    text = write_pattern(cir, result)
    mutated = text.replace("cable2x2 over next 4 sts", "cable2x2 over next 3 sts")
    assert mutated != text
    codes = [f.code for f in compare(cir, mutated)]
    assert "REVERSE_PARSE" in codes, codes


def test_every_texture_design_round_trips():
    for build in DESIGNS:
        cir = build()
        result, _ = _twin(cir)
        assert not compare(cir, write_pattern(cir, result)), cir.slug
        assert parse_pattern(write_pattern(cir, result)), cir.slug


# ---- the products are what they say ----------------------------------------


def test_the_cable_throw_actually_crosses():
    cir = build_cable_throw()
    _, twin = _twin(cir)
    assert "cable2x2" in twin.stitch_types_used
    assert {"fpdc", "bpdc"} <= twin.stitch_types_used, "cables sit between ribbed columns"


def test_the_bobble_pillow_actually_bobbles_and_is_square():
    cir = build_bobble_pillow()
    _, twin = _twin(cir)
    assert "bob" in twin.stitch_types_used
    # A cushion cover is square, and an earlier version was half again as tall as it was wide.
    assert abs(twin.width_cm - twin.height_cm) < 3.0, (twin.width_cm, twin.height_cm)


def test_the_ribbed_scarf_is_ribbed_and_is_a_scarf():
    cir = build_ribbed_scarf()
    _, twin = _twin(cir)
    assert {"fpdc", "bpdc"} <= twin.stitch_types_used
    assert 18 < twin.width_cm < 28, twin.width_cm
    assert 130 < twin.height_cm < 175, twin.height_cm


def test_all_three_certify():
    for build in DESIGNS:
        cert = certify(build())
        assert cert.granted, (build.__name__, [str(f) for f in cert.errors])


def test_the_written_patterns_stay_readable():
    """A hundred and forty identical ribbing rows is a document nobody can use. The row-cycle
    collapse is what makes a texture pattern printable at all."""
    for build in DESIGNS:
        cir = build()
        result, _ = _twin(cir)
        printed = [l for l in write_pattern(cir, result).splitlines()
                   if l.startswith("Row ")]
        worked = len(cir.components[0].rows)
        assert len(printed) < 12, (cir.slug, len(printed))
        assert worked > 50, (cir.slug, worked)


# ---- the claim -------------------------------------------------------------


def test_a_name_claiming_a_technique_the_fabric_does_not_work_is_refused():
    """The defect exactly as it shipped: every one of these was plain sc and dc."""
    from fixtures import good_mosaic_panel

    cir = good_mosaic_panel()
    _, twin = _twin(cir)
    for title in ("Heirloom Cable Throw", "Bobble Floor Pillow", "Chunky Ribbed Scarf",
                  "Waffle Stitch Blanket", "Popcorn Cushion"):
        findings = check_technique_claims(title, cir, twin)
        assert [f.code for f in findings] == ["CLAIM_TECHNIQUE_UNSUPPORTED"], title


def test_the_rebuilt_products_pass_the_check_that_blocked_them():
    for build in DESIGNS:
        cir = build()
        _, twin = _twin(cir)
        assert not check_technique_claims(cir.title, cir, twin), cir.title


def test_a_name_claiming_nothing_technical_is_left_alone():
    """The check has to be narrow, or it blocks products that were never lying."""
    from fixtures import good_mosaic_panel

    cir = good_mosaic_panel()
    _, twin = _twin(cir)
    for title in ("Nordic Forest Overlay Mosaic Throw", "Harvest Table Runner",
                  "Cloudline Textured Baby Blanket", "Pet Snuggle Mat"):
        assert not check_technique_claims(title, cir, twin), title


def test_mosaic_needs_more_than_one_colour():
    """A colour technique is checked by colour, not by stitch."""
    from fixtures import good_sphere

    cir = good_sphere()          # one colour throughout
    _, twin = _twin(cir)
    findings = check_technique_claims("Mosaic Throw", cir, twin)
    assert [f.code for f in findings] == ["CLAIM_TECHNIQUE_UNSUPPORTED"]


def test_the_certificate_runs_the_technique_check():
    """It has to be in the chain, not merely available: the three products that shipped were
    all certified."""
    from fixtures import good_mosaic_panel

    from brambleloop.cir.model import CIR

    cir = good_mosaic_panel()
    renamed = CIR.from_dict({**cir.to_dict(), "title": "Heirloom Cable Throw"})
    cert = certify(renamed)
    assert not cert.granted
    assert "CLAIM_TECHNIQUE_UNSUPPORTED" in [f.code for f in cert.errors]



# ---- the hero has to show the fabric ---------------------------------------


def test_a_single_colour_textured_fabric_is_visible():
    """Found in production: the rebuilt cable throw's hero was a blank cream rectangle.

    Colourwork is not the only way fabric has a pattern. A cabled throw in one cream yarn is
    *all* relief -- the design is light and shadow off the stitch geometry -- and colouring
    cells by their row's yarn rendered nothing at all.
    """
    from brambleloop.publish.charts import render_fabric

    for build in DESIGNS:
        cir = build()
        result, twin = _twin(cir)
        assert len([c for c in twin.colors_used if c]) == 1, \
            f"{cir.slug} is single-colour by design; this test would prove nothing otherwise"
        fabric = render_fabric(cir, twin, cell_px=18).convert("RGB")
        shades = fabric.getcolors(maxcolors=100_000) or []
        lums = [0.299 * r + 0.587 * g + 0.114 * b for _, (r, g, b) in shades]
        assert len(shades) >= 3, (cir.slug, len(shades))
        assert max(lums) - min(lums) > 12.0, (cir.slug, max(lums) - min(lums))


def test_a_blank_hero_is_refused_even_though_its_text_is_not_blank():
    """The hole this closes: the frame-level thumbnail check measured the *title text* as the
    subject, so a hero with no fabric in it scored 78% coverage and passed locally while
    production rejected the same product at 11%."""
    from brambleloop.publish.listing_assets import Frame, check_frame_plan
    from brambleloop.gates.asset_truth import AssetClass

    frames = [
        Frame(position=1, role="hero", asset_class=AssetClass.DIGITAL_TWIN_RENDER,
              caption="hero", image=None, fabric_is_flat=True),
        Frame(position=2, role="whats_included", asset_class=AssetClass.INFOGRAPHIC,
              caption="what you get"),
        Frame(position=3, role="size", asset_class=AssetClass.INFOGRAPHIC, caption="size"),
        Frame(position=4, role="materials", asset_class=AssetClass.INFOGRAPHIC,
              caption="materials"),
    ]
    problems = check_frame_plan(frames)
    assert any("LISTING_HERO_FABRIC_FLAT" in p for p in problems), problems


def test_the_real_heroes_are_not_flat():
    from brambleloop.cir.writer import write_pattern
    from brambleloop.publish.listing_assets import build_frames, check_frame_plan

    for build in DESIGNS:
        cir = build()
        result, twin = _twin(cir)
        frames = build_frames(cir, twin, pattern_text=write_pattern(cir, result),
                              difficulty="confident beginner", pages=7)
        assert frames[0].fabric_is_flat is False, cir.slug
        assert check_frame_plan(frames) == [], (cir.slug, check_frame_plan(frames))


def test_a_missing_font_is_a_blocking_problem_rather_than_ugly_output():
    """Pillow falls back to a face a few pixels tall. On a 2000px image that is invisible, so
    the imagery looked right on a machine with DejaVu installed and shipped from a container
    without it carrying no legible text at all. Silence is what let that happen."""
    from brambleloop.publish import charts
    from brambleloop.publish.listing_assets import check_frame_plan

    before = charts.FONT_FALLBACK_IN_USE
    try:
        charts.FONT_FALLBACK_IN_USE = True
        problems = check_frame_plan([])
        # An empty plan has its own complaint; the font one must appear for a real plan too.
        cir = build_bobble_pillow()
        result, twin = _twin(cir)
        from brambleloop.cir.writer import write_pattern
        from brambleloop.publish.listing_assets import build_frames

        frames = build_frames(cir, twin, pattern_text=write_pattern(cir, result),
                              difficulty="confident beginner", pages=7)
        problems = check_frame_plan(frames)
        assert any("LISTING_NO_FONT" in p for p in problems), problems
    finally:
        charts.FONT_FALLBACK_IN_USE = before


def test_the_container_installs_the_fonts_the_renderer_needs():
    """The defect itself: nothing in the image had fonts, and no local test could see it."""
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "fonts-dejavu" in dockerfile, \
        "the container renders every listing image; without a TrueType face the text is a " \
        "few pixels tall"

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
