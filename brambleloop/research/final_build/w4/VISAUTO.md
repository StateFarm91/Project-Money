# VISAUTO: visual-autonomy integration, and the Laura wardrobe-diversity fix

- **Branch:** `claude/w4-VISAUTO`. It starts from OWNERIMG c387c27 and merges W-FLUXAPI d3679fe.
  OWNERIMG's design and reuse survey stay in `OWNERIMG.md`.
- **Scope:** offline and SHADOW only. No paid calls were made, nothing was deployed, and no
  credential or release-candidate branch was touched.

## Step 0: integration (checkpoint 56691f84)

- **Failure codes have one home.** `creative/failure_codes.py` (W-FLUXAPI) is the only
  definition. `repair_routes.shared_codes()` reads it, and `ROUTES` is keyed by its constants.
- **The orchestrator uses FLUX 3.** `image_production.resolve_generator` registers
  `creative.flux3_generator.Flux3Generator` on first use.
- **A paid call is still refused.** `Flux3Generator.paid` is True for the real renderer. While
  `image_generation` is closed, the run stops at
  `blocked(image_generation gate closed: a paid generator may not be called)`. That outcome has
  zero calls, zero spend and no owner notification: it is a capability block, not a failed
  attempt. Tested in `test_default_generator_is_flux3_and_refused_while_the_gate_is_closed`.
- **Generator refusals are recorded.** A `GeneratorRefused` or `StageRefused` from the generator
  becomes a recorded block instead of a crashed job.

## Step 1: the wardrobe fix

**The owner's evidence.** FLUX carried the beige trousers and ivory top from the canonical body
references into the lifestyle frames. Outfits also differed only by the shirt.

| Part | Implementation |
|---|---|
| a. Prompt | `flux_prompt` identity is now **v2** (v1 is still registered and immutable). It states that the three references fix identity and anatomy ONLY, never clothing. It says "Preserve face, bust fullness and projection, shoulders, waist, hips, legs and silhouette exactly". It says "REPLACE ALL clothing from the reference images with the selected outfit: <top/dress; bottoms; footwear; outerwear; accessories>; do not reuse the reference beige trousers, ivory/cream tops or tan sandals". A new CIR-independent section, `image.flux3.reference_clothing`, reads "LAURA MUST NOT WEAR: …". A Laura prompt with no outfit is refused. `Flux3Generator` now passes the garments through. |
| b. Selector | `visual/styling.py` v2 draws from `visual/wardrobe.py` `CATALOGUE`: fitted tops, cardigans, jumpers, shirts, blouses, dresses, jeans, skirts, tailored and casual trousers, boots, loafers, sneakers, flats, clogs, coats, vests, blazers, shawls and accessories. It filters by season and ranks by product formality. It skips any garment that clashes with the product's colours. `REFERENCE_OUTFIT` is always treated as already used. |
| c. Diversity | `wardrobe.similarity` is a weighted per-slot score: top 0.25, lower 0.30, shoes 0.20, outerwear 0.15, accessories 0.10. Each slot scores category 0.5, colour 0.3 (family match 0.6) and distinctive features 0.2. `MAX_SIMILARITY` is 0.60. A shirt-only change with the same trousers and shoes scores 0.75 or more and is rejected. No colour or category is banned: two jeans outfits that differ elsewhere pass. When the first choice is too similar, the selector moves to the next one automatically. |
| d. QA | `outfits.reserve` FAILs with `WARDROBE_REPETITION` when the outfit is too similar to an outfit another listing holds, or to the reference clothing. New gate check `outfit_distinctness` is deterministic. `outfit_consistency` covers all five slots and needs the vision judge, so it reads UNKNOWN until that judge is funded. `canonical.LAURA_LISTING_GATES` now has 11 gates. Shared codes `WARDROBE_REPETITION` and `REFERENCE_CLOTHING_CARRYOVER` are in `failure_codes.WARDROBE_CODES`, and `EVERY_CODE` is the union of both code sets. Repair routes: carryover gets the stronger replace-clothing negatives; repetition re-picks the outfit (`_repick_outfit`: styling with the old outfit excluded, then `outfits.replace`, and the old outfit stays retired on its listing). A wardrobe failure blocks the image and the owner card, while every other check still runs. |
| e. Tests | All in `tests/test_w4_ownerimg.py`, 35/35: reference clothing never copied (prompt and selector, all 8 listings); shirt-only change rejected, with no garment banned; complete outfits distinct across all 8 listings (28 pairs below 0.60, at least 3 lower-garment categories); one outfit per listing; identity and proportion protection kept; reservations survive a new engine and a separate process; wardrobe failures route to repairs and block approval; scarf history. |

## Step 2: the scarf experiment

- **Record:** `research/final_build/w4/flux_experiments/2026-10-19_chunky_ribbed_scarf/RECORD.json`.
  It is owner_manual and contains no image bytes.
- **Product status:** `chunky-ribbed-scarf` is UNCERTIFIED (uncalibrated fpdc/bpdc) and is not
  customer-ready.
- **Outfit:** dark indigo jeans, a black fitted top, a camel wool coat and brown leather boots.
- **Seeding:** `repair_routes.seed_experiments` seeds every experiment record, idempotently,
  once per run in stage 1. Each record produces two things:
  1. a learning row: method `owner_manual`, identity UNKNOWN, cost unknown, so cost per accepted
     image stays None;
  2. wardrobe history: outfit `owner-manual-<slug>` bound to the experiment's product. No other
     listing may reuse it.
- **Records seeded today:** the wrap and the scarf.

## Remaining work

The FLUX adapter (E1) is closed by the merge, and the restart and re-pick work is partly done.
Still open:

- vision-judge adapters (identity, body proportions, outfit consistency across 5 slots,
  anatomy, realism): 6–10 h;
- the deterministic fidelity verifier on the anchor, which another worker is building on 56691f84;
- restart of a blocked run: 1–2 h;
- writing approved frames to `ListingAsset` and re-certifying: 3–5 h;
- the outfit reference image: 1–2 h;
- a Command Center wardrobe editor: 2–4 h.

That is about 13–23 h plus the fidelity checker. The real paid end-to-end test is still a
proposal and needs owner approval (`OWNERIMG.md` §8).
