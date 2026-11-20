# ENG-MOTIF-BACKLOG: review request. Recover the backlog of paid renders whose motif check was refused

Branch: `eng/motif-backlog`, base `origin/claude/w6-INTEG2` @ `a35ad302`. It merges
`origin/eng/motif-reservation` @ `58ba3455` (ENG-MOTIF) with a merge commit, `f954997a`. The final
SHA is the commit that adds this file; see the issue #28 comment.

## Answer to the owner's question first: how many products are recovered

**Under the gates as they are, a recovered owned or model render completes no gallery, and no
listing package becomes ready because of one.** The recovery job measures this; it does not
assume it. It is not caused by the motif check. Two gates the owner told me not to weaken stop it:

1. `visual.product_authority.structural_floor` gives a generated frame no PASS. There is no
   qualified whole-product producer (F-852, D-FB-7). Every usability reader requires that PASS:
   `owned_photography.usable_asset`, `model_photography.usable_asset` / `_passing_frame` and
   `listing_asset.usable`.
2. Even with that floor stood in, `listing.seo` refuses a generated finished-object image on
   **POLICY_CLASSIFICATION (F-852)**. `test_e2e_a_recovered_render_the_gallery_accepts_...`
   shows this on the real worker.

This matches ENG-MOTIF's finding: at this base `owned_photography.make` and
`model_photography.make` both return `redraw_refusal` first, so no new generated render is made.
The backlog is the renders filed before F-852.

So in production the job will:

- find every refused render;
- **park** each one at no cost, because a re-ask is bought only when a match could make the
  render usable (ENG-MOTIF's `worth_rejudging`, kept on purpose under F-328 No Spend To Look
  Busy);
- report found = N, parked = N, galleries completed = 0, packages ready = 0.

The counts come from persisted rows. The production numbers are not known from here; Main can
read them from `/api/readback/evidence` → `motif_backlog_recovery` once the first six-hourly
sweep has run. Before that first sweep every count reads **UNKNOWN**, never 0.

A parked render is not lost. Each sweep re-evaluates it for free, and it is re-asked the day a
qualified producer gives generated frames a structural floor.

Also worth the owner's attention, and **not** changed here: a generated product image filed for
a release makes `listing.seo` classify that release under F-852 *even when its gallery is the
disclosed renders*. This is the fail-closed loop in `runtime/release.py` around
`_op.last_asset`/`_mp.last_asset`. So those old paid renders block `listing.seo` for their
products today, whatever their motif verdict. Changing that is a policy decision, not a
recovery decision.

## What was built

### 1. Recovery job `assets.motif_backlog` (`publish/motif_backlog.py`, handler `runtime/motif_backlog_ops.py`)

ENG-MOTIF already reserves the call and re-asks about a render, so this branch does not
duplicate that. The re-ask is `motif_fidelity.rejudge`, through `_call_judge`'s
`check_budget` as `quality_director` / `asset_inspection`, billed at cost. The answer is filed
by `owned_photography.rejudge_motif` / `model_photography.rejudge_frame`, as a new row that the
readers already treat as superseding the refused one. This module adds the backlog around that:

- **`scan`**: reads every `assets.owned_photography` row and every frame inside an
  `assets.model_photography` sequence. It picks out the frames whose motif is `unmeasurable`
  *because the call was refused for budget or reservation*. That means either the legacy text
  (`the comparison call failed: [<code>] …` with a code in `BUDGET_CODES`,
  `BudgetExceeded`/`AgentCeilingExceeded`), or the coded `unmeasured: budget_refused`. A
  mismatch, a genuine unmeasurable, `not_activated_by_owner` and plumbing failures are never
  picked up. Scanning writes one `motif_recovery` row per distinct image
  (`source:slug@version:sha256`), so a frame that a later sequence reused counts as one render.
  Running the scan twice is a no-op.
- **`recheck_one`**: never renders.
  - Not `worth_rejudging` → **PARKED**. No call is made.
  - Loads the CIR from the **certified `PatternVersion` row** for exactly that slug@version, not
    from the catalogue. A missing or changed release → SUPERSEDED.
  - Re-asks, then:
    - match → **PASSED**, and the answer is filed;
    - mismatch, or a judge that could not see the fabric → **FAILED**, filed, and the **only**
      state that is regenerated. It goes through the existing job for its path
      (`assets.owned_photography` / `assets.model_photography`), with idempotency key
      `motif-backlog-regen:<source>:<id>`;
    - budget, ceiling or activation refusal → **QUEUED_BUDGET**: nothing filed, nothing
      regenerated, `budget_deferrals` incremented, retried on the next sweep;
    - plumbing (`call_failed`, `answer_unreadable`, `chart_unrenderable`, transient) →
      **QUEUED_RETRY**, up to `MAX_RECHECKS`. Then it becomes UNRESOLVED and the last answer is
      filed. It is never regenerated;
    - bytes gone → **BYTES_MISSING**.
  - For a model sequence, the filed re-ask sequence carries every answer already on file for
    its frames (`_answered_frames`). The floors are recombined with
    `model_photography._combine_floors`.
- **Registration**:
  - handler, in `pipeline.py` imports;
  - `publishing` agent permission;
  - six-hourly cadence;
  - `JOB_CLASS` (same class as owned photography);
  - department, through the `assets.` prefix;
  - `WORK_KEYS` (`work_done`);
  - `JOB_BANDS` (`proven_winner`);
  - regenerated `autonomy_map.json`;
  - retention decision for `assets.motif_backlog.swept` (`latest`; `unknown_read_actions()` → `[]`).

### 2. Advancement (the missing handoff)

The trace found that nothing downstream started when a gallery became usable. The
`assets.owned_photography` and `assets.model_photography` handlers audited the record and
returned, so `pricing.position` → `listing.seo` → `launch.plan` → `listing.package` waited for
an unrelated sweep. Fixed:

- `motif_backlog.gallery_handoff` enqueues `assets.build` for the certified release. Its key is
  `chain_key("assets", slug, version, release, "gallery:<id>")`, so each gallery advances once.
  It fires only when the **existing** reader (`listing_asset.last` + `listing_asset.usable`) says
  the gallery is complete. `assets.build` then carries the release through the existing chain to
  `listing.package`.
- It is called from both photography handlers (`release._gallery_handoff`) when they file a
  usable record. A handoff failure never fails the photography job. The recovery sweep also calls
  it for PASSED renders, with `requires_image`: a gallery completed by *other* frames is not
  counted as recovered.
- No gate changed. Product Truth, image truth, `structural_floor`, F-852 classification, the A3
  photo authority and `SAMPLE_PHOTO_REQUIRED` are untouched.

Not wired, and noted for Main: `image_production.approve`. It is an owner Command Center action
with no queue in scope, and `listing.package`'s six-hourly sweep picks it up.

### 3. Recovery report (read-only)

`motif_backlog.report(db)` has these counts:

- renders: found blocked, re-checked, passed, failed, still queued (budget), queued (retry),
  parked (a match could not make them usable), unresolved, awaiting first re-check, bytes
  missing, superseded;
- regenerations queued;
- products blocked;
- **products whose gallery completed**: stamped when the recovered image is part of the gallery
  the existing reader accepts;
- **listing packages that became ready**: the `OperatingReading` `listing.package` row is
  `ready_for_owner_review` and was assembled at or after that gallery completed.

Every count comes from `motif_recovery` rows. If no sweep has ever run, every count is UNKNOWN,
and an unreadable table is UNKNOWN too. It is shown in two places:

- the **P0 board** section `motif_recovery` (UNKNOWN / RECOVERING / RECOVERED, with levels);
- the **`/api/readback/evidence`** section `motif_backlog_recovery`, plus the advisory readback
  item "paid renders recovered from refused motif checks" (WARN while anything waits or before
  the first sweep, PASS when settled). It never fails a deploy. `test_w4_readback_evidence` item
  count 16 → 17.

## Tests: `tests/test_motif_backlog.py`, in `suite_final_segment.txt` before `test_product_run`

The tests use the real certification of the Cloudline blanket, the real worker, the real
`check_budget` reservation, the real `motif_fidelity.check` / `rejudge` and ENG-MOTIF's filing
functions. The stub vision provider is the only substitute, sockets are closed, and every image
generator entry point raises if reached. Re-ask tests use ENG-MOTIF's labelled
`_qualified_floor` stand-in, which gives PASS exactly when the motif matched. Without it, every
re-ask is parked, and one test proves that.

- Registration, autonomy map counts, retention guard.
- Refusal classification: legacy text for every `BUDGET_CODES` entry, coded through the
  **real** `PaidCallRefused` → `VisionGateRefused` path for every gate budget code. Mismatch,
  genuine unmeasurable, `not_activated_by_owner` and plumbing are not picked up.
- **Gates as they are**: refused renders are found and PARKED with zero calls, zero spend and
  zero regeneration. Then, with the qualified floor, the same renders are asked and PASS.
- **Backlog recovered with no regeneration**: 2 owned and 2 model renders, one of them reused
  across two sequences. Exactly 4 comparisons are made, 0 generator calls, 0 photography jobs.
  Reservations are fully released, and 4 `quality_director`/`asset_inspection` cost rows are
  written. A second sweep re-checks and spends nothing. Readers see the answer, each render is
  charged once, and the filed model sequence is `motif_rejudge_only` with `product_truth: pass`.
- **Only a genuine failure is regenerated**: in a mismatch+match pair only the mismatch is
  queued, and only once across re-sweeps. A judge that cannot see the fabric is FAILED. A model
  frame regenerates through the model path.
- **Budget exhaustion**: with `check_budget` refused, the renders are QUEUED_BUDGET, with nothing
  called, filed or regenerated. With the gate refusing the re-ask, they stay QUEUED_BUDGET. When
  budget returns, the same renders PASS.
- Plumbing: retried, nothing filed, then UNRESOLVED and filed once, never regenerated. Bytes
  missing: BYTES_MISSING.
- **End to end**:
  1. Real gates: the release's disclosed gallery is complete, but the recovered render is
     parked, not part of it and not handed on. Counts are found 1, parked 1, passed 0, galleries
     0, packages 0.
  2. With the floor stood in for one render only: the sweep hands the release to `assets.build`,
     which runs `pricing.position` and `listing.seo` with no manual kick. `listing.seo` refuses
     on POLICY_CLASSIFICATION, and the handoff fires once.
  3. No stand-ins: a release stalled after `assets.build` whose disclosed gallery is complete is
     carried by the handoff alone to `listing.package`. The package is assembled; it is BLOCKED
     only on the physical-sample, Etsy and `SAMPLE_PHOTO_REQUIRED` gates, with no image or
     gallery blocker.
  4. A gallery completed by other frames is not counted as recovered.
- Handler handoff: a usable record enqueues the exact `assets.build` inputs and key, and an
  unusable one enqueues nothing.
- **Report counts exact** over 14 rows in every state (products counted once). UNKNOWN before any
  sweep and when unreadable. A package counts as ready only when READY was assembled after the
  gallery completed (READY before → no; BLOCKED → no).
- The P0 board and readback evidence show UNKNOWN → RECOVERING → RECOVERED and WARN → PASS, and
  write nothing.

### Mutation guards (run by hand on a scratch copy; results below)

A mutation script (not committed) applied each source mutation in turn to a scratch copy of
`publish/motif_backlog.py` and ran the targeted tests against it. **10/10 were killed.** The
unmutated tests pass.

| mutant | killed by |
|---|---|
| any `unmeasurable` "comparison call failed" counts as a refusal (prefix check removed) | `test_only_a_budget_refusal_is_recoverable_legacy_and_coded` |
| any coded `unmeasured` counts (not only `budget_refused`) | same |
| `worth_rejudging` guard removed (re-ask always bought) | `test_with_every_gate_as_it_is_the_backlog_is_found_and_parked_at_no_cost` |
| a budget refusal becomes FAILED (regenerated) | `test_budget_exhaustion_leaves_every_render_queued_and_nothing_regenerated` |
| a match is not PASSED (falls to FAILED, regenerated) | `test_only_a_render_that_genuinely_fails_is_queued_for_regeneration` |
| `requires_image` ignored (other frames' gallery counted) | `test_a_gallery_completed_by_other_frames_is_not_counted_as_recovered` |
| `gallery_complete` ignores `listing_asset.usable` | `test_a_gallery_the_existing_reader_rejects_is_never_complete_or_handed_on` |
| never-swept counts read 0 instead of UNKNOWN | `test_the_report_counts_are_exact_and_unknown_is_never_zero` |
| a package READY before the gallery completed is counted | `test_a_package_counts_as_ready_only_when_ready_after_the_gallery_completed` |
| per-image dedupe removed (a reused frame recovered twice) | `test_a_backlog_of_refused_renders_is_recovered_with_no_regeneration` |

Two mutants survived the first round (`requires_image`, `gallery_complete` without
`usable`): under the real gates every render is parked, so neither branch was reached. The
two tests named above were added for them. The first draft of the `requires_image` test
also failed *unmutated*: a blanket floor stand-in hid the disclosed frames' real PASS. It was
rescoped to the one render's sha before it was counted as a kill.

## ENG-MOTIF-BACKLOG-FIX: the four MEDIUM findings of the independent review

Verdict was DO NOT SHIP. Each finding is fixed and has a test that its mutant fails.

| # | Finding | Fix | Test (kills the mutant) | Mutant |
|---|---|---|---|---|
| 1 | `test_cost_governance_wave2` fails: `motif-backlog-` missing from `ops.health.TEMP_PREFIXES` | prefix added | `test_cost_governance_wave2` (the registry test) | prefix absent (the tree as reviewed): fails |
| 2a | `sweep` bounded only BLOCKED/QUEUED rows; PARKED rows that became worth asking each bought a call (limit=1 made 4) | ONE allowance `{"left": limit}` shared by every row the sweep touches, all states; checked before the claim | `test_limit_n_means_at_most_n_paid_reasks_across_every_row_state` (limit 1/2/0/5 -> 1/2/0/1 calls) | allowance check removed: 4 calls on limit=1 |
| 2b | no per-day cap | `DAILY_CAP = 40`, `BRAMBLELOOP_MOTIF_BACKLOG_DAILY_CAP` may only lower it; durable count = `assets.motif_backlog.claimed` rows since 00:00 UTC, read inside the claim transaction (retention: `windowed`) | `test_the_daily_cap_is_durable_and_only_lowered_by_the_environment` | cap check removed |
| 3a | a newer answer on file for the image (the photography job's ENG-MOTIF rejudge, or this sweep before a crash) was paid for again | `_newer_answer`: before paying, the newest answered motif for the same image hash and slug@version filed after the refused row is reused; no call, no claim | `test_an_answer_the_photography_job_filed_first_is_reused_not_paid_again`, `test_a_crash_between_filing_and_settling_is_not_charged_twice` | reuse removed: both fail |
| 3b | `rechecks` incremented after the paid call; a crash mid-call counted toward nothing | `_claim` runs BEFORE the call, in one transaction: daily-cap count, compare-and-set `rechecks = rechecks + 1 WHERE rechecks = <read> AND state IN open`, and the claim row. A replay claims a new attempt, never re-uses a spent one; two sweeps cannot claim the same attempt. Paid attempts (`rechecks - budget_deferrals`) >= MAX_RECHECKS -> UNRESOLVED with no call | `test_a_crash_during_the_paid_call_counts_as_a_claimed_attempt` | increment removed from the claim |
| 4a | `worth_rejudging` read only the structural floor | `eligible()` applies the photography jobs' own merits rule, now one shared function each: `owned_photography.motif_eligible` (asset truth `clear`; `awaiting_motif` calls it) and `model_photography.motif_eligible_frame` (every other floor; `_awaiting_motif_frame` calls it). Ineligible -> `INELIGIBLE`, never asked, reported as `renders_ineligible_on_merits` | `test_a_render_ineligible_on_its_merits_is_never_reasked_or_passed` (blocked owned, failed styling, open realism) | eligibility check removed |
| 4b | a match was PASSED whether or not it made the render usable | PASSED only on a real MATCH whose filed answer is `usable_as_listing_asset` with structural PASS; a match that leaves it unusable is INELIGIBLE | `test_a_match_that_leaves_the_render_unusable_is_not_counted_passed` | usable check removed |

Kept: no FLUX call and no regeneration path added (`no_generation` in every new test); UNKNOWN /
UNMEASURABLE never PASSED; budget refusals queue and spend nothing; MAX_RECHECKS unchanged; Laura's
identity code and `laura-r2-a42aeac7` untouched (not in the diff).

`test_a_gallery_completed_by_other_frames_is_not_counted_as_recovered` was rescoped: it used an
asset-truth-`blocked` owned render that reached PASSED -- finding 4 itself. It now uses a recovered
model detail frame outside the gallery, and still kills its `requires_image` mutant.

A FAILED answer reused from the photography job is not queued for regeneration by the sweep (that
job's own cadence owns it; queueing it here would buy a second render). A FAILED answer this sweep
filed before a crash is, idempotently by the existing per-row key.

## Suites

Scope: the unit's suite (`test_motif_backlog`), every suite naming `motif_fidelity`,
`owned_photography`, `model_photography` or `gallery` (`grep -lE` over `tests/test_*.py`), plus
`test_model_spend_paths`, `test_cert_spend_hosts`, `test_cost_governance_wave2` and
`test_w3_spend_attribution`: **147 suites**, through `run_tests.sh` with `SUITES=`.

| Run | SHA | Suites | Result |
|---|---|---|---|
| `20261119T233335Z-1646` | `0629c1d` (all code fixes) | 147 | 2212 passing; 12 suites failing |
| `20261120T001642Z-8343` | `514f143` | the 8 below | 172 passing, 0 failing |
| `20261120T003357Z-9352` | `514f143` | the other 4 | 68 passing, 0 failing |

The 12 failures in the first run had two causes:
- **11 were the test venv:** `starlette.testclient` found no `httpx`. I installed the pinned
  `httpx==0.28.1` from `requirements-test.lock` (`--no-deps`, as its header says). No code changed.
  Suites: test_cert_mjs, test_cert_wiring, test_health, test_policy_intake, test_s4_p0_board,
  test_w3_k4_launch_verdict, test_w4_close5_rows4, test_w4_controlled_experiments,
  test_w4_launchfix, test_w4_rel2, test_w5_v0_paid_provider_gate.
- **1 was real and already on the branch** (it fails at `13c9484` too):
  `test_w4_close5_rows::test_f152_every_scratch_site_is_classified`. The backlog's
  `recheck_one` scratch site had no F-152 entry. It is now registered as `durable` through
  `_file_answer` (`AuditLog(`), and the suite fails again with the entry removed.

`test_cost_governance_wave2` (finding 1) passes in run `-1646`. Every suite that ran at
`514f143` passed. The other 135 ran at `0629c1d`, and `514f143` adds only a test-registry
entry and this document on top of it.

## Residual

- Production counts are unknown until the first sweep runs after deploy. Main reads them from
  the readback.
- An owned render whose asset-truth *inspection* was also refused (`verdict: unjudged`) is a
  different refusal (`visual.inspect`). It is out of scope here, as ENG-MOTIF also notes.
