# W4-PRODUCT: Launch-0 product fixes and the end-to-end chain (2026-10-11)

Branch `claude/w4-PRODUCT`, based on production `0417f35`. Nothing was deployed, published,
written to Etsy or Railway, or paid for. The phase stays SHADOW. No gate, threshold or existing
test assertion was changed.

## What was brought over from `claude/w4-LAUNCHREADY`

| prior commit | here | what |
|---|---|---|
| `88b240e` | `eae54cd` (cherry-pick) | Creative gate judges the engineered Launch-0 products (baskets, coaster set) as their own cohort, `launch0_engineered`. Before this, 4 of the 7 certified releases could never be creative-gate survivors. |
| `94fe81b` | `2df68d4` (cherry-pick) | The PDF stitch key defines every spelling of a stitch the document uses (`slst` and `sl st`). |
| `2e45132` | `ca99abd` (re-done as a proposal) | The three catalogue-floor products are prepared but **not** in Launch-0. See below. |
| `0bb3cdc` | tool only | `launch_readiness_run.py` (a read-only per-release reader). |

**Not brought over: the Launch-0 cap change from 5 to 8, and the edits to existing test
assertions that went with it.** The decision log records the cap as an owner decision (D-FB-9).

## Fix 1: the catalogue-floor proposal is ready for a one-line approval (`ca99abd`)

Three products are prepared in `products/launch0.py`:

- `nordic-forest-mosaic-throw-baby`
- `mosaic-placemat-pair`
- `housewarming-key-basket`

Their supporting data is held in proposal registries, separate from the live ones:

- `PROPOSED_CANDIDATES` and `PROPOSED_BUILDERS` in `products/launch0.py`
- `creative.emotional_brief.PROPOSED_ENGINEERED_BRIEFS`
- `creative.audit.PROPOSED_ENGINEERED_MOTIF`
- `runtime.pipeline.PROPOSED_ENGINEERED`

Each of these is merged into its live registry only when
`products.launch0.CATALOGUE_FLOOR_APPROVED` is `True`. It is `False` today.

The proposal is buildable and measurable now:

- `cir_for` resolves the three builders.
- `proposed_candidate(slug)` returns their candidate records.
- `audit_launch0_engineered(proposed=True)` judges the two engineered products with the
  unchanged jury. It judges them against the briefed catalogue **and** the Launch-0 products, so
  a recolour of a product already in Launch-0 still fails.

The proposal is also kept out of everything live. It is absent from:

- `LAUNCH0_SLUGS`, `CANDIDATES` and `BUILDERS`
- `ENGINEERED`
- the launch scope
- `launch_price`

The SEO families, tags and titles for the three are stored as lookup data that nothing reads
until the products are approved.

`tests/test_w4_product_catalogue_floor_proposal.py` has 13 tests, all passing. They cover:

- Launch-0 has not changed.
- Approving the proposal brings the count exactly to `MIN_LISTINGS_TO_OPEN` = 8.
- Product Truth passes and certification is granted for every product.
- The fingerprint `_engineered_cir` would build matches each product's own CIR.
- Listing identity, price plan, children's audience, the four first-customer document areas,
  the creative cohort (`needs_taste` only; the placemat survives the builder audit) and SEO
  traceability all hold.
- The stitch-key behaviour from `94fe81b`.

### Proposal for the owner (CAP-1)

- **Action:** decide whether Launch-0 opens with 8 products (the readiness floor) by adding
  these three, or set a separate Launch-0 depth.
- **Why it is yours:** D-FB-9 records this as your decision. `catalogue_depth` reads 5 of 8 and
  stays blocked until you decide.
- **Cost:** CA$0. The Etsy listing fees apply only at publication, roughly CA$0.27 per listing.
- **Time needed:** about 5 minutes.
- **If you wait:** `catalogue_depth` stays blocked. Nothing else is affected.

If you approve, these are the changes:

1. In `launch0.py`, set `CATALOGUE_FLOOR_APPROVED = True`.
2. Raise the cap in `test_launch0.test_launch0_is_small_and_every_item_is_reachable` and in the
   `test_w4_pipe_launch_promotion` `cap_unchanged` check (5 → 8).
3. Update `test_launch0.test_a_childrens_title_with_no_audience_assignment_is_reported`. Its
   fixture must also drop the baby candidate, because that candidate now assigns itself.
4. Add the two new survivors to the expected lists in `test_w4_launchready_engineered_cohort`.
5. Re-measure the product-count expectations listed in `2e45132`: store foundation and
   preview, B2 canonical assets, SEO learning and strategy, store UX.
6. Invert `test_w4_product_catalogue_floor_proposal.test_the_proposal_is_not_launched...`.

## Fix 2: D-W5-7 — the radar and Launch-0 name the same products differently (`084d6d6`)

The radar scores two products under different names than the ones Launch-0 sells them under:

| radar concept | Launch-0 product slug |
|---|---|
| `market-basket-trio` | `market-basket-small`, `market-basket-medium`, `market-basket-large` |
| `hexie-coaster-set` | `hexagon-coaster-set` |

PT-11 already routes radar → Launch-0. Nothing routed back. So any code that looks the radar up
by product slug found nothing, with three effects:

1. The teardown product class fell back to the slug itself.
2. The #168 benchmark challenge filed 4 of the 7 Launch-0 releases as `uncategorised`, so they
   were never challenged.
3. Storefront tiles showed UNMEASURED strength instead of the radar score the product was
   promoted on.

**The fix.** `launch0.radar_concept_for` returns the radar concept for a Launch-0 product slug.
It matches exactly against `LEGACY_DUPLICATES` (no prefix matching, which is what caused PT-01)
and renames nothing. `pipeline.product_seed` uses it for the code that looks products up:

- the certification teardown class
- the #168 readiness check
- the storefront tiles

`release._seed_for` falls back the same way. `pipeline._seed_for` is still exact for drafting,
because there it decides whether a payload must pass the pre-engineering gate.

**Measured on the scratch database:** the benchmark challenge now covers the categories baby,
**basket**, **coaster**, graphghan and ornament.

`tests/test_w4_product_registry_keys.py` has 4 tests, all passing.

## The end-to-end chain on a scratch database, in shadow

The run used `research/final_build/w4/product_e2e_run.py <scratch> --as-of 2026-10-11`. Outbound
network was closed, no credentials were present, and the run took 706 s. The evidence is in
`evidence_PRODUCT/e2e_launch0_chain.json`.

The chain ran: `radar.scan` (11 concepts selected) → `radar.score` → `cir.draft` → `cir.compile` →
`gate.certify` → `listing.draft` → `assets.build` → `pricing.position` → `listing.seo` →
`launch.plan` → `store.publish`, then `launch.readiness`, `marketing.schedule` and `gate.lanes`.

Two scope notes:

- The 7 selected radar scores for concepts outside Launch-0 were cancelled as out of scope.
- `hexie-coaster-set` (score 0.614) was **not** selected by the 10-slot scan. It was scored on
  demand and is reported that way.

| chain step | result for all 7 Launch-0 releases |
|---|---|
| trend | **UNMEASURED.** The scratch DB has no stamped trend evidence, so the discount is 1.0 and the score rests on the concept's own priors. It is not invented. |
| opportunity | **Promoted** (pre-engineering gate exempt as established). Scores: graphghan 0.732, cloudline 0.676, baskets 0.643, ornaments 0.628, coasters 0.614. |
| product | `cir.draft` routed the aliases to the Launch-0 slugs: `market-basket-trio` → S/M/L and `hexie-coaster-set` → `hexagon-coaster-set`. All 7 product rows were created. |
| CIR / certification | **PASS.** All 7 certified with the certificate granted and nothing withheld. Release hashes match `LAUNCH_READINESS_c131f07`. |
| Product Truth | **PASS** on all gates. `twin.calibrated` is False everywhere. |
| listing preparation | **Done.** Draft, 13 tags, prices CA$4.00–7.50. Listing set, disclosure and rollback PASS. 59 content pieces written, none published. Stale artefacts: 18–19 per release, all fresh. |
| owner boundary | `store.publish` is refused (DEAD) in shadow, and 0 owner grants exist. |

The owner boundary refusal has these causes:

- **search FAIL:** no Etsy taxonomy snapshot is stored.
- **parity UNKNOWN:** blocked on `image_vision` and benchmark observation.
- **policy UNKNOWN**
- **gauge/size UNRESOLVED:** no physical sample is bound to the content.
- **Etsy remote state UNVERIFIABLE**
- **fulfilment FAIL:** the artifact store is not durable.

Launch readiness: 16 of 33 requirements are ready. The chain is complete up to the owner
boundary.

## Remaining gaps, and whose they are

Every per-release blocker below needs an owner or external action. They are unchanged from
`LAUNCH_READINESS_c131f07.md`.

| blocker | who unblocks it |
|---|---|
| Etsy taxonomy snapshot | owner provides the Etsy app keystring |
| durable storage | owner approves (CA$5/month or less) |
| physical sample | owner commissions a tester, then an external tester makes it |
| `image_vision` credits | owner (CA$25 or less) |
| Etsy policy pages | owner reads them in |
| sealed publication grant | owner |

The launch-wide items that are not owner or external:

- `catalogue_depth`: waits on CAP-1 above.
- `storefront`: the owner's banner fails `nav_categories_truth`, and the banner is
  owner-approved, so it cannot be altered here.
- `sustainable_economics`: 0 of the 14 days of cost history it needs.
- `final_master_closure`: other lanes.

Observed and left unchanged: `gate.lanes` routes the baskets and the blanket to `neither` lane
under the lane policy's own rules. The baskets come in 3 sizes, above the fast-lane limit of 2.
This is policy, not a defect.

## Tests run (focused, one at a time, all passing)

- the two new files
- `test_launch0`, `test_w4_launchready_engineered_cohort`, `test_w3_seo_strategy`
- `test_w4_creative_brief`, `test_creative`, `test_accessibility`, `test_cert_dashboard`
- `test_originality`, `test_k9_rows`, `test_cert_benchmark_challenge`, `test_launch`
- `test_storefront_fb4`, `test_r2_product_store_lint`, `test_cert_rebuild_chain`,
  `test_products`
