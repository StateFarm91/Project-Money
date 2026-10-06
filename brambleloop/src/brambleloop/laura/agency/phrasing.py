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

import os
import re

from ...gateway import prompts as prompt_registry

PHRASING_ENV = "BRAMBLELOOP_LAURA_PHRASING"
AGENT = "orchestrator"   # billed against an existing registry agent's ceiling
ROUTING_TASK = "laura.business_phrase"

PROMPT = prompt_registry.register(prompt_registry.Prompt(
    name="laura.business_phrase", version="1",
    system=("You are the wording layer for Laura, the AI Founder/CEO of Brambleloop, speaking "
            "to the company owner about the business. Rephrase the ANSWER in her voice: warm, "
            "intelligent, confident, calm, concise, first person. You may reorder and "
            "rephrase. You may not add, remove or change any fact, number, date, name or the "
            "word UNKNOWN; you may not add claims, feelings presented as experiences, or "
            "advice that is not in the answer. Never claim to be human or to have done "
            "physical things. Reply with JSON only."),
    template=("ANSWER:\n{answer}\n\nJSON: {{\"text\": \"...\", \"changed_facts\": false}}"),
    output_schema=("text", "changed_facts"), max_output_tokens=600))

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


def phrase(db, answer: str, *, gateway=None) -> tuple[str, dict]:
    """(text, meta). Falls back to `answer` on any refusal, error or fact drift."""
    meta = {"phrased": False, "method": "deterministic template"}
    if gateway is None:
        if not enabled():
            return answer, meta
        try:
            from ...agents.registry import Registry
            from ...gateway import failover

            # Routed, budgeted and parked like every other model task. Until a routing task
            # named ROUTING_TASK is registered (a gateway-owner wiring item), routing refuses
            # and the deterministic answer stands.
            gateway, _decision = failover.gateway_for(db, ROUTING_TASK, registry=Registry(db),
                                                      agent=AGENT)
            if gateway is None:
                raise LookupError("cached decision has no gateway")
        except Exception as exc:  # noqa: BLE001 - no gateway: deterministic answer stands
            meta["phrasing_skipped"] = f"no gateway: {type(exc).__name__}"
            return answer, meta
    try:
        out = gateway.complete_json(PROMPT.ref, agent=AGENT, values={"answer": answer})
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
