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

from ..agents.registry import BudgetExceeded, Registry
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
                 job_id: int | None = None, product_slug: str | None = None):
        """`job_id` is what makes a cost attributable to the artefact it produced (#31).

        Without it every model cost lands in the ledger with a null job, `unit_costs()` can
        match none of them to the audit row that made a pattern or a listing, and every
        artefact reports a cost *floor* while the money is real and counted. The ratios were
        correct arithmetic over an empty attribution the whole time -- the same shape as a
        scorer nobody feeds.

        `product_slug` does the same for the product (F-321/F-324): left as None it is read
        at call time from the running job (`spend_report.attributed_to`), so a gateway built
        inside a product job bills that product and one built anywhere else bills shared.
        """
        self.providers = list(providers)
        self.registry = registry
        self.job_id = job_id
        self.product_slug = product_slug
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
                # The ceiling, the agent's daily permission and a reservation, *before* the
                # provider is asked -- and outside the retry `try`, because a refusal is not a
                # provider fault to retry past. Until 2026-09-26 this path billed through
                # `registry.record_cost`, which checks the permission after the answer and the
                # authorised month not at all: a measurement, not a control, and the one model
                # path the cross-process reservation never touched. Only when a registry (and
                # so a database) is attached; a gateway with neither has nothing to check
                # against and no ledger to bill, which is the test configuration and no other.
                reservation = None
                if self.registry is not None:
                    from . import anthropic as gw

                    reservation = gw.check_budget_cad(
                        self.registry.db,
                        estimate_cad=self._estimate_cad(prompt, provider, user),
                        agent=agent, purpose=prompt.ref, job_id=self.job_id,
                        model=provider.model, provider=provider.name,
                        product_slug=self.product_slug or "")
                started = time.time()
                response = None
                try:
                    response = breaker.call(
                        lambda: provider.complete(prompt.system, user,
                                                  max_tokens=prompt.max_output_tokens))
                    data = parse_model_json(response.text, required=tuple(needed))
                except Exception as e:  # noqa: BLE001 - every failure is billed or not, below
                    # RC1 audit B1: a provider that answered has billed, whatever the answer
                    # looked like. This recorded 0 tokens for a malformed reply, so a retry
                    # loop on bad JSON was real spend the month never saw. `_billing` says
                    # what each failure cost and on what basis.
                    last = e
                    in_tok, out_tok, override, basis = self._billing(
                        e, response, reservation)
                    self._record(prompt, provider, agent, in_tok, out_tok, attempt, False,
                                 str(e), reservation=reservation, cost_override=override,
                                 billing=basis,
                                 latency_ms=(time.time() - started) * 1000)
                    # A schema violation is the provider's fault, not the network's: retry
                    # this provider once, then move on rather than looping on bad output.
                    if attempt >= max_attempts_per_provider:
                        break
                    continue
                elapsed_ms = (time.time() - started) * 1000
                # A useful answer whose usage block is missing is still a billed call; its
                # cost is UNKNOWN and counted at the estimate (B1), never as nothing.
                in_tok, out_tok, override, basis = self._billing(None, response, reservation)
                cost = self._record(prompt, provider, agent, in_tok, out_tok, attempt, True,
                                    "", latency_ms=elapsed_ms, reservation=reservation,
                                    cost_override=override, billing=basis)
                data["_meta"] = {
                    "prompt": prompt.ref, "prompt_sha256": prompt.sha256,
                    "provider": provider.name, "model": provider.model,
                    "cost_cad": round(cost, 6),
                    "latency_ms": round(elapsed_ms, 1),
                }
                return data

        assert last is not None
        raise last

    def _estimate_cad(self, prompt, provider, user: str) -> float:
        """What this call may cost, padded, assuming the model writes its whole allowance.

        Priced from the one table that bills (`anthropic.PRICES_USD_PER_MTOK`) when the model
        is in it, and from the provider's own declared per-1k rates -- padded the same way --
        when it is not, so a stand-in provider is checked against what it says it costs
        rather than refused as unpriced. Zero-cost stand-ins therefore pass the month and
        still bind on the agent's permission once that permission is spent.
        """
        from . import anthropic as gw

        in_tok = (len(prompt.system) + len(user)) // 4
        out_tok = int(prompt.max_output_tokens)
        try:
            return gw.estimate_cad(provider.model, input_tokens=in_tok, output_tokens=out_tok)
        except gw.BudgetExceeded as unpriced:
            rate_in = float(provider.cost_per_1k_input_cad or 0.0)
            rate_out = float(provider.cost_per_1k_output_cad or 0.0)
            if self.registry is not None and not (rate_in > 0 or rate_out > 0):
                # Certification C-35: with a ledger attached, an unpriced model whose own
                # rates are zero would be estimated at CA$0 and billed at CA$0 however many
                # tokens it used. Refused before the call (fail closed), with the refusal
                # recorded; a stand-in that declares a nonzero rate is still usable.
                from ..finance import spend_report

                message = (f"{provider.model!r} ({provider.name}) has no price on file and "
                           f"declares zero rates, so what it spends cannot be counted "
                           f"against the ceiling. An unpriced call is an unbounded one")
                spend_report.record_refusal(
                    self.registry.db, agent="", ceiling_cad=gw.monthly_ceiling_cad(),
                    estimate_cad=0.0, committed_cad=0.0, which="unpriced_model",
                    why=message, purpose=prompt.ref,
                    detail={"model": provider.model, "provider": provider.name,
                            "job_id": self.job_id})
                raise gw.BudgetExceeded(message) from unpriced
            cad = in_tok / 1000 * rate_in + out_tok / 1000 * rate_out
            return round(cad * gw.ESTIMATE_PADDING, 6)

    @staticmethod
    def _billing(exc: BaseException, response, reservation: dict | None
                 ) -> tuple[int, int, float | None, str]:
        """(input tokens, output tokens, cost override, basis) for one failed attempt.

        * The provider answered (`response` exists): it billed. Usage from the response; if
          the response reports no usage at all the bill is UNKNOWN, and UNKNOWN is counted at
          the reservation's estimate rather than as zero.
        * The exception carries `billed_usage` (input, output): that usage.
        * A timeout waiting for the answer, or a failure that is neither a transient fault
          nor a refusal (a body that would not parse after a 200, say): the request reached
          the provider and whether it billed is UNKNOWN -- counted at the estimate.
        * A transient fault or a refusal raised before any answer (HTTP 429/5xx, 4xx,
          unreachable, open circuit): the provider declined the work and did not bill.
        """
        estimate = float((reservation or {}).get("estimate_cad") or 0.0)
        if response is not None:
            in_tok = int(getattr(response, "input_tokens", 0) or 0)
            out_tok = int(getattr(response, "output_tokens", 0) or 0)
            if in_tok or out_tok:
                return in_tok, out_tok, None, "response_usage"
            return 0, 0, estimate, "unknown_usage_counted_at_estimate"
        usage = getattr(exc, "billed_usage", None)
        if usage:
            return int(usage[0] or 0), int(usage[1] or 0), None, "exception_usage"
        if isinstance(exc, TimeoutError) or not isinstance(
                exc, (TransientError, PermanentError, BudgetExceeded)):
            return 0, 0, estimate, "unknown_counted_at_estimate"
        return 0, 0, None, "not_billed"

    def _record(self, prompt, provider, agent: str, in_tok: int, out_tok: int,
                attempt: int, ok: bool, error: str, latency_ms: float = 0.0,
                reservation: dict | None = None, cost_override: float | None = None,
                billing: str = "response_usage") -> float:
        cost = (in_tok / 1000 * provider.cost_per_1k_input_cad
                + out_tok / 1000 * provider.cost_per_1k_output_cad)
        if cost_override is not None:
            cost = max(cost, float(cost_override))
        billed = ok or billing != "not_billed"
        self.calls.append(CallRecord(
            prompt_ref=prompt.ref, prompt_sha256=prompt.sha256, provider=provider.name,
            model=provider.model, agent=agent, input_tokens=in_tok, output_tokens=out_tok,
            cost_cad=cost, attempts=attempt, ok=ok, error=error))
        if self.registry is not None and not (billed and (cost > 0 or in_tok or out_tok)):
            # Nothing billed: the claim comes back without a bill, so a declined attempt
            # never reads as a charge.
            if reservation is not None:
                from . import anthropic as gw

                gw.release_reservation(self.registry.db, reservation.get("reservation_id"))
        elif self.registry is not None:
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
            #
            # Certification C-34: the row carries provider, model, purpose and the estimate
            # the reservation was made on, so `estimate_drift` reconciles it and a provider
            # ceiling (read from the ledger by provider) binds on gateway spend.
            # `Registry.record_cost` writes none of those, so the row is written here with
            # the same order that method keeps: write first, then refuse on the agent's day.
            from ..core.models import CostEntry
            from ..finance import spend_report

            estimated = float((reservation or {}).get("estimate_cad") or 0.0)
            product_slug, attributed = spend_report.attribution(self.product_slug or "", {
                "prompt": prompt.ref, "provider": provider.name,
                "latency_ms": round(latency_ms, 1),
                "reservation_id": (reservation or {}).get("reservation_id"),
                "ok": bool(ok), "billing": billing,
                "price_basis": "assumed",
                **({"cost_basis_note": "provider billing UNKNOWN; counted at the "
                                       "reservation estimate, never as zero"}
                   if cost_override is not None else {})})
            with self.registry.db.session() as s:
                s.add(CostEntry(
                    agent=agent, amount_cad=cost, kind=routing.COST_KIND, job_id=self.job_id,
                    tokens_in=in_tok, tokens_out=out_tok, provider=provider.name[:40],
                    model=str(provider.model or "")[:80], purpose=prompt.ref[:60],
                    estimated_cad=round(estimated, 6), product_slug=product_slug,
                    # #31 asks for agent/API *minutes* as well as dollars. The latency is
                    # already measured for the response; persisting it is what makes the
                    # minutes half of that requirement a query rather than a number nobody
                    # kept.
                    detail=attributed))
            # Released *after* the cost row exists (RC1 audit B4): released first, there was
            # an instant in which neither the claim nor the bill was counted, and a
            # concurrent check could spend the same money. Before the daily-ceiling refusal
            # below, so a refusal never leaves the claim holding budget for its TTL.
            if reservation is not None:
                from . import anthropic as gw

                gw.release_reservation(self.registry.db, reservation.get("reservation_id"),
                                       actual_cad=cost)
            ceiling = self.registry.get(agent).daily_cost_ceiling_cad
            if self.registry.spend_today(agent) > ceiling:
                raise BudgetExceeded(
                    f"agent {agent!r} would exceed its daily ceiling of CA${ceiling:.2f}")
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
