# Independent review A2: P0-NAME-OBJECT (origin/opus2/a2-name-object)

Range reviewed: `db463142..3be8262f`. The commits are 5eb5d338 (motif_promise added to name_truth), 1fc30ac9 (name/object contract in `FC.plan`) and 3be8262f (the motif check scoped to rule-drafted CIRs).
Reviewer: independent and read-only. Reviewed on 2026-11-02 (UTC). No branch was modified. No deploy, no publish, no spend, no Railway.

## Verdict: **DO NOT SHIP** (as is)

The core contract is a real improvement. Every named OPUS2T, OPUS2U and OPUS2V repro is refused in every category, the radar routes are unchanged, the catalogue is byte-identical, the branch merges cleanly into INTEG1 7c42e706, and every key suite passes on the merged tree. The branch still cannot ship as it stands, for these reasons:

- The publish-time motif gate it adds can be bypassed with fullwidth or math-alphanumeric letters (A2-1, HIGH).
- The rule-drafted scoping exempts the radar flat-panel production path and the creative prototype path (A2-2, HIGH).
- The "strip trailing descriptors" rule strips any parenthesis or dash/colon clause, not just colours. As a result "Basket (Lidded)", "Basket — Giant" and "Storage Basket: with Lid" draft at medium with `name_truth == []` (A2-3, HIGH). One of these is pinned as legitimate by the new test.
- One required legitimate title, "Toy Basket", is now refused (A2-5).

## Findings

| ID | Sev | Finding | Repro |
|---|---|---|---|
| A2-1 | **HIGH** (Product Truth; same class as OPUS2T-4) | **The route reads a folded title, but the publish gate it hands off to does not fold.** `name_object_contract` NFKC-folds the title (`fold_title`), sees "heart", and lets it through as "measured by a publish-time gate". `launch0.motif_promise` reads `str(text).lower()` with `[a-z]+`, so "Ｈeart" yields "eart" and no motif word is found. Result through `pipeline.handle_cir_draft`: "Ｈeart Basket" and "𝐇eart Basket" (math bold) draft a plain vessel. "𝐒nowflake Basket" does the same on the merged tree. The CIR title keeps the fullwidth form, `motif_promise.backed == True` and `name_truth == []`. The listing-schema `_COMPATIBILITY_FORM` check may refuse such a title on an Etsy payload, but `seo/truth.py` NFKC-normalises. The end-to-end listing outcome is **UNKNOWN** (not verified, so it does not count as PASS), and the pattern PDF is not covered by that check. *Fix:* fold inside `motif_promise` (and `colourwork_claims`) with the same `fold_title`, or have the route refuse any title whose NFKC form differs from the raw title. Pin "Ｈeart Basket" as refused at publish. | `a2probes/draft.py <wt> "basket\|Ｈeart Basket" "basket\|𝐇eart Basket"` |
| A2-2 | **HIGH** (Product Truth; the scoping in 3be8262f is a loophole) | **`_drafted_by_a_rule` checks only CIRs whose primitives start with `creative.fallback_constructions.` or `creative.construction_registry.`, or CIRs with no primitives.** Exemption is therefore the default, which is fail-open. Two rule-drafting producers fall outside it. (a) The **radar flat-panel fallback with known lineage, the normal production path**, records `("runtime.pipeline.concept_to_cir", "runtime.pipeline.concept_geometry:<cat>", "creative.prototype.gauge_for:…")`. Repro: a seeded rebuild (easter-egg-cosies / cloudline-baby-hat / pumpkin-cluster-set geometry) titled "Heart Blanket", "Heart Throw", "Snowflake Baby Blanket" or "Pumpkin Table Mat" drafts a striped panel with **`motif_promise.backed == False` but `name_truth == []`**. The same title with no provenance is flagged, so the test's raw-geometry probe does not reach the production path. (b) The creative tournament path (`creative.prototype.author`) is also exempt. The 5eb5d338 message ("every fallback, registry and research draft") is false for both. Excluding the engineered catalogue (by `universe()`) and the engineered pipe-board designs is reasonable, because MOTIF_DECLARATIONS has no heart-row, pumpkin-row or fir-and-star entries. The exemption should instead be keyed on *declared engineered motif primitives* (exempt only a CIR that declares a library motif such as `products.motifs.*` or `moment_candidates`), with everything else checked. Better still, add the missing MOTIF_DECLARATIONS so no exemption is needed. On whether a catalogue or hand-authored CIR named for a motif it lacks can pass: **yes**. Catalogue: 9 of 26 titles are unbacked by motif_promise and remain the product_truth/manual_adoption gate's job, which is a recorded integrator decision. Any non-catalogue CIR whose provenance is neither fallback nor registry passes as well. | `a2probes/draft.py <wt> "seed\|easter-egg-cosies\|Heart Blanket" "seed\|cloudline-baby-hat\|Snowflake Baby Blanket"` |
| A2-3 | **HIGH** (Product Truth; OPUS2V-1 survives in another form) | **`title_core` drops every parenthesis, bracket or brace, everything after " - " / ":" / " \| ", and every for/in/by/from phrase, whatever it says.** The modifier allowlist and feature-phrase check then never see these words. The following draft a plain medium vessel through `handle_cir_draft` with `name_truth == []`: "Storage Basket (Lidded)", "Basket (with Lid)", "Basket [Lidded]", "Basket {XL}", "Storage Basket - Giant", "Basket — Giant" (em dash), "Basket – with Lid", "Storage Basket: with Lid", "Storage Basket (Teddy Bear)", "Basket - Teddy Bear", "Basket: Teddy Bear Edition", "Storage Basket for Giant Dogs". The new test pins **"Basket (Large) - Easy" as LEGITIMATE**, a size promise drafted at medium, while "Large Basket" is refused. The assignment asked for only *colour* in parentheses to be stripped. *Fix:* strip only a closed set (a parenthesised palette colour, filler words). Run the allowlist and feature check over every other word in the title, including clause text, or refuse the title. | `a2probes/plan.py <wt> "Basket (with Lid)" "Basket — Giant"`; `draft.py "basket\|Storage Basket: with Lid"` |
| A2-4 | MED (spec gap) | **The modifier allowlist covers only VESSEL and TOTE.** FLAT_PANEL, PANEL_PAIR, TRIANGLE and COSY accept any modifier. The new grid skips them with the comment "their modifiers are judged at publish", which is false for construction and size words. "Hooded Blanket", "Giant Blanket", "Zippered Cushion"/"Zippered Pillow", "Sleepy Fox Pillow", "Teddy Bear Blanket", "Teddy Bear Hanging", "Teddy Bear Cover" (pillow), "Teddy Bear Square"/"Teddy Bear Mat" and "Fox Wrap" (shawl) all draft with `name_truth == []`. The assignment asked for a per-family allowlist of head nouns *and modifiers*. Some themed modifiers are explicitly accepted ("Polar Bear Blanket", "Bear Paw Blanket", "Bear Pillow"). Construction words (hooded, zippered, lidded, pocket) and size words (giant, xl) are not judged anywhere. | `a2probes/plan.py <wt> "Hooded Blanket" "Zippered Pillow" "Teddy Bear Cover"` |
| A2-5 | MED (acceptance criterion failed) | **"Toy Basket" is now refused** ("the title names 'toy'…"). It drafted as a vessel at db463142, and the assignment lists it as a legitimate title that must still draft. It is absent from the test's LEGITIMATE list. "Laundry", "Fruit", "Yarn", "Small" and "Large Basket" also changed from vessel to refused. That is fail-closed, so LOW on its own, but it is a product-scope regression. | `a2probes/plan.py <wt> "basket\|Toy Basket"` (base: vessel; branch: refused) |
| A2-6 | MED (test gap) | **Several acceptance repros are not pinned, and mutants that re-admit them survive.** M13 adds sunflower/owl/fox/striped/xl to the VESSEL modifiers and survives, because "XL Basket", "Sunflower/Owl/Fox/Striped Basket" and "Fox Tote" are not in REPROS. M14 adds "blanket"/"cushion" to the VESSEL heads and survives, because "Blanket" and "Cushion" under `basket` are not pinned. M18 (no NFKC fold in `fold_title`) survives `test_opus2_a2_name_object`; OPUS2T N6 is still unpinned. M16 (`with` removed from the feature phrase) survives, though it is close to equivalent because a "with X" tail usually leaves a non-head last word. M11 (universe exemption removed) survives. | `a2probes/mutate.py` |
| A2-7 | LOW/INFO (merge risk) | **The registry half of "every route" is not on this branch or on INTEG1.** `origin/opus2/p0-construction-registry` is not an ancestor of 7c42e706, and `creative.construction_registry` does not exist here, so the `_RULE_DRAFTED` registry prefix is exercised only with synthetic provenance in the test. `git merge-tree a2-name-object p0-construction-registry` **conflicts** in `fallback_constructions.py`, `runtime/pipeline.py` and COORDINATION.json. Registry-path coverage of the contract is **UNKNOWN** until that merge is resolved and re-reviewed. | `git merge-tree --write-tree origin/opus2/a2-name-object origin/opus2/p0-construction-registry` (rc=1) |
| A2-8 | INFO (verified true) | **Every assignment repro is refused in all 19 probed categories:** "Teddy Bear" (+Pattern / Crochet…Pattern / (Cream)), "Bear Cub", "Sleepy Fox", "Cat", "Teddies", "Lidded Basket", "Basket with Handles", "Giant/XL Basket", "Sunflower/Owl/Fox/Striped Basket", "Sunflower/Fox Tote". "Blanket" and "Cushion" are refused under `basket`; they draft only in their own flat or pillow families. Fullwidth, math-bold and ZWSP "Teddy Bear" variants and Cyrillic are refused. "Diamond/Heart/Snowflake/Pumpkin Basket" draft a plain vessel under `basket` only and are refused at `name_truth` by `motif:` (ASCII only, see A2-1). These still draft: Bear Paw / Basket Weave / Polar Bear Blanket, Cat Bed (pet), Christmas Stocking, Drawstring Pouch, Diamond Tapestry Basket. "Toy Basket" does not (A2-5). The 34 radar seeds route identically at base, branch, INTEG1 and the merged tree. Plurals and multi-word heads are fail-closed ("Baskets", "Storage Bin Basket", "Basket Bag" and "Bag Basket" are refused). |
| A2-9 | INFO | **Catalogue byte-identity holds.** The 40 slugs (26 engineered/flat CIRs, 4 retired aliases with no CIR, and 10 Launch-0 `product_truth` records) were compared on title, fingerprint, CIR sha256, name_truth, fabric_truth and product_truth. Base and branch are identical, and INTEG1 and the merged tree are identical. The only differing field is my probe's `plan(category="basket", title)` route on catalogue titles, which is expected because they are never routed through `plan`. **Removed or weakened assertions:** none. The two fixture title changes ("Raw" → "Raw Blanket", "Bad Concept" → "Bad Concept Blanket") keep the original assertions about lineage and compile failure. |

## Mutations (`tests/test_opus2_a2_name_object.py`, branch worktree, each reverted)

| Mutant | Result |
|---|---|
| M1 contract skipped in plan | KILLED |
| M2 feature phrase off | KILLED |
| M3 non-ASCII leftover off | KILLED |
| M4 head check off | KILLED |
| M5 modifier check off | KILLED |
| M6 no paren strip | KILLED |
| M7 "pattern" not filler | KILLED |
| M8 motif block removed from name_truth | KILLED |
| M9 `_drafted_by_a_rule` always False | KILLED |
| M10 `_drafted_by_a_rule` always True | KILLED |
| M11 universe exemption removed | SURVIVED |
| M12 measured-word exemption off | KILLED |
| M13 +sunflower/owl/fox/striped/xl VESSEL modifiers | **SURVIVED** |
| M14 +blanket/cushion VESSEL heads | **SURVIVED** |
| M15 +fox/sunflower TOTE modifiers | KILLED |
| M16 "with" removed from feature phrase | SURVIVED (near-equivalent) |
| M17 no dash/colon clause strip | KILLED |
| M18 no NFKC fold | **SURVIVED** |
| M19 pet_bed skip removed | KILLED |

## Merge-tree

`git merge-tree --write-tree origin/claude/w5-INTEG1 (7c42e706) origin/opus2/a2-name-object` gives rc=0 and tree `cb937c74`, a clean merge. A scratch commit `918347ef` was made from that tree for testing; no ref points at it. W5's launch0 "two colours" change (INTEG5G-1) and the A2 eligibility and fallback changes touch disjoint hunks.

Suites on the **merged tree**, run one at a time, all rc=0: test_opus2_a2_name_object, test_fallback_draft_provenance, test_shadow, test_w4_pipe_board, test_opus2_draft_constructions, test_opus2_pet_bed, test_opus2_stocking, test_opus2_tapestry_basket, test_opus2_drawstring_pouch, test_launch0, test_first_customer_gate, test_eligibility, test_cert_publish_gates, test_w5_integfix, test_vacuity, test_w4_listready. The commit's note that test_w4_listready fails on base no longer applies on INTEG1: it passes. Extra cir.draft consumers: see the addendum below.

## Commands

```
git -C /home/user/Project-Money fetch origin
git worktree add --detach $S/a2rev-br origin/opus2/a2-name-object      # also a2rev-base (db463142), a2rev-integ1 (7c42e706)
git merge-tree --write-tree origin/claude/w5-INTEG1 origin/opus2/a2-name-object   # cb937c74, rc=0
git commit-tree cb937c74 -p origin/claude/w5-INTEG1 -p origin/opus2/a2-name-object  # 918347ef -> worktree a2rev-merged
python a2probes/plan.py <wt> <titles…>          # route-only probe across 19 categories
python a2probes/draft.py <wt> "<cat>|<title>" "seed|<slug>|<title>"   # handle_cir_draft + name_truth
python a2probes/catalogue.py <wt>               # 40-slug digest/name_truth/fabric_truth/product_truth dump
python a2probes/routes.py <wt>                  # 34 radar seeds
python a2probes/mutate.py a2rev-br              # 19 mutants
a2probes/runsuites.sh a2rev-merged <out> <tests…>   # sequential, one suite at a time
```
`$S` = `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad`. Python: `/home/user/bl-runs/venv-integ4/bin/python`.

## Required before SHIP
1. Fold titles inside `motif_promise` and `colourwork_claims`, or refuse titles that change under NFKC (A2-1).
2. Invert the 3be8262f scope: check every non-catalogue CIR, and exempt only CIRs declaring an engineered library motif, or add the missing MOTIF_DECLARATIONS. Pin the radar flat-panel lineage case "Heart Blanket" (A2-2).
3. Strip only closed-set descriptors. Clause and parenthesis text must pass the same allowlist and feature check (A2-3). Remove "Basket (Large) - Easy" from LEGITIMATE.
4. Restore "Toy Basket" (A2-5). Pin the missing repros so M13, M14 and M18 are killed (A2-6).
5. Decide whether modifier allowlists apply to flat, pillow, shawl and cosy (A2-4, integrator).

## Addendum: extra cir.draft / plan consumers on the merged tree (sequential, all rc=0, no FAIL)
test_author_provenance, test_cert_preengineering, test_launch0_listing_truth, test_opus2_knowledge_gaps, test_originality, test_w4_research_to_product_stall, test_w5_concept_intake, test_w5_inventory, test_w4_readback_evidence, test_w4_auto_status, test_cert_design_pipeline, test_w3_laura_core_identity, test_w4_f454_agents. Not run: test_product_run, test_cert_culture_teardown, test_cert_improve_wave (long, and the certification run is using this machine). Their status is UNKNOWN.
