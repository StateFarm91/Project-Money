# W-AGENTAUDIT: who is supposed to do storefront, branding and marketing work, and who actually does it

Audit date: 2026-10-21 (UTC). This was a read-only audit: no code changed, no tests run, no Etsy calls, and no production writes.

**Code audited:** `origin/claude/final-candidate-b997efd` (HEAD f19b264e, release candidate b997efda).

**Production:** b931d17, read through unauthenticated public GETs between 2026-10-21T02:30Z and 02:37Z. `/health` reported `build.commit b931d17a738d…`, `known: true`, and the phase was SHADOW.

**Diff b931d17..b997efd.** Nothing that touches the storefront, branding or marketing changed. The release adds only these:
- `publishing` gains `visual.image_production` and `visual.controlled_experiment`;
- `orchestrator` gains `ops.provider_credentials`;
- experiment refusals are added to the Etsy payload and image paths;
- taxonomy, webhook and first-sale work.

`integrations/etsy.py`, `store_foundation/*`, `brand/*`, `autonomy/charters.py` and `/api/departments` are unchanged. Every finding below therefore holds for both production and the release candidate.

## The owner's question, answered in one paragraph

**The owner is being asked because no storefront, branding or marketing agent exists that could do the work.**
- The Master Plan (§6, §16) designs a **Storefront Director** that "owns banner, icon, About, policies, sections, announcement, thumbnails and grid coherence". The registry implements no such agent, no job type, no handler and no cadence for it.
- `brand/storefront.py` is titled "Storefront Director", but it is a **library of fixed copy and image briefs**, written by build-time worker sessions. No running agent creates it.
- There is no Branding agent and no Marketing agent. The only "marketing" name in the registry is a `FORBIDDEN_COMBINATIONS["marketing"]` entry for an agent that does not exist.

**Where Etsy offers a write API, no code calls it.**
- Shop fields: there is no `updateShop` method.
- Shop sections: there is no `createShopSection` method.
- The single gate (`store_foundation.live_state.write_refusal`) refuses **every** shop field on every call.
- `OwnerGrant` has no action for storefront changes.

**Where Etsy offers no write API, the work genuinely belongs to the owner.** This covers the banner, the icon, the About text, the member bio, five of the six policy texts, and the payment and KYC steps.

**Several cards ask for work that production's own `getShop` reading already shows as done.** The store owner-action list is a fixed list that never closes when the API shows the work done. And the banner check reads a field that the repository itself records may not show a big banner.

## Four levels, as used throughout

- **Designed:** the role appears in the spec (the Master Plan, F-requirements) or in a charter.
- **Implemented:** the agent is in `DEFAULT_AGENTS`, its job types have a registered handler, and a cadence or chain enqueues it.
- **Deployed:** production completed jobs of that type in the sampled window.
  - Sample: `/api/jobs?limit=1000` on 2026-10-21 (ids 24754–25753), plus the earlier scratch read of 2026-10-20 (ids 24356–25355), about 1.5 days in all.
  - `/api/queue/cadences` gives the last output of each cadence.
- **Verified autonomous:** the job did useful, evidenced work without the owner (`work_done > 0`, rows written or decisions taken), not merely `done`.

How handlers were found: every `brambleloop.runtime.*` module was imported, and `handlers.known()` was compared with each agent's `allowed_job_types`. The probe script is in this session's scratchpad. It was an import, not a test run.

## Department-by-department table

| Owner's department | Charter in code (`autonomy/charters.py`) | Agents (`agents/registry.py`), authority, daily ceiling | Designed | Implemented | Deployed (jobs done in the sample) | Verified autonomous |
|---|---|---|---|---|---|---|
| Laura / CEO | `executive` (plus coo, orchestrator, swarm_steward) | `laura` GREEN CA$0.50; `coo` GREEN CA$0.00; `orchestrator` GREEN CA$3.00; `swarm_steward` GREEN CA$0.25 | yes (D-FB-13, F-893) | yes. `laura.executive_tick` every 5 min; `autonomy.orchestrate` every 15 min | laura.executive_tick 193; autonomy.orchestrate 248; department_review 33; morning_handoff 1 | **Partly.** She observes, prioritises and delegates, but only as GREEN `autonomy.department_review` missions. A delegated storefront request becomes a *review* job, never a storefront change, and "replace/change the banner/logo" is refused outright (`laura/agency/delegation.py` `_REFUSED`). She publishes, spends and messages nothing. |
| Creative | `product_design` | `creative_director` GREEN CA$28.00 (raised for the image benchmark); `crochet_engineer` GREEN CA$4.00 | yes (§16 Creative) | yes, 21 job types, about 17 cadences. `crochet_engineer.cir.revise` has **no handler** | creative.* 7 types, about 10 jobs. **crochet_engineer: 0 jobs** (no cir.draft in about 1.5 days) | **Partly.** `creative.north_star` reports regressing on 3 metrics. Model-tournament, model-reference-pack, blinded, expedition and tournament runs were last no-ops (`last_run_was_a_no_op`). It does no storefront or brand creative work: no job type exists for it. |
| **Branding** | **none** | **none** | yes: Master Plan §6 "Storefront Director"; §16 "Brand/Publishing: Storefront Director, Brand Model Consistency…"; F-233–F-241 | **no agent, no job type, no handler, no cadence.** Library code only: `brand/storefront.py`, `brand/takeover.py`, `store_foundation/*` (copy_v2, assets, owner_banner, preview, readiness, live_state, shop_sync) | n/a. Brand-adjacent jobs run under other agents: `quality_director visual.identity_drift` 1; `orchestrator store.live_drift` 1 (observe only); `seasonal.engine` plans "takeovers" (read only) | **No.** |
| **Marketing** | merged into `growth` ("Growth / Marketing") | no separate agent (`growth` and `ads`, below) | yes (§16 Commercial/Growth: Promotion, Pinterest, Social, Email, Etsy Ads…) | `content.draft` (declared for growth and in the charter) has **no handler**. `marketing.schedule` has a handler and runs only inside a product's release chain | marketing.ads_readiness 2; marketing.schedule **0** | **No marketing is executed.** There is no owned channel (gate `owned_surfaces` closed, owner card CA$25 / 65 min), no ads authority, and drafts are held. |
| Growth | `growth` | `growth` GREEN CA$2.00; `ads` YELLOW CA$1.00; `experiment_steward` GREEN CA$0.25 | yes | yes, apart from `content.draft` | growth.distribution 1; growth.journey 1; growth.preproduction 1; growth.experiments 1; growth.conclude 1; growth.steer 2; ads.adjust 1 | **Observes and plans; changes nothing.**<br>• preproduction: 0 prepared, 24 held on `owned_surfaces`<br>• conclude: 64 examined, 64 `no_data`<br>• ads.adjust: authority false, CA$0 |
| Etsy Operations | `store_commerce` | `listing` GREEN CA$2.00; `store_operator` YELLOW CA$1.00; `pricing` GREEN CA$1.00. The Etsy observation jobs run under `orchestrator` | yes (§16 Store Operator, Listing, Etsy SEO) | listing: yes. store_operator: `store.publish` and `store.activate` have handlers; **`store.update` has no handler**. pricing: `pricing.experiment` has **no handler**. **No storefront write job type exists at all.** | listing: chain.rebuild 7, seo.cycle 9–10, taxonomy_refresh 1, search_visibility_watch 1. orchestrator: etsy.credential_health 1, etsy.shop_snapshot 1, etsy.listing_census 1, store.live_drift 1. **store_operator 0, pricing 0** | **Reads only.** SEO proposals are written (10 products), with no Etsy write. On 2026-10-21 the shop_snapshot and listing_census returned `NO_EVIDENCE (TransientError)`; the last FRESH snapshot is from 2026-10-20 00:09Z. store.publish has been refused 186 times; 0 listings carry an Etsy id. |
| Market Intelligence | `intelligence` | `market_radar` GREEN CA$4.00 | yes | yes, except that `radar.competitor_snapshot` has **no handler** | mjs.scan 8–9, radar.score 11, radar.scan 3, etsy.probe 3, intel.serp_capture 1, culture.sweep 1, … | **Yes, for reads.** The one failing `/api/verify` check is 3 `intel.gallery_analysis` dead letters (Timeout). mjs_scan's last run was a no-op. |
| Product Development | `product_design` + `product_truth` | `crochet_engineer`; `validator` GREEN CA$1.00; `quality_director` GREEN CA$1.00; `asset_truth`; `policy` | yes | `cir.twin`, `cir.reverse`, `gate.quality`, `gate.asset_truth` and `gate.policy` have **no registered handler** (presumably done inside other handlers; not verified here) | quality_director 3 jobs; validator, crochet_engineer, asset_truth and policy **0** | **Not in this window.** No new CIR drafted or compiled. |
| Visual Production | `visual` | `publishing` GREEN CA$2.00 | yes (§7, FLUX3 standard) | yes. `assets.render` has **no handler** | visual.rnd.cycle 4–11 (last `work_done: 0`); assets.owned_photography 1–4 (last `ran: false, "no CIR for 'market-basket-trio'"`); model_photography (no-op) | **No useful output in the window.** visual.image_production and visual.controlled_experiment (new in b997efd) need an owner plan or step-up. |
| Finance | `finance` | `cfo` GREEN CA$1.00 | yes | yes | finance.governor 16, reconcile 4, accounting.cycle 4, challenge 4, orders_ingest 3, … | **Yes.** `commerce.orders_ingest` makes 2 real authenticated receipt reads per run (0 receipts). transactions_r works. |
| Customer Experience | `support` | `support` YELLOW CA$2.00 | yes (§10) | yes. `support.reply` is protected | support.triage 16 | **Correctly idle.** There are no customers. `support.reply` is never enqueued (protected). |

The other agents are the eight meta-agents (`improve.role_work`, CA$0.25 each) and `learn` (CA$0). They are not storefront-relevant. `/api/verify`'s `every_agent_has_a_cost_ceiling` passes for all 30 agent rows.

## Findings 1–10

### 1. Which agents exist for branding, creative, marketing, growth and the Etsy storefront

**Creative:** `creative_director` and `crochet_engineer`.

**Growth and marketing:** `growth`, `ads` and `experiment_steward`, plus `swarm_steward` for `growth.steer`.

**The Etsy storefront:**
- `listing`, `store_operator` and `pricing`;
- the read-only Etsy cadences run under `orchestrator`: `etsy.credential_health`, `etsy.shop_snapshot`, `etsy.listing_census`, `store.live_drift` and `etsy.openapi_reverify` (registry.py:732-741).

**Branding and storefront: no agent exists.**
- The designed Storefront Director (Master Plan v1.2 §6, §16) has no `DEFAULT_AGENTS` entry, no job type and no cadence (`runtime/worker.py:564` CADENCES).
- `grep` finds "Storefront Director" only as the docstring of `brand/storefront.py:1`.
- "Thumbnail Warfare" exists only as `commerce/thumbnail.py`, also a library.
- `FORBIDDEN_COMBINATIONS["marketing"]` (registry.py:307) constrains an agent that does not exist.

### 2. What each one does

Responsibilities, job types, authority and ceilings are in the table above, taken from `agents/registry.py` and `autonomy/charters.py`. How the permissions are enforced:
- `Registry.authorize` checks three things in turn:
  - `FORBIDDEN_COMBINATIONS`;
  - `allowed_job_types`;
  - the action class (`authority/classes.py`). The PUBLISH class covers `store.publish`, `store.activate`, `store.update` and `pricing.experiment`; SPEND covers `ads.*`; CUSTOMER-REMEDY covers `support.reply`. These classes are gated unless code declares the agent for them at a non-GREEN grade or an owner `AuthorityPolicy` exists.
- The charters' `PROTECTED_JOB_TYPES` can never be generated by the COO or Laura.
- Spend is checked twice: `record_cost` against the daily ceiling, and `gateway.anthropic.check_budget` before the call.

Ceilings: `creative_director` CA$28 is the outlier. It was raised for the owner-approved image benchmark (registry.py:151-154).

Job types allowed but with **no registered handler** (from the import probe):

| Agent | Job types with no handler |
|---|---|
| store_operator | `store.update` |
| growth | `content.draft` |
| pricing | `pricing.experiment` |
| publishing | `assets.render` |
| market_radar | `radar.competitor_snapshot` |
| crochet_engineer | `cir.revise` |
| validator | `cir.twin`, `cir.reverse` |
| quality_director | `gate.quality` |
| asset_truth | `gate.asset_truth` |
| policy | `gate.policy` |

A job of any of these types would dead-letter if enqueued. Only `store.update` and `content.draft` matter for this question.

### 3. What is deployed and actually executing

See the "Deployed" column. Storefront-relevant work actually running in production:

**Reads:**
- `etsy.shop_snapshot` (getShop) runs daily. The last FRESH reading was 2026-10-20 00:09Z, audit row 57264. Today's run failed transiently.
- `store.live_drift` runs `shop_sync` plus a drift report: 12 proposals, `writes_performed: 0`.
- `listing.taxonomy_refresh` reads 3065 nodes and finds 0 pattern-subtree nodes.

**Listing SEO proposals:** `seo.cycle` runs six-hourly (10 products, `taxonomy UNRESOLVED 10`).

**Growth readings:** distribution, journey and experiments, with nothing executed.

**Not running at all:**
- any storefront writer;
- `store_operator`: 0 jobs, and its `QUALITY_OVERRIDES` exemption reads "idle is shadow mode working";
- `pricing`: 0 jobs;
- `marketing.schedule`: 0 jobs;
- `content.draft`: no handler.

**`/api/departments` still returns 500.** The route (`app/main.py:2922` → `swarm.metrics.agents_view`) is unchanged in b997efd, so the F-487 department view stays broken in the next release. The cause was not diagnosed: that needs logs, which are outside the public-GET rule.

### 4. What is implemented but disabled, blocked or awaiting verification

| Capability | State | Exact reason |
|---|---|---|
| Listing publish (`store.publish`, createDraftListing + images + files) | implemented, blocked | SHADOW phase (`EtsyClient.refusal`). It also needs a sealed `OwnerGrant` (`_authorise_write`) and listing fees (owner card `listing_fees`, CA$6). 186 refusals are on record. |
| Listing activation (`store.activate`) | implemented, blocked | SHADOW, the owner grant, a per-job Launch-0 authorisation, and room under the CA$1 ceiling for the listing fee |
| Live listing edit (`store.update`) | **bug / missing** | Declared, classed as PUBLISH and in PROTECTED_JOB_TYPES, but there is **no handler**. `EtsyClient.update_listing` (PATCH) exists, but no job calls it. |
| Storefront text writes (announcement, sale messages, title) | **missing integration** | No `updateShop` method in `EtsyClient`. `SCOPES_REQUIRED["updateShop"]` exists (etsy_oauth.py:124) and nothing calls it. `live_state.write_refusal` returns a refusal unconditionally (live_state.py:144-158). `commerce.shop_package.api_shop_fields` computes "what may be sent to updateShop", but its only caller is a policy-consistency check (shop_package.py:547). |
| Shop sections | **missing integration** | No `createShopSection`, `updateShopSection` or `deleteShopSection` method, and no `SCOPES_REQUIRED` entry. `intel/etsy_surfaces.py` shop_sections: "creating them is a call nobody has written yet". Raised to the owner instead as `store:OA-D1`. |
| Seasonal storefront takeover (F-241) | planning only | `seasonal.engine` counts `takeovers_planned`. There is no executor, and the banner and announcement have no write path. |
| Paid marketing (`ads.campaign`) | implemented, owner-reserved | `ad_authority` gate and owner authority; `ads.adjust` reports `authority: false` |
| Owned-channel marketing (Pinterest, email, site) | implemented (prepare), blocked | `owned_surfaces` gate closed. No account exists; opening one is an owner action (CA$25, 65 min). |
| `content.draft` | **bug / missing** | Declared for growth and in the charter; no handler |
| Live storefront visual inspection (F-293) | blocked | external capability `rendered_pages` (no browser worker) |
| Store-level stats | owner-only | Etsy Stats are not in the API (`OA-STATS` CSV, deferred until listings are live) |
| Brand face (Laura) in the storefront | gated | `brand_face.image_for(..., for_customers=True)` raises until an image is publication-approved; none is |
| Owner canonical banner as a publishable asset | gated | `owner_banner.assess`: `nav_categories_truth` FAIL (its baked-in nav names Wearables and Gifts, which have no products); 4 gates UNKNOWN (`launch.readiness` storefront evidence) |

### 5. Can they read the authenticated Etsy storefront?

**Scopes held:**
- `listings_r listings_w listings_d shops_r shops_w`, granted 2026-09-25 (BUILD_STATE.md:9754);
- `transactions_r`, effectively held. `/api/verify` withholds the re-authorise card as satisfied (`gate transactions_r`), and `commerce.orders_ingest` makes 2 authenticated receipt reads per run.

**Endpoints actually called** (`integrations/etsy.py`, `store_foundation/shop_sync.py`, `runtime/etsy_ops.py`):
- **Reads:** getShop, getMe, getShopByOwnerUserId, getListing, getListingImages, getListingProperties, getAllListingFiles, getListingsByShop, getShopReceipts, getSellerTaxonomyNodes, getPropertiesByTaxonomyId.
- **shop_sync api_key reads:** getShopSections, getShopReturnPolicies, getFeaturedListingsByShop, findShops.
- **Writes, code only, never executed in production:**
  - createDraftListing, uploadListingImage, uploadListingFile;
  - updateListing (PATCH) and the activation PATCH;
  - deleteListing;
  - updateListingProperty.

**The shop census**, `intel/etsy_surfaces.SHOP_CHECKS`, judges 15 getShop fields. It **cannot read** five things: the About headline or story, a shop member's bio or role, the FAQ, the "listing order = Custom" setting, and the digital-prints option. No operation exposes them (`live_state.OBSERVATION_ONLY`, `shop_sync` READS). These are evidenced only by an owner observation (`store:OA-OBS`).

### 6. Can they prepare and submit storefront content?

| Surface | Prepared by code (deterministic, static) | Submit path in code |
|---|---|---|
| Banner | `store_foundation/assets.py` (SVG from the brief); `owner_banner.py` (gates the owner's canonical 1983×793 PNG); `preview_v2` crops | **none** (Etsy has no API) |
| Icon | `assets.py` SVG micro-mark; the owner monogram in `preview_v2` | **none** (no API) |
| About / story | `copy_v2.ABOUT`, `ABOUT_PARAGRAPHS`, `ABOUT_LAURA_INTRO`; `shop_package.check_about` | **none** (no API) |
| Laura member bio | `copy_v2.SELLER_CAPTION` / `brand_face` | **none** (no API) |
| Policies | `commerce.shop_package.policies()`, `copy_v2.DELIVERY`, `RETURNS`, `PRIVACY` (+ the PIPEDA addendum) | **none.** Only `policy_additional` is API-writable, and it is EU-only. |
| Announcement | `copy_v2.ANNOUNCEMENT`, `SEASONAL_ANNOUNCEMENTS` | **none written.** Etsy offers `updateShop.announcement`. |
| Sale / digital sale message | `copy_v2.DIGITAL_SALE_MESSAGE` | **none written.** Etsy offers `updateShop`. |
| Sections | `copy_v2.SECTIONS`, `navigation.py` (populated categories only) | **none written.** Etsy offers `createShopSection`. |
| Storefront improvements / optimisation | `store.live_drift` proposals (`auto_apply: False`, `write_allowed: False`); readiness checks; owner preview | **none.** No job turns a proposal into a change. |
| Listings (title, tags, description, images, files, price) | listing.draft, listing.seo, seo.cycle, listing_assets | **yes**, behind the owner grant and phase (findings 4 and 7) |

All storefront copy is static module text authored by build-time worker sessions (W4-COPY, lanes A, B and C). No runtime agent regenerates, tests or optimises it.

### 7. Can approved agents update Etsy directly, or must the owner act?

Sources: the repository's recorded Etsy OpenAPI facts (`research/final_build/w4/evidence_MARKETINTEL/etsy_openapi_facts_2026-10-11.json`; oas 3.0.0, sha256 b993d52f…, 105 operations), the `intel/etsy_surfaces.py` evidence and `integrations/etsy_constraints.py`. The 105 operations contain **no** operation that writes a shop image, About text, shop member, FAQ or account profile.

| Storefront field | Etsy Open API v3 write | Repo code calls it? | Verdict |
|---|---|---|---|
| Shop title (tagline) | `updateShop.title` (shops_w) | no | API-writable. **But owner-configured and protected by repo decision** (`live_state.OWNER_CONFIGURED`, 2026-10-06); only a new owner decision changes that. |
| Announcement | `updateShop.announcement` (shops_w) | no | **API-writable: agent-doable once a write path and an owner grant exist** |
| Message to buyers (`sale_message`) | `updateShop.sale_message` | no | **API-writable** |
| Message for digital items | `updateShop.digital_sale_message` | no | **API-writable** |
| Additional terms (`policy_additional`) | `updateShop.policy_additional` | no | Writable only by EU shops (`etsy_constraints.py:282`). Must stay blank here. |
| Payment, delivery, refunds, privacy, seller-info and welcome policy texts | none (readable on getShop only) | n/a | **Owner, in Shop Manager** |
| Structured return policies | `create/updateShopReturnPolicy` exist | no | Not the surface a download shop needs (`return_policy_id` "Required for active physical listings") |
| FAQ, cancellations | no field recorded in updateShop or getShop | n/a | **Owner.** Whether a cancellation field exists in the API is UNKNOWN: it is not recorded. |
| Shop sections | `createShopSection`, `updateShopSection`, `deleteShopSection` (shops_w) | no | **API-writable: agent-doable** |
| Banner | none (getShop `image_url_760x100` is a read-only URL) | n/a | **Owner, in Shop Manager** |
| Icon | none (`icon_url_fullxfull` read-only) | n/a | **Owner** |
| About headline and story | none, and not readable | n/a | **Owner** |
| Shop member bio and role (Laura) | none, and not readable | n/a | **Owner** |
| Listing order = Custom; sold-item visibility; digital prints; Offsite Ads; vacation; currency; location | none (vacation, currency and location are read-only on getShop) | n/a | **Owner** |
| Featured listings | `featured_rank` is in the repo's updateListing field list (etsy.py:661). There is no shop-level ordering setting. | no | Per-listing rank is API-writable per the repo's recorded field list; the Custom sort setting is owner-only. Exact semantics are UNKNOWN. |
| Listings (create, edit, images, files, inventory/price, delete) | createDraftListing, updateListing, uploadListingImage/File, updateListingInventory, deleteListing | yes, except inventory | API-writable; implemented behind SHADOW + OwnerGrant |
| Account profile picture, preferred name, 2FA (`OA-B`) | none | n/a | **Owner** |
| KYC, payout bank, tax | none | n/a | **Owner** (legal and banking) |

### 8. Is the owner's 2026-10-11 storefront work reflected in the shop?

**LAUNCHPREP status.** W-LAUNCHPREP has not pushed `claude/w4-LAUNCHPREP`: `git ls-remote` shows only `claude/w4-LAUNCHREADY`. Its local worktree has no LAUNCHPREP.md (only PRELAUNCH_SCOPE.*). So this section uses only existing production readings and makes no new fetches.

**Source.** The latest FRESH `etsy.shop_snapshot` reading is audit row 57264, 2026-10-20T00:09:48Z. It is identical on 2026-10-18, 10-19 and 10-20:
- `failures = [banner_set, policy_shipping_set, policy_additional_unset, has_a_digital_listing]`;
- `unevidenced = []`.

`assess_shop` checks all 15 `SHOP_CHECKS`. So every other check **passed**: icon, title, announcement, digital_sale_message, payment, refunds, privacy, payments onboarded, not on vacation, and currency CAD.

| Owner says done | Live evidence | Reflected? |
|---|---|---|
| Banner | `image_url_760x100` returned blank, so `banner_set` FAILs | **UNKNOWN: probably a collector false negative.** The repo's own SHOPSYNC.md:37 and `shop_sync.py:84-86` record that "the Shop schema has no other banner field, so a big banner may not appear". `assess_shop` still scores blank as FAIL. It should be UNKNOWN or owner-confirmed, as shop_sync already does. |
| Icon | `icon_set` PASS | **yes** |
| About and shop story | no API | UNKNOWN (only `store:OA-OBS`, still open, can evidence it) |
| Laura's member bio | no API | UNKNOWN (`OA-OBS`) |
| Cancellation policy | no recorded field; `policy_refunds_set` PASS | refunds text present. Cancellations UNKNOWN. |
| Privacy policy | `policy_privacy_set` PASS | **yes** |
| Etsy Payments | `etsy_payments_onboarded` PASS (`is_etsy_payments_onboarded: true`) | **yes** |
| Bank account | no API | UNKNOWN. Consistent with Payments being onboarded. |

**The other three failures:**
- `policy_shipping_set` FAIL is **reality at the API**: the delivery policy text is blank. The owner did not claim a delivery policy, so this is genuine remaining owner work (no API).
- `policy_additional_unset` FAIL is also **reality**: Etsy returned a non-blank `policy_additional`. The repo rule says a Canadian shop must leave it empty. What text is in it is UNKNOWN from public reads; it may be where the cancellation text went.
- `has_a_digital_listing` FAIL is reality: there are 0 listings.

**The owner also did work beyond the claimed list.** Title, announcement and digital-sale-message PASS, so they are set live.

### 9. Is any agent or readiness check wrongly handing its own work back to the owner?

There are 43 open cards (`/api/owner-actions`). The storefront and Etsy cards are classified below.

| Card | Ask | Class | Finding |
|---|---|---|---|
| `store:OA-D1` (#27) | Create sections Home, Baby | **Agent-doable** | `createShopSection` under the held `shops_w`. Raised to the owner only because nobody wrote the call. |
| `store:OA-E` (#28) | Message to Buyers + Message for Digital Items | **Agent-doable, and already done** | Both are `updateShop` fields. `digital_sale_message_set` PASSes live. The card is still presented: `store_readiness.owner_actions()` is a fixed list with no closure on `getShop`. |
| `store:OA-C` (#26) | Announcement (C5), location (C9), listing order (C10), sold visibility (C11) | mixed | Announcement is **agent-doable and already set live** (`announcement_set` PASS). C9, C10 and C11 are owner-only (no API). |
| `store:OA-F` (#29) | Privacy, FAQ with licence, cancellations | owner-only (no API), **partly done** | `policy_privacy_set` PASS. The card does not close on it. |
| `etsy_surface:policy_settings_paste` (#36) | Paste six policies | owner-only (no API) | 3 of the 5 policy checks pass. It is blocked only by delivery (blank) and `policy_additional` (non-blank). It **duplicates** OA-F. |
| `etsy_surface:info_and_appearance_setup` (#35) | Upload banner and icon, paste About | owner-only (no API), **reported done** | The icon passes. It can **never close on the API**: closure needs `banner_set` (`runtime/etsy_ops.py:95`), which reads a field that may not show a big banner. It **duplicates** `store:OA-BANNER` (#25) and `store:OA-OBS` (#23). |
| `payout` (#3) | "Add the payout bank account and tax details…" | owner-only (banking and KYC) | **Stale and un-closable.** Its text is the pre-shop `ETSY_PAYOUT`, not `ETSY_PAYOUT_CONFIRM`. `launch/readiness.py:703-709` hard-codes `ready=False` with no evidence path, although `is_etsy_payments_onboarded` is true on getShop. |
| `store:OA-BANNER` (#25) | Phone screenshot of the banner plus banner-gate rulings | owner-only | Phone crop: no API and no browser worker. The banner-gate rulings (`nav_categories_truth`) are genuine owner decisions under D-FB-17. |
| `store:OA-OBS` (#23) | Record the About text and Laura's bio and role | owner-only (no read API) | Genuine, but it is the third ask about the same surfaces |
| `store:OA-B` (#24) | Account profile, 2FA | owner-only | genuine |
| `store:OA-G1`, `store:OA-G2` (#30, #31) | Digital prints off; Offsite Ads decision | owner-only (no API, margin decision) | genuine |
| `etsy_surface:*` checks (#37–#47: apps, shared access, subscription, ads off, quota, fee readout, policy violations, statement, messages, webhook) | confirmations | owner-only (no API, or Developer Portal) | genuine, although `etsy_ads_off` (#40) and `etsy_ads_eligibility_evidence` (#32) overlap |
| `autonomy:store_commerce:publication_review` (#33), `phase` (#7), `listing_fees` (#4) | publication, graduation, fees | owner-reserved by the directive | genuine |
| `artifact_storage`, benchmark buys, `brand_clearance`, `owned_surfaces`, `physical_proof` | spend, legal, accounts | owner-only (spend, legal, terms acceptance) | genuine |

**The defects behind this:**
- **(a) Two agent-doable surfaces are routed to the owner:** sections, and the announcement and sale messages.
- **(b) Fixed store cards never close on evidence.** `store_readiness.sync_owner_actions` closes only when the owner marks a card done, and `CLOSES_ON_SHOP_CHECKS` covers only the three `etsy_surface:*` keys.
- **(c) The banner check is structurally un-closable.**
- **(d) The payout requirement is hard-coded unmet, and its card text is stale.**
- **(e) The same surface is asked about two or three times** under different keys.

`/api/verify`'s `no_satisfied_owner_action_presented` passes because it only knows gate-backed satisfaction. It cannot see that OA-E and OA-C(C5) are satisfied on getShop.

### 10. What would make storefront optimisation genuinely autonomous after launch

These are listed only, not designed. Engineering gaps are in E-1 to E-12; owner and permission gaps are in P-1 to P-8.

## Remaining gaps

### Engineering gaps (company work)

- **E-1. No storefront agent or job types.** Add a registered agent, or extend `listing` or `store_operator`. It needs job types for storefront proposal and storefront write, handlers and a cadence. Today the Storefront Director exists only as `brand/storefront.py`.
- **E-2. No `updateShop` client method.** It would cover announcement, sale_message and digital_sale_message. The scope entry exists; the method and its effect-boundary check do not.
- **E-3. No shop-section methods** (`createShopSection`, `updateShopSection`, `deleteShopSection`) and no `SCOPES_REQUIRED` entries for them.
- **E-4. No authority lane for shop writes.** `live_state.write_refusal` refuses unconditionally. `OwnerGrant` has PUBLISH, ACTIVATE and PUBLISH_COMPLETE only, with no shop-field action. The authority table has no storefront-write job type.
- **E-5. `store.update` has no handler.** Live listing edits could not run even with a grant. `content.draft` also has no handler.
- **E-6. Store owner cards never close on getShop evidence.** Fix: close `store:OA-E`, the C5 part of `OA-C`, and the privacy part of `OA-F` from the `etsy.shop_snapshot` checks. De-duplicate #35/#25/#23 and #36/#29.
- **E-7. The banner census check treats a blank field as FAIL.** `banner_set` scores blank `image_url_760x100` as FAIL although the repository records that a big banner may not appear there. It should be UNKNOWN or OWNER-CONFIRMED, consistent with `shop_sync`. Otherwise `info_and_appearance_setup` can never close.
- **E-8. The `payout` requirement is hard-coded `ready=False`, and card #3 carries the pre-shop text.** It needs an evidence path: `is_etsy_payments_onboarded` plus an owner confirmation.
- **E-9. No measurement loop for storefront changes.** Experiments are listing-level only (thumbnail, price, search, bundle, pinterest). There is no storefront experiment, no rollback of a shop-field change, and seasonal takeovers (F-241) have no executor.
- **E-10. `/api/departments` returns 500.** It is unchanged in b997efd, so the F-487 department view is broken in production and in the release candidate.
- **E-11. Today's daily Etsy reads failed.** `etsy.shop_snapshot` and `etsy.listing_census` on 2026-10-21 returned `NO_EVIDENCE (TransientError)` with no retry recorded in their outputs.
- **E-12. Smaller defects:**
  - `assets.owned_photography` runs on a slug with no CIR (`market-basket-trio`);
  - handlers are missing for `pricing.experiment`, `assets.render`, `radar.competitor_snapshot`, `cir.revise`, `cir.twin`, `cir.reverse`, `gate.quality`, `gate.asset_truth` and `gate.policy`, all declared in the registry;
  - `FORBIDDEN_COMBINATIONS["marketing"]` references a nonexistent agent.

### Owner and permission gaps

- **P-1. An owner decision to grant storefront write authority.** It would cover announcement, sale messages and sections. It is a PUBLISH-class action, so it is gated; graduation follows SHADOW → STAGING → LIMITED PRODUCTION. **No new OAuth scope is needed:** `shops_w` was granted 2026-09-25.
- **P-2. An owner decision on whether the protected shop title may ever be API-managed** (`OWNER_CONFIGURED`, 2026-10-06). Until then it stays owner-only by the repo's own rule.
- **P-3. Phase graduation out of SHADOW** (card #7) and the per-release publication review (#33). Listing fees approval (#4, CA$6).
- **P-4. Genuinely owner-only, because Etsy publishes no API:**
  - banner, icon, About headline and story;
  - member bio and role;
  - the payment, delivery, refunds, privacy and FAQ policy texts;
  - the location, listing-order, sold-visibility, digital-prints and Offsite Ads settings;
  - the account profile and 2FA;
  - KYC, payout and tax.

  The remaining items in this group are delivery-policy text (blank live) and a ruling on the non-blank `policy_additional`.
- **P-5. Evidence only the owner can supply.** The About text and Laura's bio and role (OA-OBS), and the phone banner crop (OA-BANNER), cannot be read by software unless a `rendered_pages` browser worker is approved. That is an external capability, and Etsy's terms on page reading are UNKNOWN here.
- **P-6. Store-level performance data.** It is only in Etsy Stats (CSV upload, `OA-STATS`, after listings are live). Marketplace Insights (`insights_access`) is owner-recorded.
- **P-7. Marketing execution needs an owned channel.** `owned_surfaces` needs owner account opening (CA$25, 65 min). Paid media needs `ad_authority`.
- **P-8. Laura cannot change the owner's canonical banner or logo** (`_REFUSED`, D-FB-17). Any storefront image change needs a new owner decision.

## Evidence index

**Code** (b997efd):
- `agents/registry.py:43-342, 732-831`
- `autonomy/charters.py:20-26, 150-400`
- `runtime/worker.py:564-674` (CADENCES)
- `integrations/etsy.py:781-1421`
- `integrations/etsy_oauth.py:93-159`
- `intel/etsy_surfaces.py:1287-1665, 2183-2214`
- `runtime/etsy_ops.py:91-106, 1293-1349`
- `store_foundation/live_state.py:86-158`
- `store_foundation/store_readiness.py:321-454`
- `commerce/shop_package.py:406-430`
- `launch/readiness.py:142-215, 700-709`
- `laura/agency/delegation.py:57-87`
- `authority/classes.py:53-60`

**Etsy sources:** `research/final_build/w4/evidence_MARKETINTEL/etsy_openapi_facts_2026-10-11.json`; `integrations/etsy_constraints.py`; `research/final_build/w4/SHOPSYNC.md:35-43`.

**Production reads**, saved in this session's scratchpad (not committed):
- `agentaudit/`: health, api_verify, api_departments (500), api_etsy, api_etsy_surfaces, api_owner-actions, api_growth, api_jobs_limit_1000, api_queue_cadences, api_launch, api_storefront_preview, api_status, api_swarm;
- `/api/etsy/oauth/status` returned 401 (operator credential), which is correct;
- earlier reads in `prod/`: audit_etsy.shop_snapshot.json (rows 49913, 52470, 57264), audit_commerce.orders_ingested.json, audit_etsy.listing_census.json and jobs1000.json.
