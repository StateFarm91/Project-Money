# Independent security review: combined release candidate e3747c5

- Date: 2026-10-11 (UTC). Reviewer: independent security reviewer (did not write this code).
- Scope: `git diff 0417f35..e3747c5 -- brambleloop/src ops brambleloop/Dockerfile brambleloop/railway.json`
  (80 files, +5872/-199). Production runs 0417f35. The Dockerfile and `railway.json` are
  unchanged in this delta.
- Earlier reviews:
  - `INDEPENDENT_SECREVIEW_2c6d775.md` (no blocker).
  - `INDEPENDENT_SECREVIEW_5ad94dd.md` (no blocker). 5ad94dd is the minimal Laura release, a
    faithful subset of this candidate, and its findings apply here unchanged.
- Mode: read-only, in a detached worktree at e3747c5 (W4-COMBREL was not touched). No Railway
  or Etsy calls, nothing spent, and no secrets were read.
- Tests: run one at a time, each with a private TMPDIR that was deleted afterwards.
  - `test_w4_laura1_budget` 4/4
  - `test_w4_finhealth` 11/11
  - `test_w4_etsycomm` 16/16
  - `test_route_auth_default_deny` 7/7
  - `test_offsite`: all OK
  - `test_w4_b2gates` 12/12
  - `test_deploy_verify`: 0 failing
  - `test_w4_marketintel` 7/7
  - At 5ad94dd: `test_w4_laura1_briefing` 19/19
- Line numbers refer to e3747c5 under `brambleloop/src/brambleloop/`, unless the path starts
  with `ops/`.

## Verdict: NO BLOCKER

| # | Area | Result |
|---|------|--------|
| 1 | Spend safety | PASS |
| 2 | Laura briefing | PASS (see the 5ad94dd review; the files are byte-identical) |
| 3 | New Command Center routes and actions | PASS |
| 4 | Offsite archive | PASS |
| 5 | Shadow mode | PASS |
| 6 | Migration | PASS. No ORM model, column or table change in the delta |
| 7 | Release, deploy guard, `deploy.sh`, `verify_deploy.py` | PASS |

## 1. Spend safety: PASS

- **CA$0 agents.** `gateway/anthropic.py:243`: a registered CA$0 agent now gets a 0.0 ceiling,
  not `None`. `check_budget_cad` therefore refuses any positive estimate before the provider
  is called. This is stricter only.
- **Laura's CA$0.50/day.** It is checked and reserved before every call, on this path:
  1. `laura_briefing.synthesize`: the permission is read; ≤ 0 means an audited refusal and
     no call.
  2. `failover.gateway_for`: the month and the agent's day are checked per model.
  3. `complete_json`, then `check_budget_cad`: month, provider and agent day, reserved
     atomically.

  Only the briefing bills agent `laura`. The monthly ceiling and the D-1 NaN guards are
  unchanged.
- **Ads authority** (`app/command_center/approvals.py:383`, `_set_ads_limit`; action
  `ads.set_limit`).
  - Step-up is required: `ACTIONS[...][0] is True`, enforced in `api.py:310` (`run_action`).
  - It needs `0 < daily <= CONSERVATIVE_CAPS.daily_cad` (CA$3) and
    `daily <= lifetime <= campaign_cad` (CA$25). NaN and inf fail these comparisons and are
    refused.
  - It does not clear a paused limit.
  - Setting it opens the `ad_authority` gate (`runtime/growth_ops.py:191`). Any actual spend
    still has to pass the `ads.campaign` headroom checks and then
    `paid_media.authorise_spend`. That refuses below PRODUCTION and raises
    `CapabilityNotEnabled` because no ad integration exists.
- **No runtime raise of a ceiling.** No new route writes an `Agent` ceiling. The only new
  `SpendLimit` writer is the action above, which needs step-up and is hard-capped. Laura's
  ceiling changes only through a reviewed deploy (`seed_defaults`, the existing mechanism).
- `/api/verify`'s `every_agent_has_a_cost_ceiling` uses `registry.ceiling_audit`. Declared
  CA$0 agents are accepted as "no spend". A non-finite ceiling, an undeclared zero or a
  no-spend agent that spent still fails the check.

## 3. Command Center routes and actions: PASS

- **Etsy routes.**
  - `GET /api/cc/etsy`, `POST /api/cc/etsy/recheck` and `POST /api/cc/etsy/connect`
    (`app/command_center/api.py:335-360`) sit under `/api/cc/`. The owner-session gate
    (session, same-origin, CSRF, nonce, mutation rate limit) applies before the handler runs.
  - Connect also needs step-up (`api.py:353`).
  - Recheck only queues one CA$0 `etsy.probe`, and at most one per minute (an idempotency key
    per minute).
  - `etsy_connect.status` returns booleans, scope names and the probe's state. Etsy's error
    text is redacted against the keystring and shared secret (`intel/etsy_public.py`
    `etsy_error_text`) and capped at 200 characters.
- **Authorize URL.** `connect` returns the authorize URL, which carries the keystring (a public
  client id), a PKCE challenge and the OAuth `state`. The audit stores only the state
  fingerprint. The verifier and tokens stay sealed in the database.
- **Phone side.** The phone navigates only when the host is exactly `www.etsy.com`
  (`static/js/views/store.js`). The service worker never caches `/api/`.
- **Acceptance ruling** (`approvals.py:360`, action `acceptance.rule`). It needs step-up and a
  reason. The ruling must be one of two fixed values. It records a done `OwnerAction` and
  publishes nothing.
- **Tester roster** (`POST /api/tester/agreement`, `app/main.py:1308`). It requires the
  operator credential (inline `opsauth.check`, and default deny for POST). It records only,
  sends no message, and requires express CASL consent to be named.
- **Insights intake** (`POST /api/insights/paste`, `main.py:3133`). It requires the operator
  credential. Without `confirm` it only parses. The text is capped at 20,000 characters and
  only its sha256 is audited. The phone page writes all output with `textContent`.
- **Decide-first and sections UI.** New JS builds every element with `h()` and uses no
  `innerHTML`. Hrefs are hash routes with `encodeURIComponent`.
- **`/cc` redirect** (`command_center/__init__.py:51`). It returns a 308 to a fixed, relative
  `/cc/` plus the query string, so it cannot be used as an open redirect. It serves no data.
- **Owned-surface probe** (`growth/owned_surface.py`). It is a scheduled job, not a route. It
  makes a GET to the owner-configured site and to Pinterest's boards list. The Pinterest token
  goes only in the `Authorization` header and is never written to the audit record.
- **New public GETs.** These follow the existing convention: a GET not in
  `OPERATOR_GET_ROUTES` is a public aggregate.
  - `/api/market-intel`
  - `legal_access` inside `/api/policy`
  - `loops` inside `/api/improve`
  - `filters` inside `/api/catalogue`

  `policy_access.status` reads the database only, with no outbound fetch on the public path.
  See LOW-2.

## 4. Offsite archive: PASS

`core/offsite.py:381` (`archive`):

- The encryption key is resolved before the export. With no key the archive is refused with
  `stage=configuration`, and nothing is exported or uploaded.
- The payload is sealed inside `archive` (`:445`) before any transport is called. The result
  must start with `ENCRYPTION_HEADER` and must not contain the plaintext; otherwise the archive
  is refused.
- The new `put_raw`/`get_raw` (`:348`) move only sealed bytes and are used only by `archive`.
  The old `put` path (teardown mirror) still seals itself and refuses without a key.
- The read-back is checked against the ciphertext digest. The archive is then decrypted and
  restored into scratch SQLite.
- No key material is logged or returned: `state` reports only `encryption_key_present`.
- `ops/db_backup/housekeep.sh` is NOT DEPLOYED (the header says so) and does nothing unless
  `OFFSITE_UPLOAD=1`:
  - it encrypts with the owner's public key only and refuses a private key;
  - credentials go to curl on stdin, not argv;
  - it reads the copy back and compares the sha256.

  See INFO-3.

## 5. Shadow mode: PASS

- No added line calls an Etsy write (`create_draft`, `activate`, `update_listing`, uploads), a
  phase transition, `shadow_writes_authorised` or any outbound messaging.
- New outbound GETs are read-only:
  - the policy-access robots and Help Center reads, run as a job;
  - the owned-surface probe;
  - `verify_deploy` reading `/health`.
- `pipeline.py` merges `PROPOSED_ENGINEERED` only when `launch0.CATALOGUE_FLOOR_APPROVED` is
  set. That is product drafting, not publication.
- `release_gates` only adds measurements.

## 6. Migration: PASS

The delta adds or removes no `__tablename__`, `mapped_column` or `Column` line. New data uses
existing tables (`OperatingReading`, `AuditLog`, `OwnerAction`, `SpendLimit`, `cc_*`).
`finance/accounting/schema.py` now rolls back a caller-owned session only when that session's
transaction is already lost, and always re-raises.

## 7. Release and deploy: PASS

- `ops/deploy.sh` now pushes the resolved commit sha, which the guard has already checked. It
  then runs `ops/verify_deploy.py`, which makes read-only GETs to a fixed production `/health`
  URL and exits 3 or 4 when production is not running the sha.
- It never rewinds and never calls Railway.
- `ops/deploy_guard.py` and the boot guard are unchanged in this delta.

## Findings, by severity

### LOW-1: TOTP is still optional in code (carried from the 2c6d775 review, unchanged)
`app/command_center/auth.py` `verify_owner`. With no `BRAMBLELOOP_OWNER_TOTP_SECRET`, a stolen
passphrase gives a full session and step-up. That now covers Etsy Connect and `ads.set_limit`
(up to CA$3/day, which is still unspendable below PRODUCTION). Confirm the variable is set in
production.

### LOW-2: owner-recorded Marketplace Insights figures are publicly readable
`GET /api/market-intel` (`app/main.py:3174`). It is not in `OPERATOR_GET_ROUTES`, so anyone
with the URL can read the latest `market_intel` payload, which includes owner-pasted Etsy
Marketplace Insights search counts and the competition proxies.

This is consistent with the existing public `/api/insights` and `/api/serp`. However,
`/api/mjs/findings` was made operator-only for competitor intelligence.

*Exploit scenario:* a competitor who finds the Railway URL reads the shop's demand research. No
credentials or customer data are exposed. *Action:* consider adding `/api/market-intel` (and
`/api/insights`) to `OPERATOR_GET_ROUTES`.

### INFO-1: Laura's CA$0.50/day rests on a DECISION_LOG entry relayed by the coordinator
The owner should confirm it once.

### INFO-2: Etsy Connect returns the full OAuth `state` to the owner session
This is inherent, because the owner's browser carries it to Etsy. The audit keeps only its
fingerprint.

### INFO-3: credential quoting in `housekeep.sh` (not deployed)
`ops/db_backup/housekeep.sh:176`. A secret containing `"` or `\` would break curl's `-K`
config parsing. The upload would fail closed with no exposure. Escape these characters before
the script is enabled.

### INFO-4: `/api/verify` now carries each dead-letter type's first error line
The line is capped at 200 characters. Job error heads were already public in other views, so
this exposes nothing new.

## Blockers

None.
