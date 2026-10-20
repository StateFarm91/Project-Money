"""Venice AI: the Private Laura provider (owner ruling D-W4-PL-VENICE, spec/13 ADD-PLV-01..08).

This is a TRANSPORT for the one existing Private Laura reply path
(`gateway.laura_register.reply`). It is not a second chat system: the pinned prompt, the
encrypted private store, the owner-only context, the `laura_private` agent and its atomic
CA$0.50/day reservation are all the existing ones. This module only knows how to put one
already-built (system, user) pair on the wire to Venice and read the answer back.

Facts used here, from Venice's official documentation and API (read 2026-10-20; the full
citations are in research/final_build/w4/VENICE.md):

* Base URL `https://api.venice.ai/api/v1`; OpenAI-compatible `POST /chat/completions`;
  auth `Authorization: Bearer <key>` (docs.venice.ai/overview/getting-started).
* `venice_parameters.include_venice_system_prompt` DEFAULTS TO TRUE (Venice adds its own
  system prompt beside ours). It is sent as FALSE so the pinned prompt
  `laura.private_reply@3` -- the canonical identity laura-r2-a42aeac7 and the truthful-AI
  clauses -- is the only system prompt the model sees.
* `enable_web_search` is sent "off" and web scraping/citations false: private text must
  never become a search query to a third party.
* The approved default `venice-uncensored-1-2` (owner ruling 2026-10-20) is not a reasoning
  model and gets no reasoning parameters. `zai-org-glm-5-2` (still eligible, selectable by the
  owner) is a reasoning model whose DEFAULT effort is "max"; for it `reasoning_effort: "none"`
  and `disable_thinking: true` are sent. `max_completion_tokens` caps visible plus reasoning
  output either way.
* Eligibility (`eligible`): Venice-hosted AND Private class ("Zero data retention,
  contract-enforced ... not retained after the request completes", docs.venice.ai/overview/
  privacy) AND a pinned price row. Anonymized models (the upstream provider sees the prompt)
  and unknown classifications are REFUSED; a live Venice reading that contradicts the pinned
  verified row fails closed.
* Errors (docs.venice.ai/api-reference/error-codes): 401 AUTHENTICATION_FAILED*, 402
  INSUFFICIENT_BALANCE / API_KEY_*_SPEND_LIMIT_EXCEEDED, 403 UNAUTHORIZED /
  API_ACCESS_DISABLED, 400 INVALID_* / TOO_MANY_TOKENS, 404 MODEL_NOT_FOUND, 422
  CONTENT_POLICY_VIOLATION, 429 RATE_LIMIT_EXCEEDED / MODEL_OVERLOADED, 500 INFERENCE_FAILED,
  503 MODEL_OFFLINE / MODEL_AT_CAPACITY, 504 REQUEST_TIMEOUT.

Secrets: the key is read from the environment variable `VENICE_API_KEY` at call time, only
here and in `gateway.credentials`, and is never logged, stored, audited or put in an exception.
An error body from Venice is never echoed: only a documented error CODE from a fixed
whitelist is kept. No retry: one attempt, then an honest "unavailable" (no fake reply, no
fallback to another provider).
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

from ..core.resilience import PermanentError, TransientError
from .model_gateway import ModelResponse

NAME = "venice"
API_BASE = "https://api.venice.ai/api/v1"
CHAT_URL = f"{API_BASE}/chat/completions"
RATE_LIMITS_URL = f"{API_BASE}/api_keys/rate_limits"      # GET; balances + limits; no inference
KEY_ENV = "VENICE_API_KEY"                                 # Railway variable NAME; never a value
PROVIDER_ENV = "BRAMBLELOOP_PRIVATE_PROVIDER"              # "venice" selects this transport
PROVIDER_VALUE = "venice"

# The pinned default model. FINAL OWNER RULING 2026-10-20 (D-W4-PL-VENICE-ADULT, item A):
# `venice-uncensored-1-2` is approved as the preferred Private Laura model at the existing
# CA$0.50/day cap, SUBJECT TO verification that it is available in the API, Venice-hosted,
# Private class and covered by Venice's zero-retention commitment. Verification is the pinned
# verified row below (GET /api/v1/models, 2026-10-20) and, once the owner-enabled credential
# check has run, the live metadata it recorded (`gateway.credentials`): a live reading that
# contradicts the row, or a model with no verified row, FAILS CLOSED (`eligible`).
MODEL = "venice-uncensored-1-2"
#: The owner may select another ELIGIBLE model by name (e.g. revert to GLM 5.2); an ineligible
#: or unknown name is refused, never substituted.
MODEL_ENV = "BRAMBLELOOP_PRIVATE_MODEL"

# USD per million tokens (input, output), from GET https://api.venice.ai/api/v1/models
# (`model_spec.pricing.{input,output}.usd`) and docs.venice.ai/overview/pricing, read
# 2026-10-20. An assumption about a price this company does not control, labelled as one on
# every ledger row (`price_basis: assumed`). A model with no row is unpriced and refused.
PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "zai-org-glm-5-2": (1.40, 4.40),
    "venice-uncensored-1-2": (0.20, 0.90),
    "venice-uncensored-role-play": (0.50, 2.00),
}
PRICES_READ = "2026-10-20 (GET api.venice.ai/api/v1/models?type=text; docs.venice.ai/overview/pricing)"
#: Context window and max completion (tokens) Venice publishes, 2026-10-20.
CONTEXT_TOKENS: dict[str, int] = {"zai-org-glm-5-2": 1_000_000,
                                  "venice-uncensored-1-2": 128_000,
                                  "venice-uncensored-role-play": 128_000}
MAX_COMPLETION_TOKENS: dict[str, int] = {"zai-org-glm-5-2": 131_072,
                                         "venice-uncensored-1-2": 8_192,
                                         "venice-uncensored-role-play": 4_096}

# ELIGIBILITY RULE (owner ruling item B): Venice-hosted AND Private class AND a pinned price row.
# Verified rows: Venice's own GET /api/v1/models (`owned_by: venice.ai`, `model_spec.privacy`,
# `model_spec.offline`), read 2026-10-20 15:50Z. "private" = "Zero data retention,
# contract-enforced" (docs.venice.ai/overview/privacy). Anonymized models (the upstream
# provider sees the prompt) and any model that sends text to another inference provider are
# refused unless separately approved; a model with no verified row is UNKNOWN and refused.
VERIFIED_MODELS: dict[str, dict] = {
    "zai-org-glm-5-2": {"privacy": "private", "hosted_by": "venice.ai", "offline": False,
                        "verified": "2026-10-20"},
    "venice-uncensored-1-2": {"privacy": "private", "hosted_by": "venice.ai", "offline": False,
                              "verified": "2026-10-20"},
    "venice-uncensored-role-play": {"privacy": "private", "hosted_by": "venice.ai",
                                    "offline": False, "verified": "2026-10-20"},
}
#: Separately approved exceptions to the rule (none).
SEPARATELY_APPROVED: frozenset = frozenset()
#: Reasoning models: reasoning parameters are sent only to these.
REASONING_MODELS = frozenset({"zai-org-glm-5-2"})


def eligible(model: str, live: dict | None = None) -> tuple[bool, str]:
    """(eligible?, why). Fails closed on anything unverified.

    `live` is Venice's own metadata for this model as last recorded by the owner-enabled
    credential check ({"privacy", "offline", "present"}), or None when no live reading exists.
    """
    if model in SEPARATELY_APPROVED:
        return True, "separately approved"
    row = VERIFIED_MODELS.get(model)
    if row is None:
        return False, "UNKNOWN classification: no verified Venice row"
    if row.get("privacy") != "private" or row.get("hosted_by") != "venice.ai":
        return False, f"not Venice-hosted Private class ({row.get('privacy')})"
    if model not in PRICES_USD_PER_MTOK:
        return False, "no pinned price row"
    if live is not None:
        if not live.get("present", False):
            return False, "not listed by Venice's API now"
        if live.get("privacy") != "private":
            return False, f"Venice now classifies it {live.get('privacy')!r}"
        if live.get("offline"):
            return False, "Venice reports it offline"
    return True, "verified Venice-hosted Private class with a pinned price"


#: Back-compatible name: every model the rule admits on its pinned rows.
PRIVATE_MODELS = frozenset(m for m in VERIFIED_MODELS if eligible(m)[0])


def model(env=None) -> str:
    """The approved default, or the owner's eligible choice from MODEL_ENV; "" if ineligible."""
    env = os.environ if env is None else env
    v = str(env.get(MODEL_ENV) or "").strip() or MODEL
    return v if eligible(v)[0] else ""

TIMEOUT_SECONDS = 60.0
# Venice tokenisers are not the one `chars/4` was measured on; a pessimistic chars/3 keeps the
# pre-call reservation from under-reserving (the ceiling is checked against the estimate).
CHARS_PER_TOKEN_ESTIMATE = 3

# Documented Venice error codes kept from an error body (whitelist; nothing else survives).
ERROR_CODES = frozenset({
    "AUTHENTICATION_FAILED", "AUTHENTICATION_FAILED_INACTIVE_KEY", "PRO_ONLY_MODEL",
    "INSUFFICIENT_BALANCE", "API_KEY_DIEM_SPEND_LIMIT_EXCEEDED",
    "API_KEY_USD_SPEND_LIMIT_EXCEEDED", "UNAUTHORIZED", "API_ACCESS_DISABLED",
    "INVALID_REQUEST", "INVALID_MODEL", "TOO_MANY_TOKENS", "MODEL_NOT_FOUND",
    "PAYLOAD_TOO_LARGE", "INVALID_CONTENT_TYPE", "CONTENT_POLICY_VIOLATION",
    "RATE_LIMIT_EXCEEDED", "MODEL_OVERLOADED", "INFERENCE_FAILED", "UNKNOWN_ERROR",
    "MODEL_OFFLINE", "MODEL_AT_CAPACITY", "REQUEST_TIMEOUT"})

# Failure classes -> the fixed owner-facing reply code (`laura_register.REASONS`).
AUTH, CREDIT, POLICY, RATE, DOWN, BAD_REQUEST = (
    "PROVIDER_AUTH", "PROVIDER_CREDIT", "PROVIDER_POLICY", "PROVIDER_RATE_LIMITED",
    "PROVIDER_UNREACHABLE", "PROVIDER_ERROR")


def selected(env=None) -> str:
    """Which transport the owner selected for Private Laura: "venice", "anthropic" or "".

    Default (unset or anything else) is "" = no private provider selected: OFF. "anthropic" is
    the pre-ruling transport, kept only as an explicit owner choice (D-W4-PL-VENICE makes
    Venice the provider; a different one needs the owner)."""
    env = os.environ if env is None else env
    v = str(env.get(PROVIDER_ENV) or "").strip().lower()
    return v if v in (PROVIDER_VALUE, "anthropic") else ""


def key(env=None) -> str:
    env = os.environ if env is None else env
    return str(env.get(KEY_ENV) or "").strip()


def estimate_cad(model: str, *, input_tokens: int, output_tokens: int) -> float:
    """Padded CAD estimate from the Venice price table (same FX and padding as the gateway)."""
    from .anthropic import ESTIMATE_PADDING, USD_TO_CAD, BudgetExceeded

    prices = PRICES_USD_PER_MTOK.get(model)
    if prices is None:
        raise BudgetExceeded(f"{model!r} has no Venice price on file; an unpriced call is an "
                             f"unbounded one")
    usd = input_tokens / 1e6 * prices[0] + output_tokens / 1e6 * prices[1]
    return round(usd * USD_TO_CAD * ESTIMATE_PADDING, 6)


def estimate_for(system: str, user: str, max_output_tokens: int, model: str = MODEL) -> float:
    return estimate_cad(model, input_tokens=(len(system) + len(user)) // CHARS_PER_TOKEN_ESTIMATE
                        + 1, output_tokens=int(max_output_tokens))


class VeniceTransient(TransientError):
    """Rate limit, capacity, outage, unreachable. Carries a class and a code, never a body."""

    def __init__(self, status: int, code: str, klass: str):
        super().__init__(f"venice {status:03d} {code}".strip())
        self.status, self.code, self.klass = status, code, klass


class VenicePermanent(PermanentError):
    """Auth, credit, policy, bad request. Carries a class and a code, never a body."""

    def __init__(self, status: int, code: str, klass: str):
        super().__init__(f"venice {status:03d} {code}".strip())
        self.status, self.code, self.klass = status, code, klass


class VeniceTimeout(TimeoutError):
    """The request reached Venice and no answer came: whether it billed is UNKNOWN (the gateway
    counts it at the reservation estimate, never as zero)."""

    def __init__(self, status: int = 0, code: str = "TIMEOUT"):
        super().__init__(f"venice {status:03d} {code}")
        self.status, self.code, self.klass = status, code, DOWN


def _code_from(body: str) -> str:
    """A documented error code found in the body, else "". The body itself is discarded."""
    for token in re.findall(r"[A-Z][A-Z0-9_]{3,}", body or ""):
        if token in ERROR_CODES:
            return token
    return ""


def classify(status: int, body: str = "") -> Exception:
    """One HTTP failure as a classified, content-free exception."""
    code = _code_from(body)
    if status == 401:
        return VenicePermanent(status, code or "AUTHENTICATION_FAILED", AUTH)
    if status == 402:
        return VenicePermanent(status, code or "INSUFFICIENT_BALANCE", CREDIT)
    if status == 403:
        return VenicePermanent(status, code or "UNAUTHORIZED", AUTH)
    if status == 422 and code == "CONTENT_POLICY_VIOLATION":
        return VenicePermanent(status, code, POLICY)
    if status == 429:
        return VeniceTransient(status, code or "RATE_LIMIT_EXCEEDED", RATE)
    if status == 504:
        return VeniceTimeout(status, code or "REQUEST_TIMEOUT")
    if status >= 500:
        return VeniceTransient(status, code or "UNKNOWN_ERROR", DOWN)
    return VenicePermanent(status, code or "INVALID_REQUEST", BAD_REQUEST)


def reply_code(exc: BaseException) -> str:
    """The fixed reply code for a failure (`laura_register.REASONS`)."""
    return str(getattr(exc, "klass", "") or BAD_REQUEST)


@dataclass(frozen=True)
class VeniceResponse(ModelResponse):
    #: Venice's own reported cost for this call (`cost.usd`), when it reports one.
    cost_usd: float | None = None


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


@dataclass
class VeniceProvider:
    """The Venice chat-completions transport. Priced from `PRICES_USD_PER_MTOK` only."""

    name: str = NAME
    model: str = MODEL
    timeout_seconds: float = TIMEOUT_SECONDS
    cost_per_1k_input_cad: float = field(default=0.0)
    cost_per_1k_output_cad: float = field(default=0.0)

    def __post_init__(self) -> None:
        from .anthropic import USD_TO_CAD, BudgetExceeded

        ok, why = eligible(self.model)
        if not ok:
            raise BudgetExceeded(f"{self.model!r} is not eligible for Private Laura ({why}); "
                                 f"refused")
        in_usd, out_usd = PRICES_USD_PER_MTOK[self.model]
        self.cost_per_1k_input_cad = round(in_usd / 1000 * USD_TO_CAD, 8)
        self.cost_per_1k_output_cad = round(out_usd / 1000 * USD_TO_CAD, 8)

    @staticmethod
    def key() -> str:
        return key()

    def payload(self, system: str, user: str, *, max_tokens: int) -> bytes:
        """The exact request body: pinned model, our system prompt ONLY, one user message."""
        reasoning = self.model in REASONING_MODELS
        vp = {"include_venice_system_prompt": False, "enable_web_search": "off",
              "enable_web_scraping": False, "enable_web_citations": False}
        if reasoning:
            vp.update(disable_thinking=True, strip_thinking_response=True)
        return json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_completion_tokens": int(max_tokens),
            **({"reasoning_effort": "none"} if reasoning else {}),
            "stream": False,
            "venice_parameters": vp,
        }).encode()

    @staticmethod
    def headers(api_key: str) -> dict:
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                "Accept": "application/json"}

    def _post(self, url: str, body: bytes, headers: dict, timeout: float) -> tuple[int, str]:
        """(status, body text). The one network call; tests replace it. 0 = unreachable;
        -1 = timed out after the request was sent."""
        import socket
        import urllib.error
        import urllib.request

        req = urllib.request.Request(url, data=body, method="POST")
        for k, v in headers.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return int(resp.status), resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return int(exc.code), exc.read().decode("utf-8", "replace")[:2000]
        except (TimeoutError, socket.timeout):
            return -1, ""
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout)):
                return -1, ""
            return 0, ""
        except OSError:
            return 0, ""

    def _send(self, payload: bytes, api_key: str, *, timeout: float | None = None
              ) -> VeniceResponse:
        if not api_key:
            raise VenicePermanent(0, "NO_KEY", AUTH)
        started = time.time()
        status, text = self._post(CHAT_URL, payload, self.headers(api_key),
                                  timeout or self.timeout_seconds)
        if status == -1:
            raise VeniceTimeout(0, "TIMEOUT")
        if status == 0:
            raise VeniceTransient(0, "UNREACHABLE", DOWN)
        if not 200 <= status < 300:
            raise classify(status, text)
        return self._read(text, started)

    def _read(self, text: str, started: float) -> VeniceResponse:
        body = json.loads(text)
        choice = (body.get("choices") or [{}])[0]
        content = str(((choice.get("message") or {}).get("content")) or "")
        content = _THINK.sub("", content).strip()
        usage = body.get("usage") or {}
        cost = body.get("cost") or {}
        try:
            cost_usd = float(cost.get("usd")) if cost.get("usd") is not None else None
        except (TypeError, ValueError):
            cost_usd = None
        finish = str(choice.get("finish_reason") or "")
        return VeniceResponse(
            text=content, provider=self.name, model=str(body.get("model") or self.model),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=round((time.time() - started) * 1000, 2),
            stop_reason=("max_tokens" if finish == "length" else finish),
            cost_usd=cost_usd)
