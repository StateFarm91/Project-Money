"""v1.1 lane H: Growth proposes ad spend, Finance challenges it (F-919, F-912, §95, §12).

§95: "Let Growth propose spend that Finance says violates margin/cash policy: cross-agent
challenge blocks/escalates rather than self-approving." Plus: ceilings enforced in code even
after owner authority exists; a Finance-cleared proposal is an owner approval item, not spend.

All rows are TEST FIXTURES in throwaway databases. Nothing spends.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_v11_ads_challenge.py
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import Incident, OwnerAction, SpendLimit  # noqa: E402
from brambleloop.growth import ads_readiness as ads  # noqa: E402
from test_v11_ads_readiness import (  # noqa: E402
    NOW, TRUST_PASS, add_listing, fresh_db, make_eligible,
)

HYP = "TEST FIXTURE hypothesis: ads lift visits for an organically converting listing"
STOP = "stop at CA$10 spend with zero orders or CAC above max"


def ready_db(slug="p", price=12.0):
    db = fresh_db()
    add_listing(db, slug, price=price)
    make_eligible(db)
    return db


def owner_actions(db, key_prefix="ads.proposal:"):
    with db.session() as s:
        return [a for a in s.scalars(select(OwnerAction))
                if a.requirement_key.startswith(key_prefix)]


def grant_authority(db, daily, lifetime):
    with db.session() as s:
        s.add(SpendLimit(scope="ads", daily_cap_cad=daily, lifetime_cap_cad=lifetime))


class FakeAccounting:
    """Installs a stand-in for lane E's `finance.accounting.policy` for one test."""

    def __init__(self, fn):
        self.fn = fn
        self.names = ("brambleloop.finance.accounting", "brambleloop.finance.accounting.policy")

    def __enter__(self):
        self.saved = {n: sys.modules.get(n) for n in self.names}
        pkg = types.ModuleType(self.names[0])
        pkg.__path__ = []
        mod = types.ModuleType(self.names[1])
        mod.check_spend = self.fn
        pkg.policy = mod
        sys.modules[self.names[0]], sys.modules[self.names[1]] = pkg, mod
        import brambleloop.finance as fin
        self.had = getattr(fin, "accounting", None)
        fin.accounting = pkg
        return self

    def __exit__(self, *exc):
        import brambleloop.finance as fin
        for n, m in self.saved.items():
            if m is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = m
        if self.had is None:
            fin.__dict__.pop("accounting", None)
        else:
            fin.accounting = self.had


def test_s95_growth_spend_violating_finance_margin_policy_is_blocked():
    db = ready_db()
    # Growth asks for a max CAC far above what one order contributes: margin policy violation.
    got = ads.propose(db, "p", daily_budget_cad=2.0, days=3, funding="etsy_plus_credit",
                      hypothesis=HYP, stop_condition=STOP, max_cac_cad=40.0, now=NOW,
                      trust_gate=TRUST_PASS)
    assert got["verdict"] == "BLOCK" and got["status"] == "FINANCE_BLOCKED", got
    assert any("max CAC" in r for r in got["reasons"])
    # Inside every ceiling: Finance's margin policy alone is what blocks it.
    assert not any(r.startswith("hard ceiling:") for r in got["reasons"]), got["reasons"]
    assert got["executed"] is False and got["owner_action_id"] is None
    assert owner_actions(db) == []  # not escalated as if approved, not self-approved
    listed = ads.proposals(db)
    assert len(listed) == 1 and listed[0]["challenge"]["verdict"] == "BLOCK"
    assert listed[0]["challenge"]["reasons"]
    s = ads.summary(db)
    assert s["proposals"]["finance_blocked"] == [listed[0]["id"]]


def test_s95_lane_e_check_spend_block_is_obeyed():
    db = ready_db()
    seen = []

    def check_spend(_db, proposal):
        seen.append(proposal)
        return {"verdict": "BLOCK", "reasons": ["cash runway below policy floor"]}

    with FakeAccounting(check_spend):
        got = ads.propose(db, "p", daily_budget_cad=1.0, days=3, funding="etsy_plus_credit",
                          hypothesis=HYP, stop_condition=STOP, now=NOW, trust_gate=TRUST_PASS)
    assert seen and seen[0]["kind"] == "ads_spend" and seen[0]["amount_cad"] == 3.0
    assert got["checker"] == ads.FINANCE_CHECK
    assert got["status"] == "FINANCE_BLOCKED"
    assert "cash runway below policy floor" in got["reasons"]
    assert owner_actions(db) == []


def test_finance_errors_and_unrecognised_answers_fail_closed():
    for fn in (lambda db, p: 1 / 0, lambda db, p: "sure", lambda db, p: {"hmm": 1}):
        db = ready_db()
        with FakeAccounting(fn):
            got = ads.propose(db, "p", daily_budget_cad=1.0, days=3,
                              funding="etsy_plus_credit", hypothesis=HYP,
                              stop_condition=STOP, now=NOW, trust_gate=TRUST_PASS)
        assert got["verdict"] == "BLOCK" and got["status"] == "FINANCE_BLOCKED", got


def test_finance_allow_cannot_lift_the_hard_ceiling():
    db = ready_db()
    with FakeAccounting(lambda db, p: {"verdict": "ALLOW", "reasons": ["fine"]}):
        got = ads.propose(db, "p", daily_budget_cad=50.0, days=10, funding="owner_cash",
                          hypothesis=HYP, stop_condition=STOP, now=NOW, trust_gate=TRUST_PASS)
    assert got["status"] == "FINANCE_BLOCKED"
    assert any(r.startswith("hard ceiling:") for r in got["reasons"])


def test_ceiling_enforced_even_with_owner_authority():
    db = ready_db()
    grant_authority(db, daily=3.0, lifetime=30.0)
    assert ads._ad_authority(db)["granted"] is True
    over_daily = ads.propose(db, "p", daily_budget_cad=5.0, days=2, funding="owner_cash",
                             hypothesis=HYP, stop_condition=STOP, now=NOW,
                             trust_gate=TRUST_PASS)
    assert over_daily["status"] == "FINANCE_BLOCKED"
    assert over_daily["ceiling"]["daily_cad"] == 3.0
    over_total = ads.propose(db, "p", daily_budget_cad=3.0, days=20, funding="owner_cash",
                             hypothesis=HYP, stop_condition=STOP, now=NOW,
                             trust_gate=TRUST_PASS)
    assert over_total["status"] == "FINANCE_BLOCKED"
    assert any("total CA$60.00 exceeds the CA$30.00" in r for r in over_total["reasons"])
    assert owner_actions(db) == []


def test_finance_cleared_proposal_becomes_gated_owner_item_not_spend():
    db = ready_db()
    got = ads.propose(db, "p", daily_budget_cad=1.0, days=5, funding="etsy_plus_credit",
                      hypothesis=HYP, stop_condition=STOP, now=NOW, trust_gate=TRUST_PASS)
    # Fallback Finance cannot verify the Plus credit balance, so it escalates (never ALLOW).
    assert got["verdict"] == "ESCALATE" and got["status"] == "AWAITING_OWNER", got
    assert any("credit balance" in r for r in got["reasons"])
    assert got["checker"].startswith("fallback:")  # lane E not merged in this branch
    acts = owner_actions(db)
    assert len(acts) == 1 and acts[0].max_cost_cad == 5.0 and not acts[0].done
    assert "no ads executor" in acts[0].action
    assert got["executed"] is False
    # Proposing the same thing again does not duplicate the owner item.
    ads.propose(db, "p", daily_budget_cad=1.0, days=5, funding="etsy_plus_credit",
                hypothesis=HYP, stop_condition=STOP, now=NOW, trust_gate=TRUST_PASS)
    assert len(owner_actions(db)) == 1


def test_lane_e_allow_routes_to_owner_with_its_checker_recorded():
    db = ready_db()
    with FakeAccounting(lambda db, p: {"verdict": "ALLOW", "reasons": ["inside policy"]}):
        got = ads.propose(db, "p", daily_budget_cad=1.0, days=5, funding="etsy_plus_credit",
                          hypothesis=HYP, stop_condition=STOP, now=NOW, trust_gate=TRUST_PASS)
    assert got["verdict"] == "ALLOW" and got["status"] == "AWAITING_OWNER", got
    assert got["checker"] == ads.FINANCE_CHECK and len(owner_actions(db)) == 1


def test_owner_cash_on_modelled_economics_escalates_with_uncertainty():
    db = ready_db()
    got = ads.propose(db, "p", daily_budget_cad=2.0, days=5, funding="owner_cash",
                      hypothesis=HYP, stop_condition=STOP, now=NOW, trust_gate=TRUST_PASS)
    assert got["verdict"] == "ESCALATE" and got["status"] == "AWAITING_OWNER", got
    assert any("refund rate UNMEASURED" in r for r in got["reasons"])


def test_unknown_economics_proposal_is_blocked():
    db = ready_db(price=0.0)
    got = ads.propose(db, "p", daily_budget_cad=1.0, days=2, funding="etsy_plus_credit",
                      hypothesis=HYP, stop_condition=STOP, max_cac_cad=1.0, now=NOW,
                      trust_gate=TRUST_PASS)
    assert got["status"] == "FINANCE_BLOCKED"
    assert any("UNKNOWN" in r for r in got["reasons"])


def test_governor_anomaly_hold_blocks_spend_proposal():
    db = ready_db()
    with db.session() as s:
        s.add(Incident(severity="P2", signature="spend-anomaly:ads", summary="TEST FIXTURE"))
    got = ads.propose(db, "p", daily_budget_cad=1.0, days=2, funding="etsy_plus_credit",
                      hypothesis=HYP, stop_condition=STOP, now=NOW, trust_gate=TRUST_PASS)
    assert got["status"] == "FINANCE_BLOCKED"
    assert any("anomaly hold" in r for r in got["reasons"])


def test_not_ready_listing_never_reaches_owner_even_if_finance_allows():
    db = fresh_db()
    add_listing(db, "p", organic=False)
    got = ads.propose(db, "p", daily_budget_cad=1.0, days=2, funding="etsy_plus_credit",
                      hypothesis=HYP, stop_condition=STOP, now=NOW, trust_gate=TRUST_PASS)
    assert got["status"] == "NOT_READY" and got["owner_action_id"] is None
    assert owner_actions(db) == []


def test_revoked_authority_refuses_on_rechallenge():
    db = ready_db()
    grant_authority(db, daily=3.0, lifetime=30.0)
    first = ads.propose(db, "p", daily_budget_cad=2.0, days=5, funding="owner_cash",
                        hypothesis=HYP, stop_condition=STOP, now=NOW, trust_gate=TRUST_PASS)
    assert first["status"] == "AWAITING_OWNER"
    with db.session() as s:
        lim = s.scalar(select(SpendLimit).where(SpendLimit.scope == "ads"))
        lim.daily_cap_cad, lim.lifetime_cap_cad = 1.0, 5.0  # owner lowers/revokes
    again = ads.rechallenge(db, first["proposal_id"], now=NOW, trust_gate=TRUST_PASS)
    assert again["status"] == "FINANCE_BLOCKED", again
    assert all(a.done for a in owner_actions(db))  # stale approval item withdrawn


def test_proposal_requires_hypothesis_and_stop_condition():
    db = ready_db()
    for h, st in (("", STOP), (HYP, " ")):
        try:
            ads.propose(db, "p", daily_budget_cad=1.0, days=2, funding="etsy_plus_credit",
                        hypothesis=h, stop_condition=st, now=NOW, trust_gate=TRUST_PASS)
        except ValueError:
            continue
        raise AssertionError("accepted a proposal without hypothesis/stop")


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            fails += 1
            print("FAIL", name, repr(e))
    print(f"{len(tests) - fails} passing, {fails} failing")
    sys.exit(1 if fails else 0)
