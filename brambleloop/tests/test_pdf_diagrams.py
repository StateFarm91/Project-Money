"""ENG-PDF-DIAGRAMS: per-component diagrams, placed assembly, eye options and the techniques
appendix in the premium PDF, held by the PremiumStandard checker on the rendered bytes.

Benchmarks: TEARDOWN_HIGHLAND_COW_AMIGURUMI (W1, L3, L4) and TEARDOWN_MADELINEMAECO_CAPYBARA
(M2, L4): progress imagery at every component is the #1 trust driver. With no physical
sample, the slot holds a deterministic CIR-drawn silhouette at finished size, with round
markers, labelled DIAGRAM and never presented as a photo.

- The amigurumi template document (the test fixture; never a product) passes the four new
  rules in both editions, and the template's own audit still passes.
- A mutation per rule, each failing that rule by id (AMI_MUTATIONS; test_premium_standard's
  every-rule-has-a-mutation check reads it).
- UNKNOWN is never PASS: a technique the appendix cannot explain, a missing gauge, a seam
  with no round placement, a piece with no counted rows all FAIL the rule and refuse the build.
- The appendix is derived from the CIR stitch set, in the edition's terms, and no template
  spells a terminology-sensitive stitch name.
"""
from __future__ import annotations

import dataclasses
import math
import re
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT), str(ROOT / "tests")]

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import Component, Op  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.publish import pdf as P  # noqa: E402
from brambleloop.publish import premium_standard as S  # noqa: E402
from brambleloop.publish import pdf_template as T  # noqa: E402
from brambleloop.publish import technique_appendix as TA  # noqa: E402

RELEASED = date(2026, 11, 20)
NEW_RULES = ("component_diagrams", "assembly_steps", "eye_options", "techniques_appendix")


def _fx():
    import fixture_amigurumi as F

    return F


def _stubbed_facts():
    """LAYOUT-ONLY (as test_pdf_template._ami_doc): the stuffed toy's width x height, which
    the twin refuses, is stubbed so the amigurumi pages can be built. Never a product path."""
    orig = P.childrens_facts

    def stub(cir, twin, audience):
        fx = orig(cir, twin, audience)
        return dataclasses.replace(fx, finished_size_cm=(11.0, 16.0),
                                   fibres=fx.fibres or ("cotton",),
                                   fibre_read_from=fx.fibre_read_from or "test stub")
    return orig, stub


def _build(cir, terminology="US"):
    F = _fx()
    orig, stub = _stubbed_facts()
    P.childrens_facts = stub
    try:
        return T.build_template_pdf(cir, terminology=terminology, released_on=RELEASED,
                                    gallery=T.test_double_gallery(), childrens=F.CHILDRENS)
    finally:
        P.childrens_facts = orig


@lru_cache(maxsize=None)
def _doc(terminology="US"):
    return _build(_fx().pebble_friend(), terminology)


@lru_cache(maxsize=None)
def _text(terminology="US") -> str:
    return P.extracted_text(_doc(terminology).pdf_bytes)


def _ctx(terminology="US", cir=None) -> S.Context:
    cir = cir or _fx().pebble_friend()
    r = compile_cir(cir)
    return S.context(cir, build_twin(cir, r), r, terminology, childrens=True)


def _rule(rule_id):
    return next(r for r in S.RULES if r.id == rule_id)


# ---- the document has them, and the checker sees them ---------------------------------------

def test_the_amigurumi_document_passes_the_four_new_rules_in_both_editions():
    for term in ("US", "UK"):
        doc = _doc(term)
        a = S.audit(doc.pdf_bytes, _fx().pebble_friend(), terminology=term, childrens=True)
        assert a.family == S.AMIGURUMI
        assert set(NEW_RULES) <= set(a.required), a.required
        assert not set(NEW_RULES) & set(a.failures), {k: a.failures[k] for k in NEW_RULES
                                                     if k in a.failures}
        # the template's own audit (page order now ends with the appendix) still passes
        ta = T.audit(doc.pdf_bytes, expected_gallery=doc.gallery)
        assert ta["verdict"] == "PASS", [c for c in ta["checks"] if c["status"] != "PASS"]
        assert ta["sections"][-1] == "appendix" and "copyright" in ta["sections"]


def test_every_component_has_a_diagram_at_its_finished_silhouette_with_round_markers():
    cir = _fx().pebble_friend()
    doc = _doc()
    figs = {f["component"]: f for f in doc.figures if f["kind"] == "component_diagram"}
    assert set(figs) == {c.name for c in cir.components}
    g = cir.gauge
    st, rw = 10 / g.stitches_per_10cm, 10 / g.rows_per_10cm
    for comp in cir.components:
        f = figs[comp.name]
        counts = [r.declared_count for r in comp.rows]
        assert f["label"] == "DIAGRAM"
        # independent recomputation from the stitch counts and the gauge
        assert f["across_cm"] == round(max(counts) * st / math.pi, 1)
        assert f["around_cm"] == round(max(counts) * st, 1)
        assert f["length_cm"] == round(len(counts) * rw, 1)
        assert f["markers"][0] == 1 and f["markers"][-1] == len(counts)
    text = _text()
    assert "DIAGRAM of the head, to scale at gauge" in text
    assert "6.4 cm across its widest round (20.0 cm around)" in text
    assert "8.6 cm of fabric from round 1 to round 17" in text
    assert "Round markers: R1, R6, R15, R17." in text
    # labelled a diagram, never a photo: no diagram caption claims a photograph
    captions = list(re.finditer(r"DIAGRAM of the .*?not a photograph\.", text))
    assert len(captions) == len(cir.components)
    for m in captions:
        assert not re.search(r"photograph of|progress photo", m.group(0), re.I), m.group(0)


def test_assembly_is_numbered_with_placement_callouts_tied_to_round_numbers():
    text = _text()
    i1, i2 = text.find("A1"), text.find("A2")
    p1 = text.find("Placement: round 12 of the body.")
    p2 = text.find("Placement: rounds 5 to 7 of the head, 6 sts either side of centre.")
    assert 0 <= i1 < p1 < i2 < p2, (i1, p1, i2, p2)
    placed = [f for f in _doc().figures if f["kind"] == "placement_diagram"]
    assert [p["rounds"] for p in placed] == [[12, 12], [5, 7]]


def test_the_eye_options_panel_gives_both_options_and_age_guidance():
    sec = S._section(_text(), "EYE OPTIONS", ("Safety notes for a children's item",))
    assert "Embroidered eyes (as written)" in sec
    assert "Safety eyes are not part of this pattern" in sec     # none in the materials
    assert "Age guidance:" in sec and "under 3" in sec
    # with safety eyes in the certified materials, they are offered WITH the warning
    from brambleloop.cir.model import Material
    cir = _fx().pebble_friend()
    cir = dataclasses.replace(cir, materials=cir.materials + [
        Material(name="9 mm safety eyes with washers")])
    facts = T._Facts.__new__(T._Facts)
    facts.cir = cir
    lines = T._Facts.eye_options(facts)
    joined = " ".join(lines)
    assert "Safety eyes: 9 mm safety eyes with washers" in joined
    assert "never use them on a toy for a child under 3" in joined
    assert T.EYE_AGE_GUIDANCE in lines


def test_the_appendix_is_generated_from_the_cir_stitch_set_in_the_editions_terms():
    cir = _fx().pebble_friend()
    us = [e.name for e in TA.entries(cir, "US")]
    uk = [e.name for e in TA.entries(cir, "UK")]
    assert "Single crochet (sc)" in us and "Single crochet decrease (dec)" in us
    assert "Double crochet (dc)" in uk and not any("Single crochet" in n for n in uk)
    assert {"Starting in a magic ring", "Working in joined rounds", "Stuffing", "Whipstitch",
            "Fastening off", "Weaving in ends"} <= set(us)
    # derived, not fixed: a new stitch, a flat piece and a new seam each add their entry
    extra = Component(name="scarf", construction="flat_rows", foundation=8, rows=[
        dataclasses.replace(cir.components[0].rows[0], index=1,
                            ops=[Op("bpdc", 8)], declared_count=8, turning_chain=2)])
    grown = dataclasses.replace(cir, components=cir.components + [extra], assembly=[
        dataclasses.replace(cir.assembly[0], method="mattress")])
    keys = [k for k, _w in TA.required(grown)]
    assert {"stitch:bpdc", "worked:flat_rows", "start:chain", "stitch:ch",
            "seam:mattress"} <= set(keys)
    assert "seam:whipstitch" not in keys
    names = [e.name for e in TA.entries(grown, "US")]
    assert any(n.startswith("Back post double crochet") for n in names)
    assert "Mattress stitch" in names
    # the appendix's text is in the UK document, in UK terms
    text = _text("UK")
    sec = text[text.find(TA.HEADING):]
    assert "Double crochet decrease (dc dec)" in sec and "(sc)" not in sec


def test_no_appendix_template_spells_a_terminology_sensitive_stitch_name():
    assert TA.literal_stitch_names() == ()


def test_the_engine_layout_prints_the_appendix_too():
    from tests.test_premium_standard import _text as engine_text

    text = engine_text("hexagon_coasters")
    sec = text[text.find(TA.HEADING):]
    assert TA.HEADING in text and "Starting in a magic ring" in sec and "Changing colour" in sec


def test_the_engine_layout_gives_an_amigurumi_the_same_parts():
    """The engine renders plush toys (ENG-PLUSH): diagrams under each piece, A-numbered
    assembly with placement callouts, and the child-safety gate's eye options panel."""
    import test_eng_plush as TP

    cir = TP._toy()
    doc = P.build_pattern_pdf(cir, childrens=TP.TOY, released_on=RELEASED)
    assert doc.standard["ok"] and set(NEW_RULES) <= set(doc.standard["required"]), \
        doc.standard["failures"]
    drawn = {f["component"] for f in doc.figures if f["kind"] == "component_diagram"}
    assert drawn == {c.name for c in cir.components}
    assert [f["rounds"] for f in doc.figures if f["kind"] == "placement_diagram"] == [[6, 6]]
    text = P.extracted_text(doc.pdf_bytes)
    assert "Placement: round 6 of the body, 5 sts either side of centre." in text


def test_a_flat_piece_gets_a_diagram_at_its_width():
    cir = _fx().pebble_friend()
    flat = Component(name="tag", construction="flat_rows", foundation=10, rows=[
        dataclasses.replace(cir.components[0].rows[0], index=i, ops=[Op("sc", 10)],
                            declared_count=10, note=None) for i in (1, 2, 3, 4)])
    cir = dataclasses.replace(cir, components=cir.components + [flat])
    geo = T.component_geometry(cir, flat)
    assert geo["flat"] and geo["across_cm"] == round(10 * 10 / cir.gauge.stitches_per_10cm, 1)
    assert geo["around_cm"] is None and geo["markers"] == [1, 4]
    img = T.component_profile(cir, flat)
    assert img.size == (T.PROFILE_PX, T.PROFILE_PX)


def test_an_amigurumi_flat_part_keeps_its_component_diagram_and_gets_no_row_progress_stage():
    """BATCH19D reconciliation: a pattern with any piece in rounds is drawn by the component
    diagrams (ENG-PDF-DIAGRAMS), never also by construction_diagrams' row-progress stages."""
    from brambleloop.publish import construction_diagrams as CD

    cir = _fx().pebble_friend()
    flat = Component(name="tag", construction="flat_rows", foundation=10, rows=[
        dataclasses.replace(cir.components[0].rows[0], index=i, ops=[Op("sc", 10)],
                            declared_count=10, note=None) for i in (1, 2, 3, 4)])
    cir = dataclasses.replace(cir, components=cir.components + [flat])
    assert CD._flat_geometry(cir) is None
    assert not [st for st in CD.stages(cir) if st.part == "flat"]


# ---- BATCH19D: row-progress diagrams for flat row-worked pieces ----------------------------

@lru_cache(maxsize=None)
def _blanket():
    from brambleloop.products import launch0

    cir = launch0.cir_for("cloudline_blanket")
    return cir, build_twin(cir, compile_cir(cir), component=cir.components[0].name)


def test_a_flat_piece_gets_row_progress_diagrams_at_its_finished_size():
    from brambleloop.publish import construction_diagrams as CD

    cir, twin = _blanket()
    st = CD.stages(cir)
    rows = sorted({c.row for c in twin.cells})
    assert st and all(s.part == "flat" for s in st), [s.part for s in st]
    assert len(st) <= CD.MAX_FLAT_STAGES and st[-1].round == rows[-1]
    assert [s.round for s in st] == CD.stage_rounds(cir)
    # every row belongs to exactly one stage, in order, from the first row
    assert st[0].first == rows[0]
    assert all(b.first == a.round + 1 for a, b in zip(st, st[1:]))
    for s in st:
        assert s.stitches == sum(1 for c in twin.cells if c.row == s.round)
        assert s.image().size == (CD.SIZE_PX, CD.SIZE_PX)
    cap = CD.flat_caption(st[2], cir)
    assert cap.startswith(f"DIAGRAM after row {st[2].round}: {st[2].stitches} stitches")
    assert f"{twin.width_cm:.1f} cm wide" in cap and f"of {twin.height_cm:.1f} cm" in cap
    assert f"{twin.row_top_cm[st[2].round]:.1f} of" in cap and cap.endswith(
        "not a photograph.")
    # deterministic: same CIR, same bytes
    assert [s.png for s in CD.stages(cir)] == [s.png for s in st]


def test_a_flat_diagram_draws_worked_rows_in_their_colours_and_the_rest_faint():
    from brambleloop.publish import construction_diagrams as CD
    from brambleloop.visual import disclosed_render as D

    cir, twin = _blanket()
    st = CD.stages(cir)
    first, last = st[0].image().convert("RGB"), st[-1].image().convert("RGB")
    palette = set(D._palette(cir).values())

    def near(px, colours, tol=24):
        return any(sum(abs(a - b) for a, b in zip(px, c)) <= tol for c in colours)

    # just under the top edge of the piece: still to work after the first stage (faint),
    # worked in a yarn colour after the last
    W, H = CD.SIZE_PX, CD.SIZE_PX
    probe = None
    for y in range(int(H * 0.10), int(H * 0.5)):
        if near(first.getpixel((W // 2, y)), [CD.FAINT], 6):
            probe = (W // 2, y + 3)
            break
    assert probe is not None, "no faint (still to work) area after the first stage"
    assert near(first.getpixel(probe), [CD.FAINT], 6)
    assert near(last.getpixel(probe), palette), last.getpixel(probe)


def test_the_engine_flat_pdf_passes_the_sale_diagrams_check_and_fails_without_it():
    """The sale checker's `diagrams` check FAILed every flat piece before BATCH19D (no stage
    diagram was drawn), so no flat product could become READY. A mutation that removes the
    row-progress diagrams must FAIL it again, by id."""
    from brambleloop.publish import construction_diagrams as CD
    from brambleloop.publish import pdf_standard as PS

    cir, _twin = _blanket()

    def diagrams():
        b = P.build_pattern_pdf(cir, terminology="US", released_on=RELEASED).pdf_bytes
        doc = PS.read(b)
        got = {c["check"]: c for c in PS._schematic_and_diagrams(doc, set())}
        return got["diagrams"], doc

    ok, doc = diagrams()
    assert ok["status"] == PS.PASS and ok["count"] >= 1, ok
    text = "\n".join(p["text"] for p in doc["pages"])
    assert "construction diagram of the rows worked so far" in re.sub(r"\s+", " ", text)
    # the premium standard's inline_diagrams rule reads the same words
    assert S._diagrams(re.sub(r"\s+", " ", text), None) == []
    real = CD._flat_geometry
    CD._flat_geometry = lambda c: None
    try:
        bad, _ = diagrams()
    finally:
        CD._flat_geometry = real
    assert bad["status"] == PS.FAIL, bad


def test_the_template_keeps_its_flat_mini_grids_and_takes_no_row_progress_stage():
    """BATCH19D reconciliation: the template already draws a flat piece's inline diagrams as
    mini-grids at the tricky rows; the row-progress stages are the engine layout's."""
    cir, _twin = _blanket()
    assert T._template_stages(cir) == []
    from brambleloop.products import launch0

    coaster = launch0.cir_for("hexagon_coasters")
    from brambleloop.publish import construction_diagrams as CD

    assert [s.png for s in T._template_stages(coaster)] == [s.png for s in CD.stages(coaster)]


def test_diagrams_are_deterministic():
    cir = _fx().pebble_friend()
    a = T.component_profile(cir, cir.components[0]).tobytes()
    b = T.component_profile(cir, cir.components[0]).tobytes()
    assert a == b


# ---- mutations: each new rule fails, by id, when its evidence is removed ----------------------

def _drop(*needles):
    def m(text):
        for n in needles:
            text = text.replace(n, "")
        return text
    return m


def _sub(pattern, repl):
    return lambda text: re.sub(pattern, repl, text)


AMI_MUTATIONS = {
    "component_diagrams": [
        _drop("DIAGRAM of the ear,"),
        _sub(r"6\.4 cm across", "6.9 cm across"),
        _sub(r"Round markers: R1, R6, R15, R17\.", "Round markers: R6, R15."),
        _sub(r"(DIAGRAM of the body,)", r"\1 Photograph of a worked sample,"),
        _sub(r"(DIAGRAM of the head.*?)not a photograph\.", r"\1a photo."),
    ],
    "assembly_steps": [
        _drop("Placement: round 12 of the body."),
        _sub(r"Placement: rounds 5 to 7 of the head", "Placement: rounds 4 to 7 of the head"),
        _sub(r"(?<![\w#])A2(?!\w)", ""),
        _drop("diagrams, not photographs"),
    ],
    "eye_options": [
        _drop("EYE OPTIONS"),
        _drop("Age guidance:"),
        _drop("Safety eyes are not part of this pattern"),
        _drop("Embroider"),
    ],
    "techniques_appendix": [
        _drop(TA.HEADING),
        _drop("Whipstitch"),
        _drop(TA.STUFF_HOW[1][:60]),
    ],
}


def test_each_new_rule_fails_by_id_when_its_evidence_is_removed():
    for term in ("US", "UK"):
        ctx = _ctx(term)
        text = _text(term)
        before = S.audit_text(text, ctx)
        for rule_id, mutations in sorted(AMI_MUTATIONS.items()):
            assert rule_id in before.required and rule_id not in before.failures, (
                term, rule_id, before.failures.get(rule_id))
            assert mutations, rule_id
            for n, mutate in enumerate(mutations):
                mutated = mutate(text)
                assert mutated != text, f"{rule_id}[{n}] changed nothing ({term})"
                after = S.audit_text(mutated, ctx)
                assert rule_id in after.failures, f"{rule_id}[{n}] did not fail ({term})"


# ---- UNKNOWN is never PASS ---------------------------------------------------------------------

def test_a_technique_the_appendix_cannot_explain_fails_the_rule_and_refuses_both_layouts():
    saved = dict(TA.STITCH_HOW)
    text, ctx = _text(), _ctx()
    try:
        del TA.STITCH_HOW["dec"]
        failures = _rule("techniques_appendix").check(text, ctx)
        assert failures and "cannot be generated" in failures[0], failures
        try:
            _build(_fx().pebble_friend())
        except T.TemplateBlocked as e:
            assert e.section == "appendix" and "'dec'" in str(e), e
        else:
            raise AssertionError("the template built an appendix that skips a technique")
        del TA.STITCH_HOW["inc"]
        from brambleloop.products import launch0
        try:
            P.build_pattern_pdf(launch0.cir_for("hexagon_coasters"), released_on=RELEASED)
        except ValueError as e:
            assert "'inc'" in str(e), e
        else:
            raise AssertionError("the engine built an appendix that skips a technique")
    finally:
        TA.STITCH_HOW.clear()
        TA.STITCH_HOW.update(saved)


def test_what_cannot_be_established_fails_never_passes():
    cir = _fx().pebble_friend()
    text = _text()
    # no gauge: no diagram can be checked at finished size
    ctx = dataclasses.replace(_ctx(), cir=dataclasses.replace(cir, gauge=None))
    assert _rule("component_diagrams").check(text, ctx)
    # a seam with no round placement
    seams = [dataclasses.replace(cir.assembly[0], at_round=None)] + cir.assembly[1:]
    ctx = dataclasses.replace(_ctx(), cir=dataclasses.replace(cir, assembly=seams))
    out = _rule("assembly_steps").check(text, ctx)
    assert out and "no round placement" in out[0], out
    # a piece with no counted rows cannot be drawn, so it cannot pass
    bare = dataclasses.replace(cir.components[2], rows=[
        dataclasses.replace(r, declared_count=None) for r in cir.components[2].rows])
    ctx = dataclasses.replace(_ctx(), cir=dataclasses.replace(
        cir, components=cir.components[:2] + [bare]))
    out = _rule("component_diagrams").check(text, ctx)
    assert out and "no counted rows" in out[0], out
    # a seam onto a piece the CIR does not have
    seams = [dataclasses.replace(cir.assembly[0], piece_b="tail")] + cir.assembly[1:]
    ctx = dataclasses.replace(_ctx(), cir=dataclasses.replace(cir, assembly=seams))
    assert _rule("assembly_steps").check(text, ctx)


def test_the_new_rules_apply_where_they_should():
    ctx = _ctx()
    need = {r.id for r in S.RULES if r.required_for(ctx)}
    assert set(NEW_RULES) <= need
    from tests.test_premium_standard import _ctx as engine_ctx
    coaster = {r.id for r in S.RULES if r.required_for(engine_ctx("hexagon_coasters"))}
    assert "techniques_appendix" in coaster
    assert not {"component_diagrams", "assembly_steps", "eye_options"} & coaster


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
