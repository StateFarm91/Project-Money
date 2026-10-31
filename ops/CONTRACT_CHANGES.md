# Contract changes (F-482)

A change to a shared contract is declared here **before** it merges, with what dependants do:
pin the old version or migrate. `tests/test_w4_fmbatch1_contracts.py` pins the CIR shape
fingerprint (`brambleloop.core.contract_pins.fingerprint`) and refuses a pin that has no entry
below.

| date (UTC) | contract | fingerprint | change | dependants |
|---|---|---|---|---|
| 2026-10-26 | CIR (`cir.model` dataclasses) | 8265022276e81c44 | baseline pinned | none: no change |
| 2026-10-26 | listing payload (`integrations.etsy.ListingPayload`) | 655954b9510590d0 | baseline pinned | none: no change |
| 2026-10-26 | API routes (path + methods of every app route) | fdcf14772c7b1442 | baseline pinned | none: no change |
| 2026-10-26 | API routes | cac741d8d33870a0 | added GET /api/etsy/scorecard (F-549, operator-only) | additive: no existing route changed; no dependant to migrate |
| 2026-10-26 | API routes | 0c95a60b30810b0d | added GET /api/product/{slug}/dossier (F-671, operator-only) | additive: no existing route changed; no dependant to migrate |
| 2026-10-26 | API routes | 95876e3d16e90313 | added GET /api/products/lifecycle (F-672, read-only board) | additive: no existing route changed; no dependant to migrate |
| 2026-10-26 | API routes | 97cc8307a76bcea7 | F-673: GET /api/opportunities (operator-only opportunity cards) | additive: no existing route changed; no dependant to migrate |
| 2026-10-26 | API routes | d5d77e45a60ee06d | F-448: POST /api/research/evidence (operator-only owner-supplied research evidence) | additive: no existing route changed; no dependant to migrate |
| 2026-10-26 | API routes | 4c5e4f01ca7b16dc | F-475: GET /api/evidence (operator-only internal evidence index) | additive: no existing route changed; no dependant to migrate |
| 2026-10-26 | API routes | 85e9ae1b15253cb8 | F-667: GET /api/company/departments/{key} (department workspace, read-only) | additive: no existing route changed; no dependant to migrate |
| 2026-10-26 | API routes | 887396069856321f | F-814: GET /api/marketing/constellation/{slug} (operator-only content constellation) | additive: no existing route changed; no dependant to migrate |
| 2026-10-26 | API routes | 01189a41dd61b5f9 | Review N-1: GET /api/finance/owner (operator-only); owner_view removed from public /api/finance | additive: no existing route changed; no dependant to migrate |
| 2026-10-26 | API routes | 556ba71935bfe4c4 | Review N-1 audit: GET /api/spend-report/governance (operator-only; learning value + adoptions moved off the public spend report) | additive: no existing route changed; no dependant to migrate |
| 2026-10-27 | API routes | 5f4aeb5f8c84b1e7 | WIRE1: GET /api/visual/studio and GET /api/visual/evidence/{slug} (F-748/F-680, operator-only); owner-session GET /api/cc/visual/studio, /api/cc/visual/evidence/{slug}; C12 owner entry under /api/cc/etsy/ (GET search-visibility, registers, listing/{listing_id}/learning-window; step-up POST search-visibility/{item_id}/remediated, listing/{listing_id}/learning-capture, registers/{register}, dashboard/kpi-snapshot, dashboard/traffic-sources) | additive: no existing route changed; no dependant to migrate |
| 2026-10-27 | API routes | 7f715ba78ff283a8 | INTEG8 merge: CLOSE6b's POST /api/ads/eligibility and POST /api/finance/ads-credit (CLOSE6 F-686/F-688) joined with WIRE1's routes; CLOSE6b added them without a row here, so they are declared now; both are operator-only under SECPATCH deny-by-default | additive: no existing route changed; no dependant to migrate |
| 2026-10-27 | API routes | 750cd12d5d99f93d | W4-READBACK: GET /api/readback/evidence (projected production evidence; authenticated ONLY by the separate read-only BRAMBLELOOP_READBACK_TOKEN via security.READBACK_ROUTES, never the operator token; closed 503 while unset). /api/verify body gains `evidence_checks` (anonymous projection: check and ok only) | additive: no existing route changed; `ok`/status of /api/verify unchanged; no dependant to migrate |
| 2026-10-27 | API routes | 7f715ba78ff283a8 | W-ADOPT (E-4): no route added or changed. New owner action `listing.adopt_manual` rides the existing owner-session POST /api/cc/actions/{action} (CSRF + nonce + step-up). New state values: `Listing.state = "published_manually"` and `DraftIntent.state = "ADOPTED_MANUAL"` (remote_id = the adopted Etsy listing id) | additive: readers of `Listing.state == "published"` do not count a manually published listing as system-published (deliberate); the census maps `published_manually` to the state read at adoption; no dependant to migrate |
