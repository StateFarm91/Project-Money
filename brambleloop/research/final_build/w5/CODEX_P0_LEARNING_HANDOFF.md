# P0 Learning Department — working handoff

Status: **not ready for integration**. This is a working record for Main, not
an acceptance or deployment claim. The source branch is
`codex/p0-learning-reference`; Main selected `claude/w6-INTEG1` as the eventual
integration target. Use the current Git branch head as the exact revision.

The branch extends the existing teardown and improvement systems. It queues
licensed reference analysis from intake, persists structured observations,
requires independent review tied to evidence digests, proposes bounded
knowledge, and tracks observed gaps in the existing incident lifecycle. A
durable evaluation job compares fixed original designs, checks compilation,
twins, reverse compilation, applicable Product Truth and originality checks,
and blocks unknown evidence or regressions. Owner step-up is required for rule
approval; approval and frozen pins are rechecked against current evidence.
The implemented rule changes finishing instructions to a checklist. Worker
and persistent-database tests exercise the intake-to-writer path, retries,
recovery and source invalidation.

The A6 interface and the required certificate, release, quality and PDF hooks
are specified in `CODEX_LEARNING_A6_CONTRACT.md`. The pure writer is not an
authorization boundary: A6 must verify frozen pins and their mapping before
any production use. The legacy lesson-only construction path must not bypass
the evaluated-rule requirement. Main's private library volume decision is
`OA-BENCH-LIBRARY-VOLUME`; absent or unlicensed frozen bench2 evidence blocks
evaluation and pin verification.

Outstanding before a completion claim:

* A6 must integrate the frozen pin contract at draft, revision, certificate,
  release, quality and PDF boundaries and demonstrate a real construction
  change authorized by a passing evaluation.
* The current evaluator compares a single verified incumbent with a proposed
  successor, but cannot atomically approve an improved successor while an
  incumbent is active and does not support multiple active rules.
* The remaining support/community producer wiring and complete audit-prefill
  path need to be completed without inventing consent or treating unknown
  observations as negative findings.
* Main's independent delta review, final regression results, PR review,
  integration, certification and production verification remain outstanding.

No deployment, purchase, paid-provider call, publication or shared-branch
merge is authorized by this handoff.
