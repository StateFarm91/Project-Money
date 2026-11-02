# Codex: integrator review feedback on P0-LEARNING-REFERENCE

The integrator (Main Opus) maintains this file. Codex reads it with
`CODEX_WO_P0_LEARNING_REFERENCE.md` before each work session. Newest entries are first.
Codex has no PR, so this file is the review channel.

## 2026-11-02T19:58Z: mandatory dispatch protocol (decision `I-DISPATCH-PROTOCOL`)
Your assignment is now **CODEX1-FIX** (P1) in `COORDINATION.json`. It covers CODEX1-2 and confirming CODEX1-1,
then the approved-rule reader that A6 consumes. Its ack is due by the `ack_due_by` in its `dispatch` record. Read `dispatch/README.md` on
`claude/w4-INTEG8-next`.

On every work session:
```
git fetch origin claude/w4-INTEG8-next && git checkout origin/claude/w4-INTEG8-next -- COORDINATION.json dispatch ops/assignments.py
python3 ops/assignments.py event codex CODEX1-FIX ack --push   # first time only
python3 ops/assignments.py event codex CODEX1-FIX checkpoint --sha <sha> --push
python3 ops/assignments.py event codex CODEX1-FIX review_requested --sha <sha> --push
```
A dated line in this file still works, but the `review_requested` event is what the integrator polls for.

## 2026-11-02T18:52Z: owner directive, binding: complete autonomous workforce first

The owner has made completing and activating the whole autonomous workforce the company's top priority. The decision is
`I-P0-ABSOLUTE-WORKFORCE` in `COORDINATION.json`. You keep the Learning Department (P0-LEARNING-REFERENCE). Work in this order:

1. **CODEX1-2 HIGH is still open at `d0e80fe3`.** `teardown.analyse` and `teardown.analyse_sweep` are not in
   `authority/classes.JOB_CLASS`, and `test_w3_k11_authority` fails. Fix this first.
2. **CODEX1-1 HIGH.** `f4feaaa0` looks like the fix. Confirm that `LibraryRefused` is caught wherever
   `ReferenceRefused` is caught, and that a root containing the app tree is refused. Run `test_image_reference_hash_failclosed`,
   `test_originality` and `test_w3_k11_authority`.
3. **CODEX1-3 MED.** `bd215b08` addresses it. It will be checked in the delta review.
4. **Then the approved-rule reader.** Learning has to reach design. Expose only **approved** design rules where
   `improve/consume.matching(..., "pattern_engineering", ...)` can read them, with `consume.act` recording.
   opus2's A6 consumes this, and nothing else in the department matters more.
5. **After that:** the review state and audited approval, the held-out evaluation, and the gap-detection
   items from CODEX1-4.

When 1 and 2 are pushed, add a dated line to this file asking for a delta review. The integrator reviews only commits
after 623fc26c. Push small, reviewable commits, and branch from or merge the newest `claude/w5-INTEG1`.
Do not start optional enhancements.

## 2026-11-02T17:45Z: review CODEX1 of `codex/p0-learning-reference` 623fc26c: DO NOT SHIP

**Full report:** `brambleloop/research/final_build/w4/INDEPENDENT_SECREVIEW_CODEX1.md` on branch
`claude/w5-SECREVIEW-CODEX1`. Both HIGH findings are regressions that were reproduced against
base 88982f20, which passes the same suites.

### Sound
- **IP isolation.** Analysis rows hold only fixed vocabulary, counts, pages and file hashes, and nothing reads
  `BenchmarkAnalysis` or `DesignRule` into a CIR, PDF, listing or image prompt.
- **Library location.** `.dockerignore` and `.gitignore` keep the library out.
- **Rule state.** Rules are written only as "proposed".
- **Idempotency.** Writes are idempotent, keyed by file hash under a unique constraint.
- **No spend or vendor calls.** No opus2 files are touched and no assertion is removed.
- **New tables.** `design_rules` and `benchmark_analyses` are additive (create_all), so rollback is safe.

### Required before integration
1. **CODEX1-1 HIGH: the library guard refuses the default location.** In the container, `WORKDIR /app` and
   the code is under `/app/src`, so the default `benchmark_library` is inside the app tree and `library_root()`
   refuses it.
   - With `BRAMBLELOOP_BENCHMARK_LIBRARY` unset, `gateway/images.refuse_benchmark_references` raises an
     uncaught `LibraryRefused` on every image request that carries a reference image. It catches only
     `ReferenceRefused`.
   - Teardown intake and `lab.write_manifest` fail, and the intake route returns 500.
   - Regressions: `test_image_reference_hash_failclosed` (3 errors), `test_originality` (27/28),
     `test_w3_k11_authority`.
   - **Fix:**
     - Give the library a default path outside the app tree, or make the variable a documented,
       required config item that fails closed with a named reason. A raw exception is not acceptable.
     - Catch `LibraryRefused` wherever `ReferenceRefused` is caught.
     - Reject a root that *contains* the app tree, such as `/`.
     - Do not weaken those tests.
2. **CODEX1-2 HIGH: authority classes are missing.** Add `teardown.analyse` and `teardown.analyse_sweep` to
   `authority/classes.JOB_CLASS` (F-669, `test_w3_k11_authority`).
3. **CODEX1-3 MED: the independent-review rule can be bypassed.** `design_knowledge.propose` refuses an unreviewed
   finding but accepts any **lesson** as evidence, and `teardown.enforce` publishes unreviewed teardown
   requirements as lessons.
   - **Fix:** follow provenance through lessons back to findings, and refuse unless every root finding
     is independently reviewed.
4. **CODEX1-4 (scope):** most of the work order is still missing. Build these next:
   - `review_state` on findings, plus the audited review action and independent approval;
   - `applicable()` readers, so Product Development and writers can retrieve **approved** rules through
     the existing `improve/consume` interface. opus2's A6 consumes this: expose rules where
     `consume.matching(..., "pattern_engineering", ...)` can read them, with `consume.act` recording;
   - WO-3 before-and-after held-out evaluation;
   - `teardown_state` transitions to analysed and needs_analyst;
   - intake beyond MJ's;
   - knowledge-gap detection;
   - owner-approved purchase recommendations only.
5. **LOW:**
   - Make the sweep report `work_done` with a `WORK_KEYS` entry.
   - Make a licence without `private_analysis` a named refusal rather than a half-success with a 500.
   - On retry, check for an existing analysis before re-reading the PDF.
   - Pin the 4 surviving mutants: `check_derived`, the manifest recheck under lock, the licence check at
     enqueue, and the superseded-rule key.

### Integration notes
- Branch from or merge `claude/w5-INTEG1` (it is ahead of INTEG8-next).
- There are 3 mechanical conflicts:
  - `COORDINATION.json`;
  - `autonomy_map.json` (regenerate it);
  - the `runtime/pipeline.py` import block (keep `commercial_ops`, `learning_gaps_ops`, `evidence_ops`
    and `teardown_ops`).
- Every new job type needs its `JOB_BANDS` entry **and** its `JOB_CLASS` entry in the same commit.
- Any CIR shape change must bump `core.contracts` "cir" (now v2) in the same commit.
