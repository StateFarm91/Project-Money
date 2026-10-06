"""W3 lane D: the company constitution binds Laura -- Finance, Product Truth and Security can
challenge or block her priorities and delegations, and she cannot clear their blocks (D-FB-13).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Agent, Incident, Job  # noqa: E402
from brambleloop.laura import executive  # noqa: E402
from brambleloop.laura.core import constitution  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401


def boot() -> Database:
    tmp = tempfile.mkdtemp(prefix="w3d-co-")
    db = Database(f"sqlite:///{tmp}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def laura_jobs(db) -> list:
    with db.session() as s:
        return [(j.job_type, (j.inputs or {}).get("department"))
                for j in s.scalars(select(Job)) if (j.inputs or {}).get("laura")]


def refused(fn) -> str:
    try:
        fn()
    except constitution.ChallengeRefused as e:
        return str(e)
    raise AssertionError("not refused")


def test_safe_delegation_passes_and_out_of_authority_work_is_blocked():
    db = boot()
    ok = constitution.review(db, {"department": "platform", "job_type": "ops.slo"})
    assert ok["allowed"] and ok["outcome"] == "allow", ok
    v = constitution.review(db, {"department": "store_commerce", "job_type": "store.publish"})
    assert v["outcome"] == "owner_action", v
    v = constitution.review(db, {"department": "product_truth", "job_type": "gate.certify"})
    assert not v["allowed"] and v["blocked_by"] == ["authority"], v
    v = constitution.review(db, {"department": "growth", "job_type": "ops.slo"})
    assert not v["allowed"], v                    # not growth's to generate


def test_finance_blocks_spend_and_records_its_challenge():
    db = boot()
    v = constitution.review(db, {"department": "growth", "job_type": "growth.journey",
                                 "cost_cad": 25.0, "spend_kind": "ads",
                                 "title": "boost the moss basket"})
    assert not v["allowed"] and {"finance", "authority"} <= set(v["blocked_by"]), v
    ref = [c["ref"] for c in v["checks"] if c["by"] == "finance" and c["ref"]]
    assert ref and ref[0].startswith("acct_challenges:fin-"), v["checks"]
    from brambleloop.finance.accounting.models import AcctChallenge

    with db.session() as s:
        row = s.scalar(select(AcctChallenge).where(
            AcctChallenge.challenge_id == ref[0].split(":", 1)[1]))
        assert row is not None and row.proposer == "laura" and row.verdict != "cleared"


def test_a_finance_challenge_blocks_her_tick_until_finance_resolves_it():
    db = boot()
    cid = constitution.challenge(db, raised_by="finance",
                                 reason="books not reconciled; hold all new work",
                                 evidence=["acct_exceptions:1"])
    r = executive.tick(db)
    assert r["delegated"] == 0, r["outcomes"]
    assert laura_jobs(db) == []
    blocked = executive.history(db, kind="blocked", limit=50)
    assert blocked and all("finance challenge" in b["reason"] for b in blocked), blocked
    assert any(f"laura_challenges:{cid}" in b["refs"] for b in blocked)
    assert {p["status"] for p in executive.priorities(db)
            if p["job_type"]} == {"blocked"}
    # Laura cannot clear it; another blocker cannot either; Finance can
    assert "Laura cannot clear" in refused(lambda: constitution.resolve_challenge(
        db, cid, resolved_by="laura", resolution="I disagree"))
    refused(lambda: constitution.resolve_challenge(db, cid, resolved_by="security",
                                                   resolution="x"))
    constitution.resolve_challenge(db, cid, resolved_by="finance", resolution="reconciled")
    r = executive.tick(db)
    assert r["delegated"] >= 1 and laura_jobs(db), r["outcomes"]


def test_product_truth_halt_blocks_product_forward_work_only():
    db = boot()
    with db.session() as s:
        s.add(Incident(severity="P1", signature="gate_e.chart_mismatch", product_slug="moss",
                       summary="chart and rows disagree", halts_publication=True))
    v = constitution.review(db, {"department": "store_commerce", "job_type": "seo.cycle"})
    assert not v["allowed"] and v["blocked_by"] == ["product_truth"], v
    for dept, jt in (("product_truth", "ops.sentinel"), ("platform", "ops.slo"),
                     ("finance", "finance.reconcile")):
        assert constitution.review(db, {"department": dept, "job_type": jt})["allowed"], dept
    r = executive.tick(db)
    jobs = laura_jobs(db)
    assert ("ops.sentinel", "product_truth") in jobs, jobs              # Laura sends it to Product Truth
    assert not [j for j in jobs if j[0] in ("seo.cycle", "marketing.ads_readiness",
                                            "visual.identity_drift")], jobs
    pt = [b for b in executive.history(db, kind="blocked", limit=50)
          if "Product Truth" in b["reason"]]
    assert pt, executive.history(db, kind="blocked", limit=50)


def test_an_explicit_product_truth_challenge_scoped_to_a_job_type():
    db = boot()
    constitution.challenge(db, raised_by="product_truth", reason="SEO copy overstates the chart",
                           scope={"job_type": "seo.cycle"})
    assert not constitution.review(db, {"department": "store_commerce",
                                        "job_type": "seo.cycle"})["allowed"]
    assert constitution.review(db, {"department": "store_commerce",
                                    "job_type": "seasonal.remerchandising"})["allowed"]


def test_security_blocks_all_but_monitoring_and_respects_pauses():
    db = boot()
    with db.session() as s:
        s.add(Incident(severity="P0", signature="authority_chain_tamper:store.activate",
                       summary="authority chain seal mismatch"))
    v = constitution.review(db, {"department": "growth", "job_type": "growth.journey"})
    assert not v["allowed"] and v["blocked_by"] == ["security"], v
    for dept, jt in (("platform", "ops.slo"), ("product_truth", "ops.sentinel"),
                     ("finance", "finance.reconcile")):
        assert constitution.review(db, {"department": dept, "job_type": jt})["allowed"], dept
    # an emergency-paused agent is never routed around
    db2 = boot()
    with db2.session() as s:
        s.scalar(select(Agent).where(Agent.name == "growth")).enabled = False
    v = constitution.review(db2, {"department": "growth", "job_type": "growth.journey"})
    assert not v["allowed"] and "security" in v["blocked_by"], v


def test_only_the_three_constitutional_blockers_can_challenge():
    db = boot()
    for who in ("laura", "coo", "growth", "learn"):
        refused(lambda w=who: constitution.challenge(db, raised_by=w, reason="because"))
    cid = constitution.challenge(db, raised_by="security", reason="token rotation in progress")
    assert [c["id"] for c in constitution.open_challenges(db)] == [cid]
    constitution.resolve_challenge(db, cid, resolved_by="owner", resolution="rotated")
    assert constitution.open_challenges(db) == []


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
