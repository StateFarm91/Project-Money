# Manual Etsy listing package: `hexagon-coaster-set@1.2.0` (Hexagon Coaster Set)

**Status: NOT READY TO PUBLISH.** This is a preparation package for the owner, who would enter it by
hand in Etsy Shop Manager. Nothing here was published, and no request was made to Etsy or Railway.
§9 lists what must clear first. The hard blockers are a physical sample with its photographs, the
open owner decision on Etsy's "AI-generated functional instructions" rule, and the category
(PENDING: W-LAUNCHFIX E4).

- **Prepared by:** W-LISTING on `claude/w4-LISTING1`, cut from `origin/claude/w4-INTEG8-next` at `b0133916`, on 2026-10-27 (UTC).
- **How the copy, tags and price were produced.** The repo's own release chain ran for this release in a SHADOW worker:
  - `gate.certify` → `listing.draft` → `assets.build` → `pricing.position` → `listing.seo` → `launch.plan` → `store.publish`, which refused, as it should in SHADOW;
  - run through `research/final_build/w4/pipe_chain_run.py` on a scratch SQLite, at nice 19, with every socket closed, no credentials and no model call.
- **Evidence.** The stored `Listing` row, the job outputs and the gate reasons are in `../evidence_LISTING1_chain_run.json`.
- **Nothing below is hand-written** except where it is marked **[PACKAGE EDIT]**, and each edit says why.

**Release identity**

| | Value | Source |
|---|---|---|
| CIR slug @ version | `hexagon-coaster-set@1.2.0` (the latest in code: `products.launch0.cir_for("hexagon_coasters")`) | code |
| Candidate (product) | `hexagon-coaster-set`, "Hexagon Coaster Set (4)", one variant | `products.launch0` |
| Content / release hash | `3754ed17a63b790dc2c04b0f744de3fad34e5893ca69c0ff9f0c7cb41090937b` | chain run; it equals LAUNCH_PATH §3 and W4-SAMPLE §2.1 |
| Certified **in production** at this version? | **UNKNOWN: NEEDS PRODUCTION READBACK.** LISTREADY found 0 of 10 Launch-0 releases certified in production on 2026-10-20. | LAUNCH_PATH E11 |
| Product Truth | PASS (`passes_gates=True`). The title promise "set" is backed: the CIR makes 4. | `products.launch0.product_truth`, `title_promise` |
| Risk class | A (effective). The first customer still needs `partial_physical`, which in practice means a full make (W4-SAMPLE §0.2). | `gates.risk_matrix` |

---

## 1. Title

```
Hexagon Coaster Set | Crochet Pattern PDF | Written Instructions and Chart | US and UK Terms
```

**Checks**
- **Length:** 92 characters, within the 140-character limit:
  - `seo.constraints.title_max_chars` = 140, recorded UNVERIFIED (secondary summary);
  - `integrations.etsy_constraints.title_max_chars` = 140, recorded VERIFIED_HELP_CENTER (article 115015628707, read 2026-10-06).
  - The two modules disagree on the evidence status; see §9 E-10.
- **Word guidance:** 14 words, under the "less than 15 words" guidance (`title_words_advice`, recommended only).
- **Characters:**
  - `publish.listing_schema.title_problems(title)` returns `[]`;
  - every character is in the OpenAPI title charset (`seo.constraints.title_charset`). `|` is a math symbol (Sm);
  - none of `% : & +` is used.
- **Source:** `seo.build_title`, via `listing.seo`.

**[PACKAGE NOTE] "(4)" is not in the title.** The candidate's own name is "Hexagon Coaster Set (4)", and the alt texts say "(4)". Neither the system title nor the description tells the buyer how many coasters the pattern makes. See the description edit below and §9 E-6.

## 2. Description

### 2.1 The system's description (verbatim, from the stored `Listing.description`)

Two sentences in it are marked ⚠. They must be changed before publication, as set out in §2.2. Everything else is the system's text.

```
Hexagon Coaster Set — a crochet pattern, not a finished item. You receive an instant digital download. Why it is worth making: worked in 2 colours, written for a confident beginner maker, every row written out and charted, so you can follow whichever you prefer.
If you are searching for crochet home decor, diy coaster and home decor diy, this is the one: every row is written out and charted, and every stitch count is checked before release.

WHAT YOU GET
- Written instructions for every row, with a stitch count on each
- A chart drawn from the same pattern as the written instructions, so the two always agree
- Two PDFs, one in US terms and one in UK terms — the same pattern, each written throughout in its own terminology, with a stitch key to match
- 7-page PDF, laid out to be readable on a phone or printed

THE DETAILS
- Finished size: hexagon, 9.7 cm across the points, 8.4 cm across the flats, worked at the gauge below
- Difficulty: confident beginner
- Yarn: dk cotton
- Fibre: as named above; the pattern does not specify a composition, so choose any yarn of the same weight that meets the gauge
- Gauge: 14.5 sts x 16.0 rows = 10 cm in sc, 5 mm hook
- Stitches used: inc, sc
- Colours: 2 (cream, wine)
- cream: about 18-27 m
- wine: about 5-7 m
- Yarn quantities are estimates with a +/-20% range, not measurements. Yarn use varies with yarn, hook and tension.

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

### 2.2 Required edits before publication

**[PACKAGE EDIT 1] Replace the `disclosed_render` bullet.** It is `platform_policy.DISCLOSURES["disclosed_render"]`.
- **Why.** Etsy now requires at least one real, unedited photo of the made result on a pattern listing (W-IMAGEPOLICY §2.1, §2.2). Once that photo is in the gallery, the sentences "each listing image is a digital rendering … not a photograph" and "no sample has been photographed" are **false**. W-IMAGEPOLICY §4.5 says the same.
- **Replacement.** The system has no sentence written for a mixed gallery. The truthful replacement uses two existing `DISCLOSURES` sentences, verbatim, plus one factual sentence about the sample, to be completed only once the photo exists:

  ```
  - About the images: the first photo is an unedited photograph of a set of four coasters made from this exact pattern version. Some listing images are illustrations or renders rather than photographs, and are labelled where they appear.
  ```

  The second sentence is `DISCLOSURES["generated_imagery"]`, verbatim. "Charts and previews are rendered directly from the pattern file…" (`deterministic_render`) is already in the list and stays.
- **Rules for the photo sentence.**
  - **Do not publish it until the photo exists.**
  - If the photos show only one coaster, or anything other than all four, change the wording to match.
  - If any photo other than the required unedited one is edited with AI tools, add: "Some photos have been colour- or light-adjusted with editing tools." This is Etsy's best practice (W-IMAGEPOLICY §2.1). The recommendation is to make no AI edits at all.
- **This is a deviation from system output.** The system's own checker, `gates.policy.check_ai_disclosure`, owes `disclosed_render` verbatim whenever disclosed renders are in the set. It would flag this edited copy, so engineering must add a mixed-gallery disclosure (§9 E-1).

**[PACKAGE EDIT 2] State the count.** Add one line under "WHAT YOU GET":

```
- Makes a set of 4 coasters; the yarn amounts below are for all 4
```

Backed by:
- the CIR component `coaster` with `make: 4`;
- `cir.twin._yardage(..., comp.make)`, which multiplies yardage by `make` (W4-SAMPLE §2.3: 28.8 m for the set, about 7.2 m per coaster);
- Product Truth `title_promise` ("the CIR makes 4").

**Edits that are NOT made**
- **The AI disclosure is unchanged.** "This design was created with AI assistance…" is the system's truthful sentence (`DISCLOSURES["ai_assisted_design"]`). It appears twice: in "HOW THIS PATTERN WAS MADE" and in "DISCLOSURES". **Do not reword it to avoid Etsy's functional-instructions prohibition.** That question is an owner decision (§9 O-1; W-IMAGEPOLICY §4.8).
- **No claim is added that the pattern was tested or that a sample was measured.** That stays out until a `PhysicalTest` with `passed=True` is bound to `3754ed17…`. The finished size remains "worked at the gauge below", meaning computed.

### 2.3 Coverage of the required description elements

| Element | Where in the text | Backed by |
|---|---|---|
| What the buyer receives | "WHAT YOU GET": written rows, chart, **two PDFs (US and UK terms)**, 7 pages | `assets.build` pages=7, `TERMINOLOGIES` = (US, UK) |
| Skill level | "Difficulty: confident beginner" | `runtime.release._difficulty` |
| Finished size | 9.7 cm across the points, 8.4 cm across the flats, at the stated gauge | twin; `supported_claims` |
| Materials | dk cotton, 2 colours, yardage ±20% | CIR materials and twin |
| Gauge | 14.5 sts x 16.0 rows = 10 cm in sc, 5 mm hook | CIR gauge |
| Licence | "PATTERN USE AND SUPPORT" (from `commerce.terms`), marked "not yet been through legal review" | `commerce.terms.BRAMBLELOOP_TERMS` |
| AI disclosure | "HOW THIS PATTERN WAS MADE" and "DISCLOSURES" | `DISCLOSURES["ai_assisted_design"]` |
| Digital, nothing shipped | "This is a digital pattern. No physical item is shipped." and "You receive an instant digital download." | `DISCLOSURES["digital_download"]` |
| Delivery and support | instant download; questions through the shop; free corrections. The shop-level delivery message is in §6. | `commerce.terms`, `store_foundation.copy_v2` |

The system's disclosure check (`commerce.buyer_trust.listing_disclosure_finding`) read `complete: true, missing: [], misplaced: []` on the unedited text.

**Known copy defect (not edited here):**
- The "Fibre" line says the pattern "does not specify a composition", while the yarn is named "dk cotton".
- The CIR's `fibre_content` is empty, so the line is literally true, but it reads oddly.
- See §9 E-8.

## 3. Category and attributes

**Category: PENDING: W-LAUNCHFIX E4.**

What the repo holds:
- **The only committed Etsy taxonomy evidence** is `research/final_build/w4/evidence_FMBATCH1/prod_api_audit_taxonomy_refreshed_20261021T0242Z.json`:
  - a production `etsy.taxonomy_refreshed` row of 2026-10-21;
  - 3065 nodes;
  - `pattern_subtree: 0`, `properties_read: 0`;
  - **names only, and no ids**.
- **The candidate node by name** is `Craft Supplies & Tools > Patterns & How To > Patterns & Blueprints`. It has no children in that read.
- **"Crochet" appears only** as `Art & Collectibles > Fiber Arts > Crochet` (finished art, which is wrong for a pattern) and `… > Hooking > Crochet Hooks`. Neither may be used.
- **W-LAUNCHFIX §4 ("E4")** concludes the same. Crochet can only be confirmed as a **property value** of the Patterns & Blueprints node's schema.

**Exactly what is missing**
1. The **taxonomy_id** of `Patterns & Blueprints`.
2. That node's **property schema**, and whether it offers a "Crochet" value (craft type).
3. Production's newest `etsy.taxonomy_refreshed` row after `ee35a493`'s daily refresh, with `category_choices` and `property_candidates`. This needs a production readback that has not been made.

`integrations.etsy.ListingPayload.taxonomy_id` defaults to `TAXONOMY_PATTERNS`. The system itself reports that number as "taxonomy 66 was never verified" (`search_hero` reasons). **Do not use it.**

**For a manual listing** the owner would pick the category in Shop Manager's picker. The package does not tell the owner which node to pick, because no verified node exists. If the owner chooses one by sight, record the node path and any shown id in the reconciliation record (§10), and treat the category as owner-chosen and unverified until E4 closes.

**Attributes the system decided** (`search.listing_attributes` in the `listing.seo` output). These are facts of the pattern. They are **not** Etsy property ids, which are PENDING with the node:

| Attribute (system key) | Value | Use in Shop Manager |
|---|---|---|
| craft_type | crochet | the node's craft property, if it offers "Crochet" (PENDING E4) |
| pattern_type | coaster | PENDING E4 |
| skill_level | confident beginner | PENDING E4: map only to an offered value |
| primary_color / secondary_color | cream / wine | PENDING E4 (the colour property names of the node) |
| file_type | PDF | digital-file attribute, if offered |
| digital / instant_download | true / true | listing type "Digital" |
| includes_chart / includes_written_instructions | true / true | description only |
| terminology | US terms | **System defect:** the listing ships US **and** UK PDFs; the attribute names only US. Description only. See §9 E-9. |
| occasion | none | leave blank |

**Fixed listing fields** (`integrations.etsy.ListingPayload` defaults; enums VERIFIED from the OpenAPI document, 2026-10-06):

| Field | Value |
|---|---|
| type | download (digital) |
| who_made | `i_did`. `seo.constraints.who_made_enum` notes that "which value is truthful for a Brambleloop pattern is a disclosure decision". It is tied to O-1. |
| when_made | `made_to_order` |
| is_supply | true (a pattern is a supply or tool to make things) |
| quantity | 999 (`DIGITAL_QUANTITY`) |
| materials | `dk cotton`. `build_payload` de-duplicates it; `listing.seo` emitted it twice, one per colour. |
| renewal | **manual**. The system never sends `should_auto_renew=true` (W-LAUNCHFIX §1), and renewal follows `release_gates.renewal_decision`. |

## 4. Tags (exactly the system's SEO output)

```
coaster crochet, written and chart, crochet home decor, hexagon crochet, hexagon coaster, diy coaster, digital download, home decor diy, instant download pdf, yarn craft project, us and uk terms, printable pdf chart, fiber art project
```

| # | Tag | Chars |
|---|---|---|
| 1 | coaster crochet | 15 |
| 2 | written and chart | 17 |
| 3 | crochet home decor | 18 |
| 4 | hexagon crochet | 15 |
| 5 | hexagon coaster | 15 |
| 6 | diy coaster | 11 |
| 7 | digital download | 16 |
| 8 | home decor diy | 14 |
| 9 | instant download pdf | 20 |
| 10 | yarn craft project | 18 |
| 11 | us and uk terms | 15 |
| 12 | printable pdf chart | 19 |
| 13 | fiber art project | 17 |

**Rule checks**
- **Count:** 13 of 13 maximum.
- **Length:** every tag is ≤ 20 characters (longest: 20).
- **Leading symbol:** none starts with `'` or `-`.
- **Charset:** letters, digits and spaces only.
- **System check:** `publish.listing_schema.tag_problems(tags)` returns `[]`.

**Sources**
- The limits: `integrations.etsy_constraints` `tags_max` 13, `tag_max_chars` 20 and `tag_no_leading_punct`, all VERIFIED_HELP_CENTER from article 360000336307 (2026-10-06). `seo.constraints` records the same values as UNVERIFIED.
- The tag basis is `modelled` (assumed query-model phrases). **No Etsy search volume is measured for any tag** (`search_coverage.evidence_share: UNMEASURED`).

**Production's tags may differ.**
- `listing.seo` diversifies tags against every other stored listing (#240, `_diversify_tags`).
- This scratch run had no other listing when the coaster was drafted (`query_portfolio`: "no other listing's tags to diverge from").
- **If production's stored `Listing.tags` / title / description for this release can be read back, they take precedence.** They are the system's output for the real catalogue.

## 5. Price

| | Value |
|---|---|
| **Price** | **CA$4.00** |
| Plan band | CA$4.00 – 12.00, basis **SOURCED** ("the CA$4-12 cluster from radar/market.py OBSERVATIONS, at its floor") |
| Proposal / decision | CA$4.00, `held_at_proposal: true`. "decided by commerce.pricing" (`products.launch0.price_plan`); `within_plan_band: true`, `launch_price_check` not DRIFT |
| Rationale (system's words) | "this listing earns its place through reviews and cross-sell rather than margin" |
| Modelled fees (`commerce.pricing.fees(4.0)`) | transaction CA$0.26 + payment processing CA$0.37 + amortised listing fee CA$0.028 → **net CA$3.34**, take rate 16.4% |
| Not modelled (system warning) | Offsite Ads, the regulatory operating fee and currency conversion. "if all three apply at their reported rates the take rate is 35.1% and the net is CA$2.60. Those rates are SECONDARY -- etsy.com/legal/fees is 403 to automated readers" |
| Listing fee | US$0.20 per listing (about CA$0.28) on activation and each renewal. This is the owner's `listing_fees` decision (template §11). |
| **Shop currency** | **UNKNOWN in the repo.** The price is in CAD. If Shop Manager's shop currency is not CAD, the owner must not enter "4.00"; this package gives no conversion. |

## 6. Digital download details

| | US terms | UK terms |
|---|---|---|
| File name (system convention: `f"{slug}-{pattern_filename(t)}"`, `runtime/pipeline.py`) | `hexagon-coaster-set-pattern-us.pdf` (34 chars) | `hexagon-coaster-set-pattern-uk.pdf` (34 chars) |
| Format | PDF (`application/pdf`) | PDF |
| Pages | 7 | 7 |
| Size (scratch run) | 60,876 bytes | 60,885 bytes |
| sha256 (scratch run, **not** the certified file) | `d8014e46…9d50` | `ce613061…473b` |

**Etsy limits** (`integrations.etsy_constraints`, VERIFIED_HELP_CENTER, article 115015628347):
- at most 5 files;
- at most 20 MB each;
- names at most 70 characters (letters, digits, periods, underscores, hyphens), and a name **cannot be edited after upload**.

Both files are within these limits.

**The files to upload** are the certified PDFs for this exact release, produced by **W-PDF on `claude/w4-PDF1`**. That branch was **not on origin** when this package was written.
- Each uploaded file's sha256 must equal production's `assets.built` `pdf_sha256_by_terminology` for `hexagon-coaster-set@1.2.0`. That is the check `runtime.pipeline.check_pdf_hashes` makes on the automated path.
- The bytes above come from a scratch render whose `released_on` date differs, so they will not match. They are given only for size and page count.
- Each PDF also carries `publish.pdf.AI_DISCLOSURE` ("How this pattern was made: this design was created with AI assistance…").

**Delivery message.** Shop level, so it is set once for the shop rather than per listing. It is `store_foundation.copy_v2.DIGITAL_SALE_MESSAGE`:

```
Thank you, and happy making. Your pattern is ready now: open your Etsy account, go to Purchases and downloads, and both PDFs (US and UK terms) are there. Etsy has emailed you a link as well.

Two things worth knowing. Under our pattern terms, finished items may be sold by individual makers and small businesses, not manufactured at scale. And if anything in the pattern does not add up, reply to this message with the pattern name and the row number: we correct the pattern itself and send you the corrected file.
```

Whether it is already set on the live shop is NEEDS PRODUCTION READBACK (`etsy_surfaces` `digital_sale_message_set`). It must be set before the first sale.

## 7. Disclosures: every one, and where each goes

| Disclosure | Exact text (source) | Where |
|---|---|---|
| AI-assisted design | `DISCLOSURES["ai_assisted_design"]` | Listing **description**, required by Etsy: "Sellers must disclose within their listing description if an item is created with the use of AI" (article 360024112614, edited 2026-10-22). Already present twice. Also in each PDF as `publish.pdf.AI_DISCLOSURE`. |
| Digital, nothing shipped | `DISCLOSURES["digital_download"]` | Description (present). The listing type is set to Digital. |
| Image disclosure | **[PACKAGE EDIT 1]** text in §2.2, replacing `disclosed_render` | Description |
| Renders are renders | in-pixel caption "Digital rendering of the pattern's finished design, not a photograph" (`disclosed_listing.DISCLOSURE`) and each render's alt text (§8) | On every render, and in its alt text |
| PDF preview | in-pixel label and alt text "Preview of the pattern document" (`eligibility.PREVIEW_LABEL`) | The CONTENTS frame |
| Charts / previews are deterministic | `DISCLOSURES["deterministic_render"]` | Description (present) |
| AI photo edits, if any | "Some photos have been colour- or light-adjusted with editing tools." (package wording, Etsy best practice) | Description, **only if** an edit was made. The required photo is never edited. |
| Licence not legally reviewed | "These are the terms Brambleloop offers; they have not yet been through legal review." | Description (present) |
| A "made with AI" listing attribute | **UNKNOWN.** No Help article read names one. | The owner checks the listing form in person (W-IMAGEPOLICY §6.3) |

## 8. Premium listing-gallery brief

**Etsy specifications**, from `integrations.etsy_constraints` (2026-10-06), re-read 2026-10-22/27 by W-IMAGEPOLICY:
- **Count:** up to 20 photos.
- **Size:** at least 2000 px on each side recommended; the first image at least 635 px.
- **First image:** landscape or square.
- **Thumbnail:** the first image must crop cleanly to square, portrait and landscape thumbnails. The exact crop ratios are UNKNOWN, so keep a generous border.
- **Format:** jpg, png, gif, svg or heic. No transparency or animation. Images are converted to sRGB.
- **Upload size:** images over 1 MB "may not finish uploading" (browser advice).
- **Alt text:** at most 500 characters (API); Etsy advises up to 250.

**Photos.** Each one **requires a physical sample, which has not yet been made.** The sample is all four coasters, made by an independent tester from the exact release PDF (`3754ed17…`), under W4-SAMPLE package B. Rights basis: `tester_agreement` or `brambleloop_made` (`physical_upgrade.RIGHTS_BASES`). Intake by sha256 through `POST /api/physical-photo`.

| # | Shot | Edit rule | Aspect / size | Label on image | Alt text (≤ 250 chars; finalise to what the photo shows) |
|---|---|---|---|---|---|
| **1 (FIRST)** | **All four coasters** in a 2 × 2 group or slightly fanned, flat on a real table, three-quarter angle, generous margin on every side | **UNEDITED.** No filter, crop, resize or background change. Shoot in final framing. Keep the original file and its sha256. | **Landscape 4:3 or square 1:1, ≥ 2000 px on each side** (JPG straight from the camera) | none | "Photograph of four crocheted hexagon coasters in cream with a wine round near the edge, made from this pattern, lying flat on a wooden table." |
| 2 | Flatness: a low side angle at table level showing one coaster lying flat, not pressed down | may adjust exposure (not AI) | square 1:1, ≥ 2000 px | none | "Photograph at table level showing a crocheted hexagon coaster lying flat." |
| 3 | Scale: a ruler across the points of one coaster (about 9.7 cm) | may crop | square 1:1, ≥ 2000 px | none | "Photograph of a crocheted hexagon coaster with a ruler across its points, measuring about [measured] cm." Use the **measured** value. |
| 4 | Detail: one corner, showing the stacked increases and the contrast round | may crop | square 1:1, ≥ 2000 px | none | "Close-up photograph of a crocheted hexagon coaster corner showing stacked single-crochet increases and the wine contrast round." |
| 5 | In use: a mug on one coaster, the others stacked beside it, mostly visible | may adjust (not AI) | landscape 4:3 or square, ≥ 2000 px | none | "Photograph of a mug on a crocheted hexagon coaster, with three more coasters stacked beside it." |

**Measurement rule.** If the measured size differs from 9.7 × 8.4 cm, Product Truth must reconcile the copy before publishing. Never retake the photo to hide the difference (W-IMAGEPOLICY §5).

**Renders, charts and the PDF preview**, from the system's certified listing set:
- the disclosed set comes from `visual.disclosed_render.listing_set`;
- the supplements from `gallery_frames.applicable_jobs` (MATERIALS, COLOUR_CONTEXT, CONSTRUCTION) plus CONTENTS;
- the system refuses an angle view for a flat piece ("an angle view would repeat it");
- every render is a 2000 × 2000 PNG with no transparency and is already labelled in pixels.

| # | Frame (system role) | Label (in pixels) | Size | Alt text (system, verbatim) |
|---|---|---|---|---|
| 6 | Disclosed render, hero view (all 4 from above) | "Digital rendering of the pattern's finished design, not a photograph" + cm scale | 2000 × 2000 | "Digital rendering of the pattern's finished design, not a photograph. Hexagon Coaster Set: all 4 pieces seen from above, in cream and wine. About 9.7 x 8.4 cm at the stated gauge, with a centimetre scale bar." |
| 7 | Disclosed render, scale view | same | 2000 × 2000 | "Digital rendering of the pattern's finished design, not a photograph. Hexagon Coaster Set: the finished piece with its size marked, in cream and wine. About 9.7 x 8.4 cm at the stated gauge, with a centimetre scale bar." |
| 8 | Disclosed render, detail view | same | 2000 × 2000 | "Digital rendering of the pattern's finished design, not a photograph. Hexagon Coaster Set: a close view of the rounds, stitch for stitch, in cream and wine. About 9.7 x 8.4 cm at the stated gauge, with a centimetre scale bar." |
| 9 | Supplement CONSTRUCTION | as above | 2000 × 2000 | "Digital rendering of the pattern's finished design, not a photograph. Hexagon Coaster Set (4): how it is built: the stitch count of every round or row, in working order." |
| 10 | Supplement COLOUR_CONTEXT | as above | 2000 × 2000 | "Digital rendering of the pattern's finished design, not a photograph. Hexagon Coaster Set (4): each yarn colour's share of the finished piece, counted from the pattern." |
| 11 | Supplement MATERIALS | as above | 2000 × 2000 | "Digital rendering of the pattern's finished design, not a photograph. Hexagon Coaster Set (4): the yarn colours, yarn weight, hook size and gauge the pattern calls for." |
| 12 | **CONTENTS, the PDF page preview** (Etsy's digital-download "preview of the actual content") | "Preview of the pattern document" | 2000 × 2000 | "Preview of the pattern document. Hexagon Coaster Set (4): the first pages of the PDF pattern you download, shown at reduced size." |

**Where the image bytes come from**
- **Renders:** the exact bytes certified for this release (`runtime.etsy_ops.certified_images`, in listing-set-certificate order). Do not re-export or recompress them.
- **The CONTENTS preview:** render it from the **certified** PDF, the W-PDF1 file, not the scratch one.
- **Independent vision review** (#61; LAUNCH_PATH E6) of these frames is UNKNOWN until the approved CA$7.07 vision batch is activated.

**Order rule.** Photos 1 to 5 first, with the unedited photo at #1; then the renders; the PDF preview last. Renders must never be the only images of the finished result, and must never be first.

## 9. Outstanding publication requirements (checklist)

Status as of 2026-10-27. **Every box is open.**

### Owner

- [ ] **O-1. Decide the "AI-generated functional instructions, such as craft patterns" question. This is a hard blocker.**
  - The rule is in "What Can I Sell on Etsy?" (article 360024112614, edited 2026-10-22), and in Creativity Standards (`etsy.com/legal/handmade`), which must be read in person.
  - Brambleloop's instructions are compiled and validated by deterministic code, and the copy truthfully says "created with AI assistance".
  - **Do not resolve this by rewording the disclosure.**
  - Sources: W-IMAGEPOLICY §2.3, §4.8, §6.2; ETSY_POLICY_READINGS_PACKET source 2, Q3.
- [ ] **O-2.** Read the Listing Image Requirements legal page in a browser: `https://www.etsy.com/legal/policy/listing-image-requirements/253962679005`. Check its exceptions and its wording on renders. Source: W-IMAGEPOLICY §6.1.
- [ ] **O-3.** Check the Shop Manager listing form for a "made with AI" (or similar) attribute, and fill it truthfully if it exists. Source: W-IMAGEPOLICY §6.3.
- [ ] **O-4. Approve the sample make.**
  - Coaster call `tester_kit/OUTREACH_hexagon-coaster-set.md`, about **CA$100.00** (ESTIMATED; code ceiling CA$92.03), 25 minutes. W4-SAMPLE recommends the basket first.
  - Consequence of waiting: no compliant listing is possible.
  - Sources: W4-SAMPLE §2.8, §5; W-IMAGEPOLICY §6.4.
- [ ] **O-5.** Record the policy readings in person (`seller_policy`, `creativity_standards`, `listing_image_rules`), then review each `policy_changed` card. Sources: ETSY_POLICY_READINGS_PACKET; LAUNCH_PATH E5.
- [ ] **O-6.** Decide `who_made` (`i_did`) for an AI-assisted pattern, together with O-1. Source: `seo.constraints.who_made_enum` note.
- [ ] **O-7.** Approve the listing fee: US$0.20 (about CA$0.28) per listing and per renewal. Source: PUBLICATION_APPROVAL_PACKAGE_TEMPLATE §11.
- [ ] **O-8.** Confirm the shop currency is CAD (Shop Manager > Settings > Options), or say so if it is not. Source: §5 above.
- [ ] **O-9.** Confirm that `digital_sale_message` is set to the §6 text. Source: `intel.etsy_surfaces` `messages` / `digital_sale_message_set` (NEEDS PRODUCTION READBACK).
- [ ] **O-10.** Pick the category manually only once E4 names a node; record the choice (§10). Source: §3.
- [ ] **O-11.** Leave the automated publish path disarmed for this product while a manual listing exists: `BRAMBLELOOP_PUBLISH_AUTHORISED≠1`, and no `publication.approve` grant for `hexagon-coaster-set@1.2.0`. Otherwise `store.publish` creates a duplicate (§10). Source: §10.

### Physical

- [ ] **P-1.** An independent tester makes **all four** coasters from `hexagon-coaster-set-1.2.0-TEST.pdf` (hash `3754ed17…`), with scope `full_make`. A swatch or partial set is rejected or mis-calibrates. Source: W4-SAMPLE §0.2, §2.2, §3.3.
- [ ] **P-2.** The result is recorded through `POST /api/physical-test` with `passed=True`, bound to `3754ed17…`. This clears first-customer `gauge_and_size_claims`. Source: W4-SAMPLE §2.7; LAUNCH_PATH A9, E7.
- [ ] **P-3.** All four lie flat. The code cannot see cupping, so the owner must hold the listing if any coaster cups. Source: W4-SAMPLE §2.7, G3.
- [ ] **P-4.** Photographs per §8, with #1 unedited. Intake through `POST /api/physical-photo` with a rights basis, and the original's sha256 kept. Source: W-IMAGEPOLICY §4.3, §5.2.
- [ ] **P-5.** Measure unstretched. Any difference from 9.7 / 8.4 cm is reconciled by Product Truth before publishing. Source: W-IMAGEPOLICY §5.

### Engineering

- [ ] **E-1.** `DISCLOSURES["disclosed_render"]` becomes false once a photo exists. Needed:
  - a mixed-gallery disclosure in `platform_policy.DISCLOSURES`, plus classification and `check_ai_disclosure` support;
  - the same fix in `brand.storefront` and the About copy in `store_foundation.copy_v2`, which says "We have not yet worked physical samples".

  Source: W-IMAGEPOLICY §4.5; §2.2 above.
- [ ] **E-2.** A pattern listing set must require one `PHYSICAL_PRODUCT_PHOTO`: unedited attestation, bytes on file, rights basis and release binding. Today it is optional (`physical_upgrade`). Source: W-IMAGEPOLICY §4.7, §7.
- [ ] **E-3. Category / search certificate. PENDING: W-LAUNCHFIX E4.**
  - Needs a production readback of the newest `etsy.taxonomy_refreshed`;
  - then `verify_w4_firstsale_taxonomy_live.py`.

  Source: W-LAUNCHFIX §4; LAUNCH_PATH E4.
- [ ] **E-4. Manual-listing adoption path.** It does not exist. See §10. Source: this package.
- [ ] **E-5.** D1/D2/E3 fixes are on `claude/w4-LAUNCHFIX`. They are **unmerged, and their tests were not run**. They matter for the automated path and for "independently verified" evidence. Source: W-LAUNCHFIX header; LAUNCH_PATH E1/E2/E3.
- [ ] **E-6.** The system title and description never state the count "4". [PACKAGE EDIT 2] works around this. The fix belongs in `seo.build_title` / `build_description`, so that the set count is printed when `make > 1`. Source: §1, §2.2.
- [ ] **E-7.** The certified PDFs from W-PDF1 (`claude/w4-PDF1`, not on origin at writing) must be byte-identical to production's `assets.built` for this release. Source: §6.
- [ ] **E-8.** The "Fibre" line contradicts the yarn name "dk cotton". The CIR `fibre_content` is empty. Source: §2.3; W4-SAMPLE §2.3.
- [ ] **E-9.** The `terminology` attribute says "US terms" on a listing that ships US and UK PDFs. Source: §3.
- [ ] **E-10.** `seo.constraints` labels 140/13/20 UNVERIFIED, while `integrations.etsy_constraints` labels them VERIFIED_HELP_CENTER. The record needs reconciling. Source: §1, §4.
- [ ] **E-11.** `integrations.etsy_constraints` was read 2026-10-06 with `MAX_AGE_DAYS` 30, so it goes **stale on 2026-11-05**. Re-read it before publishing after that date. Source: `etsy_constraints.is_stale`.

### Policy and evidence (independent verification)

- [ ] **V-1.** The release is certified **in production** at `1.2.0` with release hash `3754ed17…`. Source: LAUNCH_PATH E11 (NEEDS PRODUCTION READBACK).
- [ ] **V-2.** First-customer nine areas all PASS. Today `gauge_and_size_claims` is UNRESOLVED and `etsy_remote_state` is UNVERIFIABLE (the chain run's `store.release_gates` reasons). Source: evidence JSON; LAUNCH_PATH A9.
- [ ] **V-3.** The independent vision review of the frames (#61). It needs the approved CA$7.07 batch activated. Source: LAUNCH_PATH E6.
- [ ] **V-4.** The image rules are satisfied: one unedited photo of the made result, first; renders labelled and never alone; a PDF preview included. Source: W-IMAGEPOLICY §1, §3.
- [ ] **V-5.** Owner review of the first-customer evidence. `first_customer.NEVER_AUTHORISES`: PASS is "evidence for an owner review, not a substitute". Source: LAUNCH_PATH A9.

## 10. Reconciliation note: matching a manual listing to Brambleloop's records

**Finding: no manual-listing adoption path exists. This is an engineering gap (E-4).**

What was grepped (`src/brambleloop`, this branch):

1. **`ops/adoptions.py` is unrelated.** It is the F-417 register of *technology* adoptions: packages, services and hosting, with their running cost. It has no listing concept.
2. **Exactly two code paths write `Listing.etsy_listing_id`.** Both are inside the automated `store.publish`:
   - `publish/draft_intent.checkpoint` (line 83), under a `DraftIntent` this process claimed;
   - `runtime/pipeline.py:2110`.

   No API route, Command Center action or job binds an Etsy listing id that someone created by hand. `app/` only reads the field (`verify_checks`, `command_center/readers`, `executive`).
3. **Daily census (`runtime/etsy_ops.handle_listing_census`)**:
   - `_expected_listings` knows only `Listing` rows with an `etsy_listing_id`, plus exercise drafts;
   - a hand-made listing therefore surfaces as a **P2 incident `etsy.unexpected_listing:<id>`** ("A listing nobody here created is reported");
   - it is never adopted, and its fields are never compared with the certified payload (`_field_drift` returns `[]` without a slug);
   - with no Etsy credentials, the census reads NO_EVIDENCE.
4. **Orders (`commerce/orders_ingest.version_at`)**:
   - a sale on the manual listing is recorded with `"basis": "unmatched: no listing of ours carries this Etsy listing id"`;
   - it appears in `unmatched_listings`, with product and version blank;
   - so revenue, the support version and correction notices cannot be tied to `hexagon-coaster-set@1.2.0`.
5. **Stats export (`commerce/listing_outcomes._listing_index`)** matches by slug, by Etsy id or by **exact lower-cased title**. A manual listing whose title is exactly the stored `Listing.title` would match by title, if that row exists in production. That is NEEDS PRODUCTION READBACK, and any title edit breaks the match.
6. **Duplication risk.**
   - `store.publish` refuses only when a `Listing` row already has an `etsy_listing_id`, or a `DraftIntent` already exists for `(slug, version)`.
   - A manual listing sets neither.
   - So once the gates clear, the automated path would create a **second** Etsy listing for the same release.
   - Until E-4 is built, O-11 (keep the publish path disarmed for this release) is the only guard.

**Interim manual record.** The owner fills this in at the moment of publication. It goes in the operator's records, not in this repo, because it is production data:

```
slug@version:            hexagon-coaster-set@1.2.0
release_hash:            3754ed17a63b790dc2c04b0f744de3fad34e5893ca69c0ff9f0c7cb41090937b
etsy_listing_id:         <from the listing URL>
published_at (UTC):      <ISO 8601>
state set:               draft | active
title / tags / price:    exactly §1 / §4 / §5 (note any deviation)
category chosen:         <path, and id if shown>   (unverified until E4)
files uploaded:          <name, sha256> x2  (must equal production assets.built)
photos uploaded:         <rank, sha256, rights_basis, unedited yes/no>
renders uploaded:        <rank, sha256 from certified_images>
```

**What engineering must build (E-4).** An owner-authorised `listing.adopt_manual` action, step-up in `#/approvals`. It must:
- read the listing back from Etsy (getListing, files and images);
- verify title, description, tags, price, file hashes and image hashes against the certified payload for `slug@version`, and refuse on any mismatch;
- write `Listing.etsy_listing_id` and the matching state;
- record a `DraftIntent` in state `CREATED` with `remote_id`, so `store.publish` can never create another;
- audit `listing.adopted_manual`.

After that, the census compares drift, orders match, and the stats join works, all without duplication.
