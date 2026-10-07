# Handoff W4-PIPE (product pipeline)

Branch `claude/w4-PIPE` (worktree `.claude/worktrees/W4-PIPE`), latest pushed SHA: see `git log -1 origin/claude/w4-PIPE`.
Phase shadow; no deploy, no Etsy write, no spend. Production read only via public GET aggregates (evidence_PIPE/).

## Done (status → evidence)
- Inventory: `products/inventory.py` + `research/final_build/w4/product_inventory_run.py` → `PRODUCT_INVENTORY_BEFORE.{json,md}` (PROVEN: static truth + scratch chain `for_publish` verdict + production snapshot).
- Name-truth publication gate for every product (`publish.eligibility.name_truth`, reason `NAME_OUTRUNS_PATTERN`): PROVEN by `tests/test_w4_pipe_name_truth.py`.
  Defect it closes: products outside Launch-0 skipped title/assembly/fabric truth at publish (only first_customer, Launch-0-only, ran them).
- nordic-star-ornaments 1.3.0 (make 6), mosaic-placemat-pair 1.3.0 (make 2, "Diamond Lattice Placemat Pair"): PROVEN (`test_release_versions`, `test_w4_pipe_board` ornaments_now_true).
- Pipeline board `products/pipeline_board.py` (+ `handle_product_pipeline` body, not yet registered) and `pipeline_run.py` → `PIPELINE_BACKLOG.{json,md}`; six new deterministic proposals all clear Product Truth (`tests/test_w4_pipe_board.py`).

- RESUME 2026-10-07: merged origin/claude/w4-INTEG (intel/findings.py, MJS_FINDINGS.json) and
  origin/claude/w4-CREATIVE (creative/emotional_brief.py). Board now carries `creative` candidates
  (8 briefs, at DESIGN with exact engineering named) and `intelligence` candidates (uncovered
  benchmark arenas from mjs.findings coverage_gaps; answered arenas not repeated), two
  finding-driven proposals (fir-star-relief-table-runner, basketweave-textured-hand-towel; both
  certify + name-true), bundle families (mjs.findings bundle_premium). A proposal citing a finding
  that is not on file is INTELLIGENCE UNKNOWN. Handler reads `intel.findings.latest(ctx.db)`.
- Name truth: `launch0.ASSEMBLED_FORMS` += pillow, cushion, cosy, cozy, pouch, pencil roll, stocking.
  Finding: `bobble-floor-pillow` "Bobble Floor Pillow Cover" is one front panel with 0 seams →
  now PRODUCT_TRUTH FAIL clearer COMPANY (add back panel + closing seam, new version) as well as
  the OWNER stitch calibration. PROVEN `test_w4_pipe_board::pillow_front_only_fails_name_truth`.

- CREATIVE request (2) — 5 HELD titles retitled truthfully (builder 1.3.0; ornaments 1.4.0), fingerprints re-pinned:
  winter-village-graphghan → "Winter Snowfall Relief Throw" (certifies; snowfall-textured-throw proposal withdrawn as duplicate);
  autumn-oak-mosaic-throw → "Fir and Star Relief Throw" (name-true; still LEGACY_HELD gauge refusal, pinned by test_launch0_gauge);
  nordic-star-ornaments → "Nordic Snowflake Ornament Set (6)"; pressed-flower-motifs → "Heart Appliqué Motif Library (12)" (pieces=12);
  cottage-wall-hanging → "Cottage Chevron Wall Hanging" + rod-pocket self-seam (`Design.assembly`, join verdict sound).
  WIRING REQUEST W4-CREATIVE: drop these 5 from `emotional_brief.HELD` and add CATALOGUE_BRIEFS so they rejoin the gate.
- CREATIVE request (1) — engineering queue: `teacher-chevron-pencil-roll` engineered (`pipeline_board.pencil_roll_cir`:
  chevron relief body + tie strip + pocket-fold placed self-seams + tie seam). Others need builders the tiler lacks:
  first-christmas-stocking (in-the-round + heel shaping AND fir-and-star colourwork, which the CIR cannot express:
  `launch0.per_stitch_colour_expressible()` False), key basket / ring pillow (in_the_round), tea cosy (seamless_tube),
  cable wrap (side_to_side + uncalibrated cable = OWNER tester), advent garland (motif_join), kneeler (modular_panels).

- Imagery name truth: `eligibility.name_truth` also refuses imagery the CIR motif does not depict, in the
  title and in the drafted listing copy (`creative.emotional_brief.title_conflicts`). `runtime.release._motifs_for`
  no longer puts a retitled product's old slug imagery/colourwork words back into its listing (replaced by motif
  words; untouched products unchanged). PROVEN `test_w4_pipe_name_truth` (21 OK).
- Owner directive (live_listings): `PRODUCT_INVENTORY.{json,md}` "launch_candidates" = products with zero COMPANY
  blockers and the gates passed/remaining per product. The 5 Launch-0 products (cloudline, hexagon coasters,
  3 market baskets) are there: remaining = etsy_taxonomy_snapshot (EXTERNAL: deployed app's Etsy read →
  listing.taxonomy_refresh), physical_sample (OWNER/tester), etsy_remote_confirmation (EXTERNAL), durable_artifact_storage
  (OWNER: object storage), production_stale/imagery (DEPLOY). Next 7 truthful products (wall hanging, placemat,
  ornaments, heart library, snowfall throw, pet mat, harvest runner) are held only by Launch-0 scope (cap 5 pinned by
  test_launch0; owner ruling D-FB-9 on catalogue depth) → imagery verifier authority (D-FB-7) follows scope.

## Tests run (focused)
test_w4_pipe_name_truth 12, test_w4_pipe_board 31, test_launch0 52, test_release_versions 4, test_cert_growth_seasonal 24 — all OK. Others in the batch: see final report.

## WIRING REQUESTS
1. **W4-AUTO — register the board handler** (runtime/pipeline.py or release.py, wherever handlers live):
   ```python
   @handlers.register("product.pipeline")
   def handle_product_pipeline(ctx: JobContext) -> dict:
       from ..products import pipeline_board
       return pipeline_board.handle_product_pipeline(ctx)
   ```
   and in `runtime/worker.py` CADENCES:
   `("product_pipeline", "orchestrator", "product.pipeline", 24 * 60 * 60),`
   (agent must be permitted to enqueue `cir.draft`; if `orchestrator` is not, use `crochet_engineer` and add `product.pipeline` to its job types in agents/registry.py). Input `{"visual": false}` by default (renders cost ~35 s each); a weekly `{"visual": true, "merge_chain": true}` run is the full board.
   Why: the radar portfolio never selects `hexagon-coaster-set` (its concept slug `hexie-coaster-set` is retired and not selected), so the autonomous plan.cycle never builds a Launch-0 product (scratch run 2026-10-07: 0 jobs for it). The handler queues `cir.draft` for unbuilt Launch-0 slugs only.
2. **W4-CREATIVE (do not weaken the gate)** — VISUAL-stage findings from the board: (a) `visual.render_verification.authoritative_cir` is Launch-0-only (D-FB-7), so every non-Launch-0 disclosed render is structural UNKNOWN; (b) `harvest-table-runner` (autumn palette wine/gold) is refused by the renderer: "palette too close to a contract colour to measure". No change requested to thresholds; recorded so creative can decide whether a palette remap per product is a truthful option.

## Remaining (exact gate)
- Garlands (spooky, valentine), cottage wall hanging: COMPANY — need a real assembly design (pennant component make=N + cord component + named-edge Seams; `cir.assembly`), not a make>1 that merely satisfies `assembly_promise`.
- Mosaic/graphghan throws (nordic-forest, autumn-oak, winter-village), pressed-flower library: COMPANY — need per-stitch colour in the CIR (`launch0.per_stitch_colour_expressible()` False) or retirement; snowfall-textured-throw proposal carries the winter demand truthfully meanwhile.
- Launch-0 promotion of truthful reserves (pet-snuggle-mat, harvest runner, proposals) is capped at 5 by tests/test_launch0.py and coupled to the open D-FB-9 owner ruling on catalogue depth (8).
- Production is stale (1.0.0/chain 7 vs 1.2.0/chain 8): DEPLOY gate (integrator/owner), then chain.rebuild.

## Tests run this resume (all OK)
test_w4_pipe_board 51, test_w4_pipe_name_truth 21, test_launch0 52, test_launch0_gauge 1, test_launch0_listing_truth 14,
test_release_versions 4, test_eligibility 34, test_first_customer_gate 12, test_risk_matrix 17, test_first_hundred 16,
test_search_truth 32, test_w3_k1_search 20, test_w4_creative_brief 13, test_creative 11, test_cert_growth_seasonal 24,
test_blind_review 11. Guards (vacuity, secret_scan, reachability, tmp_hygiene): see final commit.

## RESUME 2 (2026-10-07, after session limit) -- owner directive: strongest products to the final publication gate
- Merged origin/claude/visual-investigation (878bd50). WIP checkpoint d648bc4 reviewed: inventory/backlog
  were generated from scratch run4 (fresh chain, head e72f086) -- valid; the board run that died is superseded.
- Measured why no non-Launch-0 product can reach the gate: disclosed imagery authority is Launch-0 scope
  (`listing_asset._in_launch_scope`, `render_verification.authoritative_cir`). Scratch render probe of every
  truthful certified non-Launch-0 product: ornaments, snowfall throw, placemat pair, heart library = 3/3 frames
  structural PASS + usable; pet mat + harvest runner = renderer palette refusal; wall hanging = 340 px legibility 22%.
- PROMOTED into Launch-0 (cap <=5 candidates kept; harvest reserve kept out): `nordic-star-ornaments`
  (Nordic Snowflake Ornament Set (6), CA$4.50, pod ornaments) and `winter-village-graphghan` (Winter Snowfall
  Relief Throw, CA$7.50, pod blankets) -- `products/launch0.py` BUILDERS + CANDIDATES + LAUNCH0_SLUGS.
  SEO package authored (`seo/strategy.py` FAMILIES/TAGS/TITLES/description; plan ok=True for all 5).
  Tests updated for the composition (strict counts 3->5): test_r2_product_catalogue_depth, test_w3_seo_strategy.
  Proof: tests/test_w4_pipe_launch_promotion.py (cert, name truth, authoritative_cir, frames PASS, usable).
- CREATIVE engineering queue #1 `first-christmas-stocking` ENGINEERED: `pipeline_board.stocking_cir`
  ("First Christmas Fir and Star Relief Stocking", 6 pieces, 12 seams, `cir.assembly` verdict assembles,
  certify granted, class B declared). Colourwork-in-the-round brief not expressible -> relief, titled so.
  Restructured to 8 pieces (leg/foot/toe front+back, cuff, loop), 15 seams, every join placed, 0 compile warnings,
  release_hash 37997da15179. **For W4-PIPE2**: the stocking CIR is DONE here (pipeline_board.stocking_cir,
  CREATIVE_ENGINEERED/CREATIVE_SEARCH, test_w4_pipe_board stocking_*). Pencil roll was done earlier
  (pencil_roll_cir). No other new-candidate CIR work started; PIPE2 owns the remaining 6 of the queue.
- Garlands 1.3.0 (spooky, valentine): five pennants + a side-to-side cord (`builder.Design.cord`,
  `_with_cord`), one placed seam per pennant run; certify + name-true; fingerprints re-pinned.
  Gate TIGHTENED: `launch0.assembly_promise` now needs a seam (pieces>1 alone no longer backs a
  garland/pillow/...); test_launch0 updated to the stricter expectation.
- Nordic Forest 1.3.0: retitled "Nordic Forest Fir and Star Relief Throw/Blanket (Baby|Large)" (one
  colour per row = relief, not overlay mosaic); fingerprints re-pinned (claims unchanged).
  `runtime.release._truthful_category`: a seed category naming colourwork (mosaic_blanket/graphghan)
  maps to "blanket" when the design's current title no longer claims it.
- Throw listing kind fixed: ListingIdentity.kind is the product-type FAMILY ("blanket"), else
  listing.seo refuses LISTING_PRODUCT_TYPE_UNSUPPORTED (found by scratch run5; promotion test now checks).
- product_inventory_run.py reads the chain's artifact store (<chain dir>/art) -- without it every frame
  reads structural UNKNOWN ("bound image bytes unavailable") and usable sets look unusable.
- **For W4-PIPE3 (non-viable products) -- already DONE here, do not duplicate:** the 5 creative retitles
  (winter-village, autumn-oak, nordic-star, pressed-flower, cottage-wall-hanging; earlier commits),
  garlands spooky + valentine 1.3.0 (cord + seams), Nordic Forest 1.3.0 retitle (relief), bobble pillow
  back panel + seam 1.3.0 (earlier). Still OPEN for PIPE3: OPEN-DEFECT test_texture::
  test_the_written_patterns_stay_readable fails (bobble-floor-pillow prints 12 Row lines: the plain sc
  back panel prints rows 1-7 before collapsing; front 5) -- introduced by the 1.3.0 back panel; fix in the
  writer's row-cycle collapse or the back's row schedule. Not started: pet mat / harvest runner palette
  (renderer refusal), wall hanging 340 px legibility, placemat/heart library listing words, autumn-oak
  gauge (LEGACY_HELD), cable/bobble/rib calibration (OWNER), nordic-forest-bundle (no CIR).
- Observation (not PIPE-caused, reproduced on origin/claude/visual-investigation 5660235):
  test_launch::test_a_company_that_has_done_its_half_is_only_blocked_on_people fails --
  opening_grid is no longer empty (creative survivors now visible). Owner: CREATIVE/launch lane.
- Composition pins updated (strict 3->5): test_w3_store_ux_structure, test_v11_store_foundation, test_w3_seo_learning.

## Next deterministic action (superseded below if a later commit says otherwise)
Run focused tests (test_w4_pipe_launch_promotion, test_w4_pipe_board, test_w3_seo_strategy,
test_r2_product_catalogue_depth + guards), commit+push; then scratch chain run
(`run_after.py <dir>` enqueues cir.draft for all Launch-0 incl. the 2 promoted), then
`product_inventory_run.py --chain-db <dir>/run.sqlite --name PRODUCT_INVENTORY` and `pipeline_run.py`.
