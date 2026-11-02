# Continuous integration queue: every completed engineering branch

Owner directive 2026-11-02, "Permanent continuous integration". The integrator maintains this
file and processes eligible items at every wake-up, before writing any status report.
Target for all items: `claude/w5-INTEG1` (Batch 5). Integration is not deployment.
Last updated: 2026-11-02T18:55Z. Owner decision I-P0-ABSOLUTE-WORKFORCE: priority 1 safety/correctness, 2 missing autonomous connections, 3 integration/certification/deploy, 4 24 h acceptance, 5 enhancements. Certification target: W5-INTEG1 50937469 (INTEG5F SHIP). Running now: 20261102T101632Z-4284 on 4af3418f (expected FAIL test_swarm_runtime). Known open in the candidate: P0-NAME-OBJECT-MISMATCH and OPUS2V-2 (disclose).

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
| Q3 | opus2/p0-revenue-workforce, PR #3 | 558e7ca9..fed859b7, 8ed2dd15 | DO NOT SHIP (OPUS2U-1 MED; OPUS2T-1/-2/-3 HIGH open) | none in target | no: **blocked** | test_opus2_size_claims, test_launch0*, test_opus2_draft_constructions, test_vacuity | delta review of fixes | opus2 |
| Q4 | opus2/p1-culture-sweep-timeout, PR #7 | e0be7c4d (tests only) | SHIP (OPUS2M) | Q1 | **integrated** (W5-INTEG1 a8ce0072, suites green) | test_opus2_culture_sweep_timeout | none; OPUS2M-5 and -6 LOW follow-ups for opus2 | — |
| Q5 | opus2/p0-cir-colourwork, PR #9 | d4486b8c..e6e6fb94 | DO NOT SHIP (OPUS2U-3 MED regressions) | Q2 | no: **blocked** | as Q2 | delta review of the fix | opus2 |
| Q6 | opus2/p0-pet-bed, PR #10 | d0a7685f, 7d220e01, 940f70e6, 09122165 | SHIP (OPUS2O) | none (split from PR #3: I-B5-SPLIT-PET-STOCKING) | **integrated** W5-INTEG1 52f9f4b5 (suites running, push on green) | test_opus2_pet_bed, test_opus2_draft_constructions, test_fallback_draft_provenance | push; Batch 6 | integrator |
| Q7 | opus2/p0-stocking, PR #11 | ..a859f6fe, d3a485a1, 7493c723 | SHIP (OPUS2O, OPUS2Q, OPUS2U) | Q6 | **integrated** 52f9f4b5, 4af3418f, 45977d4c | test_opus2_stocking + Q6 suites | certify | integrator |
| Q8 | opus2/p0-listing-package, PR #5 | be96a598 | ACCEPT | none | **merged** (earlier) | test_opus2_listing_package | none: done | — |
| Q9 | opus2/p1-owner-queue-races, PR #6 | 23935b58 | ACCEPT | none | **merged** (earlier) | test_opus2_owner_queue_races | none: done | — |
| Q10 | opus2/p0-family-membership, PR #8 | d8d80301 | ACCEPT | none | **merged** (earlier) | test_opus2_family_membership | none: done | — |
| Q11 | claude/w4-INTEG8-next records | 42db54ae, 51e39992 and this file (docs/records only) | n/a (no code) | none | **integrated** (812f63d7; records suites 7/7 green) | none (no code) | re-merge at each records change | integrator |
| Q12 | codex/p0-learning-reference | 623fc26c; bd215b08 (CODEX1-3 fix only) | DO NOT SHIP (CODEX1: -1 HIGH library guard refuses default /app path, -2 HIGH JOB_CLASS missing, -3 MED review bypass via lessons) | none (3 mechanical conflicts) | no: **blocked** on CODEX1 fixes | test_image_reference_hash_failclosed, test_originality, test_w3_k11_authority + Codex's own suites | Codex fixes CODEX1-1/-2 HIGH (still open at bd215b08); one delta review once both HIGH fixes land | Codex |
| Q13 | review / design records: claude/w4-PDFAUDIT-*, w4-DESIGNREVIEW-basket-1.3.0, w4-CONSTRUCTREVIEW-basket | docs only | n/a | none | yes (records) | none | fold into W5-INTEG1 as records at the next merge | integrator |
| Q14 | opus2/p0-tapestry | 67b67015, 71e26e6f | SHIP (OPUS2P) | none (independent of Q5: verified) | **integrated** W5-INTEG1 a0c6bfff + f7466c06 (fold_title de-dup), suites green incl. test_shadow; delta integration review INTEG5D SHIP (11272e4b) | test_opus2_tapestry_basket + pet/stocking/colourwork/launch0/shadow | certify | integrator |
| Q16 | opus2/p0-amigurumi | ..98d216b0 | DO NOT SHIP (A1-REVIEW: A1-1 HIGH, A1-2..-5 MED; toy delta itself acceptable) | Q14; a fixed, independently tested A1 | no: **blocked** on A1-1..-5 | test_opus2_a1_children, test_opus2_amigurumi, test_childrens, test_launch0, test_pdf_premium | opus2 fixes; delta review | opus2 |
| Q15 | opus2/p0-photo-asset-review (A3, P0-PHOTO-ASSET-REVIEW) | c056028d..8d98bf4c | OPUS2S/OPUS2W DO NOT SHIP; fixes 8d98bf4c under delta review A3D (18:40Z) | none | no: **in review** | test_opus2_photo_asset_review, test_w4_launchfix, photo/gallery/publish-gate suites, test_swarm_runtime | integrate on A3D SHIP | integrator |
| Q17 | opus2/p0-construction-registry | ..a7b34050 | DO NOT SHIP (OPUS2V-1 HIGH, -3 HIGH child safety, -2/-4 MED) | Q16 (carries the toy) | no: **blocked** | registry/tapestry/draft suites | delta review of fixes | opus2 |
| Q18 | opus2/p0-pouch (split of pouch + stuffed finishing) | 9e0c653a..1ea3079e | SHIP (OPUS2P, OPUS2V) | none | **integrated** W5-INTEG1 50937469 (12 suites green; INTEG5F SHIP) | test_opus2_drawstring_pouch, test_opus2_stuffed_finishing + draft/tapestry suites | push on green; certify | integrator |
| Q19 | opus2/a2-name-object (A2, P0-NAME-OBJECT) | db463142..3be8262f | DO NOT SHIP (A2-REVIEW: A2-1/-2/-3 HIGH, -4/-5/-6 MED) | none (merge with INTEG1 7c42e706 clean) | no: **blocked** on A2 fixes | test_opus2_a2_name_object + 28 draft/routing suites (green on merged tree) | opus2 fixes; delta review | opus2 |
| Q20 | opus2/p0-child-safety-core (A1-R) | not pushed | n/a | none | no: **not started** | A1-R acceptance suites | opus2 builds; delta review | opus2 |
| Q21 | claude/w5-A5-correction-loop (A5, P0-CORRECTION-LOOP) | building | n/a | none | no: **in build** (mainopus-worker, since 18:55Z) | test_w5_a5_correction_loop + swarm/authority/shadow/launch0/gate suites | independent review on push | mainopus-worker |
| Q22 | claude/w5-A7-supply-stall (A7, P0-SUPPLY-STALL) | building | n/a | none | no: **in build** (mainopus-worker) | test_w5_a7_supply_stall + radar/swarm suites | independent review on push | mainopus-worker |
| Q23 | claude/w5-A9-package-event (A9, P0-PACKAGE-EVENT) | building | n/a | none | no: **in build** (mainopus-worker) | test_w5_a9_package_event, test_opus2_listing_package | independent review on push | mainopus-worker |
| Q24 | claude/w5-A4a-research-to-concept (A4a, P0-RESEARCH-TO-CONCEPT) | building | n/a | none | no: **in build** (mainopus-worker, since 19:05Z) | test_w5_a4a_research_to_concept + concept_intake/research/knowledge_gaps/originality suites | independent review on push | mainopus-worker |
| Q25 | claude/w5-V1-visual-correctness (V1, P0-VISUAL-CORRECTNESS) | building | n/a | none | no: **in build** (mainopus-worker, since 19:00Z) | test_w5_v1_visual_correctness + image_production/flux suites | independent review on push | mainopus-worker |
| Q26 | opus2/a4b-enrichment (A4b) | 823a82dd, b0c66556 (unpushed) | n/a | none | no: **not pushed** | A4 acceptance | opus2 pushes; delta review | opus2 |

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
