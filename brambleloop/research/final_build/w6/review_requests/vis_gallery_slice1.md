# [ENG-VIS-GALLERY] slice 1 — review request

Branch `eng/vis-gallery` (from `claude/w6-INTEG3` 39b92619, merged `eng/visual-factory` c774d740). Not integrated, not deployed.

## What changed
| Area | File | Change |
|---|---|---|
| H2 exception route | `publish/eligibility.py` | `GALLERY_ROUTE`, `GALLERY_JOBS`, `GALLERY_CHECKS`, `gallery_exception`; `verified_exception` dispatches on `route`. `etsy_policy` removed from `EXCEPTION_CHECKS` (owner order). |
| Evidence producer | `visual/candidate_gates.py` | `exception_evidence` emits `route`, `honesty_label`, `sha256`, `structural_sha256` (the bytes product truth was measured on), `fidelity_release`, motif/anatomy readings and full provenance from the record; `motif_reading` (real `motif_fidelity.check`), `RealJudges.motif_fidelity`; generated hero allowed only in the route; no `ETSY_POLICY_UNKNOWN` blocker. `_anchor_of` accepts the route's own run key. |
| H1 certificate route | `visual/gallery_persist.py` | `frame_matrix`, `gallery_status`, `certify_gallery`, `advance`; blockers carry gate, status, reason, owner agent, next action (repair/measure/hold, bounded). Frames stored at position 100+slot (assets.build rows hold 1..n). |
| Listing set | `publish/release_gates.py` | `generated_selection`, `certified_contents_frame` (CONTENTS preview re-verified with `check_supplement`), `generated_listing_set` (per-frame `generated_frame_verdict`, #65, 7-frame standard, #66 mobile, #60 dims, certificate via `_record_certificate`); `listing_set` routes to it when a selection is current; disclosed path ignores gallery-route frames. |
| Campaign | `visual/shot_plans.py` | `flux_campaign_for` / `flux_campaign_plan`: 7 slots (hero, flat-lay, lifestyle, angle/back, stitch close-up, scale/fit, download info) per family (worn / soft / lived_with / small_goods). |
| Run plumbing | `visual/image_production.py` | `trigger(route=)`, `run_key(..., route=)` → `~gallery`, route threaded through stages/candidates/reverify/restart; `_spend_plan(key, db)`: owner cap + route call cap 20 (money cap CA$2.00 unchanged). |
| Spend | `visual/gallery_budget.py` (new) | owner-lowerable per-gallery cap; refuses raise above code cap and non-owner actors. |
| Upload | `runtime/etsy_ops.py` | a `generated_render` frame keeps its certified alt text (CONCEPT_LABEL). |
| Guards | `ops/retention.py`, `ops/health.py` | new audit actions classified (selection protected); `motif-frame-` temp prefix. |

## Decision to confirm (D-OWNER-FLUX-GALLERY)
Inside the route only: generated hero allowed (ASSET_CONCEPT_AS_HERO) and F-853 does not refuse DETAIL/SCALE/COLOUR_CONTEXT; both are carried by structural truth on exact bytes + motif fidelity against the CIR chart. Outside the route nothing changed. Please confirm or veto.

## Proof
- `tests/test_vis_gallery_e2e.py` 5/5 (≈4 min): full chain to FakeEtsy draft; 7 images + US/UK PDFs byte-for-byte; failing frame blocks with reason, ≤ `MAX_ATTEMPTS_PER_ROLE` attempts, next action `hold`; UNMEASURED frame blocks with `measure`; Laura publication UNMEASURED without ENG-VIS-IDENTITY's approval.
- `tests/test_vis_gallery_gates.py` 12/12; `tests/_vis_gallery_mutants.py` 21/21 killed.
- Doubles, all labelled: stub FLUX pixels, StubJudges (identity/anatomy/realism/body/outfit), V1 end-band rule on scene frames, vision transports, Laura per-image approval, FakeEtsy.

## Suites run (63 files; all exit 0 except as noted)
Every suite naming gallery, eligibility, candidate_gates, shot_plans, release_gates, listing_asset, disclosed, model_photography, owned_photography, f852, ownerimg, campaign, v6, codex_v1, motif, search_hero, w4_visual, flux, identity, retention, plus test_cert_publish_gates, test_visual_factory_e2e, test_visual_pipeline_evidence, test_model_spend_paths, test_cost_governance_wave2, test_w4_resume_runner, test_v11_autonomy_timeline, test_w4_adopt_manual_listing.
- Updated for the owner's Etsy order: `test_w4_f852_amend` (8 conditions, not 9), `test_w4_ownerimg`, `test_v6_gallery_e2e` (ETSY-POLICY no longer a remaining gate).
- `test_codex_v1_*` need pytest (fail without it by design): 43 / 13 / 62 passed under pytest.
- `test_cert_publish_gates::test_the_qa_stage_stores_the_context_renders_and_publish_only_verifies_them` FAILS — and fails identically on the unchanged base tree (verified with the changes stashed). Pre-existing, not touched.
- sw.js not touched.

## Not done (slices 2–3)
assets.build does not trigger the FLUX route yet; recovery-first re-check of paid images (coordinate with eng/motif-backlog); `visual_pipeline` production-evidence counts; e2e-level mutants on `generated_listing_set`.
