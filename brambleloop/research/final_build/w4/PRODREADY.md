# W4-PRODREADY: eight-product customer readiness, legibility, #61, scipy, taxonomy, motif truth

**Context**
- **Branch:** `claude/w4-PRODREADY`, from `origin/claude/w4-INTEG2` 9c3812b. That base already
  contains VISROLE 52b702d, so `claude/w4-VISROLE-WIP` 4dcb7c9 was not needed: it is an older
  merge of the same commit.
- **Production:** 1b21e81, in SHADOW. Nothing was deployed, published, POSTed or spent.
- **No model was called, and no paid image was generated.** Every render in this report is
  deterministic and was made locally.
- **Second pass (same day).** Three changes since the first pass:
  - B1 is fixed with disclosed-render contract 3 (§7).
  - B2 is re-diagnosed: no owner action is needed (§8).
  - The ornament and placemat names are corrected through Product Truth (§9).
  - The eighth product is `nordic-forest-mosaic-throw-baby`, the code's CAP-1 product. The
    coordinator confirmed it. `harvest-table-runner` stays a reserve, and its first-pass row is
    kept for the record.

**Verdict: none of the eight Launch-0 products is customer-ready yet.**

Every product now passes all eight of these checks:
- certification;
- Product Truth, including the new motif gate;
- US and UK PDFs;
- byte-identical rebuild from the CIR;
- the listing image set;
- **legibility of every uploaded image at its real display size**;
- price;
- copy with the AI disclosure.

**What still blocks all of them:**
1. **The search certificate (B2).** No category is matched. This is a company code fix, not an
   owner action.
2. **The independent vision review (B3).** It is unreviewed. It needs a funded run.
3. **The first-customer gate (B4 to B6).** It needs a physical sample, durable storage and a
   confirmed Etsy upload.

Certified does not mean customer-ready.

## 1. Per-product matrix (second pass, final code)

**How it was measured**
- **Script:** `research/final_build/w4/prodready_run.py <dir> --chain`.
- **What it runs:** the real release chain in a SHADOW worker, on a fresh SQLite database, with
  the network refused. Every release goes through:
  - gate.certify, listing.draft, assets.build, pricing.position, listing.seo and launch.plan;
  - then store.publish, which is refused in SHADOW (as designed).
- **How each check was read:** from the code that enforces it. UNKNOWN never counts as PASS.
- **How uploaded images were measured:** the bytes `store.publish` would upload
  (`etsy_ops.certified_images`) are matched by sha256 to a deterministic re-render of the same
  frames:
  - the disclosed hero, scale, detail and angle views;
  - the gallery frames;
  - the CONTENTS frame.
  Every matched frame's recorded lettering is then measured at its display size. An upload
  that no re-render matches reads UNKNOWN.
- **Evidence:** `evidence_PRODREADY/prodready.json` and `chain_run.json` (second pass).

### 1.1 Summary

| check | baskets S/M/L | cloudline blanket | hexagon coasters | ornaments (1.5.0) | winter graphghan | key basket | placemats (1.4.0) | nordic forest baby |
|---|---|---|---|---|---|---|---|---|
| certification | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| Product Truth (incl. motif_promise) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| US + UK PDFs (sections, AI disclosure, children's statements) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| deliverable recovery (fresh CIR = certified hash; PDFs byte-identical) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| listing image set (certified, uploadable bytes) | PASS (9/8/8) | PASS (6) | PASS (6) | PASS (6) | PASS (6) | PASS (8) | PASS (6) | PASS (6) |
| **legibility: every uploaded image, every essential line** | PASS (9/8/8 images, min 11.2 px) | PASS (6/6, min 11.2 px) | PASS (6/6) | PASS (6/6) | PASS (6/6) | PASS (8/8) | PASS (6/6) | PASS (6/6) |
| hero / thumbnail (search certificate) | FAIL (B2) | FAIL (B2) | FAIL (B2) | FAIL (B2) | FAIL (B2) | FAIL (B2) | FAIL (B2) | FAIL (B2) |
| role-specific visual checks | UNKNOWN (B3) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| price = Launch-0 plan | PASS CA$6.50 | PASS CA$7.50 | PASS CA$4.00 | PASS CA$4.50 | PASS CA$7.50 | PASS CA$5.50 | PASS CA$5.00 | PASS CA$7.50 |
| copy incl. AI disclosure | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| publication gate | FAIL (B2, B4-B6) | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| **status** | **NOT READY** | **NOT READY** | **NOT READY** | **NOT READY** | **NOT READY** | **NOT READY** | **NOT READY** | **NOT READY** |

Notes on the matrix:
- **Role checks.** The deterministic role checks pass on every non-photo listing frame:
  record labels, legibility, scale and disclosure. Only `no_third_party_marks` is unanswered,
  because it needs the describer.
- **Copy.** The stored descriptions carry the `ai_assisted_design` and `disclosed_render`
  sentences verbatim, and both PDFs carry `pdf.AI_DISCLOSURE`.
- **The stored listings now read as follows:**
  - "Textured Stripe Ornament Set (6) | Crochet Pattern PDF | US and UK Terms", tagged
    stripe/textured ornament;
  - "Raised Diamond Lattice Placemat Pair | Crochet Pattern PDF | US and UK Terms".

### 1.2 Blockers (exact)

| # | blocker | products | owner | status / exact next step |
|---|---|---|---|---|
| B1 | Uploaded images broke the legibility rule (6.6 / 5.8 / 7.0-10.9 px) | all | company | **Resolved on this branch**: disclosed-render contract 3 (§7). Every uploaded image's essential lines measure ≥ 11.2 px at their display size. It needs a release and deploy, and production then re-renders the sets. |
| B2 | Search certificate: category UNKNOWN (F-005), so no attribute schema (F-004) and no hero/search PASS | all | **company** (was listed as owner) | Production already reads Etsy's 3065-node seller taxonomy daily with the configured keystring (§8). The matcher `etsy_taxonomy.pattern_subtree` finds 0 crochet-pattern nodes. This branch makes the refresh record the tree's pattern and crochet names. After the next deploy, one daily run shows Etsy's real structure, and the matcher is corrected from that. **No owner action is needed.** |
| B3 | Independent vision review: every frame `unreviewed` (#61); parity unjudged (`competitive_blind_review`, `hero`); `no_third_party_marks` unanswered | all | company, on a funded model | A funded `image_vision` run of `assets.build` and the blind review, in production after deploy. Not run here, because no model calls or spend were allowed. |
| B4 | First-customer gate: gauge and size claims UNRESOLVED; no physical sample is bound to the content | all | owner / tester | Work a physical sample (tester roster / physical proof). |
| B5 | First-customer gate: `etsy_remote_state` UNVERIFIABLE; Etsy has never confirmed an image upload | all | owner (go-live) / external | The first draft upload under an owner publication grant. |
| B6 | First-customer gate: `fulfilment_and_download` FAIL; the artifact store is not durable | all | owner | Object storage (the offsite storage bucket owner action). |
| B7 | `harvest-table-runner` is not Launch-0 in the code (a reserve; window closed 2026-10-12; no price plan) | (reserve) | owner decision | Replaced in the eight by `nordic-forest-mosaic-throw-baby`, as confirmed. |
| B8 | Production defect: scipy missing from the production image | all | company (release) | Fixed on this branch (§4). It ships with the next release. |
| B9 | Names promised motifs the CIR does not draw: "Snowflake" ornaments, an unqualified "Diamond Lattice" | ornaments, placemats | company | **Resolved on this branch** (§9): retitled, re-versioned and re-chained, and a Product Truth gate now refuses the old names. |

### 1.3 First pass (for the record)

| check | baskets S/M/L | cloudline | coasters | ornaments 1.4.0 | graphghan | harvest runner | key basket | placemats 1.3.0 | nordic forest baby |
|---|---|---|---|---|---|---|---|---|---|
| legibility of uploaded set | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| price | PASS | PASS | PASS | PASS | PASS | **FAIL** (no plan; CA$6.94 vs CA$5.50) | PASS | PASS | PASS |
| every other check | as in 1.1 | | | | | | | | |

## 2. Legibility (owner ruling 2026-10-19, D-W4-VISROLE-LEGIBILITY)

Owner: "essential customer-facing text must be readable at the ACTUAL display size; there is no
blanket pixel floor."

**Classification is deterministic, from the frame plan.**
- Every line `listing_assets` draws records a `slot`.
- `visual/frame_role.text_tier(role, slot)` decides the tier and the display size:
  - **Essential, read in the 340 px grid:** title and headline.
  - **Essential, read in the 390 px phone gallery** (`mobile.CONTEXT_MEANS[PHONE_GALLERY]`):
    product type, disclosure, row label and value, size label, scale reference, colour name and
    preview caption.
  - **Secondary:** the brand line and the pattern excerpt.
  - **Any unnamed slot:** essential at 340 px, the strictest rule.

**Fixed in `publish/listing_assets.py`.** The new sizes are measured on the products' frames.

| line | before (390 px) | after (390 px) |
|---|---|---|
| hero disclosure "not a photograph…" | 8.0 / 8.6 px | 11.1 px (two lines, split after the comma) |
| "CROCHET PATTERN · PDF · CHART + WRITTEN" | 9.75 px | 11.3 px |
| size card "180 cm adult" | 10.1 px | 11.1 px |
| materials colour names | 9.4 px | 11.1 px |
| every row label ("WRITTEN PATTERN", "YARN", "WORKED AT"…) | 10.1 px | 11.3 px |
| pattern preview caption | 9.4 px | 11.1 px |

- **Secondary lines are reported, not blocked.** The brand line is 9.4 px and the excerpt 9.4 px.
- **Enforcement:**
  - `check_frame_plan` blocks `LISTING_FRAME_<n>_ESSENTIAL_TEXT_ILLEGIBLE`.
  - The `text_legible_340` role check fails on essential text, and records
    `essential_failing` and `secondary_below_floor`.
  - The headline-at-340 rule and the `MIN_TEXT_PT` rule for every line are unchanged.
- **Found while measuring, and fixed.**
  - The size card's label was drawn centre-anchored, and the layout recorder measured it
    without the anchor.
  - The coasters' "10 cm across × 8 cm tall" therefore started **290 px off the left edge of
    the image**, so the measurement was cut off. Layout QA could not see it.
  - The recorder now measures with the anchor, and the label is kept inside the safe area.
  - The scale bar moves clear of the label. The piece and the bar are recorded as graphics.
- **D-W4-VISROLE** is amended, append-only, as `D-W4-VISROLE-LEGIBILITY` in DECISION_LOG.md.
- **Limit (B1 above):** these frames are reviewed by #61 and stored by assets.build. They are
  not the images Launch-0 uploads. The uploaded disclosed set still breaks the rule.

## 3. Build 2 #61 closure restored

- **Why INTEG3 held it.** Closing it removed the "fund the model" card. #61 was the last row
  parked on `image_vision`, so `test_cert_dashboard` (legacy-row merge) and
  `test_w4_owner_actions` (production-nine) failed.
- **What changed.** Both tests now assert the correct consequence, without being weakened:
  - **test_w4_owner_actions:**
    - `model_provider_balance` is still a `fund_model` decision.
    - `model_credits`, which is aliased to image_vision, is accounted for in
      `suppressed_unblocks_nothing` (the etsy_shop precedent).
    - Every production row is either shown or suppressed, never both and never dropped. The
      new assertions are stricter than the old superset check.
  - **test_cert_dashboard:**
    - The merge assertions are unchanged, and run on `benchmark_purchases`, a gate that still
      parks 5 rows.
    - A stale image_vision row is asserted to be suppressed, not shown as a card.
- **Registry.** `requirements.json` #61 is `covered`, with proof `test_cert_listing_frames`,
  `test_w4_b2close2` and `test_w4_visrole`. `parked_on` is removed and a dated note is added.
- **Regenerated.** The ledger was regenerated from the same production readings. Build 2 is
  now PROVEN 228 / OPEN-DEFECT 0. The board, prelaunch scope and CC snapshots were regenerated.
  #61 moves to `implemented_unverified`: proven on the branch, waiting on a release.

## 4. Production defect: scipy undeclared (coordinator addition)

**The defect.**
- `visual/render_verification.py:271` (`_scale`) imports `scipy.ndimage` with no guard. So does
  `publish/disclosed_listing.py:171`. `visual/stitch_identity.py` re-imports it inside its
  functions.
- The production image installs only `requirements.lock` (Dockerfile:25,
  `--require-hashes --no-deps`), and scipy was in neither file.
- **So in production 1b21e81, rendering and verifying the disclosed listing images could not
  run.** The local venv had scipy installed, which hid this from every test.

**The fix.**
- `requirements.txt` gains `scipy>=1.13`, with the reason.
- `requirements.lock` gains `scipy==1.17.1` with all 61 PyPI sha256 hashes. scipy needs
  `numpy<2.7,>=1.26.4`, and the locked numpy 2.4.6 is unchanged.
- The pin was added with `scripts/lock_requirements.py`'s own `read_lock` / `pypi_hashes` /
  `render`. Rendering the existing lock reproduces it byte for byte, so only the scipy stanza
  was added.
- **Verified:** `pip download --require-hashes --no-deps` of the locked numpy and scipy for
  cp311 manylinux_2_28 resolves both wheels.

**Why the lock was not regenerated from the venv.** The venv has drifted from the lock on 20
other distributions since the container restart, for example SQLAlchemy 2.0.54 → 2.1.5 and
pillow 12.3.0 → 13.0.0. Re-pinning those would be an unreviewed supply-chain change. As a
result `test_dependency_lock::test_the_lock_is_exactly_the_installed_closure_of_the_interpreter_running_the_suite`
fails, both here and on clean INTEG2. That is environment drift, not this change.

**Consequence:** local suites are currently exercising different dependency versions from the
ones production installs. **The integrator should rebuild the venv from `requirements.lock`
before the next freeze.**

**New test:** `tests/test_w4_prodready_deps.py`, 3 tests.
- Every third-party module imported anywhere under `src/` is checked by AST walk, so
  function-level imports count. Each must map to a distribution pinned in `requirements.lock`.
- There are three documented non-runtime exceptions: fontTools (a build tool), mitsuba (a
  guarded spike) and pdfplumber (a fallback behind pypdf). Each must stay a lazy import and stay
  out of the lock.
- **Mutation check:** against the previous lock, the test fails and names
  `scipy ... disclosed_listing.py:171`.

**Also note:** `httpx` was missing from the venv, so `fastapi.testclient` could not import. It
was installed into the venv as a test-only tool. It is not a production dependency and is not
in the lock.

## 5. Tests (all through testslot)

| suite | result |
|---|---|
| test_w4_prodready_legibility (new) | 7/7 |
| test_w4_prodready_deps (new) | 3/3 |
| test_w4_owner_actions (updated) | 6/6 |
| test_cert_dashboard (updated) | 18/18 |
| test_w4_visrole | 8/8 |
| test_cert_listing_frames | 7 OK, 0 failing |
| test_w4_b2close2 | 11/11 |
| test_cert_publish_gates | 18 OK, 0 failed |
| test_w4_thumbfloors 7/7, firstimg 12/12, imgfix 3/3, disclosedqa 8/8, herotourney 4/4, multipiece 5/5, herovision 6/6 | pass |
| test_listing_parity_gate 6, test_search_hero_publish 4/4, test_photoreal_calibration 19, test_w4_b2moat 3/3, test_w4_b2vision 7/7, test_blinded 46, test_publish_execution_gate 1, test_cert_rebuild_chain 11 | pass |
| test_w4_board 7, test_w4_cc_snapshots 3, test_w4_cc_company 23/23 | pass |
| test_w3_supply_chain 6, test_w4_fm2_lock_boot_guard 3/3, test_w4_packetrel 6/6, test_rc1_own_release 10, test_w3_hq_independence 4 | pass |
| test_dependency_lock | 6 pass, **1 fail**: the venv-versus-lock drift described in §4, which is pre-existing and also fails on INTEG2 |
| **required set:** test_vacuity 8/8 (after one loop assertion was added), test_launch 28, test_cost_governance_wave2 39, test_search_hero_publish 4/4, test_cert_listing_frames, test_v11_autonomy_timeline 7 | pass |
| test_w3_decision_index | 3 pass |

## 6. Requirement IDs

- **Build 2 #61: closed in the ledger** (PROVEN). Criterion met per B2CLOSE, plus VISROLE.
  - Tests: `test_w4_b2close2` (test_61_*), `test_cert_listing_frames`, `test_w4_visrole`.
  - Registry: `src/brambleloop/build2/requirements.json` (id 61).
  - Board class: `implemented_unverified` until a release deploys.
- No other row is closed. B1 to B7 are open blockers.

## 7. B1: disclosed-render contract 3 (D-W4-CONTRACT3)

**What Launch-0 uploads.** `release_gates.listing_set` takes the `disclosed_listing_set` branch
(D-FB-7). Each listing uploads:
- 3 disclosed renders: hero, scale and detail, plus the angle view for vessels;
- verified supplements: the gallery MATERIALS, COLOUR_CONTEXT, CONSTRUCTION and SIZING frames,
  and the CONTENTS preview.

The `listing_assets` frames fixed in §2 are reviewed by #61, but they are not uploaded.

**Before (contract 2), at display size:**
- disclosure 34 px → 6.6 px;
- scale and dimension labels 30 px → 5.8 px;
- gallery body 50 → 9.8 px and small 40 → 7.8 px;
- contents body 46 → 9.0 px and small 36 → 7.0 px;
- titles 64 → 10.9 px at 340 px.

**After (contract 3):**
- every contract word is set at 58 px (11.3 px at 390 px), and titles at 66 px (11.2 px at
  340 px);
- the disclosure is on two lines, with "not a photograph" whole;
- annotations are at most two lines, wrapped to the zone;
- lettering that cannot fit refuses (`LetteringRefused`) and is never shrunk.

**Rows on the 2000 px canvas:**

| element | position |
|---|---|
| product | 170-1490 |
| scale bar and label | from 1504 |
| annotations | from 1570 |
| disclosure | from 1704, last glyph ends at 1836 |
| title-safe limit | 1840 |

**Why the product zone is 0.745, not smaller.** It was measured, not assumed:
- at 0.68, the cloudline blanket's cream row fell to 0.4 % at 340 px, and the unchanged 340 px
  colour check refused it;
- at 0.745, the lowest share is cream at 1.65 %, against a 0.5 % floor;
- the top edge moved from 0.09 to 0.085 for the stocking hero, which sat exactly at the 25 %
  coverage floor.

**Verifier.** The verifier re-letters exactly the contract-3 lines, from its own CIR figures.
- The caption IoU spans both lines.
- No tolerance was changed.
- `tests/test_w4_prodready_contract3.py` proves that each of these fails:
  - contract-2 type;
  - a painted-out "not a photograph";
  - one edited figure.

**Versions.** No cached contract-2 render can be reused:

| component | version |
|---|---|
| disclosed-render | 3.0.0 |
| assembled | 2.0.0 |
| verifier | 3.0.0 |
| gallery-frames | 2.0.0 |
| contents-frame | 2.0.0 |

- `product_authority.QUALIFIED_RENDERERS` qualifies only the contract-3 renderers. This is a
  one-line change in W-VISREF's file, required by the version bump; nothing else in that file
  was touched.
- The multipiece hero hash pins were re-pinned once, with the old values recorded.
- Three attack tests in `test_disclosed_render` were moved to contract-3 geometry. Every one
  still fails the forged frame.

**Measured on the chain, every essential line of every uploaded image, all 8 products:** see
§1.1. The smallest essential line is 11.2 px, the floor is 11 px, and no line is below it.

## 8. B2: the Etsy taxonomy needs no owner action

**Read-only production GETs:**
- `/health`: 1b21e81.
- `/api/audit?action=etsy.taxonomy_refreshed`: daily runs on 2026-10-17, 18 and 19 (00:34Z),
  each recording:
  - `ran: true` and `reading: measured`;
  - `nodes: 3065`, `network_calls: 1`;
  - `credential_refused: false` and `gate_missing: []`;
  - `pattern_subtree: 0`, with why "read Etsy's taxonomy; no node is named both pattern and
    crochet, so every category stays UNKNOWN".
- `/api/audit?action=etsy.taxonomy_unmeasured`: empty.

**Findings:**
- The code path already exists: `listing.taxonomy_refresh`, scheduled daily as
  `etsy_taxonomy`. It uses the API-key-only client (`etsy_taxonomy.ApiKeyTaxonomyClient`, GET
  `/seller-taxonomy/*` only), with the keystring already configured.
  - The successful read is the proof that the keystring is configured and healthy.
  - I did not list Railway variables. Their values would have entered this session, and the
    read itself answers the question.
- The blocker is the company's own matcher. `pattern_subtree` needs an ancestor-or-self named
  "pattern" **and** one named "crochet", and Etsy's real tree has no such path. The likely
  reason is that crochet is a property ("craft type"), not a node. That is unverified until
  the evidence below lands.
- **The change on this branch:**
  - When the subtree is empty, the refresh's audit row now records `name_evidence`: the paths of
    nodes named pattern or crochet, and the children of the pattern nodes (bounded).
  - It is served by the existing read-only `/api/audit`.
  - Test: `tests/test_w4_prodready_taxonomy.py` (3).
  - After the next deploy, the first daily run shows Etsy's structure, and the matcher (and,
    if crochet is a property, the attribute schema) is corrected from it.
- **Verdict: no owner action is needed for B2.** It is company work, gated only on the next
  release.

## 9. Motif truth: names corrected through Product Truth (owner directive 2026-10-19)

**The new gate.** `products.launch0.motif_promise` adds the `motif_promise_backed` gate to
`product_truth` and to `certified.name_matches_what_the_cir_makes`.
- **What it checks:** every motif word in these texts:
  - the CIR title;
  - the candidate's title and what_it_is;
  - the SEO title, keyword families and tags.
- **What backs a word:** the motif the CIR's provenance declares (`primitives_used`, for
  example `products.motifs:snowfall`), read through `MOTIF_DECLARATIONS`. The vocabulary
  includes snowflake, star, diamond, lattice, fir, heart and others.
- **Relief motifs.** Every Launch-0 motif is a relief, so title-like text must also say raised,
  relief or texture.
- **Unknown motifs.** A motif not in the table backs nothing.

**The two products:**

| product | old name | what the CIR makes | new name (version) |
|---|---|---|---|
| nordic-star-ornaments | "Nordic Snowflake Ornament Set (6)" | six striped pieces with scattered 3 x 3 raised crosses; no snowflake outline | "Textured Stripe Ornament Set (6)" (1.4.0 → **1.5.0**) |
| mosaic-placemat-pair | "Diamond Lattice Placemat Pair" | the lattice is only raised stitches, one colour per row | "Raised Diamond Lattice Placemat Pair" (1.3.0 → **1.4.0**) |

**What else changed:**
- The SEO title, keyword families, tags and description lead were corrected. The snowflake
  phrases were replaced with stripe and textured phrases.
- The listing-identity qualifiers were corrected.
- The two creative briefs were corrected, and `emotional_brief.MOTIF_IMAGERY["snowfall"]` no
  longer licenses "snowflake".
- The release fingerprints were updated with the version bumps.

**No pattern was redesigned.** The copy could be made truthful.

**Proof** (`tests/test_w4_prodready_motif.py`, 5 tests):
- The old titles are refused: "Nordic Snowflake …", production 1.0.0's "Nordic Star …", and
  the unqualified "Diamond Lattice …".
- The old phrases "snowflake ornament" and "nordic snowflake" are refused.
- The new titles and copy are backed.
- All 8 Launch-0 products pass Product Truth.

**Re-chained:** both products certify at their new versions, with every gate as before (§1.1).
- The slug `nordic-star-ornaments` is an internal identifier. It is not shown to buyers and is
  unchanged.
- Production holds an older draft at 1.0.0 that still uses the old title. The next release
  supersedes it. Nothing was written to production.

## 10. Second-pass tests (testslot, final code)

**New suites:**

| suite | result |
|---|---|
| test_w4_prodready_contract3 | 6/6 |
| test_w4_prodready_motif | 5/5 |
| test_w4_prodready_taxonomy | 3/3 |

**Contract-3 visual suites, all green after the updates below:**
- test_disclosed_render 27/27, after three attack tests moved to contract-3 geometry;
- test_w4_multipiece 5/5, after the hero pins were re-pinned for contract 3;
- test_w4_render_assembled 50, test_w4_verify_pockets 7/7, test_w4_visual2 8/8;
- test_disclosed_certified_upload 7/7, test_disclosed_render_runtime 3/3, test_fb4_lc 16,
  test_final_visual_authority 10/10;
- test_w4_disclosedqa, test_w4_herovision, test_w4_imgfix, test_w4_thumbfloors,
  test_w4_visual_gallery_frames, test_w4_visual_certified_gallery, test_w4_visual_angle,
  test_w4_render_corners, test_w4_cand_garland, test_w4_visualseo;
- test_owned_photography 30, test_parity 8, test_w3_k12_model_photography 10.

**The 85 suites that import launch0, the SEO strategy, the emotional brief or the release
fingerprints, plus the required set:**
- 82 green on the first run: 1186 OK lines.
- 3 not green on that run:
  - **test_vacuity**: one loop needed a non-emptiness assertion. Fixed, now 8/8.
  - **test_w3_seo_strategy**: the ornament phrase "striped" was not traceable, the tag
    "two color crochet" had no query family, and the "ornament" stem filled 6 of 13 tag slots.
    Fixed, now 12/12. test_w4_seo_packages 6, test_v11_seo_truth 9 and test_w3_seo_constraints
    8 also pass.
  - **test_product_run**: hit the runner's 1800 s timeout after 7 OK, with no failures. It was
    re-run alone with a longer timeout (result in the final report).
- test_release_versions passes, with the two bumped rows.
- These all pass: test_launch, test_launch0*, test_w4_l0_product_readiness,
  test_w4_cap1_placemat_price, test_w4_placemat_reprice, test_w4_catalog_reconciliation,
  test_w4_creative_brief and test_w4_pipe_name_truth.

**Required set:** test_vacuity, test_launch, test_cost_governance_wave2, test_search_hero_publish,
test_cert_listing_frames and test_v11_autonomy_timeline all pass.
