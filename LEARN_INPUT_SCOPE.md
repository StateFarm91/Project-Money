# Learn input validation scope
Base: 5d543ba. Branch: codex/final-learn-input-01. Reuses idle final-chain-fixtures-01 worktree; prior fixture work pushed through2f35469.
Own learn/service.py, new focused malformed-input tests, this scope and handoff only. No API/public site/curriculum/gate/status changes.
Validate input shapes explicitly at service boundary, raising ValueError through save_lesson so existing draft API returns422. Do not hide programming exceptions. Preserve approval/provenance/count semantics. Test null assumptions, malformed asset/step entries, valid draft and unchanged reviewed state after refused update; run existing Learn suites locally. No external calls/spend or production mutations.
