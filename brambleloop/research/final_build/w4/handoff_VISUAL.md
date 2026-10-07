# handoff_VISUAL — W4-VISUAL

- Branch: `claude/w4-VISUAL` (worktree `.claude/worktrees/W4-VISUAL`). It merges
  `origin/claude/visual-investigation` (0883282). For the latest pushed SHA, run
  `git log origin/claude/w4-VISUAL -1`.
- Status: `VISUAL_STATUS.md` / `.json` in this directory. Spend: CA$0. Phase: shadow.

## Items → status → evidence
| Item | Status | Evidence |
|---|---|---|
| F-030 / F-254 gallery IA | Drawable jobs **PROVEN, certified** on 6 releases (basket S 8 frames, M/L 7, blanket 5, coasters 5, pet-snuggle-mat 5). CONTENTS is OPEN: no producer yet. LIFESTYLE is OWNER-GATED (VB-1 P2 or sample photos) | `visual/certified_gallery_proof_*2026-10-07.json`, `tests/test_w4_visual_certified_gallery.py` 7/7 |
| pet-snuggle-mat imagery (W4-SEO ask) | **PROVEN**: hero/scale/detail plus COLOUR_CONTEXT and MATERIALS certified; upload path serves 5 | proof JSON |
| harvest-table-runner imagery (W4-SEO ask) | **OPEN-DEFECT, company engineering**: hero and scale fill 13–14% at 340 px, and the gate needs 25% (the runner is 3.8:1). Needs a diagonal or folded hero layout plus verifier support. The gate is not loosened. | proof JSON |
| The other 5 viable releases | Imagery complete apart from CONTENTS and LIFESTYLE | proof JSON |
| A fabric | PROVEN (PASS) | VISUAL_STATUS |
| B / C | DATA-GATED (benchmark measurements / sample close-ups; not a launch dependency) | VISUAL_STATUS |
| D | 12 PASS / 0 FAIL / 7 UNKNOWN. The 7 are EXTERNAL-GATED on VB-1 P1 | `visual/milestone_d_hdc_2026-10-07.json` |
| E | Disclosed route LIVE; photographic E waits on D / P2 | VISUAL_STATUS |
| Single owner plan | VB-1 ceiling CA$4.76, sequenced with GATESI: (1) Anthropic top-up, (2) deploy GATESI image.probe fix, (3) approve VB-1 | VISUAL_STATUS "Owner decision VB-1" |
| R&D loop, ANGLE, concept boards | As before (PROVEN) | VISUAL_STATUS |

## Renderer changes (for W4-RENDER to merge)
These are pushed in dab5888 and later commits:
- `visual/render_contract.relief`: when a raised tone lands inside MIN_SEPARATION, it steps
  further. Launch-0 output is byte-identical.
- `visual/render_verification.authoritative_cir`: falls back to `pipeline._engineered_cir`,
  at the released version only.
- `publish/listing_asset.has_render_authority`, used by `runtime/release._disclosed_render_set`.
- I made no change to geometry corner detection or to multi-piece rendering.

## Tests run (all passing, latest code)
- Visual: test_w4_visual_certified_gallery, test_w4_visual_gallery_frames 10/10,
  test_w4_visual_angle 5/5, test_w4_visual_boards 3/3, test_disclosed_render 27/27,
  test_disclosed_render_runtime 3/3.
- Listing and gates: test_disclosed_certified_upload 7/7, test_listing_set,
  test_launch0_listing_truth 14, test_first_customer_gate 12, test_eligibility 34.
- Hygiene: test_vacuity, test_secret_scan, test_w3_tmp_hygiene, test_reachability (see the
  final report).

## WIRING REQUESTS
1. AUTO (`autonomy/visual_rnd_job.summarise`): count refreshed `launch_imagery` listings in
   `work_done`.
2. DONE in this lane. The listing set now accepts the gallery frames: listing_set,
   release_gates, etsy_ops and first_customer were changed surgically.
3. CC: show VISUAL_STATUS stage D as PARTIAL, and show the VB-1 3-step sequence.
4. Partly resolved: the relief fix unblocks gold palettes (pet, harvest). Spooky-garland and
   autumn-oak have not been re-checked.
5. CREATIVE/publish: `intake.board_for` should find catalogue boards (`board/{slug}.png`).
6. CONTENTS: build a PDF page-preview frame (publish.pdf owner, or this lane next).
7. commerce owner: `search_evidence._category_for` hard-codes sizes=1 and colours=1. It
   should use the product's variant count and `len(cir.colors)`, so that
   SIZING/COLOUR_CONTEXT applicability is measured rather than assumed.

## Next deterministic actions
- harvest-table-runner: add a diagonal hero layout (disclosed_render) with the matching
  un-projection in render_verification. Then rerun:
  `PYTHONPATH=src python research/final_build/w4/visual/proof_certified_gallery.py harvest-table-runner <out.json>`
- CONTENTS frame from the built pattern PDF.
