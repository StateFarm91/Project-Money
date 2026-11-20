# Batch 18 fixes: plush, vis-gallery, pdf-template, composer, seo-price

- Written 2026-11-20 UTC. Base: `origin/eng/colourwork` 9479c0e9, which is Batch 17 b098fcce plus one docs commit. Every branch below contains b098fcce.
- No PR was opened. No secrets or Railway variables were read. Every push was a merge; nothing was force-pushed.
- Suites were run with `PY=<venv from requirements.lock + requirements-test.lock> JOBS=1–4 SUITE_REGISTRY=0 THEN_FULL=0 SUITES=… bash run_tests.sh` on each pushed tree, and every tree was clean at the start of its run.
- In each merge, BUILD_STATE.md and DECISION_LOG.md keep both sides. `autonomy_map.json` was regenerated with `python -m brambleloop.autonomy.map --write src/brambleloop/autonomy/autonomy_map.json`.

| Unit | Pushed SHA | Tested SHA | Passing | Failing suites |
|---|---|---|---|---|
| eng/plush | `de1669c776fc91dd6b3f243b3103044ba29ff200` | same | 272 | 0 |
| eng/vis-gallery | `46c1b0cbdb917e8ca1ec6a78b1419336d44bc542` | same | 94 | 0 |
| eng/pdf-template | `137abfad14d595be8dbcc3cef0a2060d6a67b704` | same | 203 | 0 |
| eng/composer | `5171734d75d059d58711ad5ef58e0b1c9523b72d` | `7b827607` (the pushed SHA only adds a merge of the docs-only 73cedf1, which someone else pushed to `ENG-COMPOSER.md`) | 204 | 0 |
| eng/seo-price | `c87d8d39dbb7b3f5c1b9c007e5d3d4155565a730` | same | 121 | 0 |

## eng/plush (b18-c §C, HIGH: child safety)

The merge's `child_safety.py` conflicts were resolved as follows:
- `_cord_word` and the base's `_picked_up_joins`, `garment_months` and `_garment_closures` are all kept.
- The chain-run loop keeps the base's "the next row works into it" exemption, using plush's `chain_runs(row)`.

The fixes are exactly as specified:
- **(a)** The plush early return in `applies()` is deleted. It had let graded garments skip the gate. Every graded baby or child garment is back inside the gate, including GARMENT_CLOSURES.
- **(b)** In `_STITCH_LOOP_TERMS`, `\s+loops?` is now `[\s-]+loops?`, so "back-loop bands" is read as a stitch term.
- **(c)** `test_eng_plush` now asserts the opposite of the old exclusion. It uses the real graded CIRs for every size of `little-wren-baby-cardigan` and `brookside-kids-sweater`, and checks `garment_months` is not None and `CS.applies(cir)`.

Suites:

| Suite | Passing | Failing |
|---|---|---|
| test_eng_plush | 73 | 0 |
| test_eng_garment (added to the review list) | 28 | 0 |
| test_opus2_amigurumi | 9 | 0 |
| test_opus2_a1_children | 2 | 0 |
| test_eng_families | 16 | 0 |
| test_compiler | 9 | 0 |
| test_twin | 8 | 0 |
| test_reverse | 18 | 0 |
| test_deliverable_qa | 61 | 0 |
| test_vacuity | 8 | 0 |
| test_w4_resume_runner | 40 | 0 |

Known issue: the merge commit message has no session trailer, because the commit was made before the suite run that is bound to its SHA.

## eng/vis-gallery (b18-a A-1)

- `ops/retention.py` KNOWN_READ_ACTIONS is the union of both sides (gallery rows and ENG-DAILY rows).
- `test_search_hero_publish` now drives the happy path with `housewarming-key-basket` / `basket`, the complete-gallery product, as `test_visual_factory_e2e` does.
- The same test asserts that the 6-frame `cloudline-baby-blanket` stays `blocked` with "gallery incomplete" and creates no draft.
- `CAMPAIGN_MIN_FRAMES` is unchanged.

Suites:

| Suite | Passing | Failing |
|---|---|---|
| test_search_hero_publish | 4 | 0 |
| test_visual_factory_e2e | 6 | 0 |
| test_vis_gallery_e2e | 9 | 0 |
| test_vis_gallery_gates | 14 | 0 |
| test_owner_gallery_complete | 5 | 0 |
| test_disclosed_certified_upload | 8 | 0 |
| test_vacuity | 8 | 0 |
| test_w4_resume_runner | 40 | 0 |

`test_w4_readback_evidence` was not run because the httpx2 environment issue is still unresolved.

## eng/pdf-template (b18-c §B, HIGH)

- **Fibre.** In `tests/fixture_amigurumi.py`, the face floss is now "black cotton embroidery floss (face)". `fibres_named` now reads cotton, where it had blocked on an unnamed fibre. Production code is unchanged.
- **Size, a further defect found while fixing.** On the merged tree, ENG-PLUSH (base) makes a closed toy's circumference count as its size: `StatementFacts.available()` accepts `size_text`. However, `size_label` returned "" whenever `finished_size_cm` was None, so the age statement printed "finishing at  at the stated gauge".
  - Fixed in `intel/childrens.py`: `size_label` now prints `size_text` when present.
  - The two amigurumi tests now assert that the circumference is printed in the child-safety text.
  - The tests also assert that a toy with no statable size at all still blocks in `[notes]` on `finished_size_cm`.
  - This also needs to land with plush, or with any integration of plush, since the same defect is in the base.

Suites:

| Suite | Passing | Failing |
|---|---|---|
| test_pdf_template | 31 | 0 |
| test_pdf_standard | 23 | 0 |
| test_owner_gallery_complete | 5 | 0 |
| test_compiler | 9 | 0 |
| test_twin | 8 | 0 |
| test_reverse | 18 | 0 |
| test_deliverable_qa | 61 | 0 |
| test_vacuity | 8 | 0 |
| test_w4_resume_runner | 40 | 0 |

## eng/composer (b18-c §A)

- `pdf_standard._LABEL`: the base's `(?<![Aa]fter )` was kept.
- **A1 (HIGH).** `test_eng_composer` now asserts that `cases` and `probes` are non-empty before each of the three loops.
- **A2 (MEDIUM).**
  - `compose()` turns a non-dict plan, or any error in `validate()` that is not a ComposeRefused, into `ComposeRefused("plan", …)`.
  - A new test covers make="two", block from="x" and parts=["body"]. It also checks that `adjudicate()` refuses all three and then composes the good plan.
- **A3.** This was confirmed: the test asserts `exc.primitive == primitive`, so a KeyError cannot satisfy it.

Suites:

| Suite | Passing | Failing |
|---|---|---|
| test_eng_composer | 21 | 0 |
| test_eng_families | 16 | 0 |
| test_pdf_standard | 23 | 0 |
| test_compiler | 9 | 0 |
| test_twin | 8 | 0 |
| test_reverse | 18 | 0 |
| test_deliverable_qa | 61 | 0 |
| test_vacuity | 8 | 0 |
| test_w4_resume_runner | 40 | 0 |

## eng/seo-price (b18-b B-1)

The B1 gates are unchanged.
- `test_w4_seo_packages` chains now seed four FIXTURE research-shelf rows with original, non-overlapping titles. They also seed the fixture taxonomy, so the package is CERTIFIED.
- A new test checks the no-taxonomy case: listing.seo blocks with `CATEGORY_UNKNOWN` and persists no package.
- The same test checks the no-shelf case: listing.seo blocks with `TITLE_ORIGINALITY_UNKNOWN` and persists no package.
- Assertions that described the old EXTERNAL_GATED package now describe the CERTIFIED package. That state can no longer be persisted.

Suites:

| Suite | Passing | Failing |
|---|---|---|
| test_w4_seo_packages | 7 | 0 |
| test_eng_seoprice | 27 | 0 |
| test_v11_seo_cycle | 8 | 0 |
| test_w4_c09_seo | 10 | 0 |
| test_v11_seo_taxonomy | 4 | 0 |
| test_v11_seo_truth | 9 | 0 |
| test_w3_seo_constraints | 8 | 0 |
| test_vacuity | 8 | 0 |
| test_w4_resume_runner | 40 | 0 |

Open before landing (from the reviewer): confirm that production has research-shelf rows for every pod that has listings due for SEO. If a pod has none, its listings stop at SEO, which is fail-closed.

## Not done

- The full unfiltered suite was not run on any branch.
- The b18-a follow-ups A-2, B-1 and B-2 were not addressed.
- The b18-c LOW items (pdf-template page splitting, and the resume-runner load flake) were not addressed.
