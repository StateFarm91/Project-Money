# [ENG-COMPOSER] Review request: a deterministic composer of original items from proven primitives

- **Branch:** `eng/composer`, from `claude/w6-INTEG7-wip` @ `c6d4400`. Not merged, not deployed.
  Production is unchanged.
- **SHA under review:** `__SHA__` (the commit that adds this file; later commits only update it).
- **Owner goal:** production learns to build new things without a new hand-written engine for
  every product family.

## What was built

`src/brambleloop/creative/composer.py` composes an ORIGINAL item from a declarative plan. The plan
is a dict that any proposer, including a model, may write. The composer builds it only from
primitives in `PRIMITIVES`. Each primitive names the test that validates it.

| Kind | Primitives (20) |
|---|---|
| Shapes in the round | `flat_circle`, `sphere`, `ovoid`, `cylinder`, `cone`, `tube` |
| Flat panels | `rectangle`, `trapezoid` (`cir.shaping.taper`), `triangle` |
| Closures | `gathered` (stuffing point and close), `folded_flat` (the ear rule), `open` |
| Joins | `sewn` (placed on a round, stitches from centre, mirrored), `join_as_you_go` (slip stitched into a named round), `seamed_panels` (named edges), `surface` (laid on a panel), `rim` (round to round) |
| Details | `colour_blocks` (fractions of a piece's rows), `band_edging` (plain contrast rounds or rows) |

- **Parameters are solved from the gauge.** A sphere's widest round comes from its diameter. An
  ovoid's even rounds come from its height (half the ellipse meridian). A cone's increases are
  spread with `shaping.distribute`. A folded piece is solved in 12-st wedges so its flattened
  edge can be centred. A sewn-on piece is raised to the smallest size that clears the
  small-parts cylinder (`clear_diameter_cm`, from `gates.small_parts`). Pieces on one round
  keep `SEWN_GAP_STS` = 6 clear front and back (the amigurumi engine's `AMI_EAR_GAP`).
- **Product Truth.** The finished-size note is written from the compiled twin, never typed. It
  uses the "about N cm" form that `risk_matrix.plausibility_findings` re-checks at certify. A
  mutant that types the note is killed (M4).
- **Refusal by name.** `validate()` returns every reason, and each reason starts with the name
  of the missing or misused primitive. `UNEXPRESSIBLE` names 12 primitives that do not exist
  yet: `graded_head_fit`, `bobble_texture`, `post_stitch_cable`, `fringe_trim`,
  `shaped_edging`, `hard_closure`, `lining_or_pocket`, `motif_join`, `charted_colourwork`,
  `loop_texture`, `hard_part` and `graded_garment`. Unknown subjects, templates and
  accessories are refused as `subject:<x>`, `template:<x>` and `accessory:<x>`. The builders
  also refuse unknown shapes on their own, so a bypassed validator still yields a named
  refusal (M6).
- **Concept to plan.** `TEMPLATES` covers toy, lovey, tote, round cushion and sleeve.
  `SUBJECTS` covers owl, whale and lamb, each a generic form in Brambleloop's own shape
  vocabulary. `concept_from_text` reads a research title deterministically.
- **The validator wins.** `adjudicate(proposals)` composes the first proposal that validates.
  Votes do not count: three identical invalid proposals are all refused.
- **Routing and change requests.**
  - `construction_families.route` admits a concept that every engine holds only when the
    composer composes it and no named feature in its title or premise is one the composer
    lacks. The new family is `composer`, status `physical_gate`.
  - `cir.draft` drafts through the composer (`pipeline._draft_composed`) in two cases: when no
    fallback engine makes the concept, and when an intake concept's engine family is not
    admitted (for example the partial `tote`).
  - An unexpressible concept files `improve.ecr.file(defect_class="missing_capability",
    module="creative.composer:<primitive>")`. Repeats merge into one request, so the
    occurrence count is the demand signal.

## Proof by example: six original items, no new family engine

Every item ran concept → plan → CIR → compile, twin, assembly, reverse (US and UK) → certify
(US and UK) → US and UK PDF. The table comes from `scripts/compose_examples.py`.

| Item | Title | Parts (shape, closure) | Joins | Rows | Sts | Risk | Size (from the twin) | Certificate US / UK | PDF US / UK |
|---|---|---|---|---|---|---|---|---|---|
| owl | Pebble Owl Amigurumi | body (ovoid, gathered), wing (cylinder, folded_flat ×2), ear tuft (cone, folded_flat ×2) | sewn | 44 | 1146 | C | The body is about 33.6 cm around its widest round | withheld: CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN, PHYSICAL_TEST_REQUIRED | 1001 KB / 1001 KB |
| whale | Harbour Whale Amigurumi | body (ovoid, gathered), fin (cylinder, folded_flat ×2), tail (cone, folded_flat) | sewn | 47 | 1392 | C | The body is about 38.4 cm around its widest round | withheld: CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN, PHYSICAL_TEST_REQUIRED | 990 KB / 990 KB |
| lovey | Meadow Lamb Lovey | square (rectangle, open), head (sphere, gathered), ear (cylinder, folded_flat ×2) | sewn, surface | 68 | 2242 | C | The square is about 30.4 cm wide and about 29.7 cm tall | withheld: CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN, PHYSICAL_TEST_REQUIRED | 247 KB / 247 KB |
| tote | Harvest Block Tote | bag (cylinder, open), strap (rectangle, open ×2) | sewn | 109 | 3360 | A | The bag is about 18.3 cm across and about 25.4 cm tall | granted / granted | 1450 KB / 1450 KB |
| cushion | Moonwell Round Cushion Cover | front (flat_circle, open), back (flat_circle, open) | rim | 54 | 4536 | A | The front is about 41.3 cm across | withheld: PHYSICAL_TEST_REQUIRED | 1312 KB / 1312 KB |
| sleeve | Slate Band Tablet Sleeve | front (rectangle, open), back (rectangle, open) | seamed_panels | 60 | 1920 | A | The front is about 25.6 cm wide and about 21.7 cm tall | granted / granted | 355 KB / 354 KB |

- **"Withheld" means withheld only for physical evidence.** The toys and the lovey are held
  for `PHYSICAL_TEST_REQUIRED` and `CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN`, exactly as the
  plush engine's own toy and lovey are. The round cushion is sewn shut over its form, so the
  risk matrix makes it class C and holds it for `PHYSICAL_TEST_REQUIRED`, like `panel_pair`.
  Every computable check passes, including every child-safety check except physical evidence.
- **The new shapes are ones the amigurumi engine does not make:** ovoid bodies, cone ear
  tufts and tail, and folded-flat cylinder wings and fins.
- **Two research concepts ran through the real handlers.** The owl (withheld only for
  physical evidence) and the tote (granted) both went intake → score → `cir.draft` (composer)
  → compile → certify.

### The beanie: REFUSED, with a change request filed

ENG-GARMENT-2's branch `eng/garment-2` does not exist on the remote (checked with
`git ls-remote`), so there was no grading to reuse.

The Craft Yarn Council head circumference chart was re-read on 2026-11-20. It publishes
circumference ranges only: no crown-to-brim height and no negative ease.

A beanie sized from that chart would have to invent two numbers. So the composer refuses it as
`graded_head_fit` and files an ECR. This is pinned by
`test_the_beanie_is_refused_by_name_and_files_a_request`.

To unblock it, a sourced hat height and ease table is needed, landed as data with its source.
Six items certify without the beanie.

## Fixes to shared code found by this work (please review)

1. **`publish/pdf_standard.py` `_LABEL`.** "Stuff after Rnd 16:" and "Close after Rnd 18:" were
   read as round labels with no count. On this base that made **every** stuffed toy PDF
   refuse (`PremiumStandardRefused`), including the plush engine's own ball bear. It was
   reproduced on `FC.amigurumi` before the fix. The fix is a `(?<!after )` lookbehind.
2. **`cir/assembly.py` `_flattened_round`.** A round piece sewn by its edge across a placed span
   lies flattened. It was measured that way only when the piece it joined had no footprint (a
   closed body). On an open vessel, it was compared by its diameter. A flap or fin on a basket
   read 3.1 cm against 4.8 cm and was refused as a mismatch that is not there. Now it is
   always measured by the flattened count (`_count_join`). Flat straps are unaffected.
3. **Open gap, not changed:** `risk_matrix._DIM_RE` reads "about 40 cm" but not "40 x 40 cm".
   A "W x H cm" size note, which is the form `twin.size_statement` itself produces, is never
   re-checked against the twin. A sleeve stating "About 40 x 40 cm" was granted at 25.6 x
   21.7 cm. The composer avoids this by writing "about W cm wide and about H cm tall". The
   gate's owner should decide whether to widen the regex, which may move catalogue
   verdicts.

## Tests

`tests/test_eng_composer.py`: 21 tests, all passing.
- **Primitive validation:** every shape compiles, builds its twin and reverse-compiles in US
  and UK, and measures as its shape. Join-as-you-go, seamed panels and the rim join are
  measured, and moved placements are refused.
- **Refusal:** of unexpressible plans and concepts, by name, plus the ECR filed and merged.
- **Determinism:** identical CIR fingerprints, and the plan digest is independent of key order.
- **The validator outvotes models.**
- **Mutation:** seven mutants, all killed:
  - M1 stuffing point before the widest round;
  - M2 small-parts solver skipped;
  - M3 odd flattened edge;
  - M4 typed size note;
  - M5 seam span off by one;
  - M6 validator bypassed;
  - M7 edited row count.
- **The six items, end to end,** plus the two real-handler research runs.

`tests/test_eng_families.py` is updated: the admitted set includes `composer`, and the probes
and `PAIR_PROOFS` cover (composer, amigurumi) and (composer, bag).
`research/final_build/w6/construction_families.md` gains the `composer` row.

__SUITE__

`autonomy_map.json` was regenerated. It has one new follow-on edge,
`runtime/pipeline.py:_draft_composed` → `cir.compile` (95 → 96).

## Honest limits

- No composed item has a physical sample. Toys, the lovey and the round cushion stay withheld
  until one is made and bound.
- Sizes are design choices stated in cm, not published standards: tote, sleeve, lovey square
  and toy bodies. The round pillow forms (14 in and 16 in) are common retail sizes, but
  `size_truth.PILLOW_FORMS` sources square and lumbar only.
- Model proposals are adjudicated, but no model is called here. `adjudicate` is the seam a
  proposer plugs into.
- Nothing was spent, no secret or Railway variable was read, and no PR was opened.
