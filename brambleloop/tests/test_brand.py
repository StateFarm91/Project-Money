"""Brand system, storefront and listing imagery (Master Plan sections 6, 7).

The thing being tested here is consistency under automation. A human designer keeps a shop
coherent by looking at it; an autonomous system producing assets unattended for months has no
equivalent, so the rules have to be data and the drift has to be detectable.

The listing-image tests care about one property above all others: a frame may never assert
something the compiled pattern does not produce. Every frame is rendered from the twin, so
that property holds by construction — these tests exist to prove it still holds after someone
edits the renderer.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.brand import bible, storefront  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.gates.asset_truth import AssetClass, check_assets  # noqa: E402
from brambleloop.products import nordic_forest as nf  # noqa: E402
from brambleloop.publish.charts import (  # noqa: E402
    crop_grids, detect_repeat, render_fabric,
)
from brambleloop.publish.listing_assets import build_frames, check_frame_plan  # noqa: E402

_CACHE: dict = {}


def _product():
    if not _CACHE:
        cir = nf.build("throw")
        result = compile_cir(cir)
        twin = build_twin(cir, result)
        _CACHE["cir"], _CACHE["result"], _CACHE["twin"] = cir, result, twin
        _CACHE["frames"] = build_frames(
            cir, twin, pattern_text=write_pattern(cir, result),
            difficulty="confident beginner", pages=8,
            siblings=["Nordic Star Ornament Set"])
    return _CACHE


# ---- brand identity --------------------------------------------------------


def test_the_palette_is_the_owners_palette():
    """Warm cream / forest / wine / muted gold, per the brand bible."""
    for name in ("pine", "cream", "wine", "gold", "ink"):
        assert name in bible.PALETTE
        assert bible.PALETTE[name].startswith("#") and len(bible.PALETTE[name]) == 7


def test_collection_names_follow_the_grammar():
    assert bible.check_collection_name("Nordic Forest") == []
    assert bible.check_collection_name("Autumn Oak") == []


def test_marketplace_filler_names_are_rejected():
    """An unconstrained namer produces exactly the generic AI store the bible warns against."""
    problems = bible.check_collection_name("Cozy Autumn Vibes")
    assert any("GENERIC" in p for p in problems), problems
    assert any("SHAPE" in p for p in problems), problems


# ---- the brand model -------------------------------------------------------


def test_the_model_brief_fixes_every_continuity_trait():
    brief = bible.model_brief("garment", "cardigan", season="autumn")
    for trait in ("face proportions", "eye colour", "hair colour", "hair length",
                  "body proportions", "approximate age"):
        assert trait in brief, trait
    assert bible.check_model_prompt(brief, "garment") == []


def test_the_model_may_not_be_built_as_a_likeness_of_a_real_person():
    """The bible is explicit, and 'it is only a reference' is not an exception."""
    for attempt in ("a model who looks like Megan Fox",
                    "brunette, based on the actress from that film",
                    "a Zendaya lookalike of about thirty"):
        try:
            bible.check_model_prompt(attempt, "garment")
        except bible.RealPersonLikeness as e:
            assert "fictional character" in str(e)
        else:
            raise AssertionError(f"accepted a real-person likeness: {attempt!r}")


def test_the_model_is_refused_where_product_first_imagery_is_stronger():
    """A model holding a blanket hides the pattern the customer is buying."""
    for category in ("mosaic_blanket", "amigurumi", "ornament", "baby"):
        problems = bible.check_model_prompt(bible.MODEL_TRAITS["hair"], category)
        assert any("WRONG_PRODUCT" in p for p in problems), (category, problems)
        try:
            bible.model_brief(category, "thing")
        except ValueError as e:
            assert "product-first" in str(e)
        else:
            raise AssertionError(f"built a model brief for {category}")


def test_an_underspecified_model_brief_is_rejected():
    problems = bible.check_model_prompt("a nice brunette in a cardigan", "garment")
    assert any("UNDERSPECIFIED" in p for p in problems), problems


# ---- grid coherence --------------------------------------------------------


def test_a_coherent_grid_passes():
    items = [bible.GridItem(slug=f"p{i}", title="t",
                            palette={"a": bible.PALETTE["pine"], "b": bible.PALETTE["cream"]},
                            hero_class="DIGITAL_TWIN_RENDER", collection="Nordic Forest")
             for i in range(6)]
    report = bible.check_grid_coherence(items)
    assert report.ok, report.problems
    assert report.palette_share == 1.0


def test_a_grid_where_every_listing_picked_its_own_colours_is_flagged():
    items = [bible.GridItem(slug=f"p{i}", title="t",
                            palette={"a": f"#{i}{i}00{i}{i}"},
                            hero_class="DIGITAL_TWIN_RENDER") for i in range(6)]
    report = bible.check_grid_coherence(items)
    assert not report.ok
    assert any("PALETTE" in p for p in report.problems), report.problems


def test_mixed_hero_treatments_are_flagged():
    classes = ["DIGITAL_TWIN_RENDER", "AI_LIFESTYLE_CONCEPT", "INFOGRAPHIC",
               "PATTERN_PREVIEW", "PHYSICAL_PRODUCT_PHOTO", "INFOGRAPHIC"]
    items = [bible.GridItem(slug=f"p{i}", title="t",
                            palette={"a": bible.PALETTE["pine"]}, hero_class=c)
             for i, c in enumerate(classes)]
    report = bible.check_grid_coherence(items)
    assert any("HERO_INCONSISTENT" in p for p in report.problems), report.problems


# ---- storefront ------------------------------------------------------------


def test_the_storefront_is_complete_before_anything_is_published():
    store = storefront.build_storefront("Christmas")
    assert store.ok, store.problems
    assert store.about and len(store.about) > storefront.ABOUT_MIN
    assert len(store.announcement) <= storefront.ANNOUNCEMENT_MAX
    for required in ("delivery", "returns", "licence", "support", "privacy"):
        assert store.policies[required].strip(), required


def test_the_refund_policy_says_plainly_that_a_pattern_cannot_be_returned():
    """Disclosed before purchase, not discovered after it."""
    store = storefront.build_storefront()
    returns = store.policies["returns"]
    assert "cannot be returned" in returns.lower()
    # And it says what we do instead, or it is just a refusal.
    assert "correct the pattern" in returns.lower()


def test_an_incomplete_storefront_is_caught():
    store = storefront.build_storefront()
    store.policies["returns"] = "no refunds"
    store.about = "we sell patterns"
    problems = storefront.check_storefront(store)
    assert any("ABOUT_THIN" in p for p in problems), problems
    assert any("RETURNS_UNCLEAR" in p for p in problems), problems


def test_every_pool_category_lands_in_a_section():
    from brambleloop.radar.opportunity import POOL

    for seed in POOL:
        slug = storefront.section_for(seed.category, seed.is_bundle)
        assert slug in {s.slug for s in storefront.SECTIONS}, (seed.category, slug)


# ---- listing imagery -------------------------------------------------------


def test_the_frame_plan_answers_the_questions_that_stop_a_purchase():
    frames = _product()["frames"]
    assert check_frame_plan(frames) == []
    roles = [f.role for f in frames]
    assert roles[0] == "hero"
    for required in ("whats_included", "size", "materials", "pattern_preview", "chart"):
        assert required in roles, required


def test_the_hero_is_a_render_that_admits_it_is_a_render():
    frames = _product()["frames"]
    hero = frames[0]
    assert hero.is_hero
    assert hero.asset_class is AssetClass.DIGITAL_TWIN_RENDER
    assert hero.image.width == hero.image.height == 2000


def test_an_ai_lifestyle_concept_can_never_be_the_hero():
    """A picture of a thing nobody has made is not evidence the thing exists."""
    frames = list(_product()["frames"])
    frames[0].asset_class = AssetClass.AI_LIFESTYLE_CONCEPT
    try:
        problems = check_frame_plan(frames)
        assert any("HERO_IS_A_CONCEPT" in p for p in problems), problems
    finally:
        frames[0].asset_class = AssetClass.DIGITAL_TWIN_RENDER


def test_every_frame_survives_asset_truth():
    p = _product()
    findings = check_assets([f.to_asset("nordic-forest-mosaic-throw") for f in p["frames"]],
                            p["cir"], p["twin"])
    errors = [f for f in findings if f.is_error]
    assert not errors, [str(f) for f in errors]


def test_the_size_frame_claims_the_twins_size_and_not_a_rounder_one():
    p = _product()
    size_frame = next(f for f in p["frames"] if f.role == "size")
    assert size_frame.claims.finished_width_cm == p["twin"].width_cm
    assert size_frame.claims.finished_height_cm == p["twin"].height_cm


def test_a_frame_claiming_a_size_the_pattern_does_not_produce_is_blocked():
    p = _product()
    frames = list(p["frames"])
    liar = next(f for f in frames if f.role == "size")
    original = liar.claims.finished_width_cm
    liar.claims.finished_width_cm = 250.0
    try:
        findings = check_assets([f.to_asset("x") for f in frames], p["cir"], p["twin"])
        assert any(f.code.startswith("CLAIM_SIZE") for f in findings), findings
    finally:
        liar.claims.finished_width_cm = original


def test_a_short_frame_plan_is_rejected():
    frames = _product()["frames"][:1]
    problems = check_frame_plan(frames)
    assert any("MISSING_FRAME" in p for p in problems), problems


# ---- the fabric render -----------------------------------------------------


def test_the_fabric_render_shows_the_motif_rather_than_stripes():
    """Overlay mosaic works one colour per row, so colouring cells by row yarn gives stripes.

    The first version of the renderer did exactly that and the fir trees vanished. The motif
    comes from the taller stitches hanging down into the previous row's contrasting band, so
    a correct render has vertical structure, not just horizontal bands.
    """
    p = _product()
    grid, colour_grid = p["twin"].chart_grid(), p["twin"].color_grid()
    cols, rows = detect_repeat(grid, colour_grid)
    img = render_fabric(p["cir"], p["twin"], cell_px=20,
                        grids=crop_grids(grid, colour_grid, cols * 2, rows))

    px = img.load()
    # Count columns whose pixels are not all identical down the image. Pure stripes give
    # every column the same vertical sequence; a motif does not.
    distinct_columns = set()
    for x in range(0, img.width, 20):
        distinct_columns.add(tuple(px[x, y] for y in range(0, img.height, 12)))
    assert len(distinct_columns) > 3, (
        f"only {len(distinct_columns)} distinct column profiles -- the render is stripes, "
        f"not a mosaic motif")


def test_the_fabric_render_cannot_invent_a_colour():
    p = _product()
    img = render_fabric(p["cir"], p["twin"], cell_px=8)
    used = {img.getpixel((x, y)) for x in range(0, img.width, 17)
            for y in range(0, img.height, 17)}
    from brambleloop.publish.charts import _hex_to_rgb

    allowed = {_hex_to_rgb(v) for v in p["cir"].colors.values()}
    # Every sampled pixel is a pattern colour or a highlight derived from one.
    for pixel in used:
        near = min(sum((a - b) ** 2 for a, b in zip(pixel, c)) for c in allowed)
        assert near < 6000, f"{pixel} is not derived from any colour in the pattern"


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
