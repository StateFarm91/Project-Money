# Independent security review: release candidate 324927f

**VERDICT: NO BLOCKER**

Reviewer: W-SECREVIEW2, an independent reviewer who did not write any of the code reviewed.
Date: 2026-10-20 (UTC). The review was read-only. Nothing was deployed, no request was sent to
production and nothing was spent.

## Scope

- Production: `1b21e81c`
- Previously reviewed: `1b21e81c..5f18d118`, NO BLOCKER
  (`INDEPENDENT_SECREVIEW_5f18d11.md`, findings M1, L1, L2, L3, I1, I2)
- Candidate: `324927f1003808dd07a14b0cb0bce29e5c7d7cbc` (branch `claude/final-candidate-324927f`)
- Diff reviewed: `git diff 5f18d118 324927f1 -- brambleloop/src brambleloop/requirements.lock
  brambleloop/requirements.txt brambleloop/Dockerfile ops brambleloop/tests/w4_pl_harness.py
  brambleloop/tests/test_w4_integ3_secfixes.py` (12 files, +392/−102).
- These paths have **no changes** in the range: `requirements.lock`, `requirements.txt`,
  `Dockerfile`, `ops/` and `core/db.py`.

## Method

1. Read the whole diff by hand. Followed `/api/etsy/webhook` → `refuse`/`receive` →
   `_refused`, and `reply` → `_reply` → `release_proven` → `core.build.identity` /
   `ops.release_record.BOOT` (`apply_at_import`, `verify_build`).
2. Compiled the new upsert against the PostgreSQL and SQLite dialects, and the
   `etsy_webhook_refusals` DDL against PostgreSQL.
3. Checked whether the table existed in production with `git show 1b21e81c:…/etsy_webhooks.py`.
4. Searched `src/` for every persisted `why` and `str(exc)` in `creative/reference.py`, and for
   every caller of `release_proven`, `RELEASE_UNPROVEN` and the private reply.
5. Ran the tests in a venv installed with `--no-deps --require-hashes` from the candidate lock
   (plus `httpx`). The local interpreter was Python 3.13; the image uses 3.11.
   - `tests/test_w4_integ3_secfixes.py`: 7 OK, PASS 0 failing
   - `tests/test_w4_rel2.py`: PASS 0 failing
   - `tests/test_w4_plact.py`: 8/8 passed
   - `tests/test_w4_pl_reply.py`: 3/3 passed
6. Ran an adversarial probe on file-backed SQLite (3.45.1, WAL): 16 threads × 50 refusals,
   with odd threads sending `bad_signature` and even threads sending 50 distinct unknown
   reasons. Result: exactly 2 counter rows (`bad_signature` 400, `other` 400, which is exactly
   800 total), 2 sampled audit rows and 0 errors.

## Prior findings

| ID | Status | Evidence |
|----|--------|----------|
| M1 | **FIXED** (one residual, R1 LOW) | `app/main.py:2979`, `:2981`; `integrations/etsy_webhooks.py:272-338` |
| L1 | **FIXED** | `integrations/etsy_webhooks.py:118`, `:123` |
| L2 | **FIXED** | `creative/reference.py:398-404`, `:475-481` |
| L3 | **FIXED** | `gateway/laura_register.py:207-231`, `:320-321`; `app/command_center/private_context.py:180`, `:188` |

### M1: FIXED

- **Off the event loop.** `refuse` and `receive` both run under
  `await run_in_threadpool(...)` (`main.py:2979`, `:2981`). `read_body` stays async, and it
  only reads the stream and checks the size cap, with no database work. The body is still
  capped at 64 KiB before anything is handed to a thread. There is no other synchronous DB
  call left on the event loop in this route.
- **The upsert is correct.** `set_={"count": t.count + 1, ...}` (`etsy_webhooks.py:285`)
  compiles on both dialects to
  `ON CONFLICT (reason) DO UPDATE SET count = (etsy_webhook_refusals.count + ?)`. That
  references the **existing** row (the target table), not `excluded.count`, so it increments
  instead of resetting to 1. `first_at` and `last_audit_epoch` are correctly left out of
  `set_`, so the first-seen time and the sample claim survive. The conflict target is
  `reason`, the primary key. SQLite's `ON CONFLICT DO UPDATE` needs 3.24 or later; the venv
  has 3.45.1 and the slim image's libsqlite is newer still.
- **One transaction.** On sqlite and postgresql, the upsert, the conditional sample claim
  (`last_audit_epoch <= epoch - window`) and the sampled `AuditLog` insert run in one
  `db.session()` (`:321-337`). On PostgreSQL the upsert takes the row lock, so the claim in
  the same transaction cannot race another transaction: at most one sample per reason per
  window. The probe and `test_m1_one_refusal_is_one_transaction…` confirm exact counts and
  one sample per reason.
- **The fallback** (`:306-320`, any other dialect) is the old three-step path, which the
  previous review found race-safe. It is unreachable on deployed dialects and marked
  `pragma: no cover`, so it is untested here. That is acceptable.
- **Failures** are still swallowed (`:338`), so a refusal is always answered and nothing
  turns into a 500. The returned payload is the static `reason`/`why`, with no request data.
- **Residual:** see R1 below. Pool exhaustion is not a regression; it is the remaining shape
  of the same availability concern.

### L1: FIXED

`count` and `last_audit_epoch` are `BigInteger` (`:118`, `:123`). The PostgreSQL DDL compiles
to `count BIGINT NOT NULL` and `last_audit_epoch BIGINT NOT NULL`. `etsy_webhook_refusals` does
not exist in production `1b21e81c`: the class and table first appear in `da658123` (REL2),
inside the reviewed range, and production never ran that range. `ensure_table` uses
`create_all(..., checkfirst=True)` (`:130-139`), and the migrations module does not reference
the table. A fresh deploy therefore creates the BIGINT table and **no migration is needed**.
One caveat: if any persistent PostgreSQL database (a staging one, for example) ever ran
`5f18d11`, its table stays int4, because `checkfirst` does not alter an existing table. The
only effect would be the L1 overflow on that database, so this is informational.

### L2: FIXED

- `failed[].why` now carries only `"<ExceptionClass>: <kind>"` for a `ReferenceRefused`, where
  `kind` comes from the closed set {depiction, not_json, closed_vocabulary, empty, refused}
  (`reference.py:475`). Any other exception carries only its class name (`:481`).
  `refusal_kind` returns only literals (`:398-404`). A model-chosen key can at worst
  misclassify the kind; it can never place text in the result.
- `record_refused_reading` stores `{"refusal": kind, "image": image_key[-64:]}`. The image key
  is ours, not the model's.
- `decompositions_refused[].why` is still `str(exc)[:200]` (`:489`). I traced it, and it does
  **not** carry refused model text. `brief()` aggregates readings that already passed
  `check_free_of_depiction` and were stored. Its `ReferenceRefused` text embeds
  `rights.RightsRefused`, which quotes `first.text`, a word from the closed
  `DEPICTION_WORDS` vocabulary, plus fixed prose. The other `brief` refusal is the
  under-two-listings message, which is fixed prose with counts. No change is needed. Using
  `refusal_kind` there too would be a harmless consistency improvement.
- The webhook refusal audit row stores `exc.why[:300]`. Every `why` is fixed prose or a
  server-side number. The only interpolated request value is `event_type` (`:257`), and that
  is reached only after HMAC verification.

### L3: FIXED

- `release_proven` (`laura_register.py:207-231`) is met only when all three hold:
  `core.build.identity` knows the commit, `BOOT.platform_markers` is non-empty, and
  `BOOT.ok` is true. `BOOT` is filled by `apply_at_import` in `main.py:50`,
  `worker_entry.py:35` and `scheduler_entry.py:34`. An empty `BOOT` (in any process that did
  not run the guard) is unmet, so it fails closed.
- `_reply` raises `RELEASE_UNPROVEN` at `:320-321`. That is after the cheap refusals and
  **before** the health read, `check_budget_cad` (the reservation) and `provider._send`. An
  unproven release therefore makes no reservation, no cost entry and no provider call, and
  the test asserts 0 `CostEntry`, 0 `SpendReservation` and no stub calls. The only earlier
  write is the existing `SPEND_UNAUTHORISED` audit refusal, which spends nothing.
- **Entry points.** `reply()` is the only public wrapper, and its only caller is
  `private_context.py:289`. Nothing else in `src/` calls `_reply` or bills `laura_private`.
  `_enablement` now ANDs `release` into `enabled` (`private_context.py:180`, `:188`), so the
  status the owner sees and the enforcement agree.
- **Spoofing.** `BOOT.ok` requires a committed `release/RELEASE_*.json` whose
  `source_tree_sha256` equals the filesystem digest of the running tree, and which passes
  `check_record`. Environment variables cannot produce that. The commit and platform markers
  come from environment variables (`RAILWAY_*`), but only someone who controls the deployment
  environment can set them, which already means owner-level control. Spoofing them still does
  not satisfy `BOOT.ok`. `env` is a keyword argument on the internal `reply()` and cannot be
  set from a request.
- **Test harness.** `tests/w4_pl_harness.py` monkeypatches `laura_register.release_proven`
  only inside the `enabled()` context manager, and restores it in `finally`. `tests/` is
  copied into the image (`Dockerfile:30`), but nothing under `src/` imports
  `w4_pl_harness` (searched), and uvicorn runs `brambleloop.app.main:app`. The stand-in
  cannot affect production.

## Other changes in the range (no security impact)

- `improve/bootstrap.py`: registers one incumbent per prompt name, choosing the highest
  dotted version through `_version_key`. Non-numeric parts sort as −1, so a malformed version
  can never outrank a numeric one. The input is code-defined prompts only. There is no
  endpoint, spend or schema change.
- `seo/strategy.py`: phrase and tag lists only.
- `visual/rnd/hero.py`: changes one deterministic parameter (`hero_gap_ratio` 0.06 → 0.04).
- `core/decision_index.json`: three new decision IDs. This is data.
- `app/command_center/private_context.py`: `_release_deployed` now delegates to
  `release_proven`. The logic is identical, and the output is still non-secret (a short SHA
  and a record file name).
- I confirmed **no new route** (the only route body changed is `/api/etsy/webhook`), and no
  change to auth, spend ceilings, the DB schema (other than the column types of a table that
  has never been deployed) or dependencies.

## New findings

| ID | Severity | Summary |
|----|----------|---------|
| R1 | LOW | A refusal flood can now saturate the shared threadpool and DB pool instead of the event loop |

### R1 (LOW): residual availability on the public webhook, now through the shared pools

- **Where:** `app/main.py:2979`, `:2981` (default `run_in_threadpool`), and
  `core/db.py:97-108` (default QueuePool: 5 connections plus 10 overflow, 30 s timeout).
- **Scenario:** an unauthenticated flood of bad-signature deliveries. Each one takes a token
  from AnyIO's default limiter (40 per process). FastAPI shares that limiter with the
  roughly 187 synchronous (`def`) routes in `main.py`, which include Command Center reads.
  On PostgreSQL, refusals for one reason also queue on that reason's row lock, and each holds
  a connection for its whole transaction (upsert, claim and audit). A sustained flood can
  keep the 15 pooled connections and most of the 40 threads busy, so owner sync routes wait
  up to the pool timeout. This is an **improvement** on 5f18d11, where every refusal blocked
  the whole event loop: async routes and the loop itself now stay responsive, and storage
  stays bounded. It does not block the release.
- **Fix (next release):** give webhook DB work its own small `anyio.CapacityLimiter` (for
  example, 4), passed as `limiter=` to `anyio.to_thread.run_sync`, so a flood cannot take
  shared tokens. Optionally coalesce refusal counts in memory and flush once a second, and
  rate limit `/api/etsy/webhook` per IP at the edge.

I1 and I2 from the previous review are unchanged and still informational.

## Verdict

**NO BLOCKER.** M1, L1, L2 and L3 are fixed as claimed, and I found no regression. I found no
auth or HMAC bypass, no way to spend without a proven release, no persisted model text, no
unbounded storage, and no dependency, Dockerfile or ops change. R1 (LOW) is recommended for
the next release.
