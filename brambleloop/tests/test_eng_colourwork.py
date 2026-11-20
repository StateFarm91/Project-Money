"""ENG-COLOURWORK: a research-admitted colourwork family, proven end to end.

Each end-to-end test runs the real handlers through the worker on a scratch SQLite file:
research-style concept -> `radar.concept_intake` (admit) -> `radar.score` -> `cir.draft` (CIR)
-> `cir.compile` -> `gate.certify` (twin, reverse, originality) -> US and UK PDFs with the
chart. Every research source, finding and judgement here is a TEST FIXTURE (the shared
fixtures of `test_eng_families`); none is an observation, a customer or a judgement anybody
made. No concept here is a catalogue or POOL concept.

The gate tests are mutation tests: a CIR mutated to break exactly one rule is refused with that
rule's code, and with the rule's code path disabled the same mutant is accepted -- so the gate,
not something else, is what refuses it.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import ast
import copy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_eng_families as EF  # noqa: E402  (shared research fixtures and chain runner)

from brambleloop.cir import colourwork as CWV  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR, Chart, Provenance  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.creative import colourwork as CW  # noqa: E402
from brambleloop.creative import construction_families as CF  # noqa: E402
from brambleloop.creative import fallback_constructions as FC  # noqa: E402
from brambleloop.gates import originality as O  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.publish.pdf import build_pattern_pdf, extracted_text  # noqa: E402
from brambleloop.radar import intake  # noqa: E402
from brambleloop.runtime.pipeline import Concept  # noqa: E402

PALETTE = {"forest": "#244A3A", "cream": "#FAF6EB"}


def _proposal(slug, title, category, form, **kw):
    return EF._proposal(slug, title, category, form=form, construction="tapestry",
                        motif=kw.pop("motif", "geometric band"), **kw)


THROW = _proposal("modern-step-tapestry-throw", "Modern Step Tapestry Throw", "blanket",
                  "rectangle_throw", function="covers a sofa")
PLACEMAT = _proposal("chevron-tapestry-placemat", "Chevron Tapestry Placemat", "placemat",
                     "flat_panel", pod="kitchen_bath", function="lays a place at the table")
BASKET = _proposal("wave-tapestry-basket", "Wave Tapestry Basket", "basket", "basket",
                   function="holds yarn by the sofa")
CUSHION = _proposal("lattice-tapestry-cushion-cover", "Lattice Tapestry Cushion Cover",
                    "pillow", "pillow", function="fronts a sofa cushion")


def _colours(ops):
    for op in ops:
        if "ops" in op:
            yield from _colours(op["ops"])
        elif op.get("color"):
            yield op["color"]


def _chain(proposal) -> tuple[dict, CIR]:
    out = EF._certify_research_concept(proposal)
    assert out["drafted"]["construction"] == FC.COLOURWORK_TAPESTRY, out["drafted"]
    cir = CIR.from_dict(out["cir"])
    charted = [c for c in cir.components if c.chart is not None]
    assert len(charted) == 1, "exactly one charted piece"
    comp = charted[0]
    # The chart is declared, generated from the library, and painted stitch by stitch.
    assert comp.chart.technique == "tapestry" and comp.chart.motif in CW.MOTIFS
    painted = [r["index"] for c in out["cir"]["components"] for r in c["rows"]
               if list(_colours(r["ops"]))]
    assert len(painted) >= len(comp.chart.rows) // 2, "the chart band changes colour in-row"
    # Its provenance declares the motif primitive and consults no benchmark (B-117).
    prov = cir.provenance
    assert prov is not None and CW.motif_primitive(comp.chart.motif) in prov.primitives_used
    assert tuple(prov.benchmarks_consulted) == ()
    # The twin renders the true chart.
    result = compile_cir(cir)
    assert result.ok and not CWV.problems(cir, result)
    twin = build_twin(cir, result, component=comp.name)
    rows = sorted({c.row for c in twin.cells})
    grid = dict(zip(rows, twin.color_grid()))
    for i in range(comp.chart.first_row, comp.chart.last_row + 1):
        assert grid[i] == comp.chart.colours_at(i), f"twin row {i} is not the chart"
    # The fabric backs the "tapestry" name, and the motif word is backed by the declared motif.
    truth = launch0.fabric_truth(cir, twin)
    assert truth["backed"] and "tapestry" in truth["colourwork_claims"], truth["why"]
    assert launch0.motif_promise(cir)["backed"], launch0.motif_promise(cir)["why"]
    return out, cir


def _pdfs(cir: CIR) -> None:
    """US and UK editions: a clean chart with symbol and colour keys and row numbers, the
    written row-by-row instructions, and yarn per colour."""
    comp = next(c for c in cir.components if c.chart is not None)
    unit = "Row" if comp.construction == "flat_rows" else "Rnd"
    last = comp.rows[-1].index
    for term, sc in (("US", "sc"), ("UK", "dc")):
        doc = build_pattern_pdf(cir, terminology=term)
        assert doc.terminology == term and not doc.problems, doc.problems
        text = " ".join(extracted_text(doc.pdf_bytes).split())
        charts = [f for f in doc.figures if isinstance(f, dict) and f.get("kind") == "chart"]
        assert charts, "the PDF carries the chart"
        assert "Chart symbols" in text and "Colour key" in text, "symbol and colour keys"
        for colour, hexcode in PALETTE.items():
            assert colour in text and hexcode in text, (term, colour)
        # Yarn requirements per colour, from the twin (carried strands included).
        assert set(doc.yardage_by_color) == set(PALETTE), doc.yardage_by_color
        assert all(m > 0 for m in doc.yardage_by_color.values())
        assert "How much yarn" in text
        # Row-by-row written instructions, first and last, in this edition's terms.
        assert f"{unit} 1" in text and f"{unit} {last}" in text, (term, unit, last)
        assert f"{sc} in next" in text or f"{sc} in each" in text, term
        assert "colourwork in" in text and "worked from the chart" in text, "overview names it"
        assert "tile 1" in text.lower() or "chart" in text.lower()


def _assert_certified(out: dict) -> None:
    EF._assert_certified_end_to_end(out)
    codes = {f["code"] for f in out["certificate"].get("findings") or []}
    assert not codes & set(CWV.CODES) and "CHART_TWIN_DISAGREE" not in codes, codes
    assert "originality" in out["certificate"]["stages_run"]


# ---- end-to-end proofs (CF.PAIR_PROOFS names each) -------------------------------------------


def test_a_research_tapestry_throw_certifies_with_its_chart():
    out, cir = _chain(THROW)
    _assert_certified(out)
    # A throw is the Craft Yarn Council throw size the title names.
    twin = build_twin(cir, compile_cir(cir))
    assert 110 <= twin.width_cm <= 140 and 140 <= twin.height_cm <= 165, (twin.width_cm,
                                                                          twin.height_cm)
    _pdfs(cir)


def test_a_research_tapestry_placemat_certifies_with_its_chart():
    out, cir = _chain(PLACEMAT)
    _assert_certified(out)
    assert cir.components[0].chart.motif == "chevron", "the title's motif word is the chart"
    _pdfs(cir)


def test_a_research_tapestry_basket_wall_certifies_with_its_chart():
    out, cir = _chain(BASKET)
    _assert_certified(out)
    comp = cir.components[0]
    assert comp.construction == "joined_rounds" and comp.chart.motif == "wave"
    assert comp.chart.first_row > 1, "the base is plain; the chart is on the wall"
    _pdfs(cir)


def test_a_research_tapestry_cushion_is_physical_gated_with_its_chart():
    out, cir = _chain(CUSHION)
    assert [c.name for c in cir.components] == ["front", "back"] and cir.assembly
    assert out["compiled"]["compiled"] is True
    reasons = out["certified"]["reasons"]
    assert out["certified"]["granted"] is False and reasons, out["certified"]
    assert all("PHYSICAL_TEST_REQUIRED" in r for r in reasons), reasons
    # The PDF is not rendered on nobody's decision: a cushion is a closed stuffed form, and
    # whether it is merchandised to a child is an owner decision bound to this design
    # (`launch0.NOT_MERCHANDISED_TO_A_CHILD`). Held at the PDF too, by name -- not bypassed.
    from brambleloop.publish.pdf import ChildrensDecisionRequired

    for term in ("US", "UK"):
        try:
            build_pattern_pdf(cir, terminology=term)
        except ChildrensDecisionRequired as exc:
            assert "closed stuffed form" in str(exc)
        else:
            raise AssertionError("a cushion PDF rendered with no children's decision")


# ---- the generator ------------------------------------------------------------------------


def test_every_library_motif_tiles_a_chart_that_passes_every_gate():
    assert CW.library_problems() == []
    assert set(CW.MOTIFS) == {"diamond", "chevron", "step", "lattice", "check", "wave"}


def test_charts_are_deterministic_and_concept_specific():
    a = CW.design("modern-step-tapestry-throw", "Modern Step Tapestry Throw")
    b = CW.design("modern-step-tapestry-throw", "Modern Step Tapestry Throw")
    assert a == b, "the same concept always draws the same chart"
    assert a["motif"] == "step", "a named motif is the one drawn"
    drawn = {CW.design(f"tapestry-throw-{i}", "Tapestry Throw")["motif"] for i in range(40)}
    assert len(drawn) >= 4, f"unnamed concepts draw from the whole library: {drawn}"
    layouts = {tuple(sorted((k, v) for k, v in CW.design(f"t-{i}", "Step Tapestry Throw").items()
                            if k != "tile")) for i in range(40)}
    assert len(layouts) >= 6, "layout choices (block, drop, inversion, separator) vary"


def _placemat_cir() -> CIR:
    c = Concept(slug="chevron-tapestry-placemat", title="Chevron Tapestry Placemat",
                category="placemat", stitch_repeat=[], width_stitches=0, rows=0,
                colors=dict(PALETTE))
    prov = Provenance(concept_key="chevron-tapestry-placemat", brief_digest="0" * 16,
                      primitives_used=CW.FLAT_PRIMITIVES + (CW.motif_primitive("chevron"),))
    return CW.flat_piece(c, provenance=prov)


def _set_row(cir: CIR, index: int, fabric_line: str, *, key=None, chart_too: bool = True):
    """Rewrite one charted row in both the chart and the instructions (or only the
    instructions), keeping the stitch count."""
    comp = cir.components[0]
    key = key or comp.chart.key
    if chart_too:
        comp.chart.rows[index - comp.chart.first_row] = fabric_line
    row = next(r for r in comp.rows if r.index == index)
    row.ops = CW._row_ops(fabric_line, key, row.color, reverse=index % 2 == 0, repeat=1)


def _codes(cir: CIR) -> set[str]:
    return {f.code for f in compile_cir(cir).findings if f.severity == "ERROR"}


def test_the_generated_placemat_passes_every_chart_gate():
    cir = _placemat_cir()
    assert _codes(cir) == set()
    assert certify(cir).granted


# ---- mutation tests: one per gate ---------------------------------------------------------


def test_mutant_float_too_long_is_refused_by_the_float_gate():
    cir = _placemat_cir()
    comp = cir.components[0]
    i = comp.chart.first_row + 1
    width = len(comp.chart.rows[0])
    line = "11" + "0" * (width - 4) + "11"     # the contrast carried width-4 sts unworked
    _set_row(cir, i, line)
    assert _codes(cir) == {"COLOURWORK_FLOAT_TOO_LONG"}, _codes(cir)
    assert not certify(cir).granted
    # Kill check: with the bound lifted the same mutant compiles, so the float gate refuses it.
    real = dict(CWV.MAX_FLOAT)
    try:
        CWV.MAX_FLOAT["tapestry"] = 10_000
        assert _codes(cir) == set()
    finally:
        CWV.MAX_FLOAT.clear()
        CWV.MAX_FLOAT.update(real)
    # The bound is exact: a carry of MAX_FLOAT passes, MAX_FLOAT + 1 does not.
    cap = CWV.MAX_FLOAT["tapestry"]
    ok_line = ("11" + "0" * cap) * (width // (cap + 2)) + "1" * (width % (cap + 2))
    _set_row(cir, i, ok_line[:width])
    assert "COLOURWORK_FLOAT_TOO_LONG" not in _codes(cir), _codes(cir)


def test_mutant_float_is_measured_around_the_join_for_rounds():
    assert CWV._longest_carry(list("ab" + "a" * 10 + "b"), "b", cyclic=True) == 10
    assert CWV._longest_carry(list("b" + "a" * 6 + "b" + "a" * 6), "b", cyclic=True) == 6
    assert CWV._longest_carry(list("b" + "a" * 6 + "b" + "a" * 6), "b", cyclic=False) == 6
    assert CWV._longest_carry(list("aaab"), "b", cyclic=False) == 3


def test_mutant_extra_colours_are_refused_by_the_colour_count_gate():
    # A third yarn in one row: declared and yarned, but tapestry carries two.
    cir = _placemat_cir()
    cir.colors["gold"] = "#C49545"
    from brambleloop.cir.model import Material

    cir.materials.append(Material(name="worsted acrylic", yarn_weight="worsted",
                                  color_id="gold"))
    comp = cir.components[0]
    comp.chart.key["2"] = "gold"
    i = comp.chart.first_row + 2
    width = len(comp.chart.rows[0])
    _set_row(cir, i, ("110022" * width)[:width])
    assert _codes(cir) == {"COLOURWORK_COLOUR_COUNT"}, _codes(cir)
    real = dict(CWV.MAX_COLOURS_IN_ROW)
    try:
        CWV.MAX_COLOURS_IN_ROW["tapestry"] = 3
        assert _codes(cir) == set(), "the row cap is what refuses the three-colour row"
    finally:
        CWV.MAX_COLOURS_IN_ROW.clear()
        CWV.MAX_COLOURS_IN_ROW.update(real)
    # More colours in the piece than MAX_COLOURS, each row still two.
    cir = _placemat_cir()
    for name, hexcode in (("gold", "#C49545"), ("wine", "#6E1F2A"), ("ink", "#1A2B3C")):
        cir.colors[name] = hexcode
        cir.materials.append(Material(name="worsted acrylic", yarn_weight="worsted",
                                      color_id=name))
    comp = cir.components[0]
    comp.chart.key.update({"2": "gold", "3": "wine", "4": "ink"})
    for k, sym in enumerate("234"):
        i = comp.chart.first_row + k + 3
        # Carry the new yarn and the main through the row only; the contrast rests.
        width = len(comp.chart.rows[0])
        _set_row(cir, i, (("00" + sym * 2) * width)[:width])
    codes = _codes(cir)
    assert "COLOURWORK_COLOUR_COUNT" in codes, codes
    # A chart colour the CIR does not declare.
    cir = _placemat_cir()
    cir.components[0].chart.key["1"] = "teal"
    assert "COLOURWORK_COLOUR_COUNT" in _codes(cir)


def test_mutant_instructions_disagreeing_with_the_chart_are_refused():
    # One row's instructions change colour; the chart does not.
    cir = _placemat_cir()
    comp = cir.components[0]
    i = comp.chart.first_row + 3
    line = comp.chart.rows[i - comp.chart.first_row]
    flipped = line[:5] + line[5:7].translate(str.maketrans("01", "10")) + line[7:]
    _set_row(cir, i, flipped, chart_too=False)
    assert _codes(cir) == {"CHART_INSTRUCTION_DISAGREE"}, _codes(cir)
    assert not certify(cir).granted
    # Kill check: compare nothing, and the mutant passes -- the agreement check refuses it.
    real = Chart.colours_at
    try:
        Chart.colours_at = lambda self, idx: None if not (
            self.first_row <= idx <= self.last_row) else [None]
        assert "CHART_INSTRUCTION_DISAGREE" not in _codes(cir)
    finally:
        Chart.colours_at = real
    # The chart row is the wrong width.
    cir = _placemat_cir()
    comp = cir.components[0]
    comp.chart.rows[0] = comp.chart.rows[0] + "0"
    assert _codes(cir) == {"CHART_STITCH_COUNT"}, _codes(cir)
    # A colour worked outside the chart.
    cir = _placemat_cir()
    comp = cir.components[0]
    width = len(comp.chart.rows[0])
    _set_row(cir, 1, ("11" + "0" * 4) * (width // 6), chart_too=False)
    assert _codes(cir) == {"CHART_INSTRUCTION_DISAGREE"}, _codes(cir)


def test_mutant_twin_disagreeing_with_the_chart_is_refused():
    cir = _placemat_cir()
    result = compile_cir(cir)
    twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
    assert CWV.twin_findings(cir, twins) == []
    mutant = copy.deepcopy(cir)
    row = mutant.components[0].chart.rows[2]
    mutant.components[0].chart.rows[2] = row.translate(str.maketrans("01", "10"))
    assert [f.code for f in CWV.twin_findings(mutant, twins)] == ["CHART_TWIN_DISAGREE"]


def test_mutant_unreachable_colour_change_is_refused_by_the_placement_gate():
    cir = _placemat_cir()
    comp = cir.components[0]
    i = comp.chart.first_row + 2
    width = len(comp.chart.rows[0])
    _set_row(cir, i, "0" * width)     # the contrast sits this row out (not carried)...
    codes = _codes(cir)               # ...so the next row asks for it at the far edge
    assert codes == {"COLOUR_CHANGE_UNREACHABLE"}, codes
    real = CWV.problems

    def without_placement(c, r=None):
        return [p for p in real(c, r) if p[0] != "COLOUR_CHANGE_UNREACHABLE"]
    try:
        CWV.problems = without_placement
        assert _codes(cir) == set()
    finally:
        CWV.problems = real
    # Rounds never turn: a yarn resting at the join is where the next round starts.
    c = Concept(slug="wave-tapestry-basket", title="Wave Tapestry Basket", category="basket",
                stitch_repeat=[], width_stitches=0, rows=0, colors=dict(PALETTE))
    basket = CW.basket_wall(c)
    bc = basket.components[0]
    j = bc.chart.first_row + 1
    bc.chart.rows[j - bc.chart.first_row] = "0" * len(bc.chart.rows[0])
    row = next(r for r in bc.rows if r.index == j)
    row.ops = CW._row_ops("0" * len(bc.chart.rows[0]), bc.chart.key, row.color,
                          reverse=False, repeat=1)
    assert "COLOUR_CHANGE_UNREACHABLE" not in _codes(basket)


# ---- routing -----------------------------------------------------------------------------


HOLDS = {
    # (category, form, construction, title): the hold label
    ("bag", "bag", "tapestry", "Wave Tapestry Tote"): FC.COLOURWORK_TAPESTRY,
    ("runner", "runner", "tapestry", "Wave Tapestry Table Runner"): FC.COLOURWORK_TAPESTRY,
    ("blanket", "rectangle_throw", "tapestry", "Wave Tapestry Baby Blanket"):
        FC.COLOURWORK_TAPESTRY,
    ("blanket", "rectangle_throw", "tapestry", "Mosaic Tapestry Throw"):
        CW.OVERLAY_MOSAIC,
    ("blanket", "rectangle_throw", "tapestry", "Inset Mosaic Tapestry Throw"): CW.INSET_MOSAIC,
    ("blanket", "rectangle_throw", "tapestry", "C2C Tapestry Throw"): CW.C2C,
    ("blanket", "rectangle_throw", "tapestry", "Heron Tapestry Throw"): FC.COLOURWORK_TAPESTRY,
    ("blanket", "rectangle_throw", "tapestry", "Snowflake Tapestry Throw"):
        FC.COLOURWORK_TAPESTRY,
    ("blanket", "rectangle_throw", "tapestry", "Wave And Step Tapestry Throw"):
        FC.COLOURWORK_TAPESTRY,
    ("placemat", "flat_panel", "tapestry", "Wave Tapestry Placemat Pair"):
        FC.COLOURWORK_TAPESTRY,
    # Declared flat rows but the title is charted: drafting it would mislabel the product.
    ("blanket", "rectangle_throw", "flat_rows", "Modern Step Tapestry Throw"):
        FC.COLOURWORK_TAPESTRY,
    # The overlay-mosaic construction itself has no engine yet.
    ("mosaic_blanket", "rectangle_throw", "mosaic_overlay", "Step Mosaic Throw"): "mosaic",
    ("blanket", "rectangle_throw", "corner_to_corner", "Step C2C Throw"): "c2c",
}


def test_categories_and_techniques_without_proof_are_held_by_name():
    for (cat, form, constr, title), label in HOLDS.items():
        got = CF.route(category=cat, title=title, form=form, construction=constr)
        assert not got["admitted"], (title, got)
        assert got["reason"].startswith(f"{CF.HOLD_PREFIX}{label}"), (title, got["reason"])
    # Through intake, so the hold reaches the concept's refusal reasons.
    reasons = intake.construction_verdict("bag", "bag", "tapestry", title="Wave Tapestry Tote")
    assert reasons and reasons[0].startswith(CF.HOLD_PREFIX), reasons
    # Every held category names its reason.
    for cat in ("bag", "baby", "runner", "wall_decor", "scarf", "dishcloth"):
        assert CW.HELD_CATEGORY_WHY[cat]


def test_a_tapestry_title_is_never_admitted_as_plain_stripes():
    """The hole this family closes: "Diamond Tapestry Throw" declared flat rows was admitted
    as a striped flat panel. Now it drafts the chart or is held; never stripes."""
    for cat, form, noun in (("blanket", "rectangle_throw", "Throw"),
                            ("placemat", "flat_panel", "Placemat"),
                            ("pillow", "pillow", "Cushion Cover")):
        for constr in ("flat_rows", "tapestry"):
            got = CF.route(category=cat, title=f"Diamond Tapestry {noun}", form=form,
                           construction=constr)
            assert got["family"] != FC.FLAT_PANEL, (cat, constr, got)
            assert got["admitted"] == (constr == "tapestry"), (cat, constr, got)
    # The existing two-chart tapestry basket keeps its own route and proof.
    got = CF.route(category="basket", title="Checked Tapestry Shelf Basket", form="basket",
                   construction="tapestry")
    assert got["admitted"] and got["family"] == FC.TAPESTRY


def test_admitted_pairs_are_exactly_the_proven_ones():
    pairs = {p for p in CF.PAIR_PROOFS if p[0] == FC.COLOURWORK_TAPESTRY}
    assert {c for _f, c in pairs} == {"blanket", "placemat", "basket", "pillow"}
    here = {n.name for n in ast.parse(Path(__file__).read_text()).body
            if isinstance(n, ast.FunctionDef)}
    for pair in pairs:
        path, _, name = CF.PAIR_PROOFS[pair].partition("::")
        assert path == "tests/test_eng_colourwork.py" and name in here, pair


# ---- originality (B-117, gates/originality.py) --------------------------------------------


def test_the_generator_reads_no_benchmark_and_the_chart_is_compared_before_sale():
    src = (ROOT / "src/brambleloop/creative/colourwork.py").read_text()
    imported = {n.module or "" for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.ImportFrom)}
    assert not any("teardown" in m or "benchmark" in m for m in imported), imported
    cir = _placemat_cir()
    chart = cir.components[0].chart.rows
    # No benchmark chart captured: the chart dimension is UNMEASURED, never "clear".
    review = O.similarity_review(cir)
    assert any(u.endswith(":chart") for u in review["unmeasured"]), review["unmeasured"]
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='cwo_')}/o.sqlite")
    db.create_all()
    # A benchmark whose chart is ours recoloured and mirrored: escalated as a copy.
    disguised = [r[::-1].translate(str.maketrans("01", "10")) for r in chart]
    O.record_chart_fingerprint(db, "benchmark-fixture-chart", disguised, title="fixture")
    review = O.similarity_review(cir, db=db)
    assert review["escalate"] and {"benchmark": "benchmark-fixture-chart",
                                   "dimensions": ["chart"]} in review["escalated"], review
    codes = {f.code for f in O.similarity_findings(cir, db=db)}
    assert "SIMILARITY_ESCALATED" in codes
    # An unrelated benchmark chart is clear.
    db2 = Database(f"sqlite:///{tempfile.mkdtemp(prefix='cwo_')}/o.sqlite")
    db2.create_all()
    other = [("1" * 3 + "0" * 9) * 5 if y % 4 < 2 else ("0" * 6 + "1" * 6) * 5
             for y in range(24)]
    O.record_chart_fingerprint(db2, "benchmark-fixture-other", other)
    review = O.similarity_review(cir, db=db2)
    assert not review["escalate"], review["escalated"]


# ---- the model --------------------------------------------------------------------------------


def test_the_chart_round_trips_and_an_uncharted_cir_is_unchanged():
    cir = _placemat_cir()
    back = CIR.from_dict(cir.to_dict())
    assert back.components[0].chart == cir.components[0].chart
    assert back.fingerprint == cir.fingerprint
    plain = copy.deepcopy(cir)
    plain.components[0].chart = None
    assert "chart" not in plain.to_dict()["components"][0], \
        "no existing Product Truth digest moves"



def _chart_cells(rounds: bool):
    """Render a one-row chart of three cells, A B C in working order, and read it back: the
    fill colour sampled inside each drawn cell (left to right on the page) and the column
    numbers printed beneath them (left to right)."""
    from PIL import ImageDraw

    from brambleloop.publish import charts as CH

    cir = copy.deepcopy(_placemat_cir())
    cir.colors = {"A": "#c81e1e", "B": "#1ec81e", "C": "#1e1ec8"}
    spec = CH.ChartSpec()
    grids = ([["a", "b", "c"]], [["A", "B", "C"]])
    texts: list[tuple[float, float, str]] = []
    real = ImageDraw.ImageDraw.text

    def spy(self, xy, text, *a, **kw):
        texts.append((xy[0], xy[1], str(text)))
        return real(self, xy, text, *a, **kw)

    ImageDraw.ImageDraw.text = spy
    try:
        img = CH.render_chart(cir, None, spec, grids, caption="mirror probe",
                              show_columns=True, rounds=rounds)
    finally:
        ImageDraw.ImageDraw.text = real
    cell = CH.cell_size(None, spec, grids)
    left = (img.width - 3 * cell) // 2
    y = spec.margin_px + int(cell * 0.85)   # clear of the glyph, the cue letter and the line
    rgb = {(0xc8, 0x1e, 0x1e): "A", (0x1e, 0xc8, 0x1e): "B", (0x1e, 0x1e, 0xc8): "C"}
    page = [rgb.get(img.getpixel((left + int(cell * (i + 0.85)), y))[:3]) for i in range(3)]
    under = sorted((x, t) for x, yy, t in texts
                   if yy >= img.height - spec.margin_px and t.isdigit())
    return page, [t for _, t in under]


def test_a_chart_of_rounds_is_drawn_mirrored_with_stitch_one_at_the_right():
    # Review b17-b finding 2: a round is worked right to left, so stitch 1 (colour A, the
    # first cell in working order) must print in the RIGHTMOST square, numbered "1" beneath
    # it, and the last stitch (C) at the left. A wrong mirror prints a wrong customer chart.
    page, numbers = _chart_cells(rounds=True)
    assert page == ["C", "B", "A"], page
    assert numbers == ["3", "2", "1"], numbers


def test_a_flat_chart_control_is_not_mirrored():
    # The control: flat rows are drawn in stored order, column 1 at the left.
    page, numbers = _chart_cells(rounds=False)
    assert page == ["A", "B", "C"], page
    assert numbers == ["1", "2", "3"], numbers


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
         and v.__module__ == __name__]

if __name__ == "__main__":
    failures = 0
    for t in TESTS:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            print("FAIL", t.__name__, repr(exc))
            traceback.print_exc()
    print(f"{failures} failure(s)")
    sys.exit(1 if failures else 0)
