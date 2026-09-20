"""Model Gateway (Master Plan section 27).

Every model call in the company goes through here, and the reason is not abstraction for its
own sake. It is that four separate things must be true of every call and none of them can be
left to the caller remembering:

  - The prompt is pinned by `name@version`, so a change in output can be attributed.
  - The output is parsed strictly and rejected if it is not the shape that was asked for. A
    half-populated object travelling downstream into a pattern or a listing is the failure we
    are actually guarding against.
  - The cost is recorded against the calling agent, so the spend guard can stop a runaway
    loop before it becomes a bill rather than after.
  - Failover is between *providers*, and a provider that is down opens a circuit rather than
    absorbing thousands of doomed calls.

And one rule outranks all of them, from section 27: **deterministic validation wins even if
every model disagrees.** The gateway exists to get useful text out of models. It has no
authority over whether a pattern is correct, and `require_deterministic` below refuses to let
a model verdict be used where the compiler has one.

No provider is configured in this repository and no API key exists here. The gateway
therefore ships with a deterministic `EchoProvider` for tests and refuses to pretend a real
provider is reachable: `available_providers()` reports what is actually wired, which is
currently nothing.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from ..agents.registry import Registry
from ..core.resilience import (
    CircuitBreaker, MalformedModelOutput, PermanentError, TransientError, parse_model_json,
)
from . import prompts as prompt_registry
from . import routing


class DeterministicAuthorityViolation(PermissionError):
    """A model verdict was offered where deterministic code already has one."""


class NoProviderAvailable(PermanentError):
    """Every configured provider is unavailable. Stated plainly rather than faked."""


@dataclass(frozen=True)
class ModelResponse:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class Provider(Protocol):
    name: str
    model: str
    cost_per_1k_input_cad: float
    cost_per_1k_output_cad: float

    def complete(self, system: str, user: str, *, max_tokens: int) -> ModelResponse: ...


@dataclass
class EchoProvider:
    """A deterministic stand-in so the whole pipeline is testable with no API key.

    It is not a mock of a model's judgement -- it cannot be. It is a mock of the *transport*:
    it exercises pinning, parsing, cost accounting, failover and the circuit breaker, which
    are the parts that break in production. Judgement is tested by eval fixtures instead.
    """

    name: str = "echo"
    model: str = "echo-1"
    cost_per_1k_input_cad: float = 0.0
    cost_per_1k_output_cad: float = 0.0
    scripted: Callable[[str, str], str] | None = None
    fail_times: int = 0
    _failures: int = 0

    def complete(self, system: str, user: str, *, max_tokens: int) -> ModelResponse:
        if self._failures < self.fail_times:
            self._failures += 1
            raise TransientError(f"{self.name}: simulated upstream failure")
        text = self.scripted(system, user) if self.scripted else "{}"
        return ModelResponse(text=text, provider=self.name, model=self.model,
                             input_tokens=len(user) // 4, output_tokens=len(text) // 4,
                             latency_ms=0.0)


def available_providers() -> list[str]:
    """What is actually reachable, based on configured credentials.

    Returns an empty list here, and that is the honest answer: no key is configured in this
    environment, so no real provider exists. Nothing in the system may claim otherwise.
    """
    out = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        out.append("anthropic")
    if os.environ.get("OPENAI_API_KEY"):
        out.append("openai")
    return out


@dataclass
class CallRecord:
    prompt_ref: str
    prompt_sha256: str
    provider: str
    model: str
    agent: str
    input_tokens: int
    output_tokens: int
    cost_cad: float
    attempts: int
    ok: bool
    error: str = ""

    def to_dict(self) -> dict:
        return {"prompt": self.prompt_ref, "prompt_sha256": self.prompt_sha256[:16],
                "provider": self.provider, "model": self.model, "agent": self.agent,
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "cost_cad": round(self.cost_cad, 6), "attempts": self.attempts,
                "ok": self.ok, "error": self.error[:200]}


class ModelGateway:
    def __init__(self, providers: list[Provider], registry: Registry | None = None,
                 breaker_threshold: int = 3, breaker_reset_seconds: float = 30.0,
                 job_id: int | None = None):
        """`job_id` is what makes a cost attributable to the artefact it produced (#31).

        Without it every model cost lands in the ledger with a null job, `unit_costs()` can
        match none of them to the audit row that made a pattern or a listing, and every
        artefact reports a cost *floor* while the money is real and counted. The ratios were
        correct arithmetic over an empty attribution the whole time -- the same shape as a
        scorer nobody feeds.
        """
        self.providers = list(providers)
        self.registry = registry
        self.job_id = job_id
        self.breakers = {
            p.name: CircuitBreaker(name=p.name, threshold=breaker_threshold,
                                   reset_after_seconds=breaker_reset_seconds)
            for p in self.providers
        }
        self.calls: list[CallRecord] = []

    # -- the one rule that outranks the rest --------------------------------
    @staticmethod
    def require_deterministic(question: str) -> None:
        """Refuse to let a model answer something the compiler already answers.

        Section 27: deterministic validation wins even if every LLM disagrees. This is a
        method rather than a comment so that a future caller reaching for a model verdict on
        pattern correctness gets an exception, not a code review.
        """
        raise DeterministicAuthorityViolation(
            f"{question!r} is decided by deterministic code, not by a model. If the compiler "
            f"and a model disagree, the compiler is right and the model is noise."
        )

    def complete_json(self, prompt_ref: str, *, agent: str, values: dict,
                      required: tuple[str, ...] | None = None,
                      max_attempts_per_provider: int = 2) -> dict:
        """Run a pinned prompt and return validated JSON, or raise.

        Failover is across providers in order. A provider whose circuit is open is skipped
        entirely rather than probed, because a probe on every call is the outage amplified.
        """
        prompt = prompt_registry.get(prompt_ref)
        user = prompt.render(**values)
        needed = required if required is not None else prompt.output_schema

        if not self.providers:
            raise NoProviderAvailable(
                "no model provider is configured. This is the real state of the system: no "
                "API key exists in this environment, and nothing may claim a model "
                "integration until one is verified.")

        last: Exception | None = None
        for provider in self.providers:
            breaker = self.breakers[provider.name]
            if breaker.is_open:
                continue
            for attempt in range(1, max_attempts_per_provider + 1):
                started = time.time()
                try:
                    response = breaker.call(
                        lambda: provider.complete(prompt.system, user,
                                                  max_tokens=prompt.max_output_tokens))
                    data = parse_model_json(response.text, required=tuple(needed))
                except MalformedModelOutput as e:
                    # A schema violation is the provider's fault, not the network's: retry
                    # this provider once, then move on rather than looping on bad output.
                    last = e
                    self._record(prompt, provider, agent, 0, 0, attempt, False, str(e))
                    if attempt >= max_attempts_per_provider:
                        break
                    continue
                except (TransientError, Exception) as e:  # noqa: BLE001
                    last = e
                    self._record(prompt, provider, agent, 0, 0, attempt, False, str(e))
                    if attempt >= max_attempts_per_provider:
                        break
                    continue
                cost = self._record(prompt, provider, agent, response.input_tokens,
                                    response.output_tokens, attempt, True, "")
                data["_meta"] = {
                    "prompt": prompt.ref, "prompt_sha256": prompt.sha256,
                    "provider": provider.name, "model": provider.model,
                    "cost_cad": round(cost, 6),
                    "latency_ms": round((time.time() - started) * 1000, 1),
                }
                return data

        assert last is not None
        raise last

    def _record(self, prompt, provider, agent: str, in_tok: int, out_tok: int,
                attempt: int, ok: bool, error: str) -> float:
        cost = (in_tok / 1000 * provider.cost_per_1k_input_cad
                + out_tok / 1000 * provider.cost_per_1k_output_cad)
        self.calls.append(CallRecord(
            prompt_ref=prompt.ref, prompt_sha256=prompt.sha256, provider=provider.name,
            model=provider.model, agent=agent, input_tokens=in_tok, output_tokens=out_tok,
            cost_cad=cost, attempts=attempt, ok=ok, error=error))
        if self.registry is not None and (cost > 0 or in_tok or out_tok):
            # Recorded even on the failed attempts that cost money, because a retry storm
            # that bills is exactly what the daily ceiling exists to catch.
            # `routing.COST_KIND`, not "model". These rows are what the monthly ceiling
            # counts, and a gateway writing a kind no ceiling reads is an unbounded budget
            # that reports CA$0.00.
            #
            # And recorded when the computed cost is zero but tokens were spent, which is the
            # condition that hid the worst of it. This used to be `cost > 0`, so a call
            # mispriced at zero wrote no row at all -- not a zero, *nothing*. A tournament
            # generated eighty concepts and left no trace in the ledger, and there were no
            # tokens stored to re-price it from afterwards. A zero-cost row carrying real
            # token counts is evidence that something is wrong with the price; silence is
            # indistinguishable from not having run.
            self.registry.record_cost(agent, cost, kind=routing.COST_KIND, tokens_in=in_tok,
                                      tokens_out=out_tok, job_id=self.job_id,
                                      detail={"prompt": prompt.ref,
                                              "provider": provider.name})
        return cost

    def spend_cad(self) -> float:
        return round(sum(c.cost_cad for c in self.calls), 6)

    def summary(self) -> dict:
        return {"calls": len(self.calls),
                "ok": sum(c.ok for c in self.calls),
                "failed": sum(not c.ok for c in self.calls),
                "cost_cad": self.spend_cad(),
                "providers": [p.name for p in self.providers],
                "open_circuits": [n for n, b in self.breakers.items() if b.is_open]}
