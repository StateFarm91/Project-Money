# handoff FM2 (wave 4) — Final Master continuation

Branch `claude/w4-FM2`, worktree `.claude/worktrees/W4-FM2`. TMPDIR=/home/user/bl-tmp-FM2.
Owned: every launch-critical OPEN row in `w4/FM2_OPEN.json` with owning_lane FM2.
Excluded: K5a/K5b -> SPEND, K9 -> K9, F-030/F-254 -> VISUAL, F-914 -> CC, F-416 -> integrator,
PROCESS -> end stage (frozen RC).

## Status per row (launch-critical OPEN at 764e334: 63, FM2-owned 12)
| row | status | evidence |
|---|---|---|
| F-233 | code done (storefront_gate in trust.shop_complete + readiness 'storefront') | tests/test_w4_fm2_storefront_trust.py (6) |
| F-263 | code done (search certificate prerequisite in ads_plan; shop_complete fixed) | same |
| others | pending | |

## Tests run (sequential)
test_w4_fm2_storefront_trust 6/6, test_trust 12/12, test_cert_growth_ops, test_v11_ads_readiness.

## Next
1. Fold F-233/F-263 via w4/close_fm2.py --apply; regenerate (v11_map.py, aggregate.py, fm2_open.py).
2. F-514 etsy_surfaces reverify; then F-159, F-213/F-219/F-732, F-677, F-518, F-834, F-123, F-926.
