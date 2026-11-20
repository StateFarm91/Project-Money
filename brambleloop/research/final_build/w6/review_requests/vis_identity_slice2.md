# Review request: ENG-VIS-IDENTITY slice 2

- **Branch:** `eng/vis-identity`.
- **Base:** slice 1 at `96f5b294`, which was reviewed SHIP.
- **Final SHA:** the commit that adds this file (see the #28 comment).
- **`eng/vis-flux`:** not merged; Main integrates by branch. The Decision 2 generator uses
  `gateway.flux_provider.readiness` when that module is present. Otherwise it uses the same two
  checks on this branch's gateway: the key present and the owner's `generation` activation.
- **Spend:** none. No image was generated and no model was called.

**Laura identity still HOLDs in production, and that is correct.** The held-out
re-measurement makes the case stronger: 2 of 6 held-out look-alikes cross the derived
`match_at`.

## Review findings

| # | finding | fix | test |
|---|---|---|---|
| F1 | The v3 test assumed `prod.embedder is None`, which fails once the models are installed. | It now asserts `qualification is None`, verdict HOLD and biometric UNMEASURED, for one judge and for two. | `test_v3_identity_qualification::test_production_configuration_stays_unknown`. Passes with and without `BRAMBLELOOP_FACE_MODEL_DIR`. |
| F2 | In-sample FAR: `match_at` was set by the same impostors FAR was measured on. | `identity_calibration` is now `identity-calibration/2`. See [F2 in detail](#f2-in-detail). | `test_held_out_split_is_disjoint_deterministic_and_keeps_augmentations_together`; `test_qualification_refuses_in_sample_evidence` (v1 evidence, forged in-sample evidence with a valid hash, and a hand-built record without `evaluation`) |
| F3 | Outfit race: when the losing claim's outfit already had `uses`, the listing held two outfits. | `outfits.settle(db, listing)`. See [F3 in detail](#f3-in-detail). | `test_interleaved_claim_whose_loser_already_has_uses_leaves_exactly_one_outfit` (a deterministic interleave inside `claim()`, between the free-list read and the compare-and-set). This test **fails on the slice-1 code** (the listing held `['outfit-a-sage', 'outfit-b-plum']`). Also `..._both_outfits_have_uses_retire_the_later_one` and `test_reserve_racing_a_claim_settles_to_one_outfit`. |
| F4 | Reservation figure and the 4× over-reservation. | `GatewayVisionJudge.read` now reserves `providers.input_tokens(model, system, prompt, images=len(paths))`. See [F4 in detail](#f4-in-detail). | `test_vision_judge_reserves_the_providers_own_image_figure_never_less_than_the_gate` |
| F5 | `transports_independent` was never called. | Removed. Independence stays enforced by distinct judge ids (`person_readings` counts one id once). | `test_second_transport_is_a_different_provider_and_is_off_without_a_key` asserts distinct ids and that the helper is gone. |

### F2 in detail

- **The split** is deterministic, keyed by `sha256(salt:unit:sha)`.
  - Calibration takes 1/6 of genuine units and 1/3 of impostor faces; the rest is held out.
  - A genuine image and its augmentations always land in the same subset.
- **Thresholds** come from calibration rows only.
- **FAR and FRR, with exact 95% bounds,** come from held-out rows only.
- **The floors** (≥30 genuine, ≥300 impostors) apply to held-out counts.
- **`audit_split`** re-derives the split, the thresholds and the rates from the rows.
- **`qualification()`** raises `InSampleEvidence` on any mismatch, and on v1 evidence.
- **`identity_gate.production_calibration_refusals`** also refuses a record without
  `evaluation: held_out`, the v2 calibration version and the split method.

### F3 in detail

- **The winner** is the outfit with the earliest recorded use, or else the lowest id.
- **A loser with no uses** is released.
- **A loser with uses** is retired, stays bound to the listing as history, and has `replaced_by`
  set to the winner. The result tells the caller to regenerate its frames.
- **Both `claim` and `reserve` settle,** so whichever writer commits last resolves the race.

### F4 in detail

- The reservation is the OpenAI paid gate's own estimate, so it is never below it.
- The OpenAI second-judge read drops from CA$0.0913 to **CA$0.0292** reserved. The expected
  actual cost is about CA$0.015.
- gpt-4.1's worst case is 1,445 tokens per image; 1,600 are reserved per image.
- The doc figure is corrected: the old reservation was about CA$0.092.

## Models in the Railway build

- **Lock:** `requirements.lock` gains `onnxruntime==1.29.0`, `flatbuffers`, `packaging` and
  `protobuf`. It was regenerated with `scripts/lock_requirements.py` from a Python 3.11 venv, the
  same interpreter as the image.
- **Fetch step:** the Dockerfile runs `scripts/fetch_face_models.py --best-effort` after the locked
  install.
  - Only the fetch script and `face_embedder.py` (the pins) are copied first, so the layer is
    rebuilt only when the pins change.
  - The script now reads the pins by file path and streams to a `.part` file. It deletes any file
    whose SHA does not match.
  - It exits 0 under `--best-effort`, so a mirror outage can't break a deploy.
- **Load-time check:** `SFaceEmbedder.load` re-verifies both SHAs on every load. Missing or
  mismatched weights mean UNMEASURED, so identity HOLDs; never PASS.
- **RAM:** the ONNX CPU memory arena and memory pattern are now off. Load plus 3 embeddings is
  about 109 MB over baseline locally and 121 MB peak RSS in the image (budget about 120 MB), with
  unchanged speed (about 0.065 s per embedding).
- **Built and run in this session.** The sandbox needed host networking and its proxy CA added in
  a scratch copy of the Dockerfile; the committed Dockerfile has no sandbox changes.
  - Both models were fetched and verified.
  - `uvicorn` boots and `/health` returned `{"status":"ok", …}`.
  - `production_floor()` in the image loads `sface-yunet-onnx` with `qualification None`, so
    identity HOLDs.
  - Corrupting a model file in the container makes `production_floor()` return `None` with
    "sha256 … is not the pinned …".
- **Tests:** `test_dockerfile_fetches_the_pinned_models_without_breaking_the_build`,
  `test_fetch_script_reads_the_embedders_pins_and_deletes_a_mismatch` (file:// fixtures for good
  and bad SHAs and a missing URL, plus a `--best-effort` run with the network blackholed),
  `test_embedder_keeps_to_the_ram_budget_settings`.

## Owner Decision 2 tooling

- **Files:** `visual/identity_labelling.py` and `scripts/identity_contact_sheet.py`, with the
  subcommands `plan`, `generate`, `sheet`, `label` and `add`.
- **Plan:** 24 varied shots (4 framings × 3 angles, 6 lights, 4 expressions, 6 settings), with no
  two prompts the same. Each is conditioned on all three canonical references, verified by SHA.
  An altered reference refuses the plan.
- **`generate`** refuses before any reservation unless the key is present and the owner's
  `generation` activation is active.
  - It goes through `gateway.images.generate`: the ceiling reservation and the ledger.
  - Hard cap: US$1.16 (24 × US$0.048 = US$1.152).
  - It is idempotent: a frame on disk with its SHA is never re-bought.
- **`sheet`** writes a numbered 6×4 PNG and `label.html`. The page has one Laura / not Laura
  choice per frame and prints the exact `label` command; it sends nothing.
- **`label`** refuses in these cases:
  - any frame is unlabelled;
  - a frame is labelled both ways;
  - a number is not on the sheet;
  - no labeller is named;
  - a frame's bytes changed.
- **No default label exists.** Frames marked "not Laura" become impostors.
- **`add`** appends to `calibration_set.json`, idempotently by SHA.
- **Arithmetic:** with 1/6 of genuine samples spent on calibration, 30 held out needs 36 in
  total. With 12 today, all 24 frames must be confirmed, or a second sheet is needed. The doc
  says so.
- **Tests:** `test_contact_sheet_plan_conditions_every_frame_on_all_three_references`,
  `test_contact_sheet_generation_refuses_without_key_and_activation_and_spends_nothing`,
  `test_contact_sheet_generate_sheet_label_and_add_round_trip`.

## Re-measured evidence

`calibration_evidence.json` was regenerated with the real models (evidence sha `1854ae98…`):

| | calibration | held out |
|---|---|---|
| genuine | 2 | 10 |
| impostors | 4 | 6 |

- The calibration impostor max is 0.433, which gives `match_at` 0.49 and `refuse_below` 0.44.
- Held out: **FAR 2/6 (upper bound 72.9%)**, FRR 0/10.
- Not production-ready.
- The real-SFace reproduction test matches every field, including the split and the evidence
  hash.
- `IDENTITY_OWNER_DECISIONS.md` is updated:
  - the evidence table;
  - Decision 2 (24 confirmed frames, cost CA$1.63);
  - Decision 3 (CA$0.015 actual, CA$0.029 reserved);
  - impostors (about 450 faces, about 50 grids, CA$3.40);
  - deploying is now done;
  - monthly totals.

## Suites

All suites were run on this tree with Python 3.11 and the regenerated lock installed. Each
listed suite exits 0.

- **Identity, Laura, canonical, vision_judges and outfit users (49 suites):** every
  `test_*identity*`, `test_*laura*` and `test_*canonical*` suite, plus
  `test_codex_v1_blind_comparison`, `test_codex_v1_variant_base`, `test_v2_gallery_consistency`,
  `test_v6_gallery_e2e`, `test_w3_k12_model_photography`, `test_w3_visual_rnd_guard`,
  `test_w4_ownerimg` and `test_w4_visnext`.
  - `test_eng_vis_identity`: 50/50.
  - `test_v3_identity_qualification`: 24/24.
  - Both pass with and without `BRAMBLELOOP_FACE_MODEL_DIR` pointing at the installed models.
- **Named suites:** `test_model_spend_paths`, `test_cost_governance_wave2`, `test_w4_resume_runner`,
  `test_v11_autonomy_timeline` and `test_vacuity`.
  - The autonomy map was regenerated with `python -m brambleloop.autonomy.map --write …`. Only
    `generated_at` changed.
- **Deploy and build suites (17):** `test_deploy`, `test_deploy_guard`, `test_deploy_path`,
  `test_deploy_verify`, `test_dependency_lock`, `test_w3_supply_chain`, `test_w4_prodready_deps`,
  `test_w3_hq_independence`, `test_rc1_own_release`, `test_texture`, `test_w3_deploy_evidence`,
  `test_w4_fm2_lock_boot_guard`, `test_w4_relfix_release_log`, `test_w4_integ4_shipped_records`,
  `test_w4_packetrel`, `test_cert_claude_independence` and `test_w3_suite_job_identity`.
- **Core:** `test_compiler`, `test_reverse` and `test_twin`.

Two suites failed on the first run, and both failures came from this slice:

- `test_cert_claude_independence` keeps a COPY allowlist. The two new early COPYs (the fetch
  script and `face_embedder.py`) were admitted by exact path, with the reason recorded. The
  suite now passes 4/4.
- `test_w4_resume_runner` F7 requires timing-sensitive suites to be declared.
  `tests/test_eng_vis_identity.py` uses `timeout=`, so it was appended to
  `scripts/suite_final_segment.txt`. The suite now passes.

## Known limits

- The held-out split on 22 samples is tiny. Its numbers say "not enough evidence", not "SFace
  fails". The 450-face impostor run and the owner's 24 labels decide that.
- The image build was verified locally with Docker, not on Railway. Railway's builder must reach
  huggingface.co. If it cannot, the build still succeeds and identity HOLDs.
