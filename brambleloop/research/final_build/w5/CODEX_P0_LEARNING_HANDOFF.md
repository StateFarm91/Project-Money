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
The implemented rules change finishing instructions to a checklist and, when
independently supported by two distinct sources, add an end-security check. Worker
and persistent-database tests exercise the intake-to-writer path, retries,
recovery and source invalidation.

The analysis worker also records a partial PDF-architecture audit from the
closed-vocabulary observations. Withheld elements stay unknown, no finding is
created automatically, and the event contains no source prose. The linked
audit is protected from retention and reused on retry. Legacy analyses without
architecture data cannot be prefilled.

Legacy and shared-token findings whose recorder is not established remain
visible and non-binding, but unmet or unmeasured requirements retain a release
hold. The owner can attest a legacy recorder through a
step-up action; that attestation is an assertion, not cryptographic proof of a
third party's identity. All owner sessions are the same principal and cannot
review the owner's own finding. An owner-authored unmet finding remains a hold
until the concern is met or an independently authenticated reviewer is available.

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
* The current store supports one composite active rule version. Independent
  reviewed sources can generate and evaluate an improved successor and the
  owner can approve an atomic replacement. Multiple independently scoped active
  rules are not implemented; existing CIRs pinned to retired versions fail
  verification and need an integration policy.
* Main decision `I-SUPPORT-LEARNING-CONSENT` prohibits feeding private support
  case text into Learning until a consent and revocation design is approved.
  The orphan support text producers therefore remain unwired; aggregate
  nonidentifying defect counts remain permitted.
* Partial architecture prefill is not a complete scored audit: unsupported
  elements remain withheld and require a separately authenticated observer.
* Main's independent delta review, final regression results, PR review,
  integration, certification and production verification remain outstanding.

No deployment, purchase, paid-provider call, publication or shared-branch
merge is authorized by this handoff.
