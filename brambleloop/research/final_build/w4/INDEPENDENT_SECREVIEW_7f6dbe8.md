# Independent security review: release candidate 7f6dbe8

**VERDICT: (in progress; written incrementally)**

Reviewer: W-SECREVIEW4, an independent reviewer who did not write any of the code reviewed.
Date: 2026-10-20 (UTC). The review was read-only. Nothing was deployed, no request was sent to
production and nothing was spent.

## Scope

- Production: `b931d17a738d6a5bcd96580f620069b669ca5f57`
- Candidate: `7f6dbe89` (branch `claude/w4-INTEG4`, "INTEG4: merge w4-VISNEXT @ 0beb522")
- Diff reviewed: `git diff b931d17 7f6dbe89 -- brambleloop/src brambleloop/requirements.lock
  brambleloop/requirements.txt brambleloop/Dockerfile ops` (73 files, +12,768/−194).
- `requirements.lock`, `requirements.txt`, `Dockerfile` and `ops/` have **no changes** in the
  range. `brambleloop/src/brambleloop/ops/retention.py` (inside `src`) has a 4-line change.

## Focus area 1: the owner-only controlled experiment command

Files: `experiments/controlled.py`, `app/command_center/api.py:550-640` (lines below are in
the candidate), `experiments/definitions/exp-2026-10-20-wrap-7ref/`, `runtime/release.py`
`handle_controlled_experiment`, `visual/experiment.py`.

### (a) Owner auth and step-up: SAFE

- All five routes sit under `/api/cc/`, so `security.operator_gate` → `auth.gate`
  (`auth.py:740-769`) runs first: a live owner session cookie is required (401 otherwise),
  and every POST also needs same-origin, the HMAC CSRF token, a fresh nonce (unique per
  session, `RequestNonce` insert → 409 `REPLAY`) and a timestamp within the skew window.
  The ops bearer token is not accepted on `/api/cc/*` (the test proves 401/403).
- `authorize` and `run` call `auth.require_stepup` (`auth.py:772-778`), which refuses when
  `stepup_until` is missing or `<= now`. The value is read from the session row at gate time,
  so an expired step-up cannot be "replayed": there is no step-up token, only a server-side
  window that a nonce-protected, passphrase-checked POST to `/auth/step-up` opens.
  `controlled.authorize`/`submit` also refuse `stepped_up=False` in code, so a future
  non-HTTP caller cannot skip it by accident.
- Note (INFO, pre-existing): `create_session` opens the step-up window at login
  (`auth.py:372`), so the first 5 minutes after a passphrase login count as stepped-up. This is
  equivalent strength (the login is the same passphrase check) and is not new.

### (b) Spend caps bound to the authorization: SAFE, one LOW

- The run request body is read and ignored (`api.py` `experiments_run`: `await
  body_of(request)` only). Caps come solely from the `ExperimentAuthorization` row.
- `authorize` refuses `gen` outside `(0, definition cap]` and `vis` outside `[0, definition
  cap]` (`controlled.py:227-234`). NaN: `float("nan")` fails `0 < nan`, so it is refused;
  `inf` fails `<= cap`. The definition's caps are in the committed, sha-bound file.
- Binding: the row stores `definition_id` and the definition file's sha256. `submit` looks
  the authorization up by **both** (`authorization(db, id, sha)`), and `run_job` re-loads the
  definition, requires `sha == inputs.definition_sha256`, and requires the live authorization
  for that sha to be the **same** `auth_id` the run was created under
  (`controlled.py:429-433`). An authorization for one definition or fingerprint cannot fund
  another, and re-authorizing revokes the previous one (a queued run under it then refuses).
- Enforced before the provider call: `gen_spent(auth) + price > cap` stops the attempt
  (`:450-455`), then the price is reserved on the run row before `images.generate`, which
  itself reserves against the agent, monthly and provider ceilings before anything leaves
  (`gateway/images.py` `reserve_render`). A failed call stays billed at its reservation
  unless it was refused before sending.
- Concurrency: only one run per definition sha can be active (`submit` returns the live run),
  and two racing submits compute the same `n` and therefore the same `idempotency_key`, which
  is `unique` on `controlled_experiment_runs` and on the job queue: the loser gets an
  IntegrityError (500), never a second paid run. The job is enqueued with `max_attempts=1`,
  and a reclaimed lease with no attempts left is dead-lettered (`queue/durable.py:420-423`),
  so a worker death cannot re-run a paid generation.
- **L2 (LOW)** below: the in-code price is the table price for FLUX.2 while the gateway now
  reserves the higher megapixel formula; see findings.

### (c) Idempotency: SAFE

Repeated POSTs while a run is queued/running return `{"duplicate": true}` with the same
job id (test `test_full_run_through_the_routes…`). After a run reaches a terminal state, a new
POST is a **new** paid run under `n+1`; that is the designed behaviour and it is still bounded
by the cumulative per-authorization cap (`_spent` sums every run under the `auth_id`). The
`run_job` status check `queued → running` is a read-then-write rather than a compare-and-set
(INFO), but only one job exists per run and it cannot be re-delivered (above).

### (d) Drift refusal: SAFE

The definition's sha256 covers the ordered reference hashes, the prompt hash, the model,
size, retries and caps. Editing `definition.json` changes its sha, so there is no
authorization for it (`submit` refuses) and a queued run refuses in `run_job`
(`:429-430`). Editing `prompt.txt` or any `refs/*` file is caught by `verify()` (sha256 of
every reference in position order, plus the prompt), which runs at authorize time and again
in the job before any spend (`:434-436`). Canonical Laura frames are resolved through
`canonical.reference_file`, which itself returns `""` unless the committed bytes match the
pack's recorded hash. `test_fingerprint_and_prompt_drift_are_refused_before_any_spend`
passes. (INFO: `verify()` joins `definition_dir / file` and only rejects `..`; an absolute
path in a committed definition would be read from anywhere. Definitions are committed
code, not request input, so this is hardening only: reject absolute paths too.)

### (e) Key-leak proof: SAFE; the test is not vacuous

- The key is read by `gateway.images.key_for` at call time and placed only in the `x-key`
  request header. It never enters job inputs (`{definition_id, definition_sha256, run_id,
  auth_id}`), and every stored string goes through `_scrub`, which drops dict keys named
  `api_key`/`authorization`/`x-key`/`headers` and replaces any environment value whose name
  contains KEY/SECRET/TOKEN/PASSWORD/PASSPHRASE.
- `tests/test_w4_controlled_experiments.py::test_full_run_through_the_routes_and_the_worker_and_no_key_anywhere`
  sets a random stand-in key, **asserts the key was actually sent** in the mocked FLUX
  request headers (so the hunt is not vacuous), then searches the card JSON, the board JSON,
  the captured root logger at DEBUG, every `Job.inputs/outputs/error`, every `AuditLog.detail`
  and every run row. I ran it: 10 passed, 0 failed.
- Gaps in the proof (INFO): it does not scan `durable_artifacts`, the spend/cost tables, the
  HTTP response headers, or the image bytes. By construction none of them receives the key
  (the receipt is built from the provider's response body; the image is the provider's
  bytes), so this is a coverage note, not a leak.

### (f) Experiment outputs never publish: SAFE in depth, one LOW

Guards found: `visual.experiment.refuse_if_experiment` (product-level, for the uncertified
product the definition names, via the `experiment.controlled_opened` audit row written at
submit) is called first in `etsy_ops` Etsy payload (`:376`) and listing image upload
(`:554`), `pipeline` (`:1579`), `activation_authority` (`:72`), `publication_authority`
(`:403`), `disclosed_listing` export (`:514`), `gallery_persist.persist_approved` and
`image_production.approve`. The image-level guard `is_experiment_image` /
`refuse_if_experiment_image` is in `gallery_persist.write_frames` (`:109-113`),
`candidate_gates.publication_verdict` (`:583-587`, so owner uploads of the same bytes are
blocked too), `release_gates.generated_frame_verdict` (`:81-86`) and
`image_production.approve`. A path from an experiment image to a `ListingAsset` row would
have to pass `write_frames`, which refuses it. See **L3** for the one exporter that does not
re-check per image, and **M1** for the unauthenticated digest route that can serve the bytes.

### (g) Path traversal and the image route: SAFE

`definition_id` is a path segment (Starlette's `str` convertor cannot contain `/`), truncated
to 80 chars, and `load()` refuses `/`, `..` and anything without a `definition.json`;
`load()` also requires the JSON `id` to equal the folder name. `run_id` is an `int` path
parameter. The image route serves only `ArtifactStore().get(run.image_sha256)`, whose sha
comes from the run row, with `Content-Type: image/png`, `Cache-Control: no-store`, the
app-wide `X-Content-Type-Options: nosniff` and CSP, behind the owner session.

## Focus area 3: the F-852 amendment gate

Files: `publish/eligibility.py:407-508`, `visual/candidate_gates.py:504-588`,
`publish/release_gates.py:68-158`.

- **UNKNOWN never counts as PASS.** `verified_exception` requires
  `str(checks.get(name) or "UNKNOWN").upper() == "PASS"` for every name in
  `EXCEPTION_CHECKS` (+ the three Laura checks when Laura is present). Missing, None, dict
  values, `UNKNOWN`, `NOT_APPLICABLE` all block. No evidence at all → the original F-852
  refusal. Provenance needs all six fields non-empty and every reference to carry a sha256.
- **COMPOSITING_FEASIBLE**: DETAIL, SCALE and COLOUR_CONTEXT are feasible → the exception is
  closed for them (F-853). Only LIFESTYLE and ANGLE remain eligible; HERO, PROOF, FIT and
  `PHYSICAL_PROOF` purposes are always refused.
- **Today the route is shut.** `candidate_gates.ETSY_POLICY_STATUS = UNKNOWN` (`:490`) and
  `etsy_policy` is a required check, so no generated frame can satisfy the exception in this
  build (`test_the_production_path_still_refuses_today_on_the_etsy_reading` passes).
- **Caller-supplied evidence.** `may_export(generated_evidence=…)` is called with evidence
  from exactly two places, both of which build it from recorded checks:
  `candidate_gates.exception_evidence` (from the checks this module just ran) and
  `release_gates.generated_frame_verdict` (from the stored `ImageCandidate.checks` row, only
  when that row's sha equals the frame's sha). No HTTP route accepts evidence. The owner
  upload route (`/api/cc/owner-images`) supplies provenance fields (model, prompt, references,
  `laura_present`), not check results; the checks are computed on the bytes. See **I2** for
  the self-supplied `laura_present` flag and **I3** for a tautological release check.
- `test_w4_f852_amend.py`: 8 passed, 0 failed.

## Focus area 4: the webhook limit (CLOSE5 R1): **R1 is FIXED**

`app/main.py:2967-2989` now runs `refuse` and `receive` through `etsy_webhooks.GATE.run`
(`integrations/etsy_webhooks.py:425-490`):

- Admission is a non-blocking `threading.BoundedSemaphore(4).acquire(blocking=False)` taken
  **after** the capped async body read, so a slow client cannot hold a slot.
- Admitted work runs on `anyio.to_thread.run_sync(..., limiter=<private CapacityLimiter(4)>)`,
  never AnyIO's shared default limiter (40 tokens) that every sync route uses. At most 4
  webhook DB calls are in flight per worker, so a refusal flood can hold at most 4 threads
  and 4 DB connections of the 15 (5 + 10 overflow) per worker.
- Saturated → `busy()` returns a static 503 + `Retry-After: 5` with no thread, no DB work and
  no request data. Etsy retries 5xx, so a shed genuine delivery is not lost.
- `leave()` runs in `finally`; `to_thread.run_sync` does not abandon the thread on cancel by
  default, so a client disconnect cannot free the slot while the thread is still using its
  connection. The per-loop limiter map is cleared above 8 loops (tests only).
- `test_w4_close5_r1.py`: PASS, 0 failing (includes "answers 503 with no db work when
  saturated, then recovers").

Residual (INFO): the gate is per process, so total webhook concurrency is 4 × workers; an
attacker can still keep the endpoint answering 503 to Etsy during a flood (availability of
the wake signal only; orders come from the authenticated receipt read). That is the accepted
shape and the right trade.
