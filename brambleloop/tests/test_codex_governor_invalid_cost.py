"""Finance views do not turn invalid expenses into credits or known totals."""
from datetime import datetime, timedelta, timezone

import pytest

from brambleloop.app.command_center import company
from brambleloop.core.db import Database
from brambleloop.core.models import CostEntry
from brambleloop.finance import governor


@pytest.mark.parametrize("amount", [-5.0, float("inf")])
def test_command_center_refuses_invalid_cost_instead_of_reporting_credit(tmp_path, amount):
    db = Database(f"sqlite:///{tmp_path / 'money.db'}", scratch=True)
    db.create_all()
    with db.session() as session:
        session.add(CostEntry(agent="fixture", department="production",
                              kind="llm", amount_cad=amount))
    result = company.department_spend(db)
    assert result["ok"] is False
    assert "reconciliation required" in result["why"]
    assert company._dept_spend(result, "production")["state"] == "UNKNOWN"
    with db.session() as session:
        with pytest.raises(governor.GovernorRefused):
            governor.agent_anomalies(session)


def test_lifetime_value_does_not_sum_historical_negative_cost(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'money.db'}", scratch=True)
    db.create_all()
    with db.session() as session:
        session.add(CostEntry(agent="fixture", amount_cad=-3.0,
                              at=datetime.now(timezone.utc) - timedelta(days=90)))
        session.add(CostEntry(agent="fixture", amount_cad=2.0))
    with db.session() as session:
        assert governor.spend_by(session, "agent", days=30)["total_cad"] == 2.0
        with pytest.raises(governor.GovernorRefused, match="reconciliation required"):
            governor.marginal_value(session, days=30)


def test_governor_endpoint_reports_unavailable_without_spend_totals(tmp_path, monkeypatch):
    from brambleloop.app import main

    db = Database(f"sqlite:///{tmp_path / 'money.db'}", scratch=True)
    db.create_all()
    with db.session() as session:
        session.add(CostEntry(agent="fixture", amount_cad=-2.0))
    monkeypatch.setattr(main, "db", db)
    result = main.api_governor()
    assert result["report"]["available"] is False
    assert "reconciliation required" in result["report"]["reason"]
    assert "attribution" not in result["report"]
