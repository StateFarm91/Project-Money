# W4-PRODREADY: eight-product customer readiness, the legibility rule, the #61 closure, and scipy

**Context**
- **Branch:** `claude/w4-PRODREADY`, from `origin/claude/w4-INTEG2` 9c3812b. That base already
  contains VISROLE 52b702d, so `claude/w4-VISROLE-WIP` 4dcb7c9 was not needed: it is an older
  merge of the same commit.
- **Production:** 1b21e81, in SHADOW. Nothing was deployed, published, POSTed or spent.
- **No model was called, and no paid image was generated.** Every render in this report is
  deterministic and was made locally.

**Verdict: none of the eight named products is customer-ready.** Every one is certified, has
true Product Truth, has complete US and UK PDFs, and can be rebuilt byte-for-byte from its CIR.
Every one is still NOT READY, because of the blockers below. Certified does not mean
customer-ready.

## 1. Per-product matrix

### How it was measured

- **Script:** `research/final_build/w4/prodready_run.py <dir> --chain`.
- **What it runs:** the REAL release chain in a SHADOW worker, on a fresh SQLite database, with
  the network refused:
  - gate.certify, then listing.draft, assets.build, pricing.position, listing.seo and
    launch.plan;
  - store.publish last, which is refused because the system is in SHADOW (as designed).
- **Scope:** every release of the eight products, which is 10 releases because the baskets come
  in S, M and L. The code's own 8th Launch-0 product (see §1.3) was run as well.
- **How each check was read:** from the code that enforces it. UNKNOWN never counts as PASS.
- **Evidence:** `evidence_PRODREADY/prodready.json` (per release, per check, with reasons) and
  `evidence_PRODREADY/chain_run.json`. The chain took 556 s and the report 782 s.

### 1.1 Summary

| check | baskets S/M/L | cloudline blanket | hexagon coasters | nordic star ornaments | winter village graphghan | harvest table runner | housewarming key basket | mosaic placemat pair |
|---|---|---|---|---|---|---|---|---|
| certification (certificate granted, nothing withheld) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| Product Truth (compiles clean; title, assembly, fabric and size promises backed) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| US + UK PDFs (both rendered; every package section; AI disclosure in each; children's statements complete where owed) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| deliverable recovery (fresh CIR equals the certified content hash; both PDFs byte-identical to the certified hashes) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| listing image set (listing set certified; certified bytes readable for upload) | PASS (9/8/8 images) | PASS (6) | PASS (6) | PASS (6) | PASS (6) | PASS (6) | PASS (8) | PASS (6) |
| legibility at actual display size (uploaded set) | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** |
| hero / thumbnail (search certificate incl. hero) | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** |
| role-specific visual checks | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| price consistency (listing = Launch-0 plan) | PASS (CA$6.50) | PASS (CA$7.50) | PASS (CA$4.00) | PASS (CA$4.50) | PASS (CA$7.50) | **FAIL** | PASS (CA$5.50) | PASS (CA$5.00) |
| customer copy incl. AI disclosure | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| publication gate (`release_gates.for_publish`) | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** |
| **status** | **NOT READY** | **NOT READY** | **NOT READY** | **NOT READY** | **NOT READY** | **NOT READY** | **NOT READY** | **NOT READY** |

**What the passing rows mean:**
- **Customer copy:** the disclosure section is complete, and two `platform_policy.DISCLOSURES`
  sentences appear verbatim in the stored description: `ai_assisted_design` and
  `disclosed_render`. `pdf.AI_DISCLOSURE` is in both PDFs.
- **Listing image set:** the images are the bytes `store.publish` would upload
  (`etsy_ops.certified_images`).
- **Deterministic role checks:** these pass on every non-photo frame of every product (record
  labels, legibility, scale and disclosure). Only the vision answers are missing.

### 1.2 The exact blockers

Products 1 to 8 are, in order: baskets, cloudline, coasters, ornaments, graphghan, runner, key
basket, placemats.

| # | blocker | products | owner | exact evidence |
|---|---|---|---|---|
| B1 | **Uploaded listing images break the owner's legibility rule.** The set `store.publish` uploads for Launch-0 is the disclosed-render set (D-FB-7: 3 disclosed renders) plus verified gallery and contents supplements. It is not the `listing_assets` frames fixed in §2. Its type sizes are fixed constants, measured at their real display size (390 px phone gallery; 340 px for headlines). | all 8 | company | disclosure caption `render_contract.CAPTION_PX` 34 → **6.6 px**; scale-bar and dimension labels `LABEL_PX` 30 → **5.8 px**; gallery body 50 → 9.8 px, small 40 → 7.8 px, title 64 → 10.9 px at 340; contents body 46 → 9.0 px, small 36 → 7.0 px, title 64 → 10.9 px at 340. Floor: 11 px. |
| B2 | **No Etsy category, so the search certificate refuses**, and with it the hero/thumbnail judgement it carries. F-005: "category UNKNOWN -- no stored Etsy taxonomy snapshot names a node for this product, and none is assumed". F-004: attributes have no schema to be complete against. | all 8 | owner, then company | The owner supplies the Etsy app keystring (read-only `GET /seller-taxonomy`). `listing.taxonomy_refresh` is then company work. |
| B3 | **Independent visual review not made.** #61 `frame_review_state`: every listing frame is `unreviewed`. Parity is unjudged on `competitive_blind_review` and `hero`. The one role check that needs the describer, `no_third_party_marks`, is unanswered, which is never a pass. | all 8 | company, on a funded model | A funded `image_vision` run of `assets.build` and the blind review is needed. Not run here, because no model calls or spend were allowed. |
| B4 | **First-customer gate:** gauge and size claims are UNRESOLVED. No passed physical sample is bound to the content, so every finished dimension is arithmetic from the stated gauge. | 1–5, 7, 8 | owner / tester | Work a physical sample (tester roster / physical proof). |
| B5 | **First-customer gate:** `etsy_remote_state` is UNVERIFIABLE. Etsy has never confirmed a listing-image upload (9 open claims). | 1–5, 7, 8 | owner (go-live) / external | A first draft upload under an owner publication grant. |
| B6 | **First-customer gate:** `fulfilment_and_download` FAIL. The artifact store is not durable, so a paid download can resolve to nothing after a redeploy. | 1–5, 7, 8 | owner | Object storage (the offsite storage bucket owner action). |
| B7 | **The harvest table runner is not a Launch-0 product in the code.** `launch0.py` keeps it as the "first reserve". It is not among the CAP-1 three, which are `nordic-forest-mosaic-throw-baby`, `mosaic-placemat-pair` and `housewarming-key-basket`. Its Thanksgiving (CA) window closed 2026-10-12. Because of this: | 6 | owner decision | Add it to Launch-0 with a price plan, or replace it in the named eight. |
| | • `launch_price_check` has no plan. `pricing.position` set CA$6.94, against the candidate's proposed CA$5.50. | | | |
| | • The first-customer gate does not run for it at all. That is why B4 to B6 are absent for it. This is **not** a pass. | | | |
| B8 | **Production defect (fixed on this branch, see §4):** scipy was not installed in the production image. | all 8 | company (release) | Production 1b21e81 could not run the disclosed-render verifier or the listing export check. |

### 1.3 Scope note

- `products.launch0.LAUNCH0_SLUGS` (CATALOGUE_FLOOR_APPROVED=True) names
  `nordic-forest-mosaic-throw-baby`, not `harvest-table-runner`.
- That product was run as well. It reads exactly like the other Launch-0 products: every
  deterministic check PASS, and NOT READY on B1 to B6.

### 1.4 What would make a product READY

The products need, in this order:
1. **B1:** a disclosed-render contract with legible type (company). It touches the render
   contract and its verifier, which redraws exactly those words, so it is a contract version
   bump. It was not attempted on this branch.
2. **B2:** the taxonomy keystring (owner).
3. **B3:** one funded vision pass (company).
4. **B4 to B6:** a physical sample, object storage and the first draft upload (owner).

The harvest runner also needs B7.

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
