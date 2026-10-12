# Draft creation crash durability handoff
Base5c983e4; branch codex/final-draft-durability-01.

## Problem and boundary
Remote createDraftListing previously completed inside EtsyClient.publish before any durable local listing ID; upload/process failure could retry and create another draft. This repair provides at-most-one automatic creation attempt per product/version, not external exactly-once execution. A network timeout or process death after request but before ID checkpoint is irreducibly uncertain without independent reconciliation; it never authorizes retry.

## Implementation
New additive draft_creation_intents table: unique deterministic product/version key, owner token, release, SHA256 binding of certified PDF hashes, actual image bytes/order, listing-set ID and payload, state, remote ID. Claim transaction commits before client.publish. Duplicate intent refuses with permanent reconciliation error, even when content/release changes or time elapses.
EtsyClient.publish optional on_created callback runs immediately after create_draft returns and BEFORE file/image upload. Runtime supplies token-bound transaction checkpoint that writes intent remote ID and Listing.etsy_listing_id/incomplete_on_etsy together. Callback failure aborts upload. Upload failures leave known ID durable; existing public handler refuses to create again for that Listing. No automatic resume or activation added.
Ordinary interrupted attempts additionally record P1 reconciliation incident; hard process death leaves CREATING intent, which blocks at retry and opens reconciliation. Existing capability, parity, PDF hash, release and readback gates remain in place. Activation code untouched.

## Runtime evidence
handle_store_publish -> all existing permission/parity/hash gates -> _publish_and_read_back -> committed claim -> real EtsyClient.publish method with fake remote transport methods -> create -> checkpoint -> upload -> existing readback.
New tests6/6 PASS: failure before request (conservative availability loss), remote created with lost response, callback failure after ID return, upload failure after durable checkpoint, actual public retry with known ID, file-backed database reopen, two concurrent SQLite connections exactly one claim winner, changed-release refusal, and child-process os._exit after fake remote creation followed by parent-process retry refusal. Child hard-exit proves no Python exception cleanup is required for protection.
Existing test_etsy.py17/17 PASS unchanged: phase/auth/request/refusal/hash tests preserved. No live calls; fake remote only. Runtime retry test isolates capability gates with explicit fixtures, not production certification evidence.

## Remaining limitations
PostgreSQL not available for runtime race execution; primary-key INSERT uniqueness and transactional checkpoint semantics reviewed only. Real Etsy does not provide a verified remote idempotency guarantee here. Unknown intent needs independent reconciliation; no reset/expiry/operator resolution API is invented. Even pre-request errors can conservatively park an attempt. Known incomplete draft is retained/refused, not automatically repaired. Legacy fake clients with restrictive publish signatures must implement the new callback contract to exercise this runtime seam honestly.
Root should independently audit callback/transaction boundaries and run final integrated publication suites on clean source. No COMPLETE+PROVEN claim.

## Files
core/db.py additive model registration; publish/draft_intent.py; integrations/etsy.py publish callback only; runtime/pipeline.py _publish_and_read_back only; tests/test_draft_creation_durability.py; scope and handoff.
No changes to activation, H, thresholds, statuses, production or paid APIs. $0 spend.
