"""What this company is obliged to do when the benchmark proves demand.

v1.4.3 requirements 306, 307, 308, 309. The mission's commercial argument is that watching a
successful shop tells you where the demand is, and the argument only pays if something happens
when it does — so #306 is written as an obligation rather than a permission.

The line these tests hold is finer than the ones drawn elsewhere in this build. A competitor's
photographs, instructions and distinctive design are protected. "Cropped V-neck button
cardigan" is not: it is what the category *is*, visible to anyone looking at a finished object,
and a rule that forbade it would make the intelligence mission conclude that the useful answer
is never to act on what it found.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.intel import response as R  # noqa: E402


# ---- the arena obligation (#306) ------------------------------------------


def test_a_generic_finished_object_characteristic_may_be_preserved():
    """The permitted side, and it is wide on purpose."""
    decision = R.consider_arena(
        "cardigan", enter=True,
        reason="the benchmark proves sustained demand for cropped button cardigans here",
        preserved=("silhouette", "neckline", "closure", "colour_blocking"),
        differentiator="deterministic grading across every size, reverse-compiled")
    assert decision.enter is True
    assert decision.pod == "garments"
    keys = {p["key"] for p in decision.to_dict()["preserved_characteristics"]}
    assert keys == {"silhouette", "neckline", "closure", "colour_blocking"}


def test_anything_that_only_makes_sense_as_a_reference_to_their_product_is_refused():
    for phrase in ("we should copy their colourway because it clearly works well",
                   "match their design as closely as we reasonably can here",
                   "build it as close as possible to the one they already sell"):
        try:
            R.consider_arena("cardigan", enter=True, reason=phrase,
                             differentiator="deterministic grading across every size")
        except R.ResponseRefused as e:
            assert "identifies the source rather than the arena" in str(e)
        else:
            raise AssertionError(f"a source reference was accepted: {phrase}")


def test_must_consider_is_satisfied_by_a_recorded_refusal_and_not_by_silence():
    """The only version anybody can check, and silence is what a queue produces."""
    declined = R.consider_arena(
        "amigurumi", enter=False,
        reason=("the pod has no sculptural shaping capability validated yet and entering "
                "would ship something we cannot certify"))
    assert declined.enter is False
    assert declined.reason

    try:
        R.consider_arena("cardigan", enter=False, reason="no")
    except R.ResponseRefused as e:
        assert "considered refusal and not by a short one" in str(e)
    else:
        raise AssertionError("a one-word refusal counted as consideration")


def test_entering_on_parity_is_refused_through_the_competitive_door_too():
    """#163's rule arriving from the benchmark side rather than the teardown side."""
    try:
        R.consider_arena("stocking", enter=True,
                         reason="the benchmark sells a great many of these every December")
    except R.ResponseRefused as e:
        assert "Entering on parity is the floor" in str(e)
    else:
        raise AssertionError("an arena was entered with nothing to offer")


def test_preserved_characteristics_is_a_closed_list():
    """Otherwise it becomes the place their design goes."""
    try:
        R.consider_arena("cardigan", enter=True,
                         reason="the benchmark proves demand for this silhouette in this size",
                         preserved=("their stripe rhythm",),
                         differentiator="deterministic grading")
    except R.ResponseRefused as e:
        assert "from becoming a place to put their design" in str(e)
    else:
        raise AssertionError("an open characteristic was preserved")


# ---- seasonalising (#307, #308) -------------------------------------------


def test_answering_only_the_palette_is_a_recolour_with_a_seasons_name_on_it():
    """The exact output this build measured as its creativity defect."""
    palette_only = R.seasonalise("cropped-cardigan", "cardigan",
                                 {"colour_palette": "forest, cranberry, cream and gold"})
    assert palette_only["palette_only"] is True
    assert palette_only["complete"] is False
    assert "recolour with a season's name on it" in palette_only["note"]
    assert len(palette_only["unanswered"]) == len(R.SEASONAL_LENSES) - 1


def test_the_owners_christmas_cardigan_example_runs_as_a_fixture_not_a_special_case():
    """#308 is a worked example of #306 and #307, so it is tested as one."""
    decision = R.consider_arena(
        "cardigan", enter=True,
        reason=("the benchmark demonstrates a proven cropped striped cardigan arena and this "
                "pod can serve the same broad buyer"),
        preserved=("silhouette", "neckline", "closure", "colour_blocking", "size_range"),
        differentiator=("every size graded deterministically and reverse-compiled, which the "
                        "category does not do"))
    assert decision.enter is True

    seasonal = R.seasonalise("cropped-striped-cardigan", "cardigan", {
        "colour_palette": "forest, cranberry, cream and gold",
        "styling": "photographed over a collared shirt for a family table",
        "trim": "cream tipped cuffs and a gold-flecked button band",
        "motif_vocabulary": "no motif: the stripe rhythm carries it",
        "gift_context": "bought by an adult for themselves in the week they host",
        "supporting_accessories": "a matching cuff-and-collar set sold beside it",
        "bundles": "cardigan plus the accessory set at a set price",
        "merchandising": "listed as a winter-hosting piece rather than a Christmas jumper",
    })
    assert seasonal["complete"] is True
    assert seasonal["palette_only"] is False

    # And the eight lenses are answered about the object, not about theirs.
    assert "forest, cranberry" in seasonal["answered"]["colour_palette"]


def test_a_seasonal_answer_that_references_the_source_is_refused():
    try:
        R.seasonalise("x", "cardigan", {"colour_palette": "the same colours as their version"})
    except R.ResponseRefused as e:
        assert "identifies the source" in str(e)
    else:
        raise AssertionError("a seasonal lens carried a source reference")


# ---- the pipeline (#309) --------------------------------------------------


def test_a_stage_cannot_run_before_the_one_it_depends_on():
    """A long pipeline fails by one stage quietly becoming optional."""
    run = R.PipelineRun(signal="mjs:listing:1234")
    assert run.next_stage == "observation"

    try:
        run.advance("cir_engineering", gate_passed=True)
    except R.ResponseRefused as e:
        assert "quietly becoming optional" in str(e)
    else:
        raise AssertionError("a pipeline stage was skipped")

    step = run.advance("observation", gate_passed=True, evidence="benchmark_observation:1")
    assert step["advanced"] is True
    assert step["next"] == "pod_routing"


def test_a_failed_gate_stops_the_run_rather_than_marking_it_amber():
    run = R.PipelineRun(signal="mjs:listing:1234")
    run.advance("observation", gate_passed=True)
    blocked = run.advance("pod_routing", gate_passed=False)
    assert blocked["advanced"] is False
    assert "rather than continuing with the stage marked" in blocked["why"]
    assert run.next_stage == "pod_routing"


def test_the_pipeline_names_every_stage_and_its_gate():
    """A stage nobody named cannot be noticed missing."""
    assert len(R.PIPELINE) == 14
    for stage, gate in R.PIPELINE:
        assert stage and gate and len(gate.split()) >= 4, stage
    names = [s for s, _ in R.PIPELINE]
    # The order encodes the argument: nothing is engineered before the season is decided,
    # and nothing publishes before it is certified and challenged.
    assert names.index("demand_and_season_fit") < names.index("cir_engineering")
    assert names.index("certification") < names.index("benchmark_challenge")
    assert names.index("benchmark_challenge") < names.index("launch")
    assert names[-1] == "measurement"


def test_a_complete_run_reaches_measurement():
    run = R.PipelineRun(signal="mjs:listing:1234")
    for stage in R.PIPELINE_STAGES:
        run.advance(stage, gate_passed=True, evidence=f"{stage}-evidence")
    assert run.to_dict()["complete"] is True
    assert run.next_stage is None


def test_the_boundary_is_stated_where_somebody_can_read_it():
    described = R.describe()
    assert "may be preserved" in described["boundary"]
    assert "only makes sense as a reference to their product" in described["boundary"]
    assert set(described["seasonal_lenses"]) == set(R.SEASONAL_LENSES)


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
