# Independent security / truth review OPUS2N — pet bed K-7..K-9 fix, tapestry basket generator

- Reviewer: independent, adversarial, read-only. Nothing was deployed, published or spent. Railway and production were not touched.
- Date: 2026-11-02 (UTC).
- Subject 1: `origin/opus2/p0-pet-bed` 940f70e6, diff `7d220e01..940f70e6`. Closes OPUS2K-7 (HIGH), K-8 and K-9.
- Subject 2: `origin/opus2/p0-tapestry` 67b67015, diff `2d2d9446..67b67015`, on `claude/w5-INTEG1` 2d2d9446. This is the first generator that emits per-stitch colour (`Op.color`).

## Verdicts

| # | Subject | Verdict | Why |
|---|---|---|---|
| 1 | Pet basket bed (940f70e6) | **DO NOT SHIP** | K-8 and K-9 are closed. Every OPUS2K-7 title is refused. But the new allowlist is not total. It only tests the `[a-z0-9]+` tokens it extracts, so any word written in non-ASCII letters, an emoji or a symbol yields no token and passes. "🐶 Bed", "犬 Bed" (Japanese "dog") and "Кот Bed" are each drafted as the cat-sized vessel. Each compiles with 0 findings and passes `name_truth` and `product_type_findings` (N-1). That is the K-7 class again: another animal gets the cat bed. The fix is one line. |
| 2 | Tapestry basket (67b67015) | **DO NOT SHIP** (one fix away) | The colourwork core is sound. The emitted CIR compiles with 0 findings. `fabric_truth` backs the name through its own `tapestry` rule. The pattern reverse-parses with the contrast intact. Yardage is computed per yarn, including the carried strand. Launch-0 digests are unchanged and no gate was loosened. But the title allowlist has the same non-ASCII hole (N-1). "🦊 Tapestry Basket" and "Лиса Tapestry Basket" ("fox") are drafted with the default diamond chart and pass every gate. That is an unbacked motif claim. The other findings are LOW or INFO. |

Both subjects become SHIP once N-1 is fixed and pinned. Neither needs anything else first.

## Findings

| ID | Sev | Subject | Finding | Repro |
|---|---|---|---|---|
| OPUS2N-1 | **MED** (blocking: it re-opens the K-7 class) | both | **The allowlist checks extracted tokens, not the whole prefix.** Pet: `re.findall(r"[a-z0-9]+", prefix)` (`fallback_constructions.py:156`). Tapestry: `re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", folded[:head])`. A word with no ASCII letters produces no token, so `unknown == []`. **Pet, drafted as the 48 cm cat vessel:** "🐶 Bed", "🐕 Basket", "犬 Bed", "Кот Bed", "Кошачья Bed", "Ⅱ Cat Bed" (a numeral). On each, compile gives 0 findings, `name_truth` = [] and `product_type_findings` = []. The size note still says "published cat-bed sizing guidance". **Tapestry, drafted with the diamond chart:** "🦊 Tapestry Basket", "Лиса Tapestry Basket", "狐 Tapestry Basket". On each, compile gives 0 findings and `title_promise`, `fabric_truth`, `name_truth` and `product_type_findings` all pass. Partly non-ASCII words fail closed ("Hündchen" → token "h ndchen", refused). *Fix:* make the allowlist total. Require the whole prefix to match `^(?:(?:w1\|w2\|…)[\s\-]+)*$` built from the allowlist, or refuse when `re.sub(r"[a-z0-9\s\-]", "", prefix)` is non-empty. Pin "🐶 Bed", "犬 Bed" and "🦊 Tapestry Basket" as refused. | `probe_pet.py`, `pet2.py`, `tap2.py`, `tap3.py` |
| OPUS2N-2 | LOW | both | **"Round" is allowlisted, but the object is a hexagon.** "Round Cat Bed" is drafted, and the test pins it. So is "Round Tapestry Basket". Each CIR's own `finished_size_note` says "A hexagonal … basket", per the PT-10 convention: "the stacked increases make a hexagon, so the name says so". The title shape and the CIR shape contradict, and no gate checks shape words. *Fix:* drop "round" from both allowlists (and from the pet test's drafted list), or add a shape gate. | `pet2.py "Round Cat Bed"` |
| OPUS2N-3 | LOW | 2 | **The contrast yarn is never told when to join or when to cut** (J7B-2, now live on a product). Cream is used only as a contrast, in Rnds 16-33. The printed Finishing says "Colourwork rounds 16-33: work over the colour not in use … Do not cut at these changes. Ends to weave in: about 4." It gives no "join cream at the start of Rnd 16" and no "cut cream after Rnd 33". `rounds_instruction` takes the `changes == 0` branch, which prints only the tapestry sentence. Nothing printed is false, and 4 ends = 2 yarns × 2 is consistent. But on the first paid colourwork pattern the maker must infer both steps. *Fix:* implement J7B-2, giving join and cut wording for contrast-only yarns from `rows_used`. | `tap1.py` → `tap_pattern.txt` l.25, 49 |
| OPUS2N-4 | LOW | 2 | **Several motif or size words in one title are silently reduced to one.** "Check Diamond Tapestry Basket" is drafted as check only. "Two-Colour Diamond Check Basket" is drafted as diamond only. "Large Small Tapestry Basket" is drafted as small. The title promises a second motif that the chart does not make. *Fix:* refuse a title that names more than one distinct chart, or more than one size. | `tap2.py` |
| OPUS2N-5 | LOW | 1 | **The size comment does not describe the compiled object.** `vessels.py:63` says "48 cm is the OUTSIDE measurement across the points (the flats are about 41.6 cm)". The compiled bed is **51.2 cm across the points and 44.3 cm across the flats**: the stitch count rounds up to a whole number of wedges. The flats still sit inside the cited 40-50 cm internal range, and the points (outside) exceed it slightly. The customer-facing note prints the computed numbers, so this is a comment error, not a listing error. | `pet2.py` note |
| OPUS2N-6 | LOW (test gap) | 2 | Mutants T8, T10 and T12 survive. **T8** removes the plural-noun guard in `_colour_count_free`. It is not killed because "Two Colour Baskets" is also refused by `tapestry_route`, and no non-basket plural is tested ("Two Tone Bowls" in another category). **T10** removes the pipeline's one-colour pre-check. This is equivalent: `tapestry_basket` raises `ValueError`, and the handler's `except (ValueError, KeyError)` refuses it at the same `construction` gate. **T12** removes "whole chart repeats only". This is equivalent on every yarn weight × size × chart tried (the band is always a multiple of 6), but nothing pins it if the gauges change. | mutations table |
| OPUS2N-7 | INFO | 1 | **K-9 is verified.** `https://thetoolstrunk.com/how-big-should-a-cat-bed-be/` returned HTTP 200 on 2026-11-02. It says "Average adult domestic cats … That translates to an internal diameter of roughly 16–20 inches (40–50 cm) for round beds", which is the cited quote. The unverified thesize.net citation is removed, and the test asserts that it stays removed. The same page's table gives "Kitten … Size for adult length, ~18 inches", so drafting "Kitten Bed" or "Kitten Nest" at the adult size agrees with the source. The table also says average adult "18–22 inches internal" (46–56 cm), which disagrees with the page's own prose (40-50 cm). It remains a single secondary blog, as the code says. P15 (the size inlined again) is now killed: the test swaps in a 30 cm `PET_BED_SIZE` and checks that the bed shrinks. | `curl` below |
| OPUS2N-8 | INFO | 1 | **K-8 is pinned.** Dropping the `$` anchor (M3) is killed by "Cat Bed Runner" and "Cat Basket Lid". The old P6 ("mat" dropped from the denylist) still survives. That is now equivalent: with the head anchor and the allowlist, "mat" can never reach the denylist. Every OPUS2K-7 title (34 listed), plus "Dachshund Bed" and "Pug Bed", is refused. No assertion was removed or weakened in `test_opus2_pet_bed.py`, because the diff only adds. "Cat's Bed" and "Cat’s Bed" are refused: the token "s" is not allowlisted, so the allowlisted word "cat's" can never match. This fails closed (INFO). | `probe_pet.py` |
| OPUS2N-9 | INFO | 2 | **Checked and true.** (a) The chart band (Rnds 16-33 at the medium size) paints exactly the chart line on every round, and the twin grid matches. (b) `fabric_truth` returns `backed=True` through `technique_backed("tapestry")`: 18 of 35 rows carry two colours. The same twin under "Mosaic Basket" is not backed. (c) A plain vessel with a "tapestry" tag is refused (`LISTING_COLOURWORK_UNSUPPORTED`), so no claim word leaks onto plain fabric. (d) Yardage per yarn is computed: forest 79.7 m and cream 43.7 m at the medium size. The carried strand is charged at `CARRY_FACTOR` (killing that charge, T16, is caught by `test_opus2_cir_colourwork`). (e) "Carried, not floated" is true: in joined rounds, `plan.cut == tapestry_cuts == 0`, and the wording says "work over … carried inside the stitches". It never says "float" or "strand across the back". (f) Every other technique is refused by name: mosaic/overlay, graphghan/C2C, intarsia, fair isle/stranded/jacquard, three-, multi- and tri-colour inside a tapestry title. | `tap1.py`, `leak.py` |
| OPUS2N-10 | INFO | 2 | **Gates are unchanged and no LLM decides validity.** The diff touches only `fallback_constructions.py` and `pipeline.py`. The one changed gate input is `_several_sizes(_colour_count_free(slug/title))`. It renames "two-colour" or "two-tone" to "bicolour" only when no plural vessel noun is present. "Pair of Two-Tone Basket", "Two-Tone Basket Set", "Two-Colour Basket Trio", "Two Tone Nesting Basket Set", "Two-Two-Tone Basket" and "Two Colour Baskets" are all still refused. `launch0`, `product_truth`, `fabric_truth`, `title_promise` and `colourwork_findings` are untouched. Launch-0 digests are byte-identical: 8 CIR + US/UK pattern hashes, aggregate `a6b94146b995b017`, and `product_truth` `fe592b38fd897917`, on both 2d2d9446 and 67b67015. Routing and validity are deterministic regexes plus the compiler and twin. | `dig.py` |
| OPUS2N-11 | INFO (pre-existing, not in delta) | 2 | "Tri Colour Basket" with no tapestry word is still drafted as the plain two-colour vessel and passes `fabric_truth` and `name_truth`. A "fair isle" or "fox" claim in the listing **description** is not checked: `name_truth` reads only the listing title and tags. Neither was introduced here. Both are recorded for a later gate. | `tap3.py`, `leak.py` |

## Mutations

Each mutant is applied to the worktree, the named suites are run, and the file is restored with `git checkout`.

| ID | Subject | Mutant | Result |
|---|---|---|---|
| M1 | 1 | the allowlist check disabled (`unknown = []`) | killed (test_opus2_pet_bed) |
| M2 | 1 | german, shepherd, maine, coon, carrier, self, warming added to the allowlist | killed |
| M3 | 1 | `_PET_BED_HEAD` `$` → `\b` (K-8) | killed |
| M4 | 1 | the prefix sliced to `[:1]` | killed |
| M5 | 1 | little, huge, plush, thermal added to the allowlist | killed |
| M6 | 1 | "thesize" re-added to `PET_BED_SIZE_SOURCE` | killed |
| P6 | 1 | "mat" dropped from `_PET_BED_NOT_PLAIN` | survives (equivalent; N-8) |
| T1 | 2 | the tapestry allowlist disabled | killed (test_opus2_tapestry_basket) |
| T2 | 2 | `_TAPESTRY_HEAD` `$` → `\b` | killed |
| T3 / T4 / T5 / T14 | 2 | fair-isle / intarsia / three-colour / graphghan refusals disabled | killed |
| T6 | 2 | the plural and multiple-basket refusal disabled | killed |
| T7 | 2 | `_colour_count_free` bypassed (the old `_several_sizes`) | killed |
| T8 | 2 | the plural-noun guard in `_colour_count_free` removed | **survives** (N-6) |
| T9 | 2 | the two-distinct-colours check in `tapestry_basket` removed | killed |
| T10 | 2 | the pipeline one-colour pre-check removed | survives (equivalent via `except ValueError`; N-6) |
| T11 | 2 | the chart's contrast cells painted main | killed |
| T12 | 2 | "whole chart repeats" (`band -= band % len(chart)`) removed | survives (equivalent on all sizes tried; N-6) |
| T13 | 2 | "argyle" (chart None) admitted to the allowlist | killed |
| T15 | 2 | fox, jumbo, lined added to the allowlist | killed |
| T16 | 2 | the carry yardage charge removed in `twin` | survives the tapestry suite; **killed** by test_opus2_cir_colourwork |
| T17 | 2 | `tapestry_route` not called from `plan` | killed |

Not mutated, because no guard exists for it: the non-ASCII prefix (N-1). It is a live bypass, not a mutant.

## Suites run (all exit 0)

| Head | Suites |
|---|---|
| 940f70e6 | test_opus2_pet_bed (0 failed, K-7/K-8 test included); test_fallback_draft_provenance (OK); test_w4_c03_fallback (6 passed) |
| 67b67015 | test_opus2_tapestry_basket (0 failed); test_opus2_draft_constructions (0 failed); test_opus2_cir_colourwork (0 failed); test_fallback_draft_provenance; test_compiler; test_reverse; test_twin; test_vacuity; test_launch0; test_pattern_truth; test_opus2_size_claims |

`sqlalchemy` and the rest of `brambleloop/requirements.txt` were pip-installed into the reviewer container. Suites that need them failed to import before that.

## Commands

```
git fetch origin opus2/p0-pet-bed opus2/p0-tapestry claude/w5-SECREVIEW-OPUS2K claude/w5-INTEG1 claude/w5-SECREVIEW-J7B
git diff 7d220e01..940f70e6; git diff 2d2d9446..67b67015
git worktree add --detach $S/{pet,tap,tap0} {940f70e6,67b67015,2d2d9446}     # S = scratchpad
cd $S/<wt>/brambleloop && PYTHONPATH=src:tests python3 tests/<suite>.py
PYTHONPATH=src:tests python3 $S/probe_pet.py           # plan(category=pet) on bypass titles
PYTHONPATH=src:tests python3 $S/pet2.py "🐶 Bed" ...   # vessel → compile, name_truth, product_type_findings
PYTHONPATH=src:tests python3 $S/tap1.py $S/tap_pattern.txt   # findings, fabric_truth, yarn, reverse, written text
PYTHONPATH=src:tests python3 $S/tap2.py / tap3.py      # tapestry routes; gates on drafted CIRs
PYTHONPATH=src:tests python3 $S/leak.py                # listing claim words on tapestry and plain fabric
PYTHONPATH=src:tests python3 $S/dig.py                 # Launch-0 CIR+pattern and product_truth digests, both heads
$S/mut.sh <wt> <file> '<old>' '<new>' <suite...>       # apply, run, git checkout
curl -sSL https://thetoolstrunk.com/how-big-should-a-cat-bed-be/   # 200; quote found
```

The probe scripts stay in the reviewer's scratchpad and were not committed. They call only the repository's public functions on the named commit. They use no network, apart from the one K-9 source fetch, and no database outside a temporary SQLite file.
