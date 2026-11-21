# B19 security and integration review: VERDICT

- **Reviewed:** `claude/batch19-fixers` @ `8204c93b`, compared with production `511a8c63` + `13585c4f`
- **Reviewer:** independent security/integration review session, 2026-11-21 (UTC)
- **Fix branch:** `review-results/b19-security-fix` (based on `8204c93b`, carrying the fix and its tests)
- **Mutation tests:** `brambleloop/tests/test_b19_security_directive.py`. On `8204c93b`, **11 of 16 fail**. On the fix branch all 16 pass, and the existing `test_owner_directive_approve_all.py` still passes 6/6.

## Verdict per unit

| Unit | Verdict | Why |
|---|---|---|
| `ops/owner_directives.py` | **BLOCK → SHIP with fix** | S1 (HIGH) renewal through a fresh or reset store; S3 (LOW) race; secret-hygiene nit |
| `gateway/paid_provider_gate.py` (`_directive`, `_current`, `is_active_id`) | **BLOCK → SHIP with fix** | S2 (MEDIUM): directive authority is not bound to the directive's own ceilings or lifetime |
| `app/main.py` startup apply | **SHIP once S1 is fixed** | Wrapped in a broad `try` and never prevents a boot. On its own, though, it turns S1 into "re-mint on every boot", so it must not ship without the S1 fix |
| `runtime/owner_queue_ops.py` | **SHIP** (with the S1 fix) | The sweep signs nothing. `apply` is a separate step. `work_done` counts only new activations, so a quiet hour still backs off |
| `improve/autocoder*.py` + `autocoder-ci.yml` (eng/autocoder) | **SHIP** | Details below |
| `ops/autopromote.py` + `certify-and-promote.yml` (eng/autopromote) | **SHIP** | Details below |

## Findings

### S1: HIGH, renewal loop. The directive has no sunset in code.

`apply()` enforced "once, never renewed" only through database state: it checks for a prior row with `activated_by == ACTOR`. In any store that has no such row, it writes a new pair of activations with `expires_at = now + 30 d`. After `8204c93b` it does this on **every boot** and on every hourly `ops.owner_queue_consolidate`, with no time limit. The stores that lack the row include:

- a new environment or staging database;
- a production database restored from a backup taken before 2026-11-20, which is exactly the rollback path that `autopromote`'s backup gate exists to make possible;
- an `paid_provider_activations` table that has been dropped or recreated (the gate's tables are "additive; a rollback simply ignores them").

In each case FLUX generation and the vision judge come back on for another 30 days, months after the owner said "once it's at 0, I will take over approval". The owner's statement covered what was pending at 2026-11-20 13:20 UTC. It was not standing authority.

The tests `test_s1_a_fresh_store_after_the_window_is_never_given_an_activation` and `test_s1_a_store_reset_two_months_later_is_never_reactivated` demonstrate it on `8204c93b`: both fail.

**Fix (pushed):**
- Add `GIVEN_AT = 2026-11-20T13:20Z` and `SUNSET = GIVEN_AT + EXPIRY`.
- `apply()` refuses when `now` is outside `[GIVEN_AT, SUNSET]`.
- `expires_at = min(now + EXPIRY, SUNSET)`.

### S2: MEDIUM, authority. Any row bearing the directive's name passes, whatever its ceilings or lifetime.

`_directive(row)` checked three things only: `activated_by == ACTOR`, `step_up.owner_directive == DIRECTIVE_ID`, and that (provider, scope) is in `ACTIVATIONS`. It did not check:

- the row's ceilings,
- `max_calls_per_run` or `max_attempts_per_request`,
- `activated_at` or `expires_at`.

So a row such as `monthly_ceiling_cad=90, max_calls_per_run=500, expires_at=2099` authorised spend through both `_current` and `is_active_id`. `authorize()` enforces the ceilings that are on the row itself, so in that case the provider ceiling became CA$90. That row could come from a bad migration, a hand-written SQL fix, a restored dump, or any future code path that writes activations. The company monthly ceiling, the reservation and `uncovered_company_exposure` still cap the total. Even so, the per-provider ceilings the owner was promised (CA$40 and CA$10) would no longer bind, which is why this is MEDIUM and not LOW.

I found no write path today, other than `apply()`, that a non-owner can reach. `activate()` requires `verify_step_up`, and a free-form `by=ACTOR` there still needs a real step-up.

**Fix (pushed):** new `owner_directives.authorises(row)`, which the gate's `_directive` now calls. Directive authority now requires all of the following:

- the exact actor and marker, with no `session_public_id`;
- every ceiling ≤ the `ACTIVATIONS` entry;
- `max_attempts_per_request` ≤ `DEFAULT_MAX_ATTEMPTS`;
- `max_calls_per_run` ≤ `DEFAULT_MAX_CALLS_PER_RUN`;
- `activated_at` within `[GIVEN_AT, SUNSET]`;
- a lifetime ≤ `EXPIRY`.

It fails closed on any unreadable field.

Rows already written in production (activated around 2026-11-20 or 21, lifetime 30 d) still pass, so the fix does not switch off an activation that is in force.

### S3: LOW, race. The check-then-insert ran without a lock.

The boot `apply` (web process) and the hourly job (worker) can run at the same moment. Each could see no prior row, and both would then insert. The spend effect is bounded: daily and monthly sums are per provider and `_current` uses the newest row. The per-gallery sum, however, is keyed on `activation_id`, so it resets when a second row appears.

**Fix (pushed):** the check and the insert now run inside `gw.budget_lock(db)` (Postgres advisory transaction lock, or SQLite `BEGIN IMMEDIATE`).

### S4: NIT, secret hygiene. Raw exception text reached the job audit.

`apply()` copied `str(exc)[:120]` into `refused`. That ends up in the `ops.owner_queue_consolidate` audit `detail`, which is visible in the owner panel and in readback. Driver errors can carry SQL text, parameters and DSN fragments.

**Fix (pushed):** only the exception's type name is kept.

## Autocoder (eng/autocoder): SHIP

- **Disabled by default:** `DEFAULT_ENABLED = False`. An unset or blank `BRAMBLELOOP_AUTOCODER_ENABLED` means OFF, checked before any spend. When enabled without `BRAMBLELOOP_GITHUB_TOKEN`, the job reports UNKNOWN before any spend (`test_eng_autocoder` H covers this). The six-hourly cadence is harmless while it is OFF.
- **No model-written code runs in the production worker:**
  - The `Workspace` operations are list, read, grep, edit and create. The `test` operation is a stub that returns "not run".
  - `autocoder.py` contains no `subprocess`, `sys.path`, `importlib` or `exec`.
  - The tarball is extracted by `_safe_extract`, which skips symlinks and paths that leave the workspace, so a read cannot reach `/proc/self/environ` through a link.
  - `.github/`, `ops/`, `app/main.py`, `Dockerfile` and `railway.json` are on the path denylist. The model therefore cannot add a workflow that posts its own `brambleloop/autocoder-ci` success status.
- **Spend:**
  - Per-request CA$3.50 limit, per-month CA$40 limit capped by `min(month, company ceiling)`.
  - The environment can only lower limits; NaN, negative or infinite values fall back to the hard limit.
  - An unreadable ceiling binds at 0.
  - Every call goes through `failover.job_gateway` under the company ceiling.
- **CI:**
  - The `test` job has `contents: read` and no secrets.
  - The `report` job has no checkout, only `statuses: write`, and posts `success` only when `needs.test.result == success`.
  - `ci_readback` accepts only a status created by `github-actions[bot]` for the exact SHA.
- **Residual (not blocking):**
  - A test that a model wrote does run on the GitHub runner. It sees `contents: read` and the checkout's persisted `GITHUB_TOKEN`. That is acceptable, but `persist-credentials: false` on the checkout would remove even that read token. Recommended, not required.

## Autopromote (eng/autopromote): SHIP

- `workflow_dispatch` only. It never runs on its own, and it stays inert until the owner adds the `RAILWAY_TOKEN` secret.
- **Backup gate kept:**
  - No token → REFUSE.
  - Triggered FAIL or CRASHED → REFUSE, even when an older OK exists.
  - No verdict → a dated `BK RESULT OK` is accepted only when it is 0 to 24 h old. Negative ages (clock skew, a forged future timestamp) are refused.
  - The workflow step uses pipefail, and a separate step exits 1 unless `ok is True` (B19 B1, mutation-tested in `test_autopromote`).
- Read-only except one db-backup redeploy. `history_append` appends only an observed SHA.

## Not verified here

- I did not read Railway variable values, as instructed. I therefore cannot say whether `BRAMBLELOOP_AUTOCODER_ENABLED` is unset in production. The panel and readback (`improve.autocoder.readback`) report it and should be checked there.
- I did not run the full suite; only the directive, gate and owner-queue suites plus the standard compiler/reverse/twin suites. The results are in the fix commit message.

## Exact merge instruction

1. Merge `review-results/b19-security-fix` into `claude/batch19-fixers` before `8204c93b` goes to production. The boot-time apply in `8204c93b` must not ship without the S1 sunset.
2. Production today (`13585c4f`) already applies the directive hourly with no sunset. That is S1 already in production, and the next release should carry this fix.

## Regression check (fix branch vs 8204c93b)

27 suites that import the gate, the directive or the owner queue were run on the fix branch: 23 pass.
Three fail **identically on unfixed `8204c93b`**, so they are pre-existing in batch19-fixers and not caused by this fix:
- `test_eng_vis_flux::test_open_motif_recoveries_block_a_replacement` (22/23)
- `test_w4_wraptest`: `plain_run_waits_for_certification`, `plain_run_not_bound_by_an_open_experiment` ("no listing package is recorded")
- `test_w5_v0_paid_provider_gate::test_key_without_activation_a_render_and_a_paid_production_generator_are_refused` (51/52; the run stops at `waiting_for_sale_admission`)

`test_cert_design_pipeline` timed out at 900 s under a 27-way parallel run and was not rerun. These pre-existing failures are a batch19-fixers merge issue for its own owner, separate from this security verdict.
