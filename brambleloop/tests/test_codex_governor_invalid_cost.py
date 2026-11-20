"""Finance views do not turn invalid expenses into credits or known totals.

Repo convention (review U7 F2): plain functions and a __main__ runner, no pytest.
Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_codex_governor_invalid_cost.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import contextlib
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.app.command_center import company  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry  # noqa: E402
from brambleloop.finance import governor  # noqa: E402


@contextlib.contextmanager
def raises(exc, match: str | None = None):
    try:
        yield
    except exc as e:  # noqa: PERF203
        if match is not None and not re.search(match, str(e)):
            raise AssertionError(f"{exc.__name__} raised, but {str(e)!r} !~ {match!r}") from e
        return
    raise AssertionError(f"{exc.__name__} was not raised")


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='gov_')}/money.db", scratch=True)
    db.create_all()
    return db


def test_command_center_refuses_invalid_cost_instead_of_reporting_credit():
    for amount in (-5.0, float("inf")):
        db = _db()
        with db.session() as session:
            session.add(CostEntry(agent="fixture", department="production",
                                  kind="llm", amount_cad=amount))
        result = company.department_spend(db)
        assert result["ok"] is False, (amount, result)
        assert "reconciliation required" in result["why"], result
        assert company._dept_spend(result, "production")["state"] == "UNKNOWN"
        with db.session() as session:
            with raises(governor.GovernorRefused):
                governor.agent_anomalies(session)


def test_lifetime_value_does_not_sum_historical_negative_cost():
    db = _db()
    with db.session() as session:
        session.add(CostEntry(agent="fixture", amount_cad=-3.0,
                              at=datetime.now(timezone.utc) - timedelta(days=90)))
        session.add(CostEntry(agent="fixture", amount_cad=2.0))
    with db.session() as session:
        assert governor.spend_by(session, "agent", days=30)["total_cad"] == 2.0
        with raises(governor.GovernorRefused, match="reconciliation required"):
            governor.marginal_value(session, days=30)


def test_governor_endpoint_reports_unavailable_without_spend_totals():
    from brambleloop.app import main

    db = _db()
    with db.session() as session:
        session.add(CostEntry(agent="fixture", amount_cad=-2.0))
    saved = main.db
    main.db = db
    try:
        result = main.api_governor()
    finally:
        main.db = saved
    assert result["report"]["available"] is False
    assert "reconciliation required" in result["report"]["reason"]
    assert "attribution" not in result["report"]


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
