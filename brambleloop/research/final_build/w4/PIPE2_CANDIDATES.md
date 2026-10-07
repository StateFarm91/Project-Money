# W4-PIPE2 — moment-first candidates engineered (shadow)

Generated 2026-10-07T02:55:35+00:00 at `ffd5eae` by `research/final_build/w4/pipe2_run.py`. Queue = `emotional_brief.gate_candidates()['engineering_queue']`; stocking and pencil roll CIRs are W4-PIPE's, deliverables/boards/taste registration for all eight are here. Publication is never advanced.

| # | candidate | version | board stage | status | PDF | concept board | taste gate | remaining gate | clearer |
|---|---|---|---|---|---|---|---|---|---|
| 1 | first-christmas-stocking | 0.1.0 | VISUAL | FAIL | 15 pp | `5a27f4556aa5` | needs_taste (vision_model (no vision probe has succeeded)) | the disclosed renderer draws one compiled piece; an assembled multi-piece render is renderer work (visual owner; the gate is not relaxed) | COMPANY |
| 2 | reading-nook-cable-wrap | 0.1.0 | PRODUCT_TRUTH | FAIL | 35 pp | `9e8f430dab60` | needs_taste (vision_model (no vision probe has succeeded)) | a pattern tester works the new stitch or makes the full piece (physical evidence) | OWNER |
| 3 | mothers-day-heart-tea-cosy | 0.1.0 | VISUAL | FAIL | 8 pp | `504efc0449d9` | needs_taste (vision_model (no vision probe has succeeded)) | the disclosed renderer draws one compiled piece; an assembled multi-piece render is renderer work (visual owner; the gate is not relaxed) | COMPANY |
| 4 | snowfall-advent-garland | 0.1.0 | VISUAL | FAIL | 9 pp | `fee3dae58e8d` | needs_taste (vision_model (no vision probe has succeeded)) | the disclosed renderer draws one compiled piece; an assembled multi-piece render is renderer work (visual owner; the gate is not relaxed) | COMPANY |
| 5 | teacher-chevron-pencil-roll | 0.1.0 | VISUAL | FAIL | 10 pp | `cc0b0622491e` | needs_taste (vision_model (no vision probe has succeeded)) | the disclosed renderer draws one compiled piece; an assembled multi-piece render is renderer work (visual owner; the gate is not relaxed) | COMPANY |
| 6 | heart-row-ring-pillow | 0.1.0 | PRODUCT_TRUTH | FAIL | 9 pp | `03bfe2b5f46c` | needs_taste (vision_model (no vision probe has succeeded)) | a pattern tester works the new stitch or makes the full piece (physical evidence) | OWNER |
| 7 | housewarming-key-basket | 0.1.0 | VISUAL | FAIL | 7 pp | `b5e8d24180ad` | needs_taste (vision_model (no vision probe has succeeded)) | the disclosed renderer cannot name this round piece's outline (staggered increases: cir.geometry.corners returns None); renderer/geometry work | COMPANY |
| 8 | spring-garden-kneeler | 0.1.0 | PRODUCT_TRUTH | FAIL | 10 pp | `bd8e295fd34a` | needs_taste (vision_model (no vision probe has succeeded)) | a pattern tester works the new stitch or makes the full piece (physical evidence) | OWNER |

## Engineering notes (where the CIR departs from the brief)

- **first-christmas-stocking**: W4-PIPE's design; see handoff_PIPE.md
- **reading-nook-cable-wrap**: Real 2-over-2 cable crossings (cable2x2), so the name's cable claim is backed; the crossing is an uncalibrated primitive, which is a physical-tester gate. The cream 'border edging' is cream end bands (a perimeter round is not expressible on one flat component).
- **mothers-day-heart-tea-cosy**: Seamless top-down: crown, heart band, then held halves worked as front and back skirts; the gaps between them are the spout and handle openings.
- **snowfall-advent-garland**: 24 fingertip-up mittens with afterthought thumbs and folded tab loops, threaded on a slip-stitch cord. Numbers on the pockets are not engineered (no chart support for numerals) and are not claimed in the title.
- **teacher-chevron-pencil-roll**: W4-PIPE's design; see handoff_PIPE.md
- **heart-row-ring-pillow**: A drum pillow: disc top worked down into a heart-row side band, a sewn-on bottom over fibrefill. Stuffed and closed, so class C: a physical make is required.
- **housewarming-key-basket**: Staggered increases so the base is round, as the brief says; the disclosed renderer draws only fully stacked (polygon) bases today (cir.geometry.corners cannot return 0 for a disc whose second round is all increases).
- **spring-garden-kneeler**: Brief named modular panels and tulip bobbles. Engineered as a relief front panel and a matching back (a grid of squares cannot be length-checked by cir.assembly), with the tulip heads as gold dc relief rows rather than bobbles (bob is an uncalibrated primitive). New motif products.motifs:tulip-trellis. Stuffed: class C.

## Taste gate (runtime proof on a scratch DB)

`creative.intake.regate_held` → vision_usable=False; held 8, presented 0, queued 0. Each candidate has a concept board with a content digest on file and waits only on a vision judgement (owner credit/vision probe); nothing here writes `thumbnail_reads_small` or `craft_impression`.
