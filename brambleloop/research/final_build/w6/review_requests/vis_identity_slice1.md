# Review request: ENG-VIS-IDENTITY slice 1

Branch: `eng/vis-identity`. Base: `origin/claude/w6-INTEG3` (39b92619) with `origin/eng/visual-factory`
(c774d740) merged in. The merge conflicts were BUILD_STATE and the suite list; both sides were kept.

**Not deployed. Laura identity still HOLDs in production. That is correct, and why is explained below.**

## What to review

| file | change |
|---|---|
| `src/brambleloop/visual/face_embedder.py` | **new.** YuNet+SFace ONNX embedder: numpy and onnxruntime only, sha-pinned weights, exactly one face. |
| `src/brambleloop/visual/identity_calibration.py` | **new.** Calibration, derived thresholds, FAR/FRR with Clopper-Pearson bounds, production floors, a content-hashed evidence file, and record building. |
| `src/brambleloop/visual/identity_records.py` | **new.** The `visual_identity_records` table. Append-only, idempotent, registered in `Database.register_models`. |
| `src/brambleloop/visual/identity_gate.py` | Changes: the all-three-references rule; `production_calibration_refusals`; the `assess` wrapper adding `verdict`, `judge_agreement` and `hold_reasons` (the old body is now `_assess`, unchanged); `production_floor()`. |
| `src/brambleloop/visual/vision_judges.py` | Changes: the OpenAI second-judge factory (`SECOND_VISION_TRANSPORT`); `identity_check` now exposes the verdict, references, readings and agreement; the blind outfit-vs-reference check; `transports_independent`. |
| `src/brambleloop/visual/candidate_gates.py` | Changes: `RealJudges` takes the production embedder by default; `gate_status` treats a non-PASS `verdict` as UNKNOWN; `_identity_record` writes the record for every Laura frame. |
| `src/brambleloop/visual/outfits.py` | `claim()`: an idempotent compare-and-set outfit claim. |
| `tests/test_eng_vis_identity.py` | **new.** 38 tests, including 8 gate mutants. |
| `tests/test_v3_identity_qualification.py` | Two pins updated:<br>(1) the second transport is now wired, and is None with no key;<br>(2) "the fixture reading without its label" now also carries `verdict: PASS`. Stripping the label alone is now caught by the verdict guard, which is asserted. |
| `research/final_build/w6/identity_calibration/*` | The calibration set manifest, the evidence (sha 6884612e…), the run script and the negative generator (gateway-reserved, not run). |
| `research/final_build/w6/IDENTITY_OWNER_DECISIONS.md` | Options, costs and the four owner decisions. |
| `scripts/fetch_face_models.py` | Downloads the two models and verifies them by pinned sha. |

## Interfaces for ENG-VIS-FLUX and ENG-VIS-GALLERY (stable)

- **`candidate_gates` checks** carry `checks["identity"]["verdict"]`, which is one of `PASS`, `HOLD`
  or `REFUSE`. Read the verdict, not `status`.
  - Each identity check also carries `judge_agreement`, `hold_reasons`, `references` (sha and
    bytes), `readings` and `biometric.qualification`.
  - Laura frames also get `checks["identity_record"]` with its `record_id`.
- **`identity_records`** provides `latest(db, image_sha256)` and `history(db, image_sha256)`.
- **`outfits.claim(db, listing)`** returns `{status, outfit_id, outfit, claimed}`. Call it before
  generating a listing's gallery, and condition every frame on that outfit.
- **`identity_gate.production_floor()`** returns `{embedder, qualification, why}`.

## Evidence

- `tests/test_eng_vis_identity.py`: 38/38 pass, with and without `BRAMBLELOOP_FACE_MODEL_DIR`.
  With the models installed, the real SFace calibration reproduces the committed evidence exactly.
- The required suites were run before and after on the same set. The results are in the PR comment.

## Known limits

- Only 10 impostor faces exist. FAR is 0/10, but its upper bound is 25.9%, so the method is not
  production-ready. The fix is `generate_negatives.py` on the worker: about 34 grids for US$1.63.
  It was not run here because no BFL key was reachable.
- No genuine labels beyond the 12 owner-viewed frames exist yet. The owner must label 18 or more.
- `onnxruntime` is not in `requirements.lock` yet. That is slice 2, after owner Decision 1.
