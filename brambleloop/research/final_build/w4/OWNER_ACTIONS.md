# Owner actions -- decision packet (W4-OWNER)

Generated 2026-10-07T01:57:20+00:00 by `research/final_build/w4/owner/build_owner_docs.py` from the runtime approvals inbox plus the STORE and VISUAL lanes. Phase stays SHADOW. UNKNOWN cost is never CA$0.

**Before:** 43 separate asks (9 production rows, 18 gate cards, 13 store items, 3 visual plans). **After:** 25 decisions in 9 batches, ~306 owner minutes; 3 converted back to company work, 1 deferred.

## Go live on Etsy (one sitting in Shop Manager) (5 decisions, 67 min, max CA$651.00)

_each of these is a step of the same move out of shadow mode; none is useful alone, and answering them together takes one Etsy session_

| id | decision | why | evidence | max cost | if yes | if no / delay | min |
|---|---|---|---|---|---|---|---|
| leave_shadow | Authorise graduation from shadow to staging, then limited production, one step at a time, once the steps above are done. | production reason phase | OwnerAction #6 raised 2026-10-07T01:57:20.110589 for phase | CA$0.00 | listings can be published under the publication authority; the live-listing requirements un-park | delay phase | 5 |
| etsy_kyc_payout | Confirm in Etsy Shop Manager > Settings > Payment settings that identity verification, the payout bank account (Canadian chequing) and tax details (GST/HST number or small-supplier declaration) show complete; complete any that do not. | production reason payout | OwnerAction #3 raised 2026-10-07T01:57:20.109673 for payout | CA$0.00 | the payout prerequisite for publishing is met | delay payout | 15 |
| listing_fees | Approve Etsy's listing fees for the opening catalogue (figure on the card). | production reason listing_fees | OwnerAction #4 raised 2026-10-07T01:57:20.110063 for listing_fees | CA$6.00 | publishing is no longer blocked on fees | delay listing_fees | 2 |
| tester_outreach | Confirm the prepared public tester call (Ravelry 'The Testing Pool'; research/final_build/w4/tester_kit/OUTREACH.md) and approve one paid sample make of market-basket-small (Hexagonal Bread Basket, max CA$59.65 incl. yarn). You are not asked to crochet. | 3 requirements are parked on it | gate 'tester_roster' opens when: at least one CreatorProfile has agreed -- delivered > 0 or a recorded permission. A prospect on file is not a tester | CA$185.00 | a measured sample calibrates yardage and Class C products can become shippable | no physical proof can exist (#64), the tester roster (#9/#43/#250) stays empty, and every Class B/C product stays blocked from live sale | 25 |
| trademark_filing | Decide whether to file a Canadian trademark for 'Brambleloop Studio' (CA$458.05 first class). The free knock-out search is company work. | production reason brand_clearance | OwnerAction #5 raised 2026-10-07T01:57:20.110347 for brand_clearance | CA$460.00 | the name is protected before brand equity accumulates on it | delay brand_clearance | 20 |

## Fund the model provider (1 decisions, 5 min, max CA$25.00)

_model_provider, image_vision and the funding rows are one Anthropic balance: one top-up opens all of them_

| id | decision | why | evidence | max cost | if yes | if no / delay | min |
|---|---|---|---|---|---|---|---|
| fund_model | Add credit to the Anthropic account the API key belongs to (console.anthropic.com -> Plans & Billing). | production reason model_credits | gate 'model_provider' opens when: a recorded model.probe succeeded -- a real call, not a variable being set | CA$25.00 | judging, vision and text calls run again: identity measurement, asset-truth checks, gallery analysis, #94 | delay model_credits | 5 |

## Rulings only the owner can make (free, minutes) (2 decisions, 12 min, max CA$0.00)

_free decisions with no account or spend behind them_

| id | decision | why | evidence | max cost | if yes | if no / delay | min |
|---|---|---|---|---|---|---|---|
| acceptance_ruling | Rule whether an API + vision traversal satisfies the 'browser/vision' wording of #189/#221/#222/#320 (yes / no). | 4 requirements are parked on it | gate 'acceptance_ruling' opens when: an OwnerAction with requirement_key 'decision.api_vision_equivalence' is done -- a decision only the owner can make, recorded rather than assumed | CA$0.00 | four requirements are graded against the API path | they stay parked and every acceptance grade stays provisional | 2 |
| production_window | Authorise deploying the reviewed build to the existing service for one unattended window (phase stays shadow). | 1 requirements are parked on it | gate 'production_window' opens when: autonomy.launch_item reads PROVEN from the rows a full production window left | CA$0.00 | the off-device proof (#195) can be read from real rows, and the fixes that close stale production incidents take effect | #195 stays parked and production keeps the stale rows | 10 |

## Owner-only Etsy account screens (10 decisions, 48 min, max CA$0.00)

_each needs the signed-in account holder in a browser, so they are done in the same login_

| id | decision | why | evidence | max cost | if yes | if no / delay | min |
|---|---|---|---|---|---|---|---|
| transactions_scope | Re-authorise the Etsy app with the transactions_r scope (consent screen). | 2 requirements are parked on it | gate 'transactions_r' opens when: the stored Etsy grant lists transactions_r AND a successful etsy.probe is recorded; the scope is added only by the owner in a browser (owner action reauthorise_transactions_r), and the ingest makes no network call while closed | CA$0.00 | orders can be read (#11, #12) | the order source stays closed | 3 |
| insights_reading | Record one Marketplace Insights reading from Shop Manager (POST the reading; no API exists). | 5 requirements are parked on it | gate 'insights_access' opens when: at least one InsightsSnapshot row exists -- a reading somebody recorded from Shop Manager, counted, because there is no sanctioned endpoint that returns it | CA$0.00 | search-demand requirements (#1, #37, #236) get real readings | they stay parked on proxies | 10 |
| OA-OBS | Record what the live shop shows for the fields no API returns: About headline, About story, Laura's member bio and role (paste text; one dated observation) | lets the drift job treat your configuration as authoritative and check it (Laura disclosed as AI, not in the Owner role) without touching it | research/final_build/w4/STORE_READINESS.md (origin/claude/w4-INTEG 7631026) | CA$0.00 | the drift job treats the live About/Laura fields as authoritative and checks them (Laura disclosed as AI, not Owner) without touching them | About/Laura fields stay UNKNOWN; previews may show stale repo drafts | 5 |
| OA-B | Account settings: profile picture = logo mark, real preferred name, short bio, 2FA on (Batch B) | the account picture/name present the legal account holder; Laura must not appear as the account holder | research/final_build/w4/STORE_READINESS.md (origin/claude/w4-INTEG 7631026) | CA$0.00 | the account presents the legal holder; Laura never reads as the owner | a persona could read as the legal owner | 5 |
| OA-BANNER | Phone check: open the shop in the Etsy app, screenshot the banner; and decide on the banner gate findings listed in IMG-2 (nav footer shows Wearables/Gifts/Seasonal, which have no products yet; Laura publication status) | the live banner is yours and is not replaced; Etsy publishes no mobile crop, and the repo gates found items only you can rule on | research/final_build/w4/STORE_READINESS.md (origin/claude/w4-INTEG 7631026) | CA$0.00 | the phone crop is evidenced and the IMG-2 banner findings are ruled on; the live banner stays yours and is not replaced | crop/footer findings stay unresolved | 3 |
| OA-C | Shop settings still open: announcement (C5), location (C9), listing order Custom (C10), sold visibility off (C11) | trust surfaces and ordering | research/final_build/w4/STORE_READINESS.md (origin/claude/w4-INTEG 7631026) | CA$0.00 | announcement, location, custom order and sold-visibility trust surfaces are set | shop snapshot keeps reporting missing trust surfaces | 5 |
| OA-D1 | Create sections for populated categories only (today: Home, Baby) | D-FB-18 item 3: never advertise empty categories | research/final_build/w4/STORE_READINESS.md (origin/claude/w4-INTEG 7631026) | CA$0.00 | listings land in populated sections only (D-FB-18 item 3) | listings land unsectioned | 3 |
| OA-E | Info & Appearance: Message to Buyers + Message for Digital Items (Batch E) | the digital message is the only text every buyer receives at purchase | research/final_build/w4/STORE_READINESS.md (origin/claude/w4-INTEG 7631026) | CA$0.00 | every buyer receives the download guidance at purchase | first buyers get no download guidance | 3 |
| OA-F | Policy Settings: privacy policy, FAQ with licence, cancellations (Batch F) | Etsy trust surfaces; licence belongs in the FAQ for a Canadian shop | research/final_build/w4/STORE_READINESS.md (origin/claude/w4-INTEG 7631026) | CA$0.00 | privacy, FAQ licence and cancellations are live; policy_consistency can pass on read-back | policy_consistency stays failing | 10 |
| OA-G1 | Settings > Options: 'Allow buyers to purchase digital prints' = Disabled | a third party would sell printed copies of a pattern PDF | research/final_build/w4/STORE_READINESS.md (origin/claude/w4-INTEG 7631026) | CA$0.00 | no third party sells printed copies of a pattern PDF beside ours | auto-enrolment may put a third-party product beside ours | 1 |

## Storage and continuity spend (2 decisions, 25 min, max UNKNOWN (at least one item is not costed))

_both are storage accounts outside the code, approved as one spend line_

| id | decision | why | evidence | max cost | if yes | if no / delay | min |
|---|---|---|---|---|---|---|---|
| storage_durable | Approve durable object storage for purchased files (Railway volume or S3). | production reason artifact_storage | OwnerAction #1 raised 2026-10-07T01:57:20.103999 for artifact_storage | CA$5.00 | purchased files survive deploys | delay artifact_storage | 10 |
| storage_offsite | Create an object-storage bucket outside this provider and its credential. | 1 requirements are parked on it | gate 'offsite_storage' opens when: a continuity archive has actually been written offsite. A typed bucket address that is wrong, or whose credentials are, survives losing this provider exactly as well as no bucket at all | UNKNOWN | the continuity archive survives losing the provider (#51) | a provider loss loses the archive with it | 15 |

## Competitive benchmark purchases (1 decisions, 75 min, max CA$300.00)

_the purchase gate and the pre-launch benchmark challenge wait on the same purchased patterns_

| id | decision | why | evidence | max cost | if yes | if no / delay | min |
|---|---|---|---|---|---|---|---|
| benchmark_purchase | Buy the 13 approved MJs benchmark patterns (exact list, links and prices: research/final_build/w4/GATE_CLEARANCE_BUSINESS.md) and upload each download at /ops/teardown. | production reason benchmark_challenge | OwnerAction #7 raised 2026-10-07T01:57:20.110844 for benchmark_challenge | CA$300.00 | the pre-launch challenge (#168) and teardowns can run | delay benchmark_challenge | 75 |

## Owned publishing channels (1 decisions, 65 min, max CA$25.00)

_accounts that accept a platform's terms in the owner's name_

| id | decision | why | evidence | max cost | if yes | if no / delay | min |
|---|---|---|---|---|---|---|---|
| owned_surfaces | The Etsy shop exists (recognised as the paid destination). Open the missing owned surfaces: a domain + static site, a Pinterest business account, a free-tier email sender, a YouTube channel (build2.gate_clearance.MISSING_SURFACES). | 7 requirements are parked on it | gate 'owned_surfaces' opens when: the latest owned_surface.probe audit row records ok: true -- a real publish-path check, not a site URL or token variable being set | CA$25.00 | off-Etsy content requirements un-park | free content, pins, video and the email list have nowhere to publish; acquisition is Etsy search only | 65 |

## Paid media (after organic sales exist) (2 decisions, 6 min, max UNKNOWN (at least one item is not costed))

_advertising authority; recommended only after the shop has sold_

| id | decision | why | evidence | max cost | if yes | if no / delay | min |
|---|---|---|---|---|---|---|---|
| ad_budget | Not askable yet: once a listing is ready to sell (gate_clearance.ad_readiness), set SpendLimit 'ads' to the recommended CA$3/day, CA$25 campaign, CA$60/month (paid_media.CONSERVATIVE_CAPS) or decline. | advertising money leaves only on approval; ceilings are enforced in code | ops/owner_queue.DECISIONS; executor gate(s) ad_authority | UNKNOWN | the ads requirements un-park under that cap | no paid media; recommended until organic sales exist | 5 |
| OA-G2 | Offsite Ads: decide enrolment (15% fee on attributed sales, no fixed spend) | a margin decision, recorded rather than defaulted | research/final_build/w4/STORE_READINESS.md (origin/claude/w4-INTEG 7631026) | UNKNOWN (15% of attributed orders (cap US$100/order)) | Offsite Ads enrolment is a recorded margin decision, not a default | default enrolment stands | 1 |

## Paid image generation (visual plans) (1 decisions, 3 min, max CA$4.01)

_three costed plans on one approval line_

| id | decision | why | evidence | max cost | if yes | if no / delay | min |
|---|---|---|---|---|---|---|---|
| visual_paid_generation | Approve up to CA$4.01 of paid image calls for the costed visual plans: P1 photograph judging (gpt-5 d_judge, <=16 calls, max CA$1.00), P2 LIFESTYLE protected composites for the 3 Launch-0 listings (flux-2-pro, 12+12 calls, max CA$2.00), P3 first judged challenger per launch class (36 calls, max CA$1.01). Approve per plan or all three; or decline and use the no-API alternative (physical sample photo session, yarn ~CA$30 estimated). | each plan is a paid API call (consequential spend needs owner approval); none has been executed (VISUAL_STATUS: 8 GATED_SPEND, never executed) | research/final_build/w4/VISUAL_STATUS.md 'Owner-ready costed plans' on origin/claude/w4-VISUAL 32332f5; visual/milestones.py milestone_d.assess | CA$4.01 | milestone D's 7 judged items become PASS or FAIL; LIFESTYLE frames for the 3 Launch-0 listings; one judged photographic challenger per launch class | D stays PARTIAL with 7 UNKNOWN judgements; LIFESTYLE and the photographic challengers stay queued (GATED_SPEND) | 3 |

## Converted back to company work (not owner asks)

- **OA-A2**: was "Report whether the shop is 'open' (title/announcement editable)" -> the shop state is read by etsy.shop_snapshot (getShop, shops_r) once OA-A1 has re-authorised the app; no separate owner report is needed
- **brand_clearance.knockout**: was "run a trademark knock-out search" -> free public read-only search: company work; the owner decides only the filing (launch/readiness.py TRADEMARK_SCREEN)
- **culture_feed**: was "approval card for the culture_feed gate" -> opened by the company's own daily culture.sweep cadence (owner_queue.COMPANY_OPENED_GATES); never shown as an owner ask

## No longer asked

- **production owner action 2 (etsy_shop)**: the shop exists (executor gate etsy_shop, 2026-09-19); readiness now reads the gate, so 'open the Etsy shop' is not asked again; KYC/payout/tax become the etsy_kyc_payout confirmation

## Deferred (not askable yet)

- **OA-STATS** After the first listings are live: export the listing-level Etsy Stats CSV and upload it (POST /api/attribution/stats): askable only after the first listings are live (DATA-GATED on go-live); produced then by the attribution intake

## Build 2 OWNER-GATED rows (58 rows -> 11 decisions above, each row exactly once)

Source: origin/claude/w4-B2 5241e46 brambleloop/research/final_build/w4/BUILD2_LEDGER.json (as_of 2026-10-07T00:47:10+00:00).

- `NOT_AN_OWNER_DECISION (mislabelled_company_work)`: #242, #243, #244, #245
- `acceptance_ruling`: #189, #221, #222, #320
- `ad_budget`: #294, #295
- `benchmark_purchase`: #163, #165, #168, #315, #317
- `fund_model`: #15, #44, #61, #67, #86, #88, #116, #126, #218, #277, #281, #304, #308, #309
- `insights_reading`: #1, #37, #54, #236, #237
- `leave_shadow`: #14, #16, #46, #238, #239, #241, #254, #263, #266
- `owned_surfaces`: #4, #10, #246, #247, #248, #251, #255
- `production_window`: #195
- `storage_offsite`: #51
- `tester_outreach`: #9, #43, #64, #250
- `transactions_scope`: #11, #12

## Mislabelled company work inside B2 owner gates

| row | parked on | executable company part | owning lane |
|---|---|---|---|
| #242 | ad_authority | the organic-first proof is computed by the daily ads.adjust cadence (runtime/growth_ops.handle_ads_adjust, which runs whatever the ad authority); what it waits for is organic ListingOutcome/order data, so the row is DATA-GATED (live listings + transactions_r), not ad-gated | B2 (ledger) / growth |
| #243 | ad_authority | risk-adjusted allowable CAC is computed in ads.adjust and refused under 20 orders: the blocker is order count (DATA-GATED), not ad authority | B2 (ledger) / growth |
| #244 | ad_authority | the Offsite Ads economics guard is arithmetic over orders and fees computed in ads.adjust; Offsite Ads is a fee on attributed sales, not spend, so ad authority is not its gate (the enrolment choice is store decision OA-G2); remaining blocker = order data | B2 (ledger) / growth |
| #245 | ad_authority | Share-and-Save/direct-link economics involve no spend at all; the computation is company work and its remaining blocker is order data | B2 (ledger) / growth |
| #10 | owned_surfaces | the ledger note says no free work has been made: drafting a free lead-magnet asset through the product chain and running growth/free_to_paid.check_asset on it needs no surface (it stays unpublished in shadow); only publication waits on owned_surfaces | B2 / growth |
| #165 | benchmark_purchases | refresh detection (new category, strong competitor, format/market shift) is software and already runs (intel.benchmark_refresh, runtime/release.py); only buying the refreshed set is the owner's. The row should be split: detection PROVEN, purchase OWNER-GATED | B2 (ledger) |
| #54 | insights_access | the pre-Etsy launch readiness gate is company software (launch/readiness.assess, 2 tests, rollback rehearsal, search baseline from listing.query_portfolio); an Insights reading is one input that stays UNKNOWN until recorded. Gate = PROVEN, Insights input = OWNER-GATED under insights_reading | B2 (ledger) |

## Gate-clearance lanes (W4-GATESI / W4-GATESB)

Folded onto existing decisions: 6; not owner actions (customers, data/external): 2; unmapped: []; pending (not yet pushed): ['infra']. Customers is never an owner action.

Genuine owner gates with an unmapped test (company work for the ledger owner): #254 tests/test_personalisation.py and runtime callers (runtime/commerce_readings.py, products/launch0.py) exist but the ledger lists 0 tests; #263 scale/leading.py reports all ten indicators; ledger lists 0 tests; #37 intel/insights_budget.py runs on commerce.readings; 0 tests mapped; #14 commerce/benchmarks.py; 0 tests mapped; #16 commerce/listing_tests.py, growth/experiments.py; 0 tests mapped; #9 growth/creators.py; 0 tests mapped; #51 core/continuity.py export path; 0 tests mapped.
