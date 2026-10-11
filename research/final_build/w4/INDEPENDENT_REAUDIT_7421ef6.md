# Independent release re-audit: candidate 7421ef6 (fast-forward from production fcb982d)

- Date: 2026-10-11 (UTC). Reviewer: independent release review (Final Master F-839/F-846).
- Scope: `fcb982d..7421ef6` (968 commits, 2350 files, 636 files under `brambleloop/src`),
  checked adversarially for **release-blocking defects in six protections only**.
  Production remains in SHADOW after the fast-forward.
- Mode: read-only on the candidate. No code was changed. Line numbers below are at 7421ef6
  under `brambleloop/src/brambleloop/` unless stated.
- Tests run, one process at a time, private TMPDIR (since deleted):
  `tests/test_secret_scan.py` (7/7 OK), `tests/test_route_auth_default_deny.py` (7/7),
  `tests/test_v11_cc_auth.py` (16/16), plus three ad-hoc repro scripts described below.

## Verdict

**No release-blocking defect found. Verdict: PASS for the fast-forward, with one MEDIUM defect
(pre-existing in production, unchanged by this candidate) and four LOW or configuration items
to track.**

| # | Area | Verdict |
|---|------|---------|
| 1 | Shadow mode: no publish, customer message or spend | PASS |
| 2 | Command Center auth | PASS (2 LOW, plus 1 config check) |
| 3 | Spend ceilings enforced in code | PASS for this release; **MEDIUM defect D-1** (pre-existing) |
| 4 | Database migration and boot | PASS (1 LOW, pre-existing) |
| 5 | Laura identity, brand assets, owner Etsy fields | PASS |
| 6 | Secrets | PASS |

---

## 1. Shadow mode: PASS

- **store.publish.** `runtime/pipeline.py:1450-1497`. The phase is re-resolved per job
  (`protected_phase(ctx)`: the environment and the sealed, chained owner transition, the more
  restrictive one wins, `core/phase.py:191-202`, failing closed to `shadow`). In SHADOW the job
  raises `ShadowModeRefusal` before any client is built. In STAGING, `EtsyClient.refusal()`
  refuses (`integrations/etsy.py:791-807`; `PHASES_THAT_MAY_PUBLISH = ("limited_production",
  "production")`, line 86).
- **Etsy write client.** Every write (`create_draft`, `upload_image`, `attach_file`,
  `update_listing`, `delete_listing`, `set_listing_property`) goes through `_authorise_write`
  (`etsy.py:878-917`). That needs a verified sealed `OwnerGrant`, re-checked against the live
  phase. The only exception is the draft-only `shadow_writes_authorised` lane, which works
  only while the re-resolved phase does not publish. `activate()` (`etsy.py:1349-1404`) needs the
  phase, owner authority, a per-call Launch-0 string and a validated `OwnerGrant`, and it
  re-checks the grant immediately before `PATCH state=active`. `update_listing` refuses `state`
  and `price`. The `store.activate` handler re-checks the phase three times
  (`pipeline.py:2163, 2183, 2194`).
- **Draft lane** (`shadow_writes_authorised=True`). It is constructed only in
  `integrations/etsy_probe.py:1450` (a CLI that needs `ETSY_SHADOW_WRITE=1`) and
  `integrations/etsy_exercise.py:350`. The exercise is reached only through the operator-token
  route `app/main.py:5046` and refuses to run if the client could activate. It creates drafts
  only, which are invisible and incur no fee. This design predates the candidate (2 changed
  lines in `etsy_exercise.py`).
- **Owner shop fields.** No `updateShop` or banner-upload method exists in the client. See
  area 5.
- **Customer messaging and CASL.** No outbound sender exists in `src/`: no smtplib, SendGrid,
  Postmark or Mailgun, and no Etsy conversation call. Every `urlopen` site is a model or image
  provider, a read-only fetch, or the off-site backup. CC notifications are in-app only
  (`app/command_center/notifications.py:17-19`), and support replies stay drafts
  (`support/workspace.py:17`).
- **Ads and paid media.** `growth/ads_readiness.py` produces proposals only: no socket, no
  `ads.campaign` enqueue, no spend row. `ads.campaign` (`runtime/growth_ops.py:500-559`)
  refuses unless `ad_authority` is granted. Then `paid_media.authorise_spend`
  (`commerce/paid_media.py:198`) refuses below PRODUCTION, and even in production it raises
  `CapabilityNotEnabled` because no ad integration exists. Finance `check_spend` blocks every
  external kind in shadow (`finance/accounting/policy.py:126-131`).
- **Model and image spend in shadow** is allowed by design and is governed by area 3.

## 2. Command Center auth: PASS (2 LOW, 1 config check)

- **Default deny.** `FastAPI(dependencies=[Depends(security.operator_gate)])` (`app/main.py:56`)
  applies to routers and to `add_api_route` routes. `operator_gate` sends every `/api/cc/*`
  route, `/cc/store-preview` and `/api/store/live_observation` to `auth.gate`
  (`app/security.py:248-262`). With no gate registered the answer is 503. Only `GET
  /api/cc/auth/status` and `POST /api/cc/auth/login` are public (`auth.py:91-95`). The CC is
  closed (503) when the operator token is unset (`auth.py:620-622`). No CORS middleware exists
  anywhere. `/cc/` static holds no data. `tests/test_route_auth_default_deny.py` and
  `test_v11_cc_auth.py` pass.
- **Identity.** PBKDF2-SHA256 hash from the environment, with 600k iterations minted and
  ≥100k accepted (`auth.py:135-172`). An unset or malformed hash closes login (503). Comparison
  uses `hmac.compare_digest`. TOTP is RFC 6238, ±1 step.
- **Session.** 256-bit token. Only its SHA-256 is stored. The cookie is `__Host-bl_cc` with
  `Secure; HttpOnly; SameSite=Strict; Path=/` (`api.py:96-97`), the same for `__Host-bl_dev`.
  Lifetime is 12 h absolute and 2 h idle, and sessions can be revoked.
- **CSRF and origin.** On every non-GET: `Sec-Fetch-Site` and `Origin` must match the
  configured or Host-derived https origin, an `X-CSRF-Token` (HMAC of the session token) is
  required, and so is a nonce plus a timestamp within ±120 s. Nonces are unique per row and
  kept longer than twice the skew (`auth.py:542-659`).
- **Trusted proxy.** `client_ip` (`auth.py:224-248`) ignores `X-Forwarded-For` unless
  `BRAMBLELOOP_TRUSTED_PROXY_HOPS=N` is set, and then takes the N-th entry from the right.
  Rotating a spoofed XFF cannot mint new buckets.
- **Rate limits and lockout.** Only `BAD_CREDENTIALS` failures count: 5 per client and 20
  globally in 15 min. A trusted device is limited per device. A single-use recovery code needs
  the operator token. There is a limit of 30 mutations a minute per session. Five failed
  step-ups revoke the session.
- **No secrets in responses.** `test_refusals_never_echo_secrets` passes. `auth/status` and
  `account` return only booleans and derived values (the CSRF token, public session ids).
  Security events store a hashed client key.

**L-1 (LOW, not blocking): TOTP is optional in code.** `verify_totp` returns True when
`BRAMBLELOOP_OWNER_TOTP_SECRET` is unset (`auth.py:184-187`). Owner login is then
passphrase-only, and neither the deploy guard nor readiness requires TOTP. This is documented
("optionally plus TOTP", `auth.py:8`). Accepted codes are also not marked as used, so a captured
passphrase and code pair can be replayed within about 90 s.
*Action: confirm the production variable is set. Consider requiring it outside local
development.*

**L-2 (LOW, not blocking): the login throttle is check-then-act without a lock.**
`api.py:73-88` runs `login_throttle` (a count of past failures) and `verify_owner` (PBKDF2,
600k iterations) as separate threadpool calls. A failure is recorded only after verification
completes. A burst of N concurrent login requests from one client can all pass the throttle
before the first failure is written, so up to about N guesses per window instead of 5 (and
instead of 20 globally). The 600k-iteration PBKDF2 cost and the ≥12-character passphrase bound
the impact.

**Config check (not a code defect).** If `BRAMBLELOOP_TRUSTED_PROXY_HOPS` (or
`BRAMBLELOOP_CLIENT_IP_HEADER`) is unset in production, every client is the edge proxy's
address. The per-client limit then acts as a global one: five wrong guesses from anyone lock
out new devices for 15 min. The trusted-device cookie and the recovery code mitigate this. The
code comment says production sets HOPS=1. This was not verified here, because I did not read
production variables, to avoid exposing secret values.

## 3. Spend ceilings: PASS for this release; MEDIUM defect D-1 (pre-existing)

- **Monthly model ceiling.** `gateway/anthropic.py:check_budget_cad`. It counts the billed
  month, the holder's own open reservations and other holders' live reservations under
  `budget_lock` (a Postgres advisory transaction lock or SQLite `BEGIN IMMEDIATE`, and refused
  on any other dialect). A NaN or negative estimate is refused (`:465-477`), and so is an
  unpriced model (`estimate_cad`, `:192-198`). A call that names no purpose or evidence is
  refused. Every refusal is audited.
- **Image keys.** `gateway/images.py:891` calls `reserve_render`, which goes through
  `check_budget_cad` at `provider.cad_per_image` before the request. An unknown provider is
  refused as unpriced (`:842-845`). A missing key raises `ImagesNotConfigured`.
- **CA$ caps.** `finance/accounting/policy.py`: a non-finite amount is blocked, unknown cash
  blocks, an owner action with an UNKNOWN `max_cost_known` authorises nothing, CA$0 means CA$0,
  and campaign and monthly ad caps apply. `paid_media.authorise_spend` checks daily, campaign
  and monthly caps after the phase. The research judge `visual/d_judge.py` refuses without a
  finite, positive `BRAMBLELOOP_RESEARCH_JUDGE_CAP_USD`, and nothing in `src/` imports it.

**D-1 (MEDIUM, pre-existing at fcb982d and unchanged by this candidate, so not a release
blocker for the fast-forward): `BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD=nan` disables the
monthly ceiling.** `monthly_ceiling_cad()` (`gateway/anthropic.py:157-164`) parses the
environment with `float(raw)` and returns `min(value, authorised)`. `float("nan")` parses, and
`min(nan, 100.0)` returns `nan`. The check `committed + estimate > ceiling` (`:488`) is then
always False. The environment is documented as "may lower it; nothing may raise it", but a NaN
removes the ceiling altogether.

Repro (against a scratch SQLite database at 7421ef6):

```
BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD=nan
spend_report.record(amount_cad=500.0)          # month already 5x the CA$100 ceiling
check_budget_cad(estimate_cad=50.0, purpose=..)
-> ceiling nan, spent 500.0, ALLOWED reservation 1
control (=100): REFUSED BudgetExceeded
```

It requires an operator to set the variable to `nan`. Fix: return `authorised` unless
`math.isfinite(value)`, and refuse when `ceiling` is not finite inside
`_decide_and_reserve`.

LOW notes (not blocking):
- The `ads.campaign` handler's `float(daily_budget_cad)` is not finiteness-checked
  (`runtime/growth_ops.py:521-525`). A NaN passes the headroom test, but phase,
  `authorise_spend` and the missing integration all still refuse.
- The image probe's injected-generator branch ledgers `got.get("cad") or 0.0`
  (`gateway/images.py:1209-1214`). It is reached only with a test-injected generator.

## 4. Database migration and boot: PASS (1 LOW, pre-existing)

- **Additive only.** `core/migrate.py` is unchanged in the diff. It runs `ALTER TABLE ADD
  COLUMN` only, plus literal-default backfill and `CREATE INDEX IF NOT EXISTS`. It refuses a
  NOT NULL column with no default (`UnsafeMigration`). There is no other DDL in `src/`: no raw
  CREATE, ALTER or DROP. `drop_all` is never called at runtime.
- **Rehearsal, run by this review.** I built the production schema with `git archive fcb982d`
  code (51 tables) and seeded one row into every table (51/51). Then the 7421ef6
  `Database.create_all()` made **26 changes**, and `migrate.plan()` afterwards was `[]`. A
  second run made `[]` changes. 126 tables matched a fresh 7421ef6 database: no missing table,
  column, index or unique constraint. **Row-count mismatches: 0 of 51.** (Three ORM read
  errors came from my synthetic enum seed values, not from the migration.) All 126 tables and
  their indexes compile for the PostgreSQL dialect.
  *Limit:* this rehearsal ran on SQLite. A local Postgres cluster could not be started under
  the private scratchpad because the `postgres` user cannot traverse the 0700 parent. The
  earlier Postgres rehearsal (`brambleloop/research/final_build/POSTGRES_MIGRATION_EVIDENCE.md`)
  used 448e87c, and a snapshot rehearsal against the real Railway database is still the
  documented deploy gate.
- **DATABASE_URL missing.** `core/db.py:resolve_url` and `sqlite_refusal_reason` refuse SQLite
  when any `RAILWAY_*` marker is present, when the phase is not shadow, or with
  `REQUIRE_POSTGRES=1`. Verified: `RAILWAY_ENVIRONMENT=production` with no URL, and with
  `DATABASE_URL=sqlite:///x.db`, both raise `EphemeralStorageRefused`. `app/main.py:52`
  constructs `Database()` at import, so the process does not start, which is fail-closed.
- **Migration failure.** `_startup` calls `db.create_all()` unguarded (`main.py:181`), so an
  exception aborts start-up, and the worker and scheduler entries do the same. Each ALTER is
  its own transaction, so a partial run leaves only added nullable or defaulted columns, and
  the next boot completes it. No data is altered except NULL backfill of the new columns.

**L-3 (LOW, pre-existing): index creation only runs when `changes` is non-empty.**
`migrate.apply` appends to `changes` only for backfilled columns (`:85-89`). If a release added
only nullable, no-default columns with indexes, their indexes would not be created on an
existing database. This affects performance only, and has no effect at this candidate: the
rehearsal showed no missing indexes.

## 5. Laura identity, brand assets, owner Etsy fields: PASS

- **Identity.** `laura/core/identity.py`. Genesis and current records are pinned by SHA-256.
  `ensure()` writes genesis once, applies only `RECORDED_AMENDMENTS` (D-FB-14, which must be in
  `AUTHORISED_IDENTITY_AMENDMENTS` and in DECISION_LOG), and verifies the hash chain on every
  load (`:325-377`). `amend()` refuses any actor except "owner" and any unlisted or unlogged
  decision (`:417-438`). Nothing in `src/` calls `amend(`. `IDENTITY_ID =
  laura-r2-a42aeac7` is derived from the pinned `FACE_SHA256` (`visual/canonical.py:45-62`).
- **Brand assets.** `brand/owner_source/SHA256SUMS` verifies (logo and banner OK).
  `export_masters` has no caller in `src/`. Runtime writes go to temp or candidate review
  directories, never to `owner_source/`.
- **Owner Etsy fields.** `store_foundation/live_state.py:85-161`: shop name, icon, banner,
  title, about, and Laura's member profile and role are `owner_configured`. `write_refusal`
  refuses them permanently, and `guard()` raises `OwnerFieldProtected`. The live-observation
  POST only records observations. Drift produces only proposals (`writes_performed`).
  `commerce/shop_package.py:411-418` strips `OWNER_CONFIGURED_API_FIELDS` from the only
  updateShop field list, and no updateShop call exists in the client.

## 6. Secrets: PASS

- `tests/test_secret_scan.py`: 7/7 OK, including "no credential-shaped string in tracked files,
  evidence or generated artefacts" and "includes untracked and generated files".
- **Logs.** The Etsy refresh-token rotation logs a fingerprint only (`integrations/etsy.py:295`).
  The access log scrubs sensitive query parameters (`app/access_log.py`). `Credentials.__repr__`
  hides secrets. The CC stores only hashes of session, device and recovery tokens. The
  passphrase is never stored.
- **Responses.** The recovery code is returned only to the operator-token route. No endpoint
  returns an environment secret. `approvals._ops_token()` uses the token server-side to seal
  grants and never returns it.

## Not covered

- Production environment values (TOTP secret, proxy hops, ceiling variable) were not read.
- No Postgres-server rehearsal for this exact candidate (see area 4).
- I did not audit areas outside the six listed, or the 968 commits' functional behaviour
  generally.
