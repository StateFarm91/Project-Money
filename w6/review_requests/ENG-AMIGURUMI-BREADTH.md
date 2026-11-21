# ENG-AMIGURUMI-BREADTH — review request

Branch: `eng/amigurumi-breadth` (cut from `claude/batch19-fixers`). NOT merged, NOT deployed;
production unchanged. Shadow capability only: the new family is `physical_gate`, so every toy
it drafts is HELD at certification for the physical sample and the child-safety physical
evidence. Nothing here can grant a certificate to a stuffed toy.

## Goal

Make the most-demanded concept shapes that were not buildable routable to verified engines.
Before this branch the demand catalogue (`radar.demand_originals.CATALOGUE`) held 11 animal
amigurumi concepts and 2 loveys as `construction_unsupported:amigurumi`, and 2 ball toys
("Cosy Round Bear", "Simple Round Teddy Bear") were held only because the title said "round".

## What was built

### 1. A CIR primitive: the low-sew ("join-as-you-go") join — `cir/low_sew.py`

Teardown lesson L2 (`research/benchmarks/TEARDOWN_MADELINEMAECO_CAPYBARA.md`) is a technique
class: an appendage is worked closed and flat, then crocheted into a named body round. Our
implementation, wording and geometry are our own.

- `Op.joins: str | None` names the piece an op's stitches are worked through. It is
  count-neutral for the host round. `to_dict` omits it when None, so no existing digest moves.
  CIR contract v3 -> v4 is declared in `core.contracts`, `ops/CONTRACT_CHANGES.md` and the
  test pin, and the consumers are re-pinned.
- **Compiler** (`low_sew.check`, called from `compile_cir`) raises these codes:
  - `LOW_SEW_UNKNOWN_PIECE`
  - `LOW_SEW_NOT_ROUNDS`
  - `LOW_SEW_EDGE_NOT_FLAT` (odd last round, or the piece is gathered closed)
  - `LOW_SEW_STITCH` (sc through both loops only)
  - `LOW_SEW_EDGE_MISMATCH` (a joined run must equal last round / 2)
  - `LOW_SEW_JOIN_COUNT` (joined exactly `make` times)
  - `LOW_SEW_ALSO_SEWN`
  - `LOW_SEW_UNMEASURED`

  Widths and counts are read from the **twin's cells** (`Cell.joins`), so the compiler and the
  twin share one definition.
- **Twin / assembly**: `assembly.assemble` records every crocheted-in run as a `join_in` join.
  A run is sound only when it matches the joined piece's flattened edge stitch for stitch.
- **Writer / reverse**: the writer prints "sc in next 9 sts through both layers of the leg", and
  the reverse compiler parses it back into `Op.joins` (US and UK). `_shape` compares `joins`, so
  a lost or renamed join is `REVERSE_MISMATCH`.

### 2. Child safety and small parts: made stricter, never weakened

- `small_parts._sewn_on` now includes every crocheted-in piece. A limb that could come away is
  measured against the 31.7 mm cylinder exactly like a sewn ear.
- `child_safety.profile_for` adds `joined_in`. AGE, PHYSICAL_EVIDENCE and the age text read it
  the same way they read `sewn`.
- A new required statement, "Crocheted-in joins", is printed in the PDF.
- `JOINS_VALIDATED` checks low-sew joins first. Before this change, a toy with no sewn seam would
  have read "no piece is sewn onto another" = PASS. Now any `LOW_SEW_*` finding or mismatched
  twin join is a FAIL, and an unmeasured join is UNKNOWN.
- Features are embroidered with yarn only. "Sleepy" is the only face variant (closed eyes in
  backstitch).

### 3. The shaped-animal engine — `creative/animals.py`, family `amigurumi_animal` (physical_gate)

Each animal has the head and body in one closed spiral piece, worked from the top of the head
down: head increases, an optional neck, the body, then a decrease to a gathered closure, with a
stuffing point validated by `closed_forms`. Appendages are tubes or cups from a magic ring with
flattened edges, crocheted in. The body note tells the maker to make the parts first. Every count
is a stated house design choice.

| animal | crocheted-in parts | notes |
|---|---|---|
| frog | 2 arms, 2 legs | contrast underside |
| capybara | 2 ears, 4 legs | |
| lamb | 2 ears, 4 legs | |
| duckling | bill, 2 wings | |
| whale | 2 fins, fluke tail | contrast underside |
| otter | 2 ears, 4 legs, tail | |
| cow | 2 ears, 4 legs, tail | |
| dinosaur | 4 legs, tail | |
| octopus | 8 legs in a ring | chunky only |

- Appendages are 18–24 sts wide at worsted and heavier, because small-parts measures any
  magic-ring piece as a disc. Finer yarn is refused, and the octopus is drafted only when the
  title says chunky (bulky). `small_parts.blocking` is still run at draft.
- Refused by name:
  - axolotl (gills fail small parts)
  - hedgehog (spines are a texture)
  - unicorn
  - any texture word
  - size words
  - "no-sew" (the face is embroidered and the closure is sewn, so it is low-sew, never no-sew)
  - more than one toy
  - unknown words
- On the premise, an accessory (holding, stone, scarf...), patches, spikes, gills or safety eyes
  are a named hold.
- Routing:
  - `FC.plan` tries the ball-body route first. If that refuses, it tries `animals.route`.
  - `CF.route` relabels a declared `amigurumi` as the animal family. It also strips the
    engine's own "joined legs/bill/wings" phrasing before the named-feature check.
  - `PAIR_PROOFS` has entries for `amigurumi` and `toy`.
  - The draft dispatch is in `runtime/pipeline.py`, and the intake treats the family as
    engine-sized.
- `outline_round` is now honest for the ball-body `amigurumi` family, whose route already allows
  "round".

### 4. Nursery: the lamb lovey head (`creative/baby.py`)

`LOVEY_HEADS["lamb"]` uses the same closed 36-st head as the bear, with a drooping lamb ear
(4 plain rounds). "Sleepy" gives an embroidered closed-eye face. "Little Fox Lovey" stays held
("little" is a size word, and there is no fox head). Blanket variants were not changed: baby
blankets are already the verified flat-panel family.

## Routing result on the demand catalogue

**Now admitted (8):**
- low-sew-puddle-frog-amigurumi
- riverbank-capybara-amigurumi
- chunky-marsh-duckling-plush
- low-sew-meadow-lamb-amigurumi
- chunky-harbour-whale-plush
- chunky-tidepool-octopus-plush
- cosy-round-bear-amigurumi
- simple-round-teddy-bear

The lamb lovey head is also routable (`Sleepy Lamb Lovey` routes to `lovey`). However,
`sleepy-lamb-lovey` in the catalogue is declared `baby`, form `toy` and is admitted as a lovey
only by `FC.plan`. Its intake path is proven by
`test_a_research_lamb_lovey_is_physical_gated_end_to_end`.

**Still held, by name (engine demand):**
- axolotl (gills)
- hedgehog (spines)
- otter (premise: "holding a little stone")
- cow (premise: "colourwork patches")
- dinosaur (premise: "spikes")
- little-fox-lovey

## Tests

New suite `tests/test_eng_animals.py`, 15 tests:
- **Family proof** — `test_a_research_animal_is_physical_gated_end_to_end`: a research frog goes
  intake → score → draft → compile → certify. It is withheld ONLY for
  `PHYSICAL_TEST_REQUIRED` and `CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN`. The US and UK PDFs carry
  every count, the join phrases, the stuffing and closure, the crocheted-in-joins statement and
  the safety section.
- **Round trip for all nine animals**: each one compiles; its twin sites equal `make` at the
  flattened-edge width; the assembly joins are sound; the US and UK reverse compare is clean;
  `to_dict` round-trips; only PHYSICAL_EVIDENCE is non-PASS.
- **Mutations**: one for every `LOW_SEW_*` code, the ring layout, and a stub that removes
  `low_sew.check` (it compiles a short edge clean, so the check is load-bearing).
- **Reverse**: a lost or renamed join phrase is refused.
- **Child safety and small parts**: crocheted-in pieces are inside small-parts; a mismatched
  join is never PASS; a shrunken leg is blocked; finer yarn is refused; the octopus needs chunky.
- **Routing**: admissions and holds by name. A sweep of the demand catalogue checks that every
  toy is admitted or held by a named feature.
- **Lamb lovey**: proof end to end, plus a test that the lovey refusals hold.

`tests/test_eng_families.py`:
- The new family is in the admitted set and the plain-concept / named-feature sweeps.
- New meta-guard probes (frog, whale, octopus, round ball bear, sleepy lamb lovey, lamb toy).
- New routing-admission test
  `test_shaped_animals_are_admitted_only_for_toy_categories_and_hold_unbuilt_shapes`: only the
  toy categories are admitted; the family is never admitted from other declarations; unbuilt
  shapes are held; the status gate still holds the family when it is demoted.

Other updates:
- `tests/test_eng_demand_supply.py`: the "still held" example moves from capybara (now built)
  to hedgehog.
- `tests/test_w4_fmbatch1_contracts.py`: the CIR pin is updated.

Suite run `20261121T003710Z-1430` (16 targeted suites, dirty tree): 275 passing, 2 suites
failing. `test_concepts100` fails identically on base (pre-existing, untouched).
`test_eng_demand_supply` failed on base; after the `outline_round` fix it exposed a harness id-reuse
DuplicateJob, fixed in the test; re-run alone: 0 failed. The two contracts suites pass.

## Things to look at hard

1. **`child_safety._joins`.** Please confirm no path returns PASS for a toy whose crocheted-in
   joins were not all measured. I believe the expected-count check covers this.
2. **Small parts and long tubes.** Small parts measures a long tube from a magic ring as a disc.
   That is conservative and I kept it. It is the reason the appendages are wide, not slim.
3. **Head stuffing.** The head is stuffed through the neck. That is a row note; the one
   structured stuffing point is after the body's 18-st round. `closed_forms` passes. A physical
   sample is still required (HELD).
4. **Single-back placement.** A tail or fluke starts at st 1 of a round that begins at the centre
   back, so it is offset by half its edge from true centre. This is stated in the body note.
   Symmetry is not checked.
5. **"Chunky".** A chunky title drafts at bulky whatever the concept's `yarn_weight` says. The
   materials list and gauge state bulky.
