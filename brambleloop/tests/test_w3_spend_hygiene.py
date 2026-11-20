"""Wave-3 lane SPEND: spend-hygiene detectors run by the governor's cadence pass.

F-308 retry storm, F-326 hourly spike + repeated identical paid request, F-305 unattributed
spend over tolerance, F-315 oversized input. Each opens an incident through
`governor.enforce` (the `finance.governor` cadence handler's call), changes no ceiling, and
says when it cannot measure. Ledger rows here are written directly; no provider is called.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_spend_hygiene.py
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from r2_autonomy_harness import boot, run_tests

NOW = datetime(2026, 10, 6, 15, 30, tzinfo=timezone.utc)


def _cost(db, *, at, amount, agent="creative_director", purpose="concept.naming@1",
          job_id=None, detail=None, tokens_in=0, product=""):
    from brambleloop.core.models import CostEntry

    with db.session() as s:
        s.add(CostEntry(at=at, agent=agent, amount_cad=amount, kind="llm", job_id=job_id,
                        purpose=purpose, detail=detail or {}, tokens_in=tokens_in,
                        product_slug=product))


def _signatures(db):
    from sqlalchemy import select

    from brambleloop.core.models import Incident

    with db.session() as s:
        return [sig for (sig,) in s.execute(select(Incident.signature))]


def test_quiet_ledger_opens_nothing_and_says_hourly_is_unmeasurable():
    from brambleloop.finance import governor

    db = boot()
    out = governor.enforce(db, now=NOW)
    h = out["hygiene"]
    assert h["hourly"]["measurable"] is False and "history" in h["hourly"]["why"], h
    assert h["incidents"] == [] and h["ceilings_changed"] == 0, h
    assert out["ceilings_changed"] == 0


def test_retry_storm_is_an_incident():
    from brambleloop.finance import governor, spend_hygiene

    db = boot()
    for i in range(spend_hygiene.RETRY_STORM_MIN_FAILED):
        _cost(db, at=NOW - timedelta(minutes=5 + i), amount=0.02,
              detail={"ok": False, "billing": "response_usage"})
    out = governor.enforce(db, now=NOW)
    assert out["hygiene"]["retry_storms"], out["hygiene"]
    assert any(s.startswith(spend_hygiene.SIGNATURES["retry_storm"]) for s in _signatures(db))


def test_hourly_spike_against_a_week_of_ordinary_hours():
    from brambleloop.finance import governor, spend_hygiene

    db = boot()
    for h in range(1, 48):
        _cost(db, at=NOW - timedelta(hours=h), amount=0.05)
    _cost(db, at=NOW - timedelta(minutes=10), amount=3.00)
    out = governor.enforce(db, now=NOW)
    hourly = out["hygiene"]["hourly"]
    assert hourly["measurable"] and hourly["spike"], hourly
    assert any(s.startswith(spend_hygiene.SIGNATURES["hourly_spike"]) for s in _signatures(db))


def test_unattributed_spend_over_tolerance_and_oversized_input():
    from brambleloop.finance import governor, spend_hygiene

    db = boot()
    _cost(db, at=NOW - timedelta(days=1), amount=5.0)
    _cost(db, at=NOW - timedelta(days=1), amount=2.0, agent="", job_id=None)
    _cost(db, at=NOW - timedelta(hours=2), amount=0.1,
          tokens_in=spend_hygiene.INPUT_TOKEN_ALLOWANCE + 1, purpose="intel.vision")
    out = governor.enforce(db, now=NOW)
    u = out["hygiene"]["unattributed"]
    assert u["over"] and u["unattributed_cad"] == 2.0, u
    assert out["hygiene"]["oversized_inputs"][0]["purpose"] == "intel.vision"
    sigs = _signatures(db)
    assert any(s.startswith(spend_hygiene.SIGNATURES["unattributed"]) for s in sigs), sigs
    assert any(s.startswith(spend_hygiene.SIGNATURES["oversized_input"]) for s in sigs), sigs


def test_identical_request_bought_by_several_jobs_is_flagged():
    from brambleloop.finance import spend_hygiene
    from brambleloop.gateway import paid_calls

    db = boot()
    paid_calls.ensure_table(db)
    with db.session() as s:
        for j in range(spend_hygiene.REPEAT_MIN_JOBS):
            s.add(paid_calls.PaidCallRecord(key=f"k{j}", effect="anthropic.vision", job_id=j,
                                            fingerprint="f" * 64, outcome=paid_calls.OK,
                                            at=NOW - timedelta(hours=1)))
    out = spend_hygiene.sweep(db, now=NOW)
    assert out["repeated_requests"] and out["repeated_requests"][0]["jobs"] == 3, out



def test_provider_billing_discrepancy_is_an_incident_only_when_current():
    from brambleloop.finance import spend_hygiene, spend_report
    from brambleloop.ops import provider_accounts

    db = boot()
    stale = spend_hygiene.provider_discrepancy(db, NOW)
    assert stale, "the reported facts are read"
    for row in stale:
        assert row["stale"] is True and row["material"] is False, row
    real = provider_accounts.REPORTED_FACTS
    provider_accounts.REPORTED_FACTS = real + (provider_accounts.AccountFact(
        "anthropic", NOW.date().isoformat(), "used", 25.0, "test fact"),)
    try:
        out = spend_hygiene.sweep(db, now=NOW)
        honesty = spend_report.governance(db, now=NOW)["honesty"]
    finally:
        provider_accounts.REPORTED_FACTS = real
    anth = [r for r in out["provider_billing"] if r["provider"] == "anthropic"][0]
    assert anth["material"] and anth["historical_unknown_usd"] == 25.0, anth
    assert any(s.startswith(spend_hygiene.SIGNATURES["provider_billing"])
               for s in _signatures(db))
    hu = [r for r in honesty["historical_unknown"] if r["provider"] == "anthropic"][0]
    assert hu["historical_unknown_usd"] == 25.0 and honesty["recorded_cad"] == 0.0, honesty


if __name__ == "__main__":
    run_tests(globals())
