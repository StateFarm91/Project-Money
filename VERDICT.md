# Independent review b19-c: eng/concepts-100 66833c52, eng/homedecor d4f08d43, eng/gallery-complete e718a1b9

Reviewer: independent Claude Code session, 2026-11-20 UTC. Base b098fcce (eng/colourwork head). No secrets or Railway variables read, no PR opened.
Merges in scratch worktrees; venv from requirements.lock + requirements-test.lock; `JOBS=4 SUITE_REGISTRY=0 SUITES="..." bash run_tests.sh`.

| unit | merge | suites | mutation | verdict |
|---|---|---|---|---|
| A eng/concepts-100 | conflicts (docs, sw.js, map) | 196 passing, **1 suite failing** (test_concepts100, 2 tests) | killed | **BLOCK** (A1) |
| B eng/homedecor | conflicts incl. code (pdf.py, construction_families.py, test_eng_families.py) | 115 passing, **2 suites failing** (test_eng_families, test_eng_homedecor) | killed | **BLOCK** (B1, B2) |
| C eng/gallery-complete | docs only (DECISION_LOG) | 180 passing, 0 failing | killed | **SHIP** |

Run records: A 20261120T160701Z-1795, B -1798, C -1797 (each in the worktree's artifacts/suite_runs).

## Merge notes
- A: DECISION_LOG (keep both), sw.js (take A's v44; base is v43 from eng/daily), autonomy_map.json (take base, regenerate with `python -m brambleloop.autonomy.map --write src/brambleloop/autonomy/autonomy_map.json`).
- B: BUILD_STATE, construction_families.md (keep both); construction_families.py (keep both family lists; the declared-vs-family check must read `... and not (tapestry/CW pair) and not (declared == VESSEL and family in HD.VARIANTS)`); test_eng_families.py (union admitted set + `*HD.VARIANTS`, union of the tuple list); pdf.py (cover: keep `makes_words`, but name the pieces for several components; overview size sentence: B's version). My pdf.py resolution is a judgement call, see B2.
- C: DECISION_LOG only (keep both).

## Unit A: re-review of b17-a
- **C1 FIXED.** research_flow.py adds only `concept_pool`; `benchmark_shopping` is no longer registered twice. test_research_flow passes on the merge.
- **C2 FIXED.** `originality()` returns a hold (`HELD_NO_CARDS`) when the pod has no benchmark cards and `classify` makes it HELD, never READY. Tests `test_a_concept_matching_an_observed_listing_card_is_refused_as_a_copy`, `test_a_pod_with_no_benchmark_cards_is_held_not_ready`, `test_classify_holds_on_unknown_originality`. Mutants `twin = ""` and dropping the hold are each killed.
- **C3 NOT ADDRESSED (Medium).** No `distinct_lanes` / `distinct_refs` in `health()`; `evidence_backed()` still does not re-check the refs resolve to fresh listings.
- **C4 NOT ADDRESSED (Low).** Title-restatement threshold is still 0.8.

### Findings (A)
1. **A1. High (integration, BLOCK).** On base b098fcce (garment engines now exist) `test_concepts100` fails: `test_held_families_are_visible_and_never_dropped` (garment reasons are now mixed `construction_unsupported:garment_raglan` / `garment_drop_shoulder`, no `construction_unsupported:garment`) and `test_synthetic_scans_yield_100_evidence_backed_original_concepts` (the `garment` family assertion at test line ~154). *Fix:* rebase on b098fcce and update both tests to the real held-family keys (assert the set of `construction_unsupported:*` keys is non-empty for the still-unbuilt families: amigurumi, hat, mosaic, c2c, cable; check garment against `garment_raglan`/`garment_drop_shoulder`, not the bare name). Do not delete the assertions.
2. **A2. Medium.** C3 above. *Fix:* as in b17-a C3.
3. **A3. Low.** C4 above. *Fix:* 0.6 plus the shared-run rule from market_fit.overlap.

## Unit B: re-review of b17-b
- **Finding 1 FIXED.** `findings()` returns error `VESSEL_GEOMETRY_UNKNOWN` when the twin has no readable rings, and when a round/bowl/lid claim sits on a non-magic-ring base. Tests: `test_a_vessel_name_with_no_readable_twin_geometry_is_an_error_not_silence`, `test_a_round_vessel_not_worked_from_a_magic_ring_cannot_pass_the_flat_base_check`. Mutant (`if not rings` -> `if False`) killed.
- **`spans` mutant KILLED.** `test_a_bridging_chain_with_spans_is_not_an_increase` fails when the `spans` exclusion is removed.
- On its own base (d4f08d43 alone) every test_eng_homedecor and test_eng_families test passes; both failures below appear only on the integrated tree.

### Findings (B)
1. **B1. High (BLOCK).** `test_eng_families::test_every_named_feature_is_held_for_every_admitted_family` raises `TypeError: 'frozenset' object is not subscriptable`. The branch reassigns `honest` inside the loop (`honest = next(h for f, _, h in CF.NAMED_FEATURES ...)`), clobbering the dict built before the loop, so the second iteration indexes a frozenset. It only surfaces now that base has more admitted families. *Fix:* rename the inner variable (e.g. `honest_fams`) and leave `honest` the dict.
2. **B2. High (BLOCK, cause not isolated).** On the merge, `test_a_research_lidded_basket_certifies_with_a_fitting_lid` is refused by PremiumStandard: "cover hero is labelled neither as a rendering nor as a photograph; schematic: missing 'FINISHED MEASUREMENTS'". It passes on d4f08d43 alone, so base's PDF requirements for multi-piece items now bite the lidded basket. My hand-merge of pdf.py (cover/overview text) may be a contributing factor; I did not isolate it. *Fix:* rebase eng/homedecor onto b098fcce, resolve pdf.py with `makes_words` kept for the single-component case and `_pieces_words` for several, then rerun test_eng_homedecor until the lidded test passes; if it still fails, the multi-component path must emit the cover rendering label and the FINISHED MEASUREMENTS schematic block. Do not relax the family requirements.
3. **B3. Low.** Branch conflicts with base in code, not only docs; B must be rebased before integration (b17-b said docs-only; base has moved).

## Unit C: eng/gallery-complete (SHIP)
Covers D-OWNER-GALLERY-COMPLETE. Verified:
- `lifecycle.derive` yields LISTING_READY only when a valid listing-set certificate names >= `CAMPAIGN_MIN_FRAMES` (7) frames; otherwise VISUAL, "gallery incomplete". Unreadable/missing certificate is never complete.
- `etsy_ops.certified_frames` adds a `gallery incomplete` problem for a short set; `certified_images` (the one upload path) inherits it, so nothing is uploaded: `fake.uploads == []`, publish blocked, review not run (test_search_hero_publish, test_w4_disclosedqa, test_disclosed_certified_upload).
- Fixtures are complete: fixtures extended to 7+ certified frames with positions `1..n` and the same frame-kind and alt-text assertions. No assertion weakened: the only removed asserts (`ranks == [1,2,3]`, `len(uploads) == 3`, image_order `[1,2,3]`) are replaced by `range(1, n+1)` / `>= CAMPAIGN_MIN_FRAMES` forms, and `> 3` became `>= CAMPAIGN_MIN_FRAMES`.
- Mutations: `>= CAMPAIGN_MIN_FRAMES` -> `>= 1` in lifecycle killed by `test_partial_gallery_is_not_complete`; disabling the etsy_ops check killed by `test_a_partial_gallery_is_not_served_so_it_is_not_reviewed` (test_w4_disclosedqa).

### Findings (C)
1. **C1. Low.** `test_certified_frames_refuses_a_partial_gallery_in_source` only greps the function source; it passes with the check disabled (verified). Behavioural tests do kill the mutant, so not blocking. *Fix:* delete it or replace it with a call to `certified_frames` on a 6-frame certificate asserting the `gallery incomplete` problem.
2. **C2. Low.** Completeness is `len(frames) >= 7`; it does not require distinct positions 1..7 or distinct asset ids. *Fix:* in `_complete_gallery` and `certified_frames` also require `len({f["asset_id"] for f in frames}) == len(frames)` and positions `== 1..n`.

## Order of integration
C now; A after A1; B after B1 and B2 (rebase onto b098fcce first).
