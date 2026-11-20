# OWNER_ACTIONS

Actions only the owner can perform, batched. Status: `open` | `done` | `withdrawn`. Before an item lands here, Claude has confirmed it cannot do it, automate it, integrate it, or eliminate it.

When you finish an item, change its status to `done` (or tell Claude in chat); the next session unblocks the dependent work automatically.

---

## OWNER ACTION REQUIRED — Block 1: open the Etsy shop (MapleSheets) and hand Claude the API keys

**Status:** open · **Requested:** 2026-09-15 (Day 1) · **Estimated time:** 45 minutes (55 with the optional Printify step) · **Cost:** Etsy one-time shop setup fee, about US$15-29 (≈ CA$20-40), charged by Etsy to your card at shop opening. **No money needs to be moved anywhere:** Etsy bills your card for fees and, later, for ads; Claude caps ad spend (CA$3/day, CA$200 total in the plan) and records every charge in the ledger. · **Why Claude cannot do it:** Etsy requires the account holder's identity (photo ID + selfie), bank details, and acceptance of its terms; the API app must be registered under the shop owner's Etsy account and the OAuth approval must be clicked by the account holder.

**What is blocked until done:** publishing listings, pulling competitor data, and therefore the 14-day visibility test (EXP-001). **What continues meanwhile:** building and testing the templates, listing copy and images, automations.

### Steps
1. **Create the shop (15 min).** Go to https://www.etsy.com/sell and click "Get started". Shop language English, country Canada, currency CAD. Shop name: try **MapleSheets** first; if taken, **LoonieBooks**, then **TrueNorthSheets** (Etsy names: max 20 characters, no spaces). Avoid "MapleLedger" and "NorthLedger": both are existing Canadian bookkeeping firms. Tell Claude which one worked.
2. **First listing placeholder.** Etsy will not let you finish without one listing. Create a draft with any title (e.g. "Placeholder — Claude will replace this via the API"), type **Digital**, price CA$29, upload any small PDF or image as the digital file. Keep it as a draft if Etsy allows; otherwise publish it and Claude will replace its contents. Do not spend time on it.
3. **Verify identity and payments (15 min).** Complete Etsy Payments: bank account (institution, transit, account number), your legal name, address, date of birth; photo ID + selfie when prompted; pay the one-time setup fee. Accept the seller terms.
4. **Register the API app (5 min).** Go to https://www.etsy.com/developers/register (log in with the same account) → "Create a New App". App name: `MapleSheets Ops`. Description: "Private tool to manage my own shop's listings and stats." Choose the option for an app that manages **your own shop** (Seller app / personal use). Copy the **Keystring** (looks like `abcd1234...`); the **Shared secret** is not needed for the PKCE flow.
5. **Set the redirect URL.** In the app settings add the callback URL exactly: `https://statefarm91.github.io/Project-Money/etsy-callback` (Claude will host a tiny page there; if it is not live yet, the flow still works: you will copy the URL from the browser's address bar in step 7).
6. **Give Claude the keystring (1 min).** Paste it into the Claude Code environment: claude.ai/code → Environments → Default → Environment variables → add `ETSY_KEYSTRING` = the keystring. (Environment variables are not stored in the repository.)
7. **One-time OAuth approval (3 min).** Claude will post an authorization link in chat. Open it, log in, approve the scopes (listings read/write/delete, shop read/write, transactions read, feedback read). Your browser will land on the callback URL with `?code=...&state=...` in the address bar. Copy that whole URL and paste it into the chat. Claude exchanges it for tokens and then tells you a `ETSY_REFRESH_TOKEN` value to add as a second environment variable (and as a GitHub Actions secret of the same name at https://github.com/StateFarm91/Project-Money/settings/secrets/actions for scheduled jobs). Refresh tokens last 90 days; Claude will ask again before expiry.
8. **Shop settings (5 min, can be later).** Shop policies: Claude will paste the policy text (digital downloads; refunds on request within 14 days; no physical shipping). Set "About" with the shop's one-paragraph description Claude provides. Skip everything else.

9. **Optional, 10 min, free: Printify (print-on-demand physical products).** Sign up at https://printify.com → "Add new store" → connect your Etsy shop (Printify opens Etsy and asks you to approve the connection) → Settings → Connections → API tokens → "Generate" a personal access token → add it to the Claude Code environment as `PRINTIFY_TOKEN`. This lets Claude create and publish physical products (mugs, prints, totes with Canadian designs) that Printify prints and ships from Canadian providers; nothing is charged until a customer orders.

### Later, 5 minutes each (Claude will ask when it is time)
- **Etsy Ads (after the 15-day new-shop wait, ~Day 20):** Shop Manager → Marketing → Etsy Ads → daily budget CA$3, advertise only the listing Claude names.
- **Any Etsy account-review or verification email:** forward the gist to Claude; reply with the text Claude drafts.
- **Buyer messages:** Claude drafts replies; you paste them (Etsy has no messaging API).

---

## OWNER ACTION REQUIRED — Block 2: the e-commerce stack for Track B (D-009)

**Status:** open · **Requested:** 2026-09-15 (Day 1) · **Estimated time:** about 2 hours, in three parts you can do separately · **Cost now:** Shopify CA$1/month for 3 months; domain ≈ CA$15-20/yr; fal.ai credits US$25; Anthropic API credits US$25. Ad spend is charged later to the card on the Meta ad account, capped by Claude at CA$150 for stage 1 and CA$250 for stage 2. · **Why Claude cannot do it:** every one of these platforms requires the account holder's identity, a payment method, and acceptance of terms. · **What is blocked until done:** Part A blocks the store build; Part B blocks the support agent and the domain; Part C blocks ads. Claude does product research and creative preparation meanwhile.

**Where to put keys:** claude.ai/code → Environments → Default → Environment variables (and the same names as GitHub Actions secrets at https://github.com/StateFarm91/Project-Money/settings/secrets/actions for scheduled deploys). Never paste keys into chat unless Claude explicitly asks for a one-time value.

### Part A — Shopify + supplier (≈ 40 min)
1. **Shopify store (10 min).** https://www.shopify.com/ca → Start free trial → use a placeholder store name (Claude renames it once the product research settles the brand) → pick the **Basic** plan on the CA$1/month-for-3-months offer. Country Canada, currency CAD.
2. **Shopify Payments (15 min).** Settings → Payments → Activate Shopify Payments: legal name, address, DOB, bank details, ID if asked. Also enable PayPal Express if you have a PayPal account (optional).
3. **Admin API access for Claude (10 min).** Settings → Apps and sales channels → Develop apps → Allow custom app development → Create an app named `Operator` → Configure Admin API scopes: `read_products, write_products, read_orders, write_orders, read_customers, write_customers, read_inventory, write_inventory, read_fulfillments, write_fulfillments, read_shipping, write_shipping, read_discounts, write_discounts, read_themes, write_themes, read_content, write_content, read_markets, write_markets, read_locations, read_price_rules, write_price_rules, read_merchant_managed_fulfillment_orders, write_merchant_managed_fulfillment_orders, read_third_party_fulfillment_orders, write_third_party_fulfillment_orders` → Install app → reveal the **Admin API access token** once → environment variables `SHOPIFY_ADMIN_TOKEN` and `SHOPIFY_STORE_DOMAIN` (the `xxxx.myshopify.com` address).
4. **CJ Dropshipping (5 min).** https://cjdropshipping.com → sign up → My CJ → Authorization → API → generate a key → `CJ_API_KEY`. Then install the CJ app from the Shopify App Store and connect it to the store (so orders route automatically).

### Part B — Domain, hosting, support agent (≈ 30 min)
5. **Cloudflare account (5 min).** https://dash.cloudflare.com/sign-up → verify email → Billing → add your card (needed only for the domain).
6. **Let Claude buy the domain (5 min).** Domain Registration → accept the Domain Registration Agreement when prompted → Registrar → set a default registrant contact (your name/address). Then create an API token (My Profile → API Tokens → Create Token → "Edit Cloudflare Workers" template, and add **Registrar: Write**, **Zone → DNS: Write**, **D1: Write**, **Email Routing: Write**) → `CLOUDFLARE_API_TOKEN`, plus your **Account ID** as `CLOUDFLARE_ACCOUNT_ID`. Claude will register one .com (≈ CA$15) through the API once the brand name is chosen, and connect it to Shopify and the support inbox.
7. **Anthropic API credits (10 min).** https://platform.claude.com → create an organization → Billing → buy US$25 of credits → set a monthly spend limit of US$40 → auto-reload off → API Keys → create → `ANTHROPIC_API_KEY`. This powers the customer-support agent (about half a cent per reply).

### Part C — Meta ads + video (≈ 45 min; Meta is the fiddly one)
8. **Meta Business Manager (15 min).** https://business.facebook.com → create a business portfolio → add a Facebook Page for the brand (placeholder name is fine) and, if you have Instagram, connect it → Ad accounts → create an ad account (currency CAD, timezone yours) → add a payment method. Complete any identity or business verification Meta requests.
9. **Meta developer app + system user (20 min).** https://developers.facebook.com → My Apps → Create App → type Business → add the **Marketing API** product. Then in Business Settings → Users → System users → Add (name `operator`, role Admin) → Add assets: the ad account (Manage), the Page (Manage) → Generate token → select the app, choose **never expires**, permissions `ads_management, ads_read, business_management, pages_read_engagement, pages_manage_ads` → copy once → `META_SYSTEM_TOKEN`. Also copy the **ad account id** (`act_...`) → `META_AD_ACCOUNT_ID`, the **Page id** → `META_PAGE_ID`, and create a **Pixel/Dataset** in Events Manager → `META_PIXEL_ID`.
10. **fal.ai credits (5 min).** https://fal.ai → sign up → Billing → add US$25 → Keys → create → `FAL_KEY`. Claude generates product videos and images with it.

### Then
Tell Claude "Block 2 done" (or which parts). Everything else, from product research to ads to customer support, is Claude's.

## Done
_None yet._
