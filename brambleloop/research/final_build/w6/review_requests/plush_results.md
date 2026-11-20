# [ENG-PLUSH] Suite and mutation results

- **Branch:** `eng/plush`.
- **Tree:** the 2763340 work plus the follow-up commits. This branch is shared with the
  ENG-PLUSH-FIX session, whose review fixes were merged at d781499.

## Suites

**Run:** every suite that imports a module this work changed (a grep over `tests/`), plus the
brief's list: 256 suites at parallelism 3. A 2-hour limit stopped the run at 254 of 256.

| Outcome | Suites |
|---|---|
| Pass | 239 |
| Failed, then fixed on the branch and re-run green | `test_garments` (a graded child garment was in the toy gate; garments keep `intel.childrens`' constraints), `test_fastlane` (`child_safety` added to `CANONICAL_STAGES` and `CONDITIONAL_STAGES`), `test_s1_fix_size_families` (a lovey now has an engine; "Baby Lovey" is refused for its head), `test_w4_resume_runner` (`test_eng_plush` declared in the final segment) |
| Pre-existing: fails identically on untouched base 809107b | `test_cert_parity_copy` (listing tag count), `test_cert_publish_gates` (context-render hashes), `test_cert_rebuild_chain` (launch readiness, divergent listing) |
| Inherited from `eng/families`: passes on base, fails identically on INTEG3 | `test_r5_research_2`, `test_r5_research_3`, `test_r5_research_4`, `test_ws2_r5_proposal_writer`, `test_ws2_research_m2` (a research coaster concept is now held `construction_unsupported:flat_panel`) |
| Timed out under load (re-run separately, see below) | `test_acceptance_gates`, `test_physical`, `test_product_run` |
| Not started before the limit (re-run separately) | `test_w5_a9_package_event`, `test_w6_listing_chain_e2e` |

The earlier run's `test_cert_lanes_capacity` and `test_cert_orders` failures read "runtime graph
source changed during analysis". They were artifacts of editing files mid-run, and both passed
in the clean run.

**Re-run of the timeouts:** never recorded by the ENG-PLUSH session. Treat those five suites as NOT RUN here. The ENG-PLUSH-FIX round-2 run below covers the review's own list, not these five.

## Mutation

`scripts/mutate_plush.py` weakens each new rule in a scratch copy of the tree; `test_eng_plush`
must kill it.
- 43 of 44 were killed in the full run.
- The survivor ("a closed piece in rounds is not a toy") was shadowed by the stuffed-figure
  rule. It got a direct test (an earless stuffed ball named "Juniper Friend") and is now KILLED.
- ENG-PLUSH-FIX has since extended the harness. It now requires a green baseline and reports an
  ERROR instead of a false KILLED.

## Owner action required (one item, batched)

**OWNER ACTION: a standing children's decision for adult cushion covers.**
- **Exact action:** decide, in writing, whether envelope-back and appliqué cushion covers that
  carry no child words are home decor and not merchandised to a child. If yes, they can be
  exempted through `launch0.NOT_MERCHANDISED_TO_A_CHILD`, design by design or as a family rule.
- **Why it is required:** A1-R holds every closed stuffed form for an explicit decision. A cover
  lists a pillow-form insert, so every cushion PDF is held, on nobody's decision, until the
  owner makes one.
- **Maximum cost:** CA$0.
- **Minutes required:** about 5.
- **Consequence of waiting:** the cushion families certify, but no cushion PDF or listing can be
  produced.

## ENG-PLUSH-FIX round 2 (measured at f95e603)

- **Suites:** run `20261120T130816Z-22908`, `PY=python3 JOBS=1 SUITE_REGISTRY=0`, tree clean at start.
  - It covered the 27 suites the review listed, plus test_vacuity, test_w4_resume_runner, test_garments, test_fastlane and test_s1_fix_size_families. The two lists overlap, so the run was 30 suites.
  - **TOTAL PASSING: 565; suites failing: 0.** 1811 s.
  - The previous run, at 098e119 (`20261120T123732Z-2109`, JOBS=2), had the same result: 565 passing and 0 failing.
- **Mutation:** `MUTATE_JOBS=3 python3 scripts/mutate_plush.py` at f95e603. The baseline was green.
  - **65 of 65 killed, 0 survived, 0 errored.**
  - At 098e119 it was 64 of 65. The survivor was "pdf ignores the age band". The test now asserts the older eye-options reading itself, not the band label, which the children's statements also print.
