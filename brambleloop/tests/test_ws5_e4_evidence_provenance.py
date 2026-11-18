"""WS5 E4: one provenance flag (real | synthetic) on every learnable evidence row.

Every learner (`improve.commercial_lessons`, `creative.outcome_learning`,
`creative.style_learning`) reads only rows marked `real`. A synthetic row, or a row with no
provenance, changes nothing. In production only the owner-export intake marks `real`, and
only for a row it wrote AND read back unchanged.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws5_e4_evidence_provenance.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from brambleloop.commerce import evidence_provenance as EP  # noqa: E402
from brambleloop.commerce import listing_outcomes as LO  # noqa: E402
from brambleloop.core.models import ListingOutcome  # noqa: E402
from brambleloop.creative import style_learning as SL  # noqa: E402
from brambleloop.improve import commercial_lessons as CL  # noqa: E402
import test_opus2_commercial_lessons as TCL  # noqa: E402
import test_style_learning as TSL  # noqa: E402


def test_the_flag_is_real_or_synthetic_and_only_real_is_learnable():
    assert EP.learnable({"provenance": "real"}) is True
    for d in ({"provenance": "synthetic"}, {}, None, {"provenance": "REAL"},
              {"provenance": "maybe"}, "real"):
        assert EP.learnable(d) is False, d
    assert EP.of({"provenance": "synthetic"}) == "synthetic"
    assert EP.mark({"a": 1}, "real") == {"a": 1, "provenance": "real"}
    try:
        EP.mark({}, "unknown")
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown provenance was accepted")


def test_commercial_lessons_learn_nothing_from_synthetic_or_unmarked_rows():
    for provenance in ("synthetic", None):
        db = TCL._db()
        for slug, visits, orders in (("market-basket-small", 400, 20),
                                     ("hexagon-coaster-set", 400, 4),
                                     ("cloudline-baby-blanket", 600, 2)):
            TCL._outcome(db, slug, visits, orders, provenance=provenance)
        v = CL.verdicts(db)
        assert v["measurable"] is False and not v["categories"], (provenance, v)
    # The same rows marked real are measurement (control).
    db = TCL._db()
    TCL._three_categories(db)
    assert CL.verdicts(db)["measurable"] is True


def test_style_learning_reads_only_real_rows():
    db = TSL._db() if hasattr(TSL, "_db") else None
    assert db is not None
    TSL._outcome(db, "synthetic-one", 1000, 100, provenance="synthetic")
    TSL._outcome(db, "unmarked-one", 1000, 100, provenance=None)
    rows, _memory = SL._rows(db)
    assert rows == [], rows
    TSL._outcome(db, "real-one", 1000, 100)
    rows, _memory = SL._rows(db)
    assert [r["slug"] for r in rows] == ["real-one"], rows


def test_outcome_learning_reads_only_real_rows():
    import test_outcome_learning as TOL

    from brambleloop.creative import outcome_learning as OL

    src = __import__("inspect").getsource(OL.outcomes_by_concept)
    assert "ep.learnable(o.detail)" in src
    db = TCL._db()
    with db.session() as s:
        for slug, prov in (("market-basket-small", "synthetic"),
                           ("hexagon-coaster-set", None)):
            s.add(ListingOutcome(product_slug=slug, period_start="2027-01-01",
                                 period_end="2027-01-31", impressions=1000, visits=100,
                                 favourites=5, source="fixture",
                                 detail={"provenance": prov} if prov else {}))
    rows = OL.outcomes_by_concept(db)
    assert all(r["outcome_periods"] == 0 for r in rows), [
        (r["concept"], r["outcome_periods"]) for r in rows if r["outcome_periods"]]
    assert TOL is not None


def test_the_intake_marks_real_only_after_a_matching_round_trip():
    import test_k3_listing_outcomes as TK

    db = TK._db()
    TK._listing(db, "coaster-a", etsy_id="7001")
    csv_text = "listing id,impressions,visits,favourites,orders\n7001,900,30,4,1\n"
    LO.submit_export(db, csv_text, period_start=TK.P_START, period_end=TK.P_END)
    LO.drain_exports(db)
    with db.session() as s:
        row = s.scalar(select(ListingOutcome).where(ListingOutcome.product_slug == "coaster-a"))
        assert EP.of(row.detail) == "real", row.detail
    # A row written but not read back unchanged is not marked real.
    db = TK._db()
    TK._listing(db, "coaster-a", etsy_id="7001")
    LO.submit_export(db, csv_text, period_start=TK.P_START, period_end=TK.P_END)
    real = SL.record_outcome

    def tampering(db_, **kw):
        out = real(db_, **{**kw, "visits": kw["visits"] + 1,
                           "impressions": kw["impressions"] + 1})
        return out

    SL.record_outcome = tampering
    try:
        LO.drain_exports(db)
    finally:
        SL.record_outcome = real
    with db.session() as s:
        row = s.scalar(select(ListingOutcome).where(ListingOutcome.product_slug == "coaster-a"))
        assert row is not None and EP.of(row.detail) is None, row.detail


def test_record_outcome_sets_provenance_only_when_told():
    db = TSL._db()
    TSL._outcome(db, "a-slug", 100, 10, provenance=None)
    with db.session() as s:
        row = s.scalar(select(ListingOutcome).where(ListingOutcome.product_slug == "a-slug"))
        assert EP.of(row.detail) is None
    try:
        TSL._outcome(db, "b-slug", 100, 10, provenance="made-up")
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown provenance was stored")


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
