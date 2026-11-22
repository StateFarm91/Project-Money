"""S1 Product Truth, second review of e490fc6f: every size the title states is bound or refused.

* S1F-H1: "King Size Ridge Throw", "Linen Lumbar Pillow 12 x 24", "Linen Blanket 200 x 220",
  "Linen Pillow Cover 26x26" and "Queen Linen Blanket" drafted at the template's size and
  certified. Every size-bearing token in a title (a class word, a relative size word, stated
  dimensions) is now bound to the drafted twin and checked; a token the parser cannot bind is a
  refusal with a reason, at draft and at certification. Unitless dimensions are read by one
  recorded rule (D-S1-UNITLESS-DIMS): the unit is inferred only when exactly one of cm / inches
  puts the size inside the object's cited band; otherwise refused.
* S1F-M1: relative size words follow one rule (D-S1-RELATIVE-SIZE): bound by stated dimensions,
  or by a defined, cited size family for that object (only the large blanket has one), or
  refused -- for every object.
* LOWs: every catalogue CIR certifies (not just Launch-0); the pet-mat, burp-cloth and tapestry
  bands fire at certification; "2 in 1" is not 2 inches; "Skinny Scarf 10 cm" is refused as a
  width, not as a length.

Every case is measured through the real path: plan -> geometry -> builder -> compile -> twin ->
certify.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_s1_product_truth_2.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brambleloop.creative import fallback_constructions as FC  # noqa: E402
from brambleloop.creative import size_truth as ST  # noqa: E402
from brambleloop.gates import certificate as C  # noqa: E402
from brambleloop.gates.policy import ListingDraft  # noqa: E402

import test_s1_fix_size_families as F  # noqa: E402

SIZE_CODES = {"OBJECT_SIZE_NOT_AS_TITLED", "OBJECT_SIZE_OUT_OF_BAND", "OBJECT_SIZE_UNBOUND",
              "LISTING_SIZE_NOT_AS_TITLED"}


def _size_errors(cir):
    cert = C.certify(cir)
    return sorted({f.code for f in cert.findings
                   if str(f.severity) == C.ERROR and f.code in SIZE_CODES})


def _drafted_at(category, title, short, long_):
    """The real path drafts `title` at (short, long) and the certificate finds no size error."""
    route, cir, twin = F._drafted(category, title)
    assert twin is not None, (title, route)
    got = sorted((twin.width_cm, twin.height_cm))
    assert ST._met(short, got[0]) and ST._met(long_, got[1]), (title, got, (short, long_))
    assert _size_errors(cir) == [], (title, got, C.object_size_findings(cir, twin))
    return got


def _refused_at_draft(category, title, *words):
    route = FC.plan(category=category, title=title)
    assert route["family"] == FC.REFUSED, (title, route)
    for w in words:
        assert w in route["why"], (title, w, route["why"])
    return route["why"]


# ---- S1F-H1 -------------------------------------------------------------------------------


def test_h1_two_class_words_are_both_bound_or_refused():
    # King and throw have no size in common: refused, naming both, never drafted as a throw.
    _refused_at_draft("blanket", "King Size Ridge Throw", "king", "throw")
    # The template-size twin under that title is refused by the certificate for "king".
    codes = F._size_codes(F._Cir("King Size Ridge Throw"), F._Twin(128.0, 152.2))
    assert "OBJECT_SIZE_NOT_AS_TITLED" in codes, codes
    # Classes that overlap are drafted inside every one of them.
    got = _drafted_at("blanket", "Linen Lap Throw", 91.0, 122.0)
    assert got


def test_h1_bare_bed_size_words_are_size_classes():
    for title, size in (("Queen Linen Blanket", (229.0, 254.0)),
                        ("King Linen Blanket", (254.0, 274.0)),
                        ("Twin Linen Blanket", (168.0, 229.0)),
                        ("Full Linen Blanket", (203.0, 229.0))):
        _drafted_at("blanket", title, *size)
        assert "OBJECT_SIZE_NOT_AS_TITLED" in F._size_codes(F._Cir(title),
                                                            F._Twin(128.0, 152.2)), title
    # Crochet-stitch, moon and name words stay non-sizes.
    for title in ("Single Crochet Throw", "Double Crochet Blanket", "Full Moon Blanket",
                  "Queen Anne's Lace Throw", "Twin Peaks Throw", "King's Cross Throw"):
        assert set(ST.named_classes("blanket", title)) <= {"throw"}, title


def test_h1_unitless_dimensions_are_read_by_the_recorded_rule_or_refused():
    # Exactly one unit puts the size in the band: drafted at it.
    _drafted_at("pillow", "Linen Lumbar Pillow 12 x 24", 30.5, 61.0)
    _drafted_at("blanket", "Linen Blanket 200 x 220", 200.0, 220.0)
    _drafted_at("pillow", "Linen Pillow Cover 26x26", 66.0, 66.0)
    # Both units fit (50 x 60 cm is a preemie, 50 x 60 in a throw): refused, not guessed.
    why = _refused_at_draft("blanket", "Linen Blanket 50 x 60", "unit")
    assert "cm" in why and "in" in why, why
    # Neither fits: refused.
    _refused_at_draft("pillow", "Linen Pillow 5 x 5", "unit")
    # The certificate refuses an unbindable title rather than passing it.
    codes = F._size_codes(F._Cir("Linen Blanket 50 x 60"), F._Twin(128.0, 152.2))
    assert "OBJECT_SIZE_UNBOUND" in codes, codes
    # And holds the inferred unit: 12 x 24 on a template-size lumbar is refused.
    codes = F._size_codes(F._Cir("Linen Lumbar Pillow 12 x 24"), F._Twin(28.8, 49.6))
    assert "OBJECT_SIZE_NOT_AS_TITLED" in codes, codes


def test_h1_a_size_the_parser_cannot_bind_is_refused():
    # Two different sizes in one title, three dimensions, a dangling figure.
    for category, title in (("pillow", "Linen Pillow 12 x 24 in and 18 x 18 in"),
                            ("pillow", "Linen Pillow 40 x 40 x 10 cm"),
                            ("blanket", "Linen Blanket 200 x")):
        why = _refused_at_draft(category, title)
        assert why, title
        codes = F._size_codes(F._Cir(title), F._Twin(42.0, 42.0))
        assert "OBJECT_SIZE_UNBOUND" in codes, (title, codes)
    # The same size in two units is one size.
    _drafted_at("pillow", "Linen Pillow Cover 18 x 18 in (46 x 46 cm)", 45.7, 45.7)


def test_h1_the_listing_title_is_bound_the_same_way():
    cir = F.l0.cir_for("nordic_forest_baby")
    for title in ("Nordic Forest Queen Blanket", "Nordic Forest Blanket 50 x 60",
                  "Nordic Forest Large Blanket"):
        codes = [f.code for f in C.certify(cir, listing=ListingDraft(
            title=title, description="d")).findings]
        assert "LISTING_SIZE_NOT_AS_TITLED" in codes, (title, codes)


# ---- S1F-M1 -------------------------------------------------------------------------------


def test_m1_relative_size_words_follow_one_rule():
    # A relative word with a defined, cited family (the large blanket) is drafted in it.
    lg = ST.BLANKET_CLASSES["large"]
    for title in ("Large Linen Throw", "Oversized Chunky Throw", "Large Linen Blanket"):
        route, cir, twin = F._drafted("blanket", title)
        assert twin is not None, (title, route)
        short, long_ = sorted((twin.width_cm, twin.height_cm))
        assert lg["short"][0] <= short <= lg["short"][1], (title, short)
        assert lg["long"][0] <= long_ <= lg["long"][1], (title, long_)
        assert _size_errors(cir) == [], (title, C.object_size_findings(cir, twin))
        # The standard throw under the name is refused.
        assert "OBJECT_SIZE_NOT_AS_TITLED" in F._size_codes(F._Cir(title),
                                                            F._Twin(128.0, 152.2)), title
    # With no family for the object and no dimensions: refused at draft and at certification.
    for category, title, size in (("scarf", "Extra Long Linen Scarf", (19.2, 152.2)),
                                  ("scarf", "Long Linen Scarf", (19.2, 152.2)),
                                  ("scarf", "Skinny Linen Scarf", (19.2, 152.2)),
                                  ("scarf", "Petite Linen Scarf", (19.2, 152.2)),
                                  ("pet", "Large Dog Mat", (40.8, 51.2)),
                                  ("placemat", "Mini Placemat", (30.0, 45.0)),
                                  ("pillow", "Large Linen Pillow", (41.6, 41.7))):
        _refused_at_draft(category, title, "relative")
        codes = F._size_codes(F._Cir(title), F._Twin(*size))
        assert "OBJECT_SIZE_UNBOUND" in codes, (title, codes)
    # A relative word is bound by stated dimensions.
    _drafted_at("wall_decor", "Large Tapestry 100 x 150 cm", 100.0, 150.0)
    _drafted_at("scarf", "Long Linen Scarf 20 x 200 cm", 20.0, 200.0)


# ---- LOWs ---------------------------------------------------------------------------------


def _catalogue():
    """Every catalogue CIR: Launch-0 and proposed builders, the flat builder catalogue, every
    Nordic Forest size, the moment candidates, the vessels and every graded garment."""
    from brambleloop.products import builder as B
    from brambleloop.products import garments as G
    from brambleloop.products import launch0 as l0
    from brambleloop.products import moment_candidates as MC
    from brambleloop.products import nordic_forest as NF
    from brambleloop.products import vessels as V

    cirs = {}
    for k in list(l0.BUILDERS) + list(l0.PROPOSED_BUILDERS):
        c = l0.cir_for(k)
        cirs[c.slug] = c
    for s in B.CATALOGUE:
        c = B.for_slug(s)
        cirs[c.slug] = c
    for c in NF.all_sizes().values():
        cirs[c.slug] = c
    for fn in ("reading_nook_cable_wrap", "mothers_day_heart_tea_cosy",
               "snowfall_advent_garland", "housewarming_key_basket", "heart_row_ring_pillow",
               "spring_garden_kneeler"):
        c = getattr(MC, fn)()
        cirs[c.slug] = c
    c = V.build()
    cirs[c.slug] = c
    cirs.update(G.every_graded_cir())
    return cirs


# Catalogue CIRs refused for a recorded reason that is not this change's: the ring pillow by
# the ring band (D-S1-SIZE-FAMILIES), the wrap by an uncalibrated primitive, the kneeler by its
# required physical test. Each must be refused by exactly those codes and nothing else.
# D-OWNER-NO-SAMPLE-SIZING (2026-11-22): the wrap's cable and the kneeler's Class C now size
# from standard gauge, so only the ring pillow's size band refuses.
KNOWN_NON_SIZE_REFUSALS = {
    "heart-row-ring-pillow": {"OBJECT_SIZE_OUT_OF_BAND"},
}


def test_low_every_catalogue_cir_certifies():
    cirs = _catalogue()
    assert len(cirs) >= 41, len(cirs)
    wrong = {}
    for slug, cir in sorted(cirs.items()):
        cert = C.certify(cir)
        errs = {f.code for f in cert.findings if str(f.severity) == C.ERROR}
        expected = KNOWN_NON_SIZE_REFUSALS.get(slug, set())
        if errs != expected or cert.granted != (not expected):
            wrong[slug] = (cir.title, sorted(errs))
    assert not wrong, wrong


def test_low_pet_mat_burp_cloth_and_tapestry_bands_fire_at_certification():
    for title, size in (("Linen Pet Mat", (12.0, 12.0)), ("Linen Dog Mat", (150.0, 200.0)),
                        ("Baby Burp Cloth", (60.0, 90.0)), ("Linen Tapestry", (5.0, 300.0)),
                        ("Mountain Tapestry", (200.0, 300.0))):
        codes = F._size_codes(F._Cir(title), F._Twin(*size))
        assert "OBJECT_SIZE_OUT_OF_BAND" in codes, (title, codes)
    # In band: no finding. A tapestry-crochet blanket is a blanket, not a wall hanging.
    for title, size in (("Linen Pet Mat", (40.8, 51.2)), ("Baby Burp Cloth", (25.4, 51.2)),
                        ("Linen Tapestry", (41.6, 59.8)),
                        ("Tapestry Crochet Throw", (128.0, 152.2))):
        assert F._size_codes(F._Cir(title), F._Twin(*size)) == [], title


def test_low_two_in_one_is_not_a_size():
    assert ST.stated_dimensions("Linen Throw 2 in 1") == ()
    _drafted_at("blanket", "Linen Throw 2 in 1", 128.0, 152.2)
    # An inch figure is still read.
    assert ST.stated_dimensions("Linen Pillow 18 in") == (45.7,)


def test_low_skinny_scarf_10_cm_is_refused_as_a_width():
    why = _refused_at_draft("scarf", "Skinny Scarf 10 cm", "10 cm wide")
    assert "long" not in why.split("wide")[0], why
    # "Short Runner 40 cm" stays refused as a length.
    _refused_at_draft("runner", "Short Runner 40 cm", "40 cm long")


def test_kept_cases_stay_fixed():
    for category, title, size in (("blanket", "Queen Size Linen Blanket", (229.0, 254.0)),
                                  ("blanket", "Linen Blanket 200 x 220 cm", (200.0, 220.0)),
                                  ("pillow", "Pillow Cover 26 x 26 inch", (66.0, 66.0)),
                                  ("baby", "Baby Burp Cloth", (25.0, 50.0)),
                                  ("pillow", "Linen Lumbar Pillow", (30.0, 50.0))):
        _drafted_at(category, title, *size)
    for category, title in (("baby", "Baby Lovey"), ("baby", "Baby Bib"),
                            ("runner", "Linen Rug"), ("placemat", "Linen Bath Mat"),
                            ("runner", "Linen Tablecloth"), ("placemat", "Linen Hot Pad"),
                            ("placemat", "Lace Doily"), ("pillow", "Linen Pouf")):
        _refused_at_draft(category, title)


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
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
