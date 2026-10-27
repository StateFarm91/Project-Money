# Etsy listing-image compliance for digital crochet patterns (W-IMAGEPOLICY)

Read on 2026-10-27 (UTC) by W-IMAGEPOLICY. Every quote below was copied from Etsy's public Help
Center article API (`https://help.etsy.com/api/v2/help_center/en-us/articles/<id>.json`, the same
route as `gates/policy_reader.read_help_center`). The raw JSON is saved under
`research/final_build/w4/evidence_IMAGEPOLICY/`. No etsy.com/legal page and no Seller Handbook page was
requested past a single status probe. The handbook returned HTTP 403, so it was not pursued.
This is the company's conservative reading and is not legal advice.

## 1. Conclusion

**Disclosed renders alone are no longer compliant for a pattern listing.** Under Etsy's current Help
Center wording, a listing for a crochet pattern must include **at least one real, unedited photograph
of something actually made from the pattern, against a real background**. A deterministic render is
a "simulated result" and does not satisfy that requirement, however clearly it is labelled. Renders,
charts and PDF page previews may stay as *additional* images if they are accurate and labelled.

On the **first image**, Etsy's wording is a best practice rather than a hard rule: make it "the
clearest, most realistic representation of the item buyers will receive". The conservative reading,
which we adopt, is that the first image should be the unedited photograph of the made sample.

The Launch-0 strategy of render-only galleries (D-FB-7 and D-FB-9) **cannot ship as it stands.** Every
Launch-0 pattern needs a physically made sample and photographs of it before it goes live.

**Confidence:**
- **High (about 90%)** that a photograph of a physically made result is required for pattern
  listings. Two separate Help articles say it in plain words, one of them edited five days ago.
- **Medium-high (about 75%)** that the photograph should be first. The text is phrased as a best
  practice, but nothing else in a pattern gallery would be a more realistic first image.

## 2. The exact current wording

### 2.1 Help article 115015663347: "Requirements and Best Practices for Images in Your Etsy Shop"

- URL: https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop
- `edited_at`: **2026-10-22T13:45:42Z** (`updated_at` 2026-10-27T07:35:36Z)
- Evidence: `evidence_IMAGEPOLICY/article_115015663347.json`

The section is headed "Image authenticity requirements". Quoted verbatim:

> Your listing images should help buyers understand exactly what they will receive:
> - All images must accurately reflect the item's true appearance, including color, condition, scale, and materials.
> - Your listing must include at least one unedited photo of the actual item against a real background, meaning the photo hasn't been edited or changed in any way. Some exceptions may apply depending on the types of items you sell.
> - Outside of your required unedited photo, you can still use photo-editing tools, including AI, to adjust lighting or color, crop or resize images, or change backgrounds.
> - You can't use editing to hide flaws, conceal damage, or edit an item's appearance to make it look different from what the buyer will receive.
> - You can't use images that create false expectations about what the buyer will receive.
> - **If you sell functional guides like patterns, recipes, or instructions, you'll also need to show an actual result made using your instructions, not an AI-generated or simulated result, so buyers know what to expect.**
>
> Beyond these requirements, here are a few best practices to keep in mind when using AI in your listings:
> - Make your first listing photo the clearest, most realistic representation of the item buyers will receive. Because it's the first image buyers see, take extra care to make sure it accurately represents your item and isn't misleading.
> - If you use AI to edit any of your listing photos, note whether images were edited in your listing description. This gives buyers more context about how your listing images were created and helps you be transparent about your use of AI.
>
> Learn more about these requirements and rules for print-on-demand, customized, made-to-order, digital items, and more.

Both the word "exceptions" and the "Learn more" line link to
`https://www.etsy.com/legal/policy/listing-image-requirements/253962679005`. That page was **not read**
because it is behind DataDome. See section 6.

The same article also sets these technical requirements:
- **File types:** "All images in your shop should be one of these file types: .jpg, .gif, .png, .svg, or .heic." Animated GIFs and transparent PNGs are not supported.
- **Resolution:** "We recommend your listing photos have a width and height of at least 2000 pixels or more. Your first listing photo should have a width and height of at least 635 pixels to avoid showing up lower in searches."
- **Orientation:** "The first photo in a listing should be horizontal (landscape) or square."
- **Thumbnail crop:** "Make sure that your thumbnail images have enough of a border that they can be cropped to square, portrait, and landscape thumbnails without losing some of the product."

### 2.2 Help article 44297885802647: "How Do Etsy's Listing Image Requirements Apply to My Listings?"

- URL: https://help.etsy.com/hc/en-us/articles/44297885802647-How-Do-Etsy-s-Listing-Image-Requirements-Apply-to-My-Listings
- `edited_at`: **2026-10-16T14:41:39Z**
- Evidence: `evidence_IMAGEPOLICY/article_44297885802647.json`

> Etsy requires at least one unedited photo for most items. For other images, you can use photo editing tools, including AI, as long as your images accurately represent what buyers will receive.

> **What counts as an unedited photo?** An unedited photo should show the actual item against a real background and must not be edited or changed in any way. Some exceptions may apply depending on the types of items you sell. All your listing photos must accurately represent what the buyer will receive. Outside of your required unedited photo, you can use photo-editing tools, including AI, to adjust lighting or color, crop or resize images, or change backgrounds, as long as those edits don't make the item appear different.

> **Does every listing photo need to be unedited?** For most items, you only need at least one real, unedited photo of your item against a real background. You can use photo editing tools in your other listing photos, as long as the edits don't misrepresent what buyers will receive.
> Make your first listing photo the clearest, most realistic representation of the item buyers will receive. [...]

> **What is Etsy's policy on AI-generated art or products?** [...] we allow AI-generated art when sellers play a clear creative role in what they create and are transparent about their process. Sellers must still disclose when an item is created using AI and cannot misrepresent AI-generated work as handmade or entirely their own creation.

> **What if I sell digital downloads or personalized items?** Requirements may differ depending on what you sell:
> - Print-on-demand items: If a production partner prints your original design on a standard base product (like a t-shirt or mug), you may use a stock photo mockup, if the stock photo's owner has authorized its use.
> - **Digital downloads: If your item has a visual component, such as a printable or template, include a preview of the actual content buyers will receive.** For digital items without a visual component, you may use representative imagery, including AI-generated images, as long as it doesn't mislead buyers about what they're purchasing.
> - Customized or made-to-order items: For customized items you make yourself, use photos of real, finished items you've made in the past to help buyers see the quality of your work.
> - **Craft patterns, recipes, seeds, or similar items: Include at least one real, unedited photo of something made using your product. AI-generated images cannot be the only images used to show the finished result.**

> **What happens if Etsy detects AI-generated images when I'm creating a listing?** If AI-generated images are detected when you create a listing, we will provide tips to help you accurately represent your item and meet our photo expectations.

> **What happens if someone reports my listing for potentially misusing AI?** In the beginning, these reports will help us better understand how buyers perceive potential AI misuse and won't result in immediate enforcement action. We'll continue investing in detection and enforcement tools as we learn more about how AI is being used across Etsy.

### 2.3 Help article 360024112614: "What Can I Sell on Etsy?"

- URL: https://help.etsy.com/hc/en-us/articles/360024112614-What-Can-I-Sell-on-Etsy
- `edited_at`: **2026-10-22T13:45:37Z**
- Evidence: `evidence_IMAGEPOLICY/article_360024112614.json`

> Designed by a seller: As a seller, you can offer your original design as a digital download [...] This category also includes seller-prompted AI creations. [...] Seller-prompted AI creations must disclose the use of AI.

> AI-generated content: Etsy allows sellers to use artificial intelligence (AI) tools to create certain items, as long as they contribute their own creative input and follow Etsy's policies. **Sellers must disclose within their listing description if an item is created with the use of AI.**
> [...]
> Some forms of AI-generated content are not allowed on Etsy, including:
> - Bot-generated content
> - **AI-generated functional instructions, such as craft patterns, recipes, and instructions**
> - AI prompt bundles

### 2.4 Other articles read (no image rule beyond the above)

| id | title | edited_at | relevance |
|---|---|---|---|
| 360016260113 | How to Edit Your Listing Photos | 2026-06-29 | "The first photo will be the thumbnail for your listing." A dark, blurry or collage main image may rank lower. |
| 4406604492823 | How to Add a Text Alternative to Your Listing Images | 2024-12-10 | If no alt text is given, Etsy adds AI-generated alt text. Alt text should describe the image. |
| 115015628347 | How to Manage Your Digital Listings | 2025-03-21 | Mechanics only. No image rule. |
| 10603291042967 | Newly Crafted: Etsy Updates for Your Shop | 2026-09-22 | Thumbnail preview before publishing. Attribute suggestions are drawn from the featured image. |

The repo's own previous reading, `policy_knowledge.READINGS["listing_image_rules"]` (read_on
2026-09-26), is labelled `basis: search_engine_excerpt_of_official_page`. It predates both the
2026-10-16 and 2026-10-22 edits and does not contain the pattern-specific sentence. It is stale.

## 3. The image categories, one at a time

| Category | What Etsy says | Use on a Brambleloop pattern listing |
|---|---|---|
| **Photo of a physically completed sample** | Required: "at least one real, unedited photo of something made using your product" (2.2), and "an actual result made using your instructions" (2.1). | **Mandatory, at least one.** It must be unedited, show a real background, and show the finished object made from this release's PDF. |
| **Accurate illustration or deterministic render** | Not named as such. "not an AI-generated or **simulated** result" (2.1) excludes it as the required image. "All images must accurately reflect the item's true appearance" applies to it. | Permitted only as an *additional* image: accurate, labelled, never the only image of the finished result, and never presented as a photograph. |
| **AI-assisted imagery** (AI edits to a real photo) | "Outside of your required unedited photo, you can still use photo-editing tools, including AI, to adjust lighting or color, crop or resize images, or change backgrounds." Best practice: note AI edits in the description. | Allowed on photos *other than* the required unedited one. The edit must not change the item's appearance. Note it in the description. |
| **AI-generated image of the finished item** | "AI-generated images cannot be the only images used to show the finished result." Etsy may show tips when it detects AI images at listing time. | At most a supplement. The repo already refuses it by default (`eligibility.GENERATED_MEDIA`, F-852 / D-W4-F852-AMEND). Keep it that way. |
| **Mockups** | Named only for print-on-demand: a stock-photo mockup is permitted with the owner's authorisation. Not named for patterns. | Not a route for patterns. The old "computer-generated mockups... first image is the real deal" excerpt came from the legal page and is unverified this round. |
| **Digital-download content preview** | "If your item has a visual component, such as a printable or template, include a preview of the actual content buyers will receive." | A crochet PDF has visual content, so **include a page preview of the actual PDF.** This is additional to the photo, not a substitute for it. |
| **First image** | Best practice: "the clearest, most realistic representation of the item buyers will receive". It must be landscape or square, at least 635 px, and crop-safe. | The unedited sample photo goes first. A PDF preview is a better literal match for "the item buyers will receive", but the hero rule in `publish/eligibility` (job DESIRE) and Etsy's realism wording both point to the made object. |
| **AI disclosure** | Description: "Sellers must disclose within their listing description if an item is created with the use of AI" (2.3). Image edits: the description should note them (best practice). | The disclosure belongs in the **description**. No Help article read here names a "made with AI" listing attribute or field, and none says to put the disclosure inside the image. Whether the listing form has such an attribute must be checked in person (section 6). |

## 4. What must change in the Launch-0 gallery strategy

1. **D-FB-7 and D-FB-9 are overtaken for live sale.** A render-only listing, including one whose
   first image is a `disclosed_render` hero, does not meet "include at least one real, unedited photo of
   something made using your product". Renders can stay as images 2 and later. They cannot be the
   whole gallery, and they should not be first.
2. **Every Launch-0 pattern needs a physical make before it is listed**, including the Class A
   hexagon-coaster-set. The `gates.risk_matrix` rule that "a make proves nothing it needs" was
   about pattern truth. This is a separate marketplace requirement, and it applies to every pattern.
3. **The required photo must be unedited.** No filter, retouch, background swap or composite. To be
   safe, also no crop or resize: shoot it in final framing, landscape or square, with the whole object
   and margin for the thumbnail crop, at 2000 px or more on each side. Keep the original file and its
   hash as evidence. Other photos may be colour-corrected or cropped.
4. **Add a PDF page preview frame** (`pattern_page_preview`) to every gallery to meet the
   digital-download content-preview rule.
5. **Keep the disclosure copy.** The `disclosed_render` sentence must be revised: it currently says
   "each listing image is a digital rendering ... no sample has been photographed", which becomes
   false once a photo is added. It should name which images are renders.
6. **Re-read the policy record.** Replace `READINGS["listing_image_rules"]` (search-engine excerpt,
   2026-09-26) with this API reading (`edited_at` 2026-10-22) so the freshness watch tracks the real
   text. This worker changed no code. Proposed rule text: "pattern listings require ≥1 unedited
   photograph of a finished object made from this release's instructions, against a real background;
   renders/AI/simulated images may only supplement it".
7. **Enforce it in code**, which is not done today (section 7). A pattern listing set should fail
   publication unless it contains one `PHYSICAL_PRODUCT_PHOTO` frame that has a rights basis
   (`physical_upgrade.RIGHTS_BASES`), bytes on file, an `unedited: true` attestation and a binding to the
   release version it was made from. The `physical_upgrade` path already does intake, rights handling
   and re-certification. It is currently an optional upgrade and must become a precondition.
8. **Separate, possibly larger issue (not images): "AI-generated functional instructions, such as
   craft patterns" are listed as not allowed** (2.3, edited 2026-10-22). Brambleloop's patterns are
   compiled and validated by deterministic code from a CIR, but the shipped copy says "This design was
   created with AI assistance" (`platform_policy.DISCLOSURES["ai_assisted_design"]`, `publish/pdf.py:396`,
   `brand/storefront.py:77`, `store_foundation/copy_v2.py:311`). The disclosure is required and must stay
   truthful. Whether Brambleloop's process falls under the prohibition is a question for the owner
   (section 6), and the answer must not be decided by rewording the disclosure.

## 5. Physical photo lists

The general rules for both products are:
- The sample is made from the exact release PDF being listed, and its content hash is recorded on the
  tester sheet, as `quality/tester_kit.py` already requires.
- Shoot in daylight on a real surface such as wood, linen or a countertop. No seamless studio sweep is
  needed, but no digital background either.
- Each photo has a rights basis recorded at intake.
- Measurements are taken without stretching. If they differ from the stated dimensions, Product Truth
  must reconcile the listing copy before publishing. Do not retake the photo to hide the difference.

### 5.1 market-basket-small: Crochet Hexagonal Bread Basket

Stated size: 16.0 cm across the points, 13.9 cm across the flats, 9 cm tall. Single crochet,
worsted-weight cotton, colour A cream and colour B wine.

| # | Shot | Edited? | Purpose |
|---|---|---|---|
| **1 (FIRST)** | Three-quarter view from about 30° above. The whole basket on a real table, empty or holding two or three bread rolls that do not hide the rim, landscape or square, centred, with generous margin. | **Unedited (the required photo)** | Hero. Shows the hexagonal form, the wall and both colours. |
| 2 | Top-down, straight overhead, showing the hexagonal base, the six increase lines and the inside. | may adjust exposure | Shape and construction. |
| 3 | Side profile at table level, showing the wall height and whether the walls stand straight. | may adjust | The `dimensional_form` risk the product is Class B for. |
| 4 | Scale: a ruler or tape across the points (≈16 cm) in frame, and a second frame with the tape at wall height (≈9 cm). | may crop | Honest scale, supporting "accurately reflect ... scale". |
| 5 | Detail macro of the rim and colour change, so single-crochet texture is legible. | may crop | Stitch and fabric identity. |
| 6 | In use: on a set table with bread. | may adjust | Desire and lifestyle. |
| 7+ | Labelled render or chart (`chart_render`), PDF page preview (`pattern_page_preview`), contents/infographic frame. | n/a | Digital-download content preview and customer information. |

### 5.2 hexagon-coaster-set: Hexagon Coaster Set (4)

Stated size per coaster: 9.7 cm across the points, 8.4 cm across the flats. Joined rounds with
increases at six corners and a contrast round one in from the edge.

Make **all four** coasters so the hero matches "Set (4)". One coaster would be a real result, but it
does not match the title.

| # | Shot | Edited? | Purpose |
|---|---|---|---|
| **1 (FIRST)** | All four coasters laid flat, slightly fanned or in a 2 × 2 group, on a real table, three-quarter angle, landscape or square, with margin. | **Unedited (the required photo)** | Hero. Shows the set, the shape and the contrast round. |
| 2 | Flatness: a low side angle at table level showing a coaster lying flat, without being pressed down. | may adjust | The product's own disqualifier ("does not lie flat"). |
| 3 | Scale: a ruler across the points (≈9.7 cm) on one coaster. | may crop | Size claim. |
| 4 | Detail macro of one corner, showing the stacked increases and the contrast round. | may crop | Stitch and construction identity. |
| 5 | In use: a mug on one coaster, with the others stacked beside it, mostly visible. | may adjust | Use and desire. |
| 6+ | Labelled chart render and PDF page preview. | n/a | Content preview. |

Also update `quality/tester_kit.py` step "Photograph the finished basket on a plain surface (top and
side) in daylight" to the shot list above, and add a coaster kit. This worker made neither change,
because only this file is in scope.

## 6. What the owner must decide or read in person

1. **Read in a normal browser:** `https://www.etsy.com/legal/policy/listing-image-requirements/253962679005`
   (Listing Image Requirements). Both Help articles link to it for the "exceptions" and for "rules
   for ... digital items". Check whether any exception covers patterns, and check the current mockup
   and render wording. This worker did not read it because the page is bot-protected.
2. **Read in person:** `https://www.etsy.com/legal/handmade` (Creativity Standards). Check the exact
   scope of "AI-generated functional instructions, such as craft patterns", and whether a pattern
   whose stitches are generated and verified by deterministic code, with AI used in the design
   process, falls under it.
3. **Check in the Etsy listing form** (Shop Manager, in person) whether a "made with AI" or similar
   attribute now exists and what it asks. No Help article read here names one.
4. **Decide: make the samples.** Who crochets them (owner or tester under the `tester_agreement`
   rights basis), and in what order across the Launch-0 products. Estimates: the small basket is about
   2.2 h and 52 m of yarn, with a cost ceiling of about CA$59.65 at the risk matrix's own rates. The
   coaster set is four small pieces. The cloudline baby blanket is about 15 h. This is a physical
   action, and spend if a tester is paid. **Consequence of waiting:** no Launch-0 pattern listing can
   go live compliantly.
5. **Decide: Launch-0 order.** Listing the cheapest makes first (the coasters, then the small basket)
   is the fastest compliant path.
6. **Acknowledge:** D-FB-7 and D-FB-9 remain valid as internal visual-quality rules. They no longer
   decide marketplace compliance.

## 7. What Product Truth already enforces (grep of this branch)

| Where | What it does | Gap against the current Etsy text |
|---|---|---|
| `gates/platform_policy.ASSET_ROLES` | `primary_listing_image`, `finished_object_photo`, `detail_photo` and `scale_reference` are `PHOTOGRAPH_REQUIRED`. `chart_render`, `pattern_page_preview`, `colourway_illustration` and `mood_frame` are `GENERATED_PERMITTED`. | The right instinct, but `classify()` exempts any `deterministic_render` from `PHOTOGRAPH_REQUIRED`. Etsy now names "simulated" results, so that exemption no longer satisfies the pattern rule. |
| `gates/platform_policy.DISCLOSURES` | `digital_download`, `ai_assisted_design`, `generated_imagery`, `deterministic_render` and `disclosed_render` sentences. `gates/policy.check_ai_disclosure` requires them verbatim in the description. | The description placement matches Etsy ("within their listing description"). The `disclosed_render` text ("no sample has been photographed") must change once a photo exists. `ai_assisted_design` must be reviewed against the functional-instructions prohibition. |
| `publish/eligibility.py` | Classes are `MEDIUM_PURPOSES`, with only `PHYSICAL_PRODUCT_PHOTO` able to serve `PHYSICAL_PROOF`. `GENERATED_MEDIA` (AI concepts) is refused for export, with an exception route (D-W4-F852-AMEND) that excludes the hero. Every non-photo is labelled (`RENDER_LABEL`). `verified_exception` refuses any generated image presented as a photograph. | Nothing *requires* a `PHYSICAL_PRODUCT_PHOTO` in a pattern listing. Per DECISION_LOG, a `DIGITAL_TWIN_RENDER` hero is accepted as the D-FB-9 disclosed hero. |
| `visual/disclosed_render.py`, `publish/disclosed_listing.py`, `runtime/release.py`, `gates/first_customer.py` | Build and certify the render-only gallery, with the disclosure in pixels, alt text and copy (D-FB-9 LIFESTYLE_QUALITY). | This is the path the new rule disallows as the *only* imagery. |
| `publish/physical_upgrade.py` | Intake of a real photo by hash, with a rights basis, as a `PROOF` frame. Re-certification. | It is an optional upgrade. It does not mark a photo as unedited, and does not require it before publish or put it first. |
| `publish/owned_photography.py` | An AI illustration of the finished object, with the disclosure "Not a photograph of a made item". | Allowed by Etsy only as a supplement. It must never be the sole finished-result image. |
| `quality/tester_kit.py` | Small-basket make kit, with a release hash on the record sheet and photographs "top and side". | The shot list is too thin for the hero and has no "unedited" instruction. There is no coaster kit. |

## 8. Remaining uncertainty

- The legal policy page (section 6, item 1) may list exceptions. Etsy says "Some exceptions may apply
  depending on the types of items you sell", but the Help FAQ's pattern bullet *adds* the requirement
  rather than lifting it, so an exception for patterns is unlikely.
- It is unclear whether Etsy's own in-app crop or thumbnail adjustment counts as "edited". The
  adjustment tool sets a thumbnail and probably does not edit the image. The crop is an edit. Shoot in
  final framing to avoid the question.
- Enforcement is soft for now: reports "won't result in immediate enforcement action", and detection
  only shows tips. That is not a licence. The Execution Directive forbids misrepresentation regardless
  of enforcement.
- "First image" is phrased as a best practice. Our choice to put the photo first is conservative, not
  compelled by Etsy's wording.
