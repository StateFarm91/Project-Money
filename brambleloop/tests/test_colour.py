"""#280: dated palette evidence, and the line between a colourway and a different product.

Etsy publishes per-image hex for every listing, so the marketplace half of this requirement
is free and already collected. These tests are about the two things the module refuses.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing  # noqa: E402
from brambleloop.creative.concept import Concept  # noqa: E402
from brambleloop.creative.prototype import author  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402
from brambleloop.seasonal import colour as C  # noqa: E402

PALETTES = [["1F3A2E", "FAF6EB", "C9A227"], ["1F3A2E", "FAF6EB", "6E1F2A"],
            ["1F3A2E", "C9A227", "FAF6EB"], ["244A3A", "FAF6EB", "C9A227"],
            ["1F3A2E", "FAF6EB", "2E3A1F"], ["1F3A2E", "FAF6EB", "C9A227"]]


def _db(palettes=PALETTES, pod="blankets", unaudited=0):
    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        for i, hexes in enumerate(palettes):
            s.add(BenchmarkListing(
                benchmark_key=benchmarks.MJS_KEY, listing_ref=f"b{i}", title="t", pod=pod,
                detail={"palette": [{"rank": r + 1, "hex": h} for r, h in enumerate(hexes)]}))
        for i in range(unaudited):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY,
                                   listing_ref=f"u{i}", title="t", pod=pod, detail={}))
    return db


def _cir():
    concept = Concept(
        key="k", title="Lantern Throw",
        premise="a folded ridge that stands proud of the field so it reads across a room",
        pod="blankets", form="rectangle_throw", construction="flat_rows", motif="lantern",
        palette_story="ember and soot", recipient="self", occasion="everyday",
        feeling="cosy", function="warmth", make_lane="LONG", provenance="test")
    return author(concept)


def test_the_palette_is_counted_from_photographs_and_is_dated():
    """A palette with no observation window is a claim about taste; one with a window is a
    measurement that can be seen to have gone stale."""
    palette = C.observed_palette(_db(), pod="blankets")
    assert palette["measurable"] is True
    assert palette["audited"] == 6
    assert len(palette["observed_between"]) == 2
    # Ordered by how often the department is photographed in them.
    counts = [s["seen_in_listings"] for s in palette["swatches"]]
    assert counts == sorted(counts, reverse=True), counts
    assert palette["swatches"][0]["hex"] == "#FAF6EB"


def test_a_palette_read_from_nothing_is_unmeasurable_rather_than_neutral():
    """An empty palette reported as neutral lets a colourway decision rest on nothing."""
    thin = C.observed_palette(_db(palettes=PALETTES[:2], unaudited=20), pod="blankets")
    assert thin["measurable"] is False
    assert thin["audited"] == 2
    assert thin["floor"] == C.MIN_AUDITED
    assert "rest on nothing" in thin["reason"]

    raised = None
    try:
        C.propose_colourway(_cir(), thin)
    except C.ColourRefused as e:
        raised = e
    assert raised is not None
    assert "no observed palette" in str(raised)


def test_a_colourway_takes_the_number_of_colours_the_pattern_already_has():
    cir = _cir()
    palette = C.observed_palette(_db(), pod="blankets")
    proposed = C.propose_colourway(cir, palette)
    assert set(proposed["colourway"]) == set(cir.colors)
    assert len(proposed["colourway"]) == len(cir.colors)
    # And every pair separates enough to survive a thumbnail and a greyscale print.
    for pair in proposed["separations"]:
        assert pair["value_gap"] >= C.MIN_VALUE_SEPARATION, pair


def test_a_palette_that_cannot_supply_separable_colours_is_refused():
    """Filling the rest from somewhere else would put colours in a listing that this market
    has not been seen using, which is the opposite of what the evidence is for."""
    flat = [["1F3A2E", "2E3A1F", "1F3A2F"]] * 6
    palette = C.observed_palette(_db(palettes=flat), pod="blankets")
    assert palette["measurable"] is True

    raised = None
    try:
        C.propose_colourway(_cir(), palette)
    except C.ColourRefused as e:
        raised = e
    assert raised is not None
    assert "opposite of what the evidence is for" in str(raised)


def test_a_colour_change_is_a_variant_only_while_the_pattern_is_unchanged():
    """The requirement's own condition. A two-colour pattern given a three-colour way is a
    different pattern wearing this one's name."""
    cir = _cir()
    good = C.is_variant(cir, {role: "#1F3A2E" if i else "#FAF6EB"
                              for i, role in enumerate(cir.colors)})
    assert good["is_variant"] is True
    assert "only the yarn changed" in good["why"]

    extra = dict.fromkeys(list(cir.colors) + ["third"], "#C9A227")
    more = C.is_variant(cir, extra)
    assert more["is_variant"] is False
    assert "changes the pattern" in more["why"]
    assert "own version" in more["otherwise"]

    moved = {"main": "#1F3A2E", "trim": "#FAF6EB"}
    renamed = C.is_variant(cir, moved)
    assert renamed["is_variant"] is False
    assert "where a colour goes" in renamed["why"]


def test_a_colourway_stated_in_words_cannot_be_checked_against_a_photograph():
    cir = _cir()
    verdict = C.is_variant(cir, {role: "sage" for role in cir.colors})
    assert verdict["is_variant"] is False
    assert "not six-digit hex" in verdict["why"]


def test_the_two_sources_this_company_does_not_have_are_named():
    """A forecast resting on one source presented as resting on three is the most confident
    kind of wrong."""
    out = C.forecast(_db(), pod="blankets")
    assert out["marketplace_evidence"]["measurable"] is True
    assert out["fashion_and_home_signals"]["measurable"] is False
    assert out["brambleloop_performance"]["measurable"] is False
    assert "customers gate" in out["brambleloop_performance"]["reason"]
    assert out["as_of"]


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
