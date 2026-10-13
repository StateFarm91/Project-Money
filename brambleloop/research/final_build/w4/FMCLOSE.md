# W4-FMCLOSE: Final Master company-executable rows (Etsy commerce cluster + launch-critical re-verification)

Branch `claude/w4-FMCLOSE` from `origin/claude/w4-INTEG2` 28ba6df. Stub Etsy transports only; no deploy, no
production write, no spend. Official docs consulted (F-437): developers.etsy.com webhooks page and Etsy OpenAPI
3.0.0 (ShopReceipt.receipt_type / is_shipped, ShopReceiptTransaction.is_digital), read 2026-10-12.

Test file: `tests/test_w4_fmclose_etsy.py` **20/20 pass** (testslot, 532 s).
Regression set: see "Re-verification after INTEG2 056398c merge" below. (Earlier note: NOT YET RUN at first handback (slot gate saturated by other workers; lanes A/B queued). Integrator must
run test_vacuity, test_launch, test_cost_governance_wave2, test_search_hero_publish, test_cert_listing_frames,
test_v11_autonomy_timeline + test_route_auth_default_deny, test_customer_data_auth, test_money_truth,
test_cert_orders, test_v11_accounting_*, test_v11_autonomy_orchestrator, test_v11_seo_proposals before merge.

## Etsy rows (transactions_r gate cleared 2026-10-12)

| F-id | criterion (quoted) | before | after | evidence | class | remaining blocker |
|---|---|---|---|---|---|---|
| F-512 | "Webhook/event handling includes validation, idempotency, duplicate protection, retries, storage and observability." | no receiver | criterion met in tests | integrations/etsy_webhooks.py:149 verify, :214 receive, :77 unique webhook_id, :269 summary; app/main.py:2960 route; security.py:127; tests test_f512_* (5) | A | owner: register endpoint in Etsy Webhook portal + set ETSY_WEBHOOK_SECRET; prod reading GET /api/etsy `webhooks.received>=1` |
| F-501 | "Supported Etsy events feed a durable, idempotent business-event layer after authenticated integration is proven." | poll only | met in tests | receive enqueues commerce.orders_ingest keyed etsy.webhook:<id>; test_f501_verified_events_feed_the_idempotent_order_layer | A/B | prod: first authenticated receipt read after shop-ID binding (hotfix) — audit commerce.orders_ingested ran:true |
| F-570 | "Track Offsite Ads attribution, fee rate, 30-day attribution behavior and the shop's 365-day revenue threshold/participation status. Recompute contribution margin on attributed orders." | unread read as 0 % (defect) | defect fixed, met in tests | commerce/paid_media.py:425,441; runtime/growth_ops.py:408; test_f570_* (3) | A | prod: real ledger read (ledger_type mapping unverified) |
| F-574 | "Compare organic Etsy search, Etsy Ads, Offsite Ads, social and Share & Save at listing/product-family level. One order cannot be double-credited to multiple channels internally." | none | met in tests | finance/channel_comparison.py:52,91; growth_ops.py:462; test_f574_* | A | none (data accrues with sales) |
| F-590 | "Inventory every enabled Etsy sales channel/integration and its effect on listings, inventory, payments, customer data and attribution. New channels require explicit readiness." | no runtime inventory | met for receipt-observable channels | commerce/sales_channels.py:25,86; orders_ingest receipt_type; test_f590_* | A | SELL_ON_FACEBOOK listing flag not yet read from the live shop (listing_census) |
| F-595 | "Treat the first ten sales as a protected learning cohort: inspect search source, conversion path, questions, download/support friction, reviews/refunds and economics after each sale without destabilizing listings with constant edits." | none | mechanism built + tested | commerce/first_ten.py:69,125; seo/proposals.py edit_hold; test_f595_* (2) | C | needs real sales (criterion literally requires them) |
| F-657 | "orders, messages, reviews, refunds, Etsy events, policy changes, incidents, spend anomalies, research signals, schedules and owner decisions wake the appropriate team." | cadence polling only | met in tests | autonomy/event_wakes.py:41 ROUTES, :133 scan; autonomy/handlers.py:46; test_f657_* (2) | A | prod reading: autonomy.orchestrate output `event_wakes` |
| F-682 | "show last reconciliation, discrepancies, close status, tax/threshold alerts and evidence; never silently force mismatches to zero." | partial | met in tests | finance/accounting/activity.py:54; dashboard.py:242; test_f682_* (2) | A | none |
| F-283 | "Record first-sale source honestly (organic Etsy, Etsy Ads, Offsite Ads, owned/direct, unknown). One sale proves possibility, not scale." | no evidence route | met in tests | POST /api/orders/attribution app/main.py; test_f283_* | A | none (first real sale is data) |
| F-558 | "For every order, reconcile payment, item/version, digital delivery state, buyer issue, refund/cancellation/case state and downstream accounting evidence." | no delivery state, no per-order ledger | met in tests | commerce/order_ledger.py; GET /api/orders/ledger (operator); test_f558_* | A | prod: first real receipt |
| F-575 | "Reconcile Etsy Payment Account entries to orders, fees, refunds, credits, ads, subscription charges and payouts. Unexplained balance movements create finance incidents." | partial | unchanged in code (an ingest->statement-lines wiring was tried and REVERTED: it fed the Accountant's external statement set from the same read that sets order fees and broke test_v11_accounting_reconciliation); unexplained movements -> incidents shown in F-682 view | test_f575_unexplained_ledger_movements_are_incidents_and_shown_to_the_owner | A/B | payout reconciliation needs a separate statement source (Etsy payments/payout read) + real ledger read to verify ledger_type mapping |
| F-538 | "Reconcile Etsy orders, fees, taxes/remittances, refunds, credits, ads/subscription charges and payouts against Brambleloop's ledger. Unknown fee behavior remains explicit until proven by a real settlement." | partial | open (F-575 wiring reverted) | as F-575 | B | real settlement |
| F-273, F-507, F-535, F-872, F-437, F-540 | (see FM_LEDGER) | existing code | not re-run (lane B queued) | existing tests listed in FM_LEDGER | A/B | F-872: authenticated receipt readback; F-437: POST /api/etsy/exercise authenticated; F-540: production rotation (rotations>=1) |

## Launch-critical rows
Software for F-027/031/041/252/253 (FIRSTIMG/HEROVISION/THUMBFLOORS), F-100/871 (FUNDING), F-144/171 (SMOKE),
F-380/381 (ROLLBACK), F-718/733 (PROVENANCE/CONDPACK) is merged; re-run here: test_w4_smoke 10/10,
test_w4_funding 5/5, test_w4_thumbfloors 7/7. All remain class B: they close on production readings after the next
approved deploy (ops/readback.py exit 0; /api/verify/smoke 200; /api/model-identity approval_record.state MATCH;
visual.hero_review rows identified=True per Launch-0 hero; 24 h off-device proof PROVEN for F-371/495/654/701/849/880/881/895/923/924).
F-834/F-845/F-846/F-878: integrator decisions (see PROVENANCE.md, OVERRIDES_PROPOSED_FMGATE.json). F-278/F-746/F-897: owned by
HEROTOURNEY/SETCONSIST/CCNOTIFY. F-848: owner CAP1.

## Re-verification after INTEG2 056398c merge (4776ba8)
Root cause of the integrator's test_v11_accounting_reconciliation failure: my ingest->`import_etsy_ledger` wiring
filled the Accountant's external Etsy statement set from the same ledger read that sets order fees (extra lines
70001-70004). Reverted; test unchanged. Results (testslot, N=1): v11_accounting_reconciliation 7/7, _controller 9/9,
_drill 5/5, _ledger 10/10, _money 9/9; fmclose_etsy 20/20; cert_orders 23/23; finance 21/21; vacuity 8/8; launch 28/28;
cost_governance_wave2 39/39; search_hero_publish 4/4; cert_listing_frames 6/6; v11_autonomy_timeline pass (rc 0);
money_truth: see handback.
