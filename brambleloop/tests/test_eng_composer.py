"""ENG-COMPOSER: original items composed from PROVEN primitives, with no new family engine.

Proves, with the real compiler, twin, assembly, reverse compiler, certificate and renderer:

* every primitive in `creative.composer.PRIMITIVES` names a proof that exists, and every shape
  validates (compiles, builds its twin, reverse-compiles US and UK, measures as its shape);
* a plan or concept the library cannot express is REFUSED by the missing primitive's name,
  never approximated, and an unexpressible concept files an `improve.ecr` change request;
* composition is deterministic, and no number of model proposals outvotes the validator;
* mutants of the composer (each a plausible bug) are killed by the deterministic chain;
* six ORIGINAL items run concept -> plan -> CIR -> compile/twin/reverse -> certify -> US and UK
  PDF: two amigurumi animals on shapes the amigurumi engine does not make (ovoid bodies, cones,
  folded-flat cylinders), a lamb lovey, a colour-blocked tote, a round cushion cover and a
  tablet sleeve; the beanie is refused by name (no sourced hat height or ease) and files a
  change request;
* a research concept runs through the real handlers (intake -> score -> cir.draft via the
  composer -> compile -> certify).

Every research source, proposal and children's assignment here is a TEST FIXTURE; no owner
decision is recorded or implied.

Run: cd brambleloop && python3 tests/test_eng_composer.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import copy
import dataclasses
import inspect
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.cir import assembly, geometry, reverse, writer  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.creative import composer as C  # noqa: E402
from brambleloop.creative import construction_families as CF  # noqa: E402
from brambleloop.gates import child_safety as CS  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.publish import pdf  # noqa: E402

PHYSICAL_ONLY = {"PHYSICAL_TEST_REQUIRED", "CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN"}
TOY = ("amigurumi_toy", "under_3")         # a TEST children's assignment, not an owner decision
LOVEY = ("lovey", "under_3")

# The six original items (and the refused seventh). Titles and palettes are Brambleloop's own.
ITEMS = {
    "owl": C.concept(slug="pebble-owl-amigurumi", title="Pebble Owl Amigurumi",
                     category="amigurumi", form="toy", subject="owl",
                     colours={"oat": "#D8C9B0", "bark": "#6B4E3D"}),
    "whale": C.concept(slug="harbour-whale-amigurumi", title="Harbour Whale Amigurumi",
                       category="amigurumi", form="toy", subject="whale",
                       colours={"sea": "#5E7F8F", "mist": "#D9E2E4"}),
    "lovey": C.concept(slug="meadow-lamb-lovey", title="Meadow Lamb Lovey", category="baby",
                       form="lovey", subject="lamb",
                       colours={"cream": "#F3EAD8", "sage": "#A9B79C"}),
    "tote": C.concept(slug="harvest-block-tote", title="Harvest Block Tote", category="bag",
                      form="tote", size="medium",
                      colours={"oat": "#E6DCC8", "rust": "#B5652B"}),
    "cushion": C.concept(slug="moonwell-round-cushion", title="Moonwell Round Cushion Cover",
                         category="pillow", form="round_cushion", size="16 in",
                         colours={"ink": "#2F3B4A", "cream": "#F3EAD8"}),
    "sleeve": C.concept(slug="slate-band-tablet-sleeve", title="Slate Band Tablet Sleeve",
                        category="case", form="sleeve", size="tablet",
                        colours={"slate": "#5B6770", "chalk": "#ECE8DF"}),
}
BEANIE = C.concept(slug="fireside-beanie", title="Fireside Beanie", category="hat",
                   form="beanie", colours={"ember": "#A0522D"})


def _composed(key: str) -> CIR:
    return C.compose(C.plan_for(ITEMS[key]))


def _codes(cert) -> set[str]:
    return {f.code for f in cert.findings if f.severity == "ERROR"}


def _db():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='engcomp_')}/c.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _plan(*parts, joins=(), colours=None, title="Composer Fixture Piece") -> dict:
    return {"slug": "composer-fixture", "title": title, "category": "fixture",
            "yarn_weight": "worsted", "colours": colours or {"MC": "#D8C9B0"},
            "parts": [dict(p) for p in parts], "joins": [dict(j) for j in joins]}


def _reverse_clean(cir: CIR) -> None:
    result = compile_cir(cir)
    assert result.ok, [f.message for f in result.findings if f.is_error]
    for terms in ("US", "UK"):
        text = writer.write_pattern(cir, result, terms)
        errors = [f for f in reverse.compare(cir, text, terms) if f.is_error]
        assert not errors, (cir.slug, terms, [(f.code, f.message) for f in errors][:3])


# ---- the library ------------------------------------------------------------------------------

SHAPE_SPECS = {
    "flat_circle": {"shape": "flat_circle", "diameter_cm": 12.0},
    "sphere": {"shape": "sphere", "diameter_cm": 9.0, "closure": "gathered"},
    "ovoid": {"shape": "ovoid", "width_cm": 9.0, "height_cm": 13.0, "closure": "gathered"},
    "cylinder": {"shape": "cylinder", "diameter_cm": 8.0, "length_cm": 10.0},
    "cone": {"shape": "cone", "base_cm": 6.0, "height_cm": 9.0},
    "tube": {"shape": "tube", "around_cm": 30.0, "length_cm": 8.0},
    "rectangle": {"shape": "rectangle", "width_cm": 20.0, "height_cm": 12.0},
    "trapezoid": {"shape": "trapezoid", "bottom_cm": 20.0, "top_cm": 12.0, "height_cm": 10.0},
    "triangle": {"shape": "triangle", "base_cm": 20.0, "height_cm": 12.0},
}


def test_every_primitive_names_a_proof_that_exists():
    here = {n for n, _ in inspect.getmembers(sys.modules[__name__], inspect.isfunction)}
    assert len(C.PRIMITIVES) >= 18, sorted(C.PRIMITIVES)
    for name, prim in C.PRIMITIVES.items():
        assert prim["kind"] in ("shape", "closure", "join", "detail"), name
        refs = [r.strip() for r in prim["proof"].split(";")]
        assert refs, name
        for ref in refs:
            path, _, fn = ref.partition("::")
            path = path.split(" (")[0]
            assert (ROOT / path).exists(), (name, path)
            fn = fn.split(" ")[0]
            if fn and path == C.COMPOSER_PROOF:
                assert fn in here, (name, fn)
    assert set(SHAPE_SPECS) == set(C.SHAPES)


def test_every_shape_primitive_validates():
    expected_geometry = {"flat_circle": geometry.DISC, "tube": geometry.TUBE,
                         "cylinder": geometry.VESSEL}
    measured = {}
    for shape, spec in SHAPE_SPECS.items():
        cir = C.compose(_plan({"name": "piece", **spec}))
        _reverse_clean(cir)
        result = compile_cir(cir)
        comp = cir.components[0]
        twin = build_twin(cir, result, component="piece")
        counts = [result.row("piece", r.index).stitch_count for r in comp.rows]
        assert counts, shape
        measured[shape] = (counts, twin)
        if shape in C.ROUND_SHAPES:
            rev = geometry.measure(comp, result, cir)
            assert not [f for f in rev.findings if f.is_error], (shape, rev.findings)
            if shape in expected_geometry:
                assert rev.shape == expected_geometry[shape], (shape, rev.shape)
            # No round gathers: the solver never asks the fabric to frill.
            assert not [f for f in rev.findings if f.code in ("ROUND_FRILL",)], shape
        if spec.get("closure") == "gathered":
            assert comp.closes and comp.stuff_at_round is not None, shape
            assert counts[-1] <= geometry.CLOSEABLE_STITCHES, shape
    # Solved from the gauge: each shape is the size its plan states, within one stitch/row.
    g = C._gauge("worsted")
    st, row = 10.0 / g.stitches_per_10cm, 10.0 / g.rows_per_10cm
    circle = max(measured["flat_circle"][0])
    assert abs(circle * st / 3.14159 - 12.0) <= 6 * st / 3.14159, circle
    rect = measured["rectangle"][1]
    assert abs(rect.width_cm - 20.0) <= st and abs(rect.height_cm - 12.0) <= row, rect
    trap = measured["trapezoid"][0]
    assert trap[0] > trap[-1] and abs(trap[-1] * st - 12.0) <= 2 * st, trap
    tri = measured["triangle"][0]
    assert tri[-1] == 2 and tri[0] > 20, tri
    # An ovoid of the same width as a sphere is taller: more even rounds, same widest count.
    sphere, ovoid = measured["sphere"][0], measured["ovoid"][0]
    assert max(sphere) == max(ovoid) and len(ovoid) > len(sphere), (sphere, ovoid)
    cone = measured["cone"][0]
    assert cone[0] == 6 and all(b >= a for a, b in zip(cone, cone[1:])), cone
    assert all(b - a <= 6 for a, b in zip(cone, cone[1:])), "one increase round at a time"


def test_join_as_you_go_is_placed_and_measured():
    body = {"name": "body", "shape": "cylinder", "diameter_cm": 10.0, "length_cm": 12.0}
    flap = {"name": "flap", "shape": "cylinder", "diameter_cm": 4.0, "length_cm": 4.0,
            "closure": "folded_flat", "make": 2}
    cir = C.compose(_plan(body, flap, joins=[{"kind": "join_as_you_go", "a": "flap",
                                             "b": "body", "at": 0.5, "mirrored": True}]))
    seam = cir.assembly[0]
    assert seam.method == "slst" and seam.at_round and seam.stitches_from_centre
    assert "join each flap as you go" in seam.note.lower()
    result = compile_cir(cir)
    twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
    assert assembly.assemble(cir, twins).verdict == "assembles"
    _reverse_clean(cir)
    # Moved by one stitch, it no longer meets the round it is joined into.
    bad = dataclasses.replace(cir, assembly=[dataclasses.replace(
        seam, stitches_from_centre=seam.stitches_from_centre + 2)])
    assert assembly.assemble(bad, twins).verdict == "does_not_assemble"
    # The printed placement is read back: a moved round is a reverse finding.
    text = writer.write_pattern(cir, result, "US")
    moved = text.replace(f"across round {seam.at_round},", f"across round {seam.at_round + 1},")
    assert moved != text
    assert "REVERSE_ASSEMBLY" in {f.code for f in reverse.compare(cir, moved, "US")}


def test_seamed_panels_are_measured():
    cir = _composed("sleeve")
    assert [s.method for s in cir.assembly] == ["mattress"] * 3
    result = compile_cir(cir)
    twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
    assert assembly.assemble(cir, twins).verdict == "assembles"
    # A back panel shorter than the front does not seam to it.
    plan = C.plan_for(ITEMS["sleeve"])
    plan["parts"][1]["height_cm"] = 14.0
    short = C.compose(plan)
    r2 = compile_cir(short)
    t2 = {c.name: build_twin(short, r2, component=c.name) for c in short.components}
    assert assembly.assemble(short, t2).verdict == "does_not_assemble"
    assert "ASSEMBLY_MISMATCH" in _codes(certify(short))
    # The rim join (round to round) is measured too.
    cushion = _composed("cushion")
    rc = compile_cir(cushion)
    tc = {c.name: build_twin(cushion, rc, component=c.name) for c in cushion.components}
    assert assembly.assemble(cushion, tc).verdict == "assembles"
    assert cushion.assembly[0].stuff_before_closing


def test_colour_blocks_and_edging():
    cir = _composed("tote")
    bag = cir.components[0]
    colours = [r.color for r in bag.rows]
    assert colours[-3:] == ["rust"] * 3, "the band edging is three contrast rounds at the rim"
    assert "rust" in colours[:-3] and colours[0] == "oat", "a contrast block below the rim"
    assert {m.color_id for m in cir.materials if m.color_id} == {"oat", "rust"}
    base = _plan({"name": "p", "shape": "rectangle", "width_cm": 10, "height_cm": 10,
                  "colour": "MC"}, colours={"MC": "#111111", "CC": "#EEEEEE"})
    try:
        C.compose(base)
    except C.ComposeRefused as exc:
        assert exc.primitive == "colour_blocks" and "CC" in exc.why
    else:
        raise AssertionError("a palette colour worked nowhere was accepted")
    overlap = copy.deepcopy(base)
    overlap["parts"][0]["blocks"] = [{"colour": "CC", "from": 0.0, "to": 0.6},
                                     {"colour": "CC", "from": 0.5, "to": 0.8}]
    assert any(p.startswith("colour_blocks") for p in C.validate(overlap))
    picot = copy.deepcopy(base)
    picot["parts"][0]["edging"] = {"colour": "CC", "rows": 1, "style": "picot"}
    assert any(p.startswith("band_edging") for p in C.validate(picot))


# ---- refusal by name -------------------------------------------------------------------------

def test_unexpressible_plans_are_refused_by_the_missing_primitive():
    cases = {
        "hexagon": _plan({"name": "p", "shape": "hexagon", "width_cm": 10}),
        "button_band": _plan({"name": "a", "shape": "rectangle", "width_cm": 10,
                              "height_cm": 10},
                             {"name": "b", "shape": "rectangle", "width_cm": 10,
                              "height_cm": 10},
                             joins=[{"kind": "button_band", "a": "a", "b": "b"}]),
        "gathered": _plan({"name": "p", "shape": "cylinder", "diameter_cm": 8,
                           "length_cm": 8, "closure": "gathered"}),
        "folded_flat": _plan({"name": "p", "shape": "sphere", "diameter_cm": 8,
                              "closure": "folded_flat"}),
        "ovoid": _plan({"name": "p", "shape": "ovoid", "width_cm": 10, "height_cm": 10,
                        "closure": "gathered"}),
        "bobble_texture": _plan({"name": "p", "shape": "rectangle", "width_cm": 10,
                                 "height_cm": 10}, title="Bobble Dishcloth"),
        "sewn": _plan({"name": "body", "shape": "cylinder", "diameter_cm": 5,
                       "length_cm": 5},
                      {"name": "wing", "shape": "cylinder", "diameter_cm": 8,
                       "length_cm": 4, "closure": "folded_flat", "make": 2},
                      joins=[{"kind": "sewn", "a": "wing", "b": "body", "at": 0.5,
                              "mirrored": True}]),
        "rectangle": _plan({"name": "p", "shape": "rectangle", "width_cm": 500,
                            "height_cm": 10}),
    }
    assert len(cases) >= 2, cases
    for primitive, plan in cases.items():
        try:
            C.compose(plan)
        except C.ComposeRefused as exc:
            assert exc.primitive == primitive, (primitive, exc.primitive, exc.why)
        else:
            raise AssertionError(f"{primitive}: an unexpressible plan was composed")


def test_unexpressible_concepts_are_refused_by_name_never_approximated():
    cases = {
        "graded_head_fit": BEANIE,
        "subject:hare": C.concept(slug="h", title="Meadow Hare Amigurumi", category="toy",
                                  form="toy", subject="hare", colours={"a": "#111111"}),
        "bobble_texture": C.concept(slug="b", title="Bobble Owl Amigurumi", category="toy",
                                    form="toy", subject="owl", colours={"a": "#111111"}),
        "template:blanket": C.concept(slug="t", title="Owl Blanket", category="blanket",
                                      form="blanket", colours={"a": "#111111"}),
        "hard_part": C.concept(slug="r", title="Owl Rattle Amigurumi", category="toy",
                               form="toy", subject="owl", colours={"a": "#111111"}),
    }
    assert len(cases) >= 2, cases
    for primitive, concept in cases.items():
        try:
            C.compose(C.plan_for(concept))
        except C.ComposeRefused as exc:
            assert exc.primitive == primitive, (primitive, exc.primitive)
        else:
            raise AssertionError(f"{primitive}: composed")
    # Read from a research title too: an accessory no subject carries is named.
    try:
        C.concept_from_text(slug="s", title="Owl Amigurumi with Scarf", category="toy",
                            colours={"a": "#111111"})
    except C.ComposeRefused as exc:
        assert exc.primitive.startswith("accessory:"), exc.primitive
    else:
        raise AssertionError("an accessory was composed")


def test_an_unexpressible_concept_files_an_engineering_change_request():
    from sqlalchemy import select

    from brambleloop.improve.self_models import EngineeringChangeRequest as E

    db = _db()
    got = C.route(BEANIE, db=db)
    assert got["route"] == "ecr" and got["primitive"] == "graded_head_fit", got
    assert got["family_hold"].startswith(CF.HOLD_PREFIX), got
    assert got["ecr"]["created"] is True
    again = C.route(dataclasses.replace(BEANIE) if dataclasses.is_dataclass(BEANIE) else
                    SimpleNamespace(**{**vars(BEANIE), "slug": "ember-beanie"}), db=db)
    assert again["ecr"]["id"] == got["ecr"]["id"] and again["ecr"]["created"] is False
    with db.session() as s:
        rows = list(s.scalars(select(E)))
        assert len(rows) == 1, rows
        row = rows[0]
        assert row.module == "creative.composer:graded_head_fit"
        assert row.defect_class == "missing_capability" and row.occurrences == 2
        assert set(row.evidence["examples"]) == {"fireside-beanie", "ember-beanie"}
    # An expressible concept no engine admits is composed, not requested.
    owl = C.route(ITEMS["owl"], db=db)
    assert owl["route"] == "composer" and owl["cir"].components[0].name == "body", owl
    assert owl["family_hold"].startswith(CF.HOLD_PREFIX)


# ---- determinism and the validator's authority ------------------------------------------------

def test_composition_is_deterministic():
    assert len(ITEMS) == 6
    for key in ITEMS:
        a, b = _composed(key), _composed(key)
        assert a.to_dict() == b.to_dict() and a.fingerprint == b.fingerprint, key
        plan = C.plan_for(ITEMS[key])
        shuffled = dict(reversed(list(plan.items())))
        assert C.plan_digest(plan) == C.plan_digest(shuffled), key
        assert C.compose(shuffled).fingerprint == a.fingerprint, key


def test_model_proposals_cannot_outvote_the_validator():
    good = C.plan_for(ITEMS["sleeve"])
    bad_shape = copy.deepcopy(good)
    bad_shape["parts"][0]["shape"] = "heart"
    bad_seam = copy.deepcopy(good)
    bad_seam["parts"][1]["height_cm"] = 14.0       # does not seam: refused at certify below
    unbuilt = copy.deepcopy(good)
    unbuilt["joins"].append({"kind": "zip", "a": "front", "b": "back"})
    # Three "models" agree on an invalid plan; the validator refuses each.
    out = C.adjudicate([bad_shape, bad_shape, unbuilt, good])
    assert out["plan"] is good and len(out["refused"]) == 3, out["refused"]
    assert {r.split(":")[0] for _, r in out["refused"]} == {"heart", "zip"}
    none = C.adjudicate([bad_shape, unbuilt])
    assert none["cir"] is None and len(none["refused"]) == 2
    # A plan that composes but does not assemble is still refused by the certificate.
    assert "ASSEMBLY_MISMATCH" in _codes(certify(C.adjudicate([bad_seam])["cir"]))


# ---- mutation tests: each mutant is a plausible composer bug the chain must kill --------------

def _mutant(name, value):
    original = getattr(C, name)
    setattr(C, name, value)
    return lambda: setattr(C, name, original)


def test_mutants_of_the_composer_are_killed():
    killed = []
    # M1: the stuffing point solver picks a round before the widest (or none).
    orig_build = C.build_part

    def no_stuffing(spec, gauge):
        comp, facts = orig_build(spec, gauge)
        if comp.closes:
            comp = dataclasses.replace(comp, stuff_at_round=comp.rows[1].index)
        return comp, facts
    undo = _mutant("build_part", no_stuffing)
    try:
        C.compose(C.plan_for(ITEMS["owl"]))
    except C.ComposeRefused as exc:
        assert "STUFFING_POINT" in exc.why
        killed.append("M1")
    finally:
        undo()
    # M2: the small-parts clearance solver is skipped.
    undo = _mutant("clear_diameter_cm", lambda gauge, step=12: 0.1)
    try:
        cir = C.compose(C.plan_for(ITEMS["owl"]))
        if "CHILD_SAFETY_SMALL_PARTS" in _codes(certify(cir)):
            killed.append("M2")
    finally:
        undo()
    # M3: folded pieces are solved in 6-st wedges, so a flattened edge can be odd.
    orig_ring = C._sc_ring
    undo = _mutant("_sc_ring", lambda cm, gauge, step=6: orig_ring(cm, gauge, 6) + 6
                   if step == 12 and orig_ring(cm, gauge, 6) % 12 == 0 else orig_ring(cm, gauge, 6))
    try:
        C.compose(C.plan_for(ITEMS["whale"]))
    except C.ComposeRefused as exc:
        assert "cannot be centred" in exc.why
        killed.append("M3")
    finally:
        undo()
    # M4: the size note is typed, not measured.
    undo = _mutant("size_note", lambda cir, twins, plan:
                   "The front is about 40.0 cm wide and about 40.0 cm tall.")
    try:
        if not certify(C.compose(C.plan_for(ITEMS["sleeve"]))).granted:
            killed.append("M4")
    finally:
        undo()
    # M5: the seam's span is off by one stitch pair.
    orig_seams = C._join_seams

    def off_by_one(plan, comps, facts):
        seams, problems = orig_seams(plan, comps, facts)
        return [dataclasses.replace(s, stitches_from_centre=s.stitches_from_centre + 1)
                if s.stitches_from_centre else s for s in seams], problems
    undo = _mutant("_join_seams", off_by_one)
    try:
        if "ASSEMBLY_MISMATCH" in _codes(certify(C.compose(C.plan_for(ITEMS["tote"])))):
            killed.append("M5")
    finally:
        undo()
    # M6: validation is bypassed, so an unknown shape reaches the builders.
    undo = _mutant("validate", lambda plan: [])
    try:
        C.compose(_plan({"name": "p", "shape": "hexagon", "width_cm": 10}))
    except C.ComposeRefused as exc:
        assert exc.primitive == "hexagon"
        killed.append("M6")
    except KeyError:
        pass        # survived as a crash, not a named refusal: not killed
    finally:
        undo()
    # M7: a counted row is edited after composition -- the compiler refuses it.
    cir = _composed("owl")
    row = cir.components[0].rows[5]
    cir.components[0].rows[5] = dataclasses.replace(row, declared_count=row.declared_count + 1)
    if not compile_cir(cir).ok:
        killed.append("M7")
    assert killed == ["M1", "M2", "M3", "M4", "M5", "M6", "M7"], killed


# ---- proof by example: six original items, concept -> PDF -------------------------------------

def _decided_not_for_a_child(cir):
    from test_eng_plush import _decided_not_for_a_child as decide

    return decide(cir)


def _end_to_end(key: str) -> dict:
    concept = ITEMS[key]
    plan = C.plan_for(concept)
    assert not C.validate(plan), C.validate(plan)
    cir = C.compose(plan)
    assert cir.provenance and cir.provenance.generated_by == "brambleloop"
    assert all(p.startswith(C.COMPOSER) for p in cir.provenance.primitives_used)
    result = compile_cir(cir)
    assert result.ok
    certs = {t: certify(cir, terminology=t) for t in ("US", "UK")}
    for terms, cert in certs.items():
        for stage in ("compile", "twin", "assembly", "write", "reverse", "originality"):
            assert stage in cert.stages_run, (key, terms, stage)
        assert not {c for c in _codes(cert) if c.startswith(("REVERSE", "OBJECT_SIZE",
                                                              "TWIN", "ASSEMBLY"))}, \
            (key, terms, _codes(cert))
        assert cert.granted or _codes(cert) <= PHYSICAL_ONLY, (key, terms, _codes(cert))
    childrens = None
    undo = None
    if CS.applies(cir):
        childrens = LOVEY if key == "lovey" else TOY
    elif key == "cushion":
        undo = _decided_not_for_a_child(cir)
    try:
        texts = {}
        for terms in ("US", "UK"):
            doc = pdf.build_pattern_pdf(cir, terminology=terms, childrens=childrens)
            text = pdf.extracted_text(doc.pdf_bytes)
            texts[terms] = text
            for comp in cir.components:
                for row in comp.rows:
                    count = result.row(comp.name, row.index).stitch_count
                    assert f"({count} sts)" in text, (key, terms, comp.name, row.index)
            if len(cir.components) > 1:
                assert "Parts and joins" in text, (key, terms)
            if childrens:
                assert CS.SECTION_HEADING in text, (key, terms)
                v = CS.evaluate(cir, result, text=text, childrens=childrens,
                                instructions=writer.write_pattern(cir, result, terms))
                assert [c.code for c in v.checks if c.state != CS.PASS] == \
                    ["PHYSICAL_EVIDENCE"], (key, v.to_dict())
        assert "single crochet" in texts["US"] and "double crochet" in texts["UK"]
    finally:
        if undo:
            undo()
    return {"cir": cir, "certs": certs}


def test_composed_owl_with_ovoid_body_cones_and_folded_wings_certifies_to_pdf():
    out = _end_to_end("owl")
    cir = out["cir"]
    shapes = {p["name"]: p["shape"] for p in C.plan_for(ITEMS["owl"])["parts"]}
    assert shapes == {"body": "ovoid", "wing": "cylinder", "ear tuft": "cone"}
    assert not out["certs"]["US"].granted, "a stuffed toy waits for its physical sample"
    assert cir.risk_class == "C"


def test_composed_whale_with_a_cone_tail_certifies_to_pdf():
    out = _end_to_end("whale")
    names = [c.name for c in out["cir"].components]
    assert names == ["body", "fin", "tail"], names
    tail = next(s for s in out["cir"].assembly if s.piece_a == "tail")
    assert not tail.mirrored and "back" in tail.note


def test_composed_teether_free_lamb_lovey_certifies_to_pdf():
    out = _end_to_end("lovey")
    cir = out["cir"]
    assert [c.name for c in cir.components] == ["square", "head", "ear"]
    assert any(s.edge_b == "surface" for s in cir.assembly)
    text = " ".join(m.name for m in cir.materials).lower()
    assert "teether" not in text and "rattle" not in text


def test_composed_tote_is_granted_and_renders():
    out = _end_to_end("tote")
    assert out["certs"]["US"].granted and out["certs"]["UK"].granted


def test_composed_round_cushion_is_physical_gated_and_renders():
    out = _end_to_end("cushion")
    assert _codes(out["certs"]["US"]) == {"PHYSICAL_TEST_REQUIRED"}
    assert [c.name for c in out["cir"].components] == ["front", "back"]


def test_composed_tablet_sleeve_is_granted_and_renders():
    out = _end_to_end("sleeve")
    assert out["certs"]["US"].granted and out["certs"]["UK"].granted


def test_the_beanie_is_refused_by_name_and_files_a_request():
    db = _db()
    got = C.route(BEANIE, db=db)
    assert got["route"] == "ecr" and got["primitive"] == "graded_head_fit"
    assert "circumference only" in got["why"]
    assert CF.route(category="hat", title="Fireside Beanie", form="hat",
                    construction="in_the_round")["admitted"] is False


# ---- routing and the real handlers -------------------------------------------------------------

def test_the_router_admits_composer_concepts_and_keeps_every_hold():
    probes = {
        ("amigurumi", "toy", "amigurumi_shaping", "Pebble Owl Amigurumi"): True,
        ("baby", "toy", "amigurumi_shaping", "Meadow Lamb Lovey"): True,
        ("bag", "bag", "in_the_round", "Harvest Block Tote"): True,
        ("pillow", "pillow", "flat_rows", "Moonwell Round Cushion Cover"): True,
        ("case", "case", "flat_rows", "Slate Band Tablet Sleeve"): True,
        ("toy", "toy", "amigurumi_shaping", "Meadow Hare"): False,
        ("toy", "toy", "amigurumi_shaping", "Cable Owl Amigurumi"): False,
        ("toy", "toy", "amigurumi_shaping", "Fluffy Owl Amigurumi"): False,
        ("bag", "bag", "in_the_round", "Lined Market Tote"): False,
        ("hat", "hat", "in_the_round", "Fireside Beanie"): False,
    }
    assert len(probes) >= 4, probes
    for (cat, form, constr, title), admitted in probes.items():
        got = CF.route(category=cat, title=title, form=form, construction=constr)
        assert got["admitted"] is admitted, (title, got)
        if admitted:
            assert got["family"] in (CF.COMPOSER, "lovey", "amigurumi"), (title, got)
        else:
            assert got["reason"].startswith(CF.HOLD_PREFIX), (title, got)
    # The existing engines keep their concepts: the composer never takes an admitted one.
    assert CF.route(category="toy", title="Ball Bear Amigurumi", form="toy",
                    construction="amigurumi_shaping")["family"] == "amigurumi"
    assert CF.FAMILIES[CF.COMPOSER].status == CF.PHYSICAL_GATE


def test_a_research_composer_concept_runs_concept_to_pdf():
    """Real handlers: intake -> score -> cir.draft (composer) -> compile -> certify -> PDF."""
    from test_eng_families import _certify_research_concept, _proposal

    proposal = _proposal("pebble-owl-amigurumi", "Pebble Owl Amigurumi", "amigurumi",
                         form="toy", construction="amigurumi_shaping", motif="plain owl",
                         pod="home_decor", function="a soft keepsake to hold",
                         palette_story="oat and bark", recipient="host",
                         premise="A plain owl worked in oat with an embroidered face")
    out = _certify_research_concept(proposal)
    assert out["drafted"]["construction"] == "composer", out["drafted"]
    assert out["compiled"]["compiled"] is True
    codes = sorted({r.split(":")[0].split()[-1] for r in out["certified"]["reasons"]})
    assert codes == sorted(PHYSICAL_ONLY), out["certified"]["reasons"]
    cir = CIR.from_dict(out["cir"])
    assert cir.provenance.primitives_used[0] == C.COMPOSER
    for terms in ("US", "UK"):
        doc = pdf.build_pattern_pdf(cir, terminology=terms, childrens=TOY)
        assert doc.pdf_bytes[:4] == b"%PDF"


def test_a_research_composer_tote_is_granted_through_the_real_handlers():
    from test_eng_families import (_assert_certified_end_to_end, _certify_research_concept,
                                   _proposal)

    proposal = _proposal("harvest-block-tote", "Harvest Block Tote", "bag", form="bag",
                         construction="in_the_round", motif="harvest band",
                         function="carries the market shop",
                         premise="A round-based market tote with a rust band at the rim")
    out = _certify_research_concept(proposal)
    assert out["drafted"]["construction"] == "composer", out["drafted"]
    _assert_certified_end_to_end(out)


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                import traceback

                traceback.print_exc()
                print(f"FAIL {name} {exc!r}")
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)


def test_a_malformed_proposal_is_refused_by_name_and_adjudication_continues():
    """b18-c A2: make="two", a block from="x", and a part that is not a dict are each a named
    ComposeRefused, and adjudicate() moves on to the next proposal."""
    import copy

    good = C.plan_for(ITEMS["owl"])
    bad_make = copy.deepcopy(good)
    bad_make["parts"][0]["make"] = "two"
    bad_from = copy.deepcopy(good)
    for part in bad_from["parts"]:
        if part.get("blocks"):
            part["blocks"][0]["from"] = "x"
            break
    else:
        bad_from["parts"][0]["blocks"] = [{"from": "x"}]
    bad_parts = copy.deepcopy(good)
    bad_parts["parts"] = ["body"]
    probes = {"make": bad_make, "from": bad_from, "parts": bad_parts}
    assert len(probes) == 3
    for name, plan in probes.items():
        try:
            C.compose(plan)
        except C.ComposeRefused as exc:
            assert exc.primitive, (name, exc.why)
        else:
            raise AssertionError(f"{name}: a malformed plan was composed")
    got = C.adjudicate([bad_make, bad_from, bad_parts, good])
    assert got["cir"] is not None and got["plan"] is good, got["refused"]
    assert [i for i, _ in got["refused"]] == [0, 1, 2], got["refused"]
