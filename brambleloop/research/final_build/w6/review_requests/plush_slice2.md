# [ENG-PLUSH] Slice 2 review request: pillows and cushions (envelope backs, appliqué faces)

- **Branch:** `eng/plush`. Not merged, not deployed. Suite and mutation results: `plush_results.md`.
- **Files that are this slice's own:**
  - `creative/cushions.py` (new);
  - `cir/assembly.py` `_surface_join`;
  - `cir/model.py` (the `surface` edge);
  - the writer and reverse surface placement;
  - the cushion routes in `fallback_constructions._plan` and `runtime.pipeline.handle_cir_draft`;
  - the `envelope_cushion` and `applique_cushion` families.

## Constructions

### `envelope_cover`

The cover is made to the standard pillow-form size (`FORMS_IN`: 16, 18 and 26 in squares and a
12 x 20 in lumbar, per `size_truth.PILLOW_FORMS`). It has three pieces:
- a sc front;
- an upper back and a lower back, each 0.65 of the height, so they overlap by 0.3 of it. This is
  an **envelope closure: no buttons, zip or ties.**

There are six joins, and `cir.assembly` measures each of them:
- each back's top or bottom edge against the front's;
- each back's side edges against exactly the rows of the front they cover (`at_round` /
  `spans_rounds` on a flat piece).

A two-colour palette works the back in the second colour. A colour the cover would not work is
refused.

### `applique_cover`

This is the same cover with a flat appliqué face from `APPLIQUES`. The only entry is the
**ORIGINAL Highland cow face**, our own geometry and no competitor's chart or photograph. Its
pieces are all flat, shaped by edge increases and decreases in plain sc:
- the face;
- a forelock;
- a muzzle;
- two mirrored ears;
- two mirrored horns.

Eyes and nostrils are embroidered, and the instruction is printed in the last appliqué step.
With a two-colour palette, the muzzle and horns are worked in the background colour.

**New join kind: `edge_b="surface"`.** A piece is laid on another, centred on a stated row and a
stated number of stitches from the centre line, and mirrored where it is a pair.
`assembly._surface_join` checks three things:
1. it lies inside the host with one stitch clear of every edge;
2. a mirrored pair does not overlap itself;
3. a closed round piece with no flat footprint is measured by its widest diameter.

The writer prints "Sew the horn onto the front centred on row 27, 14 sts from the centre line,
and the second one mirrored on the far side". The reverse compiler reads it back
independently. The compiler's existing placement checks (row exists, offset within the row)
still run first.

**Texture.** A shaggy fringe would be a loop-stitch texture, and no engine models it. So
"shaggy", "fluffy", "fringe" and the other texture words are held by name; the forelock is a
flat piece.

## End-to-end proofs (`tests/test_eng_plush.py`)

Both run the real handlers: `radar.concept_intake` → `radar.score` → `cir.draft` →
`cir.compile` → `gate.certify`.
- `test_a_research_envelope_cushion_certifies_end_to_end`
- `test_a_research_highland_cow_cushion_certifies_end_to_end`

**Certification is GRANTED.** The covers are risk class A, with no stuffing and no hard part.
The certificate shows compile, twin, assembly and reverse, no ERROR, and no OBJECT_SIZE finding.
The families are therefore **verified**.

**US and UK PDFs** both carry every row's count and the "Parts and joins" diagram and figure.

### The A1-R decision gate still holds every cushion PDF

A cover lists a pillow form, which is a non-yarn material in a seamed object, so it reads as a
closed stuffed form. **That gate is not weakened.** The e2e test satisfies it through
launch0's real decision path with a TEST decision bound to the design's digest, recorded nowhere
outside the process.

In production, every cushion PDF stays held until the owner records a decision. See the owner
action in `plush_results.md`.

## Other tests

- **Surface placements:** off the side, top or bottom, or a mirrored pair overlapping, each gives
  does_not_assemble or a compiler placement error.
- **Reverse surface:** a moved offset gives REVERSE_ASSEMBLY.
- **Texture holds, and the extra-colour refusal.**
- **Two adult cushion covers are outside the child-safety gate.** If one is assigned to a child,
  the gate applies.
