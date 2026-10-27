"""W4-PLACT: the owner's 2026-10-13 Private Laura decisions (DECISION_LOG D-W4-PL-3).

1. SEPARATE BUDGET. Private replies are billed to their own agent `laura_private` (CA$0.50/day),
   independent of Business Laura's CA$0.50/day (`laura`, the CEO briefing). Both sit inside the
   unchanged CA$100 monthly ceiling. The owner's figure BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD is
   capped at the agent ceiling and is enforced ATOMICALLY with the reservation (security review
   L1: it used to be read outside `budget_lock` and reserved separately).
2. IDENTITY / CONSENT. No human-consent prerequisite (OA-PL-3 removed): Private Laura is
   Brambleloop's established AI persona. Truthful AI representation is kept.
3. STATUS. The owner-only `/api/cc/private/status` lists each activation prerequisite as met or
   unmet, with no secret values.

Stubbed transport (no network, no spend); neutral sentinels only.
Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_plact.py
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import w3_laura_cc_harness as H  # noqa: E402  (isolated DB, no network, no provider keys)
import w4_pl_harness as PL  # noqa: E402
from w3_laura_memory_harness import fresh_db  # noqa: E402

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import (DEFAULT_AGENTS, Registry, ceiling_audit,  # noqa: E402
                                         declared_daily_ceiling)
from brambleloop.app.command_center import private_context  # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry, SpendReservation  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.gateway import laura_briefing  # noqa: E402
from brambleloop.gateway import laura_register as LR  # noqa: E402
from brambleloop.gateway import routing  # noqa: E402
from brambleloop.laura.private import _testkit as kit  # noqa: E402
from brambleloop.ops import release_record  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
USER = LR.render_user(facts=[("PRIV-LABEL-PLACT", "PRIV-SENTINEL-PLACT-1")],
                      turns=[("owner", "PRIV-SENTINEL-PLACT-2")],
                      message="PRIV-SENTINEL-PLACT-3")
BRIEFING = laura_briefing.PROMPT.ref
kit.set_key(kit.new_key())


def _db():
    db = fresh_db()
    Registry(db).seed_defaults()
    return db


def _estimate() -> float:
    """The exact pre-call estimate `laura_register._reply` reserves for USER (INTEG5: the
    private register runs on Venice, so this is Venice's estimate for the pinned model)."""
    from brambleloop.gateway import venice as V

    return V.estimate_for(LR.PROMPT.system, USER, int(LR.PROMPT.max_output_tokens), V.MODEL)


def _call(db):
    try:
        return LR.reply(db, system=LR.PROMPT.system, user=USER)["text"]
    except LR.ReplyUnavailable as exc:
        return exc.code


def _bill(db, agent: str, amount: float, purpose: str) -> None:
    with db.session() as s:
        s.add(CostEntry(agent=agent, amount_cad=amount, kind="llm", purpose=purpose,
                        provider="anthropic", model="claude-sonnet-5"))


def _refusals(db) -> list:
    with db.session() as s:
        return list(s.scalars(select(AuditLog).where(AuditLog.action == "spend.refused")))


def _briefing_check(db, estimate: float = 0.02) -> dict:
    """The gate the CEO briefing's paid call goes through: agent `laura`, its pinned purpose."""
    return gw.check_budget_cad(db, estimate_cad=estimate, agent=laura_briefing.AGENT,
                               purpose=BRIEFING, model="claude-sonnet-5",
                               provider="anthropic")


# ---------------------------------------------------------------- 1. separate budget

def test_laura_private_is_its_own_agent_with_its_own_ceiling():
    spec = next(a for a in DEFAULT_AGENTS if a["name"] == "laura_private")
    assert spec["daily_cost_ceiling_cad"] == 0.50 and spec["allowed_job_types"] == []
    assert declared_daily_ceiling("laura") == 0.50                    # Business Laura unchanged
    assert LR.AGENT == "laura_private" != laura_briefing.AGENT == "laura"
    assert gw._policy_ceiling() == 100.0                               # no other limit changed
    db = _db()
    assert Registry(db).get("laura_private").daily_cost_ceiling_cad == 0.50
    # The owner switch is capped at the agent ceiling and can only tighten it.
    assert LR.daily_authorisation_cad({LR.DAILY_AUTH_ENV: "5"}) == 0.50
    assert LR.daily_authorisation_cad({LR.DAILY_AUTH_ENV: "0.30"}) == 0.30
    assert LR.daily_authorisation_cad({LR.DAILY_AUTH_ENV: "0"}) == 0.0


def test_private_spend_never_consumes_the_briefing_budget_and_vice_versa():
    # (a) Business Laura's day is all but spent on the briefing: a private reply still runs,
    #     billed to laura_private, and Business Laura's spend is unchanged.
    db = _db()
    _bill(db, "laura", 0.499, BRIEFING)
    with PL.enabled(PL.Stub(), **{LR.DAILY_AUTH_ENV: "0.50"}):
        assert _call(db) == PL.REPLY
    laura_day = gw.agent_daily_ceiling(db, "laura")
    priv_day = gw.agent_daily_ceiling(db, "laura_private")
    assert abs(laura_day["spent_today_cad"] - 0.499) < 1e-9, laura_day
    assert 0 < priv_day["spent_today_cad"] < 0.05, priv_day
    try:
        _briefing_check(db)
        raise AssertionError("the briefing used budget that is not Business Laura's")
    except gw.AgentCeilingExceeded:
        pass                               # its own day is full; the private spend did not help
    # (b) The private day is spent: private replies are refused pre-call, and the briefing's
    #     own CA$0.50 is untouched -- its check passes and reserves under agent `laura`.
    db2 = _db()
    _bill(db2, "laura_private", 0.499, LR.PURPOSE)
    with PL.enabled(None, **{LR.DAILY_AUTH_ENV: "0.50"}):
        assert _call(db2) == "SPEND_CEILING"
    ok = _briefing_check(db2)
    assert ok["reservation_id"] and ok["agent_permission"]["agent"] == "laura"
    assert ok["agent_permission"]["spent_today_cad"] == 0.0, ok["agent_permission"]
    with db2.session() as s:
        held = list(s.scalars(select(SpendReservation)))
    assert [(r.agent, r.purpose) for r in held] == [("laura", BRIEFING)], held
    which = [(r.actor, r.detail["which"]) for r in _refusals(db2)]
    assert which == [("laura_private", "agent_daily_ceiling")], which


def _race(db, cap: str) -> tuple[list, PL.Stub]:
    """Two private turns released together; the first one in holds the model call open."""
    gate = threading.Event()
    results: list = []
    barrier = threading.Barrier(2)

    entered: list = []

    class Slow(PL.Stub):
        def __call__(self, *args):
            entered.append(1)
            gate.wait(10)                     # in flight: its reservation is live
            return super().__call__(*args)

    stub = Slow()

    def turn():
        barrier.wait(5)
        results.append(_call(db))

    with PL.enabled(stub, **{LR.DAILY_AUTH_ENV: cap}):
        ts = [threading.Thread(target=turn) for _ in range(2)]
        for t in ts:
            t.start()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not (results or len(entered) >= 2):
            time.sleep(0.02)
        gate.set()
        for t in ts:
            t.join(20)
    return results, stub


def test_two_concurrent_private_turns_cannot_both_pass_the_cap():
    est = _estimate()
    assert est > 0
    # (a) The owner's figure fits one call's estimate but not two.
    db = _db()
    results, stub = _race(db, f"{est * 1.5:.6f}")
    assert sorted(results, key=str) == sorted([PL.REPLY, "SPEND_CEILING"], key=str), results
    assert len(stub.calls) == 1, len(stub.calls)            # only one reached the provider
    assert [r.detail["which"] for r in _refusals(db)] == ["purpose_daily_authorisation"]
    # (b) The laura_private agent ceiling itself (owner figure at the ceiling): its remaining
    #     room fits one call, not two.
    db2 = _db()
    _bill(db2, "laura_private", round(0.50 - est * 1.5, 6), LR.PURPOSE)
    results, stub = _race(db2, "0.50")
    assert sorted(results, key=str) == sorted([PL.REPLY, "SPEND_CEILING"], key=str), results
    assert len(stub.calls) == 1, len(stub.calls)
    assert [r.detail["which"] for r in _refusals(db2)] == ["agent_daily_ceiling"]
    # Positive control: with room for both, both reply (the race harness is not rigged).
    db3 = _db()
    results, stub = _race(db3, "0.50")
    assert results == [PL.REPLY, PL.REPLY] and len(stub.calls) == 2, results


def test_the_monthly_ceiling_binds_both():
    ceiling = gw.monthly_ceiling_cad()
    assert ceiling <= 100.0
    db = _db()
    _bill(db, "orchestrator", ceiling - 0.001, "concept_generation")
    with PL.enabled(None, **{LR.DAILY_AUTH_ENV: "0.50"}):
        assert _call(db) == "BUDGET"
    try:
        _briefing_check(db)
        raise AssertionError("the briefing passed a spent month")
    except gw.AgentCeilingExceeded:
        raise AssertionError("the month, not the day, must refuse the briefing")
    except gw.BudgetExceeded:
        pass
    whiches = [(r.actor, r.detail["which"]) for r in _refusals(db)]
    assert whiches == [("laura_private", "monthly_ceiling"), ("laura", "monthly_ceiling")], whiches
    # One shared month: a private reservation in flight is counted against the briefing.
    db2 = _db()
    est = _estimate()
    _bill(db2, "orchestrator", ceiling - est * 1.5, "concept_generation")
    held = gw.check_budget_cad(db2, estimate_cad=est, agent="laura_private",
                               purpose=LR.PURPOSE, model="claude-sonnet-5",
                               provider="anthropic", agent_daily_cap_cad=0.50,
                               holder="private-turn")
    assert held["reservation_id"]
    try:
        _briefing_check(db2, estimate=est)
        raise AssertionError("the briefing ignored a live private reservation")
    except gw.AgentCeilingExceeded:
        raise AssertionError("expected the monthly ceiling")
    except gw.BudgetExceeded:
        pass


def test_agent_daily_cap_only_tightens_and_fails_closed():
    db = _db()
    # Above the agent ceiling: the ceiling still binds.
    _bill(db, "laura_private", 0.49, LR.PURPOSE)
    for cap in (5.0, float("inf")):
        try:
            gw.check_budget_cad(db, estimate_cad=0.02, agent="laura_private",
                                purpose=LR.PURPOSE, agent_daily_cap_cad=cap, reserve=False)
            raise AssertionError(f"cap {cap} lifted the agent ceiling")
        except gw.AgentCeilingExceeded:
            pass
    # NaN / negative / garbage read as CA$0; an unregistered agent with a cap is refused.
    db2 = _db()
    for cap in (float("nan"), -1.0, "abc"):
        try:
            gw.check_budget_cad(db2, estimate_cad=0.01, agent="laura_private",
                                purpose=LR.PURPOSE, agent_daily_cap_cad=cap, reserve=False)
            raise AssertionError(f"cap {cap!r} was read as room")
        except gw.AgentCeilingExceeded:
            pass
    try:
        gw.check_budget_cad(db2, estimate_cad=0.01, agent="nobody_registered",
                            purpose=LR.PURPOSE, agent_daily_cap_cad=0.50, reserve=False)
        raise AssertionError("an unregistered agent with a cap was unchecked")
    except gw.AgentCeilingExceeded:
        pass
    # Without a cap, every other caller is unchanged (None = no tightening).
    ok = gw.check_budget_cad(db2, estimate_cad=0.01, agent="laura", purpose=BRIEFING,
                             reserve=False)
    assert ok["agent_permission"]["daily_ceiling_cad"] == 0.50


def test_verify_every_agent_has_a_cost_ceiling_stays_green():
    from brambleloop.core.models import Agent
    from brambleloop.finance.spend_report import per_agent_today

    db = _db()
    with PL.enabled(PL.Stub(), **{LR.DAILY_AUTH_ENV: "0.50"}):
        assert _call(db) == PL.REPLY                     # laura_private has spent today
    with db.session() as s:
        agents = list(s.scalars(select(Agent)))
    assert "laura_private" in {a.name for a in agents}
    today = per_agent_today(db)
    # Exactly the inputs `/api/verify` builds (app/main.py, every_agent_has_a_cost_ceiling).
    out = ceiling_audit([(a.name, a.daily_cost_ceiling_cad) for a in agents],
                        {r["agent"]: r["spent_today_cad"] for r in today["agents"]})
    assert out["ok"] is True, out
    assert out["misconfigured"] == [] and out["no_spend_agents_that_spent_today"] == []
    assert "laura_private" not in out["declared_no_spend"]
    assert "laura_private" not in [r["agent"] for r in today["over"]], today["over"]


# ---------------------------------------------------------------- 2. identity / consent

def test_no_consent_prerequisite_and_truthful_ai_representation_kept():
    from brambleloop.laura.agency import roadmap

    row = next(r for r in roadmap.ROWS if r["id"] == "LAURA-PRIVATE-REGISTER")
    surfaces = {
        "roadmap": json.dumps(row),
        "REPLY_GATED": private_context.REPLY_GATED,
        "REPLY_ENABLED": private_context.REPLY_ENABLED,
        "reasons": json.dumps(LR.REASONS),
        "laura.js": (ROOT / "src/brambleloop/app/command_center/static/js/views/laura.js")
        .read_text(encoding="utf-8").split("function privatePrereqs")[1].split("export")[0],
        "prerequisites": json.dumps(private_context.prerequisites(_db(), boot={})),
    }
    assert len(surfaces) == 6 and all(surfaces.values()), surfaces
    for name, text in surfaces.items():
        low = text.lower()
        assert "oa-pl-3" not in low and "human laura's consent" not in low, name
        assert "consent attest" not in low, name
    board = (ROOT / "research/final_build/w4/completion_board_final.py").read_text("utf-8")
    assert "OA-PL-3 attest" not in board and "human Laura's \"\n" not in board
    # Truthful AI representation stays in the pinned prompt (W4-VENICE: @2 keeps every @1
    # sentence verbatim and adds explicit guardrails; @1 stays registered, unchanged).
    p = LR.PROMPT.system
    assert LR.PURPOSE == "laura.private_reply@3"        # W4-VENICE adult WIP (PROPOSED ruling)
    assert LR.LAURA_PRIVATE_REPLY_V1.ref == "laura.private_reply@1"
    assert LR.LAURA_PRIVATE_REPLY_V2.system == LR._system_v2()
    assert LR.LAURA_PRIVATE_REPLY_V1.system == LR._system_v1()
    for clause in ("You are an AI. Never claim or imply that you are human",
                   "never claim a body, a physical action or a place",
                   "Never state or imply consent, a signature, an identity verification or a "
                   "physical act on behalf of"):
        assert clause in p, clause
    # D-W4-PL-3 records the clarification verbatim; D-W4-PL-2 stays UNRESOLVED.
    log = (ROOT / "DECISION_LOG.md").read_text(encoding="utf-8")
    entry = " ".join(log[log.index("## D-W4-PL-3"):].split())
    assert ("\"Private Laura is Brambleloop's established AI persona, not an impersonation of "
            "a real person.\"") in entry
    assert "never claims to be human" in entry and "D-W4-PL-2 stays unresolved" in entry
    pl2 = log[log.index("## D-W4-PL-2"):log.index("## D-W4-VISROLE")]
    assert "UNRESOLVED" in pl2


# ---------------------------------------------------------------- 3. status

# W4-VENICE (D-W4-PL-VENICE) adds `private_provider_venice`: one more prerequisite, never fewer.
IDS = ["key_configured", "register_switch", "daily_cad_set", "laura_private_agent",
       "private_provider_venice", "current_release_deployed"]


def _met(prereq) -> dict:
    return {p["id"]: p["met"] for p in prereq}


def test_status_reports_each_prerequisite_met_or_unmet_without_secrets():
    secret_key = os.environ.get("BRAMBLELOOP_PRIVATE_MEMORY_KEY") or ""
    assert secret_key
    c, csrf = H.session()
    st = c.get("/api/cc/private/status").json()
    assert [p["id"] for p in st["prerequisites"]] == IDS, st["prerequisites"]
    m = _met(st["prerequisites"])
    assert m == {"key_configured": True, "register_switch": False, "daily_cad_set": False,
                 "laura_private_agent": True, "private_provider_venice": False,
                 "current_release_deployed": False}, m
    assert st["prerequisites_met"] is False
    # Turn each owner prerequisite on and watch it flip; then a proven deployed release.
    commit = "1b21e81c6d1b228a93f72be44cfdf8193740b61b"
    saved_boot = dict(release_record.BOOT)
    try:
        with PL.enabled(None, release_proven=None,   # the real boot-guard check (INTEG3)
                        **{LR.DAILY_AUTH_ENV: "0.25", "RAILWAY_GIT_COMMIT_SHA": commit,
                           "BRAMBLELOOP_PRIVATE_PROVIDER": "venice",
                           "VENICE_API_KEY": PL.DUMMY_KEY}):
            release_record.BOOT.clear()
            release_record.BOOT.update({"ok": True, "platform_markers": ["RAILWAY_GIT_COMMIT_SHA"],
                                        "record": {"file": "RELEASE_x.json", "sha": "x"}})
            r = c.get("/api/cc/private/status")
            st = r.json()
            body = r.text
        assert all(_met(st["prerequisites"]).values()), st["prerequisites"]
        assert st["prerequisites_met"] is True and st["reply_register"] == "ENABLED"
        assert "1b21e81c6d1b" in body and commit not in body          # short sha only
        assert secret_key not in body and PL.DUMMY_KEY not in body     # names, never values
        # A build the boot guard did not prove is unmet, never assumed.
        release_record.BOOT.update({"ok": False})
        rel = private_context._release_deployed(env={"RAILWAY_GIT_COMMIT_SHA": commit})
        assert rel["met"] is False and "no committed release record" in rel["detail"]
        assert private_context._release_deployed(boot={"ok": True,
                                                       "platform_markers": ["X"]},
                                                 env={})["met"] is False   # unknown commit
    finally:
        release_record.BOOT.clear()
        release_record.BOOT.update(saved_boot)
    # The agent prerequisite reads the registry, not the code: a missing row is unmet.
    db = _db()
    assert _met(private_context.prerequisites(db, boot={}))["laura_private_agent"] is True
    from brambleloop.core.models import Agent
    with db.session() as s:
        s.delete(s.scalars(select(Agent).where(Agent.name == "laura_private")).one())
    assert _met(private_context.prerequisites(db, boot={}))["laura_private_agent"] is False
    # Owner-only: no session, no status.
    anon = H.client()
    assert anon.get("/api/cc/private/status").status_code in (401, 403)


if __name__ == "__main__":
    H.run(globals())
