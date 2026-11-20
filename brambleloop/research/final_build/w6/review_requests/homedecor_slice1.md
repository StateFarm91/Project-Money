# Review request — ENG-HOMEDECOR slice 1: vessels in the round

Branch `eng/homedecor`, from `origin/claude/w6-INTEG3` (307c7e62). Builder branch: NOT reviewed,
NOT integrated, NOT deployed. Production is unchanged (SHADOW).

## What I found first (a live defect, reproduced before anything was built)

The vessel engine makes one object, a hexagon base with straight striped walls. The router
admitted any basket title that did not name a held feature, and certification checked only the
shape words it already knew. So five different products went through the real handlers
(`radar.concept_intake` → `radar.score` → `cir.draft` → `cir.compile` → `gate.certify`) and were
**granted certificates as that same hexagon basket**:

| Title | What it promised | What certified |
|---|---|---|
| Round Driftwood Basket | a circle | six stacked corners (`check_shape_claims` reads "round" only before a flat noun) |
| Oval Driftwood Basket | an oval | a hexagon |
| Driftwood Yarn Bowl | a bowl | a 16 cm straight-walled basket |
| Driftwood Plant Pot Cozy | a cover fitted to a pot | a basket at no pot's size |
| Moss Stitch Basket | moss stitch | plain single crochet |

`test_the_plain_hexagon_basket_under_a_vessel_name_it_does_not_make_is_refused` pins it.

## What this slice builds

`src/brambleloop/creative/homedecor.py`. Each variant is derived from the verified
`fallback_constructions.vessel`, so walls, palette, gauge and provenance are the ones that already
certify.

| Family | Construction | Proof (`tests/test_eng_homedecor.py`) |
|---|---|---|
| `round_vessel` | the same counts with staggered increases (alternating mid-wedge and end-of-wedge, never on a stitch the last increase made). `geometry.corners` reads 0 at small, medium and large | `test_a_research_round_basket_certifies_with_a_round_base` |
| `bowl` | a round base, then a wall with one +6 staggered round in every 3. Lean is computed, and must be 8–50° | `test_a_research_bowl_certifies_with_a_flared_wall` |
| `lidded_vessel` | a basket plus a `lid` piece: a disc grown by whole wedges until its lip clears the rim (`lid_count`), then a 2 cm lip. Not sewn | `test_a_research_lidded_basket_certifies_with_a_fitting_lid` |
| `handled_vessel` | two opposite `ch N (spans=N), sk N` openings, 2 rounds below the rim. The next round works into the chains, so the count is restored | `test_a_research_handled_basket_certifies_with_cut_out_handles` |

Each proof runs concept → intake → score → draft → compile → twin → reverse → granted certificate
→ US and UK PDF. Both PDFs are held to the small-home-goods standard
(`research/benchmarks/PDF_STRUCTURE_STANDARD.md`): materials, gauge, finished size,
abbreviations, every round with its count, finishing, licence and disclosure. The proofs also
check that no US `sc` appears in the UK edition, and that the UK edition prints "miss" where the
US edition prints "sk".

## Gates (`homedecor.findings`, wired into `gates.certificate.certify` for the CIR title AND the listing title)

| Code | Refuses | Mutation test |
|---|---|---|
| `VESSEL_BASE_NOT_FLAT` | a base round growing outside 0.85–1.15× its row height (cups or ruffles) | +3/round and +12/round bases |
| `VESSEL_OUTLINE_UNSUPPORTED` | a circle word without 0 corners; oval/oblong/square/rectangular outlines | hexagon titled "Round"; "Oval" |
| `VESSEL_BOWL_NOT_FLARED` | "bowl" whose wall leans < 8° or > 50° | straight vessel; engine mutant that never flares |
| `VESSEL_LID_DOES_NOT_FIT` | no lid, or a lip clearance outside 0.3–6.0 cm measured around | lid at rim count (binds), +60 (loose), removed |
| `VESSEL_HANDLE_UNSUPPORTED` | "handles" without two opposite openings ≥ `HANDLE_MIN_CM`, ≥ 2 rounds below the rim, ≤ 40% of the round | narrow, adjacent, single, at the rim, none |
| `VESSEL_OBJECT_UNSUPPORTED` | plant pot cozy / planter (no sourced pot size) | plain vessel retitled |
| `VESSEL_TEXTURE_UNSUPPORTED` | moss, seed, linen and other textures no technique check reads | plain vessel retitled |

Each `_kill` proves two things: the mutant is refused by the named code, and once that gate is
removed no other `VESSEL_*` code refuses it. So it is that gate that holds.

## Routing and holds

- `fallback_constructions._plan`, vessel category: tapestry first, then `homedecor.vessel_route`,
  then the plain vessel. This is one rule, so intake and `cir.draft` agree.
- `construction_families`:
  - four VERIFIED families and four `(variant, "basket")` `PAIR_PROOFS`;
  - a declared `basket` in the round accepts a vessel variant;
  - `draft_hold` labels variants.
- Changes to `NAMED_FEATURES`:
  - `lid` is now honest for `lidded_vessel`, and the other closures (zip, button, flap, covered) are split out as `closure`;
  - `handles` is honest for `handled_vessel`, and `straps` is split out (tote only);
  - new features: `outline_round` (round_vessel and bowl), `outline_oval`, `bowl`, `planter` and `stitch_texture`.
- Still held, by name: oval, square and rectangular outlines; planters and pot cozies; stitch
  textures; any two variants combined ("Round Lidded Basket"); nesting sets (one draft is one
  release).

## Shared-code changes to look at closely

1. `cir/geometry._increase_and_parentage`: a chain with `spans > 0` bridges skipped stitches and
   is no longer counted as an increase. Without this, an opening high in the wall hid the base's
   six corners (`sides` was None). Pouch eyelets use `spans` too, so pouch `sides` may now read 6.
2. `publish/pdf.py`:
   - A multi-piece CIR's cover read "Makes 2 baskets" for a basket and its lid. The same bug
     existed for the tote, which read "Makes 3 baskets". It now reads "In 2 pieces: 1 basket,
     1 lid", and the overview no longer says "each" over different pieces.
   - A round vessel's soft-fold disclosure no longer mentions corners it does not have.
3. `tests/test_eng_families.py` changes:
   - the meta-guards now accept proofs in `tests/test_eng_homedecor.py`, checked to exist by AST;
   - a feature word honest for an engine may route to that engine, and is never admitted to the plain family;
   - the granny mutant uses "Granny Stripe" ("Square" is now an outline refusal of its own).

## Honest limits

- Every figure is computed from the stated gauge, and none is measured:
  - Bowl sizes are house design sizes; no standard exists.
  - Lid fit rests on an assumed fabric thickness of half a row height, which is uncalibrated.
  - `HANDLE_MIN_CM = 8.0` is a design choice, not a sourced standard.
- The bowl's height comes out below its nominal figure, because a flare round adds almost no
  rise in the per-round surface model.
- Nothing here ran against production data. Nothing is listed or deployed.

## Suites

All of these passed on this branch:
- `test_eng_homedecor` (16 tests)
- `test_eng_families` (16)
- `test_compiler`
- `test_twin`
- `test_reverse`
- `test_s1_product_truth_3`
- `test_deliverable_qa`
- `test_w5_concept_intake`
- `test_opus2_draft_constructions`
- `test_opus2_tapestry_basket`
- `test_w4_resume_runner`
- `test_vacuity`
- `test_v11_autonomy_timeline`

`brambleloop.autonomy.map` was regenerated and produced no diff, because no job wiring changed.

## Next slices

- **Slice 2, décor:**
  - coasters and placemats in the round, using the hexagon and round disc and a size band per object;
  - garlands (motif plus joining chain);
  - ornaments (flat discs first; 3-D needs a stuffing model);
  - wall hangings (dowel casing and fringe);
  - table runners are already flat-certified.
- **Slice 3, textures:**
  - moss/linen and BLO-ribbed walls, which use only convention primitives and so can be VERIFIED;
  - bobble/popcorn and waffle, which use `bob`/`fpdc` and are UNCALIBRATED, so `physical_gate` at best;
  - each with a stitch-count definition and a yarn-factor model.
- **Later:**
  - an oval base, which needs a stadium surface model;
  - plant-pot cozies, which need a sourced pot table;
  - nesting sets, which need a multi-release bundle.
