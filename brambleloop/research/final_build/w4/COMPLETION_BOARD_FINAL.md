# Completion board (final): Build 2 + Final Master

Generated 2026-11-08T08:34:48Z by `research/final_build/w4/completion_board_final.py` on branch head 4ea4c1cb1. Production runs `b931d17a738d` (read 20261020T0540Z; /api/verify ok=False, failing ['no_unexpected_dead_letters_in_24h']). Rule: verified_complete = the ledger's own acceptance evidence, already complete in the ledger committed at the deployed commit (or closed on committed evidence taken from it), with every named runtime module in the deployed tree; no row is closed by this board.

| scope | total | verified complete | implemented, unverified | in progress | blocked: engineering | blocked: owner | blocked: external | n/a |
|---|---|---|---|---|---|---|---|---|
| Build 2 | 320 | 55 | 174 | 0 | 3 | 36 | 49 | 3 |
| Final Master launch-critical | 490 | 167 | 215 | 0 | 32 | 44 | 32 | 0 |
| Final Master total | 917 | 182 | 263 | 0 | 243 | 129 | 93 | 7 |
| Tracked requirements | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |

## Recount (nine categories, after the spot audit)

| scope | production_verified | dev_proven_not_deployed | implemented_unverified | in_progress | engineering_blocked | owner_blocked | external_blocked | live_customer_C | not_applicable | executable engineering | post-launch empirical | owner/external (non-empirical) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Build 2 | 55 | 166 | 0 | 0 | 2 | 29 | 39 | 26 | 3 | 168 | 57 | 37 |
| Final Master launch-critical | 167 | 212 | 0 | 0 | 32 | 42 | 31 | 6 | 0 | 244 | 11 | 68 |
| Final Master total | 182 | 260 | 0 | 0 | 239 | 123 | 84 | 22 | 7 | 499 | 70 | 159 |

Rule: production_verified = verified_complete after the spot audit (BOARD_AUDIT.json); dev_proven_not_deployed = proven on the branch only; live_customer_C = the criterion's own words demand live customers / post-launch history (prelaunch_scope C_PATTERNS, quoted); post_launch_empirical = live_customer_C plus rows parked on real customers / data accrual; executable_engineering = the rest of the unfinished rows the company itself can move.

Spot audit: 61 rows, verdicts {'PASS_PRODUCTION': 8, 'PASS': 44, 'DOWNGRADE': 9}; downgraded []; re-closed with new tests ['B2#184', 'F-073', 'F-907']. Closed on production evidence of the deployed commit: ['F-152', 'F-240', 'F-299', 'F-473', 'F-491', 'F-535', 'F-570', 'F-574', 'F-657', 'F-682', 'F-793', 'F-878'].

Ledger-native counts: Build 2 {'PROVEN': 229, 'OWNER-GATED': 39, 'DATA-GATED': 41, 'EXTERNAL-GATED': 6, 'NOT-APPLICABLE': 3, 'OPEN-DEFECT': 2}; Final Master launch-critical {'COMPLETE': 382, 'GATED': 106, 'OPEN': 2}.

## Critical path

1. **Release not deployed (successor + 24h window)** (engineering): unblocks 15 rows (12 FM launch-critical, 1 Build 2). Estimate: release cycle + 24h -- suite 4693 s (RELEASE_5dfd1ac run 20261011T083839Z-21062); record 09:56Z -> deployed worker 13:59Z = ~4 h observed; then off_device_proof window_hours 24
2. **Proven only on the integration branch (release + production evidence needed)** (engineering): unblocks 437 rows (215 FM launch-critical, 174 Build 2). Estimate: one release cycle -- same release evidence: ~78 min suite + ~4 h observed record-to-deploy
3. **Gate now OPEN in production: unparked, re-verify** (engineering): unblocks 25 rows (19 FM launch-critical, 0 Build 2). Estimate: one engineering pass over the unparked rows -- gates read OPEN at the board's production GET; each row's own tests/evidence decide
4. **Launch-0 catalogue cap (CAP-1)** (owner): unblocks 1 rows (1 FM launch-critical, 0 Build 2). Estimate: owner ~5 min, then the gate's own reading -- minutes stated per action in OWNER_ACTIONS.json / PRODUCT_FIX.md; no date is promised
5. **No live listings (go-live not authorised)** (owner): unblocks 38 rows (12 FM launch-critical, 9 Build 2). Estimate: owner go-live sitting (OWNER_ACTIONS go_live minutes_total)
6. **No real customers / market outcomes yet** (external): unblocks 95 rows (6 FM launch-critical, 38 Build 2). Estimate: unbounded (market) -- no buyer exists; cannot be scheduled

## Root causes (unfinished rows)

| root cause | rows | B2 | FM LC | FM post-launch | classes | owner action |
|---|---|---|---|---|---|---|
| Proven only on the integration branch (release + production evidence needed) | 437 | 174 | 215 | 48 | {'implemented_unverified': 437} |  |
| No real customers / market outcomes yet | 95 | 38 | 6 | 51 | {'blocked_external': 95} |  |
| No live listings (go-live not authorised) | 38 | 9 | 12 | 17 | {'blocked_owner': 38} | Authorise graduation from shadow to staging, then limited production, one step at a time, once the steps above |
| Image/vision provider capability | 24 | 6 | 15 | 3 | {'blocked_external': 24} |  |
| Gate now OPEN in production: unparked, re-verify | 25 | 0 | 19 | 6 | {'blocked_engineering': 25} |  |
| Etsy surface has no API or is 403 to automation | 19 | 2 | 11 | 6 | {'blocked_external': 19} |  |
| Release not deployed (successor + 24h window) | 15 | 1 | 12 | 2 | {'blocked_engineering': 15} |  |
| Marketplace Insights / Stats paste | 21 | 5 | 4 | 12 | {'blocked_owner': 21} | Record one Marketplace Insights reading from Shop Manager (POST the reading; no API exists). |
| Owned channels (site / Pinterest) | 18 | 7 | 1 | 10 | {'blocked_owner': 18} | The Etsy shop exists (recognised as the paid destination). Open the missing owned surfaces: a domain + static  |
| Testers and physical samples | 16 | 4 | 4 | 8 | {'blocked_owner': 16} | Confirm the prepared public tester call (Ravelry 'The Testing Pool'; research/final_build/w4/tester_kit/OUTREA |
| Other owner decisions (credential rotation, tax, CASL, spend numbers, deploy settings) | 7 | 0 | 7 | 0 | {'blocked_owner': 7} | rotation card wired into owner queue (fb4-OPS); exposed ANTHROPIC_API_KEY rotation is an owner act |
| Owner rulings | 7 | 4 | 2 | 1 | {'blocked_owner': 7} | Rule whether an API + vision traversal satisfies the 'browser/vision' wording of #189/#221/#222/#320 (yes / no |
| Benchmark purchases | 14 | 5 | 0 | 9 | {'blocked_owner': 14} | Buy the 13 approved MJs benchmark patterns (exact list, links and prices: research/final_build/w4/GATE_CLEARAN |
| Etsy Shop Manager settings | 10 | 0 | 4 | 6 | {'blocked_owner': 10} | subscribing is consequential spend |
| Open engineering work | 206 | 2 | 1 | 203 | {'blocked_engineering': 206} |  |
| Paid-media authority | 23 | 2 | 1 | 20 | {'blocked_owner': 23} | Not askable yet: once a listing is ready to sell (gate_clearance.ad_readiness), set SpendLimit 'ads' to the re |
| Banking / payment-ledger feeds | 4 | 0 | 3 | 1 | {'blocked_owner': 4} | Etsy statement is a browser download only |
| Data that only accrues with time / seasons | 3 | 3 | 0 | 0 | {'blocked_external': 3} |  |
| Provider admin usage keys | 3 | 0 | 3 | 0 | {'blocked_owner': 3} | provider usage/cost APIs need admin-scope keys (Anthropic Admin API, OpenAI organization usage) only the owner |
| Paid image generation approval | 2 | 0 | 2 | 0 | {'blocked_owner': 2} | OWNER_ACTIONS batch 'visual' (Paid image generation): VB-1 P2 LIFESTYLE protected composites for the Launch-0  |
| Launch-0 catalogue cap (CAP-1) | 1 | 0 | 1 | 0 | {'blocked_owner': 1} | decide the Launch-0 depth (PRODUCT_FIX.md CAP-1) |
| Model / vision provider credit | 1 | 0 | 0 | 1 | {'blocked_owner': 1} | a second funded judgement/vision provider must exist before a drill can run (owner-approved spend, F-100) |
| Session environment | 1 | 0 | 0 | 1 | {'blocked_external': 1} |  |
| Private Laura register: owner gates, then production soak | 1 | 0 | 0 | 0 | {'blocked_owner': 1} | PRIVATE_LAURA_TRACE §5 owner actions (OA-PL-3 removed by D-W4-PL-3): OA-PL-1 set BRAMBLELOOP_PRIVATE_MEMORY_KE |

## Active worker branches (unmerged, last 24 h)

- `claude/w4-INTEG8-next` @ 9a6381f41 (189 ahead, 2026-11-08T08:09:40+00:00): rows named none

## Unfinished launch-critical / Build 2 rows

| row | class | blocked by | code | deployed | remaining |
|---|---|---|---|---|---|
| B2#1 | blocked_owner | owner: Marketplace Insights paste | True | False | parked on owner gate insights_access |
| B2#2 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#3 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#4 | blocked_owner | owner: open owned channels | True | False | parked on owner gate owned_surfaces |
| B2#5 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#7 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#8 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#9 | blocked_owner | owner: testers / sample | True | False | parked on owner gate tester_roster |
| B2#10 | blocked_owner | owner: open owned channels | True | False | parked on owner gate owned_surfaces |
| B2#11 | blocked_engineering | engineering | True | True | gate transactions_r has opened; the remaining work is no longer parked |
| B2#12 | blocked_engineering | engineering | True | True | gate transactions_r has opened; the remaining work is no longer parked |
| B2#14 | blocked_owner | owner: go-live / publication grant | True | True | parked on owner gate live_listings |
| B2#15 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#16 | blocked_owner | owner: go-live / publication grant | True | False | parked on owner gate live_listings |
| B2#17 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#18 | blocked_external | external: real buyers | True | True | parked on customers: needs real customers |
| B2#19 | blocked_external | external: real buyers | True | True | parked on customers: needs real customers |
| B2#20 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#21 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#23 | blocked_external | external: real buyers/traffic | True | False | machinery exists (commerce/kill_table.py); parked on data gate listing_traffic: a listing period with counted visits (li |
| B2#24 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#25 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#27 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#28 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#29 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#30 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#31 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#33 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#34 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#35 | blocked_external | external: Etsy pages 403 to automation / no API | True | False | parked on rendered_pages, opened by a person: a person -- proposed to the owner, not yet accepted (owner_queue decision  |
| B2#36 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#37 | blocked_owner | owner: Marketplace Insights paste | True | False | parked on owner gate insights_access |
| B2#38 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#39 | blocked_external | external: Etsy pages 403 to automation / no API | True | False | parked on rendered_pages, opened by a person: a person -- proposed to the owner, not yet accepted (owner_queue decision  |
| B2#40 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#41 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#43 | blocked_owner | owner: testers / sample | True | False | parked on owner gate tester_roster |
| B2#44 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#45 | blocked_external | external: real buyers | True | True | parked on customers: needs real customers |
| B2#46 | blocked_owner | owner: go-live / publication grant | True | False | parked on owner gate live_listings |
| B2#48 | blocked_external | external: real buyers | True | True | parked on customers: needs real customers |
| B2#50 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#54 | blocked_owner | owner: Marketplace Insights paste | True | False | parked on owner gate insights_access |
| B2#55 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#57 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#58 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#60 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#61 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#63 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#64 | blocked_owner | owner: testers / sample | True | False | parked on owner gate physical_proof |
| B2#65 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#66 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#67 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#68 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#69 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#70 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#71 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#72 | blocked_external | external: image provider capability | True | True | no image provider has rendered a certified crochet structure faithfully enough to pass the deterministic stitch instrume |
| B2#73 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#74 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#75 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#78 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#79 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#80 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#81 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#82 | blocked_external | external: market outcomes | True | False | machinery exists (creative/style_learning.py); parked on data gate style_outcomes: enough listing impressions for one he |
| B2#83 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#85 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#86 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#87 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#88 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#89 | blocked_external | external: market outcomes | True | False | machinery exists (creative/outcome_learning.py); parked on data gate concept_outcomes: enough visits and orders to join  |
| B2#91 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#92 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#93 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#94 | blocked_external | external: market outcomes | True | False | machinery exists (creative/blinded.py); parked on data gate market_outcomes: live listing traffic and at least one sale |
| B2#95 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#96 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#97 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#98 | blocked_external | external: data accrues with operating time | True | False | machinery exists (intel/learning.py); parked on data gate learning_sources: a craft-technique source and buyers' complai |
| B2#99 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#100 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#101 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#104 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#105 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#108 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#110 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#112 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#114 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#115 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#116 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#117 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#118 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#119 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#120 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#121 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#122 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#124 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#125 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#126 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#127 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#129 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#130 | blocked_external | external: image provider capability | True | True | no image provider has rendered a certified crochet structure faithfully enough to pass the deterministic stitch instrume |
| B2#131 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#132 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#133 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#134 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#135 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#136 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#137 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#138 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#139 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#140 | blocked_external | external: data accrues with operating time | True | True | machinery exists (culture/feeds.py); parked on data gate lead_lag_series: both a culture series and a marketplace series |
| B2#141 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#142 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#143 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#144 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#145 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#146 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#147 | blocked_external | external: real buyers | True | True | parked on customers: needs real customers |
| B2#150 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#151 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#152 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#153 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#154 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#155 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#156 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#157 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#158 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#159 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#160 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#161 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#162 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#163 | blocked_owner | owner: buy benchmark set | True | False | parked on owner gate benchmark_purchases |
| B2#164 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#165 | blocked_owner | owner: buy benchmark set | True | False | parked on owner gate benchmark_purchases |
| B2#168 | blocked_owner | owner: buy benchmark set | True | False | parked on owner gate benchmark_purchases |
| B2#169 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#170 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#171 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#172 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#173 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#174 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#175 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#176 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#177 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#178 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#179 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#180 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#181 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#182 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#183 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#185 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#186 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#187 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#188 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#189 | blocked_owner | owner: ruling | True | False | parked on owner gate acceptance_ruling |
| B2#190 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#191 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#192 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#194 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#195 | blocked_engineering | engineering: deploy successor + 24h unattended window | True | False | parked on owner gate production_window |
| B2#196 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#199 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#201 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#202 | blocked_external | external: image provider capability | True | True | no image provider has rendered a certified crochet structure faithfully enough to pass the deterministic stitch instrume |
| B2#203 | blocked_external | external: image provider capability | True | False | no image provider has rendered a certified crochet structure faithfully enough to pass the deterministic stitch instrume |
| B2#205 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#206 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#208 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#209 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#211 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#213 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#214 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#215 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#216 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#217 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#218 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#219 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#220 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#221 | blocked_owner | owner: ruling | True | False | parked on owner gate acceptance_ruling |
| B2#222 | blocked_owner | owner: ruling | True | False | parked on owner gate acceptance_ruling |
| B2#225 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#226 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#227 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#228 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#229 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#230 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#232 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#235 | blocked_external | external: real buyers | True | True | parked on customers: needs real customers |
| B2#236 | blocked_owner | owner: Marketplace Insights paste | True | False | parked on owner gate insights_access |
| B2#237 | blocked_owner | owner: Marketplace Insights paste | True | True | parked on owner gate insights_access |
| B2#238 | blocked_owner | owner: go-live / publication grant | True | False | parked on owner gate live_listings |
| B2#239 | blocked_owner | owner: go-live / publication grant | True | True | parked on owner gate live_listings |
| B2#240 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#241 | blocked_owner | owner: go-live / publication grant | True | False | parked on owner gate live_listings |
| B2#242 | blocked_external | external: real buyers | True | True | parked on customers: needs real customers |
| B2#243 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#244 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#245 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#246 | blocked_owner | owner: open owned channels | True | True | parked on owner gate owned_surfaces |
| B2#247 | blocked_owner | owner: open owned channels | True | True | parked on owner gate owned_surfaces |
| B2#248 | blocked_owner | owner: open owned channels | True | False | parked on owner gate owned_surfaces |
| B2#249 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#250 | blocked_owner | owner: testers / sample | True | False | parked on owner gate tester_roster |
| B2#251 | blocked_owner | owner: open owned channels | True | False | parked on owner gate owned_surfaces |
| B2#252 | blocked_external | external: real buyers | True | True | parked on customers: needs real customers |
| B2#253 | blocked_external | external: real buyers | True | True | parked on customers: needs real customers |
| B2#254 | blocked_owner | owner: go-live / publication grant | True | True | parked on owner gate live_listings |
| B2#255 | blocked_owner | owner: open owned channels | True | True | parked on owner gate owned_surfaces |
| B2#256 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#257 | blocked_external | external: real buyers | True | True | parked on customers: needs real customers |
| B2#258 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#260 | blocked_external | external: real buyers | True | True | parked on customers: needs real customers |
| B2#263 | blocked_owner | owner: go-live / publication grant | True | True | parked on owner gate live_listings |
| B2#264 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#265 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#266 | blocked_owner | owner: go-live / publication grant | True | False | parked on owner gate live_listings |
| B2#270 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#271 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#272 | blocked_external | external: real buyers | True | True | parked on customers: needs real customers |
| B2#274 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#275 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#276 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#277 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#278 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#279 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#280 | blocked_external | external: real buyers | True | True | parked on customers: needs real customers |
| B2#281 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#284 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#285 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#286 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#287 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#289 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#291 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#292 | blocked_external | external: real buyers | True | False | parked on customers: needs real customers |
| B2#293 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#294 | blocked_owner | owner: ad budget authority | True | False | parked on owner gate ad_authority |
| B2#295 | blocked_owner | owner: ad budget authority | True | False | parked on owner gate ad_authority |
| B2#296 | blocked_external | external: real buyers | True | False | machinery exists (seasonal/leadtime.py); parked on data gate seasonal_orders: an order attributed to a seasonal event |
| B2#297 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#298 | blocked_external | external: a season has to pass | True | False | machinery exists (seasonal/harvest.py); parked on data gate season_harvest: a passed seasonal event with enough orders t |
| B2#299 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#300 | blocked_external | external: image provider capability | True | False | no image provider has rendered a certified crochet structure faithfully enough to pass the deterministic stitch instrume |
| B2#301 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#302 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#303 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#304 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#306 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#307 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#308 | blocked_external | external: image provider capability | True | False | no image provider has rendered a certified crochet structure faithfully enough to pass the deterministic stitch instrume |
| B2#309 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#310 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#311 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#313 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#314 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#315 | blocked_owner | owner: buy benchmark set | True | True | parked on owner gate benchmark_purchases |
| B2#316 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#317 | blocked_owner | owner: buy benchmark set | True | False | parked on owner gate benchmark_purchases |
| B2#318 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#319 | implemented_unverified | engineering: release + deploy | True | False |  |
| B2#320 | blocked_owner | owner: ruling | True | False | parked on owner gate acceptance_ruling |
| F-001 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-004 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-005 | blocked_engineering | engineering: gate etsy_api is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | False | owner gate etsy_api: certified_payload refuses UNKNOWN taxonomy; real seller taxonomy read needs the Etsy credential gat |
| F-006 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-007 | blocked_engineering | engineering: gate etsy_api is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | False | owner gate etsy_api: set_listing_property wired (pipeline); node property schema read needs etsy_api |
| F-008 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-009 | blocked_engineering | engineering: gate etsy_api is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | False | owner gate etsy_api: a working Etsy credential lets listing.taxonomy_refresh read the node schema |
| F-010 | blocked_engineering | engineering: gate etsy_api is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | False | Add a weekly handler (runtime/worker cadence) storing a taxonomy/properties snapshot digest and opening a blocking incid |
| F-011 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-012 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-013 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-014 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-015 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-020 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-021 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-022 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-023 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-024 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-025 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-026 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-027 | blocked_engineering | engineering: gate image_vision is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | True | When image_vision opens, add a vision 'identify the product' check to the hero in handle_assets_build; meanwhile keep de |
| F-030 | blocked_owner | owner: paid image calls | True | False | owner: approve OWNER_ACTIONS 'visual' / visual_paid_generation (P2 max CA$2.00) or supply sample photos; then the visual |
| F-031 | blocked_engineering | engineering: gate image_vision is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | True | Once image_vision opens, add a grid-scale identification check; otherwise none |
| F-039 | blocked_external | external: Etsy pages 403 to automation / no API | True | False | Add a 'search_guidance' POLICY_SOURCES entry governing ('listing','search') and on its change enqueue listing.seo re-run |
| F-040 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-041 | blocked_engineering | engineering: gate image_vision is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | False | none beyond F-027 vision step |
| F-042 | blocked_external | external: Etsy pages 403 to automation / no API | True | True | Build an owner-recorded Customer Service Stats intake (response rate, case count, review average) plus getShop review_av |
| F-048 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-049 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-052 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-059 | blocked_owner | owner: Marketplace Insights paste | True | False | Label search_share on /api/catalogue as internal_score and retire it from readiness once Stats exist |
| F-060 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-071 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-072 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-074 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-078 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-079 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-080 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-081 | blocked_owner | owner: testers / sample | True | False | owner gate tester_roster: physical intake fixed (fb4-PUB); Class C needs an independent tester's make |
| F-084 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-086 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-087 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-088 | blocked_external | external: real buyers | True | False | Scope incidents to slug@version plus rebuild_graph descendants and feed confirmed defects into gates/confidence |
| F-090 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-098 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-100 | blocked_engineering | engineering: gate model_provider is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | False | Add a launch/access.py AccessRequest 'second model provider' whose card carries scale/dependency.py's measured provider  |
| F-101 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-102 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-103 | blocked_owner | owner: provider admin keys | True | False | owner: set ANTHROPIC_ADMIN_KEY / OPENAI_ADMIN_KEY (read-only) |
| F-104 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-105 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-106 | blocked_owner | owner: provider admin keys | True | False | owner: set ANTHROPIC_ADMIN_KEY / OPENAI_ADMIN_KEY (read-only) |
| F-108 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-109 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-110 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-111 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-112 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-115 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-118 | blocked_owner | owner: testers / sample | True | False | owner gate tester_roster: first_customer gate wired via eligibility; calibration needs a recruited tester |
| F-119 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-120 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-131 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-132 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-135 | blocked_owner | owner: authorise a live drill | True | True | owner gate production_window: after the deploy, kill the worker mid-job once and record lease reclaim + single completio |
| F-141 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-142 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-143 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-144 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-158 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-160 | blocked_owner | owner: credential_rotation | True | False | owner gate credential_rotation: rotation card wired into owner queue (fb4-OPS); exposed ANTHROPIC_API_KEY rotation is an |
| F-161 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-162 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-163 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-164 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-165 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-166 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-168 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-169 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-171 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-172 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-173 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-174 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-175 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-179 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-180 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-181 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-182 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-183 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-184 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-185 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-186 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-187 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-188 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-189 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-195 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-196 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-197 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-202 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-204 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-206 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-210 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-211 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-212 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-213 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-219 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-221 | blocked_external | external: image provider capability | True | False | Apply photoreal.judge/gate to owned_photography frames as a separate floor (keep inspect physical checks), and require i |
| F-222 | blocked_external | external: image provider capability | True | False | Extend photoreal.CHECKS to product-first frames (see F-221) |
| F-223 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-225 | blocked_external | external: image provider capability | True | True | Add a cross-frame consistency check (same colourway/motif verdicts across frames) to parity GALLERY and plan hero/detail |
| F-227 | blocked_external | external: image provider capability | True | False | Integrate a deterministic structure reader (count/pitch/edging/dimension) into motif_fidelity or parity PRODUCT_TRUTH; e |
| F-228 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-233 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-235 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-236 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-237 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-238 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-239 | blocked_external | external: Etsy pages 403 to automation / no API | None | None | Build brand/storefront_preview.py rendering icon at 40/70px, banner 1600x400 centre-crop at 360px phone width with safe- |
| F-242 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-243 | blocked_engineering | engineering: gate etsy_api is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | False | Read Etsy seller taxonomy (getSellerTaxonomyNodes / getPropertiesByTaxonomyId, public API-key reads already sanctioned)  |
| F-244 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-245 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-246 | blocked_owner | owner: Marketplace Insights paste | True | False | Add a scheduled re-tag job that re-runs choose_tags for published listings when a new attribution.stats reading or serp  |
| F-247 | blocked_engineering | engineering: gate etsy_api is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | False | Verify taxonomy_id against Etsy seller taxonomy (sanctioned API-key read) and add a check that every attribute value map |
| F-248 | blocked_owner | owner: go-live / publication grant | None | None | Build an opsauth-guarded POST /api/search-visibility (rows: observed_at, listing_id, scope shop/listing/service, categor |
| F-249 | blocked_owner | owner: Marketplace Insights paste | True | False | Add an explicit rule in growth/listing experiment code refusing any 'manual search rank' evidence source, and route Shop |
| F-250 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-251 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-252 | blocked_engineering | engineering: gate image_vision is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | False | Add resolution (min long edge) and exposure/lighting floors to thumbnail.evaluate_thumbnail; keep comparative click appe |
| F-253 | blocked_engineering | engineering: gate image_vision is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | True | owner gate image_vision: Launch-0 disclosed renders; parity HERO judgement + competitive blind review (data) remain |
| F-254 | blocked_owner | owner: paid image calls | True | False | owner: approve OWNER_ACTIONS 'visual' / visual_paid_generation (P2 max CA$2.00) or supply sample photos; then the visual |
| F-255 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-256 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-258 | blocked_owner | owner: go-live / publication grant | True | True | Add an authenticated owner Stats listing-level intake (POST /api/listing-outcomes -> style_learning.record_outcome, sour |
| F-260 | blocked_owner | owner: go-live / publication grant | True | False | data gate live_listings: once a listing is live, the same rule decides on its real exposure; nothing to build |
| F-261 | blocked_owner | owner: go-live / publication grant | True | True | data gate live_listings: once a listing is live, the same rule decides on its real exposure; nothing to build |
| F-263 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-267 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-272 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-273 | blocked_external | external: real buyers | True | True | data: the first real offsite-attributed sale; the owner then records the ledger mapping verification (owner.etsy_ledger_ |
| F-277 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-278 | blocked_engineering | engineering: gate image_vision is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | False | Owner: fund the vision provider account (image_vision gate). Software: none beyond keeping candidates per product >=2 at |
| F-280 | blocked_owner | owner: go-live / publication grant | None | None | After F-248, add a cadence in runtime/worker.py that, for 7 days after the phase leaves shadow, raises a daily owner car |
| F-282 | blocked_owner | owner: go-live / publication grant | True | True | data gate live_listings: once a listing is live, the same rule decides on its real exposure; nothing to build |
| F-283 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-284 | blocked_external | external: real buyers | True | True | none for launch beyond F-258/F-283 data paths; post-launch: feed review distribution into trust rungs. |
| F-285 | blocked_owner | owner: Marketplace Insights paste | True | False | Add a seasonal.engine step that, N days before each occasion's indexing milestone, re-runs listing.seo tag choice for th |
| F-287 | blocked_owner | owner: go-live / publication grant | True | True | data gate live_listings: the sections fill from ListingOutcome periods once a listing is live |
| F-291 | blocked_external | external: Etsy 403 | True | True | Add search_guidance source (F-242) and the ads learning/threshold rules to the advertising_rules reading so a change inv |
| F-292 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-293 | blocked_external | external: Etsy pages 403 to automation / no API | None | None | Build the storefront preview renderer (F-239) at desktop and mobile widths and a launch/readiness Requirement comparing  |
| F-294 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-295 | blocked_owner | owner: ad budget authority | True | False | Add an ads dry-run acceptance test: granted authority fixture + one uncertified, one stale-certificate and one over-budg |
| F-297 | blocked_external | external: Etsy Ads data | True | False | Build the listing-level intake (F-258) and a 'measurement proven' readiness requirement (a recorded organic listing read |
| F-298 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-301 | blocked_owner | owner: provider admin keys | True | False | Add ops/provider_accounts.observe(provider) reading provider usage endpoints when an admin key is configured, persist ob |
| F-302 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-304 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-306 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-307 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-309 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-310 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-311 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-312 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-313 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-314 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-316 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-317 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-319 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-321 | blocked_owner | owner: go-live / publication grant | True | False | data gate live_listings: spend rows tagged with product_slug at runtime (6d86a8b); maintenance cost needs a live listing |
| F-323 | blocked_external | external: real buyers | True | True | Add per-order contribution in commerce/order_readings (gross - fees - refunds - ads - attributed variable AI cost for th |
| F-324 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-325 | blocked_owner | owner: go-live / publication grant | True | False | data gate live_listings: re-read once listings have history |
| F-327 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-328 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-329 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-336 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-339 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-360 | blocked_owner | owner: testers / sample | True | True | transcribe the full CYC baby chart (all published rows) into cir/graded as a BABY BodyTable with source/date and allow g |
| F-361 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-362 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-363 | blocked_owner | owner: testers / sample | True | True | owner: physical sample via the tester roster |
| F-364 | blocked_external | external: vision provider capability | True | True | once Visual V1 locks, add a children's shot-list (nursery context, gift framing) to publish/listing_assets frame job map |
| F-371 | blocked_engineering | engineering: deploy successor + 24h unattended window | True | False | owner: approve Build 2 deploy; then let build2/autonomy.off_device_proof read PROVEN over a full unattended window |
| F-380 | blocked_engineering | engineering: deploy successor + 24h unattended window | True | False | add scripts/deploy_gate.sh (or CI workflow) that refuses a Railway deploy unless run_tests.sh passed on the SHA, then re |
| F-381 | blocked_engineering | engineering: deploy successor + 24h unattended window | True | False | add a code-deploy rollback runbook check: record previous Railway deployment id at each deploy and a rehearsal that rede |
| F-392 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-395 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-396 | blocked_engineering | engineering: gate offsite_storage is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | False | owner: configure offsite storage destination and approve Build 2 deploy |
| F-416 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-418 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-437 | blocked_engineering | engineering: gate etsy_api is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | False | owner: complete Etsy OAuth; then run POST /api/etsy/exercise and record the verification matrix |
| F-461 | blocked_owner | owner: deploy_trigger_config | None | None | owner gate deploy_trigger_config: guard runs in ops/hooks/pre-push + ops/deploy.sh (ffcb62e); a client hook can be skipp |
| F-471 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-472 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-477 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-495 | blocked_engineering | engineering: deploy successor + 24h unattended window | True | True | After the owner deploys Build 2, let the 24h window run and read autonomy.launch_item until PROVEN |
| F-497 | blocked_owner | owner: plane_violations | True | False | Enforce GET-only production access for build sessions in tooling (separate read-only ops token scope in core/opsauth.py) |
| F-501 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-518@v0.15 | blocked_owner | owner: publication grant | True | True | owner: production window + write grant; then the attached plan is executed through listing_rollback.execute |
| F-514@v0.16 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-515@v0.16 | blocked_engineering | engineering: gate etsy_shop is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | False | owner gate etsy_shop: daily etsy.shop_snapshot judges getShop; needs a usable shop credential on the deployed build |
| F-524 | blocked_owner | owner: go-live / publication grant | True | True | data gate live_listings: store.publish sends certified images; hero experiments need a live listing |
| F-532 | blocked_external | external: Etsy has no API | True | True | Add an owner-paste intake for Etsy Customer Service Stats (response rate/time, case count) with thresholds that open an  |
| F-536 | blocked_external | external: Etsy pages 403 to automation / no API | True | False | Wire listing_census_drift to a daily getListingsByShop poll so a suppressed/removed listing raises an owner incident (po |
| F-537 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-538 | blocked_external | external: real buyers | True | False | data: first real settlement; owner records the mapping verification; classify any tax/credit/subscription ledger types t |
| F-540 | blocked_engineering | engineering: gate etsy_api is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | True | owner gate production_window: credential_health cadence built; rotation proof needs owner-authorised exercise on the dep |
| F-541 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-542 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-543 | blocked_owner | owner: publication grant | True | False | owner gate publication_authority: store.activate built with revalidated authority; going live is the owner's grant + pha |
| F-545 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-547 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-553 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-556 | blocked_external | external: Etsy has no API | True | True | external gate no_messages_api: SLA watch + opsauth owner intake built (fb4-OPS); Etsy exposes no conversation API |
| F-557 | blocked_external | external: Etsy has no API | True | True | Extend support/department.py _ROUTES with pre_sale, refund, safety, policy and abuse_spam classes (refund/safety/policy  |
| F-558 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-577 | blocked_owner | owner: Etsy shop settings | True | False | owner gate payout: drift monitor built; owner completes Etsy Payments onboarding |
| F-578 | blocked_owner | owner: legal_and_tax | True | True | Persist the owner's dated tax-position decision (POST /api/owner/decision key legal_and_tax) and surface it in shop_pack |
| F-587 | blocked_owner | owner: Etsy Shop Manager setting | True | True | In the shop snapshot cadence, compare getShop policy_* strings to commerce.shop_package.policies() and route any mismatc |
| F-588 | blocked_owner | owner: Etsy Shop Manager setting | True | False | Surface Evidence(UNKNOWN) entries in coverage()['unknowns'] so the partners question reaches readiness; add a test that  |
| F-592 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-593 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-594 | blocked_engineering | engineering: gate etsy_api is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | False | owner gate etsy_api: readiness reads exercise evidence; the owner-authorised create/read/delete round trip remains |
| F-608 | blocked_owner | owner: banking export | True | False | owner gate bank_and_payment_ledger_feed: connect or export the statements; reconciliation then runs on them |
| F-617 | blocked_external | external: Etsy has no API | True | True | Provide the owner case-intake route (F-556) so real buyer messages enter support_cases; route review themes via commerce |
| F-623 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-628 | blocked_engineering | engineering: gate offsite_storage is OPEN in production (20261020T0540Z); the row is unparked and must be re-verified, not assumed done | True | True | Owner: provide an off-provider bucket credential (offsite_storage) and authorise the production window; then read autono |
| F-629 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-654 | blocked_engineering | engineering: deploy successor + 24h unattended window | True | False | Owner action: authorise deployment of the 019ebf0 lineage; then leave devices off 24h and read /api/launch until autonom |
| F-663 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-665 | blocked_owner | owner: dashboard_truth.evidence | True | False | Define an Evidence dict (source, as_of, transform, confidence, reconciliation) and attach it to /api/console, /api/finan |
| F-674 | blocked_external | external: image provider capability | True | True | external gate visual_v1_provider_capability: generative redraw refused (F-852); B+C photoreal stays R&D, not launch-crit |
| F-676 | blocked_external | external: image provider capability | True | False | external gate model_bearing_render: F-852 refusal; protected-region enhancement waits on V2/provider fidelity |
| F-689 | blocked_external | external: Etsy has no API | True | True | external gate no_messages_api: ingest messages when Etsy exposes them; until then the owner intake (F-556) feeds the wor |
| F-695 | blocked_owner | owner: spend_policy numbers | True | False | Owner: supply provider and department ceilings (PROVIDER_CEILINGS_CAD, department allocations); software: record infrast |
| F-701 | blocked_engineering | engineering: deploy successor + 24h unattended window | True | False | Owner: authorise deploying the certified successor; software: none beyond F-654 proof read-out. |
| F-702 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-704 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-718 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-721 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-726 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-731 | blocked_external | external: image provider capability | True | True | Route every creative producer that can contain a person (growth content, ads, social) through model_registry.gate_frames |
| F-732 | blocked_external | external: image provider capability | True | False | when model-bearing renders are re-authorised: qualify a face-embedding model into identity_gate.QUALIFIED_EMBEDDERS |
| F-733 | blocked_engineering | engineering | True | True | company: record the approved pack fingerprint from the production model.frozen row in the repository manifest; store pro |
| F-734 | blocked_external | external: image provider capability | True | True | external gate model_bearing_render: no provider renders a model-bearing frame clearing every floor |
| F-735 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-736 | blocked_external | external: image provider capability | True | True | On systematic model-frame failure, have what_to_do_next select an alternate demonstrated provider (image_bench/provider_ |
| F-740 | blocked_external | external: image provider capability | True | False | none beyond deploy; waits on first passing model frame. |
| F-741 | blocked_external | external: image provider capability | True | True | Derive required views from the CIR's construction features (neckline, sleeves, closure) and require a frame that shows e |
| F-743 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-746 | blocked_external | external: image provider capability | True | True | Add a pairwise set-consistency check (product attributes and identity observations compared across frames) to parity; te |
| F-749 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-750 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-751 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-752 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-754 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-755 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-756 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-757 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-761 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-765 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-768 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-770 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-779 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-780 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-781 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-782 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-790 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-792 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-798 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-799 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-801 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-805 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-808 | blocked_owner | owner: open owned channels | True | False | Buildable now: call learn.service.help_links from support/concierge answer composition and from listing description asse |
| F-815 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-821 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-822 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-826 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-835 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-841 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-846 | implemented_unverified | engineering: release + deploy | None | None |  |
| F-848 | blocked_owner | owner: CAP-1 decision | True | False | company: make owner_phase_transition cite the readiness verdict of a production-shaped state (seed the scratch DB from a |
| F-849 | blocked_engineering | engineering: deploy successor + 24h unattended window | True | False | Buildable now: re-run tests/test_cert_claude_independence.py on the frozen candidate and commit the evidence; owner: aut |
| F-850 | blocked_owner | owner: authorise a live drill | True | True | Buildable now: add a restart test that kills the worker mid store.publish (grant-approved, fake Etsy) and mid orders.ing |
| F-851 | blocked_external | external: image provider capability | True | True | external gate visual_v1_provider_capability: V1 redraw refused; protected photoreal presentation waits on V2 R&D |
| F-852 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-853 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-854 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-870 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-871 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-872 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-874 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-877 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-880 | blocked_engineering | engineering: deploy successor + 24h unattended window | True | False | owner gate production_window: deploy the candidate, run the 24h soak and grade it with ops/slo soak grading |
| F-881 | blocked_engineering | engineering: deploy successor + 24h unattended window | True | True | owner gate production_window: deploy, then grade a soak in which no development session drives work |
| F-882 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-883 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-884 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-885 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-886 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-888 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-890 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-891 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-892 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-893 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-894 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-895 | blocked_engineering | engineering: deploy successor + 24h unattended window | True | False | owner gate production_window: deploy, then read one unattended night's useful work per department from ops/slo departmen |
| F-896 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-897 | blocked_owner | owner: casl_notification_authority | True | False | owner gate casl_notification_authority: approve one external channel; the deduplicated severity-ranked queue then feeds  |
| F-898 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-899 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-904 | blocked_owner | owner: banking export | True | False | owner gate bank_and_payment_ledger_feed: connect or export a statement feed |
| F-908 | blocked_owner | owner: banking export | True | True | owner gate bank_and_payment_ledger_feed: connect a bank / Etsy ledger feed |
| F-918 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-921 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-922 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-923 | blocked_engineering | engineering: deploy successor + 24h unattended window | True | True | owner gate production_window: deploy the candidate with the watchdog probe |
| F-924 | blocked_engineering | engineering: deployed release + hosted history | True | True | owner gate hosted_operating_history: deploy; the slo_check cadence then measures real error budgets |
| F-925 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-926 | blocked_owner | owner: Etsy Shop Manager setting | True | False | Owner: review the v2 vs v1 comparison in the Command Center store preview and accept or annotate; OA-A1/OA-OBS let the p |
| F-928 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-929 | implemented_unverified | engineering: release + deploy | True | False |  |
| F-930 | implemented_unverified | engineering: release + deploy | True | False |  |
| LAURA-PRIVATE-REGISTER | blocked_owner | owner: OA-PL-1/2/4 (private key, D-W4-PL-1 acknowledgement, spend authorisation + register switch; no consent prerequisite, D-W4-PL-3), then the class-B production soak | True | False | code + tests built (W4-PRIVLAURA); enablement is owner-only: BRAMBLELOOP_PRIVATE_MEMORY_KEY, D-W4-PL-1 acknowledgement,  |
