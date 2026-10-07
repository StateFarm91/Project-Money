# handoff FM2 (wave 4) — Final Master continuation

Branch `claude/w4-FM2`, worktree `.claude/worktrees/W4-FM2`. TMPDIR=/home/user/bl-tmp-FM2.
Latest pushed SHA: `git log origin/claude/w4-FM2 -1`. Merged origin/claude/visual-investigation at 4839486.
Overlay: `w4/close_fm2.py` (--plan / --run-tests / --apply) + `w4/fold_lanes_fm2.py` (merged lane claims).

## Launch-critical OPEN: 63 (wave-4 start) -> 17 (integrator WIP 9340fa4) -> 16 (8df5a87) -> 15 with F-123
Folded (all cited tests green in this lane's sequential run, `w4/close_fm2_test_results.json`):
- K9 (18): 17 COMPLETE + F-363 GATED owner physical_proof.
- SPEND K5b: F-312/313/314/316/317/472/328/309/318 COMPLETE. F-098/F-310/F-659 OPEN -> AUTO wiring (handoff_SPEND AUTO-1..3).
- SPENDA K5a: F-070/304/319/322/629/311 COMPLETE; F-325 GATED data live_listings; F-106/F-103 GATED owner provider_usage_api.
- F-914 COMPLETE (v11_map.py; CC ?period= reaches dashboard.summary(window=), test_w4_cc_company).
- F-416 COMPLETE at INTEGRATED: producer ops/release_record.apply_at_import (requirements.lock is in the boot-guard tree
  digest; an unrecorded lock forces SHADOW at app import) + scripts/supply_chain verify --strict (integrator's digest/apt pin).
  tests/test_w4_fm2_lock_boot_guard.py 3/3. OVERRIDES_PROPOSED_FM2.json withdrawn (empty).
- F-030/F-254 refreshed, stay OPEN: CONTENTS certified on coasters/ornaments/graphghan; missing on blanket + baskets
  (VISUAL2: re-run w4/visual/proof_contents_gallery.py for them); LIFESTYLE owner-gated VB-1.
- Earlier: F-233, F-263, F-159, F-213/219/677 COMPLETE; F-732, F-518, F-926 GATED.

## Own rows
| row | status |
|---|---|
| F-123 | BASELINE 109 -> 0 (last 6 loops guarded in test_launch, test_product_run, test_cert_claude_independence); remap pending suite runs |
| F-514@v0.16 | OPEN until W4-AUTO's etsy.openapi_reverify cadence (on origin/claude/w4-AUTO, unmerged) reaches the integration head |
| F-834 | END-STAGE (runtime packets on frozen RC + independent reviewer) |

## WIRING REQUESTS
1. W4-AUTO: merge `etsy_openapi_reverify` CADENCE + registry allow-list (already on claude/w4-AUTO) -> closes F-514@v0.16.
2. W4-AUTO: SPEND AUTO-1/2/3 (F-098, F-310, F-659).

## Next
1. Finish F-123: run tests/test_product_run.py, tests/test_launch.py, tests/test_cert_claude_independence.py (one at a time);
   if green, `close_fm2.py --run-tests <those> && --apply`, aggregate.py, fm2_open.py, commit, push.
