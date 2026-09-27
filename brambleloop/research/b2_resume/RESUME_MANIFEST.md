# Build 2 certification — RESUME MANIFEST

Written 2026-09-27 at a session-limit handoff. **Build 2 is NOT certified.** Certification is in
progress and safe to resume from this file.

## 1. Where things are

- Working branch: `claude/visual-investigation` (worktree
  `/home/user/Project-Money/.claude/worktrees/visual-investigation/brambleloop`). The HEAD that
  carries this manifest is the latest pushed checkpoint; see `git log -1 origin/claude/visual-investigation`.
- Checkpoints before this manifest: `9d6eed2` (audit findings recorded, 151 rows reopened) and
  `b90e7e1` (C-73 fixed).
- Integrated/production branch `claude/repository-setup-nc9x6o` has not been touched. It is still
  at `fcb982d`. Nothing was deployed, merged, published, advertised or spent. Phase is still shadow.
- The frozen candidate that the final audit refuted is `9434c53`.

## 2. Honest 320-row state (closure.matrix at b90e7e1; saved in `closure_state.json`)

| State | Count |
|---|---|
| COMPLETE+PROVEN | 116 |
| OPEN | 131 |
| OWNER-GATED | 44 |
| DATA-GATED | 24 |
| EXTERNAL-BLOCKED | 5 |

**Honest reading: the effective OPEN count is 151, not 131.** Twenty reopened rows still
classify as gated. Their registry status is `partial` and they have no `parked_on`, but
`build2/executor.py` Gate tuples still list them, and `closure.classify` takes gate membership
from those tuples. That is part of defect C-65.

The 20 rows are:
- design: 277, 278, 281
- improve: 147
- orders: 104
- growth: 243, 244, 245, 250, 294, 295
- platform: 61
- intel: 39, 64, 116, 165, 208, 210, 211, 304

Treat them as OPEN until their repair lands and the auditor agrees.

OPEN by repair cluster (all rows reopened by C-60; the full gap text per row is in `wave_<cluster>.md`):

- **design (C-61)**: 3, 88, 101, 109, 110, 112, 114, 115, 279, 282, 283, 290, 293, 308, 309, 314, 316, 318 (+ 277, 278, 281)
- **improve (C-62, C-63)**: 53, 90, 92, 93, 95, 96, 97, 99, 100, 129, 153-161, 164, 174, 176, 179, 180, 187, 190, 193, 194, 220, 228, 231 (+ 147)
- **orders (C-64)**: 11, 12, 13, 22, 26, 42, 47, 49, 132, 233, 234, 235, 252, 256, 269, 271 (+ 104)
- **growth (C-66, C-70)**: 7, 17, 18, 19, 24, 27, 237, 238, 239, 242, 246, 247, 248, 249, 251, 253, 255, 257-262, 264, 267, 273, 275, 276, 291 (+ 243, 244, 245, 250, 294, 295)
- **platform (C-65, C-68, C-69, C-72)**: 5, 29, 30, 31, 34, 38, 40, 44, 50, 54, 59, 81, 131, 163, 169, 171, 172, 175, 188 (+ 61)
- **intel (C-71)**: 2, 15, 86, 125, 126, 128, 139, 201, 203, 215, 219, 226, 227, 268, 287, 289, 299, 300 (+ 39, 64, 116, 165, 208, 210, 211, 304)

The following gated IDs are listed as the closure reports them today. The auditor judged them
valid unless they appear in the lists above:

- **OWNER-GATED**: 1, 4, 9, 10, 14, 16, 37, 43, 46, 51, 61, 64, 67, 104, 116, 147, 165, 168, 189, 195, 208, 210, 211, 218, 221, 222, 236, 241, 243, 244, 245, 250, 254, 263, 266, 277, 278, 281, 294, 295, 304, 315, 317, 320
- **DATA-GATED**: 8, 20, 21, 23, 25, 28, 33, 41, 45, 48, 82, 89, 94, 98, 120, 140, 229, 265, 270, 272, 280, 292, 296, 298
- **EXTERNAL-BLOCKED**: 35, 39, 72, 130, 202. Product-Only Visual V1 is a real external blocker and is not PASS.

`reopen_prev.json` holds each reopened row's status and parked_on from before it was reopened.
Use it when restoring a park that turns out to be genuine.

## 3. Certification defects (full text in `research/BUILD2_CERTIFICATION.md`)

C-1 to C-59 are FIXED or RESOLVED.

**C-60 to C-72 are unresolved.** They were recorded against 9434c53, and each Repair cell reads
`pending`:

- **C-60**: the final audit found 55 invalid rows and 96 weak rows, all reopened.
- **C-61**: tournament winners never reach engineering.
- **C-62**: the improvement sandbox is deadlocked.
- **C-63**: the league has no run producer.
- **C-64**: there is no order or receipt ingest.
- **C-65**: closure blind spots:
  - a module reached only through a static `state()` route counts as reached;
  - owner_gated rows skip the reachability check;
  - an executor gate-tuple listing overrides a reopened status;
  - a matrix built without a database treats every gate as closed.
- **C-66**: hard-coded or constant inputs.
- **C-67**: outputs that nothing reads.
- **C-68**: lane controls are inert with a single worker.
- **C-69**: chain.rebuild ignores its inputs.
- **C-70**: ads.* job types are granted but have no handler.
- **C-71**: misclassified parks.
- **C-72**: tautological gates.

**C-73 is FIXED** (b90e7e1). The fresh full suite on 9434c53 was red: 5,053 passing, 2 suites
failing. Fixes:
- collections now assemble when a member certifies, at their band;
- the disclosure test checks each product rather than counting jobs;
- #35 is added to the rendered_pages gate.

## 4. Suites and audits

**Fresh full suite on the frozen candidate 9434c53** (clean checkout, 2026-09-27T12:11:41Z, 1,590 s):
- TOTAL PASSING 5,053; suites failing 2 (test_cert_wiring 3 FAIL, test_executor 1 FAIL). Recorded as C-73.
- At b90e7e1 the C-73 fixes pass:
  - test_cert_wiring 16/16;
  - test_cert_commerce 13/13;
  - test_cert_growth_seasonal 0 failures;
  - test_cert_orchestration 0 failures;
  - test_cert_publish_gates 0 failed;
  - test_seasonal_incidents no FAIL lines.

**test_executor at b90e7e1: 3 FAIL.** These are consequences of the honest reopen:
- test_a_gate_may_be_satisfied_and_carry_no_requirements
- test_a_gate_opening_un_parks_its_requirements_with_nobody_remembering
- test_the_registry_gate_un_parks_on_the_same_condition_as_the_hand_written_one

They need a registry row parked on image_generation. Reopening removed #203's and #300's parks.
The intel cluster decides the correct parks. If no row genuinely waits on image_generation, the
tests must prove the un-park mechanism with a synthetic fixture instead, without weakening what
they prove. **Do not restore the parks just to make these tests pass.**

**A full suite has NOT been run on b90e7e1** or on any integration of the repair wave.

**The independent 320-row proof/reachability audit** was completed against 9434c53
(`final_audit_9434c53.json`: 169 valid, 96 weak, 55 invalid) and refuted certification. A fresh
audit is required on the final integrated head.

## 5. Repair wave (launched after 9d6eed2): six agents, one worktree each

Each agent has the common brief (`wave_brief.md`) and its row list (`wave_<cluster>.md`). Each
works on local branch `claude/b2r-<cluster>` from base `9d6eed2`, in worktree
`<scratchpad>/wt_<cluster>`. The scratchpad is ephemeral.

Agents may not edit `requirements.json`, the ledger, BUILD_STATE or DECISION_LOG. Each must
report a JSON block giving status, parked_on, proof and note per row.

Agent IDs, valid only in the originating session:

| Cluster | Agent ID |
|---|---|
| design | a3961c291c36d9c57 |
| improve | a3d8f5ac474c4e3bb |
| orders | a2c7d8c9a2ccf849e |
| growth | a43ac05e56ca51e4f |
| platform | a79dc900270cdf9ba |
| intel | a512474b485778415 |

Snapshot at handoff: **all six were still running and none had reported.** Their work so far is
preserved in `patches/`:

| Cluster | Branch head | Commits since 9d6eed2 | Uncommitted |
|---|---|---|---|
| design | 7195d26 | 3 (winner intake, brief generation, funnel gate at cir.draft, pipeline walker, buyer language, skill make-time, tests) | none |
| improve | 9a2ee67 | 4 (replay league producer, sandbox forward trials, teardown enforcement, veto/standards at publish, lesson consumers, weekly evolution, versioning, challenger evaluations) | test_cert_wiring.py |
| orders | 8837c2f | 2 (order ingest behind transactions_r, order readings, trajectory/north star from DB, handler tests) | none |
| growth | 072e8e5 | 6 (ads handlers behind owner gate, distribution/journey/steer cadences, support timing, commerce readings from real data, pricing, CSV ingest route, tests) | none |
| platform | 253e717 | 6 (worker pool and lane enforcement, chain.rebuild honouring inputs plus provenance, #163 #169 #81 #59 #61 #54 #34) | orchestrate.py and new test_cert_thrash.py (copied to `patches/platform_untracked/`) |
| intel | 883697e | 9 (photo intake #64, strength scorer #125, board producer #126, breakout #128, teams #287, collection blocking #289, matrix #299, pod maps #210, quote tokens #139, drift series #201, reference reading #116, tests) | none |

Notes:
- **platform** still has not done C-65 (the closure rule); verify on resume.
- **intel**: the reclassification of #203/#300/#304/#86 still needs checking.

Recovering a cluster's work if its agent or worktree is gone:

```
git worktree add -b claude/b2r-<c> <dir> 9d6eed2
cd <dir> && git am research/b2_resume/patches/<c>.mbox
git apply research/b2_resume/patches/<c>.uncommitted.diff
```

Run the `git am` with the patches taken from this branch's copy. For platform, also copy in
`patches/platform_untracked/test_cert_thrash.py`.

These are **agent claims only.** None of this work is integrated, verified by the lead, or
reflected in the registry.

Files touched by several clusters (expect merge conflicts):
- runtime/release.py (23 patch hunks' files)
- swarm/orchestrate.py
- runtime/worker.py
- runtime/pipeline.py
- agents/registry.py
- intel/mission_runtime.py
- app/main.py
- ops/retention.py
- creative/ideation.py
- core/models.py

The lead has changed these files since 9d6eed2 (in b90e7e1), so merges must keep the changes:
- runtime/release.py: collection assembly, `enqueue_member_collections`
- runtime/pipeline.py: gate.certify triggers collections
- build2/executor.py: rendered_pages is (35, 39)
- tests/test_executor.py
- tests/test_cert_wiring.py
- tests/test_cert_growth_seasonal.py

## 6. Exactly what the next session does

1. `git fetch origin claude/visual-investigation` and check out that branch. Read this file,
   `closure_state.json` and the C-60 to C-73 rows of `research/BUILD2_CERTIFICATION.md`.
   Do not re-run the 9434c53 audit.
2. For each cluster:
   - if its agent reported in the old session and a report exists, use it;
   - otherwise recover its work from `patches/` onto a branch from 9d6eed2;
   - relaunch an agent only for rows its patch series does not already cover, with the same
     brief and row list, instructed to continue from the recovered branch (not restart);
   - have that agent run its focused tests and produce the per-row JSON report.
3. Integration order:
   1. **platform**: owns closure.py/reachability.py; fix C-65 first so every later row is judged
      under the stricter rule.
   2. **orders**: Order/Customer columns that growth reads.
   3. **growth**
   4. **design**
   5. **improve**
   6. **intel**: gate reclassification last, so the executor tests are settled once.

   Merge each into `claude/visual-investigation`. Keep the lead's b90e7e1 changes. Run that
   cluster's tests plus the standard files after each merge:
   - test_closure
   - test_platform
   - test_cert_orchestration
   - test_capability_gates
   - test_executor
   - test_cert_wiring

   Commit and push after each merge.
4. Update the registry from each agent's JSON report with `regupd.py` semantics:
   - append a note;
   - set status, proof and parked_on;
   - never mark a row covered without a handler-level proof test.

   Recompute closure. The effective OPEN count must count the C-65 twenty.
5. Mark each ledger C-60 to C-72 repair cell FIXED only with the commit and the test that proves it.
6. Repeat repair waves until closure shows zero executable OPEN rows. Any remaining gate must be a
   real owner, data or external gate whose built half runs on cadence.
7. Run the focused cert suites, then a fresh full suite
   (`PY=/home/user/Project-Money/brambleloop/.venv/bin/python bash run_tests.sh`) on a clean
   checkout of the final head.
8. Run a fresh independent 320-row function-level audit: four auditors of 80 rows each, the same
   method as the 9434c53 audit, looking specifically for:
   - code reached only by tests;
   - static routes;
   - constant inputs;
   - outputs nothing reads.

   Reopen and repair anything it finds, then repeat.
9. Only then:
   - reconcile the registry, the ledger, BUILD_STATE, DECISION_LOG and the dashboard;
   - write the A–U certification report;
   - leave a clean tree and push.

## 7. Integrity confirmation

- **No certification criterion, threshold, gate, validator, Product Truth check, provenance rule
  or test was weakened in this run.**
- Test changes made by the lead, all tightening or correcting the measured unit:
  - **test_cert_wiring:** the disclosure check is asserted for every product whose SEO ran,
    instead of comparing job counts with distinct releases.
  - **test_executor:** the rendered_pages membership moved from [39] to [35, 39], with a stated
    reason, and exact-membership checking is kept.
  - **test_cert_growth_seasonal:** the collection test is now stricter. It checks for no spin,
    band priority, keyed triggers and assembly on certification.
- No honest reopening was reverted.
- The registry distinguishes code that exists, tests that exist, runtime wiring, and
  COMPLETE+PROVEN. Only COMPLETE+PROVEN counts as done.
