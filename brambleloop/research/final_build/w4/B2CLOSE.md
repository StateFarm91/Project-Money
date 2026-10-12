# W4-B2CLOSE (second pass, 2026-10-12): Build 2 company-executable rows

Branch `claude/w4-B2CLOSE`, from `origin/claude/w4-INTEG2` 28ba6df. Not deployed. Stub providers only:
no spend, no Etsy action, no production write. Production readings are read-only public GETs of
`https://brambleloop-os-production.up.railway.app` (deployed 7bbbe72), saved under `evidence_B2CLOSE/`.

Scope: the board headline (COMPLETION_BOARD_FINAL, generated c76be4c against production 0417f35) lists
Build 2 as 12 `implemented_unverified`, 2 `blocked_engineering` (#61, #195) and 1 OPEN-DEFECT (#61).

## Result

- **#61 Visual Semantic QA: closed in the ledger** (OPEN-DEFECT -> PROVEN, registry `covered`). The
  criterion is met in production (independent review running on 7bbbe72 with vision open), and the
  size-card clause, previously met only by proxy, is now explicit and tested. Board class becomes
  `implemented_unverified` until a release carrying this ledger is deployed (class B: the board's
  own rule reads the ledger at the deployed commit).
- **#195 Proof of Off-Device Autonomy: engineering blocker removed, row still open (class B).**
  Production 7bbbe72 fails exactly one condition, `no_unexpected_dead_letters_in_24h`, on three
  company defects that recurred *after* the hotfix deploy. All three are fixed and tested here. The
  row closes only after a 24 h unattended production window of a build carrying these fixes.
- **The 12 `implemented_unverified` rows: verified green on INTEG2, not closable by engineering.**
  Every evidence test file passes on clean INTEG2 28ba6df (12/12 files rc=0). On the board they
  wait on one thing: a release of INTEG2 deployed to production (the ledger at deployed 7bbbe72
  still shows them OWNER-GATED, and their fixes are absent from 7bbbe72, verified with `git show
  7bbbe72:...`). That is the integrator's release, then the production reading named per row.
- **Product recovery:** every Build 2 row about recovering, restoring, repairing or rebuilding
  products/chains/assets (#22, #50, #81, #99, #155, #172 dependency DAG + rebuild propagation, #173,
  #182, #184, #185 self-healing, #201) is already `verified_complete`; the one open recovery row is
  #195 (restart/recovery evidence), handled above. #300 (same-product complete seasonal chain) is
  `blocked_external` on `model_bearing_render` (the cycle's arena is hats; the asset step needs a
  model-bearing render no provider has produced) -- classification confirmed, not class A.
- **Other Build 2 class A rows:** none company-executable. Every remaining Build 2 row on the board
  is parked on an owner gate (live_listings, owned_surfaces, insights_paste, benchmark_purchases,
  testers_physical_proof, owner_rulings, oauth_transactions_r, paid_media_authority,
  offsite_storage) or an external one (real_customers, image_provider_capability, data_accrual,
  etsy_no_api_or_403). The 18 Build 2 class C rows in PRELAUNCH_SCOPE (#8, #10, #11, #14, #18, #23,
  #64, #82, #89, #94, #147, #229, #235, #237, #239, #263, #294, #298) were checked: each quoted
  criterion names live-customer measurement (CTR, impressions, repeat purchase, "after launch"),
  so C is correct. Not touched.

## Production findings (read-only, 2026-10-12 ~18:30Z, deployed 7bbbe72)

| Reading | Finding | Action |
|---|---|---|
| `GET /api/queue/dead` | `radar.score` KeyError 'slug' x2 at 18:06Z | Intelligence charter's CoverageGap handoff (and Laura follow-on proposals) enqueue `radar.score` with `{"handoff": ...}`, no slug; handler read `c["slug"]`. Fixed: `runtime/pipeline.py:_score_gap_queue` scores the open gap queue by concept through the ordinary per-slug job; a gap with no pool concept is reported, never scored 0. |
| `GET /api/queue/dead` | `ops.policy_watch` StringDataRightTruncation VARCHAR(40) at 18:01Z | `policy_knowledge.seed_snapshots` labels a reading `<read_on>:search_engine_excerpt_of_official_page` = 49 chars into `policy_snapshots.version` VARCHAR(40) (SQLite never enforces it). Fixed: `gates/platform_policy.fit_version` (head + 8-hex digest, distinct labels never collide), full label kept in `detail.version`, read back by `version_of` so certificate stamps still name the basis. |
| `GET /api/queue/dead` | `ops.offsite_archive` EphemeralStorageRefused at 18:08Z | the restore proof's scratch SQLite was not marked `scratch=True`, so the hosted REQUIRE_POSTGRES guard refused it. Fixed in `core/offsite.py` (same as `continuity.restore_proof`). |
| `GET /api/audit?action=assets.frame_review` | 4 reviews with vision_open=true; 3 heroes blocked (finished_result + chart_as_hero); materials/pattern_preview cleared on one product; every other frame `unjudged` on unmade realism checks; one size card `blocked` with no recorded reason | #61 evidence. The record now carries `failed_realism` and `third_party_marks`. **Open for the visual lane (not changed here):** infographic frames are asked the ten photographic realism checks (drape, hands_and_fingers, ...); the model answers `unclear`, and unmade is never passed, so most deterministic frames stay `unjudged` and publication stays blocked. Changing which checks apply to a non-photographic frame is a gate decision (C-80 / Codex P06 made "unjudged stays unjudged, whatever kind of frame" explicit, and `test_cert_listing_frames` asserts it), so it is reported, not relaxed. The heroes being read as charts is the hero imagery lane's finding. |
| `GET /api/verify` | ok=false only on `no_unexpected_dead_letters_in_24h` | #195's single unmet condition; the three defects above. |

## Requirement table

| ID | criterion (quoted) | before | after | evidence | class | remaining blocker |
|---|---|---|---|---|---|---|
| #61 | "The system must test whether an image communicates what its caption/title claims. A finished-result frame cannot be only abstract horizontal rows. A chart preview must look like a chart preview. A size card must communicate scale clearly. Use independent visual review plus deterministic metadata assertions; do not rely on the generator grading itself." | OPEN-DEFECT / blocked_engineering | ledger PROVEN (registry covered); board implemented_unverified until deployed | tests/test_w4_b2close2.py test_61_* 8/8 (5 of them fail on clean INTEG2 or need the new code: size_label, scale_shown, failed_realism); tests/test_cert_listing_frames.py 0 failing. Code: `visual/inspect.py` compare() `finished_result`/`chart_as_hero`/`chart_preview`/`size_reference`/new `size_label`; `runtime/release.py` ROLE_CLAIMS + `_review_frames` (records failed_realism, third_party_marks); `publish/listing_assets.py` `Frame.scale_shown`, `check_frame_plan` LISTING_SIZE_CARD_NO_SCALE. Production: evidence_B2CLOSE/prod_audit_frame_review_2026-10-12.json | B | release + deploy of a commit carrying this ledger; the production reading is the next `assets.frame_review` on that commit recording `failed_realism`/`third_party_marks` |
| #195 | "Before launch, prove the owner can turn off all personal computers for at least 24 hours while cloud Brambleloop continues scheduled cycles, queue processing, monitoring, learning tasks and state persistence. Record timestamps, jobs completed, incidents, costs and restart/recovery evidence. This is a launch-blocking acceptance test." | blocked_engineering (production_window; dead letters) | OWNER-GATED, engineering blocker fixed | tests/test_w4_b2close2.py test_195_* 3/3 (all 3 fail on clean INTEG2 with the exact production errors: KeyError 'slug', 49-char version, EphemeralStorageRefused); tests/test_cert_improve_autonomy.py rc=0; test_offsite, test_radar, test_platform_policy, test_policy_knowledge green. evidence_B2CLOSE/prod_queue_dead_2026-10-12.json, prod_verify_2026-10-12.json | B | approved deploy of a build with these fixes, then 24 h unattended: `GET /api/build` `off_device_proof.passed=true` and `/api/verify` ok (no unexpected dead letters in 24 h) |
| #15 | "For target Etsy queries, periodically capture legitimately observable search-result sets and score thumbnail composition, price/sale presentation, social-proof signals, pattern+video positioning, category diversity and Brambleloop differentiation. Treat observed rank as directional/contextual rather than absolute." | implemented_unverified | unchanged (verified on INTEG2) | test_serp rc=0, test_cert_intel_wave rc=0 (clean INTEG2 and this branch); intel/serp.py:364 capture_targets, :309 category_diversity, :337 differentiation_by_pod; production serp.captured 2026-10-12T00:31Z (evidence_B2MOAT) | B | release + deploy; ledger at deployed commit |
| #44 | "The recurring fictional model is one brand asset, not the brand itself. Build recognizable Brambleloop signatures: editorial layout, naming architecture, photography language, chart style, tutorial voice, collection families, customer-support experience and distinctive original design grammar. The shop must remain recognizable even on product-first listings without the model." | implemented_unverified | unchanged | test_w4_b2moat rc=0, test_cert_rebuild_chain rc=0; brand/moat.py:249 recorded_recognisability (read paths never pay a judge) | B | release + deploy; first `brand.recognisability_measured` from daily launch.readiness on that commit |
| #67 | "Before release, compare the listing set against a current sample of strong products in the same micro-market on measurable dimensions: finished-result clarity, thumbnail stop-power, proof, information density, consistency, video/support proposition and visual polish. Do not copy competitor creative; use the benchmark to reject obviously substandard presentation." | implemented_unverified | unchanged | test_blind_review, test_cert_parity_copy, test_w4_b2vision rc=0; creative/blinded.py:735 resolve_image | B | release + deploy; first non-UNKNOWN `creative.blind_review` on that commit |
| #86 | "Continuously study legitimate current market examples across categories to learn abstract commercial attributes: clever transformation, strong silhouette, recognisable motif, cute characterisation, premium minimalism, gift narrative, modularity, low-sew appeal, surprising function and collection logic. Store attributes and outcomes, not copied protected expression." | implemented_unverified | unchanged | test_cert_intel_wave2 rc=0; production creative.benchmark_memory "measured" over 36 listings 2026-10-12T00:23Z (evidence_B2MOAT). Own-outcome half needs live sales (C clause) | B | release + deploy |
| #88 | "Every finalist must have a one-sentence visual premise and a thumbnail storyboard before CIR work. Ask: if seller name, reviews, badges and price vanished, would the product idea itself still create curiosity or desire at mobile-grid size? If not, return to ideation." | implemented_unverified | unchanged | test_cert_design_pipeline, test_w4_b2vision rc=0; creative/intake.py:922 judge_held (judges stored bytes) | B | release + deploy; first `concept.judged` on that commit |
| #116 | "When studying high-performing products, decompose why they work into non-copying primitives: silhouette, motif density, dimensionality, palette role, prop/context, function, emotional tone, construction novelty, personalization, bundle logic and thumbnail readability. Store the decomposition, not a replica prompt." | implemented_unverified | unchanged | test_cert_intel_wave2, test_w4_b2vision (test_reference_decomposition_carries_personalization_bundle_and_thumbnail_primitives) rc=0; creative/reference.py:51 | B | release + deploy; next creative.reference_reading storing 11 primitives |
| #126 | "Before CIR engineering for expensive concepts and again before release, render concept boards/thumbnails into a simulated Etsy-style grid beside a current category-matched benchmark set with seller/review signals hidden. Independent judges rank attention, comprehension, desire and distinctiveness. Brambleloop must clear the defined threshold without brand favoritism." | implemented_unverified | unchanged | test_cert_intel_wave2, test_w4_b2vision (test_the_grid_handler_never_sends_an_unresolvable_render_and_scores_each_product) rc=0 | B | release + deploy; first judged `creative.grid_tournament` on that commit |
| #218 | "For relevant categories, place Brambleloop candidates beside current category-matched MJs benchmark evidence in a blinded comparison. Evaluate concept desirability, distinctiveness, product clarity, thumbnail strength, styling, apparent craftsmanship, giftability and purchase confidence. If Brambleloop looks obviously generic/amateur by comparison, return it to creative development rather than shipping." | implemented_unverified | unchanged | test_cert_parity_copy, test_w4_b2vision (test_the_challenge_reads_desirability_distinctiveness_and_giftability_from_the_panel, test_a_stale_or_absent_panel_reading_stays_unjudged) rc=0; creative/blind_review.py:610 challenge | B | release + deploy |
| #277 | "Brambleloop must continuously observe MJsOffTheHookDesigns and the elite benchmark panel for commercially successful product concepts, silhouettes, product families, merchandising mechanisms, palette directions and seasonal movement. Proven demand is an instruction to compete, not a reason to avoid the category. The system should enter the same broad/generic product market aggressively while engineering Brambleloop's own pattern and producing its own visual assets." | implemented_unverified | unchanged | test_cert_design_pipeline, test_w4_b2vision (test_a_held_board_is_judged_from_the_artifact_store_not_a_dead_path) rc=0 | B | release + deploy; first held winner reaching cir.draft |
| #281 | "When an MJs/elite listing demonstrates a strong generic market concept, route it to the relevant specialist pod. Decompose why the product appears commercially strong, generate Brambleloop responses for the current and upcoming seasonal windows, run Creative Supremacy/benchmark gates, engineer the selected original pattern through CIR, generate Brambleloop-owned assets, then launch/advertise according to evidence." | implemented_unverified | unchanged | as #277 | B | release + deploy |
| #304 | "For every accessible MJs listing selected for baseline or change audit, browser/vision workers traverse the accessible gallery and analyze each image as competitive evidence. Extract product form, proportions, generic construction cues visible from the finished item, colour/stripe/blocking logic, styling, model/product presentation, detail coverage, setting, thumbnail strategy and seasonal signals. This is not satisfied by text scraping or search-result thumbnails." | implemented_unverified | unchanged | test_intel, test_serp, test_w4_b2vision (test_gallery_drain_is_breadth_first_through_the_catalogue_pods) rc=0; intel/vision.py:90 prefer_pods; production intel.gallery_analysis judged 4/4 2026-10-12T02:00Z | B | release + deploy |
| #309 | "MJs listing/new-change event -> specialist pod -> visual/text market decomposition -> demand/season fit -> seasonal colour/theme tournament -> customer make-time estimate -> preferred/latest launch date -> original CIR/pattern engineering -> truth/certification -> Brambleloop-owned premium assets -> benchmark challenge -> SEO/ads/content -> launch -> performance measurement -> winner scaling -> lessons back to MJs specialist memory." | implemented_unverified | unchanged | test_cert_design_pipeline, test_w4_b2vision rc=0 | B | release + deploy |

## Ledger

Regenerated with `build2_ledger.py` from the same production reading as the committed ledger
(`evidence_B2VISION/prod_build_2026-10-12.json`, 0417f35 03:35Z + `evidence_B2GATE2/derived_data_gates_2026-10-11.json`),
so only this branch's changes move it: PROVEN 227 -> 228, OPEN-DEFECT 1 -> 0 (OWNER 42, DATA 41,
EXTERNAL 6, N/A 3). Rows changed: #61 (state), #195 (gate note), #293 (reachability evidence order only).
`autonomy/autonomy_map.json` regenerated (follow_on_edges 57 -> 59: the new gap-queue fan-out edge,
plus `_reprice_on_plan_drift`, which was already drifting on clean INTEG2).

## Regression (all through `/home/user/bl-runs/testslot.sh`)

Required regression set, this branch (final code):
- test_vacuity: PASS (rc=0; first run flagged the new test's loop, fixed with a non-emptiness assertion)
- test_search_hero_publish: 4/4
- test_cert_listing_frames: 0 failing
- test_v11_autonomy_timeline: 0 failing (after regenerating autonomy_map.json; clean INTEG2 fails it, 57 vs 58 edges)
- test_launch: 15 failing, **identical on clean INTEG2 28ba6df** ("hero: 340 px legibility ['2 piece(s) read at 340 px where the pattern makes 1']"; hero-render lane)
- test_cost_governance_wave2: 1 failing, **identical on clean INTEG2** (`test_no_production_module_creates_a_directory_nothing_removes`: app/main.py:1179, visual/hero_review.py:57, visual/inspect.py grid_identify mkdtemp; only the inspect.py line number moved, 320 -> 329)

Row and touched-module tests, this branch: test_w4_b2close2 11/11 (6 of 11 fail on clean INTEG2,
each with the production error), test_w4_b2close 18/18, test_closure 27/27, test_w4_b2_build2_ledger
ALL OK, test_w4_b2gates 12/12, test_w4_b2gate2, test_w4_b2vision, test_w4_b2moat, test_serp,
test_cert_intel_wave, test_cert_intel_wave2, test_blind_review, test_cert_parity_copy 20/20,
test_cert_design_pipeline 17/17, test_intel, test_cert_rebuild_chain 0 failing,
test_cert_improve_autonomy, test_radar, test_cert_trend_evidence, test_w4_mjs_findings,
test_swarm_runtime, test_platform_policy, test_policy_knowledge 20/20, test_w4_gatesi 34/34,
test_cert_commerce 14/14, test_fb4_launch 9/9, test_offsite, test_texture, test_w4_firstimg 12/12:
all rc=0. Baseline on clean INTEG2 for the 12 rows' evidence files: 12/12 rc=0.

## Owner actions

None new. Closing #195 and moving the 13 PROVEN rows to `verified_complete` needs the existing
approved-deploy step (integrator release of INTEG2 + owner deploy approval), then 24 h unattended.
