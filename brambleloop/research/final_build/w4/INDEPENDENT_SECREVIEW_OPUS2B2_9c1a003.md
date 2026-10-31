# Independent security and integrity review: OPUS2 batch 2 (`opus2/p0-revenue-workforce` @ 9c1a0037)

- Reviewed: 2026-10-31 (UTC)
- Subject: `git diff origin/claude/w4-INTEG8-next...origin/opus2/p0-revenue-workforce` (head
  `9c1a00377b7727d02b44d3757ccdd37181feedbd`), limited to the six parts in the brief.
- Reviewer: independent. This review did not change any code on the subject branch. The only
  thing pushed is this report.
- Method: I read each changed module and every caller of it that matters. I wrote two
  reproduction scripts (`/tmp/repro/r_scan.py` and `/tmp/repro/r_recert.py`; they are inlined
  below so anyone can re-run them). I ran the requested suites one at a time with
  `PYTHONPATH=src:tests nice -n 19`.
- Environment note: the container had no `sqlalchemy` or `fastapi`. A first run with system
  Python failed on import in every suite except `test_opus2_rim_negative` and `test_vacuity`.
  The suites were then run in a venv built from `brambleloop/requirements.lock`.
  `requirements-test.lock` would not install under `--require-hashes`: `h11>=0.16` is not
  pinned. That is a separate tooling defect and does not come from this branch.

## Verdicts

| # | Part | Verdict |
|---|------|---------|
| 1 | Chain successors (`runtime/chain_successors.py` and its wiring) | **ACCEPT** (two LOW follow-ups) |
| 2 | P0-REVERIFY-WITHHOLD | **ACCEPT** (one LOW, one INFO) |
| 3 | Competitor-scan evidence | **CHANGES REQUIRED** (F3.1 MEDIUM) |
| 4 | Commercial lessons | **ACCEPT** (one LOW) |
| 5 | P0-LEARNING-GAPS | **ACCEPT** (two LOW follow-ups) |
| 6 | Authority changes | **ACCEPT**: no authority is widened |

There is no CRITICAL or HIGH finding. Nothing in scope publishes, contacts a customer, spends,
calls the network or a model, or bypasses SHADOW, a gate or an owner action.

---

## Part 1: Chain successors: ACCEPT

**What I checked, and found to hold:**

- **Job storms.** `sweep()` reads at most `SWEEP_LIMIT=200` open incidents.
  - It re-drives a dead end only when the deployed commit differs from the one recorded on it
    (`refused_under_commit` or `redriven_under_commit`).
  - It never re-drives while `build.commit()` is unknown.
  - Every enqueue carries the idempotency key `deadend:<sig>:<commit>`, and `DuplicateJob` is
    swallowed.
  - When a re-driven stage refuses again, `record()` writes the new commit, so the next sweep
    waits.
  - Worst case is one re-drive per open dead end per deploy, at most 200 per deploy. There is
    no timer-driven retry. The tests `test_the_sweep_redrives_once_per_new_commit_and_never_under_an_unknown_one`
    and `test_a_held_launch_is_replanned_the_day_after_the_missed_occasion_once` cover this.
- **Launch re-plans.** `launch_held` enqueues one `launch.plan`. Its idempotency key contains
  the re-plan date, and `run_after` is set to the day after the occasion (or 30 days later
  when there is no occasion date). That is at most one re-plan per release per occasion date.
- **Gates.** Each re-drive re-enqueues the ordinary stage job, under the same agent that the
  registry already permits for it:
  - `pricing.position` runs under `pricing`;
  - `assets.build` runs under `publishing`;
  - `launch.plan` runs under `growth`.

  The stage re-runs its own gates. Nothing is marked passed. The wrappers only append
  `successor` to the stage's output, and a successor exception is captured without changing
  the stage's verdict.
- **Owner actions.** A pricing refusal becomes an `OwnerAction` with `max_cost_cad=0.0`.
  Nothing is approved on the owner's behalf. Incidents are opened with
  `halts_publication=False`. That is correct: they add no new halt, and the refusal itself
  already stops the chain.
- **Nothing outward.** `launch.plan` only enqueues `listing.seo` and the QA stages. No path
  reaches `store.publish` without the normal publish gates.
- **Parity binding.** `handle_store_publish` now writes `version` and `release` into the
  `listing.parity` detail. The only readers are `finance.governor.ADVANCEMENT_ACTIONS` and
  retention, and both read `action` and `artifact` only. Adding keys is backward compatible,
  so readers stay compatible.
- **CADENCES.** Four CA$0 cadences are added:
  - `chain_successors`, hourly;
  - `scan_evidence`, daily;
  - `commercial_lessons`, daily;
  - `knowledge_gaps`, weekly.

  The scheduler walks every cadence on each tick and has no per-tick quota for these to
  exhaust. No existing cadence was changed or removed, so no existing job is starved.

**Findings:**

- **F1.1 (LOW): the pricing owner action is not closed when the dead end clears.** `sweep()`
  resolves the incident once `pricing.position` succeeds for the release. It does not mark
  the owner action `chain-deadend:pricing:<slug>@<version>` done. After a fix deploy that
  makes a price clear, the owner still sees "Decide the price for …" for a product that
  already has a price.
  - Repro: call `pricing_refused(...)` with a net-floor decision. Insert a `DONE`
    `pricing.position` job with `price_cad` set for the same slug, version and release. Run
    `sweep()`. The incident is resolved; the `OwnerAction` still has `done=False`.
  - Fix: in the resolve branch, set `done=True` on the matching `OWNER_KEY` row, with a
    resolution note.
- **F1.2 (LOW): the parity row's version is not defaulted the way the verdict's is.** The
  row writes `version=ctx.job.inputs.get("version")`, which is `None` when absent.
  `_listing_parity` judges `inputs.get("version", "1.0.0")`. A job without `version` is
  therefore recorded as `version: null` while it was judged as 1.0.0. No current reader is
  affected.
  - Fix: use the same default, or have `_listing_parity` return the version it judged.

## Part 2: P0-REVERIFY-WITHHOLD (26e426ee): ACCEPT

**What I checked, and found to hold:**

- **Durable record.** `quality_ops._run_check` calls
  `withholding.record_reverification(check=..., problem=...)` on every definite reading.
  - Failures are kept per check in `PatternVersion.certificate["reverify_failed"]`, and the
    `quality_reverify` kind is set while any check fails.
  - That record lives on the stored release, which retention does not prune.
- **Publish gates read it.**
  - `release_gates.for_publish` appends `release withheld (re-verification): …`.
  - `publication_authority.evidence` reads `held["withheld"]`, which is true for any kind, so
    certification shows `FAIL`.
- **Pruning does not reopen it.** `test_pruning_the_audit_row_does_not_reopen_publication`
  deletes every `quality.reverified` row and shows that the gate still blocks.
- **Fails closed.**
  - An UNKNOWN reading (`ok is None`) neither sets nor clears the record.
  - A check that raises becomes a failure.
  - `reconcile()` does not touch `quality_reverify`.
  - Clearing needs the same check to pass, and one check passing does not clear another's
    failure.
- **Scope.** Publication only; not in `BUILD_BLOCKING`, so a fixed version can still be built.

**Findings:**

- **F2.1 (LOW): re-certifying the same version under a new release hash drops the withhold
  until the next daily re-verification.** `runtime/pipeline.py` (around line 1463) replaces
  `existing.certificate` outright when a version is re-certified with a different release
  hash. That replacement discards `withholding_reasons`, `withheld` and `reverify_failed`.
  - Until `gate.quality` runs again, publication for that version is not withheld for the
    earlier re-verification failure.
  - The exposure is small: re-certification itself re-runs the certification gates on the
    new content.
  - The same replacement already drops the pre-existing `teardown_qa` and `owner_veto`
    kinds. `owner_veto` is re-read on every `current()` call, but `teardown_qa` is not
    restored the same way. This behaviour predates the branch.
  - Repro (`/tmp/repro/r_recert.py`, run against this head):
    ```
    cir = D._cir(); db = D._db(cir)            # tests/test_w4_departments fixture
    QO.reverify = lambda *a, **k: {"check": a[1], "ok": False, "problems": ["SIM drift"]}
    D._run(db, "validator", "cir.twin", {"slug": cir.slug, "version": cir.version})
    # -> W.reasons(...)["blocks_publish"] == True
    # emulate pipeline re-certification: new release_hash, certificate replaced
    # -> W.reasons(...)["blocks_publish"] == False;
    #    for_publish reasons contain no "re-verification"
    ```
    Observed output: `before: True`, `after recert: False`,
    `reverify reason present: False`.
  - Fix (owner of `pipeline.py`'s re-certification path): carry `withholding.RECORD`,
    `SUMMARY` and `REVERIFY_FAILED` forward across re-certification. Alternatively, enqueue
    the four re-verification checks right after `gate.recertified`.
- **F2.2 (INFO): two texts still say nothing is blocked.**
  - The incident note in `quality_ops._incident` still reads "the certificate is unchanged
    and nothing was blocked".
  - The output still says `certificate_changed: False`.

  Both are now inaccurate, because publication is withheld and a `reverify_failed` field is
  written into the certificate dict. Only the wording is wrong, not the behaviour.

## Part 3: Competitor-scan evidence: CHANGES REQUIRED

**What I checked, and found to hold:**

- The module is read-only and has no network access. `METHOD` names the Etsy Open API v3
  public endpoints. No scraper is added.
- Timestamps come only from stored rows (`Benchmark.last_scan_at`, job `created_at` and
  `finished_at`, and watchlist memory). Nothing is invented. An absent value is `None`, and
  an unregistered shop has every time `None`.
- `BenchmarkListing` contributes only counts and min/max dates. The reference listings expose
  only an id, the owner's own name for the listing, a URL built from that id, the dates and
  `pod`. No competitor title, description, chart or photo is copied.
- The reading writes one row per UTC day into `operating_readings`.

**Finding:**

- **F3.1 (MEDIUM): a shop that once scanned and has failed ever since is reported as
  "scanned", with its failure hidden.**
  - `_watched` derives `SCANNED` whenever `st["last_ok_at"]` exists, whatever the current
    `state` is. It then sets `failure_reason=None`, because `derived == SCANNED`.
  - `watchlist.scan_member` keeps `last_ok_at` when later attempts fail with
    `credential_refused` or `source_outage`.
  - So a shop the API has refused for months appears under `scanned` and is left out of
    `not_scanned`, which is the owner-facing list.
  - This breaks the directive this module exists for: an inaccessible shop must be recorded
    as inaccessible, and "not accessible" must stay distinct from "scanned".
  - `_anchor` has the same staleness problem. It keeps `failure_reason`, but it still
    reports `SCANNED` for an old success.
  - Repro (`/tmp/repro/r_scan.py`): seed the MadelineMaeCo watchlist memory with
    `{"state": "credential_refused", "last_ok_at": "2026-08-01T00:00:00+00:00",
    "last_attempt_at": "2026-10-31T06:00:00+00:00", "last_error": "403 key refused",
    "consecutive_failures": 40}` and call `SE.report(db)`. Observed:
    ```
    {'state': 'scanned', 'last_successful': '2026-08-01T00:00:00+00:00',
     'last_attempted': '2026-10-31T06:00:00+00:00', 'failure_reason': None,
     'consecutive_failures': 40}
    ```
  - Required change:
    - Derive the state from the latest attempt.
    - If `state != "ok"` and `last_attempt_at > last_ok_at`, report the shop as
      `not_accessible` (for `credential_refused` or a recorded limitation) or
      `attempted_not_scanned` (for `source_outage`). Keep `last_successful` and always give
      `failure_reason`.
    - Apply the same rule to the anchor: a failure newer than the last success is not
      `scanned`.
    - Optionally add a staleness bound, for example a last success older than twice the
      cadence counts as stale.
    - Add a test for "success, then repeated refusal".

## Part 4: Commercial lessons: ACCEPT

**What I checked, and found to hold:**

- **Only measured data.** Only `ListingOutcome` rows whose `source` starts with
  `owner_export:` (rows written by the owner's export intake) and that carry both `orders`
  and `visits` are read.
  - With nothing published there are no listings and no export rows, so nothing is
    published and the reading says UNMEASURED (covered by
    `test_nothing_measured_publishes_nothing_and_is_no_work`).
  - A comparison needs at least two categories with 200 or more visits each. No figure is
    invented.
- **Lessons stay inside the existing nudge.**
  - The new subjects are routed through the existing bus and the bounded ±0.06
    `radar.score` nudge in `improve.consume`; `FAVOURS`/`DISFAVOURS` only gain one subject
    each.
  - No gate, threshold or pre-engineering check reads these subjects (covered by
    `test_radar_score_moves_the_named_concept_by_the_bounded_nudge_only`).
- **Idempotent.** Lessons are idempotent on `evidence_ref`, and lessons the evidence no
  longer supports are withdrawn.

**Finding:**

- **F4.1 (LOW): overlapping owner exports double-count.** `measured_groups` sums every export
  row. Two exports whose periods overlap (for example 2026-10-01..31 and 2026-10-15..31) are
  different `(slug, period_start, period_end)` rows, so visits and orders in the overlap are
  counted twice.
  - Both the rate and the order threshold shift. Every number still comes from real data.
  - Fix: skip rows whose period is contained in another row for the same slug, or take the
    widest non-overlapping cover.

## Part 5: P0-LEARNING-GAPS (3cbf6e96, 9c1a0037): ACCEPT

**What I checked, and found to hold:**

- **Never purchases.** `intel/knowledge_gaps.assess` only writes `OwnerAction` rows (key
  `knowledge_gap:<line>`) and one `OperatingReading`. It calls no purchase, network or model
  path. `benchmark_refresh._pick` reads the `purchase_selection` choice, which is
  read-only. No handler consumes the `knowledge_gap:` prefix, so an approved row triggers
  nothing automatically: the owner buys by hand.
- **Cap enforced in code.** At most `MAX_OPEN = 2` `knowledge_gap:` actions are open at once,
  with one per pod. Lines the library already covers are never asked about. With no observed
  listing nothing is raised. `max_cost_cad` is the observed price from `purchase_selection`.
- **Owner-approval path.** Recommendations are ordinary `OwnerAction` rows in the owner queue.
- **Charter.** `learning.knowledge_gaps` is added to the learning charter's `job_types` and
  is classed OBSERVE. It runs under `analyst`, which keeps `daily_cost_ceiling_cad=0.0`.
  No new authority is granted.
- **No overlap with `teardown/`.** The module neither ingests nor analyses purchased patterns.
  Intake and analysis remain with Codex `P0-LEARNING-REFERENCE`. Its only teardown-adjacent
  read is a count of `BenchmarkProduct` rows per pod.

**Findings:**

- **F5.1 (LOW): no cap shared with `benchmark_refresh`.** `knowledge_gaps` and
  `intel.benchmark_refresh` each cap their own prefix at two. Neither checks the other's
  open rows, and both pick through the same `_pick(db, pod)`.
  - The owner can be asked twice to buy the same listing, under two keys, and up to four
    reference-purchase approvals can be open at once.
  - Fix: count both prefixes against one cap, and skip a pod that already has an open
    `benchmark_refresh:` request.
- **F5.2 (LOW): declined lines come back.**
  - The cap only counts *open* rows. When the owner closes one (declined or done), the same
    line can be raised again on the next weekly run while the gap persists. That is a nag,
    not a spend.
  - Fix: suppress a line for N weeks after its action is closed without a matching
    `BenchmarkProduct`.
  - Separately, when `price_cad` is missing, `max_cost_cad` falls back to `0.0`. That would
    show a purchase as CA$0. `purchase_selection` appears always to supply a price, but
    refusing to raise without a price would make this safe by construction.

## Part 6: Authority changes: ACCEPT

- **`authority/classes.py`:**
  - `improve.commercial_lessons` and `learning.knowledge_gaps` are OBSERVE.
  - `intel.scan_evidence` is OBSERVE. That is narrower than the RESEARCH class of its
    `intel.*` siblings, which fits, because it makes no external read.
  - `chain.successors` is BUILD, like `chain.rebuild`.
- **`agents/registry.py`:** the new job types go to existing agents:
  - `market_radar` gets `intel.scan_evidence` (GREEN, CA$4/day, unchanged);
  - `listing` gets `chain.successors`;
  - `analyst` gets `improve.commercial_lessons` and `learning.knowledge_gaps` (GREEN,
    CA$0/day).

  No agent's authority level or cost ceiling changed. No spend, publish or contact job type
  was added to any agent.
- **`charters.py`:** `chain.successors` is added to the listing charter, and
  `learning.knowledge_gaps` to the learning charter. Neither job type is in `generatable`,
  so neither can be self-generated. No prefix was widened.
- **`autonomy_map.json`:** the file was regenerated. Its counts went up by the four cadences
  and four handlers, plus one follow-on edge (`chain_successors.launch_held`).

---

## Tests (run against this head, one at a time, `nice -n 19`, venv from `requirements.lock`)

`df` before the run: 30 GB available.

| Suite | Result |
|-------|--------|
| test_opus2_chain_deadends | PASS (0 failed, 5s) |
| test_opus2_commercial_lessons | PASS (0 failed, 5s) |
| test_opus2_draft_constructions | PASS (0 failed, 5s) |
| test_opus2_knowledge_gaps | PASS (0 failed, 2s) |
| test_opus2_laura_home | PASS (0 failed, 11s) |
| test_opus2_photo_led_gallery | PASS (0 failed, ~210s) |
| test_opus2_reverify_withhold | PASS (0 failed) |
| test_opus2_rim_negative | PASS (0 failed) |
| test_opus2_scan_evidence | PASS (0 failed); the suite does not cover F3.1 |
| test_opus2_size_claims | PASS (0 failed) |
| test_shadow | PASS (rc=0, 883s) |
| test_v11_autonomy_timeline | PASS (0 failing, 96s; the committed map matches the generator) |
| test_vacuity | PASS (rc=0, 10s) |
| test_w4_fmbatch1_retention_guard | PASS (rc=0, 33s) |
| test_route_auth_default_deny | **NOT RUN**: `starlette.testclient` needs an HTTP client package that `requirements.lock` does not install. Installing an unpinned package was refused in this sandbox, so this suite needs re-running in a fully provisioned environment. That is an environment limitation, not a finding against the branch. |

## Required before integration

1. **F3.1:** a scan that once succeeded and has failed since must not be reported as
   `scanned`. Its failure must be shown, with a test.

Recommended follow-ups (do not block integration): F1.1, F2.1 (owner of the
`pipeline.py` re-certification path), F5.1, F4.1, F5.2, F1.2, F2.2.
