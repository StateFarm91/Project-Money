"""The motif library and the generated catalogue (sections 2, 5, 16).

Section 16 asks for about twelve exceptional release candidates rather than hundreds of
mediocre ones. Engineering twelve products by hand is twelve chances to make an arithmetic
slip; generating them from validated motifs puts the slip in one place, where a test can find
it. These tests are that test.

Every design still compiles, reverse-compiles and certifies individually. Sharing a builder is
not sharing a pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.reverse import compare  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.products import motifs  # noqa: E402
from brambleloop.products.builder import (  # noqa: E402
    CATALOGUE, Design, DesignDoesNotFit, build, for_slug,
)


# ---- the motif library -----------------------------------------------------


def test_every_motif_is_well_formed_and_distinct():
    assert motifs.check_library() == [], motifs.check_library()
    assert len(motifs.LIBRARY) >= 6


def test_a_ragged_motif_is_refused():
    """A grid whose rows disagree produces a pattern whose rows disagree."""
    bad = motifs.Motif("x", "X", ("0000", "000"))
    try:
        bad.validate()
    except motifs.MalformedMotif as e:
        assert "ragged" in str(e) or "wide" in str(e)
    else:
        raise AssertionError("a ragged motif validated")


def test_a_motif_of_something_other_than_ones_and_zeros_is_refused():
    try:
        motifs.Motif("x", "X", ("0102",)).validate()
    except motifs.MalformedMotif:
        pass
    else:
        raise AssertionError("a motif with stray characters validated")


def test_motif_density_is_inside_the_band_that_makes_fabric():
    for slug, m in motifs.LIBRARY.items():
        assert motifs.MIN_DENSITY <= m.density <= motifs.MAX_DENSITY, (slug, m.density)


def test_a_motif_is_identified_by_its_content():
    a = motifs.get("fir-and-star")
    b = motifs.Motif("copy", "Copy", a.grid)
    assert a.sha256 == b.sha256, "identical grids must hash identically"
    assert a.sha256 != motifs.get("snowfall").sha256


# ---- the builder -----------------------------------------------------------


def test_a_width_the_motif_cannot_tile_is_refused():
    """A truncated motif compiles perfectly and is still a defect."""
    d = Design(slug="x", title="X", motif="fir-and-star", palette="nordic",
               width_stitches=100, motif_repeats=2)
    try:
        build(d)
    except DesignDoesNotFit as e:
        assert "cut off mid-shape" in str(e)
    else:
        raise AssertionError("a width that truncates the motif was accepted")


def test_an_unknown_palette_is_refused():
    d = Design(slug="x", title="X", motif="snowfall", palette="neon",
               width_stitches=24, motif_repeats=1)
    try:
        build(d)
    except KeyError:
        pass
    else:
        raise AssertionError("an off-brand palette was accepted")


def test_rows_are_emitted_as_repeats_not_flattened():
    """Flattening produced row instructions eleven lines long that no maker could follow."""
    cir = build(CATALOGUE["autumn-oak-mosaic-throw"])
    from brambleloop.cir.model import Repeat

    body_rows = cir.components[0].rows[1:]
    assert all(isinstance(r.ops[0], Repeat) for r in body_rows[:10])
    text = write_pattern(cir, compile_cir(cir))
    longest = max(len(line) for line in text.split("\n"))
    assert longest < 260, f"a row instruction is {longest} characters long"


# ---- the catalogue ---------------------------------------------------------


def test_every_design_compiles():
    broken = []
    for slug, design in CATALOGUE.items():
        result = compile_cir(build(design))
        if not result.ok:
            broken.append((slug, [str(f) for f in result.errors][:2]))
    assert not broken, broken


def test_every_design_survives_independent_reverse_compilation():
    """The customer text is what someone follows; it must match the source, every time."""
    disagreements = []
    for slug, design in CATALOGUE.items():
        cir = build(design)
        result = compile_cir(cir)
        findings = compare(cir, write_pattern(cir, result), "US")
        if findings:
            disagreements.append((slug, [str(f) for f in findings][:2]))
    assert not disagreements, disagreements


def test_every_design_is_a_plausible_physical_object():
    """Internally consistent arithmetic can still describe something absurd."""
    implausible = []
    for slug, design in CATALOGUE.items():
        cir = build(design)
        twin = build_twin(cir, compile_cir(cir))
        w, h = twin.width_cm, twin.height_cm
        yarn = sum(twin.yarn_metres_by_color.values())
        if not (5 <= w <= 200 and 5 <= h <= 260):
            implausible.append((slug, f"{w}x{h}cm"))
        if not (5 <= yarn <= 3000):
            implausible.append((slug, f"{yarn:.0f}m of yarn"))
    assert not implausible, implausible


def test_the_catalogue_covers_the_release_candidates():
    """Section 16: about twelve exceptional candidates, engineered rather than templated."""
    from brambleloop.radar.opportunity import select_portfolio
    from datetime import date

    from brambleloop.runtime.pipeline import ENGINEERED

    selected = select_portfolio(today=date(2026, 9, 17)).selected
    # Every slug that has a real design: generated from the motif library, or engineered in
    # a module of its own (the flagship and the round-worked pieces).
    engineered = set(CATALOGUE) | set(ENGINEERED)
    missing = [c.slug for c in selected
               if not c.seed.is_bundle and c.slug not in engineered]
    assert not missing, f"these candidates would ship the striped template: {missing}"


def test_a_bundle_has_no_engineered_pattern_of_its_own():
    """A bundle is its members. Generating a pattern for it invents a product."""
    assert for_slug("nordic-forest-bundle") is None


def test_the_flagship_certifies_end_to_end():
    cert = certify(build(CATALOGUE["autumn-oak-mosaic-throw"]))
    assert cert.granted, [str(f) for f in cert.findings][:3]
    assert cert.release_hash and len(cert.release_hash) == 64
    assert cert.confidence["scores"]["arithmetic"] >= 0.9


def test_a_class_b_design_is_marked_class_b():
    """The basket's arithmetic is verifiable; whether it stands up unaided is not."""
    from brambleloop.products.vessels import build_basket

    cir = build_basket("medium")
    assert cir.risk_class == "B"
    assert "physical sample" in (cir.designer_notes or "")


def test_two_designs_sharing_a_motif_are_still_different_products():
    a = build(CATALOGUE["cottage-wall-hanging"])
    b = build(CATALOGUE["pet-snuggle-mat"])
    assert a.slug != b.slug
    assert a.colors != b.colors or a.components[0].foundation != b.components[0].foundation
    assert certify(a).release_hash != certify(b).release_hash


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
