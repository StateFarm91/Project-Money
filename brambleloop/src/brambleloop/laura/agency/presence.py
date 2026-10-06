"""Laura Live Presence architecture (D-FB-16 items 7, 9, 10): one Laura across text, voice and
live presence, with graceful degradation live+voice -> voice -> text.

Phase 1 (built, ACTIVE): text conversation (`talk.converse`) with visible canonical Laura.
Phase 2 (contract, GATED): speech in (phone mic / Bluetooth earbuds e.g. Galaxy Buds ->
    `SpeechToText`) and speech out in the canonical voice (`TextToSpeech`, qualified against
    `voice_spec`).
Phase 3 (contract, GATED): real-time live presence (`LivePresenceRenderer`: photoreal canonical
    Laura, blinking, expressions, subtle movement, lip sync to the TTS visemes, turn-taking).

Why Phases 2-3 need no rebuild: every modality enters and leaves through `respond()`, which
calls the SAME `talk.converse` -- the same identity (laura.identity / visual.canonical), the
same durable memory and evidence readers, the same authority boundary (follow-ons need
confirmation; protected work needs step-up and becomes an owner decision), and the same
`laura_cc_turns` history. An adapter only converts audio <-> text or text -> frames. Swapping
or losing an adapter changes the delivery, never who Laura is or what she may do.

Nothing here calls a paid provider. Adapters are injected; the registry ships with none
configured, so `capabilities()` reports Phases 2-3 GATED with the exact owner/provider needs,
and `respond()` degrades to text. Test adapters (local, deterministic) prove the contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

TEXT, VOICE, LIVE = "text", "voice", "live"
MODES = (LIVE, VOICE, TEXT)            # preference order; degradation walks right
CONTRACT_VERSION = 1


@dataclass(frozen=True)
class Transcript:
    text: str
    confidence: float                   # 0..1, from the recogniser
    language: str = "en"
    is_final: bool = True


@dataclass(frozen=True)
class SpeechAudio:
    mime: str                           # e.g. audio/ogg;codecs=opus
    data: bytes
    visemes: tuple = ()                 # (t_ms, viseme) pairs for lip sync, if provided
    voice_ref: str = ""
    spec_id: str = ""                   # the voice spec the voice was qualified against


@dataclass(frozen=True)
class PresenceFrameStream:
    """A handle to a live rendering session (WebRTC or similar); never stored."""
    session_ref: str
    identity_id: str
    frames_source: str                  # which canonical identity build renders her


@runtime_checkable
class SpeechToText(Protocol):
    name: str

    def transcribe(self, audio: bytes, mime: str, *, language: str = "en") -> Transcript: ...


@runtime_checkable
class TextToSpeech(Protocol):
    name: str
    voice_ref: str

    def synthesize(self, text: str, *, register: str = "business") -> SpeechAudio: ...


@runtime_checkable
class LivePresenceRenderer(Protocol):
    name: str

    def start(self, identity_id: str) -> PresenceFrameStream: ...

    def speak(self, stream: PresenceFrameStream, audio: SpeechAudio) -> None: ...

    def stop(self, stream: PresenceFrameStream) -> None: ...


@dataclass
class Adapters:
    """What is configured in this process. Empty by default: no provider is wired."""
    stt: SpeechToText | None = None
    tts: TextToSpeech | None = None
    live: LivePresenceRenderer | None = None
    voice_qualification: dict | None = None   # voice_spec.qualify() result for `tts`
    notes: list = field(default_factory=list)


_ADAPTERS = Adapters()
MIN_STT_CONFIDENCE = 0.80


def configured() -> Adapters:
    return _ADAPTERS


def install(adapters: Adapters) -> None:
    """Install adapters (tests, or a future owner-approved provider lane)."""
    global _ADAPTERS
    _ADAPTERS = adapters


# The exact needs per phase, as owner actions / provider work (never performed here).
PHASE_NEEDS = {
    VOICE: [
        {"need": "speech-to-text provider (streaming, en-CA) chosen and contracted",
         "who": "owner", "kind": "consequential spend + provider terms acceptance",
         "max_cost": "UNKNOWN until a provider is chosen (per-minute pricing)"},
        {"need": "text-to-speech voice qualified against voice_spec v2 (D-FB-18: measured "
                 "readings, pronunciation lexicon), then HEARD by the owner and selected by an "
                 "owner listening decision (voice_selection.OWNER_ACTION)",
         "who": "owner", "kind": "owner listening decision + paid trial approval",
         "max_cost": "UNKNOWN until a provider is chosen"},
        {"need": "if the voice imitates the human Laura: her recorded consent",
         "who": "human Laura (via owner)", "kind": "human-gated consent", "max_cost": "CA$0"},
        {"need": "browser microphone permission on the owner's phone (Bluetooth earbuds work "
                 "as the system audio route)", "who": "owner", "kind": "device permission",
         "max_cost": "CA$0"},
    ],
    LIVE: [
        {"need": "real-time avatar renderer able to reproduce laura-r2-a42aeac7 and pass the "
                 "identity -> photorealism -> anatomy gates (nothing is publication-approved "
                 "or presence-approved today)", "who": "Visual + owner",
         "kind": "provider + owner identity approval", "max_cost": "UNKNOWN"},
        {"need": "Phase 2 voice ACTIVE (lip sync needs the qualified voice's visemes)",
         "who": "system", "kind": "dependency", "max_cost": "-"},
        {"need": "owner spend authority for streaming render minutes", "who": "owner",
         "kind": "consequential spend", "max_cost": "UNKNOWN"},
    ],
}


def capabilities() -> dict:
    """What works now, what is gated, and exactly why. Non-content; safe for any owner view."""
    a = configured()
    voice_ok = a.voice_qualification is not None and \
        a.voice_qualification.get("verdict") == "PASS"
    voice_active = a.stt is not None and a.tts is not None and voice_ok
    live_active = voice_active and a.live is not None
    phases = [
        {"phase": 1, "mode": TEXT, "status": "ACTIVE",
         "what": "text conversation with visible canonical Laura (owner-only)",
         "needs": []},
        {"phase": 2, "mode": VOICE, "status": "ACTIVE" if voice_active else "GATED",
         "what": "speech in (phone mic / earbuds) -> transcription -> the same conversation "
                 "-> spoken reply in the canonical voice + text",
         "needs": [] if voice_active else PHASE_NEEDS[VOICE],
         "configured": {"stt": getattr(a.stt, "name", None), "tts": getattr(a.tts, "name", None),
                        "voice_qualified": voice_ok}},
        {"phase": 3, "mode": LIVE, "status": "ACTIVE" if live_active else "GATED",
         "what": "real-time live presence: canonical Laura, blinking, expressions, subtle "
                 "movement, lip sync, turn-taking",
         "needs": [] if live_active else PHASE_NEEDS[LIVE],
         "configured": {"renderer": getattr(a.live, "name", None)}},
    ]
    return {"contract_version": CONTRACT_VERSION, "modes": list(MODES),
            "degradation": "live+voice -> voice -> text",
            "available": [p["mode"] for p in phases if p["status"] == "ACTIVE"],
            "phases": phases,
            "invariants": ["one Laura: identity, memory, authority and history are the same "
                           "in every mode (talk.converse is the only conversation path)",
                           "no paid provider is called without owner spend authority",
                           "private register stays GATED in every mode"]}


def negotiate(requested: list[str] | None) -> dict:
    """The best mode available for a request, walking live -> voice -> text."""
    caps = capabilities()
    avail = set(caps["available"])
    req = [m for m in (requested or [TEXT]) if m in MODES] or [TEXT]
    want = min(req, key=MODES.index)                 # the richest mode requested
    chosen, skipped = TEXT, []
    for m in MODES[MODES.index(want):]:
        if m in avail:
            chosen = m
            break
        phase = next(p for p in caps["phases"] if p["mode"] == m)
        skipped.append({"mode": m, "status": phase["status"],
                        "why": "; ".join(n["need"] for n in phase["needs"][:2]) or "unavailable"})
    return {"requested": want, "delivered": chosen, "degraded": chosen != want,
            "skipped": skipped}


def respond(db, *, text: str | None = None, audio: bytes | None = None,
            audio_mime: str = "", modes: list[str] | None = None,
            session_public_id: str = "") -> dict:
    """One owner turn in any mode. Always returns the text turn; adds speech/presence only
    when that mode is ACTIVE. Input audio without an STT adapter is refused (no guessing)."""
    from . import talk

    a = configured()
    neg = negotiate(modes)
    heard = None
    if audio is not None:
        if a.stt is None:
            return {"status": "REFUSED", "delivery": neg,
                    "error": "voice input is GATED: no speech-to-text provider is configured; "
                             "type the question instead"}
        tr = a.stt.transcribe(audio, audio_mime or "application/octet-stream")
        heard = {"text": tr.text, "confidence": tr.confidence, "stt": a.stt.name}
        if not tr.is_final or tr.confidence < MIN_STT_CONFIDENCE:
            return {"status": "CLARIFY", "delivery": neg, "heard": heard,
                    "answer": "I didn't catch that clearly enough to act on it -- could you "
                              "say it again?"}
        text = tr.text
    turn = talk.converse(db, text or "", session_public_id=session_public_id)
    out = {"status": "OK", "turn": turn, "heard": heard, "delivery": neg, "speech": None,
           "presence": None}
    if neg["delivered"] in (VOICE, LIVE) and a.tts is not None:
        sp = a.tts.synthesize(turn["answer"], register="business")
        out["speech"] = {"mime": sp.mime, "bytes": len(sp.data), "voice_ref": sp.voice_ref,
                         "spec_id": sp.spec_id, "visemes": len(sp.visemes)}
        if neg["delivered"] == LIVE and a.live is not None:
            stream = a.live.start(turn["speaker"]["identity_id"])
            a.live.speak(stream, sp)
            out["presence"] = {"session_ref": stream.session_ref,
                               "identity_id": stream.identity_id}
    return out
