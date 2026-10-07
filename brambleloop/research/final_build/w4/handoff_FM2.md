# handoff FM2 (wave 4) — Final Master continuation

Branch `claude/w4-FM2`, worktree `.claude/worktrees/W4-FM2`. TMPDIR=/home/user/bl-tmp-FM2.
Owned: every launch-critical OPEN row in `w4/FM2_OPEN.json` with owning_lane FM2.
Excluded: K5a/K5b -> SPEND, K9 -> K9, F-030/F-254 -> VISUAL, F-914 -> CC, F-416 -> integrator,
PROCESS -> end stage (frozen RC). Overlay: `w4/close_fm2.py` (--plan / --run-tests / --apply).

## Status per row (launch-critical OPEN at 764e334: 63, FM2-owned 12)
| row | status | evidence |
|---|---|---|
| F-233 | COMPLETE (code: trust.shop_complete_problems reads store_foundation.storefront_gate; readiness 'storefront') | tests/test_w4_fm2_storefront_trust.py |
| F-263 | COMPLETE (ads_plan: search certificate prerequisite + real shop gate + F-297 measurement) | same + test_cert_growth_ops |
| F-159 | code done: ops/log_secret_guard (runtime log redaction, entrypoints) | tests/test_w4_fm2_log_secret_guard.py |
| F-514@v0.16 | code done: OpenAPI classification re-verification; OPEN until AUTO cadence wiring | tests/test_w4_fm2_surface_reverify.py |
| F-213 / F-219 / F-677 | COMPLETE by remap to wave-3 K12 visual/identity_gate + final_image_gate (consumer visual/rnd/loop) | tests/test_w3_k12_model_photography.py |
| F-732 | GATED external model_bearing_render (no qualified face embedder; F-852 refuses model renders) | same |
| F-518@v0.15 | GATED owner production_window (rollback plan live; execute needs write grant) | tests/test_k8_listing_estate.py |
| F-926 | GATED owner store_preview_v2_review (v11_map.py) | test_w3_store_ux_* |
| F-834 | END-STAGE: needs real runtime packets on a frozen RC + independent reviewer (s92 consumer check exists) | - |
| F-123 | in progress: view-name root-stripping fixed (+ regression case); BASELINE 109 shrink pending | tests/test_vacuity.py |

## WIRING REQUESTS
1. **W4-AUTO** `runtime/worker.py` CADENCES: `("etsy_openapi_reverify", "orchestrator", "etsy.openapi_reverify", 7 * 24 * 60 * 60)`;
   `agents/registry.py` orchestrator allow-list: add `"etsy.openapi_reverify"` (GREEN, read-only public GET of
   Etsy's OpenAPI document, CA$0). Closes F-514@v0.16.

## Tests run (sequential, this branch)
test_w4_fm2_storefront_trust 6/6, test_trust 12/12, test_cert_growth_ops, test_v11_ads_readiness, test_launch 28/28
(run in parts), test_w4_fm2_surface_reverify 8/8, test_w4_fm2_log_secret_guard 8/8, test_etsy_surfaces, test_k8_shop_cx 17,
test_oauth_security_audit 87, test_reachability, test_vacuity, test_secret_scan, test_w3_tmp_hygiene.
Note: test_launch's opening-grid expectation was stale on the integration head (CREATIVE survivors clear
products now); it now reads the grid's own verdict and asserts visible tiles are launch-cleared.

## Next
1. `python3 research/final_build/w4/close_fm2.py --run-tests && --apply`; `v11_map.py`; `aggregate.py`; `fm2_open.py`.
2. F-123: shrink BASELINE (counter-guard insertion per loop, run each file).
