"""S2: the OpenAI provider, inside the existing model gateway (no parallel system).

One adapter, two capabilities, the same contract the Anthropic provider keeps:

* `OpenAIProvider.complete(system, user, *, max_tokens)` and `.see(system, prompt, image_urls,
  *, max_tokens)` return the gateway's `ModelResponse`, so `ModelGateway`, `paid_calls`
  idempotency, the cost ledger and the breaker treat an OpenAI answer exactly as they treat an
  Anthropic one.
* The model is explicit and pinned: only a dated snapshot in `PRICES_USD_PER_MTOK` is accepted.
  An undated alias ("gpt-4.1") would let the provider change the model under a release, and an
  unpriced model is an unbounded one; both are refused at construction.
* Every request leaves through `_guarded` -> `paid_calls.guarded`, keyed by job + request bytes,
  so a retried attempt replays the answer it already paid for. Vision requests also pass
  `paid_provider_gate.enforce` as `openai-vision`, like `visual.d_judge`.
* Failures are classified with the gateway's own error classes: a refused request (HTTP status,
  unreachable) did not bill (DECLINED); a timeout or an unreadable 2xx may have (UNCERTAIN).
  Exhausted credit (`insufficient_quota`, `billing_hard_limit_reached`) is permanent until the
  owner adds credit: it is raised as `ProviderUnusable` and noted with `ops.funding.note`,
  which puts the provider on HOLD.
* No test reaches the network: `_post` is the one network call, and tests replace it.

Prices are the provider's published list prices for the pinned snapshots, entered by hand at
build time (`PRICE_SOURCE`). They are not read from an API, so they are a stated assumption
that the owner or reviewer confirms before the provider is activated.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from .anthropic import (USD_TO_CAD, BudgetExceeded, PermanentError, ProviderUnusable,
                        TransientError, _classify_failure, _decode_response, _encode_response)
from .model_gateway import ModelResponse

NAME = "openai"
CHAT_URL = "https://api.openai.com/v1/chat/completions"
KEY_VAR = "OPENAI_API_KEY"
# KEYS-19i4: the same OpenAI account's key is held on Railway as the image provider's
# per-account variable (`gateway.images.key_var("openai")`). One account, one secret: the chat
# and vision calls read it when OPENAI_API_KEY itself is absent, so the owner never has to copy
# a secret into a second variable (a copy is a secret that gets rotated in only one place).
FALLBACK_KEY_VARS = ("BRAMBLELOOP_IMAGE_KEY_OPENAI",)


def api_key(env=None) -> str:
    """This account's OpenAI key, or empty. Never logged; callers report presence only."""
    e = env if env is not None else os.environ
    for var in (KEY_VAR, *FALLBACK_KEY_VARS):
        v = (e.get(var) or "").strip()
        if v:
            return v
    return ""


def key_present(env=None) -> bool:
    return bool(api_key(env))
TIMEOUT_SECONDS = 60.0
VISION_TIMEOUT_SECONDS = 120.0
MAX_IMAGES_PER_CALL = 4
# Tokens one image is reserved at (the same worst-case basis the Anthropic vision path uses).
IMAGE_TOKENS_ESTIMATE = 1600
# S2 review 6957356475 (LOW): the -mini snapshots count image patches with a multiplier
# (OpenAI's image-token rule: up to 1,536 patches x 1.62 for gpt-4.1-mini), so one image can
# cost about 2,500 tokens there. ESTIMATED worst case per image, read from the published
# counting rule; reserved high on purpose.
IMAGE_TOKENS_BY_MODEL: dict[str, int] = {"gpt-4.1-mini-2025-04-14": 2500,
                                         "gpt-5-mini-2025-08-07": 2500}


def image_tokens(model: str) -> int:
    return IMAGE_TOKENS_BY_MODEL.get(model, IMAGE_TOKENS_ESTIMATE)

# Pinned, dated snapshots only, (input, output) US$ per million tokens.
PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4.1-2025-04-14": (2.00, 8.00),
    "gpt-4.1-mini-2025-04-14": (0.40, 1.60),
    "gpt-5-2025-08-07": (1.25, 10.00),
    "gpt-5-mini-2025-08-07": (0.25, 2.00),
}
PRICE_SOURCE = ("OpenAI published API list prices for these snapshots, entered at build time "
                "(2026-11-17); not read from an API -- confirm before activation")
# Snapshots that accept image input in chat completions.
VISION_MODELS = frozenset({"gpt-4.1-2025-04-14", "gpt-4.1-mini-2025-04-14",
                           "gpt-5-2025-08-07", "gpt-5-mini-2025-08-07"})
# Reasoning snapshots take `max_completion_tokens` and no temperature.
REASONING_MODELS = frozenset({"gpt-5-2025-08-07", "gpt-5-mini-2025-08-07"})
DEFAULT_MODEL = "gpt-4.1-mini-2025-04-14"

# S2 per-provider rate limit: requests per rolling minute this process and its ledger allow.
# A ceiling that only restricts; the provider's own limits are higher. Counted from the
# ledger (`CostEntry` rows for this provider) when a database is known, and from this
# process's own sends always, so neither a restart nor a second process lifts it.
RATE_LIMIT_PER_MINUTE = 60
_RECENT_SENDS: list[float] = []
_RATE_LOCK = __import__("threading").Lock()     # review 6957356475 (LOW): one window, locked


class RateLimited(TransientError):
    """Over this provider's per-minute limit: refused before sending (did not bill)."""


def _rate_check(db, *, now: float | None = None, limit: int | None = None) -> None:
    import time as _t
    from datetime import datetime, timedelta, timezone

    now = _t.time() if now is None else now
    limit = RATE_LIMIT_PER_MINUTE if limit is None else limit
    with _RATE_LOCK:
        # Trim, count and (below) append under one lock: two threads cannot both take the
        # last slot of the minute.
        _RECENT_SENDS[:] = [t for t in _RECENT_SENDS if t > now - 60]
        counted = len(_RECENT_SENDS)
        if counted >= limit:
            raise RateLimited(f"{NAME}: {counted} requests in the last minute, at the limit "
                              f"of {limit}; refused before sending")
        _RECENT_SENDS.append(now)
    if db is not None:
        from sqlalchemy import func, select

        from ..core.models import CostEntry

        since = datetime.fromtimestamp(now, timezone.utc) - timedelta(seconds=60)
        with db.session() as s:
            counted = max(counted, int(s.scalar(select(func.count(CostEntry.id)).where(
                CostEntry.provider == NAME, CostEntry.at >= since)) or 0))
    if counted >= limit:
        with _RATE_LOCK:
            if now in _RECENT_SENDS:
                _RECENT_SENDS.remove(now)       # this request was not sent
        raise RateLimited(f"{NAME}: {counted} requests in the last minute, at the limit of "
                          f"{limit}; refused before sending")


# The provider's own words for an account that cannot pay (ops.funding.MARKERS reads them too).
CREDIT_EXHAUSTED = ("insufficient_quota", "billing_hard_limit_reached")


class OpenAITimeout(TransientError, TimeoutError):
    """Timed out after the request was sent: whether it billed is unknown (UNCERTAIN)."""


def estimate_cad(model: str, *, input_tokens: int, output_tokens: int) -> float:
    """The reservation for one call: list price, padded 1.25x like `anthropic.estimate_cad`.
    An unpriced model is refused, never estimated at zero."""
    prices = PRICES_USD_PER_MTOK.get(model)
    if prices is None:
        raise BudgetExceeded(f"{model!r} has no price on file; an unpriced call is an "
                             f"unbounded one")
    in_usd, out_usd = prices
    usd = (max(0, int(input_tokens)) * in_usd + max(0, int(output_tokens)) * out_usd) / 1e6
    return round(usd * USD_TO_CAD * 1.25, 6)


def classify_http(status: int, text: str) -> PermanentError | TransientError:
    """The error one non-2xx answer is. Exhausted credit is permanent and named."""
    lowered = (text or "").lower()
    if any(m in lowered for m in CREDIT_EXHAUSTED):
        exc: PermanentError | TransientError = ProviderUnusable(
            f"openai {status}: the account has no usable credit ({text[:200]})")
        exc.credit_exhausted = True  # type: ignore[attr-defined]
        return exc
    if status in (408, 409, 429) or status >= 500:
        return TransientError(f"openai {status}: {text[:300]}")
    return ProviderUnusable(f"openai {status}: {text[:300]}")


def _note_funding(exc: BaseException, db=None) -> None:
    """Exhausted credit becomes an owner action (HOLD), never a silent retry loop."""
    if not getattr(exc, "credit_exhausted", False):
        return
    try:
        from . import paid_calls
        from ..ops import funding

        db = db if db is not None else paid_calls.current_db()
        if db is not None:
            funding.note_provider(db, NAME, f"insufficient_quota: {exc}")
    except Exception:  # noqa: BLE001 - recording the hold must never mask the refusal
        pass


def image_url(reference: str) -> str:
    """The `image_url.url` OpenAI reads: an http(s) URL as is, a local file as a data URL.

    The company's own renders are files (`visual.inspect` writes a downscaled copy and passes
    its path); a path sent as a URL is a request about no picture. The same reader as the
    Anthropic path (`anthropic._image_block`): the file must exist and its bytes must sniff as
    png/jpeg/gif/webp, or the call is refused before anything is sent."""
    if reference.startswith(("http://", "https://", "data:")):
        return reference
    from .anthropic import _image_block

    block = _image_block(reference)["source"]
    return f"data:{block['media_type']};base64,{block['data']}"


@dataclass
class OpenAIProvider:
    """The OpenAI chat-completions transport, priced from `PRICES_USD_PER_MTOK` only."""

    name: str = NAME
    model: str = DEFAULT_MODEL
    timeout_seconds: float = TIMEOUT_SECONDS
    cost_per_1k_input_cad: float = field(default=0.0)
    cost_per_1k_output_cad: float = field(default=0.0)

    def __post_init__(self) -> None:
        prices = PRICES_USD_PER_MTOK.get(self.model)
        if prices is None:
            raise BudgetExceeded(
                f"{self.model!r} is not a pinned, priced OpenAI snapshot "
                f"({', '.join(sorted(PRICES_USD_PER_MTOK))}); refused")
        in_usd, out_usd = prices
        self.cost_per_1k_input_cad = round(in_usd / 1000 * USD_TO_CAD, 8)
        self.cost_per_1k_output_cad = round(out_usd / 1000 * USD_TO_CAD, 8)

    @staticmethod
    def key() -> str:
        return api_key()

    # ---- requests --------------------------------------------------------------------------

    def _body(self, messages: list[dict], max_tokens: int) -> bytes:
        limit = ({"max_completion_tokens": int(max_tokens)} if self.model in REASONING_MODELS
                 else {"max_tokens": int(max_tokens)})
        return json.dumps({"model": self.model, "messages": messages, **limit,
                           "stream": False}).encode()

    def complete(self, system: str, user: str, *, max_tokens: int) -> ModelResponse:
        key = self.key()
        if not key:
            raise ProviderUnusable(f"no {KEY_VAR} in this environment")
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": user}]
        from . import providers

        own = estimate_cad(self.model,
                           input_tokens=providers.input_tokens(self.model, system=system,
                                                               user=user),
                           output_tokens=max_tokens)
        from . import paid_provider_gate as gate

        # S2 review 6957356475: text is owner-activated like vision (`openai-text`), with the
        # activation's own day/month/attempt ceilings, before any request leaves.
        return self._guarded(self._body(messages, max_tokens), key, "openai.chat",
                             gate=self._paid_gate(own, gate.OPENAI_TEXT, gate.TEXT,
                                                  "openai.chat"))

    def see(self, system: str, prompt: str, image_urls: list[str], *,
            max_tokens: int) -> ModelResponse:
        key = self.key()
        if not key:
            raise ProviderUnusable(f"no {KEY_VAR} in this environment")
        if self.model not in VISION_MODELS:
            raise ProviderUnusable(f"{self.model!r} does not take image input")
        if not image_urls:
            raise ProviderUnusable("a vision call with no image is a text call that thinks it "
                                   "looked at something; refused")
        if len(image_urls) > MAX_IMAGES_PER_CALL:
            raise ProviderUnusable(f"{len(image_urls)} images in one call, against a limit of "
                                   f"{MAX_IMAGES_PER_CALL}")
        content = [{"type": "text", "text": prompt}] + [
            {"type": "image_url", "image_url": {"url": image_url(u)}} for u in image_urls]
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": content}]
        payload = self._body(messages, max_tokens)
        from . import providers

        own = estimate_cad(self.model,
                           input_tokens=providers.input_tokens(self.model, system=system,
                                                               user=prompt,
                                                               images=len(image_urls)),
                           output_tokens=max_tokens)
        return self._guarded(payload, key, "openai.vision", timeout=VISION_TIMEOUT_SECONDS,
                             gate=self._vision_gate(own))

    def _vision_gate(self, own_estimate: float):
        from . import paid_provider_gate as gate

        return self._paid_gate(own_estimate, gate.OPENAI_VISION, gate.VISION, "openai.vision")

    # ---- the paid boundary -----------------------------------------------------------------

    def _paid_gate(self, own_estimate: float, provider: str, scope: str, purpose: str):
        """`paid_provider_gate.enforce` as `provider`/`scope`, on this request's own worst case
        or the reservation noted for it, whichever is larger (as `visual.d_judge` does)."""
        from . import paid_calls, paid_provider_gate as gate

        def wrap(send, fp):
            def gated():
                noted_db, held = gate.take_budget()
                db = noted_db if noted_db is not None else paid_calls.current_db()
                held = held or {}
                try:
                    noted = float(held.get("estimate_cad") or 0.0)
                except (TypeError, ValueError):
                    noted = 0.0
                return gate.enforce(
                    db, provider=provider, scope=scope,
                    estimate_cad=max(own_estimate, noted), fingerprint=fp,
                    reservation_id=held.get("reservation_id"), call=send,
                    classify=lambda exc: _classify_failure(exc),
                    purpose=purpose)
            return gated
        return wrap

    def _guarded(self, payload: bytes, key: str, effect: str, *,
                 timeout: float | None = None, gate=None) -> ModelResponse:
        from . import paid_calls, routing

        from ..ops import funding

        # S2 review 6957356475 (LOW): the HOLD is read wherever this call's ledger is -- the
        # job scope's database, or the one its reservation was noted in -- not only in a job.
        from . import paid_provider_gate

        db = paid_calls.current_db() or paid_provider_gate.peek_budget_db()
        hold = funding.blocked_provider(db, NAME)
        if hold.get("blocked"):
            # HOLD: the account has no usable credit; nothing is sent until the owner adds it.
            raise ProviderUnusable(f"{NAME} is on HOLD: {hold.get('action', '')}")
        fp = paid_calls.fingerprint(effect, payload.decode("utf-8", "replace"))

        def send():
            # Checked at send time, inside the idempotency guard: a replayed answer sends
            # nothing and spends none of the minute.
            _rate_check(db)
            return self._send(payload, key, timeout=timeout)
        try:
            response = paid_calls.guarded(
                effect, fp, gate(send, fp) if gate is not None else send,
                encode=_encode_response, decode=_decode_response, classify=_classify_failure,
                cost_kind=routing.COST_KIND, provider=self.name, model=self.model)
        except BaseException as exc:
            _note_funding(exc, db)
            raise
        if db is not None and not response.replayed:
            # A live call succeeded: a HOLD another worker opened meanwhile is closed.
            funding.cleared_provider(db, NAME)
        return response

    def _post(self, body: bytes, headers: dict, timeout: float) -> tuple[int, str]:
        """(status, body text). The one network call; tests replace it. 0 = unreachable;
        -1 = timed out after the request was sent."""
        import socket
        import urllib.error
        import urllib.request

        from .venice import no_redirect_opener

        req = urllib.request.Request(CHAT_URL, data=body, method="POST")
        for k, v in headers.items():
            req.add_header(k, v)
        try:
            # The bearer key is never re-sent to a redirect target.
            with no_redirect_opener().open(req, timeout=timeout) as resp:
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

    def _send(self, payload: bytes, key: str, *, timeout: float | None = None
              ) -> ModelResponse:
        started = time.time()
        status, text = self._post(payload, {"Authorization": f"Bearer {key}",
                                            "Content-Type": "application/json",
                                            "Accept": "application/json"},
                                  timeout or self.timeout_seconds)
        if status == -1:
            raise OpenAITimeout("openai: timed out after the request was sent")
        if status == 0:
            raise TransientError("openai unreachable")
        if not 200 <= status < 300:
            raise classify_http(status, text)
        return self._read(text, started)

    def _read(self, text: str, started: float) -> ModelResponse:
        body = json.loads(text)
        usage = body.get("usage")
        if (not isinstance(usage, dict)
                or type(usage.get("prompt_tokens")) is not int
                or type(usage.get("completion_tokens")) is not int
                or usage["prompt_tokens"] < 0 or usage["completion_tokens"] < 0
                or usage["prompt_tokens"] + usage["completion_tokens"] <= 0):
            # The answer arrived after transmission, but its cost is unknown: never coerced
            # into understated usage (the gateway counts it at the estimate, UNCERTAIN).
            raise ValueError("openai response has invalid or missing usage")
        reported = str(body.get("model") or "")
        if reported != self.model:
            # S2 review 6957356475 (LOW): the answer must come from the pinned snapshot that
            # was priced and requested. It was billed, so it counts at its estimate (a
            # ValueError is UNCERTAIN to the gateway), and it is not used.
            raise ValueError(f"openai answered as {reported!r}, not the pinned {self.model!r}")
        choice = (body.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content")
        finish = str(choice.get("finish_reason") or "")
        return ModelResponse(
            text=str(content or ""), provider=self.name, model=reported,
            response_id=str(body.get("id") or "")[:120],
            input_tokens=usage["prompt_tokens"], output_tokens=usage["completion_tokens"],
            latency_ms=round((time.time() - started) * 1000, 2),
            stop_reason=("max_tokens" if finish == "length" else finish))


def balance(db=None) -> dict:
    """The account balance: UNKNOWN. OpenAI publishes no supported endpoint that reports an
    API account's remaining credit to an API key, so none is read or guessed. What is known is
    the ledger (`finance.credits.split`) and, with the owner's admin key, the provider's own
    cost report (`ops.provider_accounts.fetch_provider_costs`, OWNER_GATED without it)."""
    out = {"provider": NAME, "balance": "UNKNOWN",
           "why": "no supported balance API for an API key; never estimated as a number"}
    if db is not None:
        from ..finance import credits

        out["ledger"] = {k: v for k, v in credits.split(db, NAME).items() if k != "calls"}
    return out


def provider_for(task_key: str, *, model: str | None = None, **_kw) -> OpenAIProvider:
    """The vendor factory `gateway.providers` registers: the task's pinned OpenAI snapshot."""
    from . import routing

    return OpenAIProvider(model=model or routing.openai_model_for(task_key))
