# Handoff W4-PIPE (product pipeline)

Branch `claude/w4-PIPE` (worktree `.claude/worktrees/W4-PIPE`), latest pushed SHA: see `git log -1 origin/claude/w4-PIPE`.
Phase shadow; no deploy, no Etsy write, no spend. Production read only via public GET aggregates (evidence_PIPE/).

## Done (status → evidence)
- Inventory: `products/inventory.py` + `research/final_build/w4/product_inventory_run.py` → `PRODUCT_INVENTORY_BEFORE.{json,md}` (PROVEN: static truth + scratch chain `for_publish` verdict + production snapshot).
- Name-truth publication gate for every product (`publish.eligibility.name_truth`, reason `NAME_OUTRUNS_PATTERN`): PROVEN by `tests/test_w4_pipe_name_truth.py`.
  Defect it closes: products outside Launch-0 skipped title/assembly/fabric truth at publish (only first_customer, Launch-0-only, ran them).
- nordic-star-ornaments 1.3.0 (make 6), mosaic-placemat-pair 1.3.0 (make 2, "Diamond Lattice Placemat Pair"): PROVEN (`test_release_versions`, `test_w4_pipe_board` ornaments_now_true).
- Pipeline board `products/pipeline_board.py` (+ `handle_product_pipeline` body, not yet registered) and `pipeline_run.py` → `PIPELINE_BACKLOG.{json,md}`; six new deterministic proposals all clear Product Truth (`tests/test_w4_pipe_board.py`).

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

## Next deterministic action
Finish scratch run2 (`/home/user/bl-tmp-PIPE/run_after.py`), run `product_inventory_run.py --chain-db run2 --name PRODUCT_INVENTORY` and `pipeline_run.py --chain-db run2`, commit.
