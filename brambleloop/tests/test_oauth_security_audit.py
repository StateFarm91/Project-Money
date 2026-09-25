"""An adversarial audit of the Etsy / OAuth paths, against one sentence.

    No authorization code, access token, refresh token, shared secret, PKCE verifier,
    encryption key or operator token may reach a log, report, artifact, audit row or
    exception body.

`tests/test_etsy_oauth_callback.py` proves the callback holds that line. This file is the
other direction: it goes looking for the places the line is crossed, and where it finds one it
reproduces the crossing rather than describing it. Two are found, and both are in files this
lane does not own, so they are proven here and written up as diffs in
`research/OAUTH_SECURITY_AUDIT.md`.

  1. **The refresh path has no redactor at all.** `etsy_oauth._token_request` builds its
     exception message out of Etsy's own response body -- `error_description`, or the WHOLE
     body when Etsy names neither `error` nor `error_description`. On the callback that
     message is caught and passed through `Redactor`. On the refresh it is not caught by
     anything that redacts: it rises through `TokenProvider.token()` into whatever asked for
     a token, and `runtime.worker` writes `str(e)` verbatim into an `AuditLog.detail` and
     into `Job.last_error`. Both tables are in the continuity export and in `pg_dump`, in the
     clear -- unlike `oauth_credentials`, which is ciphertext. So an Etsy error body that
     quotes the refresh token back at us becomes a durable, exportable copy of the company's
     only write credential. `tests/fake_etsy.py` already carries `echo_token_in_error`
     because a real API has been seen doing exactly that.

  2. **The access-log filter can be walked around with a percent-encoded parameter name.**
     `%63ode=` is `code=` to `urllib.parse.parse_qsl`, which is what Starlette parses the
     query with, and is not `code=` to `access_log._PARAM`, which matches literal names. The
     application reads the value as the authorization code; the access log prints it whole.

Everything else audited is asserted here as an invariant so that it keeps holding: the
fingerprint discipline, the sealing boundary, the handshake vocabulary, retention, process
replacement and spend. Nothing in this file touches Etsy, spends anything, or reads a real
credential: every secret below is a literal invented by the test.
"""
from __future__ import annotations

import json
import logging
import logging.config
import os
import re
import sys
import tempfile
import time
import urllib.parse
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.TemporaryDirectory()
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP.name}/audit.sqlite"
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ["BRAMBLELOOP_PHASE"] = "shadow"

SEAL_KEY = "an-audit-sealing-key-of-quite-sufficient-length-0123456789"
os.environ["BRAMBLELOOP_SECRET_KEY"] = SEAL_KEY

from sqlalchemy import select                                            # noqa: E402

from brambleloop.agents.registry import Registry                         # noqa: E402
from brambleloop.app import access_log                                   # noqa: E402
from brambleloop.core import oauth_store, sealed                         # noqa: E402
from brambleloop.core.db import Database                                 # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry, Job             # noqa: E402
from brambleloop.integrations import etsy_authorise, etsy_oauth          # noqa: E402
from brambleloop.integrations.etsy import (                              # noqa: E402
    Credentials, Response, _persisting_on_refresh,
)
from brambleloop.integrations.http import Redactor, fingerprint          # noqa: E402
from brambleloop.queue.durable import JobQueue                           # noqa: E402
from brambleloop.runtime.worker import HandlerRegistry, Worker           # noqa: E402

PASSED = FAILED_N = 0


def check(name, ok, detail=""):
    global PASSED, FAILED_N
    if ok:
        PASSED += 1
        print("OK  ", name)
    else:
        FAILED_N += 1
        print("FAIL", name, detail)


# Invented secrets. Shaped like the real ones so the shape-based half of the redactor is
# exercised honestly, and none of them is, or has ever been, a credential of this company.
REFRESH_TOKEN = "111111.rYQ6bF3k9sZ2wQ8tL4vN1pM7xJ0hG5dCzA3eW"
ROTATED_TOKEN = "111111.kP2nX8vB4tR6yH0jL3mQ9wZ1sD5fG7cVuI4oA"
ACCESS_TOKEN = "111111.aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5bC"
AUTH_CODE = "bftcubu-Xq2W4e6R8t0Y2u4I6o8P0aS2d4F6g8H0j2K4l6"
VERIFIER = "sJ9kL1mN3pQ5rS7tU9vW1xY3zA5bC7dE9fG1hJ3kL5m"
SHARED_SECRET = "fakesharedsecret-not-a-real-one"
REDIRECT_URI = "https://brambleloop.example/api/etsy/oauth/callback"

APP = etsy_oauth.OAuthApp(keystring="fakekeystring", shared_secret=SHARED_SECRET,
                          redirect_uri=REDIRECT_URI,
                          token_url="https://api.etsy.com/v3/public/oauth/token")


class Echoing:
    """A token endpoint that quotes back what was sent to it, which real ones do.

    Not invented for this test: `tests/fake_etsy.py` carries `echo_token_in_error` for the
    same reason, and the comment beside it says a real API has been observed doing it. The
    point of redaction by VALUE rather than only by field name is exactly this case -- a
    secret arriving in prose, in a field nobody predicted.
    """

    def __init__(self, body, status=400):
        self.body, self.status = body, status
        self.sent: list[dict] = []

    def request(self, method, url, *, headers, json=None, form=None, multipart=None):
        self.sent.append(dict(form or {}))
        return Response(status=self.status, body=self.body)


# =========================================================================================
# A. THE LEAK: an Etsy error body reaches an audit row through the refresh path, unredacted
# =========================================================================================

# A1. The exception message is built out of Etsy's words and nothing filters it.
echo = Echoing({"error": "invalid_grant",
                "error_description": f"refresh token {REFRESH_TOKEN} has already been used"})
try:
    etsy_oauth.refresh(echo, APP, REFRESH_TOKEN)
    message = ""
except etsy_oauth.EtsyAuthNeedsOwner as exc:
    message = str(exc)

check("REPRODUCED: an echoed refresh token survives into the exception message",
      REFRESH_TOKEN in message, message[:120])

# A2. The fallback is worse than the echo: with neither `error` nor `error_description`,
# `detail` becomes the entire response body, so every field Etsy chose to include -- including
# any it copied from our own form -- is rendered into the message by `str(dict)`.
try:
    etsy_oauth.refresh(Echoing({"submitted": {"refresh_token": REFRESH_TOKEN}}),
                       APP, REFRESH_TOKEN)
    whole_body = ""
except etsy_oauth.EtsyAuthNeedsOwner as exc:
    whole_body = str(exc)

check("REPRODUCED: with no named error field the whole response body becomes the message",
      REFRESH_TOKEN in whole_body, whole_body[:120])

# A3. Where that message lands. Not argued -- run, through the real worker, the real queue
# and a real database, on the job type that actually reaches a refresh (`store.publish` builds
# its credentials with a `TokenProvider`, and a token is fetched when the request headers are
# built). The handler below raises precisely what `_token_request` raised above.
_DB = Database(f"sqlite:///{_TMP.name}/audit.sqlite")
_DB.create_all()
Registry(_DB).seed_defaults()

_handlers = HandlerRegistry()


@_handlers.register("store.publish")
def _publish_that_needs_a_token(ctx):
    raise etsy_oauth.EtsyAuthNeedsOwner(message)


JobQueue(_DB).enqueue("store_operator", "store.publish", {"slug": "audit-fixture"})
Worker(_DB, "audit-worker", registry=_handlers).run_once()

with _DB.session() as s:
    rows = [a for a in s.scalars(select(AuditLog)) if a.action == "job.failed"]
    audit_detail = json.dumps([r.detail for r in rows])
    job_errors = "\n".join(j.last_error or "" for j in s.scalars(select(Job)))

check("REPRODUCED: the token is written verbatim into an audit row",
      REFRESH_TOKEN in audit_detail, audit_detail[:160])
check("REPRODUCED: and into the job's durable last_error, with a traceback beside it",
      REFRESH_TOKEN in job_errors, job_errors[:160])

# A4. Why that matters more than a log line: those two tables leave the database.
from brambleloop.core import continuity                                  # noqa: E402

check("and both tables are inside the continuity export, which is served as a download",
      "audit_log" in continuity.NON_REDERIVABLE and "jobs" in continuity.NON_REDERIVABLE
      and "audit_log" not in continuity.EXCLUDED_TABLES
      and "jobs" not in continuity.EXCLUDED_TABLES)
check("while the credential table itself is excluded, so the leak is in the clear and the "
      "credential is not",
      "oauth_credentials" in continuity.EXCLUDED_TABLES
      and "oauth_handshakes" in continuity.EXCLUDED_TABLES)

# A5. The fix, measured rather than asserted. `Redactor` needs nothing registered to catch
# this: `TOKEN_SHAPED` recognises an Etsy token by shape wherever it appears, including inside
# a sentence. So the whole repair is to build the message through a redactor.
check("THE FIX HOLDS: an unseeded Redactor already removes it by shape alone",
      REFRESH_TOKEN not in Redactor().string(message)
      and f"***{fingerprint(REFRESH_TOKEN)}" in Redactor().string(message),
      Redactor().string(message)[:120])
check("and the same redactor removes it from the whole-body form too",
      REFRESH_TOKEN not in Redactor().string(whole_body))
check("the fingerprint is not a prefix of the token: it is a digest",
      not REFRESH_TOKEN.startswith(fingerprint(REFRESH_TOKEN)))

# The proposed repair seeds that redactor from the request's own form, and WHICH fields it
# seeds from is the difference between a redactor and a mangler: `form.values()` would
# register `grant_type` -- whose value is the literal string "refresh_token" -- and the error
# message would come out with its own field names replaced by fingerprints. That is the
# `token_type` argument again, and a redactor nobody can read is one somebody switches off.
from brambleloop.integrations.http import SECRET_KEYS                    # noqa: E402

_form = {"grant_type": "refresh_token", "client_id": "fakekeystring",
         "refresh_token": REFRESH_TOKEN}
_naive = Redactor(_form.values())
_tight = Redactor(v for k, v in _form.items() if k.lower() in SECRET_KEYS)
_body = str({"submitted": {"refresh_token": REFRESH_TOKEN}, "grant_type": "refresh_token"})

check("seeding from the form's SECRET_KEYS fields removes the token and nothing else",
      REFRESH_TOKEN not in _tight.string(_body)
      and "'grant_type': 'refresh_token'" in _tight.string(_body), _tight.string(_body))
check("seeding from every form value would fingerprint the field names too: do not",
      "'grant_type': 'refresh_token'" not in _naive.string(_body)
      and "refresh_token" not in _naive.string(_body), _naive.string(_body))

# A6. The asymmetry is the finding, so the other side is exercised in the same run: the
# callback DOES redact, against the same echoing server, through the real `finish`.
_CB = Database(f"sqlite:///{_TMP.name}/callback.sqlite")
_CB.create_all()
_ENV = {"BRAMBLELOOP_SECRET_KEY": SEAL_KEY, "ETSY_KEYSTRING": "fakekeystring",
        "ETSY_SHARED_SECRET": SHARED_SECRET, "ETSY_REDIRECT_URI": REDIRECT_URI}

handshake = oauth_store.begin(_CB, provider="etsy", verifier=VERIFIER,
                              redirect_uri=REDIRECT_URI, scopes="shops_r", env=_ENV)
completed = etsy_authorise.finish(
    _CB, {"code": AUTH_CODE, "state": handshake.state},
    transport=Echoing({"error": "invalid_grant",
                       "error_description": (f"code {AUTH_CODE} and verifier {VERIFIER} "
                                             f"and token {ACCESS_TOKEN} were rejected")}),
    env=_ENV)
rendered = json.dumps(completed.to_dict())

check("the CALLBACK path redacts the same Etsy body: no authorization code reaches the page",
      AUTH_CODE not in rendered, rendered[:160])
check("no PKCE verifier reaches it either",
      VERIFIER not in rendered, rendered[:160])
check("and an access token echoed in the same sentence is caught by shape",
      ACCESS_TOKEN not in rendered, rendered[:160])
check("so the leak is an ASYMMETRY, not a missing mechanism: one path redacts, one does not",
      AUTH_CODE not in rendered and REFRESH_TOKEN in message)

# A7. An injected defect, so that A6 cannot be vacuously green: remove the redaction that
# `finish` performs and the same call renders the code.
_real_string = Redactor.string
try:
    Redactor.string = lambda self, text: text            # type: ignore[assignment]
    hs2 = oauth_store.begin(_CB, provider="etsy", verifier=VERIFIER,
                            redirect_uri=REDIRECT_URI, scopes="shops_r", env=_ENV)
    broken = etsy_authorise.finish(
        _CB, {"code": AUTH_CODE, "state": hs2.state},
        transport=Echoing({"error": "invalid_grant",
                           "error_description": f"code {AUTH_CODE} was rejected"}),
        env=_ENV)
    leaked = json.dumps(broken.to_dict())
finally:
    Redactor.string = _real_string                       # type: ignore[assignment]

check("INJECTED DEFECT: with Redactor.string neutered the callback does render the code",
      AUTH_CODE in leaked, leaked[:160])
check("and the real code refuses it again once the defect is removed",
      AUTH_CODE not in json.dumps(etsy_authorise.finish(
          _CB,
          {"code": AUTH_CODE,
           "state": oauth_store.begin(_CB, provider="etsy", verifier=VERIFIER,
                                      redirect_uri=REDIRECT_URI, env=_ENV).state},
          transport=Echoing({"error": "invalid_grant",
                             "error_description": f"code {AUTH_CODE} was rejected"}),
          env=_ENV).to_dict()))


# =========================================================================================
# B. THE ACCESS LOG: the request line IS the credential, and one way around the filter
# =========================================================================================

REAL_LINE = (f'127.0.0.1:0 - "GET /api/etsy/oauth/callback?code={AUTH_CODE}'
             f'&state=aVeryLongOpaqueStateValue HTTP/1.1" 200')

scrubbed = access_log.scrub_query(REAL_LINE)
check("the shape uvicorn actually writes is scrubbed: no authorization code in the line",
      AUTH_CODE not in scrubbed, scrubbed)
check("the state is scrubbed too, because a URL is the one place it can be replayed from",
      "aVeryLongOpaqueStateValue" not in scrubbed, scrubbed)
check("the path, the method and the status survive, so the log still answers its questions",
      "/api/etsy/oauth/callback" in scrubbed and "GET" in scrubbed
      and scrubbed.endswith('200'), scrubbed)
check("both values are replaced by the same fingerprints the rest of the system uses",
      f"code=***{fingerprint(AUTH_CODE)}" in scrubbed, scrubbed)
check("an ordinary request line is byte-identical after the filter",
      access_log.scrub_query('127.0.0.1:0 - "GET /api/verify?deep=1 HTTP/1.1" 200')
      == '127.0.0.1:0 - "GET /api/verify?deep=1 HTTP/1.1" 200')

# The filter has to catch the record whichever way the server formats it.
_rec = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1,
                         '%s - "%s %s HTTP/%s" %d',
                         ("127.0.0.1:0", "GET",
                          f"/api/etsy/oauth/callback?code={AUTH_CODE}", "1.1", 200), None)
access_log.QueryStringRedaction().filter(_rec)
check("a lazily formatted record is scrubbed through record.args",
      AUTH_CODE not in _rec.getMessage(), _rec.getMessage())

_rec2 = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, REAL_LINE, (), None)
access_log.QueryStringRedaction().filter(_rec2)
check("an eagerly formatted record is scrubbed through record.msg",
      AUTH_CODE not in _rec2.getMessage(), _rec2.getMessage())


class _Hostile(str):
    """A message object whose formatting explodes. A redactor must not print it anyway."""

    def __contains__(self, other):                       # pragma: no cover - defensive
        raise RuntimeError("no")


_rec3 = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, _Hostile(REAL_LINE),
                          (), None)
access_log.QueryStringRedaction().filter(_rec3)
check("a filter that cannot do its job suppresses the line rather than printing the secret",
      AUTH_CODE not in _rec3.getMessage(), _rec3.getMessage()[:80])

# Installation order was the residual doubt: uvicorn configures logging before it imports the
# app, and `install()` runs at app import. Anything that reconfigures logging afterwards -- a
# `dictConfig` from a supervisor -- replaces the HANDLERS. What matters is that the filter on
# the LOGGER survives, because it rewrites the record before any handler sees it.
access_log.install()
before = len(logging.getLogger("uvicorn.access").filters)
try:
    from uvicorn.config import LOGGING_CONFIG

    logging.config.dictConfig(LOGGING_CONFIG)
    after_logger = logging.getLogger("uvicorn.access")
    check("the redaction filter survives a later dictConfig on the access logger",
          before >= 1 and len(after_logger.filters) >= 1,
          f"{before} -> {len(after_logger.filters)}")
    _rec4 = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, REAL_LINE,
                              (), None)
    for f in after_logger.filters:
        f.filter(_rec4)
    check("and still scrubs after it, which is what makes handler replacement survivable",
          AUTH_CODE not in _rec4.getMessage(), _rec4.getMessage()[:80])
except ImportError:                                      # pragma: no cover
    check("uvicorn is importable so the installation order can be checked", False,
          "uvicorn not installed")

check("install() is idempotent, so a re-import cannot stack filters",
      len(access_log.install()) == len(access_log.LOGGERS))

# --- the bypass -------------------------------------------------------------------------
# `_PARAM` matches a literal parameter name. Starlette reads the query with
# `urllib.parse.parse_qsl`, which percent-decodes the NAME as well as the value. So there is
# a spelling of `code` that the application honours and the scrubber does not recognise.
ENCODED = f'127.0.0.1:0 - "GET /api/etsy/oauth/callback?%63ode={AUTH_CODE} HTTP/1.1" 200'
bypassed = access_log.scrub_query(ENCODED)
parsed = dict(urllib.parse.parse_qsl(f"%63ode={AUTH_CODE}"))

check("REPRODUCED: a percent-encoded parameter name is not recognised by the scrubber",
      AUTH_CODE in bypassed, bypassed)
check("while the application parses that exact spelling as `code`",
      parsed.get("code") == AUTH_CODE, str(parsed))


check("the name charset is half of why: `%` is not in it, so `%63ode=` matches nothing",
      access_log._PARAM.match("?%63ode=x") is None)

# The proposed repair, kept here rather than applied because `app/access_log.py` belongs to
# another lane. Two halves, and both are needed: `%` joins the name charset so an encoded
# name is seen at all, and the name is percent-decoded before it is looked up. The VALUE is
# deliberately left alone -- it is fingerprinted, and fingerprinting the bytes that were
# actually on the wire is the honest thing to do.
_PARAM_FIXED = re.compile(r"([?&])([A-Za-z0-9_.%\-]{1,64})=([^&\s\"']*)")


def _scrub_query_fixed(text: str) -> str:
    if "?" not in text:
        return text

    def one(match: re.Match) -> str:
        sep, name, value = match.group(1), match.group(2), match.group(3)
        decoded = urllib.parse.unquote(name)
        if decoded.strip().lower() not in access_log.SCRUBBED_QUERY_KEYS or not value:
            return match.group(0)
        return f"{sep}{name}=***{fingerprint(value)}"

    return _PARAM_FIXED.sub(one, text)


check("THE FIX HOLDS: widening the charset and decoding the name closes the bypass",
      AUTH_CODE not in _scrub_query_fixed(ENCODED), _scrub_query_fixed(ENCODED))
check("and it fingerprints the same value, so one secret still has one identity",
      f"***{fingerprint(AUTH_CODE)}" in _scrub_query_fixed(ENCODED),
      _scrub_query_fixed(ENCODED))
check("and the fix leaves the ordinary case byte-identical to what ships today",
      _scrub_query_fixed(REAL_LINE) == scrubbed)
check("and leaves an ordinary line alone, so nothing operational is lost",
      _scrub_query_fixed('127.0.0.1:0 - "GET /api/verify?deep=1 HTTP/1.1" 200')
      == '127.0.0.1:0 - "GET /api/verify?deep=1 HTTP/1.1" 200')


# =========================================================================================
# C. ROTATION: what a losing compare-and-set does to the NEXT write
# =========================================================================================
# Etsy issues a new refresh token on every refresh and spends the old one, so two containers
# -- which this platform creates routinely during a deploy roll -- can both be holding a
# chain. `_persisting_on_refresh` guards the first collision with compare-and-set. The
# question this audit asks is what the loser does afterwards, because process replacement is
# the boundary the original board defect hid behind.
_ROT = Database(f"sqlite:///{_TMP.name}/rotation.sqlite")
_ROT.create_all()


class _Tokens:
    def __init__(self, refresh_token):
        self.refresh_token = refresh_token
        self.scopes = ("shops_r",)


T0, T1_A, T1_B, T2_B = REFRESH_TOKEN, ROTATED_TOKEN, ACCESS_TOKEN, AUTH_CODE + "zz1234567890"

oauth_store.save_refresh_token(_ROT, T0, new_grant=True, env=_ENV)
loser = _persisting_on_refresh(_ROT, _ENV, current_token=T0)

# Container A refreshes first and wins the row.
oauth_store.save_refresh_token(_ROT, T1_A, expected_fingerprint=sealed.fingerprint(T0),
                               env=_ENV)
# Container B refreshed inside whatever grace window Etsy allows and loses the claim.
loser(_Tokens(T1_B))
check("the compare-and-set holds the first time: the loser does not overwrite the winner",
      oauth_store.credential_health(_ROT, env=_ENV)["token_fingerprint"]
      == f"***{sealed.fingerprint(T1_A)}")

# An hour later container B refreshes again. Its closure set `expected` to None after the
# conflict, so this write names nothing and is unconditional.
loser(_Tokens(T2_B))
after = oauth_store.credential_health(_ROT, env=_ENV)
check("REPRODUCED: the loser's NEXT rotation overwrites the winner's live credential",
      after["token_fingerprint"] == f"***{sealed.fingerprint(T2_B)}", str(after))
check("which contradicts the closure's own docstring, so one of the two has to move",
      "adopts whatever is there" in (_persisting_on_refresh.__doc__ or ""))
check("and the rotation count keeps rising, so nothing in the numbers shows the fork",
      after["rotations"] >= 2, str(after))

# The shape the repair has to have, asserted as a property rather than as an implementation:
# once a worker has lost a claim, its later writes must not be able to replace a row it can
# no longer name. `save_refresh_token` already refuses when the expectation is wrong -- the
# repair is to keep naming an expectation instead of dropping it.
try:
    oauth_store.save_refresh_token(_ROT, "111111.somethingElseEntirely0123456789abcd",
                                   expected_fingerprint=sealed.fingerprint(T1_A), env=_ENV)
    refused = False
except oauth_store.CredentialConflict as exc:
    refused = True
    conflict_text = str(exc)
check("THE FIX HOLDS: a write that names a stale token is already refused by the store",
      refused)
check("and the refusal names both sides by fingerprint and neither by value",
      "***" in conflict_text and T1_A not in conflict_text
      and sealed.fingerprint(T1_A) in conflict_text, conflict_text[:160])


# =========================================================================================
# D. THE INVARIANTS THAT HOLD. Asserted so they keep holding.
# =========================================================================================
_SECRETS = (REFRESH_TOKEN, ACCESS_TOKEN, AUTH_CODE, VERIFIER, SHARED_SECRET, SEAL_KEY)


def clean(blob, *, allow=()) -> bool:
    text = blob if isinstance(blob, str) else json.dumps(blob, default=str)
    return not any(s in text for s in _SECRETS if s not in allow)


# -- sealing ------------------------------------------------------------------------------
box = sealed.seal(REFRESH_TOKEN, context=oauth_store.REFRESH_TOKEN_CONTEXT, env=_ENV)
check("a sealed value contains neither the plaintext nor the key", clean(box), box[:60])
check("and it opens again under the same key and context",
      sealed.unseal(box, context=oauth_store.REFRESH_TOKEN_CONTEXT, env=_ENV)
      == REFRESH_TOKEN)

try:
    sealed.unseal(box, context=oauth_store.VERIFIER_CONTEXT, env=_ENV)
    context_bound = False
except sealed.SealBroken as exc:
    context_bound = True
    seal_error = str(exc)
check("a verifier's context cannot open a refresh token's ciphertext", context_bound)
check("and the refusal carries no plaintext, no key and no ciphertext",
      clean(seal_error) and box[10:40] not in seal_error, seal_error[:160])

try:
    sealed.unseal(box, context=oauth_store.REFRESH_TOKEN_CONTEXT,
                  env={"BRAMBLELOOP_SECRET_KEY": "a-completely-different-key-0123456789ab"})
    wrong_key = ""
except sealed.SealBroken as exc:
    wrong_key = str(exc)
check("a wrong key is refused, and refused in the same words as a wrong context, so the "
      "error is not an oracle",
      wrong_key and wrong_key.split("(")[0] == seal_error.split("(")[0], wrong_key[:80])

health = sealed.key_health(_ENV)
check("key_health never returns the key", clean(health), str(health))
check("and its fingerprint is a digest, not a prefix of the key",
      not SEAL_KEY.startswith(health["key_fingerprint"]), str(health))

# -- the handshake vocabulary --------------------------------------------------------------
for verdict in oauth_store.Verdict:
    c = oauth_store.Consumed(verdict=verdict, verifier=VERIFIER, fingerprint="deadbeef")
    check(f"Consumed.redacted() carries no verifier for {verdict.value}",
          clean(c.redacted()), str(c.redacted()))

check("credential_health reports the credential without any part of it",
      clean(oauth_store.credential_health(_ROT, env=_ENV)))
check("save_refresh_token returns fingerprints only",
      clean(oauth_store.save_refresh_token(_ROT, REFRESH_TOKEN, new_grant=True, env=_ENV)))
check("a state is never stored in a replayable form: only its SHA-256 and a fingerprint",
      oauth_store.state_hash("a-state") != "a-state"
      and len(oauth_store.state_hash("a-state")) == 64)

# -- reprs, which is where a secret reaches a traceback --------------------------------------
tokens = etsy_oauth.TokenSet(access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN,
                             expires_at=time.time() + 3600, scopes=("shops_r",))
check("TokenSet.redacted() and its repr carry no token",
      clean(tokens.redacted()) and clean(repr(tokens)), repr(tokens)[:120])
check("OAuthApp's repr carries no keystring and no shared secret", clean(repr(APP)),
      repr(APP)[:120])
check("Credentials' repr carries neither key, secret nor access token",
      clean(repr(Credentials(api_key="fakekeystring", access_token=ACCESS_TOKEN,
                             shop_id="12345", shared_secret=SHARED_SECRET))))

# -- the redactor's deliberate narrowness ---------------------------------------------------
red = Redactor([SHARED_SECRET])
check("a secret is removed by field name whatever its value looks like",
      clean(red({"access_token": "short"}) | {"x": 1}, allow=_SECRETS[:0])
      and red({"access_token": "shortish-value"})["access_token"].startswith("***"))
check("and by value, wherever in a sentence it appears",
      SHARED_SECRET not in json.dumps(red({"note": f"we sent {SHARED_SECRET} by mistake"})))
check("`token_type` is NOT eaten, which is why the redactor is one nobody switches off",
      red({"token_type": "Bearer"})["token_type"] == "Bearer")
check("nor is `listing_id`", red({"listing_id": 1234567})["listing_id"] == 1234567)
check("TOKEN_SHAPED is deliberately Etsy-shaped and does not claim to be general",
      etsy_oauth.fingerprint(REFRESH_TOKEN) == fingerprint(REFRESH_TOKEN)
      == sealed.fingerprint(REFRESH_TOKEN))
check("a PKCE verifier is NOT token-shaped, so only registration protects it",
      Redactor().string(VERIFIER) == VERIFIER)
check("which is why `finish` registers it explicitly before Etsy's words are read",
      "redactor.add(consumed.verifier)" in
      (ROOT / "src/brambleloop/integrations/etsy_authorise.py").read_text())


# =========================================================================================
# E. RETENTION, and PROCESS REPLACEMENT
# =========================================================================================
from brambleloop.ops import retention                                    # noqa: E402

check("the credential table is never pruned at any age",
      "oauth_credentials" in retention.NEVER_PRUNED_TABLES)
_retention_src = (ROOT / "src/brambleloop/ops/retention.py").read_text()
check("and retention never imports the credential model, so it cannot delete one by hand",
      "OAuthCredential" not in _retention_src)
check("the only thing it prunes on the OAuth side is `prune_handshakes`",
      _retention_src.count("prune_handshakes") >= 1
      and "OAuthHandshake" not in _retention_src)

_RET = Database(f"sqlite:///{_TMP.name}/retention.sqlite")
_RET.create_all()
# A long-lived open flow, so that "never deleted at any age" is asked at an age where the
# horizon would otherwise have reached it. A fifteen-minute handshake is expired long before
# the replay window closes, and an expired one is a different fact from a live one.
LONG = 60 * 60 * 24 * 90
live = oauth_store.begin(_RET, verifier=VERIFIER, redirect_uri=REDIRECT_URI,
                         ttl_seconds=LONG, env=_ENV)
spent = oauth_store.begin(_RET, verifier=VERIFIER, redirect_uri=REDIRECT_URI, env=_ENV)
oauth_store.consume(_RET, state=spent.state, env=_ENV)

far = oauth_store.utcnow() + timedelta(days=oauth_store.REPLAY_MEMORY_DAYS - 1)
kept = oauth_store.prune_handshakes(_RET, now=far)
check("a live handshake is never deleted, whatever the horizon says",
      kept["kept"]["live"] == 1 and kept["removed"] == 0, str(kept))
check("and a spent one is kept inside the replay window, so a replay is still a replay",
      kept["kept"]["inside_replay_window"] == 1, str(kept))
check("a replayed callback inside the window is answered as a replay, not as unknown",
      oauth_store.consume(_RET, state=spent.state, env=_ENV).verdict
      is oauth_store.Verdict.STATE_REPLAYED)

beyond = oauth_store.utcnow() + timedelta(days=oauth_store.REPLAY_MEMORY_DAYS + 1)
swept = oauth_store.prune_handshakes(_RET, now=beyond)
check("beyond the window the spent row goes and the live one still does not",
      swept["removed"] == 1 and swept["kept"]["live"] == 1, str(swept))
check("RESIDUAL, pinned rather than fixed: after the window a replay reads as unknown",
      oauth_store.consume(_RET, state=spent.state, env=_ENV).verdict
      is oauth_store.Verdict.STATE_UNKNOWN)

# Process replacement. The whole reason the verifier is sealed in the database rather than
# held in the process: the browser round trip crosses a container boundary routinely, and on
# this platform the container is replaced several times an hour.
_PR = f"sqlite:///{_TMP.name}/replaced.sqlite"
_before = Database(_PR)
_before.create_all()
opened = oauth_store.begin(_before, verifier=VERIFIER, redirect_uri=REDIRECT_URI, env=_ENV)
del _before                                              # the container that opened it, gone
_after = Database(_PR)
closed = oauth_store.consume(_after, state=opened.state, env=_ENV)
check("a handshake opened by one process is closed by a different one",
      closed.ok and closed.verifier == VERIFIER)
check("and it cannot be closed twice, whichever process presents it",
      oauth_store.consume(Database(_PR), state=opened.state, env=_ENV).verdict
      is oauth_store.Verdict.STATE_REPLAYED)

oauth_store.save_refresh_token(_after, REFRESH_TOKEN, new_grant=True, env=_ENV)
del _after
check("a credential sealed by one process opens in the next, from the same key",
      oauth_store.load_refresh_token(Database(_PR), env=_ENV) == REFRESH_TOKEN)
check("and does not open without the key, so the database half is not a credential",
      oauth_store.load_refresh_token(
          Database(_PR), env={"BRAMBLELOOP_SECRET_KEY": ""}) is None)
check("`openable` is what distinguishes stored from stored-and-we-still-hold-the-key",
      oauth_store.credential_health(Database(_PR), env=_ENV)["openable"] is True
      and oauth_store.credential_health(
          Database(_PR), env={"BRAMBLELOOP_SECRET_KEY": "x" * 40})["openable"] is False)


# =========================================================================================
# F. SPEND. CA$0 is a claim, so it is measured.
# =========================================================================================
with _DB.session() as s:
    cost_rows = list(s.scalars(select(CostEntry)))
with Database(f"sqlite:///{_TMP.name}/callback.sqlite").session() as s:
    cb_rows = list(s.scalars(select(CostEntry)))
check("nothing on the OAuth paths recorded a cost entry",
      cost_rows == [] and cb_rows == [], f"{len(cost_rows)} / {len(cb_rows)}")

_OAUTH_FILES = ("app/access_log.py", "core/sealed.py", "core/oauth_store.py",
                "integrations/etsy_oauth.py", "integrations/etsy_authorise.py",
                "integrations/http.py")
_sources = {f: (ROOT / "src/brambleloop" / f).read_text() for f in _OAUTH_FILES}
check("no OAuth module imports the model gateway or a provider",
      all("model_gateway" not in t and "gateway.anthropic" not in t
          for t in _sources.values()))
check("and none of them calls a provider method, which is what the spend scanner counts",
      all(not re.search(r"\.(see|complete)\(", t) for t in _sources.values()),
      [f for f, t in _sources.items() if re.search(r"\.(see|complete)\(", t)])
check("`finish` is named `finish` on purpose, so the scanner needs no exclusion here",
      "def finish(" in _sources["integrations/etsy_authorise.py"]
      and "def complete(" not in _sources["integrations/etsy_authorise.py"])

print(f"\n  {PASSED} passing, {FAILED_N} failing")
sys.exit(1 if FAILED_N else 0)
