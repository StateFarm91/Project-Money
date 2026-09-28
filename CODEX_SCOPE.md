# Codex B owner activation authority scope

Base: 449ce602b7cecd06aa37e38841e3e16a7a4343ed (origin/claude/fb1-B).
Requirements: F-543, F-703, F-835; candidate repair only, no certification/status changes.
Defect: an arbitrary nonempty queued string authorizes public activation.
Owned: runtime/pipeline.py handle_store_activate only; new ops/activation_authority.py;
new app/activation_authority_api.py; new tests/test_activation_authority.py;
existing test_etsy_readback_observe.py successful-approval fixture; this report directory.
Shared app/main registration delegated to coordinator. No other shared models/runtime edits.
Acceptance: unauthenticated/forged/missing/revoked/expired/content-mismatched approvals refuse;
authenticated server-produced approval binds action/listing/release/copy/images/files and time;
worker revalidates persisted record immediately before effect. Local fake Etsy only.
Tests: focused new suite plus existing test_etsy_readback_observe.py. No spend, real network,
production, requirement statuses, Visual V2 edits, or certification claims.
