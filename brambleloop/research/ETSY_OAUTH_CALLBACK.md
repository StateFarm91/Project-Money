# The Etsy OAuth callback: the endpoint that holds the only key to the shop

**Written:** 2026-09-25 (UTC). **Phase:** SHADOW. **By:** the Authentication Infrastructure
lane, in an isolated worktree. **Nothing is pushed, merged or deployed by this lane.**

**The one sentence that matters: there was no way to finish an Etsy authorization, and now
there is one — but it has still never been run against Etsy, because this environment holds
no Etsy credentials and none were sought.** Everything below distinguishes what a primary
source says, what a local model of Etsy established, and what remains unverified.

---

## 1. The gap, verified before anything was written

Checked by reading `src/` on 2026-09-25, not taken from the brief:

| Claim | Verified |
|---|---|
| No callback route exists anywhere in `src/` | yes — no route matching `callback`, `oauth` or `redirect` was registered on the FastAPI app |
| `etsy_oauth.exchange()` has no caller | yes — the only occurrences of `exchange` in `src/` were its definition and its docstring. Nothing, anywhere, had ever called it |
| The PKCE verifier could not survive the round trip | yes — `etsy_oauth`'s own docstring said the verifier is "held in the calling process only", and `owner_action()` said so again in the text it printed to the owner |
| `OAuthApp.from_env` validated the redirect URI only as `startswith("https://")` | yes |
| `Credentials.from_env` built a `TokenProvider` with **no `on_refresh`** | yes — so every rotated refresh token was read, used for an hour, and dropped |

That last row is the one nobody had written down, and it is worse than a missing callback. It
means that even if a refresh token had been pasted into `ETSY_REFRESH_TOKEN`, the system would
have refreshed it, received the rotated replacement Etsy issues on every refresh, used it for
one hour, and lost it when the container was replaced — which this platform does several times
an hour. The next start would have presented a token Etsy had already spent and got
`invalid_grant`, which looks exactly like a revoked app. The owner action in
`ETSY_TRANSPORT.md` §5.1 — "put the resulting refresh token in the environment as
`ETSY_REFRESH_TOKEN`" — described a credential that would have died on day two.

---

## 2. Primary-source findings

All fetched from this environment on **2026-09-25**, each HTTP 200. Labels: **SOURCED** = Etsy
said it, quoted; **INFERRED** = reasoning from something Etsy said; **UNKNOWN** = not
established, and not guessed.

### 2.1 The token-endpoint host — **the §3.3 ambiguity is resolved**

`ETSY_TRANSPORT.md` §3.3 recorded that two Etsy documents give two different hosts and left it
open. Both were re-read today and both still say what they said:

- **SOURCED** — `https://developer.etsy.com/documentation/essentials/authentication/`:
  authorization code grants "generate[] an authorization code an app includes in a token
  request (`https://api.etsy.com/v3/public/oauth/token`)".
- **SOURCED** — Etsy's OpenAPI description (`https://www.etsy.com/openapi/generated/oas/3.0.0.json`,
  `info.version` = 3.0.0), `components.securitySchemes.oauth2.flows.authorizationCode.tokenUrl`:
  `"https://openapi.etsy.com/v3/public/oauth/token"`.

What was missing was a third Etsy page, which answers it directly:

- **SOURCED** — `https://developers.etsy.com/documentation/essentials/requests/`:
  *"Etsy API endpoints are accessible at URLs starting with `https://api.etsy.com/v3/` or
  `https://openapi.etsy.com/v3/` … **The two hostnames are equivalent and you can use
  either.**"* (Fetched with `curl`, HTTP 200; the sentence is present verbatim in the page
  source.)

So the two documents were never in conflict about *behaviour*, only about which of two
interchangeable names to print. **INFERRED**: that equivalence is stated of v3 *API* endpoints,
and `/v3/public/oauth/token` is a `/v3/` path, so it is covered — but Etsy does not say so of
the token endpoint by name, which is why the code keeps both.

**What was done about it.** `etsy_oauth.TOKEN_URL` stays the authentication page's host,
because that is the page about tokens. `TOKEN_URL_ALTERNATE` stays, the 404 retry stays, and a
new named constant `TOKEN_HOSTS_ARE_EQUIVALENT` carries the sentence and the date. The
ambiguity is now recorded as *resolved by a third Etsy page*, with the one reading that page
cannot rule out written next to it. A test pins both constants and the resolution string. The
new callback test asserts that the live route sent its grant to `TOKEN_URL` **and to no other
host** — that is a real assertion about the code path, not a comment.

**Still UNKNOWN:** whether either host accepts a grant. No token request has ever been made
from this system.

### 2.2 `state`: recommended, not required — and single-use by Etsy's own instruction

**SOURCED**, the authentication page's parameter table:

> `state` — **(Recommended)** A single-use token generated specifically for a given request.
> It is important that the state parameter is **impossible to guess, associated with a
> specific request, and used once**. When present, it must be non-empty; Etsy echoes it back
> in the redirect response… **OAuth 2.1 clients relying on PKCE for CSRF protection may omit
> `state`, but including it is still best practice.**

And, after a successful redirect:

> If you included `state` in your authorization request, validate that the state string in the
> response matches the value you sent. If they do not match, halt authentication as the request
> is vulnerable to CSRF attacks. If they match, **make a note never to use that state again**,
> and make your next authorization code request with a new state string.

So every property this implementation enforces — unguessable, bound to one request, used once —
is Etsy's own list rather than this company's invention. It is recorded in code as
`etsy_oauth.STATE_IS_REQUIRED_BY_ETSY = False`, so nobody later "fixes" the comment by claiming
Etsy requires it.

### 2.3 Redirect-URI matching — confirmed, character for character

**SOURCED**, the authentication page's "Redirect URIs" section:

> All `redirect_uri` parameter values must match a precise callback URL string registered with
> Etsy… **URL matching is case-sensitive and is specifically the URL established when you
> registered.** For example, if your registered redirect URL is
> `https://www.example.com/some/location`, the following strings **fail to match**:
> `http://…` (http, not https) · `https://…/some/location/` (additional trailing slash) ·
> `https://…/some/location?` (additional trailing question mark) · `Https://…` (uppercase H) ·
> `https://example.com/some/location` (no www subdomain).

The existing code's claim was right. `etsy_oauth.redirect_uri_problem()` now checks the class
of URI Etsy documents as always failing (non-https, whitespace, a fragment, a trailing `?`,
empty), and `REDIRECT_URI_MATCHING` carries the rule as text. It deliberately does **not**
reject a trailing slash: a trailing slash is a *different* URL, not an invalid one, and only
Etsy can say which one was registered. What is checked instead is that `ETSY_REDIRECT_URI` ends
with the path this service actually answers on — because the symptom of that typo is a 404 in a
browser twenty minutes later with no server-side trace at all.

### 2.4 The grants, the response, and the redirect

**SOURCED**, the authentication page:

- authorization-code grant body, `application/x-www-form-urlencoded`: `grant_type`
  (`authorization_code`), `client_id`, `redirect_uri` *("(Optional) The redirect_uri used in
  the prior authorization code request")*, `code`, `code_verifier`.
- refresh grant body: `grant_type` (`refresh_token`), `client_id`, `refresh_token`.
- response JSON: `access_token`, `token_type` ("always `Bearer`"), `expires_in` ("3600 seconds
  is 1 hour"), `refresh_token`, and the granted `scope`, which "may be a subset of the
  requested scopes".
- the access token "has a functional life of 1 hour"; the refresh token has "a longer
  functional lifetime (90 days)" and **a new refresh token is issued on every refresh**.
- success redirect carries `code` and `state`; an error redirect carries `error` (an RFC 6749
  code), `error_description` ("always in English"), optional `error_uri`, and `state` "only
  present if state was included in the original request".

**UNKNOWN**, and stated rather than inferred: Etsy's published documentation does **not** say
how long an authorization code remains valid, and does not state in so many words that it is
single-use. RFC 6749 §4.1.2 says an authorization code MUST be short-lived and single-use, and
the existing repository text says "the code is single-use and expires quickly" — that is
RFC 6749, not Etsy, and it is labelled as such here. The implementation does not depend on it:
the *state* is single-use on this side regardless.

### 2.5 What could not be established

- Whether Etsy accepts anything this code sends. No credentials, no registered app, no
  authorization code. Everything in §4 is "our side of the wire is right".
- `help.etsy.com` remains 403 to automated readers from here — unchanged from previous lanes.

---

## 3. What was built

| Thing | Where |
|---|---|
| `GET /api/etsy/oauth/callback` — the real HTTPS callback route | `app/main.py:api_etsy_oauth_callback` |
| `GET /api/etsy/oauth/start` — operator-authenticated initiation | `app/main.py:api_etsy_oauth_start` |
| `GET /api/etsy/oauth/status` — credential health, fingerprints only | `app/main.py:api_etsy_oauth_status` |
| The flow: `begin` / `finish`, calling the existing `etsy_oauth.exchange` | `integrations/etsy_authorise.py` |
| Server-side handshake and credential store, with every rejection named | `core/oauth_store.py` |
| Sealing: AES-256-GCM under an environment-held key, context-bound | `core/sealed.py` |
| `oauth_handshakes`, `oauth_credentials` | `core/models.py` |
| `on_refresh` wired to the store, compare-and-set rotation | `integrations/etsy.py:_persisting_on_refresh`, `Credentials.from_env(db=…)` |
| The publish job now hands the database to its credentials | `runtime/pipeline.py` |
| Access-log query-string redaction | `app/access_log.py` |
| Etsy's authorization-code grant, modelled with PKCE and a single-use code | `tests/fake_etsy.py` |
| 41 checks | `tests/test_etsy_oauth_callback.py` |

### 3.1 The route, and its exact path

**`GET /api/etsy/oauth/callback`** — one constant, `etsy_authorise.CALLBACK_PATH`, because the
path appears in the route, in the configuration check and in the owner action, and Etsy matches
it character for character. Three copies of that string would be three chances to be one
character out.

The registered redirect URI is therefore
`https://<the deployment's host>/api/etsy/oauth/callback` — no trailing slash, no query, no
fragment, lower-case scheme.

### 3.2 The persistence design, and why

Two things have to cross the browser round trip, and both are secrets.

**The state is not stored at all.** Only its SHA-256 is. The row is found by hashing what the
callback presented, so a database dump, a `pg_dump`, a console session or a leaked backup does
not contain a value anybody could replay into the callback. `state_fingerprint` (eight hex
characters) is what appears in logs, reports and audit rows.

**The verifier is sealed.** `core.sealed` encrypts it with AES-256-GCM under a key derived from
`BRAMBLELOOP_SECRET_KEY`, with a fresh nonce per seal and the *context string* authenticated
alongside — so a sealed verifier moved into the credential column fails to open rather than
opening as the wrong secret. There is **no plaintext fallback**: with no key, sealing refuses,
in the same direction `core.opsauth` chose for a missing operator token.

Postgres is the durable store, as instructed, and `core/models.py` is where the tables live.

### 3.3 The four state rejections, each distinguishable

`consume()` claims a handshake with **one conditional UPDATE** —
`consumed_at IS NULL AND expires_at > now` — so the database decides who wins. Two callbacks
delivered simultaneously with one valid state produce one `ok` and one `state_replayed`; there
is no window in which both read "unconsumed" and both proceed, which is the flaw in the obvious
read-then-write version. Only when that UPDATE changes nothing does it go looking for a reason,
and the reasons are ordered most-specific-first.

| What arrived | Verdict | HTTP | Page headline | Audit detail |
|---|---|---|---|---|
| no `state` parameter | `state_missing` | **400** | "No state on this callback" | `verdict`, no fingerprint |
| a state no handshake ever held | `state_unknown` | **403** | "Unrecognised state" | fingerprint of what was presented |
| a handshake past its deadline, unused | `state_expired` | **410** | "This authorization expired" | row id, fingerprint |
| a handshake already consumed | `state_replayed` | **409** | "This authorization was already used" | row id, **`replays` count** |
| valid state, verifier will not open | `verifier_unreadable` | **503** | "This deployment cannot finish the flow" | row id, fingerprint |

Five distinct HTTP statuses, five distinct outcome strings, five distinct headlines — and a
test asserts the statuses are all different, because an operator reading a proxy log with no
bodies still has to be able to tell them apart. 403 rather than 400 for an unknown state is
deliberate: a missing state is a malformed request, an unrecognised one is a credential this
service declines, and the difference distinguishes a mistyped URL from somebody probing.

Two further properties:

- **An expired handshake is marked consumed on the way out**, so waiting for a clock skew to go
  your way cannot revive it. A second presentation of an expired state reports `state_replayed`.
- **A valid state whose verifier will not open still spends the state.** Whatever went wrong
  afterwards, the state has been presented and must never be usable again.

### 3.4 The operator guard, at both ends

**Initiation** carries the operator credential exactly as `/api/continuity/export` and
`/api/queue/requeue` do: `opsauth.check(authorization)`, **401** on a wrong or absent
credential, **503 when `BRAMBLELOOP_OPS_TOKEN` is unset** — unconfigured means closed, which is
the direction that does not serve the company to the internet in the window between deploying
this and remembering to set a variable.

**Completion cannot carry it, and pretending otherwise would be theatre.** Etsy redirects the
*owner's browser*. A browser sent by Etsy carries no bearer header of ours, and the operator who
called `/start` with curl and the browser that lands on the callback are not the same client, so
a cookie set at initiation would not be there either. The callback is guarded by the thing it
*can* check:

1. **A state this service minted**, 32 bytes from `secrets`, written to the database before the
   authorize URL was ever returned, and claimable exactly once within fifteen minutes.
2. **The operator token must be configured at all.** The callback returns 503 with outcome
   `operator_credential_unconfigured` when it is not. Belt and braces — without one, nothing
   could have started a flow — but it keeps both ends pointing the same way.

That is what stops this being an open code-exchange endpoint. An unauthenticated caller who
posts a stolen authorization code cannot make this endpoint send **one byte** to Etsy, because
they cannot produce a state whose claim will win. A test proves exactly that: six malformed
callbacks, including one carrying a real-looking code, against a transport that raises on any
outbound request at all — zero calls.

### 3.5 Where the refresh token lives, and why that is the right place

The token **rotates on every refresh**, so it must be written somewhere the running service can
update. The candidates:

- **A repository file** — refused by CLAUDE.md, and rightly: a credential in git is a credential
  in every clone, CI log and repository backup forever.
- **A Railway environment variable** — where every other secret in this system lives, and the
  right place for a secret a *human* sets. Wrong for this one: the application cannot rewrite
  its own environment. `os.environ[...] = ...` changes one process's copy and is gone on the
  next container start.
- **A container file** — ephemeral on this platform, for exactly the reason `core.db` refuses to
  start on SQLite.
- **Postgres** — the only durable store the running service can write.

So Postgres, **and that alone is not good enough**, which is why `core/sealed.py` exists. The
database is read in three places a credential must never reach: `core.continuity.export` writes
every table into a portable file that `/api/continuity/export` serves as a download,
`core.backup` shells out to `pg_dump`, and anybody with the connection string can select from
it. A refresh token in a plain column is a refresh token in all three.

The design is a **split**:

> the **key** lives where this system already keeps secrets — an environment variable a human
> sets and the app never rewrites — and the **ciphertext** lives where this system can write.

Neither half is a credential by itself. A dump, an export, a console session or a stolen backup
yields ciphertext. `credential_health()` reports `openable`, which is the one field that
distinguishes "a credential is stored" from "a credential is stored and this deployment still
holds the key it was sealed under" — a stored credential sealed under a rotated key looks
present in every other report and is in fact gone.

**It is additionally excluded from the continuity export**, for a second reason that matters
independently: Etsy's refresh token is single-use per refresh, so two deployments restored from
one export would both try to refresh the same token, one would win, and the other would look
revoked — a restore drill would silently spend the production company's credential. A restored
Brambleloop authorises itself, deliberately, in a browser. That is the correct amount of
friction for the one thing that can write to the shop.

**Nowhere else.** The token does not appear in any response body (`/api/etsy/oauth/status`
returns fingerprints), any log line, any audit `detail`, any traceback (`OAuthCredential` and
`OAuthHandshake` both carry redacting `__repr__`s) or the callback page.

### 3.6 The rotation path

`TokenProvider.on_refresh` was read first, as instructed, and it is the hook that does the
work — but it had no caller wiring it to anything. Now:

1. `Credentials.from_env(env, transport=…, db=…)` loads the sealed token from
   `oauth_credentials` and **prefers it over `ETSY_REFRESH_TOKEN`**, because the environment
   variable is a snapshot of a chain that has since moved on.
2. It installs `_persisting_on_refresh(db, env, current_token=…)` as `on_refresh`.
3. On each refresh, the closure writes the rotated token back with
   `expected_fingerprint` = the token it believes it is replacing. `save_refresh_token`
   performs the write only if the row still holds that token.
4. **When the compare-and-set loses**, it does not raise. The loser is holding a brand-new
   access token that works for the next hour, and turning a successful refresh into a failed
   Etsy call would be a worse answer than a log line. It stops claiming to own the stored value
   instead, so its next write adopts whatever is there. The message names fingerprints, never
   tokens — asserted by a test.
5. `runtime/pipeline.py` passes `db=ctx.db`, so the unattended publish job is the path that
   benefits.

A fresh browser authorization is a different write: `new_grant=True`, which resets `rotations`
and `obtained_at` because it starts a new 90-day chain. That is a separate flag rather than
something inferred from the absence of a fingerprint, because "a new grant" and "a process
adopting a row it did not load" are both unconditional writes and mean different things about
the chain.

### 3.7 Never logging the code — including the leak nothing in the application could close

Inside the application: `http.Redactor` is reused, not reinvented. It is seeded per request
with the shared secret and, once the handshake is claimed, with **this request's authorization
code and PKCE verifier**, so an Etsy error body echoing either back — the case redaction by
field name misses, and one `tests/fake_etsy.py` already reproduces for bearer tokens — is
replaced by a fingerprint rather than rendered into a page.

Outside it, the leak that careful application code would not have closed:

    127.0.0.1:0 - "GET /api/etsy/oauth/callback?code=bftcubu-wownsvftz5kowdmxnqtsuoik…" 200

An access log logs the request line, and in an authorization-code flow the request line **is**
the credential. Nothing in this repository asked for that line; it is uvicorn's default, which
is exactly why it would have survived a review of `src/`. `app/access_log.py` installs a
`logging.Filter` on `uvicorn.access` (and the gunicorn/hypercorn equivalents) at import of
`app.main`, rewriting the value of every query parameter whose name is in
`integrations.http.SECRET_KEYS` — plus `state` — to `***<fingerprint>`. The path, method and
status are untouched, so the log answers every operational question it answered before. A test
proves both halves: the code and the state are gone, and `GET /api/status?limit=50` comes
through byte-identical, because a redactor that mangles ordinary log lines is one somebody
switches off.

The callback response itself carries `Cache-Control: no-store`, `Referrer-Policy: no-referrer`,
`X-Robots-Tag: noindex`, and a content policy of `default-src 'none'` so the page cannot load
or contact anything.

### 3.8 The success and failure pages

One page for every outcome: a status pill, a headline, an explanation, what to do next, and a
table of facts — every value `html.escape`d on the way in. Escaping matters more here than
anywhere else in the app: `error_description` is text that arrived on a URL from outside, and a
page that renders it raw is a reflected XSS hole on the one endpoint whose job is to be visited
by the owner's authenticated browser. A test injects `<script>alert('x')</script>` and asserts
it comes out escaped.

The page carries no credential. Its own footer says so, and a test sweeps the rendered HTML for
every secret in play — the shared secret, the authorization code, the state, the operator
token, the sealing key, and every access and refresh token the fake server ever issued.

---

## 4. Adversarial tests: what each one proves

`PYTHONPATH=src .venv/bin/python tests/test_etsy_oauth_callback.py` — **41 checks, all
passing.** Every one is its own named test.

**Sealing** (4) — a sealed value does not contain its plaintext and two seals of one secret
differ, so a database cannot be searched for "the row holding the same token"; sealing with no
key **refuses** rather than falling back to plaintext; a sealed verifier cannot be opened as a
sealed refresh token (context binding); a wrong key fails with a message that does not
distinguish wrong-key from wrong-context from corrupt — the three are one answer,
re-authorise, and telling them apart is an oracle.

**What is written down** (2) — the raw state appears nowhere in the row (only its SHA-256) and
the verifier appears nowhere in the clear, checked against every column *and* the row's `repr`;
500 fresh states are all distinct and at least 43 characters, and both modules import `secrets`
and **do not import `random`**.

**The four state rejections** (6) — missing, unknown, expired, replayed, each its own verdict;
an unknown state leaves the legitimate handshake untouched, so a stranger's guess cannot spend
the owner's flow; an expired state cannot be retried into existence; a replay is **counted**
and hands back no verifier; and a test asserts the five refusals have five different HTTP
statuses and five different headlines. A sixth: a handshake opened for one provider cannot be
closed by another's redirect.

**Missing/unreadable verifier** (1) — reports `verifier_unreadable`, hands back nothing, and
**still marks the state consumed**.

**Malformed callbacks** (3) — six shapes (nothing at all; a code and no state; a state and no
code; junk in both, including `../../etc/passwd` and `%00%00`; an unknown state with a
real-looking code; an `error=access_denied` redirect) against a transport that raises on any
call: **zero outbound requests**. `access_denied` is reported as `etsy_refused` with Etsy's own
error code, and spends the state — presented once is used once, even when what was presented
was a refusal. A reflected `<script>` is escaped.

**Exchange failure** (3) — Etsy returning **400** and **403** both produce `exchange_failed`
(502), the state is left spent so a dead code cannot be retried through it, and **no credential
is written**. A verifier that does not match the challenge is refused by the server, which is
the property that makes a stolen authorization code not a credential. A token echoed back
inside an error body does not reach the report.

**Duplicate callback** (1) — the same valid callback delivered twice through the real route:
200 then **409**, and `fake.exchanges == 1`. The second delivery did not reach Etsy.

**The operator guard** (4) — `/start` and `/status` return 401 with no credential and with a
wrong one; **both ends return 503 when `BRAMBLELOOP_OPS_TOKEN` is unset**; `/start` writes the
handshake before returning a URL, and the URL carries no shared secret and no verifier;
`/start` refuses (409) when there is nowhere to seal the verifier, *before* the owner is sent
to Etsy — because discovering that at the callback means an authorization code has already been
spent for nothing.

**No secret anywhere** (2) — a full successful authorization driven through the real FastAPI
route, then every secret in play swept from the page, the audit rows, the credential row and
`/api/etsy/oauth/status`. Plus: the access log cannot print an authorization code, the filter
is attached to the logger uvicorn writes through, and an ordinary log line is unchanged.

**The success path** (1) — the code is exchanged exactly once, the refresh token is stored
sealed and unseals to what the server issued, and **the grant was sent to `TOKEN_URL` and
nowhere else** — asserted at the transport, which is a stronger check than an environment
override would have allowed.

**Rotation** (4) — a rotation replaces the token and counts itself; a rotation that lost a race
is refused and the live credential survives, with fingerprints and not tokens in the message;
`Credentials.from_env(db=…)` reads the stored credential, refreshes, and **writes the rotated
token back** (the check that would have caught the original defect); a credential sealed under
a key the deployment no longer has reads as `stored: true, openable: false`.

**Interactions** (5) — retention removes a spent handshake past its window, never a live one
and never the credential; `unknown_read_actions()` is still empty and `etsy.oauth_callback` is
registered; a continuity export carries neither table and does not contain the token;
**`/api/verify` still reports 12 checks**; and the authorization flow references no
`EtsyClient`, no `activate(`, no create/update/delete operation, does not consult
`BRAMBLELOOP_PHASE`, and `activate()`'s three gates are all still present.

**Two injected defects** (2) — because a test that has never failed is a test nobody has reason
to believe:

1. A naive read-then-write `consume` is substituted, and the replay scenario is run against it:
   **both** deliveries return `ok`. The test asserts the defect reproduces, then asserts the
   real implementation refuses the second. Without this, "single-use" would rest on reading the
   code.
2. `sealed.seal` is replaced by the identity function, and the storage check goes red: the
   verifier is found in the row. The test asserts the leak reproduces, proving the
   "nothing in the clear" check has teeth.

### Other suites run

Individually, in this worktree (`run_tests.sh` was not run, by instruction):
`test_etsy_transport` 44 · `test_etsy` · `test_listing_schema` · `test_deploy` 32 ·
`test_gates` 33 · `test_cost_governance_wave2` 39 (retention) · `test_continuity` 15 ·
`test_model_spend_paths` · `test_persistence` · `test_platform` · `test_offsite` ·
`test_etsy_capability` · `test_acceptance_gates` · `test_capability_gates` · `test_shadow` ·
`test_commercial_truth` · `test_health` · `test_board` · `test_board_restart` · `test_chaos` ·
`test_intake` — all passing.

`test_deploy`'s `test_scheduler_tick_endpoint_is_idempotent_within_a_window`, which
`ETSY_TRANSPORT.md` recorded as failing in a full run and passing alone, **passed** here.
Nothing in this work touches the scheduler; it is noted because the previous lane asked for it
to be watched.

---

## 5. Interactions checked rather than assumed

**Retention** (`ops/retention.py`). Its rule is that a lifetime count over a pruned table is a
different claim from the one it says it is making, and that protected actions are never
deleted. Two decisions, both now in the code:

- **`oauth_credentials` is never pruned at any age** (`NEVER_PRUNED_TABLES`, reported in
  `state()["never_pruned"]` and `plan()["never_touched"]`). It is one row, it is the company's
  only write credential, and a horizon that reached it would log the company out of its own
  shop with the owner's browser as the only repair.
- **`oauth_handshakes` is pruned, under its own rule**, in `oauth_store.prune_handshakes`,
  wired into `retention.plan` (dry run) and `retention.apply`. A **live** handshake is never
  deleted at any age — deleting one strands the owner mid-authorization and turns a legitimate
  callback into `state_unknown` — and a spent one is kept for `REPLAY_MEMORY_DAYS = 30`, which
  is not housekeeping: prune it sooner and a replayed callback starts reporting as an unknown
  state, still refused but for a vaguer reason than the true one.
- `etsy.oauth_callback` is read by name in `src/` (by `/api/etsy/oauth/start`, so an operator
  can tell a flow that was never finished from one that failed), so it is registered in
  `KNOWN_READ_ACTIONS` as `latest`. `unknown_read_actions()` is still empty; a test asserts it.

**Phase.** `BRAMBLELOOP_PHASE=shadow` does **not** block authentication, and the flow module
does not read the variable at all. Authenticating creates nothing on Etsy: it exchanges a code
for a token and stores the token. Refusing it in SHADOW would mean the first authentication
this company ever performed happened on the day the shop opened, which is the risk the whole
Etsy department exists to remove. **No listing is activated, published, modified or deleted by
any of this work.** `activate()`'s three gates are byte-for-byte as they were, and a test
asserts both that the flow module references no listing operation and that the three gates are
still present in `integrations/etsy.py`.

**`/api/verify`.** Still 12 checks, unchanged in name and order. A test asserts the count.

**Continuity and backup.** Both new tables are in `continuity.EXCLUDED_TABLES`, for the two
reasons in §3.5. `core/backup.py`'s `pg_dump` path does include them — which is why the
sealing, not the exclusion, is the actual protection.

---

## 6. What I found and did not fix

1. **`core/backup.py` runs `pg_dump` over the whole database**, including `oauth_credentials`.
   The row is ciphertext, so this is safe by design rather than by accident, but the backup
   file's security is then the sealing key's security. Not changed: a selective `pg_dump` is
   another department's file and the sealed design already answers it.
2. **`http.TOKEN_SHAPED` only recognises an Etsy-shaped token** (`\d{5,}\.[A-Za-z0-9_-]{16,}`).
   A secret echoed back in a shape nobody predicted, and not seeded into the `Redactor` by
   value, would pass. The seeding covers what each request actually holds — shared secret,
   code, verifier — which is the important half. Recorded rather than widened, because a
   redactor that eats ordinary fields is one somebody switches off.
3. **A reverse proxy or platform router in front of this process keeps its own access log**, and
   nothing in this repository can reach it. The residual exposure is bounded and worth stating:
   an Etsy authorization code is single-use, short-lived, and **useless without the PKCE
   verifier**, which never leaves this service's database and is sealed inside it. A code lifted
   from a proxy log cannot be exchanged.
4. **`ETSY_REFRESH_TOKEN` is still read** and is still how a token can first arrive in a
   deployment that has never completed the callback. The database wins when both exist. Left
   in place deliberately — removing it would break the only path an operator has today — but it
   should be dropped from the owner instructions once the callback has been exercised once.
5. **`BUILD_STATE.md` and `DECISION_LOG.md` are untouched**, as previous lanes did, to avoid
   conflicting with concurrent lanes. The integrator owns that merge.
6. **`CREDENTIALS_SETUP.md` does not yet mention `BRAMBLELOOP_SECRET_KEY`.** Not edited for the
   same reason; §7 below is the text for it.
7. **Nothing here has been exercised against Etsy.** Every claim in §4 is about our side of the
   wire, against a local model of Etsy built from Etsy's document by the same hand that read it.
   One green run against that model is not evidence about Etsy, and no number of them adds up
   to one.

---

## 7. OWNER ACTION REQUIRED — one addition to §5.1 of ETSY_TRANSPORT.md

The existing item stands, with two changes: step 4 now describes something that exists, and
step 5 is gone.

### Authorise the Brambleloop Etsy app once, in a browser

- **Exact action, in order:**
  1. Sign in to the Etsy account that owns BrambleloopStudio.
  2. At `etsy.com/developers/your-apps`, register the app (or open the existing one) and set
     the callback URL to **exactly**
     `https://<the deployment's host>/api/etsy/oauth/callback` — no trailing slash, no trailing
     `?`, lower-case `https`, the same host the service actually answers on. Etsy matches it
     character for character.
  3. Put the keystring, shared secret and that same URL in the **deployment's environment** as
     `ETSY_KEYSTRING`, `ETSY_SHARED_SECRET`, `ETSY_REDIRECT_URI`. Never in the repository.
  4. **New:** set `BRAMBLELOOP_SECRET_KEY` to 32 or more random characters if it is not already
     set. It is the key the PKCE verifier and the refresh token are sealed under. Without it
     the flow refuses to start rather than storing a credential in the clear. **Changing it
     later invalidates the stored credential** and requires authorising again.
  5. Call `GET /api/etsy/oauth/start` with `Authorization: Bearer $BRAMBLELOOP_OPS_TOKEN`. It
     returns an authorize URL and, if anything is missing, says exactly what.
  6. Open that URL in a browser, approve the scopes
     (`listings_r listings_w listings_d shops_r shops_w`), and let the callback finish. The
     page will say whether it worked.
  7. **Nothing further.** There is no refresh token to copy anywhere. It is stored sealed and
     rotated in place from then on.
- **Why it is required:** Etsy's authorization-code grant requires a human to approve scopes in
  a browser. There is no client-credentials or key-only route to a write scope, so no amount of
  code removes this step, and no path around an auth wall was attempted.
- **Maximum cost:** CA$0. No fee is charged for an app, an authorization, a draft, an upload or
  a deletion. Etsy charges its listing fee on **publication**, which none of this performs.
- **Minutes:** 15.
- **Consequence of waiting:** unchanged — the shop cannot be built by software at all, and the
  first real Etsy request would be made on the day the shop opens.

---

## 8. Standing rules, confirmed

- **CA$0.** No model call, no image generation, no paid API. Three HTTPS GETs to Etsy's own
  public documentation pages and one to its OpenAPI document, all free and all reads. The
  unauthenticated `openapi-ping` was not re-run: no error string was needed.
- **No credential was rotated, changed or created**, and nothing was registered or modified at
  Etsy. This environment holds no Etsy OAuth credentials; none was sought, guessed or worked
  around.
- **No listing was activated, published, modified or deleted.** `activate()`'s three gates are
  exactly as they were.
- **No secret is stored in this repository.** The test suite's key and operator token are
  obvious test literals used only to exercise refusals against a loopback server.
- **`BRAMBLELOOP_PHASE=shadow`** throughout.
- **Committed on the worktree branch. Nothing pushed, nothing merged, nothing deployed.** The
  integrator performs the merge, the deploy and the production verification.

---

## 9. Proving the rotation fix — design, safety and what it establishes

**Written:** 2026-09-25 (UTC). **State:** IMPLEMENTED and LOCALLY_TESTED. `rotations: 0` in
production at the time of writing, so **nothing here has been observed against Etsy**.

### 9.1 The defect, restated exactly

`Credentials.from_env` built a `TokenProvider` with **no `on_refresh`**, against an Etsy that
issues a **new** refresh token on every refresh (SOURCED: Etsy's own example response, §2).
The old refresh token is spent. So the system worked for one hour, kept working as long as the
process lived, and then — at the next container replacement, which this platform performs
several times an hour — presented a token Etsy had already invalidated. `invalid_grant`. Which
looks exactly like a revoked app.

Two things must be shown, and they are different things:

1. **Etsy really rotates**, and the value it returns is written to the store.
2. **The stored value survives the process/container boundary** and is accepted by Etsy. This
   is the half the defect actually broke; (1) alone passed under the defect too, which is
   precisely why nobody noticed.

### 9.2 What forces a refresh

Not waiting an hour, and not touching anything at Etsy. `TokenProvider.token()` refreshes when
its `TokenSet` is expired, and `TokenSet.expired()` compares against `expires_at`. A credential
built from the sealed store with no live access token **already** carries `expires_at = 0.0` —
the value `Credentials.from_env` gives it, meaning "of unknown age, treat as dead". So every
production process already forces one refresh on its first Etsy call; `_force_expiry` sets the
same documented value explicitly so that the refresh happens *now*, under observation, instead
of at whatever moment the hour runs out.

The call that carries the refreshed token is a **shop read**. It creates nothing, changes
nothing, publishes nothing and costs nothing.

### 9.3 The two rounds

**Round A — Etsy rotates, and we seal what it gave us.** A credential built by
`Credentials.from_env(db=db)` spends the stored refresh token. Four things are then checked:

- `TokenProvider.history[-1]["refresh_token_rotated"]` — that the token Etsy returned *differs*
  from the one sent. This is the sourced claim under test, observed rather than assumed.
- `oauth_credentials.rotations` rose by exactly one.
- the stored fingerprint changed.
- **the fingerprint the database now holds equals the fingerprint of the token this process is
  holding live.** That last equality is the one that separates "we refreshed" from "we
  refreshed and stored what we got", and it is the check the defect fails.

**Round B — the sealed credential survives the boundary.** Every object from round A is
dropped. A *new* `Credentials.from_env(db=db)` is built; its refresh token can only have come
from `oauth_store.load_refresh_token` — a read of Postgres and an unseal under
`BRAMBLELOOP_SECRET_KEY`. It is asserted to be carrying round A's *stored* fingerprint and
nothing else, and then it spends it against Etsy. **Etsy accepting it is the proof.** Under the
defect, round B presents the token from before round A, which Etsy has already spent, and
answers `invalid_grant`.

The result is three distinct fingerprints, `rotations` up by two, and `openable: true`
throughout. No credential value appears anywhere; every identity in the report is an
eight-character SHA-256 fingerprint.

### 9.3b What the counter will read afterwards

`rotations` goes **0 to 3** on the first `mode=full` run, and the first of the three is the
one worth understanding. The exercise's own first authenticated call already forces a refresh:
a credential built from the sealed store carries no live access token, so
`Credentials.from_env` gives it `expires_at = 0.0` and `TokenProvider` refreshes before the
first request reaches Etsy. Rounds A and B then add two more. `mode=rotation` alone goes 0 to
2, for the same reason in reverse -- round A *is* that first forced refresh.

`rotations: 0` in production therefore never meant "the fix is untested". It meant **nothing
had ever made an authenticated Etsy call at all**, which is exactly what §5 of
`ETSY_TRANSPORT.md` said and is the thing this trigger changes.

### 9.4 Safety — what each refresh risks, and how it is bounded

A refresh **spends** a refresh token, so the failure worth designing against is a refresh that
succeeds while the seal write does not: the row would then hold a dead credential and the
company would be locked out until the owner re-authorises in a browser. Four bounds:

- **Round A is checked completely before round B is allowed to start**, including the stored
  fingerprint equalling the live one. A failure costs one rotation, stops, and emits an owner
  action naming the re-authorisation — rather than costing two and being reported once.
- **There are never more than two rounds.**
- **The proof runs after the shop has been confirmed clean**, so a credential failure can never
  strand a draft.
- **It is separately triggerable** — `POST /api/etsy/exercise?mode=rotation` — which is the
  safest form the evidence takes: two authenticated shop reads, no draft, no write, nothing to
  clean up. It is the one to run first.

The residual risk is the same one ordinary operation carries: any refresh at all can be the one
whose write fails. This makes that moment observed instead of unobserved.

### 9.5 What it does not establish, and the free way to close it

Round B's objects are new; **the interpreter is not**. A real container replacement adds one
thing this cannot: that no Python object survived at all.

That gap closes for **CA$0 and with no second container**, because this platform replaces the
container on every deploy and the first Etsy call from a new container presents the stored
token. So the confirmation is a *reading*, not a run: after the next restart,
`GET /api/etsy/oauth/status` showing `rotations` **above the number this run left** with
`openable: true` is the container-boundary proof. The report prints that number to compare
against. No run, no draft, no spend.

### 9.6 The injected defect

Two tests reinstate the bug rather than describing it. `_persisting_on_refresh` is replaced by
one that returns `None` — the exact shape of the old code — and then:

- the proof reports round A as **failed** with the store unmoved and the word "spent" in its
  danger note, and refuses to run round B;
- driven directly, a credential rebuilt from the untouched store is refused by the fake with
  `invalid_grant`, which is the failure that would have arrived on day two with nobody
  watching.

A test that has never failed is a test nobody has reason to believe.

### 9.7 Standing rules, confirmed for this work

- **CA$0.** No model call, no paid API, no listing fee. Every request is a read, a draft
  operation or a token refresh, and Etsy charges for none of them.
- **No listing was activated or published, and `activate()`'s three gates are byte-for-byte
  unchanged** — pinned by a SHA-256 of its source in `tests/test_etsy_exercise.py`.
- **No existing listing and no unrelated shop setting is touched.** The only listing this path
  can address is one it created, titled `DO NOT BUY - …`, in state DRAFT for its entire
  lifetime.
- **No secret is in this repository**, in any log, report, artifact or exception body. The test
  suite's key and operator token are obvious test literals used against a loopback server.
- **`BRAMBLELOOP_PHASE=shadow`** throughout.
- **Committed on the worktree branch. Nothing pushed, nothing merged, nothing deployed.**
