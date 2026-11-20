# ENG-GARMENT slice 3: review request (routing and concept to PDF, end to end)

Branch `eng/garment`. NOT merged, NOT deployed.

## Routing (`creative/construction_families.py`)
- New families: `garment_raglan` and `garment_one_piece` (VERIFIED), and `garment_side_to_side` and `garment_drop_shoulder` (PARTIAL). The partial ones certify and render at every size, but no research concept is pinned through intake yet.
- `route()` sends a `fitted_garment` concept to `garment_route`. That calls `products.garment_release.spec_for`, the same table `cir.draft` uses, then applies these checks:
  - the named-feature check (H1): cable, bobble, hood, lining and so on are held. `garment_or_wearable` is honest only for the garment families.
  - **PAIR_PROOFS only where the end-to-end proof exists**: (raglan, cardigan) on the adult table, (raglan, baby) on the baby table, and (one_piece, sweater) on the child table. `GARMENT_PAIR_AUDIENCE` pins each proof to the body table it was proven on, so an adult one-piece sweater is held.
  - Everything else is held as `construction_unsupported:<family>`. Fitted designs are refused as class C, and hoods are refused.
- The audience on the intake path is read from category and title words (baby, kids, child, toddler and so on). The draft then checks that the concept's recipient agrees, or holds it.

## Intake (`radar/intake.py`)
- A garment is sized by its sourced body table as one release of the whole run, so the flat size bands do not apply.
- A garment title that names any one size (a digit, XS–5X, small/medium/large, months, years, newborn and so on) is refused, failing closed.

## Draft (`runtime/pipeline.py::_draft_garment`)
1. `cir.draft` for a `fitted_garment` routes the concept, builds every size, and runs `garment_release.certify` (every size's certificate plus the garment gates).
2. A refused run is held with its reasons.
3. A granted run enqueues each size's CIR into the unchanged `cir.compile` → `gate.certify` chain.

No new job type, so the autonomy map counts are unchanged. It was regenerated with `python -m brambleloop.autonomy.map --write`.

## End to end (real handlers, `tests/test_eng_garment.py`)
Each test runs:
1. intake;
2. score (jury and pre-engineering gates);
3. draft;
4. every size through `cir.compile` and `gate.certify` (all granted);
5. the US and UK PDFs with schematic and size chart, rendered from the same release.

The CIRs the runtime stored are compared component for component with the release the PDF renders.

| test | sizes |
|---|---|
| `test_a_research_adult_cardigan_runs_concept_to_pdf_in_nine_sizes` | XS–5X (9), buttons |
| `test_a_research_child_sweater_runs_concept_to_pdf` | 2–12 (6), child-safety section |
| `test_a_research_baby_cardigan_runs_concept_to_pdf` | 3–24 m (5), no buttons, child-safety section |
| `test_every_admitted_garment_pair_has_a_pinned_proof_and_others_are_held` | router sweep |

The fixture concepts give a specific occasion. The #83 jury correctly refused an "everyday thing for oneself" premise; the gate is unchanged.

## Test expectations changed (more gates apply now, nothing weakened)
- `test_eng_plush::test_baby_garments_and_unbuilt_baby_items_are_held_by_name`: a baby cardigan is now admitted to `garment_raglan`. A baby side-to-side vest is still held.
- `test_eng_families` meta-guards: the admitted-family set, the (family, category) sweep and the report table now include the two garment families and garment probes (adult one-piece, vest, pullover are swept and held).
- `test_garment_design` (varied concepts): child-table sizes of 12 and under from the tournament drop-shoulder template are now inside the child-safety gate.
  - They are held because the sleeves are sewn on and the seam notes do not say "through both loops".
  - The only refusals allowed are CHILD_SAFETY_*, and the stage must have run.
  - **Follow-up:** `products/garments.drop_shoulder_flat` seam notes need "through both loops; bury the tails". That changes Harbour's released text, so it needs a version bump and is not done here.

## Suites (final tree, e78f87b + this fix)
- `test_eng_garment`: 28/28, including the 3 end-to-end tests and 11 mutation tests.
- Exit 0 (31 suites):
  - core: eng_families, compiler, twin, reverse;
  - product truth: s1_product_truth, s1_product_truth_2, s1_product_truth_3, s1_product_truth_4, blanket_size_truth;
  - deliverables and intake: deliverable_qa (928 s), w5_concept_intake;
  - grading: graded, grading, cert_grading, k9_graded_truth, garments, garment_design, benchmark_garment, w4_overnight_grade;
  - children's and plush: eng_plush, opus2_a1_children, opus2_amigurumi, childrens, a1r_child_safety_core, w4_children;
  - other: gates, w4_resume_runner, v11_autonomy_timeline (map regenerated with the module), vacuity.
