"""W4-FMBATCH1 batch P: provider dependency (F-092, F-093, F-094, F-095, F-099).

- F-092 "Measure provider concentration by calls, spend, critical workflows and requirements
  lost during outage."
- F-093 "A single provider carrying all load-bearing judgement work is explicitly an
  existential dependency until tested fallback exists."
- F-094 "Do not add a second paid provider for symmetry; trigger diversification when outage,
  price/terms, volume, revenue dependence or downtime cost justifies it."
- F-095 "Define required structured output, vision, context, quality, latency and cost before a
  fallback can satisfy a gate."
- F-099 "Version provider pricing/model availability and re-run routing economics on material
  change."
No provider is called; no money moves.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="fmb1_prov_")

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry, Incident, LedgerEntry  # noqa: E402
from brambleloop.gateway import anthropic, fallback_contract as FC, provider_watch as PW  # noqa: E402
from brambleloop.scale import dependency as D  # noqa: E402

NOW = datetime.now(timezone.utc)
_n = [0]


def _db():
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    return db


def _cost(db, provider, amount, kind="llm", purpose="gallery_observation", n=1):
    with db.session() as s:
        for _ in range(n):
            s.add(CostEntry(agent="a", amount_cad=amount, provider=provider, kind=kind,
                            purpose=purpose, at=NOW - timedelta(days=1)))


def _axis(rep, key):
    return next(a for a in rep["axes"] if a["axis"] == key)


# ---- F-092 -------------------------------------------------------------------------------

def test_f092_the_register_splits_workloads_and_counts_calls_spend_and_what_stops():
    db = _db()
    _cost(db, "anthropic", 1.0, purpose="gallery_observation", n=3)
    _cost(db, "anthropic", 5.0, purpose="asset_inspection", n=1)
    _cost(db, "bfl", 2.0, kind="image", purpose="owned_photography", n=4)
    reg = D.register(db)
    rows = {(r["provider"], r["workload"]): r for r in reg["providers"]}
    a = rows[("anthropic", "judgement_vision")]
    assert a["calls"] == 4 and a["spend_cad"] == 8.0
    assert a["critical_workflows"] == ["asset_inspection", "gallery_observation"]
    b = rows[("bfl", "image_generation")]
    assert b["calls"] == 4 and b["spend_share"] == 1.0
    lost = reg["requirements_lost_if_down"]
    assert lost["judgement_vision"] and isinstance(lost["judgement_vision"], list)
    # The axis no longer mixes image providers into judgement.
    rep = D.report(db)
    assert _axis(rep, "ai_provider")["holders"] == 1
    assert _axis(rep, "image_generation")["largest"] == "bfl"
    assert D.register(_db())["measured"] is False


# ---- F-093 -------------------------------------------------------------------------------

def test_f093_a_second_billed_provider_is_still_existential_without_a_tested_fallback():
    db = _db()
    _cost(db, "anthropic", 5.0)
    _cost(db, "mistral", 5.0)
    _cost(db, "bfl", 50.0, kind="image")              # an image provider never counts
    ai = _axis(D.report(db), "ai_provider")
    assert ai["verdict"] == D.EXISTENTIAL and ai.get("untested_fallback") is True, ai
    assert "no fallback drill" in ai["why"]
    with db.session() as s:
        s.add(AuditLog(actor="ops", action=D.FALLBACK_DRILL_ACTION, at=NOW - timedelta(days=40),
                       detail={"passed": True, "workload": "judgement_vision"}))
    assert _axis(D.report(db), "ai_provider")["verdict"] == D.EXISTENTIAL   # too old
    with db.session() as s:
        s.add(AuditLog(actor="ops", action=D.FALLBACK_DRILL_ACTION, at=NOW - timedelta(days=2),
                       detail={"passed": False, "workload": "judgement_vision"}))
    assert _axis(D.report(db), "ai_provider")["verdict"] == D.EXISTENTIAL   # failed
    with db.session() as s:
        s.add(AuditLog(actor="ops", action=D.FALLBACK_DRILL_ACTION, at=NOW - timedelta(days=1),
                       detail={"passed": True, "workload": "judgement_vision"}))
    assert _axis(D.report(db), "ai_provider")["verdict"] == D.SOUND


# ---- F-094 -------------------------------------------------------------------------------

def test_f094_symmetry_alone_never_triggers_and_measured_reasons_do():
    db = _db()
    _cost(db, "anthropic", 0.5)
    quiet = D.diversification_trigger(db)
    assert quiet["triggered"] is False and quiet["reasons"] == []
    assert any("revenue" in u for u in quiet["unmeasured"])
    with db.session() as s:
        for k in range(10):
            s.add(AuditLog(actor="x", action="model.probe", at=NOW - timedelta(hours=k + 1),
                           detail={"ok": k >= 5}))
        s.add(AuditLog(actor="x", action="gateway.provider_change", at=NOW - timedelta(days=2),
                       detail={}))
        s.add(LedgerEntry(category="sale", gross_cad=12.0))
    out = D.diversification_trigger(db)
    kinds = {r["kind"] for r in out["reasons"]}
    assert {"outage", "price_or_terms", "revenue_dependence"} <= kinds, out
    from brambleloop.finance.funding_packet import diversification_packet

    assert diversification_packet(db)["trigger"]["triggered"] is True


# ---- F-095 -------------------------------------------------------------------------------

def test_f095_the_contract_names_every_dimension_and_unknown_is_not_pass():
    db = _db()
    c = FC.contract_for("listing_classify")
    for k in ("structured_output", "vision", "min_context_tokens", "min_eval_pass_rate",
              "max_p95_latency_s", "max_cad_per_call"):
        assert k in c, k
    other = FC.evaluate(db, provider="mistral", model="mistral-large", task_key="listing_classify")
    assert other["verdict"] == FC.UNKNOWN
    assert FC.may_route(db, provider="mistral", primary_provider="anthropic",
                        model="mistral-large", task_key="listing_classify")["allowed"] is False
    model = "claude-sonnet-5"
    tier = c["tier"]
    FC.record_eval(db, provider="anthropic", model=model, tier=tier, passed=19, total=20,
                   source="gateway/evals golden tasks")
    FC.record_latency(db, provider="anthropic", model=model, tier=tier, p95_s=4.0, samples=50)
    ok = FC.evaluate(db, provider="anthropic", model=model, task_key="listing_classify")
    assert ok["verdict"] == FC.PASS, ok["checks"]
    FC.record_eval(db, provider="anthropic", model=model, tier=tier, passed=10, total=20,
                   source="a later run")
    bad = FC.evaluate(db, provider="anthropic", model=model, task_key="listing_classify")
    assert bad["verdict"] == FC.FAIL and bad["checks"]["quality"]["verdict"] == FC.FAIL
    assert FC.may_route(db, provider="anthropic", primary_provider="anthropic", model=model,
                        task_key="listing_classify")["allowed"] is False


def test_f095_failover_never_routes_a_fallback_that_fails_its_contract():
    from brambleloop.gateway import failover

    db = _db()
    chain = failover.candidates("listing_classify")
    assert len(chain) == 2, chain
    primary, fallback = chain
    for _ in range(failover.DOWN_AFTER_CONSECUTIVE):
        failover.record_attempt(db, provider="anthropic", model=primary, ok=False,
                                error=TimeoutError("read timed out"))
    tier = FC.contract_for("listing_classify")["tier"]
    ok = failover.decide(db, "listing_classify")
    assert ok.action == failover.CALL and ok.chosen == fallback, ok.to_dict()
    assert ok.candidates[1]["contract"] in (FC.UNKNOWN, FC.PASS)
    FC.record_eval(db, provider="anthropic", model=fallback, tier=tier, passed=2, total=20,
                   source="golden tasks")
    refused = failover.decide(db, "listing_classify")
    assert refused.action == failover.PARK, refused.to_dict()
    assert refused.candidates[1].get("contract_refused") is True


def test_review_f10_an_unreadable_contract_is_not_routed():
    from brambleloop.gateway import failover

    db = _db()
    primary, fallback = failover.candidates("listing_classify")
    for _ in range(failover.DOWN_AFTER_CONSECUTIVE):
        failover.record_attempt(db, provider="anthropic", model=primary, ok=False,
                                error=TimeoutError("read timed out"))
    real = FC.may_route

    def boom(*a, **k):
        raise RuntimeError("contract table unreadable")

    FC.may_route = boom
    try:
        d = failover.decide(db, "listing_classify")
    finally:
        FC.may_route = real
    assert d.action == failover.PARK, d.to_dict()
    row = d.candidates[1]
    assert row["contract"].startswith("UNKNOWN") and row.get("contract_refused") is True


# ---- F-099 -------------------------------------------------------------------------------

def test_f099_prices_are_versioned_and_a_change_reruns_routing_economics():
    db = _db()
    first = PW.watch(db)
    assert first["baseline"] is True and first["version"] == 1
    assert PW.watch(db)["changed"] == []
    model = next(iter(anthropic.PRICES_USD_PER_MTOK))
    saved = anthropic.PRICES_USD_PER_MTOK[model]
    anthropic.PRICES_USD_PER_MTOK[model] = (saved[0] * 2, saved[1] * 2)
    try:
        out = PW.watch(db)
    finally:
        anthropic.PRICES_USD_PER_MTOK[model] = saved
    assert out["version"] == 2 and [c["what"] for c in out["changed"]] == [
        f"prices_usd_per_mtok:{model}"], out
    # F-096: a provider change asks for a fresh compatibility pack; none has been recorded.
    assert out["compat_pack"]["required"] is True and out["compat_pack"]["last"] is None
    with db.session() as s:
        actions = [r.action for r in s.scalars(select(AuditLog))]
        inc = [r.signature for r in s.scalars(select(Incident).where(
            Incident.resolved == False))]  # noqa: E712
    assert PW.REVIEW_ACTION in actions and PW.CHANGE_ACTION in actions
    assert inc == [f"provider-change:prices_usd_per_mtok:{model}"]
    back = PW.watch(db)                       # price restored: a change again, version 3
    assert back["version"] == 3
    steady = PW.watch(db)
    assert steady["changed"] == [] and steady["resolved"], steady


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
