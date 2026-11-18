"""S1 Product Truth: the fallback drafts the object its title names, at that object's size.

Main's S1 audit of every fallback geometry family (#28, 6953884261) found:
* A "Baby Blanket" took the mixed `baby` template (80 x 18 cm) and could only be refused.
* "Wedding Ring Cushion" took the default 32 x 10 cm strip, paired, and was then held to the
  28-66 cm pillow band, so even a correctly sized ring cushion would have been refused.
* A pet mat drafted as a 48 x 15 cm strip and a wall hanging as a 35 x 14 cm strip.
* "Round Placemat", "Infinity Scarf" and "Ribbed Cowl" drafted as flat rectangles: an outline
  and a loop the pattern does not make.

Now the title-named object picks the size where the category cannot; a ring cushion has its
own band; and a flat rectangle under a round, oval or loop name is refused by name.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_s1_product_truth.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.reverse import compare  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.creative import fallback_constructions as FC  # noqa: E402
from brambleloop.gates import certificate as C  # noqa: E402
from brambleloop.radar.opportunity import POOL, ConceptSeed  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402


class _Twin:
    def __init__(self, w, h):
        self.width_cm, self.height_cm = w, h


class _Cir:
    def __init__(self, title):
        self.title = title


def _drafted(category, title):
    """The CIR the fallback drafts for this concept, through its real route."""
    seed = ConceptSeed(slug="linen-ridge-" + category, title=title, category=category,
                       risk_class="A", price_cad=6.0, maker_hours=(2.0, 6.0),
                       design_hours=3.0, whitespace=0.5,
                       rationale="fixture concept for the S1 product truth audit", origin="test")
    route = FC.plan(category=category, title=title, slug=seed.slug, rationale=seed.rationale)
    g = pipeline.concept_geometry(seed)
    concept = pipeline.Concept(slug=seed.slug, title=title, category=category,
                               stitch_repeat=[tuple(x) for x in g["stitch_repeat"]],
                               width_stitches=g["width_stitches"], rows=g["rows"],
                               colors=g["colors"])
    cir = pipeline.concept_to_cir(concept)
    if route["family"] == FC.PANEL_PAIR:
        cir = FC.panel_pair(cir)
    result = compile_cir(cir)
    assert result.ok, (title, result.errors)
    return route, cir, result, build_twin(cir, result)


def test_a_baby_blanket_is_drafted_at_a_baby_blanket_size_and_certifies():
    _, cir, _, twin = _drafted("baby", "Linen Ridge Baby Blanket")
    assert 70 <= min(twin.width_cm, twin.height_cm) and max(twin.width_cm, twin.height_cm) <= 100, (
        twin.width_cm, twin.height_cm)
    assert C.object_size_findings(cir, twin) == []
    # The rest of the mixed category keeps its own template.
    seed = ConceptSeed(slug="x", title="Linen Ridge Baby Bib", category="baby", risk_class="A",
                       price_cad=6.0, maker_hours=(2.0, 6.0), design_hours=3.0, whitespace=0.5,
                       rationale="fixture concept for the S1 product truth audit", origin="test")
    assert pipeline.concept_geometry(seed)["rows"] == pipeline._GEOMETRY["baby"]["rows"]


def test_a_ring_cushion_is_its_own_size_and_band():
    route, cir, _, twin = _drafted("wedding", "Wedding Ring Cushion")
    assert route["family"] == FC.PANEL_PAIR
    assert 12 <= twin.width_cm <= 25 and 12 <= twin.height_cm <= 25, (twin.width_cm,
                                                                      twin.height_cm)
    assert C.object_size_findings(cir, twin) == []
    # A ring cushion is not held to the pillow band, and the old strip is refused by its own.
    assert C.object_size_findings(_Cir("Ring Bearer Pillow"), _Twin(18.0, 18.0)) == []
    assert [f.code for f in C.object_size_findings(_Cir("Wedding Ring Cushion"),
                                                   _Twin(32.0, 9.8))] == ["OBJECT_SIZE_OUT_OF_BAND"]
    assert C.object_size_findings(_Cir("Wedding Ring Cushion"), _Twin(45.0, 45.0))
    # A plain pillow is still held to the pillow band.
    assert C.object_size_findings(_Cir("Linen Pillow Cover"), _Twin(19.0, 19.0))


def test_pet_mat_and_wall_hanging_templates_are_not_strips():
    _, _, _, mat = _drafted("pet", "Linen Ridge Pet Mat")
    assert 40 <= mat.width_cm <= 60 and 40 <= mat.height_cm <= 55, (mat.width_cm, mat.height_cm)
    _, _, _, art = _drafted("wall_decor", "Linen Ridge Wall Art")
    assert 35 <= art.width_cm <= 45 and 55 <= art.height_cm <= 65, (art.width_cm, art.height_cm)


def test_an_outline_or_loop_a_rectangle_does_not_have_is_refused_by_name():
    for category, title in (("placemat", "Round Placemat"), ("placemat", "Oval Linen Placemats"),
                            ("scarf", "Infinity Scarf"), ("scarf", "Ribbed Cowl"),
                            ("pillow", "Round Velvet Cushion"), ("scarf", "Chunky Snood")):
        route = FC.plan(category=category, title=title, slug="x")
        assert route["family"] == FC.REFUSED, (title, route)
    # A plain one, and "year-round", are not outline claims.
    for category, title in (("placemat", "Linen Placemat"), ("dishcloth", "Year-Round Dishcloth"),
                            ("scarf", "Linen Ridge Scarf")):
        assert FC.plan(category=category, title=title, slug="x")["family"] == FC.FLAT_PANEL, title


def test_every_template_and_title_route_writes_the_size_its_twin_has_and_reverse_compiles():
    titles = [(c, f"Linen Ridge {c.replace('_', ' ').title()}") for c in pipeline._GEOMETRY]
    titles += [("baby", "Linen Ridge Baby Blanket"), ("wedding", "Wedding Ring Cushion")]
    assert len(titles) > 2, titles
    for category, title in titles:
        _, cir, result, twin = _drafted(category, title)
        text = write_pattern(cir, result, width_cm=twin.width_cm, height_cm=twin.height_cm)
        assert compare(cir, text) == [], (title, compare(cir, text))
        stated = re.findall(r"Block the finished piece to (\d+) x (\d+) cm", text)
        # A flat piece states the size it blocks to; an assembled pair states none. Either
        # way no size other than the twin's is written.
        assert stated in ([(f"{twin.width_cm:.0f}", f"{twin.height_cm:.0f}")], []), (title,
                                                                                     stated)
        assert stated or len(cir.components) > 1, title


def test_no_radar_pool_seed_drafts_a_size_its_title_refuses():
    from brambleloop.gates.first_customer import _family_hits  # noqa: F401

    for s in POOL:
        if pipeline._engineered_cir(s.slug) is not None:
            continue
        route = FC.plan(category=s.category, title=s.title, is_bundle=bool(s.is_bundle),
                        slug=s.slug, rationale=s.rationale)
        if route["family"] not in (FC.FLAT_PANEL, FC.PANEL_PAIR):
            continue
        _, cir, _, twin = _drafted(s.category, s.title)
        assert C.object_size_findings(cir, twin) == [], (s.slug, twin.width_cm, twin.height_cm)


if __name__ == "__main__":
    import traceback

    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception:  # noqa: BLE001
                fails += 1
                print("FAIL", name)
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
