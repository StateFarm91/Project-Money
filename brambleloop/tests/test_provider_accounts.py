"""A provider balance, an internal budget and a working provider are three different facts.

All three were live on 2026-09-21 and all three said something different: the monthly
ceiling had CA$55 free, the owner reported US$10 of credit added, and every call was
refused. A single combined number would have had to be wrong about two of them.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.ops import funding, provider_accounts as pa  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def test_the_three_columns_are_reported_separately():
    db = _db()
    out = pa.reconcile(db)
    assert out["internal_budget"]["source"] == pa.OBSERVED
    assert out["capability"]["source"] == pa.OBSERVED
    assert all(f["source"] == pa.REPORTED
               for p in out["provider_accounts"] for f in p["reported"])
    assert "would have had to be wrong about two of them" in out["never_merged"]
    # And there is no single "how much is left" figure, because it would have to pick one.
    assert "remaining" not in json_keys(out)


def json_keys(obj, seen=None) -> set:
    seen = seen if seen is not None else set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            seen.add(k)
            json_keys(v, seen)
    elif isinstance(obj, list):
        for item in obj:
            json_keys(item, seen)
    return seen


def test_a_reported_balance_is_never_treated_as_a_capability():
    """The owner reported US$10 added and the provider went on refusing every call. The
    report is evidence of a dashboard; the probe is evidence of a call."""
    db = _db()
    funding.note(db, "credit balance is too low")
    out = pa.reconcile(db)
    assert out["capability"]["balance_blocked"] is True
    assert out["capability"]["anthropic_probe_ok"] is False
    anthropic = next(p for p in out["provider_accounts"] if p["provider"] == "anthropic")
    assert any(f["kind"] == "credit_added" and f["amount_usd"] == 10.0
               for f in anthropic["reported"])


def test_a_balance_is_not_a_budget_and_the_code_says_so():
    assert "not authority to spend it" in pa.NOT_A_BUDGET
    assert "CA$100 monthly ceiling" in pa.NOT_A_BUDGET or "CA$100" in pa.NOT_A_BUDGET


def test_the_dashboard_figure_is_reconciled_against_our_own_ledger():
    """They can differ, and the difference is worth knowing rather than hiding: other usage
    on the account, or this system's assumed list prices being wrong."""
    from brambleloop.finance import spend_report

    db = _db()
    spend_report.record(db, agent="gateway", amount_cad=14.0, estimated_cad=14.0,
                        purpose="image.render", provider="openai", model="gpt-image-2",
                        department="creative")
    out = pa.reconcile(db)
    openai = next(p for p in out["provider_accounts"] if p["provider"] == "openai")
    assert openai["our_ledger"]["usd"] == 10.01  # 14.0 CAD at the assumed rate
    assert openai["dashboard_used_usd"] == 10.08
    assert openai["difference_usd"] == 0.07
    assert openai["organisation_limit_usd"] == 50.0
    assert "assumed list prices" in openai["our_ledger"]["price_basis"]


def test_the_openai_dashboard_figures_reconcile_with_each_other():
    """Balance plus spend-to-date is what was bought, and it comes to twenty dollars.

    Checking it is how a typo, or a second account sharing the key, shows up as arithmetic
    rather than as a surprise three weeks later.
    """
    out = pa.reconcile(_db())
    openai = next(p for p in out["provider_accounts"] if p["provider"] == "openai")
    assert openai["balance_usd"] == 9.92
    assert openai["dashboard_self_check"]["implied_credits_purchased_usd"] == 20.0
    assert openai["dashboard_self_check"]["consistent"] is True
    # The organisation limit is a cap, not the money: US$50 allowed, US$20 bought.
    assert openai["organisation_limit_usd"] == 50.0


def test_a_balance_with_auto_reload_off_is_reported_as_a_cliff():
    """Anthropic did this hours earlier: every call stops at once, and nothing inside this
    system can retry past it."""
    out = pa.reconcile(_db())
    openai = next(p for p in out["provider_accounts"] if p["provider"] == "openai")
    assert openai["auto_reload_off"] is True
    assert "stops every render at once" in openai["stops_without_warning"]
    # And the runway is arithmetic from the measured price, named as arithmetic.
    assert openai["renders_left_at_observed_price"] == 338
    assert "not a forecast" in openai["runway_basis"]


def test_the_anthropic_row_records_that_the_credit_has_not_arrived():
    """The owner reported adding it; three probes since were refused for a low balance.
    Both facts are kept, because the report is evidence of a dashboard and the probe is
    evidence of a call."""
    out = pa.reconcile(_db())
    anthropic = next(p for p in out["provider_accounts"] if p["provider"] == "anthropic")
    added = next(f for f in anthropic["reported"] if f["kind"] == "credit_added")
    assert added["amount_usd"] == 10.0
    assert "has not reached the key" in added["note"]


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
