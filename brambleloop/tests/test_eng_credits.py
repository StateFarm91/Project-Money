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


def test_an_unstated_expiry_is_recorded_as_period_end():
    db = boot("engcred-noexp-")
    out = _grant(db, expires_on="")
    # L2: no stated expiry, but the owner recorded a period end: the basis says so.
    assert out["expires_on"] is None and out["expiry_basis"] == "period_end"
    g = C.model_credit_accounting(db, now=NOW)["providers"]["anthropic"]["grants"][0]
    assert g["expiry_basis"] == "period_end" and g["expires_on"] is None
    led = C.split(db, "anthropic", now=NOW)["grants"][0]
    assert led["expiry_basis"] == "period_end"
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
    _grant(db, amount=C.MAX_GRANT_USD)  # the largest grant accepted, still >> the ceiling
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
    # L1: one of two rows reported is PARTIAL: the total is UNKNOWN, never the 1.8 as the bill.
    assert got["gross_usage_cad"] == 3.0 and got["billed_usage_cad"] == C.UNKNOWN
    assert got["billed_state"] == "PARTIAL" and got["billed_reported_partial_cad"] == 1.8
    assert "1 of 2" in got["billed_basis"] and "UNKNOWN" in got["billed_basis"]
    assert abs(got["gross_usage_usd"] - round(3.0 * USD_PER_CAD, 6)) < 1e-9
    _cost(db, cad=1.0, observed=0.9)
    got = C.model_credit_accounting(db, now=NOW)["providers"]["anthropic"]
    assert got["billed_state"] == "PARTIAL"
    with db.session() as s:
        for e in s.scalars(select(CostEntry).where(CostEntry.observed_cad.is_(None))):
            e.observed_cad = 0.1
    got = C.model_credit_accounting(db, now=NOW)["providers"]["anthropic"]
    assert got["billed_state"] == "COMPLETE" and got["billed_usage_cad"] == 2.8
    assert got["billed_reported_partial_cad"] is None
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


# ---- 7. review fix round 1: nonsense grants, void, atomic overlap, secrets -------------------

# Built from fragments so this file does not match the secret scan's own patterns.
FAKE_KEY = "sk" + "-ant-api03-" + "Zq9" * 12


def _refused(fn, *a, why="", **kw):
    try:
        fn(*a, **kw)
    except C.CreditRefused as exc:
        assert why in str(exc), (why, str(exc))
        return str(exc)
    raise AssertionError(f"was not refused: {kw}")


def _count(db):
    C.ensure_table(db)
    with db.session() as s:
        return s.scalar(select(func.count()).select_from(C.ProviderCredit))


def test_m1_nonsense_amounts_and_periods_are_refused():
    db = boot("engcred-m1-")
    for amt in (True, False, None, "100", "1e3", [100], {"a": 1}, b"5",
                1e15, 1000.01, float("inf"), 10 ** 9):
        _refused(_grant, db, amount=amt)
    # The cap is in USD whatever currency the owner types: CA$ 1e6 is far above it too.
    _refused(_grant, db, amount=1_000_000.0, currency="CAD", why="above")
    _refused(_grant, db, amount=C.MAX_GRANT_USD / USD_PER_CAD * 1.01, currency="CAD")
    # A period of 100 years, or one day over a year, is not a credit period.
    _refused(_grant, db, period_start="2026-01-01", period_end="2126-01-01", why="at most")
    _refused(_grant, db, period_start="2026-01-01", period_end="2027-01-02", why="at most")
    assert _count(db) == 0
    # The edges are accepted: exactly the cap, exactly a (leap-free) year of 366 days.
    _grant(db, amount=C.MAX_GRANT_USD, period_start="2026-01-01", period_end="2027-01-01")
    db2 = boot("engcred-m1b-")
    _grant(db2, amount=C.MAX_GRANT_USD / USD_PER_CAD, currency="CAD")
    _grant(db2, provider="openai", period_start="2027-01-01", period_end="2028-01-01", expires_on="")


def test_l3_currency_and_dates_are_validated_whole_not_truncated():
    db = boot("engcred-l3-")
    for over in (dict(currency="USDX"), dict(currency="CADX"), dict(currency="US"),
                 dict(currency=None), dict(currency=5),
                 dict(period_start="2026-11-01junk"), dict(period_end="2026-11-30T00:00"),
                 dict(period_start="20261101"), dict(period_start="2026-W45-1"),
                 dict(expires_on="2026-11-30x"), dict(period_start=20261101)):
        _refused(_grant, db, **over)
    assert _count(db) == 0
    import r2_security_harness as H

    c = H.client()
    csrf = H.login(c)
    _reset(H)
    _stepup(H)
    base = {"provider": "anthropic", "amount": 100, "currency": "USD",
            "period_start": "2026-11-01", "period_end": "2026-11-30",
            "evidence_note": EVIDENCE}
    for over in ({"currency": "USDX"}, {"period_start": "2026-11-01junk"},
                 {"amount": True}, {"amount": 1e15}):
        r = c.post("/api/cc/finance/model-credit", json={**base, **over},
                   headers=H.fresh(csrf))
        assert r.status_code == 400 and "REFUSED" in r.text, (over, r.text)
    assert _live_count(H.DB) == 0


def _live_count(db):
    C.ensure_table(db)
    with db.session() as s:
        return s.scalar(select(func.count()).select_from(C.ProviderCredit).where(
            C.ProviderCredit.voided_at.is_(None)))


def _reset(H):
    """The route tests share one app DB: void whatever an earlier test recorded there."""
    C.ensure_table(H.DB)
    with H.DB.session() as s:
        ids = list(s.scalars(select(C.ProviderCredit.id).where(
            C.ProviderCredit.voided_at.is_(None))))
    for i in ids:
        C.void_model_credit(H.DB, grant_id=i, reason="test reset of the shared app database",
                            voided_by=OWNER)


def _stepup(H):
    from brambleloop.app.command_center.models import OwnerSession

    with H.DB.session() as s:
        for row in s.scalars(select(OwnerSession)):
            row.stepup_until = datetime.now(timezone.utc) + timedelta(minutes=5)


def test_void_frees_the_period_never_deletes_and_stops_drawing():
    db = boot("engcred-void-")
    first = _grant(db)
    _cost(db, cad=5.0)
    assert C.split(db, "anthropic", now=NOW)["promo_credit_cad"] == 5.0
    _refused(_grant, db, why="overlapping")
    # Refusals: not the owner, a bad id, a missing id, a vague or secret-bearing reason.
    ok_reason = "typed 100 where the console says 10"
    _refused(C.void_model_credit, db, grant_id=first["id"], reason=ok_reason,
             voided_by="agent:x", why="owner")
    for gid in (True, "1", None, 0, -3, 9999):
        _refused(C.void_model_credit, db, grant_id=gid, reason=ok_reason, voided_by=OWNER)
    _refused(C.void_model_credit, db, grant_id=first["id"], reason="oops", voided_by=OWNER)
    _refused(C.void_model_credit, db, grant_id=first["id"],
             reason=f"wrong key {FAKE_KEY}", voided_by=OWNER, why="secret")
    assert _count(db) == 1
    with db.session() as s:
        assert s.scalar(select(C.ProviderCredit.voided_at)) is None
    out = C.void_model_credit(db, grant_id=first["id"], reason=ok_reason, voided_by=OWNER,
                              now=NOW)
    assert out["ceilings_changed"] == 0 and out["id"] == first["id"]
    _refused(C.void_model_credit, db, grant_id=first["id"], reason=ok_reason,
             voided_by=OWNER, why="already voided")
    # Never deleted: the row stays, marked.
    assert _count(db) == 1
    with db.session() as s:
        row = s.scalar(select(C.ProviderCredit))
        assert row.voided_by == OWNER and row.void_reason == ok_reason and row.voided_at
    # Voided: draws nothing (the call is cash again), credit is UNKNOWN, and it is listed.
    sp = C.split(db, "anthropic", now=NOW)
    assert sp["promo_credit_cad"] == 0.0 and sp["billable_cash_cad"] == 5.0 and not sp["grants"]
    acct = C.model_credit_accounting(db, now=NOW)["providers"]["anthropic"]
    assert acct["credit"]["state"] == C.UNKNOWN and acct["grants"] == []
    assert acct["estimated_cash_cad"] == 5.0
    assert [v["id"] for v in acct["voided_grants"]] == [first["id"]]
    assert C.wallet(db, now=NOW)["providers"] == {} or all(
        r["id"] != first["id"] for r in C.wallet(db, now=NOW).get("grants", []))
    # The period is free: the corrected grant records, and now a third still overlaps.
    again = _grant(db, amount=10.0)
    assert again["id"] != first["id"] and _count(db) == 2
    _refused(_grant, db, why="overlapping")
    got = C.model_credit_accounting(db, now=NOW)["providers"]["anthropic"]
    assert got["credit"]["state"] == "RECORDED"
    assert got["credit"]["remaining_eligible_cad"] == round(10.0 / USD_PER_CAD - 5.0, 6)


def test_the_void_route_needs_step_up_is_audited_and_never_echoes_a_secret():
    import r2_security_harness as H
    from brambleloop.app.command_center.models import OwnerSession
    from brambleloop.core.models import AuditLog

    c = H.client()
    csrf = H.login(c)
    _reset(H)
    _stepup(H)
    body = {"provider": "anthropic", "amount": 100, "currency": "USD",
            "period_start": "2026-11-01", "period_end": "2026-11-30",
            "evidence_note": EVIDENCE}
    # L4 on the record route: a key pasted into the note is refused, never stored or echoed.
    r = c.post("/api/cc/finance/model-credit", json={**body, "evidence_note": f"key {FAKE_KEY}"},
               headers=H.fresh(csrf))
    assert r.status_code == 400 and "secret" in r.text and FAKE_KEY not in r.text, r.text
    assert "Zq9Zq9" not in r.text and _live_count(H.DB) == 0
    r = c.post("/api/cc/finance/model-credit", json=body, headers=H.fresh(csrf))
    assert r.status_code == 200, r.text
    gid = r.json()["id"]
    assert r.json()["expiry_basis"] == "period_end"
    with H.DB.session() as s:
        for row in s.scalars(select(OwnerSession)):
            row.stepup_until = None
    why = {"id": gid, "reason": "recorded from the wrong statement"}
    r = c.post("/api/cc/finance/model-credit/void", json=why, headers=H.fresh(csrf))
    assert r.status_code == 403 and "STEP_UP_REQUIRED" in r.text, r.text
    anon = H.client()
    r = anon.post("/api/cc/finance/model-credit/void", json=why, headers=H.fresh(None))
    assert r.status_code in (401, 403), r.text
    _stepup(H)
    r = c.post("/api/cc/finance/model-credit/void",
               json={**why, "reason": f"key {FAKE_KEY} here"}, headers=H.fresh(csrf))
    assert r.status_code == 400 and FAKE_KEY not in r.text and "Zq9Zq9" not in r.text, r.text
    r = c.post("/api/cc/finance/model-credit/void", json={"id": gid, "reason": "x"},
               headers=H.fresh(csrf))
    assert r.status_code == 400, r.text
    r = c.post("/api/cc/finance/model-credit/void", json=why, headers=H.fresh(csrf))
    assert r.status_code == 200 and r.json()["ceilings_changed"] == 0, r.text
    assert r.json()["accounting"]["providers"]["anthropic"]["grants"] == []
    with H.DB.session() as s:
        acts = [(a.action, a.detail) for a in s.scalars(select(AuditLog))
                if a.action == C.MODEL_CREDIT_VOIDED]
        assert len(acts) == 1 and acts[0][1]["id"] == gid
        blob = " ".join(str(a.detail) for a in s.scalars(select(AuditLog)))
    assert FAKE_KEY not in blob and "Zq9Zq9" not in blob
    r = c.post("/api/cc/finance/model-credit/void", json=why, headers=H.fresh(csrf))
    assert r.status_code == 400 and "already voided" in r.text, r.text


def test_l4_secret_like_evidence_is_refused_and_never_echoed():
    db = boot("engcred-l4-")
    for note in (f"billing page, key {FAKE_KEY}",
                 "console read; Authorization: Bearer " + "abcDEF0123456789" * 3,
                 "email, AKIA" + "ABCDEFGHIJKLMNOP",
                 "statement -----BEGIN RSA PRIVATE KEY-----"):
        msg = _refused(_grant, db, evidence_note=note, why="secret")
        assert FAKE_KEY not in msg and "Zq9Zq9" not in msg and "abcDEF" not in msg, msg
    _refused(_grant, db, evidence_note="x" * 5000, why="at most")
    assert _count(db) == 0
    # An honest note, and a note that merely mentions the word, are fine.
    _grant(db, evidence_note="Billing page: the credit grant line; no key quoted here")
    with db.session() as s:
        assert "Zq9" not in s.scalar(select(C.ProviderCredit.note))


def _race(db, results):
    """Two threads record overlapping grants at the same instant: both read the ledger before
    either inserts (the seam holds them between the check and the insert)."""
    import threading

    barrier = threading.Barrier(2)

    def seam():
        try:
            barrier.wait(timeout=2.0)
        except threading.BrokenBarrierError:
            pass            # the other recorder is (correctly) waiting on the lock

    def one(i, **over):
        try:
            results[i] = _grant(db, **over)
        except C.CreditRefused as exc:
            results[i] = exc
        except Exception as exc:  # noqa: BLE001 - an engine-level lock failure is a refusal too
            results[i] = exc

    C._before_insert = seam
    try:
        ts = [threading.Thread(target=one, args=(0,)),
              threading.Thread(target=one, args=(1,), kwargs=dict(
                  period_start="2026-11-15", period_end="2026-12-14", expires_on=""))]
        for th in ts:
            th.start()
        for th in ts:
            th.join(timeout=30)
    finally:
        C._before_insert = None


def _one_wins(db, results):
    won = [r for r in results if isinstance(r, dict)]
    lost = [r for r in results if isinstance(r, Exception)]
    assert len(won) == 1 and len(lost) == 1, results
    assert isinstance(lost[0], C.CreditRefused) and "overlapping" in str(lost[0]), lost
    assert _count(db) == 1


def test_two_concurrent_overlapping_grants_record_only_one_sqlite():
    db = boot("engcred-race-")
    results = [None, None]
    _race(db, results)
    _one_wins(db, results)


def _local_pg_cluster():
    """A throwaway PostgreSQL cluster (the W6 pattern of test_a3_postgres_photo_fence):
    127.0.0.1, a free port, one empty database, destroyed afterwards. Yields the URL, or None
    when no local PostgreSQL toolchain exists (the test then prints SKIP: never a silent pass)."""
    import contextlib
    import glob
    import os
    import shutil
    import socket
    import subprocess
    import tempfile

    @contextlib.contextmanager
    def cluster():
        bins = sorted(glob.glob("/usr/lib/postgresql/*/bin/initdb"))
        if not bins:
            yield None
            return
        bindir = os.path.dirname(bins[-1])
        as_pg = []
        if os.geteuid() == 0:
            import pwd

            try:
                pwd.getpwnam("postgres")
            except KeyError:
                yield None
                return
            as_pg = ["runuser", "-u", "postgres", "--"]
        base = tempfile.mkdtemp(prefix="eng-credits-pg-", dir="/tmp")
        os.chmod(base, 0o755)
        if as_pg:
            shutil.chown(base, user="postgres")
        data = os.path.join(base, "data")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        started = False
        run = lambda *a: subprocess.run(as_pg + list(a), check=True,  # noqa: E731
                                        capture_output=True, timeout=120)
        try:
            run(f"{bindir}/initdb", "-D", data, "-A", "trust", "-U", "postgres")
            started = True
            run(f"{bindir}/pg_ctl", "-D", data, "-w", "-l", os.path.join(base, "log"), "-o",
                f"-c listen_addresses=127.0.0.1 -c port={port} "
                f"-c unix_socket_directories={base}", "start")
            run(f"{bindir}/createdb", "-h", "127.0.0.1", "-p", str(port), "-U", "postgres",
                "eng_credits_test")
            yield f"postgresql://postgres@127.0.0.1:{port}/eng_credits_test"
        finally:
            if started:
                subprocess.run(as_pg + [f"{bindir}/pg_ctl", "-D", data, "-m", "immediate",
                                        "-w", "stop"], capture_output=True, timeout=120)
            shutil.rmtree(base, ignore_errors=True)

    return cluster()


def test_two_concurrent_overlapping_grants_record_only_one_postgresql():
    from brambleloop.core.db import Database

    with _local_pg_cluster() as url:
        if url is None:
            print("SKIP test_two_concurrent_overlapping_grants_record_only_one_postgresql: "
                  "no local PostgreSQL toolchain (UNKNOWN, not PASS)")
            return
        db = Database(url, scratch=True)
        assert db.engine.dialect.name == "postgresql"
        with db.engine.connect() as conn:
            from sqlalchemy import text
            assert int(conn.execute(text("show server_version_num")).scalar()) // 10000 >= 16
        C.ensure_table(db)
        results = [None, None]
        _race(db, results)
        _one_wins(db, results)
        # Run the race again for the next period boundary and a void between: still one winner.
        with db.session() as s:
            gid = s.scalar(select(C.ProviderCredit.id))
        C.void_model_credit(db, grant_id=gid, reason="recorded in the wrong period",
                            voided_by=OWNER)
        results = [None, None]
        _race(db, results)
        with db.session() as s:
            live = s.scalar(select(func.count()).select_from(C.ProviderCredit).where(
                C.ProviderCredit.voided_at.is_(None)))
        assert live == 1 and sum(isinstance(r, dict) for r in results) == 1, results
        db.engine.dispose()


def test_no_new_audit_action_lacks_a_retention_decision():
    from brambleloop.ops import retention

    assert retention.unknown_read_actions() == []


if __name__ == "__main__":
    run_tests(globals())
