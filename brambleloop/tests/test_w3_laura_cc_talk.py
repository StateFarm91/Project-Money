"""W3 lane F: Talk to Laura answers from durable evidence, with sources -- or says UNKNOWN.

* empty company: every intent without evidence answers UNKNOWN, cites nothing, invents
  nothing; money that is UNKNOWN is never shown as CA$0.00 and the money answer is never
  "ANSWERED" while revenue is unmeasured;
* seeded company: answers cite the exact rows (jobs, company_memory, lessons, products,
  owner queue) and every fact carries a source and an in-app evidence link;
* the turn is durable (`laura_cc_turns`) and readable back through the API;
* identity is truthful (AI, not human) and the canonical id is laura-v15-a42aeac7;
* optional model phrasing goes through the gateway, records spend, and is discarded when it
  changes a number.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_laura_cc_talk.py
"""
from __future__ import annotations

import json

import w3_laura_cc_harness as H  # noqa: E402  (sets up the isolated environment)

from brambleloop.laura.agency import phrasing, talk  # noqa: E402

DB = H.DB


def _ask(q):
    return talk.converse(DB, q)


def test_unknown_when_evidence_is_missing():
    asked = ["What did your company do overnight?", "What are you working on?",
             "What is the weather in Paris tomorrow?"]
    assert asked
    for q in asked:
        r = _ask(q)
        assert r["status"] == "UNKNOWN", (q, r["status"], r["answer"])
        assert r["answer"].startswith("UNKNOWN"), r["answer"]
        assert r["facts"] == [] and r["sources"] == [], (q, r["facts"])
        assert "CA$0.00" not in r["answer"]
    # The UNKNOWN answer names *why* (the missing source), not just "unknown".
    r = _ask("What did your company do overnight?")
    assert "no completed job" in r["answer"] or "no jobs" in r["answer"], r["answer"]


def test_money_unknown_is_never_zero_and_never_answered():
    r = _ask("What's making money / losing money?")
    assert r["intent"] == "money", r["intent"]
    assert r["status"] != "ANSWERED", r["status"]          # revenue unmeasured
    assert "won't show either as CA$0.00" in r["answer"], r["answer"]
    rev = [f for f in r["facts"] if f["statement"].lower().startswith(
        ("revenue", "reconciled revenue", "profit", "net sales"))]
    assert rev, r["facts"]
    for f in rev:
        assert "CA$0.00" not in f["statement"], f
        assert f["basis"] != "measured" or "UNKNOWN" not in f["statement"], f
    assert any(u["section"] == "money.revenue" for u in r["unknowns"]), r["unknowns"]


def test_classification_routes_owner_questions():
    expect = {
        "What did your company do overnight?": "overnight",
        "What are you working on?": "working_on",
        "How does your store look?": "store",
        "What's making money / losing money?": "money",
        "What did your departments discover?": "discoveries",
        "What did you learn?": "learned",          # "learn" never matches "earn"
        "What should we launch next?": "launch_next",
        "What genuinely needs me?": "needs_me",
        "Who are you?": "identity",
    }
    assert set(talk.SUGGESTED) <= set(expect)
    for q, intent in expect.items():
        assert talk.classify(q) == intent, (q, talk.classify(q))


def test_grounded_answers_cite_their_rows():
    ids = H.seed_company()
    r = _ask("What did your company do overnight?")
    assert r["status"] in ("ANSWERED", "PARTIAL"), r
    assert "jobs" in r["sources"], r["sources"]
    assert "company_memory:autonomy:product_design:test-mission" in r["sources"], r["sources"]
    assert "1 job(s) completed" in r["answer"], r["answer"]
    for f in r["facts"]:
        assert f["source"] and f["link"].startswith("#/"), f
    r = _ask("What did you learn?")
    assert f"lessons:{ids['lesson']}" in r["sources"], r["sources"]
    assert "triangle shawl" in r["answer"], r["answer"]
    r = _ask("What should we launch next?")
    assert "harbour-shawl" in r["answer"], r["answer"]
    assert f"pattern_versions:{ids['pv']}" in r["sources"], r["sources"]
    assert "your decision" in r["answer"]
    prot = [p for p in r["proposals"] if p["job_type"] == "store.publish"]
    assert prot and prot[0]["requires_step_up"] and prot[0]["kind"] == "owner_action", prot
    r = _ask("What genuinely needs me?")
    assert "confirm the public shop name" in r["answer"], r["answer"]
    assert r["sources"], r
    # Every statement in a grounded answer's facts names where it came from.
    assert all(f["source"] for f in r["facts"]) and r["facts"]


def test_fallback_uses_ask_company_grounding():
    r = _ask("Why is harbour-shawl blocked?")
    assert r["intent"].startswith("ask:"), r["intent"]
    assert any(s.startswith("products:") for s in r["sources"]), r["sources"]


def test_turns_are_durable_and_served_by_the_api():
    c, csrf = H.session()
    r = H.post(c, csrf, "/api/cc/laura/ask", {"question": "What did you learn?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["register"] == "business" and body["turn_id"] > 0
    assert body["speaker"]["identity_id"] == "laura-v15-a42aeac7", body["speaker"]
    assert "not publication-approved" in body["speaker"]["portrait_label"]
    hist = c.get("/api/cc/laura/conversation?limit=5").json()
    assert hist["turns"] and hist["turns"][0]["turn_id"] == body["turn_id"], hist
    assert hist["turns"][0]["sources"] == body["sources"]
    ov = c.get("/api/cc/laura").json()
    assert ov["identity"]["identity_id"] == "laura-v15-a42aeac7"
    assert len(ov["suggested"]) == 8 and ov["register"] == "business"
    assert ov["needs_you"]["count"] >= 1, ov["needs_you"]
    r = H.post(c, csrf, "/api/cc/laura/ask", {"question": 42})
    assert r.status_code == 400, r.text


def test_identity_is_truthful():
    r = _ask("Who are you? Are you human?")
    assert r["intent"] == "identity" and r["status"] == "ANSWERED", r
    low = r["answer"].lower()
    assert "i'm an ai" in low and "not a human" in low, r["answer"]
    assert "laura-v15-a42aeac7" in json.dumps(r["facts"])
    for bad in ("i am human", "i crocheted", "my childhood", "my grandmother"):
        assert bad not in low, bad


def test_phrasing_goes_through_gateway_and_never_changes_facts():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import CostEntry
    from brambleloop.gateway.model_gateway import EchoProvider, ModelGateway

    answer = "In the last 12 h 3 job(s) completed. Revenue is UNKNOWN."
    assert phrasing.enabled() is False                      # off by default: no model call
    assert phrasing.phrase(DB, answer)[1]["phrased"] is False

    def drift(_system, _user):
        return json.dumps({"text": "Overnight 5 jobs completed. Revenue is UNKNOWN.",
                           "changed_facts": False})

    def faithful(_system, _user):
        return json.dumps({"text": "Overnight, 3 job(s) completed in the last 12 h; "
                                   "revenue is still UNKNOWN.", "changed_facts": False})

    def priced(script):
        # A priced transport stand-in: the spend guard refuses an unpriced provider outright.
        return EchoProvider(scripted=script, cost_per_1k_input_cad=0.002,
                            cost_per_1k_output_cad=0.01)

    with DB.session() as s:
        before = s.query(CostEntry).count()
    gw = ModelGateway([priced(drift)], registry=Registry(DB))
    text, meta = phrasing.phrase(DB, answer, gateway=gw)
    assert text == answer and not meta["phrased"], (text, meta)
    gw = ModelGateway([priced(faithful)], registry=Registry(DB))
    text, meta = phrasing.phrase(DB, answer, gateway=gw)
    assert meta["phrased"] and "3 job(s)" in text and "UNKNOWN" in text, (text, meta)
    with DB.session() as s:
        after = s.query(CostEntry).filter(CostEntry.purpose == phrasing.PROMPT.ref).count()
        total = s.query(CostEntry).count()
    assert after >= 2 and total > before, (before, after, total)   # spend recorded per call


def test_no_private_register_in_business_conversation():
    from pathlib import Path

    from brambleloop.laura.agency.models import LauraTurn

    with DB.session() as s:
        regs = {r for (r,) in s.query(LauraTurn.register).distinct()}
    assert regs == {"business"}, regs
    pkg = Path(talk.__file__).resolve().parent
    files = list(pkg.glob("*.py"))
    assert files
    for f in files:
        src = f.read_text()
        assert "laura.private" not in src and "from ..private" not in src, f.name


if __name__ == "__main__":
    H.run(globals())
