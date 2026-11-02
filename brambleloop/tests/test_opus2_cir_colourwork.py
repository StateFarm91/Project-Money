"""OPUS2 P0-CIR-COLOURWORK (proposal): stitches worked in their own colour.

A CIR row carried one colour, so tapestry, two-colour rounds and per-stitch mosaic could not
be expressed: the radar fallback refused "Nordic Forest Mosaic Storage Basket" and every
colourwork stocking for that reason. `Op.color` names the yarn an op is worked in when it is
not the row's main colour. It is additive and count-neutral, and omitted when None, so no
existing CIR's digest moves.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_cir_colourwork.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir import reverse, writer  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR, Component, Gauge, Op, Repeat, Row  # noqa: E402


BASE_DIGESTS = {
    'basket_large': '0fbec61859f79def4eadaf3e0996910f0b3c971fc2c843fff0fec17c1cd89b7a',
    'basket_medium': '0a6ffc8af62d7b6f9c58f85cb67409bf61e7441f11b5876fc3f242748a359ab6',
    'basket_small': '8a28d62a15e7bd856936d2e57fb2da3fafc9b3755bb53e86c16c7de19cd9ccf8',
    'cloudline_blanket': '9234419ee25770998fc9b92ef0d9fad4ffa75d10b521f40f857029c64465d9ca',
    'harvest_runner': 'eeb3b7d4ecc0664afe62965cdd1ee0602f2d00545a74eef5611b5ff3eaf8404f',
    'hexagon_coasters': 'd4a486f10b4e12cfae384f02f9b2d254959a5489f51cf3fc790e71009bf44ef8',
    'key_basket': 'bbc70e8baa4ca7508bd43655c8ac84837f17f30df617e56ed5fe2a193783f828',
    'nordic_forest_baby': '1a67c10f9e25ec8e89f0e10665ddf6e4928504aef4546d1459f6bb53294bc9e4',
    'placemat_pair': '414099177bbcb2b7cbd662bd549bec095eea7f420c99bebd3bcdfa8ebe7e07ec',
    'snowfall_throw': '9e3c5d56087a3ff4c3ce3f29cfb7d872b674c3c67f06d480691134f3ba1b55c9',
    'snowflake_ornaments': '2dc618b6772181a4b73390f731554362f5bfa3b512b1b6e76bd07df80eb759ce',
}


def _tapestry(main="natural", contrast="rust", colors=None) -> CIR:
    """A flat-based round with a two-colour tapestry band: 3 main, 1 contrast, all round."""
    colors = colors if colors is not None else {"natural": "#EFE6D2", "rust": "#A4502C"}
    rows = [Row(1, [Op("sc", 6)], declared_count=6, color=main),
            Row(2, [Op("inc", 6)], declared_count=12, color=main),
            Row(3, [Repeat([Op("sc", 2), Op("sc", 2, color=contrast)], times=3)],
                declared_count=12, color=main),
            Row(4, [Repeat([Op("sc", 1), Op("sc", 2, color=contrast), Op("sc", 1)], times=3)],
                declared_count=12, color=main),
            Row(5, [Repeat([Op("sc", 2), Op("sc", 2, color=contrast)], times=3)],
                declared_count=12, color=main),
            Row(6, [Op("sc", 12)], declared_count=12, color=main)]
    return CIR(slug="tapestry-fixture", title="Tapestry Fixture", version="1.0.0",
               construction="joined_rounds", gauge=Gauge(18, 20),
               components=[Component("body", "joined_rounds", foundation=0,
                                     foundation_kind="magic_ring", rows=rows)],
               colors=colors)


def _errors(cir):
    return [f for f in compile_cir(cir).findings if f.severity == "ERROR"]


def test_a_two_colour_round_compiles_with_its_counts_unchanged():
    cir = _tapestry()
    result = compile_cir(cir)
    assert not _errors(cir), _errors(cir)
    assert result.row("body", 3).stitch_count == 12      # colour is count-neutral


def test_the_writer_names_the_contrast_and_the_reverse_compiler_reads_it_back():
    cir = _tapestry()
    result = compile_cir(cir)
    text = writer.write_pattern(cir, result)
    assert "sc in next 2 sts with rust" in text, text
    findings = reverse.compare(cir, text)
    assert not [f for f in findings if f.severity == "ERROR"], findings
    # A document that drops the contrast describes a different fabric: it is a mismatch.
    plain = text.replace(" with rust", "")
    assert plain != text
    assert [f for f in reverse.compare(cir, plain) if f.severity == "ERROR"]


def test_to_dict_round_trips_the_stitch_colour_and_omits_it_when_absent():
    cir = _tapestry()
    d = cir.to_dict()
    assert CIR.from_dict(d).to_dict() == d
    assert CIR.from_json(json.dumps(d)).to_dict() == d
    band = d["components"][0]["rows"][2]["ops"][0]["ops"]
    assert band[1]["color"] == "rust" and "color" not in band[0]
    assert all("color" not in op for op in d["components"][0]["rows"][0]["ops"])


def test_an_undeclared_stitch_colour_or_a_missing_main_colour_is_an_error():
    codes = {f.code for f in _errors(_tapestry(contrast="teal"))}
    assert "UNKNOWN_COLOR" in codes, codes
    cir = _tapestry()
    cir.components[0].rows[2].color = None
    assert "STITCH_COLOUR_WITHOUT_ROW_COLOUR" in {f.code for f in _errors(cir)}


def test_no_existing_launch_design_changes_its_digest():
    """The field is additive: every Launch-0 CIR serialises byte-for-byte as before."""
    from brambleloop.products import launch0 as L

    pinned = {}
    for b in sorted(L.BUILDERS):
        cir = L.cir_for(b)
        assert "\"color\": null" not in cir.to_json()
        d = cir.to_dict()
        assert d["components"] and all(c["rows"] for c in d["components"])
        for comp in d["components"]:
            assert comp["rows"]
            for row in comp["rows"]:
                stack = list(row["ops"])
                while stack:
                    node = stack.pop()
                    assert "color" not in node, (b, node)
                    stack.extend(node.get("ops", []))
        pinned[b] = hashlib.sha256(cir.to_json().encode()).hexdigest()
    # OPUS2H H2-5: the digests themselves, taken on the base (d230e8fd) before Op.color existed.
    assert pinned == BASE_DIGESTS, {b: d for b, d in pinned.items() if BASE_DIGESTS.get(b) != d}


def test_the_twin_paints_each_stitch_and_fabric_truth_backs_a_colourwork_claim():
    import dataclasses

    from brambleloop.cir.twin import build_twin
    from brambleloop.products import launch0 as L

    cir = _tapestry()
    result = compile_cir(cir)
    twin = build_twin(cir, result)
    band = [c for c in twin.cells if c.row == 3]
    assert [c.color for c in band][:4] == ["natural"] * 2 + ["rust"] * 2
    assert {c.color for c in twin.cells if c.row == 6} == {"natural"}
    assert set(twin.yarn_metres_by_color) == {"natural", "rust"}
    assert twin.yarn_metres_by_color["rust"] < twin.yarn_metres_by_color["natural"]
    # The name-truth gate the radar fallback refused colourwork on now backs it.
    assert L.per_stitch_colour_expressible() is True
    claimed = dataclasses.replace(cir, title="Tapestry Fixture Bowl")
    truth = L.fabric_truth(claimed, twin)
    assert truth["max_colours_in_one_row"] == 2 and truth["backed"] is True, truth
    plain = dataclasses.replace(claimed, components=[dataclasses.replace(
        cir.components[0], rows=[dataclasses.replace(r, ops=[Op("sc", 12)])
                                 if r.index == 3 else r for r in cir.components[0].rows])])
    plain_twin = build_twin(plain, compile_cir(plain))
    assert L.fabric_truth(plain, plain_twin)["backed"] is False   # a claim without the fabric


def test_the_colour_plan_and_the_pdf_tell_the_maker_how_to_work_a_tapestry_round():
    from brambleloop.cir import colour_changes as CC

    cir = _tapestry()
    plan = CC.analyse(cir)["body"]
    assert plan.tapestry_rows == [3, 4, 5] and plan.ends == 4   # two yarns, joined and fastened
    assert (3, "rust", CC.IN_ROW) in plan.events and plan.cut == 0
    text = writer.write_pattern(cir, compile_cir(cir))
    assert "Colourwork rounds 3-5: work over the colour not in use" in text, text
    # A one-colour-per-row design keeps exactly the sentence it had before.
    from brambleloop.products import launch0 as L

    stripes = L.cir_for("nordic_forest_baby")
    before = CC.analyse(stripes)
    assert before and all(not p.tapestry_rows for p in before.values())
    assert all("Colourwork" not in (CC.instruction(p) or "") for p in before.values())


def test_review_opus2h_h21_each_technique_claim_needs_its_own_fabric():
    import dataclasses

    from brambleloop.cir.twin import build_twin
    from brambleloop.products import launch0 as L

    def truth(cir, title):
        claimed = dataclasses.replace(cir, title=title)
        return L.fabric_truth(claimed, build_twin(claimed, compile_cir(claimed)))

    # One contrast stitch backs nothing (the reviewer's repro).
    token = _tapestry()
    token.components[0].rows[2:5] = [
        Row(3, [Op("sc", 11), Op("sc", 1, color="rust")], declared_count=12, color="natural"),
        Row(4, [Op("sc", 12)], declared_count=12, color="natural"),
        Row(5, [Op("sc", 12)], declared_count=12, color="natural")]
    claims = ("Overlay Mosaic Basket", "Fair Isle Basket", "Intarsia Basket",
              "Graphghan Basket", "Tapestry Basket", "Colourwork Basket")
    assert claims
    for title in claims:
        assert truth(token, title)["backed"] is False, title
    # A real three-round band backs tapestry, fair isle and colourwork...
    band = _tapestry()
    for title in ("Tapestry Basket", "Fair Isle Basket", "Colourwork Basket"):
        assert truth(band, title)["backed"] is True, (title, truth(band, title)["why"])
    # ...but never mosaic, overlay, graphghan or intarsia, which need primitives that do not exist.
    for title in ("Overlay Mosaic Basket", "Mosaic Basket", "Graphghan Basket", "Intarsia Basket"):
        assert truth(band, title)["backed"] is False, title


def test_review_opus2h_h22_a_contrast_left_at_the_other_edge_is_cut_and_carry_is_charged():
    from brambleloop.cir import colour_changes as CC
    from brambleloop.cir.twin import build_twin

    rows = [Row(1, [Op("sc", 12)], declared_count=12, turning_chain=1, color="natural"),
            Row(2, [Op("sc", 6), Op("sc", 6, color="rust")], declared_count=12,
                turning_chain=1, color="natural"),
            Row(3, [Op("sc", 12)], declared_count=12, turning_chain=1, color="natural"),
            Row(4, [Op("sc", 6, color="rust"), Op("sc", 6)], declared_count=12,
                turning_chain=1, color="natural")]
    cir = CIR(slug="flat-tapestry", title="Flat Tapestry", version="1.0.0",
              construction="flat_rows", gauge=Gauge(18, 20),
              components=[Component("panel", "flat_rows", foundation=12, rows=rows)],
              colors={"natural": "#EFE6D2", "rust": "#A4502C"})
    plan = CC.analyse(cir)["panel"]
    assert plan.tapestry_rows == [2, 4] and plan.tapestry_cuts == 1 and plan.ends == 6, plan
    line = CC.instruction(plan)
    assert "Colourwork rows 2 and 4" in line and "cut it" in line, line
    assert "2-4" not in line
    twin = build_twin(cir, compile_cir(cir))
    worked_only = 12 * 10.0 / 18 / 100.0                      # rust's own stitches, in m
    assert twin.yarn_metres_by_color["rust"] > worked_only     # the carried strand is charged


def test_review_opus2h_h23_h24_h26_colour_errors_fail_at_compile():
    def codes(cir):
        return {f.code for f in _errors(cir)}

    skip = _tapestry()
    skip.components[0].rows[2] = Row(3, [Op("sc", 11), Op("sk", 1, color="rust")],
                                     declared_count=11, color="natural", allow_remainder=True)
    assert "COLOUR_ON_NON_STITCH" in codes(skip)
    assert "UNKNOWN_COLOR" in codes(_tapestry(colors={}))
    rose = _tapestry(contrast="Dusty Rose",
                     colors={"natural": "#EFE6D2", "Dusty Rose": "#C9A0A0"})
    assert "COLOUR_KEY_UNWRITABLE" in codes(rose)


def _truth(cir, title, tags=()):
    import dataclasses

    from brambleloop.cir.twin import build_twin
    from brambleloop.gates import first_customer as FCG
    from brambleloop.products import launch0 as L

    claimed = dataclasses.replace(cir, title=title)
    twin = build_twin(claimed, compile_cir(claimed))
    return L.fabric_truth(claimed, twin), FCG.colourwork_findings(claimed, twin, title=title,
                                                                    tags=tags)


def _band(rows_spec, total_rows=6):
    """rows_spec: {row index: ops}; other rows plain natural, 12 sts."""
    rows = [Row(1, [Op("sc", 6)], declared_count=6, color="natural"),
            Row(2, [Op("inc", 6)], declared_count=12, color="natural")]
    for i in range(3, total_rows + 1):
        rows.append(Row(i, rows_spec.get(i, [Op("sc", 12)]), declared_count=12,
                        color="natural"))
    return CIR(slug="band", title="Band", version="1.0.0", construction="joined_rounds",
               gauge=Gauge(18, 20), colors={"natural": "#EFE6D2", "rust": "#A4502C"},
               components=[Component("body", "joined_rounds", foundation=0,
                                     foundation_kind="magic_ring", rows=rows)])


def test_review_opus2i_i2_the_listing_gate_shares_the_technique_rule():
    token = _band({3: [Op("sc", 11), Op("sc", 1, color="rust")]})
    truth, findings = _truth(token, "Overlay Mosaic Intarsia Basket",
                             tags=("mosaic", "fair isle", "intarsia"))
    assert truth["backed"] is False
    claimed = {f.split("claims ")[1].split(";")[0] for f in findings}
    assert {"'mosaic'", "'fair isle'", "'intarsia'"} <= claimed, findings
    band = _tapestry()
    truth, findings = _truth(band, "Tapestry Basket", tags=("tapestry",))
    assert truth["backed"] is True and findings == [], findings
    truth, findings = _truth(band, "Tapestry Mosaic Basket")       # all, never any (I-5 C14)
    assert truth["backed"] is False and any("'mosaic'" in f for f in findings)


def _flat_band(width, spec, total=6):
    rows = [Row(i, spec.get(i, [Op("sc", width)]), declared_count=width, turning_chain=1,
                color="natural") for i in range(1, total + 1)]
    return CIR(slug="flat-band", title="Flat Band", version="1.0.0", construction="flat_rows",
               gauge=Gauge(18, 20), colors={"natural": "#EFE6D2", "rust": "#A4502C"},
               components=[Component("panel", "flat_rows", foundation=width, rows=rows)])


def test_review_opus2i_i5_i7_each_threshold_is_pinned_at_its_boundary():
    """Each case fails exactly one rule, so each threshold mutated to zero is caught."""
    from brambleloop.products import launch0 as L

    def backed(width, spec, total=6):
        return _truth(_flat_band(width, spec, total), "Tapestry Panel")[0]["backed"]

    two = [Op("sc", 5), Op("sc", 2, color="rust"), Op("sc", 5)]      # 16.7%, run 2
    assert backed(12, {2: two, 3: two, 4: two})                       # all rules pass
    assert not backed(12, {2: two, 3: two})                           # MIN_ROWS only
    assert not backed(12, {2: two, 3: two, 4: two}, total=16)         # ROW_SHARE only (3/16)
    thin = [Op("sc", 11), Op("sc", 2, color="rust"), Op("sc", 11)]    # 2/24 = 8.3%, run 2
    assert not backed(24, {2: thin, 3: thin, 4: thin})                # MINORITY_SHARE only
    dots = [Op("sc", 2), Op("sc", 1, color="rust"), Op("sc", 5), Op("sc", 1, color="rust"),
            Op("sc", 3)]                                              # 16.7%, run 1
    assert not backed(12, {2: dots, 3: dots, 4: dots})                # MIN_RUN only (I-7)
    assert (L.COLOURWORK_MIN_ROWS, L.COLOURWORK_MIN_ROW_SHARE,
            L.COLOURWORK_MIN_MINORITY_SHARE, L.COLOURWORK_MIN_RUN) == (3, 0.20, 0.10, 2)


def test_review_opus2i_i4_a_tapestry_cut_is_not_a_stripe_cut():
    from brambleloop.cir import colour_changes as CC

    def row(i, ops, colour):
        return Row(i, ops, declared_count=12, turning_chain=1, color=colour)
    rows = [row(1, [Op("sc", 12)], "natural"), row(2, [Op("sc", 12)], "natural"),
            row(3, [Op("sc", 12)], "sage"), row(4, [Op("sc", 12)], "sage"),
            row(5, [Op("sc", 12)], "natural"),
            row(6, [Op("sc", 6), Op("sc", 6, color="rust")], "natural"),
            row(7, [Op("sc", 12)], "natural"),
            row(8, [Op("sc", 6, color="rust"), Op("sc", 6)], "natural")]
    cir = CIR(slug="mixed", title="Mixed", version="1.0.0", construction="flat_rows",
              gauge=Gauge(18, 20),
              colors={"natural": "#EFE6D2", "sage": "#9CAF88", "rust": "#A4502C"},
              components=[Component("panel", "flat_rows", foundation=12, rows=rows)])
    plan = CC.analyse(cir)["panel"]
    assert plan.cut == 0 and plan.carry_is_possible, plan          # the stripes carry
    assert plan.tapestry_cuts == 1 and plan.first_tapestry_cut_row == 8
    line = CC.instruction(plan)
    assert "cannot be carried" not in line and "Colourwork rows 6 and 8" in line, line


def test_review_opus2i_i5_c19_the_carried_strand_is_charged_exactly():
    from brambleloop.cir import twin as T

    # 60 stitches, so the carry shows through the 0.1 m rounding of the materials list.
    rows = [Row(1, [Op("sc", 60)], declared_count=60, turning_chain=1, color="natural"),
            Row(2, [Op("sc", 30), Op("sc", 30, color="rust")], declared_count=60,
                turning_chain=1, color="natural")]
    cir = CIR(slug="carry", title="Carry", version="1.0.0", construction="flat_rows",
              gauge=Gauge(18, 20), colors={"natural": "#EFE6D2", "rust": "#A4502C"},
              components=[Component("panel", "flat_rows", foundation=60, rows=rows)])
    st_cm = 10.0 / 18
    worked = T._YARN_FACTOR.get("sc", 3.0) * st_cm * 30
    carried = T.CARRY_FACTOR * st_cm * 30
    got = T.build_twin(cir, compile_cir(cir)).yarn_metres_by_color["rust"]
    assert got == round((worked + carried) / 100.0, 1), (got, worked, carried)
    assert got > round(worked / 100.0, 1)                       # the carry moves the figure


def test_review_opus2i_i6_a_coloured_chain_is_stated():
    cir = _tapestry()
    cir.components[0].rows[5] = Row(6, [Op("sc", 11), Op("ch", 1, color="rust")],
                                    declared_count=12, color="natural")
    codes = {f.code for f in compile_cir(cir).findings}
    assert "COLOUR_ON_CHAIN" in codes, codes


def test_review_opus2j_j6_spelling_variants_are_the_same_claim():
    plain = _band({})                                   # one colour per row: backs nothing
    variants = ("Fair-Isle Basket", "Colour Work Basket", "Color-Work Basket", "Stranded Basket",
                "Jacquard Basket", "Two-Colour Basket", "Duplicate Stitch Basket")
    assert variants
    for title in variants:
        truth, findings = _truth(plain, title)
        assert truth["backed"] is False and findings, title
    truth, findings = _truth(plain, "Plain Basket", tags=("fair-isle", "stranded"))
    assert len(findings) == 2, findings
    band = _tapestry()
    for title in ("Fair-Isle Basket", "Stranded Basket", "Colour Work Basket"):
        assert _truth(band, title)[0]["backed"] is True, title     # a real motif still backs
    assert _truth(band, "Duplicate Stitch Basket")[0]["backed"] is False


def test_review_opus2j_j8b_every_motif_row_needs_the_minimum_run():
    two = [Op("sc", 5), Op("sc", 2, color="rust"), Op("sc", 5)]
    dot = [Op("sc", 4), Op("sc", 1, color="rust"), Op("sc", 3), Op("sc", 1, color="rust"),
           Op("sc", 3)]                                   # 2/12 = 16.7%: fails only the run
    one_run_two_dots = _flat_band(12, {2: two, 3: dot, 4: dot})
    assert _truth(one_run_two_dots, "Tapestry Panel")[0]["backed"] is False


def test_review_opus2k_k5_k6_every_spelling_is_folded_and_held_double_is_not_stranded():
    plain = _band({})
    variants = ("Fair\u2013Isle", "Fair\u2014Isle", "Fair\u2011Isle", "Fair/Isle", "Fair.Isle",
                "Fair\u00b7Isle", "Colour\u2011Work", "Colour/Work", "Graphgan", "Two-Tone",
                "Bicolour", "Multicolour", "Three-Colour", "Tri-Colour", "Two-Coloured",
                "Two Colours", "2-Colour", "Duplicate-Stitched", "C2C", "Corner to Corner",
                "Mosaics", "Colourworked")
    assert variants
    for word in variants:
        truth, findings = _truth(plain, f"{word} Basket")
        assert truth["backed"] is False and findings, word
        assert _truth(plain, "Plain Basket", tags=(word,))[1], word       # as a tag too
    for title in ("Double-Stranded Basket", "Held Double Stranded Basket"):
        truth, findings = _truth(plain, title)
        assert truth["backed"] is True and findings == [], (title, findings)


def test_review_opus2m_compounds_inflections_counts_and_unicode_are_claims():
    """OPUS2M-2 (the K-5 anchor loosened the gate), -3, -4, -8: every one of these is a
    colourwork claim, refused on all-plain fabric as a title and as a tag."""
    plain = _band({})
    claims = (
        # M-2: a claim word inside a compound is still a claim (substring, as before K-5)
        "Minimosaic", "Microtapestry", "Minitapestry", "Superfairisle", "Multicolourwork",
        "Pseudointarsia",
        # M-3: inflections, any colour count, and the missing spellings
        "Tapestries", "Graphgans", "Jacquards", "Duplicate Stitching", "Colour Works",
        "Color Works", "Two-Tones", "Five-Colour", "5 Colour", "Ten Colour", "C-2-C", "C 2 C",
        "Corner-2-Corner", "Dual Colour", "Duo-Tone", "Duotone", "Colour Block",
        "Colorblock", "Pixel Crochet", "Four Colour",
        # M-4: invisible characters, accents, dotted capital I, look-alike letters
        "Tape\u200bstry", "Mo\u00adsaic", "Mo\u200dsaic", "F\u00e1ir \u00cdsle",
        "T\u00e1pestry", "Mos\u00e4ic", "Colourw\u00f6rk", "FA\u0130R ISLE",
        "\u0422\u0430pestry", "Fair\u200bIsle",
        # M-8: full-width forms are folded
        "\uff26\uff41\uff49\uff52 \uff29\uff53\uff4c\uff45",
    )
    assert claims
    checked = 0
    for word in claims:
        truth, findings = _truth(plain, f"{word} Basket")
        assert truth["backed"] is False and findings, word
        assert _truth(plain, "Plain Basket", tags=(word,))[1], word
        checked += 1
    assert checked == len(claims)
    # Still not claims: yarn held double, and a plain title (OPUS2M-8 We: "held" alone).
    for title in ("Held Stranded Basket", "Double-Stranded Basket", "Plain Basket"):
        truth, findings = _truth(plain, title)
        assert truth["backed"] is True and findings == [], (title, findings)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
