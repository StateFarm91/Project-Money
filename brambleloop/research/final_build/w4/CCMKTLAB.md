# W4-CCMKTLAB: F-684 Marketing Laboratory

Branch `claude/w4-CCMKTLAB`, based on INTEG2 `16e36ae`.

**Criterion** (registry F-684, quoted): "organic/paid growth, Share & Save, Offsite Ads, social, seasonal campaigns and experiments with hypothesis, baseline, budget, attribution and stop/scale rules."

The ledger names the owner `ad_budget` gate as the blocker. That gate governs spend, not this view. The view is buildable pre-launch, and it changes no spend path.

## What is built

`app/command_center/marketing_lab.py` adds two sections to the Insights tab: "Marketing lab: channels" and "Marketing lab: experiments".

**channels(db)** produces one row for each channel the criterion names:

- organic;
- paid (Etsy Ads);
- Share & Save;
- Offsite Ads;
- social (Pinterest);
- seasonal campaigns.

Every rule is read from the module that enforces it:

| Rule | Source |
|---|---|
| Paid caps, CAC, test-loss and refund stops, and scale floors | `paid_media.CONSERVATIVE_CAPS` and the `REFUND_RATE_ALARM` constant |
| Organic-first floors | `paid_media.economics_state` |
| Offsite fee, attribution window and threshold | `paid_media.offsite_ads_terms`, which reads policy_knowledge |
| Share & Save | `paid_media.share_and_save`. It stays UNMEASURED: no rate is assumed. |
| Pin rules | `growth.pins.state` |
| Seasonal events | `seasonal.calendar.rolling` and the #294 learning window |
| Paid state and ROAS | `ads_readiness.summary` |

**experiments(db)** produces one row per RegisteredExperiment:

- the stop and scale rules are derived from its write-once thresholds and minimum sample;
- the baseline is UNKNOWN unless `detail.baseline` was measured;
- attribution reads UNMEASURED until it is observed.

Rows are flat. The criterion's six fields (hypothesis, baseline, budget, attribution, stop rule, scale rule) lead each row, so the row renderer, which shows the first six facts, always shows all six.

No baseline is ever 0: with no traffic, every baseline is UNKNOWN with its reason. The module calls nothing that spends, proposes, enqueues or schedules, and a test asserts this.

## Tests

`tests/test_w4_ccmktlab.py` has 5 tests. The cc_mock gains a `ccmktlab insights` block, which checks that all six fields are shown on every row.

## Results
The last run was through the gate, on `16e36ae`: `test_w4_ccmktlab` passed 4/5.

The one failure was in `test_registered_experiments_show_rules_and_unmeasured_attribution`. The test's own fixture hypothesis was refused by `growth.experiments` as "a title". The fixture now uses a full hypothesis sentence. Nothing in the product code or the gate was changed. This fix has not been re-run.

## Checkpoint (2026-10-12, controlled pause)

**Status:** PARTIAL. The code is complete, but verification is incomplete.

**Rows:** F-684 advanced. The paid channel still needs owner `ad_budget` authority before it can spend; the view itself does not depend on that.

**Not run:**

- the rerun of `test_w4_ccmktlab`;
- `test_w4_ccall`, `test_v11_cc_views` and `test_v11_pwa_static`;
- the required regression set;
- the cc_mock check, including the new `ccmktlab insights` block.

**Next step:** run the following through the gate:

1. `test_w4_ccmktlab`, `test_w4_ccall`, `test_v11_cc_views` and `test_v11_pwa_static`;
2. the required set: test_vacuity, test_launch, test_cost_governance_wave2, test_search_hero_publish, test_cert_listing_frames, test_v11_autonomy_timeline;
3. the cc_mock check.

Fix any red.
