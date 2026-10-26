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
