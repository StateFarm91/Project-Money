# Continuous integration queue: every completed engineering branch

Owner directive 2026-11-02, "Permanent continuous integration". The integrator maintains this
file and processes eligible items at every wake-up, before writing any status report.
Target for all items: `claude/w5-INTEG1` (Batch 5). Integration is not deployment.
Last updated: 2026-11-02T11:06Z. Certification: run 20261102T101632Z-4284 on W5-INTEG1 4af3418f (running). Known open in the candidate: P0-NAME-OBJECT-MISMATCH (to be disclosed in the deploy request).

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
| Q3 | opus2/p0-revenue-workforce, PR #3 | 558e7ca9..b185b528, fed859b7 | b185b528 CHANGES_REQUIRED (OPUS2Q-1); fed859b7 partial (OPUS2T-1/-2 HIGH, -3 MED) | none in target | no: **blocked** | test_opus2_size_claims, test_launch0*, test_opus2_draft_constructions, test_vacuity | delta review of fixes | opus2 |
| Q4 | opus2/p1-culture-sweep-timeout, PR #7 | e0be7c4d (tests only) | SHIP (OPUS2M) | Q1 | **integrated** (W5-INTEG1 a8ce0072, suites green) | test_opus2_culture_sweep_timeout | none; OPUS2M-5 and -6 LOW follow-ups for opus2 | — |
| Q5 | opus2/p0-cir-colourwork, PR #9 | d4486b8c, 5889cc37, 2f9c413d | 2f9c413d CHANGES_REQUIRED (OPUS2Q-2 MED regression) | Q2 | no: **blocked** on the OPUS2Q-2 fix | as Q2 | delta review of the fix | opus2 |
| Q6 | opus2/p0-pet-bed, PR #10 | d0a7685f, 7d220e01, 940f70e6, 09122165 | SHIP (OPUS2O) | none (split from PR #3: I-B5-SPLIT-PET-STOCKING) | **integrated** W5-INTEG1 52f9f4b5 (suites running, push on green) | test_opus2_pet_bed, test_opus2_draft_constructions, test_fallback_draft_provenance | push; Batch 6 | integrator |
| Q7 | opus2/p0-stocking, PR #11 | ..a859f6fe, d3a485a1 | SHIP (OPUS2O, OPUS2Q) | Q6 | **integrated** 52f9f4b5 + 4af3418f (follow-ups); integration check INTEG5E SHIP (0d0e238d) | test_opus2_stocking + Q6 suites | certify | integrator |
| Q8 | opus2/p0-listing-package, PR #5 | be96a598 | ACCEPT | none | **merged** (earlier) | test_opus2_listing_package | none: done | — |
| Q9 | opus2/p1-owner-queue-races, PR #6 | 23935b58 | ACCEPT | none | **merged** (earlier) | test_opus2_owner_queue_races | none: done | — |
| Q10 | opus2/p0-family-membership, PR #8 | d8d80301 | ACCEPT | none | **merged** (earlier) | test_opus2_family_membership | none: done | — |
| Q11 | claude/w4-INTEG8-next records | 42db54ae, 51e39992 and this file (docs/records only) | n/a (no code) | none | **integrated** (812f63d7; records suites 7/7 green) | none (no code) | re-merge at each records change | integrator |
| Q12 | codex/p0-learning-reference | 57c176a9 (claim only) | n/a: no code yet | — | no: **not started** | — | owner starts Codex; review its first push | Codex |
| Q13 | review / design records: claude/w4-PDFAUDIT-*, w4-DESIGNREVIEW-basket-1.3.0, w4-CONSTRUCTREVIEW-basket | docs only | n/a | none | yes (records) | none | fold into W5-INTEG1 as records at the next merge | integrator |
| Q14 | opus2/p0-tapestry | 67b67015, 71e26e6f | SHIP (OPUS2P) | none (independent of Q5: verified) | **integrated** W5-INTEG1 a0c6bfff + f7466c06 (fold_title de-dup), suites green incl. test_shadow; delta integration review INTEG5D SHIP (11272e4b) | test_opus2_tapestry_basket + pet/stocking/colourwork/launch0/shadow | certify | integrator |
| Q16 | opus2/p0-amigurumi | a9fac088..3b0a8867, c5671087 | DO NOT SHIP (OPUS2T-4 HIGH child safety; -5 MED) | Q14 | no: **blocked** on a construction-keyed children's refusal | named suites + childrens/pdf | delta review of the fix | opus2 |
| Q15 | opus2/p0-photo-asset-review (P0-PHOTO-ASSET-REVIEW) | c056028d, 5a47cd8e | **in review OPUS2S** | none known (merge-tree in review) | no: awaiting OPUS2S | photo/gallery/publish-gate suites | integrate on SHIP | integrator |
| Q17 | opus2/p0-construction-registry | 83194fb7..21d4ceaf, 66378ebf | DO NOT SHIP (OPUS2R-1 / OPUS2T-7 HIGH; OPUS2T-6 HIGH child safety) | Q16 | no: **blocked** | registry/tapestry/draft suites | delta review of fixes | opus2 |

Not integration items:
- #4: reference only, do not merge.
- #1: Codex draft, superseded.
- #2, #12, #13: review reports.
- claude/w5-INTEG1-trial and claude/w4-INTEG8-trial-adopt: trial branches, superseded.
- claude/w5-LEARNREF-parked-mainopus: parked; Codex owns that work.

## Integration review
INTEG5B (6d402593): SHIP for certification on W5-INTEG1 a8ce0072; its second regression batch re-run by the integrator on a8ce0072: 13/13 green (05:42Z). **Batch 5 certification run 20261102T054208Z-6424 on a8ce0072 started 05:42:08Z** (full, 864 suites, clean tree, dedicated worktree). Later additions need only a delta integration review.

## Batch 5 certification path
1. Q1 and Q2 pushed, then Q3, Q4 and Q5 on OPUS2M SHIP; Q11 and Q13 records alongside.
2. Q6 and Q7 if they reach SHIP before step 3 starts. Otherwise they ride the next batch.
3. Affected regression suites; one independent integration review of the W5-INTEG1 delta since
   0967c3ee; then ONE uninterrupted full suite (REQUIRE_CLEAN=1).
4. deploy_guard record, DRY_RUN, rollback rehearsal, then the owner's approval of the exact
   SHA, then deploy through ops/deploy.sh at once.
