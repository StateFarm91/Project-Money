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
    assert cir.components and all(c.rows for c in cir.components)
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
    assert states == {"FEATURES_EMBROIDERED": CS.PASS, "JOINS_VALIDATED": CS.PASS,
                      "NO_CORDS_OR_LOOPS": CS.PASS, "STUFFING_GUIDANCE": CS.PASS,
                      "SMALL_PARTS": CS.PASS, "PHYSICAL_EVIDENCE": CS.UNKNOWN}, states
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
    assert codes == ["CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN", "PHYSICAL_TEST_REQUIRED"], \
        out["certified"]["reasons"]
    lovey = ("lovey", "under_3")                         # a TEST assignment
    result = compile_cir(cir)
    for terms in ("US", "UK"):
        doc = pdf.build_pattern_pdf(cir, terminology=terms, childrens=lovey)
        text = pdf.extracted_text(doc.pdf_bytes)
        assert cir.components and all(c.rows for c in cir.components)
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
