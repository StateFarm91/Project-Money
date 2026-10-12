# W4-SHOPSYNC: live shop settings, each one CONFIRMED-LIVE, OWNER-CONFIRMED or UNVERIFIED

Branch `claude/w4-SHOPSYNC`, from `origin/claude/w4-INTEG2`.
Code: `store_foundation/shop_sync.py`. Tests: `tests/test_w4_shopsync.py`, 13 tests, against stubbed Etsy responses.

This branch adds no Etsy write and changes no scope or credential. It never writes an owner-configured live field.

## Source of truth for the API column

The column comes from Etsy's Open API v3 document at `https://www.etsy.com/openapi/generated/oas/3.0.0.json`.
- It was re-downloaded on 2026-10-11.
- Its sha256 is `b993d52f46afdf87f7687dc6ff8885f2b012589f9b123e1faf14cc54ee73a9ef`, which is byte-identical to the copy pinned in `evidence_MARKETINTEL/etsy_openapi_facts_2026-10-11.json`.

Operations called. All are GET, and all carry root-level `api_key` security, so the app keystring alone is enough: no OAuth token and no scope.

| Operation | Path |
|---|---|
| `findShops` (only when `ETSY_SHOP_ID` is unset; exact-name match) | `/v3/application/shops` |
| `getShop` | `/v3/application/shops/{shop_id}` |
| `getShopSections` | `/v3/application/shops/{shop_id}/sections` |
| `getShopReturnPolicies` | `/v3/application/shops/{shop_id}/policies/return` |
| `getFeaturedListingsByShop` | `/v3/application/shops/{shop_id}/listings/featured` |

These operations exist in the document but are not called here, because they need OAuth:
- `getHolidayPreferences` (`shops_r`)
- `getMe` (`shops_r`): returns only the account's user id and shop id
- `getUser` (`email_r`): returns only the account holder, not shop members

The OAuth grant (Connect button, W4-ETSYCOMM) is therefore not needed for this sync. It is still needed for orders (`transactions_r`) and for writes.

## Mapping

| Setting | How it is evidenced | State when evidenced |
|---|---|---|
| Shop name | `getShop.shop_name` | CONFIRMED-LIVE |
| Shop icon (logo) | `getShop.icon_url_fullxfull` | CONFIRMED-LIVE (`value_present` shows whether one is set) |
| Banner | `getShop.image_url_760x100`. The Shop schema has no other banner field, so a big banner may not appear. When the API shows none, the owner confirms it (prefilled from the open `store:OA-BANNER` card). | CONFIRMED-LIVE when present, else OWNER-CONFIRMED |
| Tagline (shop title) | `getShop.title` | CONFIRMED-LIVE |
| Announcement | `getShop.announcement` | CONFIRMED-LIVE (a blank announcement is a confirmed blank) |
| About headline and story | No operation. The owner confirms, prefilled with the dated `store.live_observation` text and `store:OA-OBS`. | OWNER-CONFIRMED |
| Member identity (Laura's profile and role) | No operation. The owner confirms, prefilled with the `laura_member_*` observations, `store:OA-OBS` and `store:OA-B`. | OWNER-CONFIRMED |
| Listing order (Custom) | The sort setting is not in the API. The owner confirms, prefilled with `getFeaturedListingsByShop.featured_rank` and `store:OA-C`. | OWNER-CONFIRMED |
| Sold-item visibility | No field. The owner confirms, prefilled with `store:OA-C`. | OWNER-CONFIRMED |
| Sections | `getShopSections` (title, rank, active_listing_count) | CONFIRMED-LIVE |
| Buyer messages | `getShop.sale_message` and `getShop.digital_sale_message` | CONFIRMED-LIVE |
| Vacation mode | `getShop.is_vacation` and `getShop.vacation_message` | CONFIRMED-LIVE |
| FAQ | No field. The owner confirms, prefilled with `store:OA-F`. | OWNER-CONFIRMED |
| Privacy policy | `getShop.policy_privacy` | CONFIRMED-LIVE |
| Cancellation and returns | `getShopReturnPolicies` (accepts_returns, accepts_exchanges, return_deadline) and `getShop.policy_refunds` | CONFIRMED-LIVE |
| Payment readiness | `getShop.is_etsy_payments_onboarded` and `is_direct_checkout_onboarded` | CONFIRMED-LIVE |
| Payout bank account and tax details | Not exposed. The owner confirms, prefilled with `getShop.is_etsy_payments_onboarded` and `store:OA-B`. | OWNER-CONFIRMED |
| Currency and location | `getShop.currency_code` and `shop_location_country_iso` | CONFIRMED-LIVE |
| 2FA | No field. The owner confirms, prefilled with `store:OA-B`. | OWNER-CONFIRMED |

## Rules
- **CONFIRMED-LIVE** requires an API reading no more than 7 days old. Older readings show as UNVERIFIED, with the reason.
- **OWNER-CONFIRMED** is valid for 90 days.
  - It is offered only where the API cannot read the setting. A confirm for an API-readable setting is refused with `NOT_OWNER_CONFIRMABLE`.
  - It records a `store.owner_confirmed` audit row with the statement, a timestamp and the evidence snapshot.
- **UNVERIFIED** is everything else, and always carries a reason. A refused key, a missing keystring or an inexact shop name each means "nothing read", recorded in a `store.shop_sync` audit row. None of them is ever a dead letter.
- **Cadence.** The sync runs at the start of the daily `store.live_drift` job (no new job type). Its `getShop` body becomes the live side of the existing drift report, so `live_state` UNKNOWNs clear. "Re-read from Etsy" on the Store tab queues the same job.
- **Phone.** Store tab → "Live shop settings":
  - each setting shows its state badge, source and timestamp;
  - each owner-confirmable setting has a Confirm button that lists the evidence already on file;
  - one tap records the confirmation.
  - Session and CSRF are required. No step-up, because a confirmation grants no authority.

## Not done
- Integration with ETSYCOMM's Store-tab card: both edit `views/store.js` and `api.js`, so the integrator merges two additive blocks.
- The service-worker cache version is bumped to `cc-shell-v12`.
