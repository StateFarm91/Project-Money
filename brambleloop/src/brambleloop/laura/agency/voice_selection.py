"""Choosing Laura's voice (D-FB-18 item 7): candidate scorecard, owner listening, selection,
and the durable voice identity record.

The provider is an implementation detail; a voice is never locked because it approximately
matches. A candidate becomes canonical only when ALL of these hold:

1. `voice_spec.qualify()` PASSES (measured acoustic readings, pronunciation lexicon, consent
   rule, register scope) against the current spec version;
2. its `scorecard()` is complete: every D-FB-18 criterion PASSES. Perceptual criteria are the
   OWNER's (or a named human listener's) judgement after HEARING the reference samples -- a
   model, a metric or a provider description can never fill them; until heard they are
   UNKNOWN, and UNKNOWN never passes. Technical criteria need recorded measurements/evidence;
3. an owner listening decision id that is recorded in DECISION_LOG.md names it (`select()`).

Selection writes one hash-chained `laura_voice_identity` row: provider-independent
descriptors (from the spec) + the sha256 of the exact reference samples the owner heard. From
then on that record is her voice identity; any replacement (new provider, new voice, a model
update of the same voice) must requalify through the same path AND be judged by the owner as
recognisably the same voice as the locked reference (`same_voice_as_reference`).

No provider is called here and nothing is auto-selected. Listening needs provider access and,
for a paid trial, owner spend approval: `OWNER_ACTION` states it, with max cost UNKNOWN until a
provider is chosen.
"""
from __future__ import annotations

import hashlib
import json

from . import voice_spec

HUMAN_JUDGES = ("owner", "human_listener")
OWNER_ONLY = ("attractiveness", "natural_sensuality", "match_to_canonical_appearance",
              "same_voice_as_reference")

# (key, label, kind). kind: "listening" -> owner/human judgement after hearing samples;
# "measured" -> a recorded measurement; "evidence" -> a documented fact (terms, pricing...).
CRITERIA: tuple[tuple[str, str, str], ...] = (
    ("apparent_age", "Apparent age early 30s (30-34, ~32)", "listening"),
    ("match_to_canonical_appearance", "Matches Laura's canonical appearance", "listening"),
    ("femininity", "Distinctly feminine", "listening"),
    ("attractiveness", "Naturally attractive, magnetic", "listening"),
    ("warmth", "Warm", "listening"),
    ("natural_sensuality", "Subtly sensual without performing it", "listening"),
    ("intelligence_confidence", "Intelligent and confident", "listening"),
    ("conversational_naturalness", "Naturally conversational prosody", "listening"),
    ("emotional_range", "Emotional range (humour, seriousness, excitement, reactions)",
     "listening"),
    ("exclusions_absent", "None of the excluded performances or cadences is heard",
     "listening"),
    ("latency", "Latency: time to first audio (p50 ms) fit for conversation", "measured"),
    ("consistency", "Consistent across renders and sessions", "measured"),
    ("pronunciation", "Pronunciation lexicon exact", "measured"),
    ("provider_stability", "Provider stability (versioned voice, terms, uptime)", "evidence"),
    ("cost", "Cost per minute (CAD) known and within an owner-approved ceiling", "evidence"),
)
REPLACEMENT_CRITERIA = (("same_voice_as_reference",
                         "Recognisably the same voice as the locked reference samples",
                         "listening"),)
MAX_LATENCY_MS = 900


class SelectionRefused(ValueError):
    pass


OWNER_ACTION = {
    "requirement_key": "laura.voice.listen_shortlist",
    "action": "Listen to the shortlisted Laura voice candidates and choose one (or none)",
    "why": "D-FB-18 item 7: no voice becomes Laura's canonical voice until you have heard it; "
           "perceptual criteria (attractiveness, warmth, natural sensuality, match to her "
           "appearance, the exclusions) are your listening judgement, not a model's",
    "needs": ["provider access: a voice provider account/API key chosen by you",
              "paid trial approval: generating candidate samples is a paid call (owner spend "
              "approval required before any call)"],
    "max_cost": "UNKNOWN until a provider is chosen (per-character / per-minute pricing)",
    "max_cost_cad": None,
    "minutes": 20,
    "consequence_of_waiting": "Voice (Phase 2) and Live Presence (Phase 3) stay GATED; Talk to "
                              "Laura continues in text with no loss of identity, memory or "
                              "authority",
    "blocks": ["LAURA-VOICE-P2", "LAURA-LIVE-P3"],
    "status": "OPEN",
    "source": "DECISION_LOG D-FB-18 item 7",
}


def seed_owner_action(db) -> dict:
    """Put `OWNER_ACTION` into the one consolidated owner queue (W3-F wiring 5, W3-WIRE4).

    Idempotent on `requirement_key`: a row that already exists -- open, or answered by the
    owner -- is never re-added or re-opened. The cost is stored with basis UNKNOWN
    (`OwnerAction.max_cost_known` is None), so no surface renders it as CA$0.00 and no spend
    path treats it as free (finance.accounting.policy refuses an UNKNOWN ceiling)."""
    from sqlalchemy import select

    from ...core.models import MAX_COST_UNKNOWN, OwnerAction

    a = OWNER_ACTION
    key = a["requirement_key"]
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key)
                       .order_by(OwnerAction.id.desc()).limit(1))
        if row is not None:
            return {"seeded": False, "owner_action_id": int(row.id), "why": "already queued"}
        row = OwnerAction(
            requirement_key=key, action=a["action"], reason=a["why"],
            max_cost_cad=0.0, max_cost_basis=MAX_COST_UNKNOWN, minutes=int(a["minutes"]),
            consequence_of_delay=a["consequence_of_waiting"],
            blocks=", ".join(a["blocks"]),
            why_software_cannot=("a listening judgement and a provider/paid-trial choice are "
                                 "the owner's (D-FB-18 item 7); " + "; ".join(a["needs"])))
        s.add(row)
        s.flush()
        return {"seeded": True, "owner_action_id": int(row.id), "why": a["source"]}


def _judgement(key: str, kind: str, j) -> dict:
    """One criterion's reading. Never PASS without the right kind of evidence."""
    if not isinstance(j, dict):
        return {"criterion": key, "kind": kind, "result": "UNKNOWN",
                "why": "not heard yet" if kind == "listening" else "not measured/recorded"}
    verdict = str(j.get("verdict", "")).upper()
    if kind == "listening":
        judge = str(j.get("judge") or "")
        if judge not in HUMAN_JUDGES or j.get("auto") or j.get("basis") in ("model", "metric",
                                                                             "provider"):
            return {"criterion": key, "kind": kind, "result": "UNKNOWN",
                    "why": "only the owner or a named human listener judges this by hearing "
                           "it; an automatic score is never a pass"}
        if key in OWNER_ONLY and judge != "owner":
            return {"criterion": key, "kind": kind, "result": "UNKNOWN",
                    "why": "this criterion is the owner's own listening judgement"}
        if not j.get("heard_samples_sha256"):
            return {"criterion": key, "kind": kind, "result": "UNKNOWN",
                    "why": "a listening judgement names the samples heard (sha256)"}
    elif kind == "measured":
        if str(j.get("reading", "")).upper() != "MEASURED" or j.get("value") is None \
                or not j.get("method"):
            return {"criterion": key, "kind": kind, "result": "UNKNOWN",
                    "why": "UNKNOWN: not measured"}
        if key == "latency":
            try:
                verdict = "PASS" if float(j["value"]) <= MAX_LATENCY_MS else "FAIL"
            except (TypeError, ValueError):
                verdict = "FAIL"
    else:
        if not j.get("evidence"):
            return {"criterion": key, "kind": kind, "result": "UNKNOWN",
                    "why": "no recorded evidence"}
        if key == "cost" and j.get("value_cad_per_minute") is None:
            return {"criterion": key, "kind": kind, "result": "UNKNOWN",
                    "why": "cost UNKNOWN until a provider is chosen"}
    if verdict not in ("PASS", "FAIL"):
        return {"criterion": key, "kind": kind, "result": "UNKNOWN", "why": "no verdict"}
    return {"criterion": key, "kind": kind, "result": verdict,
            "judge": j.get("judge"), "note": str(j.get("note") or "")[:200],
            "heard": sorted(str(h).lower() for h in j.get("heard_samples_sha256") or [])}


def scorecard(candidate: dict, judgements: dict | None, *, replacement: bool = False) -> dict:
    """The D-FB-18 scorecard. COMPLETE only when every criterion PASSES."""
    j = judgements if isinstance(judgements, dict) else {}
    crit = CRITERIA + (REPLACEMENT_CRITERIA if replacement else ())
    rows = [dict(_judgement(k, kind, j.get(k)), label=label) for k, label, kind in crit]
    unknown = [r["criterion"] for r in rows if r["result"] == "UNKNOWN"]
    failed = [r["criterion"] for r in rows if r["result"] == "FAIL"]
    return {"candidate": {k: (candidate or {}).get(k) for k in ("provider", "voice_ref")},
            "spec_id": voice_spec.SPEC_ID, "criteria": rows,
            "verdict": "FAIL" if failed else ("INCOMPLETE" if unknown else "PASS"),
            "unknown": unknown, "failed": failed}


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def samples_digest(sample_hashes: list[str]) -> str:
    hs = sorted(str(h).lower() for h in sample_hashes or [])
    if not hs or not all(len(h) == 64 and all(c in "0123456789abcdef" for c in h) for h in hs):
        raise SelectionRefused("reference samples must be listed by sha256")
    return hashlib.sha256("\n".join(hs).encode()).hexdigest()


def current(db) -> dict | None:
    """The locked voice identity (latest version), verified, or None when none is selected."""
    from sqlalchemy import select

    from .models import LauraVoiceIdentity, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        rows = list(s.scalars(select(LauraVoiceIdentity).order_by(LauraVoiceIdentity.version)))
        prev = ""
        for r in rows:
            if _sha(r.record) != r.record_sha256 or r.prev_sha256 != prev:
                raise SelectionRefused(f"voice identity v{r.version} does not verify")
            prev = r.record_sha256
        if not rows:
            return None
        r = rows[-1]
        return {"version": r.version, "spec_id": r.spec_id, "owner_decision_id":
                r.owner_decision_id, "reference_samples_sha256": r.reference_samples_sha256,
                "record": dict(r.record), "record_sha256": r.record_sha256}


def select(db, candidate: dict, qualification: dict, card: dict, *, owner_decision_id: str,
           reference_samples: list[str], decision_recorded=None) -> dict:
    """Lock a candidate as Laura's canonical voice. Refuses unless every rule holds."""
    from .models import LauraVoiceIdentity

    if decision_recorded is None:
        from ..core.identity import decision_recorded
    if not isinstance(qualification, dict) or qualification.get("verdict") != "PASS" \
            or qualification.get("spec_sha256") != voice_spec.SPEC_SHA256:
        raise SelectionRefused("qualification must PASS against the current voice spec")
    prior = current(db)
    if prior is not None and not any(c["criterion"] == "same_voice_as_reference"
                                     for c in (card or {}).get("criteria") or []):
        raise SelectionRefused("a voice is already locked: a replacement must requalify "
                               "with the owner judging it the same voice as the reference")
    if not isinstance(card, dict) or card.get("verdict") != "PASS":
        raise SelectionRefused("the D-FB-18 scorecard is not complete: "
                               f"{(card or {}).get('verdict')} (unknown: "
                               f"{(card or {}).get('unknown')}, failed: "
                               f"{(card or {}).get('failed')})")
    if card.get("candidate") != {k: candidate.get(k) for k in ("provider", "voice_ref")}:
        raise SelectionRefused("the scorecard is for a different candidate")
    if not owner_decision_id or not decision_recorded(owner_decision_id):
        raise SelectionRefused("no canonical voice without an owner listening decision id "
                               "recorded in DECISION_LOG.md")
    digest = samples_digest(reference_samples)
    refs = {str(h).lower() for h in reference_samples}
    for c in card["criteria"]:
        if c["kind"] == "listening" and not set(c.get("heard") or []) <= refs:
            raise SelectionRefused(f"{c['criterion']} was judged on samples that are not the "
                                   f"reference samples being locked")
    record = {"identity_id": voice_spec.SPEC["identity_id"], "spec_id": voice_spec.SPEC_ID,
              "spec_sha256": voice_spec.SPEC_SHA256,
              "descriptors": {k: voice_spec.SPEC[k] for k in
                              ("vocal_character", "accent_dialect", "apparent_age", "prosody",
                               "pitch", "pace", "rhythm", "warmth", "energy")},
              "registers": {"business": "ACTIVE", "private_owner": "GATED"},
              "reference_samples_sha256": digest,
              "instrument": {"provider": candidate.get("provider"),
                             "voice_ref": candidate.get("voice_ref"),
                             "note": "replaceable instrument; replacement must requalify"},
              "owner_decision_id": owner_decision_id,
              "scorecard_sha256": _sha(card), "qualification_sha256": _sha(qualification)}
    rsha = _sha(record)
    version = 1 if prior is None else prior["version"] + 1
    with db.session() as s:
        s.add(LauraVoiceIdentity(version=version, spec_id=voice_spec.SPEC_ID,
                                 spec_sha256=voice_spec.SPEC_SHA256,
                                 owner_decision_id=owner_decision_id,
                                 reference_samples_sha256=digest, record=record,
                                 record_sha256=rsha,
                                 prev_sha256="" if prior is None else prior["record_sha256"]))
    return {"selected": True, "version": version, "record_sha256": rsha,
            "reference_samples_sha256": digest}


def status(db=None) -> dict:
    """For the Command Center: the spec, whether a voice is locked, and the owner action."""
    locked = None
    if db is not None:
        try:
            locked = current(db)
        except Exception as exc:  # noqa: BLE001 - a broken chain is reported, never hidden
            locked = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    return {"spec_id": voice_spec.SPEC_ID, "spec_sha256": voice_spec.SPEC_SHA256,
            "decision_id": voice_spec.DECISION_ID,
            "canonical_voice": locked or "NONE SELECTED (no candidate heard by the owner yet)",
            "criteria": [{"key": k, "label": label, "kind": kind} for k, label, kind in CRITERIA],
            "owner_action": OWNER_ACTION}
