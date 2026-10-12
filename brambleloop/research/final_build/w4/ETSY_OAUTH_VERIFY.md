# Etsy OAuth: production verification (2026-10-12, production c498888)

Evidence is read-only: public `/api/audit`, `/api/etsy`, `/api/verify` on
https://brambleloop-os-production.up.railway.app. No token value was read or recorded.

| Check | Result | Evidence |
|---|---|---|
| Grant stored | VERIFIED | `etsy.oauth_started` 15:09:18Z (source command_center, owner session, handshake 2); `etsy.oauth_callback` 15:09:24Z: outcome ok, verdict ok, credential "sealed in oauth_credentials", token fingerprint ***65a30c77, rotations 0 |
| Scopes | VERIFIED | granted: listings_r listings_w listings_d shops_r shops_w transactions_r (all six requested) |
| Replay protection | VERIFIED | 15:09:37Z second hit on the same state refused: `state_replayed` |
| API key ping | VERIFIED | `/api/etsy` last_probe ok, application_id 1516181443672 |
| Shop ID resolved / associated with BrambleloopStudio | NOT YET | `ETSY_SHOP_ID` is not set in production; `Credentials.from_env` requires it, so every authenticated read reports "no Etsy credentials" (shop_snapshot, listing_census 00:26Z). Public shop page is anti-bot protected (403), not bypassed. Fix in progress: branch claude/w4-ETSYSHOPID resolves the shop from the owner's own grant (users/{id}/shops, shops_r) and binds only shop name BrambleloopStudio. |
| Authenticated shop/listing reads | NOT YET | blocked on shop ID (above) |
| Order reads (transactions_r) | SCOPE VERIFIED, READ NOT YET | scope granted; first read waits for shop ID |
| Token refresh | NOT YET EXERCISED | rotations 0; first refresh happens on the first authenticated client build (stored refresh token, expiry 0 forces refresh), persisted by compare-and-set |
| SHADOW, nothing published or modified | VERIFIED | `/api/verify` phase_is_shadow true; nothing_published: store.published 0, listings_with_etsy_id 0; `store.published` audit 0 rows |

## Requirement rows whose owner gate this clears (status moves from owner-blocked to company work; NOT complete)
- `oauth_transactions_r` gate: Build 2 #11, #12; Final Master F-273, F-283, F-501, F-507, F-512, F-535, F-538,
  F-558, F-570, F-574, F-575, F-590, F-595, F-657, F-682, F-872 (18 rows).
- `etsy_credential_403` gate (API key accepted since 2026-10-12T02:05Z): F-437, F-540.
Each row still needs its own acceptance evidence (authenticated reads, order reads) after the shop-ID fix ships.
