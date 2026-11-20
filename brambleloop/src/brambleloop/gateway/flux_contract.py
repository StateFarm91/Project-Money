"""ENG-VIS-FLUX: the FLUX 3 Image contract, as Black Forest Labs documents it, held as data.

Every fact the gateway relies on about the BFL API is written down here once, with the URL it
was read from and the UTC date it was read (`SOURCES`). Nothing in this module makes a request
-- it imports no HTTP client (pinned by `test_cert_spend_hosts`) -- and nothing in it is
inferred: a field, a status or a limit that is not in a cited document is not here, so the
request builder cannot send it.

Read 2026-11-20 (UTC) from the official sources, all reachable from this build:

* the machine-readable schema `https://api.bfl.ai/openapi.json` (`Flux3ImageInputs`,
  `AsyncResponse`, `ResultResponse`, `SettledCostResultResponse`, `StatusResponse`, security
  scheme `APIKeyHeader` = header `x-key`);
* the API reference page for `POST /v1/flux-3-image`;
* the pricing page (its embedded rate card: credits per image by tier, 1 credit = US$0.01);
* the integration guide (polling_url, delivery URLs, 24 concurrent calls);
* the errors page (HTTP codes, `Request Moderated` / `Content Moderated`, FLUX 3 Image
  `safety_tolerance` range 0-4);
* the technical-parameters guide (tiers, exact width/height bounds, billing of exact sizes,
  no negative prompt).

**What the current FLUX offering is.** "FLUX 3" is the current family (FLUX 3 Image, FLUX 3
Image Klein, FLUX 3 Video). Its multi-reference image-conditioning endpoint is FLUX 3 Image
itself: `images` carries one to ten references (URL or base64) and the prompt refers to each by
position. FLUX.1 Kontext is the previous generation and the docs recommend FLUX.2 or later for
new work; this build conditions on FLUX 3 Image only for listing frames.

**What it does not offer, said plainly.** `Flux3ImageInputs` is `additionalProperties: false`
and has no `seed`, no `negative_prompt`, no `prompt_upsampling`, no `output_format` and no
`webhook_url`. So a FLUX 3 Image request cannot be made deterministic by a seed: the seed is
recorded when (and only when) the provider's result reports one, and is otherwise UNKNOWN. A
seed this build invented and sent would be refused with 422.
"""
from __future__ import annotations

import math

CONTRACT_VERSION = "bfl-flux3-image-contract/2026-11-20"
ACCESSED = "2026-11-20"

SOURCES: dict[str, dict] = {
    "openapi": {"url": "https://api.bfl.ai/openapi.json", "accessed": ACCESSED,
                "facts": "Flux3ImageInputs, AsyncResponse, ResultResponse, "
                         "SettledCostResultResponse, StatusResponse, APIKeyHeader x-key, "
                         "GET /v1/get_result?id=, GET /v1/credits"},
    "api_reference": {"url": "https://docs.bfl.ai/api-reference/utility/"
                             "generate-an-image-with-flux-3",
                      "accessed": ACCESSED,
                      "facts": "POST /v1/flux-3-image; text-to-image, edit, multi-reference "
                               "examples; same schema as openapi"},
    "image_overview": {"url": "https://docs.bfl.ai/flux_3/flux3_image_overview",
                       "accessed": ACCESSED,
                       "facts": "combine up to ten references; grounding searches the web by "
                                "default, false turns it off"},
    "quickstart": {"url": "https://docs.bfl.ai/flux_3/flux3_image_generate",
                   "accessed": ACCESSED,
                   "facts": "poll polling_url until Ready; in-progress Pending/Reasoning/"
                            "Generating; result.sample signed URL expires after 1 hour; never "
                            "send x-key to it"},
    "pricing": {"url": "https://docs.bfl.ai/quick_start/pricing", "accessed": ACCESSED,
                "facts": "1 credit = US$0.01; /v1/flux-3-image tier768 4.1, tier1k 4.8, "
                         "tier1_5k 7, tier2k 10, tier4k 60.7 credits; exact sizes billed at "
                         "the smallest tier with at least as many pixels; the submit response "
                         "includes the cost"},
    "technical": {"url": "https://docs.bfl.ai/guides/prompting_unified_technical",
                  "accessed": ACCESSED,
                  "facts": "tiers 768sq/1k/1.5k/2k/4k/match_input; width/height 256-6256 px, "
                           "up to 16.8 MP, 4 MP with reference images; no negative_prompt or "
                           "prompt_upsampling field"},
    "integration": {"url": "https://docs.bfl.ai/api_integration/integration_guidelines",
                    "accessed": ACCESSED,
                    "facts": "must use the returned polling_url; delivery URLs expire after 10 "
                             "minutes and are not for direct serving; at most 24 concurrent "
                             "calls; exponential backoff on 429"},
    "errors": {"url": "https://docs.bfl.ai/api_integration/errors", "accessed": ACCESSED,
               "facts": "400/402/403/422/429/500/503; Request Moderated before processing, "
                        "Content Moderated after, result null with details.Moderation Reasons; "
                        "FLUX 3 Image safety_tolerance 0-4, default 2, above max is 422"},
}

# ---- the request -------------------------------------------------------------------------

HOST = "https://api.bfl.ai"
ENDPOINT = f"{HOST}/v1/flux-3-image"
AUTH_HEADER = "x-key"
MODEL = "flux-3-image"
# `Flux3ImageInputs.properties` exactly (openapi). additionalProperties: false.
REQUEST_FIELDS = frozenset({"user", "prompt", "images", "aspect_ratio", "resolution", "width",
                            "height", "safety_tolerance", "grounding", "version"})
REQUIRED_FIELDS = frozenset({"prompt"})
# Fields people reach for that FLUX 3 Image does not have; named so a refusal can say so.
ABSENT_FIELDS = frozenset({"seed", "negative_prompt", "prompt_upsampling", "output_format",
                           "webhook_url", "input_image", "image_prompt", "steps", "guidance"})
ASPECT_RATIOS = ("21:9", "2:1", "16:9", "3:2", "7:5", "4:3", "5:4", "1:1", "4:5", "3:4",
                 "5:7", "2:3", "9:16", "1:2", "9:21")
RESOLUTIONS = ("768sq", "1k", "1.5k", "2k", "4k", "match_input")
MAX_REFERENCES = 10
EXACT_SIDE_PX = (256, 6256)
EXACT_MAX_PIXELS = 16_822_272
EXACT_MAX_PIXELS_WITH_REFERENCES = 4_194_304
# The schema allows 0-7 in general; the errors page fixes FLUX 3 Image at 0-4 (default 2), and
# a value above the endpoint's maximum is a 422. The tighter, endpoint-specific bound wins.
SAFETY_TOLERANCE_RANGE = (0, 4)
SAFETY_TOLERANCE_DEFAULT = 2
VERSION_VALUES = ("latest",)

# ---- responses ---------------------------------------------------------------------------

SUBMIT_REQUIRED = ("id", "polling_url")                 # AsyncResponse.required
SUBMIT_OPTIONAL = ("cost", "input_mp", "output_mp")     # cost in credits
RESULT_REQUIRED = ("id", "status")                      # ResultResponse.required
STATUSES = ("Task not found", "Pending", "Reasoning", "Generating", "Request Moderated",
            "Content Moderated", "No Card Generated", "Ready", "Error")
IN_PROGRESS = ("Pending", "Reasoning", "Generating")
READY = "Ready"
TERMINAL_FAILURES = ("Task not found", "Request Moderated", "Content Moderated",
                     "No Card Generated", "Error")
SAMPLE_URL_EXPIRY_S = 600      # the stricter of the two documented figures (10 min vs 1 h)
MAX_CONCURRENT_REQUESTS = 24

# ---- price -------------------------------------------------------------------------------

USD_PER_CREDIT = 0.01
CREDITS_PER_IMAGE = {"768sq": 4.1, "1k": 4.8, "1.5k": 7.0, "2k": 10.0, "4k": 60.7}


class ContractViolation(ValueError):
    """A request or response that does not match the documented contract. `.code` names it."""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code


def usd_per_image(tier: str) -> float:
    if tier not in CREDITS_PER_IMAGE:
        raise ContractViolation("unpriced_tier", f"{tier!r} has no published FLUX 3 price")
    return round(CREDITS_PER_IMAGE[tier] * USD_PER_CREDIT, 6)


def validate_request(body: dict) -> dict:
    """Refuse any FLUX 3 Image body the documented schema would not accept. Returns it."""
    if not isinstance(body, dict):
        raise ContractViolation("not_an_object", "a FLUX 3 Image request is a JSON object")
    absent = sorted(set(body) & ABSENT_FIELDS)
    if absent:
        raise ContractViolation("field_not_in_contract",
                                f"FLUX 3 Image has no {absent} field (openapi Flux3ImageInputs, "
                                f"additionalProperties false); it would be refused with 422")
    unknown = sorted(set(body) - REQUEST_FIELDS)
    if unknown:
        raise ContractViolation("unknown_field", f"not in Flux3ImageInputs: {unknown}")
    if not isinstance(body.get("prompt"), str) or not body["prompt"].strip():
        raise ContractViolation("prompt_required", "prompt is required and non-empty")
    images = body.get("images")
    refs = [images] if isinstance(images, str) else list(images or [])
    if images is not None and not (1 <= len(refs) <= MAX_REFERENCES):
        raise ContractViolation("reference_count",
                                f"images carries one to {MAX_REFERENCES}; got {len(refs)}")
    if any(not isinstance(r, str) or not r for r in refs):
        raise ContractViolation("reference_type", "each reference is a URL or base64 string")
    ar = body.get("aspect_ratio")
    if ar is not None and ar not in ASPECT_RATIOS + ("auto",):
        raise ContractViolation("aspect_ratio", f"{ar!r} is not a documented aspect ratio")
    res = body.get("resolution")
    if res is not None and res not in RESOLUTIONS:
        raise ContractViolation("resolution", f"{res!r} is not a documented resolution")
    if res == "match_input" and not refs:
        raise ContractViolation("resolution", "match_input applies to edits only")
    w, h = body.get("width"), body.get("height")
    if (w is None) != (h is None):
        raise ContractViolation("exact_size", "width and height are set together")
    if w is not None:
        lo, hi = EXACT_SIDE_PX
        if not all(isinstance(v, int) and lo <= v <= hi for v in (w, h)):
            raise ContractViolation("exact_size", f"width/height are integers in [{lo}, {hi}]")
        cap = EXACT_MAX_PIXELS_WITH_REFERENCES if refs else EXACT_MAX_PIXELS
        if w * h > cap:
            raise ContractViolation("exact_size", f"{w}x{h} is over the {cap}-pixel bound"
                                                  f"{' with reference images' if refs else ''}")
    st = body.get("safety_tolerance")
    if st is not None:
        lo, hi = SAFETY_TOLERANCE_RANGE
        if isinstance(st, bool) or not isinstance(st, int) or not lo <= st <= hi:
            raise ContractViolation("safety_tolerance",
                                    f"FLUX 3 Image accepts safety_tolerance {lo}-{hi}; got {st!r}")
    if "grounding" in body and not isinstance(body["grounding"], bool):
        raise ContractViolation("grounding", "grounding is a boolean")
    if "version" in body and body["version"] not in VERSION_VALUES:
        raise ContractViolation("version", f"version is one of {VERSION_VALUES}")
    return body


def validate_submit(body: dict) -> dict:
    """An `AsyncResponse`: id and polling_url present; cost, when present, a finite number."""
    if not isinstance(body, dict):
        raise ContractViolation("submit_shape", "the submit response is not an object")
    missing = [k for k in SUBMIT_REQUIRED if not body.get(k)]
    if missing:
        raise ContractViolation("submit_shape", f"AsyncResponse is missing {missing}")
    if not str(body["polling_url"]).startswith("https://"):
        raise ContractViolation("submit_shape", "polling_url is not an https URL")
    for k in SUBMIT_OPTIONAL:
        v = body.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))
                              or not math.isfinite(float(v)) or float(v) < 0):
            raise ContractViolation("submit_shape", f"{k} is not a finite non-negative number")
    return body


def classify_result(body: dict) -> str:
    """`in_progress`, `ready` or `terminal`, from the documented `StatusResponse` vocabulary.
    A status the contract does not name is `terminal` (never a reason to keep polling)."""
    if not isinstance(body, dict):
        raise ContractViolation("result_shape", "the result response is not an object")
    status = body.get("status")
    if status in IN_PROGRESS:
        return "in_progress"
    if status == READY:
        sample = (body.get("result") or {}).get("sample") if isinstance(
            body.get("result"), dict) else None
        if not sample or not str(sample).startswith("https://"):
            raise ContractViolation("result_shape", "Ready without an https result.sample")
        return "ready"
    return "terminal"


def moderation_reasons(body: dict) -> list[str]:
    """The categories a moderated result names (`details["Moderation Reasons"]`), if any."""
    details = body.get("details") if isinstance(body, dict) else None
    reasons = (details or {}).get("Moderation Reasons") if isinstance(details, dict) else None
    return [str(r) for r in reasons] if isinstance(reasons, list) else []


def summary() -> dict:
    """The audited contract, for reports and the owner decisions document."""
    return {"version": CONTRACT_VERSION, "endpoint": ENDPOINT, "auth_header": AUTH_HEADER,
            "model": MODEL, "request_fields": sorted(REQUEST_FIELDS),
            "absent_fields": sorted(ABSENT_FIELDS), "max_references": MAX_REFERENCES,
            "resolutions": list(RESOLUTIONS), "aspect_ratios": list(ASPECT_RATIOS),
            "safety_tolerance_range": list(SAFETY_TOLERANCE_RANGE),
            "seed_supported": False, "statuses": list(STATUSES),
            "credits_per_image": dict(CREDITS_PER_IMAGE), "usd_per_credit": USD_PER_CREDIT,
            "sources": SOURCES}
