"""ENG-CREDITS (W6): model-provider promotional credit is accounted, never spending authority.

The owner receives about US$100/month of Anthropic API credit (and possibly an OpenAI credit).
`finance.credits` accounts for it per provider; these tests hold the rules:

* the remaining eligible credit is UNKNOWN until the owner records a verified grant for the
  period -- never assumed to exist, never read as zero;
* a credit grant never raises the cash ceiling: the monthly ceiling, the month's spend and the
  pre-call refusal all read the same with a grant as without one;
* model cost per product (plus the unattributed remainder) sums to the month's model ledger;
* gross, billed (provider-reported only, else UNKNOWN) and cash usage, and failed / uncertain
  paid calls, are reported per provider;
* recording a grant is the owner's step-up action, and nothing here adds an auto-recharge, a
  balance probe or any network call.

No test reaches a network (`network_guard`).

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_eng_credits.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import network_guard  # noqa: E402
from r2_autonomy_harness import boot, run_tests  # noqa: E402

network_guard.install()

from sqlalchemy import func, select  # noqa: E402

from brambleloop.core.models import CostEntry  # noqa: E402
from brambleloop.finance import credits as C, spend_policy  # noqa: E402
from brambleloop.gateway import paid_calls, routing  # noqa: E402
from brambleloop.gateway.routing import USD_PER_CAD  # noqa: E402

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
OWNER = "owner:cc:s_test"
EVIDENCE = "Anthropic console billing page, credit grant line, read 2026-11-01"


def _cost(db, *, provider="anthropic", cad=1.0, slug="", kind="llm", at=None,
          observed=None):
    with db.session() as s:
        row = CostEntry(agent="concept", kind=kind, amount_cad=cad, provider=provider,
                        model="m", product_slug=slug, at=at or NOW - timedelta(days=1),
                        observed_cad=observed)
        s.add(row)
        s.flush()
        return row.id


def _grant(db, **over):
    kw = dict(provider="anthropic", amount=100.0, currency="USD", period_start="2026-11-01",
              period_end="2026-11-30", expires_on="2026-11-30", evidence_note=EVIDENCE,
              recorded_by=OWNER)
    kw.update(over)
    return C.record_model_credit(db, **kw)


# ---- 1. UNKNOWN until recorded ---------------------------------------------------------------

def test_credit_is_unknown_until_the_owner_records_it():
    db = boot("engcred-unknown-")
    _cost(db, cad=2.5)
    got = C.model_credit_accounting(db, now=NOW)
    for name in C.MODEL_PROVIDERS:
        credit = got["providers"][name]["credit"]
        assert credit["state"] == C.UNKNOWN, credit
        # UNKNOWN is never zero and never a number.
        assert credit["remaining_eligible_cad"] == C.UNKNOWN
        assert credit["remaining_eligible_usd"] == C.UNKNOWN
        assert "not assumed to exist" in credit["why"]
    a = got["providers"]["anthropic"]
    assert a["gross_usage_cad"] == 2.5 and a["estimated_cash_cad"] == 2.5
    assert a["estimated_credit_absorbed_cad"] == 0.0
    # A grant for a different period does not make this period's credit known.
    _grant(db, period_start="2026-10-01", period_end="2026-10-31", expires_on="2026-10-31")
    got = C.model_credit_accounting(db, now=NOW)
    assert got["providers"]["anthropic"]["credit"]["state"] == C.UNKNOWN
    assert got["providers"]["anthropic"]["estimated_cash_cad"] == 2.5
    # Recording this period's grant makes it known, as an estimate.
    _grant(db)
    got = C.model_credit_accounting(db, now=NOW)
    credit = got["providers"]["anthropic"]["credit"]
    assert credit["state"] == "RECORDED", credit
    expected = round(100.0 / USD_PER_CAD - 2.5, 6)
    assert abs(credit["remaining_eligible_cad"] - expected) < 1e-6, credit
    assert "ESTIMATED" in credit["basis"]
    assert got["providers"]["anthropic"]["estimated_cash_cad"] == 0.0
    # The other provider is untouched: still UNKNOWN.
    assert got["providers"]["openai"]["credit"]["state"] == C.UNKNOWN


def test_an_expired_grant_leaves_the_credit_unknown_not_zero():
    db = boot("engcred-expired-")
    _grant(db, period_start="2026-11-01", period_end="2026-11-30", expires_on="2026-11-10")
    got = C.model_credit_accounting(db, now=NOW)
    assert got["providers"]["anthropic"]["credit"]["state"] == C.UNKNOWN
    # Usage after the expiry is cash.
    _cost(db, cad=3.0)
    assert C.model_credit_accounting(db, now=NOW)["providers"]["anthropic"][
        "estimated_cash_cad"] == 3.0


def test_an_unknown_expiry_is_recorded_as_unknown():
    db = boot("engcred-noexp-")
    out = _grant(db, expires_on="")
    assert out["expires_on"] is None and out["expiry_basis"] == C.UNKNOWN
    g = C.model_credit_accounting(db, now=NOW)["providers"]["anthropic"]["grants"][0]
    assert g["expiry_basis"] == C.UNKNOWN and g["expires_on"] is None
    # The period still bounds the draw: usage after the period is cash.
    _cost(db, cad=4.0, at=datetime(2026, 12, 2, tzinfo=timezone.utc))
    dec = C.model_credit_accounting(db, now=datetime(2026, 12, 3, tzinfo=timezone.utc))
    assert dec["providers"]["anthropic"]["credit"]["state"] == C.UNKNOWN
    assert dec["providers"]["anthropic"]["estimated_cash_cad"] == 4.0


# ---- 2. a credit never raises the cash ceiling -----------------------------------------------

def test_a_credit_grant_never_raises_the_cash_ceiling():
    db = boot("engcred-ceiling-")
    ceiling = spend_policy.ceiling_cad()
    assert ceiling == spend_policy.CEILING_CAD == 100.0
    # Spend up to just under the ceiling, so the next deep call must be refused.
    task = "creative_evaluation"
    near = ceiling - routing.estimate_cad(task) / 2
    _cost(db, cad=near, at=NOW - timedelta(hours=1))
    before = (routing.spent_this_month(db, NOW), routing.budget(db, NOW).ceiling_cad,
              spend_policy.headroom(near))
    try:
        routing.check(db, task, now=NOW)
        raise AssertionError("the ceiling did not refuse")
    except routing.CeilingReached:
        pass
    # A grant far larger than the ceiling.
    _grant(db, amount=5000.0)
    acct = C.model_credit_accounting(db, now=NOW)
    assert acct["providers"]["anthropic"]["credit"]["state"] == "RECORDED"
    assert acct["ceilings_changed"] == 0 and acct["cash_ceiling_cad"] == ceiling
    after = (routing.spent_this_month(db, NOW), routing.budget(db, NOW).ceiling_cad,
             spend_policy.headroom(near))
    assert after == before, (before, after)
    assert spend_policy.ceiling_cad() == ceiling and routing.MONTHLY_CEILING_CAD == ceiling
    try:
        routing.check(db, task, now=NOW)
        raise AssertionError("a credit grant let a call past the cash ceiling")
    except routing.CeilingReached:
        pass


def test_the_credit_module_never_writes_a_ceiling_or_reads_one_as_raisable():
    text = (ROOT / "src/brambleloop/finance/credits.py").read_text(encoding="utf-8")
    assert not re.search(r"CEILING_CAD\s*=|MONTHLY_CEILING_CAD\s*=|ceiling_cad\s*=", text)
    assert not re.search(r"spend_policy\.\w+\s*=", text)
    assert "setattr(spend_policy" not in text and "setattr(routing" not in text


# ---- 3. per-product model cost sums to the ledger --------------------------------------------

def test_per_product_model_cost_sums_match_the_ledger():
    db = boot("engcred-product-")
    _cost(db, slug="basket", cad=0.40)
    _cost(db, slug="basket", cad=0.10, provider="openai")
    _cost(db, slug="cardigan", cad=1.25)
    _cost(db, slug="", cad=0.30)                                   # unattributed
    _cost(db, slug="basket", cad=9.0, kind="image")                 # not a model cost
    _cost(db, slug="basket", cad=7.0, at=datetime(2026, 10, 30, tzinfo=timezone.utc))
    got = C.model_cost_by_product(db, now=NOW)
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    end = datetime(2026, 12, 1, tzinfo=timezone.utc)
    with db.session() as s:
        ledger = s.scalar(select(func.sum(CostEntry.amount_cad)).where(
            CostEntry.kind == "llm", CostEntry.at >= start, CostEntry.at < end))
    assert abs(got["ledger_total_cad"] - ledger) < 1e-9, (got, ledger)
    by = {p["product_slug"]: p for p in got["by_product"]}
    assert set(by) == {"basket", "cardigan"}
    assert abs(by["basket"]["cad"] - 0.50) < 1e-9 and by["basket"]["calls"] == 2
    assert by["basket"]["by_provider"] == {"anthropic": 0.4, "openai": 0.1}
    assert abs(sum(p["cad"] for p in got["by_product"]) + got["unattributed_cad"]
               - ledger) < 1e-9
    assert got["reconciles"] is True and got["unattributed_cad"] == 0.30


def test_per_package_cost_is_the_product_cost_only_when_it_is_the_only_package():
    db = boot("engcred-package-")
    _cost(db, slug="basket", cad=0.8)
    _cost(db, slug="cardigan", cad=0.6)
    from brambleloop.publish import listing_package as LP

    releases = [("basket", "1.3.0"), ("cardigan", "1.0.0"), ("cardigan", "1.1.0")]
    with patch.object(LP, "certified_releases", lambda _db: releases), \
            patch.object(LP, "latest", lambda _db, s, v: {"status": LP.READY}):
        got = C.model_cost_by_product(db, now=NOW)
    pk = {p["package"]: p for p in got["certified_packages"]}
    assert pk["basket@1.3.0"]["package_model_cost_cad"] == 0.8
    assert pk["basket@1.3.0"]["status"] == LP.READY
    for key in ("cardigan@1.0.0", "cardigan@1.1.0"):
        assert pk[key]["package_model_cost_cad"] == C.UNKNOWN, pk[key]
        assert pk[key]["product_model_cost_cad"] == 0.6


# ---- 4. gross / billed / cash and failed / uncertain calls -----------------------------------

def test_billed_usage_is_provider_reported_only_and_failed_calls_are_counted():
    db = boot("engcred-billed-")
    _cost(db, cad=1.0)
    got = C.model_credit_accounting(db, now=NOW)["providers"]["anthropic"]
    assert got["billed_usage_cad"] == C.UNKNOWN and "UNKNOWN" in got["billed_basis"]
    _cost(db, cad=2.0, observed=1.8)
    got = C.model_credit_accounting(db, now=NOW)["providers"]["anthropic"]
    assert got["gross_usage_cad"] == 3.0 and got["billed_usage_cad"] == 1.8
    assert "1 of 2" in got["billed_basis"]
    assert abs(got["gross_usage_usd"] - round(3.0 * USD_PER_CAD, 6)) < 1e-9
    paid_calls.ensure_table(db)
    with db.session() as s:
        for i, (outcome, prov, est) in enumerate((
                (paid_calls.UNCERTAIN, "anthropic", 0.07),
                (paid_calls.UNCERTAIN, "anthropic-vision", 0.03),
                (paid_calls.FAILED_BILLED, "anthropic", 0.2),
                (paid_calls.DECLINED, "anthropic", 0.5),
                (paid_calls.OK, "anthropic", 0.9),
                (paid_calls.UNCERTAIN, "openai", 0.4))):
            s.add(paid_calls.PaidCallRecord(key=f"k{i}", effect="e", fingerprint="f",
                                            outcome=outcome, estimate_cad=est, provider=prov,
                                            model="m", at=NOW - timedelta(hours=2)))
        # Last month's uncertain call is not this month's.
        s.add(paid_calls.PaidCallRecord(key="old", effect="e", fingerprint="f",
                                        outcome=paid_calls.UNCERTAIN, estimate_cad=5.0,
                                        provider="anthropic", model="m",
                                        at=datetime(2026, 10, 3, tzinfo=timezone.utc)))
    o = C.model_credit_accounting(db, now=NOW)["providers"]["anthropic"]["calls_outcomes"]
    assert o["uncertain"] == 2 and abs(o["uncertain_estimate_cad"] - 0.10) < 1e-9, o
    assert o["failed_billed"] == 1 and o["failed_billed_estimate_cad"] == 0.2
    assert o["declined"] == 1


# ---- 5. recording refuses what is not a verified owner grant ---------------------------------

def test_recording_refuses_anything_but_a_verified_owner_grant():
    db = boot("engcred-refuse-")
    bad = [dict(recorded_by="agent:concept"), dict(recorded_by=""),
           dict(evidence_note="trust me"), dict(evidence_note=""),
           dict(provider="venice"), dict(provider=""),
           dict(amount=0), dict(amount=-5), dict(amount=float("nan")), dict(amount="x"),
           dict(currency="EUR"), dict(period_start="2026-11-31"),
           dict(period_start="2026-11-30", period_end="2026-11-01"),
           dict(expires_on="2026-10-01")]
    for over in bad:
        try:
            _grant(db, **over)
            raise AssertionError(f"recorded {over}")
        except C.CreditRefused:
            pass
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(C.ProviderCredit)) == 0
    _grant(db)
    try:
        _grant(db, period_start="2026-11-15", period_end="2026-12-14", expires_on="")
        raise AssertionError("an overlapping grant was recorded twice")
    except C.CreditRefused as exc:
        assert "overlapping" in str(exc)
    # The next month is its own grant; OpenAI is its own provider.
    _grant(db, period_start="2026-12-01", period_end="2026-12-31", expires_on="2026-12-31")
    _grant(db, provider="openai", amount=20.0)
    with db.session() as s:
        rows = list(s.scalars(select(C.ProviderCredit)))
    assert len(rows) == 3 and all(r.recorded_by == OWNER for r in rows)
    assert all(r.kind == "promotional_credit" and r.source == "owner_reported" for r in rows)


# ---- 6. no auto-recharge, no paid probe, no network ------------------------------------------

def _identifiers(path: Path) -> set[str]:
    """Every name, attribute, called function, defined function and imported module in a
    file's code -- docstrings and comments excluded, so prose that says "no recharge" is not
    mistaken for a recharge."""
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.add(node.module or "")
            out.update(a.name for a in node.names)
    return out


def test_nothing_here_recharges_probes_or_calls_a_provider():
    names = _identifiers(ROOT / "src/brambleloop/finance/credits.py")
    banned = {"httpx", "requests", "urllib", "urllib.request", "socket", "AnthropicProvider",
              "OpenAIProvider", "probe", "vision_probe", "probe_if_due", "for_task",
              "provider_for", "check_budget", "reserve", "enqueue", "JobQueue", "complete",
              "see", "ask"}
    assert not (names & banned), sorted(names & banned)
    assert not [n for n in names if re.search(r"recharge|top_?up|probe", n, re.I)], names
    # Repository-wide: no code identifier anywhere names an auto-recharge or top-up.
    hits = []
    for p in (ROOT / "src").rglob("*.py"):
        bad = [n for n in _identifiers(p)
               if re.search(r"auto_?recharge|recharge|top_?up_?(credit|balance)", n, re.I)]
        if bad:
            hits.append((str(p.relative_to(ROOT)), bad))
    assert hits == [], hits
    # Recording and reading move no money: no cost row, no paid call, no reservation.
    db = boot("engcred-nomoney-")
    paid_calls.ensure_table(db)
    from brambleloop.core.models import SpendReservation

    def counts():
        with db.session() as s:
            return tuple(s.scalar(select(func.count()).select_from(m)) for m in
                         (CostEntry, paid_calls.PaidCallRecord, SpendReservation))
    before = counts()
    _grant(db)
    C.model_credit_accounting(db, now=NOW)
    C.model_cost_by_product(db, now=NOW)
    from brambleloop.app.command_center import p0_board

    sec = p0_board.view(db, now=NOW)["sections"]["model_credit"]
    assert counts() == before
    assert sec["state"] == "RECORDED" and sec["ceilings_changed"] == 0, sec


def test_the_p0_board_section_is_unknown_until_recorded():
    db = boot("engcred-p0-")
    _cost(db, cad=0.25, slug="basket")
    from brambleloop.app.command_center import p0_board

    sec = p0_board.view(db, now=NOW)["sections"]["model_credit"]
    assert sec["state"] == C.UNKNOWN and "never assumed" in sec["why"], sec
    assert sec["providers"]["anthropic"]["credit"]["remaining_eligible_cad"] == C.UNKNOWN
    assert sec["cash_ceiling_cad"] == spend_policy.CEILING_CAD
    assert sec["cost_by_product"]["reconciles"] is True
    assert sec["level"] == p0_board.CODE_BUILT


# ---- 7. productive use: where a model call is starved -----------------------------------------

def test_productive_use_reports_starved_no_caller_and_running_families():
    from brambleloop.core.models import AuditLog
    from brambleloop.finance import spend_report

    db = boot("engcred-productive-")
    with db.session() as s:
        s.add(CostEntry(agent="creative_director", kind="llm", amount_cad=0.9,
                        provider="anthropic", purpose="concept_generation",
                        at=NOW - timedelta(hours=3)))
    spend_report.record_refusal(db, agent="quality_director", ceiling_cad=1.0,
                                estimate_cad=0.05, committed_cad=0.98, which="agent",
                                why="t", purpose="asset_inspection",
                                now=NOW - timedelta(hours=1))
    # Last month's refusal does not starve this month.
    spend_report.record_refusal(db, agent="creative_director", ceiling_cad=28.0,
                                estimate_cad=1.0, committed_cad=28.0, which="agent",
                                why="t", purpose="benchmark_challenge",
                                now=datetime(2026, 10, 2, tzinfo=timezone.utc))
    with db.session() as s:
        n_audit = s.scalar(select(func.count()).select_from(AuditLog))
    got = C.productive_model_use(db, now=NOW)
    fam = {f["family"]: f for f in got["families"]}
    assert fam["concept_generation"]["state"] == "RUNNING"
    assert fam["concept_generation"]["spend_cad"] == 0.9
    assert fam["image_review"]["state"] == "STARVED", fam["image_review"]
    assert fam["image_review"]["refusals"] == {"agent": 1}
    assert fam["image_review"]["agent_daily_ceiling_cad"] == 1.0
    assert fam["independent_review"]["state"] == "IDLE"
    assert fam["listing_copy_refinement"]["state"] == "NO_CALLER"
    assert fam["defect_learning"]["state"] == "NO_CALLER"
    assert got["ceilings_changed"] == 0
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(AuditLog)) == n_audit


# ---- 8. the owner's Command Center action ----------------------------------------------------

def test_the_owner_route_requires_step_up_and_records_the_owner_not_the_body():
    import r2_security_harness as H  # the real app, owner login, CSRF and nonce
    from brambleloop.app.command_center.models import OwnerSession

    c = H.client()
    csrf = H.login(c)
    body = {"provider": "anthropic", "amount": 100, "currency": "USD",
            "period_start": "2026-11-01", "period_end": "2026-11-30",
            "expires_on": "2026-11-30", "evidence_note": EVIDENCE,
            "recorded_by": "owner:forged"}
    with H.DB.session() as s:
        for row in s.scalars(select(OwnerSession)):
            row.stepup_until = None
    r = c.post("/api/cc/finance/model-credit", json=body, headers=H.fresh(csrf))
    assert r.status_code == 403 and "STEP_UP_REQUIRED" in r.text, r.text
    with H.DB.session() as s:
        C.ensure_table(H.DB)
        assert s.scalar(select(func.count()).select_from(C.ProviderCredit)) == 0
    # Without a session at all: refused before the handler.
    anon = H.client()
    r = anon.post("/api/cc/finance/model-credit", json=body, headers=H.fresh(None))
    assert r.status_code in (401, 403), r.text
    with H.DB.session() as s:
        for row in s.scalars(select(OwnerSession)):
            row.stepup_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    r = c.post("/api/cc/finance/model-credit", json={**body, "evidence_note": "short"},
               headers=H.fresh(csrf))
    assert r.status_code == 400 and "REFUSED" in r.text, r.text
    r = c.post("/api/cc/finance/model-credit", json=body, headers=H.fresh(csrf))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ceilings_changed"] == 0 and data["expiry_basis"] == "stated"
    with H.DB.session() as s:
        row = s.scalar(select(C.ProviderCredit))
        assert row.recorded_by.startswith("owner:cc:") and row.recorded_by != "owner:forged"
    view = c.get("/api/cc/finance/model-credit", headers=H.fresh(csrf))
    assert view.status_code == 200, view.text
    v = view.json()
    assert v["accounting"]["cash_ceiling_cad"] == spend_policy.CEILING_CAD
    assert v["cost_by_product"]["reconciles"] is True


def test_no_new_audit_action_lacks_a_retention_decision():
    from brambleloop.ops import retention

    assert retention.unknown_read_actions() == []


if __name__ == "__main__":
    run_tests(globals())
