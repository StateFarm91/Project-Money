# Codex Build 2 assist 01

Read [OPUS_HANDOFF.md](OPUS_HANDOFF.md) first. Durable continuation: [CURRENT_STATE.md](CURRENT_STATE.md) and [NEXT_SESSION.md](NEXT_SESSION.md). Scope: [CODEX_SCOPE.md](../../../CODEX_SCOPE.md).

- [75-finding reconciliation](RECONCILIATION.md), with machine-readable [full evidence map](RECONCILIATION.json).
- [Priority-area map](HIGH_RISK_STATUS.md).
- [Runtime traces](RUNTIME_TRACES.md).
- [Remote source/claim mismatch](out/remote_sync.json).
- Raw results under out/. Names ending 2e66b3a target that exact detached source; unsuffixed originals target 4edacff.
- Receipt result ending _v2 is authoritative: corrected positive-control chronology, same assertions and same 9 failures.
- artifact_manifest.json preserves hashes of this evidence package; verify_package.py checks the saved package without rerunning experiments.

## Reproduce only when source changes or a defect is repaired

Use Python with local SQLAlchemy, FastAPI and httpx. On this host the bundled interpreter is C:/Users/Jacob McKenna/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe and free dependencies are in ../runtime-build2 (SQLAlchemy 2.1.1, FastAPI 0.141.1, httpx 0.28.1; Starlette 1.7.0). No pytest is required. Scripts use temporary SQLite and block application network.

From the Codex repository root, with python referring to that interpreter:

    python brambleloop/research/codex_build2_assist_01/test_receipt_adversarial.py --deps ../runtime-build2 --source-root ../build2-verify-2e66b3a/brambleloop --source-sha 2e66b3a44cf87fb6d99d10f136148899b4177877 --suffix _new_run
    python brambleloop/research/codex_build2_assist_01/growth_followups.py --deps ../runtime-build2 --source-root ../build2-verify-2e66b3a/brambleloop --source-sha 2e66b3a44cf87fb6d99d10f136148899b4177877 --suffix _new_run --only bands
    python brambleloop/research/codex_build2_assist_01/verify_closure.py --deps ../runtime-build2 --source-root ../build2-verify-2e66b3a/brambleloop --source-sha 2e66b3a44cf87fb6d99d10f136148899b4177877 --suffix _new_run

The receipt and band scripts intentionally exit 1 while defects persist; no xfail or pass relabeling. Select a new suffix so saved evidence is not overwritten. --source-sha labels results: verify source checkout HEAD and cleanliness before choosing it. No automated script installs dependencies or contacts providers. Existing run_focused.py remains pinned to original 4ed source; it is not a current-head full-suite proof.

The narrow route follow-up permits only stdlib socketpair's loopback handshake required by Windows asyncio. It does not allow application HTTP/TCP connections.

Public fixture references: [Etsy API reference](https://developer.etsy.com/documentation/reference), [Etsy definitions](https://developers.etsy.com/documentation/essentials/definitions/). Public documentation lookup only; no account/API calls.

## Interpretation

4 FIXED / 39 STILL PRESENT / 30 CHANGED — REAUDIT REQUIRED / 2 BLOCKED FROM DETERMINING are independent finding classifications, not requirement statuses. No COMPLETE+PROVEN determination. No application code repair delivered.

First checkpoint 3860881 preserved raw output text through Git newline normalization; final evidence restores original byte-identical logs using explicit -text attributes. Recorded output hashes are verified against the committed bytes at final checkpoint.
