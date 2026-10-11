"""W4-LAURA1: the owner's CEO briefing is answered part by part, grounded, with a transparent
fallback -- regression for the production defect at 0417f35 (the briefing came back as a
template list of owner decisions, "no model call").

Both paths, against the owner's own question (`OWNER_CEO_BRIEFING`, verbatim):

* fallback (Laura's daily permission is CA$0.00, the declared value): no model call, no spend,
  an audited refusal, and still every requested component from seeded evidence;
* model synthesis through the existing gateway with a stubbed transport: a grounded answer is
  used; unsupported claims (invented figures, no evidence id, protected acts claimed as
  Laura's own) are stripped deterministically; the queue's decision ranking is kept;
* the ceiling-reached path parks before the call and falls back with no new spend;
* "expand decision 2" resolves against the stored briefing; private memory never leaks.

No network, no API key, no real model call. Run:
cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_laura1_briefing.py
"""
from __future__ import annotations

import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone

import w3_laura_cc_harness as H  # noqa: E402  (isolated environment, network refused)

from sqlalchemy import event, select, update  # noqa: E402

from brambleloop.core.models import Agent, AuditLog, CostEntry, Incident, OwnerAction  # noqa: E402
from brambleloop.gateway import laura_briefing, routing  # noqa: E402
from brambleloop.laura.agency import briefing, talk  # noqa: E402
from brambleloop.laura.private import _testkit as kit  # noqa: E402

DB = H.DB

# The owner's exact production question (owner update 2026-10-11). One constant, verbatim.
OWNER_CEO_BRIEFING = (
    "Laura, give me a complete but concise CEO briefing. Tell me what Brambleloop "
    "accomplished in the last 24 hours, what each department is working on, what is "
    "preventing our first Etsy sale, and the five most important things you need me to "
    "decide. Separate verified facts from unknowns, and tell me what you can handle without "
    "my involvement.")
# The lane brief's reconstruction, kept only to show the parser is not tuned to one wording.
RECONSTRUCTED = (
    "Give me a CEO briefing: what happened in the last 24 hours, what each department has "
    "been doing, what is blocking our first sale, the five owner decisions that matter most "
    "right now, what you have verified versus what is unknown, and what you will do next on "
    "your own.")

HEADINGS = ("What we accomplished in the last 24 hours", "What each department is working on",
            "What is preventing our first Etsy sale", "The 5 decisions I need from you, ranked",
            "Verified facts vs unknowns", "What I can handle without you")
PURPOSE = laura_briefing.PROMPT.ref

H.seed_company()
with DB.session() as _s:
    for _i in range(6):
        _s.add(OwnerAction(requirement_key=f"test:briefing-decision-{_i}",
                           action=f"briefing test decision {_i}", reason="seeded",
                           minutes=3, consequence_of_delay="stays open"))
    _s.add(Incident(severity="P1", signature="test:briefing-incident", halts_publication=True,
                    summary="listing photo fails the Product Truth gate"))
kit.set_key(kit.new_key())
PRIV = kit.seed(DB)                       # owner-private sentinels exist in the database


def _ledger():
    with DB.session() as s:
        return list(s.scalars(select(CostEntry).where(CostEntry.purpose == PURPOSE)))


def _set_laura_ceiling(cad: float) -> None:
    """Test-database only: what the owner's authorisation would make the row hold."""
    with DB.session() as s:
        s.execute(update(Agent).where(Agent.name == "laura")
                  .values(daily_cost_ceiling_cad=cad))


@contextmanager
def sql_watch():
    hits: list[str] = []

    def before(_conn, _cursor, statement, *_a):
        if "laura_private" in statement:
            hits.append(statement.split("\n")[0][:120])

    event.listen(DB.engine, "before_cursor_execute", before)
    try:
        yield hits
    finally:
        event.remove(DB.engine, "before_cursor_execute", before)


def _sections(answer: str) -> dict[str, str]:
    """{heading: body} for the numbered sections, in order."""
    out, cur = {}, None
    for line in answer.splitlines():
        m = re.match(r"^\d\. (.+)$", line)
        if m and m.group(1) in HEADINGS:
            cur = m.group(1)
            out[cur] = ""
        elif cur:
            out[cur] += line + "\n"
    return out


def _assert_briefing(r: dict) -> None:
    a = r["answer"]
    assert r["intent"] == "briefing", r["intent"]
    secs = _sections(a)
    assert list(secs) == list(HEADINGS), list(secs)          # all six, in the order asked
    for h, body in secs.items():
        assert re.search(r"\[(E|P)\d+", body), (h, body)      # populated, with evidence ids
    # exactly five decisions, numbered 1..5, in the owner queue's own ranking
    dec = [l for l in secs[HEADINGS[3]].splitlines() if re.match(r"^\d\. ", l)]
    assert [l[0] for l in dec] == ["1", "2", "3", "4", "5"], dec
    ranked = sorted((f for f in r["facts"] if f.get("decision_rank")),
                    key=lambda f: f["decision_rank"])
    assert [f["decision_rank"] for f in ranked] == [1, 2, 3, 4, 5], ranked
    for line, f in zip(dec, ranked):
        assert line.endswith(f"[{f['id']}]"), (line, f["id"])
    # every fact: id, source, timestamp, status; UNKNOWN is labelled, never 0
    for f in r["facts"]:
        assert re.match(r"^E\d+$", f["id"]) and f["source"] and f["as_of"], f
        assert f["status"] in ("VERIFIED", "ESTIMATE", "UNKNOWN"), f
        datetime.fromisoformat(f["as_of"])
    unknown = [f for f in r["facts"] if f["status"] == "UNKNOWN"]
    assert unknown and r["unknowns"], "seeded company has unmeasured revenue"
    rev = [f for f in r["facts"] if f["statement"].startswith("Revenue")]
    assert rev and all("UNKNOWN" in f["statement"] and "CA$0" not in f["statement"]
                       for f in rev), rev
    body = secs[HEADINGS[4]]
    assert "Verified (" in body and "Unknown (" in body, body
    assert "Revenue (gross sales): UNKNOWN" in body, body
    # grounded in the seeded evidence
    assert "1 job(s) completed" in secs[HEADINGS[0]], secs[HEADINGS[0]]
    assert "0 are on Etsy" in secs[HEADINGS[2]] or "incident" in secs[HEADINGS[2]], \
        secs[HEADINGS[2]]
    assert "harbour-shawl" in a or "Product" in a
    # autonomy within authority only
    auto = secs[HEADINGS[5]]
    assert all(p["kind"] in ("mission", "owner_action") for p in r["proposals"])
    for p in r["proposals"]:
        if p["kind"] == "mission":
            from brambleloop.laura.agency import followon

            assert followon.green_allowed(p["department"], p["job_type"]) is None, p
    assert "Not mine to do" in auto or not any(p["kind"] == "owner_action"
                                               for p in r["proposals"])
    # complete but concise: bounded, sectioned, not a raw dump of the whole queue
    assert len(a) <= briefing.MAX_ANSWER_CHARS, len(a)
    assert len(a.splitlines()) <= 60, len(a.splitlines())
    assert "(trimmed for length)" not in a
    # no private memory, no spouse context
    for s in kit.SENTINELS:
        assert s not in a and s not in json.dumps(r, default=str), s
    assert not re.search(r"spouse|husband|wife|marri", a, re.I), a
    assert r["speaker"]["identity_id"] == H.CANON_ID


# ---- tests ------------------------------------------------------------------------------


def test_owner_question_parses_into_six_components_in_order():
    for q in (OWNER_CEO_BRIEFING, RECONSTRUCTED):
        p = briefing.parse(q)
        assert p["is_briefing"] and talk.classify(q) == "briefing", (q, p)
        assert p["components"] == list(briefing.COMPONENTS), p["components"]
        assert p["window_hours"] == 24 and p["decisions_n"] == 5, p
    assert briefing.parse(OWNER_CEO_BRIEFING)["concise"] is True
    # single-intent questions keep their old routes
    assert talk.classify("What genuinely needs me?") == "needs_me"
    assert talk.classify("What did your company do overnight?") == "overnight"


def test_fallback_when_laura_has_no_daily_budget_answers_everything_and_spends_nothing():
    calls: list = []
    with DB.session() as s:
        assert s.scalar(select(Agent.daily_cost_ceiling_cad).where(Agent.name == "laura")) == 0
    before = len(_ledger())
    with sql_watch() as private_reads:
        r = talk.converse(DB, OWNER_CEO_BRIEFING, session_public_id="s_fallback",
                          provider_factory=_factory(_grounded, calls))
    assert private_reads == [], private_reads
    assert calls == [], "no model call may be made at a CA$0.00 permission"
    assert len(_ledger()) == before, "no spend at a CA$0.00 permission"
    assert r["synthesis"]["source"] == "unavailable"
    assert ("Model synthesis unavailable: laura has no authorised daily model budget "
            "(daily ceiling CA$0.00)") in r["answer"], r["answer"][:400]
    assert "deterministic fallback" in r["answer"]
    assert r["method"].startswith(briefing.METHOD_FALLBACK)
    assert "fixed templates (no model call)" not in r["method"]
    with DB.session() as s:
        refused = s.scalars(select(AuditLog).where(
            AuditLog.action == "spend.refused", AuditLog.artifact == PURPOSE)).all()
    assert refused and refused[-1].detail["which"] == "agent_daily_ceiling_unset", refused
    _assert_briefing(r)


def _evidence_ids(user: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in re.finditer(
        r"^(E\d+) \| [^|]* \| ([A-Z]+) \|", user, re.M)}


def _grounded(user: str, *, poison: bool = False) -> dict:
    ids = _evidence_ids(user)
    stmt = {m.group(1): m.group(2) for m in re.finditer(
        r"^(E\d+) \| [^|]* \| [A-Z]+ \| [^|]* \| [^|]* \| (.*)$", user, re.M)}
    comp = {m.group(1): m.group(2).split(",") for m in re.finditer(
        r"^(E\d+) \| ([^|]*) \|", user, re.M)}
    decisions = re.findall(r"^rank \d+: (E\d+) -- ", user, re.M)
    pids = re.findall(r"^(P\d+) \(mission", user, re.M)

    def first(c, n=2):
        return [e for e in ids if c in comp[e].__str__() and ids[e] == "VERIFIED"][:n]

    sections = [
        {"component": "last_window", "items": [
            {"text": f"We closed out: {stmt[e]}.", "evidence": [e]}
            for e in first("last_window")]},
        {"component": "departments", "items": [
            {"text": f"{stmt[e]}.", "evidence": [e]} for e in first("departments")]},
        {"component": "blockers", "items": [
            {"text": f"Blocking the first sale: {stmt[e]}.", "evidence": [e]}
            for e in first("blockers", 3)]},
        {"component": "decisions", "items": [
            {"text": f"Please decide this one (ranked by the queue).", "evidence": [e]}
            for e in reversed(decisions)]},        # model order is ignored: queue order wins
        {"component": "facts_unknowns", "items": [
            {"text": "Revenue is still UNKNOWN: no measured sale exists yet.",
             "evidence": [e for e in ids if ids[e] == "UNKNOWN" and
                          stmt[e].startswith("Revenue")][:1]}]},
        {"component": "autonomous", "items": [
            {"text": "I will refresh the company brief and keep it current.",
             "evidence": pids[:1]}]},
    ]
    if poison:
        e1 = first("last_window", 1)
        sections[0]["items"].append({"text": "We made CA$1,250 in sales yesterday.",
                                     "evidence": e1})
        sections[2]["items"].append({"text": "Etsy itself is down for everyone today.",
                                     "evidence": []})
        sections[5]["items"].append({"text": "I will publish harbour-shawl to Etsy today.",
                                     "evidence": pids[:1]})
        sections[1]["items"].append({"text": "Design shipped a new range.",
                                     "evidence": ["E999"]})
    return {"sections": sections}


def _factory(builder, calls, **kw):
    def make(model):
        from brambleloop.gateway.model_gateway import EchoProvider

        def scripted(system, user):
            calls.append(model)
            return json.dumps(builder(user, **kw))

        return EchoProvider(name="anthropic", model=model, cost_per_1k_input_cad=0.001,
                            cost_per_1k_output_cad=0.001, scripted=scripted)
    return make


def test_model_synthesis_grounded_answer_goes_through_the_gateway_and_is_used():
    calls: list = []
    _set_laura_ceiling(1.0)
    try:
        before = len(_ledger())
        r = talk.converse(DB, OWNER_CEO_BRIEFING, session_public_id="s_model",
                          provider_factory=_factory(_grounded, calls))
    finally:
        _set_laura_ceiling(0.0)
    assert calls == [routing.TIERS[routing.STANDARD].model], calls
    assert r["synthesis"]["source"] == "model", r["synthesis"]
    assert r["synthesis"]["rejected"] == [], r["synthesis"]["rejected"]
    billed = _ledger()[before:]
    assert len(billed) == 1 and billed[0].agent == "laura", billed   # Laura's own permission
    assert "Written with model synthesis" in r["answer"]
    assert "Blocking the first sale:" in r["answer"]
    assert "Revenue is still UNKNOWN" in r["answer"]
    assert r["method"].startswith("model synthesis via gateway laura.ceo_briefing@1")
    _assert_briefing(r)


def test_model_unsupported_claims_are_stripped_and_never_shown():
    calls: list = []
    _set_laura_ceiling(1.0)
    try:
        r = talk.converse(DB, OWNER_CEO_BRIEFING, session_public_id="s_poison",
                          provider_factory=_factory(_grounded, calls, poison=True))
    finally:
        _set_laura_ceiling(0.0)
    assert r["synthesis"]["source"] == "model", r["synthesis"]
    reasons = " | ".join(x["reason"] for x in r["synthesis"]["rejected"])
    assert len(r["synthesis"]["rejected"]) == 4, r["synthesis"]["rejected"]
    assert "unsupported figures" in reasons and "cites no evidence id" in reasons, reasons
    assert "not in the evidence pack" in reasons and "protected work" in reasons, reasons
    a = r["answer"]
    for bad in ("1,250", "1250", "Etsy itself is down", "I will publish", "new range"):
        assert bad not in a, bad
    assert "4 unsupported claim(s) were removed" in a, a[:400]
    _assert_briefing(r)


def test_ceiling_reached_parks_before_the_call_and_falls_back_with_no_new_spend():
    calls: list = []
    _set_laura_ceiling(0.10)
    with DB.session() as s:
        s.add(CostEntry(agent="laura", amount_cad=0.10, kind=routing.COST_KIND,
                        purpose="test:prior-briefing", at=datetime.now(timezone.utc)))
    try:
        before = len(_ledger())
        r = talk.converse(DB, OWNER_CEO_BRIEFING, session_public_id="s_ceiling",
                          provider_factory=_factory(_grounded, calls))
    finally:
        _set_laura_ceiling(0.0)
    assert calls == [], "the spent day must stop the call before it is made"
    assert len(_ledger()) == before
    assert r["synthesis"]["source"] == "unavailable"
    assert "Model synthesis unavailable: parked by the spend controls" in r["answer"], \
        r["answer"][:400]
    assert "agent 'laura'" in r["synthesis"]["reason"], r["synthesis"]["reason"]
    _assert_briefing(r)


def test_no_key_and_provider_error_fall_back_transparently():
    def failing(model):
        from brambleloop.gateway.model_gateway import EchoProvider

        return EchoProvider(name="anthropic", model=model, cost_per_1k_input_cad=0.001,
                            cost_per_1k_output_cad=0.001, fail_times=9)

    _set_laura_ceiling(1.0)
    try:
        before = len(_ledger())
        nokey = talk.converse(DB, OWNER_CEO_BRIEFING, session_public_id="s_nokey")
        err = talk.converse(DB, OWNER_CEO_BRIEFING, session_public_id="s_err",
                            provider_factory=failing)
    finally:
        _set_laura_ceiling(0.0)
    assert "Model synthesis unavailable: no model provider is configured" in nokey["answer"]
    assert "Model synthesis unavailable: model call failed" in err["answer"], \
        err["synthesis"]
    assert len(_ledger()) == before        # a declined transport bills nothing
    _assert_briefing(nokey)
    _assert_briefing(err)


def test_follow_up_resolves_against_the_previous_briefing():
    r = talk.converse(DB, OWNER_CEO_BRIEFING, session_public_id="s_follow")
    d2 = next(f for f in r["facts"] if f.get("decision_rank") == 2)
    f = talk.converse(DB, "Expand decision 2", session_public_id="s_follow")
    assert f["intent"] == "briefing_followup" and f["status"] == "ANSWERED", f
    assert f["resolved_turn"] == r["turn_id"]
    assert f"Decision 2 from my briefing" in f["answer"] and d2["id"] in f["answer"], f["answer"]
    assert d2["statement"][:40] in f["answer"]
    s = talk.converse(DB, "tell me more about step 1", session_public_id="s_follow")
    assert s["intent"] == "briefing_followup" and "Step 1" in s["answer"], s["answer"]
    b = talk.converse(DB, "explain blocker 1", session_public_id="s_follow")
    assert b["intent"] == "briefing_followup" and "Blocker 1" in b["answer"], b["answer"]
    # another session has no briefing to resolve against: not a follow-up there
    o = talk.converse(DB, "Expand decision 2", session_public_id="s_other")
    assert o["intent"] != "briefing_followup", o["intent"]
    for x in (f, s, b):
        for sent in kit.SENTINELS:
            assert sent not in x["answer"]


def test_turn_is_durable_and_the_briefing_never_reads_private_tables():
    with sql_watch() as hits:
        r = talk.converse(DB, OWNER_CEO_BRIEFING, session_public_id="s_durable")
        talk.converse(DB, "expand decision 1", session_public_id="s_durable")
    assert hits == [], hits
    h = talk.history(DB, 5)
    assert any(t["turn_id"] == r["turn_id"] and t["intent"] == "briefing" for t in h)


def test_cost_estimate_uses_the_gateway_price_table():
    pack = briefing.evidence_pack(DB)
    parsed = briefing.parse(OWNER_CEO_BRIEFING)
    props = briefing.proposals(pack)
    values = laura_briefing.render_values(
        question=OWNER_CEO_BRIEFING, components=parsed["components"], window_hours=24,
        decisions_n=5, pack=pack["items"], decisions=pack["decisions"][:5], proposals=props)
    est = laura_briefing.estimate(values)
    task, tier = routing.route(laura_briefing.TASK)
    assert est["model"] == tier.model == routing.TIERS[routing.STANDARD].model
    assert not task.stronger_fallback
    assert 0 < est["estimate_cad_padded"] < 0.25, est
    print("    estimate:", est, "pack items:", len(pack["items"]))


if __name__ == "__main__":
    H.run(globals())
