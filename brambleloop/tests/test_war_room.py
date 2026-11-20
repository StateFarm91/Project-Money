"""The CA$5K war room board (#276).

Orders and experiments below are synthetic fixtures. The empty-database test is the company
today: no sales, so run rate, forecast, gap, constraint and winners are UNMEASURED.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.scale import war_room as W  # noqa: E402

NOW = datetime(2027, 3, 1, tzinfo=timezone.utc)


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _orders(db, per_product: dict[str, tuple[int, float]], *, old: int = 1):
    from brambleloop.core.models import Customer, Order

    with db.session() as s:
        cust = Customer(customer_ref="fixture-buyer")
        s.add(cust)
        s.flush()
        n = 0
        for _ in range(old):
            n += 1
            s.add(Order(customer_id=cust.id, external_ref=f"o-{n}",
                        at=NOW - timedelta(days=61), product_slug="old", revenue_cad=10.0,
                        contribution_cad=5.0))
        for slug, (count, contribution) in per_product.items():
            for k in range(count):
                n += 1
                s.add(Order(customer_id=cust.id, external_ref=f"o-{n}",
                            at=NOW - timedelta(days=1 + k % 20), product_slug=slug,
                            revenue_cad=20.0, contribution_cad=contribution))


def test_an_empty_database_reports_every_absent_field_with_its_reason():
    out = W.board(_db(), now=NOW)
    b = out["board"]
    assert set(b) == {"monthly_run_rate", "forecast_30d", "gap_to_target", "primary_constraint",
                      "top_actions", "experiments_in_flight", "winner_alerts",
                      "risk_concentration", "owner_approvals"}
    for key in ("monthly_run_rate", "forecast_30d", "gap_to_target", "primary_constraint",
                "top_actions", "winner_alerts"):
        assert b[key]["status"] == W.UNMEASURED and b[key]["value"] is None, key
        assert b[key]["why"] and b[key]["needs"], key
    assert "nothing has sold" in b["monthly_run_rate"]["why"]
    assert b["experiments_in_flight"]["count"] == 0
    assert b["owner_approvals"]["status"] == W.MEASURED
    assert out["target_cad_per_month"] == 5000.0


def test_the_forecast_minimum_boundary():
    db = _db()
    _orders(db, {"a": (18, 5.0)})           # 19 orders in total
    f = W.board(db, now=NOW)["board"]["forecast_30d"]
    assert f["status"] == W.UNMEASURED and "19 order(s)" in f["why"]
    db = _db()
    _orders(db, {"a": (19, 5.0)})           # 20
    b = W.board(db, now=NOW)["board"]
    assert b["forecast_30d"]["status"] == W.MEASURED
    assert b["forecast_30d"]["value"] == 380.0 and b["forecast_30d"]["low"] == 0.0
    assert b["monthly_run_rate"]["value"] == 380.0
    assert b["gap_to_target"]["value"] == 4620.0


def test_winner_alerts_need_the_minimum_and_name_the_disproportionate_product():
    db = _db()
    _orders(db, {"a": (10, 30.0), "b": (5, 5.0), "c": (4, 5.0)})    # 19 in window
    assert W.board(db, now=NOW)["board"]["winner_alerts"]["status"] == W.UNMEASURED
    db = _db()
    _orders(db, {"a": (10, 30.0), "b": (5, 5.0), "c": (5, 5.0)})    # 20 in window
    w = W.board(db, now=NOW)["board"]["winner_alerts"]
    assert w["status"] == W.MEASURED
    assert [x["product"] for x in w["value"]] == ["a"]


def test_top_actions_rank_by_expected_contribution_and_stop_at_five():
    from brambleloop.core.models import OwnerAction, RegisteredExperiment

    db = _db()
    with db.session() as s:
        for i, ev in enumerate((10.0, 50.0, None, 30.0, 70.0, 20.0, 40.0)):
            s.add(RegisteredExperiment(key=f"e{i}", expected_value_cad=ev, owner="growth",
                                       state="registered"))
        s.add(RegisteredExperiment(key="dead", expected_value_cad=999.0, state="killed"))
        s.add(OwnerAction(action="approve a thing", requirement_key="x"))
    b = W.board(db, now=NOW)["board"]
    top = b["top_actions"]
    assert top["status"] == W.MEASURED
    assert [a["expected_incremental_contribution_cad"] for a in top["value"]] == [
        70.0, 50.0, 40.0, 30.0, 20.0]
    assert top["unvalued"] == 1
    assert b["experiments_in_flight"]["count"] == 7
    assert b["owner_approvals"]["count"] == 1


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
