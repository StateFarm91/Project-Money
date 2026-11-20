# W4-ETSYCOMM — Etsy connection failures in production, fixed and handed over

Branch `claude/w4-ETSYCOMM` from 0417f35. Production read 2026-10-11 ~14:40Z, read-only
(public `/api/*`, Railway logs and deployment list; no variable values read). Nothing was
written to Etsy, Railway or production.

## 1. Diagnosis

| Failure | Evidence | Kind | Fix |
|---|---|---|---|
| `etsy.probe` HTTP 403 | 89 probe rows: OK every 6 h from 2026-09-19 to 2026-10-07T06:00Z (app id 1516181443672), 403 from 12:00Z that day. No deploy in between (fcb982d ran 2026-09-25 to 2026-10-11). | **External / owner.** The owner reports Etsy suspended the developer app over a missed payment, now resolved. | Company side: Etsy's own refusal text was being discarded, so the record could not tell "key inactive" from a formatting error. It is now kept (redacted, ≤200 chars) in `ReadFailed.etsy_error` and on the probe row (`etsy_error`). |
| `benchmark_observation`, `etsy_api`, `etsy_shop` gates closed | They read the last probe. | Follows from the 403. | None needed. They reopen on the next successful probe. |
| Taxonomy snapshot missing, so the search certificate refuses | `listing.taxonomy_refresh` job 11847 went **dead** on its first attempt with `EtsyRejected 403` on the API-key-only path. No `etsy.taxonomy_refreshed` row exists. | **Company defect, two parts.** (a) A credential refusal raised an exception and became a dead letter. (b) A latent bug would have kept the snapshot from ever being taken: after a successful probe the refresh switched to the shop (OAuth) client. That client needs `ETSY_SHOP_ID`, and production does not have it (`/api/dependencies` shows `etsy_account.configured: false`), so the refresh would have answered "no client could be built" every day. | The API-key client is now used whenever a keystring exists. Etsy's OpenAPI marks `getSellerTaxonomyNodes` and `getPropertiesByTaxonomyId` as `api_key` only, so this is a permitted read-only use. After a refused probe the refresh stands aside with no request. A 401/403 during the read is recorded as `UNMEASURED credential_refused`, not a dead letter. A 5xx still retries. A successful probe with no snapshot queues the refresh immediately (key `tax-after-probe-YYYYMMDD`). |
| 17 `mjs.scan` dead letters | All carry `ReadFailed: find_shops returned HTTP 403`. All were produced by fcb982d before 0417f35 was deployed at 13:58Z. Under 0417f35, `mjs.scan` at 14:00Z recorded `mjs.scan_blocked` `credential_refused: true` and completed. | Same root cause. The defect was already fixed by fa24cd3, which is in 0417f35. | No new change. The old rows leave `/api/verify`'s 24-hour window on their own. The scan resumes after the first successful probe. Not deleted, because that would be a production write. |
| `transactions_r` gate closed | `etsy.credential_health`: a grant is stored (written 2026-09-25T19:27Z, one minute after `etsy.oauth_started`) with scopes `listings_d/r/w` and `shops_r/w`. `missing_scopes` is empty against the old list. The two later `state_missing`/`state_unknown` callbacks were replays. | **Owner action:** re-authorise so the grant includes `transactions_r`. A refresh grant can never widen scopes. | The owner previously could start this only with the operator token. There is now a Command Center button (below). |
| Owner had no phone route | `/api/etsy/oauth/start` and `POST /api/etsy/probe` need the operator Bearer token. | Company gap. | Added `GET /api/cc/etsy`, `POST /api/cc/etsy/recheck` and `POST /api/cc/etsy/connect` (owner session, CSRF, nonce and timestamp through the existing gate; Connect also needs step-up). Added an "Etsy connection" card on the **Store** tab. |
| `ETSY_REDIRECT_URI` vs `CALLBACK_PATH` (report only) | The daily posture (`etsy.credential_health` `security_posture.checks.callback`) reports `configured: true, problems: []`. Its filter keeps every `configuration()` problem that mentions REDIRECT, including the "does not end with /api/etsy/oauth/callback" one. | Consistent | None. |

Seen while diagnosing, outside this lane and not fixed here (owner limited the release to the Etsy connection):
- 7 `ops.sentinel` dead letters: `StringDataRightTruncation`, `jobs.idempotency_key` varchar(200) on insert.
- `/api/verify` `every_agent_has_a_cost_ceiling` fails for learn, coo and laura.
- `model_credits`: anthropic 400.

## 2. Owner phone steps (≈5 min, CA$0) after this release is deployed

1. Open the Command Center and sign in, then go to the **Store** tab and the **Etsy connection** card.
2. Tap **Re-check Etsy connection**, then **Re-check**. Wait 1–2 minutes and pull to refresh. The card should read
   "Etsy accepts the app key (last check …)". If it still says Etsy is refusing the key, the card shows Etsy's own words.
   Check the app at etsy.com/developers/your-apps and re-check. Do **not** regenerate the key.
3. Tap **Connect Etsy shop**. Enter the passphrase or code if asked (step-up), then tap **Continue to Etsy**.
   This button is disabled while the key is refused, and the server refuses with `ETSY_KEY_REFUSED` as well.
4. Etsy shows its own consent page naming the Brambleloop app and the permissions. These are listings read/write/delete,
   shops read/write and **transactions read**. Sign in as the account that owns BrambleloopStudio and tap **Allow access**.
5. Etsy returns the browser to `/api/etsy/oauth/callback`. Success is a page headed "Brambleloop is authorised on Etsy" (status 200),
   with no token shown. Back on the card: "Shop authorised for: …, transactions_r". "Still needed" disappears.
   The consent link expires after 15 minutes. If Etsy shows an error or the callback page says state unknown or expired, tap Connect again.

What then happens on its own: the next probe (≤6 h, or immediately after step 2) reopens `etsy_api`.
The taxonomy snapshot is queued straight away. The search certificate can then pass on category.
`mjs.scan` resumes. `transactions_r` opens once the probe is OK and the grant lists the scope.

## 3. Remaining steps to the first sale

Company side, not part of this Etsy-connection release (from `/api/launch`, 2026-10-11):
- listing_photography (0 listable)
- storefront and storefront_preview checks
- support_knowledge and FAQ packs for the listed releases
- rollback rehearsal
- sustainable_economics forecast
- final_master_closure (DEGRADED)
- etsy_integration round trip, after the connection is restored
- open P2/P3 incidents

Owner, in addition to section 2:

| Action | Why | Max cost | Minutes |
|---|---|---|---|
| Set Railway variable `ETSY_SHOP_ID` to the shop's numeric id | The shop client (census, listing writes, receipts) cannot be built without it (`etsy_account.configured: false`). The company can read the id with `findShops` once the key works. | CA$0 | 2 |
| Confirm payout and tax details on the Etsy shop | Etsy will not pay out without them (launch `payout`) | CA$0 | 10 |
| Approve listing fees for the opening catalogue | about CA$5.32 for 19 listings, plus 6.5% transaction fee per sale | ≈CA$5.32 | 1 |
| Top up Anthropic credit (`model_credits`: 400) | Model-dependent work is stopped | console minimum; code ceiling CA$100/month | 3 |
| Approve durable object storage | Generated PDFs and images do not survive a restart | CA$1–5/month | 5 |
| Confirm the legal seller identity (F-240) | launch `seller_identity` | CA$0 | 5 |
| Authorise the phase move to staging, then limited production, and the first publication | Publication stays owner-authorised | CA$0 | 5 |
