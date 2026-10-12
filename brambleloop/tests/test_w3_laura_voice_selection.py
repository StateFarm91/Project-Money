"""W3 lane F: choosing Laura's voice (D-FB-18 items 7-8) and her required roadmap.

* the scorecard covers every D-FB-18 criterion; perceptual criteria are UNKNOWN until the
  owner (or a named human listener) has HEARD named samples -- automatic/model scores, missing
  sample hashes, or a non-owner judging an owner-only criterion never pass;
* `select()` refuses without a PASS qualification on the current spec, a complete scorecard,
  and an owner listening decision id recorded in DECISION_LOG; on success it writes a
  hash-chained durable voice identity (provider-independent descriptors + reference-sample
  digest); a replacement must requalify AND be judged the same voice as the reference;
* the "listen to shortlisted candidates" owner action states provider access + paid trial
  approval with max cost UNKNOWN (never CA$0.00) and is surfaced by Laura and the CC;
* Voice (P2) and Live Presence (P3) are REQUIRED, GATED, never cancelled; voice is a permanent
  improvement domain; the roadmap is a Command Center provider.
No voice provider is called.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_laura_voice_selection.py
"""
from __future__ import annotations

import hashlib

import w3_laura_cc_harness as H  # noqa: E402

from brambleloop.app.command_center import providers  # noqa: E402
from brambleloop.laura.agency import presence, roadmap, talk  # noqa: E402
from brambleloop.laura.agency import voice_selection as VS  # noqa: E402
from brambleloop.laura.agency import voice_spec as V  # noqa: E402
from test_w3_laura_voice_spec import CAND, good_eval  # noqa: E402

DB = H.DB
SAMPLES = [hashlib.sha256(f"sample-{i}".encode()).hexdigest() for i in range(3)]
D18 = ("apparent age", "canonical appearance", "feminine", "attractive", "warm", "sensual",
       "confident", "conversational", "emotional range", "latency", "consistent",
       "pronunciation", "stability", "cost")


def heard(verdict="PASS", judge="owner", **kw):
    return {"verdict": verdict, "judge": judge, "heard_samples_sha256": SAMPLES[:2], **kw}


def full_judgements(**over):
    j = {k: heard() for k, _l, kind in VS.CRITERIA if kind == "listening"}
    j.update({"latency": {"reading": "MEASURED", "value": 420, "method": "p50 over 50 turns",
                          "verdict": "PASS"},
              "consistency": {"reading": "MEASURED", "value": 0.97, "method": "20 renders",
                              "verdict": "PASS"},
              "pronunciation": {"reading": "MEASURED", "value": 1.0, "method": "lexicon",
                                "verdict": "PASS"},
              "provider_stability": {"evidence": "versioned voice id; terms reviewed",
                                     "verdict": "PASS"},
              "cost": {"evidence": "price sheet", "value_cad_per_minute": 0.2,
                       "verdict": "PASS"}})
    j.update(over)
    return j


def test_scorecard_covers_d_fb_18_and_perception_is_never_auto_scored():
    labels = " ".join(label.lower() for _k, label, _kind in VS.CRITERIA)
    for word in D18:
        assert word in labels, word
    empty = VS.scorecard(CAND, {})
    assert empty["verdict"] == "INCOMPLETE" and len(empty["unknown"]) == len(VS.CRITERIA)
    assert all(r["result"] == "UNKNOWN" for r in empty["criteria"])
    listening = [k for k, _l, kind in VS.CRITERIA if kind == "listening"]
    assert len(listening) >= 9
    for bad in ({"verdict": "PASS", "judge": "model", "heard_samples_sha256": SAMPLES},
                {"verdict": "PASS", "judge": "owner", "auto": True,
                 "heard_samples_sha256": SAMPLES},
                {"verdict": "PASS", "judge": "owner"},                    # nothing heard
                {"verdict": "PASS", "judge": "owner", "basis": "metric",
                 "heard_samples_sha256": SAMPLES}):
        card = VS.scorecard(CAND, full_judgements(warmth=bad))
        assert card["verdict"] == "INCOMPLETE" and "warmth" in card["unknown"], card
    card = VS.scorecard(CAND, full_judgements(attractiveness=heard(judge="human_listener")))
    assert "attractiveness" in card["unknown"]                       # owner-only criterion
    card = VS.scorecard(CAND, full_judgements(cost={"evidence": "pending"}))
    assert "cost" in card["unknown"]                                 # UNKNOWN, never CA$0
    card = VS.scorecard(CAND, full_judgements(latency={"reading": "MEASURED", "value": 2500,
                                                       "method": "p50"}))
    assert card["verdict"] == "FAIL" and "latency" in card["failed"]
    card = VS.scorecard(CAND, full_judgements(exclusions_absent=heard("FAIL")))
    assert card["verdict"] == "FAIL"
    assert VS.scorecard(CAND, full_judgements())["verdict"] == "PASS"


def test_selection_needs_owner_listening_decision_and_locks_a_durable_identity():
    q = V.qualify(CAND, good_eval())
    card = VS.scorecard(CAND, full_judgements())
    rec = {"D-TEST-LISTEN-1"}
    yes = rec.__contains__
    for kwargs, why in (
            (dict(qualification={"verdict": "FAIL"}, card=card, owner_decision_id="D-TEST-LISTEN-1"),
             "qualification"),
            (dict(qualification=q, card=VS.scorecard(CAND, {}), owner_decision_id="D-TEST-LISTEN-1"),
             "scorecard"),
            (dict(qualification=q, card=card, owner_decision_id=""), "decision"),
            (dict(qualification=q, card=card, owner_decision_id="D-NOT-RECORDED"), "decision")):
        try:
            VS.select(DB, CAND, kwargs["qualification"], kwargs["card"],
                      owner_decision_id=kwargs["owner_decision_id"],
                      reference_samples=SAMPLES, decision_recorded=yes)
        except VS.SelectionRefused as exc:
            assert why in str(exc).lower(), (why, exc)
            continue
        raise AssertionError(f"selected without {why}")
    # The real DECISION_LOG has no listening decision yet: refused by default.
    try:
        VS.select(DB, CAND, q, card, owner_decision_id="D-FB-99", reference_samples=SAMPLES)
        raise AssertionError("selected without a recorded owner decision")
    except VS.SelectionRefused:
        pass
    assert VS.current(DB) is None
    out = VS.select(DB, CAND, q, card, owner_decision_id="D-TEST-LISTEN-1",
                    reference_samples=SAMPLES, decision_recorded=yes)
    assert out["selected"] and out["version"] == 1
    cur = VS.current(DB)
    assert cur["reference_samples_sha256"] == VS.samples_digest(SAMPLES)
    r = cur["record"]
    assert r["spec_id"] == V.SPEC_ID and r["descriptors"]["apparent_age"]["range_years"] == [30, 34]
    assert r["registers"] == {"business": "ACTIVE", "private_owner": "GATED"}
    assert r["instrument"]["provider"] == CAND["provider"]       # instrument, not identity
    # A replacement must requalify and be judged the same voice as the locked reference.
    other = {**CAND, "voice_ref": "voice-99"}
    q2 = V.qualify(other, good_eval())
    try:
        VS.select(DB, other, q2, VS.scorecard(other, full_judgements()),
                  owner_decision_id="D-TEST-LISTEN-1", reference_samples=SAMPLES,
                  decision_recorded=yes)
        raise AssertionError("replacement accepted without same-voice judgement")
    except VS.SelectionRefused as exc:
        assert "same voice" in str(exc)
    c2 = VS.scorecard(other, full_judgements(same_voice_as_reference=heard()), replacement=True)
    out = VS.select(DB, other, q2, c2, owner_decision_id="D-TEST-LISTEN-1",
                    reference_samples=SAMPLES, decision_recorded=yes)
    assert out["version"] == 2 and VS.current(DB)["version"] == 2
    # Tampering with the stored record breaks the chain and is reported, never hidden.
    from brambleloop.laura.agency.models import LauraVoiceIdentity
    with DB.session() as s:
        row = s.query(LauraVoiceIdentity).filter_by(version=1).one()
        row.record = {**row.record, "owner_decision_id": "forged"}
    try:
        VS.current(DB)
        raise AssertionError("tampered voice identity verified")
    except VS.SelectionRefused:
        pass
    assert "error" in VS.status(DB)["canonical_voice"]


def test_listening_owner_action_states_paid_trial_and_unknown_cost():
    a = VS.OWNER_ACTION
    assert "Listen to the shortlisted Laura voice candidates" in a["action"]
    assert any("provider access" in n for n in a["needs"])
    assert any("paid trial" in n for n in a["needs"])
    assert a["max_cost"].startswith("UNKNOWN") and a["max_cost_cad"] is None
    t = talk.converse(DB, "What genuinely needs me?", session_public_id="s")
    assert "Listen to the shortlisted Laura voice candidates" in t["answer"], t["answer"]
    assert "CA$0.00" not in t["answer"].split("And one of mine")[-1]
    c, _csrf = H.session()
    j = c.get("/api/cc/laura/presence").json()
    assert j["voice"]["owner_action"]["requirement_key"] == "laura.voice.listen_shortlist"
    assert j["voice"]["spec_id"] == "laura-voice-v2"


def test_voice_and_live_presence_are_required_gated_never_cancelled():
    presence.install(presence.Adapters())
    rows = {r["id"]: r for r in roadmap.rows()}
    for rid in ("LAURA-VOICE-P2", "LAURA-LIVE-P3", "LAURA-PRIVATE-REGISTER",
                "LAURA-VOICE-IMPROVE"):
        r = rows[rid]
        assert r["required"] and r["cancelled"] is False and r["status"] == "GATED", r
        assert r["gate"]["kind"] in ("owner", "data", "external") and r["gate"]["key"]
    assert rows["LAURA-TEXT-P1"]["status"] == "COMPLETE"
    assert "Zoom-like" in rows["LAURA-LIVE-P3"]["title"]
    dom = roadmap.IMPROVEMENT_DOMAIN
    assert set(dom["dimensions"]) == {"realism", "latency", "prosody", "expressiveness",
                                      "conversation quality"}
    assert any("same voice" in i for i in dom["invariants"])
    assert all(str(v).startswith("UNKNOWN") for v in dom["metrics"].values())
    e = providers.call("laura_roadmap", DB)
    assert e["status"] == "DEGRADED" and "GATED" in e["reason"], e
    assert len(e["items"]) == len(roadmap.ROWS)
    from brambleloop.app.command_center import tabs
    assert tabs.autonomy(DB)["sections"]["laura_roadmap"]["status"] == "DEGRADED"


if __name__ == "__main__":
    H.run(globals())
