"""The one authenticated shadow-write run, and the taxonomy that classifies what it returns.

There are no Etsy credentials in this environment and not one write has ever reached Etsy.
When the owner's authorisation arrives (`research/ETSY_TRANSPORT.md` section 5.1), this module
is what runs. It is written now so that the run costs **one attempt rather than five**: every
outcome it can produce is already named, already attributed to a cause, and already attached
to the single change that follows from it.

## The eight steps, in this order

0.  **Ping**, and then **sweep**. The ping needs no token and tells the classifier whether a
    later failure is the network. The sweep deletes any draft a *previous* run left behind,
    which is what makes this safe to run twice.
1.  **Authenticated identity and shop read.** Who Etsy thinks we are and whether
    `ETSY_SHOP_ID` names a shop we can read. Nothing after this is meaningful if it fails.
2.  **Create one clearly marked test draft** -- "DO NOT BUY - Brambleloop transport test".
3.  **Upload an image.** The step whose absence made every draft permanently unactivatable.
4.  **Update permitted fields.** A form-encoded PATCH.
5.  **Read the listing back from Etsy.** A separate request: the write's own 200 is Etsy
    repeating our data at us and no mismatch can appear in it.
6.  **Verify taxonomy, properties, encoding and remote values.** The step that produces the
    evidence. A 201 is not evidence of anything here: a wrong taxonomy id is a listing in the
    wrong category rather than an error, and a wrongly encoded tag list is stored without
    complaint as one tag containing a comma.
7.  **Delete the test draft.**
8.  **Verify the cleanup.** Read the listing back and require a 404. A 204 is Etsy accepting
    the request, which is a different claim from the listing being gone.

Activation is not in that list and never will be. A draft is invisible to buyers and free;
publication is neither, Etsy charges its listing fee at publication, and `activate` refuses
without a Launch-0 authorisation passed to the call itself. The whole run costs **CA$0**.

## Three states, never collapsed

`publish.listing_schema` holds IMPLEMENTED, LOCALLY_TESTED and VERIFIED_AGAINST_ETSY, and
this run reports every claim in the same three. **One successful run against
`tests/fake_etsy.py` is not evidence of Etsy's behaviour** -- the fake is our reading of
Etsy's document, written by the same hand as the client, so if the reading is wrong both are
wrong together and every test still passes. A claim only reaches VERIFIED_AGAINST_ETSY here
when this run observed the specific discriminating evidence for it against `openapi.etsy.com`,
and `claims()` below refuses to promote one on anything less.

## Secrets

Nothing in the report is a secret. Every value that leaves this module passes through
`http.Redactor`, seeded with the credentials this process actually holds, so a token echoed
back inside an error message, a URL or a field Etsy added after this code was written is
replaced by a fingerprint rather than hoped about. Redaction happens where a response becomes
a report, not where a report is printed.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
import zlib
from dataclasses import dataclass, field
from typing import Any, Callable

from ..core.resilience import PermanentError, TransientError
from ..publish import listing_schema
from .etsy import (
    ARRAY_ENCODING, TAXONOMY_PATTERNS, Authority, Credentials, EtsyClient, EtsyNotPermitted,
    EtsyRejected, build_payload,
)
from .etsy_verify import verify
from .http import Redactor

# What the test draft says it is, in the first words of its title, so that a human who finds
# it in Shop Manager before the cleanup runs knows immediately what it is and that it is safe
# to delete. Etsy's title character set allows letters, digits, punctuation and whitespace.
TEST_TITLE_PREFIX = "DO NOT BUY - Brambleloop transport test"


# ---------------------------------------------------------------------------
# The three causes. Which one an outcome has decides who fixes it.

OUR_BUG = "OUR_BUG"
"""This system sent something wrong. The fix is in this repository and it is ours.

Includes the two cases that look like successes: a taxonomy id that is simply the wrong
integer, and an array encoding Etsy stores without complaining about.
"""

ETSY_CONTRACT_DRIFT = "ETSY_CONTRACT_DRIFT"
"""Etsy behaves differently from Etsy's own published document.

The fix is still in this repository, but it is a different fix and a different conversation:
the reading was right and the document is wrong or stale, so what changes is the recorded
source alongside the code, and `listing_schema.READ_ON` needs a fresh reading.
"""

ENVIRONMENT = "ENVIRONMENT"
"""Nothing about our request or Etsy's contract. Credentials, scopes, network, or an outage.

Costs no code change at all. Most of these end at the owner: a scope not approved, an app not
active, a refresh token spent. Re-running is the right response to exactly one of them.
"""

CONFIRMED = "CONFIRMED"
"""Not a failure: the outcome that turns the claim into a fact. Listed with the others so the
taxonomy covers the whole outcome space rather than only the bad half."""

CAUSES = (CONFIRMED, OUR_BUG, ETSY_CONTRACT_DRIFT, ENVIRONMENT)


@dataclass(frozen=True)
class Signature:
    """One outcome the run can produce, and everything needed to act on it without thinking.

    `change` is the point of the whole file. A taxonomy entry that says "investigate" has
    moved the work rather than done it, so every entry here names one concrete change -- a
    constant, a field name, a call -- or says explicitly that no code changes.
    """

    claim: str            # the claim in listing_schema.verification_matrix() this settles
    step: str             # the probe step that produces it
    outcome: str          # short identifier, stable enough to grep for
    we_send: str
    signal: str           # what we would see
    means: str
    cause: str
    change: str
    match: Callable[[dict], bool] = lambda ctx: False
    settles: bool = True
    """Whether this outcome decides the claim. False for an outcome that is about the run
    rather than about Etsy -- a check that could not be made, a credential that was refused.
    Those must leave the claim exactly where it was: "we could not look" is not "it is
    broken", and conflating them is how a run produces a worse record than no run at all."""

    def __post_init__(self) -> None:
        if self.cause not in CAUSES:
            raise ValueError(f"{self.outcome}: {self.cause!r} is not one of {list(CAUSES)}")

    def to_dict(self) -> dict[str, Any]:
        return {"claim": self.claim, "step": self.step, "outcome": self.outcome,
                "we_send": self.we_send, "signal": self.signal, "means": self.means,
                "cause": self.cause, "change": self.change, "settles": self.settles}


def _text(ctx: dict[str, Any]) -> str:
    """Everything a response said, lowercased, for matching. Never used for a decision that
    a status code could make: an error string is Etsy's prose and prose changes."""
    return str(ctx.get("error") or ctx.get("body") or "").lower()


def _status(ctx: dict[str, Any]) -> int:
    try:
        return int(ctx.get("status") or 0)
    except (TypeError, ValueError):
        return 0


def _ping_ok(ctx: dict[str, Any]) -> bool:
    """Whether the unauthenticated ping reached Etsy in this same run.

    This is the discriminator that separates ENVIRONMENT from everything else: if the ping
    reached Etsy and the authenticated call did not, the network is not the problem.
    """
    return bool(ctx.get("ping_reachable"))


# The unauthenticated-transport failure, which can happen at any step and always means the
# same thing. `UrllibTransport` reports a connection failure as a synthetic 503.
_NETWORK = dict(
    we_send="the request for this step",
    signal=("HTTP 503 with 'transport failure', a TLS error, a proxy 403/407, a reset "
            "connection, or any 5xx from Etsy"),
    means=("the request never got an answer from Etsy's application. The step-0 ping "
           "separates the two cases: if it failed too, this environment cannot reach Etsy; "
           "if it succeeded, Etsy is up and this endpoint is not. Neither says anything "
           "about our request"),
    cause=ENVIRONMENT,
    change=("none. Check the agent proxy (curl \"$HTTPS_PROXY/__agentproxy/status\") if the "
            "ping failed, and re-run. The run is idempotent and its sweep removes anything a "
            "half-finished attempt left, so a retry costs nothing and creates nothing extra"))

_AUTH = dict(
    signal="HTTP 403 with Etsy's API-key error string, or 401 invalid_token",
    means=("the keystring, the shared secret or the access token is not what Etsy will "
           "accept. Our reading of the contract is untouched by this"),
    cause=ENVIRONMENT,
    change=("none in code. ETSY_KEYSTRING/ETSY_SHARED_SECRET must match the app in "
            "etsy.com/developers/your-apps, and the app must be active. A 401 means the "
            "refresh produced a token Etsy will not take: the owner re-authorises"))

_SCOPE = dict(
    signal="HTTP 403 whose body names a scope, e.g. 'insufficient scope; missing listings_w'",
    means="the owner approved fewer scopes than the app asked for",
    cause=ENVIRONMENT,
    change=("none in code. The owner re-opens the authorize URL and approves "
            "listings_r listings_w listings_d shops_r shops_w. `TokenProvider` already "
            "refuses an operation whose scope Etsy did not grant, so this is visible before "
            "the request whenever ETSY_SCOPES is set"))


def _network_sig(claim: str, step: str) -> Signature:
    return Signature(claim=claim, step=step, outcome=f"{step}_unreachable", settles=False,
                     match=lambda ctx: (_status(ctx) >= 500
                                        or (_status(ctx) in (0, 407)
                                            and not _ping_ok(ctx))),
                     **_NETWORK)


def _auth_sig(claim: str, step: str) -> Signature:
    return Signature(claim=claim, step=step, outcome=f"{step}_credentials_refused",
                     settles=False,
                     we_send="the request for this step, with x-api-key and a bearer token",
                     match=lambda ctx: (_status(ctx) in (401, 403)
                                        and "scope" not in _text(ctx)
                                        and "property" not in _text(ctx)),
                     **_AUTH)


def _scope_sig(claim: str, step: str) -> Signature:
    return Signature(claim=claim, step=step, outcome=f"{step}_scope_missing", settles=False,
                     we_send="the request for this step, with the granted bearer token",
                     match=lambda ctx: _status(ctx) == 403 and "scope" in _text(ctx),
                     **_SCOPE)


# ---------------------------------------------------------------------------
# The taxonomy itself: every outcome of every step, in the order the step runs.
#
# Each entry is built from one of the specific unexercised claims in ETSY_TRANSPORT.md
# section 3.3, because each has its own signature and its own single change. Read the `cause`
# column as the answer to "who fixes this".

TAXONOMY: tuple[Signature, ...] = (

    # -- step 1: authenticated identity and shop read ----------------------
    _network_sig("oauth_token_endpoint", "identity"),
    _scope_sig("oauth_token_endpoint", "identity"),
    Signature(
        claim="oauth_token_endpoint", step="identity", outcome="token_endpoint_404_both",
        we_send=("POST to https://api.etsy.com/v3/public/oauth/token, form-encoded per RFC "
                 "6749 4.1.3, then the same to https://openapi.etsy.com/... on a 404"),
        signal="both hosts answer 404 before any listing request is made",
        means=("neither host Etsy documents serves the token endpoint. Etsy's authentication "
               "page and Etsy's OpenAPI document give two different hosts and this is the "
               "case where both readings are stale"),
        cause=ETSY_CONTRACT_DRIFT,
        change=("re-read developer.etsy.com/documentation/essentials/authentication and set "
                "etsy_oauth.TOKEN_URL to the host it now gives; refresh "
                "listing_schema.READ_ON"),
        match=lambda ctx: _status(ctx) == 404 and "oauth" in _text(ctx)),
    Signature(
        claim="oauth_token_endpoint", step="identity", outcome="token_endpoint_alternate_won",
        we_send="the refresh grant to api.etsy.com first, openapi.etsy.com on a 404",
        signal="api.etsy.com answered 404 and openapi.etsy.com answered 200",
        means=("the two Etsy documents disagreed and Etsy settled it. The fallback in "
               "`etsy_oauth._token_request` did its job, which is the only reason this run "
               "got as far as a shop read"),
        cause=ETSY_CONTRACT_DRIFT,
        change=("set etsy_oauth.TOKEN_URL to the openapi host and keep the fallback pointing "
                "the other way, so the common case is one request rather than two"),
        match=lambda ctx: bool(ctx.get("token_alternate_used"))),
    Signature(
        claim="oauth_token_endpoint", step="identity", outcome="refresh_token_spent",
        we_send="grant_type=refresh_token with ETSY_REFRESH_TOKEN",
        signal="HTTP 400 invalid_grant, 'refresh token unknown, spent or expired'",
        means=("Etsy rotates the refresh token on every refresh and the environment holds a "
               "spent one. Not a bug: it is what happens when a refresh succeeded somewhere "
               "and the rotated token was not written back"),
        cause=ENVIRONMENT,
        change=("none in code -- `TokenProvider` already hands the rotated token to "
                "`on_refresh`. The deployment must persist what that callback receives, and "
                "the owner re-authorises once to get a live token"),
        match=lambda ctx: _status(ctx) == 400 and "invalid_grant" in _text(ctx)),
    _auth_sig("oauth_token_endpoint", "identity"),
    Signature(
        claim="oauth_token_endpoint", step="identity", outcome="shop_not_found",
        we_send="GET /shops/{ETSY_SHOP_ID} and GET /users/me",
        signal="HTTP 404 'Shop not found', while /users/me answers 200",
        means="the token is good and ETSY_SHOP_ID names a shop this account does not own",
        cause=ENVIRONMENT,
        change=("none in code. Take shop_id from the /users/me response this run printed and "
                "correct ETSY_SHOP_ID in the deployment environment"),
        match=lambda ctx: _status(ctx) == 404),
    Signature(
        claim="oauth_token_endpoint", step="identity", outcome="identity_read",
        we_send="GET /users/me then GET /shops/{ETSY_SHOP_ID}",
        signal="both answer 200 and the shop's id matches the one we addressed",
        means=("the app is registered and active, the grant worked, the token carries the "
               "read scopes and the shop id is right. Everything after this is about "
               "encodings rather than credentials"),
        cause=CONFIRMED,
        change="none. The OAuth path and the token endpoint host are now facts",
        match=lambda ctx: _status(ctx) in (200, 0) and bool(ctx.get("ok"))),

    # -- step 2: create the draft ------------------------------------------
    _network_sig("form_encoded_create", "create_draft"),
    _scope_sig("form_encoded_create", "create_draft"),
    _auth_sig("form_encoded_create", "create_draft"),
    Signature(
        claim="form_encoded_create", step="create_draft", outcome="create_media_type_refused",
        we_send=("POST /shops/{id}/listings, Content-Type application/x-www-form-urlencoded, "
                 "the seven required fields plus is_supply, type, tags and materials"),
        signal="HTTP 415 Unsupported Media Type",
        means=("Etsy refuses the only media type its own document lists for this operation. "
               "Our encoder is not wrong; the document is"),
        cause=ETSY_CONTRACT_DRIFT,
        change=("switch this one call to the `json` body channel -- `_call(..., json=...)` "
                "in `EtsyClient.create_draft` -- and re-read the OpenAPI document. The "
                "transport already carries all three channels, so this is one argument"),
        match=lambda ctx: _status(ctx) == 415),
    Signature(
        claim="taxonomy_required_properties", step="create_draft",
        outcome="create_needs_listing_property",
        we_send="the create request with taxonomy_id=%d" % TAXONOMY_PATTERNS,
        signal="HTTP 400 whose message names a property or a property_id",
        means=("the patterns taxonomy node marks a listing property required, so **every** "
               "create against this node is refused until it is set. Nothing in this client "
               "can set a listing property"),
        cause=OUR_BUG,
        change=("a build task, not a tweak: implement updateListingProperty (PUT "
                "/shops/{shop_id}/listings/{listing_id}/properties/{property_id}) and call "
                "it after create. This run's step-6 property read names the exact ids. The "
                "taxonomy_required_properties gap becomes a launch blocker"),
        match=lambda ctx: _status(ctx) == 400 and "propert" in _text(ctx)),
    Signature(
        claim="array_encoding_tags", step="create_draft", outcome="tags_rejected_on_create",
        we_send="tags as ARRAY_ENCODING=%r renders them" % ARRAY_ENCODING,
        signal=("HTTP 400 naming tags or materials -- 'may not contain a comma', 'expected "
                "an array', or a tag-length complaint whose length is the joined string's"),
        means=("the other reading of Etsy's document is the right one. Etsy's tags "
               "description says 'a comma-separated list' and the OpenAPI default for an "
               "un-encoded form array is repeated keys; we picked the first and Etsy has now "
               "settled it"),
        cause=OUR_BUG,
        change=("set integrations.etsy.ARRAY_ENCODING = \"repeat\" -- one constant, already "
                "wired through form_fields and http.form_body, and already exercised both "
                "ways against the fake -- and re-run. If only one of tags/materials is named, "
                "the encoding is per field and ARRAY_ENCODING becomes a mapping"),
        match=lambda ctx: (_status(ctx) == 400
                           and ("tag" in _text(ctx) or "material" in _text(ctx)))),
    Signature(
        claim="form_encoded_create", step="create_draft", outcome="create_missing_field",
        we_send="quantity, title, description, price, who_made, when_made, taxonomy_id",
        signal="HTTP 400 'Required parameters missing: [...]'",
        means=("if the named field is one we sent, our encoder dropped it or sent it under "
               "another name -- OUR_BUG. If it is a field the document's `required` array "
               "does not list, Etsy requires something it does not document -- drift. The "
               "run records the field names it sent so the two are told apart on sight"),
        cause=OUR_BUG,
        change=("compare the named fields against the `sent` list in this step's record. Ours "
                "to fix in `ListingPayload.to_dict`; Etsy's to record by adding the field to "
                "listing_schema.REQUIRED_TO_CREATE and to the payload"),
        match=lambda ctx: _status(ctx) == 400 and "missing" in _text(ctx)),
    Signature(
        claim="form_encoded_create", step="create_draft", outcome="create_rejected_other",
        we_send="the form-encoded create request",
        signal="HTTP 400 naming something else -- an enum value, a character, a length",
        means=("Etsy enforces a rule our reading of its document got wrong. Which of the "
               "three causes it is depends on whether the document states the rule: it does "
               "for the enums and lengths (ours), and it does not for the character sets"),
        cause=OUR_BUG,
        change=("fix the named limit where it is written down -- the enums in "
                "listing_schema, the lengths in etsy.TITLE_MAX/TAGS_MAX, the character sets "
                "in listing_schema.TITLE_CATEGORIES -- and record which one Etsy actually "
                "enforced, since that closes the character-set gap either way"),
        match=lambda ctx: _status(ctx) == 400),
    Signature(
        claim="form_encoded_create", step="create_draft", outcome="create_accepted",
        we_send="the form-encoded create request",
        signal="HTTP 201 with a listing_id",
        means=("Etsy accepts application/x-www-form-urlencoded for createDraftListing. This "
               "much is settled by the status alone -- and **nothing about the content is**: "
               "the taxonomy, the tags and the draft state are all still unverified until "
               "step 6 reads them back"),
        cause=CONFIRMED,
        change="none. form_encoded_create becomes VERIFIED_AGAINST_ETSY",
        match=lambda ctx: _status(ctx) == 201 or bool(ctx.get("ok"))),

    # -- step 3: upload the image ------------------------------------------
    _network_sig("multipart_image_upload", "upload_image"),
    _scope_sig("multipart_image_upload", "upload_image"),
    _auth_sig("multipart_image_upload", "upload_image"),
    Signature(
        claim="image_minimum_acceptable", step="upload_image", outcome="image_too_small",
        we_send="a generated 1x1 PNG in a multipart part named `image`",
        signal=("HTTP 400 or 413 naming a dimension, a pixel count, a minimum size or an "
                "aspect ratio"),
        means=("the multipart transport worked -- Etsy read the part, found an image and "
               "judged it. What failed is the probe's fixture. Etsy's image rules live on "
               "help.etsy.com, which refuses automated readers, so this was never a reading "
               "either: it is the one thing in the run we expected to learn by being told"),
        cause=OUR_BUG,
        change=("call `png(width, height)` with the size Etsy's message names -- the "
                "generator already takes dimensions -- and re-run. multipart_image_upload "
                "stays LOCALLY_TESTED until an image is actually accepted"),
        match=lambda ctx: (_status(ctx) in (400, 413)
                           and any(w in _text(ctx) for w in
                                   ("small", "dimension", "pixel", "size", "width",
                                    "height", "ratio", "large")))),
    Signature(
        claim="multipart_image_upload", step="upload_image", outcome="image_part_not_found",
        we_send="multipart/form-data with the binary in a part named `image`",
        signal="HTTP 400 'No image supplied' or a message listing the parts received",
        means=("Etsy did not find a part named `image`. Our multipart encoder is producing "
               "something a real parser reads differently from Python's `email` package, "
               "which is the parser the fake uses"),
        cause=OUR_BUG,
        change=("compare the exact bytes `http.multipart_body` produced against the part "
                "names Etsy's message lists, and fix `FilePart.field` or the boundary "
                "rendering. This is the defect the old transport had: it hard-coded `file`"),
        match=lambda ctx: _status(ctx) == 400 and ("no image" in _text(ctx)
                                                   or "part" in _text(ctx))),
    Signature(
        claim="multipart_image_upload", step="upload_image", outcome="image_media_type_refused",
        we_send="Content-Type: multipart/form-data with our boundary",
        signal="HTTP 415",
        means="Etsy refuses the media type its own document lists for uploadListingImage",
        cause=ETSY_CONTRACT_DRIFT,
        change=("re-read the uploadListingImage request body in the OpenAPI document and "
                "send what it now says; refresh listing_schema.READ_ON"),
        match=lambda ctx: _status(ctx) == 415),
    Signature(
        claim="multipart_image_upload", step="upload_image", outcome="image_format_refused",
        we_send="a PNG, declared as image/png in the part's own Content-Type",
        signal="HTTP 400 naming the format, e.g. 'Unsupported image format'",
        means=("Etsy reached the bytes and would not take a PNG. The transport worked and "
               "`IMAGE_CONTENT_TYPES` offers a format Etsy does not accept for listings"),
        cause=ETSY_CONTRACT_DRIFT,
        change=("send a JPEG instead -- `IMAGE_CONTENT_TYPES` already carries it -- and "
                "remove PNG from that mapping so no product ever tries it"),
        match=lambda ctx: _status(ctx) == 400 and "format" in _text(ctx)),
    Signature(
        claim="multipart_image_upload", step="upload_image", outcome="image_accepted",
        we_send="the multipart upload",
        signal="HTTP 201 with a listing_image_id",
        means=("Etsy took the image. Whether it is attached to the listing is a separate "
               "question that step 6 answers by reading the listing's images back"),
        cause=CONFIRMED,
        change=("none. image_minimum_acceptable becomes VERIFIED_AGAINST_ETSY; "
                "multipart_image_upload waits for step 6"),
        match=lambda ctx: _status(ctx) == 201 or bool(ctx.get("ok"))),

    # -- step 4: update permitted fields -----------------------------------
    _network_sig("form_encoded_create", "update_listing"),
    _auth_sig("form_encoded_create", "update_listing"),
    Signature(
        claim="form_encoded_create", step="update_listing", outcome="update_method_refused",
        we_send="PATCH /shops/{id}/listings/{listing_id}, form-encoded",
        signal="HTTP 405 Method Not Allowed, or 404 on a path the create just used",
        means=("updateListing is not a PATCH. The document says it is, and this was one of "
               "the four defects the 2026-09-25 reading corrected in the other direction"),
        cause=ETSY_CONTRACT_DRIFT,
        change="change the method in `EtsyClient.update_listing` to the one Etsy's 405 allows",
        match=lambda ctx: _status(ctx) in (404, 405)),
    Signature(
        claim="array_encoding_tags", step="update_listing", outcome="tags_rejected_on_update",
        we_send="tags as ARRAY_ENCODING=%r renders them, in a PATCH" % ARRAY_ENCODING,
        signal="HTTP 400 naming tags",
        means="as tags_rejected_on_create, reached through the update instead",
        cause=OUR_BUG,
        change="set integrations.etsy.ARRAY_ENCODING = \"repeat\" and re-run",
        match=lambda ctx: _status(ctx) == 400 and "tag" in _text(ctx)),
    Signature(
        claim="form_encoded_create", step="update_listing", outcome="update_accepted",
        we_send="the form-encoded PATCH",
        signal="HTTP 200",
        means=("Etsy accepted the PATCH. It does **not** mean the fields changed: an unknown "
               "form field is ignored silently and returns 200, which is why step 5 exists"),
        cause=CONFIRMED,
        change="none",
        match=lambda ctx: _status(ctx) == 200 or bool(ctx.get("ok"))),

    # -- step 6: verify taxonomy, properties, encoding and remote values ----
    Signature(
        claim="taxonomy_patterns_id", step="verify_contract", outcome="taxonomy_unreadable",
        settles=False,
        we_send="GET /seller-taxonomy/nodes and /seller-taxonomy/nodes/{id}/properties",
        signal="either read failed, including a refusal raised by this system before sending",
        means=("the taxonomy could not be checked. That is not evidence that it is right and "
               "not evidence that it is wrong -- the two claims it would have settled stay "
               "exactly where they were"),
        cause=ENVIRONMENT,
        change=("read `taxonomy.node_error` / `taxonomy.properties_error` in this step's "
                "record: it names the fix, including the two-line addition to "
                "etsy_oauth.SCOPES_REQUIRED when that is what blocked it"),
        match=lambda ctx: bool(ctx.get("taxonomy_unreadable"))),
    Signature(
        claim="taxonomy_patterns_id", step="verify_contract", outcome="taxonomy_id_wrong",
        we_send="taxonomy_id=%d, then GET /seller-taxonomy/nodes to look it up" % TAXONOMY_PATTERNS,
        signal=("the node is absent from Etsy's tree, or present under a name that is not "
                "Patterns -- with the create having returned 201 either way"),
        means=("the listing is in the wrong category and **no status code anywhere says so**. "
               "This is the outcome that makes reading the node back non-negotiable: a "
               "listing nobody shopping for a crochet pattern can find is not an error, it "
               "is an invisible product"),
        cause=OUR_BUG,
        change=("set integrations.etsy.TAXONOMY_PATTERNS to the id of the node this run "
                "printed under `taxonomy_candidates` -- the run searches the tree for "
                "'pattern' precisely so the corrected value is in the same report"),
        match=lambda ctx: bool(ctx.get("taxonomy_wrong"))),
    Signature(
        claim="taxonomy_patterns_id", step="verify_contract", outcome="taxonomy_id_remapped",
        we_send="taxonomy_id=%d on the create" % TAXONOMY_PATTERNS,
        signal="the listing Etsy holds carries a different taxonomy_id from the one we sent",
        means=("Etsy silently remapped the node, which it does for deprecated ones. Our value "
               "was accepted and is not what the listing has"),
        cause=ETSY_CONTRACT_DRIFT,
        change=("set TAXONOMY_PATTERNS to the id Etsy returned, and record that this node "
                "redirects so a future reading of the document does not change it back"),
        match=lambda ctx: bool(ctx.get("taxonomy_remapped"))),
    Signature(
        claim="taxonomy_required_properties", step="verify_contract",
        outcome="taxonomy_requires_property",
        we_send="GET /seller-taxonomy/nodes/%d/properties" % TAXONOMY_PATTERNS,
        signal="a property with is_required true, while the create returned 201",
        means=("the node requires a property that a draft can be created without. It will be "
               "demanded at activation, which is the worst possible moment to discover it: "
               "the fee-charging call is the one that fails"),
        cause=OUR_BUG,
        change=("implement updateListingProperty and set the named property before any "
                "activation; move the taxonomy_required_properties gap to blocks_launch"),
        match=lambda ctx: bool(ctx.get("required_properties"))),
    Signature(
        claim="array_encoding_tags", step="verify_contract", outcome="tags_stored_comma_joined",
        we_send="tags=%s" % ("a,b (comma-joined)" if ARRAY_ENCODING == "comma"
                             else "tags=a&tags=b (repeated keys)"),
        signal=("Etsy returns ONE tag containing a comma where we sent two tags -- after a "
                "201 and a 200, with no error at any point"),
        means=("the wrong reading of Etsy's document. Both readings are Etsy's own, this is "
               "the ambiguity named in ETSY_TRANSPORT.md 3.3, and **it is settled by a "
               "comparison rather than by a status code**: every request in the run succeeded"),
        cause=OUR_BUG,
        change=("set integrations.etsy.ARRAY_ENCODING = \"repeat\" and re-run. Nothing else "
                "moves: form_fields reads the constant, http.form_body renders a list as "
                "repeated keys, and both settings already pass against the fake"),
        match=lambda ctx: bool(ctx.get("tags_collapsed"))),
    Signature(
        claim="array_encoding_tags", step="verify_contract", outcome="tags_round_tripped",
        we_send="tags under ARRAY_ENCODING=%r" % ARRAY_ENCODING,
        signal="Etsy returns exactly the tags we sent, as separate tags, in order",
        means="the encoding we chose is the one Etsy reads. The ambiguity is closed",
        cause=CONFIRMED,
        change=("none. array_encoding_tags becomes VERIFIED_AGAINST_ETSY and the ARRAY_ENCODING "
                "comment gains the observation date"),
        match=lambda ctx: bool(ctx.get("tags_match"))),
    Signature(
        claim="form_encoded_create", step="verify_contract", outcome="field_not_returned",
        we_send="the create and update payloads",
        signal="a field we sent is absent from Etsy's listing response entirely",
        means=("the write cannot be confirmed either way. Not a match and not a mismatch -- "
               "`etsy_verify` reports NOT_RETURNED for exactly this and counts it against "
               "verification, because a verifier that passes when it cannot see is decoration"),
        cause=ETSY_CONTRACT_DRIFT,
        change=("if the field is one ShopListing documents, Etsy's response has dropped it: "
                "record it and verify that field through a different read. If it is one we "
                "invented, remove it from the payload"),
        match=lambda ctx: bool(ctx.get("not_returned"))),
    Signature(
        claim="form_encoded_create", step="verify_contract", outcome="value_mismatch",
        we_send="the create and update payloads",
        signal="Etsy holds a different value from the one we sent, after a 200/201",
        means=("Etsy accepted a field and did something else with it. The classic case is a "
               "field `updateListing` has no property for: accepted as an unknown form field, "
               "ignored, 200 returned"),
        cause=OUR_BUG,
        change=("check the field against `etsy.UPDATE_WRITABLE`. If it is not there, this "
                "client should have refused it before sending -- add it to the guard. If it "
                "is there and Etsy ignored it anyway, that is drift and the set is wrong"),
        match=lambda ctx: bool(ctx.get("mismatched"))),
    Signature(
        claim="form_encoded_create", step="verify_contract", outcome="not_a_draft",
        we_send="createDraftListing, with no `state` field at all",
        signal="the listing Etsy holds is not in state 'draft'",
        means=("a listing this run created is reachable by buyers. The single most serious "
               "outcome in the whole taxonomy: the run's entire premise is that it cannot "
               "publish anything"),
        cause=ETSY_CONTRACT_DRIFT,
        change=("stop. Delete the listing (step 7 runs regardless), do not re-run, and raise "
                "an owner action: createDraftListing does not create a draft, so no shadow "
                "write is safe until Etsy's actual default state is established"),
        match=lambda ctx: bool(ctx.get("not_draft"))),
    Signature(
        claim="multipart_image_upload", step="verify_contract", outcome="image_not_attached",
        we_send="the image upload, then GET /listings/{id}?includes=Images",
        signal="the upload returned 201 and Etsy reports zero images on the listing",
        means=("the image exists and is not on this listing. A draft in that state can never "
               "be activated, which is the exact failure the upload path was written to fix, "
               "reached by a different route"),
        cause=OUR_BUG,
        change=("check the listing_id in the upload URL against the one create returned, and "
                "whether `rank` needs to be set for the image to attach"),
        match=lambda ctx: bool(ctx.get("image_missing"))),
    Signature(
        claim="multipart_image_upload", step="verify_contract", outcome="remote_values_match",
        we_send="everything the create and the update sent",
        signal="every field Etsy returned matches, the state is draft, and one image is held",
        means=("the write path works against Etsy, end to end, for a listing Etsy actually "
               "holds. This is the evidence section 3.3 of ETSY_TRANSPORT.md is missing"),
        cause=CONFIRMED,
        change=("none. form_encoded_create, multipart_image_upload and array_encoding_tags "
                "all become VERIFIED_AGAINST_ETSY, with this run's report as the observation"),
        match=lambda ctx: bool(ctx.get("verified"))),

    # -- steps 7 and 8: delete, and verify the deletion --------------------
    _network_sig("delete_removes_draft", "cleanup"),
    # The specific scope signature rather than the generic one, because listings_d is the one
    # scope whose absence leaves an artefact in a real shop -- a different consequence from
    # any other missing scope, and the only one with an owner action attached.
    Signature(
        claim="delete_removes_draft", step="cleanup", outcome="delete_scope_missing",
        settles=False,
        we_send="DELETE /listings/{listing_id}",
        signal="HTTP 403 naming listings_d",
        means=("the owner approved the write scopes and not the delete scope, so this run "
               "can create test drafts it cannot remove"),
        cause=ENVIRONMENT,
        change=("none in code. The owner re-authorises including listings_d. Until then the "
                "draft named in this report must be deleted by hand in Shop Manager, and "
                "ETSY_SHADOW_WRITE should be unset so no further run creates one"),
        match=lambda ctx: _status(ctx) == 403 and "listings_d" in _text(ctx)),
    Signature(
        claim="delete_removes_draft", step="cleanup", outcome="delete_refused_wrong_state",
        settles=False,
        we_send="a read of the listing's state, then DELETE only if it is 'draft'",
        signal="the client refused before sending: the state on Etsy was not 'draft'",
        means=("the listing changed underneath us. The guard did its job -- `deleteListing` "
               "deletes whatever the id names, including an active listing"),
        cause=ENVIRONMENT,
        change=("none. The report names the id and the state; a human decides. Never widen "
                "`expect_states` to make this pass"),
        match=lambda ctx: "refusing to delete" in _text(ctx)),
    Signature(
        claim="delete_removes_draft", step="cleanup", outcome="delete_rejected",
        we_send="DELETE /listings/{listing_id} for a listing just read as a draft",
        signal="HTTP 400 or 409 from Etsy",
        means=("Etsy will not delete a draft it says is deletable. Its document lists DRAFT "
               "among the deletable states, so either that is wrong or this listing is not "
               "in the state the read reported"),
        cause=ETSY_CONTRACT_DRIFT,
        change=("record Etsy's message and the state the read returned; they are in this "
                "report side by side. The draft is named for manual removal either way, and "
                "ETSY_SHADOW_WRITE should be unset until it is understood, because every "
                "further run would leave another one"),
        match=lambda ctx: _status(ctx) in (400, 409)),
    Signature(
        claim="delete_removes_draft", step="cleanup", outcome="delete_accepted",
        we_send="a read of the listing's state, then DELETE /listings/{listing_id}",
        signal="HTTP 204",
        means=("Etsy accepted the deletion. It does **not** mean the listing is gone: that "
               "is step 8's question and Etsy's document says nothing about what a deleted "
               "draft becomes"),
        cause=CONFIRMED,
        change="none. delete_removes_draft waits for step 8",
        match=lambda ctx: bool(ctx.get("ok"))),
    Signature(
        claim="delete_removes_draft", step="verify_cleanup",
        outcome="delete_never_happened", settles=False,
        we_send="GET /listings/{listing_id} after a deletion that failed",
        signal="the listing is still there and step 7 did not succeed",
        means=("the listing is present because nothing deleted it. Nothing is established "
               "about whether deletion works -- the failure was in step 7 and is classified "
               "there"),
        cause=ENVIRONMENT,
        change=("act on step 7's finding. The draft is named in `left_behind` and in the "
                "owner action for manual removal in Shop Manager"),
        match=lambda ctx: bool(ctx.get("present_after_failed_delete"))),
    Signature(
        claim="delete_removes_draft", step="verify_cleanup", outcome="delete_did_not_delete",
        we_send="DELETE, then GET /listings/{listing_id}",
        signal="the DELETE returned 204 and the GET returned 200 with the listing still there",
        means=("Etsy accepted a deletion it did not perform, or performs it eventually. "
               "Either way the shop holds a test artefact and the 204 was not evidence"),
        cause=ETSY_CONTRACT_DRIFT,
        change=("report the listing id and title as an owner action for Shop Manager, and "
                "make `delete_listing` read back and return the observed state rather than "
                "the status. Do not re-run until this is understood: each run would leave "
                "another draft"),
        match=lambda ctx: bool(ctx.get("still_present"))),
    Signature(
        claim="delete_removes_draft", step="verify_cleanup", outcome="delete_is_soft",
        we_send="DELETE, then GET /listings/{listing_id}",
        signal="the GET returns 200 with a state like 'removed', 'expired' or 'inactive'",
        means=("Etsy soft-deletes rather than removing. The listing is not a draft any more "
               "and is not reachable by buyers, which is a different kind of clean"),
        cause=ETSY_CONTRACT_DRIFT,
        change=("record the terminal state Etsy uses and change step 8's expectation from "
                "'404' to 'that state'. The sweep must then match on the title rather than "
                "on absence, or it will try to delete the same listing forever"),
        match=lambda ctx: bool(ctx.get("soft_deleted"))),
    Signature(
        claim="delete_removes_draft", step="verify_cleanup", outcome="deleted_and_gone",
        we_send="DELETE, then GET /listings/{listing_id}",
        signal="204, then 404",
        means=("the draft is gone and the shop is exactly as the run found it. This is also "
               "what makes every future shadow write reversible"),
        cause=CONFIRMED,
        change="none. delete_removes_draft becomes VERIFIED_AGAINST_ETSY",
        match=lambda ctx: bool(ctx.get("absent"))),
)


def classify(step: str, context: dict[str, Any]) -> dict[str, Any]:
    """Which signature this outcome is, or an explicit admission that the taxonomy is short.

    First match within the step wins, so the entries are ordered from most specific to least.
    An unmatched outcome returns `UNCLASSIFIED` with cause `None`, which is a defect **in this
    file** rather than an instruction to go and look: the whole point is that the run's output
    needs no interpretation, and an outcome nobody predicted means one more entry is owed.
    """
    for signature in TAXONOMY:
        if signature.step != step:
            continue
        try:
            if signature.match(context):
                return signature.to_dict()
        except Exception:   # noqa: BLE001 - a matcher must never decide the run's fate
            continue
    return {"claim": "", "step": step, "outcome": "UNCLASSIFIED", "cause": None,
            "we_send": "", "signal": str(context.get("error") or context.get("status") or ""),
            "means": ("this outcome is not in the taxonomy. That is a gap in "
                      "integrations.etsy_probe.TAXONOMY, not a question for the reader"),
            "change": ("add the signature, with its cause and its single change, before the "
                       "run is attempted again")}


# The things step 6 can find wrong, in the order they are reported. Each is classified on its
# own, because they are independent and a run that hits three of them owes three changes.
_CONTRACT_FLAGS = ("taxonomy_unreadable", "taxonomy_wrong", "taxonomy_remapped",
                   "required_properties", "tags_collapsed", "not_draft", "image_missing",
                   "mismatched", "not_returned")

# The confirming outcomes of the same step. Reported alongside the problems, because a run
# that found one thing wrong still established the others and those are facts worth keeping.
_CONTRACT_CONFIRMATIONS = ("tags_match", "verified")

# Which problem makes which confirmation meaningless. `verified` is a whole-listing verdict,
# so any problem contradicts it; a tags round trip stands on its own unless the tags were the
# problem. Stated as data because the alternative is a chain of conditions nobody can audit.
_SHADOWED_BY = {"verified": set(_CONTRACT_FLAGS),
                "tags_match": {"tags_collapsed", "mismatched", "not_returned"}}


def problems_shadowing(confirmation: str, problems: list[str]) -> bool:
    """Whether any problem in this run makes that confirmation unsafe to report."""
    return bool(_SHADOWED_BY.get(confirmation, set()) & set(problems))


def taxonomy_table() -> list[dict[str, Any]]:
    """The whole taxonomy as rows, for the report and for a document."""
    return [s.to_dict() for s in TAXONOMY]


# ---------------------------------------------------------------------------
# The test artefact


def png(width: int = 1, height: int = 1) -> bytes:
    """A solid PNG of the given size, built rather than stored.

    No binary file enters the repository and the bytes are provably an image rather than
    something renamed. Etsy's image requirements -- minimum dimensions, maximum size -- are on
    help.etsy.com, which refuses automated readers, so **whether Etsy accepts a 1x1 is exactly
    the sort of thing this run finds out.** If it refuses, the size is what changes, which is
    why this takes dimensions instead of being a constant.
    """
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return (len(data).to_bytes(4, "big") + body + zlib.crc32(body).to_bytes(4, "big"))

    raw = b"".join(b"\x00" + b"\x7f\x5a\x3c" * width for _ in range(height))
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", width.to_bytes(4, "big") + height.to_bytes(4, "big")
                 + bytes([8, 2, 0, 0, 0]))
    return header + ihdr + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def one_pixel_png() -> bytes:
    """The smallest thing that is unarguably an image. Kept as its own name because the
    taxonomy's `image_too_small` entry is about this specific choice."""
    return png(1, 1)


def test_payload(marker: str):
    """The draft this run creates: a real listing shape, unmistakably not a product.

    It goes through `build_payload`, which means it is checked against Etsy's character sets
    and limits exactly as a real listing would be. A probe that bypassed those checks would be
    exercising a path no product takes.

    The two tags are deliberate and they are the experiment: two tags, each containing a
    space and neither containing a comma, so that a comma-joined encoding Etsy misreads comes
    back as one tag rather than two and the read-back can see it.
    """
    return build_payload(
        title=f"{TEST_TITLE_PREFIX} {marker}",
        description=(
            "This is not a product. It is an automated transport test created by "
            "Brambleloop Studio's own software to verify that its Etsy integration can "
            "create a draft, attach an image and read the result back. It is a draft, it is "
            "not for sale, and the software deletes it immediately after the check. "
            f"Marker: {marker}."),
        price_cad=9.99,
        tags=["do not buy", "test draft"],
        materials=["test"],
    )


# ---------------------------------------------------------------------------
# The run


def _redactor_for(client: EtsyClient) -> Redactor:
    """Seed a redactor with every secret this process actually holds.

    Redacting by key name alone would pass through a token echoed inside an error message;
    redacting by value alone would miss a field whose value we never saw. Both, always.
    """
    redactor = Redactor()
    creds = getattr(client, "credentials", None)
    for attribute in ("api_key", "shared_secret", "access_token"):
        redactor.add(getattr(creds, attribute, ""))
    if creds is not None:
        redactor.add(f"{getattr(creds, 'api_key', '')}:{getattr(creds, 'shared_secret', '')}")
    provider = getattr(creds, "token_provider", None)
    tokens = getattr(provider, "tokens", None)
    for attribute in ("access_token", "refresh_token"):
        redactor.add(getattr(tokens, attribute, ""))
    return redactor


@dataclass
class _Run:
    """The record a run builds, kept as one object so no step can forget to report itself."""

    steps: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    left_behind: list[dict[str, Any]] = field(default_factory=list)

    def step(self, name: str, why: str) -> dict[str, Any]:
        entry: dict[str, Any] = {"step": name, "measures": why, "started_at": time.time()}
        self.steps.append(entry)
        return entry

    def classify(self, entry: dict[str, Any], step: str, context: dict[str, Any]) -> None:
        """Attach one finding to a step. Always a list, because step 6 produces several and a
        report whose shape depends on how many things went wrong is one nobody can parse."""
        finding = classify(step, context)
        entry.setdefault("classified", []).append(finding)
        self.findings.append(finding)


def _failure_context(client: EtsyClient, error: Exception, *,
                     ping_reachable: bool) -> dict[str, Any]:
    """What the classifier needs from a failed call: the status Etsy gave, and the text.

    The status comes from `client.calls`, which `_call` appends *before* it raises, so it is
    the real status rather than one parsed out of a message. A refusal raised before any
    request appends nothing, and the status is then 0 -- which is itself information, since it
    means this client stopped the call and Etsy never saw it.
    """
    last = client.calls[-1] if client.calls else {}
    return {"status": last.get("status", 0), "error": str(error),
            "operation": last.get("operation", ""), "ping_reachable": ping_reachable}


def sweep(client: EtsyClient, run: _Run, *, prefix: str = TEST_TITLE_PREFIX) -> dict[str, Any]:
    """Delete any test draft a previous run left behind. What makes this safe to run twice.

    A run that failed between the create and the delete left a draft in a real shop. Without
    this, the next run cannot see it and creates a second, and the shop accumulates artefacts
    indistinguishable from products with a mistake in them.

    It only ever looks at drafts (`state=draft` is the query Etsy filters on) and only ever at
    titles beginning with this module's own marker, so a product cannot be matched. A failure
    here does not stop the run: it is reported and the run continues, because the sweep is
    housekeeping and the evidence is the point.
    """
    entry = run.step("sweep", "that a draft left by an earlier run is removed before this one "
                             "starts, so running twice is safe and leaves one shop, not two")
    found: list[dict[str, Any]] = []
    try:
        for listing in client.get_shop_listings(state="draft"):
            title = str(listing.get("title") or "")
            if title.startswith(prefix):
                found.append({"listing_id": str(listing.get("listing_id") or ""),
                              "title": title})
    except (PermanentError, TransientError) as e:
        entry["ok"] = False
        entry["error"] = str(e)
        entry["note"] = ("the shop's drafts could not be listed, so this run cannot know "
                         "whether an earlier one left anything. It creates its own draft and "
                         "deletes it as usual")
        return entry

    removed, stuck = [], []
    for stale in found:
        try:
            if client.delete_listing(stale["listing_id"], expect_states=("draft",)):
                removed.append(stale)
            else:
                stuck.append(stale)
        except (PermanentError, TransientError) as e:
            stuck.append({**stale, "error": str(e)})
    run.left_behind.extend(stuck)
    entry["ok"] = not stuck
    entry["observed"] = {"stale_drafts_found": len(found), "removed": removed,
                         "could_not_remove": stuck}
    return entry


def run_exercise(client: EtsyClient, *, image: bytes | None = None,
                 image_filename: str = "brambleloop-transport-test.png",
                 pattern: bytes | None = None,
                 cleanup: bool = True,
                 ping_reachable: bool = True,
                 sweep_first: bool = True) -> dict[str, Any]:
    """Run the eight steps against whatever `client` points at, and report what happened.

    Returns a record rather than raising, at every step, because a partial run is the
    interesting case: a draft created and not deleted is a fact about a real shop, and a
    function that raised would leave the caller to guess whether that happened. The record
    always carries `left_behind` -- empty when the shop is clean -- so the answer is never
    absent.

    Every value in the returned record has been through the redactor.
    """
    run = _Run()
    report: dict[str, Any] = {
        "at": time.time(),
        "base_url": client.BASE,
        "phase": client.phase,
        "array_encoding": ARRAY_ENCODING,
        "taxonomy_id_sent": TAXONOMY_PATTERNS,
        "authority": {
            "read": client.refusal_for(Authority.READ) or "permitted",
            "draft_write": client.refusal_for(Authority.DRAFT_WRITE) or "permitted",
            "activate": client.refusal_for(Authority.ACTIVATE) or "permitted",
        },
        "steps": run.steps,
        "findings": run.findings,
        "listing_id": None,
        "cleaned_up": None,
        "cleanup_verified": None,
        "verified": False,
        "left_behind": run.left_behind,
        "activation_attempted": False,   # stays false. See the module docstring.
    }
    redactor = _redactor_for(client)
    image = image if image is not None else one_pixel_png()
    marker = uuid.uuid4().hex[:10]
    title = f"{TEST_TITLE_PREFIX} {marker}"

    def finish(stopped_at: str | None = None) -> dict[str, Any]:
        if stopped_at:
            report["stopped_at"] = stopped_at
        for step in run.steps:
            step["seconds"] = round(time.time() - step.pop("started_at", time.time()), 3)
        report["against_etsy"] = against_etsy(client)
        report["claims"] = claims(run.findings, etsy=report["against_etsy"])
        report["evidence_note"] = (
            "requests went to openapi.etsy.com; CONFIRMED findings are observations of Etsy"
            if report["against_etsy"] else
            f"requests went to {client.BASE}, which is not Etsy. Every CONFIRMED finding "
            f"below is evidence about this system's own correctness against our reading of "
            f"Etsy's document, and promotes nothing to VERIFIED_AGAINST_ETSY.")
        report["shop_is_clean"] = not run.left_behind
        if run.left_behind:
            report["owner_action"] = {
                "action": "delete a test draft this run could not remove",
                "where": "Etsy Shop Manager, Listings, Drafts",
                "listings": list(run.left_behind),
                "why": ("a test artefact left in a real shop is indistinguishable from a "
                        "product with a mistake in it"),
                "maximum_cost": "CA$0", "minutes": 2}
        return redactor(report)

    # -- 0b. Sweep, before anything is created. -----------------------------
    if sweep_first:
        sweep(client, run)

    # -- 1. Authenticated identity and shop read. ---------------------------
    entry = run.step("identity",
                     "that the OAuth grant produced a usable token, that Etsy knows who we "
                     "are, and that ETSY_SHOP_ID names a shop we can read")
    try:
        me = client.get_me()
        shop = client.get_shop()
        entry["ok"] = True
        # The shop name and the user id are the owner's business identity. That a shop was
        # read is the evidence; the identity is not, so only its shape is recorded.
        entry["observed"] = {
            "identity_returned": bool(me),
            "shop_returned": bool(shop),
            "shop_id_matches": str(shop.get("shop_id") or "") == str(
                getattr(client.credentials, "shop_id", "")),
            "fields": sorted(k for k in shop)[:12]}
        run.classify(entry, "identity", {"ok": True, "status": 200})
    except (PermanentError, TransientError) as e:
        entry["ok"] = False
        entry["error"] = str(e)
        run.classify(entry, "identity", _failure_context(client, e,
                                                         ping_reachable=ping_reachable))
        return finish("identity")

    # -- 2. Create the clearly marked test draft. ---------------------------
    entry = run.step("create_draft",
                     "that Etsy accepts a form-encoded createDraftListing and returns an id")
    sent: dict[str, Any] = {}
    try:
        payload = test_payload(marker)
        sent = payload.to_dict()
        sent.pop("state", None)
        listing_id = client.create_draft(payload)
        report["listing_id"] = listing_id
        report["listing_title"] = title
        # From here on the shop holds something. It is recorded as left behind immediately and
        # removed when the cleanup succeeds, so an exception anywhere below cannot lose it.
        run.left_behind.append({"listing_id": listing_id, "title": title})
        entry["ok"] = True
        entry["observed"] = {"listing_id": listing_id,
                             "encoding_sent": client.calls[-1]["encoding"],
                             "fields_sent": sorted(sent)}
        run.classify(entry, "create_draft", {"ok": True, "status": 201})
    except (PermanentError, TransientError) as e:
        entry["ok"] = False
        entry["error"] = str(e)
        context = _failure_context(client, e, ping_reachable=ping_reachable)
        run.classify(entry, "create_draft", context)
        # A create refused for a property id is the one failure whose diagnosis is a free
        # read, and the answer decides whether this is a one-line change or a build task. It
        # would be perverse to make somebody run this again to find out.
        if "propert" in str(e).lower() or "taxonom" in str(e).lower():
            entry["diagnosis"] = _taxonomy_diagnosis(client)
        return finish("create_draft")

    # -- 3. Upload the image. -----------------------------------------------
    entry = run.step("upload_image",
                     "that a multipart part named `image` reaches Etsy and becomes a listing "
                     "image -- what a draft needs before it could ever be activated")
    image_id = None
    try:
        uploaded = client.upload_image(
            listing_id, filename=image_filename, data=image, rank=1,
            alt_text="Automated transport test image. Not a product photograph.")
        image_id = uploaded.get("listing_image_id")
        entry["ok"] = True
        entry["observed"] = {"listing_image_id": image_id,
                             "encoding_sent": client.calls[-1]["encoding"],
                             "image_bytes": len(image)}
        run.classify(entry, "upload_image", {"ok": True, "status": 201})
    except (PermanentError, TransientError) as e:
        entry["ok"] = False
        entry["error"] = str(e)
        run.classify(entry, "upload_image",
                     _failure_context(client, e, ping_reachable=ping_reachable))

    # 3b. The digital file, only if the caller supplied bytes. Optional because the pattern
    # PDF is a release artefact and this run must not need one to happen.
    if pattern:
        entry = run.step("upload_file",
                         "that a multipart part named `file` attaches the digital download")
        try:
            entry["ok"] = client.attach_file(listing_id,
                                             filename=f"transport-test-{marker}.pdf",
                                             data=pattern)
        except (PermanentError, TransientError) as e:
            entry["ok"] = False
            entry["error"] = str(e)

    # -- 4. Update permitted draft fields. ----------------------------------
    entry = run.step("update_listing",
                     "that a form-encoded PATCH changes the fields it names, and only those")
    update: dict[str, Any] = {"title": f"{title} updated",
                              "tags": ["do not buy", "test draft", "updated"]}
    try:
        client.update_listing(listing_id, update)
        entry["ok"] = True
        entry["observed"] = {"fields": sorted(update),
                             "encoding_sent": client.calls[-1]["encoding"]}
        run.classify(entry, "update_listing", {"ok": True, "status": 200})
    except (PermanentError, TransientError) as e:
        entry["ok"] = False
        entry["error"] = str(e)
        run.classify(entry, "update_listing",
                     _failure_context(client, e, ping_reachable=ping_reachable))
        update = {}

    # 4b. Prove the refusals are refusals, not documentation. Free: nothing is sent.
    entry = run.step("refusals_hold",
                     "that price cannot be sent to updateListing, that state cannot be set "
                     "through it, and that activation refuses without a Launch-0 authorisation")
    observed: dict[str, Any] = {}
    for label, call in (
            ("price_refused", lambda: client.update_listing(listing_id, {"price": 1.0})),
            ("state_refused", lambda: client.update_listing(listing_id, {"state": "active"})),
            ("activation_refused", lambda: client.activate(listing_id)),
    ):
        try:
            call()
            observed[label] = "NOT REFUSED -- this is a defect in the gate"
        except (EtsyRejected, EtsyNotPermitted) as e:
            observed[label] = str(e)[:140]
    entry["ok"] = all("NOT REFUSED" not in v for v in observed.values())
    entry["observed"] = observed

    # -- 5. Read it back from Etsy. A separate request. ---------------------
    entry = run.step("read_back",
                     "that the listing Etsy holds matches what we sent, that it is still a "
                     "draft, and that Etsy has the image")
    remote: dict[str, Any] = {}
    result = None
    try:
        remote = client.get_listing(listing_id)
        expected = {**sent, **update}
        result = verify(expected, remote, listing_id=listing_id, expect_state="draft",
                        expect_images=1 if image_id else 0)
        report["verified"] = result.verified
        report["read_back"] = result.summary()
        entry["ok"] = result.verified
        entry["observed"] = result.summary()
    except (PermanentError, TransientError) as e:
        entry["ok"] = False
        entry["error"] = str(e)

    # -- 6. Verify taxonomy, properties, encoding and remote values. --------
    # Nothing above this line is evidence about content. A 201 says Etsy accepted a request;
    # this step is where what Etsy actually holds is compared with what we meant.
    entry = run.step("verify_contract",
                     "that the taxonomy node is the one we think it is, that it requires no "
                     "listing property we cannot set, that our array encoding survived the "
                     "round trip, and that the remote values are the ones we sent")
    context: dict[str, Any] = {"ping_reachable": ping_reachable}
    try:
        diagnosis = _taxonomy_diagnosis(client)
        sent_tags = list(update.get("tags") or sent.get("tags") or [])
        remote_tags = remote.get("tags") if isinstance(remote.get("tags"), list) else []
        remote_taxonomy = remote.get("taxonomy_id")
        context.update({
            "taxonomy_wrong": bool(diagnosis.get("node_wrong")),
            "taxonomy_unreadable": bool(diagnosis.get("node_error")
                                        or diagnosis.get("properties_error")),
            "taxonomy_remapped": (remote_taxonomy is not None
                                  and str(remote_taxonomy) != str(TAXONOMY_PATTERNS)),
            "required_properties": bool(diagnosis.get("required_properties")),
            # The silent failure: two tags sent, one tag held, and that one tag is the two
            # joined by a comma. No status code anywhere in the run says so.
            "tags_collapsed": (len(sent_tags) > 1 and len(remote_tags) == 1
                               and "," in str(remote_tags[0])),
            "tags_match": (bool(sent_tags)
                           and [str(t).strip() for t in remote_tags] ==
                           [str(t).strip() for t in sent_tags]),
            "image_missing": bool(image_id) and not (remote.get("images") or []),
            "not_draft": str(remote.get("state") or "").lower() not in ("", "draft"),
            "mismatched": bool(result.mismatches) if result is not None else False,
            "not_returned": bool(result.unverifiable) if result is not None else False,
            # The whole-listing verdict, and it requires the image. A listing whose fields all
            # match but which carries no image is a draft Etsy will never activate, so
            # reporting it as a confirmation of the write path would confirm the exact state
            # this module was written to make visible.
            "verified": (bool(result.verified) and bool(image_id)
                         and bool(remote.get("images")) if result is not None else False),
        })
        entry["observed"] = {
            "taxonomy": diagnosis,
            "taxonomy_id_on_etsy": remote_taxonomy,
            "array_encoding_sent": ARRAY_ENCODING,
            "tags_sent": sent_tags,
            "tags_on_etsy": remote_tags,
            "state_on_etsy": remote.get("state"),
            "images_on_etsy": len(remote.get("images") or []),
        }
        entry["ok"] = bool(context["verified"] and not context["taxonomy_wrong"]
                           and not context["taxonomy_unreadable"]
                           and not context["taxonomy_remapped"]
                           and not context["required_properties"])
        # Every true flag is classified on its own, so a run with three problems reports
        # three findings and three changes rather than whichever one matched first. The
        # context handed to each is that flag alone: a classifier given all of them would
        # return the earliest entry in the table every time.
        problems = [flag for flag in _CONTRACT_FLAGS if context[flag]]
        # A run with one problem still confirmed everything else, and those confirmations are
        # the evidence this whole exercise exists to collect. Reporting only the problems
        # would throw away a fact about Etsy because something unrelated went wrong.
        confirmations = [flag for flag in _CONTRACT_CONFIRMATIONS
                         if context[flag] and not problems_shadowing(flag, problems)]
        found: list[dict[str, Any]] = []
        for flag in problems + confirmations:
            finding = classify("verify_contract", {flag: True,
                                                   "ping_reachable": ping_reachable})
            run.findings.append(finding)
            found.append(finding)
        entry["classified"] = found
    except (PermanentError, TransientError) as e:
        entry["ok"] = False
        entry["error"] = str(e)
        run.classify(entry, "verify_contract",
                     _failure_context(client, e, ping_reachable=ping_reachable))

    # -- 7. Delete the test draft. ------------------------------------------
    if not cleanup:
        report["cleaned_up"] = False
        report["note"] = (f"cleanup was not requested; draft {listing_id} remains in the "
                          f"shop and is named in left_behind.")
        return finish()

    entry = run.step("cleanup",
                     "that the test artefact is gone from the shop, and that the delete "
                     "refuses if the listing is not the draft we expect")
    deleted = False
    try:
        deleted = bool(client.delete_listing(listing_id, expect_states=("draft",)))
        report["cleaned_up"] = deleted
        entry["ok"] = deleted
        run.classify(entry, "cleanup", {"ok": deleted, "status": 204})
    except (PermanentError, TransientError) as e:
        report["cleaned_up"] = False
        entry["ok"] = False
        entry["error"] = str(e)
        run.classify(entry, "cleanup", _failure_context(client, e,
                                                        ping_reachable=ping_reachable))
        entry["owner_action"] = (
            f"listing {listing_id} still exists in the shop as a draft and this run could "
            f"not remove it. Delete it in Shop Manager: it is titled '{title}'.")

    # -- 8. Verify the cleanup. ---------------------------------------------
    # The 204 above is Etsy accepting the request. Whether the listing is gone is a different
    # claim and this is the only thing in the run that settles it.
    entry = run.step("verify_cleanup",
                     "that Etsy no longer holds the listing -- the claim a 204 does not make")
    try:
        exists, state = client.listing_exists(listing_id)
        report["cleanup_verified"] = not exists
        entry["ok"] = not exists
        entry["observed"] = {"still_on_etsy": exists, "state": state}
        if not exists:
            run.left_behind[:] = [row for row in run.left_behind
                                  if row.get("listing_id") != listing_id]
        else:
            entry["owner_action"] = (
                f"Etsy still holds listing {listing_id} ('{title}') in state {state!r} after "
                f"a delete it accepted. Remove it in Shop Manager.")
        # `deleted` matters here. A listing still present after a delete Etsy *accepted* is a
        # finding about Etsy; a listing still present after a delete that failed is the
        # failure already classified in step 7, and reporting it twice under two different
        # causes would be worse than reporting it once.
        run.classify(entry, "verify_cleanup", {
            "absent": not exists,
            "present_after_failed_delete": exists and not deleted,
            "still_present": exists and deleted and state.lower() in ("draft", "active", ""),
            "soft_deleted": exists and deleted and state.lower() not in ("draft", "active",
                                                                         ""),
            "state": state, "ping_reachable": ping_reachable})
    except (PermanentError, TransientError) as e:
        report["cleanup_verified"] = False
        entry["ok"] = False
        entry["error"] = str(e)
        run.classify(entry, "verify_cleanup",
                     _failure_context(client, e, ping_reachable=ping_reachable))

    return finish()


def _taxonomy_diagnosis(client: EtsyClient) -> dict[str, Any]:
    """Read Etsy's taxonomy tree and the node's properties. Two reads, CA$0, no writes.

    Run at step 6 normally, and immediately on a create failure that mentions a property or a
    taxonomy, because in that case these two reads are the whole answer and making somebody
    start again to get them would waste the credentials this run exists to spend well.
    """
    out: dict[str, Any] = {"taxonomy_id_sent": TAXONOMY_PATTERNS}
    try:
        node = client.get_taxonomy_node(TAXONOMY_PATTERNS)
        out["node"] = {"id": node.get("id"), "name": node.get("name"),
                       "level": node.get("level")} if node else None
        name = str(node.get("name") or "").lower() if node else ""
        out["node_wrong"] = (not node) or ("pattern" not in name)
        out["candidates"] = client.find_taxonomy_nodes("pattern")[:12]
    except (PermanentError, TransientError) as e:
        out["node_error"] = _blocked(str(e), "getSellerTaxonomyNodes")
    try:
        properties = client.get_taxonomy_properties(TAXONOMY_PATTERNS)
        out["required_properties"] = [
            {"property_id": p.get("property_id"), "name": p.get("name")}
            for p in properties if p.get("is_required")]
        out["properties_read"] = len(properties)
    except (PermanentError, TransientError) as e:
        out["properties_error"] = _blocked(str(e), "getPropertiesByTaxonomyId")
    # Absent rather than false: a check that could not run has not passed. `verify_contract`
    # reads these as flags, and a missing key is not a true one, so a failed diagnosis never
    # accuses the taxonomy of being wrong.
    return out


def _blocked(error: str, operation: str) -> str:
    """Name the fix when a read is refused for a reason that is not Etsy's.

    `etsy_oauth.SCOPES_REQUIRED` is the map of Etsy operation to scope, and `missing_scopes`
    refuses an operation that is not in it rather than guessing. That module belongs to
    another lane, so the two taxonomy reads this run needs can be blocked by a file this
    department may not edit -- and the failure would otherwise read as "the taxonomy could not
    be checked", which is true and useless.
    """
    if "unknown Etsy operation" in error:
        return (f"{error} FIX: add `\"{operation}\": (),` to etsy_oauth.SCOPES_REQUIRED. "
                f"Etsy's seller-taxonomy endpoints carry root-level api_key security in the "
                f"OpenAPI document, so the tuple is empty -- the same as getShop and "
                f"getListing. Until it is there this run cannot read the taxonomy back, and "
                f"the taxonomy_patterns_id and taxonomy_required_properties claims stay "
                f"IMPLEMENTED however well everything else goes.")
    return error


# ---------------------------------------------------------------------------
# What the run may and may not conclude


ETSY_HOST = "https://openapi.etsy.com"


def against_etsy(client: EtsyClient) -> bool:
    """Whether this run's requests actually went to Etsy.

    The single condition on which VERIFIED_AGAINST_ETSY depends. `EtsyClient.BASE` defaults to
    Etsy and only a test overrides it, so this is false for every run against
    `tests/fake_etsy.py` -- which is the point: the local suite must be unable to promote a
    claim no matter how green it is, and the check is a property of where the bytes went
    rather than of who is asking.
    """
    return str(client.BASE).startswith(ETSY_HOST)


def claims(findings: list[dict[str, Any]], *,
           etsy: bool = False) -> list[dict[str, Any]]:
    """Every claim's state before and after this run. The three states, kept apart.

    A claim moves to VERIFIED_AGAINST_ETSY only when **both** are true: this run's requests
    went to `openapi.etsy.com`, and it produced the CONFIRMED signature for that claim -- the
    specific discriminating observation, not a 201 and not a green test suite. A run against
    the local fake produces exactly the same findings and promotes nothing, because one
    successful fake-shop run is not evidence of Etsy's behaviour.

    A claim this run contradicted is marked `CONTRADICTED` rather than being quietly demoted,
    because the difference between "we have not checked" and "we checked and it was wrong" is
    the difference between a task and a defect. A claim whose check could not be made keeps
    its state and says so.

    This function does not write the matrix. Promoting a claim in
    `publish/listing_schema.py` means a human pasting the observation into
    `ETSY_VERIFIED_FACTS`, which is deliberate: a state that a program can grant itself is a
    state that means nothing.
    """
    confirmed = {f["claim"] for f in findings
                 if f.get("cause") == CONFIRMED and f.get("claim") and f.get("settles", True)}
    contradicted = {f["claim"]: f for f in findings
                    if f.get("cause") in (OUR_BUG, ETSY_CONTRACT_DRIFT) and f.get("claim")
                    and f.get("settles", True)}
    blocked = {f["claim"] for f in findings
               if not f.get("settles", True) and f.get("claim")}
    out: list[dict[str, Any]] = []
    for row in listing_schema.verification_matrix():
        claim = row["claim"]
        after = row["state"]
        note = "unchanged by this run"
        if claim in contradicted:
            after = "CONTRADICTED"
            note = (f"this run produced {contradicted[claim]['outcome']}: "
                    f"{contradicted[claim]['change']}")
        elif claim in confirmed and row["state"] != listing_schema.VERIFIED_AGAINST_ETSY:
            if etsy:
                after = listing_schema.VERIFIED_AGAINST_ETSY
                note = ("observed against openapi.etsy.com in this run; paste the "
                        "observation into listing_schema.ETSY_VERIFIED_FACTS to make it "
                        "durable")
            else:
                note = ("this run confirmed the claim against a local model of Etsy, which "
                        "is our reading of Etsy's document and not Etsy. The state does not "
                        "move: LOCALLY_TESTED is what a green local suite establishes, and "
                        "no number of those adds up to one observation of Etsy")
        elif claim in blocked:
            note = ("this run could not look: the state is unchanged, which is not the same "
                    "as the claim holding")
        out.append({"claim": claim, "state_before": row["state"], "state_after": after,
                    "blocks_launch": row["blocks_launch"], "note": note,
                    "graduates_by": row["graduates_by"]})
    return out


# ---------------------------------------------------------------------------
# The operator entry point


def main(argv: list[str] | None = None) -> int:
    """Run the exercise against the real shop, or explain precisely why it cannot.

    Writes nothing to the repository and prints no secret. What it prints is a record of what
    was measured, which is the thing the deliverable needs and the thing a token is not.

    `--taxonomy` prints the failure taxonomy and exits without touching the network, so the
    table can be read and reviewed before anybody spends the one attempt.
    """
    argv = argv if argv is not None else sys.argv[1:]
    env = os.environ

    if "--taxonomy" in argv:
        print(json.dumps({"taxonomy": taxonomy_table(),
                          "causes": list(CAUSES),
                          "verification_matrix": listing_schema.verification_matrix(),
                          "verification_summary": listing_schema.verification_summary()},
                         indent=2, default=str))
        return 0

    from .http import UrllibTransport, probe_live

    transport = UrllibTransport()
    credentials = Credentials.from_env(env, transport=transport)

    report: dict[str, Any] = {"at": time.time(),
                              "verification_summary": listing_schema.verification_summary()}

    # 0. Ping, always. It needs no OAuth token, it is the one fact available without an owner
    # action, and its result is what tells the classifier whether a later failure is the
    # network rather than the request.
    report["ping"] = probe_live(
        credentials.api_key_header() if credentials is not None else "", transport)
    reachable = bool(report["ping"].get("reachable"))

    if credentials is None:
        from .etsy_oauth import OAuthApp, owner_action
        report["status"] = "NOT EXERCISED -- no Etsy credentials in this environment"
        report["owner_action"] = owner_action(OAuthApp.from_env(env))
        report["when_credentials_arrive"] = (
            "this module runs the eight steps in order and classifies every outcome against "
            "TAXONOMY, so the run costs one attempt. `--taxonomy` prints that table without "
            "touching the network.")
        print(json.dumps(report, indent=2, default=str))
        return 2

    if env.get("ETSY_SHADOW_WRITE", "") != "1":
        client = EtsyClient(transport, credentials=credentials,
                            phase=env.get("BRAMBLELOOP_PHASE", "shadow"))
        try:
            shop = client.get_shop()
            report["read_shop"] = {"ok": True, "fields": sorted(shop)[:12]}
        except (PermanentError, TransientError) as e:
            report["read_shop"] = {"ok": False, "error": str(e)}
        report["status"] = ("READ ONLY -- set ETSY_SHADOW_WRITE=1 to let this run create "
                            "and then delete one draft in the real shop. No listing is ever "
                            "activated and no fee is incurred either way.")
        print(json.dumps(_redactor_for(client)(report), indent=2, default=str))
        return 0

    client = EtsyClient(transport, credentials=credentials,
                        phase=env.get("BRAMBLELOOP_PHASE", "shadow"),
                        shadow_writes_authorised=True)
    report["exercise"] = run_exercise(client, cleanup="--keep" not in argv,
                                      ping_reachable=reachable)
    report["status"] = ("EXERCISED against openapi.etsy.com"
                        if report["exercise"].get("verified")
                        else "ATTEMPTED -- see steps and findings for what failed")
    print(json.dumps(_redactor_for(client)(report), indent=2, default=str))
    ok = report["exercise"].get("verified") and report["exercise"].get("shop_is_clean")
    return 0 if ok else 1


if __name__ == "__main__":   # pragma: no cover - operator entry point
    raise SystemExit(main())
