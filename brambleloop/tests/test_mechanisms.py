"""What a competitor's listing is doing, taken apart into things nobody owns.

Requirement 214's two unbuilt halves. Decomposition is the dangerous step, and in a specific
way: a decomposition that keeps the expression is a copy with extra steps. What is learnable
is why something works commercially -- a size card that removes support questions, a bundle
that makes the anchor look cheap. What is not learnable is the chart, the photograph, the
pattern text and the depicted subject, and a "mechanism" written down as *a gnome with a
striped hat* has decomposed nothing.

The second test worth reading is the tournament one. Most listings do not justify a
tournament, and a pipeline that turns every competitor listing into one spends the creative
budget on whatever the competitor published -- which is handing them the roadmap.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.culture import rights  # noqa: E402
from brambleloop.intel import mechanisms as M  # noqa: E402


def _mech(**kw) -> M.Mechanism:
    args = dict(listing_ref="mjs-1042", klass=M.INFORMATION,
                what="size card in frame three",
                effect="removes the sizing question before it reaches support",
                evidence_ref="observation/mjs-2026-09-12")
    args.update(kw)
    return M.Mechanism(**args)


# ---- the expression may not survive ---------------------------------------


def test_a_depicted_subject_is_not_a_mechanism():
    try:
        _mech(klass=M.PRESENTATION, what="a gnome with a striped hat",
              effect="makes the listing feel festive and inviting at thumbnail scale")
    except M.MechanismRefused as e:
        assert "described in an analytical tone" in str(e)
    else:  # pragma: no cover
        raise AssertionError("the product was described and called a decomposition")


def test_every_depiction_word_is_caught_in_the_effect_too():
    for word in ("snowman", "pumpkin", "unicorn", "motif"):
        try:
            _mech(what="the first frame", effect=f"shows the {word} clearly at small size")
        except M.MechanismRefused as e:
            assert "not how it works" in str(e), word
        else:  # pragma: no cover
            raise AssertionError(f"{word!r} survived decomposition")


def test_the_check_uses_word_boundaries_rather_than_substrings():
    """`cat` inside `catalogue` would make the rule unusable and teach people to route
    around it, which is worse than not having it."""
    m = _mech(what="catalogue-wide price anchoring",
              effect="makes the single pattern look inexpensive beside the bundle")
    assert m.klass == M.INFORMATION


def test_a_protected_token_cannot_be_carried_away_in_a_mechanism():
    tokens = [rights.ProtectedToken(text="Rudolph", asset_class=rights.CHARACTER_NAME,
                                    source="a film")]
    m = _mech(what="the hero frame", effect="places Rudolph where the eye lands first")
    try:
        M.decompose(listing_ref="mjs-1042", mechanisms=[m], protected_tokens=tokens)
    except M.MechanismRefused as e:
        assert "what it may not carry away" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a protected token survived decomposition")


def test_a_clean_decomposition_passes_the_same_check_creative_output_passes():
    tokens = [rights.ProtectedToken(text="Rudolph", asset_class=rights.CHARACTER_NAME,
                                    source="a film")]
    out = M.decompose(listing_ref="mjs-1042", mechanisms=[_mech()], protected_tokens=tokens)
    assert out["by_class"] == {M.INFORMATION: 1}


# ---- a mechanism claims an effect -----------------------------------------


def test_an_observation_that_cannot_be_wrong_is_refused():
    try:
        _mech(what="lifestyle photography", effect="looks nice")
    except M.MechanismRefused as e:
        assert "cannot be wrong" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an observation was recorded as a mechanism")


def test_a_mechanism_names_the_dated_observation_it_came_from():
    try:
        _mech(evidence_ref="  ")
    except M.MechanismRefused as e:
        assert "something somebody thought about a competitor" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a mechanism with no evidence was accepted")


def test_every_class_is_about_how_rather_than_what():
    for klass in ("presentation", "packaging", "pricing", "information", "range", "service",
                  "construction"):
        assert klass in M.CLASSES
    assert len(M.CLASSES) == 7


def test_an_invented_class_is_refused():
    try:
        _mech(klass="vibe")
    except M.MechanismRefused as e:
        assert "copy with extra steps" in str(e)
    else:  # pragma: no cover
        raise AssertionError("the class vocabulary grew")


def test_unexamined_classes_are_listed_rather_than_assumed_absent():
    out = M.decompose(listing_ref="mjs-1042", mechanisms=[_mech()])
    assert M.PRICING in out["classes_unexamined"]
    assert "has not established that the pricing is ordinary" in out["why"]


# ---- most listings are notes ----------------------------------------------


def _decomposition(n: int):
    mechs = [_mech(what=f"mechanism {i}",
                   effect="does a specific commercial thing worth checking later")
             for i in range(n)]
    return M.decompose(listing_ref="mjs-1042", mechanisms=mechs)


def test_a_listing_with_nothing_new_is_a_note():
    out = M.justifies_tournament(
        decomposition=_decomposition(3),
        already_have={"mechanism 0", "mechanism 1", "mechanism 2"},
        arena_has_evidence=True)
    assert out["decision"] == M.NOTE_ONLY
    assert "the creative budget is the thing being protected" in out["why"]


def test_one_new_mechanism_is_still_a_note():
    out = M.justifies_tournament(decomposition=_decomposition(3),
                                 already_have={"mechanism 0", "mechanism 1"},
                                 arena_has_evidence=True)
    assert out["decision"] == M.NOTE_ONLY and out["new_mechanisms"] == 1


def test_two_new_mechanisms_in_an_evidenced_arena_justify_a_search():
    out = M.justifies_tournament(decomposition=_decomposition(3),
                                 already_have={"mechanism 0"}, arena_has_evidence=True)
    assert out["decision"] == M.TOURNAMENT
    assert "a search, not a response" in out["why"]


def test_an_arena_with_no_demand_evidence_never_justifies_one():
    out = M.justifies_tournament(decomposition=_decomposition(5), already_have=set(),
                                 arena_has_evidence=False)
    assert out["decision"] == M.NO_ARENA_EVIDENCE
    assert "following rather than competing" in out["why"]


def test_the_tournament_carries_mechanisms_and_never_the_expression():
    out = M.justifies_tournament(decomposition=_decomposition(4), already_have=set(),
                                 arena_has_evidence=True)
    assert "never the expression" in out["carries"]


def test_state_names_the_failure_decomposition_is_for():
    out = M.state()
    assert out["requirement"] == 214
    assert "copy with extra steps" in out["note"]
    assert "handing them the roadmap" in out["most_listings_are_notes"]
    assert "culture.rights" in out["builds_on"]


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
