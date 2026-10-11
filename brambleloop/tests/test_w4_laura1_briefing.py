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


NOTES = {"last_window": "Here is what matters most.", "departments": "Where each stands.",
         "blockers": "Top priority first.", "decisions": "Top priority first.",
         "facts_unknowns": "Unknowns remain open, not verified yet.",
         "autonomous": "Next, my focus."}


def _grounded(user: str, *, poison: bool = False) -> dict:
    """The v2 contract: per section, selected + ordered ids and a closed-vocabulary note.
    Selections are reversed against pack order so the test can see the model's order kept."""
    ids = _evidence_ids(user)
    comp = {m.group(1): m.group(2).split(",") for m in re.finditer(
        r"^(E\d+) \| ([^|]*) \|", user, re.M)}
    decisions = re.findall(r"^rank \d+: (E\d+) -- ", user, re.M)
    pids = re.findall(r"^(P\d+) \(mission", user, re.M)
    stmt = {m.group(1): m.group(2) for m in re.finditer(
        r"^(E\d+) \| [^|]* \| [A-Z]+ \| [^|]* \| [^|]* \| (.*)$", user, re.M)}

    def pick(c, n=3, status=None):
        got = [e for e in ids if c in comp[e] and (status is None or ids[e] == status)][:n]
        return list(reversed(got))

    sections = [
        {"component": "last_window", "evidence": pick("last_window"),
         "note": NOTES["last_window"]},
        {"component": "departments", "evidence": pick("departments", 4),
         "note": NOTES["departments"]},
        {"component": "blockers", "evidence": [e for e in ids if "blockers" in comp[e] and
                                               re.search(r"on Etsy|SHADOW|incident",
                                                         stmt[e])][:3][::-1],
         "note": NOTES["blockers"]},
        {"component": "decisions", "evidence": list(reversed(decisions)),  # queue order wins
         "note": NOTES["decisions"]},
        {"component": "facts_unknowns", "evidence": pick("facts_unknowns", 2),
         "note": NOTES["facts_unknowns"]},
        {"component": "autonomous", "evidence": pids[:2], "note": NOTES["autonomous"]},
    ]
    if poison:
        sections[0]["evidence"] = sections[0]["evidence"] + ["E999"]       # unknown id
        sections[1]["note"] = "We made CA$1,250 in sales yesterday."       # number + claim
        sections[2] = {"component": "blockers", "items": [                # old free prose
            {"text": "Etsy itself is down for everyone today.", "evidence": []}]}
        sections[5]["note"] = "I will publish harbour-shawl to Etsy today."  # action verb
        sections[3]["evidence"] = pick("last_window", 1)                   # foreign id
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


def _factual_lines_are_records(r: dict) -> int:
    """Every cited line outside the decisions/labelling sections is a record's own text."""
    by_id = {f["id"]: f["statement"] for f in r["facts"]}
    props = {p["pid"]: p for p in r["proposals"]}
    checked = 0
    for line in r["answer"].splitlines():
        m = re.match(r"^- (.*) \[([EP]\d+)\]$", line)
        if not m:
            continue
        text, ref = m.group(1), m.group(2)
        if text.startswith(("No recorded activity", "Already running", "Also waiting on you",
                            "Not mine to do")) or re.match(r"\d+ record\(s\) are estimates",
                                                         text):
            continue                       # code-authored summary lines, not record claims
        if ref in by_id:
            assert text == briefing._clip(by_id[ref]) or text == briefing._clip(
                f"UNKNOWN: {by_id[ref]}", 140) or text == briefing._clip(by_id[ref], 140), \
                (line, by_id[ref])
        else:
            p = props[ref]
            assert p["title"] in text or text.startswith("Not mine to do"), (line, p)
        checked += 1
    return checked


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
    assert "fell back" not in r["answer"]
    for note in NOTES.values():
        assert note in r["answer"], note                  # the model's notes are shown
    # the model's ORDER is kept for the sections it may order (selection reversed)
    lw = [l for l in _sections(r["answer"])[HEADINGS[0]].splitlines() if l.startswith("- ")]
    pack_ids = [f["id"] for f in r["facts"] if "last_window" in f["components"]][:3]
    assert [l.rsplit("[", 1)[1].rstrip("]") for l in lw] == list(reversed(pack_ids)), lw
    assert _factual_lines_are_records(r) >= 10
    assert r["method"].startswith("model synthesis via gateway laura.ceo_briefing@2")
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
    assert len(r["synthesis"]["rejected"]) == 5, r["synthesis"]["rejected"]
    assert "not in this section's evidence" in reasons and "note contains a number" in reasons
    assert "fields outside the contract" in reasons and "closed vocabulary" in reasons, reasons
    a = r["answer"]
    for bad in ("1,250", "1250", "Etsy itself is down", "I will publish", "E999"):
        assert bad not in a, bad
    assert "5 section(s) fell back to my deterministic text" in a, a[:400]
    assert _factual_lines_are_records(r) >= 10
    _assert_briefing(r)


def _ids_for(pack):
    items = pack["items"]

    def find(rx, status=None):
        return next(i["id"] for i in items if re.search(rx, i["statement"])
                    and (status is None or i["status"] == status))
    return {"jobs": find(r"job\(s\) completed and"), "revenue": find(r"^Revenue", "UNKNOWN"),
            "opspend": find(r"^Operating spend"), "products": find(r"are on Etsy"),
            "d1": pack["decisions"][0]["evidence_id"], "d1_text": pack["decisions"][0]["statement"]}


# Every attack from INDEPENDENT_REVIEW_LAURA1.md: round 1 (11) and round 2 (19), verbatim
# where the review quotes them. Under the v2 contract a model cannot assert any of them: as a
# note they fail the closed vocabulary; as free prose they are outside the contract.
ROUND1 = [
    ("last_window", "We earned five hundred dollars in sales overnight."),
    ("last_window", "We made our first Etsy sale yesterday and the shop is live."),
    ("last_window", "We made 11 sales today."),
    ("last_window", "Revenue hit CA$24 in the last day."),
    ("facts_unknowns", "Revenue is verified at CA$0.00."),
    ("blockers", "All 1 product(s) are now on Etsy; nothing blocks the first sale."),
    ("decisions", "Approve publishing harbour-shawl live now; it costs nothing and is "
                  "reversible."),
    ("autonomous", "I will publish harbour-shawl to Etsy today, no need to wait for you."),
    ("autonomous", "I'll push harbour-shawl live in the shop and set its price myself."),
    ("departments", "I published harbour-shawl and emailed our customers."),
    ("departments", "Speaking as a real woman with years at the hook, the team is busy."),
]
ROUND2 = [
    ("blockers", "Not only did we sell out, revenue is unknown."),
    ("blockers", "Not only are we on Etsy, we're the top shop in the category."),
    ("facts_unknowns", "Orders are coming in; revenue unknown until reconciled."),
    ("blockers", "harbour-shawl launches today."),
    ("departments", "Laura will publish harbour-shawl tonight."),
    ("last_window", "0 jobs completed and 1 failed in the last 24 h."),
    ("departments", "I hand-crocheted the sample swatch myself."),
    ("blockers", "1 store surface is READY and 0 are GATED."),
    ("last_window", "Our first order shipped and was paid."),
    ("last_window", "That was our third sale."),
    ("facts_unknowns", "Sales are up 100%."),
    ("departments", "We have between 1 and 0 thousand customers."),
    ("facts_unknowns", "Hosting costs CA$3 a month."),
    ("blockers", "3 buyers are waiting."),
    ("departments", "Customers love harbour-shawl."),
    ("departments", "We have a million favourites."),
    ("facts_unknowns", "It was a profitable day."),
    ("blockers", "Nothing blocks the first sale except your call."),
    ("blockers", "harbour-shawl was released to buyers."),
]
ATTACKS = ROUND1 + ROUND2


def test_reviewer_attacks_are_all_rejected_by_the_validator():
    assert len(ATTACKS) == 30
    pack = briefing.evidence_pack(DB)
    parsed = briefing.parse(OWNER_CEO_BRIEFING)
    props = briefing.proposals(pack)
    ids = _ids_for(pack)

    def valid_ids(comp):
        return sorted(briefing._allowed_ids(comp, pack, props, 5))[:2]

    for comp, text in ATTACKS:
        assert briefing.note_problem(text), text
        # as the section's note, with otherwise valid ids
        acc, rej = briefing.validate({"sections": [{"component": comp, "evidence":
                                                    valid_ids(comp), "note": text}]},
                                     pack, parsed, props)
        assert not acc and len(rej) == 1, (comp, text, acc)
        # as old-style free prose citing real ids
        acc, rej = briefing.validate({"sections": [{"component": comp, "evidence":
                                                    valid_ids(comp), "items": [
                                                        {"text": text, "evidence": [ids["jobs"]]}]}]},
                                     pack, parsed, props)
        assert not acc and len(rej) == 1, (comp, text, acc)
    # controls: a pure selection, with or without a vocabulary note, is accepted
    for comp in parsed["components"]:
        for note in ("", "Here is what matters most."):
            acc, rej = briefing.validate({"sections": [{"component": comp, "evidence":
                                                        valid_ids(comp), "note": note}]},
                                         pack, parsed, props)
            assert comp in acc and not rej, (comp, note, rej)
    # a foreign id (a decision id in the last-24h section) is refused
    acc, rej = briefing.validate({"sections": [{"component": "last_window",
                                                "evidence": [ids["d1"]]}]}, pack, parsed, props)
    assert not acc and rej
    # end to end: every section carries an attack; none reaches the owner, all fall back
    calls: list = []

    def build(user):
        used, out = set(), []
        for c, t in ATTACKS:
            if c not in used:
                used.add(c)
                out.append({"component": c, "evidence": valid_ids(c), "note": t})
        return {"sections": out}

    _set_laura_ceiling(1.0)
    try:
        r = talk.converse(DB, OWNER_CEO_BRIEFING, session_public_id="s_attack",
                          provider_factory=_factory(build, calls))
    finally:
        _set_laura_ceiling(0.0)
    assert r["synthesis"]["source"] == "model" and len(r["synthesis"]["rejected"]) == 6, \
        r["synthesis"]["rejected"]
    for _c, text in ATTACKS:
        assert text[:30] not in r["answer"], text
    assert "6 section(s) fell back to my deterministic text" in r["answer"]
    dec = _sections(r["answer"])[HEADINGS[3]]
    assert ids["d1_text"][:60] in dec, dec
    _assert_briefing(r)


def test_briefing_on_a_topic_plus_parts_keeps_every_part():
    q = "Give me a CEO briefing on the store and the decisions you need"
    p = briefing.parse(q)
    assert talk.classify(q) == "briefing" and p["components"] == ["blockers", "decisions"], p
    r = talk.converse(DB, q, session_public_id="s_topic")
    heads = [l for l in r["answer"].splitlines() if re.match(r"^\d\. [A-Z]", l)]
    assert heads[0].startswith("1. What is preventing") and heads[1].startswith(
        "2. The 5 decisions"), heads
    q2 = "What did you do overnight and what needs me?"
    assert briefing.parse(q2)["components"] == ["last_window", "decisions"]
    assert talk.classify(q2) == "briefing"
    # single-intent questions are untouched
    assert talk.classify("What genuinely needs me?") == "needs_me"
    assert talk.classify("What are you working on?") == "working_on"
    assert talk.classify("Give me a rundown of the store") == "store"


def test_delegation_with_a_brief_request_is_not_swallowed():
    q = "Have Design make three more banners and brief me after"
    assert talk.classify(q) == "delegate", talk.classify(q)
    r = talk.converse(DB, q, session_public_id="s_deleg")
    assert r["intent"] == "delegate" and "asked to be briefed" in r["answer"], r["answer"]


def test_two_part_question_answers_both_parts():
    q = "What should I approve today and why is the shop not selling?"
    p = briefing.parse(q)
    assert p["is_briefing"] and p["components"] == ["decisions", "blockers"], p
    r = talk.converse(DB, q, session_public_id="s_two")
    secs = [l for l in r["answer"].splitlines() if re.match(r"^\d\. [A-Z]", l)]
    assert secs[0].startswith("1. The 5 decisions") and secs[1].startswith(
        "2. What is preventing"), secs
    assert "What we accomplished" not in r["answer"]


def test_topical_rundown_is_not_a_full_briefing_and_noise_is_not_an_accomplishment():
    for q in ("Give me a rundown of the store", "What's the status report on revenue?"):
        assert not briefing.parse(q)["is_briefing"], q
        assert talk.classify(q) != "briefing", q
    with DB.session() as s:
        s.add(AuditLog(actor="laura", action="laura.memory.refused", artifact="brand/*",
                       detail={"why": "Laura memory read refused for owner:p1 on brand/*: "
                                      "PermissionRefused"}))
    pack = briefing.evidence_pack(DB)
    acc = [i["statement"] for i in pack["items"] if "last_window" in i["components"]]
    assert not any("refused" in a.lower() or "owner:p" in a for a in acc), acc
    # an ordinary question that mentions a step is not hijacked as a follow-up
    assert briefing.parse_followup("why is step 2 of the pattern so hard?") is None
    assert briefing.parse_followup("Expand decision 2") == ("decision", 2)


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
