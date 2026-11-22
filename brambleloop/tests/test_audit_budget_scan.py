"""Audit F-06: the monthly spend read is bounded in SQL, and says exactly what it said before.

`gateway.anthropic.spent_this_month_cad` runs on every budget decision and every paid-call
authorisation, inside the process-wide and Postgres advisory budget lock. It loaded every
ledger row ever written and filtered the month in Python, so the lock was held for a time
that grew with the lifetime ledger. These tests pin two things:

  * the statement it issues carries a date bound on `cost_entries.at`;
  * its result -- the total, or the exact refusal -- equals the old implementation's, copied
    below verbatim as the oracle, across month boundaries, naive and offset timestamps,
    separately-governed kinds and invalid amounts in and out of the month.
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import event, select, text  # noqa: E402
from sqlalchemy.schema import CreateTable  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.gateway import routing  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


def _oracle(db, *, now=None):
    """The pre-F-06 implementation, verbatim apart from the names it imports."""
    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        rows = list(s.scalars(select(CostEntry).where(routing.ceiling_kind_filter())))
    total = 0.0
    for row in rows:
        at = row.at if row.at.tzinfo else row.at.replace(tzinfo=timezone.utc)
        if (at.year, at.month) == (now.year, now.month):
            try:
                amount = float(row.amount_cad)
            except (TypeError, ValueError, OverflowError):
                raise gw.BudgetExceeded("company cost ledger has an invalid amount; reconciliation required") from None
            if not math.isfinite(amount) or amount < 0:
                raise gw.BudgetExceeded("company cost ledger has an invalid or negative amount; reconciliation required")
            total += amount
    return round(total, 6)


def _outcome(fn, db, now):
    try:
        return ("ok", fn(db, now=now))
    except Exception as e:  # noqa: BLE001
        return ("raise", type(e).__name__, str(e))


def _db(entries, *, relaxed=False):
    """`relaxed` pre-creates `cost_entries` without its NOT NULL constraints, standing in for
    a legacy or hand-repaired table, so NULL kind / at / amount rows can be seeded."""
    db = Database("sqlite://")
    if relaxed:
        ddl = str(CreateTable(CostEntry.__table__).compile(db.engine)).replace(" NOT NULL", "")
        with db.engine.begin() as c:
            c.exec_driver_sql(ddl)
    db.create_all()
    with db.session() as s:
        for at, kind, amount in entries:
            s.add(CostEntry(agent="a", at=at, kind=kind, amount_cad=amount))
    return db


def _history(months=24, per_month=40):
    """Many governed rows in past months: the lifetime ledger the old read scanned."""
    out = []
    for m in range(1, months + 1):
        base = datetime(2026, 11, 1, tzinfo=UTC) - timedelta(days=31 * m)
        for i in range(per_month):
            out.append((base + timedelta(hours=i), "llm", 0.25))
    return out


def _agree(db, nows):
    for now in nows:
        new, old = _outcome(gw.spent_this_month_cad, db, now), _outcome(_oracle, db, now)
        assert new == old, (now, new, old)


NOWS = [NOW,
        datetime(2026, 11, 1, 0, 0, tzinfo=UTC),            # first instant of the month
        datetime(2026, 11, 30, 23, 59, 59, 999999, tzinfo=UTC),
        datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC),     # previous month, last second
        datetime(2026, 12, 1, 0, 0, tzinfo=UTC),            # next month, first instant
        datetime(2026, 12, 31, 23, 0, tzinfo=UTC),          # year rollover of next_month
        datetime(2026, 11, 1, 0, 0),                        # naive now
        datetime(2026, 11, 1, 3, 0, tzinfo=timezone(timedelta(hours=5))),   # offset now
        datetime(2026, 10, 31, 22, 0, tzinfo=timezone(timedelta(hours=-5)))]


def _boundary_rows():
    plus5, minus5 = timezone(timedelta(hours=5)), timezone(timedelta(hours=-5))
    return [
        (datetime(2026, 11, 1, 0, 0, 0, tzinfo=UTC), "llm", 1.0),            # exactly the 1st
        (datetime(2026, 10, 31, 23, 59, 59, 999999, tzinfo=UTC), "llm", 2.0),
        (datetime(2026, 12, 1, 0, 0, 0, tzinfo=UTC), "llm", 4.0),            # next month
        (datetime(2026, 11, 30, 23, 59, 59, tzinfo=UTC), "image", 8.0),
        (datetime(2026, 11, 15, 9, 0), "vision", 16.0),                     # naive
        (datetime(2026, 11, 1, 2, 0, tzinfo=plus5), "llm", 32.0),           # offset, 1st
        (datetime(2026, 10, 31, 21, 0, tzinfo=minus5), "llm", 64.0),        # offset, 31st
        (datetime(2026, 11, 10, tzinfo=UTC), "hosting", 128.0),             # separately governed
        (datetime(2026, 11, 10, tzinfo=UTC), "etsy_listing_fee", 256.0),    # separately governed
        (datetime(2026, 11, 10, tzinfo=UTC), "software", 512.0),
        (datetime(2026, 12, 31, 23, 0, tzinfo=UTC), "llm", 1024.0),
        (datetime(2027, 1, 1, 0, 0, tzinfo=UTC), "llm", 2048.0),
        (datetime(2026, 11, 20, 0, 0, tzinfo=UTC), "llm", 0.1),
        (datetime(2026, 11, 20, 0, 0, tzinfo=UTC), "llm", 0.2),
    ]


def test_the_read_carries_a_date_bound():
    db = _db(_history() + _boundary_rows())
    seen = []

    @event.listens_for(db.engine, "before_cursor_execute")
    def _capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        if "cost_entries" in statement:
            seen.append(statement)

    gw.spent_this_month_cad(db, now=NOW)
    event.remove(db.engine, "before_cursor_execute", _capture)
    assert seen, "no ledger read issued"
    for statement in seen:
        flat = " ".join(statement.split())
        assert "cost_entries.at >=" in flat and "cost_entries.at <" in flat, flat


def test_fetched_rows_are_bounded_by_the_month_not_the_ledger():
    history = _history()
    db = _db(history + _boundary_rows())
    fetched = []

    @event.listens_for(db.engine, "after_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        if "cost_entries" in statement:
            fetched.append((statement, parameters))

    gw.spent_this_month_cad(db, now=NOW)
    event.remove(db.engine, "after_cursor_execute", _count)
    with db.engine.connect() as c:
        statement, parameters = fetched[-1]
        n = len(c.exec_driver_sql(statement, parameters).fetchall())
        total = c.execute(text("select count(*) from cost_entries")).scalar()
    assert total >= len(history) and n <= len(_boundary_rows()), (n, total)


def test_totals_equal_the_old_implementation_across_boundaries():
    db = _db(_history() + _boundary_rows())
    _agree(db, NOWS)
    assert gw.spent_this_month_cad(db, now=NOW) == _oracle(db, now=NOW) > 0


def test_null_kind_rows_still_count():
    db = _db(_boundary_rows(), relaxed=True)
    with db.engine.begin() as c:
        c.execute(text("insert into cost_entries (at, agent, kind, amount_cad) "
                       "values ('2026-11-05 10:00:00.000000', 'a', NULL, 3.5)"))
    without = _oracle(_db(_boundary_rows()), now=NOW)
    assert gw.spent_this_month_cad(db, now=NOW) == _oracle(db, now=NOW) == round(without + 3.5, 6)
    _agree(db, NOWS)


def test_invalid_amount_this_month_refuses_exactly_as_before():
    for bad in (float("nan"), float("inf"), -0.01):
        db = _db(_history() + _boundary_rows() + [(datetime(2026, 11, 3, tzinfo=UTC), "llm", bad)],
                 relaxed=True)
        new, old = _outcome(gw.spent_this_month_cad, db, NOW), _outcome(_oracle, db, NOW)
        assert new == old and new[0] == "raise" and new[1] == "BudgetExceeded", (bad, new, old)
        _agree(db, NOWS)
    db = _db(_boundary_rows(), relaxed=True)
    with db.engine.begin() as c:
        c.execute(text("insert into cost_entries (at, agent, kind, amount_cad) "
                       "values ('2026-11-05 10:00:00.000000', 'a', 'llm', 'not-a-number')"))
    new, old = _outcome(gw.spent_this_month_cad, db, NOW), _outcome(_oracle, db, NOW)
    assert new == old and new[0] == "raise", (new, old)


def test_invalid_amount_in_a_past_month_does_not_refuse_as_before():
    db = _db(_history() + _boundary_rows()
             + [(datetime(2025, 3, 3, tzinfo=UTC), "llm", float("nan")),
                (datetime(2026, 9, 3, tzinfo=UTC), "llm", -5.0),
                (datetime(2026, 8, 3, tzinfo=UTC), "llm", float("inf"))], relaxed=True)
    old = _outcome(_oracle, db, NOW)
    assert old[0] == "ok", old            # today's behaviour, confirmed against the oracle
    assert _outcome(gw.spent_this_month_cad, db, NOW) == old
    # and an invalid amount just outside the month, inside the SQL margin, is still ignored
    db = _db(_boundary_rows() + [(datetime(2026, 10, 31, 12, tzinfo=UTC), "llm", -1.0)])
    assert _outcome(gw.spent_this_month_cad, db, NOW) == _outcome(_oracle, db, NOW)
    assert _outcome(_oracle, db, NOW)[0] == "ok"


def test_invalid_amount_in_a_separately_governed_kind_is_ignored_as_before():
    db = _db(_boundary_rows() + [(datetime(2026, 11, 3, tzinfo=UTC), "hosting", float("nan"))],
             relaxed=True)
    assert _outcome(gw.spent_this_month_cad, db, NOW) == _outcome(_oracle, db, NOW)
    assert _outcome(_oracle, db, NOW)[0] == "ok"


def test_null_at_still_fails_as_before():
    """A NULL `at` cannot be placed in any month; the old read fetched it and failed on
    `.tzinfo`. The bounded read must fetch it too (`OR at IS NULL`), not drop it silently."""
    db = _db(_boundary_rows(), relaxed=True)
    with db.engine.begin() as c:
        c.execute(text("insert into cost_entries (at, agent, kind, amount_cad) "
                       "values (NULL, 'a', 'llm', 1.0)"))
    new, old = _outcome(gw.spent_this_month_cad, db, NOW), _outcome(_oracle, db, NOW)
    assert new == old and new[0] == "raise", (new, old)


def test_empty_ledger():
    db = _db([])
    assert gw.spent_this_month_cad(db, now=NOW) == _oracle(db, now=NOW) == 0.0


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
