# W4-PLACEMATPRICE: the placemat is re-priced to its CA$5.00 plan through the release path

Branch `claude/w4-PLACEMATPRICE`, from `origin/claude/w4-INTEG2` (85ec5d0). Nothing is written
to Etsy or to production.

## The defect

Production holds `mosaic-placemat-pair@1.3.0` (release `b2cd736f0f34`) as a **draft listing at
CA$9.50**. That price came from the generic pricing path, before CAP-1 put the placemat into
Launch-0:

- there is no `placemat` band, so pricing fell back to the unsourced `DEFAULT_BAND`
  (CA$4.50–9.50) and took its ceiling;
- the placemat's plan of record is **CA$5.00** (PT-04).

W4-CAP1 already added `release_gates.launch_price_check`, so publication refuses this listing.
**But nothing re-priced it.** `chain.rebuild` judges a listing current by its chain version and
release hash. Both still match, so it reported the placemat "current" on every cadence, and the
CA$9.50 price would never have moved.

## The fix

The untargeted pass of `chain.rebuild`, which runs on the scheduler's cadence, now does one
more check. For a listing that is current by chain version and release hash, it compares the
stored price with the Launch-0 plan (`_reprice_on_plan_drift`). When the two differ:

1. It enqueues `pricing.position` for that release. The input is the release's latest completed
   `assets.build` output, the same measurement `_targeted_rebuild` re-prices from.
2. It is keyed by the drift itself, so each drift is re-priced once, not once per cadence.
3. It is audited as `chain.reprice_requested`.

From there the normal chain does the work:

- the Launch-0 pricing path (`_price_launch0`) prices the release from its plan, CA$5.00;
- `listing.seo` then re-drafts the listing row.

If no `assets.build` measurement exists for the release, nothing is enqueued. The skip is
audited as `chain.reprice_refused`, and publication keeps refusing the listing.

## Evidence

`tests/test_w4_placemat_reprice.py` covers these cases:

- **An off-plan listing is re-priced through `pricing.position`.**
  - `chain.rebuild` reports `repriced: [mosaic-placemat-pair@1.3.0]` and enqueues exactly one
    `pricing.position`, carrying the release and a rebuild token.
  - That job prices the release at **5.00**.
  - `listing.seo` is enqueued with `price_cad` 5.00.
  - `chain.reprice_requested` is audited with `plan_cad` 5.00.
  - In this fixture the `assets.build` payload is synthetic (no rendered frames), so `listing.seo`
    correctly **refuses** to draft (`POLICY_CLASSIFICATION`). The listing row therefore keeps
    CA$9.50 and is not on Etsy.
- **The re-price is enqueued once per drift.** A second cadence pass enqueues nothing new.
- **A listing on plan is untouched.** It is "current", and nothing is re-priced.
- **Without an `assets.build` measurement,** the re-price is refused and audited, and no pricing
  job is enqueued.

**Verified on a real release chain** (2026-10-12, after the test slots reached 3). The check is
`research/final_build/w4/placemat_reprice_check.py`, run on a scratch DB in shadow, with the
network closed. It went in three steps:

1. **Normal chain run.** `pipe_chain_run.py mosaic-placemat-pair` ran the real chain, with real
   rendered frames. The listing came out at **CA$5.00**, so a fresh Launch-0 release is priced
   from its plan.
2. **Production state reproduced.** The listing price was forced to **CA$9.50**, as in
   production.
3. **One `chain.rebuild` pass.** It recorded `chain.reprice_requested` (9.50 → plan 5.00) and
   enqueued `pricing.position`. That positioned the price at CA$5.00 (SOURCED band). Then
   `listing.seo` (DONE) re-drafted the row.

The listing row ended at **CA$5.00**, still in `draft`, with no Etsy listing id. Result:
`evidence_PLACEMATPRICE/reprice_result.json`.

**Board rows.** This is queue item (2). It hardens F-878 / PT-04 (the price of record). No
final-master row is closed by it.
