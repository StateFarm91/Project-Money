"""The creativity engine, and the defect it was built to measure.

v1.4.3 requirements 83, 84, 85, 87, 88, 94, 104. The owner judged the generated catalogue
materially below the required creative standard and called it a Build-2 defect. The useful
response is a gate that would notice if it were fixed — and whose first act is to fail our own
products for a reason we can point at in the code.

Most of these tests are attacks on the gate itself, because a creative gate that passes
everything is worse than none: it produces a certificate.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.creative import audit, jury, tournament  # noqa: E402
from brambleloop.creative.concept import (  # noqa: E402
    Concept, ConceptRefused, Field, distance,
)


def _concept(key: str, **over) -> Concept:
    base = dict(
        key=key, title=key.replace("-", " ").title(),
        premise="A fir-tree yoke that reads as a wreath when the cardigan is buttoned.",
        pod="garments", form="fitted_garment", construction="top_down_yoke",
        motif="fir-wreath", palette_story="forest and cranberry",
        recipient="partner", occasion="christmas", feeling="heirloom",
        function="turns the one photograph everyone takes on the day into the garment",
        make_lane="LONG")
    base.update(over)
    return Concept(**base)


# ---- what a concept has to be ---------------------------------------------


def test_a_concept_cannot_be_described_in_words_nobody_chose():
    """The vocabularies are closed because an open field accepts 'nice'.

    A free-text `feeling` scores well against every check written to read English and tells a
    buyer nothing, which is exactly how a generated catalogue passes a prose review.
    """
    for bad in ({"feeling": "lovely"}, {"form": "thing"}, {"construction": "somehow"},
                {"occasion": "whenever"}, {"recipient": "someone"},
                {"make_lane": "MEDIUM-ISH"}):
        try:
            _concept("x", **bad)
        except ConceptRefused as e:
            assert "closed vocabulary" in str(e)
        else:
            raise AssertionError(f"accepted {bad}")

    # And #88's one-sentence visual premise is required before any engineering.
    try:
        _concept("x", premise="A cardigan.")
    except ConceptRefused as e:
        assert "visual premise" in str(e)
    else:
        raise AssertionError("a concept with no premise was accepted")


def test_a_recolour_is_the_same_idea_and_the_distance_says_zero():
    """#84's explicit exclusion: superficial colour and name variations.

    Palette is deliberately not a term in the distance function. If it were, twenty recolours
    would read as a diverse field and the tournament would be a formality — which is what the
    current catalogue is evidence of.
    """
    original = _concept("fir-yoke-cardigan")
    recolour = _concept("fir-yoke-cardigan-cream", palette_story="oat and clay")
    assert distance(original, recolour) == 0.0

    renamed = _concept("winter-yoke-cardigan", title="Winter Yoke Cardigan",
                       palette_story="ink and silver")
    assert distance(original, renamed) == 0.0

    # Rewriting the sentence cannot rescue an identical structure.
    reworded = _concept(
        "fir-yoke-again", palette_story="moss",
        premise="A pine-crown shoulder that becomes a garland once fastened at the throat.")
    assert distance(original, reworded) < 0.2

    # A genuinely different idea in the same arena is far away.
    different = _concept("stocking-advent", form="stocking", construction="in_the_round",
                         motif="numbered-pockets", pod="stockings",
                         function="holds twenty-four small gifts and becomes the countdown",
                         make_lane="MEDIUM")
    assert distance(original, different) > 0.6


# ---- the jury -------------------------------------------------------------


def test_one_critic_is_enough_because_a_scoring_jury_averages_the_fatal_objection_away():
    """#85. The jury is not a score.

    Five approvals and one "this is our fourth throw" averages to a healthy number, and the
    fourth throw ships. Same arithmetic mistake as averaging the confidence ladder.
    """
    ours = [_concept("existing-fir-yoke")]
    clone = _concept("new-fir-yoke", palette_story="different")

    verdict = jury.judge(clone, jury.Context(catalogue=ours))
    assert verdict.decision == jury.REJECTED
    assert [f.critic for f in verdict.findings] == ["sameness"]
    assert verdict.survives is False
    # The finding names what is shared, so the autopsy can be acted on.
    assert "form" in verdict.findings[0].evidence["shared"]


def test_structural_cleanliness_is_never_approval():
    """#83, and the honesty this whole module turns on.

    The structural critics are real and they cannot tell whether a thing is desirable. That
    needs eyes. So while nothing in this system can see, the best available verdict is
    `needs_taste` — and a concept reaching engineering on structural cleanliness alone is
    exactly what #83 forbids.
    """
    clean = _concept("fir-yoke-cardigan")
    verdict = jury.judge(clean, jury.Context(catalogue=[]))

    assert verdict.decision == jury.NEEDS_TASTE
    assert verdict.survives is True
    assert set(verdict.unjudged) == {"thumbnail_legibility", "craft_impression"}
    assert jury.APPROVED != verdict.decision

    # Judged and good is approval; judged and weak is rejection. Both require a judgement.
    judged = _concept("fir-yoke-judged", thumbnail_reads_small=True, craft_impression=4.2)
    assert jury.judge(judged, jury.Context()).decision == jury.APPROVED

    weak = _concept("fir-yoke-weak", thumbnail_reads_small=True, craft_impression=2.0)
    weak_verdict = jury.judge(weak, jury.Context())
    assert weak_verdict.decision == jury.REJECTED
    assert weak_verdict.findings[0].critic == "craft_impression"


def test_the_critics_each_catch_the_thing_they_are_named_for():
    """Six critics, six distinct failures. A critic that never fires is decoration."""
    # Genericness: a premise made of words that describe any crochet product.
    generic = _concept("cosy-throw", premise="A lovely warm cosy blanket for your home.")
    assert jury.genericness(generic, jury.Context()) is not None
    assert jury.genericness(_concept("ok"), jury.Context()) is None

    # Emotional appeal: the default answer to every brief.
    default = _concept("plain", recipient="self", occasion="everyday", feeling="cosy")
    assert jury.weak_emotional_appeal(default, jury.Context()) is not None

    # And a concept that cannot say what it does for its owner.
    purposeless = _concept("purposeless", function="")
    assert jury.weak_emotional_appeal(purposeless, jury.Context()) is not None

    # Derivative: inside a benchmark product's radius.
    theirs = [_concept("their-fir-yoke")]
    assert jury.derivative(_concept("ours", palette_story="x"),
                           jury.Context(benchmark=theirs)) is not None

    # Thumbnail: a small object whose appeal is fine detail.
    tiny = _concept("filigree-ornament", form="ornament",
                    premise="An intricate filigree snowflake with delicate openwork arms.")
    assert jury.thumbnail(tiny, jury.Context()) is not None

    # Complexity: more techniques than the lane repays.
    quick = _concept("overbuilt", make_lane="QUICK")
    assert jury.unnecessary_complexity(quick, jury.Context(techniques=6)) is not None
    assert jury.unnecessary_complexity(quick, jury.Context(techniques=2)) is None


# ---- the tournament -------------------------------------------------------


def test_twenty_recolours_are_refused_as_a_field_before_any_of_them_is_judged():
    """#84's real requirement is the word 'materially'.

    Twenty concepts are trivially produced by varying a palette twenty times, and that looks
    like a tournament in every report anybody reads. So the field is judged first.
    """
    recolours = Field("christmas cardigan",
                      [_concept(f"fir-yoke-{i}", palette_story=f"colourway {i}")
                       for i in range(14)])
    try:
        tournament.check_field(recolours)
    except tournament.FieldRefused as e:
        assert "one idea in 14 costumes" in str(e)
    else:
        raise AssertionError("a field of recolours passed as a tournament")

    # A short field is refused too: the first plausible idea wins by default.
    try:
        tournament.check_field(Field("x", [_concept(f"a{i}", form="stocking")
                                           for i in range(4)]))
    except tournament.FieldRefused as e:
        assert "not a tournament" in str(e)
    else:
        raise AssertionError("a four-concept shortlist passed as a tournament")


def test_a_genuinely_diverse_field_runs_and_most_of_it_dies():
    """The pass rate is expected to be low (#85). A jury that passes everything is a stamp."""
    forms = ["fitted_garment", "stocking", "ornament", "basket", "pillow", "bag",
             "wall_hanging", "runner", "toy", "wreath", "hat", "scarf"]
    constructions = ["top_down_yoke", "in_the_round", "amigurumi_shaping", "motif_join",
                     "cable_panel", "granny_square", "tapestry", "modular_panels",
                     "seamless_tube", "corner_to_corner", "bottom_up", "side_to_side"]
    concepts = [
        _concept(f"c{i}", form=forms[i], construction=constructions[i],
                 motif=f"motif-{i}", pod="seasonal_gift",
                 function=f"solves the {forms[i]} problem for a christmas host",
                 premise=f"A {forms[i].replace('_', ' ')} whose {constructions[i]} "
                         f"construction reveals a second image when hung.")
        for i in range(12)]
    field = Field("christmas gifting", concepts)

    assert field.spread() > jury.FIELD_SPREAD_MINIMUM
    result = tournament.run(field, catalogue=[], benchmark=[])

    # Structurally clean concepts survive to `needs_taste` and none is approved.
    assert result.field_size == 12
    assert all(v.decision == jury.NEEDS_TASTE for v in result.survivors)
    assert all("craft_impression" in v.unjudged for v in result.survivors)
    assert "not desirable" in result.to_dict()["note"]


def test_the_autopsy_names_the_cause_rather_than_counting_the_dead():
    """#94: a creative system that cannot say what it stopped making cannot improve.

    A field dying of sameness has a generation problem; one dying of complexity has a brief
    problem. Those are different fixes, so the count alone is not the useful output.
    """
    ours = [_concept("existing-fir-yoke")]
    field = Field("christmas cardigan", [
        _concept(f"clone-{i}", palette_story=f"c{i}",
                 form=["fitted_garment", "stocking", "ornament", "bag", "hat", "pillow",
                       "basket", "toy", "wreath", "runner", "scarf", "pouch"][i],
                 construction=["top_down_yoke", "in_the_round", "amigurumi_shaping",
                               "motif_join", "cable_panel", "granny_square", "tapestry",
                               "modular_panels", "seamless_tube", "corner_to_corner",
                               "bottom_up", "side_to_side"][i],
                 function="")
        for i in range(12)])

    result = tournament.run(field, catalogue=ours)
    report = tournament.autopsy(result)

    assert report["survival_rate"] == 0.0
    assert report["dominant_cause"] == "emotional_appeal"
    assert "who they are for" in report["diagnosis"]
    assert report["examples"]["emotional_appeal"]


def test_the_scorecard_refuses_to_read_a_softening_jury_as_progress():
    """#104's north star, and the metric that would fake it.

    Survival rate alone rewards a lenient jury. Reported beside field spread, a rising
    survival rate with falling spread is visible for what it is.
    """
    assert tournament.scorecard([])["tournaments"] == 0

    early = tournament.Result("a", "", 12, 0.80, survivors=[], rejected=[])
    late = tournament.Result("b", "", 12, 0.50, survivors=[], rejected=[])
    early.survivors = [jury.Verdict("x", jury.NEEDS_TASTE, [], [])]
    late.survivors = [jury.Verdict("y", jury.NEEDS_TASTE, [], []) for _ in range(6)]

    card = tournament.scorecard([early, late])
    assert card["spread_trend"] == "declining"
    assert card["survival_trend"] == "improving"
    assert "jury going soft" in card["warning"]


# ---- the defect ------------------------------------------------------------


def test_the_gate_fails_our_own_catalogue_and_says_why():
    """The measurement the owner's defect report deserves.

    Not "creativity is low" but: which critic fires, on how many products, and what in the
    generator produces it.
    """
    report = audit.audit_catalogue()

    assert report["products_audited"] == 11
    assert report["survivors"] == [], "the gate passed products the owner judged below standard"
    assert report["rejected"] == 11
    assert report["autopsy"]["survival_rate"] == 0.0
    assert "no representation of an idea" in report["root_cause"]


def test_the_generators_degrees_of_freedom_are_measured_from_the_cir_not_asserted():
    """The finding that does not depend on any judgement made in this module.

    The concept mapping involves choices — which slug means which form, what a missing field
    defaults to — and a conclusion resting on those is arguable. This one rests on compiling
    all eleven products and looking at what came out.
    """
    freedom = audit.generator_degrees_of_freedom()

    assert freedom["products"] == 11
    assert freedom["constructions_used"] == {"flat_rows": 11}
    assert freedom["components_per_product"] == {"1": 11}
    assert freedom["stitch_vocabularies"] == {"dc,sc": 11}
    assert "construction" in freedom["does_not_vary"]
    assert "same object at different widths" in freedom["finding"]


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
