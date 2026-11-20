# VISREF: reference readiness and the minimum truthful lifestyle-image design

- **Branch:** `claude/w4-VISREF`, based on `origin/claude/w4-INTEG2` 9c3812bd. Production is
  1b21e81 (SHADOW; nothing published).
- **Scope:** shadow only. No provider was called, nothing was spent, and no credential,
  provider setting or production state was changed.
- **Input:** the owner's study, `inputs/Brambleloop_Image_Model_Research_2026-10-19.pdf`
  (12 pages, sha256 `199c99ef909a44d4ebf91cfd974d17fe106e0d7a5985636be0103a617320b45c`),
  committed in a8e4c5e6. It is treated as research evidence, not as proof. Each claim is
  reconciled in §0. Its provider and pricing claims were re-read from official documentation
  on 2026-10-19 (§7).
- **Product list:** the eight Launch-0 products in code are `_CORE_LAUNCH0_SLUGS` plus
  `PROPOSED_SLUGS` (products/launch0.py:759, `CATALOGUE_FLOOR_APPROVED = True`).
  harvest-table-runner is the reserve and is not audited here.

## 0. Research findings reconciliation (PDF of 2026-10-19 against the code at 9c3812bd)

The study inspected 7bbbe72 and INTEG2 at 5cc096f. Between 5cc096f and 9c3812bd, the only
change is a record commit (`DEPLOYED_HISTORY`). Its code findings therefore still apply to
today's code. No newer branch changes `visual/compose.py`, `disclosed_render.py`,
`product_authority.py`, `gateway/images.py` or `owned_photography.py`. W-PRODREADY changes
`frame_role.py` and `listing_assets.py`, for legibility only.

| # | PDF claim | Verdict | Evidence |
|---|---|---|---|
| 1 | `disclosed_render` draws on a 2000×2000 opaque RGB canvas; it is not a yarn photograph or a cutout | **Confirmed** | `disclosed_render.py:165` `Image.new("RGB", …)`. Measured: all 50 frames of the 8 products are mode RGB, 2000×2000, with no alpha (§1). |
| 2 | If you pass that image to `compose.verify`, the whole canvas is protected | **Confirmed, with a refinement** | `compose._rgba` converts RGB to alpha 255 everywhere. However, the path that is actually wired (`final_image_gate.product_cutout`) zeroes the exact background colour. Its protected "product" region therefore includes the drawn **caption, scale bar and dimension text**, and its matte is binary (0/255). Measured on a real hexagon-coaster hero: `test_a_real_disclosed_render_is_an_opaque_diagram_whose_cutout_includes_its_captions`. |
| 3 | `product_authority` keeps structure UNKNOWN without qualified whole-product evidence, even after pixel preservation passes | **Confirmed** | `product_authority._structural_floor`, last return. There is no branch for a photographic reference. |
| 4 | `owned_photography.make` returns a redraw refusal | **Confirmed** | `owned_photography.py:250-251`. **Refinement:** the owner/tester photo path is `publish/physical_upgrade.intake` (bytes plus a rights basis, then the PROOF job), not `owned_photography`. `owned_photography` is the disabled AI-illustration path. "An owner photo through owned_photography" therefore names the wrong module. |
| 5 | `gateway/images` provider table: flux-2-pro, gpt-image-2, nano-banana-2→gemini-3.1-flash-image, seedream-v5-lite; prices embedded 2026-09-20; no Ideogram adapter | **Confirmed** | `gateway/images.py:92-122`. grep finds no `ideogram` or `recraft` anywhere in `src/`. |
| 6 | The BFL path sends only `refs[0]` | **Confirmed, partly mitigated** | `images.py:487-488`. `conditioning_receipt` (`images.py:521`) measures the built body and reports `proven: False` for the references that were not sent, so a provider label alone cannot pass. |
| 7 | `contents_frame` binds the released PDF bytes and hashes | **Confirmed** | `contents_frame.released_pdf` (`:75`) reads the certified hash from the `assets.built` record. **New:** `build_pattern_pdf` is deterministic per `released_on` but prints the release date, so a rebuild on another day has a different sha256 (measured: `2347c6d9…` on 2026-10-19, `58d010d2…` on 2026-10-20). Version binding must use the certified hash and never a rebuild. |
| 8 | B2VISION digest resolution and VISROLE role routing exist and must be kept | **Confirmed** | aabc8db3 (B2VISION), 640c63ff (VISROLE). VISROLE classifies anything unlisted, including `AI_LIFESTYLE_CONCEPT` and `PHYSICAL_PRODUCT_PHOTO`, as photographic (strictest). Re-asserted in `test_informational_references_are_refused_and_lifestyle_frames_are_photographic`. |
| 9 | FIRSTIMG / HEROVISION / HEROTOURNEY exist | **Confirmed** | b15b34c3, 4f6e65df, b93b6f66. |
| 10 | Spend reservation, uncertain-call accounting and bounded plans exist; do not build a second budget system | **Confirmed** | `gateway/images.reserve_render`, `visual/spend_plan.guard`, `finance/spend_policy.py:42` (`CEILING_CAD = 100.0`), `:62` (`BENCHMARK_BUDGET_CAD = 50.0`). |
| 11 | "Five certified galleries" were shadow certificates; LIFESTYLE was uncovered | **Confirmed** | `VISUAL_STATUS.md`. Re-measured in §1: LIFESTYLE is missing on all 7 products where it applies. It does not apply to ornaments. |
| 12 | The ornament one-of-six and placemat one-of-two defects are historical | **Already fixed in 8a41fe7c (W4-MULTIPIECE)** | Viewed today: the ornament hero draws 6 pieces and the placemat hero draws 2. |
| 13 | VB-1's CA$4.76 was never executed and is not current headroom | **Confirmed** | `VISUAL_STATUS.md` VB-1 table. CA$0 has been spent. |
| 14 | Copying every nonzero-alpha source RGB pixel can keep an old-background halo; the PDF says this is "not a finding that the repo has a visible defect" | **Confirmed, and stronger** | `compose.protect` copies soft-edge pixels *with their partial alpha*. Its export is therefore not opaque, and Etsy renders transparency black (`w3/ETSY_REQUIREMENTS.md:44`, VERIFIED 2026-10-06). The defect is latent: no composite exists yet. Characterised in `test_existing_exact_copy_mode_keeps_partial_alpha_which_etsy_renders_black`. |
| 15 | Ideogram 4.5 Precise Edit: `POST https://api.ideogram.ai/v2/image/precise-edit/ideogram-4-5`; black = edit, white = keep; context region ≥256 px per side, aspect ≤6:1, ≤4,194,304 px; `dry_run` gives a price quote | **Confirmed against official docs, 2026-10-19** | §7 |
| 16 | Ideogram medium CA$0.0849 / high CA$0.3114 (US$0.06 / US$0.22) | **Not confirmed on an official page** | Ideogram's pricing page is client-rendered ("Loading current prices"). Only resellers and launch coverage give US$0.06 / US$0.22, and they disagree on the high tier. The official mechanism is `dry_run`, which must quote the price before any reservation. |
| 17 | Recraft V3 CA$0.0566 per raster edit; white = regenerate, black = keep; lossless output | **Confirmed against official docs** | US$0.04 per image for inpaint, generateBackground and replaceBackground. `image_format` is `webp` (lossless) or `png`. |
| 18 | FX: 1 USD = CA$1.4154 (Bank of Canada, 2026-10-16) | **Confirmed** | bankofcanada.ca, read 2026-10-19. **New:** the code reserves at `1/0.715 = 1.3986` (`core/fx.py:17`), which under-reserves USD-priced calls by about 1.2% at today's rate. A plan ceiling therefore needs a buffer. |
| 19 | Etsy recommends ≥2000 px in both dimensions | **Confirmed (repo record)** | `w3/ETSY_REQUIREMENTS.md:44`. Re-fetching the pages today returned HTTP 403 (DataDome, §8). |
| 20 | OpenAI Sunburst, Gemini 3 Pro, FLUX 3, Photoroom, Bria and others: capabilities and prices | **Not verified** | They are outside this proposal's two arms. They stay the PDF's claims and are not used here. |
| 21 | "The highest-leverage missing piece is trustworthy photographic product evidence" | **Confirmed** | §1: no product has a photograph or a validated photoreal render, `twin.calibrated` is False for all 8, and PRODREADY B4 records no passed physical sample. |

Two findings the PDF does not make:

- **The owner action recorded for F-030/F-254 would not close them truthfully.**
  `COMPLETION_BOARD_FINAL` offers "approve visual_paid_generation (P2 max CA$2.00) *or*
  supply sample photos". P2 is flux-2-pro "protected composites". The only foreground that
  exists today is the disclosed diagram, and flux-2-pro has no mask field in our adapter.
  Funding P2 would therefore buy a diagram pasted into a room, which is not a lifestyle
  photograph. **Recommendation: do not approve P2 as written. The sample-photo branch is the
  one that leads anywhere.**
- **Titles and fabric are a generator-invention risk.** "Nordic Snowflake Ornament Set (6)"
  is six flat 9.6×10.2 cm rectangles, striped, with raised dc. They have no snowflake
  outline. "Diamond Lattice Placemat Pair" carries its lattice only as dc relief inside
  one-colour rows. "Mosaic" and "graphghan" fabrics are one colour per row, because the CIR
  cannot express more (`launch0.per_stitch_colour_expressible() is False`). A generative
  model is likely to "correct" these toward the named motif. Exact restoration (below)
  prevents that, but it also means any physical sample must be reviewed against these exact
  relief layouts. The title wording is a merchandising-truth question for the product lane.
  It was not changed here.

## 1. Reference readiness, all eight products (P1)

**Method.** Every asset was materialised locally with deterministic tooling: the certified
CIRs from `launch0.cir_for`, `launch_imagery.assemble` (disclosed hero/scale/detail, gallery
frames, the vessel ANGLE view, each verified on its bytes) and `publish.pdf.build_pattern_pdf`
(US terms, `released_on` 2026-10-19). I then looked at every image with the Read tool, as
contact sheets, plus full-size frames for the placemat detail and the key-basket PDF pages.
The local PDF hashes are rebuilds, not the production-certified files (see §0 #7).

| Product (version, CIR fp) | Pieces / size (twin) | Whole-product reference | Kind | What verifies structure, motif, size, colour, count | Usable alpha matte | Truthful lifestyle possible now? |
|---|---|---|---|---|---|---|
| nursery-nesting-baskets (S/M/L 1.2.0; fc05b233 / d742f6ad / a43d6b1e) | 1 each; 16×8.7, 20.8×15.9, 25.6×23.2 cm | yes: disclosed hero, scale, detail and angle per size | informational illustration (glyph drawing, "not a photograph") | `render_verification` against the CIR checks stitch counts per round, colour bands, extent and caption: PASS on all 9 frames + angle. Dimensions are **arithmetic from the stated gauge**; `twin.calibrated=False`. | no: RGB; `product_cutout` is binary and includes text | **no** |
| cloudline-baby-blanket (1.2.0; cbca61cd) | 1; 79.2×96.4 cm | yes: hero/scale/detail | informational | same; PASS ×3; uncalibrated | no | **no** |
| hexagon-coaster-set (1.2.0; b9f6aa13) | 4; 9.7×8.4 cm | yes; the hero draws 4 | informational | same; PASS ×3; uncalibrated | no | **no** |
| nordic-star-ornaments (1.4.0; 4a84abec) | 6; 9.6×10.2 cm | yes; the hero draws 6 | informational | same; PASS ×3; uncalibrated. LIFESTYLE is not an applicable job for this category. | no | n/a (job not applicable) |
| winter-village-graphghan (1.3.0; 1f4eca4f) | 1; 86.4×91.8 cm | yes | informational | same; PASS ×3; uncalibrated | no | **no** |
| nordic-forest-mosaic-throw-baby (1.3.0; 3487773b) | 1; 57.6×67.8 cm | yes | informational | same; PASS ×3; uncalibrated | no | **no** |
| mosaic-placemat-pair (1.3.0; bb87acc6) | 2; 28.8×47.7 cm | yes; the hero draws 2 | informational | same; PASS ×3; uncalibrated | no | **no** |
| housewarming-key-basket (0.1.0; c6374369) | 1; 18.3×11.1 cm | yes: hero/scale/detail + angle | informational | same; PASS ×4; uncalibrated. The PDF itself says "computed, not yet measured on a worked sample". | no | **no** |

Across all eight:

- **Photograph: none.** No physical-photo evidence exists anywhere in the repository.
  `VISUAL_STATUS` records "0 accepted (no sample photographs on file)". PRODREADY B4 records
  no passed physical sample. I did not read the production `physical_photos` table, so its
  live count is UNKNOWN, not zero.
- **Validated photorealistic render: none.** Milestone D (Mitsuba) is PARTIAL on an `hdc`
  swatch only: 12 PASS, 7 UNKNOWN. It is not a launch product.
- **Gallery certification is informational, not photographic truth.** The disclosed
  frames prove that the drawing matches the CIR. They do not prove what yarn looks like,
  how the piece drapes, its stitch texture, its real size or its real colour.
- **The usable alpha matte is missing for every product.** The drawn glyphs have no yarn
  holes, fuzz or fringe, and the cutout carries the captions.
- **Missing evidence for each product.** For each product, the following are missing:
  1. a photograph of a physically worked sample, with every piece, in the intended pose,
     against a plain contrasting background, with front and macro views;
  2. its `physical_upgrade.intake` record, with bytes on file and a rights basis;
  3. a measured size against the twin;
  4. an independent construction review against the CIR: rounds/rows, stitch counts,
     colour order, border, piece count;
  5. a reviewed matte with opaque core, soft edge and true holes kept separate.
- **Inventing construction.** Without those, any photographic-looking lifestyle image would
  have to invent texture, drape and finish.

## 2. The actual visual architecture (P2)

1. **The product authority is the CIR.** `render_verification.authoritative_cir` resolves
   it, and `disclosed_render` (qualified versions `disclosed-render/2.0.0` and
   `disclosed-render-assembled/1.0.0`) draws it 1:1 as an opaque diagram.
   `render_verification.verify` re-measures the pixels independently. This is the only
   producer `product_authority.structural_floor` can PASS.
2. **Gallery frames** (`gallery_frames`, `contents_frame`, the angle view) are re-derived
   from the CIR or the certified PDF and verified on their bytes.
   `release_gates.disclosed_supplements` puts them into the listing-set certificate.
3. **The compositor** (`compose.protect`/`verify`) gives exact copy-back of nonzero-alpha
   pixels. It never certifies construction or photorealism.
   `final_image_gate.evaluate` (F-677) passes an image only if its product region is
   pixel-identical to a verified disclosed render (`product_cutout`). Vision readings can
   only FAIL.
4. **Generation** (`gateway/images`) uses a priced provider table. Its rules:
   - unpriced providers are refused;
   - each render is reserved against the monthly ceiling before the call;
   - uncertain outcomes are counted at the price;
   - `conditioning_receipt` proves which reference bytes were actually sent;
   - `refuse_benchmark_references` blocks competitor sources.
5. **Spend** goes through `visual/spend_plan` (complete plan + `guard` before each call) and
   `visual/provider_trial` (its own ceiling). Both sit under `finance/spend_policy`:
   CA$100 per month and a CA$50 benchmark budget.
6. **Redraw is prohibited (F-852).**
   - `owned_photography.make` and `model_photography` return `redraw_refusal`.
   - `eligibility.may_export` refuses `AI_LIFESTYLE_CONCEPT` in every role.
   - `asset_truth` requires `PHYSICAL_PRODUCT_PHOTO` to have camera provenance.
7. **Review** (`release._review_frames` with VISROLE, owned by PRODREADY for legibility):
   non-photo frames get the five role checks, and photographic or unknown frames get every
   realism check. An unclear check is unjudged.
8. **Physical proof** comes in through `physical_upgrade.intake` (bytes plus a rights basis),
   and `plan_upgrade` adds a `PHYSICAL_PRODUCT_PHOTO` PROOF frame and forces
   re-certification.

## 3. Confirmed root causes of the lifestyle-image gap

1. **No qualified photographic reference exists for any product (§1).** This is an evidence
   gap, not a model gap. Every downstream design depends on it.
2. **The only qualified product source is an informational diagram.** It is opaque RGB, and
   its binary cutout includes captions and the scale bar. Compositing it would put a
   labelled diagram into a room (§0 #1, #2).
3. **The existing exact-copy compositor cannot export a soft-edged matte truthfully.**
   It keeps partial alpha (black on Etsy) and copies soft pixels instead of compositing them
   (§0 #14).
4. **There is no masked-edit provider adapter.** No Ideogram or Recraft dialect exists, and
   none of the four existing providers has a mask field in our adapter.
5. **There is no evidence branch or asset class for "real sample photo + generated
   background".**
   - `product_authority` cannot PASS a photographic reference.
   - `eligibility` knows only `PHYSICAL_PRODUCT_PHOTO` (camera) and `AI_LIFESTYLE_CONCEPT`
     (refused).
   - A composite is neither. Deciding this is a policy decision, not a code default.
6. **The recorded owner action for F-030/F-254 (P2) is mis-specified** (§0, first new
   finding).

## 4. What newer commits have already fixed

The relevant fixes are older than the study's 5cc096f and already in production 1b21e81:

| Commit | Fix |
|---|---|
| 8a41fe7c | MULTIPIECE: 6 ornaments and 2 placemats drawn, verified and described |
| 35ff3402 | IMGFIX: scoped temp dirs; 340 px legibility |
| aabc8db3 | B2VISION: durable digest resolution for judges |
| b15b34c3 | FIRSTIMG: hero identification at full size and in the 230 px grid |
| 4f6e65df | HEROVISION: blind HERO judgement bound to bytes |
| b93b6f66 | HEROTOURNEY: ≥2 verified hero candidates in the blinded grid |
| 640c63ff | VISROLE: role-appropriate #61 review |

PRODREADY (not merged) changes the legibility of essential text (a4cf1211) and restores the
#61 closure (3a5e6c99). It is out of scope here. **None of these touch the lifestyle gap.**

## 5. Smallest implementation needed (P3), and what this branch built

**Design.** Lane 1 of the study, using the existing protected compositor. Masked generation
is assumed **not** to preserve pixels.

1. **Reference.** An owner photograph of a physical sample enters through
   `physical_upgrade.intake`, with `rights_basis=brambleloop_made`. A qualified render is
   the alternative.
2. **Matte.** Opaque core (255), soft edge (fuzz/fringe 1..254) and true holes (0) are kept
   separate. A person reviews the matte. Its component count must equal the CIR's piece
   count.
3. **Mask.** The mask is derived from the matte in the provider's documented polarity:
   Ideogram black = edit, Recraft white = regenerate. It is checked to be binary, the same
   size as the image, two-region, and exactly the matte.
4. **Provider call.** It goes through `reserve_render`, with a `spend_plan` and an Ideogram
   `dry_run` quote first. Its output must be the same size; nothing is resampled.
5. **Deterministic restoration as the last step.**
   - Opaque pixels are copied exactly.
   - Soft pixels are `(a·src + (255−a)·gen + 127) // 255`.
   - Holes and background are the provider pixel.
   - The export is opaque RGB PNG.
6. **Independent re-verification.** Every pixel is re-checked on the exported bytes.
7. **Exact-hash certificate.** It binds product slug, version, CIR fingerprint, certified PDF
   sha, piece count, reference sha and class, provider, source, mask, provider output and
   export.
8. **Independent Product Truth and the photographic review.** Product Truth on the export,
   then the full photographic realism review (VISROLE), the disclosure, and every existing
   veto.

**Built on this branch (thin glue, inside `visual/compose.py`; `protect`/`verify` unchanged):**

- `MASK_POLARITY`, `edit_mask`, `check_mask`: provider polarity, size, binary, both regions,
  exact agreement with the matte.
- `restore`, `blend`, `verify_restored`: alpha-edge restoration plus an independent
  per-pixel verifier. It refuses resampling, empty mattes, non-RGB exports and truncated
  input.
- `matte_components`: deterministic 8-connected piece count. Holes do not split a piece.
- `certificate`, `verify_certificate`: an exact sha256 of the exported bytes. A re-encode
  with identical pixels is refused.
- `lifestyle_evidence`: PASS only when every required piece of evidence is PASS on one
  product/PDF/reference version.
  - An informational reference class FAILs.
  - A missing or unknown item is UNKNOWN, never PASS.
  - A physical photo needs intake `may_use` and bytes present.
  - It never certifies photorealism.
  - It is evidence only, and is **not yet wired into the release path** (§9 E4).

**Not built, deliberately:** provider adapters, any provider call, a matte producer, an
asset-class or eligibility change, and release wiring. Each needs an owner decision or
credentials (§9).

**If the references are not good enough, the smallest credible way to qualify one:**

- **Option 1: one physical sample.** The owner (or a tester) works one sample of
  hexagon-coaster-set: 4 flat 7-round DK-cotton motifs of 168 stitches each, the smallest
  product where LIFESTYLE applies.
  - Photograph all 4, top-down, in daylight, on a plain contrasting board, with a
    millimetre ruler in one frame and a macro of one coaster.
  - Upload through `physical_upgrade.intake` with `rights_basis=brambleloop_made`.
  - A crochet-competent reviewer compares the photographs against the CIR: 7 rounds;
    6/12/…/42 stitches; wine in round 6; 4 pieces; measured across-the-points 9.7 cm ±10%
    (`SIZE_TOLERANCE`).
  - A flat, rigid, top-down product is the case where background-only editing is most
    truthful: no new drape and no hidden back.
- **Option 2: a qualified photoreal render.** This would be a new verified digital-twin
  capability, as in the study's Lane 2. It is much larger and is **not** recommended for
  launch.

## 6. Offline test results (P4)

All runs used testslot, with no network and no provider.

| Test file | Result |
|---|---|
| tests/test_w4_visref.py (new) | **14/14** |
| test_final_visual_authority | 10/10 |
| test_image_reference_hash_failclosed | 4/4 OK |
| test_owned_photography | all OK, exit 0 |
| test_w4_visrole | 8/8 |
| test_cert_listing_frames | 0 failing |
| test_vacuity | 4/4 OK. The first run flagged one loop in the new test, so a non-emptiness assertion was added and the suite was rerun clean. |
| test_launch | 28 OK, exit 0 |
| test_cost_governance_wave2 | 39 OK, exit 0 |
| test_search_hero_publish | 4/4 |
| test_v11_autonomy_timeline | 0 failing, exit 0 |

What `test_w4_visref.py` covers:

1. Mask polarity and dimensions for Ideogram and Recraft. Inverted, cross-provider,
   resized, grey, keep-only and unknown-provider masks are refused.
2. Exact preservation after a simulated provider repaints the product.
3. Alpha behaviour:
   - fuzz and fringe follow the alpha equation exactly;
   - holes show the new scene and never the old background;
   - the export has no alpha;
   - the latent partial-alpha defect in `protect` is characterised.
4. Motif removed, border recoloured, colours swapped, piece overpainted, fringe changed and
   hole filled are each rejected. The matte piece count is held to the CIR.
5. Product, PDF and reference version binding: mismatch FAILs, missing is UNKNOWN, and a
   different CIR or PDF hash FAILs.
6. Exact certification of the exported bytes, including the identical-pixels re-encode.
7. Photographic versus informational roles:
   - informational reference classes FAIL;
   - an unknown class is UNKNOWN;
   - lifestyle frames classify as photographic;
   - a real disclosed hero is shown to be an opaque diagram whose cutout includes its
     captions.
8. Corrupted inputs: resized or truncated provider output, an RGBA export and an empty matte
   are each refused.
9. No publication without all the evidence:
   - removing any single item blocks;
   - UNKNOWN is never PASS;
   - intake without rights FAILs;
   - an unreviewed matte FAILs;
   - `owned_photography.make` still refuses;
   - `final_image_gate` stays UNKNOWN without a source.

## 7. Trial proposal and cost (P5), a proposal only

**No product has a qualified reference today, so no trial can run yet.** The proposal below
starts only after §5 Option 1 has produced a reviewed reference for hexagon-coaster-set.

| | |
|---|---|
| **Arms** | 2× Ideogram 4.5 Precise Edit (`quality=medium`, explicit or `auto` context window, frozen mask, the same seed recorded) and 2× Recraft V3 `generateBackground` (`model=recraftv3`, `image_format=png`). Same reference, same matte and mask (polarity translated), same scene brief: "four coasters on a pale oak table, soft window light, a ceramic mug *beside* (never on) the coasters". Nothing may occlude a product pixel. |
| **Official facts (read 2026-10-19)** | Ideogram endpoint, multipart, `Api-Key` header, mask polarity, context-window limits, `dry_run` → `PriceQuote`: [developer.ideogram.ai precise-edit 4.5](https://developer.ideogram.ai/api-reference/images/precise-edit/ideogram-4-5.md). Recraft US$0.04 per image for inpaint, generate and replace background; $1 = 1,000 units, any number of packages: [recraft.ai/docs/api-reference/pricing](https://www.recraft.ai/docs/api-reference/pricing). Recraft mask polarity and limits (256–4096 px sides, ≤16 MP, <20 MB): [recraft.ai/docs/api-reference/tools/background](https://www.recraft.ai/docs/api-reference/tools/background). FX: [Bank of Canada](https://www.bankofcanada.ca/rates/exchange/daily-exchange-rates/), 2026-10-16, 1.4154. |
| **Expected cost** | Recraft: 2 × US$0.04 = **US$0.08** (official). Ideogram medium: 2 × US$0.06 = **US$0.12**. This is **unofficial**: the reseller figure, because Ideogram's page is client-rendered. The free `dry_run` must quote it before reservation. **Total US$0.20 = CA$0.28** at 1.4154. If Ideogram medium is not enough and the plan allows high (reseller US$0.22): US$0.52 = CA$0.74. |
| **Proposed ceiling** | **CA$1.00** hard, in `spend_plan` (`call_count=4`, `max_spend_cad=1.00`). It covers the FX gap (§0 #18) and taxes. It sits inside the CA$50 benchmark and CA$100 monthly ceilings. There is no auto-top-up. |
| **Owner actions** | (1) Physical sample + photos (§5 Option 1). (2) Create an Ideogram API account and key with billing (needs a card). (3) Create a Recraft API account and buy the smallest unit package (needs a card). (4) Put both keys in the production secret store. That is a credential change, which workers may not make. (5) Approve the CA$1.00 plan. |
| **Engineering prerequisites** | §9 E1–E3 and E6, all offline and testable before any spend. |
| **Success criteria (per image, all required)** | `check_mask` PASS; provider output the same size; `verify_restored` PASS; `lifestyle_evidence` PASS; VISROLE photographic review with every realism check answered, none unclear; two blind reviewers (construction plus commercial) report no invented seam, motif or border, the hole visible, believable contact shadow and no halo at 200–400% zoom; readable at 340 px. |
| **Arm success** | ≥1 of 2 accepted. Report cost per accepted image = billed spend / accepted (zero accepts reported as undefined, never hidden). Two images per arm are a smoke test, not an acceptance rate. |
| **Early stop** | Stop on any of: a `dry_run` quote above plan; the first provider output of the wrong size or mode; two consecutive `verify_restored` FAILs (a pipeline bug, not a model one); a safety refusal (422 or `is_image_safe=false`); any uncertain billing outcome; spend reaching CA$1.00. |
| **Expansion if it succeeds** | (a) The study's Stage 1 on 3 products × 2 briefs × 2 attempts for the winning arm and one challenger, ≤CA$20 with a new plan. (b) A sample photo per remaining product; baskets and blankets first, because LIFESTYLE applies there. (c) Stage 2 on all 7 LIFESTYLE products × 2 scenes. Every published image must pass individually, and F-030/F-254 close per product only after production readback. |

## 8. Etsy image-policy uncertainty

- **Pages unreadable to automated clients on 2026-10-19.** The official policy pages return
  HTTP 403 to this environment. The repository has recorded this before as DataDome
  (`evidence_B2GATE2/policy_access_live_2026-10-11.json`), and passing that challenge would
  be evasion. Affected pages:
  - [listing image requirements](https://www.etsy.com/legal/policy/listing-image-requirements/253962679005)
  - [Creativity Standards](https://www.etsy.com/legal/creativity)
  - [image best practices](https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop)
- **Already recorded and verified** (`w3/ETSY_REQUIREMENTS.md`, retrieved 2026-10-06):
  - recommended ≥2000 px in width and height;
  - the primary photo is a single finished product, not a collage;
  - **no transparency** (it renders black);
  - no webp;
  - "Seller-prompted AI creations must disclose the use of AI" (article 360024112614).
- **Still uncertain.** Whether an AI-generated *background* around a genuine photograph of a
  sample, on a **digital pattern** listing, is acceptable, and what wording Etsy expects.
  Neither the code nor the study found an explicit Etsy rule. A person must read the
  listing-image and Creativity pages in a browser, or ask Etsy support, before relying on
  composites. Until then the conservative wording stands: "Photograph of a sample made from
  this pattern; background digitally generated." It must never be the hero
  (`ASSET_CONCEPT_AS_HERO` already prevents a concept hero).

## 9. Engineering work and dependencies to close F-030, F-254, F-278 and related Build 2 rows

Row status today (board on 1b21e81):

- **F-030 / F-254:** `blocked_owner` (LIFESTYLE). Every other drawable job is certified on
  the six renderable products. CONTENTS is served from the certified PDF.
- **F-278:** `blocked_engineering`. The image_vision gate is open and the row must be
  re-verified.
- **F-253:** `blocked_engineering`. It requires photographic realism and pattern fidelity
  for photographic assets.
- **Build 2 #61:** OPEN, owned by PRODREADY.

| Step | Work (all offline-testable unless marked) | Depends on |
|---|---|---|
| E0 | Retire or rewrite OWNER_ACTIONS `visual_paid_generation` P2. As written, it cannot produce a truthful lifestyle image (§0). | integrator decision |
| E1 | **Reference manifest + qualification branch** in `product_authority`. A `physical_product_photo` reference PASSes structural truth only with: intake `may_use`; product/version/CIR fp/certified PDF sha; measured size within `SIZE_TOLERANCE`; and an independent construction-review record (reviewer ≠ maker, counts per round, colour order, piece count). Otherwise UNKNOWN. | **owner decision** on who qualifies as reviewer; a physical sample |
| E2 | **Matte producer** for plain-background photos: deterministic threshold or chroma plus morphological cleanup; core, soft and holes stored separately; `matte_components` == CIR pieces; `reviewed` set only by a person. | sample photos |
| E3 | **Provider adapters** in `gateway/images`: `ideogram` dialect (multipart, `Api-Key`, image, mask, `context_window`, `seed`, `dry_run` quote → reservation at the quoted price) and `recraft` dialect (`generateBackground`, png). Price rows with an official basis and date. `conditioning_receipt` must prove the image and mask bytes are in the body. `ACCOUNTS` entries. | owner accounts and keys (credential change) |
| E4 | **Asset class / eligibility for "sample photo, generated background"**. Add a labelled class or provenance (`camera+generator`) that `may_export` accepts only with `lifestyle_evidence` PASS, never as the hero, and with the label in alt text and in pixels. Wire `compose.restore` + `lifestyle_evidence` into `launch_imagery` LIFESTYLE coverage and the listing-set certificate. VISROLE keeps it photographic. | **owner policy decision** (D-record); Etsy policy reading (§8); coordinate with PRODREADY (`listing_assets`) |
| E5 | FX buffer: reserve USD-priced calls at the current rate plus a margin, or refresh `core/fx.ASSUMED_USD_PER_CAD`. | none |
| E6 | A trial driver for the edit arms. `provider_trial` drives `owned_photography.make`, which refuses; the driver reuses `spend_plan.guard` and the early-stop rules in §7. | E1–E3, owner spend approval (CA$1.00) |
| E7 | **F-278**: add the sample photo, or an accepted composite, as a second truthful hero-candidate class in HEROTOURNEY. A composite is never the hero; the sample photo can be. Re-run the 230/340 px recognition on production. | E1, sample photo, image_vision funded |
| E8 | **Closure evidence**: per product, LIFESTYLE covered by an image whose `lifestyle_evidence` is PASS, the full photographic review answered, the certificate valid, production readback of the uploaded bytes and alt text, and no-change evidence on every other gate. Close F-030/F-254 per product and never in aggregate. | everything above, plus an Etsy draft upload (owner authority) |

The smallest critical path:

1. owner physical sample of the coasters;
2. E1 + E2;
3. E3 + accounts;
4. the CA$1.00 trial;
5. E4 decision;
6. Stage 1/2 expansion.

F-030/F-254 cannot close truthfully before step 5, whatever model is chosen.

## Final results note

The full required regression set (test_vacuity, test_launch, test_cost_governance_wave2,
test_search_hero_publish, test_cert_listing_frames, test_v11_autonomy_timeline) plus the
visual, certification and owned-photography suites all pass on this branch (§6). The first
batch run was stopped at its 30-minute background limit during test_launch. The four
remaining suites were rerun separately and all passed.
