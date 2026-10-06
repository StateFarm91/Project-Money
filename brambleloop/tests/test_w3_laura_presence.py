"""W3 lane F: Laura Live Presence architecture (D-FB-16 items 7, 9, 10) and visible canonical
Laura (Phase 1).

* Phase 1 text is ACTIVE; voice (Phase 2) and live presence (Phase 3) are GATED by default
  with the exact owner/provider needs, and a richer request degrades live+voice -> voice ->
  text with its reason;
* every mode goes through the SAME conversation (`talk.converse`): local deterministic test
  adapters (no network, no provider) prove that a spoken turn has the same identity, evidence,
  proposals and durable history as a typed one -- no rebuild of identity/memory/authority;
* voice input with no speech-to-text provider is refused (never guessed); a low-confidence
  transcript asks again and records no turn; an unqualified voice is never used;
* the owner's view shows only the owner-approved canonical reference frames, verified by
  bytes, labelled internal; nothing is publication-approved; non-owners get nothing.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_laura_presence.py
"""
from __future__ import annotations

import base64
import hashlib

import w3_laura_cc_harness as H  # noqa: E402

from brambleloop.laura.agency import presence, voice_spec  # noqa: E402
from brambleloop.laura.agency.models import LauraTurn  # noqa: E402
from brambleloop.visual import canonical  # noqa: E402

DB = H.DB
H.seed_company()


class LocalSTT:
    name = "test-local-stt"

    def __init__(self, text, confidence=0.97):
        self.text, self.confidence = text, confidence

    def transcribe(self, audio, mime, *, language="en"):
        assert audio and isinstance(audio, bytes)
        return presence.Transcript(self.text, self.confidence)


class LocalTTS:
    name = "test-local-tts"
    voice_ref = "test-voice"

    def synthesize(self, text, *, register="business"):
        assert register == "business"
        return presence.SpeechAudio("audio/test", text.encode()[:64], ((0, "A"), (80, "O")),
                                    self.voice_ref, voice_spec.SPEC_ID)


class LocalLive:
    name = "test-local-live"

    def __init__(self):
        self.spoken = []

    def start(self, identity_id):
        return presence.PresenceFrameStream("live-1", identity_id, "test")

    def speak(self, stream, audio):
        self.spoken.append((stream.identity_id, audio.voice_ref))

    def stop(self, stream):
        pass


def _qualified():
    from test_w3_laura_voice_spec import CAND, good_eval

    return voice_spec.qualify(CAND, good_eval())


def _turns():
    with DB.session() as s:
        return s.query(LauraTurn).count()


def test_default_capabilities_text_active_voice_and_live_gated_with_needs():
    presence.install(presence.Adapters())
    caps = presence.capabilities()
    by = {p["mode"]: p for p in caps["phases"]}
    assert caps["available"] == ["text"] and caps["degradation"] == "live+voice -> voice -> text"
    assert by["text"]["status"] == "ACTIVE"
    for m in ("voice", "live"):
        assert by[m]["status"] == "GATED" and by[m]["needs"], by[m]
        for n in by[m]["needs"]:
            assert {"need", "who", "kind", "max_cost"} <= set(n), n
    neg = presence.negotiate(["live", "voice", "text"])
    assert neg["requested"] == "live" and neg["delivered"] == "text" and neg["degraded"]
    assert [s["mode"] for s in neg["skipped"]] == ["live", "voice"], neg
    c, csrf = H.session()
    r = H.post(c, csrf, "/api/cc/laura/ask", {"question": "What genuinely needs me?",
                                              "modes": ["live", "voice", "text"]})
    assert r.status_code == 200 and r.json()["delivery"]["delivered"] == "text", r.text
    j = c.get("/api/cc/laura/presence").json()
    assert j["capabilities"]["available"] == ["text"], j


def test_voice_input_is_refused_without_stt_and_records_nothing():
    presence.install(presence.Adapters())
    c, csrf = H.session()
    before = _turns()
    r = H.post(c, csrf, "/api/cc/laura/voice",
               {"audio_b64": base64.b64encode(b"\x00\x01fake-opus").decode(),
                "mime": "audio/ogg"})
    assert r.status_code == 503 and r.json()["code"] == "VOICE_GATED", r.text
    assert _turns() == before
    r = H.post(c, csrf, "/api/cc/laura/voice", {"audio_b64": "not base64!!"})
    assert r.status_code == 400, r.text


def test_spoken_turn_is_the_same_laura_same_evidence_same_history():
    q = "What should we launch next?"
    presence.install(presence.Adapters())
    typed = presence.respond(DB, text=q, session_public_id="s-typed")
    assert typed["delivery"]["delivered"] == "text" and typed["speech"] is None
    live = LocalLive()
    presence.install(presence.Adapters(stt=LocalSTT(q), tts=LocalTTS(), live=live,
                                       voice_qualification=_qualified()))
    try:
        caps = presence.capabilities()
        assert caps["available"] == ["text", "voice", "live"], caps["available"]
        before = _turns()
        spoken = presence.respond(DB, audio=b"opus-bytes", audio_mime="audio/ogg",
                                  modes=["live", "voice", "text"], session_public_id="s-voice")
        assert _turns() == before + 1                       # the same durable history table
        a, b = typed["turn"], spoken["turn"]
        assert spoken["heard"]["text"] == q and spoken["delivery"]["delivered"] == "live"
        assert a["speaker"]["identity_id"] == b["speaker"]["identity_id"] == canonical.IDENTITY_ID
        assert a["intent"] == b["intent"] and a["sources"] == b["sources"], (a["sources"],
                                                                             b["sources"])
        assert [p["key"] for p in a["proposals"]] == [p["key"] for p in b["proposals"]]
        assert spoken["speech"]["spec_id"] == voice_spec.SPEC_ID
        assert live.spoken == [(canonical.IDENTITY_ID, "test-voice")]
        # Mumbled audio: ask again, no turn recorded, nothing acted on.
        presence.install(presence.Adapters(stt=LocalSTT("publish everything", 0.4),
                                           tts=LocalTTS(), voice_qualification=_qualified()))
        before = _turns()
        out = presence.respond(DB, audio=b"x", modes=["voice"])
        assert out["status"] == "CLARIFY" and _turns() == before, out
        # An unqualified voice is never used: voice stays GATED, delivery degrades to text.
        presence.install(presence.Adapters(stt=LocalSTT(q), tts=LocalTTS(),
                                           voice_qualification={"verdict": "FAIL"}))
        out = presence.respond(DB, text=q, modes=["voice"])
        assert out["delivery"]["delivered"] == "text" and out["speech"] is None, out
    finally:
        presence.install(presence.Adapters())


def test_visible_identity_shows_only_verified_owner_approved_frames_labelled_internal():
    c, csrf = H.session()
    vis = c.get("/api/cc/laura/presence").json()["visible_identity"]
    assert vis["identity_id"] == canonical.IDENTITY_ID
    assert vis["publication_approved_frames"] == 0 and vis["customer_ready"] is False
    assert "No Laura image is publication-approved" in vis["state"]
    frames = vis["frames"]
    assert [f["frame"] for f in frames] == ["neutral_portrait", "torso_fit_reference",
                                            "full_length_standing"]
    for f in frames:
        assert f["displayable_to_owner"] and not f["publication_approved"], f
        assert f["status"] == canonical.CANONICAL_REFERENCE and "Internal" in f["label"]
        r = c.get(f["path"])
        assert r.status_code == 200, (f, r.status_code)
        assert hashlib.sha256(r.content).hexdigest() == f["sha256"]
        assert r.headers["cache-control"] == "no-store"
        assert "not publication-approved" in r.headers["x-laura-image-status"]
    for bad in ("identity_torso_v5", "..%2Fidentity_portrait.jpg", "owner_candidate_concept"):
        assert c.get(f"/api/cc/laura/frame/{bad}").status_code == 404, bad
    anon = H.client()
    for path in ("/api/cc/laura/presence", "/api/cc/laura/frame/neutral_portrait",
                 "/api/cc/laura/voice-spec"):
        assert anon.get(path).status_code in (401, 403), path
    spec = c.get("/api/cc/laura/voice-spec").json()
    assert spec["spec_id"] == voice_spec.SPEC_ID
    assert spec["registers"]["private_owner"]["status"] == "GATED"


if __name__ == "__main__":
    H.run(globals())
