# W4-PRICEFIX: the price-plan regression in test_search_hero_publish

Branch `claude/w4-PRICEFIX` from `origin/claude/w4-INTEG2` (9fd62cc).

## The truth

`tests/test_search_hero_publish.py` failed on INTEG2 with `LISTING_PRICE_NOT_PLAN`: the
cloudline listing was CA$9.50 against a CA$7.50 plan. I re-ran the unmodified test through
`testslot` and it fails exactly that way (rc=1). The questions:

**Is the cloudline plan of CA$7.50 sourced?** Yes.

- The band is the premium blanket band observed on HanJanCrochet and MJsOffTheHookDesigns,
  CA$8.47–11.65, recorded in `radar/market.py`.
- The proposal is CA$7.50, deliberately below the band floor. The candidate gives the reason:
  no video and no review history yet.
- `commerce.pricing` decides it, and `launch_price.within_plan_band` is True.

**Is CA$9.50 the same unsourced `DEFAULT_BAND` ceiling as the placemat's?** No. It is a
constant written into the test fixture.

- `_chain()` called `listing.seo` directly with `price_cad: 9.5`. That skipped
  `pricing.position`, which is the only stage that sets a price.
- For a Launch-0 product, the release path never produces CA$9.50: `pricing.position` prices
  it from its plan (PT-04). A fresh scratch chain run gives CA$7.50 for cloudline and CA$5.00
  for the placemat (W4-PLACEMATPRICE evidence).

So the fixture's price was false: it does not match what the release path produces. The test's
subject is search-certificate and publication mechanics, not price.

## The fix

**Fixture only.** The fixture now hands `listing.seo` the price the release path gives:
`launch0.launch_price(SLUG)["price_cad"]`. It asserts that the plan is within its band.

**Not changed:** the gate, and every assertion in the test.

- The test still asserts exactly one Etsy draft.
- Its negative cases still refuse with zero requests.

## Sweep

**Production Launch-0 listings.** Read from `/api/catalogue` on 0417f35 and compared with each
plan:

| listing | price | plan | result |
|---|---|---|---|
| cloudline 1.2.0 | CA$7.50 | CA$7.50 | match |
| nordic-star-ornaments 1.4.0 | CA$4.50 | CA$4.50 | match |
| **mosaic-placemat-pair 1.3.0** | CA$9.50 | CA$5.00 | **drift** |

The placemat is the only drift. It is fixed through the release path in
`claude/w4-PLACEMATPRICE` (c1a56f0): `chain.rebuild` re-prices it, verified on a real scratch
chain.

The superseded 1.0.0 listings of cloudline and nordic-star also match their plans. The other
Launch-0 releases have no production listing.

**Tests that publish, or check the publish gates on, a listing with a stored price.** Each was
run through `testslot` and its log checked for `LISTING_PRICE_NOT_PLAN`. Results are in the
table below.

| test (base) | rc | LISTING_PRICE_NOT_PLAN in log |
|---|---|---|
| test_search_hero_publish (unmodified, 9fd62cc) | **1** | yes (cloudline 9.50 vs 7.50) |
| test_search_hero_publish (fixed, 9fd62cc) | 0 | 0 |
| test_search_hero_publish (fixed, merged with 16e36ae) | 0 | 0 |
| test_vacuity (merged with 16e36ae) | 0 | 0 |
| test_acceptance_gates, test_cert_commerce, test_cert_culture_teardown, test_cert_intel_wave2, test_cert_orders, test_cert_parity_copy (9fd62cc) | 0 each | 0 each |

## Checkpoint (owner controlled pause, 2026-10-12)

**Status:**

- **Fix: DONE.**
- **Sweep: PARTIAL.** Production Launch-0 listings were swept in full; only the placemat drifts,
  and W4-PRICEFIX together with W4-PLACEMATPRICE covers it. The test sweep was not completed.

**Not run (stopped at the pause):**

- test_launch, test_cost_governance_wave2, test_cert_listing_frames,
  test_v11_autonomy_timeline (the remainder of the required set);
- sweep files: test_cert_wiring, test_disclosed_certified_upload, test_etsy, test_fb4_launch,
  test_launch0_listing_truth, test_shadow, test_w4_fm2_storefront_trust,
  test_w4_cap1_placemat_price.

**Known, not from this branch:** on 16e36ae, `test_launch` fails with `hero: 340 px legibility
['2 piece(s) read at 340 px where the pattern makes 1']`. That was seen on W4-AESTHETIC, whose
diff is unrelated; whether clean INTEG2 fails the same way has not been checked.

**Next executable step:** run the not-run list through testslot on this branch (head after
merge 72a0b76), then hand to the integrator.
