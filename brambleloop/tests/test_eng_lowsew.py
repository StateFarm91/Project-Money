"""ENG-LOWSEW-CHENILLE: join-as-you-go ("low-sew") chunky chenille amigurumi.

What this file proves, from the CIR outward:

* **Fold and close.** A limb tube is flattened and closed with a stated number of sc through
  both layers (`Row.fold`); the compiler halves the stitches available, and an odd opening,
  a fold that is not the last row or a fold in anything but sc / sl st is refused.
* **Joined rounds.** A limb is crocheted INTO a named body round at explicit stitches
  (`Op.through`); the joined round's count includes the stitches worked through it. Every
  joined round's count, positions and symmetry is checked by `cir.joins`, and every
  appendage's closing count must equal its join width. A head is joined by working its last
  round through the body's open last round.
* **Three proofs of the same placement.** The compiler (`joins.runs`), the twin's own cells
  (`twin.joined_runs`) and the reverse compiler (recomputed from the printed text alone)
  must agree, or certification fails.
* **Spiral drift.** A spiral host states its drift allowance in stitches, bounded by the gaps.
* **construction.sewing_required** (none / low / standard / UNKNOWN), carried on the
  certificate; "no sew" and "low sew" may appear in a title or tag ONLY when certified true.
* **Chenille / jumbo yarn class** (CYC 6-7): gauge per hook, hook range, tension and
  shedding/care text in the PDF, a wider yardage tolerance in the twin.
* **Eye options**: an embroidered variant always available, printed inside the child-safety
  section with the gate's age guidance.
* **Three ORIGINAL animals** (a penguin, a fox, an elephant): CIR -> compile, twin, reverse ->
  certification, withheld ONLY for physical evidence -- exactly as the plush bear.

Run: cd brambleloop && python3 tests/test_eng_lowsew.py
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

from brambleloop.cir import joins, reverse, writer, yarn_classes  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR, Component, Op, Row, Seam  # noqa: E402
from brambleloop.cir.twin import build_twin, joined_runs  # noqa: E402
from brambleloop.creative import construction_families as CF  # noqa: E402
from brambleloop.creative import lowsew  # noqa: E402
from brambleloop.gates import child_safety as CS  # noqa: E402
from brambleloop.gates import eye_options  # noqa: E402
from brambleloop.gates.certificate import certify, construction_reading  # noqa: E402

TOY = ("amigurumi_toy", "under_3")          # a TEST assignment, not an owner decision
HELD_ONLY = ["CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN", "PHYSICAL_TEST_REQUIRED"]


def _codes(result) -> set[str]:
    return {f.code for f in result.findings if f.is_error}


def _fox() -> CIR:
    return lowsew.draft(lowsew.FOX)


def _comp(cir: CIR, name: str) -> Component:
    return next(c for c in cir.components if c.name == name)


def _row(cir: CIR, name: str, index: int) -> Row:
    return next(r for r in _comp(cir, name).rows if r.index == index)


def _set_ops(cir: CIR, name: str, index: int, ops: list) -> CIR:
    cir = copy.deepcopy(cir)
    _row(cir, name, index).ops = ops
    return cir


# ---- the end-to-end proof --------------------------------------------------------------------


def test_three_original_animals_are_physical_gated_end_to_end():
    """CIR -> compile -> twin -> reverse (US, UK) -> certify, for each animal: withheld ONLY
    for the physical sample and the child-safety physical evidence."""
    from brambleloop.publish import pdf

    assert {a.kind for a in lowsew.ANIMALS} == {"penguin", "fox", "elephant"}
    for animal in lowsew.ANIMALS:
        cir = lowsew.draft(animal)
        result = compile_cir(cir)
        assert result.ok, [str(f) for f in result.errors]
        assert joins.uses_joins(cir)
        twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
        compiled = sorted((r.host, r.round, r.target, r.start, r.end, r.round_count)
                          for r in joins.runs(cir, result))
        assert compiled and joined_runs(twins) == compiled, animal.slug
        for terms in ("US", "UK"):
            text = writer.write_pattern(cir, result, terms)
            assert reverse.compare(cir, text, terms) == [], (animal.slug, terms)
            assert "Joining Rnd" in text and "Flatten the opening" in text
        cert = certify(cir)
        errors = sorted({f.code for f in cert.findings if f.is_error})
        assert errors == HELD_ONLY, (animal.slug, [str(f) for f in cert.errors])
        assert not cert.granted
        for stage in ("compile", "twin", "joins", "reverse", "child_safety"):
            assert stage in cert.stages_run, (stage, cert.stages_run)
        reading = cert.twin_summary["construction"]
        assert reading["sewing_required"] == joins.SEWING_LOW, reading
        assert reading["yarn_class"]["key"] == "chenille_6"
        assert len(reading["joined_runs"]) == len(compiled)
        verdict = CS.evaluate(cir, result)
        states = {c.code: c.state for c in verdict.checks}
        assert verdict.verdict == CS.VERDICT_HELD, states
        assert [c for c, s in states.items() if s != CS.PASS] == ["PHYSICAL_EVIDENCE"], states
        # The deliverable, both terminologies, with the safety section read back.
        for terms in ("US", "UK"):
            doc = pdf.build_pattern_pdf(cir, terminology=terms, childrens=TOY)
            pdf_text = pdf.extracted_text(doc.pdf_bytes)
            for comp in cir.components:
                for row in comp.rows:
                    count = result.row(comp.name, row.index).stitch_count
                    assert f"({count} sts)" in pdf_text, (animal.slug, terms, comp.name)
            low = pdf_text.lower()
            assert eye_options.HEADING in pdf_text and "hook range 6-8 mm" in low
            assert "shedding and care" in low and "tension with chenille" in low
            assert "make these first" in low and "joining rnd" in low
            assert CS.SECTION_HEADING in pdf_text
            v = CS.evaluate(cir, result, text=pdf_text, childrens=TOY,
                            instructions=writer.write_pattern(cir, result, terms))
            st = {c.code: c.state for c in v.checks}
            assert [c for c, s in st.items() if s != CS.PASS] == ["PHYSICAL_EVIDENCE"], st


def test_the_animals_are_original_and_not_the_benchmarks():
    names = " ".join(f"{a.title} {a.slug} {a.kind}" for a in lowsew.ANIMALS).lower()
    for word in ("capybara", "cara", "highland", "cow", "madeline"):
        assert word not in names, word
    titles = [a.title for a in lowsew.ANIMALS]
    assert len(set(titles)) == 3
    for animal in lowsew.ANIMALS:
        prov = lowsew.draft(animal).provenance
        assert prov.generated_by == "brambleloop" and prov.benchmarks_consulted == ()


def test_family_table_names_the_lowsew_engine_honestly():
    fam = CF.FAMILIES["lowsew_chenille"]
    assert fam.engine == "creative.lowsew.draft"
    # Not admitted to research intake until a title route exists; the proof exists.
    assert fam.status == CF.PARTIAL and fam.status not in CF.ADMITTED_STATUSES
    path, name = fam.proof.split("::")
    assert path == "tests/test_eng_lowsew.py" and name in globals()
    assert "no research title route" in fam.gaps


# ---- fold and close ---------------------------------------------------------------------------


def test_fold_close_halves_the_opening_and_is_the_join_width():
    cir = _fox()
    result = compile_cir(cir)
    leg = _comp(cir, "leg")
    last = result.row("leg", leg.rows[-1].index)
    assert last.fold and last.into_count == 6 and last.stitch_count == 6
    assert result.row("leg", leg.rows[-2].index).stitch_count == 12
    assert joins.join_edge(leg, result) == ("fold", 6)
    tail = _comp(cir, "tail")
    assert joins.join_edge(tail, result) == ("fold", 9)


def test_fold_close_refuses_odd_openings_wrong_stitches_and_a_fold_mid_piece():
    cir = _fox()
    leg = _comp(cir, "leg")
    i = leg.rows[-1].index
    bad = _set_ops(cir, "leg", i, [Op("dec", 6)])
    assert "FOLD_STITCH" in _codes(compile_cir(bad))
    odd = copy.deepcopy(cir)
    rows = _comp(odd, "leg").rows
    rows[-2].ops = [Op("sc", 11), Op("inc")]
    rows[-2].declared_count = 13
    assert "FOLD_ODD" in _codes(compile_cir(odd))
    mid = copy.deepcopy(cir)
    rows = _comp(mid, "leg").rows
    rows.append(Row(index=rows[-1].index + 1, ops=[Op("sc", 6)], declared_count=6,
                    color=rows[-1].color))
    codes = _codes(compile_cir(mid))
    assert "FOLD_NOT_LAST" in codes


def test_a_fold_closed_piece_never_attached_is_refused():
    cir = copy.deepcopy(_fox())
    # Work the tail's round as plain sc: the tail is fold-closed but never crocheted in.
    _row(cir, "body", 8).ops = [Op("sc", 30)]
    codes = _codes(compile_cir(cir))
    assert "JOIN_UNATTACHED" in codes and "JOIN_DRIFT_TOO_WIDE" not in codes


# ---- joined rounds ----------------------------------------------------------------------------


def test_the_joined_round_count_includes_the_stitches_worked_through_the_limb():
    cir = _fox()
    result = compile_cir(cir)
    row = result.row("body", 6)
    through = sum(o.count for o in row.ops if o.through == "leg")
    assert through == 12
    assert row.stitch_count == 30 and _row(cir, "body", 6).declared_count == 30
    runs = [r for r in joins.runs(cir, result) if r.host == "body" and r.round == 6]
    assert [(r.target, r.start, r.end) for r in runs] == [("leg", 1, 6), ("leg", 10, 15)]
    # A miscounted joined round is a count mismatch like any other.
    bad = copy.deepcopy(cir)
    _row(bad, "body", 6).declared_count = 18
    assert "COUNT_MISMATCH" in _codes(compile_cir(bad))


def test_a_head_is_joined_by_working_through_both_pieces():
    cir = _fox()
    result = compile_cir(cir)
    head = _comp(cir, "head")
    last = head.rows[-1]
    assert all(o.through == "body" for o in last.ops)
    full = [r for r in joins.runs(cir, result) if r.host == "head" and r.target == "body"]
    assert len(full) == 1 and full[0].full_round and full[0].width == 18
    assert joins.closed_by_join(cir, result, "body") and joins.closed_by_join(cir, result, "head")
    assert head.stuff_at_round == head.rows[-2].index


def test_join_width_must_equal_the_appendage_closing_count():
    bad = _set_ops(_fox(), "body", 6, [Op("sc", 5, through="leg"), Op("sc", 4),
                                       Op("sc", 6, through="leg"), Op("sc", 15)])
    assert "JOIN_WIDTH_MISMATCH" in _codes(compile_cir(bad))


def test_every_instance_is_joined_once():
    bad = _set_ops(_fox(), "body", 6, [Op("sc", 6, through="leg"), Op("sc", 24)])
    assert "JOIN_INSTANCES" in _codes(compile_cir(bad))


def test_limbs_are_mirrored_about_one_line():
    # The tail moved one stitch off the legs' mirror line.
    bad = _set_ops(_fox(), "body", 8, [Op("sc", 19), Op("sc", 9, through="tail"), Op("sc", 2)])
    assert "JOIN_ASYMMETRIC" in _codes(compile_cir(bad))
    # Elephant: the back legs shifted off the front legs' line.
    ele = lowsew.draft(lowsew.ELEPHANT)
    shifted = _set_ops(ele, "body", 7, [Op("sc", 6, through="front_leg"), Op("sc", 3),
                                        Op("sc", 6, through="front_leg"), Op("sc", 4),
                                        Op("sc", 6, through="back_leg"), Op("sc", 3),
                                        Op("sc", 6, through="back_leg"), Op("sc", 2)])
    assert "JOIN_ASYMMETRIC" in _codes(compile_cir(shifted))
    assert compile_cir(ele).ok


def test_runs_that_touch_or_a_split_pair_are_refused():
    touch = _set_ops(_fox(), "body", 6, [Op("sc", 6, through="leg"),
                                         Op("sc", 6, through="leg"), Op("sc", 18)])
    codes = _codes(compile_cir(touch))
    # Two adjacent runs of one piece read as one 12-wide run: the width is wrong.
    assert "JOIN_WIDTH_MISMATCH" in codes or "JOIN_RUNS_TOUCH" in codes
    ele = lowsew.draft(lowsew.ELEPHANT)
    touch2 = _set_ops(ele, "body", 7, [Op("sc", 6, through="front_leg"), Op("sc", 3),
                                       Op("sc", 6, through="front_leg"),
                                       Op("sc", 6, through="back_leg"), Op("sc", 3),
                                       Op("sc", 6, through="back_leg"), Op("sc", 6)])
    assert "JOIN_RUNS_TOUCH" in _codes(compile_cir(touch2))
    split = copy.deepcopy(_fox())
    _row(split, "body", 6).ops = [Op("sc", 6, through="leg"), Op("sc", 24)]
    _row(split, "body", 7).ops = [Op("sc", 9), Op("sc", 6, through="leg"), Op("sc", 15)]
    assert "JOIN_PAIR_SPLIT" in _codes(compile_cir(split))


def test_unknown_self_cyclic_and_closed_targets_are_refused():
    unknown = _set_ops(_fox(), "body", 7, [Op("sc", 6, through="wing"), Op("sc", 24)])
    assert "JOIN_UNKNOWN_PIECE" in _codes(compile_cir(unknown))
    selfj = _set_ops(_fox(), "body", 7, [Op("sc", 6, through="body"), Op("sc", 24)])
    assert "JOIN_SELF" in _codes(compile_cir(selfj))
    cyc = _set_ops(_fox(), "body", 9, [Op("sc", 6, through="head"), Op("sc", 24)])
    assert "JOIN_CYCLE" in _codes(compile_cir(cyc))
    pen = lowsew.draft(lowsew.PENGUIN)
    closed = copy.deepcopy(pen)
    closed.components.append(Component(
        name="hat", construction="spiral_rounds", foundation_kind="magic_ring",
        rows=[Row(1, [Op("sc", 6)], 6, color="charcoal"),
              Row(2, [Op("sc", 6, through="body")], 6, color="charcoal")]))
    assert "JOIN_TARGET_CLOSED" in _codes(compile_cir(closed))


def test_a_joining_stitch_is_sc_or_slst():
    bad = _set_ops(_fox(), "body", 6, [Op("hdc", 6, through="leg"), Op("sc", 3),
                                       Op("sc", 6, through="leg"), Op("sc", 15)])
    assert "JOIN_STITCH" in _codes(compile_cir(bad))


def test_drift_is_stated_and_bounded_by_the_gaps():
    unstated = copy.deepcopy(_fox())
    _comp(unstated, "body").join_drift_sts = None
    assert "JOIN_DRIFT_UNSTATED" in _codes(compile_cir(unstated))
    wide = copy.deepcopy(_fox())
    _comp(wide, "body").join_drift_sts = 2          # the legs are 3 sts apart: limit 1
    assert "JOIN_DRIFT_TOO_WIDE" in _codes(compile_cir(wide))
    over = copy.deepcopy(_fox())
    _comp(over, "head").join_drift_sts = joins.JOIN_DRIFT_MAX + 1
    assert "JOIN_DRIFT_TOO_WIDE" in _codes(compile_cir(over))


def test_stuffed_pieces_are_closed_and_stuffed_before_the_join():
    open_body = copy.deepcopy(_fox())
    head = _comp(open_body, "head")
    head.rows.pop()                                   # the head is no longer joined on
    codes = _codes(compile_cir(open_body))
    assert "JOIN_STUFFED_OPEN" in codes
    late = copy.deepcopy(_fox())
    h = _comp(late, "head")
    h.stuff_at_round = h.rows[-1].index
    assert "JOIN_STUFF_AFTER_JOIN" in _codes(compile_cir(late))


def test_eye_placement_is_checked():
    for change, code in ((dict(eye_round=40), "EYE_ROUND_UNKNOWN"),
                         (dict(eye_gap_sts=20), "EYE_GAP"),
                         (dict(eye_gap_sts=None), "EYE_PLACEMENT_INCOMPLETE")):
        cir = copy.deepcopy(_fox())
        head = _comp(cir, "head")
        for k, v in change.items():
            setattr(head, k, v)
        assert code in _codes(compile_cir(cir)), code


# ---- twin and reverse -------------------------------------------------------------------------


def test_the_twin_carries_the_joined_runs_and_certify_refuses_a_disagreement():
    from brambleloop.gates.certificate import joins_twin_findings

    cir = _fox()
    result = compile_cir(cir)
    twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
    assert joins_twin_findings(cir, result, twins) == []
    moved = next(c for c in twins["body"].cells if c.row == 6 and c.through == "leg")
    moved.through = None
    found = joins_twin_findings(cir, result, twins)
    assert [f.code for f in found] == ["JOIN_TWIN_DISAGREES"]


def test_joined_stitches_cost_more_yarn_and_chenille_carries_its_own_tolerance():
    from brambleloop.cir import twin as T

    cir = _fox()
    result = compile_cir(cir)
    body = build_twin(cir, result, component="body")
    assert body.yardage_tolerance == yarn_classes.CHENILLE_6.yardage_tolerance == 0.30
    plain = _set_ops(cir, "body", 6, [Op("sc", 30)])
    plain_twin_rows = [r for r in compile_cir(plain).rows if r.component == "body"]
    joined_rows = [r for r in result.rows if r.component == "body"]
    assert T._yardage(joined_rows, cir, 1.0)["rust"] > T._yardage(plain_twin_rows, plain,
                                                                   1.0)["rust"]
    lo, hi = yarn_classes.grams(60.0, yarn_classes.CHENILLE_6)
    assert (lo, hi) == (60, 100)


def test_the_reverse_compiler_reads_every_join_back_from_the_text():
    cir = _fox()
    result = compile_cir(cir)
    text = writer.write_pattern(cir, result, "US")
    assert reverse.compare(cir, text, "US") == []
    probes = {
        "Joining Rnd 6 of 30 sts: leg 1 through sts 1-6; leg 2 through sts 10-15.":
            ("Joining Rnd 6 of 30 sts: leg 1 through sts 2-7; leg 2 through sts 10-15.",
             "REVERSE_JOIN_PLACEMENT"),
        "sc in next 9 sts through the tail edge": ("sc in next 9 sts", "REVERSE_MISMATCH"),
        "by up to 1 sts": ("by up to 3 sts", "REVERSE_JOIN_DRIFT"),
        "Eyes on Rnd 8, 4 sts apart": ("Eyes on Rnd 8, 6 sts apart", "REVERSE_EYES"),
        "Flatten the opening and work through both layers: sc in next 9 sts":
            ("sc in next 9 sts", "REVERSE_FOLD"),
        "ear (make 2).": ("ear (make 1).", "REVERSE_JOIN_ORDER"),
    }
    for old, (new, code) in probes.items():
        assert old in text, old
        tampered = text.replace(old, new, 1)
        got = {f.code for f in reverse.compare(cir, tampered, "US")}
        assert code in got, (old, got)


def test_the_cir_round_trips_and_old_digests_do_not_move():
    from brambleloop.creative import fallback_constructions as FC

    cir = _fox()
    again = CIR.from_json(cir.to_json())
    assert again.to_dict() == cir.to_dict() and again.fingerprint == cir.fingerprint
    assert _row(again, "leg", 6).fold and _comp(again, "body").join_drift_sts == 1
    assert any(o.through == "leg" for o in _row(again, "body", 6).ops)
    # A design that uses none of it serialises without the new keys.
    bear = FC.amigurumi(SimpleNamespace(slug="b", title="Ball Bear Amigurumi",
                                        category="amigurumi", colors={"MC": "#D8C9B0"},
                                        yarn_weight="worsted"))
    blob = bear.to_json()
    for key in ("through", "fold", "join_drift_sts", "eye_round", "eye_gap_sts"):
        assert f'"{key}"' not in blob, key
    assert not joins.uses_joins(bear)


# ---- sewing reading and the low-sew SEO gate --------------------------------------------------


def test_sewing_reading_is_none_low_standard_or_unknown():
    from brambleloop.creative import fallback_constructions as FC

    for animal in lowsew.ANIMALS:
        assert joins.sewing_required(lowsew.draft(animal))["sewing_required"] == "low"
    # A plush bear sews two ears on: standard, never low.
    bear = FC.amigurumi(SimpleNamespace(slug="b", title="Ball Bear Amigurumi",
                                        category="amigurumi", colors={"MC": "#D8C9B0"},
                                        yarn_weight="worsted"))
    r = joins.sewing_required(bear)
    assert r["sewing_required"] == "standard" and r["sewn_joins"] == 2, r
    # A fox with no embroidered eyes and no gathered closure needs no needle at all.
    bare = copy.deepcopy(_fox())
    head = _comp(bare, "head")
    head.eye_round = head.eye_gap_sts = None
    head.note = "Worked from the top down, stuffed, then joined to the body."
    bare.designer_notes = "A sitting fox."
    assert joins.sewing_required(bare)["sewing_required"] == "none"
    broken = _set_ops(_fox(), "body", 6, [Op("sc", 29)])
    assert joins.sewing_required(broken)["sewing_required"] == joins.SEWING_UNKNOWN


def test_low_sew_claims_need_the_certified_reading():
    f = joins.sewing_claim_findings
    assert f("Fox Pattern, Low Sew Chenille", "low") == []
    assert f("Fox Pattern, Low-Sew", "none") == []
    assert f("Fox Pattern, No Sew", "low")[0].startswith("SEW_CLAIM_UNCERTIFIED")
    assert f("No-sew fox", "none") == []
    for reading in ("standard", "UNKNOWN", None):
        assert f("low sew fox", reading), reading
        assert f("nosew fox", reading), reading
    assert f("Fox Pattern, Chenille", None) == []          # no claim, nothing to refuse
    for wording in ("sew-free", "without sewing", "minimal sewing", "zero sew"):
        assert joins.sewing_claims(wording), wording


def test_certify_refuses_an_uncertified_sewing_claim_in_the_title_or_listing():
    from brambleloop.creative import fallback_constructions as FC

    no_sew = dataclasses.replace(_fox(), title="Juniper the Fox No Sew Chenille Amigurumi")
    codes = {f.code for f in certify(no_sew).findings if f.is_error}
    assert "SEW_CLAIM_UNCERTIFIED" in codes
    low = dataclasses.replace(_fox(), title="Juniper the Fox Low Sew Chenille Amigurumi")
    assert "SEW_CLAIM_UNCERTIFIED" not in {f.code for f in certify(low).findings}
    # The ball-body route refuses the words in a title; a hand-retitled bear still sews two
    # ears on, so its "low sew" claim is refused at certification.
    bear = FC.amigurumi(SimpleNamespace(slug="b", title="Ball Bear Amigurumi",
                                        category="amigurumi", colors={"MC": "#D8C9B0"},
                                        yarn_weight="worsted"))
    bear = dataclasses.replace(bear, title="Low Sew Ball Bear Amigurumi")
    assert "SEW_CLAIM_UNCERTIFIED" in {f.code for f in certify(bear).findings}
    assert construction_reading(_fox())["sewing_required"] == "low"


def test_the_seo_validator_gates_low_sew_titles_and_tags():
    from brambleloop.seo import truth
    from brambleloop.seo.facts import ProductFacts, _add

    def facts(cir):
        vocab: dict = {}
        _add(vocab, cir.title + " pattern crochet low sew no amigurumi", "test")
        return ProductFacts(slug=cir.slug, candidate=cir.slug, cir_title=cir.title,
                            kind="toy", category="", nouns=[], qualifiers=[], techniques=[],
                            difficulty="beginner", colors=[], colour_families=[],
                            materials=[], stitches=[], width_cm=None, height_cm=None,
                            makes=1, vocabulary=vocab, cir=cir, twin=None)

    fox = facts(_fox())
    low = truth.validate_listing("Juniper the Fox | low sew amigurumi pattern", [], fox,
                                 competitors=[])
    assert not [b for b in low["blocking"] if "SEW_CLAIM" in b], low["blocking"]
    nosew = truth.validate_listing("Juniper the Fox | no sew amigurumi pattern", [], fox,
                                   competitors=[])
    assert [b for b in nosew["blocking"] if b.startswith("SEW_CLAIM_UNCERTIFIED")]
    tag = truth.validate_listing("Juniper the Fox amigurumi pattern", ["no sew"], fox,
                                 competitors=[])
    assert [b for b in tag["blocking"] if b.startswith("SEW_CLAIM_UNCERTIFIED")]
    nocir = dataclasses.replace(fox, cir=None)
    unknown = truth.validate_listing("Juniper the Fox | low sew pattern", [], nocir,
                                     competitors=[])
    assert [b for b in unknown["blocking"] if "'UNKNOWN'" in b and "SEW_CLAIM" in b]


# ---- chenille yarn class ----------------------------------------------------------------------


def test_chenille_is_a_first_class_yarn_class():
    for cls, weight, cyc in ((yarn_classes.CHENILLE_6, "super_bulky", 6),
                             (yarn_classes.CHENILLE_7, "jumbo", 7)):
        assert cls.weight_key == weight and cls.cyc == cyc
        lo, hi = cls.hook_range_mm
        assert lo < hi and len(cls.hooks) >= 3
        from brambleloop.publish.substitution import WEIGHT_BY_KEY

        band = WEIGHT_BY_KEY[weight].sc_per_10cm
        for h in cls.hooks:                       # every design gauge inside the CYC band
            assert band[0] <= h.sc_per_10cm <= band[1], (cls.key, h)
        # Bigger hook, fewer stitches.
        assert [h.sc_per_10cm for h in cls.hooks] == sorted(
            (h.sc_per_10cm for h in cls.hooks), reverse=True)
        g = cls.gauge()
        assert g.hook_mm == lo and g.yarn_weight == weight
        assert "shed" in cls.shedding_care.lower() and "worm" in cls.shedding_care.lower()
        assert "uncalibrated" in cls.basis
    assert yarn_classes.classify(_fox()) is yarn_classes.CHENILLE_6
    jumbo = lowsew.draft(lowsew.PENGUIN, yarn=yarn_classes.CHENILLE_7)
    assert yarn_classes.classify(jumbo) is yarn_classes.CHENILLE_7
    assert yarn_classes.findings(jumbo) == [] and compile_cir(jumbo).ok


def test_a_chenille_gauge_off_its_table_is_refused():
    from brambleloop.cir.model import Gauge

    cir = _fox()
    assert yarn_classes.findings(cir) == []
    off = dataclasses.replace(cir, gauge=Gauge(10.0, 11.0, "sc", 6.0, "super_bulky"))
    assert [f.code for f in yarn_classes.findings(off)] == ["CHENILLE_GAUGE_MISMATCH"]
    hook = dataclasses.replace(cir, gauge=Gauge(9.0, 9.9, "sc", 4.0, "super_bulky"))
    assert [f.code for f in yarn_classes.findings(hook)] == ["CHENILLE_HOOK_OUT_OF_RANGE"]
    none = dataclasses.replace(cir, gauge=None)
    assert [f.code for f in yarn_classes.findings(none)] == ["CHENILLE_GAUGE_UNSTATED"]
    worsted = copy.deepcopy(cir)
    worsted.materials[0].yarn_weight = "medium"
    for m in worsted.materials:
        if "chenille" in m.name:
            m.yarn_weight = "medium"
    assert [f.code for f in yarn_classes.findings(worsted)] == ["CHENILLE_WEIGHT_UNCLASSED"]
    assert "CHENILLE_GAUGE_MISMATCH" in {f.code for f in certify(off).findings}


# ---- eye options and the child-safety gate ----------------------------------------------------


def test_eye_options_always_offer_embroidered_and_follow_the_age_guidance():
    cir = _fox()
    young = eye_options.options(cir, TOY)
    assert young[0].key == eye_options.EMBROIDERED and young[0].available and young[0].default
    assert "Rnd 8 of the head, 4 sts apart" in young[0].text
    assert not young[1].available and "only option" in young[1].text
    unassigned = eye_options.options(cir, None)          # read as under 3, conservatively
    assert unassigned[1].text == young[1].text
    older = eye_options.options(cir, ("amigurumi_toy", "three_to_six"))
    assert older[0].available and older[0].default and not older[1].available
    assert "embroidered eyes only" in older[1].text
    lines = " ".join(t for _h, t in eye_options.block_lines(cir, TOY))
    assert not CS._CLAIMS.search(CS._fold(lines)), "the block must claim no certification"


def test_the_gate_validates_crocheted_joins_and_their_closures():
    cir = _fox()
    result = compile_cir(cir)
    v = CS.evaluate(cir, result)
    checks = {c.code: c for c in v.checks}
    assert checks["JOINS_VALIDATED"].state == CS.PASS
    assert "crocheted-in" in checks["JOINS_VALIDATED"].detail
    assert "joined" in v.profile and "crochet_joins" in CS.required_statements(v.profile)
    broken = _set_ops(cir, "body", 6, [Op("sc", 5, through="leg"), Op("sc", 4),
                                       Op("sc", 6, through="leg"), Op("sc", 15)])
    got = {c.code: c.state for c in CS.evaluate(broken).checks}
    assert got["JOINS_VALIDATED"] == CS.FAIL, got


def test_crocheted_in_pieces_are_measured_for_small_parts():
    from brambleloop.gates import small_parts

    cir = _fox()
    assert {"leg", "tail", "ear", "head", "body"} <= set(small_parts._sewn_on(cir))
    tiny = copy.deepcopy(cir)
    ear = _comp(tiny, "ear")
    ear.rows = [Row(1, [Op("sc", 4)], 4, color="rust"),
                Row(2, [Op("inc", 4)], 8, color="rust"),
                Row(3, [Op("sc", 8)], 8, color="rust"),
                Row(4, [Op("sc", 4)], 4, color="rust", fold=True)]
    _row(tiny, "head", 6).ops = [Op("sc", 4, through="ear"), Op("sc", 10),
                                 Op("sc", 4, through="ear"), Op("sc", 12)]
    states = {c.code: c.state for c in CS.evaluate(tiny).checks}
    assert states["SMALL_PARTS"] != CS.PASS and states["AGE_SUITABILITY"] != CS.PASS, states


def test_the_written_pattern_says_what_to_make_first_and_where_each_piece_goes():
    cir = lowsew.draft(lowsew.ELEPHANT)
    text = writer.write_pattern(cir, compile_cir(cir), "US")
    assert [c.name for c in cir.components][:2] == ["body", "head"]
    assert ("Make these first, from their sections below: front leg (make 2), back leg "
            "(make 2).") in text
    assert "ear (make 2), trunk (make 1)." in text
    assert ("Joining Rnd 9 of 30 sts: trunk 1 through sts 10-15.") in text
    assert "Spiral drift:" in text and "by up to 1 sts" in text


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
