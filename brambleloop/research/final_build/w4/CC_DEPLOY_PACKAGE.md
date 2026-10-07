# Owner Command Center — deploy-readiness package (lane W4-CC)

Written 2026-10-07 (UTC) by lane W4-CC. **Nothing was deployed.** No Railway mutation, no push
to `claude/repository-setup-nc9x6o`. All production facts below are read-only observations
of public, unauthenticated endpoints, or repository history.

## 1. What production runs now vs the integrated head

| | Production (observed) | Integrated head |
|---|---|---|
| Commit | **fcb982d** (`fcb982d57e291c88d9f78eaa091e90904b6c2cc9`) | `claude/visual-investigation` (f5c7aa4 at 2026-10-07T00:12Z, moving) + wave-4 lanes incl. `claude/w4-CC` |
| Evidence | `GET /api/status` and `/health` → `build.commit = fcb982d…`, branch `claude/repository-setup-nc9x6o` (read 2026-10-07T00:12Z); `release/DEPLOYED_HISTORY.json`; `ops/deployed_sha.py` | `git rev-list --count fcb982d..claude/visual-investigation` = 665 commits at fee1cfe; 584 files under `brambleloop/src` changed (+139k / −2.8k), 399 new src files |
| Command Center | **absent**: `GET /cc/` → 404, `GET /api/cc/auth/status` → 404 | v1.1 PWA at `/cc/`, `/api/cc/*` (61 owner-session routes), wave-3 Laura, K4/K7/K11 surfaces, W4-CC Company + Completion views |
| Health | `/api/verify` ok (12 checks), shadow, scheduler/worker ticking, 166 dead letters (all deliberate refusals), 18 open incidents | — |
| Phase | shadow | stays shadow (nothing in this package changes the phase) |

`origin/claude/repository-setup-nc9x6o` == fcb982d, and it is an ancestor of the integrated head
(0 commits on the production branch that the head lacks), so the deploy is a fast-forward.

## 2. What will change for the owner

- A real HTTPS phone app: `https://brambleloop-os-production.up.railway.app/cc/` (installable
  PWA; same origin as today's dashboard, so TLS is Railway's existing certificate).
- Tabs: Laura (talk), Home, Approvals, Money, Store, **Company** (every department and agent:
  active / sleeping / blocked / unhealthy / UNKNOWN, current job, last useful result, next wake;
  owner actions, approvals, store, pipeline, finance, autonomy/learn, Build 2 closure, Final
  Master closure, visual, blockers), **Completion effort** (lanes from
  `research/final_build/w4/COMPLETION_BOARD.json`, both the CC schema and the integrator's
  `wave4.completion_board.v1`), Operations, Autonomy & Learn, Insights,
  Notifications, Timeline, Ask, Account, Emergency.
- Wave-4 wiring (2026-10-07): **Company** also shows visual pipeline stages from
  `VISUAL_STATUS.json` (each stage "STATUS (basis)", e.g. D = PARTIAL (measured), the stale
  dashboard value shown as superseded), competitor findings (`intel.findings.latest`, each with
  provenance + confidence grade), and live-shop-vs-repo drift. **Store** shows live drift
  (repo proposals ADOPT_LIVE_INTO_REPO only; software never writes to Etsy), STORE_READINESS
  counts + every non-PROVEN item with its gate, competitor findings, and a form to record what
  the live shop shows (`POST /api/store/live_observation`).
- Build 2 headline (dashboard `/`, `/api/build2` `headline`, CC Build 2 card) is the closure
  ledger (`closure.dashboard`): executable remaining = OPEN only; the registry's own counts are
  labelled "registry claim".
- The existing server-rendered dashboard `/` and all `/api/*` reads keep working (head adds
  routes; see §5 for one performance caveat).
- Everything else in the 665-commit integrated head ships with it (Build 2 runtime, v1.1 lanes
  A–I, wave-3, wave-4). That is the real size of this deploy: the Command Center cannot be
  shipped alone without a separate cherry-pick branch, which would be an untested tree (the
  release proof binds to a tree digest) — not recommended.

## 3. Schema / migrations

- `Database.create_all()` at boot = `Base.metadata.create_all` + `core.migrate.apply`
  (additive only: new tables, new nullable/defaulted columns, indexes; never drops, renames or
  narrows). Evidence: `research/final_build/POSTGRES_MIGRATION_EVIDENCE.md` — fcb982d schema →
  head: 21 changes, 51/51 tables preserved, 0 row-count mismatches, `migrate.plan` idempotent.
- Command Center tables (`cc_owner_sessions`, `cc_nonces`, `cc_security_events`, `cc_kv`,
  notifications, Laura/private tables) are created lazily by their `ensure_tables` (additive).
- W4-CC adds **no** table or column.
- Limit (honest): a rehearsal against a snapshot of the real Railway Postgres has not been run
  (that DB is not touched by any lane). It remains the recommended pre-deploy step.

## 4. Required / recommended environment variables (web service)

| Variable | Required? | Value | Effect if absent |
|---|---|---|---|
| `BRAMBLELOOP_OWNER_PASSPHRASE_HASH` | **required for login** | output of `python -m brambleloop.app.command_center.auth hash` (PBKDF2-SHA256, 600k iterations); run locally, paste only the hash | login closed (503-safe "not configured"); the PWA says so; nothing is open |
| `BRAMBLELOOP_OWNER_TOTP_SECRET` | strongly recommended | base32 RFC 6238 secret, added to the owner's authenticator app | passphrase-only login |
| `BRAMBLELOOP_TRUSTED_PROXY_HOPS` | **required on Railway** | `1` (Railway's single edge proxy appends the client IP) | every client looks like the proxy's IP, so per-client login rate limits collapse into the global one (owner still protected by the trusted-device cookie, but limits are coarser) |
| `BRAMBLELOOP_PUBLIC_ORIGIN` | recommended | `https://brambleloop-os-production.up.railway.app` (or the custom domain) | origin derived from the Host header (works on Railway; explicit is stricter) |
| `BRAMBLELOOP_PRIVATE_MEMORY_KEY` | optional | ≥32 random bytes, base64 | Laura's owner-private memory stays disabled (UNKNOWN/“not configured”); nothing private is stored |
| `BRAMBLELOOP_OPS_TOKEN` | already set in production (operator bearer) | unchanged | operator routes 503 |
| `DATABASE_URL` | already bound (Postgres) | unchanged — confirm on web/worker/scheduler (DEPLOY_CONTROLS action 3) | head refuses SQLite on the host → crash-loop (fail-closed) |
| `BRAMBLELOOP_BOOT_GUARD` | leave unset for the first deploy | — | see §6 (unproven build → SHADOW + P1) |

No secret is stored in the repository; the hash and TOTP secret are entered in Railway → service
→ Variables by the owner.

## 5. Security review of every exposed route (integrated head + W4-CC, enumerated from `security.iter_api_routes(main.app)`)

| Class | Count | Control | Verdict |
|---|---|---|---|
| `/api/cc/*` owner-session | 61 (+2 public: `GET /api/cc/auth/status`, `POST /api/cc/auth/login`) | `security.operator_gate` → `auth.gate`: default-deny for the whole prefix; `__Host-bl_cc` cookie `HttpOnly; Secure; SameSite=Strict`, only SHA-256 stored, 12 h absolute / 2 h idle, revocable; every mutation needs `X-CSRF-Token` (HMAC of session) + fresh `X-CC-Nonce` + `X-CC-Timestamp` (±120 s, single use) + same-origin `Origin`/`Sec-Fetch-Site`; consequential actions need step-up within 5 min (5 failed step-ups revoke); login and mutation rate limits; every refusal audited in `cc_security_events`. The operator bearer token is **not** accepted as an owner session (tested). | PASS — `test_route_auth_default_deny` 7/7, `test_rc1_auth` 11/11, `test_v11_cc_auth`, `test_w4_cc_company::test_routes_default_deny_without_owner_session` |
| W4 wiring routes | 2 | `POST /api/store/live_observation`: in `security.OWNER_SESSION_PAGES`, so `auth.gate` requires owner session + same-origin + CSRF + fresh nonce; body validated by `live_state.record_observation` (unknown fields/future dates refused, 400 audited in `cc_security_events`); success appends one `store.live_observation` audit row with actor `owner:cc:<session>`; performs no Etsy write. `GET /api/mjs/findings`: in `OPERATOR_GET_ROUTES` (operator bearer; the owner reads the same data through `/api/cc/company` and `/api/cc/store`). | PASS — `test_w4_cc_company` (17/17) incl. no-session 401, bearer-only 401, no-CSRF 403; `test_route_auth_default_deny` |
| `/cc/` static PWA shell + `/cc/store-preview` | static; store-preview owner-session gated | `_StrictStatic`: CSP `default-src 'none'; script-src 'self'; style-src 'self'; … frame-ancestors 'none'; object-src 'none'` (no inline script or style), `Cache-Control: no-cache`; the shell holds no data; service worker never caches `/api/` | PASS — `test_v11_pwa_static`, `test_v11_pwa_browser` (108 checks at 390×844, 0 console/CSP errors) |
| operator-bearer routes | 61 (all non-GET outside `/api/cc/` + `OPERATOR_GET_ROUTES`) | `core.opsauth` bearer; 503 when unconfigured, 401/403 when wrong | PASS (default-deny test walks every route incl. routers) |
| public mutating, justified | 1 (`POST /api/learn/lessons/{slug}/review`, own reviewer credential) | separate credential | unchanged |
| public noted | 4 (`/health`, `/api/etsy/oauth/callback`, `/api/verify`, `/ops/teardown`) | reasons in `security.PUBLIC_GET_NOTES` | unchanged |
| public read-only aggregates | 160 GETs (dashboard `/`, `/api/status`, `/api/closure`, …) | read-only; `CustomerRefScrubMiddleware` redacts buyer identifiers from any unauthenticated JSON/HTML; `test_customer_data_auth` sweeps them | PASS for data exposure. **Finding (MEDIUM, availability):** `/api/closure`, `/api/build2/maturity` and the server-rendered `/` (its Build 2 card calls `closure.matrix`) compute the closure matrix synchronously: ~55 s CPU on a cold idle process (168 s measured under parallel test load), ~10–25 s warm, on the single uvicorn worker, unauthenticated. Not present at fcb982d. Repeated hits slow every route (including `/cc/`). The Command Center itself does **not** have this problem (W4-CC computes it off the request path, once per 30 min, `company.build2_snapshot`). **Mitigated in `claude/w4-CC`:** `main.closure_matrix_shared` / `maturity_report_shared` make those reads single-flight and reuse the matrix while the live gate table and requirements file are unchanged (gates are still read on every request, ~0.1 s; an opened gate forces a fresh matrix), maturity for ≤5 min with `reused_from`. Test: `test_w4_cc_company::test_public_closure_reads_are_single_flight_and_reused`. Residual: a cold process still pays one computation. |
| All responses | — | `SecurityHeadersMiddleware`: CSP (dashboard keeps `'unsafe-inline'` style only), `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, COOP same-origin | PASS |

## 6. Release proof and boot guard (must read)

The head carries the runtime boot guard (`ops/release_record.py`, A3-05). On Railway, a build
whose deployable tree is not named by a committed `release/RELEASE_<sha>.json` (written by
`ops/deploy_guard.py record` after a clean full suite, committed on top) **boots as SHADOW and
opens a P1 incident `release.unproven_build` that halts publication**. No release record has
ever been committed (`git log --all -- 'brambleloop/release/RELEASE_*'` is empty).
Consequences: production is already shadow, so behaviour is the same; but the owner would see a
P1 in the Command Center, and `ops/deploy.sh` (the sanctioned path) refuses without the record.
Therefore the bounded validation lane must: run the full suite on the integrated SHA X →
`python3 ops/deploy_guard.py record --sha X` → commit `brambleloop/release/` as Y.

## 7. Exact owner action (OWNER ACTION REQUIRED — one batch)

1. **Approve the production deploy of commit Y** (the integrator names Y = the release-record
   commit on top of the integrated head that includes `claude/w4-CC`). Mechanism:
   `ops/deploy.sh` run by the integrator (guard `check` → push Y to
   `claude/repository-setup-nc9x6o`; Railway builds on push), or, with branch protection
   (DEPLOY_CONTROLS action 1), merge the PR `Y → claude/repository-setup-nc9x6o` on GitHub.
   - **Why:** production deploys are owner-controlled; a push to that branch is the deploy.
   - **Max cost:** Railway usage delta **UNKNOWN (not provable from the repository)**: the
     service, replica count (1) and plan stay the same; the head runs more background job types,
     so CPU/RAM may rise. The repository's own estimate (CLOUD_HOSTING_PLAN.md §6, ASSUMED list
     prices) is declared CA$7/month today, ceiling CA$20/month; no new paid service, no new
     provider spend (phase stays shadow; model spend stays under its existing ceiling).
   - **Minutes:** ~5 to approve/merge; Railway build ~5–10.
   - **Consequence of waiting:** the owner has no phone Command Center (prod `/cc/` = 404) and
     keeps reading the fcb982d dashboard, which lacks the autonomy, closure and Laura surfaces.
2. **Set web-service variables** (Railway → brambleloop-os → Variables), before or with the deploy:
   `BRAMBLELOOP_OWNER_PASSPHRASE_HASH`, `BRAMBLELOOP_OWNER_TOTP_SECRET` (recommended),
   `BRAMBLELOOP_TRUSTED_PROXY_HOPS=1`, `BRAMBLELOOP_PUBLIC_ORIGIN=https://brambleloop-os-production.up.railway.app`,
   optionally `BRAMBLELOOP_PRIVATE_MEMORY_KEY`.
   - **Why:** login is closed until the hash exists (safe default); proxy hops make rate limits per client.
   - **Max cost:** CA$0. **Minutes:** 10 (generate hash locally, add TOTP to authenticator).
   - **Consequence of waiting:** the deployed `/cc/` shows "Owner sign-in is not configured", nobody can sign in.
3. **Confirm `DATABASE_URL`** on web, worker and scheduler (DEPLOY_CONTROLS action 3). CA$0, 2 min.
   Consequence: a service without it crash-loops (fail-closed by design).

## 8. Post-deploy verification (read-only, integrator)

`python3 ops/deployed_sha.py` = Y; `GET /health` 200 with `build.commit` Y; `GET /api/verify`
ok; `GET /cc/` 200 with the CSP header; `GET /api/cc/company` without a session → 401; owner
signs in on the phone → Company tab renders, Build 2 card says "computing" for ≤1 min then
counts; no `release.unproven_build` incident (if the record was committed). Append Y to
`release/DEPLOYED_HISTORY.json`.

## 9. Rollback

`ops/ROLLBACK_RUNBOOK.md`: `DRY_RUN=1 ops/deploy.sh --rollback-to fcb982d --reason "<owner reason>" --deployed Y`
then the real run (integrator, owner's go-ahead). fcb982d is listed in `DEPLOYED_HISTORY.json`.
Schema: additive only, fcb982d code ignores the added tables/columns (verified in
POSTGRES_MIGRATION_EVIDENCE.md); no down-migration needed. Owner sessions created on Y are
simply unused after rollback (fcb982d has no `/cc/`).
Time: ~10 min including Railway rebuild.
