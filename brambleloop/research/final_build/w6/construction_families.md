# Construction families: which engine makes a researched concept (ENG-FAMILIES)

Status as of 2026-11-19, branch `eng/families` (base `claude/w6-INTEG2` @ a35ad302).
Nothing here is deployed. The router's machine-readable form is
`src/brambleloop/creative/construction_families.py` (`FAMILIES`, `UNBUILT`, `family_table()`).
`tests/test_eng_families.py::test_router_family_table_is_the_report_and_names_every_unbuilt_family`
fails if a family in that table is missing from this file.

## How a researched concept is routed

`radar.concept_intake` → `construction_families.route` → `radar.score` → `cir.draft` →
`cir.compile` → `gate.certify`.

- The route has no rule of its own. It asks `creative.fallback_constructions.plan`, the same
  function `cir.draft` calls, which family the concept's category and title draft.
- The concept's **declared** form and construction (closed vocabulary) must name that same
  family. If they don't (for example, a "tapestry" basket whose title the draft would build
  as a plain striped vessel, or a basket in the placemat category), the concept is held.
- Only families with status `verified` or `physical_gate` are admitted. Everything else is
  held with the reason `construction_unsupported:<family> -- <why>`.
- Holds show up in `production_inventory` as hold kind `construction_unsupported`, both for
  intake holds (state `research_candidate`) and for `cir.draft` construction refusals (state
  `research_approved`, "held: …"). `production_summary.held_by_reason` counts them.
- Children's safety is untouched. Intake's `_children_reasons` pre-check runs for every
  family. `childrens_decision` and `small_parts` run at PDF build. Routing never changes a
  concept's category or title, and no baby item routes to a shaped family: a baby concept
  declared in the round is held as `construction_unsupported:vessel`.

## Status definitions

- **verified**: a research-derived, non-catalogue concept goes through all of the following,
  pinned by the named test: intake approval, score, draft, compile, twin, independent reverse
  compile, Product Truth size check (no `OBJECT_SIZE_*` finding), and a granted certificate
  with no ERROR finding.
- **physical_gate**: everything computes clean, and certification withholds only for the
  physical sample that its risk class requires. The existing physical-sample path carries it.
  Admitted.
- **partial**: an engine exists, but it does not certify a research concept, or no pinned
  research-derived proof exists yet. Held.
- **none**: no engine on the research route. Held.

## Research-route families (reachable from a researched concept)

| Family | Engine | Status | Test that proves it | Sizes (source) | Gaps |
|---|---|---|---|---|---|
| `flat_panel` | `runtime.pipeline.concept_to_cir` | verified | `test_a_research_flat_runner_certifies_end_to_end` | per-category template (`_GEOMETRY`, `_TITLE_GEOMETRY`); size classes from `creative.size_truth` (Craft Yarn Council blanket sizes) | plain sc/dc stripes only: no charted motif, no texture stitch |
| `vessel` | `creative.fallback_constructions.vessel` | verified | `test_a_research_basket_routes_to_the_vessel_engine_and_certifies` | small / medium / large from `products.vessels.BASKET_SIZES` (house design sizes, **no published standard**) | striped walls only; one size per release; pet bed is cat size only |
| `tapestry` | `creative.fallback_constructions.tapestry_basket` | verified | `test_a_research_tapestry_basket_routes_to_its_chart_and_certifies` | small / medium / large from `BASKET_SIZES` | two charts (diamond, check), two colours; a motif word outside the allowlist (for example "heron") is held |
| `panel_pair` | `creative.fallback_constructions.panel_pair` | physical_gate | `test_a_research_cushion_is_physical_gated_not_flattened` | `size_truth.PILLOW_FORMS` (standard pillow-form sizes) | certification's risk matrix sets class C; the only refusal is `PHYSICAL_TEST_REQUIRED` |
| `garment_raglan` | `products.garment_release` (`raglan_cardigan`) | verified | `tests/test_eng_garment.py::test_a_research_adult_cardigan_runs_concept_to_pdf_in_nine_sizes`, `::test_a_research_baby_cardigan_runs_concept_to_pdf` | CYC woman XS-5X; CYC baby 3-24 months (`cir.graded`), one release of every size | cardigan only; relaxed or oversized; adult pair proven on the adult table, baby pair on the baby table only (ENG-GARMENT) |
| `garment_one_piece` | `products.garment_release` (`one_piece_sweater`) | verified | `tests/test_eng_garment.py::test_a_research_child_sweater_runs_concept_to_pdf` | CYC child/youth 2-12 (`cir.graded`) | sweater on the child table only; adult one-piece held until a proof exists (ENG-GARMENT) |
| `garment_side_to_side` | `products.garment_release` (`side_to_side_vest`) | partial | none at intake (every size certifies and renders in `tests/test_eng_garment.py`) | CYC woman XS-5X | no research concept pinned through intake (ENG-GARMENT) |
| `garment_drop_shoulder` | `products.garment_release` (`drop_shoulder_pullover`) | partial | none at intake (every size certifies and renders in `tests/test_eng_garment.py`) | CYC woman XS-5X | no research concept pinned through intake (ENG-GARMENT) |
| `pouch` | `creative.fallback_constructions.pouch` | partial | none: an exploratory run was refused | one size (`POUCH_ACROSS_CM`, design choice) | certification refuses `ASSET_COLOR_ABSENT`: the pouch works one palette colour while its hero asset depicts two |
| `tote` | `creative.fallback_constructions.tote` | partial | none yet | `BASKET_SIZES` | no research-derived concept pinned through certification (the exploratory title was a dedupe hit on POOL `everyday-market-tote`) |
| `cosy` | `creative.fallback_constructions.cosy` | partial | none yet | one size (`EGG_AROUND_CM`) | one exploratory run was granted; no pinned test yet (slice two) |
| `stocking` | `creative.fallback_constructions.stocking` | partial | none yet | one size (`STOCKING_SIZE_SOURCE`, design choice) | no research-derived concept pinned through certification |
| `triangle` | `creative.fallback_constructions.triangle` | partial | none yet | one size (`SHAWL_WINGSPAN_CM`, design choice) | no research-derived concept pinned through certification |
| `colourwork_tapestry` | `creative.colourwork.flat_piece` (blanket, placemat, cushion front) / `creative.colourwork.basket_wall` | verified (ENG-COLOURWORK, pair by pair) | `tests/test_eng_colourwork.py`: throw, placemat and basket wall certify with their charts; the cushion is physical-gated | `creative.size_truth` (CYC blanket sizes; placemat 30 x 45 cm; pillow forms); baskets `BASKET_SIZES` | tapestry only; six library motifs; bag, runner, wall hanging, scarf, dishcloth and baby held (`creative.colourwork.HELD_CATEGORY_WHY`) |
| `colourwork_overlay_mosaic` | none | none | — | — | no reach-down primitive yet (slice 2) |
| `colourwork_inset_mosaic` | none | none | — | — | no reach-down primitive yet (slice 2) |
| `colourwork_c2c` | none | none | — | — | no diagonal tile primitive yet (slice 3) |
| `intarsia` | none | none | — | — | colour blocks on bobbins, no carried strand; not modelled |
| `fair_isle` | none | none | — | — | floated stranded technique; not modelled |
| `amigurumi` | none | none | — | — | spiral rounds with sculpted shaping; no shaped-form engine on the radar path |
| `amigurumi` | `creative.fallback_constructions.amigurumi` | physical_gate (ENG-PLUSH) | `tests/test_eng_plush.py::test_a_research_amigurumi_is_physical_gated_end_to_end` | one size, `AMI_BODY_STITCHES` at the drafted weight (design choice; circumference only) | ball-body bear or bunny only; embroidered features; held for the physical sample and the child-safety physical evidence (`gates.child_safety`) |
| `envelope_cushion` | `creative.cushions.envelope_cover` | verified (ENG-PLUSH) | `tests/test_eng_plush.py::test_a_research_envelope_cushion_certifies_end_to_end` | `creative.cushions.FORMS_IN` (standard pillow-form sizes) | plain sc front, envelope back; no buttons, zip or ties |
| `applique_cushion` | `creative.cushions.envelope_cover` (appliqué) | verified (ENG-PLUSH) | `tests/test_eng_plush.py::test_a_research_highland_cow_cushion_certifies_end_to_end` | `creative.cushions.FORMS_IN` | faces only from `creative.cushions.APPLIQUES` (original flat pieces); no modelled texture, so "shaggy"/"fluffy"/"fringe" are held |
| `lovey` | `creative.baby.lovey` | physical_gate (ENG-PLUSH) | `tests/test_eng_plush.py::test_a_research_lovey_is_physical_gated_end_to_end` | 30 x 30 cm square (`LOVEY_SQUARE_CM`, design choice) | bear or bunny head; held for the physical sample and the child-safety physical evidence |
| `composer` | `creative.composer.compose` (ENG-COMPOSER) | physical_gate | `tests/test_eng_composer.py::test_a_research_composer_concept_runs_concept_to_pdf`, `::test_a_research_composer_tote_is_granted_through_the_real_handlers` | per template: tote small/medium/large, tablet/laptop sleeve, 14 in / 16 in round pillow form, 30 x 30 cm lovey square (design choices stated in cm); sewn pieces solved to clear the small-parts cylinder | only `TEMPLATES` (toy, lovey, tote, round cushion, sleeve) and `SUBJECTS` (owl, whale, lamb); toys, the lovey and the round cushion are held for their physical sample, totes and sleeves are granted; anything else files an `improve.ecr` request naming the missing primitive (for example `graded_head_fit` for a beanie) |
| `mosaic` | none on research route | none | — | — | overlay mosaic needs stitches that reach past the previous row; only the hand-engineered Nordic Forest throw has it |
| `graphghan` | none | none | — | — | a charted picture in rows; the radar template drafts stripes |
| `cable` | none on research route | none | — | — | post-stitch crossings (B-080); only the hand-engineered `texture.build_cable_throw` has them |
| `motif` | none | none | — | — | granny squares / joined motifs |
| `c2c` | none | none | — | — | diagonal tile increases and decreases |
| `side_to_side` | none | none | — | — | lengthwise foundation |
| `modular` | none | none | — | — | several shaped panels and an assembly |
| `garment` | `creative.garment_design` (tournament path only) | none on research route | — | — | graded garments are built only from tournament winners, not radar concepts |
| `ornament` | none | none | — | — | closed or shaped small pieces |
| `hat` | none | none | — | — | the sourced head chart lacks height and negative ease (`HAT_UNSOURCED`) |
| `flower` | none | none | — | — | a motif in rounds |
| `seasonal_decor` | none | none | — | — | garlands and shapes |

## Catalogue engines (hand-engineered; not reachable from a researched concept)

These build named catalogue slugs (`runtime.pipeline.ENGINEERED`). They are not parameterised
by a concept, so a researched concept cannot route to them. They were **not re-verified on
this branch**. Their certification status is whatever the certification runs in
`BUILD_STATE.md` recorded.

| Engine | Builds | Research-route status | Gap to route research concepts |
|---|---|---|---|
| `products.nordic_forest.build` | mosaic/overlay throw (and baby proposal) | none | one fixed motif; would need a parameterised overlay-chart engine |
| `products.texture` | cable throw, bobble pillow, ribbed scarf | none | each is one design; cable, bobble and rib are not exposed as concept parameters |
| `products.launch0` / `products.vessels.build_basket` | the three Launch-0 baskets, hexagon coasters | none directly; the research `vessel` family reuses `vessels._disc_rounds`, `base_stitches_for` and `BASKET_SIZES` | hexagon coaster disc is not on the fallback route |
| `products.moment_candidates` | tea cosy, advent garland, ring pillow, key basket, kneeler, cable wrap | none | per-candidate builders, tournament path |
| `products.garments` + `cir.graded` + `creative.garment_design` | graded garments | none on radar route | tournament path only |
| `products.builder` + `products.motifs` | generated catalogue (motif × palette panels) | none | the catalogue generator, not a research route |
| `products.personalisation` | personalised variants of certified designs | n/a | operates on certified releases |
| `creative.prototype.author` | tournament prototypes (sc body in the routed construction) | n/a here | `ENGINE_ROUTE` maps tapestry, mosaic, cable, granny and C2C to `flat_rows`, a plain sc body. It is a prototype size check, not a product. It is out of scope for this slice and noted as a gap: it must never be certified under a technique name (`launch0.fabric_truth` refuses that at publication) |

## Defects found while verifying (not fixed here; owned elsewhere)

- **`gates/policy.py` IP terms** matched bare substrings ("Fernbank" refused 'nba'). Fixed in
  fix round 1: whole-word matching with a test.
- **`pouch` hero asset colour.** The pouch engine works one colour of a two-colour palette,
  while its hero asset depicts both, so certification correctly refuses it. To promote the
  family, either colour the pouch (rim or cord in the second colour) or render a one-colour
  asset.

## Next slices

1. Pin cosy, tote, stocking and triangle with research-derived certify tests and promote any
   that pass. Fix the pouch colour and promote it.
2. Family expansion: sizes from each family's size table (vessel and tapestry: small, medium,
   large), tapestry charts (diamond, check) and colourways. Each variation is deduplicated by
   the existing novelty and sibling gates and certified as its own release.

## Fix round 1 (review verdict DO NOT SHIP: H1, M1)

- **H1, named constructions.** `route` now also reads the title and the concept premise against
  one shared vocabulary, `construction_families.NAMED_FEATURES` (granny squares, cables,
  bobbles, waffle and other texture stitches, lids and closures, ears and other amigurumi
  parts, trim, lining and pockets, motif assemblies, colourwork techniques, wearables). A
  family's own honest word is exempt (handles for the tote). Any hit holds the concept as
  `construction_unsupported:<feature>` for every admitted family. Winner Amplification
  premises no longer name the winner's own construction word.
- **M1, pet beds.** A pet bed drafts as the vessel but certifies nowhere: its note states 10 cm
  against the twin's 11.4 cm (`TWIN_DIMENSION_IMPLAUSIBLE`). Held as
  `construction_unsupported:pet_bed` until the sizing is corrected and proven. The flat pet mat
  stays admitted. The twin tolerance is untouched.
- **Pair guard.** `PAIR_PROOFS` names a certifying proof for every admitted (family, category)
  pair; a sweep test fails when the router admits a pair without one.
