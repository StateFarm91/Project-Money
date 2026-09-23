"""Dedicated capacity, a living map, and a memory that only outcomes move.

v1.4.3 requirements 302, 303, 316. Three parts of the benchmark mission, and each fails in a
way that leaves the org chart intact.

Capacity gets borrowed — sensibly, every time — until the mission has specialists on paper and
no throughput. A map fills its judgement columns from the title and looks complete while being
fiction, persuasive fiction because most of it is right. And a learning memory grows confident
by repetition, which is the one thing that cannot possibly be evidence.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.intel import capacity as C  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402
from brambleloop.intel import market_map as M  # noqa: E402
from brambleloop.intel import memory as Mem  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/mission.sqlite")
    db.create_all()
    return db


# ---- dedicated capacity (#302) --------------------------------------------


def test_generic_research_cannot_draw_below_the_reserved_floor():
    """Borrowing is locally sensible every time, which is how the mission starves."""
    assert C.reserve_check(generic_wants=5, total_specialists=10)["spare"] == 2
    try:
        C.reserve_check(generic_wants=9, total_specialists=10)
    except C.CapacityRefused as e:
        assert "org chart and no throughput" in str(e)
        assert "catalogue_coverage" in str(e)
    else:
        raise AssertionError("generic work drew below the reserved floor")


def test_scale_is_bounded_by_money_rather_than_by_a_headcount_constant():
    plenty = C.allocate(open_work=400, budget_remaining_cad=100.0, justification="coverage")
    assert plenty.granted == 50
    assert plenty.bounded_by == "work"

    broke = C.allocate(open_work=400, budget_remaining_cad=0.20, justification="coverage")
    assert broke.bounded_by == "budget"
    assert broke.granted == 4
    # The reserved floor is on top of whatever elasticity buys.
    assert broke.to_dict()["total"] == broke.granted + C.MJS_RESERVED_SPECIALISTS


def test_a_fan_out_that_cannot_name_what_it_buys_is_refused():
    """'We could use more' is what an elastic system asks for by default."""
    for reason in ("coverage", "quality", "latency"):
        assert C.allocate(open_work=10, budget_remaining_cad=5.0,
                          justification=reason).justification == reason
    try:
        C.allocate(open_work=10, budget_remaining_cad=5.0, justification="it seems useful")
    except C.CapacityRefused as e:
        assert "is buying none" in str(e)
    else:
        raise AssertionError("scale was bought with no reason")


# ---- the living map (#303) -------------------------------------------------


def test_the_judgement_columns_are_absent_rather_than_inferred_from_the_title():
    """A map that inferred them would be persuasive fiction: nine of ten columns right."""
    row = M.describe_listing({
        "listing_ref": "1", "title": "Cropped Striped Cardigan Crochet Pattern",
        "product_type": "cardigan", "price_cad": 12.0, "media_count": 7})

    assert row.pod == "garments"
    assert "generic_product_type" in row.attributes
    assert "visible_pricing" in row.attributes
    assert "gallery_structure" in row.attributes
    for judgement in M.VISION_ATTRIBUTES:
        assert judgement in row.absent, judgement
        assert "look complete and be fiction" in row.absent[judgement]

    # With the capability, the same columns fill.
    seen = M.describe_listing({
        "listing_ref": "1", "title": "Cropped Striped Cardigan", "product_type": "cardigan",
        "silhouette": "cropped, straight-sided", "merchandising_mechanism": "flat-lay first"},
        vision_available=True)
    assert "silhouette" in seen.attributes
    assert "silhouette" not in seen.absent


def test_palette_is_absent_for_want_of_a_gallery_call_not_for_want_of_a_model():
    """Etsy publishes per-image colour, so this is a request that was not made."""
    row = M.describe_listing({"listing_ref": "1", "title": "x", "product_type": "hat"})
    assert "needs a gallery call, not a model" in row.absent["palette"]

    coloured = M.describe_listing({"listing_ref": "1", "title": "x", "product_type": "hat",
                                   "palette": [{"hex": "#2f4f3a"}]})
    assert coloured.attributes["palette"]
    assert "palette" not in coloured.absent


def test_an_empty_map_is_not_a_map_of_an_empty_shop():
    db = _db()
    result = M.build(db)
    assert result["mapped"] is False
    assert "not a map of an empty shop" in result["reason"]
    assert set(result["needs_vision"]) == set(M.VISION_ATTRIBUTES)


def test_the_map_reports_its_own_staleness_and_what_changed():
    from brambleloop.core.models import BenchmarkListing

    db = _db()
    now = datetime.now(timezone.utc)
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref="a", title="Fair Isle Hat",
                               product_type="hat", price_cad=9.0, media_count=5,
                               fingerprint="f1", last_seen=now))
        s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref="b", title="Chunky Throw",
                               product_type="blanket", price_cad=14.0, media_count=8,
                               fingerprint="f2",
                               last_seen=now - timedelta(hours=M.STALE_AFTER_HOURS + 6)))

    result = M.build(db, now=now)
    assert result["mapped"] is True
    assert result["listings"] == 2
    assert result["by_pod"]["hats"] == 1
    assert result["stale_rows"] == ["b"]
    assert result["living"] is False
    # Completeness is scored against observable columns, not all ten, or the map would look
    # permanently broken rather than correctly limited.
    assert result["observable_attributes"] == len(M.ATTRIBUTES) - len(M.VISION_ATTRIBUTES)
    # Seven of the eight observable columns are filled. The eighth is palette, which is
    # absent because no gallery has been read -- a request that was not made rather than a
    # capability that is missing, and the map distinguishes those.
    assert result["completeness_of_observable"] == 0.875
    assert all("palette" in row["absent"] for row in result["rows"])
    assert "persuasive fiction" in result["note"]


# ---- the learning memory (#316) --------------------------------------------


def _lesson(db) -> int:
    return Mem.learn(db, pod="garments", subject="stripe_demand",
                     statement="striped cropped cardigans hold demand right through winter",
                     mechanism="silhouette_strength")


def test_repetition_is_refused_as_evidence():
    """Forty observations of one shop's Christmas listings is one observation, forty times."""
    db = _db()
    lesson = _lesson(db)
    for kind in Mem.NON_OUTCOMES:
        try:
            Mem.outcome(db, lesson, kind, evidence_ref="scan:2")
        except Mem.MemoryRefused as e:
            assert "is not an outcome" in str(e)
        else:
            raise AssertionError(f"{kind} moved a lesson")

    assert Mem.report(db)["untested"] == 1
    assert "hypotheses the pods are carrying" in Mem.report(db)["note"]


def test_only_an_outcome_moves_a_lesson_and_it_names_its_evidence():
    db = _db()
    lesson = _lesson(db)
    moved = Mem.outcome(db, lesson, "launch_sold", evidence_ref="ledger:1")
    assert moved["direction"] == "supports"
    assert moved["supports"] == 1

    try:
        Mem.outcome(db, lesson, "owner_veto", evidence_ref="   ")
    except Mem.MemoryRefused as e:
        assert "it is an assertion" in str(e)
    else:
        raise AssertionError("an outcome was recorded with no evidence")


def test_a_challenger_wins_on_outcomes_or_it_does_not_win():
    """Otherwise the memory tracks whoever last wrote a paragraph."""
    db = _db()
    incumbent = _lesson(db)
    Mem.outcome(db, incumbent, "launch_sold", evidence_ref="ledger:1")

    rival = Mem.challenge(db, incumbent,
                          statement="the demand is the colour blocking rather than the crop",
                          mechanism="colour_architecture")
    # Newer, better argued, no outcomes: the incumbent stands.
    held = Mem.resolve(db, pod="garments", subject="stripe_demand")
    assert held["active_lesson_id"] == incumbent
    assert held["changed"] is False
    assert "promoting on novelty" in held["note"]

    # Two supporting outcomes beat one, and the memory changes its mind.
    Mem.outcome(db, rival, "conversion_up", evidence_ref="cohort:3")
    Mem.outcome(db, rival, "benchmark_confirmed", evidence_ref="scan:9")
    won = Mem.resolve(db, pod="garments", subject="stripe_demand")
    assert won["active_lesson_id"] == rival
    assert won["changed"] is True
    assert won["active_version"] == 2


def test_a_superseded_lesson_is_kept_because_a_memory_that_was_always_right_is_not_learning():
    db = _db()
    incumbent = _lesson(db)
    rival = Mem.challenge(db, incumbent,
                          statement="the demand is the colour blocking rather than the crop",
                          mechanism="colour_architecture")
    Mem.outcome(db, rival, "launch_sold", evidence_ref="ledger:2")
    Mem.resolve(db, pod="garments", subject="stripe_demand")

    report = Mem.report(db)
    assert report["lessons"] == 2
    assert report["active"] == 1
    assert report["superseded"] == 1
    assert report["challengers"] == 1


def test_a_lesson_carrying_a_competitors_instructions_is_refused_by_the_shared_boundary():
    """The pods' boundary, called rather than copied: a duplicate boundary drifts."""
    db = _db()
    try:
        Mem.learn(db, pod="garments", subject="construction",
                  statement="their written instructions say sc in each across the yoke",
                  mechanism="fit_strategy")
    except Exception as e:
        assert "competitor's instructions" in str(e)
    else:
        raise AssertionError("a competitor's instructions entered the pod memory")


# ---- coverage gaps are named, not counted (#207, #303) --------------------


def _listings(db, rows):
    from brambleloop.core.models import BenchmarkListing
    with db.session() as s:
        for i, (title, product_type) in enumerate(rows):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY,
                                   listing_ref=f"L{i}", title=title,
                                   product_type=product_type))


def test_an_unrouted_listing_is_named_rather_than_counted():
    """`unclassified: 58` tells nobody which 58, so it cannot be closed."""
    db = _db()
    _listings(db, [("Crochet Christmas Stocking", ""),
                   ("Dusty Rose Baby Set", ""),
                   ("Boot Cuffs Pattern", "")])
    report = M.gaps(db)
    assert report["routing"]["unclassified"] == 2
    named = {r["title"] for r in report["routing"]["listings"]}
    assert named == {"Dusty Rose Baby Set", "Boot Cuffs Pattern"}, named


def test_the_gap_report_surfaces_the_terms_a_widening_may_be_drawn_from():
    """The vocabulary may only grow from observed titles, so the titles have to be readable."""
    db = _db()
    _listings(db, [(f"Dusty Rose Baby Set number {i}", "") for i in range(5)])
    terms = {t["term"]: t["listings"] for t in M.gaps(db)["routing"]["frequent_terms"]}
    assert terms.get("dusty") == 5, terms
    assert "number" in terms  # noise is shown too; the judgement is not the report's to make


def test_an_attribute_absence_names_its_real_blocker_not_an_expired_one():
    """Confusing the two is how a closeable gap waits on a gate that was never its blocker.

    This asserted `silhouette`'s capability was `browser/vision`, as the contrast to
    palette's unmade call. That contrast expired: the vision capability was demonstrated,
    `intel.gallery_analysis` has been draining the backlog for days, and the column is
    filled by judged images rather than by a browser. A test holding the old words would
    have kept the coverage report pointing at a gate that had already opened -- which is
    the defect it was written to prevent, committed by the test (B-606, B-620, and now
    here).
    """
    db = _db()
    _listings(db, [("Crochet Blanket", "")])
    attrs = M.gaps(db)["attributes"]
    assert attrs["palette"]["absent_on"] == 1
    assert "credential" in attrs["palette"]["capability"]
    # Neither column waits on a capability nobody has any more.
    assert "browser" not in attrs["silhouette"]["capability"]
    assert "image_vision" in attrs["silhouette"]["capability"]
    assert attrs["silhouette"]["absent_on"] == 1, "no image of this listing was judged"


def test_the_gap_report_reads_the_key_the_scanner_writes():
    """The defect that made the map report an empty catalogue against 438 rows."""
    db = _db()
    _listings(db, [("Dusty Rose Baby Set", "")])
    assert M.gaps(db)["listings"] == 1
    assert M.gaps(db)["benchmark_key"] == benchmarks.MJS_KEY


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
