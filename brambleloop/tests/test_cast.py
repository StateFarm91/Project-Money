"""Characters this company owns, and the difference between owning one and naming one.

Requirement 146. The long-term goal is in the requirement itself: *not permanent dependence
on external pop culture*. Two things follow, and both are refusals rather than features.

Recurrence cannot be declared. "Customers return for it" is a claim about the second time, so
an element becomes `recurring` by having recurred and there is no field that promotes it -- a
roster populated by writing names in it measures enthusiasm.

And originality is checked on the primitives, never on the name. The dangerous failure is not
a product that borrows openly; that path exists and is routed. It is a character with an
original name whose design is a recognisable external one, which looks like an asset, carries
the full legal risk of the thing it resembles, and cannot be defended because nobody wrote
down what it was derived from.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.culture import cast as C  # noqa: E402
from brambleloop.culture import rights, translate  # noqa: E402

TOKENS = [rights.ProtectedToken(text="Rudolph", asset_class=rights.CHARACTER_NAME,
                                source="a film")]


def _element(**kw) -> C.Element:
    args = dict(key="pim", kind=C.CHARACTER, name="Pim the Hare",
                about="a small hare who over-decorates everything every single year",
                derived_from={"emotion": "chaotic warmth",
                              "era": "classic_storybook_winter"})
    args.update(kw)
    return C.propose(**args, declared_tokens=TOKENS)


def _appear(element: C.Element, n: int, season: str) -> None:
    C.record_appearance(element, C.Appearance(product_slug=f"p{n}", season=season,
                                              released_on="2026-11-01"))


# ---- recurrence cannot be declared ----------------------------------------


def test_a_new_element_is_proposed_and_says_what_it_still_needs():
    e = _element()
    assert e.status == C.PROPOSED
    assert e.to_dict()["needs"] == {"appearances": C.MIN_APPEARANCES,
                                    "seasons": C.MIN_SEASONS}


def test_there_is_no_field_that_promotes_an_element_to_recurring():
    assert "status" not in C.Element.__dataclass_fields__
    assert "recurring" not in C.Element.__dataclass_fields__
    e = _element()
    e.name = "Pim"
    assert e.status == C.PROPOSED


def test_an_element_becomes_recurring_by_having_recurred():
    e = _element()
    _appear(e, 1, "christmas-2026")
    _appear(e, 2, "christmas-2026")
    assert e.status == C.PROPOSED, "three products in one season is a collection"
    _appear(e, 3, "christmas-2027")
    assert e.status == C.RECURRING


def test_appearances_in_one_season_are_not_enough_however_many():
    e = _element()
    for n in range(8):
        _appear(e, n, "christmas-2026")
    assert e.status == C.PROPOSED
    assert len(e.seasons) == 1


def test_one_product_cannot_be_counted_twice_toward_recurrence():
    e = _element()
    _appear(e, 1, "christmas-2026")
    try:
        C.record_appearance(e, C.Appearance(product_slug="p1", season="christmas-2027",
                                            released_on="2027-11-01"))
    except C.CastRefused as ex:
        assert "without recurring" in str(ex)
    else:  # pragma: no cover
        raise AssertionError("a roster reached recurring by counting one product twice")


def test_an_appearance_must_name_its_season():
    try:
        C.Appearance(product_slug="p1", season="  ", released_on="2026-11-01")
    except C.CastRefused as e:
        assert "across several is IP" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an appearance with no season was accepted")


# ---- originality is checked on the primitives -----------------------------


def test_a_protected_token_in_the_description_is_refused_however_original_the_name():
    """The failure being guarded: the name is the only original part."""
    try:
        _element(about="a hare who helps Rudolph decorate the tree every single year")
    except C.CastRefused as e:
        assert "borrowed however it is named" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an element borrowed in everything but its name was accepted")


def test_a_protected_token_hidden_in_a_primitive_is_refused_too():
    try:
        _element(derived_from={"emotion": "the warmth of Rudolph", "era": "retro_halloween"})
    except C.CastRefused as e:
        assert "borrowed however it is named" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a protected token passed inside a primitive")


def test_the_check_uses_word_boundaries_rather_than_substrings():
    """Substring matching fires on 'art' inside 'heart' and teaches everybody to work around
    the check, so this reuses rights.check_free_of rather than implementing a second one."""
    e = _element(about="a hare with a heart full of tinsel and no sense of restraint")
    assert e.status == C.PROPOSED


def test_an_element_with_no_recorded_primitives_is_refused():
    try:
        _element(derived_from={})
    except C.CastRefused as e:
        assert "nothing is derived from nothing" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an element with no provenance was accepted as original")


def test_a_primitive_that_is_not_one_is_refused():
    try:
        _element(derived_from={"franchise": "a film everybody knows"})
    except C.CastRefused as e:
        assert "never as the property it came from" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a property was recorded as a primitive")


def test_every_primitive_key_comes_from_the_translation_engine():
    e = _element()
    assert set(e.derived_from) <= set(translate.PRIMITIVE_KEYS)


def test_an_invented_kind_is_refused():
    try:
        _element(kind="mascot")
    except C.CastRefused as e:
        assert "not an owned-IP kind" in str(e)
    else:  # pragma: no cover
        raise AssertionError("the roster grew a category")


def test_every_kind_the_requirement_names_is_present():
    for kind in ("character", "motif", "joke", "tradition", "collection_world"):
        assert kind in C.KINDS


def test_a_name_with_no_description_is_refused():
    try:
        _element(about="a hare")
    except C.CastRefused as e:
        assert "the roster is supposed to hold more than names" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a bare name was accepted onto the roster")


# ---- retirement -----------------------------------------------------------


def test_an_element_can_be_retired_and_a_roster_that_only_grows_never_does():
    e = _element()
    C.retire(e, "three seasons running it sold nothing anybody could attribute to it")
    assert e.status == C.RETIRED


def test_retiring_needs_a_reason():
    try:
        C.retire(_element(), "tired of it")
    except C.CastRefused as e:
        assert "argue with" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an element was retired on a shrug")


def test_a_retired_element_does_not_quietly_come_back():
    e = _element()
    C.retire(e, "three seasons running it sold nothing anybody could attribute to it")
    try:
        _appear(e, 1, "christmas-2028")
    except C.CastRefused as ex:
        assert "somebody decided twice" in str(ex)
    else:  # pragma: no cover
        raise AssertionError("a retired element accumulated standing again")


# ---- a world must answer for something it has never seen ------------------


def _world(**kw) -> C.World:
    args = dict(key="hollow", name="Bramble Hollow",
                premise="a village under the snow where everybody over-decorates everything",
                admits=("ornaments", "home_decor", "stockings"),
                excludes=("garments",))
    args.update(kw)
    return C.World(**args)


def test_a_world_answers_for_a_product_it_has_never_seen():
    world = _world()
    assert C.can_host(world, object_category="ornaments")["can_host"] is True
    assert C.can_host(world, object_category="garments")["can_host"] is False


def test_an_undecided_category_is_a_decision_rather_than_a_yes():
    out = C.can_host(_world(), object_category="bags")
    assert out["can_host"] is False
    assert "not a setting" in out["why"]


def test_a_world_that_admits_nothing_is_a_label_for_what_already_exists():
    try:
        _world(admits=())
    except C.CastRefused as e:
        assert "before the thing it holds is made" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a bundle was accepted as a world")


def test_a_world_needs_a_premise_somebody_could_design_against():
    try:
        _world(premise="christmas things")
    except C.CastRefused as e:
        assert "design against" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a world was created from two words")


def test_a_category_both_admitted_and_excluded_answers_nothing():
    try:
        _world(admits=("ornaments",), excludes=("ornaments",))
    except C.CastRefused as e:
        assert "answers nothing" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a world contradicted itself")


# ---- the direction, not the state -----------------------------------------


def test_the_roster_counts_recurring_apart_from_proposed():
    proposed = _element()
    recurring = _element(key="fen", name="Fen the Fox")
    for n, season in ((1, "a"), (2, "a"), (3, "b")):
        _appear(recurring, n, season)
    out = C.roster([proposed, recurring])
    assert out["recurring"] == 1 and out["proposed"] == 1
    assert "measures enthusiasm" in out["note"]


def test_dependence_refuses_to_answer_from_one_reading():
    out = C.dependence([{"period": "2026-Q4", "borrowed": 3, "owned": 1}])
    assert out["readable"] is False
    assert "fewest that can have a direction" in out["why"]


def test_dependence_with_no_history_at_all_says_so():
    out = C.dependence([])
    assert out["readable"] is False
    assert "falling is the requirement" in out["why"]


def test_a_falling_borrowed_share_is_the_direction_the_requirement_asks_for():
    out = C.dependence([{"period": "a", "borrowed": 8, "owned": 2},
                        {"period": "b", "borrowed": 3, "owned": 7}])
    assert out["direction"] == "toward_owned"
    assert out["change"] < 0


def test_a_rising_borrowed_share_names_what_it_costs():
    out = C.dependence([{"period": "a", "borrowed": 2, "owned": 8},
                        {"period": "b", "borrowed": 9, "owned": 1}])
    assert out["direction"] == "toward_borrowed"
    assert "withdrawn in January" in out["why"]


def test_an_unchanged_share_is_flat_and_flat_is_not_progress():
    out = C.dependence([{"period": "a", "borrowed": 5, "owned": 5},
                        {"period": "b", "borrowed": 5, "owned": 5}])
    assert out["direction"] == "flat"
    assert "not progress" in out["why"]


def test_state_says_the_roster_is_empty_rather_than_implying_otherwise():
    out = C.state()
    assert out["requirement"] == 146
    assert "the roster is empty" in out["today"]
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
