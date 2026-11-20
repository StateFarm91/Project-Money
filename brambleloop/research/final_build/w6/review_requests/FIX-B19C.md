# FIX-B19C — fixes for independent review b19-c (units A and B)

Date: 2026-11-20 UTC. Base merged into both units: `claude/batch19-approve-all` 13585c4f
(contains b098fcce / 511a8c63). No PR opened; nothing deployed; no Railway variable read.
Venv from `requirements.lock` + `requirements-test.lock`. Runner:
`JOBS=4 SUITE_REGISTRY=0 SUITES="..." bash run_tests.sh`.

## Unit A — `eng/concepts-100`

Merge conflicts: DECISION_LOG (kept both), sw.js, autonomy_map.json (took base, regenerated
with `python -m brambleloop.autonomy.map --write ...`).

- **A1 FIXED.** `tests/test_concepts100.py`
  - `test_held_families_are_visible_and_never_dropped`: the set of non-empty
    `construction_unsupported:*` keys must be non-empty; each still-unbuilt family (amigurumi,
    hat, mosaic, c2c, cable) must have its own key and a `held` count in `by_family`; garments
    must be held under a non-empty set of `construction_unsupported:garment_*` keys (observed:
    `garment_raglan`, `garment_drop_shoulder`), the bare `construction_unsupported:garment` key
    must be absent, and every held construction key must appear held in `by_family`. No
    assertion deleted; the property is stricter than before (the by_family check now covers
    every held key, not six named ones).
  - `test_synthetic_scans_yield_100_evidence_backed_original_concepts`: the bare `garment`
    family is replaced by "some `garment_*` family is present and bare `garment` is not".
- **sw.js**: both sides changed SHELL files at v44 (concepts: `p0_board.js`; base: daily/demand
  views), so v45. `test_eng_demand_supply` pinned `'cc-shell-v44'` literally; it now checks
  `demand.js` is in the SHELL and VERSION >= 44 (the same form other shell tests use).
- **Clock flake fixed** (found while running the unit): `test_research_flow::
  test_a_never_succeeded_or_failing_source_never_reads_ok` read the board at wall-clock now
  while the fixture scanned at 06:00 UTC today, so after ~18:00 UTC the scanned shop read STALE
  and the final `== "OK"` failed. The board is now read with `now=S.at(0, 7)`. Assertions
  unchanged.
- **Housekeeping**: the merge commit accidentally included a `brambleloop/.venv` symlink to a
  scratch venv; removed in the follow-up commit.
- **Not addressed (still open):** A2 (b17-a C3: `distinct_lanes`/`distinct_refs`, ref
  re-resolution in `evidence_backed()`), A3 (b17-a C4: title-restatement 0.8 -> 0.6).

Suites: test_concepts100, test_vacuity, test_research_flow, test_eng_demand_supply,
test_s4_p0_board — 89 passing, 0 failing (run 20261120T223138Z-3131). Earlier wider run
(adds test_w4_f454_agents, test_w4_c12_wiring, test_v11_autonomy_timeline,
test_w4_credhealth, test_motif_backlog, test_eng_daily, test_v11_autonomy_orchestrator):
180 passing, the only failure was the clock flake above (fixed).

## Unit B — `eng/homedecor`

Merge conflicts resolved as the verdict suggests: BUILD_STATE, DECISION_LOG,
construction_families.md (kept both); construction_families.py (both family lists; the
declared-vs-family check is `... and not ({family, declared} <= tapestry/CW pair and basket)
and not (declared == VESSEL and family in HD.VARIANTS)`, plus base's lovey rename);
test_eng_families.py (admitted set = base's union `*HD.VARIANTS`; probe lists unioned);
autonomy_map.json (base, regenerated).

- **B1 FIXED.** The inner `honest = next(...)` is now `honest_fams`; `honest` stays the
  feature -> families dict. test_eng_families: 0 failures.
- **B2 FIXED, cause isolated.** Not the pdf.py hand-merge: on eng/homedecor alone the lidded
  basket's disclosed renders were already refused ("round pieces with no structural
  placement") and `schematic_for` returned None (no `cir.assembly`). It only passed there
  because PremiumStandard (`publish/pdf_standard.py`) did not exist on that base. Fix,
  without touching PremiumStandard:
  - `publish/schematic.schematic_for`: a multi-piece design with no seams (pieces worked
    separately) is drawn when **every** piece has a measured `Footprint` from
    `cir.assembly.assemble` — side by side, no joins. So the cover gets the schematic hero with
    `COVER_SCHEMATIC_CAPTION` ("a rendering, not a photograph") and the construction page gets
    the Schematic + FINISHED MEASUREMENTS block (basket 19.2 x 15.9 cm, lid 22.4 x 2.2 cm).
    Designs with seams are unchanged; any unmeasured piece still yields None.
  - The schematic paragraph says "The pieces are worked separately and are not sewn together"
    when there is no assembly, rather than "with the joins that make it one object".
  - Cover text: `makes_words` for a single component ("Makes 4 coasters", unchanged, its unit
    test unchanged); several components name their pieces: "In 2 pieces: 1 basket, 1 lid".
    Overview size sentence: B's version.
  - Pinned in `test_a_research_lidded_basket_certifies_with_a_fitting_lid` (US and UK: piece
    names on the cover, no "Makes 2 baskets", rendering label in the cover text, "not sewn
    together", schematic labels == {basket, lid} with no arrows/closures). Mutant: cover back
    to `makes_words` for multi-piece -> killed.

Suites: test_eng_families, test_eng_homedecor, test_vacuity, test_pdf_premium,
test_pdf_standard, test_compiler, test_schematic, test_eng_garment, test_eng_plush,
test_eng_colourwork — 179 passing, 0 failing (run 20261120T224000Z-4441), then
test_eng_homedecor rerun with the new assertions: 0 failures.

## For the reviewer

- Noticed, not changed: the lidded basket's cover "Finished size" reads "19.2 cm across the
  points" (hexagon wording on a round-family vessel). Pre-existing on eng/homedecor alone.
- B3 (rebase before integration): done by merging the batch19 base into the branch.
