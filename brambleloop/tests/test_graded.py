"""cir/graded.py: sourced body tables, stated ease, and a design that is a function of size."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir import graded as G  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.grading import GradingRefused  # noqa: E402
from brambleloop.cir.model import CIR, Component, Gauge, Op, Repeat, Row  # noqa: E402
from brambleloop.cir.reverse import compare  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402

GAUGE = Gauge(16, 18)


def _panel(g: G.GradedSize) -> CIR:
    """The smallest honest template: a back panel, chest-wide and back-length tall."""
    w = g.stitches(g.finished_cm("bust") / 2)
    n = g.rows(g.finished_cm("back_length"))
    return CIR(slug=f"panel-{g.size.lower()}", title="Panel", version="1",
               construction="flat_rows", gauge=g.gauge,
               components=[Component("back", "flat_rows", foundation=w, rows=[
                   Row(i, [Op("sc", w)], declared_count=w, turning_chain=1)
                   for i in range(1, n + 1)])])


def _design(template=_panel, requires=("bust", "back_length"), table=G.WOMAN, **kw):
    return G.GradedDesign(key="panel", title="Panel", table=table,
                          fit=G.FitIntent({"bust": 10, "back_length": 5}), gauge=GAUGE,
                          template=template, requires=requires, **kw)


def test_the_tables_cite_their_source_and_retrieval_date():
    for table in (G.WOMAN, G.CHILD):
        assert table.source_url.startswith("https://www.craftyarncouncil.com/standards/")
        assert table.retrieved == "2026-09-26"
    source = Path(G.__file__).read_text()
    assert G.CYC_WOMAN_URL in source and G.CYC_CHILD_URL in source


def test_transcribed_values_match_the_published_chart():
    assert G.WOMAN.size("M").cm("bust") == 94.0          # 91.5-96.5 cm
    assert G.WOMAN.size("XS").cm("upper_arm") == 25.0
    assert G.WOMAN.size("5X").cm("hip") == 156.0         # 155-157 cm
    assert G.CHILD.size("2").cm("bust") == 53.0
    assert G.CHILD.size("16").cm("armhole_depth") == 19.0
    assert G.WOMAN.names == ("XS", "S", "M", "L", "XL", "2X", "3X", "4X", "5X")


def test_what_the_source_does_not_publish_is_unsourced_and_grading_to_it_refuses():
    for table in (G.WOMAN, G.CHILD):
        _vac_57 = 0
        for body in table.sizes:
            _vac_57 += 1
            assert body.cm("wrist") is G.UNSOURCED and body.cm("neck") is G.UNSOURCED
        assert _vac_57, "table.sizes was empty: the loop proved nothing (F-123)"
    design = _design(requires=("bust", "wrist"))
    assert design.sourced_sizes() == ()
    try:
        design.build("M")
    except GradingRefused as e:
        assert "UNSOURCED" in str(e) and "wrist" in str(e)
    else:
        raise AssertionError("graded to a size using an invented wrist")


def test_every_graded_size_compiles_reverse_compiles_and_rises_monotonically():
    for table in (G.WOMAN, G.CHILD):
        design = _design(table=table)
        design.check_monotonic()
        widths = []
        for size, cir in design.build_all().items():
            result = compile_cir(cir)
            assert result.ok, (size, [str(f) for f in result.errors])
            assert compare(cir, write_pattern(cir, result)) == [], size
            widths.append(cir.components[0].foundation)
            assert cir.provenance is not None and cir.provenance.benchmarks_consulted == ()
        assert widths == sorted(widths) and len(set(widths)) == len(widths)


def test_a_transposed_body_table_is_refused():
    body = list(G.WOMAN.sizes)
    body[3], body[4] = body[4], body[3]
    swapped = G.BodyTable("swapped", G.WOMAN.source_url, G.WOMAN.retrieved, tuple(body))
    try:
        _design(table=swapped).check_monotonic()
    except GradingRefused as e:
        assert "bust" in str(e)
    else:
        raise AssertionError("a size run that goes backwards passed")


def test_a_fixed_times_repeat_in_a_graded_template_is_refused():
    def fixed(g):
        cir = _panel(g)
        cir.components[0].rows[0] = Row(1, [Repeat([Op("sc", 2)], times=10)],
                                        declared_count=20, turning_chain=1)
        return cir
    try:
        _design(template=fixed).build("M")
    except GradingRefused as e:
        assert "fixed-times" in str(e)
    else:
        raise AssertionError("a fixed-times repeat passed in a graded template")


def test_negative_ease_and_unknown_measurements_are_refused():
    for bad in ({"bust": -2}, {"elbow": 3}):
        try:
            G.FitIntent(bad)
        except GradingRefused:
            pass
        else:
            raise AssertionError(bad)


def test_the_size_table_is_written_and_read_back():
    design = _design(requires=("bust", "back_length", "upper_arm"))
    text = G.write_size_table(design)
    assert G.CYC_WOMAN_URL in text
    assert G.parse_size_table(text) == design.size_table()
    tampered = text.replace("94 cm to fit", "95 cm to fit")
    assert tampered != text and G.parse_size_table(tampered) != design.size_table()


def test_the_monotonic_check_measures_the_built_cir_when_it_can():
    """Audit C-10: requested figures can rise while the built object does not, because
    whole stitches and rows are rounded per size. A design that says how to measure a built
    size is checked on what it built; one that does not is checked on its figures only."""
    import dataclasses
    widths = {}

    def measure(cir):
        w = cir.components[0].foundation
        widths[cir.slug] = w
        return {"chest": float(w)}
    design = dataclasses.replace(_design(table=G.WOMAN), measure=measure)
    design.check_monotonic()
    assert len(widths) == len(G.WOMAN.names)
    flat = dataclasses.replace(design, measure=lambda cir: {"chest": 1.0})
    flat.check_monotonic(built=False)
    try:
        flat.check_monotonic()
    except GradingRefused as e:
        assert "built chest" in str(e)
    else:
        raise AssertionError("a built chest that does not rise passed")


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
