"""F-056 Size/Scale Intent: a size/shape query family from the twin's own dimensions.

The board row: "Size count in title and finished size in description; no size/shape query
family" -> "Add a size/shape query family from twin dimensions". The family is built only from
what the twin measured (a polygon's sides, a round-worked piece), a graded size count from the
pattern itself, never a small/large class; and a shape word that contradicts the twin is
refused as a tag (TAG_SHAPE_UNTRUE), wherever the phrase came from.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_size_shape_intent.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.commerce import search  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402

FAILS = 0


def check(name, fn):
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as e:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {e!r}")


def _twin(build_key):
    cir = l0.cir_for(build_key)
    return build_twin(cir, compile_cir(cir))


def test_the_shape_is_read_from_the_twin():
    assert search.shape_of(_twin("hexagon_coasters")) == "hexagon"
    assert search.shape_of(_twin("basket_medium")) == "hexagon"
    assert search.shape_of(_twin("key_basket")) == "round"
    for flat in ("cloudline_blanket", "placemat_pair", "snowflake_ornaments"):
        assert search.shape_of(_twin(flat)) is None, flat


def test_the_family_adds_shape_and_graded_size_phrases_only():
    qs = search.build_query_set("coaster", ["contrast"], None, ["texture"],
                                difficulty="beginner", shape="hexagon", sizes=1)
    shape = [q.phrase for q in qs if q.family == "shape"]
    assert shape == sorted(["hexagon coaster pattern", "hexagon crochet coaster"]) or \
        set(shape) == {"hexagon coaster pattern", "hexagon crochet coaster"}, shape
    assert not [q for q in qs if q.family == "sizes"]       # one size: no size phrase
    qs3 = search.build_query_set("basket", [], None, ["texture"], difficulty="beginner",
                                 shape="hexagon", sizes=3)
    sizes = {q.phrase for q in qs3 if q.family == "sizes"}
    assert sizes == {"basket pattern in 3 sizes", "multi size basket pattern"}, sizes
    every = " ".join(q.phrase for q in qs3)
    for word in ("small", "large", "mini", "oversized"):
        assert word not in every.split(), word
    fam = [q for q in qs3 if q.family in ("shape", "sizes")]
    assert len(fam) == 4, fam
    for q in fam:
        assert q.provenance == search.ASSUMED and not q.observed


def test_no_shape_family_without_a_measured_shape():
    qs = search.build_query_set("blanket", ["cloud"], None, ["texture"],
                                difficulty="beginner")
    assert qs
    assert not [q for q in qs if q.family in ("shape", "sizes")]


def test_a_shape_word_that_contradicts_the_twin_is_refused():
    assert search.tag_truth("round coaster", difficulty=None, shape="hexagon")
    assert "TAG_SHAPE_UNTRUE" in search.tag_truth("square basket", difficulty=None,
                                                  shape="round")
    assert search.tag_truth("hexagonal basket", difficulty=None, shape="hexagon") is None
    assert search.tag_truth("circle basket", difficulty=None, shape="round") is None
    # An unmeasured shape neither supports nor refutes a phrase.
    assert search.tag_truth("round coaster", difficulty=None) is None
    probs = search.tags_truth(["hexagon coaster", "round coaster"], difficulty=None,
                              shape="hexagon")
    assert len(probs) == 1 and "round coaster" in probs[0], probs


def test_every_launch0_curated_tag_set_agrees_with_its_twin():
    from brambleloop.seo import strategy

    checked = 0
    for slug in l0.LAUNCH0_SLUGS:
        cand = l0.candidate(slug)
        assert cand.variants, slug
        shapes = {search.shape_of(_twin(v.build)) for v in cand.variants}
        tags = strategy.TAGS.get(slug) or []
        for shape in shapes:
            found = search.tags_truth(tags, difficulty=None, shape=shape)
            assert not [p for p in found if "TAG_SHAPE_UNTRUE" in p], (slug, shape, found)
            checked += 1
    assert checked >= len(l0.LAUNCH0_SLUGS)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        check(name, fn)
    sys.exit(1 if FAILS else 0)
