"""Flat-rows size truth: every plain flat-rows template drafts the object it is named for.

After A4A-1 (dishcloth) and the blanket fix, the other flat-rows templates measured the same
way: a coaster drafted 19 x 7 cm, a placemat 38 x 11, a runner 48 x 13, a scarf 32 x 18, a
pillow 58 x 18 and a baby blanket 80 x 18. Every research, radar or R5 concept in those
categories was certified at that size under its object's name.

Now:
* each template drafts a standard-sized object;
* certification refuses a title naming only that object when the finished size is outside
  its band (`OBJECT_SIZE_OUT_OF_BAND`);
* square objects are bounded on both sides; oblong ones by short and long side separately;
* a cowl is not held to the scarf band, and a title naming two objects to no band.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_flat_rows_size_truth.py
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
from brambleloop.radar.opportunity import ConceptSeed  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402

# category -> (a title naming the object, its OLD drafted size in cm)
CASES = {
    "coaster": ("Linen Ridge Coaster", (19.2, 7.2)),
    "placemat": ("Linen Ridge Placemat", (38.4, 11.4)),
    "runner": ("Linen Ridge Table Runner", (48.0, 13.0)),
    "scarf": ("Linen Ridge Scarf", (32.0, 18.1)),
    "pillow": ("Linen Ridge Pillow Cover", (57.6, 18.1)),
    "baby": ("Linen Ridge Baby Blanket", (80.0, 18.1)),
}


class _Twin:
    def __init__(self, w, h):
        self.width_cm, self.height_cm = w, h


class _Cir:
    def __init__(self, title):
        self.title = title


def _twin_of(category, title):
    seed = ConceptSeed(slug=f"linen-ridge-{category}", title=title, category=category,
                       risk_class="A", price_cad=6.0, maker_hours=(2.0, 6.0),
                       design_hours=3.0, whitespace=0.5,
                       rationale="fixture concept for the flat rows size bands", origin="test")
    g = pipeline.concept_geometry(seed)
    concept = pipeline.Concept(slug=seed.slug, title=seed.title, category=seed.category,
                               stitch_repeat=[tuple(x) for x in g["stitch_repeat"]],
                               width_stitches=g["width_stitches"], rows=g["rows"],
                               colors=g["colors"])
    cir = pipeline.concept_to_cir(concept)
    result = compile_cir(cir)
    assert result.ok, (category, result.errors)
    return cir, build_twin(cir, result)


def test_every_plain_template_drafts_its_object_inside_the_band():
    for category, (title, _old) in CASES.items():
        cir, twin = _twin_of(category, title)
        assert C.object_size_findings(cir, twin) == [], (category, twin.width_cm,
                                                         twin.height_cm)


def test_every_old_template_size_is_refused():
    for category, (title, (w, h)) in CASES.items():
        bad = C.object_size_findings(_Cir(title), _Twin(w, h))
        assert [f.code for f in bad] == ["OBJECT_SIZE_OUT_OF_BAND"], (category, bad)


def test_oblong_bands_check_each_side_separately():
    runner = "Linen Ridge Table Runner"
    assert C.object_size_findings(_Cir(runner), _Twin(33.0, 150.0)) == []
    assert C.object_size_findings(_Cir(runner), _Twin(150.0, 33.0)) == []   # orientation-free
    assert C.object_size_findings(_Cir(runner), _Twin(80.0, 150.0))         # too wide
    assert C.object_size_findings(_Cir(runner), _Twin(33.0, 60.0))          # too short
    assert C.object_size_findings(_Cir("Plain Scarf"), _Twin(20.0, 300.0))  # too long
    assert C.object_size_findings(_Cir("Plain Placemat"), _Twin(30.0, 45.0)) == []


def test_square_bands_check_size_and_shape():
    assert C.object_size_findings(_Cir("Coaster"), _Twin(10.0, 10.0)) == []
    assert C.object_size_findings(_Cir("Coaster"), _Twin(10.0, 13.0))       # 1.3x: not square
    assert C.object_size_findings(_Cir("Lumbar Pillow"), _Twin(30.0, 50.0)) == []
    assert C.object_size_findings(_Cir("Pillow"), _Twin(20.0, 20.0))        # too small


def test_a_cowl_and_two_object_titles_are_not_held_to_these_bands():
    assert C.object_size_findings(_Cir("Ribbed Cowl"), _Twin(60.0, 25.0)) == []
    assert C.object_size_findings(_Cir("Coaster and Placemat Set"), _Twin(19.2, 7.2)) == []
    assert C.object_size_findings(_Cir("Scarf"), None) == []


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
