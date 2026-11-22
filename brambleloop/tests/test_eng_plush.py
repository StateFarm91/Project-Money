"""ENG-PLUSH slice 1: amigurumi as a core family (D-OWNER-CORE-FAMILIES), under the child-safety
pattern-content gate.

Proves, with the real handlers and the real renderer:

* a research-derived toy is admitted -> drafted as a closed spiral body (magic ring, increase,
  even, decrease, close) with a structured stuffing point and two placed ears -> compiled ->
  twin -> reverse-compiled -> certified, and certification withholds ONLY for the physical
  evidence a stuffed toy requires;
* its US and UK PDFs carry every round with its count, the stuffing and closing steps in
  place, a part diagram and the child-safety section with cited sources and access dates;
* every check of `gates.child_safety` fails on the defect it exists for (each a mutation of
  the drafted toy), and UNKNOWN is never PASS;
* `cir.closed_forms` and the reverse compiler catch a wrong stuffing point or closure;
* routing admits only a plain ball-body bear or bunny and holds everything else by name.

Every research source and judgement here is a TEST FIXTURE. The children's assignment passed
to the renderer is a TEST argument (`build_pattern_pdf(childrens=...)` documents that use);
no owner decision is recorded or implied.

Run: cd brambleloop && python3 tests/test_eng_plush.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import dataclasses
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.cir import closed_forms, reverse, writer  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR, Component, Material, Op, Row, Seam  # noqa: E402
from brambleloop.creative import construction_families as CF  # noqa: E402
from brambleloop.creative import fallback_constructions as FC  # noqa: E402
from brambleloop.gates import child_safety as CS  # noqa: E402
from brambleloop.publish import part_diagram, pdf  # noqa: E402

TOY = ("amigurumi_toy", "under_3")          # a TEST assignment, not an owner decision


def _toy(title: str = "Ball Bear Amigurumi", weight: str = "worsted",
         slug: str = "plush-fixture") -> CIR:
    concept = SimpleNamespace(slug=slug, title=title, category="amigurumi",
                              colors={"MC": "#D8C9B0"}, yarn_weight=weight)
    return FC.amigurumi(concept)


def _codes(cir) -> dict[str, str]:
    return {c.code: c.state for c in CS.evaluate(cir).checks}


# ---- the end-to-end proof ----------------------------------------------------------------------

BEAR = None


def _bear_proposal():
    from test_eng_families import _proposal

    return _proposal("hearthside-ball-bear", "Ball Bear Amigurumi", "amigurumi", form="toy",
                     construction="amigurumi_shaping", motif="plain round bear",
                     pod="home_decor", function="a soft keepsake to hold",
                     palette_story="oat and bark", recipient="host",
                     premise="A plain ball-body bear worked in one oat colour with an "
                             "embroidered face")


def test_a_research_amigurumi_is_physical_gated_end_to_end():
    """admit -> CIR -> compile -> twin -> reverse -> certify -> US/UK PDF, real handlers."""
    from test_eng_families import _certify_research_concept

    out = _certify_research_concept(_bear_proposal())
    assert out["drafted"]["construction"] == FC.AMIGURUMI, out["drafted"]
    cir = CIR.from_dict(out["cir"])
    assert [c.name for c in cir.components] == ["body", "ear"]
    body = cir.components[0]
    assert body.construction == "spiral_rounds" and body.foundation_kind == "magic_ring"
    assert body.closes and body.stuff_at_round is not None
    assert out["compiled"]["compiled"] is True
    cert = out["certified"]
    assert cert["granted"] is False
    codes = sorted({r.split(":")[0].split()[-1] for r in cert["reasons"]})
    # Withheld ONLY for physical evidence: every computable check passed.
    # D-OWNER-NO-SAMPLE-SIZING: this toy is not sized from standard gauge (gates.certificate.sized_from_standard_gauge is False), so its Class C hold stays
    assert codes == ["CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN", "PHYSICAL_TEST_REQUIRED"], \
        cert["reasons"]
    stages = out["certificate"].get("stages_run") or []
    for stage in ("compile", "twin", "assembly", "reverse", "child_safety"):
        assert stage in stages or not stages, (stage, stages)
    # The deliverable, in both terminologies.
    result = compile_cir(cir)
    for terms in ("US", "UK"):
        doc = pdf.build_pattern_pdf(cir, terminology=terms, childrens=TOY)
        text = pdf.extracted_text(doc.pdf_bytes)
        for comp in cir.components:
            for row in comp.rows:
                count = result.row(comp.name, row.index).stitch_count
                assert f"({count} sts)" in text, (terms, comp.name, row.index)
        assert f"Rnd {body.rows[-1].index}" in text
        assert f"Stuff after Rnd {body.stuff_at_round}" in text, terms
        assert f"Close after Rnd {body.rows[-1].index}" in text, terms
        assert "Parts and joins" in text and part_diagram.CAPTION.split(":")[0] in text
        assert any(f.get("kind") == "part_diagram" for f in doc.figures), doc.figures
        assert CS.SECTION_HEADING in text and CS.SECTION_END in text
        assert f"accessed {CS.ACCESSED}" in text
        verdict = CS.evaluate(cir, result, text=text, childrens=TOY,
                              instructions=writer.write_pattern(cir, result, terms))
        states = {c.code: c.state for c in verdict.checks}
        assert verdict.verdict == CS.VERDICT_HELD, states
        assert [c for c, s in states.items() if s != CS.PASS] == ["PHYSICAL_EVIDENCE"], states
    # And with nobody's decision, the pipeline's renderer holds it (A1-R): never rendered
    # without a children's decision.
    try:
        pdf.build_pattern_pdf(cir)
    except pdf.ChildrensDecisionRequired:
        pass
    else:
        raise AssertionError("a drafted toy rendered with no children's decision")


def test_the_toy_is_a_closed_spiral_with_counts_and_geometry_validated():
    cir = _toy()
    result = compile_cir(cir)
    assert result.ok, result.findings
    body = cir.components[0]
    counts = [result.row("body", r.index).stitch_count for r in body.rows]
    # magic ring, increase, even, decrease, close
    assert counts[0] == 6 and max(counts) == FC.AMI_BODY_STITCHES and counts[-1] == 6
    widest = counts.index(max(counts))
    assert all(b > a for a, b in zip(counts[:widest], counts[1:widest + 1]))
    assert counts[widest:widest + FC.AMI_PLAIN_ROUNDS + 1] == [36] * (FC.AMI_PLAIN_ROUNDS + 1)
    tail = counts[widest + FC.AMI_PLAIN_ROUNDS:]
    assert all(b < a for a, b in zip(tail, tail[1:]))
    assert counts[body.stuff_at_round - 1] == FC.AMI_STUFF_AT_STITCHES
    geo = {g["piece"]: g for g in closed_forms.part_geometry(cir, result)}
    assert geo["body"]["meridian_cm"] > geo["body"]["diameter_cm"]
    # Every round's declared count is the computed count (the compiler's own check).
    assert cir.components and all(comp.rows for comp in cir.components)
    for comp in cir.components:
        for row in comp.rows:
            assert row.declared_count == result.row(comp.name, row.index).stitch_count


def test_closed_forms_refuse_a_wrong_stuffing_point_or_an_open_closure():
    cir = _toy()
    body = cir.components[0]

    def compiled_codes(**change):
        b = dataclasses.replace(body, **change)
        mutated = dataclasses.replace(cir, components=[b] + cir.components[1:])
        return {f.code for f in compile_cir(mutated).findings if f.is_error}

    assert "STUFFING_POINT_TOO_EARLY" in compiled_codes(stuff_at_round=3)
    assert "STUFFING_OPENING_TOO_SMALL" in compiled_codes(stuff_at_round=body.rows[-1].index)
    assert "STUFFING_OPENING_TOO_SMALL" not in compiled_codes(
        stuff_at_round=body.rows[-2].index)                     # 12 sts is the floor
    assert "STUFFING_POINT_UNKNOWN_ROUND" in compiled_codes(stuff_at_round=99)
    assert "CLOSED_FORM_UNSTUFFED" in compiled_codes(stuff_at_round=None)
    assert "CLOSED_FORM_OPEN" in compiled_codes(rows=body.rows[:-2])
    assert "STUFFING_AFTER_CLOSE" in compiled_codes(stuff_at_round=body.rows[-1].index)
    # A shallow closed piece: a disc gathered shut without walls cannot enclose stuffing.
    shallow = [r for r in body.rows if r.declared_count <= 18 and r.index <= 3]
    shallow += [Row(index=4, ops=[Op("dec", 6), Op("sc", 6)], declared_count=12),
                Row(index=5, ops=[Op("dec", 6)], declared_count=6)]
    assert "PART_GEOMETRY_TOO_SHALLOW" in compiled_codes(rows=shallow, stuff_at_round=4) or \
        "PART_GEOMETRY_GATHERED" in compiled_codes(rows=shallow, stuff_at_round=4)
    # A flat piece cannot close.
    assert "CLOSED_FORM_NOT_ROUNDS" in compiled_codes(construction="flat_rows")


def test_the_reverse_compiler_reads_the_stuffing_point_and_closure_back():
    cir = _toy()
    result = compile_cir(cir)
    for terms in ("US", "UK"):
        text = writer.write_pattern(cir, result, terms)
        assert not [f for f in reverse.compare(cir, text, terms) if f.is_error]
        dropped = "\n".join(ln for ln in text.splitlines() if not ln.startswith("Stuff after"))
        assert "REVERSE_CLOSED_FORM" in {f.code for f in reverse.compare(cir, dropped, terms)}
        moved = text.replace(f"Stuff after Rnd {cir.components[0].stuff_at_round}",
                             f"Stuff after Rnd {cir.components[0].stuff_at_round + 1}")
        assert "REVERSE_CLOSED_FORM" in {f.code for f in reverse.compare(cir, moved, terms)}
    # And it round-trips through to_dict/from_dict (every pipeline hop serialises).
    again = CIR.from_dict(cir.to_dict())
    assert again.components[0].stuff_at_round == cir.components[0].stuff_at_round
    assert again.components[0].closes is True and again.to_dict() == cir.to_dict()
    # A piece that states neither keeps its old dict exactly (no digest moves).
    assert "closes" not in cir.to_dict()["components"][1]
    assert "stuff_at_round" not in cir.to_dict()["components"][1]


# ---- the gate: every check fails on its defect ---------------------------------------------------


def test_the_drafted_toy_passes_every_computable_check_and_is_held_for_evidence():
    v = CS.evaluate(_toy())
    states = {c.code: c.state for c in v.checks}
    assert states == {"FEATURES_EMBROIDERED": CS.PASS, "MATERIALS_KNOWN": CS.PASS,
                      "ATTACHMENTS_KNOWN": CS.PASS,
                      "JOINS_VALIDATED": CS.PASS, "NO_CORDS_OR_LOOPS": CS.PASS,
                      "STUFFING_GUIDANCE": CS.PASS, "SMALL_PARTS": CS.PASS,
                      "AGE_SUITABILITY": CS.PASS, "PHYSICAL_EVIDENCE": CS.UNKNOWN}, states
    assert v.verdict == CS.VERDICT_HELD
    assert set(v.profile) >= {"stuffed", "face", "sewn"}


def test_a_toy_called_anything_is_still_inside_the_gate():
    toy = _toy()
    for title, slug in (("Juniper Friend", "juniper-friend-1"), ("", "design-1"),
                        ("Woodland Keepsake", "woodland-keepsake-1")):
        renamed = _with(toy, title=title, slug=slug)
        assert CS.applies(renamed), title
        assert CS.evaluate(renamed).verdict == CS.VERDICT_HELD, title
    # A stuffed closed ball with nothing sewn on (not a "stuffed figure") and no child word in
    # its name is still a toy: the closed-piece rule alone brings it inside the gate.
    from brambleloop.products import launch0 as L

    ball = _with(toy, components=[toy.components[0]], assembly=[], title="Juniper Friend",
                 slug="juniper-ball-1")
    assert not L.stuffed_figure(ball) and not L.child_words_in(ball.title, ball.slug)
    assert CS.applies(ball) and CS.evaluate(ball).verdict == CS.VERDICT_HELD


def test_an_unidentified_material_on_a_toy_is_held_and_childrens_garments_stay_in_the_gate():
    toy = _toy()
    odd = _with(toy, materials=toy.materials + [Material(name="trim kit (assorted)")])
    v = CS.evaluate(odd)
    assert {c.code: c.state for c in v.checks}["MATERIALS_KNOWN"] == CS.UNKNOWN
    assert v.verdict != CS.VERDICT_PASS
    assert CS.applies(toy)                                  # ungraded toy: inside
    # Review b18-c C1: a graded baby or child garment is NEVER outside the child-safety gate
    # (GARMENT_CLOSURES, cords, small parts). Real graded CIRs, not a stand-in grading object.
    from brambleloop.products import garment_release as GR
    for key in ("little-wren-baby-cardigan", "brookside-kids-sweater"):
        cirs = GR.build(GR.DESIGNS[key]).cirs
        assert cirs, key
        for size, cir in cirs.items():
            assert cir.grading is not None and not any(
                c.stuff_at_round is not None or c.closes for c in cir.components), (key, size)
            assert CS.garment_months(cir) is not None, (key, size)
            assert CS.applies(cir), (key, size)             # graded, unstuffed: still inside


def test_unknown_is_never_pass():
    v = CS.Verdict(applies=True, profile=("base",),
                   checks=[CS.Check("X", CS.PASS, ""), CS.Check("Y", CS.UNKNOWN, "")])
    assert v.verdict == CS.VERDICT_HELD != CS.VERDICT_PASS
    v.checks.append(CS.Check("Z", CS.FAIL, ""))
    assert v.verdict == CS.VERDICT_FAIL


def _with(cir, **change):
    return dataclasses.replace(cir, **change)


def test_hard_parts_fail_features_even_with_embroidered_eyes():
    cir = _toy()
    for material in ("12 mm safety eyes", "2 buttons", "plastic pellets", "a jingle bell",
                     "beads for the nose"):
        bad = _with(cir, materials=cir.materials + [Material(name=material)])
        assert _codes(bad)["FEATURES_EMBROIDERED"] == CS.FAIL, material
    noted = _with(cir, designer_notes=(cir.designer_notes or "") + " Add safety eyes.")
    assert _codes(noted)["FEATURES_EMBROIDERED"] == CS.FAIL
    # A face with no embroidery instruction fails too.
    body = cir.components[0]
    plain = dataclasses.replace(body, note="Worked from the top down; add eyes and a nose.")
    faceless = _with(cir, components=[plain] + cir.components[1:],
                     designer_notes="A ball-body bear.",
                     assembly=[dataclasses.replace(cir.assembly[0],
                                                   note="sew through both loops; bury the "
                                                        "tail; add eyes")],
                     materials=[m for m in cir.materials if "embroider" not in m.name])
    assert _codes(faceless)["FEATURES_EMBROIDERED"] == CS.FAIL
    # Embroidered eyes alone are not sufficient: a toy with embroidered eyes and a cord fails.
    corded = _with(cir, components=cir.components + [
        Component("tie", "flat_rows", rows=[Row(1, [Op("ch", 40)], declared_count=40)],
                  foundation=0, foundation_kind="none")],
        assembly=cir.assembly + [Seam("sew", "tie", "body", at_round=10, spans_rounds=1,
                                      stitches_from_centre=0,
                                      note="sew through both loops and bury the tail")])
    v = CS.evaluate(corded)
    assert {c.code: c.state for c in v.checks}["FEATURES_EMBROIDERED"] == CS.PASS
    assert v.verdict == CS.VERDICT_FAIL


def test_joins_must_be_placed_measured_and_sewn_through_both_loops():
    cir = _toy()
    seam = cir.assembly[0]
    unplaced = dataclasses.replace(seam, at_round=None, stitches_from_centre=None,
                                   edge_a=None, edge_b=None)
    assert _codes(_with(cir, assembly=[unplaced]))["JOINS_VALIDATED"] == CS.FAIL
    mismatched = dataclasses.replace(seam, stitches_from_centre=2)
    assert _codes(_with(cir, assembly=[mismatched]))["JOINS_VALIDATED"] == CS.FAIL
    vague = dataclasses.replace(seam, note="sew the ear on")
    assert _codes(_with(cir, assembly=[vague]))["JOINS_VALIDATED"] == CS.FAIL
    threaded = dataclasses.replace(seam, method="thread")
    assert _codes(_with(cir, assembly=[threaded]))["JOINS_VALIDATED"] == CS.FAIL


def test_cords_and_loops_fail():
    cir = _toy()
    ear = cir.components[1]
    looped = list(ear.rows)
    looped[-1] = dataclasses.replace(looped[-1], ops=[Op("sc", 10), Op("ch", 12),
                                                      Op("sc", 10)])
    bad = _with(cir, components=[cir.components[0], dataclasses.replace(ear, rows=looped)])
    assert _codes(bad)["NO_CORDS_OR_LOOPS"] == CS.FAIL
    worded = _with(cir, designer_notes=(cir.designer_notes or "") + " Tie a ribbon bow.")
    assert _codes(worded)["NO_CORDS_OR_LOOPS"] == CS.FAIL
    threaded = _with(cir, assembly=[dataclasses.replace(cir.assembly[0], method="thread")])
    assert _codes(threaded)["NO_CORDS_OR_LOOPS"] == CS.FAIL


def test_stuffing_guidance_fails_without_toy_stuffing_or_a_stuffing_point():
    cir = _toy()
    no_fill = _with(cir, materials=[m for m in cir.materials if "fibrefill" not in m.name]
                    + [Material(name="scrap fabric filling")])
    assert _codes(no_fill)["STUFFING_GUIDANCE"] == CS.FAIL
    body = cir.components[0]
    unstated = dataclasses.replace(body, stuff_at_round=None)
    assert _codes(_with(cir, components=[unstated] + cir.components[1:]))[
        "STUFFING_GUIDANCE"] == CS.FAIL
    # Stuffed but never stated to close: the stuffing has nowhere to stay.
    unclosed = dataclasses.replace(body, closes=False)
    v = CS.evaluate(_with(cir, components=[unclosed] + cir.components[1:]))
    check = {c.code: c for c in v.checks}["STUFFING_GUIDANCE"]
    assert check.state == CS.FAIL and "closure" in check.detail, check


def test_small_ears_fail_or_are_unknown_never_pass():
    cir = _toy()
    ear = cir.components[1]
    tiny = dataclasses.replace(ear, rows=ear.rows[:2])          # 10 sts across
    v = _codes(_with(cir, components=[cir.components[0], tiny]))
    assert v["SMALL_PARTS"] in (CS.FAIL, CS.UNKNOWN) and v["SMALL_PARTS"] != CS.PASS
    # The engine's own small-parts refusal, reached past the body-size floor: at lace weight
    # an ear fits the cylinder, and the toy is refused for that, by name.
    floor = FC.AMI_MIN_BODY_CM
    FC.AMI_MIN_BODY_CM = 0.0
    try:
        _toy(weight="lace")
    except ValueError as exc:
        assert "small-parts cylinder" in str(exc) and "ear" in str(exc), exc
    else:
        raise AssertionError("a toy with small-part ears was drafted")
    finally:
        FC.AMI_MIN_BODY_CM = floor
    # And the engine refuses a yarn weight at which an ear fits or may fit the cylinder.
    for weight in ("fingering", "lace"):
        try:
            _toy(weight=weight)
        except ValueError:
            pass
        else:
            raise AssertionError(f"a toy drafted at {weight}")


def test_the_rendered_document_fails_on_a_missing_statement_citation_or_a_claim():
    cir = _toy()
    result = compile_cir(cir)
    doc = pdf.build_pattern_pdf(cir, childrens=TOY)
    text = pdf.extracted_text(doc.pdf_bytes)
    instructions = writer.write_pattern(cir, result, "US")

    def state(t, code, instr=instructions):
        v = CS.evaluate(cir, result, text=t, childrens=TOY, instructions=instr)
        return {c.code: c.state for c in v.checks}[code]

    assert state(text, "SAFETY_SECTION") == CS.PASS
    for key in ("pattern_not_toy", "age_suitability", "features", "joins", "stuffing",
                "no_cords"):
        cut = text.replace(CS.STATEMENTS[key].marker, "")
        assert state(cut, "SAFETY_SECTION") == CS.FAIL, key
    assert state(text.replace(f"accessed {CS.ACCESSED}", "accessed"), "CITATIONS") == CS.FAIL
    for src in ("cfr_1501", "sor_2011_17", "cpsc_5100"):
        assert state(text.replace(CS.SOURCES[src].url, ""), "CITATIONS") == CS.FAIL, src
    for claim in ("This toy is safety tested.", "Meets ASTM F963.", "CE marked.",
                  "Safe for babies.", "This bear has been certified."):
        assert state(text + " " + claim, "NO_CERTIFICATION_CLAIM") == CS.FAIL, claim
    assert state(text, "NO_CERTIFICATION_CLAIM") == CS.PASS
    assert state(text, "NO_HARD_PARTS_IN_TEXT", instructions + " Attach safety eyes.") == \
        CS.FAIL
    # The face must be instructed in the printed pattern, not only in the CIR's notes.
    import re as _re

    unprinted = _re.sub(r"(?i)embroider\w*", "add", instructions)
    v = CS.evaluate(cir, result, text=text, childrens=TOY, instructions=unprinted)
    assert {c.code: c.state for c in v.checks}.get("FEATURES_INSTRUCTED") == CS.FAIL
    assert "FEATURES_INSTRUCTED" not in {c.code for c in CS.evaluate(
        cir, result, text=text, childrens=TOY, instructions=instructions).checks}


def test_the_renderer_refuses_a_document_whose_safety_section_fails():
    cir = _toy()
    original = CS.STATEMENTS["stuffing"]
    CS.STATEMENTS["stuffing"] = dataclasses.replace(original, text="Stuff it.")
    try:
        pdf.build_pattern_pdf(cir, childrens=TOY)
    except ValueError as exc:
        assert "child-safety content gate fails" in str(exc) and "SAFETY_SECTION" in str(exc)
    else:
        raise AssertionError("a toy PDF rendered without its stuffing statement")
    finally:
        CS.STATEMENTS["stuffing"] = original


def test_certification_carries_every_failing_check():
    from brambleloop.gates.certificate import certify

    cir = _toy()
    bad = _with(cir, materials=cir.materials + [Material(name="safety eyes")])
    codes = {f.code for f in certify(bad).findings if f.is_error}
    assert "CHILD_SAFETY_FEATURES_EMBROIDERED" in codes, codes
    assert "CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN" in codes


def test_the_gate_does_not_reach_a_decided_adult_cushion_or_a_flat_adult_piece():
    from brambleloop.products import inventory

    reached = []
    for slug in inventory.universe():
        c = inventory._engineered(slug)
        if c is not None and CS.applies(c):
            reached.append(slug)
            assert CS.evaluate(c).verdict == CS.VERDICT_PASS, slug   # flat baby blankets
    assert set(reached) <= {"cloudline-baby-blanket", "nordic-forest-mosaic-throw-baby"}, reached


# ---- routing -----------------------------------------------------------------------------------


def test_routing_admits_a_plain_bear_or_bunny_and_holds_the_rest_by_name():
    ok = CF.route(category="amigurumi", title="Ball Bear Amigurumi", form="toy",
                  construction="amigurumi_shaping")
    assert ok == {"admitted": True, "family": FC.AMIGURUMI, "status": CF.PHYSICAL_GATE,
                  "reason": ""}, ok
    assert CF.route(category="toy", title="Cosy Rabbit", form="toy",
                    construction="in_the_round")["admitted"]
    for title, word in (("Fluffy Bear", "fluffy"), ("Brushed Bunny Plush", "brushed"),
                        ("Faux Fur Bear", "faux fur")):
        got = CF.route(category="amigurumi", title=title, form="toy",
                       construction="amigurumi_shaping")
        assert not got["admitted"] and got["reason"].startswith(
            "construction_unsupported:amigurumi"), got
        assert word in got["reason"] and "texture" in got["reason"], got
    for title in ("Meadow Hare", "Bear with Safety Eyes", "Two Bears", "Bear Keychain",
                  "Bunny Rattle"):
        got = CF.route(category="amigurumi", title=title, form="toy",
                       construction="amigurumi_shaping")
        assert not got["admitted"] and got["reason"].startswith(CF.HOLD_PREFIX), (title, got)
    # The family is admitted only because its proof exists (remove it and it is not).
    fam = CF.FAMILIES[FC.AMIGURUMI]
    assert fam.status == CF.PHYSICAL_GATE
    assert fam.proof == ("tests/test_eng_plush.py::"
                         "test_a_research_amigurumi_is_physical_gated_end_to_end")
    assert fam.proof.split("::")[1] in globals()


def test_the_part_diagram_draws_every_piece_and_join_from_the_numbers():
    cir = _toy()
    result = compile_cir(cir)
    ps = {p["piece"]: p for p in part_diagram.pieces(cir, result)}
    assert ps["body"]["widest_sts"] == 36 and ps["ear"]["make"] == 2
    assert ps["body"]["stuff_at_round"] == cir.components[0].stuff_at_round
    js = part_diagram.joins(cir)
    assert js == [{"from": "ear", "to": "body", "method": "whipstitch",
                   "where": f"Rnd {FC.AMI_EAR_ROUND}, {FC.AMI_EAR_STITCHES // 2} sts, mirrored",
                   "stuffed_before_closing": False}], js
    png = part_diagram.render(cir, result)
    assert png and png.startswith(b"\x89PNG")


# ---- slice 2: pillows and cushions --------------------------------------------------------------


def _cushion_proposal(slug, title, motif, palette_story):
    from test_eng_families import _proposal

    return _proposal(slug, title, "pillow", form="pillow", function="fronts a sofa cushion",
                     motif=motif, palette_story=palette_story,
                     premise=f"A {title.lower()} for a reading chair, worked in plain rows")


def _decided_not_for_a_child(cir):
    """A TEST decision bound to this exact design (launch0's real decision path), so the
    renderer's A1-R gate is satisfied the way an owner's written decision would satisfy it.
    Nothing is recorded outside this process."""
    from brambleloop.products import launch0 as L

    L.NOT_MERCHANDISED_TO_A_CHILD[cir.slug] = "TEST: a sofa cushion cover, home decor"
    L._STUFFED_DECISION_CIR_SHA256[cir.slug] = L._cir_decision_digest(cir)

    def undo():
        L.NOT_MERCHANDISED_TO_A_CHILD.pop(cir.slug, None)
        L._STUFFED_DECISION_CIR_SHA256.pop(cir.slug, None)
    return undo


def _cushion_end_to_end(proposal, family):
    from test_eng_families import _assert_certified_end_to_end, _certify_research_concept

    out = _certify_research_concept(proposal)
    assert out["drafted"]["construction"] == family, out["drafted"]
    _assert_certified_end_to_end(out)
    assert "assembly" in out["certificate"]["stages_run"]
    cir = CIR.from_dict(out["cir"])
    result = compile_cir(cir)
    names = [c.name for c in cir.components]
    assert names[:3] == ["front", "upper back", "lower back"], names
    undo = _decided_not_for_a_child(cir)
    try:
        for terms in ("US", "UK"):
            doc = pdf.build_pattern_pdf(cir, terminology=terms)
            text = pdf.extracted_text(doc.pdf_bytes)
            for comp in cir.components:
                for row in comp.rows:
                    count = result.row(comp.name, row.index).stitch_count
                    assert f"({count} sts)" in text, (terms, comp.name, row.index)
            assert "Parts and joins" in text
            assert any(f.get("kind") == "part_diagram" for f in doc.figures)
            assert "envelope" in text.lower()
            assert not CS.applies(cir), "an adult cushion cover is outside the child gate"
    finally:
        undo()
    return cir


def test_a_research_envelope_cushion_certifies_end_to_end():
    cir = _cushion_end_to_end(
        _cushion_proposal("linen-ridge-envelope-cushion", "Linen Envelope Cushion Cover",
                          "plain linen rows", "oat and sage"), FC.ENVELOPE)
    upper = next(c for c in cir.components if c.name == "upper back")
    front = cir.components[0]
    assert 2 * len(upper.rows) > len(front.rows)        # the backs overlap
    assert not [m for m in cir.materials if "button" in m.name.lower()]


def test_a_research_highland_cow_cushion_certifies_end_to_end():
    cir = _cushion_end_to_end(
        _cushion_proposal("glen-highland-cow-cushion", "Highland Cow Cushion Cover",
                          "highland cow face", "oat, ginger and cream"), FC.APPLIQUE)
    from brambleloop.creative import cushions

    pieces = {c.name for c in cir.components}
    assert {p[0] for p in cushions.APPLIQUES["highland cow"]["pieces"]} <= pieces
    surface = [s for s in cir.assembly if s.edge_b == "surface"]
    assert len(surface) == len(cushions.APPLIQUES["highland cow"]["pieces"])
    assert any("embroider" in (s.note or "").lower() for s in cir.assembly)


def horn_index(cir) -> int:
    return next(i for i, s in enumerate(cir.assembly) if s.piece_a == "horn")


def test_surface_joins_are_measured_and_misplacement_is_refused():
    from brambleloop.cir import assembly
    from brambleloop.cir.twin import build_twin
    from brambleloop.creative import cushions

    concept = SimpleNamespace(slug="cow-fixture", title="Highland Cow Cushion Cover",
                              category="pillow", colors={"oat": "#E6DCC8", "ginger": "#B5652B",
                                                         "cream": "#F3EAD8"},
                              yarn_weight="worsted", risk_class="A")
    cir = cushions.envelope_cover(concept, applique="highland cow")

    def verdict(c):
        r = compile_cir(c)
        if not r.ok:          # the compiler's placement checks refuse it first
            return SimpleNamespace(verdict="does_not_assemble")
        twins = {k.name: build_twin(c, r, component=k.name) for k in c.components}
        return assembly.assemble(c, twins)

    assert verdict(cir).verdict == "assembles"
    # Within the panel by the compiler's own checks, but off it by the surface geometry: the
    # horn centred 22 sts out on a 51-st front runs past the edge.
    bad = list(cir.assembly)
    bad[horn_index(cir)] = dataclasses.replace(bad[horn_index(cir)], stitches_from_centre=22)
    mutated = dataclasses.replace(cir, assembly=bad)
    assert compile_cir(mutated).ok and verdict(mutated).verdict == "does_not_assemble"
    horn = next(i for i, s in enumerate(cir.assembly) if s.piece_a == "horn")
    for change in ({"stitches_from_centre": 60}, {"at_round": 400}, {"at_round": 1},
                   {"stitches_from_centre": 1}):       # off the side, top, bottom; overlaps
        bad = list(cir.assembly)
        bad[horn] = dataclasses.replace(bad[horn], **change)
        assert verdict(dataclasses.replace(cir, assembly=bad)).verdict == "does_not_assemble", \
            change
    # Written and read back: the placement survives the reverse compiler in both terms.
    r = compile_cir(cir)
    for terms in ("US", "UK"):
        text = writer.write_pattern(cir, r, terms)
        assert "onto the front centred on row" in text
        assert not [f for f in reverse.compare(cir, text, terms) if f.is_error]
        moved = text.replace("14 sts from the centre line", "13 sts from the centre line")
        assert "REVERSE_ASSEMBLY" in {f.code for f in reverse.compare(cir, moved, terms)}


def test_cushion_routing_holds_unmodelled_textures_and_extra_colours():
    for title in ("Shaggy Highland Cow Cushion", "Fluffy Envelope Cushion",
                  "Fringed Highland Cow Pillow"):
        got = CF.route(category="pillow", title=title, form="pillow", construction="flat_rows")
        assert not got["admitted"] and "texture" in got["reason"], (title, got)
    from brambleloop.creative import cushions

    four = SimpleNamespace(slug="x", title="Linen Envelope Cushion Cover", category="pillow",
                           colors={"a": "#111111", "b": "#222222", "c": "#333333"},
                           yarn_weight="worsted")
    try:
        cushions.envelope_cover(four)
    except ValueError as exc:
        assert "colours" in str(exc)
    else:
        raise AssertionError("a colour the cover does not work was listed")


# ---- slice 3: baby --------------------------------------------------------------------------


def test_a_research_lovey_is_physical_gated_end_to_end():
    from test_eng_families import _certify_research_concept, _proposal

    proposal = _proposal("meadow-bear-lovey", "Bear Lovey", "baby", form="toy",
                         construction="amigurumi_shaping", motif="plain bear head",
                         recipient="new_parent", function="a soft square to hold",
                         palette_story="oat and cream",
                         premise="A plain bear head on a soft square, embroidered face")
    out = _certify_research_concept(proposal)
    assert out["drafted"]["construction"] == FC.LOVEY, out["drafted"]
    cir = CIR.from_dict(out["cir"])
    codes = sorted({r.split(":")[0].split()[-1] for r in out["certified"]["reasons"]})
    # D-OWNER-NO-SAMPLE-SIZING: Class C sizes from standard gauge; child safety still holds
    assert codes == ["CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN"], \
        out["certified"]["reasons"]
    lovey = ("lovey", "under_3")                         # a TEST assignment
    result = compile_cir(cir)
    for terms in ("US", "UK"):
        doc = pdf.build_pattern_pdf(cir, terminology=terms, childrens=lovey)
        text = pdf.extracted_text(doc.pdf_bytes)
        assert cir.components and all(comp.rows for comp in cir.components)
        for comp in cir.components:
            for row in comp.rows:
                assert f"({result.row(comp.name, row.index).stitch_count} sts)" in text
        assert "Parts and joins" in text and CS.SECTION_HEADING in text
        assert CS.STATEMENTS["safe_sleep"].marker in text           # the sleep statement
        v = CS.evaluate(cir, result, text=text, childrens=lovey,
                        instructions=writer.write_pattern(cir, result, terms))
        assert v.verdict == CS.VERDICT_HELD, v.to_dict()
        assert "sleep" in v.profile


def test_baby_blankets_carry_the_safety_section_and_pass_the_gate():
    from brambleloop.products import inventory

    cir = inventory._engineered("cloudline-baby-blanket")
    doc = pdf.build_pattern_pdf(cir)
    text = pdf.extracted_text(doc.pdf_bytes)
    v = CS.evaluate(cir, text=text, instructions=writer.write_pattern(cir, compile_cir(cir),
                                                                       "US"))
    assert v.applies and "sleep" in v.profile
    assert v.verdict == CS.VERDICT_PASS, v.to_dict()
    assert CS.STATEMENTS["safe_sleep"].marker in text


def test_baby_garments_and_unbuilt_baby_items_are_held_by_name():
    # ENG-GARMENT: a baby cardigan now routes to the proven graded raglan family; a baby
    # garment in a construction no baby proof pins (side-to-side) is still held by name.
    got = CF.route(category="baby", title="Baby Cardigan", form="fitted_garment",
                   construction="top_down_yoke")
    assert got["admitted"] and got["family"] == "garment_raglan", got
    got = CF.route(category="baby", title="Baby Vest", form="fitted_garment",
                   construction="side_to_side")
    assert not got["admitted"] and got["reason"].startswith("construction_unsupported:garment")
    got = CF.route(category="baby", title="Fluffy Bear Lovey", form="toy",
                   construction="amigurumi_shaping")
    assert not got["admitted"] and "texture" in got["reason"], got


# ---- ENG-PLUSH-FIX: every probe of the independent review of 2763340b --------------------------

M1_MATERIAL_PROBES = ("2 x 9 mm black eyes", "9mm animal eyes with washers", "craft eyes",
                      "doll eyes", "toy eyes", "crystal eyes", "rhinestones", "pom-pom nose",
                      "an eye back", "press studs", "hook and eye", "toggle")


def test_m1_every_reviewer_hard_part_probe_fails_features_on_the_embroidered_bear():
    cir = _toy()
    assert _codes(cir)["FEATURES_EMBROIDERED"] == CS.PASS        # the baseline is clean
    assert len(M1_MATERIAL_PROBES) == 12
    for material in M1_MATERIAL_PROBES:
        bad = _with(cir, materials=cir.materials + [Material(name=material)])
        v = CS.evaluate(bad)
        states = {c.code: c.state for c in v.checks}
        assert states["FEATURES_EMBROIDERED"] == CS.FAIL, (material, states)
        assert v.verdict == CS.VERDICT_FAIL, material


def test_m1_an_eye_or_nose_instruction_not_stated_as_embroidered_fails():
    cir = _toy()
    probes = ("Sew on two 9 mm eyes.", "Add the eyes between rounds 8 and 9.",
              "Insert the nose at round 10.", "Glue the felt nose on.",
              "Embroider the mouth, then attach the 12mm eyes.")
    assert probes
    for note in probes:
        noted = _with(cir, designer_notes=(cir.designer_notes or "") + " " + note)
        assert _codes(noted)["FEATURES_EMBROIDERED"] == CS.FAIL, note
    # And the printed instructions are read by the same rule.
    result = compile_cir(cir)
    checks = CS._text_checks("x", ("base", "face"), instructions="Add two craft eyes.")
    hard = {c.code: c.state for c in checks}["NO_HARD_PARTS_IN_TEXT"]
    assert hard == CS.FAIL and result.ok


def test_m1_materials_are_an_allow_list_and_an_unknown_one_holds_the_item():
    cir = _toy()
    assert _codes(cir)["MATERIALS_KNOWN"] == CS.PASS
    unknowns = ("a scrap of felt", "leather lacing", "a small notion", "fabric paint")
    assert unknowns
    for material in unknowns:
        v = CS.evaluate(_with(cir, materials=cir.materials + [Material(name=material)]))
        states = {c.code: c.state for c in v.checks}
        assert states["MATERIALS_KNOWN"] in (CS.UNKNOWN, CS.FAIL), (material, states)
        assert v.verdict != CS.VERDICT_PASS, material
    tools = ("4.0 mm crochet hook", "tapestry needle", "stitch markers", "scissors")
    assert tools
    for material in tools:
        ok = _with(cir, materials=cir.materials + [Material(name=material)])
        assert _codes(ok)["MATERIALS_KNOWN"] == CS.PASS, material
        assert _codes(ok)["FEATURES_EMBROIDERED"] == CS.PASS, material


M2_NOTE_PROBES = ("Tie a bow around the neck.", "Add a loop for hanging.",
                  "Attach a lace to the pram.", "Crochet a leash.",
                  "Make a 60 cm chain and tie it on.")
M2_MATERIAL_PROBES = ("a 40 cm length of yarn to tie on", "a pacifier chain", "leather lacing")


def test_m2_every_reviewer_cord_and_loop_probe_fails():
    cir = _toy()
    assert _codes(cir)["NO_CORDS_OR_LOOPS"] == CS.PASS
    assert len(M2_NOTE_PROBES) == 5 and len(M2_MATERIAL_PROBES) == 3
    for note in M2_NOTE_PROBES:
        noted = _with(cir, designer_notes=(cir.designer_notes or "") + " " + note)
        assert _codes(noted)["NO_CORDS_OR_LOOPS"] == CS.FAIL, note
    for material in M2_MATERIAL_PROBES:
        bad = _with(cir, materials=cir.materials + [Material(name=material)])
        v = CS.evaluate(bad)
        assert {c.code: c.state for c in v.checks}["NO_CORDS_OR_LOOPS"] == CS.FAIL, material
        assert v.verdict == CS.VERDICT_FAIL, material


def test_m2_consecutive_chain_ops_and_repeats_are_one_chain_run():
    from brambleloop.cir.model import Repeat

    cir = _toy()
    ear = cir.components[1]
    for ops in ([Op("sc", 10), Op("ch", 6), Op("ch", 6), Op("ch", 6), Op("sc", 10)],
                [Op("sc", 10), Repeat([Op("ch", 6)], times=5), Op("sc", 10)],
                [Op("sc", 10), Op("ch", 4), Repeat([Op("ch", 2)], times=2), Op("sc", 10)]):
        rows = list(ear.rows)
        rows[-1] = dataclasses.replace(rows[-1], ops=ops)
        bad = _with(cir, components=[cir.components[0], dataclasses.replace(ear, rows=rows)])
        assert _codes(bad)["NO_CORDS_OR_LOOPS"] == CS.FAIL, ops
    # A chain run of exactly the limit, broken by a stitch, is not a loop.
    rows = list(ear.rows)
    rows[-1] = dataclasses.replace(rows[-1], ops=[Repeat([Op("ch", 3), Op("sc", 1)], times=4)])
    ok = _with(cir, components=[cir.components[0], dataclasses.replace(ear, rows=rows)])
    assert _codes(ok)["NO_CORDS_OR_LOOPS"] == CS.PASS


def test_m2_a_corded_flat_baby_blanket_cannot_reach_pass():
    from brambleloop.products import inventory

    cir = inventory._engineered("cloudline-baby-blanket")
    assert CS.evaluate(cir).verdict == CS.VERDICT_PASS
    corded = _with(cir, designer_notes=(cir.designer_notes or "") + " Add a loop for hanging.")
    assert CS.evaluate(corded).verdict == CS.VERDICT_FAIL
    tied = _with(cir, materials=cir.materials + [Material(name="a 40 cm length of yarn to "
                                                                "tie on")])
    assert CS.evaluate(tied).verdict == CS.VERDICT_FAIL


def test_m3_certify_reads_the_catalogue_assignment_of_a_flat_design():
    """A flat sewn applique throw with no child word in its name, assigned to a child in the
    catalogue, is inside the gate at certify and held for physical evidence."""
    from brambleloop.gates import certificate
    from brambleloop.products import inventory, launch0

    base = inventory._engineered("cloudline-baby-blanket")
    neutral = _with(base, title="Meadow Applique Throw", slug="meadow-applique-throw-m3")
    assert not launch0.child_words_in(neutral.title, neutral.slug)
    patch = Component("patch", "flat_rows",
                      rows=[Row(i, [Op("sc", 20)], declared_count=20) for i in range(1, 21)],
                      foundation=20)
    sewn = _with(neutral, components=list(neutral.components) + [patch],
                 assembly=list(neutral.assembly) + [
                     Seam("whipstitch", "patch", neutral.components[0].name,
                          edge_a="bottom", edge_b="top",
                          note="sew through both loops; bury the tail")])
    assert not CS.applies(sewn)                        # nothing in the CIR says "child"
    launch0.EXTRA_CHILDRENS_ASSIGNMENTS[sewn.slug] = ("baby_blanket", "under_3")
    launch0._CIR_AUDIENCE = None
    try:
        assert launch0.childrens_assignment(sewn.slug) == ("baby_blanket", "under_3")
        cert = certificate.certify(sewn)
        codes = {f.code for f in cert.findings}
        assert "CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN" in codes, codes
        assert "child_safety" in cert.stages_run and not cert.granted
    finally:
        del launch0.EXTRA_CHILDRENS_ASSIGNMENTS[sewn.slug]
        launch0._CIR_AUDIENCE = None


def test_m4_the_age_band_is_read_and_the_age_statement_claims_only_what_is_shown():
    cir = _toy()
    small = {c.code: c for c in CS.evaluate(cir).checks}
    assert small["AGE_SUITABILITY"].state == CS.PASS
    odd = {c.code: c.state for c in CS.evaluate(cir, childrens=("amigurumi_toy",
                                                               "no_such_band")).checks}
    assert odd["AGE_SUITABILITY"] == CS.UNKNOWN
    ear = cir.components[1]
    tiny = _with(cir, components=[cir.components[0],
                                  dataclasses.replace(ear, rows=ear.rows[:2])])
    states = {c.code: c.state for c in CS.evaluate(tiny, childrens=TOY).checks}
    assert states["SMALL_PARTS"] != CS.PASS and states["AGE_SUITABILITY"] != CS.PASS
    claim = "every sewn-on piece is larger than the small-parts cylinder"
    sewn = ("base", "sewn", "stuffed")
    assert claim in dict(CS.section_lines(sewn, small_parts_clear=True))["Age suitability"]
    for clear in (None, False):
        text = dict(CS.section_lines(sewn, small_parts_clear=clear))["Age suitability"]
        assert claim not in text and "has NOT been shown" in text, clear
    one = dict(CS.section_lines(("base",), small_parts_clear=True))["Age suitability"]
    assert claim not in one and "one piece" in one
    for text in (CS.AGE_TEXT_ONE_PIECE, CS.AGE_TEXT_UNPROVEN,
                 CS.STATEMENTS["age_suitability"].text):
        assert CS.STATEMENTS["age_suitability"].marker in text


def test_m5_a_closed_stuffed_ball_with_a_neutral_name_and_no_placed_seam_is_in_scope():
    """The surviving mutant: a closed stuffed piece in rounds is a toy by its construction
    alone -- one piece, a neutral name, no sewn-on part, no assignment."""
    from brambleloop.products import launch0

    cir = _toy()
    body = cir.components[0]
    ball = _with(cir, title="Oat Round", slug="oat-round-m5", components=[body],
                 assembly=[], designer_notes="Worked as one closed piece.")
    assert not launch0.child_words_in(ball.title, ball.slug)
    assert not launch0.stuffed_figure(ball)            # no placed seam
    assert launch0.childrens_assignment(ball.slug) is None
    assert any(c.closes for c in ball.components)
    assert CS.applies(ball)
    assert CS.evaluate(ball).verdict != CS.VERDICT_PASS


def test_l3_a_stated_closure_on_an_uncompiled_piece_is_a_finding():
    cir = _toy()
    result = compile_cir(cir)
    stripped = SimpleNamespace(rows=[r for r in result.rows if r.component != "body"])
    found: list = []
    closed_forms.check(cir, stripped, found)
    assert [f.code for f in found] == ["CLOSED_FORM_UNMEASURED"], found


def test_l4_an_asset_naming_its_pieces_may_show_only_their_colours():
    from brambleloop.cir.twin import build_twin
    from brambleloop.gates import asset_truth as AT

    concept = SimpleNamespace(slug="two-tone", title="Ball Bear Amigurumi",
                              category="amigurumi",
                              colors={"MC": "#D8C9B0", "CC": "#5A3A22"}, yarn_weight="worsted")
    cir = FC.amigurumi(concept)
    ear = cir.components[1]
    ear = dataclasses.replace(ear, rows=[dataclasses.replace(r, color="CC") for r in ear.rows])
    body = dataclasses.replace(cir.components[0], rows=[dataclasses.replace(r, color="MC")
                                                        for r in cir.components[0].rows])
    cir = _with(cir, components=[body, ear])
    result = compile_cir(cir)
    twin = build_twin(cir, result, component="body")
    assert "CC" not in set(twin.colors_used)

    def asset(components):
        return AT.Asset(asset_id="a", asset_class=AT.AssetClass.DIGITAL_TWIN_RENDER,
                        provenance=AT.Provenance(source="twin", created_by="t", tool="t"),
                        depicts_colors=["CC"], depicts_components=components, is_hero=True)

    def colour_errors(a):
        return [f for f in AT.check_assets([a], cir, twin) if f.code == "ASSET_COLOR_ABSENT"]

    assert colour_errors(asset(["body"]))                 # the body never works CC
    assert not colour_errors(asset(["body", "ear"]))      # the ear does
    assert not colour_errors(asset([]))                   # a whole-design depiction


def test_mutation_harness_reports_an_import_error_as_an_error_not_a_kill():
    import importlib.util

    spec = importlib.util.spec_from_file_location("mutate_plush",
                                                  ROOT / "scripts" / "mutate_plush.py")
    mp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mp)
    import_error = SimpleNamespace(returncode=1, stdout=b"",
                                   stderr=b"ModuleNotFoundError: No module named 'sqlalchemy'")
    assert mp.classify(import_error) == mp.ERROR
    assert mp.classify(SimpleNamespace(returncode=1, stdout=b"FAIL test_x AssertionError",
                                       stderr=b"")) == mp.KILLED
    assert mp.classify(SimpleNamespace(returncode=0, stdout=b"0 failed", stderr=b"")) == \
        mp.SURVIVED


def test_l2_every_quote_was_reread_and_an_unread_one_is_unknown():
    assert CS.SOURCES
    for key, src in CS.SOURCES.items():
        assert src.verified.startswith(CS.ACCESSED), key
    original = CS.SOURCES["hc_toy_tips"]
    CS.SOURCES["hc_toy_tips"] = dataclasses.replace(original, verified="")
    try:
        profile = ("base", "face", "stuffed")
        lines = CS.section_lines(profile, small_parts_clear=True)
        text = " ".join(f"{h} {t}" for h, t in lines)
        cit = {c.code: c.state for c in CS._text_checks(text, profile)}["CITATIONS"]
        assert cit == CS.UNKNOWN
    finally:
        CS.SOURCES["hc_toy_tips"] = original


def test_a_face_named_without_eyes_or_nose_must_still_say_it_is_embroidered():
    """Kills "features: a face need not be embroidered": the face word alone, with no eye or
    nose for the clause rule to read, still needs an embroidery instruction."""
    cir = _toy()
    body = cir.components[0]
    plain = dataclasses.replace(body, note="Worked from the top down. Give it a friendly face.")
    faceless = _with(cir, components=[plain] + cir.components[1:],
                     designer_notes="A ball-body bear.",
                     assembly=[dataclasses.replace(cir.assembly[0],
                                                   note="sew through both loops; bury the "
                                                        "tail")],
                     materials=[m for m in cir.materials if "embroider" not in m.name])
    texts = " ".join(CS._instruction_texts(faceless))
    assert "face" in texts and "embroider" not in texts.lower()
    assert all(CS._unembroidered_feature(t) is None for t in CS._instruction_texts(faceless))
    check = {c.code: c for c in CS.evaluate(faceless).checks}["FEATURES_EMBROIDERED"]
    assert check.state == CS.FAIL and "embroidered" in check.detail, check


def test_a_hard_part_that_is_not_a_feature_fails_in_the_printed_instructions():
    """Kills "text: hard parts in instructions unread": no eye or nose for the clause rule."""
    probes = ("Sew two buttons to the tummy.", "Add a jingle bell inside.",
              "Finish with press studs.")
    assert probes
    for line in probes:
        assert CS._unembroidered_feature(line) is None, line
        checks = CS._text_checks("x", ("base",), instructions=line)
        assert {c.code: c.state for c in checks}["NO_HARD_PARTS_IN_TEXT"] == CS.FAIL, line


# ---- ENG-PLUSH-FIX round 2: one test per reviewer probe ----------------------------------------
# Every probe the review of 2763340b listed is its own test, so a probe that stops failing is
# named in the run, not hidden inside a loop that another probe already satisfied.

def _probe_material_hard_part(material):
    def test():
        v = CS.evaluate(_with(_toy(), materials=_toy().materials + [Material(name=material)]))
        states = {c.code: c.state for c in v.checks}
        assert states["FEATURES_EMBROIDERED"] == CS.FAIL, (material, states)
        assert v.verdict != CS.VERDICT_PASS, material
    return test


def _probe_note_cord(note):
    def test():
        cir = _toy()
        v = CS.evaluate(_with(cir, designer_notes=(cir.designer_notes or "") + " " + note))
        assert {c.code: c.state for c in v.checks}["NO_CORDS_OR_LOOPS"] == CS.FAIL, note
        assert v.verdict == CS.VERDICT_FAIL, note
    return test


def _probe_material_cord(material):
    def test():
        cir = _toy()
        v = CS.evaluate(_with(cir, materials=cir.materials + [Material(name=material)]))
        assert {c.code: c.state for c in v.checks}["NO_CORDS_OR_LOOPS"] == CS.FAIL, material
        assert v.verdict == CS.VERDICT_FAIL, material
    return test


def _slug(text):
    import re as _re

    return _re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


assert len(M1_MATERIAL_PROBES) == 12 and len(M2_NOTE_PROBES) == 5 \
    and len(M2_MATERIAL_PROBES) == 3
for _p in M1_MATERIAL_PROBES:
    globals()[f"test_probe_m1_material_{_slug(_p)}"] = _probe_material_hard_part(_p)
for _p in M2_NOTE_PROBES:
    globals()[f"test_probe_m2_note_{_slug(_p)}"] = _probe_note_cord(_p)
for _p in M2_MATERIAL_PROBES:
    globals()[f"test_probe_m2_material_{_slug(_p)}"] = _probe_material_cord(_p)


def test_probe_m2_chain_ops_ch6_ch6_ch6_in_one_round():
    cir = _toy()
    ear = cir.components[1]
    rows = list(ear.rows)
    rows[-1] = dataclasses.replace(rows[-1], ops=[Op("sc", 10), Op("ch", 6), Op("ch", 6),
                                                  Op("ch", 6), Op("sc", 10)])
    bad = _with(cir, components=[cir.components[0], dataclasses.replace(ear, rows=rows)])
    assert _codes(bad)["NO_CORDS_OR_LOOPS"] == CS.FAIL


def test_probe_m2_chain_repeat_ch6_times_5_in_one_round():
    from brambleloop.cir.model import Repeat

    cir = _toy()
    ear = cir.components[1]
    rows = list(ear.rows)
    rows[-1] = dataclasses.replace(rows[-1], ops=[Op("sc", 10), Repeat([Op("ch", 6)], times=5),
                                                  Op("sc", 10)])
    bad = _with(cir, components=[cir.components[0], dataclasses.replace(ear, rows=rows)])
    assert _codes(bad)["NO_CORDS_OR_LOOPS"] == CS.FAIL


# ---- attachments are an allow-list ------------------------------------------------------------

ATTACHMENT_PROBES = ("Sew on the felt heart.", "Attach the plastic charm holder.",
                     "Glue the label in place.", "Clip on the soother holder.",
                     "Fasten the bow tie with a pin.")


def _probe_attachment(note):
    def test():
        cir = _toy()
        v = CS.evaluate(_with(cir, designer_notes=(cir.designer_notes or "") + " " + note))
        states = {c.code: c.state for c in v.checks}
        assert states["ATTACHMENTS_KNOWN"] == CS.UNKNOWN, (note, states)
        assert v.verdict != CS.VERDICT_PASS, note
    return test


assert len(ATTACHMENT_PROBES) == 5
for _p in ATTACHMENT_PROBES:
    globals()[f"test_probe_attachment_{_slug(_p)}"] = _probe_attachment(_p)


def test_attaching_the_patterns_own_pieces_or_yarn_is_known():
    cir = _toy()
    assert _codes(cir)["ATTACHMENTS_KNOWN"] == CS.PASS
    known = ("Sew the ears to the head.", "Attach yarn at the back loop.",
             "Sew on both ear pieces across the whole edge.")
    assert known
    for note in known:
        ok = _with(cir, designer_notes=(cir.designer_notes or "") + " " + note)
        assert _codes(ok)["ATTACHMENTS_KNOWN"] == CS.PASS, note


def test_an_unknown_attachment_on_a_flat_baby_blanket_holds_it():
    from brambleloop.products import inventory

    cir = inventory._engineered("cloudline-baby-blanket")
    assert CS.evaluate(cir).verdict == CS.VERDICT_PASS
    held = _with(cir, designer_notes=(cir.designer_notes or "") + " Sew on the felt heart.")
    v = CS.evaluate(held)
    assert {c.code: c.state for c in v.checks}["ATTACHMENTS_KNOWN"] == CS.UNKNOWN
    assert v.verdict == CS.VERDICT_HELD


# ---- eye options: embroidered is the default for baby and under 3 -----------------------------

def test_eye_options_default_to_embroidered_and_allow_only_embroidered():
    bands = ("under_3", "three_to_six", "six_to_twelve", "over_twelve", None, "no-such-band")
    assert bands
    for band in bands:
        opts = CS.eye_options(band)
        assert opts["default"] == CS.EYE_DEFAULT == "embroidered", band
        assert opts["allowed"] == ("embroidered",), band
        assert opts["text"].startswith(CS.EYE_OPTIONS_MARKER), band
        assert CS.AGE_GUIDANCE_MARKER in opts["text"], band
    # A baby or a child under 3: the only option, with its age guidance.
    young = ((None, ()), ("under_3", ()), ("three_to_six", ("base", "sleep")),
             ("no-such-band", ()))
    assert young
    for band, profile in young:
        opts = CS.eye_options(band, profile)
        assert opts["young"], band
        assert "for a baby or a child under 3 it is the only option" in opts["text"], band
        assert "0 to 36 months" in opts["text"], band
    older = CS.eye_options("three_to_six")
    assert not older["young"] and "3 to under 6 years" in older["text"]
    assert "Not for children under 3 yrs." in older["text"]


def test_eye_options_are_required_with_age_guidance_on_a_face_or_stuffed_item():
    assert "eye_options" in CS.required_statements(("base", "face"))
    assert "eye_options" in CS.required_statements(("base", "stuffed"))
    assert "eye_options" not in CS.required_statements(("base", "sleep"))
    lines = dict(CS.section_lines(("base", "face", "stuffed"), small_parts_clear=True))
    assert lines["Eye options"] == CS.eye_options(None)["text"]
    older = dict(CS.section_lines(("base", "face"), age_band="six_to_twelve"))
    assert "6 to 12 years" in older["Eye options"]
    # A document whose eye options lose their age guidance fails the text check.
    full = " ".join([CS.SECTION_HEADING] + [f"{h} {t}" for h, t in CS.section_lines(
        ("base", "face"), small_parts_clear=True)])
    ok = {c.code: c.state for c in CS._text_checks(full, ("base", "face"))}
    assert ok["AGE_GUIDANCE_IN_TEXT"] == CS.PASS and ok["SAFETY_SECTION"] == CS.PASS, ok
    cut = full.replace(CS.AGE_GUIDANCE_MARKER, "")
    bad = {c.code: c.state for c in CS._text_checks(cut, ("base", "face"))}
    assert bad["AGE_GUIDANCE_IN_TEXT"] == CS.FAIL, bad
    gone = full.replace(CS.EYE_OPTIONS_MARKER, "")
    assert {c.code: c.state for c in CS._text_checks(gone, ("base", "face"))
            }["SAFETY_SECTION"] == CS.FAIL


def test_the_toy_and_lovey_pdfs_print_the_eye_options_and_age_guidance():
    import re as _re

    cases = ((_toy(), TOY), (_toy(), ("amigurumi_toy", "three_to_six")))
    assert cases
    for cir, childrens in cases:
        doc = pdf.build_pattern_pdf(cir, childrens=childrens)
        text = pdf.extracted_text(doc.pdf_bytes)
        flat = _re.sub(r"\s+", " ", text)
        assert "Eye options" in flat, childrens
        assert CS.EYE_OPTIONS_MARKER in flat, childrens
        assert CS.AGE_GUIDANCE_MARKER in flat, childrens
        if childrens[1] == "under_3":
            assert "for a baby or a child under 3 it is the only option" in flat
            assert "0 to 36 months" in flat
        else:
            # The older reading, not the under-3 one (the band label alone also appears in
            # the children's statements, so it cannot tell the readings apart).
            assert "this design is assigned to 3 to under 6 years" in flat
            assert "for a baby or a child under 3 it is the only option" not in flat
        v = CS.evaluate(cir, text=text, childrens=childrens,
                        instructions=writer.write_pattern(cir, compile_cir(cir), "US"))
        states = {c.code: c.state for c in v.checks}
        assert states["AGE_GUIDANCE_IN_TEXT"] == CS.PASS, states
        assert states["SAFETY_SECTION"] == CS.PASS, states


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
