# Wave 3, cluster lane K12: visual residuals (model photography)

Branch `claude/w3-K12`, based on `claude/visual-investigation` @ 8f54d40. The rows come from
the closure audit `CLOSURE_f0c2d12.md`, cluster K12. Shadow phase throughout:

- no network, no provider call, no spend;
- no Laura asset touched, `visual/canonical.py` and `visual/assets/**` unchanged;
- no image approved for publication.

Every row was checked against the current code before any change was made.

## Rows

| Row | Status | Evidence (test → consumer) |
|---|---|---|
| **F-212** Reference conditioning proven end-to-end | **COMPLETE** | `gateway.images.conditioning_receipt` reads the exact request body that `_post` sends. It records each reference's sha256 and whether its bytes are in the body (base64 inline for google/bfl, the raw multipart upload for openai). `generate()` attaches `conditioning` to every result. It refuses before any budget is reserved when a requested reference is not carried; BFL carries only the first of several. `reference_probe` now sets `ok` only on a proven receipt, and `reference_proven` ignores legacy probes that have no receipt. Tests: `test_f212_*` (3). Live consumers: `images.generate`, which is reached by `ops.capability_probes`→`reference_probe`, by the `image_bench` handler, and by the `visual.provider_trial` handler. |
| **F-213** Identity trial validity | **COMPLETE (machinery)**; live-root pending wiring | `visual.identity_gate.trial_validity` returns INVALID for missing reference bytes, unsupported conditioning (receipt not proven), an expired reference (an `expires_at` in the past, or a superseded/forbidden canon hash) or a non-canonical reference. It returns UNMEASURED for a missing judge pair or unmeasurable morphology (bust/torso). In both cases `score: None` and `counts_against_provider: False`. Test: `test_f213_invalid_and_unmeasured_trials_are_never_a_score`. Consumer: `visual.rnd.loop.record_judgement`. |
| **F-219** Human review escalation band | **COMPLETE (machinery)**; live-root pending wiring | `identity_gate.assess` sorts each frame into a band: drift seen by any judge is AUTO_REFUSE (FAIL, the existing rule, kept); an invalid trial is INVALID (UNKNOWN); anything not provably her is REVIEW (UNKNOWN, blocks). REVIEW results are persisted in the new table `visual_rnd_identity_reviews`, idempotent per subject and image. `resolve()` records the reviewer's decision and never approves anything for publication. The open queue is surfaced in `visual.rnd.status.summary()["identity_review"]`. Tests: `test_f219_*` (2). |
| **F-677** Final image gate | **COMPLETE (machinery)**; GATED for garments | `visual.final_image_gate.evaluate` returns PASS only when the source is a disclosed render that passes `product_authority.structural_floor` (the pixel verifier against the certified CIR) **and** every non-background product pixel of that render is unchanged in the judged image (`compose.verify`, bound by sha256). PASS covers neckline, sleeves, silhouette, stitch family, colour placement, dimensions and construction. A vision reading can only FAIL an image; "match" alone is UNKNOWN. A pure generation is UNKNOWN. `record_judgement` now computes `product_truth`/`structure` for model-bearing classes and overrides any PASS the caller supplies. Tests: `test_f677_*` (2), including one changed product pixel → FAIL. GATED: garments have no qualified renderer yet (F-852), so garment model photography stays UNKNOWN. |
| **F-732** Exact identity, not a similar person | **COMPLETE (machinery)**; biometric floor **GATED** | A PASS needs all of: a proven receipt over her *current* reference hashes; two judges who each give `laura_verdict` = laura with the morphology floor readable; and a deterministic biometric floor (cosine computed in code, thresholds fixed per *qualified* embedder in `QUALIFIED_EMBEDDERS`). The registry is empty in this build because no face-embedding model is installed. As a result every non-drift Laura frame goes to REVIEW, and no Laura frame can be accepted. GATE: `image_vision` / a face-embedding model dependency that must be qualified (owner/model_provider). Tests use a fake embedder that each test registers and removes. |
| **F-877** Bounded visual spend | **COMPLETE** | `visual.spend_plan`: `build`, `problems`/`validate` (hypothesis, provider/model, call count, max spend, pass and fail criteria, price × calls ≤ cap) and `guard` (per-call count and ceiling). `rnd.loop.experiment` stores `paid_plan` on every GATED_SPEND row. `execute_paid` refuses an incomplete plan before it consults the paid gate, which stays closed. `provider_trial.run` validates `trial_plan()` and guards every render; that run is live through the `visual.provider_trial` runtime handler. Status lists `paid_plans_incomplete`. Tests: `test_f877_*` (2). |

## Files

- **New:**
  - `src/brambleloop/visual/identity_gate.py`
  - `src/brambleloop/visual/final_image_gate.py`
  - `src/brambleloop/visual/spend_plan.py`
  - `tests/test_w3_k12_model_photography.py` (10 tests)
- **Modified:**
  - `gateway/images.py`
  - `visual/rnd/models.py`: new table `VisualIdentityReview`, added to `TABLES`.
  - `visual/rnd/loop.py`: `record_judgement` takes `identity_evidence`/`product_evidence`; adds `paid_plan` and the plan check in `execute_paid`.
  - `visual/rnd/status.py`
  - `visual/provider_trial.py`
- **Tightened, not weakened:** `tests/test_w3_visual_rnd_guard.py::test_laura_identity_is_a_hard_independent_gate`. Its last case gave one judge's all-match reading plus caller PASS gates, and it was **accepted**. Under F-219/F-677/F-732 it can no longer pass. The assertion now checks that the case is refused, and that the measured consistency is 0.0 rather than UNKNOWN. The fully-evidenced accepted path moved to `test_f677_and_f732_rnd_door_overrides_caller_pass`.

## Tests run (focused, never the full suite)

| Result | Suites |
|---|---|
| All pass | k12 10/10; w3_visual_rnd_guard 6/6; w3_visual_rnd_loop 8/8; provider_trial 22/22; image_bench (all); model_identity 28/28; model_photography 44/44; model_tournament 18/18; final_visual_authority 10/10; cert_cost 19/19; originality 28/28; model_spend_paths 12/12; reachability 11/11; w3_reachability_dynamic 3/3; vacuity 7/7; secret_scan 7/7 |
| Pre-existing failures | cost_governance_wave2: 35 OK, 4 FAIL. The 4 failures are identical on the base: retention has no decision about `support.defect_candidate`. Not this lane's. |

## WIRING REQUESTS

These are the same requests lane H already made. They make F-213/F-219/F-677/F-732 reachable from a live root:

1. **Lane D:** add a `visual.rnd.cycle` job handler that calls `visual.rnd.loop.cycle(db)`, plus a cadence (handoff_H.md #2). The `visual_rnd_identity_reviews` table is created lazily by `ensure_tables`.
2. **Lane F:** in the Command Center, render `visual.rnd.status.summary(db)`, including the new `identity_review` queue (show the band and its reasons; never present a review as publication approval) and `spend.paid_plans_incomplete`.

## Not verified / gated

- No real render was made. Every identity and product-truth result on real model photography is GATED on spend authority, and a face-embedding model must be qualified before the biometric floor can be measured.
- Behaviour change: `reference_proven` will re-probe a provider whose last probe predates receipts. That costs 2 renders (about CA$0.06–0.28) inside an owner-authorised benchmark run, and only there.
- BFL multi-reference requests are now refused rather than silently sent with only the first reference.
