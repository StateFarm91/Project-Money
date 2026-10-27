# Manual Etsy listing package: `market-basket-small@1.2.0` (Hexagonal Bread Basket, kitchen and home)

**Status: NOT READY TO PUBLISH.** This is a preparation package for the owner to enter by hand in
Etsy Shop Manager. Nothing was published, and no request was made to Etsy or Railway.

§9 lists what must clear first. The hard blockers are:
- a physical sample and its photographs;
- the open owner decision on Etsy's "AI-generated functional instructions" rule;
- the category (PENDING: W-LAUNCHFIX E4).

**Owner decision applied: D-W4-OWNER-BASKET-IDENTITY (2026-10-27).** Quoted exactly:

> "I approve positioning the Hexagonal Bread Basket 1.2.0 as a kitchen and home product. The first listing sells the small basket only. Remove inaccurate nursery, baby-product and three-size nesting-basket claims from its listing package and customer PDF. Preserve the existing larger basket family for separately verified future releases. Keep the proposed CA$6.50 price pending final pricing verification."

**The fix is at the source, not in this package.**
- `products.launch0` now sells this CIR as the Launch-0 product `hexagonal-bread-basket`: one size, with no children's sub-category.
- The three-size `nursery-nesting-baskets` family is kept unchanged as a reserve candidate.
- The release chain was re-run, so the title, tags, description and customer PDF below are the system's regenerated output.
- The superseded nursery version of this package is in git history (commit `5bf9aaf3`).

**How this package was made**
- **Prepared by:** W-LISTING on `claude/w4-LISTING1`, on 2026-10-27 (UTC).
- **Copy, tags and price:** from the repo's real release chain, run in a SHADOW worker. The jobs were:
  - `gate.certify` → `listing.draft` → `assets.build` → `pricing.position` → `listing.seo` → `launch.plan` → `store.publish`;
  - `store.publish` refused, as expected in SHADOW.
- **How it was run:** `research/final_build/w4/pipe_chain_run.py` on a scratch SQLite at nice 19, with sockets closed, no credentials and no model call.
- **Evidence:** `../evidence_LISTING1_basket_after_identity_fix.json`. The pre-decision run is `../evidence_LISTING1_chain_run.json`.
- **Hand-written text:** only where marked **[PACKAGE EDIT]**.

**Release identity**

| | Value | Source |
|---|---|---|
| CIR slug @ version | `market-basket-small@1.2.0`. CIR title "Crochet Hexagonal Bread Basket". Builder and instructions unchanged. | `products.launch0.cir_for("basket_small")` |
| Product (candidate) | `hexagonal-bread-basket`, "Hexagonal Bread Basket", one variant | `products.launch0`, D-W4-OWNER-BASKET-IDENTITY |
| Content / release hash | `1ddde587f537388b4a9dd5a74e9a0e0ebadc6ce0c0a79372dd6b867a230b3991`. **Unchanged** by the identity fix. | Re-run chain. Equals LAUNCH_PATH §3, W4-SAMPLE §1.1 and the tester kit. |
| Certified **in production** at this version? | **UNKNOWN: NEEDS PRODUCTION READBACK.** Production still runs the code that merchandised this CIR as nursery decor, so its stored listing and PDF carry the old framing until this change deploys and the release re-renders. | LAUNCH_PATH E11 |
| Product Truth | PASS (`passes_gates=True`) | `products.launch0.product_truth(candidate("hexagonal-bread-basket"))` |
| Risk class | B (`dimensional_form`). The first customer needs `partial_physical`, which in practice is a full make. | `gates.risk_matrix`; W4-SAMPLE §1.1 |
| Children's decision | **`not_for_children`** ("the candidate declares no children's sub-category"). Previously `('nursery_decor', 'under_3')`. | `products.launch0.childrens_decision("market-basket-small")` |

---

## 1. Title

```
Hexagonal Bread Basket | Crochet Pattern PDF | Written Instructions and Chart | US and UK Terms
```

**Checks**
- **Length:** 95 characters, within the 140 limit.
  - `seo.constraints` records the 140 limit as UNVERIFIED.
  - `integrations.etsy_constraints` records it as VERIFIED_HELP_CENTER (article 115015628707, 2026-10-06).
  - The two records disagree; see E-10.
- **Words:** 14, under the "less than 15 words" guidance.
- **Charset:** `publish.listing_schema.title_problems(title)` returns `[]`. The title uses only the OpenAPI charset and none of `% : & +`.
- **Source:** `seo.build_title` via `listing.seo`.
- **"Nursery" is gone.** The new candidate's `ListingIdentity` has no qualifier.

## 2. Description

### 2.1 The system's description (verbatim, regenerated after the owner decision)

The sentence marked ⚠ must change before publication (§2.2).

```
Crochet Hexagonal Bread Basket — a crochet pattern, not a finished item. You receive an instant digital download. Why it is worth making: worked in 2 colours, written for a confident beginner maker, every row written out and charted, so you can follow whichever you prefer.
If you are searching for crochet home decor, diy basket and home decor diy, this is the one: every row is written out and charted, and every stitch count is checked before release.

WHAT YOU GET
- Written instructions for every row, with a stitch count on each
- A chart drawn from the same pattern as the written instructions, so the two always agree
- Two PDFs, one in US terms and one in UK terms — the same pattern, each written throughout in its own terminology, with a stitch key to match
- 7-page PDF, laid out to be readable on a phone or printed

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

**What the regeneration removed (verified in the text):**
- the SAFETY AND SUITABILITY block, which said the item was "intended for children under 3 years" and covered sleep spaces and CPSIA;
- every nursery, baby and child word;
- any three-size or nesting claim.

The PDF went from 9 pages to 7 for the same reason (§6).

### 2.2 Required edit before publication

**[PACKAGE EDIT 1] Replace the `disclosed_render` bullet.**

Etsy requires at least one real, unedited photo of the made result (W-IMAGEPOLICY §2.1 and §2.2). Once that photo exists, "each listing image is a digital rendering … not a photograph" and "no sample has been photographed" become false.

Replace the bullet with this. The second sentence is `DISCLOSURES["generated_imagery"]`, verbatim. Complete the bullet only after the photo exists:

```
- About the images: the first photo is an unedited photograph of a basket made from this exact pattern version. Some listing images are illustrations or renders rather than photographs, and are labelled where they appear.
```

If a non-required photo is edited with AI tools, add: "Some photos have been colour- or light-adjusted with editing tools." The recommendation is to make no AI edits at all.

The system's `gates.policy.check_ai_disclosure` would flag this edited copy until a disclosure for mixed photo-and-render galleries is added (E-1).

**Not edited.**
- **The AI disclosure.** `DISCLOSURES["ai_assisted_design"]` stays verbatim. Do not reword it to get around Etsy's functional-instructions rule (O-1).
- **Testing claims.** Add no "tested" or "measured" claim until a passed `PhysicalTest` is bound to `1ddde587…`.

### 2.3 Coverage of the required description elements

| Element | Where | Backed by |
|---|---|---|
| What the buyer receives | "WHAT YOU GET": written rows, chart, **two PDFs (US and UK terms)**, 7 pages | `assets.build` pages=7; `TERMINOLOGIES` |
| Skill level | "Difficulty: confident beginner" | `runtime.release._difficulty` |
| Finished size | base 16.0 × 13.9 cm (points × flats); 8.7 cm tall, at gauge | twin; `supported_claims` |
| Materials | worsted cotton, 2 colours, yardage ±20% | CIR and twin |
| Gauge | 12.5 sts x 13.8 rows = 10 cm in sc, 5 mm hook | CIR |
| Licence | "PATTERN USE AND SUPPORT"; "not yet been through legal review" | `commerce.terms` |
| AI disclosure | "HOW THIS PATTERN WAS MADE" and "DISCLOSURES" | `DISCLOSURES["ai_assisted_design"]` |
| Digital, nothing shipped | "This is a digital pattern. No physical item is shipped." | `DISCLOSURES["digital_download"]` |
| Delivery and support | instant download; questions through the shop; free corrections; shop message in §6 | `commerce.terms`, `copy_v2` |

The system's disclosure check (`listing_disclosure_finding`) reads `complete: true, missing: [], misplaced: []`.

### 2.4 Product identity: RESOLVED by D-W4-OWNER-BASKET-IDENTITY

Before the decision, the system contradicted itself:
- the title, tags and a safety block sold a "Bread Basket" as nursery decor for children under 3;
- the price reason and alt text described three nesting sizes.

The owner chose the kitchen and home framing, sold in one size. The fix is in source; the code changes are listed in DECISION_LOG.

**Children and Baby policy (`children_and_baby`):**
- It **no longer applies to this listing**:
  - the product is `not_for_children`;
  - its title, tags, description and PDF contain no child-audience word;
  - it no longer carries children's statements.
- It **still applies to the shop**, through `cloudline-baby-blanket` and `nordic-forest-mosaic-throw-baby`, which are still Launch-0.
- It still applies to the reserve nursery family (medium and large) if those are released later.

## 3. Category and attributes

**Category: PENDING: W-LAUNCHFIX E4.**

**What the repo has.** The only committed Etsy taxonomy evidence is `research/final_build/w4/evidence_FMBATCH1/prod_api_audit_taxonomy_refreshed_20261021T0242Z.json`:
- 3065 nodes, by name only, with no ids;
- `pattern_subtree: 0`.

**Candidate node by name.** `Craft Supplies & Tools > Patterns & How To > Patterns & Blueprints`, which has no children.

**Never use** `Art & Collectibles > Fiber Arts > Crochet` or `… > Crochet Hooks`.

**Missing:**
1. the taxonomy_id of Patterns & Blueprints;
2. that node's property schema, including whether "Crochet" is a value;
3. production's newest `etsy.taxonomy_refreshed` row (`category_choices`, `property_candidates`).

Do **not** use `TAXONOMY_PATTERNS` (66). The system itself reports it as "never verified".

**Attributes the system decided** (regenerated `listing.seo`). These are pattern facts; the Etsy property ids are PENDING E4.

| Key | Value | Note |
|---|---|---|
| craft_type | crochet | PENDING E4 |
| pattern_type | basket | PENDING E4 |
| skill_level | confident beginner | map only to an offered value |
| primary / secondary colour | cream / wine | PENDING E4 |
| file_type | PDF | |
| digital / instant_download | true / true | listing type Digital |
| includes_chart / includes_written_instructions | true / true | description |
| terminology | US terms | **defect E-9**: the listing ships US and UK |
| occasion | none | |

**Fixed listing fields** (`integrations.etsy.ListingPayload`):

| Field | Value | Note |
|---|---|---|
| type | download | |
| who_made | `i_did` | owner decision O-6 |
| when_made | `made_to_order` | |
| is_supply | true | |
| quantity | 999 | |
| materials | `worsted cotton` | de-duplicated |
| renewal | manual | |

## 4. Tags (exactly the system's regenerated SEO output)

```
basket crochet, written and chart, crochet home decor, pdf crochet pattern, hexagon basket, diy basket, digital download, home decor diy, instant download pdf, yarn craft project, us and uk terms, printable pdf chart, fiber art project
```

| # | Tag | Chars |
|---|---|---|
| 1 | basket crochet | 14 |
| 2 | written and chart | 17 |
| 3 | crochet home decor | 18 |
| 4 | pdf crochet pattern | 19 |
| 5 | hexagon basket | 14 |
| 6 | diy basket | 10 |
| 7 | digital download | 16 |
| 8 | home decor diy | 14 |
| 9 | instant download pdf | 20 |
| 10 | yarn craft project | 18 |
| 11 | us and uk terms | 15 |
| 12 | printable pdf chart | 19 |
| 13 | fiber art project | 17 |

**Rule checks.**
- 13 tags, which is the maximum of 13.
- Each tag is 20 characters or fewer.
- No tag starts with `'` or `-`.
- Every tag uses only letters, digits and spaces.
- `publish.listing_schema.tag_problems(tags)` returns `[]`.
- The limits are VERIFIED_HELP_CENTER (article 360000336307).

**Differences from the pre-decision tags.**
- `nursery crochet`, `nursery basket` and `beginner crochet` are gone.
- `us and uk terms`, `printable pdf chart` and `fiber art project` were added.

**Evidence basis.** The tags are modelled; no search volume is measured.

**This run had no other listing.** The tags were generated without other listings in the scratch database, so there was nothing to diverge from. Production's `listing.seo` diversifies tags against every stored listing (#240), so the stored tags may differ. **If production's stored tags, title and description for this release can be read back after deploy, those take precedence.**

**The SEO strategy tags are separate.** `seo.strategy.TAGS["hexagonal-bread-basket"]` holds the lane-G strategy tags, which include "bread basket", "kitchen decor" and "table decor". They are a separate strategy proposal and are not what `listing.seo` writes. This package uses the chain's output.

## 5. Price

**Price: CA$6.50, pending final pricing verification** (D-W4-OWNER-BASKET-IDENTITY).

| Figure | Before the decision (three-size candidate) | After (one size, `hexagonal-bread-basket`) |
|---|---|---|
| Band | CA$4.00–12.00, SOURCED | same |
| `decide_price` input | `sizes_offered=3` | `sizes_offered=1` |
| Price | CA$6.50 | **CA$6.50** |
| Reasons | "3 finished sizes from one chart, which no profiled competitor offers" | **none** |
| Net after modelled fees | CA$5.60 (13.8% take rate) | CA$5.60 (13.8% take rate) |

**Did the old rationale rely on the three sizes?** Partly:
- the three-size reason was the only *reason* `decide_price` recorded;
- but the price itself never depended on it. `decide_price` holds the proposed CA$6.50 because it lies inside the band, with or without the reason.

So both computations give CA$6.50, and the one-size run records no premium reason. The price was not changed.

**Price notes**
- **Band rationale:** "A basket-specific observed price is UNKNOWN … the proposal sits mid-band rather than pretending to a comparable".
- **Not modelled:** Offsite Ads, the regulatory operating fee and currency conversion. With all three, the take rate would be 32.4% and the net CA$4.39 (SECONDARY rates).
- **Listing fee:** US$0.20 (about CA$0.28) per listing and per renewal.
- **Shop currency:** UNKNOWN in the repo. Confirm CAD before entering the price (O-8).

## 6. Digital download details

| | US terms | UK terms |
|---|---|---|
| File name (`f"{slug}-{pattern_filename(t)}"`) | `market-basket-small-pattern-us.pdf` (34 chars) | `market-basket-small-pattern-uk.pdf` (34 chars) |
| Format | PDF | PDF |
| Pages | **7** (was 9: the children's safety pages are gone) | 7 |
| Size (scratch run) | 376,631 bytes | 376,636 bytes |
| sha256 (scratch run, **not** the certified file) | `c5dbe661…00b1` | `fc3592b8…2d6d` |

**Checked text.** The regenerated US and UK PDF text contains no "nursery", "baby", "child", "children", "infant", "nesting", "three sizes", "CPSIA" or "under 3".

**Etsy limits** (VERIFIED_HELP_CENTER, article 115015628347):
- at most 5 files;
- at most 20 MB each;
- file names at most 70 characters, which cannot be edited after upload.

**Files to upload.** These must be the certified PDFs re-rendered from the **corrected source**. That means W-PDF (`claude/w4-PDF1`) after merging this branch's source change, and production `assets.built` after deploy. Their sha256 must match production's `pdf_sha256_by_terminology` for this release.
- **Any PDF rendered before this change is stale.** It still carries the nursery safety block.
- **The tester kit's TEST.pdf is stale too.** It is `a724cbae…`, 9 pages, and also predates the change. The pattern instructions are identical and the content hash is the same, so the tester's evidence still binds. The kit should still be rebuilt so the tester works the customer's text (W4-SAMPLE §0.1 rule).

**Delivery message.** This is set at shop level. Its text is `store_foundation.copy_v2.DIGITAL_SALE_MESSAGE`:

```
Thank you, and happy making. Your pattern is ready now: open your Etsy account, go to Purchases and downloads, and both PDFs (US and UK terms) are there. Etsy has emailed you a link as well.

Two things worth knowing. Under our pattern terms, finished items may be sold by individual makers and small businesses, not manufactured at scale. And if anything in the pattern does not add up, reply to this message with the pattern name and the row number: we correct the pattern itself and send you the corrected file.
```

Whether it is set on the live shop is NEEDS PRODUCTION READBACK.

## 7. Disclosures: every one, and where each goes

| Disclosure | Text (source) | Where |
|---|---|---|
| AI-assisted design | `DISCLOSURES["ai_assisted_design"]` | **Description**, present twice (Etsy: "within their listing description", article 360024112614). Also in each PDF as `publish.pdf.AI_DISCLOSURE`. |
| Digital, nothing shipped | `DISCLOSURES["digital_download"]` | Description; listing type Digital |
| Image disclosure | §2.2 [PACKAGE EDIT 1] | Description |
| Renders are renders | in-pixel caption "Digital rendering of the pattern's finished design, not a photograph", plus alt text | Each render |
| PDF preview | "Preview of the pattern document" | CONTENTS frame |
| Deterministic charts | `DISCLOSURES["deterministic_render"]` | Description |
| AI photo edits, if any | "Some photos have been colour- or light-adjusted with editing tools." | Description, only if an edit was made |
| Licence not legally reviewed | present | Description |
| Children's statements | **None owed.** The product is `not_for_children`. | — |
| "Made with AI" attribute | UNKNOWN | The owner checks the listing form (O-3) |

## 8. Premium listing-gallery brief

**Etsy image specs** (`integrations.etsy_constraints`, confirmed by W-IMAGEPOLICY):
- up to 20 images;
- 2000 px or more on each side recommended;
- first image at least 635 px, landscape or square, with crop-safe borders;
- jpg, png, gif, svg or heic, with no transparency;
- converted to sRGB;
- files over 1 MB may not finish uploading;
- alt text up to 500 characters (250 advised).

**Photos: each requires a physical sample, which has not yet been made.**
- **Sample:** a full make by an independent tester from the exact release PDF (`1ddde587…`), under W4-SAMPLE package A (`tester_outreach`).
- **Rights:** each photo needs a rights basis (`tester_agreement` or `brambleloop_made`).
- **Intake:** by sha256 through `POST /api/physical-photo`.
- **Styling:** kitchen and home, per the owner's positioning. This matches W-IMAGEPOLICY §5.1.

| # | Shot | Edit rule | Aspect / size | Label | Alt text (≤ 250; finalise to the photo) |
|---|---|---|---|---|---|
| **1 (FIRST)** | Three-quarter view from about 30° above. The whole basket on a real kitchen or dining table, empty or with two or three bread rolls that do not hide the rim. Centred, generous margin. | **UNEDITED.** No filter, crop, resize or background change. Shoot in final framing; keep the original and its sha256. | **Landscape 4:3 or square 1:1, ≥ 2000 px each side** | none | "Photograph of a crocheted hexagonal bread basket in cream with wine rounds, made from this pattern, holding bread rolls on a wooden table." |
| 2 | Top-down: the hexagonal base, the six increase lines and the inside | may adjust exposure (not AI) | square, ≥ 2000 px | none | "Overhead photograph of a crocheted hexagonal basket showing its six-sided base and corner increase lines." |
| 3 | Side profile at table level: wall height, walls standing straight | may adjust | square, ≥ 2000 px | none | "Side photograph of a crocheted hexagonal basket at table level showing straight walls about [measured] cm tall." |
| 4 | Scale: tape across the points (about 16 cm); a second frame with the tape at wall height (about 8.7–9 cm) | may crop | square, ≥ 2000 px | none | "Photograph of a crocheted hexagonal basket with a tape measure across its base, about [measured] cm across the points." |
| 5 | Detail macro of the rim and the colour change | may crop | square, ≥ 2000 px | none | "Close-up photograph of single-crochet stitches at the rim of a crocheted basket where cream meets wine." |
| 6 | In use: on a set table with bread | may adjust (not AI) | landscape 4:3, ≥ 2000 px | none | "Photograph of a crocheted hexagonal basket of bread rolls in the middle of a table set for a meal." |

**Measurements.** Use **measured** values in the alt text of shots 3 and 4. A difference from 16.0 / 13.9 / 8.7 cm is reconciled by Product Truth before publishing. Never retake a photo to hide one.

**Renders, charts and PDF preview** (the system's certified set). All are 2000 × 2000 PNG, labelled in pixels. The alt texts below are the system's, regenerated, and now name the product correctly.

| # | Frame | Label (pixels) | Alt text (system, verbatim) |
|---|---|---|---|
| 7 | Disclosed render, hero | "Digital rendering of the pattern's finished design, not a photograph" + cm scale | "Digital rendering of the pattern's finished design, not a photograph. Crochet Hexagonal Bread Basket: the finished basket seen from slightly above, in cream and wine. About 16 x 8.7 cm at the stated gauge, with a centimetre scale bar." |
| 8 | Disclosed render, scale | same | "Digital rendering of the pattern's finished design, not a photograph. Crochet Hexagonal Bread Basket: the finished piece with its size marked, in cream and wine. About 16 x 8.7 cm at the stated gauge, with a centimetre scale bar." |
| 9 | Disclosed render, detail (base from above) | same | "Digital rendering of the pattern's finished design, not a photograph. Crochet Hexagonal Bread Basket: the base seen from above, every base round stitch for stitch, in cream and wine. About 16 x 8.7 cm at the stated gauge, with a centimetre scale bar." |
| 10 | Disclosed render, angle | same | "Digital rendering of the pattern's finished design, not a photograph. Crochet Hexagonal Bread Basket: the finished piece, in cream and wine. About 16 x 8.7 cm at the stated gauge, with a centimetre scale bar." |
| 11 | Supplement CONSTRUCTION | as above | "Digital rendering of the pattern's finished design, not a photograph. Hexagonal Bread Basket: how it is built: the stitch count of every round or row, in working order." |
| 12 | Supplement COLOUR_CONTEXT | as above | "Digital rendering of the pattern's finished design, not a photograph. Hexagonal Bread Basket: each yarn colour's share of the finished piece, counted from the pattern." |
| 13 | Supplement MATERIALS | as above | "Digital rendering of the pattern's finished design, not a photograph. Hexagonal Bread Basket: the yarn colours, yarn weight, hook size and gauge the pattern calls for." |
| 14 | **CONTENTS: PDF page preview** | "Preview of the pattern document" | "Preview of the pattern document. Hexagonal Bread Basket: the first pages of the PDF pattern you download, shown at reduced size." |

**Supplement alt text came from the product record.** It used to say "Nesting Baskets, three sizes". It now reads "Hexagonal Bread Basket", because `visual.launch_imagery._primary_for` reads the new candidate's title. The [PACKAGE EDIT] that patched it earlier is no longer needed.

**Image bytes.**
- Use the certified bytes (`runtime.etsy_ops.certified_images`), in certificate order.
- Render the CONTENTS preview from the **re-rendered** certified PDF (§6).
- The independent vision review (#61) is UNKNOWN (LAUNCH_PATH E6).

**Order.** Photos first, with the unedited photo at #1. Then renders. The PDF preview goes last. Renders are never first, and never the only images of the finished result.

## 9. Outstanding publication requirements (checklist)

Status as of 2026-10-27. **Every box is open unless marked done.**

### Owner

- [x] **Identity and positioning: decided.** D-W4-OWNER-BASKET-IDENTITY (2026-10-27): kitchen and home, small basket only, CA$6.50 pending pricing verification.
- [ ] **O-1. "AI-generated functional instructions, such as craft patterns": HARD BLOCKER.**
  - Source: article 360024112614, edited 2026-10-22; Creativity Standards, read in person.
  - Do not reword the disclosure to resolve it.
  - References: W-IMAGEPOLICY §2.3, §4.8, §6.2; ETSY_POLICY_READINGS_PACKET source 2, Q3.
- [ ] **O-2.** Read the Listing Image Requirements legal page in person. Source: W-IMAGEPOLICY §6.1.
- [ ] **O-3.** Check the listing form for a "made with AI" attribute. Source: W-IMAGEPOLICY §6.3.
- [ ] **O-4.** Approve `tester_outreach` for market-basket-small@1.2.0.
  - Cost: **CA$66.00** (fee plus 2 balls, ESTIMATED), or CA$59.65 with yarn reimbursed per metre.
  - Time: 25 minutes.
  - Also add the "re-weigh after the swatch" line (G2), and rebuild the kit's TEST.pdf from the corrected renderer (§6).
  - Consequence of waiting: no compliant listing is possible.
  - Source: W4-SAMPLE §1.8, §4, §5.
- [ ] **O-5.** Record the policy readings in person: `seller_policy`, `creativity_standards` and `listing_image_rules`. Then review each `policy_changed` card.
  - `children_and_baby` is **no longer required for this listing** (§2.4). It is still required for the shop's two baby blankets.
  - Source: ETSY_POLICY_READINGS_PACKET; LAUNCH_PATH E5.
- [ ] **O-6.** Decide `who_made`, together with O-1. Source: `seo.constraints.who_made_enum` note.
- [ ] **O-7.** Approve the listing fee: US$0.20 (about CA$0.28) per listing and per renewal. Source: template §11.
- [ ] **O-8.** Confirm the shop currency is CAD. Source: §5.
- [ ] **O-9.** Final pricing verification of CA$6.50. Source: D-W4-OWNER-BASKET-IDENTITY; §5.
- [ ] **O-10.** Confirm `digital_sale_message` is set. Source: `intel.etsy_surfaces` (production readback).
- [ ] **O-11.** Keep the automated publish path disarmed for `market-basket-small@1.2.0` while a manual listing exists. Source: §10.

### Physical

- [ ] **P-1.** Full make by an independent adult who is not the owner (F-071), scope `full_make`, against content hash `1ddde587…`. Source: W4-SAMPLE §1.2.
- [ ] **P-2.** `POST /api/physical-test` with `passed=True`, bound to `1ddde587…`. Source: W4-SAMPLE §1.7; LAUNCH_PATH E7.
- [ ] **P-3.** Every measurement within ±12% of the stated size: 16.0 / 8.7 / 13.9 cm. The code does not check the flats measurement. Source: W4-SAMPLE §1.4.
- [ ] **P-4.** Photographs per §8: #1 unedited, a rights basis, and the original's sha256. Source: W-IMAGEPOLICY §4.3, §5.1.
- [ ] **P-5.** Product Truth reconciles any measured difference. Source: W-IMAGEPOLICY §5.

### Engineering

- [x] **Identity source fix: done on `claude/w4-LISTING1`.** The fixed parts are:
  - the `products.launch0` candidate split and lookup precedence;
  - `seo.strategy`, `seo.facts`, `seo.shop`, `creative.emotional_brief` and `creative.audit`.

  The content hash is unchanged. Tests are listed in the commit and the report. Source: DECISION_LOG D-W4-OWNER-BASKET-IDENTITY.
- [ ] **E-0.** Merge and deploy that change, then re-render this release's PDFs and listing set. The production PDF and `Listing` row still carry the nursery framing until this happens. W-PDF must merge it. Source: §6.
- [ ] **E-1.** Add a mixed photo-and-render gallery disclosure to `DISCLOSURES` and `check_ai_disclosure`. Fix the copy_v2 About text ("We have not yet worked physical samples") and `brand.storefront`. Source: W-IMAGEPOLICY §4.5.
- [ ] **E-2.** Require a `PHYSICAL_PRODUCT_PHOTO` before a pattern listing can publish. Source: W-IMAGEPOLICY §4.7, §7.
- [ ] **E-3. Category and search certificate: PENDING W-LAUNCHFIX E4.** Source: W-LAUNCHFIX §4; LAUNCH_PATH E4.
- [ ] **E-4.** Build a manual-listing adoption path (§10).
- [ ] **E-5.** The W-LAUNCHFIX D1/D2/E3 fixes are unmerged and untested. Source: W-LAUNCHFIX header.
- [ ] **E-9.** The `terminology` attribute says "US terms" although the listing ships US and UK. The "Fibre" line contradicts "worsted cotton". Source: §2, §3.
- [ ] **E-10.** Reconcile the 140/13/20 limit status between `seo.constraints` and `integrations.etsy_constraints`. `etsy_constraints` goes stale on 2026-11-05. Source: §1, §4.
- [ ] **E-12.** The certified, re-rendered PDFs must equal production's `assets.built` hashes. Source: §6.
- [ ] **E-13.** Minor: `housewarming-key-basket`'s price-band text still says "below the nesting baskets' three-size price", which is stale wording in another product's record. It was not changed here. Source: `products.launch0`.

### Policy and evidence

- [ ] **V-1.** The release is certified in production at 1.2.0 with hash `1ddde587…`. Source: LAUNCH_PATH E11.
- [ ] **V-2.** All nine first-customer areas pass. In the re-run chain, `gauge_and_size_claims` is UNRESOLVED and `etsy_remote_state` is UNVERIFIABLE. Source: evidence JSON; LAUNCH_PATH A9.
- [ ] **V-3.** Independent vision review. Source: LAUNCH_PATH E6.
- [ ] **V-4.** The image rules are met: an unedited photo first, renders labelled and never alone, and a PDF preview. Source: W-IMAGEPOLICY §1, §3.
- [ ] **V-5.** Owner review of the first-customer evidence (`NEVER_AUTHORISES`). Source: LAUNCH_PATH A9.

## 10. Reconciliation note: matching a manual listing to Brambleloop's records

**Finding: no manual-listing adoption path exists. This is engineering gap E-4.** The grep in full is in `hexagon-coaster-set-1.2.0/LISTING_PACKAGE.md` §10. In summary:

**What exists today**
- `ops/adoptions.py` is the F-417 register of technology costs. It has no listing concept.
- Only `store.publish` writes `Listing.etsy_listing_id`, through `publish/draft_intent.checkpoint` and `runtime/pipeline.py:2110`. No route, action or job binds a hand-made listing.

**What happens to a hand-made listing**
- **Census:** it raises a P2 `etsy.unexpected_listing:<id>`. It is never adopted and never checked for drift.
- **Orders:** recorded as "unmatched: no listing of ours carries this Etsy listing id", with product and version blank.
- **Stats export:** matches only by slug, Etsy id or exact lower-cased title, and only if the production `Listing` row exists.

**Duplication risk.** `store.publish` would create a second Etsy listing for this release once its gates clear. O-11 is the only guard.

**Interim manual record.** Kept by the owner at publication, in operator records, not in this repo:

```
slug@version:            market-basket-small@1.2.0   (product: hexagonal-bread-basket)
release_hash:            1ddde587f537388b4a9dd5a74e9a0e0ebadc6ce0c0a79372dd6b867a230b3991
etsy_listing_id:         <from the listing URL>
published_at (UTC):      <ISO 8601>
state set:               draft | active
title / tags / price:    exactly §1 / §4 / §5 (note any deviation)
category chosen:         <path, and id if shown>   (unverified until E4)
files uploaded:          <name, sha256> x2  (must equal production assets.built, post-fix render)
photos uploaded:         <rank, sha256, rights_basis, unedited yes/no>
renders uploaded:        <rank, sha256 from certified_images>
```

**What E-4 must build.** An owner-authorised `listing.adopt_manual` action, under step-up, that does five things:
1. read the listing back;
2. verify every field, file hash and image hash against the certified payload;
3. write `etsy_listing_id`;
4. record a `DraftIntent` with state `CREATED` and the remote id;
5. audit `listing.adopted_manual`.
