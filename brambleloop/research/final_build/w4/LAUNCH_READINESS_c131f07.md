# Launch-0 launch readiness, measured at c131f07 (W4-LAUNCHREADY, 2026-10-11)

Branch `claude/w4-LAUNCHREADY`, based on `c131f07`; the one fix is in `88b240e`. Nothing here was
deployed, published, written to Etsy or Railway, or paid for. The phase stays SHADOW.

## How this was measured

Every verdict below comes from the repository's own gate code, not from earlier prose:

1. `research/final_build/w4/pipe_chain_run.py <scratch> <7 CIR slugs>` ran the real release chain
   (gate.certify → listing.draft → assets.build → pricing.position → listing.seo → launch.plan →
   store.publish) in a SHADOW worker on a scratch SQLite DB. Every outbound socket was refused and
   no Etsy or model credential was present. All 7 releases certified; all 7 `store.publish` jobs
   were refused, which is the expected result in shadow. Run time was 232 s
   (`evidence_LAUNCHREADY/chain_run.json`).
2. The daily `launch.readiness` job and `marketing.schedule` were then run once on the same DB, as
   production cadences would run them. The `launch.readiness` job also runs the rollback rehearsal.
3. `research/final_build/w4/launch_readiness_run.py <scratch>` (new; it only reads) calls, for each
   release:
   - `compile_cir`
   - `products.launch0.product_truth` / `price_plan` / `launch_price`
   - `gates.first_customer.gate_product` (with the DB and the stored listing)
   - `ops.publication_authority.evidence`
   - `publish.release_gates.for_publish` (the exact verdict `store.publish` refuses on)
   - the stored `Listing` and `listing_search_profiles` rows
   - radar POOL bundle membership
   - `launch.packet.build`

   Output: `evidence_LAUNCHREADY/readiness_c131f07_before.json` (before step 2 and before the fix)
   and `readiness_88b240e_after.json`.

Interpreter note: the task named `.claude/worktrees/visual-investigation/brambleloop/.venv`, which
does not exist. The equivalent `/home/user/Project-Money/brambleloop/.venv/bin/python` was used,
with one process at a time and a private TMPDIR.

## Launch-0 set

There are 5 products (`products.launch0.LAUNCH0_SLUGS`) and 7 releases, because the basket comes in
3 sizes:

| product | release (CIR slug @ version) | release hash |
|---|---|---|
| nursery-nesting-baskets | market-basket-small@1.2.0 | 1ddde587f537 |
| | market-basket-medium@1.2.0 | 00182234041c |
| | market-basket-large@1.2.0 | cc698c1b1498 |
| cloudline-baby-blanket | cloudline-baby-blanket@1.2.0 | 7c63dbdd501f |
| hexagon-coaster-set | hexagon-coaster-set@1.2.0 | 3754ed17a63b |
| nordic-star-ornaments | nordic-star-ornaments@1.4.0 | 18c6e64fa4c5 |
| winter-village-graphghan | winter-village-graphghan@1.3.0 | b41e0430fe3d |

## Per-release inventory

These results are the same for all 7 releases unless a column says otherwise.

| check (gate code) | result |
|---|---|
| CIR compiles (`compile_cir`) | **PASS**: 0 errors, 0 warnings |
| Certified release (`gate.certify`) | **PASS**: certificate granted, nothing withheld |
| Product Truth (`launch0.product_truth`) | **PASS** on all 5 gates (compiles clean; title, assembly, fabric and size-label promises backed). `twin.calibrated` is False everywhere. |
| Originality (`release_gates.originality_gate`) | **CHECKED**, 0 reasons |
| Pattern PDFs, US and UK (`first_customer.final_pdf`) | **PASS**: both render with no problems. Pages US/UK: S 9/9, M 10/10, L 11/11, blanket 35/35, coasters 7/7, ornaments 7/7, throw 7/7 |
| Terminology, reverse compile, counts | **PASS** on all three |
| Licence and safety statements | **PASS**. The baskets and the blanket carry the full children's statement set. |
| Imagery (`first_customer.imagery`) | **PASS**: 3 disclosed hero/scale/detail frames, structurally verified on their bytes, plus 3–6 gallery frames, all covered by a valid listing-set certificate |
| Listing set (`publication_authority.listing_set`) | **PASS**: certified |
| Disclosure | **PASS**: every owed disclosure is in the stored copy |
| Listing claims | **PASS** |
| Listing draft | **present**, state `draft`, 13 tags each. Titles are 73–107 characters; descriptions 2,888–4,740 characters. |
| Attributes (search profile) | drafted: digital, PDF, crochet, pattern_type, skill level, colours, US terms, chart and written instructions; `occasion` is null |
| Search certificate (F-004/F-005) | **FAIL**: category UNKNOWN because no Etsy taxonomy snapshot is stored, so the attributes have no schema to be checked against |
| Creative parity #75 (`publication_authority.parity`) | **UNKNOWN**: `hero` and `competitive_blind_review` are unjudged, and the frames have not been independently reviewed (#61) |
| Gauge and size claims | **UNRESOLVED**: no physical sample is bound to this content |
| Etsy remote state | **UNVERIFIABLE**: 9 open claims; the image upload has never been confirmed by Etsy |
| Fulfilment and download | **FAIL**: the artifact store is not durable |
| Policy freshness | **UNKNOWN**: the policy sources have never been read |
| Rollback | **PASS**, once the daily `launch.readiness` rehearsal had run (it was UNKNOWN before) |
| Seasonal window (#297) | **launch**. Ornaments: 34 days of runway. Throw: 15 days. The others are evergreen or unassigned. |

### Prices

All prices are SOURCED bands, decided by `commerce.pricing`, and every release is within its plan
band.

| release | price | band | net after modelled fees |
|---|---|---|---|
| baskets S/M/L | CA$6.50 | CA$4–12 cluster | CA$5.60 |
| blanket | CA$7.50 | CA$8.47–11.65 premium blanket band | CA$6.51 |
| coasters | CA$4.00 | CA$4–12 cluster, at its floor | CA$3.34 |
| ornaments | CA$4.50 | CA$4–12 cluster | CA$3.79 |
| throw | CA$7.50 | CA$8.47–11.65 premium blanket band | CA$6.51 |

The two CA$7.50 prices sit below the band floor on purpose: the plan proposes this to buy early
reviews. The modelled fees exclude offsite ads, the regulatory fee and currency conversion. If all
three apply, the blanket's net falls to CA$5.11.

### Bundles

None of the 7 releases is a member of a listable bundle.

- nordic-star-ornaments belongs to radar family `nordic-forest`, whose `nordic-forest-bundle`
  waits in `collection.assemble`. That bundle has no CIR of its own and stays outside Launch-0.
- The cloudline family has no bundle.

### Listing-ready summary

Copy, tags, price, imagery and disclosure are drafted and pass their gates for all 7 releases.

The listings are not certified for search: the category and attributes need the Etsy taxonomy.

## Fix made (executable company work)

**`88b240e`: the creative gate now judges the engineered Launch-0 products.**

**The defect.** `creative.audit.audit_catalogue` judges only `products/builder.py` designs. The
baskets and the coaster set are engineered in `products/vessels.py` and `products/launch0.py`, so
the creative audit never judged them. As a result, `dashboard_truth.launch_inventory` failed 4 of
the 7 certified releases on `creative_gate_survivor`. This had two effects:

- the opening grid showed only 3 certified tiles;
- the launch-readiness item `storefront_preview` was blocked as company work ("a phone's first
  screen needs 4").

**The fix.** These products are now their own cohort (`launch0_engineered`). They are judged by the
same jury, against the briefed builder catalogue. Each has a moment-first brief, validated by the
same `emotional_brief.validate`. The brief claims nothing about stiffness or lying flat. Survival
means `needs_taste` and never `approved`. The legacy KPI count is unchanged.

**Tests.** `tests/test_w4_launchready_engineered_cohort.py` (8 tests) checks four things:

- without its brief, the same jury still rejects each product;
- a brief that claims imagery the fabric does not carry, or that uses the default answer, or that
  contains social proof, is refused;
- a recolour of a catalogue design still dies of sameness;
- the jury thresholds are unchanged.

**Result on the scratch chain.**

- Launch-cleared releases went from 3 of 7 to 7 of 7.
- `storefront_preview` went from build-blocked to ready.
- Launch-readiness company items went from 7 to 4.

**Regression tests run, all passing.** test_w4_creative_brief, test_cert_dashboard,
test_fin_truth_closure, test_r2_product_store_lint, test_storefront_fb4, test_v11_store_foundation,
test_w3_k7_ops_truth, test_w4_b2close, test_launch, test_creative, test_improve_handlers.

## Exact remaining blockers

### Per release (all 7)

| # | blocker | gate | who must act | class |
|---|---|---|---|---|
| 1 | Search category and attributes need a stored Etsy seller-taxonomy snapshot | F-004/F-005 search certificate | Owner supplies the Etsy app keystring (read-only `GET /seller-taxonomy`); then `listing.taxonomy_refresh` is company work | external, then owner credential |
| 2 | Pattern PDFs live on non-durable storage | first_customer fulfilment_and_download; readiness `artifact_storage` | Owner approves object storage (≤CA$5/month, 10 min) | owner approval |
| 3 | No physical sample is bound to the content (size claims UNRESOLVED; risk class B needs partial physical evidence) | first_customer gauge_and_size_claims; `risk_based_physical_evidence` | Owner approves a tester commission (≤CA$32.40 per basket swatch; `tester_outreach` batch ≤CA$185); then an external tester makes it | owner approval, then external |
| 4 | Parity: `hero` needs a vision description and `competitive_blind_review` needs observed benchmark galleries; frames not independently reviewed (#61) | publication_authority parity (#75) | Owner funds model credits (≤CA$25) to open `image_vision`; benchmark observation is data | owner approval, then data |
| 5 | Etsy remote state has never been confirmed (image upload and 8 other claims) | first_customer etsy_remote_state | Needs a live shop and credential; then a controlled `etsy_exercise` round trip | external (shop) |
| 6 | Policy sources have never been read (Etsy refuses automated retrieval) | publication_authority policy | Owner reads and pastes the 6 policy pages through `scripts/record_policy.py` | owner action |
| 7 | Sealed owner publication grant per release (D-FB-10) | publication_authority approve | Owner | owner approval |

### Launch-wide

| blocker | who must act | class |
|---|---|---|
| Etsy shop and identity verification (`etsy_shop`), payout and tax details (`payout`), listing fees (≈CA$1.96) | Owner | owner (KYC, banking, spend) |
| Phase move out of shadow (`phase`), one step at a time | Owner | owner approval |
| `catalogue_depth`: 5 products, while the threshold is 8 (D-FB-9 open decision; Launch-0 is capped at 5 by tests) | Owner decides: keep 8, or set a Launch-0 depth | owner decision, not company work |
| `storefront`: the owner's canonical banner fails `nav_categories_truth` (its baked-in nav names empty categories), and its photorealism, AI-disclosure, product-truth and visible-text gates are UNKNOWN | Owner (the banner is owner-approved and must not be altered here); the judge needs model credits | owner |
| `brand_clearance` trademark (≤CA$460) and `benchmark_challenge` (≤CA$300) | Owner | owner spend |
| `sustainable_economics`: 0 days of AI/API cost history (14 needed) | Accrues once model calls run | data |
| `final_master_closure`: 9 launch-critical rows OPEN (F-169, F-834, F-839–F-841, F-845, F-846, F-848, F-878) | Other W4 lanes | company work (other lanes) |
| `off_device_autonomy_proof` (#195): a 24-hour production window | Owner authorises the deploy window | owner approval |

## Catalogue floor: three products added (BRANCH ONLY: `claude/w4-LAUNCHREADY`, not deployed)

> **Branch-only.** Nothing below exists in production. These products are drafted in a
> scratch shadow database only; nothing has been published and no owner grant covers them.

`catalogue_depth` (8 products) turned out to be company work. Launch-0 is now these 8 products
(10 releases), drafted on a fresh scratch shadow chain on 2026-10-11. Evidence:
`evidence_LAUNCHREADY/readiness_catalogue_floor_8products.json` and
`chain_run_catalogue_floor.json`.

**How they were chosen.** The repo's own demand evidence decided the order. It came from three
places:

- `radar.opportunity.score_concept` on 2026-10-11;
- the radar POOL families;
- the #297 seasonal window.

The candidates were limited to designs that already compile clean and survive the creative gate.
This used demand intelligence only: no competitor instructions, charts or photographs.

| new product (release) | version / release | why | price (basis) | bundle fit |
|---|---|---|---|---|
| **Nordic Forest Relief Baby Blanket** (`nordic-forest-mosaic-throw-baby`) | 1.3.0 / 01679f95e4dd | Nordic Forest is the top radar concept (0.761). The Christmas window has 27 days of runway. Children's category: baby_blanket under 3, with the full statement set. | CA$7.50 (SOURCED blanket band; deliberately below the floor, as for Cloudline) | nordic-forest family with the snowflake ornaments |
| **Diamond Lattice Placemat Pair** (`mosaic-placemat-pair`) | 1.3.0 / b2cd736f0f34 | radar 0.621; evergreen; a housewarming gift in the collection's cream and wine | CA$5.00 (SOURCED cluster) | housewarming table set with the coaster set |
| **Housewarming Key Basket** (`housewarming-key-basket`) | 0.1.0 / 142b52f0f9c6 | Moment-first housewarming design (W4-PIPE2), in the basket category | CA$5.50 (SOURCED cluster) | housewarming table-and-hall set |

**Gate results.** Every new release has the same gate profile as the first five:

- **PASS:** certification, Product Truth, originality, US+UK PDFs (10/10, 7/7 and 7/7 pages),
  terminology, reverse compile, licence and safety, listing claims, disclosed imagery (structural
  PASS plus a valid listing-set certificate), listing set, disclosure, rollback.
- **Seasonal window:** launch.
- **Listing draft:** present, 13 tags each.
- **Remaining blockers:** the same owner and external ones as the first five (taxonomy, storage,
  physical sample, parity/image_vision, Etsy remote state, policy, grant).

**Launch-wide effect on the scratch chain.**

- `catalogue_depth` (8 products with listings) and `storefront_preview` (≥4 certified tiles) are
  now **ready**.
- The remaining build-class items are `storefront` (the owner's banner), `sustainable_economics`
  (data) and `final_master_closure` (other lanes).

**Fixes made to get there. No gate was changed.**

- `publish.abbreviations.stitch_key`: a document that spells the slip stitch two ways now defines
  both. The key basket's `slst` op and the joined-round line's `sl st` both appear; before, the
  printed key defined only the first, and the unchanged completeness check refused the PDF.
- Registry wiring:
  - `launch0.BUILDERS` and the `Candidate` records for the three products;
  - `runtime.pipeline.ENGINEERED` for the baby size;
  - engineered-cohort briefs for the baby blanket and the key basket.
- `seo.strategy`: query families, 13 tags and a buyer-first title for each new product. Every
  phrase passed `seo.truth.check_term`; refused phrases were dropped. `strategy.plan()` is ok for
  all 8 products.
- Scope tests: the Launch-0 cap moved from 5 to the readiness floor of 8 (still a cap). These
  three tests were updated:
  - `test_launch0`
  - `test_w4_pipe_launch_promotion`
  - `test_r2_product_catalogue_depth`

  Product-count expectations went from 5 to 8 in the store, preview, SEO and gallery tests. Each
  new card or frame was checked VERIFIED, and every new gallery job measured.

**Tried and dropped on a gate, not tuned.**

- **pet-snuggle-mat:** its CIR names no product-type family (LISTING_PRODUCT_TYPE_UNSUPPORTED).
- **spooky-garland:** misses the #297 window (pivot to evergreen), and the renderer cannot draw an
  assembled garland.
- **valentine-heart-garland:** the same renderer refusal.
- **cottage-wall-hanging:** fails the 340 px legibility check at 22% fill.
- **Nordic Forest throw:** the cream is not visible in the scale frame at 340 px.
- **Nordic Forest large size:** misses the #297 window (simplify to a quick make).
- **harvest-table-runner:** Thanksgiving (CA) falls on 2026-10-12, so its window is gone.

**Note.** The key basket's release number is 0.1.0, its engineered version. It certifies under the
current gauge standard like the others.

## Verdict

The launch packet (`launch.packet.build`) reads **UNKNOWN**: every product has an unread or unjudged
section, namely parity and policy. Even if those were read, the verdict would be **BLOCKED**.

- **Products ready to the limit of what the company can establish: 5 of 5 (7 of 7 releases)**
  at c131f07. On this branch it is 8 of 8 (10 of 10 releases), with the catalogue floor met; see
  above. This
  covers the CIR, PDFs, Product Truth, originality, disclosed certified imagery, listing set,
  disclosure, copy, tags and price.
- **Listings ready to publish: 0 of 7.** No release clears search certification, parity, durable
  fulfilment or physical proof. Every remaining per-release blocker needs an owner action or an
  external party first.
