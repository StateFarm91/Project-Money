"""The Etsy publishing path (Master Plan sections 14, 26).

This is the last mile: the only place in the system that could put a product in front of a
customer. It is written now, deliberately, while it cannot do that -- no credentials exist in
this environment and the phase forbids it -- because the alternative is writing the code that
sends real listings to a real shop for the first time on the day it matters.

Three refusals sit in front of any request, checked in this order, because the order is the
argument:

1. **Phase.** SHADOW and STAGING may not publish, whatever else is true. This is checked
   first so that a misconfigured credential can never be the thing that stops us.
2. **Owner authority.** Publishing is a RED action in the authority matrix: it needs the
   owner's explicit grant, which is a separate fact from having a key.
3. **Credentials.** Read from the environment, never from the repository, and absent here.

What this module does *not* do is decide whether a listing is fit to publish. That is the
release chain's job and it has already happened by the time anything reaches here: the
certificate, Asset Truth, the policy gate and the thumbnail check are all upstream. This maps
a listing we already trust onto Etsy's shape, and refuses to send anything it cannot map.

The payload is shaped to Etsy's v3 draft-listing API as documented. The *limits* enforced
here -- 140-character title, 13 tags of 20 characters, 13 materials -- are the ones the
policy gate already enforces on our side, so a listing that reaches this point should never
fail them; the check is here anyway, because "should never" is not a guarantee and a
rejected listing at publish time is worse than a refusal now.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..core.resilience import PermanentError, TransientError, classify_http

# Etsy's own limits, as published. These are not our preferences.
TITLE_MAX = 140
TAGS_MAX = 13
TAG_CHARS_MAX = 20
MATERIALS_MAX = 13
DESCRIPTION_MAX = 102400

# A digital pattern is an instant download with unlimited stock. Quantity is a required
# field and Etsy's maximum is 999; for a file that is copied rather than consumed, any
# number is arbitrary, so the maximum is the least misleading choice.
DIGITAL_QUANTITY = 999

# "Patterns" under Craft Supplies & Tools. Recorded as a constant with its name so that a
# wrong taxonomy is a visible mistake rather than an unexplained integer.
TAXONOMY_PATTERNS = 66   # craft_supplies_and_tools.patterns

PHASES_THAT_MAY_PUBLISH = ("limited_production", "production")


class EtsyNotConfigured(PermanentError):
    """No credentials. Not an outage: there is nothing to connect to."""


class EtsyNotPermitted(PermanentError):
    """The phase or the owner's authority forbids publishing. Never retried."""


class EtsyRejected(PermanentError):
    """Etsy refused the listing. The payload is wrong and retrying sends the same payload."""


@dataclass(frozen=True)
class Credentials:
    """Read from the environment. Never stored in this repository (CLAUDE.md)."""

    api_key: str
    access_token: str
    shop_id: str
    shared_secret: str = ""

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> "Credentials | None":
        e = env if env is not None else os.environ
        key = e.get("ETSY_API_KEY", "").strip()
        token = e.get("ETSY_ACCESS_TOKEN", "").strip()
        shop = e.get("ETSY_SHOP_ID", "").strip()
        secret = e.get("ETSY_SHARED_SECRET", "").strip()
        if not (key and token and shop):
            return None
        return Credentials(api_key=key, access_token=token, shop_id=shop,
                           shared_secret=secret)

    def api_key_header(self) -> str:
        """Etsy v3 wants keystring and shared secret joined by a colon, not the keystring.

        This was wrong here until the owner caught it, and it is the kind of wrong that costs
        a diagnosis round rather than failing loudly: a keystring-only header is accepted as a
        header and refused as a credential, so the first real call returns 401 and every
        explanation for a 401 is plausible. Etsy's own words:

            "Every request to a v3 endpoint must include an `x-api-key` header containing
             your keystring and shared secret separated by a colon"

        A credential with no secret is still sent, because a placeholder here would hide a
        misconfiguration behind a value that looks deliberate. Etsy refuses it and says so.
        """
        return f"{self.api_key}:{self.shared_secret}" if self.shared_secret else self.api_key

    def headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key_header(),
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"}

    def __repr__(self) -> str:  # pragma: no cover - keeps secrets out of logs and tracebacks
        return (f"Credentials(shop_id={self.shop_id!r}, api_key=***, shared_secret=***, "
                f"access_token=***)")


@dataclass
class Response:
    status: int
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


class Transport(Protocol):
    """The seam. Tests pass a fake; production would pass an HTTP client.

    Deliberately narrow: this module cannot reach the network except through something a
    caller handed it, so a test cannot accidentally make a real request and neither can a
    misconfigured job.

    `file` carries the digital pattern's bytes, because Etsy's file upload is a multipart
    form rather than JSON. It is separated from `json` rather than smuggled inside it so
    that the one part of this client which cannot be verified without a live call is
    visible in the interface instead of hidden in a body.
    """

    def request(self, method: str, url: str, *, headers: dict[str, str],
                json: dict[str, Any] | None = None,
                file: tuple[str, bytes] | None = None) -> Response:
        ...


@dataclass
class ListingPayload:
    """What we would send, and nothing more."""

    title: str
    description: str
    price: float
    tags: list[str]
    materials: list[str]
    taxonomy_id: int = TAXONOMY_PATTERNS
    quantity: int = DIGITAL_QUANTITY
    who_made: str = "i_did"
    when_made: str = "made_to_order"
    is_supply: bool = True
    type: str = "download"
    state: str = "draft"

    def to_dict(self) -> dict[str, Any]:
        return {
            "quantity": self.quantity,
            "title": self.title,
            "description": self.description,
            "price": round(self.price, 2),
            "who_made": self.who_made,
            "when_made": self.when_made,
            "taxonomy_id": self.taxonomy_id,
            "is_supply": self.is_supply,
            "type": self.type,
            "state": self.state,
            "tags": list(self.tags),
            "materials": list(self.materials),
        }


def build_payload(*, title: str, description: str, price_cad: float, tags: list[str],
                  materials: list[str]) -> ListingPayload:
    """Map a listing we already trust onto Etsy's shape, refusing what cannot be mapped.

    Every refusal here is a limit Etsy enforces. Truncating silently would be worse than
    refusing: a title cut at 140 characters mid-word is a listing nobody would have approved,
    and it would go out under a certificate that described something else.
    """
    problems: list[str] = []
    if not title.strip():
        problems.append("no title")
    if len(title) > TITLE_MAX:
        problems.append(f"title is {len(title)} characters; Etsy allows {TITLE_MAX}")
    if not description.strip():
        problems.append("no description")
    if len(description) > DESCRIPTION_MAX:
        problems.append(f"description is {len(description)} characters")
    if price_cad <= 0:
        problems.append("price must be positive")
    if len(tags) > TAGS_MAX:
        problems.append(f"{len(tags)} tags; Etsy allows {TAGS_MAX}")
    over = [t for t in tags if len(t) > TAG_CHARS_MAX]
    if over:
        problems.append(f"tags over {TAG_CHARS_MAX} characters: {over}")
    if len(materials) > MATERIALS_MAX:
        problems.append(f"{len(materials)} materials; Etsy allows {MATERIALS_MAX}")

    # Duplicates are collapsed rather than refused, because they are not a mistake anybody
    # made: a CIR carries one material entry per colour, so a six-colour blanket in one yarn
    # arrives here as that yarn six times. Etsy would accept it and the listing would read as
    # careless, and above thirteen colours it would be refused for a reason that has nothing
    # to do with the thirteen-material limit's purpose. Order is preserved so the first-named
    # yarn stays first.
    deduplicated: list[str] = []
    for material in materials:
        if material not in deduplicated:
            deduplicated.append(material)

    payload = ListingPayload(title=title.strip(), description=description,
                             price=float(price_cad), tags=list(tags),
                             materials=deduplicated)

    # Etsy's character sets, from Etsy's own published API document. Additive: none of the
    # limits above is restated there, because a limit written in two places is a limit that
    # gets changed in one of them. This catches what length and count cannot -- a material
    # written "100% cotton", a title with two ampersands -- which is the class of failure
    # that is invisible until the first request is sent.
    from ..publish.listing_schema import check_payload

    problems.extend(check_payload(payload.to_dict()))

    if problems:
        raise EtsyRejected("this listing cannot be mapped to an Etsy listing: "
                           + "; ".join(problems))

    return payload


@dataclass
class PublishOutcome:
    """What actually happened, including the half-done case.

    `listing_id` with `file_uploaded` false is the dangerous state: a listing exists on Etsy
    with no file attached to it. It is reported as its own outcome rather than folded into
    success or failure, because the recovery is different -- the listing must be completed or
    deleted, not created again.
    """

    published: bool
    listing_id: str | None = None
    file_uploaded: bool = False
    state: str = "draft"
    problems: list[str] = field(default_factory=list)

    @property
    def needs_completion(self) -> bool:
        return self.listing_id is not None and not self.file_uploaded


class EtsyClient:
    """Talks to Etsy, or refuses to. Never decides whether a listing is fit to publish."""

    BASE = "https://openapi.etsy.com/v3/application"

    def __init__(self, transport: Transport, *, credentials: Credentials | None = None,
                 phase: str = "shadow", owner_authorised: bool = False) -> None:
        self.transport = transport
        self.credentials = credentials
        self.phase = (phase or "shadow").lower()
        self.owner_authorised = owner_authorised

    # ---- the three refusals, in order ------------------------------------

    def refusal(self) -> str | None:
        """Why this client may not publish, or None. Order matters: phase first."""
        if self.phase not in PHASES_THAT_MAY_PUBLISH:
            return (f"BRAMBLELOOP_PHASE={self.phase} does not permit publication. Shadow and "
                    f"staging hold the whole shop ready rather than open.")
        if not self.owner_authorised:
            return ("publishing is a RED action in the authority matrix and the owner has "
                    "not granted it. A credential is not a permission.")
        if self.credentials is None:
            return ("no Etsy credentials in this environment. ETSY_API_KEY, "
                    "ETSY_ACCESS_TOKEN and ETSY_SHOP_ID are read from the environment and "
                    "are never stored in this repository.")
        return None

    def _require_permission(self) -> Credentials:
        reason = self.refusal()
        if reason is not None:
            error = EtsyNotConfigured if "credentials" in reason else EtsyNotPermitted
            raise error(reason)
        assert self.credentials is not None
        return self.credentials

    # ---- requests --------------------------------------------------------

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None,
              file: tuple[str, bytes] | None = None) -> Response:
        creds = self._require_permission()
        headers = creds.headers()
        if file is not None:
            # The transport owns the multipart encoding; setting a JSON content type here
            # would be a lie about the body.
            headers.pop("Content-Type", None)
        response = self.transport.request(method, f"{self.BASE}{path}",
                                          headers=headers, json=body, file=file)
        if response.status >= 400:
            kind = classify_http(response.status)
            message = (f"Etsy returned {response.status} for {method} {path}: "
                       f"{response.body.get('error', response.body)}")
            if kind is TransientError:
                raise TransientError(message)
            raise EtsyRejected(message)
        return response

    def create_draft(self, payload: ListingPayload) -> str:
        """Create the listing as a draft. Draft, always: activation is a separate decision."""
        creds = self._require_permission()
        body = payload.to_dict()
        body["state"] = "draft"
        response = self._call("POST", f"/shops/{creds.shop_id}/listings", body)
        listing_id = response.body.get("listing_id")
        if not listing_id:
            raise EtsyRejected(f"Etsy accepted the request but returned no listing_id: "
                               f"{response.body}")
        return str(listing_id)

    def attach_file(self, listing_id: str, *, filename: str, data: bytes) -> bool:
        """Attach the pattern file to a draft listing.

        The digital file is what the customer buys. A listing without one is a product that
        takes money and delivers nothing, which is why the outcome distinguishes that state.

        Two honest caveats, both recorded rather than hidden. The multipart encoding is the
        one part of this client that cannot be verified without a live call, so the
        transport owns it and this method is a shape rather than a proof. And the bytes have
        to exist: artifact bytes in this system are not durable until object storage is
        provisioned, so a process that renders a PDF, restarts, and then tries to upload it
        has nothing to send -- which is the dependency the readiness report records against
        the owner's storage decision.
        """
        creds = self._require_permission()
        if not data:
            raise EtsyRejected(
                f"no bytes to upload for {filename}: the pattern file is not available to "
                f"this process. Artifact bytes are not durable without object storage, so "
                f"the file has to be re-rendered from the certified CIR before publishing.")
        response = self._call("POST",
                              f"/shops/{creds.shop_id}/listings/{listing_id}/files",
                              {"name": filename}, file=(filename, data))
        return bool(response.body.get("listing_file_id"))

    def publish(self, *, payload: ListingPayload, filename: str,
                data: bytes) -> PublishOutcome:
        """Create the draft and attach the file, reporting the half-done case honestly."""
        reason = self.refusal()
        if reason is not None:
            return PublishOutcome(published=False, problems=[reason])

        listing_id = self.create_draft(payload)
        try:
            uploaded = self.attach_file(listing_id, filename=filename, data=data)
        except (TransientError, EtsyRejected) as e:
            return PublishOutcome(published=False, listing_id=listing_id,
                                  file_uploaded=False,
                                  problems=[f"listing {listing_id} exists on Etsy with no "
                                            f"file attached: {e}"])
        return PublishOutcome(published=uploaded, listing_id=listing_id,
                              file_uploaded=uploaded,
                              problems=[] if uploaded else
                              [f"listing {listing_id} exists with no file attached"])
