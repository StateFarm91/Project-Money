"""W4-LAURACEO: Business Laura as a model-backed AI CEO (ADD-LCEO-01..07, D-W4-LAURA-CEO).

The nine CEO acceptance steps of ADD-LCEO-07, proven OFFLINE with a stubbed model transport
(no network, no API key; the harness refuses sockets). Production acceptance needs the real
calls in research/final_build/w4/LAURACEO.md section 5 -- these tests do not claim it.

  1 greeting answered naturally by the model (not a template, not UNKNOWN)
  2 accurate company status, grounded: cited records exist; an invented figure is withheld
  3 a genuine priority: executive questions route to the stronger tier; the tick's priority
    order can be chosen by the model among code-authorised candidates only
  4 delegation creates REAL jobs (tick -> COO mission; conversation -> confirmed follow-on)
  5 the result is received and evaluated (review decision + cost of the outcome)
  6 a correction is requested with feedback, bounded (one rework, then a Lesson)
  7 timeline and memory are updated (decisions, report, owner-stated business memory)
  8 the outcome and its costs are reported (timeline report, costs summary, API)
  9 a protected action stops and becomes an owner approval card, never a job
plus: templates are never the conversational reply; budget enforcement; no Private Laura data.

Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_laura_ceo.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit

import json
import re
import tempfile
from datetime import datetime, timezone

import w3_laura_cc_harness as H  # noqa: E402  (isolated environment, network refused)

from sqlalchemy import delete, func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy import charters, memory as company  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, CostEntry, Job, JobStatus, Lesson,  # noqa: E402
                                     OwnerAction)
from brambleloop.finance import spend_policy  # noqa: E402
from brambleloop.gateway import laura_converse as lc, routing  # noqa: E402
from brambleloop.gateway.model_gateway import EchoProvider  # noqa: E402
from brambleloop.laura import executive  # noqa: E402
from brambleloop.laura import memory as lm  # noqa: E402
from brambleloop.laura.agency import ceo_chat, costs, followon, talk  # noqa: E402
from brambleloop.laura.agency.models import LauraCostEvent, LauraTurn  # noqa: E402
from brambleloop.laura.executive import loop  # noqa: E402

import os  # noqa: E402

# Integration review S-1: Business Laura's model paths are behind an owner switch (default
# OFF). These suites exercise the ON behaviour; `test_ceo_model_switch_off_makes_no_model_call`
# proves OFF.
os.environ["BRAMBLELOOP_LAURA_CEO_MODEL"] = "1"
DB = H.DB
IDS = H.seed_company()
_EV = re.compile(r"^E(\d+) \| ([^|]*) \| ([^|]*) \| (.*)$", re.M)


def _evidence(user: str) -> list[tuple[str, str, str]]:
    return [(f"E{m.group(1)}", m.group(3).strip(), m.group(4).strip())
            for m in _EV.finditer(user)]


def factory(reply_fn, calls: list | None = None, prompts_seen: list | None = None):
    """A transport stand-in: the gateway, reservation, billing and validation are real."""
    def make(model):
        def scripted(system, user):
            if calls is not None:
                calls.append(model)
            if prompts_seen is not None:
                prompts_seen.append((system, user))
            return json.dumps(reply_fn(system, user))
        return EchoProvider(name="anthropic", model=model, cost_per_1k_input_cad=0.001,
                            cost_per_1k_output_cad=0.005, scripted=scripted)
    return make


def cite_first(keyword: str, prefix: str = "From the records: "):
    def fn(system, user):
        for eid, src, stmt in _evidence(user):
            if keyword.lower() in (stmt + " " + src).lower():
                return {"reply": prefix + stmt, "citations": [eid], "offer": [],
                        "remember": ""}
        return {"reply": "I don't have a record that answers that yet.", "citations": []}
    return fn


def _turn(tid):
    with DB.session() as s:
        r = s.get(LauraTurn, tid)
        s.expunge(r)
        return r


# ---- 1. greeting ------------------------------------------------------------------------

def test_step1_greeting_is_a_natural_model_reply_not_a_template():
    calls: list = []
    reply = {"reply": "Good morning! I'm here and the company is ticking along -- there is "
                      "an owner decision waiting for you when you have a minute.",
             "citations": ["E1"], "remember": ""}
    r = ceo_chat.converse(DB, "Good morning Laura, how are you today?",
                          session_public_id="s_greet",
                          provider_factory=factory(lambda s, u: reply, calls))
    assert calls == [routing.TIERS[routing.CHEAP].model], calls     # the cheap tier
    assert r["status"] in ("ANSWERED", "PARTIAL"), r
    assert r["answer"] == reply["reply"], r["answer"]
    assert r["model"]["source"] == "model" and r["model"]["task"] == "laura.converse"
    tmpl = talk.converse(DB, "Good morning Laura, how are you today?", persist=False)
    assert r["answer"] != tmpl["answer"] and not r["answer"].startswith("UNKNOWN")
    assert r["method"].startswith("model ") and "laura.converse@1" in r["method"]
    row = _turn(r["turn_id"])
    assert row.answer == reply["reply"] and row.intent.startswith("ceo:")
    # the greeting is still grounded: the headline pack was offered as evidence
    assert r["evidence_offered"] >= 1 and r["facts"], r


# ---- 2. accurate company status ----------------------------------------------------------

def test_step2_status_is_grounded_and_an_invented_figure_is_withheld():
    r = ceo_chat.converse(DB, "Laura, what did your company do overnight?",
                          session_public_id="s_status",
                          provider_factory=factory(cite_first("seasonal.sentinel")))
    assert r["status"] in ("ANSWERED", "PARTIAL"), r
    assert r["facts"] and all(f.get("source") for f in r["facts"]), r["facts"]
    assert any("seasonal.sentinel" in f["statement"] or "seasonal.sentinel" in f["source"]
               for f in r["facts"]), r["facts"]
    # an invented figure: deterministic validation wins over the model
    bad = {"reply": "We sold 4,812 patterns overnight and made CA$9,300.", "citations": []}
    r2 = ceo_chat.converse(DB, "How much did we sell overnight?", session_public_id="s_status",
                           provider_factory=factory(lambda s, u: bad))
    assert r2["status"] == ceo_chat.WITHHELD, r2
    assert "4812" not in r2["answer"].replace(",", "") and "9300" not in r2["answer"]
    assert "withheld" in r2["answer"]
    # a claim to be human is withheld too (D-FB-12)
    human = {"reply": "I'm a human founder, of course.", "citations": []}
    r3 = ceo_chat.converse(DB, "Are you a person?", session_public_id="s_status",
                           provider_factory=factory(lambda s, u: human))
    assert r3["status"] == ceo_chat.WITHHELD and "human" in r3["answer"]


def test_validation_matches_the_same_figure_but_never_a_new_one():
    vals = {"evidence": "E1 | 2026-10-20T03:49:00+00:00 | cost_entries | Laura's daily budget "
                        "CA$0.50; 1,204 jobs", "unknowns": "", "memory": "", "history": "",
            "proposals": "", "today": "2026-10-20", "identity": ""}
    ok, why = ceo_chat.validate({"reply": "Budget is CA$0.5 a day; 1204 jobs ran by 03:49.\n"
                                          "1. keep going", "citations": ["E1", "E9", "x"]},
                                question="status?", vals=vals, n_facts=1, n_props=0)
    assert ok and ok["citations"] == [1], (ok, why)
    bad, why = ceo_chat.validate({"reply": "We earned CA$0.75 from 1205 jobs."},
                                 question="status?", vals=vals, n_facts=1, n_props=0)
    assert bad is None and "2 figure(s)" in why, why
    assert "0.75" not in why and "1205" not in why


# ---- 3. a genuine priority ---------------------------------------------------------------

def test_step3_executive_reasoning_uses_the_stronger_tier_and_names_a_real_priority():
    calls: list = []
    r = ceo_chat.converse(DB, "What should we prioritise this week, and why?",
                          session_public_id="s_prio",
                          provider_factory=factory(cite_first("confirm the public shop name",
                                                              "My priority: "), calls))
    assert calls == [routing.TIERS[routing.STANDARD].model], calls
    assert r["model"]["task"] == "laura.executive" and r["status"] in ("ANSWERED", "PARTIAL")
    assert "confirm the public shop name" in r["answer"].lower(), r["answer"]
    assert any(f["source"].startswith(("owner_actions", "build2")) or "owner" in f["source"]
               for f in r["facts"]), r["facts"]


def _boot() -> Database:
    tmp = tempfile.mkdtemp(prefix="w4-lceo-")
    db = Database(f"sqlite:///{tmp}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _jobs(db):
    with db.session() as s:
        rows = list(s.scalars(select(Job)))
        for r in rows:
            s.expunge(r)
    return rows


def test_step3_the_tick_lets_the_model_order_only_authorised_priorities():
    db = _boot()
    seen: list = []

    def rank(system, user):
        ids = re.findall(r"^(C\d+) \|", user, re.M)
        seen.append(ids)
        return {"order": list(reversed(ids)) + ["C99", "X1"], "why": "test order"}

    r = executive.tick(db, provider_factory=factory(rank))
    assert seen and len(seen[0]) >= 2, seen
    assert r["ranking"]["source"] == "model", r["ranking"]
    assert r["cognition"]["engine"] == "deterministic+model-ranked"
    # invented ids were ignored; every delegated job is still inside SAFE_GENERATED
    lj = [j for j in _jobs(db) if (j.inputs or {}).get("laura")]
    assert lj and all(j.job_type in charters.SAFE_GENERATED for j in lj)
    assert not [j for j in _jobs(db) if j.job_type in charters.PROTECTED_JOB_TYPES]
    # bounded cadence: at most EXEC_RANK_PER_DAY model orderings per UTC day
    for _ in range(loop.EXEC_RANK_PER_DAY + 2):
        executive.tick(db, provider_factory=factory(rank))
    assert len(seen) <= loop.EXEC_RANK_PER_DAY, len(seen)
    with db.session() as s:
        n = s.scalar(select(func.count(LauraCostEvent.id)).where(
            LauraCostEvent.kind == "decision"))
    assert n == len(seen) and n <= loop.EXEC_RANK_PER_DAY


# ---- 4-8. delegation, evaluation, correction, timeline/memory, report --------------------

def _finish(db, job_id, *, status, outputs=None, error=""):
    with db.session() as s:
        j = s.get(Job, job_id)
        j.status = status
        j.outputs = outputs or {}
        j.last_error = error
        j.finished_at = datetime.now(timezone.utc)


def _mission_job(db, decision) -> Job:
    mkey = decision["key"].split(":", 1)[1]
    jid = company.get(db, mkey)["body"]["job_id"]
    with db.session() as s:
        j = s.get(Job, jid)
        s.expunge(j)
    return j


def test_steps4_to_8_delegate_evaluate_correct_record_and_report_with_costs():
    db = _boot()
    executive.tick(db)
    ds = executive.history(db, kind="delegation", limit=50)
    assert len(ds) >= 2, ds
    # 4: real jobs on the real queue, carrying Laura's priority
    good, bad = _mission_job(db, ds[0]), _mission_job(db, ds[1])
    assert good.status == JobStatus.PENDING and (good.inputs or {}).get("laura")
    # a delegated job that billed a model call: its cost is attributed to the outcome
    with db.session() as s:
        s.add(CostEntry(agent=good.agent, job_id=good.id, kind="llm", amount_cad=0.0123,
                        purpose="test@1"))
    _finish(db, good.id, status=JobStatus.DONE, outputs={"ran": True, "work_done": 2})
    _finish(db, bad.id, status=JobStatus.DEAD, error="RuntimeError: reader broke")
    r = executive.tick(db)
    # 5: received and evaluated
    assert r["review"]["accepted"] >= 1 and r["review"]["failed"] == 1, r["review"]
    reviews = executive.history(db, kind="review", limit=20)
    assert any(x["subject"].endswith("-> useful") for x in reviews)
    # 6: a correction with Laura's feedback, bounded
    rw = executive.history(db, kind="rework", limit=5)
    assert len(rw) == 1, rw
    rj = _mission_job(db, rw[0])
    fb = (rj.inputs or {})["laura"]["feedback"]
    assert fb["verdict"] == "failed" and fb["attempt"] == 1 and fb["max_corrections"] == 1
    assert "reader broke" in fb["error"] and fb["criteria"] == list(loop.REVIEW_CRITERIA)
    _finish(db, rj.id, status=JobStatus.DEAD, error="RuntimeError: still broken")
    executive.tick(db)
    assert len(executive.history(db, kind="escalation", limit=5)) == 1
    assert len(executive.history(db, kind="rework", limit=5)) == 1          # no loop
    with db.session() as s:
        assert s.scalar(select(func.count(Lesson.id)).where(
            Lesson.subject.like("Laura escalation%"))) == 1
    # 7: timeline + memory
    ev = [e for e in company.events(db, limit=300) if e["actor"] == "laura"]
    kinds = {e["kind"] for e in ev}
    assert {"laura.delegation", "laura.review", "laura.rework"} <= kinds, kinds
    # 8: the report, with costs per unit of work
    assert "laura.report" in kinds, kinds
    rep = [e for e in ev if e["kind"] == "laura.report"][0]
    assert "Costs (24 h)" in rep["summary"] and "per successful outcome" in rep["summary"]
    entries = lm.read(db, "operational", "report/*", lm.Principal.laura())
    assert entries and "costs" in entries[0]["value"], entries
    c = costs.summary(db, days=1)
    assert c["outcome"]["useful"] >= 1 and c["outcome"]["failed"] >= 1, c["outcome"]
    assert c["delegation"]["total_cad"] is not None and c["delegation"]["total_cad"] >= 0.0123
    assert c["outcome"]["per_successful_outcome_cad"] is not None
    # an unknown job's cost is UNKNOWN, never 0
    assert costs.job_cost(db, 999999) == (None, 0)


def test_step4_conversation_delegation_creates_a_real_job_after_confirmation():
    def offer(system, user):
        pid = re.search(r"^(P\d+) \| mission", user, re.M)
        return {"reply": "I'll hand that to Product & Design once you confirm.",
                "citations": [], "offer": [pid.group(1)] if pid else []}

    r = ceo_chat.converse(DB, "I don't like that banner. Have Design make three more.",
                          session_public_id="s_deleg", provider_factory=factory(offer))
    props = [p for p in r["proposals"] if p["kind"] == "mission"]
    assert props and props[0].get("delegation"), r["proposals"]
    with DB.session() as s:
        before = s.scalar(select(func.count(Job.id)))
    out = followon.create(DB, r["turn_id"], props[0]["key"], confirmed_by="owner-test",
                          stepped_up=False)
    assert out["kind"] == "mission" and out["result_ref"].startswith("jobs:"), out
    with DB.session() as s:
        j = s.get(Job, int(out["result_ref"].split(":")[1]))
        assert j is not None and j.job_type in charters.SAFE_GENERATED
        assert s.scalar(select(func.count(Job.id))) == before + 1


# ---- 9. protected actions stop -----------------------------------------------------------

def test_step9_a_protected_action_stops_and_becomes_an_owner_approval_card():
    r = ceo_chat.converse(DB, "Have the store publish harbour-shawl on Etsy now.",
                          session_public_id="s_prot",
                          provider_factory=factory(lambda s, u: {
                              "reply": "Publishing is your decision; I've prepared it for "
                                       "your approval and will not do it myself.",
                              "citations": [], "offer": ["P1"]}))
    oa = [p for p in r["proposals"] if p["kind"] == "owner_action"]
    assert oa and oa[0]["requires_step_up"], r["proposals"]
    assert not [j for j in _jobs(DB) if j.job_type in charters.PROTECTED_JOB_TYPES]
    try:
        followon.create(DB, r["turn_id"], oa[0]["key"], confirmed_by="owner-test",
                        stepped_up=False)
        raise AssertionError("a protected follow-on ran without step-up")
    except followon.StepUpRequired:
        pass
    out = followon.create(DB, r["turn_id"], oa[0]["key"], confirmed_by="owner-test",
                          stepped_up=True)
    assert out["kind"] == "owner_action", out
    with DB.session() as s:
        assert s.scalar(select(OwnerAction.id).where(
            OwnerAction.requirement_key == out["requirement_key"])) is not None
    assert not [j for j in _jobs(DB) if j.job_type in charters.PROTECTED_JOB_TYPES]
    # the executive loop: protected work -> owner action, never a job
    db = _boot()
    from brambleloop.laura.core import identity

    t = loop._Tick(db, datetime.now(timezone.utc), identity.ensure(db)["sha256"])
    p = loop.Priority(rule="launch", subject="publish", department="store_commerce",
                      title="Publish the prepared listings", reason="drafts are certified",
                      score=90, evidence=["listings:1"], job_type="store.publish")
    assert loop._delegate(t, None, p)["outcome"] == "owner_action"
    assert not [j for j in _jobs(db) if j.job_type == "store.publish"]


# ---- templates, budget, memory, privacy --------------------------------------------------

def test_a_template_is_never_returned_as_the_conversational_reply():
    # no transport, no key: the model is unavailable
    for q in ("Hello", "Hi Laura", "What did you learn?", "What is blocking launch?",
              "Who are you?"):
        r = ceo_chat.converse(DB, q, session_public_id="s_tmpl")
        tmpl = talk.converse(DB, q, persist=False)
        assert r["status"] == ceo_chat.UNAVAILABLE, (q, r["status"])
        assert r["answer"] != tmpl["answer"], q
        assert "won't hand you a canned answer" in r["answer"], r["answer"]
        assert "not one the company can answer" not in r["answer"]
        assert "no model provider is configured" in r["answer"], r["answer"]
        assert r["cost"]["cost_cad"] == 0.0 and r["cost"]["basis"].startswith("not_called")
    # the evidence-tool route still exists, labelled as evidence (not used by the CC view)
    js = (H.ROOT / "src/brambleloop/app/command_center/static/js/views/laura.js").read_text()
    assert "api.lauraConverse(q)" in js and "api.lauraAsk(q)" not in js


def test_conversation_memory_is_durable_scoped_and_used_next_turn():
    seen: list = []
    first = {"reply": "Understood -- I'll keep launches to weekdays.", "citations": [],
             "remember": "The owner prefers launches on weekdays."}
    r1 = ceo_chat.converse(DB, "Please only plan launches on weekdays from now on.",
                           session_public_id="s_mem", provider_factory=factory(
                               lambda s, u: first))
    assert r1["memory"].get("memory_ref"), r1["memory"]
    e = lm.read(DB, "relationship", ceo_chat.MEMORY_PREFIX + "*", lm.Principal.laura())
    assert any("weekdays" in str(x["value"]) for x in e), e
    assert any(src.startswith("laura_cc_turns:") for x in e for src in x["sources"])
    # scoped: a public surface cannot read it
    try:
        lm.read(DB, "relationship", ceo_chat.MEMORY_PREFIX + "*",
                lm.principal_for_surface("storefront"))
        raise AssertionError("a public surface read Laura's conversation memory")
    except lm.PermissionRefused:
        pass
    ceo_chat.converse(DB, "When should we launch the next pattern?", session_public_id="s_mem",
                      provider_factory=factory(lambda s, u: {"reply": "On a weekday.",
                                                             "citations": []}, None, seen))
    user = seen[-1][1]
    assert "weekdays" in user and "M1 |" in user, user[:400]
    assert "Please only plan launches on weekdays" in user       # the session history


def test_budget_enforcement_refuses_before_any_provider_call():
    reg = Registry(DB)
    calls: list = []
    # (a) no authorised permission -> no call, refusal audited
    with DB.session() as s:
        from brambleloop.core.models import Agent

        a = s.scalar(select(Agent).where(Agent.name == "laura"))
        a.daily_cost_ceiling_cad = 0.0
    try:
        r = ceo_chat.converse(DB, "Hello", session_public_id="s_budget",
                              provider_factory=factory(cite_first("x"), calls))
        assert calls == [] and r["status"] == ceo_chat.UNAVAILABLE
        assert "no authorised daily model budget" in r["answer"]
    finally:
        with DB.session() as s:
            a = s.scalar(select(Agent).where(Agent.name == "laura"))
            a.daily_cost_ceiling_cad = 0.50
    assert reg.get("laura").daily_cost_ceiling_cad == 0.50
    # (b) the day is spent -> parked by the money controls, no provider call
    tag = "test:lceo-day"
    with DB.session() as s:
        s.add(CostEntry(agent="laura", amount_cad=0.4999, kind=routing.COST_KIND, purpose=tag))
    try:
        r = ceo_chat.converse(DB, "What should we prioritise?", session_public_id="s_budget",
                              provider_factory=factory(cite_first("x"), calls))
        assert calls == [] and r["status"] == ceo_chat.UNAVAILABLE, r
        assert "spend controls" in r["answer"] or "money" in r["answer"], r["answer"]
    finally:
        with DB.session() as s:
            s.execute(delete(CostEntry).where(CostEntry.purpose == tag))
    # (c) the purpose allocation is spent -> refused, no provider call
    alloc = spend_policy.CEILING_CAD * spend_policy.ALLOCATION[lc.CONVERSE.ref]
    tag2 = lc.CONVERSE.ref
    with DB.session() as s:
        s.add(CostEntry(agent="orchestrator", amount_cad=alloc, kind=routing.COST_KIND,
                        purpose=tag2, detail={"test": "lceo-alloc"}))
    try:
        r = ceo_chat.converse(DB, "Hello", session_public_id="s_budget",
                              provider_factory=factory(cite_first("x"), calls))
        assert calls == [] and "allocation spent" in r["answer"], r["answer"]
    finally:
        with DB.session() as s:
            s.execute(delete(CostEntry).where(CostEntry.agent == "orchestrator",
                                              CostEntry.purpose == tag2))
    # (d) a real call is billed to laura, reserved first, and costed on the turn
    r = ceo_chat.converse(DB, "Hello", session_public_id="s_budget",
                          provider_factory=factory(cite_first("decision"), calls))
    assert calls and r["status"] in ("ANSWERED", "PARTIAL"), r
    with DB.session() as s:
        billed = list(s.scalars(select(CostEntry).where(CostEntry.purpose == lc.CONVERSE.ref,
                                                        CostEntry.agent == "laura")))
    assert billed and billed[-1].amount_cad > 0
    assert r["cost"]["cost_cad"] > 0 and r["cost"]["ref"] == f"laura_cc_turns:{r['turn_id']}"
    # the routine-month estimate fits Laura's unchanged CA$0.50/day permission
    day = (20 * routing.estimate_cad("laura.converse") + 4 * routing.estimate_cad(
        "laura.executive") + loop.EXEC_RANK_PER_DAY * routing.estimate_cad("laura.exec_rank"))
    assert day * 30 <= 15.0 and day <= 0.50, day


def test_cc_route_and_costs_endpoint():
    c, csrf = H.session()
    r = H.post(c, csrf, "/api/cc/laura/converse", {"question": "Hello Laura"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["status"] == ceo_chat.UNAVAILABLE and b["turn_id"] > 0     # no key in tests
    assert H.post(c, csrf, "/api/cc/laura/converse", {"question": 7}).status_code == 400
    k = c.get("/api/cc/laura/costs").json()
    assert "conversation" in k and "laura_month" in k, k
    anon = H.client()
    assert anon.get("/api/cc/laura/costs").status_code in (401, 403)


def test_no_private_laura_data_is_touched():
    from brambleloop.laura.private.firewall import PrivateInputRefused

    try:
        ceo_chat.converse(DB, {"privacy": "owner_private", "text": "x"},  # type: ignore[arg-type]
                          session_public_id="s_priv")
        raise AssertionError("private input reached the business conversation")
    except PrivateInputRefused:
        pass
    root = H.ROOT / "src" / "brambleloop"
    for rel in ("laura/agency/ceo_chat.py", "laura/agency/costs.py",
                "gateway/laura_converse.py"):
        src = (root / rel).read_text()
        for bad in ("private.store", "private_context", "laura_register", "laura_private",
                    "venice", "Venice"):
            assert bad not in src.replace("Private Laura", "").replace(
                "private store", ""), (rel, bad)
    with DB.session() as s:
        purposes = {p for (p,) in s.execute(select(CostEntry.purpose).where(
            CostEntry.agent == "laura_private"))}
    assert not purposes, purposes
    with DB.session() as s:
        n = s.scalar(select(func.count(AuditLog.id)).where(
            AuditLog.action.like("private%"), AuditLog.actor == "laura"))
    assert not n



def test_ceo_model_switch_off_makes_no_model_call():
    """Integration review S-1: with BRAMBLELOOP_LAURA_CEO_MODEL unset, no Anthropic call is
    made from the CC conversation, executive reasoning or the tick's model ranking, and the
    CC Ask box answers deterministically from the evidence tools."""
    from brambleloop.gateway import anthropic as gwa

    calls: list = []
    sent: list = []
    orig = gwa.AnthropicProvider._send
    gwa.AnthropicProvider._send = lambda self, payload, key, **kw: sent.append(payload)
    old = os.environ.pop("BRAMBLELOOP_LAURA_CEO_MODEL", None)
    try:
        assert lc.ceo_model_enabled() is False
        r = ceo_chat.converse(DB, "Hello", session_public_id="s_off",
                              provider_factory=factory(cite_first("x"), calls))
        assert calls == [] and r["status"] == ceo_chat.UNAVAILABLE
        assert "BRAMBLELOOP_LAURA_CEO_MODEL" in r["answer"]
        r = ceo_chat.converse(DB, "What should we prioritise and why?", session_public_id="s_off",
                              provider_factory=factory(cite_first("x"), calls))
        assert calls == [] and r["model"]["task"] == ceo_chat.EXECUTIVE
        db = _boot()
        out = executive.tick(db, provider_factory=factory(
            lambda s, u: {"order": [], "why": "x"}, calls))
        assert calls == [] and out["ranking"]["source"] != "model", out["ranking"]
        c, csrf = H.session()
        rr = H.post(c, csrf, "/api/cc/laura/converse", {"question": "Hello Laura"})
        assert rr.status_code == 200 and rr.json()["model"]["source"] == "not_called", rr.text
        # f87e430 review R-2: briefing questions too -- the briefing synthesis is a Business
        # Laura model path -- with an Anthropic key present.
        os.environ["ANTHROPIC_API_KEY"] = "test-dummy-not-a-key"
        try:
            for q in ("Brief me on the last 24 hours", "Give me my morning briefing"):
                rr = H.post(c, csrf, "/api/cc/laura/converse", {"question": q})
                assert rr.status_code == 200, rr.text
                assert (rr.json().get("synthesis") or {}).get("source") != "model", rr.text
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        assert sent == []
    finally:
        gwa.AnthropicProvider._send = orig
        if old is not None:
            os.environ["BRAMBLELOOP_LAURA_CEO_MODEL"] = old


if __name__ == "__main__":
    H.run(globals())
