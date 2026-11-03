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

The measured first-rule improvement is the number of existing finishing actions
presented as checklist items; the successor measures an added end-security
instruction. These deterministic output measurements are not maker studies or
evidence of a real-world quality outcome. Main must independently decide whether
the formatting metric meets the owner's genuine-improvement standard; the
unmeasured image and real-outcome stages cannot support construction rules.

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

* Analysis and evaluation run without an interactive session, but independent
  observation review and rule approval currently require an owner session.
  Main has been asked whether a separately implemented, capability-scoped
  reviewer may review observations and what independent evidence it must use.
  Rule approval remains owner-authorized; replaying the same parser under a
  different role is not independent review.
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

## Recent checkpoint verification

On the code at `1bc6f47` (subsequent changes to this handoff are documentation
only), the following ran individually using Python 3.12 and SQLite: worker
8/8, knowledge contract 4/4, retention guard 5/5, improve regression 24/24,
autonomy timeline 6/6, design-evaluation cases 7/7, finding review Command
Center 5/5, analysis store 1/1, purchase intake API 1/1, teardown reader
12/12, originality 28/28, compiler 9/9, twin 8/8, and reverse 18/18. An
older SQLite database copy migrated the new nullable audit link successfully.
These focused results do not represent the complete integration certification;
the work order's Python 3.11 environment and full remaining regression set must
be verified by the integrator.

After that checkpoint, `test_codex_learning_http_e2e.py` passed against a
persistent SQLite database: the real intake HTTP route queued a synthetic PDF;
the worker analysed it; owner-session HTTP actions reviewed the observation
and approved a proposed rule after a durable held-out evaluation; the approved
pin changed original finishing instructions; a mutated evaluation was detected
as a regression. Separate worker tests cover interruption after the purchase
state update and recovery without duplicate analysis or audit. This proves the
finishing-rule path, not an approved construction change. The current-head
shadow suite remains incomplete: three cases passed before the run was paused
to complete this acceptance test.

At `7419ffa`, the intake-to-approval HTTP test, worker (10/10), knowledge
contract (4/4), owner review actions (5/5), frozen evaluation cases (7/7),
retention guard (5/5), and learning-loop regression (13/13) passed. Analysis
review, proposal, pin verification and partial audit now require the source
hash to remain manifested as a PDF. This change alters the evaluator's
implementation digest: previous evaluation pins require re-evaluation.
Unreviewed architecture evidence is tracked as a separate gap rather than a
product defect. Recovery also covers a worker failure after a purchase was
marked analysed. A complete independent review and full shadow regression are
still required.
