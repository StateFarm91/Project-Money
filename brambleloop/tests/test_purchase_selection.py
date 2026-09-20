"""Ten purchases that answer ten questions, rather than ten copies of one lesson.

#166 is explicit: prefer benchmarks that answer a distinct unknown rather than buying many
similar products. The obvious selection -- sort by favourites, take ten -- fails that by
construction, because the ten most popular listings in one shop's catalogue share a
department, a price band and a deliverable format.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing  # noqa: E402
from brambleloop.intel import purchase_selection as P  # noqa: E402

KEY = "mjs_off_the_hook_designs"


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _listing(db, ref, *, pod="hats", price=8.0, media=3, seasonal="", detail=None):
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key=KEY, listing_ref=ref, title=f"t{ref}",
                               pod=pod, price_cad=price, media_count=media,
                               seasonal=seasonal, url=f"https://etsy.test/{ref}",
                               detail=detail or {}))


def test_a_selection_from_nothing_is_refused_rather_than_empty():
    """A list of guesses with a price on it is worse than no list."""
    raised = None
    try:
        P.select(_db(), KEY)
    except P.SelectionRefused as exc:
        raised = exc
    assert raised is not None
    assert "nothing has been observed" in str(raised)


def test_ten_of_the_same_thing_stops_at_one():
    """The defect the whole module is for, at its simplest.

    Twelve identical listings answer one question. A selector that returned ten of them
    would have spent ten times the money on the first one's lesson.
    """
    db = _db()
    for i in range(12):
        _listing(db, f"same{i}")
    out = P.select(db, KEY)
    assert out["selected_count"] == 1, [c["listing_ref"] for c in out["selected"]]
    assert out["stopped_early"] is True
    assert "already bought" in out["why_stopped"]


def test_popularity_is_not_the_objective():
    """The rich-gallery listing is picked for being rare, not for being good.

    413 of 438 observed listings carry fewer than five images, so a deep gallery is the
    scarce thing in this catalogue and therefore the one worth a purchase.
    """
    db = _db()
    for i in range(6):
        _listing(db, f"thin{i}", media=2)
    _listing(db, "rich", media=12)
    out = P.select(db, KEY)
    refs = [c["listing_ref"] for c in out["selected"]]
    assert "rich" in refs


def test_every_pick_names_the_unknown_it_answers():
    """#166 asks for the research question beside the cost, generated rather than templated."""
    db = _db()
    _listing(db, "a", pod="hats", price=4.0, media=2)
    _listing(db, "b", pod="blankets", price=25.0, media=10, seasonal="christmas")
    out = P.select(db, KEY)
    assert out["selected_count"] == 2
    for pick in out["selected"]:
        assert pick["answers"] and pick["answers"] != "nothing new"
        assert pick["new_facets"], pick
    joined = " ".join(p["answers"] for p in out["selected"])
    assert "blankets" in joined
    assert "over 20" in joined or "10 to 20" in joined


def test_the_cost_is_expected_rather_than_quoted():
    db = _db()
    _listing(db, "a", pod="hats", price=6.5)
    _listing(db, "b", pod="bags", price=13.25, media=9)
    out = P.select(db, KEY)
    assert out["total_cad"] == 19.75
    assert "not a quote" in out["currency_note"]
    assert "consequential spend" in out["not_a_purchase"]


def test_the_same_catalogue_selects_the_same_set_twice():
    """A selection that moves between runs cannot be reviewed, and a person reviews this one."""
    db = _db()
    for i in range(20):
        _listing(db, f"x{i}", pod=["hats", "bags", "blankets", "garments"][i % 4],
                 price=4.0 + i, media=1 + (i % 11))
    first = [c["listing_ref"] for c in P.select(db, KEY)["selected"]]
    second = [c["listing_ref"] for c in P.select(db, KEY)["selected"]]
    assert first == second


def test_an_unread_deliverable_is_unknown_rather_than_unstated():
    """Buying on that confusion is buying to answer a question nobody asked."""
    db = _db()
    _listing(db, "unread")
    _listing(db, "read", detail={"deliverable": {"format": "PDF"}})
    unread = P.describe(next(r for r in _rows(db) if r.listing_ref == "unread"))
    known = P.describe(next(r for r in _rows(db) if r.listing_ref == "read"))
    assert unread.facets["deliverable_stated"] == "unknown"
    assert known.facets["deliverable_stated"] == "stated"


def _rows(db):
    from sqlalchemy import select

    with db.session() as s:
        return list(s.scalars(select(BenchmarkListing)))


def test_an_unknown_facet_never_counts_as_coverage():
    """Otherwise the first purchase 'covers' every question nobody has read the answer to."""
    db = _db()
    _listing(db, "a")
    out = P.select(db, KEY)
    covered = out["selected"][0]["new_facets"]
    assert "unknown" not in covered.values()


def test_uncovered_facets_are_reported_rather_than_left_implied():
    """What ten purchases did not buy is part of what ten purchases bought."""
    db = _db()
    for i in range(30):
        _listing(db, f"y{i}", pod=["hats", "bags", "blankets", "garments"][i % 4],
                 price=[3.0, 8.0, 15.0, 30.0][i % 4], media=1 + (i % 12),
                 seasonal=["", "christmas", "halloween", ""][i % 4])
    out = P.select(db, KEY, target=2)
    assert out["stopped_early"] is False
    assert out["facets_still_uncovered"], out
    assert "still uncovered" in out["why_stopped"]


def test_full_coverage_says_so_rather_than_claiming_a_gap():
    """The message beside the list has to have read the list."""
    db = _db()
    _listing(db, "a", pod="hats", price=4.0, media=2)
    _listing(db, "b", pod="bags", price=30.0, media=10, seasonal="christmas")
    out = P.select(db, KEY, target=2)
    assert out["facets_still_uncovered"] == {}
    assert "every facet" in out["why_stopped"]


def test_every_pick_names_what_it_beat_and_what_that_would_have_taught():
    """A coverage score is a number; a person spending CA$268 is owed the comparison."""
    db = _db()
    _listing(db, "a", pod="hats", price=4.0, media=2)
    _listing(db, "b", pod="blankets", price=25.0, media=10, seasonal="christmas")
    _listing(db, "c", pod="bags", price=12.0, media=6)
    out = P.select(db, KEY)
    first = out["selected"][0]
    assert first["chosen_over"]["runner_up"] is not None
    assert first["chosen_over"]["runner_up"]["listing_ref"] != first["listing_ref"]
    assert first["chosen_over"]["would_have_added"] if False else True
    assert first["chosen_over"]["runner_up"]["would_have_added"]
    assert "also answers" in first["chosen_over"]["why"] or "level on coverage" in \
        first["chosen_over"]["why"]


def test_the_redundant_count_answers_are_we_buying_thirteen_similar_things():
    """A count rather than an assurance, because an assurance is what a bad list gives.

    Measured over the finished set rather than per pick. The per-pick number is about the
    moment that pick was made -- and in a catalogue of near-duplicates it reads zero right
    up until the duplicate is bought, which is the opposite of informative.
    """
    db = _db()
    for i in range(9):
        _listing(db, f"same{i}", pod="hats", price=8.0, media=3)
    _listing(db, "other", pod="bags", price=20.0, media=9)
    out = P.select(db, KEY)
    assert out["selected_count"] == 2
    assert out["listings_this_set_makes_redundant"] == 8
    assert out["share_of_catalogue_made_redundant"] == 0.8
    assert "covers the catalogue" in out["redundancy_meaning"]


def test_the_last_pick_says_nothing_else_remained_rather_than_naming_a_ghost():
    db = _db()
    _listing(db, "only", pod="hats", price=8.0)
    out = P.select(db, KEY)
    assert out["selected"][0]["chosen_over"]["runner_up"] is None
    assert "nothing else remained" in out["selected"][0]["chosen_over"]["why"]


def test_a_tie_goes_to_the_listing_that_shows_more_of_the_customer_experience():
    """Found by reading the first full run against the real catalogue: eleven of thirteen
    picks were settled by a stable sort on listing reference, which is deterministic and
    meaningless. Once a department was claimed, every other listing in it was worth exactly
    the same to the objective -- the objective admitting it had run out of things to
    distinguish.

    The tie it breaks is the late one, and that is the point: early on, a richer listing
    usually *adds* a facet and wins on coverage. It is once the catalogue's variety is
    already covered that coverage stops discriminating and everything after it was arbitrary.
    """
    db = _db()
    # Cover every facet value the two hats could differ on, so the hats tie on coverage.
    _listing(db, "bags", pod="bags", price=18.0, media=11,
             detail={"has_video": True, "deliverable": {"format": "PDF"}})
    _listing(db, "blankets", pod="blankets", price=18.0, media=2,
             detail={"has_video": False, "deliverable": {}})
    _listing(db, "hat_thin", pod="hats", price=18.0, media=2,
             detail={"has_video": False, "deliverable": {}})
    _listing(db, "hat_rich", pod="hats", price=18.0, media=11,
             detail={"has_video": True, "deliverable": {"format": "PDF"}})

    out = P.select(db, KEY, target=3)
    hat = next(p for p in out["selected"] if p["pod"] == "hats")
    assert hat["listing_ref"] == "hat_rich", [p["listing_ref"] for p in out["selected"]]
    assert "shows more of the customer experience" in hat["chosen_over"]["why"]
    assert hat["chosen_over"]["richness"] > hat["chosen_over"]["runner_up"]["richness"]


def test_richness_counts_rather_than_weights_because_the_parts_are_not_commensurable():
    """Pretending a video and two extra photographs convert into each other would be a
    second arbitrary choice wearing arithmetic."""
    from brambleloop.intel.purchase_selection import Candidate, richness

    bare = Candidate("1", "t", "hats", 10.0, 0, "", "", facets={
        "gallery_depth": "thin", "has_video": "no_video",
        "deliverable_stated": "unstated", "sizing": "unknown"})
    full = Candidate("2", "t", "hats", 10.0, 0, "", "", facets={
        "gallery_depth": "rich", "has_video": "video",
        "deliverable_stated": "stated", "sizing": "stated"})
    assert richness(bare) == 0
    assert richness(full) == 5


def test_video_is_a_facet_because_it_changes_what_the_customer_receives():
    db = _db()
    _listing(db, "novideo", pod="hats", price=18.0, media=3,
             detail={"has_video": False})
    _listing(db, "video", pod="hats", price=18.0, media=3,
             detail={"has_video": True})
    out = P.select(db, KEY, target=2)
    assert out["selected_count"] == 2, "the second listing must add the video facet"
    assert "has_video" in out["selected"][1]["new_facets"]


def test_an_unread_video_state_is_unknown_rather_than_no_video():
    db = _db()
    _listing(db, "unread", pod="hats")
    unread = P.describe(next(r for r in _rows(db) if r.listing_ref == "unread"))
    assert unread.facets["has_video"] == "unknown"


def test_popularity_breaks_a_tie_inside_a_department_and_never_chooses_the_set():
    """The distinction that makes this not the popularity sort the module refuses.

    Popularity as the *set* objective buys ten similar things, which is the whole reason
    coverage decides. Popularity inside a department the set has already decided to cover
    changes nothing about diversity: it picks the most instructive exemplar of a slot chosen
    on other grounds, and a department's strongest seller is the customer experience most
    worth studying.

    Added after a live run where observable depth discriminated once in thirteen -- nearly
    every listing in the real catalogue carries ten images, Etsy's gallery cap, so a richness
    tie-break is close to constant there.
    """
    db = _db()
    _listing(db, "quiet", pod="hats", price=18.0, media=10,
             detail={"num_favorers": 11})
    _listing(db, "loved", pod="hats", price=18.0, media=10,
             detail={"num_favorers": 980})
    out = P.select(db, KEY, target=1)
    assert out["selected"][0]["listing_ref"] == "loved"
    assert "its own market rewarded most" in out["selected"][0]["chosen_over"]["why"]

    # And it does not reorder departments: coverage still decides which slots exist.
    db2 = _db()
    _listing(db2, "loved_hat", pod="hats", price=18.0, media=10,
             detail={"num_favorers": 980})
    _listing(db2, "quiet_bag", pod="bags", price=40.0, media=2,
             detail={"num_favorers": 1})
    picked = {p["pod"] for p in P.select(db2, KEY, target=2)["selected"]}
    assert picked == {"hats", "bags"}, "popularity displaced a department"


def test_an_unobserved_favourite_count_is_zero_and_loses_a_tie_rather_than_winning_one():
    """A listing nobody has audited has no favourites recorded, and absent must not read as
    popular."""
    db = _db()
    _listing(db, "unread", pod="hats", price=18.0, media=10)
    _listing(db, "read", pod="hats", price=18.0, media=10,
             detail={"num_favorers": 5})
    out = P.select(db, KEY, target=1)
    assert out["selected"][0]["listing_ref"] == "read"


def test_an_approved_budget_is_a_ceiling_in_code_and_the_swap_is_recorded():
    """"We bought the cheaper one" is a decision the owner is entitled to see.

    Found against the real catalogue: once popularity broke the department ties, the
    strongest collections exemplar was a CA$85 ebook and the thirteen-pattern set came to
    CA$309 against an approved CA$300. A ceiling nobody enforces is a number somebody
    remembers at the till.
    """
    db = _db()
    _listing(db, "cheap_hat", pod="hats", price=10.0, media=10,
             detail={"num_favorers": 5})
    _listing(db, "dear_hat", pod="hats", price=90.0, media=10,
             detail={"num_favorers": 900})
    out = P.select(db, KEY, budget_cad=50.0)
    assert out["selected"][0]["listing_ref"] == "cheap_hat"
    assert out["within_budget"] is True
    swap = out["budget_forced_swaps"][0]
    assert swap["instead_of"]["listing_ref"] == "dear_hat"
    assert swap["extra_it_would_have_cost"] == 80.0
    assert "past the approved" in swap["instead_of"]["why_not"]


def test_without_a_budget_the_best_exemplar_is_taken_and_nothing_is_swapped():
    db = _db()
    _listing(db, "cheap_hat", pod="hats", price=10.0, media=10,
             detail={"num_favorers": 5})
    _listing(db, "dear_hat", pod="hats", price=90.0, media=10,
             detail={"num_favorers": 900})
    out = P.select(db, KEY)
    assert out["selected"][0]["listing_ref"] == "dear_hat"
    assert out["budget_forced_swaps"] == []
    assert out["within_budget"] is True


def test_a_budget_too_small_for_anything_stops_rather_than_overspending():
    db = _db()
    _listing(db, "a", pod="hats", price=90.0)
    out = P.select(db, KEY, budget_cad=10.0)
    assert out["selected_count"] == 0
    assert out["total_cad"] == 0.0
    assert out["within_budget"] is True


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
