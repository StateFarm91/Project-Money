"""Seasonal transformation, and the recolour that must not be called one.

v1.4.3 requirements 279 and 282. The worked example the master gives -- a proven striped
cardigan in Christmas, winter, spring and fall palettes -- is in there because it is the case
most likely to be got wrong: four seasonal palettes look like four products and are one
cardigan photographed four times.

Getting it wrong is expensive in both directions. Weeks go into producing something the
concept engine already scores at zero distance from its parent, and the transformation that
would have been worth engineering never gets made because the quota was filled by recolours.

The last test here is the one that matters to the owner's standard. The creative jury's
dominant failure on the Build-1 catalogue was emotional appeal: technically perfect products
naming no moment a buyer would act on. A transformation engine that did not demand a promise
would produce more of them in seasonal colours.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.creative import seasonal_transform as T  # noqa: E402
from brambleloop.creative.concept import Concept  # noqa: E402
from brambleloop.creative.jury import Context, judge  # noqa: E402


def _parent(**over) -> Concept:
    base = dict(
        key="cosy-throw", title="Cosy Throw",
        premise="a plain ribbed throw worked in a single cream yarn",
        pod="home", form="rectangle_throw", construction="flat_rows", motif="ribbing",
        palette_story="cream", recipient="self", occasion="everyday", feeling="cosy",
        function="warms", make_lane="LONG")
    base.update(over)
    return Concept(**base)


def _engineered(parent: Concept | None = None) -> T.Transformation:
    return T.transform(
        parent or _parent(), occasion="christmas",
        layers=("motif_vocabulary", "trim"), motifs=("woodland", "lantern"),
        feeling="nostalgic", execution="motif",
        how="a lantern-lit woodland walks the length of the throw in relief stitch")


# ---- routing: what actually changes ---------------------------------------


def test_a_palette_change_is_a_photograph_not_a_pattern():
    result = T.transform(_parent(), occasion="christmas", layers=("palette", "styling"))

    assert result.route == T.REMERCHANDISE
    assert result.to_dict()["counts_as_new_product"] is False
    assert any("photograph and a listing" in p for p in result.problems)
    assert any("#292" in p for p in result.problems)


def test_gift_context_and_collection_story_change_the_listing_not_the_object():
    for layer in ("gift_context", "collection_story"):
        assert T.route_for((layer,)) == T.REMERCHANDISE


def test_a_motif_a_trim_or_a_companion_is_a_pattern():
    for layer in ("motif_vocabulary", "trim", "accessory"):
        assert T.route_for((layer,)) == T.ENGINEER


def test_one_object_changing_layer_makes_the_whole_transformation_an_engineering_job():
    assert T.route_for(("palette", "styling", "trim")) == T.ENGINEER


def test_a_transformation_with_no_layers_is_a_season_name():
    try:
        T.route_for(())
    except T.TransformRefused as e:
        assert "a seasonal name is not a layer" in str(e)
    else:
        raise AssertionError("a transformation changed nothing and was accepted")


def test_motifs_cannot_be_smuggled_into_a_presentation_only_transformation():
    """A motif is worked into the fabric, so declaring one is an engineering change."""
    try:
        T.transform(_parent(), occasion="christmas", layers=("palette",),
                    motifs=("woodland",))
    except T.TransformRefused as e:
        assert "worked into the fabric" in str(e)
    else:
        raise AssertionError("a motif was added without the pattern changing")


def test_a_season_with_no_motif_grammar_is_refused():
    try:
        T.transform(_parent(), occasion="arbor_day", layers=("trim",))
    except T.TransformRefused as e:
        assert "cannot describe in motifs" in str(e)
    else:
        raise AssertionError("a season nobody can design for was accepted")


# ---- an engineered variant has to be worth the engineering ----------------


def test_an_engineered_variant_with_no_emotional_promise_is_refused():
    """The jury's dominant failure, arriving through the seasonal door."""
    result = T.transform(_parent(), occasion="christmas",
                         layers=("motif_vocabulary",), motifs=("woodland",))

    assert result.ok is False
    assert any("NO_EMOTIONAL_PROMISE" in p for p in result.problems)
    assert any("a seasonal palette does not fix it" in p for p in result.problems)


def test_a_motif_outside_the_seasons_grammar_does_the_seasons_work_for_nobody():
    result = T.transform(_parent(), occasion="christmas",
                         layers=("motif_vocabulary",), motifs=("watermelon",),
                         feeling="nostalgic", execution="motif",
                         how="a band of fruit worked across the field")

    assert any("MOTIF_OUT_OF_SEASON" in p for p in result.problems)


def test_a_variant_built_only_from_the_saturated_motifs_is_named_as_the_commodity():
    result = T.transform(_parent(), occasion="christmas",
                         layers=("motif_vocabulary",), motifs=("tree", "santa"),
                         feeling="nostalgic", execution="motif",
                         how="a row of trees worked across the field in relief stitch")

    assert any("MOTIF_IS_THE_DEFAULT" in p for p in result.problems)


def test_listing_copy_is_not_an_execution():
    result = T.transform(_parent(), occasion="christmas",
                         layers=("trim",), feeling="nostalgic", execution="finish",
                         how="perfect for cosy winter evenings")

    assert any("PROMISE_REFUSED" in p for p in result.problems)


def test_a_flagship_transformation_still_owes_a_wow_mechanism():
    flagship = _parent(make_lane="FLAGSHIP")
    result = T.transform(flagship, occasion="christmas", layers=("trim",),
                         feeling="nostalgic", execution="finish",
                         how="a scalloped lantern edging worked into the border")

    assert any(p.startswith("WOW:") for p in result.problems)


def test_a_complete_engineered_transformation_passes():
    result = _engineered()

    assert result.route == T.ENGINEER
    assert result.ok is True, result.problems
    assert result.emotional_promise.feeling == "nostalgic"


# ---- the child concept -----------------------------------------------------


def test_a_presentation_only_transformation_has_no_child_concept():
    """Minting one would put a recolour in the catalogue through the side door."""
    result = T.transform(_parent(), occasion="christmas", layers=("palette",))
    try:
        T.derive(_parent(), result, key="x", title="X", premise="a premise of several words",
                 palette_story="forest", recipient="host", function="warms a sofa nicely")
    except T.TransformRefused as e:
        assert "side door" in str(e)
    else:
        raise AssertionError("a recolour became a catalogue entry")


def test_a_transformation_with_problems_cannot_become_a_concept():
    unresolved = T.transform(_parent(), occasion="christmas",
                             layers=("motif_vocabulary",), motifs=("woodland",))
    try:
        T.derive(_parent(), unresolved, key="x", title="X",
                 premise="a premise of several words", palette_story="forest",
                 recipient="host", function="warms a sofa nicely")
    except T.TransformRefused as e:
        assert "unresolved problems" in str(e)
    else:
        raise AssertionError("an incomplete transformation became a product")


def test_the_engine_turns_a_concept_the_jury_kills_into_one_it_does_not():
    """The owner's standard, as a test rather than an intention.

    The Build-1 catalogue failed the creative gate 0 for 11, with emotional appeal as the
    dominant cause: an everyday thing for oneself that feels cosy is the default answer to
    every crochet brief and names no moment a buyer would act on. This is that concept, and
    this is what the transformation engine does to it.

    The child still faces the jury on its own -- the engine's job is to produce something
    that survives the gate, never to be trusted instead of it.
    """
    parent = _parent()
    before = judge(parent, Context())
    assert before.decision == "rejected"
    assert [f.critic for f in before.findings] == ["emotional_appeal"]

    child = T.derive(
        parent, _engineered(parent), key="winter-woodland-throw",
        title="Winter Woodland Throw",
        premise="a lantern-lit woodland walking the length of a deep cream field",
        palette_story="cream, spruce and lantern gold", recipient="host",
        function="is given to the person hosting christmas and stays out all winter")

    after = judge(child, Context())

    assert [f.critic for f in after.findings] == [], after.findings
    assert after.decision != "rejected"
    assert child.provenance == f"transformed:{parent.key}"


# ---- #282: the worked example ----------------------------------------------


def test_the_striped_cardigan_example_produces_three_photographs_and_one_product():
    report = T.striped_cardigan_example()

    assert len(report["palette_variants"]) == 3
    assert all(v["route"] == T.REMERCHANDISE for v in report["palette_variants"])
    assert report["engineered_variant"]["route"] == T.ENGINEER
    assert report["engineered_variant"]["ok"] is True
    assert report["catalogue_growth"] == 1
    assert "zero new patterns" in report["note"]


def test_the_ladder_puts_the_cheap_transformations_first():
    """The photograph costs an afternoon and the trim costs a fortnight, and the fortnight is
    the one that feels like real work."""
    rows = T.ladder(_parent(), occasion="christmas")

    assert rows[0]["changes_the_object"] is False
    assert rows[-1]["changes_the_object"] is True


def test_the_survey_covers_every_season_the_company_can_describe():
    from brambleloop.creative.invention import MOTIF_GRAMMAR

    report = T.evaluate(_parent())

    assert {s["occasion"] for s in report["seasons"]} == set(MOTIF_GRAMMAR)


def _run() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
