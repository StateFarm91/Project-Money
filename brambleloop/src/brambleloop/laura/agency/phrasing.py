"""Optional model phrasing of Laura's deterministic answer -- off unless explicitly enabled.

The answer Laura gives is always assembled deterministically from source-linked facts
(`talk.py`). A model may only *rephrase* it in her voice, and only:

* through `gateway.model_gateway.ModelGateway` (pinned prompt, spend recorded against the
  calling agent's ceiling, provider failover) -- never a direct provider call;
* when enabled: `BRAMBLELOOP_LAURA_PHRASING=1` *and* a real provider is configured, or a
  caller hands in a gateway explicitly (tests use the transport-only EchoProvider);
* and the rephrasing must preserve every number and every UNKNOWN in the deterministic
  answer and introduce no number that was not in it. Otherwise it is discarded and the
  deterministic answer stands (deterministic wins, Master Plan section 27).

The model is cognition, not Laura (D-FB-13): the identity, voice spec and facts come from
durable state; swapping or removing the model changes wording at most, never content.
"""
from __future__ import annotations

import json
import os
import re

from ...gateway import laura_phrase

PHRASING_ENV = "BRAMBLELOOP_LAURA_PHRASING"
AGENT = "orchestrator"   # billed against an existing registry agent's ceiling
ROUTING_TASK = "laura.business_phrase"

# One prompt for Laura's business phrasing: lane SPEND's `gateway.laura_phrase` registers
# `laura.business_phrase@1` (its own allocation stop, cheap tier). Registering a second text
# under the same ref would raise `PromptIsImmutable` the moment both modules are imported.
PROMPT = laura_phrase.PROMPT

_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def enabled() -> bool:
    from ...gateway.model_gateway import available_providers

    return os.environ.get(PHRASING_ENV, "").strip() == "1" and bool(available_providers())


def preserves_facts(original: str, phrased: str) -> bool:
    """Every number and UNKNOWN survives; no new number appears."""
    if not phrased or not phrased.strip():
        return False
    a, b = set(_NUM.findall(original)), set(_NUM.findall(phrased))
    if a != b:
        return False
    if original.count("UNKNOWN") > phrased.count("UNKNOWN"):
        return False
    return True


def phrase(db, answer: str, *, gateway=None, facts: dict | None = None) -> tuple[str, dict]:
    """(text, meta). Falls back to `answer` on any refusal, error or fact drift.

    Production path (no `gateway` handed in): lane SPEND's `gateway.laura_phrase.phrase` --
    the registered `laura.business_phrase` routing task with its own allocation stop, month
    ceiling, agent cap, health parking, content cache and deterministic validation. Its
    answer must then also pass this module's own check (every number and UNKNOWN kept)."""
    meta = {"phrased": False, "method": "deterministic template"}
    if gateway is None:
        if not enabled():
            return answer, meta
        try:
            out = laura_phrase.phrase(db, statement=answer, facts=dict(facts or {}),
                                      agent=AGENT)
        except Exception as exc:  # noqa: BLE001 - deterministic answer stands
            meta["phrasing_skipped"] = f"laura_phrase failed: {type(exc).__name__}"
            return answer, meta
        text = str(out.get("text") or "")
        if out.get("source") not in ("model", "cache"):
            meta["phrasing_skipped"] = str(out.get("reason") or "deterministic")[:200]
            return answer, meta
        if not preserves_facts(answer, text):
            meta["phrasing_skipped"] = "rephrasing changed facts; deterministic answer kept"
            meta["cost_cad"] = out.get("cost_cad")
            return answer, meta
        return text, {"phrased": True, "method": f"deterministic facts, phrased via gateway "
                                                  f"{laura_phrase.PROMPT.ref} ({out['source']})",
                      "cost_cad": out.get("cost_cad")}
    try:
        out = gateway.complete_json(PROMPT.ref, agent=AGENT, values={
            "statement": answer,
            "facts": json.dumps(dict(facts or {}), sort_keys=True, default=str)})
    except Exception as exc:  # noqa: BLE001 - budget refusal, provider down, bad JSON
        meta["phrasing_skipped"] = f"gateway refused or failed: {type(exc).__name__}"
        return answer, meta
    text = str(out.get("text") or "")
    if out.get("changed_facts") or not preserves_facts(answer, text):
        meta["phrasing_skipped"] = "rephrasing changed facts; deterministic answer kept"
        return answer, meta
    m = out.get("_meta") or {}
    return text, {"phrased": True,
                  "method": f"deterministic facts, phrased via gateway {PROMPT.ref} "
                            f"({m.get('provider')}/{m.get('model')})",
                  "cost_cad": m.get("cost_cad"), "prompt_sha256": m.get("prompt_sha256")}
