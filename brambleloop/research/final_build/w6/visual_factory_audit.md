# ENG-VISUAL — listing-image and PDF factory audit (W6)

- Branch: `eng/visual-factory`
- Base: `origin/claude/w6-INTEG2 @ a35ad302`
- Audited: 2026-11-19 (UTC)
- Paths are relative to `brambleloop/src/brambleloop/` unless they start with `tests/` or `ops/`.

## Honesty statement

This is a **code audit**. It made no production call.

- The production numbers the owner asked for are **UNKNOWN on this branch**. They become readable only after Main deploys this branch and reads `visual_pipeline` on `/api/readback/evidence`.
- No number in this document is a production count.
- No Laura asset was touched.
- No identity verification was fabricated.
- No gate was weakened.

## The chain, stage by stage

### 1. Certified pattern → premium US/UK PDFs and hashes — **WORKS**

**Certification**
- `runtime/pipeline.py:1301 handle_certify` issues the certificate.
- On a grant:
  - writes `gate.certified` (`:1382`);
  - `_persist_release` (`:1818`) writes `pattern_versions(certified=True, release_hash, certificate)` (`core/models.py:313-329`).

**From certification to the PDF build**
- `gate.certify` enqueues `listing.draft` (`pipeline.py:1486`).
- `listing.draft` enqueues `assets.build` (`pipeline.py:1944`).
- `assets.build` runs `runtime/release.py:10430 handle_assets_build_with_successor`, which wraps `release.py:319 handle_assets_build`.
- `_load_cir` (`release.py:111`) refuses an uncertified pattern.

**The PDFs**
- `publish/pdf.py:480` sets `TERMINOLOGIES = ("US","UK")`.
- `build_pattern_pdf` (`pdf.py:975`) runs once per terminology (`release.py:350-352`).
- UK terms come from `cir/stitches.py:75`; a missing term raises.

**Where the hashes are kept**
- `durable_artifacts` (`release.py:368-371`).
- `artefact_provenance`, class `pdf` (`release.py:407-413`).
- Audit row `assets.built` with `pdfs:{US,UK}` (`:422-431`).
- Job outputs `pdf_sha256_by_terminology` (`:621-626`).

**Reading them back**
- The canonical reader is `runtime/pipeline.py:1959 _certified_pdf_hashes(slug, version, release)`. It binds to the exact release.
- `pipeline.py:1992 check_pdf_hashes` refuses an upload whose re-render drifted (`PDF_HASH_DRIFT`).

**Gates and caveats**
- Gates: an open P0/P1 incident; an owner veto or teardown; `ChildrensDecisionRequired` (`pdf.py:740-800`).
- Caveat: an image block (`release.py:489-611`) stores the PDFs but returns `ok: False`, so pricing is not enqueued.

**Evidence:** `visual_pipeline.certified_pdfs`, which counts certified releases with US+UK hashes, US-only, UK-only, and none.

### 2. FLUX generation — **BLOCKED (owner activation)**

**Model**
- `creative/image_stages.py:54` sets `MODEL = "flux-3-image"`.
- The provider row is `gateway/images.py:113-118`:
  - endpoint `https://api.bfl.ai/v1/flux-3-image`;
  - `dialect="bfl3"`, `account="bfl"`;
  - at most 10 references.
- No API `version` field is sent. `BFL3_FIELDS` allows one (`images.py:462`), but nothing sets it. The model is pinned by endpoint name only.
- The prompt builder is `creative/flux_prompt.py:25` (`flux3-prompt-builder/2.1.1`).

**Sizes and price**
- Product and lifestyle frames are 2048² (`image_stages.py:66-67`).
- The identity anchor is 1024² (`:685`).
- Price comes from `BFL3_TIER_USD` (`images.py:458`): about CA$0.14 per 2k call (`flux3_generator.py:239-240`).

**The call**
- `images._request_for` (`:584`) builds the request, authenticated with the `x-key` header.
- `_generate_reserved` (`:1341`) sends it and polls up to 150 × 2 s (`:873-884`).
- Path: `flux3_renderer` (`image_stages.py:151`) → `images.generate` (`:1150`).
- The generator is `creative/flux3_generator.py:200 Flux3Generator` (`paid=True`), registered lazily (`:516-522`).

**Budget — four layers, all enforced in code:**
1. Per gallery: `MAX_GENERATION_CALLS = 12` and `MAX_SPEND_CAD_PER_GALLERY = 2.00` (`visual/image_production.py:103-106`), enforced by `spend_plan.guard` (`visual/spend_plan.py:85`). Write-ahead pending markers: `_begin_generation` `:530`, settle `:559`, complete `:592`.
2. Capability gate `image_generation` (`image_production.py:728-732`) → `gateway.images.usable` (`:1788`). It needs an owner activation in `paid_provider_activations` and a probe.
3. Company monthly ceiling: `images.reserve_render` (`:913`) → `anthropic.check_budget_cad` (`gateway/anthropic.py:383`) → `spend_reservations`.
4. Owner paid-provider gate: `gateway/paid_provider_gate.py:873 enforce`. It walks RESERVED→BILLED/RELEASED/UNCERTAIN against daily, monthly and per-gallery ceilings.

**How production reaches it**
- `assets.build` → `image_production.trigger` (`release.py:646-656`, only with a release and a usable disclosed render set).
- → `visual.image_production` (`release.py:4004`).
- → `run_stage` (`image_production.py:877`).

**Blocker:** `CapabilityBlocked("image_generation gate closed …")` at `image_production.py:731`, with reason `not_activated_by_owner` (`paid_provider_gate.py:961`).

**Secret needed:** `BRAMBLELOOP_IMAGE_KEY_BFL` (`images.py:220-227`). The key alone authorises nothing.

### 3. Laura identity — **BLOCKED: no production-qualified verification exists**

**The identity**
- `visual/canonical.py:62` sets `IDENTITY_ID = "laura-r2-a42aeac7"` (D-FB-14).

**The three canonical references** (`canonical.py:63-67`, files under `visual/assets/canonical/laura-r2-a42aeac7/reference_pack/`):

| frame | sha256 |
|---|---|
| `neutral_portrait` | `a42aeac72ba5733e42f55f9eb527218242c50610531ec9263ffb6f3e82519bc9` |
| `torso_fit_reference` | `afe6191fb4c68d0a9c61229fe822a1032ee7c54150597210888db25b0f9ef0db` |
| `full_length_standing` | `f32bac686cba46c75e3ac193e72f2bcea4ba7ebc80355a102a4bed4bca3931e0` |

- They are loaded with sha256 checks in `vision_judges.canonical_reference_bytes` (`:173`) and `image_production.laura_refs` (`:1157-1175`). Fewer than three raises `ConditioningRefused`.

**How verification is meant to run** — `visual/identity_gate.py:414 assess` needs all three of:
- (a) a conditioning receipt proving the current reference bytes were sent (`trial_validity` `:104`);
- (b) two independent vision judges, each reading every locked face dimension as `match` (`canonical.laura_verdict` `:514`);
- (c) a biometric floor: face-embedding cosine similarity (`biometric_floor` `:170`, `measure_biometric` `:370`).

The judges are `vision_judges.Adapters` (`:804`), reached through `candidate_gates.RealJudges` (`:201`).

**Why production has no qualified check** (all five hold today):
1. `identity_gate.QUALIFIED_EMBEDDERS = {}` (`:57`). No face-embedding model is in the build.
2. `identity_gate.PRODUCTION_QUALIFICATIONS = ()` (`:237`). `validate_qualification` refuses: "not on the owner-funded production register … OWNER ACTION" (`:340-344`).
3. Production `Adapters` gets `embedder=None` (`vision_judges.py:813-816`), so the biometric floor is UNMEASURED (`identity_gate.py:383-385`).
4. `vision_judges.SECOND_VISION_TRANSPORT = None` (`:933`). With one judge, identity can only refuse, never pass (`identity_gate.py:148-150`, `missing_judge_pair`).
5. The `image_vision` gate is not owner-activated, so the judges answer "unfunded" (`visual/fidelity.py:1066`).

**Result**
- The best reachable band is REVIEW/UNKNOWN (`identity_gate.py:463-468`).
- `canonical.PUBLICATION_APPROVED = frozenset()` (`:152`).
- A fixture qualification exists for shadow tests only. It is labelled `FIXTURE ONLY` (`:228`) and is **never** counted as verification. `visual_pipeline` counts it under `fixture_only` and `not_run`.

**Evidence:**
- `visual_pipeline.laura_identity_checks`: `laura_frames`, `run`, `passed`, `failed`, `not_run`, `unknown`, `fixture_only`, `biometric_measured`.
- `visual_pipeline.laura_identity_method`:
  - `canonical_references_verified` of `_expected` (3);
  - `second_vision_transport_configured`;
  - `production_embedder_qualifications`;
  - `production_qualified`, which is true only when all of them hold.

### 4. Outfits: unique per listing, consistent in a gallery — **WORKS (registry) / BLOCKED (visual check)**

**The registry** (`visual/outfits.py`)
- `register:101`, `approve:167`.
- `reserve:204` returns FAIL for:
  - an outfit bound to another listing;
  - a second outfit for the same listing;
  - an identical garment signature (`WARDROBE_REPETITION`).
- `check_use:257`, `release:276`, `replace:293`.
- `distinctness:368` uses `visual/wardrobe.py:132/139` (`MAX_SIMILARITY`).
- Table: `laura_outfits`.

**Selection and checks**
- Selection: `visual/styling.py:151 select_for_listing`, run at stage `reserve_outfit` (`image_production.py:1110-1155`). On repair, `_repick_outfit:1861`.
- Per frame: `candidate_gates.evaluate:466` (`:510-523`).
- Per gallery: `candidate_gates.campaign_consistency:716` returns FAIL when more than one outfit appears, and UNKNOWN for frame pairs nobody judged (`:733-740`).

**Blocker:** the visual outfit-consistency reading goes through the vision adapters. With `image_vision` closed it is UNKNOWN, and UNKNOWN is never PASS (`technical_of:552` takes the worst).

### 5. Product-specific references — **WORKS (deterministic), gated behind generation**

- `creative/pattern_refs.py:674 build` renders `ROLES` (`:44`: layout, texture, detail, rules) from the certified CIR.
- Verification: `verify:741`. Release binding: `release_hash_of:78`.
- Path: `image_stages.py:211 release_from_cir` → `flux3_generator._prepare:286`, then `_bind:292`, which refuses bytes from another release.
- Persisted at `image_production_runs.stages.prepare_references` (`image_production.py:1002-1012`).
- Runs only once a generator runs (blocker of stage 2).

### 6. The 7-image campaign standard — **MISSING as an enforced constant**

- `visual/shot_plans.py:183-205` records the ruling: "a typical set of seven".
- But `campaign_plan:213` returns `image_count = len(slots)`, which varies by category (`plan_for_category:121`).
- Only three roles are generated (`CAMPAIGN_GENERATED`: LIFESTYLE, SCALE, COLOUR_CONTEXT). The others reuse the disclosed render.
- The hero stays the disclosed render (F-852; `ruling_conflicts:233`).
- A literal `image_count: 7` exists only in the experiment plan (`visual/experiment.py:271-326`), and experiments never publish.
- `publish/listing_assets.py:626 build_frames` produces the deterministic frame plan.

**Blocker (S1):** no code refused a gallery below 7.

**Fixed in S2:**
- `visual/shot_plans.py` adds `CAMPAIGN_MIN_FRAMES = 7` and `campaign_standard(plan)`, which needs at least 7 frames and one job per frame. It never pads a short gallery.
- `image_production.readiness` reports `campaign_standard`. A shortfall is a set-check problem, and `gallery_ready` requires the standard.
- The owner card carries the reading.
- All 8 Launch-0 plans meet it (7–9 frames). Test: `tests/test_visual_campaign_standard.py`.

### 7. Automatic verification, motif fidelity, repairs — **WIRED, BLOCKED**

**Verification**
- `candidate_gates.evaluate:466` → `technical_of:552` takes the worst check.
- Product truth: `RealJudges.product_truth:248`, using `visual.fidelity` because `product_authority.structural_floor:153` is UNKNOWN for generated frames (`:192`).
- `final_image_gate.py:86` and `d_judge.py` are **not** on the production gallery path.

**Motif fidelity**
- `publish/motif_fidelity.py:346 check` returns MATCH / MISMATCH / UNMEASURABLE, and UNMEASURABLE blocks (`:394-398`).
- It is used only by `publish/owned_photography.py` and `publish/model_photography.py`, not by `image_production`.
- The motif work belongs to `eng/motif-reservation` and `eng/motif-backlog`. `eng/motif-reservation` (aa8b2b93) was merged into this branch in S2. `eng/motif-backlog` is not on origin yet.

**Repair**
- Stage `repair` (`image_production.py:1285-1308`) → `_repair_for:1880` → `visual/repair_routes.py:103 route`.
- Limits: at most 2 rounds and 3 attempts per role.
- A structural failure with no route blocks at `:1263`.
- `visual/portrait_repair.py` is a separate job, not part of the gallery chain.

**Recovered images:** no producer exists on this build. `visual_pipeline.recovered_images.count` reads `"UNKNOWN"` with `not_measured_because`. It picks up `visual.motif_backlog.recovered_count(db)` when that branch lands.

### 8. Gallery certification — **BLOCKED (structural)**

**The path**
- Owner approval: `app/command_center/api.py:437` (step-up) → `image_production.approve:2155` → `visual/gallery_persist.py:38 persist_approved`.
- `persist_approved` calls `write_frames:94`, which writes `listing_assets` and the audit row `images.listing_asset_written`.
- Then `recertify:174` → `publish/release_gates.py:531 listing_set` writes `listing_set_certificates`.

**Blocker:** while the disclosed render set is current, `listing_set` certifies that set only (`release_gates.py:550-557`). Generated frames are "not part of any certificate", so `recertify` returns `blocks_release=True`. Generated Laura frames cannot enter a certified gallery today, even before the identity blocker.

### 9. Listing package — **WORKS, BLOCKED in practice**

- `publish/listing_package.py:185 assemble` → `record:343`, stored in `operating_readings(kind='listing.package')` plus `OwnerAction listing_package:<key>`.
- States: `ready_for_owner_review` and `blocked`.
- The package reads PDFs through `_files:112` → `_certified_pdf_hashes` (release-bound).
- Its gallery is `etsy_ops.certified_frames` (the certificate only).
- Job `listing.package` (`runtime/listing_package_ops.py:65`) runs on a 6-hour cadence (`runtime/worker.py:733`).
- The blocker set is pinned by `tests/test_w6_listing_chain_e2e.py:310-320` (listing-set certificate #70, F-004, `SAMPLE_PHOTO_REQUIRED`, and others).

**Evidence:** `visual_pipeline.listing_packages`, which reports `listing_ready`, `blocked` and `blocker_sources`.

### 10. Etsy draft with read-back of both PDFs and every image — **WORKS against FakeEtsy; BLOCKED by phase and grant**

**Client** (`integrations/etsy.py`)
- `create_draft:1289`.
- `upload_image:1313` (`uploadListingImage`).
- `attach_file:1373` (`uploadListingFile`).
- `get_listing_files:1124`, `get_listing_images:1097`.
- `publish:1644` attaches the US PDF.

**Production path**
- `runtime/pipeline.py:2023 handle_store_publish` attaches the UK PDF (`:2573-2590`).
- `runtime/etsy_ops.py:800 read_back` reads back the fields, the files (`verify_files`) and the images, rank by rank with alt text (`images_read_back:772`).
- Persisted as `listings.etsy_listing_id` and audit rows `store.published` / `store.publish_incomplete`, with `read_back`, `files_attached_by_terminology` and `pdf_sha256_by_terminology`.

**Blockers**
- SHADOW phase gives `ShadowModeRefusal`.
- An `OwnerGrant` and real OAuth credentials are required.

**Test double:** `tests/fake_etsy.py:63 FakeEtsy`.

**Evidence:** `visual_pipeline.etsy_drafts`, which reports `drafts` and `fully_read_back` (fields + files verified, US and UK both attached, images verified).

## Status summary

| # | Stage | Status | Blocker |
|---|---|---|---|
| 1 | Certified → US/UK PDFs + hashes | works | — |
| 2 | FLUX-3 generation | blocked | `image_generation` not owner-activated; BFL key |
| 3 | Laura identity verification | blocked | no qualified embedder; no second vision transport; `image_vision` closed |
| 4 | Outfit uniqueness / consistency | works (registry) / blocked (visual) | `image_vision` closed → UNKNOWN |
| 5 | Product-specific references | works | runs only behind 2 |
| 6 | 7-image standard | works (S2) | enforced at gallery readiness; ≥7 frames, one job each |
| 7 | Verify / repair | wired, blocked | identity UNKNOWN; motif fidelity not on the generated path (motif branches) |
| 8 | Gallery certification | blocked | generated frames are never in a listing-set certificate while the disclosed set is current |
| 9 | Listing package | works, BLOCKED in practice | listing-set certificate, F-004, `SAMPLE_PHOTO_REQUIRED` |
| 10 | Etsy draft + read-back | works on the fake | SHADOW phase, owner grant, OAuth |

## Production numbers (owner's list)

None of these exist yet. All are **UNKNOWN until the next deploy**. Main reads `GET /api/readback/evidence` → `visual_pipeline`, and the advisory readback row is "listing-image and PDF factory (visual pipeline)":

| Asked for | Field |
|---|---|
| products with certified PDFs | `certified_pdfs.with_us_and_uk_pdf_hashes` / `certified_releases` |
| valid galleries | `galleries.valid` |
| blocked galleries | `galleries.blocked` and `galleries.blocked_reasons_grouped` (`stage:family[:exhausted]`, fixed vocabulary) |
| images generated / verified / failed / unmeasurable | `images.candidates` / `verified` / `failed` / `unmeasurable` |
| Laura identity checks | `laura_identity_checks.run` / `passed` / `failed` / `not_run` |
| recovered images | `recovered_images.count` (UNKNOWN until motif-backlog lands) |
| listing-ready packages | `listing_packages.listing_ready` |
| real Etsy drafts | `etsy_drafts.drafts`; fully read back: `etsy_drafts.fully_read_back` |

From the code alone, two things can be stated:
- **identity checks passed in production = 0 possible**, because `production_qualified` is false by construction;
- **certified generated galleries = 0 possible**, because of the stage-8 blocker.

Both are structural facts, not row counts.

## Owner exceptions (OWNER ACTION REQUIRED)

1. **Approve an identity-verification method and fund it.**
   - Action: choose a face-embedding model, fund it, and approve its calibration record into `identity_gate.PRODUCTION_QUALIFICATIONS`. Choose and fund a second independent vision transport (`vision_judges.SECOND_VISION_TRANSPORT`).
   - Why: identity can never PASS without both, and a fabricated verification is forbidden.
   - Maximum cost: provider-dependent; this is a decision to make, and no spend has been made.
   - Owner time: about 30 minutes to decide.
   - Consequence of waiting: no Laura frame can pass identity, so no gallery containing Laura can certify.
2. **Activate `image_generation` (BFL FLUX-3) and `image_vision`.**
   - Action: Command Center → paid providers → activate, with step-up (`POST /api/cc/paid-providers/activate`), setting the daily, monthly and per-gallery ceilings. Set `BRAMBLELOOP_IMAGE_KEY_BFL` in Railway.
   - Maximum cost: the code caps every gallery at 12 calls and CA$2.00, plus the owner's own ceilings.
   - Owner time: about 10 minutes.
   - Consequence of waiting: no image is generated, and every vision check reads UNKNOWN.
3. **Publication grant and leaving SHADOW** for a real Etsy draft. This is already tracked by first-listing doors and is not new here.

## Fix plan (engineering, no gate weakened)

- **S1 (this slice):**
  - this audit;
  - the `visual_pipeline` evidence section (`ops/production_evidence.py`);
  - its readback row (`ops/readback.py`, advisory);
  - `tests/test_visual_pipeline_evidence.py`.
- **S2:**
  - enforce the 7-frame campaign standard as a gallery-certification check that refuses fewer frames and never pads them;
  - an end-to-end test on a certified fixture: certified pattern → PDFs → stub-FLUX images → identity and product QA (fixture judges, labelled) → gallery certification → listing package → FakeEtsy draft with read-back of both PDFs and every image.
- **S3:** a generated-gallery certificate route so that verified generated frames can join a listing-set certificate (stage 8). It requires every frame PASS, so UNKNOWN identity keeps blocking.
- **S4:** merge `eng/motif-reservation` and `eng/motif-backlog` when they appear, and wire `recovered_images`.

## S2 proof: end to end on a certified fixture (`tests/test_visual_factory_e2e.py`)

Real handlers throughout. The doubles are: the FLUX-3 StubRenderer (no network, no spend), labelled stub vision and identity judges (production has no qualified method), and `tests/fake_etsy.py` (loopback).

**A. Generated gallery** (cloudline-baby-blanket):
- `assets.build` triggers `visual.image_production`.
- The real `Flux3Generator` builds every request: lifestyle, size and colour_context, plus the product and identity anchors. Spend is CA$0.
- Identity is judged on every Laura frame, and product truth on every gallery frame. `visual_pipeline` counts exactly these rows.
- The campaign standard holds: 7 frames, one job each.
- The run stops at the owner card on named gates.
- Stage-8 blocker, pinned: `approve` refuses, no `listing_assets` row is written, no certificate is issued, and nothing reaches the package or Etsy.

**B. Certified gallery to Etsy:**
- Chain: `gate.certify` → `assets.build` (US+UK PDFs) → `listing.seo` → `listing.package` (recorded) → owner grant → `store.publish` on FakeEtsy → read-back.
- Both certified PDFs arrived byte for byte: their sha256 equals the `assets.built` hashes. Etsy lists both, and `files_attached_by_terminology` is `{US: True, UK: True}`.
- Every certified image arrived in rank order, byte for byte.
- The read-back verified the fields, the files and the images.
- `visual_pipeline.etsy_drafts.fully_read_back` is 1.

**What remains unproven:** a *generated* frame inside a certified listing on Etsy. That is blocked by stage 8 and by the owner gates (identity method, F-852 verified exception, Etsy policy, Laura publication). No test claims it.
