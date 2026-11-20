VERDICT: SHIP 705b739d86fd626429e77308a5e6f7d6133acf31

Delta review of origin/eng/research-flow @ 705b739d over ecb5ce0c. Base origin/claude/w6-INTEG2 @ cde89a4b. Merged tree built (conflicts only in BUILD_STATE.md, scripts/suite_final_segment.txt, sw.js; resolved mechanically, both sides kept except sw.js taken from the unit).

## Findings

### HIGH / MEDIUM
None.

### LOW
- **L1 `node --check` is not a reliable gate for these files.** On this node (v22.23.5) `node --check x.js` returns 0 even for a file with an injected `}}}(`; only `.mjs` is actually parsed. I checked the real `static/js/views/p0_board.js` (and every view in that directory) as a `.mjs` copy: all parse cleanly. The real guard is `test_v11_pwa_browser`, which does catch a broken p0_board.js (mutation below). Recommend the review request say "parsed as ESM" rather than `node --check`.
- **L2 `intel/research_flow.py:463` (`health_of`)** is correct, but the three off-Etsy rows (`research_flow.py:368-377`) are `UNKNOWN` by construction and will stay so; that is intended and shown as a limitation.
- sw.js: unit sets `cc-shell-v35`; see VERSION note.

## Previous findings: truly fixed? (each mutated, each killed)
- H1 honest qualifiers: FIXED. `proposal_writer.brief_for` (proposal_writer.py:277) derives `silhouette_qualifiers` via `creative.intake.qualifiers_for(creative_concept(...))`; the end-to-end concept (`housewarming`, reading chair in a new home) honestly qualifies. Mutation: replace with the constant `["motif_composition"]` -> 3 tests fail (`..._an_honestly_qualifying_proposal_clears_the_gates...`, `..._a_generic_concept_with_no_qualifier_is_held_by_108...`, `..._the_brief_is_derived_from_the_concept_not_a_constant`). Mutation: drop the `not held_by_108` / gate_refused clause from `qualifying` -> `test_a_generic_concept_with_no_qualifier_is_held_by_108_and_says_so` fails. A generic concept is held by #108 and the reason is surfaced.
- H2 p0_board.js syntax + browser suite: FIXED. File parses (ESM); `test_v11_pwa_browser` passes; appending a syntax error -> browser suite fails ("Could not load... Unexpected token").
- M1 per-row pill never OK for a never-succeeded or failing source: FIXED. Mutating either the never-succeeded branch or the failing branch of `health_of` -> `test_a_never_succeeded_or_failing_source_never_reads_ok` fails.
- M2 website / YouTube / Pinterest rows: FIXED. `competitor_websites`, `youtube`, `pinterest` present as `kind="offsite"`; mutating the offsite branch -> `test_the_off_etsy_channels_of_mp1_2_s4_are_visible_as_unavailable` fails.
- NINE research shops scheduled: CONFIRMED. `research_flow.sources()` yields 9 shop sources equal to `len(watchlist.WATCHLIST)`: mjs_off_the_hook_designs, madeline_mae_co, zkbdesigner, the_easy_design, hanjan_crochet, ivyloop, loveandstitch_designs, firefly_crochets, artlove_desing (ArtLoveDesing included). `test_watchlist_cadence` passes.

## Suites (merged tree, `PY=venv python`, JOBS=2)
`TOTAL PASSING: 577 ; suites failing: 0` (0 environment failures)
- test_research_flow, test_v11_pwa_browser, test_v11_pwa_static (84/0), test_s4_p0_board, test_w5_concept_intake, test_prospecting, test_watchlist_cadence, plus guards test_vacuity, test_w3_tmp_hygiene, test_w4_resume_runner, test_w4_c12_wiring, test_v11_autonomy_timeline, test_w4_adopt_manual_listing: all pass.
- autonomy_map.json: no regeneration needed.

## sw.js VERSION
Unit sets `cc-shell-v35` (base v33). No equal-number collision with eng/catalogue (v34) or eng/families (v33 unchanged), but both catalogue and research-flow rewrite the same VERSION line, so the second to merge needs a rebump (v36+ if both numbers are kept).
