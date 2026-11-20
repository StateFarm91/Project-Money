# The Etsy surface registry: what software may do with each Shop Manager page

**Written:** 2026-09-25 (UTC). **Phase:** SHADOW. **By:** Lane D, Etsy shop readiness, working
in an isolated worktree.

**Nothing in this document was learned by calling Etsy.** No authenticated request was made,
no listing was created or changed, no setting was touched, no promotion was started, and CA$0
was spent. Every PRIMARY claim below is read from two documents Etsy publishes about itself,
both fetched successfully from this environment on 2026-09-25:

| Source | Status | Identity |
|---|---|---|
| `https://www.etsy.com/openapi/generated/oas/3.0.0.json` | HTTP 200 | document version 3.0.0, 908,638 bytes, **SHA-256 `e6f95f1a38810cadf920796bc0e08797fb499312c8b50f317454e6ebd39531f7`**, 76 paths, **105 operations** |
| `https://developer.etsy.com/documentation/essentials/webhooks/` | HTTP 200 | the order-event push and the portal that configures it |
| `https://developer.etsy.com/documentation/essentials/authentication/` | HTTP 200 | the twelve OAuth scopes |
| `https://developer.etsy.com/documentation/tutorials/shopmanagement/` | HTTP 200 | what `updateShop` changes, in Etsy's words |
| `https://developer.etsy.com/documentation/essentials/rate-limits/` | HTTP 200 | QPS/QPD sliding window |
| `https://help.etsy.com/hc/en-us/` | **HTTP 403** | refused every automated request, with and without a browser user agent |
| `https://www.etsy.com/legal/fees/` | **HTTP 403** | the fee schedule cannot be read from here |

The two 403s are why several entries below are labelled SECONDARY. That label is not
decoration: it is the difference between a sentence Etsy wrote and a sentence somebody on the
internet wrote about Etsy, and the registry refuses to let the second one be cited as the
first. **The surface names and their Shop Manager locations are themselves SECONDARY** — they
come from the owner's own reading of Shop Manager, because nobody here has seen the page.
Every verdict about *what the API does* is PRIMARY.

The registry is code, not prose: `src/brambleloop/intel/etsy_surfaces.py`, with 52 checks in
`tests/test_etsy_surfaces.py`. This document is its reading.

---

## 0. The six answers, and the three findings that matter

**35 surfaces classified.** OBSERVE 6, ANALYZE 1, ACT 4, OWNER-ONLY 10, NOT-APPLICABLE 5,
UNSUPPORTED 9.

**Finding 1 — this shop cannot see its own first sale.** Etsy publishes a complete order read:
`getShopReceipts` and five related operations return the status, the totals, the tax, the
buyer's message and the transactions, and Etsy will even push `order.paid` the instant payment
clears. Every one of those requires the `transactions_r` scope. The scope set Etsy granted this
shop on 2026-09-25 is `listings_r listings_w listings_d shops_r shops_w`. **`transactions_r` is
not in it**, and a refresh grant "has the same scope as the token granted by the initial
Authorization Code grant", so no amount of refreshing widens it. Nothing published so far in
this repository had noticed: the OAuth work correctly recorded what was asked for and what was
granted, and nobody compared either against what the order path needs. The fix is a six-minute
browser re-authorisation, and it is in the owner queue.

**Finding 2 — no ad-spend ceiling can be enforced in code, and this is not fixable.** The
Execution Directive requires budget ceilings enforced in code. For Etsy Ads that is not
available: the string `advertis` appears **zero** times in Etsy's API document, along with
`campaign` 0, `budget` 0 and `impression` 0. Nor is the spend readable after the fact — the
ledger entry description enumerates its kinds as *"a payment, refund, reversal of a failed
refund, disbursement, returned disbursement, recoupment, miscellaneous credit, miscellaneous
debit, or bill payment"*, and advertising is not among them. The only control available is that
nobody turns it on. That is a promise, not a ceiling, and the registry records it as one.

**Finding 3 — the pricing floor was computed from an incomplete fee model that read as
complete.** `offsite` appears **zero** times in Etsy's document: not as an endpoint, not as a
setting, and not as a fee line on a receipt, a payment or a ledger entry. So the largest fee
this shop may pay is one that cannot be opted out of by API, cannot be set by API, and cannot
be attributed to an order by API. `commerce/pricing.py` modelled 6.5% + 3% + CA$0.25 + the
amortised listing fee and reported a take rate of 13.7% on a CA$6.50 pattern as though that
were the cost of selling. With the three unmodelled fees at their reported rates the take rate
is **32.3%** and the net falls from CA$5.61 to CA$4.40. The fix is not to fold a blog's number
into the constant — that would turn an unverified figure into one that looks measured. The fix
is that the incompleteness now travels with the answer (§5).

---

## 1. How the six verdicts are defined, and why two of them are kept apart by force

| Verdict | Means |
|---|---|
| **ACT** | Etsy exposes a write this company may make, so software can change the surface's state. |
| **OBSERVE** | Etsy exposes the surface's own state to a read this company may make. It cannot change it. |
| **ANALYZE** | Etsy exposes nothing for this surface. A legitimate **proxy** is computable from data it does expose, and the proxy is labelled a proxy everywhere it is used. |
| **OWNER-ONLY** | No API, and something here is a person's job. Carries an owner-action entry, always. |
| **NOT-APPLICABLE** | The surface does not apply to a shop that sells digital patterns. Carries a reason in words. |
| **UNSUPPORTED** | Etsy offers no API for it. Carries a **reproducible, counted absence**, always. |

The brief was explicit that UNSUPPORTED and NOT-APPLICABLE are different claims, so the
registry enforces the difference rather than describing it. `check_registry()` refuses an
UNSUPPORTED verdict with no absence probe and a NOT-APPLICABLE verdict with no reason, and a
test proves each rule fires against a deliberately broken surface.

**Delivery Settings is the entry that shows why this matters.** Etsy ships *thirteen*
shipping-profile operations — a full CRUD surface — and it is still nothing to do with us,
because `shipping_profile_id` is *"Required when listing type is `physical`"*. Recorded as
UNSUPPORTED it would say something false about Etsy. Recorded as a gap it would put thirteen
endpoints on a build list forever. **Etsy Ads is the mirror image**: central to how sellers are
told to grow, and there is no endpoint, no scope and no field.

**Where a surface is split down the middle, the verdict names the governing half and never the
flattering one.** Messages has exactly one automated write (`digital_sale_message`) and no
read at all, so it is OWNER-ONLY, not ACT. Sales & Discounts has a read and no write, so it is
OBSERVE, not ACT.

---

## 2. The registry

Every row's evidence is labelled by kind. **OAS** = a sentence or schema element in Etsy's
OpenAPI document. **OAS-ABSENCE** = a counted, reproducible absence in that document.
**DEV-DOC** = a sentence on developer.etsy.com. **SECONDARY** = from a source this environment
could not read. **DECISION** = a decision of this company, not a fact about Etsy. **INFERRED**
= our reading, arguable. **UNKNOWN** = genuinely not established, and not filled in.

<!-- generated from intel/etsy_surfaces.py; regenerate rather than edit by hand -->

| # | Surface (Shop Manager) | Verdict | Required before first sale | Class | Etsy operations | Scope | Evidence and provenance |
|---|---|---|---|---|---|---|---|
| 1 | Dashboard<br>`dashboard`<br>*Shop Manager > Dashboard* | **UNSUPPORTED** | no | - | **none** | -- | **OAS-ABSENCE** 'dashboard' appears 0 times in Etsy's OpenAPI document.<br><br>**OAS** The document's 27 tags are User, Shop, ShopListing, Receipt, Payment, Ledger Entry, Taxonomy, Review and their sub-resources. None of them is an aggregate view.<br><br>**INFERRED** The dashboard is a composition of surfaces below, so it inherits their verdicts rather than having one of its own. Nothing is lost by having no API for the composition; what is lost is the notices Etsy only shows here, which is handled under policy_violations. |
| 2 | Listings<br>`listings`<br>*Shop Manager > Listings* | **ACT** | **yes** (etsy) | A | `createDraftListing`, `updateListing`, `updateListingInventory`, `uploadListingImage`, `uploadListingFile`, `uploadListingVideo`, `updateListingProperty`, `getListingsByShop`, `getListing`, `getListingImages`, `deleteListing` | `listings_w` `listings_r` `listings_d` | **OAS** POST /shops/{shop_id}/listings creates a draft; PATCH /shops/{shop_id}/listings/{listing_id} updates it; both list application/x-www-form-urlencoded as their only media type and both require listings_w.<br><br>**OAS** "Setting a `draft` listing to `active` will also publish the listing on etsy.com and requires that the listing have an image set."<br><br>**OAS** updateListing has no `price` property: price is set by PUT /listings/{listing_id}/inventory, which is the only application/json write in the whole document.<br><br>**INFERRED** The write path is implemented in `integrations/etsy.py` and has never created a listing on Etsy. ACT here means Etsy offers the write and we hold the scope, not that the round trip has been demonstrated. |
| 3 | Messages<br>`messages`<br>*Shop Manager > Messages* | **OWNER_ONLY** | **yes** (this_company) | A | `updateShop` | `shops_w` | **OAS-ABSENCE** 'conversation' appears once in the whole document, in the description of `vacation_autoreply`. There is no Messages, Conversation or Thread resource, no read, no send, no scope.<br><br>**DEV-DOC** The one message the API can cause: updateShop sets `digital_sale_message`, "A message sent to the buyer's Etsy messages when they purchase any digital product from this shop".<br><br>**OAS** A receipt carries `message_from_buyer`, "An optional message string from the buyer" -- the note attached to an order, not the inbox, and it needs transactions_r.<br><br>**DECISION** Verdict is OWNER_ONLY rather than ACT because the governing half of this surface -- reading a buyer's question and answering it -- is a person's, and calling the surface ACT because one automated message exists would be the flattering half. |
| 4 | Orders & Delivery<br>`orders`<br>*Shop Manager > Orders & Delivery* | **OBSERVE** | **yes** (this_company) | A | `getShopReceipts`, `getShopReceipt`, `getShopReceiptTransactionsByShop`, `getShopReceiptTransactionsByReceipt`, `getListingsByShopReceipt` | `transactions_r` | **OAS** GET /shops/{shop_id}/receipts and five related reads return the whole order: status (`paid`, `completed`, `open`, `payment processing`, `canceled`), totals, tax, VAT, discount, the buyer's message and the transactions.<br><br>**DEV-DOC** Etsy pushes four webhook events and all four are orders: order.paid, order.canceled, order.shipped, order.delivered. "order.paid -- delivered immediately when an order receives payment."<br><br>**OAS** Every one of those reads requires the transactions_r scope.<br><br>**INFERRED** transactions_r is NOT in the scope set Etsy granted this shop on 2026-09-25. As things stand this system cannot see its own first sale -- not the order, not the buyer's note, not the money. The read exists; the authorisation does not.<br><br>**OAS** updateShopReceipt and createReceiptShipment exist and write fulfilment state; for a digital download there is nothing to ship, so this company will not call them. |
| 5 | Etsy Search Visibility<br>`search_visibility`<br>*Shop Manager > Marketing > Etsy Search Visibility* | **ANALYZE** | no | C | `findAllListingsActive` | -- | **OAS-ABSENCE** 'seo' 0, 'impression' 0, 'visit' 0, 'traffic' 0. Etsy publishes none of its own search-visibility numbers.<br><br>**OAS** What does exist is the public marketplace search: GET /listings/active takes `keywords`, `taxonomy_id`, `min_price`, `max_price` and `sort_on=score`, on the API key alone.<br><br>**INFERRED** So a rank probe is computable -- does our listing appear in the API's ranked results for keyword K, and at what position. It is a **proxy**: it measures the API's search index, not the buyer-facing etsy.com ranking, and it cannot see impressions at all. Anywhere it is used it must say so. |
| 6 | Stats (Shop Traffic)<br>`stats`<br>*Shop Manager > Stats* | **UNSUPPORTED** | no | D | **none** | -- | **OAS-ABSENCE** 'stats' 0, 'statistic' 0, 'traffic' 0, 'visit' 0, 'impression' 0 in Etsy's OpenAPI document.<br><br>**OAS** The nearest readable numbers are counters on other objects -- Shop.num_favorers, Listing.num_favorers, Shop.review_count, Shop.transaction_sold_count. They are totals with no time series and no source breakdown.<br><br>**DECISION** A paste-in ingest, where the owner copies figures out of Shop Manager, is buildable and is not a collector. If it is ever built its records must be labelled as owner-reported, never merged into anything that reads as measured. |
| 7 | Marketplace Insights<br>`marketplace_insights`<br>*Shop Manager > Marketing > Marketplace Insights* | **UNSUPPORTED** | no | C | **none** | -- | **OAS-ABSENCE** 'insight' 0 in Etsy's OpenAPI document.<br><br>**INFERRED** `radar/` and `intel/` already compute demand signals from the public listing search and from the benchmark shop. Those are our measurements of the marketplace, not Etsy's insights, and conflating them would put Etsy's authority behind our arithmetic. |
| 8 | Customer Service Stats<br>`customer_service_stats`<br>*Shop Manager > Stats > Customer Service* | **UNSUPPORTED** | no | D | **none** | -- | **OAS-ABSENCE** 'stats' 0 and no case, dispute-count or response-time resource. 'dispute' appears twice, both in Shop.include_dispute_form_link, a boolean about whether the shop's policies link to the EU online dispute form.<br><br>**OAS** Shop.review_count is "Number of reviews of shop listings in the past year" and Shop.review_average is the mean. Those are reviews, which is a different surface, and using them as a service metric would be a category error. |
| 9 | Policy Violations<br>`policy_violations`<br>*Shop Manager > Policy Violations (and Dashboard notices)* | **OWNER_ONLY** | no | B | `getListingsByShop` | `listings_r` | **OAS-ABSENCE** 'violation' 0 and 'infringement' 0 in Etsy's OpenAPI document. There is no notice, case or appeal resource.<br><br>**OAS** The one indirect signal: getListingsByShop (listings_r) returns each listing's state, and the document's own state note includes "seller flags: SUPRESSED (frozen)". A listing that disappears or changes state is visible; the reason is not.<br><br>**INFERRED** So the honest design is an alarm, not a report: `listing_census_drift()` detects that something happened to a listing and hands it to a person, who is the only one who can read why. It must never be allowed to print a reason. |
| 10 | Etsy Ads<br>`etsy_ads`<br>*Shop Manager > Marketing > Etsy Ads* | **UNSUPPORTED** | no | D | **none** | -- | **OAS-ABSENCE** 'advertis' 0, 'campaign' 0, 'budget' 0, 'impression' 0. There is no Ads resource, no scope and no field.<br><br>**OAS** Nor is ad spend separately readable after the fact: the ledger entry description enumerates its kinds as "a payment, refund, reversal of a failed refund, disbursement, returned disbursement, recoupment, miscellaneous credit, miscellaneous debit, or bill payment" -- advertising is not among them.<br><br>**INFERRED** This is a governance finding, not just a capability gap. The Execution Directive requires budget ceilings enforced in code. For Etsy Ads that is impossible: software can neither set a budget nor read the spend. The only control available is that nobody turns it on, which is a promise rather than a ceiling, and it has to be recorded as one. |
| 11 | Offsite Ads<br>`offsite_ads`<br>*Shop Manager > Marketing > Offsite Ads* | **UNSUPPORTED** | no | D | **none** | -- | **OAS-ABSENCE** 'offsite' appears 0 times in Etsy's OpenAPI document -- not as an endpoint, not as a setting, and not as a fee line on a receipt, a payment or a ledger entry.<br><br>**SECONDARY** Widely reported third-party figures put the fee at 12% or 15% of the order total on attributed orders, with participation compulsory above a revenue threshold. Etsy's own fees page is HTTP 403 from this environment, so this is SECONDARY and the rate is not treated as known.<br><br>**INFERRED** The combination is what matters: the largest fee this shop may pay is one it cannot opt out of by API, cannot see by API, and cannot attribute to an order by API. The only defence available to software is a price that survives it, which is why `commerce/pricing.py` now carries the fee as an explicitly unmodelled one. |
| 12 | Sales & Discounts<br>`sales_and_discounts`<br>*Shop Manager > Marketing > Sales and Discounts* | **OBSERVE** | no | C | `getListingsByListingIds` | -- | **OAS-ABSENCE** 'coupon' 8 and 'discount' 21, and every one of the 29 is read-only. No endpoint creates a sale, a coupon or an offer.<br><br>**OAS** GET /listings/batch returns a buyer-price block with `has_discount`, `discount_percentage`, `discount_amount`, `discount_start_epoch` and `discount_end_epoch`, and the document says it is "Currently only supported on the /listings/batch endpoint" and "Requires buyer_country parameter".<br><br>**INFERRED** So a sale started in a browser is observable and a sale is not creatable. That asymmetry is useful rather than annoying: it means a discount nobody here authorised would be visible.<br><br>**DECISION** Section 9 forbids the category's near-universal fake sale. Whatever this surface could do, a struck-through price this shop never charged is not available to it, and `commerce.pricing.check_no_fake_discount` already refuses one. |
| 13 | Social Media<br>`social_media`<br>*Shop Manager > Marketing > Social Media* | **UNSUPPORTED** | no | C | **none** | -- | **OAS-ABSENCE** 'social' 0 in Etsy's OpenAPI document.<br><br>**INFERRED** Nothing is lost by the absence: this company's owned-channel work lives in `growth/owned.py` under a CASL consent gate, and routing posts through Etsy's composer would put content outside that gate. |
| 14 | Share & Save<br>`share_and_save`<br>*Shop Manager > Marketing > Share & Save* | **UNSUPPORTED** | no | D | **none** | -- | **OAS-ABSENCE** No term for it appears in Etsy's OpenAPI document: no enrolment flag, no share-link resource, and no fee line that could show its effect.<br><br>**SECONDARY** What the programme actually is, and what it costs or saves, is described only on help.etsy.com, which is 403 from here. The description above is SECONDARY and should be confirmed by the owner in a browser before any decision rests on it. |
| 15 | Payment Account<br>`payment_account`<br>*Shop Manager > Finances > Payment account* | **OBSERVE** | no | D | `getShopPaymentAccountLedgerEntries`, `getShopPaymentAccountLedgerEntry`, `getPayments`, `getShopPaymentByReceiptId`, `getPaymentAccountLedgerEntryPayments` | `transactions_r` | **OAS** GET /shops/{shop_id}/payment-account/ledger-entries returns entry_id, amount, currency, balance, create_date, ledger_type, reference_type and reference_id, and requires min_created and max_created.<br><br>**OAS** Payment carries amount_gross, amount_fees, amount_net and their posted and adjusted forms, so per-order economics are readable once a payment exists.<br><br>**OAS** The ledger entry `description` enumerates the kinds of entry and names no advertising fee, so fee attribution is coarser than Shop Manager's own view.<br><br>**INFERRED** Requires transactions_r, which this shop has not granted. Today the verdict is a capability Etsy offers and we are not authorised to use. |
| 16 | Monthly Statements<br>`monthly_statements`<br>*Shop Manager > Finances > Monthly statements* | **UNSUPPORTED** | no | D | **none** | -- | **OAS-ABSENCE** 'statement' appears twice and both are "shipment statements" on a receipt. There is no statement document, no download and no monthly aggregate.<br><br>**OAS** The underlying entries are readable through the ledger (see payment_account), so the *data* is reachable with transactions_r even though the *document* is not.<br><br>**INFERRED** The statement is still the authority for what Etsy charged, and the ledger is our reconstruction of it. Where the two disagree the statement wins, which is the reason to keep the owner action below rather than declaring the ledger sufficient. |
| 17 | Payment Settings<br>`payment_settings`<br>*Shop Manager > Finances > Payment settings* | **OWNER_ONLY** | **yes** (etsy) | A | `getShop` | -- | **OAS-ABSENCE** No banking, payout, deposit or billing resource exists. 'payout' 0, 'deposit' 0; the single occurrence of 'bank' is inside an unrelated word.<br><br>**OAS** One bit of it is observable: Shop.is_etsy_payments_onboarded, "When true, the shop has onboarded onto Etsy Payments" -- readable on the API key alone through getShop, which makes it a check rather than an assertion.<br><br>**INFERRED** That one boolean is the difference between this surface and legal_and_tax: the owner's action here produces evidence a collector can read back. |
| 18 | Legal and tax information<br>`legal_and_tax`<br>*Shop Manager > Finances > Legal and tax information* | **OWNER_ONLY** | **yes** (law_or_regulator) | A | **none** | -- | **OAS-ABSENCE** 'identity' 0, 'kyc' 0, 'gst' 0. No identity, entity or tax-registration resource exists. The 190 occurrences of 'tax' are receipt tax amounts and the taxonomy, neither of which is a tax setting.<br><br>**DECISION** The non-negotiables forbid bypassing KYC, identity verification or legal acceptance, so even if an endpoint existed this company would not use it.<br><br>**INFERRED** Whether to register for GST/HST, and whether to give Etsy the number, is a tax position with a consequence and is the owner's alone. `commerce/shop_package.CLAIMS` carries the CRA primary source and the reasoning; it deliberately takes no position. |
| 19 | Apps<br>`apps`<br>*Shop Manager > Apps* | **NOT_APPLICABLE** | no | - | **none** | -- | **OAS-ABSENCE** No resource lists or manages installed apps, so a third-party app installed in a browser would also be invisible to this system.<br><br>**DECISION** NOT_APPLICABLE rather than UNSUPPORTED: the deciding fact is our decision not to use the surface, which makes the API question moot.<br><br>**WHY N/A** This company integrates with Etsy through its own registered application, which it controls end to end. Installing a third-party app would put shop writes behind software this repository cannot inspect, audit or gate, and the Execution Directive's refusal ladder could not reach them. |
| 20 | Help<br>`help`<br>*Shop Manager > Help* | **NOT_APPLICABLE** | no | - | **none** | -- | **OAS-ABSENCE** No support-case resource exists; 'case' appears 23 times, all in unrelated words such as 'in case' and 'lowercase'.<br><br>**SECONDARY** help.etsy.com returns HTTP 403 to every automated request from this environment, which is why a great deal of this registry's context is secondary and says so.<br><br>**WHY N/A** The surface carries no shop state: nothing here can be right or wrong, fresh or stale. That is a claim about state, not about usefulness -- it is the escape hatch when something goes wrong, and it is reached under policy_violations. |
| 21 | Your Shop (storefront)<br>`your_shop`<br>*Shop Manager > Your shop* | **ACT** | **yes** (this_company) | A | `updateShop`, `createShopSection`, `getShop`, `getShopSections` | `shops_w` `shops_r` | **OAS** PUT /shops/{shop_id} accepts exactly five fields: title, announcement, sale_message, digital_sale_message, policy_additional. That is the whole write surface of the shop object.<br><br>**DEV-DOC** Etsy's own shop-management tutorial lists four of them -- "title, announcement, sale_message, digital_sale_message" -- and omits policy_additional, which the request schema does accept. The schema is the stronger evidence; the discrepancy is recorded rather than resolved.<br><br>**OAS** getShop returns the storefront's readable state on the API key alone: title, announcement, all six policy strings, icon_url_fullxfull, image_url_760x100, listing_active_count, digital_listing_count, review_count, num_favorers.<br><br>**INFERRED** Verdict is ACT because the fields that carry this company's decisions are writable and the rest is at least readable. The About story, banner and icon are not, and live under info_and_appearance. |
| 22 | Info & Appearance<br>`info_and_appearance`<br>*Shop Manager > Settings > Info & appearance* | **OWNER_ONLY** | **yes** (this_company) | A | `updateShop`, `getShop` | `shops_w` | **OAS** Shop.image_url_760x100 (banner) and Shop.icon_url_fullxfull are read-only URLs on the Shop object. updateShop's request schema contains no image field and no About field.<br><br>**OAS** Only `title` from this page is writable, through updateShop.<br><br>**INFERRED** The bulk of the page -- the two images and the About story, which are the whole of a first impression -- can only be typed and uploaded by a person, so the verdict is OWNER_ONLY even though one field is writable.<br><br>**DECISION** That a shop needs a banner, an icon and an About before opening is this company's judgement about buyer trust at zero reviews, not a rule of Etsy's that we have read. Labelled BY_US deliberately. |
| 23 | Options<br>`options`<br>*Shop Manager > Settings > Options* | **OBSERVE** | **yes** (this_company) | A | `getShop` | -- | **OAS** is_vacation, vacation_message, vacation_autoreply, currency_code, languages, shop_location_country_iso and shop_name are all present on the Shop object and none of them is in updateShop's request schema.<br><br>**OAS** updateHolidayPreferences (PUT, shops_w) exists but governs shipping holidays, which a digital shop does not have.<br><br>**INFERRED** So every setting on this page is readable and none is writable: OBSERVE exactly. That makes them checkable, which is worth more here than writable -- a shop left in vacation mode, or set to the wrong currency, is silent failure, and `assess_shop` checks both. |
| 24 | Shared Access<br>`shared_access`<br>*Shop Manager > Settings > Shared access* | **OWNER_ONLY** | no | B | **none** | -- | **OAS-ABSENCE** 'shared access' 0 in Etsy's OpenAPI document. No resource lists, grants or revokes shop access.<br><br>**INFERRED** This is a security surface rather than an operational one. An attacker who reached the account once would persist here, and nothing in this repository could see it. Cheap to check, invisible to software, so it becomes a standing owner action rather than a gap we note and forget. |
| 25 | Delivery Settings<br>`delivery_settings`<br>*Shop Manager > Settings > Delivery settings* | **NOT_APPLICABLE** | no | - | `getShopShippingProfiles` | -- | **OAS** Etsy ships thirteen shipping-profile operations, a full CRUD surface -- so this is emphatically not a case of Etsy offering nothing.<br><br>**OAS** And it still does not apply: shipping_profile_id is "Required when listing type is `physical`", and readiness_state_id is "Returned only when the listing is `active` and of type `physical`".<br><br>**INFERRED** This entry is the reason the registry keeps NOT_APPLICABLE and UNSUPPORTED apart. Recorded as UNSUPPORTED it would say something false about Etsy; recorded as a gap it would put thirteen endpoints on a build list forever.<br><br>**WHY N/A** Everything on this page describes moving a physical object. A digital pattern is delivered by Etsy as a download the instant payment clears; there is no origin, no carrier, no processing time and no destination. |
| 26 | Policy Settings<br>`policy_settings`<br>*Shop Manager > Settings > Policies* | **OWNER_ONLY** | **yes** (this_company) | A | `updateShop`, `getShop`, `getShopReturnPolicies` | `shops_w` | **OAS** Shop carries policy_welcome, policy_payment, policy_shipping, policy_refunds, policy_additional, policy_seller_info and policy_privacy, each "(may be blank)". updateShop's request schema contains exactly one of them: policy_additional.<br><br>**OAS** The structured return-policy resource (createShopReturnPolicy and four others) exists, and return_policy_id is "Required for active physical listings" -- so it is not the surface a download shop needs.<br><br>**SECONDARY** Etsy's own announcement: "Sellers will no longer be able to accept returns on digital listings given the nature of the items", quoted in `commerce/shop_package.py` from Etsy's community announcement.<br><br>**INFERRED** Six of the seven policy strings a buyer actually reads can only be typed. They are written and held in `commerce/shop_package.policies()`; what is missing is a person to paste them. That they are *readable* is what makes the paste checkable. |
| 27 | Partners You Work With<br>`production_partners`<br>*Shop Manager > Settings > Production partners* | **NOT_APPLICABLE** | no | - | `getShopProductionPartners` | `shops_r` | **OAS** getShopProductionPartners is read-only and requires shops_r. No endpoint creates or edits one, so even a shop that needed partners would declare them in a browser.<br><br>**INFERRED** The trap worth naming: an empty partner list is what a correctly configured shop looks like **and** what a shop nobody has read looks like. No check in this repository may turn that emptiness into a pass -- which is exactly why `EvidenceState` exists.<br><br>**UNKNOWN** Whether Etsy considers a generative model used for listing imagery a production partner. Etsy's guidance is on help.etsy.com, which is 403 here. The AI-disclosure question is handled in `gates/platform_policy` and in the listing description; this entry records the doubt rather than resolving it.<br><br>**WHY N/A** A production partner is somebody who helps make the physical item a buyer receives. This shop sells a document it wrote and compiled itself; there is no third party in the making of it. |
| 28 | Subscription (Etsy Plus)<br>`subscription`<br>*Shop Manager > Settings > Subscriptions* | **OWNER_ONLY** | no | B | **none** | -- | **OAS-ABSENCE** 'subscription' 0 in Etsy's OpenAPI document. No subscription state, no enrolment, no charge line.<br><br>**INFERRED** A subscription is a recurring charge that software here can neither see nor stop, which makes it the same class of problem as Etsy Ads: a spend outside every ceiling this repository enforces. The control available is a person confirming it is off. |
| 29 | Sales channels<br>`sales_channels`<br>*Shop Manager > Settings > Sales channels* | **NOT_APPLICABLE** | no | - | **none** | -- | **OAS** The channel of a sale is observable after the fact, under the orders surface and its transactions_r scope: ShopReceipt.receipt_type is "0 or 5 for Etsy.com, 1 for a Pattern shop". It is recorded under orders rather than here so that this entry does not appear as a scope gap for a surface we have decided not to use.<br><br>**OAS** And the listing-state note mentions seller flags "CUSTOM_SHOPS (pattern), SELL_ON_FACEBOOK", so channels exist as flags on objects rather than as a manageable resource.<br><br>**INFERRED** No endpoint enables, disables or configures a channel. If this decision is ever revisited, the work is a browser action and a subscription, not an integration.<br><br>**WHY N/A** This company sells on etsy.com and nowhere else. Pattern is a separate paid subscription and no decision to buy one exists; opening a second storefront before the first has a customer would be building a channel for a product with no demonstrated demand. |
| 30 | Shop sections<br>`shop_sections`<br>*Shop Manager > Your shop > Sections* | **ACT** | no | B | `createShopSection`, `updateShopSection`, `deleteShopSection`, `getShopSections` | `shops_w` | **OAS** POST /shops/{shop_id}/sections takes one required field, `title`, form-encoded, under shops_w. Reading sections needs no OAuth scope at all.<br><br>**INFERRED** The six sections are already decided in `brand/storefront.py`; creating them is a call nobody has written yet. It is a launch-week task rather than a blocker: a shop with three listings and no sections is untidy, not unsellable. |
| 31 | Digital files<br>`digital_files`<br>*Shop Manager > Listings > (a listing) > Digital files* | **ACT** | **yes** (etsy) | A | `uploadListingFile`, `getAllListingFiles`, `getListingFile`, `deleteListingFile` | `listings_w` `listings_r` | **OAS** POST /shops/{shop_id}/listings/{listing_id}/files, multipart/form-data, with the binary in a part named `file` -- distinct from the images endpoint, whose part is named `image`.<br><br>**INFERRED** The two endpoints disagreeing about the part name is a defect this repository has already hit once: a single hard-coded `file` produced a well-formed upload in which Etsy found no image.<br><br>**UNKNOWN** Etsy's per-file size and count limits for digital listings are not in the OpenAPI document and the help page that carries them is 403 here. A deliverable larger than the limit would fail at upload, not at compile. |
| 32 | Category & attributes<br>`taxonomy_and_attributes`<br>*Shop Manager > Listings > (a listing) > Category* | **OBSERVE** | **yes** (etsy) | A | `getSellerTaxonomyNodes`, `getPropertiesByTaxonomyId`, `getListingProperties`, `updateListingProperty` | `listings_w` | **OAS** taxonomy_id is in createDraftListing's required array, and getSellerTaxonomyNodes needs no OAuth scope -- the API key alone reads the whole tree.<br><br>**OAS** "is_required: When true, listings assigned eligible taxonomy IDs require this property." So a node can refuse a listing that omits an attribute.<br><br>**UNKNOWN** This repository sends TAXONOMY_PATTERNS = 66 and has never read it back from Etsy. The OpenAPI document contains no taxonomy ids at all -- 'craft_supplies' appears zero times -- so it cannot be settled from the document. One unauthenticated GET to getSellerTaxonomyNodes with the API key settles it, and this lane is forbidden from making it. |
| 33 | Reviews<br>`reviews`<br>*Shop Manager > Your shop > Reviews* | **OBSERVE** | no | D | `getReviewsByShop`, `getReviewsByListing`, `getShop` | -- | **OAS** GET /shops/{shop_id}/reviews and /listings/{listing_id}/reviews require no OAuth scope, and Shop carries review_count and review_average.<br><br>**OAS** There is no write of any kind: no reply endpoint, no rating, no flag. Reviews can be read and nothing else.<br><br>**DECISION** The non-negotiables forbid fake reviews, fake buyers and artificial engagement absolutely. Recorded here because this is the surface where the temptation lives, and because 'favorite' appearing only as a read-only counter means there is no mechanism to abuse either. |
| 34 | Webhooks (order events)<br>`webhooks`<br>*Developer Portal > Manage your apps > Webhook portal* | **OWNER_ONLY** | no | B | **none** | -- | **DEV-DOC** "We currently support the following events: order.paid, order.canceled, order.shipped, order.delivered." All four are orders; nothing else pushes.<br><br>**DEV-DOC** Subscriptions are created only in the portal: "Navigate to Manage your apps in the Developer Portal. Click the dropdown menu for your commercial app and select Go to Webhook portal... Choose +Add Endpoint." There is no management endpoint in the OpenAPI document.<br><br>**DEV-DOC** Deliveries are signed: HMAC-SHA256 over webhook-id + '.' + webhook-timestamp + '.' + raw_body, with the secret base64-decoded after its whsec_ prefix, and a stale timestamp rejected beyond 300 seconds.<br><br>**INFERRED** A webhook would remove the need to poll for orders, but the payload carries only event_type, resource_url and shop_id -- reading the order still needs transactions_r. So this is worth doing after the scope is widened, not instead of it. |
| 35 | Your Apps (developer portal)<br>`developer_portal`<br>*https://www.etsy.com/developers/your-apps* | **OWNER_ONLY** | no | B | **none** | -- | **OAS** Etsy's own security scheme points at it: "Your keystring and shared secret are available on the Your Apps page."<br><br>**DEV-DOC** Rate limits are per API key and visible only there: "You can see your application's current rate limits in the Developer Portal", and a higher quota is requested by emailing developer@etsy.com.<br><br>**INFERRED** Every quota this company's collectors must live inside is readable only by a person. Designing a polling cadence without that number is guessing, and the guess is cheap to replace. |

---

## 3. Emptiness is never a pass

The brief named this repository's recurring defect — a verdict computed from the absence of
evidence — and said this registry is a perfect place to repeat it. It is, so the machinery to
prevent it is the largest part of what was built.

**Four evidence states, one of them good.** A surface with no collector is `NO_COLLECTOR`. A
collector that has never returned anything is `NO_EVIDENCE`. A record older than the surface's
tolerance is `STALE`. Only `FRESH` with every check passing is green, and
`SurfaceStatus.green` is written with no other path through it.

**Absent and empty are different facts.** In the shop collector, a field Etsy returned as
`null` is a **FAIL** — the thing is not set, and an owner action is open. A field the snapshot
does not contain at all is **NO_EVIDENCE** — nobody read it, which is a different problem with
a different fix. A truthiness test merges them into one comfortable "false", and the
comfortable half is the wrong one. Proved against an injected defect: the naive
`body.get(field, "assume it is set")` form reports a snapshot missing four policy fields as
completely clean; the real collector reports four `NO_EVIDENCE` checks and refuses green.

**An unread census is not a quiet shop.** `listing_census_drift(expected, None)` returns
`NO_EVIDENCE`, not "no drift". The naive `if not observed: return []` is written out in the
test, asserted to reproduce the failure, and then the real function is asserted to refuse it.

**An absence is evidence only when it is reproducible.** Every UNSUPPORTED verdict rests on
`ABSENCE_PROBES`: 22 terms counted in Etsy's document, with the document's version and SHA-256
beside them. `verify_absence(document_text)` recounts them against any document handed to it
and reports every term whose count has moved, in either direction. The day Etsy ships an Ads
API, this registry says so out loud instead of ageing quietly into a lie. Non-zero counts are
recorded too, with what the occurrences actually are — `keyword` 18, and all eighteen are the
public listing-search parameter, which is a marketplace search and never our own search
performance.

**A surface cannot cite an endpoint that does not exist.** All 105 operationIds are held in
`ETSY_OPERATIONS` and every cited operation is checked against them. An invented operation name
is the most natural way for a registry like this to drift into fiction: it reads exactly like a
real one, it is never called in shadow mode, and the first thing that disproves it is a 404
during a launch.

**Three live injected defects were run against the real code and each made tests fail:**
treating a missing field as present (2 failures), recording an unread field as PASS (2
failures), and allowing green without freshness (2 failures). The code was restored and the
file is green at 52/52.

---

## 4. What was built, and the evidence each piece rests on

| Built | Where | Rests on |
|---|---|---|
| The registry: 35 surfaces, six verdicts, evidence with provenance per surface | `src/brambleloop/intel/etsy_surfaces.py` | Etsy's OpenAPI document (SHA-256 recorded) and four developer-documentation pages, all fetched 2026-09-25 |
| `check_registry()` — eleven invariants that refuse a verdict from being a mood | same | four of them proved against injected defects |
| `ABSENCE_PROBES` + `verify_absence()` — the negative half made falsifiable | same | 22 counted terms in the recorded document version |
| `ETSY_OPERATIONS` — all 105 operationIds, so no surface can cite a fictional endpoint | same | the document's own `operationId`s |
| `scope_gaps()` — Etsy's reads against the scopes this shop actually holds | same | `BUILD_STATE.md`'s record of the 2026-09-25 grant, and each operation's `security` block |
| `EvidenceState` / `SurfaceStatus.green` — the four-state machine that makes empty non-green | same | the brief's rule, enforced rather than described |
| **Collector: `assess_shop()`** — 14 checks over a recorded `getShop` response | same | every checked field is one `getShop` returns; `getShop` needs no OAuth scope, only the API key |
| **Collector: `listing_census_drift()`** — the only machine-readable trace a takedown leaves | same | `getListingsByShop` returns each listing's state; the document's own state note includes `SUPRESSED (frozen)` |
| `owner_queue()` — 15 owner actions, each closing on evidence rather than on somebody's word | same | one per OWNER-ONLY surface, plus the ads and fee read-outs |
| `manual_only_consistency()` — `shop_package.MANUAL_ONLY` cross-checked against the registry, both ways | same | prevents a manual action existing with no surface that owns its evidence |
| The unmodelled-fee record, `worst_case_fees()`, and a warning on every price decision | `src/brambleloop/commerce/pricing.py` | the `offsite` = 0 absence probe, and etsy.com/legal/fees returning 403 |
| 52 checks, four naive-implementation defect proofs | `tests/test_etsy_surfaces.py` | — |

**Only two collectors exist, and that is deliberate.** A collector that cannot get data is not
a collector. Both of these are pure functions over a recorded observation — this module never
speaks to Etsy — and both are built on reads that need **no OAuth scope beyond what this shop
already holds**: `getShop` needs only the API key, and `getListingsByShop` needs `listings_r`,
which is granted. They are ready the moment the first observation is recorded by the lane that
holds the credential, and until then they report `NO_EVIDENCE` rather than nothing.

**What was deliberately not built.** A stats paste-in ingest (owner-reported figures must never
be merged into anything that reads as measured); a keyword rank probe (needs a live listing);
a shop-section creation call (that is an Etsy write, which Lane A owns); any fetcher for
help.etsy.com (it returns 403 to automated readers, and a check that skips when the network
refuses is a check that passes when the network refuses).

---

## 5. The pricing consequence, and why the fee constants were not changed

`commerce/pricing.py` modelled Etsy's transaction fee, payment processing and the amortised
listing fee. Three fees were missing, and the reason they cannot simply be added is itself a
finding of this registry: **Etsy exposes none of them and refuses to be read about them.**

| Fee | Basis | Rate if the secondary source is right | Applies when |
|---|---|---|---|
| Offsite Ads | SECONDARY — third-party reports of 12% or 15%; `etsy.com/legal/fees` is 403 here | 15% | only on attributed orders, reportedly compulsory below a revenue threshold |
| Regulatory Operating Fee | SECONDARY **and contested** — some sources report ~1.15% for Canada, others report none | 1.15% | every order, if Canada carries it at all |
| Currency conversion | SECONDARY — commonly reported at 2.5% | 2.5% | orders paid in a currency other than CAD, which for an international pattern shop is most of them |

The wrong fix is to fold a rate off a third-party page into `TRANSACTION_FEE`. That turns a
figure nobody has verified into a figure that looks measured, and every number downstream
inherits the confidence without the evidence. So `fees()` is **unchanged**, and instead:

- `FeeBreakdown.unmodelled` names what is missing, and `to_dict()` carries
  `take_rate_is_a_floor: true`, so no consumer can quote a take rate as complete.
- `worst_case_fees()` returns a dict — deliberately not a second `FeeBreakdown`, which would
  be passed around and eventually quoted as *the* model — with `basis` on every line.
- `decide_price()` now warns on every decision: at CA$6.50 the modelled take rate is 13.7% and
  the worst case is 32.3%, net CA$4.40.

The worst case is **not a forecast** and says so: offsite attribution and currency conversion
will not both apply to every order. It is the only figure here that cannot be an
understatement, and a price that survives it cannot be surprised by a fee.

---

## 6. OWNER ACTION REQUIRED

Fifteen entries, four of which block the first sale. Every one closes on **evidence a check can
read**, not on somebody saying it is done — three of the four blockers close on a `getShop`
field that `assess_shop()` checks automatically.

**Total for the four blockers: 95 minutes. Maximum cost: CA$0, except the tax decision, which
is CA$0 to do and up to CA$250 if you want an hour of an accountant's time.**

| # | Action | Surface | Min | Blocks first sale | Risk | Why software cannot | Evidence required to close it |
|---|---|---|---|---|---|---|---|
| 1 | Upload the shop banner and icon and paste the About story from `brand/storefront.ABOUT` into Shop Manager > Settings > Info & appearance. | `info_and_appearance` | 20 | **YES** | Low. The assets and the words are prepared; this is pasting and uploading, not composing. | updateShop writes five text fields and none of them is an image or the About story; Etsy publishes no shop-image upload endpoint at all. | getShop returning non-empty icon_url_fullxfull and image_url_760x100 -- checked by `assess_shop`, so this closes on a reading. |
| 2 | In Shop Manager > Finances > Payment settings, complete Etsy Payments onboarding: deposit account, billing card for fees, and the deposit schedule. | `payment_settings` | 20 | **YES** | Handle the account details only in the browser. Nothing here should ever receive them, and nothing here asks for them. | Etsy exposes no banking endpoint of any kind, and the process is identity-bound: a bank account may only be added by the account holder. | getShop returning is_etsy_payments_onboarded true -- which `assess_shop` checks, so this action closes on a reading rather than on a statement. |
| 3 | Paste the six prepared policies from `commerce.shop_package.policies()` into Shop Manager > Settings > Policies. They are written; this is copying, not drafting. | `policy_settings` | 25 | **YES** | Low. The words are already consistent with the licence in `commerce/terms.py`, and changing them while pasting would reintroduce the three-surface drift that module exists to prevent. | updateShop writes exactly one policy field (policy_additional). Etsy publishes no write endpoint for the delivery, returns, payment, privacy or FAQ text. | getShop returning non-blank policy_payment, policy_shipping, policy_refunds, policy_privacy and policy_seller_info -- which `assess_shop` checks field by field. |
| 4 | Complete identity verification and the legal/tax information, and decide the GST/HST position: register now or open as a small supplier, and whether to give Etsy a GST/HST number. | `legal_and_tax` | 30 | **YES** | Getting the tax position wrong is a correction to file later rather than a failure now. Giving Etsy a GST/HST number moves collection and remittance responsibility to you. | Identity verification is the one thing an autonomous system must never do on someone's behalf, and there is no endpoint for it in any case. The tax position is a decision with legal consequence, which software must not take. | A statement of the position chosen and its date, so `commerce.shop_package` can record it as decided rather than open; identity verification is evidenced by the shop being able to open at all. |
| 5 | Confirm once that no third-party app is installed on the shop, and install none without telling this system. | `apps` | 2 | no | Low. This is a standing security check, not a setup step. | Etsy exposes no list of installed applications, so an app with write access to the shop would be invisible here. | A dated statement that the Apps page is empty. |
| 6 | Confirm the Shared Access list is empty (or contains only people you intend), and re-check it after any account recovery. | `shared_access` | 2 | no | Low to perform; it is the cheapest check on this list and the only one that would catch a persistent intruder. | Etsy publishes no shared-access API, so a second person with listing permissions would be indistinguishable from us. | A dated statement of who appears on the page. |
| 7 | Confirm no paid Etsy subscription is active, and do not start one without recording the monthly amount here. | `subscription` | 2 | no | Low to perform. Unchecked, it is a recurring charge invisible to every budget ceiling in this system. | No subscription resource exists in the API, and the charge does not appear as its own ledger kind. | A dated statement that no subscription is active. |
| 8 | Leave Etsy Ads off, and confirm once that it is off. If you ever turn it on, tell this system the daily budget and the date, because nothing here can see either. | `etsy_ads` | 3 | no | The risk is entirely in the other direction: an ads budget set in a browser spends real money that no ceiling in this repository can stop. | No Ads endpoint exists in any form, and ad spend does not appear as its own ledger kind, so a code-enforced budget ceiling is not available for this surface. | A dated statement that Etsy Ads is off, recorded against this key; and if it is ever enabled, the budget and start date. |
| 9 | Read this application's x-limit-per-second and x-limit-per-day from the Developer Portal and report both figures. | `developer_portal` | 5 | no | None to perform. | The quota is shown on the portal page. It is also returned in response headers, but only to a caller already making authenticated requests, which this lane must not do. | The two numbers, so any polling cadence is set against a known quota rather than a guess. |
| 10 | On the first order, read the fee lines in Shop Manager > Finances > Payment account and report every one by name and amount -- in particular whether an Offsite Ads fee and a Regulatory Operating Fee appear, and at what rates. | `offsite_ads` | 5 | no | None to perform. The risk of not doing it is a pricing floor that is quietly optimistic by an unknown amount in the wrong direction. | Etsy's fee schedule is 403 to automated readers, and no fee line in the API is named for Offsite Ads, so the rate cannot be derived from a settlement either. | The fee lines from one real order, by name and amount, so `commerce.pricing.UNMODELLED_FEES` can be replaced by measured rates. |
| 11 | After the first listings go live, open Shop Manager > Policy Violations and confirm it is empty; check it again whenever the listing census alarm fires. | `policy_violations` | 5 | no | Low to perform. The risk of not looking is that the first notice of a problem is a suspension, and the appeal windows are short. | Etsy publishes no violations API. The only machine-readable trace of a takedown is a listing that is no longer there, which is also what a mistake of ours looks like. | A dated statement of the page's contents, recorded against this key -- 'empty on <date>' is evidence; silence is not. |
| 12 | Re-authorise the Brambleloop app in a browser with transactions_r added to the scope set (listings_r listings_w listings_d shops_r shops_w transactions_r). Start the flow at /api/etsy/oauth/start as before. | `orders` | 6 | no | Moderate and reversible. The new grant replaces the stored credential; if the flow fails midway the old refresh token may already be spent, and the write path is down until the flow is completed. Do it while you are at a keyboard, not before a launch window. | Etsy grants scope only through the authorization-code flow, which requires a human to approve the consent screen in a browser. A refresh grant "has the same scope as the token granted by the initial Authorization Code grant", so no amount of refreshing widens it. | A /api/etsy/oauth/status response whose granted scope list contains transactions_r, plus the credential still openable. |
| 13 | Download the first monthly statement once one exists and give the finance department its fee lines and totals. | `monthly_statements` | 10 | no | None to perform. | Etsy publishes no statement endpoint; the document exists only as a download behind the seller login. | The statement's fee lines and totals for one month, against which the ledger reconstruction can be reconciled. |
| 14 | Confirm Etsy message notifications reach an inbox you read daily (Shop Manager > Settings > Emails), and agree a reply window. Nothing in this system will ever see a buyer message. | `messages` | 10 | no | Low to perform. High to skip: an unanswered pre-sale question is a lost sale, and an unanswered post-sale problem becomes a case. | Etsy publishes no messaging API at all: no endpoint, no scope, no field. There is nothing to poll and nothing to send. | A screenshot or statement of which address Etsy message notifications go to, recorded against this action's key. |
| 15 | In the Developer Portal's Webhook portal, add an endpoint for order.paid pointing at this service's callback, and give this system the signing secret through the environment -- never through this repository. | `webhooks` | 10 | no | Moderate: the signing secret is a credential. It belongs in the hosting environment beside the other secrets, and a subscription pointed at the wrong URL leaks order metadata to whoever owns it. | Etsy's OpenAPI document contains no webhook resource; subscriptions exist only as a page in the developer portal. | The subscription visible in the portal, plus one delivery recorded by the receiving route with a verified signature. |

### The one that is new and is not a blocker but should be done soon

`reauthorise_transactions_r` (6 minutes). It does not block a sale — Etsy delivers a digital
file without us, so the sale completes whether or not we can see it. What it blocks is
everything *after* the sale: knowing a customer exists, version-aware support, the
first-hundred programme, and any revenue figure that is not a guess. Overstating it would put
a non-blocker at the top of the list, and a test asserts it is not marked as one.

---

## 7. A / B / C / D — what remains, and what may honestly remain

The owner's rule is explicit: **Build 2 may finish with B, C and D remaining.** The
classification is enforced, not asserted — `check_registry()` refuses a surface that is
required before the first sale and filed as anything but A, and a test asserts that every
class A surface really is a first-sale blocker, which is the rule that stops every improvement
becoming a launch blocker.

- **A** (11): `listings`, `messages`, `orders`, `payment_settings`, `legal_and_tax`, `your_shop`, `info_and_appearance`, `options`, `policy_settings`, `digital_files`, `taxonomy_and_attributes`
- **B** (6): `policy_violations`, `shared_access`, `subscription`, `shop_sections`, `webhooks`, `developer_portal`
- **C** (4): `search_visibility`, `marketplace_insights`, `sales_and_discounts`, `social_media`
- **D** (8): `stats`, `customer_service_stats`, `etsy_ads`, `offsite_ads`, `share_and_save`, `payment_account`, `monthly_statements`, `reviews`
- **-** (6): `dashboard`, `apps`, `help`, `delivery_settings`, `production_partners`, `sales_channels`

**A — first-sale blockers (11 surfaces).** Nine of the eleven are already built or already
prepared; what is outstanding on them is four owner actions and two pieces of build work that
belong to other lanes: the one controlled Etsy round trip (Lane A/C), and confirming
`TAXONOMY_PATTERNS = 66` with a single API-key GET.

**B — launch week (6).** Shop-section creation; the listing-census collector wired to a real
`getListingsByShop` read; the policy-violation check habit; the webhook subscription; the
developer-portal quota read-out; the two two-minute security confirmations (shared access,
subscription).

**C — post-launch continuous improvement (4).** The keyword rank probe (needs a live listing);
marketplace intelligence that is ours rather than Etsy's; the sales-and-discounts observation;
social posting, which this company does through `growth/owned.py` under a CASL gate instead.

**D — parked on real-world evidence (8).** Stats, customer-service stats, reviews, the payment
account, monthly statements, Share & Save, Etsy Ads and Offsite Ads. Every one needs something that
does not exist yet: traffic, customers, settlements or a decision to spend. Building a
collector for any of them now would produce a report of zeros that reads as a clean shop,
which is the failure this whole registry exists to prevent.

---

## 8. What is UNKNOWN, and what would settle it

Recorded as unknown rather than inferred. Each one names the single thing that would settle it.

| Unknown | What would settle it | Who can |
|---|---|---|
| Whether `TAXONOMY_PATTERNS = 66` is the crochet-patterns node, and whether that node marks any property `is_required` | **One unauthenticated-except-API-key GET** to `getSellerTaxonomyNodes`. The OpenAPI document contains no taxonomy ids at all (`craft_supplies` appears zero times), so it cannot be settled from the document | a lane holding the API key; this lane is forbidden from making the call |
| Whether Etsy's consent screen re-grants the existing five scopes silently when `transactions_r` is added | doing the re-authorisation once | the owner, 6 minutes |
| Whether a personal (non-commercial) application can subscribe to webhooks — the page says webhooks are "available for both commercial and personal applications" and then describes the portal as reached through "your commercial app" | opening the Webhook portal once | the owner |
| Etsy's per-file size and count limits for digital listings | the help page that carries them, which is 403 here | the owner, in a browser |
| Whether `/listings/active`'s `score` ordering is the ranking buyers see | comparing a rank probe against a browser search, once a listing is live | post-launch |
| Whether enrolling in Share & Save changes the fee on non-attributed orders | help.etsy.com, 403 here | the owner |
| Whether Etsy considers a generative model used for listing imagery a production partner | Etsy's guidance, on help.etsy.com, 403 here | the owner |
| The real Canadian fee stack: Offsite Ads rate, Regulatory Operating Fee, currency conversion | the fee lines on one real order | the owner, 5 minutes, after the first sale |
| This application's `x-limit-per-second` and `x-limit-per-day` | the Developer Portal page | the owner, 5 minutes |

**And the largest unknown of all, stated so its absence is not mistaken for a pass:** every
claim in this document about Etsy's *behaviour* is a reading of a document. The write path has
never created a listing, the read path has never read a shop, and the first real request will
teach us something this registry could not.

---

## 9. Compliance statement

- **CA$0 spent.** No model call, no image generation, no paid anything.
- **No Etsy write of any kind.** No listing created or changed, no setting touched, no draft,
  no upload. Lane A owns real Etsy writes and this lane did not make one.
- **No authenticated Etsy call at all** — not even a read. The only network requests made were
  unauthenticated GETs to Etsy's public OpenAPI document and its public developer
  documentation, plus two 403s from `help.etsy.com` and `etsy.com/legal/fees` which are
  recorded as evidence that those pages refuse automated readers.
- **No promotion started, no ad budget set, nothing activated, nothing published.**
- `BRAMBLELOOP_PHASE=shadow` throughout.
- Committed on the worktree branch. **Not pushed, not merged.**
