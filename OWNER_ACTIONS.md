# OWNER_ACTIONS

Actions only the owner can perform, batched. Status: `open` | `done` | `withdrawn`. Before an item lands here, Claude has confirmed it cannot do it, automate it, integrate it, or eliminate it.

When you finish an item, change its status to `done` (or tell Claude in chat); the next session unblocks the dependent work automatically.

---

## OWNER ACTION REQUIRED — Block 1: open the Etsy shop (MapleSheets) and hand Claude the API keys

**Status:** open · **Requested:** 2026-09-15 (Day 1) · **Estimated time:** 45 minutes · **Cost:** Etsy one-time shop setup fee, about US$15-29 (≈ CA$20-40), charged by Etsy at shop opening · **Why Claude cannot do it:** Etsy requires the account holder's identity (photo ID + selfie), bank details, and acceptance of its terms; the API app must be registered under the shop owner's Etsy account and the OAuth approval must be clicked by the account holder.

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

### Later, 5 minutes each (Claude will ask when it is time)
- **Etsy Ads (after the 15-day new-shop wait, ~Day 20):** Shop Manager → Marketing → Etsy Ads → daily budget CA$3, advertise only the listing Claude names.
- **Any Etsy account-review or verification email:** forward the gist to Claude; reply with the text Claude drafts.
- **Buyer messages:** Claude drafts replies; you paste them (Etsy has no messaging API).

---

## Deferred — Block 2: own-domain checkout and the WCAG pre-check page (only if Claude asks after Day 21)
Domain (Cloudflare Registrar, ~CA$15/yr), Cloudflare account + API token, Stripe account (plain Checkout; Managed Payments later if EU buyers appear), Resend API key, GitHub Actions secrets. ~40 minutes. Not needed for Track A.

## Done
_None yet._
