# W4-FIRSTSALE: the first-sale blockers the company can solve itself

**Context**
- **Branch:** `claude/w4-FIRSTSALE`, from `origin/claude/w4-INTEG3` 364ade0.
- **Production:** b931d17, in SHADOW. Production was only read, with GETs to `/health` and
  `/api/audit`.
  - Nothing was deployed, POSTed, published or spent.
  - Etsy was not called.
  - No credential was touched.
- **Visual pipeline files:** not edited. These belong to W-VISNEXT: creative/flux*,
  image_stages, visual/image_production, outfits, styling and fidelity.
- **Blocker numbering:** the brief's numbers are used, with PRODREADY §1.2's in brackets:
  - B2 is the category;
  - B4 is "upload never confirmed" [PRODREADY B5];
  - B5 is durable delivery [PRODREADY B6];
  - B3 is the vision review;
  - the physical sample is [PRODREADY B4].

## Verdict

| blocker | status | evidence | owner action |
|---|---|---|---|
| **B5 durable customer PDF delivery** [B6] | **RESOLVED on this branch.** Production's `deliverables_restorable` and `fulfilment_and_download` pass once it ships. | §2. The rehearsal ran the real chain for 10 releases and then simulated a redeploy by deleting the artifact directory. Every certified PDF was then served from Postgres with a matching sha256 (10/10). With those Postgres rows also deleted, a re-render reproduced the certified bytes exactly (FAIL→PASS, 10/10). A drifted re-render is refused. The rollback drill's `deliverables_restorable` passed for 10/10 releases. Tested on SQLite and on a local Postgres 16. | None. Object storage is not needed for this. |
| **Purchase → download rehearsal** | **PASS, 10/10 releases, 20/20 files** | §3. Each run took an Etsy-shaped paid receipt, built a delivery link per terminology, fetched the bytes from the database alone (the disk was gone), and compared sha256 with the certified PDF. `etsy_called: false`. | None |
| **B4 image upload readiness (offline)** [B5] | **PASS for all 8 products: 10 releases, 69 images, built after the simulated redeploy.** This also fixed one real defect found on the way: the certified upload set did not survive a redeploy. | §4 | None |
| **B4 upload confirmed by Etsy** [B5] | **UNKNOWN.** It stays UNKNOWN until a real upload. | `check_etsy_remote_state` reports 9 open gaps. | Owner-gated publication (see the owner actions below). |
| **B2 Etsy category** | **UNKNOWN.** The matcher is built and tested, but the real data has not been read through it. | §1. The newest production row (2026-10-20T00:13Z) predates b931d17's `name_evidence`. The live verifier exits 3 (UNKNOWN). | None (company work) |
| **First-sale readiness view** | **BUILT** | §5. `GET /api/cc/first-sale`, shown on the Command Center's Completion tab, plus `launch.first_sale`. | None |
| B3 independent vision review | FAIL, not changed here | `frame_review_state`: every frame is `unreviewed` | Owner approves a funded `image_vision` run (spend). |
| Physical sample (gauge and size) [B4] | FAIL, not changed here | No `full_physical_make` is bound to any content. | Tester or owner |
| Publication grant / phase | FAIL (SHADOW, kill switch off) | `publication_authority.resolve` | Owner |

**No product is first-sale ready.** The local rehearsal shows the same row for every product:
- **PASS:** certification, Product Truth, image truth, listing, price, disclosure,
  **image_upload_payload** and **durable_delivery**;
- **UNKNOWN:** category (the tree was never read in a local run) and etsy_upload_confirmed;
- **FAIL:** seo, which is B2; vision_review, physical_sample and publication_grant.

The full table is in `evidence_FIRSTSALE/first_sale.md`.

## 1. B2: the Etsy category matcher

**What production shows** (read-only GET `/api/audit?action=etsy.taxonomy_refreshed`,
2026-10-20T03:52Z):
- The daily rows for 10-17, 10-18, 10-19 and 10-20 (00:13Z) each record:
  - `nodes: 3065` and `pattern_subtree: 0`;
  - `credential_refused: false` and `gate_missing: []`.
- None carries `name_evidence`. b931d17's worker started at 03:48Z, after the 00:13Z refresh.
- The first row with Etsy's real pattern and crochet names is due on the next daily refresh,
  around 2026-10-21T00:0xZ. **No real node name or id was available to this branch, so none
  is used and the category stays UNKNOWN.**

**What Etsy documents.** Source: Open API v3, `https://www.etsy.com/openapi/generated/oas/3.0.0.json`,
read 2026-10-20. This is the document `etsy_constraints.OPENAPI_URL` already cites.
- `getSellerTaxonomyNodes` returns a tree of `SellerTaxonomyNode`, with fields `id`, `level`,
  `name`, `parent_id`, `children` and `full_path_taxonomy_ids`.
- `getPropertiesByTaxonomyId` returns per-node `TaxonomyNodeProperty`, with fields
  `property_id`, `name`, `possible_values[value_id, name]`, `is_required` and others.
- So a technique can be a property value of a pattern node rather than a node itself. That fits
  production's evidence: no path names both a pattern and crochet.

**The matcher** (`commerce/category.py`):
- **Path route, unchanged:** a node whose path names both a pattern and crochet.
- **New property route:**
  1. Find the one pattern-named root that is not under another craft (knit, sew, quilt,
     cross stitch, paper and so on). Several unrelated roots are refused, unless exactly one
     sits under a top-level node named for craft supplies.
  2. Descend by the product's object, then by its family, then into a generic pattern child.
     A pattern child that names another object or shelf is never entered. This was a real bug
     the tests caught: "Blanket Patterns" was being entered for an ornament.
  3. The choice is **CHOSEN only when Etsy's own stored property schema for exactly that node
     offers the value "Crochet"**. The basis is recorded as Etsy's `property_id` and
     `value_id`, and the listing's property payload sets that value.
- No snapshot, no unique root, no stored schema, or no Crochet value all give UNKNOWN.
- The id and path always come from the snapshot.

**The refresh** (`integrations/etsy_taxonomy.py`):
- When there is no path match, it reads the property schemas of the nodes the chooser would
  land on. This is bounded by `MAX_PROPERTY_READS` = 40 and is GET-only.
- It records `property_candidates` and `category_choices` on the audit row: for each Launch-0
  category, the status, id, `path_ids`, `path_names` and crochet basis.

**Verification against the real row:** `tests/test_w4_firstsale_taxonomy_live.py`. It makes one
public GET.
- If the row has `category_choices`: every CHOSEN category must end its `path_ids` at its
  `taxonomy_id`, have as many names as ids, have a pattern-named node on its path, and carry a
  path or property crochet basis with integer Etsy ids. Any violation is CONTRADICTED (exit 1).
- If the row has only `name_evidence` (b931d17): it runs the root rule on the real names. This
  is a diagnostic, never a match. The result stays UNKNOWN (exit 3).
- **Run today: `UNKNOWN`** ("the newest row predates name_evidence").
- **Re-run after the next deploy plus one daily refresh.** It verifies the match exactly by id
  and path.

**Re-attribution:** `launch.product_readiness._seo` named the owner for a missing taxonomy
("the owner supplies the keystring"). Production reads the tree daily with the keystring and is
not refused, so the gap is now attributed to the company matcher.
`test_w4_l0_product_readiness` now asserts that. It still asserts FAIL, so it is not weakened.

## 2. B5: durable customer PDF delivery

**Production before this branch** (read-only GET of `launch.rollback_rehearsed`,
2026-10-20T00:03Z):
- Every listed release reads `deliverables_restorable: false`, with "8 recorded artefact(s) are
  not on disk".
- `fulfilment_and_download` reads FAIL ("the artifact store is not durable").

**The design.** It uses only what production already has, so there is no schema change and no
new provider.
- **Postgres keeps the certified bytes.** `core.models.DurableArtifact` (`durable_artifacts`,
  sha256 primary key) already exists. The offsite continuity archive restores it, and
  `ArtifactStore.get(sha, db=db)` already falls back to it. What is kept:
  - `assets.build` now keeps both certified PDFs and every stored listing frame
    (`runtime/release.py`, `keep=`).
  - Issuing or re-validating a listing-set certificate keeps every certified upload image
    (`publish/release_gates._keep_certified_bytes`).
- **Re-render is a fallback** (`commerce/deliverables.resolve_pdf`).
  - The order is disk, then Postgres, then a re-render from the certified CIR. The re-render
    uses `released_on` pinned to the release row, the stored calibration, and the same lesson
    links.
  - The re-render is accepted **only if its sha256 equals the certified one**, and it is then
    kept.
  - Anything else raises `DeliveryRefused`. A paid download never resolves to nothing, and
    never to a different file.
- **Production catch-up.** Daily `launch.readiness` calls `deliverables.secure_release` for
  every listed release before the dry rehearsal. It keeps the bytes from disk, or re-renders
  them byte-identically, or reports a refusal.
- **Gates:**
  - `rollback.rehearse` now counts a hash as restorable when it is on disk **or** held in
    Postgres and re-hashed on read.
  - `first_customer.check_fulfilment_and_download(store, db=, slug=, version=)` reads:
    - PASS only when both certified PDFs are held;
    - FAIL when one is not;
    - UNVERIFIABLE when nothing is certified.
  - Without a database it gives the old answer (FAIL).
- **Size.** In the 10-release rehearsal:
  - 20 PDFs, 5.4 MB;
  - 59 listing frames, 14.3 MB;
  - 35 supplement images, 2.9 MB;
  - plus 30 disclosed renders that were already kept, 1.7 MB.
  - That is about 2.4 MB per release, one row per distinct hash. There is no pruning yet. A
    superseded release's rows stay until retention is added (company follow-up).

**Proof:** `tests/test_w4_firstsale_deliverables.py`, 6 tests on a real Launch-0 CIR. They pass on
SQLite and, with `BL_TEST_PG_URL`, on a throwaway local **Postgres 16**. Every case passes on both:
- kept bytes survive a wiped artifact directory, and the drill passes;
- with nothing held, a byte-identical re-render is kept;
- a drifted re-render is refused and never stored;
- with nothing certified, the result is UNVERIFIABLE;
- purchase → download.

## 3. Purchase → download rehearsal (shadow)

**How it was run:** `research/final_build/w4/firstsale_run.py <dir> --chain`.
- The real chain ran for all 10 releases in 572 s, with SHADOW, the network refused and no
  credential.
- The artifact directory was then **moved away** to simulate a redeploy.

**Steps, per release:**
1. A paid, digital, Etsy-shaped `ShopReceipt` with a fixture listing id.
2. `delivery_links`: one link per terminology. A link is an internal reference, not a public
   URL: no route serves PDFs by hash.
3. `resolve_pdf`, with re-rendering forbidden.
4. The served sha256 must equal the certified sha256, and the bytes must start with `%PDF-`.

**Result: 10/10 receipts and 20/20 files PASS, `source: durable`.** Unpaid and unmapped receipts
FAIL, as the tests prove.

**The re-render fallback** ran on a copy of the database with every held PDF row deleted.
Every release went FAIL→PASS, and all 20 PDFs were `re-render (byte-identical to the certified
sha256)`.

**Honest limit:** on Etsy, the buyer downloads the file Etsy stores from `uploadListingFile` at
publication. This rehearsal proves the bytes the company would upload, and would redeliver
through support, are the certified ones after any redeploy. Etsy's own download can only be
observed after an owner-granted publication. The API exposes no download event (`order_ledger`).

Evidence: `evidence_FIRSTSALE/firstsale.json` (per release: `durable_before`, `purchase`,
`rerender`, `deliverables_restorable`, `image_upload`), `first_sale.md` and `chain_run.json`.

## 4. B4: Etsy image-upload readiness (offline)

**What it checks** (`integrations/etsy_image_readiness.py`).

How the requests are built:
- The exact `uploadListingImage` requests come from the **client's own** `EtsyClient._upload_image`,
  which runs its validation and builds its fields. `_call` is replaced by a recorder.
- They are encoded with production's `http.multipart_body`.
- They are re-parsed with Python's `email` package, an independent parser.

What is checked against Etsy's OpenAPI and the Help Center rules already quoted in
`etsy_constraints`:
- the request is a POST to `/shops/{shop_id}/listings/{listing_id}/images`;
- the body is `multipart/form-data`;
- the binary is in a part named `image`, and those bytes equal the certified bytes;
- `rank` runs 1..n in certificate order, with n ≤ 20;
- `alt_text` matches the certified alt text and is at most 500 characters;
- the format is jpg/png/gif and matches the file suffix;
- there is no transparency and no animation;
- the first image is at least 635 px and landscape or square;
- 2000 px is recommended;
- more than 1 MB is flagged as advice.

**Result, on exactly the bytes `store.publish` would upload** (`etsy_ops.certified_images`),
**after the simulated redeploy: PASS for all 10 releases, 69 images.**
- The largest image is 219 KB.
- There are 5 warnings, none blocking. Five disclosed alt texts are 253–256 characters,
  against Etsy's advice of "up to 250 characters". Those alt texts are written by the visual
  lane's disclosed renders, so this is passed to W-VISNEXT and not changed here.

**A defect this found.** Before the fix, the same check after the redeploy failed on frames 4
and up of every release ("recorded but not on disk").
- The gallery supplements and the CONTENTS frame were certified by hash but stored only on the
  ephemeral disk.
- So after a redeploy the certified upload set was unreadable, and publication would have
  refused.
- The fix: listing-set certification now keeps them in Postgres. This is in
  `publish/release_gates.py`, with no visual file touched. The rerun: PASS, 69/69.

**Only a real upload can confirm** (owner-gated publication):
- that Etsy accepts these bytes on this shop (the API publishes no size limit);
- that each rank returns a `listing_image_id`;
- that asynchronous processing completes (`full_width` and `full_height` are null until then);
- that the alt text is stored verbatim and the rank order is honoured;
- the thumbnail crops;
- that the draft activates.

Tests: `tests/test_w4_firstsale_view.py`, covering the contract, each rule, a corrupted part,
the first-sale view and the CC route.

## 5. First-sale readiness view (Command Center)

**What the module returns.** `launch/first_sale.build(db)` reads only. It reuses
`launch.product_readiness` (certification, Product Truth, image truth, listing, price,
disclosure and seo) and adds these gates:

| gate | blocker |
|---|---|
| `etsy_category` | B2 |
| `vision_review` | B3 |
| `image_upload_payload` | B4 |
| `durable_delivery` | B5 |
| `physical_sample` | — |
| `etsy_upload_confirmed` | — |
| `publication_grant` | — |

- Each gate gives PASS, FAIL or UNKNOWN, with its evidence, **who acts** (company or owner) and
  the next action.
- It also returns shop-wide gates: operating phase, taxonomy read, category matched, durable
  delivery and Etsy upload confirmed.
- UNKNOWN is never PASS. On a fresh shadow database, no gate that was not measured reads PASS,
  and a test asserts this.

**The route.** `GET /api/cc/first-sale` (`app/command_center/first_sale.py`):
- It sits behind the existing default-deny owner-session gate. The operator bearer token gets
  401.
- It is read-only (POST gives 405), single-flight, and cached for at most 5 minutes.
- The PWA renders it as the "First-sale readiness" card on the Completion tab
  (`static/js/views/completion.js`). The CC mock fixture includes it.

## OWNER ACTION REQUIRED (batched; nothing here is new spend by this branch)

| # | action | why | max cost | minutes | if it waits |
|---|---|---|---|---|---|
| 1 | Approve a funded `image_vision` run of `assets.build` and the blind review (B3) | Every listing frame is `unreviewed`. A model review is consequential spend. | Within the existing image_vision budget ceiling (see `cost_governance`). This branch adds none. | 5 | The search certificate and publication stay refused for all 8 products. |
| 2 | Physical sample: a tester crochets one Launch-0 product and records it | Gauge and size claims are UNRESOLVED without a bound `full_physical_make`. | Yarn plus tester time | Owner: 10 to arrange | `physical_sample` stays FAIL. No first-customer gate passes. |
| 3 | After 1 and 2 and the B2 re-check: go-live phase decision and a sealed draft-publication grant for the first product | Publication is owner-only (kill switch, SHADOW). It is the only way to confirm B4 (`etsy_upload_confirmed`). | Etsy listing fee US$0.20 per published listing (`commerce.fee_schedule.listing_fee_cad`), only when activated | 15 | No listing exists, so there is no first sale. |

**Company follow-ups:**
- (a) After this branch deploys and one daily refresh runs (around 00:0xZ), run
  `tests/test_w4_firstsale_taxonomy_live.py`. If it reads VERIFIED, `listing.seo` re-runs and
  the category becomes PASS. If it reads UNKNOWN, `name_evidence` shows Etsy's real structure,
  and the matcher is corrected from it.
- (b) Retention for `durable_artifacts` of superseded releases.
- (c) The visual lane shortens 5 alt texts to 250 characters or fewer.

## Tests (testslot)

**New:**

| suite | result |
|---|---|
| test_w4_firstsale_taxonomy | 6/6 |
| test_w4_firstsale_deliverables | 6/6 on SQLite, and 6/6 with Postgres 16 |
| test_w4_firstsale_view | 5/5 |
| test_w4_firstsale_taxonomy_live | self-test OK; live result UNKNOWN (exit 3, as designed) |

**Required set:**

| suite | result |
|---|---|
| test_vacuity | 8 |
| test_launch | 28 |
| test_cost_governance_wave2 | 39 |
| test_search_hero_publish | 4 |
| test_cert_listing_frames | 6 OK, 0 failing |
| test_v11_autonomy_timeline | 6 |

All rc=0.

**Suites for the touched files, all rc=0 and 0 FAIL:**

| suite | result |
|---|---|
| test_first_customer_gate | 12 |
| test_cert_rebuild_chain | 10 |
| test_w4_pipe_board | 70 |
| test_search_truth | 32 |
| test_v11_seo_taxonomy | 4 |
| test_w4_prodready_taxonomy | 3 |
| test_w4_ccpacket | 5 |
| test_launch0_listing_truth | 14 |
| test_w4_fmgate_catalogue_filters | 1 |
| test_w4_seo_packages | 6 |
| test_w4_etsycomm | 16 |
| test_w3_k1_search | 20 |
| test_etsy | 17 |
| test_fb4_launch | 9 |
| test_w4_fmend_rehearsal_phase | 5 |
| test_w4_fmclose_etsy | 20 |
| test_fb4_ops | 12 |
| test_w4_smoke | 10 |
| test_w4_prodready_deps | 3 |
| test_secret_scan | 7 |
| test_w4_l0_product_readiness | 4 (updated attribution) |

**Second batch, after the release_gates change** (all rc=0, 0 FAIL):

| suite | result |
|---|---|
| test_w4_firstsale_taxonomy | 6 |
| test_w4_firstsale_deliverables | 6 |
| test_w4_firstsale_view | 5 |
| test_disclosed_certified_upload | 7 |
| test_cert_publish_gates | 18 |
| test_w4_cap1_gates_intact | 5 |
| test_search_certificate_integrity | 2 |
| test_k8_listing_estate | 9 |
| test_w4_disclosedqa | 8 |
| test_draft_intent_precreate_refusal | 1 |
| test_cert_commerce | 14 |
| test_cert_listing_frames | 6 |
| test_search_hero_publish | 4 |
| test_vacuity | 8 |
| test_w3_tmp_hygiene | 16 |

BUILD_STATE.md and DECISION_LOG.md are left to the integrator at merge.
