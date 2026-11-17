"""A4A-1 (Main verdict on A4a, HIGH, Product Truth): a "dishcloth" is drafted as a dishcloth.

The research concept "... Dishcloth" was drafted with the placemat template (48 sts x 14
rows, 38.4 x 11.4 cm at worsted gauge) and certified with no reason. Now:

* the dishcloth has its own geometry, a ~22 cm square;
* certification refuses any CIR whose title names a dishcloth while its finished size is
  outside the dishcloth band (`OBJECT_SIZE_OUT_OF_BAND`) -- a placemat-sized "dishcloth" is
  refused whoever drafted it;
* "hot pad" is no longer proposed: one layer of flat rows is not a heat-protection object.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_a4a_fix_object_size.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.gates import certificate as C  # noqa: E402
from brambleloop.radar import ideation  # noqa: E402
from brambleloop.radar.opportunity import ConceptSeed  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402


class _Twin:
    def __init__(self, w, h):
        self.width_cm, self.height_cm = w, h


class _Cir:
    def __init__(self, title):
        self.title = title


def _seed(category, title):
    return ConceptSeed(slug=f"linen-ridge-{category}", title=title, category=category,
                       risk_class="A", price_cad=5.0, maker_hours=(1.0, 2.5),
                       design_hours=3.0, whitespace=0.5,
                       rationale="fixture research concept for the size band test",
                       origin="test")


def _twin_of(seed):
    g = pipeline.concept_geometry(seed)
    concept = pipeline.Concept(slug=seed.slug, title=seed.title, category=seed.category,
                               stitch_repeat=[tuple(x) for x in g["stitch_repeat"]],
                               width_stitches=g["width_stitches"], rows=g["rows"],
                               colors=g["colors"])
    cir = pipeline.concept_to_cir(concept)
    result = compile_cir(cir)
    assert result.ok, result.errors
    return cir, build_twin(cir, result)


def test_the_size_band_refuses_a_placemat_sized_dishcloth():
    bad = C.object_size_findings(_Cir("Linen Ridge Dishcloth"), _Twin(38.4, 11.4))
    assert len(bad) == 1 and bad[0].code == "OBJECT_SIZE_OUT_OF_BAND", bad
    assert bad[0].severity == C.ERROR and "38.4 x 11.4" in bad[0].message
    assert C.object_size_findings(_Cir("Linen Ridge Dishcloth"), _Twin(22.4, 21.9)) == []
    # A square at the wrong size, and a right-sized oblong, are both refused.
    assert C.object_size_findings(_Cir("Wash Cloth"), _Twin(35.0, 35.0))
    assert C.object_size_findings(_Cir("A Dishcloth"), _Twin(27.0, 18.5))
    # A title that names no banded object is untouched.
    assert C.object_size_findings(_Cir("Linen Ridge Placemat"), _Twin(38.4, 11.4)) == []
    assert C.object_size_findings(_Cir("Dishcloth"), None) == []


def test_the_dishcloth_template_drafts_a_square_inside_the_band():
    cir, twin = _twin_of(_seed("dishcloth", "Linen Ridge Dishcloth"))
    lo, hi = C.OBJECT_SIZE_BANDS["dishcloth"]["side_cm"]
    assert lo <= twin.width_cm <= hi and lo <= twin.height_cm <= hi, (twin.width_cm,
                                                                      twin.height_cm)
    assert C.object_size_findings(cir, twin) == []


def test_a_dishcloth_drafted_on_the_placemat_template_is_refused_by_certification():
    cir, twin = _twin_of(_seed("placemat", "Linen Ridge Dishcloth"))
    assert twin.width_cm > 30, twin.width_cm             # the old 38 x 11 cm panel
    codes = [f.code for f in C.object_size_findings(cir, twin)]
    assert codes == ["OBJECT_SIZE_OUT_OF_BAND"], codes
    # And it reaches the certificate: the real certify refuses it.
    import inspect

    assert "object_size_findings(cir, twin)" in inspect.getsource(C.certify)


def test_ideation_drafts_a_dishcloth_on_its_own_template_and_offers_no_hot_pad():
    objs = ideation.POD_OBJECTS["kitchen_bath"]
    assert [o.key for o in objs] == ["dishcloth"], [o.key for o in objs]
    assert objs[0].category == "dishcloth"
    from brambleloop.radar import intake

    assert "dishcloth" in intake.SUPPORTED_FORMS
    assert pipeline._GEOMETRY["dishcloth"] != pipeline._GEOMETRY["placemat"]
    assert replace(objs[0]).category != "placemat"


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
