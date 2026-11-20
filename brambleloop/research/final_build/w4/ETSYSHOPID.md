# W4-ETSYSHOPID: bind the Etsy shop id from the owner's own grant

Branch `claude/w4-ETSYSHOPID`, based on production `c498888`. Not deployed.

## Root cause
The owner's OAuth grant succeeded on 2026-10-12T15:09:24Z (refresh token sealed in
`oauth_credentials`, six scopes). `Credentials.from_env` still returned None because it
requires `ETSY_SHOP_ID` (`if not (key and shop and (token or provider)) return None`), and that
variable is not set in production. Every authenticated read (shop snapshot, listing census,
credential-health live check) therefore said "no Etsy credentials". The public shop page is
anti-bot protected and is not scraped.

A second latent defect sat behind it: a provider built from the *stored* token started with
`scopes=()` (none in the environment), and Etsy's documented refresh response carries no
`scope` field, so after the first refresh `TokenSet.missing_scopes` would have refused every
scoped read (getMe, listings, receipts) as "missing shops_r".

## Design
- `integrations/etsy_shop_binding.py`
  - user id = numeric prefix of the access token (Etsy OAuth docs show tokens as
    `12345678.<opaque>`, the prefix being the granting user's id); fallback `getMe`
    (`GET /v3/application/users/me`, shops_r) `user_id`.
  - `getShopByOwnerUserId` (`GET /v3/application/users/{user_id}/shops`, shops_r) gives
    `shop_id`, `shop_name`, `user_id`. (Operation names from the pinned OpenAPI 3.0.0,
    sha256 b993d52f..., `seo/constraints.py`; the spec was not re-fetched here: no requests
    to Etsy from this branch.)
  - Bound only if `shop_name == store_foundation.content.ETSY_HANDLE` ("BrambleloopStudio")
    and the shop's `user_id` matches. Otherwise: nothing stored, P1 incident
    `etsy.shop_binding:mismatch`, audit `etsy.shop_resolution_refused`.
  - Success: audit `etsy.shop_resolved` {shop_id, shop_name, user_id, how, expected}; never a
    token. Resolves the mismatch incident if one was open.
  - `ensure_credentials(db, transport, phase)`: unchanged path when ETSY_SHOP_ID is set, a
    binding is stored, or there is no token; otherwise resolve, and reuse the same
    TokenProvider (no second refresh; its compare-and-set state stays current). Any failure
    is logged and yields None, i.e. the previous behaviour.
- Persistence: `oauth_store.save_shop_binding/load_shop_binding`, one `operating_readings`
  row (`kind=etsy.shop_binding`, `period_key=bound`). No schema change; that table is not
  pruned by `ops/retention.py`.
- `Credentials.from_env`: `ETSY_SHOP_ID` wins; else, with `db`, the stored binding.
  New `require_shop=False` (resolver only). Stored-token providers are seeded with the
  stored row's scopes (`oauth_store.stored_scopes`).
- `TokenProvider._refresh_now`: a refresh response without `scope` keeps the previous scopes
  (Etsy: refresh grants have the same scope as the original grant).
- `SCOPES_REQUIRED["getShopByOwnerUserId"] = ("shops_r",)`.
- Trigger: `runtime/etsy_ops.build_client` calls `ensure_credentials`, so the first
  authenticated build (and the daily `etsy.credential_health` job, which uses build_client)
  binds lazily. Other `Credentials.from_env(db=...)` callers (orders ingest, pipeline,
  taxonomy) pick up the stored binding thereafter. Two GETs plus the normal token refresh;
  no writes to Etsy; SHADOW/phase rules untouched (READ authority only).

## Tests
`tests/test_w4_etsy_shop_binding.py` (stub transport, 7 tests): resolves + persists + audit
has no token; resolved credentials read after a refresh (scope carry-over); env var wins;
wrong shop refused with incident and not bound; no token -> None, zero requests; a rotation
lost to another worker is not overwritten and the next build resolves after refresh;
credential-health job + build_client bind the shop (HEALTHY). Every test asserts no non-GET
request except the token endpoint.

Regression (all green): test_etsy, test_etsy_oauth_callback, test_etsy_readback_observe,
test_etsy_exercise, test_etsy_capability, test_etsy_transport, test_etsy_surfaces,
test_oauth_security_audit, test_k8_shop_cx, test_w4_etsycomm, test_w3_etsy_upload_readback,
test_w3_tmp_hygiene, test_vacuity, test_cost_governance_wave2.

## Presence checks (follow-up, same branch)
Every place that read `ETSY_SHOP_ID` directly now also accepts the stored binding, and only
when its `shop_name` is the expected shop (`etsy_shop_binding.bound_shop_id`):
- `launch/readiness.py` `etsy_integration`: `credentials_present(db)` (keystring + shop id
  from env or binding + a token: env access/refresh or stored refresh that opens). Ready still
  needs the proven round trip.
- `ops/dependencies.py` `etsy_account.configured` (env_probe ETSY_SHOP_ID): binding counts
  when `map_state` has a db.
- `build2/executor.py` gate `etsy_shop`: `ETSY_SHOP_NAME or shop id known`, still AND a
  recorded successful probe.
- `store_foundation/store_readiness.py` `credentials_present.ETSY_SHOP_ID`.
- `Credentials.from_env` uses the same name-verified reader.
Neither env var nor verified binding: all report absent/False as before (tested, including a
stored binding with the wrong shop name). Tests: two more in
`tests/test_w4_etsy_shop_binding.py` (9 total).

## Notes
- Unverified until deployed: the real token prefix and the real getShopByOwnerUserId body.
  If the prefix is not numeric the resolver falls back to getMe.
