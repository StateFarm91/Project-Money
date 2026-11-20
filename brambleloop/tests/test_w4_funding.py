"""W4-FUNDING (F-871 / F-100): funding asks are prepared packets read from runtime rows."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry, OwnerAction, utcnow  # noqa: E402
from brambleloop.finance import funding_packet as F  # noqa: E402
from brambleloop.gateway.anthropic import monthly_ceiling_cad  # noqa: E402
from brambleloop.ops import funding  # noqa: E402
from brambleloop.runtime.worker import PARKED_ACTION  # noqa: E402


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _seeded():
    db = _db()
    now = utcnow()
    with db.session() as s:
        for i, purpose in enumerate(("asset_truth", "asset_truth", "gallery_analysis")):
            s.add(CostEntry(agent="asset_truth", provider="anthropic", purpose=purpose,
                            amount_cad=1.5, at=now - timedelta(days=i + 1)))
        s.add(CostEntry(agent="creative_director", provider="openai", purpose="render",
                        amount_cad=0.2, at=now - timedelta(days=1)))
        for ok in (True, True, False):
            s.add(AuditLog(actor="orchestrator", action="model.probe", detail={"ok": ok},
                           at=now - timedelta(hours=2)))
        s.add(AuditLog(actor="orchestrator", action=PARKED_ACTION, detail={},
                       at=now - timedelta(hours=1)))
    return db


def test_an_empty_ledger_is_unmeasured_never_zero():
    p = F.credit_packet(_db())
    assert p["measured_run_rate_cad_per_day"] is None and "unmeasured" in p["run_rate_basis"]
    assert p["outage_evidence"]["probes"] is None and p["outage_evidence"]["why_null"]
    assert p["max_spend"]["monthly_ceiling_cad"] == float(monthly_ceiling_cad())
    assert p["approves_itself"] is False
    d = F.diversification_packet(_db())
    assert d["measured_resilience_value"] is None and d["unmeasured_because"]


def test_the_credit_packet_names_what_the_credit_buys_and_its_bound():
    p = F.credit_packet(_seeded(), "anthropic")
    assert p["measured_run_rate_cad_per_day"] == round(4.5 / F.WINDOW_DAYS, 4)
    buys = {b["purpose"]: b["cad_30d"] for b in p["bounded_experiment"]["what_the_credit_buys"]}
    assert buys == {"asset_truth": 3.0, "gallery_analysis": 1.5}
    assert p["max_spend"]["headroom_cad"] <= p["max_spend"]["monthly_ceiling_cad"]
    o = p["outage_evidence"]
    assert o["probes"] == 3 and o["failed_probes"] == 1 and o["model_jobs_parked"] == 1


def test_the_diversification_packet_carries_measured_resilience_value_and_a_bound():
    d = F.diversification_packet(_seeded())
    v = d["measured_resilience_value"]
    assert v["probe_failure_share"] == round(1 / 3, 4) and v["model_jobs_parked"] == 1
    assert "would have carried" in v["reading"]
    assert d["bounded_experiment"]["one_off"] is True
    assert d["bounded_experiment"]["max_cost_cad"] == F.DIVERSIFICATION_EXPERIMENT_CAD > 0
    assert d["approves_itself"] is False


def test_the_owner_funding_action_carries_the_prepared_packet():
    db = _seeded()
    out = funding.note(db, "Your credit balance is too low to access the Anthropic API")
    assert out["raised"] is True
    from sqlalchemy import select

    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == funding.REQUIREMENT_KEY))
        assert "Prepared packet" in row.reason and "monthly ceiling CA$" in row.reason
        assert "/day" in row.reason


def test_the_packets_route_is_registered():
    main = (ROOT / "src/brambleloop/app/main.py").read_text()
    assert '@app.get("/api/funding/packets")' in main
    out = F.packets(_seeded())
    assert [p.get("packet") for p in out["packets"]] == ["model_credit",
                                                         "provider_diversification"]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
