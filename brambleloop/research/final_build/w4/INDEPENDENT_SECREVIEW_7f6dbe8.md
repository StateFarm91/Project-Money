# Independent security review: release candidate 7f6dbe8

**VERDICT: BLOCKER** (one finding, B1: every certified paid pattern PDF becomes permanently
downloadable without authentication. The fix is small; see B1.)

Findings: **B1 BLOCKER**, **L1-L4 LOW**, **I1-I6 INFO**. The previous review's **R1 is FIXED**.

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

## Focus area 2: durable artifacts and retention

Files: `commerce/deliverables.py`, `core/artifacts.py` (`_keep` / `_recover`, unchanged in the
range but newly fed), `runtime/release.py:339-346`, `:477-478`, `:4019-4036`,
`ops/retention.py`.

- **Re-render fallback: SAFE.** `resolve_pdf` serves disk → Postgres → re-render, and the
  re-render is accepted only when `sha256(rendered) == certified hash`. Anything else raises
  `DeliveryRefused`; no other file is substituted. `ArtifactStore.get` re-hashes disk bytes,
  and `_recover` re-hashes Postgres bytes, so a corrupt row is never served.
- **Prune cannot delete a protected release's bytes (by plan): SAFE.** `retention_plan`
  protects every non-withdrawn listing, every sold release (an `Order` with no version
  protects every version of the product), the newest 2 other releases per product, every
  hash in a delivery audit row, and every row not kept by this module (`why_kept` prefix).
  The protected set is computed from all protected releases' hashes, so a hash shared with a
  protected release is safe whatever its `why_kept` says. Any exception in planning prunes
  nothing. `test_w4_firstsale_retention.py`: 6/6 passed.
- **Race: L4** below (plan and delete are separate transactions).
- **Customer download links.** There is no customer-facing download route in this build:
  `delivery_links` produces internal `deliverable:<slug>@<version>/<t>` references resolved
  by `resolve_pdf`, and fulfilment is Etsy's digital-file delivery. Every buyer of a release
  receives the same file, so "another customer's file" does not arise. **However, an
  unauthenticated route already serves any stored artifact by sha256, and this candidate
  makes the paid PDFs permanently available to it: B1.**
- **Growth.** `durable_artifacts` gains: every certified PDF and frame per build (pruned by
  `prune`), every image-production candidate (`image_production.py:271`, never pruned) and
  every experiment image (`controlled.py:490`, never pruned). Both unpruned sets are bounded
  by spend ceilings (a few MB per paid image), so this is INFO (I5), not a DoS.
- `ops/retention.py`: one new `KNOWN_READ_ACTIONS` entry (`creative.grid_panel`, windowed).
  No security impact.
- `test_w4_firstsale_deliverables.py`: 6/6 passed.

## Focus area 5: new endpoints and new tables

New routes (all under `/api/cc/`, so owner session for GET; session + same-origin + CSRF +
nonce + timestamp for POST, from `auth.gate`):

| Route | Step-up | Assessment |
|---|---|---|
| GET `/first-sale`, `/images`, `/images/plans`, `/images/{listing}`, `/images/runs/card`, `/wardrobe`, `/experiments`, `/experiments/runs/{id}/card` | n/a | read-only; `{listing}` checked against `LAUNCH0_SLUGS`; `run_key` truncated to 300 |
| GET `/images/candidates/{id}/image`, `/experiments/runs/{id}/image` | n/a | int id → sha from DB row → `ArtifactStore.get`; nosniff; `no-store` |
| POST `/owner-images` | no | owner fallback upload; 25 MB cap checked after `request.json()` reads the whole body (I6); all gates run on the bytes |
| POST `/images/outfits`, `/images/outfits/action` | no | wardrobe edits; `set_reference` only accepts a stored candidate of this outfit whose outfit check PASSed, never a canonical identity frame |
| POST `/images/runs/approve` | **yes** | publication decision; re-checks every gate and `refuse_if_experiment(_image)` |
| POST `/images/runs/visual-approval` | no | recorded only; no gate reads it |
| POST `/images/runs/restart` | no | see L1 |
| POST `/experiments/{id}/authorize`, `/experiments/{id}/run` | **yes** | see focus area 1 |

New tables: `experiment_authorizations`, `controlled_experiment_runs` (`experiments/controlled.py`),
`laura_outfits`, `image_production_runs`, `image_candidates` (`visual/image_records.py`). All
five are created additively at boot: `core/db.py` `Database.create_all` now imports
`visual.image_records` and `experiments.controlled` before `Base.metadata.create_all`, and
each module also has a lazy `ensure_tables` with `checkfirst=True`. None drops or alters an
existing table. None holds a credential or customer data: they hold hashes, caps, prompts,
outfit descriptions, verdicts and the owner's `owner:cc:<public_id>` actor string. Growth is
one row per authorization, run or candidate, all bounded by spend.

## Focus area 6: new outbound calls

- **`gateway/images.py` (FLUX 3, FLUX.2 multi-reference).** Every reference is inlined from a
  **local file** (`_inline_reference` never fetches), so a reference cannot be turned into
  SSRF. More references than the documented limit are refused, not truncated. Grounding
  (model web search) is forced off. The per-call price (`render_estimate_usd`, never below the
  table price; an unreadable input is refused) is reserved **before** `_post`
  (`reserve_render`, agent + monthly + provider ceilings). TLS: `urllib.request.urlopen` with
  the default verified context; no `verify=False`, `CERT_NONE` or unverified context
  anywhere in the diff.
- **Provider-supplied URLs (L3-adjacent, pre-existing, now also used for FLUX 3): I1.** The
  `polling_url` from BFL's answer is polled **with the `x-key` header**, and the delivery URL
  is fetched, with no scheme or host check.
- **`creative/flux3_generator.py`** goes through `image_stages` → `gateway.images.generate`
  (same reservation); it adds no transport of its own.
- **`visual/vision_judges.py`** adds no transport: every read goes through the judge passed
  in, which in production is `fidelity.GatewayVisionJudge` (gated on `image_vision`,
  `gw.check_budget` before `provider.see`, reservation released with the actual cost), and in
  the experiment additionally `CappedVision` (refuses a call whose padded estimate exceeds the
  remaining vision cap).
- The experiment's generation call does not consult the `image_generation` capability gate;
  the step-up owner authorization with its caps is that gate by design (I4).

## Findings

### B1 (BLOCKER): paid pattern PDFs are downloadable without authentication, now permanently

- **Where.** `app/main.py:2151-2178` `GET /api/model-tournament/image/{sha256}` (public: GETs
  are open unless listed in `security.OPERATOR_GET_ROUTES`) returns
  `ArtifactStore().get(sha256, db=db)` for **any** digest, whatever the bytes are, with
  `Cache-Control: public, max-age=86400`. `app/main.py:4879-4894` `GET /api/audit` (also
  public) returns up to 1000 `AuditLog` rows with their full `detail`; the `assets.built` rows
  carry `pdf.sha256` and `pdfs.{US,UK}.sha256` (`runtime/release.py:397-406`). New in this
  range: `runtime/release.py:343-346` keeps every certified PDF in `durable_artifacts`, and
  `ArtifactStore.get(..., db=db)` recovers it from Postgres and writes it back to disk.
- **Exploit path.** `GET /api/audit?action=assets.built` → read `detail.pdfs.US.sha256` →
  `GET /api/model-tournament/image/<sha>` → the certified paid pattern PDF (labelled
  `image/png`). Reproduced locally on scratch SQLite with no network
  (`scratchpad probe`, not committed): after deleting the artifact directory to simulate a
  redeploy, `/api/audit` → 200 with the hash, and the image route → 200, `public,
  max-age=86400`, **bytes identical to the PDF**. The same path serves EXPERIMENT images (the
  `experiment.controlled_run` audit row carries `image_sha256`) and image-production
  candidates to anyone.
- **Why it blocks this candidate.** In production `b931d17` the two routes already exist, but
  the PDFs live only on the ephemeral disk, and the 2026-10-20 rehearsal found them "not on
  disk", so the leak is effectively closed today. This candidate exists to make those files
  durable for the first sale; deployed as is, every certified pattern, the product being sold,
  becomes a permanent free download. CLAUDE.md treats the patterns as the product, and there
  are 0 live listings, so fixing it now costs nothing.
- **Fix (small; either part closes the path, do both).**
  1. Restrict the tournament route to what it exists for. Serve a digest only when it is
     named by the tournament package or the canonical pack, or at minimum when its
     `DurableArtifact.why_kept` does **not** start with `deliverables.KEEP_PREFIX` or the
     EXPERIMENT label. Also refuse bytes that are not PNG/JPEG/WebP by magic number (never
     `%PDF`), and drop `public` caching for anything kept.
  2. Add `/api/audit` to `OPERATOR_GET_ROUTES`, or strip `detail` from the public view. It is
     a raw dump of every audit row, so other hashes and internal state leak the same way.
  Add a test: a kept PDF's sha is 404 on `/api/model-tournament/image/{sha}`, and
  `/api/audit` without the operator credential is 401 (or carries no `detail`).

### L1 (LOW): `/api/cc/images/runs/restart` can resume paid generation without step-up

`api.py` `images_restart` → `image_production.restart`. It needs the owner session, CSRF and
a nonce, but not step-up. A restart re-enqueues a blocked run, and its next stage can call
the paid generator. The spend stays bounded: attempts, calls and spend carry over, the
per-role cap and gallery spend plan bind, `MAX_RESTARTS` caps it, budget stops are final,
and the run needs the `image_generation` gate. So this is consistency, not a hole. **Fix:**
add `auth.require_stepup(db, request, "images.restart")`, matching authorize, run and approve.

### L2 (LOW): the experiment's in-code cap uses the table price for FLUX.2, below what the gateway reserves

`controlled.py:382-387` `_price_cad` prices `flux-2-pro` at `cad_per_image` (table), while
`gateway.images` now reserves and bills `render_estimate_usd` (the megapixel formula plus
input MP, "which is higher"). The check `gen_spent + price <= cap` can therefore admit an
attempt whose billed cost takes cumulative spend past the authorization cap, by the
difference. The committed definition uses `flux-3-image` at 2048² (tier 2k), where both
agree, so the shipped definition is unaffected. **Fix:** compute the price with
`images.render_estimate_usd(BY_KEY[model], size, refs)` (the same function the gateway
reserves with), and pass the remaining cap as a hard ceiling.

### L3 (LOW, defence in depth): the Etsy image exporter does not re-check per image

`runtime/etsy_ops.py:554-556` (`certified_images`, "the one upload path") calls only the
product-level `refuse_if_experiment(slug, version)`. For a **certified** product, an
experiment image is stopped only upstream (`gallery_persist.write_frames`,
`candidate_gates`, `release_gates`). `is_experiment_image` also fails open (returns False)
when the run table is unreadable (`visual/experiment.py:450-464`). **Fix:** call
`refuse_if_experiment_image(db, [f["sha256"] for f in cert["frames"]], action="listing image
upload")` there and in `disclosed_listing` export, and make the image check fail closed on
publication paths.

### L4 (LOW): retention plan and delete are not atomic

`deliverables.prune` computes `retention_plan` in one set of sessions, then deletes in
another, and re-checks only `why_kept`, not protection (despite the docstring's
"re-checking each hash at delete time"). An `assets.build` or new listing committed in
between can see the row as already held (`_keep` returns True on an existing digest) and then
lose it. Consequence: `durable_state` reads FAIL and the next `secure_release` re-keeps it
from disk or a byte-identical re-render, so a buyer is never served a wrong file, but the
restart guarantee is briefly lost. **Fix:** recompute `_release_hashes` for the row's
releases inside the delete transaction, or take the heartbeat lease around prune and the
asset build.

### INFO

- **I1 (pre-existing, extended to FLUX 3).** `gateway/images.py:1182-1186` polls the
  provider-returned `polling_url` with the `x-key` header, and `:1231` fetches the delivery
  URL, with no scheme or host allowlist. urllib also forwards the header across redirects,
  and accepts `file://` and `http://`. Exploitation needs a compromised or spoofed BFL
  answer over verified TLS. **Fix:** require `https` and a host under `bfl.ai` (and the
  documented delivery hosts) before sending the key, and use an opener that strips `x-key`
  on redirect.
- **I2.** `laura_present` on `/api/cc/owner-images` is self-declared by the uploader. False
  skips Laura's identity, body and outfit checks and the Laura publication gate for that
  candidate. Owner-only, and F-852 still needs every other PASS (and Etsy policy is UNKNOWN
  today). Consider detecting a person independently before trusting `False`.
- **I3.** `verified_exception`'s release check compares `fidelity_release` with
  `provenance.release`, but `exception_evidence` fills both from the same
  `binding.release_hash`, so the check is tautological. `release_gates.generated_frame_verdict`
  also does not compare the stored candidate's slug/version/release with the release being
  exported. That is unreachable today, because `write_frames` takes candidates from the run
  of the same slug. **Fix:** bind the candidate's `release` to the certified release hash of
  the slug@version under evaluation.
- **I4.** The experiment's generation bypasses the `image_generation` capability gate by
  design (owner step-up plus caps is the gate). Every gateway ceiling still applies.
- **I5.** Image-production candidates and experiment images are kept in `durable_artifacts`
  with no retention. The growth is bounded by spend.
- **I6.** `/api/cc/owner-images` reads the whole JSON body (`request.json()`) before the
  25 MB check. Owner-only behind CSRF. Consider a Content-Length cap like the webhook's.
- Also noted in focus area 1: `verify()` should reject absolute reference/prompt paths;
  `run_job`'s `queued → running` is not a compare-and-set; the key-leak test does not scan
  `durable_artifacts`, spend tables or response headers; login opens the step-up window.

## Method

1. Read the full diff of the scoped paths. Read by hand, in full: `experiments/controlled.py`,
   the new `api.py` routes, `integrations/etsy_webhooks.py` gate, `commerce/deliverables.py`,
   the `eligibility.py` amendment, `candidate_gates.exception_evidence` /
   `publication_verdict`, `release_gates.generated_frame_verdict`, the `gateway/images.py`
   changes, `gallery_persist`, and `image_production.restart` / `restartable`.
2. Read the unchanged code they depend on: `auth.gate`, `require_stepup`, `create_session`,
   `security.operator_gate` / `requires_operator`, `queue/durable.py` claim/reclaim,
   `core/artifacts.py`, `fidelity.GatewayVisionJudge.read`, `outfits.set_approved_reference`,
   `visual/experiment.py` guards.
3. Searched `src/` for every caller of `refuse_if_experiment`, `refuse_if_experiment_image`,
   `is_experiment_image`, `generated_evidence` / `exception_evidence`, and every
   `ArtifactStore().get` / `store.get`. A sub-search mapped the public GET routes that expose
   PDF hashes (found `/api/audit`).
4. Ran focused tests in a venv installed with `--no-deps --require-hashes` from the candidate
   lock, plus `httpx`, on Python 3.13 (the image uses 3.11):
   - `test_w4_controlled_experiments.py`: 10 passed, 0 failed
   - `test_w4_close5_r1.py`: PASS, 0 failing
   - `test_w4_f852_amend.py`: 8 passed, 0 failed
   - `test_w4_firstsale_deliverables.py`: 6/6 passed
   - `test_w4_firstsale_retention.py`: 6/6 passed
5. Reproduced B1 in-process (TestClient, scratch SQLite, sockets disabled): kept a PDF the way
   `assets.build` now does, wrote its `assets.built` audit row, deleted the artifact
   directory, then fetched the hash from `/api/audit` and the bytes from
   `/api/model-tournament/image/{sha}` without credentials. The bytes were identical.

## Verified safe

- Owner session, CSRF, nonce and step-up on experiment authorize/run; no ops-token path.
- Caps come only from the authorization row, capped by the sha-bound definition, and are
  checked in code before the provider call and reserved again by the gateway. An
  authorization cannot fund another definition or fingerprint.
- One active run per definition sha, a unique idempotency key on the run and the job, and
  `max_attempts=1` with dead-lettering on lease expiry: no duplicate paid runs.
- Drift of `definition.json`, `prompt.txt`, the refs or the canonical frames refuses before
  any spend.
- The provider key never reaches stored rows, logs, cards or responses, and the test proves
  it non-vacuously.
- An experiment image never reaches a `ListingAsset`, and an experiment product never passes
  a publication or activation path.
- No path traversal through `definition_id` / `run_id`. The image routes are owner-only, nosniff
  and `no-store`.
- F-852: UNKNOWN never counts as PASS, no route accepts caller-supplied check evidence, and the
  route is closed today because Etsy policy is UNKNOWN.
- The webhook gate (R1 fixed).
- The re-render fallback requires a sha256 match. Retention protects listed, sold, recent and
  delivered releases and fails closed.
- All new tables are created additively at boot. No secrets are stored.
- References are local files only (no SSRF from references), TLS is verified, and every
  outbound generation or vision call is gated and reserved before it is sent.

## Verdict

**BLOCKER**, for B1 alone. Everything this candidate set out to build (the experiment
command, the F-852 amendment, the webhook gate, durable deliverables) is sound on its own
terms. But making certified PDFs durable, while a public digest route serves any stored
artifact and a public audit route publishes the digests, turns a latent leak into a
permanent free download of the product. Apply B1's fix (both parts, with the test), then
this reviewer would expect NO BLOCKER. L1-L4 can ride the same change or follow it.
