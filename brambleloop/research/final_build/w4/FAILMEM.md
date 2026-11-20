# W4-FAILMEM — failure memory (F-378, F-427, F-428, F-706)

Branch `claude/w4-FAILMEM` from `origin/claude/w4-INTEG2` 85ec5d0. Domain: autonomy and learning.

## What changed
- New `src/brambleloop/improve/failure_memory.py`, which adds:
  - a `failure_memory` table (`FailureRecord`: fingerprint, cell, method, scope {method, class, conditions},
    premise digest, evidence ids, source, reason);
  - fingerprint = sha256(cell | normalised claim | sorted touches | premise digest). Normalising keeps
    digits, so a claim quoting new measured numbers counts as a new claim;
  - `check()`, `record()`, `listing()`, `generalise()`, and seeds taken from DECISION_LOG dead ends
    (B-650, B-634, B-675, B-686, B-647), each scoped exactly as the log entry justifies.
- `improve/cells.propose` now refuses a proposal that repeats a **measured** failure inside the failure's
  scope, unless the proposal cites evidence ids the failure did not have or states a changed premise.
  New optional arguments: `premise`, `method`, `evidence_ids`, `scope`. They are stored on the Improvement,
  together with `failure_fingerprint`. Existing callers are unchanged.
- What counts as a failure:
  - a REVERTED improvement;
  - a REJECTED improvement with both a baseline and a result;
  - a recorded finding with evidence and scope.

  A refusal, a first measurement ("no baseline") and a withdrawal are not failures. B-686 is the reason:
  a refusal read as "tried" once retired the strongest challenger.
- Scope discipline (F-428): a failure blocks only proposals inside its method, class and conditions.
  `generalise()` refuses to widen a scope without new evidence; narrowing is always allowed.
- Each refused repeat is audited as `improve.repeat_refused`, so "repeated failures avoided" (F-399) is a
  count of rows.
- `core/db.create_all` registers the table. `core/continuity.NON_REDERIVABLE` gains `failure_memory`,
  because it is a record and cannot be re-derived.

## Acceptance evidence
`tests/test_w4_failmem.py` passes 10/10 through testslot. It covers:
- F-706: the same failed improvement proposed months later is refused;
- new evidence or a changed premise reopens the question;
- a refusal or a first measurement is not a failure;
- a REVERTED promotion is remembered;
- digits are kept;
- scope blocks only inside the observed conditions;
- generalisation needs new evidence;
- a record requires evidence and scope;
- the DECISION_LOG seeds are present and enforced;
- the table is non-rederivable.

Existing tests re-run one at a time through testslot, all passing:
- improve: test_improve, test_improve_director, test_improve_handlers, test_cert_improve_wave,
  test_cert_improve_autonomy, test_cert_learning, test_cert_owner_decision;
- learn and measurement: test_v11_learn_loops, test_w4_learn_loops, test_measure, test_profiles,
  test_roi, test_w3_k10_learn, test_w3_k11_authority;
- teardown and product: test_teardown, test_teardown_audits, test_cert_benchmark_challenge,
  test_cert_unique_value, test_r2_product_policy_alias;
- other: test_freshness, test_weekly, test_v11_wiring.

Two existing tests proposed the identical failed improvement twice to exercise their own logic: the
`stop_doing` retrospective and the promotion refusal. That is exactly what F-706 now refuses. Their
**setup** now cites a distinct evidence id for the second attempt (`evidence_ids=("run:{i}",)` and
`("holdout:2",)`), with a comment. Every assertion is unchanged, and the rejection reason they test is
the same.
- tests/test_improve_director.py::test_the_retrospective_names_what_to_stop_and_what_is_next
- tests/test_cert_learning.py::test_failed_or_baseline_less_experiments_cannot_promote

## Board rows advanced
F-378, F-427, F-428 and F-706 move from engineering_open to implemented and tested in this branch. They
become deployed only after integration and release. The failure memory is readable with
`failure_memory.listing(db)`; a Command Center surface is not part of this domain.
