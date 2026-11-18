# Continuous integration queue: every completed engineering branch

Owner directive 2026-11-02, "Permanent continuous integration". The integrator maintains this
file and processes eligible items at every wake-up, before writing any status report.
Target for all items: `claude/w5-INTEG1` (Batch 5). Integration is not deployment.
Last updated: 2026-11-02T04:35Z.

## Rules
- A head is merge-ready when three things hold: an independent review says SHIP or ACCEPT for
  that exact SHA, its dependencies are already in the target, and its listed regression suites
  pass on the merged tree.
- A merge-ready head is merged at the next wake-up.
- A PR is split by commit when its clusters are independent. Each unit keeps its exact SHAs,
  and each merge commit names the PR, the SHA and the review.
- No item waits on unrelated work. In particular, the pet bed, stocking and gallery fixes hold
  nothing else back.
- Unchanged code is never re-reviewed. A delta review covers only the commits after the last
  reviewed SHA.
- A blocked item records its exact blocker; integration then continues with the next item.

## Queue

| ID | Branch / PR | Exact SHA(s) | Verdict | Depends on | Merge-ready | Regression suites | Next action | Operator |
|---|---|---|---|---|---|---|---|---|
| Q1 | opus2/p1-culture-sweep-timeout, PR #7 | 3468fe73 | ACCEPT (OPUS2K) | none | **integrated** (W5-INTEG1 812f63d7, pushed 03:46Z; 13/13 suites green) | test_opus2_culture_sweep_timeout, test_culture, test_culture_feed, test_cost_governance_wave2 | none: done | — |
| Q2 | opus2/p0-cir-colourwork, PR #9 | 424d69a9 | ACCEPT (OPUS2K); J-7 SHIP (J7B) | W5-INTEG1 2d2d9446 | **integrated** (W5-INTEG1 812f63d7) | test_opus2_cir_colourwork, test_first_customer_gate, test_launch0, test_launch0_listing_truth, test_w5_integfix, test_compiler, test_reverse, test_twin | none: done | — |
| Q3 | opus2/p0-revenue-workforce, PR #3 (J-1 chain) | 558e7ca9, 6d6d83d9, 771e1e1a, c3074241, 6769e696 | 6769e696 CHANGES_REQUIRED (OPUS2M-1 MED: count words still a list) | none in target | no: **blocked** on the OPUS2M-1 fix (Secondary working it, 04:32Z) | test_opus2_size_claims, test_launch0*, test_opus2_draft_constructions, test_vacuity | delta review of the fix; merge the chain on SHIP | opus2 |
| Q4 | opus2/p1-culture-sweep-timeout, PR #7 | e0be7c4d (tests only) | SHIP (OPUS2M) | Q1 | **integrated** (W5-INTEG1 a8ce0072, suites green) | test_opus2_culture_sweep_timeout | none; OPUS2M-5 and -6 LOW follow-ups for opus2 | — |
| Q5 | opus2/p0-cir-colourwork, PR #9 | d4486b8c | CHANGES_REQUIRED (OPUS2M-2 MED **regression**: word-start anchor loosens the claim reader) | Q2 | no: **blocked** on the OPUS2M-2 fix | as Q2 | delta review of the fix | opus2 |
| Q6 | opus2/p0-pet-bed, PR #10 | d0a7685f, 7d220e01, 940f70e6 | 940f70e6 **in review OPUS2N** (fix for OPUS2K-7 HIGH) | Q3 (stacked on -b4merge; uses fallback_constructions from PR #3) | no: awaiting OPUS2N, then Q3 | test_opus2_pet_bed, test_opus2_draft_constructions, test_fallback_draft_provenance | merge after OPUS2N SHIP and once Q3 is in | integrator |
| Q7 | opus2/p0-stocking, PR #11 | 5c7b984a, be12b47b, 563c0436, 0ef8a716 | DO NOT SHIP (OPUS2L-1 HIGH) | Q6 | no: **blocked** on the OPUS2L fixes | test_opus2_stocking + Q6 suites | opus2 fixes; then one delta review with Q6 | opus2 |
| Q8 | opus2/p0-listing-package, PR #5 | be96a598 | ACCEPT | none | **merged** (earlier) | test_opus2_listing_package | none: done | — |
| Q9 | opus2/p1-owner-queue-races, PR #6 | 23935b58 | ACCEPT | none | **merged** (earlier) | test_opus2_owner_queue_races | none: done | — |
| Q10 | opus2/p0-family-membership, PR #8 | d8d80301 | ACCEPT | none | **merged** (earlier) | test_opus2_family_membership | none: done | — |
| Q11 | claude/w4-INTEG8-next records | 42db54ae, 51e39992 and this file (docs/records only) | n/a (no code) | none | **integrated** (812f63d7; records suites 7/7 green) | none (no code) | re-merge at each records change | integrator |
| Q12 | codex/p0-learning-reference | 57c176a9 (claim only) | n/a: no code yet | — | no: **not started** | — | owner starts Codex; review its first push | Codex |
| Q13 | review / design records: claude/w4-PDFAUDIT-*, w4-DESIGNREVIEW-basket-1.3.0, w4-CONSTRUCTREVIEW-basket | docs only | n/a | none | yes (records) | none | fold into W5-INTEG1 as records at the next merge | integrator |
| Q14 | opus2/p0-tapestry (new) | 67b67015 (on W5-INTEG1 2d2d9446) | **in review OPUS2N** | Q5 (uses the colourwork claim reader) | no: awaiting OPUS2N and Q5 | test_opus2_cir_colourwork, test_launch0*, the tapestry suite | merge after OPUS2N SHIP and Q5 | integrator |
| Q15 | opus2 new work: P0-PHOTO-ASSET-REVIEW | not started | — | none | — | — | assigned on PR #3 | opus2 |

Not integration items:
- #4: reference only, do not merge.
- #1: Codex draft, superseded.
- #2, #12, #13: review reports.
- claude/w5-INTEG1-trial and claude/w4-INTEG8-trial-adopt: trial branches, superseded.
- claude/w5-LEARNREF-parked-mainopus: parked; Codex owns that work.

## Batch 5 certification path
1. Q1 and Q2 pushed, then Q3, Q4 and Q5 on OPUS2M SHIP; Q11 and Q13 records alongside.
2. Q6 and Q7 if they reach SHIP before step 3 starts. Otherwise they ride the next batch.
3. Affected regression suites; one independent integration review of the W5-INTEG1 delta since
   0967c3ee; then ONE uninterrupted full suite (REQUIRE_CLEAN=1).
4. deploy_guard record, DRY_RUN, rollback rehearsal, then the owner's approval of the exact
   SHA, then deploy through ops/deploy.sh at once.
