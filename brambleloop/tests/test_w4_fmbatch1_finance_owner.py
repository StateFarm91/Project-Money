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
from brambleloop.core.models import CostEntry  # noqa: E402

main.db.create_all()
Registry(main.db).seed_defaults()


def test_owner_view_blocks_and_unmeasured_ads():
    v = TestClient(main.app).get("/api/finance").json()["owner_view"]
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


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
