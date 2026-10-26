# Contract changes (F-482)

A change to a shared contract is declared here **before** it merges, with what dependants do:
pin the old version or migrate. `tests/test_w4_fmbatch1_contracts.py` pins the CIR shape
fingerprint (`brambleloop.core.contracts.fingerprint`) and refuses a pin that has no entry
below.

| date (UTC) | contract | fingerprint | change | dependants |
|---|---|---|---|---|
| 2026-10-26 | CIR (`cir.model` dataclasses) | 8265022276e81c44 | baseline pinned | none: no change |
| 2026-10-26 | listing payload (`integrations.etsy.ListingPayload`) | 655954b9510590d0 | baseline pinned | none: no change |
| 2026-10-26 | API routes (path + methods of every app route) | fdcf14772c7b1442 | baseline pinned | none: no change |
| 2026-10-26 | API routes | cac741d8d33870a0 | added GET /api/etsy/scorecard (F-549, operator-only) | additive: no existing route changed; no dependant to migrate |
