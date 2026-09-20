"""#240: whether the catalogue competes with itself, and whether it stuffs to avoid it.

The two failures are opposites, which is the difficulty. A catalogue all reaching for one
head term ranks its own listings against each other; a catalogue fixing that by loading every
term anybody might type gets demoted for it. Both have to be counted, and a module that
counted only one would push the catalogue straight into the other.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import portfolio as P  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Listing  # noqa: E402


def _db(rows=()):
    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        for slug, title, tags in rows:
            s.add(Listing(product_slug=slug, version="1.0.0", title=title,
                          description="", tags=list(tags), price_cad=9.0))
    return db


def test_a_title_repeating_a_word_is_stuffing_even_when_the_word_is_furniture():
    """The commonest form of stuffing there is.

    Furniture is excluded from the tag count on purpose -- a tag set where every slot
    contains "crochet" is just how tags work. Excluding it from the *title* would make the
    check blind to exactly the case it exists for.
    """
    stuffed = P.stuffing("Crochet Pattern Crochet Blanket Crochet Throw",
                         ["crochet blanket", "crochet throw", "crochet afghan"])
    assert stuffed["stuffed"] is True
    assert stuffed["repeated_in_title"] == ["crochet"]

    clean = P.stuffing("Nordic Star Christmas Ornament Crochet Pattern",
                       ["christmas ornament", "nordic", "mosaic crochet", "teacher gift"])
    assert clean["stuffed"] is False, clean


def test_tags_spending_their_slots_on_one_word_are_stuffing():
    stuffed = P.stuffing("Mosaic Throw Pattern",
                         ["mosaic throw", "mosaic blanket", "mosaic afghan",
                          "mosaic crochet", "mosaic pattern"])
    assert stuffed["stuffed"] is True
    assert stuffed["most_repeated_word"] == "mosaic"
    assert stuffed["share_of_slots"] == 1.0


def test_a_listing_with_no_tags_is_a_different_problem():
    empty = P.stuffing("Nordic Star Ornament", [])
    assert empty["measurable"] is False
    assert "different problem" in empty["why"]


def test_the_facets_a_listing_claims_are_read_from_the_shared_vocabulary():
    read = P.listing_facets(
        "Nordic Star Christmas Ornament Crochet Pattern",
        ["christmas ornament", "nordic", "mosaic crochet", "teacher gift"])
    assert read["stated"]["object"] == ["ornament"]
    assert read["stated"]["season_event"] == ["christmas"]
    assert read["stated"]["aesthetic"] == ["nordic"]
    assert read["required_missing"] == [], read


def test_an_empty_catalogue_is_not_a_diversified_one():
    out = P.diversification(_db())
    assert out["measurable"] is False
    assert "not a diversified one" in out["reason"]


def test_a_catalogue_all_reaching_for_one_term_is_concentrated_and_cannibalising():
    """Eleven listings competing for one query have one listing's worth of visibility."""
    rows = [(f"throw{i}", "Christmas Throw Crochet Pattern",
             ["christmas throw", "christmas blanket", "christmas gift"])
            for i in range(5)]
    out = P.diversification(_db(rows))
    assert out["measurable"] is True
    assert "object" in out["concentrated_on"], out["facets"]["object"]
    assert out["facets"]["object"]["share"] == 1.0
    # Every pair is competing, which is 10 pairs across 5 listings.
    assert len(out["competing_pairs"]) == 10, out["competing_pairs"]


def test_a_spread_catalogue_is_neither_concentrated_nor_cannibalising():
    rows = [
        ("orn", "Nordic Star Christmas Ornament Crochet Pattern",
         ["christmas ornament", "nordic", "teacher gift"]),
        ("throw", "Mosaic Autumn Throw Crochet Pattern",
         ["autumn throw", "mosaic", "mantel"]),
        ("hat", "Beginner Valentine Hat Crochet Pattern",
         ["valentines hat", "beginner", "baby"]),
    ]
    out = P.diversification(_db(rows))
    assert out["concentrated_on"] == [], out["facets"]
    assert out["competing_pairs"] == []
    assert out["stuffing"] == []


def test_one_listing_stating_a_facet_is_thin_coverage_not_concentration():
    """The finding exactly inverted, caught by a test rather than shipped.

    A facet a single listing states reported 100% concentration and was flagged as crowded.
    One listing cannot be ranked against itself, so the least crowded facet in the catalogue
    was being reported as its most crowded.
    """
    rows = [
        ("orn", "Nordic Star Christmas Ornament Crochet Pattern",
         ["christmas ornament", "nordic", "teacher gift"]),
        ("throw", "Mosaic Autumn Throw Crochet Pattern",
         ["autumn throw", "mosaic", "mantel"]),
    ]
    out = P.diversification(_db(rows))
    aesthetic = out["facets"]["aesthetic"]
    assert aesthetic["listings_stating_it"] == 1
    assert aesthetic["share"] == 1.0
    assert aesthetic["concentrated"] is False, aesthetic
    assert aesthetic["sole_occupant"] is True
    assert "nothing for it to compete with" in aesthetic["why"]
    assert "aesthetic" not in out["concentrated_on"]


def test_a_facet_no_listing_states_is_absent_rather_than_diverse():
    """Absent is not spread. A catalogue that names no technique has not diversified
    technique, it has left it empty."""
    rows = [("a", "Christmas Ornament Crochet Pattern", ["christmas ornament", "gift"]),
            ("b", "Autumn Throw Crochet Pattern", ["autumn throw", "mantel"])]
    out = P.diversification(_db(rows))
    technique = out["facets"]["technique"]
    assert technique["measurable"] is False
    assert "absent rather than diverse" in technique["why"]


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
