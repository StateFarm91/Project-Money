# Independent security review: W4-SECPATCH (`051dbee2..4ff953da`)

Reviewer: independent (did not write the patch). Review only: nothing was fixed, nothing was
deployed, and no production endpoint was called. All evidence comes from a local `TestClient`
or raw-ASGI calls against a temporary SQLite database seeded with sentinel owner data.
Date: 2026-10-26 (UTC).

## Verdict

| Question | Answer |
|---|---|
| **Ship 4ff953da as a production security patch?** | **YES.** It closes the reported exposure. I found no path by which an unauthenticated caller reaches owner-only data in the configuration as deployed (`railway.json`: plain `uvicorn`, no `--root-path`). |
| Why | Reads are now deny-by-default. The enumerated sweep covered 345 routes (339 API routes, 5 Starlette routes, 1 mount), each tried with GET/HEAD/OPTIONS/POST/PUT/PATCH/DELETE and no credential. It found **zero** sentinel leaks. It also covered path variants, error bodies, forged cookies and headers, websocket attempts and the `/cc/` bundles. The public readback projections hold only deploy-identity and liveness fields. Owner login, TOTP, the owner-session gate, CSRF and the operator token are unchanged. The deploy readback still reads every field it needs. |
| Blocking findings | None. |
| Follow-ups (non-blocking) | F1 should be fixed soon. The projection fails open if the app is ever served under a `root_path`. The rest are Low or Info. |

## Findings

| # | Severity | Title |
|---|---|---|
| F1 | Low (latent fail-open) | Projection is keyed on the raw `scope["path"]`, not the routed path |
| F2 | Low | Duplicate `Authorization` headers are read inconsistently (first vs last) |
| F3 | Low (pre-existing) | `/openapi.json`, `/docs`, `/redoc`, `/docs/oauth2-redirect` are public and sit outside the gate |
| F4 | Low (pre-existing) | `/api/cc/auth/status` tells an anonymous caller about the login's second-factor posture |
| F5 | Low (availability) | The owner-text scrub runs a full table scan and a regex compile on every anonymous response, 401s included |
| F6 | Info | The `/api/verify` projection is wider than the readback needs (13 checks, 5 used) |
| F7 | Info | Test changes: some assertions were loosened or moved to unit level (none weakened the security property) |
| F8 | Info (pre-existing, not a regression) | `GET /api/learn/lessons/{slug}` cannot be reached with any credential |
| F9 | Info | HEAD returns 405 on every API route, so the projection's HEAD branch never runs |

### F1: projection keyed on raw `scope["path"]` (Low, latent fail-open)

- **Location:** `app/security.py`, `PublicProjectionMiddleware.__call__`, at
  `spec = self.projections.get(scope.get("path") or "")`. `OwnerTextScrubMiddleware` has the
  same pattern, via `owner_session_route(scope.get("path"))`.
- **Scenario:** Starlette routes on `get_route_path(scope)`, which is `scope["path"]` with
  `scope["root_path"]` stripped. The projection looks up the unstripped path. If the app is ever
  served with a root path (`uvicorn --root-path`, or a path-prefix proxy or mount), `/x/api/status`
  routes to `api_status` but matches no projection, so an anonymous caller gets the full body.
  Reproduced with raw ASGI (`root_path="/x"`, `path="/x/api/status"`, no credential): HTTP 200
  with `agent_opex_cad`, `spend`, `revenue`, `revenue_cad`, `owner_actions_open`,
  `open_incidents`, `products`, `dead_letters`, `queue` and `certified_versions`. `/x/health`
  likewise returned the unprojected `boot_enqueues`. The gate itself fails closed:
  `/x/api/owner-actions` returned 401.
- **Exploitability today:** none. `railway.json` and the `Dockerfile` start uvicorn without
  `--root-path`, and uvicorn does not derive `root_path` from client headers. This is a
  configuration trap: the patch's main control fails open on an unrelated deploy change, and
  no test would catch it.
- **Fix:** key both middlewares on `starlette.routing.get_route_path(scope)`. Better still,
  apply the projection after routing, using `scope["route"].path`, as the gate already does.
  Add a test with a non-empty `root_path`.

### F2: duplicate `Authorization` headers parsed inconsistently (Low)

- **Location:** `operator_gate` and `root()` use `request.headers.get("authorization")`, which
  returns the **first** header. `PublicProjectionMiddleware` and the inherited
  `CustomerRefScrubMiddleware.__call__` loop over the headers and keep the **last** one.
- **Scenario:** `[Bearer <garbage>, Bearer <valid>]` on `/api/status` passes the gate (public
  route). The middlewares see the valid token and return the full, unprojected and unscrubbed
  body. The reverse order makes `/` render the full dashboard. Both cases need the real operator
  token, so an anonymous caller gains nothing. The finding is that two security layers disagree
  about who the caller is.
- **Fix:** one helper (`security.request_authorization(scope)`) used everywhere, and refuse
  any request with more than one `Authorization` header (400).

### F3: OpenAPI and Swagger UI are public, outside the gate (Low, pre-existing)

- **Location:** `app/main.py`, `FastAPI(...)` with the default `docs_url`, `redoc_url` and
  `openapi_url`. These are plain Starlette `Route`s, so the application-wide `operator_gate`
  dependency never runs on them. `iter_api_routes` and `PUBLIC_GET_NOTES` do not list them.
- **Scenario:** an anonymous `GET /openapi.json` returns 200, about 204 KB: 331 paths and 215
  operation descriptions taken from internal docstrings (for example "re-anchor a broken grant
  chain; voids every earlier grant"). This is a full map of the owner API, though it contains no
  owner data, and the sentinel sweep found none. It also contradicts the new docstring claim that
  "every GET/HEAD route not named here requires the operator credential".
- **Fix:** `FastAPI(..., docs_url=None, redoc_url=None, openapi_url=None)`. Alternatively, serve
  the schema behind the operator credential. Extend `test_every_get_is_gated_unless_on_the_public_allow_list`
  to walk the non-API `Route`s too.

### F4: `/api/cc/auth/status` discloses the login's security posture (Low, pre-existing)

- **Location:** `app/command_center/api.py`, `auth_status`. It is on
  `auth.PUBLIC_ROUTES` and outside this patch's diff.
- **Scenario:** an anonymous caller learns `login_configured`, `totp_required`, and the
  `second_factor.summary` text, for example "passphrase only: BRAMBLELOOP_OWNER_TOTP_SECRET is
  not set, so no second factor is required". That tells an attacker whether guessing the
  passphrase alone is enough. It is not owner business data, and the patch did not change it.
- **Fix:** answer anonymous callers with `authenticated` and the minimum the login form needs
  (whether to show a TOTP field). Move the `second_factor` summary to the authenticated branch.

### F5: owner-text scrub cost on every anonymous response (Low, availability)

- **Location:** `app/main.py`, `_owner_only_texts()` and
  `security.OwnerTextScrubMiddleware._scrubber()`.
- **Scenario:** on every response to a caller without the operator token, the middleware does
  the following. It loads **every** `OwnerAction` row, closed ones included, with no status
  filter, so the set grows forever. It also loads all open incidents and all access-capability
  texts, then compiles one alternation regex over up to four variants per text. This runs on 401
  refusal bodies and on `/cc/` HTML too. Measured locally with 3,000 owner actions: an anonymous
  401 on `/api/owner-actions` averaged **222 ms**, against 161 ms for the operator's full,
  unscrubbed render. Any anonymous client can use this as an amplification lever. The customer-ref
  scrub has the same per-request design, so the cost is now paid twice.
- **Fix:** skip the scrub for refusal bodies produced by `OperatorRefused` and `CCRefused`, and
  for static files. Restrict the texts to open actions. Cache the compiled pattern keyed on
  (row count, max updated_at), or with a TTL of a few seconds.

### F6: `/api/verify` projection wider than needed (Info)

- **Location:** `PUBLIC_PROJECTIONS["/api/verify"] = {"ok", "checks": [{"check", "ok"}]}`.
- **Observation:** an anonymous caller sees all 13 check names and their booleans, including
  `model_spend_within_its_ceiling`, `spend_limits_not_breached`, `no_revenue_claimed`,
  `worker_is_alive` and `scheduler_has_ticked`. `ops/readback.py` reads five of them
  (`phase_is_shadow`, `nothing_published`, `publication_was_actually_attempted_and_refused`,
  `no_unexpected_dead_letters_in_24h` and `every_agent_has_a_cost_ceiling`). No figures leak,
  only pass/fail signals about spend and revenue. Separately, and before this patch, each
  anonymous `GET /api/verify` runs the full verification and stamps its verdict to the database,
  which is a cost lever like F5.
- **Fix (optional):** project only the five checks the readback reads, and rate-limit or cache
  the anonymous verification.

### F7: test changes (Info). No security assertion was weakened.

Each of the 28 modified test files (plus the new `_opread.py` and `test_w4_secpatch_public_surface.py`) was read diff by diff. The pattern is consistent. An anonymous
read that certified a computed view now goes through `_opread.get`, using the operator token
(`_opread` sets the token in the env only for the duration of the call and restores it). Where
the old test made a security claim, an anonymous assertion was added next to it: 401, or the
projected key set. The new `test_w4_secpatch_public_surface.py` is non-vacuous: it first proves
the operator view contains every sentinel. Three places are weaker than they could be:

- `test_customer_data_auth.py::test_owner_card_routes_never_carry_the_recorded_buyer` now accepts
  `status_code in (200, 401)` for all five paths instead of pinning each one (`/` and
  `/api/build` 200, the rest 401). `test_the_named_leak_routes_are_closed` and
  `test_cert_dashboard` pin 401 on those paths, so the property is still held elsewhere.
- `test_a_card_that_does_quote_a_buyer_is_redacted_on_render`: the customer-ref scrub is no
  longer exercised end to end through a public route. It is now `scrub_body` called directly, plus
  a check that the middleware is installed. Every route that used to show it is now 401, so the
  end-to-end path no longer exists. Acceptable, but an ASGI-level test like the one added for
  `OwnerTextScrubMiddleware` would keep the middleware honest.
- `test_w4_integ4_secfixes.py` (b1 and i7) now applies `main._shorten_digests` itself to the
  operator body, so the route's anonymous shortening branch (`full=False` in the `/api/audit`
  handler) is dead and untested. That is harmless while `/api/audit` is 401.

### F8: Learn reviewer read path unreachable (Info, pre-existing)

`GET /api/learn/lessons/{slug}` needs the operator token at the gate. The handler then needs the
**distinct** reviewer token in the same `Authorization` header (`learn/api.py::_reviewer` refuses
a reviewer token equal to the operator token). Locally, the reviewer token got 401 from the gate
and the operator token got 401 "Learn reviewer credential refused". The route was already in
`OPERATOR_GET_ROUTES` at `051dbee2`, so this patch did not cause it. Fix it separately: add the
route to an explicit reviewer-credential allow-list, just as `POST .../review` is in
`PUBLIC_MUTATING_ROUTES`.

### F9: HEAD is 405 on API routes (Info)

FastAPI `APIRoute`s registered with `GET` do not answer HEAD (334 of 339 returned 405). The
`HEAD` branches in `requires_operator` and `PublicProjectionMiddleware` therefore never run.
There is no security impact, and Railway's health check uses GET.

## Answers to the six questions

### 1. Does anything owner-only still reach an unauthenticated caller?

**No**, in the deployed configuration. F1 is a latent exception under a non-empty `root_path`.

Method: a fresh DB was seeded with sentinels: an owner action (action, reason, consequence,
blocks, a CA$55.55 cost), a P1 incident (summary, signature, detail), an unpublished product and
listing, a job with an error, and a CA$83.4567 spend row. Non-vacuity was checked first: the
sentinels appear in `/api/owner-actions` and `/api/incidents` with the operator token. The
operator token was configured but not presented. Each check searched the body **and the response
headers** for every sentinel.

- **Every route.** All 345 routes were enumerated recursively, including the `_IncludedRouter`
  candidates (owner phase, publication, activation, ledger mapping, Learn, storefront, estate,
  and every Command Center `/api/cc/*` router). Each was tried with GET, HEAD, OPTIONS, POST, PUT,
  PATCH and DELETE, with path parameters filled. Result: 0 leaks, and 0 anonymous 2xx on any
  mutating method. Anonymous 2xx/3xx came only from `/`, `/health`, `/api/status`, `/api/build`,
  `/api/catalogue`, `/api/cc/auth/status`, `/ops/teardown`, `/ops/teardown.js`, `/ops/insights`
  (a redirect), `/cc` (a redirect), the `/cc/` static mount, and the F3 docs routes.
  `/api/verify` and `/api/verify/smoke` answered 503 with the projected body.
- **Variants.** Tried trailing slash, upper case, `//x`, `?x=1`, `%2F`, `/.`, `;x`,
  `/api/cc/../api/owner-actions`, `/api/cc/%2e%2e/owner-actions`, `/cc/../api/owner-actions`,
  `/CC/`, `/cc/%2e%2e/%2e%2e/etc/passwd`, and `/api/cc` without the slash. Each was tried with
  and without following redirects. Trailing slashes give a 307 to the canonical path, which is
  then gated or projected. Case variants give 404. No leaks.
- **Error pages.** The 404, 400, 422 and Etsy-callback 400/403 bodies are generic. The 503 bodies
  on projected routes are projected. The middleware also replaces a body that is not JSON. No
  sentinel appeared.
- **Static and bundles.** `/cc/index.html` and all files under `command_center/static`,
  `/ops/teardown(.js)` and `/openapi.json` contain no sentinel and no embedded state. The PWA
  fetches only `/api/cc/*` and `/api/store/live_observation`.
- **Websocket/SSE.** The app registers no `WebSocketRoute`, and websocket connects to `/`,
  `/api/cc/events`, `/api/events` and `/ws` were refused. There is no SSE or streaming endpoint
  on a public path.
- **`/`** for an anonymous caller, or one with a wrong, Basic, or truncated token: the 299-byte
  static page with no numbers and no script.

### 2. Is the allow-list correct and minimal?

The allow-list is correct. Each entry in `PUBLIC_GET_NOTES` was checked against its handler:
- `/learn/{slug}` and the diagram route serve APPROVED lessons only.
- `/api/model-tournament/image/{sha256}` serves only digests from the canonical reference pack,
  and only images.
- `/brand/fonts/{name}` uses a file-name allow-list.
- The Etsy callback carries no data without a valid state.
- `/api/learn/metrics` is guarded by its own editor check, which is the operator token (anonymous
  gets 401).
- `/ops/*` serves static pages.

Observed anonymous projections:
- `/health`: `{status, version, db, build{commit, commit_short, known}, runner{worker_alive}}`
  (`db` is `ok` or `unreachable`; the driver text is not included).
- `/api/status`: `{version, build{…}, boot_guard{enforced, ok}}`.
- `/api/build`: `{final_master{launch_ready}}`.
- `/api/catalogue`: `{published}`.
- `/api/verify/smoke`: `{verdict, as_of}`.
- `/api/verify`: `{ok, checks[{check, ok}]}`.

None carries owner data. The only one that is not minimal is `/api/verify` (F6). The list does
not cover the non-API docs routes (F3).

### 3. Can the scrub exemption for `/api/cc/*` or the owner-session pages be abused?

No. The exemption only removes the *second* layer. Every exempt path still passes through
`operator_gate`, which sends `owner_session_route` paths to `auth.gate`. That requires a valid
owner session cookie, except on `GET /api/cc/auth/status` and `POST /api/cc/auth/login`, which
return no owner text. A forged session cookie, a forged `X-Forwarded-For`, `X-Real-IP` or `Host`
header, or a Basic or truncated bearer token gave 401 on `/api/cc/approvals` and
`/cc/store-preview`, and the projected or static body on public routes. A path that starts
`/api/cc/` cannot route to a non-CC handler: Starlette matches on the same path, `..` segments
do not match, and 404 bodies are generic. The F1 path-keying caveat makes the exemption fail
*closed* (a prefixed path is not exempt, so it gets scrubbed).

### 4. Did anything change in owner login, TOTP, the owner-session gate, CSRF or the operator token?

**No.** `git diff --stat 051dbee2..4ff953da` touches only `app/main.py` and `app/security.py` in
`src/`. There is no change under `app/command_center/` (`auth.py` and `api.py` included) or to
`core/opsauth.py`. `PUBLIC_MUTATING_ROUTES`, `OPERATOR_GET_ROUTES`, `_FORBIDDEN_PREFIXES`,
`refusal_status`, `operator_gate`, `owner_session_route`, `OWNER_SESSION_PAGES` and
`presents_operator_credential` are unchanged. In `operator_gate`, the owner-session branch still
runs before `requires_operator`, so the new read default cannot intercept CC routes. The only
semantic change to the gate is the safe-method branch of `requires_operator`, which is now
deny-by-default. F2 is a pre-existing header-parsing inconsistency that this patch carried into
a new middleware.

### 5. Does the deploy readback still work, and does anything the system needs now get a 401?

- **Deploy readback works.** `test_deploy_readback_still_reads_every_field` passes: it runs the
  real `ops/readback.py`, `ops/deployed_sha.py` and `ops/verify_deploy.py` anonymously against
  the app. I confirmed independently that every field in `readback.MANIFEST` is in the anonymous
  projection, and that `/api/launch/packet` still answers 401, which the readback expects. Railway
  `healthcheckPath: /health` with GET returns 200 and the projected body.
- **Internal calls:** none. Nothing in `src/` makes HTTP calls to its own routes, and the worker
  calls functions directly.
- **PWA:** fetches only `/api/cc/*` and `/api/store/live_observation`, both owner-session gated
  and unaffected. The `/cc/` static mount and the `/cc` redirect are outside the dependency gate,
  as before.
- **Etsy OAuth callback:** still public. Without a valid state it returns 400/403 HTML with no
  data. `/api/etsy/oauth/start` was already operator-gated. The Etsy webhook POST is unchanged.
- **Learn pages:** `/learn/{slug}` and the diagrams stay public. The editor endpoints work with
  the operator token. The reviewer GET is unreachable, but that predates this patch (F8).
- No other `ops/` script or workflow reads production GETs anonymously.

### 6. Was any test weakened?

No security assertion was removed or inverted (see F7). The changes swap anonymous reads for
operator reads and add anonymous-refusal or projection assertions next to them. Three assertions
are looser than ideal or moved to unit level. Each is covered elsewhere or concerns a path that
no longer exists.

## Test runs (local, `nice -n 19`)

Environment: Python 3.13, a venv from `brambleloop/requirements.lock` (fastapi 0.141.1,
starlette 1.6.0, SQLAlchemy 2.0.54). **`requirements-test.lock` does not exist in the
repository**, so `httpx` and `pytest` were installed unpinned for `TestClient`.

<!-- results -->
- `test_w4_secpatch_public_surface.py`: **10/10 passed** (82 s).
- Modified suites that have finished (exit code, last summary line):
  - `test_cert_culture_teardown`: EXIT 0 (0 failed)
  - `test_cert_dashboard`: still running at commit time
  - `test_cert_growth_ops`: EXIT 0 (PASS: 0 failing)
  - `test_cert_growth_seasonal`: EXIT 0 (0 failure(s))
  - `test_cert_wiring`: still running at commit time
  - `test_closure`: still running at commit time
  - `test_customer_data_auth`: EXIT 0 (9/9 passed in 24s)
  - `test_dashboard_spend`: EXIT 0 (8 passing, 0 failing)
  - `test_deploy`: still running at commit time
  - `test_health`: still running at commit time
  - `test_incident_lifecycle`: EXIT 0 (OK   test_the_snapshot_groups_by_kind_and_keeps_a_day_of_resolutions)
  - `test_policy_intake`: EXIT 0 (9 passing, 0 failing)
  - `test_provenance_backfill`: EXIT 0 (OK   test_without_an_audit_row_the_job_is_unknown_and_the_artefact_stays_unprove)
  - `test_ranking_readiness`: EXIT 0 (OK   test_the_catalogue_shows_the_certificate_verdict_not_the_proxy)
  - `test_route_auth_default_deny`: EXIT 0 (8/8 passed in 23s)
  - `test_search_visibility`: EXIT 0 (OK   test_the_watch_is_inert_in_shadow_and_daily_for_seven_days_after)
  - `test_swarm_runtime`: EXIT 0 (OK   test_the_runtime_routes_report_what_the_handlers_decided)
  - `test_w3_laura_cc_providers`: EXIT 0 (7/7 passed in 26s)
  - `test_w4_board_close`: EXIT 0 (6/6 passed in 35s)
  - `test_w4_cc_company`: still running at commit time
  - `test_w4_close5_r1`: EXIT 0 (PASS: 0 failing)
  - `test_w4_close5_rows4`: EXIT 0 (PASS: 0 failing of 2)
  - `test_w4_fmclose_etsy`: EXIT 0 (PASS: 0 failing)
  - `test_w4_fmgate_catalogue_filters`: EXIT 0 (OK   test_entered_and_lost_filters_per_listing_and_unmeasured_without_a_schema)
  - `test_w4_integ4_secfixes`: EXIT 0 (12/12 passed)
  - `test_w4_rel2`: EXIT 0 (PASS: 0 failing)
  - `test_w4_secfix_insights_private`: EXIT 0 (4/4 passed)
  - `test_web_security`: still running at commit time
<!-- /results -->

Independent probes, written for this review and run from the scratchpad, not committed:
- the full-route × method sweep with path variants, error pages, header and cookie tricks and
  websockets: **0 findings**;
- the raw-ASGI `root_path` reproduction for F1;
- the OpenAPI inventory and the scrub-cost timing for F3 and F5.
