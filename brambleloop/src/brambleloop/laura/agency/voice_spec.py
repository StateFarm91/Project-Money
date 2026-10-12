"""Canonical Laura Voice specification and the qualification a voice must pass.

Version 2 (current) is the owner's decision D-FB-18 item 6 (2026-10-06), which resolved the
accent and apparent age that v1 (D-FB-16 item 8) had left PROPOSED. v1 is kept, pinned, in
`SUPERSEDED` for history; it is never edited, and v2 is never edited in place either -- a change
is a new version under a new owner decision.

Provider-independent: this is what Laura SOUNDS like, written as targets and explicit
exclusions, not as a vendor voice id. A text-to-speech provider/voice is a replaceable
instrument (D-FB-18 item 7: "the provider is an implementation detail"); it speaks as Laura only
after `qualify()` PASSES on measured evidence AND the owner has HEARD it and selected it by a
recorded decision (`laura.agency.voice_selection`).

ONE canonical voice. Registers are contexts of that one voice, never a second voice or persona:
* business/public -- polished and appropriate (ACTIVE once a voice is selected);
* private owner   -- the same voice, warmer, more intimate, playful and flirtatious through
  prosody, pacing and delivery only; available only where the PRIV rules (owner-private
  principal, `app/command_center/private_context`) AND the underlying provider support it. It
  stays GATED: the private conversational register is not implemented, and the provider's usage
  policies are the outer limit, which this code does not try to bypass.

Hard rules (not tunable):
* A voice cloned from, or designed to imitate, a real person -- including the human Laura --
  requires that person's recorded consent (spec/07 Ruling 2). Without it qualification FAILS.
* Every acoustic reading must be MEASURED (method + sample count). An estimate, a provider's
  marketing description or a missing reading is UNKNOWN, and UNKNOWN fails.
* Perceptual qualities (attractiveness, warmth, natural sensuality, the exclusions...) are
  judged by the owner LISTENING, never auto-scored (`voice_selection.scorecard`).

Deterministic; no audio is generated or analysed here and no provider is called.
"""
from __future__ import annotations

import hashlib
import json

SPEC_VERSION = 2
SPEC_ID = f"laura-voice-v{SPEC_VERSION}"
DECISION_ID = "D-FB-18"

SPEC: dict = {
    "spec_id": SPEC_ID,
    "identity_id": "laura-r2-a42aeac7",      # the same Laura (visual.canonical.IDENTITY_ID)
    "decision_id": DECISION_ID,
    "owner_confirmation": "CONFIRMED (D-FB-18 item 6)",
    "supersedes": "laura-voice-v1",
    "derived_from": ["spec/07 item 6", "DECISION_LOG D-FB-13", "DECISION_LOG D-FB-16 item 8",
                     "DECISION_LOG D-FB-18 items 6-8"],
    "one_voice": "ONE canonical voice; registers are contexts of it -- no second voice or "
                 "separate persona",
    "vocal_character": {
        "description": "a naturally attractive adult woman's voice: smooth, warm, confident, "
                       "expressive, subtly sensual without performing a 'sexy voice'",
        "positive": ["distinctly feminine", "warm", "intelligent", "confident",
                     "naturally conversational", "charismatic", "attractive", "magnetic",
                     "smooth", "expressive", "subtly sensual (never performed)"],
        "excluded_performance": ["forced seduction", "exaggerated breathiness",
                                 "pornographic performance", "cartoonish sensuality",
                                 "fake whispering", "childish or youthful delivery",
                                 "character acting"],
        "excluded_cadence": ["corporate narrator", "customer-service script",
                             "radio announcer", "generic AI-assistant cadence",
                             "robotic TTS rhythm", "over-polished delivery"],
        "timbre": {"allowed": ["warm", "smooth", "clear"]},
        "breathiness": {"allowed": ["low", "natural"]},
    },
    "prosody": {
        "natural_conversational": ["natural pauses", "thinking cadence", "humour", "amusement",
                                   "warmth", "seriousness", "excitement", "reactions",
                                   "pacing changes",
                                   "natural interruption / turn-taking (Phase 3)"],
    },
    "accent_dialect": {
        "target": "natural Canadian / neutral North American English, subtle and authentic, "
                  "never exaggerated",
        "allowed": ["en-CA", "en-US-general"],
        "intensity": "subtle",
    },
    "apparent_age": {"target_years": 32, "range_years": [30, 34],
                     "note": "early 30s; must agree with the canonical visual identity"},
    "pitch": {"median_f0_hz": [165, 215], "f0_range_semitones": [4.0, 10.0]},
    "warmth": {"panel_score_1_to_5": [3.8, 5.0]},
    "pace": {"words_per_minute": [135, 170],
             "note": "conversational, with pacing changes; never a read-aloud monotone"},
    "energy": {"panel_score_1_to_5": [2.8, 3.9],
               "note": "calm confidence with real range (amusement, seriousness, excitement)"},
    "rhythm": {"pause_ms_between_sentences": [250, 700],
               "note": "natural pauses and thinking cadence; numbers read unhurried"},
    "pronunciation": {
        "lexicon": {
            "Brambleloop": "BRAM-bul-loop",
            "crochet": "kroh-SHAY",
            "amigurumi": "ah-mee-goo-ROO-mee",
            "skein": "SKAYN",
            "Etsy": "ET-see",
            "CA$": "Canadian dollars",
        },
        "required_accuracy": 1.0,
        "rules": ["figures are read exactly as written; 'UNKNOWN' is said as 'unknown', "
                  "never as zero", "currency is always named (Canadian dollars)"],
    },
    "registers": {
        "business": {
            "status": "ACTIVE",
            "surfaces": ["owner Command Center", "public/brand (when any public voice use is "
                         "separately authorised)"],
            "delivery": "polished and appropriate: Laura as Founder/CEO",
            "forbidden": ["claims to be human", "invented personal experiences",
                          "fake enthusiasm", "flirtation or intimacy"],
        },
        "private_owner": {
            "status": "GATED",
            "surfaces": ["owner-private context only (app/command_center/private_context)"],
            "delivery": "the same voice, warmer, more intimate, playful and flirtatious through "
                        "prosody, pacing and delivery only",
            "requires": ["owner-private principal (PRIV)", "provider support under its usage "
                         "policies", "the private conversational register (not implemented)"],
            "why_gated": "the private conversation register is not implemented (PRIV lane: "
                         "infrastructure only); a provider's usage policies bound what it "
                         "will voice; never on any business, public or customer surface",
        },
    },
}

#: Readings a candidate's evaluation must supply, each MEASURED.
REQUIRED_READINGS = ("median_f0_hz", "f0_range_semitones", "words_per_minute",
                     "pause_ms_between_sentences", "warmth_panel", "energy_panel",
                     "apparent_age_years", "accent", "timbre", "breathiness",
                     "pronunciation_accuracy")
MIN_SAMPLES = {"acoustic": 20, "panel": 5}
_PANEL = {"warmth_panel", "energy_panel", "apparent_age_years", "accent", "timbre",
          "breathiness"}


def spec_sha256(spec: dict | None = None) -> str:
    return hashlib.sha256(json.dumps(spec or SPEC, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


#: Pinned: editing v2 in place fails `test_w3_laura_voice_spec` -- publish v3 instead.
SPEC_SHA256 = spec_sha256()

#: Earlier versions, by id -> (pinned sha256, why superseded). History only; never used to
#: qualify a voice.
SUPERSEDED = {
    "laura-voice-v1": ("08f98c00318bef946ca3a7d6727f23288c09800c0b6695ac3386908613a6ca53",
                       "accent and apparent age were PROPOSED; resolved by owner decision "
                       "D-FB-18 item 6 (v2)"),
}


def _in(v, rng) -> bool:
    try:
        return float(rng[0]) <= float(v) <= float(rng[1])
    except (TypeError, ValueError, IndexError):
        return False


def _target(name: str):
    s = SPEC
    return {"median_f0_hz": ("range", s["pitch"]["median_f0_hz"]),
            "f0_range_semitones": ("range", s["pitch"]["f0_range_semitones"]),
            "words_per_minute": ("range", s["pace"]["words_per_minute"]),
            "pause_ms_between_sentences": ("range", s["rhythm"]["pause_ms_between_sentences"]),
            "warmth_panel": ("range", s["warmth"]["panel_score_1_to_5"]),
            "energy_panel": ("range", s["energy"]["panel_score_1_to_5"]),
            "apparent_age_years": ("range", s["apparent_age"]["range_years"]),
            "accent": ("set", s["accent_dialect"]["allowed"]),
            "timbre": ("set", s["vocal_character"]["timbre"]["allowed"]),
            "breathiness": ("set", s["vocal_character"]["breathiness"]["allowed"]),
            "pronunciation_accuracy": ("min", s["pronunciation"]["required_accuracy"]),
            }[name]


def qualify(candidate: dict, evaluation: dict) -> dict:
    """PASS only when every reading is MEASURED, sampled enough and inside the spec.

    candidate: {"provider", "voice_ref", "cloned_from_real_person": bool,
                "consent_record": str|None, "registers": [..]}
    evaluation: {"<reading>": {"value": .., "reading": "MEASURED", "method": str,
                               "samples": int}}, plus "pronunciation_items" {word: bool}.
    Returns {"verdict": PASS|FAIL, "spec_id", "spec_sha256", "checks": [...], "failures": [...]}
    """
    checks: list[dict] = []

    def add(name: str, ok: bool, why: str):
        checks.append({"check": name, "result": "PASS" if ok else "FAIL", "why": why})

    cand = candidate if isinstance(candidate, dict) else {}
    ev = evaluation if isinstance(evaluation, dict) else {}
    add("candidate_named", bool(cand.get("provider")) and bool(cand.get("voice_ref")),
        "a candidate names its provider and voice reference")
    cloned = cand.get("cloned_from_real_person")
    if cloned is None:
        add("real_person_consent", False, "UNKNOWN whether the voice imitates a real person; "
                                          "a provider must state it")
    elif cloned:
        add("real_person_consent", bool(cand.get("consent_record")),
            "a voice cloned from or imitating a real person needs that person's recorded "
            "consent (the AI never asserts the human Laura's consent)")
    else:
        add("real_person_consent", True, "provider states the voice is not a clone")
    regs = set(cand.get("registers") or ["business"])
    add("register_scope", "business" in regs and regs <= {"business", "private_owner"},
        "the business register is required; only defined registers are allowed")
    if "private_owner" in regs:
        add("private_register_gated", False, "the private owner register is GATED; a "
                                             "candidate cannot be qualified for it yet")

    for name in REQUIRED_READINGS:
        r = ev.get(name)
        if not isinstance(r, dict) or str(r.get("reading", "")).upper() != "MEASURED" \
                or r.get("value") is None or not r.get("method"):
            add(name, False, "UNKNOWN: not measured (an estimate or a provider description "
                             "is never a pass)")
            continue
        need = MIN_SAMPLES["panel" if name in _PANEL else "acoustic"]
        if int(r.get("samples") or 0) < need:
            add(name, False, f"only {r.get('samples') or 0} sample(s); needs >= {need}")
            continue
        kind, target = _target(name)
        v = r["value"]
        if kind == "range":
            add(name, _in(v, target), f"{v} must be within {target}")
        elif kind == "set":
            add(name, str(v) in target, f"{v!r} must be one of {target}")
        else:
            try:
                ok = float(v) >= float(target)
            except (TypeError, ValueError):
                ok = False
            add(name, ok, f"{v} must be >= {target}")
    items = ev.get("pronunciation_items")
    lex = SPEC["pronunciation"]["lexicon"]
    if not isinstance(items, dict):
        add("pronunciation_lexicon", False, "UNKNOWN: lexicon items not evaluated")
    else:
        missing = [w for w in lex if items.get(w) is not True]
        add("pronunciation_lexicon", not missing,
            "every lexicon word pronounced as specified" + (f"; failed/missing: {missing}"
                                                           if missing else ""))
    failures = [c for c in checks if c["result"] == "FAIL"]
    return {"verdict": "FAIL" if failures else "PASS", "spec_id": SPEC_ID,
            "spec_sha256": SPEC_SHA256, "candidate": {k: cand.get(k) for k in
                                                      ("provider", "voice_ref")},
            "checks": checks, "failures": failures}


def promotion_requirements(qualification: dict) -> dict:
    """What must be true before a qualified voice speaks as Laura (never automatic)."""
    passed = isinstance(qualification, dict) and qualification.get("verdict") == "PASS"
    return {"may_promote": False,
            "qualification": "PASS" if passed else "FAIL",
            "requires": ["qualification PASS against this exact spec version",
                         "a complete D-FB-18 scorecard: every perceptual criterion judged by "
                         "the owner LISTENING (voice_selection.scorecard)",
                         "owner listening decision id recorded in DECISION_LOG naming the "
                         "candidate (voice_selection.select)",
                         "owner spend authority for the voice provider (paid API / trial)",
                         "re-qualification on every provider/voice/model change"],
            "why": "promotion of a voice is an owner decision; this function only reports "
                   "what is missing"}


def public_view() -> dict:
    """The spec as the Command Center shows it (no private-register detail beyond GATED)."""
    out = json.loads(json.dumps(SPEC))
    out["registers"]["private_owner"] = {"status": "GATED",
                                         "why_gated": SPEC["registers"]["private_owner"]
                                         ["why_gated"]}
    out["spec_sha256"] = SPEC_SHA256
    out["required_readings"] = list(REQUIRED_READINGS)
    out["min_samples"] = dict(MIN_SAMPLES)
    return out
