# Independent review — Etsy connection release candidate e8ced0b

Reviewer: independent (did not write the code). Date 2026-10-11. Scope: `git diff 0417f35..e8ced0b`
(f48c8c4 + e8ced0b; 10 files, +833/−13). Read-only review; nothing written to Etsy, Railway or production.

## Verdict: RELEASE

No blocking or high/medium finding. Every changed source line concerns the Etsy connection
(probe refusal text, taxonomy stand-aside/recovery, owner connect/re-check buttons, SW version bump).

## Owner conditions

| Condition | Result |
|---|---|
| Etsy-connection scope only | Yes. 8 source files: CC api/etsy_connect/store.js/api.js/sw.js, etsy_taxonomy, etsy_public, release.py (two handlers). |
| No change to credentials, scopes, redirect URI, Etsy app | Yes. `SCOPES_WANTED`, `CALLBACK_PATH`, `OAuthApp`, redirect validation, sealing untouched. `connect` calls the existing `etsy_authorise.begin` with default scopes. |
| Production stays shadow; no publishing; no spend; no customer messaging; no phase change | Yes. Only new jobs are `etsy.probe` (read-only ping) and `listing.taxonomy_refresh` (GET-only, `/seller-taxonomy` prefix enforced by `ApiKeyTaxonomyClient._call`). |
| Command Center and Laura keep working | Store tab fetches `/api/cc/etsy` in a try/catch; failure hides the card only. CC auth/security suites pass. |
| Rollback | Additive: no migration, no schema change, no new env var. Reverting to 0417f35 is a plain redeploy. |

## Checks

- **Auth / default-deny**: the three routes sit under `/api/cc/*`, so `security.operator_gate` → `auth.gate` applies: owner session for all, same-origin + CSRF header + nonce + timestamp + 30/min per-session limit for the POSTs. None is in `PUBLIC_ROUTES`. Connect calls `auth.require_stepup` (403 `STEP_UP_REQUIRED`, audited as a security event). Tested unauthenticated → 401, no CSRF → 403.
- **Durable handshake before URL**: `oauth_store.begin` commits the row (state hash + sealed verifier) inside `db.session()` before `authorize_url` is built and returned.
- **No secret leakage**: response keys = authorize_url, state_expires_at, scopes, redirect_uri, state_fingerprint (`***` 8 chars), next, note. Audit row (`etsy.oauth_started`, same shape as the operator route) carries only the fingerprint, handshake id, scopes, expiry, source, actor. No `log.*` calls added. Response is `Cache-Control: no-store`.
- **Refusal while key refused**: server raises `ETSY_KEY_REFUSED` (409, audited via `auth.refuse`); UI disables the button (`can_connect`).
- **Open redirect**: URL built server-side from `AUTHORIZE_URL = https://www.etsy.com/oauth/connect`; the client additionally navigates only if `hostname === "www.etsy.com"` after `safeUrl` (store.js:58,91).
- **sw.js**: only `VERSION` bumped (v10→v11). `/api/` remains network-only; non-GET never intercepted.
- **Etsy error text**: `etsy_error_text` (etsy_public.py:117) takes only dict `error`/`error_description`, collapses whitespace, passes `Redactor((keystring, shared_secret))`, caps at 200 chars; probe view re-caps. Rendered via `h()` text nodes (dom.js has no HTML-string path) → not an injection vector.
- **Taxonomy job**: when the last probe is a 401/403, `refresh` returns UNMEASURED with `network_calls: 0` before constructing a client; a 401/403 during the read becomes `CredentialRefused` → UNMEASURED summary, not a dead letter; 5xx still raises for retries. No writes to Etsy.
- **Probe → taxonomy trigger**: only on `record["ok"]` and no snapshot, idempotency key `tax-after-probe-YYYYMMDD` (≤200 chars, `ctx.enqueue` treats duplicates as success). The refresh never enqueues a probe, so no loop.

## Findings (all Low / Info, none blocking)

1. **Low** — `app/command_center/etsy_connect.py:61,91`: `can_connect` and `connect` refuse on *any* failed probe (5xx, timeout), while the message says "Etsy is refusing this app's API key". Fails safe; wording can mislead after a transient outage. Suggest `etsy_public.auth_refused(probe)` for the wording, or a neutral message.
2. **Low** — `etsy_connect.py:106`: `etsy_authorise.begin` can still raise `NotConfigured`/`SealUnavailable` if configuration changes between the `configuration()` check and `begin` (narrow race) → unaudited 500 instead of a 409. No secret exposed.
3. **Info** — `integrations/etsy_taxonomy.py:171`: the gate now prefers the API-key client whenever a keystring exists (previously the shop/OAuth client after a successful probe). Uses existing env credentials, least-privileged, GET-only; not a credential change but a behaviour change worth knowing.
4. **Info** — `etsy_connect.py:70`: re-check allows one Etsy ping per minute even while the key is refused (owner-initiated, CA$0, far under Etsy's limits).
5. **Info** — the connect response necessarily contains the OAuth `state` inside `authorize_url` (same as the operator route); it is single-use, 15-minute, PKCE-bound and not cached.
6. **Info** — `Redactor` ignores secrets shorter than 8 chars; Etsy shared secrets are longer, so no practical gap.

## Tests run (one at a time, private TMPDIR deleted afterwards)

| Suite | Result |
|---|---|
| test_w4_etsycomm | 16 passed, 0 failed |
| test_v11_cc_auth | 16/16 |
| test_route_auth_default_deny | 7/7 |
| test_web_security | 11/11 |
| test_customer_data_auth | 9/9 |
| test_v11_pwa_static (named test_pwa_static in the brief; no such file) | 81 passed, 0 failed |
| test_oauth_security_audit | 87 passing, 0 failing |
| test_etsy_oauth_callback | exit 0, all OK |

Full suite not run (one already running).
