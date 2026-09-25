"""Etsy OAuth 2.0: the authorization-code grant with PKCE, and the refresh that keeps it.

Why this exists. Until now `Credentials.from_env` read a static `ETSY_ACCESS_TOKEN` and that
was the whole authentication story. Etsy's access token lives **one hour**. So a static token
is a system that works for the first hour after a human pasted it and then fails, and it
fails in the most expensive possible way: not on the day of the launch, when somebody is
watching, but on the second day, with a 401 that looks exactly like a revoked app.

Everything in this module about Etsy's flow is SOURCED. Read on 2026-09-25 from
`https://developer.etsy.com/documentation/essentials/authentication/` (HTTP 200 from this
environment) and from Etsy's OpenAPI description's `securitySchemes.oauth2` block. The
quotes are kept next to the code they justify, because a constant with a URL in it is
unfalsifiable and a constant with Etsy's sentence beside it is not.

**The two-host discrepancy, resolved 2026-09-25.** Etsy's authentication page gives the token
endpoint as `https://api.etsy.com/v3/public/oauth/token`; Etsy's OpenAPI description's
`oauth2.flows.authorizationCode.tokenUrl` gives `https://openapi.etsy.com/v3/public/oauth/token`.
Both were read again today and both still say what they said. What was missing was a third
Etsy page, "Request Standards", which answers the question directly:

    "Etsy API endpoints are accessible at URLs starting with https://api.etsy.com/v3/ or
     https://openapi.etsy.com/v3/ ... The two hostnames are equivalent and you can use
     either."

(`https://developers.etsy.com/documentation/essentials/requests/`, fetched HTTP 200 from this
environment on 2026-09-25.) So the documents were never in conflict about behaviour, only
about which of two interchangeable names to print. `TOKEN_URL` stays the authentication
page's host because that is the page about tokens, `TOKEN_URL_ALTERNATE` stays, and the 404
retry stays -- it now costs nothing in the expected case and still covers the one reading
this cannot rule out, which is that the equivalence is stated of `/v3/` *API* endpoints and
`/v3/public/oauth/token` might be served differently. **Neither host has been exercised**: no
token request has ever been made from this system, because there is no registered app and no
authorization code.

What is not here, deliberately: nothing writes a token to disk, and nothing in this module
knows what a database is. The refreshed token lives in the process and is handed back to the
caller through `on_refresh`, so where it is persisted stays the deployment's decision and
cannot accidentally become this repository (CLAUDE.md). What that decision turned out to be
is in `core.oauth_store` and `core.sealed`: sealed in Postgres under a key held in the
environment, because Etsy rotates the refresh token hourly and a process cannot rewrite the
environment it was started with. The flow that drives this module across a browser round trip
is `integrations.etsy_authorise`, and the endpoint the owner's browser lands on is
`GET /api/etsy/oauth/callback`.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from ..core.resilience import PermanentError, TransientError, classify_http

# SOURCED: "direct the user to https://www.etsy.com/oauth/connect with a GET request"
AUTHORIZE_URL = "https://www.etsy.com/oauth/connect"

# SOURCED: "make a POST request to https://api.etsy.com/v3/public/oauth/token with the
# following parameters in the request body in application/x-www-form-urlencoded format"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"

# SOURCED: Etsy's OpenAPI description's `oauth2.flows.authorizationCode.tokenUrl`. It names
# the other host, and Etsy's Request Standards page says the two are equivalent -- see the
# module docstring. Kept as a named constant with its own sentence rather than deleted,
# because "we established they are the same" is a fact somebody will want to re-check.
TOKEN_URL_ALTERNATE = "https://openapi.etsy.com/v3/public/oauth/token"

# SOURCED, `https://developers.etsy.com/documentation/essentials/requests/`, 2026-09-25:
# "The two hostnames are equivalent and you can use either."
TOKEN_HOSTS_ARE_EQUIVALENT = (
    "Etsy's Request Standards page states that api.etsy.com and openapi.etsy.com are "
    "equivalent hostnames for v3 endpoints, which is why two Etsy documents print different "
    "hosts for one token endpoint. Read 2026-09-25; not exercised, because no token request "
    "has ever been made from this system.")

# SOURCED: "which has a functional life of 1 hour" / "expires_in ... 3600 seconds is 1 hour".
ACCESS_TOKEN_SECONDS = 3600

# SOURCED: "has a longer functional lifetime (90 days)". Not enforced here -- Etsy enforces
# it -- but it is the clock behind the owner action this module can raise.
REFRESH_TOKEN_DAYS = 90

# Refresh this many seconds before expiry. A token that expires during the flight of a
# request is a token that was valid when we checked it, so checking is not enough.
EXPIRY_SKEW_SECONDS = 120

# SOURCED: the scope table on Etsy's authentication page, and each write operation's
# `security` block in the OpenAPI description.
SCOPE_MEANINGS = {
    "listings_r": "read a member's inactive and expired (i.e., non-public) listings",
    "listings_w": "create and edit a member's listings",
    "listings_d": "delete a member's listings",
    "shops_r": "see a member's shop description, messages and sections",
    "shops_w": "update a member's shop description, messages and sections",
    "transactions_r": "read a member's purchase and sales data",
}

# What this company's Etsy work actually needs, per operation, from each operation's own
# `security` block. Asking for more than this is asking the owner to grant more than we use,
# and Etsy's own advice is that "users are generally less likely to authorize an application
# that makes a request for more scopes than it requires".
SCOPES_REQUIRED = {
    "createDraftListing": ("listings_w",),
    "updateListing": ("listings_w",),
    "uploadListingImage": ("listings_w",),
    "uploadListingFile": ("listings_w",),
    "deleteListing": ("listings_d",),
    "getListingsByShop": ("listings_r",),
    "getShop": (),           # root-level api_key only
    "getListing": (),        # root-level api_key only
    "getMe": ("shops_r",),
    "updateShop": ("shops_w",),
    # The two taxonomy reads step 6 of the authenticated exercise needs. Empty for the same
    # reason `getShop` and `getListing` are: Etsy's document gives both root-level `api_key`
    # security. That reading is UNVERIFIED like every other write-path claim here, and it is
    # the safest possible way to be wrong -- an empty tuple requests no new scope, so if Etsy
    # actually wants one the call returns a 403 naming it, which the exercise's failure
    # taxonomy already classifies as ENVIRONMENT with the owner re-authorisation to match.
    # Without these two entries `missing_scopes` refuses an operation it has never heard of
    # (correctly: it will not guess), and step 6 is skipped as `taxonomy_unreadable`.
    "getSellerTaxonomyNodes": (),
    "getPropertiesByTaxonomyId": (),
}

# The set this system asks for. `listings_d` is in it because the shadow-safe exercise
# deletes the test draft it created, and a test artefact we cannot remove is a test artefact
# that stays in the shop.
SCOPES_WANTED = ("listings_r", "listings_w", "listings_d", "shops_r", "shops_w")

# SOURCED, RFC 7636 via Etsy: "a code verifier, which must be a high-entropy random string
# consisting of between 43 and 128 characters from the range [A-Za-z0-9._~-]".
VERIFIER_MIN = 43
VERIFIER_MAX = 128

# SOURCED, the authentication page's "state" row, 2026-09-25: "(Recommended) A single-use
# token generated specifically for a given request. It is important that the state parameter
# is impossible to guess, associated with a specific request, and used once. When present, it
# must be non-empty" -- and, after a successful redirect, "make a note never to use that
# state again". So `state` is *recommended* rather than required for a PKCE client ("OAuth
# 2.1 clients relying on PKCE for CSRF protection may omit state, but including it is still
# best practice"), and every property this system enforces about it -- unguessable, bound to
# one request, single-use -- is Etsy's own list rather than this company's invention.
STATE_IS_REQUIRED_BY_ETSY = False

# 32 bytes of CSPRNG output. `secrets`, never `random`.
STATE_BYTES = 32

# SOURCED, the authentication page's "Redirect URIs" section, 2026-09-25: "URL matching is
# case-sensitive and is specifically the URL established when you registered", and each of
# these fails to match a registered `https://www.example.com/some/location`: `http://...`,
# a trailing slash, a trailing question mark, an uppercase `H` in `Https`, and a missing
# `www`. Quoted because a redirect URI that is one character out produces an error page in
# front of the owner and no callback at all, which is the failure hardest to diagnose from
# the server side -- nothing reaches the server.
REDIRECT_URI_MATCHING = (
    "exact and case-sensitive against the URL registered at etsy.com/developers/your-apps. "
    "A trailing slash, a trailing '?', an uppercase scheme, http instead of https, or a "
    "missing subdomain are all different URLs and all fail.")


def new_state() -> str:
    """A fresh OAuth state: unguessable, and used once.

    `secrets`, not `random`. `random` is a Mersenne Twister seeded from the clock and 624 of
    its outputs determine every output after them, which is exactly the property a value
    guarding against cross-site request forgery must not have.
    """
    return secrets.token_urlsafe(STATE_BYTES)


def parse_redirect(params: dict[str, Any]) -> dict[str, str]:
    """Read what Etsy put on the redirect, and classify it, without deciding anything.

    SOURCED, the authentication page, Step 2 and Errors: a successful redirect carries `code`
    and `state`; an unsuccessful one carries `error` (an RFC 6749 code), `error_description`
    ("always in English"), an optional `error_uri`, and `state` if the request included one.

    Returns a dict with `kind` set to `code`, `error` or `unusable`, so the caller has one
    thing to branch on. The error text is truncated and passed through unchanged otherwise:
    it is attacker-influencable text arriving on a URL, so whoever renders it escapes it, and
    nothing here treats it as trustworthy.
    """
    def one(name: str) -> str:
        value = params.get(name)
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        return str(value or "").strip()

    state, code, error = one("state"), one("code"), one("error")
    if error:
        return {"kind": "error", "state": state, "code": "", "error": error[:80],
                "error_description": one("error_description")[:300],
                "error_uri": one("error_uri")[:300]}
    if code:
        return {"kind": "code", "state": state, "code": code, "error": "",
                "error_description": "", "error_uri": ""}
    return {"kind": "unusable", "state": state, "code": "",
            "error": "no_code_and_no_error",
            "error_description": ("Etsy sends either a code or an error to the redirect URI; "
                                  "this request carried neither, so it did not come from an "
                                  "Etsy authorization."),
            "error_uri": ""}


class EtsyAuthFailed(PermanentError):
    """Etsy refused the token request. Retrying sends the same proof and gets the same no."""


class EtsyAuthNeedsOwner(PermanentError):
    """Only a human with a browser can fix this: there is no code path around it.

    Raised rather than worked around. An expired refresh token, a revoked app and a scope
    that was never granted all land here, and all three end at the same place -- the owner
    opening `authorize_url()` and approving the app.
    """


class EtsyRedirectError(EtsyAuthFailed):
    """Etsy redirected with an error instead of a code, or with nothing usable at all.

    Its own class because the three outcomes end differently: a code is exchanged, an
    `error=access_denied` is the owner declining and needs no fix, and a redirect carrying
    neither did not come from an Etsy authorization at all.
    """


def redirect_uri_problem(redirect_uri: str) -> str:
    """Why this redirect URI cannot be the registered one, or "" if nothing is visibly wrong.

    Only Etsy can say whether a URI *matches* what was registered -- and it says so by
    showing the owner an error page and never calling the callback, which is the failure
    mode hardest to diagnose from a server that never hears about it. What can be checked
    here is the class of URI Etsy documents as always failing, and checking it costs nothing.
    """
    value = (redirect_uri or "").strip()
    if not value:
        return ("no redirect URI. ETSY_REDIRECT_URI is read from the environment and is "
                "empty, so there is no callback for Etsy to send the authorization code to.")
    if value != redirect_uri:
        return ("the redirect URI has leading or trailing whitespace. Etsy matches character "
                "for character, so this is a different URL from the registered one.")
    if not value.startswith("https://"):
        return (f"the redirect URI must begin with `https://` ({REDIRECT_URI_MATCHING}). "
                f"Etsy: 'The URL must have the https:// prefix or the request will fail.'")
    if "#" in value:
        return ("the redirect URI carries a fragment. A fragment is never sent to a server "
                "and cannot be part of a registered callback.")
    if value.endswith("?"):
        return ("the redirect URI ends with '?', which Etsy's own examples list as a string "
                "that fails to match a registration without one.")
    return ""


def fingerprint(secret: str) -> str:
    """Eight hex characters of a SHA-256, so two tokens can be told apart in a log.

    Never the token, never a prefix of the token. Etsy's tokens carry the granting user's
    numeric id as a prefix, so even "the first eight characters" would publish an identifier.
    """
    if not secret:
        return "absent"
    return hashlib.sha256(secret.encode()).hexdigest()[:8]


def new_verifier() -> str:
    """A PKCE code verifier: 32 bytes of CSPRNG output in URL-safe base64, unpadded.

    Etsy: "You can generate an appropriate verifier using a cryptographically secure source
    of randomness and encode 32 bytes of random data into url-safe base 64." That yields 43
    characters, which is exactly the documented minimum.
    """
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")


def challenge(verifier: str) -> str:
    """The PKCE challenge: URL-safe base64 of the SHA-256 of the verifier, unpadded.

    Etsy: "construct a code challenge by taking the URL-safe base64-encoded output of the
    SHA256 hash of the code verifier".
    """
    if not VERIFIER_MIN <= len(verifier) <= VERIFIER_MAX:
        raise EtsyAuthFailed(
            f"a PKCE verifier is {VERIFIER_MIN}-{VERIFIER_MAX} characters; this one is "
            f"{len(verifier)}. Etsy rejects the authorization request, not the token "
            f"request, so the failure would arrive as a browser error in front of the owner.")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


class Transport(Protocol):
    def request(self, method: str, url: str, *, headers: dict[str, str],
                json: dict | None = None, form: dict | None = None,
                multipart: Any | None = None) -> Any:
        ...


@dataclass(frozen=True)
class OAuthApp:
    """The registered Etsy app. Read from the environment; never from this repository."""

    keystring: str
    redirect_uri: str
    shared_secret: str = ""
    # Empty means "the two hosts Etsy's own documents give, in order". A test points this at
    # a local server; nothing in `src/` sets it, so a provider built from the environment can
    # only send a grant to Etsy.
    token_url: str = ""

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> "OAuthApp | None":
        e = env if env is not None else os.environ
        # Two names because two documents in this repository chose differently:
        # CREDENTIALS_SETUP.md says ETSY_KEYSTRING, integrations/etsy.py reads ETSY_API_KEY.
        # They are the same value -- Etsy calls it a keystring -- so both are accepted and
        # the mismatch cannot become a silent "no credentials".
        keystring = (e.get("ETSY_KEYSTRING") or e.get("ETSY_API_KEY") or "").strip()
        redirect = (e.get("ETSY_REDIRECT_URI") or "").strip()
        if not keystring:
            return None
        return OAuthApp(keystring=keystring, redirect_uri=redirect,
                        shared_secret=(e.get("ETSY_SHARED_SECRET") or "").strip())

    def __repr__(self) -> str:  # pragma: no cover - keeps secrets out of tracebacks
        return (f"OAuthApp(keystring=***{fingerprint(self.keystring)}, "
                f"redirect_uri={self.redirect_uri!r}, shared_secret=***)")


@dataclass
class TokenSet:
    """An access token, its refresh token, when it dies and what it may do."""

    access_token: str
    refresh_token: str
    expires_at: float
    scopes: tuple[str, ...] = ()

    @property
    def seconds_left(self) -> float:
        return self.expires_at - time.time()

    def expired(self, *, now: float | None = None, skew: float = EXPIRY_SKEW_SECONDS) -> bool:
        return (now if now is not None else time.time()) >= self.expires_at - skew

    def missing_scopes(self, operation: str) -> tuple[str, ...]:
        """Which scopes this token lacks for a named Etsy operation.

        Checked against what Etsy said it granted -- the token response's `scope` field --
        rather than against what we asked for. Etsy's own words: the granted scope "may be a
        subset of the requested scopes". A token that was granted less than we asked for and
        is used as though it were not is a 403 at publish time.
        """
        required = SCOPES_REQUIRED.get(operation)
        if required is None:
            raise EtsyAuthFailed(f"unknown Etsy operation {operation!r}: its required scopes "
                                 f"are not recorded, so nothing here can say whether this "
                                 f"token may perform it.")
        if not self.scopes:
            # An unknown scope set is not an empty one. Refusing on "we do not know" would
            # block the operations Etsy grants by api_key alone; claiming it is fine would
            # be a guess. Only the scopes we cannot see are reported, and only when some
            # are needed.
            return tuple(required)
        return tuple(s for s in required if s not in self.scopes)

    def redacted(self) -> dict[str, Any]:
        """What may be logged, printed, committed or put in a status report."""
        return {"access_token": f"***{fingerprint(self.access_token)}",
                "refresh_token": f"***{fingerprint(self.refresh_token)}",
                "seconds_left": round(self.seconds_left, 1),
                "scopes": list(self.scopes)}

    def __repr__(self) -> str:  # pragma: no cover
        return f"TokenSet({self.redacted()})"

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> "TokenSet | None":
        """Build a token set from the environment, treating an access token as suspect.

        `ETSY_ACCESS_TOKEN` with no stated expiry is assumed **already expired**, which
        forces one refresh before the first call. That is the honest default: a token pasted
        into an environment an unknown time ago is a token of unknown age, and Etsy gives it
        an hour. One wasted refresh at start-up is the price of never sending a dead token.
        """
        e = env if env is not None else os.environ
        refresh = (e.get("ETSY_REFRESH_TOKEN") or "").strip()
        access = (e.get("ETSY_ACCESS_TOKEN") or "").strip()
        if not (refresh or access):
            return None
        raw_expiry = (e.get("ETSY_ACCESS_TOKEN_EXPIRES_AT") or "").strip()
        try:
            expires_at = float(raw_expiry) if raw_expiry else 0.0
        except ValueError:
            expires_at = 0.0
        scopes = tuple(s for s in (e.get("ETSY_SCOPES") or "").split() if s)
        return TokenSet(access_token=access, refresh_token=refresh,
                        expires_at=expires_at, scopes=scopes)


def authorize_url(app: OAuthApp, *, verifier: str, state: str,
                  scopes: tuple[str, ...] = SCOPES_WANTED) -> str:
    """The URL the owner opens in a browser. This is the auth wall; there is no way round it.

    Every parameter here is from Etsy's documented table. `state` is included even though
    Etsy now says a PKCE client may omit it, because Etsy also says "including it is still
    best practice" and the caller has to compare it on the way back anyway.
    """
    problem = redirect_uri_problem(app.redirect_uri)
    if problem:
        raise EtsyAuthFailed(
            f"the redirect URI must be an exact, https, pre-registered callback: {problem} "
            f"Etsy: 'URL matching is case-sensitive and is specifically the URL established "
            f"when you registered' -- a trailing slash is a different URL and fails.")
    if not state:
        raise EtsyAuthFailed("state must be non-empty when sent: Etsy echoes it back and the "
                             "caller has nothing to compare against.")
    query = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": app.keystring,
        "redirect_uri": app.redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": challenge(verifier),
        "code_challenge_method": "S256",
    })
    return f"{AUTHORIZE_URL}?{query}"


def _token_request(transport: Transport, app: OAuthApp, form: dict[str, str], *,
                   what: str) -> TokenSet:
    """POST a form-encoded grant to Etsy's token endpoint and read the token set back."""
    urls = (app.token_url,) if app.token_url else (TOKEN_URL, TOKEN_URL_ALTERNATE)
    last: Any = None
    for url in urls:
        response = transport.request("POST", url, headers={}, form=form)
        last = response
        if response.status == 404 and url is not urls[-1]:
            # The two Etsy documents disagree about this host. A 404 is what the wrong one
            # would look like, so try the other before concluding anything.
            continue
        break
    body = getattr(last, "body", {}) or {}
    status = getattr(last, "status", 0)
    if status >= 400:
        detail = body.get("error_description") or body.get("error") or body
        if status in (400, 401, 403):
            # RFC 6749's `invalid_grant` is the refresh token being spent, expired or
            # revoked, and no amount of retrying produces a new one.
            raise EtsyAuthNeedsOwner(
                f"Etsy refused the {what} with {status}: {detail}. A refresh token lasts "
                f"{REFRESH_TOKEN_DAYS} days and is single-use per refresh, so this needs the "
                f"owner to open the authorize URL in a browser and approve the app again. "
                f"No code path avoids this.")
        if classify_http(status) is TransientError:
            raise TransientError(f"Etsy returned {status} for the {what}: {detail}")
        raise EtsyAuthFailed(f"Etsy returned {status} for the {what}: {detail}")
    access = body.get("access_token")
    refresh = body.get("refresh_token")
    if not access or not refresh:
        raise EtsyAuthFailed(
            f"Etsy accepted the {what} and returned no usable token set "
            f"(access_token present: {bool(access)}, refresh_token present: {bool(refresh)}). "
            f"Storing half of one would make the next failure look like a revoked app.")
    expires_in = body.get("expires_in") or ACCESS_TOKEN_SECONDS
    try:
        expires_in = float(expires_in)
    except (TypeError, ValueError):
        expires_in = float(ACCESS_TOKEN_SECONDS)
    scopes = tuple(s for s in str(body.get("scope") or "").split() if s)
    return TokenSet(access_token=str(access), refresh_token=str(refresh),
                    expires_at=time.time() + expires_in, scopes=scopes)


def exchange(transport: Transport, app: OAuthApp, *, code: str, verifier: str) -> TokenSet:
    """Turn the authorization code the owner's browser produced into a token set."""
    form = {"grant_type": "authorization_code", "client_id": app.keystring, "code": code,
            "code_verifier": verifier}
    if app.redirect_uri:
        # Optional per Etsy for OAuth 2.1 clients, "when present, it must exactly match".
        form["redirect_uri"] = app.redirect_uri
    return _token_request(transport, app, form, what="authorization-code grant")


def refresh(transport: Transport, app: OAuthApp, refresh_token: str) -> TokenSet:
    """Spend a refresh token for a fresh hour of access, and a fresh refresh token.

    Etsy: refresh grants "do not require sellers to re-approve access and have the same scope
    as the token granted by the initial Authorization Code grant token." So a scope this
    system lacks cannot be acquired here -- that is the owner action in `authorize_url`.
    """
    if not refresh_token:
        raise EtsyAuthNeedsOwner(
            "no refresh token. ETSY_REFRESH_TOKEN is read from the environment and is "
            "absent, so there is nothing to refresh and the owner has to authorise the app.")
    return _token_request(transport, app,
                          {"grant_type": "refresh_token", "client_id": app.keystring,
                           "refresh_token": refresh_token},
                          what="refresh grant")


@dataclass
class TokenProvider:
    """Hands out a live access token, refreshing it when it is about to die.

    The one place in this system that decides whether a token is usable. Callers ask for a
    token instead of reading one, so "the token expired" stops being a failure mode of every
    call site and becomes one refresh here.

    `on_refresh` receives the new token set. It exists because Etsy returns a **new refresh
    token on every refresh** and the old one is spent: a process that refreshes and does not
    persist the new refresh token works until it restarts, then needs the owner's browser.
    It is a callback rather than a file write because where a secret is persisted is a
    deployment decision and must not become this repository.
    """

    app: OAuthApp
    transport: Transport
    tokens: TokenSet | None = None
    on_refresh: Callable[[TokenSet], None] | None = None
    refreshes: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    def token(self, *, operation: str | None = None) -> str:
        if self.tokens is None:
            raise EtsyAuthNeedsOwner(
                "no Etsy token set in this environment. ETSY_REFRESH_TOKEN is absent, so the "
                "owner must complete the authorization-code grant once in a browser.")
        if self.tokens.expired():
            self._refresh_now()
        if operation is not None:
            missing = self.tokens.missing_scopes(operation)
            if missing:
                raise EtsyAuthNeedsOwner(
                    f"this token cannot perform {operation}: it is missing {list(missing)}. "
                    f"Etsy grants scope only through the authorization-code flow and a "
                    f"refresh cannot widen it, so the owner must re-approve the app with "
                    f"{list(SCOPES_WANTED)}.")
        return self.tokens.access_token

    def _refresh_now(self) -> None:
        assert self.tokens is not None
        fresh = refresh(self.transport, self.app, self.tokens.refresh_token)
        rotated = fresh.refresh_token != self.tokens.refresh_token
        self.tokens = fresh
        self.refreshes += 1
        self.history.append({"at": time.time(), "refresh_token_rotated": rotated,
                             **fresh.redacted()})
        if self.on_refresh is not None:
            self.on_refresh(fresh)

    @staticmethod
    def from_env(transport: Transport, env: dict[str, str] | None = None,
                 on_refresh: Callable[[TokenSet], None] | None = None) -> "TokenProvider|None":
        app = OAuthApp.from_env(env)
        if app is None:
            return None
        return TokenProvider(app=app, transport=transport, tokens=TokenSet.from_env(env),
                             on_refresh=on_refresh)


def owner_action(app: OAuthApp | None, *, verifier: str | None = None,
                 state: str | None = None) -> dict[str, Any]:
    """The exact browser step only the owner can take, in the shape OWNER_ACTIONS wants.

    Returned as data so the launch queue can carry it without this module knowing about the
    queue. The URL is only included when an app exists to build one from; asking the owner to
    open a URL containing a keystring we do not have would be a fabricated instruction.
    """
    action = {
        "action": "authorise the Brambleloop Etsy app once, in a browser",
        "steps": [
            "Sign in to the Etsy account that owns BrambleloopStudio.",
            "At etsy.com/developers/your-apps, register the app (or open the existing one) "
            "and set the callback URL to the exact https redirect this system will use. "
            "Etsy matches it character for character: a trailing slash is a different URL.",
            "Put the keystring, shared secret and redirect URI in the deployment's "
            "environment as ETSY_KEYSTRING, ETSY_SHARED_SECRET and ETSY_REDIRECT_URI. "
            "Never in the repository. The redirect URI is this service's own callback: "
            "https://<the deployment's host>/api/etsy/oauth/callback, character for "
            "character, no trailing slash.",
            "Set BRAMBLELOOP_SECRET_KEY to 32 or more random characters, if it is not set "
            "already. It is the key the refresh token is sealed under; without it the "
            "callback refuses to complete rather than storing a credential in the clear.",
            "Call GET /api/etsy/oauth/start with the operator credential. It returns an "
            "authorize URL, having first written that flow's state and PKCE verifier to the "
            "database, which is what lets the callback finish on any container.",
            "Open that URL, approve the listed scopes, and let the callback capture the "
            "code. The code is single-use and expires quickly, and the state is good for "
            "fifteen minutes.",
            "Nothing further. The refresh token is stored sealed by the callback and rotated "
            "in place from then on; it is never printed, returned or put in a variable.",
        ],
        "why": ("Etsy's authorization-code grant requires a human to approve the scopes in a "
                "browser session. There is no client-credentials or API-key-only path to a "
                "write scope, so no amount of code removes this step. Without it every write "
                "endpoint returns 403 and the shop cannot be built by software at all."),
        "scopes_requested": {s: SCOPE_MEANINGS.get(s, "") for s in SCOPES_WANTED},
        "maximum_cost": "CA$0",
        "minutes": 15,
        "consequence_of_waiting": (
            "every Etsy write stays unexercised. The transport, the encodings and the "
            "read-back verification are tested against a local model of Etsy built from "
            "Etsy's document; not one of them has been confirmed by Etsy."),
        "expires": (f"the refresh token lasts {REFRESH_TOKEN_DAYS} days and every refresh "
                    f"issues a new one; if the deployment loses it, this action repeats."),
    }
    if app is not None and not redirect_uri_problem(app.redirect_uri):
        v = verifier or new_verifier()
        action["authorize_url"] = authorize_url(app, verifier=v, state=state or new_state())
        action["code_verifier_note"] = (
            "this URL's verifier is held only by whatever built it. A URL built by "
            "`GET /api/etsy/oauth/start` has its verifier sealed in the database and its "
            "callback will complete; a URL built by this function on its own -- the probe's "
            "offline printout -- has nowhere to complete, because the verifier dies with the "
            "process. Use the endpoint.")
    else:
        action["authorize_url"] = None
        action["blocked_on"] = ("no ETSY_KEYSTRING / ETSY_REDIRECT_URI in this environment, "
                               "so no authorize URL can be built yet.")
    return action
