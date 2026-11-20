# FIX-CONCEPTS-DECOR: fixes for review b17-a Unit C (eng/concepts-100) and b17-b Unit C (eng/homedecor)

Fixer session, 2026-11-20 UTC. Nothing was force-pushed, no PR was opened, and no Railway variables or secrets were read.
Both branches merged `origin/claude/w6-INTEG6` (dde3ea62). Suites ran with a fresh venv built from requirements.lock and requirements-test.lock:
`JOBS=4 SUITE_REGISTRY=0 SUITES="..." bash run_tests.sh`, on the clean committed tree.

| branch | was | fix commit | suites | result | run id |
|---|---|---|---|---|---|
| eng/concepts-100 | f6a23e46 | `5af91b60599ea0987f59ed5eb727b2dd7b91532d` | test_concepts100, test_vacuity, test_w4_resume_runner, test_w4_readback_evidence, test_s4_p0_board, test_v11_pwa_static, test_research_flow, test_v11_autonomy_timeline, test_compiler, test_reverse, test_twin | **255 passing, 0 failing** | 20261120T132742Z-20637 |
| eng/homedecor | 33de16ac | `6cbe6e18c5bae0884758c19cfc385cc45d0d1f5f` | test_eng_homedecor, test_vacuity, test_w4_resume_runner, test_v11_autonomy_timeline, test_compiler, test_reverse, test_twin | **107 passing, 0 failing** | 20261120T134404Z-8092 |

This file is committed on top of each fix commit, so each branch head is one docs-only commit past the SHA above.

## eng/concepts-100 (b17-a Unit C)

- **Merge.** Conflicts resolved:
  - p0_board SECTIONS keeps `motif_recovery` and `concept_pool`.
  - orchestrate UPSTREAM_INPUTS keeps INTEG's learn and improve entries plus both `radar.concept_pool` entries.
  - sw.js is **cc-shell-v44**.
  - BUILD_STATE and DECISION_LOG keep both sides.
  - autonomy_map.json was regenerated: 149 cadences, 181 handlers.
- **C1 (fixed).** The duplicate `_src("benchmark_shopping", ...)` was removed from `intel/research_flow.sources()`. test_research_flow passes on the merged tree.
- **C2 (fixed).**
  - `concept_pool.originality()` returns `holds=[HELD_NO_CARDS]` when the pod has no benchmark cards. `classify()` then returns HELD, never READY, because UNKNOWN originality is not a pass.
  - New tests:
    - `test_a_concept_matching_an_observed_listing_card_is_refused_as_a_copy`: a listing whose card reads back to a READY concept's card makes that concept REFUSED with a `copy:` reason.
    - `test_a_pod_with_no_benchmark_cards_is_held_not_ready`.
    - `test_classify_holds_on_unknown_originality`.
  - The fixture titles now state a feeling ("Vintage ..."), so every fixture pod has comparable cards. Before this, the copy check never ran in the fixture.
  - Mutants run:
    - `twin = ""` is now killed (the copy test fails).
    - Removing the no-cards hold is now killed.
- **Demand and core families.**
  - The pool is already demand-led: `priority_of` scores listings, shops and favourites.
  - Core weighting follows D-OWNER-CORE-FAMILIES: amigurumi, baby and pillow x1.5; garment x1.25; MadelineMaeCo x1.5.
  - Both teardowns on eng/gallery-complete (highland cow, capybara) are MadelineMaeCo-style amigurumi bestsellers, which is consistent with that weighting.
  - New test `test_core_families_outrank_plain_lanes_at_equal_demand_and_demand_still_leads`:
    - Amigurumi, baby, pillow and garment lanes outrank a plain lane at equal demand.
    - Strong demand in a plain lane still outranks thin demand in a core lane.
  - No weight was changed.
- **Production effect to note.** `blinded.from_listing` reads a card only from a title that states a product form and a feeling. In a live pod where no observed title does, every concept is now HELD with `HELD_NO_CARDS` instead of READY.
- **Open (not fixed here).** C3 (lane-level lineage, `distinct_lanes` / `distinct_refs`, freshness re-check) and C4 (the 0.8 title threshold).

## eng/homedecor (b17-b Unit C)

- **Merge.** BUILD_STATE and DECISION_LOG conflicts were resolved by keeping both sides. autonomy_map.json was regenerated (generated_at only).
- **Finding 1 (fixed).** `creative/homedecor.findings` emits `VESSEL_GEOMETRY_UNKNOWN` (ERROR) in two cases:
  - The body twin has no readable rings (no twin, or `geometry is None`). It then returns.
  - A round, bowl or lid claim sits on a base whose `foundation_kind` is not `magic_ring`.
- **Finding 5, the `spans` survivor (fixed).** `test_a_bridging_chain_with_spans_is_not_an_increase` checks three things:
  - The handled vessel's opening rounds consume no increases.
  - The body's corner count is the same with and without the opening rounds.
  - A `ch` ResolvedOp with `spans>0` is not an increase, and the same op with `spans=0` is.
- **Mutants.**
  - Dropping `and not getattr(op, "spans", 0)` is killed by `test_a_bridging_chain_with_spans_is_not_an_increase`.
  - Changing the UNKNOWN branch to `return []` is killed by `test_a_vessel_name_with_no_readable_twin_geometry_is_an_error_not_silence`.
- **Not done.** Findings 2, 3, 4, 6 and 7 belong to other units or the base, so they were left alone. The full unfiltered suite was not run.
