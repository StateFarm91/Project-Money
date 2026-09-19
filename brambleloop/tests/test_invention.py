"""The creativity defect the owner named, and the machinery that addresses it.

v1.4.3 requirements 106-110, 115, 124, 125, 127, 129. The defect is measured rather than
asserted: `creative/audit.py` compiles all eleven catalogue products and finds one component
shape, one construction and two stitches. That is not a taste failure. It is a generator with
one degree of freedom being asked for variety and answering with colour.

Nothing in a validator fixes that, because given a season and a category the highest-probability
output *is* the commodity — the commodity is what the category is made of. What fixes it is
making the brief carry the novelty, so the generator is asked for a specific unusual thing
rather than for a good thing. These tests are about the briefs refusing to be ordinary, and
about the bar being allowed to move.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.creative import invention as I  # noqa: E402
from brambleloop.creative import standard as S  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/invention.sqlite")
    db.create_all()
    return db


# ---- the invention matrix (#106) ------------------------------------------


def test_one_dimension_is_a_category_and_a_category_is_the_commodity():
    try:
        I.cross("motif", "motif", season="christmas",
                premise="an ornament with a nice seasonal motif on the front of it")
    except I.InventionRefused as e:
        assert "which is a category" in str(e)
    else:
        raise AssertionError("a single-dimension brief was accepted")

    # Near-synonyms are the same failure wearing two names.
    try:
        I.cross("storage", "organization", season="fall",
                premise="a basket that holds things and also keeps them sorted neatly")
    except I.InventionRefused as e:
        assert "one idea stated twice" in str(e)
    else:
        raise AssertionError("two near-synonymous dimensions were crossed")

    good = I.cross("tableware", "character", season="christmas",
                   premise=("a set of cutlery pockets whose folded shapes read as a family "
                            "of carol singers when the table is laid"))
    assert good.dimension_a == "tableware"
    assert "carol singers" in good.premise


def test_the_matrix_is_a_queue_rather_than_an_intention():
    """Breadth that exists as a list of empty slots is breadth somebody can work through."""
    slots = I.matrix("christmas")
    assert len(slots) == len(I.NAMED_PAIRS)
    pairs = {(s["dimension_a"], s["dimension_b"]) for s in slots}
    for required in (("motif", "function"), ("holiday", "storage"),
                     ("character", "household_utility"), ("tableware", "character"),
                     ("modularity", "gifting")):
        assert required in pairs, required
    assert all("the same decision rather than two features" in s["prompt"] for s in slots)


# ---- the transformation engine (#107) -------------------------------------


def test_a_transformation_is_an_abstract_pattern_never_somebody_s_product():
    try:
        I.transform("becomes_a_set", from_form="sphere",
                    to_function="table protection",
                    description="a copy of the pumpkin one that splits into coasters")
    except I.InventionRefused as e:
        assert "Learn the transformation, never the expression" in str(e)
    else:
        raise AssertionError("a specific competitor product entered the engine")

    original = I.transform(
        "becomes_a_set", from_form="sphere", to_function="table protection",
        description=("a closed sculptural form whose segments detach into flat discs, so "
                     "the decorative object is the storage for the useful one"))
    assert original.pattern == "becomes_a_set"
    assert original.to_dict()["meaning"]

    try:
        I.transform("looks_nice", from_form="sphere", to_function="table protection",
                    description="x" * 40)
    except I.InventionRefused as e:
        assert "not a transformation pattern" in str(e)
    else:
        raise AssertionError("an invented transformation pattern was accepted")


# ---- the silhouette gate (#108) -------------------------------------------


def test_a_generic_form_with_no_qualifier_is_a_disc_among_discs():
    result = I.silhouette(
        form="round_disc",
        premise="a set of round coasters worked in a textured stitch for the winter table",
        title="Winter Coasters")
    assert result["generic_form"] is True
    assert result["passes"] is False
    assert "one is every one" in result["problems"][0]

    rescued = I.silhouette(
        form="round_disc",
        premise=("each disc is one segment of a sculptural gourd that reassembles into the "
                 "closed form when the table is cleared"),
        title="Winter Coasters",
        qualifiers=("transformation",))
    assert rescued["passes"] is True


def test_a_premise_that_needs_its_title_is_weak_and_reading_them_together_hides_it():
    """#108's own sentence, enforced literally by removing the title's words."""
    result = I.silhouette(
        form="basket",
        premise="a gingerbread village basket",
        title="Gingerbread Village Basket")
    assert result["passes"] is False
    assert "needs its title to explain why it is interesting" in result["problems"][-1]
    assert result["specific_words_without_title"] == []

    standing = I.silhouette(
        form="basket",
        premise=("the rim is shaped into a row of rooflines so the whole thing reads as a "
                 "street seen from above"),
        title="Gingerbread Village Basket")
    assert standing["passes"] is True


# ---- the emotional promise (#109) -----------------------------------------


def test_a_feeling_delivered_in_listing_copy_is_the_failure_this_requirement_names():
    try:
        I.promise("cosy", "texture", "perfect for snuggling on the sofa this winter")
    except I.InventionRefused as e:
        assert "visible in the object" in str(e)
        assert "sound off" in str(e)
    else:
        raise AssertionError("listing copy passed as an execution")

    real = I.promise("cosy", "texture",
                     "a deep looped pile that holds shadow, so the photograph reads as weight")
    assert real.execution == "texture"
    assert real.to_dict()["execution_meaning"]

    try:
        I.promise("cosy", "wishing", "a deep looped pile that holds shadow")
    except I.InventionRefused as e:
        assert "not a way an object delivers a feeling" in str(e)
    else:
        raise AssertionError("an invented execution was accepted")


# ---- the motif grammar (#110) ---------------------------------------------


def test_a_concept_built_only_from_saturated_motifs_is_the_commodity_by_construction():
    everybody = I.motifs("christmas", ("tree", "santa", "snow"))
    assert everybody["all_saturated"] is True
    assert "the commodity by construction" in everybody["note"]

    recombined = I.motifs("christmas", ("tree", "post_box", "lantern"))
    assert recombined["all_saturated"] is False
    assert recombined["fresh"] == ["post_box", "lantern"]
    # The grammar is broad on purpose, and what is unused is the interesting list.
    assert len(recombined["unused"]) > 10


def test_inventing_a_motif_per_concept_is_how_a_grammar_stops_being_one():
    try:
        I.motifs("halloween", ("ghost", "a spooky vibe"))
    except I.InventionRefused as e:
        assert "Widening the grammar is a deliberate decision" in str(e)
    else:
        raise AssertionError("an invented motif was accepted")

    for season in ("christmas", "fall", "halloween", "spring", "summer"):
        assert len(I.MOTIF_GRAMMAR[season]) >= 10, season


# ---- the wow requirement (#115) -------------------------------------------


def test_a_flagship_with_no_wow_mechanism_is_clean_correct_and_forgettable():
    missing = I.wow("FLAGSHIP", None)
    assert missing.ok is False
    assert "forgettable" in missing.problems[0]

    ungrounded = I.wow("FLAGSHIP", "modular_reveal", "it has a reveal")
    assert ungrounded.ok is False
    assert "a checkbox is what a generator learns to tick" in ungrounded.problems[0]

    grounded = I.wow("FLAGSHIP", "modular_reveal",
                     "the assembled squares form a continuous rooftop line no single square "
                     "shows")
    assert grounded.ok is True

    # A quick make owes no wow mechanism: the requirement is about flagships.
    assert I.wow("QUICK", None).ok is True


# ---- the rising floor (#124) ----------------------------------------------


def test_the_floor_is_the_companys_own_trailing_median_so_it_rises():
    """A concept that would have passed six months ago can fail today."""
    early = [S.Scored(f"e{i}", 0.50) for i in range(20)]
    later = [S.Scored(f"l{i}", 0.78) for i in range(20)]

    assert S.floor(early)["floor"] == 0.5
    assert S.floor(later)["floor"] == 0.78

    concept = 0.62
    assert S.meets_standard(concept, make_lane="SHORT", history=early)["passes"] is True
    assert S.meets_standard(concept, make_lane="SHORT", history=later)["passes"] is False


def test_a_bad_quarter_cannot_lower_the_standard_permanently():
    """A trailing median alone is a fixed threshold arriving from the other direction."""
    weak = [S.Scored(f"w{i}", 0.20) for i in range(20)]
    result = S.floor(weak)
    assert result["floor"] == S.ABSOLUTE_FLOOR
    assert result["held_by_absolute"] is True

    thin = S.floor([S.Scored("a", 0.9), S.Scored("b", 0.9)])
    assert thin["derived_from"] == "absolute"
    assert "whichever four they were" in thin["reason"]


# ---- top decile, and boring as a verdict (#125, #129) ---------------------


def test_a_flagship_aims_at_the_top_decile_rather_than_the_category_mean():
    scores = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80, 0.88, 0.94]
    aim = S.aspiration(scores)
    assert aim["measurable"] is True
    assert aim["top_decile"] > aim["category_mean"]
    assert "definition of forgettable" in aim["note"]

    history = [S.Scored(f"h{i}", 0.55) for i in range(20)]
    acceptable = S.meets_standard(0.70, make_lane="FLAGSHIP", history=history,
                                  benchmark_scores=scores)
    assert acceptable["passes"] is True
    assert acceptable["meets_flagship_target"] is False
    assert "not what a flagship is for" in acceptable["note"]

    assert S.aspiration([0.4, 0.9, 0.7])["measurable"] is False


def test_boring_is_a_verdict_and_no_correctness_score_overrides_it():
    """#129's most important sentence: agents must be able to reject technically valid ideas."""
    history = [S.Scored(f"h{i}", 0.40) for i in range(20)]
    rejected = S.meets_standard(0.99, make_lane="FLAGSHIP", history=history,
                                taste_rejection="boring")
    assert rejected["passes"] is False
    assert rejected["rejected_on"] == "taste"
    assert "exactly what a boring concept passes" in rejected["note"]

    try:
        S.meets_standard(0.9, make_lane="SHORT", history=history,
                         taste_rejection="not sure about it")
    except S.StandardRefused as e:
        assert "is not a judgement" in str(e)
    else:
        raise AssertionError("an open-ended taste rejection was accepted")


# ---- the autopsy (#127) ---------------------------------------------------


def test_forty_rejections_with_no_reasons_is_a_shortlist_and_no_learning():
    db = _db()
    empty = S.autopsy_patterns(db)
    assert empty["autopsies"] == 0
    assert "produced a shortlist and no learning" in empty["note"]

    for i in range(6):
        S.autopsy(db, concept_key=f"c{i}", cohort="christmas-2026",
                  reason="obvious" if i < 5 else "floor",
                  detail="the first idea anybody has for this brief, arrived at six times",
                  score=0.3)
    patterns = S.autopsy_patterns(db, cohort="christmas-2026")
    assert patterns["autopsies"] == 6
    assert patterns["dominant_reason"] == "obvious"
    # Five of six rejected for the same reason is a brief problem, not six concept problems.
    assert "a brief problem rather than" in patterns["note"]


def test_an_autopsy_needs_a_recorded_reason_and_a_specific_detail():
    db = _db()
    try:
        S.autopsy(db, concept_key="c", cohort="x", reason="did not like it",
                  detail="it was not very good at all really")
    except S.StandardRefused as e:
        assert "forty reasons and no pattern" in str(e)
    else:
        raise AssertionError("a free-text rejection reason was recorded")

    try:
        S.autopsy(db, concept_key="c", cohort="x", reason="boring", detail="boring")
    except S.StandardRefused as e:
        assert "says what specifically was wrong" in str(e)
    else:
        raise AssertionError("an autopsy with no detail was recorded")


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
