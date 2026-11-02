# Independent security and correctness review OPUS2K: Secondary's fixes for OPUS2J, 2026-11-02

Reviewer: an independent Claude Code session (branch `claude/w5-SECREVIEW-OPUS2K`).
- The review was read-only on every branch under review. This report is the only file written.
- Every probe and mutation ran in scratch worktrees in the session scratchpad and was reverted
  with `git checkout`. Each worktree was clean afterwards (`git status --porcelain`: 0 lines).
- Nothing was deployed, published, messaged or spent. Railway and production were not touched.
- Every branch head matched the brief:

| # | Subject | Branch | Head | Diffed against |
|---|---|---|---|---|
| 1 | J-1 (+ plural nouns) | opus2/p0-revenue-workforce | c3074241 (771e1e1a, c3074241) | 6d6d83d9 |
| 2 | J-3 | opus2/p1-culture-sweep-timeout | 3468fe73 | 7c3806fc |
| 3 | J-6 / J-8b | opus2/p0-cir-colourwork | 424d69a9 | fa02cb49 |
| 4 | J-9..J-12 | opus2/p0-pet-bed | 7d220e01 | d0a7685f |

## Verdicts

| # | Subject | Verdict | Why |
|---|---|---|---|
| 1 | J-1 | **DO NOT SHIP** (small fix) | Every J-1 repro is closed and nothing regresses. Two gaps remain, both MED. "Tote Duet", "Tote Quintet", "Tote Sextet", "Tote Twosome", "Tote Triplets", "Tote Couple" and "Tote Multipack" are drafted as one tote, and `title_promise` backs them: the same live draft-path breach as J-1's "Tote Quartets" (K-1). A numeral also silences the new plural-noun rule: "Totes 1" and "Market Totes No. 1" read as backed (K-2). |
| 2 | J-3 | **SHIP** (test-only; J-3 only partly closed) | No assertion is weakened, and M7p is now killed. But the test named for M7n does not kill M7n, and M7o is not addressed. Both still survive (K-4). |
| 3 | J-6 / J-8b | **SHIP** (the J-7 merge condition from OPUS2J still applies) | All the J-6 repros and the C24c mutant are now killed. The 40-CIR catalogue check is identical before and after. Spelling bypasses remain (K-5, MED). J-6 is pre-existing, so this is not a hold reason, as OPUS2J also ruled. |
| 4 | Pet bed | **DO NOT SHIP** | J-9 and J-10 are not closed at the root. Only half of the J-9 fix was built: the "last word is the bed word" check. The "nothing but species and plain adjectives before it" half was not. So other animals, other objects and feature claims are still drafted as the 48 cm cat bed, with the cat-bed size note, and every gate passes them (K-7, HIGH). |

## Findings

| ID | Sev | Subject | Finding | Repro |
|---|---|---|---|---|
| OPUS2K-1 | MED | J-1 | Collective count nouns are still not read. On the one-piece tote, `title_promise.backed` is True and `plan(category="bag")` drafts `tote` for: "Tote Duet", "Tote Quintet", "Tote Sextet", "Tote Twosome", "Tote Triplets", "Tote Trilogy", "Tote Couple", "Tote Multipack" and "Tote Quartette". "Tote Pack", "Tote Kit", "Tote Lot", "Tote Assortment" and "Tote Combo" are ambiguous but get the same result. `plan` refuses "Double Tote", "Market Shoppers" and "Mother and Daughter Tote", yet `title_promise` backs them: it lacks `_MULTIPLE_WORDS`'s `double`, `shoppers`, `family`, `mother`, `daughter` and `matching`. Number words above twelve are not counted either ("Thirteen Tote", "Fifteen Tote": backed, drafted). | `tp.py` on c3074241 |
| OPUS2K-2 | MED | J-1 | A numeral overrides a plural marker or noun. `claimed` is checked first (`if claimed is not None: backed = makes >= claimed`), so a "1" in the title cancels the new noun rule. "Totes 1", "Market Totes No. 1" and "Tote Set 1" are all backed on one tote. On 6d6d83d9, "Tote Set 1" was already backed, so the precedence bug pre-dates this delta; this delta extends it to the new noun rule. `plan` refuses these titles, so the gap is on the retitle backstop (H1-4) only. *Fix:* when a plural marker or noun is present, require `makes > 1` as well. Mutant K8 (`claimed` used only when there is no plural) passes the whole suite, so the fix is safe. | `tp.py` |
| OPUS2K-3 | LOW | J-1 | Test gaps. Removing the number words `two`..`eleven` and `twin` (mutant K1) survives: every pinned number-word title also contains "totes", so the noun rule refuses it anyway. Only "Twelve Tote Dozen" exercises the number words, through `twelve` or `dozen`. A mutant that strips every `two` or `three` (K5) also survives. *Fix:* pin "Two Market Tote", "Twin Tote" and "Three Tote Carryall" (no plural noun) as unbacked. The closed list `_PLURAL_OBJECT_NOUNS` also misses "Beds", "Nests", "Mats", "Hats", "Pouches", "Rugs", "Garlands", "Squares", "Hearts", "Cosys" and "Totebags", all backed on the retitle backstop. | mutants K1, K5 |
| OPUS2K-4 | LOW | J-3 | M7n still survives (and so do the new M7r and M7s, which also only change the row check). `test_review_opus2j_j3_a_pending_record_is_billed_once_across_attempts` makes `effects.claim` fail. That happens before the guard sets `scope.last_call` (paid_calls.py:368 vs :372). So `_outcome_unknown` returns at the "no key" branch and never reads the record's outcome; a spy shows it is called once, with `last_call=None`. The test pins once-only billing, which is a good property, but not M7n. M7o (outside a scope, always UNCERTAIN) also survives; no test was added for it. *Fix:* one test where the record is not UNCERTAIN but `last_call` is set: for example `_update` raising after `call()` fails (the record stays PENDING), or a stale OK `last_call` from an earlier call in the same job. Add one test with no scope, `sent=True`, and an exception that `_classify_failure` does not call UNCERTAIN, asserting it is re-raised. | mutants M7n/M7o/M7r/M7s on 3468fe73 |
| OPUS2K-5 | MED | J-6 | The fold covers only ASCII whitespace, `_` and `-`. These still pass on an all-plain one-colour fabric (`fabric_truth.backed` True, 0 listing findings, as title or as tag): "Fair–Isle" (en dash), "Fair—Isle" (em dash), "Fair‑Isle" (U+2011), "Fair/Isle", "Fair.Isle", "Fair·Isle", "Colour‑Work", "Colour/Work". Also "Graphgan" (only the spelling "graphghan" is listed), "Two-Tone", "Bicolour", "Multicolour", "Three-Colour", "Tri-Colour", "Two-Coloured", "Two Colours", "2-Colour", "Duplicate-Stitched", "C2C" and "Corner to Corner". *Fix:* NFKC-normalise, then fold every non-alphanumeric run to a space. Match "two colou?r(?:s\|ed)?" and "\d+ colou?r", and add "graphgan", "two tone", "bi colou?r", "multi colou?r", "duplicate stitch(?:ed)?" and "c2c" / "corner to corner". | `cw.py` on 424d69a9 |
| OPUS2K-6 | INFO | J-6 / J-8b | (a) Fail-closed false positives: "Double-Stranded Basket" (a held-double construction) and "Two Colour Stripe Basket" are refused on plain fabric. `title_promise._NOT_A_COUNT` treats "two-strand" as a construction, so the two rules disagree. (b) C26b (judge only the first claim per text) still survives; it is near-equivalent. W2 (`_` no longer folded), W6 ("two color" removed) and W11 ("stranded" mapped to tapestry) also survive; they are minor or equivalent. | mutants |
| OPUS2K-7 | HIGH | J-9 / J-10 | The route is still a closed denylist. With `category="pet"`, each of these titles is drafted as the 48 cm vessel. On each, compile gives 0 findings, and `name_truth`, `product_type_findings`, `title_promise` and `fabric_truth` all pass. Each carries "Sized to published cat-bed sizing guidance". **Other animals:** "German Shepherd Bed", "Golden Retriever Bed", "Lab Bed", "Corgi Bed", "Dachshund Bed", "Pug Bed", "Doggy Bed", "Pooch Bed", "Canine Bed", "Guinea-Pig Bed" (only the spaced "guinea pig" is listed), "Gerbil Bed", "Rats Nest", "Birds Nest" and "Owl Nest". **Cat sizes outside the source:** "Maine Coon Bed", "Little Cat Bed", "Huge Cat Bed", "King Size Cat Bed". **Feature claims (the J-9 "heated" class):** "Self-Warming Cat Bed", "Thermal Cat Bed", "Memory Foam Cat Bed", "Plush Cat Bed", "Cat Sofa Bed", "Cat Hideaway Bed". **Other objects:** "Cat Carrier Basket", "Cat Litter Basket", "Treat Basket", "Pet Food Basket", "Leash Basket", "Doll Bed", "Teddy Bed", "Hen Nest", "Easter Nest", "Egg Basket". *Fix* (the second half of OPUS2J's J-9 fix): route to the vessel only when every word before the head noun is in an allowlist, for example {cat, kitten, kitty, pet, cosy, cozy, round, snug, basket, crochet}, and refuse everything else. Pin "German Shepherd Bed", "Maine Coon Bed", "Cat Carrier Basket" and "Self-Warming Cat Bed". | `pet.py`, `pet2.py` on 7d220e01 |
| OPUS2K-8 | LOW | J-9 | The new head-noun guard is not pinned. Mutant P1 drops the `$` anchor and survives: every J-9 title in the test is also refused by a denylist word (liner, mat, toy, weave …). P6 (drop "mat") and P9 (drop "elevated", "bunk", "canopy") also survive. *Fix:* pin a non-bed head with no denylist word, such as "Cat Bed Runner" or "Cat Basket Lid", as not drafted. | mutants P1, P6, P9 |
| OPUS2K-9 | LOW | J-11 | The size is now in `products.vessels` with a citation, which is an improvement. The first source was fetched on 2026-11-02 and says "internal diameter of roughly 16–20 inches (40–50 cm) for round beds". The second citation, "thesize-net Pet Bed Sizes 51 x 41 cm", gives no URL, and `www.thesize.net/pet-bed-sizes/` returns "Page not found", so it is **UNVERIFIED**. Both are secondary blogs, not a measured sample, as the code itself says. 48 cm is across the points and the flats are about 41.6 cm, both outside measurements, so the interior is a little smaller. Mutant P15 (the size inlined again in `fallback_constructions`) survives: it is equivalent, but the J-11 test does not prove the vessel reads `PET_BED_SIZE`. | curl; mutant P15 |
| OPUS2K-10 | LOW | J-12 | On the draft path, J-12 is closed: "Pet Beds", "Two Cat Beds" and "Cat Bed Pair" are refused (mutants P2 and P3 killed). On the retitle backstop, "Pet Beds" is still backed: this branch's `title_promise` has no plural nouns, and even c3074241's list lacks "beds" and "nests". 7d220e01 merges cleanly with c3074241 (`git merge-tree`). It is still based on 13d67502 and has not been restacked. | `tp.py` |
| OPUS2K-11 | INFO | pet bed | Fail-closed effects of the `$` anchor: "Cat Bed Pattern", "Cat Bed!" and "Cat Bed (Crochet Pattern)" are refused, not drafted. "Nest Toy" and "Cat Basket Toy" now go to `flat_panel`. That is the 55450fc3 behaviour, and no form gate checks a "toy" made as a flat panel. The test change that removes "Dog Basket" from the vessel list moves it to the refused list and asserts the refusal, so it is not a weakening. | `pet.py` |

No removed or weakened assertion was found in any of the four diffs. Every diff adds tests;
the two edits to existing test lines (the pet `beds` tuple and the `_worker_sweep` helper) keep
or extend what they asserted. No gate was loosened, and no deterministic validation was
overridden. The Launch-0 / catalogue checks are identical before and after for items 1 and 3:
40 CIRs × (`title_promise` backed, markers, claimed) for item 1, and 40 CIRs × (fabric_truth,
claims, listing findings, title_promise, CIR hash) for item 3. No CIR became unbacked.

## Mutations (each reverted; every worktree clean afterwards)

| ID | Subject | Mutation | Result |
|---|---|---|---|
| K1 | J-1 | number words two..eleven and twin removed | survives (K-3) |
| K2 | J-1 | every J-1 count word removed | killed |
| K3 | J-1 | count-word inflection (`token[:-1]`) dropped | killed |
| K4 | J-1 | `_NOT_A_COUNT` not applied | killed |
| K5 | J-1 | `_NOT_A_COUNT` strips every two/three | survives (K-3) |
| K6 / K7 | J-1 | plural nouns not added / list cut | killed / killed |
| K8 | J-1 | `claimed` used only with no plural (the proposed K-2 fix) | passes the suite |
| K9 | J-1 | "ply" dropped from `_NOT_A_COUNT` | killed |
| M7n / M7o | J-3 | non-DECLINED counts / out-of-scope always UNCERTAIN | **survive** (K-4) |
| M7p | J-3 | `prompt()` built after `sent = True` (OPUS2J form) | killed; survived on 7c3806fc |
| M7q / M7t | J-3 | `_outcome_unknown` always False / no key → True | killed / killed |
| M7r / M7s | J-3 | key present → True / missing row → True | survive (K-4) |
| C24c | J-8b | `min_contrast_run` = max | killed |
| C26b | J-8b | first claim per text only | survives (INFO) |
| W1, W3, W4, W5, W7, W8, W9, W10 | J-6 | fold drops `-`; variants ignored; stranded / jacquard / color work removed; duplicate stitch → motif rule; listing gate / fabric_truth back to substring | all killed |
| W2 / W6 / W11 | J-6 | `_` not folded / "two color" removed / stranded → tapestry | survive (INFO) |
| P2, P3, P4, P5, P7, P8, P10, P11, P12, P13 | pet | plural refusal off; "beds" clause off; animals off; sizes off; weave off; heated off; source note off; hamster off; medium off; 48 → 45 cm | all killed |
| P1 / P6 / P9 | pet | `$` anchor dropped / "mat" dropped / elevated, bunk, canopy dropped | survive (K-8) |
| P15 | pet | size inlined again in fallback | survives (equivalent; K-9) |

## Tests run (from `brambleloop/`, `PYTHONPATH=src:tests PYTHONDONTWRITEBYTECODE=1 python3 tests/<f>.py`, after `pip install -r requirements.txt`)

Every suite exited 0.

| Head | Suites |
|---|---|
| c3074241 | test_opus2_draft_constructions 19 OK; test_launch0 52; test_w4_pipe_board 70; test_opus2_size_claims 13; test_first_customer_gate 12 passing; test_compiler 9 / test_twin 8 / test_reverse 18 / test_vacuity 8 |
| 3468fe73 | test_opus2_culture_sweep_timeout 7 OK; test_culture; test_culture_feed; test_w3_spend_paid_calls (PASS); test_w4_close5_vision_timeout (PASS 4); test_w3_spend_hygiene (PASS); test_vacuity; test_w4_fmbatch1_retention_guard |
| 424d69a9 | test_opus2_cir_colourwork (0 failed); test_compiler; test_twin; test_reverse; test_vacuity; test_pattern_truth; test_launch0; test_leadtime; test_first_customer_gate 12 passing; test_physfix 46/46 |
| 7d220e01 | test_opus2_pet_bed 5 OK; test_opus2_draft_constructions 18; test_fallback_draft_provenance 1; test_opus2_knowledge_gaps 9; test_w4_listready 31; test_w4_auto_status (PASS); test_compiler 9 / test_twin 8 / test_reverse 18 / test_vacuity 8 / test_launch0 52 |

## Commands

```
git fetch origin claude/w5-SECREVIEW-OPUS2J opus2/p0-revenue-workforce \
  opus2/p1-culture-sweep-timeout opus2/p0-cir-colourwork opus2/p0-pet-bed
git diff 6d6d83d9..c3074241; git diff 7c3806fc..3468fe73
git diff fa02cb49..424d69a9; git diff d0a7685f..7d220e01
git worktree add --detach $S/{r,r0,c,c0,w,w0,p,p2,p0} <head>    # S = session scratchpad
python3 $S/tp.py "<titles>"     # title_promise + plan(category=bag) on the one-piece tote
python3 $S/cat.py / catf.py     # catalogue title_promise / fabric_truth / hash, before vs after
python3 $S/cw.py "<titles>"     # fabric_truth + colourwork_findings on the plain band fixture
python3 $S/pet.py / pet2.py     # plan(category=pet) routes; gates on the drafted vessel
$S/mut.sh <wt> <file> 'old@@@new' <suite...>   # apply, run, git checkout
git merge-tree --write-tree 7d220e01 c3074241   # clean
curl -sSL https://thetoolstrunk.com/how-big-should-a-cat-bed-be/   # J-11 source check
```

The probe scripts stay in the reviewer's scratchpad and were not committed. Each uses only the
repository's public functions on the named commit, with no network (except the one J-11 source
fetch) and no database outside a temporary SQLite file.
