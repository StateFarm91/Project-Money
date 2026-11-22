"""ENG-AMIGURUMI-BREADTH: shaped low-sew animals and the lamb lovey, under the child-safety gate.

Proves, with the real handlers and the real renderer:

* a research-derived low-sew frog is admitted -> drafted as one closed head-and-body piece with
  arms and legs crocheted in through flattened edges -> compiled -> twin -> reverse-compiled ->
  certified, and certification withholds ONLY for the physical evidence a stuffed toy requires;
  its US and UK PDFs print every joining round, the crocheted-in joins statement and the
  child-safety section;
* every animal in `creative.animals.ANIMALS` compiles clean, its twin carries every joined run
  at the stitch count of the joined piece's flattened edge, the assembly geometry records each
  as a sound join, and the US and UK documents reverse-compile to the same structure;
* `cir.low_sew` refuses every defect it exists for (each a mutation of a drafted animal), the
  reverse compiler refuses a document that lost or renamed a join, and the child-safety gate
  and the small-parts cylinder read a crocheted-in piece exactly like a sewn one;
* routing admits the buildable animals and holds the rest by name;
* a research-derived sleepy lamb lovey is physical-gated end to end.

Every research source and judgement here is a TEST FIXTURE. The children's assignment passed
to the renderer is a TEST argument; no owner decision is recorded or implied.

Run: cd brambleloop && python3 tests/test_eng_animals.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import copy
import dataclasses
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.cir import assembly, low_sew, reverse, writer  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR, Op, Repeat, Seam  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.creative import animals as A  # noqa: E402
from brambleloop.creative import construction_families as CF  # noqa: E402
from brambleloop.creative import fallback_constructions as FC  # noqa: E402
from brambleloop.gates import child_safety as CS  # noqa: E402
from brambleloop.gates import small_parts  # noqa: E402
from brambleloop.publish import pdf  # noqa: E402

TOY = ("amigurumi_toy", "under_3")          # a TEST assignment, not an owner decision
COLOURS = {"MC": "#6E8B4E", "CC": "#EFE6D2"}


def _title(kind: str) -> str:
    return f"{'Chunky ' if A.ANIMALS[kind].chunky_only else ''}Low-Sew {kind.title()} Amigurumi"


def _animal(kind: str = "frog", weight: str = "worsted") -> CIR:
    return A.build(SimpleNamespace(slug=f"fx-{kind}", title=_title(kind), category="amigurumi",
                                   colors=dict(COLOURS), yarn_weight=weight))


def _errors(cir) -> set[str]:
    return {f.code for f in compile_cir(cir).findings if f.is_error}


def _host_row(cir, piece: str):
    body = next(c for c in cir.components if c.name == "body")
    return next(r for r in body.rows if any(getattr(o, "joins", None) == piece
                                           for o in low_sew._ops(r.ops)))


# ---- the end-to-end proof ----------------------------------------------------------------------


def _frog_proposal():
    from test_eng_families import _proposal

    return _proposal("puddle-hop-frog-fixture", "Low-Sew Puddle Frog Amigurumi", "amigurumi",
                     form="toy", construction="amigurumi_shaping", motif="pond frog",
                     pod="home_decor", function="a rainy-day companion",
                     palette_story="moss and cream", recipient="child",
                     premise="A chunky low-sew frog with limbs worked into the body rounds "
                             "and an embroidered face")


def test_a_research_animal_is_physical_gated_end_to_end():
    """admit -> CIR -> compile -> twin -> reverse -> certify -> US/UK PDF, real handlers."""
    from test_eng_families import _certify_research_concept

    out = _certify_research_concept(_frog_proposal())
    assert out["drafted"]["construction"] == FC.AMIGURUMI_ANIMAL, out["drafted"]
    cir = CIR.from_dict(out["cir"])
    assert [c.name for c in cir.components] == ["body", "arm", "leg"]
    assert cir.assembly == [], "nothing is sewn on: every part is crocheted in"
    body = cir.components[0]
    assert "make the arms and legs below" in body.note, body.note
    assert body.closes and body.stuff_at_round is not None
    assert low_sew.joined_pieces(cir) == ["arm", "leg"]
    assert out["compiled"]["compiled"] is True
    cert = out["certified"]
    assert cert["granted"] is False
    codes = sorted({r.split(":")[0].split()[-1] for r in cert["reasons"]})
    # Withheld ONLY for physical evidence: every computable check passed.
    assert codes == ["CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN"], \  # D-OWNER-NO-SAMPLE-SIZING: Class C sizes from standard gauge; child safety still holds
        cert["reasons"]
    stages = out["certificate"].get("stages_run") or []
    for stage in ("compile", "twin", "assembly", "reverse", "child_safety"):
        assert stage in stages or not stages, (stage, stages)
    result = compile_cir(cir)
    for terms in ("US", "UK"):
        doc = pdf.build_pattern_pdf(cir, terminology=terms, childrens=TOY)
        text = pdf.extracted_text(doc.pdf_bytes)
        flat = " ".join(text.split())
        for comp in cir.components:
            for row in comp.rows:
                count = result.row(comp.name, row.index).stitch_count
                assert f"({count} sts)" in text, (terms, comp.name, row.index)
        for piece in ("arm", "leg"):
            assert f"{writer.JOIN_PHRASE} {piece}" in flat, (terms, piece)
        assert f"Stuff after Rnd {body.stuff_at_round}" in text, terms
        assert f"Close after Rnd {body.rows[-1].index}" in text, terms
        assert CS.SECTION_HEADING in text and CS.SECTION_END in text
        assert " ".join(CS.STATEMENTS["low_sew_joins"].marker.split()) in flat, terms
        verdict = CS.evaluate(cir, result, text=text, childrens=TOY,
                              instructions=writer.write_pattern(cir, result, terms))
        states = {c.code: c.state for c in verdict.checks}
        assert verdict.verdict == CS.VERDICT_HELD, states
        assert [c for c, s in states.items() if s != CS.PASS] == ["PHYSICAL_EVIDENCE"], states
        assert "joined_in" in verdict.profile, verdict.profile
    try:
        pdf.build_pattern_pdf(cir)
    except pdf.ChildrensDecisionRequired:
        pass
    else:
        raise AssertionError("a drafted toy rendered with no children's decision")


# ---- every animal: compiler, twin, assembly, reverse ---------------------------------------


def test_every_animal_compiles_twins_and_reverse_round_trips():
    for kind in A.ANIMALS:
        cir = _animal(kind)
        result = compile_cir(cir)
        assert result.ok, (kind, [str(f) for f in result.errors])
        comps = {c.name: c for c in cir.components}
        sites = low_sew.all_sites(cir, result)
        assert sites, kind
        for name in low_sew.joined_pieces(cir):
            mine = [s for s in sites if s.piece == name]
            assert len(mine) == comps[name].make, (kind, name, mine)
            assert all(s.width == comps[name].rows[-1].declared_count // 2 for s in mine), mine
        twins = {c.name: build_twin(cir, result, c.name) for c in cir.components}
        geo = assembly.assemble(cir, twins)
        joins = [j for j in geo.joins if j.method == low_sew.METHOD]
        assert len(joins) == sum(comps[n].make for n in low_sew.joined_pieces(cir)), kind
        assert all(j.verdict == "sound" for j in joins), [j.why for j in joins]
        assert geo.verdict == "assembles", (kind, geo.verdict, geo.why)
        for terms in ("US", "UK"):
            text = writer.write_pattern(cir, result, terms)
            assert reverse.compare(cir, text, terms) == [], (kind, terms)
        # The CIR round-trips through its dict with every join intact.
        again = CIR.from_dict(cir.to_dict())
        assert again.to_dict() == cir.to_dict()
        assert low_sew.joined_pieces(again) == low_sew.joined_pieces(cir)
        # The child-safety gate reads every crocheted-in piece; only physical evidence holds.
        states = {c.code: c.state for c in CS.evaluate(cir, result).checks}
        assert [c for c, s in states.items() if s != CS.PASS] == ["PHYSICAL_EVIDENCE"], \
            (kind, states)


def test_a_ball_toy_digest_is_unchanged_by_the_new_field():
    """`Op.joins` is omitted from `to_dict` when None, so no existing digest moves."""
    toy = FC.amigurumi(SimpleNamespace(slug="b", title="Ball Bear Amigurumi",
                                       category="amigurumi", colors={"MC": "#D8C9B0"},
                                       yarn_weight="worsted"))
    assert "joins" not in str(toy.to_dict())


# ---- cir.low_sew: every defect it exists for ------------------------------------------------


def _mutate(kind, fn):
    cir = copy.deepcopy(_animal(kind))
    fn(cir)
    return _errors(cir)


def _set_op(cir, piece, **change):
    row = _host_row(cir, piece)
    for i, op in enumerate(row.ops):
        if isinstance(op, Op) and op.joins == piece:
            row.ops[i] = dataclasses.replace(op, **change)
            return row, i
    raise AssertionError(piece)


def test_an_edge_that_does_not_match_its_round_is_refused():
    def short(cir):
        row, i = _set_op(cir, "arm", count=8)
        row.ops.insert(i + 1, Op("sc", 1))      # keep the round's count; the run is short
    assert "LOW_SEW_EDGE_MISMATCH" in _mutate("frog", short)

    def long(cir):
        row, i = _set_op(cir, "arm", count=10)
        nxt = row.ops[i + 1]
        row.ops[i + 1] = dataclasses.replace(nxt, count=nxt.count - 1)
    assert "LOW_SEW_EDGE_MISMATCH" in _mutate("frog", long)


def test_a_piece_joined_a_different_number_of_times_than_it_is_made_is_refused():
    def one_arm(cir):
        _set_op(cir, "arm", joins=None)
    assert "LOW_SEW_JOIN_COUNT" in _mutate("frog", one_arm)

    def three_made(cir):
        arm = next(c for c in cir.components if c.name == "arm")
        arm.make = 3
    assert "LOW_SEW_JOIN_COUNT" in _mutate("frog", three_made)


def test_unknown_unflattenable_and_wrong_stitch_joins_are_refused():
    assert "LOW_SEW_UNKNOWN_PIECE" in _mutate("frog", lambda c: _set_op(c, "arm", joins="wing"))
    assert "LOW_SEW_UNKNOWN_PIECE" in _mutate("frog", lambda c: _set_op(c, "arm", joins="body"))

    def odd(cir):
        arm = next(c for c in cir.components if c.name == "arm")
        last = arm.rows[-1]
        arm.rows.append(dataclasses.replace(last, index=last.index + 1,
                                            ops=[Op("sc", 17), Op("sk", 1)],
                                            declared_count=17, allow_remainder=True))
    assert "LOW_SEW_EDGE_NOT_FLAT" in _mutate("frog", odd) or \
        "LOW_SEW_EDGE_MISMATCH" in _mutate("frog", odd)

    def gathered(cir):
        next(c for c in cir.components if c.name == "arm").closes = True
    assert "LOW_SEW_EDGE_NOT_FLAT" in _mutate("frog", gathered)

    assert "LOW_SEW_STITCH" in _mutate("frog", lambda c: _set_op(c, "arm", loop="back"))
    assert "LOW_SEW_STITCH" in _mutate("frog", lambda c: _set_op(c, "arm", stitch="hdc"))

    def also_sewn(cir):
        cir.assembly.append(Seam("whipstitch", "arm", "body", edge_a="top", edge_b="top",
                                 at_round=10, note="sew through both loops and bury the tail"))
    assert "LOW_SEW_ALSO_SEWN" in _mutate("frog", also_sewn)


def test_the_ring_layout_is_validated_too():
    def seven(cir):
        row = _host_row(cir, "leg")
        rep = row.ops[0]
        assert isinstance(rep, Repeat)
        row.ops = [Repeat(rep.ops, times=7), Op("sc", 9)]
    assert "LOW_SEW_JOIN_COUNT" in _mutate("octopus", seven)


def test_mutant_without_the_low_sew_check_compiles_a_short_edge_clean():
    """The checks are load-bearing: with `low_sew.check` stubbed out, a short edge compiles."""
    def short(cir):
        row, i = _set_op(cir, "arm", count=8)
        row.ops.insert(i + 1, Op("sc", 1))
    real = low_sew.check
    low_sew.check = lambda cir, result, findings: None
    try:
        assert "LOW_SEW_EDGE_MISMATCH" not in _mutate("frog", short)
    finally:
        low_sew.check = real
    assert "LOW_SEW_EDGE_MISMATCH" in _mutate("frog", short)


# ---- the reverse compiler reads every join back ---------------------------------------------


def test_the_reverse_compiler_refuses_a_lost_or_renamed_join():
    cir = _animal("lamb")
    result = compile_cir(cir)
    for terms in ("US", "UK"):
        text = writer.write_pattern(cir, result, terms)
        assert reverse.compare(cir, text, terms) == []
        lost = text.replace(f" {writer.JOIN_PHRASE} leg", "", 1)
        assert "REVERSE_MISMATCH" in {f.code for f in reverse.compare(cir, lost, terms)}
        renamed = text.replace(f"{writer.JOIN_PHRASE} ear", f"{writer.JOIN_PHRASE} leg", 1)
        assert "REVERSE_MISMATCH" in {f.code for f in reverse.compare(cir, renamed, terms)}
    p = reverse._parse_op("sc in next 9 sts through both layers of the leg with CC", "US")
    assert (p.stitch, p.count, p.joins, p.color) == ("sc", 9, "leg", "CC")


# ---- child safety and the small-parts cylinder ----------------------------------------------


def test_crocheted_in_pieces_are_inside_the_small_parts_and_joins_checks():
    cir = _animal("capybara")
    assert set(small_parts._sewn_on(cir)) >= {"ear", "leg"}
    assert small_parts.blocking(cir) == []
    profile = CS.profile_for(cir)
    assert "joined_in" in profile and "low_sew_joins" in CS.required_statements(profile)
    # A mismatched join FAILS the gate's joins check (never a silent pass).
    bad = copy.deepcopy(cir)
    row, i = _set_op(bad, "leg", count=8)
    row.ops.insert(i + 1, Op("sc", 1))
    states = {c.code: c.state for c in CS.evaluate(bad).checks}
    assert states["JOINS_VALIDATED"] != CS.PASS, states
    # An appendage that shrinks into the cylinder is refused at draft and blocked by the gate.
    small = copy.deepcopy(cir)
    leg = next(c for c in small.components if c.name == "leg")
    leg.rows = leg.rows[:2]                           # a 12-st leg: about 31 mm across
    assert any("leg" in b for b in small_parts.blocking(small)), small_parts.blocking(small)
    assert {c.code: c.state for c in CS.evaluate(small).checks}["SMALL_PARTS"] != CS.PASS


def test_features_are_embroidered_only_and_a_finer_yarn_is_refused():
    cir = _animal("duckling")
    text = writer.write_pattern(cir, compile_cir(cir), "US").lower()
    assert "embroider" in text
    for word in ("safety eye", "button", "bead", "bell", "pellet"):
        assert word not in text, word
    for weight in ("dk", "fingering", "sport"):
        try:
            _animal("duckling", weight)
        except ValueError as exc:
            assert "small-parts" in str(exc), exc
        else:
            raise AssertionError(f"a duckling drafted at {weight}")
    try:
        A.build(SimpleNamespace(slug="o", title="Low-Sew Octopus Amigurumi",
                                category="amigurumi", colors=dict(COLOURS),
                                yarn_weight="worsted"))
    except ValueError:
        pass
    else:
        raise AssertionError("an octopus drafted without chunky yarn")


# ---- routing ---------------------------------------------------------------------------------


def test_routing_admits_the_buildable_animals_and_holds_the_rest_by_name():
    for title in ("Low-Sew Puddle Frog Amigurumi", "Riverbank Capybara Amigurumi",
                  "Chunky Marsh Duckling Plush", "Low-Sew Meadow Lamb Amigurumi",
                  "Chunky Harbour Whale Plush", "Chunky Tidepool Octopus Plush",
                  "Sleepy Otter Amigurumi", "Clover Cow Amigurumi", "Dinosaur Plush"):
        got = CF.route(category="amigurumi", title=title, form="toy",
                       construction="amigurumi_shaping",
                       premise="an original animal with its parts worked into the body")
        assert got == {"admitted": True, "family": FC.AMIGURUMI_ANIMAL,
                       "status": CF.PHYSICAL_GATE, "reason": ""}, (title, got)
    held = {
        "Low-Sew Pond Axolotl Amigurumi": "gills", "Hedgerow Hedgehog Amigurumi": "spines",
        "Fluffy Frog Amigurumi": "texture", "No-Sew Frog Amigurumi": "no-sew",
        "Mini Whale Plush": "size", "Two Frogs Amigurumi": "more than one",
        "Frog And Duck Amigurumi": "more than one", "Octopus Plush": "chunky",
        "Frog Amigurumi With Safety Eyes": "safety", "Rainbow Frog Amigurumi": "rainbow",
        "Woodland Fox Amigurumi": "Woodland Fox",
    }
    for title, word in held.items():
        got = CF.route(category="amigurumi", title=title, form="toy",
                       construction="amigurumi_shaping")
        assert not got["admitted"] and got["reason"].startswith(CF.HOLD_PREFIX), (title, got)
        assert word in got["reason"], (title, word, got["reason"])
    for premise, word in (("an otter holding a little stone", "holding"),
                          ("a cow with colourwork patches", "patches"),
                          ("a dinosaur with spikes along the back", "spikes"),
                          ("a frog with safety eyes", "safety eye")):
        got = CF.route(category="amigurumi", title="Low-Sew Frog Amigurumi", form="toy",
                       construction="amigurumi_shaping", premise=premise)
        assert not got["admitted"] and word in got["reason"], (premise, got)
    # The ball-body toy keeps its own route and refusals.
    assert CF.route(category="amigurumi", title="Ball Bear Amigurumi", form="toy",
                    construction="amigurumi_shaping")["family"] == FC.AMIGURUMI
    got = CF.route(category="amigurumi", title="Meadow Hare", form="toy",
                   construction="amigurumi_shaping")
    assert not got["admitted"] and got["reason"].startswith("construction_unsupported:amigurumi")
    fam = CF.FAMILIES[FC.AMIGURUMI_ANIMAL]
    assert fam.status == CF.PHYSICAL_GATE and fam.proof.split("::")[1] in globals()


def test_every_demand_catalogue_toy_is_routed_or_held_by_a_named_feature():
    from brambleloop.radar.demand_originals import CATALOGUE

    admitted = set()
    for o in CATALOGUE:
        if o.category != "amigurumi":
            continue
        got = CF.route(category=o.category, title=o.title, form=o.form,
                       construction=o.construction, slug=o.slug, premise=o.premise)
        if got["admitted"]:
            admitted.add(o.slug)
        else:
            assert got["reason"].startswith(CF.HOLD_PREFIX), (o.slug, got)
    assert {"low-sew-puddle-frog-amigurumi", "riverbank-capybara-amigurumi",
            "chunky-marsh-duckling-plush", "low-sew-meadow-lamb-amigurumi",
            "chunky-harbour-whale-plush", "chunky-tidepool-octopus-plush",
            "cosy-round-bear-amigurumi", "simple-round-teddy-bear"} <= admitted, admitted
    for slug in ("low-sew-pond-axolotl-amigurumi", "low-sew-hedgerow-hedgehog-amigurumi",
                 "chunky-riverstone-otter-plush", "low-sew-clover-cow-amigurumi",
                 "low-sew-fernback-dinosaur-amigurumi"):
        assert slug not in admitted, slug


# ---- nursery: the sleepy lamb lovey ---------------------------------------------------------


def test_a_research_lamb_lovey_is_physical_gated_end_to_end():
    from test_eng_families import _certify_research_concept, _proposal

    proposal = _proposal("dove-sleepy-lamb-lovey", "Sleepy Lamb Lovey", "baby", form="toy",
                         construction="amigurumi_shaping", motif="sleepy lamb head",
                         recipient="new_parent", function="a soft square to hold",
                         palette_story="cream and dove",
                         premise="A sleepy lamb head with closed stitched eyes on a soft "
                                 "square, embroidered face")
    out = _certify_research_concept(proposal)
    assert out["drafted"]["construction"] == FC.LOVEY, out["drafted"]
    cir = CIR.from_dict(out["cir"])
    codes = sorted({r.split(":")[0].split()[-1] for r in out["certified"]["reasons"]})
    assert codes == ["CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN"], \  # D-OWNER-NO-SAMPLE-SIZING: Class C sizes from standard gauge; child safety still holds
        out["certified"]["reasons"]
    lovey = ("lovey", "under_3")                         # a TEST assignment
    result = compile_cir(cir)
    ear = next(c for c in cir.components if c.name == "ear")
    assert len(ear.rows) == 4 + 4, [r.declared_count for r in ear.rows]   # 4 inc + 4 plain
    for terms in ("US", "UK"):
        text = writer.write_pattern(cir, result, terms)
        assert reverse.compare(cir, text, terms) == [], terms
        assert "sleepy eyes" in text
        doc = pdf.build_pattern_pdf(cir, terminology=terms, childrens=lovey)
        ptext = pdf.extracted_text(doc.pdf_bytes)
        assert CS.STATEMENTS["safe_sleep"].marker in ptext
        v = CS.evaluate(cir, result, text=ptext, childrens=lovey, instructions=text)
        assert v.verdict == CS.VERDICT_HELD, v.to_dict()
        assert [c.code for c in v.checks if c.state != CS.PASS] == ["PHYSICAL_EVIDENCE"]


def test_lovey_heads_hold_what_they_do_not_build():
    from brambleloop.creative import baby

    for title in ("Little Fox Lovey", "Lamb Bunny Lovey", "Fluffy Lamb Lovey"):
        assert baby.lovey_route(title)["family"] == FC.REFUSED, title
    assert baby.lovey_route("Lamb Lovey")["kind"] == "lamb"
    assert baby.lovey_route("Sleepy Bear Lovey")["sleepy"] is True


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]

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
