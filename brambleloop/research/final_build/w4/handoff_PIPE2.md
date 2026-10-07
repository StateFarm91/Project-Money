# Handoff — W4-PIPE2 (new product candidates)

- Branch `claude/w4-PIPE2` (worktree `.claude/worktrees/W4-PIPE2`), from origin/claude/visual-investigation;
  merged origin/claude/w4-PIPE twice (d648bc4, then 18baa94 — PIPE engineered the stocking first).
- Latest pushed SHA: see `git log -1 origin/claude/w4-PIPE2`.
- Mission: engineer CREATIVE's 8 moment-first candidates in `emotional_brief.gate_candidates()['engineering_queue']`
  order. Stocking + pencil roll CIRs are W4-PIPE's (`pipeline_board.stocking_cir` / `pencil_roll_cir`); my duplicate
  in-the-round stocking was withdrawn on merge. The other six are engineered here; PDFs, concept boards and taste-gate
  registration are produced for all eight.

## Candidates → stage → remaining gate (evidence: `PIPE2_CANDIDATES.{json,md}`, `PIPELINE_BACKLOG.json` rows, `pipe2/<slug>/`)
| # | candidate | CIR | Product Truth | PDF | stage reached | remaining gate (clearer) |
|---|---|---|---|---|---|---|
| 1 | first-christmas-stocking | W4-PIPE | certified | 15 pp | VISUAL | renderer draws 1 piece; 8-piece assembled render = renderer work (COMPANY/visual) |
| 2 | reading-nook-cable-wrap | PIPE2 (real cable2x2) | UNCALIBRATED_PRIMITIVE | 35 pp | PRODUCT_TRUTH | tester calibrates 2-over-2 cable (OWNER/tester) |
| 3 | mothers-day-heart-tea-cosy | PIPE2 (crown→band→held-half skirts) | certified | 8 pp | VISUAL | multi-piece render (COMPANY/visual) |
| 4 | snowfall-advent-garland | PIPE2 (24 mittens, afterthought thumbs, tab loops, cord) | certified | 9 pp | VISUAL | multi-piece render (COMPANY/visual) |
| 5 | teacher-chevron-pencil-roll | W4-PIPE | certified | 10 pp | VISUAL | multi-piece render (COMPANY/visual) |
| 6 | heart-row-ring-pillow | PIPE2 (drum, sewn bottom over fibrefill), class C | PHYSICAL_TEST_REQUIRED | 9 pp | PRODUCT_TRUTH | full physical make (OWNER/tester) |
| 7 | housewarming-key-basket | PIPE2 (round staggered base, basketweave relief walls) | certified | 7 pp | VISUAL | renderer cannot name a staggered disc (geometry.corners defect, below) |
| 8 | spring-garden-kneeler | PIPE2 (tulip-trellis relief front + back, stuffed), class C | PHYSICAL_TEST_REQUIRED | 10 pp | PRODUCT_TRUTH | full physical make (OWNER/tester) |

All 8: concept board (deterministic twin render, `products.moment_candidates.board_png`) filed with a content digest;
`register_for_taste_gate` writes the gate's own WAITING verdict; runtime proof on a scratch DB:
`creative.intake.regate_held` holds all 8 at needs_taste waiting ONLY on `vision_model (no vision probe has succeeded)`
(board_for/board_digest_for find the board). Vision judgement = owner credit top-up (EXTERNAL). Novelty vs stored benchmark
data remains DATA-GATED (shadow DB has no BenchmarkListing rows; production holds 441). Search/listing: not reached.

## Files (surgical edits outside my module — please review)
- NEW `src/brambleloop/products/moment_candidates.py` (6 builders, SEARCH, ENGINEERING_NOTES, board_png/file_board/board_record,
  register_for_taste_gate, creative_cir), `research/final_build/w4/pipe2_run.py`, `tests/test_w4_pipe2_candidates.py`.
- `products/motifs.py`: + TULIP_TRELLIS (original geometry; check_library clean).
- `products/pipeline_board.py` (W4-PIPE's): registers moment_candidates via `setdefault` (never replaces PIPE entries);
  PRODUCT_TRUTH treats PHYSICAL_TEST_REQUIRED like UNCALIBRATED_PRIMITIVE (clearer OWNER); VISUAL next_step names the
  actual renderer refusal (multi-piece / staggered disc).
- `creative/intake.py` (W4-CREATIVE's, lane complete): `board_for` / `board_digest_for` fall back to the
  `creative.concept_board` record (moment_candidates.board_record). Fail-closed unchanged ("" when none).
- `tests/test_w4_pipe_board.py` (W4-PIPE's): the "some creative candidate is unengineered" premise became false; now
  checks the waiting ones at DESIGN if any, else that every creative candidate compiled (stronger, not weaker).
- `PIPELINE_BACKLOG.{json,md}`: only the 8 creative rows replaced (`pipe2_rows` marker); PIPE's rows untouched.

## Brief departures (CREATIVE should know; the CIR is the product)
See `moment_candidates.ENGINEERING_NOTES`: no per-stitch colourwork (relief instead); kneeler is 2 panels not modular
squares, gold relief tulip rows not bobbles; garland pockets are not numbered (no numeral charting); wrap's cream
"border" is end bands.

## WIRING REQUESTS
1. **W4-AUTO** `runtime/pipeline.py` ENGINEERED: add the six slugs →
   `"brambleloop.products.moment_candidates:<fn>"` (reading_nook_cable_wrap, mothers_day_heart_tea_cosy,
   snowfall_advent_garland, heart_row_ring_pillow, housewarming_key_basket, spring_garden_kneeler) so a regate ENGINEERING →
   `cir.draft` builds the engineered CIR, not a prototype. Also a cadence/handler calling `file_board` +
   `register_for_taste_gate` against the live DB (shadow) so production's `regate_held` sees them.
2. **visual owner**: disclosed renderer is single-component; 5 of 8 candidates are assembled objects.
3. **cir/geometry owner**: `geometry.corners` can never return 0 (circle) for a magic-ring disc: round 2 is all increases,
   so every round-3 increase lands on an increase-produced stitch and counts as stacked → mixed → None. The renderer
   therefore refuses every staggered (round) base.

## Tests run (all pass)
test_w4_pipe2_candidates (85 OK), test_w4_pipe_board, test_products, test_products_adversarial, test_intake,
test_w4_creative_brief; guards: test_vacuity, test_secret_scan, test_reachability, test_w3_tmp_hygiene, test_w4_pipe_name_truth.

## Next deterministic action
Rerun: `PYTHONPATH=src python research/final_build/w4/pipe2_run.py` (≈40 s, scratch store/DB under $TMPDIR).
Nothing executable remains in this lane until a vision probe succeeds or a tester's evidence lands.
