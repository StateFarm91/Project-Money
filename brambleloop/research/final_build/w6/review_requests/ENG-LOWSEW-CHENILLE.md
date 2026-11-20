# Review request — ENG-LOWSEW-CHENILLE

- **Branch:** `eng/lowsew-chenille` (builder branch; NOT reviewed, NOT integrated, NOT deployed; no PR opened)
- **SHA:** see the commit that adds this file (`git log -1 -- research/final_build/w6/review_requests/ENG-LOWSEW-CHENILLE.md`). The suites below were run on the tree of 3d47273 plus doc-only changes.
- **Merged in:** `origin/eng/plush` b01851c and `origin/claude/w6-INTEG6` dde3ea62. DECISION_LOG and suite_final_segment kept both sides. autonomy_map.json was regenerated with `python -m brambleloop.autonomy.map --write`.
- **Decision:** D-ENG-LOWSEW-CHENILLE.

## What was built

1. **Join-as-you-go in the CIR and amigurumi engine** (`cir/model.py`: `Op.through`, `Row.fold`, drift, eyes; `cir/joins.py`). Limbs are worked flat, fold-closed and crocheted INTO a named body round at explicit positions. The head is joined through both pieces. The compiler, twin (`certify` refuses a disagreement) and reverse (every join is read back from the text, with seven tamper probes) all prove the joined counts, positions, mirror symmetry, closure and stuffing order. The written pattern names what to make first and where each piece goes.
2. **`construction.sewing_required`** with the readings none / low / standard / unknown. `seo/truth.py` and `gates/certificate.py` refuse "no sew" or "low sew" in a title, tag or listing unless the certified reading supports it.
3. **Chenille / jumbo yarn class (CYC 6–7)** in `cir/yarn_classes.py`. It has a gauge table (a gauge off the table is refused), a 6–8 mm hook range, tension guidance, shedding and care notes, and a yardage/grams model with its own tolerance. The PDF prints all of these.
4. **Eye options** in `gates/eye_options.py`. Embroidered eyes are always offered, and are the default and the only option for baby and under-3. This is consistent with `gates.child_safety`.
5. **Proof:** three ORIGINAL animals in `creative/lowsew.py`: Tumble the penguin, Juniper the fox and Marlow the elephant. Each is certified through compile, twin and reverse, plus US and UK PDFs, and is HELD only on `PHYSICAL_EVIDENCE`. No benchmark instructions, counts, characters or names were used (asserted by `test_the_animals_are_original_and_not_the_benchmarks`). The family `lowsew_chenille` is **partial**, because research intake does not route a concept to it yet.

## Suite counts (run in this session)

| Suite | Passed | Failed |
|---|---|---|
| test_eng_lowsew | 31 | 0 |
| test_compiler | 9 | 0 |
| test_twin | 8 | 0 |
| test_reverse | 18 | 0 |
| test_vacuity | 8 | 0 |
| test_w4_resume_runner | 40 | 0 |
| test_eng_plush | 41 | 0 |
| test_eng_families | 16 | 0 |
| test_owner_gallery_complete | 5 | 0 |
| test_motif_backlog | 25 | **1** |

The full `run_tests.sh` was **not** run.

## Integration finding (not caused by this branch; for the integrator)

`test_motif_backlog::test_e2e_a_completed_gallery_hands_a_stalled_release_on_to_listing_package` **passes on INTEG6 dde3ea62 alone** (verified in a separate worktree) and fails here. This branch's base already contains `eng/gallery-complete` 8d26893 (D-OWNER-GALLERY-COMPLETE: 7 frames), which INTEG6 does not.

The cause is that `motif_backlog.gallery_complete` decides completeness with `listing_asset.usable`, which does not enforce `CAMPAIGN_MIN_FRAMES`. As a result it hands off a 6-frame gallery. The listing-set certificate then correctly blocks that gallery ("names 6 of the 7 required listing photos"). The fix belongs to whoever integrates the two branches: make `gallery_complete` apply the same 7-frame bar, and give the e2e fixture a 7-frame gallery. I did not change either team's semantics.

## Other changes

- `tests/test_eng_lowsew.py` was added to `scripts/suite_final_segment.txt`.
- A `lowsew_chenille` row was added to `research/final_build/w6/construction_families.md`.
- Vacuity guards were added in test_eng_lowsew. `test_owner_gallery_complete` gets a `# vacuity-ok` pragma, because its range is pinned to 7.

## Honest state

No physical sample, listing, campaign or revenue exists for any of the three animals. **OWNER ACTION (later, batched with the other plush):** crochet one physical sample per animal in CYC 6 chenille, about 1–2 h each, plus yarn cost. Until that happens each animal stays HELD.
