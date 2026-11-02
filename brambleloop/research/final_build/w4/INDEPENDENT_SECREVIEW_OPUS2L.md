# INDEPENDENT_SECREVIEW_OPUS2L: delta review of the OPUS2J J-13..J-16 stocking fixes

- **Reviewer:** an independent, adversarial, read-only Claude context. Nothing was deployed, published or spent. Railway and production were not touched.
- **Date:** 2026-11-02 (UTC)
- **Subject:**
  - `origin/opus2/p0-stocking` commit `563c0436` (diff `be12b47b..563c0436`)
  - merge `0ef8a716`, which brings in `opus2/p0-pet-bed` `7d220e01`
- **Reference findings:** J-13..J-17 in `INDEPENDENT_SECREVIEW_OPUS2J.md`. OPUS2K-7 is in `INDEPENDENT_SECREVIEW_OPUS2K.md`. The pet bed was not re-reviewed.
- **Worktrees:**
  - `wt` at `0ef8a716` for the suites and probes;
  - `mt` at `0ef8a716` for mutations, restored with `git checkout -- .` and confirmed clean.

## Verdict: **DO NOT SHIP** (the stocking route)

- **What was fixed:**
  - The literal J-13..J-16 repros are fixed and pinned.
  - All seven new guards are killed by a test (M1–M7).
  - No assertion was removed or weakened. The test diff only adds, and compile and validation are untouched.
  - The merge is a correct union of the two `plan()` routes.
- **What is still wrong:**
  - J-13 is fixed only for its prefix half ("Stocking X").
  - The suffix half is still open: "X Stocking" in category `stocking`, or in any category not in `NEEDS`, drafts the one 14 × 36 cm Christmas stocking, whatever X names.
  - X can be another product, hosiery (including **"Compression Stocking"**, a medical claim), a size, a child audience, a motif outside `MOTIF_WORDS`, or an embellishment.
  - Each of these compiles with 0 findings and passes `name_truth`, `product_type_findings`, `title_promise` and `motif_promise`.
  - This is the same closed-denylist defect as OPUS2K-7 on the pet route.

## Findings

All repros: `F.plan(category=…, title=…)` and then `F.stocking(concept)`, `compile_cir`, `name_truth`, `product_type_findings(cir, title=…)`, `L.title_promise`, `L.motif_promise` and `L.finished_objects`, with the fixture concept from `tests/test_opus2_stocking.py`. Script: a scratch probe script (114 cases, not committed). "Drafts, all pass" means family `stocking`, 0 compile findings, 0 `name_truth`, 0 product-type findings, `title_promise` backed, `motif_promise` backed and 1 object.

| ID | Sev | Finding | Repro |
|---|---|---|---|
| OPUS2L-1 | **HIGH** | **J-13, residual.** Requiring "stocking" as the last word stops "Stocking Stitch Blanket" and similar titles. But the third part of the J-13 fix ("in category `stocking`, refuse a title that names another product type") was implemented only as "has no stocking head". A title that names another product, or a different kind of stocking, before the head noun is drafted as the Christmas stocking, and no gate catches it. | Drafts, all pass, in `stocking`: "Pillow Stocking", "Garland Stocking", "Tote Stocking", "Coaster Stocking", "Ornament Stocking", "Wine Bottle Stocking", "Gift Card Stocking", "Advent Calendar Stocking". In `blanket`: "Blanket Stocking", "Blanket Stitch Stocking". In `bag`: "Tote Bag Stocking" (the tote word skips `NEEDS`). **Hosiery** in `home_decor`/`seasonal`: "Nylon Stocking", "**Compression Stocking**", "Fishnet Stocking", "Silk Stocking", "Knee High Stocking", "Thigh-High Stocking". The repo has no medical-claim gate (`grep -i compression\|medical src` finds only seasonal compression). *Fix:* the same shape as the OPUS2K-7 fix. Draft only when every word before the head is in an allowlist (for example {christmas, holiday, classic, fireside, festive, cozy, cosy, plain, simple, crochet, stripe, cuff}), and refuse everything else. Pin "Compression Stocking", "Wine Bottle Stocking", "Ornament Stocking" and "Blanket Stocking". |
| OPUS2L-2 | MED | **J-14 size and audience, residual.** Only "medium" was added. Other size and audience words still draft the one adult-size stocking. The pet route already lists "big", "xxl" and "petite" (`_PET_BED_SIZE_WORDS`); the stocking list does not. | Drafts, all pass, in `stocking`: "Big Stocking", "Huge Stocking", "Little Stocking", "XXL Stocking", "Petite Stocking", "Kids Stocking", "Baby Stocking", "Toddler Stocking", "Doll Stocking", "Super Chunky Stocking", "Chunky Stocking". The yarn-weight claim is not checked against the CIR. "Baby's First Stocking" still drafts. J-17 (children's audience) remains untraced and is UNKNOWN, not PASS. |
| OPUS2L-3 | MED | **J-14 motifs and colourwork, residual.** The motif guard reuses `launch0.MOTIF_WORDS`. That set has no Christmas figures and no stripe/check words, so common stocking motifs pass as a plain stocking and `name_truth` passes. | Drafts, all pass: "Santa Stocking", "Snowman Stocking", "Gingerbread Stocking", "Candy Cane Stocking", "Penguin Stocking", "Elf Stocking", "Holly Stocking", "Rainbow Stocking", "Striped Stocking", "Plaid Stocking", "Buffalo Check Stocking", "Argyle Stocking", "Polka Dot Stocking", "Granny Square Stocking". Embellishment and personalisation words are also unguarded: "Embroidered", "Beaded", "Tassel", "Bell", "Lined", "Stuffed", "Custom", "Named", "Lettered", "Textured", "Waffle Stitch", "Puff Stitch", "Ribbed Cuff", "Velvet", "Glitter", "Sparkle". Only "Poinsettia Stocking" is caught (`name_truth`=1). *Fix:* the allowlist in OPUS2L-1 subsumes this. |
| OPUS2L-4 | MED | **Unicode punctuation bypasses the named refusals.** `_STOCKING_NOT_PLAIN` uses `fair[- ]?isle` and `pom[- ]?poms?` (ASCII only), and the motif scan uses `[a-z]+` on un-normalised text. A non-breaking or en-dash hyphen, typical of LLM or smart-quote copy, drafts the plain stocking. | Drafts, all pass: "Fair‑Isle Stocking" (U+2011), "Fair–Isle Stocking" (U+2013), "Pom‑Pom Stocking", "Pom–Pom Stocking". Contrived variants that also pass: "Ｓnowflake Stocking" (fullwidth S) and "Snöflake Stocking". The ASCII forms are refused. *Fix:* NFKC-normalise the title and map `\p{Pd}` to "-" before routing. Mutant M9, which adds NFKC to the motif scan, survives: no test pins Unicode. |
| OPUS2L-5 | LOW | **J-14 number words, residual.** `_MULTIPLE_WORDS` stops at "six". | Drafts: "Seven Stocking", "Ten Stocking", "Dozen Stocking", "Half Dozen Stocking", "Couples Stocking", "Both Stocking", "Multi Stocking". The grammar is unusual, so the risk is low. "Twin", "Family", "Stockings" and "STOCKINGS" are refused. |
| OPUS2L-6 | LOW | **J-15 is fixed in the text only.** The note now says to place the back on the front "with the same side facing up", which is geometrically right for two identical L panels. But the second half of the J-15 fix, a handedness check in the assembly geometry, was not added. The finished stocking also shows one panel's wrong side outward, which the note does not say. In row-turned sc this is near-identical, so it is cosmetic. | `cir.assembly[0].note` on `0ef8a716`; `seam.is_placed` still ignores handedness. |
| OPUS2L-7 | LOW | **J-16 is pinned, not sourced.** The test now pins (14, 26, 22, 10) cm and the size-note sentence, so MS6 (leg 26 → 60) is killed (M7). The figures still have no cited source and are not in `products.vessels` or any measured table. The pet bed got `PET_BED_SIZE_SOURCE`, so this is inconsistent. The note's "Computed, not yet measured" is honest. | `fallback_constructions.STOCKING_*_CM`; no source constant. |
| OPUS2L-8 | INFO | **The head-noun rule fails closed on suffixes.** "Christmas Stocking!", "Christmas Stocking.", "… (Crochet Pattern)", "… Pattern", "… Ornament" and "Christmas Stocking​" are refused in `stocking`. In `home_decor` they are refused by the flat-panel shaped-word check. This is the safe direction, but a real "Christmas Stocking Pattern" concept will never draft. Trailing whitespace is stripped, but mutant M8 (strip removed) survives because no test pins it. |
| OPUS2L-9 | INFO | **Merge `0ef8a716` and OPUS2K-7.** The union is correct. `git diff 7d220e01 0ef8a716` adds only the stocking route, `STOCKING` and the `NEEDS` text, and the pet block is byte-identical. Both routes key on the last word ({bed, beds, basket, baskets, nest, nests} vs {stocking, stockings}), which are disjoint, so their order is irrelevant: mutant M10 (stocking before pet) survives as an equivalent mutant. *Interaction:* in category `pet`, a stocking title falls past the pet route into the stocking route and inherits none of the pet guards. "German Shepherd Stocking", "Dog Stocking" and "Cat Bed Stocking" draft the stocking. This is harmless for size because a pet stocking is a stocking. The reverse is OPUS2K-7: "Stocking Bed" and "Stocking Basket" in `pet` draft the 48 cm cat-bed vessel. When OPUS2K-7's allowlist lands, "stocking" must not be in the pet pre-head allowlist. |

## Mutations (worktree `mt`, `brambleloop/src/brambleloop/creative/fallback_constructions.py`, each reverted; tree clean afterwards)

Each mutant was run against `test_opus2_stocking` and `test_opus2_pet_bed`. Script: a scratch mutation runner (not committed).

| ID | Mutation | Result |
|---|---|---|
| M1 | `_STOCKING_HEAD` back to `\bstockings?\b` (J-13 head rule) | **killed** (stocking) |
| M2 | category-`stocking` no-head refusal → `if False` (J-13) | **killed** |
| M3 | `\bstockings\b` plural refusal → `if False` (J-14) | **killed** |
| M4 | motif refusal → `if False` (J-14) | **killed** |
| M5 | "medium" removed from `_STOCKING_NOT_PLAIN` (J-14) | **killed** |
| M6 | assembly note reverted to "wrong sides together" (J-15) | **killed** |
| M7 | `STOCKING_LEG_L_CM` 26 → 60 (J-16 / old MS6) | **killed** (was surviving in OPUS2J) |
| M8 | `.strip()` dropped from the stocking title | survives (fail-closed direction; OPUS2L-8) |
| M9 | NFKC added to the motif scan (hardening) | survives (no Unicode pin; OPUS2L-4) |
| M10 | stocking route moved before pet route | survives (equivalent; OPUS2L-9) |

## Removed or weakened checks

None found:
- `be12b47b..563c0436` touches only `fallback_constructions.py` (+34/−4) and `test_opus2_stocking.py` (+30/−0).
- No assertion was removed, no gate or compiler path was changed, and no deterministic validation was overridden.
- The `NEEDS["stocking"]` exemption predates this commit (`5c7b984a`).

## Commands run

```
git fetch origin claude/w5-SECREVIEW-OPUS2J opus2/p0-stocking opus2/p0-pet-bed
git show --stat 563c0436; git show --stat 0ef8a716
git diff be12b47b 563c0436 -- brambleloop/src brambleloop/tests
git diff 563c0436 0ef8a716 -- brambleloop/src/brambleloop/creative/fallback_constructions.py
git diff 7d220e01 0ef8a716 --stat; git diff 7d220e01 0ef8a716 -- …/fallback_constructions.py
git worktree add --detach <scratch>/wt 0ef8a716; git worktree add --detach <scratch>/mt 0ef8a716
cd brambleloop && pip install -r requirements.txt
PYTHONPATH=src python3 <scratch>/probe.py <scratch>/cases.txt        # 114 title/category probes
python3 <scratch>/mut.py                                             # M1–M10
for t in <suites below>; do PYTHONPATH=src:tests python3 tests/$t.py; done
grep -rniE "compression|medical|hosiery|nylon" src
```

## Suites (worktree `wt` at `0ef8a716`, run one at a time; "ok" counts `OK`/`PASS` lines)

| Suite | rc | ok | fail |
|---|---|---|---|
| test_opus2_stocking | 0 | 5 | 0 |
| test_opus2_pet_bed | 0 | 5 | 0 |
| test_opus2_draft_constructions | 0 | 18 | 0 |
| test_fallback_draft_provenance | 0 | 1 | 0 |
| test_accessibility | 0 | 11 | 0 |
| test_cert_parity_copy | 0 | 20 | 0 |
| test_cir_fibre | 0 | 20 | 0 |
| test_deliverable_qa | 0 | 61 | 0 |
| test_geometry | 0 | 44 | 0 |
| test_launch0_gauge | 0 | 1 | 0 |
| test_physfix | 0 | 46 | 0 |
| test_physical | 0 | 18 | 0 |
| test_products | 0 | 16 | 0 |
| test_products_adversarial | 0 | 15 | 0 |
| test_provenance_write_path | 0 | 19 | 0 |
| test_schematic | 0 | 6 | 0 |
| test_search_truth | 0 | 32 | 0 |
| test_shadow | 0 | 10 | 0 |
| test_w4_fmbatch1_drift | 0 | 10 | 0 |
| test_w4_launchready_engineered_cohort | 0 | 8 | 0 |
| test_w4_seo_packages | 0 | 6 | 0 |
| test_compiler | 0 | 9 | 0 |
| test_reverse | 0 | 18 | 0 |
| test_twin | 0 | 8 | 0 |

All 24 suites: rc=0, 0 failures (407 OK/PASS lines).
