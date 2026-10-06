# Wave 3 — lane C handoff: Store copy / brand voice

Branch `claude/w3-C` (base `claude/v11-CANON` @ f0c2d12). Worktree `.claude/worktrees/W3-C`.
Interface: `brambleloop.store_foundation.copy_v2`, exported in the first commit (ca41781).

## Requirements addressed

| Requirement (directive §) | Status | Where |
|---|---|---|
| Lead with crochet patterns customers want to make, with taste, warmth and trust (§6) | COMPLETE | `copy_v2.ABOUT_PARAGRAPHS[0]`, `ANNOUNCEMENT`, `TAGLINE`, `SECTIONS` blurbs |
| Reliability turned into customer value: clear instructions, charts that agree, consistent terms, corrections, confidence (§6) | COMPLETE | About ¶3, `TRUST_SIGNALS` (same evidence paths as before, new customer wording), `TRUST_HEADLINE` |
| Verification explained deeper in About, after Laura and why the patterns are worth making (§6) | COMPLETE | About ¶4 (no "compiler", "machine-readable" or "formal" anywhere in customer copy) |
| Tagline: several candidates plus a chosen one (§6) | COMPLETE | `TAGLINE_CANDIDATES`, `tagline_candidates()`. Chosen: **"Crochet patterns for a life you make by hand"** (44 chars) |
| Owner concept (logo/banner): descriptor "Crochet Patterns", line "Patterns for a More Handmade Life", nav Home · Baby · Wearables · Gifts · Seasonal | COMPLETE, with one lint finding (below) | `BANNER`, `SECTIONS` |
| Announcement, plus seasonal drafts (§14) | COMPLETE | `ANNOUNCEMENT` (134 characters; the first sentence fits the 86-character phone window), `SEASONAL_ANNOUNCEMENTS` |
| About/story anchored on Laura as AI Founder/CEO, truthfully (§3, §7, §16) | COMPLETE | About ¶2, `ABOUT_LAURA_INTRO`, `SELLER_CAPTION`, `LAURA_FAQ` |
| FAQs (§14) | COMPLETE | `faq()` = 10 core answers (licence answers quote `commerce.terms` verbatim) + skill level, renders, sample, **who is Laura**, contact |
| Policy wording: digital delivery, licence and customer use, refunds for digital patterns, privacy with PIPEDA and CASL (§14) | COMPLETE | `DELIVERY`, `RETURNS`, `PRIVACY`, `PRIVACY_ADDENDUM`; licence still rendered from `commerce.terms` |
| Support/contact presentation (§14) | COMPLETE | `SUPPORT_CONTACT`, `PAGE_HEADINGS["support"]` |
| Section names (§14) | COMPLETE | Owner nav order. **Live:** Home (2 Launch-0 patterns), Baby (1). **Planned, not shown:** Wearables, Gifts (maps the `collections` slug), Seasonal, Blankets |
| Trust copy (§14) | COMPLETE | `TRUST_HEADLINE`, 8 `TRUST_SIGNALS`, each with evidence paths |
| Existing surfaces routed through copy_v2 | COMPLETE | `content.build()`; `commerce.shop_package` (DELIVERY, RETURNS, PRIVACY, DIGITAL_SALE_MESSAGE, `shop_text()['title']`, `faq()`, FAQ_ORDER); `brand.storefront`'s tagline through `shop_text` |
| Verify current Etsy disclosure requirements (§3, §16) | COMPLETE for the AI-disclosure rule (Etsy help, verified); legal pages UNVERIFIED (403) | See below |
| Etsy settings checklist row for the Creativity Standards classification | COMPLETE (row added) | `content.settings_checklist()` → `creativity_classification` |

**How the truth rules are kept.** Laura is always introduced with the AI disclosure, e.g. "Laura is Brambleloop's AI founder… She is an AI, not a human". The copy never says she crocheted, tested or photographed anything, never gives her a human history, and never calls her the legal owner or seller. The shop is described as "sold on Etsy by its human account holder, who is responsible for every order", once in the About, once in the disclosure block and once in the Laura FAQ. Pictures are called digital renderings, never photographs, and no sample has been made. The AI disclosure is proportionate: it is not in the tagline, the banner, the announcement or the About opening (a test enforces this). It is in About ¶2 and ¶5, the disclosure block and the FAQ.

## Lint finding for the integrator (the lint was not weakened)
- **The owner's line "Patterns for a More Handmade Life" (and the version with "Crochet") fails `TRUTH_PHYSICAL_MAKING`** on `hand[- ]?made`.
  - The line is truthful: "handmade" describes the customer's life and what they make, not Brambleloop making anything.
  - `copy_v2` picks the first candidate that passes every check, so it falls through to the closest lint-clean wording ("…a life you make by hand" / "For a life you make by hand").
  - Proposal (`copy_v2.LINT_MISFIRES`): allow "handmade" only in the fixed phrases "handmade life" / "more handmade" / "handmade home".
  - If the integrator makes that change in `lint.py`, the owner's line becomes the chosen tagline and banner line automatically, with no copy edit. Note that the shop-title form needs "crochet" (`check_shop_seo`), which is why candidate 1 is "Crochet patterns for a more handmade life".

## Etsy requirements (verified 2026-10-06)
The etsy.com/legal/* pages and the seller-handbook pages return HTTP 403 to WebFetch and curl. The **Help Center API** (`help.etsy.com/api/v2/help_center/en-us/articles/{id}.json`, the route lane I used) does serve them:
- **AI disclosure (VERIFIED, primary).** "What Can I Sell on Etsy?" (https://help.etsy.com/hc/en-us/articles/360024112614, edited 2025-09-17T18:36:53Z), under *Designed by a seller*:
  - "This category also includes seller-prompted AI creations."
  - "Digital items listed in your store must be made and/or designed by you, the seller."
  - "Seller-prompted AI creations must disclose the use of AI."
  - "If you work with a production partner, you must disclose that production partner in your relevant listings."

  This is a listing-level duty, met by `platform_policy.DISCLOSURES['ai_assisted_design']` in every listing. No shop-level (About) AI requirement was found; the store disclosure block is proportionate and voluntary. An owner checklist row `creativity_classification` has been added ('Designed by' + description disclosure). Brambleloop has no production partner.
- **"First listing image must be a real photograph" (UNVERIFIED, and not in Etsy's images article).** Third-party summaries claim this (listadum, 2026). Etsy's "Requirements and Best Practices for Images" (https://help.etsy.com/hc/en-us/articles/115015663347, edited 2026-05-04) contains no such rule; it only says "The first photo in a listing should be horizontal (landscape) or square." The Creativity Standards and Seller Policy legal pages are still unreadable (403), so the claim is neither confirmed nor refuted. A human should read https://www.etsy.com/legal/creativity before relying on disclosed renders as the primary image (D-FB-7). Routed to lanes I/H.
- **Secondary context.** Creativity Standards quote "Sellers must disclose within their listing description if an item is created with the use of AI." (via https://www.growtsy.com/etsy-ai-policy, citing the 2025-06-10 update). "Designed by" covers digital downloads and AI from the seller's own prompts (https://www.listadum.com/blog/etsy-creativity-standards). Buyer distrust of AI-imaged crochet patterns: https://www.nbcnews.com/tech/tech-news/etsy-crochet-buyers-suspect-ai-made-images-used-sell-patterns-rcna145878.
- **Limits.** These come from `integrations.etsy_constraints` (lane I, VERIFIED_HELP): shop title ≤ 55, About ≤ 5000, ≤ 20 sections, section names ≤ 24. `copy_v2.CONSTRAINTS` reads them and falls back to the secondary figures if the module is absent. The announcement has no Etsy number; the copy is held to the shop's own 160 and the 86-character phone opening.
  - Chosen tagline: 44 characters. The **56-character v1 title is gone**.
  - Section names are 4–9 characters. ANNOUNCEMENT is 134 characters. About is about 2,170 characters.
- **policy_additional is EU-only** (Etsy OpenAPI, via lane I). Changes made:
  - `shop_package.shop_text()['policy_additional']` is now `""` for this Canadian shop (`SHOP_LOCATED_IN_EU = False`).
  - New `api_shop_fields()` omits it from the payload.
  - `check_package()` now fails if the field is set or sent, and requires every `commerce.terms` axis verbatim in the FAQ.
  - The licence lives in the FAQ answers, and the About's last paragraph points to them.
  - The settings checklist row `policy_additional` is replaced by `licence_in_faq`.
  - The assertion in `test_shop_package.test_the_api_can_write_five_fields_and_a_person_types_the_rest` was updated to the verified fact: it is now *stricter* (all five axes in the FAQ, field empty, not sent).
- **Laura placement.** `copy_v2.LAURA_PLACEMENT` puts her in the banner, the About story and photos, and seasonal creative, once publication-approved. She is **never** the account profile photo (that is the account holder) and **never** the shop-team Owner role (Etsy help 360000336867).

## Files
- New: `src/brambleloop/store_foundation/copy_v2.py`, `tests/test_w3_store_copy_surfaces.py`, `tests/test_w3_store_copy_routing.py`, this handoff.
- Modified:
  - `src/brambleloop/store_foundation/content.py`: routing, the owner-nav `_sections()`, a creativity checklist row, and re-exports.
  - `src/brambleloop/commerce/shop_package.py`: copy read from copy_v2, and the tagline.
  - `tests/test_v11_store_preview.py`: one needle changed from the rejected v1 title literal to `copy_v2.TAGLINE`, which is the same assertion against the new title. The test is not removed or weakened.
- `commerce/terms.py` is unchanged. Its sentences are licence decisions rendered into the PDF, and changing them would ripple into PDF consistency.

## Tests
RESULTS_PLACEHOLDER

## Wiring requests
1. **Lane B (preview.py).**
   - Render from `copy_v2.export()`, or from the individual names.
   - Replace `preview.ABOUT_LAURA_INTRO` with `copy_v2.ABOUT_LAURA_INTRO`; it keeps "Brambleloop's AI founder" and "She is an AI", which `test_canon_store_brand_face` needs.
   - Use `BANNER`, `SECTIONS` (show only `status == "live"`), `PAGE_HEADINGS` and `TRUST_HEADLINE`.
2. **Lane A (`brand/storefront.py`).** `ABOUT` and `ANNOUNCEMENT_TEMPLATES` are still v1 there. `content.build()` no longer reads them, except as the takeover detector. Suggest `ABOUT = copy_v2.ABOUT`, `ANNOUNCEMENT_TEMPLATES = copy_v2.SEASONAL_ANNOUNCEMENTS`, and section display names from `copy_v2.SECTIONS`. Note that `test_v11_store_foundation.test_about_is_paste_ready` and `test_shop_package` read `storefront.ABOUT`; copy_v2's About passes both checks.
3. **Owner of `gates/platform_policy.py`.** `ai_assisted_design` says "directed and edited by the designer". The owner finding `DISCLOSURE_DESIGNER_CLAIM` is still open: who is "the designer" when Laura is an AI? Suggested truthful wording: "This design was developed with AI tools by Brambleloop, an AI-run studio, and every row's arithmetic is checked before release." This needs owner sign-off, because the gate text propagates to every listing.
4. **Lint owner.** Decide the `handmade` phrase scope above.

## Open defects / could not verify
- The Etsy legal pages (Creativity Standards, Seller Policy) are 403. The listing-image "first photo" question is HIGH.
- `store_foundation/limits.py` still records shop_title and section_name as UNKNOWN. Suggest it read `integrations.etsy_constraints`; `copy_v2.CONSTRAINTS` already does.
- Public use of Laura's name and persona needs human Laura's consent, which is an owner action (spec/07). The copy is ready, but it is not cleared for publication.
- The "Gifts" section is planned. Etsy puts each listing in one section only, so Gifts will need bundles or gift sets to exist.
