# Independent delta review A2F: origin/opus2/a2-name-object @ 51f87859

Range: `3be8262f..51f87859`. Reviewer: independent and read-only. Date: 2026-11-02 (UTC). Nothing was pushed, committed, deployed or modified. The scratch worktree `a2frev` (detached at 51f87859) was removed after the review.

Commits in range:
- 9e1e1b27, 5ba84bf7, 7c42e706: INTEG1 commits. They arrive through merge **9c27ece7** (INTEG1 7c42e706 into the branch).
- **76cc4547** (SHARED): A2-1 `launch0._motif_fold` inside `motif_promise`; A2-2 `eligibility._engineered_designs()` with `_drafted_by_a_rule = slug not in _engineered_designs()`.
- **60e76dcd**: A2-3 `_split_title` / `title_extras`; A2-4 a `FAMILY_MODIFIERS` entry for FLAT_PANEL, PANEL_PAIR, TRIANGLE and COSY; A2-5 toy/laundry/fruit/yarn and small/medium/large for VESSEL, with `_SIZE_WORDS` extended; A2-6 new pinned repros (79 refused, 31 legitimate).
- **c93f9c53**: test_fallback_draft_provenance fixture "Raw Blanket" → "Everyday Blanket".
- **51f87859**: test_shadow fixture "Bad Concept Blanket" → "Everyday Blanket"; test_opus2_draft_constructions changes "Bobble Cushion" → PANEL_PAIR into "Everyday Cushion" → PANEL_PAIR, plus "Bobble Cushion" → REFUSED.

## Verdict: **DO NOT SHIP** (exact SHA 51f87859)

There is real progress. Every prior A2-1, A2-3, A2-4 and A2-5 repro is now refused or fixed. The catalogue is byte-identical to INTEG1. M13 and M18 are now killed.

The required principle, "one normalised title, one check, on every producer; no title or provenance special cases", is still not met:
- A2-2 is replaced by a **slug** special case that is fail-open for rule-drafted CIRs carrying an engineered slug, and the test pins it (A2F-1).
- There are still **several different folds**, and none of them is A1-R's `products/text_fold.fold` (A2F-2).
- The A2-5 fix adds a new name-truth defect: a title's size word can draft the **opposite** size (A2F-3).

## Findings

| ID | Sev | Finding | Repro |
|---|---|---|---|
| A2F-1 | **HIGH** (A2-2 still open in another form; a special case pinned by the test) | **`_drafted_by_a_rule(cir)` is `cir.slug not in _engineered_designs()`.** The exemption is keyed on the slug, not on what produced the CIR or what it declares. `_engineered_designs()` includes 9 non-universe slugs that have **no engineered CIR in `pipeline._engineered_cir`**: the 7 `pipeline_board.PROPOSALS` slugs, plus `first-christmas-stocking` and `teacher-chevron-pencil-roll` from `emotional_brief.candidate_concepts()`. A rule-drafted CIR under any of those slugs skips the motif check. (a) `pipeline.handle_cir_draft` (radar fallback) with slug `heart-relief-table-runner` and title "Heart Table Runner" drafts a plain panel with `motif_backed=False` and **`name_truth == []`**. The same draft under slug `a2f-x1` is flagged `motif:`. `chevron-relief-scarf` + "Snowflake Scarf" and `first-christmas-stocking` + "Heart Blanket" behave the same way. (b) This is the A2-2(b) producer: `creative.prototype.author(concept)` for `first-christmas-stocking` ("First Christmas Fir and Star Stocking", declared motifs `[]`) and `teacher-chevron-pencil-roll` ("Chevron Pencil Roll") lose the `motif:` finding under their own slug and get it under any other slug. Today `assembly:` happens to block both, but the motif check is still bypassed. The new test pins the loophole: it asserts `not _drafted_by_a_rule(replace(heart_basket, slug="heart-relief-table-runner"))`, so a plain "Heart Basket" vessel under that slug is exempt. *Fix:* exempt only a CIR whose own content declares an engineered library motif, or one that is byte-equal to the engineered builder's output for that slug. Never exempt by slug alone. Remove the pinning assertion, and pin "Heart Table Runner" under `heart-relief-table-runner` as flagged. | `a2probes/slugex.py <wt> "heart-relief-table-runner\|runner\|Heart Table Runner" "a2f-x1\|runner\|Heart Table Runner" "chevron-relief-scarf\|scarf\|Snowflake Scarf" "first-christmas-stocking\|blanket\|Heart Blanket"` |
| A2F-2 | **HIGH** (the "ONE shared fold" requirement is not met; concrete bypasses) | **There is no single fold.** At 51f87859 a title is read four different ways: `fallback_constructions.fold_title` (NFKC + dashes + lower), the new `launch0._motif_fold` (NFKC + drop Cf/Cn/Mn/Me), `_basket_size` (`.lower()` only) and `asset_truth.check_technique_claims` (`.lower()` only). A1-R's `products/text_fold.fold` (1dd257be) is a fifth, and it is the one the assignment requires. `_motif_fold` is weaker than it: it has no look-alike table and does not drop Lo fillers. `_motif_fold("Неart")` = 'неart' (Cyrillic Н/е), `"Ηeart"` = 'ηeart' (Greek), `"Heㅤart"` and `"Heaᅟrt"` (Hangul fillers) are kept, and none of these is found as "heart". The route refuses these in a *title* (non-ASCII leftover), but `manual_adoption` calls `motif_promise` on the **live Etsy title, description and tags** with no route in front of it, so a look-alike "Неart" passes there. Bypasses through words the route admits after folding but the downstream check reads unfolded: **"Ｒibbed Scarf"** (scarf) and **"𝐑ibbed Blanket"** draft a plain `['sc']` panel with `name_truth == []` and **0** technique findings. The ASCII "Ribbed Scarf" gets 1 certificate finding. "ribbed" is newly listed in the FLAT_PANEL allowlist (60e76dcd). **"Ｌarge Basket"** drafts at *medium*, because `_basket_size` does not fold. Merging A1-R (1dd257be) leaves both `text_fold.fold` and `_motif_fold` in the tree. *Fix:* one fold function (A1-R's `text_fold.fold`, merged first) used by `fold_title`, `motif_promise`, `colourwork_claims`, `_basket_size`/`_SIZE_WORDS` and `check_technique_claims`. Pin a Cyrillic or Greek motif word through `motif_promise(texts=…)`, and pin "Ｒibbed Scarf". | `a2probes/tech.py <wt> "scarf\|Ｒibbed Scarf" "blanket\|𝐑ibbed Blanket"`; `a2probes/size.py <wt> "Ｌarge Basket"`; `python -c "from brambleloop.products import launch0 as l; print(l._motif_fold('Неart'))"` |
| A2F-3 | **HIGH** (new in 60e76dcd; Product Truth, a name promising a size it is not) | **The size word drafts the wrong size.** `_basket_size` takes the first substring hit in the order bread → small, market → large, small, medium, large. All of the following draft through `handle_cir_draft` with `name_truth == []`: **"Small Market Basket" → large**, **"Large Bread Basket" → small**, "Medium Bread Basket" → small, **"Market Basket (Small)" → large**, "Basket - Small - Large" → small, and "Ｌarge Basket" → medium (A2F-2). Before 60e76dcd, small/medium/large were not VESSEL modifiers, so these titles were refused. The code's own comment says "a size word is admitted only where the builder honours it". The test pins only small < plain < large; mutant M26 (reversed priority) survives. *Fix:* refuse a title with more than one size word, or with a size word that conflicts with bread/market; read the size from the folded words. | `a2probes/size.py <wt> "Small Market Basket" "Large Bread Basket" "Market Basket (Small)"`; `draft.py <wt> "basket\|Small Market Basket"` |
| A2F-4 | MED (A2-4 principle not applied uniformly) | **The new allowlists admit texture and construction words the plain builder does not make.** FLAT_PANEL lists "ribbed", "stripe/striped", "basket", "weave", "paw", "polar", "bear", "wall", "door" and "village". As a result, "Ribbed Blanket", "Ribbed Throw", "Ribbed Scarf", "Basket Weave Blanket", "Weave Blanket", "Bear Blanket", "Paw Blanket" and "Polar Blanket" draft plain sc. PANEL_PAIR "bear" makes "Bear Cushion" draft. Meanwhile the delta refuses "Bobble Cushion" for exactly this reason ("a texture the construction does not make is never drafted plain"). "ribbed" relies on the certificate's technique check, which does not fold (A2F-2). "basket weave" is measured by nothing. Some themed words (Polar Bear, Bear Paw, Bear Pillow) come from the assignment's legitimate list, and the integrator owns that; standalone "Bear", "Paw" and "Weave" are wider than that list. | `a2probes/plan2.py <wt> blanket "Ribbed Throw" "Weave Blanket" "Paw Blanket"`; `tech.py <wt> "blanket\|Ribbed Blanket"` |
| A2F-5 | MED (test gap; prior A2-6 partially open) | **The prior-review mutants are not all killed.** M14 (+blanket/cushion as VESSEL heads) still **SURVIVES**: under `basket`, "Blanket", "Cushion", "Storage Blanket" and "Everyday Cushion" would draft as a vessel, and none is pinned. The commit's claim that it is killed is false. M11d (drop the emotional_brief exemption) survives, which shows that exemption is unpinned (see A2F-1). M21 (`_motif_fold` keeps Cf/zero-width), M26 (size priority) and M32 (only the first dash clause read: "Basket - Cream - Giant") survive. M16 and M24 survive as near-equivalent: a "with/and" inside the clause still fails the allowlist. | `a2probes/mutate2.py <wt> M14 M11d M21 M26 M32` |
| A2F-6 | LOW (merge) | **Conflicts are limited to COORDINATION.json.** `git merge-tree` against 1dd257be (A1-R) and 230b7d8d (A4b) conflicts only in **COORDINATION.json**. `launch0.py` auto-merges with A1-R, but the result carries two folds (A2F-2). Merges with 3dc3e68c (A4a) and ebead3dd (A6) are clean. INTEG1 7c42e706 is an ancestor. | `git merge-tree --write-tree --name-only 51f87859 1dd257be` (rc=1) |
| A2F-7 | INFO (verified) | **The two seed refusals are correct and change no product.** `bobble-floor-pillow` and `chunky-ribbed-scarf` are routed to engineered builders (`pipeline._ENGINEERED` → `products.texture`), so `cir.draft` never uses the fallback for them (probe: `ENGINEERED`). The engineered CIRs do work the technique: `['bob','sc']` and `['bpdc','fpdc','sc']`. The fallback route refusing them is correct, because a plain panel has neither (texture.py records the earlier plain sc/dc version). **Catalogue byte-identity vs INTEG1 7c42e706:** 40/40 slugs have identical title, fingerprint, CIR sha256, name_truth, fabric_truth and Launch-0 product_truth. The only difference is my probe's `plan(category="basket", catalogue title)` column, which is expected because INTEG1 has no contract and catalogue titles are never routed. |

## Prior findings (A2-1..A2-7)

| ID | Status at 51f87859 |
|---|---|
| A2-1 | **Fixed for the probed cases, but the fold is not shared (A2F-2).** "Ｈeart Basket", "𝐇eart Basket" and "𝐒nowflake Basket" now get `motif:` in name_truth. "Hеart" (Cyrillic), "Ηeart" (Greek), ZWSP and Hangul-filler titles are refused at the route. |
| A2-2 | **Partially fixed.** The radar flat-panel lineage repros are flagged: "Heart Blanket", "Heart Throw", "Snowflake Baby Blanket", "Pumpkin Table Mat" and "Ｈeart Blanket" (seeded) all get `motif:`. A slug-keyed exemption replaces the provenance scoping and is fail-open for engineered-but-unbuilt slugs, including the creative prototype path (A2F-1). **OPEN.** |
| A2-3 | **Fixed.** All 12 prior repros are refused, plus about 50 extra clause, bracket and punctuation variants ("Storage Basket (Teddy Bear)", "Basket — Giant", "Basket {XL}", "Storage Basket: with Lid", nested and full-width parentheses, ";", "~", "/", "w/", "Basket (Cream) [Giant]", "Basket in Teddy Bear Shape"). Colour, filler and "Edition/for You" clauses still draft. "Basket (Large) - Easy" now drafts at *large*. |
| A2-4 | **Fixed for the listed repros.** Hooded/Giant Blanket, Zippered Cushion/Pillow, Sleepy Fox Pillow, all Teddy Bear variants, Fox Wrap, Giant/Bunny Egg Cosy, and Fox Tote are refused. The allowlist contents are too wide (A2F-4). |
| A2-5 | **Fixed.** Toy, Laundry, Fruit and Yarn Basket draft. The size words introduced the new defect A2F-3. |
| A2-6 | **Partially fixed.** M13 and M18 are now KILLED. M11 is split: always-True, universe-only and the board exemption are KILLED; the emotional_brief exemption **SURVIVES**. **M14 SURVIVES.** M16 survives (near-equivalent). |
| A2-7 | Unchanged. The registry branch is not merged, so registry-path coverage is **UNKNOWN**. |

## Test-change audit

Against INTEG1 7c42e706, four test files differ. I checked the author's issue #28 comment 6589003363 against the actual diff, and its 3-row table is **accurate**.
- `test_fallback_draft_provenance`: "Raw" → "Everyday Blanket". Fixture only; all assertions unchanged. Equal coverage.
- `test_shadow`: "Bad Concept" → "Everyday Blanket". Fixture only; it still asserts the compile failure, and `test_a_concept_whose_maths_fails_dies_at_compile` passes. Equal coverage.
- `test_opus2_draft_constructions`: "Bobble Cushion" → PANEL_PAIR becomes "Everyday Cushion" → PANEL_PAIR, plus "Bobble Cushion" → REFUSED. Routing coverage is kept and one assertion is added. The flip is justified.
- `test_opus2_a2_name_object` is new against INTEG1.

**Omission in the author's table:** it covers only INTEG1 → head, and it leaves out the semantic change *inside* `test_opus2_a2_name_object` against the last reviewed 3be8262f:
- (a) The provenance loop used to assert that `products.moment_candidates._disc` was **not** flagged. It now asserts it **is** flagged. This is consistent with fail-closed, and coverage is stronger.
- (b) **A new assertion pins the slug exemption:** a plain "Heart Basket" given slug `heart-relief-table-runner` is not rule-drafted. This assertion encodes the A2F-1 loophole, and it should be removed or inverted.
- (c) The grid no longer skips FLAT_PANEL, PANEL_PAIR and TRIANGLE bare modifiers and adds " (Giant)" and " - Lidded" tails. Coverage is stronger.
- (d) REPROS 48 → 79 and LEGITIMATE 24 → 31; a size-ordering assertion is added.
- (e) Radar-seed `before` gains 5 pinned seeds, including the 2 deliberate refusals.

**No assertion was removed or weakened**, other than (b), which adds coverage of the wrong behaviour.

## Suites (worktree at 51f87859, one at a time, on a shared machine with load average about 8)

| Suite | Result |
|---|---|
| test_opus2_a2_name_object | PASS (3s) |
| test_fallback_draft_provenance | PASS (18s) |
| test_shadow | First run TIMEOUT at 1800s (rc=124) under machine load, with every test reported up to that point OK (including the changed compile-failure test). Rerun with a 4500s limit: **PASS** (rc=0, 2712s, 10/10 OK; the slow test is `test_open_incident_halts_certification`, which also times out on other reviewers' branches under this load) |
| test_opus2_draft_constructions | PASS (46s) |
| test_launch0 | PASS (73s) |
| test_first_customer_gate | PASS (269s) |
| test_eligibility | PASS (31s) |
| test_cert_publish_gates | PASS (179s) |
| test_w5_integfix | PASS (6s) |
| test_vacuity | PASS (17s) |
| test_w4_listready | PASS (165s) |

## Mutants (`a2probes/mutate2.py`, test_opus2_a2_name_object, each reverted)

| Result | Mutants |
|---|---|
| **KILLED** | M11a always-True; M11b universe-only; M11c drop board; M11e always-False; M13; M18; M20 motif_fold=lower; M22 extras never kept; M23 extras not judged; M25 no size words; M27 +hooded/giant flat; M28 +zippered/teddy pair; M29 +fox triangle; M30 strippable +lidded/giant; M31 -toy |
| **SURVIVED** | M11d drop emotional_brief; **M14 +blanket/cushion VESSEL heads**; M16 (near-equivalent); M21 motif_fold keeps Cf; M24 feature ignores extras (near-equivalent); M26 size priority reversed; M32 only first clause |

## Merge-tree (51f87859 vs …)

| Branch / SHA | Result |
|---|---|
| origin/claude/w5-INTEG1 (7c42e706) | Ancestor; clean (rc=0) |
| 1dd257be (A1-R) | **Conflict in COORDINATION.json only** (launch0.py auto-merges, leaving two folds) |
| 3dc3e68c (A4a) | Clean |
| 230b7d8d (A4b) | **Conflict in COORDINATION.json only** |
| ebead3dd (A6) | Clean |

## Required before SHIP

1. Replace the slug exemption with a content- or builder-identity check, and remove the pinning assertion (A2F-1).
2. Merge A1-R's `text_fold.fold` and use it for every reader of title words: route, motif, colourwork, size and technique (A2F-2).
3. Make size words unambiguous (A2F-3), and drop texture words with no measuring gate from the allowlists (A2F-4).
4. Pin "Blanket" and "Cushion" under basket so M14 is killed, and pin the size-conflict and multi-clause cases (A2F-5).

Open as before, for the owner or integrator: 9 catalogue titles are unbacked by motif_promise.

Probes: `$S/a2probes/{draft,plan,plan2,size,tech,slugex,mutate2,catalogue}.py`, where `$S` = `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad`. Logs are in `$S/suites_a2f/`.
