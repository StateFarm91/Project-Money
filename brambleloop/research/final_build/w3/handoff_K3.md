# Wave-3 lane K3: listing-outcome intake (handoff)

Branch `claude/w3-K3` (base `claude/v11-CANON` @ f0c2d12). Phase stays shadow. No Etsy write
and no real Etsy call: the tests run against `tests/fake_etsy.py` on loopback. No spend.

## What was missing (confirmed against f0c2d12)

`ListingOutcome` had readers but no writer at runtime. `creative.style_learning.record_outcome`
had no caller outside tests. Every funnel reader (portfolio review #47, `growth.conclude`,
style and outcome learning, `seo/measure`, war room, runrate, `organic_period`) read an empty
table. `growth.conclude` did not apply the listing-test exposure rule. No optimiser checked
whether measurement had been proven.

## Rows

| Row | Status | Evidence (test, in `tests/test_k3_listing_outcomes.py`) | Runtime consumer path |
|---|---|---|---|
| F-258 Conversion Evidence Loop | COMPLETE (software); real numbers are GATED on `live_listings` (owner Stats export) and `etsy_api` (credential) | `test_the_export_is_read_strictly_and_names_only_our_listings`, `test_the_scheduled_daily_job_records_an_export_and_reads_it_back`, `test_the_etsy_api_half_is_read_only_differenced_and_never_invents_impressions` | cadence `commerce.readings` (daily, cfo) → `runtime/listing_outcomes.run` → `commerce/listing_outcomes.produce` → `style_learning.record_outcome` → `ListingOutcome`; the reading is `operating_readings[listing_outcomes.reading]` |
| F-259 Neutral New-Listing Prior | COMPLETE | `test_the_weekly_review_diagnoses_each_stage_from_the_produced_outcomes` (NO_EVIDENCE before any outcome and for an unexposed listing; the producer's stage is `UNMEASURED`) | `portfolio.review` (weekly) reads the produced rows |
| F-260 Listing Experiment Discipline | COMPLETE | `test_a_listing_experiment_with_too_little_exposure_concludes_nothing` (199 impressions: `not_tested`, no verdict written; 1,200 impressions: concludes, discipline recorded) | `growth.conclude` → `experiments.conclude_all` → `listing_discipline` → `commerce.listing_tests.exposure_refusal` (one shared rule) |
| F-261 Underperformer Remediation | COMPLETE | same review test: SEO_PROBLEM (shown, not clicked), APPEAL_PROBLEM (clicked, not saved; #13's offer guard withholds the discard), CONVERSION_PROBLEM (saved, not bought) | `portfolio.review` |
| F-282 No Zero-Sales Panic | COMPLETE | same review test: 120 impressions with zero sales gives NO_EVIDENCE; 4,000 impressions with no conversion gives a diagnosed stage | `portfolio.review` |
| F-297 Measurement Before Optimisation | COMPLETE (gate); paid half GATED on `etsy_ads` data | `test_optimisers_wait_until_measurement_is_recorded_and_read_back` (a hand-inserted row proves nothing; ads stay ineligible until both an organic and a paid intake reading are read back; the steer withholds the winner credit until organic is proven) | `ads.adjust` → `growth_ops.ads_plan` (blocker `measurement before optimisation (#297)`); `growth.steer` → `growth_ops.steer` (`measurement.winner_credit_held`) |

Also: `test_the_producer_is_registered_and_reached_from_a_scheduled_job`.

## Design (honest limits)

- **Owner listing-level Stats export.** Impressions and visits are required. Favourites,
  carts, orders and traffic source are optional. A missing column is UNKNOWN (None), and a
  blank cell is refused because blank is not zero. A `views` column with no impressions
  column is refused by name, because listing views are page views. Every row must resolve to
  one of our listings, by Etsy id, slug or exact title. `submit_export` validates the export
  synchronously and queues it in an inbox reading. The producer records it through the one
  writer, `record_outcome`, then reads every row back field by field. The result is
  `round_trip.ok`.
- **Etsy API (read-only `getListingsByShop`).** The producer differences two daily snapshots
  of cumulative `views` and `num_favorers`. The API exposes no impressions and no carts, so an
  API period is stored as a reading only, never as a `ListingOutcome` row. Writing one would
  need an invented impressions denominator. A cumulative count that falls is reported as
  UNKNOWN, not as zero. No credential means UNKNOWN, and nothing is stored.
- `measurement_status` counts only rows written by the intake (`owner_export:` source) whose
  export's round trip was ok.
- Not done: writing the disproof memory (`ListingMemory`) from `conclude_all`. The F-260
  requirement text does not ask for it, and the audit's next-action mentions it. Building it
  needs a context (pod, price band, season, maturity) for each experiment.
- The ads escalation owner-action (#295) is not gated by #297. It is a proposal to the owner,
  not automated optimisation.

## Files

- new `src/brambleloop/commerce/listing_outcomes.py` (intake, API snapshot, funnel, measurement status, producer)
- new `src/brambleloop/runtime/listing_outcomes.py` (handler `listing.outcomes`)
- `src/brambleloop/runtime/commerce_readings.py` (imports and runs the producer first; adds `listing_outcomes` to the summary)
- `src/brambleloop/growth/experiments.py` (`LISTING_METRICS`, `_window`, `listing_discipline`, exposure and window in `observe_metric`)
- `src/brambleloop/commerce/listing_tests.py` (`exposure_refusal`; `check_design` now uses it, with the same text)
- `src/brambleloop/runtime/growth_ops.py` (#297 gate in `ads_plan` and `steer`)
- new `tests/test_k3_listing_outcomes.py` (7 tests)

## WIRING REQUESTS

1. **Lane D, `runtime/worker.py` CADENCES.** Add
   `("listing_outcomes", "cfo", "listing.outcomes", 24 * 60 * 60),`. Also grant `cfo` the job
   type `listing.outcomes` in `agents/registry.py`, and add a band in
   `swarm/orchestrate.JOB_BANDS` matching `commerce.readings`. Until then, the job runs inside
   `commerce.readings`.
2. **Lane F, `app/main.py`.** Add an authenticated owner intake route, following
   `api_attribution_stats`:
   `POST /api/listing-outcomes?period_start=YYYY-MM-DD&period_end=YYYY-MM-DD`. The body is the
   CSV. The route runs `opsauth.check`, then
   `commerce.listing_outcomes.submit_export(db, text, period_start=..., period_end=...)`. It
   returns `OutcomeRefused` as 400 and the result dict as 200.
3. **Lane F (optional).** Show `listing_outcomes.latest(db)["measurement"]` and the stages per
   listing in the Command Center growth view.

## Tests run

`test_k3_listing_outcomes` 7/7. Regression tests on the modified modules: `test_listing_tests` 24,
`test_style_learning` 11, `test_cert_growth_seasonal` 24, `test_protected_bands` 6,
`test_cert_growth_ops` 13, `test_cert_orders` 23, plus `test_vacuity` and `test_secret_scan`.
All of them exit 0. The full suite was not run, because of the machine limits.

## Runtime reachability (`build2.reachability.function_reached`, C-65 rule)

- `commerce/listing_outcomes.produce` and `creative/style_learning.record_outcome` are
  reached. The path is handler `commerce.readings` (cadence) → `runtime/listing_outcomes.run`
  → `produce`. Before K3, `record_outcome` was unreached.
- `measurement_status` is reached through `growth.steer` and `ads.adjust`.
  `growth/experiments.listing_discipline` is reached through `growth.conclude`.
- `submit_export` is NOT reached until WIRING REQUEST 2 (the route) lands. The handler
  `listing.outcomes` is NOT reached on its own until WIRING REQUEST 1 lands. Its logic already
  runs inside `commerce.readings`.

## Could not verify

- Real Etsy Stats export headings. The aliases are informed guesses, and an unknown heading is
  refused by name, never guessed.
- Real `views`/`num_favorers` semantics on live listings. There is no live listing yet
  (`live_listings`, `etsy_api` gates).
