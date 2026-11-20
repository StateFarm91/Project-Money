"""The Etsy authorization-code flow, end to end, across a browser round trip.

`etsy_oauth` knows Etsy's protocol and `core.oauth_store` knows how to hold half a flow
durably. Neither of them, on its own, could complete an authorization: `exchange()` had no
caller anywhere in this system, and the PKCE verifier it needs was documented as living in
"the calling process only" -- so the owner action that said "let the callback capture the
code" described a thing that did not exist. This module is the missing middle, and it is
deliberately thin: two functions, `begin` and `finish`, and no second implementation of
anything `etsy_oauth` already does.

**Nothing here creates, modifies, activates, publishes or deletes anything on Etsy.**
Authenticating is not a write to the shop; it exchanges a code for a token and stores the
token. `EtsyClient.activate`'s three gates are untouched by this file and `BRAMBLELOOP_PHASE`
is not consulted, because refusing to authenticate in SHADOW would mean the first time this
system ever authenticated would be the day the shop opened -- which is the exact risk the
whole Etsy department was built to remove.

**The secrets and where they are.** Five values pass through this module and none of them is
ever returned, logged, audited or rendered:

| value | lives | for how long |
|---|---|---|
| PKCE verifier | sealed in `oauth_handshakes` | one flow, then the row is spent |
| OAuth state | **nowhere** -- only its SHA-256 is stored | one flow |
| authorization code | one function's local variable | the length of one HTTPS request |
| access token | `TokenProvider`, in memory | one hour |
| refresh token | sealed in `oauth_credentials` | 90 days, rotating hourly |
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core import oauth_store, sealed
from ..core.oauth_store import Verdict
from . import etsy_oauth
from .http import Redactor

PROVIDER = "etsy"

# The path this service listens on, and the path the owner registers at Etsy. One constant,
# because it appears in three places -- the route, the configuration check and the owner
# action -- and three copies of a string Etsy matches character for character is three
# chances to be one character out.
CALLBACK_PATH = "/api/etsy/oauth/callback"


@dataclass
class Started:
    """What `begin` produced: a URL for a human, and nothing a machine could misuse."""

    authorize_url: str
    state_fingerprint: str
    expires_at: str
    scopes: tuple[str, ...]
    handshake: int
    redirect_uri: str

    def to_dict(self) -> dict:
        return {"authorize_url": self.authorize_url,
                "state_fingerprint": f"***{self.state_fingerprint}",
                "state_expires_at": self.expires_at,
                "scopes": list(self.scopes),
                "handshake": self.handshake,
                "redirect_uri": self.redirect_uri,
                "next": ("open the authorize URL in a browser, sign in as the Etsy account "
                         "that owns the shop, and approve the listed scopes. Etsy will send "
                         f"the browser back to {CALLBACK_PATH}."),
                "note": ("the URL carries this app's keystring, which is a public client "
                         "identifier, and a PKCE challenge, which is a hash. It carries no "
                         "secret: the shared secret, the verifier and every token stay on "
                         "the server.")}


@dataclass
class Completed:
    """What `finish` produced. Readable by a human; useless to anyone who steals it."""

    ok: bool
    outcome: str
    http_status: int
    headline: str
    explanation: str
    what_to_do: str = ""
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "outcome": self.outcome, "headline": self.headline,
                "explanation": self.explanation, "what_to_do": self.what_to_do,
                **self.detail}


class NotConfigured(RuntimeError):
    """The deployment cannot start a flow yet, and says exactly which piece is missing."""


def configuration(env: dict[str, str] | None = None) -> dict:
    """Everything that has to be true before an authorization can be started.

    Reported as data rather than raised, so the start endpoint can tell an operator all of
    what is missing at once instead of one item per attempt.
    """
    app = etsy_oauth.OAuthApp.from_env(env)
    redirect = app.redirect_uri if app else ""
    problems: list[str] = []
    if app is None:
        problems.append("ETSY_KEYSTRING (or ETSY_API_KEY) is not set, so there is no app to "
                        "authorise.")
    else:
        problem = etsy_oauth.redirect_uri_problem(redirect)
        if problem:
            problems.append(f"ETSY_REDIRECT_URI: {problem}")
        elif not redirect.endswith(CALLBACK_PATH):
            # Not fatal: the owner may have registered a proxy or a custom domain path. It is
            # reported because the overwhelmingly likely cause is a typo, and the symptom of
            # the typo is a 404 in a browser twenty minutes later with no server-side trace.
            problems.append(
                f"ETSY_REDIRECT_URI does not end with {CALLBACK_PATH}, which is the only "
                f"path this service answers an Etsy redirect on. Unless a proxy rewrites it, "
                f"the callback will 404 and the authorization will be lost.")
    key = sealed.key_health(env)
    if not key["usable"]:
        problems.append(
            f"{sealed.KEY_VAR} is {key['reason']}. The PKCE verifier and the refresh token "
            f"are sealed with it, and this flow refuses to store either in the clear.")
    return {
        "ready": not problems,
        "problems": problems,
        "redirect_uri": redirect,
        "callback_path": CALLBACK_PATH,
        "scopes": list(etsy_oauth.SCOPES_WANTED),
        "redirect_uri_matching": etsy_oauth.REDIRECT_URI_MATCHING,
        "sealing_key": {k: v for k, v in key.items() if k != "key_fingerprint"},
    }


def begin(db, *, env: dict[str, str] | None = None,
          scopes: tuple[str, ...] = etsy_oauth.SCOPES_WANTED,
          started_by: str = "operator") -> Started:
    """Mint a state and a verifier, write them down, and build the URL the owner opens.

    The order is the whole point: the handshake is **written before the URL is returned**. A
    URL handed out before its verifier is durable is a URL that can produce an authorization
    code this system cannot spend -- and an authorization code that cannot be spent is one
    the owner has to go and get again.
    """
    config = configuration(env)
    if not config["ready"]:
        raise NotConfigured("; ".join(config["problems"]))

    app = etsy_oauth.OAuthApp.from_env(env)
    assert app is not None  # configuration() established this
    verifier = etsy_oauth.new_verifier()
    handshake = oauth_store.begin(
        db, provider=PROVIDER, verifier=verifier, redirect_uri=app.redirect_uri,
        scopes=" ".join(scopes), started_by=started_by, env=env)
    url = etsy_oauth.authorize_url(app, verifier=verifier, state=handshake.state,
                                   scopes=scopes)
    return Started(authorize_url=url, state_fingerprint=handshake.fingerprint,
                   expires_at=handshake.expires_at.isoformat(), scopes=tuple(scopes),
                   handshake=handshake.row_id, redirect_uri=app.redirect_uri)


# Every way the callback can end, with the status a browser gets and the sentence a human
# reads. Written as a table rather than as branches so that "each rejection is
# distinguishable" is something a reader can check in one place -- and so that adding a
# sixth refusal means adding a row, not remembering to invent a status code.
#
# The status codes are chosen to be different from each other on purpose: an operator reading
# a proxy log with no body still gets the verdict.
OUTCOMES: dict[str, tuple[int, str, str, str]] = {
    Verdict.STATE_MISSING.value: (
        400, "No state on this callback",
        "Etsy echoes back exactly the state the authorization request carried, and this "
        "system always sends one. A redirect with no state did not come from a flow this "
        "service started.",
        "Start again with GET /api/etsy/oauth/start."),
    # 403 rather than 400, and the difference is the point: a missing state is a malformed
    # request, while a state that exists and was not issued here is a credential this service
    # declines to recognise. An operator reading a proxy log with no bodies can tell a
    # mistyped URL from somebody probing the endpoint.
    Verdict.STATE_UNKNOWN.value: (
        403, "Unrecognised state",
        "No authorization flow in this database has ever held that state. It was not "
        "minted here, or it was minted by a different deployment.",
        "Start again with GET /api/etsy/oauth/start, and open the URL it returns."),
    Verdict.STATE_EXPIRED.value: (
        410, "This authorization expired",
        f"An authorization has {oauth_store.HANDSHAKE_TTL_SECONDS // 60} minutes to complete "
        f"and this one took longer. Nothing was exchanged and nothing was stored.",
        "Start again with GET /api/etsy/oauth/start."),
    Verdict.STATE_REPLAYED.value: (
        409, "This authorization was already used",
        "A state is single-use -- Etsy's own instruction is to make a note never to use one "
        "again -- and this one has been presented before. No code was exchanged.",
        "If you did not just reload the page, the callback URL has been replayed by somebody "
        "else. Nothing was granted. Start a new authorization if you still need one."),
    Verdict.VERIFIER_UNREADABLE.value: (
        503, "This deployment cannot finish the flow",
        f"The state was valid, and the PKCE verifier stored with it will not open. Either "
        f"{sealed.KEY_VAR} is not the key it was sealed under, or the stored value is "
        f"damaged. Nothing was exchanged.",
        f"Check that {sealed.KEY_VAR} is the same value it was when the flow was started, "
        f"then start again."),
    "etsy_refused": (
        400, "Etsy did not grant access",
        "Etsy sent an error back instead of an authorization code. Nothing was exchanged and "
        "nothing was stored.",
        "If this says access_denied, the consent screen was declined -- approve the scopes to "
        "continue. Otherwise the error code below is Etsy's."),
    "unusable_callback": (
        400, "Not an Etsy redirect",
        "This request carried neither an authorization code nor an error. Etsy's redirect "
        "always carries one of the two.",
        "Start at GET /api/etsy/oauth/start; the callback is not a URL to visit by hand."),
    "exchange_failed": (
        502, "Etsy refused the token request",
        "The state was valid and the code was exchanged with Etsy, which declined it. The "
        "authorization code is now spent, so this exact flow cannot be retried.",
        "Start again with GET /api/etsy/oauth/start. If it fails a second time, the "
        "registered redirect URI most likely does not match the one this service sends."),
    "not_stored": (
        503, "Etsy granted access and this deployment could not store it",
        "A token was issued and could not be sealed, so it was discarded rather than held "
        "somewhere it does not belong. The grant is wasted; nothing is broken.",
        f"Set {sealed.KEY_VAR} in the deployment's environment and authorise again."),
    Verdict.OK.value: (
        200, "Brambleloop is authorised on Etsy",
        "The authorization code was exchanged and the refresh token is stored, sealed, in "
        "the database. This page does not carry it and neither does any log.",
        "Nothing further. The service refreshes its own access token from here on."),
}


def _outcome(name: str, *, detail: dict | None = None, ok: bool = False) -> Completed:
    status, headline, explanation, what_to_do = OUTCOMES[name]
    return Completed(ok=ok, outcome=name, http_status=status, headline=headline,
                     explanation=explanation, what_to_do=what_to_do, detail=detail or {})


def finish(db, params: dict[str, Any], *, transport: Any,
           env: dict[str, str] | None = None) -> Completed:
    """Turn a redirect from Etsy into a stored credential, or into a named refusal.

    Named `finish` rather than the obvious `complete` for one concrete reason:
    `tests/test_model_spend_paths.py` scans every module in `src/` for a call to a method
    named `complete` on any receiver, because that is how this company's model provider is
    billed, and it refuses any it finds without a budget check. A free OAuth call named
    `complete` would have had to be added to that scanner's exclusion list -- and an
    exclusion list with an entry in it is a place a real spend path can hide later. A
    four-letter rename here costs nothing and leaves that instrument reading zero
    exclusions in this file.

    The order of the checks is the security property. **The state is consumed before the code
    is looked at, and the code is never sent to Etsy until a handshake this service opened
    has been claimed.** That is what stops this being an open code-exchange endpoint: an
    unauthenticated caller who posts a stolen authorization code here cannot make a single
    outbound request, because they cannot produce a state that a claim will win.

    Nothing this function returns contains the code, the verifier, the state or any token.
    The detail it hands back is put through Lane C's `Redactor` on the way out as a
    belt-and-braces pass over any Etsy-supplied string that reached it.
    """
    redactor = Redactor()
    app = etsy_oauth.OAuthApp.from_env(env)
    if app is not None:
        redactor.add(app.shared_secret)

    parsed = etsy_oauth.parse_redirect(params)
    state = parsed["state"]

    # 1. Claim the handshake. First, always -- including for a redirect that carries an Etsy
    #    error, because a state presented with an error is still a state that has been used
    #    and must not be usable twice.
    consumed = oauth_store.consume(db, provider=PROVIDER, state=state, env=env)
    base = consumed.redacted()

    if not consumed.ok:
        return _outcome(consumed.verdict.value, detail=base)

    # Seed the redactor with the two secrets this request is actually holding, so that an
    # Etsy error body echoing either back -- which has been observed for bearer tokens and is
    # exactly the case redaction by field name misses -- is replaced by a fingerprint rather
    # than rendered into a page.
    redactor.add(parsed["code"])
    redactor.add(consumed.verifier)

    # 2. Only now is Etsy's own answer read.
    if parsed["kind"] == "error":
        oauth_store.record_outcome(db, consumed.row_id, "etsy_refused")
        return _outcome("etsy_refused", detail={
            **base,
            # Etsy's words, truncated and redacted. Whoever renders this escapes it: it
            # arrived on a URL and is not this system's text.
            "etsy_error": redactor.string(parsed["error"]),
            "etsy_error_description": redactor.string(parsed["error_description"])})
    if parsed["kind"] != "code":
        oauth_store.record_outcome(db, consumed.row_id, "unusable_callback")
        return _outcome("unusable_callback", detail=base)

    # 3. Refuse to spend the code if the result could not be stored. A grant that is
    #    exchanged and then dropped costs the owner a second trip to the browser for nothing.
    if not sealed.configured(env):
        oauth_store.record_outcome(db, consumed.row_id, "not_stored")
        return _outcome("not_stored", detail={**base, "sealing_key": sealed.key_health(env)})

    # 4. The one outbound request. `etsy_oauth.exchange` is the only implementation of this
    #    grant in the system and this is its first caller.
    try:
        tokens = etsy_oauth.exchange(transport, app, code=parsed["code"],
                                     verifier=consumed.verifier)
    except Exception as exc:  # noqa: BLE001 - every failure here has the same shape
        oauth_store.record_outcome(db, consumed.row_id, "exchange_failed")
        # The message is redacted before it is shown or stored. Etsy has been observed
        # echoing a bearer token back inside an error body (`tests/fake_etsy.py` reproduces
        # it), and an exception message is a string like any other.
        return _outcome("exchange_failed", detail={
            **base, "error_class": type(exc).__name__,
            "etsy_said": redactor.string(str(exc))[:400]})

    # 5. Store it sealed. No `expected_fingerprint`: a fresh grant supersedes whatever was
    #    there, because the owner has just approved the app in a browser.
    try:
        stored = oauth_store.save_refresh_token(
            db, tokens.refresh_token, provider=PROVIDER, scopes=" ".join(tokens.scopes),
            source="authorization-code grant", new_grant=True, env=env)
    except Exception as exc:  # noqa: BLE001
        oauth_store.record_outcome(db, consumed.row_id, "not_stored")
        return _outcome("not_stored", detail={
            **base, "error_class": type(exc).__name__,
            "sealing_key": sealed.key_health(env)})

    oauth_store.record_outcome(db, consumed.row_id, "exchanged")
    granted = tuple(tokens.scopes)
    missing = tuple(s for s in etsy_oauth.SCOPES_WANTED if s not in granted)
    return _outcome(Verdict.OK.value, ok=True, detail={
        **base,
        # Fingerprints, never values. `TokenSet.redacted()` is the existing shape for this
        # and is reused rather than reinvented.
        "tokens": tokens.redacted(),
        "credential": stored,
        "scopes_granted": list(granted),
        # Etsy's granted scope "may be a subset of the requested scopes", so this is worth
        # saying on the page: a missing write scope is a 403 at publish time otherwise.
        "scopes_not_granted": list(missing),
    })
