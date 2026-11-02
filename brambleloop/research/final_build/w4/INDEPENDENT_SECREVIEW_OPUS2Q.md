# Independent security and correctness review OPUS2Q: Secondary's fixes for OPUS2O, 2026-11-02

Reviewer: an independent, adversarial, read-only Claude Code session (branch `claude/w5-SECREVIEW-OPUS2Q`).
- The review was read-only on every branch under review. This report is the only file written.
- Every probe and mutation ran in scratch worktrees in the session scratchpad: one worktree per head
  (b185b528, 8cf4a458, f4bf34bb, 2f9c413d, 5889cc37, d3a485a1, a859f6fe) plus one mutation copy per
  subject. Each mutation was reverted by the runner, which writes the original file back. Afterwards,
  `git status --porcelain` printed 0 lines in all three mutation worktrees.
- Nothing was deployed, published, messaged or spent. Railway and production were not touched.
- Network use was limited to `git fetch` and one read-only GET of the retail URL that the stocking code
  used to cite (OPUS2O-9).

| # | Subject | Branch | Head | Delta reviewed |
|---|---|---|---|---|
| 1 | PR #3 title multiplicity (OPUS2O-1, -2, -3, -10) | opus2/p0-revenue-workforce | b185b528 | 8cf4a458..b185b528 |
| 1m | same, merged | opus2/p0-revenue-workforce-b4merge | f4bf34bb (merge of b185b528) | 80f4b073..f4bf34bb (first parent) |
| 2 | PR #9 colourwork claim reader (OPUS2O-4, -5, -2) | opus2/p0-cir-colourwork | 2f9c413d | 5889cc37..2f9c413d |
| 3 | PR #11 stocking (OPUS2O-6, -7, -9) | opus2/p0-stocking | d3a485a1 | a859f6fe..d3a485a1 |

## Verdicts

| # | Subject | Verdict | Why |
|---|---|---|---|
| 1 | Multiplicity reader (b185b528) | **DO NOT SHIP** | **What it fixes:** the reader is now genuinely morphological. It has every root the brief named (tri, quad, quint, sext, sept, oct, non, dec, plus bi/di/du/twi/tetra/penta/hexa/hepta). It reads the suffixes -some, -plet/-uplet, -ple/-uple, -ad, -et, -ette, -pack, -set, -plicate and -fecta, and the -s/-es/-ies/-d/-ed inflections. Every OPUS2O-1 drafted-as-one-tote repro is now refused by `plan` and unbacked by `title_promise`. The brief's 17 ordinary words ("Triangle", "Quadrant", "Octopus", "Decorative", "Septic", "Sextant", "Tripod", "Quaint", "Novelty", "Nonsense", "Settle", "Battle", "Ballet", "Doublet", "Triumph", "Trivet", "Quartz") all still draft and are backed. The 28-CIR catalogue is byte-identical. **What it breaks:** it adds a **new class of false positives that refuse real product titles in every category**, because `title_promise` is a publish and first-customer gate. On the one-piece Cloudline blanket, these all fail the count gate: "Multicolour Stripe Baby Blanket", "Multicolored Granny Blanket", "Multi-Season Throw", "Multipurpose Basket", "Polyester Blend Blanket", "Tent Stitch Wall Hanging", "Fanny Pack", "Hip Pack", "Ice Pack Cover", "Twined Cord Basket", "Tiny Bits Blanket", "Diet Coke Coaster" and "Son Shine Baby Blanket" (OPUS2Q-1, MED). The brief asked for exactly the opposite: no wrongly-refused ordinary words. |
| 1m | merge f4bf34bb | **Faithful** | `git diff 80f4b073..f4bf34bb` is byte-identical to `git diff 8cf4a458..b185b528`. `launch0.py` and `test_opus2_draft_constructions.py` are identical between b185b528 and f4bf34bb. The 160-title probe and the catalogue probe give identical output on both heads, and the suites pass. The merge carries OPUS2Q-1 with it. |
| 2 | Colourwork claim reader (2f9c413d) | **DO NOT SHIP** | **What it fixes:** every OPUS2O-4 and OPUS2O-5 repro is closed and pinned, as title and as tag: "Corner2Corner", "Cornertocorner", "C to C", "C-to-C", "Ctoc", "Eleven/Twelve/Dozen/Quad Colour", "Five Shade", "Two Hue", "Polychrome", U+034F, U+FE0F, U+17B4, U+115F, U+3164, U+2800, ı, ø, ѕ, ϲ, ɑ, ᴀ, օ and Ӏ. Marks are now dropped by category Mn/Me. **What it breaks:** the new trailing `\b` in `c ?(?:2\|to) ?c\b` is a **regression**. "C2CBlanket", "C2Cs", "C2Cgraph" and "C2Cing" were refused on 5889cc37. They are now backed with 0 findings on plain fabric, as title and as tag. The mutant that removes the `\b` survives the suite. **Still not done:** letters are still not split from digits, which the brief required, so "CrochetC2C", "crochetc2c", "Basket5Colour", "Blanket2Tone" and "crochet2colour" pass (OPUS2Q-2, MED). The look-alike map is still a list, not a confusables class (OPUS2Q-3, LOW). |
| 3 | Stocking (d3a485a1) | **SHIP** | **O-6 closed.** A "Contrast/Contrasting/Stripe/Striped Cuff" title with fewer than two distinct palette hex values in `palette[:2]` raises `ValueError`. `pipeline.py:813` turns that into a named `construction` refusal. One colour, two names for one hex, and three colours whose first two match are all refused. "Solid" is out of the allowlist, and "Solid (Christmas) Stocking" is now refused in all 6 categories. That is the only plan change vs a859f6fe over 20 probe titles. **O-7 closed.** The pet route's `fold_title` is pinned: reverting it to `lower()` is killed. **O-9 closed.** The retail citation is gone and the constant reads "design choice; no published standard stocking size found". I re-fetched the old URL: HTTP 200 with `<title>Product Not Found \| The Home Depot Canada`. So the new comment, which says the listing "no longer resolves", is accurate, and no figure is quoted. The delta cites no other URL. **Residuals (LOW):** OPUS2Q-4 (hex compared case-sensitively, with no contrast threshold), OPUS2Q-5 ("Striped Cuff" is one solid band) and OPUS2Q-6 (two guard cases unpinned). |

Subjects 1 and 2 each need one more change. Subject 3 can merge; its LOW items can follow.

## Findings

**Probes, subject 1:**
- `L.multiplicity(t)`, `F.plan(category="bag", title=t)` and `L.title_promise(replace(sunset, title=t))` on the one-piece sunset tote from `test_opus2_draft_constructions`, over 160 titles (`tp.py`).
- `title_promise` on `cir_for("cloudline_blanket")` renamed, over 21 titles (`fp.py`).

**Probes, subject 2:** `colourwork_claims`, `fabric_truth` and `FCG.colourwork_findings` on the all-plain `_band({})` fixture, as the title "<w> Basket" and as a tag on "Plain Basket" (`cw.py`, 112 + 11 words).

**Probes, subject 3:**
- `F.plan` over 20 titles × 6 categories (`stk.py`).
- `F.stocking` + `compile_cir` over 9 titles × 6 palettes, recording the cuff-row and body-row colours (`cuff.py`).

| ID | Sev | Subject | Finding | Repro |
|---|---|---|---|---|
| OPUS2Q-1 | **MED** | 1 | **New false positives: the reader now refuses ordinary product words, in every category.** Four new rules over-match. **(a) Prefix rule:** `token.startswith(("multi", "poly"))` marks any word with that prefix, so "Multicolour", "Multicolored", "Multi-Season" (token "multi"), "Multipurpose", "Multi-Use", "Polyester", "Polymer" and "Multiplicity" are plural markers. **(b) Short roots:** a short root followed by `e?ts?` reads ordinary words as counts: "Tent"/"Tents"/"Tenet" = 10 (ten + t/ts/et), "Bit"/"Bits" = 2 (bi + t/ts), "Diet" = 2 (di + et), "Twit" = 2 (twi + t). "Tent Stitch" is a real stitch name. **(c) Bare pack:** `re.fullmatch(r"packs?", token)` makes every single bag called a pack plural: "Fanny Pack", "Hip Pack", "Sling Pack", "Ice Pack Cover". **(d) Inflections:** the new `-d`/`-ed` inflection over-reads "Tend" (= ten, 10) and "Twined" (= twin, 2). The new family noun "son" reads "Son Shine". `kit` + `-ed` reads "Kited". **Every one of these was backed on 8cf4a458 and is unbacked on b185b528.** `title_promise` is read by `gates/first_customer.py:258`, `publish/eligibility.py:645`, `publish/manual_adoption.py:743` and `products/inventory.py:123`. So a one-piece "Multicolour Stripe Baby Blanket" now fails the count gate (`fp.py`: `backed` False, markers `('multicolour',)`). On the tote route, `plan` refuses "Multicolour Market Tote", "Tent Stitch Tote", "Hip Pack Tote" and the like. No catalogue CIR is affected today (28/28 backed, byte-identical), but the brief explicitly counts wrongly-refused real titles as defects. The only effect on listing strings is the gate's own explanation sentence, which now reads as plural through "multiplicity" (`ident.py`). *Fix:* (a) read multi-/poly- only before a count suffix or an object noun (`multi[- ]?(?:pack\|set\|piece\|pc)s?`, `poly(?:ptych\|ad)`), never as a bare prefix. (b) For the two-letter roots and `ten`, do not accept the bare `t`/`ts`/`et`/`ets` suffixes; "duet" is already a `_COUNT_WORDS` key. (c) Read "pack" as a marker only after a count, or as variety/value/multi pack. (d) Apply `-d`/`-ed` only to the count words that take it (double, triple, couple, quadruple, pair). Drop "son", or require "father son"/"mother son". Pin "Multicolour Stripe Blanket", "Tent Stitch Tote", "Fanny Pack" and "Tiny Bits Blanket" as backed one-piece titles. | `tp.py < titles.txt`, `fp.py`, on 8cf4a458 vs b185b528 |
| OPUS2Q-2 | **MED** | 2 | **Regression from the new trailing `\b`, and letters are still not split from digits.** **The regression:** the C2C variant changed from `c ?2 ?c` to `c ?(?:2\|to) ?c\b`. Glued tag spellings that were claims on 5889cc37 are now backed with 0 findings on plain fabric, as title and as tag: "C2CBlanket", "C2Cs", "C2Cgraph", "C2Cing". The `\b` has no tested purpose: mutant Q2a (remove it) survives `test_opus2_cir_colourwork`, and the negative pins ("Doctor", "Victoria", "Accent", "Plain") pass without it. **The unmet requirement:** the brief required letters split from digits. `_fold` still does not do it, and the variants are matched from a word start (`\b(?:variant)`), so a digit glued to a word hides the claim. "Basket5Colour", "Blanket2Tone", "CrochetC2C", "crochetc2c", "learnc2c", "crochet2colour" and "crochetcornertocorner" are backed on both heads. That part is not a regression. These are ordinary hashtag-style tag spellings. *Fix:* in `_fold`, insert a space at every letter↔digit boundary (`re.sub(r"(?<=[a-z])(?=\d)\|(?<=\d)(?=[a-z])", " ", t)`). Drop the trailing `\b` on the digit form, since `c 2 c` after the split is unambiguous. Keep `\b` only on the spelled `c to c`. Pin "C2CBlanket", "C2Cs", "CrochetC2C" and "Basket5Colour". | `cw.py < cw.txt`, `cw.py < cw3.txt` on 5889cc37 vs 2f9c413d |
| OPUS2Q-3 | LOW | 2 | **Confusables are still a list, and some invisible characters still split a word.** **Look-alikes:** these Latin small capitals and Cyrillic letters still hide a claim on plain fabric, as title and as tag: "Mᴏsaic" (U+1D0F), "Moꜱaic" (U+A731), "Mosaɪc" (U+026A), "Mosaiᴄ" (U+1D04), "Tapestrʏ" (U+028F), "Fair Isʟe" (U+029F), "Fair Iꜱle", "Colᴏurwork", "Intarꜱia" and "Graphgһan" (U+04BB). The small capitals are Latin script, so a mixed-script refusal would not catch them either. Only a confusables skeleton (UTS #39), or refusing any non-ASCII letter that survives the fold inside a claim-length window, closes this class. **Invisible characters:** whitespace-class characters that render with almost no width still split a claim word: U+200A HAIR SPACE, U+2009, U+202F, U+205F and U+3000. So do the unassigned Default_Ignorable code points U+2065, U+FFF0 and U+E01F0, which are category Cn. Every Mn/Me, Cf, U+034F, variation-selector and Hangul-filler case the brief named is closed. *Fix:* drop every `Default_Ignorable_Code_Point`, Cn included, and the Zs characters other than U+0020 between letters. Fold through the UTS #39 confusables skeleton, or refuse. | `cw.py < cw.txt` |
| OPUS2Q-4 | LOW | 3 | **The two-colour check compares hex strings case-sensitively and has no contrast threshold.** A palette of `#244A3A` and `#244a3a` (one colour, written twice) builds a "Contrast Cuff Christmas Stocking" (`compile_cir` ok), and so does `#EFE6D2` with `#EFE6D3`. The cuff is visually the body colour. *Fix:* normalise hex case before the set. Require a minimum colour distance (e.g. ΔE ≥ 10) for any title that claims contrast. | `cuff.py` |
| OPUS2Q-5 | LOW | 3 | **"Stripe(d) Cuff" is admitted, but the cuff is one solid band.** `stocking()` colours rows 1–4 with `accent` and the rest with `main`. On a two-colour palette, "Striped Cuff Christmas Stocking" and "Stripe Cuff Holiday Stocking" build a single four-row contrast band (cuff rows `['b']`, body rows `['forest']`), not stripes. *Fix:* drop stripe/striped from the admitted fold, so only contrast/contrasting is admitted, or work alternating cuff rows when the title says stripe. | `cuff.py` |
| OPUS2Q-6 | LOW (test gaps) | 1, 2, 3 | **Surviving mutants.** **Subject 1:** the brief asked for pins "with generated titles", but the new test is a hand-written list, and eight list entries survive: Q1b (`-ed`), Q1l (`pled`, so "Tote Quintupled" drafts), Q1t ("son"), Q1v ("sext"), Q1y (`sets?`), Q1z ("twi"), Q1aa ("ter"), Q1ab ("hept/hepta") and Q1ac ("oct"). A root × suffix × inflection product test would kill all of them. **Subject 2:** Q2a (the trailing `\b`, see OPUS2Q-2), Q2g (ɡ), Q2j (ј), Q2k ("thirteen"), Q2n ("many") and Q2s (օ). **Subject 3:** Q3b (the guard compares colour names instead of hex values; the two-names-one-hex case is unpinned) and Q3c ("striped" dropped from the guard regex). | mutations table |
| OPUS2Q-7 | LOW | 1, 2 | **Residual class gaps beyond the brief's list.** **Subject 1:** drafted as one tote and backed: number word + -some/-pack above ten ("Tote Elevensome", "Tote Twelvepack", "Tote Dozensome"); inflected large numbers ("Tote Thousands", "Tote Millions"), since `_LARGE_NUMBERS.get` is exact; "Tote Billion"; Roman numerals above XII ("Tote XIII"); "Tote Quints" and "Tote Quins"; the -logy series ("Tote Duology", "Tote Tetralogy", "Tote Quadrilogy", "Tote Pentalogy"); "Diptych/Triptych Tote" (only "Polyptych" is refused, through poly-); "Tote Twinset"; "Tote Tercet"; "Tote Trine"; "Tote Triune"; and family nouns outside the list ("Grandmother", "Mom", "Mum", "Mama", "Grandson"). **Subject 2:** colour counts above twenty, or compound, are not claims ("Thirty Colour", "Forty Colour", "Hundred Colour", "Twenty-One Colour"), and neither are "Multiple Colours" and "Several Colours". The same results hold on the earlier heads, so none of this is a regression. | `tp.py`, `cw.py` |
| OPUS2Q-8 | INFO | 1 | **Intended loosenings, and one inconsistency in the fail-closed direction.** **Loosenings (OPUS2O-10, on purpose):** "Triple Strand Tote" and "Triple-Stranded Tote" now draft and are backed, because `(two\|three\|triple)[- ]strand` is not a count. "Mother’s Day Tote" (U+2019) is now backed by `title_promise`. **Inconsistency:** `plan` still refuses "Mother's Day Tote", in both apostrophe forms, and "Three Strand Tote", through `_MULTIPLE_WORDS` on the unfolded title. Meanwhile "Mothers Day Tote", "Father’s Day Tote" and "Triple Strand Tote" draft. That is fail-closed, but the two readers no longer agree on these titles. **Closed:** OPUS2O-3 ("Tote Doubled", "Tote Tripled", "Tote Quadrupled" are unbacked and refused). The `-es` branch (former mutant A2) and "lot" (A7) are now pinned (OPUS2O-2). | `tp.py` |
| OPUS2Q-9 | INFO | 2 | **New fail-closed claims, and the catalogue is unchanged.** "Two Shades Of Calm" and "Multi Shade" are now colourwork claims, because `shade` was added to the count alternation. They are refused on plain fabric. The catalogue output (28 CIRs: `title_promise`, `fabric_truth`, `colourwork_findings`) and the colourwork reading of the 138 listing strings are byte-identical between 5889cc37 and 2f9c413d. | `cat.py`, `ident.py` |
| OPUS2Q-10 | INFO | all | **Every prior repro was re-run.** **Subject 1:** all OPUS2O-1 titles ("Quintuplets" … "Octuple", "Fivesome", "Sixsome", "Dyad", "Tetrad", "Pentad", "Hexad", "Sestet", "Nonet", "Quintette", "Tri-Pack", "Tripack", "Quadpack", "Twopack", "Bi-Pack", "Multi-Tote", "Multiset", "Thousand", "Million", "Triplicate", "Sisters", "Brothers", "Siblings", "Father Son", "Mommy", "Tote Pack", "Tote Value Pack", "Tote Variety Pack", "Tote II/III/Ⅲ/③") are refused by `plan` and unbacked. Still drafted, as reported in OPUS2O-1 (ambiguous, not counts): "Tote Combination", "Tote Mix", "Tote Selection", "Tote Series", "Tote Score", "Tote Gross", "Tote Matched", "Tote Coordinating", "Tote Assorted". **Subject 2:** every OPUS2O-4 and OPUS2O-5 word is refused as title and as tag (pinned). **Subject 3:** the OPUS2O-6 repro (a one-colour "Contrast Cuff Christmas Stocking") is refused. The OPUS2O-7 mutant (pet route back to `lower()`) is killed. The OPUS2O-9 citation is removed. | as above |

**Removed or weakened assertions: none.**
- `git diff <range> -- brambleloop/tests | grep -cE '^-[^-]'` is 0 for all three deltas. Every test change is an addition.
- The only source loosenings are the intended `triple strand` clause (OPUS2O-10) and the removal of "solid", which makes the stocking route stricter.
- No compiler, twin or gate path changed. No deterministic validation was overridden.

**Catalogue: no new false positive.** `cat.py` enumerates `BUILDERS` (11), `PROPOSED_BUILDERS` (3), `builder.CATALOGUE`, every `inventory.universe()` slug, every `nordic_forest.SIZES` and `vessels.build()`.
- **Count:** 11 + 3 builders + 8 `launch0()` rows + 18 `excluded_from_launch0()` rows = 40 entries, which resolve to **28 distinct CIRs**. The brief's "40" is the entry count.
- **Recorded per CIR:** `title_promise` (backed, claimed, markers), `fabric_truth` and `colourwork_findings`.
- **Every pair is byte-identical** (8cf4a458 vs b185b528 vs f4bf34bb; 5889cc37 vs 2f9c413d; a859f6fe vs d3a485a1).
- **On every head:** 28/28 are backed, and `launch0_is_all_gate_clean()` is True.

## Mutations (each reverted; every mutation worktree clean afterwards)

Subject 1 mutants ran against test_opus2_draft_constructions. Subject 2 mutants ran against test_opus2_cir_colourwork. Subject 3 mutants ran against test_opus2_stocking, then test_opus2_pet_bed.

| ID | Subject | Mutation | Result |
|---|---|---|---|
| Q1a | 1 | `_inflected`: `-d` branch removed | killed |
| Q1b | 1 | `_inflected`: `-ed` branch removed | **survives** (OPUS2Q-6) |
| Q1c | 1 | `_morphological_count` root loop disabled | killed |
| Q1d / Q1e / Q1f / Q1g / Q1h | 1 | root "dy" / "tetr" / "non" / "dec" / "sest" removed | killed / killed / killed / killed / killed |
| Q1v / Q1z / Q1aa / Q1ab / Q1ac | 1 | root "sext" / "twi" / "ter" / "hept"+"hepta" / "oct"+"octu" (→ "octu" only) removed | **survive** (OPUS2Q-6) |
| Q1i / Q1j / Q1k / Q1w / Q1x | 1 | suffix `fecta` / `somes?` / `plicates?` / `ads?` / `e?ts?` removed | killed |
| Q1l / Q1y | 1 | suffix `pled` / `sets?` removed | **survive** (OPUS2Q-6) |
| Q1m / Q1n / Q1ad / Q1ae | 1 | Roman numerals / "thousand" / "million" / `_LARGE_NUMBERS` disabled | killed |
| Q1o / Q1p | 1 | NFKC fold / U+2019 → ' fold removed | killed / killed |
| Q1q / Q1r | 1 | "poly" prefix / bare "pack" marker removed | killed / killed |
| Q1s | 1 | "triple" removed from the strand/tone `_NOT_A_COUNT` clause | killed |
| Q1t / Q1u | 1 | "son" / "lot" removed from `_PLURAL_WORDS` | **survives** / killed |
| Q2a | 2 | trailing `\b` on the C2C variant removed (this would fix OPUS2Q-2) | **survives** (no test needs the `\b`) |
| Q2b / Q2c | 2 | `c ?(?:2\|to) ?c` → `c ?2 ?c` / `corner ?(…) ?corner` → `corner (…) corner` | killed / killed |
| Q2d / Q2q / Q2r | 2 | `_INVISIBLE` emptied / U+2800 removed / U+180B–180F removed | killed / killed / survives: equivalent (those are Mn or Cf, and are dropped anyway) |
| Q2e | 2 | Mn/Me drop → `unicodedata.combining()` (the OPUS2O-5 state) | killed |
| Q2f / Q2h / Q2i / Q2t | 2 | look-alike ı / Ӏ (U+04CF) / ς / ᴀ removed | killed |
| Q2g / Q2j / Q2s | 2 | look-alike ɡ / ј / օ removed | **survive** (OPUS2Q-6) |
| Q2k / Q2n | 2 | count word "thirteen" / "many" removed | **survive** (OPUS2Q-6) |
| Q2l / Q2m | 2 | count word "dozen" / "quad" removed | killed / killed |
| Q2o / Q2p | 2 | `shade\|hue` / `polychrom` removed | killed / killed |
| Q3a | 3 | contrast-cuff guard disabled | killed (stocking) |
| Q3b | 3 | guard compares colour names, not hex values | **survives** (OPUS2Q-6) |
| Q3c | 3 | "striped" dropped from the guard regex | **survives** (OPUS2Q-6) |
| Q3d | 3 | "solid" re-added to the allowlist | killed (stocking) |
| Q3e / Q3f | 3 | pet route back to `lower()` (both reads / the second only), i.e. OPUS2O-7 D12 | killed / killed (stocking) |
| Q3g | 3 | guard reads `concept.title` without `fold_title` | killed (stocking) |
| Q3h | 3 | `STOCKING_SIZE_SOURCE` carries a URL again | killed (stocking) |

## Suites

Each suite ran from `brambleloop/`, one at a time, after `pip install -r requirements.txt`:
`PYTHONPATH=src:tests PYTHONDONTWRITEBYTECODE=1 python3 tests/<f>.py`. "ok" counts the suite's OK/PASS lines.

Every suite listed exited 0 with 0 failures, apart from the one marked UNKNOWN.

| Head | Suites (ok) |
|---|---|
| b185b528 (1) | test_opus2_draft_constructions (21), test_launch0 (52), test_first_customer_gate (12 passing), test_compiler (9), test_twin (8), test_reverse (18), test_vacuity (8), test_products (16), test_products_adversarial (15), test_w4_pipe_board (70), test_opus2_size_claims (13), test_w4_listready (31), test_fallback_draft_provenance (1). **test_shadow: UNKNOWN.** The first run hit the 900 s timeout (rc 124) after 5 OK lines while 3 other suites were running in parallel; the rerun is reported in the addendum below. |
| f4bf34bb (1m) | test_opus2_draft_constructions (21), test_first_customer_gate (12 passing), test_launch0 (52), test_compiler (9) |
| 2f9c413d (2) | test_opus2_cir_colourwork (20), test_compiler (9), test_twin (8), test_reverse (18), test_vacuity (8), test_pattern_truth (11), test_launch0 (52), test_first_customer_gate (12 passing), test_physfix (46/46), test_w4_seo_packages (6), test_search_truth (32 passing), test_w4_pipe_board (70) |
| d3a485a1 (3) | test_opus2_stocking (8), test_opus2_pet_bed (7), test_opus2_draft_constructions (18), test_fallback_draft_provenance (1), test_vacuity (8), test_products (16), test_products_adversarial (15), test_launch0 (52), test_geometry (44), test_w4_c03_fallback (6 passed), test_compiler (9), test_reverse (18), test_twin (8), test_physical (18), test_deliverable_qa (61), test_shadow (10) |

## Commands

```
git fetch origin claude/w5-SECREVIEW-OPUS2O opus2/p0-revenue-workforce opus2/p0-revenue-workforce-b4merge \
    opus2/p0-cir-colourwork opus2/p0-stocking
git diff 8cf4a458..b185b528; git diff 5889cc37..2f9c413d; git diff a859f6fe..d3a485a1
diff <(git diff 80f4b073..f4bf34bb) <(git diff 8cf4a458..b185b528)            # identical
git diff --stat b185b528 f4bf34bb -- .../launch0.py .../test_opus2_draft_constructions.py   # empty
git diff <range> -- brambleloop/tests | grep -cE '^-[^-]'                        # 0, 0, 0
git worktree add --detach $S/wt_<head> <head>       # 7 heads + 3 mutation copies
python3 $S/probes/tp.py  < titles.txt   # multiplicity + plan(bag) + title_promise, 160 titles
python3 $S/probes/fp.py                 # title_promise on the renamed one-piece blanket
python3 $S/probes/cw.py  < cw.txt       # claims + fabric_truth + colourwork_findings, title and tag
python3 $S/probes/cw.py  < cw3.txt      # C2C compounds, 5889cc37 vs 2f9c413d
python3 $S/probes/stk.py < stk.txt      # plan × 6 categories, a859f6fe vs d3a485a1
python3 $S/probes/cuff.py               # stocking() × 9 titles × 6 palettes
python3 $S/probes/cat.py; python3 $S/probes/ident.py   # catalogue + listing strings, before vs after
python3 $S/probes/mut.py <wt> <file> <id> '<old>' '<new>' <suite...>   # apply once, run, restore
curl -sSL https://www.homedepot.ca/product/northlight-20-traditional-red-with-white-cuff-hanging-christmas-stocking/1001820543
```

The probe scripts stay in the reviewer's scratchpad and were not committed. Each uses only the
repository's public functions and test fixtures on the named commit, with no network access.
