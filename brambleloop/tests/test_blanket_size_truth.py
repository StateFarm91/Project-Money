"""Blanket size truth: a "blanket" or "throw" is drafted as one, and certification checks it.

The flat-rows blanket template was 160 sts x 24 rows: a 128 x 22 cm strip. Any research or
radar concept in the blanket category (WS2 R5 maps the blankets pod there) was drafted from it
and called a throw. The fix is the same as A4A-1's dishcloth:

* the template is a throw, about 128 x 152 cm (Craft Yarn Council standard blanket sizes);
* certification refuses a title that names only a blanket when its finished size is under
  about 70 cm on a side, or its sides differ by more than 1.6x (`OBJECT_SIZE_OUT_OF_BAND`);
* a title naming another object as well ("Throw Pillow") is not a blanket for this band.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_blanket_size_truth.py
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


class _Twin:
    def __init__(self, w, h):
        self.width_cm, self.height_cm = w, h


class _Cir:
    def __init__(self, title):
        self.title = title


def _twin_of(title, category="blanket"):
    seed = ConceptSeed(slug="linen-ridge-blanket", title=title, category=category,
                       risk_class="A", price_cad=9.0, maker_hours=(20.0, 40.0),
                       design_hours=6.0, whitespace=0.5,
                       rationale="fixture blanket concept for the size band", origin="test")
    g = pipeline.concept_geometry(seed)
    concept = pipeline.Concept(slug=seed.slug, title=seed.title, category=seed.category,
                               stitch_repeat=[tuple(x) for x in g["stitch_repeat"]],
                               width_stitches=g["width_stitches"], rows=g["rows"],
                               colors=g["colors"])
    cir = pipeline.concept_to_cir(concept)
    result = compile_cir(cir)
    assert result.ok, result.errors
    return cir, build_twin(cir, result)


def test_the_blanket_template_drafts_a_throw_inside_the_band():
    cir, twin = _twin_of("Linen Ridge Throw")
    lo, hi = C.OBJECT_SIZE_BANDS["blanket"]["side_cm"]
    assert lo <= twin.width_cm <= hi and lo <= twin.height_cm <= hi, (twin.width_cm,
                                                                      twin.height_cm)
    assert twin.height_cm > 120, twin.height_cm               # a throw, not a 22 cm strip
    assert C.object_size_findings(cir, twin) == []


def test_the_old_strip_is_refused_whatever_it_is_called():
    for title in ("Linen Ridge Throw", "Linen Ridge Blanket", "Linen Ridge Afghan"):
        bad = C.object_size_findings(_Cir(title), _Twin(128.0, 21.7))
        assert [f.code for f in bad] == ["OBJECT_SIZE_OUT_OF_BAND"], (title, bad)
        assert bad[0].severity == C.ERROR
    # A square too small to be a blanket, and a runner-shaped one, are both refused.
    assert C.object_size_findings(_Cir("Tiny Blanket"), _Twin(40.0, 40.0))
    assert C.object_size_findings(_Cir("Long Blanket"), _Twin(80.0, 200.0))
    # The smallest standard blanket (stroller, 76 x 89 cm) passes.
    assert C.object_size_findings(_Cir("Stroller Blanket"), _Twin(76.0, 89.0)) == []


def test_a_title_naming_another_object_is_not_a_blanket_for_this_band():
    assert C.object_size_findings(_Cir("Linen Throw Pillow Cover"), _Twin(40.0, 40.0)) == []
    assert C.object_size_findings(_Cir("Blanket Basket"), _Twin(30.0, 25.0)) == []
    assert C.object_size_findings(_Cir("Linen Ridge Throw"), None) == []


def test_the_engineered_cable_throw_is_inside_the_band():
    cir = pipeline._engineered_cir("heirloom-cable-blanket")
    twin = build_twin(cir, compile_cir(cir))
    assert C.object_size_findings(cir, twin) == [], (twin.width_cm, twin.height_cm)


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
