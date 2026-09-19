"""Events against departments, and the empty cell somebody points at in a meeting.

v1.4.3 requirement 299. Half of this matrix already existed -- the calendar knows which
departments an occasion spans and which this catalogue answers. The benchmark's half was
missing because nothing had ever observed a competitor's catalogue, which changed when the
credential was verified and 438 listings were read.

The discipline worth testing is narrow and important: an unobserved market and a market with
nothing in it render identically in a matrix, both as an empty cell, and the empty cell is
the one somebody points at. So a department is only "proven and unserved" when somebody
actually looked.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.seasonal import benchmark_matrix as M  # noqa: E402

TODAY = date(2026, 9, 19)


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/matrix.sqlite")
    db.create_all()
    return db


def _observe(db, pod: str, n: int) -> None:
    """Write listings exactly as the scanner writes them, under the scanner's own key."""
    from brambleloop.core.models import BenchmarkListing
    from brambleloop.intel import benchmarks

    with db.session() as s:
        for i in range(n):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY,
                                   listing_ref=f"{pod}-{i}",
                                   pod=pod, product_type=pod, title=f"{pod} {i}"))


def _cell(report: dict, event: str, department: str) -> dict:
    row = next(r for r in report["rows"] if r["event"] == event)
    return next(c for c in row["cells"] if c["department"] == department)


# ---- the discipline --------------------------------------------------------


def test_an_unobserved_benchmark_cell_is_unknown_rather_than_empty():
    report = M.matrix(_db(), today=TODAY)

    cell = _cell(report, "Christmas", "stockings")
    assert cell["benchmark_listings"] is None
    assert cell["benchmark_basis"] == M.UNOBSERVED
    assert cell["proven_and_unserved"] is False
    assert cell["unknown_whether_proven"] is True
    assert "the empty cell is the one somebody points at" in report["note"]


def test_nothing_is_proven_and_unserved_until_somebody_looked():
    report = M.matrix(_db(), today=TODAY)
    assert report["proven_and_unserved"] == []


def test_an_observed_department_we_do_not_answer_is_the_row_this_exists_for():
    db = _db()
    _observe(db, "stockings", 13)

    report = M.matrix(db, today=TODAY)

    cell = _cell(report, "Christmas", "stockings")
    assert cell["benchmark_listings"] == 13
    assert cell["brambleloop"] == "absent"
    assert cell["proven_and_unserved"] is True
    assert {"event": "Christmas", "department": "stockings"}.items() <= \
        report["proven_and_unserved"][0].items()


def test_a_department_we_already_cover_is_not_a_gap():
    db = _db()
    _observe(db, "stockings", 13)

    report = M.matrix(db, today=TODAY, covered={"Christmas": ("stockings",)})

    cell = _cell(report, "Christmas", "stockings")
    assert cell["brambleloop"] == "covered"
    assert cell["proven_and_unserved"] is False


def test_a_department_neither_of_us_sells_is_not_a_proven_market():
    """Both render as an empty cell and only one of them is an opportunity."""
    db = _db()
    _observe(db, "stockings", 13)

    report = M.matrix(db, today=TODAY)

    cell = _cell(report, "Christmas", "hats")
    assert cell["benchmark_listings"] == 0
    assert cell["proven_and_unserved"] is False
    assert cell["unknown_whether_proven"] is False


# ---- ordering --------------------------------------------------------------


def test_gaps_are_ordered_by_how_much_they_sell_and_how_soon_the_occasion_is():
    db = _db()
    _observe(db, "stockings", 13)
    _observe(db, "hats", 82)

    gaps = M.matrix(db, today=TODAY)["proven_and_unserved"]

    christmas = [g for g in gaps if g["event"] == "Christmas"]
    assert christmas[0]["department"] == "hats"
    assert christmas[0]["benchmark_listings"] == 82


def test_cells_lead_with_where_the_benchmark_is_deepest():
    db = _db()
    _observe(db, "hats", 82)
    _observe(db, "ornaments", 13)

    row = next(r for r in M.matrix(db, today=TODAY)["rows"] if r["event"] == "Christmas")

    assert row["cells"][0]["department"] == "hats"


def test_the_depth_this_company_already_measures_is_carried_through():
    report = M.matrix(_db(), today=TODAY)
    assert all("depth" in row and "days_away" in row for row in report["rows"])


def test_the_observed_count_is_reported_so_the_matrix_can_be_argued_with():
    db = _db()
    _observe(db, "hats", 5)

    assert M.matrix(db, today=TODAY)["benchmark_observed_listings"] == 5


def test_the_reader_defaults_to_the_key_the_scanner_actually_writes():
    """Found in production: the matrix reported zero observed listings against a database
    holding 438, because it defaulted to "mjs" while the scanner wrote
    "mjs_off_the_hook_designs". A wrong key does not fail -- it returns an empty result
    indistinguishable from the truth, and this module's entire job is to tell those apart.

    The same defect was in the living market map, which had been reporting "no benchmark
    listing has been observed" since the scan succeeded.
    """
    import inspect

    from brambleloop.intel import benchmarks, market_map

    db = _db()
    _observe(db, "hats", 3)

    assert M.benchmark_depth(db)["observed"] == 3
    assert M.matrix(db, today=TODAY)["benchmark_observed_listings"] == 3
    assert market_map.build(db)["mapped"] is True

    # And no reader may carry a literal key of its own: the constant is the contract.
    for module in (M, market_map):
        source = inspect.getsource(module)
        assert 'benchmark_key: str = "mjs"' not in source, module.__name__
    assert benchmarks.MJS_KEY != "mjs"


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
