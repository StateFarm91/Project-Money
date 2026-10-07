# Handoff — W4-CAND (candidate CIR fixes: pencil roll, stocking loop, advent garland)

- Branch `claude/w4-CAND` (worktree `.claude/worktrees/W4-CAND`), from origin/claude/visual-investigation 5a586c0.
- Latest pushed SHA: `git log -1 origin/claude/w4-CAND`.
- Mission: fix the candidates' pattern data so they render and verify truthfully; never by relaxing a gate.

## Items → status → evidence
| item | status | evidence |
|---|---|---|
| pencil roll (a) flat footprint | DONE (0.2.0) | `pipeline_board.pencil_roll_cir`: 60 cm tie → closed 22 cm sc band (self-seam, lies flat 10.9 cm) sewn by its seam just above the pocket; panel 4 repeats (25.6 x 32.5 cm), pocket fold rows chosen on the twin (8 rows = 8.06 cm), 24.5 cm above the fold for a 17.5 cm pencil; 8 slots every 4 sts. Hero 36.5 x 24.5 cm: 340 px coverage hero 45.5 % / scale 45.3 % (gate 25 %, unchanged); layout_qa clean. `test_w4_render_assembled` pencil_roll_* |
| pencil roll (b) tie above pocket | DONE | band at rows 2k+1.. (17-20), note says "rows 17-20, just above the pocket's top edge (row 16)"; drawn y0 = tops[16]-tops[8]. `pencil_roll_band_above_the_pocket_as_its_note_says` |
| pencil roll (c) gold vs relief shade | ALREADY CLEARED (W4-VISUAL `render_contract.relief` steps the raised tone until it clears MIN_SEPARATION 40; minimum unchanged): gold #C49545 vs its tone 51.9, palette separation 44.8. Proven: `pencil_roll_palette_clears_contract_separation`. No palette change needed |
| stocking hanging loop | DONE (0.2.0) | loop ends joined by a structured self-seam (top↔bottom: a band along its stitches), even chain (16), sewn by that seam to cuff rows 1-2; renderer draws it flat (stitches 0-7, 6.4 cm) on the cuff's top edge at the back seam. `stocking_loop_*`, `stocking_nothing_left_undrawn` |
| advent garland thumbs + cord | DONE (0.2.0) — VISUAL stage now UNKNOWN (was FAIL refused) | thumb = `pick_up` join (round 1 into the mitten's 4-chain opening; 6.4 cm = 6.4 cm, measured by `cir.assembly`), cord = `thread` join through each closed loop (girth 0.4 cm <= half of 4.3 cm inside; a dc cord is refused as mismatched), loop = closed band (6 rows); spacing derived from a flat mitten + thumb (15 cm, cord 420 cm; 0.1.0 typed 11 cm < a 13.2 cm flat pocket). Certified (no ASSEMBLY findings); text round-trips through `cir.reverse`. Renderer form `pockets`: hero = all 24 pockets laid flat (best-fit grid), scale = one pocket with dims + "threaded on a 420 cm cord (not drawn)", detail = relief rounds laid flat. 340 px legibility hero 24/24 pieces, coverage 49 %; layout_qa + asset_truth pass. `tests/test_w4_cand_garland.py` (28 OK) |

CIR vocabulary added (additive): `cir.model.SeamMethod` + "pick_up", "thread" (`SEAM_CONNECTOR` into/through);
`cir.writer`, `publish.pdf` words; `cir.reverse` reads "Work ... into" / "Thread ... through" with its own table;
`cir.assembly`: `band_axis`/`BAND_EDGES`/`band_length_cm`, pick-up joins measure the round piece's first round,
thread joins check fit (THREAD_ROOM 0.5), a picked-up-only round piece without a finished size no longer makes the
whole assembly unmeasurable. `publish.disclosed_listing`: pockets alt text; hero expected pieces = layout copies.
`visual.render_contract.annotation_lines`: pockets scale lines.

Renderer support added (`visual/assembled_render.py`, additive): a flat piece whose two opposite ends are
self-seamed is a closed band; when a planar join places it by one of those edges it lies flat: first half in
front (rows 1..m/2 or stitches 0..n/2-1), second half behind; odd counts are not drawn (reason recorded).
Manifest pieces carry `band_flat` and `stitches_shown`. Assembled renderer version unchanged (still
unqualified → assembled hero/scale UNKNOWN until VISUAL2's assembled verifier).

## Release procedure
Candidates are pre-release (not in tests/data/release_fingerprints.tsv); versions bumped 0.1.0 → 0.2.0
for content changes; superseded 0.1.0 PDFs removed, 0.2.0 PDFs written by pipe2_run.

## WIRING / coordination
- W4-VISUAL2 (assembled-frame measurement): stocking hero now includes the loop as a flat band (layout
  piece `loop`, `band_flat: "stitches"`, `stitches_shown: [0, 7]`); re-derive with
  `assembled_render._band_of` / `BAND_EDGES`. Pencil roll's second piece is now `band` (`band_flat: "rows"`).

## Tests run
test_w4_render_assembled (ALL PASSED), test_w4_pipe_board (55 OK), test_w4_pipe2_candidates (86 OK), test_w4_cand_garland (29), test_assembly, test_compiler, test_reverse, test_twin, test_schematic, test_geometry, test_garments, test_disclosed_render (27), test_w4_visual2, test_release_versions, test_vacuity, test_secret_scan, test_w3_tmp_hygiene, test_reachability: all pass.

## Next deterministic actions
1. Nothing executable left in-lane. Remaining gates: assembled-frame verifier (VISUAL2) so assembled hero/scale can PASS; Launch-0 promotion (catalogue); physical sample confirms pencil-roll band fit.
2. `PYTHONPATH=src python research/final_build/w4/pipe2_run.py` then `render_run.py` (one at a time).
