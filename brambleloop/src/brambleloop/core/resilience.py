"""Resilience primitives: retry classification, circuit breaker, artifact integrity.

An autonomous company fails in boring, predictable ways: a provider returns 429, a socket
hangs, a model emits prose where JSON was expected, a file writes half. The difference between
a system that survives those and one that does not is whether it distinguishes *transient*
from *permanent* and refuses to keep hammering something that is down.
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, TypeVar

T = TypeVar("T")


# ---- failure classification ----------------------------------------------


class TransientError(Exception):
    """Worth retrying: rate limits, 5xx, timeouts, connection resets."""


class PermanentError(Exception):
    """Never worth retrying: 400/401/403/404, schema violations, policy refusals."""


def classify_http(status: int) -> type[Exception]:
    if status == 429 or status >= 500:
        return TransientError
    if status >= 400:
        return PermanentError
    raise ValueError(f"{status} is not an error status")


def retry_after_seconds(headers: dict[str, str] | None, attempt: int,
                        base: float = 2.0, cap: float = 300.0) -> float:
    """Honour a server's Retry-After when it gives one; otherwise back off with jitter.

    Ignoring Retry-After is how a client turns a rate limit into a ban.
    """
    if headers:
        for key in ("retry-after", "Retry-After"):
            if key in headers:
                try:
                    return min(cap, float(headers[key]))
                except (TypeError, ValueError):
                    pass
    delay = min(cap, base ** max(1, attempt))
    return delay * (0.8 + 0.4 * random.random())


# ---- circuit breaker ------------------------------------------------------


@dataclass
class CircuitBreaker:
    """Stops calling a dependency that is clearly down.

    Without this, a provider outage becomes thousands of doomed calls, each costing money and
    each delaying the queue. After `threshold` consecutive failures the circuit opens and
    calls fail instantly until `reset_after` has elapsed.
    """

    name: str
    threshold: int = 5
    reset_after_seconds: float = 60.0
    failures: int = 0
    opened_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if datetime.now(timezone.utc) - self.opened_at >= timedelta(
            seconds=self.reset_after_seconds
        ):
            return False  # half-open: allow one probe
        return True

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = datetime.now(timezone.utc)

    def call(self, fn: Callable[[], T]) -> T:
        if self.is_open:
            raise TransientError(
                f"circuit {self.name!r} is open after {self.failures} consecutive failures"
            )
        try:
            out = fn()
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return out


# ---- artifact integrity ---------------------------------------------------


def artifact_hash(payload: Any) -> str:
    if isinstance(payload, (bytes, bytearray)):
        return hashlib.sha256(bytes(payload)).hexdigest()
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


class CorruptArtifact(PermanentError):
    """A stored artifact no longer matches the hash recorded when it was written."""


def verify_artifact(payload: Any, expected_hash: str, label: str = "artifact") -> None:
    actual = artifact_hash(payload)
    if actual != expected_hash:
        raise CorruptArtifact(
            f"{label} failed integrity check: expected {expected_hash[:12]}, "
            f"got {actual[:12]}"
        )


# ---- model output validation ---------------------------------------------


class MalformedModelOutput(PermanentError):
    """A model returned something the caller cannot safely use."""


def parse_model_json(text: str, *, required: tuple[str, ...] = ()) -> dict:
    """Parse model output strictly.

    A model that returns prose, truncated JSON or a missing field must fail loudly here
    rather than quietly producing a half-populated object that travels downstream into a
    pattern or a listing.
    """
    if not isinstance(text, str) or not text.strip():
        raise MalformedModelOutput("model returned empty output")

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1] if "```" in cleaned[3:] else cleaned[3:]
        if cleaned.lstrip().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise MalformedModelOutput(f"model output is not valid JSON: {e}") from None
    if not isinstance(data, dict):
        raise MalformedModelOutput(f"expected a JSON object, got {type(data).__name__}")
    missing = [k for k in required if k not in data]
    if missing:
        raise MalformedModelOutput(f"model output missing required fields: {missing}")
    return data


# ---- generic retry --------------------------------------------------------


def with_retries(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    breaker: CircuitBreaker | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Retry transient failures only. Permanent ones surface immediately."""
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return breaker.call(fn) if breaker else fn()
        except PermanentError:
            raise
        except TransientError as e:
            last = e
            if attempt < attempts:
                sleep(retry_after_seconds(None, attempt))
        except Exception as e:  # unknown -> treat as transient once, then give up
            last = e
            if attempt < attempts:
                sleep(retry_after_seconds(None, attempt))
    assert last is not None
    raise last
