# Build 2 assist — current state

Updated 2026-09-27. Read CODEX_SCOPE.md first. This is an independent verification lane, not a repair or certification lane.

## Identity and boundaries
- Branch: codex/build2-assist-01; worktree: ../build2-assist-01.
- Pinned Claude base / latest fetched remote: 4edacff1f8b445a84749464dc1d7271e6c71173e.
- Canonical 75-finding audit: e6c397656d42406d9da338264f15bb36fadab5cf, brambleloop/research/codex_b2_integration_pack/FINDINGS.json.
- Visual remains frozen at 035ff0c62a42dd5fd0b616998dcf98833b5c1097 on codex/visual-v2-rnd.
- No application/shared-test/requirement-status edits. No merges, deployment, production mutations, Etsy, ads, paid APIs or secrets. Paid spend: $0. Opus alone integrates and certifies.

## Synchronization
Actual merges since 0d42f2f: Platform bb32b3a, Orders 9931ebf, Growth 63fe5bd. The resume manifest incorrectly still lists Growth as unmerged. C-74/e5239e6 changes P01/P03. Growth merge contains C-75/G01, C-76/G03 and C-77/referral half of X01 repairs; do not inspect only non-merge commits.

Design f76d277, Improve d033e02 and Intel 038e873 persist as candidate reports/patches, not integrated code. Git cannot prove live Claude agent liveness or vacant application ownership. Thus selected non-overlapping scope is new Codex research tests and evidence only.

Latest certification ledger claims 153 OPEN; old manifest claims 133. Neither is a freshly verified count in this environment. Platform validation and local independence 4/4 logs persist. Orders validation log is partial. No current-head full suite or live production gate read was performed.

## Executed evidence
- out/receipt_adversarial.json: 11 tests, 9 FAIL, 2 PASS, 0 errors. O01 late full refund, partial amount and old-update window; O02 unpaid/canceled; O03 future listing version; O04 first-purchase chronology; O05 post-Order interruption/retry leaves OrderVersion absent; O07 negative contribution clamped. Paid idempotence and closed-gate controls pass. SQLite and synthetic fixtures only. Ledger repairs on O05 retry; sale-version mapping does not. This is deterministic interruption, not an actual worker kill.
- out/source_index.json: all 75 canonical findings indexed against pinned source with hashes, symbol ranges and missing candidate paths. Indexing is not the final status verdict.
- out/focused_suites.json plus full logs: test_cert_dependencies, test_cert_takeover, test_cert_trend_evidence and test_moat exit 0. test_closure aborts after failures / gate_checked KeyError; test_cert_orders 13 pass / 1 fail; test_cert_growth_ops 12 pass / 1 fail.
- Closure and Orders reachability failures expose Windows backslash labels in build2/reachability.py::_rel_of versus literal runtime/worker.py comparisons. Do not report these entire suites as passing.
- Growth failing route test is blocked by harness socket denial intercepting Windows asyncio's local self-pipe; not evidence of an application route failure. Its C-75 repeated-steering and C-76 scoped-rebuild tests independently passed.
- out/closure_checks.json: 63 independent controls PASS (60 reopened-row precedence checks and 3 live-gate-read closeout controls). P01/P03 exact defects are fixed.
- Unmodified Windows closure counts without DB: COMPLETE+PROVEN 88, OWNER-GATED 20, DATA-GATED 21, EXTERNAL-BLOCKED 4, OPEN 187.
- In-memory _rel_of separator normalization diagnostic only: 103,24,24,4,165 respectively. This is not an unmodified suite pass or certification. Both matrices closed_out=false, indeterminate=true, no live gates checked. Residual 165 versus ledger 153 remains unexplained; do not silently report 153 as reproduced.

## Environment / reproductions
Bundled Python: C:/Users/Jacob McKenna/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe.
Missing free test dependencies installed in ../runtime-build2 (SQLAlchemy 2.1.1, FastAPI 0.141.1, httpx 0.28.1); scripts insert that directory, since this bundled runtime ignores PYTHONPATH.
From repository root: python brambleloop/research/codex_build2_assist_01/test_receipt_adversarial.py --deps ../runtime-build2 (expected exit 1 while defects persist).
Other scripts: index_findings.py (read-only Git source index), run_focused.py --deps ../runtime-build2, verify_closure.py --deps ../runtime-build2. Do not rerun the full historical program.

## Active work and exact next actions
1. Finish the 75-finding reconciliation with only the four owner-approved status labels; distinguish absent/unmerged candidate code from integrated defects.
2. Targeted source checks for remaining high-risk contracts. Optionally isolate the one Growth route test using a local-socket-compatible, external-network-denying harness.
3. Explain platform-qualified closure counts and any unresolved discrepancy honestly; no changes to gates or application.
4. Write OPUS_HANDOFF.md, runtime chain, README and NEXT_SESSION.md with raw evidence links and precise remaining uncertainty.
5. Verify only scoped new files changed; refetch once for freshness, record any newer Claude head rather than silently replacing this base. Commit and push clean branch.

No application repair candidate is claimed. Receipt failures are reviewable reproduction evidence for the existing cluster owners.
