# Etsy store and listing requirements — verified evidence (lane W3-I)

Retrieved **2026-10-06 (UTC)**. Machine-readable source of truth:
`brambleloop.integrations.etsy_constraints` (`summary()`, `CONSTRAINTS`, `reconcile()`,
checkers `image_problems` / `image_bytes_problems` / `digital_file_problems` / `text_problems`
/ `shop_name_problems`). This document is generated from that module plus narrative; if they
ever disagree, the module wins and this file is stale.

## How the evidence was obtained (and what it is worth)

- **Etsy Help Center** HTML pages (`help.etsy.com/hc/...`) return HTTP 403 to automated
  readers from this environment (confirmed again 2026-10-06). The Help Center's **public
  article API** — `https://help.etsy.com/api/v2/help_center/en-us/articles/<id>.json` — returns
  the same article body plus Etsy's own `edited_at`. Every Help Center figure below was read
  that way, read-only, with no credentials. This is a new finding: earlier repo modules
  (`commerce.shop_package.SOURCES['etsy_help']`, `intel.etsy_surfaces`, `store_foundation.limits`)
  record the help centre as unreadable; that is no longer true (see WIRING REQUESTS in
  `handoff_I.md`).
- **Etsy Open API v3** OpenAPI document `https://www.etsy.com/openapi/generated/oas/3.0.0.json`
  (HTTP 200, 911 KB) for API-level rules.
- **Third-party "Etsy size guides"** (linearity.io, printify, picsart, adnabu, ratioready …)
  were consulted only to see what the folklore says. They are **not evidence** and several are
  wrong against Etsy's own article: the widely repeated "big banner 3360 x 840" appears in no
  Etsy document; Etsy says minimum 1200 x 300, recommended **1600 x 400**. No value in the
  module comes from a third party.
- **Basis labels.** `VERIFIED_HELP_CENTER` / `VERIFIED_OPENAPI` = an Etsy document states it
  (quoted). That is evidence of what Etsy **publishes**, not an observation of Etsy enforcing
  it on this shop: no authenticated Etsy call has ever been made (owner re-auth is GATED).
  `UNKNOWN` = Etsy publishes nothing; no number is carried.

## The answers the lane was asked for

| Surface | Etsy's published rule | Basis |
|---|---|---|
| Shop icon (Etsy calls it **logo**) | jpg/png/gif, **< 10 MB, at least 500 x 500**; recommended 500 x 500; cropped **square** in the editor. A missing logo "may" lower search visibility. Circular display mask: **not stated by Etsy** (folklore). | VERIFIED (115015628487, 115015663347, 115015663247, 25869947521175) |
| Big banner | **min 1200 x 300, recommended 1600 x 400** (4:1) | VERIFIED (115015663347, 115015663247) |
| Mini banner | **min 1200 x 160, recommended 1600 x 213** | VERIFIED (same) |
| Mobile banner crop | **UNKNOWN** — Etsy publishes no crop geometry or safe zone; only "appears … on mobile devices" and "Image sizes are optimized for mobile displays". Keep marks centred; check the real crop in the Etsy app after upload. | UNKNOWN |
| Order receipt banner | min 760 x 100 | VERIFIED |
| Carousel / collage banners | Etsy Plus (paid subscription) only | VERIFIED |
| Seller/owner profile photo | It is the **account's** Public-profile picture (Your account > Account settings > Public profile): **at least 400 x 400, < 10 MB, square** ("or your profile picture will be distorted"), jpg/png/gif | VERIFIED (115015651948) |
| Shop team member photo | exists (Settings > Your shop > Shop team); no size published | path VERIFIED, size UNKNOWN |
| About featured photos | up to **5**, jpg/png/gif **≤ 2 MB**, displayed cropped to **760 x 468** | VERIFIED |
| Listing images | up to **20** photos + 2 videos (5–15 s); recommended **≥ 2000 px width and height**; first photo **≥ 635 px** "to avoid showing up lower in searches"; first photo landscape or square; primary photo a single finished product, no collage; types **.jpg .gif .png .svg .heic only** (no .webp); **no transparency** (renders black), no animation; > 1 MB "may not finish uploading" (browser); Etsy converts to sRGB; served at up to 3000 px | VERIFIED |
| Thumbnail crop | first photo is cut to **square, portrait and landscape** thumbnails; exact ratios **UNKNOWN** | VERIFIED (shapes) / UNKNOWN (ratios) |
| Digital files | **≤ 5 files, ≤ 20 MB each**, names **≤ 70 chars of letters, digits, `.`, `_`, `-`**, names cannot be edited after upload; supported types listed; an instant digital listing cannot be published or saved without a file; no variations | VERIFIED (115015628347) |
| Listing title | **≤ 140 chars**; "consider using less than 15 words"; Open API character set (`%`, `:`, `&`, `+` once each) | VERIFIED |
| Tags | **≤ 13 tags, ≤ 20 chars each**; letters, digits, spaces; `'` and `-` allowed inside but **not at the start** | VERIFIED (360000336307) |
| Materials | character set letters/digits/whitespace (Open API); **count limit UNKNOWN** (repo's 13 is unsourced) | VERIFIED set / UNKNOWN count |
| Description | **length limit UNKNOWN** (repo's 102400 is unsourced) | UNKNOWN |
| Styles | ≤ 2 | VERIFIED_OPENAPI |
| Alt text | API max **500**; Etsy advises **≤ 250** | VERIFIED |
| Shop title (tagline) | **≤ 55 chars**; only after the shop is open | VERIFIED (360000343708) |
| Announcement | **no published limit** ("short and sweet"); only after the shop is open | UNKNOWN (limit) |
| About your shop | **≤ 5,000 chars** | VERIFIED |
| Sections | **≤ 20** custom sections (+ All items); name **≤ 24 chars**; empty sections are hidden; one section per listing | VERIFIED (360000345048) |
| Shop name | **4–20 chars, no spaces or punctuation**; ≤ 5 self-service changes once open | VERIFIED |
| `policy_additional` (updateShop) | **EU-located shops only**; "Passing a value … outside of the EU, will result in an error" | VERIFIED_OPENAPI |
| AI disclosure | "Seller-prompted AI creations must disclose the use of AI." | VERIFIED (360024112614) |
| Shop team "Owner" role | must be an owner who makes/designs/sources and "is responsible for any activity on the account" under Etsy's Terms of Use | VERIFIED (360000336867) |

## Taxonomy / attribute API flow

1. `getSellerTaxonomyNodes` (api_key) → choose the crochet-pattern node.
2. `getPropertiesByTaxonomyId` (api_key) → `is_required`, `supports_attributes`,
   `possible_values`, `scales`, `max_values_allowed` for that node.
3. `createDraftListing` (listings_w) with `taxonomy_id`, `type=download`.
4. `updateListingProperty` (listings_w) per attribute: `value_ids` + `values` (+ `scale_id`).
5. `uploadListingFile` (listings_w) → 6. `uploadListingImage` (listings_w, multipart part `image`).
7. Read back: `getListing`, `getListingProperties`, `getAllListingFiles`, `getListingImages`
   (image `full_width`/`full_height` may be **null** straight after upload — Etsy processes
   asynchronously; `etsy_verify.verify_images` reports that as PENDING, never verified).
8. `updateListing state=active` — GATED (owner authority; needs an image and a file).

Code: `integrations.etsy_taxonomy` (gated refresh), `EtsyClient.get_taxonomy_properties`,
`EtsyClient.set_listing_property`, `runtime.etsy_ops.read_back`. The node id in code
(`TAXONOMY_PATTERNS = 66`) is still **UNVERIFIED**: reading the tree needs an Etsy keystring
this environment does not hold. Help article 115014502508 (edited 2026-09-16) confirms the
seller-side flow: attributes appear only after a category is chosen and depend on it; fill
both attributes and tags.

## Code changed because evidence disagreed (lane I files)

| Was | Now | Evidence |
|---|---|---|
| `integrations.etsy.IMAGE_CONTENT_TYPES` allowed `.webp` | removed (jpg/jpeg/png/gif) | 115015663347: "These are the only image file types Etsy supports" (no webp) |
| no digital-file name/type/size check before upload | `digital_file_refusals` refuses before any request; `publish_preflight` before the create (no orphan drafts) | 115015628347 |
| tags could start with `'` or `-` | `listing_schema.tag_problems` → `TAG_LEADING_PUNCTUATION` | 360000336307 |
| image read-back compared alt text only | `etsy_verify.verify_images`: rank, alt text, pixel size, extra images, PENDING | Open API ListingImage + uploadListingImage async note |
| `listing_schema` matrix said Etsy's image rules were unreadable | now cites the article; the 1x1 probe image stays IMPLEMENTED (Etsy publishes no hard minimum) | 115015663347 |

Disagreements in files lane I does **not** own are listed as WIRING REQUESTS in `handoff_I.md`.

## Full evidence table (generated from `etsy_constraints.CONSTRAINTS`)

### shop_logo

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `logo_min_px` | shop logo (icon) minimum size, px (w, h) | 500 x 500 | VERIFIED_HELP_CENTER | required | [115015628487](https://help.etsy.com/hc/en-us/articles/115015628487-How-to-Edit-Your-Shop-s-About-Section) (2026-05-04) | "Your logo must be a .jpg, .png, or .gif file, smaller than 10MB, and at least 500px by 500px." |
| `logo_recommended_px` | shop logo recommended size, px | 500 x 500 | VERIFIED_HELP_CENTER | recommended | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "The recommended size for logos is 500 x 500px." |
| `logo_max_bytes` | shop logo file size, bytes (exclusive) | 10 MB | VERIFIED_HELP_CENTER | required | [115015628487](https://help.etsy.com/hc/en-us/articles/115015628487-How-to-Edit-Your-Shop-s-About-Section) (2026-05-04) | "smaller than 10MB" |
| `logo_formats` | shop logo file types | jpg, png, gif | VERIFIED_HELP_CENTER | required | [115015628487](https://help.etsy.com/hc/en-us/articles/115015628487-How-to-Edit-Your-Shop-s-About-Section) (2026-05-04) | "Your logo must be a .jpg, .png, or .gif file" |
| `logo_crop` | the logo is cropped square in the editor | square crop tool | VERIFIED_HELP_CENTER | display | [115015663247](https://help.etsy.com/hc/en-us/articles/115015663247-How-to-Customize-Your-Shop-s-Appearance) (2026-05-05) | "Select the square (crop) icon to crop your image." — Whether Etsy then masks the logo as a circle on any surface is NOT stated by Etsy (third-party guides claim it). Design the mark to survive a circular mask anyway; that is a design margin, not a fact. |
| `logo_affects_search` | a missing logo may lower search visibility | True | VERIFIED_HELP_CENTER | recommended | [25869947521175](https://help.etsy.com/hc/en-us/articles/25869947521175-How-to-Use-the-Etsy-Search-Visibility-Page) (2026-05-04) | "Your shop should have a logo, which helps the buyer understand who you are. If your shop is not complete, your listings' search visibility may be impacted." |

### profile_photo

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `profile_min_px` | account public-profile picture minimum size, px | 400 x 400 | VERIFIED_HELP_CENTER | required | [115015651948](https://help.etsy.com/hc/en-us/articles/115015651948-Your-Bio-and-Profile-Picture) (2025-07-15) | "The image you use must be at least 400 x 400 pixels in size and smaller than 10MB." |
| `profile_recommended_px` | profile photo recommended size, px | 400 x 400 | VERIFIED_HELP_CENTER | recommended | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "The recommended size for profile photos is 400 x 400px." |
| `profile_max_bytes` | profile photo size, bytes (exclusive) | 10 MB | VERIFIED_HELP_CENTER | required | [115015651948](https://help.etsy.com/hc/en-us/articles/115015651948-Your-Bio-and-Profile-Picture) (2025-07-15) | "smaller than 10MB" |
| `profile_square` | profile photo must be square | 1.0 | VERIFIED_HELP_CENTER | required | [115015651948](https://help.etsy.com/hc/en-us/articles/115015651948-Your-Bio-and-Profile-Picture) (2025-07-15) | "Make sure your original image is a square, or your profile picture will be distorted on the site." |
| `profile_formats` | profile photo file types | jpg, png, gif | VERIFIED_HELP_CENTER | required | [115015651948](https://help.etsy.com/hc/en-us/articles/115015651948-Your-Bio-and-Profile-Picture) (2025-07-15) | "Profile pictures should be a .jpg, .png, or .gif file only." |
| `profile_is_account_level` | the profile picture belongs to the signed-in Etsy *account* (Your account > Account settings > Public profile), not to the shop | account | VERIFIED_HELP_CENTER | display | [115015651948](https://help.etsy.com/hc/en-us/articles/115015651948-Your-Bio-and-Profile-Picture) (2025-07-15) | "On Etsy.com, go to Your account. Go to Account settings. Go to Public profile." — Truth consequence: this is the account holder's own picture. Putting an AI persona there presents the persona as the account holder. See ETSY_SETTINGS_CHECKLIST.md item B3. |

### big_banner

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `big_banner_min_px` | big shop banner minimum size, px | 1200 x 300 | VERIFIED_HELP_CENTER | required | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "The minimum required size for big shop banners is 1200 x 300px." |
| `big_banner_recommended_px` | big shop banner recommended size, px | 1600 x 400 | VERIFIED_HELP_CENTER | recommended | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "The recommended size is 1600 x 400px." |

### mini_banner

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `mini_banner_min_px` | mini shop banner minimum size, px | 1200 x 160 | VERIFIED_HELP_CENTER | required | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "The minimum required size for mini shop banners is 1200 x 160px." |
| `mini_banner_recommended_px` | mini shop banner recommended size, px | 1600 x 213 | VERIFIED_HELP_CENTER | recommended | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "The recommended size is 1600 x 213px." |

### big_banner

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `banner_mobile_crop` | how much of the banner a phone shows | — | UNKNOWN | required | — |  — Etsy says only that the banner 'appears when shoppers view your shop on the standard view of the website as well as on mobile devices' and that 'Image sizes are optimized for mobile displays'. No crop geometry or safe zone is published. Third-party 'safe zones' (e.g. 1200x300 central) are not evidence. Keep text/marks centred with generous margins and check the real crop in the Etsy app after upload (checklist B2). |

### receipt_banner

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `receipt_banner_min_px` | order receipt banner minimum, px | 760 x 100 | VERIFIED_HELP_CENTER | required | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "The minimum required size for order receipt banner photos is 760 x 100px." |

### big_banner

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `carousel_collage_etsy_plus` | carousel and collage banners need Etsy Plus (paid) | True | VERIFIED_HELP_CENTER | display | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "The carousel and collage banners are only available to sellers subscribed to Etsy Plus." |

### about

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `about_photos_max` | About featured photos, count | 5 | VERIFIED_HELP_CENTER | required | [115015628487](https://help.etsy.com/hc/en-us/articles/115015628487-How-to-Edit-Your-Shop-s-About-Section) (2026-05-04) | "Upload up to 5 photos with captions from this section." |
| `about_photo_max_bytes` | About featured photo size, bytes | 2 MB | VERIFIED_HELP_CENTER | required | [115015628487](https://help.etsy.com/hc/en-us/articles/115015628487-How-to-Edit-Your-Shop-s-About-Section) (2026-05-04) | "Images can be .jpg, .png, or .gif files up to 2MB." |
| `about_photo_display_px` | About photos are cropped to display at, px | 760 x 468 | VERIFIED_HELP_CENTER | display | [115015628487](https://help.etsy.com/hc/en-us/articles/115015628487-How-to-Edit-Your-Shop-s-About-Section) (2026-05-04) | "your photos will be cropped to display at 760 x 468 pixels." |
| `about_video_max_bytes` | shop featured video, bytes | 300 MB | VERIFIED_HELP_CENTER | required | [115015628487](https://help.etsy.com/hc/en-us/articles/115015628487-How-to-Edit-Your-Shop-s-About-Section) (2026-05-04) | "Your video must be an MP4, MOV, AVI, MPEG, or M4V file up to 300 MB." |

### shop_title

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `shop_title_max_chars` | shop title (tagline) characters | 55 | VERIFIED_HELP_CENTER | required | [360000343708](https://help.etsy.com/hc/en-us/articles/360000343708-How-to-Add-a-Shop-Announcement-and-Shop-Title) (2025-06-12) | "Shop titles can be up to 55 characters long." |

### shop_name

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `shop_name_chars` | shop name length (min, max) characters | 4 x 20 | VERIFIED_HELP_CENTER | required | [115015672808](https://help.etsy.com/hc/en-us/articles/115015672808-How-to-Open-an-Etsy-Shop) (2026-05-04) | "4-20 characters in length" — Also: 'they can't have spaces or punctuation' (article 115015710568). |
| `shop_name_changes` | self-service shop-name changes once open | 5 | VERIFIED_HELP_CENTER | required | [115015710568](https://help.etsy.com/hc/en-us/articles/115015710568-How-to-Change-Your-Shop-Name) (2026-05-04) | "Once your shop is open, you can change your shop name up to 5 times" |

### about

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `about_max_chars` | About your shop characters | 5000 | VERIFIED_HELP_CENTER | required | [115015628487](https://help.etsy.com/hc/en-us/articles/115015628487-How-to-Edit-Your-Shop-s-About-Section) (2026-05-04) | "Share the story behind your business in 5,000 characters or less." |

### announcement

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `announcement_max_chars` | shop announcement characters | — | UNKNOWN | required | — |  — Etsy says only 'Keep your announcement short and sweet' (360000343708). No number is published; the repo's 160 is an internal style cap, not Etsy's limit. |
| `announcement_needs_open_shop` | announcement and shop title cannot be set before the shop is open | True | VERIFIED_HELP_CENTER | display | [360000343708](https://help.etsy.com/hc/en-us/articles/360000343708-How-to-Add-a-Shop-Announcement-and-Shop-Title) (2025-06-12) | "If your shop isn't open to the public yet, you won't be able to add an announcement until you open your shop." |

### sections

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `sections_max` | custom shop sections, count | 20 | VERIFIED_HELP_CENTER | required | [360000345048](https://help.etsy.com/hc/en-us/articles/360000345048-How-to-Create-and-Manage-Shop-Sections) (2024-02-15) | "You can have up to 20 custom sections, as well as the default All items section that is in every shop." |
| `section_name_max_chars` | shop section name characters | 24 | VERIFIED_HELP_CENTER | required | [360000345048](https://help.etsy.com/hc/en-us/articles/360000345048-How-to-Create-and-Manage-Shop-Sections) (2024-02-15) | "A section name can be up to 24 characters." |
| `empty_sections_hidden` | empty sections are not shown | True | VERIFIED_HELP_CENTER | display | [360000345048](https://help.etsy.com/hc/en-us/articles/360000345048-How-to-Create-and-Manage-Shop-Sections) (2024-02-15) | "Sections that don't have any item listings won't appear on your public shop page." |

### shop_home

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `featured_listings` | featured listings shown on shop home | 4 | VERIFIED_HELP_CENTER | display | [115015663247](https://help.etsy.com/hc/en-us/articles/115015663247-How-to-Customize-Your-Shop-s-Appearance) (2026-05-05) | "Featuring items is a way to showcase 4 listings" |

### policies

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `policy_additional_eu_only` | updateShop.policy_additional may only be set by EU-located shops | True | VERIFIED_OPENAPI | required | [openapi](https://www.etsy.com/openapi/generated/oas/3.0.0.json) (unversione) | "the policy_additional field should only be set for shops located in the EU. Passing a value for this field for shops outside of the EU, will result in an error." — Brambleloop is Canadian: policy_additional must not be sent. |
| `digital_sale_message_max_chars` | Message to Buyers for Digital Items characters | — | UNKNOWN | required | — |  — Field exists (updateShop.digital_sale_message; help 360000337107); no length published. |
| `faq_limits` | FAQ entries / characters | — | UNKNOWN | required | — |  — Etsy's policies article suggests putting licensing info in FAQs but publishes no FAQ limits. |

### listing

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `title_max_chars` | listing title characters | 140 | VERIFIED_HELP_CENTER | required | [115015628707](https://help.etsy.com/hc/en-us/articles/115015628707-How-to-Create-a-Listing) (2026-06-29) | "A listing's title can be up to 140 characters long." |
| `title_words_advice` | title word-count guidance | 15 | VERIFIED_HELP_CENTER | recommended | [115015628707](https://help.etsy.com/hc/en-us/articles/115015628707-How-to-Create-a-Listing) (2026-06-29) | "Consider using less than 15 words" |
| `tags_max` | tags per listing | 13 | VERIFIED_HELP_CENTER | required | [360000336307](https://help.etsy.com/hc/en-us/articles/360000336307-How-to-Use-Tags-to-Get-Found-in-Search) (2026-04-21) | "You can use up to 13 tags per listing." |
| `tag_max_chars` | characters per tag | 20 | VERIFIED_HELP_CENTER | required | [360000336307](https://help.etsy.com/hc/en-us/articles/360000336307-How-to-Use-Tags-to-Get-Found-in-Search) (2026-04-21) | "Each tag can contain up to 20 characters." |
| `tag_no_leading_punct` | a tag may not start with ' or - | '- | VERIFIED_HELP_CENTER | required | [360000336307](https://help.etsy.com/hc/en-us/articles/360000336307-How-to-Use-Tags-to-Get-Found-in-Search) (2026-04-21) | "You're able to use ' and - within words and phrases, but cannot start your tag with these characters." |
| `materials_max` | materials per listing | — | UNKNOWN | required | — |  — 13 is asserted in integrations.etsy.MATERIALS_MAX. Neither the Open API document nor any help article read on 2026-10-06 states a materials count; materials are now also an attribute (115014502508). |
| `description_max_chars` | listing description characters | — | UNKNOWN | required | — |  — integrations.etsy.DESCRIPTION_MAX = 102400 has no Etsy source on file; the Open API description field states no maximum. |
| `styles_max` | styles per listing | 2 | VERIFIED_OPENAPI | required | [openapi](https://www.etsy.com/openapi/generated/oas/3.0.0.json) (unversione) | "the listing may have up to two styles." |

### listing_image

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `alt_text_max_chars` | image alt text characters (API) | 500 | VERIFIED_OPENAPI | required | [openapi](https://www.etsy.com/openapi/generated/oas/3.0.0.json) (unversione) | "Alt text for the listing image. Max length 500 characters." |
| `alt_text_advice_chars` | alt text guidance, characters | 250 | VERIFIED_HELP_CENTER | recommended | [4406604492823](https://help.etsy.com/hc/en-us/articles/4406604492823-How-to-Add-a-Text-Alternative-to-Your-Listing-Images) (2024-12-10) | "Keep the description concise: up to 250 characters." |
| `listing_images_max` | photos per listing | 20 | VERIFIED_HELP_CENTER | required | [115015628707](https://help.etsy.com/hc/en-us/articles/115015628707-How-to-Create-a-Listing) (2026-06-29) | "You can add up to 20 photos and 2 videos that are 5-15 seconds in length to each listing." |
| `listing_videos_max` | videos per listing (5-15 s each) | 2 | VERIFIED_HELP_CENTER | required | [115015628707](https://help.etsy.com/hc/en-us/articles/115015628707-How-to-Create-a-Listing) (2026-06-29) | "You can add up to 20 photos and 2 videos that are 5-15 seconds in length to each listing." |
| `listing_image_recommended_px` | listing photo recommended min width AND height, px | 2000 | VERIFIED_HELP_CENTER | recommended | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "We recommend your listing photos have a width and height of at least 2000 pixels or more." — Etsy's form warns below 2000 px wide but still publishes (115015628707). |
| `first_image_min_px` | first listing photo min width and height to avoid lower search placement, px | 635 | VERIFIED_HELP_CENTER | recommended | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "Your first listing photo should have a width and height of at least 635 pixels to avoid showing up lower in searches." |
| `first_image_orientation` | first photo should be landscape or square | landscape, square | VERIFIED_HELP_CENTER | recommended | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "The first photo in a listing should be horizontal (landscape) or square." — The same article also says 'Avoid square crops. Upload horizontal or landscape images.' Etsy is internally inconsistent; landscape satisfies both sentences. |
| `thumbnail_crops` | thumbnails are cut from the first photo in three shapes | square, portrait, landscape | VERIFIED_HELP_CENTER | display | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "Make sure your thumbnail images have enough of a border that they can be cropped to square, portrait, and landscape thumbnails without losing some of the product." — The exact aspect ratios of the three crops are NOT published (UNKNOWN). |
| `primary_photo_single_product` | primary photo: a single finished product, no collage | True | VERIFIED_HELP_CENTER | recommended | [25869947521175](https://help.etsy.com/hc/en-us/articles/25869947521175-How-to-Use-the-Etsy-Search-Visibility-Page) (2026-05-04) | "The listing's primary photo is a singular image of a finished product (no collaged or stitched together images)" |
| `image_formats` | image file types Etsy supports | jpg, gif, png, svg, heic | VERIFIED_HELP_CENTER | required | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "All images in your shop should be one of these file types: .jpg, .gif, .png, .svg, or .heic. These are the only image file types Etsy supports." |
| `no_animation_no_transparency` | animated GIF and transparent PNG unsupported; transparency renders black | True | VERIFIED_HELP_CENTER | required | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "Animated .gif files & transparent .png files are not supported. If a file contains transparency, the transparent parts of the image will appear black on Etsy." |
| `image_upload_bytes_advice` | images over 1MB may not finish uploading | 1 MB | VERIFIED_HELP_CENTER | recommended | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "Images larger than 1MB in file size may not finish uploading, especially on a slower internet connection." — Applies to the browser upload; whether the API enforces any size is UNKNOWN. |
| `color_profile` | Etsy converts images to sRGB | sRGB | VERIFIED_HELP_CENTER | display | [115015663347](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop) (2026-05-04) | "We convert images to use the sRGB color profile" |
| `full_image_max_px` | url_fullxfull is served at up to this many px per dimension | 3000 | VERIFIED_OPENAPI | display | [openapi](https://www.etsy.com/openapi/generated/oas/3.0.0.json) (unversione) | "The url string for the full-size image, up to 3000 pixels in each dimension" |
| `image_size_async` | size/colour fields may be null straight after upload | True | VERIFIED_OPENAPI | display | [openapi](https://www.etsy.com/openapi/generated/oas/3.0.0.json) (unversione) | "When uploading a new image, data such as colors and size may return as null values due to asynchronous processing of the image. Use getListingImage endpoint to fetch these values." |

### digital_file

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `digital_files_max` | files per digital listing | 5 | VERIFIED_HELP_CENTER | required | [115015628347](https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings) (2025-03-21) | "You can upload up to five digital files." |
| `digital_file_max_bytes` | size per digital file, bytes | 20 MB | VERIFIED_HELP_CENTER | required | [115015628347](https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings) (2025-03-21) | "The maximum size for each file is 20MB." |
| `digital_filename_max_chars` | digital file name characters | 70 | VERIFIED_HELP_CENTER | required | [115015628347](https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings) (2025-03-21) | "File names are limited to 70 alphanumeric characters, periods, underscores, or hyphens." |
| `digital_filename_immutable` | a digital file's name cannot be edited after upload | True | VERIFIED_HELP_CENTER | display | [115015628347](https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings) (2025-03-21) | "We don't have a way of editing the name after uploading, so be sure to name your files appropriately first." |
| `digital_file_types` | digital file types | bmp, doc, gif, jpeg, jpg, mobi, mov, mp3, mpeg, pdf, png, psp, rtf, stl, txt, zip, epub, ibook | VERIFIED_HELP_CENTER | required | [115015628347](https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings) (2025-03-21) | "Supported file types .bmp .doc .gif .jpeg .jpg .mobi .mov .mp3 .mpeg .pdf .png .psp .rtf .stl .txt .zip .ePUB .iBook" |
| `instant_digital_needs_file` | an instant digital listing cannot be published or saved without a file | True | VERIFIED_HELP_CENTER | required | [115015628347](https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings) (2025-03-21) | "You will be unable to publish or save an instant digital listing if there is no file attached to it." |
| `digital_no_variations` | digital listings take no variations | True | VERIFIED_HELP_CENTER | required | [115015628347](https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings) (2025-03-21) | "No, you can't offer variations for digital items." |

### disclosure

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `ai_disclosure` | seller-prompted AI creations must disclose AI | True | VERIFIED_HELP_CENTER | required | [360024112614](https://help.etsy.com/hc/en-us/articles/360024112614-What-Can-I-Sell-on-Etsy) (2025-09-17) | "Seller-prompted AI creations must disclose the use of AI." |

### about

| key | what | value | basis | enforced | source (edited) | quote / note |
|---|---|---|---|---|---|---|
| `owner_role_truth` | a shop-team 'Owner' must be a real responsible owner who makes/designs | True | VERIFIED_HELP_CENTER | required | [360000336867](https://help.etsy.com/hc/en-us/articles/360000336867-How-to-Display-Team-Members-in-your-Shop-About-Section) (2026-07-30) | "Owner: You and anyone else you consider to be an owner of your Etsy shop. The owner must also be making, designing, hand picking, or sourcing qualifying items in line with Etsy's Creativity Standards. Under Etsy's Terms of Use, the owner is responsible for any activity on the account." |

## Reconciliation with code (live output of `etsy_constraints.reconcile()` on this branch)

| where | repo | Etsy | status | note |
|---|---|---|---|---|
| `integrations.etsy.TITLE_MAX` | 140 | 140 | **AGREES** |  |
| `integrations.etsy.TAGS_MAX` | 13 | 13 | **AGREES** |  |
| `integrations.etsy.TAG_CHARS_MAX` | 20 | 20 | **AGREES** |  |
| `integrations.etsy.MATERIALS_MAX` | 13 | None | **ETSY_PUBLISHES_NONE** | 13 is asserted in integrations.etsy.MATERIALS_MAX. Neither the Open API document nor any help article read on 2026-10-06 states a materials count; materials are |
| `integrations.etsy.DESCRIPTION_MAX` | 102400 | None | **ETSY_PUBLISHES_NONE** | integrations.etsy.DESCRIPTION_MAX = 102400 has no Etsy source on file; the Open API description field states no maximum. |
| `integrations.etsy.ALT_TEXT_MAX` | 500 | 500 | **AGREES** |  |
| `integrations.etsy.IMAGE_CONTENT_TYPES` | ['gif', 'jpeg', 'jpg', 'png'] | ('jpg', 'gif', 'png', 'svg', 'heic') | **AGREES** | the client may send a subset of Etsy's formats, never a superset |
| `publish.listing_schema.MAX_IMAGES` | 20 | 20 | **AGREES** |  |
| `brand.storefront.BANNER_SIZE` | (1600, 400) | (1600, 400) | **AGREES** |  |
| `brand.storefront.ICON_SIZE` | (500, 500) | (500, 500) | **AGREES** |  |
| `brand.storefront.ABOUT_MAX` | 5000 | 5000 | **AGREES** |  |
| `brand.storefront.ANNOUNCEMENT_MAX` | 160 | None | **ETSY_PUBLISHES_NONE** | Etsy publishes no announcement limit; 160 is an internal style cap |
| `brand.storefront.SECTIONS (count)` | 6 | 20 | **AGREES** |  |
| `brand.storefront.SECTIONS (longest name)` | 21 | 24 | **AGREES** |  |
| `brand.storefront_preview.SECTION_LABEL_MAX` | 30 | 24 | **DISAGREES** | repo labels 30 ASSUMED; Etsy's verified section-name limit is 24 |
| `publish.listing_assets.CANVAS` | 2000 | 2000 | **AGREES** |  |
| `commerce.seo.TITLE_MAX` | 140 | 140 | **AGREES** |  |
| `commerce.seo.TAG_MAX_CHARS` | 20 | 20 | **AGREES** |  |
| `commerce.seo.TAG_MAX_COUNT` | 13 | 13 | **AGREES** |  |
| `commerce.search.TITLE_MAX` | 140 | 140 | **AGREES** |  |
| `commerce.search.TAG_MAX_CHARS` | 20 | 20 | **AGREES** |  |
| `store_foundation.limits.LIMITS['about'] (UNVERIFIED_REPO_ASSERTED)` | 5000 | 5000 | **AGREES_BUT_REPO_LABELS_UNSOURCED** |  |
| `store_foundation.limits.LIMITS['announcement'] (UNVERIFIED_REPO_ASSERTED)` | 160 | None | **ETSY_PUBLISHES_NONE** |  |
| `store_foundation.limits.LIMITS['sections_count'] (UNVERIFIED_REPO_ASSERTED)` | 20 | 20 | **AGREES_BUT_REPO_LABELS_UNSOURCED** |  |
| `store_foundation.limits.LIMITS['shop_title'] (UNVERIFIED_UNKNOWN)` | None | 55 | **REPO_UNKNOWN_ETSY_PUBLISHES** |  |
| `store_foundation.limits.LIMITS['section_name'] (UNVERIFIED_UNKNOWN)` | None | 24 | **REPO_UNKNOWN_ETSY_PUBLISHES** |  |
| `store_foundation.limits.LIMITS['shop_name'] (UNVERIFIED_UNKNOWN)` | None | (4, 20) | **REPO_UNKNOWN_ETSY_PUBLISHES** |  |
| `store_foundation.limits.LIMITS['banner_px'] (UNVERIFIED_UNKNOWN)` | None | (1600, 400) | **REPO_UNKNOWN_ETSY_PUBLISHES** | repo records this as UNKNOWN; Etsy publishes it |
| `store_foundation.limits.LIMITS['icon_px'] (UNVERIFIED_UNKNOWN)` | None | (500, 500) | **REPO_UNKNOWN_ETSY_PUBLISHES** | repo records this as UNKNOWN; Etsy publishes it |
| `commerce.shop_package.shop_text()['title'] length` | 56 | 55 | **DISAGREES** | 'Crochet patterns checked row by row before they are sold' |
| `commerce.shop_package.shop_text()['policy_additional']` | True | True | **DISAGREES** | a Canadian shop sending policy_additional gets an error from Etsy |
| `store_foundation.copy_v2` | None | 55 | **NOT_PRESENT** | ModuleNotFoundError: No module named 'brambleloop.store_foundation.copy_v2' |
