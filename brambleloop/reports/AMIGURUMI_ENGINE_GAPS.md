# Amigurumi engine gaps (D6, catalogue-unblock, 2026-11-22)

Every amigurumi-family `construction_unsupported` refusal on the catalogue, read from
`creative.construction_families.route` over `radar.demand_originals.CATALOGUE`,
`radar.opportunity.POOL` and the `radar.concept_pool` toy lanes on this branch. Each one is a
true refusal: the engine does not make what the title or premise sells. None is lifted by
loosening a word list. None was implemented here, because each needs new original geometry,
a small-parts reading and an end-to-end proof, so none is small.

## What the engines lack, by refusal

| Concept | Refusal | What the engine lacks |
|---|---|---|
| little-fox-lovey | lovey head names "little fox"; only bear, bunny and lamb heads exist | A **fox lovey head**: `creative.baby.LOVEY_HEADS` holds only ear variants on the closed 36-st bear head. A fox needs a pointed (triangular, decreasing) ear, a protruding snout piece worked in the round and sewn on, and a two-colour face (white muzzle/cheeks). The snout is a new sewn-on part that needs its own child-safety attachment reading. "Little" is also a size word the router refuses, so the title needs a stated design size or "little" dropped. |
| chunky-riverstone-otter-plush | premise names "holding" (an otter holding a little stone) | A **held prop**: `creative.animals` has no accessory piece and no "held between joined paws" placement. A stone is a separate stuffed or solid piece, so it needs a small-parts cylinder reading at chunky gauge and a stated attachment (sewn into the paws, never loose). Today's otter builds the otter without the stone. |
| sleepy-frog-face-cushion, dozy-bear-face-cushion | title names "face" (amigurumi_features) on the panel_pair engine | **Appliqué faces beyond the highland cow**: `creative.cushions.APPLIQUES` has one original face. Each new face needs original piece geometry (row widths, placements, colour slots, feature embroidery), and the router must treat "face" as honest for the appliqué family only when an appliqué face is drafted (today `amigurumi_features` is honest only for the toy, lovey and animal families). |
| low-sew-clover-cow-amigurumi | premise names "patches" | **Colour patches on a shaped body**: the animal engine works the body in one colour plus one contrast region (`contrast="lower"`); irregular patches need intarsia or sewn-on flat patches with their own counts and yarn quantity. |
| low-sew-fernback-dinosaur-amigurumi | premise names "spikes" | **Back spikes**: a row of small cones crocheted into the back seam. Needs the part shape and a small-parts reading per spike. |
| low-sew-hedgerow-hedgehog-amigurumi, Bramble Hedgehog | spines are a texture | **Loop or spike stitch texture** with its own counts and yardage (twin model), for the spines. |
| low-sew-pond-axolotl-amigurumi | six gills | **Small appendages under a small-parts assessment** at every drafted gauge (gills fail the cylinder today). |
| woodland-fox-amigurumi, Barn Owl, Sea Turtle, Harbour Seal, Puffin, Shore Crab, Slow Snail, Bumble Bee, Field Mouse | shape the fallback does not make | **New `creative.animals.ANIMALS` entries** (fox, owl, turtle, seal, puffin, crab, snail, bee, mouse), each original house geometry with its parts, placements and a proof. The mouse premise also says "holding its tail" (the held-prop gap above). |
| no-sew-reindeer | shape and "no-sew" | A reindeer (antlers are a stiffened or branched part) and a **no-sew construction**: the animal engine is low-sew (embroidered face, sewn closure). |
| pocket-penguin-trio | more than one toy | **One release per toy**, each certified and listed alone, plus a bundle; and a penguin entry. |
| Little Whale, River Otter, Honey Bear, Garden Bunny (concept-pool lanes) | the title names "little" (a size), "river", "honey" | Title vocabulary, not geometry: "little" is a size the one-size animal does not state; "river" and "honey" are not in `animals._DESCRIPTORS` or the ball-body vocabulary. These could be admitted by adding naming descriptors, but that is a copy-truth decision for the concept generator, not an engine gap, so it is left as is. |

## Plan, highest catalogue value first

1. **Appliqué faces (frog, bear).** Add two original entries to `cushions.APPLIQUES`; make
   "face" honest for `FC.APPLIQUE` only when `applique_for(title)` names a drafted face; add
   the proof `tests/test_eng_plush.py::test_a_research_<face>_cushion_certifies_end_to_end`.
   Risk class A (no stuffing, no hard part), so it can reach VERIFIED. About half a day.
2. **Fox lovey head.** Extend `LOVEY_HEADS` with a shape (pointed ear: increase then
   decrease) and an optional sewn snout part; add the snout to the child-safety attachment
   reading; proof in `tests/test_eng_plush.py`. Still physical-gated like every lovey.
3. **Held prop for animals.** A `Part(kind="prop")` placed between joined paws, sewn through
   both paws; small-parts reading at chunky gauge; proof in `tests/test_eng_animals.py`.
4. **New animal entries** (fox, mouse, owl first by demand), each with its proof.
5. Textures (spines, patches, spikes) and no-sew need twin and compiler work; plan after 1-4.

All of them stay physical-gated (stuffed toys for children) except the cushion appliqué.
