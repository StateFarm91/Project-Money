"""Mosaic and graphghan template size truth: both plain templates draft a throw.

They were 160 x 24 and 140 x 24 stitches: 128 x 20 and 112 x 17 cm strips, which the blanket
band (`OBJECT_SIZE_OUT_OF_BAND`) refused, so every research or radar concept in these
categories failed certification. The catalogue's mosaic and graphghan seeds are engineered
from their own charts and never reach these templates.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_colourwork_template_size_truth.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.gates import certificate as C  # noqa: E402
from brambleloop.radar.opportunity import POOL, ConceptSeed  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402

CASES = {"mosaic_blanket": "Linen Ridge Mosaic Throw", "graphghan": "Linen Ridge Graphghan"}


def _twin_of(category, title):
    seed = ConceptSeed(slug=f"linen-ridge-{category}", title=title, category=category,
                       risk_class="A", price_cad=9.0, maker_hours=(20.0, 40.0),
                       design_hours=6.0, whitespace=0.5,
                       rationale="fixture concept for the colourwork size band", origin="test")
    g = pipeline.concept_geometry(seed)
    concept = pipeline.Concept(slug=seed.slug, title=seed.title, category=seed.category,
                               stitch_repeat=[tuple(x) for x in g["stitch_repeat"]],
                               width_stitches=g["width_stitches"], rows=g["rows"],
                               colors=g["colors"])
    cir = pipeline.concept_to_cir(concept)
    result = compile_cir(cir)
    assert result.ok, (category, result.errors)
    return cir, build_twin(cir, result)


def test_both_templates_draft_a_throw_inside_the_blanket_band():
    for category, title in CASES.items():
        cir, twin = _twin_of(category, title)
        assert twin.height_cm > 120 and twin.width_cm > 100, (category, twin.width_cm,
                                                              twin.height_cm)
        assert C.object_size_findings(cir, twin) == [], (category, twin.width_cm,
                                                         twin.height_cm)


def test_the_catalogue_seeds_in_these_categories_are_engineered_not_templated():
    seeds = [s for s in POOL if s.category in CASES]
    assert seeds
    for s in seeds:
        assert pipeline._engineered_cir(s.slug) is not None, s.slug


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
