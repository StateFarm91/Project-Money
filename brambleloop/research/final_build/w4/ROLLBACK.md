# W4-ROLLBACK: every forward deploy proves its way back first (F-380 / F-381)

Branch `claude/w4-ROLLBACK`, based on `origin/claude/w4-INTEG2` 083c9fc. No production change and
no push to the production branch.

## The gap the board names, and what closes it

F-381 needs every material deployment to preserve a known-good predecessor and an executable
rollback path. F-380 needs deploy evidence, rollback capability and post-deploy observation.

Already in place before this branch:

| control | where |
|---|---|
| guard on a tracked release record | `deploy_guard check` |
| post-push deploy confirmation | `verify_deploy.py` |
| per-feature readback | `readback.py`, W4-SMOKE |
| sanctioned rollback door | `rollback-commit`, plus `ROLLBACK_RUNBOOK.md` |
| boot verdict rows | runtime |
| `known_good_predecessor` | runtime |

What was missing: nothing proved, before a deploy, that its rollback would be accepted. In
particular, nothing proved that the candidate still records the commit it replaces in
`DEPLOYED_HISTORY.json`. If that entry is missing, the way back is refused at the worst moment.

**New:**

- **`ops/deploy_guard.py rehearse-rollback --candidate X --deployed D`**:
  - Builds the rollback commit from X back to D as an unreferenced, never-pushed object.
  - Checks it with the same `check` a real rollback gets: D is in X's tracked history, the
    commit carries exactly D's tree, and it sits on top of X.
  - Prints the verdict and exits 0 or 1.
- **`ops/deploy.sh`**: after the guard's ALLOW and before its only push, every forward deploy
  runs the rehearsal. A REFUSE pushes nothing (exit 1) and says to append the deployed sha to
  `DEPLOYED_HISTORY.json`. Rollback deploys are exempt; they are the rollback.

## Acceptance evidence (tests through the shared slot)

**`tests/test_w4_rollback_rehearsal.py`: 5/5.** It covers:

- A candidate that preserves its predecessor gives ALLOW, and the rehearsal object is not
  referenced by any branch or tag.
- A candidate that drops its predecessor from history gives REFUSE, naming the history.
- An unknown or foreign deployed commit gives REFUSE, never an assumption.
- The CLI exit code follows the verdict.
- In `deploy.sh`, the rehearsal runs after the guard and before the only push.

**Regression:**

| test | result |
|---|---|
| `test_deploy_path` | 10/10 (the "only one push" rule still holds) |
| `test_deploy_verify` | 10/10 |
| `test_rc1_own_release` | 10/10 |
| `test_deploy_guard` | 7/7 |
| `test_w4_smoke` | 10/10 |

**Real history, scratch clone, nothing pushed** (`evidence_ROLLBACK/`): rolling back from the
integration head 083c9fc to production 0417f35 gives ALLOW. Rolling back from the release
candidate c498888 to 0417f35 also gives ALLOW. Both carry 0417f35 in `DEPLOYED_HISTORY`.

## Rows

- **F-381:** advanced. The executable rollback path is now proven before every deploy. The row
  stays on data `production_window`, which needs the deployed release plus 24 h.
- **F-380:** advanced. Every deploy is now guarded, observed (readback) and rollback-rehearsed.
  The same window remains.

## F-834 decision memo (requested by the coordinator)

**The rule.** `build2/final_proof.py::_validate` gives a packet one run identity (`packet.head`,
`packet.run_id`). Its `receipt()` requires every receipt to carry that same head and run id:
the six chain stages, `live_root`, `production_producer`, `failure_test`, `suite` and
`independent_review`. Otherwise it records "stale or unrelated receipt".

**Why no honest packet can pass.** The evidence the row needs comes from three different runs:

1. The runtime chain comes from a rehearsal or production run.
2. The full suite is a `run_tests.sh` run. Its head is the suite SHA (5dfd1ac), which is bound
   to the deployed record-only commit (0417f35) by the deploy guard's tree-digest rule.
3. The independent review is a separate session, by definition.

Giving all of them one `run_id` means relabelling two runs' receipts with a third run's id.
That is fabrication. So F-834 cannot leave BLOCKED by any emitter change.

**Options.**

- **(1) Keep the rule.** F-834 then stays OPEN for ever. This is a gate that cannot open.
- **(2) Scope the run identity to the runtime chain.** Keep head+run_id equality for the chain
  stages, `live_root` and `production_producer`. Bind the other three by artifact digest plus
  their own declared identity:
  - **suite:** its own `run_id`, and `head` equal to the packet head or to a commit whose
    deployable-tree digest equals the packet head's (the deploy guard's existing rule).
  - **failure_test:** its own run.
  - **independent_review:** its own reviewer and run, bound to the packet by digest.

  Every receipt still has to be bound, observed, digest-checked and on the same deployable
  tree. Self-review stays refused.
- **(3) Fold the suite and the review into the rehearsal run.** This is impractical. A 78-minute
  full suite and an independent session cannot happen inside one rehearsal.

**Recommendation: option (2).** It is a technical correction of an unsatisfiable condition, not
a change to F-834's acceptance criterion ("prove the consumer"). Every proof obligation is kept,
and only the requirement that unrelated runs share one id is removed. It does change an
adjudicator (`final_proof`), so it needs your explicit approval, plus its own regression tests:

- The existing `tests/test_final_proof.py` mutations must all still block.
- A packet whose suite is bound by tree digest passes the suite check.
- A suite for a different tree is refused.

Not implemented on this branch: no worker may relax an adjudicator rule unilaterally.
