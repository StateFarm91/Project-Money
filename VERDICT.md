VERDICT: SHIP c774d740a790d3fba073e65e27afa47ced205472

# Independent review: eng/visual-factory @ c774d740 (FULL), merged onto claude/w6-INTEG2 @ cde89a4b

- Merged tree: be2b21af. The only conflict was `brambleloop/BUILD_STATE.md` (documentation, both sides kept). Every suite ran on the merged tree.
- No Etsy, Railway or production call was made, and no secret was read.

## Scope of the unit

The unit makes three changes:
- It adds the `visual_pipeline` evidence section (`ops/production_evidence.py`) and its advisory readback row (`ops/readback.py`).
- It adds the seven-frame campaign standard (`visual/shot_plans.py campaign_standard`), enforced in `image_production.readiness`.
- It adds two test suites: `test_visual_pipeline_evidence` and `test_visual_factory_e2e` (stub FLUX, labelled stub judges, FakeEtsy).

The unit does **not** touch:
- the Laura identity lock;
- `candidate_gates`;
- `eligibility` (F-852 and the D-W4-F852-AMEND verified-exception route);
- the PDF builder;
- spend or reservations.

## Why SHIP

- The unit is honest and only tightens. It weakens no gate.
- It changes no spend path, and it sends no generated frame to publication. `test_visual_factory_e2e` a4 pins that `approve` refuses a generated gallery.
- It reports UNKNOWN, never 0, for anything it cannot read.
- The endpoint is behind the read-only readback token (`app/security.py:321`).

**This SHIP is for the slice only. It does NOT accept the visual factory.** Most of the owner's acceptance criteria are still unmet in production. They are listed below as HIGH gaps. None of them is a regression from this unit.

## Answer: can generated galleries be produced in production? NO.

Generated galleries still cannot be produced in production after this unit. What remains:

1. **Stage 8: no certificate route for generated frames.** `publish/release_gates.py:550-557` certifies only the disclosed render set while that set is current, and `gallery_persist.recertify` returns `blocks_release=True`. The audit plans a fix as "S3", but it is not built.
2. **The F-852 verified exception is never supplied.** `eligibility.verified_exception` (`publish/eligibility.py:449`) exists. The unit respects it and does not bypass it. But no production path produces exception evidence that would pass, so every generated render is still refused (`eligibility.py:455`).
3. **Laura identity cannot PASS.** `identity_gate.PRODUCTION_QUALIFICATIONS = ()`, `QUALIFIED_EMBEDDERS = {}` and `vision_judges.SECOND_VISION_TRANSPORT = None`. This needs OWNER ACTION (choose and fund a method).
4. **`image_generation` and `image_vision` are not owner-activated, and no BFL key is set.** This needs OWNER ACTION.
5. **Motif fidelity is not on the generated path.** `publish/motif_fidelity.py` is used only by owned and model photography. `eng/motif-backlog` is not on origin.
6. **SHADOW phase and the owner publication grant** are already tracked by first-listing doors.

## What slice 1 (and S2) covers, and the gaps

- **Covered:**
  - evidence counts read from persisted rows;
  - the readback row;
  - the seven-frame standard;
  - e2e proof B: certified PDFs (US+UK) and certified images reach FakeEtsy and are read back byte for byte.
- **Not covered:** the findings below.

## Findings

### HIGH — owner-criterion gaps (not regressions; the merge stays safe)

- **H1 Imagery / Product: no production route for a generated gallery to certify.**
  - Where: `publish/release_gates.py:550-557`; `visual/gallery_persist.py:18` ("Today step 2 always refuses").
  - Failure scenario: an owner funds FLUX and vision, and every frame reads PASS. `approve` still writes no `listing_assets` row and issues no certificate, so no generated image ever reaches a listing.
- **H2 Redraw policy: the verified-exception route has no producer.**
  - Where: `publish/eligibility.py:449-470`; `visual/candidate_gates.py:602` reads the evidence from checks.
  - Failure scenario: nothing on the production generation path emits an `honesty_label` and the `EXCEPTION_PROVENANCE` fields (model, references, release, prompt_version, receipt, disclosure). Every generated product frame therefore stays F-852-refused.
  - The route is respected, not bypassed: PASS for policy, gap for production.
- **H3 Verification: there is no production-qualified identity method.**
  - Where: `visual/identity_gate.py:57,237`; `visual/vision_judges.py:933`.
  - Failure scenario: every Laura frame is REVIEW/UNKNOWN, so no Laura gallery can pass. It fails closed, which is correct, but the criterion "identity QA" is not met in production.

### MEDIUM

- **M1 Identity lock: the reduced-conditioning refusal is untested. A mutant survived.**
  - Where: `visual/image_production.py:1171`.
  - Mutation: `if len(out) != len(CURRENT_REFERENCE_HASHES)` changed to `if len(out) < 1`. `test_w4_condpack`, `test_w4_ownerimg` and `test_visual_factory_e2e` all still pass (47/0).
  - Failure scenario: a refactor lets generation run with 1 or 2 of Laura's 3 canonical references, and no suite catches it.
  - Defence in depth still exists (`creative/image_stages.py:257`; `identity_gate.trial_validity:94`), but the primary lock has no pin.
  - Fix: add a test that removes one reference file and asserts `ConditioningRefused`.
- **M2 Honesty of evidence: "galleries valid" overstates.**
  - Where: `ops/production_evidence.py` `_vp_runs` (`valid = ready_for_owner_review + approved_for_publication`).
  - A run in `ready_for_owner_review` still carries `publication_blockers` (F-852, stage 8).
  - For an experiment run, the owner card skips `set_check` (`image_production.py:1385`, `exp is None`).
  - Failure scenario: the readback prints "galleries valid 1" for a gallery that cannot be certified or published. Rename the count to `awaiting_owner_review`, or count only certified galleries.
- **M3 Process: there is no review request.**
  - No file for ENG-VISUAL exists under `brambleloop/research/final_build/w6/review_requests/`.
  - The audit (`research/final_build/w6/visual_factory_audit.md`) was used instead.
  - The audit's base line says `a35ad302`; the actual base is `cde89a4b`.

### LOW

- **L1 Redundant code: one readiness clause is redundant (equivalent mutant).**
  - Where: `visual/image_production.py:2060`.
  - Removing `and standard["ok"]` from `gallery_ready` survived, because the shortfall is already injected into `set_check` (`:2035-2037`).
  - It is harmless and it is defence in depth. Note only.
- **L2 Evidence: `_vp_drafts` can skip the newest audit row.**
  - Where: `ops/production_evidence.py` `_vp_drafts`.
  - When the newest audit row for a release has no `etsy_listing_id`, an older row is used instead. A failed re-publish can then leave an older "fully read back" draft counted.
  - It is advisory only.
- **L3 Product consistency covers only what vision reports.**
  - `cross_frame_product` compares only yarn-colour count and edging. Cross-frame stitch-pattern and motif identity is not judged.
  - Today an unjudged pair is UNKNOWN (fail-closed), so this is not a pass path. It is a coverage gap for "Product IDENTICAL".
- **L4 PDFs: family-aware PDFs are not in this unit's scope.**
  - The garment branch exists (`publish/pdf.py:599-720`). The PDF suites pass on the merged tree.
  - The unit adds no family-aware requirement test, so the criterion is not re-verified here.

## Owner criteria against this unit

| Criterion | Result |
|---|---|
| Imagery | Gap (H1). |
| Laura | Lock intact. M2 identity-id swap killed by 8+ tests. Reduced-conditioning pin missing (M1). |
| Outfits | Registry and per-gallery FAIL intact. Outfit-check mutant killed. |
| Product | Consistency gate intact. Mutants killed. Production coverage gap (L3, H1). |
| Honesty | No generated frame is presented as a sample. Disclosure untouched. M2 is a labelling issue. |
| Spend | Untouched. `test_model_spend_paths` and `test_cost_governance_wave2` pass. The e2e spends CA$0. |
| Verification | Fails closed. UNKNOWN never reads as PASS (M3 mutant killed). |
| Paid images | Not touched by the unit. Recovery producer absent (`recovered_images` = UNKNOWN, honest). Gap carried to motif-backlog. |
| PDFs | Not in scope (L4). |
| Redraw policy | Respected, not bypassed. Route has no producer (H2). |

## Mutation results (merged tree, each reverted after its run)

| Mutant | Change | Result |
|---|---|---|
| M1 | identity lock: accept fewer than 3 canonical references | **SURVIVED** (47 pass / 0 fail) → finding M1 |
| M2 | identity lock: `IDENTITY_ID` changed to `laura-r3-…` | KILLED (`test_w3_laura_core_identity`, `test_canon_manifest`, `test_visual_pipeline_evidence`, …) |
| M3 | product gate: unjudged pairs read as PASS | KILLED (`test_v2_gallery_consistency` and 1 other) |
| M4 | product gate: multiple-outfit check dropped | KILLED (`test_incompatible_gallery_mix_is_refused`) |
| M5 | product gate: version, release and CIR mix check dropped | KILLED (3 suites) |
| M6 | `campaign_standard` always ok | KILLED (`test_visual_campaign_standard`) |
| M7 | `standard["ok"]` dropped from `gallery_ready` | SURVIVED (equivalent mutant) → finding L1 |

## Suites on the merged tree be2b21af

- Command: `JOBS=4 SUITE_REGISTRY=0 bash run_tests.sh`.
- Selection: the 60 suites named in the brief:
  - the unit's own suites: `test_visual_campaign_standard`, `test_visual_factory_e2e`, `test_visual_pipeline_evidence`, `test_v2_gallery_consistency`, `test_w4_readback_evidence`;
  - every suite whose name contains laura, model_photography, owned_photography, gallery, motif_fidelity, deliverable, pdf or eligibility;
  - `test_model_spend_paths`, `test_cost_governance_wave2` and `test_w4_resume_runner`;
  - the always-add guards: `test_vacuity`, `test_w3_tmp_hygiene`, `test_etsy_oauth_callback`, `test_w4_fmbatch1_retention_guard`, `test_w4_adopt_manual_listing`, `test_w4_c12_wiring`.
- **Result:**
  - TOTAL PASSING: 768; suites failing: 0 of 60;
  - environment failures: 0;
  - TMP leaked: 0;
  - duration: 907 s;
  - tree clean at start.
