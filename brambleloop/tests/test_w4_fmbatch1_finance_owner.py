"""F-620: the owner's finance view -- MTD/YTD apart, ad credit vs cash, cash/payout position,
unreconciled items and the monthly close; UNMEASURED is never zero."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1fin_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/f.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import CostEntry  # noqa: E402

TOKEN = "f" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}
os.environ[opsauth.TOKEN_VAR] = TOKEN
# JSON keys of the owner view. Quoted, so the public P&L's own `tax_reserve_cad` line (public
# since before this branch) is not mistaken for the owner's reserve obligation.
OWNER_KEYS = tuple(f'"{k}"' for k in (
    "owner_view", "cash_on_hand_cad", "cash_unreconciled_lines", "expected_payout_cad",
    "owner_payable", "tax_reserve", "runway", "safe_discretionary_budget_cad",
    "statement_lines", "unreconciled_cad", "cash_and_payout"))


def _owner():
    r = TestClient(main.app).get("/api/finance/owner", headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def test_owner_view_blocks_and_unmeasured_ads():
    v = _owner()
    assert set(v) >= {"windows", "ads", "cash_and_payout", "unreconciled", "monthly_close"}
    assert set(v["windows"]) == {"mtd", "ytd"}, v["windows"]
    assert v["ads"]["recorded_ad_spend_cad"] == "UNMEASURED"
    assert v["ads"]["free_ad_credit_granted_cad"] == "UNMEASURED"
    assert v["unreconciled"]["unreconciled"] == 0
    assert "current_period" in v["monthly_close"]


def test_ad_spend_split_into_credit_and_cash():
    from brambleloop.finance import credits

    with main.db.session() as s:
        s.add(CostEntry(agent="ads", kind="ads", amount_cad=10.0, provider="etsy_ads",
                        purpose="ads"))
    credits.grant(main.db, provider="etsy_ads", kind="ads_credit", amount=4.0, currency="CAD",
                  granted_on="2000-01-01", evidence_ref="test grant")
    ads = main._finance_owner_view()["ads"]
    assert ads["recorded_ad_spend_cad"] == 10.0
    assert ads["free_ad_credit_granted_cad"] == 4.0
    assert ads["estimated_paid_by_credit_cad"] == 4.0
    assert ads["estimated_cash_ad_spend_cad"] == 6.0



def test_f681_unreconciled_items_listed_and_totals_equal_sql():
    from sqlalchemy import func, select

    from brambleloop.finance.accounting import reconciliation
    from brambleloop.finance.accounting.models import AcctStatementLine

    reconciliation.import_statement(main.db, "bank", [
        {"external_id": "b1", "kind": "charge", "amount": -12.5, "at": "2026-10-20T00:00:00+00:00",
         "reference": "UNKNOWN-VENDOR"},
        {"external_id": "b2", "kind": "deposit", "amount": 40.0, "at": "2026-10-21T00:00:00+00:00",
         "reference": "NO-PAYOUT"}])
    v = _owner()["unreconciled"]
    with main.db.session() as s:
        n, micros = s.execute(select(func.count(), func.sum(AcctStatementLine.amount_micros))
                              .where(AcctStatementLine.state == "unmatched")).one()
    assert v["unreconciled"] == n == len(v["items"]) == 2
    assert v["unreconciled_cad"] == round(micros / 1e6, 4) == 27.5
    assert [i["external_id"] for i in v["items"]] == ["b2", "b1"]


def test_n1_public_finance_carries_no_owner_data_and_the_owner_route_needs_the_credential():
    from brambleloop.finance.accounting import reconciliation

    reconciliation.import_statement(main.db, "bank", [
        {"external_id": "n1-secret-line", "kind": "deposit", "amount": 99.0,
         "at": "2026-10-19T00:00:00+00:00", "reference": "N1"}])
    c = TestClient(main.app)
    body = c.get("/api/finance").text
    assert OWNER_KEYS, OWNER_KEYS              # INTEG7: test_vacuity non-emptiness
    for k in OWNER_KEYS + ("n1-secret-line",):
        assert k not in body, f"public /api/finance leaks {k!r}"
    assert c.get("/api/finance/owner").status_code == 401
    assert "n1-secret-line" in str(_owner())

main.db.create_all()
Registry(main.db).seed_defaults()


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
