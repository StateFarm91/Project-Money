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
    # The exact identifier on the wire, and which API dialect to speak. These exist because
    # the first version of `generate` sent one invented body -- `{"prompt", "size"}` with a
    # bearer token -- to every provider's base endpoint, on the reasoning that the
    # differences "are not worth an abstraction nobody has exercised". The moment a real key
    # existed the reasoning collapsed: Google wants `x-goog-api-key`, a `:generateContent`
    # suffix, a `contents` array and an `imageConfig`, and would have refused that body under
    # any billing arrangement. An abstraction nobody has exercised is not thin, it is untested.
    model: str = ""
    dialect: str = ""

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
        "needs", account="bfl", model="flux-2-pro", dialect="bfl"),
    ImageProvider(
        "gpt-image-2", "OpenAI GPT Image 2 at 1024px",
        "https://api.openai.com/v1/images/generations", 0.03, True, 16,
        "strongest prompt adherence of the three and the most reference images; half again "
        "the price of FLUX per image, which matters at catalogue scale and not at pack "
        "scale", account="openai", model="gpt-image-2", dialect="openai"),
    ImageProvider(
        "nano-banana-2", "Google Gemini 3.1 Flash Image (Nano Banana 2)",
        "https://generativelanguage.googleapis.com/v1beta/models", 0.101, True, 5,
        "fine-grained fabric and material texture at up to 4K and feature consistency across "
        "characters. The most expensive candidate that can hold an identity, and the "
        "benchmark exists to find out whether that buys anything on crochet. "
        "US$0.101 read from Google's own pricing page 2026-09-21: image output is billed at "
        "US$60 per million tokens and a 2048px image is 1,680 of them. The table said 0.063, "
        "which is nearer the 1K figure (1,120 tokens, US$0.067) -- and this candidate is "
        "benchmarked at 2K, so the estimate was for a rendering nobody was going to do",
        account="google", model="gemini-3.1-flash-image", dialect="google"),
    ImageProvider(
        "seedream-v5-lite", "ByteDance Seedream v5.0 Lite",
        "https://ark.cn-beijing.volces.com/api/v3/images/generations", 0.026, True, 4,
        "production-quality output at 2048px, between FLUX and GPT Image on price",
        account="volcengine", model="seedream-5-0-lite", dialect="openai"),
    # Imagen 4 was here, listed to be ruled out on the requirement rather than on taste: no
    # reference conditioning, so #200 and #201 are unmeetable by it whatever its
    # photorealism. It is removed rather than re-priced because on 2026-09-21 it no longer
    # appears on Google's Gemini API pricing page at all. A provider table is what the
    # generator can be *pointed at*, and a row for a model that cannot be bought is a row
    # that will one day be selected. The exclusion itself is kept in `image_bench.CANDIDATES`,
    # where it is a recorded decision rather than an endpoint.
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
        # Corrected 2026-09-21 against Google's own pricing page. The key is free to create
        # and this said so and stopped there, which made it the first and easiest action in
        # the owner's list. But Nano Banana 2's image output reads "Not available" under Free
        # Tier: generation is paid-tier only, so a key created without billing produces a
        # refusal rather than an image. "Free to create" and "free to use" are different
        # claims and the owner was given the wrong one.
        "needs_card": True,
        "reachable": True,
        "minutes": 4,
        "how": ("sign in with the Google account already on the phone, tap Get API key, "
                "create the key in a project with billing enabled -- image output is not "
                "available on the free tier -- and copy it"),
        "why_first": ("the texture-strongest candidate, and the one the benchmark exists to "
                      "test: it is also the dearest, so whether 4K fabric detail is worth "
                      "five times FLUX's price is exactly the question"),
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


class QuotaUnavailable(PermanentError):
    """The account cannot pay for this call. Not a rate limit, and not a content refusal.

    Two live responses on 2026-09-21 made the case for a separate class:

    Google answered 429 `generate_content_free_tier_requests, limit: 0`. A rate limit says
    "slower"; a free-tier limit of zero says "not on this plan". Both arrive as 429 and only
    one is worth retrying, and the generic mapping would have had the queue back off and
    retry a request that could never succeed, reporting a transient outage the whole time.

    Black Forest Labs answered 402 `Insufficient credits`. That fell through to
    `ImagesRefused`, whose message says a content refusal "is a fact about the brief rather
    than the wiring" -- so the audit log would have recorded the provider declining to
    render a crochet basket on content grounds, when the actual fact was an empty balance.
    A wrong diagnosis in the log is worse than none, because somebody acts on it: the answer
    to a content refusal is a new brief, and the answer to this is a top-up.
    """


# What a 429 body says when the answer is "not on this plan" rather than "slower". Matched
# on the provider's own words because there is no status code for the difference.
_PERMANENT_QUOTA: tuple[str, ...] = (
    "limit: 0", "free_tier", "free tier", "billing details", "check your plan",
    "exceeded your current quota", "insufficient_quota", "billing_hard_limit_reached",
)


def _is_permanent_quota(detail: str) -> bool:
    low = (detail or "").lower()
    return any(marker.lower() in low for marker in _PERMANENT_QUOTA)


# Size on the wire. Google names sizes; the others take pixels. Kept as a translation rather
# than as a string the caller is trusted to get right per provider.
def _pixels(size: str) -> int:
    try:
        return int(str(size).lower().split("x")[0])
    except (ValueError, IndexError):
        return 1024


def _google_tier(size: str) -> str:
    px = _pixels(size)
    return "4K" if px >= 3072 else "2K" if px >= 1536 else "1K"


def _request_for(provider: ImageProvider, key: str, prompt: str,
                 reference_urls: list[str] | None, size: str) -> tuple[str, dict, bytes]:
    """The URL, headers and body this provider actually accepts.

    Verified against the live API for `google` on 2026-09-21: the auth header, the
    `:generateContent` suffix, the `contents` shape and `imageConfig` are what the endpoint
    answered 200 to for model listing and 429-with-a-quota-reason for generation, which is
    the response of an endpoint that understood the request. The other two dialects are
    written from their published documentation and are **unverified** -- no key for either
    exists yet, and the probe is what will prove them rather than this comment.
    """
    refs = list(reference_urls or [])
    if provider.dialect == "google":
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{provider.model}:generateContent")
        parts: list[dict] = [{"text": prompt}]
        for ref in refs:
            # Reference conditioning is what an identity lock is (#200). Google takes the
            # bytes inline, so a reference has to be readable from here.
            parts.append({"inlineData": {"mimeType": "image/png",
                                         "data": _inline_reference(ref)}})
        body = {
            "contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"],
                                 "imageConfig": {"imageSize": _google_tier(size)}},
        }
        return url, {"x-goog-api-key": key}, json.dumps(body).encode()

    if provider.dialect == "bfl":
        # Black Forest Labs is a submit-then-poll API: the POST returns a job, not a picture.
        # Unverified; `generate` polls because a synchronous read of this endpoint would
        # return a job id and `_first_image` would call it an answer without an image.
        px = _pixels(size)
        body = {"prompt": prompt, "width": px, "height": px,
                **({"image_prompt": refs[0]} if refs else {})}
        return provider.endpoint, {"x-key": key}, json.dumps(body).encode()

    # OpenAI-shaped, which Volcano Engine also speaks. Unverified.
    body = {"model": provider.model, "prompt": prompt, "size": size, "n": 1,
            **({"image": refs} if refs else {})}
    return provider.endpoint, {"authorization": f"Bearer {key}"}, json.dumps(body).encode()


def _inline_reference(reference: str) -> str:
    """A reference image as base64, from a local file. Never fetched from the network."""
    import base64
    from pathlib import Path

    path = Path(reference)
    if not path.is_file():
        raise ImagesRefused(
            f"{reference!r} is not a file on this disk. A reference image that resolves to "
            f"nothing would be sent as a conditioning signal that conditions on nothing, "
            f"and the identity lock would silently become a prompt")
    return base64.standard_b64encode(path.read_bytes()).decode()


def _parse_image(provider: ImageProvider, body: dict) -> tuple[str, str, str]:
    """(url, base64, mime) from one provider's answer. Exactly one of url/base64 is set."""
    if provider.dialect == "google":
        for candidate in body.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return "", inline["data"], inline.get("mimeType") or "image/png"
        return "", "", ""

    for container in (body.get("data"), body.get("images"), body.get("output"),
                      body.get("result")):
        for item in container or []:
            if isinstance(item, str) and item.startswith("http"):
                return item, "", ""
            if isinstance(item, dict):
                if item.get("url"):
                    return str(item["url"]), "", ""
                if item.get("b64_json"):
                    return "", str(item["b64_json"]), "image/png"
    sample = body.get("result") if isinstance(body.get("result"), dict) else {}
    if sample.get("sample"):
        return str(sample["sample"]), "", ""
    return str(body.get("url") or ""), "", ""


def _post(url: str, headers: dict, payload: bytes, *, label: str,
          timeout: float) -> dict:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, data=payload, method="POST")
    request.add_header("content-type", "application/json")
    for name, value in headers.items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        if exc.code == 402 or (exc.code == 429 and _is_permanent_quota(detail)):
            raise QuotaUnavailable(
                f"{label} {exc.code}: {detail}. This is the account's balance or plan "
                f"rather than traffic or the brief, so it is neither retried nor recorded "
                f"as a content refusal. The answer is a top-up, not a new prompt") from exc
        if exc.code in (429, 500, 502, 503, 504):
            raise TransientError(f"{label} {exc.code}: {detail}") from exc
        # A content refusal is permanent and is a fact about the brief rather than the
        # wiring. It must surface as a refusal with the provider's words, not as an empty
        # gallery somebody later explains as a rendering bug.
        raise ImagesRefused(f"{label} {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise TransientError(f"{label} unreachable: {exc.reason}") from exc


def _get(url: str, headers: dict, *, label: str, timeout: float) -> dict:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, method="GET")
    for name, value in headers.items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise TransientError(f"{label} poll {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise TransientError(f"{label} poll unreachable: {exc.reason}") from exc


BFL_POLL_SECONDS = 2.0
BFL_POLL_ATTEMPTS = 60


def generate(prompt: str, *, reference_urls: list[str] | None = None,
             env: dict[str, str] | None = None, size: str = "1024x1024",
             provider_key: str | None = None, work_dir: str | None = None,
             timeout: float = 120.0) -> dict:
    """Ask one provider for one image. Raises rather than returning nothing.

    Returns `image_ref`: whatever the judge can be handed, which is a URL when the provider
    gives one and a path on this disk when it returns the bytes inline. Google returns
    inline base64 and never a URL, so a caller that only read `url` would treat every
    successful Google render as an answer with no picture in it.
    """
    import base64
    import tempfile
    from pathlib import Path

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

    url, headers, payload = _request_for(provider, key, prompt, reference_urls, size)
    started = time.time()
    body = _post(url, headers, payload, label=provider.key, timeout=timeout)

    if provider.dialect == "bfl" and body.get("polling_url"):
        # Submit-then-poll. A job id is not a picture, and returning one as though it were
        # is how a benchmark scores sixty identical acknowledgements.
        poll = str(body["polling_url"])
        for _ in range(BFL_POLL_ATTEMPTS):
            body = _get(poll, headers, label=provider.key, timeout=timeout)
            status = str(body.get("status") or "").lower()
            if status in ("ready", "succeeded", "complete", "completed"):
                break
            if status in ("error", "failed", "content_moderated",
                          "request_moderated"):
                raise ImagesRefused(f"{provider.key} returned {status}: "
                                    f"{json.dumps(body)[:300]}")
            time.sleep(BFL_POLL_SECONDS)
        else:
            raise TransientError(
                f"{provider.key} did not finish within "
                f"{int(BFL_POLL_ATTEMPTS * BFL_POLL_SECONDS)}s")

    image_url, b64, mime = _parse_image(provider, body)
    if not image_url and not b64:
        raise ImagesRefused(
            f"{provider.key} answered without an image. A 200 with no picture in it is what "
            f"a content refusal and a wrong payload shape both look like from here")

    # Every render is written to this disk, whether it arrived as bytes or as a link.
    #
    # The link case is the one that had to be learned. Black Forest Labs returns a presigned
    # URL that expires about ten minutes after it is issued -- measured 2026-09-21: issued
    # 01:47Z, `se=2026-09-21T01:57:00Z`. Passing that along works for a benchmark that
    # judges immediately and fails quietly everywhere else: a model whose thirty renders
    # take longer than the expiry loses its earliest images before they are scored, and the
    # canonical identity pack of #200 -- the frozen reference every future listing is
    # conditioned on -- cannot be a set of links that stop resolving over lunch. A reference
    # that expires is not a lock.
    root = Path(work_dir or tempfile.mkdtemp(prefix="generated-"))
    root.mkdir(parents=True, exist_ok=True)
    if b64:
        raw = base64.b64decode(b64)
    else:
        import urllib.request

        try:
            with urllib.request.urlopen(image_url, timeout=timeout) as response:
                raw = response.read()
                mime = mime or response.headers.get("content-type", "")
        except Exception as exc:  # noqa: BLE001 - a link that will not fetch is no image
            raise ImagesRefused(
                f"{provider.key} returned a link that could not be fetched: {exc}. A "
                f"presigned URL is only an image while it lasts") from exc

    suffix = ".jpg" if "jpeg" in mime else ".webp" if "webp" in mime else ".png"
    path = str(root / f"{provider.key}-{int(time.time() * 1000)}{suffix}")
    Path(path).write_bytes(raw)

    return {"provider": provider.key, "url": image_url, "path": path,
            "image_ref": path, "bytes": len(raw),
            # Reported rather than assumed: the first version defaulted this to image/png
            # and said so about a JPEG that BFL had plainly labelled.
            "mime": mime or "", "size": size,
            "cad": provider.cad_per_image,
            "latency_ms": round((time.time() - started) * 1000, 2)}


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
        "benchmark": image_bench.state(db),
        "workload": WORKLOAD,
        "estimate_per_candidate": {
            p.key: monthly_estimate_cad(p) for p in PROVIDERS if p.supports_lock},
        "never": ("image generation is not image understanding. The model that can look at a "
                  "photograph cannot make one, and substituting it is refused in code rather "
                  "than discouraged in a note"),
    }
