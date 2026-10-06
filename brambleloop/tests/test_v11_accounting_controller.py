"""v1.1 lane E: the Accountant agent -- policy, close, tax pack, handoff, guardrails.

F-901 controller cycle, F-909 tax-ready pack, F-910 month-end close, F-912 spend governor
(section 95: "Let Growth propose spend that Finance says violates margin/cash policy:
cross-agent challenge blocks/escalates rather than self-approving"), F-916 handoff export,
F-917 guardrails, and the `next_work` contract for the orchestrator.
Run: cd brambleloop && PYTHONPATH=src python3 tests/test_v11_accounting_controller.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="v11_acct_ctrl_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")


def _no_network(*_a, **_k):
    raise OSError("network refused by the accounting harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import OwnerAction  # noqa: E402
from brambleloop.finance import accounting  # noqa: E402
from brambleloop.finance.accounting import (close, controller, dashboard,  # noqa: E402
                                            guardrails, handoff, policy, posting_rules,
                                            reconciliation, shadow_dataset, tax_pack)
from brambleloop.finance.accounting import exceptions as X  # noqa: E402
from brambleloop.finance.accounting.models import AcctChallenge  # noqa: E402

NOW = datetime.now(timezone.utc)
PREV = (NOW.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
_n = [0]


def _db(seed=True):
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/c{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    if seed:
        shadow_dataset.seed(db, now=NOW)
    return db


GROWTH_ADS = {"proposer": "growth", "department": "growth", "kind": "ads",
              "purpose": "Etsy Ads test for the moss stitch cowl", "amount_cad": 40.0,
              "channel": "etsy_ads", "product_slug": "moss-stitch-cowl",
              "expected_contribution_cad": 20.0}


def test_growth_spend_violating_margin_and_cash_policy_is_blocked_by_finance():
    """Section 95."""
    db = _db()
    controller.run_cycle(db, now=NOW)
    r = policy.check_spend(db, GROWTH_ADS, now=NOW)
    assert r["allow"] is False and r["verdict"] == "blocked" and r["escalate_to"] == "owner"
    rules = {c["rule"] for c in r["checks"] if c["outcome"] == "block"}
    assert {"margin", "cash", "caps", "phase"} <= rules, rules
    assert r["challenge_id"].startswith("fin-")
    with db.session() as s:
        row = s.scalar(select(AcctChallenge).where(
            AcctChallenge.challenge_id == r["challenge_id"]))
        assert row is not None and row.verdict == "blocked" and row.proposer == "growth"
    assert policy.challenges(db)[0]["challenge_id"] == r["challenge_id"]


def test_budget_availability_is_never_permission():
    """Cash known and ample, margin fine, not shadow -- and still no authority: escalate."""
    db = _db()
    reconciliation.import_statement(db, "bank", [
        {"external_id": "c1", "at": NOW, "kind": "owner_contribution", "amount": 5000.0,
         "reference": "owner"}], now=NOW)
    controller.run_cycle(db, now=NOW)
    for x in X.listing(db):
        X.resolve(db, x["key"], resolution="reviewed in test fixture", by="owner")
    from brambleloop.core import phase as phase_mod
    real = phase_mod.effective
    phase_mod.effective = lambda *a, **k: "limited_production"  # isolate the authority rule
    try:
        proposal = {**GROWTH_ADS, "amount_cad": 10.0, "expected_contribution_cad": 30.0,
                    "product_slug": None}
        r = policy.check_spend(db, proposal, now=NOW)
        assert r["allow"] is False and r["verdict"] == "escalated", r
        assert any("not permission" in x for x in r["reasons"])
        with db.session() as s:
            s.add(OwnerAction(requirement_key="ads.test.cowl", action="approve ads test",
                              max_cost_cad=10.0, done=False))
        r2 = policy.check_spend(db, {**proposal, "authority": {"type": "owner_action",
                                                               "ref": "ads.test.cowl"}},
                                now=NOW)
        assert r2["allow"] is False, "an unapproved owner action is not authority"
        with db.session() as s:
            s.scalar(select(OwnerAction)).done = True
        r3 = policy.check_spend(db, {**proposal, "authority": {"type": "owner_action",
                                                               "ref": "ads.test.cowl"}},
                                now=NOW)
        assert r3["allow"] is True and r3["verdict"] == "cleared", r3
        r4 = policy.check_spend(db, {**proposal, "amount_cad": 11.0, "authority": {
            "type": "owner_action", "ref": "ads.test.cowl"}}, now=NOW)
        assert r4["allow"] is False, "above the approved maximum"
    finally:
        phase_mod.effective = real


def test_month_end_close_checklist_blocks_until_clean_then_locks():
    db = _db()
    controller.run_cycle(db, now=NOW)
    cur = NOW.strftime("%Y-%m")
    c0 = close.checklist(db, cur, now=NOW)
    assert not c0["closable"] and any(s["step"] == "period_ended" and s["outcome"] == "block"
                                      for s in c0["steps"])
    X.open_exception(db, key="t:open", kind="unmatched_statement_line", summary="x",
                     period=PREV)
    c1 = close.checklist(db, PREV, now=NOW)
    assert not c1["closable"] and "reconciliation_exceptions" in c1["owner_summary"]
    X.resolve(db, "t:open", resolution="matched by hand to bank line 3", by="owner")
    c2 = close.checklist(db, PREV, now=NOW)
    assert c2["closable"], c2["owner_summary"]
    assert {s["step"] for s in c2["steps"]} >= {
        "source_completeness", "ledger_posted", "chain_integrity", "trial_balance",
        "reconciliation_exceptions", "anomalies", "revenue_fees_refunds", "expenses",
        "tax_reserve", "bank_source"}
    assert any(s["outcome"] == "warn" for s in c2["steps"]), "modelled fees are a warning"
    out = close.lock_period(db, PREV, by="accountant", now=NOW)
    assert out["locked"] and close.verify_lock(db, PREV)["intact"]
    shadow_dataset.disconnect_order_source(db)
    c3 = close.checklist(db, "2026-01" if PREV != "2026-01" else "2025-12", now=NOW)
    assert any(s["step"] == "source_completeness" and s["outcome"] == "block"
               for s in c3["steps"]), "revenue UNKNOWN cannot be closed"


def test_tax_pack_is_preparation_only_cad_canada_with_questions():
    db = _db()
    posting_rules.post_all(db, now=NOW)
    for spec in (PREV, f"{NOW.year}-Q{(NOW.month - 1) // 3 + 1}", str(NOW.year)):
        p = tax_pack.pack(db, spec, now=NOW)
        assert p["jurisdiction"] == "Canada" and p["currency"] == "CAD"
        assert "NOT FILED" in p["status"]
        assert p["gst_hst"]["collected_cad"] is None and p["gst_hst"]["collected_why"]
        assert len(p["questions_for_accountant"]) >= 5
    y = tax_pack.pack(db, str(NOW.year), now=NOW)
    assert y["summary_cad"]["gross_sales"] > 0 and y["evidence_rows"]
    assert all(r["source_table"] and r["source_id"] for r in y["evidence_rows"])
    assert "USD" in y["sales_by_original_currency"]
    assert any("modelled" in w or "basis" in w for w in y["warnings"])


def test_human_accountant_handoff_export_is_self_describing():
    db = _db()
    posting_rules.post_all(db, now=NOW)
    out_dir = Path(_TMP) / "handoff"
    r = handoff.export(db, out_dir, str(NOW.year), now=NOW)
    want = {"chart_of_accounts.csv", "journal.csv", "trial_balance.csv", "exceptions.csv",
            "statement_lines.csv", "tax_summary.json", "notes.txt", "questions.txt",
            "manifest.json"}
    assert want <= set(r["files"])
    man = json.loads((out_dir / "manifest.json").read_text())["sha256"]
    assert man
    for name, digest in man.items():
        assert hashlib.sha256((out_dir / name).read_bytes()).hexdigest() == digest
    rows = list(csv.DictReader((out_dir / "journal.csv").open()))
    assert rows and all(r["source_table"] and r["basis"] for r in rows)
    notes = (out_dir / "notes.txt").read_text()
    assert "UNKNOWN is not zero" in notes and "REVERSAL" in notes


def test_guardrails_the_package_has_no_money_moving_capability():
    audit = guardrails.audit_package()
    assert audit["modules"] and "ledger" in audit["modules"], audit
    assert audit["ok"], audit
    for action in guardrails.FORBIDDEN_ACTIONS:
        try:
            guardrails.refuse(action)
        except guardrails.AccountingAuthorityRefused:
            continue
        raise AssertionError(action)
    import importlib
    names = []
    for m in audit["modules"]:
        mod = importlib.import_module(f"brambleloop.finance.accounting.{m}")
        names += [n for n in dir(mod) if callable(getattr(mod, n)) and not n.startswith("_")]
    assert names
    bad = [n for n in names if any(f in n.lower() for f in (
        "file_tax", "transfer", "withdraw", "borrow", "sign_contract", "change_bank",
        "send_money", "remit"))]
    assert not bad, bad
    assert "file taxes" in " ".join(controller.PERSONA["may_not"])


def test_controller_cycle_is_idempotent_and_next_work_follows_the_contract():
    db = _db()
    first = controller.run_cycle(db, now=NOW)
    assert first["posting"]["posted"] > 0
    second = controller.run_cycle(db, now=NOW)
    assert second["posting"]["posted"] == 0 and second["posting"]["reversed"] == 0
    assert controller.last_run(db) is not None
    work = dashboard.next_work(db, now=NOW)
    assert work
    keys = {"id", "department", "kind", "title", "priority", "ready", "blocked_by",
            "handler", "evidence"}
    for w in work:
        assert keys <= set(w) and w["department"] == "finance"
        if w["ready"] and w["handler"]:
            mod, fn = w["handler"].split(":")
            import importlib
            assert callable(getattr(importlib.import_module(mod), fn))
    kinds = {w["kind"] for w in work}
    assert "close_month" in kinds and "connect_source" in kinds
    json.dumps(work)
    # New source rows -> a ready post_rows item at priority 1.
    from brambleloop.core.models import CostEntry
    with db.session() as s:
        s.add(CostEntry(agent="a", kind="llm", amount_cad=0.5, detail={"price_basis": "measured"}))
    w2 = dashboard.next_work(db, now=NOW)
    assert w2[0]["kind"] == "post_rows" and w2[0]["ready"] and w2[0]["priority"] == 1
    empty = dashboard.next_work(_db(seed=False), now=NOW)
    assert any(w["kind"] == "run_cycle" for w in empty)


def test_the_cycle_runs_as_a_worker_job():
    from types import SimpleNamespace

    from brambleloop.finance.accounting import job
    from brambleloop.runtime.worker import handlers
    db = _db()
    out = job.handle_accounting_cycle(SimpleNamespace(db=db, job=SimpleNamespace(inputs={})))
    assert out["posting"]["posted"] > 0
    json.dumps(out)
    assert handlers.get(job.JOB_TYPE) is job.handle_accounting_cycle


def test_package_docstring_names_every_module():
    doc = accounting.__doc__ or ""
    mods = guardrails.audit_package()["modules"]
    assert mods
    missing = [m for m in mods if f"`{m}`" not in doc]
    assert not missing, missing


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    assert tests
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
