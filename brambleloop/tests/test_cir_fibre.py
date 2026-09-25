"""`Material.fibre_content`: the field, and the round trip that makes it a fact.

Specified by the Children's Safety Deliverable department in
`research/CHILDRENS_STATEMENTS.md` §5, which hit it as a blocker and could not close it
because `cir/**` was not theirs:

    add `fibre_content: tuple[tuple[str, int], ...] = ()` to `Material`, validated in
    `__post_init__` to sum to 100 when non-empty and drawn from a closed vocabulary,
    defaulting empty so a CIR that omits it is refused rather than assumed.

Two things this file is about, and they pull in opposite directions on purpose.

**The field has to carry a fact all the way to the buyer and back.** A composition printed in
a document that the independent reverse compiler cannot read back is not a round trip, and
decision B-005 forbids the writer and the reverse compiler sharing parsing code, so the
reverse compiler needs its own grammar for it. `test_a_document_that_loses_the_composition_
is_caught_by_the_reverse_compiler` is the one that matters.

**The field must stay empty wherever nobody stated the fact.** `publish/substitution.py`
reads a fibre *class* out of `Material.name` and `publish/pdf.fibres_named` reads a fibre
*word* out of the same field; both are honest readings of a yarn description and neither is a
composition. "worsted acrylic" is not "100% acrylic". None of the eleven Launch-0 CIRs is
given a value here, and `test_the_eleven_launch0_cirs_state_no_fibre_content` pins that,
with the reason.

Visual/CIR department, 2026-09-25.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir import reverse, writer  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import FIBRES, CIR, Material  # noqa: E402
from brambleloop.products import vessels  # noqa: E402


def _refused(**kw) -> str:
    try:
        Material(**kw)
    except ValueError as exc:
        return str(exc)
    raise AssertionError(f"Material({kw!r}) was accepted and should not have been")


def _coaster_with(content: dict[int, tuple]) -> tuple[CIR, object]:
    """The hexagon coaster set, with a composition attached to the given materials."""
    cir = vessels.build_hexagon_coaster()
    for index, pairs in content.items():
        material = cir.materials[index]
        cir.materials[index] = Material(
            name=material.name, yarn_weight=material.yarn_weight,
            colorway=material.colorway, metres_estimate=material.metres_estimate,
            color_id=material.color_id, fibre_content=pairs)
    return cir, compile_cir(cir)


def _materials_line(text: str) -> str:
    return next(line for line in text.splitlines() if line.startswith("Materials:"))


# ---------------------------------------------------------------------------
# The field


def test_a_material_that_states_nothing_stays_empty_and_says_so():
    """Empty is the default and it means "not stated", never "no fibre concerns"."""
    material = Material(name="worsted acrylic")
    assert material.fibre_content == ()
    assert material.states_fibre_content is False
    assert Material(name="x", fibre_content=(("cotton", 100),)).states_fibre_content is True


def test_the_vocabulary_is_closed_and_a_composition_must_account_for_the_whole_yarn():
    """Each refusal names a different way of being unable to check a claim."""
    assert "not a fibre this schema knows" in _refused(
        name="y", fibre_content=(("spandex", 100),))
    assert "sums to 90%" in _refused(
        name="y", fibre_content=(("cotton", 60), ("linen", 30)))
    assert "sums to 110%" in _refused(
        name="y", fibre_content=(("cotton", 60), ("linen", 50)))
    assert "stated twice" in _refused(
        name="y", fibre_content=(("cotton", 50), ("cotton", 50)))
    assert "outside 1..100" in _refused(
        name="y", fibre_content=(("cotton", 0), ("linen", 100)))
    assert "whole percent" in _refused(
        name="y", fibre_content=(("cotton", 55.0), ("linen", 45.0)))
    # `bool` is an `int` in Python, so `True` would otherwise be accepted as 1%.
    assert "whole percent" in _refused(
        name="y", fibre_content=(("cotton", True), ("linen", 99)))
    assert "not a mapping" in _refused(name="y", fibre_content={"cotton": 100})
    assert "not a (fibre, percent) pair" in _refused(name="y", fibre_content=("cotton",))


def test_one_composition_has_one_representation():
    """Declaration order must not give the same yarn two compile keys.

    `CIR.compile_key` hashes `to_dict`, and a design whose hash moves when nothing about the
    design moved re-runs certification for nothing -- the defect that comment was written
    about. Descending by percentage is also how a composition is customarily written, so the
    document gets the customary order without the writer deciding it.
    """
    a = Material(name="y", fibre_content=(("linen", 45), ("cotton", 55)))
    b = Material(name="y", fibre_content=(("cotton", 55), ("linen", 45)))
    assert a.fibre_content == b.fibre_content == (("cotton", 55), ("linen", 45))
    tie = Material(name="y", fibre_content=(("wool", 50), ("cotton", 50)))
    assert tie.fibre_content == (("cotton", 50), ("wool", 50))


def test_the_two_fibre_vocabularies_are_the_same_seventeen_words():
    """`cir.model.FIBRES` and `publish.substitution.FIBRE_CLASSES` are one fact, twice.

    The schema cannot import `publish` -- `publish` reads `cir` and the arrow must not turn
    round -- so the copy exists. This is what stops it drifting: a fibre the CIR accepts and
    `publish` does not recognise is a composition the document cannot print, and a fibre
    `publish` recognises and the CIR refuses is a yarn nobody can describe.

    `research/VISUAL_GOVERNANCE.md` carries the diff that deletes the copy, for the owner of
    `publish/substitution.py`.
    """
    from brambleloop.publish import substitution

    theirs = {fibre for family in substitution.FIBRE_CLASSES.values() for fibre in family}
    assert set(FIBRES) == theirs, (
        f"the two fibre vocabularies have drifted: only in cir.model.FIBRES "
        f"{sorted(set(FIBRES) - theirs)}, only in substitution.FIBRE_CLASSES "
        f"{sorted(theirs - set(FIBRES))}")
    assert FIBRES == tuple(sorted(FIBRES))


# ---------------------------------------------------------------------------
# Serialisation


def test_a_cir_written_before_this_field_existed_still_loads():
    """The default is what makes an old CIR loadable, and empty is the honest value for it.

    An old CIR did not state a composition, so it does not have one, and it must not acquire
    one by being loaded by newer code.
    """
    cir = vessels.build_hexagon_coaster()
    payload = json.loads(json.dumps(cir.to_dict(), default=str))
    for material in payload["materials"]:
        material.pop("fibre_content", None)
    loaded = CIR.from_dict(payload)
    assert [m.fibre_content for m in loaded.materials] == [(), ()]
    assert all(not m.states_fibre_content for m in loaded.materials)


def test_to_dict_and_from_dict_carry_the_composition_through_json():
    """JSON turns every tuple into a list, so the field has to survive being a list."""
    cir, _ = _coaster_with({0: (("cotton", 100),), 1: (("linen", 45), ("cotton", 55))})
    reloaded = CIR.from_json(cir.to_json())
    assert [m.fibre_content for m in reloaded.materials] == [
        (("cotton", 100),), (("cotton", 55), ("linen", 45))]
    assert reloaded.to_json() == cir.to_json()


def test_a_composition_that_survived_serialisation_is_still_validated():
    """Round-tripping is not a way past the rules, which is where a bad one would get in."""
    cir, _ = _coaster_with({0: (("cotton", 100),)})
    payload = json.loads(cir.to_json())
    payload["materials"][0]["fibre_content"] = [["cotton", 60], ["linen", 30]]
    try:
        CIR.from_dict(payload)
    except ValueError as exc:
        assert "sums to 90%" in str(exc)
    else:
        raise AssertionError("a stored CIR with an impossible composition was loaded")


# ---------------------------------------------------------------------------
# The document, and reading it back


def test_the_writer_prints_the_composition_with_the_yarn_it_belongs_to():
    cir, result = _coaster_with({0: (("cotton", 100),), 1: (("linen", 45), ("cotton", 55))})
    line = _materials_line(writer.write_pattern(cir, result))
    assert line == ("Materials: dk cotton (cream), 100% cotton; "
                    "dk cotton (wine), 55% cotton, 45% linen")


def test_a_pattern_that_states_nothing_prints_nothing():
    """The eleven existing documents must not change a byte because of this field."""
    cir = vessels.build_hexagon_coaster()
    line = _materials_line(writer.write_pattern(cir, compile_cir(cir)))
    assert line == "Materials: dk cotton (cream); dk cotton (wine)"
    assert "%" not in line


def test_the_reverse_compiler_recovers_the_composition_from_the_document_alone():
    """The round trip. It reads percent signs, not the writer's formatting (B-005)."""
    cir, result = _coaster_with({0: (("cotton", 100),), 1: (("linen", 45), ("cotton", 55))})
    text = writer.write_pattern(cir, result)
    assert reverse.parse_fibre_content(text) == (
        (("cotton", 100),), (("cotton", 55), ("linen", 45)))
    assert [f.code for f in reverse.compare(cir, text)] == []


def test_the_reverse_compiler_reads_a_line_no_writer_in_this_repository_produced():
    """A round trip through shared code proves nothing, so this is the proof it is not one.

    Retyped by hand in a different order with different spacing and a different separator
    between the yarn and its composition. If this only parsed `writer.material_line`'s exact
    output it would be a comparison of one function with itself.
    """
    text = "Materials: Aran Wool Blend [ivory] - 70 % merino and 30% nylon\n"
    assert reverse.parse_fibre_content(text) == ((("merino", 70), ("nylon", 30)),)


def test_a_document_that_loses_the_composition_is_caught_by_the_reverse_compiler():
    """The injected defect: the fact is in the CIR and gone from the customer's document."""
    cir, result = _coaster_with({0: (("cotton", 100),)})
    text = writer.write_pattern(cir, result)
    assert [f.code for f in reverse.compare(cir, text)] == []

    broken = text.replace("dk cotton (cream), 100% cotton", "dk cotton (cream)")
    assert broken != text
    codes = [f.code for f in reverse.compare(cir, broken)]
    assert codes == ["REVERSE_FIBRE_CONTENT"], codes


def test_a_composition_attached_to_the_wrong_yarn_is_caught():
    """Order is the fact here: which yarn is 100% cotton is a different product claim."""
    cir, result = _coaster_with({0: (("cotton", 100),)})
    text = writer.write_pattern(cir, result)
    moved = text.replace(
        "Materials: dk cotton (cream), 100% cotton; dk cotton (wine)",
        "Materials: dk cotton (cream); dk cotton (wine), 100% cotton")
    assert moved != text
    assert [f.code for f in reverse.compare(cir, moved)] == ["REVERSE_FIBRE_CONTENT"]


def test_a_document_that_invented_a_composition_is_caught():
    """A CIR that states nothing and a document that states something is the other direction.

    This is the one a generated or hand-edited document produces, and it is the direction the
    owner's rule is about: a fibre content nobody validated, printed to a buyer.
    """
    cir = vessels.build_hexagon_coaster()
    text = writer.write_pattern(cir, compile_cir(cir))
    invented = text.replace("dk cotton (cream)", "dk cotton (cream), 100% cotton")
    assert [f.code for f in reverse.compare(cir, invented)] == ["REVERSE_FIBRE_CONTENT"]


def test_silence_on_both_sides_is_not_a_finding():
    """Every product says nothing today, and its document says nothing.

    Reporting that pair as a defect would bury the real findings under a copy of a known gap
    per product. Checked on more than one shape of CIR -- two materials and three -- because
    the comparison is per material and a one-material check would not notice a reader that
    flattened them.
    """
    from brambleloop.products import builder as flat
    from brambleloop.products import vessels as v

    for name, cir in (("hexagon-coaster-set", v.build_hexagon_coaster()),
                      ("market-basket-small", v.build_basket("small")),
                      ("harvest-table-runner", flat.for_slug("harvest-table-runner")),
                      ("cloudline-baby-blanket", flat.for_slug("cloudline-baby-blanket"))):
        text = writer.write_pattern(cir, compile_cir(cir))
        recovered = reverse.parse_fibre_content(text)
        assert recovered == tuple(() for _ in cir.materials), (name, recovered)
        assert [f.code for f in reverse.compare(cir, text)] == [], name


def test_the_reverse_compiler_refuses_an_impossible_composition_in_a_document():
    """A document is allowed to be silent. It is not allowed to be arithmetically wrong.

    A buyer reads and acts on this, so 60% cotton and 30% linen is not a rounding question:
    it is ten percent of the yarn nobody has accounted for.
    """
    cir = vessels.build_hexagon_coaster()
    text = writer.write_pattern(cir, compile_cir(cir))
    bad = text.replace("dk cotton (cream)", "dk cotton (cream), 60% cotton, 30% linen")
    findings = reverse.compare(cir, bad)
    assert [f.code for f in findings] == ["REVERSE_PARSE"]
    assert "90%" in findings[0].message

    try:
        reverse.parse_fibre_content("Materials: yarn, 150% cotton\n")
    except reverse.ParseProblem as exc:
        assert "not a share of a yarn" in str(exc)
    else:
        raise AssertionError("a document claiming 150% of one fibre was parsed")


def test_the_reverse_compiler_does_not_import_the_writer():
    """B-005, checked on the module rather than trusted to a comment."""
    source = (ROOT / "src" / "brambleloop" / "cir" / "reverse.py").read_text()
    # Calls and imports, not mentions: the module names `writer.material_line` in a comment
    # precisely to say it is not using it, and a check that failed on that would be teaching
    # the next reader to delete the explanation.
    assert "material_line(" not in source
    assert "fibre_content_phrase(" not in source
    assert "from .writer" not in source and "from . import writer" not in source
    assert "import writer" not in source
    import brambleloop.cir.reverse as module

    assert not hasattr(module, "writer")


# ---------------------------------------------------------------------------
# What is deliberately *not* populated


def test_the_eleven_launch0_cirs_state_no_fibre_content():
    """None of them gets a value, and the reason is the point of the field.

    Every Launch-0 material is a generic yarn description -- `"worsted acrylic"`,
    `"worsted cotton"`, `"dk cotton"`, `"chunky acrylic"` -- with no manufacturer, no
    product and no ball band behind it. There is no source that states a composition for
    any of them, so there is nothing to record. Writing `(("acrylic", 100),)` because the
    word "acrylic" appears in a yarn name is precisely the inference the owner forbade and
    that this field exists to make unnecessary.

    This is a pin on a decision, not a wish: if a product module ever states one, this test
    fails and whoever stated it has to say where they read it.
    """
    from brambleloop.products import builder as flat
    from brambleloop.products import nordic_forest, vessels as v

    stated: list[tuple[str, str]] = []
    cirs = [flat.for_slug(slug) for slug in sorted(flat.CATALOGUE)]
    assert len(cirs) == 11
    cirs += [nordic_forest.build(size) for size in sorted(nordic_forest.SIZES)]
    cirs += [v.build_basket(size) for size in ("small", "medium", "large")]
    cirs.append(v.build_hexagon_coaster())
    for cir in cirs:
        for material in cir.materials:
            assert isinstance(material.fibre_content, tuple)
            if material.states_fibre_content:
                stated.append((cir.slug, material.name))
    assert stated == [], (
        f"{stated} now state a fibre content. That is only correct if a source states it: "
        f"a ball band, a manufacturer's specification, a supplier's declaration. A fibre "
        f"word in the yarn name is not one")


def test_an_empty_field_never_reads_as_no_fibre_concerns():
    """The consumer refuses rather than treating silence as a clean bill.

    `publish.pdf.fibres_named` is the reader that matters: today it falls back to the yarn
    name, which is why it returns something for a Launch-0 product. What it must never do is
    return a *composition*. The patch that makes it prefer the new field -- and keeps the
    refusal when neither is available -- is in `research/VISUAL_GOVERNANCE.md` for the owner
    of `publish/pdf.py`.
    """
    from brambleloop.publish import pdf

    cir = vessels.build_hexagon_coaster()
    assert all(not m.states_fibre_content for m in cir.materials)
    fibres, read_from = pdf.fibres_named(cir)
    assert fibres == ("cotton",)
    assert "Material.name" in read_from
    assert "%" not in read_from and "content" in read_from

    nameless = vessels.build_hexagon_coaster()
    nameless.materials[0] = Material(name="Bernat Blanket",
                                     colorway=nameless.materials[0].colorway,
                                     color_id=nameless.materials[0].color_id)
    assert nameless.materials[0].fibre_content == ()
    fibres, why = pdf.fibres_named(nameless)
    assert fibres == ()
    assert "inventing one" in why


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
    sys.exit(1 if fails else 0)
