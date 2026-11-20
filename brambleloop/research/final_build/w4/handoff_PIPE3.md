# W4-PIPE3 handoff — Product Truth for the 14 non-viable catalogue products (+5 creative retitles)

Branch `claude/w4-PIPE3` (worktree `.claude/worktrees/W4-PIPE3`). Latest pushed SHA: see `git log -1 origin/claude/w4-PIPE3`.
Merged: origin/claude/visual-investigation, origin/claude/w4-PIPE (nordic-forest conflict resolved — PIPE's
1.3.0 relief rename kept, title shortened by PIPE3 within the same unreleased 1.3.0 bump).

Proof: `cd brambleloop && PYTHONPATH=src python research/final_build/w4/pipe3_run.py [slug ...]` (real
release chain gate.certify→listing.draft→assets.build→pricing.position→listing.seo, shadow worker,
scratch SQLite, network closed). Evidence: `evidence_PIPE3/pipe3_run.json` (`product_truth_ok`, `listing_truth_ok`).

## Per product (14 = 12 here + 2 owned by W4-PIPE)
| Product | Status | Evidence / gate |
|---|---|---|
| autumn-oak-mosaic-throw | PROVEN 1.4.0 | re-derived from worsted (builder.YARN_DERIVED); 1.3.0 typed gauge still refused via `builder.as_drawn` (test_launch0_gauge) |
| cottage-wall-hanging | PROVEN 1.3.0 | chain OK (W4-PIPE retitle + rod-pocket seam) |
| mosaic-placemat-pair | PROVEN 1.3.0 | chain OK |
| pressed-flower-motifs | PROVEN 1.3.0 | `release.SEED_CORRECTIONS` files it as `applique` (no "flower"/"pressed" in listing); category.py `applique` node |
| spooky-garland, valentine-heart-garland | PROVEN 1.3.0 | chain OK (W4-PIPE cord+seams) |
| nordic-forest-mosaic-throw-{baby,throw,large} | PROVEN 1.3.0 | "Nordic Forest Relief Throw / Baby Blanket / Large Blanket" — PIPE's longer title failed TITLE_FRONT_SCAN in listing.seo; listing handler files one-colour-per-row fabric as `blanket` |
| chunky-ribbed-scarf 1.0.0, heirloom-cable-blanket 1.2.0, bobble-floor-pillow 1.4.0 | OWNER-GATED (physical) | Product Truth otherwise clean (compile, name/assembly/fabric truth); certify refuses UNCALIBRATED_PRIMITIVE (scarf fpdc/bpdc; cable fpdc/bpdc/cable2x2; pillow bob) until a measured physical sample calibrates them — OWNER_ACTIONS `tester_outreach` (gate tester_roster). Not weakenable. |
| nordic-star-ornaments, winter-village-graphghan | W4-PIPE's (promoted to Launch-0) | not touched here |

5 creative retitles: done by W4-PIPE (handoff_PIPE.md); PIPE3 verified listing-level name truth via the chain.

## Tests run (focused, all pass)
test_release_versions, test_launch0_gauge 5, test_w4_pipe_name_truth, test_texture 25, test_w4_pipe_board 57, test_cir_roundtrip, test_pattern_truth, test_fabric_relief 8, test_gates 44, test_products_adversarial 15, test_deliverable_qa 61, test_launch0, test_v11_seo_taxonomy 4, test_v11_seo_truth 9, test_w4_pipe_launch_promotion 18, guards test_vacuity/test_secret_scan/test_w3_tmp_hygiene/test_reachability.

## Remaining / next
- Lane work complete. bobble-floor-pillow readability OPEN-DEFECT: FIXED 1.4.0 (back = foundation + whole 4-row blocks, 61 rows; prints 5 Row lines). test_texture 25 OK, test_w4_pipe_board 57 OK.
- WIRING REQUEST W4-CREATIVE: drop the 5 retitled slugs from `creative.emotional_brief.HELD` (see handoff_PIPE.md).
