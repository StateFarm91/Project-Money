# Visual pipeline wiring audit: Laura, the home, the product and the gallery (read-only)

- **Tree audited:** `/home/user/bl-runs/wt-b5cert` @ `5ba84bf7` (the Batch 5 candidate). Nothing in the tree was modified, no git state was changed and no tests were run. Read-only `git cat-file`/`git diff` calls were used against `0967c3ee` (production).
- **Paths:** unless stated otherwise, paths are relative to `brambleloop/src/brambleloop/`.
- **Probes run:** three small Python probes ran from the scratchpad with `PYTHONDONTWRITEBYTECODE=1`. They were pure function calls (`pattern_refs.technical_rules`, `flux_prompt.build`, `candidate_gates.lifestyle_reading`, `candidate_gates.role`, `eligibility.verified_exception`, `shot_plans.campaign_plan`). None of them touched a database or the network.
- **Reused evidence:** the scheduler, queue, idempotency and restart mechanics are reused from `research/final_build/w5/P0_WIRING_50937469.md`, rows 15–16, 18 and 24. They were not re-derived here.
- **Production vs. candidate.** Production (`0967c3ee`) does **not** contain `visual/laura_home.py`. Production also builds the basket at `market-basket-small@1.2.0`, not 1.3.0. Everything about the home below is therefore Batch 5 candidate code only.
- **Production evidence is UNKNOWN throughout.** That covers whether the `image_generation` and `image_vision` gates are open, whether any `image_production_runs` row exists, and whether any certificate exists. Only the production DB can answer it.

## 1. Matrix

| # | Requirement | What exists | On the automatic path? | Main gap | Verdict |
|---|---|---|---|---|---|
| 1 | Laura's exact canonical identity, from the approved reference set only | Three canonical originals, hash-verified and sent first, in order, on every Laura generation. A missing reference is refused, never degraded. | **Conditioning: yes.** **Verification: no.** Identity can never PASS: no qualified embedder exists and production configures one judge. Every Laura frame is UNKNOWN and goes to an owner review hold. | No automatic identity PASS is possible. Stage A/D reuse generated images as extra identity context. Laura is absent from the basket, coaster and ornament galleries. | **PARTIAL** |
| 2 | One consistent Canadian family home across images and listings | `laura-home-v1` is a text room per category, with a deterministic per-frame variation hash. | Text only, injected into the FLUX prompt. There is no home or scene reference image. There is no seed: the FLUX 3 API rejects `seed`. No check of any kind is made on the output. | No reference image, no scene lock and no verifier. The decision is absent from DECISION_LOG. | **PARTIAL** |
| 3 | Premium natural lifestyle photography, not a showroom | Prompt REALISM section; `laura_home.FORBIDDEN` vocabulary (deterministic, text); realism vision judge (defect list); `naturalism.sameness_only` (dHash). | Yes, as candidate checks. | Nothing judges "lived-in vs showroom" or premium quality on the pixels. Realism is defect-only. | **PARTIAL** |
| 4 | The product identical across the gallery | Four certified CIR-derived reference images plus CIR text in every prompt, and the flat-lay anchor as a supplementary reference. The deterministic anchor verifier covers flat items. Lifestyle frames get a palette check plus a vision consistency check. | Yes. | Lifestyle geometry is never checked (stated blind spot). Gallery consistency compares metadata only. No cross-image pixel comparison exists. | **PARTIAL** |
| 5 | Realistic scale between product, Laura, furniture and objects | Product cm in prompt text. The deterministic disclosed scale frame (separate path). | No scale check on any generated image. | No measurement exists. Generated SCALE frames are structurally unpublishable (F-853). | **MISSING** (generated) |
| 6 | Reject imagery showing construction the pattern cannot produce | CIR-derived negatives (knitting, edging, rim, bands, cables, colour-change rows). Fidelity codes INVENTED_EDGING, END_BAND, PIECE_COUNT, REPEAT_COUNT, COLOUR_LAYOUT. Vision checks for craft and blind anchor consistency. | Yes. | Round and vessel pieces get aspect plus radial profile only: no side count, no stripe count, no rim type. The verifier is not calibrated on any vessel. Basket 1.3.0 mis-declares ribbing, which disables the ribbing check. | **PARTIAL** |
| 7 | Generated imagery distinct from attested physical-sample photography | `provenance_kind ai_generated_*`, `asset_class AI_LIFESTYLE_CONCEPT`, `is_photograph: False`, honesty label. Physical photos enter only through `physical_upgrade.intake`. `sample_photo` requires a photo-led certified set. | Yes, in records and certificates. | P0-PHOTO-ASSET-REVIEW is open (a photo-led set cannot certify). The prompt calls the generated flat lay an "approved product photograph". | **CONNECTED** (records), with defects |
| 8 | Visual production → identity review → Product Truth → gallery → listing package chained automatically | `visual.image_production` is registered and durable. `listing.package` runs on a 6-hour cadence. | Production through the owner card is automatic. The identity review, the publication approval and the ListingAsset write are owner-only. `listing.package` never receives generated frames. | Human-gated by construction (identity cannot PASS), and generated frames never become ListingAssets. | **PARTIAL** |
| 9 | Bounded correction loop when authorised; never a silent pass; never blocks unrelated products | Per-role attempt cap 3, 2 repair rounds, 12 calls and CA$2 per gallery. A named `blocked` hold per run key. Notification. | Repair is automatic within a run. A blocked run is never re-driven automatically; restart is owner-only, maximum 3. | Repairs are bought for a structurally unfixable LIFESTYLE FAIL. UNKNOWN is never repaired. There is no automatic re-drive. "Authorised" means only that a successful probe opened the gate. | **PARTIAL** |
| 10 | FLUX 3 prompt architecture, references, review jobs and gallery certificates work unattended | Pinned, hashed prompt sections; byte-verified references; durable stages; review adapters; `gallery_persist` plus listing-set recertify. | Prompt and references: yes. Reviews: run, but identity cannot pass. Certificate: generated frames are never judged or certified while the disclosed set is in use. | Generated frames are unpublishable by construction: F-852/F-853, Etsy policy UNKNOWN as a constant, LIFESTYLE `lifestyle_evidence` always FAIL, and Etsy's sample-photo rule. | **PARTIAL** |

**Counts:** CONNECTED 1, PARTIAL 8, MISSING 1. Nothing is a full PASS end to end.

---

## 2. Evidence by point

### How the automatic path starts (shared by every point)

**Trigger.**

- `assets.build` → `image_production.trigger`, once per `slug@version@release`, when the disclosed set is usable (`runtime/release.py:620-635`).
- The handler is `visual.image_production` (`runtime/release.py:3610-3627`).

**Registration.**

- `swarm/orchestrate.py:781` (band `proven_winner`).
- `authority/classes.py:110` (`_B`).

**Durability and idempotency.** Each stage self-enqueues with the key `imgprod:<slug>@<ver>@<release>:<stage>[:round][:e<epoch>]` (`visual/image_production.py:169-180`, `:254-266`). The run row is `image_records.ImageProductionRun`.

**Stages.** The stage list is at `visual/image_production.py:80-96`:

`retrieve_release → prepare_references → product_generation → fidelity_gate → load_laura_references → reserve_outfit → identity_anchor → lifestyle_generation → remaining_roles → verification → repair → gallery_assembly → owner_card`.

**Scope.** Only Launch-0 listings have a shot plan. For any other listing, `plan = SP.campaign_plan(...) if _is_launch(...) else None` (`:690`) leads to `block("… has no shot plan (not a Launch-0 listing)")` (`:728`). Every non-Launch-0 product stops here.

**Generator.** `resolve_generator` registers `creative/flux3_generator.Flux3Generator` (`image_production.py:138-162`, `flux3_generator.py:357-363`). `paid=True`, and its renderer is `image_stages.flux3_renderer` → `gateway.images.generate` on `flux-3-image`.

**What each Launch-0 listing generates.** Probe of `shot_plans.campaign_plan` on this tree:

| Listing | Category | Generated roles | Laura? |
|---|---|---|---|
| hexagonal-bread-basket | basket | lifestyle, size, colour_context | **no** |
| cloudline-baby-blanket | baby | lifestyle, size, colour_context | yes |
| winter-village-graphghan | blanket | lifestyle, size, colour_context | yes |
| hexagon-coaster-set | coaster | lifestyle, size, colour_context | no |
| nordic-star-ornaments | ornament | angle | no |

- Laura only appears for categories whose `LIFESTYLE_BRIEF` sets `True` (`visual/shot_plans.py:85-92`). `"basket": (False, ...)` is at `:88`.
- The basket's `size` brief is "Laura using it from another angle, which also shows its size" (`shot_plans.py:192-196`). It is nonetheless sent as a product-only edit whose prompt says "The product alone; no person." (`flux_prompt.py:271-275`). This is a contradictory instruction.

### FLUX 3 prompt assembly

**Builder.** `creative/flux_prompt.py:175-292` builds the prompt from eight pinned, content-hashed sections (`:29-103`): REFERENCES, IDENTITY v2, REFERENCE_CLOTHING, PRODUCT v2, NEGATIVES, SCENE, REALISM and DISCLOSURE. The receipt carries each section's ref and sha, plus the final text sha (`:131-135`).

**Where the CIR data comes from.** `pattern_refs.technical_rules` (`creative/pattern_refs.py:252-317`) and `fabric_facts`/`negatives` (`:148-249`).

**What the prompt actually carries for `market-basket-small@1.3.0`** (probe output):

| Item | Present? | How |
|---|---|---|
| Shape (hexagonal) | Yes, as text only | Via `finished_size_note`: "A hexagonal basket: the increases stack at six corners … 16.0 cm across the points and 13.9 cm across the flats … walls about 9 cm tall". The structured `shape` field is `"vessel"`, and `_pieces` does not print it in the prompt (`flux_prompt.py:145-149`); it appears only on the rules sheet image (`pattern_refs.py:466-467`). |
| Dimensions | Yes | "basket x1 (in rounds, 16.0 x 8.7 cm)", plus the note. |
| Gauge | Yes | "12.5 sts x 13.8 rows per 10 cm in sc". |
| Colours | Yes | "cream #FAF6EB, wine #6E1F2A", exact and only these. |
| Stitch type | Yes | "inc, sc". |
| Stripe sequence and counts | **Only indirectly** | The negative reads "colour changes anywhere except rounds 15, 17, 18, 20" (colour-change rows, `pattern_refs.py:242-249`). The CIR's actual stripes are wine rounds 15–16 and 18–19 (two 2-round stripes, one cream round between). No sentence says "two wine stripes, two rounds each". Stripe layout otherwise rides on the layout reference image. |
| Rim / edge finish | Yes, as a negative | "a vessel's top rim is that plain final round: no braided, rolled, twisted, scalloped, picot or crab-stitch rim" (`pattern_refs.py:217-225`). **This text is absent in production `0967c3ee`.** |
| Construction | Partly | `joined_rounds` and pieces are stated. **Defect:** `ribbing_declared` is `True` for 1.3.0 because one back-loop round (rnd 11, the base crease) makes `loops - {"both"}` non-empty (`pattern_refs.py:163`). As a result: <br>• the "ribbing anywhere (the pattern has none)" negative is dropped (`:213-214`); <br>• `fidelity.compare_craft` skips its ribbing check (`visual/fidelity.py:951-955`). <br>Basket 1.2.0 in production does not have this. |

**References sent with each request** (`creative/image_stages.py:315-375`; order is enforced):

- **Laura frames:** the three canonical originals first (face a42aeac7, torso afe6191f, full length f32bac68), byte-validated against `canonical.CURRENT_REFERENCE_HASHES` (`image_stages.py:243-275`). The order is checked again immediately before the request (`:422-426`). Reduced conditioning is refused (`image_production.py:891-909`).
- **Product references (4–7), from the exact certified release:** layout, texture, detail chart and rules. They are re-rendered and must hash-match on every call (`flux3_generator.py:157-169`). They are bound to the release hash (`pattern_refs.py:520-547`).
- **Supplementary references:**
  - the product-only anchor (`product_candidate`), labelled in the prompt "approved product photograph of this exact product" (`flux_prompt.py:217`) although it is an AI flat lay;
  - the outfit's `approved_reference` (clothing only; refused if it is a canonical or forbidden hash, `image_stages.py:357-371`);
  - the stage-A identity anchor (`identity_anchor`), which comes after the canonical three;
  - a stage-D edit base (an accepted lifestyle frame) (`image_production.py:919-941`).
- **Conditioning package:** `visual/assets/conditioning/laura-r2-a42aeac7/flux-3-image.json` declares the three frames, with `provider_reference_limit` 10. The stage resolves the registry and verifies views (`image_production.py:820-842`, `visual/canonical_registry.py:42-67`).

**Scene and home reference image: none.** `laura-home-v1` is text only:

- Laura frames: `laura_home.scene_for(slug, role)` → `environment` text (`flux3_generator.py:234-239`).
- Product-only frames: a room `cue` prefixed to the ≤400-character edit (`:259-270`).
- No image of the house exists in the repository, and no home image is ever sent to FLUX.

**Seed and scene lock: none.**

- The FLUX 3 API refuses unknown fields, so no `seed` is sent (`gateway/images.py:104-112`). The provider's seed is only recorded if returned (`image_stages.py:454`).
- Cross-image consistency rests on:
  - the deterministic text hash `laura_home.variation` (`visual/laura_home.py:246-266`), which keeps the same frame's scene stable across repairs;
  - stage D (editing the accepted lifestyle frame), which never triggers in practice; see point 9.

### Point 1: identity

**Conditioning: CONNECTED.** Evidence is listed above. In addition, `canonical_registry.resolve` failures block before any Laura frame (`image_production.py:830-839`).

**Judging.** Stage A runs `identity_anchor_verdict` (`image_production.py:573-600`); every other frame runs `candidate_gates.evaluate` → `RealJudges.identity` → `vision_judges.Adapters.identity` → `identity_check` → `identity_gate.assess`. These are in `visual/candidate_gates.py:391-470`, `visual/vision_judges.py:184-251` and `:666-723`, and `visual/identity_gate.py:190-238`.

- **Method:** blind, closed-vocabulary vision readings of the candidate against the three canonical references, compared in code. A PASS needs all of the following:
  - a valid conditioning receipt;
  - **two different judges**;
  - a **biometric embedding floor**.
- **What production has:** `QUALIFIED_EMBEDDERS = {}` (`identity_gate.py:47`), and `RealJudges(db)` is built with `second_vision=None` at every production call site (`image_production.py:680`, `gallery_persist.py:58`, `candidate_gates.py:398`). DECISION_LOG D-W4-VISNEXT-JUDGES confirms that "Production configures one judge today", so identity tops out at REVIEW (UNKNOWN).
- **Fail-closed:** yes. Any judged drift is a FAIL. Everything else is UNKNOWN and blocks.

**Consequence for a Laura listing.** Stage A always ends in one of two ways:

- FAIL, then blocked; or
- UNKNOWN, then `identity_gate.open_review`, then a block held for owner review (`image_production.py:1385-1402`).

The run resumes only after the owner resolves it in the Command Center and restarts the run (`resolve_identity_anchor_review`, `:1420-1440`; `app/command_center/api.py:513`). The owner's confirmation does not make the verdict PASS, so the lifestyle frames will again read identity UNKNOWN.

**Re-derivation risk.** Two generated images are fed back as identity context after the canonical three:

- the stage-A identity anchor (a generated Laura-alone image);
- the stage-D edit base, an accepted *lifestyle* frame, edited for the non-LIFESTYLE roles (`image_production.py:930-941`; `flux3_generator.py:240-250`).

The canonical three still lead every request, but stage D edits a generated lifestyle image. That conflicts with "never re-derived from a lifestyle image". Today it is dormant, because `_accepted_lifestyle` (`:1304-1314`) requires a non-FAIL LIFESTYLE frame, and LIFESTYLE always FAILs (see point 10).

**Drift monitor.** `visual.identity_drift` runs daily from the cadence at `runtime/worker.py:808` (handler `release.py:3691`). It reads recorded verdicts and is UNMEASURED with fewer than 3 batches.

### Point 2: home

**What exists:** `visual/laura_home.py`.

- `HOME_ID = "laura-home-v1"` (`:42`).
- A shared `HOUSE` description (`:68-70`) and six rooms (`:72-160`).
- `ROOM_FOR_CATEGORY` (`:164-174`): basket → kitchen.
- A deterministic `variation` of angle, light, two clutter items and a moment (`:246-266`).
- `FORBIDDEN` showroom vocabulary (`:179-183`) and `DECOY_FOR_CATEGORY` (`:199-210`).

**Wiring.** `flux3_generator.py:229-270` is the only consumer that affects images.

**What is missing:**

- A home or room reference image, which would be the only practical geometry lock for FLUX.
- Any check of room geometry, furniture, materials or recurring details on the output, by vision or deterministically.
- A seed or scene lock.
- A DECISION_LOG entry for D-W4-OWNER-LAURA-HOME. It is cited only in the module docstring (`laura_home.py:22`).
- Production deployment: the module is absent in `0967c3ee`.

### Point 3: naturalism

**What exists:**

- The REALISM prompt section (`flux_prompt.py:90-96`).
- `laura_home.check` on the environment and brief (deterministic, text).
- `vision_judges.compare_realism`, a list of defects (render/illustration, text, artefacts) through `image_vision` (`vision_judges.py:483-522`). It is UNKNOWN when unanswered.
- `naturalism.sameness_only`: a dHash copy-paste check, which is deterministic and becomes a publication blocker (`image_production.py:1561-1563`).
- `visual.photoreal` (skin and processing) through realism.

**What is missing:** no pixel check rewards "lived-in" or penalises "showroom" or "staged". Realism is a defect list, not an art-direction judgement.

### Points 4 and 6: product fidelity and construction

**Anchor (product-only flat lay).** `fidelity.verify_anchor` (`visual/fidelity.py:1068-1121`) runs deterministic checks for:

- isolation;
- piece count;
- flat/fill;
- aspect;
- palette;
- colour layout;
- end bands;
- edges;
- repeat count.

It also runs a vision craft-texture check (`fidelity.py:1036-1048`).

**Round and vessel pieces** go to `_verify_round` (`:870-917`): solidity, aspect at ±15 %, palette, and a radial colour profile (outer-bin mismatch → INVENTED_EDGING).

- **No side count.** A hexagon's points-to-flats ratio (1.155) sits inside the ±15 % aspect tolerance of a circle.
- **No stripe or round count on walls.**
- **No rim-type check** beyond the radial outer bins and the vision `border_or_edging_visible` answer.
- The calibration set is Cloudline, the wrap and the coasters (`research/final_build/w4/FIDELITY.md:126-136`). **There is no vessel**, and the flat-lay prompt asks for a basket "laid completely flat and unfolded" (`image_stages.py:533-539`). The basket anchor's outcome is UNKNOWN, and plausibly UNKNOWN (solidity) or a false FAIL.

**Lifestyle and other roles.** `fidelity.verify_lifestyle` (`:1124-1216`) checks:

- anchor PASS for the same release;
- the palette inside vision-located patches (`vision_judges.locate_product`, `:645`);
- blind anchor consistency (`vision_judges.blind_consistency`/`compare_items`, `:545-607`), which compares craft, edging, bands, cables and colour count;
- craft.

`BLIND_SPOTS` states "lifestyle images: only palette and consistency, never geometry" (`fidelity.py:131-144`).

**Gallery.** `CG.campaign_consistency` (`candidate_gates.py:610-625`) compares only `listing`, `version`, `release`, `cir_fingerprint` and `outfit_id` metadata. No pixel comparison runs across frames.

**Which checks are deterministic and which need vision**

- **Deterministic:**
  - binding;
  - quality (≥2000 px, PNG/JPEG, opaque);
  - role;
  - provenance;
  - disclosure;
  - the anchor geometry, palette and layout checks;
  - outfit registry uniqueness and distinctness;
  - dHash sameness;
  - the home text filter.
- **Vision (`image_vision`):**
  - identity and body proportions (two judges required to PASS);
  - outfit consistency;
  - anatomy;
  - realism;
  - craft texture;
  - anchor consistency;
  - product-region location.
- All checks are fail-closed: UNKNOWN never counts as PASS (`candidate_gates.worst`, `:69-71`). `UNVERIFIABLE_COUNT` is never passed (`:409-412`).

### Point 5: scale

- No generated-image check measures relative size against Laura, furniture or objects (searched `visual/`; only the disclosed renderer's `_scale_bar` and `render_verification._scale` exist, on the deterministic path).
- Generated SCALE (`size`) frames are refused publication by design under F-853. Verified with `eligibility.verified_exception` on this tree, which returns "F-853: certified pixels are feasible for SCALE … the exception does not apply" (`publish/eligibility.py:426-429`).

### Point 7: generated vs physical

**Generated images:**

- Every candidate is stored as "AI; never a photograph" (`image_production.py:532-535`), with `provenance_kind="ai_generated_autonomous"`.
- Owner uploads are `ai_generated_owner_submitted` (`publish/owner_images.py:34`, `:98`).
- ListingAsset writes use `asset_class AI_LIFESTYLE_CONCEPT`, `claims.is_photograph False` and the label "AI-generated concept image", plus `visual_truth` lineage (`visual/gallery_persist.py:135-166`).
- The honesty label is `eligibility.CONCEPT_LABEL` (`publish/eligibility.py:223`), shown in the listing package (`publish/listing_package.py:194`, `:231`).

**Physical photos:**

- They enter only through `physical_upgrade.intake` (`publish/physical_upgrade.py:63`).
- `publish/sample_photo.py:1-35` requires an unedited, attested photo, bound to a passed full physical make of this release, as frame 1 of the certified set.

**Gaps:**

- P0-PHOTO-ASSET-REVIEW is open (`research/final_build/w5/P0_GAP_REGISTER.md:20`).
- The prompt labels the AI anchor a "photograph" (`flux_prompt.py:217`). This is internal, but it conflates the two classes.

### Point 8: chain

- **Automatic to the owner card:** production → fidelity → identity anchor → lifestyle and roles → verification/repair → `gallery_assembly` → `owner_card` (`image_production.py:1028-1101`). The owner-card notification is in `:1598-1673`.
- **Identity review:** owner-resolved only (`api.py:513`).
- **Publication approval:** owner step-up, `approve` (`image_production.py:1675-1722`, `api.py:435`). It then calls `gallery_persist.persist_approved` → `write_frames` → `recertify`.
- **Visual approval:** recorded only; no gate reads it (`:1725-1752`).
- **Listing package:** `listing.package` runs on a 6-hour cadence (prior audit row 18). It reads certified frames only. Generated frames reach ListingAsset only after approval with zero blockers, which cannot happen (see point 10). So the package never includes generated imagery.

### Point 9: correction loop

**Caps** (`image_production.py:103-111`): `MAX_ATTEMPTS_PER_ROLE=3`, `MAX_REPAIR_ROUNDS=2`, `MAX_GENERATION_CALLS=12`, `MAX_SPEND_CAD_PER_GALLERY=2.00`, `MAX_RESTARTS=3`. They are enforced by:

- `spend_plan.guard` before every call (`:497-500`);
- the `image_generation` gate (`:492-495`);
- `gateway.images.reserve_render` against the monthly and agent ceilings (`gateway/images.py:904-920`).

**Repair.**

- `verification` enqueues `repair` when a role FAILs, its attempts are under the cap and `_repair_for` is not None (`:973-992`).
- Directives come from `repair_routes.ROUTES` (`visual/repair_routes.py:26-71`).
- An unrouted code → no repair. UNKNOWN → no repair.
- The anchor gets up to 3 attempts (`:787-817`).

**Named hold.** The run row goes to `blocked`, with `blocked_reason` and `attempts_exhausted` (`:268-270`, `:1092-1100`). One notification follows (`:1598-1673`).

**Scope.** The hold is per run key (`slug@version@release`), so other products are unaffected. This is consistent with prior audit row 25.

**Defect: paid repairs for an unfixable failure.**

- Every LIFESTYLE-job candidate FAILs `product_truth`, because `lifestyle_reading` classifies `pattern_derived` references as `"chart"`, and `compose.lifestyle_evidence` refuses informational references (`candidate_gates.py:252-255`, `:375-388`; `visual/compose.py:253`, `:279-281`). This was verified by probe: status FAIL, "reference: 'chart' is informational".
- Its failure category `product_fidelity` is neither a routed code nor upper-case, so `_repair_for` returns `{"directives": []}` rather than None (`image_production.py:1462-1477`; probe confirmed).
- `verification` therefore buys up to two more paid regenerations per LIFESTYLE role. None of them can pass.

**No automatic re-drive.**

- `restart` is reachable only from the Command Center (`api.py:543`; `image_production.py:1192-1283`).
- A FAIL-blocked run is not restartable (`:1222-1225`).
- A new release creates a new run.

**"When authorised".** The `image_generation` gate is `images.usable(db)`, meaning the last successful `image.probe` (`build2/executor.py:399-407`, `:816-826`; `gateway/images.py:1676`). It is opened automatically by the 6-hourly capability sweep if a provider key exists (`runtime/release.py:7729`; probe reuse 24 h, `images.py:1654`). There is no separate owner switch for listing-image generation.

### Point 10: unattended capability

- **Prompt architecture and reference handling:** CONNECTED (above).
- **Review jobs:** they run inline in the stage jobs; there is no separate image-review job type. Identity can never PASS (above).

**Gallery certificate.**

- `gallery_persist.recertify` → `release_gates.listing_set` (`publish/release_gates.py:522-640`).
- `listing_set` runs `el.check_set` (job collisions, not pixels; `publish/eligibility.py:328-368`), `dimension_audit` and `mobile_contexts`.
- When the disclosed render set is in use, generated frames "are not part of any certificate" (`gallery_persist.py:174-195`).
- **No cross-image product-consistency requirement exists in the certificate.**

**Generated frames are unpublishable by construction.** All of the following hold at once:

1. **F-852 exception.** Every check must read PASS, but `ETSY_POLICY_STATUS = UNKNOWN` is a constant (`candidate_gates.py:490`; `eligibility.py:449-505`).
2. **F-853.** It closes SCALE and COLOUR_CONTEXT (`eligibility.py:426-429`).
3. **LIFESTYLE.** `lifestyle_evidence` always FAILs.
4. **Laura publication gate.** It requires canonical `publication_approved` bytes (`candidate_gates.py:530-537`).
5. **Etsy sample-photo rule** (`publish/sample_photo.py`).

---

## 3. Specific answers

**Checks that judge a generated image.** Detail is under points 4–6.

- Identity uses blind vision readings against the three canonical references plus `identity_gate`. It needs two judges and a biometric floor, and in production it is UNKNOWN at best.
- Product fidelity:
  - deterministic CIR comparison on the flat lay (no side, stripe-count or rim checks for round or vessel pieces);
  - palette in vision-located regions, plus a vision consistency check, on lifestyle frames.
- Scale: none.
- Home consistency: none.
- Naturalism: a vision defect list, dHash sameness and a text filter.
- Everything is fail-closed.

**Gallery certificate and cross-image consistency:** no. Only metadata consistency (`campaign_consistency`) and job uniqueness (`check_set`).

**On rejection.**

- In-run bounded repair (3 attempts per role, 2 rounds, 12 calls, CA$2), then a named `blocked` hold on that run only, plus a notification.
- No automatic regeneration after a hold. The owner may restart (maximum 3, and not after a FAIL).
- There is no separate "regenerate" job type: repairs are `visual.image_production` stage jobs.

**Generated vs physical in records and the listing set.** See point 7.

**Gates that stop generation in production (names only).**

- `image_generation` (successful `image.probe`).
- `image_vision` (vision probe) for every judge.
- Provider credentials:
  - `BRAMBLELOOP_IMAGE_KEY_BFL` (per-account key name pattern `BRAMBLELOOP_IMAGE_KEY_<ACCOUNT>`, `gateway/images.py:220-249`);
  - `BRAMBLELOOP_IMAGE_KEY` and `BRAMBLELOOP_IMAGE_PROVIDER` (`:42-43`).
- `spend_plan.guard` per gallery (CA$2.00, 12 calls).
- The `publishing` agent's daily ceiling.
- `gateway.anthropic.monthly_ceiling_cad` (environment may lower it, never raise it), enforced by `images.reserve_render`.
- Launch-0-only shot plans.
- SHADOW refuses `store.publish` (`runtime/pipeline.py:1856`).

**Owner-supplied visual-direction and reference images.** There is no supported intake for using them in production conditioning. The paths that exist are:

1. **`visual/assets/owner_experiments/<YYYY-MM-DD>_<slug>/RECORD.json`.** A byte-identical copy of `research/final_build/w4/flux_experiments/<same>/RECORD.json`, enforced by `tests/test_w4_integ4_shipped_records.py`. It is read by `repair_routes.seed_experiments`/`seed_experiment` (`visual/repair_routes.py:77-221`) at each run's first stage.
   - **Fields read:**
     - `experiment_id` (idempotency key `seed:<id>`) and `recorded_at`;
     - `receipt_as_shown_on_dashboard{model, cost_usd, latency_s}`;
     - `product{slug, version, certification_refusal}`;
     - `references[{n, sha256}]` (n ≤ 3 is `laura_canonical`, otherwise `pattern_derived`);
     - `output{sha256, pixels}`;
     - `failure_categories[{code, detail}]` (codes from `creative.failure_codes`);
     - `outfit` (a dict of five slots, or text).
   - **Optional fields:** `prompt`, `verdict` and `lessons`.
   - **Image bytes are not shipped**; only sha256 hashes are recorded. The bytes and the dashboard screenshot stay under `research/`.
   - **What it produces:** a learning `ImageCandidate` (`method="owner_manual"`, `provenance_kind="ai_generated_owner_manual"`, technical FAIL, never publishable) plus wardrobe history.
   - **Never conditioning.** Note: `2026-10-19_owner_manual_batch2/` has a `BATCH_RECORD.json`, not a `RECORD.json`, so it is neither shipped nor seeded.
2. **Controlled experiments:** `experiments/definitions/<id>/definition.json`, `refs/*.png` and `prompt.txt`.
   - Each reference has a `position`, a `role`, and either a `canonical_frame` or a `file` plus `sha256`. The prompt has `file` and `sha256`; the definition also carries caps.
   - Verified by sha256 before any spend (`experiments/controlled.py:177-208`).
   - Requires owner `authorize` with step-up (`:306`) and `submit` (`:385`), then runs as job `visual.controlled_experiment`.
   - This is the **only** path where arbitrary committed reference images condition a FLUX request. The output is labelled EXPERIMENT and never published.
3. **Outfit `approved_reference`:** set via Command Center `images.outfit.set_reference` with an artefact sha256 (`app/command_center/api.py:579`; `visual/outfits.py:390`). It is the only owner image that enters production conditioning, as clothing only, after the canonical three (`image_stages.py:357-371`).
4. **`publish/owner_images.intake`:** owner-made *finished* images, evaluated as candidates (`:65-98`), not used as references.
5. **`visual/assets/MANIFEST.json`:** canonical assets with `sha256`, `role`, `provenance{date, run, decision_ids}` and `forbidden_as_fallback`. Owner concept images are recorded as `owner_concept` with `forbidden_as_fallback: true`, so they are not references.
6. **`visual/approval_record.py` and `approval_record.json`:** these only pin the `model.frozen` freeze row (key, version, approved_at, pack_version, candidate_fingerprint). They are not an image intake.

**To add new owner direction images the way existing ones are recorded:**

- For learning, add a dated `flux_experiments/<date>_<slug>/RECORD.json` with the fields above, keeping the bytes under research and the sha256 in the record. Mirror the file byte-identically into `visual/assets/owner_experiments/`.
- For trying them as conditioning, add a controlled-experiment definition.
- No path makes them production conditioning without new code.

**Hexagonal bread basket.**

- **Slugs:** listing `hexagonal-bread-basket` (`products/launch0.py:752-783`, first in `_CORE_LAUNCH0_SLUGS` at `:1040-1043`, owner decision D-W4-OWNER-BASKET-IDENTITY). CIR `market-basket-small`, built by `products/vessels.build_basket("small")` (`products/vessels.py:148-216`).
- **Version:** 1.3.0 in this tree, under D-W4-OWNER-BASKET-1.3.0 (`:43-50`). Production `0967c3ee` builds 1.2.0.
- **Title:** "Crochet Hexagonal Bread Basket".
- **Construction:** `joined_rounds`, one piece from a magic ring.
- **Base:** 10 rounds of sc, 6 → 60 sts, with the increases stacked at 6 corners, which makes a hexagon. It measures about 16.0 cm across the points and 13.9 cm across the flats.
- **Walls:** rounds 11–22 at 60 sc, about 9 cm tall. Round 11 is worked in the back loop only, which gives a defined base edge (1.3.0 only).
- **Gauge:** 12.5 sts × 13.8 rows per 10 cm, sc, 5.0 mm hook.
- **Colours:** cream `#FAF6EB` and wine `#6E1F2A`.
- **Stripes:** wine rounds 15–16 and 18–19, which is two 2-round wine stripes separated by one cream round, with three plain cream rounds above.
- **Rim:** the plain final sc round 22, cream. No edging is declared.
- **Release and certificate:**
  - No certificate record is in the repository; certificates live in the production DB, so their status is UNKNOWN.
  - The inventory of 2026-10-10 shows `market-basket-small@1.2.0` truth PASS in a shadow chain (`research/final_build/w4/PRODUCT_INVENTORY.md:36`).
  - 1.3.0 cannot be certified in production until Batch 5 deploys.
  - The basket 1.3.0 tester kit is provisional (BUILD_STATE line 26).
  - There is no physical sample and no sample photo.
- **Imagery:** the basket shot plan generates lifestyle, size and colour_context frames, all product-only with **no Laura**, in the kitchen.

---

## 4. Prioritised gap list, with assignment boundaries for one engineer

Each item gives the files owned and the acceptance check. All acceptance tests use a real DB and the registered `visual.image_production` handler with a stub renderer, as in the existing tests.

| P | Gap | Boundary (files) | Acceptance |
|---|---|---|---|
| P0-a | The LIFESTYLE `lifestyle_evidence` FAIL is structural, and the repair loop buys paid regenerations for it | `visual/image_production.py` (`_repair_for`: return None when the only categories are unroutable lowercase FAILs, or route `product_fidelity` explicitly), plus `visual/candidate_gates.py` (`lifestyle_reading` scope). The policy itself (whether pattern-derived references can ever satisfy `lifestyle_evidence`) is an owner decision; do not relax it. | A stub run on a Launch-0 listing records exactly one LIFESTYLE call, then blocks with the named reason "lifestyle_evidence: chart reference", and `generation_calls` does not grow on later ticks. |
| P0-b | Identity can never PASS automatically | `visual/identity_gate.py` (`QUALIFIED_EMBEDDERS`, plus a qualification record), `visual/candidate_gates.RealJudges` (configured `second_vision` from a second vision transport), `visual/vision_judges.py`. Spend and provider choice are OWNER ACTION. | With two distinct judge stubs and a qualified embedder stub, a canonical-matching frame reads identity PASS and a drifted one reads FAIL. Production config is UNKNOWN until owner-funded. |
| P0-c | Vessel and round fidelity is unqualified: no side count, wall-stripe count or rim check; the flat-lay brief is impossible for a basket | `visual/fidelity.py` (a vessel model: top-down hexagon corner count from the contour; a side-view or second-angle stripe-band count; rim profile), `creative/image_stages.py` (`FLAT_LAY_SCENE` variant for vessels: "standing upright, top-down plus a side view"), plus calibration fixtures rendered from `market-basket-small` | Calibration: the basket's own render passes; a 5- or 8-sided variant FAILs; a 3-stripe variant FAILs `WRONG_COLOUR_LAYOUT`; a braided rim FAILs `INVENTED_EDGING`. |
| P0-d | Basket 1.3.0 `ribbing_declared` misfire | `creative/pattern_refs.py:163` (treat a single BLO crease round, or any round whose note marks a fold, as not ribbing; require a repeating alternating loop/post pattern) | `technical_rules(build_basket("small"))["fabric"]["ribbing_declared"] is False`, and the negatives include "ribbing anywhere". |
| P1-a | No home or scene reference and no consistency check | New `visual/laura_home` assets: owner-approved room reference images recorded in MANIFEST style (sha256, provenance, decision id), passed as a `supplementary` kind `scene_reference` after the product references (`image_stages.campaign_references`). Add a blind vision "same room?" adapter in `vision_judges`. Generating or approving the room images is owner direction. | Every Laura and product-scene request for a kitchen listing carries the same room-reference sha. A mismatched-room stub reading FAILs `home_consistency`. |
| P1-b | Stripe and shape text is indirect in the prompt | `creative/pattern_refs.py` (`fabric_facts`: emit bands as `[{rounds:[15,16], colour:wine}, …]` and a polygon side count from `cir.geometry.corners`), `creative/flux_prompt.py` (PRODUCT v3 section: "hexagon, 6 corners; 2 wine stripes of 2 rounds…") | Prompt snapshot test for `market-basket-small` names the 6 corners, two 2-round wine stripes and the plain cream rim. |
| P1-c | The basket SIZE brief says "Laura" but the frame is product-only, and no scale check exists | `visual/shot_plans.py` (`CAMPAIGN_GENERATED` briefs conditioned on `laura`), and a scale reading in `vision_judges` (object-relative size band vs `twin` cm) | The brief for a non-Laura listing contains no "Laura". The scale adapter is UNKNOWN when unread and FAILs on a 2× size stub. |
| P1-d | Gallery certificate has no cross-image product consistency | `visual/candidate_gates.campaign_consistency` (add a pairwise blind `compare_items` across the chosen frames) and `release_gates.listing_set` for generated frames | A gallery whose two frames disagree on colour count or edging FAILs `campaign_consistency`. |
| P2-a | A blocked run is never re-driven automatically | `runtime/chain_successors.py` (a once-per-commit restart for capability-only blocks via `image_production.restartable`) | A run blocked on "image_generation gate closed" restarts once after the gate opens, and never after a FAIL. |
| P2-b | Prompt label "approved product photograph" | `creative/flux_prompt.py:217`: "AI-generated product-only flat lay of this exact product (verified against the pattern)" | Snapshot test. |
| P2-c | Records | Add D-W4-OWNER-LAURA-HOME to DECISION_LOG. Convert `owner_manual_batch2/BATCH_RECORD.json` into per-image `RECORD.json`, or document that it is excluded. | Doc and test only. |
| OWNER | Policy blockers outside code | F-852/F-853 scope for generated LIFESTYLE/SCALE/COLOUR_CONTEXT frames; the Etsy image-policy reading (UNKNOWN); funding a second vision judge and a face embedder; a physical basket sample plus photo (Etsy sample-photo rule); approving room reference images | — |

**Suggested single-engineer order:** P0-a → P0-d → P1-b. These are all deterministic, cost CA$0, and cover the prompt and loop. Then P0-c, the vessel verifier, which is the largest piece. P0-b, P1-a and P1-c each need owner spend or approval first.
