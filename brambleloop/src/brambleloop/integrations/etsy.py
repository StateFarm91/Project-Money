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

## 2026-09-25: the transport gap, and what those three refusals were guarding

An audit found that this client could create a draft and could not finish one. Three things
were missing and two were launch blockers:

- `uploadListingImage` was called nowhere in `src/`. Etsy will not activate a listing with no
  image, so **every draft this system could create was permanently unactivatable** -- the shop
  would have opened with zero live listings, and every upstream gate would have passed.
- `updateListing` was called nowhere, so nothing could change a draft or publish one.
- Requests were serialised as JSON. Etsy lists `application/x-www-form-urlencoded` as the
  only media type for both write operations.

All three are now built, and the single publish-or-refuse gate has become three authorities
(`Authority`): READ creates nothing, DRAFT_WRITE touches only objects no buyer can see and no
fee attaches to, and ACTIVATE -- which publishes and charges Etsy's listing fee -- needs the
phase, the owner's grant *and* a Launch-0 authorisation passed to the call itself.

**What has been exercised, as of 2026-09-25.** Reaching Etsy: yes, `http.probe_live()` and
Etsy answers. Every write: no. There are no Etsy credentials in this environment, so the whole
write path is exercised against a local server built from Etsy's document
(`tests/fake_etsy.py`) and confirmed by nothing Etsy has said. `integrations/etsy_probe.py`
is the sequence that would confirm it, and `research/ETSY_TRANSPORT.md` records exactly which
claims are still only readings.
"""
from __future__ import annotations

import logging
import os
import urllib.parse
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from ..core.resilience import PermanentError, TransientError, classify_http

log = logging.getLogger("brambleloop.etsy")

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


def _persisting_on_refresh(db: Any, env: dict[str, str], current_token: str | None = None):
    """The `TokenProvider.on_refresh` hook, wired to the sealed credential store.

    Etsy spends the refresh token on every refresh and issues a new one, so this callback is
    not bookkeeping: it is the difference between a system that keeps working and one that
    needs the owner's browser after the next container replacement.

    **Compare-and-set, and what happens when it loses.** The closure remembers which token it
    believes is stored and names it on every write, so two workers refreshing at the same
    moment cannot leave the row holding a token Etsy has already invalidated. The loser does
    not raise: it is holding a brand-new access token that works for the next hour, and
    turning a successful refresh into a failed Etsy call would be a worse answer than a log
    line. What it does instead is stop claiming to own the stored value -- the next write
    from this process adopts whatever is there rather than fighting over it.

    Nothing in this function logs a token. The fingerprints are the same eight hex characters
    every other report in this system uses for the same value.
    """
    from ..core import oauth_store, sealed

    state = {"expected": sealed.fingerprint(current_token) if current_token else None}

    def on_refresh(tokens) -> None:
        try:
            result = oauth_store.save_refresh_token(
                db, tokens.refresh_token, scopes=" ".join(tokens.scopes),
                source="refresh grant", expected_fingerprint=state["expected"], env=env)
            state["expected"] = sealed.fingerprint(tokens.refresh_token)
            log.info("etsy refresh token rotated to %s (rotation %s)",
                     result["token_fingerprint"], result["rotations"])
        except oauth_store.CredentialConflict:
            state["expected"] = None
            log.warning(
                "etsy refresh token was rotated by another worker first; this process kept "
                "its access token and did not overwrite the stored credential")
        except Exception as exc:  # noqa: BLE001 - a storage failure must not kill the call
            state["expected"] = None
            log.warning("etsy refresh token could not be stored (%s); it will have to be "
                        "granted again after the next restart", type(exc).__name__)

    return on_refresh


@dataclass(frozen=True)
class Credentials:
    """Read from the environment. Never stored in this repository (CLAUDE.md).

    `token_provider`, when present, owns the access token: it refreshes it when it is about
    to expire and refuses an operation whose scope Etsy did not grant. `access_token` then
    becomes a fallback for the case where a human pasted one and no app is registered. A
    static token is valid for one hour (Etsy's own figure), so the fallback is a way to fail
    on day two rather than a way to run.
    """

    api_key: str
    access_token: str
    shop_id: str
    shared_secret: str = ""
    token_provider: Any = None

    @staticmethod
    def from_env(env: dict[str, str] | None = None,
                 transport: Any = None, db: Any = None) -> "Credentials | None":
        """Build credentials, preferring a refreshing token provider over a static token.

        Accepts `ETSY_KEYSTRING` as well as `ETSY_API_KEY` because two documents in this
        repository named the same value differently, and a name mismatch that presents as
        "no credentials" is the most expensive kind of typo.

        **`db` is what makes the refresh survive a restart.** Without it this function built a
        `TokenProvider` with no `on_refresh` callback, which meant the rotated refresh token
        Etsy returns on every refresh was read, used for an hour and then dropped: the system
        worked until the container was replaced -- several times an hour on this platform --
        and then presented `invalid_grant`, which looks exactly like a revoked app. With it,
        the stored credential is preferred over `ETSY_REFRESH_TOKEN` and every rotation is
        written back, sealed, under compare-and-set.

        `ETSY_REFRESH_TOKEN` is still read, and is still how a token first arrives in a
        deployment that has never completed the callback flow. The database wins when both
        exist, because the environment variable is a snapshot of a chain that has since moved
        on: an env var that was correct when it was pasted is a spent token an hour later.
        """
        e = env if env is not None else os.environ
        key = (e.get("ETSY_KEYSTRING") or e.get("ETSY_API_KEY") or "").strip()
        token = (e.get("ETSY_ACCESS_TOKEN") or "").strip()
        shop = (e.get("ETSY_SHOP_ID") or "").strip()
        secret = (e.get("ETSY_SHARED_SECRET") or "").strip()
        refresh_token = (e.get("ETSY_REFRESH_TOKEN") or "").strip()

        stored_token = None
        on_refresh = None
        if db is not None:
            from ..core import oauth_store

            stored_token = oauth_store.load_refresh_token(db, env=e)
            # Only a token that came *from the store* may be named in a compare-and-set. One
            # read out of the environment has no claim on the row, so its first write adopts
            # whatever is there instead of asserting what it is replacing.
            on_refresh = _persisting_on_refresh(db, e, current_token=stored_token)

        provider = None
        if key and (refresh_token or stored_token) and transport is not None:
            from .etsy_oauth import TokenProvider, TokenSet

            provider = TokenProvider.from_env(transport, e, on_refresh=on_refresh)
            if provider is not None and stored_token:
                current = provider.tokens
                # Expiry 0.0 means "treat as already expired", which is what a stored refresh
                # token with no live access token has to mean: one refresh at start-up rather
                # than a call with a token of unknown age.
                provider.tokens = TokenSet(
                    access_token=current.access_token if current else token,
                    refresh_token=stored_token,
                    expires_at=current.expires_at if current else 0.0,
                    scopes=current.scopes if current else ())

        if not (key and shop and (token or provider is not None)):
            return None
        return Credentials(api_key=key, access_token=token, shop_id=shop,
                           shared_secret=secret, token_provider=provider)

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

    def headers(self, *, operation: str | None = None) -> dict[str, str]:
        """The two credential headers, and no Content-Type.

        Content-Type used to be set here, to `application/json`, for every request this
        client made -- including the two write endpoints for which Etsy lists
        `application/x-www-form-urlencoded` as the only accepted media type. A credential
        object is the wrong place to decide a body format: it cannot know which endpoint is
        being called. The transport sets it from the body channel it was actually given, so
        the header and the bytes can no longer disagree.

        `operation` names the Etsy operation, so that when a `TokenProvider` is supplying the
        token it can refuse a call whose scope Etsy never granted -- before the request,
        rather than reading it back as a 403.
        """
        token = self.access_token
        if self.token_provider is not None:
            token = self.token_provider.token(operation=operation)
        return {"x-api-key": self.api_key_header(),
                "Authorization": f"Bearer {token}"}

    def __repr__(self) -> str:  # pragma: no cover - keeps secrets out of logs and tracebacks
        # The shop id stays: it is not a secret -- Etsy puts it in public listing URLs -- and
        # it is the one field that identifies which account a failure came from. Whether it
        # belongs in this repository is a different question, and the answer there is no.
        return (f"Credentials(shop_id={self.shop_id!r}, api_key=***, shared_secret=***, "
                f"access_token=***, token_provider="
                f"{'yes' if self.token_provider else 'no'})")


@dataclass
class Response:
    status: int
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FilePart:
    """One binary part of a multipart body, with the field name Etsy asks for.

    `field` is data rather than a constant because Etsy's two upload endpoints disagree:
    `uploadListingImage` reads the binary from a part named `image`, `uploadListingFile` from
    one named `file`. Sending `file` to the images endpoint -- which is what this client did
    before, because its transport hard-coded the name -- is a request Etsy accepts the shape
    of and finds no image in.
    """

    field: str
    filename: str
    data: bytes
    content_type: str = "application/octet-stream"


class Transport(Protocol):
    """The seam. Tests pass a fake; production passes `http.UrllibTransport`.

    Deliberately narrow: this module cannot reach the network except through something a
    caller handed it, so a test cannot accidentally make a real request and neither can a
    misconfigured job.

    Three body channels, because Etsy uses three media types and which one is correct is a
    property of the endpoint (`form` for createDraftListing and updateListing, `multipart`
    for the two uploads, `json` for updateListingInventory and nothing else this client
    sends). They are separate parameters rather than one `body` so that a call site states
    the encoding it means and the transport never has to guess. A multipart request carries
    its text fields in `form` alongside `multipart`: that is one body, not two.
    """

    def request(self, method: str, url: str, *, headers: dict[str, str],
                json: dict[str, Any] | None = None,
                form: dict[str, Any] | None = None,
                multipart: FilePart | None = None) -> Response:
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
    images_uploaded: int = 0

    @property
    def needs_completion(self) -> bool:
        return self.listing_id is not None and not self.file_uploaded

    @property
    def activatable(self) -> bool:
        """Whether this draft could be published at all, which is a separate question.

        Etsy refuses to activate a listing with no image. Before 2026-09-25 nothing in this
        system uploaded one, so every outcome that reported `published=True` described a draft
        that could never go live -- and nothing said so. This property is the difference
        between "the request succeeded" and "there is a listing here that could become a
        product".
        """
        return (self.listing_id is not None and self.file_uploaded
                and self.images_uploaded > 0)


# ---------------------------------------------------------------------------
# What each operation may do, and who may authorise it


class Authority(Enum):
    """The three different things a request to Etsy can be, and they are not one gate.

    The client used to have a single refusal covering everything, which was correct while it
    could only do one thing -- publish. It is wrong now, in both directions:

    - It was too strict to be useful. A shop read, a draft, an image upload and a draft
      deletion are invisible to every buyer and cost CA$0, so refusing them in SHADOW means
      the first time this code runs against Etsy is the day the shop opens. That is precisely
      the risk this whole module was written to avoid.
    - It was too loose where it mattered. `create_draft` and activation sat behind the same
      permission, so any authority that allowed a draft allowed publishing.

    So: READ creates nothing. DRAFT_WRITE creates and changes things no buyer can see and no
    fee attaches to. ACTIVATE puts a product in front of customers and **costs money on
    Etsy's side**, and it is the only one that needs the launch authorisation.
    """

    READ = "read"
    DRAFT_WRITE = "draft_write"
    ACTIVATE = "activate"


# Etsy charges the listing fee when a listing is *published*, not when a draft is created.
# Kept as a constant with its currency so the refusal below can quote the number it is
# protecting rather than say "a fee".
LISTING_FEE_USD = 0.20

# The fields `updateListing` accepts, from the operation's own request schema. A field not in
# this set is refused here rather than sent: a listing that silently keeps its old value is
# worse than a 400, because read-back verification would then report a mismatch whose real
# cause is our own request.
UPDATE_WRITABLE = frozenset({
    "image_ids", "title", "description", "materials", "should_auto_renew",
    "shipping_profile_id", "return_policy_id", "shop_section_id", "item_weight",
    "item_length", "item_width", "item_height", "item_weight_unit", "item_dimensions_unit",
    "is_taxable", "taxonomy_id", "tags", "who_made", "when_made", "featured_rank", "state",
    "is_supply", "production_partner_ids", "type",
})

# `price` is conspicuously absent from that set, and it is the field most likely to be
# reached for. Etsy moves price to the inventory endpoint -- `updateListingInventory`, PUT,
# and the one Etsy write this company touches that really is `application/json`.
PRICE_IS_ELSEWHERE = (
    "price is not an updateListing field. Etsy's update schema has no price property; the "
    "price of an offering lives in the listing's inventory and is written with PUT "
    "/v3/application/listings/{listing_id}/inventory (application/json, not form-encoded). "
    "Sending price here would be accepted as an unknown field and change nothing, which is "
    "the worst of the three possible outcomes."
)

# How an array becomes form-encoded. Etsy's document says of `tags`: "A comma-separated list
# of tag strings for the listing" -- while the OpenAPI default for an un-encoded form array
# would be repeated keys (`tags=a&tags=b`). Both readings come from Etsy's own document. This
# system sends the comma form, which is the reading the sentence supports and the decision
# `publish/listing_schema.form_encoded` already made. `ARRAY_ENCODING` exists so the decision
# has a name, and so that the day a real 400 settles it, one constant moves.
#
# **It is the only thing that moves.** `form_fields` below reads it, `http.form_body` renders
# a list as repeated keys, and `etsy_probe`'s failure taxonomy names this constant as the
# single change that follows a tags rejection. Both settings are exercised against
# `tests/fake_etsy.py`, including the case that makes this dangerous: a comma-joined value
# Etsy accepts with a 201 and stores as **one tag containing a comma**. That outcome is not
# an error anywhere on the wire; only the read-back comparison sees it.
ARRAY_ENCODING = "comma"
ARRAY_ENCODINGS = ("comma", "repeat")

# Etsy's alt_text limit, from the `uploadListingImage` schema: "Alt text for the listing
# image. Max length 500 characters."
ALT_TEXT_MAX = 500

# Content types for the formats a listing image can be. Explicit rather than guessed from
# `mimetypes`, whose answer depends on the host's /etc/mime.types.
IMAGE_CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                       ".gif": "image/gif", ".webp": "image/webp"}


def form_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten a payload for a form-encoded Etsy write, honouring `ARRAY_ENCODING`.

    With `"comma"` this delegates to `publish.listing_schema.form_encoded`, which is where the
    array-encoding decision is written down, so the shape this client sends and the shape the
    schema module documents cannot drift apart.

    With `"repeat"` a list survives as a list and `http.form_body` emits repeated keys. The
    scalar fields are still rendered by `form_encoded`, one key at a time, so the boolean and
    number rendering cannot differ between the two settings -- if it could, flipping the
    constant would change more than the arrays and the experiment would prove nothing.
    """
    from ..publish.listing_schema import form_encoded

    if ARRAY_ENCODING not in ARRAY_ENCODINGS:
        raise EtsyRejected(
            f"ARRAY_ENCODING is {ARRAY_ENCODING!r}; Etsy's form arrays are one of "
            f"{list(ARRAY_ENCODINGS)}. An unrecognised value would silently fall back to a "
            f"rendering nobody chose.")
    if ARRAY_ENCODING == "comma":
        return dict(form_encoded(payload))
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, (list, tuple)):
            out[key] = [str(item) for item in value]
        else:
            out[key] = form_encoded({key: value})[key]
    return out


class EtsyClient:
    """Talks to Etsy, or refuses to. Never decides whether a listing is fit to publish."""

    BASE = "https://openapi.etsy.com/v3/application"

    def __init__(self, transport: Transport, *, credentials: Credentials | None = None,
                 phase: str = "shadow", owner_authorised: bool = False,
                 shadow_writes_authorised: bool = False,
                 base: str | None = None) -> None:
        # `base` exists so a test can point this client at a local server that speaks Etsy's
        # documented contract. It defaults to Etsy, and nothing in `src/` overrides it: a
        # client built normally can only reach openapi.etsy.com.
        if base:
            self.BASE = base
        self.transport = transport
        self.credentials = credentials
        self.phase = (phase or "shadow").lower()
        self.owner_authorised = owner_authorised
        # Draft-only writes in a non-publishing phase: the narrow permission that lets this
        # code be exercised against the real shop without a listing ever becoming visible.
        # A constructor argument rather than an environment read inside the client, so a call
        # site has to state it and a test cannot acquire it by accident.
        self.shadow_writes_authorised = shadow_writes_authorised
        self.calls: list[dict[str, Any]] = []

    # ---- the refusals ----------------------------------------------------

    def refusal(self) -> str | None:
        """Why this client may not publish, or None. Order matters: phase first.

        Unchanged, and still the gate the pipeline asks about. "Publish" here means putting a
        product in front of a customer; the narrower authorities are `refusal_for`.
        """
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

    def refusal_for(self, authority: Authority) -> str | None:
        """Why this client may not do a thing of this kind, or None."""
        no_credentials = (
            "no Etsy credentials in this environment. ETSY_KEYSTRING (or ETSY_API_KEY), "
            "ETSY_SHOP_ID and either ETSY_REFRESH_TOKEN or ETSY_ACCESS_TOKEN are read from "
            "the environment and are never stored in this repository.")

        if authority is Authority.READ:
            # A read creates nothing, charges nothing and cannot be seen by a buyer. The only
            # thing that can stop it is not having a credential.
            return None if self.credentials is not None else no_credentials

        if authority is Authority.DRAFT_WRITE:
            if self.credentials is None:
                return no_credentials
            if self.refusal() is None:
                return None          # full publish authority includes drafting
            if self.shadow_writes_authorised:
                return None
            # The publish refusal is quoted rather than paraphrased, because it is the real
            # reason and there are two of them -- the phase and the owner's authority. A
            # paraphrase here said "the phase does not permit publication" even when the
            # phase did and the grant was what was missing.
            return (f"draft writes are not authorised in this client: {self.refusal()} "
                    f"Draft-only writes without publishing authority need "
                    f"`shadow_writes_authorised` -- a deliberate, separate grant covering "
                    f"objects no buyer can see and no fee attaches to.")

        # ACTIVATE. Everything that guards publication guards this, and nothing less does.
        reason = self.refusal()
        if reason is not None:
            return reason
        if self.shadow_writes_authorised and self.phase not in PHASES_THAT_MAY_PUBLISH:
            return ("shadow_writes_authorised permits drafts, never activation. Activation "
                    "publishes the listing on etsy.com.")
        return None

    def _require(self, authority: Authority) -> Credentials:
        reason = self.refusal_for(authority)
        if reason is not None:
            error = EtsyNotConfigured if "credentials" in reason else EtsyNotPermitted
            raise error(reason)
        assert self.credentials is not None
        return self.credentials

    def _require_permission(self) -> Credentials:
        """Kept for the publish path, which asks the publish question and no other."""
        reason = self.refusal()
        if reason is not None:
            error = EtsyNotConfigured if "credentials" in reason else EtsyNotPermitted
            raise error(reason)
        assert self.credentials is not None
        return self.credentials

    # ---- requests --------------------------------------------------------

    def _call(self, method: str, path: str, *, operation: str,
              authority: Authority = Authority.DRAFT_WRITE,
              form: dict[str, Any] | None = None,
              json: dict[str, Any] | None = None,
              multipart: FilePart | None = None,
              query: dict[str, Any] | None = None,
              allow: tuple[int, ...] = ()) -> Response:
        """One request, with the encoding the endpoint requires and nothing implicit.

        `operation` is Etsy's own operationId. It is passed to the credentials so that a
        token missing that operation's scope is refused here rather than by Etsy, and it is
        recorded on `self.calls` so a caller -- or the probe -- can state what was sent
        without keeping its own log. What is recorded is field *names* for a multipart
        request: the value is the file.

        `allow` names statuses that are an *answer* rather than a failure for this call. The
        only use is checking whether a listing still exists after a delete, where a 404 is the
        result being measured; raising on it would turn the evidence into an exception.
        """
        creds = self._require(authority)
        headers = creds.headers(operation=operation)
        url = f"{self.BASE}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        response = self.transport.request(method, url, headers=headers, json=json,
                                          form=form, multipart=multipart)
        self.calls.append({
            "operation": operation, "method": method, "path": path,
            "encoding": ("multipart/form-data" if multipart is not None else
                         "application/x-www-form-urlencoded" if form is not None else
                         "application/json" if json is not None else "none"),
            "status": response.status,
            "sent": (sorted((form or {}).keys()) + [f"<binary:{multipart.field}>"]
                     if multipart is not None else dict(form or json or {})),
        })
        if response.status >= 400 and response.status not in allow:
            kind = classify_http(response.status)
            message = (f"Etsy returned {response.status} for {method} {path} "
                       f"({operation}): {response.body.get('error', response.body)}")
            if kind is TransientError:
                raise TransientError(message)
            raise EtsyRejected(message)
        return response

    # ---- reads -----------------------------------------------------------

    def get_shop(self) -> dict[str, Any]:
        """Read the shop back. The cheapest possible proof that a credential works.

        Everything else in this client depends on the shop id being right and the key being
        live. Asking Etsy for the shop turns both into an observation instead of an
        assumption, and it creates nothing.
        """
        creds = self._require(Authority.READ)
        return self._call("GET", f"/shops/{creds.shop_id}", operation="getShop",
                          authority=Authority.READ).body

    def get_me(self) -> dict[str, Any]:
        """Who Etsy thinks we are. Needs `shops_r`, so it also checks the OAuth token."""
        return self._call("GET", "/users/me", operation="getMe",
                          authority=Authority.READ).body

    def get_listing(self, listing_id: str, *,
                    includes: tuple[str, ...] = ("Images",)) -> dict[str, Any]:
        """Read a listing back from Etsy, images included.

        This is the method that turns a write into a fact. `includes=Images` is Etsy's own
        association parameter, so one request returns the listing and the images actually
        attached to it -- the pair that decides whether the listing could ever be activated.
        """
        return self._call("GET", f"/listings/{listing_id}", operation="getListing",
                          authority=Authority.READ,
                          query={"includes": ",".join(includes)} if includes else None).body

    def get_listing_images(self, listing_id: str) -> list[dict[str, Any]]:
        """The images Etsy holds for a listing, as Etsy reports them."""
        body = self._call("GET", f"/listings/{listing_id}/images",
                          operation="getListing", authority=Authority.READ).body
        results = body.get("results")
        return list(results) if isinstance(results, list) else []

    def listing_exists(self, listing_id: str) -> tuple[bool, str]:
        """Whether Etsy still holds this listing, and what state it is in. Never raises a 404.

        This is how a deletion is *verified* rather than assumed. `deleteListing` returning
        204 is Etsy saying it accepted the request; only a subsequent read says the listing is
        gone. The two are different claims and Etsy's document supports only the first, so the
        second is one of the things the authenticated run exists to establish.

        Returns `(False, "")` when Etsy answers 404, which is the outcome that means clean.
        """
        response = self._call("GET", f"/listings/{listing_id}", operation="getListing",
                              authority=Authority.READ, allow=(404,))
        if response.status == 404:
            return False, ""
        return True, str(response.body.get("state") or "")

    def get_shop_listings(self, *, state: str = "draft",
                          limit: int = 100) -> list[dict[str, Any]]:
        """The shop's listings in one state. The read that makes a run idempotent.

        A run that failed before its cleanup left a draft in a real shop. Without this, the
        next run cannot see it, so it creates a second one and the shop accumulates test
        artefacts that are indistinguishable from products with a mistake in them. With it,
        the run's first act can be to sweep what a previous run left.

        `getListingsByShop` is the operation; `state` is its own filter parameter, so the
        sweep never sees an active listing and cannot act on one.
        """
        creds = self._require(Authority.READ)
        body = self._call("GET", f"/shops/{creds.shop_id}/listings",
                          operation="getListingsByShop", authority=Authority.READ,
                          query={"state": state, "limit": limit}).body
        results = body.get("results")
        return list(results) if isinstance(results, list) else []

    def get_taxonomy_node(self, taxonomy_id: int = TAXONOMY_PATTERNS) -> dict[str, Any]:
        """Find one seller taxonomy node in Etsy's tree, or return {} if it is not there.

        `TAXONOMY_PATTERNS = 66` is an integer with a comment next to it. A wrong taxonomy id
        is **not an error**: Etsy accepts the create, returns 201, and the listing sits in the
        wrong category where nobody shopping for a crochet pattern will ever see it. So the
        id cannot be confirmed by a successful write, and the only thing that confirms it is
        reading Etsy's own tree and looking at the node's name.

        Etsy returns the whole tree from one endpoint, so this walks it rather than asking for
        a node by id -- there is no by-id operation in the document.
        """
        body = self._call("GET", "/seller-taxonomy/nodes",
                          operation="getSellerTaxonomyNodes",
                          authority=Authority.READ).body
        found: dict[str, Any] = {}

        def walk(nodes: Any) -> None:
            nonlocal found
            if not isinstance(nodes, list):
                return
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if node.get("id") == taxonomy_id and not found:
                    found = node
                walk(node.get("children"))

        walk(body.get("results"))
        return found

    def find_taxonomy_nodes(self, needle: str) -> list[dict[str, Any]]:
        """Every taxonomy node whose name contains `needle`, case-insensitively.

        The companion to `get_taxonomy_node`: when the id turns out to be wrong, the next
        question is immediately "then which id is right", and a run that has already paid for
        the tree should answer it rather than make somebody run it again.
        """
        body = self._call("GET", "/seller-taxonomy/nodes",
                          operation="getSellerTaxonomyNodes",
                          authority=Authority.READ).body
        out: list[dict[str, Any]] = []
        target = needle.lower()

        def walk(nodes: Any) -> None:
            if not isinstance(nodes, list):
                return
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if target in str(node.get("name") or "").lower():
                    out.append({"id": node.get("id"), "name": node.get("name"),
                                "level": node.get("level")})
                walk(node.get("children"))

        walk(body.get("results"))
        return out

    def get_taxonomy_properties(self,
                                taxonomy_id: int = TAXONOMY_PATTERNS) -> list[dict[str, Any]]:
        """The listing properties this taxonomy node defines, and which of them are required.

        If any is `is_required`, **every create against that node is refused** with a property
        id in the message, and nothing in this client can set a listing property. That would
        be a launch blocker discovered by a 400 on the first real product; asking Etsy first
        costs one read.
        """
        body = self._call("GET", f"/seller-taxonomy/nodes/{taxonomy_id}/properties",
                          operation="getPropertiesByTaxonomyId",
                          authority=Authority.READ).body
        results = body.get("results")
        return list(results) if isinstance(results, list) else []

    # ---- draft writes ----------------------------------------------------

    def create_draft(self, payload: ListingPayload) -> str:
        """Create the listing as a draft. Draft, always: activation is a separate decision.

        Form-encoded, because `application/x-www-form-urlencoded` is the only media type
        Etsy lists for this operation. It was JSON until 2026-09-25.

        `state` is **not sent**. Etsy's create schema has no state property -- the operation
        is called createDraftListing and a created listing is a draft -- so sending one was
        sending a field Etsy does not document accepting. Draft-ness is now asserted by
        reading the listing back and finding `state == "draft"`, which is a fact rather than
        a hope.
        """
        creds = self._require(Authority.DRAFT_WRITE)
        fields = payload.to_dict()
        fields.pop("state", None)
        response = self._call("POST", f"/shops/{creds.shop_id}/listings",
                              operation="createDraftListing", form=form_fields(fields))
        listing_id = response.body.get("listing_id")
        if not listing_id:
            raise EtsyRejected(f"Etsy accepted the request but returned no listing_id: "
                               f"{response.body}")
        return str(listing_id)

    def upload_image(self, listing_id: str, *, filename: str, data: bytes,
                     rank: int = 1, alt_text: str = "",
                     overwrite: bool = False) -> dict[str, Any]:
        """Upload a listing image. The step whose absence made every draft unactivatable.

        Etsy: "Setting a `draft` listing to `active` will also publish the listing on
        etsy.com and requires that the listing have an image set." Before this method existed
        this system generated, checked, certified and approved listing imagery and then kept
        every byte of it on our side of the wire -- so the shop could have opened with zero
        activatable listings and every upstream check would still have passed.

        The binary goes in a part named `image`, which is Etsy's parameter name for it. The
        old transport hard-coded `file` for every upload; an image sent that way is a request
        Etsy accepts the shape of and finds no image in.
        """
        creds = self._require(Authority.DRAFT_WRITE)
        if not data:
            raise EtsyRejected(
                f"no bytes to upload for {filename}. An image that is not there cannot be "
                f"uploaded, and a draft with no image can never be activated, so this is a "
                f"launch blocker rather than a cosmetic failure.")
        if rank < 1:
            raise EtsyRejected(f"rank must be a positive non-zero position; got {rank}.")
        if len(alt_text) > ALT_TEXT_MAX:
            raise EtsyRejected(f"alt text is {len(alt_text)} characters; Etsy allows "
                               f"{ALT_TEXT_MAX}.")
        suffix = filename[filename.rfind("."):].lower() if "." in filename else ""
        content_type = IMAGE_CONTENT_TYPES.get(suffix)
        if content_type is None:
            raise EtsyRejected(
                f"{filename!r} is not a listing-image format this client will send "
                f"({sorted(IMAGE_CONTENT_TYPES)}). Sending an unknown type as "
                f"application/octet-stream is how a PDF gets uploaded as a photograph.")
        fields: dict[str, Any] = {"rank": rank}
        if alt_text:
            fields["alt_text"] = alt_text
        if overwrite:
            fields["overwrite"] = True
        response = self._call(
            "POST", f"/shops/{creds.shop_id}/listings/{listing_id}/images",
            operation="uploadListingImage", form=fields,
            multipart=FilePart(field="image", filename=filename, data=data,
                               content_type=content_type))
        image_id = response.body.get("listing_image_id")
        if not image_id:
            raise EtsyRejected(f"Etsy accepted the image upload and returned no "
                               f"listing_image_id: {response.body}")
        return response.body

    def attach_file(self, listing_id: str, *, filename: str, data: bytes) -> bool:
        """Attach the pattern file to a draft listing.

        The digital file is what the customer buys. A listing without one is a product that
        takes money and delivers nothing, which is why the outcome distinguishes that state.
        Etsy's own rule, from `updateListing`: "Digital listings that are not made to order
        must have a file upload associated with it to be activated."

        The bytes have to exist: artifact bytes in this system are not durable until object
        storage is provisioned, so a process that renders a PDF, restarts, and then tries to
        upload it has nothing to send -- the dependency the readiness report records against
        the owner's storage decision.
        """
        creds = self._require(Authority.DRAFT_WRITE)
        if not data:
            raise EtsyRejected(
                f"no bytes to upload for {filename}: the pattern file is not available to "
                f"this process. Artifact bytes are not durable without object storage, so "
                f"the file has to be re-rendered from the certified CIR before publishing.")
        response = self._call(
            "POST", f"/shops/{creds.shop_id}/listings/{listing_id}/files",
            operation="uploadListingFile", form={"name": filename},
            multipart=FilePart(field="file", filename=filename, data=data,
                               content_type="application/pdf"))
        return bool(response.body.get("listing_file_id"))

    def update_listing(self, listing_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Change permitted fields on a listing. PATCH, form-encoded, never activation.

        `state` is refused here even though Etsy's update schema accepts it, because
        `state=active` is the request that publishes a listing and charges a listing fee.
        That request has one door, `activate`, and it is locked.
        """
        creds = self._require(Authority.DRAFT_WRITE)
        if not fields:
            raise EtsyRejected("update_listing was called with no fields. A PATCH that "
                               "changes nothing is a request that can only fail or mislead.")
        if "price" in fields:
            raise EtsyRejected(PRICE_IS_ELSEWHERE)
        if "state" in fields:
            raise EtsyNotPermitted(
                "state is not updatable through update_listing. `state=active` publishes the "
                "listing on etsy.com and incurs Etsy's listing fee; it goes through "
                "`activate`, which requires the launch authorisation.")
        unknown = sorted(set(fields) - UPDATE_WRITABLE)
        if unknown:
            raise EtsyRejected(
                f"updateListing has no such field(s): {unknown}. Etsy's update schema lists "
                f"{len(UPDATE_WRITABLE)} writable fields, and an unknown one is not an error "
                f"we would see -- the listing would simply keep its old value.")
        response = self._call("PATCH", f"/shops/{creds.shop_id}/listings/{listing_id}",
                              operation="updateListing", form=form_fields(fields))
        return response.body

    def delete_listing(self, listing_id: str, *,
                       expect_states: tuple[str, ...] = ("draft", "inactive")) -> bool:
        """Delete a listing, after reading it back and refusing if it is not what we expect.

        The read first is the point. `deleteListing` takes an id and deletes whatever that id
        names, including an active listing a customer is looking at. So this reads the
        listing, refuses unless its state is one the caller said it expected, and only then
        deletes. A wrong id then costs a refusal instead of a product.
        """
        self._require(Authority.DRAFT_WRITE)
        current = self.get_listing(listing_id, includes=())
        state = str(current.get("state", "")).lower()
        if state not in expect_states:
            raise EtsyNotPermitted(
                f"refusing to delete listing {listing_id}: its state on Etsy is {state!r} and "
                f"this call expected one of {list(expect_states)}. Deleting a listing that is "
                f"not the one we think it is cannot be undone.")
        response = self._call("DELETE", f"/listings/{listing_id}",
                              operation="deleteListing")
        return response.status in (200, 204)

    # ---- activation: the one that costs money ----------------------------

    def activate(self, listing_id: str, *, launch_authorisation: str = "") -> dict[str, Any]:
        """Publish a listing on etsy.com. Implemented, gated, and never yet called.

        This is the only method in this system that spends money and the only one whose
        result a member of the public can see. Etsy charges its listing fee on publication,
        not on drafts, so calling this is a purchase decision as well as a product decision.

        Three things must all be true, checked in this order: the phase permits publication,
        the owner has granted publishing authority, and a Launch-0 authorisation string was
        passed to *this call*. The third exists because the first two are process state that
        can drift, and a per-call argument cannot be acquired by a job that was configured
        once and forgotten.

        The pre-flight check is Etsy's own rule, checked before the request so the failure is
        free: a draft with no image cannot be activated, and a digital listing that is not
        made to order needs a file.
        """
        creds = self._require(Authority.ACTIVATE)
        if not launch_authorisation.strip():
            raise EtsyNotPermitted(
                f"activation needs a Launch-0 authorisation on the call itself. Publishing "
                f"puts a product in front of customers and Etsy charges its listing fee "
                f"(US${LISTING_FEE_USD:.2f}) at publication, so this is a spend decision, and "
                f"a spend decision is the owner's.")
        current = self.get_listing(listing_id)
        images = current.get("images") or []
        if not images:
            raise EtsyRejected(
                f"listing {listing_id} has no image on Etsy, so activation would be refused: "
                f"'Setting a `draft` listing to `active` ... requires that the listing have "
                f"an image set.' Upload an image first; nothing is spent by stopping here.")
        # `file_data` is the ShopListing field Etsy describes as the files attached to a
        # digital listing. It is the only file signal on the listing response, so an empty
        # one is the closest thing available to "no download attached".
        if (str(current.get("listing_type") or current.get("type") or "") == "download"
                and str(current.get("when_made") or "") != "made_to_order"
                and not str(current.get("file_data") or "").strip()):
            raise EtsyRejected(
                f"listing {listing_id} is a digital listing with no file attached: 'Digital "
                f"listings that are not made to order must have a file upload associated "
                f"with it to be activated.'")
        response = self._call("PATCH", f"/shops/{creds.shop_id}/listings/{listing_id}",
                              operation="updateListing", authority=Authority.ACTIVATE,
                              form={"state": "active"})
        return response.body

    # ---- the publish path, unchanged in what it permits -------------------

    def publish(self, *, payload: ListingPayload, filename: str, data: bytes,
                images: list[tuple[str, bytes]] | None = None) -> PublishOutcome:
        """Create the draft, attach the file and upload the images, reporting each honestly.

        Still creates a draft and still stops there: activation is gated. What has changed is
        that stopping there is now a stated position rather than the end of the code.

        `images` is optional and its absence is reported as a problem rather than ignored. A
        caller that passes none gets a draft that Etsy will never activate, which is exactly
        the state this system was in until 2026-09-25 -- and the outcome now says so instead
        of returning `published=True` about a listing that could not go live. **No caller in
        this system supplies image bytes yet**: the listing imagery is a release artefact and
        the bytes are not durable without object storage, which is an owner decision already
        in the queue and a dependency this department does not own.
        """
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

        problems = [] if uploaded else [f"listing {listing_id} exists with no file attached"]
        images_uploaded = 0
        for rank, (image_name, image_bytes) in enumerate(images or [], start=1):
            try:
                self.upload_image(listing_id, filename=image_name, data=image_bytes,
                                  rank=rank)
                images_uploaded += 1
            except (TransientError, EtsyRejected) as e:
                problems.append(f"image {rank} ({image_name}) was not uploaded: {e}")
        if not images:
            problems.append(
                f"listing {listing_id} has no image, so Etsy will never activate it: "
                f"'Setting a `draft` listing to `active` ... requires that the listing have "
                f"an image set.' No image bytes were passed to publish().")

        return PublishOutcome(published=uploaded, listing_id=listing_id,
                              file_uploaded=uploaded, images_uploaded=images_uploaded,
                              problems=problems)
