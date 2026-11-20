VERDICT: DO NOT SHIP

Reviewed origin/claude/w6-INTEG2 (64146306) and origin/claude/w6-INTEG3 (307c7e62). Suites run on INTEG3 HEAD with a venv from requirements-test.lock: 459 passing, 2 suites failing. Both failures are real and neither is an environment problem.

## Blocking findings

1. **Mutation survives (Unit A).** I mutated `_disclosed_mobile` so `missing = []`, which ignores renders that are not on file. test_cert_publish_gates, test_w4_visnext_frames, test_cert_listing_frames, test_disclosed_render, test_disclosed_render_runtime and test_w4_disclosedqa still passed 74/74. No test covers the new disclosed-set block: a missing stored render must give not_rendered, blocks_release and COMMERCIAL_QA not_run. By the stated criterion this is a finding. The code logic reads correctly, but it is unpinned. Fix: add a test that deletes a stored render and asserts all three.
2. **test_research_flow fails on INTEG3 HEAD.** `test_every_research_cadence_is_in_the_registry_and_every_mandatory_shop_too` reports `['intel.benchmark_shopping']`. The benchbuy merge (36c281c2) added the cadence at worker.py:1003 but did not add it to the research_flow source registry. This is an integration gap. The `intake_refused` stage itself is intact (STAGES, research_flow.py:101 and :166).
3. **test_w4_readback_evidence fails on INTEG3 HEAD.** `test_readback_evidence_cli_never_prints_the_token_and_keeps_unknown_apart` fails because the visual_pipeline row (ENG-VISUAL, ops/readback.py) makes the row count 17. The test at line 586 still asserts `len(out["items"]) == 16`. The conflict resolution did not update the count.

## Unit A (INTEG2 64146306)
- **No gate is weakened.** The diff only adds blocking logic. The new check also reads stored renders at publish time, which the earlier code did not.
- **Missing render blocks.** In `disclosed_listing_set`, a missing render sets `complete` and `ok` False and lists it in `not_rendered`. It then forces COMMERCIAL_QA to `not_run` and appends a reason, so `blocks_release` is True. By reading, this is correct. Finding 1 says no test proves it.
- **Minor.** If `rec.qa.mobile` is absent, `_disclosed_mobile` returns None and this block adds no reason. I did not verify whether `usable_as_listing_asset` already covers that case.
- **F4 test.** The rewrite follows #39 "holds publication only" (`policy_publication_only`). It still asserts that a growth-affecting change blocks the marketing rebuild, so it keeps its invariant.
- **qa_stage test.** It now runs `listing_set(..., store_renders=True)` on the current set, so it still checks that renders exist in the store. It no longer checks the set that launch.plan saw, which the ENG-SUPPLY chain-order change makes unavoidable.
- **suite_final_segment.** The test_eng_recovery declaration is in cde89a4b, which is below the review range. It is present.

## Unit B (D-OWNER-POLICY39-OVERRIDE, 4717887d and fb012fb3)
- **Recorded honestly.** The basis is "owner directed proceeding without review" and `reviewed` is False. DECISION_LOG says the same.
- **Scope is correct and tested.** The override covers only `listing_image_rules` with `checked_on <= 2026-11-20`. Undated, later and other-source changes still hold. test_owner_policy39_override passes (4 tests).
- **Suites that `.clear()` the override** (approvals, gatesi, prodfix_policy_review, prodfix_review) do so at import, so the generic #39 hold and review mechanism is tested on fixture changes. All pass.
- **Finding, non-blocking.** DECISION_LOG and the commit message say the readback lists the override under `overridden_changes`. Nothing outside platform_policy.py calls `overridden_changes`, and ops/readback.py has no such row. The override is invisible on every operator surface, so the record claims something that does not exist. Wire it into readback or correct the record.
- **Related.** `unreviewed_changes` call sites (release.py, approvals, policy_readings) now silently drop the overridden change. The owner is not shown it anywhere.

## Batch 13 resolutions (39b92619..307c7e62)
- **Motif-backlog revert:** clean. The only remaining mention is a guarded stub in production_evidence.py (`_vp_recovered`). It imports `visual.motif_backlog` inside a try and degrades to UNKNOWN, and the module imports fine.
- **Static bundle trims** (0a1d3037): the removed lines are all `//` comments in store.js and approvals.js, with no code removed. The catalogue.js and agents_evidence.js trims are in 383315fb, which I did not diff in full.
- **Catalogue perf bound:** BOUND_SECONDS = 2.0, and the suite passes.
- **p0_board SECTIONS and test_s4_p0_board:** pass.
- **production_inventory load_records:** no dropped behaviour found, and the dependent suites pass.
- **Dropped behaviour:** findings 2 and 3 above are resolutions that left a test stale.

## Suites on INTEG3 HEAD
Passing: test_cert_publish_gates, test_owner_policy39_override, test_w4_gatesi, test_w4_prodfix_policy_review, test_eng_approvals, test_w4_listready, test_s4_p0_board, test_v11_pwa_browser, test_eng_catalogue_perf.
Failing: test_research_flow (1 test), test_w4_readback_evidence (1 test).
