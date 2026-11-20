# Store Foundation — honest review against the owner's bar

Lane F, v1.1 (directive section 10, F-926, F-233..F-241, F-515). Written 2026-10-06 by the lane
worker after building `src/brambleloop/store_foundation/` and looking at its own output at 390 px
and 1280 px (`evidence/F_preview_*.png`).

**The bar:** *Does Brambleloop look like a polished, premium, trustworthy crochet-pattern company
that has existed for years?* Without inventing history, sales or reviews.

**Short answer: the shop chrome and the words now clear it; the merchandise does not yet.** The
banner, icon, palette, voice, policies, FAQ, disclosures and About read as one considered studio,
and on a phone nothing is blank, default or contradictory. What still reads as "new" is
structural and cannot be written away: three products, renders instead of photographs, and no
reviews. Those are stated, not hidden.

## What exists now (verified by running it)

- One content model with **21 surfaces**, each assembled from the module that owns its words
  (`brand.storefront`, `commerce.shop_package`, `commerce.terms`, `gates.platform_policy`), with a
  deterministic readiness verdict. Current roll-up: **DEGRADED — FAIL 0, NEEDS_OWNER 9, GATED 2,
  UNVERIFIED 7, READY 3**. It is not OK because owner decisions and unread Etsy limits remain.
  That is the honest state.
- A truthfulness lint that catches years-in-business, superlatives, sales/review/customer counts,
  endorsements, founder stories, physical-making or photography claims, scarcity and safety
  claims, and respects true negatives ("no sample has been photographed"). Every customer-facing
  surface passes it.
- Deterministic SVG icon and banner in the bible palette. No model was used and nothing was spent.
- `render_preview(db, viewport)`: a self-contained page with no script and no external URL,
  labelled "Preview — not live". On every load it renders the three Launch-0 hero images from the
  current CIR and verifies them on their exact bytes. All three **VERIFIED** in this run. A frame
  that fails verification is withheld (D-FB-7). `summary(db)` is the Command Center provider.
- Playwright at 390 px and 1280 px: **no horizontal overflow** (scrollWidth equals clientWidth).

## Surface by surface

| Surface | Verdict | Critical view |
|---|---|---|
| Shop name | NEEDS_OWNER | "Brambleloop Studio" / handle `BrambleloopStudio` (opened 2026-09-19). It is consistent everywhere. The owner must confirm it, and Etsy's legal-name rule is still unread. |
| Icon | NEEDS_OWNER | A pine ring holding one gold crochet "v", with a bramble sprig. It works as a badge at 70 px and stays legible at 40 px (ring stroke about 2.9 px). The weaknesses: at 40 px the sprig becomes a speck, and the ring-plus-tail silhouette can read as a "Q". It is a v1 that needs the owner's taste call. Etsy needs a PNG, which nobody has exported or uploaded yet. |
| Banner | NEEDS_OWNER | The strongest asset. It has crochet stitch bands in cream, gold, pine and wine, and a centred wordmark between two bramble sprigs. The phone centre crop keeps the wordmark inside the safe area (measured with `brand.storefront_preview.banner_crops`). It still needs a raster export and upload, or a deliberate no-banner choice. |
| Shop title | UNVERIFIED | "Crochet patterns checked row by row before they are sold" (56 characters). It is specific and uses buyer words. **Etsy's limit is not on file.** If the counter refuses it, the fallback is "Crochet patterns, checked row by row" (36). |
| Announcement | UNVERIFIED | Short, specific, and fits the phone opening. "Charts and written instructions always agree" is an absolute claim. It is backed by charts and text being rendered from one CIR, but it is the one sentence a sceptic will test. The 160 cap is in repository code with no Etsy source. |
| About | UNVERIFIED (limit) | Truthful and distinctive (the "row 94" paragraph is the best copy in the shop), and it covers all five `check_about` elements. **Fixed here:** `brand.storefront.ABOUT` was hard-wrapped at 95 columns, so pasting it into Etsy would have put mid-sentence line breaks on phones. It is now one line per paragraph. It is long for a phone. There is no person on the About page; that is honest, and whether to add a real name is an owner choice (`seller_identity.owner_display_name` = UNKNOWN). |
| Delivery | UNVERIFIED (limit) | Clear: the product is a digital file, there is no processing time, and it says where the PDF is. |
| Returns | UNVERIFIED (limit) | Excellent. "Cannot be returned" comes first, then what the shop does instead. It is open by default in the preview. |
| Licence | NEEDS_OWNER | It answers the most-asked question correctly and comes from `commerce.terms`. Two flaws, both owned by `commerce.terms`. It publicly says the terms "have not yet been through legal review": honest, but the least premium sentence in the shop. It also refers to "its photographs" when there are none. |
| Privacy | NEEDS_OWNER | New PIPEDA/CASL-aware addendum: what the shop receives, why, who sees it, express-consent email with an unsubscribe, access and correction rights, and records kept as long as tax rules require (no invented retention period). **It needs legal review**, because it is a compliance statement. |
| Disclosures | NEEDS_OWNER | All four disclosures are present: AI-assisted design, digital item, rendered from the pattern file, and images are renderings, not photographs. The render sentence matches the pixels and the alt text. **Truth risk:** "directed and edited by the designer" (owned by `gates.platform_policy`) is only true if a person directs and edits each design. The owner must say who that person is, or the wording changes at its source. |
| FAQ | UNVERIFIED (limits) | 14 entries. The finished-item question comes first. This lane added four that were missing: skill level, whether the pictures are photographs, whether the pattern has been made up in yarn ("Not yet by us"), and how to reach the shop. The "not yet" answer is conspicuous, and it is the truth. A shop that has existed for years earns that impression by answering it plainly. |
| Support / contact | NEEDS_OWNER | The channel (Etsy Messages), what to include, and the correction promise. No response time is shown because none is decided. |
| Digital sale message | UNVERIFIED (limit) | Good: where the file is, the licence in one line, and how to report an error. |
| Sections | READY | Only populated sections are shown: Home & Table (2) and Baby & Nursery (1). **Inconsistency:** the nursery basket goes to *Home & Table* (category `basket`) while its title says "Nursery". This needs a merchandising decision. |
| Opening grid | NEEDS_OWNER | Three products at CA$6.50, 7.50 and 4.00. Sizes are not counted as products. `MIN_LISTINGS_TO_OPEN` is 8 and was not lowered (D-FB-9). **This is the main reason the shop still looks new.** Weaknesses: the hero renders sit on the contract's sage background (#B0BAAC, `visual.render_contract.BACKGROUND`), which is not a brand-palette colour, so the grid clashes slightly with the cream and pine chrome. The Cloudline blanket thumbnail is dense dark striping and is the weakest tile. The renders read as technical drawings, not lifestyle images. Titles are pipe-separated search strings that truncate on a phone ("Hexagonal Storage Basket \| Crochet Pattern PDF \|…"). That is normal on Etsy but mechanical. The basket's plan name ("Nesting Baskets") and its CIR title ("Hexagonal Storage Basket … Nursery") disagree. |
| Trust signals | READY | Seven real signals. Each is typed (verified process, policy commitment or platform fact) and points at the code or decision behind it. **Caveat:** "Corrections sent free to every buyer" is a decided policy (`terms.VERSION_POLICY`), but how Etsy delivers a corrected file to *past* buyers has not been verified by anyone here. |
| Brand voice | UNVERIFIED | No filler words, no exclamation marks, no emoji and no shouting. **Found:** typewriter " -- " in the returns, privacy, FAQ and digital-sale-message text from `commerce.shop_package`. Etsy shows it verbatim, so it should become a real dash at source. |
| Settings checklist | NEEDS_OWNER | 16 items that need the account holder signed in to Shop Manager, about 58 minutes (an estimate), CA$0. Their live state is UNKNOWN. |
| Search readiness | GATED | Shop SEO checks pass: the category words are present and nothing is stuffed. Etsy's Search Visibility page can only be read once listings are live. |
| Support readiness | GATED | Triage works (`support.department`). There is no Etsy messaging integration, so replies are drafted and held. |

## Owner decisions (cannot be made by this lane)

1. **Shop name**: confirm "Brambleloop Studio" for handle `BrambleloopStudio`.
2. **Basket naming and placement**: choose between "Nesting Baskets", "Hexagonal Storage Basket" and the "Nursery" qualifier, and pick Home & Table or Baby & Nursery.
3. **Catalogue depth**: the shop has 3 products against a threshold of 8 (D-FB-9, still open). This lane did not lower the threshold.
4. **Legal review** of the licence and the privacy text, or accept the public "not yet legally reviewed" sentence.
5. **"Directed and edited by the designer"**: confirm who that is, or change the disclosure at `gates.platform_policy`.
6. **Support response time**: commit to one, or keep none.
7. **Icon and banner approval** (taste), then raster upload or a deliberate no-banner choice.
8. **A person on the About page**: name someone (truthfully), or keep the studio voice.

## Gated (owner login or a live shop required)

- Every setting in the checklist: icon and banner upload, title, About, announcement, the four policy pages, FAQ, additional policies, digital sale message, sections, location and currency, two-factor sign-in.
- Etsy's own field limits for title, sections, policies, FAQ and banner/icon sizes. These are all UNKNOWN here, because Etsy's help pages refuse automated readers. The owner sees Etsy's counters at entry.
- Search Visibility, after the first live listings, recorded via `POST /api/search-visibility`.
- Live-shop inspection (`rendered_pages` gate). This preview is a mock-up and is not that inspection.

## Recommended fixes for other owners (not this lane's files)

- `commerce.shop_package`: replace " -- " with a dash.
- `commerce.terms`: drop "its photographs" from REDISTRIBUTION, or make it conditional.
- Visual lane: consider a brand-palette ground (cream) for disclosed hero renders, and a lighter thumbnail treatment for the Cloudline blanket. This must not weaken any verifier threshold.
- Integrator: `scripts/`, or a job, could export the SVGs to PNG with the preinstalled headless Chromium. That would turn the icon and banner "raster pending" items into upload-ready files.

## What was not verified

- How Etsy actually renders any of this. Fonts on Etsy will differ; a raster export removes that for the icon and banner.
- Any Etsy field limit except listing title (140) and alt text (500).
- That the live shop's current settings are blank or set. They are UNKNOWN.
- The Docker image: `research/` is not copied into it, which is why the preview renders images at runtime from the CIR instead of reading committed samples. The runtime path was exercised locally only.
