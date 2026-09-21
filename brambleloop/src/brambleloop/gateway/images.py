"""Image generation: a different purchase from a model that can look at images.

Requirements 72, 73, 74, 75, 130, 198, 199, 200, 201, 202. The canonical Brambleloop model is
a fictional person who has to be the same person across every listing, every season and every
regeneration -- #200 calls it an identity lock and #201 makes drift a release-blocking defect.
Nothing in that is served by a language model that can see. The owner said so explicitly, and
the distinction is worth keeping in code rather than in a note:

**Looking is not making.** `gateway.anthropic.see` judges a photograph that exists. This
generates one that does not. They are different capabilities, different providers and
different bills, and the only thing they share is the ceiling they both spend against. A
system that quietly substituted the first for the second would report the model pack as
buildable and produce nothing.

**An identity lock needs reference conditioning, not a better prompt.** A prompt describing a
face produces a different face every time, within a family. What makes the same person appear
twice is conditioning generation on an approved reference image -- so a provider that cannot
take reference images cannot satisfy #200, whatever its output quality, and `SUPPORTS_LOCK`
is part of the provider table rather than a footnote.

**Unpriced is unbounded.** The same rule the text gateway learned the hard way: a provider
with no price on file is refused rather than defaulted to zero, because a model the price
table does not know bills CA$0.00 against a ceiling that counts dollars.

**Nothing here is configured yet, and the gate says so by being a probe.** A key that is set
and a provider that will generate an image are different states; so are a provider that
generates and one that refuses this company's prompts on content grounds, which is a real
outcome for a brief about an attractive adult model and one that must surface as a refusal
rather than as an empty gallery.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from ..core.resilience import PermanentError, TransientError

KEY_VAR = "BRAMBLELOOP_IMAGE_KEY"
PROVIDER_VAR = "BRAMBLELOOP_IMAGE_PROVIDER"
PROBE_ACTION = "image.probe"

# Assumed list prices, USD per generated image at the stated size, read 2026-09-20 from
# published pricing pages. An assumption and labelled one on every row this produces, exactly
# as the text gateway labels its per-token figures: these are not a measurement of this
# account's billing.
USD_TO_CAD = 1.37


@dataclass(frozen=True)
class ImageProvider:
    key: str
    what: str
    endpoint: str
    usd_per_image: float
    supports_lock: bool
    reference_images: int
    note: str
    # Which sign-up this model is bought through. Not the same thing as the model: one
    # Google AI Studio key covers two of the candidates below, and an owner action list that
    # counted models rather than accounts would ask for five sign-ups to reach five
    # candidates when three reach four of them.
    account: str = ""

    @property
    def cad_per_image(self) -> float:
        return round(self.usd_per_image * USD_TO_CAD, 6)

    def to_dict(self) -> dict:
        return {"provider": self.key, "what": self.what, "account": self.account,
                "usd_per_image": self.usd_per_image,
                "cad_per_image": self.cad_per_image,
                "supports_identity_lock": self.supports_lock,
                "reference_images": self.reference_images,
                "note": self.note, "price_basis": "assumed, read 2026-09-20"}


# Kept in step with `image_bench.CANDIDATES`, which is the list the measurement runs over.
# This table is what the *generator* can be pointed at; that one is what the benchmark
# compares. A test asserts every conditioning-capable candidate there has an entry here, so
# a model can never win a benchmark this module cannot then call.
PROVIDERS: tuple[ImageProvider, ...] = (
    ImageProvider(
        "flux-2-pro", "Black Forest Labs FLUX 2 Pro",
        "https://api.bfl.ai/v1/flux-2-pro", 0.02, True, 8,
        "cheapest of the candidates that conditions on reference images, which is what an "
        "identity lock actually is. Eight references is more than a canonical face pack "
        "needs", account="bfl"),
    ImageProvider(
        "gpt-image-2", "OpenAI GPT Image 2 at 1024px",
        "https://api.openai.com/v1/images/generations", 0.03, True, 16,
        "strongest prompt adherence of the three and the most reference images; half again "
        "the price of FLUX per image, which matters at catalogue scale and not at pack "
        "scale", account="openai"),
    ImageProvider(
        "nano-banana-2", "Google Gemini 3.1 Flash Image (Nano Banana 2)",
        "https://generativelanguage.googleapis.com/v1beta/models", 0.063, True, 5,
        "fine-grained fabric and material texture at up to 4K and feature consistency across "
        "characters. The most expensive candidate that can hold an identity, and the "
        "benchmark exists to find out whether that buys anything on crochet",
        account="google"),
    ImageProvider(
        "seedream-v5-lite", "ByteDance Seedream v5.0 Lite",
        "https://ark.cn-beijing.volces.com/api/v3/images/generations", 0.026, True, 4,
        "production-quality output at 2048px, between FLUX and GPT Image on price",
        account="volcengine"),
    ImageProvider(
        "imagen-4-standard", "Google Imagen 4 Standard",
        "https://generativelanguage.googleapis.com/v1beta/models", 0.04, False, 0,
        "best photorealism of the three and no reference conditioning on this tier, so it "
        "cannot hold an identity across a season -- listed to be ruled out on the "
        "requirement rather than on taste", account="google"),
)

BY_KEY: dict[str, ImageProvider] = {p.key: p for p in PROVIDERS}


# The sign-ups behind those models, because the owner action is an account and not a model.
# `minutes` and `needs_card` are what makes this list orderable on a phone: an account that
# unlocks two candidates for free and two minutes is not the same ask as one that needs a
# card and an identity check, and an action list that did not say so would be sorted by
# whichever provider was typed first.
#
# `reachable` is the honest column. Volcano Engine is where Seedream is bought and it wants a
# mainland Chinese account with phone verification; calling that a two-minute action and
# leaving it in the list is how a benchmark ends up permanently one candidate short with
# nobody able to say why.
ACCOUNTS: dict[str, dict] = {
    "google": {
        "name": "Google AI Studio",
        "where": "https://aistudio.google.com/apikey",
        "needs_card": False,
        "reachable": True,
        "minutes": 2,
        "how": ("sign in with the Google account already on the phone, tap Get API key, "
                "tap Create API key, copy it"),
        "why_first": ("free to create and it is the only account that unlocks two "
                      "candidates, one of them the texture-strongest one"),
    },
    "bfl": {
        "name": "Black Forest Labs",
        "where": "https://api.bfl.ai",
        "needs_card": True,
        "reachable": True,
        "minutes": 4,
        "how": "register, add a card, buy the smallest credit pack, copy the API key",
        "why_first": ("the cheap candidate the owner refused to lock on price alone. It "
                      "cannot be ruled in or out without being measured"),
    },
    "openai": {
        "name": "OpenAI platform",
        "where": "https://platform.openai.com/api-keys",
        "needs_card": True,
        "reachable": True,
        "minutes": 4,
        "how": ("sign in, add a payment method under Billing, set a low usage limit, "
                "create a secret key, copy it"),
        "why_first": ("the strongest prompt adherence of the candidates and the most "
                      "reference images, which is what an identity lock conditions on"),
    },
    "volcengine": {
        "name": "Volcano Engine (ByteDance)",
        "where": "https://www.volcengine.com",
        "needs_card": True,
        "reachable": False,
        "minutes": 0,
        "how": "",
        "why_first": "",
        "unreachable_because": (
            "registration expects a mainland Chinese mobile number and identity "
            "verification. Listed so the benchmark can report Seedream as unmeasured for a "
            "named reason rather than leaving a candidate silently absent"),
    },
}


def key_var(account: str) -> str:
    """The environment variable holding one account's credential.

    Per account rather than per model, because that is how the credential is actually
    issued: one Google key renders both Google candidates, and two variables holding the
    same secret is a secret that gets rotated in one of them.
    """
    return f"BRAMBLELOOP_IMAGE_KEY_{account.upper()}"


def key_for(provider_key: str, env: dict[str, str] | None = None) -> str:
    """This provider's credential, or empty.

    Falls back to the single `BRAMBLELOOP_IMAGE_KEY` only when `BRAMBLELOOP_IMAGE_PROVIDER`
    names this same provider -- so a one-provider environment keeps working with one
    variable, and a benchmark across four providers cannot accidentally send all four
    requests with whichever key happened to be in the general slot. That accident would not
    look like a failure: it would look like four candidates scoring identically.
    """
    e = env if env is not None else os.environ
    provider = BY_KEY.get(provider_key)
    if provider is None:
        return ""
    specific = (e.get(key_var(provider.account)) or "").strip()
    if specific:
        return specific
    if (e.get(PROVIDER_VAR) or "").strip() == provider_key:
        return (e.get(KEY_VAR) or "").strip()
    return ""


def available(env: dict[str, str] | None = None) -> list[str]:
    """Which providers this environment holds a credential for. Not which ones work."""
    return [p.key for p in PROVIDERS if key_for(p.key, env)]


def credential_plan(env: dict[str, str] | None = None) -> dict:
    """The owner actions that would unlock the most candidates for the least phone time.

    Ordered by what each account unlocks rather than by provider name, and it reports what
    stays unmeasurable afterwards. A plan that listed only what to create would read as
    though completing it measured everything.
    """
    have = set(available(env))
    todo = []
    for account, info in ACCOUNTS.items():
        models = [p for p in PROVIDERS if p.account == account]
        unlocked = [p.key for p in models if p.key not in have]
        if not unlocked or not info["reachable"]:
            continue
        if any(p.key in have for p in models):
            continue        # the account exists; its models are already reachable
        todo.append({
            "account": account, "name": info["name"], "where": info["where"],
            "how": info["how"], "minutes": info["minutes"],
            "needs_card": info["needs_card"],
            "unlocks": unlocked,
            "unlocks_count": len(unlocked),
            "set_variable": key_var(account),
            "why": info["why_first"],
        })
    # Free first, then by how many candidates one sign-up unlocks, then by how long it takes.
    todo.sort(key=lambda row: (row["needs_card"], -row["unlocks_count"], row["minutes"]))

    unreachable = [{"account": a, "models": [p.key for p in PROVIDERS if p.account == a],
                    "why": info.get("unreachable_because", "")}
                   for a, info in ACCOUNTS.items() if not info["reachable"]]
    return {
        "have": sorted(have),
        "actions": todo,
        "total_minutes": sum(row["minutes"] for row in todo),
        "unreachable": unreachable,
        "still_unmeasured_after": sorted(
            {p.key for p in PROVIDERS if p.key not in have}
            - {m for row in todo for m in row["unlocks"]}),
        "note": ("one account can cover more than one candidate, so this counts sign-ups "
                 "rather than models. Nothing here is a claim that a key works: the probe "
                 "is what says that"),
    }

# What the requirements actually need generated, so "how much a month" is answerable before
# anything is bought rather than after. Counts are this build's estimate and are labelled.
WORKLOAD: dict[str, dict] = {
    "candidate_tournament": {
        "requirement": 199, "images": 24, "once": True,
        "why": "a controlled candidate set wide enough that the owner's choice is a choice"},
    "identity_reference_pack": {
        "requirement": 200, "images": 20, "once": True,
        "why": "canonical face views, expression and lighting range, frozen after selection"},
    "listing_creative": {
        "requirement": 130, "images": 60, "once": False,
        "why": "model-led frames across the listings a month produces"},
    "anti_drift_regeneration": {
        "requirement": 201, "images": 20, "once": False,
        "why": "assets that failed the identity check are regenerated, never shipped"},
}


class ImagesNotConfigured(PermanentError):
    """No provider or no key. Not an outage: there is nothing to call."""


class ImagesRefused(PermanentError):
    """The provider answered and the answer is not an image."""


class SubstitutionRefused(PermanentError):
    """Somebody tried to satisfy image generation with a model that can only look."""


def refuse_vision_substitution(reason: str = "") -> None:
    """Called where the temptation lives, so the refusal is in the code path.

    The owner named this one specifically: do not silently substitute ordinary language-model
    vision for image generation. It is a tempting substitution because the vision capability
    exists, is paid for and answers questions about pictures -- and it cannot produce one.
    A system that made the swap would report the model pack as progressing.
    """
    raise SubstitutionRefused(
        "image generation is not image understanding. `gateway.anthropic.see` judges a "
        "photograph that exists; nothing in it makes one. The canonical model (#198-#202) "
        "needs a generator that conditions on reference images, and no amount of looking "
        f"substitutes for that. {reason}".strip())


def configured_provider(env: dict[str, str] | None = None) -> ImageProvider | None:
    """Which provider this environment names, refusing one with no price on file."""
    e = env if env is not None else os.environ
    key = (e.get(PROVIDER_VAR) or "").strip()
    if not key:
        return None
    provider = BY_KEY.get(key)
    if provider is None:
        raise ImagesRefused(
            f"{key!r} has no price on file, so what it spends cannot be checked against the "
            f"ceiling. An unpriced call is an unbounded one. Known: {sorted(BY_KEY)}")
    return provider


def api_key(env: dict[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    return (e.get(KEY_VAR) or "").strip()


def configured(env: dict[str, str] | None = None) -> bool:
    """Whether any provider has a credential in this environment. Deliberately not `usable`.

    Reads the per-account variables as well as the general slot, because the benchmark can
    run on a Google key alone and a `configured` that only knew about `BRAMBLELOOP_IMAGE_KEY`
    would report nothing configured while four candidates were reachable.
    """
    try:
        if configured_provider(env) and api_key(env):
            return True
    except ImagesRefused:
        pass
    return bool(available(env))


def monthly_estimate_cad(provider: ImageProvider) -> dict:
    """What the workload above costs at this provider, one-off and recurring apart.

    Two numbers rather than one. The candidate tournament and the reference pack are bought
    once; listing creative and regeneration are bought every month, and a single blended
    figure would make the first month look like the standing rate.
    """
    once = sum(w["images"] for w in WORKLOAD.values() if w["once"])
    recurring = sum(w["images"] for w in WORKLOAD.values() if not w["once"])
    return {
        "provider": provider.key,
        "one_off_images": once,
        "one_off_cad": round(once * provider.cad_per_image, 2),
        "monthly_images": recurring,
        "monthly_cad": round(recurring * provider.cad_per_image, 2),
        "first_month_cad": round((once + recurring) * provider.cad_per_image, 2),
        "price_basis": "assumed list price read 2026-09-20, not a measurement of billing",
    }


def generate(prompt: str, *, reference_urls: list[str] | None = None,
             env: dict[str, str] | None = None, size: str = "1024x1024",
             provider_key: str | None = None, timeout: float = 120.0) -> dict:
    """Ask the configured provider for one image. Raises rather than returning nothing.

    The request is deliberately thin and provider-shaped at one place: every candidate here
    takes a prompt, an optional set of reference images and a size, and the differences
    between their payloads are not worth an abstraction nobody has exercised. When a provider
    is actually chosen this is where its exact body goes, and the probe below is what proves
    the body is right rather than plausible.
    """
    import urllib.error
    import urllib.request

    e = env if env is not None else os.environ
    # `provider_key` is how the benchmark asks for a specific candidate. Without it this
    # falls back to whichever provider the environment names, which is right for ordinary
    # generation and wrong for a comparison: a benchmark that sent every candidate's prompt
    # to one provider would not fail, it would return five identical-looking scores and call
    # the cheapest of them a winner.
    provider = BY_KEY.get(provider_key) if provider_key else configured_provider(e)
    if provider_key and provider is None:
        raise ImagesRefused(
            f"{provider_key!r} has no price on file, so what it spends cannot be checked "
            f"against the ceiling. Known: {sorted(BY_KEY)}")
    key = key_for(provider.key, e) if provider else ""
    if provider is None or not key:
        want = provider.key if provider else "a provider"
        raise ImagesNotConfigured(
            f"no credential for {want}. Set {key_var(provider.account)} if it is named, or "
            f"{PROVIDER_VAR} to one of {sorted(BY_KEY)} with {KEY_VAR} as that provider's "
            f"key. This is the state the gate describes rather than a failure to retry")

    payload = json.dumps({
        "prompt": prompt, "size": size,
        **({"reference_images": list(reference_urls)} if reference_urls else {}),
    }).encode()
    request = urllib.request.Request(provider.endpoint, data=payload, method="POST")
    request.add_header("content-type", "application/json")
    request.add_header("authorization", f"Bearer {key}")

    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        if exc.code in (429, 500, 502, 503, 504):
            raise TransientError(f"{provider.key} {exc.code}: {detail}") from exc
        # A content refusal is permanent and is a fact about the brief rather than the
        # wiring. It must surface as a refusal with the provider's words, not as an empty
        # gallery somebody later explains as a rendering bug.
        raise ImagesRefused(f"{provider.key} {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise TransientError(f"{provider.key} unreachable: {exc.reason}") from exc

    url = _first_image(body)
    if not url:
        raise ImagesRefused(
            f"{provider.key} answered without an image. A 200 with no picture in it is what "
            f"a content refusal and a wrong payload shape both look like from here")
    return {"provider": provider.key, "url": url, "size": size,
            "cad": provider.cad_per_image,
            "latency_ms": round((time.time() - started) * 1000, 2)}


def _first_image(body: dict) -> str:
    for container in (body.get("data"), body.get("images"), body.get("output")):
        for item in container or []:
            if isinstance(item, str) and item.startswith("http"):
                return item
            if isinstance(item, dict):
                for field in ("url", "image_url", "b64_json"):
                    if item.get(field):
                        return str(item[field])
    return str(body.get("url") or "")


def probe(db, *, env: dict[str, str] | None = None, generator=None,
          now: datetime | None = None, job_id: int | None = None) -> dict:
    """Generate one real image and record whether that worked. The gate's evidence.

    The gate this replaces read whether `BRAMBLELOOP_IMAGE_KEY` was set. A key that is set,
    a key for a provider with no price on file, an account with no credit and a provider that
    refuses this company's brief on content grounds are four states and one string, and the
    fourth is a genuine possibility for a brief about an attractive adult model that this
    system must surface rather than absorb.
    """
    from ..core.models import AuditLog, CostEntry
    from . import routing

    e = env if env is not None else os.environ
    record: dict = {"at": (now or datetime.now(timezone.utc)).isoformat(),
                    "ok": False, "reason": "", "provider": ""}
    try:
        provider = configured_provider(e)
    except ImagesRefused as exc:
        provider = None
        record["reason"] = str(exc)[:400]

    if provider is None and not record["reason"]:
        record["reason"] = f"no {PROVIDER_VAR} in this environment"
    elif provider is not None and not api_key(e):
        record["reason"] = f"no {KEY_VAR} in this environment"
        record["provider"] = provider.key
    elif provider is not None:
        record["provider"] = provider.key
        try:
            got = (generator or generate)(
                "A plain grey fabric swatch on a white background, product photograph.",
                env=e, size="1024x1024")
        except (PermanentError, TransientError) as exc:
            record["reason"] = str(exc)[:400]
        else:
            record.update({"ok": True, "url_present": bool(got.get("url")),
                           "cad": got.get("cad"), "latency_ms": got.get("latency_ms")})
            from ..finance import spend_report

            spend_report.record(
                db, agent="gateway", amount_cad=float(got.get("cad") or 0.0),
                estimated_cad=provider.cad_per_image, purpose=PROBE_ACTION,
                provider=provider.key, model=provider.key, department="gateway",
                job_id=job_id, kind=routing.COST_KIND,
                detail={"price_basis": "assumed"})

    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=PROBE_ACTION,
                       artifact=record.get("provider") or "none", detail=record))
    return record


def last_probe(db) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == PROBE_ACTION)
                              .order_by(desc(AuditLog.id)).limit(1)))
    return dict(rows[0].detail or {}) if rows else None


def usable(db) -> bool:
    """Whether an image has actually been generated. The `image_generation` condition."""
    state_ = last_probe(db)
    return bool(state_ and state_.get("ok"))


def state(db, *, env: dict[str, str] | None = None) -> dict:
    """The decision this needs from the owner, with the numbers already worked out."""
    try:
        provider = configured_provider(env)
        provider_error = ""
    except ImagesRefused as exc:
        provider, provider_error = None, str(exc)
    last = last_probe(db)

    from . import image_bench

    return {
        "configured": configured(env),
        "provider": provider.key if provider else None,
        "provider_error": provider_error,
        "key_present": bool(api_key(env)),
        "credentialled": available(env),
        "credential_plan": credential_plan(env),
        "last_probe": last,
        "usable": bool(last and last.get("ok")),
        "candidates": [p.to_dict() for p in PROVIDERS],
        # No standing recommendation. There was one -- the cheapest candidate that supports
        # reference conditioning -- and the owner's 2026-09-20 decision replaced it with a
        # measurement: do not lock a provider because it is inexpensive, and a moderately
        # dearer model that materially outperforms is worth paying for. Naming a winner here
        # would be the price list deciding again, with a benchmark sitting beside it.
        "recommended": None,
        "why_no_recommendation": (
            "the choice is measured rather than reasoned. gateway/image_bench.py renders the "
            "same six Brambleloop trials on every eligible model, five samples each, and "
            "scores them blind against a rubric whose every line cites a requirement. Until "
            "it runs there is no winner, and the cheapest candidate is not a default"),
        "benchmark": image_bench.state(),
        "workload": WORKLOAD,
        "estimate_per_candidate": {
            p.key: monthly_estimate_cad(p) for p in PROVIDERS if p.supports_lock},
        "never": ("image generation is not image understanding. The model that can look at a "
                  "photograph cannot make one, and substituting it is refused in code rather "
                  "than discouraged in a note"),
    }
