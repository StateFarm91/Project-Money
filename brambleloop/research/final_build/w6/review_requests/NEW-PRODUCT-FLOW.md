# NEW-PRODUCT-FLOW: why new products never reached certified, and the fix

**Branch:** `eng/new-product-flow`, cut from `claude/batch19-fixers` (8204c93).
**Status:** NOT merged and NOT deployed. Production is unchanged and no production row was read.
The cause is worked out from code and from the readback text.

## The readback

On prod 2f7da291, two checks fail:

- **"products progressing through certification":** 0 products certified in 7 days. The 9 Launch-0
  products sit at LISTING_READY, and every other lifecycle stage is empty.
- **"autonomous company loop":** 11 of 12 stages pass. The failing stage is `original_product`: no
  useful `cir.draft`, `cir.compile` or `gate.certify` job ran.

Every other stage is empty, so no Product row exists for anything outside Launch-0. In other
words, `cir.draft` never ran for a new concept.

## The supply path, traced

```
radar.concept_intake (6h, CA$0)  -> approves a research concept (RadarConcept row)
  -> radar.score (score:<slug>:<date>)
       promotion_verdict -> preengineering.gate_concept
         premise_thumbnail (#88): needs Concept.thumbnail_reads_small  -> UNMEASURED, needs image_vision
         jury (#83):              needs Concept.craft_impression       -> UNMEASURED, needs image_vision
       gate WAITING -> no supply.offer                                  <-- every new concept stops here
  [only if a judgement exists] radar.intake.rescore_judged -> radar.score -> supply.offer(draft:<slug>)
  -> supply.admit (15 min) -> cir.draft -> cir.compile -> gate.certify -> listing chain
```

Launch-0 is exhausted (`catalogue-exhausted:launch0`), so `seed_launch0` adds nothing. The only
new supply is therefore research concepts, and every one of them waits on `image_vision`.

The two taste fields come only from `creative.intake.judgement_for`. That function reads a
`concept.judged` row bound to the bytes of the board on file (CB2-D01), or a grid-tournament
verdict.

**The defect.** Only one function asks the vision judge: `creative.intake.regate_held`, called by
`mjs.seasonal_sentinel`, `creative.tournament` and `creative.expedition`. It iterates
`creative.winner_intake` rows only, which cover tournament winners and the engineered moment
candidates that `register_for_taste_gate` files. Two things were missing for a radar research
concept:

- no board was filed where `board_for` reads;
- the judge was never asked about it.

`rescore_judged` was written to re-score a concept "once the vision judge's verdict is on record",
but nothing ever put that verdict on record. So even with paid vision open (D-OWNER-APPROVE-ALL),
a research concept waited forever.

This reproduces on the real handlers. With vision usable, `mjs.seasonal_sentinel` returned
`regated: {presented: [], held: [], vision_usable: True}`, so the waiting concept was invisible to
the judge.

A second, smaller defect: the re-score after a judgement used the key `score:<slug>:<date>`. The
score that left the concept waiting had already taken that key that day, so the re-score was
dropped until the next UTC day.

## The fix

All the changes are in `creative/intake.py` and `radar/intake.py`.

- **`judge_radar_waiting(ctx, ...)`**, called at the end of `regate_held`. It shares that run's
  `REGATE_LIMIT` cap on paid judge calls, and the budget stop. It picks each approved radar concept
  that meets all of these:
  - not yet drafted;
  - no current judgement;
  - its newest pre-engineering verdict is WAITING on `image_vision`.

  For each one it:
  - **Vision closed:** writes nothing and asks nothing. It reports the concept under
    `radar_held` with `vision_model (...)`.
  - **No board yet:** draws one with `file_radar_board`, which uses the existing #126
    `creative.board.make_board`. The board is a deterministic digital-twin render, costs CA$0, and
    is disclosed as "not a photograph". It is filed as a `creative.concept_board` row (the action
    `moment_candidates` already uses), so the judge and `judgement_for` read the same bytes.
  - **Board on file:** calls the existing `judge_held`. That call is budgeted, bound to the board's
    sha256, and refused rather than faked when the answer is not a judgement.
  - **Judged:** hands the concept straight back to `radar.score` through `rescore_judged`.
    `radar.score` re-runs the whole pre-engineering gate on the recorded judgement and offers the
    concept to supply only if every check passes.
- **`rescore_judged(..., key_for=None)`**. The judge's pass sends a key bound to the judged board,
  `score-judged:<slug>:<board sha[:16]>`. This means the re-score happens in the same run, and at
  most once per judged board. The default key and the radar.concept_intake caller are unchanged.

No new job type and no new cadence. The autonomy map and sw.js are unchanged.

## What is NOT changed (every gate stays)

- The pre-engineering gate, its thresholds, and "unmeasured is never passing".
- Nothing writes `thumbnail_reads_small` or `craft_impression` except the judge's own recorded
  answer.
- A concept judged not to read at grid size is REFUSED at `radar.score` and never drafted (tested).
- The children's-products pre-check at intake, child-safety holds at certify, engine holds
  (`construction_unsupported:*`, `engine_demand:*`), supply admission (WIP, backlog, cost, family
  diversity) and the certificate gates: none of these is touched.
- No existing test was edited.

## Tests

New suite: `tests/test_new_product_flow.py`.

The simulated production state:
- Launch-0 is exhausted: every release seeded before, and `seed_launch0` reports `exhausted`.
- One research concept is approved and scored. It is a FIXTURE, as is all its research evidence.
- The owner has activated paid vision, a probe succeeded, and a FIXTURE vision provider answers.

Only the scheduler's own cadence jobs are enqueued (`radar.concept_intake`,
`mjs.seasonal_sentinel`, `supply.admit`); the worker drains what follows. Nothing stubs
`judgement_for` or enqueues a chain job.

| test | before fix | after fix |
|---|---|---|
| `test_the_simulated_state_is_productions` (WAITING on image_vision, nothing drafted) | ok | ok |
| `test_with_vision_open_a_new_research_product_reaches_certified_unaided` | **FAIL** `([], [])`: judge never called | ok: judged once, `draft:<slug>` admitted, certified with compile/twin/reverse stages |
| `test_a_concept_judged_not_to_read_at_grid_size_is_refused_and_never_drafted` | FAIL (never judged) | ok |
| `test_with_vision_closed_nothing_is_judged_and_the_concept_waits_with_its_reason` | FAIL (no `radar_held`) | ok |
| `test_a_judgement_is_never_carried_onto_a_board_nobody_looked_at` (CB2-D01) | FAIL | ok |
| `test_mutation_the_radar_judging_pass_removed_leaves_production_stalled` | n/a (added with the fix) | ok: the mutant re-creates the stall |

The before run was made at 8204c93 with the test file only; its output was kept in the session
scratchpad. The before-fix version of the CB2-D01 test asserted on a state after certification,
which the listing assets legitimately change. It was rewritten to check the binding right after
judging, before any draft.

Targeted run: see "Suite run" below.

## Not verified / open

- **Whether `image_vision` is actually open in production is UNVERIFIED.** `vision_usable` needs
  two things:
  - the **anthropic-vision** activation, and
  - a successful vision probe under it.

  D-OWNER-APPROVE-ALL activates `openai-vision:vision` and `flux-3-image:generation` only.
  - **If anthropic-vision is not activated:** after this fix the readback still shows 0 new
    certified products, but the reason is now named on each `mjs.seasonal_sentinel` /
    `creative.tournament` output (`regated.radar_held: vision_model (...)`) instead of being
    invisible.
  - **Opening it:** that is owner activation of anthropic-vision through the normal step-up path
    (CA$ ceilings per the activation). This branch does not route the radar judge to openai-vision
    on its own.
- POOL (non-research) concepts that wait on image_vision are not covered by
  `rescore_judged`, which handles approved intake rows only. Launch-0 and catalogue designs are
  gate-exempt (`preengineering.established`). Covering POOL concepts is a follow-up.
- The judging cadences are `mjs.seasonal_sentinel` (daily), `creative.tournament` and
  `creative.expedition`. In production, a new concept therefore waits up to about a day for its
  judgement, then flows on the 15-minute `supply.admit`.
- The board for a concept whose form has no prototype geometry cannot be drawn. That concept
  stays held, with `board_image (no board could be drawn: ...)` as the reason.

## Suite run

Runs used `JOBS=4 SUITE_REGISTRY=0 SUITES=... bash run_tests.sh` on the py3.11 lockfile venv. None of
them is release-eligible: the tree was dirty, and HEAD moved during run 2.

1. **Run 20261121T003201Z-1262** (the fix, before the retention follow-up), 14 suites:
   - 264 passing, 3 suites failing.
   - `test_w5_concept_intake`: 2 failures, `RetentionRefused`. The retention scan could not resolve
     the f-string audit actions that `_gate_waits_on_vision` reads. This was **caused by this
     branch, and fixed**: the actions are now named literally, and `concept.gate_waiting`,
     `concept.gate_refused` and `concept.gate_passed` have `latest` retention decisions.
   - `test_eng_demand_supply`: 1 failure in
     `test_originals_run_through_intake_gates_into_buildable_work_and_engine_demand`
     (`cosy-round-bear-amigurumi` held `construction_unsupported:outline_round`). This is
     **pre-existing**: it fails identically on the base commit 8204c93 in a clean worktree. Not
     caused by this branch, and not fixed here.
   - Passing: `test_cert_design_pipeline`, `test_eng_families`, `test_eng_homedecor`,
     `test_eng_supply`, `test_fb2_i_repairs`, `test_new_product_flow`, `test_research_flow`,
     `test_vacuity`, `test_w4_auto_pipe2_wiring`, `test_w4_pipe2_candidates`,
     `test_w4_research_to_product_stall`, `test_w5_a7_supply_stall`.
2. **Run 20261121T005130Z-3588** (after the retention fix), 8 suites:
   - `test_w5_concept_intake`, the three retention suites, `test_cert_design_pipeline`,
     `test_w4_research_to_product_stall` and `test_vacuity` all pass.
   - `test_new_product_flow`: 6 of 6 passed, but the runner counted no passes (lowercase `ok`
     output). Fixed to `OK`.
3. **Final run:** `test_new_product_flow` + `test_vacuity`, 14 passing, 0 failing.
