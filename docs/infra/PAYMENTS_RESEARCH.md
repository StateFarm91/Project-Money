# Payment infrastructure for a Canadian sole-proprietor digital business run by an AI operator

Research date: 2026-09-15 (Day 1), produced by a research subagent with live web fetches. Legend: **[V]** verified on the cited page; **[T]** third-party/secondary source only; **[I]** inference. Nothing here is legal or tax advice.

## 0. Executive summary

- **Set up Stripe first, and turn on Stripe Managed Payments (Stripe's merchant-of-record product).** GA since 2026-04-22, explicitly supports businesses located in Canada, onboards "individual or sole proprietorship" accounts, handles sales tax/VAT/GST in 80+ countries including Canadian domestic sales, pays out in CAD, and every object (product, price, payment link, checkout session, webhook, refund, subscription change) can be created via API with a single `managed_payments[enabled]=true` flag. The same account can also run ordinary (non-MoR) Stripe checkouts for productized services, which no MoR will carry. Cost: 2.9% + CA$0.30 + 3.5% MoR fee (+0.8% on non-Canadian cards; currency conversion charged to the buyer).
- **Runner-up: Polar.sh** (native license keys, full API, Canada supported, 5% + 50¢ on the free tier; up to 14-day account review before first payout; no services allowed).
- **Avoid for a new Canadian store in Sept 2026:** Lemon Squeezy (now "Sold through Link, LLC f/k/a Lemon Squeezy LLC", steering users to Stripe Managed Payments; API cannot create products), FastSpring (sales-led, opaque pricing), Payhip (not a MoR outside EU/UK; API only covers coupons and license keys), Gumroad (10% + 50¢ **plus** card processing, API cannot create products, bans "AI services").

## 1. Merchant-of-record (MoR) options

| Provider | Base fee | Surcharges | Payout to Canada | MoR tax scope | Canadian individual onboarding | API creates products / checkout / licenses? | Subscriptions / licenses | Restrictions |
|---|---|---|---|---|---|---|---|---|
| **Stripe Managed Payments** | 2.9% + CA$0.30 + **3.5%** MoR fee [V] | +0.8% intl cards; Billing 0.7% on subscriptions; FX paid by buyer via Adaptive Pricing; dispute CA$15 [V] | CAD bank; first payout 7 business days, then 3-day [V] | Yes; tax in 80+ countries incl. CA and US domestic [V] | Canada supported; "individual or sole proprietorship"; activation = dashboard toggle + ToS + eligibility review [V] | **Yes**: Products, Prices, Payment Links, Checkout Sessions, Subscriptions, Webhooks, Refunds [V] | Subscriptions yes; no native license keys [I] | Digital products only; no human services; checkout on Stripe domain branded "Sold through Link"; Stripe may refund within 60 days [V] |
| **Paddle** | 5% + $0.50 [V] | <$10 products need custom pricing; up to 1.5% conversion margin [V] | Wire/Payoneer; monthly; min $100; CAD payout to Canadian bank free [V] | Yes [V] | Individuals allowed [T]; Sumsub ID; live HTTPS site with T&C showing legal name; domain review 5–7 business days [V] | Yes [T] | Subs yes; no native licenses [I] | Software only; no services [V] |
| **Polar.sh** | Free: 5% + 50¢; Pro $20/mo: 3.8% + 40¢ [V] | +1.5% intl; $15 dispute; Stripe payout fees; FX 0.25–1% [V] | Stripe Connect Express; Canada supported; first payout after review up to 14 days [V] | Yes [V] | Questionnaire + Stripe Identity [V] | **Yes** incl. native license keys [V] | Yes [V] | Software; no human services; AI tools "restricted" category [V] |
| **Lemon Squeezy** | 5% + 50¢ [V] | +1.5% intl, +0.5% subs, +1% non-US payout [V] | Bank/PayPal, 14th & 28th, min $50 [V] | Yes [V] | 2–3 business days claimed; 2026 reports 1–4 weeks [T] | **No product creation via API** [T] | Yes [V] | No services; company migrating users to Stripe MP [V] |
| **Gumroad** | 10% + $0.50 direct; 30% Discover [V] | + card processing on top [T] | Weekly after 7-day hold [T] | Yes [V] | Instant signup [T] | No create-product endpoint [T] | Yes [T] | Bans "AI services" and consulting [V] |
| **Whop** | 2.7% + $0.30 [V] | +1.5% intl, +1% FX, tax add-on 2% [V] | 200+ countries; KYC at payout [T] | Partial (US/EU/UK managed) [V] | Fast [T] | Yes [V/T] | Yes [T] | Allows services/communities [V] |
| **Creem** | 3.9% + 40¢ [V] | none intl [V] | Canada supported; 1st & 15th; min $50; payout fee $7 or 1% [V] | Yes, 50+ countries [V] | KYC at onboarding [V] | Yes [T] | Yes [T] | Young company [I] |
| **Dodo Payments** | 4% + 40¢ [V] | +1.5% intl, +0.5% subs [V] | Free; $5 if under $1,000; Canada eligible [V] | Yes [V] | Individuals accepted; KYC 1–3 business days [V] | Yes [T] | Yes [T] | — |
| **Payhip** | 5% free plan + your own Stripe/PayPal [T] | — | Instant to own Stripe [T] | No (EU/UK VAT only) [T] | Needs own Stripe [T] | Coupons and license keys only [V] | Yes [T] | Allows services [T] |
| **FastSpring** | Not published; ~5.9% + $0.95 [T] | — | — | Yes [V] | Sales-led | Yes [T] | Yes | Unsuitable at this scale [I] |
| **Freemius** | 4.7% (+2.3% WordPress) + ~3.5% gateway [V] | — | Monthly, ~2-month lag [T] | Yes [T] | — | Licensing API [T] | Yes | WordPress plugins fit [I] |

Sources: https://stripe.com/en-ca/pricing ; https://docs.stripe.com/payments/managed-payments/eligibility ; https://docs.stripe.com/payments/managed-payments/tax-compliance ; https://docs.stripe.com/payments/managed-payments/how-it-works ; https://docs.stripe.com/payments/managed-payments/set-up ; https://docs.stripe.com/payments/managed-payments/use-payment-links ; https://docs.stripe.com/payments/managed-payments/changelog ; https://docs.stripe.com/payments/currencies/localize-prices/adaptive-pricing ; https://support.stripe.com/questions/default-payout-speeds-in-europe-and-canada ; https://www.paddle.com/pricing ; https://www.paddle.com/help/start/intro-to-paddle/what-am-i-not-allowed-to-sell-on-paddle ; https://www.paddle.com/help/start/account-verification/what-is-domain-verification ; https://polar.sh/resources/pricing ; https://polar.sh/docs/merchant-of-record/supported-countries ; https://polar.sh/docs/merchant-of-record/account-reviews ; https://polar.sh/docs/merchant-of-record/acceptable-use ; https://polar.sh/docs/api-reference/products/create ; https://docs.lemonsqueezy.com/help/getting-started/fees ; https://docs.lemonsqueezy.com/help/getting-started/prohibited-products ; https://www.lemonsqueezy.com/blog/2026-update ; https://lemonsqueezy.nolt.io/279 ; https://gumroad.com/pricing ; https://gumroad.com/prohibited ; https://docs.whop.com/fees ; https://docs.whop.com/payments-and-billing/fees/taxes ; https://www.creem.io/pricing ; https://docs.creem.io/merchant-of-record/supported-countries ; https://dodopayments.com/pricing ; https://docs.dodopayments.com/miscellaneous/verification-process ; https://payhip.com/api-reference ; https://fastspring.com/pricing/ ; https://freemius.com/help/documentation/getting-started/our-pricing/

### 1a. Notes that matter more than the headline rates
1. **Lemon Squeezy is in wind-down-by-migration mode** (2026-01-28 post: goal is "an easy way to migrate to Stripe Managed Payments"; footer "Sold through Link, LLC f/k/a Lemon Squeezy LLC") [V]. Its API cannot create products [T].
2. **Stripe Managed Payments went GA 2026-04-22 in 39 countries**, Payment Links supported, AI-as-a-Service tax codes added 2026-06-02 [V]. Canadian pricing page lists 3.5% MoR fee natively [V].
3. **Whop's tax handling is not a global MoR** [V].
4. **Effective cost on a US$50 sale to a non-domestic card** [I]: Creem ≈ 4.7% + payout fee; Dodo ≈ 6.3%; Stripe MP ≈ 7.8% (FX paid by buyer); Paddle 6% + up to 1.5%; Polar Starter 7.5% + fees; Lemon Squeezy 7.5% + 1%; Whop 7.2–9.7%; Gumroad ≈ 14.5%.
5. **Productized services (a human does something per order) are prohibited by every true MoR** (Stripe MP, Paddle, Polar, Lemon Squeezy) [V]. Only Whop and Payhip allow them. Sell services as seller-of-record (plain Stripe).
6. **AI-generated products**: no MoR bans AI-generated content per se; Stripe MP has AIaaS tax codes [V]; Polar/Paddle flag AI tools for review; Gumroad bans selling access to AI tools/services [V].

## 2. Stripe direct for a Canadian individual
- Business type "individual or sole proprietorship" is first-class in Canada [V] https://support.stripe.com/questions/types-of-business-and-structure-guidelines-in-canada . Requirements: name, DOB, address, email, phone, bank account, business URL, MCC, product description, support phone, ToS [V] https://docs.stripe.com/connect/required-verification-information . Photo ID + proof of address if automatic verification fails [V].
- No business number needed under the small-supplier threshold [T].
- Fees (CAD): 2.9% + CA$0.30 domestic; +0.8% international; +2% conversion if you settle foreign charges (Adaptive Pricing shifts this to the buyer) [V]. Billing 0.7%; disputes CA$15; Stripe Tax 0.5% PAYG [V]. First payout 7 business days, then 3-day rolling [V].
- As seller of record, foreign consumption taxes are your problem (EU/UK no de-minimis for B2C digital) — the reason MoRs exist [I].

## 3. Marketplace-native payments (brief)
| Channel | Fees for a Canadian seller | Notes |
|---|---|---|
| Etsy | Listing US$0.20; 6.5% transaction; processing 3% + C$0.25 (4% intl); 2.5% conversion if listing in USD; Offsite Ads 15% [T] | Digital downloads allowed |
| Fiverr | 20% seller commission; funds clear 14 days after completion [T] | Fits productized services |
| Shopify Payments (Canada) | Basic CA$49/mo; 2.8% + 30¢ [V] https://www.shopify.com/ca/pricing | You are seller of record |
| Chrome extensions via ExtensionPay | 5% + your own Stripe fees [V] https://extensionpay.com/ | Seller of record |
| WordPress plugins via Freemius | ≈10.5% all-in [V] | Freemius is MoR |

## 4. Canada small-supplier rule and record-keeping (factual, not advice)
- Small supplier if worldwide taxable supplies ≤ $30,000 in a single calendar quarter and over the last four consecutive quarters [V] https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/when-register-charge.html . Exceed within one quarter → register within 29 days; exceed over four quarters → end of following month. Voluntary registration allowed [V].
- Zero-rated supplies (exports) count toward the threshold [T]. MoR interaction: MoR payouts count toward the test; characterization is fact-specific [I — confirm with an accountant].
- Record-keeping: keep six years; income records with date/amount/source; expense receipts; computerized records acceptable [V] https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/sole-proprietorships-partnerships/business-records.html . Sole-proprietor income on T2125 with the T1 [T].
- Practical set: MoR payout statements, Stripe Payout Reconciliation reports (`withheld_tax` columns) [V], bank statements, expense receipts.

## 5. Recommendation: Stripe with Managed Payments enabled
Why: Canada supported for individuals [V]; no separate store-approval gate requiring a live site (Paddle) or 14-day pre-payout review (Polar); deepest API; CAD payouts; FX on buyers; Canadian GST/HST handled on domestic digital sales; the same account also runs plain checkouts for services. Upfront cost CA$0. Ongoing 6.4% + CA$0.30 domestic / 7.2% + CA$0.30 foreign cards, +0.7% subscriptions.

Trade-offs: no native license keys (generate on `checkout.session.completed`); checkout on Stripe's domain with "Sold through Link" branding; Stripe may refund within 60 days and expects support responses within 48 hours (route the support inbox to the operator); MP can't be toggled on existing payment links [V].

### Owner's one-time setup (60–90 minutes)
1. Create the account (5 min): https://dashboard.stripe.com/register .
2. Activate the Canadian account (25–35 min): Country Canada → "Individual or sole proprietorship" → legal name, DOB, home address, phone, email; business website URL (a one-page site is fine); product description; industry/MCC (e.g. "Software as a service"); support phone; statement descriptor; bank account (institution, transit, account numbers); accept terms; photo ID + proof of address if prompted [V].
3. Turn on Managed Payments (5 min + review): Settings → Managed Payments (https://dashboard.stripe.com/settings/managed-payments) → Activate → accept https://stripe.com/legal/managed-payments [V].
4. Tax presentation (2 min): Settings → Tax → tax-inclusive or exclusive [V].
5. API access (5 min): Developers → API keys → Create restricted key (write: Products, Prices, Payment Links, Checkout Sessions, Customers, Subscriptions, Coupons, Refunds, Webhook Endpoints; read: Balance, Payouts, Reports) → paste into the secret store (GitHub Actions secret, never the repo). Also a sandbox key for testing with 4242 4242 4242 4242 [V].
6. Support routing (3 min): Settings → Business details → support email = an inbox the operator can read and answer [V].
7. Customer portal (3 min): Settings → Billing → Customer portal → enable cancel/update [V].
8. Payouts (2 min): leave automatic [V].
9. Optional (10 min): domain + one-page site with product description, pricing, contact, privacy and refund policy [I].

### What the AI operator can do via API afterwards [V]
- Catalogue: `POST /v1/products` with MP-eligible `tax_code` (`txcd_10202000` downloadable software, `txcd_10302000` e-book, `txcd_10103001` SaaS business use, `txcd_10105001-4` AIaaS, `txcd_20060158` online course) and `default_price_data`; `POST /v1/prices` for tiers.
- Sell without a website: `POST /v1/payment_links` with `managed_payments[enabled]=true`.
- Sell with a site: `POST /v1/checkout/sessions` with `mode=payment|subscription`, `managed_payments[enabled]=true` (API version `2025-03-31.basil`+; do not pass `automatic_tax`, `tax_id_collection`, `payment_method_types`, `custom_text`, `invoice_creation`, statement descriptors).
- Fulfilment: webhooks for `checkout.session.completed`, `invoice.paid`, `customer.subscription.updated/deleted` → generate license keys / download links and email them (Stripe/Link sends receipts).
- Money ops: refunds, subscription changes, coupons, Balance/Payout Reconciliation reports, disputes (Stripe fights them under MP).
- Services line: separate payment links without `managed_payments`; track revenue against the $30,000 four-quarter test and alert the owner at ~$25k [I].

### Fallback order if Stripe MP eligibility declines [I]
1. Polar.sh (full API incl. license keys; Stripe Identity; up to 14 days to first payout) [V].
2. Dodo Payments (individuals; 1–3 day KYC; Canada eligible; 4% + 40¢) [V].
3. Paddle (needs live HTTPS site with T&C showing legal name; 5–7 day domain review) [V].
