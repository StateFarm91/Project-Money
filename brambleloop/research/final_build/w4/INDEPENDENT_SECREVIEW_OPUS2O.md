# Independent security and correctness review OPUS2O: Secondary's fixes for OPUS2L, OPUS2M and OPUS2N, 2026-11-02

Reviewer: an independent, adversarial, read-only Claude Code session (branch `claude/w5-SECREVIEW-OPUS2O`).
- The review was read-only on every branch under review. This report is the only file written.
- Every probe and mutation ran in scratch worktrees in the session scratchpad: 13 worktrees, one
  per head plus a mutation copy of each. Each mutation was reverted (the runner writes the original
  file back). Every mutation worktree was clean afterwards (`git status --porcelain`: 0 lines).
- Nothing was deployed, published, messaged or spent. Railway and production were not touched.
  The only network use was `git fetch` and one read-only GET of the stocking size citation (OPUS2O-9).

| # | Subject | Branch | Head | Delta reviewed |
|---|---|---|---|---|
| 1 | PR #3 multiplicity (OPUS2M-1, M-7) | opus2/p0-revenue-workforce | 8cf4a458 | 6769e696..8cf4a458 |
| 1m | same, merged | opus2/p0-revenue-workforce-b4merge | 80f4b073 (merge of 8cf4a458) | 651b1580..80f4b073 (first parent) |
| 2 | PR #9 colourwork claim reader (OPUS2M-2, M-3, M-4, M-8) | opus2/p0-cir-colourwork | 5889cc37 | d4486b8c..5889cc37 |
| 3 | PR #10 pet bed (OPUS2N-1, N-2, N-5) | opus2/p0-pet-bed | 09122165 | 940f70e6..09122165 |
| 4 | PR #11 stocking (OPUS2L-1..L-7) | opus2/p0-stocking | a859f6fe | 0ef8a716..a859f6fe, first parent: bd3399eb (merge of 940f70e6), e07157dc, a859f6fe (merge of 09122165) |

## Verdicts

| # | Subject | Verdict | Why |
|---|---|---|---|
| 1 | Multiplicity reader (8cf4a458) | **DO NOT SHIP** as the M-1 closure. It is not a regression: it is strictly stricter than 6769e696 apart from OPUS2O-3. | The unification is real: `plan()` now refuses everything `title_promise` would not back, so the two readers can no longer disagree in the unsafe direction. Every OPUS2M-1 repro is closed and pinned. But the requirement was a **class** reader, and the fix adds eight more words to a list. On the sunset tote, these are still drafted as one tote and `title_promise`-backed: "Tote Quintuplets", "Tote Sextuplets", "Tote Septuplets", "Tote Octuplets", "Tote Quintuple" … "Tote Octuple", "Tote Fivesome", "Tote Sixsome", "Tote Dyad", "Tote Tetrad", "Tote Pentad", "Tote Hexad", "Tote Sestet", "Tote Nonet", "Tote Quintette", "Tote Tri-Pack", "Tote Tripack", "Tote Quadpack", "Tote Twopack", "Tote Bi-Pack", "Multi-Tote", "Tote Multiset", "Thousand Tote", "Million Tote", "Tote Triplicate", "Sisters Tote", "Brothers Tote", "Tote Siblings", "Father Son Tote" (OPUS2O-1, MED). |
| 1m | merge 80f4b073 | **Faithful** | `git diff 651b1580..80f4b073` is byte-identical to `git diff 6769e696..8cf4a458`. The 128-title probe and the catalogue probe give identical output on 8cf4a458 and 80f4b073. The suites pass. It carries OPUS2O-1 with it. |
| 2 | Colourwork claim reader (5889cc37) | **DO NOT SHIP** (small fix) | The OPUS2M-2 regression is closed: "Minimosaic", "Microtapestry", "Multicolourwork", "Superfairisle" and "Pseudointarsia" are refused on plain fabric, as title and as tag. Every M-3, M-4 and M-8 repro is closed and pinned, and the fold now runs before lowering. But the same classes are still open beyond the listed spellings: "Corner2Corner", "Cornertocorner", "C to C", "C-to-C" (C2C variants), and "Eleven/Twelve/Dozen/Quad Colour" (counts) (OPUS2O-4, MED); and invisible non-Cf characters plus non-decomposing look-alikes (OPUS2O-5, LOW). |
| 3 | Pet bed (09122165) | **SHIP** | N-1 is closed: the allowlist is now total. Every OPUS2N-1 repro and every new probe with an emoji, another script, a symbol, a numeral form, a combining mark, a zero-width character or a non-ASCII dash before the head noun is refused. N-2 is closed: "round" is gone, and "Round Cat Bed" is refused and pinned. N-5 is closed: the compiled note reads 51.2 cm across the points and 44.3 cm across the flats, which the comment now states. Every new guard is killed by a test. |
| 4 | Stocking (a859f6fe) | **SHIP** | L-1 (HIGH) is closed by the shared construction-intent rule. On all 104 probe titles × 6 categories, "X Stocking" drafts only when every word before the head noun is allowlisted. "Compression", "Nylon", "Fishnet", "Silk", "Support", "Medical", "Anti-Embolism", other products, sizes, audiences, Christmas motifs, embellishments, number words, Unicode dashes, fullwidth forms, emoji and Cyrillic are all refused in every category. L-2..L-5 are closed, L-6 is closed in the text, and L-7 is honestly reworded. The shared rule changes pet-bed behaviour vs 09122165 only by drafting four more spellings of "Cat Bed" (OPUS2O-8, INFO). The residuals are LOW: OPUS2O-6 (a "Contrast Cuff" title on a one-colour palette) and OPUS2O-9 (a dead retail citation in a code comment and constant). |

Subjects 1 and 2 each need one more change, and nothing else first. Subjects 3 and 4 can merge as
they are; the LOW items can follow.

## Findings

Subject 1 probes: `F.plan(category="bag", title=t)` and `L.title_promise(replace(sunset, title=t))`
on the one-piece sunset tote from `test_opus2_draft_constructions` (128 titles). Subject 2: `fabric_truth`
and `colourwork_findings` on the all-plain `_band({})` fixture, as title ("<w> Basket") and as tag.
Subjects 3 and 4: `F.plan` over 84 pet titles, and 104 stocking titles × {stocking, seasonal,
home_decor, blanket, bag, pet}. Each drafted stocking was then built with `F.stocking`, and
`compile_cir`, `name_truth`, `product_type_findings`, `title_promise` and `motif_promise` were run on it.

| ID | Sev | Subject | Finding | Repro |
|---|---|---|---|---|
| OPUS2O-1 | **MED** | 1 | **The multiplicity reader is still a word list, not a class.** `multiplicity()` reads a count only from a token that is a numeral or a `_COUNT_WORDS` key (with -s/-es/-ies inflection), plus `_PLURAL_WORDS` and the marker and noun lists. The brief named the numeric roots tri/quad/quint/sext/sept/oct and the suffixes -some/-let/-uple/-ad/-et. Of these, only the exact words threesome, foursome, triad, triple, quad, quadruple and quadruplet were added. Drafted as one tote, with `title_promise.backed` True (claimed None, markers ()): **-uplet/-uple** "Tote Quintuplet(s)", "Tote Sextuplets", "Tote Septuplets", "Tote Octuplets", "Tote Quintuple", "Quintuple Tote", "Tote Sextuple", "Tote Septuple", "Tote Octuple"; **-some** "Tote Fivesome", "Tote Sixsome"; **-ad** "Tote Dyad", "Tote Tetrad", "Tote Pentad", "Tote Hexad"; **-et/-ette** "Tote Sestet", "Tote Nonet", "Tote Decet", "Tote Quintette"; **root + pack** "Tote Tri-Pack", "Tote Tri Pack", "Tote Tripack", "Tote Quadpack", "Tote Twopack", "Tote Bi-Pack" ("Tote Quad Pack" and "Tote Twin Pack" are refused only because quad and twin are whole words); **multi-** "Multi Tote", "Multi-Tote", "Tote Multiset" (but "Tote Multi-Set" is refused through "set"); **large numbers** "Thousand Tote", "Million Tote"; **other** "Tote Triplicate", "Tote Trifecta", "Tote Duplicate"; **family nouns** "Sisters Tote", "Brothers Tote", "Tote Siblings", "Father Son Tote", "Mommy Tote" (mother, daughter and family are listed; sister, brother, sibling, son, father and mommy are not). Still ambiguous and still drafted, as in OPUS2M-1: "Tote Pack", "Tote Packs", "Tote Value Pack", "Tote Variety Pack", "Tote Combination(s)", "Tote Assorted", "Tote Mix", "Tote Selection", "Tote Series", "Tote II", "Tote III", "Tote Ⅲ", "Tote ③", "Tote Score", "Tote Gross", "Tote Matched", "Tote Matchy", "Tote Coordinating". The commit says "the rest of the class, not only the listed words". The code does not do that. *Fix (either):* (a) read by morphology, not membership. A count root `(?:bi\|di\|du[o]?\|twi\|tri\|ter\|quadr?u?\|tetra\|quint\|penta\|sext\|hexa\|sept\|hepta\|oct[ao]?\|non\|dec[ai]?\|multi\|poly)` followed by `(?:ple[sdt]?s?\|plets?\|plicate\|ads?\|e?ts?\|ettes?\|somes?\|packs?\|sets?\|fecta)`, or a number word + `some`; any `\bpacks?\b`; roman numerals ≥ II as a whole token; thousand and million; and the sibling and parent nouns. (b) Better, and consistent with the pet and stocking routes: route to `tote` only when every word in the title is in a tote allowlist, through the shared `modifiers_outside` rule now on the stocking branch. Pin "Tote Quintuplets", "Tote Tetrad", "Tote Tri-Pack" and "Multi-Tote". | `tp.py < titles.txt` on 8cf4a458 and 80f4b073 |
| OPUS2O-2 | LOW | 1, 2 | **List-entry test gaps in the new code.** These mutants survive their suites: **A2** removes the `-es` branch of `_inflected` (no pinned title needs `-es`, e.g. "Tote Sixes"); **A7** removes "lot" from `_PLURAL_WORDS` (only "Tote Kit" is pinned, not "Tote Lot"); **B13** removes the Cyrillic р→p look-alike (only Т and а are pinned, via "Таpestry"); **B14** removes six…nine from the colour-count alternation (only five and ten are pinned). Every core rule of the four deltas is killed (mutations table). | mutants A2, A7, B13, B14 |
| OPUS2O-3 | LOW | 1 | **Small regression in the `title_promise` backstop: `-d`/`-ed` count forms are no longer read.** The old reader tried `token[:-1]` for any last letter. The new `_inflected` strips only `-s`/`-es`/`-ies`. "Tote Doubled" was unbacked on 6769e696 and is backed on 8cf4a458. "Tote Tripled", "Tote Quadrupled" and "Tote Coupled" are backed on both. `plan()` drafts all four as one tote on both heads. Low impact, but it is a loosening that the commit does not mention. *Fix:* add `d`/`ed` to `_inflected`. | `tp.py`, diff 6769e696 vs 8cf4a458 |
| OPUS2O-4 | **MED** | 2 | **C2C and colour-count variants are still enumerated, not read as a class.** On `_band({})` these are backed with 0 listing findings, as title and as tag: **C2C** "Corner2Corner", "Cornertocorner", "C to C", "C-to-C" and "Ctoc". `_fold` does not split letters from digits, and the variant needs `corner (?:to\|2) corner` with spaces and `c ?2 ?c` with a literal 2. "Corner2Corner" is a common hashtag spelling, so it is likely in tags. **Counts** "Eleven Colour", "Twelve-Colour", "Dozen Colour" and "Quad Colour": the count alternation stops at "ten". "Five Shade", "Two-Shade", "Two Hue" and "Polychrome" also pass. These are arguable, but they are the same claim. The same probe on d4486b8c gives the same result for all of these, so none is a regression. They are the residue of OPUS2M-3, which asked for the class. *Fix:* in `_fold`, insert a space at letter↔digit boundaries; use `c ?(?:2\|to) ?c` and `corner ?(?:2\|to) ?corner`; and drive the count alternation from one number-word list (the `_COUNT_WORDS` keys) plus `quad\|poly\|many`, with `(?:colou?r\|tone\|shade\|hue)`. Pin "Corner2Corner Basket" and "Eleven Colour Basket". | `cw.py < cw.txt` on 5889cc37 vs d4486b8c |
| OPUS2O-5 | LOW | 2 | **Invisible characters that are not category Cf, and look-alikes that do not decompose, still split a claim word.** Backed on plain fabric: "Tape͏stry" (U+034F COMBINING GRAPHEME JOINER: category Mn, combining class 0, so `unicodedata.combining()` keeps it), "Tape️stry" (U+FE0F VARIATION SELECTOR-16, the same), "Mo឴saic" (U+17B4, Mn, ccc 0), "Moᅟsaic" (U+115F) and "Tapeㅤstry" (U+3164 HANGUL FILLER, Lo), "Tape⠀stry" (U+2800). Look-alikes not in `_LOOKALIKES`: "Faır Isle" and "Mosaıc" (U+0131 dotless i), "Coløurwork" (ø), "Moѕaic" (U+0455), "Mosaiϲ" (U+03F2), "Mosօic" (U+0585), "Mosᴀic" (U+1D00), "Mosɑic" (U+0251), "Fair Ӏsle" (U+04C0). The commit says the map is "small and explicit, not a general confusables table", and OPUS2M-4 called the map optional, so this is LOW. *Fix:* drop every character with category Mn/Me (not only combining class > 0) and every Default_Ignorable_Code_Point; add ı→i, ø→o and the Cyrillic/Greek small letters dze, je, lunate sigma and palochka. | `cw.py < cw2.txt` |
| OPUS2O-6 | LOW | 4 | **"Contrast Cuff" and "Stripe(d) Cuff" are admitted from the title alone, without checking the palette.** `banded = re.sub(r"\b(?:stripe\|striped\|contrast\|contrasting) cuff\b", "cuff", …)` makes the title draftable. But `stocking()` accepts a one-colour palette (`accent = palette[1 % len(palette)]`, which is `main` when there is one colour). "Contrast Cuff Christmas Stocking" with one colour compiles with 0 findings, `name_truth` [], `product_type_findings` [], `fabric_truth.backed` True and colourwork [], and the cuff is the body colour. Conversely, "Solid" is allowlisted, but a two-colour stocking always has an accent cuff. *Fix:* refuse "contrast/stripe cuff" when `len(set(palette[:2])) < 2`, or have `stocking()` refuse that title. Drop "solid", or refuse it when the cuff is a contrast. | `cuff.py` on a859f6fe |
| OPUS2O-7 | LOW (test gap, fail-closed) | 4 | **The pet route's switch to `fold_title` is unpinned.** Mutant D12 reverts the pet route to `title.lower().replace("’", "'")` and survives `test_opus2_stocking` and `test_opus2_pet_bed`. The difference only drafts "Cat‑Bed" (U+2011), "Cat‒Bed", "Cat−Bed" and "Ｃat Bed" (OPUS2O-8). So the surviving mutant is the fail-closed direction. | mutant D12 |
| OPUS2O-8 | INFO | 4 vs 3 | **The shared rule changes pet-bed behaviour vs 09122165 only toward plain cat beds.** Over 84 pet titles, the only family differences between 09122165 and a859f6fe are "Cat‑Bed" (U+2011), "Cat‒Bed" (U+2012), "Cat−Bed" (U+2212) and "Ｃat Bed" (fullwidth C). These were refused and are now drafted, and each means "Cat Bed". "Ⅱ Cat Bed" is still refused (now as 'ii'). "Ｄｏｇ Bed" and "Cat Ｄog Bed" are refused on both heads. The pet constants (`_PET_BED_HEAD`, `_PET_BED_NOT_PLAIN`, `_PET_BED_ALLOWED_WORDS`, `_PET_BED_OTHER_ANIMALS`) are byte-identical between the two heads. The pet block differs only by `fold_title` and by the call to `modifiers_outside`, which is the 09122165 logic moved into a function. `vessels.py` and `test_opus2_pet_bed.py` are identical (`git diff 09122165 a859f6fe` on them is empty). The rule is genuinely shared: the stocking route calls the same `modifiers_outside`, and its leftover check is killed by both suites (D3). | `pet.py < pet.txt` on 09122165 vs a859f6fe |
| OPUS2O-9 | LOW | 4 | **The L-7 retail citation does not resolve.** `STOCKING_SIZE_SOURCE` and its comment cite "Northlight 20-inch stocking, 20 x 9 in (Home Depot Canada listing 1001820543)". A GET of that URL on 2026-11-02 returned HTTP 200 with `<title>Product Not Found \| The Home Depot Canada`, and the page has no product data and no "Northlight" or "stocking" text. So the 20 × 9 in figure is **UNKNOWN**, not verified. The constant leads with "design choice; no published standard stocking size found", which is honest, and it is read only by the test, not by the listing or the size note. So this is LOW. *Fix:* drop the retail example, or replace it with a retrievable source quoted verbatim, as `PET_BED_SIZE_SOURCE` does. | `curl -sSL <url>` |
| OPUS2O-10 | INFO | 1 | **New fail-closed refusals in the delta.** "Triple Strand Tote" and "Triple Stranded Tote" are now refused by `plan` and unbacked: "triple" counts 3, and `_NOT_A_COUNT` exempts only `(two\|three)[- ]strand`. "Three Strand Tote" stays backed. "Mother’s Day Tote" (U+2019) is unbacked because the clause is ASCII `'?`, while "Mother's Day Tote" and "Mothers Day Tote" are backed. "Mommy And Me Tote" is refused by `plan` (`and`) but backed by `title_promise`. That is the safe direction. No catalogue CIR is affected (below). | `tp.py` |
| OPUS2O-11 | INFO | 2 | **New fail-closed claims.** "1 Colour Basket" is now a colourwork claim (`\d+`), and so is "Colour Workshop …", because `colou?r ?works?` has no trailing boundary. These are refused on plain fabric, which is the safe direction. Catalogue output is unchanged (below). | `cw.py` |
| OPUS2O-12 | INFO | 1, 2 | **Every prior repro was re-run and is closed.** **1:** all 21 OPUS2M-1 titles, plus the M-1 plural-marker titles (Mothers, Families, Daughters, Multipacks, Doubles), are refused by `plan` and unbacked. The new pins cover N5, N8, N9, N11, N14, N15 and N19-N21. **2:** every OPUS2M-2 compound; every OPUS2M-3 inflection, count and spelling; and every OPUS2M-4 Unicode form ("Tape​stry", "Mo­saic", "Mo‍saic", "Fáir Ísle", "FAİR ISLE", "Таpestry", full-width) is refused as title and as tag. "Double-Stranded" and "Held Stranded" are still backed (K-6a). Removing the trailing NFKC (B19) survives as an equivalent mutant: NFKD already applies the compatibility fold, so full-width forms are caught either way. Removing NFKD (B12) is killed. | `tp.py`, `cw.py` |

**Removed or weakened assertions: none.**
- **8cf4a458 and 5889cc37:** 0 test lines removed. Both diffs only add tests.
- **09122165:** the 3 removed lines take "Round Cat Bed" out of the two drafted lists, which N-2 asked for. It is now asserted refused.
- **0ef8a716..a859f6fe:** the 2 removed test lines are the same "Round Cat Bed" edit, and the K-9 assert gains `"https://" in …` and the `"thesize" not in …` check, so it is stronger.
- **Source:** on 8cf4a458, "matching", "family", "mother" and "daughter" moved from `_PLURAL_OBJECT_NOUNS` to `_PLURAL_WORDS`, which reads them with more inflections. That is stricter, apart from OPUS2O-3. `_NOT_A_COUNT` gained only feature clauses (double handle/strap, mother's/father's day, triple crochet/treble). Those loosen `title_promise` on purpose (OPUS2M-9), and `plan` still refuses all of them through `_MULTIPLE_WORDS` ("double").
- No compiler, twin or gate path changed. No deterministic validation was overridden.

**Catalogue: no new false positive.** `cat.py` enumerates `BUILDERS` (11), `PROPOSED_BUILDERS` (3),
`builder.CATALOGUE`, the `nordic_forest` sizes, the three market baskets, the hexagon coaster set and every
`inventory.universe()` slug. That gives **28 distinct CIRs**. The brief's "40" matches
11 `BUILDERS` + 3 `PROPOSED_BUILDERS` + 8 `launch0()` rows + 18 `excluded_from_launch0()` rows = 40
entries, which resolve to the same 28 CIRs.
- **What is recorded per CIR:** `title_promise` (backed, claimed, markers), `fabric_truth`, `colourwork_claims`, and `colourwork_findings` on the title and tags.
- **Subject 1:** the output is byte-identical between 6769e696, 8cf4a458 and 80f4b073, apart from the field that is new in 8cf4a458.
- **Subject 2:** the output is byte-identical between d4486b8c and 5889cc37.
- **On every head:** every CIR is backed, colourwork findings are 0, and `launch0_is_all_gate_clean()` is True.
- **Listing words:** `ident.py` runs `multiplicity` and `colourwork_claims` over every `ListingIdentity` field string, title and slug in `launch_scope_slugs()` (41 strings). The output is identical before and after. The only claims are in slugs, which neither gate reads, and the only counts are on genuinely multi-piece products ("Hexagon Coaster Set (4)", "… Placemat Pair", "Nesting Baskets, three sizes", "Ornament Set (6)"), all of which are backed.

## Mutations (each reverted; every mutation worktree clean afterwards)

| ID | Subject | Mutation | Result |
|---|---|---|---|
| A1 | 1 | `_inflected`: `-ies` → `y` branch removed | killed (draft_constructions) |
| A2 | 1 | `_inflected`: `-es` branch removed | **survives** (OPUS2O-2) |
| A3 | 1 | "multi pack" → multipack fold removed | killed |
| A4 / A4b / A4c | 1 | `plan()` ignores `multiplicity` entirely / its claimed count / its markers | killed / killed / killed |
| A5 / A6 / A11 | 1 | "hundred" / quadruple+quadruplet / threesome, foursome, triad, triple removed | killed |
| A7 | 1 | "lot" removed from `_PLURAL_WORDS` | **survives** (OPUS2O-2) |
| A8 / A13 | 1 | the feature + occasion `_NOT_A_COUNT` clause / the mother's-father's day part only | killed / killed |
| A9 | 1 | `triple[- ](crochet\|treble)` not-a-count removed | killed |
| A10 | 1 | `multipacks?\|multi-packs?` removed from `_PLURAL_OBJECT_NOUNS` | survives: equivalent (read through `_PLURAL_WORDS` after the fold) |
| A12 | 1 | markers matched on `lowered` instead of `counted` | survives: equivalent (no `_NOT_A_COUNT` clause removes a marker word) |
| B1 | 2 | base claims back to word-start `\b…` (the OPUS2M-2 regression) | **killed** (cir_colourwork) |
| B2 / B3 / B12 / B4 | 2 | Cf removal / combining-mark drop / NFKD / `_LOOKALIKES` removed | killed |
| B5 / B6 / B7 / B8 | 2 | `tapestri` / `\d+` count / `colou?r ?block` / `pixel crochet` removed | killed |
| B9 / B10 | 2 | `c ?2 ?c` → `c2c` / `corner (to\|2) corner` → `corner to corner` | killed |
| B15 / B17 / B18 | 2 | dual+duo removed / `tone` removed from the count / trailing `\b` restored on variants | killed |
| B11 | 2 | `fair ?isle` variant removed | survives: equivalent (base substring claims "fair isle", "fairisle") |
| B13 | 2 | Cyrillic р→p look-alike removed | **survives** (OPUS2O-2) |
| B14 | 2 | six…nine removed from the count alternation | **survives** (OPUS2O-2) |
| B16 | 2 | `colou?r ?works?` → `colou?r works?` | survives: equivalent (base substring "colourwork") |
| B19 | 2 | trailing NFKC removed | survives: equivalent (NFKD already folds compatibility forms) |
| C1 | 3 | the OPUS2N-1 leftover check disabled | **killed** (pet_bed) |
| C2 | 3 | "round" re-added to the allowlist | killed |
| C3 / C4 | 3 | typographic-apostrophe fold removed / `'s` token form removed | killed / killed |
| C5 | 3 | leftover class `[a-z0-9…]` → Unicode `\w` (other scripts pass) | killed |
| C6 | 3 | leftover counts emoji only | killed |
| D1 / D3 / D13 | 4 | stocking allowlist disabled / shared leftover check disabled / pet call to `modifiers_outside` disabled | killed (stocking; D3 and D13 also pet_bed) |
| D2 / D14 | 4 | "stripe/contrast cuff" fold removed / widened to any "stripe(d)" | killed |
| D4 / D5 / D9 | 4 | `fold_title` without NFKC / without the Pd→"-" fold / without the whitespace collapse | killed |
| D6 / D7 / D8 / D15 | 4 | allowlist + compression / + santa, baby, big / + striped / − cuff | killed |
| D10 / D11 | 4 | `STOCKING_SIZE_SOURCE` no longer "design choice" / the wrong-side sentence removed | killed |
| D12 | 4 | the pet route back to `lower()` instead of `fold_title` | **survives** (fail-closed; OPUS2O-7) |

Mutants per subject were run against: 1 — test_opus2_draft_constructions, test_launch0,
test_first_customer_gate; 2 — test_opus2_cir_colourwork, test_first_customer_gate, test_launch0;
3 — test_opus2_pet_bed, test_opus2_draft_constructions; 4 — test_opus2_stocking, test_opus2_pet_bed.
After the runs, `git status --porcelain` printed 0 lines in all four mutation worktrees.

## Suites (from `brambleloop/`, `PYTHONPATH=src:tests PYTHONDONTWRITEBYTECODE=1 python3 tests/<f>.py`, one at a time, after `pip install -r requirements.txt`)

Every suite exited 0 with 0 failures ("ok" counts the suite's OK/PASS lines).

| Head | Suites (ok) |
|---|---|
| 8cf4a458 (1) | test_opus2_draft_constructions (20), test_launch0 (52), test_w4_pipe_board (70), test_opus2_size_claims (13), test_first_customer_gate (12 passing), test_compiler (9), test_twin (8), test_reverse (18), test_vacuity (8), test_w4_listready (31), test_opus2_knowledge_gaps (9), test_fallback_draft_provenance (1), test_shadow (10), test_products (16), test_products_adversarial (15) |
| 80f4b073 (1m) | test_opus2_draft_constructions (20), test_first_customer_gate (12 passing), test_launch0 (52), test_compiler (9) |
| 5889cc37 (2) | test_opus2_cir_colourwork (19), test_compiler (9), test_twin (8), test_reverse (18), test_vacuity (8), test_pattern_truth (11), test_launch0 (52), test_leadtime (21), test_first_customer_gate (12 passing), test_physfix (46/46), test_w4_seo_packages (6), test_search_truth (32 passing), test_w4_pipe_board (70) |
| 09122165 (3) | test_opus2_pet_bed (7), test_opus2_draft_constructions (18), test_fallback_draft_provenance (1), test_vacuity (8), test_shadow (10), test_products (16), test_products_adversarial (15), test_launch0 (52), test_geometry (44), test_w4_c03_fallback (6 passed) |
| a859f6fe (4) | test_opus2_stocking (7), test_opus2_pet_bed (7), test_opus2_draft_constructions (18), test_fallback_draft_provenance (1), test_vacuity (8), test_shadow (10), test_products (16), test_products_adversarial (15), test_launch0 (52), test_geometry (44), test_w4_c03_fallback (6 passed), test_physfix (46/46), test_physical (18), test_compiler (9), test_reverse (18), test_twin (8), test_cert_parity_copy (20 passing), test_deliverable_qa (61), test_schematic (PASS), test_search_truth (32 passing) |

## Commands

```
for b in opus2/p0-revenue-workforce opus2/p0-revenue-workforce-b4merge opus2/p0-cir-colourwork \
         opus2/p0-pet-bed opus2/p0-stocking; do git fetch origin "+refs/heads/$b:refs/remotes/origin/$b"; done
git fetch origin claude/w5-SECREVIEW-OPUS2L claude/w5-SECREVIEW-OPUS2M     # prior reports
git diff 6769e696..8cf4a458; git diff d4486b8c..5889cc37; git diff 940f70e6..09122165
git log --first-parent 0ef8a716..a859f6fe; git diff 0ef8a716..a859f6fe
diff <(git diff 651b1580..80f4b073) <(git diff 6769e696..8cf4a458)          # identical
git diff 09122165 a859f6fe -- tests/test_opus2_pet_bed.py src/.../vessels.py # empty
git diff <range> -- brambleloop/tests | grep -E '^-[^-]'                     # removed asserts
git worktree add --detach $S/{rw,rw0,rb,cw,cw0,pb,pb0,st,st0,rwm,cwm,pbm,stm} <head>
python3 $S/probes/tp.py  < titles.txt   # plan(bag) + title_promise + multiplicity, 128 titles
python3 $S/probes/cw.py  < cw.txt       # fabric_truth + colourwork_findings, title and tag, _band({})
python3 $S/probes/pet.py < pet.txt      # plan(pet), 84 titles, 09122165 vs a859f6fe
python3 $S/probes/stk.py < stk.txt      # plan × 6 categories, then stocking → compile + 4 gates
python3 $S/probes/cuff.py               # "Contrast Cuff" on a 1- and 2-colour palette
python3 $S/probes/cat.py; python3 $S/probes/ident.py   # catalogue + listing words, before vs after
python3 $S/probes/mut.py <wt> <file> <id> '<old>' '<new>' <suite...>   # apply once, run, restore
curl -sSL https://www.homedepot.ca/product/northlight-20-traditional-red-with-white-cuff-hanging-christmas-stocking/1001820543
```

The probe scripts stay in the reviewer's scratchpad and were not committed. Each uses only the
repository's public functions and test fixtures on the named commit, with no network and no
database outside the suites' temporary SQLite.
