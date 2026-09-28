# Opus handoff — Build 2 assist 01

Independent verification only. No application repair, requirement-status change or certification decision.

## Immediate finding: reported Orders hardening is absent from remote source

Verified remote Claude head: **2e66b3a44cf87fb6d99d10f136148899b4177877**. Codex branch **codex/build2-assist-01** retains base **4edacff1f8b445a84749464dc1d7271e6c71173e**; a separate detached checkout supplied the newer source for tests.

C-78 and commit b9f7e3a report Orders2/3081402 integrated and test_cert_orders 23/23. Actual source contradicts that claim:
- Ten critical application files and test_cert_orders.py have identical Git blobs at 4edacff and 2e66b3a.
- The claimed receipt_state/refund reconciliation, transactional session threading, historical version resolution and negative-contribution fixes are absent.
- b9f7e3a changes seven documentation/registry/gate/retention/closure-test files, not those Orders implementations.
- Fresh execution against the detached 2e66b3a source reproduces **9 receipt failures, 2 controls pass, 0 errors**.

This establishes a **remote source/evidence mismatch**, not why it happened. A single-parent commit alone is not proof of a bad integration; missing code, identical blobs and failing runtime assertions are the evidence. Candidate work may exist in Claude's unpushed worktree or preserved patch. Opus should reconcile the actual 3081402 tree and remote implementation before consuming C-78 as fixed.

Evidence: [remote synchronization and blob comparison](out/remote_sync.json), [latest corrected-fixture receipt run](out/receipt_adversarial_2e66b3a_v2.json), [reproduction script](test_receipt_adversarial.py). The saved orders2 report and uncommitted diff remain in Claude's b2_resume directory; Codex did not apply them.

## Reconciliation and collisions

All 75 canonical audit findings from e6c3976 are classified in [RECONCILIATION.md](RECONCILIATION.md) / [JSON](RECONCILIATION.json): **4 FIXED; 39 STILL PRESENT; 30 CHANGED — REAUDIT REQUIRED; 2 BLOCKED FROM DETERMINING**. [HIGH_RISK_STATUS.md](HIGH_RISK_STATUS.md) maps the owner's priority list.

Confirmed bounded fixes: P01 reopened-row precedence, P03 live-gate closeout, G01 third-run steering idempotence, G03 scoped-slug rebuild. Fixed findings do not certify their parent requirements.

Current persisted ownership: Platform/Orders original/Growth/Design integrated; Platform2 named as pending C-80 work; Improve d033e02 and Intel 038e873 remain unmerged candidates. C-78 claims Orders2 integrated but source disagrees. Remote Git does not reveal whether Claude repair agents are currently alive. No application scope was proven vacant, so Codex owns only CODEX_SCOPE.md and this new research directory. Do not cherry-pick a hypothetical application repair from this lane.

## Fresh adversarial results

| Case | Observed result at 2e66b3a | Required behavior |
|---|---|---|
| Late full refund | Order remains $12; ledger refund $0 | Reconcile the existing transaction and money |
| $2 partial refund on $12 sale | Revenue $0; ledger refund $12 | Retain $10 net sale and $2 refund |
| Old modified receipt | Creation watermark skips the 60-day-old refund | Discover modifications to historical receipts |
| Unpaid/open and canceled receipts | Each creates $12 sales revenue | Explicit non-sale handling |
| Historical sale version | A 60-day-old sale receives 2-day-old version 2.0.0 | Historical version evidence or UNKNOWN |
| Out-of-order history | Customer first_seen uses newer arrival | Earliest qualifying purchase, order-independent |
| Interrupted transaction/retry | Order=1, version=0, ledger=1 | Atomic or recoverably complete state |
| Negative contribution | Order $0 versus ledger -$0.27 | Preserve losses and money provenance |
| G02 single fast-lane steer | Priority 25→5, queue claims rebuild before waiting support at 10 | Respect customer/truth protection at actual claim |

Receipt positive controls prove duplicate paid ingestion creates one logical sale and a closed gate never reads the fake feed. Default paid receipt now occurs one day ago after the known listing version two days ago; explicit old-history tests remain 60 days old. Earlier raw runs used a 10-day default, which was unsuitable for positive version/recovery controls once historical attribution is repaired. Correcting that fixture did not change assertions or the 9-failure outcome.

G02 proof is [growth_followups_2e66b3a_claim.json](out/growth_followups_2e66b3a_claim.json). The actual durable queue selected chain.rebuild while support.reply remained waiting. No handler for either claimed/synthetic action was executed; no message was sent. Idempotence is independently fixed but the single-step band violation remains.

## Test and closure qualifications

Fresh latest-head controls:
- Receipt suite: 11 tests, 9 FAIL / 2 PASS / 0 errors.
- C-74: 63 PASS (20 reopened rows × 3 gate states, plus 3 zero-OPEN/live-read controls).
- One existing Growth stats/API route test: PASS after permitting only Windows stdlib socketpair's loopback handshake. External/application network remains denied.
- G02 band/actual queue-claim assertion: FAIL.

Historical focused suites at 4edacff, preserved separately:
- Dependencies, takeover, trend evidence and moat suites exit 0.
- Orders: 13 pass / 1 reachability failure.
- Growth: 12 pass / 1 harness failure; the exact route test subsequently passes at latest head.
- Closure: fails/aborts; do not present the saved suite as green.
- No full current-head suite or actual production gate read.

On Windows, reachability._rel_of returns backslashes while cadence discovery compares against runtime/worker.py. Native latest closure calculation (without DB): **135 COMPLETE+PROVEN / 118 OPEN / 37 OWNER-GATED / 26 DATA-GATED / 4 EXTERNAL-BLOCKED**. Diagnostic-only in-memory slash normalization: **159 / 83 / 41 / 33 / 4** in that order. Both are indeterminate, gates unchecked and closed_out=false. No application source was patched.

The latest ledger/commit claims **176 COMPLETE+PROVEN / 66 OPEN**. This was not reproduced. The native path discrepancy explains part of the difference; residual difference is unresolved. A Linux/current-head exact-source run and proof-row comparison are needed. Do not change requirement states to make these totals agree.

## Runtime chain and integration order

See [RUNTIME_TRACES.md](RUNTIME_TRACES.md) for producer → state → consumer → action paths and proof limits.

Recommended Opus sequence:
1. Reconcile C-78's claimed Orders2 code with actual remote blobs. Reuse completed candidate work if valid; do not rewrite the same repair merely because it was not pushed.
2. Run the corrected receipt tests against that actual integrated tree. Require reconciliation, historical attribution and interruption/retry assertions to pass without weakening them; then run the real Orders/commerce/finance consumers and affected suites.
3. Give G02's actual queue-order reproduction to the current Growth/Platform owner. Enforce a shared priority policy at composition/claim; do not adjust the customer/truth threshold.
4. Let Platform2 own the C-80/P05–P13 application repairs. Preserve P01/P03 fixes and rerun exact-source closure on the production OS; counters alone cannot certify output semantics.
5. Re-audit integrated Design's exact gap provenance (D03), release-bound stages (D04), funnel payload binding (D08) and new judgement hash binding (D01).
6. After actual Improve/Intel integration, execute the already-written original adversarial specs. Missing replay/photo/strength code is unresolved, not a PASS.

## Delivery and boundaries

Checkpoint already pushed: 3860881e61cc0c621b7c30fac508b1450a5ac220 (initial evidence). Follow-up commit(s) containing this handoff, latest-source evidence and reconciliation are identifiable by git log -- CODEX_SCOPE.md brambleloop/research/codex_build2_assist_01.

Only new Codex scope/research files change. The branch intentionally stays based on 4edacff; tests explicitly select 2e66b3a. Use the verification commits as evidence, not an application integration. No merge, rebase onto Claude, deploy, Etsy operation, advertising, paid API, production write or secret access occurred. Spend $0. Visual branch remains 035ff0c62a42dd5fd0b616998dcf98833b5c1097. Opus alone decides integration and COMPLETE+PROVEN.
