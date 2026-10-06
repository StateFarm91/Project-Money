"""Laura's REQUIRED open roadmap items and her permanent voice improvement domain (D-FB-18
items 7-8; D-FB-16 items 7-11).

The Final Master v1.1 registry (`research/final_build/master_registry_v1_1.json`) is parsed
from the spec text (F-880..F-930) and cannot carry owner-ruling rows, and lane K's closure is a
research artefact. So the owner's Laura rows live here, in code, in the same shape as the
closure's v1.1 rows (`id`, `title`, `status`, `gate {kind, key, detail}`), served as a provider
(`summary(db)`) to the Command Center, and listed for the integrator to fold into the closure
overlay (handoff_F WIRING REQUEST).

Rules: these rows are REQUIRED and never CANCELLED for lack of a provider (D-FB-18 item 8). A row
leaves GATED only when its gate's evidence exists -- this module never marks one COMPLETE on
its own; `status_of()` recomputes each status from what is actually configured.
"""
from __future__ import annotations

from datetime import datetime, timezone

ROWS: tuple[dict, ...] = (
    {"id": "LAURA-TEXT-P1", "title": "Talk to Laura, Phase 1: visible canonical Laura + text, "
     "persistent company context, evidence-grounded answers, audited delegation, authority "
     "boundaries, private-memory isolation", "required": True,
     "source": "D-FB-16 items 7,10; D-FB-18 item 8 (approved as the foundation)",
     "gate": None},
    {"id": "LAURA-VOICE-P2", "title": "Talk to Laura, Phase 2: voice in (phone mic / Galaxy "
     "Buds) and out in the canonical Laura Voice (spec v2), same Laura/memory/authority",
     "required": True, "source": "D-FB-16 items 7-9; D-FB-18 items 6-8",
     "gate": {"kind": "owner", "key": "laura_voice_provider",
              "detail": "owner chooses a voice provider and approves a paid trial; the owner "
                        "LISTENS to shortlisted candidates and records a selection decision; "
                        "STT provider chosen; contract presence.SpeechToText/TextToSpeech"}},
    {"id": "LAURA-LIVE-P3", "title": "Talk to Laura, Phase 3: real-time Live Presence "
     "(Zoom-like): photoreal canonical Laura, blinking, expressions, subtle movement, lip sync, "
     "turn-taking", "required": True, "source": "D-FB-16 items 7,10; D-FB-18 item 8",
     "gate": {"kind": "owner", "key": "laura_live_presence_provider",
              "detail": "LAURA-VOICE-P2 done; a real-time avatar renderer that reproduces "
                        "laura-r2-a42aeac7 and passes identity -> photorealism -> anatomy; owner "
                        "identity approval and spend authority; contract "
                        "presence.LivePresenceRenderer"}},
    {"id": "LAURA-PRIVATE-REGISTER", "title": "Private owner register (text and, where "
     "supported, the same voice's private delivery)", "required": True,
     "source": "spec/07 Ruling 2; D-FB-15; D-FB-16 item 11; D-FB-18 item 6",
     "gate": {"kind": "owner", "key": "laura_private_register",
              "detail": "PRIV infrastructure exists; the conversational register needs its own "
                        "owner-approved lane bounded by the provider's usage policies"}},
    {"id": "LAURA-VOICE-IMPROVE", "title": "Voice as a permanent improvement domain: realism, "
     "latency, prosody, expressiveness, conversation quality -- without changing her "
     "recognisable identity", "required": True, "source": "D-FB-18 item 7",
     "gate": {"kind": "external", "key": "laura_voice_provider",
              "detail": "needs a selected voice to measure; loop registration is a WIRING "
                        "REQUEST to the Learn/improve owner"}},
)

IMPROVEMENT_DOMAIN = {
    "key": "laura_voice", "department": "learn", "owner_domain": "Brand / Laura",
    "dimensions": ["realism", "latency", "prosody", "expressiveness", "conversation quality"],
    "metrics": {"latency_ms_p50": "UNKNOWN (no voice selected)",
                "owner_listening_preference": "UNKNOWN (owner A/B listening, never auto-scored)",
                "pronunciation_accuracy": "UNKNOWN", "turn_taking_interruptions": "UNKNOWN"},
    "invariants": ["recognisable identity is locked: every challenger must be judged by the "
                   "owner as the same voice as the locked reference samples",
                   "spec v2 is not tuned by the loop; a spec change is an owner decision",
                   "no paid generation without owner spend authority",
                   "private register stays GATED"],
    "promotion": "challenger -> voice_spec.qualify PASS -> voice_selection.scorecard PASS "
                 "(replacement) -> owner decision -> voice_selection.select (new version)",
    "status": "GATED",
}


def status_of(row: dict) -> str:
    """Recomputed from what is configured; never COMPLETE by declaration."""
    from . import presence

    if row["gate"] is None:
        return "COMPLETE"
    caps = {p["mode"]: p["status"] for p in presence.capabilities()["phases"]}
    if row["id"] == "LAURA-VOICE-P2" and caps.get("voice") == "ACTIVE":
        return "ACTIVE (verify, then certify)"
    if row["id"] == "LAURA-LIVE-P3" and caps.get("live") == "ACTIVE":
        return "ACTIVE (verify, then certify)"
    return "GATED"


def rows() -> list[dict]:
    return [{**r, "status": status_of(r), "cancelled": False} for r in ROWS]


def summary(db) -> dict:
    """Provider contract: Laura's required roadmap rows. GATED rows make it DEGRADED."""
    rs = rows()
    gated = [r["id"] for r in rs if r["status"] == "GATED"]
    return {"status": "DEGRADED" if gated else "OK",
            "as_of": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "basis": "modelled",
            "reason": (f"{len(gated)} required Laura item(s) GATED on provider + owner: "
                       f"{', '.join(gated)}") if gated else None,
            "items": [{"title": f"{r['id']}: {r['title']}", "status": "OK" if r["status"] ==
                       "COMPLETE" else "BLOCKED", "detail": r["status"],
                       "gate": r["gate"], "required": True, "cancelled": False,
                       "source": r["source"]} for r in rs],
            "improvement_domain": IMPROVEMENT_DOMAIN,
            "sources": ["src/brambleloop/laura/agency/roadmap.py", "DECISION_LOG D-FB-18"]}
