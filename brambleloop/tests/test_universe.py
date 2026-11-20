"""Cells to generate against, and the discipline of measuring the cells.

v1.4.3 requirements 105, 113, 114, 117-123, 132. One idea runs through all of them: generate
against explicit cells and measure the cells, because the alternative is generating against a
keyword and measuring a count.

"Christmas crochet patterns" as a brief produces what the phrase suggests. The same December
contains a mantel stocking, a teacher gift under fifteen dollars, a nursery keepsake somebody
keeps for thirty years, a table setting and a front door — different products for different
people, and the only reason a catalogue ends up with six variations on a blanket is that
nothing ever asked which cell each one was for.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.creative import discovery as D  # noqa: E402
from brambleloop.creative import standard as S  # noqa: E402
from brambleloop.creative import universe as U  # noqa: E402
from brambleloop.seasonal import calendar as C  # noqa: E402


def _entrant(key: str, **kw) -> U.Entrant:
    base = dict(form="pillow", function="comfort", emotional_tone="cosy",
                construction="flat_rows", motif_family="woodland", recipient="self",
                make_time="SHORT")
    base.update(kw)
    return U.Entrant(key=key, **base)


# ---- the universe (#105, #113) --------------------------------------------


def test_christmas_spans_a_taxonomy_rather_than_a_keyword():
    """#105 singles Christmas out, and four departments done well is four chances."""
    assert len(U.UNIVERSE["christmas"]) >= 15
    for department in ("stocking", "ornament", "tree_skirt", "advent", "table_setting",
                       "pet", "keepsake"):
        assert department in U.UNIVERSE["christmas"], department

    cells = U.cells("christmas")
    assert len(cells) == len(U.UNIVERSE["christmas"]) * len(U.CONTEXTS)
    # A cell is a person in a room, which is a better question than a keyword tool produces.
    assert all(c["context_meaning"] for c in cells)

    try:
        U.cells("arbor_day")
    except U.UniverseRefused as e:
        assert "which is the commodity" in str(e)
    else:
        raise AssertionError("an occasion with no universe was accepted")


def test_depth_is_cells_covered_rather_than_a_product_count():
    have = [("blanket", "bedroom"), ("blanket", "adult_self_use"),
            ("blanket", "cottage"), ("blanket", "family_tradition"),
            ("blanket", "host_gift"), ("blanket", "child")]
    result = U.coverage("christmas", have)
    assert result["covered"] == 6
    assert result["depth"] < 0.05
    # Six products and fifteen departments with nothing: the count says one thing and the
    # catalogue says another.
    assert len(result["departments_with_nothing"]) == len(U.UNIVERSE["christmas"]) - 1
    assert "five of them are blankets" in result["note"]


def test_the_context_list_is_people_and_places_both():
    """"A teacher" and "the front door" are both cells somebody shops for."""
    assert "teacher" in U.CONTEXTS and "front_door" in U.CONTEXTS
    assert "stocking_stuffer" in U.CONTEXTS and "pet_owner" in U.CONTEXTS
    assert len(U.CONTEXTS) >= 18


# ---- the skill portfolio (#114) -------------------------------------------


def test_a_wave_of_only_flagships_is_a_portfolio_that_looks_busy():
    all_heirloom = U.skill_portfolio(["advanced_heirloom"] * 8)
    assert all_heirloom["segmented"] is False
    absent = {g["level"] for g in all_heirloom["gaps"] if g.get("absent")}
    assert "beginner_quick_win" in absent
    assert "nothing anybody keeps" in all_heirloom["note"]

    all_quick = U.skill_portfolio(["beginner_quick_win"] * 8)
    assert all_quick["segmented"] is False

    balanced = U.skill_portfolio(
        ["beginner_quick_win"] * 3 + ["intermediate"] * 5 + ["advanced_heirloom"] * 2)
    assert balanced["segmented"] is True


# ---- diversity quotas (#119) ----------------------------------------------


def test_a_tournament_dominated_by_one_construction_explored_one_construction():
    """And the entrant count is exactly the number that makes it look otherwise."""
    narrow = [_entrant(f"c{i}") for i in range(12)]
    result = U.diversity(narrow)
    assert result["entrants"] == 12
    assert result["explored"] is False
    assert "construction" in result["dominated_axes"]
    assert "makes it look otherwise" in result["note"]

    forms = ["pillow", "basket", "stocking", "ornament", "bag", "wreath", "coaster", "toy"]
    constructions = ["flat_rows", "in_the_round", "motif_join", "amigurumi_shaping",
                     "granny_square", "tapestry", "modular_panels", "corner_to_corner"]
    tones = ["cosy", "playful", "heirloom", "festive", "whimsical", "bold", "tender",
             "nostalgic"]
    wide = [_entrant(f"w{i}", form=forms[i], construction=constructions[i],
                     emotional_tone=tones[i], motif_family=f"m{i}", recipient=f"r{i}",
                     function=f"f{i}", make_time=["QUICK", "SHORT", "MEDIUM", "LONG"][i % 4])
            for i in range(8)]
    assert U.diversity(wide)["explored"] is True

    assert U.diversity([])["measurable"] is False


# ---- between the holidays (#121, #122) ------------------------------------


def test_a_shop_that_only_sells_in_december_is_closed_for_eleven_months():
    for season in ("spring", "summer", "fall", "winter"):
        result = U.between_holidays(season)
        assert result["programs"]
        assert all(p["meaning"] for p in result["programs"])
    winter = U.between_holidays("winter")
    assert any(p["key"] == "cozy_winter_neutral" for p in winter["programs"])
    # The non-holiday occasions are evergreen demand that does not wait for a date.
    keys = {o["key"] for o in winter["occasions"]}
    assert {"birthday", "baby_shower", "wedding", "teacher_gift"} <= keys


# ---- saturation (#117) ----------------------------------------------------


def test_popularity_is_not_an_argument_for_imitation():
    """Forty listings is evidence it sells and evidence the forty-first is invisible."""
    crowded = D.Archetype("pumpkin_coaster", listings=40)
    try:
        D.may_enter(crowded)
    except D.DiscoveryRefused as e:
        assert "is what everybody entering a crowded category believes" in str(e)
        assert "40 already there" in str(e)
    else:
        raise AssertionError("a crowded archetype was entered on its crowding")

    entered = D.may_enter(crowded, angle_kind="unserved_context",
                          angle="nobody makes this for a desk in an office")
    assert entered["may_enter"] is True
    assert entered["angle_kind"] == "unserved_context"

    open_ground = D.Archetype("advent_garland", listings=4)
    assert D.may_enter(open_ground)["may_enter"] is True

    # An angle has to say something specific; a category name is not an angle.
    try:
        D.may_enter(crowded, angle_kind="giftability", angle="better gifting")
    except D.DiscoveryRefused as e:
        assert "a category name is not an angle" in str(e)
    else:
        raise AssertionError("a vague angle passed")


# ---- white space (#118) ---------------------------------------------------


def test_white_space_is_mined_from_complaints_not_from_the_category():
    empty = D.white_space([])
    assert empty["minable"] is False
    assert "rediscovers the commodity" in empty["reason"]

    complaints = [
        D.Complaint("excessive_sewing", "review:acme-granny",
                    "gave up at the tenth panel"),
        D.Complaint("excessive_sewing", "review:birch-throw", "too much seaming"),
        D.Complaint("bad_sizing", "review:acme-cardigan", "stops two sizes short"),
    ]
    result = D.white_space(complaints)
    assert result["minable"] is True
    assert result["strongest"] == "excessive_sewing"
    assert result["hypotheses"][0]["support"] == 2
    assert "no search volume report is" in result["note"]

    try:
        D.Complaint("vibes", "review:x", "did not like it")
    except D.DiscoveryRefused as e:
        assert "not a complaint kind" in str(e)
    else:
        raise AssertionError("an invented complaint kind was accepted")

    try:
        D.Complaint("bad_sizing", "", "stops two sizes short")
    except D.DiscoveryRefused as e:
        assert "somebody had in the shower" in str(e)
    else:
        raise AssertionError("a sourceless complaint was accepted")


# ---- learning transfer (#120) ---------------------------------------------


def test_the_mechanism_transfers_and_the_theme_does_not():
    """The distinction collapses first under a deadline, because the design is right there."""
    moved = D.transfer("modular_character_pockets", from_season="halloween",
                       to_season="christmas",
                       original_theme="a row of carol singers along the mantel")
    assert moved["mechanism"] == "modular_character_pockets"
    assert "not the Halloween product with a hat on it" in moved["note"]

    try:
        D.transfer("modular_character_pockets", from_season="halloween",
                   to_season="christmas", original_theme="the same")
    except D.DiscoveryRefused as e:
        assert "the design travelling with the mechanism" in str(e)
    else:
        raise AssertionError("a design was carried across as a mechanism")

    try:
        D.transfer("that ghost pocket thing", from_season="halloween",
                   to_season="christmas", original_theme="a row of carol singers")
    except D.DiscoveryRefused as e:
        assert "A design cannot transfer" in str(e)
    else:
        raise AssertionError("a design was named as a transferable mechanism")


# ---- the collection calendar (#123) ---------------------------------------


def test_a_missed_milestone_is_a_portfolio_failure_rather_than_an_amber_row():
    """The failure is silent: a phase that slips becomes the next phase."""
    result = C.collection_calendar("Christmas", date(2026, 12, 25), today=date(2026, 9, 19))
    assert len(result["milestones"]) == len(C.MILESTONES)
    assert result["on_schedule"] is False
    missed = {m["milestone"] for m in result["missed"]}
    # Concept freeze and engineering start for Christmas 2026 are already behind us.
    assert "concept_freeze" in missed
    assert "engineering_start" in missed
    assert "becomes the next phase" in result["note"]

    # A year out, nothing is missed.
    early = C.collection_calendar("Christmas", date(2027, 12, 25), today=date(2026, 9, 19))
    assert early["on_schedule"] is True
    assert early["next_due"]["milestone"] == "research_start"


def test_every_milestone_says_why_it_matters():
    for key, days, why in C.MILESTONES:
        assert why and len(why.split()) >= 4, key
    days = [d for _, d, _ in C.MILESTONES]
    assert days == sorted(days, reverse=True), "milestones must run in calendar order"


# ---- north-star metrics (#132) --------------------------------------------


def test_four_metrics_are_computable_today_and_seven_need_customers():
    """A dashboard of four green numbers and seven blanks is read as four green numbers."""
    result = S.north_star({})
    assert len(result["computable_today"]) == 4
    assert len(result["needs_customers"]) == 7
    assert result["answerable"] is False
    assert "read as four green numbers" in result["note"]
    assert set(result["computable_today"]) == {
        "concept_to_engineering_survival", "concept_to_launch_survival",
        "blind_grid_score", "novelty_distance"}


def test_cohorts_rather_than_a_running_total():
    """An average of everything ever made moves too slowly to show that anything changed."""
    result = S.north_star({
        "2026-q3": {"novelty_distance": 0.20, "blind_grid_score": 0.50},
        "2026-q4": {"novelty_distance": 0.48, "blind_grid_score": 0.44},
    })
    assert result["answerable"] is True
    assert result["improving"] == ["novelty_distance"]
    assert result["regressing"] == ["blind_grid_score"]
    assert "indistinguishable from nothing changing" in result["note"]

    try:
        S.north_star({"2026-q3": {"vibes": 1.0}})
    except S.StandardRefused as e:
        assert "not north-star metrics" in str(e)
    else:
        raise AssertionError("an invented north-star metric was accepted")


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
