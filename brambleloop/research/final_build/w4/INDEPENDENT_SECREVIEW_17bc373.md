# Independent security review: release candidate 17bc373

**VERDICT: NO BLOCKER.** B1 is fixed, and the fix holds against every bypass I tried.
L1-L4 are fixed.

Findings: **M1 MEDIUM** (a resumed controlled-experiment run can send a new paid render while
the interrupted attempt's billing is unknown; bounded to one extra image, behind owner step-up),
**I7-I11 INFO**. No BLOCKER, no HIGH. Earlier findings: **B1 FIXED, L1-L4 FIXED**, I1-I3 and
I5-I6 still open (unchanged), I4 by design.

Reviewer: W-SECREVIEW5, an independent reviewer who did not write any of the code reviewed,
including the B1 fix. Date: 2026-10-20 (UTC). The review was read-only. Nothing was deployed,
no request was sent to production and nothing was spent.

## Scope

- Production: `b931d17a738d6a5bcd96580f620069b669ca5f57`
- Previous review: `INDEPENDENT_SECREVIEW_7f6dbe8.md` (B1 BLOCKER, L1-L4 LOW, I1-I6 INFO).
- Candidate: `17bc373e` (branch `claude/w4-INTEG4`, "INTEG4: merge w4-CREDHEALTH @ 0b6e699").
- Diff reviewed: `git diff 7f6dbe89 17bc373e -- brambleloop/src
  brambleloop/tests/test_w4_integ4_secfixes.py brambleloop/tests/test_w4_integ4_deliverable_routes.py
  brambleloop/tests/test_w4_credhealth.py brambleloop/requirements.lock brambleloop/Dockerfile ops`
  (26 files, +1,684/−86). `requirements.lock`, `Dockerfile` and `ops/` have no changes in the
  range. Generated data (board snapshots, `final_master_closure.json`) ignored.

## Focus area 1: is B1 closed? **Yes. B1 is FIXED.**

Lines are in the candidate.

### The byte route: `app/main.py:2152-2234`

`GET /api/model-tournament/image/{sha256}` is still public, but now:

1. Lower-cases the digest and requires exactly 64 characters of `[0-9a-f]` (`:2166-2168`).
2. `tournament_image_refusal` (`:2206-2234`) is an allowlist that fails closed:
   - a digest with a `DurableArtifact` row is served **only** if `why_kept` equals the
     reference pack's `KEEP_REASON`; every other keep purpose (deliverable PDFs, certified
     frames, experiment outputs, image-production candidates) is refused, **even if a
     tournament package names it**;
   - a digest with no row is served only if one of the 50 newest `model.tournament` /
     `model.reference_pack` audit rows names it;
   - any exception → refused.
3. After loading, the bytes must start with a PNG, JPEG or WebP magic number
   (`image_media_type`, `:2195-2203`), else 404. A `%PDF` body is never served, whatever the
   allowlist says.
4. `Cache-Control` is now `private`, with `nosniff`.

Bypass attempts (in-process probe, scratch SQLite, sockets disabled; not committed):

| Attempt | Result |
|---|---|
| Kept paid PDF digest, also named in a `model.tournament` audit row | 404 (row exists, not reference-pack) |
| Same, digest in upper case | 404 |
| Certified listing frame (PNG, kept with a `deliverables` reason) named in a tournament row | 404 |
| A PDF whose row is (mis)labelled with the reference-pack `KEEP_REASON` | 404 (magic-number check) |
| An unkept PDF on disk named in a tournament row | 404 (magic-number check) |
| Leading `%20` / URL-encoded junk | 400 |
| Genuine tournament PNG (named, unkept), lower and upper case | 200 `image/png`, `private` |

Who can make a digest "named"? Only `ctx.audit(tournament.TOURNAMENT_ACTION | reference_pack.PACK_ACTION, …)`
inside worker jobs (`runtime/release.py:7867`, `:7881`, `:8696`). No HTTP route writes an audit
row with a caller-chosen action and detail. The substring match (`sha256 in json.dumps(detail)`)
needs the full 64 lower-case characters, so it cannot be widened by a prefix.

Other byte-serving routes: every other `ArtifactStore().get` reached from HTTP is under
`/api/cc/*` (owner session: `store/pdf/{slug}`, candidate and experiment images) or
`/api/continuity/export` (operator credential). The remaining public GETs return JSON or HTML;
`/api/model-asset`, `/api/storefront/preview`, `/api/build`, `/api/verify`, `/api/status` and
the dashboard return no artifact bytes. So a digest published anywhere else can reach only the
tournament route, which now refuses everything except reference-pack and tournament images.
B1's fix therefore does not depend on digest secrecy.

### The audit route: `app/main.py:4936-4975`

Without the operator credential, `detail` goes through `_shorten_digests`, which recurses
into dict keys and values and lists/tuples and cuts every **isolated** 64-hex run (either
case) to 12 characters. Verified on keys, nested lists, upper case and `sha256:<hex>`.
Gaps (defence in depth only, since the byte route no longer depends on it; **I7** below):
the `artifact` and `actor` columns are not shortened; a digest preceded or followed by a
hex letter (`blob<sha>`, `<sha><sha>` concatenations) is not matched because of the
look-arounds. I found no writer that puts a full digest in `artifact` today.

### The sweep test is sound and not vacuous

`tests/test_w4_integ4_deliverable_routes.py` enumerates every GET route of the app (routers
included, via `security.iter_api_routes`) plus every public mutating route, fills each path
parameter with the PDF digest, slug, slug@version, version and `1`, and requests each
without any credential (operator token configured, never presented), on disk and after a
simulated redeploy. It flags raw bytes, base64 and any `%PDF` body.

- On `17bc373e`: 4/4 passed.
- On the unfixed tree `263e94da` (the same test file copied in): **2/4 failed**, both sweeps
  naming exactly `GET /api/model-tournament/image/<sha>` → 200 raw bytes. The test catches B1.
- Limits (INFO): it does not vary query parameters (no current public GET takes a digest or
  slug by query and returns bytes), and it checks bytes, not digest publication.

## Focus area 2: L1-L4

- **L1 FIXED.** `api.py:493-495` `images_restart` calls `auth.require_stepup(db, request,
  "images.restart")` before reading the body; CSRF and nonce are still enforced by the gate.
  `test_l1_restart_requires_step_up` passes.
- **L2 FIXED.** `experiments/controlled.py:382-392` `_price_cad` now uses
  `images.render_estimate_usd(provider, size, refs)` (the gateway's own reservation price),
  converted to CAD, never below the table price. The cap check therefore uses the price the
  gateway bills.
- **L3 FIXED.** `runtime/etsy_ops.py:560-565` `certified_images` checks every certified
  frame's digest with `refuse_if_experiment_image`, after the product-level check. In
  `visual/experiment.py:471-485` the image check now fails closed: when no hit is found it
  re-reads the run table and raises `ExperimentRefused` if that read fails. This is correct and
  not a harmful regression: `ensure_tables` creates the table if it is missing, so only a real
  database error refuses, and in that state the publication path could not complete anyway.
  It applies to all three callers (Etsy upload, `gallery_persist.write_frames`,
  `image_production` approve), all publication paths. Residual (INFO): `candidate_gates` and
  `release_gates` still call the fail-open `is_experiment_image` directly, and the
  `disclosed_listing` export still checks only the product; the Etsy upload path is now the
  fail-closed choke point, which is enough.
- **L4 FIXED (narrowed).** `commerce/deliverables.py:419-431` recomputes `retention_plan`
  just before deleting and deletes only digests both plans would prune; a failed re-read
  prunes nothing. A write landing in the few milliseconds between the second plan and the
  delete is still possible; the comment states it and the consequence (re-kept by
  `secure_release`, never a wrong file) is unchanged. Acceptable.
- Tests: `test_w4_integ4_secfixes.py` 10/10 passed.

## Focus area 3: CREDHEALTH (`gateway/credentials.py`, `/api/cc/credentials`, on-demand check)

### Routes and authority: SAFE

- `GET /api/cc/credentials` (`app/command_center/api.py:786-792`) is under `/api/cc/`, so
  `auth.gate` requires a live owner session; the ops bearer token is not accepted there.
  Anonymous → 401 (`test_on_demand_check_runs_the_job_and_no_key_leaks_anywhere`). It needs no
  step-up. That is acceptable, because it returns only statuses and a fingerprint (I8), never a
  key.
- "Check now" is `POST /api/cc/checks/credentials/run` (`api.py:800-819`). The gate enforces
  same-origin, CSRF, a fresh nonce and the timestamp. `on_demand.CHECKS["credentials"]` has
  `external=True`, so `auth.require_stepup(db, request, "checks.credentials")` runs before
  anything is queued. `run_check` refuses a run less than 60 s after the previous one (429,
  audited), and it only **enqueues** the existing `ops.provider_credentials` job. The worker
  runs it, so the request thread makes no provider call.
- There is no public endpoint: no new route outside `/api/cc/`, and nothing added to
  `PUBLIC_GET_NOTES` or `PUBLIC_MUTATING_ROUTES`. The job type is registered for the
  `orchestrator` agent and classed `_O` (observe) in `authority/classes.py`.

### Key secrecy: SAFE (with I8, I9)

- The key is read from the environment at call time (`_key`), placed only in the request
  header (`x-key` / `x-api-key`), and never put in job inputs or outputs. Job outputs carry
  `{checked, ok, statuses, consecutive_failures}`.
- Every provider answer is cut to 300 characters after `_redact(text, key)`. An exception is
  redacted too. The whole audit record is then JSON-dumped, redacted again and reloaded
  (`check_all:272`). Exception text from `urllib` does not contain request headers.
- The stored record holds no fingerprint, only a 4-hex `rotation_marker` =
  `sha256("brambleloop-rotation-marker:" + key)[:4]`, which is domain-separated and too short
  to confirm anything. Notifications use only the status, the redacted `why`, the marker and
  the static owner action. No cost row is written (the checks are not priced).
- The owner-view fingerprint is `last4` plus `sha256(key)[:12]`, computed live and never
  stored. It cannot be reversed: provider keys are high-entropy, so 48 bits of an unsalted
  hash give nothing to search. It is **not** domain-separated, though, and someone holding a
  candidate key can confirm it offline with one hash (I8).
- The test is not vacuous: the mocked providers echo both keys in their 401 bodies, the test
  asserts `"invalid key [redacted]"` reached the audit row, and then it scans logs, job rows,
  audit details, notifications and both API bodies for the keys and for the fingerprint.
  13 passed, 0 failed.

### Free, budget-neutral, bounded: SAFE

- BFL: `GET https://api.bfl.ai/v1/credits` (fixed URL, verified TLS, 20 s timeout). This is
  a balance read and does not generate. Anthropic: `POST /v1/messages/count_tokens` with a
  1×1 PNG. Token counting is free and is not billed against usage, but it is rate-limited by
  RPM. Neither call goes through a gateway reservation, which is correct for a free call.
  The recorded estimate is CA$0 with its documentation basis.
- Bounded: the daily cadence (`worker.CADENCES`, 86,400 s) plus the on-demand path
  (step-up + 60 s floor). Each run makes exactly one request per provider with no retry
  loop: a failed check is recorded as a status and not retried. Transient statuses alert only
  after 3 consecutive failures (`ALERT_AFTER_CONSECUTIVE`), deduplicated by
  `credential:<provider>:<status>:<marker>`. It is listed in `LIVENESS_JOB_TYPES`, so the
  swarm's back-off does not suppress it, and that cannot make it loop either: the cadence is
  the only scheduler.
- The 60 s floor is read-then-enqueue, not atomic. Two simultaneous owner clicks could queue two
  free checks. This has no cost impact.

### Experiment restart robustness: **M1** (see findings)

`api.py:600-603` now enqueues the controlled run with `max_attempts=2`, so a reclaimed lease
runs `run_job` a second time. `controlled.run_job:419-484` resumes:

- When the image was already stored, it is judged again without a new generation. Vision
  calls are replayed by the paid-call guard, and the vision cap reads the persisted spend.
  **Correct.**
- When attempts > 0 and there is no paid-call job scope, the run settles as failed, billing
  unknown, with the reservation kept. **Correct.**
- When attempts > 0 inside the same job scope, the loop restarts at `attempt =
  resume["attempts"]` and relies on `paid_calls.guarded` to replay or refuse the interrupted
  call. **This is wrong when the interrupted attempt was not the first** (M1). It is correct
  when attempts == 1 (`test_restart_during_the_paid_call_is_never_resent` passes).
- Another job that finds the run `running` is refused. `settle_dead` fails runs whose job
  dead-lettered. Idempotency of the enqueue (the unique key) is unchanged.

## Focus area 4: the CLOSE5 timeout fix: SAFE

`gateway/anthropic.py:773-808`: vision calls pass `timeout=max(timeout_seconds, 180)` into
`_send`. The paid-call guard is unchanged. It is the same `paid_calls.guarded` with the same
fingerprint (the payload, not the timeout) and the same `_classify_failure`.

- A read timeout while waiting for the response raises `TimeoutError`. In `urllib`,
  `getresponse()` runs outside the `URLError` wrapper, so the error is not converted to a
  `TransientError`. `_classify_failure` therefore returns **UNCERTAIN**. The call is recorded,
  an incident is opened, and any later attempt of the job gets `PaidCallUnresolved` (a
  PermanentError) instead of a resend. A timeout cannot cause a double charge.
- No unbounded retry: UNCERTAIN is never resent automatically. `intel.vision.analyse` does not
  start a call that could end past `ANALYSIS_RUN_SECONDS` (40 min, with 180 s headroom per
  call), which is below `worker.MAX_HANDLER_SECONDS` (60 min). The rest of the backlog waits
  for the next run.
- The schema change (every field required, with `""` allowed in the `shot_type` enum) touches
  only the prompt and the grammar. `parse_observation` still validates every answer.

## Focus area 5: other changes in the range

- `ops/on_demand.py`, `runtime/release.py` handler, `worker.py` cadence, `swarm/orchestrate.py`
  liveness/band, `registry.py`, `authority/classes.py`, `pipeline.WORK_KEYS`,
  `notifications.py` (a try-wrapped extension of the candidate list), and `static/js` (one GET
  wrapper): wiring only, nothing security-relevant beyond the points above.
- `requirements.lock`, `Dockerfile` and `ops/`: unchanged in the range.
- **B1 sanity across `b931d17..17bc373e`:** the commits after the fix (`0b6e699`, `304e8a2`,
  the CREDHEALTH merge `17bc373`) do not touch `api_model_tournament_image`,
  `tournament_image_refusal`, `api_audit`, `security.py` or `core/artifacts.py`. They add one
  route, which is under `/api/cc/`. The sweep test passes on the head. Nothing reopens B1.

## Findings

### M1 (MEDIUM): a resumed experiment run can resend a paid render while the interrupted attempt's billing is unknown

- **Where.** `experiments/controlled.py:484-509` (resume loop) together with
  `gateway/paid_calls.py:328-330`. The guard keys a call by
  `job:<id>:<request fp>:<occurrence>`, where the occurrence counts identical requests
  **within this execution**. The original execution's attempt 1 is occurrence 0 and attempt 2
  is occurrence 1. The resumed execution starts at `attempt = resume["attempts"]` (2), but its
  first `images.generate` is occurrence **0**, which is attempt 1's key.
- **Exploit path / failure scenario** (with the committed definition, `max_retries: 1`).
  1. Attempt 1's submit is refused before BFL accepts it (5xx/429/unreachable). This is
     DECLINED and a `TransientError`, so the loop continues.
  2. BFL accepts attempt 2 (it bills on submit), and the worker is lost while polling, for
     example on a deploy. The guard row for occurrence 1 is PENDING (UNCERTAIN in my probe).
  3. The lease is reclaimed and the job runs again (`max_attempts=2`). Occurrence 0 is DECLINED,
     so the guard sends a **new paid render**. Occurrence 1 is never reached, so its
     in-flight call is neither counted as an orphan nor refused.
- **Reproduced** in-process with the candidate's own harness (`test_w4_credhealth._claimed_run`,
  BFL stand-in, no network): the first execution produced posts = 2, with guard rows
  `[DECLINED, UNCERTAIN]`. The resumed execution sent **1 new paid post**, the run completed,
  and the rows became `[OK, UNCERTAIN]`. This contradicts the code comment "it never pays
  twice" and F-339's "no blind restart".
- **Impact.** The run can incur at most one extra 2k FLUX image per occurrence (about CA$0.14
  at the shipped tier). It requires an owner step-up authorization, a transient refusal on
  attempt 1, and a worker loss during attempt 2. The authorization cap held in my probe,
  because attempt 1's unbilled reservation stays counted. However, the gateway's monthly and
  provider ledgers miss the in-flight render when the row is PENDING (no orphan count, no
  incident). This is not a blocker: the amount is small and bounded, and the path is
  owner-initiated. It is a correctness hole in the money path that this change claims to
  close.
- **Fix (small).** On resume with `attempts > 0`, decide from the guard's own records rather
  than the attempt number. If any `paid_call_records` row for this `job_id` and effect
  `image.render` has outcome PENDING or UNCERTAIN, settle the run as failed, billing unknown
  (count a PENDING row once through `paid_calls._count_orphan`, as the guard does), and send
  nothing. Only if every earlier row is DECLINED or OK should the loop proceed. Equivalently,
  pre-advance the scope's occurrence counter for this fingerprint to `attempts - 1` so the
  resumed attempt maps to its own key. The records check is clearer. Add a test with
  attempt 1 DECLINED and attempt 2 in flight, and assert no new post. Also, the resumed
  `attempt_log` starts empty because `attempt_log` is only persisted at the end (`resume["log"]`
  is `[]`), so persist it per attempt (I11).

### INFO

- **I7. `_shorten_digests` gaps** (`app/main.py:4962-4974`): the `artifact` and `actor`
  columns are not shortened, and a 64-hex run adjacent to another hex character (`blob<sha>`,
  two concatenated digests) is not matched. This does not matter for B1 now that the byte
  route is an allowlist. For hardening, apply the shortener to `artifact` too and drop the
  look-arounds (shorten any 64-hex window).
- **I8. Owner-view fingerprint is an unsalted `sha256(key)[:12]`** (`gateway/credentials.py:77-82`).
  It cannot be reversed. However, it is not domain-separated as the brief asks, and it lets
  someone with a candidate key confirm it offline with one hash; the same digest also appears
  in other tools that hash keys. Use `sha256(b"brambleloop-key-fingerprint:" + key)`, or an
  HMAC keyed by a server secret. It is shown only to the owner session (no step-up). That is
  acceptable for a non-secret, but consider requiring step-up if the fingerprint is kept
  unsalted.
- **I9. The public `/api/audit` shows `provider.credential_health` rows**: status, HTTP
  status, the redacted provider message, the 4-hex marker and the **BFL credit balance**. No
  key or fingerprint. This is business-state disclosure only. Consider dropping `credits` /
  `credits_usd` from the stored detail or the public view, or gating `/api/audit` (B1 fix
  part 2's stronger option).
- **I10. Sweep test limits**: it fills only path parameters, not query parameters, and checks
  bytes, not digests. It is sound for B1's class today. Extend it if a byte-serving route ever
  takes a query identifier.
- **I11.** The resumed experiment's `attempt_log` loses the earlier attempts (see M1). The
  on-demand 60 s floor is not atomic (free checks only). `candidate_gates` and `release_gates`
  still call the fail-open `is_experiment_image`, and the `disclosed_listing` export checks
  only the product. The Etsy upload choke point is now fail-closed, which is sufficient.
- The new BFL `/v1/credits` call uses `urllib` with `x-key` on a fixed `https://api.bfl.ai`
  URL. A redirect would forward the header, so this is the same class as I1, with no
  provider-controlled URL.

## Status of earlier findings (review of 7f6dbe8)

| ID | Status | Evidence |
|---|---|---|
| B1 | **FIXED** | Allowlist + magic-number check + `private` cache on the byte route; digests shortened in public `/api/audit`; sweep fails on `263e94da`, passes on `17bc373e`; my bypass probes all 404 |
| L1 | **FIXED** | `images_restart` requires step-up |
| L2 | **FIXED** | `_price_cad` = gateway `render_estimate_usd`, never below the table |
| L3 | **FIXED** | per-frame check in `certified_images`; image check fails closed |
| L4 | **FIXED** (window narrowed to the delete transaction, consequence unchanged) | prune re-plans and intersects |
| I1 | OPEN (unchanged) | `gateway/images.py` polling/delivery URL not host-checked |
| I2 | OPEN (unchanged) | self-declared `laura_present` |
| I3 | OPEN (unchanged) | tautological release comparison |
| I4 | BY DESIGN | owner step-up + caps gate the experiment |
| I5 | OPEN (unchanged) | candidates/experiment images unpruned, bounded by spend |
| I6 | OPEN (unchanged) | `/owner-images` reads the body before the size check |

## Method

1. Read the previous review, then the full scoped diff `7f6dbe89..17bc373e`. Read by hand in
   full: the B1 code in `app/main.py`, `gateway/credentials.py`, the `controlled.run_job`
   resume path, `paid_calls.guarded` / `_replay`, `images._guarded_render`, the
   `anthropic._send` / `_classify_failure` path, `on_demand.run_check`, and the new route and
   handler wiring.
2. Enumerated every `ArtifactStore().get`, `FileResponse` and `application/pdf` response in
   `src/` and checked each route's gate (`/api/cc` owner session, `OPERATOR_GET_ROUTES`, or
   public). Checked every writer of the `model.tournament` / `model.reference_pack` audit
   actions.
3. Ran focused tests in a venv installed with `--no-deps --require-hashes` from the candidate
   lock, plus `httpx` (Python 3.13):
   - `test_w4_integ4_deliverable_routes.py`: 4/4 passed on `17bc373e`; **2/4 failed on
     `263e94da`** (the same file copied into a scratch worktree), both on the tournament route.
   - `test_w4_integ4_secfixes.py`: 10/10 passed.
   - `test_w4_credhealth.py`: 13 passed, 0 failed.
4. Two in-process probes (scratch SQLite, sockets disabled, not committed): the B1 bypass
   table above and the `_shorten_digests` cases; and the M1 resume reproduction.
5. No request to production, no deploy, no spend, no credential read or printed.

## Verified safe

- B1 closed: the public digest route serves only reference-pack rows and package-named,
  unkept images, and only bytes with an image magic number. Every other byte route is owner- or
  operator-gated.
- L1-L4 fixes hold. Fail-closed L3 refuses only on a real database error, which is correct.
- `/api/cc/credentials` is owner-only. The on-demand check needs session, CSRF, nonce,
  timestamp and step-up, and is rate-limited. There is no public credential endpoint.
- No key value in responses, logs, audit rows, job rows, notifications or owner cards. Provider
  echoes are redacted. The stored marker is domain-separated and 4 hex.
- Both health checks are free documented reads with no retry loop, a daily cadence and a 60 s
  on-demand floor.
- The CLOSE5 timeout leaves the paid-call guard unchanged. A timeout is UNCERTAIN and never
  resent, and the run is time-bounded under the handler cap.
- An experiment resume with the image already stored, or with only the first attempt in flight,
  never pays twice (M1 covers the second-attempt case).

## Verdict

**NO BLOCKER.** B1 is closed and the closure does not depend on keeping digests secret. Fix
M1 before the controlled experiment is run with `max_retries >= 1` on a worker that can be
redeployed mid-run. Alternatively, set the experiment job back to `max_attempts=1` until the
fix lands, which restores the 7f6dbe8 behaviour (dead-letter, settled by `settle_dead`). The
INFO items can follow.
