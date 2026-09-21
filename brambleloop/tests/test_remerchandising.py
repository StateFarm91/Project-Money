"""Selling what already exists into a new season, without pretending it is a new product.

v1.4.3 requirement 292. Its closing instruction -- avoid unnecessary new product creation --
runs against the instinct: making something new is more satisfying than re-photographing
something old, and it is usually the worse trade. An existing certified pattern has already
paid for its engineering, its physical test and its gates; a seasonal colourway costs a
photograph.

The two failures held here are the ones that turn the exercise into fiction. A recolour
described as a launch inflates catalogue size, release rate and the apparent breadth of a
collection all at once. And calling an unsold product "proven" makes every subsequent number
about proven products meaningless.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.seasonal import remerchandising as R  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/remerch.sqlite")
    db.create_all()
    return db


def _product(db, slug: str, *, certified: bool = True) -> int:
    from brambleloop.core.models import PatternVersion, Product

    with db.session() as s:
        product = Product(slug=slug, title=slug.replace("-", " ").title(), status="released")
        s.add(product)
        s.flush()
        s.add(PatternVersion(product_id=product.id, version="1.0.0",
                             cir_json={"slug": slug}, certified=certified))
        return product.id


def _sale(db, slug: str) -> None:
    from brambleloop.core.models import LedgerEntry

    with db.session() as s:
        s.add(LedgerEntry(category="sale", gross_cad=9.0, evidence_ref=f"order:{slug}:1"))


# ---- proven is a claim about sales -----------------------------------------


def test_with_no_sales_nothing_is_proven_and_the_report_says_so():
    db = _db()
    _product(db, "market-basket")

    pool = R.candidates(db)

    assert pool["proven"] == []
    assert pool["proof_measurable"] is False
    assert "makes the exercise fiction" in pool["note"]
    assert pool["eligible"][0]["proven"] is False


def test_a_recorded_sale_makes_a_candidate_proven():
    db = _db()
    _product(db, "market-basket")
    _sale(db, "market-basket")

    pool = R.candidates(db)

    assert pool["proven"] == ["market-basket"]
    assert pool["proof_measurable"] is True


def test_an_uncertified_product_is_not_a_candidate_at_all():
    db = _db()
    _product(db, "half-built", certified=False)

    assert R.candidates(db)["eligible"] == []


# ---- a re-merchandising move is never a new product ------------------------


def test_a_move_that_changes_the_pattern_is_a_new_product_and_is_refused():
    try:
        R.check_move(move="colourway", changes=("construction", "rows"))
    except R.RemerchandisingRefused as e:
        assert "different pipeline" in str(e)
        assert "unengineered product in front of a buyer" in str(e)
    else:
        raise AssertionError("a new product was routed through re-merchandising")


def test_changing_presentation_is_allowed_and_counts_as_nothing_new():
    record = R.check_move(move="styled_photography",
                          changes=("photography", "listing_copy"))

    assert record["counts_as_new_product"] is False
    assert "inflates catalogue size" in record["note"]


def test_the_release_hash_is_immutable_because_it_is_what_a_buyer_downloaded():
    assert "release_hash" in R.IMMUTABLE
    try:
        R.check_move(move="bundle", changes=("release_hash",))
    except R.RemerchandisingRefused:
        pass
    else:
        raise AssertionError("a bundle was allowed to change the shipped pattern")


def test_an_invented_move_is_refused():
    try:
        R.check_move(move="rebrand", changes=())
    except R.RemerchandisingRefused as e:
        assert "not a re-merchandising move" in str(e)
    else:
        raise AssertionError("an invented move was accepted")


# ---- the plan ---------------------------------------------------------------


def test_every_move_names_what_it_is_waiting_on():
    db = _db()
    _product(db, "market-basket")

    plan = R.plan(db, event="Christmas")

    moves = plan["candidates"][0]["moves"]
    assert {m["move"] for m in moves} == set(R.MOVES)
    assert all(m["needs"] for m in moves)
    assert all(m["available"] is False for m in moves), "nothing is wired yet"


def test_an_available_capability_makes_its_move_ready():
    db = _db()
    _product(db, "market-basket")

    plan = R.plan(db, event="Christmas", available=("search_positioning",))

    assert plan["ready_moves"] == 1
    ready = [m for m in plan["candidates"][0]["moves"] if m["available"]]
    assert [m["move"] for m in ready] == ["search_positioning"]


def test_the_plan_never_reports_catalogue_growth():
    db = _db()
    _product(db, "market-basket")

    plan = R.plan(db, event="Christmas", available=tuple(R.MOVES))

    assert plan["catalogue_growth"] == 0
    assert "costs a photograph" in plan["note"]


def test_an_empty_catalogue_says_so_rather_than_proposing_moves():
    plan = R.plan(_db(), event="Christmas")

    assert plan["candidates"] == []
    assert "no certified product exists" in plan["note"]


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


# ---- availability is read, not asserted by the caller (#292) -----------------


def _lang_db(n=8):
    import tempfile

    from brambleloop.core.db import Database
    from brambleloop.core.models import BenchmarkListing
    from brambleloop.intel import benchmarks

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/cap.sqlite")
    db.create_all()
    with db.session() as s:
        for i in range(n):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=str(i),
                                   title="Cozy Rustic Crochet Christmas Stocking, Easy",
                                   pod="stockings"))
    return db


def test_search_positioning_is_available_because_the_language_map_is_readable():
    """It became possible on 2026-09-20 -- the credential made a department's observed
    titles countable -- and `plan()` previously took the answer from its caller."""
    from brambleloop.seasonal import remerchandising

    state = remerchandising.capabilities(_lang_db(), pod="stockings")
    assert "search_positioning" in state["available"]
    assert state["moves"]["search_positioning"]["available"] is True


def test_a_pod_with_no_readable_language_does_not_claim_the_move():
    from brambleloop.seasonal import remerchandising

    state = remerchandising.capabilities(_lang_db(), pod="education")
    assert "search_positioning" not in state["available"]
    assert "buyer-language map" in state["blocked"]["search_positioning"]


def test_the_image_moves_read_a_recorded_generation_rather_than_a_variable():
    """The defect this check exists to catch, found live on 2026-09-21.

    Both image moves were gated on `BRAMBLELOOP_IMAGE_KEY` -- a variable that stopped
    existing when credentials moved to one key per provider account. So a capability that
    had been rendering in production for a day read as absent here, and two requirements
    stayed parked on it. The familiar defect with an extra turn of the screw: the
    configuration the gate read had been renamed out from under it, so the condition could
    no longer come true at all.
    """
    from brambleloop.gateway import images
    from brambleloop.seasonal import remerchandising

    db = _lang_db()
    state = remerchandising.capabilities(db, pod="stockings")
    assert "colourway" in state["blocked"] and "styled_photography" in state["blocked"]
    assert "image-generation" in state["blocked"]["styled_photography"]

    original = images.usable
    images.usable = lambda _db: True
    try:
        opened = remerchandising.capabilities(db, pod="stockings")
    finally:
        images.usable = original
    assert "colourway" in opened["available"]
    assert "styled_photography" in opened["available"]
    assert "recorded successful image generation" in \
        opened["moves"]["colourway"]["evidence"]

    # And the module reads no environment variable for this any more -- parsed rather than
    # grepped, because the comment recording the defect contains the string that describes
    # it, and a check that cannot tell a call from a sentence about a call reports the
    # thing it exists to detect.
    import ast

    tree = ast.parse((ROOT / "src/brambleloop/seasonal/remerchandising.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("environ", "getenv"):
            raise AssertionError("the capability is read from the environment again")


def test_a_bundle_of_one_product_is_a_product():
    """Two certified products is the floor, and it is a count rather than a judgement."""
    from brambleloop.seasonal import remerchandising

    state = remerchandising.capabilities(_lang_db(), pod="stockings")
    assert state["moves"]["bundle"]["certified_products"] == 0
    assert "bundle" not in state["available"]


def test_a_review_computes_its_own_capabilities():
    """A review that took its capability list as an argument was only as honest as its
    caller -- the same shape as a gate reading a variable instead of a recorded success."""
    from brambleloop.seasonal import remerchandising

    report = remerchandising.review(_lang_db(), event="Christmas", pod="stockings")
    assert report["capabilities"]["available"] == ("search_positioning",)
    assert report["catalogue_growth"] == 0


# ---- a bundle opportunity is a pair, not a checkbox (#292) -------------------


def _certified_db(rows):
    import tempfile

    from brambleloop.core.db import Database
    from brambleloop.core.models import PatternVersion, Product

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/pairs.sqlite")
    db.create_all()
    with db.session() as s:
        for i, slug in enumerate(rows, start=1):
            s.add(Product(id=i, slug=slug, title=slug))
            s.add(PatternVersion(product_id=i, version="1.0", certified=True, cir_json={}))
    return db


def test_a_product_is_never_bundled_with_itself_in_another_colour():
    """The catalogue-inflation move this module exists to refuse, wearing a bundle label."""
    from brambleloop.seasonal import remerchandising

    try:
        remerchandising.pair_reason("coaster", "coaster")
    except remerchandising.PairRefused as e:
        assert "one product offered twice" in str(e)
    else:
        raise AssertionError("a product was bundled with itself")


def test_a_pair_with_no_stated_reason_is_refused():
    """"Both exist" is not a reason, and a bundle built on it is a discount."""
    from brambleloop.seasonal import remerchandising

    try:
        remerchandising.pair_reason("coaster", "stocking")
    except remerchandising.PairRefused as e:
        assert "is not a reason" in str(e)
    else:
        raise AssertionError("a bundle was proposed with no logic")


def test_every_proposed_pair_says_why_a_buyer_wants_both():
    from brambleloop.seasonal import remerchandising

    db = _certified_db(["throw", "mat", "orn", "gar"])
    forms = {"throw": "rectangle_throw", "mat": "coaster", "orn": "ornament",
             "gar": "garland"}
    lanes = {"throw": "LONG", "mat": "QUICK", "orn": "QUICK", "gar": "SHORT"}
    report = remerchandising.bundle_pairs(db, forms=forms, lanes=lanes)
    assert report["pairs"], "no pair was proposed from four complementary products"
    assert all(p["why"] for p in report["pairs"])
    assert report["catalogue_growth"] == 0


def test_the_add_on_is_the_faster_half():
    """A small make beside a longer one is an easy yes; the other way round is a bigger
    commitment wearing a smaller label."""
    from brambleloop.seasonal import remerchandising

    db = _certified_db(["throw", "mat"])
    report = remerchandising.bundle_pairs(
        db, forms={"throw": "rectangle_throw", "mat": "coaster"},
        lanes={"throw": "LONG", "mat": "QUICK"})
    assert report["pairs"][0]["add_on"] == "mat"


def test_a_product_whose_form_is_unknown_is_never_paired_on_a_guess():
    from brambleloop.seasonal import remerchandising

    db = _certified_db(["throw", "mystery"])
    report = remerchandising.bundle_pairs(db, forms={"throw": "rectangle_throw"},
                                          lanes={"throw": "LONG"})
    assert report["unpairable"] == ["mystery"]
    assert report["pairs"] == []


def test_proven_stays_false_until_both_halves_have_sold():
    from brambleloop.seasonal import remerchandising

    db = _certified_db(["throw", "mat"])
    report = remerchandising.bundle_pairs(
        db, forms={"throw": "rectangle_throw", "mat": "coaster"},
        lanes={"throw": "LONG", "mat": "QUICK"})
    assert report["pairs"][0]["proven"] is False
    assert report["proof_measurable"] is False


def test_a_catalogue_with_no_complements_says_that_about_itself():
    """A statement about how narrow the catalogue is, rather than about bundling."""
    from brambleloop.seasonal import remerchandising

    db = _certified_db(["a", "b"])
    report = remerchandising.bundle_pairs(db, forms={"a": "coaster", "b": "stocking"},
                                          lanes={"a": "QUICK", "b": "SHORT"})
    assert report["pairs"] == []
    assert "how narrow this catalogue is" in report["note"]


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
