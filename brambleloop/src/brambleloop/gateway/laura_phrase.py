"""Optional model phrasing of a business statement Laura has already decided (lane F).

The routing task is `laura.business_phrase` (cheap tier, 220 output tokens, no stronger
fallback). The decision, every figure and every fact are made by code before this is called;
the model is only allowed to reword them. So the deterministic sentence the caller passes in
is always a complete answer, and this module returns it whenever paying for a rewording is not
possible or not safe:

* the task's own allocation (`spend_policy.ALLOCATION["laura.business_phrase@1"]`) is spent;
* the month's ceiling, the agent's daily cap or model health parks the call (`Parked`);
* no provider is configured (no key in this environment -- the normal test state);
* the answer adds a number that is not in the facts, is empty, or is too long.

Spend recording is the gateway's single path (`ModelGateway._record`, reserved before the
call by `anthropic.check_budget_cad`, guarded by `paid_calls` inside a job). An identical
request is answered from the content-keyed cache and is not paid for twice (F-306/F-311).
"""
from __future__ import annotations

import json
import re

from . import prompts, routing

TASK = "laura.business_phrase"
MAX_CHARS = 600

PROMPT = prompts.register(prompts.Prompt(
    name=TASK, version="1",
    system=("You reword one short business update for the owner of a crochet pattern studio, "
            "in the voice of Laura, the studio's AI chief executive: warm, plain, decisive, "
            "brief. The decision and every fact are given to you and are final. Do not add, "
            "remove or change any fact, number, date, amount or name. Never say or imply Laura "
            "is human, did anything physical, or owns anything legally. At most three "
            "sentences. Reply with JSON only."),
    template=("Decided statement:\n{statement}\n\nFacts (JSON):\n{facts}\n\n"
              "JSON: {{\"text\": \"...\"}}"),
    output_schema=("text",),
    max_output_tokens=routing.TASKS[TASK].max_output_tokens))

from ..finance.spend_policy import ALLOCATION as _ALLOCATION  # noqa: E402

assert PROMPT.ref in _ALLOCATION, "the phrasing prompt must carry its own allocation stop"

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER.findall(text or "")}


def validate(text: str, *, statement: str, facts: dict) -> str | None:
    """The reason a model rewording is refused, or None. Deterministic; it always wins."""
    if not isinstance(text, str) or not text.strip():
        return "empty answer"
    if len(text) > MAX_CHARS:
        return f"longer than {MAX_CHARS} characters"
    allowed = _numbers(statement) | _numbers(json.dumps(facts, sort_keys=True, default=str))
    added = sorted(_numbers(text) - allowed)
    if added:
        return f"adds figures the facts do not contain: {added}"
    return None


def phrase(db, *, statement: str, facts: dict | None = None, agent: str = "orchestrator",
           registry=None, job_id: int | None = None, provider_factory=None) -> dict:
    """{text, source: model|cache|deterministic, reason, cost_cad}. Never raises for money,
    health or a missing provider; the deterministic `statement` is the fallback.

    `agent` defaults to `orchestrator` (the registered CEO agent Laura acts through), whose
    daily cap and permissions the gateway checks before reserving."""
    from ..agents.registry import PermissionDenied
    from ..finance import spend_policy
    from .failover import Parked, gateway_for
    from .model_gateway import NoProviderAvailable

    facts = dict(facts or {})
    payload = {"prompt": PROMPT.ref, "statement": statement, "facts": facts}

    def _plain(reason: str) -> dict:
        return {"text": statement, "source": "deterministic", "reason": reason,
                "cost_cad": 0.0}

    allowance = spend_policy.may_spend(db, PROMPT.ref)
    if not allowance.get("may_spend", False):
        return _plain(f"allocation spent: {allowance.get('why', '')}")
    if registry is None:
        from ..agents.registry import Registry

        registry = Registry(db)
    try:
        gateway, decision = gateway_for(db, TASK, registry=registry, agent=agent,
                                        job_id=job_id, payload=payload,
                                        provider_factory=provider_factory)
    except Parked as exc:
        return _plain(f"parked: {exc}")
    except routing.TaskRefused as exc:
        return _plain(f"refused: {exc}")
    except NoProviderAvailable as exc:
        return _plain(f"no provider: {exc}")
    if gateway is None:
        cached = (decision.cached or {}).get("text", "")
        why = validate(cached, statement=statement, facts=facts)
        if why is None:
            return {"text": cached, "source": "cache", "reason": decision.reason,
                    "cost_cad": 0.0}
        return _plain(f"cached answer refused: {why}")
    try:
        data = gateway.complete_json(PROMPT.ref, agent=agent, values={
            "statement": statement, "facts": json.dumps(facts, sort_keys=True, default=str)},
            max_attempts_per_provider=1)
    except NoProviderAvailable as exc:
        return _plain(f"no provider: {exc}")
    except (PermissionError, PermissionDenied) as exc:  # ceiling / agent cap at reservation
        return _plain(f"budget: {exc}")
    except Exception as exc:  # noqa: BLE001 - the call is billed by the gateway either way
        return _plain(f"model call failed ({type(exc).__name__}); deterministic text kept")
    text = str(data.get("text") or "").strip()
    cost = float((data.get("_meta") or {}).get("cost_cad") or 0.0)
    why = validate(text, statement=statement, facts=facts)
    if why is not None:
        out = _plain(f"model answer refused: {why}")
        out["cost_cad"] = cost
        return out
    routing.remember_analysis(db, TASK, payload, {"text": text}, agent=agent)
    return {"text": text, "source": "model", "reason": decision.reason, "cost_cad": cost}
