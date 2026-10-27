# Manual Etsy listing package: `market-basket-small@1.2.0` (Crochet Hexagonal Bread Basket)

**Status: NOT READY TO PUBLISH.** This is a preparation package for the owner to enter by hand in
Etsy Shop Manager. Nothing was published, and no request was made to Etsy or Railway.

§9 lists what must clear first. The hard blockers are:
- a physical sample and its photographs;
- the open owner decision on Etsy's "AI-generated functional instructions" rule;
- the category (PENDING: W-LAUNCHFIX E4);
- **a product-identity conflict this package found in the system's own output.** The listing is titled "Bread Basket" but is merchandised as **nursery decor for children under 3** (§2.4, E-6).

**How the package was made**
- **Prepared by:** W-LISTING on `claude/w4-LISTING1`, cut from `origin/claude/w4-INTEG8-next` at `b0133916`, on 2026-10-27 (UTC).
- **Copy, tags and price:** from the repo's real release chain, run in a SHADOW worker:
  - `gate.certify` → `listing.draft` → `assets.build` → `pricing.position` → `listing.seo` → `launch.plan` → `store.publish` (refused, as expected in SHADOW);
  - via `research/final_build/w4/pipe_chain_run.py`, on a scratch SQLite, at nice 19;
  - with sockets closed, no credentials and no model call.
- **Evidence:** `../evidence_LISTING1_chain_run.json`.
- **Hand-written text:** only where marked **[PACKAGE EDIT]**, and each edit says why.

**Release identity**

| | Value | Source |
|---|---|---|
| CIR slug @ version | `market-basket-small@1.2.0`, the latest in code (`products.launch0.cir_for("basket_small")`) | code |
| Candidate (product) | `nursery-nesting-baskets` ("Nesting Baskets, three sizes"), small variant | `products.launch0` |
| Content / release hash | `1ddde587f537388b4a9dd5a74e9a0e0ebadc6ce0c0a79372dd6b867a230b3991` | chain run; equals LAUNCH_PATH §3, W4-SAMPLE §1.1 and the tester kit |
| Certified **in production** at this version? | **UNKNOWN: NEEDS PRODUCTION READBACK** | LAUNCH_PATH E11 |
| Product Truth | PASS (`passes_gates=True`) | `products.launch0.product_truth` |
| Risk class | B (`dimensional_form`). The first customer needs `partial_physical`, which in practice means a full make. | `gates.risk_matrix`; W4-SAMPLE §1.1 |
| Children's assignment | `('nursery_decor', 'under_3')` | `products.launch0.childrens_assignment("market-basket-small")` |

---

## 1. Title

```
Hexagonal Bread Basket | Crochet Pattern PDF | Nursery | Written Instructions and Chart | US and UK Terms
```

**Length.** 105 characters, within the 140-character limit.
- `seo.constraints` records the limit as UNVERIFIED.
- `integrations.etsy_constraints` records it as VERIFIED_HELP_CENTER (article 115015628707, 2026-10-06).
- The disagreement is item E-10.

**Words.** 15 words, at the edge of the "less than 15 words" guidance (recommended only).

**Characters.**
- `publish.listing_schema.title_problems(title)` returns `[]`.
- The title uses only the OpenAPI charset.
- It contains none of `% : & +`.

**Source.** `seo.build_title` via `listing.seo`.

**⚠ DEFECT (E-6): the title says both "Bread Basket" and "Nursery".**
- The CIR title is "Crochet Hexagonal Bread Basket".
- The "Nursery" segment and the nursery tags come from the candidate's children's assignment, `nursery_decor` / `under_3`.
- A basket named for bread and also sold as nursery decor for under-3s is a contradiction a buyer will notice.
- This package does not choose between the two framings. That is a Product Truth and catalogue decision, and it must be made before listing. See §2.4.

## 2. Description

### 2.1 The system's description (verbatim, from the stored `Listing.description`)

The sentence marked ⚠ must change (§2.2).

```
Crochet Hexagonal Bread Basket — a crochet pattern, not a finished item. You receive an instant digital download. Why it is worth making: worked in 2 colours, written for a confident beginner maker, every row written out and charted, so you can follow whichever you prefer.
If you are searching for diy basket, crochet home decor and home decor diy, this is the one: every row is written out and charted, and every stitch count is checked before release.

WHAT YOU GET
- Written instructions for every row, with a stitch count on each
- A chart drawn from the same pattern as the written instructions, so the two always agree
- Two PDFs, one in US terms and one in UK terms — the same pattern, each written throughout in its own terminology, with a stitch key to match
- 9-page PDF, laid out to be readable on a phone or printed

THE DETAILS
- Finished size: hexagon base 16.0 cm across the points, 13.9 cm across the flats; 8.7 cm tall, worked at the gauge below
- Difficulty: confident beginner
- Yarn: worsted cotton
- Fibre: as named above; the pattern does not specify a composition, so choose any yarn of the same weight that meets the gauge
- Gauge: 12.5 sts x 13.8 rows = 10 cm in sc, 5 mm hook
- Stitches used: inc, sc
- Colours: 2 (cream, wine)
- cream: about 32-48 m
- wine: about 10-14 m
- Yarn quantities are estimates with a +/-20% range, not measurements. Yarn use varies with yarn, hook and tension.

SAFETY AND SUITABILITY
- Who this is for: This pattern makes an item intended for children under 3 years, finishing at hexagon base 16.0 cm across the points, 13.9 cm across the flats; 8.7 cm tall at the stated gauge. The age band is stated here rather than left to be read off a photograph, because it is the fact every safety note below depends on, and because the person buying this is usually choosing for one particular child.
- Not for an unsupervised sleep space: This is for supervised, awake use, and it does not belong in an unsupervised sleep space before 12 months. The American Academy of Pediatrics' 2022 recommendations keep soft objects and loose bedding (blankets, comforters, pillows, soft toys) out of the infant sleep area. Keep this out of the cot, and out of reach of a baby who is in one. We know where a soft crocheted thing in a nursery is most likely to end up, so we say so here rather than leave it to be assumed.
- If you sell what you make: What this licence permits is set out in the licence terms; this is about what follows if you do it. Sell a finished children's item and you become its manufacturer. In the United States that is CPSIA: testing by a CPSC-accepted third-party laboratory, a Children's Product Certificate, and a tracking label on the product itself. In Canada it is the Canada Consumer Product Safety Act and, for a toy, the Toys Regulations SOR/2011-17. We are not your lawyer and this is a pointer rather than advice, and we are not entitled to let you assume none of it exists.
The pattern itself carries the full set of safety notes for a children's item, each with its source, and states the date the guidance was compiled.

HOW THIS PATTERN WAS MADE
This design was created with AI assistance, and every row's stitch count is checked before release. If anything in it does not add up, tell us: we correct the pattern itself and send you the corrected file.

PATTERN USE AND SUPPORT

- for the buyer's own use, and to teach from in a class where each participant has their own copy
- finished items may be sold by individual makers and small businesses, not manufactured at scale
- the pattern file, its charts and its images may not be shared, resold, uploaded or included in another publication
- questions are answered through the shop the pattern was bought from, against the exact version that was bought
- corrections are free: a corrected pattern replaces the old file, and anyone who bought an earlier version can ask for the corrected one at any time

These are the terms Brambleloop offers; they have not yet been through legal review.

DISCLOSURES
- ⚠ About the images: each listing image is a digital rendering of the pattern's finished design, not a photograph. Every stitch in it is drawn from the pattern itself at the stated gauge, with a centimetre scale; no sample has been photographed, and your finished piece will vary with yarn and tension.
- Charts and previews are rendered directly from the pattern file, so they show exactly what is in the document.
- This design was created with AI assistance, and every row's stitch count is checked before release.
- This is a digital pattern. No physical item is shipped.
```

### 2.2 Required edit before publication

**[PACKAGE EDIT 1] Replace the `disclosed_render` bullet.**

Etsy requires at least one real, unedited photo of the made result on a pattern listing (W-IMAGEPOLICY §2.1 and §2.2). Once that photo is in the gallery, "each listing image is a digital rendering … not a photograph" and "no sample has been photographed" become **false** (W-IMAGEPOLICY §4.5).

Use these existing `DISCLOSURES` sentences verbatim, plus one factual sentence about the sample. Complete the sentence only once the photo exists:

```
- About the images: the first photo is an unedited photograph of a basket made from this exact pattern version. Some listing images are illustrations or renders rather than photographs, and are labelled where they appear.
```

- The second sentence is `DISCLOSURES["generated_imagery"]`.
- The `deterministic_render` bullet stays as it is.
- If a non-required photo is edited with AI tools, add: "Some photos have been colour- or light-adjusted with editing tools." The recommendation is to make no AI edits at all.
- This deviates from the system's output. `gates.policy.check_ai_disclosure` would flag the edited copy until engineering adds a mixed-gallery disclosure (E-1).

**Not edited**
- **The AI disclosure.** `DISCLOSURES["ai_assisted_design"]` stays verbatim. Do not reword it to dodge the functional-instructions prohibition (O-1).
- **Testing claims.** No "tested" or "measured" claim is added until a `PhysicalTest` with `passed=True` is bound to `1ddde587…`.

### 2.3 Coverage of the required description elements

| Element | Where | Backed by |
|---|---|---|
| What the buyer receives | "WHAT YOU GET": written rows, a chart, **two PDFs (US and UK terms)**, 9 pages | `assets.build` pages=9; `TERMINOLOGIES` |
| Skill level | "Difficulty: confident beginner" | `runtime.release._difficulty` |
| Finished size | base 16.0 cm across the points, 13.9 cm across the flats; 8.7 cm tall, at the stated gauge | twin; `supported_claims` |
| Materials | worsted cotton, 2 colours, yardage ±20% | CIR and twin (40.2 m + 11.9 m, W4-SAMPLE §1.3) |
| Gauge | 12.5 sts x 13.8 rows = 10 cm in sc, 5 mm hook | CIR gauge |
| Licence | "PATTERN USE AND SUPPORT"; "not yet been through legal review" | `commerce.terms` |
| AI disclosure | "HOW THIS PATTERN WAS MADE" and "DISCLOSURES" | `DISCLOSURES["ai_assisted_design"]` |
| Digital, nothing shipped | "This is a digital pattern. No physical item is shipped." | `DISCLOSURES["digital_download"]` |
| Delivery and support | instant download; questions through the shop; free corrections (shop delivery message in §6) | `commerce.terms`, `copy_v2` |
| Children's safety | "SAFETY AND SUITABILITY" | `childrens_statements` for `nursery_decor` / `under_3` |

The system's disclosure check (`commerce.buyer_trust.listing_disclosure_finding`) read `complete: true, missing: [], misplaced: []`.

### 2.4 Product-identity conflict (must be resolved; not edited here)

The system's own output contradicts itself in four places:

| Source | Says |
|---|---|
| CIR title, PDF and description first line | "Crochet Hexagonal Bread Basket" |
| Title segment, tags (`nursery crochet`, `nursery basket`) and the SAFETY section | nursery decor, "intended for children under 3 years" |
| W-IMAGEPOLICY §5.1 and W4-SAMPLE §1.6 shot plans | styled with bread or rolls on a set table |
| Pricing reason | "3 finished sizes from one chart, which no profiled competitor offers". **But this listing sells one size**, and the description gives one finished size. |

**Consequences.**
- Food-styled photos on a listing that says "for children under 3" make the gallery and the copy disagree, which is the kind of misleading-image problem Etsy's authenticity rules target.
- The under-3 assignment also makes the listing a children's listing under Etsy's Children and Baby policy. That policy needs the owner's in-person reading (ETSY_POLICY_READINGS_PACKET source 6).

**Required decision** (company/Product Truth, with owner acknowledgement). Choose one of:
- **(a)** a bread basket, with the children's assignment removed for this variant and the copy and tags regenerated by the system; or
- **(b)** a nursery basket, with the CIR title changed and a new version released.

Either way the copy is regenerated by `listing.seo`, not hand-edited. The §8 shot list below is written to work for either framing, with the in-use shot marked as framing-dependent.

## 3. Category and attributes

**Category: PENDING: W-LAUNCHFIX E4.**

**What the repo has.** The only committed Etsy taxonomy evidence is `research/final_build/w4/evidence_FMBATCH1/prod_api_audit_taxonomy_refreshed_20261021T0242Z.json`:
- 3065 nodes, recorded by name only;
- `pattern_subtree: 0`;
- **no ids**.

**The candidate node by name** is `Craft Supplies & Tools > Patterns & How To > Patterns & Blueprints`, which has no children.

**Not usable.** "Crochet" exists only as `Art & Collectibles > Fiber Arts > Crochet` and `… > Crochet Hooks`, and neither may be used.

**Exactly what is missing:**
1. The taxonomy_id of Patterns & Blueprints.
2. That node's property schema, including whether "Crochet" is a value.
3. Production's newest `etsy.taxonomy_refreshed` row (`category_choices`, `property_candidates`), which needs a production readback.

Do **not** use `ListingPayload.taxonomy_id = TAXONOMY_PATTERNS`. The system reports it as "taxonomy 66 was never verified".

**If the category is open.** A children's node for nursery items would further depend on §2.4 and the children's policy reading.

**Attributes the system decided** (`listing.seo` output). These are pattern facts, not Etsy property ids; the property ids are PENDING E4.

| Key | Value | Note |
|---|---|---|
| craft_type | crochet | PENDING E4 |
| pattern_type | basket | PENDING E4 |
| skill_level | confident beginner | map only to an offered value |
| primary / secondary colour | cream / wine | PENDING E4 |
| file_type | PDF | |
| digital / instant_download | true / true | listing type Digital |
| includes_chart / includes_written_instructions | true / true | description |
| terminology | US terms | **defect E-9:** the listing ships US and UK |
| occasion | none | |

**Fixed listing fields** (`integrations.etsy.ListingPayload`):

| Field | Value |
|---|---|
| type | download |
| who_made | `i_did` (owner decision, O-6) |
| when_made | `made_to_order` |
| is_supply | true |
| quantity | 999 |
| materials | `worsted cotton` (de-duplicated) |
| renewal | manual |

## 4. Tags (exactly the system's SEO output)

```
basket crochet, nursery crochet, nursery basket, pdf crochet pattern, hexagon basket, beginner crochet, diy basket, written and chart, crochet home decor, digital download, home decor diy, instant download pdf, yarn craft project
```

| # | Tag | Chars | Note |
|---|---|---|---|
| 1 | basket crochet | 14 | |
| 2 | nursery crochet | 15 | depends on §2.4 |
| 3 | nursery basket | 14 | depends on §2.4 |
| 4 | pdf crochet pattern | 19 | |
| 5 | hexagon basket | 14 | |
| 6 | beginner crochet | 16 | The pattern is "confident beginner". The system's `search.tag_truth` let it through; flagged for review, E-11. |
| 7 | diy basket | 10 | |
| 8 | written and chart | 17 | |
| 9 | crochet home decor | 18 | |
| 10 | digital download | 16 | |
| 11 | home decor diy | 14 | |
| 12 | instant download pdf | 20 | |
| 13 | yarn craft project | 18 | |

**Rule checks.**
- 13 tags, which is the maximum of 13.
- Each tag is 20 characters or fewer.
- No tag starts with `'` or `-`.
- Every tag uses only letters, digits and spaces.
- `publish.listing_schema.tag_problems(tags)` returns `[]`.

The limits are VERIFIED_HELP_CENTER in `integrations.etsy_constraints` (article 360000336307, 2026-10-06).

**Evidence for the tags.** The basis is modelled. No search volume is measured.

**Overlap, and why production's tags may differ.**
- `listing.seo` re-spends a tag slot that another of our listings already uses (#240, `_diversify_tags`).
- In this two-product scratch run the coaster was the only other listing. Shared phrases fell from 9 to 6 (`query_portfolio` `shared_before` / `shared_after`).
- Production diversifies against **every** stored listing, so its stored `Listing.tags` for this release may differ from the tags above.
- **If production's stored tags can be read back, they take precedence over these.** They are the system's output for the real catalogue. The same rule applies to the title and description.

**If §2.4 changes the framing,** the tags must be regenerated by `listing.seo`, not hand-swapped.

## 5. Price

| | Value |
|---|---|
| **Price** | **CA$6.50** |
| Plan band | CA$4.00 – 12.00, **SOURCED**: "the band is the CA$4-12 crochet-pattern cluster recorded in radar/market.py OBSERVATIONS. A basket-specific observed price is UNKNOWN: no profiled shop's basket price was captured, so the proposal sits mid-band rather than pretending to a comparable" |
| Decision | CA$6.50, `held_at_proposal: true`. Basis: "products.launch0.price_plan(nursery-nesting-baskets) … decided by commerce.pricing". `within_plan_band: true`. |
| System reason | "3 finished sizes from one chart, which no profiled competitor offers". **Defect E-7:** this listing is one size. The reason belongs to the three-size candidate, not to this single-size listing. The price stays within the band without that reason. |
| Modelled fees (`commerce.pricing.fees(6.5)`) | transaction CA$0.4225 + processing CA$0.445 + amortised listing CA$0.028, giving **net CA$5.60** (take rate 13.8%) |
| Not modelled | Offsite Ads, regulatory operating fee, currency conversion. If all apply, the take rate is 32.4% and the net is CA$4.39 (SECONDARY rates) |
| Listing fee | US$0.20, about CA$0.28, per listing and per renewal (owner `listing_fees`) |
| **Shop currency** | **UNKNOWN in the repo.** The price is in CAD. Confirm it before entering (O-8). |

## 6. Digital download details

| | US terms | UK terms |
|---|---|---|
| File name (`f"{slug}-{pattern_filename(t)}"`) | `market-basket-small-pattern-us.pdf` (34 chars) | `market-basket-small-pattern-uk.pdf` (34 chars) |
| Format | PDF | PDF |
| Pages | 9 | 9 |
| Size (scratch run) | 380,819 bytes | 380,825 bytes |
| sha256 (scratch run, **not** the certified file) | `6b7dfc85…df81` | `010e085a…41b1` |

**Etsy limits** (VERIFIED_HELP_CENTER, article 115015628347):
- at most 5 files;
- at most 20 MB each;
- names of at most 70 characters, which cannot be edited after upload.

**Files to upload.** Use the certified PDFs for this release from **W-PDF (`claude/w4-PDF1`)**. That branch was not on origin when this package was written.
- Each file's sha256 must equal production's `assets.built` `pdf_sha256_by_terminology` for `market-basket-small@1.2.0` (the `check_pdf_hashes` rule).
- The scratch bytes above differ only through `released_on`.
- The tester kit's TEST.pdf (`a724cbae…`, released_on 2026-10-07) is a test copy. It is **not** the listing file unless production's certified hash equals it.

**Delivery message.** This is set at shop level, once. The text is `store_foundation.copy_v2.DIGITAL_SALE_MESSAGE`:

```
Thank you, and happy making. Your pattern is ready now: open your Etsy account, go to Purchases and downloads, and both PDFs (US and UK terms) are there. Etsy has emailed you a link as well.

Two things worth knowing. Under our pattern terms, finished items may be sold by individual makers and small businesses, not manufactured at scale. And if anything in the pattern does not add up, reply to this message with the pattern name and the row number: we correct the pattern itself and send you the corrected file.
```

Whether it is set on the live shop is NEEDS PRODUCTION READBACK.

## 7. Disclosures: every one, and where each goes

| Disclosure | Text (source) | Where |
|---|---|---|
| AI-assisted design | `DISCLOSURES["ai_assisted_design"]` | **Description**. Etsy: "Sellers must disclose within their listing description if an item is created with the use of AI" (360024112614, edited 2026-10-22). It is present twice. It is also in each PDF as `publish.pdf.AI_DISCLOSURE`. |
| Digital, nothing shipped | `DISCLOSURES["digital_download"]` | Description (present); listing type set to Digital |
| Image disclosure | §2.2 [PACKAGE EDIT 1] | Description |
| Renders are renders | in-pixel caption "Digital rendering of the pattern's finished design, not a photograph", plus the render alt text | Each render |
| PDF preview | "Preview of the pattern document" | CONTENTS frame |
| Deterministic charts | `DISCLOSURES["deterministic_render"]` | Description (present) |
| Children's statements | the SAFETY AND SUITABILITY block (`childrens_statements`) | Description (present). The full set is in the PDF. **Depends on §2.4.** |
| AI photo edits, if any | "Some photos have been colour- or light-adjusted with editing tools." | Description, only if an edit was made |
| Licence not legally reviewed | present | Description |
| "Made with AI" attribute | UNKNOWN whether the form has one | The owner checks in person (O-3) |

## 8. Premium listing-gallery brief

**Etsy image specs** (from `integrations.etsy_constraints`, confirmed by W-IMAGEPOLICY):
- up to 20 images;
- each side at least 2000 px recommended; the first image at least 635 px, landscape or square;
- crop-safe borders (the thumbnail crop ratios are UNKNOWN);
- jpg, png, gif, svg or heic, with no transparency;
- images are converted to sRGB;
- images over 1 MB may not finish uploading;
- alt text at most 500 characters (the API limit; Etsy advises 250 or fewer).

**Photos.** These **require a physical sample, which has not yet been made.**
- The basket must be made by an independent tester from the exact release PDF (`1ddde587…`), under W4-SAMPLE package A (`tester_outreach`, CA$59.65 code ceiling, or CA$66.00 recommended).
- Each photo needs a rights basis (`tester_agreement` or `brambleloop_made`) and intake by sha256 (`POST /api/physical-photo`).

| # | Shot | Edit rule | Aspect / size | Label | Alt text (≤ 250; finalise to the photo) |
|---|---|---|---|---|---|
| **1 (FIRST)** | Three-quarter view from about 30° above. The whole basket on a real table, centred, with generous margin. **Empty, or holding neutral contents that suit the §2.4 decision**, never hiding the rim. | **UNEDITED.** No filter, crop, resize or background change. Shoot in final framing; keep the original and its sha256. | **Landscape 4:3 or square 1:1, ≥ 2000 px each side** | none | "Photograph of a crocheted hexagonal basket in cream with wine rounds, made from this pattern, on a wooden table." |
| 2 | Top-down, straight overhead: the hexagonal base, the six increase lines and the inside | may adjust exposure (not AI) | square, ≥ 2000 px | none | "Overhead photograph of a crocheted hexagonal basket showing its six-sided base and corner increase lines." |
| 3 | Side profile at table level: wall height, and whether the walls stand straight | may adjust | square, ≥ 2000 px | none | "Side photograph of a crocheted hexagonal basket at table level showing straight walls about [measured] cm tall." |
| 4 | Scale: a tape across the points (about 16 cm), and a second frame with the tape at wall height (about 8.7–9 cm) | may crop | square, ≥ 2000 px | none | "Photograph of a crocheted hexagonal basket with a tape measure across its base, about [measured] cm across the points." |
| 5 | Detail macro of the rim and the colour change | may crop | square, ≥ 2000 px | none | "Close-up photograph of single-crochet stitches at the rim of a crocheted basket where cream meets wine." |
| 6 | In use. **Framing-dependent (§2.4):** (a) bread on a set table, or (b) a supervised, awake nursery shelf setting, never in a cot | may adjust (not AI) | landscape 4:3, ≥ 2000 px | none | written once §2.4 is decided |

**Measurement rule.** Use **measured** values in alt text 3 and 4. If they differ from 16.0 / 13.9 / 8.7 cm, Product Truth reconciles the copy before publishing. Do not retake the photo to hide a difference.

**Renders, charts and PDF preview** (the system's certified set):
- the disclosed set is `listing_set` plus the angle view, which renders for a vessel;
- supplements come from `applicable_jobs`: MATERIALS, COLOUR_CONTEXT and CONSTRUCTION;
- CONTENTS is added as the PDF preview;
- every image is a 2000 × 2000 PNG, labelled in pixels.

| # | Frame | Label (pixels) | Size | Alt text (system, verbatim unless marked) |
|---|---|---|---|---|
| 7 | Disclosed render, hero (from slightly above) | "Digital rendering of the pattern's finished design, not a photograph" + cm scale | 2000² | "Digital rendering of the pattern's finished design, not a photograph. Crochet Hexagonal Bread Basket: the finished basket seen from slightly above, in cream and wine. About 16 x 8.7 cm at the stated gauge, with a centimetre scale bar." |
| 8 | Disclosed render, scale | same | 2000² | "Digital rendering of the pattern's finished design, not a photograph. Crochet Hexagonal Bread Basket: the finished piece with its size marked, in cream and wine. About 16 x 8.7 cm at the stated gauge, with a centimetre scale bar." |
| 9 | Disclosed render, detail (base from above) | same | 2000² | "Digital rendering of the pattern's finished design, not a photograph. Crochet Hexagonal Bread Basket: the base seen from above, every base round stitch for stitch, in cream and wine. About 16 x 8.7 cm at the stated gauge, with a centimetre scale bar." |
| 10 | Disclosed render, angle | same | 2000² | "Digital rendering of the pattern's finished design, not a photograph. Crochet Hexagonal Bread Basket: the finished piece, in cream and wine. About 16 x 8.7 cm at the stated gauge, with a centimetre scale bar." |
| 11 | Supplement CONSTRUCTION | as above | 2000² | **[PACKAGE EDIT 2]** "Digital rendering of the pattern's finished design, not a photograph. Crochet Hexagonal Bread Basket: how it is built: the stitch count of every round or row, in working order." |
| 12 | Supplement COLOUR_CONTEXT | as above | 2000² | **[PACKAGE EDIT 2]** "… Crochet Hexagonal Bread Basket: each yarn colour's share of the finished piece, counted from the pattern." |
| 13 | Supplement MATERIALS | as above | 2000² | **[PACKAGE EDIT 2]** "… Crochet Hexagonal Bread Basket: the yarn colours, yarn weight, hook size and gauge the pattern calls for." |
| 14 | **CONTENTS: PDF page preview** | "Preview of the pattern document" | 2000² | **[PACKAGE EDIT 2]** "Preview of the pattern document. Crochet Hexagonal Bread Basket: the first pages of the PDF pattern you download, shown at reduced size." |

**[PACKAGE EDIT 2], why.** For this release, `visual.launch_imagery.expected_alt_text` names the candidate, **"Nesting Baskets, three sizes"**. This listing sells one size, so that alt text misdescribes the item. The edit swaps only the name for the release's own title. The certified alt text is what `etsy_verify` reads back, so engineering must make the same change (E-8).

**Image bytes.**
- Use the certified bytes (`runtime.etsy_ops.certified_images`), in listing-set-certificate order.
- Render the CONTENTS preview from the **certified** W-PDF1 file.
- The independent vision review (#61) is UNKNOWN (LAUNCH_PATH E6).

**Order rule.**
1. The photos, with the unedited photo at #1.
2. The renders.
3. The PDF preview, last.

Renders are never first and never the only images of the finished result.

## 9. Outstanding publication requirements (checklist)

Status as of 2026-10-27. **Every box is open.**

### Owner

- [ ] **O-1. Decide the "AI-generated functional instructions, such as craft patterns" question. This is a hard blocker.**
  - Sources: article 360024112614, edited 2026-10-22; Creativity Standards, to be read in person.
  - Do not resolve it by rewording the disclosure.
  - References: W-IMAGEPOLICY §2.3, §4.8, §6.2; ETSY_POLICY_READINGS_PACKET source 2, Q3.
- [ ] **O-2.** Read the Listing Image Requirements legal page (`…/listing-image-requirements/253962679005`). Source: W-IMAGEPOLICY §6.1.
- [ ] **O-3.** Check the listing form for a "made with AI" attribute. Source: W-IMAGEPOLICY §6.3.
- [ ] **O-4. Approve `tester_outreach` for market-basket-small@1.2.0.**
  - Cost: **CA$66.00** (fee plus two balls; ESTIMATED), or CA$59.65 with yarn reimbursed per metre.
  - Time: 25 minutes.
  - Also add the "re-weigh after the swatch" line (G2) before sending.
  - Consequence of waiting: no compliant listing is possible.
  - Source: W4-SAMPLE §1.8, §4, §5.
- [ ] **O-5. Record policy readings in person:**
  - `seller_policy`;
  - `creativity_standards`;
  - `listing_image_rules`;
  - **`children_and_baby`**, which is required here because the release is assigned under-3 nursery decor (Q1 and Q2: does it cover a nursery basket, and does it cover patterns?).

  Then review each `policy_changed` card. Sources: ETSY_POLICY_READINGS_PACKET sources 1, 2, 3 and 6; LAUNCH_PATH E5.
- [ ] **O-6.** Decide `who_made` together with O-1. Source: `seo.constraints.who_made_enum` note.
- [ ] **O-7.** Approve the listing fee, US$0.20 (about CA$0.28) per listing and per renewal. Source: template §11.
- [ ] **O-8.** Confirm the shop currency is CAD. Source: §5.
- [ ] **O-9.** Confirm that `digital_sale_message` is set (§6). Source: `intel.etsy_surfaces` (production readback).
- [ ] **O-10.** Acknowledge the §2.4 identity decision once the company makes it. Source: §2.4.
- [ ] **O-11.** Keep the automated publish path disarmed for `market-basket-small@1.2.0` while a manual listing exists. Source: §10.

### Physical

- [ ] **P-1.** A full make by an independent adult (not the owner, F-071) from `market-basket-small-1.2.0-TEST.pdf` (`a724cbae…`, content hash `1ddde587…`), scope `full_make`. Source: W4-SAMPLE §1.2.
- [ ] **P-2.** `POST /api/physical-test` with `passed=True`, bound to `1ddde587…`. This clears `gauge_and_size_claims` for this release only. Source: W4-SAMPLE §1.7, §3.1; LAUNCH_PATH E7.
- [ ] **P-3.** Measurements within ±12% of: across the points 16.0 cm, wall height 8.7 cm, across the flats 13.9 cm. Note that the code does not check the flats. Source: W4-SAMPLE §1.4.
- [ ] **P-4.** Photographs per §8, with #1 unedited, a rights basis, and the original's sha256 kept. Source: W-IMAGEPOLICY §4.3, §5.1.
- [ ] **P-5.** Any measured difference from the stated size is reconciled by Product Truth before publishing. Source: W-IMAGEPOLICY §5.

### Engineering / company

- [ ] **E-1.** Add a mixed-gallery disclosure to `DISCLOSURES`, and update the classifier and `check_ai_disclosure` to match. Fix `copy_v2` About ("We have not yet worked physical samples") and `brand.storefront` at the same time. Source: W-IMAGEPOLICY §4.5.
- [ ] **E-2.** Require a `PHYSICAL_PRODUCT_PHOTO` (unedited, with bytes, rights and release binding) before a pattern listing can publish. Source: W-IMAGEPOLICY §4.7, §7.
- [ ] **E-3. Category / search certificate: PENDING W-LAUNCHFIX E4.** Needs a production taxonomy readback, then the matcher. Source: W-LAUNCHFIX §4; LAUNCH_PATH E4.
- [ ] **E-4.** Build the manual-listing adoption path (§10).
- [ ] **E-5.** The W-LAUNCHFIX D1/D2/E3 fixes are unmerged and untested. Source: W-LAUNCHFIX header.
- [ ] **E-6. Identity conflict: "Bread Basket" against `nursery_decor` / `under_3`** in the title, tags and SAFETY block. The fix is (a) remove the children's assignment for this variant, or (b) retitle, release a new version and re-test. Either way, regenerate the copy. Sources: §2.4; `products.launch0.childrens_assignment`.
- [ ] **E-7.** The pricing reason "3 finished sizes from one chart" is attached to a single-size listing. The fix is to make the reason per release, or to sell the three-size candidate as one listing (which needs 3 samples; W4-SAMPLE §3.1). Source: §5.
- [ ] **E-8.** The supplement and CONTENTS alt text names "Nesting Baskets, three sizes" for the small-only listing (`visual.launch_imagery._primary_for`). Source: §8.
- [ ] **E-9.** The `terminology` attribute says "US terms" although the listing ships US and UK files. The "Fibre" line contradicts the yarn name "worsted cotton". Source: §2.1, §3.
- [ ] **E-10.** Reconcile the 140/13/20 evidence status between `seo.constraints` and `integrations.etsy_constraints`. `etsy_constraints` goes stale on 2026-11-05. Source: §1, §4.
- [ ] **E-11.** The tag "beginner crochet" sits on a "confident beginner" pattern. Confirm the `search.tag_truth` policy. Source: §4.
- [ ] **E-12.** The certified PDFs from W-PDF1 must equal production's `assets.built` hashes. Source: §6.

### Policy and evidence (independent verification)

- [ ] **V-1.** The release is certified in production at 1.2.0, with release hash `1ddde587…`. Source: LAUNCH_PATH E11.
- [ ] **V-2.** All nine first-customer areas PASS. Today `gauge_and_size_claims` is UNRESOLVED and `etsy_remote_state` is UNVERIFIABLE (chain-run release gates). Source: evidence JSON; LAUNCH_PATH A9.
- [ ] **V-3.** Independent vision review of the frames. Source: LAUNCH_PATH E6.
- [ ] **V-4.** The image rules are met: one unedited photo of the made result, placed first; renders labelled and never shown alone; a PDF preview included. Source: W-IMAGEPOLICY §1, §3.
- [ ] **V-5.** The children's listing is compliant under the owner's `children_and_baby` reading, or no longer a children's listing (E-6). Source: ETSY_POLICY_READINGS_PACKET source 6.
- [ ] **V-6.** Owner review of the first-customer evidence (`NEVER_AUTHORISES`). Source: LAUNCH_PATH A9.

## 10. Reconciliation note: matching a manual listing to Brambleloop's records

**Finding: there is no manual-listing adoption path. This is an engineering gap (E-4).**

The `hexagon-coaster-set-1.2.0` package §10 has the same grep in full. In summary:

**What exists today**
- **`ops/adoptions.py`** is the F-417 technology-cost adoption register. It has no listing concept.
- **Only `store.publish` writes `Listing.etsy_listing_id`.** The writes are `publish/draft_intent.checkpoint` and `runtime/pipeline.py:2110`. No API route, Command Center action or job binds a hand-made listing.

**What happens to a hand-made listing**
- **Census.** It opens a P2 incident, `etsy.unexpected_listing:<id>`. The listing is never adopted and never drift-checked. Without credentials the census reads NO_EVIDENCE.
- **Orders.** Sales are recorded as `"unmatched: no listing of ours carries this Etsy listing id"`, with product and version blank. Corrections and support cannot be tied to the version sold.
- **Stats export.** It matches by slug, Etsy id or the exact lower-cased title. A verbatim title would match, but only if the production `Listing` row exists (NEEDS PRODUCTION READBACK).

**Duplication risk.** Nothing records the manual listing. Once the gates clear, `store.publish` would create a second Etsy listing for `market-basket-small@1.2.0`. O-11 is the only guard until E-4 exists.

**Interim manual record.** The owner keeps this record at publication, in the operator's records rather than in this repo:

```
slug@version:            market-basket-small@1.2.0
release_hash:            1ddde587f537388b4a9dd5a74e9a0e0ebadc6ce0c0a79372dd6b867a230b3991
etsy_listing_id:         <from the listing URL>
published_at (UTC):      <ISO 8601>
state set:               draft | active
title / tags / price:    exactly §1 / §4 / §5 (note any deviation)
identity decision (§2.4):<a | b, and the regenerated copy's source>
category chosen:         <path, and id if shown>   (unverified until E4)
files uploaded:          <name, sha256> x2  (must equal production assets.built)
photos uploaded:         <rank, sha256, rights_basis, unedited yes/no>
renders uploaded:        <rank, sha256 from certified_images>
```

**What E-4 must build.** An owner-authorised `listing.adopt_manual` action, under step-up. It must:
1. read the listing back from Etsy;
2. verify every field, file hash and image hash against the certified payload, and refuse on any mismatch;
3. write `Listing.etsy_listing_id` and the state;
4. record a `DraftIntent` in state `CREATED` with `remote_id`, so `store.publish` can never create another;
5. audit `listing.adopted_manual`.
