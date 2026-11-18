# Review request — `eng/e1-receipt-lessons-fix` (base 76fe0dd3, `opus2/ws6-e1-receipt-lessons`)

Code commit: `0af2e7f` (this file is committed on top of it).

## Findings → fix → test

| Finding | Fix | Regression test (fails on 76fe0dd3, passes here) |
|---|---|---|
| **M1** `official_groups` kept orders where `not o.offsite_ad_attributed`. That flag defaults False, so orders with no ledger reading counted as organic demand and could publish `commercial_demand` | `improve/commercial_lessons.py`: an order counts only when `paid_media.offsite_attribution(o) is False`. Unknown orders are counted apart (`Group.orders_unknown`, reported as `orders_attribution_unknown` with a `why`), and a category holding any is UNMEASURED: its rate would be too low if they were organic and too high if paid. An Offsite Ads fee on the ledger now also excludes an order; the old code ignored the fee | `test_e1_receipt_lessons_fix.test_m1_orders_with_unknown_offsite_attribution_never_publish_demand`, `test_m1_ledger_read_organic_orders_still_measure`, `test_m1_an_offsite_fee_excludes_the_order` |
| **LOW** views include ad-bought views without saying so | `VIEWS_INCLUDE` on the official reading (`views_include`); the lesson statement says "all sources including ad-driven views; visits UNKNOWN" and "organic receipt orders" | `test_low_views_say_they_include_ad_driven_views` |
| **LOW** the job audit hid the official reading | `runtime/commercial_ops.py` audits and returns `official` (measurable, why, shop, denominator, unknown, views_include, and per category state, verdict and unknown-attribution count) | `test_low_the_job_audit_carries_the_official_reading` (through the real worker) |
| **LOW** the views count was stored under `visits` | Official categories and shop store the count under `views`; the export basis keeps `visits`. Statement and evidence ref read the basis's own denominator | `test_low_views_are_stored_as_views_never_visits` |
| **LOW** window edges a day loose | `_view_windows` keeps each snapshot's read time (`OperatingReading.at`). Orders count between the first and last snapshot times, not from the first day's midnight to the day after the last | `test_low_the_order_window_is_the_snapshot_times_not_whole_days` |

Fixture change in `test_ws6_e1_receipt_lessons.py` (no assertion changed): `_order` now
records the ledger reading. The default `ledger_fee=0.0` means read, no fee, i.e. organic;
`None` means unread. Before M1, the suite's "organic" orders were unread orders, and F-570
says those are unknown.

## Consequence to know
Until `offsite_ads_fee_cad` is populated from Etsy's payment-account ledger, every category
with receipt orders is UNMEASURED on the official basis, so no official lesson is published.
That is the honest reading. Categories with views but no orders are unaffected.

## Suites run
`JOBS=4 SUITE_REGISTRY=0 PY=/tmp/venv/bin/python bash run_tests.sh` with SUITES = test_e1_receipt_lessons_fix
test_ws6_e1_receipt_lessons test_opus2_commercial_lessons test_opus2_knowledge_gaps:
**30 passing, 0 failing**. New suite: 7/7 here, 0/7 on 76fe0dd3.
