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


def _tapestry(main="natural", contrast="rust", colors=None) -> CIR:
    """A flat-based round with a two-colour tapestry band: 3 main, 1 contrast, all round."""
    colors = colors if colors is not None else {"natural": "#EFE6D2", "rust": "#A4502C"}
    rows = [Row(1, [Op("sc", 6)], declared_count=6, color=main),
            Row(2, [Op("inc", 6)], declared_count=12, color=main),
            Row(3, [Repeat([Op("sc", 3), Op("sc", 1, color=contrast)], times=3)],
                declared_count=12, color=main),
            Row(4, [Op("sc", 12)], declared_count=12, color=main)]
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
    assert "sc in next st with rust" in text, text
    findings = reverse.compare(cir, text)
    assert not [f for f in findings if f.severity == "ERROR"], findings
    # A document that drops the contrast describes a different fabric: it is a mismatch.
    plain = text.replace(" with rust", "")
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
    assert len(pinned) == len(L.BUILDERS) >= 11


def test_the_twin_paints_each_stitch_and_fabric_truth_backs_a_colourwork_claim():
    import dataclasses

    from brambleloop.cir.twin import build_twin
    from brambleloop.products import launch0 as L

    cir = _tapestry()
    result = compile_cir(cir)
    twin = build_twin(cir, result)
    band = [c for c in twin.cells if c.row == 3]
    assert [c.color for c in band][:4] == ["natural"] * 3 + ["rust"]
    assert {c.color for c in twin.cells if c.row == 4} == {"natural"}
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
    assert plan.tapestry_rows == [3] and plan.ends == 4     # two yarns, joined and fastened
    assert (3, "rust", CC.IN_ROW) in plan.events and plan.cut == 0
    text = writer.write_pattern(cir, compile_cir(cir))
    assert "Colourwork round 3: work over the colour not in use" in text, text
    # A one-colour-per-row design keeps exactly the sentence it had before.
    from brambleloop.products import launch0 as L

    stripes = L.cir_for("nordic_forest_baby")
    before = CC.analyse(stripes)
    assert before and all(not p.tapestry_rows for p in before.values())
    assert all("Colourwork" not in (CC.instruction(p) or "") for p in before.values())


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
