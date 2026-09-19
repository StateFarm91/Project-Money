"""Buyer language, and the two ways a search strategy becomes a description of ourselves.

v1.4.3 requirement 293. Before a seasonal product launches, its search strategy is built from
what buyers actually type across six facets. The requirement exists because a shop's own
vocabulary is invisible to it: "heirloom mosaic throw in pine and cream" is how this company
thinks about a product and is not a search anybody performs.

The failures held here are the two that produce a strategy nobody can tell is empty: a facet
filled with our own words, which yields phrases that look like research, and a ranked list
that blends assumed phrases with observed ones so the distinction is gone by the time anybody
acts on it.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.commerce import intent as I  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/intent.sqlite")
    db.create_all()
    return db


def _map(**over) -> dict:
    base = dict(object="stocking", technique="tapestry", recipient_or_use="teacher gift",
                aesthetic="nordic", season_event="christmas", skill_feature="easy")
    base.update(over)
    return I.map_product(**{k: v for k, v in base.items() if v is not None})


# ---- our vocabulary is not buyer language --------------------------------


def test_a_facet_filled_with_our_own_words_is_refused():
    """A facet filled with our language is worse than an empty one: it produces phrases that
    look like research."""
    try:
        _map(aesthetic="quietly luxurious heirloom")
    except I.IntentRefused as e:
        assert "look like research" in str(e)
        assert "heirloom" in str(e)
    else:
        raise AssertionError("the shop's own vocabulary became a search facet")


def test_a_facet_of_pure_adjective_is_refused():
    try:
        _map(object="lovely beautiful")
    except I.IntentRefused as e:
        assert "does not search for an adjective" in str(e)
    else:
        raise AssertionError("an adjective was accepted as the object of a search")


def test_the_words_a_buyer_types_are_not_the_words_a_premise_may_use():
    """'easy' and 'gift' describe nothing in a creative premise and are most of what a
    shopper types. The same word is empty in one place and load-bearing in the other."""
    from brambleloop.creative.concept import GENERIC_TOKENS

    assert "easy" in GENERIC_TOKENS
    assert "easy" not in I.EMPTY_FOR_SEARCH
    assert _map(skill_feature="easy")["skill_feature"] == "easy"


def test_a_query_with_no_object_is_refused_because_it_is_a_category_browse():
    try:
        _map(object=None)
    except I.IntentRefused as e:
        assert "category browse" in str(e)
    else:
        raise AssertionError("a strategy was built with no object to search for")


def test_the_gifting_facets_are_required_because_that_is_how_seasonal_buyers_search():
    for absent in ("recipient_or_use", "season_event"):
        try:
            _map(**{absent: None})
        except I.IntentRefused as e:
            assert absent in str(e)
        else:
            raise AssertionError(f"{absent} was optional")


def test_an_invented_facet_is_refused():
    try:
        I.map_product(object="stocking", recipient_or_use="gift", season_event="christmas",
                      colour="pine")
    except I.IntentRefused as e:
        assert "a word somebody wanted in the title" in str(e)
    else:
        raise AssertionError("an extra facet was accepted")


# ---- the phrases, and what they are made of -------------------------------


def test_phrases_are_built_in_the_orders_buyers_type():
    rows = I.phrases(_map())
    phrases = {r["phrase"] for r in rows}

    assert "christmas stocking crochet pattern" in phrases
    assert "crochet stocking for teacher gift" in phrases
    assert len({r["pattern"] for r in rows}) >= 4


def test_a_pattern_missing_its_facet_is_skipped_rather_than_half_built():
    rows = I.phrases(_map(technique=None, aesthetic=None, skill_feature=None))
    patterns = {r["pattern"] for r in rows}

    assert "technique_led" not in patterns
    assert "aesthetic_led" not in patterns
    assert "object_led" in patterns
    assert all(r["phrase"].strip() == r["phrase"] for r in rows)


# ---- assumed is not observed ----------------------------------------------


def test_with_no_market_evidence_every_phrase_is_labelled_assumed():
    report = I.strategy(_db(), facet_map=_map())

    assert report["observed"] == []
    assert report["observed_share"] == 0.0
    assert all(r["evidence"] == I.ASSUMED for r in report["assumed"])
    assert "is not research" in report["note"]


def test_a_phrase_a_recorded_observation_contains_is_promoted_to_observed():
    db = _db()
    from brambleloop.core.models import Keyword

    with db.session() as s:
        s.add(Keyword(phrase="christmas stocking crochet pattern"))

    report = I.strategy(db, facet_map=_map())

    assert [r["phrase"] for r in report["observed"]] == [
        "christmas stocking crochet pattern"]
    assert 0 < report["observed_share"] < 1
    assert "the rest are assumed" in report["note"]


def test_observed_and_assumed_are_never_blended_into_one_list():
    """Blended, the distinction is gone by the time anybody acts on the ranking."""
    report = I.strategy(_db(), facet_map=_map())

    assert set(report) >= {"observed", "assumed"}
    assert "ranked" not in report


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
