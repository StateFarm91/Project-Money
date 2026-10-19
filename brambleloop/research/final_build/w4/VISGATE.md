# VISGATE: which gallery roles need a photograph, and can the CIR make one

- **Branch:** `claude/w4-VISGATE`, based on `origin/claude/w4-INTEG2` 9c3812bd. Production is
  1b21e81 (SHADOW; nothing published).
- **Scope:** research and documentation only. No provider was called, nothing was spent, and no
  credential, provider setting or production state was changed. Three small local probes were
  run (§5.2). No source file was edited.
- **Inputs:**
  - `VISREF.md` at `origin/claude/w4-VISREF` 8eab43b;
  - the owner study `Brambleloop_Image_Model_Research_2026-10-19.pdf`;
  - spec PDFs 01, 08, 09, 10 and 11 in `brambleloop/spec/`;
  - `research/final_build/master_registry.json` (the Final Master ledger, which takes its text
    from spec 09);
  - `src/brambleloop/build2/requirements.json`;
  - `research/final_build/w4/COMPLETION_BOARD_FINAL.json`.
- **Products:** the eight Launch-0 products named in the brief.
- **Labels:**
  - **YES**, **NO** and **AMBIGUOUS** describe what a requirement's own words say.
  - **UNKNOWN** means a fact could not be read.
  - AMBIGUOUS and UNKNOWN never count as satisfied.

## Answer in brief

1. **Required visual rows (wording):** none of F-030, F-254 or F-278 names a photograph.
   - F-254 does not mention lifestyle at all. Lifestyle comes only from F-030's "lifestyle/use".
   - The photographic requirement comes from **F-253**, which points to F-221 ("Every
     customer-facing listing image must independently pass a photographic-realism gate").
   - The owner's later ruling (spec 11 §13, recorded as D-FB-7 and D-FB-9) lets disclosed
     deterministic imagery launch if it passes the truth gates.
2. **What a photograph or photoreal reference is still needed for:**
   - **Definitely unsatisfied:** LIFESTYLE/use on the 7 products where it applies (not the
     ornaments).
   - **AMBIGUOUS, so also unsatisfied until ruled:**
     - F-030 "category-specific proof" (all 8);
     - F-030 "texture", where it means yarn or material texture (all 8);
     - the literal F-221/F-253 realism floor (all 8);
     - **every image role on all 8**, if Etsy's Listing Image Requirements policy forbids
       renderings for digital-pattern listings. That page could not be read (403).
3. **Ornament gaps that do not need a photograph:** nordic-star-ornaments is missing ANGLE and
   CONSTRUCTION. Neither needs a photograph; both are engineering or mapping gaps.
4. **A qualified photoreal reference from the CIR: NO-GO.** This holds for launch and also for a
   pilot that has no physical sample.
   - The yarn-level twin refuses whole-product construction for **8 of 8** products (measured,
     §5.2).
   - `twin.calibrated` can only become True from a measured physical sample.
   - The only photoreal evidence so far is a 25-stitch swatch with 7 UNKNOWN realism items.
5. **Smallest credible resolution:**
   - A real photograph of a physically made sample, **in use, in a real room**, taken by the
     owner or a tester.
   - It goes through `physical_upgrade.intake` with `rights_basis=brambleloop_made`.
   - It needs no generated background, no new provider and no spend beyond the yarn.
   - One small wiring gap must be closed first (§6, E-A).
   - Start with hexagon-coaster-set.

---

## 1. The criteria, verbatim

Page numbers are PDF page numbers, read with `pdftotext -layout -f N -l N`. The ledger takes its
text from spec 09 (`master_registry.json` → `source.pdf`). Spec 10 (v1.1) repeats these rows
word for word on the same pages (checked for F-030, F-253, F-254 and F-278).

### F-030 (Gallery Information Architecture)

Spec 09 `09_Brambleloop_FINAL_Master_v1.0_Audited.pdf`, **p. 2**, §"2. FINAL-UPGRADE
REQUIREMENTS" (v0.1), priority P0-before-launch:

> **F-030 Gallery Information Architecture** — "Use later frames for angles, detail, texture,
> scale, lifestyle/use, sizing, inclusions and category-specific proof."

### F-254 (Gallery Information Architecture, v0.8)

Spec 09, **p. 21**, §"30. CLICK-THROUGH / CONVERSION" (continued from p. 20),
addendum-P0-launch-critical:

> **F-254 Gallery Information Architecture** — "Gallery frames have jobs: hero, useful alternate
> angle, stitch/motif detail, scale/context, construction detail, colour context and fit/worn
> views where applicable."

### F-253 (Natural Photo + Product Truth)

Spec 09, **p. 20**, §"30. CLICK-THROUGH / CONVERSION":

> **F-253 Natural Photo + Product Truth** — "Final Master F-221-F-232 applies to every gallery:
> natural photographic realism and exact pattern/product fidelity are independent hard gates."

The rows it incorporates are on spec 09, **p. 18**, §"26. NATURAL LISTING IMAGE HARDENING"
(v0.7 addendum). Only the ones that decide a role are quoted:

> **F-221 Photographic Realism Hard Floor** — "Every customer-facing listing image must
> independently pass a photographic-realism gate. The target is a believable high-quality
> photograph of a real crochet product in a plausible environment, not merely attractive
> generated art. Obvious synthetic/AI appearance blocks release."
>
> **F-225 Gallery-as-Real-Photo-Shoot** — "A listing gallery must read as one coherent,
> believable photo shoot rather than unrelated generated hero images. Where relevant include
> hero, useful alternate angles, scale/context, construction/detail close-ups and worn/fit views.
> Maintain consistent product identity, materials, colour and construction across frames."
>
> **F-227 Product Truth Outranks Beauty** — "… The pictured object must agree with the certified
> pattern/CIR/digital twin on visually material construction: stitch structure, motif, repeat
> geometry, shaping, seams/joins, edging, dimensions, colour placement, drape and garment fit. …"
>
> **F-230 Unreadable Is Not Pass** — "… Customer-facing release cannot treat absence of evidence
> as a pass."
>
> **F-232 Generated-Content Disclosure Integrity** — "Generated-image disclosure requirements
> remain authoritative. Photographic realism must never be achieved by concealing a material
> fact, fabricating proof, or representing generated imagery as real-world evidence when
> platform rules or Brambleloop policy require disclosure."

The section's acceptance tests are on spec 09, **p. 19**, §"27. REQUIRED ACCEPTANCE TESTS".
One of them is relevant:

> "Generated-content disclosure MUST remain correct even when the image is sufficiently realistic
> that a viewer could mistake it for a photograph."

### F-278 (Hero Thumbnail Tournament)

Spec 09, **p. 21**, §"32. LAUNCH / SEASONAL ORCHESTRATION":

> **F-278 Hero Thumbnail Tournament** — "Challenge first-photo candidates at Etsy-like
> thumbnail/mobile size; select for truthful clarity and click appeal, not full-resolution
> beauty."

### The owner's later ruling, which governs how F-221/F-253 apply at launch

Spec 11 `11_Final_Build_v1.1_Master_Prompt.pdf`, **p. 3**, §"13. VISUAL OWNER RULING":

> "Photorealistic Visual V2 is NOT intrinsically required for first launch. TRUTHFUL
> CUSTOMER-READY VISUAL EVIDENCE IS LAUNCH-CRITICAL.
> Rendered/deterministic imagery may launch only when the actual customer-facing set passes
> Product Truth, stitch/fabric identity, dimensions/features/construction consistency, image QA,
> mobile/thumbnail-safe layout, disclosure, marketplace/publishing and customer-truth gates.
> Disclosure alone cannot make inaccurate imagery acceptable. Do not weaken Product Truth or
> Visual thresholds. Preserve B+C as the preferred Visual V2 architecture."

The repository recorded this ruling twice:

- **D-FB-7** (`DECISION_LOG.md:1350`) records it.
- **D-FB-9** (`DECISION_LOG.md:1370`) applies it: "a disclosed deterministic render states that
  it is not a photograph, so the photographic-realism judgement of F-221 / F-229(B) / F-856
  cannot meaningfully apply to it".

### Build 2 rows that map onto these roles

Spec 08 `08_Brambleloop_Queued_Upgrades_v1.4.3_MASTER.pdf`; text as in `requirements.json`:

| # | Page, version | Words that matter here |
|---|---|---|
| 35 | p. 7, v1.3.2 | "AI use must be disclosed where required. … Never assume an AI-generated lifestyle image satisfies Etsy's listing-image requirements." |
| 36 | p. 7, v1.3.2 | "For patterns, prioritize real tester/customer finished-project photography as soon as available. … If current Etsy policy requires seller-owned photos/video or restricts renderings for the relevant listing class, the Policy Gate blocks incompatible assets." |
| 57 | p. 10, v1.3.3 | "A technically correct chart cannot be promoted to hero/listing creative merely because it rendered successfully." |
| 62 | p. 10, v1.3.3 | "The hero's job is desire and instant comprehension … while remaining truthful and policy-compliant." |
| 64 | p. 10, v1.3.3 | "For products initially marketed with permitted non-physical representations, create an automatic upgrade task when tester/customer physical photography becomes available." |
| 65 | p. 10, v1.3.3 | "Every frame has exactly one primary commercial job: DESIRE, SCALE, DETAIL, CONTENTS, DIFFICULTY, MATERIALS, SIZING, PATTERN_PREVIEW, PROOF or CROSS_SELL." |
| 69 | p. 11, v1.3.3 | "distinguish a digital pattern render/chart from a photograph of a physically completed object … Do not use a disclaimer as permission to make a misleading hero" |
| 75 | p. 12, v1.3.4 | "(5) LIFESTYLE QUALITY - premium lighting/composition/material realism" |
| 78 | p. 12, v1.3.4 | "Hero/lifestyle frames sell the truthful finished outcome; later evidence frames prove dimensions, chart quality, materials, included files and support." |

**Finding:**

- Build 2 #64 says "products initially marketed with permitted non-physical representations".
  The Build 2 spec therefore expects listings to launch on non-photographic imagery and to be
  upgraded later.
- No Build 2 row says a gallery must contain a photograph before launch.
- The only "must" that rests on Etsy is conditional ("If current Etsy policy requires …", #36),
  and that condition is UNKNOWN (§3).

## 2. Roles × "can a truthful, disclosed informational illustration satisfy it?"

"Disclosed illustration" means the existing certified frames:

- `disclosed_render` hero, scale and detail;
- `gallery_frames` MATERIALS, COLOUR_CONTEXT, CONSTRUCTION and SIZING;
- the vessel angle view;
- `contents_frame`.

Each carries `render_contract.DISCLOSURE` in its pixels, and each is verified on its bytes
against the CIR.

| Role (code job) | Required by | Satisfiable by disclosed illustration? | Deciding words |
|---|---|---|---|
| Hero / thumbnail (DESIRE) | F-254 "hero"; F-278 | **YES** | F-254 names no medium. F-278: "select for truthful clarity and click appeal, not full-resolution beauty". "First-photo" is Etsy's own word for any listing image: its help article says "We recommend your listing photos …" about every image (§3). HEROTOURNEY already supplies ≥2 verified disclosed candidates. **F-278's blocker is the funded vision judge (`image_vision`), not the medium.** |
| Alternate angle (ANGLE) | F-030 "angles"; F-254 "useful alternate angle … where applicable" | **YES** for vessels: a verified 50° disclosed angle exists for both baskets products. **Not applicable** to flat pieces ("useful"; a flat piece's back is its front). | "useful", "where applicable" |
| Stitch/motif detail (DETAIL) | F-030 "detail"; F-254 "stitch/motif detail" | **YES** | The stitch and motif are CIR facts. `render_verification` re-measures them. |
| Texture | F-030 "texture" | **AMBIGUOUS** | Stitch-relief texture is a CIR fact, so YES. Yarn or material texture (fibre, fuzz, sheen) is not in the CIR, and F-223 counts "fake-looking yarn" as a defect, so a drawing cannot show it: NO. The word does not say which is meant. |
| Scale (SCALE) | F-030 "scale"; F-254 "scale/context" | **YES** for scale. **AMBIGUOUS** for "context". | The size card draws the CIR dimensions against a named everyday reference. "Context" can mean that reference (YES) or a room setting (same question as lifestyle). |
| Lifestyle / use (LIFESTYLE) | F-030 "lifestyle/use" only (F-254 does not list it) | **AMBIGUOUS** | F-030 names no medium. However: F-221 targets "a believable high-quality photograph of a real crochet product in a plausible environment"; #78 says "Hero/lifestyle frames sell the truthful finished outcome"; spec 11 §13 says "Disclosure alone cannot make inaccurate imagery acceptable". The repository's own reading is NO (`gallery_frames.NOT_DRAWABLE["LIFESTYLE"]`: "a room scene is a claim about a physical object in a place"). A disclosed, scale-true *use diagram* has never been ruled on. |
| Sizing (SIZING) | F-030 "sizing" | **YES** | Every size outline is drawn to one scale from the CIR (applies to the nesting baskets). |
| Inclusions (CONTENTS) | F-030 "inclusions" | **YES** | `contents_frame` shows pages of the certified PDF itself, which is the thing sold. The board records CONTENTS as certified on every renderable release. This branch did not re-verify that on production. |
| Category-specific proof (PROOF?) | F-030 "category-specific proof" | **AMBIGUOUS** | "Proof" is undefined. Build 2 #65 defines PROOF; the code's gloss is "that somebody has made this and it worked" (`eligibility.JOBS`), and the code lets only PHYSICAL_PROOF do it. If F-030 means that, the answer is **NO**. If it means category facts (dimensions, piece count), the existing frames already do it. **Mapping gap:** `gallery_jobs_for` never requires PROOF, so F-030's word is not enforced anywhere. |
| Construction detail (CONSTRUCTION) | F-254 | **YES** | The stitch-count profile per round or row is a CIR fact. Ornaments have no producer yet (§4), which is an engineering gap, not a medium question. |
| Colour context (COLOUR_CONTEXT) | F-254 | **YES** | Each colour's share is counted from the compiled pattern. It does not prove how real yarn looks on screen. The code's gloss "or in a room" is wider than the words "colour context". |
| Fit / worn | F-254 "where applicable"; F-225 | **NO**, but **not applicable** to any of the 8 products | `JOB_PURPOSES[FIT] = (PHYSICAL_PROOF,)`. None of the 8 products is worn. |
| Photographic realism floor | F-253 → F-221, F-225 | **NO** on the literal text. **Superseded for launch** by spec 11 §13 / D-FB-7 / D-FB-9. | F-221: "Every customer-facing listing image must independently pass a photographic-realism gate." §13: "Rendered/deterministic imagery may launch only when …". The owner's later ruling governs. This needs no new owner action, but F-253 cannot be *closed as written* by disclosed frames. It can only be closed as "not applicable to disclosed frames, per D-FB-9", and that disposition is the integrator's call, not mine. |

## 3. Etsy rules (read 2026-10-19 UTC)

### Method

- **Help Center (readable).** Etsy Help Center HTML returns 403 to automated clients, but its
  public article API (`https://help.etsy.com/api/v2/help_center/en-us/articles/<id>.json`)
  returned **HTTP 200**. That is the method `w3/ETSY_REQUIREMENTS.md` already uses.
- **Legal policy and Seller Handbook pages (not readable).** These returned **HTTP 403** to both
  curl and WebFetch:
  - [Listing Image Requirements](https://www.etsy.com/legal/policy/listing-image-requirements/253962679005);
  - [Creativity Standards](https://www.etsy.com/legal/creativity/);
  - `etsy.com/help/article/6128`;
  - the Seller Handbook.

  This is DataDome, as recorded before. Getting past it would be evasion, so I did not try.

### What Etsy's own text says (quoted, read 2026-10-19)

| Source (Etsy's `edited_at`) | Quote | Bearing |
|---|---|---|
| [What Can I Sell on Etsy?](https://help.etsy.com/hc/en-us/articles/360024112614) (2025-09-17) | Under **"Made by a seller"** (physical items): "Use your own photographs in your listings". Under **"Designed by a seller"**: "you can offer your original design as a digital download … This category also includes seller-prompted AI creations. … Seller-prompted AI creations must disclose the use of AI." Also: "The images you use in your listings must also comply with our Listing Image Requirements." | The own-photographs line sits under *physical* made items, not under digital designs. The AI disclosure concerns *AI creations*. Deterministic renders are not generated by AI. A generated background would be. |
| [How to Create a Listing](https://help.etsy.com/hc/en-us/articles/115015628707) (2026-06-29) | "Handmade items are items that are made and/or designed by you, the seller. If you sell handmade items, you must: … Use your own photographs in your listings." | This uses the older framing and **does include "designed"**. It conflicts with the article above. "Own photographs" may mean images you own (not stock or another seller's), or camera photographs. **AMBIGUOUS.** |
| [Requirements and Best Practices for Images](https://help.etsy.com/hc/en-us/articles/115015663347) (2026-05-04) | "We recommend your listing photos have a width and height of at least 2000 pixels"; "The first photo in a listing should be horizontal (landscape) or square"; "transparent parts of the image will appear black". | Technical rules only. It calls every listing image a "photo" and sets no rule on medium. |
| [How to Add a Text Alternative](https://help.etsy.com/hc/en-us/articles/4406604492823) (2024-12-10) | "If you don't provide a text alternative … Etsy will automatically add a description to your listing using AI generated text." | Not a rule on images; it supports keeping our own alt text, which D-FB-9 already requires. |

### Not read; attributed only by search engines (UNVERIFIED, not used as policy)

- **Search-tool summary of the 403 policy page.** WebSearch, 2026-10-19, `site:etsy.com`,
  summarised the 403 Listing Image Requirements page as saying sellers must "use original photos
  of the actual product buyers will receive, not renderings or stock photos, except in the
  situations outlined below". The summary also said:
  - personalised items' first image must be a finished item, not a placeholder mockup;
  - mockups may appear in later images;
  - production-partner items have stock-mockup exceptions.

  It reported the page's metadata as about 832 days old.
- **Why it is not policy here.** I could not read the page, so I cannot confirm the wording, the
  date, or **whether digital downloads (patterns) are an exception**.
- **Why it matters.** For a digital pattern, "the actual product buyers will receive" is the PDF.
  On that reading the CONTENTS frame is the literal product, and a photograph of a finished
  blanket is not.
- **Third-party blogs.** Sources such as
  [listadum](https://www.listadum.com/blog/should-you-disclose-mockups-and-ai-images-in-your-etsy-listings)
  and [neural4d](https://blog.neural4d.com/?p=2741) claim the first image must be an original
  photo. They disagree with each other and are **not evidence**. `w3/handoff_C.md:52` reached
  the same conclusion on 2026-10-06.

### Answers to the three questions

1. **Does Etsy require photographs?**
   - For physical made items: **yes** (Etsy text, quoted).
   - For digital patterns: **UNKNOWN**. Two current Help articles disagree, and the binding
     legal page is unreadable.
2. **Are illustrations or mockups allowed for digital patterns?** **UNKNOWN.** No readable Etsy
   text allows or forbids them.
3. **Does AI-generated imagery need disclosure?** "Seller-prompted AI creations must disclose
   the use of AI" (read). No readable Etsy text sets a separate rule for AI-generated *listing
   images*. Brambleloop's own rule is stricter and stays in force: B-097, F-232 and spec 09
   §27 require any generated image to be disclosed and never to be the hero.

**Consequence.** Until a person reads the Listing Image Requirements page in a browser,
"disclosed renders are acceptable listing images on Etsy for a digital pattern" is
**UNKNOWN**. Under Build 2 #36 the Policy Gate must then hold any incompatible class. This is
the single largest unread risk in the visual lane. It affects every role on every product, not
just LIFESTYLE.

## 4. Roles still unsatisfied without a photographic or photoreal reference, per product

The applicable jobs and current coverage come from a local
`visual.launch_imagery.assemble_all()` run on this branch (2026-10-19). It used the certified
CIRs and deterministic tooling only; no network.

- CONTENTS shows as missing locally only because no `assets.built` PDF record exists offline.
  The production board records it as certified, so it is not listed below.
- "Definite" means unsatisfied under every reading. "Conditional" means AMBIGUOUS or UNKNOWN,
  which counts as unsatisfied until it is ruled on.

| Product | Definite (needs a photo, or a photoreal reference that does not exist) | Conditional (AMBIGUOUS / UNKNOWN) | Gaps that need no photograph |
|---|---|---|---|
| nursery-nesting-baskets | LIFESTYLE | proof, yarn texture, F-221 literal, Etsy medium rule | none (ANGLE, CONSTRUCTION, SIZING covered) |
| cloudline-baby-blanket | LIFESTYLE | same four | none |
| hexagon-coaster-set | LIFESTYLE | same four | none |
| nordic-star-ornaments | none (LIFESTYLE is not applicable) | same four | **ANGLE**: refused because "a flat piece's back is its front". F-254's "useful … where applicable" supports marking it not applicable, but `_THREE_D` includes `ornament`. **CONSTRUCTION**: "no truthful producer for this job yet"; the flat-row profile is not drawn for this category. |
| winter-village-graphghan | LIFESTYLE | same four | none |
| nordic-forest-mosaic-throw-baby | LIFESTYLE | same four | none |
| mosaic-placemat-pair | LIFESTYLE | same four | none |
| housewarming-key-basket | LIFESTYLE | same four | none |

**The exact list.**

- **LIFESTYLE/use** remains unsatisfied on 7 products: every product except
  nordic-star-ornaments.
- **Category-specific proof** and **yarn texture** remain AMBIGUOUS on all 8.
- **Every role on all 8** is conditional on the Etsy listing-image rule (UNKNOWN).
- **F-278** is not a photo gap. Its block is the funded vision judge.

## 5. Can a qualified photoreal digital reference be produced from the CIR?

### 5.1 What "qualified" means in the code and gates today

- **Qualified producers.** `product_authority.QUALIFIED_RENDERERS` contains only
  `disclosed-render/2.0.0` and `disclosed-render-assembled/1.0.0`. "Qualification is of a
  producer/verifier pair" (`product_authority.py:13-18`).
- **No photoreal producer is qualified.** Every other frame ends at
  `'no qualified whole-product construction/gauge evidence producer'` → UNKNOWN
  (`product_authority.py:181`).
- **Generative redraw is prohibited.** F-852 prohibits generative product redraw
  (`redraw_refusal`). A photoreal reference therefore has to be *rendered* from geometry, not
  generated.
- **What qualifying a new photoreal renderer would take:**
  1. **Whole-product yarn-level geometry from the CIR.** This is `visual.crochet_topology` →
     `drape` → `pbr_scene` (Mitsuba, lazily imported).
  2. **An independent verifier pair** that measures the rendered product against the CIR, as
     `render_verification` does for the disclosed renders.
  3. **Agreement with F-227** on "dimensions, colour placement, drape". Today's solver
     constants are not calibrated: `drape.py:94` says "the honest status of B is BOUNDED and
     CONDITIONED, not calibrated".
  4. **Calibration.**
     - `TwinModel.calibrated` is True only when `calibration != 1.0` (`cir/twin.py:259`).
     - Per `quality/physical.py`, that factor comes only from a measured sample: "This is the
       one input that is measured, and it is the only thing that can turn an estimate into a
       figure. … A sample is never assumed."
  5. **The realism judgement**, for example Milestone D's 7 photograph items. These need a
     paid vision judge (VISUAL_STATUS plan P1, CA$1.00).
  6. **Comparison against real views.** The owner study, p. "Lane 2", says to "Compare the twin
     against withheld real views before accepting it".

**Can it be qualified without any physical sample?** **No.**

- Items 3, 4 and 6 each need measurements of a real worked object.
- The code has no other path that sets `calibrated`, and the owner study names withheld real
  views as the acceptance test.
- Manufacturer yarn photographs could inform shading. They are not our sample, though, and
  cannot settle size, drape or the hook-and-gauge texture of this pattern.

### 5.2 What exists, measured on this branch

**Probe 1: can the yarn-level twin build each whole product?** I called
`crochet_topology.build(build_twin(cir, compile_cir(cir)), cir.gauge)` on each product's
certified CIR.

| Product | Total stitches (compiled, per piece type) | Yarn-level build |
|---|---|---|
| nursery-nesting-baskets | 1050 / 2262 / 3888 (S/M/L) | **REFUSED**: `UnmodelledConstruction`, worked in the round (`shape='vessel'`) |
| cloudline-baby-blanket | 9900 | **REFUSED** at row 7: `UnmodelledStitch` 'dc'. The first 4 rows build. |
| hexagon-coaster-set | 168 ×4 pieces | **REFUSED**: in the round (`shape='disc'`) |
| nordic-star-ornaments | 144 ×6 | **REFUSED**: 'dc' at row 2 |
| winter-village-graphghan | 11664 | **REFUSED**: 'dc' at row 2 |
| nordic-forest-mosaic-throw-baby | 5184 | **REFUSED**: 'dc' at row 2 |
| mosaic-placemat-pair | 1728 ×2 | **REFUSED**: 'dc' at row 2 |
| housewarming-key-basket | 1332 | **REFUSED**: in the round (`shape='vessel'`) |

`STITCH_KINDS = ("sc", "hdc")` and flat rows only (`crochet_topology.py:233`, `:646`). The
refusals are by design: "Refused, never substituted".

**8 of 8 products cannot be built** at yarn level today.

**Probe 2: renderer availability.** `import mitsuba` fails in `brambleloop/.venv`
(`ModuleNotFoundError`). The machine has 4 CPUs and no GPU.

**Prior evidence:**

- **Milestone D** is PARTIAL on a **25-stitch hdc swatch**: 12 PASS, 0 FAIL, 7 UNKNOWN. All 7
  UNKNOWNs are paid photograph judgements. One run took **768.8 s** (4000 settle iterations,
  spp 32; `w4/visual/milestone_d_hdc_2026-10-07.json`).
- **Wave 4** found a load-independent instability in the solver (`VISUAL_WAVE4.md`).
- **E3/E4** (swatches; generative presentation over a deterministic reference) ended
  "**E4 FAIL as a pipeline**". Structural yield was 2/14; spend US$0.60.
- **Bench1** produced one passing photoreal hero of 12 draws (US$3.45). Bench2 had no
  certified hero (US$1.83). Both are generative, which F-852 now prohibits for product redraw.
- **The CIR cannot express per-stitch colour** (`launch0.per_stitch_colour_expressible() is
  False`). Mosaic and graphghan fabrics are one colour per row.

### 5.3 Bounded estimate (ESTIMATES, not measurements)

| Item | Estimate | Basis |
|---|---|---|
| Engineering to reach a whole-product yarn render for the *simplest* product (hexagon coaster: sc + inc, in the round, 168 stitches) | **80–200 h** | New in-the-round topology (rings, increases, joins, closure) plus self-contact for a disc. The new geometry must pass the existing validators (morphology, linkage) and needs a new pixel verifier pair. For scale: sc/hdc flat swatches took Waves 1–5, E1–E5 and Milestone D, many sessions across 2026-09-2x. |
| Each further stitch family ('dc', raised/relief dc, 'slst') | **+40–120 h each** | Each family needs a cell model with its own linkage checks, as sc and hdc did. |
| Compute per qualified render (4 CPU, no GPU) | Coaster: about 1.5 h per piece-run. Graphghan: about 100 h. | **Linear extrapolation** from 768.8 s / 25 stitches. Unmeasured; the solver's measured instability makes linear optimistic. |
| Cash | CA$0 compute (local). CA$1.00 judge (P1). Mitsuba install is free. | VISUAL_STATUS paid plans |
| **Qualification** | **Not reachable without a sample** | §5.1 items 3, 4 and 6 |
| **Main risk** | 100–300 h of work that still ends **UNKNOWN**, because the gates that would qualify it need the physical sample this route was meant to avoid. | |

### 5.4 Verdict: **NO-GO**

- **For launch: NO-GO.** No product can be built (8/8 refused). No qualification route exists
  without a sample.
- **For a pilot without a sample: NO-GO.** It cannot pass the qualification it would be piloting.
- **For a one-product pilot after a coaster sample exists:** this is a legitimate *research*
  option (Visual V2, B+C) at the 80–200 h estimate. It is **not a launch path**, because by then
  the sample's own photographs already satisfy the role.

### 5.5 Against the alternative: physical samples

| | Photoreal from CIR | One physical sample per product | Samples only where a role needs one |
|---|---|---|---|
| Products needing work | 8 (and 8/8 cannot be built today) | 8 | **7** (LIFESTYLE): every product except ornaments. **1** if the conditional roles are ruled not to need a photo and LIFESTYLE is started on the coasters. |
| Closes LIFESTYLE truthfully | Only after qualification, which itself needs a sample | Yes: a camera photo of the object in use is a `PHYSICAL_PRODUCT_PHOTO`, and `JOB_PURPOSES[LIFESTYLE]` includes PHYSICAL_PROOF | Yes, per product |
| Also settles | nothing extra | yarn texture, "proof", size falsification (`physical.SIZE_DISAGREEMENT`), `twin.calibrated`, and the Etsy reading "own photographs" | the same, for the products sampled |
| Owner cost | 0 cash, 100–300 h engineering, still UNKNOWN | yarn plus maker time (below) | the subset of that |
| Engineering | large | small (§6 E-A, E-B) | small |

**Rough maker-time ESTIMATES** (stitch counts from the compile above; not measured):

- hexagon coasters ×4 (672 stitches): about 2 h;
- key basket (1332): about 2 h;
- ornaments ×6 (864): about 2–3 h;
- baskets S/M/L (7200): about 6–9 h;
- placemats ×2 (3456): about 4–6 h;
- mosaic baby throw (5184): about 6–10 h;
- cloudline blanket (9900): about 10–16 h;
- graphghan (11664 plus colour changes): about 14–20 h.

Yarn is roughly CA$10 to CA$15 for the coasters and a few tens of dollars for each blanket.
Neither cost was verified against a supplier.

## 6. Smallest credible resolution for each remaining visual launch blocker

| Blocker | Smallest credible resolution | Who | Cost / time | Depends on |
|---|---|---|---|---|
| **V1. Etsy medium rule unread (affects all 8, all roles)** | A person opens the [Listing Image Requirements](https://www.etsy.com/legal/policy/listing-image-requirements/253962679005) and [Creativity Standards](https://www.etsy.com/legal/creativity/) pages in a browser and records, with the date, whether *digital downloads / patterns* may use renderings or illustrations, and in which positions. Alternatively, ask Etsy support. Record the result in `integrations.etsy_constraints`. | **OWNER ACTION REQUIRED** (a human browser read; automated access is blocked and must not be evaded) | CA$0, about 10 min. **If not done:** every disclosed listing image stays UNKNOWN under #36. | none |
| **V2. LIFESTYLE on 7 products** | A **real photograph of a made sample in use in a real room**, with no generated background. Start with **hexagon-coaster-set**: 4 coasters under or next to a mug on a table, daylight, all 4 visible. Add top-down and macro views for construction review, as VISREF §5 describes. Intake through `physical_upgrade.intake(rights_basis="brambleloop_made")`. Expand product by product: baskets, then blankets. | **OWNER ACTION REQUIRED** (physical: make and photograph) | Yarn about CA$10–15; about 2 h to make and 30 min to photograph for the coasters (ESTIMATE). **If not done:** F-030 LIFESTYLE stays open on 7 products and `search_evidence` reads the gallery architecture as FAIL. | E-A below |
| **E-A (engineering, offline). The photo path cannot yet do LIFESTYLE** | `plan_upgrade` adds the photograph with `role="proof"` (`physical_upgrade.py`). `release_gates.ROLE_JOBS` has no `"proof"` (or `"lifestyle"`) role, so such a frame is classed as "filler" (`release_gates.py:452-455`). This was read from code, not exercised. Fix: let intake declare the frame's job (PROOF, LIFESTYLE, DETAIL or SCALE), map it in `ROLE_JOBS`, and count a camera LIFESTYLE frame in `launch_imagery` coverage. A physical photo also needs the photographic VISROLE review and construction review against the CIR (VISREF E1). **Coordinate with W-PRODREADY, which owns `listing_assets.py`.** | next engineering lane | about 4–8 h with tests | none (testable with fixtures) |
| **E-B. The recorded owner action is mis-specified** | Replace the F-030/F-254 `visual_paid_generation` P2 action ("flux-2-pro protected composites", CA$2.00) with V2. As VISREF §0 found, P2 would paste a captioned diagram into a room. | integrator | 0 | none |
| **V3. Category-specific proof and yarn texture (AMBIGUOUS, all 8)** | An owner or integrator ruling on what F-030 "category-specific proof" and "texture" mean for Launch-0. The minimal truthful reading: dimensions and piece count (proof) and stitch relief (texture) are met by the disclosed frames; yarn texture and "somebody made it" are met by the V2 sample photo when it exists. Record it as a D-record. **Not** closed by re-classifying the row. | owner or integrator (decision) | 0 | none |
| **V4. F-253 / F-221 literal realism floor** | No new action is needed for launch. Spec 11 §13 plus D-FB-7/D-FB-9 already govern disclosed frames. F-253 should be shown as "not applicable to disclosed frames (D-FB-9); applies to the first photographic frame". Photographic frames (V2 photos) keep the full realism review. | integrator (row disposition) | 0 | none |
| **V5. nordic-star-ornaments ANGLE and CONSTRUCTION** | No photograph. (a) ANGLE: make applicability follow geometry (a flat piece's back is its front), not the category name; `_THREE_D` includes `ornament`, but this product is 6 flat panels. Record it as a decision; F-254 "useful … where applicable" supports it. (b) CONSTRUCTION: extend `gallery_frames` CONSTRUCTION's per-row stitch-count profile to flat multi-piece panels, verified the same way. | next engineering lane | about 3–6 h with tests | none |
| **V6. F-278 hero tournament** | Not a medium problem: HEROTOURNEY already has ≥2 verified disclosed candidates per product. Fund the vision judge (`image_vision` gate), then re-run the 230/340 px judgement on production. | **OWNER ACTION REQUIRED** (credential and funding) | Existing V0 plan, CA$0.75 max | none |
| **V7. Photoreal-from-CIR** | **Do not pursue for launch** (§5.4). Leave it in Visual V2 R&D. Reconsider only once a coaster sample exists, as a research pilot against withheld real views. | — | — | V2 |

**Owner batch, if the integrator surfaces it:**

1. **V1, read the Etsy policy pages.**
   - Why: it decides whether any disclosed image may be used.
   - Cost: CA$0, about 10 min.
   - If it waits: every image class stays UNKNOWN.
2. **V2, make and photograph the hexagon-coaster set in use.**
   - Why: it is the only truthful LIFESTYLE source.
   - Cost: about CA$15, about 2.5 h.
   - If it waits: LIFESTYLE stays open on 7 products.
3. **V6, fund the vision judge.**
   - Why: it unblocks F-278 and the HERO judgements.
   - Cost: at most CA$0.75.
   - If it waits: the tournament stays unjudged and publishing stays blocked.

## 7. Verification of this note

- Every verbatim quote was re-extracted from the PDF page cited.
- Etsy quotes were read on 2026-10-19 through the Help Center article API, with Etsy's
  `edited_at` dates shown.
- The coverage, stitch-count and topology probes are local, deterministic and shadow-only. The
  probe scripts were kept out of the repository.
- No source file was changed. The required regression set was run on this branch through
  testslot on 2026-10-19, and every suite exited 0:
  - test_vacuity: OK;
  - test_search_hero_publish: 4/4;
  - test_cert_listing_frames: 0 failing;
  - test_cost_governance_wave2: OK;
  - test_v11_autonomy_timeline: 0 failing;
  - test_launch: OK.
