# Store readiness — real Etsy shop (lane W4-STORE)

Generated 2026-10-07T00:03:20.929978+00:00 by `store_foundation.store_readiness` (regenerate: `PYTHONPATH=src python -m brambleloop.store_foundation.store_readiness --write`). Phase: **SHADOW** — no Etsy write, no publication.

**Live state is authoritative.** The owner configured the real shop on 2026-10-06 (logo, banner, title/tagline, About headline/story, Laura's member profile and Designer role). Those fields are never overwritten; drift proposes ADOPT_LIVE_INTO_REPO only. In this environment no live value could be read: no Etsy credential is present (none of ETSY_KEYSTRING, ETSY_API_KEY, ETSY_SHARED_SECRET, ETSY_SHOP_ID), and the public page returned HTTP 403 DataDome CAPTCHA (not bypassed). Every live field is therefore **UNKNOWN** here; production performs the read-back (`etsy.shop_snapshot` → `store.live_drift`).

Counts: DATA-GATED 1, EXTERNAL-GATED 10, NOT-APPLICABLE 2, OWNER-GATED 27, PROVEN 11

| id | area | item | status | live | remaining gate | evidence |
|---|---|---|---|---|---|---|
| SET-A1 | settings | Re-authorise the Etsy app with all scopes incl. transactions_r | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-A2 | settings | Report whether the shop is 'open' (title/announcement fields visible) | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-B1 | settings | Account public profile picture = Brambleloop logo mark (not Laura) | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-B2 | settings | Account preferred name = a real person's name or removed | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-B3 | settings | Account bio blank or one honest line | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-B4 | settings | Two-factor authentication on | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-C1 | settings | Shop name kept as BrambleloopStudio | **EXTERNAL-GATED** | UNKNOWN | live read-back: etsy.shop_snapshot (getShop, shops_r) then store.live_drift in production | owner configured the live shop 2026-10-06 (statement); readback route: getShop.shop_name |
| SET-C2 | settings | Logo / shop icon | **EXTERNAL-GATED** | UNKNOWN | live read-back: etsy.shop_snapshot (getShop, shops_r) then store.live_drift in production | owner configured the live shop 2026-10-06 (statement); readback route: getShop.icon_url_fullxfull |
| SET-C3 | settings | Shop title (tagline) <= 55 chars | **EXTERNAL-GATED** | UNKNOWN | live read-back: etsy.shop_snapshot (getShop, shops_r) then store.live_drift in production | owner configured the live shop 2026-10-06 (statement); readback route: getShop.title |
| SET-C4 | settings | Banner (Big Banner) + phone-crop check in the Etsy app | **EXTERNAL-GATED** | UNKNOWN | live read-back: etsy.shop_snapshot (getShop, shops_r) then store.live_drift in production | owner configured the live shop 2026-10-06 (statement); readback route: getShop.image_url_760x100 + owner phone screenshot |
| SET-C5 | settings | Announcement | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-C6 | settings | About your shop (headline + story, AI disclosure) | **OWNER-GATED** | UNKNOWN | owner records a dated observation of the live field (store_foundation.live_state.record_observation); no API returns it | owner configured the live shop 2026-10-06 (statement); readback route: owner observation |
| SET-C7 | settings | Shop team: legal owner as Owner; Laura not Owner (owner added Laura as Designer) | **OWNER-GATED** | UNKNOWN | owner records a dated observation of the live field (store_foundation.live_state.record_observation); no API returns it | owner configured the live shop 2026-10-06 (statement); readback route: owner observation |
| SET-C8 | settings | About featured photos (certified images only) | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-C9 | settings | Location = Canada (real province) | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-C10 | settings | Listing order = Custom | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-C11 | settings | Sold listings visibility off | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-D1 | settings | Sections: create only populated sections (D-FB-18 item 3) | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-D2 | settings | Featured listings (4 hero listings, once active) | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-E1 | settings | Message to Buyers | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-E2 | settings | Message to Buyers for Digital Items | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-E3 | settings | Order receipt banner (optional) | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-F1 | settings | Returns & exchanges (nothing to create for digital-only) | **NOT-APPLICABLE** | - | - | ETSY_SETTINGS_CHECKLIST.md Batch F |
| SET-F2 | settings | Cancellations setting | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-F3 | settings | Privacy policy | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-F4 | settings | Fixed policies (view only) | **NOT-APPLICABLE** | - | - | ETSY_SETTINGS_CHECKLIST.md Batch F |
| SET-F5 | settings | FAQ incl. pattern licence | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-F6 | settings | EU/Omnibus trader status (owner/legal) | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-G1 | settings | Options: 'Allow buyers to purchase digital prints' = Disabled | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-G2 | settings | Offsite Ads enrolment (owner decision; fee on sale, not spend) | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| SET-G3 | settings | Etsy Ads off (no budget) | **OWNER-GATED** | UNKNOWN | owner login to Etsy (no API writes this in Shadow Mode) | research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md |
| LIVE-1 | live_state | Live-state snapshot record (getShop + owner observation, per-field source/freshness; unread = UNKNOWN) | **PROVEN** | 14/14 fields UNKNOWN here (no Etsy credential in this environment; public page 403 (DataDome CAPTCHA, not bypassed)) | - | store_foundation/live_state.py snapshot(); tests/test_w4_store_live_state.py |
| LIVE-2 | live_state | Drift report repo draft vs live; owner fields authoritative (ADOPT_LIVE_INTO_REPO), never auto-overwrite; proposals only | **PROVEN** | {"UNKNOWN": 14} | - | live_state.drift(); tests/test_w4_store_live_state.py |
| LIVE-3 | live_state | Owner-field write protection (title removed from the updateShop field set; write_refusal/guard) | **PROVEN** | - | - | commerce.shop_package.api_shop_fields; live_state.OWNER_CONFIGURED_API_FIELDS; tests/test_w4_store_live_state.py |
| LIVE-4 | live_state | Read-back/drift job on a cadence (store.live_drift) | **EXTERNAL-GATED** | - | WIRING REQUEST W4-AUTO: CADENCES entry + orchestrator permission; then production getShop credential (A1) | runtime/etsy_ops.py handle_store_live_drift; tests/test_w4_store_live_state.py (runs via Worker) |
| LIVE-5 | live_state | Storefront content model reports entered_on_etsy from live evidence | **PROVEN** | - | - | store_foundation.content.build(db) -> live_state.annotate; tests/test_w4_store_live_state.py |
| LIVE-6 | live_state | Public shop page read | **EXTERNAL-GATED** | - | Etsy bot protection; only the API path is sanctioned (never bypass CAPTCHA) | {"url": "https://www.etsy.com/shop/BrambleloopStudio", "attempted_at": "2026-10-07", "result": "HTTP 403 DataDome CAPTCHA", "bypassed": false} |
| TAX-1 | taxonomy | Seller taxonomy read (getSellerTaxonomyNodes) + crochet pattern subtree, daily listing.taxonomy_refresh | **EXTERNAL-GATED** | TAXONOMY_PATTERNS=66 UNVERIFIED until a real read | a real read needs ETSY_KEYSTRING (api-key only) or a recorded etsy.probe; gate here: ['no ETSY_KEYSTRING/ETSY_API_KEY in this environment'] | integrations/etsy_taxonomy.py refresh(); tests/test_v11_seo_taxonomy.py; tests/test_w3_k1_search.py; worker CADENCES etsy_taxonomy (24h) |
| TAX-2 | attributes | Required attributes per taxonomy (getPropertiesByTaxonomyId) and property contract | **EXTERNAL-GATED** | - | same real read as TAX-1 | EtsyClient.get_taxonomy_properties; integrations/etsy_constraints.py; tests/test_etsy_property_contract.py; tests/test_w3_etsy_constraints.py |
| POL-1 | policies | Policy package (delivery, returns, privacy, licence FAQ, digital sale message) passes package checks | **PROVEN** | - | - | commerce.shop_package.check_package() -> 0 problems; tests/test_shop_package.py |
| POL-2 | policies | Live policy text consistency vs canonical (policy_consistency in etsy.shop_snapshot) | **EXTERNAL-GATED** | - | owner pastes Batch F; then getShop read-back | commerce/policy_consistency.py; tests/test_k8_shop_cx.py |
| IMG-1 | images | Shop icon at Etsy sizes (owner-approved micro-mark, D-FB-18 item 5) | **PROVEN** | UNKNOWN | - | storefront_gate.check_icon() -> 0 findings; asset a3_micro_mark; tests/test_w3_store_ux_gate.py |
| IMG-2 | images | Banner publication gates on the canonical owner banner (D-FB-17/18) | **OWNER-GATED** | UNKNOWN | owner already put a banner live (2026-10-06): live is authoritative and is not replaced. The repo gates still report the findings listed; they go to the owner as findings (D-FB-17 item 2: never silently substitute) | storefront_gate.check_banner() -> 6 findings: STORE_BANNER_OWNER_LAURA_PUBLICATION_STATUS_FAIL, STORE_BANNER_OWNER_LAURA_PHOTOREALISM_ANATOMY_UNKNOWN, STORE_BANNER_OWNER_AI_GENERATED_IMAGERY_DISCLOSURE_UNKNOWN, STORE_BANNER_OWNER_PRODUCT_TRUTH_UNKNOWN, STORE_B |
| IMG-3 | images | Listing image readiness: certified frames in certificate order, alt text, read-back | **PROVEN** | - | real images need certified releases (DATA) and A1 for real upload | runtime/etsy_ops.py certified_images/images_read_back; tests/test_etsy_readback_observe.py; tests/test_w3_etsy_upload_readback.py |
| LST-1 | listings | Listing readiness (release gates, search certificate, ranking readiness) | **DATA-GATED** | - | needs certified releases with listing-set + search certificates in the production DB (none in this environment) | publish/release_gates.py; commerce/ranking_readiness.py; tests/test_ranking_readiness.py; tests/test_listing_parity_gate.py |
| LST-2 | listings | Sections: only populated categories exposed (D-FB-18 item 3) | **PROVEN** | - | - | populated: ['Home', 'Baby']; hidden (planned): ['Wearables', 'Gifts', 'Seasonal', 'Blankets']; store_foundation.navigation; tests/test_w3_store_ux_structure.py |
| UPL-1 | upload_readback | Draft -> image upload -> file -> read back -> delete probe, field-by-field verification | **PROVEN** | - | real-Etsy confirmation needs A1 re-authorisation; stays LOCALLY_TESTED until then | integrations/etsy_verify.py; integrations/etsy_probe.py; tests/test_w3_etsy_upload_readback.py; tests/test_etsy_readback_observe.py (FakeEtsy contract) |
| UPL-2 | upload_readback | Daily listing census + field drift (never overwrite) | **PROVEN** | - | real census needs the production credential | etsy.listing_census; tests/test_etsy_readback_observe.py test_a_listing_edited_on_etsy_is_field_drift_and_is_never_overwritten |
| ANA-1 | analytics | Etsy Stats CSV intake (listing-level) -> ListingOutcome, strict, blank != zero | **PROVEN** | - | DATA: first owner export after listings are live | commerce/listing_outcomes.py submit_export/produce; commerce/attribution.py parse_stats_csv; tests/test_k3_listing_outcomes.py; tests/test_w3_spend_attribution.py |
| ANA-2 | analytics | API read of views/favourites (impressions/carts stay UNKNOWN) | **EXTERNAL-GATED** | - | production credential + active listings | commerce/listing_outcomes.py (getListingsByShop) |
| PUB-1 | publication | Publication pipeline (store.publish drafts; store.activate only on read-back proof + owner authority at execution time) | **OWNER-GATED** | - | phase stays SHADOW; activation needs owner launch authorisation + certified releases + A1 | runtime/pipeline.py handle_store_publish; runtime/etsy_ops.py; tests/test_etsy.py; tests/test_draft_creation_durability.py; tests/test_etsy_readback_observe.py |

## Live drift (repo draft vs live)

| field | owner-configured | status | source | proposal |
|---|---|---|---|---|
| shop_name | yes | UNKNOWN | - | OWNER_CONFIRM |
| shop_icon | yes | UNKNOWN | - | OWNER_CONFIRM |
| shop_banner | yes | UNKNOWN | - | OWNER_CONFIRM |
| shop_title | yes | UNKNOWN | - | OWNER_CONFIRM |
| about_headline | yes | UNKNOWN | - | OWNER_OBSERVE |
| about_story | yes | UNKNOWN | - | OWNER_OBSERVE |
| laura_member_profile | yes | UNKNOWN | - | OWNER_OBSERVE |
| laura_member_role | yes | UNKNOWN | - | OWNER_OBSERVE |
| announcement | no | UNKNOWN | - | OWNER_CONFIRM |
| digital_sale_message | no | UNKNOWN | - | OWNER_CONFIRM |
| policy_privacy | no | UNKNOWN | - | OWNER_CONFIRM |
| policy_refunds | no | UNKNOWN | - | OWNER_CONFIRM |
| policy_shipping | no | UNKNOWN | - | OWNER_CONFIRM |
| policy_additional | no | UNKNOWN | - | OWNER_CONFIRM |

## Owner actions for the store (batched)

| id | exact action | why | max cost | min | if you wait |
|---|---|---|---|---|---|
| OA-A1 | Re-authorise the Etsy app: Command Center GET /api/etsy/oauth/start -> Allow all scopes incl. transactions_r | the only route to a real read-back of the live shop (title, icon, banner), taxonomy, upload proof and orders | CA$0 | 5 | every live field stays UNKNOWN; nothing real can be verified |
| OA-OBS | Record what the live shop shows for the fields no API returns: About headline, About story, Laura's member bio and role (paste text; one dated observation) | lets the drift job treat your configuration as authoritative and check it (Laura disclosed as AI, not in the Owner role) without touching it | CA$0 | 5 | About/Laura fields stay UNKNOWN; previews may show stale repo drafts |
| OA-A2 | Report whether the shop is 'open' (title/announcement editable) | decides whether announcement can be set now | CA$0 | 1 | C5 stays blocked |
| OA-B | Account settings: profile picture = logo mark, real preferred name, short bio, 2FA on (Batch B) | the account picture/name present the legal account holder; Laura must not appear as the account holder | CA$0 | 5 | a persona could read as the legal owner |
| OA-BANNER | Phone check: open the shop in the Etsy app, screenshot the banner; and decide on the banner gate findings listed in IMG-2 (nav footer shows Wearables/Gifts/Seasonal, which have no products yet; Laura publication status) | the live banner is yours and is not replaced; Etsy publishes no mobile crop, and the repo gates found items only you can rule on | CA$0 | 3 | crop/footer findings stay unresolved |
| OA-C | Shop settings still open: announcement (C5), location (C9), listing order Custom (C10), sold visibility off (C11) | trust surfaces and ordering | CA$0 | 5 | shop snapshot keeps reporting missing trust surfaces |
| OA-D1 | Create sections for populated categories only (today: Home, Baby) | D-FB-18 item 3: never advertise empty categories | CA$0 | 3 | listings land unsectioned |
| OA-E | Info & Appearance: Message to Buyers + Message for Digital Items (Batch E) | the digital message is the only text every buyer receives at purchase | CA$0 | 3 | first buyers get no download guidance |
| OA-F | Policy Settings: privacy policy, FAQ with licence, cancellations (Batch F) | Etsy trust surfaces; licence belongs in the FAQ for a Canadian shop | CA$0 | 10 | policy_consistency stays failing |
| OA-G1 | Settings > Options: 'Allow buyers to purchase digital prints' = Disabled | a third party would sell printed copies of a pattern PDF | CA$0 | 1 | auto-enrolment may put a third-party product beside ours |
| OA-G2 | Offsite Ads: decide enrolment (15% fee on attributed sales, no fixed spend) | a margin decision, recorded rather than defaulted | 15% of attributed orders (cap US$100/order) | 1 | default enrolment stands |
| OA-STATS | After the first listings are live: export the listing-level Etsy Stats CSV and upload it (POST /api/attribution/stats) | impressions/carts are not in the API; the CSV is the only measurement | CA$0 | 3 | funnel stays UNMEASURED |
| OA-LAUNCH | Launch authorisation for the first listings (separate gated approval) | no listing is activated without it | CA$0 | 5 | the shop stays without listings |

Total owner time: ~50 minutes. OA-A1 and OA-OBS unblock the live read-back; the rest can follow in any order.
