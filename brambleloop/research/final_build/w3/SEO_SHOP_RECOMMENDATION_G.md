# Shop-level SEO recommendation for lane C (from lane G, wave 3, 2026-10-06)

Recommendation only. Lane C owns `store_foundation.copy_v2` and all store text; lane G did not
edit any C file. Machine-readable form: `brambleloop.seo.shop.RECOMMENDATION`; checker:
`brambleloop.seo.shop.check_shop_copy(copy)` (and `shop.review()` reads `copy_v2` automatically
once it is integrated).

## What shop text can honestly do for search
- VERIFIED (Etsy OpenAPI v3, read 2026-10-06): the shop `title` is "A brief heading string for
  the shop's main page"; `announcement` "displays on the shop's homepage". No length is stated
  in the API for either.
- UNVERIFIED (Etsy Help Center refused automated reads; search-index summary only): shop title
  up to **55** characters; up to **20** sections, each name up to **24** characters. Owner
  confirms via the counters in Shop Manager.
- Whether Etsy's *listing* search reads shop text is not documented anywhere we could read. So:
  write for people, name the category once in buyer words, never a keyword list.

## Shop title (tagline) — options (all pass `check_shop_copy`)
1. "Modern crochet patterns for home and nursery" (44)
2. "Crochet patterns for a calm, cosy home" (38)
3. "Thoughtful crochet patterns for home and baby" (45)
Rules: says "crochet" and "pattern(s)"; no repeated word; no AI/compiler/agent words.

## Announcement
First sentence names what a buyer makes and gets. Example:
"Crochet patterns for baskets, blankets and coasters you will love making, with clear written
instructions and charts in US and UK terms."
No discount language unless a real sale exists.

## About
Story first (Laura, taste, why these patterns); the careful checking process deeper down as
customer value (fewer errors, dependable charts). Name "crochet" at least once. Disclosure
wording: lanes C/I + owner (Etsy AI-disclosure rule is UNVERIFIED wording; see
`seo.constraints` key `ai_disclosure`).

## Sections at Launch-0
Only populated sections: **Baby & Nursery** (Cloudline blanket, nesting baskets) and
**Home & Table** (coaster set). Zero sections is also acceptable with three listings. Note:
`brand.storefront.SECTIONS` maps baskets to Home; the basket product's `nursery` qualifier
makes Baby & Nursery the truer shelf — C/B decide.

## Listing titles (for consistency with store copy)
See `seo.strategy.TITLES`: object + "crochet pattern" first, then shape/size/material,
then the deliverable.
