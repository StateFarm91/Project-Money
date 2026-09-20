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

    @property
    def cad_per_image(self) -> float:
        return round(self.usd_per_image * USD_TO_CAD, 6)

    def to_dict(self) -> dict:
        return {"provider": self.key, "what": self.what,
                "usd_per_image": self.usd_per_image,
                "cad_per_image": self.cad_per_image,
                "supports_identity_lock": self.supports_lock,
                "reference_images": self.reference_images,
                "note": self.note, "price_basis": "assumed, read 2026-09-20"}


PROVIDERS: tuple[ImageProvider, ...] = (
    ImageProvider(
        "flux-2-pro", "Black Forest Labs FLUX 2 Pro",
        "https://api.bfl.ai/v1/flux-2-pro", 0.02, True, 8,
        "cheapest of the candidates that conditions on reference images, which is what an "
        "identity lock actually is. Eight references is more than a canonical face pack "
        "needs"),
    ImageProvider(
        "gpt-image-2", "OpenAI GPT Image 2 at 1024px",
        "https://api.openai.com/v1/images/generations", 0.03, True, 16,
        "strongest prompt adherence of the three and the most reference images; half again "
        "the price of FLUX per image, which matters at catalogue scale and not at pack "
        "scale"),
    ImageProvider(
        "imagen-4-standard", "Google Imagen 4 Standard",
        "https://generativelanguage.googleapis.com/v1beta/models", 0.04, False, 0,
        "best photorealism of the three and no reference conditioning on this tier, so it "
        "cannot hold an identity across a season -- listed to be ruled out on the "
        "requirement rather than on taste"),
)

BY_KEY: dict[str, ImageProvider] = {p.key: p for p in PROVIDERS}

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
    """Whether a provider and a key are both named. Deliberately not `usable`."""
    try:
        return bool(configured_provider(env)) and bool(api_key(env))
    except ImagesRefused:
        return False


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
             timeout: float = 120.0) -> dict:
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
    provider = configured_provider(e)
    key = api_key(e)
    if provider is None or not key:
        raise ImagesNotConfigured(
            f"set {PROVIDER_VAR} to one of {sorted(BY_KEY)} and {KEY_VAR} to that "
            f"provider's key. Neither exists in this environment, which is the state the "
            f"gate describes rather than a failure to retry")

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
            with db.session() as s:
                s.add(CostEntry(agent="gateway", kind=routing.COST_KIND,
                                amount_cad=float(got.get("cad") or 0.0), job_id=job_id,
                                detail={"purpose": PROBE_ACTION, "provider": provider.key,
                                        "price_basis": "assumed"}))

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

    recommended = BY_KEY["flux-2-pro"]
    return {
        "configured": configured(env),
        "provider": provider.key if provider else None,
        "provider_error": provider_error,
        "key_present": bool(api_key(env)),
        "last_probe": last,
        "usable": bool(last and last.get("ok")),
        "candidates": [p.to_dict() for p in PROVIDERS],
        "recommended": recommended.key,
        "why_recommended": (
            "an identity lock is reference conditioning, not a better prompt. Two of the "
            "three candidates support it; this is the cheaper of those two, and the third is "
            "ruled out on the requirement rather than on output quality"),
        "workload": WORKLOAD,
        "estimate": monthly_estimate_cad(recommended),
        "never": ("image generation is not image understanding. The model that can look at a "
                  "photograph cannot make one, and substituting it is refused in code rather "
                  "than discouraged in a note"),
    }
