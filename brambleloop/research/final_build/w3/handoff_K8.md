# Wave-3 lane K8 handoff: Etsy estate, orders and CX (13 rows)

Branch `claude/w3-K8`. Its base is `claude/v11-CANON` @ f0c2d12. The phase stays shadow throughout this work:

- nothing writes to Etsy;
- nothing is sent to a buyer;
- no paid call is made;
- no new ORM table is added (everything persists in `audit_log`, `operating_readings`, `incidents`, `owner_actions`, or the `detail` JSON on existing rows).

Every Etsy-shaped proof runs against `tests/fake_etsy.py` through the real handlers, using `Worker.run_once`. Real data stays gated:

- orders and refunds need the owner's `transactions_r` re-authorisation;
- the estate, drift and delivery checks need live listings on the real shop;
- a rollback write needs `production_window`, the owner's `OwnerGrant`, and `listings_w`.

## Per-row status

| Row | Status | Evidence (test → consumer) |
|---|---|---|
| **F-553** Listing estate manager | COMPLETE | `test_census_estate_rows_carry_files_images_properties_expiry_and_fee` → `etsy.listing_census`, which now stores `listing_estate.estate_row`. Each row records state vs intended state, family, taxonomy, properties, images, files, expiry, days left, renewal mode and fee. The fee basis is labelled *modelled*. |
| **F-544** Live drift: images and files | COMPLETE | `test_a_customer_file_removed…`, `test_an_image_removed_on_etsy_is_drift` → census `asset_audit`. Drift opens the existing halting reconcile incident and is never overwritten. The tests assert that no non-GET request is made. |
| **F-559** Daily digital delivery verification | COMPLETE | Same tests, plus `test_an_unreadable_file_list_is_unverified_never_verified`. Each day the census re-reads `getAllListingFiles` and checks every US/UK variant by name and exact size against the verified publish's `files_sent`. A failed read is UNVERIFIED. Post-purchase availability is stated as *inferred* from the attachment, because Etsy has no buyer-download API. |
| **F-250** Recency non-gaming | COMPLETE | `test_renewal_rule_now_has_a_caller…`. `release_gates.renewal_decision` now runs on every census. A recency renewal opens `etsy.renewal_refused:<id>`. An expired listing opens `etsy.listing_expired:<id>` as a proposal, which is never executed. |
| **F-545** Listing lifecycle audit trail | COMPLETE | `test_the_trail_unifies…`. `listing_lifecycle.record/trail/test_listings` uses the append-only `audit_log`. It reads legacy publish, activation and exercise rows into one shape and reports stranded test listings. The census writes `observe_drift` rows and stores the `etsy.listing_lifecycle` reading. Legacy producers were not rewritten, so legacy create rows carry no "before" state. |
| **F-518** Safe rollback | Plan COMPLETE; execution GATED | `test_a_title_edited…defined_rollback_plan…`, `test_rollback_refuses_in_shadow…`, `test_rollback_with_every_condition_clear…`. Every drift incident carries a `rollback_plan` with the restore and 4 stop conditions. `listing_rollback.execute` refuses in shadow, without a grant, or on a stale fingerprint, and it reads back afterwards. It is proved only with a fake client. Gate: `production_window` + `OwnerGrant`. There is no live job type yet. |
| **F-537** Shop policy consistency | COMPLETE | `test_policy_text_matching…`, `test_a_contradiction…`, `test_the_shop_snapshot_opens_and_closes…` → `etsy.shop_snapshot`. Each live policy field is checked against its one canonical source, and the FACT contradiction patterns are applied. The result opens `etsy.shop:policy_inconsistent`: P1 on a contradiction, P2 on wording drift. It does not halt. |
| **F-585** Shop options registry | COMPLETE (browser-only half needs W1) | `test_options_registry…`. There are 8 controls, each with value, desired state, consequence and owner authority. The registry detects DRIFT, CHANGED, and changes to the page's labels (Etsy UI changes). It runs in the snapshot and opens `etsy.shop:options_drift`. |
| **F-592** Shop security posture | COMPLETE (apps and shared-access readings need W1) | `test_security_posture…`, `test_credential_health_carries_the_posture…` → `etsy.credential_health`. It checks for scopes that were added, unexpected or removed, and for a credential replaced outside a refresh (masked fingerprint plus rotation counter). It also covers rotation age, callback config, apps and shared access, and raises `etsy.security:posture`. The tests assert that it never echoes credentials. |
| **F-514** Etsy surface inventory | COMPLETE for re-verification; serving needs W1 | `test_the_inventory_is_served…`. The snapshot stores the `etsy.surface_inventory` reading daily: held scopes vs declared API access, plus collector and observation freshness. Every surface named in F-514 is covered, each with an api / browser_only / owner_only / unsupported / n/a channel. There is a provider-shaped `surface_inventory.summary(db)`. |
| **F-568** Policy violation incident system | COMPLETE (owner intake needs W1) | `test_policy_violation_items_become_ranked…`, `test_a_violation_past_its_deadline…`. Each item gets a severity (P0 account, P1 IP or removal, P2 warning), plus halting, the source text, the listing, the deadline and its basis, the remediation owner, a legal-review owner action, and the closure proof. A complete, empty reading closes the item and also the earlier census `policy_violation_suspected:*`. The live daily consumer is `escalate_overdue`, run inside the census. |
| **F-535** Refund and cancellation root cause | COMPLETE (fakes) | `test_refund_reasons_are_captured_at_ingest`, `test_every_refund_and_case_gets_a_code…`, `test_the_daily_order_readings_carry…` → `commerce.order_readings`. Ingest keeps Etsy's refund `reason` and `note_from_issuer`. Every refund, cancellation, case and complaint gets a code, an owner and an investigation. When the same cause hits 3 times in 90 days on one product, `cx.repeated_cause:<product>:<code>` opens. Buyer text never goes into an incident. Real refunds are gated on `transactions_r`. |
| **F-689** Customer workspace | COMPLETE (operator view needs W1) | `test_the_workspace_joins…`, `test_support_mining_carries…` → `support.triage` (`mine_cases` produces `workspace`). `support.workspace.workspace` is the operator view, joined per buyer across messages, orders, reviews, refunds, risks and upstream fixes. `summary` holds aggregates only, and the tests assert it contains no buyer text or reference. The recorded defect, unauthenticated `/api/support`, was already fixed on the base: `test_customer_data_auth` passes. |

## Files

- **New** (owned paths): `commerce/{listing_estate,listing_lifecycle,listing_rollback,policy_consistency,policy_violations,shop_observations,shop_options,shop_security,surface_inventory,cx_root_cause,estate_api}.py`, `support/workspace.py`, `tests/test_k8_listing_estate.py` (9 OK), `tests/test_k8_shop_cx.py` (17 OK).
- **Modified** (owned): `commerce/orders_ingest.py` (refund reasons), `commerce/order_readings.py` (`root_cause`), `support/department.py` (`workspace` in `mine_cases`).
- **Modified outside the stated ownership:** `runtime/etsy_ops.py`. It is not in the brief's shared-file table and no lane owns it. It holds the census, snapshot and credential-health handlers, which are the only live consumers for these rows. The integrator should check for conflicts with any other lane that touches it.

## WIRING REQUESTS

- **W1 (lane F, `app/main.py`):** add these two lines beside the other routers:
  `from ..commerce.estate_api import make_router as estate_router` and `app.include_router(estate_router(db))`.
  Also add `"/api/cx/workspace"` to `CUSTOMER_DATA_ROUTES`.
- **W2 (lane F, `providers`, optional):** expose `commerce.surface_inventory.summary` and `support.workspace.summary`. Both follow the provider contract.
- **W3 (lane D, later):** add an owner-enqueued `etsy.listing_rollback` job type that calls `listing_rollback.execute`, at the `production_window` step only.

## Tests run

- K8 suites: 26/26.
- `test_etsy_readback_observe` 37/37 (after the census changes).
- Other suites: `test_rc1_order_truth` 13, `test_receipt_adversarial` 18, `test_rc1_ord2` 13, `test_departments` 28, `test_vacuity` 7, `test_secret_scan` 6, `test_etsy_surfaces` 52, `test_oauth_security_audit` 87.
- `test_cert_orders` failed 2 under parallel load and then passed 0-failing when re-run alone. I am not certain it is only load-related.
- I did not run the full suite.

## Could not verify

- Etsy's real refund `reason` field contents.
- Real Options page labels: the registry labels are our reading.
- Real Policy Violations notice formats.
- Any behaviour of the real Etsy API.
