# ENG-WARDROBE-SCENES slice 1: review request (outfit library, scene library, prompt assembly, gallery planner)

- Branch: `eng/wardrobe-scenes`, created from `origin/claude/w6-INTEG3` @ `307c7e62`.
- The final SHA is the commit that adds this file. It is posted on issue #28, tagged `[ENG-WARDROBE-SCENES]`.
- Not deployed and not merged.
- Nothing touches Railway, production, secrets, Etsy writes, spend, `BRAMBLELOOP_PHASE` or `STAGE_A_ENABLED`.
- No image provider is called. `claude/repository-setup-nc9x6o` was not pushed to.
- **Only new files.** No existing module is edited (`outfits.py`, `wardrobe.py`, `shot_plans.py`, `laura_home.py`, `image_production.py` are all unchanged), so this slice cannot conflict with ENG-VIS-IDENTITY, ENG-VIS-GALLERY or ENG-LEARN.

## The owner's standard, and where each part is enforced

| Standard | Code |
|---|---|
| Laura's identity (laura-r2-a42aeac7) is locked | `prompt_assembly.IDENTITY_LOCK` is in every Laura frame. Outfits never name an identity feature (`outfits._IDENTITY_WORDS`). Hair is a closed list of arrangements; colour, length, cut and texture are never changed (`outfit_library.HAIR_STYLINGS`, `_HAIR_CHANGE`). |
| ONE complete outfit per listing, constant across its gallery | `outfit_library.claim_for_listing` goes through the durable `laura_outfits` reservation (`outfits.reserve`). `gallery_planner.check_gallery` refuses `more_than_one_outfit`, `laura_without_outfit` and `outfit_not_the_listing_claim`. |
| A DIFFERENT approved outfit for each new listing | A claim excludes every outfit another listing holds, and `outfits.reserve` refuses a reuse (FAIL). A retired outfit stays bound to its listing. All library outfits are pairwise below `wardrobe.MAX_SIMILARITY`. |
| The product is identical in every frame | `prompt_assembly.ProductRef.block()` is built from the certified CIR (title, release, fingerprint, pieces, exact yarn hexes). It is byte-identical in every frame, and `check_gallery` refuses `product_not_invariant`. A learned template can never change it. |
| Lifestyle scenes: attractive rooms, natural light, people, multiple environments | 59 scenes: 43 in the rooms of Laura's one home (D-W4-OWNER-LAURA-HOME architecture, verbatim) plus its porch, garden and craft room, and 16 outdoor scenes. There are 7 lightings and all 6 camera angles, at 35–100 mm with shallow, medium or deep depth of field. Every gallery needs at least `MIN_PLACES` = 3 places, and the planner reaches 5 where the library allows it. |
| Trustworthy presentation (the MJ half) | A flat-lay (overhead, deep depth of field) and a close-up (≥ 85 mm, shallow) are in every gallery, along with the CONTENTS frame from the certified PDF (never generated). |

## What was built

1. **`visual/outfit_library.py`: 63 outfits** (`LIBRARY_VERSION = outfit-library/1`).
   - **Each outfit has:**
     - a stable id (`wl-<key>`);
     - the five registry garment slots;
     - a hair arrangement;
     - a palette of named colours with sRGB values;
     - season tags (spring, summer, autumn, winter);
     - occasion tags (`OCCASIONS`);
     - a formality;
     - a text spec.
   - **Library rules** (`outfit_problems`, `library_problems`, all at zero):
     - complete: top or dress, lower unless a dress (the registry's own rule), footwear;
     - no brand, logo or lettering (`BRAND_OR_LOGO`);
     - nothing revealing (`REVEALING`);
     - **no knitted or crocheted garment**: a knitted cardigan beside a crochet product reads as part of it, and every frame states "no other crocheted or knitted item";
     - every large garment names a palette colour;
     - pairwise distinct (max similarity 0.59 < 0.60), and distinct from the reference clothing.
   - **Family compatibility** (`compatible`) follows how the product meets Laura:
     - **Garment** (worn): the outfit is the base layer, with no outerwear and no dress.
     - **Shawl**: no outerwear.
     - **Scarf**: no necklace.
     - **Hat**: hair down or low, no barrette.
     - **Held families** (blanket, baby, pillow, amigurumi): no coat, jacket or blazer, because they are indoors.
     - **Baby and amigurumi**: no necklace and no bag, because the product is held close.
   - **Colour harmony** (`harmony`, CIELAB, rule `outfit_library.harmony/1`). Only the large garments (top, lower, outerwear) are measured:
     - **CAMOUFLAGE**: a large garment with ΔE76 < 20 to any yarn colour would merge with the product's edges.
     - **COMPETITION**: a garment with chroma above max(yarn chroma + 12, 34) outshouts the product.
     - **Unmeasurable product colours**: UNKNOWN, never PASS.
   - **Claim** (`claim_for_listing`). When the listing already holds an outfit, that outfit is returned unchanged. Otherwise the planner takes the first usable outfit in a stable per-listing order: compatible, harmonious, in season, held by no one. That outfit is then registered, approved (`approved_by = code:outfit_library/1`, see decision D-ENG-WARDROBE-1) and reserved. If `reserve` FAILs, the planner moves to the next outfit. If no outfit is usable, the result is UNKNOWN.
   - **Reference images** (`reference_request`) never call a provider:
     - **HELD** unless `paid_provider_gate.activation_state("flux-3-image", "generation")` is active;
     - **READY** with an activation, handed to the existing producer, whose `enforce` is the only spend point.
2. **`visual/scene_library.py`: 59 scenes and 36 props.**
   - The places include:
     - the living room, reading nook, nursery, kitchen, dining room, bedroom, entry and craft room;
     - the porch and garden;
     - away from home: a park, a lakeside, a forest trail, a market, an orchard and a snowy street.
   - Each scene maps to frame roles. `scene_problems` enforces:
     - a flat-lay is overhead;
     - a close-up is a close view with shallow depth of field;
     - neither shows Laura;
     - no `laura_home.FORBIDDEN` words;
     - no knitwear;
     - no "studio", which ENG-LEARN would read as studio light.
   - **The misleading-prop rule** (`prop_problems`, `misleading_text`):
     - **KNITWEAR**: no crocheted or knitted item;
     - **DECOY**: nothing of the product's own kind (`laura_home.DECOY_FOR_CATEGORY`);
     - **KIT**: nothing that reads as supplied with the pattern (yarn, hooks, notions, a printed pattern, packaging, gift boxes or tags);
     - **NOT_ALLOWED**: only props in the family's `FAMILY_PROPS`;
     - every prompt carries `NOT_INCLUDED`.
   - A scene suits a family only if its whole text, the room architecture included, passes the rule. For example, the bedroom's cream duvet is a decoy beside a blanket, so the bedroom is not a blanket scene.
3. **`visual/prompt_assembly.py`.**
   - **Deterministic sections:** scene, Laura (identity lock, outfit and hair) or "No person in the frame", the product block, realism and negatives.
   - **Versioned templates:** `ws.<role>@1`. Each frame records `template_id`, `prompt_version` and `prompt_sha256`.
   - **ENG-LEARN interface** (`image_lessons/1`):
     - `learn_default_template(family, role)` returns their shape (`brief`, `camera`, `lighting`, `negatives`) in their CAMERA and LIGHTING vocabularies, and accepts a frame role or a shot_plans role key;
     - `assemble(learned=prompt_for(...))` lets a learned brief, camera, lighting or negatives replace the code template's and carries `learn:<arm>:<ver>`;
     - `learn_scene(frame)` is the `scene` dict their `features` reads.
   - A learned brief is held to the misleading-prop rule and `laura_home.check`, and never touches the product block or the outfit.
   - `flux_scene` is the `scene` argument `creative.flux_prompt.build` takes (outfit, environment, pose, framing).
4. **`visual/gallery_planner.py`.**
   - **The frames:**

     | Frame | Job |
     |---|---|
     | hero | DESIRE |
     | flat_lay | COLOUR_CONTEXT |
     | lifestyle | LIFESTYLE |
     | alt_angle | ANGLE |
     | close_up | DETAIL |
     | scale_in_use | SCALE |
     | extra, shaped or worn family | CONSTRUCTION (generated), plus the CONTENTS frame as an 8th |
     | extra, any other family | CONTENTS (deterministic) |

     This matches ENG-VIS-GALLERY's `FLUX_SLOTS` jobs. One job per frame, so `shot_plans.campaign_standard` passes.
   - **Scene choice:** a deterministic depth-first search. No scene is used twice, and no place is shot from the same angle twice. It prefers new places, is season-strict, and keeps Laura only in scenes that can host her.
   - **Where Laura appears:**
     - worn families: hero, lifestyle, back view and fit;
     - held families: lifestyle and scale;
     - home goods: lifestyle;
     - never in the flat-lay or close-up.
   - **`check_gallery` refuses:**
     - fewer than 7 frames;
     - a duplicate role or job;
     - a duplicate scene;
     - the same place shot from the same angle;
     - fewer than 3 places;
     - outfit problems;
     - `product_not_invariant`;
     - `repetitive_filler`: Jaccard ≥ 0.70 on what varies between frames, with the fixed room architecture excluded.
   - With no distinct scene available, the planner raises `GalleryRefused` and never pads.
   - `plan_for_listing(db, slug)` claims the outfit and plans from the certified CIR.

## Evidence

- `tests/test_wardrobe_scenes.py`: 34 tests, all OK.
  - **Uniqueness:** 25 listings get 25 distinct outfits, all held in the registry.
  - **Constancy:** the same id comes back on every repeat, with any family or season asked later, and across the whole gallery.
  - **Harmony:** CAMOUFLAGE, COMPETITION and UNKNOWN are all reached, and the claim enforces harmony.
  - **Props:** KIT, KNITWEAR, DECOY, NOT_ALLOWED and UNKNOWN are all reached, and a learned brief with yarn is refused.
  - **Plans:** 13 families × 5 seasons (any, spring, summer, autumn, winter) × 12 listings = 780 valid plans, plus all 8 Launch-0 listings with distinct outfits.
  - **Determinism:** byte-identical prompts and fingerprints.
  - **Activation:** reference images are HELD with no activation and no `enforce` call, and READY only under a test activation.
- **Mutations** (`MUTANTS`, run by `test_each_rule_mutation_is_caught`). Each of these mutants is killed by its rule's own `AssertionError`, and every test passes again with the mutant removed:
  - uniqueness (registry plus exclusion disabled);
  - constancy (`reserved_for` blinded);
  - the one-outfit gallery check removed;
  - harmony (thresholds disabled);
  - props (KIT regex emptied);
  - the seven-role plan (a role dropped);
  - determinism (a drifting prompt);
  - filler (overlap and place limits disabled).
- Wide suites: see the #28 comment for the list and counts. They are the suites naming outfit, shot_plans, gallery or campaign, plus `test_w4_resume_runner`, `test_v11_autonomy_timeline` and `test_vacuity`.
- The autonomy map was regenerated via `python -m brambleloop.autonomy.map --write`. The only diff was `generated_at`, so it is not committed: nothing in the wiring changed.

## Honest status and findings

- **No image was generated and no provider was called.** The libraries and the planner are not yet wired into the producer (`image_production` / ENG-VIS-GALLERY's FLUX route). That is slice 2, coordinated on #28.
- **Library approval is by code, not by the owner.** `approved_by = code:outfit_library/1` (D-ENG-WARDROBE-1). The owner can retire any outfit with `outfits.replace`.
- **Capacity finding: Cloudline Baby Blanket (cream + ink).** Only 5 library outfits pass harmony and the baby rules, because ink #1A2B3C camouflages navy, indigo, black and charcoal, and cream camouflages white and ivory. That is enough for this listing, but a family of cream+ink products would exhaust it. The next library version should add mid-tone, muted outfits (sage, stone, rose, heather).
- **Laura in home-goods lifestyle frames.** I put her in the lifestyle frame of coasters, placemats, baskets and ornaments, because the owner asked for people. ENG-VIS-GALLERY's `FLUX_BRIEFS[small_goods]` has no person. This is one table, `gallery_planner.LAURA_IN`, raised on #28 to agree before wiring.
- **Hair arrangement.** It is stored in the outfit's `concept`, not its garments, because the registry refuses the word "hair" in garments. ENG-VIS-IDENTITY owns the identity lock, so it is asked on #28 to confirm that an arrangement-only list is within the lock.
