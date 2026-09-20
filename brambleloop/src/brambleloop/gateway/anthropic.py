"""The real model provider, the ceiling that stands in front of it, and an honest gate.

The owner supplied an Anthropic key on 2026-09-19. Three things had to be true before the
system was allowed to treat that as "the model provider exists", and only the first is
obvious.

**A key is not a capability.** The first call this key made returned, verbatim, "Your credit
balance is too low to access the Anthropic API." The key authenticates; the account cannot
serve a request. A gate that checks whether an environment variable is set would have
reported the model provider available and un-parked four requirements onto work that cannot
run -- the queue advertising work nobody can start, which is the failure the build executor
exists to prevent. So the gate reads a recorded *successful call*, not a variable, and
`probe()` is what records one. When credits arrive the next probe succeeds and the gate opens
with nobody having to remember.

**The ceiling is enforced before the call, not discovered on the invoice.** The owner's
standing ceiling is CA$25 a month. It is checked from CostEntry rows -- the same
rows-not-arguments rule used everywhere else -- and the estimate is deliberately pessimistic,
because a ceiling that relies on an optimistic cost estimate is a ceiling that is crossed
before anybody notices.

**Prices are an assumption and are labelled one.** The per-token figures below are the
provider's published list prices read at build time, converted at an assumed exchange rate.
They are not a measurement of this account's billing, so every ledger row carries
`price_basis: assumed` and the ceiling is compared against the padded estimate.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..core.resilience import PermanentError, TransientError
from .model_gateway import ModelResponse

# Published list prices, USD per million tokens, read 2026-09-19. An assumption, labelled as
# one on every row it produces.
# The one price table. `routing.Tier` used to restate these and the two disagreed by a factor
# of three on the deep tier, so every estimate in the system was a third of what the call
# actually billed -- the expedition estimated CA$0.15 and cost CA$1.02. A price restated in a
# second place is a price that will drift, and the one that bills is the one that is true.
PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (15.0, 75.0),
    "claude-sonnet-5": (3.0, 15.0),
    # Both the alias the router uses and the dated identifier. The router asked for
    # "claude-haiku-4-5", this table only held the dated form, and `.get(model, (0.0, 0.0))`
    # priced every cheap-tier call at nothing: 80 concepts generated, CA$0.00 recorded,
    # and a CA$25 monthly ceiling that cheap work could never reach.
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}
DEFAULT_MODEL = "claude-sonnet-5"

# Assumed, not fetched. A rate this company does not control and does not measure.
USD_TO_CAD = 1.37

# Applied to every estimate before it is checked against the ceiling. A ceiling that trusts an
# optimistic estimate is crossed before anybody notices.
ESTIMATE_PADDING = 1.25

# The owner's standing ceiling. Overridable by environment so it can be lowered without a
# deploy, never raised silently past this default.
DEFAULT_MONTHLY_CEILING_CAD = 25.0

# What one gallery image costs to look at, in input tokens. The provider's own rule of thumb
# is roughly (width x height) / 750, so Etsy's 570-wide gallery variant -- about 570x760 --
# is near 580. Rounded up, because this number is used to refuse a call before it is made and
# an optimistic estimate makes a ceiling into a suggestion. Measured usage is what gets
# billed and what reaches the ledger; this only has to be no smaller than the truth.
IMAGE_TOKENS_ESTIMATE = 800

# One refusal should not lose a batch of observations. Also the practical limit on how much
# of one listing's gallery is worth judging in a single question.
MAX_IMAGES_PER_CALL = 8

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class BudgetExceeded(PermanentError):
    """The monthly model ceiling would be crossed by this call."""


class ProviderUnusable(PermanentError):
    """The key authenticates and the account cannot serve a request."""


def monthly_ceiling_cad() -> float:
    """The ceiling in force. Environment may lower it; nothing may raise it."""
    raw = (os.environ.get("BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD") or "").strip()
    try:
        value = float(raw) if raw else DEFAULT_MONTHLY_CEILING_CAD
    except ValueError:
        return DEFAULT_MONTHLY_CEILING_CAD
    return min(value, DEFAULT_MONTHLY_CEILING_CAD)


def spent_this_month_cad(db, *, now: datetime | None = None) -> float:
    """Model spend for the calendar month, counted from ledger rows."""
    from sqlalchemy import select

    from ..core.models import CostEntry
    from . import routing

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        rows = list(s.scalars(select(CostEntry).where(
            CostEntry.kind == routing.COST_KIND)))
    total = 0.0
    for row in rows:
        at = row.at if row.at.tzinfo else row.at.replace(tzinfo=timezone.utc)
        if (at.year, at.month) == (now.year, now.month):
            total += row.amount_cad or 0.0
    return round(total, 6)


def estimate_cad(model: str, *, input_tokens: int, output_tokens: int) -> float:
    """What a call of this shape is expected to cost, padded on purpose."""
    prices = PRICES_USD_PER_MTOK.get(model)
    if prices is None:
        raise BudgetExceeded(
            f"{model!r} has no price on file, so its cost cannot be checked against the "
            f"ceiling. An unpriced call is an unbounded one")
    in_usd, out_usd = prices
    usd = (input_tokens / 1_000_000) * in_usd + (output_tokens / 1_000_000) * out_usd
    return round(usd * USD_TO_CAD * ESTIMATE_PADDING, 6)


def check_budget(db, *, model: str, input_tokens: int, max_tokens: int,
                 now: datetime | None = None) -> dict:
    """Refuse a call that would cross the ceiling, before it is made.

    Assumes the model writes its entire output allowance. It usually does not, and budgeting
    for the usual case is how a ceiling becomes a target.
    """
    spent = spent_this_month_cad(db, now=now)
    ceiling = monthly_ceiling_cad()
    estimate = estimate_cad(model, input_tokens=input_tokens, output_tokens=max_tokens)
    if spent + estimate > ceiling:
        raise BudgetExceeded(
            f"this call is estimated at CA${estimate:.4f} against CA${spent:.4f} already "
            f"spent this month and a ceiling of CA${ceiling:.2f}. Refused before the call "
            f"rather than found on the invoice")
    return {"spent_cad": spent, "ceiling_cad": ceiling, "estimate_cad": estimate,
            "headroom_cad": round(ceiling - spent - estimate, 6)}


@dataclass
class AnthropicProvider:
    """A real provider, used only where a key exists and the ceiling has been checked."""

    name: str = "anthropic"
    model: str = DEFAULT_MODEL
    timeout_seconds: float = 60.0
    cost_per_1k_input_cad: float = field(default=0.0)
    cost_per_1k_output_cad: float = field(default=0.0)

    def __post_init__(self) -> None:
        # Refused rather than defaulted to zero. `_cost_for` below already says it -- "an
        # unpriced call is an unbounded one" -- and this path silently disagreed with it,
        # which is how a model the price table did not know billed CA$0.00 against a ceiling
        # that counts dollars. Two code paths for one rule, and the silent one was the one
        # the gateway actually used.
        prices = PRICES_USD_PER_MTOK.get(self.model)
        if prices is None:
            raise BudgetExceeded(
                f"{self.model!r} has no price on file, so what it spends cannot be counted "
                f"against the ceiling. An unpriced call is an unbounded one")
        in_usd, out_usd = prices
        self.cost_per_1k_input_cad = round(in_usd / 1000 * USD_TO_CAD, 8)
        self.cost_per_1k_output_cad = round(out_usd / 1000 * USD_TO_CAD, 8)

    @staticmethod
    def key() -> str:
        return (os.environ.get("ANTHROPIC_API_KEY") or "").strip()

    def complete(self, system: str, user: str, *, max_tokens: int) -> ModelResponse:
        import urllib.error
        import urllib.request

        key = self.key()
        if not key:
            raise ProviderUnusable("no ANTHROPIC_API_KEY in this environment")

        payload = json.dumps({
            "model": self.model, "max_tokens": max_tokens,
            **({"system": system} if system else {}),
            "messages": [{"role": "user", "content": user}],
        }).encode()
        request = urllib.request.Request(API_URL, data=payload, method="POST")
        request.add_header("x-api-key", key)
        request.add_header("anthropic-version", API_VERSION)
        request.add_header("content-type", "application/json")

        started = time.time()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:  # noqa: PERF203 - each status means something
            detail = exc.read().decode(errors="replace")[:400]
            if exc.code in (429, 500, 502, 503, 529):
                raise TransientError(f"anthropic {exc.code}: {detail}") from exc
            # 400 with a billing message is the state this account is actually in, and it is
            # permanent until somebody buys credits. Retrying it is spend on nothing.
            raise ProviderUnusable(f"anthropic {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TransientError(f"anthropic unreachable: {exc.reason}") from exc

        return self._read(body, started)

    def see(self, system: str, prompt: str, image_urls: list[str], *,
            max_tokens: int) -> ModelResponse:
        """The same call with pictures in it. A model with eyes, not a browser.

        This is the half of the old `browser_vision` gate that never needed a browser. The
        sanctioned Etsy endpoint `listing_images` already returns every gallery image's URL,
        so the thing standing between this company and image-level competitive evidence was
        never infrastructure -- it was that nobody had written the call. Conflating the two
        under one capability name kept twelve requirements parked behind a cloud browser
        nobody had bought, when what they needed was already paid for.

        The API takes the image by URL, so nothing is downloaded, re-hosted or stored here:
        the observation is stored and the picture is not, which is also what keeps this on
        the right side of "never copy a competitor's expression".
        """
        import urllib.error
        import urllib.request

        key = self.key()
        if not key:
            raise ProviderUnusable("no ANTHROPIC_API_KEY in this environment")
        if not image_urls:
            raise ProviderUnusable(
                "a vision call with no image is a text call that thinks it looked at "
                "something, which is exactly the observation this system refuses to record")
        if len(image_urls) > MAX_IMAGES_PER_CALL:
            raise ProviderUnusable(
                f"{len(image_urls)} images in one call, against a limit of "
                f"{MAX_IMAGES_PER_CALL}. Batching past this makes one refusal lose every "
                f"observation in the batch")

        content: list[dict] = [
            {"type": "image", "source": {"type": "url", "url": url}} for url in image_urls]
        content.append({"type": "text", "text": prompt})

        payload = json.dumps({
            "model": self.model, "max_tokens": max_tokens,
            **({"system": system} if system else {}),
            "messages": [{"role": "user", "content": content}],
        }).encode()
        request = urllib.request.Request(API_URL, data=payload, method="POST")
        request.add_header("x-api-key", key)
        request.add_header("anthropic-version", API_VERSION)
        request.add_header("content-type", "application/json")

        started = time.time()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:400]
            if exc.code in (429, 500, 502, 503, 529):
                raise TransientError(f"anthropic {exc.code}: {detail}") from exc
            raise ProviderUnusable(f"anthropic {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TransientError(f"anthropic unreachable: {exc.reason}") from exc

        return self._read(body, started)

    def _read(self, body: dict, started: float) -> ModelResponse:
        text = "".join(block.get("text", "") for block in body.get("content", [])
                       if block.get("type") == "text")
        usage = body.get("usage", {})
        return ModelResponse(
            text=text, provider=self.name, model=body.get("model", self.model),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            latency_ms=round((time.time() - started) * 1000, 2))


# ---------------------------------------------------------------------------
# The probe: what makes the gate honest


PROBE_PROMPT = "Reply with the single word: ok"
PROBE_MAX_TOKENS = 8
PROBE_MODEL = "claude-haiku-4-5-20251001"


def probe(db, *, provider: AnthropicProvider | None = None,
          now: datetime | None = None, job_id: int | None = None) -> dict:
    """Make the smallest possible real call and record whether it worked.

    This is the difference between "a key is configured" and "a model provider exists". The
    result is a row, so the gate reads evidence rather than an environment variable, and the
    reason for a failure is recorded in the words the provider used rather than in a
    paraphrase somebody will later argue with.
    """
    from ..core.models import AuditLog, CostEntry
    from . import routing

    provider = provider or AnthropicProvider(model=PROBE_MODEL)
    record: dict = {"at": (now or datetime.now(timezone.utc)).isoformat(),
                    "model": provider.model, "ok": False, "reason": ""}

    if not provider.key():
        record["reason"] = "no ANTHROPIC_API_KEY in this environment"
    else:
        try:
            budget = check_budget(db, model=provider.model,
                                  input_tokens=len(PROBE_PROMPT) // 4,
                                  max_tokens=PROBE_MAX_TOKENS, now=now)
            response = provider.complete("", PROBE_PROMPT, max_tokens=PROBE_MAX_TOKENS)
        except BudgetExceeded as exc:
            record["reason"] = f"budget: {exc}"
        except (ProviderUnusable, TransientError) as exc:
            # The provider's own words. A key that authenticates and an account that cannot
            # serve a request are different failures, and only the message distinguishes them.
            record["reason"] = str(exc)[:400]
        else:
            cost = round(
                response.input_tokens * provider.cost_per_1k_input_cad / 1000
                + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
            record.update({"ok": True, "reason": "",
                           "input_tokens": response.input_tokens,
                           "output_tokens": response.output_tokens,
                           "cost_cad": cost, "headroom_cad": budget["headroom_cad"]})
            with db.session() as s:
                # The job that ran the probe, so this cost attributes like every other
                # one. It was the last model spend reaching the ledger with a null job
                # (#31), and an unattributed row is indistinguishable from a cost nobody
                # caused.
                s.add(CostEntry(agent="gateway", kind=routing.COST_KIND, amount_cad=cost,
                                job_id=job_id,
                                tokens_in=response.input_tokens,
                                tokens_out=response.output_tokens,
                                detail={"purpose": "model.probe", "model": response.model,
                                        "price_basis": "assumed",
                                        "latency_ms": record.get("latency_ms")}))

    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action="model.probe", artifact=provider.model,
                       detail=record))
    return record


# The probe image and what it asks. A picture whose answer is checkable without a model:
# a 1x1 PNG is not usable as a URL source, so the probe uses the benchmark's own gallery
# when one is known and refuses to claim vision otherwise. Set by `vision_probe`.
VISION_PROBE_PROMPT = (
    "Answer with one lowercase word and nothing else. Is this image a photograph or a "
    "diagram? If you cannot see any image at all, answer: none")
VISION_PROBE_MAX_TOKENS = 8
VISION_PROBE_MODEL = "claude-haiku-4-5-20251001"
VISION_PROBE_ACTION = "vision.probe"


def vision_probe(db, *, image_url: str = "", provider: AnthropicProvider | None = None,
                 now: datetime | None = None, job_id: int | None = None) -> dict:
    """Look at one real picture and record whether that worked.

    Separate from `probe()` on purpose. A text call succeeding says the account can serve a
    request; it says nothing about whether this code can put an image in front of the model
    and get an answer back, and those failed differently in practice -- a URL the provider
    cannot fetch, an image format it refuses, a payload shape that is subtly wrong. A gate
    that opened on the text probe would have advertised twelve requirements as startable on
    the strength of a call that never carried a picture.

    The answer is checked rather than merely received. "none" is the reply this prompt asks
    for when no image arrived, and a reply of "none" is recorded as a failure with that as
    the reason -- because a 200 response containing a model's apology is the shape a broken
    vision path actually takes, and counting it as success is how an empty capability
    reports itself available.
    """
    from ..core.models import AuditLog, CostEntry
    from . import routing

    provider = provider or AnthropicProvider(model=VISION_PROBE_MODEL)
    image_url = image_url or _a_known_image(db)
    record: dict = {"at": (now or datetime.now(timezone.utc)).isoformat(),
                    "model": provider.model, "ok": False, "reason": "",
                    "image_url": image_url}

    if not provider.key():
        record["reason"] = "no ANTHROPIC_API_KEY in this environment"
    elif not image_url:
        record["reason"] = (
            "no image to look at. Nothing has been observed that carries a gallery URL, so "
            "there is no picture in this system to prove the capability against -- and a "
            "vision probe with no image is the thing it exists to refuse")
    else:
        try:
            budget = check_budget(
                db, model=provider.model,
                input_tokens=len(VISION_PROBE_PROMPT) // 4 + IMAGE_TOKENS_ESTIMATE,
                max_tokens=VISION_PROBE_MAX_TOKENS, now=now)
            response = provider.see("", VISION_PROBE_PROMPT, [image_url],
                                    max_tokens=VISION_PROBE_MAX_TOKENS)
        except BudgetExceeded as exc:
            record["reason"] = f"budget: {exc}"
        except (ProviderUnusable, TransientError) as exc:
            record["reason"] = str(exc)[:400]
        else:
            answer = (response.text or "").strip().lower().strip(".")
            cost = round(
                response.input_tokens * provider.cost_per_1k_input_cad / 1000
                + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
            record.update({"answer": answer,
                           "input_tokens": response.input_tokens,
                           "output_tokens": response.output_tokens,
                           "cost_cad": cost, "headroom_cad": budget["headroom_cad"]})
            if answer in ("photograph", "diagram"):
                record["ok"] = True
            else:
                record["reason"] = (
                    f"the call succeeded and the model did not describe an image: "
                    f"{answer!r}. A 200 carrying an apology is what a broken vision path "
                    f"looks like from here")
            with db.session() as s:
                s.add(CostEntry(agent="gateway", kind=routing.COST_KIND, amount_cad=cost,
                                job_id=job_id,
                                tokens_in=response.input_tokens,
                                tokens_out=response.output_tokens,
                                detail={"purpose": VISION_PROBE_ACTION,
                                        "model": response.model,
                                        "price_basis": "assumed"}))

    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=VISION_PROBE_ACTION,
                       artifact=provider.model, detail=record))
    return record


def _a_known_image(db) -> str:
    """One gallery image URL this system has actually observed, or "".

    Deliberately reads observed evidence rather than carrying a URL as a constant: a probe
    against a hardcoded picture proves the provider works and not that it works on the
    images this company will actually ask it about.
    """
    from sqlalchemy import desc, select

    from ..core.models import BenchmarkListing

    with db.session() as s:
        rows = list(s.scalars(
            select(BenchmarkListing)
            .where(BenchmarkListing.audit_state == "audited")
            .order_by(desc(BenchmarkListing.last_seen)).limit(40)))
        for row in rows:
            for url in (row.detail or {}).get("image_urls") or []:
                if url:
                    return url
    return ""


def last_vision_probe(db) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(
            AuditLog.action == VISION_PROBE_ACTION)
            .order_by(desc(AuditLog.id)).limit(1)))
    return dict(rows[0].detail or {}) if rows else None


def vision_usable(db) -> bool:
    """Whether a real image has actually been looked at. The `image_vision` gate's condition."""
    state = last_vision_probe(db)
    return bool(state and state.get("ok"))


def last_probe(db) -> dict | None:
    """The most recent probe result, or None if nobody has ever tried."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == "model.probe")
                              .order_by(desc(AuditLog.id)).limit(1)))
    return dict(rows[0].detail or {}) if rows else None


def usable(db) -> bool:
    """Whether a real model call has actually succeeded. The gate's condition."""
    state = last_probe(db)
    return bool(state and state.get("ok"))


def state(db) -> dict:
    """What the model provider's situation actually is, in one readable object."""
    probe_state = last_probe(db)
    return {
        "key_present": bool(AnthropicProvider.key()),
        "last_probe": probe_state,
        "usable": bool(probe_state and probe_state.get("ok")),
        "spent_this_month_cad": spent_this_month_cad(db),
        "monthly_ceiling_cad": monthly_ceiling_cad(),
        "price_basis": "assumed: provider list prices read at build time, USD converted at "
                       f"an assumed {USD_TO_CAD} and padded {ESTIMATE_PADDING}x before any "
                       "ceiling check",
        "note": ("no probe has been run, so whether this key can serve a request is unknown "
                 "-- which is not the same as unavailable"
                 if probe_state is None else
                 "a real call succeeded, so the provider exists" if probe_state.get("ok")
                 else f"the key is configured and the last call failed: "
                      f"{probe_state.get('reason', '')[:200]}"),
    }
