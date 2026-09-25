"""The Etsy OAuth callback: every way it refuses, and the one way it does not.

This suite is written the way the endpoint is: mostly about rejections. The callback is the
only route in this system an unauthenticated stranger is *meant* to reach, and it holds the
door to the only credential that can write to the company's shop, so a test that only proved
the happy path would prove the least interesting thing about it.

Three things are exercised for real rather than described:

* **A server on a socket.** `tests/fake_etsy.py` now implements Etsy's authorization-code
  grant -- single-use code, PKCE verifier checked against the challenge, exact `redirect_uri`
  match -- so the bytes of the token request go over a real connection and are parsed by a
  parser that is not ours. It is still a model of Etsy built from Etsy's document, so what
  passes here is "our side of the wire is right", never "Etsy accepts it".
* **The real route.** The success path is driven through `TestClient` against the actual
  FastAPI app, not a hand-wired call, and the transport is intercepted at the class so the
  test can *assert which host the grant was sent to* -- which is a stronger check than an
  environment override would have allowed.
* **Two injected defects.** Two of these checks are run a second time against a deliberately
  broken implementation, because a test that has never failed is a test nobody has reason to
  believe.

Nothing here touches Etsy, creates a listing, activates anything or costs a cent.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.TemporaryDirectory()
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP.name}/oauth.sqlite"
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ["BRAMBLELOOP_RUNNER_START_DELAY"] = "0"

OPS_TOKEN = "operator-token-for-tests-0123456789"
SEAL_KEY = "a-test-sealing-key-of-quite-sufficient-length-0123456789"
REDIRECT_URI = "https://brambleloop.example/api/etsy/oauth/callback"

os.environ["BRAMBLELOOP_OPS_TOKEN"] = OPS_TOKEN
os.environ["BRAMBLELOOP_SECRET_KEY"] = SEAL_KEY
os.environ["ETSY_KEYSTRING"] = "fakekeystring"
os.environ["ETSY_SHARED_SECRET"] = "fakesharedsecret"
os.environ["ETSY_REDIRECT_URI"] = REDIRECT_URI

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.app import main as app_main  # noqa: E402
from brambleloop.core import oauth_store, sealed  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, OAuthCredential, OAuthHandshake, utcnow,
)
from brambleloop.integrations import etsy_authorise, etsy_oauth, http as etsy_http  # noqa: E402
from brambleloop.ops import retention  # noqa: E402

from fake_etsy import FakeEtsy  # noqa: E402

ENV = {
    "ETSY_KEYSTRING": "fakekeystring",
    "ETSY_SHARED_SECRET": "fakesharedsecret",
    "ETSY_REDIRECT_URI": REDIRECT_URI,
    "BRAMBLELOOP_SECRET_KEY": SEAL_KEY,
}

# Every secret this suite handles, so one assertion can sweep a response, a page and an
# audit row for all of them at once. A test that checks only for the token it happened to
# think of is a test that passes while a verifier leaks.
def _secrets_in_play(fake: FakeEtsy, extra: tuple[str, ...] = ()) -> list[str]:
    values = [fake.shared_secret, *extra]
    values += list(fake.refresh_tokens)
    values += [t for t in fake.tokens]
    values += list(fake.authorization_codes)
    return [v for v in values if v]


def _fresh_db() -> Database:
    handle = tempfile.mkdtemp(prefix="oauth-store-")
    db = Database(f"sqlite:///{handle}/db.sqlite", scratch=True)
    db.create_all()
    return db


def _client() -> TestClient:
    return TestClient(app_main.app)


# ---------------------------------------------------------------------------
# Sealing: the reason a credential may live in Postgres at all


def test_a_sealed_secret_never_appears_in_the_value_that_is_stored():
    secret = "111.refresh-token-that-must-not-be-readable"
    box = sealed.seal(secret, context=oauth_store.REFRESH_TOKEN_CONTEXT, env=ENV)
    assert secret not in box, "the sealed value contains the plaintext it is sealing"
    assert box.startswith("v1:"), box
    assert sealed.unseal(box, context=oauth_store.REFRESH_TOKEN_CONTEXT, env=ENV) == secret
    # Two seals of one secret differ: a fresh nonce every time, so a database cannot be
    # searched for "the row holding the same token as this one".
    again = sealed.seal(secret, context=oauth_store.REFRESH_TOKEN_CONTEXT, env=ENV)
    assert again != box


def test_sealing_refuses_without_a_key_rather_than_storing_plaintext():
    try:
        sealed.seal("a-secret", context="x", env={})
    except sealed.SealUnavailable as exc:
        assert sealed.KEY_VAR in str(exc)
    else:
        raise AssertionError("sealing with no key must refuse, never fall back to plaintext")
    assert sealed.configured({}) is False
    assert sealed.key_health({})["usable"] is False


def test_a_sealed_verifier_cannot_be_opened_as_a_sealed_refresh_token():
    """Context binding. Two secrets in two columns stay two secrets."""
    box = sealed.seal("the-verifier", context=oauth_store.VERIFIER_CONTEXT, env=ENV)
    try:
        sealed.unseal(box, context=oauth_store.REFRESH_TOKEN_CONTEXT, env=ENV)
    except sealed.SealBroken:
        pass
    else:
        raise AssertionError("a sealed verifier opened as a refresh token")


def test_a_different_key_cannot_open_a_sealed_value_and_says_so_without_an_oracle():
    box = sealed.seal("secret-value", context="ctx", env=ENV)
    other = {"BRAMBLELOOP_SECRET_KEY": "a-completely-different-key-also-long-enough-12345"}
    try:
        sealed.unseal(box, context="ctx", env=other)
    except sealed.SealBroken as exc:
        # The message must not distinguish "wrong key" from "wrong context" from "corrupt":
        # the three are one answer -- re-authorise -- and telling them apart is an oracle.
        assert "did not open" in str(exc)
    else:
        raise AssertionError("a value opened under the wrong key")


# ---------------------------------------------------------------------------
# The handshake: what is written down, and what is deliberately not


def test_the_state_is_never_stored_and_the_verifier_is_never_stored_in_the_clear():
    db = _fresh_db()
    verifier = etsy_oauth.new_verifier()
    handshake = oauth_store.begin(db, verifier=verifier, redirect_uri=REDIRECT_URI,
                                  scopes="listings_w", env=ENV)
    with db.session() as s:
        row = s.scalar(select(OAuthHandshake))
        stored = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    blob = repr(stored)
    assert handshake.state not in blob, "the raw OAuth state was written to the database"
    assert verifier not in blob, "the PKCE verifier was written to the database in the clear"
    assert stored["state_sha256"] == oauth_store.state_hash(handshake.state)
    assert stored["verifier_sealed"].startswith("v1:")
    # And the row's repr, which is what reaches a traceback.
    assert verifier not in repr(row) and handshake.state not in repr(row)


def test_the_state_is_unpredictable_and_comes_from_secrets_not_random():
    states = {etsy_oauth.new_state() for _ in range(500)}
    assert len(states) == 500, "two of 500 states collided"
    assert all(len(s) >= 43 for s in states), "a state shorter than a PKCE verifier"
    source = (ROOT / "src/brambleloop/integrations/etsy_oauth.py").read_text()
    store_source = (ROOT / "src/brambleloop/core/oauth_store.py").read_text()
    for text, name in ((source, "etsy_oauth"), (store_source, "oauth_store")):
        assert "import secrets" in text, f"{name} does not import `secrets`"
        assert "import random" not in text, (
            f"{name} imports `random`. 624 outputs of a Mersenne Twister determine every "
            f"output after them, which is the one property a CSRF token must not have")


# ---------------------------------------------------------------------------
# The four state rejections, each distinguishable from the other three


def test_a_missing_state_is_its_own_refusal():
    db = _fresh_db()
    result = oauth_store.consume(db, state=None, env=ENV)
    assert result.verdict is oauth_store.Verdict.STATE_MISSING
    assert result.verifier == ""


def test_an_unknown_state_is_its_own_refusal():
    db = _fresh_db()
    oauth_store.begin(db, verifier=etsy_oauth.new_verifier(), redirect_uri=REDIRECT_URI,
                      env=ENV)
    result = oauth_store.consume(db, state="a-state-this-database-never-minted", env=ENV)
    assert result.verdict is oauth_store.Verdict.STATE_UNKNOWN
    # The legitimate handshake is untouched: a stranger's guess cannot spend the owner's flow.
    with db.session() as s:
        assert s.scalar(select(OAuthHandshake)).consumed_at is None


def test_an_expired_state_is_its_own_refusal_and_cannot_be_retried():
    db = _fresh_db()
    handshake = oauth_store.begin(db, verifier=etsy_oauth.new_verifier(),
                                  redirect_uri=REDIRECT_URI, env=ENV)
    later = utcnow() + timedelta(seconds=oauth_store.HANDSHAKE_TTL_SECONDS + 60)
    first = oauth_store.consume(db, state=handshake.state, now=later, env=ENV)
    assert first.verdict is oauth_store.Verdict.STATE_EXPIRED
    # Marked spent on the way out, so waiting for a clock to move cannot revive it.
    second = oauth_store.consume(db, state=handshake.state, env=ENV)
    assert second.verdict is oauth_store.Verdict.STATE_REPLAYED


def test_a_replayed_state_is_its_own_refusal_and_is_counted():
    db = _fresh_db()
    handshake = oauth_store.begin(db, verifier=etsy_oauth.new_verifier(),
                                  redirect_uri=REDIRECT_URI, env=ENV)
    assert oauth_store.consume(db, state=handshake.state, env=ENV).ok
    for expected in (1, 2):
        again = oauth_store.consume(db, state=handshake.state, env=ENV)
        assert again.verdict is oauth_store.Verdict.STATE_REPLAYED
        assert again.replays == expected, "a replay was not counted"
        assert again.verifier == "", "a replayed state handed back a verifier"


def test_the_four_refusals_are_four_different_outcomes_end_to_end():
    """Not one of them may be reported as another. The point of the whole table."""
    seen = {
        oauth_store.Verdict.STATE_MISSING.value,
        oauth_store.Verdict.STATE_UNKNOWN.value,
        oauth_store.Verdict.STATE_EXPIRED.value,
        oauth_store.Verdict.STATE_REPLAYED.value,
        oauth_store.Verdict.VERIFIER_UNREADABLE.value,
    }
    statuses = {etsy_authorise.OUTCOMES[name][0] for name in seen}
    assert len(statuses) == len(seen), (
        f"two state refusals share an HTTP status: {sorted(statuses)}. An operator reading a "
        f"proxy log with no body could not tell them apart")
    assert len({etsy_authorise.OUTCOMES[n][1] for n in seen}) == len(seen)


def test_a_verifier_that_will_not_open_is_its_own_refusal_and_still_spends_the_state():
    db = _fresh_db()
    handshake = oauth_store.begin(db, verifier=etsy_oauth.new_verifier(),
                                  redirect_uri=REDIRECT_URI, env=ENV)
    with db.session() as s:
        s.scalar(select(OAuthHandshake)).verifier_sealed = "v1:not-openable-bytes"
    result = oauth_store.consume(db, state=handshake.state, env=ENV)
    assert result.verdict is oauth_store.Verdict.VERIFIER_UNREADABLE
    assert result.verifier == ""
    with db.session() as s:
        row = s.scalar(select(OAuthHandshake))
        assert row.consumed_at is not None, (
            "a state that was presented must never be usable again, whatever went wrong "
            "after it was presented")


def test_a_handshake_opened_for_one_provider_cannot_be_closed_by_another():
    db = _fresh_db()
    handshake = oauth_store.begin(db, provider="etsy", verifier=etsy_oauth.new_verifier(),
                                  redirect_uri=REDIRECT_URI, env=ENV)
    result = oauth_store.consume(db, provider="pinterest", state=handshake.state, env=ENV)
    assert result.verdict is oauth_store.Verdict.STATE_UNKNOWN


# ---------------------------------------------------------------------------
# Injected defects: proof that two of the checks above can fail


def test_the_replay_check_catches_an_injected_single_use_defect():
    """Run the replay scenario against a naive read-then-write consume, and watch it pass.

    This is the defect that a careful person writes by accident: read the row, see it is
    unconsumed, do the work, mark it consumed. It is wrong twice -- a second delivery of the
    same callback finds the row unconsumed if it arrives first, and two concurrent deliveries
    both do. The real implementation claims the row with one conditional UPDATE, so the
    database decides.
    """
    db = _fresh_db()

    def naive_consume(database, *, provider="etsy", state=None, now=None, env=None):
        with database.session() as s:
            row = s.scalar(select(OAuthHandshake).where(
                OAuthHandshake.state_sha256 == oauth_store.state_hash(state or "")))
            if row is None:
                return oauth_store.Consumed(verdict=oauth_store.Verdict.STATE_UNKNOWN)
            if row.consumed_at is not None:
                return oauth_store.Consumed(verdict=oauth_store.Verdict.STATE_REPLAYED)
            verifier = sealed.unseal(row.verifier_sealed,
                                     context=oauth_store.VERIFIER_CONTEXT, env=env)
            return oauth_store.Consumed(verdict=oauth_store.Verdict.OK, verifier=verifier,
                                        row_id=row.id)

    handshake = oauth_store.begin(db, verifier=etsy_oauth.new_verifier(),
                                  redirect_uri=REDIRECT_URI, env=ENV)
    first = naive_consume(db, state=handshake.state, env=ENV)
    second = naive_consume(db, state=handshake.state, env=ENV)
    assert first.ok and second.ok, (
        "the injected defect did not reproduce, so this check proves nothing")
    # And the real one, on the same scenario.
    handshake = oauth_store.begin(db, verifier=etsy_oauth.new_verifier(),
                                  redirect_uri=REDIRECT_URI, env=ENV)
    assert oauth_store.consume(db, state=handshake.state, env=ENV).ok
    assert oauth_store.consume(db, state=handshake.state, env=ENV).verdict is (
        oauth_store.Verdict.STATE_REPLAYED)


def test_the_no_plaintext_check_catches_an_injected_sealing_defect():
    """Replace sealing with the identity function and watch the storage check go red."""
    db = _fresh_db()
    verifier = etsy_oauth.new_verifier()
    real_seal = sealed.seal
    try:
        sealed.seal = lambda value, *, context, env=None: value  # the defect
        oauth_store.begin(db, verifier=verifier, redirect_uri=REDIRECT_URI, env=ENV)
    finally:
        sealed.seal = real_seal
    with db.session() as s:
        row = s.scalar(select(OAuthHandshake))
        leaked = verifier in repr({c.name: getattr(row, c.name)
                                   for c in row.__table__.columns})
    assert leaked, ("the injected defect did not reproduce: the check that the verifier is "
                    "never stored in the clear would not have caught it")


# ---------------------------------------------------------------------------
# The route: the operator guard at both ends


def test_the_start_endpoint_refuses_a_caller_with_no_operator_credential():
    with _client() as c:
        assert c.get("/api/etsy/oauth/start").status_code == 401
        assert c.get("/api/etsy/oauth/status").status_code == 401
        wrong = {"Authorization": "Bearer not-the-operator-token-but-long-enough"}
        assert c.get("/api/etsy/oauth/start", headers=wrong).status_code == 401
        assert c.get("/api/etsy/oauth/status", headers=wrong).status_code == 401


def test_both_ends_close_when_the_operator_token_is_unset():
    """Unconfigured means closed, in the same direction `/api/continuity/export` chose."""
    saved = os.environ.pop("BRAMBLELOOP_OPS_TOKEN")
    try:
        with _client() as c:
            start = c.get("/api/etsy/oauth/start",
                          headers={"Authorization": f"Bearer {saved}"})
            assert start.status_code == 503, start.text
            back = c.get("/api/etsy/oauth/callback?code=x&state=y")
            assert back.status_code == 503, back.text
            assert "operator_credential_unconfigured" in back.text
    finally:
        os.environ["BRAMBLELOOP_OPS_TOKEN"] = saved


def test_the_start_endpoint_writes_the_handshake_before_it_returns_a_url():
    with _client() as c:
        body = c.get("/api/etsy/oauth/start",
                     headers={"Authorization": f"Bearer {OPS_TOKEN}"}).json()
    assert body["authorize_url"].startswith(etsy_oauth.AUTHORIZE_URL + "?")
    for part in ("response_type=code", "code_challenge_method=S256", "state=",
                 "code_challenge="):
        assert part in body["authorize_url"], part
    # The URL carries the public client identifier and a hash. It must not carry the shared
    # secret or the verifier.
    assert os.environ["ETSY_SHARED_SECRET"] not in body["authorize_url"]
    assert "code_verifier" not in body["authorize_url"]
    assert body["state_fingerprint"].startswith("***")
    with app_main.db.session() as s:
        row = s.scalar(select(OAuthHandshake).where(
            OAuthHandshake.id == body["handshake"]))
    assert row is not None and row.consumed_at is None


def test_the_start_endpoint_refuses_when_there_is_nowhere_to_seal_the_verifier():
    saved = os.environ.pop("BRAMBLELOOP_SECRET_KEY")
    try:
        with _client() as c:
            r = c.get("/api/etsy/oauth/start",
                      headers={"Authorization": f"Bearer {OPS_TOKEN}"})
        assert r.status_code == 409, r.text
        assert any(sealed.KEY_VAR in p for p in r.json()["problems"])
    finally:
        os.environ["BRAMBLELOOP_SECRET_KEY"] = saved


# ---------------------------------------------------------------------------
# The route: malformed callbacks, and the proof that none of them reaches Etsy


class _RefusingTransport:
    """Any outbound request at all is a test failure."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def request(self, method, url, **kwargs):
        self.calls.append(url)
        raise AssertionError(f"an outbound {method} to {url} was made by a callback that "
                             f"should never have reached Etsy")


def test_no_malformed_callback_causes_a_single_outbound_request():
    db = _fresh_db()
    good = oauth_store.begin(db, verifier=etsy_oauth.new_verifier(),
                             redirect_uri=REDIRECT_URI, env=ENV)
    spy = _RefusingTransport()
    cases = {
        "nothing at all": {},
        "a code and no state": {"code": "stolen-authorization-code"},
        "a state and no code": {"state": good.state},
        "junk in both": {"code": "../../etc/passwd", "state": "%00%00"},
        "an unknown state with a real-looking code": {
            "code": "bftcubu-wownsvftz5kowdmxnqtsuoik", "state": "not-a-state-we-minted"},
        "an error redirect": {"error": "access_denied",
                              "error_description": "the user declined",
                              "state": "not-a-state-we-minted"},
    }
    for name, params in cases.items():
        result = etsy_authorise.finish(db, params, transport=spy, env=ENV)
        assert not result.ok, name
        assert result.http_status >= 400, name
    assert spy.calls == [], f"the callback contacted Etsy: {spy.calls}"


def test_a_state_and_no_code_spends_the_state_and_says_it_was_not_an_etsy_redirect():
    db = _fresh_db()
    handshake = oauth_store.begin(db, verifier=etsy_oauth.new_verifier(),
                                  redirect_uri=REDIRECT_URI, env=ENV)
    result = etsy_authorise.finish(db, {"state": handshake.state},
                                     transport=_RefusingTransport(), env=ENV)
    assert result.outcome == "unusable_callback"
    assert result.http_status == 400
    with db.session() as s:
        assert s.scalar(select(OAuthHandshake)).outcome == "unusable_callback"


def test_an_access_denied_redirect_is_reported_and_spends_the_state():
    db = _fresh_db()
    handshake = oauth_store.begin(db, verifier=etsy_oauth.new_verifier(),
                                  redirect_uri=REDIRECT_URI, env=ENV)
    result = etsy_authorise.finish(
        db, {"state": handshake.state, "error": "access_denied",
             "error_description": "The user denied your request."},
        transport=_RefusingTransport(), env=ENV)
    assert result.outcome == "etsy_refused"
    assert result.detail["etsy_error"] == "access_denied"
    # Presented once is used once, even when what was presented was a refusal.
    assert oauth_store.consume(db, state=handshake.state, env=ENV).verdict is (
        oauth_store.Verdict.STATE_REPLAYED)


def test_an_etsy_error_description_is_escaped_into_the_page():
    """The one place in this app that renders text which arrived on a URL from outside."""
    page = app_main._oauth_page(
        400, "Etsy did not grant access", "explanation", "what to do",
        {"etsy_error_description": "<script>alert('x')</script>"})
    text = page.body.decode()
    assert "<script>alert" not in text, "reflected script survived into the callback page"
    assert "&lt;script&gt;" in text


# ---------------------------------------------------------------------------
# The route: the success path, against a server on a socket


class _PinnedTransport(etsy_http.UrllibTransport):
    """Sends the grant to the fake, and records the URL the application asked for.

    This intercepts at the transport rather than through an environment override on purpose.
    An override would have let the application send the token request anywhere; this way the
    application still resolves Etsy's own host from `etsy_oauth`, and the test can *assert*
    which host that was.
    """

    fake_token_url = ""
    asked_for: list[str] = []

    def request(self, method, url, **kwargs):
        _PinnedTransport.asked_for.append(url)
        return super().request(method, self.fake_token_url, **kwargs)


def _run_callback_through_the_app(fake: FakeEtsy, params: dict) -> tuple[int, str]:
    _PinnedTransport.fake_token_url = fake.token_url
    _PinnedTransport.asked_for = []
    real = etsy_http.UrllibTransport
    etsy_http.UrllibTransport = _PinnedTransport
    try:
        with _client() as c:
            r = c.get("/api/etsy/oauth/callback", params=params)
            return r.status_code, r.text
    finally:
        etsy_http.UrllibTransport = real


def test_a_real_callback_exchanges_the_code_and_stores_the_refresh_token_sealed():
    with FakeEtsy() as fake:
        with _client() as c:
            started = c.get("/api/etsy/oauth/start",
                            headers={"Authorization": f"Bearer {OPS_TOKEN}"}).json()
        state = _state_from(started["authorize_url"])
        challenge = _param_from(started["authorize_url"], "code_challenge")
        code = fake.issue_authorization_code(challenge=challenge,
                                             redirect_uri=REDIRECT_URI)
        status, page = _run_callback_through_the_app(fake, {"code": code, "state": state})

    assert status == 200, page
    assert "Brambleloop is authorised on Etsy" in page
    assert fake.exchanges == 1, "the authorization code was not exchanged exactly once"
    # The grant went to a host Etsy's own documents name, and nowhere else.
    assert _PinnedTransport.asked_for == [etsy_oauth.TOKEN_URL], _PinnedTransport.asked_for

    with app_main.db.session() as s:
        row = s.scalar(select(OAuthCredential))
    assert row is not None and row.refresh_token_sealed.startswith("v1:")
    assert sealed.unseal(row.refresh_token_sealed,
                         context=oauth_store.REFRESH_TOKEN_CONTEXT) == (
        "111.granted-refresh-1")
    assert row.source == "authorization-code grant"
    assert row.rotations == 0


def test_nothing_in_the_page_the_log_or_the_audit_row_carries_a_secret():
    with FakeEtsy() as fake:
        with _client() as c:
            started = c.get("/api/etsy/oauth/start",
                            headers={"Authorization": f"Bearer {OPS_TOKEN}"}).json()
        state = _state_from(started["authorize_url"])
        verifier_challenge = _param_from(started["authorize_url"], "code_challenge")
        code = fake.issue_authorization_code(challenge=verifier_challenge,
                                             redirect_uri=REDIRECT_URI)
        status, page = _run_callback_through_the_app(fake, {"code": code, "state": state})
        assert status == 200, page
        leakable = _secrets_in_play(fake, extra=(code, state, OPS_TOKEN, SEAL_KEY))

    with app_main.db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(
            AuditLog.action.in_(("etsy.oauth_callback", "etsy.oauth_started")))))
        audits = repr([r.detail for r in rows])
        credentials = repr([{c.name: getattr(r, c.name) for c in r.__table__.columns}
                            for r in s.scalars(select(OAuthCredential))])
    assert rows, "the callback wrote no audit record at all"

    for secret in leakable:
        assert secret not in page, f"a secret reached the callback page: ***{secret[:4]}"
        assert secret not in audits, f"a secret reached an audit detail: ***{secret[:4]}"
        if secret != "111.granted-refresh-1":
            continue
        assert secret not in credentials, "the refresh token is stored in the clear"
    # And the status endpoint, which an operator reads while holding the ops token.
    with _client() as c:
        body = c.get("/api/etsy/oauth/status",
                     headers={"Authorization": f"Bearer {OPS_TOKEN}"}).text
    for secret in leakable:
        assert secret not in body, "a secret reached /api/etsy/oauth/status"


def test_the_access_log_cannot_print_an_authorization_code():
    """The leak no amount of care inside the application would have closed."""
    from brambleloop.app import access_log

    line = ('GET /api/etsy/oauth/callback?code=bftcubu-wownsvftz5kowdmxnqtsuoik'
            '&state=superstate HTTP/1.1')
    scrubbed = access_log.scrub_query(line)
    assert "bftcubu-wownsvftz5kowdmxnqtsuoik" not in scrubbed
    assert "superstate" not in scrubbed
    assert "/api/etsy/oauth/callback" in scrubbed and "code=***" in scrubbed
    # A path with nothing sensitive in it is left exactly as it was: a redactor that mangles
    # ordinary log lines is one somebody switches off.
    plain = 'GET /api/status?limit=50 HTTP/1.1'
    assert access_log.scrub_query(plain) == plain
    # And the filter is actually attached to the logger uvicorn writes through.
    import logging

    assert any(isinstance(f, access_log.QueryStringRedaction)
               for f in logging.getLogger("uvicorn.access").filters)


def test_a_duplicate_callback_delivered_twice_exchanges_once():
    with FakeEtsy() as fake:
        with _client() as c:
            started = c.get("/api/etsy/oauth/start",
                            headers={"Authorization": f"Bearer {OPS_TOKEN}"}).json()
        params = {"code": fake.issue_authorization_code(
            challenge=_param_from(started["authorize_url"], "code_challenge"),
            redirect_uri=REDIRECT_URI),
            "state": _state_from(started["authorize_url"])}
        first_status, _ = _run_callback_through_the_app(fake, params)
        second_status, second_page = _run_callback_through_the_app(fake, params)

    assert first_status == 200
    assert second_status == 409, second_page
    assert "already used" in second_page
    assert fake.exchanges == 1, (
        "the second delivery of the same callback reached Etsy. A single-use state is the "
        "only thing standing between this endpoint and an open code exchange")


def test_an_exchange_failure_is_reported_and_the_state_is_still_spent():
    db = _fresh_db()
    for status, label in ((400, "invalid_grant"), (403, "forbidden")):
        with FakeEtsy() as fake:
            fake.token_failure = (status, {"error": label,
                                           "error_description": f"Etsy said {status}"})
            app = etsy_oauth.OAuthApp(keystring=fake.keystring,
                                      shared_secret=fake.shared_secret,
                                      redirect_uri=REDIRECT_URI,
                                      token_url=fake.token_url)
            handshake = oauth_store.begin(db, verifier=etsy_oauth.new_verifier(),
                                          redirect_uri=REDIRECT_URI, env=ENV)
            result = _complete_with(db, app, fake,
                                    {"code": "any-code", "state": handshake.state})
        assert result.outcome == "exchange_failed", (status, result.outcome)
        assert result.http_status == 502
        assert oauth_store.consume(db, state=handshake.state, env=ENV).verdict is (
            oauth_store.Verdict.STATE_REPLAYED), (
            "a spent authorization code must not be retryable through the same state")
        with app_main_db_free(db) as s:
            assert s.scalar(select(OAuthCredential)) is None, (
                "a failed exchange wrote a credential")


def test_a_verifier_that_does_not_match_the_challenge_is_refused_by_the_server():
    """PKCE doing its job: this is why a stolen authorization code is not a credential."""
    db = _fresh_db()
    with FakeEtsy() as fake:
        app = etsy_oauth.OAuthApp(keystring=fake.keystring,
                                  shared_secret=fake.shared_secret,
                                  redirect_uri=REDIRECT_URI, token_url=fake.token_url)
        # A code issued against somebody else's challenge -- which is what a code lifted from
        # a proxy log looks like to the thief who did not generate the verifier.
        code = fake.issue_authorization_code(
            challenge=etsy_oauth.challenge(etsy_oauth.new_verifier()),
            redirect_uri=REDIRECT_URI)
        handshake = oauth_store.begin(db, verifier=etsy_oauth.new_verifier(),
                                      redirect_uri=REDIRECT_URI, env=ENV)
        result = _complete_with(db, app, fake, {"code": code, "state": handshake.state})
    assert result.outcome == "exchange_failed"
    assert "code_verifier" in result.detail["etsy_said"]


def test_a_token_echoed_back_inside_an_error_body_does_not_reach_the_report():
    """Lane C's redactor, reused rather than reinvented, on the path that matters here."""
    db = _fresh_db()
    with FakeEtsy() as fake:
        # An Etsy-shaped token: the granting user's numeric id, a dot, then the body. That
        # shape is what `http.TOKEN_SHAPED` recognises, and it is how a token really leaks --
        # inside prose, in a field nobody predicted, from a server with no business repeating
        # it. `tests/fake_etsy.py` already reproduces the same leak for bearer headers.
        leaked = "743219087.leaked-token-abcdefghijklmnop"
        fake.token_failure = (400, {
            "error": "invalid_grant",
            "error_description": f"the token {leaked} was already used"})
        app = etsy_oauth.OAuthApp(keystring=fake.keystring,
                                  shared_secret=fake.shared_secret,
                                  redirect_uri=REDIRECT_URI, token_url=fake.token_url)
        handshake = oauth_store.begin(db, verifier=etsy_oauth.new_verifier(),
                                      redirect_uri=REDIRECT_URI, env=ENV)
        result = _complete_with(db, app, fake,
                               {"code": "some-code", "state": handshake.state})
    assert leaked not in repr(result.to_dict())
    assert "***" in result.detail["etsy_said"]


# ---------------------------------------------------------------------------
# Rotation


def test_a_rotation_replaces_the_stored_token_and_counts_itself():
    db = _fresh_db()
    oauth_store.save_refresh_token(db, "111.first", source="authorization-code grant",
                                   new_grant=True, env=ENV)
    first = sealed.fingerprint("111.first")
    oauth_store.save_refresh_token(db, "111.second", expected_fingerprint=first,
                                   source="refresh grant", env=ENV)
    assert oauth_store.load_refresh_token(db, env=ENV) == "111.second"
    health = oauth_store.credential_health(db, env=ENV)
    assert health["rotations"] == 1
    assert health["token_fingerprint"] == f"***{sealed.fingerprint('111.second')}"
    assert health["openable"] is True


def test_a_rotation_that_lost_a_race_is_refused_rather_than_overwriting_a_live_token():
    db = _fresh_db()
    oauth_store.save_refresh_token(db, "111.first", new_grant=True, env=ENV)
    stale = sealed.fingerprint("111.first")
    oauth_store.save_refresh_token(db, "111.winner", expected_fingerprint=stale, env=ENV)
    try:
        oauth_store.save_refresh_token(db, "111.loser", expected_fingerprint=stale, env=ENV)
    except oauth_store.CredentialConflict as exc:
        assert "111.loser" not in str(exc) and "111.winner" not in str(exc), (
            "the conflict message quoted a token instead of a fingerprint")
    else:
        raise AssertionError("a stale rotation overwrote a newer credential")
    assert oauth_store.load_refresh_token(db, env=ENV) == "111.winner"


def test_the_publish_path_reads_the_stored_credential_and_writes_rotations_back():
    """`Credentials.from_env(db=...)` is what makes a refresh survive a restart."""
    from brambleloop.integrations.etsy import Credentials

    db = _fresh_db()
    with FakeEtsy() as fake:
        oauth_store.save_refresh_token(db, "111.refresh-one", new_grant=True, env=ENV)
        env = dict(ENV, ETSY_SHOP_ID=fake.shop_id, ETSY_KEYSTRING=fake.keystring)
        transport = etsy_http.UrllibTransport()
        credentials = Credentials.from_env(env, transport=transport, db=db)
        assert credentials is not None and credentials.token_provider is not None
        # Point the provider's app at the fake without touching how it was built.
        credentials.token_provider.app = etsy_oauth.OAuthApp(
            keystring=fake.keystring, shared_secret=fake.shared_secret,
            redirect_uri=REDIRECT_URI, token_url=fake.token_url)
        # No stated expiry means "already expired", so this forces exactly one refresh.
        token = credentials.token_provider.token(operation="createDraftListing")
        assert token.startswith("111.access-")

    stored = oauth_store.load_refresh_token(db, env=ENV)
    assert stored == "111.refresh-2", (
        "the rotated refresh token was not written back. Etsy spends the old one, so this is "
        "the difference between a system that keeps working and one that needs the owner's "
        "browser after the next container replacement")
    assert oauth_store.credential_health(db, env=ENV)["rotations"] == 1


def test_a_credential_sealed_under_a_key_the_deployment_no_longer_has_reads_as_unusable():
    db = _fresh_db()
    oauth_store.save_refresh_token(db, "111.token", new_grant=True, env=ENV)
    other = {"BRAMBLELOOP_SECRET_KEY": "a-different-key-that-is-also-long-enough-0123456789"}
    assert oauth_store.load_refresh_token(db, env=other) is None, (
        "a credential must not be half-recovered under the wrong key")
    health = oauth_store.credential_health(db, env=other)
    assert health["stored"] is True and health["openable"] is False, (
        "a stored credential that cannot be opened looks present in every other report; this "
        "is the one field that says otherwise")


# ---------------------------------------------------------------------------
# Interactions this work must not break


def test_retention_never_prunes_the_credential_and_never_prunes_a_live_handshake():
    db = _fresh_db()
    oauth_store.save_refresh_token(db, "111.keep-me", new_grant=True, env=ENV)
    live = oauth_store.begin(db, verifier=etsy_oauth.new_verifier(),
                             redirect_uri=REDIRECT_URI, env=ENV)
    spent = oauth_store.begin(db, verifier=etsy_oauth.new_verifier(),
                              redirect_uri=REDIRECT_URI, env=ENV)
    oauth_store.consume(db, state=spent.state, env=ENV)
    with db.session() as s:
        row = s.scalar(select(OAuthHandshake).where(OAuthHandshake.id == spent.row_id))
        row.consumed_at = utcnow() - timedelta(days=oauth_store.REPLAY_MEMORY_DAYS + 5)

    result = retention.apply(db)
    assert result["removed"]["oauth_handshakes"] == 1
    with db.session() as s:
        left = [r.id for r in s.scalars(select(OAuthHandshake))]
        assert left == [live.row_id], "retention deleted a live handshake"
        assert s.scalar(select(OAuthCredential)) is not None, (
            "retention deleted the company's Etsy credential")
    assert "oauth_credentials" in retention.state()["never_pruned"]
    assert "oauth_credentials" in retention.plan(db)["never_touched"]


def test_retention_still_knows_every_audit_action_the_source_reads_by_name():
    assert retention.unknown_read_actions() == [], (
        "an audit action is read by name in `src/` with no retention decision recorded")
    assert "etsy.oauth_callback" in retention.KNOWN_READ_ACTIONS


def test_a_continuity_export_does_not_carry_the_credential_or_a_handshake():
    from brambleloop.core import continuity

    for table in ("oauth_credentials", "oauth_handshakes"):
        assert table in continuity.EXCLUDED_TABLES, (
            f"{table} would be written into a portable export that "
            f"/api/continuity/export serves as a download")
    db = _fresh_db()
    oauth_store.save_refresh_token(db, "111.must-not-be-exported", new_grant=True, env=ENV)
    out = Path(tempfile.mkdtemp(prefix="export-")) / "export.jsonl"
    continuity.export(db, out)
    text = out.read_text()
    assert "111.must-not-be-exported" not in text
    assert "oauth_credentials" not in [line for line in text.splitlines()
                                       if '"__table__"' in line and "oauth" in line]


def test_the_verify_endpoint_still_reports_twelve_checks():
    with _client() as c:
        body = c.get("/api/verify").json()
    assert len(body["checks"]) == 12, [c["check"] for c in body["checks"]]
    assert body["checks"][0]["check"] == "phase_is_shadow"


def test_authenticating_is_not_a_publication_and_the_activation_gates_are_untouched():
    """Shadow mode must not block authentication, and this work must not loosen activation."""
    from brambleloop.integrations import etsy as etsy_module

    source = (ROOT / "src/brambleloop/integrations/etsy_authorise.py").read_text()
    import re

    # Docstrings and comments removed, so this asks what the module *does* rather than what
    # it says about what it deliberately does not do.
    code_only = re.sub(r'""".*?"""', "", source, flags=re.S)
    code_only = "\n".join(line for line in code_only.splitlines()
                          if not line.lstrip().startswith("#"))
    for forbidden in ("EtsyClient", "activate(", "createDraftListing", "updateListing",
                      "deleteListing", "uploadListingImage"):
        assert forbidden not in code_only, (
            f"the authorization flow references {forbidden}; authenticating creates nothing")
    assert etsy_module.PHASES_THAT_MAY_PUBLISH == ("limited_production", "production")
    # `authorize_url` and `complete` do not consult the phase at all -- deliberately, because
    # refusing to authenticate in SHADOW would mean the first authentication ever attempted
    # happened on the day the shop opened.
    assert "BRAMBLELOOP_PHASE" not in code_only
    # And the three activation gates are exactly as they were.
    activate_source = (ROOT / "src/brambleloop/integrations/etsy.py").read_text()
    for gate in ("PHASES_THAT_MAY_PUBLISH", "owner_authorised", "launch_authorisation"):
        assert gate in activate_source, f"activation lost its {gate} gate"


def test_the_redirect_uri_rules_etsy_publishes_are_enforced_before_the_owner_sees_a_browser():
    bad = {
        "http://example.com/cb": "https",
        "https://example.com/cb ": "whitespace",
        "https://example.com/cb#frag": "fragment",
        "https://example.com/cb?": "?",
        "": "no redirect URI",
    }
    for value, because in bad.items():
        problem = etsy_oauth.redirect_uri_problem(value)
        assert problem, f"{value!r} was accepted; it fails on {because}"
    assert etsy_oauth.redirect_uri_problem(REDIRECT_URI) == ""
    # A trailing slash is a *different* URL to Etsy, not an invalid one, so it is not
    # rejected here -- only Etsy can say whether it matches a registration. What is checked
    # is that the configuration report notices a path this service does not answer on.
    config = etsy_authorise.configuration(
        dict(ENV, ETSY_REDIRECT_URI="https://example.com/somewhere-else"))
    assert any(etsy_authorise.CALLBACK_PATH in p for p in config["problems"])


def test_the_token_endpoint_host_is_one_named_constant_with_its_source_beside_it():
    assert etsy_oauth.TOKEN_URL == "https://api.etsy.com/v3/public/oauth/token"
    assert etsy_oauth.TOKEN_URL_ALTERNATE == "https://openapi.etsy.com/v3/public/oauth/token"
    assert "equivalent" in etsy_oauth.TOKEN_HOSTS_ARE_EQUIVALENT
    assert etsy_oauth.STATE_IS_REQUIRED_BY_ETSY is False


# ---------------------------------------------------------------------------
# helpers


def _param_from(url: str, name: str) -> str:
    import urllib.parse

    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)[name][0]


def _state_from(url: str) -> str:
    return _param_from(url, "state")


def _complete_with(db, app, fake, params):
    """Run `complete` with an app pointed at the fake, without touching the environment."""
    real = etsy_oauth.OAuthApp.from_env
    etsy_oauth.OAuthApp.from_env = staticmethod(lambda env=None: app)
    try:
        return etsy_authorise.finish(db, params,
                                       transport=etsy_http.UrllibTransport(), env=ENV)
    finally:
        etsy_oauth.OAuthApp.from_env = real


class app_main_db_free:
    """A session on a test database, spelled so the assertion above reads plainly."""

    def __init__(self, db) -> None:
        self._db = db
        self._cm = None

    def __enter__(self):
        self._cm = self._db.session()
        return self._cm.__enter__()

    def __exit__(self, *exc):
        return self._cm.__exit__(*exc)


def _run_all() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
            import traceback

            traceback.print_exc()
        else:
            print(f"OK   {name}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run_all() else 0)
