# WS5/WS6 audit: real Etsy operations, and the sales and learning chain

- Scope: read-only. Worktree `/home/user/bl-runs/wt-cert9`, commit `5f4a175e` (`claude/w6-INTEG1`). No tests were run and no files in the worktree were changed.
- Paths below are relative to `brambleloop/src/brambleloop/` unless they start with `ops/`, `tests/` or `brambleloop/`.
- **UNKNOWN** means the repository cannot settle the point. That includes all live production state, because no request was made to production or to Etsy.

---

## Part A: real Etsy operations

### A1. Integration map

| Step | Where | What it does |
|---|---|---|
| App config | `integrations/etsy_oauth.py:335-358` (`OAuthApp.from_env`) | Reads `ETSY_KEYSTRING`, falling back to `ETSY_API_KEY`. Also reads `ETSY_REDIRECT_URI` and `ETSY_SHARED_SECRET`. |
| Scopes requested | `integrations/etsy_oauth.py:164-165` `SCOPES_WANTED` | `listings_r listings_w listings_d shops_r shops_w transactions_r`. |
| Scopes per operation | `integrations/etsy_oauth.py:106-151` `SCOPES_REQUIRED` | Draft create, update, property, image and file need `listings_w`. Delete needs `listings_d`. `getListingsByShop`, `getListingProperties` and `getAllListingFiles` need `listings_r`. `getMe` and `getShopByOwnerUserId` need `shops_r`. Receipts, ledger and payments need `transactions_r`. Taxonomy, `getShop` and `getListing` need only the api_key. |
| OAuth start | `app/main.py:5759-5799` `GET /api/etsy/oauth/start` (operator Bearer, `BRAMBLELOOP_OPS_TOKEN`). Also `app/command_center/etsy_connect.py:88-107` (owner session). | Calls `etsy_authorise.begin` (`integrations/etsy_authorise.py:137`). PKCE verifier and state are stored sealed before the URL is returned. `authorize_url` is at `etsy_oauth.py:436`. |
| OAuth callback | `app/main.py:5827-5870` `GET /api/etsy/oauth/callback` (`CALLBACK_PATH`, `etsy_authorise.py:45`) | `etsy_authorise.finish` (`etsy_authorise.py:241-346`): consume the state first, check the sealing key, `exchange` (`etsy_oauth.py:528`), `oauth_store.save_refresh_token` (`core/oauth_store.py:274`), then report `scopes_granted` and `scopes_not_granted`. |
| Token storage | `core/oauth_store.py:274-389`, `core/sealed.py:59` (`BRAMBLELOOP_SECRET_KEY`) | The refresh token is sealed in Postgres `oauth_credentials` with its scopes. Loaded at `oauth_store.py:340`. |
| Refresh | `etsy_oauth.py:538` `refresh`, `etsy_oauth.py:556-620` `TokenProvider` | Refreshes 120 s before expiry. Refuses an operation whose scope was not granted (`etsy_oauth.py:585-591`). Each rotation is persisted with compare-and-set through `integrations/etsy.py:286-327` `_persisting_on_refresh`. Credential selection is at `etsy.py:347-419`. |
| x-api-key | `integrations/etsy.py:421-435` | Sends `keystring:shared_secret`. |
| Shop binding | `integrations/etsy_shop_binding.py`, `runtime/etsy_ops.py:201-217` `build_client` | `ETSY_SHOP_ID` wins. Otherwise the shop is bound from the owner's grant. |
| Taxonomy and properties | `integrations/etsy.py:1143-1216` (`get_taxonomy_node`, `find_taxonomy_nodes`, `get_taxonomy_properties`); `integrations/etsy_taxonomy.py:358` `refresh`; scheduled daily as `listing.taxonomy_refresh` (`runtime/worker.py:683`, handler `runtime/release.py:1557`); drift in `integrations/taxonomy_drift.py` | Category choice is `commerce/category.py:551` `publish_inputs`. The production payload refuses an unchosen taxonomy and never falls back to the default (`runtime/etsy_ops.py:492-505`). The default is still `TAXONOMY_PATTERNS = 66` (`etsy.py:84`). |
| Attribute writes | `integrations/etsy.py:1046` `set_listing_property`; caller `runtime/pipeline.py:2364-2370` | Each certified property is written after create. Readback goes through `etsy_ops.with_properties` (`runtime/etsy_ops.py:528`). |
| Draft create | `integrations/etsy.py:1218` `create_draft` (form-encoded POST `/shops/{id}/listings`); `etsy.py:1539` `publish` (create, then image, then file); production caller `runtime/pipeline.py:2259-2420` | Fields come from `ListingPayload` (`etsy.py:513-546`): `type=download`, `who_made=i_did`, `when_made=made_to_order`, `is_supply=True`. |
| Image upload | `integrations/etsy.py:1242-1300` `upload_image` (multipart part `image`); readiness in `integrations/etsy_image_readiness.py` | |
| Digital file upload | `integrations/etsy.py:1302-1337` `attach_file` (multipart part `file`); production caller `runtime/pipeline.py:2372-2388` | Uploads the US PDF, then the UK PDF. |
| Readback | `runtime/etsy_ops.py` `read_back` (called at `runtime/pipeline.py:2402-2409`); `get_listing` `etsy.py:1027`, `get_listing_images` `:1039`, `get_listing_files` `:1066`, `get_listing_properties` `:1058` | A listing is `published` only if Etsy's readback matches the certified fields, image count, alt text, files and draft state (`pipeline.py:2410-2420`). |
| Recovery: draft intent | `publish/draft_intent.py:43-115` | At most one automatic create per slug@version. If the outcome is uncertain, the intent becomes `RECONCILE_REQUIRED` and a **P1 incident halts publication** (`draft_intent.py:43-51`). **No automatic reconciler reads Etsy to resolve it** (only `ops/slo.py:1161` counts these). Resolution is manual. |
| Recovery: test drafts | `integrations/etsy_probe.py:864` `sweep`; `integrations/etsy_exercise.py:197-313` (`_Breadcrumbs`, `outstanding_drafts`, `reconcile`, `raise_owner_actions`) | Each test draft is audited the moment it is created, and again when its deletion is verified. |
| Recovery: live listing | `commerce/listing_rollback.py:61-112` (`plan`, `execute`); `publish/manual_adoption.py` (adopt a listing the owner created by hand, writes an `ADOPTED_MANUAL` intent) | |
| Activation | `integrations/etsy.py:1481-1537` `activate`; caller `runtime/pipeline.py:2640-2700` | |
| Orders (receipts) | `integrations/etsy.py:1117-1141` `get_shop_receipts` (uses `min_last_modified`); `commerce/orders_ingest.py:234-288` (`EtsyReceiptReader`, with ledger entries via raw `_call`) | |

### A2. What production needs, step by step

**Environment variables** (all in Railway; none in the repo):

- `ETSY_KEYSTRING` and/or `ETSY_API_KEY`. **Set `ETSY_API_KEY` to be safe.** `intel/etsy_public.py:73` reads `ETSY_API_KEY` only, with no `ETSY_KEYSTRING` fallback. That module drives the probe, the `etsy_api` gate and the `/api/etsy` "usable" field.
- `ETSY_SHARED_SECRET`.
- `ETSY_REDIRECT_URI`. It must exactly equal the Callback URL registered in the Etsy app: `https://<host>/api/etsy/oauth/callback`, case-sensitive, no trailing slash (`etsy_oauth.py:188-191`, `etsy_authorise.py:110-120`).
- `BRAMBLELOOP_SECRET_KEY`, the sealing key (`core/sealed.py:59`). Without it the callback refuses to spend the code (`etsy_authorise.py:298-300`).
- `BRAMBLELOOP_OPS_TOKEN`, the operator credential. It guards `/oauth/start`, `/api/etsy/exercise` and the grant APIs, and it is the HMAC key for all owner grants (`ops/publication_authority.py:57-61`). **Rotating it invalidates every grant.**
- Optional: `ETSY_SHOP_ID` (otherwise bound from the grant), `ETSY_REFRESH_TOKEN` (bootstrap only; the database wins).
- Phase: `BRAMBLELOOP_PHASE` (`core/phase.py:49`). It must match the owner's recorded transition.
- `BRAMBLELOOP_PUBLISH_AUTHORISED=1`. This is a global kill-switch: it can deny but never grant (`ops/publication_authority.py:44,68-73`). It is required for real publish and activate (`runtime/pipeline.py:1992, 2541, 2647`).
- `BRAMBLELOOP_READBACK_TOKEN` (`core/readbackauth.py:26`). It is needed so the deploy readback can read the operator rows, including the Etsy row. BUILD_STATE line 11 says it is not set.

**Owner steps:**

1. Register the Etsy app, then paste the Callback URL.
2. Set the variables above.
3. Open `/api/etsy/oauth/start` (or the Command Center Connect button) and approve **all six scopes** in the browser.

**Current state (from BUILD_STATE):**

- 2026-09-25: the OAuth grant succeeded with only the 5 original scopes, so **`transactions_r` was not granted** (`brambleloop/BUILD_STATE.md:9838-9856`).
- Later entries say the `etsy.probe` ping was HTTP 403 from 2026-10-07 (`BUILD_STATE.md:177,188`).
- An entry around 2026-10-13 says the etsy_shop, etsy_api and transactions_r gates were "OPEN" (`BUILD_STATE.md:136`).
- **Today's live state of the credential, its scopes and the probe: UNKNOWN.**

**What the "Etsy credential usable" readback row checks** (`ops/readback.py:122-123`):

- It reads `GET /api/etsy` field `usable` == true. The value is projected through `ops/production_evidence.py:686`.
- `/api/etsy` (`app/main.py:3235-3249`) returns `etsy_public.capability`, which spreads `health(env)` (`intel/etsy_public.py:585-596`).
- `usable` is `bool(keystring and secret)` (`intel/etsy_public.py:219-233`). So it is true whenever `ETSY_API_KEY` and `ETSY_SHARED_SECRET` are set.
- **It does not check OAuth, scopes, refresh, or whether any read succeeded.** The field that actually means "a real read worked" is `demonstrated`, from the last `etsy.probe` (`etsy_public.py:579-582, 590`). The row reads the wrong field. It would have passed through the whole 403 period.
- Separately, the daily `etsy.credential_health` job (`runtime/etsy_ops.py:878-940`, cadence `runtime/worker.py:953`) checks that the sealed credential opens, has the required scopes and survives a `getMe` refresh. But `REQUIRED_SCOPES` (`runtime/etsy_ops.py:77`) **omits `transactions_r`**, so the missing scope is never flagged there.

### A3. Is there a "minimal approved operation" path?

Yes, it exists.

- Route: **`POST /api/etsy/exercise?mode=full|rotation`** (`app/main.py:5973-6010`).
- Implementation: `integrations/etsy_exercise.py:666-786` (`run`), which calls `integrations/etsy_probe.py:909` `run_exercise`.
- Steps (`etsy_probe.py:10-28`):
  - ping, then sweep earlier test drafts;
  - `getMe` and `getShop`;
  - create one draft titled "DO NOT BUY - Brambleloop transport test";
  - upload an image (a 1-pixel PNG, `etsy_probe.py:775`);
  - PATCH the title and tags;
  - read back;
  - verify taxonomy, required properties, tag encoding and remote values;
  - delete, then verify a 404.
- After that it does an independent shop readback, reconciles the breadcrumbs, runs a refresh-rotation proof (`etsy_exercise.py:492`), takes an `/api/verify` snapshot, and writes a sealed evidence row (`etsy_exercise.py:816`).
- That evidence row is what `gates/first_customer.py:626` `check_etsy_remote_state` reads to promote claims to VERIFIED_AGAINST_ETSY.
- `mode=rotation` makes two shop reads and no draft.

**Authorization it needs, exactly:**

- The operator Bearer `BRAMBLELOOP_OPS_TOKEN` (`app/main.py:5998-6003`).
- A stored, openable sealed credential with `listings_r`, `listings_w`, `listings_d` and `shops_r`. The keystring and shared secret must be set (`etsy_exercise.py:314-330`).
- The effective phase must be **non-publishing** (shadow or staging). The client is built with `owner_authorised=False, shadow_writes_authorised=True` (`etsy_exercise.py:346-350`). `_authorise_write` allows the draft-only lane only while `core.phase.effective` is not a publishing phase (`etsy.py:923-963`, `PHASES_THAT_MAY_PUBLISH` at `etsy.py:86`).
- **No publication grant (`ops/publication_authority.py`) and no activation grant (`ops/activation_authority.py`) are needed or used.** Activation is structurally refused: `_client` raises if `refusal_for(ACTIVATE)` is None (`etsy_exercise.py:352-360`).
- Cost: CA$0.

**What it does not prove** (this matters for the owner's request):

- **No digital file upload.** `etsy_exercise.run` calls `run_exercise` without `pattern=` (`etsy_exercise.py:714-716`), so step 3b (`etsy_probe.py:1055-1065`) never runs. In addition, `uploadListingFile` is not a claim in the `publish/listing_schema.py` verification matrix (claims at `:513-577`), so no gate requires it to be verified against Etsy.
- **No attribute or property write.** `set_listing_property` is not called by the exercise. Step 6 only reads the taxonomy and its required properties.
- **Not the production category.** The exercise sends the default `taxonomy_id=66` (`etsy_probe.py:781-803`, `etsy.py:522`), not the node `commerce.category.publish_inputs` would choose.
- The 1x1 image may be refused by Etsy. The probe classifies that as `image_too_small` (`etsy_probe.py:382`). Etsy's actual minimum: **UNKNOWN**.

**Grants used by the real-product path (not the exercise):**

- Publication grant: `ops/publication_authority.py:401` `approve`, served at `/api/owner/publication/{preview,approve,revoke,rebase}` (`app/publication_authority_api.py:13-48`). It is sealed, bound to slug@version, the release hash, the CIR digest and the exact listing fields including taxonomy. It expires after 24 h and is revocable and chained.
- Activation grant: `ops/activation_authority.py:62-91`, served at `/api/owner/activation/...` (`app/activation_authority_api.py:8-37`). It is bound to listing id, frames, files and payload, and expires after 24 h.
- Both are re-checked by `OwnerGrant.refusal` (`integrations/etsy.py:140-181`) at the effect boundary.

### A4. From SHADOW to the first public listing

There are two routes.

**Route 1, automated:**

1. **SHADOW (now).**
   - Owner: complete the OAuth grant with all 6 scopes.
   - Operator: run `POST /api/etsy/exercise?mode=full`.
   - The run must finish `ok` against `openapi.etsy.com` with every test draft verifiably deleted. That settles the `blocks_launch` claims `form_encoded_create`, `multipart_image_upload`, `array_encoding_tags` and `oauth_token_endpoint` (`publish/listing_schema.py:529-563, 640-724`) for `check_etsy_remote_state`.
2. **SHADOW → STAGING.**
   - `POST /api/owner/phase/transition` (`app/phase_api.py:39`, `core/phase.py:311`).
   - Requires the ops token and a reason.
   - Requires evidence refs `readiness` (a `launch.assessed` row under 7 days old) and `rollback` (a `launch.rollback_rehearsed` row under 3 days old; `core/phase.py:231-268`).
   - Requires `launch.readiness.transition_verdict(to)` to be ready at transition time (`launch/readiness.py:1598-1635`; `core/phase.py:283-308`). That verdict covers the six questions, every hard gate, the off-device autonomy proof and the demand-capture plan.
   - Then set `BRAMBLELOOP_PHASE=staging` to match the record. A mismatch resolves to the more restrictive phase and opens an incident (`core/phase.py:1-20, 164-205`).
3. **STAGING → LIMITED_PRODUCTION.** Same as step 2, but the cited evidence must now be **passing** (`core/phase.py:235, 261-265`). Then set `BRAMBLELOOP_PHASE=limited_production`. This is the first phase in which `EtsyClient.refusal()` allows a real product draft (`etsy.py:836-852`, `PHASES_THAT_MAY_PUBLISH`).
4. **Real certified draft (`store.publish`).**
   - Set `BRAMBLELOOP_PUBLISH_AUTHORISED=1`.
   - Owner previews, then approves the publication grant for slug@version@release (24 h).
   - The job must carry `owner_publication_approval_id` (`runtime/pipeline.py:2316-2321`).
   - Pre-create revalidation (`pipeline.py:2297-2300`), then a durable intent, then create with image and US PDF, then the property writes, the UK PDF, and readback.
   - The listing becomes `published` (still a **draft** on Etsy) or `incomplete_on_etsy`.
5. **Activation (first public listing, US$0.20 listing fee).**
   - Owner previews, then approves the activation grant for that listing id (24 h).
   - `store.activate` checks the kill-switch, the release and parity gates, and the phase twice. Then `effect_guard` makes at most one attempt, and `client.activate(... launch_authorisation="owner-approval:<id>", grant=...)` sends `updateListing state=active` (`runtime/pipeline.py:2640-2700`, `etsy.py:1481-1537`).
   - It then reads back `state=active`.
   - The first-customer gate (physical sample, `gates/first_customer.py`) is also part of the release gates. Its full contents were not audited here: **UNKNOWN** in detail.

**Route 2, manual first listing:** the owner creates the listing by hand in Shop Manager, then runs `listing.adopt_manual` (`publish/manual_adoption.py:1-30`). That path needs no publishing phase for Brambleloop's own writes.

**Key ordering fact:** a real (non-test) product draft **cannot be created in SHADOW or STAGING**. Only the self-deleting test draft can. So "prove real draft creation with category, attributes and files" before LIMITED_PRODUCTION is possible only if the exercise is extended.

---

## Part B: the sales and learning chain

### B1. Each link

| Link | Module (file:line) | Scheduled? | Data source |
|---|---|---|---|
| Etsy listings | `runtime/pipeline.py:2259-2420` (`store.publish`), `:2640-2700` (`store.activate`) | Job-driven, gated by the owner | Our own writes, then **official API** readback |
| Listing observations | `runtime/etsy_ops.py:1278` (census, cadence `runtime/worker.py:1014` daily); `commerce/listing_outcomes.py:363-427` `api_snapshot` | Daily (`listing.outcomes`, `runtime/worker.py:1028`; handler `runtime/listing_outcomes.py:45`) | **Official API** `getListingsByShop(state=active)`: cumulative `views` and `num_favorers`. Stored as an `operating_readings` row only, **never** as a `ListingOutcome`. |
| Listing outcomes (funnel) | `commerce/listing_outcomes.py:225` `submit_export`, `:260-322` `_record_export`, `:557` `produce` | Upload is manual; draining is daily | **Manual owner Etsy Stats CSV** (`POST /api/listing-outcomes` at `app/main.py:4355`; Command Center `app/command_center/api.py:1241`) |
| Orders and receipts | `commerce/orders_ingest.py:1069` `ingest`, reader `:234-288`, gate `:178-194`; handler `runtime/orders.py:75` | Every 6 h (`runtime/worker.py:679`) | **Official API** `getShopReceipts` (`transactions_r`), including `refunds[]` and `min_last_modified` re-reads. The gate also requires a successful public `etsy.probe`. |
| Fees and refunds | `finance/reconcile.py:1-25`; handler `runtime/pipeline.py:3288` | Daily (`runtime/worker.py:621`) | **Official API** `getShopPaymentAccountLedgerEntries` (`transactions_r`) |
| Accounting | `finance/accounting/posting_rules.py:1-30`; job `finance/accounting/job.py:17` | Every 6 h (`runtime/worker.py:1043`); period pack daily (`:1034`) | Derived from ledger, cost and bank-line rows. `finance/accounting/shadow_dataset.py` is **synthetic**, refuses non-SQLite databases (`:1-10`), and is used only by tests and the proof. |
| Measured performance | `commerce/listing_outcomes.py:472` `funnel`, `:434` `measurement_status`; `runtime/commerce_readings.py:241` | Daily | Export rows plus the API snapshot. Orders come from export rows, or from `countable_orders` when the order source is live (`:536-554`). |
| Lessons | `improve/commercial_lessons.py:123-152` `measured_groups`, `:170` `verdicts`, `:218` `record_lessons`; job `runtime/commercial_ops.py:14` | Daily (`runtime/worker.py:640`) | **Only `ListingOutcome` rows whose source starts `owner_export:`**, meaning the manual CSV. Both visits and orders come from that CSV (`commercial_lessons.py:40-41`). Receipts are **not** used. |
| Other learners | `creative/outcome_learning.py:60-100`; `creative/style_learning.py:271-279, 416-487` | Daily (`runtime/worker.py:653-654`) | All `ListingOutcome` rows **with no source filter**, plus `countable_orders`. Style learning writes hero-image preferences. Outcome learning writes an audit only and does not change rankings. |
| Concept rankings | `runtime/pipeline.py:434-560` `radar.score`; `improve/consume.py:71, 120-123` | On each scan or intake (`runtime/worker.py:618, 982`) | Lesson inbox `market_radar`. The nudge is `score_adjustment` (`step=0.02`, `cap=±0.06`), applied after the evidence discount (`pipeline.py:487-495`). |
| New products | `runtime/pipeline.py:528-560` (`cir.draft` enqueue) | When promoted | Promotion needs `adjusted >= PROMOTION_THRESHOLD`, plus the pre-engineering gate (`pipeline.py:498-516`). |

### B2. Dependencies on manual Etsy Stats exports, and official alternatives

| Dependency | File:line | Official API alternative? |
|---|---|---|
| Listing funnel and `ListingOutcome` rows (impressions, visits, favourites, carts, orders) | `commerce/listing_outcomes.py:13-27, 65-81` (impressions and visits are REQUIRED) | **Orders:** yes. Receipts and transactions (`getShopReceipts`, `getShopReceiptTransactionsByShop`, `transactions_r`) are already ingested, but lessons ignore them. **Favourites:** partial. `num_favorers` is a cumulative counter with no time series, which can be differenced, and is already snapshotted. **Views:** partial. `views` is cumulative, "tabulated once per day and only for active listings" (`brambleloop/research/final_build/w4/evidence_MARKETINTEL/etsy_openapi_facts_2026-10-11.json`, `views_field`). **Impressions, visits, carts:** none. |
| `improve.commercial_lessons` (visits, orders per category) | `improve/commercial_lessons.py:123-152` | Orders: yes (receipts). Visits: **no**. The API's views are page views, not visits. |
| Search-term and traffic-source attribution (#237) | `commerce/attribution.py:183-264` (`POST /api/attribution/stats`, `app/main.py:4508`) | **None.** The OpenAPI has 0 occurrences of stats, traffic, visit or impression (`intel/etsy_surfaces.py:745-765`). |
| SEO measurement and learning | `seo/measure.py:6-7, 102`; `seo/evidence.py:7, 72`; `seo/learning.py:17, 47` | None for search terms or queries. |
| Dashboard KPIs and traffic sources | `integrations/etsy_dashboard.py:10-30, 62-70` (`kpi_snapshot`, `record_traffic_sources`) | Orders and revenue: yes (already from receipts). Views, visits and sources: none. |
| Leading indicators and run-rate | `scale/leading.py:21-22, 136-173` | Orders: yes. Impressions and visits: none. |
| Style learning, outcome learning, first-ten, success, paid media | `creative/style_learning.py:308`; `creative/outcome_learning.py:117-123`; `commerce/first_ten.py:53`; `launch/success.py:45`; `commerce/paid_media.py:392-418` | Orders and revenue: yes. Impressions, visits and offsite share: none. |

**Metrics that must stay UNKNOWN without an owner export:** impressions, visits (sessions), cart adds, conversion rate, traffic sources and channel, search terms and queries, Etsy Ads and Offsite Ads traffic.

**Partly available from the API:** listing `views` (cumulative, daily, active listings only) and `num_favorers` (cumulative).

**Fully available from the API:** orders, revenue, refunds, fees and the Offsite Ads fee (as attribution evidence).

**Bug found:** `api_snapshot` maps the API's `views` delta to the name **"visits"** (`commerce/listing_outcomes.py:413`), and the docstring says the same (`:22-24`). Etsy distinguishes views from visits, so this mislabels a metric. Today it does not feed lessons, because API periods never become `ListingOutcome` rows.

**Unverified:** whether Etsy Shop Manager actually offers a listing-level Stats CSV with these columns is **UNKNOWN** from the repo.

### B3. Are internal manufacturing and quality signals kept apart from buyer evidence?

**Partly.**

- **Kept apart:**
  - `improve/presale.py:1-25, 59-63`: every internal reading carries `customer_outcome: False` and `kind: "internal pre-sale outcome"`.
  - `improve/measure.py:466-480`: `DATA_GATED_CELLS` (pricing, customer_experience, portfolio, ...) state that "nothing internal stands in for them".
  - The dashboard shows the two separately (`app/main.py:6633-6648`).
- **Not kept apart where rankings are decided:**
  - The `Lesson` model has no evidence-class field (`core/models.py:1370-1379`).
  - `market_radar` receives internal lessons such as `creative_rejection` (jury deaths) and `construction_preference`, research lessons such as `cultural_*`, and buyer lessons such as `commercial_*`, through `improve/bus.py:27-62`.
  - `consume.score_adjustment` sums them all under **one** ±0.06 cap (`improve/consume.py:36-45, 120-123`; `runtime/pipeline.py:487-490`). So internal and buyer signals are mixed and can offset each other.
  - `defect` lessons do not route to `market_radar` (`improve/bus.py:46`).

### B4. Is there a test proving a real measured outcome safely changes later rankings?

**No end-to-end proof.**

What exists, in `tests/test_opus2_commercial_lessons.py`:

- `:136-147`: a lesson raises `radar.score`'s `lesson_adjustment`, stays at or under 0.06, and the gate still decides.
- `:96-103`: rows whose source is not `owner_export:`, or that have no orders, measure nothing.
- `:150-167`: idempotence, and newer evidence withdraws the old lesson.

What is missing:

- **Synthetic exclusion is by prefix only.** The test fixtures are themselves `owner_export:fixture-1` rows inserted directly (`tests/test_opus2_commercial_lessons.py:44-50`), and they are counted as measured. `measured_groups` checks only `source LIKE 'owner_export:%'` (`improve/commercial_lessons.py:131-133`). It does not apply the round-trip proof that `measurement_status` uses (`commerce/listing_outcomes.py:434-469`). No model has an `is_synthetic` flag. The other learners read every `ListingOutcome` row unfiltered (`creative/outcome_learning.py:80`, `creative/style_learning.py:273`).
- **No test of the full chain:** `submit_export` → `listing.outcomes` → `improve.commercial_lessons` → `radar.score` → `cir.draft`. (`submit_export` appears only in `tests/test_k3_listing_outcomes.py` and `tests/test_w4_seo_packages.py`, and neither references lessons or radar.)
- **No test of the loop over repeated cycles.** Nothing tests decay or expiry of a lesson's effect, an exploration floor, or preventing a favoured category's follow-ons from compounding. The bounds are the per-concept ±0.06 cap and verdicts relative to the shop rate. There is no time decay.
- **No paid-traffic exclusion.** `detail.paid` is recorded (`commerce/listing_outcomes.py:286-289`), but `commercial_lessons` does not filter on it.
- **Receipts unused.** Lessons do not use official receipt orders at all.

---

## Engineering gaps by severity

1. **HIGH.** Buyer evidence can reach rankings only through manual Stats CSV uploads. `commercial_lessons` ignores receipts (`improve/commercial_lessons.py:40-41, 123-152`). With no uploads, the learning loop never closes. Fix: use `countable_orders` from receipts for the numerator and API `views` as an explicitly labelled denominator. Keep visits and impressions UNKNOWN.
2. **HIGH.** The minimal exercise does not prove digital file upload, property writes or the chosen category (`integrations/etsy_exercise.py:714-716`; `integrations/etsy_probe.py:781-803, 1055-1065`). `uploadListingFile` is not a claim in the matrix (`publish/listing_schema.py:513-577`). Fix: pass a marked test PDF, use the `category.publish_inputs` taxonomy and properties, write and read back one property, and add a `multipart_file_upload` claim that blocks launch.
3. **HIGH.** The "Etsy credential usable" readback row checks only that the environment variables exist (`intel/etsy_public.py:227`; `ops/readback.py:122-123`). It should read `demonstrated`, and ideally `oauth_store.credential_health`.
4. **MEDIUM.** Synthetic or hand-inserted rows are excluded only by source prefix. The round-trip proof is not enforced in `commercial_lessons`, and the style and outcome learners have no filter at all (B4).
5. **MEDIUM.** Lessons have no evidence class, and internal and buyer lessons share one cap in `radar.score` (`improve/consume.py:120-123`). There is no end-to-end or multi-cycle loop test, no decay, and no paid-traffic exclusion.
6. **MEDIUM.** An uncertain draft creation opens a P1 halting incident with no automatic Etsy reconciler (`publish/draft_intent.py:43-51`).
7. **LOW.** API `views` is labelled "visits" (`commerce/listing_outcomes.py:413`).
8. **LOW.** `REQUIRED_SCOPES` omits `transactions_r` (`runtime/etsy_ops.py:77`). A stale comment says "no code path calls a receipt" (`integrations/etsy_oauth.py:160-161`).
9. **LOW.** `etsy_public` reads only `ETSY_API_KEY` (`intel/etsy_public.py:73`), while OAuth accepts `ETSY_KEYSTRING`. A keystring-only setup closes the orders gate through `etsy_public.usable`.
10. **LOW.** `get_shop_listings` has no paging (limit 100; `integrations/etsy.py:1098-1115`), so snapshots and census truncate above 100 listings.

## Owner actions per Etsy step

- **A. App and environment, once.**
  - In the Etsy developer portal, set the Callback URL to exactly `https://<prod host>/api/etsy/oauth/callback`.
  - In Railway, set `ETSY_API_KEY` (and/or `ETSY_KEYSTRING`), `ETSY_SHARED_SECRET`, `ETSY_REDIRECT_URI`, `BRAMBLELOOP_SECRET_KEY`, `BRAMBLELOOP_OPS_TOKEN` and `BRAMBLELOOP_READBACK_TOKEN`.
  - Also resolve the ping 403 recorded in `brambleloop/BUILD_STATE.md:188` (check app status and the shared secret).
  - About 15 min, CA$0.
- **B. OAuth.** Open `/api/etsy/oauth/start` (or Command Center Connect) and approve all 6 scopes, **including `transactions_r`**. Confirm `scopes_not_granted` is empty. About 3 min, CA$0. Until this is done, orders, fees and accounting stay UNMEASURED.
- **C. Minimal operation.** The operator calls `POST /api/etsy/exercise?mode=full` with the ops Bearer while the phase is SHADOW. CA$0. If a draft is stranded, the owner deletes it in Shop Manager > Listings > Drafts (about 2 min). No publication or activation grant is needed.
- **D. Phase moves.** `POST /api/owner/phase/transition` SHADOW→STAGING, then STAGING→LIMITED_PRODUCTION. Each move needs a reason, `readiness` and `rollback` evidence ids, and a ready verdict. Match `BRAMBLELOOP_PHASE` each time. About 5 min per move.
- **E. First real draft.** Set `BRAMBLELOOP_PUBLISH_AUTHORISED=1`, then preview and approve the publication grant for slug@version@release (24 h). CA$0, because drafts are free.
- **F. First public listing.** Preview and approve the activation grant for the listing id (24 h). Etsy listing fee US$0.20 (`integrations/etsy.py:670`). This is a consequential spend, approved by the owner.
- **G. Stats.** Optional. Periodically upload the listing-level Stats CSV through the Command Center. This is the only source for impressions, visits, carts, search terms and traffic sources.
