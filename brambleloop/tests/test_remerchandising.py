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


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
