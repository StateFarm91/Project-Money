"""publish/schematic.py: the drawing's numbers are the assembly model's numbers."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir import assembly  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.products import garments as G  # noqa: E402
from brambleloop.publish import schematic as S  # noqa: E402


def _geo(cir):
    result = compile_cir(cir)
    twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
    return assembly.assemble(cir, twins)


def test_every_label_is_the_footprints_own_number():
    for cir in (G.harbour_pullover().build("M"), G.pebble_cardigan().build("8")):
        geo = _geo(cir)
        drawn = S.render_schematic(cir, geo)
        assert set(drawn.labels) == set(geo.footprints)
        for name, fp in geo.footprints.items():
            assert drawn.labels[name] == (f"{fp.across_cm:.1f} cm", f"{fp.up_cm:.1f} cm")
        assert drawn.image.size[0] == S.WIDTH_PX


def test_every_join_between_pieces_is_an_arrow_with_its_measured_length():
    cir = G.harbour_pullover().build("L")
    geo = _geo(cir)
    drawn = S.render_schematic(cir, geo)
    between = [j for j in geo.joins if j.piece_a != j.piece_b]
    assert len(drawn.arrows) == len(between) == 2
    for (a, b, length), j in zip(drawn.arrows, between):
        assert a == f"{j.piece_a}.{j.edge_a}" and b == f"{j.piece_b}.{j.edge_b}"
        assert length == f"{j.length_b_cm:.1f} cm"
    assert len(drawn.closures) == len(geo.joins) - len(between)


def test_a_one_piece_product_has_no_schematic():
    from brambleloop.products.builder import CATALOGUE, build
    cir = build(CATALOGUE[sorted(CATALOGUE)[0]])
    assert S.schematic_for(cir, compile_cir(cir)) is None


def test_the_pdf_carries_a_schematic_page_for_a_multi_piece_design():
    from brambleloop.publish.pdf import build_pattern_pdf, extracted_text
    cir = G.harbour_pullover().build("S")
    doc = build_pattern_pdf(cir, released_on=date(2026, 9, 26))
    text = extracted_text(doc.pdf_bytes)
    assert "Schematic" in text
    assert text.index("Schematic") < text.index("Materials")



def test_a_garment_pdf_explains_its_construction_before_the_instructions():
    """F-765: pieces and joins, from the CIR's own assembly, before any row instruction."""
    from brambleloop.products.vessels import build_hexagon_coaster
    from brambleloop.publish.pdf import build_pattern_pdf, construction_overview, extracted_text

    cir = G.harbour_pullover().build("S")
    overview = construction_overview(cir)
    assert overview, "a multi-piece garment needs a construction overview"
    for comp in cir.components:
        assert comp.name.replace("_", " ") in overview[0], (comp.name, overview[0])
    assert sum(1 for line in overview if line.startswith("Join ")) == len(cir.assembly)

    text = extracted_text(build_pattern_pdf(cir, released_on=date(2026, 9, 26)).pdf_bytes)
    assert "How it goes together" in text
    assert text.index("How it goes together") < text.index("Instructions (US terms)")

    # A one-piece coaster has nothing to explain, and gets nothing.
    assert construction_overview(build_hexagon_coaster()) is None


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
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
