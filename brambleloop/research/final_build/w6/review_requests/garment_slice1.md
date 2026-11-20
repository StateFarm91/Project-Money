# ENG-GARMENT slice 1: review request

Branch `eng/garment` (from `claude/w6-INTEG2` 64146306). NOT merged, NOT deployed.

## Base
`eng/plush` d4aaf9b6 is merged in. It carries `eng/families` 777a66f3, which holds
`creative.construction_families` (slice 3 routing), and `gates.child_safety`, the child gate this
work applies. **Two inherited defects from eng/plush were fixed here. Please also tell ENG-PLUSH:**
- `test_garments` failed on eng/plush (and passes on INTEG2). The child gate now applies to that
  suite's `test-child-drop-shoulder` fixture because of the "Child" in its title. The fixture is
  held, correctly: its sleeves are sewn on, and its yarn names no weight, which fails closed as
  unknown filling. The expectation is now "only CHILD_SAFETY_* refusals, and the child_safety
  stage ran". The gate is unchanged.
- `test_w4_resume_runner` F7 found that `tests/test_eng_plush.py` was missing from
  `scripts/suite_final_segment.txt`. It is now declared.
- `test_vacuity` flagged four eng/plush and amigurumi loops. Each now has a non-emptiness
  assertion.

## What is new
| file | what |
|---|---|
| `src/brambleloop/products/garment_families.py` | `Piece`/`Step`: the step list each size is built from. Four constructions. `built_measures`. `balls_and_yards`. `GarmentSpec` and `design()`. |
| `src/brambleloop/products/garment_release.py` | The five designs, `spec_for(concept)` (table routing), and `build`/`certify`. Every size goes through `certificate.certify`, then the garment gates. |
| `src/brambleloop/gates/garment_fit.py` | The garment gates (below), plus the multi-size reader `read_line`/`expand`/`multi_size_problems`. |
| `src/brambleloop/publish/garment_writer.py` | Multi-size text: `a (b, c, ...)` with the smallest size first, a count after every row line, US and UK, and the finishing lines (pick-up rates as small fractions). |
| `src/brambleloop/cir/graded.py` | `BABY`, the CYC Baby Size Chart (https://www.craftyarncouncil.com/standards/baby-size-chart, read 2026-11-20), plus `months_of`. |
| `src/brambleloop/gates/child_safety.py` | `garment_months`, GARMENT_CLOSURES, picked-up joins, and worked-into chains. |
| `src/brambleloop/products/garments.py` | `built_measures` dispatches to the family's own instrument (used by grading recompute and plausibility). |
| `src/brambleloop/publish/pdf.py` | `graded_childrens_assignment` reads baby months. |

## Gates (each with a mutation test in `tests/test_eng_garment.py`)
- GARMENT_STITCH_COUNT: every row's declared count equals the compiler's count, and so does every step's end count.
- GARMENT_SHAPING: increases and decreases change the count by 2 per event, over `(times-1)*every+1` rows. A raglan adds 8 per unit. Chain-on and leave steps change it by ±2X.
- GARMENT_SEAM_MISMATCH: covers three things.
  - Seams sewn row to row have equal rows on both sides (the one-piece fold is checked row for row from the compiled counts).
  - Joins checked by length agree within 6%.
  - The assembler's mismatched joins.
- GARMENT_PICKUP_RATE: a band starts on exactly the stitches it says it picks up, and those stitches at gauge are within 4% of the twin's edge length.
- GARMENT_NECK_FIT: the slash neck is 0.55 to 1.0 of the cross-back. For a raglan, the gate uses `cir.specification` yoke plausibility.
- GARMENT_ARMHOLE_FIT: the armhole is at least as deep as the body's armhole depth, and the sleeve top is at least the body's upper arm.
- GARMENT_FINISHED_OFF_TARGET: the built chest is within 5% of body + ease, and the length within 8%.
- GARMENT_EASE_OUT_OF_BAND: the built chest ease is inside the stated fit band at every size, with no ±2 slack.
- GARMENT_YARDAGE_CLAIM / GARMENT_SIZE_CLAIM: every printed metre, yard, ball and measurement is recomputed from the twin. This is Product Truth for the size chart.
- GARMENT_STEPS_DIFFER / GARMENT_SIZE_RUN: one design, with chest and yarn strictly rising.
- GARMENT_DOCUMENT: the parenthesised text, read back and expanded per size, gives every compiled row's count.

## Decisions (DECISION_LOG D-ENG-GARMENT-1..4)
- Release as one unit, built from one step list.
- Constructions the assembler can measure honestly. Separate front and back panels with set-in sleeves are deferred, because `cir.assembly` cannot place a join on both pieces.
- The back-loop band is not called "rib": the technique gate reserves that word for post stitches. Its gauge is stated, at the main gauge (F-754).
- Child and baby garments are inside the child gate. No buttonholes for under-3s, and an older child's buttons are held.

## Results
- Five designs certify at every size: 9 + 6 + 5 + 9 + 9 = 38 certificates granted. Baby and child sizes run the child_safety stage and pass every check, including PHYSICAL_EVIDENCE: no piece is sewn on.
- 10 multi-size documents (5 designs × US/UK) read back with 0 problems.

## Suites (this branch)
- `test_eng_garment`: 21/21.
- Exit 0 (13 suites): `test_eng_families`, `test_compiler`, `test_twin`, `test_reverse`, `test_s1_product_truth_3`, `test_blanket_size_truth`, `test_w5_concept_intake`, `test_eng_plush`, `test_opus2_a1_children`, `test_opus2_amigurumi`, `test_childrens`, `test_w4_children`, `test_gates`.
- Grading suites, exit 0: `test_graded`, `test_grading`, `test_cert_grading` (10/10), `test_k9_graded_truth` (8/8), `test_garments` (after the fixture expectation above), `test_garment_design`, `test_benchmark_garment`.
- Exit 0: `test_v11_autonomy_timeline`. The autonomy map was not regenerated, because this slice adds no job types.
- `test_vacuity`: exit 0 after the loop fixes.
- `test_w4_resume_runner`: F7 fixed. Full re-run pending at slice 2.
- `test_deliverable_qa`: not yet re-run (slice 2 touches the PDF).

## Honest status
- No garment has been physically made. Fit is computed, not tested. Fitted designs (class C) are refused at routing.
- Garments do not route yet (`construction_families` still holds `garment`). That is slice 3.
- There is no garment PDF yet. That is slice 2.
