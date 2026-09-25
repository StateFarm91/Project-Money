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
standing ceiling is read from `finance.spend_policy` -- CA$100 a month since
2026-09-20, raised from CA$25. It is checked from CostEntry rows -- the same
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
    # and a monthly ceiling that cheap work could never reach.
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}
DEFAULT_MODEL = "claude-sonnet-5"

# Assumed, not fetched. A rate this company does not control and does not measure.
USD_TO_CAD = 1.37

# Applied to every estimate before it is checked against the ceiling. A ceiling that trusts an
# optimistic estimate is crossed before anybody notices.
ESTIMATE_PADDING = 1.25

# The owner's standing ceiling, read from the policy rather than restated. It was written
# here *and* in `routing`, which is the defect this file's own price comment names: a number
# written twice is a number that will drift. Overridable downward by environment so it can be
# lowered without a deploy, never raised silently past the authorised figure.
def _policy_ceiling() -> float:
    from ..finance.spend_policy import ceiling_cad

    return ceiling_cad()

# What one gallery image costs to look at, in input tokens. This number is used to refuse a
# call before it is made, so it has to be no *smaller* than the truth -- an optimistic
# estimate turns a ceiling into a suggestion.
#
# Wrong twice in the dangerous direction, and the second time is the instructive one.
#
# It was 800, from the provider's (width x height) / 750 rule against Etsy's 570-wide gallery
# variant. The first production probe measured 1,562 for one image and a thirty-token prompt,
# because what `observe.py` stores is `il_fullxfull` -- the full-size original, not the
# thumbnail the arithmetic assumed. Raised to 2,000 from that measurement, which looked like
# room above it.
#
# The first real analysis run then billed 126,518 input tokens for 25 images: about **5,000
# tokens an image**, two and a half times the corrected figure. A single probe measured one
# small image and generalised; the catalogue's galleries are larger than the one that
# happened to be first. Both errors were the same shape -- an estimate derived from a rule
# or a sample rather than from the workload -- and both went under, which is the direction
# that turns a ceiling into a suggestion.
#
# 6,000 is the measured mean with a fifth above it, and it was found by the
# reservation-versus-bill reconciliation the owner's spend policy asked for, on the first
# run after that reconciliation existed. Three ways of being wrong about this number have now
# been tried; the one that worked was measuring the actual work.
IMAGE_TOKENS_ESTIMATE = 6000

# One refusal should not lose a batch of observations. Also the practical limit on how much
# of one listing's gallery is worth judging in a single question.
MAX_IMAGES_PER_CALL = 8

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class BudgetExceeded(PermanentError):
    """The monthly model ceiling would be crossed by this call."""


class AgentCeilingExceeded(BudgetExceeded):
    """This agent's daily permission is spent. The month may still have room.

    A subclass so every `except BudgetExceeded` already in the codebase keeps refusing, and so
    the two can be told apart where the difference matters -- because they are different
    facts. The monthly ceiling is the authorised budget and crossing it stops the company. An
    agent's daily ceiling is a *permission*: the owner's ruling of 2026-09-25 is explicit that
    per-agent ceilings are permissions rather than additive allocations, which is why
    twenty-four agents declaring about CA$57 a day against a CA$100 month is not an
    over-commitment. Hitting one means this agent is finished for today and the work resumes at
    the next UTC day, so it is a pause rather than a defect, and the message says which
    ceiling and what to do.
    """


class ProviderUnusable(PermanentError):
    """The key authenticates and the account cannot serve a request."""


def provider_for(task_key: str, **kw) -> "AnthropicProvider":
    """A provider on the tier the declared task routes to.

    Added 2026-09-20 when reconciling routing against the owner's quality-first policy.
    Four call sites were constructing providers with a hardcoded cheap model and never
    consulting `routing.TASKS` at all -- so the declared tier for gallery observation said
    `standard` and the code that made the call used `cheap`, for a day, on the owner's
    second-highest spending priority. A table nothing reads is documentation.
    """
    from . import routing

    _, tier = routing.route(task_key)
    return AnthropicProvider(model=tier.model, **kw)


def monthly_ceiling_cad() -> float:
    """The ceiling in force. Environment may lower it; nothing may raise it."""
    authorised = _policy_ceiling()
    raw = (os.environ.get("BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD") or "").strip()
    try:
        value = float(raw) if raw else authorised
    except ValueError:
        return authorised
    return min(value, authorised)


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


def agent_daily_ceiling(db, agent: str, *, now: datetime | None = None) -> dict | None:
    """This agent's daily permission and what it has spent against it today.

    `None` when the name has no `Agent` row. That is not a ceiling of zero and it is not a
    ceiling of infinity -- it is a spender the registry has never heard of, which production
    has four of (`gateway`, `publishing`, `intel`, and whatever gets added next). Inventing a
    ceiling for them here would be enforcing a number nobody authorised; reporting the absence
    is what `spend_report.per_agent_today` already does, under
    `spenders_with_no_agent_row`.
    """
    from ..agents.registry import PermissionDenied, Registry

    if not agent:
        return None
    registry = Registry(db)
    try:
        row = registry.get(agent)
    except PermissionDenied:
        return None
    ceiling = float(row.daily_cost_ceiling_cad or 0.0)
    if ceiling <= 0:
        return None
    return {"agent": agent, "daily_ceiling_cad": ceiling,
            "spent_today_cad": registry.spend_today(agent, now=now)}


def check_budget(db, *, model: str, input_tokens: int, max_tokens: int,
                 now: datetime | None = None, uncommitted_cad: float = 0.0,
                 agent: str = "", purpose: str = "", job_id: int | None = None,
                 reserve: bool = True, holder: str | None = None,
                 ttl_seconds: int | None = None) -> dict:
    """Refuse a call that would cross the ceiling, before it is made.

    Assumes the model writes its entire output allowance. It usually does not, and budgeting
    for the usual case is how a ceiling becomes a target.

    Three things are checked, in the order the owner's ruling of 2026-09-25 puts them in:

    1. **The authorised monthly ceiling**, which is the budget. It counts the billed month,
       this caller's own unbilled spend, and every *other* caller's live reservation.
    2. **This agent's daily ceiling**, which is a permission rather than a share of the
       budget. `AgentCeilingExceeded` says which ceiling and that the work resumes tomorrow.
    3. Nothing else. A purpose's monthly allocation is `spend_policy.may_spend`'s job and is
       asked once per batch by the handler, not once per call.

    `uncommitted_cad` is money this caller has already spent and has not yet written to a
    cost row. It exists because the ceiling is read from rows and the callers that spend the
    most write one row per *run*, not one per call: `intel.vision` judges up to a page of
    gallery images in a loop and bills once at the end, and `visual.inspect` makes two vision
    calls and bills once. Every call after the first in those loops was therefore checked
    against the month as it stood before the loop began -- so a guard whose whole purpose is
    to refuse before the call was, in practice, refusing only the first call of each batch.
    Production ran about twenty-one vision calls behind one ledger row on 2026-09-24.

    A caller that passes nothing gets the old behaviour, which is correct for a caller that
    bills each call. A caller that batches must pass what it is holding, and the amount is
    its running *actual* spend plus what it has estimated for calls still unbilled -- the
    same pessimism the padding applies, for the same reason.

    **The cross-process half is now closed too, and it is a row rather than an argument.** A
    live reservation from another holder is counted against the month, and this call writes
    one of its own before returning, which the caller releases when it bills
    (`release_reservation`). An unreleased reservation expires, so a holder that dies holds
    budget for its TTL rather than for the rest of the month -- `finance.reservations` has the
    reasoning. `reserve=False` is for a caller that only wants the arithmetic, and it is not
    what a caller about to spend money should pass.
    """
    from ..finance import reservations

    me = holder or reservations.holder_id()
    spent = spent_this_month_cad(db, now=now)
    mine = max(0.0, float(uncommitted_cad or 0.0))
    others = reservations.outstanding(db, exclude_holder=me, now=now)
    committed = round(spent + mine + others["cad"], 6)
    ceiling = monthly_ceiling_cad()
    estimate = estimate_cad(model, input_tokens=input_tokens, output_tokens=max_tokens)

    # 1. The authorised month. This is the budget, and it is the one that stops the company.
    if committed + estimate > ceiling:
        raise BudgetExceeded(
            f"this call is estimated at CA${estimate:.4f} against CA${committed:.4f} "
            f"already committed this month (CA${spent:.4f} billed, "
            f"CA${mine:.4f} spent by this run and not yet billed, "
            f"CA${others['cad']:.4f} reserved right now by {others['count']} other "
            f"caller(s)) and a ceiling of CA${ceiling:.2f}. Refused before the call rather "
            f"than found on the invoice. The way past this is the owner raising the ceiling "
            f"with measured usage attached, not a cheaper model")

    # 2. This agent's daily permission. Second, because the month is authoritative and a
    #    per-agent ceiling is a permission rather than a slice of it.
    permission = agent_daily_ceiling(db, agent, now=now)
    if permission is not None:
        today = permission["spent_today_cad"]
        allowed = permission["daily_ceiling_cad"]
        if today + mine + estimate > allowed:
            raise AgentCeilingExceeded(
                f"agent {agent!r} may spend CA${allowed:.2f} a day and has committed "
                f"CA${today + mine:.4f} of it (CA${today:.4f} billed, CA${mine:.4f} unbilled "
                f"in this run); this call is estimated at CA${estimate:.4f}. Refused before "
                f"the call. This is a daily permission, not the budget -- the month still "
                f"has CA${round(ceiling - committed, 2):.2f} of headroom -- so this agent's "
                f"work resumes at the next UTC day. To do more today, either lower the work "
                f"this agent asks for (the cadence is derived from this ceiling, so it will "
                f"follow) or have the owner raise the agent's ceiling in "
                f"`agents.registry.DEFAULT_AGENTS`")

    # 3. Written down before the call, so another process reading the same month sees it.
    reservation_id = None
    if reserve:
        # `now` is threaded through deliberately. Without it the row's expiry is stamped from
        # the wall clock while every reader of it is asking about `now`, so a caller that
        # supplies a timestamp writes a reservation that reads as already expired -- a
        # reservation that protects nothing, in exactly the callers that are most careful
        # about which instant they mean.
        reservation_id = reservations.reserve(
            db, amount_cad=estimate, holder=me, agent=agent, purpose=purpose, model=model,
            job_id=job_id, now=now,
            ttl_seconds=(reservations.DEFAULT_TTL_SECONDS if ttl_seconds is None
                         else ttl_seconds))

    return {"spent_cad": spent, "committed_cad": committed, "ceiling_cad": ceiling,
            "estimate_cad": estimate,
            "headroom_cad": round(ceiling - committed - estimate, 6),
            "uncommitted_cad": round(mine, 6),
            "reserved_by_others_cad": others["cad"],
            "reserved_by_others_count": others["count"],
            "expired_unreleased_cad": others["expired_unreleased_cad"],
            "agent_permission": permission,
            "holder": me,
            "reservation_id": reservation_id}


def release_reservation(db, reservation_id: int | None, *,
                        actual_cad: float | None = None) -> bool:
    """Give back what `check_budget` reserved, with the bill when the caller has it.

    Called in a `finally`, or immediately after the provider answers. A caller that forgets
    is not a leak that lasts: the reservation expires. It is, though, a caller that holds
    budget nobody is spending for up to five minutes, which is why
    `reservations.sweep` records the abandonment instead of quietly tidying it away.
    """
    from ..finance import reservations

    return reservations.release(db, reservation_id, actual_cad=actual_cad)


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

        content: list[dict] = [_image_block(ref) for ref in image_urls]
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
        budget: dict = {}
        try:
            budget = check_budget(db, model=provider.model,
                                  input_tokens=len(PROBE_PROMPT) // 4,
                                  max_tokens=PROBE_MAX_TOKENS, now=now,
                                  agent="gateway", purpose="model.probe", job_id=job_id)
            response = provider.complete("", PROBE_PROMPT, max_tokens=PROBE_MAX_TOKENS)
        except BudgetExceeded as exc:
            record["reason"] = f"budget: {exc}"
        except (ProviderUnusable, TransientError) as exc:
            # The provider's own words. A key that authenticates and an account that cannot
            # serve a request are different failures, and only the message distinguishes them.
            record["reason"] = str(exc)[:400]
            from ..ops import funding

            record["funding"] = funding.note(db, record["reason"])
        else:
            cost = round(
                response.input_tokens * provider.cost_per_1k_input_cad / 1000
                + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
            record.update({"ok": True, "reason": "",
                           "input_tokens": response.input_tokens,
                           "output_tokens": response.output_tokens,
                           "cost_cad": cost, "headroom_cad": budget["headroom_cad"]})
            # Through the accounting writer, so the probe's spend carries the same six
            # dimensions as everything else. It wrote a bare CostEntry with the purpose in
            # a JSON blob, which is how twenty-four of the first twenty-five rows in the
            # live ledger came back `unattributed`.
            from ..finance import spend_report

            spend_report.record(
                db, agent="gateway", amount_cad=cost, estimated_cad=budget["estimate_cad"],
                purpose="model.probe", provider="anthropic", model=response.model,
                department="gateway", job_id=job_id, kind=routing.COST_KIND,
                tokens_in=response.input_tokens, tokens_out=response.output_tokens,
                detail={"price_basis": "assumed", "latency_ms": record.get("latency_ms")})

            # A call that got an answer is evidence the balance is no longer the blocker,
            # which is the only honest way to close an owner action about money: by the
            # thing working again rather than by somebody ticking it.
            from ..ops import funding

            record["funding"] = funding.cleared(db)
        finally:
            # Released whichever way the call went. A probe that failed still took the
            # reservation, and a reservation nobody gives back holds budget until it expires.
            release_reservation(db, budget.get("reservation_id"),
                               actual_cad=record.get("cost_cad"))

    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action="model.probe", artifact=provider.model,
                       detail=record))
    return record


def _image_block(reference: str) -> dict:
    """One image content block, from a URL or from a file on this disk.

    Competitor evidence arrives as URLs the sanctioned Etsy endpoint returns, and nothing is
    downloaded or re-hosted: the observation is stored and the picture is not, which is also
    what keeps benchmark study on the right side of "never copy a competitor's expression".

    This company's *own* rendered assets are files, and #61 and #79 are checks on those. They
    are read and sent inline rather than published somewhere first, because putting an
    unreleased listing asset on a public URL to have it judged would be a release.
    """
    import base64
    import mimetypes
    from pathlib import Path

    if reference.startswith(("http://", "https://")):
        return {"type": "image", "source": {"type": "url", "url": reference}}

    path = Path(reference)
    if not path.is_file():
        raise ProviderUnusable(
            f"{reference!r} is neither a URL nor a file on this disk. An image reference "
            f"that resolves to nothing would be sent as a question about no picture")
    data = path.read_bytes()
    media_type = _sniff(data) or mimetypes.guess_type(path.name)[0]
    if media_type not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        raise ProviderUnusable(
            f"{reference!r} is not an image format the provider accepts "
            f"(png, jpeg, gif, webp); its bytes read as {media_type or 'nothing known'}")
    return {"type": "image",
            "source": {"type": "base64", "media_type": media_type,
                       "data": base64.standard_b64encode(data).decode()}}


# The four formats' magic numbers, because a filename is not evidence about bytes.
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def _sniff(data: bytes) -> str | None:
    """What this file actually is, from its first bytes rather than from its name.

    The artifact store is content-addressed, so its files are named for their sha256 and
    have no extension at all -- and `guess_type` on such a name returns nothing. Defaulting
    that to `image/png` is a guess wearing a fact's clothes, and on 2026-09-22 it cost the
    identity floor: the canonical portrait is a JPEG, it was recovered from the store as an
    extensionless file, sent to the provider labelled `image/png`, refused, and the face
    comparison came back `unmeasurable` on all five dimensions. The body reference happened
    to be a PNG and worked, so half the identity check passed and half silently did not.

    Sniffing is authoritative and the filename is the fallback, never the other way round.
    A file whose bytes say nothing recognisable is refused rather than assumed.
    """
    for magic, media_type in _MAGIC:
        if data.startswith(magic):
            return media_type
    # WEBP is RIFF....WEBP, so the tag is not at offset zero.
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


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
        budget: dict = {}
        try:
            budget = check_budget(
                db, model=provider.model,
                input_tokens=len(VISION_PROBE_PROMPT) // 4 + IMAGE_TOKENS_ESTIMATE,
                max_tokens=VISION_PROBE_MAX_TOKENS, now=now,
                agent="gateway", purpose=VISION_PROBE_ACTION, job_id=job_id)
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
            from ..finance import spend_report

            spend_report.record(
                db, agent="gateway", amount_cad=cost, estimated_cad=budget["estimate_cad"],
                purpose=VISION_PROBE_ACTION, provider="anthropic", model=response.model,
                department="gateway", job_id=job_id, kind=routing.COST_KIND,
                tokens_in=response.input_tokens, tokens_out=response.output_tokens,
                detail={"price_basis": "assumed"})

            # This call got an answer, so the balance is no longer the blocker.
            #
            # `funding.cleared` was reached only from `model.probe`, and the funding action
            # is the only thing `funding.blocked` reads -- so a successful *vision* probe
            # proved the credential worked and changed nothing. Live, 2026-09-23: the
            # vision probe came back working at 20:37Z while the funding action stayed open
            # on an 18:00Z `model.probe` failure, and both owner-authorised experiments
            # went on refusing for three and a half hours with the evidence to unblock them
            # already on file.
            #
            # A gate reading one specific probe rather than the thing the probe is evidence
            # of. The clear belongs to any real call that got an answer, which is exactly
            # what `funding.cleared`'s own docstring says it is for.
            from ..ops import funding

            record["funding"] = funding.cleared(db)
        finally:
            release_reservation(db, budget.get("reservation_id"),
                               actual_cad=record.get("cost_cad"))

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
