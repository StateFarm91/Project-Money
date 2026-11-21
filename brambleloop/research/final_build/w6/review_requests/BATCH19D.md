# BATCH19D — sale pipeline merged onto Batch 19c; flat-piece diagrams; publish read-back

- **Branch:** `claude/batch19d`. Base `claude/batch19c` @ d8751850, with
  `origin/claude/batch19-sale` @ 61b508b4 merged in.
- **Commits:** `9202a44` (the merge); `5151529` (the fixes); then docs only (this file,
  BUILD_STATE, DECISION_LOG, decision_index).
- **Status:** builder branch. NOT reviewed, NOT deployed. No PR opened. Nothing generated,
  published or spent. Production is unchanged.
- **Date (UTC):** 2026-11-21

## 1. Merge

- **Docs.** BUILD_STATE.md and DECISION_LOG.md merged with no conflict, so both sides are kept.
- **autonomy_map.json.** Took ours, then regenerated it with
  `PYTHONPATH=src python -m brambleloop.autonomy.map --write …`. `core.decision_index` was
  rerun (81 ids after D-BATCH19D-FLAT-DIAGRAMS).
- **publish/pdf_standard.py and tests/test_pdf_standard.py: a whole-file conflict.**
  - The sale branch had moved the family-aware premium standard to
    `publish/premium_standard.py` (tests to `test_premium_standard.py`). It then made
    `pdf_standard.py` the sale checker (`CHECKER_VERSION pdf_standard/2`).
  - Batch 19c's eng/pdf-diagrams had changed the old `pdf_standard.py`: component diagrams,
    assembly steps, eye options and the techniques appendix.
  - Resolution: the split is kept. `pdf_standard.py` and its test take the sale side.
    Batch 19c's diagram changes were three-way merged (`git merge-file`, clean, 0 conflicts)
    into `premium_standard.py` and `test_premium_standard.py`.
  - The references in `pdf_template.py`, `test_pdf_diagrams.py` and `test_learn_proof.py` now
    point at `premium_standard`.
  - Both behaviours are kept, and no gate or rule was dropped.

## 2. Flat row-worked pieces: row-progress diagrams

**Defect.** `construction_diagrams.stages` drew round geometry only. A flat piece's engine-layout
PDF had no inline image on its Instructions pages, so the sale checker's `diagrams` check
FAILed. This was reproduced on the blanket: `diagrams FAIL: no inline construction diagram on
the instruction pages`.

**Fix.**
- **What is drawn.** When every component is `flat_rows`, `stages()` returns up to 6
  row-progress diagrams (`part="flat"`). They are built from the twin:
  - finished `width_cm` × the cumulative `row_top_cm`, on one scale for every stage;
  - each worked row drawn cell by cell, in its colour and fabric position;
  - rows still to work drawn faint, and a rose outline on the newest row;
  - `R<n>` markers, a width dimension line and the label "DIAGRAM: after row k of N".
- **Captions.** The engine's step cards carry them, and the paragraph calls them a
  "construction diagram … not a photograph". `flat_caption()` gives the same numbers in words.
- **Placement.** The engine places stages only in the twin component's block, so a multi-panel
  piece never shows the front's diagram under the back.

**Reconciled with eng/pdf-diagrams, not duplicated.**
- A pattern with any piece worked in rounds (amigurumi, including one with a flat part) gets no
  row-progress stage. Its component diagrams (`component_profile`) are its diagrams.
- The template already draws a flat piece's inline diagrams as mini-grids at the tricky rows. It
  takes only the round stages (`pdf_template._template_stages`), so `test_pdf_template`'s
  mini-grid assertions hold unchanged.

**Evidence.**
- Blanket engine US PDF, pre-image reading: `PASS_PENDING_IMAGES`, where it was `FAIL` on
  `diagrams` before.
- In `test_vis_gallery_e2e` test 3, the REAL sale pipeline now builds and certifies both
  premium PDFs for the blanket: US PASS and UK PASS, `both_pass` True.
- New tests in `test_pdf_diagrams.py`:
  - the stages run at the twin's finished size and are deterministic;
  - worked rows are drawn in yarn colours and the rest faint;
  - the engine flat PDF PASSes the sale `diagrams` check, and the premium `inline_diagrams`
    rule reads the same words;
  - a mutation that removes the stages FAILs `diagrams` by id;
  - an amigurumi with a flat part gets no row-progress stage;
  - the template takes no flat stage.

## 2b. A defect found on the way: the premium read-back hash

`store.publish` now uploads the certified premium edition. The post-upload read-back still
compared those bytes with the base `assets.build` hashes, so every READY release's draft would
read back unverified (`published: False`). This showed up in the draft run in
`test_search_hero_publish`.

The read-back now compares against `sha256` of the bytes `certified_premium_pdfs` returned.
Those bytes are re-hashed against their certificates, which are bound to the `assets.build`
hashes checked earlier in the handler. The base hashes are kept beside it as
`hash_check.base_certified`.

## 3. test_search_hero_publish: the byte-for-byte draft upload, restored

The merits test keeps the sale side's assertion: with the release truthfully not READY,
`store.publish` passes the search, listing-set and F-524 gates and is stopped only by
D-OWNER-SALE-PIPELINE, with zero Etsy requests. The same test then restores HEAD's assertion:
- exactly one draft;
- the taxonomy;
- the uploaded gallery equals the certified frames by rank and sha256, at least 7 frames.

Only the sale verdict (`ready_for_sale`, `certified_premium_pdfs`) is replaced for that second
publish, by a labelled `test_double`. READY itself is derived and asserted by
`test_sale_pipeline_e2e`. Result: 5/5.

## 4. test_vis_gallery_e2e tests 3 and 7: STILL FAILING (not weakened, not forged)

Test 3 now drives the real launch decision (`launch.plan`) and every `sale.pipeline` stage.
The assertion on what is uploaded is now stricter:
- the files sent must be the certified premium editions;
- each certificate's base hash must equal the `assets.build` hash.

What happens:
- admission, then gallery certified;
- the premium PDFs are built and certified PASS for both editions;
- `attach` is blocked by `listing_gates`:
  `SAMPLE_PHOTO_REQUIRED: no unedited photograph of a sample made from this release is on
  file (Etsy Help 44297885802647)`.

D-OWNER-SALE-PIPELINE defines READY as "every listing gate PASS", so `store.publish` stays
correctly blocked. Test 7 calls test 3 and fails the same way.

Why this is not fixed in the test:
- A qualifying photo needs a passed FULL physical make bound to the release, a photo through
  the real intake, and listing-set re-certification with it as frame 1.
- `test_w6_listing_chain_e2e` (section D) records that READY "is not reachable here without
  forging": the physical photo frame stays unapproved and no production job approves it.
- Approving it by hand, or relaxing the sale rule for drafts, would drop a gate. Neither was
  done.

**Owner action, not a code fix:** a real physical sample and an unedited photograph of it. This
is already on the owner list.

## Suites

Run `20261121T020920Z-4751`, GIT SHA `5151529c4e27`, tree clean at start, 805 s, `JOBS=4
SUITE_REGISTRY=0`. All 19 names were checked to exist.

| Suite | Passed | Failed |
|---|---:|---:|
| test_vis_gallery_e2e | 11 | 2 (test_3, test_7: SAMPLE_PHOTO_REQUIRED, above) |
| test_sale_pipeline | 20 | 0 |
| test_sale_pipeline_e2e | 8 | 0 |
| test_search_hero_publish | 5 | 0 |
| test_pdf_standard | 14 | 0 |
| test_premium_standard | 23 | 0 |
| test_pdf_template | 31 | 0 |
| test_pdf_diagrams | 19 | 0 |
| test_owner_gallery_complete | 5 | 0 |
| test_b19_pdf_blocker_admission | 2 | 0 |
| test_motif_backlog | 26 | 0 |
| test_w4_ownerimg | 35 | 0 |
| test_w4_readback_evidence | 23 | 0 |
| test_compiler | 9 | 0 |
| test_reverse | 18 | 0 |
| test_twin | 8 | 0 |
| test_vacuity | 8 | 0 |
| test_clothing_e2e | 10 | 0 |
| test_mission_control2 | 13 | 0 |

**TOTAL PASSING: 288; suites failing: 1** (test_vis_gallery_e2e). Environment failures: 0.

`test_learn_proof` was also run after the merge (premium_standard import), in run
`20261121T013803Z-871` with test_pdf_standard, test_premium_standard and test_pdf_diagrams:
68 passing, 0 failing.
