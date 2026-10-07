# Handoff W4-PIPE (product pipeline)

Branch `claude/w4-PIPE` (worktree `.claude/worktrees/W4-PIPE`). Phase shadow; no deploy, no Etsy write, no spend.

## Done
- `src/brambleloop/products/inventory.py`: per-product inventory (static Product Truth now, chain DB evidence, production snapshot), blockers classified COMPANY/OWNER/EXTERNAL/DATA/DEPLOY.

## In progress
- Scratch shadow chain run (plan.cycle → store.publish) for chain evidence; PRODUCT_INVENTORY.json/.md.

## Next deterministic action
- Run `research/final_build/w4/product_inventory_run.py` → write PRODUCT_INVENTORY.json/.md; then execute company-side fixes per product.

## Wiring requests
- (none yet)
