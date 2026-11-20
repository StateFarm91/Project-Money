"""S1 fix (Main's verdict 6958883678): size families, requested sizes, no default panels.

* H1: the blanket family band spans the Craft Yarn Council table (preemie to king), and a named
  class (baby, throw, queen, lumbar...) is held to its own band. Launch-0's
  `nordic-forest-mosaic-throw-baby` (57.6 x 67.8 cm) certifies, and every catalogue product
  certifies (the non-regression test Main asked for).
* H2: a size the title asks for -- a class word or stated dimensions -- is drafted at that size
  when the family is made in it, refused by name when it is not (at intake and at draft), and
  the certificate holds the twin to the size the title and the listing title state.
* M1: an object with no size band and no correct template (lovey, bib, rug, bath mat,
  tablecloth, hot pad, doily, pouf, or a category template with no object behind it) is refused,
  never drafted as the default panel; a burp cloth and a lumbar pillow get their own sizes.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_s1_fix_size_families.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.creative import fallback_constructions as FC  # noqa: E402
from brambleloop.creative import size_truth as ST  # noqa: E402
from brambleloop.gates import certificate as C  # noqa: E402
from brambleloop.gates.policy import ListingDraft  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402
from brambleloop.radar.opportunity import ConceptSeed  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402


class _Twin:
    def __init__(self, w, h):
        self.width_cm, self.height_cm = w, h


class _Cir:
    def __init__(self, title):
        self.title = title


def _seed(category, title):
    return ConceptSeed(slug="size-fix-" + category, title=title, category=category,
                       risk_class="A", price_cad=6.0, maker_hours=(2.0, 6.0), design_hours=3.0,
                       whitespace=0.5, rationale="fixture concept for the S1 size fix",
                       origin="test")


def _drafted(category, title):
    """Plan, geometry, CIR and twin through the real fallback route; None when refused."""
    route = FC.plan(category=category, title=title)
    if route["family"] == FC.REFUSED:
        return route, None, None
    g = pipeline.concept_geometry(_seed(category, title))
    cir = pipeline.concept_to_cir(pipeline.Concept(
        slug="size-fix", title=title, category=category,
        stitch_repeat=[tuple(x) for x in g["stitch_repeat"]], width_stitches=g["width_stitches"],
        rows=g["rows"], colors=g["colors"]))
    if route["family"] == FC.PANEL_PAIR:
        cir = FC.panel_pair(cir)
    result = compile_cir(cir)
    assert result.ok, (title, result.errors)
    return route, cir, build_twin(cir, result)


def _size_codes(cir, twin):
    return [f.code for f in C.object_size_findings(cir, twin)]


# ---- H1: per-family bands; the catalogue certifies ------------------------------------------


def test_every_catalogue_product_certifies():
    assert l0.BUILDERS, "no catalogue builders: the loop would prove nothing"
    refused = {}
    for key in sorted(l0.BUILDERS):
        cert = C.certify(l0.cir_for(key))
        if not cert.granted:
            refused[key] = [f"{f.code}: {f.message[:120]}" for f in cert.findings
                            if str(f.severity) == C.ERROR]
    assert not refused, refused


def test_the_launch0_baby_blanket_is_inside_the_baby_class_at_its_real_size():
    cir = l0.cir_for("nordic_forest_baby")
    result = compile_cir(cir)
    twin = build_twin(cir, result)
    assert (twin.width_cm, twin.height_cm) == (57.6, 67.8), (twin.width_cm, twin.height_cm)
    assert C.object_size_findings(cir, twin) == []
    assert C.certify(cir).granted


def test_a_named_blanket_class_holds_the_twin_to_its_own_band():
    # A "Baby" blanket at a queen's size, and a "Queen Size" blanket at a throw's, are refused.
    assert "OBJECT_SIZE_NOT_AS_TITLED" in _size_codes(_Cir("Linen Baby Blanket"),
                                                      _Twin(229.0, 254.0))
    assert "OBJECT_SIZE_NOT_AS_TITLED" in _size_codes(_Cir("Queen Size Linen Blanket"),
                                                      _Twin(128.0, 152.0))
    # Each class's own default passes its own band.
    for name, c in ST.BLANKET_CLASSES.items():
        word = c["words"][0]
        assert _size_codes(_Cir(f"Linen {word.title()} Blanket"), _Twin(*c["default"])) == [], name
    # The family band spans preemie to king; a 40 cm square is no blanket.
    assert _size_codes(_Cir("Linen Blanket"), _Twin(46.0, 61.0)) == []
    assert _size_codes(_Cir("Linen Blanket"), _Twin(254.0, 274.0)) == []
    assert "OBJECT_SIZE_OUT_OF_BAND" in _size_codes(_Cir("Tiny Blanket"), _Twin(40.0, 40.0))


def test_crochet_stitch_and_moon_words_are_not_bed_sizes():
    for title in ("Single Crochet Throw", "Double Crochet Blanket", "Full Moon Blanket",
                  "Queen Anne's Lace Throw", "Twin Peaks Throw"):
        assert ST.named_classes("blanket", title).keys() <= {"throw"}, title


# ---- H2: requested sizes are drafted, or refused, and certified against the claim ------------


def test_main_h2_examples_are_drafted_at_the_asked_size_or_refused():
    drafted = {
        ("blanket", "Queen Size Linen Blanket"): (229.0, 254.0),
        ("blanket", "Linen Blanket 200 x 220 cm"): (200.0, 220.0),
        ("pillow", "Pillow Cover 26 x 26 inch"): (66.0, 66.0),
        ("wall_decor", "Large Tapestry 100 x 150 cm"): (100.0, 150.0),
    }
    for (category, title), (short, long_) in drafted.items():
        route, cir, twin = _drafted(category, title)
        assert twin is not None, (title, route)
        got = sorted((twin.width_cm, twin.height_cm))
        assert ST._met(short, got[0]) and ST._met(long_, got[1]), (title, got)
        assert _size_codes(cir, twin) == [], (title, got, C.object_size_findings(cir, twin))
    # One figure on a square object is its side.
    route, cir, twin = _drafted("pillow", "Linen Pillow Cover 18 inch")
    got = sorted((twin.width_cm, twin.height_cm))
    assert ST._met(45.7, got[0]) and ST._met(45.7, got[1]), got
    assert _size_codes(cir, twin) == []
    route, _, twin = _drafted("runner", "Short Runner 40 cm")
    assert twin is None and route["family"] == FC.REFUSED
    assert "40 cm long" in route["why"], route


def test_a_template_sized_draft_under_a_requested_size_is_refused_by_the_certificate():
    # The old behaviour (Main's probe): the request silently drafted at the template's size.
    for title, size in (("Queen Size Linen Blanket", (128.0, 152.0)),
                        ("Linen Blanket 200 x 220 cm", (128.0, 152.0)),
                        ("Pillow Cover 26 x 26 inch", (42.0, 42.0)),
                        ("Large Tapestry 100 x 150 cm", (42.0, 60.0))):
        assert "OBJECT_SIZE_NOT_AS_TITLED" in _size_codes(_Cir(title), _Twin(*size)), title


def test_the_listing_title_is_a_size_claim_too():
    cir = l0.cir_for("nordic_forest_baby")
    good = ListingDraft(title="Nordic Forest Baby Blanket 58 x 68 cm", description="d")
    bad = ListingDraft(title="Nordic Forest Queen Size Blanket", description="d")
    codes = lambda lst: [f.code for f in C.certify(cir, listing=lst).findings]  # noqa: E731
    assert "LISTING_SIZE_NOT_AS_TITLED" not in codes(good)
    assert "LISTING_SIZE_NOT_AS_TITLED" in codes(bad)


def test_stated_dimensions_parse_cm_inches_and_one_figure():
    assert ST.stated_dimensions("Linen Blanket 200 x 220 cm") == (200.0, 220.0)
    assert ST.stated_dimensions("Pillow Cover 26 x 26 inch") == (66.0, 66.0)
    assert ST.stated_dimensions('Cushion 18" x 12"') == (30.5, 45.7)
    assert ST.stated_dimensions("Table Runner 72 in") == (182.9,)
    assert ST.stated_dimensions("Short Runner 40 cm") == (40.0,)
    assert ST.stated_dimensions("Linen Ridge Throw") == ()


def test_intake_refuses_a_size_the_family_cannot_make():
    import test_w5_concept_intake as W
    from brambleloop.radar import intake

    db = W._db()
    ok = intake.validate(db, W._proposal(), {"reasons": []}, source_ref="t")
    assert not [r for r in ok["reasons"] if r.startswith("size:")], ok["reasons"]
    bad = intake.validate(db, W._proposal(title="Tide Line Short Table Runner 40 cm"),
                          {"reasons": []}, source_ref="t")
    assert any(r.startswith("size:") and "40 cm long" in r for r in bad["reasons"]), bad
    # A basket proposal is not a flat object: size truth does not speak for it.
    assert not ST.applies("basket", "Market Basket")


# ---- M1: no band, no template -> refused; burp cloth and lumbar get their own sizes ----------


def test_objects_without_a_band_and_template_are_refused_not_drafted_as_a_panel():
    for category, title in (("baby", "Baby Lovey"), ("baby", "Baby Bib"),
                            ("placemat", "Linen Hot Pad"), ("placemat", "Cotton Pot Holder"),
                            ("runner", "Linen Rug"), ("placemat", "Linen Bath Mat"),
                            ("runner", "Linen Tablecloth"), ("placemat", "Lace Doily"),
                            ("pillow", "Linen Pouf"), ("baby", "Baby Nursery Panel"),
                            ("seasonal_decor", "Autumn Panel"), ("unlisted", "Linen Panel")):
        route = FC.plan(category=category, title=title)
        # Refused by name (some, such as a pot "holder", by the shaped-object rule first).
        assert route["family"] == FC.REFUSED, (title, route)
        assert route["why"], (title, route)
    # The band-less ones are refused for that reason, not by accident of another rule.
    # ENG-PLUSH: a lovey now has an engine (creative.baby); "Baby Lovey" is still refused
    # above, by the lovey's head (no bear or bunny is named), not for a missing size band.
    assert "head" in FC.plan(category="baby", title="Baby Lovey")["why"]
    for title in ("Linen Hot Pad", "Linen Tablecloth", "Baby Nursery Panel"):
        cat = "baby" if title.startswith("Baby") else "placemat"
        assert "size band" in FC.plan(category=cat, title=title)["needs"], title


def test_a_burp_cloth_and_a_lumbar_pillow_are_drafted_at_their_own_sizes():
    route, cir, twin = _drafted("baby", "Baby Burp Cloth")
    got = sorted((twin.width_cm, twin.height_cm))
    assert ST._met(25.0, got[0]) and ST._met(50.0, got[1]), got
    route, cir, twin = _drafted("pillow", "Linen Lumbar Pillow")
    got = sorted((twin.width_cm, twin.height_cm))
    assert ST._met(30.0, got[0]) and ST._met(50.0, got[1]), got
    assert _size_codes(cir, twin) == []
    # A square under the lumbar name is refused by the certificate.
    assert "OBJECT_SIZE_NOT_AS_TITLED" in _size_codes(_Cir("Linen Lumbar Pillow"),
                                                      _Twin(42.0, 42.0))


def test_a_throw_pillow_is_a_pillow_not_a_throw():
    assert ST.object_of("pillow", "Linen Throw Pillow") == "pillow"
    route, cir, twin = _drafted("pillow", "Linen Throw Pillow")
    assert max(twin.width_cm, twin.height_cm) < 68.0, (twin.width_cm, twin.height_cm)
    assert _size_codes(cir, twin) == []


def test_a_relative_size_word_without_dimensions_is_refused():
    for title in ("Large Linen Placemat", "Mini Linen Runner", "Oversized Linen Scarf"):
        cat = title.split()[-1].lower()
        route = FC.plan(category=cat, title=title)
        assert route["family"] == FC.REFUSED and "relative" in route["why"], (title, route)


def test_the_radar_pool_drafts_exactly_what_it_drafted_before():
    # The template already makes each class's default: no pool concept's geometry moves, so no
    # release fingerprint drafted from it changes.
    from brambleloop.radar.opportunity import POOL

    for s in POOL:
        g = pipeline.concept_geometry(s)
        e = pipeline._geometry_entry(s.category, s.title)
        assert g["rows"] == e["rows"], s.slug


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:600])
                import traceback

                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
